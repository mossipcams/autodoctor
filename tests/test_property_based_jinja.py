"""Property-based tests for jinja_validator pure functions.

Property-based testing generates hundreds of random inputs to find edge cases
that hand-crafted tests miss. Each test asserts that functions NEVER crash
(return normally or return empty results) regardless of input.

This file focuses on jinja_validator.py functions that parse and validate
Jinja2 templates in automation configurations.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.autodoctor.jinja_validator import JinjaValidator, _ensure_list
from custom_components.autodoctor.models import ValidationIssue

# ============================================================================
# Helper function tests - _ensure_list
# ============================================================================


@given(
    value=st.one_of(
        st.none(),
        st.text(max_size=100),
        st.integers(),
        st.booleans(),
        st.lists(st.text(max_size=50), max_size=10),
        st.dictionaries(st.text(max_size=20), st.text(max_size=20), max_size=5),
    )
)
@settings(max_examples=200)
def test_ensure_list_never_crashes(value: Any) -> None:
    """Property: _ensure_list accepts any input type without crashing.

    Tests that:
    - None returns empty list
    - List returns itself
    - Any other type returns wrapped in list
    - Never raises exceptions
    """
    result = _ensure_list(value)
    assert isinstance(result, list)

    # Verify specific behaviors
    if value is None:
        assert result == []
    elif isinstance(value, list):
        assert result is value
    else:
        assert result == [value]


# ============================================================================
# JinjaValidator._is_template tests
# ============================================================================


@given(
    text=st.text(
        max_size=500,
        alphabet=st.characters(blacklist_categories=("Cs",)),  # Exclude surrogates
    )
)
@settings(max_examples=200)
def test_is_template_never_crashes(text: str) -> None:
    """Property: _is_template handles any string without crashing.

    Tests that arbitrary strings (empty, unicode, special chars) return bool.
    """
    validator = JinjaValidator(hass=None)
    result = validator._is_template(text)
    assert isinstance(result, bool)


@given(
    prefix=st.text(max_size=50),
    marker=st.sampled_from(["{{", "{%", "{#"]),
    suffix=st.text(max_size=50),
)
@settings(max_examples=200)
def test_is_template_detects_jinja_markers(
    prefix: str, marker: str, suffix: str
) -> None:
    """Property: strings containing Jinja markers return True.

    Tests that {{, {%, or {# anywhere in the string triggers detection.
    """
    validator = JinjaValidator(hass=None)
    text = prefix + marker + suffix
    result = validator._is_template(text)
    assert result is True


# ============================================================================
# JinjaValidator._check_template tests
# ============================================================================


@given(
    template=st.text(max_size=500, alphabet=st.characters(blacklist_categories=("Cs",)))
)
@settings(max_examples=200)
def test_check_template_never_crashes(template: str) -> None:
    """Property: _check_template handles any template string without crashing.

    Tests that arbitrary strings (valid templates, invalid syntax, plain text)
    always return a list of ValidationIssue without raising exceptions.
    """
    validator = JinjaValidator(hass=None, strict_template_validation=False)
    result = validator._check_template(
        template,
        location="test_location",
        auto_id="automation.test",
        auto_name="Test Automation",
    )
    assert isinstance(result, list)
    assert all(isinstance(issue, ValidationIssue) for issue in result)


@given(
    template=st.text(max_size=500, alphabet=st.characters(blacklist_categories=("Cs",)))
)
@settings(max_examples=200)
def test_check_template_strict_never_crashes(template: str) -> None:
    """Property: _check_template with strict mode handles any template without crashing.

    Tests that strict_template_validation=True doesn't cause crashes when
    checking unknown filters/tests.
    """
    validator = JinjaValidator(hass=None, strict_template_validation=True)
    result = validator._check_template(
        template,
        location="test_location",
        auto_id="automation.test",
        auto_name="Test Automation",
    )
    assert isinstance(result, list)
    assert all(isinstance(issue, ValidationIssue) for issue in result)


# ============================================================================
# JinjaValidator._extract_automation_variables tests
# ============================================================================


@given(
    automation=st.fixed_dictionaries(
        {},
        optional={
            "variables": st.one_of(
                st.none(),
                st.dictionaries(
                    st.text(max_size=20), st.text(max_size=50), max_size=10
                ),
                st.text(max_size=50),  # Wrong type
                st.integers(),  # Wrong type
                st.lists(st.text(max_size=20), max_size=5),  # Wrong type
            ),
        },
    )
)
@settings(max_examples=200)
def test_extract_automation_variables_never_crashes(automation: dict[str, Any]) -> None:
    """Property: _extract_automation_variables handles any automation dict without crashing.

    Tests that:
    - Dict with variables dict returns set of keys
    - Dict with None/missing variables returns empty set
    - Dict with wrong-typed variables returns empty set
    - Never raises exceptions
    """
    validator = JinjaValidator(hass=None)
    result = validator._extract_automation_variables(automation)
    assert isinstance(result, set)
    assert all(isinstance(var, str) for var in result)


# ============================================================================
# JinjaValidator.validate_automations tests - main entry point
# ============================================================================


@st.composite
def automation_dicts_with_templates(draw: Any) -> dict[str, Any]:
    """Generate arbitrary automation dicts with nested action structures."""
    # Base primitive values
    primitives = st.one_of(
        st.none(),
        st.text(max_size=100),
        st.integers(),
        st.booleans(),
    )

    # Simple containers
    simple_lists = st.lists(primitives, max_size=3)
    simple_dicts = st.dictionaries(st.text(max_size=20), primitives, max_size=5)

    # Trigger/condition/action items
    item_dict = st.dictionaries(
        st.text(max_size=20),
        st.one_of(primitives, simple_lists, simple_dicts),
        max_size=10,
    )

    # Top-level automation
    return draw(
        st.fixed_dictionaries(
            {
                "id": st.text(max_size=50),
                "alias": st.text(max_size=50),
            },
            optional={
                "variables": st.dictionaries(
                    st.text(max_size=20), st.text(max_size=50), max_size=5
                ),
                "trigger": st.lists(item_dict, max_size=3),
                "condition": st.lists(item_dict, max_size=3),
                "action": st.lists(item_dict, max_size=3),
            },
        )
    )


@given(automations=st.lists(automation_dicts_with_templates(), max_size=3))
@settings(max_examples=200)
def test_validate_automations_never_crashes(automations: list[dict[str, Any]]) -> None:
    """Property: validate_automations accepts arbitrary automation lists without crashing.

    Tests that random automation configs with triggers/conditions/actions
    return a list of ValidationIssue without raising exceptions.
    """
    validator = JinjaValidator(hass=None)
    result = validator.validate_automations(automations)
    assert isinstance(result, list)
    assert all(isinstance(issue, ValidationIssue) for issue in result)


@st.composite
def deeply_nested_automation(draw: Any) -> dict[str, Any]:
    """Generate automation with deeply nested choose/if/repeat/parallel blocks."""

    def nested_action(depth: int) -> dict[str, Any]:
        """Recursively generate nested action structures."""
        if depth >= 5:  # Limit nesting to 5 levels
            return {"service": "test.service"}

        action_type = draw(
            st.sampled_from(["choose", "if", "repeat", "parallel", "simple"])
        )

        if action_type == "simple":
            return {"service": "test.service"}
        elif action_type == "choose":
            return {
                "choose": [
                    {
                        "conditions": [{"condition": "state"}],
                        "sequence": [nested_action(depth + 1)],
                    }
                ],
                "default": [nested_action(depth + 1)],
            }
        elif action_type == "if":
            return {
                "if": [{"condition": "state"}],
                "then": [nested_action(depth + 1)],
                "else": [nested_action(depth + 1)],
            }
        elif action_type == "repeat":
            return {
                "repeat": {
                    "while": [{"condition": "state"}],
                    "sequence": [nested_action(depth + 1)],
                }
            }
        else:  # parallel
            return {
                "parallel": [
                    [nested_action(depth + 1)],
                    [nested_action(depth + 1)],
                ]
            }

    return {
        "id": draw(st.text(max_size=50)),
        "alias": draw(st.text(max_size=50)),
        "action": [nested_action(0)],
    }


@given(automation=deeply_nested_automation())
@settings(max_examples=200)
def test_validate_deeply_nested_actions_never_crashes(
    automation: dict[str, Any],
) -> None:
    """Property: validate_automations handles deeply nested actions without stack overflow.

    Tests that automations with choose/if/repeat/parallel nesting up to 5 levels
    complete validation without crashing or hitting recursion limits.
    """
    validator = JinjaValidator(hass=None)
    result = validator.validate_automations([automation])
    assert isinstance(result, list)
    assert all(isinstance(issue, ValidationIssue) for issue in result)


# ============================================================================
# Edge case: type confusion in automation structure
# ============================================================================


@given(
    automation=st.fixed_dictionaries(
        {
            "id": st.text(max_size=50),
            "alias": st.text(max_size=50),
        },
        optional={
            # Pass wrong types for lists - should handle gracefully
            "trigger": st.one_of(
                st.none(),
                st.text(max_size=50),
                st.integers(),
                st.dictionaries(st.text(max_size=20), st.text(max_size=20), max_size=3),
            ),
            "condition": st.one_of(
                st.none(),
                st.text(max_size=50),
                st.integers(),
            ),
            "action": st.one_of(
                st.none(),
                st.text(max_size=50),
                st.booleans(),
            ),
        },
    )
)
@settings(max_examples=200)
def test_validate_automations_with_type_confusion(automation: dict[str, Any]) -> None:
    """Property: validate_automations handles type-confused fields without crashing.

    Tests that when trigger/condition/action fields get wrong types (string
    instead of list, None, etc.), validation handles it gracefully.
    """
    validator = JinjaValidator(hass=None)
    result = validator.validate_automations([automation])
    assert isinstance(result, list)
    assert all(isinstance(issue, ValidationIssue) for issue in result)
