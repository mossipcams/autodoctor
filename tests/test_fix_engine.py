"""Tests for simplified fix engine."""

import pytest
from custom_components.autodoctor.fix_engine import (
    get_state_suggestion,
    get_entity_suggestion,
    STATE_SYNONYMS,
)


class TestStateSynonyms:
    """Test the STATE_SYNONYMS mapping."""

    def test_away_maps_to_not_home(self):
        assert STATE_SYNONYMS["away"] == "not_home"

    def test_true_maps_to_on(self):
        assert STATE_SYNONYMS["true"] == "on"

    def test_false_maps_to_off(self):
        assert STATE_SYNONYMS["false"] == "off"


class TestGetStateSuggestion:
    """Test get_state_suggestion function."""

    def test_synonym_match(self):
        """Test that synonyms are matched correctly."""
        valid_states = {"on", "off", "unavailable"}
        assert get_state_suggestion("true", valid_states) == "on"
        assert get_state_suggestion("false", valid_states) == "off"

    def test_synonym_with_case(self):
        """Test synonym matching with different cases in valid_states."""
        valid_states = {"On", "Off"}
        result = get_state_suggestion("true", valid_states)
        assert result.lower() == "on"

    def test_fuzzy_match(self):
        """Test fuzzy matching for typos."""
        valid_states = {"playing", "paused", "idle"}
        # "playng" is close to "playing"
        assert get_state_suggestion("playng", valid_states) == "playing"

    def test_no_match(self):
        """Test when no match is found."""
        valid_states = {"on", "off"}
        assert get_state_suggestion("something_completely_different", valid_states) is None

    def test_person_state_away(self):
        """Test that 'away' suggests 'not_home' for person entities."""
        valid_states = {"home", "not_home", "unknown"}
        assert get_state_suggestion("away", valid_states) == "not_home"


class TestGetEntitySuggestion:
    """Test get_entity_suggestion function."""

    def test_same_domain_match(self):
        """Test entity suggestion within same domain."""
        all_entities = [
            "light.living_room",
            "light.bedroom",
            "switch.kitchen",
        ]
        # "light.livingroom" is close to "light.living_room"
        result = get_entity_suggestion("light.livingroom", all_entities)
        assert result == "light.living_room"

    def test_different_domain_no_match(self):
        """Test that different domains don't match."""
        all_entities = [
            "switch.living_room",
            "switch.bedroom",
        ]
        # No lights available
        assert get_entity_suggestion("light.living_room", all_entities) is None

    def test_no_match(self):
        """Test when no match is found."""
        all_entities = [
            "light.bedroom",
            "switch.kitchen",
        ]
        assert get_entity_suggestion("light.completely_different", all_entities) is None

    def test_invalid_entity_format(self):
        """Test that invalid entity IDs return None."""
        all_entities = ["light.bedroom"]
        assert get_entity_suggestion("invalid_no_dot", all_entities) is None
