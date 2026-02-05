"""Tests for attribute value validation feature.

Tests cover:
- Analyzer captures attribute field from state triggers/conditions
- Analyzer captures is_state_attr() value (no longer discarded)
- Validator checks attribute values against knowledge base valid values
- INVALID_ATTRIBUTE_VALUE IssueType in entity_state group
- Edge cases: templates skipped, no valid values skipped, case mismatch
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import (
    VALIDATION_GROUPS,
    IssueType,
    Severity,
    StateReference,
)
from custom_components.autodoctor.validator import ValidationEngine

# ============================================================================
# Part 1: Analyzer attribute context extraction
# ============================================================================


def test_state_trigger_with_attribute_extracts_both() -> None:
    """Test that state trigger with attribute field captures both attribute and state.

    HA supports `trigger: state` with `attribute: fan_mode, to: eco`.
    The analyzer must set both expected_attribute and expected_state
    so the validator can check the attribute value.
    """
    automation: dict[str, Any] = {
        "id": "fan_eco",
        "alias": "Fan Eco Mode",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "climate.living_room",
                "attribute": "fan_mode",
                "to": "eco",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_state == "eco"
    assert refs[0].expected_attribute == "fan_mode"


def test_state_condition_with_attribute_extracts_both() -> None:
    """Test that state condition with attribute field captures both attribute and state.

    HA supports `condition: state` with `attribute: preset_mode, state: eco`.
    The analyzer must set both expected_attribute and expected_state.
    """
    automation: dict[str, Any] = {
        "id": "check_preset",
        "alias": "Check Preset",
        "trigger": [{"platform": "time", "at": "12:00:00"}],
        "condition": [
            {
                "condition": "state",
                "entity_id": "climate.bedroom",
                "attribute": "preset_mode",
                "state": "eco",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Filter to just the condition ref (trigger also produces a ref)
    condition_refs = [r for r in refs if "condition" in r.location]
    assert len(condition_refs) == 1
    assert condition_refs[0].entity_id == "climate.bedroom"
    assert condition_refs[0].expected_state == "eco"
    assert condition_refs[0].expected_attribute == "preset_mode"


def test_is_state_attr_captures_value() -> None:
    """Test that is_state_attr() captures the value as expected_state.

    The third argument to is_state_attr() is the expected value.
    Previously it was extracted as _value but discarded.
    """
    automation: dict[str, Any] = {
        "id": "check_fan",
        "alias": "Check Fan",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ is_state_attr('climate.office', 'fan_mode', 'auto') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    attr_refs = [r for r in refs if "is_state_attr" in r.location]
    assert len(attr_refs) == 1
    assert attr_refs[0].entity_id == "climate.office"
    assert attr_refs[0].expected_attribute == "fan_mode"
    assert attr_refs[0].expected_state == "auto"


def test_state_trigger_without_attribute_unchanged() -> None:
    """Guard: state trigger without attribute field still works as before.

    When no attribute field is present, expected_attribute must remain None.
    """
    automation: dict[str, Any] = {
        "id": "light_on",
        "alias": "Light On",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "light.kitchen",
                "to": "on",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].expected_state == "on"
    assert refs[0].expected_attribute is None


# ============================================================================
# Part 2: IssueType enum membership
# ============================================================================


def test_invalid_attribute_value_in_entity_state_group() -> None:
    """Test that INVALID_ATTRIBUTE_VALUE is in the entity_state validation group.

    This ensures the WebSocket API correctly groups attribute value issues
    with other entity/state checks.
    """
    entity_state_types: frozenset[IssueType] = VALIDATION_GROUPS["entity_state"]["issue_types"]  # type: ignore[assignment]
    assert IssueType.INVALID_ATTRIBUTE_VALUE in entity_state_types


# ============================================================================
# Part 3: Validator attribute value checking
# ============================================================================


async def test_valid_attribute_value_no_issue(
    hass: HomeAssistant,
) -> None:
    """Test that a valid attribute value produces no issue.

    'low' is a valid fan_mode → no issue should be reported.
    """
    hass.states.async_set(
        "climate.living_room",
        "cool",
        {"fan_mode": "low", "fan_modes": ["low", "medium", "high", "auto"]},
    )
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state="low",
        expected_attribute="fan_mode",
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    # Should have no INVALID_ATTRIBUTE_VALUE issues
    attr_issues = [i for i in issues if i.issue_type == IssueType.INVALID_ATTRIBUTE_VALUE]
    assert len(attr_issues) == 0


async def test_invalid_attribute_value_flagged(
    hass: HomeAssistant,
) -> None:
    """Test that an invalid attribute value is flagged as INVALID_ATTRIBUTE_VALUE.

    'turbo' is not in fan_modes → should produce a WARNING.
    """
    hass.states.async_set(
        "climate.living_room",
        "cool",
        {"fan_mode": "low", "fan_modes": ["low", "medium", "high", "auto"]},
    )
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state="turbo",
        expected_attribute="fan_mode",
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    attr_issues = [i for i in issues if i.issue_type == IssueType.INVALID_ATTRIBUTE_VALUE]
    assert len(attr_issues) == 1
    assert attr_issues[0].severity == Severity.WARNING
    assert "turbo" in attr_issues[0].message
    assert "fan_mode" in attr_issues[0].message


async def test_attribute_value_case_mismatch(
    hass: HomeAssistant,
) -> None:
    """Test that case mismatch in attribute value is flagged as CASE_MISMATCH.

    'Auto' vs 'auto' → should produce a CASE_MISMATCH warning.
    """
    hass.states.async_set(
        "climate.living_room",
        "cool",
        {"fan_mode": "auto", "fan_modes": ["low", "medium", "high", "auto"]},
    )
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state="Auto",
        expected_attribute="fan_mode",
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    case_issues = [i for i in issues if i.issue_type == IssueType.CASE_MISMATCH]
    assert len(case_issues) == 1
    assert case_issues[0].severity == Severity.WARNING
    assert "auto" in case_issues[0].suggestion


async def test_attribute_value_no_valid_values_skips(
    hass: HomeAssistant,
) -> None:
    """Test that attributes without known valid values are skipped.

    brightness has no valid value list → should not produce
    INVALID_ATTRIBUTE_VALUE (avoid false positives).
    """
    hass.states.async_set(
        "light.bedroom",
        "on",
        {"brightness": 128},
    )
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.bedroom",
        expected_state="50",
        expected_attribute="brightness",
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    attr_issues = [i for i in issues if i.issue_type == IssueType.INVALID_ATTRIBUTE_VALUE]
    assert len(attr_issues) == 0


async def test_transition_from_attribute_value(
    hass: HomeAssistant,
) -> None:
    """Test that transition_from with attribute is validated.

    from: turbo with attribute: fan_mode → turbo not in fan_modes → invalid.
    """
    hass.states.async_set(
        "climate.living_room",
        "cool",
        {"fan_mode": "low", "fan_modes": ["low", "medium", "high", "auto"]},
    )
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state="low",
        expected_attribute="fan_mode",
        location="trigger[0].to",
        transition_from="turbo",
    )

    issues = engine.validate_reference(ref)
    attr_issues = [i for i in issues if i.issue_type == IssueType.INVALID_ATTRIBUTE_VALUE]
    assert len(attr_issues) == 1
    assert "turbo" in attr_issues[0].message
async def test_attribute_value_template_skipped(
    hass: HomeAssistant,
) -> None:
    """Test that template values in attribute checks are skipped.

    '{{ template }}' can't be validated statically → must skip.
    """
    hass.states.async_set(
        "climate.living_room",
        "cool",
        {"fan_mode": "auto", "fan_modes": ["low", "medium", "high", "auto"]},
    )
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="climate.living_room",
        expected_state="{{ states('input_select.fan_mode') }}",
        expected_attribute="fan_mode",
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    attr_issues = [i for i in issues if i.issue_type == IssueType.INVALID_ATTRIBUTE_VALUE]
    assert len(attr_issues) == 0


# ============================================================================
# Part 4: Confidence-aware state validation severity
# ============================================================================


async def test_invalid_state_error_with_confirmed_states(
    hass: HomeAssistant,
) -> None:
    """Test that INVALID_STATE is ERROR when capabilities/history confirm valid states.

    When the knowledge base has confirmed states (via capabilities or history),
    we have high confidence in the valid states list, so INVALID_STATE is ERROR.
    """
    hass.states.async_set("vacuum.roborock_s7", "cleaning")
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    # Simulate confirmed states via history
    kb._observed_states["vacuum.roborock_s7"] = {"cleaning", "docked"}
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="vacuum.roborock_s7",
        expected_state="segment_cleaning",
        expected_attribute=None,
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    state_issues = [i for i in issues if i.issue_type == IssueType.INVALID_STATE]
    assert len(state_issues) == 1
    assert state_issues[0].severity == Severity.ERROR


async def test_invalid_state_warning_without_confirmed_states(
    hass: HomeAssistant,
) -> None:
    """Test that INVALID_STATE is WARNING when only device class defaults available.

    When the knowledge base has no confirmed states (no capabilities, no history),
    valid states come only from device_class_states.py defaults — low confidence.
    Custom integrations may report states not in defaults, so demote to WARNING.
    """
    hass.states.async_set("vacuum.roborock_s7", "cleaning")
    await hass.async_block_till_done()

    kb = StateKnowledgeBase(hass)
    # No observed history, no capabilities — only device class defaults
    engine = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="vacuum.roborock_s7",
        expected_state="segment_cleaning",
        expected_attribute=None,
        location="trigger[0].to",
    )

    issues = engine.validate_reference(ref)
    state_issues = [i for i in issues if i.issue_type == IssueType.INVALID_STATE]
    assert len(state_issues) == 1
    assert state_issues[0].severity == Severity.WARNING
