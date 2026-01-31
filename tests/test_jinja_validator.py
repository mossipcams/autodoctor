"""Tests for JinjaValidator."""

import pytest
from unittest.mock import MagicMock
from custom_components.autodoctor.jinja_validator import JinjaValidator, _ISSUE_TYPE_REMAP
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import IssueType, Severity, StateReference, ValidationIssue
from custom_components.autodoctor.validator import ValidationEngine


def test_deeply_nested_conditions_do_not_stackoverflow():
    """Test that deeply nested conditions hit recursion limit gracefully."""
    validator = JinjaValidator()

    # Build deeply nested condition (25 levels deep)
    condition = {"condition": "state", "entity_id": "light.test", "state": "on"}
    for _ in range(25):
        condition = {"condition": "and", "conditions": [condition]}

    automation = {
        "id": "deep_nest",
        "alias": "Deeply Nested",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [condition],
        "actions": [],
    }

    # Should not raise RecursionError, should return (possibly with warning logged)
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)
    assert len(issues) == 0


@pytest.mark.parametrize("action_key", ["repeat", "parallel"])
def test_null_action_config_does_not_crash(action_key):
    """Test that repeat: null and parallel: null don't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": f"null_{action_key}",
        "alias": f"Null {action_key.title()}",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{action_key: None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)
    assert len(issues) == 0


def test_break_continue_do_not_produce_false_positives():
    """Templates using {% break %} and {% continue %} are valid in HA."""
    validator = JinjaValidator()
    automation = {
        "id": "loop_control_test",
        "alias": "Loop Control Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "data": {
                    "message": """{% for item in items %}
{% if item == 'skip' %}{% continue %}{% endif %}
{% if item == 'stop' %}{% break %}{% endif %}
{{ item }}
{% endfor %}"""
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    # Variable validation removed in v2.7.0 - no issues expected
    assert len(issues) == 0


def test_valid_template_produces_no_issues():
    """A valid HA template should produce no issues."""
    validator = JinjaValidator()
    automation = {
        "id": "valid_template",
        "alias": "Valid Template",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float > 20 }}",
            }
        ],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{{ is_state('binary_sensor.motion', 'on') and now().hour > 6 }}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_invalid_template_produces_syntax_error():
    """A template with bad syntax should produce an error."""
    validator = JinjaValidator()
    automation = {
        "id": "bad_syntax",
        "alias": "Bad Syntax",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float > }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR
    assert issues[0].severity == Severity.ERROR


def test_unknown_filter_produces_warning():
    """A template using a filter that doesn't exist in HA should produce a warning."""
    validator = JinjaValidator(strict_template_validation=True)
    automation = {
        "id": "bad_filter",
        "alias": "Bad Filter",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | as_timestmp }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_UNKNOWN_FILTER
    assert issues[0].severity == Severity.WARNING
    assert "as_timestmp" in issues[0].message


def test_unknown_test_produces_warning():
    """A template using a test that doesn't exist in HA should produce a warning."""
    validator = JinjaValidator(strict_template_validation=True)
    automation = {
        "id": "bad_test",
        "alias": "Bad Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{% if states('sensor.temp') is mach('\\\\d+') %}true{% endif %}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_UNKNOWN_TEST
    assert issues[0].severity == Severity.WARNING
    assert "mach" in issues[0].message


def test_known_filters_are_accepted():
    """HA and standard Jinja2 filters should not produce warnings."""
    validator = JinjaValidator(strict_template_validation=True)
    templates = [
        # HA filters
        "{{ states('sensor.temp') | float }}",
        "{{ states('sensor.temp') | as_timestamp }}",
        "{{ states('sensor.temp') | from_json }}",
        "{{ states('sensor.temp') | to_json }}",
        "{{ states('sensor.temp') | regex_match('\\\\d+') }}",
        "{{ states('sensor.temp') | slugify }}",
        "{{ states('sensor.temp') | base64_encode }}",
        "{{ states('sensor.temp') | md5 }}",
        "{{ states('sensor.temp') | iif('yes', 'no') }}",
        "{{ states('sensor.temp') | as_datetime }}",
        "{{ states('sensor.temp') | multiply(2) }}",
        "{{ [1, 2, 3] | average }}",
        "{{ [1, 2, 3] | median }}",
        # Standard Jinja2 filters
        "{{ items | join(', ') }}",
        "{{ name | upper }}",
        "{{ name | lower }}",
        "{{ items | first }}",
        "{{ items | last }}",
        "{{ items | length }}",
        "{{ items | sort }}",
        "{{ items | unique | list }}",
        "{{ name | replace('a', 'b') }}",
        "{{ name | trim }}",
        "{{ items | map(attribute='state') | list }}",
        "{{ items | selectattr('state', 'eq', 'on') | list }}",
        "{{ items | rejectattr('state', 'eq', 'off') | list }}",
        "{{ value | default('N/A') }}",
        "{{ items | batch(3) | list }}",
        "{{ text | truncate(20) }}",
    ]
    for tmpl in templates:
        automation = {
            "id": "filter_test",
            "alias": "Filter Test",
            "triggers": [{"platform": "template", "value_template": tmpl}],
            "conditions": [],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert all(i.issue_type != IssueType.TEMPLATE_UNKNOWN_FILTER for i in issues), \
            f"Unexpected filter issue for template: {tmpl}: {issues}"


def test_ha_tests_are_accepted():
    """Common HA tests should not produce warnings."""
    validator = JinjaValidator(strict_template_validation=True)
    templates = [
        "{% if states('sensor.temp') is match('\\\\d+') %}t{% endif %}",
        "{% if states('sensor.temp') is search('\\\\d+') %}t{% endif %}",
        "{% if states('sensor.temp') is is_number %}t{% endif %}",
        "{% if states('sensor.temp') is has_value %}t{% endif %}",
        "{% if states('sensor.temp') is contains('x') %}t{% endif %}",
        "{% if states('sensor.temp') is is_list %}t{% endif %}",
    ]
    for tmpl in templates:
        automation = {
            "id": "test_test",
            "alias": "Test Test",
            "triggers": [{"platform": "time", "at": "12:00:00"}],
            "conditions": [{"condition": "template", "value_template": tmpl}],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert len(issues) == 0, f"Unexpected issue for template: {tmpl}: {issues}"


def test_multiple_unknown_filters_all_reported():
    """Multiple unknown filters in one template should each produce a warning."""
    validator = JinjaValidator(strict_template_validation=True)
    automation = {
        "id": "multi_bad_filter",
        "alias": "Multi Bad Filter",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | florb | blargh }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 2
    names = {i.message for i in issues}
    assert any("florb" in m for m in names)
    assert any("blargh" in m for m in names)


def test_syntax_error_skips_semantic_check():
    """When there's a syntax error, semantic checks should not run."""
    validator = JinjaValidator(strict_template_validation=True)
    automation = {
        "id": "syntax_then_semantic",
        "alias": "Syntax Then Semantic",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


@pytest.mark.parametrize("template,expected_ids,expected_location_suffix", [
    ("{{ is_state('light.kitchen', 'on') }}", ["light.kitchen"], "is_state"),
    ("{{ state_attr('climate.living_room', 'temperature') }}", ["climate.living_room"], "state_attr"),
    ("{{ states.light.bedroom.state }}", ["light.bedroom"], "states_object"),
    (
        "{{ is_state('light.kitchen', 'on') and states.sensor.temp.state | float > 20 }}",
        ["light.kitchen", "sensor.temp"],
        None,
    ),
])
def test_extract_entity_references(template, expected_ids, expected_location_suffix):
    """Test extracting entity references from various patterns."""
    validator = JinjaValidator()
    refs = validator._extract_entity_references(
        template,
        "test_location",
        "automation.test",
        "Test Automation"
    )

    assert len(refs) == len(expected_ids)
    entity_ids = [r.entity_id for r in refs]
    for eid in expected_ids:
        assert eid in entity_ids
    if expected_location_suffix is not None:
        assert refs[0].location == f"test_location.{expected_location_suffix}"


def test_validate_entity_not_found(hass):
    """Test entity existence validation delegates to ValidationEngine."""
    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    # Create a reference to non-existent entity
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            expected_state=None,
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND
    assert "light.nonexistent" in issues[0].message


def test_validate_attribute_not_found(hass):
    """Test attribute existence validation delegates and remaps issue type."""
    # Setup entity in hass
    hass.states.async_set("climate.living_room", "heat", {"temperature": 20})

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="climate.living_room",
            expected_state=None,
            expected_attribute="nonexistent_attr",
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND
    assert "nonexistent_attr" in issues[0].message


def test_validate_invalid_state(hass):
    """Test state value validation delegates and remaps issue type."""
    # Setup entity in hass - use binary_sensor which is in STATE_VALIDATION_WHITELIST
    hass.states.async_set("binary_sensor.motion", "off")

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="binary_sensor.motion",
            expected_state="invalid_state",
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    # Should find invalid state issue
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_INVALID_STATE for i in issues)


def test_validate_entity_exists_no_issues(hass):
    """Test validation passes for existing entity."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "on")

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.kitchen",
            expected_state=None,
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 0


def test_template_validation_end_to_end(hass):
    """Test complete template validation with entity and state checks."""
    # Setup entity in hass - use binary_sensor which is in STATE_VALIDATION_WHITELIST
    hass.states.async_set("binary_sensor.motion", "off")

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    automation = {
        "id": "test_e2e",
        "alias": "Test End to End",
        "condition": {
            "condition": "template",
            "value_template": "{{ is_state('binary_sensor.nonexistent', 'on') and is_state('binary_sensor.motion', 'invalid_state') }}"
        }
    }

    issues = validator.validate_automations([automation])

    # Should find both entity not found and invalid state
    assert len(issues) >= 2
    issue_types = {i.issue_type for i in issues}
    assert IssueType.TEMPLATE_ENTITY_NOT_FOUND in issue_types
    assert IssueType.TEMPLATE_INVALID_STATE in issue_types


def test_template_validation_passes_for_valid_template(hass):
    """Test template validation passes for valid template."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "on")

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    automation = {
        "id": "test_valid",
        "alias": "Test Valid",
        "condition": {
            "condition": "template",
            "value_template": "{{ is_state('light.kitchen', 'on') }}"
        }
    }

    issues = validator.validate_automations([automation])

    # Should have no issues
    assert len(issues) == 0


@pytest.mark.parametrize("template,location", [
    ("{{ states('sensor.temp') | custom_filter }}", "triggers"),
    ("{% if states('sensor.temp') is custom_test %}true{% endif %}", "conditions"),
])
def test_unknown_filter_or_test_not_flagged_without_strict_mode(template, location):
    """Without strict mode, unknown filters and tests should not produce warnings."""
    validator = JinjaValidator()
    automation = {
        "id": "non_strict",
        "alias": "Non Strict",
        "triggers": [{"platform": "template", "value_template": template}] if location == "triggers" else [{"platform": "time", "at": "12:00:00"}],
        "conditions": [{"condition": "template", "value_template": template}] if location == "conditions" else [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


# --- Delegation tests (Task 1: H5/C2) ---


def test_delegation_calls_validation_engine():
    """Verify _validate_entity_references delegates to validation_engine.validate_all."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.kitchen",
            location="trigger[0].value_template.is_state",
            message="Entity 'light.kitchen' does not exist",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.kitchen",
            expected_state="on",
            expected_attribute=None,
            location="trigger[0].value_template.is_state",
        )
    ]

    issues = validator._validate_entity_references(refs)

    mock_engine.validate_all.assert_called_once_with(refs)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == "light.kitchen"


def test_delegation_remaps_entity_not_found():
    """Verify ENTITY_NOT_FOUND is remapped to TEMPLATE_ENTITY_NOT_FOUND."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            location="trigger[0].value_template.is_state",
            message="Entity 'light.nonexistent' does not exist",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            expected_state=None,
            expected_attribute=None,
            location="trigger[0].value_template.is_state",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == "light.nonexistent"


def test_delegation_remaps_entity_removed():
    """Verify ENTITY_REMOVED is remapped to TEMPLATE_ENTITY_NOT_FOUND."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.ENTITY_REMOVED,
            severity=Severity.INFO,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.old",
            location="action[0].data.entity_id",
            message="Entity 'light.old' existed in history but is now missing",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.old",
            expected_state=None,
            expected_attribute=None,
            location="action[0].data.entity_id",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND
    assert issues[0].severity == Severity.INFO
    assert issues[0].entity_id == "light.old"


def test_delegation_remaps_invalid_state():
    """Verify INVALID_STATE is remapped to TEMPLATE_INVALID_STATE."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.INVALID_STATE,
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="binary_sensor.motion",
            location="trigger[0].value_template.is_state",
            message="State 'bogus' is not valid for binary_sensor.motion",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="binary_sensor.motion",
            expected_state="bogus",
            expected_attribute=None,
            location="trigger[0].value_template.is_state",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_STATE
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == "binary_sensor.motion"


def test_delegation_remaps_attribute_not_found():
    """Verify ATTRIBUTE_NOT_FOUND is remapped to TEMPLATE_ATTRIBUTE_NOT_FOUND."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.ATTRIBUTE_NOT_FOUND,
            severity=Severity.WARNING,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="climate.living_room",
            location="condition[0].value_template.state_attr",
            message="Attribute 'nonexistent' does not exist on climate.living_room",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="climate.living_room",
            expected_state=None,
            expected_attribute="nonexistent",
            location="condition[0].value_template.state_attr",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND
    assert issues[0].severity == Severity.WARNING
    assert issues[0].entity_id == "climate.living_room"


def test_delegation_preserves_case_mismatch():
    """Verify CASE_MISMATCH is NOT remapped (same type in both families)."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.CASE_MISMATCH,
            severity=Severity.WARNING,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="binary_sensor.motion",
            location="trigger[0].value_template.is_state",
            message="State 'On' has incorrect case, should be 'on'",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="binary_sensor.motion",
            expected_state="On",
            expected_attribute=None,
            location="trigger[0].value_template.is_state",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.CASE_MISMATCH
    assert issues[0].severity == Severity.WARNING
    assert issues[0].entity_id == "binary_sensor.motion"


def test_delegation_preserves_location():
    """Verify template-specific location strings are preserved through delegation."""
    mock_engine = MagicMock(spec=ValidationEngine)
    mock_engine.validate_all.return_value = [
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            location="trigger[0].value_template.is_state",
            message="Entity 'light.nonexistent' does not exist",
        )
    ]

    validator = JinjaValidator(validation_engine=mock_engine)
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            expected_state=None,
            expected_attribute=None,
            location="trigger[0].value_template.is_state",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert issues[0].location == "trigger[0].value_template.is_state"
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == "light.nonexistent"


def test_no_validation_engine_returns_empty():
    """Without validation_engine, _validate_entity_references returns empty list."""
    validator = JinjaValidator()

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            expected_state=None,
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)
    assert issues == []


def test_issue_type_remap_dict_completeness():
    """Verify _ISSUE_TYPE_REMAP covers all expected source types."""
    assert IssueType.ENTITY_NOT_FOUND in _ISSUE_TYPE_REMAP
    assert IssueType.ENTITY_REMOVED in _ISSUE_TYPE_REMAP
    assert IssueType.INVALID_STATE in _ISSUE_TYPE_REMAP
    assert IssueType.ATTRIBUTE_NOT_FOUND in _ISSUE_TYPE_REMAP
    # CASE_MISMATCH intentionally not in remap
    assert IssueType.CASE_MISMATCH not in _ISSUE_TYPE_REMAP


# --- Trigger to/from field validation tests (Task 2: H2) ---


def test_trigger_to_with_jinja_is_validated():
    """Template trigger with Jinja expression in 'to' field should be validated."""
    validator = JinjaValidator()
    automation = {
        "id": "trigger_to_jinja",
        "alias": "Trigger To Jinja",
        "triggers": [
            {
                "platform": "template",
                "to": "{{ states('sensor.temp') > 25 }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    # Valid Jinja, no syntax errors expected
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_trigger_to_with_bad_jinja_produces_syntax_error():
    """Template trigger with bad Jinja in 'to' should produce syntax error."""
    validator = JinjaValidator()
    automation = {
        "id": "trigger_to_bad_jinja",
        "alias": "Trigger To Bad Jinja",
        "triggers": [
            {
                "platform": "template",
                "to": "{{ states('sensor.temp') > }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR
    assert "trigger[0].to" in issues[0].location


def test_trigger_from_with_jinja_entity_is_validated(hass):
    """Template trigger with Jinja in 'from' field extracts and validates entities."""
    hass.states.async_set("light.kitchen", "on")

    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    automation = {
        "id": "trigger_from_jinja",
        "alias": "Trigger From Jinja",
        "triggers": [
            {
                "platform": "template",
                "from": "{{ is_state('light.kitchen', 'on') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    # Entity exists, no issues expected
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_trigger_to_plain_string_not_treated_as_template():
    """Plain string 'to' field (no Jinja syntax) should NOT be treated as template."""
    validator = JinjaValidator()
    automation = {
        "id": "trigger_to_plain",
        "alias": "Trigger To Plain",
        "triggers": [
            {
                "platform": "state",
                "entity_id": "light.kitchen",
                "to": "on",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_trigger_from_plain_string_not_treated_as_template():
    """Plain string 'from' field (no Jinja syntax) should NOT be treated as template."""
    validator = JinjaValidator()
    automation = {
        "id": "trigger_from_plain",
        "alias": "Trigger From Plain",
        "triggers": [
            {
                "platform": "state",
                "entity_id": "light.kitchen",
                "from": "off",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_trigger_to_and_from_both_validated():
    """Both to and from fields with Jinja should be validated."""
    validator = JinjaValidator()
    automation = {
        "id": "trigger_both",
        "alias": "Trigger Both",
        "triggers": [
            {
                "platform": "template",
                "to": "{{ broken > }}",
                "from": "{{ also broken > }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    # Both to and from have syntax errors
    assert len(issues) == 2
    locations = {i.location for i in issues}
    assert "trigger[0].to" in locations
    assert "trigger[0].from" in locations
    assert all(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_trigger_from_with_nonexistent_entity(hass):
    """Jinja 'from' field referencing a nonexistent entity produces issue."""
    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)
    validator = JinjaValidator(hass, validation_engine=engine)

    automation = {
        "id": "trigger_from_missing",
        "alias": "Trigger From Missing Entity",
        "triggers": [
            {
                "platform": "template",
                "from": "{{ is_state('light.nonexistent', 'on') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND for i in issues)
    # Verify location includes the from field
    entity_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND]
    assert any("trigger[0].from" in i.location for i in entity_issues)


# --- Exception classification tests (Task 1: C3) ---


def test_jinja_syntax_error_produces_template_syntax_error():
    """A jinja2.TemplateSyntaxError should produce TEMPLATE_SYNTAX_ERROR."""
    validator = JinjaValidator()
    # {% if %} is invalid Jinja syntax (missing expression after 'if')
    issues = validator._check_template(
        "{% if %}", "test_location", "automation.test", "Test"
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_non_syntax_exception_does_not_produce_template_syntax_error():
    """A non-TemplateSyntaxError exception in _check_template should NOT produce TEMPLATE_SYNTAX_ERROR."""
    validator = JinjaValidator()

    # Monkey-patch the environment's parse method to raise a non-syntax exception
    original_parse = validator._env.parse

    def raise_key_error(source, *args, **kwargs):
        raise KeyError("simulated registry lookup failure")

    validator._env.parse = raise_key_error

    issues = validator._check_template(
        "{{ states('sensor.temp') }}", "test_location", "automation.test", "Test"
    )

    # Should NOT produce any issues (exception is logged and skipped)
    assert len(issues) == 0

    # Restore original parse
    validator._env.parse = original_parse


# --- _check_special_reference mutation hardening (JV-01, JV-02) ---


def test_check_special_reference_zone_found(hass):
    """Zone entity exists -- no issue returned.

    Kills: Eq->IsNot/Gt/LtE on reference_type == 'zone',
           AddNot on 'if not exists'.
    """
    hass.states.async_set("zone.home", "zoning", {"latitude": 51.5, "longitude": -0.1})

    validator = JinjaValidator(hass)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="zone.home",
        expected_state=None,
        expected_attribute=None,
        location="test_location",
        reference_type="zone",
    )
    issue = validator._check_special_reference(ref)
    assert issue is None


def test_check_special_reference_zone_not_found(hass):
    """Zone entity does NOT exist -- issue returned.

    Kills: AddNot on 'if not exists' (found case returns None, not-found returns issue).
    """
    validator = JinjaValidator(hass)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="zone.nonexistent",
        expected_state=None,
        expected_attribute=None,
        location="test_location",
        reference_type="zone",
    )
    issue = validator._check_special_reference(ref)
    assert issue is not None
    assert issue.issue_type == IssueType.TEMPLATE_ZONE_NOT_FOUND
    assert issue.severity == Severity.ERROR
    assert "zone.nonexistent" in issue.message


def test_check_special_reference_device_found(hass, device_registry):
    """Device exists in device registry -- no issue returned.

    Kills: Eq->IsNot/Gt/LtE on reference_type == 'device'.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    config_entry = MockConfigEntry(domain="test", data={})
    config_entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("test", "device1")},
    )

    validator = JinjaValidator(hass)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id=device.id,
        expected_state=None,
        expected_attribute=None,
        location="test_location",
        reference_type="device",
    )
    issue = validator._check_special_reference(ref)
    assert issue is None


def test_check_special_reference_device_not_found(hass):
    """Device does NOT exist -- issue returned.

    Kills: AddNot on 'if not exists' for device path.
    """
    validator = JinjaValidator(hass)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="nonexistent_device_id",
        expected_state=None,
        expected_attribute=None,
        location="test_location",
        reference_type="device",
    )
    issue = validator._check_special_reference(ref)
    assert issue is not None
    assert issue.issue_type == IssueType.TEMPLATE_DEVICE_NOT_FOUND
    assert issue.severity == Severity.ERROR
    assert "nonexistent_device_id" in issue.message


def test_check_special_reference_area_found(hass, area_registry):
    """Area exists in area registry -- no issue returned.

    Kills: Eq->IsNot/Gt/LtE on reference_type == 'area'.
    """
    area = area_registry.async_create("Living Room")

    validator = JinjaValidator(hass)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id=area.id,
        expected_state=None,
        expected_attribute=None,
        location="test_location",
        reference_type="area",
    )
    issue = validator._check_special_reference(ref)
    assert issue is None


def test_check_special_reference_area_not_found(hass):
    """Area does NOT exist -- issue returned.

    Kills: AddNot on 'if not exists' for area path.
    """
    validator = JinjaValidator(hass)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="nonexistent_area",
        expected_state=None,
        expected_attribute=None,
        location="test_location",
        reference_type="area",
    )
    issue = validator._check_special_reference(ref)
    assert issue is not None
    assert issue.issue_type == IssueType.TEMPLATE_AREA_NOT_FOUND
    assert issue.severity == Severity.ERROR
    assert "nonexistent_area" in issue.message


# --- _validate_filter_args boundary tests (JV-03, JV-04) ---


def test_filter_args_under_minimum_produces_error():
    """0 args when min=1 -- should produce TEMPLATE_INVALID_ARGUMENTS.

    Kills: Lt->Eq (0 < 1 is True; 0 == 1 is False -- mutation misses error),
           Lt->Gt (0 > 1 is False -- mutation misses error),
           Lt->IsNot (different semantics).
    """
    validator = JinjaValidator(strict_template_validation=True)
    # multiply has min_args=1, max_args=2. Provide 0 args.
    automation = {
        "id": "test",
        "alias": "Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | multiply }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    arg_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS]
    assert len(arg_issues) == 1
    assert "multiply" in arg_issues[0].message


def test_filter_args_at_minimum_no_error():
    """Exactly min_args should NOT produce an error -- distinguishes < from <=.

    Kills: Lt->LtE mutation (1 <= 1 would incorrectly flag valid input).
    """
    validator = JinjaValidator(strict_template_validation=True)
    # multiply has min_args=1. Provide exactly 1 arg.
    automation = {
        "id": "test",
        "alias": "Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | multiply(2) }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    arg_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS]
    assert len(arg_issues) == 0


def test_filter_args_over_maximum_produces_error():
    """More args than max_args -- should produce TEMPLATE_INVALID_ARGUMENTS.

    Kills: Gt->Lt (4 < 3 is False -- mutation misses error),
           Gt->Eq (4 == 3 is False -- mutation misses error).
    """
    validator = JinjaValidator(strict_template_validation=True)
    # clamp has min_args=2, max_args=3. Provide 4 args.
    automation = {
        "id": "test",
        "alias": "Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float | clamp(0, 100, 50, 'extra') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    arg_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS]
    assert len(arg_issues) == 1
    assert "clamp" in arg_issues[0].message


def test_filter_args_at_maximum_no_error():
    """Exactly max_args should NOT produce an error -- distinguishes > from >=.

    Kills: Gt->GtE mutation (3 >= 3 would incorrectly flag valid input).
    """
    validator = JinjaValidator(strict_template_validation=True)
    # clamp has min_args=2, max_args=3. Provide exactly 3 args.
    automation = {
        "id": "test",
        "alias": "Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float | clamp(0, 100, 50) }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    arg_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS]
    assert len(arg_issues) == 0


def test_filter_args_exact_count_branch_under():
    """Filter with min_args == max_args == 1, given 0 args.

    Kills: Eq mutations on min_args == max_args (line 681). When min==max,
    the message uses str(min_args) (exact count) not a range like "1-2".
    """
    validator = JinjaValidator(strict_template_validation=True)
    # atan2 has min_args=1, max_args=1 (exact count).
    automation = {
        "id": "test",
        "alias": "Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float | atan2 }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    arg_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS]
    assert len(arg_issues) == 1
    assert "atan2" in arg_issues[0].message
    # Exact count: message says "expects 1 arguments" (not "1-2")
    assert "1" in arg_issues[0].message


def test_filter_args_exact_count_branch_over():
    """Filter with min_args == max_args == 0, given 1 arg.

    Kills: Eq mutations on min_args == max_args (line 681). Tests the over-max
    direction for a filter where the exact count is 0.
    """
    validator = JinjaValidator(strict_template_validation=True)
    # as_datetime has min_args=0, max_args=0 (exact count: 0 args expected).
    automation = {
        "id": "test",
        "alias": "Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | as_datetime('extra') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    arg_issues = [i for i in issues if i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS]
    assert len(arg_issues) == 1
    assert "as_datetime" in arg_issues[0].message
    # Exact count: message says "expects 0 arguments"
    assert "0" in arg_issues[0].message


# --- ZeroIterationForLoop mutation hardening (JV-05) ---


def test_choose_conditions_loop_finds_template_error():
    """Choose option with bad template in condition.

    Kills: ZeroIterationForLoop on `for cond_idx, cond in enumerate(opt_conditions)` (line 313).
    If mutated to empty iterable, the condition's bad template is never checked.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_choose_cond",
        "alias": "ZIL Choose Cond",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [
                    {
                        "conditions": [
                            {"condition": "template", "value_template": "{{ broken > }}"}
                        ],
                        "sequence": [],
                    }
                ]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_choose_options_loop_finds_template_error():
    """Choose block with option whose sequence has bad template.

    Kills: ZeroIterationForLoop on `for opt_idx, option in enumerate(action.get("choose", []))` (line 307).
    If mutated to empty iterable, the entire option (including sequence) is never validated.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_choose_opt",
        "alias": "ZIL Choose Opt",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [
                    {
                        "conditions": [],
                        "sequence": [{"data": {"msg": "{{ broken > }}"}}],
                    }
                ]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_if_conditions_loop_finds_template_error():
    """If action with bad template in condition.

    Kills: ZeroIterationForLoop on `for cond_idx, cond in enumerate(if_conditions)` (line 351).
    If mutated to empty iterable, the if condition's bad template is never checked.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_if_cond",
        "alias": "ZIL If Cond",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "if": [{"condition": "template", "value_template": "{{ broken > }}"}],
                "then": [],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_repeat_while_conditions_loop_finds_template_error():
    """Repeat action with bad template in while condition.

    Kills: ZeroIterationForLoop on `for cond_idx, cond in enumerate(repeat_conditions)` (line 384)
    via the "while" key. If mutated to empty iterable, the while condition is never checked.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_repeat_while",
        "alias": "ZIL Repeat While",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "repeat": {
                    "while": [
                        {"condition": "template", "value_template": "{{ broken > }}"}
                    ],
                    "sequence": [],
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_repeat_until_conditions_loop_finds_template_error():
    """Repeat action with bad template in until condition.

    Kills: ZeroIterationForLoop on `for cond_idx, cond in enumerate(repeat_conditions)` (line 384)
    via the "until" key. If mutated to empty iterable, the until condition is never checked.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_repeat_until",
        "alias": "ZIL Repeat Until",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "repeat": {
                    "until": [
                        {"condition": "template", "value_template": "{{ broken > }}"}
                    ],
                    "sequence": [],
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_parallel_branches_loop_finds_template_error():
    """Parallel action with bad template in branch.

    Kills: ZeroIterationForLoop on `for branch_idx, branch in enumerate(branches)` (line 409).
    If mutated to empty iterable, the branch's bad template is never checked.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_parallel",
        "alias": "ZIL Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "parallel": [{"data": {"msg": "{{ broken > }}"}}]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_nested_conditions_loop_finds_template_error():
    """Top-level 'and' condition with nested bad template condition.

    Kills: ZeroIterationForLoop on `for nested_idx, nested_cond in enumerate(nested)` (line 232).
    If mutated to empty iterable, the nested condition's bad template is never checked.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_nested_cond",
        "alias": "ZIL Nested Cond",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "and",
                "conditions": [
                    {"condition": "template", "value_template": "{{ broken > }}"}
                ],
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


# --- Depth arithmetic mutation hardening (JV-06) ---


def test_choose_nested_two_levels_finds_deep_error():
    """Choose inside choose with bad template at depth 2.

    Kills: _depth + 1 arithmetic mutations at choose sequence recursion (line 333).
    Proves recursion physically reaches depth 2.
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_choose",
        "alias": "Depth 2 Choose",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [
                    {
                        "conditions": [],
                        "sequence": [
                            {
                                "choose": [
                                    {
                                        "conditions": [],
                                        "sequence": [
                                            {"data": {"msg": "{{ broken > }}"}}
                                        ],
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_if_then_nested_two_levels_finds_deep_error():
    """If/then inside if/then with bad template at depth 2.

    Kills: _depth + 1 arithmetic mutations at if/then recursion (line 362).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_if",
        "alias": "Depth 2 If",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "if": [],
                "then": [
                    {
                        "if": [],
                        "then": [{"data": {"msg": "{{ broken > }}"}}],
                    }
                ],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_repeat_nested_two_levels_finds_deep_error():
    """Repeat inside repeat with bad template at depth 2.

    Kills: _depth + 1 arithmetic mutations at repeat sequence recursion (line 401).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_repeat",
        "alias": "Depth 2 Repeat",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "repeat": {
                    "while": [],
                    "sequence": [
                        {
                            "repeat": {
                                "while": [],
                                "sequence": [
                                    {"data": {"msg": "{{ broken > }}"}}
                                ],
                            }
                        }
                    ],
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_parallel_nested_two_levels_finds_deep_error():
    """Parallel inside parallel with bad template at depth 2.

    Kills: _depth + 1 arithmetic mutations at parallel recursion (line 417).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_parallel",
        "alias": "Depth 2 Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "parallel": [
                    {
                        "parallel": [
                            {"data": {"msg": "{{ broken > }}"}}
                        ]
                    }
                ]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_nesting_at_depth_limit_stops_validation():
    """Nesting 22 levels deep should hit depth limit and stop.

    Template error at bottom should NOT be found.
    Kills: _depth + 1 -> _depth - 1 (depth never reaches 20, so no stop)
           _depth + 1 -> _depth * 1 (depth stays 0, so no stop)
           _depth + 1 -> _depth + 0 (depth stays 0, so no stop)
    """
    validator = JinjaValidator()

    # Build 22-level nested choose
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(22):
        inner = [{"choose": [{"conditions": [], "sequence": inner}]}]

    automation = {
        "id": "depth_limit",
        "alias": "Depth Limit",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": inner,
    }
    issues = validator.validate_automations([automation])
    # Depth limit reached -- template error at bottom should NOT be found
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_nesting_just_under_depth_limit_finds_error():
    """Nesting 19 levels deep should be under limit and find the error.

    Paired with test_nesting_at_depth_limit_stops_validation to kill
    depth arithmetic mutations: if depth never increments, both tests
    can't pass simultaneously.
    """
    validator = JinjaValidator()

    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(19):
        inner = [{"choose": [{"conditions": [], "sequence": inner}]}]

    automation = {
        "id": "under_limit",
        "alias": "Under Limit",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": inner,
    }
    issues = validator.validate_automations([automation])
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_choose_default_nested_finds_deep_error():
    """Choose with default containing nested choose with bad template at depth 2.

    Kills: _depth + 1 arithmetic mutations at choose default recursion (line 343).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_default",
        "alias": "Depth 2 Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [],
                "default": [
                    {
                        "choose": [
                            {
                                "conditions": [],
                                "sequence": [
                                    {"data": {"msg": "{{ broken > }}"}}
                                ],
                            }
                        ]
                    }
                ],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_if_else_nested_finds_deep_error():
    """If/else with nested if/then containing bad template at depth 2.

    Kills: _depth + 1 arithmetic mutations at if/else recursion (line 371).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_else",
        "alias": "Depth 2 Else",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "if": [],
                "else": [
                    {
                        "if": [],
                        "then": [{"data": {"msg": "{{ broken > }}"}}],
                    }
                ],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


# --- Template detection, dedup, and guard mutation hardening (JV-07, JV-08, JV-09) ---


def test_non_string_data_value_not_treated_as_template():
    """Non-string value in action data is NOT treated as a template.

    Kills: and->or swap on `isinstance(value, str) and self._is_template(value)` (line 436).
    If `and` becomes `or`, `isinstance(42, str)` is False but `or` would try
    `self._is_template(42)` which expects a string -- causing a crash or incorrect behavior.
    """
    validator = JinjaValidator()
    automation = {
        "id": "non_string_data",
        "alias": "Non String Data",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{"data": {"count": 42, "flag": True, "nothing": None}}],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_template_string_in_data_is_validated():
    """Template string in action data IS validated for syntax errors.

    Positive counterpart to test_non_string_data_value_not_treated_as_template.
    Confirms the isinstance(str) + _is_template path works for real templates.
    """
    validator = JinjaValidator()
    automation = {
        "id": "template_data",
        "alias": "Template Data",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{"data": {"msg": "{{ broken > }}"}}],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_data_list_with_non_string_items_not_validated():
    """Non-string items in a data list are skipped; only template strings are validated.

    Kills: and->or swap on `isinstance(item, str) and self._is_template(item)` (line 450).
    If `and` becomes `or`, non-string items (42, True, None) would be passed to
    `_is_template` or `_check_template`, potentially crashing. Only the template
    string should produce an issue.
    """
    validator = JinjaValidator()
    automation = {
        "id": "list_mixed",
        "alias": "List Mixed",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{"data": {"targets": [42, True, None, "{{ broken > }}"]}}],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_entity_dedup_prevents_duplicate_refs():
    """Same entity via two dedup=True patterns produces exactly 1 ref.

    Kills: AddNot on `any(r.entity_id == entity_id for r in refs)` (line 519),
           Eq->NotEq on entity_id comparison inside any().
    If dedup logic is negated or inverted, duplicate refs would appear.
    """
    validator = JinjaValidator()
    refs = validator._extract_entity_references(
        "{{ states.sensor.temp.state }} and {{ states('sensor.temp') }}",
        "test_loc", "automation.test", "Test"
    )
    entity_ids = [r.entity_id for r in refs]
    assert entity_ids.count("sensor.temp") == 1


def test_entity_dedup_continue_not_break():
    """Dedup uses continue (not break) so later entities are still found.

    Kills: continue->break swap on dedup path (line 520).
    Template has a dedup pair (sensor.temp via two patterns) followed by a
    different entity (light.kitchen). If continue becomes break, the loop
    exits early and light.kitchen is never found.
    """
    validator = JinjaValidator()
    refs = validator._extract_entity_references(
        "{{ states.sensor.temp.state }} and {{ states('sensor.temp') }} and {{ states('light.kitchen') }}",
        "test_loc", "automation.test", "Test"
    )
    entity_ids = [r.entity_id for r in refs]
    assert entity_ids.count("sensor.temp") == 1
    assert "light.kitchen" in entity_ids
    assert len(refs) == 2


def test_non_dict_action_skipped_dict_action_validated():
    """Non-dict action (string) is skipped; dict action with bad template is found.

    Kills: AddNot on `not isinstance(action, dict)` (line 274) causing dict
           actions to be skipped and string actions to be processed (crash).
           Also kills continue->break swap: if break is used at the string
           action, the dict action is never reached.
    """
    validator = JinjaValidator()
    automation = {
        "id": "guard_test",
        "alias": "Guard Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            "scene.activate_script",  # non-dict, should be skipped
            {"data": {"msg": "{{ broken > }}"}},  # dict, should be validated
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_all_dict_actions_with_errors_all_found():
    """Multiple dict actions with bad templates -- ALL errors are found.

    Positive counterpart proving every dict action in the list is processed,
    not just the first one.
    """
    validator = JinjaValidator()
    automation = {
        "id": "multi_dict",
        "alias": "Multi Dict",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {"data": {"msg": "{{ broken > }}"}},
            {"data": {"msg": "{{ also broken > }}"}},
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 2
    assert all(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


# --- Action key detection mutation hardening (JV-10) ---
# NOTE: "choose" in action (line 306) AddNot is already killed by
# test_choose_conditions_loop_finds_template_error (Plan 02 / JV-05).
# "repeat" in action (line 377) AddNot is already killed by
# test_repeat_while_conditions_loop_finds_template_error (Plan 02 / JV-05).
# Tests below target the REMAINING action key guards: default, else, if/then.


def test_choose_action_key_detected_and_validated():
    """Choose action with bad template in condition is found.

    Targets: `"choose" in action` guard (line 306) -- JV-10.
    NOTE: Also killed by test_choose_conditions_loop_finds_template_error (JV-05),
    but included here with distinct structure (bad template in option sequence
    data, not just conditions) for completeness.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_choose",
        "alias": "Key Choose",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{
            "choose": [{
                "conditions": [],
                "sequence": [{"data": {"msg": "{{ broken > }}"}}],
            }]
        }],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_repeat_action_key_detected_and_validated():
    """Repeat action with bad template in while condition is found.

    Targets: `"repeat" in action` guard (line 377) -- JV-10.
    NOTE: Also killed by test_repeat_while_conditions_loop_finds_template_error
    (JV-05), but included here for explicit JV-10 coverage with a distinct
    automation ID and docstring.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_repeat",
        "alias": "Key Repeat",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{
            "repeat": {
                "while": [{"condition": "template", "value_template": "{{ broken > }}"}],
                "sequence": [],
            }
        }],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_choose_default_key_detected_and_validated():
    """Choose action with non-empty default containing bad template is found.

    Targets: `if default:` guard (line 340) -- JV-10.
    If AddNot inverts to `if not default:`, a non-empty default block is NOT
    processed and the bad template inside is missed.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_default",
        "alias": "Key Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{
            "choose": [],
            "default": [{"data": {"msg": "{{ broken > }}"}}],
        }],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_choose_empty_default_no_crash():
    """Choose action with empty default produces no issues and does not crash.

    Negative counterpart: empty default (falsy) should NOT be processed.
    If `if default:` becomes `if not default:`, the empty list IS processed
    but since it's empty, no crash -- the real kill comes from
    test_choose_default_key_detected_and_validated above.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_empty_default",
        "alias": "Key Empty Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{
            "choose": [],
            "default": [],
        }],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_if_else_key_detected_and_validated():
    """If/else action with bad template in else block is found.

    Targets: `if else_actions:` guard (line 368) -- JV-10.
    If AddNot inverts to `if not else_actions:`, a non-empty else block is NOT
    processed and the bad template inside is missed.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_if_else",
        "alias": "Key If Else",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{
            "if": [],
            "else": [{"data": {"msg": "{{ broken > }}"}}],
        }],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)
