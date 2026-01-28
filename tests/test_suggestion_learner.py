"""Tests for SuggestionLearner."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.autodoctor.suggestion_learner import SuggestionLearner


def test_record_rejection():
    """Test recording a suggestion rejection."""
    learner = SuggestionLearner()

    learner.record_rejection("sensor.temp", "sensor.humidity")

    assert learner.get_rejection_count("sensor.temp", "sensor.humidity") == 1

    learner.record_rejection("sensor.temp", "sensor.humidity")

    assert learner.get_rejection_count("sensor.temp", "sensor.humidity") == 2


def test_penalty_after_rejections():
    """Test penalty calculation after rejections."""
    learner = SuggestionLearner()

    # No rejections = no penalty
    assert learner.get_score_multiplier("a", "b") == 1.0

    # 1 rejection = mild penalty
    learner.record_rejection("a", "b")
    assert learner.get_score_multiplier("a", "b") == 0.7

    # 2+ rejections = heavy penalty
    learner.record_rejection("a", "b")
    assert learner.get_score_multiplier("a", "b") == 0.3


def test_persistence_format():
    """Test data serialization format."""
    learner = SuggestionLearner()
    learner.record_rejection("sensor.a", "sensor.b")
    learner.record_rejection("sensor.a", "sensor.b")
    learner.record_rejection("light.x", "light.y")

    data = learner.to_dict()

    assert "negative_pairs" in data
    assert len(data["negative_pairs"]) == 2

    # Verify can be restored
    learner2 = SuggestionLearner()
    learner2.from_dict(data)

    assert learner2.get_rejection_count("sensor.a", "sensor.b") == 2
    assert learner2.get_rejection_count("light.x", "light.y") == 1
