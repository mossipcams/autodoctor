"""StateKnowledgeBase - builds and maintains valid states for entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .device_class_states import get_device_class_states

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Schema introspection attribute mappings
SCHEMA_ATTRIBUTES: dict[str, list[str]] = {
    "climate": ["hvac_modes", "preset_modes", "fan_modes", "swing_modes"],
    "fan": ["preset_modes"],
    "select": ["options"],
    "input_select": ["options"],
}

# Attribute value mappings (for attribute checking)
ATTRIBUTE_VALUE_SOURCES: dict[str, str] = {
    "effect": "effect_list",
    "preset_mode": "preset_modes",
    "hvac_mode": "hvac_modes",
    "fan_mode": "fan_modes",
    "swing_mode": "swing_modes",
}


class StateKnowledgeBase:
    """Builds and maintains the valid states map for all entities.

    Data sources (in priority order):
    1. Device class defaults (hardcoded mappings)
    2. Schema introspection (entity capabilities)
    3. Recorder history (observed states)
    """

    def __init__(self, hass: HomeAssistant, history_days: int = 30) -> None:
        """Initialize the knowledge base.

        Args:
            hass: Home Assistant instance
            history_days: Number of days of history to query
        """
        self.hass = hass
        self.history_days = history_days
        self._cache: dict[str, set[str]] = {}

    def entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists.

        Args:
            entity_id: The entity ID to check

        Returns:
            True if entity exists
        """
        return self.hass.states.get(entity_id) is not None

    def get_domain(self, entity_id: str) -> str:
        """Extract domain from entity ID.

        Args:
            entity_id: The entity ID (e.g., 'binary_sensor.motion')

        Returns:
            The domain (e.g., 'binary_sensor')
        """
        return entity_id.split(".")[0] if "." in entity_id else ""

    def get_valid_states(self, entity_id: str) -> set[str] | None:
        """Get valid states for an entity.

        Args:
            entity_id: The entity ID

        Returns:
            Set of valid states, or None if entity doesn't exist
        """
        # Check cache first
        if entity_id in self._cache:
            return self._cache[entity_id]

        # Check if entity exists
        state = self.hass.states.get(entity_id)
        if state is None:
            return None

        domain = self.get_domain(entity_id)

        # Start with device class defaults
        valid_states = get_device_class_states(domain)
        if valid_states is not None:
            valid_states = valid_states.copy()
        else:
            # Unknown domain - return empty set (will be populated by history)
            valid_states = set()

        # Schema introspection - after getting device class defaults
        if domain in SCHEMA_ATTRIBUTES:
            for attr_name in SCHEMA_ATTRIBUTES[domain]:
                attr_value = state.attributes.get(attr_name)
                if attr_value and isinstance(attr_value, list):
                    valid_states.update(str(v) for v in attr_value)

        # Always add unavailable/unknown as these are always valid
        valid_states.add("unavailable")
        valid_states.add("unknown")

        # Cache the result
        self._cache[entity_id] = valid_states

        return valid_states

    def is_valid_state(self, entity_id: str, state: str) -> bool:
        """Check if a state is valid for an entity.

        Args:
            entity_id: The entity ID
            state: The state to check

        Returns:
            True if state is valid, False otherwise
        """
        valid_states = self.get_valid_states(entity_id)
        if valid_states is None:
            return False
        return state.lower() in {s.lower() for s in valid_states}

    def clear_cache(self) -> None:
        """Clear the state cache."""
        self._cache.clear()

    def get_valid_attributes(self, entity_id: str, attribute: str) -> set[str] | None:
        """Get valid values for an entity attribute.

        Args:
            entity_id: The entity ID
            attribute: The attribute name to get valid values for

        Returns:
            Set of valid attribute values, or None if not available
        """
        state = self.hass.states.get(entity_id)
        if state is None:
            return None

        source_attr = ATTRIBUTE_VALUE_SOURCES.get(attribute)
        if source_attr:
            values = state.attributes.get(source_attr)
            if values and isinstance(values, list):
                return set(str(v) for v in values)

        return None
