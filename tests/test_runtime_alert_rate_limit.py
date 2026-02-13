"""Runtime alert rate limiting tests."""

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
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_alert_limits.json")
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        runtime_state_store=store,
        telemetry_db_path=None,
        warmup_samples=0,
        min_expected_events=0,
        **kwargs,
    )


def test_rate_limit_enforces_per_automation_daily_cap(tmp_path: Path) -> None:
    """Per-automation daily cap should block additional alerts after limit."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        max_alerts_per_day=1,
        global_alert_cap_per_day=10,
    )

    assert monitor._allow_alert("automation.kitchen", now=now) is True
    assert (
        monitor._allow_alert("automation.kitchen", now=now + timedelta(minutes=1))
        is False
    )


def test_rate_limit_enforces_global_daily_cap(tmp_path: Path) -> None:
    """Global daily cap should stop alerts across automations once exhausted."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        max_alerts_per_day=10,
        global_alert_cap_per_day=2,
    )

    assert monitor._allow_alert("automation.a", now=now) is True
    assert monitor._allow_alert("automation.b", now=now + timedelta(minutes=1)) is True
    assert monitor._allow_alert("automation.c", now=now + timedelta(minutes=2)) is False


def test_rate_limit_counters_reset_on_new_day(tmp_path: Path) -> None:
    """Per-automation and global counters should reset when the date rolls over."""
    now = datetime(2026, 2, 13, 23, 59, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        max_alerts_per_day=1,
        global_alert_cap_per_day=1,
    )

    assert monitor._allow_alert("automation.a", now=now) is True
    assert (
        monitor._allow_alert("automation.a", now=now + timedelta(seconds=10)) is False
    )

    tomorrow = now + timedelta(minutes=2)
    assert monitor._allow_alert("automation.a", now=tomorrow) is True
