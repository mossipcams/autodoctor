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
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from statistics import fmean, median
from typing import Any, Protocol, cast

from .const import DOMAIN
from .models import IssueType, Severity, ValidationIssue
from .runtime_health_state_store import RuntimeHealthStateStore

_LOGGER = logging.getLogger(__name__)
_TELEMETRY_RETENTION_DAYS = 90
_BUCKET_NIGHT_START_HOUR = 22
_BUCKET_MORNING_START_HOUR = 5
_BUCKET_AFTERNOON_START_HOUR = 12
_BUCKET_EVENING_START_HOUR = 17
_DEFAULT_RUNTIME_FLUSH_INTERVAL_MINUTES = 15


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


class _GammaPoissonDetector:
    """Gamma-Poisson anomaly detector over rolling 24h trigger counts.

    Uses a conjugate Gamma prior over Poisson rate and returns a two-sided
    tail anomaly score for the current count.
    """

    def __init__(
        self,
        *,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
        count_feature: str = "rolling_24h_count",
    ) -> None:
        self._prior_alpha = max(1e-6, float(prior_alpha))
        self._prior_beta = max(1e-6, float(prior_beta))
        self._count_feature = count_feature

    def score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        window_size: int | None = None,
    ) -> float:
        """Return a two-sided tail score where larger means more anomalous."""
        if len(train_rows) < 2:
            return 0.0

        training = train_rows[:-1]
        if window_size is not None and window_size > 0 and len(training) > window_size:
            training = training[-window_size:]

        baseline_counts = [self._coerce_count(row) for row in training]
        if not baseline_counts:
            return 0.0
        current_count = self._coerce_count(train_rows[-1])

        score = self._score_count(
            baseline_counts=baseline_counts,
            current_count=current_count,
        )
        _LOGGER.debug(
            "Scored '%s' with Gamma-Poisson: %.3f (current=%d, n=%d)",
            automation_id,
            score,
            current_count,
            len(baseline_counts),
        )
        return score

    def _coerce_count(self, row: dict[str, float]) -> int:
        value = row.get(self._count_feature, 0.0)
        try:
            return max(0, round(float(value)))
        except (TypeError, ValueError):
            return 0

    def _score_count(self, *, baseline_counts: list[int], current_count: int) -> float:
        n = len(baseline_counts)
        total = float(sum(baseline_counts))
        r = self._prior_alpha + total
        p = (self._prior_beta + n) / (self._prior_beta + n + 1.0)

        cdf = 0.0
        for count in range(current_count + 1):
            cdf += self._nb_pmf(count, r, p)

        pmf_current = self._nb_pmf(current_count, r, p)
        lower_tail = min(1.0, max(0.0, cdf))
        upper_tail = min(1.0, max(0.0, 1.0 - (cdf - pmf_current)))
        two_sided_p = min(1.0, 2.0 * min(lower_tail, upper_tail))
        return float(-math.log10(max(two_sided_p, 1e-12)))

    @staticmethod
    def _nb_pmf(count: int, r: float, p: float) -> float:
        if count < 0:
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
        self._detector: _Detector = detector or _GammaPoissonDetector()
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
        self._runtime_state = self._runtime_state_store.load()
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

    def flush_runtime_state(self) -> None:
        """Force a runtime state persistence flush."""
        self._persist_runtime_state()

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
        """Evaluate learned gap thresholds and return newly emitted gap issues."""
        check_time = now or self._now_factory()
        issues: list[ValidationIssue] = []
        automations = self._runtime_state.get("automations", {})
        if not isinstance(automations, dict):
            return []
        automations_dict = cast(dict[str, Any], automations)

        for automation_id, automation_state_raw in automations_dict.items():
            if not isinstance(automation_state_raw, dict):
                continue
            automation_state = cast(dict[str, Any], automation_state_raw)
            gap_model_raw = automation_state.get("gap_model", {})
            if not isinstance(gap_model_raw, dict):
                continue
            gap_model = cast(dict[str, Any], gap_model_raw)

            last_trigger = self._coerce_datetime(gap_model.get("last_trigger"))
            p99_minutes = self._coerce_float(gap_model.get("p99_minutes"), 0.0)
            if last_trigger is None or p99_minutes <= 0:
                continue

            elapsed_minutes = max(
                0.0, (check_time - last_trigger).total_seconds() / 60.0
            )
            if elapsed_minutes <= p99_minutes:
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
                    f"learned p99 {p99_minutes:.1f}m"
                ),
                issue_type=IssueType.RUNTIME_AUTOMATION_GAP,
                confidence="medium",
            )
            self._register_runtime_alert(issue)
            issues.append(issue)

        if issues:
            self._persist_runtime_state()
        else:
            self._maybe_flush_runtime_state(check_time)
        return issues

    def run_weekly_maintenance(self, *, now: datetime | None = None) -> None:
        """Promote over-dispersed buckets to NB scoring mode."""
        maintenance_time = now or self._now_factory()
        automations = self._runtime_state.get("automations", {})
        if not isinstance(automations, dict):
            return
        automations_dict = cast(dict[str, Any], automations)
        for automation_state_raw in automations_dict.values():
            if not isinstance(automation_state_raw, dict):
                continue
            automation_state = cast(dict[str, Any], automation_state_raw)
            count_model_raw = automation_state.get("count_model", {})
            if not isinstance(count_model_raw, dict):
                continue
            count_model = cast(dict[str, Any], count_model_raw)
            buckets_raw = count_model.get("buckets", {})
            if not isinstance(buckets_raw, dict):
                continue
            buckets_dict = cast(dict[str, Any], buckets_raw)
            for bucket_state in buckets_dict.values():
                if not isinstance(bucket_state, dict):
                    continue
                vmr = self._coerce_float(bucket_state.get("vmr"), 1.0)
                bucket_state["use_negative_binomial"] = vmr > 1.5
        self._runtime_state["last_weekly_maintenance"] = maintenance_time.isoformat()
        self._persist_runtime_state()

    @staticmethod
    def _empty_automation_state() -> dict[str, Any]:
        """Return default in-memory state for an automation runtime model."""
        return {
            "count_model": {
                "buckets": {},
                "negative_binomial_buckets": [],
                "anomaly_streak": 0,
            },
            "gap_model": {
                "intervals_minutes": [],
                "last_trigger": None,
                "lambda_per_minute": 0.0,
                "p99_minutes": 0.0,
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

    @staticmethod
    def _ensure_count_bucket_state(
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
            return cast(dict[str, Any], bucket_state_raw)
        bucket_state: dict[str, Any] = {
            "counts": [],
            "current_day": "",
            "current_count": 0,
            "alpha": 1.0,
            "beta": 1.0,
            "mean": 0.0,
            "variance": 0.0,
            "vmr": 1.0,
            "use_negative_binomial": False,
        }
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

        event_day = event_time.date().isoformat()
        current_day = str(bucket_state.get("current_day", ""))
        if current_day and current_day != event_day:
            counts = bucket_state.get("counts")
            if not isinstance(counts, list):
                counts = []
                bucket_state["counts"] = counts
            counts.append(int(bucket_state.get("current_count", 0)))
            if len(counts) > 180:
                del counts[:-180]
            bucket_state["current_count"] = 0

        if not current_day or current_day != event_day:
            bucket_state["current_day"] = event_day
            bucket_state["current_count"] = 0

        bucket_state["current_count"] = int(bucket_state.get("current_count", 0)) + 1
        self._refresh_count_bucket_stats(bucket_state)
        return bucket_name, bucket_state

    @staticmethod
    def _refresh_count_bucket_stats(bucket_state: dict[str, Any]) -> None:
        counts_raw = bucket_state.get("counts")
        counts_values = (
            cast(list[Any], counts_raw) if isinstance(counts_raw, list) else []
        )
        counts = [max(0, int(value)) for value in counts_values]
        total = float(sum(counts))
        n = len(counts)
        bucket_state["alpha"] = 1.0 + total
        bucket_state["beta"] = 1.0 + float(n)

        if n == 0:
            current_count = max(0.0, float(bucket_state.get("current_count", 0.0)))
            bucket_state["mean"] = current_count
            bucket_state["variance"] = max(1.0, current_count)
            bucket_state["vmr"] = 1.0
            return

        mean = total / float(n)
        if n > 1:
            variance = sum((value - mean) ** 2 for value in counts) / float(n - 1)
        else:
            variance = max(1.0, mean)
        vmr = variance / mean if mean > 0 else 1.0
        bucket_state["mean"] = float(mean)
        bucket_state["variance"] = float(max(0.0, variance))
        bucket_state["vmr"] = float(max(0.0, vmr))

    def _update_gap_model(
        self,
        automation_state: dict[str, Any],
        event_time: datetime,
    ) -> None:
        gap_model = automation_state.setdefault("gap_model", {})
        if not isinstance(gap_model, dict):
            gap_model = {}
            automation_state["gap_model"] = gap_model
        intervals_raw = cast(Any, gap_model.get("intervals_minutes"))
        if isinstance(intervals_raw, list):
            intervals_list = cast(list[float], intervals_raw)
        else:
            intervals_list = []
            gap_model["intervals_minutes"] = intervals_list

        last_trigger = self._coerce_datetime(gap_model.get("last_trigger"))
        if last_trigger is not None and event_time > last_trigger:
            interval = max(0.0, (event_time - last_trigger).total_seconds() / 60.0)
            intervals_list.append(interval)
            if len(intervals_list) > 240:
                del intervals_list[:-240]
            mean_gap = fmean(intervals_list) if intervals_list else 0.0
            lambda_per_minute = (1.0 / mean_gap) if mean_gap > 0 else 0.0
            gap_model["lambda_per_minute"] = lambda_per_minute
            gap_model["p99_minutes"] = (
                (-math.log(0.01) / lambda_per_minute) if lambda_per_minute > 0 else 0.0
            )

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
        counts = bucket_state.get("counts")
        if not isinstance(counts, list) or len(counts) < 7:
            return []

        lower, upper = self._expected_count_range(bucket_state)
        observed = int(bucket_state.get("current_count", 0))
        if lower <= observed <= upper:
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

    def _detect_burst_anomaly(
        self,
        *,
        automation_entity_id: str,
        automation_state: dict[str, Any],
        now: datetime,
    ) -> list[ValidationIssue]:
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

        if len(recent) < 6 or float(current_5m_count) < threshold:
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
            issue_type=IssueType.RUNTIME_AUTOMATION_BURST,
            confidence="medium",
        )
        self._register_runtime_alert(issue)
        self._persist_runtime_state()
        return [issue]

    def _expected_count_range(self, bucket_state: dict[str, Any]) -> tuple[int, int]:
        sensitivity_to_coverage = {
            "low": 0.99,
            "medium": 0.95,
            "high": 0.90,
        }
        coverage = sensitivity_to_coverage.get(self.sensitivity, 0.95)
        tail = (1.0 - coverage) / 2.0

        use_nb = bool(bucket_state.get("use_negative_binomial", False))
        if use_nb:
            mean = max(0.0, self._coerce_float(bucket_state.get("mean"), 0.0))
            variance = max(0.0, self._coerce_float(bucket_state.get("variance"), 0.0))
            if mean > 0 and variance > mean:
                r = (mean * mean) / max(1e-6, variance - mean)
                p = r / (r + mean)
            else:
                # Near-Poisson fallback.
                r = max(1e-6, mean if mean > 0 else 1.0)
                p = r / (r + max(1.0, mean))
        else:
            r = max(1e-6, self._coerce_float(bucket_state.get("alpha"), 1.0))
            beta = max(1e-6, self._coerce_float(bucket_state.get("beta"), 1.0))
            p = beta / (beta + 1.0)

        lower = self._nb_quantile(tail, r=r, p=p)
        upper = self._nb_quantile(1.0 - tail, r=r, p=p)
        return max(0, lower), max(0, upper)

    def _nb_quantile(self, quantile: float, *, r: float, p: float) -> int:
        q = min(1.0, max(0.0, quantile))
        if q <= 0.0:
            return 0
        if q >= 1.0:
            return 10_000
        cumulative = 0.0
        for count in range(10_001):
            cumulative += self._negative_binomial_pmf(count, r, p)
            if cumulative >= q:
                return count
        return 10_000

    @staticmethod
    def _negative_binomial_pmf(count: int, r: float, p: float) -> float:
        if count < 0:
            return 0.0
        log_prob = (
            math.lgamma(count + r)
            - math.lgamma(count + 1)
            - math.lgamma(r)
            + (r * math.log(p))
            + (count * math.log(1.0 - p))
        )
        return math.exp(log_prob)

    def _register_runtime_alert(self, issue: ValidationIssue) -> None:
        self._active_runtime_alerts[issue.get_suppression_key()] = issue

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
        bucket_state["counts"] = []
        bucket_state["current_count"] = 0
        bucket_state["alpha"] = 1.0
        bucket_state["beta"] = 1.0
        bucket_state["mean"] = 0.0
        bucket_state["variance"] = 0.0
        bucket_state["vmr"] = 1.0
        bucket_state["use_negative_binomial"] = False
        count_model_dict["anomaly_streak"] = 0
        _LOGGER.debug(
            "Auto-adapt reset runtime count baseline for '%s' bucket '%s'",
            automation_entity_id,
            bucket_name,
        )
        self._persist_runtime_state()

    def _persist_runtime_state(self) -> None:
        self._runtime_state_store.save(self._runtime_state)
        self._last_runtime_state_flush = self._now_factory()

    def _maybe_flush_runtime_state(self, now: datetime) -> None:
        if (now - self._last_runtime_state_flush) < self._runtime_state_flush_interval:
            return
        self._runtime_state_store.save(self._runtime_state)
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

        history = await self._async_fetch_trigger_history(
            automation_ids,
            baseline_start,
            now,
        )
        if self._last_query_failed:
            stats["recorder_query_failed"] = 1

        issues: list[ValidationIssue] = []
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
            timestamps = sorted(history.get(automation_entity_id, []))

            baseline_events = [
                t for t in timestamps if baseline_start <= t < recent_start
            ]
            recent_events = [t for t in timestamps if recent_start <= t <= now]
            day_counts = self._build_daily_counts(
                baseline_events, baseline_start, recent_start
            )
            expected = fmean(day_counts) if day_counts else 0.0
            active_days = sum(1 for c in day_counts if c > 0)
            _LOGGER.debug(
                "Automation '%s': %d baseline events, %d recent events, %d active days",
                automation_name,
                len(baseline_events),
                len(recent_events),
                active_days,
            )

            if active_days < self.warmup_samples:
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient warmup: "
                    "%d active days < %d required)",
                    automation_name,
                    active_days,
                    self.warmup_samples,
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
                baseline_start=baseline_start,
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

            if recent_count == 0 and smoothed_score >= stalled_threshold:
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
            ):
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
