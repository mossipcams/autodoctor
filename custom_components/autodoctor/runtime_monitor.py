"""Runtime health monitoring for automation trigger behavior."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from statistics import fmean, median
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .suppression_store import SuppressionStore

from .bocpd_detector import (
    DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
    DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
    BOCPDDetector,
    Detector,
)
from .const import DOMAIN
from .models import IssueType, Severity, ValidationIssue
from .runtime_event_store import (
    AsyncRuntimeEventStore,
    RuntimeEventStore,
    classify_time_bucket,
)

_LOGGER = logging.getLogger(__name__)

# --- Tuning constants (not user-configurable) ---

# Event store write failure logging threshold
_WRITE_FAILURE_LOG_THRESHOLD = 3

# Bootstrap history minimum horizon (days)
_BOOTSTRAP_MIN_HISTORY_DAYS = 90

# Burst detection
_BURST_WINDOW_HOURS = 1
_BURST_SHORT_WINDOW_MINUTES = 5
_BURST_BASELINE_SEGMENT_COUNT = 11.0
_BURST_THRESHOLD_FLOOR = 2.0
_BURST_BASELINE_EMA_DECAY = 0.8
_BURST_BASELINE_EMA_NEW = 0.2
_BURST_MIN_RECENT_TRIGGERS = 6
_BURST_MIN_SHORT_WINDOW_COUNT = 3

# Validation scoring
_RECENT_WINDOW_HOURS = 24
_LOW_FREQUENCY_WARMUP_MINIMUM = 2
_DEFAULT_MEDIAN_GAP_MINUTES = 60.0
_MIN_MEDIAN_GAP_MINUTES = 1.0
_OVERDUE_MIN_COMPARABLE_ACTIVE_DAYS = 4
_OVERDUE_PREDICTABLE_SCORE_THRESHOLD = 0.7
_OVERDUE_PROBABILITY_THRESHOLD = 0.85
_OVERDUE_PROBABILITY_THRESHOLD_CEILING = 0.99
_BUCKET_GRANULARITY_MINUTES = 5
_RECORDER_QUERY_CHUNK_SIZE = 200
_EVENT_STORE_OBS_START_KEY = "observation:start_at"
_OVERACTIVE_MIN_COMPARABLE_ACTIVE_DAYS = 2
_HISTORICAL_HIGH_VOLUME_MIN_DAILY_COUNT = 10

# BOCPD anomaly score sensitivity thresholds
_SENSITIVITY_THRESHOLDS: dict[str, float] = {
    "low": 3.0,
    "medium": 2.0,
    "high": 1.5,
}
_OVERACTIVE_PROMOTION_MARGIN = 0.5
_OVERACTIVE_IMMEDIATE_MARGIN = 0.5

# EMA recovery: snap hangover when raw score is clearly normal again.
_EMA_RECOVERY_RATIO = 0.5


@dataclass(frozen=True)
class _RuntimeHistoryFetchResult:
    """Per-validation runtime history read result."""

    history: dict[str, list[datetime]]
    failed_automation_ids: frozenset[str]
    read_failure_count: int = 0


def _linear_percentile(values: list[float], quantile: float) -> float | None:
    """Return linear-interpolated percentile from sorted numeric values."""
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    clamped = min(1.0, max(0.0, float(quantile)))
    position = clamped * float(len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - float(lower)
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


class RuntimeHealthMonitor:
    """Detect runtime automation anomalies from recorder trigger history."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        baseline_days: int = 30,
        min_coverage_days: int | None = None,
        hour_ratio_days: int = 30,
        warmup_samples: int = 14,
        min_expected_events: int = 1,
        score_ema_samples: int = 5,
        dismissed_threshold_multiplier: float = 1.25,
        cold_start_days: int = 7,
        startup_recovery_minutes: int = 0,
        detector: Detector | None = None,
        sensitivity: str = "medium",
        burst_multiplier: float = 4.0,
        max_alerts_per_day: int = 10,
        global_alert_cap_per_day: int | None = None,
        hazard_rate: float = DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
        max_run_length: int = DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
        runtime_event_store: RuntimeEventStore | None = None,
        async_runtime_event_store: AsyncRuntimeEventStore | None = None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.hass = hass
        self.baseline_days = baseline_days
        self.min_coverage_days = max(
            1,
            int(min_coverage_days if min_coverage_days is not None else baseline_days),
        )
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
        self.hazard_rate = min(1.0, max(1e-6, float(hazard_rate)))
        self.max_run_length = max(2, int(max_run_length))
        self._runtime_event_store_degraded = False
        self._runtime_event_store_pending_jobs = 0
        self._runtime_event_store_write_failures = 0
        self._runtime_event_store_read_failures = 0
        self._runtime_event_store_dropped_events = 0
        self._runtime_event_store: RuntimeEventStore | None = runtime_event_store
        self._async_runtime_event_store: AsyncRuntimeEventStore | None = (
            async_runtime_event_store
        )
        self._runtime_event_store_tasks: set[asyncio.Task[Any]] = set()
        self._detector: Detector = detector or BOCPDDetector(
            hazard_rate=self.hazard_rate,
            max_run_length=self.max_run_length,
        )
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._started_at = self._now_factory()
        self._score_history: dict[str, list[float]] = {}
        self._score_ema: dict[str, float] = {}
        self._last_run_stats: dict[str, int] = {}
        self._runtime_state: dict[str, Any] = {
            "schema_version": 2,
            "automations": {},
            "alerts": {"date": "", "global_count": 0},
            "updated_at": "",
        }
        self._active_runtime_alerts: dict[str, ValidationIssue] = {}
        self._loaded_adaptation_ids: set[str] = set()
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
        if self._runtime_event_store is not None:
            try:
                if (
                    self._runtime_event_store.get_metadata(_EVENT_STORE_OBS_START_KEY)
                    is None
                ):
                    self._runtime_event_store.set_metadata(
                        _EVENT_STORE_OBS_START_KEY, self._started_at.isoformat()
                    )
            except Exception:
                _LOGGER.debug(
                    "Failed initializing runtime observation metadata",
                    exc_info=True,
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
        suppression_store: SuppressionStore | None = None,
    ) -> list[ValidationIssue]:
        """Ingest a live automation_triggered event for runtime model updates."""
        if not automation_entity_id or not automation_entity_id.startswith(
            "automation."
        ):
            return []
        event_time = occurred_at or self._now_factory()
        automation_state = self._ensure_automation_state(automation_entity_id)
        burst_suppressed = self._is_runtime_suppressed(
            automation_entity_id,
            IssueType.RUNTIME_AUTOMATION_BURST,
            suppression_store,
        )

        last_trigger = self._coerce_datetime(automation_state.get("last_trigger"))
        if last_trigger is not None and event_time <= last_trigger:
            _LOGGER.debug(
                "Ignoring out-of-order runtime trigger for '%s': event_time=%s last_trigger=%s",
                automation_entity_id,
                event_time.isoformat(),
                last_trigger.isoformat(),
            )
            return []

        automation_state["last_trigger"] = event_time.isoformat()

        self._enqueue_runtime_event_store_write(
            automation_entity_id=automation_entity_id,
            event_time=event_time,
        )

        recovery_cutoff = self._started_at + timedelta(
            minutes=self.startup_recovery_minutes
        )
        if (
            self.startup_recovery_minutes > 0
            and self._started_at <= event_time < recovery_cutoff
        ):
            return []

        self._clear_runtime_alert(
            automation_entity_id, IssueType.RUNTIME_AUTOMATION_OVERDUE
        )

        if burst_suppressed:
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
                log_fn = (
                    _LOGGER.warning
                    if self._runtime_event_store_write_failures
                    <= _WRITE_FAILURE_LOG_THRESHOLD
                    else _LOGGER.debug
                )
                log_fn(
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
        """Return runtime event-store operational diagnostics."""
        return {
            "degraded": self._runtime_event_store_degraded,
            "pending_jobs": self._runtime_event_store_pending_jobs,
            "write_failures": self._runtime_event_store_write_failures,
            "read_failures": self._runtime_event_store_read_failures,
            "dropped_events": self._runtime_event_store_dropped_events,
        }

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
        start = now - timedelta(
            days=max(self.baseline_days, _BOOTSTRAP_MIN_HISTORY_DAYS)
        )
        history = await self._async_fetch_trigger_history(automation_ids, start, now)

        def _import_history() -> None:
            imported_timestamps = [
                ts for timestamps in history.values() for ts in timestamps
            ]
            for aid, timestamps in history.items():
                store.bulk_import(aid, timestamps)
            if imported_timestamps:
                earliest = min(imported_timestamps)
                existing = self._coerce_datetime(
                    store.get_metadata(_EVENT_STORE_OBS_START_KEY)
                )
                if existing is None or earliest < existing:
                    store.set_metadata(_EVENT_STORE_OBS_START_KEY, earliest.isoformat())
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

        now = self._now_factory()

        def _create_store() -> RuntimeEventStore:
            store = RuntimeEventStore(db_path)
            store.ensure_schema(target_version=1)
            if store.get_metadata(_EVENT_STORE_OBS_START_KEY) is None:
                store.set_metadata(_EVENT_STORE_OBS_START_KEY, now.isoformat())
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
        """Record maintenance tick and trim old events from the store."""
        maintenance_time = now or self._now_factory()
        self._runtime_state["last_weekly_maintenance"] = maintenance_time.isoformat()
        if self._runtime_event_store is not None:
            try:
                retention = self.baseline_days + 7
                deleted = self._runtime_event_store.trim(
                    retention_days=retention, now=maintenance_time
                )
                if deleted > 0:
                    _LOGGER.info(
                        "Weekly maintenance: trimmed %d events older than %d days",
                        deleted,
                        retention,
                    )
            except Exception:
                _LOGGER.debug(
                    "Weekly maintenance: failed to trim event store", exc_info=True
                )

    @staticmethod
    def _empty_automation_state() -> dict[str, Any]:
        """Return default in-memory state for an automation runtime model."""
        return {
            "last_trigger": None,
            "burst_model": {
                "recent_triggers": [],
                "baseline_rate_5m": 0.0,
                "baseline_rate_5m_by_bucket": {},
                "baseline_samples": 0,
            },
            "rate_limit": {
                "date": "",
                "count": 0,
                "last_alert": None,
            },
            "adaptation": {
                "threshold_multiplier": 1.0,
                "dismissed_count": 0,
                "overactive": {
                    "threshold_multiplier": 1.0,
                    "dismissed_count": 0,
                },
                "burst": {
                    "threshold_multiplier": 1.0,
                    "dismissed_count": 0,
                },
                "overdue": {
                    "threshold_multiplier": 1.0,
                    "dismissed_count": 0,
                },
            },
            "overactive_confirmation": {
                "pending": False,
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
        else:
            state = cast(dict[str, Any], state_raw)
            defaults = self._empty_automation_state()
            for key, default_value in defaults.items():
                if key not in state or (
                    isinstance(default_value, dict) and not isinstance(state[key], dict)
                ):
                    state[key] = deepcopy(default_value)

        if (
            automation_entity_id not in self._loaded_adaptation_ids
            and self._runtime_event_store is not None
        ):
            self._loaded_adaptation_ids.add(automation_entity_id)
            raw = self._runtime_event_store.get_metadata(
                f"adaptation:{automation_entity_id}"
            )
            if raw is not None:
                try:
                    persisted = json.loads(raw)
                    adaptation_raw = state.setdefault("adaptation", {})
                    if isinstance(adaptation_raw, dict):
                        adaptation = cast(dict[str, Any], adaptation_raw)
                    else:
                        adaptation: dict[str, Any] = {}
                        state["adaptation"] = adaptation
                    if int(persisted.get("dismissed_count", 0)) > int(
                        adaptation.get("dismissed_count", 0)
                    ):
                        adaptation["dismissed_count"] = persisted["dismissed_count"]
                        adaptation["threshold_multiplier"] = persisted[
                            "threshold_multiplier"
                        ]
                        overactive = adaptation.setdefault("overactive", {})
                        if isinstance(overactive, dict):
                            overactive_bucket = cast(dict[str, Any], overactive)
                            overactive_bucket["dismissed_count"] = persisted[
                                "dismissed_count"
                            ]
                            overactive_bucket["threshold_multiplier"] = persisted[
                                "threshold_multiplier"
                            ]
                    for key in ("overactive", "burst", "overdue"):
                        persisted_bucket = persisted.get(key)
                        if not isinstance(persisted_bucket, dict):
                            continue
                        bucket_raw = adaptation.setdefault(key, {})
                        if isinstance(bucket_raw, dict):
                            bucket = cast(dict[str, Any], bucket_raw)
                        else:
                            bucket = {}
                            adaptation[key] = bucket
                        if int(persisted_bucket.get("dismissed_count", 0)) > int(
                            bucket.get("dismissed_count", 0)
                        ):
                            bucket["dismissed_count"] = persisted_bucket[
                                "dismissed_count"
                            ]
                            bucket["threshold_multiplier"] = persisted_bucket[
                                "threshold_multiplier"
                            ]
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

        return state

    @staticmethod
    def _resolve_burst_bucket_baseline(
        *,
        bucket_name: str,
        baseline_by_bucket: dict[str, Any],
        global_baseline: float,
    ) -> tuple[float, str]:
        """Resolve burst baseline with bucket-aware fallback."""
        exact = RuntimeHealthMonitor._coerce_float(
            baseline_by_bucket.get(bucket_name),
            0.0,
        )
        if exact > 0.0:
            return exact, RuntimeHealthMonitor._bucket_label(bucket_name)

        current_daypart = RuntimeHealthMonitor._bucket_daypart(bucket_name)
        daypart_values = [
            RuntimeHealthMonitor._coerce_float(value, 0.0)
            for key, value in baseline_by_bucket.items()
            if RuntimeHealthMonitor._bucket_daypart(key) == current_daypart
        ]
        daypart_values = [value for value in daypart_values if value > 0.0]
        if len(daypart_values) >= 2:
            return fmean(daypart_values), current_daypart

        if bucket_name.startswith("weekday_"):
            prefix = "weekday_"
            label = "weekday"
        elif bucket_name.startswith("weekend_"):
            prefix = "weekend_"
            label = "weekend"
        else:
            prefix = ""
            label = "same day type"
        day_type_values = [
            RuntimeHealthMonitor._coerce_float(value, 0.0)
            for key, value in baseline_by_bucket.items()
            if prefix and key.startswith(prefix)
        ]
        day_type_values = [value for value in day_type_values if value > 0.0]
        if len(day_type_values) >= 2:
            return fmean(day_type_values), label

        return global_baseline, "all history"

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
            if ts is not None and ts >= (now - timedelta(hours=_BURST_WINDOW_HOURS))
        ]
        recent.append(now)
        recent.sort()

        current_5m_count = sum(
            1
            for ts in recent
            if ts >= (now - timedelta(minutes=_BURST_SHORT_WINDOW_MINUTES))
        )
        baseline_segment_count = sum(
            1
            for ts in recent
            if (now - timedelta(hours=_BURST_WINDOW_HOURS))
            <= ts
            < (now - timedelta(minutes=_BURST_SHORT_WINDOW_MINUTES))
        )
        baseline_from_history = (
            baseline_segment_count / _BURST_BASELINE_SEGMENT_COUNT
            if baseline_segment_count
            else 0.0
        )
        bucket_name = classify_time_bucket(now)
        previous_baseline = self._coerce_float(burst_model.get("baseline_rate_5m"), 0.0)
        baseline_by_bucket_raw = cast(
            Any, burst_model.get("baseline_rate_5m_by_bucket")
        )
        baseline_by_bucket = (
            cast(dict[str, Any], baseline_by_bucket_raw)
            if isinstance(baseline_by_bucket_raw, dict)
            else {}
        )
        baseline_samples = int(
            self._coerce_float(burst_model.get("baseline_samples"), 0.0)
        )
        global_baseline = (
            previous_baseline
            if previous_baseline > 0
            else max(1.0, baseline_from_history if baseline_from_history > 0 else 1.0)
        )
        baseline_rate, baseline_context_label = self._resolve_burst_bucket_baseline(
            bucket_name=bucket_name,
            baseline_by_bucket=baseline_by_bucket,
            global_baseline=global_baseline,
        )
        base_threshold = max(
            _BURST_THRESHOLD_FLOOR, baseline_rate * self.burst_multiplier
        )
        threshold = base_threshold * self._threshold_multiplier_for(
            automation_entity_id, "burst"
        )

        burst_model["recent_triggers"] = [ts.isoformat() for ts in recent]
        burst_model["baseline_rate_5m_by_bucket"] = baseline_by_bucket
        if baseline_from_history > 0:
            burst_model["baseline_rate_5m"] = (
                _BURST_BASELINE_EMA_DECAY * global_baseline
            ) + (_BURST_BASELINE_EMA_NEW * baseline_from_history)
            previous_bucket_baseline = self._coerce_float(
                baseline_by_bucket.get(bucket_name),
                global_baseline,
            )
            baseline_by_bucket[bucket_name] = (
                _BURST_BASELINE_EMA_DECAY * previous_bucket_baseline
            ) + (_BURST_BASELINE_EMA_NEW * baseline_from_history)
            baseline_samples += 1
            burst_model["baseline_samples"] = baseline_samples
        else:
            burst_model["baseline_rate_5m"] = global_baseline
            burst_model["baseline_samples"] = baseline_samples

        if not allow_alerts:
            return []
        if baseline_samples <= 0:
            self._clear_runtime_alert(automation_entity_id, issue_type)
            return []
        if (
            len(recent) < _BURST_MIN_RECENT_TRIGGERS
            or current_5m_count < _BURST_MIN_SHORT_WINDOW_COUNT
            or float(current_5m_count) < threshold
        ):
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
                f"Burst: runtime burst detected in 5m window: observed {current_5m_count} "
                f"triggers vs {baseline_context_label} baseline {baseline_rate:.2f}/5m"
            ),
            issue_type=issue_type,
            confidence="medium",
            evidence={
                "detector": "burst",
                "observed_5m_count": float(current_5m_count),
                "baseline_5m_count": float(baseline_rate),
                "threshold": float(threshold),
                "window_minutes": _BURST_SHORT_WINDOW_MINUTES,
                "baseline_window_minutes": _BURST_WINDOW_HOURS * 60,
            },
        )
        self._register_runtime_alert(issue)

        return [issue]

    def _score_threshold_for(self, automation_id: str) -> float:
        """Return effective anomaly score threshold for an automation."""
        base = _SENSITIVITY_THRESHOLDS.get(self.sensitivity, 2.0)
        return base * self._threshold_multiplier_for(automation_id, "overactive")

    def _threshold_multiplier_for(self, automation_id: str, detector_key: str) -> float:
        """Return dismissal multiplier for a runtime detector."""
        automation_state = self._ensure_automation_state(automation_id)
        adaptation_raw = automation_state.get("adaptation", {})
        if not isinstance(adaptation_raw, dict):
            return 1.0
        adaptation = cast(dict[str, Any], adaptation_raw)
        if detector_key == "overactive":
            top_level = self._coerce_float(adaptation.get("threshold_multiplier"), 1.0)
            bucket_raw = adaptation.get(detector_key)
            if isinstance(bucket_raw, dict):
                bucket = cast(dict[str, Any], bucket_raw)
                return max(
                    1.0,
                    self._coerce_float(
                        bucket.get("threshold_multiplier"),
                        top_level,
                    ),
                )
            return max(1.0, top_level)
        bucket_raw = adaptation.get(detector_key)
        if not isinstance(bucket_raw, dict):
            return 1.0
        bucket = cast(dict[str, Any], bucket_raw)
        return max(
            1.0,
            self._coerce_float(bucket.get("threshold_multiplier"), 1.0),
        )

    def _overdue_probability_threshold_for(self, automation_id: str) -> float:
        """Return effective overdue probability threshold for an automation."""
        dismissed_count = self._dismissed_count_for(automation_id, "overdue")
        if dismissed_count <= 0:
            return _OVERDUE_PROBABILITY_THRESHOLD
        adaptation_fraction = 1.0 - (1.0 / (float(dismissed_count) + 1.5))
        return _OVERDUE_PROBABILITY_THRESHOLD + (
            (_OVERDUE_PROBABILITY_THRESHOLD_CEILING - _OVERDUE_PROBABILITY_THRESHOLD)
            * adaptation_fraction
        )

    def _dismissed_count_for(self, automation_id: str, detector_key: str) -> int:
        """Return dismissal count for one runtime detector bucket."""
        automation_state = self._ensure_automation_state(automation_id)
        adaptation_raw = automation_state.get("adaptation", {})
        if not isinstance(adaptation_raw, dict):
            return 0
        adaptation = cast(dict[str, Any], adaptation_raw)
        bucket_raw = adaptation.get(detector_key)
        if not isinstance(bucket_raw, dict):
            return 0
        bucket = cast(dict[str, Any], bucket_raw)
        return max(0, int(self._coerce_float(bucket.get("dismissed_count"), 0.0)))

    def _register_runtime_alert(self, issue: ValidationIssue) -> None:
        self._active_runtime_alerts[issue.get_suppression_key()] = issue

    def _clear_runtime_alert(self, automation_id: str, issue_type: IssueType) -> None:
        key = f"{automation_id}:{automation_id}:{issue_type.value}"
        self._active_runtime_alerts.pop(key, None)

    def _clear_runtime_alerts_for(self, automation_id: str) -> int:
        """Clear all active runtime alerts for one automation."""
        before = len(self._active_runtime_alerts)
        for issue_type in (
            IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
            IssueType.RUNTIME_AUTOMATION_BURST,
            IssueType.RUNTIME_AUTOMATION_OVERDUE,
        ):
            self._clear_runtime_alert(automation_id, issue_type)
        return max(0, before - len(self._active_runtime_alerts))

    def _clear_historical_runtime_alerts_for(self, automation_id: str) -> int:
        """Clear validation-scored runtime alerts while preserving live burst alerts."""
        before = len(self._active_runtime_alerts)
        for issue_type in (
            IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
            IssueType.RUNTIME_AUTOMATION_OVERDUE,
        ):
            self._clear_runtime_alert(automation_id, issue_type)
        return max(0, before - len(self._active_runtime_alerts))

    def clear_runtime_alert(
        self,
        automation_id: str,
        issue_type: IssueType | str,
    ) -> None:
        """Clear one active runtime alert by automation and issue type."""
        resolved_issue_type = (
            issue_type if isinstance(issue_type, IssueType) else IssueType(issue_type)
        )
        self._clear_runtime_alert(automation_id, resolved_issue_type)

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
        issue_type: IssueType,
        suppression_store: SuppressionStore | None,
    ) -> bool:
        if suppression_store is None or not hasattr(suppression_store, "is_suppressed"):
            return False
        prefixes = (f"{automation_id}:{automation_id}:{issue_type.value}",)
        try:
            return any(
                bool(suppression_store.is_suppressed(prefix)) for prefix in prefixes
            )
        except Exception:
            _LOGGER.debug(
                "Suppression check failed for '%s'", prefixes[0], exc_info=True
            )
        return False

    def _runtime_suppression_store(self) -> SuppressionStore | None:
        """Return suppression store from hass domain data when available."""
        hass_data = getattr(self.hass, "data", {})
        data = cast(dict[str, Any], hass_data) if isinstance(hass_data, dict) else {}
        domain_data_raw = data.get(DOMAIN, {})
        if not isinstance(domain_data_raw, dict):
            return None
        domain_data = cast(dict[str, Any], domain_data_raw)
        return domain_data.get("suppression_store")

    def record_issue_dismissed(
        self,
        automation_id: str,
        issue_type: IssueType | str | None = None,
    ) -> None:
        """Increase dismissal-aware threshold multiplier for an automation."""
        automation_state = self._ensure_automation_state(automation_id)
        adaptation_raw = automation_state.setdefault("adaptation", {})
        if isinstance(adaptation_raw, dict):
            adaptation = cast(dict[str, Any], adaptation_raw)
        else:
            adaptation: dict[str, Any] = {}
            automation_state["adaptation"] = adaptation
        issue_value = (
            issue_type.value if isinstance(issue_type, IssueType) else issue_type
        )
        detector_key = "overactive"
        if issue_value == IssueType.RUNTIME_AUTOMATION_BURST.value:
            detector_key = "burst"
        elif issue_value == IssueType.RUNTIME_AUTOMATION_OVERDUE.value:
            detector_key = "overdue"

        bucket_raw = adaptation.setdefault(detector_key, {})
        if isinstance(bucket_raw, dict):
            bucket = cast(dict[str, Any], bucket_raw)
        else:
            bucket: dict[str, Any] = {}
            adaptation[detector_key] = bucket
        bucket["dismissed_count"] = int(bucket.get("dismissed_count", 0)) + 1
        current_multiplier = self._coerce_float(
            bucket.get("threshold_multiplier"),
            1.0,
        )
        bucket["threshold_multiplier"] = max(
            1.0, current_multiplier * self.dismissed_threshold_multiplier
        )
        if detector_key == "overactive":
            adaptation["dismissed_count"] = bucket["dismissed_count"]
            adaptation["threshold_multiplier"] = bucket["threshold_multiplier"]
        if self._runtime_event_store is not None:
            self._runtime_event_store.set_metadata(
                f"adaptation:{automation_id}",
                json.dumps(adaptation),
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

    def _resolve_automation_name(
        self, automation_entity_id: str, automation: dict[str, Any]
    ) -> str:
        """Resolve display name from the canonical HA entity when possible."""
        state = self.hass.states.get(automation_entity_id)
        friendly_name = None
        if state is not None:
            friendly_name = state.attributes.get("friendly_name")
        if isinstance(friendly_name, str) and friendly_name:
            return friendly_name
        return str(automation.get("alias", automation_entity_id))

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

        recent_start = now - timedelta(hours=_RECENT_WINDOW_HOURS)
        baseline_start = recent_start - timedelta(days=self.baseline_days)
        observed_start = self._observed_coverage_start()
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

        effective_baseline_start = baseline_start
        if observed_start is not None and observed_start > baseline_start:
            effective_baseline_start = observed_start
        baseline_start_by_automation: dict[str, datetime] = dict.fromkeys(
            automation_ids, effective_baseline_start
        )
        history_result = await self._async_fetch_trigger_history_from_store(
            automation_ids=automation_ids,
            start=baseline_start,
            end=now,
        )
        history = history_result.history
        if history_result.read_failure_count > 0:
            stats["event_store_read_failed"] = history_result.read_failure_count
        failed_history_ids = history_result.failed_automation_ids

        issues: list[ValidationIssue] = []
        all_events_by_automation = history
        bucket_index = self._build_5m_bucket_index(all_events_by_automation)
        suppression_store = self._runtime_suppression_store()
        observed_coverage_days: float | None = (
            max(0.0, (now - observed_start).total_seconds() / 86400)
            if observed_start is not None
            else None
        )
        for automation in automations:
            automation_entity_id = self._resolve_automation_entity_id(automation)
            if not automation_entity_id:
                stats["missing_identity"] += 1
                continue

            automation_name = self._resolve_automation_name(
                automation_entity_id, automation
            )
            automation_baseline_start = baseline_start_by_automation.get(
                automation_entity_id,
                baseline_start,
            )
            if automation_entity_id in failed_history_ids:
                stats["event_store_read_abstained"] += 1
                continue
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
                stats["stale_alerts_cleared"] += (
                    self._clear_historical_runtime_alerts_for(automation_entity_id)
                )
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
                stats["stale_alerts_cleared"] += (
                    self._clear_historical_runtime_alerts_for(automation_entity_id)
                )
                continue

            if observed_coverage_days is not None and observed_coverage_days < float(
                self.min_coverage_days
            ):
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient coverage: %.1f days < %d required)",
                    automation_name,
                    observed_coverage_days,
                    self.min_coverage_days,
                )
                stats["insufficient_coverage"] += 1
                stats["stale_alerts_cleared"] += (
                    self._clear_historical_runtime_alerts_for(automation_entity_id)
                )
                continue

            overdue_decision = self._predict_overdue(
                automation_events=timestamps,
                now=now,
                baseline_start=automation_baseline_start,
                overdue_probability_threshold=self._overdue_probability_threshold_for(
                    automation_entity_id
                ),
            )
            overdue_issue_type = IssueType.RUNTIME_AUTOMATION_OVERDUE
            overdue_suppressed = self._is_runtime_suppressed(
                automation_entity_id,
                overdue_issue_type,
                suppression_store,
            )

            if expected < float(self.min_expected_events):
                if self._handle_overdue_decision(
                    issues=issues,
                    stats=stats,
                    automation_entity_id=automation_entity_id,
                    automation_name=automation_name,
                    timestamps=timestamps,
                    baseline_events=baseline_events,
                    recent_events=recent_events,
                    day_counts=day_counts,
                    active_days=active_days,
                    training_rows_count=0,
                    overdue_decision=overdue_decision,
                    overdue_suppressed=overdue_suppressed,
                    data_quality="cadence",
                    now=now,
                ):
                    continue
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient baseline: "
                    "%.1f events/day < %d required)",
                    automation_name,
                    expected,
                    self.min_expected_events,
                )
                stats["insufficient_baseline"] += 1
                stats["stale_alerts_cleared"] += (
                    self._clear_historical_runtime_alerts_for(automation_entity_id)
                )
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
            bucket_context = self._build_bucket_baseline_context(
                now=now,
                baseline_events=baseline_events,
                baseline_window_start=max(
                    automation_baseline_start,
                    now - timedelta(days=max(1, self.hour_ratio_days)),
                ),
            )
            current_row["predictability_score"] = self._coerce_float(
                overdue_decision.get("predictability_score"),
                0.0,
            )
            current_row["overdue_probability"] = self._coerce_float(
                overdue_decision.get("overdue_probability"),
                0.0,
            )
            train_rows.append(current_row)
            if len(train_rows) < 2:
                _LOGGER.debug(
                    "Automation '%s': skipped (insufficient training rows: %d)",
                    automation_name,
                    len(train_rows),
                )
                stats["insufficient_training_rows"] += 1
                stats["stale_alerts_cleared"] += (
                    self._clear_historical_runtime_alerts_for(automation_entity_id)
                )
                continue
            _LOGGER.debug(
                "Automation '%s': scoring with %d training rows, "
                "expected %.1f/day, recent %d events",
                automation_name,
                len(train_rows) - 1,
                expected,
                len(recent_events),
            )
            score = self._score_current(automation_entity_id, train_rows)
            detector_expected = getattr(self._detector, "last_expected_rate", 0.0)
            if (
                isinstance(detector_expected, (int, float))
                and float(detector_expected) > 0.0
            ):
                # Prefer filtered-training BOCPD rate for alert copy / high-activity gate.
                # Warmup and min_expected still use fmean(day_counts) above.
                expected = float(detector_expected)
            prefetched_ema: float | None = None
            if (
                automation_entity_id not in self._score_ema
                and not self._score_history.get(automation_entity_id)
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
                    feature_payload = dict(current_row)
                    feature_payload["raw_bocpd_score"] = score
                    feature_payload["bocpd_ema_score"] = smoothed_score
                    await self.hass.async_add_executor_job(
                        partial(
                            self._runtime_event_store.record_score,
                            automation_entity_id,
                            scored_at=now,
                            score=score,
                            ema_score=smoothed_score,
                            features=feature_payload,
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
            stats["scored_automations"] += 1

            issue_type = IssueType.RUNTIME_AUTOMATION_OVERACTIVE
            automation_state = self._ensure_automation_state(automation_entity_id)
            threshold = self._score_threshold_for(automation_entity_id)
            promotion_threshold = threshold + _OVERACTIVE_PROMOTION_MARGIN
            immediate_threshold = promotion_threshold + _OVERACTIVE_IMMEDIATE_MARGIN
            overactive_suppressed = self._is_runtime_suppressed(
                automation_entity_id,
                issue_type,
                suppression_store,
            )
            overactive_confirmation = automation_state.setdefault(
                "overactive_confirmation",
                {"pending": False},
            )
            if not isinstance(overactive_confirmation, dict):
                overactive_confirmation = {"pending": False}
                automation_state["overactive_confirmation"] = overactive_confirmation

            self._handle_overdue_decision(
                issues=issues,
                stats=stats,
                automation_entity_id=automation_entity_id,
                automation_name=automation_name,
                timestamps=timestamps,
                baseline_events=baseline_events,
                recent_events=recent_events,
                day_counts=day_counts,
                active_days=active_days,
                training_rows_count=len(train_rows) - 1,
                overdue_decision=overdue_decision,
                overdue_suppressed=overdue_suppressed,
                data_quality="trained",
                now=now,
            )

            current_24h_count = self._coerce_float(
                current_row.get("rolling_24h_count"), 0.0
            )
            is_high_activity = current_24h_count > expected
            comparable_counts = self._overactive_comparable_counts(
                baseline_events,
                now,
                automation_baseline_start,
                recent_start,
            )
            has_comparable_context = (
                comparable_counts["same_day_type_events"] > 0
                and comparable_counts["same_weekday_events"] > 0
            )
            has_comparable_active_days = (
                comparable_counts["same_weekday_active_days"]
                >= _OVERACTIVE_MIN_COMPARABLE_ACTIVE_DAYS
                and comparable_counts["same_day_type_active_days"]
                >= _OVERACTIVE_MIN_COMPARABLE_ACTIVE_DAYS
            )
            required_overactive_count = comparable_counts["required_overactive_count"]
            exceeds_comparable_count = current_24h_count > required_overactive_count
            if (
                smoothed_score >= promotion_threshold
                and is_high_activity
                and has_comparable_context
                and has_comparable_active_days
                and not overactive_suppressed
                and self._within_historical_high_volume_envelope(
                    recent_count=int(current_24h_count),
                    day_counts=day_counts,
                )
            ):
                self._clear_runtime_alert(automation_entity_id, issue_type)
                stats["within_historical_envelope"] += 1
                continue

            if (
                smoothed_score >= promotion_threshold
                and is_high_activity
                and has_comparable_context
                and has_comparable_active_days
                and exceeds_comparable_count
                and not overactive_suppressed
            ):
                overactive_key = (
                    f"{automation_entity_id}:{automation_entity_id}:{issue_type.value}"
                )
                has_active_overactive = overactive_key in self._active_runtime_alerts
                pending_confirmation = bool(overactive_confirmation.get("pending"))
                if has_active_overactive:
                    overactive_confirmation["pending"] = False
                elif smoothed_score >= immediate_threshold or pending_confirmation:
                    overactive_confirmation["pending"] = False
                    if self._allow_alert(automation_entity_id, now=now):
                        confidence = (
                            "high"
                            if threshold > 0 and smoothed_score / threshold >= 2.0
                            else "medium"
                        )
                        issue = ValidationIssue(
                            severity=Severity.WARNING,
                            automation_id=automation_entity_id,
                            automation_name=automation_name,
                            entity_id=automation_entity_id,
                            location="runtime.health.anomaly",
                            message=(
                                f"Overactive: Triggered {current_24h_count:g} times in 24h; "
                                f"normal is about {expected:.1f}/day "
                                f"({bucket_context.get('context_label', 'all history')} baseline; "
                                f"score {smoothed_score:.2f} exceeds threshold {threshold:.2f})"
                            ),
                            issue_type=issue_type,
                            confidence=confidence,
                            evidence={
                                "detector": "overactive",
                                "observed_24h_count": current_24h_count,
                                "expected_daily_count": expected,
                                "score": smoothed_score,
                                "raw_score": score,
                                "threshold": threshold,
                                "promotion_threshold": promotion_threshold,
                                "immediate_threshold": immediate_threshold,
                                "window_hours": _RECENT_WINDOW_HOURS,
                                "baseline_active_days": active_days,
                                "baseline_event_count": len(baseline_events),
                                "baseline_days": len(day_counts),
                                "recent_event_count": len(recent_events),
                                "training_rows": len(train_rows) - 1,
                                "data_quality": "trained",
                                "comparable_day_type_events": comparable_counts[
                                    "same_day_type_events"
                                ],
                                "comparable_weekday_events": comparable_counts[
                                    "same_weekday_events"
                                ],
                                "comparable_day_type_active_days": comparable_counts[
                                    "same_day_type_active_days"
                                ],
                                "comparable_weekday_active_days": comparable_counts[
                                    "same_weekday_active_days"
                                ],
                                "comparable_day_type_p95_count": comparable_counts[
                                    "same_day_type_p95_count"
                                ],
                                "comparable_weekday_p95_count": comparable_counts[
                                    "same_weekday_p95_count"
                                ],
                                "required_overactive_count": required_overactive_count,
                            },
                        )
                        self._register_runtime_alert(issue)
                        issues.append(issue)
                        stats["overactive_alerts"] += 1
                else:
                    overactive_confirmation["pending"] = True
                    stats["overactive_candidates"] += 1
            else:
                overactive_confirmation["pending"] = False
                if smoothed_score >= threshold and not is_high_activity:
                    stats["overactive_low_activity_abstained"] += 1
                elif (
                    smoothed_score >= threshold
                    and is_high_activity
                    and not has_comparable_context
                ):
                    stats["overactive_insufficient_comparable_context"] += 1
                elif (
                    smoothed_score >= threshold
                    and is_high_activity
                    and has_comparable_context
                    and not has_comparable_active_days
                ):
                    stats["overactive_insufficient_comparable_active_days"] += 1
                elif (
                    smoothed_score >= threshold
                    and is_high_activity
                    and has_comparable_context
                    and has_comparable_active_days
                    and not exceeds_comparable_count
                ):
                    stats["overactive_below_comparable_threshold"] += 1
                self._clear_runtime_alert(automation_entity_id, issue_type)

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

    def _handle_overdue_decision(
        self,
        *,
        issues: list[ValidationIssue],
        stats: dict[str, int],
        automation_entity_id: str,
        automation_name: str,
        timestamps: list[datetime],
        baseline_events: list[datetime],
        recent_events: list[datetime],
        day_counts: list[int],
        active_days: int,
        training_rows_count: int,
        overdue_decision: dict[str, float | str | bool | None],
        overdue_suppressed: bool,
        data_quality: str,
        now: datetime,
    ) -> bool:
        """Apply one overdue decision and return whether it emitted an alert."""
        overdue_issue_type = IssueType.RUNTIME_AUTOMATION_OVERDUE
        overdue_status = str(overdue_decision.get("status", "abstain"))
        overdue_probability = self._coerce_float(
            overdue_decision.get("overdue_probability"),
            0.0,
        )
        if overdue_status == "overdue" and not overdue_suppressed:
            if self._allow_alert(automation_entity_id, now=now):
                overdue_confidence = "high" if overdue_probability >= 0.95 else "medium"
                issue = ValidationIssue(
                    severity=Severity.WARNING,
                    automation_id=automation_entity_id,
                    automation_name=automation_name,
                    entity_id=automation_entity_id,
                    location="runtime.health.overdue",
                    message=(
                        f"Overdue: "
                        f"{overdue_decision.get('reason', 'Automation appears overdue based on recent timing history.')!s}"
                    ),
                    issue_type=overdue_issue_type,
                    confidence=overdue_confidence,
                    evidence={
                        "detector": "overdue",
                        "overdue_probability": overdue_probability,
                        "overdue_probability_threshold": self._coerce_float(
                            overdue_decision.get("overdue_probability_threshold"),
                            _OVERDUE_PROBABILITY_THRESHOLD,
                        ),
                        "predictability_score": self._coerce_float(
                            overdue_decision.get("predictability_score"),
                            0.0,
                        ),
                        "comparable_days": self._coerce_float(
                            overdue_decision.get("comparable_days"),
                            0.0,
                        ),
                        "active_comparable_days": self._coerce_float(
                            overdue_decision.get("active_comparable_days"),
                            0.0,
                        ),
                        "usual_deadline": overdue_decision.get("usual_deadline"),
                        "expected_trigger_index": int(
                            self._coerce_float(
                                overdue_decision.get("expected_trigger_index"),
                                1.0,
                            )
                        ),
                        "last_trigger": (
                            max(timestamps).isoformat() if timestamps else None
                        ),
                        "baseline_active_days": active_days,
                        "baseline_event_count": len(baseline_events),
                        "baseline_days": len(day_counts),
                        "recent_event_count": len(recent_events),
                        "training_rows": training_rows_count,
                        "data_quality": data_quality,
                    },
                )
                self._register_runtime_alert(issue)
                issues.append(issue)
                stats["overdue_alerts"] += 1
                if bool(overdue_decision.get("repeated_run")):
                    stats["overdue_repeated_run_supported"] += 1
                return True
            return False

        if overdue_status == "abstain":
            abstain_reason = str(overdue_decision.get("abstain_reason", "unknown"))
            if abstain_reason == "unpredictable":
                stats["overdue_unpredictable"] += 1
            elif abstain_reason == "multi_run_unsupported":
                stats["overdue_multi_run_unsupported"] += 1
        elif overdue_status == "not_due":
            not_due_reason = str(overdue_decision.get("not_due_reason", "unknown"))
            if not_due_reason == "next_window_open":
                stats["overdue_next_window_open"] += 1
        self._clear_runtime_alert(automation_entity_id, overdue_issue_type)
        return False

    def _score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
    ) -> float:
        return self._detector.score_current(automation_id, train_rows)

    @staticmethod
    def _overactive_comparable_counts(
        baseline_events: list[datetime],
        now: datetime,
        baseline_start: datetime | None = None,
        baseline_end: datetime | None = None,
    ) -> dict[str, float]:
        """Return baseline event counts comparable to current timing."""
        current_is_weekend = now.weekday() >= 5
        same_day_type_events = sum(
            1
            for event in baseline_events
            if (event.weekday() >= 5) == current_is_weekend
        )
        same_weekday_events = sum(
            1 for event in baseline_events if event.weekday() == now.weekday()
        )
        start = (baseline_start or min(baseline_events, default=now)).date()
        end = (baseline_end or now).date()
        counts_by_day: dict[date, int] = defaultdict(int)
        for event in baseline_events:
            counts_by_day[event.date()] += 1

        same_day_type_counts: list[float] = []
        same_weekday_counts: list[float] = []
        current = start
        while current < end:
            count = float(counts_by_day.get(current, 0))
            if (current.weekday() >= 5) == current_is_weekend:
                same_day_type_counts.append(count)
            if current.weekday() == now.weekday():
                same_weekday_counts.append(count)
            current += timedelta(days=1)

        same_day_type_active_days = sum(
            1 for count in same_day_type_counts if count > 0
        )
        same_weekday_active_days = sum(1 for count in same_weekday_counts if count > 0)
        same_day_type_active_counts = [
            count for count in same_day_type_counts if count > 0
        ]
        same_weekday_active_counts = [
            count for count in same_weekday_counts if count > 0
        ]
        same_day_type_p95 = _linear_percentile(same_day_type_active_counts, 0.95) or 0.0
        same_weekday_p95 = _linear_percentile(same_weekday_active_counts, 0.95) or 0.0
        required_overactive_count = (
            max(same_day_type_p95, same_weekday_p95) * 1.25
        ) + 1.0
        return {
            "same_day_type_events": float(same_day_type_events),
            "same_weekday_events": float(same_weekday_events),
            "same_day_type_active_days": float(same_day_type_active_days),
            "same_weekday_active_days": float(same_weekday_active_days),
            "same_day_type_p95_count": float(same_day_type_p95),
            "same_weekday_p95_count": float(same_weekday_p95),
            "required_overactive_count": float(required_overactive_count),
        }

    def _smoothed_score(
        self,
        automation_id: str,
        score: float,
        *,
        persisted_ema: float | None = None,
    ) -> float:
        history = self._score_history.setdefault(automation_id, [])
        if automation_id not in self._score_ema:
            if persisted_ema is not None:
                self._score_ema[automation_id] = max(0.0, float(persisted_ema))
                if not history:
                    history.append(self._score_ema[automation_id])
            elif history:
                # Reconstruct once from any pre-seeded history (tests / legacy).
                ema = history[0]
                for value in history[1:]:
                    ema = (self._score_ema_alpha * value) + (
                        (1 - self._score_ema_alpha) * ema
                    )
                self._score_ema[automation_id] = ema

        prev = self._score_ema.get(automation_id)
        base_threshold = self._score_threshold_for(automation_id)
        promotion_threshold = base_threshold + _OVERACTIVE_PROMOTION_MARGIN
        if (
            prev is not None
            and score < base_threshold
            and prev >= promotion_threshold
            and score <= prev * _EMA_RECOVERY_RATIO
        ):
            history.clear()
            history.append(score)
            self._score_ema[automation_id] = score
            return score

        if prev is None:
            ema = score
        else:
            ema = (self._score_ema_alpha * score) + ((1 - self._score_ema_alpha) * prev)

        history.append(score)
        if len(history) > self.score_ema_samples:
            del history[: -self.score_ema_samples]
        self._score_ema[automation_id] = ema
        return ema

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
            return min(required, _LOW_FREQUENCY_WARMUP_MINIMUM)
        return required

    @staticmethod
    def _within_historical_high_volume_envelope(
        *,
        recent_count: int,
        day_counts: list[int],
    ) -> bool:
        """Return true when recent activity is comparable to known busy days."""
        if recent_count <= 0 or not day_counts:
            return False
        historical_max = max(day_counts, default=0)
        if historical_max < _HISTORICAL_HIGH_VOLUME_MIN_DAILY_COUNT:
            return False
        tolerated_max = max(historical_max + 1, int(historical_max * 1.10))
        return recent_count <= tolerated_max

    def _observed_coverage_days(
        self,
        *,
        now: datetime,
    ) -> float | None:
        """Return best-known observed coverage age in days for maturity checks."""
        parsed = self._observed_coverage_start()
        if parsed is None:
            return None
        return max(0.0, (now - parsed).total_seconds() / 86400)

    def _observed_coverage_start(self) -> datetime | None:
        """Return persisted event-store observation start timestamp when available."""
        if self._runtime_event_store is None:
            return None
        try:
            stored_start = self._runtime_event_store.get_metadata(
                _EVENT_STORE_OBS_START_KEY
            )
        except Exception:
            return None
        if stored_start is None:
            return None
        return self._coerce_datetime(stored_start)

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
            return _DEFAULT_MEDIAN_GAP_MINUTES
        sorted_events = sorted(events)
        gaps = [
            (sorted_events[idx] - sorted_events[idx - 1]).total_seconds() / 60.0
            for idx in range(1, len(sorted_events))
        ]
        return max(_MIN_MEDIAN_GAP_MINUTES, float(median(gaps)))

    def _build_overdue_profile(
        self,
        *,
        automation_events: list[datetime],
        now: datetime,
        baseline_start: datetime,
    ) -> dict[str, Any]:
        """Summarize 90-day timing regularity for overdue prediction."""
        baseline_events = sorted(
            ts
            for ts in automation_events
            if baseline_start <= ts < now and ts.date() != now.date()
        )
        total_days = max(0, (now.date() - baseline_start.date()).days)
        full_weeks, remaining = divmod(total_days, 7)
        offset = (now.weekday() - baseline_start.date().weekday()) % 7
        comparable_days = full_weeks + (1 if offset < remaining else 0)
        comparable_events = [
            ts for ts in baseline_events if ts.weekday() == now.weekday()
        ]
        comparable_by_day: dict[date, list[datetime]] = defaultdict(list)
        for ts in comparable_events:
            comparable_by_day[ts.date()].append(ts)

        first_trigger_minutes = sorted(
            float(ts.hour * 60 + ts.minute + (ts.second / 60.0))
            for ts_list in comparable_by_day.values()
            for ts in [min(ts_list)]
        )
        last_trigger_minutes = sorted(
            float(ts.hour * 60 + ts.minute + (ts.second / 60.0))
            for ts_list in comparable_by_day.values()
            for ts in [max(ts_list)]
        )
        active_comparable_days = len(first_trigger_minutes)
        multi_run_comparable_days = sum(
            1 for ts_list in comparable_by_day.values() if len(ts_list) > 1
        )
        sorted_comparable_days = [
            sorted(ts_list) for ts_list in comparable_by_day.values()
        ]
        max_trigger_count = max(
            (len(ts_list) for ts_list in sorted_comparable_days),
            default=0,
        )
        trigger_minutes_by_index: list[list[float]] = []
        for trigger_index in range(max_trigger_count):
            trigger_minutes_by_index.append(
                sorted(
                    float(
                        ts_list[trigger_index].hour * 60
                        + ts_list[trigger_index].minute
                        + (ts_list[trigger_index].second / 60.0)
                    )
                    for ts_list in sorted_comparable_days
                    if len(ts_list) > trigger_index
                )
            )

        gap_days = [
            (baseline_events[idx] - baseline_events[idx - 1]).total_seconds() / 86400.0
            for idx in range(1, len(baseline_events))
        ]
        median_gap_days = float(median(gap_days)) if gap_days else None
        gap_p90_days = _linear_percentile(gap_days, 0.9)

        timing_spread = (
            (max(first_trigger_minutes) - min(first_trigger_minutes))
            if len(first_trigger_minutes) >= 2
            else 0.0
        )
        activity_ratio = (
            float(active_comparable_days) / float(comparable_days)
            if comparable_days > 0
            else 0.0
        )
        timing_consistency = max(0.0, 1.0 - min(1.0, timing_spread / 180.0))
        sample_strength = min(
            1.0,
            float(active_comparable_days) / float(_OVERDUE_MIN_COMPARABLE_ACTIVE_DAYS),
        )
        predictability_score = activity_ratio * (
            (0.6 * timing_consistency) + (0.4 * sample_strength)
        )
        is_predictable = (
            active_comparable_days >= _OVERDUE_MIN_COMPARABLE_ACTIVE_DAYS
            and predictability_score >= _OVERDUE_PREDICTABLE_SCORE_THRESHOLD
        )

        return {
            "comparable_days": float(comparable_days),
            "active_comparable_days": float(active_comparable_days),
            "first_trigger_median_minute": (
                float(median(first_trigger_minutes)) if first_trigger_minutes else None
            ),
            "first_trigger_p90_minute": _linear_percentile(first_trigger_minutes, 0.9),
            "first_trigger_minutes": first_trigger_minutes,
            "last_trigger_minutes": last_trigger_minutes,
            "trigger_minutes_by_index": trigger_minutes_by_index,
            "multi_run_comparable_days": float(multi_run_comparable_days),
            "median_gap_days": median_gap_days,
            "gap_p90_days": gap_p90_days,
            "predictability_score": float(predictability_score),
            "is_predictable": is_predictable,
        }

    def _predict_overdue(
        self,
        *,
        automation_events: list[datetime],
        now: datetime,
        baseline_start: datetime,
        overdue_probability_threshold: float = _OVERDUE_PROBABILITY_THRESHOLD,
    ) -> dict[str, float | str | bool | None]:
        """Return an overdue decision for predictable automations."""
        observed_days = max(0, (now.date() - baseline_start.date()).days)
        if (
            self.baseline_days < _BOOTSTRAP_MIN_HISTORY_DAYS
            or observed_days < _BOOTSTRAP_MIN_HISTORY_DAYS
        ):
            return {
                "status": "abstain",
                "overdue_probability": 0.0,
                "predictability_score": 0.0,
                "reason": "Overdue detection requires a full 90-day timing baseline.",
            }
        profile = self._build_overdue_profile(
            automation_events=automation_events,
            now=now,
            baseline_start=baseline_start,
        )
        today_events = sorted(
            ts for ts in automation_events if ts.date() == now.date() and ts <= now
        )
        comparable_days = max(1, int(float(profile["comparable_days"] or 0.0)))
        expected_trigger_index = len(today_events)
        repeated_run = expected_trigger_index > 0
        raw_trigger_windows = profile.get("trigger_minutes_by_index")
        trigger_windows: list[list[float]] = (
            cast(list[list[float]], raw_trigger_windows)
            if isinstance(raw_trigger_windows, list)
            else []
        )
        target_minutes: list[float] = (
            trigger_windows[expected_trigger_index]
            if expected_trigger_index < len(trigger_windows)
            else []
        )
        if today_events and not target_minutes:
            return {
                "status": "not_due",
                "overdue_probability": 0.0,
                "predictability_score": float(profile["predictability_score"] or 0.0),
                "comparable_days": float(comparable_days),
                "active_comparable_days": float(
                    profile["active_comparable_days"] or 0.0
                ),
                "usual_deadline": None,
                "expected_trigger_index": float(expected_trigger_index + 1),
                "reason": "Automation already fired today.",
            }

        active_comparable_days = len(target_minutes)
        timing_spread = (
            (max(target_minutes) - min(target_minutes))
            if len(target_minutes) >= 2
            else 0.0
        )
        activity_ratio = (
            float(active_comparable_days) / float(comparable_days)
            if comparable_days > 0
            else 0.0
        )
        timing_consistency = max(0.0, 1.0 - min(1.0, timing_spread / 180.0))
        sample_strength = min(
            1.0,
            float(active_comparable_days) / float(_OVERDUE_MIN_COMPARABLE_ACTIVE_DAYS),
        )
        predictability_score = activity_ratio * (
            (0.6 * timing_consistency) + (0.4 * sample_strength)
        )
        is_predictable = (
            active_comparable_days >= _OVERDUE_MIN_COMPARABLE_ACTIVE_DAYS
            and predictability_score >= _OVERDUE_PREDICTABLE_SCORE_THRESHOLD
        )

        if not is_predictable:
            return {
                "status": "abstain",
                "abstain_reason": "unpredictable",
                "overdue_probability": 0.0,
                "predictability_score": predictability_score,
                "comparable_days": float(comparable_days),
                "active_comparable_days": float(active_comparable_days),
                "usual_deadline": None,
                "expected_trigger_index": float(expected_trigger_index + 1),
                "reason": "Automation history is not predictable enough for overdue assessment.",
            }

        now_minute = float(now.hour * 60 + now.minute + (now.second / 60.0))
        p_active_today_type = float(active_comparable_days) / float(comparable_days)
        p_fired_by_now = float(
            sum(1 for minute in target_minutes if minute <= now_minute)
        ) / float(active_comparable_days)
        overdue_probability = p_active_today_type * p_fired_by_now

        median_minute = float(median(target_minutes))
        p90_minute = float(_linear_percentile(target_minutes, 0.9) or median_minute)
        spread_minutes = max(0.0, p90_minute - median_minute)
        grace_minutes = max(15.0, min(90.0, spread_minutes + 15.0))
        deadline_minute = min((24.0 * 60.0) - 1.0, p90_minute + grace_minutes)

        if now_minute < deadline_minute:
            return {
                "status": "not_due",
                "overdue_probability": overdue_probability,
                "predictability_score": predictability_score,
                "comparable_days": float(comparable_days),
                "active_comparable_days": float(active_comparable_days),
                "not_due_reason": "next_window_open",
                "usual_deadline": (
                    f"{int(deadline_minute // 60):02d}:{int(deadline_minute % 60):02d}"
                ),
                "expected_trigger_index": float(expected_trigger_index + 1),
                "repeated_run": repeated_run,
                "reason": (
                    f"Typical {now.strftime('%A')} firing window remains open until about "
                    f"{int(deadline_minute // 60):02d}:{int(deadline_minute % 60):02d}."
                ),
            }
        if overdue_probability < overdue_probability_threshold:
            return {
                "status": "abstain",
                "overdue_probability": overdue_probability,
                "overdue_probability_threshold": overdue_probability_threshold,
                "predictability_score": predictability_score,
                "comparable_days": float(comparable_days),
                "active_comparable_days": float(active_comparable_days),
                "usual_deadline": (
                    f"{int(deadline_minute // 60):02d}:{int(deadline_minute % 60):02d}"
                ),
                "expected_trigger_index": float(expected_trigger_index + 1),
                "repeated_run": repeated_run,
                "reason": "Comparable history is still too weak to call this overdue with confidence.",
            }

        deadline_hour = int(deadline_minute // 60)
        deadline_remainder = int(deadline_minute % 60)
        return {
            "status": "overdue",
            "overdue_probability": overdue_probability,
            "overdue_probability_threshold": overdue_probability_threshold,
            "predictability_score": predictability_score,
            "comparable_days": float(comparable_days),
            "active_comparable_days": float(active_comparable_days),
            "usual_deadline": f"{deadline_hour:02d}:{deadline_remainder:02d}",
            "expected_trigger_index": float(expected_trigger_index + 1),
            "repeated_run": repeated_run,
            "reason": (
                f"Automation usually fires by {deadline_hour:02d}:{deadline_remainder:02d} "
                f"on {now.strftime('%A')} and has not run yet."
            ),
        }

    @staticmethod
    def _build_5m_bucket_index(
        all_events_by_automation: dict[str, list[datetime]],
    ) -> dict[datetime, set[str]]:
        """Build an index mapping 5-minute bucket starts to automation IDs with events."""
        index: dict[datetime, set[str]] = defaultdict(set)
        for automation_id, events in all_events_by_automation.items():
            for ts in events:
                bucket_start = ts.replace(
                    minute=(ts.minute // _BUCKET_GRANULARITY_MINUTES)
                    * _BUCKET_GRANULARITY_MINUTES,
                    second=0,
                    microsecond=0,
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
    def _count_comparable_bucket_days(
        *,
        bucket_name: str,
        start: datetime,
        end: datetime,
    ) -> int:
        """Count comparable calendar days for the current bucket in a range."""
        if end <= start:
            return 0

        current = start.date()
        end_date = end.date()
        comparable_days = 0
        while current < end_date:
            if RuntimeHealthMonitor._bucket_matches_day_type(bucket_name, current):
                comparable_days += 1
            current += timedelta(days=1)
        return comparable_days

    @staticmethod
    def _bucket_daypart(bucket_name: str) -> str:
        """Return daypart suffix from bucket name."""
        if "_" not in bucket_name:
            return bucket_name
        return bucket_name.split("_", 1)[1]

    @staticmethod
    def _bucket_label(bucket_name: str) -> str:
        """Return human-friendly label for a bucket name."""
        return bucket_name.replace("_", " ")

    @staticmethod
    def _count_matching_days(
        *,
        start: datetime,
        end: datetime,
        predicate: Callable[[date], bool],
    ) -> int:
        """Count calendar days in [start, end) matching the predicate."""
        if end <= start:
            return 0

        current = start.date()
        end_date = end.date()
        matching_days = 0
        while current < end_date:
            if predicate(current):
                matching_days += 1
            current += timedelta(days=1)
        return matching_days

    @staticmethod
    def _build_bucket_baseline_context(
        *,
        now: datetime,
        baseline_events: list[datetime],
        baseline_window_start: datetime,
    ) -> dict[str, Any]:
        """Build comparable time-context baseline with conservative fallback."""
        current_bucket = classify_time_bucket(now)
        current_daypart = RuntimeHealthMonitor._bucket_daypart(current_bucket)
        current_weekday = now.weekday()

        strategies: list[
            tuple[str, str, Callable[[datetime], bool], Callable[[date], bool]]
        ] = [
            (
                "same_weekday_daypart",
                f"{now.strftime('%A')} {current_daypart}",
                lambda ts: (
                    ts.weekday() == current_weekday
                    and RuntimeHealthMonitor._bucket_daypart(classify_time_bucket(ts))
                    == current_daypart
                ),
                lambda day: day.weekday() == current_weekday,
            ),
            (
                "same_day_type_daypart",
                RuntimeHealthMonitor._bucket_label(current_bucket),
                lambda ts: (
                    RuntimeHealthMonitor._bucket_matches_day_type(
                        current_bucket, ts.date()
                    )
                    and RuntimeHealthMonitor._bucket_daypart(classify_time_bucket(ts))
                    == current_daypart
                ),
                lambda day: RuntimeHealthMonitor._bucket_matches_day_type(
                    current_bucket, day
                ),
            ),
            (
                "same_daypart",
                current_daypart,
                lambda ts: (
                    RuntimeHealthMonitor._bucket_daypart(classify_time_bucket(ts))
                    == current_daypart
                ),
                lambda _day: True,
            ),
            (
                "same_day_type",
                "weekend" if now.weekday() >= 5 else "weekday",
                lambda ts: RuntimeHealthMonitor._bucket_matches_day_type(
                    current_bucket, ts.date()
                ),
                lambda day: RuntimeHealthMonitor._bucket_matches_day_type(
                    current_bucket, day
                ),
            ),
            (
                "global",
                "all history",
                lambda _ts: True,
                lambda _day: True,
            ),
        ]

        minimum_samples = {
            "same_weekday_daypart": 2,
            "same_day_type_daypart": 2,
            "same_daypart": 2,
            "same_day_type": 1,
            "global": 1,
        }

        for strategy, label, event_matcher, day_matcher in strategies:
            matched_events = [ts for ts in baseline_events if event_matcher(ts)]
            comparable_days = RuntimeHealthMonitor._count_matching_days(
                start=baseline_window_start,
                end=now,
                predicate=day_matcher,
            )
            if (
                len(matched_events) >= minimum_samples.get(strategy, 1)
                and comparable_days > 0
            ):
                expected_count = float(len(matched_events)) / float(comparable_days)
                return {
                    "strategy": strategy,
                    "context_label": label,
                    "bucket_name": current_bucket,
                    "matched_event_count": len(matched_events),
                    "comparable_days": comparable_days,
                    "expected_count": expected_count,
                }

        return {
            "strategy": "global",
            "context_label": "all history",
            "bucket_name": current_bucket,
            "matched_event_count": 0,
            "comparable_days": 0,
            "expected_count": 0.0,
        }

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

        bucket_context = RuntimeHealthMonitor._build_bucket_baseline_context(
            now=now,
            baseline_events=baseline_30d,
            baseline_window_start=baseline_window_start,
        )
        bucket_expected_30d = RuntimeHealthMonitor._coerce_float(
            bucket_context.get("expected_count"),
            0.0,
        )
        bucket_ratio_30d = (
            current_hour_count / bucket_expected_30d
            if bucket_expected_30d > 0
            else current_hour_count
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
            "bucket_expected_30d": bucket_expected_30d,
            "bucket_ratio_30d": bucket_ratio_30d,
            "gap_vs_median": gap_vs_median,
            "is_weekend": 1.0 if now.weekday() >= 5 else 0.0,
            "weekday": float(now.weekday()),
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
                chunk_size = _RECORDER_QUERY_CHUNK_SIZE
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
    ) -> _RuntimeHistoryFetchResult:
        """Fetch trigger history from local runtime event store."""
        if self._async_runtime_event_store is None:
            return _RuntimeHistoryFetchResult(
                history={automation_id: [] for automation_id in automation_ids},
                failed_automation_ids=frozenset(),
            )
        history: dict[str, list[datetime]] = {}
        failed_automation_ids: set[str] = set()
        read_failure_count = 0
        for automation_id in automation_ids:
            try:
                epochs = await self._async_runtime_event_store.async_get_events(
                    automation_id,
                    start,
                    end,
                )
            except Exception as err:
                self._runtime_event_store_read_failures += 1
                read_failure_count += 1
                failed_automation_ids.add(automation_id)
                self._runtime_event_store_degraded = True
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
        return _RuntimeHistoryFetchResult(
            history=history,
            failed_automation_ids=frozenset(failed_automation_ids),
            read_failure_count=read_failure_count,
        )
