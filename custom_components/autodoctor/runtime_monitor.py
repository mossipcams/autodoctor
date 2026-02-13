"""Runtime health monitoring for automation trigger behavior."""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from statistics import fmean, median
from typing import Any, Protocol, cast

from .const import DOMAIN
from .models import IssueType, Severity, ValidationIssue

_LOGGER = logging.getLogger(__name__)
_TELEMETRY_RETENTION_DAYS = 90


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
        anomaly_threshold: float = 0.8,
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
        if suppression_store is None:
            data: dict[str, Any] = (
                self.hass.data.get(DOMAIN, {}) if hasattr(self.hass, "data") else {}
            )
            suppression_store = data.get("suppression_store")
        if suppression_store is None:
            return 1.0

        prefixes = (
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_STALLED.value}",
            f"{automation_id}:{automation_id}:{IssueType.RUNTIME_AUTOMATION_OVERACTIVE.value}",
        )
        for prefix in prefixes:
            if suppression_store.is_suppressed(prefix):
                return self.dismissed_threshold_multiplier
        return 1.0

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
