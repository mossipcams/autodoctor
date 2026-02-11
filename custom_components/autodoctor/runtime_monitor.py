"""Runtime health monitoring for automation trigger behavior."""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import fmean
from typing import Any, Protocol, cast

from .models import IssueType, Severity, ValidationIssue

_LOGGER = logging.getLogger(__name__)

try:
    from river import anomaly
except ImportError:  # pragma: no cover - environment-dependent
    anomaly = None

_HAS_RIVER: bool = anomaly is not None


class _Detector(Protocol):
    """Anomaly detector interface for runtime monitoring."""

    def score_current(
        self, automation_id: str, train_rows: list[dict[str, float]]
    ) -> float:
        """Train from history rows and return anomaly score for the current row."""
        ...


class _RiverAnomalyDetector:
    """River-backed detector with watermark-based incremental learning.

    Persists a model per automation and tracks how many training rows
    have already been learned, so subsequent calls only learn new rows.
    If the row count shrinks (e.g. sliding window), the model resets.
    """

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._watermarks: dict[str, int] = {}

    def score_current(
        self, automation_id: str, train_rows: list[dict[str, float]]
    ) -> float:
        if len(train_rows) < 2:
            return 0.0

        if not _HAS_RIVER:  # pragma: no cover - guarded by constructor call
            raise RuntimeError("River is unavailable")

        training = train_rows[:-1]
        watermark = self._watermarks.get(automation_id, 0)

        # Reset if history shrank (sliding window shifted)
        if watermark > len(training):
            watermark = 0
            self._models.pop(automation_id, None)

        model = self._models.get(automation_id)
        if model is None:
            assert anomaly is not None  # guaranteed by _HAS_RIVER check above
            model = anomaly.HalfSpaceTrees(
                n_trees=15, height=8, window_size=256, seed=42
            )
            self._models[automation_id] = model

        for row in training[watermark:]:
            model.learn_one(row)
        self._watermarks[automation_id] = len(training)

        return float(model.score_one(train_rows[-1]))


class RuntimeHealthMonitor:
    """Detect runtime automation anomalies from recorder trigger history."""

    def __init__(
        self,
        hass: Any,
        *,
        baseline_days: int = 30,
        warmup_samples: int = 14,
        anomaly_threshold: float = 0.8,
        min_expected_events: int = 1,
        overactive_factor: float = 3.0,
        detector: _Detector | None = None,
        now_factory: Any = None,
    ) -> None:
        self.hass = hass
        self.baseline_days = baseline_days
        self.warmup_samples = warmup_samples
        self.anomaly_threshold = anomaly_threshold
        self.min_expected_events = min_expected_events
        self.overactive_factor = overactive_factor
        self._detector = detector or (_RiverAnomalyDetector() if _HAS_RIVER else None)
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._last_run_stats: dict[str, int] = {}

    def get_last_run_stats(self) -> dict[str, int]:
        """Return telemetry from the most recent run."""
        return dict(self._last_run_stats)

    async def validate_automations(
        self, automations: list[dict[str, Any]]
    ) -> list[ValidationIssue]:
        """Validate runtime trigger behavior for automations."""
        stats: dict[str, int] = defaultdict(int)
        stats["total_automations"] = len(automations)

        if self._detector is None:
            stats["river_unavailable"] = len(automations)
            self._last_run_stats = dict(stats)
            return []

        now = self._now_factory()
        recent_start = now - timedelta(hours=24)
        baseline_start = recent_start - timedelta(days=self.baseline_days)
        automation_ids = [
            f"automation.{a.get('id')}"
            for a in automations
            if isinstance(a.get("id"), str) and a.get("id")
        ]
        if not automation_ids:
            self._last_run_stats = dict(stats)
            return []

        history = await self._async_fetch_trigger_history(
            automation_ids,
            baseline_start,
            now,
        )

        issues: list[ValidationIssue] = []
        for automation in automations:
            raw_id = automation.get("id")
            if not isinstance(raw_id, str) or not raw_id:
                continue

            automation_id = f"automation.{raw_id}"
            automation_name = str(automation.get("alias", automation_id))
            timestamps = sorted(history.get(automation_id, []))

            baseline_events = [
                t for t in timestamps if baseline_start <= t < recent_start
            ]
            recent_events = [t for t in timestamps if recent_start <= t <= now]
            day_counts = self._build_daily_counts(
                baseline_events, baseline_start, recent_start
            )
            expected = fmean(day_counts) if day_counts else 0.0
            active_days = sum(1 for c in day_counts if c > 0)

            if active_days < self.warmup_samples:
                stats["insufficient_warmup"] += 1
                continue

            if expected < float(self.min_expected_events):
                stats["insufficient_baseline"] += 1
                continue

            train_rows = self._build_training_rows(day_counts, baseline_start)
            current_row = self._build_current_row(recent_events, expected, now)
            train_rows.append(current_row)
            score = self._detector.score_current(automation_id, train_rows)

            recent_count = len(recent_events)
            if recent_count == 0 and score >= self.anomaly_threshold:
                stats["stalled_detected"] += 1
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=automation_id,
                        location="runtime.health",
                        message=(
                            f"Automation appears stalled: 0 triggers in last 24h, "
                            f"baseline expected {expected:.1f}/day (anomaly score {score:.2f})"
                        ),
                        issue_type=IssueType.RUNTIME_AUTOMATION_STALLED,
                        confidence="medium",
                    )
                )
                continue

            if (
                recent_count > expected * self.overactive_factor
                and score >= self.anomaly_threshold
            ):
                stats["overactive_detected"] += 1
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=automation_id,
                        location="runtime.health",
                        message=(
                            f"Automation trigger rate is abnormally high: {recent_count} "
                            f"triggers in last 24h vs baseline {expected:.1f}/day "
                            f"(anomaly score {score:.2f})"
                        ),
                        issue_type=IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
                        confidence="medium",
                    )
                )

        self._last_run_stats = dict(stats)
        return issues

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

    @staticmethod
    def _build_training_rows(
        day_counts: list[int],
        baseline_start: datetime,
    ) -> list[dict[str, float]]:
        rows: list[dict[str, float]] = []
        for idx, count in enumerate(day_counts):
            day_dt = baseline_start + timedelta(days=idx)
            rows.append(
                {
                    "count_24h": float(count),
                    "dow_sin": math.sin(2 * math.pi * (day_dt.weekday() / 7.0)),
                    "dow_cos": math.cos(2 * math.pi * (day_dt.weekday() / 7.0)),
                }
            )
        return rows

    @staticmethod
    def _build_current_row(
        recent_events: list[datetime],
        expected_daily: float,
        now: datetime,
    ) -> dict[str, float]:
        return {
            "count_24h": float(len(recent_events)),
            "dow_sin": math.sin(2 * math.pi * (now.weekday() / 7.0)),
            "dow_cos": math.cos(2 * math.pi * (now.weekday() / 7.0)),
        }

    async def _async_fetch_trigger_history(
        self,
        automation_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[datetime]]:
        """Fetch automation trigger timestamps from recorder events table."""
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

        try:
            return await self.hass.async_add_executor_job(_query)
        except Exception as err:  # pragma: no cover - integration/runtime differences
            _LOGGER.debug(
                "Failed to query recorder events for runtime monitor: %s", err
            )
            return {aid: [] for aid in automation_ids}
