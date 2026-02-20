"""Three-model runtime health monitor tests (count, gap, burst foundations)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def test_weekly_maintenance_is_noop_with_bocpd(tmp_path: Path) -> None:
    """Weekly maintenance should not mutate burst model internals."""
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

    before_burst = before["automations"][aid]["burst_model"]
    after_burst = after["automations"][aid]["burst_model"]
    assert after_burst == before_burst


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
    last_trigger = state["automations"][aid]["last_trigger"]
    assert last_trigger == newer.isoformat()


def test_async_backfill_from_recorder_removed(tmp_path: Path) -> None:
    """async_backfill_from_recorder was removed — replaced by async_bootstrap_from_recorder."""
    assert not hasattr(RuntimeHealthMonitor, "async_backfill_from_recorder")


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
