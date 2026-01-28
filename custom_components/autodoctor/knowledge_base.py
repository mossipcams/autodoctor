"""StateKnowledgeBase - builds and maintains valid states for entities."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .device_class_states import get_device_class_states

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

try:
    # Current HA location (2021+)
    from homeassistant.components.recorder.history import get_significant_states
except ImportError:
    try:
        # Alternative location
        from homeassistant.helpers.recorder import get_significant_states
    except ImportError:
        try:
            # Legacy fallback
            from homeassistant.components.recorder import get_significant_states
        except ImportError:
            get_significant_states = None

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
        self._observed_states: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

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

    def get_integration(self, entity_id: str) -> str | None:
        """Get the integration/platform that owns an entity.

        Args:
            entity_id: The entity ID to look up

        Returns:
            Integration name (e.g., 'roborock'), or None if not found
        """
        entity_registry = er.async_get(self.hass)
        entry = entity_registry.async_get(entity_id)
        return entry.platform if entry else None

    def get_valid_states(self, entity_id: str) -> set[str] | None:
        """Get valid states for an entity.

        Args:
            entity_id: The entity ID

        Returns:
            Set of valid states, or None if entity doesn't exist
        """
        # Check cache first - return a copy to prevent external mutation
        if entity_id in self._cache:
            return self._cache[entity_id].copy()

        # Check if entity exists
        state = self.hass.states.get(entity_id)
        if state is None:
            return None

        domain = self.get_domain(entity_id)

        # Sensors are too free-form to validate - skip state validation
        # They can have numeric values, battery states, text, etc.
        if domain == "sensor":
            return None

        # Start with device class defaults
        device_class_defaults = get_device_class_states(domain)
        if device_class_defaults is not None:
            valid_states = device_class_defaults.copy()
            _LOGGER.debug(
                "Entity %s (domain=%s): device class defaults = %s",
                entity_id, domain, device_class_defaults
            )
        else:
            # Unknown domain - return empty set (will be populated by history)
            valid_states = set()
            _LOGGER.debug(
                "Entity %s (domain=%s): no device class defaults",
                entity_id, domain
            )

        # For zone-aware entities, add all zone names as valid states
        # Device trackers and person entities can report zone names as their state
        # Also handle area sensors (e.g., Bermuda BLE area sensors)
        is_area_sensor = (
            domain == "sensor" and
            ("_area" in entity_id or "_room" in entity_id or "bermuda" in entity_id.lower())
        )
        is_bermuda_tracker = (
            domain == "device_tracker" and "bermuda" in entity_id.lower()
        )
        if domain in ("device_tracker", "person") or is_area_sensor:
            for zone_state in self.hass.states.async_all("zone"):
                # Use friendly_name if available, otherwise use zone ID
                zone_name = zone_state.attributes.get(
                    "friendly_name", zone_state.entity_id.split(".")[1]
                )
                valid_states.add(zone_name)
            _LOGGER.debug(
                "Entity %s: added zone names to valid states",
                entity_id
            )

        # For Bermuda BLE entities, add HA area names (lowercase) from area registry
        # Bermuda sensors report lowercase area names matching HA area IDs
        if is_area_sensor or is_bermuda_tracker:
            area_registry = ar.async_get(self.hass)
            for area in area_registry.async_list_areas():
                # Add both the normalized name (lowercase with underscores) and the original name
                valid_states.add(area.name)
                # Also add lowercase version in case Bermuda normalizes differently
                valid_states.add(area.name.lower())
            _LOGGER.debug(
                "Entity %s: added HA area names to valid states",
                entity_id
            )

        # For Bermuda BLE device_trackers, also add area names from Bermuda sensors
        # Bermuda uses BLE areas which may differ from HA zones
        if is_bermuda_tracker:
            for sensor_state in self.hass.states.async_all("sensor"):
                sensor_id = sensor_state.entity_id
                if "_area" in sensor_id or "bermuda" in sensor_id.lower():
                    if sensor_state.state not in ("unavailable", "unknown"):
                        valid_states.add(sensor_state.state)
            _LOGGER.debug(
                "Entity %s: added Bermuda area sensor states to valid states",
                entity_id
            )

        # Schema introspection - after getting device class defaults
        if domain in SCHEMA_ATTRIBUTES:
            for attr_name in SCHEMA_ATTRIBUTES[domain]:
                attr_value = state.attributes.get(attr_name)
                if attr_value and isinstance(attr_value, list):
                    valid_states.update(str(v) for v in attr_value)

        # Add observed states from history (take snapshot to avoid race)
        observed = self._observed_states.get(entity_id)
        if observed:
            valid_states.update(observed)

        # Always include current state as valid
        if state.state not in ("unavailable", "unknown"):
            valid_states.add(state.state)

        # Always add unavailable/unknown as these are always valid
        valid_states.add("unavailable")
        valid_states.add("unknown")

        # Cache the result atomically - merge with any existing cache entry
        # to avoid losing states added by async_load_history()
        if entity_id in self._cache:
            self._cache[entity_id].update(valid_states)
        else:
            self._cache[entity_id] = valid_states

        _LOGGER.debug(
            "Entity %s: final valid states = %s",
            entity_id, valid_states
        )

        return valid_states.copy()

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

    async def async_load_history(self, entity_ids: list[str] | None = None) -> None:
        """Load state history from recorder.

        Uses a lock to prevent concurrent history loads from racing.
        """
        if get_significant_states is None:
            _LOGGER.warning("Recorder history not available - get_significant_states not found")
            return

        # Serialize history loading to prevent races
        async with self._lock:
            if entity_ids is None:
                entity_ids = [s.entity_id for s in self.hass.states.async_all()]

            if not entity_ids:
                return

            start_time = datetime.now() - timedelta(days=self.history_days)
            end_time = datetime.now()

            try:
                # get_significant_states is synchronous, call it directly
                history = get_significant_states(
                    self.hass,
                    start_time,
                    end_time,
                    entity_ids,
                    significant_changes_only=True,
                )
            except Exception as err:
                _LOGGER.warning("Failed to load recorder history: %s", err)
                return

            # Build updates in temporary structures first
            new_observed: dict[str, set[str]] = {}
            loaded_count = 0

            for entity_id, states in history.items():
                entity_states: set[str] = set()

                for state in states:
                    # Handle both State objects and dict formats
                    if hasattr(state, "state"):
                        state_value = state.state
                    elif isinstance(state, dict):
                        state_value = state.get("state")
                    else:
                        continue

                    if state_value and state_value not in ("unavailable", "unknown"):
                        entity_states.add(state_value)
                        loaded_count += 1

                if entity_states:
                    new_observed[entity_id] = entity_states

            # Apply updates atomically - merge with existing data
            for entity_id, states in new_observed.items():
                if entity_id in self._observed_states:
                    self._observed_states[entity_id].update(states)
                else:
                    self._observed_states[entity_id] = states

                # Also update cache if entry exists
                if entity_id in self._cache:
                    self._cache[entity_id].update(states)

            _LOGGER.debug(
                "Loaded %d historical states for %d entities",
                loaded_count,
                len(new_observed),
            )

    def get_observed_states(self, entity_id: str) -> set[str]:
        """Get states that have been observed in history."""
        return self._observed_states.get(entity_id, set())

    def get_historical_entity_ids(self) -> set[str]:
        """Get entity IDs that have been observed in history."""
        return set(self._observed_states.keys())
