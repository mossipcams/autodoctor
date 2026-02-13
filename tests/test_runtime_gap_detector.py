"""Gap detector tests for runtime health monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.autodoctor.models import IssueType
from custom_components.autodoctor.runtime_health_state_store import (
    RuntimeHealthStateStore,
)
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(
    tmp_path: Path, now: datetime, **kwargs: object
) -> RuntimeHealthMonitor:
    hass = MagicMock()
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


def test_gap_model_updates_lambda_and_p99_from_intervals(tmp_path: Path) -> None:
    """Gap model should derive lambda and p99 threshold from rolling intervals."""
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
    assert gap_state["lambda_per_minute"] > 0
    assert gap_state["p99_minutes"] > 0


def test_hourly_gap_check_emits_gap_issue_when_elapsed_exceeds_p99(
    tmp_path: Path,
) -> None:
    """Hourly gap check should alert when elapsed gap exceeds learned p99."""
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
    assert "p99" in gap_issues[0].message.lower()
