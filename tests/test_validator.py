"""Tests for ValidationEngine."""

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import IssueType, Severity, StateReference
from custom_components.autodoctor.validator import ValidationEngine


@pytest.fixture
def knowledge_base(hass: HomeAssistant):
    """Create a knowledge base with mocked data."""
    kb = StateKnowledgeBase(hass)
    return kb


async def test_validate_missing_entity(hass: HomeAssistant, knowledge_base):
    """Test validation detects missing entity."""
    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="binary_sensor.nonexistent",
        expected_state="on",
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "does not exist" in issues[0].message.lower()


async def test_validate_invalid_state(hass: HomeAssistant, knowledge_base):
    """Test validation detects invalid state."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        expected_state="away",
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "away" in issues[0].message


async def test_validate_case_mismatch(hass: HomeAssistant, knowledge_base):
    """Test validation detects case mismatch."""
    hass.states.async_set("alarm_control_panel.home", "disarmed")
    await hass.async_block_till_done()

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="alarm_control_panel.home",
        expected_state="Armed_Away",
        expected_attribute=None,
        location="condition[0].state",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert "case" in issues[0].message.lower()
    assert issues[0].suggestion == "armed_away"


async def test_validate_valid_state(hass: HomeAssistant, knowledge_base):
    """Test validation passes for valid state."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        expected_state="home",
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 0


@pytest.mark.asyncio
async def test_validate_detects_removed_entity(hass: HomeAssistant):
    """Test that validator detects entities that existed in history but are now gone."""
    kb = StateKnowledgeBase(hass)

    # Simulate that this entity was seen in history
    kb._observed_states["sensor.old_sensor"] = {"on", "off"}

    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.old_sensor",
        expected_state="on",
        expected_attribute=None,
        location="trigger[0].to",
    )

    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.ENTITY_REMOVED
    assert (
        "existed in history" in issues[0].message.lower()
        or "removed" in issues[0].message.lower()
    )


def test_validate_reference_handles_knowledge_base_error():
    """Test that knowledge_base errors don't crash validation."""
    mock_kb = MagicMock()
    mock_kb.entity_exists.side_effect = Exception("KB error")

    validator = ValidationEngine(mock_kb)
    ref = StateReference(
        entity_id="light.test",
        automation_id="test_auto",
        automation_name="Test",
        location="trigger[0]",
        expected_state=None,
        expected_attribute=None,
    )

    # Should not raise, should return empty list
    issues = validator.validate_reference(ref)
    assert issues == []


def test_validator_caches_entity_suggestions():
    """Test that entity cache is built once and reused."""
    mock_kb = MagicMock()
    mock_hass = MagicMock()
    mock_kb.hass = mock_hass

    # Return same entities each time
    mock_entity1 = MagicMock()
    mock_entity1.entity_id = "light.living_room"
    mock_entity2 = MagicMock()
    mock_entity2.entity_id = "light.bedroom"
    mock_hass.states.async_all.return_value = [mock_entity1, mock_entity2]

    validator = ValidationEngine(mock_kb)

    # Call _suggest_entity twice
    validator._suggest_entity("light.living_rom")  # Typo
    validator._suggest_entity("light.bedroon")  # Typo

    # async_all should only be called once (cached)
    assert mock_hass.states.async_all.call_count == 1


@pytest.mark.asyncio
async def test_no_false_positive_for_light_brightness_when_off(hass: HomeAssistant):
    """Test that checking brightness on a light that's off doesn't report error.

    Lights support brightness even when off, but the attribute isn't present
    in the current state. We should validate against supported attributes,
    not just current state attributes.
    """
    # Set up a light that's off - no brightness attribute present
    hass.states.async_set("light.bedroom", "off")
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.bedroom",
        expected_state=None,
        expected_attribute="brightness",
        location="trigger[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report an error - lights support brightness even when off
    assert len(issues) == 0


@pytest.mark.asyncio
async def test_no_false_positive_for_climate_temperature(hass: HomeAssistant):
    """Test that checking temperature on climate doesn't report false positive."""
    # Climate entity that's off - temperature attribute may not be present
    hass.states.async_set("climate.living_room", "off")
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state=None,
        expected_attribute="temperature",
        location="trigger[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report an error - climate supports temperature
    assert len(issues) == 0


@pytest.mark.asyncio
async def test_invalid_attribute_sets_issue_type(hass: HomeAssistant):
    """Test that invalid attributes set ATTRIBUTE_NOT_FOUND issue type."""
    # Create a light with standard attributes
    hass.states.async_set("light.bedroom", "on", {"brightness": 255})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    # Check for an attribute that doesn't exist and isn't supported by lights
    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.bedroom",
        expected_state=None,
        expected_attribute="nonexistent_attribute",
        location="condition[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should report an error with ATTRIBUTE_NOT_FOUND issue type
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.ATTRIBUTE_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert "nonexistent_attribute" in issues[0].message


@pytest.mark.asyncio
async def test_light_color_temp_attribute_is_valid(hass: HomeAssistant):
    """Test that color_temp is recognized as valid for light domain."""
    # Create a light without color_temp in current state
    hass.states.async_set("light.bedroom", "on", {"brightness": 255})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    # Reference color_temp which is not in state but IS a valid domain attribute
    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.bedroom",
        expected_state=None,
        expected_attribute="color_temp",
        location="condition[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report error - light domain supports color_temp
    assert len(issues) == 0


@pytest.mark.asyncio
async def test_light_rgb_color_attribute_is_valid(hass: HomeAssistant):
    """Test that rgb_color is recognized as valid for light domain."""
    # Create a light without rgb_color in current state
    hass.states.async_set("light.bedroom", "on", {"brightness": 255})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    # Reference rgb_color which is not in state but IS a valid domain attribute
    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.bedroom",
        expected_state=None,
        expected_attribute="rgb_color",
        location="condition[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report error - light domain supports rgb_color
    assert len(issues) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attribute",
    [
        "brightness",
        "color_temp",
        "hs_color",
        "rgb_color",
        "xy_color",
        "rgbw_color",
        "rgbww_color",
        "white_value",
        "color_mode",
        "supported_color_modes",
        "effect",
        "effect_list",
    ],
)
async def test_light_domain_attributes_are_valid(
    hass: HomeAssistant, attribute: str
):
    """Test that all standard light attributes are recognized as valid."""
    # Create a light with only brightness
    hass.states.async_set("light.bedroom", "on", {"brightness": 255})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.bedroom",
        expected_state=None,
        expected_attribute=attribute,
        location="condition[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report error - all these attributes are valid for light domain
    assert len(issues) == 0, f"Attribute '{attribute}' should be valid for light domain"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attribute",
    [
        "temperature",
        "target_temp_high",
        "target_temp_low",
        "current_temperature",
        "humidity",
        "current_humidity",
        "fan_mode",
        "fan_modes",
        "swing_mode",
        "swing_modes",
        "preset_mode",
        "preset_modes",
        "hvac_action",
        "hvac_modes",
    ],
)
async def test_climate_domain_attributes_are_valid(
    hass: HomeAssistant, attribute: str
):
    """Test that all standard climate attributes are recognized as valid."""
    # Create a climate entity with minimal attributes
    hass.states.async_set("climate.living_room", "heat", {"temperature": 22})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state=None,
        expected_attribute=attribute,
        location="condition[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report error - all these attributes are valid for climate domain
    assert len(issues) == 0, f"Attribute '{attribute}' should be valid for climate domain"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attribute",
    [
        "volume_level",
        "is_volume_muted",
        "media_content_id",
        "media_content_type",
        "media_duration",
        "media_position",
        "media_position_updated_at",
        "media_title",
        "media_artist",
        "media_album_name",
        "media_album_artist",
        "media_track",
        "media_series_title",
        "media_season",
        "media_episode",
        "source",
        "source_list",
        "sound_mode",
        "sound_mode_list",
        "shuffle",
        "repeat",
    ],
)
async def test_media_player_domain_attributes_are_valid(
    hass: HomeAssistant, attribute: str
):
    """Test that all standard media_player attributes are recognized as valid."""
    # Create a media_player with minimal attributes
    hass.states.async_set("media_player.living_room", "playing", {"volume_level": 0.5})
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="media_player.living_room",
        expected_state=None,
        expected_attribute=attribute,
        location="condition[0].attribute",
    )

    issues = validator.validate_reference(ref)

    # Should NOT report error - all these attributes are valid for media_player domain
    assert len(issues) == 0, f"Attribute '{attribute}' should be valid for media_player domain"
