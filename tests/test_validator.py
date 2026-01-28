"""Tests for ValidationEngine."""

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
