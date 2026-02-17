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
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
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


def _feature_row(
    count_24h: float,
    *,
    hour_ratio_30d: float = 1.0,
    gap_vs_median: float = 1.0,
    other_automations_5m: float = 0.0,
) -> dict[str, float]:
    """Build a runtime feature row aligned with monitor feature schema."""
    return {
        "rolling_24h_count": count_24h,
        "rolling_7d_count": count_24h * 6.0,
        "hour_ratio_30d": hour_ratio_30d,
        "gap_vs_median": gap_vs_median,
        "is_weekend": 0.0,
        "other_automations_5m": other_automations_5m,
    }


def test_bocpd_context_gap_signal_amplifies_stalled_score() -> None:
    """Large gap-vs-median should increase anomaly confidence for stalls."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    baseline = [_feature_row(6.0 + float(i % 2)) for i in range(28)]

    score_small_gap = detector.score_current(
        "automation.stalled.small_gap",
        [*baseline, _feature_row(0.0, gap_vs_median=1.0)],
    )
    score_large_gap = detector.score_current(
        "automation.stalled.large_gap",
        [*baseline, _feature_row(0.0, gap_vs_median=8.0)],
    )

    assert score_large_gap > score_small_gap


def test_bocpd_context_hour_ratio_amplifies_overactive_score() -> None:
    """High same-hour ratio should raise confidence for overactive anomalies."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    baseline = [_feature_row(7.0 + float(i % 2)) for i in range(28)]

    score_typical_hour = detector.score_current(
        "automation.overactive.typical",
        [*baseline, _feature_row(30.0, hour_ratio_30d=1.0)],
    )
    score_hot_hour = detector.score_current(
        "automation.overactive.hot_hour",
        [*baseline, _feature_row(30.0, hour_ratio_30d=5.0)],
    )

    assert score_hot_hour > score_typical_hour


def test_bocpd_context_global_activity_dampens_overactive_score() -> None:
    """Broad cross-automation activity should dampen overactive confidence."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    baseline = [_feature_row(7.0 + float(i % 2)) for i in range(28)]

    score_isolated = detector.score_current(
        "automation.overactive.isolated",
        [*baseline, _feature_row(30.0, other_automations_5m=0.0)],
    )
    score_global_surge = detector.score_current(
        "automation.overactive.global",
        [*baseline, _feature_row(30.0, other_automations_5m=25.0)],
    )

    assert score_global_surge < score_isolated


def test_bocpd_changepoint_mass_increases_for_surprising_observation() -> None:
    """Highly surprising counts should increase changepoint posterior mass."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    state = detector.initial_state()
    for observed in [5] * 32:
        detector.update_state(state, observed)

    detector.update_state(state, 80)

    assert state["run_length_probs"][0] > detector.hazard_rate


def test_bocpd_extreme_scores_are_monotonic_for_larger_deviations() -> None:
    """Larger overactive deviations should produce larger anomaly scores."""
    detector = _BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    baseline = [_feature_row(20.0 + float(i % 2)) for i in range(40)]

    score_100 = detector.score_current(
        "automation.extreme.100",
        [*baseline, _feature_row(100.0)],
    )
    score_400 = detector.score_current(
        "automation.extreme.400",
        [*baseline, _feature_row(400.0)],
    )
    score_1200 = detector.score_current(
        "automation.extreme.1200",
        [*baseline, _feature_row(1200.0)],
    )

    assert score_100 < score_400 < score_1200
