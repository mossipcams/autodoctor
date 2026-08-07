"""BOCPD detector and runtime BOCPD integration tests."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from custom_components.autodoctor.bocpd_detector import (
    DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
    DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
    BOCPDDetector,
)
from tests.conftest import build_runtime_monitor


def test_bocpd_constants_exist() -> None:
    """BOCPD tuning defaults should exist in bocpd_detector module."""
    assert isinstance(DEFAULT_RUNTIME_HEALTH_HAZARD_RATE, float)
    assert DEFAULT_RUNTIME_HEALTH_HAZARD_RATE > 0.0

    assert isinstance(DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH, int)
    assert DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH >= 8


def test_runtime_monitor_accepts_bocpd_config() -> None:
    """Runtime monitor should accept explicit BOCPD runtime tuning."""
    now = datetime(2026, 2, 13, 12, 0, tzinfo=UTC)
    monitor = build_runtime_monitor(
        now,
        hazard_rate=0.08,
        max_run_length=64,
    )

    assert monitor.hazard_rate == 0.08
    assert monitor.max_run_length == 64


def test_bocpd_nb_predictive_returns_valid_pmf() -> None:
    """Predictive PMF should be non-negative and approximately normalized."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    state = detector.initial_state()
    for observed in [2, 3, 2, 4, 3, 3]:
        detector.update_state(state, observed)

    pmf = [detector.predictive_pmf_for_count(state, count) for count in range(40)]
    assert all(value >= 0.0 for value in pmf)
    assert sum(pmf) == pytest.approx(1.0, rel=1e-3, abs=1e-3)


def test_bocpd_update_cold_start_produces_valid_run_length_dist() -> None:
    """Cold-start update should produce a normalized run-length distribution."""
    detector = BOCPDDetector(hazard_rate=0.1, max_run_length=32)
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
    detector = BOCPDDetector(hazard_rate=0.07, max_run_length=24)
    state = detector.initial_state()

    for observed in [1, 2, 0, 1, 3, 2, 1, 2, 1, 0, 2]:
        detector.update_state(state, observed)
        probs = state["run_length_probs"]
        assert sum(probs) == pytest.approx(1.0, abs=1e-9)
        assert all(value >= 0.0 for value in probs)


def test_bocpd_truncates_at_max_run_length() -> None:
    """Run-length posterior and retained observations should respect truncation."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=4)
    state = detector.initial_state()

    for _ in range(30):
        detector.update_state(state, 1)

    assert len(state["run_length_probs"]) <= 5
    assert len(state["observations"]) <= 4
    assert state["map_run_length"] <= 4


def test_bocpd_detects_rate_shift() -> None:
    """Tail count should score higher than in-regime count for same baseline."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)

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
    detector = BOCPDDetector(hazard_rate=0.03, max_run_length=64)
    state = detector.initial_state()

    stable_counts = [5, 4, 6, 5, 5, 4, 6, 5] * 6
    for observed in stable_counts:
        detector.update_state(state, observed)

    expected_rate = detector.expected_rate(state)
    assert expected_rate == pytest.approx(5.0, rel=0.35)


def test_bocpd_score_current_exposes_last_expected_rate() -> None:
    """score_current should publish the filtered-training expected rate."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    rows = [_feature_row(5.0) for _ in range(24)] + [_feature_row(5.0)]

    detector.score_current("automation.expected", rows)

    assert detector.last_expected_rate == pytest.approx(5.0, rel=0.35)


def test_bocpd_score_current_implements_detector_protocol() -> None:
    """Detector should provide score_current compatible with Detector protocol."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=32)
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
    is_weekend: float = 0.0,
    weekday: float = 0.0,
) -> dict[str, float]:
    """Build a runtime feature row aligned with monitor feature schema."""
    return {
        "rolling_24h_count": count_24h,
        "rolling_7d_count": count_24h * 6.0,
        "hour_ratio_30d": hour_ratio_30d,
        "gap_vs_median": gap_vs_median,
        "is_weekend": is_weekend,
        "weekday": weekday,
        "other_automations_5m": other_automations_5m,
    }


def test_bocpd_upper_tail_under_count_scores_near_zero() -> None:
    """Upper-tail scoring should not treat under-counts as overactive anomalies."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    baseline = [_feature_row(5.0 + float(i % 2)) for i in range(30)]

    score_under = detector.score_current(
        "automation.upper_tail.under",
        [*baseline, _feature_row(0.0)],
    )
    score_over = detector.score_current(
        "automation.upper_tail.over",
        [*baseline, _feature_row(20.0)],
    )

    assert score_under < 1.0
    assert score_over > score_under * 3.0


def test_bocpd_context_gap_no_longer_amplifies_under_count() -> None:
    """Gap context must not inflate under-count scores (stall path removed)."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    baseline = [_feature_row(6.0 + float(i % 2)) for i in range(28)]

    score_small_gap = detector.score_current(
        "automation.stalled.small_gap",
        [*baseline, _feature_row(0.0, gap_vs_median=1.0)],
    )
    score_large_gap = detector.score_current(
        "automation.stalled.large_gap",
        [*baseline, _feature_row(0.0, gap_vs_median=8.0)],
    )

    assert score_large_gap == pytest.approx(score_small_gap, abs=1e-9)


def test_bocpd_day_type_filter_reduces_cross_weekend_false_alarm() -> None:
    """Weekday scoring should ignore busy weekend history when enough weekdays exist."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    weekday_quiet = [
        _feature_row(3.0 + float(i % 2), is_weekend=0.0) for i in range(20)
    ]
    weekend_busy = [
        _feature_row(25.0 + float(i % 2), is_weekend=1.0) for i in range(10)
    ]
    mixed = weekday_quiet + weekend_busy
    current = _feature_row(4.0, is_weekend=0.0)

    score_filtered = detector.score_current(
        "automation.day_type.filtered",
        [*mixed, current],
    )
    # Relabel weekends as weekdays so the filter keeps the busy weekend counts.
    mixed_as_weekday = [{**row, "is_weekend": 0.0} for row in mixed]
    score_mixed = detector.score_current(
        "automation.day_type.mixed",
        [*mixed_as_weekday, current],
    )

    assert score_filtered < score_mixed
    assert score_filtered < 2.0


def test_bocpd_day_type_filter_falls_back_when_sparse() -> None:
    """Sparse same day-type history should fall back to full training window."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    weekday_rows = [_feature_row(5.0 + float(i % 2), is_weekend=0.0) for i in range(20)]
    weekend_rows = [_feature_row(6.0, is_weekend=1.0) for _ in range(3)]
    current = _feature_row(30.0, is_weekend=1.0)

    score = detector.score_current(
        "automation.day_type.sparse",
        [*weekday_rows, *weekend_rows, current],
    )

    assert math.isfinite(score)
    assert score > 0.0


def test_bocpd_recurring_busy_day_stays_below_medium_threshold() -> None:
    """Recurring busy days inside the historical envelope must not promote."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    # ~80% quiet (~5), ~20% busy (~22) — current matches the busy pattern.
    history = [_feature_row(22.0 if i % 5 == 0 else 5.0) for i in range(32)]

    score = detector.score_current(
        "automation.envelope.recurring",
        [*history, _feature_row(22.0)],
    )

    assert score < 2.0


def test_bocpd_true_spike_above_historical_envelope_still_high() -> None:
    """Counts above the historical envelope must keep a high overactive score."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(22.0 if i % 5 == 0 else 5.0) for i in range(32)]

    score_recurring = detector.score_current(
        "automation.envelope.recurring",
        [*history, _feature_row(22.0)],
    )
    score_spike = detector.score_current(
        "automation.envelope.spike",
        [*history, _feature_row(40.0)],
    )

    assert score_spike > score_recurring
    assert score_spike >= 2.5


def test_bocpd_envelope_dampen_skipped_when_sparse_history() -> None:
    """Sparse training history should skip envelope dampening and stay finite."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    sparse = [_feature_row(5.0) for _ in range(4)]

    score = detector.score_current(
        "automation.envelope.sparse",
        [*sparse, _feature_row(40.0)],
    )

    assert math.isfinite(score)
    assert score > 2.5


def test_bocpd_post_spike_return_to_normal_stays_low() -> None:
    """Day after a lone spike returning to baseline must not promote."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(5.0) for _ in range(25)] + [_feature_row(80.0)]

    score = detector.score_current(
        "automation.hangover.return",
        [*history, _feature_row(5.0)],
    )

    assert score < 2.0


def test_bocpd_post_spike_continued_extreme_still_high() -> None:
    """A lone spike must not set the envelope so a continued extreme is muted."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(5.0) for _ in range(25)] + [_feature_row(80.0)]

    score = detector.score_current(
        "automation.hangover.continued",
        [*history, _feature_row(80.0)],
    )

    assert score >= 2.5


def test_bocpd_cold_start_modest_count_stays_below_medium() -> None:
    """Modest first activity with almost no prior active days must not promote."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(0.0) for _ in range(20)]

    score = detector.score_current(
        "automation.cold_start.modest",
        [*history, _feature_row(5.0)],
    )

    assert score < 2.0


def test_bocpd_cold_start_extreme_spike_still_high() -> None:
    """Extreme first-day spikes must still clear the promote threshold."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(0.0) for _ in range(20)]

    score = detector.score_current(
        "automation.cold_start.extreme",
        [*history, _feature_row(40.0)],
    )

    assert score >= 2.5


def test_bocpd_mature_history_unaffected() -> None:
    """Cold-start gate must not dampen spikes once history is mature."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(10.0 + float(i % 2)) for i in range(28)]

    score = detector.score_current(
        "automation.cold_start.mature",
        [*history, _feature_row(30.0)],
    )

    assert score >= 2.5


def test_bocpd_sparse_active_recurring_night_stays_below_medium() -> None:
    """Zero-inflated history: recurring active-night levels must not promote."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    active_levels = [12.0, 13.0, 14.0, 12.0, 13.0]
    history: list[dict[str, float]] = []
    active_idx = 0
    for i in range(30):
        # ~1/6 days active at 12-14, rest quiet — matches late-night motion patterns.
        if i % 6 == 0:
            history.append(_feature_row(active_levels[active_idx]))
            active_idx += 1
        else:
            history.append(_feature_row(0.0))

    score = detector.score_current(
        "automation.sparse.recurring",
        [*history, _feature_row(14.0)],
    )

    assert score < 2.0


def test_bocpd_sparse_active_true_spike_still_high() -> None:
    """Zero-inflated history: counts above the active-day envelope still promote."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    active_levels = [12.0, 13.0, 14.0, 12.0, 13.0]
    history: list[dict[str, float]] = []
    active_idx = 0
    for i in range(30):
        if i % 6 == 0:
            history.append(_feature_row(active_levels[active_idx]))
            active_idx += 1
        else:
            history.append(_feature_row(0.0))

    score_recurring = detector.score_current(
        "automation.sparse.recurring",
        [*history, _feature_row(14.0)],
    )
    score_spike = detector.score_current(
        "automation.sparse.spike",
        [*history, _feature_row(40.0)],
    )

    assert score_spike > score_recurring
    assert score_spike >= 2.5


def test_bocpd_dense_history_skips_sparse_active_gate() -> None:
    """Everyday activity must not be treated as zero-inflated sparse-active."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history = [_feature_row(10.0 + float(i % 2)) for i in range(28)]

    score = detector.score_current(
        "automation.sparse.dense",
        [*history, _feature_row(30.0)],
    )

    assert score >= 2.5


def test_bocpd_same_weekday_filter_recovers_weekday_specific_spike() -> None:
    """Same-weekday training should surface Monday spikes hidden by busy Fridays."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    history: list[dict[str, float]] = []
    # 5 Mondays quiet (~3), 5 Fridays busy (~25).
    for _ in range(5):
        history.append(_feature_row(3.0, is_weekend=0.0, weekday=0.0))  # Mon
        history.append(_feature_row(4.0, is_weekend=0.0, weekday=1.0))  # Tue
        history.append(_feature_row(4.0, is_weekend=0.0, weekday=2.0))  # Wed
        history.append(_feature_row(5.0, is_weekend=0.0, weekday=3.0))  # Thu
        history.append(_feature_row(25.0, is_weekend=0.0, weekday=4.0))  # Fri

    monday_spike = _feature_row(12.0, is_weekend=0.0, weekday=0.0)
    score_same_weekday = detector.score_current(
        "automation.weekday.same",
        [*history, monday_spike],
    )
    # Collapse weekday labels so Friday highs stay in the Monday training envelope.
    collapsed = [{**row, "weekday": 0.0} for row in history]
    score_mixed = detector.score_current(
        "automation.weekday.mixed",
        [*collapsed, monday_spike],
    )

    assert score_same_weekday > score_mixed
    assert score_same_weekday >= 2.5
    assert score_mixed < 2.0


def test_bocpd_same_weekday_filter_falls_back_when_sparse() -> None:
    """Fewer than 4 same-weekday rows should fall back to day-type history."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    # 15 weekday rows cycling Mon-Fri => only 3 Mondays.
    history = [
        _feature_row(5.0 + float(i % 2), is_weekend=0.0, weekday=float(i % 5))
        for i in range(15)
    ]
    current = _feature_row(30.0, is_weekend=0.0, weekday=0.0)

    score = detector.score_current(
        "automation.weekday.sparse",
        [*history, current],
    )

    assert math.isfinite(score)
    assert score > 0.0


def test_bocpd_context_hour_ratio_amplifies_overactive_score() -> None:
    """High same-hour ratio should raise confidence for overactive anomalies."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
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
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
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
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
    state = detector.initial_state()
    for observed in [5] * 32:
        detector.update_state(state, observed)

    detector.update_state(state, 80)

    assert state["run_length_probs"][0] > detector.hazard_rate


def test_bocpd_extreme_scores_are_monotonic_for_larger_deviations() -> None:
    """Larger overactive deviations should produce larger anomaly scores."""
    detector = BOCPDDetector(hazard_rate=0.05, max_run_length=64)
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
