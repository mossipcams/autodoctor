"""Runtime health monitoring for automation trigger behavior."""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path
from statistics import fmean, median
from typing import Any, Protocol, cast

from .const import (
    DEFAULT_RUNTIME_HEALTH_GAP_THRESHOLD_MULTIPLIER,
    DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
    DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
    DOMAIN,
)
from .models import IssueType, Severity, ValidationIssue
from .runtime_health_state_store import RuntimeHealthStateStore

_LOGGER = logging.getLogger(__name__)
_TELEMETRY_RETENTION_DAYS = 90
_BUCKET_NIGHT_START_HOUR = 22
_BUCKET_MORNING_START_HOUR = 5
_BUCKET_AFTERNOON_START_HOUR = 12
_BUCKET_EVENING_START_HOUR = 17
_DEFAULT_RUNTIME_FLUSH_INTERVAL_MINUTES = 15
_BACKFILL_MIN_LOOKBACK_DAYS = 30
_GAP_MODEL_MAX_RECENT_INTERVALS = 32
_SPARSE_WARMUP_LOOKBACK_DAYS = 90


class _Detector(Protocol):
    """Anomaly detector interface for runtime monitoring."""

    def score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        window_size: int | None = None,
    ) -> float:
        """Train from history rows and return anomaly score for the current row."""
        ...


class _BOCPDDetector:
    """BOCPD detector using Gamma-Poisson predictive updates.

    The detector maintains a run-length posterior and a bounded history of
    observations to score the next count with a posterior predictive tail score.
    """

    def __init__(
        self,
        *,
        hazard_rate: float = DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
        max_run_length: int = DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
        count_feature: str = "rolling_24h_count",
    ) -> None:
        self.hazard_rate = min(1.0, max(1e-6, float(hazard_rate)))
        self.max_run_length = max(2, int(max_run_length))
        self._prior_alpha = max(1e-6, float(prior_alpha))
        self._prior_beta = max(1e-6, float(prior_beta))
        self._count_feature = count_feature

    def initial_state(self) -> dict[str, Any]:
        """Return a default BOCPD bucket state."""
        return {
            "run_length_probs": [1.0],
            "observations": [],
            "current_day": "",
            "current_count": 0,
            "map_run_length": 0,
            "expected_rate": 0.0,
        }

    def score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        window_size: int | None = None,
    ) -> float:
        """Return two-sided tail score from BOCPD posterior predictive mass."""
        if len(train_rows) < 2:
            return 0.0

        training = train_rows[:-1]
        if window_size is not None and window_size > 0 and len(training) > window_size:
            training = training[-window_size:]

        state = self.initial_state()
        for row in training:
            self.update_state(state, self._coerce_count(row))
        current_row = train_rows[-1]
        current_count = self._coerce_count(current_row)
        score = self._score_tail_probability(state, current_count)
        score *= self._context_score_multiplier(
            state=state,
            current_row=current_row,
            current_count=current_count,
        )
        _LOGGER.debug(
            "Scored '%s' with BOCPD: %.3f (current=%d, n=%d)",
            automation_id,
            score,
            current_count,
            len(training),
        )
        return score

    def update_state(self, state: dict[str, Any], observed_count: int) -> None:
        """Apply one BOCPD update step for a finalized bucket count."""
        self._ensure_state(state)
        count = max(0, int(observed_count))
        effective_hazard = self._effective_hazard(state, count)
        observations = cast(list[int], state["observations"])
        previous_probs = cast(list[float], state["run_length_probs"])

        next_probs = [0.0] * (self.max_run_length + 1)
        for run_length, mass in enumerate(previous_probs):
            if mass <= 0.0:
                continue
            alpha, beta = self._posterior_params(observations, run_length)
            p = beta / (beta + 1.0)
            predictive = self._nb_pmf(count, alpha, p)
            weighted = mass * predictive
            changepoint_mass = weighted * effective_hazard
            growth_mass = weighted * (1.0 - effective_hazard)
            next_probs[0] += changepoint_mass
            growth_index = min(run_length + 1, self.max_run_length)
            next_probs[growth_index] += growth_mass

        normalized = self._normalize_probs(next_probs)
        observations.append(count)
        if len(observations) > self.max_run_length:
            del observations[: -self.max_run_length]

        state["run_length_probs"] = normalized
        state["map_run_length"] = self.map_run_length(state)
        state["expected_rate"] = self.expected_rate(state)

    def normalize_state(self, state: dict[str, Any]) -> None:
        """Normalize a BOCPD state payload in-place."""
        self._ensure_state(state)

    def predictive_pmf_for_count(self, state: dict[str, Any], count: int) -> float:
        """Return BOCPD posterior predictive PMF for an integer count."""
        self._ensure_state(state)
        candidate = max(0, int(count))
        observations = cast(list[int], state["observations"])
        probs = cast(list[float], state["run_length_probs"])

        total = 0.0
        for run_length, mass in enumerate(probs):
            if mass <= 0.0:
                continue
            alpha, beta = self._posterior_params(observations, run_length)
            p = beta / (beta + 1.0)
            total += mass * self._nb_pmf(candidate, alpha, p)
        return max(0.0, float(total))

    def map_run_length(self, state: dict[str, Any]) -> int:
        """Return MAP run length from a BOCPD state."""
        self._ensure_state(state)
        probs = cast(list[float], state["run_length_probs"])
        return self._map_run_length_from_probs(probs)

    def expected_rate(self, state: dict[str, Any]) -> float:
        """Return posterior expected count rate from run-length mixture."""
        self._ensure_state(state)
        observations = cast(list[int], state["observations"])
        if not observations:
            return 0.0
        probs = cast(list[float], state["run_length_probs"])
        return self._expected_rate_from(observations, probs)

    def expected_gap_minutes(self, state: dict[str, Any]) -> float:
        """Return expected gap in minutes implied by expected rate."""
        rate = self.expected_rate(state)
        return (1.0 / rate) if rate > 0.0 else 0.0

    def _coerce_count(self, row: dict[str, float]) -> int:
        value = row.get(self._count_feature, 0.0)
        try:
            return max(0, round(float(value)))
        except (TypeError, ValueError):
            return 0

    def _score_tail_probability(
        self, state: dict[str, Any], current_count: int
    ) -> float:
        pmf_floor = 1e-300
        max_score = 80.0
        pmf_current = self.predictive_pmf_for_count(state, current_count)
        surprise_score = min(max_score, -math.log10(max(pmf_current, pmf_floor)))
        if pmf_current <= 0.0:
            return surprise_score

        upper_limit = max(
            current_count + 64,
            round(self.expected_rate(state) * 8.0) + 32,
            64,
        )
        cumulative = 0.0
        cdf = 0.0
        for count in range(upper_limit + 1):
            mass = self.predictive_pmf_for_count(state, count)
            cumulative += mass
            if count <= current_count:
                cdf += mass
            if cumulative >= 0.999999 and count >= current_count:
                break

        cdf = min(1.0, max(0.0, cdf))
        upper_tail = min(1.0, max(0.0, 1.0 - (cdf - pmf_current)))
        two_sided_p = min(1.0, 2.0 * min(cdf, upper_tail))
        tail_score = min(max_score, -math.log10(max(two_sided_p, pmf_floor)))
        if surprise_score > tail_score:
            tail_score += 0.35 * (surprise_score - tail_score)
        return max(0.0, min(max_score, float(tail_score)))

    def _effective_hazard(self, state: dict[str, Any], observed_count: int) -> float:
        """Increase changepoint prior on highly surprising observations."""
        predictive = self.predictive_pmf_for_count(state, observed_count)
        surprise = -math.log10(max(predictive, 1e-12))
        if surprise <= 1.0:
            return self.hazard_rate
        boost = min(12.0, (surprise - 1.0) / 2.0)
        return min(0.60, max(self.hazard_rate, self.hazard_rate * (1.0 + boost)))

    def _context_score_multiplier(
        self,
        *,
        state: dict[str, Any],
        current_row: dict[str, float],
        current_count: int,
    ) -> float:
        """Apply bounded runtime-context adjustments to BOCPD anomaly score."""
        expected = max(0.0, self.expected_rate(state))
        if expected <= 0.0:
            return 1.0

        deviation = float(current_count) - expected
        gap_vs_median = max(
            0.0, self._coerce_numeric(current_row.get("gap_vs_median"), 1.0)
        )
        hour_ratio = max(
            0.0, self._coerce_numeric(current_row.get("hour_ratio_30d"), 1.0)
        )
        other_automations = max(
            0.0,
            self._coerce_numeric(current_row.get("other_automations_5m"), 0.0),
        )

        multiplier = 1.0
        if deviation < 0.0:
            gap_boost = min(0.40, 0.18 * math.log1p(max(0.0, gap_vs_median - 1.0)))
            multiplier *= 1.0 + gap_boost
        elif deviation > 0.0:
            hour_boost = min(0.35, 0.20 * math.log1p(max(0.0, hour_ratio - 1.0)))
            multiplier *= 1.0 + hour_boost
            dampening = min(0.45, 0.14 * math.log1p(other_automations))
            multiplier *= max(0.55, 1.0 - dampening)

        return max(0.55, min(1.75, multiplier))

    def _posterior_params(
        self,
        observations: list[int],
        run_length: int,
    ) -> tuple[float, float]:
        if run_length <= 0 or not observations:
            return self._prior_alpha, self._prior_beta
        sample_size = min(run_length, len(observations))
        segment = observations[-sample_size:]
        return (
            self._prior_alpha + float(sum(segment)),
            self._prior_beta + float(sample_size),
        )

    def _ensure_state(self, state: dict[str, Any]) -> None:
        run_length_probs_raw = state.get("run_length_probs")
        if isinstance(run_length_probs_raw, list):
            run_length_probs = [
                max(0.0, float(value))
                for value in cast(list[Any], run_length_probs_raw)[
                    : self.max_run_length + 1
                ]
            ]
        else:
            run_length_probs = [1.0]
        if not run_length_probs:
            run_length_probs = [1.0]
        state["run_length_probs"] = self._normalize_probs(run_length_probs)

        observations_raw = state.get("observations")
        if isinstance(observations_raw, list):
            observations = [
                max(0, round(float(value)))
                for value in cast(list[Any], observations_raw)[-self.max_run_length :]
            ]
        else:
            observations = []
        state["observations"] = observations
        state.setdefault("current_day", "")
        state["current_count"] = max(
            0, int(self._coerce_numeric(state.get("current_count"), 0.0))
        )
        run_length_probs_state = state["run_length_probs"]
        state["map_run_length"] = self._map_run_length_from_probs(
            run_length_probs_state
        )
        state["expected_rate"] = self._expected_rate_from(
            observations,
            run_length_probs_state,
        )

    def _normalize_probs(self, values: list[float]) -> list[float]:
        total = float(sum(values))
        if not math.isfinite(total) or total <= 0.0:
            return [1.0]
        normalized = [max(0.0, value) / total for value in values]
        while len(normalized) > 1 and normalized[-1] <= 1e-15:
            normalized.pop()
        return normalized

    @staticmethod
    def _coerce_numeric(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _map_run_length_from_probs(probs: list[float]) -> int:
        if not probs:
            return 0
        return int(max(range(len(probs)), key=probs.__getitem__))

    def _expected_rate_from(
        self,
        observations: list[int],
        probs: list[float],
    ) -> float:
        if not observations or not probs:
            return 0.0
        expected = 0.0
        for run_length, mass in enumerate(probs):
            if mass <= 0.0:
                continue
            alpha, beta = self._posterior_params(observations, run_length)
            expected += mass * (alpha / beta)
        return max(0.0, float(expected))

    @staticmethod
    def _nb_pmf(count: int, r: float, p: float) -> float:
        if count < 0:
            return 0.0
        if p <= 0.0 or p >= 1.0:
            return 0.0
        log_prob = (
            math.lgamma(count + r)
            - math.lgamma(count + 1)
            - math.lgamma(r)
            + (r * math.log(p))
            + (count * math.log(1.0 - p))
        )
        return math.exp(log_prob)


class RuntimeHealthMonitor:
    """Detect runtime automation anomalies from recorder trigger history."""

    def __init__(
        self,
        hass: Any,
        *,
        baseline_days: int = 30,
        hour_ratio_days: int = 30,
        warmup_samples: int = 14,
        anomaly_threshold: float = 1.3,
        min_expected_events: int = 1,
        overactive_factor: float = 3.0,
        stalled_threshold: float | None = None,
        overactive_threshold: float | None = None,
        score_ema_samples: int = 5,
        dismissed_threshold_multiplier: float = 1.25,
        cold_start_days: int = 7,
        startup_recovery_minutes: int = 0,
        telemetry_db_path: str | None = None,
        detector: _Detector | None = None,
        runtime_state_store: RuntimeHealthStateStore | None = None,
        sensitivity: str = "medium",
        burst_multiplier: float = 4.0,
        max_alerts_per_day: int = 10,
        global_alert_cap_per_day: int | None = None,
        smoothing_window: int = 5,
        auto_adapt: bool = True,
        hazard_rate: float = DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
        max_run_length: int = DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
        gap_threshold_multiplier: float = DEFAULT_RUNTIME_HEALTH_GAP_THRESHOLD_MULTIPLIER,
        now_factory: Any = None,
    ) -> None:
        self.hass = hass
        self.baseline_days = baseline_days
        self.hour_ratio_days = max(1, hour_ratio_days)
        self.warmup_samples = warmup_samples
        self.anomaly_threshold = anomaly_threshold
        self.stalled_threshold = (
            stalled_threshold if stalled_threshold is not None else anomaly_threshold
        )
        self.overactive_threshold = (
            overactive_threshold
            if overactive_threshold is not None
            else anomaly_threshold
        )
        self.min_expected_events = min_expected_events
        self.overactive_factor = overactive_factor
        self.score_ema_samples = max(2, score_ema_samples)
        self._score_ema_alpha = 2.0 / (self.score_ema_samples + 1.0)
        self.dismissed_threshold_multiplier = max(1.0, dismissed_threshold_multiplier)
        self.cold_start_days = max(0, cold_start_days)
        self.startup_recovery_minutes = max(0, startup_recovery_minutes)
        self.sensitivity = sensitivity
        self.burst_multiplier = max(1.0, float(burst_multiplier))
        self.max_alerts_per_day = max(1, int(max_alerts_per_day))
        self.global_alert_cap_per_day = (
            max(1, int(global_alert_cap_per_day))
            if global_alert_cap_per_day is not None
            else max(10, self.max_alerts_per_day * 10)
        )
        self.smoothing_window = max(1, int(smoothing_window))
        self.auto_adapt = bool(auto_adapt)
        self.hazard_rate = min(1.0, max(1e-6, float(hazard_rate)))
        self.max_run_length = max(2, int(max_run_length))
        self.gap_threshold_multiplier = max(1.0, float(gap_threshold_multiplier))
        self._bocpd_count_detector = _BOCPDDetector(
            hazard_rate=self.hazard_rate,
            max_run_length=self.max_run_length,
        )
        self._detector: _Detector = detector or self._bocpd_count_detector
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._started_at = self._now_factory()
        self._score_history: dict[str, list[float]] = {}
        self._telemetry_table_ensured = False
        self._telemetry_lock = threading.Lock()
        default_db_path = None
        if telemetry_db_path:
            default_db_path = telemetry_db_path
        elif hasattr(hass, "config") and hasattr(hass.config, "path"):
            default_db_path = hass.config.path("autodoctor_runtime_health.sqlite")
        self._telemetry_db_path = default_db_path
        self._last_run_stats: dict[str, int] = {}
        self._last_query_failed = False
        self._live_trigger_events: dict[str, list[datetime]] = defaultdict(list)
        self._runtime_state_store = runtime_state_store or RuntimeHealthStateStore(hass)
        self._runtime_state = {
            "schema_version": 2,
            "automations": {},
            "alerts": {"date": "", "global_count": 0},
            "updated_at": "",
        }
        self._active_runtime_alerts: dict[str, ValidationIssue] = {}
        self._last_runtime_state_flush = self._now_factory()
        self._runtime_state_flush_interval = timedelta(
            minutes=_DEFAULT_RUNTIME_FLUSH_INTERVAL_MINUTES
        )
        _LOGGER.debug(
            "RuntimeHealthMonitor initialized: baseline_days=%d, warmup_samples=%d, "
            "anomaly_threshold=%.1f, min_expected_events=%d, overactive_factor=%.1f, "
            "hour_ratio_days=%d, detector=%s",
            baseline_days,
            warmup_samples,
            anomaly_threshold,
            min_expected_events,
            overactive_factor,
            self.hour_ratio_days,
            type(self._detector).__name__,
        )

    def get_last_run_stats(self) -> dict[str, int]:
        """Return telemetry from the most recent run."""
        return dict(self._last_run_stats)

    def get_runtime_state(self) -> dict[str, Any]:
        """Return a snapshot of persisted runtime model state."""
        return deepcopy(self._runtime_state)

    def get_active_runtime_alerts(self) -> list[ValidationIssue]:
        """Return currently tracked runtime alerts."""
        return list(self._active_runtime_alerts.values())

    async def async_load_state(self) -> None:
        """Load persisted runtime state asynchronously."""
        self._runtime_state = await self._runtime_state_store.async_load()

    async def async_flush_runtime_state(self) -> None:
        """Force a runtime state persistence flush asynchronously."""
        await self._runtime_state_store.async_save(self._runtime_state)

    def flush_runtime_state(self) -> None:
        """Force a runtime state persistence flush."""
        self._persist_runtime_state()

    async def async_backfill_from_recorder(
        self,
        automations: list[dict[str, Any]],
        *,
        now: datetime | None = None,
    ) -> int:
        """Seed runtime state from recorder history when persisted state is empty."""
        existing_automations = self._runtime_state.get("automations", {})
        if isinstance(existing_automations, dict) and existing_automations:
            return 0

        automation_ids: list[str] = []
        seen_ids: set[str] = set()
        for automation in automations:
            automation_entity_id = self._resolve_automation_entity_id(automation)
            if not automation_entity_id or automation_entity_id in seen_ids:
                continue
            automation_ids.append(automation_entity_id)
            seen_ids.add(automation_entity_id)
        if not automation_ids:
            return 0

        backfill_end = now or self._now_factory()
        lookback_days = max(
            _BACKFILL_MIN_LOOKBACK_DAYS,
            self.baseline_days,
            self.hour_ratio_days,
            self.cold_start_days,
        )
        backfill_start = backfill_end - timedelta(days=lookback_days)
        history = await self._async_fetch_trigger_history(
            automation_ids,
            backfill_start,
            backfill_end,
        )

        seeded_automations = 0
        for automation_id in automation_ids:
            events = sorted(history.get(automation_id, []))
            if not events:
                continue
            automation_state = self._ensure_automation_state(automation_id)
            for event_time in events:
                self._update_count_model(automation_state, event_time)
                self._update_gap_model(automation_state, event_time)
                self._detect_burst_anomaly(
                    automation_entity_id=automation_id,
                    automation_state=automation_state,
                    now=event_time,
                    allow_alerts=False,
                )
            seeded_automations += 1

        if seeded_automations:
            self._persist_runtime_state()
        return seeded_automations

    @staticmethod
    def classify_time_bucket(timestamp: datetime) -> str:
        """Map timestamp into weekday/weekend x daypart bucket."""
        day_type = "weekend" if timestamp.weekday() >= 5 else "weekday"
        hour = timestamp.hour
        if _BUCKET_MORNING_START_HOUR <= hour < _BUCKET_AFTERNOON_START_HOUR:
            daypart = "morning"
        elif _BUCKET_AFTERNOON_START_HOUR <= hour < _BUCKET_EVENING_START_HOUR:
            daypart = "afternoon"
        elif _BUCKET_EVENING_START_HOUR <= hour < _BUCKET_NIGHT_START_HOUR:
            daypart = "evening"
        else:
            daypart = "night"
        return f"{day_type}_{daypart}"

    def ingest_trigger_event(
        self,
        automation_entity_id: str,
        *,
        occurred_at: datetime | None = None,
        suppression_store: Any = None,
    ) -> list[ValidationIssue]:
        """Ingest a live automation_triggered event for runtime model updates."""
        if not automation_entity_id or not automation_entity_id.startswith(
            "automation."
        ):
            return []
        if self._is_runtime_suppressed(automation_entity_id, suppression_store):
            return []
        event_time = occurred_at or self._now_factory()
        self._live_trigger_events[automation_entity_id].append(event_time)
        automation_state = self._ensure_automation_state(automation_entity_id)

        count_bucket_name, count_bucket = self._update_count_model(
            automation_state, event_time
        )
        self._update_gap_model(automation_state, event_time)
        self._clear_runtime_alert(
            automation_entity_id,
            IssueType.RUNTIME_AUTOMATION_GAP,
        )
        issues = self._detect_burst_anomaly(
            automation_entity_id=automation_entity_id,
            automation_state=automation_state,
            now=event_time,
        )
        issues.extend(
            self._detect_count_anomaly(
                automation_entity_id=automation_entity_id,
                automation_state=automation_state,
                bucket_name=count_bucket_name,
                bucket_state=count_bucket,
                now=event_time,
            )
        )
        self._maybe_auto_adapt(
            automation_entity_id=automation_entity_id,
            automation_state=automation_state,
            bucket_name=count_bucket_name,
        )
        self._maybe_flush_runtime_state(event_time)
        return issues

    def check_gap_anomalies(
        self, *, now: datetime | None = None
    ) -> list[ValidationIssue]:
        """Evaluate BOCPD-derived gap thresholds and emit gap anomaly issues."""
        check_time = now or self._now_factory()
        issues: list[ValidationIssue] = []
        state_dirty = False
        gap_issue_type = IssueType.RUNTIME_AUTOMATION_GAP
        suppression_store = self._runtime_suppression_store()
        automations = self._runtime_state.get("automations", {})
        if not isinstance(automations, dict):
            return []
        automations_dict = cast(dict[str, Any], automations)

        for automation_id, automation_state_raw in automations_dict.items():
            if not isinstance(automation_state_raw, dict):
                continue
            automation_state = cast(dict[str, Any], automation_state_raw)
            state_dirty = (
                self._roll_count_model_forward(automation_state, now=check_time)
                or state_dirty
            )
            gap_model_raw = automation_state.get("gap_model", {})
            if not isinstance(gap_model_raw, dict):
                continue
            gap_model = cast(dict[str, Any], gap_model_raw)

            last_trigger = self._coerce_datetime(gap_model.get("last_trigger"))
            if last_trigger is None:
                self._clear_runtime_alert(automation_id, gap_issue_type)
                continue

            expected_gap = self._expected_gap_minutes_for_automation(
                automation_state, last_trigger
            )
            if expected_gap <= 0.0:
                self._clear_runtime_alert(automation_id, gap_issue_type)
                continue

            threshold = expected_gap * self.gap_threshold_multiplier
            elapsed_minutes = max(
                0.0, (check_time - last_trigger).total_seconds() / 60.0
            )
            if elapsed_minutes <= threshold:
                self._clear_runtime_alert(automation_id, gap_issue_type)
                continue

            if self._is_runtime_suppressed(automation_id, suppression_store):
                self._clear_runtime_alert(automation_id, gap_issue_type)
                continue

            if not self._allow_alert(automation_id, now=check_time):
                continue

            issue = ValidationIssue(
                severity=Severity.ERROR,
                automation_id=automation_id,
                automation_name=automation_id,
                entity_id=automation_id,
                location="runtime.health.gap",
                message=(
                    f"Runtime gap anomaly: observed gap {elapsed_minutes:.1f}m exceeds "
                    f"expected gap {expected_gap:.1f}m (threshold {threshold:.1f}m)"
                ),
                issue_type=IssueType.RUNTIME_AUTOMATION_GAP,
                confidence="medium",
            )
            self._register_runtime_alert(issue)
            issues.append(issue)

        if issues or state_dirty:
            self._persist_runtime_state()
        else:
            self._maybe_flush_runtime_state(check_time)
        return issues

    def run_weekly_maintenance(self, *, now: datetime | None = None) -> None:
        """Record maintenance tick; BOCPD path has no periodic bucket promotion."""
        maintenance_time = now or self._now_factory()
        self._runtime_state["last_weekly_maintenance"] = maintenance_time.isoformat()
        self._persist_runtime_state()

    @staticmethod
    def _empty_automation_state() -> dict[str, Any]:
        """Return default in-memory state for an automation runtime model."""
        return {
            "count_model": {
                "buckets": {},
                "anomaly_streak": 0,
            },
            "gap_model": {
                "last_trigger": None,
                "expected_gap_minutes": 0.0,
                "ewma_gap_minutes": 0.0,
                "median_gap_minutes": 0.0,
                "recent_gaps_minutes": [],
            },
            "burst_model": {
                "recent_triggers": [],
                "baseline_rate_5m": 0.0,
            },
            "rate_limit": {
                "date": "",
                "count": 0,
                "last_alert": None,
            },
            "adaptation": {
                "threshold_multiplier": 1.0,
                "dismissed_count": 0,
            },
            "periodic_model": {
                "run_length_probs": [1.0],
                "observations": [],
                "map_run_length": 0,
                "expected_rate": 0.0,
                "updated_at": "",
                "window_size": 0,
            },
        }

    def _ensure_automation_state(self, automation_entity_id: str) -> dict[str, Any]:
        automations = self._runtime_state.setdefault("automations", {})
        if not isinstance(automations, dict):
            automations = {}
            self._runtime_state["automations"] = automations
        automations_dict = cast(dict[str, Any], automations)
        state_raw = automations_dict.get(automation_entity_id)
        if not isinstance(state_raw, dict):
            state: dict[str, Any] = self._empty_automation_state()
            automations_dict[automation_entity_id] = state
            return state
        state = cast(dict[str, Any], state_raw)

        defaults = self._empty_automation_state()
        for key, default_value in defaults.items():
            if key not in state or (
                isinstance(default_value, dict) and not isinstance(state[key], dict)
            ):
                state[key] = deepcopy(default_value)
        return state

    def _ensure_count_bucket_state(
        self,
        count_model: dict[str, Any],
        bucket_name: str,
    ) -> dict[str, Any]:
        buckets = count_model.setdefault("buckets", {})
        if not isinstance(buckets, dict):
            buckets = {}
            count_model["buckets"] = buckets
        buckets_dict = cast(dict[str, Any], buckets)
        bucket_state_raw = buckets_dict.get(bucket_name)
        if isinstance(bucket_state_raw, dict):
            bucket_state = cast(dict[str, Any], bucket_state_raw)
        else:
            bucket_state = {}
            buckets_dict[bucket_name] = bucket_state

        # Migrate any legacy shape into BOCPD-compatible fields on read.
        if not (
            isinstance(bucket_state.get("run_length_probs"), list)
            and isinstance(bucket_state.get("observations"), list)
        ):
            seeded = self._bocpd_count_detector.initial_state()
            legacy_counts_raw = bucket_state.get("counts")
            if isinstance(legacy_counts_raw, list):
                for value in cast(list[Any], legacy_counts_raw):
                    try:
                        self._bocpd_count_detector.update_state(seeded, int(value))
                    except (TypeError, ValueError):
                        continue
            seeded["current_day"] = str(bucket_state.get("current_day", ""))
            seeded["current_count"] = max(
                0, int(self._coerce_float(bucket_state.get("current_count"), 0.0))
            )
            bucket_state.clear()
            bucket_state.update(seeded)

        self._bocpd_count_detector.normalize_state(bucket_state)
        buckets_dict[bucket_name] = bucket_state
        return bucket_state

    def _update_count_model(
        self,
        automation_state: dict[str, Any],
        event_time: datetime,
    ) -> tuple[str, dict[str, Any]]:
        count_model = automation_state.setdefault("count_model", {})
        if not isinstance(count_model, dict):
            count_model = {}
            automation_state["count_model"] = count_model
        bucket_name = self.classify_time_bucket(event_time)
        bucket_state = self._ensure_count_bucket_state(count_model, bucket_name)
        self._advance_count_bucket_to_day(
            bucket_name=bucket_name,
            bucket_state=bucket_state,
            target_day=event_time.date(),
        )

        bucket_state["current_day"] = event_time.date().isoformat()
        bucket_state["current_count"] = max(
            0, int(self._coerce_float(bucket_state.get("current_count"), 0.0))
        )
        bucket_state["current_count"] = int(bucket_state.get("current_count", 0)) + 1
        return bucket_name, bucket_state

    def _advance_count_bucket_to_day(
        self,
        *,
        bucket_name: str,
        bucket_state: dict[str, Any],
        target_day: date,
    ) -> bool:
        current_day = self._coerce_date(bucket_state.get("current_day"))
        if current_day is None:
            bucket_state["current_day"] = target_day.isoformat()
            bucket_state["current_count"] = max(
                0, int(self._coerce_float(bucket_state.get("current_count"), 0.0))
            )
            return True
        if current_day >= target_day:
            return False

        current_count = max(
            0, int(self._coerce_float(bucket_state.get("current_count"), 0.0))
        )
        cursor = current_day
        consumed_current_count = False
        while cursor < target_day:
            if self._bucket_matches_day_type(bucket_name, cursor):
                finalized = current_count if not consumed_current_count else 0
                self._bocpd_count_detector.update_state(bucket_state, finalized)
                consumed_current_count = True
            cursor += timedelta(days=1)

        if not consumed_current_count and current_count > 0:
            self._bocpd_count_detector.update_state(bucket_state, current_count)

        bucket_state["current_day"] = target_day.isoformat()
        bucket_state["current_count"] = 0
        return True

    def _roll_count_model_forward(
        self,
        automation_state: dict[str, Any],
        *,
        now: datetime,
    ) -> bool:
        count_model_raw = automation_state.get("count_model", {})
        if not isinstance(count_model_raw, dict):
            return False
        count_model = cast(dict[str, Any], count_model_raw)
        buckets_raw = count_model.get("buckets", {})
        if not isinstance(buckets_raw, dict):
            return False

        state_dirty = False
        bucket_names = list(cast(dict[str, Any], buckets_raw).keys())
        target_day = now.date()
        for bucket_name in bucket_names:
            bucket_state = self._ensure_count_bucket_state(count_model, bucket_name)
            state_dirty = (
                self._advance_count_bucket_to_day(
                    bucket_name=bucket_name,
                    bucket_state=bucket_state,
                    target_day=target_day,
                )
                or state_dirty
            )
        return state_dirty

    def _update_gap_model(
        self,
        automation_state: dict[str, Any],
        event_time: datetime,
    ) -> None:
        gap_model_raw = automation_state.setdefault("gap_model", {})
        if not isinstance(gap_model_raw, dict):
            gap_model_raw = {}
            automation_state["gap_model"] = gap_model_raw
        gap_model = cast(dict[str, Any], gap_model_raw)
        previous_trigger = self._coerce_datetime(gap_model.get("last_trigger"))
        if previous_trigger is not None and event_time > previous_trigger:
            gap_minutes = max(
                0.0,
                (event_time - previous_trigger).total_seconds() / 60.0,
            )
            if gap_minutes > 0.0:
                recent_raw = gap_model.get("recent_gaps_minutes")
                recent_values = (
                    cast(list[Any], recent_raw) if isinstance(recent_raw, list) else []
                )
                recent = [
                    self._coerce_float(value, 0.0)
                    for value in recent_values
                    if self._coerce_float(value, 0.0) > 0.0
                ]
                recent.append(gap_minutes)
                if len(recent) > _GAP_MODEL_MAX_RECENT_INTERVALS:
                    del recent[:-_GAP_MODEL_MAX_RECENT_INTERVALS]

                median_gap = float(median(recent))
                previous_ewma = self._coerce_float(
                    gap_model.get("ewma_gap_minutes"),
                    gap_minutes,
                )
                ewma_gap = (
                    gap_minutes
                    if previous_ewma <= 0.0
                    else (0.8 * previous_ewma) + (0.2 * gap_minutes)
                )
                expected_gap = max(1.0, (0.5 * median_gap) + (0.5 * ewma_gap))

                gap_model["recent_gaps_minutes"] = recent
                gap_model["median_gap_minutes"] = median_gap
                gap_model["ewma_gap_minutes"] = ewma_gap
                gap_model["expected_gap_minutes"] = expected_gap
        gap_model["last_trigger"] = event_time.isoformat()

    def _expected_gap_minutes_for_automation(
        self,
        automation_state: dict[str, Any],
        last_trigger: datetime,
    ) -> float:
        gap_model_raw = automation_state.get("gap_model", {})
        if isinstance(gap_model_raw, dict):
            gap_model = cast(dict[str, Any], gap_model_raw)
            expected_gap = self._coerce_float(
                gap_model.get("expected_gap_minutes"), 0.0
            )
            if expected_gap > 0.0:
                return expected_gap

        count_model_raw = automation_state.get("count_model", {})
        if not isinstance(count_model_raw, dict):
            return 0.0
        count_model = cast(dict[str, Any], count_model_raw)
        buckets_raw = count_model.get("buckets", {})
        if not isinstance(buckets_raw, dict):
            return 0.0
        buckets = cast(dict[str, Any], buckets_raw)

        bucket_name = self.classify_time_bucket(last_trigger)
        bucket_state_raw = buckets.get(bucket_name)
        if not isinstance(bucket_state_raw, dict):
            return 0.0
        bucket_state = cast(dict[str, Any], bucket_state_raw)

        expected_count = self._coerce_float(bucket_state.get("expected_rate"), 0.0)
        if expected_count <= 0.0:
            expected_count = max(
                0.0, self._coerce_float(bucket_state.get("current_count"), 0.0)
            )
        if expected_count <= 0.0:
            return 0.0

        bucket_duration_minutes = self._bucket_duration_minutes(bucket_name)
        if bucket_duration_minutes <= 0.0:
            return 0.0
        return bucket_duration_minutes / expected_count

    @staticmethod
    def _bucket_duration_minutes(bucket_name: str) -> float:
        if bucket_name.endswith("_morning"):
            return 7.0 * 60.0
        if bucket_name.endswith("_afternoon"):
            return 5.0 * 60.0
        if bucket_name.endswith("_evening"):
            return 5.0 * 60.0
        return 7.0 * 60.0

    def _detect_count_anomaly(
        self,
        *,
        automation_entity_id: str,
        automation_state: dict[str, Any],
        bucket_name: str,
        bucket_state: dict[str, Any],
        now: datetime,
    ) -> list[ValidationIssue]:
        issue_type = IssueType.RUNTIME_AUTOMATION_COUNT_ANOMALY
        observations = bucket_state.get("observations")
        if not isinstance(observations, list) or len(observations) < 7:
            self._clear_runtime_alert(automation_entity_id, issue_type)
            return []

        lower, upper = self._bocpd_expected_count_range(bucket_state)
        observed = int(bucket_state.get("current_count", 0))
        if lower <= observed <= upper:
            self._clear_runtime_alert(automation_entity_id, issue_type)
            count_model = automation_state.get("count_model", {})
            if isinstance(count_model, dict):
                count_model["anomaly_streak"] = 0
            return []

        if not self._allow_alert(automation_entity_id, now=now):
            return []

        issue = ValidationIssue(
            severity=Severity.WARNING,
            automation_id=automation_entity_id,
            automation_name=automation_entity_id,
            entity_id=automation_entity_id,
            location="runtime.health.count",
            message=(
                f"Runtime count anomaly in {bucket_name}: observed {observed}, expected "
                f"range {lower}-{upper} for current window"
            ),
            issue_type=IssueType.RUNTIME_AUTOMATION_COUNT_ANOMALY,
            confidence="medium",
        )
        self._register_runtime_alert(issue)
        count_model = automation_state.get("count_model", {})
        if isinstance(count_model, dict):
            count_model["anomaly_streak"] = (
                int(count_model.get("anomaly_streak", 0)) + 1
            )
        self._persist_runtime_state()
        return [issue]

    def _bocpd_expected_count_range(
        self, bucket_state: dict[str, Any]
    ) -> tuple[int, int]:
        sensitivity_to_coverage = {
            "low": 0.99,
            "medium": 0.95,
            "high": 0.90,
        }
        coverage = sensitivity_to_coverage.get(self.sensitivity, 0.95)
        tail = (1.0 - coverage) / 2.0
        lower = self._bocpd_quantile(bucket_state, tail)
        upper = self._bocpd_quantile(bucket_state, 1.0 - tail)
        return max(0, lower), max(0, upper)

    def _bocpd_quantile(self, bucket_state: dict[str, Any], quantile: float) -> int:
        q = min(1.0, max(0.0, quantile))
        if q <= 0.0:
            return 0
        if q >= 1.0:
            return 10_000

        cumulative = 0.0
        expected = self._bocpd_count_detector.expected_rate(bucket_state)
        max_count = max(64, round(expected * 10.0) + 32)
        for count in range(max_count + 1):
            cumulative += self._bocpd_count_detector.predictive_pmf_for_count(
                bucket_state, count
            )
            if cumulative >= q:
                return count

        for count in range(max_count + 1, 10_001):
            cumulative += self._bocpd_count_detector.predictive_pmf_for_count(
                bucket_state, count
            )
            if cumulative >= q:
                return count
        return 10_000

    def _detect_burst_anomaly(
        self,
        *,
        automation_entity_id: str,
        automation_state: dict[str, Any],
        now: datetime,
        allow_alerts: bool = True,
    ) -> list[ValidationIssue]:
        issue_type = IssueType.RUNTIME_AUTOMATION_BURST
        burst_model = automation_state.setdefault("burst_model", {})
        if not isinstance(burst_model, dict):
            burst_model = {}
            automation_state["burst_model"] = burst_model
        recent_raw = cast(Any, burst_model.get("recent_triggers"))
        recent_values = (
            cast(list[Any], recent_raw) if isinstance(recent_raw, list) else []
        )
        recent_triggers = [self._coerce_datetime(value) for value in recent_values]
        recent = [
            ts
            for ts in recent_triggers
            if ts is not None and ts >= (now - timedelta(hours=1))
        ]
        recent.append(now)
        recent.sort()

        current_5m_count = sum(1 for ts in recent if ts >= (now - timedelta(minutes=5)))
        baseline_segment_count = sum(
            1
            for ts in recent
            if (now - timedelta(hours=1)) <= ts < (now - timedelta(minutes=5))
        )
        baseline_from_history = (
            baseline_segment_count / 11.0 if baseline_segment_count else 0.0
        )
        previous_baseline = self._coerce_float(burst_model.get("baseline_rate_5m"), 0.0)
        baseline_rate = (
            previous_baseline
            if previous_baseline > 0
            else max(1.0, baseline_from_history if baseline_from_history > 0 else 1.0)
        )
        threshold = max(2.0, baseline_rate * self.burst_multiplier)

        burst_model["recent_triggers"] = [ts.isoformat() for ts in recent]
        if baseline_from_history > 0:
            burst_model["baseline_rate_5m"] = (0.8 * baseline_rate) + (
                0.2 * baseline_from_history
            )
        else:
            burst_model["baseline_rate_5m"] = baseline_rate

        if not allow_alerts:
            return []
        if len(recent) < 6 or float(current_5m_count) < threshold:
            self._clear_runtime_alert(automation_entity_id, issue_type)
            return []
        if not self._allow_alert(automation_entity_id, now=now):
            return []

        issue = ValidationIssue(
            severity=Severity.ERROR,
            automation_id=automation_entity_id,
            automation_name=automation_entity_id,
            entity_id=automation_entity_id,
            location="runtime.health.burst",
            message=(
                f"Runtime burst detected in 5m window: observed {current_5m_count} "
                f"triggers vs baseline {baseline_rate:.2f}/5m"
            ),
            issue_type=issue_type,
            confidence="medium",
        )
        self._register_runtime_alert(issue)
        self._persist_runtime_state()
        return [issue]

    def _register_runtime_alert(self, issue: ValidationIssue) -> None:
        self._active_runtime_alerts[issue.get_suppression_key()] = issue

    def _clear_runtime_alert(self, automation_id: str, issue_type: IssueType) -> None:
        key = f"{automation_id}:{automation_id}:{issue_type.value}"
        self._active_runtime_alerts.pop(key, None)

    def _allow_alert(self, automation_id: str, *, now: datetime) -> bool:
        alerts = self._runtime_state.setdefault("alerts", {})
        if not isinstance(alerts, dict):
            alerts = {}
            self._runtime_state["alerts"] = alerts
        day = now.date().isoformat()
        if alerts.get("date") != day:
            alerts["date"] = day
            alerts["global_count"] = 0

        automation_state = self._ensure_automation_state(automation_id)
        rate_limit = automation_state.setdefault("rate_limit", {})
        if not isinstance(rate_limit, dict):
            rate_limit = {}
            automation_state["rate_limit"] = rate_limit
        if rate_limit.get("date") != day:
            rate_limit["date"] = day
            rate_limit["count"] = 0

        automation_count = int(rate_limit.get("count", 0))
        global_count = int(alerts.get("global_count", 0))
        if automation_count >= self.max_alerts_per_day:
            return False
        if global_count >= self.global_alert_cap_per_day:
            return False

        rate_limit["count"] = automation_count + 1
        rate_limit["last_alert"] = now.isoformat()
        alerts["global_count"] = global_count + 1
        return True

    def _is_runtime_suppressed(
        self,
        automation_id: str,
        suppression_store: Any | None,
    ) -> bool:
        if suppression_store is None or not hasattr(suppression_store, "is_suppressed"):
            return False
        prefixes = (
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_STALLED.value}",
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_OVERACTIVE.value}",
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_COUNT_ANOMALY.value}",
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_GAP.value}",
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_BURST.value}",
        )
        for prefix in prefixes:
            try:
                if bool(suppression_store.is_suppressed(prefix)):
                    return True
            except Exception:
                continue
        return False

    def _runtime_suppression_store(self) -> Any | None:
        """Return suppression store from hass domain data when available."""
        hass_data = getattr(self.hass, "data", {})
        data = cast(dict[str, Any], hass_data) if isinstance(hass_data, dict) else {}
        domain_data_raw = data.get(DOMAIN, {})
        if not isinstance(domain_data_raw, dict):
            return None
        domain_data = cast(dict[str, Any], domain_data_raw)
        return domain_data.get("suppression_store")

    def record_issue_dismissed(self, automation_id: str) -> None:
        """Increase dismissal-aware threshold multiplier for an automation."""
        automation_state = self._ensure_automation_state(automation_id)
        adaptation = automation_state.setdefault("adaptation", {})
        if not isinstance(adaptation, dict):
            adaptation = {}
            automation_state["adaptation"] = adaptation
        adaptation["dismissed_count"] = int(adaptation.get("dismissed_count", 0)) + 1
        current_multiplier = self._coerce_float(
            adaptation.get("threshold_multiplier"),
            1.0,
        )
        adaptation["threshold_multiplier"] = max(
            1.0, current_multiplier * self.dismissed_threshold_multiplier
        )
        self._persist_runtime_state()

    def _maybe_auto_adapt(
        self,
        *,
        automation_entity_id: str,
        automation_state: dict[str, Any],
        bucket_name: str,
    ) -> None:
        if not self.auto_adapt:
            return
        count_model = automation_state.get("count_model", {})
        if not isinstance(count_model, dict):
            return
        count_model_dict = cast(dict[str, Any], count_model)
        streak = int(count_model_dict.get("anomaly_streak", 0))
        if streak < self.smoothing_window:
            return

        buckets = count_model_dict.get("buckets", {})
        if not isinstance(buckets, dict):
            return
        buckets_dict = cast(dict[str, Any], buckets)
        bucket_state = buckets_dict.get(bucket_name)
        if not isinstance(bucket_state, dict):
            return
        preserved_day = str(bucket_state.get("current_day", ""))
        bucket_state.clear()
        bucket_state.update(self._bocpd_count_detector.initial_state())
        bucket_state["current_day"] = preserved_day
        count_model_dict["anomaly_streak"] = 0
        _LOGGER.debug(
            "Auto-adapt reset runtime count baseline for '%s' bucket '%s'",
            automation_entity_id,
            bucket_name,
        )
        self._persist_runtime_state()

    def _persist_runtime_state(self) -> None:
        snapshot = deepcopy(self._runtime_state)
        self.hass.async_create_task(self._runtime_state_store.async_save(snapshot))
        self._last_runtime_state_flush = self._now_factory()

    def _maybe_flush_runtime_state(self, now: datetime) -> None:
        if (now - self._last_runtime_state_flush) < self._runtime_state_flush_interval:
            return
        snapshot = deepcopy(self._runtime_state)
        self.hass.async_create_task(self._runtime_state_store.async_save(snapshot))
        self._last_runtime_state_flush = now

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        return None

    @staticmethod
    def _coerce_date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _bucket_matches_day_type(bucket_name: str, day: date) -> bool:
        if bucket_name.startswith("weekday_"):
            return day.weekday() < 5
        if bucket_name.startswith("weekend_"):
            return day.weekday() >= 5
        return True

    @staticmethod
    def _coerce_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _resolve_automation_entity_id(automation: dict[str, Any]) -> str | None:
        """Resolve canonical automation entity_id for runtime history matching."""
        explicit = automation.get("entity_id") or automation.get("__entity_id")
        if isinstance(explicit, str) and explicit.startswith("automation."):
            return explicit

        raw_id = automation.get("id")
        if isinstance(raw_id, str) and raw_id:
            return (
                raw_id if raw_id.startswith("automation.") else f"automation.{raw_id}"
            )
        return None

    async def validate_automations(
        self, automations: list[dict[str, Any]]
    ) -> list[ValidationIssue]:
        """Validate runtime trigger behavior for automations."""
        _LOGGER.debug(
            "Runtime health validation starting: %d automations", len(automations)
        )
        stats: dict[str, int] = defaultdict(int)
        stats["total_automations"] = len(automations)

        now = self._now_factory()
        recovery_cutoff = self._started_at + timedelta(
            minutes=self.startup_recovery_minutes
        )
        if now < recovery_cutoff:
            stats["startup_recovery"] = len(automations)
            self._last_run_stats = dict(stats)
            _LOGGER.debug("Runtime health in startup recovery window, skipping scoring")
            return []

        recent_start = now - timedelta(hours=24)
        baseline_start = recent_start - timedelta(days=self.baseline_days)
        automation_ids: list[str] = []
        seen_ids: set[str] = set()
        for automation in automations:
            automation_entity_id = self._resolve_automation_entity_id(automation)
            if not automation_entity_id or automation_entity_id in seen_ids:
                continue
            automation_ids.append(automation_entity_id)
            seen_ids.add(automation_entity_id)
        _LOGGER.debug("Extracted %d valid automation IDs", len(automation_ids))
        if not automation_ids:
            _LOGGER.debug("No valid automation IDs to validate")
            self._last_run_stats = dict(stats)
            return []

        baseline_start_by_automation: dict[str, datetime] = dict.fromkeys(
            automation_ids, baseline_start
        )
        looked_back_automation_ids: set[str] = set()
        history = await self._async_fetch_trigger_history(
            automation_ids,
            baseline_start,
            now,
        )
        if self._last_query_failed:
            stats["recorder_query_failed"] = 1
        if self.warmup_samples > 0 and self.baseline_days < _SPARSE_WARMUP_LOOKBACK_DAYS:
            sparse_automation_ids: list[str] = []
            for automation_id in automation_ids:
                baseline_events = [
                    ts
                    for ts in history.get(automation_id, [])
                    if baseline_start <= ts < recent_start
                ]
                day_counts = self._build_daily_counts(
                    baseline_events,
                    baseline_start,
                    recent_start,
                )
                active_days = sum(1 for count in day_counts if count > 0)
                if active_days < self.warmup_samples:
                    sparse_automation_ids.append(automation_id)

            if sparse_automation_ids:
                extended_baseline_start = recent_start - timedelta(
                    days=_SPARSE_WARMUP_LOOKBACK_DAYS
                )
                extended_history = await self._async_fetch_trigger_history(
                    sparse_automation_ids,
                    extended_baseline_start,
                    now,
                )
                if self._last_query_failed:
                    stats["recorder_query_failed"] = 1
                for automation_id in sparse_automation_ids:
                    merged_events = sorted(
                        set(history.get(automation_id, []))
                        | set(extended_history.get(automation_id, []))
                    )
                    history[automation_id] = merged_events
                    baseline_start_by_automation[automation_id] = extended_baseline_start
                looked_back_automation_ids.update(sparse_automation_ids)
                stats["extended_lookback_used"] += len(sparse_automation_ids)
                _LOGGER.debug(
                    "Runtime health extended lookback applied to %d sparse automations",
                    len(sparse_automation_ids),
                )

        issues: list[ValidationIssue] = []
        runtime_state_dirty = False
        all_events_by_automation = history
        domain_data: dict[str, Any] = (
            self.hass.data.get(DOMAIN, {}) if hasattr(self.hass, "data") else {}
        )
        suppression_store: Any = domain_data.get("suppression_store")
        bucket_index = self._build_5m_bucket_index(all_events_by_automation)
        for automation in automations:
            automation_entity_id = self._resolve_automation_entity_id(automation)
            if not automation_entity_id:
                stats["missing_identity"] += 1
                continue

            automation_name = str(automation.get("alias", automation_entity_id))
            automation_baseline_start = baseline_start_by_automation.get(
                automation_entity_id,
                baseline_start,
            )
            timestamps = sorted(history.get(automation_entity_id, []))

            baseline_events = [
                t for t in timestamps if automation_baseline_start <= t < recent_start
            ]
            recent_events = [t for t in timestamps if recent_start <= t <= now]
            day_counts = self._build_daily_counts(
                baseline_events,
                automation_baseline_start,
                recent_start,
            )
            expected = fmean(day_counts) if day_counts else 0.0
            active_days = sum(1 for c in day_counts if c > 0)
            required_warmup = self._effective_warmup_samples(
                expected_daily=expected,
                baseline_days=len(day_counts),
                baseline_event_count=len(baseline_events),
                oldest_event_age_days=(
                    (now - timestamps[0]).total_seconds() / 86400 if timestamps else None
                ),
            )
            _LOGGER.debug(
                "Automation '%s': %d baseline events, %d recent events, %d active days",
                automation_name,
                len(baseline_events),
                len(recent_events),
                active_days,
            )

            if active_days < required_warmup:
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient warmup: "
                    "%d active days < %d required)",
                    automation_name,
                    active_days,
                    required_warmup,
                )
                stats["insufficient_warmup"] += 1
                continue

            if timestamps and (now - timestamps[0]) < timedelta(
                days=self.cold_start_days
            ):
                _LOGGER.debug(
                    "Automation '%s': skipped (cold start: %.1f days < %d required)",
                    automation_name,
                    (now - timestamps[0]).total_seconds() / 86400,
                    self.cold_start_days,
                )
                stats["cold_start"] += 1
                continue

            if expected < float(self.min_expected_events):
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient baseline: "
                    "%.1f events/day < %d required)",
                    automation_name,
                    expected,
                    self.min_expected_events,
                )
                stats["insufficient_baseline"] += 1
                continue

            median_gap = self._median_gap_minutes(baseline_events)
            train_rows = self._build_training_rows_from_events(
                automation_id=automation_entity_id,
                baseline_events=baseline_events,
                baseline_start=automation_baseline_start,
                baseline_end=recent_start,
                expected_daily=expected,
                all_events_by_automation=all_events_by_automation,
                cold_start_days=self.cold_start_days,
                hour_ratio_days=self.hour_ratio_days,
                median_gap_override=median_gap,
                bucket_index=bucket_index,
            )
            current_row = self._build_feature_row(
                automation_id=automation_entity_id,
                now=now,
                automation_events=timestamps,
                baseline_events=baseline_events,
                expected_daily=expected,
                all_events_by_automation=all_events_by_automation,
                hour_ratio_days=self.hour_ratio_days,
                median_gap_override=median_gap,
                bucket_index=bucket_index,
            )
            train_rows.append(current_row)
            if len(train_rows) < 2:
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient training rows: %d)",
                    automation_name,
                    len(train_rows),
                )
                stats["insufficient_training_rows"] += 1
                continue
            window_size = self._compute_window_size(expected)
            runtime_state_dirty = (
                self._persist_periodic_bocpd_state(
                    automation_id=automation_entity_id,
                    train_rows=train_rows,
                    now=now,
                    window_size=window_size,
                )
                or runtime_state_dirty
            )
            if automation_entity_id in looked_back_automation_ids:
                stats["scored_after_lookback"] += 1
            _LOGGER.debug(
                "Automation '%s': scoring with %d training rows, "
                "expected %.1f/day, recent %d events",
                automation_name,
                len(train_rows) - 1,
                expected,
                len(recent_events),
            )
            score = self._score_current(
                automation_entity_id, train_rows, window_size=window_size
            )
            smoothed_score = self._smoothed_score(automation_entity_id, score)
            telemetry_ok = await self.hass.async_add_executor_job(
                partial(
                    self._log_score_telemetry,
                    automation_id=automation_entity_id,
                    score=smoothed_score,
                    now=now,
                    features=current_row,
                )
            )
            if not telemetry_ok:
                stats["telemetry_write_failed"] += 1
            _LOGGER.debug(
                "Automation '%s': anomaly score=%.3f ema=%.3f",
                automation_name,
                score,
                smoothed_score,
            )

            recent_count = len(recent_events)
            threshold_multiplier = self._dismissed_multiplier(
                automation_entity_id, suppression_store=suppression_store
            )
            stalled_threshold = self.stalled_threshold * threshold_multiplier
            overactive_threshold = self.overactive_threshold * threshold_multiplier
            runtime_suppressed = self._is_runtime_suppressed(
                automation_entity_id,
                suppression_store,
            )

            is_weekend = now.weekday() >= 5
            day_type_active = any(
                (t.weekday() >= 5) == is_weekend for t in baseline_events
            )
            alert_baseline_ok = len(baseline_events) >= max(3, required_warmup)

            if (
                recent_count == 0
                and smoothed_score >= stalled_threshold
                and day_type_active
                and alert_baseline_ok
                and not runtime_suppressed
            ):
                if not self._allow_alert(automation_entity_id, now=now):
                    continue
                _LOGGER.info(
                    "Stalled: '%s' - 0 triggers in 24h, baseline %.1f/day, score %.2f",
                    automation_name,
                    expected,
                    smoothed_score,
                )
                stats["stalled_detected"] += 1
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        automation_id=automation_entity_id,
                        automation_name=automation_name,
                        entity_id=automation_entity_id,
                        location="runtime.health",
                        message=(
                            f"Automation appears stalled: 0 triggers in last 24h, "
                            f"baseline expected {expected:.1f}/day "
                            f"(anomaly score {smoothed_score:.2f})"
                        ),
                        issue_type=IssueType.RUNTIME_AUTOMATION_STALLED,
                        confidence="medium",
                    )
                )
                continue

            if (
                recent_count > expected * self.overactive_factor
                and smoothed_score >= overactive_threshold
                and day_type_active
                and alert_baseline_ok
                and not runtime_suppressed
            ):
                if not self._allow_alert(automation_entity_id, now=now):
                    continue
                _LOGGER.info(
                    "Overactive: '%s' - %d triggers in 24h, baseline %.1f/day, score %.2f",
                    automation_name,
                    recent_count,
                    expected,
                    smoothed_score,
                )
                stats["overactive_detected"] += 1
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        automation_id=automation_entity_id,
                        automation_name=automation_name,
                        entity_id=automation_entity_id,
                        location="runtime.health",
                        message=(
                            f"Automation trigger rate is abnormally high: {recent_count} "
                            f"triggers in last 24h vs baseline {expected:.1f}/day "
                            f"(anomaly score {smoothed_score:.2f})"
                        ),
                        issue_type=IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
                        confidence="medium",
                    )
                )

        if runtime_state_dirty:
            self._persist_runtime_state()
        self._last_run_stats = dict(stats)
        return issues

    def _persist_periodic_bocpd_state(
        self,
        *,
        automation_id: str,
        train_rows: list[dict[str, float]],
        now: datetime,
        window_size: int,
    ) -> bool:
        if not isinstance(self._detector, _BOCPDDetector):
            return False
        if len(train_rows) < 2:
            return False

        training = train_rows[:-1]
        if window_size > 0 and len(training) > window_size:
            training = training[-window_size:]
        if not training:
            return False

        detector = self._detector
        state = detector.initial_state()
        for row in training:
            observed = max(
                0, round(self._coerce_float(row.get("rolling_24h_count"), 0.0))
            )
            detector.update_state(state, observed)
        detector.normalize_state(state)

        automation_state = self._ensure_automation_state(automation_id)
        periodic_model = automation_state.setdefault("periodic_model", {})
        if not isinstance(periodic_model, dict):
            periodic_model = {}
            automation_state["periodic_model"] = periodic_model

        run_length_probs_raw = state.get("run_length_probs")
        observations_raw = state.get("observations")
        periodic_model["run_length_probs"] = (
            [
                self._coerce_float(value, 0.0)
                for value in cast(list[Any], run_length_probs_raw)
            ]
            if isinstance(run_length_probs_raw, list)
            else [1.0]
        )
        periodic_model["observations"] = (
            [
                max(0, int(self._coerce_float(value, 0.0)))
                for value in cast(list[Any], observations_raw)
            ]
            if isinstance(observations_raw, list)
            else []
        )
        periodic_model["map_run_length"] = max(
            0,
            int(self._coerce_float(state.get("map_run_length"), 0.0)),
        )
        periodic_model["expected_rate"] = max(
            0.0,
            self._coerce_float(state.get("expected_rate"), 0.0),
        )
        periodic_model["updated_at"] = now.isoformat()
        periodic_model["window_size"] = max(0, int(window_size))
        return True

    def _score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        *,
        window_size: int,
    ) -> float:
        try:
            return self._detector.score_current(
                automation_id,
                train_rows,
                window_size=window_size,
            )
        except TypeError as exc:
            _LOGGER.debug(
                "Detector for '%s' raised TypeError, falling back without window_size: %s",
                automation_id,
                exc,
            )
            return self._detector.score_current(automation_id, train_rows)

    def _smoothed_score(self, automation_id: str, score: float) -> float:
        history = self._score_history.setdefault(automation_id, [])
        history.append(score)
        if len(history) > self.score_ema_samples:
            del history[: -self.score_ema_samples]

        ema = history[0]
        for value in history[1:]:
            ema = (self._score_ema_alpha * value) + ((1 - self._score_ema_alpha) * ema)
        return ema

    def _dismissed_multiplier(
        self, automation_id: str, *, suppression_store: Any = None
    ) -> float:
        automation_state = self._ensure_automation_state(automation_id)
        adaptation = automation_state.get("adaptation", {})
        learned_multiplier = 1.0
        if isinstance(adaptation, dict):
            learned_multiplier = max(
                1.0,
                self._coerce_float(adaptation.get("threshold_multiplier"), 1.0),
            )

        if suppression_store is None:
            hass_data = getattr(self.hass, "data", {})
            data = (
                cast(dict[str, Any], hass_data) if isinstance(hass_data, dict) else {}
            )
            suppression_store = data.get("suppression_store")
        if suppression_store is None or not hasattr(suppression_store, "is_suppressed"):
            return learned_multiplier

        if self._is_runtime_suppressed(automation_id, suppression_store):
            return max(learned_multiplier, self.dismissed_threshold_multiplier)
        return learned_multiplier

    @staticmethod
    def _compute_window_size(expected_daily: float) -> int:
        return max(16, min(1024, int(max(1.0, expected_daily) * 30)))

    def _effective_warmup_samples(
        self,
        *,
        expected_daily: float,
        baseline_days: int,
        baseline_event_count: int,
        oldest_event_age_days: float | None = None,
    ) -> int:
        """Compute warmup requirements with low-frequency-aware adaptation."""
        required = max(0, int(self.warmup_samples))
        if required <= 1:
            return required
        if baseline_event_count <= 0:
            return required
        if (
            oldest_event_age_days is not None
            and oldest_event_age_days < float(self.cold_start_days)
        ):
            return required
        if baseline_days < self.baseline_days:
            return required
        if expected_daily < 1.0:
            return min(required, 2)
        return required

    def _log_score_telemetry(
        self,
        *,
        automation_id: str,
        score: float,
        now: datetime,
        features: dict[str, float],
    ) -> bool:
        if not self._telemetry_db_path:
            return True

        db_path = Path(self._telemetry_db_path)
        try:
            with sqlite3.connect(db_path) as conn:
                with self._telemetry_lock:
                    if not self._telemetry_table_ensured:
                        conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS runtime_health_scores (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                ts TEXT NOT NULL,
                                automation_id TEXT NOT NULL,
                                score REAL NOT NULL,
                                features_json TEXT NOT NULL
                            )
                            """
                        )
                        self._telemetry_table_ensured = True
                conn.execute(
                    """
                    INSERT INTO runtime_health_scores (ts, automation_id, score, features_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        now.isoformat(),
                        automation_id,
                        float(score),
                        json.dumps(features, separators=(",", ":")),
                    ),
                )
                cutoff = (now - timedelta(days=_TELEMETRY_RETENTION_DAYS)).isoformat()
                conn.execute(
                    "DELETE FROM runtime_health_scores WHERE ts < ?",
                    (cutoff,),
                )
            return True
        except Exception as err:
            _LOGGER.debug("Failed writing runtime score telemetry: %s", err)
            return False

    @staticmethod
    def _count_events_in_range(
        events: Iterable[datetime],
        start: datetime,
        end: datetime,
    ) -> int:
        return sum(1 for ts in events if start <= ts <= end)

    @staticmethod
    def _median_gap_minutes(events: list[datetime]) -> float:
        if len(events) < 2:
            return 60.0
        sorted_events = sorted(events)
        gaps = [
            (sorted_events[idx] - sorted_events[idx - 1]).total_seconds() / 60.0
            for idx in range(1, len(sorted_events))
        ]
        return max(1.0, float(median(gaps)))

    @staticmethod
    def _build_5m_bucket_index(
        all_events_by_automation: dict[str, list[datetime]],
    ) -> dict[datetime, set[str]]:
        """Build an index mapping 5-minute bucket starts to automation IDs with events."""
        index: dict[datetime, set[str]] = defaultdict(set)
        for automation_id, events in all_events_by_automation.items():
            for ts in events:
                bucket_start = ts.replace(
                    minute=(ts.minute // 5) * 5, second=0, microsecond=0
                )
                index[bucket_start].add(automation_id)
        return dict(index)

    @staticmethod
    def _count_other_automations_same_5m(
        automation_id: str,
        now: datetime,
        all_events_by_automation: dict[str, list[datetime]],
    ) -> float:
        bucket_start = now - timedelta(
            minutes=now.minute % 5,
            seconds=now.second,
            microseconds=now.microsecond,
        )
        bucket_end = bucket_start + timedelta(minutes=5)
        count = 0
        for other_id, events in all_events_by_automation.items():
            if other_id == automation_id:
                continue
            if any(bucket_start <= ts < bucket_end for ts in events):
                count += 1
        return float(count)

    @staticmethod
    def _build_feature_row(
        *,
        automation_id: str,
        now: datetime,
        automation_events: list[datetime],
        baseline_events: list[datetime],
        expected_daily: float,
        all_events_by_automation: dict[str, list[datetime]],
        hour_ratio_days: int = 30,
        median_gap_override: float | None = None,
        bucket_index: dict[datetime, set[str]] | None = None,
    ) -> dict[str, float]:
        events_up_to_now = [ts for ts in automation_events if ts <= now]
        rolling_24h_count = float(
            RuntimeHealthMonitor._count_events_in_range(
                events_up_to_now, now - timedelta(hours=24), now
            )
        )
        rolling_7d_count = float(
            RuntimeHealthMonitor._count_events_in_range(
                events_up_to_now, now - timedelta(days=7), now
            )
        )

        baseline_window_days = max(1, hour_ratio_days)
        baseline_window_start = now - timedelta(days=baseline_window_days)
        baseline_30d = [
            ts for ts in baseline_events if baseline_window_start <= ts < now
        ]
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        current_hour_count = float(
            RuntimeHealthMonitor._count_events_in_range(
                events_up_to_now,
                current_hour_start,
                now,
            )
        )
        hour_matches = [ts for ts in baseline_30d if ts.hour == now.hour]
        hour_avg = float(len(hour_matches)) / float(baseline_window_days)
        hour_ratio_30d = (
            current_hour_count / hour_avg if hour_avg > 0 else current_hour_count
        )

        minutes_since_last = (
            (now - max(events_up_to_now)).total_seconds() / 60.0
            if events_up_to_now
            else 24 * 60.0
        )
        median_gap = (
            median_gap_override
            if median_gap_override is not None
            else RuntimeHealthMonitor._median_gap_minutes(baseline_events)
        )
        gap_vs_median = minutes_since_last / median_gap if median_gap > 0 else 0.0

        if bucket_index is not None:
            bucket_key = now.replace(
                minute=(now.minute // 5) * 5, second=0, microsecond=0
            )
            bucket_members = bucket_index.get(bucket_key, set())
            other_5m = float(sum(1 for aid in bucket_members if aid != automation_id))
        else:
            other_5m = RuntimeHealthMonitor._count_other_automations_same_5m(
                automation_id=automation_id,
                now=now,
                all_events_by_automation=all_events_by_automation,
            )

        return {
            "rolling_24h_count": rolling_24h_count,
            "rolling_7d_count": rolling_7d_count,
            "hour_ratio_30d": hour_ratio_30d,
            "gap_vs_median": gap_vs_median,
            "is_weekend": 1.0 if now.weekday() >= 5 else 0.0,
            "other_automations_5m": other_5m,
        }

    @staticmethod
    def _build_training_rows_from_events(
        *,
        automation_id: str,
        baseline_events: list[datetime],
        baseline_start: datetime,
        baseline_end: datetime,
        expected_daily: float,
        all_events_by_automation: dict[str, list[datetime]],
        cold_start_days: int,
        hour_ratio_days: int = 30,
        median_gap_override: float | None = None,
        bucket_index: dict[datetime, set[str]] | None = None,
    ) -> list[dict[str, float]]:
        rows: list[dict[str, float]] = []
        current = baseline_start + timedelta(days=max(0, cold_start_days))
        while current < baseline_end:
            rows.append(
                RuntimeHealthMonitor._build_feature_row(
                    automation_id=automation_id,
                    now=current,
                    automation_events=baseline_events,
                    baseline_events=baseline_events,
                    expected_daily=expected_daily,
                    all_events_by_automation=all_events_by_automation,
                    hour_ratio_days=hour_ratio_days,
                    median_gap_override=median_gap_override,
                    bucket_index=bucket_index,
                )
            )
            current += timedelta(days=1)
        return rows

    @staticmethod
    def _build_daily_counts(
        events: list[datetime],
        start: datetime,
        end: datetime,
    ) -> list[int]:
        counts = [0] * max(0, (end.date() - start.date()).days)
        for ts in events:
            day_idx = (ts.date() - start.date()).days
            if 0 <= day_idx < len(counts):
                counts[day_idx] += 1
        return counts

    async def _async_fetch_trigger_history(
        self,
        automation_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[datetime]]:
        """Fetch automation trigger timestamps from recorder events table."""
        self._last_query_failed = False
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text
        except Exception:  # pragma: no cover - dependency/runtime differences
            _LOGGER.debug("Recorder/SQLAlchemy unavailable for runtime monitoring")
            return {aid: [] for aid in automation_ids}

        def _query() -> dict[str, list[datetime]]:
            results: dict[str, list[datetime]] = {aid: [] for aid in automation_ids}
            instance = get_instance(self.hass)
            with instance.get_session() as session:
                rows = session.execute(
                    text(
                        """
                        SELECT ed.shared_data, e.time_fired_ts
                        FROM events e
                        INNER JOIN event_types et
                            ON e.event_type_id = et.event_type_id
                        INNER JOIN event_data ed
                            ON e.data_id = ed.data_id
                        WHERE et.event_type = 'automation_triggered'
                        AND e.time_fired_ts >= :start_ts
                        AND e.time_fired_ts <= :end_ts
                        """
                    ),
                    {
                        "start_ts": start.timestamp(),
                        "end_ts": end.timestamp(),
                    },
                )

                for shared_data_raw, fired_ts in rows:
                    if fired_ts is None:
                        continue
                    try:
                        payload = cast(
                            dict[str, Any],
                            shared_data_raw
                            if isinstance(shared_data_raw, dict)
                            else json.loads(shared_data_raw or "{}"),
                        )
                    except (TypeError, json.JSONDecodeError):
                        continue

                    entity_id: str | None = payload.get("entity_id")
                    if entity_id not in results:
                        continue
                    results[entity_id].append(datetime.fromtimestamp(fired_ts, tz=UTC))

            return results

        days_span = (end - start).days
        _LOGGER.debug(
            "Querying recorder for %d automation IDs over %d days",
            len(automation_ids),
            days_span,
        )
        try:
            result = await self.hass.async_add_executor_job(_query)
            total_events = sum(len(ts_list) for ts_list in result.values())
            automations_with_events = sum(1 for ts_list in result.values() if ts_list)
            _LOGGER.debug(
                "Fetched %d total trigger events for %d automations",
                total_events,
                automations_with_events,
            )
            return result
        except Exception as err:  # pragma: no cover - integration/runtime differences
            self._last_query_failed = True
            _LOGGER.debug(
                "Failed to query recorder events for runtime monitor: %s", err
            )
            return {aid: [] for aid in automation_ids}
