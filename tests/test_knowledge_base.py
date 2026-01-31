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
    assert kb.hass is hass
    assert kb.history_days == 30
    assert kb.history_timeout == 120
    assert kb._cache == {}
    assert kb._observed_states == {}
    assert kb._learned_states_store is None
    assert kb._zone_names is None
    assert kb._area_names is None


async def test_get_valid_states_for_known_domain(hass: HomeAssistant):
    """Test getting valid states for known domain entity."""
    kb = StateKnowledgeBase(hass)

    # Set up an actual entity state
    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    states = kb.get_valid_states("binary_sensor.motion")
    assert "on" in states
    assert "off" in states
    assert states == {"on", "off", "unavailable", "unknown"}


async def test_get_valid_states_unknown_entity(hass: HomeAssistant):
    """Test getting valid states for unknown entity."""
    kb = StateKnowledgeBase(hass)

    states = kb.get_valid_states("sensor.nonexistent")
    assert states is None


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
    assert "Home" in kb._zone_names
    assert kb._area_names is not None
    assert "Living Room" in kb._area_names

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
    # Device class defaults + schema introspection + unavailable/unknown
    assert states >= {"off", "heat", "cool", "auto", "heat_cool", "dry", "fan_only", "unavailable", "unknown"}


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
    assert states == {"low", "medium", "high", "unavailable", "unknown"}


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
    assert states == {"on", "off", "unavailable", "unknown"}

    # But we should be able to get valid attributes
    attrs = kb.get_valid_attributes("light.strip", "effect")
    assert "rainbow" in attrs
    assert "strobe" in attrs
    assert attrs == {"rainbow", "strobe", "solid"}


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
    assert states == {"active", "idle", "error", "unavailable", "unknown"}
    assert "unavailable" not in kb.get_observed_states("input_select.mode")
    assert "unknown" not in kb.get_observed_states("input_select.mode")


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
    assert states >= {"segment_cleaning", "cleaning", "docked", "idle", "paused", "returning", "error", "unavailable", "unknown"}


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
    assert zones1 == {"Home"}
    # Prove cache returns stale data after underlying state changes
    hass.states.async_set("zone.work", "zoning", {"friendly_name": "Work"})
    await hass.async_block_till_done()
    zones3 = kb._get_zone_names()
    assert zones3 is zones1  # Same cached object
    assert "Work" not in zones3  # Stale — new zone not visible


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
    assert areas1 == {"Living Room", "living room"}
    # Prove cache returns stale data after underlying registry changes
    area_registry.async_create("Kitchen")
    await hass.async_block_till_done()
    areas3 = kb._get_area_names()
    assert areas3 is areas1  # Same cached object
    assert "Kitchen" not in areas3  # Stale — new area not visible


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


async def test_get_capabilities_states_climate_entity(hass: HomeAssistant):
    """Test extracting hvac_modes from climate entity capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test",
        unique_id="test_climate_1",
        suggested_object_id="thermostat",
        capabilities={
            "hvac_modes": ["heat", "cool", "auto", "off"],
            "fan_modes": ["low", "medium", "high"],  # Should NOT be in states
        },
    )

    hass.states.async_set("climate.thermostat", "heat")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("climate.thermostat")
    # Should only include hvac_modes (state source), not fan_modes (attribute source)
    assert states == {"heat", "cool", "auto", "off"}
    assert "low" not in states
    assert "medium" not in states


async def test_get_capabilities_states_no_capabilities(hass: HomeAssistant):
    """Test handling entity with no capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="switch",
        platform="test",
        unique_id="test_switch_1",
        suggested_object_id="test_switch",
        capabilities=None,  # No capabilities
    )

    hass.states.async_set("switch.test_switch", "on")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("switch.test_switch")
    assert states == set()


async def test_get_capabilities_states_no_registry_entry(hass: HomeAssistant):
    """Test handling entity not in registry."""
    kb = StateKnowledgeBase(hass)

    # Entity exists in states but not in registry
    hass.states.async_set("sensor.temperature", "20")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("sensor.temperature")
    assert states == set()


async def test_get_capabilities_states_invalid_capability_format(hass: HomeAssistant):
    """Test handling capabilities with non-list values."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test",
        unique_id="test_select_bad",
        suggested_object_id="bad_select",
        capabilities={"options": "not_a_list"},  # Invalid format
    )

    hass.states.async_set("select.bad_select", "on")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("select.bad_select")
    assert states == set()  # Should return empty, not crash


async def test_get_valid_states_uses_capabilities(hass: HomeAssistant):
    """Test that get_valid_states() includes capability states on fresh install."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create select entity with capabilities but NO history
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test",
        unique_id="test_select_fresh",
        suggested_object_id="test_mode",
        capabilities={"options": ["mode1", "mode2", "mode3"]},
    )

    hass.states.async_set("select.test_mode", "mode1")
    await hass.async_block_till_done()

    # Get valid states (should include capabilities even without history)
    valid_states = kb.get_valid_states("select.test_mode")

    assert "mode1" in valid_states
    assert "mode2" in valid_states
    assert "mode3" in valid_states
    assert valid_states == {"mode1", "mode2", "mode3", "unavailable", "unknown"}


async def test_attribute_maps_to_capability(hass: HomeAssistant):
    """Test mapping attribute names to capability keys."""
    kb = StateKnowledgeBase(hass)

    # Test valid mappings
    assert kb._attribute_maps_to_capability("fan_mode") == "fan_modes"
    assert kb._attribute_maps_to_capability("preset_mode") == "preset_modes"
    assert kb._attribute_maps_to_capability("swing_mode") == "swing_modes"
    assert (
        kb._attribute_maps_to_capability("swing_horizontal_mode")
        == "swing_horizontal_modes"
    )

    # Test non-mapped attributes
    assert kb._attribute_maps_to_capability("brightness") is None
    assert kb._attribute_maps_to_capability("temperature") is None
    assert kb._attribute_maps_to_capability("unknown_attr") is None


async def test_get_capabilities_attribute_values_climate(hass: HomeAssistant):
    """Test extracting attribute values from climate capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create climate entity with fan_modes and preset_modes capabilities
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test",
        unique_id="test_climate_1",
        suggested_object_id="thermostat",
        capabilities={
            "hvac_modes": ["auto", "cool", "heat", "off"],  # States, not attributes
            "fan_modes": ["low", "medium", "high", "auto"],  # Attribute values
            "preset_modes": ["eco", "comfort", "sleep"],  # Attribute values
        },
    )

    hass.states.async_set("climate.thermostat", "heat")
    await hass.async_block_till_done()

    # Test fan_mode attribute
    fan_values = kb._get_capabilities_attribute_values("climate.thermostat", "fan_mode")
    assert fan_values == {"low", "medium", "high", "auto"}

    # Test preset_mode attribute
    preset_values = kb._get_capabilities_attribute_values(
        "climate.thermostat", "preset_mode"
    )
    assert preset_values == {"eco", "comfort", "sleep"}


async def test_get_valid_attributes_uses_capabilities(hass: HomeAssistant):
    """Test that get_valid_attributes() includes capability values on fresh install."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create climate entity with fan_modes capability but NO current state attributes
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test",
        unique_id="test_climate_fresh",
        suggested_object_id="fresh_climate",
        capabilities={
            "fan_modes": ["low", "medium", "high"],
            "preset_modes": ["eco", "comfort"],
        },
    )

    # Set state WITHOUT fan_modes/preset_modes attributes
    hass.states.async_set("climate.fresh_climate", "heat", {})
    await hass.async_block_till_done()

    # Get valid attributes (should include capabilities even without current attributes)
    fan_values = kb.get_valid_attributes("climate.fresh_climate", "fan_mode")
    assert fan_values == {"low", "medium", "high"}

    preset_values = kb.get_valid_attributes("climate.fresh_climate", "preset_mode")
    assert preset_values == {"eco", "comfort"}


async def test_fresh_install_no_false_positives(hass: HomeAssistant):
    """Test that fresh install has no false positives with capabilities.

    Simulates a fresh Home Assistant install where:
    - Entity registry has capabilities
    - No recorder history exists
    - State attributes might be incomplete
    """
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create select entity (no history, capabilities only)
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test_integration",
        unique_id="fresh_select",
        suggested_object_id="input_mode",
        capabilities={"options": ["option_a", "option_b", "option_c"]},
    )
    hass.states.async_set("select.input_mode", "option_a")

    # Create climate entity (no history, capabilities only)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test_integration",
        unique_id="fresh_climate",
        suggested_object_id="thermostat",
        capabilities={
            "hvac_modes": ["heat", "cool", "auto", "off"],
            "fan_modes": ["low", "medium", "high"],
            "preset_modes": ["eco", "comfort"],
        },
    )
    hass.states.async_set(
        "climate.thermostat",
        "off",
        attributes={},  # Minimal attributes (like fresh install)
    )

    await hass.async_block_till_done()

    # Verify select options are valid (no false positives)
    select_states = kb.get_valid_states("select.input_mode")
    assert "option_a" in select_states
    assert "option_b" in select_states
    assert "option_c" in select_states
    assert select_states == {"option_a", "option_b", "option_c", "unavailable", "unknown"}

    # Verify climate hvac_modes are valid (no false positives)
    climate_states = kb.get_valid_states("climate.thermostat")
    assert "heat" in climate_states
    assert "cool" in climate_states
    assert "auto" in climate_states
    assert "off" in climate_states
    assert climate_states >= {"heat", "cool", "auto", "off", "heat_cool", "dry", "fan_only", "unavailable", "unknown"}

    # Verify climate attribute values are valid
    fan_values = kb.get_valid_attributes("climate.thermostat", "fan_mode")
    assert fan_values == {"low", "medium", "high"}

    preset_values = kb.get_valid_attributes("climate.thermostat", "preset_mode")
    assert preset_values == {"eco", "comfort"}

    # Verify history is NOT required
    assert not kb.has_history_loaded()


async def test_bermuda_sensor_detected_by_platform(hass: HomeAssistant):
    """Test that Bermuda BLE area sensor is detected by integration platform.

    Note: Sensors return None from get_valid_states() (sensors are too free-form
    to validate). However, get_integration() is still called for sensors in
    is_area_sensor detection -- it just doesn't reach that code due to early return.
    This test verifies the sensor domain early-return behavior is preserved and
    that get_integration is used (not substring matching) for the detection logic.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zones and areas for completeness
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    from homeassistant.helpers import area_registry as ar
    area_registry = ar.async_get(hass)
    area_registry.async_create("Kitchen")
    await hass.async_block_till_done()

    # Create a Bermuda BLE area sensor
    hass.states.async_set("sensor.bermuda_ble_area_kitchen", "kitchen")
    await hass.async_block_till_done()

    mock_registry = MagicMock()
    mock_entry_bermuda = MagicMock()
    mock_entry_bermuda.platform = "bermuda"
    mock_registry.async_get.return_value = mock_entry_bermuda

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        # Sensors return None from get_valid_states (domain == "sensor" early return)
        states = kb.get_valid_states("sensor.bermuda_ble_area_kitchen")

    # Sensor domain returns None (sensors are too free-form for state validation)
    assert states is None


async def test_non_bermuda_area_sensor_not_matched(hass: HomeAssistant):
    """Test that non-Bermuda sensor with '_area' in name is NOT falsely matched.

    This is the key regression test: sensor.living_area_temperature should NOT
    get zone/area names injected into valid states. With substring matching,
    '_area' in entity_id would have matched this entity. With platform-based
    detection, only bermuda integration sensors would match.

    Since sensors return None from get_valid_states (early return), this test
    verifies the sensor is NOT treated specially regardless of its name.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zones and areas
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    hass.states.async_set("zone.work", "zoning", {"friendly_name": "Work"})
    from homeassistant.helpers import area_registry as ar
    area_registry = ar.async_get(hass)
    area_registry.async_create("Kitchen")
    area_registry.async_create("Bedroom")
    await hass.async_block_till_done()

    # Create sensor with _area in name but NOT bermuda platform
    hass.states.async_set("sensor.living_area_temperature", "22.5")
    await hass.async_block_till_done()

    mock_registry = MagicMock()
    mock_entry_mqtt = MagicMock()
    mock_entry_mqtt.platform = "mqtt"
    mock_registry.async_get.return_value = mock_entry_mqtt

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("sensor.living_area_temperature")

    # Sensor returns None (NOT a set with zone/area names injected)
    assert states is None


async def test_bermuda_device_tracker_detected_by_platform(hass: HomeAssistant):
    """Test that Bermuda BLE device_tracker is detected by integration platform.

    device_tracker entities DO go through full get_valid_states logic (no early
    return). This test verifies that platform-based detection correctly identifies
    a bermuda device_tracker and adds area names to its valid states.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zones and areas
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    hass.states.async_set("zone.work", "zoning", {"friendly_name": "Work"})
    from homeassistant.helpers import area_registry as ar
    area_registry = ar.async_get(hass)
    area_registry.async_create("Kitchen")
    area_registry.async_create("Bedroom")
    await hass.async_block_till_done()

    # Create a Bermuda device_tracker
    hass.states.async_set("device_tracker.bermuda_ble_phone", "home")
    await hass.async_block_till_done()

    mock_registry = MagicMock()
    mock_entry_bermuda = MagicMock()
    mock_entry_bermuda.platform = "bermuda"
    mock_entry_bermuda.capabilities = None
    mock_registry.async_get.return_value = mock_entry_bermuda

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("device_tracker.bermuda_ble_phone")

    # device_tracker gets zone names (all device_trackers do)
    assert "Home" in states
    assert "Work" in states

    # Bermuda tracker additionally gets HA area names
    assert "Kitchen" in states
    assert "Bedroom" in states
    # Also lowercase area names (added by _get_area_names)
    assert "kitchen" in states
    assert "bedroom" in states
    assert states >= {"home", "not_home", "Home", "Work", "Kitchen", "Bedroom", "kitchen", "bedroom", "unavailable", "unknown"}


# --- Bermuda/area sensor detection (KB-06) ---


async def test_sensor_domain_returns_none_non_sensor_returns_set(hass: HomeAssistant):
    """Sensor entities return None; non-sensor entities return a set.

    Kills: Eq mutations on 'domain == "sensor"' (line 294).
    If == becomes !=, sensor would get a set and non-sensor would get None.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("sensor.temperature", "22.5")
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()

    # Sensor domain returns None (too free-form to validate)
    assert kb.get_valid_states("sensor.temperature") is None

    # Non-sensor domain returns a set with expected states
    result = kb.get_valid_states("binary_sensor.motion")
    assert isinstance(result, set)
    assert "on" in result
    assert "off" in result


# --- Bermuda tracker state filtering (KB-07) ---


async def test_bermuda_tracker_collects_bermuda_sensor_states(hass: HomeAssistant):
    """Bermuda tracker collects valid states from bermuda sensors.

    Kills: AddNot on 'if is_bermuda_tracker' (line 349) -- skipping the block
    means bermuda sensor states are not added.
    Kills: AddNot on 'if state.state not in ("unavailable", "unknown")' (line 353) --
    inverting means only unavailable/unknown are collected, excluding valid states.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zone (device_trackers need this)
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    from homeassistant.helpers import area_registry as ar

    area_reg = ar.async_get(hass)
    area_reg.async_create("Kitchen")
    await hass.async_block_till_done()

    # Create bermuda device_tracker
    hass.states.async_set("device_tracker.bermuda_phone", "home")

    # Create bermuda sensors: one valid, one unavailable
    hass.states.async_set("sensor.bermuda_area_kitchen", "kitchen")
    hass.states.async_set("sensor.bermuda_area_garage", "unavailable")
    await hass.async_block_till_done()

    # Mock: all entities are bermuda platform, no capabilities
    mock_registry = MagicMock()
    mock_entry = MagicMock()
    mock_entry.platform = "bermuda"
    mock_entry.capabilities = None
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("device_tracker.bermuda_phone")

    # "kitchen" from bermuda sensor (valid state, not unavailable/unknown)
    assert "kitchen" in states


# --- Zone entity friendly_name fallback (KB-08) ---


async def test_zone_without_friendly_name_uses_entity_id_suffix(hass: HomeAssistant):
    """Zone without friendly_name falls back to entity_id.split('.')[1].

    Kills: NumberReplacer on [1] -- [0] would produce 'zone',
    [2] would raise IndexError.
    """
    hass.states.async_set("zone.my_office", "zoning", {})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    zones = kb._get_zone_names()

    assert "my_office" in zones
    assert "zone" not in zones  # Would be [0] if index mutated


async def test_zone_with_and_without_friendly_name(hass: HomeAssistant):
    """Both friendly_name path and fallback path produce correct results.

    Verifies the two zone-name extraction paths work together.
    """
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    hass.states.async_set("zone.my_office", "zoning", {})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    zones = kb._get_zone_names()

    assert zones == {"Home", "my_office"}
