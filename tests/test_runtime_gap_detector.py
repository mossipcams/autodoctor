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


def _next_weekday_after(
    base: datetime, target_weekday: int, *, hour: int = 12
) -> datetime:
    days_ahead = (target_weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    candidate = base + timedelta(days=days_ahead)
    return candidate.replace(hour=hour, minute=0, second=0, microsecond=0)


@pytest.mark.parametrize(
    ("active_weekdays", "inactive_weekday"),
    [
        ({0, 2, 4}, 1),
        ({2}, 1),
    ],
)
def test_gap_check_respects_learned_active_weekdays(
    tmp_path: Path,
    active_weekdays: set[int],
    inactive_weekday: int,
) -> None:
    """Gap checks should honor learned weekday cadence from recent history."""
    seed_now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, seed_now, max_alerts_per_day=20)
    aid = "automation.weekly_pattern"

    for days_back in range(30):
        ts = seed_now - timedelta(days=(29 - days_back))
        if ts.weekday() in active_weekdays:
            monitor.ingest_trigger_event(
                aid,
                occurred_at=ts.replace(hour=9, minute=0, second=0, microsecond=0),
            )

    baseline_check = seed_now + timedelta(days=14)
    outside_now = _next_weekday_after(baseline_check, inactive_weekday)
    inside_now = _next_weekday_after(
        outside_now,
        min(active_weekdays, key=lambda w: (w - outside_now.weekday()) % 7),
        hour=9,
    )

    no_issue = monitor.check_gap_anomalies(now=outside_now)
    # First check on active day may require confirmation; second call confirms.
    monitor.check_gap_anomalies(now=inside_now)
    late_issue = monitor.check_gap_anomalies(now=inside_now + timedelta(hours=1))

    assert no_issue == []
    assert late_issue
    assert late_issue[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


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


def test_gap_model_learns_weekday_cadence_profile_from_events(tmp_path: Path) -> None:
    """Gap model should learn active/inactive weekdays and confidence."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)  # Wednesday
    monitor = _build_monitor(tmp_path, now)
    aid = "automation.profile_learning"

    # 6 weeks of activity on Monday/Wednesday only.
    start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)  # Monday
    for week in range(6):
        monitor.ingest_trigger_event(aid, occurred_at=start + timedelta(days=7 * week))
        monitor.ingest_trigger_event(
            aid,
            occurred_at=start + timedelta(days=7 * week + 2),
        )

    state = monitor.get_runtime_state()
    profile = state["automations"][aid]["gap_model"]["cadence_profile"]

    assert set(profile["active_weekdays"]) == {0, 2}
    assert 1 in set(profile["inactive_weekdays"])
    assert profile["confidence"] >= 0.7


def test_gap_model_marks_low_confidence_when_history_is_sparse(tmp_path: Path) -> None:
    """Cadence profile confidence should stay low for very sparse event history."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now)
    aid = "automation.profile_sparse"

    monitor.ingest_trigger_event(aid, occurred_at=now - timedelta(days=2))
    monitor.ingest_trigger_event(aid, occurred_at=now - timedelta(days=1))

    state = monitor.get_runtime_state()
    profile = state["automations"][aid]["gap_model"]["cadence_profile"]

    assert profile["confidence"] < 0.7


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


def test_gap_check_suppresses_when_profile_marks_current_bucket_inactive(
    tmp_path: Path,
) -> None:
    """High-confidence cadence profile should suppress out-of-bucket gap alerts."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.bucket_profile_gate"
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=240)
    ).isoformat()
    automation_state["gap_model"]["expected_gap_minutes"] = 30.0
    automation_state["gap_model"]["cadence_profile"] = {
        "version": 1,
        "confidence": 0.95,
        "active_weekdays": [2],
        "inactive_weekdays": [],
        "active_buckets": ["weekday_night"],
        "enforce_active_buckets": True,
    }
    automation_state["count_model"]["buckets"] = {
        "weekday_morning": {
            "expected_rate": 1.0,
            "current_count": 1,
            "observations": [1, 1, 1, 1, 1],
            "run_length_probs": [1.0],
            "hazard": 0.1,
            "current_day": now.date().isoformat(),
        }
    }

    issues = monitor.check_gap_anomalies(now=now)

    assert issues == []


def test_gap_check_does_not_suppress_with_low_profile_confidence(
    tmp_path: Path,
) -> None:
    """Low-confidence profile should not suppress otherwise eligible gap alerts."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.low_conf_profile"
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=240)
    ).isoformat()
    automation_state["gap_model"]["expected_gap_minutes"] = 30.0
    automation_state["gap_model"]["cadence_profile"] = {
        "version": 1,
        "confidence": 0.3,
        "active_weekdays": [2],
        "inactive_weekdays": [2],
        "active_buckets": ["weekday_night"],
        "enforce_active_buckets": True,
    }
    automation_state["count_model"]["buckets"] = {
        "weekday_morning": {
            "expected_rate": 1.0,
            "current_count": 1,
            "observations": [1, 1, 1, 1, 1],
            "run_length_probs": [1.0],
            "hazard": 0.1,
            "current_day": now.date().isoformat(),
        }
    }

    first = monitor.check_gap_anomalies(now=now)
    second = monitor.check_gap_anomalies(now=now + timedelta(hours=1))

    assert first == []
    assert second
    assert second[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


def test_gap_check_requires_second_breach_when_profile_confidence_is_low(
    tmp_path: Path,
) -> None:
    """Low-confidence candidates should require a second consecutive breach."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.low_conf_confirmation"
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=240)
    ).isoformat()
    automation_state["gap_model"]["expected_gap_minutes"] = 30.0
    automation_state["gap_model"]["cadence_profile"] = {
        "version": 1,
        "confidence": 0.2,
        "active_weekdays": [2],
        "inactive_weekdays": [],
        "active_buckets": ["weekday_morning"],
    }
    automation_state["count_model"]["buckets"] = {
        "weekday_morning": {
            "expected_rate": 1.0,
            "current_count": 1,
            "observations": [1, 1, 1, 1, 1],
            "run_length_probs": [1.0],
            "hazard": 0.1,
            "current_day": now.date().isoformat(),
        }
    }

    first = monitor.check_gap_anomalies(now=now)
    second = monitor.check_gap_anomalies(now=now + timedelta(hours=1))

    assert first == []
    assert second
    assert second[0].issue_type == IssueType.RUNTIME_AUTOMATION_GAP


def test_gap_check_applies_dismissal_adaptation_to_threshold(
    tmp_path: Path,
) -> None:
    """Dismissals should raise the effective gap threshold for future checks."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)
    baseline_monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    adapted_monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.dismissal_gap"

    for monitor in (baseline_monitor, adapted_monitor):
        state = monitor._ensure_automation_state(aid)
        state["gap_model"]["last_trigger"] = (now - timedelta(minutes=50)).isoformat()
        state["gap_model"]["expected_gap_minutes"] = 30.0
        state["gap_model"]["cadence_profile"] = {
            "version": 1,
            "confidence": 1.0,
            "active_weekdays": [2],
            "inactive_weekdays": [],
            "active_buckets": ["weekday_morning"],
        }
        state["count_model"]["buckets"] = {
            "weekday_morning": {
                "expected_rate": 1.0,
                "current_count": 1,
                "observations": [1, 1, 1, 1, 1],
                "run_length_probs": [1.0],
                "hazard": 0.1,
                "current_day": now.date().isoformat(),
            }
        }

    baseline_issues = baseline_monitor.check_gap_anomalies(now=now)

    adapted_monitor.record_issue_dismissed(aid)
    adapted_issues = adapted_monitor.check_gap_anomalies(now=now)

    assert baseline_issues
    assert adapted_issues == []


def test_gap_dismissal_adaptation_decays_after_recovery_events(tmp_path: Path) -> None:
    """Gap-specific adaptation should decay back toward default on healthy activity."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.dismissal_decay"

    monitor.record_issue_dismissed(aid)
    monitor.record_issue_dismissed(aid)
    adaptation = monitor.get_runtime_state()["automations"][aid]["adaptation"]
    assert adaptation["gap_threshold_multiplier"] > 1.0
    assert adaptation["gap_confirmation_required"] >= 2

    # Healthy triggers should slowly relax dismissal adaptation.
    base = now + timedelta(minutes=1)
    for idx in range(8):
        monitor.ingest_trigger_event(
            aid, occurred_at=base + timedelta(minutes=idx * 10)
        )

    adaptation_after = monitor.get_runtime_state()["automations"][aid]["adaptation"]
    assert (
        adaptation_after["gap_threshold_multiplier"]
        <= adaptation["gap_threshold_multiplier"]
    )
    assert adaptation_after["gap_threshold_multiplier"] >= 1.0
    assert adaptation_after["gap_confirmation_required"] >= 1


def test_gap_check_suppresses_when_elapsed_is_within_recurring_safe_window(
    tmp_path: Path,
) -> None:
    """Known recurring safe windows should suppress gap alerts in matching context."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.safe_window"
    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=130)
    ).isoformat()
    automation_state["gap_model"]["expected_gap_minutes"] = 30.0
    automation_state["gap_model"]["cadence_profile"] = {
        "version": 1,
        "confidence": 1.0,
        "active_weekdays": [2],
        "inactive_weekdays": [],
        "active_buckets": ["weekday_morning"],
    }
    context_key = f"{now.weekday()}:{monitor.classify_time_bucket(now)}"
    automation_state["gap_model"]["safe_gap_windows"] = {
        context_key: {
            "samples": [92.0, 98.0, 104.0, 100.0],
            "p90_minutes": 104.0,
        }
    }
    automation_state["count_model"]["buckets"] = {
        "weekday_morning": {
            "expected_rate": 1.0,
            "current_count": 1,
            "observations": [1, 1, 1, 1, 1],
            "run_length_probs": [1.0],
            "hazard": 0.1,
            "current_day": now.date().isoformat(),
        }
    }

    issues = monitor.check_gap_anomalies(now=now)

    assert issues == []


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


def test_gap_check_logs_reason_coded_decisions(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Gap checks should log explicit decision reasons for alert/suppress paths."""
    now = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)

    suppressed_id = "automation.reason_suppressed"
    suppressed_state = monitor._ensure_automation_state(suppressed_id)
    suppressed_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=240)
    ).isoformat()
    suppressed_state["gap_model"]["expected_gap_minutes"] = 30.0
    suppressed_state["gap_model"]["cadence_profile"] = {
        "version": 1,
        "confidence": 0.95,
        "active_weekdays": [0, 4],  # Not Wednesday.
        "inactive_weekdays": [2],
        "active_buckets": ["weekday_morning"],
    }
    suppressed_state["count_model"]["buckets"] = {
        "weekday_morning": {
            "expected_rate": 1.0,
            "current_count": 1,
            "observations": [1, 1, 1, 1, 1],
            "run_length_probs": [1.0],
            "hazard": 0.1,
            "current_day": now.date().isoformat(),
        }
    }

    alerted_id = "automation.reason_alerted"
    alerted_state = monitor._ensure_automation_state(alerted_id)
    alerted_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=240)
    ).isoformat()
    alerted_state["gap_model"]["expected_gap_minutes"] = 30.0
    alerted_state["gap_model"]["cadence_profile"] = {
        "version": 1,
        "confidence": 1.0,
        "active_weekdays": [2],
        "inactive_weekdays": [],
        "active_buckets": ["weekday_morning"],
    }
    alerted_state["count_model"]["buckets"] = {
        "weekday_morning": {
            "expected_rate": 1.0,
            "current_count": 1,
            "observations": [1, 1, 1, 1, 1],
            "run_length_probs": [1.0],
            "hazard": 0.1,
            "current_day": now.date().isoformat(),
        }
    }

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        monitor.check_gap_anomalies(now=now)

    assert "Runtime gap decision" in caplog.text
    assert "reason=profile_inactive_weekday" in caplog.text
    assert "reason=alert_emitted" in caplog.text
