"""Tests for runtime automation health monitoring."""

from __future__ import annotations

import json
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


def test_training_and_current_rows_have_same_features() -> None:
    """Training rows and current row must have identical feature keys."""
    now = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
    baseline_start = now - timedelta(days=30)
    day_counts = [1] * 30

    train_rows = RuntimeHealthMonitor._build_training_rows(day_counts, baseline_start)
    current_row = RuntimeHealthMonitor._build_current_row(
        [now - timedelta(hours=1)], 1.0, now
    )

    assert set(train_rows[0].keys()) == set(current_row.keys()), (
        f"Feature mismatch: training={sorted(train_rows[0].keys())} "
        f"vs current={sorted(current_row.keys())}"
    )


def test_river_detector_learns_incrementally() -> None:
    """Detector must persist models and only learn new rows on subsequent calls."""
    from unittest.mock import MagicMock, patch

    from custom_components.autodoctor.runtime_monitor import _RiverAnomalyDetector

    detector = _RiverAnomalyDetector()
    row = {"count_24h": 1.0, "dow_sin": 0.0, "dow_cos": 1.0}
    rows_10 = [row] * 9 + [{"count_24h": 5.0, "dow_sin": 0.0, "dow_cos": 1.0}]

    mock_model = MagicMock()
    mock_model.score_one.return_value = 0.5

    with patch("custom_components.autodoctor.runtime_monitor.anomaly") as mock_anomaly:
        mock_anomaly.HalfSpaceTrees.return_value = mock_model

        # First call: should learn 9 training rows (all except the last)
        detector.score_current("auto.test", rows_10)
        assert mock_model.learn_one.call_count == 9

        mock_model.learn_one.reset_mock()

        # Second call with 1 extra training row appended before the current row
        rows_11 = [*rows_10[:-1], row, rows_10[-1]]
        detector.score_current("auto.test", rows_11)
        # Should only learn the 1 new row, not re-learn the original 9
        assert mock_model.learn_one.call_count == 1


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
