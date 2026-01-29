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


def test_unknown_filter_produces_warning():
    """A template using a filter that doesn't exist in HA should produce a warning."""
    validator = JinjaValidator()
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
    validator = JinjaValidator()
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


def test_ha_filters_are_accepted():
    """Common HA filters should not produce warnings."""
    validator = JinjaValidator()
    templates = [
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
        assert len(issues) == 0, f"Unexpected issue for template: {tmpl}: {issues}"


def test_ha_tests_are_accepted():
    """Common HA tests should not produce warnings."""
    validator = JinjaValidator()
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


def test_standard_jinja2_filters_are_accepted():
    """Standard Jinja2 built-in filters should not produce warnings."""
    validator = JinjaValidator()
    templates = [
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
            "id": "builtin_filter",
            "alias": "Builtin Filter",
            "triggers": [{"platform": "template", "value_template": tmpl}],
            "conditions": [],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert len(issues) == 0, f"Unexpected issue for template: {tmpl}: {issues}"


def test_multiple_unknown_filters_all_reported():
    """Multiple unknown filters in one template should each produce a warning."""
    validator = JinjaValidator()
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
    validator = JinjaValidator()
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
