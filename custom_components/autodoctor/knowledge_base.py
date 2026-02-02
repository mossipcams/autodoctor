"""StateKnowledgeBase - builds and maintains valid states for entities.

Data sources (in priority order):
1. Device class defaults (hardcoded domain mappings)
2. Learned states (user-taught via suppression)
3. Entity registry capabilities (integration-declared valid values)
4. Schema introspection (entity state attributes)
5. Recorder history (observed states)
6. Current state (always valid)

Capabilities provide reliable state/attribute values on fresh installs
where recorder history is not yet available.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from .const import STATE_VALIDATION_WHITELIST
from .device_class_states import get_device_class_states
from .learned_states_store import LearnedStatesStore

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

# Capability introspection - map capability keys to state vs attribute values
CAPABILITY_STATE_SOURCES: dict[str, bool] = {
    "options": True,  # select/input_select - STATES
    "hvac_modes": True,  # climate - STATES
}

CAPABILITY_ATTRIBUTE_SOURCES: dict[str, bool] = {
    "fan_modes": True,  # climate fan_mode attribute
    "preset_modes": True,  # climate/fan preset_mode attribute
    "swing_modes": True,  # climate swing_mode attribute
    "swing_horizontal_modes": True,  # climate swing_horizontal_mode attribute
}


class StateKnowledgeBase:
    """Builds and maintains the valid states map for all entities.

    Data sources (in priority order):
    1. Device class defaults (hardcoded mappings)
    2. Learned states (user-taught)
    3. Entity registry capabilities (integration-declared values)
    4. Schema introspection (entity attributes)
    5. Recorder history (observed states)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        history_days: int = 30,
        learned_states_store: LearnedStatesStore | None = None,
        history_timeout: int = 120,
    ) -> None:
        """Initialize the knowledge base.

        Args:
            hass: Home Assistant instance
            history_days: Number of days of history to query
            learned_states_store: Optional store for user-learned states
            history_timeout: Timeout in seconds for history loading
        """
        self.hass = hass
        self.history_days = history_days
        self.history_timeout = history_timeout
        self._cache: dict[str, set[str]] = {}
        self._observed_states: dict[str, set[str]] = {}
        self._learned_states_store = learned_states_store
        self._lock = asyncio.Lock()
        self._zone_names: set[str] | None = None
        self._area_names: set[str] | None = None

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

    def _get_learned_states(self, entity_id: str) -> set[str]:
        """Get learned states for an entity from the store.

        Args:
            entity_id: The entity ID

        Returns:
            Set of learned states, or empty set if none
        """
        if not self._learned_states_store:
            return set()

        domain = self.get_domain(entity_id)
        integration = self.get_integration(entity_id)

        if not integration:
            return set()

        return self._learned_states_store.get_learned_states(domain, integration)

    def _get_capabilities_states(self, entity_id: str) -> set[str]:
        """Extract valid states from entity registry capabilities.

        Checks registry entry capabilities for attributes that contain
        valid state lists (e.g., options, hvac_modes).

        Returns:
            Set of valid states from capabilities, or empty set
        """
        try:
            entity_registry = er.async_get(self.hass)
            entry = entity_registry.async_get(entity_id)

            if not entry or not entry.capabilities:
                return set()

            states = set()

            # Extract state-related capabilities only
            for cap_key in CAPABILITY_STATE_SOURCES:
                if cap_key in entry.capabilities:
                    cap_value = entry.capabilities[cap_key]
                    if isinstance(cap_value, list):
                        states.update(str(v) for v in cap_value)

            return states

        except Exception as err:
            _LOGGER.debug("Failed to get capabilities for %s: %s", entity_id, err)
            return set()

    def _attribute_maps_to_capability(self, attribute_name: str) -> str | None:
        """Map an attribute name to its capability key.

        Some attributes get their valid values from capabilities
        (e.g., fan_mode → fan_modes, preset_mode → preset_modes).

        Args:
            attribute_name: The attribute to check

        Returns:
            The capability key if mapped, None otherwise
        """
        # Direct mapping: attribute_name → capability_key
        ATTRIBUTE_TO_CAPABILITY = {
            "fan_mode": "fan_modes",
            "preset_mode": "preset_modes",
            "swing_mode": "swing_modes",
            "swing_horizontal_mode": "swing_horizontal_modes",
        }

        return ATTRIBUTE_TO_CAPABILITY.get(attribute_name)

    def _get_capabilities_attribute_values(
        self, entity_id: str, attribute_name: str
    ) -> set[str]:
        """Extract valid values for an attribute from capabilities.

        Uses _attribute_maps_to_capability() to find the capability key,
        then extracts the values from that capability.

        Args:
            entity_id: The entity ID
            attribute_name: The attribute name

        Returns:
            Set of valid values from capabilities, or empty set
        """
        try:
            # Map attribute to capability key
            capability_key = self._attribute_maps_to_capability(attribute_name)
            if not capability_key:
                return set()

            # Get entity registry entry
            entity_registry = er.async_get(self.hass)
            entry = entity_registry.async_get(entity_id)

            if not entry or not entry.capabilities:
                return set()

            # Extract values from capability
            if capability_key in entry.capabilities:
                cap_value = entry.capabilities[capability_key]
                if isinstance(cap_value, list):
                    return {str(v) for v in cap_value}

            return set()

        except Exception as err:
            _LOGGER.debug(
                "Failed to get capability values for %s.%s: %s",
                entity_id,
                attribute_name,
                err,
            )
            return set()

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

        # Most sensors are too free-form to validate (numeric, text, battery, etc.)
        # Exception: enum sensors declare discrete valid states via options attribute
        if domain == "sensor":
            if (
                state.attributes.get("device_class") == "enum"
                and isinstance(state.attributes.get("options"), list)
                and state.attributes["options"]  # non-empty
            ):
                valid_states = set(str(v) for v in state.attributes["options"])
                valid_states.add("unavailable")
                valid_states.add("unknown")
                # Always include current state as valid
                if state.state not in ("unavailable", "unknown"):
                    valid_states.add(state.state)
                # Cache and return
                if entity_id in self._cache:
                    self._cache[entity_id].update(valid_states)
                else:
                    self._cache[entity_id] = valid_states
                return valid_states.copy()
            return None

        # Start with device class defaults
        device_class_defaults = get_device_class_states(domain)
        if device_class_defaults is not None:
            valid_states = device_class_defaults.copy()
            _LOGGER.debug(
                "Entity %s (domain=%s): device class defaults = %s",
                entity_id,
                domain,
                device_class_defaults,
            )
        else:
            # Unknown domain - return empty set (will be populated by history)
            valid_states = set()
            _LOGGER.debug(
                "Entity %s (domain=%s): no device class defaults", entity_id, domain
            )

        # Add learned states for this integration
        learned = self._get_learned_states(entity_id)
        if learned:
            valid_states.update(learned)
            _LOGGER.debug("Entity %s: added learned states = %s", entity_id, learned)

        # Add capabilities states
        capabilities_states = self._get_capabilities_states(entity_id)
        if capabilities_states:
            valid_states.update(capabilities_states)
            _LOGGER.debug(
                "Entity %s: capabilities states = %s", entity_id, capabilities_states
            )

        # For zone-aware entities, add all zone names as valid states
        # Device trackers and person entities can report zone names as their state
        # Also handle Bermuda BLE area sensors (detected by integration platform)
        is_area_sensor = (
            domain == "sensor" and self.get_integration(entity_id) == "bermuda"
        )
        is_bermuda_tracker = (
            domain == "device_tracker" and self.get_integration(entity_id) == "bermuda"
        )
        if domain in ("device_tracker", "person") or is_area_sensor:
            valid_states.update(self._get_zone_names())
            _LOGGER.debug("Entity %s: added zone names to valid states", entity_id)

        # For Bermuda BLE entities (detected by platform), add HA area names from area registry
        # Bermuda sensors report lowercase area names matching HA area IDs
        if is_area_sensor or is_bermuda_tracker:
            valid_states.update(self._get_area_names())
            _LOGGER.debug("Entity %s: added HA area names to valid states", entity_id)

        # For Bermuda BLE device_trackers, also add area names from Bermuda sensors
        # Bermuda uses BLE areas which may differ from HA zones
        if is_bermuda_tracker:
            for sensor_state in self.hass.states.async_all("sensor"):
                sensor_id = sensor_state.entity_id
                if self.get_integration(sensor_id) == "bermuda":
                    if sensor_state.state not in ("unavailable", "unknown"):
                        valid_states.add(sensor_state.state)
            _LOGGER.debug(
                "Entity %s: added Bermuda area sensor states to valid states", entity_id
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

        _LOGGER.debug("Entity %s: final valid states = %s", entity_id, valid_states)

        return valid_states.copy()

    def _get_zone_names(self) -> set[str]:
        """Get all zone names (cached)."""
        if self._zone_names is None:
            self._zone_names = set()
            for zone_state in self.hass.states.async_all("zone"):
                zone_name = zone_state.attributes.get(
                    "friendly_name", zone_state.entity_id.split(".")[1]
                )
                self._zone_names.add(zone_name)
        return self._zone_names

    def _get_area_names(self) -> set[str]:
        """Get all area names (cached)."""
        if self._area_names is None:
            self._area_names = set()
            area_registry = ar.async_get(self.hass)
            for area in area_registry.async_list_areas():
                self._area_names.add(area.name)
                self._area_names.add(area.name.lower())
        return self._area_names

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._zone_names = None
        self._area_names = None

    def get_valid_attributes(self, entity_id: str, attribute: str) -> set[str] | None:
        """Get valid values for an entity attribute.

        Data sources (in priority order):
        1. Entity registry capabilities (integration-declared values)
        2. Current state attributes (fallback)

        Args:
            entity_id: The entity ID
            attribute: The attribute name to get valid values for

        Returns:
            Set of valid attribute values, or None if not available
        """
        state = self.hass.states.get(entity_id)
        if state is None:
            return None

        # Try capability values first (works on fresh install)
        capability_values = self._get_capabilities_attribute_values(
            entity_id, attribute
        )
        if capability_values:
            return capability_values

        # Fall back to current state attributes
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
            _LOGGER.warning(
                "Recorder history not available - get_significant_states not found"
            )
            return

        # Serialize history loading to prevent races
        async with self._lock:
            if entity_ids is None:
                entity_ids = [
                    s.entity_id
                    for s in self.hass.states.async_all()
                    if s.entity_id.split(".")[0] in STATE_VALIDATION_WHITELIST
                ]

            if not entity_ids:
                return

            start_time = datetime.now(UTC) - timedelta(days=self.history_days)
            end_time = datetime.now(UTC)

            try:
                # Run blocking call in executor with timeout
                history = await asyncio.wait_for(
                    self.hass.async_add_executor_job(
                        get_significant_states,
                        self.hass,
                        start_time,
                        end_time,
                        entity_ids,
                        None,
                        True,
                        True,
                    ),
                    timeout=self.history_timeout,
                )
            except TimeoutError:
                _LOGGER.warning(
                    "Timed out loading recorder history after %d seconds",
                    self.history_timeout,
                )
                return
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

    def has_history_loaded(self) -> bool:
        """Check if history has been loaded."""
        return bool(self._observed_states)
