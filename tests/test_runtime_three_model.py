"""Three-model runtime health monitor tests (count, gap, burst foundations)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.autodoctor.models import IssueType
from custom_components.autodoctor.runtime_health_state_store import (
    RuntimeHealthStateStore,
)
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(
    tmp_path: Path, now: datetime, **kwargs: object
) -> RuntimeHealthMonitor:
    hass = MagicMock()
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_state.json")
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        telemetry_db_path=None,
        runtime_state_store=store,
        warmup_samples=0,
        min_expected_events=0,
        **kwargs,
    )


def test_classify_time_bucket_returns_expected_segments(tmp_path: Path) -> None:
    """Bucket classifier should split weekday/weekend x daypart into 8 segments."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now)

    weekday_morning = datetime(2026, 2, 12, 8, 30, tzinfo=UTC)  # Thursday
    weekend_night = datetime(2026, 2, 14, 1, 15, tzinfo=UTC)  # Saturday

    assert monitor.classify_time_bucket(weekday_morning) == "weekday_morning"
    assert monitor.classify_time_bucket(weekend_night) == "weekend_night"


def test_count_model_updates_bocpd_state_on_day_rollover(tmp_path: Path) -> None:
    """Per-bucket count model should roll prior day count into BOCPD state."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, burst_multiplier=999.0)

    aid = "automation.kitchen"
    base_day = datetime(2026, 2, 9, 8, 0, tzinfo=UTC)
    # Monday: 2 triggers
    monitor.ingest_trigger_event(aid, occurred_at=base_day)
    monitor.ingest_trigger_event(aid, occurred_at=base_day + timedelta(minutes=10))
    # Tuesday: 4 triggers
    for idx in range(4):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=base_day + timedelta(days=1, minutes=idx * 3),
        )
    # Wednesday event rolls Tuesday into historical counts
    monitor.ingest_trigger_event(aid, occurred_at=base_day + timedelta(days=2))

    state = monitor.get_runtime_state()
    bucket = state["automations"][aid]["count_model"]["buckets"]["weekday_morning"]

    assert bucket["observations"] == [2, 4]
    assert bucket["current_count"] == 1
    assert bucket["current_day"] == (base_day + timedelta(days=2)).date().isoformat()
    assert sum(bucket["run_length_probs"]) == pytest.approx(1.0)
    assert bucket["map_run_length"] >= 0
    assert bucket["expected_rate"] > 0.0


def test_count_anomaly_emits_runtime_issue_with_expected_range_metadata(
    tmp_path: Path,
) -> None:
    """Count anomaly path should emit range-aware runtime issue messages."""
    now = datetime(2026, 2, 20, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        sensitivity="high",
        burst_multiplier=999.0,
        max_alerts_per_day=20,
    )
    aid = "automation.count_watch"

    # Build a stable historical bucket baseline (1 trigger/day).
    for days_back in range(14, 1, -1):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(days=days_back),
        )

    emitted = []
    for idx in range(12):
        emitted.extend(
            monitor.ingest_trigger_event(
                aid,
                occurred_at=now + timedelta(seconds=idx),
            )
        )

    count_issues = [
        issue
        for issue in emitted
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_COUNT_ANOMALY
    ]
    assert count_issues, "Expected at least one count anomaly issue"
    assert "expected range" in count_issues[0].message.lower()
    assert "observed" in count_issues[0].message.lower()


def test_weekly_maintenance_is_noop_with_bocpd(tmp_path: Path) -> None:
    """Weekly maintenance should not mutate BOCPD bucket internals."""
    now = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, burst_multiplier=999.0)
    aid = "automation.nb_watch"

    # Alternate sparse/dense days to force vmr > 1.5.
    cursor = now - timedelta(days=21)
    pattern = [0, 8, 1, 12, 0, 10, 2, 11, 1, 9]
    for daily_count in pattern:
        for minute in range(daily_count):
            monitor.ingest_trigger_event(
                aid, occurred_at=cursor + timedelta(minutes=minute)
            )
        cursor += timedelta(days=1)

    before = monitor.get_runtime_state()
    monitor.run_weekly_maintenance(now=now)
    after = monitor.get_runtime_state()

    before_bucket = before["automations"][aid]["count_model"]["buckets"][
        "weekday_morning"
    ]
    after_bucket = after["automations"][aid]["count_model"]["buckets"][
        "weekday_morning"
    ]
    assert after_bucket == before_bucket
    assert "use_negative_binomial" not in after_bucket


def test_record_issue_dismissed_increases_threshold_multiplier(tmp_path: Path) -> None:
    """Dismissals should increase learned threshold multiplier for adaptation loop."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, dismissed_threshold_multiplier=1.5)
    aid = "automation.dismissed"

    assert monitor._dismissed_multiplier(aid) == pytest.approx(1.0)
    monitor.record_issue_dismissed(aid)
    assert monitor._dismissed_multiplier(aid) == pytest.approx(1.5)
    monitor.record_issue_dismissed(aid)
    assert monitor._dismissed_multiplier(aid) == pytest.approx(2.25)


def test_auto_adapt_resets_bucket_after_persistent_count_anomalies(
    tmp_path: Path,
) -> None:
    """Persistent count anomalies should trigger auto-adapt baseline reset."""
    now = datetime(2026, 2, 20, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        sensitivity="high",
        smoothing_window=2,
        auto_adapt=True,
        burst_multiplier=999.0,
        max_alerts_per_day=50,
    )
    aid = "automation.auto_adapt"

    for days_back in range(15, 1, -1):
        monitor.ingest_trigger_event(aid, occurred_at=now - timedelta(days=days_back))

    for idx in range(8):
        monitor.ingest_trigger_event(aid, occurred_at=now + timedelta(seconds=idx))

    state = monitor.get_runtime_state()
    bucket = state["automations"][aid]["count_model"]["buckets"]["weekday_morning"]
    assert bucket["run_length_probs"] == [1.0]
    assert bucket["observations"] == []
    assert bucket["map_run_length"] == 0
    assert bucket["expected_rate"] == pytest.approx(0.0)
    assert state["automations"][aid]["count_model"]["anomaly_streak"] == 0


def test_suppressed_runtime_paths_are_excluded_from_learning(tmp_path: Path) -> None:
    """Suppressed runtime alerts should skip model learning updates."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now)
    suppression_store = MagicMock()
    suppression_store.is_suppressed.return_value = True

    monitor.ingest_trigger_event(
        "automation.suppressed",
        occurred_at=now,
        suppression_store=suppression_store,
    )

    state = monitor.get_runtime_state()
    assert "automation.suppressed" not in state["automations"]


@pytest.mark.asyncio
async def test_backfill_from_recorder_seeds_three_models_from_history(
    tmp_path: Path,
) -> None:
    """Backfill should seed count/gap/burst models when runtime state starts empty."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, burst_multiplier=999.0)

    history: dict[str, list[datetime]] = {
        "automation.kitchen": [
            now - timedelta(days=3, hours=2),
            now - timedelta(days=2, hours=2),
            now - timedelta(days=1, minutes=45),
            now - timedelta(days=1, minutes=25),
            now - timedelta(days=1, minutes=5),
        ],
        "automation.hallway": [
            now - timedelta(days=6, hours=1),
            now - timedelta(days=5, hours=1),
            now - timedelta(days=4, hours=1),
            now - timedelta(days=3, hours=1),
        ],
    }
    monitor._async_fetch_trigger_history = AsyncMock(return_value=history)  # type: ignore[method-assign]

    await monitor.async_backfill_from_recorder(
        [
            {"id": "kitchen", "entity_id": "automation.kitchen"},
            {"id": "hallway", "entity_id": "automation.hallway"},
        ],
        now=now,
    )

    state = monitor.get_runtime_state()
    kitchen_state = state["automations"]["automation.kitchen"]
    hallway_state = state["automations"]["automation.hallway"]

    assert kitchen_state["count_model"]["buckets"]
    assert hallway_state["count_model"]["buckets"]
    assert (
        kitchen_state["gap_model"]["last_trigger"]
        == history["automation.kitchen"][-1].isoformat()
    )
    assert (
        hallway_state["gap_model"]["last_trigger"]
        == history["automation.hallway"][-1].isoformat()
    )
    assert kitchen_state["burst_model"]["baseline_rate_5m"] > 0.0
    assert hallway_state["burst_model"]["baseline_rate_5m"] > 0.0


def test_gap_check_rolls_count_bucket_forward_without_new_live_event(
    tmp_path: Path,
) -> None:
    """Gap checks should finalize day buckets even when no new trigger arrives."""
    now = datetime(2026, 2, 11, 9, 0, tzinfo=UTC)  # Wednesday
    monitor = _build_monitor(
        tmp_path,
        now,
        burst_multiplier=999.0,
        gap_threshold_multiplier=999.0,
    )
    aid = "automation.sparse"
    first_event = datetime(2026, 2, 9, 8, 15, tzinfo=UTC)  # Monday

    monitor.ingest_trigger_event(aid, occurred_at=first_event)
    monitor.check_gap_anomalies(now=now)

    state = monitor.get_runtime_state()
    bucket_name = monitor.classify_time_bucket(first_event)
    bucket = state["automations"][aid]["count_model"]["buckets"][bucket_name]
    assert bucket["observations"] == [1, 0]
    assert bucket["current_day"] == now.date().isoformat()
    assert bucket["current_count"] == 0
