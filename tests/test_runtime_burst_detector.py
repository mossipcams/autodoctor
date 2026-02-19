"""Burst detector tests for runtime health monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.autodoctor.models import IssueType, Severity
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(
    tmp_path: Path, now: datetime, **kwargs: object
) -> RuntimeHealthMonitor:
    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        telemetry_db_path=None,
        warmup_samples=0,
        min_expected_events=0,
        **kwargs,
    )


def test_burst_detector_emits_immediate_critical_issue(tmp_path: Path) -> None:
    """Rapid trigger spikes should emit immediate burst runtime issues."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.burst_watch"

    # Train a low baseline rate (1 trigger per 5 minutes).
    for idx in range(12):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(minutes=(60 - (idx * 5))),
        )

    emitted = []
    for second in range(20):
        emitted.extend(
            monitor.ingest_trigger_event(
                aid,
                occurred_at=now + timedelta(seconds=second),
            )
        )

    burst_issues = [
        issue
        for issue in emitted
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST
    ]
    assert burst_issues
    assert burst_issues[0].severity == Severity.ERROR
    assert "5m" in burst_issues[0].message


def test_burst_alert_clears_after_quiet_period(tmp_path: Path) -> None:
    """Active burst alerts should clear after traffic returns to normal."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.burst_recovery"

    for idx in range(12):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(minutes=(60 - (idx * 5))),
        )

    emitted = []
    for second in range(20):
        emitted.extend(
            monitor.ingest_trigger_event(
                aid,
                occurred_at=now + timedelta(seconds=second),
            )
        )
    assert any(
        issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST for issue in emitted
    )
    assert any(
        issue.automation_id == aid
        and issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST
        for issue in monitor.get_active_runtime_alerts()
    )

    monitor.ingest_trigger_event(aid, occurred_at=now + timedelta(hours=2))

    assert all(
        not (
            issue.automation_id == aid
            and issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST
        )
        for issue in monitor.get_active_runtime_alerts()
    )
