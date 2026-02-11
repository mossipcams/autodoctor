"""Tests for runtime automation health monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.models import IssueType
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


class _FixedScoreDetector:
    """Test detector that returns a fixed anomaly score."""

    def __init__(self, score: float) -> None:
        self._score = score

    def score_current(self, automation_id: str, train_rows: list[dict[str, float]]) -> float:
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
async def test_runtime_monitor_skips_when_warmup_insufficient(hass: HomeAssistant) -> None:
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
    history = {
        "runtime_test": [
            now - timedelta(days=d, hours=2) for d in range(2, 31)
        ]
    }
    monitor = _TestRuntimeMonitor(
        hass,
        history=history,
        now=now,
        warmup_samples=7,
        anomaly_threshold=0.8,
        min_expected_events=0,
    )

    issues = await monitor.validate_automations([_automation("runtime_test", "Kitchen Motion")])
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

    issues = await monitor.validate_automations([_automation("runtime_test", "Hallway Lights")])
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
