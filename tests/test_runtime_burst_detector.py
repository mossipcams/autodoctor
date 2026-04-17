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
    assert burst_issues[0].message.startswith("Burst:")
    assert "baseline" in burst_issues[0].message
    assert "5m" in burst_issues[0].message


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


def test_burst_detector_respects_bucket_specific_baseline() -> None:
    """A historically busy bucket should require a higher burst threshold."""
    now = datetime(2026, 2, 16, 8, 30, tzinfo=UTC)  # Monday morning
    monitor = build_runtime_monitor(
        now,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.bucketed_burst"

    recent_triggers = [
        (now - timedelta(minutes=40 + idx)).isoformat() for idx in range(10)
    ] + [(now - timedelta(seconds=(idx * 20))).isoformat() for idx in range(6)]
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["burst_model"] = {
        "recent_triggers": recent_triggers,
        "baseline_rate_5m": 1.0,
        "baseline_rate_5m_by_bucket": {
            "weekday_morning": 4.0,
            "weekend_morning": 0.5,
        },
    }

    issues = monitor._detect_burst_anomaly(
        automation_entity_id=aid,
        automation_state=automation_state,
        now=now,
    )

    assert issues == []


def test_burst_detector_falls_back_to_global_baseline_when_bucket_is_quiet() -> None:
    """Off-schedule spikes should still alert when bucket baseline is missing or low."""
    now = datetime(2026, 2, 15, 8, 30, tzinfo=UTC)  # Sunday morning
    monitor = build_runtime_monitor(
        now,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.off_schedule_burst"

    recent_triggers = [
        (now - timedelta(minutes=40 + idx)).isoformat() for idx in range(10)
    ] + [(now - timedelta(seconds=(idx * 20))).isoformat() for idx in range(6)]
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["burst_model"] = {
        "recent_triggers": recent_triggers,
        "baseline_rate_5m": 1.0,
        "baseline_rate_5m_by_bucket": {
            "weekday_morning": 4.0,
        },
    }

    issues = monitor._detect_burst_anomaly(
        automation_entity_id=aid,
        automation_state=automation_state,
        now=now,
    )

    assert any(
        issue.issue_type == IssueType.RUNTIME_AUTOMATION_BURST for issue in issues
    )


def test_burst_detector_ignores_two_trigger_low_volume_window() -> None:
    """Two-trigger low-volume windows should not emit a burst alert."""
    now = datetime(2026, 2, 16, 8, 30, tzinfo=UTC)  # Monday morning
    monitor = build_runtime_monitor(
        now,
        burst_multiplier=2.0,
        max_alerts_per_day=20,
    )
    aid = "automation.low_volume_burst"

    recent_triggers = [
        (now - timedelta(minutes=59)).isoformat(),
        (now - timedelta(minutes=55)).isoformat(),
        (now - timedelta(minutes=45)).isoformat(),
        (now - timedelta(minutes=35)).isoformat(),
        (now - timedelta(minutes=15)).isoformat(),
        (now - timedelta(minutes=4, seconds=30)).isoformat(),
    ]
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["burst_model"] = {
        "recent_triggers": recent_triggers,
        "baseline_rate_5m": 0.26,
        "baseline_rate_5m_by_bucket": {
            "weekday_morning": 0.26,
        },
    }

    issues = monitor._detect_burst_anomaly(
        automation_entity_id=aid,
        automation_state=automation_state,
        now=now,
    )

    assert issues == []
