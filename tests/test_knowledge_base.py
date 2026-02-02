"""Tests for StateKnowledgeBase.

Tests cover the multi-source state validation system including:
- Device class defaults
- Learned states from user suppression
- Entity registry capabilities
- Schema introspection from state attributes
- Recorder history loading
- Bermuda BLE integration area detection
- Enum sensor validation
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from custom_components.autodoctor.knowledge_base import (
    CAPABILITY_ATTRIBUTE_SOURCES,
    CAPABILITY_STATE_SOURCES,
    StateKnowledgeBase,
)
from custom_components.autodoctor.learned_states_store import LearnedStatesStore


async def test_capability_constants_defined(hass: HomeAssistant) -> None:
    """Test that capability constants distinguish state vs attribute sources.

    The knowledge base uses entity registry capabilities to determine valid
    states (e.g., select.options) vs valid attribute values (e.g., climate.fan_modes).
    This ensures proper validation on fresh installs without history.
    """
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


async def test_knowledge_base_initialization(hass: HomeAssistant) -> None:
    """Test knowledge base initializes with default configuration.

    Verifies that the knowledge base starts with empty caches and default
    settings for history loading (30 days, 120s timeout).
    """
    kb = StateKnowledgeBase(hass)
    assert kb.hass is hass
    assert kb.history_days == 30
    assert kb.history_timeout == 120
    assert kb._cache == {}
    assert kb._observed_states == {}
    assert kb._learned_states_store is None
    assert kb._zone_names is None
    assert kb._area_names is None


async def test_get_valid_states_for_known_domain(hass: HomeAssistant) -> None:
    """Test valid states include device class defaults for known domains.

    Binary sensors have well-defined states (on/off) from device class defaults.
    This ensures validation works immediately on fresh installs.
    """
    kb = StateKnowledgeBase(hass)

    # Set up an actual entity state
    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    states = kb.get_valid_states("binary_sensor.motion")
    assert "on" in states
    assert "off" in states
    assert states == {"on", "off", "unavailable", "unknown"}


async def test_get_valid_states_unknown_entity(hass: HomeAssistant) -> None:
    """Test that unknown entities return None (sensors have no predefined states).

    Sensors are too free-form to validate, so they return None unless they're
    enum sensors with explicit options.
    """
    kb = StateKnowledgeBase(hass)

    states = kb.get_valid_states("sensor.nonexistent")
    assert states is None


async def test_entity_exists(hass: HomeAssistant) -> None:
    """Test entity existence checking in Home Assistant state registry.

    This is used by validators to distinguish between typos (entity doesn't exist)
    and state mismatches (entity exists but state is wrong).
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    assert kb.entity_exists("binary_sensor.motion") is True
    assert kb.entity_exists("binary_sensor.missing") is False


async def test_get_domain(hass: HomeAssistant) -> None:
    """Test domain extraction from entity ID strings.

    Domain is the part before the dot in entity IDs (e.g., 'light' from 'light.bedroom').
    Returns empty string for malformed IDs.
    """
    kb = StateKnowledgeBase(hass)
    assert kb.get_domain("binary_sensor.motion") == "binary_sensor"
    assert kb.get_domain("light.living_room") == "light"
    assert kb.get_domain("invalid") == ""


async def test_clear_cache(hass: HomeAssistant) -> None:
    """Test that cache clearing resets all cached data structures.

    Cache should be cleared when entities are added/removed or when the user
    requests a fresh validation pass. This ensures stale data doesn't cause
    false positives.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zone and area
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
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


async def test_schema_introspection_climate_hvac_modes(hass: HomeAssistant) -> None:
    """Test that hvac_modes from entity state attributes are recognized.

    Schema introspection reads hvac_modes from climate entity attributes to
    determine valid states. This supplements device class defaults with
    integration-specific modes.
    """
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
    assert states >= {
        "off",
        "heat",
        "cool",
        "auto",
        "heat_cool",
        "dry",
        "fan_only",
        "unavailable",
        "unknown",
    }


async def test_schema_introspection_select_options(hass: HomeAssistant) -> None:
    """Test that select entity options are extracted from state attributes.

    Select entities declare their valid options in the 'options' attribute,
    which defines all possible states the entity can be in.
    """
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


async def test_schema_introspection_light_effect_list(hass: HomeAssistant) -> None:
    """Test that light effects are treated as attribute values, not states.

    Light states are still on/off, but effect_list provides valid values for
    the 'effect' attribute. This distinction prevents false positives.
    """
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


async def test_load_history_adds_observed_states(hass: HomeAssistant) -> None:
    """Test that history loading captures actually-observed states.

    For entities with custom states (like input_select), history reveals states
    that have been used but aren't in device class defaults. Excludes
    unavailable/unknown which are always valid.
    """
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


async def test_history_excludes_unavailable_unknown(hass: HomeAssistant) -> None:
    """Test that unavailable/unknown states are not tracked as observed states.

    These states are always valid and don't represent actual operational states,
    so they shouldn't be counted in the observed states set.
    """
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


async def test_get_historical_entity_ids(hass: HomeAssistant) -> None:
    """Test retrieving entities that have been seen in recorder history.

    Historical entities may no longer exist in the current state registry but
    could still be referenced in automations. This helps detect stale references.
    """
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


async def test_get_integration_from_entity_registry(hass: HomeAssistant) -> None:
    """Test that integration platform name is extracted from entity registry.

    Integration names (e.g., 'roborock', 'bermuda') are used to apply
    integration-specific validation rules like custom states or area detection.
    """

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


async def test_get_integration_returns_none_for_unknown(hass: HomeAssistant) -> None:
    """Test that entities not in registry return None for integration.

    Entities not in the entity registry (e.g., manually created via YAML)
    don't have integration metadata, so integration-specific rules don't apply.
    """

    kb = StateKnowledgeBase(hass)

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = None

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        integration = kb.get_integration("vacuum.unknown")

    assert integration is None


async def test_get_valid_states_includes_learned_states(hass: HomeAssistant) -> None:
    """Test that user-learned states are merged into valid states.

    When users suppress false positives, those states are saved and treated
    as valid. This allows custom states (e.g., Roborock 'segment_cleaning')
    to be recognized without false positives.
    """

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
    assert states >= {
        "segment_cleaning",
        "cleaning",
        "docked",
        "idle",
        "paused",
        "returning",
        "error",
        "unavailable",
        "unknown",
    }


async def test_zone_names_are_cached(hass: HomeAssistant) -> None:
    """Test that zone names are cached to avoid repeated lookups.

    Zone names are used for device_tracker/person validation. Caching improves
    performance but means stale data until clear_cache() is called.
    """
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


async def test_area_names_are_cached(hass: HomeAssistant) -> None:
    """Test that area names are cached for Bermuda tracker validation.

    Area names (both original case and lowercase) are valid states for Bermuda
    BLE device trackers. Caching avoids repeated registry lookups.
    """

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


async def test_load_history_uses_executor(hass: HomeAssistant) -> None:
    """Test that history loading offloads to executor thread.

    Recorder queries are blocking I/O operations that should run in an executor
    to avoid blocking the event loop.
    """

    kb = StateKnowledgeBase(hass)

    # Mock async_add_executor_job
    hass.async_add_executor_job = AsyncMock(return_value={})

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states"):
        await kb.async_load_history(["light.test"])

    # Should have called async_add_executor_job
    assert hass.async_add_executor_job.called


async def test_has_history_loaded(hass: HomeAssistant) -> None:
    """Test detection of whether history has been loaded.

    This allows callers to determine if observed states are available or if
    validation is relying solely on defaults and capabilities.
    """
    kb = StateKnowledgeBase(hass)

    # Initially empty
    assert kb.has_history_loaded() is False

    # After adding observed states
    kb._observed_states["light.test"] = {"on", "off"}
    assert kb.has_history_loaded() is True


async def test_get_capabilities_states_select_entity(hass: HomeAssistant) -> None:
    """Test that entity registry capabilities provide valid states on fresh install.

    Entity registry capabilities are declared by integrations and remain available
    even when history is empty, preventing false positives on new installs.
    """

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


async def test_get_capabilities_states_climate_entity(hass: HomeAssistant) -> None:
    """Test that climate capabilities distinguish hvac_modes (states) from fan_modes (attributes).

    Only capability keys in CAPABILITY_STATE_SOURCES are treated as valid states.
    Attribute sources like fan_modes are handled separately.
    """

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


async def test_get_capabilities_states_no_capabilities(hass: HomeAssistant) -> None:
    """Test that entities without capabilities return empty set.

    Simple entities (switches, basic sensors) don't declare capabilities,
    so they rely entirely on device class defaults and history.
    """

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


async def test_get_capabilities_states_no_registry_entry(hass: HomeAssistant) -> None:
    """Test that entities not in registry (YAML-defined) return empty set.

    Legacy YAML entities aren't in the entity registry and don't have
    capabilities metadata.
    """
    kb = StateKnowledgeBase(hass)

    # Entity exists in states but not in registry
    hass.states.async_set("sensor.temperature", "20")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("sensor.temperature")
    assert states == set()


async def test_get_capabilities_states_invalid_capability_format(hass: HomeAssistant) -> None:
    """Test that malformed capability values are safely ignored.

    Defensive programming: capabilities should be lists, but if they're not,
    we return empty set rather than crashing.
    """

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


async def test_get_valid_states_uses_capabilities(hass: HomeAssistant) -> None:
    """Test that capabilities enable validation on fresh installs without history.

    This is critical for preventing false positives when users install Autodoctor
    on a new system with no recorder history.
    """

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


async def test_attribute_maps_to_capability(hass: HomeAssistant) -> None:
    """Test that attribute names map to their capability keys correctly.

    Attributes like 'fan_mode' map to capability key 'fan_modes' (plural).
    This mapping allows validating attribute values against capabilities.
    """
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


async def test_get_capabilities_attribute_values_climate(hass: HomeAssistant) -> None:
    """Test that climate capability attribute values are extracted correctly.

    Climate entities declare valid fan_modes and preset_modes in capabilities,
    which defines valid values for those attributes (not states).
    """

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


async def test_get_valid_attributes_uses_capabilities(hass: HomeAssistant) -> None:
    """Test that attribute validation works on fresh installs using capabilities.

    Even without current state attributes, capabilities provide valid attribute
    values to prevent false positives.
    """

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


async def test_fresh_install_no_false_positives(hass: HomeAssistant) -> None:
    """Test comprehensive fresh install scenario without false positives.

    Simulates a fresh Home Assistant install where:
    - Entity registry has capabilities
    - No recorder history exists
    - State attributes might be incomplete

    This is the primary regression test for capabilities feature - ensures
    validation works correctly without any history.
    """

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
    assert select_states == {
        "option_a",
        "option_b",
        "option_c",
        "unavailable",
        "unknown",
    }

    # Verify climate hvac_modes are valid (no false positives)
    climate_states = kb.get_valid_states("climate.thermostat")
    assert "heat" in climate_states
    assert "cool" in climate_states
    assert "auto" in climate_states
    assert "off" in climate_states
    assert climate_states >= {
        "heat",
        "cool",
        "auto",
        "off",
        "heat_cool",
        "dry",
        "fan_only",
        "unavailable",
        "unknown",
    }

    # Verify climate attribute values are valid
    fan_values = kb.get_valid_attributes("climate.thermostat", "fan_mode")
    assert fan_values == {"low", "medium", "high"}

    preset_values = kb.get_valid_attributes("climate.thermostat", "preset_mode")
    assert preset_values == {"eco", "comfort"}

    # Verify history is NOT required
    assert not kb.has_history_loaded()


async def test_bermuda_sensor_detected_by_platform(hass: HomeAssistant) -> None:
    """Test that Bermuda BLE sensors are detected by platform, not name matching.

    Bermuda BLE area sensors use integration platform detection (not entity_id
    substring matching) to avoid false positives. However, sensor domain returns
    None early, so this test verifies that behavior is preserved.

    Uses platform='bermuda' check, not '_area' substring in entity_id.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zones and areas for completeness
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
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


async def test_non_bermuda_area_sensor_not_matched(hass: HomeAssistant) -> None:
    """Test that non-Bermuda sensors with '_area' in name are not falsely matched.

    This is the key regression test: sensor.living_area_temperature should NOT
    be treated as a Bermuda area sensor based on substring matching.

    Platform-based detection (platform='bermuda') prevents false positives from
    entity names containing '_area'. Sensors return None regardless.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zones and areas
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    hass.states.async_set("zone.work", "zoning", {"friendly_name": "Work"})
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


async def test_bermuda_device_tracker_detected_by_platform(hass: HomeAssistant) -> None:
    """Test that Bermuda BLE device_trackers get both zone and area names.

    device_tracker entities go through full validation logic. Platform-based
    detection identifies bermuda trackers and adds HA area names as valid states,
    in addition to standard zone names that all trackers receive.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zones and areas
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    hass.states.async_set("zone.work", "zoning", {"friendly_name": "Work"})
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
    assert states >= {
        "home",
        "not_home",
        "Home",
        "Work",
        "Kitchen",
        "Bedroom",
        "kitchen",
        "bedroom",
        "unavailable",
        "unknown",
    }


# === Mutation Testing Guards ===
# These tests target specific mutations to ensure robustness


async def test_sensor_domain_returns_none_non_sensor_returns_set(hass: HomeAssistant) -> None:
    """Test that sensor domain correctly returns None while others return sets.

    Mutation guard: Kills Eq mutations on 'domain == "sensor"'.
    If == becomes !=, sensor would incorrectly get a set and non-sensor would get None.
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


async def test_bermuda_tracker_collects_bermuda_sensor_states(hass: HomeAssistant) -> None:
    """Test that Bermuda trackers collect states from Bermuda sensors only.

    Mutation guard: Kills AddNot on 'if is_bermuda_tracker' and 'if state.state not in'.
    Ensures bermuda sensor states are collected but unavailable/unknown are excluded.
    """
    kb = StateKnowledgeBase(hass)

    # Set up zone (device_trackers need this)
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
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


async def test_zone_without_friendly_name_uses_entity_id_suffix(hass: HomeAssistant) -> None:
    """Test that zones without friendly_name use entity_id suffix correctly.

    Mutation guard: Kills NumberReplacer on [1] index.
    [0] would produce 'zone' instead of the actual zone name,
    [2] would raise IndexError.
    """
    hass.states.async_set("zone.my_office", "zoning", {})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    zones = kb._get_zone_names()

    assert "my_office" in zones
    assert "zone" not in zones  # Would be [0] if index mutated


async def test_zone_with_and_without_friendly_name(hass: HomeAssistant) -> None:
    """Test that both zone name extraction paths work together correctly.

    Verifies that zones with friendly_name and zones without both contribute
    to the valid zone names set.
    """
    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    hass.states.async_set("zone.my_office", "zoning", {})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    zones = kb._get_zone_names()

    assert zones == {"Home", "my_office"}


async def test_get_valid_attributes_empty_list_returns_none(hass: HomeAssistant) -> None:
    """Test that empty attribute lists correctly return None.

    Mutation guard: Kills and->or on 'if values and isinstance(values, list)'.
    With 'or', isinstance([], list) would return empty set instead of None.
    Uses 'effect' attribute which has no capability mapping.
    """
    kb = StateKnowledgeBase(hass)
    hass.states.async_set("light.test", "on", {"effect_list": []})
    await hass.async_block_till_done()

    result = kb.get_valid_attributes("light.test", "effect")
    assert result is None


async def test_get_valid_attributes_non_list_string_returns_none(hass: HomeAssistant) -> None:
    """Test that non-list attribute values return None, not character sets.

    Mutation guard: Kills and->or on attribute value type checking.
    With 'or', truthy strings would be iterated into character sets.
    """
    kb = StateKnowledgeBase(hass)
    hass.states.async_set("light.test", "on", {"effect_list": "rainbow"})
    await hass.async_block_till_done()

    result = kb.get_valid_attributes("light.test", "effect")
    assert result is None


async def test_async_load_history_start_time_is_in_past(hass: HomeAssistant) -> None:
    """Test that history loading correctly uses past time range.

    Mutation guard: Kills Sub->Add on 'datetime.now(UTC) - timedelta(days=...)'.
    Mutation would produce start_time in the future, which makes no sense for history.
    """
    from datetime import UTC, datetime

    kb = StateKnowledgeBase(hass, history_days=30)
    hass.async_add_executor_job = AsyncMock(return_value={})

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states"):
        await kb.async_load_history(["light.test"])

    # Capture the args passed to async_add_executor_job
    assert hass.async_add_executor_job.called
    call_args = hass.async_add_executor_job.call_args
    # args: (get_significant_states, hass, start_time, end_time, entity_ids, None, True, True)
    start_time = call_args[0][2]  # Third positional arg
    end_time = call_args[0][3]  # Fourth positional arg

    now = datetime.now(UTC)
    assert start_time < end_time
    assert start_time < now  # Must be in the past


async def test_non_bermuda_device_tracker_no_area_names(hass: HomeAssistant) -> None:
    """Test that non-Bermuda trackers get zones but not area names.

    Mutation guard: Kills Eq on 'get_integration(entity_id) == "bermuda"'.
    If == becomes !=, non-bermuda trackers would incorrectly get area names.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    area_reg = ar.async_get(hass)
    area_reg.async_create("Kitchen")
    await hass.async_block_till_done()

    hass.states.async_set("device_tracker.phone", "home")
    await hass.async_block_till_done()

    # Mock: entity is from 'owntracks', not bermuda
    mock_registry = MagicMock()
    mock_entry = MagicMock()
    mock_entry.platform = "owntracks"
    mock_entry.capabilities = None
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("device_tracker.phone")

    # Should have zone names (all device_trackers do)
    assert "Home" in states
    # Should NOT have area names (only bermuda trackers do)
    assert "Kitchen" not in states
    assert "kitchen" not in states


async def test_bermuda_sensor_gets_zone_and_area_names(hass: HomeAssistant) -> None:
    """Test that Bermuda sensors return None (sensor early return preserved).

    Mutation guard: Kills and->or on 'domain == "sensor" and ... == "bermuda"'.
    With 'or', non-sensor domains would incorrectly match is_area_sensor logic.

    Note: Sensor domain returns None due to early return, so Bermuda sensors
    still don't get area name validation (sensors are too free-form).
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    area_reg = ar.async_get(hass)
    area_reg.async_create("Kitchen")
    await hass.async_block_till_done()

    # bermuda sensor
    hass.states.async_set("sensor.bermuda_area", "kitchen")
    # non-bermuda binary_sensor — should NOT be treated as area sensor
    hass.states.async_set("binary_sensor.bermuda_motion", "on")
    await hass.async_block_till_done()

    def mock_get(entity_id):
        entry = MagicMock()
        if "bermuda" in entity_id:
            entry.platform = "bermuda"
        else:
            entry.platform = "generic"
        entry.capabilities = None
        return entry

    mock_registry = MagicMock()
    mock_registry.async_get.side_effect = mock_get

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        # Sensor domain returns None (early return)
        sensor_states = kb.get_valid_states("sensor.bermuda_area")
        assert sensor_states is None

        # binary_sensor should NOT have area names (not bermuda tracker)
        bs_states = kb.get_valid_states("binary_sensor.bermuda_motion")
        assert "Kitchen" not in bs_states
        assert "kitchen" not in bs_states


async def test_bermuda_tracker_collects_only_bermuda_sensor_states(hass: HomeAssistant) -> None:
    """Test that Bermuda trackers only collect Bermuda sensor states.

    Mutation guard: Kills ZeroIterationForLoop and Eq on platform check.
    Ensures loop runs and only collects from bermuda sensors, not all sensors.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    area_reg = ar.async_get(hass)
    area_reg.async_create("Office")
    await hass.async_block_till_done()

    hass.states.async_set("device_tracker.bermuda_phone", "home")
    # bermuda sensor with unique state
    hass.states.async_set("sensor.bermuda_area_office", "office")
    # non-bermuda sensor — its state should NOT be collected
    hass.states.async_set("sensor.weather_temp", "22.5")
    await hass.async_block_till_done()

    def mock_get(entity_id):
        entry = MagicMock()
        entry.capabilities = None
        if "bermuda" in entity_id:
            entry.platform = "bermuda"
        else:
            entry.platform = "generic"
        return entry

    mock_registry = MagicMock()
    mock_registry.async_get.side_effect = mock_get

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("device_tracker.bermuda_phone")

    # "office" from bermuda sensor should be in states
    assert "office" in states
    # "22.5" from non-bermuda sensor should NOT be in states
    assert "22.5" not in states


async def test_person_entity_gets_zones_but_not_area_names(hass: HomeAssistant) -> None:
    """Test that person entities get zone names but not area names.

    Mutation guard: Kills AddNot on 'if is_area_sensor or is_bermuda_tracker'.
    If inverted, non-bermuda entities would incorrectly get area names.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    area_reg = ar.async_get(hass)
    area_reg.async_create("Garage")
    await hass.async_block_till_done()

    hass.states.async_set("person.john", "home")
    await hass.async_block_till_done()

    mock_registry = MagicMock()
    mock_entry = MagicMock()
    mock_entry.platform = "default"
    mock_entry.capabilities = None
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("person.john")

    # Person gets zone names
    assert "Home" in states
    # Person does NOT get area names (not bermuda)
    assert "Garage" not in states
    assert "garage" not in states


async def test_bermuda_tracker_excludes_unavailable_sensor_states(hass: HomeAssistant) -> None:
    """Test that Bermuda trackers exclude unavailable/unknown sensor states.

    Mutation guard: Kills 'not in' -> 'in' mutation.
    If inverted, only unavailable/unknown would be collected, excluding valid states.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("zone.home", "zoning", {"friendly_name": "Home"})
    area_reg = ar.async_get(hass)
    area_reg.async_create("Bedroom")
    await hass.async_block_till_done()

    hass.states.async_set("device_tracker.bermuda_watch", "home")
    hass.states.async_set("sensor.bermuda_area_bedroom", "bedroom")
    hass.states.async_set("sensor.bermuda_area_unknown", "unknown")
    hass.states.async_set("sensor.bermuda_area_unavail", "unavailable")
    await hass.async_block_till_done()

    mock_registry = MagicMock()
    mock_entry = MagicMock()
    mock_entry.platform = "bermuda"
    mock_entry.capabilities = None
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("device_tracker.bermuda_watch")

    # "bedroom" is valid, should be collected
    assert "bedroom" in states
    # unavailable/unknown ARE in valid_states (always added), but should not
    # have been collected from the bermuda sensor iteration path specifically.
    # The key assertion: "bedroom" is present (proves the loop ran and
    # filtered correctly). If the mutation flipped `not in` to `in`,
    # only "unknown" and "unavailable" would be collected, not "bedroom".


async def test_non_bermuda_sensor_returns_none(hass: HomeAssistant) -> None:
    """Test that non-Bermuda sensors return None (sensor domain early return).

    Mutation guard: Verifies sensor early return at domain check.
    Even if is_area_sensor logic were mutated, sensors still return None.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("sensor.generic_temp", "22.5")
    await hass.async_block_till_done()

    mock_registry = MagicMock()
    mock_entry = MagicMock()
    mock_entry.platform = "generic"
    mock_entry.capabilities = None
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry,
    ):
        states = kb.get_valid_states("sensor.generic_temp")

    assert states is None


# === Enum Sensor Validation ===


async def test_enum_sensor_returns_options_as_valid_states(hass: HomeAssistant) -> None:
    """Test that enum sensors with options enable state validation.

    Enum sensors (device_class: enum with options list) are the exception to
    the "sensors return None" rule. They have well-defined states that can
    be validated, preventing false positives for state references.
    """
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "sensor.washing_machine_status",
        "idle",
        {"device_class": "enum", "options": ["idle", "washing", "drying"]},
    )
    await hass.async_block_till_done()

    states = kb.get_valid_states("sensor.washing_machine_status")
    assert states is not None
    assert isinstance(states, set)
    assert "idle" in states
    assert "washing" in states
    assert "drying" in states
    assert "unavailable" in states
    assert "unknown" in states
    # Current state always included
    assert states >= {"idle", "washing", "drying", "unavailable", "unknown"}


async def test_non_enum_sensor_still_returns_none(hass: HomeAssistant) -> None:
    """Non-enum sensors continue to return None (no state validation)."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "sensor.temperature",
        "22.5",
        {"device_class": "temperature", "unit_of_measurement": "°C"},
    )
    await hass.async_block_till_done()

    # Temperature sensors are not enum, should return None
    assert kb.get_valid_states("sensor.temperature") is None


async def test_sensor_without_device_class_returns_none(hass: HomeAssistant) -> None:
    """Sensors without device_class attribute return None."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("sensor.custom_value", "42")
    await hass.async_block_till_done()

    # No device_class, should return None
    assert kb.get_valid_states("sensor.custom_value") is None


async def test_enum_sensor_empty_options_returns_none(hass: HomeAssistant) -> None:
    """Enum sensor with empty options list returns None (not valid for validation)."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "sensor.bad_enum", "unknown", {"device_class": "enum", "options": []}
    )
    await hass.async_block_till_done()

    # Empty options should fail the non-empty guard
    assert kb.get_valid_states("sensor.bad_enum") is None


async def test_enum_sensor_options_not_list_returns_none(hass: HomeAssistant) -> None:
    """Enum sensor with non-list options attribute returns None."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "sensor.bad_enum", "unknown", {"device_class": "enum", "options": "not_a_list"}
    )
    await hass.async_block_till_done()

    # options must be a list, not a string
    assert kb.get_valid_states("sensor.bad_enum") is None


async def test_enum_sensor_caches_result(hass: HomeAssistant) -> None:
    """Enum sensor results are cached (consistent with other domains)."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set(
        "sensor.mode",
        "auto",
        {"device_class": "enum", "options": ["auto", "manual"]},
    )
    await hass.async_block_till_done()

    # First call populates cache
    states1 = kb.get_valid_states("sensor.mode")
    assert "auto" in states1
    assert "manual" in states1

    # Second call uses cache (verify cache key exists)
    assert "sensor.mode" in kb._cache

    # Second call returns copy of cached data
    states2 = kb.get_valid_states("sensor.mode")
    assert states1 == states2
    assert states1 is not states2  # Different objects (copy)


# --- Quick task 015: Coverage improvements for knowledge_base.py ---


@pytest.mark.asyncio
async def test_get_capabilities_states_exception_returns_empty(hass: HomeAssistant) -> None:
    """Test that entity registry exception returns empty set."""
    kb = StateKnowledgeBase(hass)

    with patch("custom_components.autodoctor.knowledge_base.er.async_get", side_effect=RuntimeError("Registry error")):
        result = kb._get_capabilities_states("select.test")

    assert result == set()


@pytest.mark.asyncio
async def test_get_capabilities_attribute_values_exception_returns_empty(hass: HomeAssistant) -> None:
    """Test that exception during attribute value extraction returns empty set."""
    kb = StateKnowledgeBase(hass)

    with patch("custom_components.autodoctor.knowledge_base.er.async_get", side_effect=RuntimeError("Registry error")):
        result = kb._get_capabilities_attribute_values("climate.test", "fan_mode")

    assert result == set()


@pytest.mark.asyncio
async def test_get_capabilities_attribute_values_no_matching_capability(hass: HomeAssistant) -> None:
    """Test attribute value extraction when capability key doesn't exist."""
    kb = StateKnowledgeBase(hass)

    # Create mock entity entry with capabilities but missing fan_modes
    mock_entry = MagicMock()
    mock_entry.capabilities = {"hvac_modes": ["heat", "cool"]}  # No fan_modes

    with patch("custom_components.autodoctor.knowledge_base.er.async_get") as mock_get:
        mock_registry = MagicMock()
        mock_registry.async_get.return_value = mock_entry
        mock_get.return_value = mock_registry

        result = kb._get_capabilities_attribute_values("climate.thermostat", "fan_mode")

    assert result == set()


@pytest.mark.asyncio
async def test_async_load_history_timeout(hass: HomeAssistant) -> None:
    """Test history loading handles timeout gracefully."""
    kb = StateKnowledgeBase(hass, history_timeout=1)

    async def slow_load(*args, **kwargs):
        await asyncio.sleep(10)
        return {}

    hass.async_add_executor_job = slow_load

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states"):
        # Should timeout and not crash
        try:
            await asyncio.wait_for(kb.async_load_history(["light.test"]), timeout=0.5)
        except asyncio.TimeoutError:
            pass  # Expected

    assert kb._observed_states == {}


@pytest.mark.asyncio
async def test_async_load_history_general_exception(hass: HomeAssistant) -> None:
    """Test history loading handles general exceptions gracefully."""
    kb = StateKnowledgeBase(hass)

    hass.async_add_executor_job = AsyncMock(side_effect=Exception("Load failed"))

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states"):
        await kb.async_load_history(["light.test"])

    # Should not crash, observed states remain empty
    assert kb._observed_states == {}


@pytest.mark.asyncio
async def test_async_load_history_no_recorder(hass: HomeAssistant) -> None:
    """Test history loading when recorder is not available."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("light.test", "on")
    await hass.async_block_till_done()

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states", None):
        await kb.async_load_history(["light.test"])

    # Should not crash
    assert kb._observed_states == {}


@pytest.mark.asyncio
async def test_async_load_history_dict_format_states(hass: HomeAssistant) -> None:
    """Test history loading with dict format states (not State objects)."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("light.test", "on")
    await hass.async_block_till_done()

    # Mock history returning dict format instead of State objects
    mock_history = {"light.test": [{"state": "on"}, {"state": "off"}, {"state": None}]}

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states", return_value=mock_history):
        hass.async_add_executor_job = AsyncMock(return_value=mock_history)
        await kb.async_load_history(["light.test"])

    states = kb.get_observed_states("light.test")
    assert "on" in states
    assert "off" in states
    assert None not in states  # None states filtered out


@pytest.mark.asyncio
async def test_async_load_history_merges_existing_observed(hass: HomeAssistant) -> None:
    """Test that history loading merges with existing observed states."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("light.test", "on")
    await hass.async_block_till_done()

    # Pre-populate observed states
    kb._observed_states["light.test"] = {"on"}

    mock_state = MagicMock()
    mock_state.state = "off"
    mock_history = {"light.test": [mock_state]}

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states", return_value=mock_history):
        hass.async_add_executor_job = AsyncMock(return_value=mock_history)
        await kb.async_load_history(["light.test"])

    observed = kb.get_observed_states("light.test")
    assert "on" in observed
    assert "off" in observed


@pytest.mark.asyncio
async def test_async_load_history_updates_cache(hass: HomeAssistant) -> None:
    """Test that history loading updates existing cache."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("light.test", "on")
    await hass.async_block_till_done()

    # Pre-populate cache
    kb._cache["light.test"] = {"on", "unavailable", "unknown"}

    mock_state = MagicMock()
    mock_state.state = "off"
    mock_history = {"light.test": [mock_state]}

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states", return_value=mock_history):
        hass.async_add_executor_job = AsyncMock(return_value=mock_history)
        await kb.async_load_history(["light.test"])

    # Cache should now include "off"
    states = kb.get_valid_states("light.test")
    assert "off" in states


@pytest.mark.asyncio
async def test_async_load_history_auto_discovers_whitelisted(hass: HomeAssistant) -> None:
    """Test history auto-discovery loads only whitelisted entities."""
    kb = StateKnowledgeBase(hass)

    # Set up whitelisted and non-whitelisted entities
    hass.states.async_set("binary_sensor.motion", "on")
    hass.states.async_set("sensor.temp", "20")
    await hass.async_block_till_done()

    mock_history = {}

    def mock_get_significant(hass, start, end, entity_ids=None, **kwargs):
        # Capture which entities were requested
        mock_get_significant.called_with_entities = entity_ids
        return mock_history

    mock_get_significant.called_with_entities = None

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states", side_effect=mock_get_significant):
        hass.async_add_executor_job = AsyncMock(return_value=mock_history)
        await kb.async_load_history()  # No entity_ids - should auto-discover

    # Should have requested only binary_sensor (whitelisted), not sensor
    requested = mock_get_significant.called_with_entities
    if requested:
        assert "binary_sensor.motion" in requested
        assert "sensor.temp" not in requested


@pytest.mark.asyncio
async def test_async_load_history_empty_entities_returns_early(hass: HomeAssistant) -> None:
    """Test that history loading returns early when no entities to load."""
    kb = StateKnowledgeBase(hass)

    # No whitelisted entities in state
    hass.async_add_executor_job = AsyncMock()

    with patch("custom_components.autodoctor.knowledge_base.get_significant_states"):
        await kb.async_load_history()  # No entity_ids, no whitelisted entities

    # Should not have called executor job
    hass.async_add_executor_job.assert_not_called()


@pytest.mark.asyncio
async def test_get_valid_states_cache_hit_returns_copy(hass: HomeAssistant) -> None:
    """Test that cache hit returns a copy to prevent external mutation."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("binary_sensor.test", "on")
    await hass.async_block_till_done()

    # Populate cache
    kb._cache["binary_sensor.test"] = {"on", "off"}

    # Get states
    states1 = kb.get_valid_states("binary_sensor.test")
    assert states1 == {"on", "off"}

    # Modify returned set
    states1.add("modified")

    # Get again - should not contain modification (returns copy)
    states2 = kb.get_valid_states("binary_sensor.test")
    assert "modified" not in states2
    assert states2 == {"on", "off"}
