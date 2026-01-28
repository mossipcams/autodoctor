"""Tests for StateKnowledgeBase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF

from custom_components.autodoctor.knowledge_base import (
    StateKnowledgeBase,
)


async def test_knowledge_base_initialization(hass: HomeAssistant):
    """Test knowledge base can be created."""
    kb = StateKnowledgeBase(hass)
    assert kb is not None
    assert kb.hass == hass


async def test_get_valid_states_for_known_domain(hass: HomeAssistant):
    """Test getting valid states for known domain entity."""
    kb = StateKnowledgeBase(hass)

    # Set up an actual entity state
    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    states = kb.get_valid_states("binary_sensor.motion")
    assert "on" in states
    assert "off" in states


async def test_get_valid_states_unknown_entity(hass: HomeAssistant):
    """Test getting valid states for unknown entity."""
    kb = StateKnowledgeBase(hass)

    states = kb.get_valid_states("sensor.nonexistent")
    assert states is None


async def test_is_valid_state(hass: HomeAssistant):
    """Test checking if a state is valid."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    assert kb.is_valid_state("binary_sensor.motion", "on") is True
    assert kb.is_valid_state("binary_sensor.motion", "off") is True
    assert kb.is_valid_state("binary_sensor.motion", "maybe") is False


async def test_entity_exists(hass: HomeAssistant):
    """Test checking if entity exists."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    assert kb.entity_exists("binary_sensor.motion") is True
    assert kb.entity_exists("binary_sensor.missing") is False


async def test_get_domain(hass: HomeAssistant):
    """Test domain extraction from entity ID."""
    kb = StateKnowledgeBase(hass)
    assert kb.get_domain("binary_sensor.motion") == "binary_sensor"
    assert kb.get_domain("light.living_room") == "light"
    assert kb.get_domain("invalid") == ""


async def test_clear_cache(hass: HomeAssistant):
    """Test cache clearing."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    # Populate cache
    kb.get_valid_states("binary_sensor.motion")
    assert "binary_sensor.motion" in kb._cache

    # Clear cache
    kb.clear_cache()
    assert len(kb._cache) == 0


async def test_schema_introspection_climate_hvac_modes(hass: HomeAssistant):
    """Test extracting hvac_modes from climate entity."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "climate.living_room",
        "heat",
        {"hvac_modes": ["off", "heat", "cool", "auto"]},
    )
    await hass.async_block_till_done()

    states = kb.get_valid_states("climate.living_room")
    assert "off" in states
    assert "heat" in states
    assert "cool" in states
    assert "auto" in states


async def test_schema_introspection_select_options(hass: HomeAssistant):
    """Test extracting options from select entity."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "select.speed",
        "low",
        {"options": ["low", "medium", "high"]},
    )
    await hass.async_block_till_done()

    states = kb.get_valid_states("select.speed")
    assert "low" in states
    assert "medium" in states
    assert "high" in states


async def test_schema_introspection_light_effect_list(hass: HomeAssistant):
    """Test extracting effect_list from light entity."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "light.strip",
        STATE_ON,
        {"effect_list": ["rainbow", "strobe", "solid"]},
    )
    await hass.async_block_till_done()

    # Light states are still on/off
    states = kb.get_valid_states("light.strip")
    assert "on" in states
    assert "off" in states

    # But we should be able to get valid attributes
    attrs = kb.get_valid_attributes("light.strip", "effect")
    assert "rainbow" in attrs
    assert "strobe" in attrs


@pytest.mark.asyncio
async def test_load_history_adds_observed_states(hass: HomeAssistant):
    """Test that recorder history adds observed states."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("sensor.custom", "active")
    await hass.async_block_till_done()

    history_states = [
        MagicMock(state="active", last_changed=None),
        MagicMock(state="idle", last_changed=None),
        MagicMock(state="active", last_changed=None),
        MagicMock(state="error", last_changed=None),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        return_value={"sensor.custom": history_states},
    ):
        await kb.async_load_history(["sensor.custom"])

    states = kb.get_valid_states("sensor.custom")
    assert "active" in states
    assert "idle" in states
    assert "error" in states


@pytest.mark.asyncio
async def test_history_excludes_unavailable_unknown(hass: HomeAssistant):
    """Test that history loading excludes unavailable/unknown from observed."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("sensor.custom", "active")
    await hass.async_block_till_done()

    history_states = [
        MagicMock(state="active", last_changed=None),
        MagicMock(state="unavailable", last_changed=None),
        MagicMock(state="unknown", last_changed=None),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        return_value={"sensor.custom": history_states},
    ):
        await kb.async_load_history(["sensor.custom"])

    observed = kb.get_observed_states("sensor.custom")
    assert "active" in observed
    assert "unavailable" not in observed
    assert "unknown" not in observed


@pytest.mark.asyncio
async def test_get_historical_entity_ids(hass: HomeAssistant):
    """Test getting historical entity IDs from recorder."""
    kb = StateKnowledgeBase(hass)

    # Simulate loading history with entities
    history_states = [
        MagicMock(state="on", last_changed=None),
        MagicMock(state="off", last_changed=None),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        return_value={
            "sensor.old_entity": history_states,
            "sensor.another_old": history_states,
        },
    ):
        await kb.async_load_history(["sensor.old_entity", "sensor.another_old"])

    historical = kb.get_historical_entity_ids()
    assert "sensor.old_entity" in historical
    assert "sensor.another_old" in historical
    assert "sensor.nonexistent" not in historical


async def test_get_integration_from_entity_registry(hass: HomeAssistant):
    """Test getting integration name from entity registry."""
    from unittest.mock import MagicMock, patch
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    # Mock entity registry
    mock_entry = MagicMock()
    mock_entry.platform = "roborock"

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry
    ):
        integration = kb.get_integration("vacuum.roborock_s7")

    assert integration == "roborock"


async def test_get_integration_returns_none_for_unknown(hass: HomeAssistant):
    """Test getting integration returns None for unknown entity."""
    from unittest.mock import MagicMock, patch
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = None

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry
    ):
        integration = kb.get_integration("vacuum.unknown")

    assert integration is None
