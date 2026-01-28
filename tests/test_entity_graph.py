"""Tests for EntityGraph."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from custom_components.autodoctor.entity_graph import EntityGraph


def test_entity_graph_same_area():
    """Test same_area check."""
    graph = EntityGraph()

    # Manually populate for testing
    graph._entity_areas = {
        "light.kitchen": "kitchen",
        "switch.kitchen_fan": "kitchen",
        "light.bedroom": "bedroom",
    }

    assert graph.same_area("light.kitchen", "switch.kitchen_fan") is True
    assert graph.same_area("light.kitchen", "light.bedroom") is False


def test_entity_graph_same_device():
    """Test same_device check."""
    graph = EntityGraph()

    graph._entity_devices = {
        "sensor.temp": "device_1",
        "sensor.humidity": "device_1",
        "sensor.motion": "device_2",
    }

    assert graph.same_device("sensor.temp", "sensor.humidity") is True
    assert graph.same_device("sensor.temp", "sensor.motion") is False


def test_entity_graph_same_domain():
    """Test same_domain check."""
    graph = EntityGraph()

    assert graph.same_domain("light.kitchen", "light.bedroom") is True
    assert graph.same_domain("light.kitchen", "switch.kitchen") is False


def test_entity_graph_relationship_score():
    """Test relationship scoring."""
    graph = EntityGraph()

    # Set up test data
    graph._entity_areas = {
        "light.kitchen": "kitchen",
        "switch.kitchen_fan": "kitchen",
    }
    graph._entity_devices = {
        "light.kitchen": "device_1",
        "switch.kitchen_fan": "device_1",
    }
    graph._entity_labels = {
        "light.kitchen": {"ceiling"},
        "switch.kitchen_fan": {"ceiling"},
    }

    # Same device + same area + shared labels = high score
    # 0.4 (device) + 0.3 (area) + 0.1 (labels) = 0.8
    score = graph.relationship_score("light.kitchen", "switch.kitchen_fan")
    assert score == pytest.approx(0.8, rel=1e-9)  # Should be high

    # Different entities with no relationship
    graph._entity_areas["light.bedroom"] = "bedroom"
    graph._entity_devices["light.bedroom"] = "device_2"
    graph._entity_labels["light.bedroom"] = set()

    score = graph.relationship_score("light.kitchen", "light.bedroom")
    assert score < 0.4  # Should be low (only domain match)
