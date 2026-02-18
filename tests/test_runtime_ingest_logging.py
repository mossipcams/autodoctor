"""Verify runtime ingest emits debug logging on successful event processing."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.autodoctor.runtime_health_state_store import (
    RuntimeHealthStateStore,
)
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def _build_monitor(tmp_path: Path, now: datetime) -> RuntimeHealthMonitor:
    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_state.json")
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        runtime_state_store=store,
        telemetry_db_path=None,
        warmup_samples=0,
        min_expected_events=0,
    )


def test_ingest_trigger_logs_completion(tmp_path: Path, caplog: object) -> None:
    """Successful ingest should emit a TEMP DEBUG log confirming completion."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(tmp_path, now)

    with caplog.at_level(logging.DEBUG):  # type: ignore[union-attr]
        monitor.ingest_trigger_event(
            "automation.test_auto",
            occurred_at=now,
        )

    assert any(
        "[TEMP DEBUG] ingest complete" in rec.message
        and "automation.test_auto" in rec.message
        for rec in caplog.records  # type: ignore[union-attr]
    ), f"Expected '[TEMP DEBUG] ingest complete' log, got: {[r.message for r in caplog.records]}"  # type: ignore[union-attr]
