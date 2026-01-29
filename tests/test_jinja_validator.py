"""Tests for JinjaValidator."""

import pytest
from custom_components.autodoctor.jinja_validator import JinjaValidator
from custom_components.autodoctor.models import IssueType, Severity


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


def test_null_repeat_config_does_not_crash():
    """Test that repeat: null doesn't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": "null_repeat",
        "alias": "Null Repeat",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{"repeat": None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)


def test_null_parallel_config_does_not_crash():
    """Test that parallel: null doesn't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": "null_parallel",
        "alias": "Null Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{"parallel": None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)


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
