"""Tests for JinjaValidator.

Comprehensive test coverage for Jinja2 template validation including:
- Template syntax error detection
- Unknown filter and test detection
- Trigger field validation (to/from with Jinja)
- Action recursion (choose, if/then/else, repeat, parallel)
- Depth limit enforcement
- Guard tests for removed entity validation features
"""

from __future__ import annotations

import inspect

import pytest

from custom_components.autodoctor.jinja_validator import JinjaValidator
from custom_components.autodoctor.models import IssueType, Severity


def test_deeply_nested_conditions_do_not_stackoverflow() -> None:
    """Test that deeply nested conditions hit recursion limit gracefully.

    Ensures that extremely deep nesting (25 levels) doesn't cause a stack
    overflow, instead reaching the depth limit and returning gracefully.
    """
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


@pytest.mark.parametrize(
    "action_key",
    ["repeat", "parallel"],
    ids=["repeat-null", "parallel-null"],
)
def test_null_action_config_does_not_crash(action_key: str) -> None:
    """Test that null action values don't crash validation.

    Home Assistant automations may have repeat: null or parallel: null
    in certain edge cases. Validation should handle these gracefully.
    """
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


def test_break_continue_do_not_produce_false_positives() -> None:
    """Test that loop control statements are treated as valid.

    Home Assistant's Jinja2 environment supports {% break %} and {% continue %}
    within loops. These should not produce syntax errors or false positives.
    """
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


def test_valid_template_produces_no_issues() -> None:
    """Test that well-formed templates produce no validation issues.

    Valid templates using standard Home Assistant filters and functions
    should pass validation without errors or warnings.
    """
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


def test_invalid_template_produces_syntax_error() -> None:
    """Test that malformed templates produce TEMPLATE_SYNTAX_ERROR.

    Templates with invalid Jinja2 syntax (incomplete expressions, missing
    operators, etc.) should be detected and reported as errors.
    """
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


def test_unknown_filter_produces_warning() -> None:
    """Test that unknown filters produce TEMPLATE_UNKNOWN_FILTER warnings.

    When strict validation is enabled, filters not in the Home Assistant or
    standard Jinja2 filter registry should be flagged as warnings (not errors).
    """
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


def test_unknown_test_produces_warning() -> None:
    """Test that unknown Jinja2 tests produce TEMPLATE_UNKNOWN_TEST warnings.

    When strict validation is enabled, tests (e.g., 'is match()') not in the
    Home Assistant or standard Jinja2 test registry should be flagged as warnings.
    """
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


def test_known_filters_are_accepted() -> None:
    """Test that all known Home Assistant and Jinja2 filters are accepted.

    Validates a comprehensive list of filters including HA-specific filters
    (as_timestamp, iif, slugify, etc.) and standard Jinja2 filters (join,
    upper, selectattr, etc.). None should produce warnings.
    """
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
        assert all(i.issue_type != IssueType.TEMPLATE_UNKNOWN_FILTER for i in issues), (
            f"Unexpected filter issue for template: {tmpl}: {issues}"
        )


def test_ha_tests_are_accepted() -> None:
    """Test that all known Home Assistant Jinja2 tests are accepted.

    Validates HA-specific tests like 'is match()', 'is has_value',
    'is is_number', etc. None should produce warnings.
    """
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


def test_multiple_unknown_filters_all_reported() -> None:
    """Test that all unknown filters in a template are reported.

    When a template contains multiple unknown filters, each should be
    reported as a separate warning (not just the first one encountered).
    """
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


def test_syntax_error_skips_semantic_check() -> None:
    """Test that syntax errors prevent semantic validation.

    When a template has a syntax error, semantic checks (filter/test
    validation) should be skipped to avoid cascading errors.
    """
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


# --- Trigger to/from field validation tests ---


def test_trigger_to_with_jinja_is_validated() -> None:
    """Test that Jinja templates in trigger 'to' fields are validated.

    Template triggers can have Jinja expressions in the 'to' field.
    These should be parsed and validated for syntax errors.
    """
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


def test_trigger_to_with_bad_jinja_produces_syntax_error() -> None:
    """Test that malformed Jinja in trigger 'to' field produces syntax error.

    Invalid Jinja2 syntax in a trigger's 'to' field should be detected
    and reported with the correct location information.
    """
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


def test_trigger_to_plain_string_not_treated_as_template() -> None:
    """Test that plain strings in 'to' field are not treated as templates.

    State trigger 'to' fields without Jinja syntax (e.g., "on") should be
    treated as literal values, not validated as templates.
    """
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


def test_trigger_from_plain_string_not_treated_as_template() -> None:
    """Test that plain strings in 'from' field are not treated as templates.

    State trigger 'from' fields without Jinja syntax (e.g., "off") should be
    treated as literal values, not validated as templates.
    """
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


def test_trigger_to_and_from_both_validated() -> None:
    """Test that both 'to' and 'from' fields with Jinja are validated.

    When both fields contain Jinja templates with syntax errors, both
    should be reported with correct location information.
    """
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


# --- Exception classification tests ---


def test_jinja_syntax_error_produces_template_syntax_error() -> None:
    """Test that jinja2.TemplateSyntaxError produces TEMPLATE_SYNTAX_ERROR.

    Ensures that Jinja2's native TemplateSyntaxError exceptions are correctly
    classified as TEMPLATE_SYNTAX_ERROR issues.
    """
    validator = JinjaValidator()
    # {% if %} is invalid Jinja syntax (missing expression after 'if')
    issues = validator._check_template(
        "{% if %}", "test_location", "automation.test", "Test"
    )
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_non_syntax_exception_does_not_produce_template_syntax_error() -> None:
    """Test that non-syntax exceptions don't produce TEMPLATE_SYNTAX_ERROR.

    Exceptions other than TemplateSyntaxError (e.g., KeyError, ValueError)
    should be logged and skipped, not reported as syntax errors.
    """
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


# --- ZeroIterationForLoop mutation hardening ---


def test_choose_conditions_loop_finds_template_error() -> None:
    """Test that choose option conditions are validated.

    Mutation test: Ensures the conditions loop is not skipped. If the loop
    over opt_conditions is mutated to an empty iterable, the bad template
    in the condition would never be detected.
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
                            {
                                "condition": "template",
                                "value_template": "{{ broken > }}",
                            }
                        ],
                        "sequence": [],
                    }
                ]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_choose_options_loop_finds_template_error() -> None:
    """Test that choose options sequence is validated.

    Mutation test: Ensures the options loop is not skipped. If the loop
    over choose options is mutated to empty, the bad template in the
    option's sequence would never be detected.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_if_conditions_loop_finds_template_error() -> None:
    """Test that if action conditions are validated.

    Mutation test: Ensures the if conditions loop is not skipped. If the loop
    over if_conditions is mutated to empty, the bad template would not be found.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_repeat_while_conditions_loop_finds_template_error() -> None:
    """Test that repeat while conditions are validated.

    Mutation test: Ensures the repeat while conditions loop is not skipped.
    If mutated to empty, the bad template in the while condition is not found.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_repeat_until_conditions_loop_finds_template_error() -> None:
    """Test that repeat until conditions are validated.

    Mutation test: Ensures the repeat until conditions loop is not skipped.
    If mutated to empty, the bad template in the until condition is not found.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_parallel_branches_loop_finds_template_error() -> None:
    """Test that parallel branches are validated.

    Mutation test: Ensures the parallel branches loop is not skipped. If
    mutated to empty, the bad template in the branch is not detected.
    """
    validator = JinjaValidator()
    automation = {
        "id": "zil_parallel",
        "alias": "ZIL Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [{"parallel": [{"data": {"msg": "{{ broken > }}"}}]}],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_nested_conditions_loop_finds_template_error() -> None:
    """Test that nested conditions within 'and' blocks are validated.

    Mutation test: Ensures the nested conditions loop is not skipped. If
    mutated to empty, the bad template in nested conditions is not found.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


# --- Depth arithmetic mutation hardening ---


def test_choose_nested_two_levels_finds_deep_error() -> None:
    """Test that nested choose blocks at depth 2 are validated.

    Mutation test: Ensures depth tracking works correctly. If depth increment
    is mutated (e.g., _depth + 1 -> _depth), nested templates won't be found.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_if_then_nested_two_levels_finds_deep_error() -> None:
    """Test that nested if/then blocks at depth 2 are validated.

    Mutation test: Ensures depth tracking for if/then recursion is correct.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_repeat_nested_two_levels_finds_deep_error() -> None:
    """Test that nested repeat blocks at depth 2 are validated.

    Mutation test: Ensures depth tracking for repeat recursion is correct.
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
                                "sequence": [{"data": {"msg": "{{ broken > }}"}}],
                            }
                        }
                    ],
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_parallel_nested_two_levels_finds_deep_error() -> None:
    """Test that nested parallel blocks at depth 2 are validated.

    Mutation test: Ensures depth tracking for parallel recursion is correct.
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth2_parallel",
        "alias": "Depth 2 Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {"parallel": [{"parallel": [{"data": {"msg": "{{ broken > }}"}}]}]}
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_nesting_at_depth_limit_stops_validation() -> None:
    """Test that depth limit (20) stops validation at 22 levels deep.

    When nesting exceeds the depth limit, validation should stop to prevent
    stack overflow. The template error at the bottom should NOT be found.
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


def test_nesting_just_under_depth_limit_finds_error() -> None:
    """Test that nesting at 19 levels (under limit) finds template errors.

    Paired with test_nesting_at_depth_limit_stops_validation: this ensures
    depth tracking works correctly. At 19 levels, validation continues and
    the error IS found.
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
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_choose_default_nested_finds_deep_error() -> None:
    """Test that nested choose blocks in default path at depth 2 are validated.

    Mutation test: Ensures depth tracking for choose default recursion is correct.
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
                                "sequence": [{"data": {"msg": "{{ broken > }}"}}],
                            }
                        ]
                    }
                ],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_if_else_nested_finds_deep_error() -> None:
    """Test that nested if blocks in else path at depth 2 are validated.

    Mutation test: Ensures depth tracking for if/else recursion is correct.
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


# --- Template detection and guard mutation hardening ---


def test_non_string_data_value_not_treated_as_template() -> None:
    """Test that non-string values in action data are not treated as templates.

    Mutation test: Ensures isinstance check prevents non-strings from being
    passed to template validation. If and->or mutation occurs, this would crash.
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


def test_template_string_in_data_is_validated() -> None:
    """Test that template strings in action data are validated.

    Positive test: Confirms that string values containing templates are
    correctly identified and validated for syntax errors.
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


def test_data_list_with_non_string_items_not_validated() -> None:
    """Test that non-string items in data lists are skipped.

    Mutation test: Ensures isinstance check in list processing prevents
    non-strings from being validated. Mixed-type lists should only validate
    the template string items.
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


def test_non_dict_action_skipped_dict_action_validated() -> None:
    """Test that non-dict actions are skipped while dict actions are validated.

    Mutation test: Ensures the isinstance guard correctly skips non-dict
    actions. If inverted, dict actions would be skipped and strings processed.
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


def test_all_dict_actions_with_errors_all_found() -> None:
    """Test that all dict actions in a sequence are validated.

    Ensures the action loop processes all items, not just the first one.
    Multiple template errors should all be reported.
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


# --- Action key detection mutation hardening ---


def test_choose_action_key_detected_and_validated() -> None:
    """Test that choose action blocks are detected and validated.

    Mutation test: Ensures 'choose' key detection works. If the key check
    is mutated, choose blocks would not be validated.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_choose",
        "alias": "Key Choose",
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_repeat_action_key_detected_and_validated() -> None:
    """Test that repeat action blocks are detected and validated.

    Mutation test: Ensures 'repeat' key detection works. If the key check
    is mutated, repeat blocks would not be validated.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_repeat",
        "alias": "Key Repeat",
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
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_choose_default_key_detected_and_validated() -> None:
    """Test that choose default blocks are detected and validated.

    Mutation test: Ensures 'default' field detection works. If the truthy
    check is inverted, non-empty defaults would not be validated.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_default",
        "alias": "Key Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [],
                "default": [{"data": {"msg": "{{ broken > }}"}}],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def test_choose_empty_default_no_crash() -> None:
    """Test that empty default blocks are handled gracefully.

    Negative test: Empty defaults should not be processed. This ensures
    the falsy check works correctly without crashes.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_empty_default",
        "alias": "Key Empty Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [],
                "default": [],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_if_else_key_detected_and_validated() -> None:
    """Test that if/else blocks are detected and validated.

    Mutation test: Ensures 'else' field detection works. If the truthy
    check is inverted, non-empty else blocks would not be validated.
    """
    validator = JinjaValidator()
    automation = {
        "id": "key_if_else",
        "alias": "Key If Else",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "if": [],
                "else": [{"data": {"msg": "{{ broken > }}"}}],
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


# --- Entity validation removal guard tests ---


def test_no_validation_engine_parameter() -> None:
    """Guard: Prevent re-introduction of validation_engine parameter.

    v2.14.0 removed duplicate entity validation from JinjaValidator.
    Entity validation is now handled solely by validator.py via analyzer.
    This test ensures the parameter stays removed.

    See: PROJECT.md "Key Decisions" - Remove duplicate validation paths
    """
    sig = inspect.signature(JinjaValidator.__init__)
    param_names = set(sig.parameters.keys()) - {"self"}
    assert "validation_engine" not in param_names, (
        "validation_engine parameter must not exist on JinjaValidator.__init__"
    )


def test_no_entity_validation_methods() -> None:
    """Guard: Prevent re-introduction of entity validation methods.

    v2.14.0 removed _extract_entity_references, _check_special_reference,
    and _validate_entity_references from JinjaValidator. These created a
    duplicate validation path with high false positive rates.

    See: PROJECT.md "Key Decisions" - Remove duplicate validation paths
    """
    assert not hasattr(JinjaValidator, "_extract_entity_references"), (
        "_extract_entity_references must be removed"
    )
    assert not hasattr(JinjaValidator, "_check_special_reference"), (
        "_check_special_reference must be removed"
    )
    assert not hasattr(JinjaValidator, "_validate_entity_references"), (
        "_validate_entity_references must be removed"
    )


def test_no_issue_type_remap_dict() -> None:
    """Guard: Prevent re-introduction of _ISSUE_TYPE_REMAP.

    v2.14.0 removed _ISSUE_TYPE_REMAP as part of entity validation removal.
    This dict was used to remap entity issues from the template path.

    See: PROJECT.md "Key Decisions" - Remove duplicate validation paths
    """
    import custom_components.autodoctor.jinja_validator as jv_module

    assert not hasattr(jv_module, "_ISSUE_TYPE_REMAP"), (
        "_ISSUE_TYPE_REMAP must be removed from jinja_validator module"
    )


def test_no_special_ref_types_dict() -> None:
    """Guard: Prevent re-introduction of _SPECIAL_REF_TYPES.

    v2.14.0 removed _SPECIAL_REF_TYPES as part of entity validation removal.
    This dict was used for special entity reference handling in templates.

    See: PROJECT.md "Key Decisions" - Remove duplicate validation paths
    """
    import custom_components.autodoctor.jinja_validator as jv_module

    assert not hasattr(jv_module, "_SPECIAL_REF_TYPES"), (
        "_SPECIAL_REF_TYPES must be removed from jinja_validator module"
    )


def test_template_with_nonexistent_entity_no_entity_issues() -> None:
    """Templates referencing nonexistent entities must NOT produce entity issues.

    After v2.14.0, JinjaValidator only checks syntax and filter/test semantics.
    Entity validation is handled by validator.py through the analyzer path.
    """
    validator = JinjaValidator()
    automation = {
        "id": "no_entity_check",
        "alias": "No Entity Check",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ is_state('light.totally_nonexistent', 'on') }}",
            }
        ],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{{ states.sensor.also_missing.state | float > 20 }}",
            }
        ],
        "actions": [
            {
                "data": {
                    "message": "{{ state_attr('climate.gone', 'temperature') }}",
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    # No issues at all -- syntax is valid, no entity validation
    assert len(issues) == 0


# --- Paired depth tests per recursion path (mutation hardening) ---


def _build_nested_choose_default(depth: int) -> list:
    """Build nested choose→default actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"choose": [], "default": inner}]
    return inner


def test_choose_default_22_deep_stops_at_depth_limit() -> None:
    """22-deep choose→default nesting hits depth limit; error NOT found.

    Kills: _depth + 1 mutations at choose default recursion (L317).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth22_default",
        "alias": "Depth 22 Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_choose_default(22),
    }
    issues = validator.validate_automations([automation])
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_choose_default_19_deep_finds_error() -> None:
    """19-deep choose→default nesting is under limit; error IS found.

    Paired with test_choose_default_22_deep_stops_at_depth_limit to kill
    _depth+1 arithmetic mutations at choose default recursion (L317).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth19_default",
        "alias": "Depth 19 Default",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_choose_default(19),
    }
    issues = validator.validate_automations([automation])
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def _build_nested_if_then(depth: int) -> list:
    """Build nested if→then actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"if": [], "then": inner}]
    return inner


def test_if_then_22_deep_stops_at_depth_limit() -> None:
    """22-deep if→then nesting hits depth limit; error NOT found.

    Kills: _depth + 1 mutations at if/then recursion (L336).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth22_if_then",
        "alias": "Depth 22 If Then",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_if_then(22),
    }
    issues = validator.validate_automations([automation])
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_if_then_19_deep_finds_error() -> None:
    """19-deep if→then nesting is under limit; error IS found.

    Paired with test_if_then_22_deep_stops_at_depth_limit to kill
    _depth+1 arithmetic mutations at if/then recursion (L336).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth19_if_then",
        "alias": "Depth 19 If Then",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_if_then(19),
    }
    issues = validator.validate_automations([automation])
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def _build_nested_if_else(depth: int) -> list:
    """Build nested if→else actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"if": [], "else": inner}]
    return inner


def test_if_else_22_deep_stops_at_depth_limit() -> None:
    """22-deep if→else nesting hits depth limit; error NOT found.

    Kills: _depth + 1 mutations at if/else recursion (L345).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth22_if_else",
        "alias": "Depth 22 If Else",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_if_else(22),
    }
    issues = validator.validate_automations([automation])
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_if_else_19_deep_finds_error() -> None:
    """19-deep if→else nesting is under limit; error IS found.

    Paired with test_if_else_22_deep_stops_at_depth_limit to kill
    _depth+1 arithmetic mutations at if/else recursion (L345).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth19_if_else",
        "alias": "Depth 19 If Else",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_if_else(19),
    }
    issues = validator.validate_automations([automation])
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def _build_nested_repeat_sequence(depth: int) -> list:
    """Build nested repeat→sequence actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"repeat": {"while": [], "sequence": inner}}]
    return inner


def test_repeat_sequence_22_deep_stops_at_depth_limit() -> None:
    """22-deep repeat→sequence nesting hits depth limit; error NOT found.

    Kills: _depth + 1 mutations at repeat sequence recursion (L375).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth22_repeat_seq",
        "alias": "Depth 22 Repeat Sequence",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_repeat_sequence(22),
    }
    issues = validator.validate_automations([automation])
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_repeat_sequence_19_deep_finds_error() -> None:
    """19-deep repeat→sequence nesting is under limit; error IS found.

    Paired with test_repeat_sequence_22_deep_stops_at_depth_limit to kill
    _depth+1 arithmetic mutations at repeat sequence recursion (L375).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth19_repeat_seq",
        "alias": "Depth 19 Repeat Sequence",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_repeat_sequence(19),
    }
    issues = validator.validate_automations([automation])
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def _build_nested_parallel(depth: int) -> list:
    """Build nested parallel actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"parallel": inner}]
    return inner


def test_parallel_22_deep_stops_at_depth_limit() -> None:
    """22-deep parallel nesting hits depth limit; error NOT found.

    Kills: _depth + 1 mutations at parallel recursion (L391).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth22_parallel",
        "alias": "Depth 22 Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_parallel(22),
    }
    issues = validator.validate_automations([automation])
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_parallel_19_deep_finds_error() -> None:
    """19-deep parallel nesting is under limit; error IS found.

    Paired with test_parallel_22_deep_stops_at_depth_limit to kill
    _depth+1 arithmetic mutations at parallel recursion (L391).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth19_parallel",
        "alias": "Depth 19 Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": _build_nested_parallel(19),
    }
    issues = validator.validate_automations([automation])
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR


def _build_nested_condition(depth: int) -> dict:
    """Build nested condition with syntax error at bottom."""
    inner = {"condition": "template", "value_template": "{{ broken > }}"}
    for _ in range(depth):
        inner = {"condition": "and", "conditions": [inner]}
    return inner


def test_condition_nesting_22_deep_stops_at_depth_limit() -> None:
    """22-deep condition nesting hits depth limit; error NOT found.

    Kills: _depth + 1 mutations at _validate_condition recursion (L214).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth22_condition",
        "alias": "Depth 22 Condition",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [_build_nested_condition(22)],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert not any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def test_condition_nesting_19_deep_finds_error() -> None:
    """19-deep condition nesting is under limit; error IS found.

    Paired with test_condition_nesting_22_deep_stops_at_depth_limit to kill
    _depth+1 arithmetic mutations at _validate_condition recursion (L214).
    """
    validator = JinjaValidator()
    automation = {
        "id": "depth19_condition",
        "alias": "Depth 19 Condition",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [_build_nested_condition(19)],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR
