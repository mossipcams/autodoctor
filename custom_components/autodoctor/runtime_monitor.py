"""Runtime health monitoring for automation trigger behavior."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from functools import partial
from statistics import fmean, median
from typing import Any, Protocol, cast

from .const import (
    DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
    DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
    DOMAIN,
)
from .models import IssueType, Severity, ValidationIssue
from .runtime_event_store import (
    AsyncRuntimeEventStore,
    RuntimeEventStore,
    classify_time_bucket,
)

_LOGGER = logging.getLogger(__name__)
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
        min_expected_events: int = 1,
        score_ema_samples: int = 5,
        dismissed_threshold_multiplier: float = 1.25,
        cold_start_days: int = 7,
        startup_recovery_minutes: int = 0,
        detector: _Detector | None = None,
        sensitivity: str = "medium",
        burst_multiplier: float = 4.0,
        max_alerts_per_day: int = 10,
        global_alert_cap_per_day: int | None = None,
        smoothing_window: int = 5,
        auto_adapt: bool = True,
        hazard_rate: float = DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
        max_run_length: int = DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
        runtime_event_store: RuntimeEventStore | None = None,
        async_runtime_event_store: AsyncRuntimeEventStore | None = None,
        now_factory: Any = None,
    ) -> None:
        self.hass = hass
        self.baseline_days = baseline_days
        self.hour_ratio_days = max(1, hour_ratio_days)
        self.warmup_samples = warmup_samples
        self.min_expected_events = min_expected_events
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
        self._runtime_event_store_degraded = False
        self._runtime_event_store_pending_jobs = 0
        self._runtime_event_store_write_failures = 0
        self._runtime_event_store_dropped_events = 0
        self._runtime_event_store: RuntimeEventStore | None = runtime_event_store
        self._async_runtime_event_store: AsyncRuntimeEventStore | None = (
            async_runtime_event_store
        )
        self._runtime_event_store_tasks: set[asyncio.Task[Any]] = set()
        self._bocpd_count_detector = _BOCPDDetector(
            hazard_rate=self.hazard_rate,
            max_run_length=self.max_run_length,
        )
        self._detector: _Detector = detector or self._bocpd_count_detector
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._started_at = self._now_factory()
        self._score_history: dict[str, list[float]] = {}
        self._last_run_stats: dict[str, int] = {}
        self._runtime_state: dict[str, Any] = {
            "schema_version": 2,
            "automations": {},
            "alerts": {"date": "", "global_count": 0},
            "updated_at": "",
        }
        self._active_runtime_alerts: dict[str, ValidationIssue] = {}
        self._runtime_event_store_db_path: str | None = None
        if self._runtime_event_store is None:
            if hasattr(hass, "config") and hasattr(hass.config, "path"):
                self._runtime_event_store_db_path = hass.config.path(
                    "autodoctor_runtime.db"
                )
        if (
            self._async_runtime_event_store is None
            and self._runtime_event_store is not None
        ):
            self._async_runtime_event_store = AsyncRuntimeEventStore(
                hass,
                self._runtime_event_store,
            )
        _LOGGER.debug(
            "RuntimeHealthMonitor initialized: baseline_days=%d, warmup_samples=%d, "
            "min_expected_events=%d, hour_ratio_days=%d, detector=%s",
            baseline_days,
            warmup_samples,
            min_expected_events,
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

    @staticmethod
    def classify_time_bucket(timestamp: datetime) -> str:
        """Map timestamp into weekday/weekend x daypart bucket."""
        return classify_time_bucket(timestamp)

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
        event_time = occurred_at or self._now_factory()
        automation_state = self._ensure_automation_state(automation_entity_id)
        runtime_suppressed = self._is_runtime_suppressed(
            automation_entity_id, suppression_store
        )

        gap_model_raw = automation_state.get("gap_model", {})
        if isinstance(gap_model_raw, dict):
            gap_model = cast(dict[str, Any], gap_model_raw)
            last_trigger = self._coerce_datetime(gap_model.get("last_trigger"))
            if last_trigger is not None and event_time <= last_trigger:
                _LOGGER.debug(
                    "Ignoring out-of-order runtime trigger for '%s': event_time=%s last_trigger=%s",
                    automation_entity_id,
                    event_time.isoformat(),
                    last_trigger.isoformat(),
                )
                return []

        self._enqueue_runtime_event_store_write(
            automation_entity_id=automation_entity_id,
            event_time=event_time,
        )

        count_bucket_name, count_bucket = self._update_count_model(
            automation_state, event_time
        )
        self._update_gap_model(automation_state, event_time)
        if runtime_suppressed:
            self._clear_runtime_alert(
                automation_entity_id, IssueType.RUNTIME_AUTOMATION_OVERACTIVE
            )
            self._clear_runtime_alert(
                automation_entity_id, IssueType.RUNTIME_AUTOMATION_BURST
            )
            issues: list[ValidationIssue] = []
        else:
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
        return issues

    def _enqueue_runtime_event_store_write(
        self,
        *,
        automation_entity_id: str,
        event_time: datetime,
    ) -> None:
        """Schedule an async dual-write of a live trigger into local event store."""
        if self._async_runtime_event_store is None:
            return
        async_store = self._async_runtime_event_store

        async def _write() -> None:
            try:
                self._runtime_event_store_pending_jobs = max(
                    self._runtime_event_store_pending_jobs,
                    int(getattr(async_store, "pending_jobs", 0)),
                )
                result = await async_store.async_record_trigger(
                    automation_entity_id,
                    event_time,
                )
                if result is False:
                    self._runtime_event_store_degraded = True
                    self._runtime_event_store_dropped_events += 1
                self._runtime_event_store_pending_jobs = int(
                    getattr(async_store, "pending_jobs", 0)
                )
            except Exception as err:
                self._runtime_event_store_degraded = True
                self._runtime_event_store_write_failures += 1
                self._runtime_event_store_pending_jobs = int(
                    getattr(async_store, "pending_jobs", 0)
                )
                _LOGGER.debug(
                    "Runtime event-store write failed for '%s': %s",
                    automation_entity_id,
                    err,
                )

        task: Any
        if hasattr(self.hass, "async_create_task"):
            task = self.hass.async_create_task(_write())
        elif hasattr(self.hass, "create_task"):
            task = self.hass.create_task(_write())
        else:
            task = asyncio.create_task(_write())

        if isinstance(task, asyncio.Task):
            self._runtime_event_store_tasks.add(task)
            task.add_done_callback(self._runtime_event_store_tasks.discard)

    def get_event_store_diagnostics(self) -> dict[str, Any]:
        """Return runtime event-store rollout diagnostics."""
        return {
            "enabled": True,
            "cutover": True,
            "degraded": self._runtime_event_store_degraded,
            "pending_jobs": self._runtime_event_store_pending_jobs,
            "write_failures": self._runtime_event_store_write_failures,
            "dropped_events": self._runtime_event_store_dropped_events,
        }

    def catch_up_count_model(
        self,
        store: RuntimeEventStore,
        automation_id: str,
        now: datetime,
    ) -> None:
        """Replay missing finalized daily counts into BOCPD bucket state."""
        automation_state = self._ensure_automation_state(automation_id)
        count_model_raw: object = automation_state.setdefault("count_model", {})
        if not isinstance(count_model_raw, dict):
            count_model_raw = {}
            automation_state["count_model"] = count_model_raw
        count_model = cast(dict[str, Any], count_model_raw)
        buckets_raw: object = count_model.setdefault("buckets", {})
        if not isinstance(buckets_raw, dict):
            buckets_raw = {}
            count_model["buckets"] = buckets_raw
        buckets = cast(dict[str, Any], buckets_raw)

        store.rebuild_daily_summaries(automation_id)

        for bucket_name in list(buckets.keys()):
            bucket_state = self._ensure_count_bucket_state(count_model, bucket_name)
            current_day_str = bucket_state.get("current_day")
            current_day = self._coerce_date(current_day_str)
            if current_day is None:
                continue
            target_day = now.date()
            if current_day >= target_day:
                continue

            daily_bucket = store.get_daily_bucket_counts(automation_id, bucket_name)

            cursor = current_day + timedelta(days=1)
            while cursor < target_day:
                if self._bucket_matches_day_type(bucket_name, cursor):
                    count = daily_bucket.get(cursor.isoformat(), 0)
                    self._bocpd_count_detector.update_state(bucket_state, count)
                cursor += timedelta(days=1)
            bucket_state["current_day"] = target_day.isoformat()
            bucket_state["current_count"] = 0

    def rebuild_models_from_store(self, *, now: datetime | None = None) -> None:
        """Bootstrap in-memory BOCPD + gap models from SQLite event store."""
        store = self._runtime_event_store
        if store is None:
            return
        if now is None:
            now = cast(datetime, self._now_factory())
        target_day = now.date()
        for aid in store.get_automation_ids():
            store.rebuild_daily_summaries(aid)
            automation_state = self._ensure_automation_state(aid)
            count_model = cast(dict[str, Any], automation_state["count_model"])
            for bucket_name in (
                "weekday_morning",
                "weekday_afternoon",
                "weekday_evening",
                "weekday_night",
                "weekend_morning",
                "weekend_afternoon",
                "weekend_evening",
                "weekend_night",
            ):
                daily_counts = store.get_daily_bucket_counts(aid, bucket_name)
                if not daily_counts:
                    continue
                bucket_state = self._ensure_count_bucket_state(count_model, bucket_name)
                min_date = date.fromisoformat(sorted(daily_counts)[0])
                cursor = min_date
                while cursor < target_day:
                    if self._bucket_matches_day_type(bucket_name, cursor):
                        count = daily_counts.get(cursor.isoformat(), 0)
                        self._bocpd_count_detector.update_state(bucket_state, count)
                    cursor += timedelta(days=1)
                bucket_state["current_day"] = target_day.isoformat()
                bucket_state["current_count"] = 0

            # Seed gap model from last trigger in store
            last_epoch = store.get_last_trigger(aid)
            if last_epoch is not None:
                last_dt = datetime.fromtimestamp(last_epoch, tz=UTC)
                automation_state["gap_model"]["last_trigger"] = last_dt.isoformat()

    async def async_rebuild_models_from_store(self) -> None:
        """Run rebuild_models_from_store in an executor thread."""
        await self.hass.async_add_executor_job(self.rebuild_models_from_store)

    async def async_bootstrap_from_recorder(
        self,
        automations: list[dict[str, Any]],
    ) -> None:
        """One-time bootstrap: import recorder history into SQLite if empty."""
        store = self._runtime_event_store
        if store is None:
            return

        def _check_bootstrap_needed() -> bool:
            if store.get_metadata("bootstrap:complete") == "true":
                return False
            if store.get_automation_ids():
                store.set_metadata("bootstrap:complete", "true")
                return False
            return True

        if not await self.hass.async_add_executor_job(_check_bootstrap_needed):
            return

        automation_ids: list[str] = []
        for automation in automations:
            entity_id = self._resolve_automation_entity_id(automation)
            if entity_id:
                automation_ids.append(entity_id)
        if not automation_ids:
            await self.hass.async_add_executor_job(
                store.set_metadata, "bootstrap:complete", "true"
            )
            return
        now = self._now_factory()
        start = now - timedelta(days=max(self.baseline_days, 90))
        history = await self._async_fetch_trigger_history(automation_ids, start, now)

        def _import_history() -> None:
            for aid, timestamps in history.items():
                store.bulk_import(aid, timestamps)
            store.set_metadata("bootstrap:complete", "true")

        await self.hass.async_add_executor_job(_import_history)

    async def async_close_event_store(self) -> None:
        """Drain pending event-store tasks and close the SQLite connection."""
        # Await all in-flight write tasks before closing the connection
        tasks = list(self._runtime_event_store_tasks)
        for task in tasks:
            with contextlib.suppress(Exception):
                await task
        self._runtime_event_store_tasks.clear()
        if self._runtime_event_store is not None:
            await self.hass.async_add_executor_job(self._runtime_event_store.close)

    async def async_init_event_store(self) -> None:
        """Create and initialize the runtime event store off the event loop."""
        if (
            self._runtime_event_store is not None
            or not self._runtime_event_store_db_path
        ):
            return

        db_path = self._runtime_event_store_db_path

        def _create_store() -> RuntimeEventStore:
            store = RuntimeEventStore(db_path)
            store.ensure_schema(target_version=1)
            return store

        try:
            store = await self.hass.async_add_executor_job(_create_store)
            self._runtime_event_store = store
            self._async_runtime_event_store = AsyncRuntimeEventStore(
                self.hass,
                store,
            )
        except Exception as err:
            _LOGGER.warning("Failed initializing runtime event store: %s", err)
            self._runtime_event_store = None

    def run_weekly_maintenance(self, *, now: datetime | None = None) -> None:
        """Record maintenance tick; BOCPD path has no periodic bucket promotion."""
        maintenance_time = now or self._now_factory()
        self._runtime_state["last_weekly_maintenance"] = maintenance_time.isoformat()

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
        if previous_trigger is None or event_time >= previous_trigger:
            gap_model["last_trigger"] = event_time.isoformat()

    def _detect_count_anomaly(
        self,
        *,
        automation_entity_id: str,
        automation_state: dict[str, Any],
        bucket_name: str,
        bucket_state: dict[str, Any],
        now: datetime,
    ) -> list[ValidationIssue]:
        issue_type = IssueType.RUNTIME_AUTOMATION_OVERACTIVE
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
            issue_type=IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
            confidence="medium",
        )
        self._register_runtime_alert(issue)
        count_model = automation_state.get("count_model", {})
        if isinstance(count_model, dict):
            count_model["anomaly_streak"] = (
                int(count_model.get("anomaly_streak", 0)) + 1
            )

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
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_OVERACTIVE.value}",
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
        history = await self._async_fetch_trigger_history_from_store(
            automation_ids=automation_ids,
            start=baseline_start,
            end=now,
        )
        if (
            self.warmup_samples > 0
            and self.baseline_days < _SPARSE_WARMUP_LOOKBACK_DAYS
        ):
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
                extended_history = await self._async_fetch_trigger_history_from_store(
                    automation_ids=sparse_automation_ids,
                    start=extended_baseline_start,
                    end=baseline_start,
                )
                for automation_id in sparse_automation_ids:
                    merged_events = sorted(
                        history.get(automation_id, [])
                        + extended_history.get(automation_id, [])
                    )
                    history[automation_id] = merged_events
                    baseline_start_by_automation[automation_id] = (
                        extended_baseline_start
                    )
                looked_back_automation_ids.update(sparse_automation_ids)
                stats["extended_lookback_used"] += len(sparse_automation_ids)
                _LOGGER.debug(
                    "Runtime health extended lookback applied to %d sparse automations",
                    len(sparse_automation_ids),
                )

        issues: list[ValidationIssue] = []
        all_events_by_automation = history
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
                    (now - timestamps[0]).total_seconds() / 86400
                    if timestamps
                    else None
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
            prefetched_ema: float | None = None
            if (
                not self._score_history.get(automation_entity_id)
                and self._runtime_event_store is not None
            ):
                try:
                    persisted = await self.hass.async_add_executor_job(
                        self._runtime_event_store.get_last_score,
                        automation_entity_id,
                    )
                    if persisted is not None:
                        prefetched_ema = self._coerce_float(
                            getattr(persisted, "ema_score", 0.0), 0.0
                        )
                except Exception as err:
                    _LOGGER.debug(
                        "Failed reading persisted runtime EMA for '%s': %s",
                        automation_entity_id,
                        err,
                    )
            smoothed_score = self._smoothed_score(
                automation_entity_id, score, persisted_ema=prefetched_ema
            )
            if self._runtime_event_store is not None:
                try:
                    await self.hass.async_add_executor_job(
                        partial(
                            self._runtime_event_store.record_score,
                            automation_entity_id,
                            scored_at=now,
                            score=smoothed_score,
                            ema_score=smoothed_score,
                            features=current_row,
                        )
                    )
                except Exception as err:
                    self._runtime_event_store_write_failures += 1
                    self._runtime_event_store_degraded = True
                    _LOGGER.debug(
                        "Failed persisting runtime score history for '%s': %s",
                        automation_entity_id,
                        err,
                    )
            _LOGGER.debug(
                "Automation '%s': anomaly score=%.3f ema=%.3f",
                automation_name,
                score,
                smoothed_score,
            )

            self._clear_runtime_alert(
                automation_entity_id,
                IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
            )

        evaluated_automation_ids = set(automation_ids)
        existing_keys = {issue.get_suppression_key() for issue in issues}
        for issue in self.get_active_runtime_alerts():
            if issue.automation_id not in evaluated_automation_ids:
                continue
            key = issue.get_suppression_key()
            if key in existing_keys:
                continue
            issues.append(issue)
            existing_keys.add(key)

        self._last_run_stats = dict(stats)
        return issues

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

    def _smoothed_score(
        self,
        automation_id: str,
        score: float,
        *,
        persisted_ema: float | None = None,
    ) -> float:
        history = self._score_history.setdefault(automation_id, [])
        if not history and persisted_ema is not None:
            history.append(max(0.0, persisted_ema))
        history.append(score)
        if len(history) > self.score_ema_samples:
            del history[: -self.score_ema_samples]

        ema = history[0]
        for value in history[1:]:
            ema = (self._score_ema_alpha * value) + ((1 - self._score_ema_alpha) * ema)
        return ema

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
        if oldest_event_age_days is not None and oldest_event_age_days < float(
            self.cold_start_days
        ):
            return required
        if baseline_days < self.baseline_days:
            return required
        if expected_daily < 1.0:
            return min(required, 2)
        return required

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
        requested_ids = [
            automation_id for automation_id in automation_ids if automation_id
        ]
        if not requested_ids:
            return {}
        try:
            from homeassistant.components.recorder import get_instance
            from sqlalchemy import text
        except Exception:  # pragma: no cover - dependency/runtime differences
            _LOGGER.debug("Recorder/SQLAlchemy unavailable for runtime monitoring")
            return {aid: [] for aid in requested_ids}

        def _query() -> dict[str, list[datetime]]:
            unique_ids = list(dict.fromkeys(requested_ids))
            results: dict[str, list[datetime]] = {aid: [] for aid in unique_ids}

            def _escape_like(value: str) -> str:
                return (
                    value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )

            instance = get_instance(self.hass)
            with instance.get_session() as session:
                chunk_size = 200
                for chunk_start in range(0, len(unique_ids), chunk_size):
                    id_chunk = unique_ids[chunk_start : chunk_start + chunk_size]
                    like_clauses: list[str] = []
                    params: dict[str, Any] = {
                        "start_ts": start.timestamp(),
                        "end_ts": end.timestamp(),
                    }
                    for idx, automation_id in enumerate(id_chunk):
                        param_name = f"entity_like_{idx}"
                        params[param_name] = (
                            f'%"entity_id"%"{_escape_like(automation_id)}"%'
                        )
                        like_clauses.append(
                            f"ed.shared_data LIKE :{param_name} ESCAPE '\\'"
                        )

                    rows = session.execute(
                        text(
                            f"""
                            SELECT ed.shared_data, e.time_fired_ts
                            FROM events e
                            INNER JOIN event_types et
                                ON e.event_type_id = et.event_type_id
                            INNER JOIN event_data ed
                                ON e.data_id = ed.data_id
                            WHERE et.event_type = 'automation_triggered'
                            AND e.time_fired_ts >= :start_ts
                            AND e.time_fired_ts <= :end_ts
                            AND ({" OR ".join(like_clauses)})
                            """
                        ),
                        params,
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
                        results[entity_id].append(
                            datetime.fromtimestamp(fired_ts, tz=UTC)
                        )

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
            _LOGGER.debug(
                "Failed to query recorder events for runtime monitor: %s", err
            )
            return {aid: [] for aid in requested_ids}

    async def _async_fetch_trigger_history_from_store(
        self,
        *,
        automation_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[datetime]]:
        """Fetch trigger history from local runtime event store."""
        if self._async_runtime_event_store is None:
            return {automation_id: [] for automation_id in automation_ids}
        history: dict[str, list[datetime]] = {}
        for automation_id in automation_ids:
            try:
                epochs = await self._async_runtime_event_store.async_get_events(
                    automation_id,
                    start,
                    end,
                )
            except Exception as err:
                _LOGGER.debug(
                    "Failed reading runtime event store history for '%s': %s",
                    automation_id,
                    err,
                )
                history[automation_id] = []
                continue
            history[automation_id] = [
                datetime.fromtimestamp(float(ts), tz=UTC) for ts in epochs
            ]
        return history
