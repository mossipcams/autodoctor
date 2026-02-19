"""Gap detector tests for runtime health monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.autodoctor.models import IssueType
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
    assert "cadence_profile" not in gap_state
    assert "recent_gaps_minutes" not in gap_state
    assert "safe_gap_windows" not in gap_state


def test_hourly_gap_check_emits_gap_issue_when_elapsed_exceeds_expected_gap(
    tmp_path: Path,
) -> None:
    """Hourly gap check should alert when BOCPD-derived threshold is exceeded."""
    now = datetime(2026, 2, 18, 9, 30, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.gap_alert"

    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(hours=8)
    ).isoformat()

    # Build BOCPD baseline: 5 events/day for 10 days in weekday_morning bucket
    count_model = automation_state["count_model"]
    bucket_state = monitor._ensure_count_bucket_state(count_model, "weekday_morning")
    for _ in range(10):
        monitor._bocpd_count_detector.update_state(bucket_state, 5)
    bucket_state["current_day"] = now.date().isoformat()
    bucket_state["current_count"] = 0

    gap_issues = monitor.check_gap_anomalies(now=now)

    assert gap_issues
    assert gap_issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_SILENT
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


def test_gap_alert_clears_after_recovery_trigger(tmp_path: Path) -> None:
    """Active gap alerts should clear once a new trigger closes the elapsed gap."""
    now = datetime(2026, 2, 18, 9, 30, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.gap_recovery"

    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(hours=8)
    ).isoformat()
    count_model = automation_state["count_model"]
    bucket_state = monitor._ensure_count_bucket_state(count_model, "weekday_morning")
    for _ in range(10):
        monitor._bocpd_count_detector.update_state(bucket_state, 5)
    bucket_state["current_day"] = now.date().isoformat()
    bucket_state["current_count"] = 0

    gap_issues = monitor.check_gap_anomalies(now=now)
    assert gap_issues
    assert any(
        issue.issue_type == IssueType.RUNTIME_AUTOMATION_SILENT
        for issue in monitor.get_active_runtime_alerts()
    )

    monitor.ingest_trigger_event(aid, occurred_at=now)

    assert all(
        not (
            issue.automation_id == aid
            and issue.issue_type == IssueType.RUNTIME_AUTOMATION_SILENT
        )
        for issue in monitor.get_active_runtime_alerts()
    )


def test_gap_check_uses_bocpd_expected_rate_for_threshold(tmp_path: Path) -> None:
    """Gap check should derive threshold from BOCPD expected_rate in current bucket."""
    now = datetime(2026, 2, 18, 9, 30, tzinfo=UTC)  # Wednesday morning
    monitor = _build_monitor(tmp_path, now, max_alerts_per_day=20)
    aid = "automation.bocpd_gap"

    automation_state = monitor._ensure_automation_state(aid)
    automation_state["gap_model"]["last_trigger"] = (
        now - timedelta(minutes=500)
    ).isoformat()

    # Feed 10 days of 2 events/day into BOCPD to build expected_rate ~2.0
    count_model = automation_state["count_model"]
    bucket_state = monitor._ensure_count_bucket_state(count_model, "weekday_morning")
    for _ in range(10):
        monitor._bocpd_count_detector.update_state(bucket_state, 2)
    bucket_state["current_day"] = now.date().isoformat()
    bucket_state["current_count"] = 0

    # Morning bucket is 7h (420min). expected_rate ~2.0 => expected_gap = 420/2 = 210m
    # threshold = 210 * 1.5 = 315m, elapsed = 500m > 315 => alert
    assert bucket_state["expected_rate"] > 1.0
    issues = monitor.check_gap_anomalies(now=now)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_SILENT


def test_bucket_duration_covers_all_dayparts(tmp_path: Path) -> None:
    """Every bucket produced by classify_time_bucket must have a duration entry."""
    from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor

    all_buckets = set()
    now = datetime(2026, 2, 16, 12, 0, tzinfo=UTC)  # Monday
    monitor = _build_monitor(tmp_path, now)
    # Sample every hour across a full week to hit all 8 buckets
    for day_offset in range(7):
        for hour in range(24):
            ts = datetime(2026, 2, 16 + day_offset, hour, 30, tzinfo=UTC)
            all_buckets.add(monitor.classify_time_bucket(ts))

    missing = all_buckets - set(RuntimeHealthMonitor._BUCKET_DURATION_MINUTES.keys())
    assert not missing, f"Buckets missing duration entries: {missing}"


def test_gap_threshold_uses_correct_per_bucket_duration(tmp_path: Path) -> None:
    """Morning (7h) and afternoon (5h) should produce different gap thresholds."""
    # Morning: 05:00-12:00 = 420 min
    morning_now = datetime(2026, 2, 18, 9, 30, tzinfo=UTC)  # Wednesday morning
    monitor_m = _build_monitor(tmp_path, morning_now, max_alerts_per_day=20)
    aid = "automation.bucket_dur"

    auto_m = monitor_m._ensure_automation_state(aid)
    cm_m = auto_m["count_model"]
    bs_m = monitor_m._ensure_count_bucket_state(cm_m, "weekday_morning")
    for _ in range(10):
        monitor_m._bocpd_count_detector.update_state(bs_m, 2)
    bs_m["current_day"] = morning_now.date().isoformat()
    bs_m["current_count"] = 0
    rate_m = bs_m["expected_rate"]

    # Afternoon: 12:00-17:00 = 300 min
    afternoon_now = datetime(2026, 2, 18, 14, 30, tzinfo=UTC)  # Wednesday afternoon
    monitor_a = _build_monitor(tmp_path, afternoon_now, max_alerts_per_day=20)

    auto_a = monitor_a._ensure_automation_state(aid)
    cm_a = auto_a["count_model"]
    bs_a = monitor_a._ensure_count_bucket_state(cm_a, "weekday_afternoon")
    for _ in range(10):
        monitor_a._bocpd_count_detector.update_state(bs_a, 2)
    bs_a["current_day"] = afternoon_now.date().isoformat()
    bs_a["current_count"] = 0
    rate_a = bs_a["expected_rate"]

    # Same expected_rate but different bucket durations => different expected_gap
    assert abs(rate_m - rate_a) < 0.1, "Rates should be similar for same input"

    # Morning expected_gap = 420 / rate, afternoon = 300 / rate
    # The ratio should be ~420/300 = 1.4x
    # Set last_trigger so that elapsed is between the two thresholds:
    # afternoon threshold = (300 / ~2.0) * 1.5 = ~225m
    # morning threshold = (420 / ~2.0) * 1.5 = ~315m
    # Use elapsed = 280m: should alert for afternoon but NOT for morning
    auto_m["gap_model"]["last_trigger"] = (
        morning_now - timedelta(minutes=280)
    ).isoformat()
    auto_a["gap_model"]["last_trigger"] = (
        afternoon_now - timedelta(minutes=280)
    ).isoformat()

    issues_m = monitor_m.check_gap_anomalies(now=morning_now)
    issues_a = monitor_a.check_gap_anomalies(now=afternoon_now)

    assert len(issues_a) == 1, "Afternoon (5h bucket) should alert at 280m elapsed"
    assert len(issues_m) == 0, "Morning (7h bucket) should NOT alert at 280m elapsed"


def test_ingest_trigger_increments_dow_counts(tmp_path: Path) -> None:
    """ingest_trigger_event should track per-day-of-week firing counts."""
    # Wednesday = weekday 2
    wednesday = datetime(2026, 2, 18, 10, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, wednesday, max_alerts_per_day=20)
    aid = "automation.dow_test"

    monitor.ingest_trigger_event(aid, occurred_at=wednesday)
    monitor.ingest_trigger_event(aid, occurred_at=wednesday + timedelta(minutes=10))

    state = monitor._runtime_state["automations"][aid]
    dow_counts = state.get("dow_counts")
    assert dow_counts is not None, "dow_counts should exist in automation state"
    assert dow_counts.get(2, 0) == 2, "Wednesday (dow=2) should have 2 events"
    assert dow_counts.get(0, 0) == 0, "Monday should have 0 events"


def test_gap_check_skips_day_with_no_historical_activity(tmp_path: Path) -> None:
    """Gap check should not flag an automation on a day-of-week it has never fired."""
    # Wednesday = dow 2; set up automation that only fires Mon/Fri
    wednesday_3am = datetime(2026, 2, 18, 3, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, wednesday_3am, max_alerts_per_day=20)
    aid = "automation.weekday_sporadic"

    automation_state = monitor._ensure_automation_state(aid)
    # Simulate historical Mon(0) and Fri(4) triggers only
    automation_state["dow_counts"] = {0: 10, 4: 8}
    automation_state["gap_model"]["last_trigger"] = (
        wednesday_3am - timedelta(hours=48)
    ).isoformat()

    # Give it a nonzero expected_rate so the existing rate check doesn't skip it
    count_model = automation_state["count_model"]
    bucket_state = monitor._ensure_count_bucket_state(count_model, "weekday_night")
    for _ in range(10):
        monitor._bocpd_count_detector.update_state(bucket_state, 5)
    bucket_state["current_day"] = wednesday_3am.date().isoformat()
    bucket_state["current_count"] = 0

    gap_issues = monitor.check_gap_anomalies(now=wednesday_3am)

    assert gap_issues == [], (
        "Should not flag gap on Wednesday when automation only fires Mon/Fri"
    )


def test_gap_check_still_flags_on_active_dow(tmp_path: Path) -> None:
    """Gap check should still flag when automation has history on current dow."""
    # Wednesday = dow 2; automation fires on Wed
    wednesday_morning = datetime(2026, 2, 18, 9, 30, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, wednesday_morning, max_alerts_per_day=20)
    aid = "automation.active_wed"

    automation_state = monitor._ensure_automation_state(aid)
    automation_state["dow_counts"] = {2: 15}  # fires on Wednesdays
    automation_state["gap_model"]["last_trigger"] = (
        wednesday_morning - timedelta(hours=8)
    ).isoformat()

    count_model = automation_state["count_model"]
    bucket_state = monitor._ensure_count_bucket_state(count_model, "weekday_morning")
    for _ in range(10):
        monitor._bocpd_count_detector.update_state(bucket_state, 5)
    bucket_state["current_day"] = wednesday_morning.date().isoformat()
    bucket_state["current_count"] = 0

    gap_issues = monitor.check_gap_anomalies(now=wednesday_morning)

    assert len(gap_issues) == 1, (
        "Should flag gap on Wednesday when automation has Wednesday history"
    )
