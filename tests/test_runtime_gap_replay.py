"""Replay-based runtime gap regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.autodoctor.runtime_health_state_store import (
    RuntimeHealthStateStore,
)
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(
    tmp_path: Path, now: datetime, **kwargs: object
) -> RuntimeHealthMonitor:
    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_gap_replay_state.json")
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        runtime_state_store=store,
        telemetry_db_path=None,
        warmup_samples=0,
        min_expected_events=0,
        burst_multiplier=999.0,
        **kwargs,
    )


def test_gap_replay_known_false_positive_set_suppressed_by_cadence_profile(
    tmp_path: Path,
) -> None:
    """Known hourly gap false positives should be suppressed by cadence metadata."""
    check_time = datetime(2026, 2, 18, 9, 41, 14, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, check_time, max_alerts_per_day=20)

    replay_snapshot = {
        "automation.charging": (274.5, 17.3),
        "automation.dryer_finished": (2595.5, 519.0),
        "automation.garage_door": (795.4, 204.0),
        "automation.home_security_cam_off": (797.5, 215.3),
        "automation.homethermostat": (797.5, 281.1),
        "automation.left_home": (910.6, 522.3),
        "automation.weekend_thermostat": (4186.5, 359.5),
    }

    for automation_id, (
        observed_gap_minutes,
        expected_gap_minutes,
    ) in replay_snapshot.items():
        automation_state = monitor._ensure_automation_state(automation_id)
        automation_state["gap_model"]["last_trigger"] = (
            check_time - timedelta(minutes=observed_gap_minutes)
        ).isoformat()
        automation_state["gap_model"]["expected_gap_minutes"] = expected_gap_minutes
        automation_state["gap_model"]["median_gap_minutes"] = expected_gap_minutes
        automation_state["gap_model"]["ewma_gap_minutes"] = expected_gap_minutes
        automation_state["gap_model"]["recent_gaps_minutes"] = [expected_gap_minutes]
        # Replay profile: these automations are active in specific windows only,
        # so this check window should be treated as ineligible for gap alerts.
        automation_state["gap_model"]["cadence_profile"] = {
            "version": 1,
            "inactive_weekdays": [2],
            "confidence": 0.95,
        }
        automation_state["count_model"]["buckets"] = {
            "weekday_morning": {
                "expected_rate": 1.0,
                "current_count": 1,
                "observations": [1, 1, 1, 1, 1],
                "run_length_probs": [1.0],
                "hazard": 0.1,
                "current_day": check_time.date().isoformat(),
            }
        }

    issues = monitor.check_gap_anomalies(now=check_time)

    assert issues == []


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
