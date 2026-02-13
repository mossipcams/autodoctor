"""Tests for runtime automation health monitoring."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.models import IssueType
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
async def test_runtime_monitor_flags_stalled_automation(hass: HomeAssistant) -> None:
    """Automation with expected activity but no recent triggers should be flagged."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=7,
        anomaly_threshold=1.3,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Kitchen Motion")]
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_STALLED
    assert issues[0].automation_id == "automation.runtime_test"


@pytest.mark.asyncio
async def test_runtime_monitor_flags_overactive_automation(hass: HomeAssistant) -> None:
    """Automation with extreme recent activity vs baseline should be flagged."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline = [now - timedelta(days=d, hours=1) for d in range(2, 31)]
    burst = [now - timedelta(hours=1, minutes=i) for i in range(20)]
    history = {"runtime_test": baseline + burst}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=7,
        anomaly_threshold=1.3,
        min_expected_events=0,
        overactive_factor=3.0,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Hallway Lights")]
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE
    assert issues[0].automation_id == "automation.runtime_test"


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
        anomaly_threshold=1.3,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [
            {
                "id": "01HTYV52MPM2Q2PY6EW3S9AFRF",
                "alias": "Kitchen Motion",
                "entity_id": "automation.kitchen_motion",
            }
        ]
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_STALLED
    assert issues[0].automation_id == "automation.kitchen_motion"


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
        anomaly_threshold=1.3,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations(
        [{"alias": "No ID Automation", "entity_id": "automation.no_id"}]
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_STALLED
    assert issues[0].automation_id == "automation.no_id"


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


def test_runtime_monitor_default_anomaly_threshold_matches_log10_scale(
    hass: HomeAssistant,
) -> None:
    """Default anomaly_threshold should remain calibrated to log10 tail scale."""
    monitor = RuntimeHealthMonitor(hass)
    assert monitor.anomaly_threshold == 1.3


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
            anomaly_threshold=1.3,
            min_expected_events=1,
            overactive_factor=3.0,
        )

    assert "baseline_days=30" in caplog.text
    assert "warmup_samples=14" in caplog.text
    assert "anomaly_threshold=1.3" in caplog.text


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
async def test_validate_automations_records_recorder_query_failure_stat(
    hass: HomeAssistant,
) -> None:
    """Recorder fetch failures should be reflected in run stats."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    monitor = RuntimeHealthMonitor(
        hass,
        detector=_FixedScoreDetector(0.0),
        now_factory=lambda: now,
    )
    hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("db unavailable"))

    await monitor.validate_automations([_automation("runtime_test", "Runtime Test")])

    stats = monitor.get_last_run_stats()
    assert stats["recorder_query_failed"] == 1


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
async def test_validate_automations_logs_stalled_detection(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log at INFO level when a stalled automation is detected."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    # Baseline with daily events, no recent events -> stalled
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.0,
        warmup_samples=7,
        anomaly_threshold=1.3,
        min_expected_events=0,
    )

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        issues = await monitor.validate_automations(
            [_automation("runtime_test", "Kitchen Motion")]
        )

    assert len(issues) == 1
    assert "Stalled: 'Kitchen Motion'" in caplog.text
    assert "0 triggers in 24h" in caplog.text


@pytest.mark.asyncio
async def test_validate_automations_logs_overactive_detection(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log at INFO level when an overactive automation is detected."""
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
        anomaly_threshold=1.3,
        min_expected_events=0,
        overactive_factor=3.0,
    )

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        issues = await monitor.validate_automations(
            [_automation("runtime_test", "Hallway Lights")]
        )

    assert len(issues) == 1
    assert "Overactive: 'Hallway Lights'" in caplog.text
    assert "20 triggers in 24h" in caplog.text


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
async def test_runtime_monitor_uses_separate_thresholds(
    hass: HomeAssistant,
) -> None:
    """Overactive should use its own threshold independent from stalled threshold."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline = [now - timedelta(days=d, hours=1) for d in range(2, 31)]
    burst = [now - timedelta(hours=1, minutes=i) for i in range(20)]
    history = {"runtime_test": baseline + burst}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=1.5,
        warmup_samples=7,
        min_expected_events=0,
        overactive_factor=3.0,
        stalled_threshold=2.0,
        overactive_threshold=1.0,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Hallway Lights")]
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.RUNTIME_AUTOMATION_OVERACTIVE


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
        stalled_threshold=1.3,
        dismissed_threshold_multiplier=1.25,
    )

    issues = await monitor.validate_automations(
        [_automation("runtime_test", "Kitchen Motion")]
    )
    assert issues == []


@pytest.mark.asyncio
async def test_runtime_monitor_logs_scores_to_sqlite(
    hass: HomeAssistant, tmp_path
) -> None:
    """Every scored automation should write telemetry row with score and features."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}
    db_path = tmp_path / "runtime_scores.sqlite"

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.72,
        warmup_samples=7,
        min_expected_events=0,
        telemetry_db_path=str(db_path),
    )

    await monitor.validate_automations([_automation("runtime_test", "Kitchen Motion")])

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT automation_id, score, features_json FROM runtime_health_scores"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "automation.runtime_test"
    assert row[1] == pytest.approx(0.72)
    assert "rolling_24h_count" in json.loads(row[2])


@pytest.mark.asyncio
async def test_telemetry_write_offloaded_to_executor(
    hass: HomeAssistant, tmp_path
) -> None:
    """Telemetry SQLite writes must run in executor to avoid blocking the event loop."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}
    db_path = tmp_path / "runtime_scores.sqlite"

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.72,
        warmup_samples=7,
        min_expected_events=0,
        telemetry_db_path=str(db_path),
    )

    with patch.object(
        hass, "async_add_executor_job", wraps=hass.async_add_executor_job
    ) as spy:
        await monitor.validate_automations(
            [_automation("runtime_test", "Kitchen Motion")]
        )
        telemetry_calls = [
            c for c in spy.call_args_list if "_log_score_telemetry" in str(c.args[0])
        ]
        assert len(telemetry_calls) > 0, (
            "Telemetry write must be offloaded via async_add_executor_job"
        )


@pytest.mark.asyncio
async def test_telemetry_create_table_runs_only_once(
    hass: HomeAssistant, tmp_path
) -> None:
    """CREATE TABLE DDL should execute only once, not on every telemetry write."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {
        "runtime_a": [now - timedelta(days=d, hours=2) for d in range(2, 31)],
        "runtime_b": [now - timedelta(days=d, hours=3) for d in range(2, 31)],
    }
    db_path = tmp_path / "runtime_scores.sqlite"

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=0.5,
        warmup_samples=7,
        min_expected_events=0,
        telemetry_db_path=str(db_path),
    )

    await monitor.validate_automations(
        [_automation("runtime_a", "Auto A"), _automation("runtime_b", "Auto B")]
    )

    assert monitor._telemetry_table_ensured is True

    # Run again — should still be True from first pass, not re-created
    call_count_before = 0
    conn = sqlite3.connect(db_path)
    try:
        # Count rows to verify both automations wrote telemetry
        call_count_before = conn.execute(
            "SELECT COUNT(*) FROM runtime_health_scores"
        ).fetchone()[0]
    finally:
        conn.close()
    assert call_count_before == 2

    await monitor.validate_automations(
        [_automation("runtime_a", "Auto A"), _automation("runtime_b", "Auto B")]
    )
    assert monitor._telemetry_table_ensured is True


def test_fixed_score_detector_accepts_window_size_kwarg() -> None:
    """Test detector must accept window_size to match the _Detector protocol."""
    detector = _FixedScoreDetector(0.5)
    rows = [{"rolling_24h_count": 1.0}] * 3
    score = detector.score_current("auto.test", rows, window_size=32)
    assert score == 0.5


def test_telemetry_table_ensured_flag_protected_by_lock() -> None:
    """RuntimeHealthMonitor should have a threading.Lock for telemetry table creation."""
    import threading

    hass = MagicMock()
    monitor = RuntimeHealthMonitor(
        hass,
        detector=_FixedScoreDetector(0.5),
        now_factory=lambda: datetime(2026, 2, 11, 12, 0, tzinfo=UTC),
    )
    assert hasattr(monitor, "_telemetry_lock")
    assert isinstance(monitor._telemetry_lock, type(threading.Lock()))


def test_telemetry_table_creation_acquires_lock(tmp_path) -> None:
    """The _telemetry_table_ensured check/set must be protected by _telemetry_lock."""

    hass = MagicMock()
    db_path = tmp_path / "runtime_scores.sqlite"
    monitor = RuntimeHealthMonitor(
        hass,
        detector=_FixedScoreDetector(0.5),
        now_factory=lambda: datetime(2026, 2, 11, 12, 0, tzinfo=UTC),
        telemetry_db_path=str(db_path),
    )

    acquired_count = 0
    original_lock = monitor._telemetry_lock

    class _TrackingLock:
        def __enter__(self) -> _TrackingLock:
            nonlocal acquired_count
            acquired_count += 1
            original_lock.acquire()
            return self

        def __exit__(self, *args: object) -> None:
            original_lock.release()

    monitor._telemetry_lock = _TrackingLock()  # type: ignore[assignment]

    monitor._log_score_telemetry(
        automation_id="automation.test",
        score=0.5,
        now=datetime(2026, 2, 11, 12, 0, tzinfo=UTC),
        features={"a": 1.0},
    )
    assert acquired_count >= 1, (
        "_telemetry_lock must be acquired during telemetry write"
    )


def test_telemetry_deletes_rows_older_than_retention_days(tmp_path) -> None:
    """Telemetry writes should delete rows older than the retention period."""
    hass = MagicMock()
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    db_path = tmp_path / "runtime_scores.sqlite"

    monitor = RuntimeHealthMonitor(
        hass,
        detector=_FixedScoreDetector(0.5),
        now_factory=lambda: now,
        telemetry_db_path=str(db_path),
    )

    # Pre-populate DB with old and recent rows
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_health_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            automation_id TEXT NOT NULL,
            score REAL NOT NULL,
            features_json TEXT NOT NULL
        )
        """
    )
    old_ts = (now - timedelta(days=100)).isoformat()
    recent_ts = (now - timedelta(days=10)).isoformat()
    conn.execute(
        "INSERT INTO runtime_health_scores (ts, automation_id, score, features_json) VALUES (?, ?, ?, ?)",
        (old_ts, "automation.old", 0.5, "{}"),
    )
    conn.execute(
        "INSERT INTO runtime_health_scores (ts, automation_id, score, features_json) VALUES (?, ?, ?, ?)",
        (recent_ts, "automation.recent", 0.6, "{}"),
    )
    conn.commit()
    conn.close()

    # Mark table as already ensured since we created it manually
    monitor._telemetry_table_ensured = True

    # Write a new telemetry row, which should trigger cleanup
    monitor._log_score_telemetry(
        automation_id="automation.test",
        score=0.7,
        now=now,
        features={"a": 1.0},
    )

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT automation_id FROM runtime_health_scores ORDER BY automation_id"
    ).fetchall()
    conn.close()

    automation_ids = [r[0] for r in rows]
    assert "automation.old" not in automation_ids, (
        "Rows older than 90 days should be deleted"
    )
    assert "automation.recent" in automation_ids
    assert "automation.test" in automation_ids


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


def test_telemetry_retention_days_constant_exists() -> None:
    """Module should expose a _TELEMETRY_RETENTION_DAYS constant set to 90."""
    from custom_components.autodoctor.runtime_monitor import _TELEMETRY_RETENTION_DAYS

    assert _TELEMETRY_RETENTION_DAYS == 90


def test_dismissed_multiplier_accepts_suppression_store_parameter() -> None:
    """_dismissed_multiplier should accept an explicit suppression_store parameter."""
    hass = MagicMock()
    hass.data = {}  # No store in hass.data

    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=True)

    monitor = RuntimeHealthMonitor(
        hass,
        detector=_FixedScoreDetector(0.5),
        now_factory=lambda: datetime(2026, 2, 11, 12, 0, tzinfo=UTC),
        dismissed_threshold_multiplier=1.5,
    )

    # When passing suppression_store directly, it should be used instead of hass.data lookup
    result = monitor._dismissed_multiplier(
        "automation.test", suppression_store=suppression_store
    )
    assert result == 1.5
    suppression_store.is_suppressed.assert_called()


@pytest.mark.asyncio
async def test_validate_automations_passes_suppression_store_to_dismissed_multiplier(
    hass: HomeAssistant,
) -> None:
    """validate_automations should extract store once and pass it to _dismissed_multiplier."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    history = {"runtime_test": [now - timedelta(days=d, hours=2) for d in range(2, 31)]}

    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=False)
    hass.data["autodoctor"] = {"suppression_store": suppression_store}

    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        score=2.0,
        warmup_samples=7,
        min_expected_events=0,
    )

    with patch.object(
        monitor, "_dismissed_multiplier", wraps=monitor._dismissed_multiplier
    ) as spy:
        await monitor.validate_automations([_automation("runtime_test", "Kitchen")])
        assert spy.call_count == 1
        # Verify suppression_store was passed as keyword argument
        call_kwargs = spy.call_args[1]
        assert "suppression_store" in call_kwargs
        assert call_kwargs["suppression_store"] is suppression_store


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


def test_legacy_row_builders_removed() -> None:
    """Legacy _build_training_rows and _build_current_row should not exist.

    These were replaced by _build_training_rows_from_events and _build_feature_row.
    """
    assert not hasattr(RuntimeHealthMonitor, "_build_training_rows"), (
        "_build_training_rows is dead code — use _build_training_rows_from_events"
    )
    assert not hasattr(RuntimeHealthMonitor, "_build_current_row"), (
        "_build_current_row is dead code — use _build_feature_row"
    )


def test_legacy_gamma_poisson_class_removed() -> None:
    """Legacy runtime detector should no longer be exported."""
    from custom_components.autodoctor import runtime_monitor

    assert not hasattr(runtime_monitor, "_GammaPoissonDetector")
