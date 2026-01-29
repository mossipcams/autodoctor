# Validation System Enhancement - Three Gap Solutions

**Date:** 2026-01-28
**Status:** Design
**Version:** 1.0

## Overview

This design addresses three gaps in the autodoctor validation system that cause false positives and limit validation coverage:

1. **Gap 1:** Fresh installs create false positives for valid integration-specific states until history accumulates
2. **Gap 2:** Schema introspection only covers 4 domains (climate, fan, select, input_select)
3. **Gap 3:** No mechanism queries HA's internal platform enums for state discovery

## Current System

### Data Sources (Priority Order)

1. Device class defaults (30+ domains in `device_class_states.py`)
2. Schema introspection (4 domains: climate, fan, select, input_select)
3. Recorder history (observed states over N days)
4. Learned states (user-taught via suppression)

### Current Limitations

- **Fresh installs:** Lack history, so integration-specific states get flagged until dismissed or history accumulates
- **Limited schema coverage:** Only 4 domains introspected for valid values
- **Manual maintenance:** `DEVICE_CLASS_STATES` dict requires manual updates when HA changes
- **Missing capabilities:** Entity registry capabilities contain valid values but aren't queried

## Solution Architecture

Three complementary approaches that work together:

- **Approach A:** Entity Registry Capabilities (solves Gaps 1 & 2)
- **Approach B:** Dynamic State Discovery (solves Gap 3)
- **Approach C:** Expanded Schema Introspection (solves Gap 2)

---

## Approach A: Entity Registry Capabilities

### Problem

Fresh installs lack history, so valid states from entity capabilities (select options, climate hvac_modes) get flagged as errors until history accumulates or user dismisses them.

### Solution

Query entity registry capabilities as a data source between device class defaults and history.

### Key Insight

Entity registry capabilities are populated when the entity is registered by the integration. This is the integration's declaration of valid values - more reliable than observing state attributes which might be missing depending on current entity state.

**Examples:**
- select entities: `capabilities = {ATTR_OPTIONS: ["option1", "option2"]}`
- climate entities: `capabilities = {ATTR_HVAC_MODES: ["heat", "cool"], ATTR_FAN_MODES: [...]}`

### New Priority Order

1. Device class defaults (fallback for all entities)
2. **Entity registry capabilities** ← NEW
3. Schema introspection (state attributes)
4. Recorder history (observed states)
5. Learned states (user-taught)

### Implementation

#### New File: Capability Constants

**Location:** `knowledge_base.py`

```python
# Map capability keys to whether they contain state values vs attribute values
CAPABILITY_STATE_SOURCES = {
    "options": True,              # select/input_select - STATES
    "hvac_modes": True,           # climate - STATES
}

CAPABILITY_ATTRIBUTE_SOURCES = {
    "fan_modes": True,            # climate fan_mode attribute
    "preset_modes": True,         # climate/fan preset_mode attribute
    "swing_modes": True,          # climate swing_mode attribute
    "swing_horizontal_modes": True, # climate swing_horizontal_mode attribute
}
```

#### New Method: `_get_capabilities_states()`

```python
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
        _LOGGER.debug(
            "Failed to get capabilities for %s: %s",
            entity_id,
            err
        )
        return set()
```

#### Modified: `get_valid_states()`

Insert capability check after device class defaults:

```python
# 1. Start with device class defaults
valid_states = device_class_defaults.copy() if device_class_defaults else set()

# 2. Add capabilities states (NEW)
capabilities_states = self._get_capabilities_states(entity_id)
if capabilities_states:
    valid_states.update(capabilities_states)
    _LOGGER.debug(
        "Entity %s: capabilities states = %s",
        entity_id,
        capabilities_states
    )

# 3. Add learned states
# 4. Add zone names (for device_tracker/person)
# 5. Schema introspection (state attributes)
# 6. History
# 7. Current state
```

#### Modified: `get_valid_attributes()`

Add capability-based attribute validation:

```python
def _get_capabilities_attribute_values(
    self,
    entity_id: str,
    attribute: str
) -> set[str] | None:
    """Extract valid attribute values from entity registry capabilities."""
    try:
        entity_registry = er.async_get(self.hass)
        entry = entity_registry.async_get(entity_id)

        if not entry or not entry.capabilities:
            return None

        # Check capability attribute sources
        for cap_key in CAPABILITY_ATTRIBUTE_SOURCES:
            # Map attribute name to capability key
            if self._attribute_maps_to_capability(attribute, cap_key):
                cap_value = entry.capabilities.get(cap_key)
                if isinstance(cap_value, list):
                    return set(str(v) for v in cap_value)

        return None

    except Exception as err:
        _LOGGER.debug(
            "Failed to get capability attributes for %s: %s",
            entity_id,
            err
        )
        return None

def _attribute_maps_to_capability(self, attribute: str, cap_key: str) -> bool:
    """Check if an attribute name maps to a capability key."""
    # fan_modes -> fan_mode, preset_modes -> preset_mode
    return cap_key.rstrip('s') == attribute or cap_key == attribute
```

### Error Handling

**Registry access failures:**
- Return empty set on any exception
- Log at debug level (not warning - avoid noise)
- Fail safe - don't break validation

**Invalid capability data:**
- Handle non-dict capabilities
- Handle non-list capability values
- Skip null/None values

### Performance

**No performance impact:**
- Entity registry lookups are fast (in-memory)
- No additional caching needed beyond existing `_cache`
- No startup penalty (on-demand during validation)

### Impact

**Eliminates false positives for:**
- select/input_select options (even if never selected)
- climate modes (even if never used)
- fan preset_modes (even if never activated)
- Any entity type with capability-declared valid values

### Testing

**Test file:** `test_knowledge_base.py`

**New test cases:**

1. Capabilities extraction with select entity (options)
2. Capabilities extraction with climate entity (hvac_modes)
3. Empty capabilities handling
4. Missing registry entry handling
5. State vs attribute separation (hvac_modes → states, fan_modes → attributes)
6. Fresh install simulation (no history, capabilities only)

**Mock structure:**

```python
mock_entry = er.RegistryEntry(
    entity_id="select.test",
    platform="test_integration",
    capabilities={"options": ["option1", "option2", "option3"]},
    # ... other required fields
)
```

---

## Approach B: Dynamic State Discovery

### Problem

`DEVICE_CLASS_STATES` is a hardcoded dict that requires manual updates when HA adds new domains or states. No mechanism queries HA's internal platform enums.

### Solution

Dynamically build state mappings by importing HA's entity platform modules and extracting state constants/enums.

### What HA Provides

**State constants:**
```python
from homeassistant.components.lock import (
    STATE_LOCKED, STATE_UNLOCKED, STATE_LOCKING,
    STATE_UNLOCKING, STATE_JAMMED
)
```

**State enums:**
```python
from homeassistant.components.alarm_control_panel import AlarmControlPanelState
# AlarmControlPanelState.DISARMED, ARMED_HOME, etc.
```

**Device class enums (metadata only):**
```python
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
# 28 classes: motion, door, window, occupancy, etc.
from homeassistant.components.sensor import SensorDeviceClass
# 60 classes: temperature, humidity, battery, power, etc.
```

### Implementation Strategy

#### Two-Phase Discovery

**Phase 1:** Extract STATE_* constants from component modules
**Phase 2:** Extract states from Enum classes (AlarmControlPanelState, etc.)

#### When to Discover

**At integration startup** (during `async_setup_entry`)
- One-time cost, then cached in memory
- HA components already loaded at that point
- Avoids import overhead during validation

#### Fallback Strategy

**Use hardcoded defaults if discovery fails:**
- If discovery fails, use current `DEVICE_CLASS_STATES`
- Log discovery failures at debug level
- Ensures reliability even if HA changes structure

#### Caching

**Cache discovered states in memory for the session:**
- No need to rediscover on knowledge base refresh
- Only rediscover on HA restart (integration reload)

### New File: `state_discovery.py`

```python
"""Dynamic state discovery from Home Assistant components."""

import importlib
import logging
from enum import Enum

_LOGGER = logging.getLogger(__name__)

# Domains known to have state constants/enums
DISCOVERABLE_DOMAINS = [
    "lock", "cover", "alarm_control_panel", "vacuum",
    "media_player", "climate", "water_heater", "humidifier",
    "lawn_mower", "valve", "timer", "weather"
]

# Map domain to (state_enum_name, use_constants)
DOMAIN_STATE_SOURCES = {
    "alarm_control_panel": ("AlarmControlPanelState", True),
    "lawn_mower": ("LawnMowerActivity", True),
    "valve": ("ValveState", True),
    "lock": (None, True),  # Only STATE_* constants
    "cover": (None, True),
    "vacuum": (None, True),
    # ... etc
}


def discover_domain_states() -> dict[str, set[str]]:
    """Discover valid states from HA components.

    Returns:
        Dict mapping domain to set of valid states
    """
    discovered = {}

    for domain in DISCOVERABLE_DOMAINS:
        try:
            module = importlib.import_module(
                f"homeassistant.components.{domain}"
            )

            states = set()

            # Get state sources for this domain
            enum_name, use_constants = DOMAIN_STATE_SOURCES.get(
                domain,
                (None, True)
            )

            # Extract from enum if specified
            if enum_name:
                enum_states = _extract_state_enum(module, enum_name)
                states.update(enum_states)

            # Extract from STATE_* constants if enabled
            if use_constants:
                constant_states = _extract_state_constants(module)
                states.update(constant_states)

            if states:
                discovered[domain] = states
                _LOGGER.debug(
                    "Discovered %d states for domain %s: %s",
                    len(states),
                    domain,
                    states
                )

        except ImportError as err:
            _LOGGER.debug(
                "Could not import homeassistant.components.%s: %s",
                domain,
                err
            )
            continue
        except Exception as err:
            _LOGGER.debug(
                "Failed to discover states for %s: %s",
                domain,
                err
            )
            continue

    return discovered


def _extract_state_constants(module) -> set[str]:
    """Extract STATE_* constants from a module.

    Returns:
        Set of state values (lowercased)
    """
    states = set()

    for name in dir(module):
        if name.startswith('STATE_'):
            try:
                value = getattr(module, name)
                # Only include string constants (filter out STATE_CLASS, etc.)
                if isinstance(value, str):
                    states.add(value)
            except AttributeError:
                continue

    return states


def _extract_state_enum(module, enum_name: str) -> set[str]:
    """Extract states from an Enum class.

    Args:
        module: The module containing the enum
        enum_name: Name of the enum class (e.g., "AlarmControlPanelState")

    Returns:
        Set of state values
    """
    try:
        enum_class = getattr(module, enum_name)
        if not issubclass(enum_class, Enum):
            return set()

        return {member.value for member in enum_class}

    except (AttributeError, TypeError):
        return set()
```

### Modified: `device_class_states.py`

```python
"""Device class state mappings for known Home Assistant domains."""

from __future__ import annotations

import logging

from .state_discovery import discover_domain_states

_LOGGER = logging.getLogger(__name__)

# Hardcoded fallback mappings (current implementation)
FALLBACK_DEVICE_CLASS_STATES: dict[str, set[str]] = {
    "binary_sensor": {"on", "off"},
    "person": {"home", "not_home"},
    "device_tracker": {"home", "not_home"},
    "lock": {"locked", "unlocked", "locking", "unlocking", "jammed", "opening", "open"},
    "cover": {"open", "closed", "opening", "closing", "stopped"},
    # ... all current mappings
}

# Discovered states (populated at startup)
_DISCOVERED_STATES: dict[str, set[str]] | None = None


def initialize_discovered_states() -> None:
    """Initialize discovered states from HA components.

    Called at integration startup. Falls back to FALLBACK states if discovery fails.
    """
    global _DISCOVERED_STATES

    try:
        _DISCOVERED_STATES = discover_domain_states()
        _LOGGER.info(
            "Discovered states for %d domains",
            len(_DISCOVERED_STATES)
        )
    except Exception as err:
        _LOGGER.warning(
            "Failed to discover domain states, using fallback: %s",
            err
        )
        _DISCOVERED_STATES = {}


def get_device_class_states(domain: str) -> set[str] | None:
    """Get known valid states for a domain.

    Uses discovered states if available, falls back to hardcoded.

    Args:
        domain: The entity domain (e.g., 'binary_sensor', 'lock')

    Returns:
        Set of valid states, or None if domain is unknown
    """
    # Prefer discovered states
    if _DISCOVERED_STATES is not None and domain in _DISCOVERED_STATES:
        return _DISCOVERED_STATES[domain].copy()

    # Fallback to hardcoded
    return FALLBACK_DEVICE_CLASS_STATES.get(domain)


def get_all_known_domains() -> set[str]:
    """Get all domains with known state mappings.

    Returns:
        Set of domain names
    """
    domains = set(FALLBACK_DEVICE_CLASS_STATES.keys())

    if _DISCOVERED_STATES:
        domains.update(_DISCOVERED_STATES.keys())

    return domains
```

### Modified: `__init__.py`

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up autodoctor from a config entry."""

    # Initialize discovered states (run in executor to avoid blocking startup)
    await hass.async_add_executor_job(
        device_class_states.initialize_discovered_states
    )

    # ... rest of setup
```

### Error Handling

**Discovery failures:**
- Import errors (HA component structure changed)
- Missing state constants (component doesn't define them)
- Unknown domain (not in DISCOVERABLE_DOMAINS)

**All failures → use FALLBACK_DEVICE_CLASS_STATES**

**Logging strategy:**
- INFO: Successful discovery with count
- DEBUG: Per-domain discovery results
- WARNING: Overall discovery failure (with fallback note)

### Performance

**Startup cost:**
- One-time import cost during integration setup
- Run in executor to avoid blocking HA startup
- Typically < 100ms for all domains

**Runtime:**
- Zero overhead - uses in-memory dict
- Same performance as current hardcoded approach

### Testing

**Test file:** `test_state_discovery.py` (new)

**Test cases:**

1. State constants extraction with mock module
2. State constants filtering (only STRING values)
3. State enum extraction with real AlarmControlPanelState
4. Full discovery discovers known domains
5. Partial failure handling (some succeed, some fail)
6. Integration test: discovered vs fallback precedence
7. Comparison test: discovered states match hardcoded FALLBACK

**Mock structure:**

```python
class MockLockModule:
    STATE_LOCKED = "locked"
    STATE_UNLOCKED = "unlocked"
    STATE_CLASS = "lock"  # Should be filtered (not a state)
    OTHER_CONSTANT = 123  # Should be filtered (not STATE_*)
```

---

## Approach C: Expanded Schema Introspection

### Problem

Schema introspection only covers 4 domains (climate, fan, select, input_select). Many other domains have similar list-based attributes containing valid values.

### Solution

Expand schema introspection to cover more domains and split into state vs attribute value mappings.

### Current State

**Current SCHEMA_ATTRIBUTES (4 domains):**
```python
SCHEMA_ATTRIBUTES: dict[str, list[str]] = {
    "climate": ["hvac_modes", "preset_modes", "fan_modes", "swing_modes"],
    "fan": ["preset_modes"],
    "select": ["options"],
    "input_select": ["options"],
}
```

**Problem:** Mixed state values and attribute values in same mapping.

### New Design: Split Mappings

#### SCHEMA_STATE_ATTRIBUTES

Attributes containing valid **states**:

```python
SCHEMA_STATE_ATTRIBUTES: dict[str, list[str]] = {
    "climate": ["hvac_modes"],
    "select": ["options"],
    "input_select": ["options"],
    "humidifier": ["available_modes", "modes"],  # Try both variants
    "water_heater": ["operation_list", "operation_mode_list"],  # Try both
}
```

#### SCHEMA_VALUE_ATTRIBUTES

Attributes containing valid **attribute values**:

```python
SCHEMA_VALUE_ATTRIBUTES: dict[str, list[str]] = {
    "climate": ["preset_modes", "fan_modes", "swing_modes", "swing_horizontal_modes"],
    "fan": ["preset_modes"],
    "light": ["effect_list"],  # NEW
    "media_player": ["source_list", "sound_mode_list"],  # NEW
}
```

### Attribute Name Variations

**Support multiple attribute name variants per domain:**

Some integrations use different names for the same concept:
- humidifier: `available_modes` vs `modes`
- water_heater: `operation_list` vs `operation_mode_list`

**Solution:** List multiple variants, try in order until found.

### Expanded ATTRIBUTE_VALUE_SOURCES

**Current (5 mappings):**
```python
ATTRIBUTE_VALUE_SOURCES: dict[str, str] = {
    "effect": "effect_list",
    "preset_mode": "preset_modes",
    "hvac_mode": "hvac_modes",
    "fan_mode": "fan_modes",
    "swing_mode": "swing_modes",
}
```

**Expanded (10+ mappings):**
```python
ATTRIBUTE_VALUE_SOURCES: dict[str, str] = {
    "effect": "effect_list",
    "preset_mode": "preset_modes",
    "hvac_mode": "hvac_modes",
    "fan_mode": "fan_modes",
    "swing_mode": "swing_modes",
    "swing_horizontal_mode": "swing_horizontal_modes",  # NEW - climate
    "mode": "available_modes",  # NEW - humidifier
    "operation_mode": "operation_list",  # NEW - water_heater
    "source": "source_list",  # NEW - media_player
    "sound_mode": "sound_mode_list",  # NEW - media_player
}
```

**Variant handling:**
```python
ATTRIBUTE_VALUE_SOURCES_VARIANTS: dict[str, list[str]] = {
    "mode": ["available_modes", "modes"],
    "operation_mode": ["operation_list", "operation_mode_list"],
}
```

### Implementation

#### Modified: `get_valid_states()`

Replace current schema introspection:

```python
# Schema introspection for STATE attributes
if domain in SCHEMA_STATE_ATTRIBUTES:
    for attr_name in SCHEMA_STATE_ATTRIBUTES[domain]:
        attr_value = state.attributes.get(attr_name)
        if attr_value and isinstance(attr_value, list):
            valid_states.update(str(v) for v in attr_value)
            _LOGGER.debug(
                "Entity %s: added states from attribute %s = %s",
                entity_id,
                attr_name,
                attr_value
            )
```

#### Modified: `get_valid_attributes()`

Add variant handling:

```python
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

    # Try primary source
    source_attr = ATTRIBUTE_VALUE_SOURCES.get(attribute)
    if source_attr:
        values = state.attributes.get(source_attr)
        if values and isinstance(values, list):
            return set(str(v) for v in values)

    # Try variants
    variants = ATTRIBUTE_VALUE_SOURCES_VARIANTS.get(attribute, [])
    for source_attr in variants:
        values = state.attributes.get(source_attr)
        if values and isinstance(values, list):
            return set(str(v) for v in values)

    return None
```

### Coverage

**Domains with expanded coverage:**

| Domain | State Attributes | Attribute Value Attributes |
|--------|-----------------|---------------------------|
| climate | hvac_modes | preset_modes, fan_modes, swing_modes, swing_horizontal_modes |
| fan | - | preset_modes |
| select | options | - |
| input_select | options | - |
| humidifier | available_modes, modes | - |
| water_heater | operation_list, operation_mode_list | - |
| light | - | effect_list |
| media_player | - | source_list, sound_mode_list |

### Testing

**Expand `test_knowledge_base.py`:**

**Test cases:**

1. Humidifier with `available_modes` → states added to valid_states
2. Water heater with `operation_list` → states added to valid_states
3. Light with `effect_list` → values NOT added to valid_states
4. Light `get_valid_attributes("light.x", "effect")` → returns effect_list
5. Media player source/sound_mode attribute validation
6. Attribute name variants (primary missing, variant found)

**Mock structure:**

```python
# Mock humidifier with available_modes
mock_humidifier = Mock(
    entity_id="humidifier.bedroom",
    state="auto",
    attributes={"available_modes": ["auto", "normal", "eco", "sleep"]}
)

# Mock light with effect_list
mock_light = Mock(
    entity_id="light.kitchen",
    state="on",
    attributes={"effect_list": ["rainbow", "colorloop", "random"]}
)
```

---

## Implementation Order

### Phase 1: Approach A (Entity Registry Capabilities)

**Priority:** HIGH - solves biggest pain point (fresh install false positives)

**Files:**
- `custom_components/autodoctor/knowledge_base.py` - add capability methods
- `tests/test_knowledge_base.py` - add capability tests

**Estimated effort:** Medium

### Phase 2: Approach C (Expanded Schema Introspection)

**Priority:** MEDIUM - quick win, clear what to add

**Files:**
- `custom_components/autodoctor/knowledge_base.py` - split schema mappings, expand coverage
- `tests/test_knowledge_base.py` - add schema expansion tests

**Estimated effort:** Small

### Phase 3: Approach B (Dynamic Discovery)

**Priority:** MEDIUM - future-proofing, less urgent

**Files:**
- `custom_components/autodoctor/state_discovery.py` - NEW file
- `custom_components/autodoctor/device_class_states.py` - refactor for discovery
- `custom_components/autodoctor/__init__.py` - startup integration
- `tests/test_state_discovery.py` - NEW file
- `tests/test_device_class_states.py` - expand tests

**Estimated effort:** Medium

---

## Success Criteria

### Approach A Success

- [ ] select/input_select entities validate correctly on fresh install (no history)
- [ ] climate entities validate hvac_modes on fresh install
- [ ] fan entities validate preset_modes on fresh install
- [ ] Capabilities fallback gracefully when registry unavailable
- [ ] No performance regression in validation speed

### Approach B Success

- [ ] States discovered from 10+ HA component modules
- [ ] Discovered states match or exceed hardcoded FALLBACK
- [ ] Discovery failures fall back to FALLBACK gracefully
- [ ] No blocking on HA startup
- [ ] Startup time increase < 100ms

### Approach C Success

- [ ] humidifier, water_heater, light, media_player validation coverage added
- [ ] State vs attribute separation prevents false positives
- [ ] Attribute name variants handled correctly
- [ ] No regression in existing climate/fan/select validation

### Overall Success

- [ ] Zero false positives on fresh install for covered entity types
- [ ] Expanded coverage to 8+ domains (from 4)
- [ ] Future-proof state discovery from HA components
- [ ] All existing tests pass
- [ ] New test coverage > 90% for new code

---

## Risks & Mitigations

### Risk: HA Changes Component Structure

**Impact:** Discovery breaks, imports fail

**Mitigation:**
- Fallback to hardcoded FALLBACK_DEVICE_CLASS_STATES
- Log failures at debug level (not warning to avoid user alarm)
- Keep FALLBACK mappings maintained as backup

### Risk: Entity Registry Capabilities Change Format

**Impact:** Capability extraction breaks

**Mitigation:**
- Type checks before accessing (isinstance checks)
- Exception handling returns empty set (fail safe)
- Falls back to schema introspection and history

### Risk: Performance Regression

**Impact:** Validation slower, integration startup delayed

**Mitigation:**
- Discovery runs in executor (non-blocking)
- Capability lookups are in-memory (fast)
- Cache discovered states (no repeated imports)
- Benchmark validation speed before/after

### Risk: False Negatives (Missing Valid States)

**Impact:** Some valid states still flagged as errors

**Mitigation:**
- Multi-layer approach (capabilities + discovery + schema + history)
- Learned states still work as escape hatch
- User can still suppress individual issues

---

## Future Enhancements

### Auto-discovery of Schema Attributes

Instead of hardcoding SCHEMA_STATE_ATTRIBUTES, inspect entity base classes:

```python
# Auto-discover attributes ending in _modes, _list, options
for attr in dir(entity):
    if attr.endswith(('_modes', '_list')) or attr == 'options':
        # Check if it's a list-valued property
```

### Integration-Specific State Learning

Track which integrations add which states beyond defaults:

```python
# Example: roborock vacuum adds "returning_to_dock" beyond default vacuum states
INTEGRATION_STATE_EXTENSIONS = {
    "roborock": {
        "vacuum": {"returning_to_dock", "spot_cleaning"}
    }
}
```

### Community-Sourced State Database

Allow users to contribute integration-specific states:

- Upload learned states anonymously
- Aggregate into community database
- Download on integration setup

---

## References

- Home Assistant Entity Platform docs: https://developers.home-assistant.io/docs/core/entity
- Entity Registry: `homeassistant.helpers.entity_registry`
- Current `device_class_states.py`: Line 6-98
- Current `knowledge_base.py`: Line 36-50 (schema attributes)
- Current `domain_attributes.py`: Line 6-13

---

## Changelog

**2026-01-28:** Initial design - three gap solutions (A, B, C)
