"""Property-based tests using Hypothesis to fuzz analyzer, validator, and service validator.

Property-based testing generates hundreds of random inputs to find edge cases
that hand-crafted tests miss. Each test asserts that functions NEVER crash
(return normally or return empty results) regardless of input.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.service_validator import _is_template_value
from custom_components.autodoctor.validator import get_entity_suggestion

# ============================================================================
# Analyzer Tests - AutomationAnalyzer is pure Python, no HA mocks needed
# ============================================================================


@st.composite
def automation_dicts(draw: Any) -> dict[str, Any]:
    """Generate arbitrary automation dictionaries with nested structures.

    Uses recursive strategy to create deeply nested triggers/conditions/actions.
    """
    # Base primitive values
    primitives = st.one_of(
        st.none(),
        st.text(max_size=100),
        st.integers(),
        st.booleans(),
    )

    # Lists and dicts (non-recursive)
    simple_lists = st.lists(primitives, max_size=5)
    simple_dicts = st.dictionaries(st.text(max_size=20), primitives, max_size=5)

    # Trigger/condition/action items (can contain arbitrary keys)
    item_dict = st.dictionaries(
        st.text(max_size=20),
        st.one_of(primitives, simple_lists, simple_dicts),
        max_size=10,
    )

    # Top-level automation structure
    return draw(
        st.fixed_dictionaries(
            {
                "id": st.text(max_size=50),
                "alias": st.text(max_size=50),
            },
            optional={
                "triggers": st.lists(item_dict, max_size=3),
                "trigger": st.lists(item_dict, max_size=3),
                "conditions": st.lists(item_dict, max_size=3),
                "condition": st.lists(item_dict, max_size=3),
                "actions": st.lists(item_dict, max_size=3),
                "action": st.lists(item_dict, max_size=3),
            },
        )
    )


@given(automation=automation_dicts())
@settings(max_examples=200)
def test_extract_state_references_never_crashes(automation: dict[str, Any]) -> None:
    """Property: extract_state_references accepts any automation dict without crashing.

    Generates arbitrary automation configs with random trigger/condition/action
    structures and ensures the analyzer returns a list without raising exceptions.
    """
    analyzer = AutomationAnalyzer()
    result = analyzer.extract_state_references(automation)
    assert isinstance(result, list)


@st.composite
def automation_with_none_values(draw: Any) -> dict[str, Any]:
    """Generate automation dicts where trigger/condition/action fields are None or contain None items."""
    none_or_list = st.one_of(
        st.none(),
        st.just([]),
        st.lists(st.none(), min_size=1, max_size=3),
        st.lists(
            st.one_of(
                st.none(),
                st.fixed_dictionaries(
                    {},
                    optional={
                        "platform": st.text(max_size=20),
                        "entity_id": st.none(),
                        "to": st.none(),
                        "from": st.none(),
                    },
                ),
            ),
            max_size=3,
        ),
    )

    return draw(
        st.fixed_dictionaries(
            {
                "id": st.text(max_size=50),
                "alias": st.text(max_size=50),
            },
            optional={
                "trigger": none_or_list,
                "condition": none_or_list,
                "action": none_or_list,
            },
        )
    )


@given(automation=automation_with_none_values())
@settings(max_examples=200)
def test_extract_state_references_with_none_values(
    automation: dict[str, Any],
) -> None:
    """Property: extract_state_references handles None values without crashing.

    Tests that None in trigger/condition/action lists or as field values
    doesn't cause AttributeError or TypeError.
    """
    analyzer = AutomationAnalyzer()
    result = analyzer.extract_state_references(automation)
    assert isinstance(result, list)


@st.composite
def automation_with_wrong_types(draw: Any) -> dict[str, Any]:
    """Generate automation dicts where string fields get ints/bools/lists/dicts instead."""
    wrong_type_values = st.one_of(
        st.integers(),
        st.booleans(),
        st.lists(st.text(max_size=10), max_size=3),
        st.dictionaries(st.text(max_size=10), st.text(max_size=10), max_size=3),
    )

    trigger_item = st.fixed_dictionaries(
        {},
        optional={
            "platform": wrong_type_values,  # Should be string
            "entity_id": wrong_type_values,  # Should be string or list of strings
            "to": wrong_type_values,  # Should be string or list
            "from": wrong_type_values,  # Should be string or list
            "value_template": wrong_type_values,  # Should be string
        },
    )

    return draw(
        st.fixed_dictionaries(
            {
                "id": st.text(max_size=50),
                "alias": st.text(max_size=50),
            },
            optional={
                "trigger": st.lists(trigger_item, max_size=3),
            },
        )
    )


@given(automation=automation_with_wrong_types())
@settings(max_examples=200)
def test_extract_state_references_with_wrong_types(
    automation: dict[str, Any],
) -> None:
    """Property: extract_state_references handles type mismatches without crashing.

    Tests that int/bool/list/dict values in string fields don't cause crashes
    when the analyzer tries to parse them.
    """
    analyzer = AutomationAnalyzer()
    result = analyzer.extract_state_references(automation)
    assert isinstance(result, list)


@given(automation=automation_dicts())
@settings(max_examples=200)
def test_extract_service_calls_never_crashes(automation: dict[str, Any]) -> None:
    """Property: extract_service_calls accepts any automation dict without crashing.

    Generates arbitrary automation configs and ensures service call extraction
    returns a list without raising exceptions.
    """
    analyzer = AutomationAnalyzer()
    result = analyzer.extract_service_calls(automation)
    assert isinstance(result, list)


@given(
    template=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),  # Exclude surrogates
        max_size=1000,
    )
)
@settings(max_examples=200)
def test_extract_from_template_never_crashes(template: str) -> None:
    """Property: _extract_from_template handles any string without crashing.

    Tests full unicode range, null bytes, unmatched braces, deeply nested
    Jinja-like patterns. Should return a list without regex catastrophic
    backtracking or other crashes.
    """
    analyzer = AutomationAnalyzer()
    result = analyzer._extract_from_template(
        template,
        location="test_location",
        automation_id="automation.test",
        automation_name="Test Automation",
    )
    assert isinstance(result, list)


@given(
    value=st.one_of(
        st.none(),
        st.text(max_size=100),
        st.integers(),
        st.booleans(),
        st.lists(st.text(max_size=50), max_size=5),
        st.dictionaries(st.text(max_size=20), st.text(max_size=20), max_size=3),
    )
)
@settings(max_examples=200)
def test_normalize_states_never_crashes(value: Any) -> None:
    """Property: _normalize_states handles any input type without crashing.

    Tests None, string, int, bool, list, dict. Should always return a list.
    """
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_states(value)
    assert isinstance(result, list)


# ============================================================================
# Validator Tests - Standalone functions, no HA mocks needed
# ============================================================================


@given(
    invalid_entity=st.text(max_size=100),
    all_entities=st.lists(st.text(max_size=100), max_size=50),
)
@settings(max_examples=200)
def test_get_entity_suggestion_never_crashes(
    invalid_entity: str, all_entities: list[str]
) -> None:
    """Property: get_entity_suggestion handles any string inputs without crashing.

    Tests empty strings, strings without dots, strings with multiple dots,
    unicode strings. Should return str | None without raising.
    """
    result = get_entity_suggestion(invalid_entity, all_entities)
    assert result is None or isinstance(result, str)


# ============================================================================
# Service Validator Tests - Helper functions, no HA mocks needed
# ============================================================================


@given(
    value=st.one_of(
        st.text(max_size=100),
        st.integers(),
        st.booleans(),
        st.none(),
        st.lists(st.text(max_size=50), max_size=5),
        st.binary(max_size=100),
    )
)
@settings(max_examples=200)
def test_is_template_value_never_crashes(value: Any) -> None:
    """Property: _is_template_value handles any value type without crashing.

    Tests text, int, bool, None, list, binary. Should return bool without raising.
    """
    result = _is_template_value(value)
    assert isinstance(result, bool)
