"""Property-based tests for validator, device_class_states, and domain_attributes.

Property-based testing generates hundreds of random inputs to find edge cases
that hand-crafted tests miss. Each test asserts that functions NEVER crash
(return normally or return empty results) regardless of input.

This file focuses on validator-side pure functions that handle user-provided
data (entity IDs, domain strings, state values, attribute names).
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.autodoctor.const import STATE_VALIDATION_WHITELIST
from custom_components.autodoctor.device_class_states import (
    DEVICE_CLASS_STATES,
    get_device_class_states,
)
from custom_components.autodoctor.domain_attributes import get_domain_attributes
from custom_components.autodoctor.knowledge_base import SCHEMA_ATTRIBUTES
from custom_components.autodoctor.validator import get_entity_suggestion

# Domains that use schema introspection (entity options attr) instead of DEVICE_CLASS_STATES
_SCHEMA_INTROSPECTION_DOMAINS = frozenset(SCHEMA_ATTRIBUTES.keys())

# ============================================================================
# Device Class States Tests - Pure functions, no HA mocks needed
# ============================================================================


@given(domain=st.text(max_size=100))
@settings(max_examples=200)
def test_get_device_class_states_never_crashes(domain: str) -> None:
    """Property: get_device_class_states accepts any string without crashing.

    Tests empty strings, unicode, strings with special characters, very long
    strings. Should return set[str] | None without raising.
    """
    result = get_device_class_states(domain)
    assert result is None or isinstance(result, set)
    if result is not None:
        # If result is not None, all items must be non-empty strings
        assert all(isinstance(state, str) and state for state in result)


@given(domain=st.sampled_from(list(DEVICE_CLASS_STATES.keys())))
@settings(max_examples=200)
def test_get_device_class_states_known_domains_return_states(domain: str) -> None:
    """Property: all known domains return non-None, non-empty state sets."""
    result = get_device_class_states(domain)
    assert result is not None
    assert isinstance(result, set)
    assert len(result) > 0
    assert all(isinstance(state, str) and state for state in result)


def test_device_class_states_consistency() -> None:
    """All DEVICE_CLASS_STATES domains have non-empty state sets."""
    assert len(DEVICE_CLASS_STATES) > 0
    for domain, states in DEVICE_CLASS_STATES.items():
        assert isinstance(domain, str)
        assert domain
        assert states is not None, f"Domain {domain} has no state mapping"
        assert len(states) > 0, f"Domain {domain} has no state mapping"


@given(domain=st.sampled_from(list(STATE_VALIDATION_WHITELIST)))
@settings(max_examples=200)
def test_whitelisted_domains_have_valid_states(domain: str) -> None:
    """Property: all STATE_VALIDATION_WHITELIST domains have state sources.

    Tests that every domain in the whitelist has either a corresponding
    state set in DEVICE_CLASS_STATES, or uses schema introspection
    (entity options attribute) for dynamic state validation.
    """
    if domain in _SCHEMA_INTROSPECTION_DOMAINS:
        # Schema introspection domains get valid states from entity attributes
        # (e.g., select.options), not from DEVICE_CLASS_STATES
        return

    result = get_device_class_states(domain)
    assert result is not None, f"Whitelisted domain {domain} has no state mapping"
    assert isinstance(result, set)
    assert len(result) > 0
    # Most whitelisted domains should have at least on/off or similar
    assert all(isinstance(state, str) and state for state in result)


# ============================================================================
# Domain Attributes Tests - Pure functions, no HA mocks needed
# ============================================================================


@given(domain=st.one_of(st.none(), st.text(max_size=100)))
@settings(max_examples=200)
def test_get_domain_attributes_never_crashes(domain: str | None) -> None:
    """Property: get_domain_attributes handles any string or None without crashing.

    Tests that:
    - None input returns dict
    - String input returns list
    - Never raises exceptions
    """
    result = get_domain_attributes(domain)

    if domain is None:
        # None should return the full dict
        assert isinstance(result, dict)
        assert all(isinstance(k, str) for k in result)
        assert all(isinstance(v, list) for v in result.values())
    else:
        # String domain should return list (empty if unknown domain)
        assert isinstance(result, list)
        assert all(isinstance(attr, str) for attr in result)


@given(domain=st.text(max_size=100))
@settings(max_examples=200)
def test_get_domain_attributes_string_returns_list(domain: str) -> None:
    """Property: get_domain_attributes with string domain always returns list.

    Tests that arbitrary strings (known or unknown domains) return a list,
    possibly empty for unknown domains.
    """
    result = get_domain_attributes(domain)
    assert isinstance(result, list)
    # All items in list must be non-empty strings (attribute names)
    assert all(isinstance(attr, str) and attr for attr in result)


def test_get_domain_attributes_none_returns_dict() -> None:
    """Property: get_domain_attributes(None) returns full mapping dict.

    Tests that passing None returns the complete DOMAIN_ATTRIBUTES dict
    with valid structure (str keys, list[str] values).
    """
    result = get_domain_attributes(None)
    assert isinstance(result, dict)
    assert len(result) > 0  # Should have at least some domains
    for key, value in result.items():
        assert isinstance(key, str)
        assert key  # Non-empty
        assert isinstance(value, list)
        # All attribute names must be non-empty strings
        assert all(isinstance(attr, str) and attr for attr in value)


# ============================================================================
# Entity Suggestion Tests - Extended fuzzing beyond basic test
# ============================================================================


@given(
    invalid_entity=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),  # Exclude surrogates
        max_size=200,
    ),
    all_entities=st.lists(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            max_size=100,
        ),
        max_size=50,
    ),
)
@settings(max_examples=200)
def test_get_entity_suggestion_never_crashes_unicode(
    invalid_entity: str, all_entities: list[str]
) -> None:
    """Property: get_entity_suggestion handles full unicode without crashing.

    Tests arbitrary unicode strings (excluding surrogates), empty strings,
    strings with multiple dots, no dots, etc.
    """
    result = get_entity_suggestion(invalid_entity, all_entities)
    assert result is None or isinstance(result, str)


@given(
    invalid_entity=st.text(max_size=100).filter(lambda s: "." not in s),
    all_entities=st.lists(st.text(max_size=100), max_size=50),
)
@settings(max_examples=200)
def test_get_entity_suggestion_no_dot_always_none(
    invalid_entity: str, all_entities: list[str]
) -> None:
    """Property: entity IDs without dots always return None.

    Tests that if invalid_entity has no "." character, the function
    always returns None (can't extract domain).
    """
    result = get_entity_suggestion(invalid_entity, all_entities)
    assert result is None


@st.composite
def entity_id_with_suggestion(draw: Any) -> tuple[str, list[str], str]:
    """Generate entity ID typo with matching suggestion in list.

    Returns: (invalid_entity with typo, all_entities list, expected suggestion)
    """
    # Generate a valid-looking entity ID
    domain = draw(st.sampled_from(["light", "switch", "sensor", "binary_sensor"]))
    base_name = draw(
        st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            min_size=3,
            max_size=10,
        )
    )
    correct_entity = f"{domain}.{base_name}"

    # Create typo by replacing one character
    if len(base_name) > 1:
        typo_pos = draw(st.integers(min_value=0, max_value=len(base_name) - 1))
        typo_char = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")))
        typo_name = base_name[:typo_pos] + typo_char + base_name[typo_pos + 1 :]
        invalid_entity = f"{domain}.{typo_name}"
    else:
        # Single-char name, just append char
        invalid_entity = f"{domain}.{base_name}x"

    # Build entity list with correct entity + some noise
    other_entities = draw(
        st.lists(
            st.from_regex(r"[a-z_]{1,10}\.[a-z_]{1,15}", fullmatch=True),
            max_size=10,
        )
    )
    all_entities = [correct_entity, *other_entities]

    return invalid_entity, all_entities, correct_entity


@given(data=entity_id_with_suggestion())
@settings(max_examples=200)
def test_get_entity_suggestion_returns_valid_entity(
    data: tuple[str, list[str], str],
) -> None:
    """Property: when suggestion is not None, it's always from all_entities list.

    Tests that get_entity_suggestion never invents entity IDs - it either
    returns None or returns an entity that exists in all_entities.
    """
    invalid_entity, all_entities, _expected = data
    result = get_entity_suggestion(invalid_entity, all_entities)

    if result is not None:
        assert result in all_entities, f"Suggestion {result} not in entity list"


@given(
    invalid_entity=st.from_regex(r"[a-z_]{1,20}\.[a-z_]{1,20}", fullmatch=True),
    all_entities=st.lists(st.text(max_size=100), max_size=50).filter(
        lambda lst: all("." not in e for e in lst)  # No valid entities
    ),
)
@settings(max_examples=200)
def test_get_entity_suggestion_no_same_domain_returns_none(
    invalid_entity: str, all_entities: list[str]
) -> None:
    """Property: when no entities share domain, always returns None.

    Tests that if all_entities has no entities with the same domain prefix
    as invalid_entity, the function returns None (no matches possible).
    """
    result = get_entity_suggestion(invalid_entity, all_entities)
    assert result is None


@given(
    domain=st.sampled_from(["light", "switch", "sensor", "binary_sensor"]),
    name=st.text(min_size=1, max_size=20),
)
@settings(max_examples=200)
def test_get_entity_suggestion_exact_match_empty_list(domain: str, name: str) -> None:
    """Property: get_entity_suggestion with empty entity list always returns None.

    Tests that if all_entities is empty, no suggestion can be made.
    """
    invalid_entity = f"{domain}.{name}"
    result = get_entity_suggestion(invalid_entity, [])
    assert result is None
