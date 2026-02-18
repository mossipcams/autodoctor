"""Gap detector tests for runtime health monitoring."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

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
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_gap_state.json")
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


def test_gap_model_stores_last_trigger_only(tmp_path: Path) -> None:
    """Gap model should retain only last trigger timestamp in BOCPD mode."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now)
    aid = "automation.gap_model"

    timestamps = [
        now - timedelta(minutes=60),
        now - timedelta(minutes=45),
        now - timedelta(minutes=30),
        now - timedelta(minutes=15),
    ]
    for ts in timestamps:
        monitor.ingest_trigger_event(aid, occurred_at=ts)

    state = monitor.get_runtime_state()
    gap_state = state["automations"][aid]["gap_model"]
    assert gap_state["last_trigger"] == timestamps[-1].isoformat()
    assert "intervals_minutes" not in gap_state
    assert "lambda_per_minute" not in gap_state
    assert "p99_minutes" not in gap_state


def test_hourly_gap_check_emits_gap_issue_when_elapsed_exceeds_expected_gap(
    tmp_path: Path,
) -> None:
    """Hourly gap check should alert when elapsed gap exceeds learned expected gap."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.gap_alert"

    # Train with regular 10-minute intervals.
    for idx in range(8):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(minutes=(80 - (idx * 10))),
        )

    gap_issues = monitor.check_gap_anomalies(now=now + timedelta(hours=2))

    assert gap_issues
    assert gap_issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP
    assert "expected gap" in gap_issues[0].message.lower()


def test_hourly_gap_check_respects_runtime_suppression(tmp_path: Path) -> None:
    """Hourly gap checks should skip suppressed automations."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.gap_suppressed"

    for idx in range(8):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(minutes=(80 - (idx * 10))),
        )

    suppression_store = MagicMock()
    suppression_store.is_suppressed.return_value = True
    monitor.hass.data = {"autodoctor": {"suppression_store": suppression_store}}

    gap_issues = monitor.check_gap_anomalies(now=now + timedelta(hours=2))

    assert gap_issues == []


def test_gap_check_skips_weekday_for_weekend_only_automation(tmp_path: Path) -> None:
    """Weekend-only automations should not alert on weekday inactivity windows."""
    now = datetime(2026, 2, 17, 18, 51, tzinfo=UTC)  # Tuesday
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.weekend_only"

    # Two weekend cycles that include late-night Sunday activity crossing midnight.
    # This models weekend schedules whose last run can land on Monday 00:00.
    for weekend_start in (
        datetime(2026, 2, 7, 6, 0, tzinfo=UTC),
        datetime(2026, 2, 14, 6, 0, tzinfo=UTC),
    ):
        for idx in range(8):
            monitor.ingest_trigger_event(
                aid,
                occurred_at=weekend_start + timedelta(hours=idx * 6),
            )

    gap_issues = monitor.check_gap_anomalies(now=now)

    assert gap_issues == []


def test_gap_check_uses_interarrival_model_for_daily_automations(
    tmp_path: Path,
) -> None:
    """Daily schedules should not alert mid-day when the next daily run is not due."""
    now = datetime(2026, 2, 13, 8, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.daily_schedule"

    # Train with one trigger per day at the same hour.
    for day in range(10):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(days=(9 - day)),
        )

    no_issue = monitor.check_gap_anomalies(now=now + timedelta(hours=12))
    late_issue = monitor.check_gap_anomalies(now=now + timedelta(hours=40))

    assert no_issue == []
    assert late_issue
    assert late_issue[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


def test_gap_check_handles_recurring_inactive_windows_for_morning_cluster(
    tmp_path: Path,
) -> None:
    """Recurring morning-only sessions should not alert during normal evening idle."""
    now = datetime(2026, 2, 17, 20, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.morning_cluster"

    # Train with morning-only clustered runs (06:00, 07:00, 08:00).
    for day in range(10):
        base = (now - timedelta(days=(9 - day))).replace(
            hour=6,
            minute=0,
            second=0,
            microsecond=0,
        )
        for hour_offset in (0, 1, 2):
            monitor.ingest_trigger_event(
                aid,
                occurred_at=base + timedelta(hours=hour_offset),
            )

    no_issue = monitor.check_gap_anomalies(now=now)
    late_issue = monitor.check_gap_anomalies(now=now + timedelta(hours=30))

    assert no_issue == []
    assert late_issue
    assert late_issue[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


def test_gap_check_handles_recurring_overnight_windows_for_daytime_hourly(
    tmp_path: Path,
) -> None:
    """Daytime-hourly schedules should tolerate overnight quiet windows."""
    train_now = datetime(2026, 2, 17, 20, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, train_now, max_alerts_per_day=20)
    aid = "automation.daytime_hourly"

    # Train with hourly daytime runs (08:00-20:00) and nightly inactivity.
    for day in range(10):
        base = (train_now - timedelta(days=(9 - day))).replace(
            hour=8,
            minute=0,
            second=0,
            microsecond=0,
        )
        for hour_offset in range(13):
            monitor.ingest_trigger_event(
                aid,
                occurred_at=base + timedelta(hours=hour_offset),
            )

    no_issue = monitor.check_gap_anomalies(now=datetime(2026, 2, 18, 5, 0, tzinfo=UTC))
    late_issue = monitor.check_gap_anomalies(
        now=datetime(2026, 2, 18, 16, 0, tzinfo=UTC)
    )

    assert no_issue == []
    assert late_issue
    assert late_issue[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


def test_gap_check_single_long_gap_does_not_desensitize_model(
    tmp_path: Path,
) -> None:
    """A one-off long gap should not be treated as recurring expected cadence."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.single_long_gap"

    start = now - timedelta(hours=6)
    for idx in range(18):
        offset_minutes = idx * 10
        if idx >= 8:
            # Inject one 180-minute interruption between idx=7 and idx=8.
            offset_minutes += 180
        monitor.ingest_trigger_event(
            aid,
            occurred_at=start + timedelta(minutes=offset_minutes),
        )

    issues = monitor.check_gap_anomalies(now=now + timedelta(hours=2))

    assert issues
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


def test_gap_alert_clears_after_recovery_trigger(tmp_path: Path) -> None:
    """Active gap alerts should clear once a new trigger closes the elapsed gap."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.gap_recovery"

    for idx in range(8):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(minutes=(80 - (idx * 10))),
        )

    gap_issues = monitor.check_gap_anomalies(now=now + timedelta(hours=2))
    assert gap_issues
    assert any(
        issue.issue_type == IssueType.RUNTIME_AUTOMATION_GAP
        for issue in monitor.get_active_runtime_alerts()
    )

    monitor.ingest_trigger_event(aid, occurred_at=now + timedelta(hours=2))

    assert all(
        not (
            issue.automation_id == aid
            and issue.issue_type == IssueType.RUNTIME_AUTOMATION_GAP
        )
        for issue in monitor.get_active_runtime_alerts()
    )


def test_gap_check_logs_summary_counters(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Gap checks should log evaluated/alerted/suppressed/cleared counters."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.gap_log_summary"

    for idx in range(8):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(minutes=(80 - (idx * 10))),
        )

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        gap_issues = monitor.check_gap_anomalies(now=now + timedelta(hours=2))

    assert gap_issues
    assert "Runtime gap check summary" in caplog.text
    assert "evaluated=1" in caplog.text
    assert "alerted=1" in caplog.text
    assert "suppressed=0" in caplog.text
