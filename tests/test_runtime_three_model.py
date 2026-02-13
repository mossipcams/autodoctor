"""Three-model runtime health monitor tests (count, gap, burst foundations)."""

from __future__ import annotations

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
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_state.json")
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        telemetry_db_path=None,
        runtime_state_store=store,
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


def test_count_model_tracks_alpha_beta_and_dispersion_metrics(tmp_path: Path) -> None:
    """Per-bucket count model should maintain posterior and variance metrics."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, burst_multiplier=999.0)

    aid = "automation.kitchen"
    base_day = datetime(2026, 2, 9, 8, 0, tzinfo=UTC)
    # Monday: 2 triggers
    monitor.ingest_trigger_event(aid, occurred_at=base_day)
    monitor.ingest_trigger_event(aid, occurred_at=base_day + timedelta(minutes=10))
    # Tuesday: 4 triggers
    for idx in range(4):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=base_day + timedelta(days=1, minutes=idx * 3),
        )
    # Wednesday event rolls Tuesday into historical counts
    monitor.ingest_trigger_event(aid, occurred_at=base_day + timedelta(days=2))

    state = monitor.get_runtime_state()
    bucket = state["automations"][aid]["count_model"]["buckets"]["weekday_morning"]

    assert bucket["alpha"] == pytest.approx(7.0)
    assert bucket["beta"] == pytest.approx(3.0)
    assert bucket["mean"] == pytest.approx(3.0)
    assert bucket["variance"] > 0
    assert bucket["vmr"] > 0


def test_count_anomaly_emits_runtime_issue_with_expected_range_metadata(
    tmp_path: Path,
) -> None:
    """Count anomaly path should emit range-aware runtime issue messages."""
    now = datetime(2026, 2, 20, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        sensitivity="high",
        burst_multiplier=999.0,
        max_alerts_per_day=20,
    )
    aid = "automation.count_watch"

    # Build a stable historical bucket baseline (1 trigger/day).
    for days_back in range(14, 1, -1):
        monitor.ingest_trigger_event(
            aid,
            occurred_at=now - timedelta(days=days_back),
        )

    emitted = []
    for idx in range(12):
        emitted.extend(
            monitor.ingest_trigger_event(
                aid,
                occurred_at=now + timedelta(seconds=idx),
            )
        )

    count_issues = [
        issue
        for issue in emitted
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_COUNT_ANOMALY
    ]
    assert count_issues, "Expected at least one count anomaly issue"
    assert "expected range" in count_issues[0].message.lower()
    assert "observed" in count_issues[0].message.lower()


def test_negative_binomial_promotion_triggers_when_vmr_is_high(tmp_path: Path) -> None:
    """Buckets with sustained over-dispersion should promote to NB scoring mode."""
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

    monitor.run_weekly_maintenance(now=now)

    state = monitor.get_runtime_state()
    bucket = state["automations"][aid]["count_model"]["buckets"]["weekday_morning"]
    assert bucket["vmr"] > 1.5
    assert bucket["use_negative_binomial"] is True


def test_record_issue_dismissed_increases_threshold_multiplier(tmp_path: Path) -> None:
    """Dismissals should increase learned threshold multiplier for adaptation loop."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now, dismissed_threshold_multiplier=1.5)
    aid = "automation.dismissed"

    assert monitor._dismissed_multiplier(aid) == pytest.approx(1.0)
    monitor.record_issue_dismissed(aid)
    assert monitor._dismissed_multiplier(aid) == pytest.approx(1.5)
    monitor.record_issue_dismissed(aid)
    assert monitor._dismissed_multiplier(aid) == pytest.approx(2.25)


def test_auto_adapt_resets_bucket_after_persistent_count_anomalies(
    tmp_path: Path,
) -> None:
    """Persistent count anomalies should trigger auto-adapt baseline reset."""
    now = datetime(2026, 2, 20, 9, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        sensitivity="high",
        smoothing_window=2,
        auto_adapt=True,
        burst_multiplier=999.0,
        max_alerts_per_day=50,
    )
    aid = "automation.auto_adapt"

    for days_back in range(15, 1, -1):
        monitor.ingest_trigger_event(aid, occurred_at=now - timedelta(days=days_back))

    for idx in range(8):
        monitor.ingest_trigger_event(aid, occurred_at=now + timedelta(seconds=idx))

    state = monitor.get_runtime_state()
    bucket = state["automations"][aid]["count_model"]["buckets"]["weekday_morning"]
    assert bucket["counts"] == []
    assert state["automations"][aid]["count_model"]["anomaly_streak"] == 0


def test_suppressed_runtime_paths_are_excluded_from_learning(tmp_path: Path) -> None:
    """Suppressed runtime alerts should skip model learning updates."""
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
    assert "automation.suppressed" not in state["automations"]
