"""Local SQLite runtime event storage for automation trigger history."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

_BUCKET_NIGHT_START_HOUR = 22
_BUCKET_MORNING_START_HOUR = 5
_BUCKET_AFTERNOON_START_HOUR = 12
_BUCKET_EVENING_START_HOUR = 17


def classify_time_bucket(timestamp: datetime) -> str:
    """Map timestamp into weekday/weekend x daypart bucket."""
    day_type = "weekend" if timestamp.weekday() >= 5 else "weekday"
    hour = timestamp.hour
    if _BUCKET_MORNING_START_HOUR <= hour < _BUCKET_AFTERNOON_START_HOUR:
        daypart = "morning"
    elif _BUCKET_AFTERNOON_START_HOUR <= hour < _BUCKET_EVENING_START_HOUR:
        daypart = "afternoon"
    elif _BUCKET_EVENING_START_HOUR <= hour < _BUCKET_NIGHT_START_HOUR:
        daypart = "evening"
    else:
        daypart = "night"
    return f"{day_type}_{daypart}"


@dataclass(frozen=True)
class ScoreHistoryRow:
    """Persisted runtime score row."""

    automation_id: str
    scored_at: float
    score: float
    ema_score: float
    features: dict[str, float]


class RuntimeEventStore:
    """Local SQLite store for runtime automation events and score history."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.commit()

    def ensure_schema(self, target_version: int) -> int:
        """Apply forward-only schema migrations and return active schema version."""
        desired = max(1, int(target_version))
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                ) WITHOUT ROWID
                """
            )
            current_version = int(self._get_metadata_unlocked("schema_version") or "0")
            if current_version >= desired:
                return current_version

            self._set_metadata_unlocked("migration:state", "running")
            self._set_metadata_unlocked("migration:target_version", str(desired))
            self._set_metadata_unlocked("migration:last_error", "")
            self._set_metadata_unlocked(
                "migration:updated_at", datetime.now(UTC).isoformat()
            )

            try:
                while current_version < desired:
                    next_version = current_version + 1
                    if next_version == 1:
                        self._apply_schema_v1()
                        current_version = 1
                        continue
                    raise RuntimeError(f"Unsupported target schema version: {desired}")

                self._set_metadata_unlocked("schema_version", str(current_version))
                self._set_metadata_unlocked("migration:state", "idle")
                self._set_metadata_unlocked(
                    "migration:updated_at", datetime.now(UTC).isoformat()
                )
                return current_version
            except Exception as err:
                self._set_metadata_unlocked("migration:state", "failed")
                self._set_metadata_unlocked("migration:last_error", str(err))
                self._set_metadata_unlocked(
                    "migration:updated_at", datetime.now(UTC).isoformat()
                )
                raise

    def get_metadata(self, key: str) -> str | None:
        """Read metadata value for key, if present."""
        with self._lock:
            return self._get_metadata_unlocked(key)

    def set_metadata(self, key: str, value: str) -> None:
        """Upsert metadata value for key."""
        with self._lock:
            self._set_metadata_unlocked(key, value)

    def set_metadata_batch(self, pairs: dict[str, str]) -> None:
        """Upsert multiple metadata key-value pairs in a single transaction."""
        if not pairs:
            return
        with self._lock:
            for key, value in pairs.items():
                self._set_metadata_unlocked(key, value)

    def _get_metadata_unlocked(self, key: str) -> str | None:
        """Read metadata value without acquiring lock. Caller must hold self._lock."""
        row = self._conn.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def _set_metadata_unlocked(self, key: str, value: str) -> None:
        """Upsert metadata value without acquiring lock. Caller must hold self._lock."""
        self._conn.execute(
            """
            INSERT INTO metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self._conn.close()

    def record_trigger(self, automation_id: str, triggered_at: datetime) -> None:
        """Record a single trigger event, deduplicated by primary key."""
        if not automation_id:
            return
        ts = self._to_utc(triggered_at)
        bucket = self._classify_time_bucket(ts)
        weekday = ts.weekday()
        epoch = ts.timestamp()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO trigger_events
                    (automation_id, triggered_at, time_bucket, weekday)
                VALUES (?, ?, ?, ?)
                """,
                (automation_id, epoch, bucket, weekday),
            )
            self._conn.commit()

    def bulk_import(self, automation_id: str, timestamps: list[datetime]) -> int:
        """Bulk-insert recorder backfill timestamps. Returns inserted row count."""
        if not automation_id or not timestamps:
            return 0

        rows: list[tuple[str, float, str, int]] = []
        for ts in timestamps:
            utc_ts = self._to_utc(ts)
            rows.append(
                (
                    automation_id,
                    utc_ts.timestamp(),
                    self._classify_time_bucket(utc_ts),
                    utc_ts.weekday(),
                )
            )

        with self._lock:
            before = self._conn.total_changes
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO trigger_events
                    (automation_id, triggered_at, time_bucket, weekday)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            self._conn.commit()
            inserted = self._conn.total_changes - before
        return max(0, int(inserted))

    def get_events(
        self,
        automation_id: str,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[float]:
        """Return event epochs for automation within optional bounds."""
        if not automation_id:
            return []
        query = "SELECT triggered_at FROM trigger_events WHERE automation_id = ?"
        params: list[object] = [automation_id]
        if after is not None:
            query += " AND triggered_at >= ?"
            params.append(self._to_utc(after).timestamp())
        if before is not None:
            query += " AND triggered_at <= ?"
            params.append(self._to_utc(before).timestamp())
        query += " ORDER BY triggered_at ASC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [float(row[0]) for row in rows]

    def get_events_for_bucket(
        self,
        automation_id: str,
        time_bucket: str,
        after: datetime | None = None,
    ) -> list[float]:
        """Return event epochs for one automation and time bucket."""
        if not automation_id or not time_bucket:
            return []
        query = (
            "SELECT triggered_at FROM trigger_events "
            "WHERE automation_id = ? AND time_bucket = ?"
        )
        params: list[object] = [automation_id, time_bucket]
        if after is not None:
            query += " AND triggered_at >= ?"
            params.append(self._to_utc(after).timestamp())
        query += " ORDER BY triggered_at ASC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [float(row[0]) for row in rows]

    def get_daily_counts(
        self,
        automation_id: str,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> dict[str, int]:
        """Return day_date -> count for one automation."""
        if not automation_id:
            return {}
        query = (
            "SELECT date(triggered_at, 'unixepoch') AS day_date, COUNT(*) "
            "FROM trigger_events WHERE automation_id = ?"
        )
        params: list[object] = [automation_id]
        if after is not None:
            query += " AND triggered_at >= ?"
            params.append(self._to_utc(after).timestamp())
        if before is not None:
            query += " AND triggered_at <= ?"
            params.append(self._to_utc(before).timestamp())
        query += " GROUP BY day_date ORDER BY day_date ASC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def get_bucket_counts(
        self,
        automation_id: str,
        after: datetime | None = None,
    ) -> dict[str, int]:
        """Return time_bucket -> count for one automation."""
        if not automation_id:
            return {}
        query = (
            "SELECT time_bucket, COUNT(*) FROM trigger_events WHERE automation_id = ?"
        )
        params: list[object] = [automation_id]
        if after is not None:
            query += " AND triggered_at >= ?"
            params.append(self._to_utc(after).timestamp())
        query += " GROUP BY time_bucket ORDER BY time_bucket ASC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def get_last_trigger(self, automation_id: str) -> float | None:
        """Return epoch timestamp of most recent trigger for automation."""
        if not automation_id:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(triggered_at) FROM trigger_events WHERE automation_id = ?",
                (automation_id,),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return float(row[0])

    def get_automation_ids(self) -> list[str]:
        """Return automation IDs with at least one event."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT automation_id FROM trigger_events ORDER BY automation_id"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def count_events(self, automation_id: str) -> int:
        """Return total trigger row count for one automation."""
        if not automation_id:
            return 0
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM trigger_events WHERE automation_id = ?",
                (automation_id,),
            ).fetchone()
        if row is None:
            return 0
        return int(row[0])

    def has_data(self, automation_id: str) -> bool:
        """Check whether automation has at least one trigger event."""
        if not automation_id:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM trigger_events WHERE automation_id = ? LIMIT 1",
                (automation_id,),
            ).fetchone()
        return row is not None

    def get_inter_arrival_times(
        self,
        automation_id: str,
        time_bucket: str | None = None,
        after: datetime | None = None,
    ) -> list[float]:
        """Return gap durations in minutes between consecutive trigger events."""
        if not automation_id:
            return []
        query = "SELECT triggered_at FROM trigger_events WHERE automation_id = ?"
        params: list[object] = [automation_id]
        if time_bucket is not None:
            query += " AND time_bucket = ?"
            params.append(time_bucket)
        if after is not None:
            query += " AND triggered_at >= ?"
            params.append(self._to_utc(after).timestamp())
        query += " ORDER BY triggered_at ASC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        values = [float(row[0]) for row in rows]
        if len(values) < 2:
            return []
        gaps: list[float] = []
        for idx in range(1, len(values)):
            gap_minutes = max(0.0, (values[idx] - values[idx - 1]) / 60.0)
            gaps.append(gap_minutes)
        return gaps

    def trim(self, retention_days: int = 90, now: datetime | None = None) -> int:
        """Delete trigger rows older than retention cutoff and return deleted count."""
        retention = max(1, int(retention_days))
        current = self._to_utc(now or datetime.now(UTC))
        cutoff = (current.timestamp()) - float(retention * 24 * 60 * 60)
        with self._lock:
            before = self._conn.total_changes
            self._conn.execute(
                "DELETE FROM trigger_events WHERE triggered_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            deleted = self._conn.total_changes - before
        return max(0, int(deleted))

    def record_score(
        self,
        automation_id: str,
        *,
        scored_at: datetime,
        score: float,
        ema_score: float,
        features: dict[str, float] | None = None,
    ) -> None:
        """Persist one runtime score row."""
        if not automation_id:
            return
        ts = self._to_utc(scored_at).timestamp()
        payload = json.dumps(features or {}, separators=(",", ":"), sort_keys=True)
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO score_history
                    (automation_id, scored_at, score, ema_score, features_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (automation_id, ts, float(score), float(ema_score), payload),
            )
            self._conn.commit()

    def get_last_score(self, automation_id: str) -> ScoreHistoryRow | None:
        """Return the most recent score row for one automation."""
        if not automation_id:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT automation_id, scored_at, score, ema_score, features_json
                FROM score_history
                WHERE automation_id = ?
                ORDER BY scored_at DESC
                LIMIT 1
                """,
                (automation_id,),
            ).fetchone()
        if row is None:
            return None
        features_raw: Any = row[4]
        parsed_obj: object
        try:
            parsed_obj = json.loads(features_raw) if features_raw else {}
        except (TypeError, ValueError):
            parsed_obj = {}
        features: dict[str, float] = {}
        if isinstance(parsed_obj, dict):
            parsed_dict = cast(dict[object, object], parsed_obj)
            for key, value in parsed_dict.items():
                if not isinstance(value, (int, float, str)):
                    continue
                try:
                    features[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
        return ScoreHistoryRow(
            automation_id=str(row[0]),
            scored_at=float(row[1]),
            score=float(row[2]),
            ema_score=float(row[3]),
            features=features,
        )

    def migrate_legacy_runtime_health_scores(self, legacy_db_path: str | Path) -> bool:
        """Migrate legacy runtime_health_scores rows into score_history."""
        legacy_path = Path(legacy_db_path)
        if not legacy_path.exists():
            return False

        with sqlite3.connect(legacy_path) as legacy_conn:
            legacy_table = legacy_conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'runtime_health_scores'
                """
            ).fetchone()
            if legacy_table is None:
                return False
            legacy_rows = legacy_conn.execute(
                """
                SELECT ts, automation_id, score, features_json
                FROM runtime_health_scores
                ORDER BY automation_id ASC, ts ASC
                """
            ).fetchall()
        if not legacy_rows:
            return True

        imported_latest: dict[str, float] = {}
        normalized_rows: list[tuple[str, float, float, float, str]] = []
        for ts_raw, automation_id_raw, score_raw, features_raw in legacy_rows:
            try:
                parsed = datetime.fromisoformat(str(ts_raw))
                parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
                scored_epoch = parsed.astimezone(UTC).timestamp()
            except (TypeError, ValueError):
                continue
            automation_id = str(automation_id_raw)
            score = float(score_raw)
            features_json = str(features_raw) if features_raw is not None else "{}"
            normalized_rows.append(
                (automation_id, scored_epoch, score, score, features_json)
            )
            imported_latest[automation_id] = max(
                imported_latest.get(automation_id, float("-inf")),
                scored_epoch,
            )
        if not normalized_rows:
            return False

        with self._lock:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO score_history
                    (automation_id, scored_at, score, ema_score, features_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                normalized_rows,
            )
            self._conn.commit()

            placeholders = ",".join("?" for _ in imported_latest)
            params = list(imported_latest)
            rows = self._conn.execute(
                f"""
                SELECT automation_id, MAX(scored_at)
                FROM score_history
                WHERE automation_id IN ({placeholders})
                GROUP BY automation_id
                """,
                params,
            ).fetchall()

        observed_latest = {str(row[0]): float(row[1]) for row in rows}
        for automation_id, expected_latest in imported_latest.items():
            observed = observed_latest.get(automation_id)
            if observed is None or abs(observed - expected_latest) > 1e-9:
                return False
        return True

    def is_backfilled(self, automation_id: str) -> bool:
        """Return whether recorder backfill completed successfully for automation."""
        if not automation_id:
            return False
        value = self.get_metadata(f"backfill_status:{automation_id}")
        return value == "success"

    def mark_backfilled(self, automation_id: str) -> None:
        """Mark recorder backfill completed for automation."""
        if not automation_id:
            return
        self.set_metadata(f"backfill_status:{automation_id}", "success")

    def rebuild_daily_summaries(self, automation_id: str) -> None:
        """Recompute daily rollup cache from trigger_events for one automation."""
        if not automation_id:
            return
        with self._lock:
            self._conn.execute(
                "DELETE FROM daily_bucket_counts WHERE automation_id = ?",
                (automation_id,),
            )
            self._conn.execute(
                """
                INSERT INTO daily_bucket_counts
                    (automation_id, day_date, time_bucket, trigger_count)
                SELECT
                    automation_id,
                    date(triggered_at, 'unixepoch') AS day_date,
                    time_bucket,
                    COUNT(*)
                FROM trigger_events
                WHERE automation_id = ?
                GROUP BY automation_id, day_date, time_bucket
                """,
                (automation_id,),
            )
            self._conn.commit()

    def get_daily_bucket_counts(
        self, automation_id: str, time_bucket: str
    ) -> dict[str, int]:
        """Return day_date -> trigger_count for one automation and time bucket."""
        if not automation_id or not time_bucket:
            return {}
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT day_date, trigger_count
                FROM daily_bucket_counts
                WHERE automation_id = ? AND time_bucket = ?
                ORDER BY day_date ASC
                """,
                (automation_id, time_bucket),
            ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def _apply_schema_v1(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trigger_events (
                automation_id TEXT NOT NULL,
                triggered_at REAL NOT NULL,
                time_bucket TEXT NOT NULL,
                weekday INTEGER NOT NULL,
                PRIMARY KEY (automation_id, triggered_at)
            ) WITHOUT ROWID
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trigger_events_time
                ON trigger_events (triggered_at)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trigger_events_bucket
                ON trigger_events (automation_id, time_bucket, triggered_at)
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS score_history (
                automation_id TEXT NOT NULL,
                scored_at REAL NOT NULL,
                score REAL NOT NULL,
                ema_score REAL NOT NULL,
                features_json TEXT,
                PRIMARY KEY (automation_id, scored_at)
            ) WITHOUT ROWID
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bucket_counts (
                automation_id TEXT NOT NULL,
                day_date TEXT NOT NULL,
                time_bucket TEXT NOT NULL,
                trigger_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (automation_id, day_date, time_bucket)
            ) WITHOUT ROWID
            """
        )
        self._conn.commit()

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _classify_time_bucket(timestamp: datetime) -> str:
        return classify_time_bucket(timestamp)


class AsyncRuntimeEventStore:
    """Async wrapper that delegates RuntimeEventStore methods to executor jobs."""

    def __init__(
        self,
        hass: Any,
        store: RuntimeEventStore,
        *,
        max_in_flight: int = 256,
    ) -> None:
        self._hass = hass
        self._store = store
        self._max_in_flight = max(1, int(max_in_flight))
        self._semaphore = asyncio.Semaphore(self._max_in_flight)
        self.pending_jobs = 0
        self.write_failures = 0
        self.dropped_events = 0

    async def _run_in_executor(self, func: Any, *args: Any) -> Any:
        async with self._semaphore:
            self.pending_jobs += 1
            try:
                return await self._hass.async_add_executor_job(func, *args)
            except Exception:
                self.write_failures += 1
                raise
            finally:
                self.pending_jobs = max(0, self.pending_jobs - 1)

    async def async_record_trigger(
        self,
        automation_id: str,
        triggered_at: datetime,
    ) -> bool:
        if self.pending_jobs >= self._max_in_flight:
            self.dropped_events += 1
            return False
        await self._run_in_executor(
            self._store.record_trigger,
            automation_id,
            triggered_at,
        )
        return True

    async def async_get_events(
        self,
        automation_id: str,
        after: datetime | None = None,
        before: datetime | None = None,
    ) -> list[float]:
        result = await self._run_in_executor(
            self._store.get_events,
            automation_id,
            after,
            before,
        )
        return [float(value) for value in result]
