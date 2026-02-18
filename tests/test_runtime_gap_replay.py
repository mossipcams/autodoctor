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
