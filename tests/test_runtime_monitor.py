"""Tests for runtime automation health monitoring."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.models import IssueType
from custom_components.autodoctor.runtime_event_store import RuntimeEventStore
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


class _FixedScoreDetector:
    """Test detector that returns a fixed anomaly score."""

    def __init__(self, score: float) -> None:
        self._score = score

    def score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        window_size: int | None = None,
    ) -> float:
        return self._score


class _TestRuntimeMonitor(RuntimeHealthMonitor):
    """Runtime monitor with injectable history for tests."""

    def __init__(
        self,
        hass: HomeAssistant,
        history: dict[str, list[datetime]],
        now: datetime,
        score: float = 2.0,
        **kwargs: object,
    ) -> None:
        super().__init__(
            hass,
            detector=_FixedScoreDetector(score),
            now_factory=lambda: now,
            **kwargs,
        )
        self._history = history

    async def _async_fetch_trigger_history(
        self,
        automation_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[datetime]]:
        return {
            automation_id: [
                ts
                for ts in self._history.get(
                    automation_id,
                    self._history.get(automation_id.replace("automation.", ""), []),
                )
                if start <= ts <= end
            ]
            for automation_id in automation_ids
        }

    async def _async_fetch_trigger_history_from_store(
        self,
        *,
        automation_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> dict[str, list[datetime]]:
        return await self._async_fetch_trigger_history(automation_ids, start, end)


def _automation(automation_id: str, name: str = "Test Automation") -> dict[str, str]:
    return {"id": automation_id, "alias": name}


@pytest.mark.asyncio
async def test_runtime_monitor_skips_when_warmup_insufficient(
    hass: HomeAssistant,
) -> None:
    """No issues should be emitted when there is not enough baseline training data."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {
        "runtime_test": [
            now - timedelta(days=1),
            now - timedelta(days=2),
            now - timedelta(days=3),
        ]
    }
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=10,
    )

    issues = await monitor.validate_automations([_automation("runtime_test")])
    assert issues == []
    assert monitor.get_last_run_stats()["insufficient_warmup"] == 1


@pytest.mark.asyncio
async def test_runtime_monitor_extends_lookback_for_sparse_warmup(
    hass: HomeAssistant,
) -> None:
    """Sparse automations should trigger a wider history fetch before warmup skip."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    sparse_history = {
        "runtime_sparse": [
            now - timedelta(days=35, hours=2),
            now - timedelta(days=50, hours=2),
            now - timedelta(days=65, hours=2),
        ]
    }
    fetch_calls: list[tuple[datetime, datetime, tuple[str, ...]]] = []

    class _TrackingRuntimeMonitor(_TestRuntimeMonitor):
        async def _async_fetch_trigger_history_from_store(
            self,
            *,
            automation_ids: list[str],
            start: datetime,
            end: datetime,
        ) -> dict[str, list[datetime]]:
            fetch_calls.append((start, end, tuple(automation_ids)))
            return {
                automation_id: [
                    ts
                    for ts in self._history.get(
                        automation_id,
                        self._history.get(automation_id.replace("automation.", ""), []),
                    )
                    if start <= ts <= end
                ]
                for automation_id in automation_ids
            }

    monitor = _TrackingRuntimeMonitor(
        hass,
        history=sparse_history,
        now=now,
        score=0.1,
        baseline_days=30,
        warmup_samples=3,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations([_automation("runtime_sparse")])
    stats = monitor.get_last_run_stats()

    assert issues == []
    assert len(fetch_calls) == 2
    assert fetch_calls[1][0] < fetch_calls[0][0]
    assert fetch_calls[1][1] == fetch_calls[0][0], (
        "Extended lookback query should end where the original query started (no overlap)"
    )
    assert stats.get("insufficient_warmup", 0) == 0
    assert stats.get("extended_lookback_used", 0) == 1
    assert stats.get("scored_after_lookback", 0) == 1


@pytest.mark.asyncio
async def test_runtime_monitor_adapts_warmup_for_low_frequency_automation(
    hass: HomeAssistant,
) -> None:
    """Low-frequency automations should still score after extended lookback."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    sparse_history = {
        "runtime_sparse": [
            now - timedelta(days=35, hours=2),
            now - timedelta(days=56, hours=2),
        ]
    }

    monitor = _TestRuntimeMonitor(
        hass,
        history=sparse_history,
        now=now,
        score=0.2,
        baseline_days=30,
        warmup_samples=5,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations([_automation("runtime_sparse")])
    stats = monitor.get_last_run_stats()

    assert issues == []
    assert stats.get("insufficient_warmup", 0) == 0
    assert "automation.runtime_sparse" in monitor._score_history


@pytest.mark.asyncio
async def test_runtime_monitor_suppresses_sparse_stalled_alerts(
    hass: HomeAssistant,
) -> None:
    """Sparse-history automations should avoid hard stalled alerts."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    sparse_history = {
        "runtime_sparse": [
            now - timedelta(days=35, hours=2),
            now - timedelta(days=56, hours=2),
        ]
    }

    monitor = _TestRuntimeMonitor(
        hass,
        history=sparse_history,
        now=now,
        score=2.2,
        baseline_days=30,
        warmup_samples=5,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations([_automation("runtime_sparse")])

    assert issues == []
    assert "automation.runtime_sparse" in monitor._score_history


@pytest.mark.asyncio
async def test_async_init_event_store_creates_store_off_event_loop(
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """Event store creation and schema ensure must run via executor, not in __init__."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    db_path = str(tmp_path / "autodoctor_runtime.db")

    # Constructor should NOT create the store - just save the path
    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
    )
    # Override the db path to our tmp location
    monitor._runtime_event_store_db_path = db_path
    assert monitor._runtime_event_store is None

    # async_init_event_store should create it via executor
    await monitor.async_init_event_store()

    assert monitor._runtime_event_store is not None
    assert monitor._async_runtime_event_store is not None
    # Verify schema was applied (metadata table exists with version)
    version = monitor._runtime_event_store.get_metadata("schema_version")
    assert version == "1"

    monitor._runtime_event_store.close()


@pytest.mark.asyncio
async def test_ingest_trigger_event_dual_writes_to_runtime_event_store(
    hass: HomeAssistant,
) -> None:
    """Live trigger ingest should dual-write to async runtime event store when enabled."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
    )

    mock_async_store = AsyncMock()
    mock_async_store.async_record_trigger = AsyncMock(return_value=True)
    monitor._async_runtime_event_store = mock_async_store

    monitor.ingest_trigger_event("automation.runtime_dual_write", occurred_at=now)
    await hass.async_block_till_done()

    mock_async_store.async_record_trigger.assert_awaited_once_with(
        "automation.runtime_dual_write",
        now,
    )


@pytest.mark.asyncio
async def test_ingest_trigger_event_marks_degraded_when_store_drops_event(
    hass: HomeAssistant,
) -> None:
    """Dropped runtime-store writes should put monitor into degraded mode."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
    )

    mock_async_store = AsyncMock()
    mock_async_store.async_record_trigger = AsyncMock(return_value=False)
    monitor._async_runtime_event_store = mock_async_store

    monitor.ingest_trigger_event("automation.runtime_drop", occurred_at=now)
    await hass.async_block_till_done()

    assert monitor._runtime_event_store_degraded is True
    assert monitor._runtime_event_store_dropped_events == 1


@pytest.mark.asyncio
async def test_async_close_event_store_drains_tasks_and_closes_connection(
    hass: HomeAssistant,
) -> None:
    """async_close_event_store should await pending tasks then close the store."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
    )

    mock_store = MagicMock()
    monitor._runtime_event_store = mock_store

    mock_async_store = AsyncMock()
    mock_async_store.async_record_trigger = AsyncMock(return_value=True)
    monitor._async_runtime_event_store = mock_async_store

    # Enqueue a write to create a tracked task
    monitor.ingest_trigger_event("automation.close_test", occurred_at=now)

    await monitor.async_close_event_store()

    # Store should be closed (executor runs it synchronously in test)
    mock_store.close.assert_called_once()
    # All tasks should be drained
    assert len(monitor._runtime_event_store_tasks) == 0


@pytest.mark.asyncio
async def test_validate_automations_always_uses_event_store(
    hass: HomeAssistant,
) -> None:
    """validate_automations should always read history from event store."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    history = {
        "automation.cutover": [
            now - timedelta(days=days_back, hours=2) for days_back in range(2, 35)
        ]
    }
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.0,
        warmup_samples=3,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations([_automation("cutover", "Cutover")])

    assert issues == []


def test_get_event_store_diagnostics_returns_runtime_store_state(
    hass: HomeAssistant,
) -> None:
    """get_event_store_diagnostics should expose store state via public API."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
    )
    monitor._runtime_event_store_degraded = True
    monitor._runtime_event_store_pending_jobs = 5
    monitor._runtime_event_store_write_failures = 3
    monitor._runtime_event_store_dropped_events = 2

    diag = monitor.get_event_store_diagnostics()

    assert diag["enabled"] is True
    assert diag["cutover"] is True  # Always-on after v2.28.0
    assert diag["degraded"] is True
    assert diag["pending_jobs"] == 5
    assert diag["write_failures"] == 3
    assert diag["dropped_events"] == 2


@pytest.mark.asyncio
async def test_runtime_monitor_does_not_flag_overactive_for_bursty_reminder_baseline(
    hass: HomeAssistant,
) -> None:
    """Bursty reminder baselines should tolerate historically normal high days."""
    now = datetime(2026, 2, 17, 12, 0, tzinfo=UTC)
    daily_counts = [
        0,
        0,
        6,
        0,
        0,
        10,
        0,
        0,
        5,
        0,
        0,
        8,
        0,
        0,
        7,
        0,
        0,
        5,
        0,
        0,
        9,
        0,
        0,
        6,
        0,
        0,
        4,
        0,
        0,
        9,
    ]
    history_events: list[datetime] = []
    for days_back, day_count in enumerate(daily_counts, start=2):
        day = now - timedelta(days=days_back, hours=2)
        for minute in range(day_count):
            history_events.append(day + timedelta(minutes=minute * 5))
    # Recent burst (12 in 24h) that should be treated as in-regime for this baseline.
    for minute in range(12):
        history_events.append(now - timedelta(hours=2, minutes=minute * 3))

    monitor = _TestRuntimeMonitor(
        hass,
        history={"garage_door": history_events},
        now=now,
        score=2.31,
        warmup_samples=3,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [_automation("garage_door", "Garage Door")]
    )

    overactive = [
        issue
        for issue in issues
        if issue.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    ]
    assert overactive == []


@pytest.mark.asyncio
async def test_runtime_monitor_does_not_flag_stalled_for_weekly_reminder_cadence(
    hass: HomeAssistant,
) -> None:
    """Weekly reminder-like cadence should not be stalled after only a few quiet days."""
    now = datetime(2026, 2, 17, 12, 0, tzinfo=UTC)
    history = {
        "trash_reminder": [
            now - timedelta(days=20, hours=2),
            now - timedelta(days=13, hours=2),
            now - timedelta(days=6, hours=2),
        ]
    }

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.20,
        warmup_samples=3,
        min_expected_events=0,
        baseline_days=30,
    )

    await monitor.validate_automations(
        [_automation("trash_reminder", "Trash Reminder")]
    )


@pytest.mark.asyncio
async def test_runtime_monitor_skips_when_no_baseline_signal(
    hass: HomeAssistant,
) -> None:
    """No issue should be created when baseline has no meaningful expected activity."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": []}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=0,
        min_expected_events=2,
    )

    issues = await monitor.validate_automations([_automation("runtime_test")])
    assert issues == []
    assert monitor.get_last_run_stats()["insufficient_baseline"] == 1


@pytest.mark.asyncio
async def test_runtime_monitor_reports_insufficient_training_rows(
    hass: HomeAssistant,
) -> None:
    """Runtime stats should include explicit training-row skip reason."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 40)]}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=1,
        min_expected_events=0,
        baseline_days=7,
    )

    issues = await monitor.validate_automations([_automation("runtime_test")])
    assert issues == []
    assert monitor.get_last_run_stats()["insufficient_training_rows"] == 1


@pytest.mark.asyncio
async def test_runtime_monitor_uses_entity_id_over_config_id_for_history_lookup(
    hass: HomeAssistant,
) -> None:
    """History lookup should use automation entity_id when config id differs."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {
        "automation.kitchen_motion": [
            now - timedelta(days=d, hours=2) for d in range(1, 31)
        ]
    }
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.0,
        warmup_samples=7,
        min_expected_events=0,
    )

    await monitor.validate_automations(
        [
            {
                "id": "01HTYV52MPM2Q2PY6EW3S9AFRF",
                "alias": "Kitchen Motion",
                "entity_id": "automation.kitchen_motion",
            }
        ]
    )


@pytest.mark.asyncio
async def test_runtime_monitor_analyzes_automation_without_id_when_entity_id_present(
    hass: HomeAssistant,
) -> None:
    """Automations without config id should still run when entity_id is available."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {
        "automation.no_id": [now - timedelta(days=d, hours=2) for d in range(1, 31)]
    }
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.0,
        warmup_samples=7,
        min_expected_events=0,
    )

    await monitor.validate_automations(
        [{"alias": "No ID Automation", "entity_id": "automation.no_id"}]
    )


def test_training_and_current_rows_have_same_features() -> None:
    """Training rows and current row must have identical feature keys."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline_start = now - timedelta(days=30)
    baseline_end = now - timedelta(hours=24)
    expected = 1.0
    events = [now - timedelta(days=d) for d in range(1, 31)]
    all_events = {"automation.test": events}

    train_rows = RuntimeHealthMonitor._build_training_rows_from_events(
        automation_id="automation.test",
        baseline_events=events,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        expected_daily=expected,
        all_events_by_automation=all_events,
        cold_start_days=0,
    )
    current_row = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.test",
        now=now,
        automation_events=events,
        baseline_events=events,
        expected_daily=expected,
        all_events_by_automation=all_events,
    )

    assert set(train_rows[0].keys()) == set(current_row.keys()), (
        f"Feature mismatch: training={sorted(train_rows[0].keys())} "
        f"vs current={sorted(current_row.keys())}"
    )


def test_bocpd_detector_scores_tail_events_higher_than_normal() -> None:
    """BOCPD detector should assign higher scores to tail events."""
    from custom_components.autodoctor.runtime_monitor import _BOCPDDetector

    detector = _BOCPDDetector()

    def _row(count_24h: float) -> dict[str, float]:
        return {
            "rolling_24h_count": count_24h,
            "rolling_7d_count": count_24h * 6.0,
            "hour_ratio_30d": 1.0,
            "gap_vs_median": 1.0,
            "is_weekend": 0.0,
            "other_automations_5m": 0.0,
        }

    training = [_row(9.0 + float(i % 3)) for i in range(23)]
    score_normal = detector.score_current("automation.normal", [*training, _row(10.0)])
    score_stalled = detector.score_current("automation.stalled", [*training, _row(0.0)])
    score_overactive = detector.score_current(
        "automation.overactive", [*training, _row(35.0)]
    )

    assert score_normal >= 0.0
    assert score_stalled > score_normal
    assert score_overactive > score_normal


def test_runtime_monitor_defaults_to_bocpd_detector(
    hass: HomeAssistant,
) -> None:
    """Runtime monitor should default to BOCPD detector."""
    from custom_components.autodoctor.runtime_monitor import _BOCPDDetector

    monitor = RuntimeHealthMonitor(hass)
    assert isinstance(monitor._detector, _BOCPDDetector)


def test_runtime_monitor_shares_single_bocpd_instance_when_no_custom_detector(
    hass: HomeAssistant,
) -> None:
    """Default detector and count detector should be the same BOCPD instance."""
    monitor = RuntimeHealthMonitor(hass)
    assert monitor._detector is monitor._bocpd_count_detector


@pytest.mark.asyncio
async def test_fetch_trigger_history_uses_modern_schema(
    hass: HomeAssistant,
) -> None:
    """Recorder query must JOIN event_types and event_data tables (HA 2023.4+ schema)."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    start = now - timedelta(days=30)

    ts1 = (now - timedelta(days=1)).timestamp()
    mock_rows = [
        (json.dumps({"entity_id": "automation.test1"}), ts1),
    ]

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_rows

    mock_instance = MagicMock()
    mock_instance.get_session.return_value = mock_session

    monitor = RuntimeHealthMonitor(hass, detector=_FixedScoreDetector(0.0))

    with patch(
        "homeassistant.components.recorder.get_instance",
        return_value=mock_instance,
    ):
        hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        result = await monitor._async_fetch_trigger_history(
            ["automation.test1"], start, now
        )

    # Verify the query was executed
    mock_session.execute.assert_called_once()
    sql_text = str(mock_session.execute.call_args[0][0])

    # Must use modern schema JOINs, not the legacy event_type/event_data columns
    assert "event_types" in sql_text, "Query must JOIN event_types table"
    assert "event_data" in sql_text, "Query must JOIN event_data table"
    assert "shared_data" in sql_text, "Query must select shared_data, not event_data"

    # Verify results are parsed correctly
    assert len(result["automation.test1"]) == 1


@pytest.mark.asyncio
async def test_fetch_trigger_history_adds_entity_id_selective_filter(
    hass: HomeAssistant,
) -> None:
    """Recorder query should include entity_id filter fragments for requested IDs."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    start = now - timedelta(days=30)
    ts1 = (now - timedelta(days=1)).timestamp()
    captured_sql: list[str] = []
    captured_params: list[dict[str, object]] = []

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    def _capture_execute(
        statement: object, params: dict[str, object]
    ) -> list[tuple[str, float]]:
        captured_sql.append(str(statement))
        captured_params.append(dict(params))
        return [(json.dumps({"entity_id": "automation.kitchen_main"}), ts1)]

    mock_session.execute.side_effect = _capture_execute

    mock_instance = MagicMock()
    mock_instance.get_session.return_value = mock_session

    monitor = RuntimeHealthMonitor(hass, detector=_FixedScoreDetector(0.0))

    with patch(
        "homeassistant.components.recorder.get_instance",
        return_value=mock_instance,
    ):
        hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        result = await monitor._async_fetch_trigger_history(
            ["automation.kitchen_main"], start, now
        )

    assert len(result["automation.kitchen_main"]) == 1
    assert captured_sql, "Expected recorder query execution"
    assert any("LIKE" in sql for sql in captured_sql), (
        "Recorder query should include entity_id selectivity filters"
    )
    filter_values = [
        value
        for params in captured_params
        for key, value in params.items()
        if key.startswith("entity_like_")
    ]
    assert filter_values, "Expected LIKE parameters for requested automation IDs"
    assert any(
        "automation.kitchen_main" in str(v).replace("\\", "") for v in filter_values
    )
    assert any('"entity_id"' in str(v) for v in filter_values)


def test_constructor_logs_config_params(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Constructor should log config parameters and detector type."""
    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        _monitor = RuntimeHealthMonitor(
            hass,
            baseline_days=30,
            warmup_samples=14,
            min_expected_events=1,
        )

    assert "baseline_days=30" in caplog.text
    assert "warmup_samples=14" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_entry(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """validate_automations should log the number of automations at entry."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    monitor = _TestRuntimeMonitor(hass, history={}, now=now, warmup_samples=0)

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("a1"), _automation("a2")])

    assert "Runtime health validation starting: 2 automations" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_handles_missing_event_store(
    hass: HomeAssistant,
) -> None:
    """validate_automations should return empty when event store is unavailable."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    monitor = _TestRuntimeMonitor(
        hass,
        history={},
        now=now,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Runtime Test")]
    )

    assert issues == []


@pytest.mark.asyncio
async def test_validate_automations_logs_no_valid_ids(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log when no valid automation IDs are found."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    monitor = _TestRuntimeMonitor(hass, history={}, now=now)

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([{"id": "", "alias": "Empty"}])

    assert "No valid automation IDs to validate" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_valid_id_count(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log the count of extracted valid automation IDs."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    monitor = _TestRuntimeMonitor(hass, history={}, now=now, warmup_samples=0)

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("a1"), _automation("a2")])

    assert "Extracted 2 valid automation IDs" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_warmup_skip(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log per-automation warmup skip detail."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d) for d in range(2, 5)]}
    monitor = _TestRuntimeMonitor(hass, history=history, now=now, warmup_samples=10)

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("runtime_test", "Kitchen")])

    assert "Automation 'Kitchen': skipped (insufficient warmup:" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_baseline_skip(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log per-automation baseline skip detail."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    # Empty history -> 0 expected events/day
    monitor = _TestRuntimeMonitor(
        hass, history={}, now=now, warmup_samples=0, min_expected_events=2
    )

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("runtime_test", "Hallway")])

    assert "Automation 'Hallway': skipped (insufficient baseline:" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_per_automation_history(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log per-automation history summary (baseline events, recent events, active days)."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    # 3 baseline events on different days, 0 recent
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 5)]}
    monitor = _TestRuntimeMonitor(hass, history=history, now=now, warmup_samples=0)

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("runtime_test", "Garage")])

    assert "Automation 'Garage': 3 baseline events" in caplog.text
    assert "0 recent events" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_scoring(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log scoring details when an automation passes warmup/baseline checks."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    # One event per day for 20 days in baseline
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 22)]}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.5,
        warmup_samples=7,
        min_expected_events=0,
    )

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("runtime_test", "Office")])

    assert "Automation 'Office': scoring with" in caplog.text
    assert "Automation 'Office': anomaly score=" in caplog.text


@pytest.mark.asyncio
async def test_fetch_trigger_history_logs_query(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log before and after fetching trigger history from recorder."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    start = now - timedelta(days=30)

    ts1 = (now - timedelta(days=1)).timestamp()
    mock_rows = [
        (json.dumps({"entity_id": "automation.test1"}), ts1),
        (json.dumps({"entity_id": "automation.test1"}), ts1),
    ]

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value = mock_rows

    mock_instance = MagicMock()
    mock_instance.get_session.return_value = mock_session

    monitor = RuntimeHealthMonitor(hass, detector=_FixedScoreDetector(0.0))

    with (
        caplog.at_level(
            logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
        ),
        patch(
            "homeassistant.components.recorder.get_instance",
            return_value=mock_instance,
        ),
    ):
        hass.async_add_executor_job = AsyncMock(side_effect=lambda fn: fn())
        await monitor._async_fetch_trigger_history(["automation.test1"], start, now)

    assert "Querying recorder for 1 automation IDs" in caplog.text
    assert "Fetched 2 total trigger events" in caplog.text


def test_feature_row_includes_expanded_runtime_features() -> None:
    """Feature rows should include the expanded runtime feature set."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    events = [now - timedelta(hours=h) for h in [1, 3, 5, 27, 48, 72]]
    all_events = {
        "automation.a": events,
        "automation.b": [now - timedelta(hours=1, minutes=2)],
    }

    row = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.a",
        now=now,
        automation_events=events,
        baseline_events=events,
        expected_daily=2.0,
        all_events_by_automation=all_events,
    )

    assert set(row.keys()) == {
        "rolling_24h_count",
        "rolling_7d_count",
        "hour_ratio_30d",
        "gap_vs_median",
        "is_weekend",
        "other_automations_5m",
    }


def test_feature_row_hour_ratio_uses_configured_window() -> None:
    """Hour ratio should be derived from configurable lookback days."""
    now = datetime(2026, 2, 11, 12, 30, tzinfo=UTC)
    events = [
        now - timedelta(minutes=10),  # current hour event
        now - timedelta(days=8),  # same hour, outside 7d but inside 30d
        now - timedelta(days=20),  # same hour, outside 7d but inside 30d
        now - timedelta(days=2, hours=1),  # different hour
    ]
    all_events = {"automation.a": events}

    row_30 = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.a",
        now=now,
        automation_events=events,
        baseline_events=events,
        expected_daily=2.0,
        all_events_by_automation=all_events,
        hour_ratio_days=30,
    )
    row_7 = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.a",
        now=now,
        automation_events=events,
        baseline_events=events,
        expected_daily=2.0,
        all_events_by_automation=all_events,
        hour_ratio_days=7,
    )

    assert row_30["hour_ratio_30d"] != row_7["hour_ratio_30d"]
    assert row_30["hour_ratio_30d"] > row_7["hour_ratio_30d"]


def test_feature_row_hour_ratio_uses_current_clock_hour_bucket() -> None:
    """Hour ratio should not count events from the previous clock hour."""
    now = datetime(2026, 2, 11, 12, 30, tzinfo=UTC)
    automation_events = [
        datetime(2026, 2, 11, 11, 50, tzinfo=UTC),  # trailing 60m, previous hour
        datetime(2026, 2, 10, 12, 10, tzinfo=UTC),
        datetime(2026, 2, 9, 12, 5, tzinfo=UTC),
    ]
    baseline_events = [
        datetime(2026, 2, 10, 12, 10, tzinfo=UTC),
        datetime(2026, 2, 9, 12, 5, tzinfo=UTC),
        datetime(2026, 2, 8, 12, 15, tzinfo=UTC),
    ]
    all_events = {"automation.a": automation_events}

    row = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.a",
        now=now,
        automation_events=automation_events,
        baseline_events=baseline_events,
        expected_daily=2.0,
        all_events_by_automation=all_events,
        hour_ratio_days=30,
    )

    assert row["hour_ratio_30d"] == 0.0


def test_median_gap_minutes_uses_adjacent_trigger_deltas() -> None:
    """Median gap should use sorted adjacent trigger deltas."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    # Gaps: 10, 20, 30 minutes -> median 20
    events = [
        now - timedelta(minutes=60),
        now - timedelta(minutes=50),
        now - timedelta(minutes=30),
        now,
    ]
    median_gap = RuntimeHealthMonitor._median_gap_minutes(events)
    assert median_gap == pytest.approx(20.0)


def test_count_other_automations_same_5m_excludes_current_automation() -> None:
    """Cascade count should include only *other* automations in same 5-minute bucket."""
    now = datetime(2026, 2, 11, 12, 3, tzinfo=UTC)
    all_events = {
        "automation.a": [now - timedelta(minutes=1)],  # same 5m window, ignored
        "automation.b": [now - timedelta(minutes=2)],  # same 5m window, counted
        "automation.c": [now - timedelta(minutes=7)],  # different 5m window
    }
    count = RuntimeHealthMonitor._count_other_automations_same_5m(
        automation_id="automation.a",
        now=now,
        all_events_by_automation=all_events,
    )
    assert count == 1.0


@pytest.mark.asyncio
async def test_validate_automations_does_not_emit_overactive_issues(
    hass: HomeAssistant,
) -> None:
    """validate_automations should not emit OVERACTIVE; _detect_count_anomaly handles it."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline = [now - timedelta(days=d, hours=1) for d in range(2, 31)]
    burst = [now - timedelta(hours=1, minutes=i) for i in range(20)]
    history = {"runtime_test": baseline + burst}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.0,
        warmup_samples=7,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Hallway Lights")]
    )

    overactive_issues = [
        i for i in issues if i.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    ]
    assert overactive_issues == []


@pytest.mark.asyncio
async def test_runtime_monitor_skips_during_startup_recovery(
    hass: HomeAssistant,
) -> None:
    """Monitor should skip learning/scoring during startup recovery window."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    monitor = _TestRuntimeMonitor(
        hass,
        history={"runtime_test": [now - timedelta(days=2)]},
        now=now,
        startup_recovery_minutes=10,
    )

    issues = await monitor.validate_automations([_automation("runtime_test")])
    assert issues == []
    assert monitor.get_last_run_stats()["startup_recovery"] == 1


@pytest.mark.asyncio
async def test_runtime_monitor_raises_threshold_when_runtime_issue_previously_suppressed(
    hass: HomeAssistant,
) -> None:
    """Suppressed runtime issues should require a higher threshold before alerting."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}

    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=True)
    hass.data["autodoctor"] = {"suppression_store": suppression_store}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=1.5,
        warmup_samples=7,
        min_expected_events=0,
        dismissed_threshold_multiplier=1.25,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Kitchen Motion")]
    )
    assert issues == []


@pytest.mark.asyncio
async def test_runtime_monitor_suppresses_stalled_even_when_score_exceeds_multiplier(
    hass: HomeAssistant,
) -> None:
    """Suppressed stalled automations should not emit runtime issues."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}

    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=True)
    hass.data["autodoctor"] = {"suppression_store": suppression_store}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.5,
        warmup_samples=7,
        min_expected_events=0,
        dismissed_threshold_multiplier=1.25,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Kitchen Motion")]
    )
    assert issues == []


@pytest.mark.asyncio
async def test_validate_automations_does_not_emit_stalled_with_rate_limit(
    hass: HomeAssistant,
) -> None:
    """validate_automations should not emit stalled issues with rate limiting."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.5,
        warmup_samples=7,
        min_expected_events=0,
        max_alerts_per_day=1,
        global_alert_cap_per_day=10,
    )

    automations = [_automation("runtime_test", "Kitchen Motion")]
    await monitor.validate_automations(automations)


@pytest.mark.asyncio
async def test_validate_automations_does_not_emit_overactive_with_rate_limit(
    hass: HomeAssistant,
) -> None:
    """validate_automations no longer emits OVERACTIVE; _detect_count_anomaly handles it."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline = [now - timedelta(days=d, hours=1) for d in range(2, 31)]
    burst = [now - timedelta(hours=1, minutes=i) for i in range(20)]
    history = {
        "runtime_a": baseline + burst,
        "runtime_b": baseline + burst,
    }
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.5,
        warmup_samples=7,
        min_expected_events=0,
        max_alerts_per_day=10,
        global_alert_cap_per_day=1,
    )

    first = await monitor.validate_automations([_automation("runtime_a", "A")])

    overactive = [
        i for i in first if i.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    ]
    assert overactive == []


def test_fixed_score_detector_accepts_window_size_kwarg() -> None:
    """Test detector must accept window_size to match the _Detector protocol."""
    detector = _FixedScoreDetector(0.5)
    rows = [{"rolling_24h_count": 1.0}] * 3
    score = detector.score_current("auto.test", rows, window_size=32)
    assert score == 0.5


def test_smoothed_score_bootstraps_from_persisted_ema(tmp_path: Path) -> None:
    """_smoothed_score should resume from persisted EMA when runtime store is enabled."""
    hass = MagicMock()
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    store = RuntimeEventStore(tmp_path / "autodoctor_runtime.db")
    store.ensure_schema(target_version=1)
    store.record_score(
        "automation.persisted",
        scored_at=now - timedelta(hours=1),
        score=0.4,
        ema_score=0.4,
        features={"x": 1.0},
    )

    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        runtime_event_store=store,
    )

    persisted = store.get_last_score("automation.persisted")
    assert persisted is not None
    ema = monitor._smoothed_score(
        "automation.persisted", 0.8, persisted_ema=persisted.ema_score
    )
    store.close()

    # score_ema_samples defaults to 5 => alpha = 2/6 ~= 0.3333
    # seeded ema: 0.4, then update with 0.8 => 0.5333
    assert ema == pytest.approx(0.5333333333, rel=1e-3)


def test_smoothed_score_accepts_prefetched_persisted_ema(tmp_path: Path) -> None:
    """_smoothed_score should use persisted_ema kwarg without touching the store."""
    hass = MagicMock()
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)

    monitor = RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
    )

    ema = monitor._smoothed_score("automation.prefetched", 0.8, persisted_ema=0.4)

    # score_ema_samples defaults to 5 => alpha = 2/6 ~= 0.3333
    # seeded ema: 0.4, then update with 0.8 => 0.5333
    assert ema == pytest.approx(0.5333333333, rel=1e-3)


def test_build_feature_row_uses_precomputed_median_gap() -> None:
    """_build_feature_row should use median_gap_override when provided."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    events = [now - timedelta(hours=1)]
    all_events: dict[str, list[datetime]] = {"automation.a": events}

    row = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.a",
        now=now,
        automation_events=events,
        baseline_events=events,
        expected_daily=1.0,
        all_events_by_automation=all_events,
        median_gap_override=42.0,
    )

    # minutes_since_last = 60.0, median_gap_override = 42.0 -> gap_vs_median = 60/42
    expected_gap_vs_median = 60.0 / 42.0
    assert row["gap_vs_median"] == pytest.approx(expected_gap_vs_median)


def test_build_training_rows_passes_median_gap_override() -> None:
    """_build_training_rows_from_events should pass median_gap_override to _build_feature_row."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline_start = now - timedelta(days=10)
    baseline_end = now - timedelta(hours=24)
    events = [now - timedelta(days=d, hours=2) for d in range(1, 10)]
    all_events: dict[str, list[datetime]] = {"automation.a": events}

    rows_with_override = RuntimeHealthMonitor._build_training_rows_from_events(
        automation_id="automation.a",
        baseline_events=events,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        expected_daily=1.0,
        all_events_by_automation=all_events,
        cold_start_days=0,
        median_gap_override=42.0,
    )

    rows_without_override = RuntimeHealthMonitor._build_training_rows_from_events(
        automation_id="automation.a",
        baseline_events=events,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        expected_daily=1.0,
        all_events_by_automation=all_events,
        cold_start_days=0,
    )

    # With override, gap_vs_median values should differ from default computation
    assert len(rows_with_override) > 0
    assert len(rows_with_override) == len(rows_without_override)
    # At least one row should have a different gap_vs_median value
    diffs = [
        a["gap_vs_median"] != b["gap_vs_median"]
        for a, b in zip(rows_with_override, rows_without_override, strict=True)
    ]
    assert any(diffs), (
        "median_gap_override should change gap_vs_median in training rows"
    )


@pytest.mark.asyncio
async def test_validate_automations_precomputes_median_gap(
    hass: HomeAssistant,
) -> None:
    """validate_automations should compute median gap once and pass it through."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.5,
        warmup_samples=7,
        min_expected_events=0,
    )

    with patch.object(
        RuntimeHealthMonitor,
        "_build_training_rows_from_events",
        wraps=RuntimeHealthMonitor._build_training_rows_from_events,
    ) as spy:
        await monitor.validate_automations([_automation("runtime_test", "Kitchen")])
        assert spy.call_count == 1
        call_kwargs = spy.call_args[1]
        assert "median_gap_override" in call_kwargs
        assert isinstance(call_kwargs["median_gap_override"], float)


@pytest.mark.asyncio
async def test_validate_automations_does_not_persist_periodic_model(
    hass: HomeAssistant,
    tmp_path,
) -> None:
    """validate_automations should not populate periodic_model (removed)."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {
        "automation.runtime_test": [
            now - timedelta(days=days_back, hours=2) for days_back in range(2, 40)
        ]
    }

    class _HistoryRuntimeMonitor(RuntimeHealthMonitor):
        def __init__(self) -> None:
            super().__init__(
                hass,
                now_factory=lambda: now,
                warmup_samples=7,
                min_expected_events=0,
                burst_multiplier=999.0,
            )

        async def _async_fetch_trigger_history(
            self,
            automation_ids: list[str],
            start: datetime,
            end: datetime,
        ) -> dict[str, list[datetime]]:
            return {
                automation_id: [
                    ts for ts in history.get(automation_id, []) if start <= ts <= end
                ]
                for automation_id in automation_ids
            }

        async def _async_fetch_trigger_history_from_store(
            self,
            *,
            automation_ids: list[str],
            start: datetime,
            end: datetime,
        ) -> dict[str, list[datetime]]:
            return await self._async_fetch_trigger_history(automation_ids, start, end)

    monitor = _HistoryRuntimeMonitor()
    await monitor.validate_automations([_automation("runtime_test", "Kitchen")])
    await hass.async_block_till_done()

    state = monitor.get_runtime_state()
    automations = state.get("automations", {})
    automation_state = automations.get("automation.runtime_test", {})
    assert "periodic_model" not in automation_state


@pytest.mark.asyncio
async def test_validate_automations_does_not_overwrite_live_daypart_bucket_state(
    hass: HomeAssistant,
    tmp_path,
) -> None:
    """Periodic scoring should not mutate daypart live bucket expected-rate semantics."""
    now = datetime(2026, 2, 20, 9, 0, tzinfo=UTC)
    aid = "automation.runtime_mix_units"
    history_events: list[datetime] = []
    cursor = now - timedelta(days=40)
    for _ in range(32):
        cursor += timedelta(days=1)
        history_events.extend(
            [
                cursor.replace(hour=8, minute=0),  # morning
                cursor.replace(hour=13, minute=0),  # afternoon
                cursor.replace(hour=18, minute=0),  # evening
                cursor.replace(hour=23, minute=0),  # night
            ]
        )
    history = {aid: history_events}

    class _HistoryRuntimeMonitor(RuntimeHealthMonitor):
        def __init__(self) -> None:
            super().__init__(
                hass,
                now_factory=lambda: now,
                warmup_samples=7,
                min_expected_events=0,
                burst_multiplier=999.0,
            )

        async def _async_fetch_trigger_history(
            self,
            automation_ids: list[str],
            start: datetime,
            end: datetime,
        ) -> dict[str, list[datetime]]:
            return {
                automation_id: [
                    ts for ts in history.get(automation_id, []) if start <= ts <= end
                ]
                for automation_id in automation_ids
            }

        async def _async_fetch_trigger_history_from_store(
            self,
            *,
            automation_ids: list[str],
            start: datetime,
            end: datetime,
        ) -> dict[str, list[datetime]]:
            return await self._async_fetch_trigger_history(automation_ids, start, end)

    monitor = _HistoryRuntimeMonitor()

    for event_time in history_events:
        monitor.ingest_trigger_event(aid, occurred_at=event_time)

    state_before = monitor.get_runtime_state()
    bucket_name = monitor.classify_time_bucket(now)
    before_bucket = state_before["automations"][aid]["count_model"]["buckets"][
        bucket_name
    ]
    before_expected_rate = before_bucket["expected_rate"]

    await monitor.validate_automations(
        [{"id": "runtime_mix_units", "alias": "Mix Units", "entity_id": aid}]
    )

    state_after = monitor.get_runtime_state()
    after_bucket = state_after["automations"][aid]["count_model"]["buckets"][
        bucket_name
    ]
    assert after_bucket["expected_rate"] == pytest.approx(before_expected_rate)


def test_build_5m_bucket_index_groups_events_correctly() -> None:
    """_build_5m_bucket_index should bucket events into 5-minute windows."""
    all_events: dict[str, list[datetime]] = {
        "automation.a": [
            datetime(2026, 2, 11, 12, 1, tzinfo=UTC),  # bucket 12:00
            datetime(2026, 2, 11, 12, 6, tzinfo=UTC),  # bucket 12:05
        ],
        "automation.b": [
            datetime(2026, 2, 11, 12, 2, tzinfo=UTC),  # bucket 12:00
        ],
    }

    index = RuntimeHealthMonitor._build_5m_bucket_index(all_events)

    # Bucket key for 12:00-12:05 window
    bucket_key_1200 = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    bucket_key_1205 = datetime(2026, 2, 11, 12, 5, tzinfo=UTC)

    assert "automation.a" in index[bucket_key_1200]
    assert "automation.b" in index[bucket_key_1200]
    assert "automation.a" in index[bucket_key_1205]
    assert "automation.b" not in index.get(bucket_key_1205, set())


def test_build_profile_removed() -> None:
    """build_profile and AutomationProfile were removed — BOCPD handles profiling."""
    assert not hasattr(RuntimeHealthMonitor, "build_profile")


def test_catch_up_count_model_replays_missing_finalized_days(
    tmp_path: Path,
) -> None:
    """catch_up_count_model should feed missing finalized daily counts into BOCPD state."""
    automation_id = "automation.catch_up_test"
    store = RuntimeEventStore(tmp_path / "catch_up.db")
    store.ensure_schema(target_version=1)

    # Plant 2 events per day for Feb 14-17 (Sat-Tue) in the morning bucket
    timestamps = [
        datetime(2026, 2, 14, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 14, 10, 0, tzinfo=UTC),
        datetime(2026, 2, 15, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 15, 10, 0, tzinfo=UTC),
        datetime(2026, 2, 16, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 16, 10, 0, tzinfo=UTC),
        datetime(2026, 2, 17, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 17, 10, 0, tzinfo=UTC),
    ]
    store.bulk_import(automation_id, timestamps)
    store.rebuild_daily_summaries(automation_id)

    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    monitor = RuntimeHealthMonitor(
        hass=MagicMock(),
        now_factory=lambda: now,
    )

    # Pre-seed bucket state as if last scored on Feb 13
    automation_state = monitor._ensure_automation_state(automation_id)
    bucket_state = monitor._ensure_count_bucket_state(
        automation_state["count_model"], "weekday_morning"
    )
    bucket_state["current_day"] = "2026-02-13"
    bucket_state["current_count"] = 0
    bucket_state["observations"] = [1, 1, 1]

    monitor.catch_up_count_model(
        store=store,
        automation_id=automation_id,
        now=now,
    )

    updated = automation_state["count_model"]["buckets"]["weekday_morning"]
    # Feb 14 (Sat) and 15 (Sun) are weekend — don't match weekday_morning.
    # Feb 16 (Mon) and 17 (Tue) are weekday_morning days with 2 events each.
    # Original 3 obs + 2 new weekday days = 5 observations.
    assert len(updated["observations"]) == 5

    store.close()


def test_build_feature_row_uses_prebucketed_5m_index() -> None:
    """_build_feature_row should use bucket_index for O(1) lookup when provided."""
    now = datetime(2026, 2, 11, 12, 3, tzinfo=UTC)
    events = [now - timedelta(minutes=1)]
    all_events: dict[str, list[datetime]] = {
        "automation.a": events,
        "automation.b": [now - timedelta(minutes=2)],  # same 5m bucket
        "automation.c": [now - timedelta(minutes=7)],  # different bucket
    }

    # Build the bucket index
    bucket_index = RuntimeHealthMonitor._build_5m_bucket_index(all_events)

    row = RuntimeHealthMonitor._build_feature_row(
        automation_id="automation.a",
        now=now,
        automation_events=events,
        baseline_events=events,
        expected_daily=1.0,
        all_events_by_automation=all_events,
        bucket_index=bucket_index,
    )

    # automation.b is in same 5m bucket, automation.c is not -> count should be 1
    assert row["other_automations_5m"] == 1.0


def test_build_training_rows_passes_bucket_index() -> None:
    """_build_training_rows_from_events should pass bucket_index through to _build_feature_row."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline_start = now - timedelta(days=5)
    baseline_end = now - timedelta(hours=24)
    events = [now - timedelta(days=d, hours=2) for d in range(1, 5)]
    all_events: dict[str, list[datetime]] = {"automation.a": events}
    bucket_index = RuntimeHealthMonitor._build_5m_bucket_index(all_events)

    with patch.object(
        RuntimeHealthMonitor,
        "_build_feature_row",
        wraps=RuntimeHealthMonitor._build_feature_row,
    ) as spy:
        RuntimeHealthMonitor._build_training_rows_from_events(
            automation_id="automation.a",
            baseline_events=events,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            expected_daily=1.0,
            all_events_by_automation=all_events,
            cold_start_days=0,
            bucket_index=bucket_index,
        )
        assert spy.call_count >= 1
        for call in spy.call_args_list:
            assert call[1].get("bucket_index") is bucket_index


@pytest.mark.asyncio
async def test_validate_automations_builds_and_passes_bucket_index(
    hass: HomeAssistant,
) -> None:
    """validate_automations should build bucket index once and pass it through."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.5,
        warmup_samples=7,
        min_expected_events=0,
    )

    with patch.object(
        RuntimeHealthMonitor,
        "_build_training_rows_from_events",
        wraps=RuntimeHealthMonitor._build_training_rows_from_events,
    ) as spy:
        await monitor.validate_automations([_automation("runtime_test", "Kitchen")])
        assert spy.call_count == 1
        call_kwargs = spy.call_args[1]
        assert "bucket_index" in call_kwargs
        assert isinstance(call_kwargs["bucket_index"], dict)


@pytest.mark.parametrize(
    "attr",
    [
        "_log_score_telemetry",
        "_telemetry_table_ensured",
        "_telemetry_lock",
        "_telemetry_db_path",
        "_dismissed_multiplier",
        "_percentile",
        "_build_training_rows",
        "_build_current_row",
        "async_load_state",
        "async_flush_runtime_state",
        "_persist_runtime_state",
        "_maybe_flush_runtime_state",
        "_bucket_expected_rate",
    ],
)
def test_removed_runtime_monitor_attrs(attr: str) -> None:
    """Guard: removed RuntimeHealthMonitor attributes must not be re-introduced."""
    assert not hasattr(RuntimeHealthMonitor, attr), (
        f"RuntimeHealthMonitor.{attr} was removed — do not re-introduce"
    )


def test_legacy_gamma_poisson_class_removed() -> None:
    """Legacy runtime detector should no longer be exported."""
    from custom_components.autodoctor import runtime_monitor

    assert not hasattr(runtime_monitor, "_GammaPoissonDetector")


def test_score_current_logs_debug_on_type_error_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_score_current should log a debug message when falling back due to TypeError."""

    class _NoWindowSizeDetector:
        def score_current(
            self,
            automation_id: str,
            train_rows: list[dict[str, float]],
            **kwargs: object,
        ) -> float:
            if "window_size" in kwargs:
                raise TypeError("unexpected keyword argument 'window_size'")
            return 0.42

    hass = MagicMock()
    monitor = RuntimeHealthMonitor(
        hass,
        detector=_NoWindowSizeDetector(),
        now_factory=lambda: datetime(2026, 2, 11, 12, 0, tzinfo=UTC),
    )
    rows = [{"a": 1.0}, {"a": 2.0}]

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        score = monitor._score_current("auto.test", rows, window_size=32)

    assert score == pytest.approx(0.42)
    assert "TypeError" in caplog.text
    assert "auto.test" in caplog.text


def test_init_does_not_call_sync_load(hass: HomeAssistant) -> None:
    """RuntimeHealthMonitor.__init__ should not call sync load on the state store."""
    mock_store = MagicMock()
    mock_store.load.return_value = {
        "schema_version": 2,
        "automations": {},
        "alerts": {"date": "", "global_count": 0},
    }
    _TestRuntimeMonitor(
        hass,
        history={},
        now=datetime(2026, 2, 13, 12, 0, tzinfo=UTC),
    )
    mock_store.load.assert_not_called()


@pytest.mark.asyncio
async def test_overactive_skipped_when_no_baseline_events_on_current_day_type(
    hass: HomeAssistant,
) -> None:
    """Overactive check should be suppressed when no baseline events on current day type."""
    # Wednesday 12:00 UTC — current day type is weekday
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    # Baseline: weekend-only events (Sat/Sun), plus a burst of recent events
    baseline = [
        now - timedelta(days=d, hours=1)
        for d in range(2, 31)
        if (now - timedelta(days=d, hours=1)).weekday() >= 5
    ]
    burst = [now - timedelta(hours=1, minutes=i) for i in range(20)]
    history = {"weekend_auto": baseline + burst}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=7,
        min_expected_events=0,
    )
    issues = await monitor.validate_automations(
        [_automation("weekend_auto", "Weekend Party Lights")]
    )
    overactive = [
        i for i in issues if i.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    ]
    assert overactive == [], (
        "Should not flag overactive when no baseline events on current day type"
    )


@pytest.mark.asyncio
async def test_overactive_skipped_when_no_baseline_events_on_current_weekday(
    hass: HomeAssistant,
) -> None:
    """Overactive should not fire on weekdays with zero historical activity."""
    # Tuesday 12:00 UTC
    now = datetime(2026, 2, 17, 12, 0, tzinfo=UTC)
    baseline = [
        datetime(2026, 1, 21, 9, 0, tzinfo=UTC),
        datetime(2026, 1, 28, 9, 0, tzinfo=UTC),
        datetime(2026, 2, 4, 9, 0, tzinfo=UTC),
    ]
    burst = [now - timedelta(hours=1, minutes=i) for i in range(20)]
    history = {"weekly_auto": baseline + burst}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=7,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [_automation("weekly_auto", "Weekly Auto")]
    )
    overactive = [
        i for i in issues if i.issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    ]

    assert overactive == [], (
        "Should not flag overactive when current weekday has no baseline evidence"
    )


@pytest.mark.asyncio
async def test_validate_automations_does_not_use_recorder_path(
    hass: HomeAssistant,
) -> None:
    """validate_automations should always use event store, never recorder."""
    now = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.5,
        warmup_samples=7,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Kitchen")]
    )
    assert issues == []
