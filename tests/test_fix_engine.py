"""Tests for entity suggestion (consolidated from fix_engine into validator)."""

from custom_components.autodoctor.validator import (
    get_entity_suggestion,
)


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
