"""Bayesian Online Changepoint Detection (BOCPD) detector.

Pure statistical anomaly detector with no Home Assistant dependencies.
Extracted from runtime_monitor.py to reduce module size and improve testability.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Protocol, cast

_LOGGER = logging.getLogger(__name__)

# Internal BOCPD tuning constants (not user-configurable).
DEFAULT_RUNTIME_HEALTH_HAZARD_RATE = 0.05
DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH = 90

# Scoring constants
_PMF_FLOOR = 1e-300
_MAX_ANOMALY_SCORE = 80.0
_CDF_CONVERGENCE_THRESHOLD = 0.999999
_UPPER_LIMIT_OFFSET = 64
_UPPER_LIMIT_RATE_MULTIPLIER = 8.0
_UPPER_LIMIT_RATE_OFFSET = 32
_SURPRISE_BLEND_FACTOR = 0.35

# Effective hazard constants
_HAZARD_SURPRISE_FLOOR = 1e-12
_HAZARD_SURPRISE_THRESHOLD = 1.0
_HAZARD_BOOST_CAP = 12.0
_HAZARD_BOOST_DIVISOR = 2.0
_HAZARD_MAX = 0.60

# Context score multiplier bounds
_CONTEXT_MULTIPLIER_MIN = 0.55
_CONTEXT_MULTIPLIER_MAX = 1.75
_GAP_BOOST_CAP = 0.40
_GAP_BOOST_SCALE = 0.18
_HOUR_BOOST_CAP = 0.35
_HOUR_BOOST_SCALE = 0.20
_DAMPENING_CAP = 0.45
_DAMPENING_SCALE = 0.14
_DAMPENING_FLOOR = 0.55

# Probability normalization
_PROB_TRIM_THRESHOLD = 1e-15

# Prior parameter floor
_PRIOR_FLOOR = 1e-6
_HAZARD_FLOOR = 1e-6


class Detector(Protocol):
    """Anomaly detector interface for runtime monitoring."""

    def score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        window_size: int | None = None,
    ) -> float:
        """Train from history rows and return anomaly score for the current row."""
        ...


class BOCPDDetector:
    """BOCPD detector using Gamma-Poisson predictive updates.

    The detector maintains a run-length posterior and a bounded history of
    observations to score the next count with a posterior predictive tail score.
    """

    def __init__(
        self,
        *,
        hazard_rate: float = DEFAULT_RUNTIME_HEALTH_HAZARD_RATE,
        max_run_length: int = DEFAULT_RUNTIME_HEALTH_MAX_RUN_LENGTH,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
        count_feature: str = "rolling_24h_count",
    ) -> None:
        self.hazard_rate = min(1.0, max(_HAZARD_FLOOR, float(hazard_rate)))
        self.max_run_length = max(2, int(max_run_length))
        self._prior_alpha = max(_PRIOR_FLOOR, float(prior_alpha))
        self._prior_beta = max(_PRIOR_FLOOR, float(prior_beta))
        self._count_feature = count_feature

    def initial_state(self) -> dict[str, Any]:
        """Return a default BOCPD bucket state."""
        return {
            "run_length_probs": [1.0],
            "observations": [],
            "current_day": "",
            "current_count": 0,
            "map_run_length": 0,
            "expected_rate": 0.0,
        }

    def score_current(
        self,
        automation_id: str,
        train_rows: list[dict[str, float]],
        window_size: int | None = None,
    ) -> float:
        """Return two-sided tail score from BOCPD posterior predictive mass."""
        if len(train_rows) < 2:
            return 0.0

        training = train_rows[:-1]
        if window_size is not None and window_size > 0 and len(training) > window_size:
            training = training[-window_size:]

        state = self.initial_state()
        for row in training:
            self.update_state(state, self._coerce_count(row))
        current_row = train_rows[-1]
        current_count = self._coerce_count(current_row)
        score = self._score_tail_probability(state, current_count)
        score *= self._context_score_multiplier(
            state=state,
            current_row=current_row,
            current_count=current_count,
        )
        _LOGGER.debug(
            "Scored '%s' with BOCPD: %.3f (current=%d, n=%d)",
            automation_id,
            score,
            current_count,
            len(training),
        )
        return score

    def update_state(self, state: dict[str, Any], observed_count: int) -> None:
        """Apply one BOCPD update step for a finalized bucket count."""
        self._ensure_state(state)
        count = max(0, int(observed_count))
        effective_hazard = self._effective_hazard(state, count)
        observations = cast(list[int], state["observations"])
        previous_probs = cast(list[float], state["run_length_probs"])

        next_probs = [0.0] * (self.max_run_length + 1)
        for run_length, mass in enumerate(previous_probs):
            if mass <= 0.0:
                continue
            alpha, beta = self._posterior_params(observations, run_length)
            p = beta / (beta + 1.0)
            predictive = self._nb_pmf(count, alpha, p)
            weighted = mass * predictive
            changepoint_mass = weighted * effective_hazard
            growth_mass = weighted * (1.0 - effective_hazard)
            next_probs[0] += changepoint_mass
            growth_index = min(run_length + 1, self.max_run_length)
            next_probs[growth_index] += growth_mass

        normalized = self._normalize_probs(next_probs)
        observations.append(count)
        if len(observations) > self.max_run_length:
            del observations[: -self.max_run_length]

        state["run_length_probs"] = normalized
        state["map_run_length"] = self.map_run_length(state)
        state["expected_rate"] = self.expected_rate(state)

    def normalize_state(self, state: dict[str, Any]) -> None:
        """Normalize a BOCPD state payload in-place."""
        self._ensure_state(state)

    def predictive_pmf_for_count(self, state: dict[str, Any], count: int) -> float:
        """Return BOCPD posterior predictive PMF for an integer count."""
        self._ensure_state(state)
        candidate = max(0, int(count))
        observations = cast(list[int], state["observations"])
        probs = cast(list[float], state["run_length_probs"])

        total = 0.0
        for run_length, mass in enumerate(probs):
            if mass <= 0.0:
                continue
            alpha, beta = self._posterior_params(observations, run_length)
            p = beta / (beta + 1.0)
            total += mass * self._nb_pmf(candidate, alpha, p)
        return max(0.0, float(total))

    def map_run_length(self, state: dict[str, Any]) -> int:
        """Return MAP run length from a BOCPD state."""
        self._ensure_state(state)
        probs = cast(list[float], state["run_length_probs"])
        return self._map_run_length_from_probs(probs)

    def expected_rate(self, state: dict[str, Any]) -> float:
        """Return posterior expected count rate from run-length mixture."""
        self._ensure_state(state)
        observations = cast(list[int], state["observations"])
        if not observations:
            return 0.0
        probs = cast(list[float], state["run_length_probs"])
        return self._expected_rate_from(observations, probs)

    def _coerce_count(self, row: dict[str, float]) -> int:
        value = row.get(self._count_feature, 0.0)
        try:
            return max(0, round(float(value)))
        except (TypeError, ValueError):
            return 0

    def _score_tail_probability(
        self, state: dict[str, Any], current_count: int
    ) -> float:
        pmf_floor = _PMF_FLOOR
        max_score = _MAX_ANOMALY_SCORE
        pmf_current = self.predictive_pmf_for_count(state, current_count)
        surprise_score = min(max_score, -math.log10(max(pmf_current, pmf_floor)))
        if pmf_current <= 0.0:
            return surprise_score

        upper_limit = max(
            current_count + _UPPER_LIMIT_OFFSET,
            round(self.expected_rate(state) * _UPPER_LIMIT_RATE_MULTIPLIER)
            + _UPPER_LIMIT_RATE_OFFSET,
            _UPPER_LIMIT_OFFSET,
        )
        cumulative = 0.0
        cdf = 0.0
        for count in range(upper_limit + 1):
            mass = self.predictive_pmf_for_count(state, count)
            cumulative += mass
            if count <= current_count:
                cdf += mass
            if cumulative >= _CDF_CONVERGENCE_THRESHOLD and count >= current_count:
                break

        cdf = min(1.0, max(0.0, cdf))
        upper_tail = min(1.0, max(0.0, 1.0 - (cdf - pmf_current)))
        two_sided_p = min(1.0, 2.0 * min(cdf, upper_tail))
        tail_score = min(max_score, -math.log10(max(two_sided_p, pmf_floor)))
        if surprise_score > tail_score:
            tail_score += _SURPRISE_BLEND_FACTOR * (surprise_score - tail_score)
        return max(0.0, min(max_score, float(tail_score)))

    def _effective_hazard(self, state: dict[str, Any], observed_count: int) -> float:
        """Increase changepoint prior on highly surprising observations."""
        predictive = self.predictive_pmf_for_count(state, observed_count)
        surprise = -math.log10(max(predictive, _HAZARD_SURPRISE_FLOOR))
        if surprise <= _HAZARD_SURPRISE_THRESHOLD:
            return self.hazard_rate
        boost = min(
            _HAZARD_BOOST_CAP,
            (surprise - _HAZARD_SURPRISE_THRESHOLD) / _HAZARD_BOOST_DIVISOR,
        )
        return min(_HAZARD_MAX, max(self.hazard_rate, self.hazard_rate * (1.0 + boost)))

    def _context_score_multiplier(
        self,
        *,
        state: dict[str, Any],
        current_row: dict[str, float],
        current_count: int,
    ) -> float:
        """Apply bounded runtime-context adjustments to BOCPD anomaly score."""
        expected = max(0.0, self.expected_rate(state))
        if expected <= 0.0:
            return 1.0

        deviation = float(current_count) - expected
        gap_vs_median = max(
            0.0, self._coerce_numeric(current_row.get("gap_vs_median"), 1.0)
        )
        hour_ratio = max(
            0.0, self._coerce_numeric(current_row.get("hour_ratio_30d"), 1.0)
        )
        other_automations = max(
            0.0,
            self._coerce_numeric(current_row.get("other_automations_5m"), 0.0),
        )

        multiplier = 1.0
        if deviation < 0.0:
            gap_boost = min(
                _GAP_BOOST_CAP,
                _GAP_BOOST_SCALE * math.log1p(max(0.0, gap_vs_median - 1.0)),
            )
            multiplier *= 1.0 + gap_boost
        elif deviation > 0.0:
            hour_boost = min(
                _HOUR_BOOST_CAP,
                _HOUR_BOOST_SCALE * math.log1p(max(0.0, hour_ratio - 1.0)),
            )
            multiplier *= 1.0 + hour_boost
            dampening = min(
                _DAMPENING_CAP, _DAMPENING_SCALE * math.log1p(other_automations)
            )
            multiplier *= max(_DAMPENING_FLOOR, 1.0 - dampening)

        return max(_CONTEXT_MULTIPLIER_MIN, min(_CONTEXT_MULTIPLIER_MAX, multiplier))

    def _posterior_params(
        self,
        observations: list[int],
        run_length: int,
    ) -> tuple[float, float]:
        if run_length <= 0 or not observations:
            return self._prior_alpha, self._prior_beta
        sample_size = min(run_length, len(observations))
        segment = observations[-sample_size:]
        return (
            self._prior_alpha + float(sum(segment)),
            self._prior_beta + float(sample_size),
        )

    def _ensure_state(self, state: dict[str, Any]) -> None:
        run_length_probs_raw = state.get("run_length_probs")
        if isinstance(run_length_probs_raw, list):
            run_length_probs = [
                max(0.0, float(value))
                for value in cast(list[Any], run_length_probs_raw)[
                    : self.max_run_length + 1
                ]
            ]
        else:
            run_length_probs = [1.0]
        if not run_length_probs:
            run_length_probs = [1.0]
        state["run_length_probs"] = self._normalize_probs(run_length_probs)

        observations_raw = state.get("observations")
        if isinstance(observations_raw, list):
            observations = [
                max(0, round(float(value)))
                for value in cast(list[Any], observations_raw)[-self.max_run_length :]
            ]
        else:
            observations = []
        state["observations"] = observations
        state.setdefault("current_day", "")
        state["current_count"] = max(
            0, int(self._coerce_numeric(state.get("current_count"), 0.0))
        )
        run_length_probs_state = state["run_length_probs"]
        state["map_run_length"] = self._map_run_length_from_probs(
            run_length_probs_state
        )
        state["expected_rate"] = self._expected_rate_from(
            observations,
            run_length_probs_state,
        )

    def _normalize_probs(self, values: list[float]) -> list[float]:
        total = float(sum(values))
        if not math.isfinite(total) or total <= 0.0:
            return [1.0]
        normalized = [max(0.0, value) / total for value in values]
        while len(normalized) > 1 and normalized[-1] <= _PROB_TRIM_THRESHOLD:
            normalized.pop()
        return normalized

    @staticmethod
    def _coerce_numeric(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _map_run_length_from_probs(probs: list[float]) -> int:
        if not probs:
            return 0
        return int(max(range(len(probs)), key=probs.__getitem__))

    def _expected_rate_from(
        self,
        observations: list[int],
        probs: list[float],
    ) -> float:
        if not observations or not probs:
            return 0.0
        expected = 0.0
        for run_length, mass in enumerate(probs):
            if mass <= 0.0:
                continue
            alpha, beta = self._posterior_params(observations, run_length)
            expected += mass * (alpha / beta)
        return max(0.0, float(expected))

    @staticmethod
    def _nb_pmf(count: int, r: float, p: float) -> float:
        if count < 0:
            return 0.0
        if p <= 0.0 or p >= 1.0:
            return 0.0
        log_prob = (
            math.lgamma(count + r)
            - math.lgamma(count + 1)
            - math.lgamma(r)
            + (r * math.log(p))
            + (count * math.log(1.0 - p))
        )
        return math.exp(log_prob)
