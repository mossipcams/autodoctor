"""Tests for ValidationEngine."""

import pytest
from unittest.mock import MagicMock

from custom_components.autodoctor.validator import ValidationEngine
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import StateReference, Severity


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    return hass


@pytest.fixture
def knowledge_base(mock_hass):
    """Create a knowledge base with mocked data."""
    kb = StateKnowledgeBase(mock_hass)
    return kb


def test_validate_missing_entity(mock_hass, knowledge_base):
    """Test validation detects missing entity."""
    mock_hass.states.get = MagicMock(return_value=None)

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


def test_validate_invalid_state(mock_hass, knowledge_base):
    """Test validation detects invalid state."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

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


def test_validate_case_mismatch(mock_hass, knowledge_base):
    """Test validation detects case mismatch."""
    mock_state = MagicMock()
    mock_state.entity_id = "alarm_control_panel.home"
    mock_state.domain = "alarm_control_panel"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

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


def test_validate_valid_state(mock_hass, knowledge_base):
    """Test validation passes for valid state."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

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
