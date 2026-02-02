"""Tests for JinjaValidator."""

import inspect

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


# --- Phase 24: Entity validation removal guard tests ---
# These tests ensure entity validation is NOT present in JinjaValidator.
# The template validator should only check syntax and filter/test semantics,
# NOT entity existence, attribute existence, or state validity.
# Entity validation is handled by validator.py through the analyzer path.


def test_no_validation_engine_parameter():
    """JinjaValidator.__init__ must NOT accept a validation_engine parameter.

    v2.14.0 removed duplicate entity validation from the template path.
    Entity validation is handled solely by validator.py via analyzer.
    """
    sig = inspect.signature(JinjaValidator.__init__)
    param_names = set(sig.parameters.keys()) - {"self"}
    assert "validation_engine" not in param_names, (
        "validation_engine parameter must not exist on JinjaValidator.__init__"
    )


def test_no_entity_validation_methods():
    """JinjaValidator must NOT have entity validation methods.

    v2.14.0 removed _extract_entity_references, _check_special_reference,
    and _validate_entity_references. These were a duplicate code path.
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


def test_no_issue_type_remap_dict():
    """Module must NOT export _ISSUE_TYPE_REMAP (removed in v2.14.0)."""
    import custom_components.autodoctor.jinja_validator as jv_module
    assert not hasattr(jv_module, "_ISSUE_TYPE_REMAP"), (
        "_ISSUE_TYPE_REMAP must be removed from jinja_validator module"
    )


def test_no_special_ref_types_dict():
    """Module must NOT export _SPECIAL_REF_TYPES (removed in v2.14.0)."""
    import custom_components.autodoctor.jinja_validator as jv_module
    assert not hasattr(jv_module, "_SPECIAL_REF_TYPES"), (
        "_SPECIAL_REF_TYPES must be removed from jinja_validator module"
    )


def test_template_with_nonexistent_entity_no_entity_issues():
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


def test_choose_default_22_deep_stops_at_depth_limit():
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


def test_choose_default_19_deep_finds_error():
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
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def _build_nested_if_then(depth: int) -> list:
    """Build nested if→then actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"if": [], "then": inner}]
    return inner


def test_if_then_22_deep_stops_at_depth_limit():
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


def test_if_then_19_deep_finds_error():
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
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def _build_nested_if_else(depth: int) -> list:
    """Build nested if→else actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"if": [], "else": inner}]
    return inner


def test_if_else_22_deep_stops_at_depth_limit():
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


def test_if_else_19_deep_finds_error():
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
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def _build_nested_repeat_sequence(depth: int) -> list:
    """Build nested repeat→sequence actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"repeat": {"while": [], "sequence": inner}}]
    return inner


def test_repeat_sequence_22_deep_stops_at_depth_limit():
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


def test_repeat_sequence_19_deep_finds_error():
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
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def _build_nested_parallel(depth: int) -> list:
    """Build nested parallel actions to the given depth."""
    inner = [{"data": {"msg": "{{ broken > }}"}}]
    for _ in range(depth):
        inner = [{"parallel": inner}]
    return inner


def test_parallel_22_deep_stops_at_depth_limit():
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


def test_parallel_19_deep_finds_error():
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
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)


def _build_nested_condition(depth: int) -> dict:
    """Build nested condition with syntax error at bottom."""
    inner = {"condition": "template", "value_template": "{{ broken > }}"}
    for _ in range(depth):
        inner = {"condition": "and", "conditions": [inner]}
    return inner


def test_condition_nesting_22_deep_stops_at_depth_limit():
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


def test_condition_nesting_19_deep_finds_error():
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
    assert any(i.issue_type == IssueType.TEMPLATE_SYNTAX_ERROR for i in issues)
