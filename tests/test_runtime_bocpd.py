"""BOCPD detector and runtime BOCPD integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.autodoctor import const
from custom_components.autodoctor.runtime_health_state_store import (
    RuntimeHealthStateStore,
)
from custom_components.autodoctor.runtime_monitor import (
    RuntimeHealthMonitor,
    _BOCPDDetector,
)


def _build_monitor(
    tmp_path: Path,
    now: datetime,
    **kwargs: object,
) -> RuntimeHealthMonitor:
    hass = MagicMock()
    store = RuntimeHealthStateStore(path=tmp_path / "runtime_bocpd_state.json")
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        runtime_state_store=store,
        telemetry_db_path=None,
        warmup_samples=0,
        min_expected_events=0,
        **kwargs,
    )


def test_bocpd_constants_exist() -> None:
    """BOCPD tuning defaults should exist in constants module."""
    assert isinstance(const.DEFAULT_RUNTIME_HEALTH_HAZARD_RATE, float)
    assert const.DEFAULT_RUNTIME_HEALTH_HAZARD_RATE > 0.0

    assert isinstance(const.DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH, int)
    assert const.DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH >= 8

    assert isinstance(const.DEFAULT_RUNTIME_HEALTH_GAP_THRESHOLD_MULTIPLIER, float)
    assert const.DEFAULT_RUNTIME_HEALTH_GAP_THRESHOLD_MULTIPLIER > 1.0


def test_runtime_monitor_accepts_bocpd_config(tmp_path: Path) -> None:
    """Runtime monitor should accept explicit BOCPD runtime tuning."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = _build_monitor(
        tmp_path,
        now,
        hazard_rate=0.08,
        max_run_length=64,
        gap_threshold_multiplier=1.8,
    )

    assert monitor.hazard_rate == 0.08
    assert monitor.max_run_length == 64
    assert monitor.gap_threshold_multiplier == 1.8


def test_bocpd_nb_predictive_returns_valid_pmf() -> None:
    """Predictive PMF should be non-negative and approximately normalized."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    state = detector.initial_state()
    for observed in [2, 3, 2, 4, 3, 3]:
        detector.update_state(state, observed)

    pmf = [detector.predictive_pmf_for_count(state, count) for count in range(40)]
    assert all(value >= 0.0 for value in pmf)
    assert sum(pmf) == pytest.approx(1.0, rel=1e-3, abs=1e-3)


def test_bocpd_update_cold_start_produces_valid_run_length_dist() -> None:
    """Cold-start update should produce a normalized run-length distribution."""
    detector = _BOCPDDetector(hazard_rate=0.1, max_run_length=32)
    state = detector.initial_state()

    detector.update_state(state, 4)

    probs = state["run_length_probs"]
    assert probs
    assert all(0.0 <= value <= 1.0 for value in probs)
    assert sum(probs) == pytest.approx(1.0)
    assert state["observations"][-1] == 4
    assert state["map_run_length"] >= 0
    assert state["expected_rate"] > 0.0


def test_bocpd_run_length_probs_normalized_after_multiple_updates() -> None:
    """Posterior run-length distribution should stay normalized over time."""
    detector = _BOCPDDetector(hazard_rate=0.07, max_run_length=24)
    state = detector.initial_state()

    for observed in [1, 2, 0, 1, 3, 2, 1, 2, 1, 0, 2]:
        detector.update_state(state, observed)
        probs = state["run_length_probs"]
        assert sum(probs) == pytest.approx(1.0, abs=1e-9)
        assert all(value >= 0.0 for value in probs)


def test_bocpd_truncates_at_max_run_length() -> None:
    """Run-length posterior and retained observations should respect truncation."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=4)
    state = detector.initial_state()

    for _ in range(30):
        detector.update_state(state, 1)

    assert len(state["run_length_probs"]) <= 5
    assert len(state["observations"]) <= 4
    assert state["map_run_length"] <= 4


def test_bocpd_detects_rate_shift() -> None:
    """Tail count should score higher than in-regime count for same baseline."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)

    def _row(count_24h: float) -> dict[str, float]:
        return {
            "rolling_24h_count": count_24h,
            "rolling_7d_count": count_24h * 6.0,
            "hour_ratio_30d": 1.0,
            "gap_vs_median": 1.0,
            "is_weekend": 0.0,
            "other_automations_5m": 0.0,
        }

    baseline = [_row(3.0 + float(i % 2)) for i in range(25)]
    score_normal = detector.score_current("automation.normal", [*baseline, _row(3.0)])
    score_shifted = detector.score_current(
        "automation.shifted", [*baseline, _row(20.0)]
    )

    assert score_shifted > score_normal


def test_bocpd_expected_rate_approximates_mean_in_stable_regime() -> None:
    """Expected rate should converge near the empirical mean in stable data."""
    detector = _BOCPDDetector(hazard_rate=0.03, max_run_length=64)
    state = detector.initial_state()

    stable_counts = [5, 4, 6, 5, 5, 4, 6, 5] * 6
    for observed in stable_counts:
        detector.update_state(state, observed)

    expected_rate = detector.expected_rate(state)
    assert expected_rate == pytest.approx(5.0, rel=0.35)


def test_bocpd_score_current_implements_detector_protocol() -> None:
    """Detector should provide score_current compatible with _Detector protocol."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=32)
    rows = [{"rolling_24h_count": float(value)} for value in [1, 2, 2, 3, 1, 2]]

    score = detector.score_current("automation.protocol", rows, window_size=16)
    assert isinstance(score, float)
    assert score >= 0.0
