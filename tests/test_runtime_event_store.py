"""Tests for runtime event SQLite store."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from custom_components.autodoctor.runtime_event_store import (
    AsyncRuntimeEventStore,
    RuntimeEventStore,
)


@pytest.fixture
def store(tmp_path: Path) -> RuntimeEventStore:
    """Create a RuntimeEventStore with schema initialized, auto-closed on teardown."""
    db_path = tmp_path / "autodoctor_runtime.db"
    s = RuntimeEventStore(db_path)
    s.ensure_schema(target_version=1)
    yield s
    s.close()


def _table_exists(db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    return row is not None


def _index_exists(db_path: Path, index_name: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        ).fetchone()
    return row is not None


def test_ensure_schema_creates_required_tables_and_indexes(tmp_path: Path) -> None:
    """Runtime event store schema should include required tables and indexes."""
    db_path = tmp_path / "autodoctor_runtime.db"

    store = RuntimeEventStore(db_path)
    active_version = store.ensure_schema(target_version=1)
    store.close()

    assert active_version == 1
    assert _table_exists(db_path, "trigger_events")
    assert _table_exists(db_path, "score_history")
    assert _table_exists(db_path, "metadata")
    assert _table_exists(db_path, "daily_bucket_counts")
    assert _index_exists(db_path, "idx_trigger_events_time")
    assert _index_exists(db_path, "idx_trigger_events_bucket")


def test_ensure_schema_writes_migration_metadata(tmp_path: Path) -> None:
    """Schema ensure should persist migration status metadata keys."""
    db_path = tmp_path / "autodoctor_runtime.db"

    store = RuntimeEventStore(db_path)
    active_version = store.ensure_schema(target_version=1)

    assert active_version == 1
    assert store.get_metadata("schema_version") == "1"
    assert store.get_metadata("migration:state") == "idle"
    assert store.get_metadata("migration:target_version") == "1"
    assert store.get_metadata("migration:last_error") == ""
    assert store.get_metadata("migration:updated_at") is not None

    store.close()


def test_ensure_schema_unknown_target_marks_failed_without_downgrading(
    tmp_path: Path,
) -> None:
    """Unknown schema target should fail and preserve prior schema version."""
    db_path = tmp_path / "autodoctor_runtime.db"
    store = RuntimeEventStore(db_path)
    assert store.ensure_schema(target_version=1) == 1

    with pytest.raises(RuntimeError):
        store.ensure_schema(target_version=2)

    assert store.get_metadata("schema_version") == "1"
    assert store.get_metadata("migration:state") == "failed"
    last_error = store.get_metadata("migration:last_error")
    assert last_error is not None
    assert "target schema version" in last_error.lower()
    store.close()


def test_record_trigger_deduplicates_and_stores_bucket_metadata(
    tmp_path: Path, store: RuntimeEventStore
) -> None:
    """record_trigger should ignore duplicates and persist weekday/time bucket columns."""
    triggered_at = datetime(2026, 2, 18, 9, 15, tzinfo=UTC)  # Wednesday morning
    store.record_trigger("automation.kitchen_motion", triggered_at)
    store.record_trigger("automation.kitchen_motion", triggered_at)

    db_path = tmp_path / "autodoctor_runtime.db"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*), MIN(time_bucket), MIN(weekday)
            FROM trigger_events
            WHERE automation_id = ?
            """,
            ("automation.kitchen_motion",),
        ).fetchone()

    assert row is not None
    assert row[0] == 1
    assert row[1] == "weekday_morning"
    assert row[2] == 2


def test_bulk_import_inserts_and_reports_inserted_count(
    tmp_path: Path, store: RuntimeEventStore
) -> None:
    """bulk_import should insert unique timestamps and report inserted rows."""
    timestamps = [
        datetime(2026, 2, 18, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 18, 9, 5, tzinfo=UTC),
        datetime(2026, 2, 18, 9, 5, tzinfo=UTC),  # duplicate
        datetime(2026, 2, 18, 9, 10, tzinfo=UTC),
    ]

    inserted_first = store.bulk_import("automation.bulk", timestamps)
    inserted_second = store.bulk_import("automation.bulk", timestamps)

    db_path = tmp_path / "autodoctor_runtime.db"
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM trigger_events WHERE automation_id = ?",
            ("automation.bulk",),
        ).fetchone()

    assert inserted_first == 3
    assert inserted_second == 0
    assert count is not None
    assert count[0] == 3


def test_get_events_respects_time_filters_and_order(
    store: RuntimeEventStore,
) -> None:
    """get_events should return sorted epochs constrained by after/before bounds."""
    times = [
        datetime(2026, 2, 18, 8, 0, tzinfo=UTC),
        datetime(2026, 2, 18, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 18, 10, 0, tzinfo=UTC),
    ]
    store.bulk_import("automation.filtered", times)

    filtered = store.get_events(
        "automation.filtered",
        after=datetime(2026, 2, 18, 8, 30, tzinfo=UTC),
        before=datetime(2026, 2, 18, 9, 30, tzinfo=UTC),
    )

    assert filtered == [times[1].timestamp()]


def test_get_daily_counts_aggregates_by_date(store: RuntimeEventStore) -> None:
    """get_daily_counts should return per-day trigger totals for an automation."""
    store.record_trigger("automation.daily", datetime(2026, 2, 18, 9, 0, tzinfo=UTC))
    store.record_trigger("automation.daily", datetime(2026, 2, 18, 11, 0, tzinfo=UTC))
    store.record_trigger("automation.daily", datetime(2026, 2, 19, 9, 0, tzinfo=UTC))

    counts = store.get_daily_counts("automation.daily")

    assert counts == {"2026-02-18": 2, "2026-02-19": 1}


def test_last_trigger_ids_counts_and_has_data(store: RuntimeEventStore) -> None:
    """Basic read helpers should expose last trigger, ids, counts, and data presence."""
    store.record_trigger("automation.one", datetime(2026, 2, 18, 9, 0, tzinfo=UTC))
    store.record_trigger("automation.one", datetime(2026, 2, 18, 10, 0, tzinfo=UTC))
    store.record_trigger("automation.two", datetime(2026, 2, 19, 11, 0, tzinfo=UTC))

    assert (
        store.get_last_trigger("automation.one")
        == datetime(2026, 2, 18, 10, 0, tzinfo=UTC).timestamp()
    )
    assert store.get_last_trigger("automation.missing") is None
    assert store.count_events("automation.one") == 2
    assert store.count_events("automation.two") == 1
    assert store.has_data("automation.one") is True
    assert store.has_data("automation.none") is False
    assert store.get_automation_ids() == ["automation.one", "automation.two"]


def test_trim_deletes_rows_older_than_retention_days(store: RuntimeEventStore) -> None:
    """trim should remove events older than retention cutoff and keep newer rows."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    store.record_trigger("automation.trim", now - timedelta(days=120))
    store.record_trigger("automation.trim", now - timedelta(days=10))

    deleted = store.trim(retention_days=90, now=now)
    remaining = store.count_events("automation.trim")

    assert deleted == 1
    assert remaining == 1


def test_record_score_and_get_last_score(store: RuntimeEventStore) -> None:
    """Score history APIs should persist and return the latest score row."""
    t1 = datetime(2026, 2, 18, 9, 0, tzinfo=UTC)
    t2 = datetime(2026, 2, 18, 10, 0, tzinfo=UTC)
    store.record_score(
        "automation.score",
        scored_at=t1,
        score=0.5,
        ema_score=0.5,
        features={"rolling_24h_count": 3.0},
    )
    store.record_score(
        "automation.score",
        scored_at=t2,
        score=0.9,
        ema_score=0.7,
        features={"rolling_24h_count": 4.0},
    )

    last = store.get_last_score("automation.score")

    assert last is not None
    assert last.automation_id == "automation.score"
    assert last.scored_at == t2.timestamp()
    assert last.score == pytest.approx(0.9)
    assert last.ema_score == pytest.approx(0.7)
    assert last.features["rolling_24h_count"] == pytest.approx(4.0)


def test_migrate_legacy_runtime_health_scores_into_score_history(
    tmp_path: Path,
) -> None:
    """Legacy telemetry rows should migrate into score_history with parity checks."""
    runtime_db = tmp_path / "autodoctor_runtime.db"
    legacy_db = tmp_path / "autodoctor_runtime_health.sqlite"
    store = RuntimeEventStore(runtime_db)
    store.ensure_schema(target_version=1)

    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE runtime_health_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                automation_id TEXT NOT NULL,
                score REAL NOT NULL,
                features_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO runtime_health_scores (ts, automation_id, score, features_json)
            VALUES (?, ?, ?, ?)
            """,
            ("2026-02-18T09:00:00+00:00", "automation.a", 0.3, '{"f":1}'),
        )
        conn.execute(
            """
            INSERT INTO runtime_health_scores (ts, automation_id, score, features_json)
            VALUES (?, ?, ?, ?)
            """,
            ("2026-02-18T10:00:00+00:00", "automation.a", 0.8, '{"f":2}'),
        )
        conn.execute(
            """
            INSERT INTO runtime_health_scores (ts, automation_id, score, features_json)
            VALUES (?, ?, ?, ?)
            """,
            ("2026-02-18T11:00:00+00:00", "automation.b", 0.5, '{"g":4}'),
        )
        conn.commit()

    migrated = store.migrate_legacy_runtime_health_scores(legacy_db)
    assert migrated is True

    with sqlite3.connect(runtime_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM score_history").fetchone()
        newest_a = conn.execute(
            """
            SELECT MAX(scored_at) FROM score_history WHERE automation_id = ?
            """,
            ("automation.a",),
        ).fetchone()

    store.close()
    assert count is not None
    assert count[0] == 3
    assert newest_a is not None
    assert newest_a[0] == datetime(2026, 2, 18, 10, 0, tzinfo=UTC).timestamp()


def test_set_metadata_batch_writes_multiple_keys_atomically(
    store: RuntimeEventStore,
) -> None:
    """set_metadata_batch should persist all key-value pairs in a single call."""
    store.set_metadata_batch(
        {
            "backfill_status:automation.a": "success",
            "backfill_attempts:automation.a": "2",
            "backfill_last_error:automation.a": "",
        }
    )

    assert store.get_metadata("backfill_status:automation.a") == "success"
    assert store.get_metadata("backfill_attempts:automation.a") == "2"
    assert store.get_metadata("backfill_last_error:automation.a") == ""


def test_backfill_tracking_helpers(store: RuntimeEventStore) -> None:
    """mark_backfilled/is_backfilled should persist per-automation backfill state."""
    assert store.is_backfilled("automation.backfill") is False
    store.mark_backfilled("automation.backfill")
    assert store.is_backfilled("automation.backfill") is True


def test_rebuild_daily_summaries_recomputes_rollup_rows(
    tmp_path: Path, store: RuntimeEventStore
) -> None:
    """Daily rollup rebuild should aggregate trigger_events into daily_bucket_counts."""
    store.record_trigger("automation.rollup", datetime(2026, 2, 18, 9, 0, tzinfo=UTC))
    store.record_trigger(
        "automation.rollup",
        datetime(2026, 2, 18, 9, 30, tzinfo=UTC),
    )
    store.record_trigger(
        "automation.rollup",
        datetime(2026, 2, 19, 13, 0, tzinfo=UTC),
    )
    store.rebuild_daily_summaries("automation.rollup")

    db_path = tmp_path / "autodoctor_runtime.db"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT day_date, time_bucket, trigger_count
            FROM daily_bucket_counts
            WHERE automation_id = ?
            ORDER BY day_date, time_bucket
            """,
            ("automation.rollup",),
        ).fetchall()

    assert rows == [
        ("2026-02-18", "weekday_morning", 2),
        ("2026-02-19", "weekday_afternoon", 1),
    ]


def test_get_daily_bucket_counts_returns_per_day_counts(
    store: RuntimeEventStore,
) -> None:
    """get_daily_bucket_counts should return day_date -> count from rollup table."""
    store.record_trigger("automation.dbc", datetime(2026, 2, 18, 9, 0, tzinfo=UTC))
    store.record_trigger("automation.dbc", datetime(2026, 2, 18, 9, 30, tzinfo=UTC))
    store.record_trigger("automation.dbc", datetime(2026, 2, 19, 9, 0, tzinfo=UTC))
    store.record_trigger("automation.dbc", datetime(2026, 2, 19, 14, 0, tzinfo=UTC))
    store.rebuild_daily_summaries("automation.dbc")

    morning = store.get_daily_bucket_counts("automation.dbc", "weekday_morning")
    assert morning == {"2026-02-18": 2, "2026-02-19": 1}

    afternoon = store.get_daily_bucket_counts("automation.dbc", "weekday_afternoon")
    assert afternoon == {"2026-02-19": 1}

    assert store.get_daily_bucket_counts("", "weekday_morning") == {}
    assert store.get_daily_bucket_counts("automation.dbc", "") == {}


def test_async_store_hass_type_annotation_is_not_any() -> None:
    """Guard: AsyncRuntimeEventStore.__init__ hass param should not be Any."""
    import inspect
    from typing import Any

    sig = inspect.signature(AsyncRuntimeEventStore.__init__)
    hint = sig.parameters["hass"].annotation
    assert hint is not Any, "hass parameter should use HomeAssistant type, not Any"
    assert hint != "Any", "hass parameter should use HomeAssistant type, not Any"


def test_run_in_executor_func_annotation_is_not_bare_any() -> None:
    """Guard: _run_in_executor func param should use Callable, not bare Any."""
    import inspect
    from typing import Any

    sig = inspect.signature(AsyncRuntimeEventStore._run_in_executor)
    hint = sig.parameters["func"].annotation
    assert hint is not Any, "func parameter should use Callable[..., Any], not bare Any"
    assert hint != "Any", "func parameter should use Callable[..., Any], not bare Any"


def test_get_last_score_features_raw_annotation_is_not_any() -> None:
    """Guard: features_raw local in get_last_score should not be typed Any."""
    import inspect

    import custom_components.autodoctor.runtime_event_store as mod

    source = inspect.getsource(mod.RuntimeEventStore.get_last_score)
    assert "features_raw: Any" not in source, (
        "features_raw should be str | None, not Any"
    )
