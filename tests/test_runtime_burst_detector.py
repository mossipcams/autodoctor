"""Burst detector tests for runtime health monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.autodoctor.models import IssueType, Severity
from tests.conftest import build_runtime_monitor


def test_burst_detector_emits_immediate_critical_issue() -> None:
    """Rapid trigger spikes should emit immediate burst runtime issues."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = build_runtime_monitor(
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
    evidence = max(
        (issue.to_dict()["evidence"] for issue in burst_issues),
        key=lambda item: item["observed_5m_count"],
    )
    assert evidence["observed_5m_count"] >= 6
    assert evidence["baseline_5m_count"] > 0
    assert evidence["threshold"] > 0
    assert evidence["window_minutes"] == 5


def test_burst_ignores_triggers_during_startup_recovery() -> None:
    """Rapid startup triggers should not produce burst alerts."""
    started_at = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = build_runtime_monitor(
        started_at,
        startup_recovery_minutes=5,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.startup_burst"

    emitted = []
    for second in range(6):
        emitted.extend(
            monitor.ingest_trigger_event(
                aid,
                occurred_at=started_at + timedelta(minutes=2, seconds=second),
            )
        )

    assert [
        issue
        for issue in emitted
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST
    ] == []


def test_burst_requires_mature_baseline_before_error() -> None:
    """Fresh automations should not emit burst errors before a baseline exists."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = build_runtime_monitor(
        now,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.immature_burst"

    emitted = []
    for second in range(6):
        emitted.extend(
            monitor.ingest_trigger_event(
                aid,
                occurred_at=now + timedelta(seconds=second),
            )
        )

    assert [
        issue
        for issue in emitted
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST
    ] == []


def test_burst_alert_clears_after_quiet_period() -> None:
    """Active burst alerts should clear after traffic returns to normal."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = build_runtime_monitor(
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
