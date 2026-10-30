"""Regression test: a failed SQLite write must not leave the store's transaction open."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.autodoctor.runtime_event_store import RuntimeEventStore


def test_failed_write_rolls_back_so_later_writes_persist(tmp_path: Path) -> None:
    """After a failed trigger write, the connection is clean and later writes succeed."""
    db_path = tmp_path / "autodoctor_runtime.db"
    store = RuntimeEventStore(db_path)
    store.ensure_schema(target_version=1)

    with sqlite3.connect(db_path) as raw:
        raw.execute(
            """
            CREATE TRIGGER fail_broken_trigger
            BEFORE INSERT ON trigger_events
            WHEN NEW.automation_id = 'broken'
            BEGIN
                SELECT RAISE(ABORT, 'simulated disk failure');
            END
            """
        )

    ts = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
    with pytest.raises(sqlite3.DatabaseError, match="simulated disk failure"):
        store.record_trigger("broken", ts)

    assert store._conn.in_transaction is False

    store.record_trigger("healthy", ts)
    store.close()

    reopened = RuntimeEventStore(db_path)
    try:
        assert reopened.count_events("healthy") == 1
    finally:
        reopened.close()
