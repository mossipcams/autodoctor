"""Tests for StateKnowledgeBase."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.automation_mutation_tester.knowledge_base import (
    StateKnowledgeBase,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    return hass


@pytest.mark.asyncio
async def test_knowledge_base_initialization(mock_hass):
    """Test knowledge base can be created."""
    kb = StateKnowledgeBase(mock_hass)
    assert kb is not None
    assert kb.hass == mock_hass


@pytest.mark.asyncio
async def test_get_valid_states_for_known_domain(mock_hass):
    """Test getting valid states for known domain entity."""
    kb = StateKnowledgeBase(mock_hass)

    # Mock an entity
    mock_state = MagicMock()
    mock_state.entity_id = "binary_sensor.motion"
    mock_state.domain = "binary_sensor"
    mock_state.state = "on"
    mock_hass.states.get = MagicMock(return_value=mock_state)

    states = kb.get_valid_states("binary_sensor.motion")
    assert "on" in states
    assert "off" in states


@pytest.mark.asyncio
async def test_get_valid_states_unknown_entity(mock_hass):
    """Test getting valid states for unknown entity."""
    kb = StateKnowledgeBase(mock_hass)
    mock_hass.states.get = MagicMock(return_value=None)

    states = kb.get_valid_states("sensor.nonexistent")
    assert states is None


@pytest.mark.asyncio
async def test_is_valid_state(mock_hass):
    """Test checking if a state is valid."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "binary_sensor.motion"
    mock_state.domain = "binary_sensor"
    mock_hass.states.get = MagicMock(return_value=mock_state)

    assert kb.is_valid_state("binary_sensor.motion", "on") is True
    assert kb.is_valid_state("binary_sensor.motion", "off") is True
    assert kb.is_valid_state("binary_sensor.motion", "maybe") is False


@pytest.mark.asyncio
async def test_entity_exists(mock_hass):
    """Test checking if entity exists."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_hass.states.get = MagicMock(return_value=mock_state)

    assert kb.entity_exists("binary_sensor.motion") is True

    mock_hass.states.get = MagicMock(return_value=None)
    assert kb.entity_exists("binary_sensor.missing") is False
