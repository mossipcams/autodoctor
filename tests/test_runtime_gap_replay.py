"""Replay-based runtime gap regression tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(
    tmp_path: Path, now: datetime, **kwargs: object
) -> RuntimeHealthMonitor:
    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        warmup_samples=0,
        min_expected_events=0,
        burst_multiplier=999.0,
        **kwargs,
    )


def test_catch_up_replays_days_in_chronological_order(tmp_path: Path) -> None:
    """catch_up_count_model should process finalized days in date order."""
    from custom_components.autodoctor.runtime_event_store import RuntimeEventStore

    automation_id = "automation.ordered_replay"
    store = RuntimeEventStore(tmp_path / "ordered_replay.db")
    store.ensure_schema(target_version=1)

    # Plant events: 1 on Feb 16 (Mon), 3 on Feb 17 (Tue) — weekday_morning
    timestamps = [
        datetime(2026, 2, 16, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 17, 8, 0, tzinfo=UTC),
        datetime(2026, 2, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
    ]
    store.bulk_import(automation_id, timestamps)
    store.rebuild_daily_summaries(automation_id)

    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now)

    automation_state = monitor._ensure_automation_state(automation_id)
    bucket_state = monitor._ensure_count_bucket_state(
        automation_state["count_model"], "weekday_morning"
    )
    bucket_state["current_day"] = "2026-02-15"
    bucket_state["current_count"] = 0
    bucket_state["observations"] = []

    monitor.catch_up_count_model(
        store=store,
        automation_id=automation_id,
        now=now,
    )

    updated = automation_state["count_model"]["buckets"]["weekday_morning"]
    # Feb 16 (Mon) = 1 event, Feb 17 (Tue) = 3 events — both weekday mornings.
    # Observations should be [1, 3] in that order.
    assert updated["observations"] == [1, 3]

    store.close()
