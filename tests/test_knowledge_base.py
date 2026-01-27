"""Tests for StateKnowledgeBase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.autodoctor.knowledge_base import (
    StateKnowledgeBase,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    return hass


def test_knowledge_base_initialization(mock_hass):
    """Test knowledge base can be created."""
    kb = StateKnowledgeBase(mock_hass)
    assert kb is not None
    assert kb.hass == mock_hass


def test_get_valid_states_for_known_domain(mock_hass):
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


def test_get_valid_states_unknown_entity(mock_hass):
    """Test getting valid states for unknown entity."""
    kb = StateKnowledgeBase(mock_hass)
    mock_hass.states.get = MagicMock(return_value=None)

    states = kb.get_valid_states("sensor.nonexistent")
    assert states is None


def test_is_valid_state(mock_hass):
    """Test checking if a state is valid."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "binary_sensor.motion"
    mock_state.domain = "binary_sensor"
    mock_hass.states.get = MagicMock(return_value=mock_state)

    assert kb.is_valid_state("binary_sensor.motion", "on") is True
    assert kb.is_valid_state("binary_sensor.motion", "off") is True
    assert kb.is_valid_state("binary_sensor.motion", "maybe") is False


def test_entity_exists(mock_hass):
    """Test checking if entity exists."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_hass.states.get = MagicMock(return_value=mock_state)

    assert kb.entity_exists("binary_sensor.motion") is True

    mock_hass.states.get = MagicMock(return_value=None)
    assert kb.entity_exists("binary_sensor.missing") is False


def test_get_domain(mock_hass):
    """Test domain extraction from entity ID."""
    kb = StateKnowledgeBase(mock_hass)
    assert kb.get_domain("binary_sensor.motion") == "binary_sensor"
    assert kb.get_domain("light.living_room") == "light"
    assert kb.get_domain("invalid") == ""


def test_clear_cache(mock_hass):
    """Test cache clearing."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_hass.states.get = MagicMock(return_value=mock_state)

    # Populate cache
    kb.get_valid_states("binary_sensor.motion")
    assert "binary_sensor.motion" in kb._cache

    # Clear cache
    kb.clear_cache()
    assert len(kb._cache) == 0


def test_schema_introspection_climate_hvac_modes(mock_hass):
    """Test extracting hvac_modes from climate entity."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "climate.living_room"
    mock_state.domain = "climate"
    mock_state.attributes = {"hvac_modes": ["off", "heat", "cool", "auto"]}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    states = kb.get_valid_states("climate.living_room")
    assert "off" in states
    assert "heat" in states
    assert "cool" in states
    assert "auto" in states


def test_schema_introspection_select_options(mock_hass):
    """Test extracting options from select entity."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "select.speed"
    mock_state.domain = "select"
    mock_state.attributes = {"options": ["low", "medium", "high"]}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    states = kb.get_valid_states("select.speed")
    assert "low" in states
    assert "medium" in states
    assert "high" in states


def test_schema_introspection_light_effect_list(mock_hass):
    """Test extracting effect_list from light entity."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "light.strip"
    mock_state.domain = "light"
    mock_state.attributes = {"effect_list": ["rainbow", "strobe", "solid"]}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    # Light states are still on/off
    states = kb.get_valid_states("light.strip")
    assert "on" in states
    assert "off" in states

    # But we should be able to get valid attributes
    attrs = kb.get_valid_attributes("light.strip", "effect")
    assert "rainbow" in attrs
    assert "strobe" in attrs


@pytest.mark.asyncio
async def test_load_history_adds_observed_states(mock_hass):
    """Test that recorder history adds observed states."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "sensor.custom"
    mock_state.domain = "sensor"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    history_states = [
        MagicMock(state="active"),
        MagicMock(state="idle"),
        MagicMock(state="active"),
        MagicMock(state="error"),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        new_callable=AsyncMock,
        return_value={"sensor.custom": history_states},
    ):
        await kb.async_load_history(["sensor.custom"])

    states = kb.get_valid_states("sensor.custom")
    assert "active" in states
    assert "idle" in states
    assert "error" in states


@pytest.mark.asyncio
async def test_history_excludes_unavailable_unknown(mock_hass):
    """Test that history loading excludes unavailable/unknown from observed."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "sensor.custom"
    mock_state.domain = "sensor"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    history_states = [
        MagicMock(state="active"),
        MagicMock(state="unavailable"),
        MagicMock(state="unknown"),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        new_callable=AsyncMock,
        return_value={"sensor.custom": history_states},
    ):
        await kb.async_load_history(["sensor.custom"])

    observed = kb.get_observed_states("sensor.custom")
    assert "active" in observed
    assert "unavailable" not in observed
    assert "unknown" not in observed
