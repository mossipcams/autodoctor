"""Tests for runtime automation health monitoring."""

from __future__ import annotations

import json
import logging
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
        self, automation_id: str, train_rows: list[dict[str, float]]
    ) -> float:
        return self._score


class _TestRuntimeMonitor(RuntimeHealthMonitor):
    """Runtime monitor with injectable history for tests."""

    def __init__(
        self,
        hass: HomeAssistant,
        history: dict[str, list[datetime]],
        now: datetime,
        score: float = 0.95,
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
        anomaly_threshold=0.8,
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
        anomaly_threshold=0.8,
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
        score=0.95,
        warmup_samples=7,
        anomaly_threshold=0.8,
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
        score=0.95,
        warmup_samples=7,
        anomaly_threshold=0.8,
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
    day_counts = [1] * 30
    expected = 1.0

    train_rows = RuntimeHealthMonitor._build_training_rows(
        day_counts, baseline_start, expected
    )
    current_row = RuntimeHealthMonitor._build_current_row(
        [now - timedelta(hours=1)], expected, now
    )

    assert set(train_rows[0].keys()) == set(current_row.keys()), (
        f"Feature mismatch: training={sorted(train_rows[0].keys())} "
        f"vs current={sorted(current_row.keys())}"
    )


def test_isolation_forest_detector_fits_training_and_scores_current() -> None:
    """IsolationForest detector should fit on training rows and score the current row."""
    from custom_components.autodoctor.runtime_monitor import (
        _IsolationForestDetector,
    )

    detector = _IsolationForestDetector()
    row = {"count_24h": 1.0, "ratio": 1.0}
    rows = [row] * 31  # 30 training + 1 current

    mock_model = MagicMock()
    mock_model.score_samples.return_value = [-0.3]

    with patch(
        "custom_components.autodoctor.runtime_monitor.IsolationForest"
    ) as mock_cls:
        mock_cls.return_value = mock_model
        score = detector.score_current("auto.test", rows)

    # score_samples returns negative values; detector normalizes to [0, 1]
    assert 0.0 <= score <= 1.0
    fit_arg = mock_model.fit.call_args.args[0]
    score_arg = mock_model.score_samples.call_args.args[0]
    assert len(fit_arg) == 30
    assert len(score_arg) == 1


def test_isolation_forest_detector_refits_each_call() -> None:
    """IsolationForest detector should refit on full training rows each call."""
    from custom_components.autodoctor.runtime_monitor import (
        _IsolationForestDetector,
    )

    detector = _IsolationForestDetector()
    row = {"count_24h": 1.0, "ratio": 1.0}
    rows_10 = [row] * 9 + [{"count_24h": 5.0, "ratio": 5.0}]

    mock_model = MagicMock()
    mock_model.score_samples.return_value = [-0.3]

    with patch(
        "custom_components.autodoctor.runtime_monitor.IsolationForest"
    ) as mock_cls:
        mock_cls.return_value = mock_model
        detector.score_current("auto.test", rows_10)

        rows_11 = [*rows_10[:-1], row, rows_10[-1]]
        detector.score_current("auto.test", rows_11)

    assert mock_model.fit.call_count == 2
    assert len(mock_model.fit.call_args_list[0].args[0]) == 9
    assert len(mock_model.fit.call_args_list[1].args[0]) == 10


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
            anomaly_threshold=0.8,
            min_expected_events=1,
            overactive_factor=3.0,
        )

    assert "baseline_days=30" in caplog.text
    assert "warmup_samples=14" in caplog.text
    assert "anomaly_threshold=0.8" in caplog.text


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
async def test_validate_automations_logs_sklearn_unavailable(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Should log when sklearn detector is unavailable."""
    monitor = RuntimeHealthMonitor(hass, detector=None)
    # Force detector to None to simulate sklearn unavailable
    monitor._detector = None

    with caplog.at_level(
        logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
    ):
        await monitor.validate_automations([_automation("a1")])

    assert "Detector unavailable" in caplog.text


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


def test_isolation_forest_detector_logs_fit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """IsolationForest detector should log when fitting a model."""
    from custom_components.autodoctor.runtime_monitor import (
        _IsolationForestDetector,
    )

    detector = _IsolationForestDetector()
    row = {"count_24h": 1.0, "ratio": 1.0}
    rows = [row] * 3

    mock_model = MagicMock()
    mock_model.score_samples.return_value = [-0.3]

    with (
        caplog.at_level(
            logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
        ),
        patch(
            "custom_components.autodoctor.runtime_monitor.IsolationForest"
        ) as mock_cls,
    ):
        mock_cls.return_value = mock_model
        detector.score_current("auto.test", rows)

    assert "Fitting IsolationForest for 'auto.test' on 2 rows" in caplog.text


def test_isolation_forest_detector_handles_window_changes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """IsolationForest detector should work when history shrinks between calls."""
    from custom_components.autodoctor.runtime_monitor import (
        _IsolationForestDetector,
    )

    detector = _IsolationForestDetector()
    row = {"count_24h": 1.0, "ratio": 1.0}

    mock_model = MagicMock()
    mock_model.score_samples.return_value = [-0.3]

    with patch(
        "custom_components.autodoctor.runtime_monitor.IsolationForest"
    ) as mock_cls:
        mock_cls.return_value = mock_model
        detector.score_current("auto.test", [row] * 5)

    with (
        caplog.at_level(
            logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
        ),
        patch(
            "custom_components.autodoctor.runtime_monitor.IsolationForest"
        ) as mock_cls,
    ):
        mock_cls.return_value = mock_model
        detector.score_current("auto.test", [row] * 3)

    assert "Fitting IsolationForest for 'auto.test' on 2 rows" in caplog.text


def test_isolation_forest_detector_logs_score(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """IsolationForest detector should log score result."""
    from custom_components.autodoctor.runtime_monitor import (
        _IsolationForestDetector,
    )

    detector = _IsolationForestDetector()
    row = {"count_24h": 1.0, "ratio": 1.0}
    rows = [row] * 5

    mock_model = MagicMock()
    mock_model.score_samples.return_value = [-0.42]

    with (
        caplog.at_level(
            logging.DEBUG, logger="custom_components.autodoctor.runtime_monitor"
        ),
        patch(
            "custom_components.autodoctor.runtime_monitor.IsolationForest"
        ) as mock_cls,
    ):
        mock_cls.return_value = mock_model
        detector.score_current("auto.test", rows)

    assert "Scored 'auto.test': 0.420" in caplog.text


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
        score=0.95,
        warmup_samples=7,
        anomaly_threshold=0.8,
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
        score=0.95,
        warmup_samples=7,
        anomaly_threshold=0.8,
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
