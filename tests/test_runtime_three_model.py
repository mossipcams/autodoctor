"""Three-model runtime health monitor tests (count, gap, burst foundations)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.autodoctor.models import IssueType
from custom_components.autodoctor.runtime_event_store import RuntimeEventStore
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(
    tmp_path: Path, now: datetime, **kwargs: object
) -> RuntimeHealthMonitor:
    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())

    async def _mock_executor(func, *args):
        return func(*args)

    hass.async_add_executor_job = _mock_executor
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
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
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    ]
    assert count_issues, "Expected at least one count anomaly issue"
    assert "expected range" in count_issues[0].message.lower()
    assert "observed" in count_issues[0].message.lower()


def test_count_alert_clears_when_observation_returns_to_expected_range(
    tmp_path: Path,
) -> None:
    """Active count alerts should clear once counts return to expected range."""
    now = datetime(2026, 2, 20, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        sensitivity="high",
        burst_multiplier=999.0,
        max_alerts_per_day=20,
    )
    aid = "automation.count_recovery"
    automation_state = monitor._ensure_automation_state(aid)
    count_model = automation_state["count_model"]
    bucket_name = "weekday_morning"
    bucket_state = monitor._ensure_count_bucket_state(count_model, bucket_name)

    for _ in range(20):
        monitor._bocpd_count_detector.update_state(bucket_state, 1)
    bucket_state["current_day"] = now.date().isoformat()
    bucket_state["current_count"] = 10

    emitted = monitor._detect_count_anomaly(
        automation_entity_id=aid,
        automation_state=automation_state,
        bucket_name=bucket_name,
        bucket_state=bucket_state,
        now=now,
    )
    assert emitted
    assert any(
        issue.automation_id == aid
        and issue.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
        for issue in monitor.get_active_runtime_alerts()
    )

    bucket_state["current_count"] = 1
    monitor._detect_count_anomaly(
        automation_entity_id=aid,
        automation_state=automation_state,
        bucket_name=bucket_name,
        bucket_state=bucket_state,
        now=now + timedelta(minutes=1),
    )

    assert all(
        not (
            issue.automation_id == aid
            and issue.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
        )
        for issue in monitor.get_active_runtime_alerts()
    )


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


def test_suppressed_runtime_paths_continue_learning_without_alerts(
    tmp_path: Path,
) -> None:
    """Suppressed runtime alerts should still update runtime model baselines."""
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
    assert "automation.suppressed" in state["automations"]
    assert monitor.get_active_runtime_alerts() == []


def test_out_of_order_runtime_events_do_not_backdate_last_trigger(
    tmp_path: Path,
) -> None:
    """Older trigger timestamps should be ignored to keep model state monotonic."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, burst_multiplier=999.0)
    aid = "automation.out_of_order"

    newer = now
    older = now - timedelta(minutes=30)
    monitor.ingest_trigger_event(aid, occurred_at=newer)
    monitor.ingest_trigger_event(aid, occurred_at=older)

    state = monitor.get_runtime_state()
    gap_last_trigger = state["automations"][aid]["gap_model"]["last_trigger"]
    assert gap_last_trigger == newer.isoformat()

    bucket = state["automations"][aid]["count_model"]["buckets"][
        monitor.classify_time_bucket(newer)
    ]
    assert bucket["current_day"] == newer.date().isoformat()
    assert bucket["current_count"] == 1


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


def test_rebuild_models_from_store_populates_bocpd_from_sqlite(
    tmp_path: Path,
) -> None:
    """rebuild_models_from_store should replay SQLite daily counts into BOCPD."""
    now = datetime(2026, 2, 12, 12, 0, tzinfo=UTC)  # Thursday noon
    store = RuntimeEventStore(str(tmp_path / "autodoctor_runtime.db"))
    store.ensure_schema(target_version=1)

    aid = "automation.kitchen"
    base = datetime(2026, 2, 9, 8, 0, tzinfo=UTC)  # Monday 8am
    # Mon: 1 trigger, Tue: 2 triggers, Wed: 3 triggers
    for day_offset in range(3):
        for minute in range(day_offset + 1):
            store.record_trigger(
                aid,
                base + timedelta(days=day_offset, minutes=minute),
            )

    monitor = _build_monitor(tmp_path, now, runtime_event_store=store)
    monitor.rebuild_models_from_store(now=now)

    state = monitor.get_runtime_state()
    bucket = state["automations"][aid]["count_model"]["buckets"]["weekday_morning"]
    assert bucket["observations"] == [1, 2, 3]
    assert bucket["current_day"] == now.date().isoformat()
    assert bucket["current_count"] == 0

    # Gap model should have last_trigger seeded from store
    last_trigger = state["automations"][aid]["gap_model"]["last_trigger"]
    assert last_trigger is not None


@pytest.mark.asyncio
async def test_bootstrap_from_recorder_populates_sqlite_when_empty(
    tmp_path: Path,
) -> None:
    """One-time recorder bootstrap should bulk-import events into empty SQLite."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    store = RuntimeEventStore(str(tmp_path / "autodoctor_runtime.db"))
    store.ensure_schema(target_version=1)

    monitor = _build_monitor(tmp_path, now, runtime_event_store=store)

    history: dict[str, list[datetime]] = {
        "automation.kitchen": [
            now - timedelta(days=3, hours=2),
            now - timedelta(days=2, hours=2),
            now - timedelta(days=1, hours=2),
        ],
    }
    monitor._async_fetch_trigger_history = AsyncMock(return_value=history)  # type: ignore[method-assign]

    await monitor.async_bootstrap_from_recorder(
        [{"id": "kitchen", "entity_id": "automation.kitchen"}],
    )

    assert store.count_events("automation.kitchen") == 3
    assert store.get_metadata("bootstrap:complete") == "true"


@pytest.mark.asyncio
async def test_bootstrap_from_recorder_skips_when_already_complete(
    tmp_path: Path,
) -> None:
    """Bootstrap should skip if metadata flag is already set."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    store = RuntimeEventStore(str(tmp_path / "autodoctor_runtime.db"))
    store.ensure_schema(target_version=1)
    store.set_metadata("bootstrap:complete", "true")

    monitor = _build_monitor(tmp_path, now, runtime_event_store=store)
    monitor._async_fetch_trigger_history = AsyncMock()  # type: ignore[method-assign]

    await monitor.async_bootstrap_from_recorder(
        [{"id": "kitchen", "entity_id": "automation.kitchen"}],
    )

    monitor._async_fetch_trigger_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_from_recorder_uses_executor_for_store_calls(
    tmp_path: Path,
) -> None:
    """Bootstrap store I/O must be offloaded via async_add_executor_job."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    store = RuntimeEventStore(str(tmp_path / "autodoctor_runtime.db"))
    store.ensure_schema(target_version=1)

    monitor = _build_monitor(tmp_path, now, runtime_event_store=store)

    history: dict[str, list[datetime]] = {
        "automation.kitchen": [
            now - timedelta(days=2, hours=2),
            now - timedelta(days=1, hours=2),
        ],
    }
    monitor._async_fetch_trigger_history = AsyncMock(return_value=history)  # type: ignore[method-assign]

    executor_calls: list[object] = []

    async def tracking_executor(func, *args):
        executor_calls.append(func)
        return func(*args)

    monitor.hass.async_add_executor_job = tracking_executor

    await monitor.async_bootstrap_from_recorder(
        [{"id": "kitchen", "entity_id": "automation.kitchen"}],
    )

    assert store.count_events("automation.kitchen") == 2
    assert len(executor_calls) > 0, (
        "Store I/O in bootstrap must go through async_add_executor_job"
    )
