"""Tests for StateKnowledgeBase."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.knowledge_base import (
    CAPABILITY_ATTRIBUTE_SOURCES,
    CAPABILITY_STATE_SOURCES,
    StateKnowledgeBase,
)


async def test_capability_constants_defined(hass: HomeAssistant):
    """Test capability source constants are defined."""
    # State sources (contain valid states)
    assert "options" in CAPABILITY_STATE_SOURCES
    assert "hvac_modes" in CAPABILITY_STATE_SOURCES
    assert CAPABILITY_STATE_SOURCES["options"] is True
    assert CAPABILITY_STATE_SOURCES["hvac_modes"] is True

    # Attribute sources (contain valid attribute values)
    assert "fan_modes" in CAPABILITY_ATTRIBUTE_SOURCES
    assert "preset_modes" in CAPABILITY_ATTRIBUTE_SOURCES
    assert "swing_modes" in CAPABILITY_ATTRIBUTE_SOURCES
    assert "swing_horizontal_modes" in CAPABILITY_ATTRIBUTE_SOURCES


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
    """Test cache clearing clears all caches."""
    kb = StateKnowledgeBase(hass)

    # Set up zone and area
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    from homeassistant.helpers import area_registry as ar
    area_registry = ar.async_get(hass)
    area_registry.async_create("Living Room")
    await hass.async_block_till_done()

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    # Populate caches
    kb.get_valid_states("binary_sensor.motion")
    kb._get_zone_names()
    kb._get_area_names()

    assert "binary_sensor.motion" in kb._cache
    assert kb._zone_names is not None
    assert kb._area_names is not None

    # Clear cache
    kb.clear_cache()

    assert len(kb._cache) == 0
    assert kb._zone_names is None
    assert kb._area_names is None


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

    # Use input_select which supports arbitrary states from history
    hass.states.async_set("input_select.mode", "active", {"options": ["active"]})
    await hass.async_block_till_done()

    history_states = [
        MagicMock(state="active", last_changed=None),
        MagicMock(state="idle", last_changed=None),
        MagicMock(state="active", last_changed=None),
        MagicMock(state="error", last_changed=None),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        return_value={"input_select.mode": history_states},
    ):
        await kb.async_load_history(["input_select.mode"])

    states = kb.get_valid_states("input_select.mode")
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
        return_value=mock_registry,
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
        return_value=mock_registry,
    ):
        integration = kb.get_integration("vacuum.unknown")

    assert integration is None


async def test_get_valid_states_includes_learned_states(hass: HomeAssistant):
    """Test that learned states are included in valid states."""
    from unittest.mock import MagicMock, patch

    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    # Set up entity
    hass.states.async_set("vacuum.roborock_s7", "cleaning")
    await hass.async_block_till_done()

    # Create store with learned state
    store = LearnedStatesStore(hass)
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    # Create knowledge base with store
    kb = StateKnowledgeBase(hass, learned_states_store=store)

    # Mock entity registry
    mock_entry = MagicMock()
    mock_entry.platform = "roborock"
    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("vacuum.roborock_s7")

    # Should include learned state
    assert "segment_cleaning" in states
    # Should still include device class defaults
    assert "cleaning" in states
    assert "docked" in states


async def test_zone_names_are_cached(hass: HomeAssistant):
    """Test that zone names are only fetched once and contain zone names."""
    # Set up a zone
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)

    # Call _get_zone_names twice
    zones1 = kb._get_zone_names()
    zones2 = kb._get_zone_names()

    # Should be same object (cached)
    assert zones1 is zones2
    # Should contain the zone name
    assert "Home" in zones1


async def test_area_names_are_cached(hass: HomeAssistant):
    """Test that area names are only fetched once and contain area names."""
    from homeassistant.helpers import area_registry as ar

    # Set up an area
    area_registry = ar.async_get(hass)
    area_registry.async_create("Living Room")
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)

    # Call _get_area_names twice
    areas1 = kb._get_area_names()
    areas2 = kb._get_area_names()

    # Should be same object (cached)
    assert areas1 is areas2
    # Should contain the area name
    assert "Living Room" in areas1


@pytest.mark.asyncio
async def test_load_history_uses_executor(hass: HomeAssistant):
    """Test that history loading uses executor for blocking call."""
    from unittest.mock import AsyncMock, patch

    kb = StateKnowledgeBase(hass)

    # Mock async_add_executor_job
    hass.async_add_executor_job = AsyncMock(return_value={})

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states"
    ) as mock_get:
        await kb.async_load_history(["light.test"])

    # Should have called async_add_executor_job
    assert hass.async_add_executor_job.called


async def test_has_history_loaded(hass: HomeAssistant):
    """Test has_history_loaded public method."""
    kb = StateKnowledgeBase(hass)

    # Initially empty
    assert kb.has_history_loaded() is False

    # After adding observed states
    kb._observed_states["light.test"] = {"on", "off"}
    assert kb.has_history_loaded() is True


async def test_get_capabilities_states_select_entity(hass: HomeAssistant):
    """Test extracting states from select entity capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create entity registry entry with capabilities
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test",
        unique_id="test_select_1",
        suggested_object_id="mode",
        capabilities={"options": ["auto", "cool", "heat", "off"]},
    )

    # Also need the state to exist
    hass.states.async_set("select.mode", "auto")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("select.mode")
    assert states == {"auto", "cool", "heat", "off"}
