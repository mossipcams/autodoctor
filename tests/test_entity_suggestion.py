"""Tests for entity suggestion (get_entity_suggestion in validator.py)."""

import pytest

from custom_components.autodoctor.validator import (
    get_entity_suggestion,
)


class TestGetEntitySuggestion:
    """Tests for get_entity_suggestion function.

    This function suggests similar entity IDs when a referenced entity doesn't exist,
    helping users find typos in their automations.
    """

    def test_same_domain_match(self) -> None:
        """Test suggestion finds close match within same domain.

        When an entity has a typo (e.g., "livingroom" instead of "living_room"),
        the suggester should find the correct entity if it's similar enough.
        """
        all_entities = [
            "light.living_room",
            "light.bedroom",
            "switch.kitchen",
        ]
        # "light.livingroom" is close to "light.living_room"
        result = get_entity_suggestion("light.livingroom", all_entities)
        assert result == "light.living_room"

    def test_different_domain_no_match(self) -> None:
        """Test suggestion returns None when no entities in same domain exist.

        Entity suggestions should only match within the same domain to avoid
        suggesting irrelevant entities (e.g., don't suggest switch.X for light.Y).
        """
        all_entities = [
            "switch.living_room",
            "switch.bedroom",
        ]
        # No lights available
        assert get_entity_suggestion("light.living_room", all_entities) is None

    def test_no_match(self) -> None:
        """Test suggestion returns None when no close match exists.

        If the typo is too different from any existing entity, no suggestion
        should be made rather than suggesting something unrelated.
        """
        all_entities = [
            "light.bedroom",
            "switch.kitchen",
        ]
        assert get_entity_suggestion("light.completely_different", all_entities) is None

    @pytest.mark.parametrize(
        ("invalid_entity", "expected_result"),
        [
            ("invalid_no_dot", None),
            ("", None),
            (".", None),
            (".no_domain", None),
            ("no_entity.", None),
        ],
        ids=[
            "no-dot",
            "empty-string",
            "only-dot",
            "no-domain",
            "no-entity",
        ],
    )
    def test_invalid_entity_format(
        self, invalid_entity: str, expected_result: str | None
    ) -> None:
        """Test that invalid entity ID formats return None.

        Entity IDs must follow the domain.entity format. Invalid formats
        should not crash the suggester or return spurious suggestions.
        """
        all_entities = ["light.bedroom"]
        assert get_entity_suggestion(invalid_entity, all_entities) == expected_result
