# Entity Registry Capabilities Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add entity registry capabilities as a data source to eliminate fresh install false positives

**Architecture:** Query entity registry capabilities between device class defaults and schema introspection. Split capabilities into state sources (options, hvac_modes) and attribute sources (fan_modes, preset_modes) for accurate validation.

**Tech Stack:** Home Assistant entity_registry, Python type checking, pytest

---

## Task 1: Add Capability Constants

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py:34-50`

**Step 1: Write the failing test**

Create test for capability constants existence:

```python
# In tests/test_knowledge_base.py (add after imports)
from custom_components.autodoctor.knowledge_base import (
    CAPABILITY_STATE_SOURCES,
    CAPABILITY_ATTRIBUTE_SOURCES,
)

async def test_capability_constants_defined(hass: HomeAssistant):
    """Test capability source constants are defined."""
    # State sources (contain valid states)
    assert "options" in CAPABILITY_STATE_SOURCES
    assert "hvac_modes" in CAPABILITY_STATE_SOURCES
    assert CAPABILITY_STATE_SOURCES["options"] is True
    assert CAPABILITY_STATE_SOURCES["hvac_modes"] is True

    # Attribute sources (contain valid attribute values)
    assert "fan_modes" in CAPABILITY_ATTRIBUTE_SOURCES
    assert "preset_modes" in CAPABILITY_ATTRIBUTE_SOURCES
    assert "swing_modes" in CAPABILITY_ATTRIBUTE_SOURCES
    assert "swing_horizontal_modes" in CAPABILITY_ATTRIBUTE_SOURCES
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge_base.py::test_capability_constants_defined -xvs`

Expected: FAIL with "ImportError: cannot import name 'CAPABILITY_STATE_SOURCES'"

**Step 3: Add constants to knowledge_base.py**

Add after line 50 (after ATTRIBUTE_VALUE_SOURCES):

```python
# Capability introspection - map capability keys to state vs attribute values
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_capability_constants_defined -xvs`

Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: add capability source constants for state vs attribute separation"
```

---

## Task 2: Implement _get_capabilities_states() Method

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py` (add method after line 136)
- Modify: `tests/test_knowledge_base.py` (add tests at end)

**Step 1: Write the failing test - basic capabilities extraction**

```python
async def test_get_capabilities_states_select_entity(hass: HomeAssistant):
    """Test extracting states from select entity capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create entity registry entry with capabilities
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test",
        unique_id="test_select_1",
        suggested_object_id="mode",
        capabilities={"options": ["auto", "cool", "heat", "off"]},
    )

    # Also need the state to exist
    hass.states.async_set("select.mode", "auto")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("select.mode")
    assert states == {"auto", "cool", "heat", "off"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_states_select_entity -xvs`

Expected: FAIL with "AttributeError: 'StateKnowledgeBase' object has no attribute '_get_capabilities_states'"

**Step 3: Implement _get_capabilities_states() method**

Add method after line 136 (after `_get_learned_states()`):

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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_states_select_entity -xvs`

Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: implement _get_capabilities_states() for select/climate entities"
```

---

## Task 3: Test Edge Cases for _get_capabilities_states()

**Files:**
- Modify: `tests/test_knowledge_base.py` (add edge case tests)

**Step 1: Write failing tests for edge cases**

```python
async def test_get_capabilities_states_climate_entity(hass: HomeAssistant):
    """Test extracting hvac_modes from climate entity capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test",
        unique_id="test_climate_1",
        suggested_object_id="thermostat",
        capabilities={
            "hvac_modes": ["heat", "cool", "auto", "off"],
            "fan_modes": ["low", "medium", "high"],  # Should NOT be in states
        },
    )

    hass.states.async_set("climate.thermostat", "heat")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("climate.thermostat")
    # Should only include hvac_modes (state source), not fan_modes (attribute source)
    assert states == {"heat", "cool", "auto", "off"}
    assert "low" not in states
    assert "medium" not in states


async def test_get_capabilities_states_no_capabilities(hass: HomeAssistant):
    """Test handling entity with no capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="switch",
        platform="test",
        unique_id="test_switch_1",
        suggested_object_id="test_switch",
        capabilities=None,  # No capabilities
    )

    hass.states.async_set("switch.test_switch", "on")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("switch.test_switch")
    assert states == set()


async def test_get_capabilities_states_no_registry_entry(hass: HomeAssistant):
    """Test handling entity not in registry."""
    kb = StateKnowledgeBase(hass)

    # Entity exists in states but not in registry
    hass.states.async_set("sensor.temperature", "20")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("sensor.temperature")
    assert states == set()


async def test_get_capabilities_states_invalid_capability_format(hass: HomeAssistant):
    """Test handling capabilities with non-list values."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test",
        unique_id="test_select_bad",
        suggested_object_id="bad_select",
        capabilities={"options": "not_a_list"},  # Invalid format
    )

    hass.states.async_set("select.bad_select", "on")
    await hass.async_block_till_done()

    states = kb._get_capabilities_states("select.bad_select")
    assert states == set()  # Should return empty, not crash
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_states_climate_entity -xvs`
Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_states_no_capabilities -xvs`
Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_states_no_registry_entry -xvs`
Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_states_invalid_capability_format -xvs`

Expected: All PASS (implementation already handles these cases)

**Step 3: Commit**

```bash
git add tests/test_knowledge_base.py
git commit -m "test: add edge case coverage for _get_capabilities_states()"
```

---

## Task 4: Integrate Capabilities into get_valid_states()

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py:137-247`
- Modify: `tests/test_knowledge_base.py` (add integration test)

**Step 1: Write failing integration test**

```python
async def test_get_valid_states_uses_capabilities(hass: HomeAssistant):
    """Test that get_valid_states() includes capability states on fresh install."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create select entity with capabilities but NO history
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test",
        unique_id="test_select_fresh",
        suggested_object_id="test_mode",
        capabilities={"options": ["mode1", "mode2", "mode3"]},
    )

    hass.states.async_set("select.test_mode", "mode1")
    await hass.async_block_till_done()

    # Get valid states (should include capabilities even without history)
    valid_states = kb.get_valid_states("select.test_mode")

    assert "mode1" in valid_states
    assert "mode2" in valid_states
    assert "mode3" in valid_states
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge_base.py::test_get_valid_states_uses_capabilities -xvs`

Expected: FAIL with assertion errors (capabilities not yet integrated)

**Step 3: Modify get_valid_states() to use capabilities**

Update `get_valid_states()` method around line 162-183, insert after learned states (line 183):

```python
# Add learned states for this integration
learned = self._get_learned_states(entity_id)
if learned:
    valid_states.update(learned)
    _LOGGER.debug("Entity %s: added learned states = %s", entity_id, learned)

# Add capabilities states (NEW - insert here after learned states)
capabilities_states = self._get_capabilities_states(entity_id)
if capabilities_states:
    valid_states.update(capabilities_states)
    _LOGGER.debug(
        "Entity %s: capabilities states = %s",
        entity_id,
        capabilities_states
    )

# For zone-aware entities, add all zone names as valid states
# (rest of method continues...)
```

Also update the docstring around line 54-60 to reflect new priority order:

```python
"""Builds and maintains the valid states map for all entities.

Data sources (in priority order):
1. Device class defaults (hardcoded mappings)
2. Learned states (user-taught)
3. Entity registry capabilities (integration-declared values)
4. Schema introspection (entity attributes)
5. Recorder history (observed states)
"""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_get_valid_states_uses_capabilities -xvs`

Expected: PASS

**Step 5: Run all existing tests to ensure no regression**

Run: `pytest tests/test_knowledge_base.py -xvs`

Expected: All tests PASS

**Step 6: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: integrate capabilities into get_valid_states() data flow"
```

---

## Task 5: Implement _attribute_maps_to_capability() Helper

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py` (add method after line 311)
- Modify: `tests/test_knowledge_base.py` (add tests)

**Step 1: Write failing tests**

```python
async def test_attribute_maps_to_capability(hass: HomeAssistant):
    """Test attribute name to capability key mapping."""
    kb = StateKnowledgeBase(hass)

    # fan_modes -> fan_mode (strip trailing 's')
    assert kb._attribute_maps_to_capability("fan_mode", "fan_modes") is True

    # preset_modes -> preset_mode
    assert kb._attribute_maps_to_capability("preset_mode", "preset_modes") is True

    # swing_modes -> swing_mode
    assert kb._attribute_maps_to_capability("swing_mode", "swing_modes") is True

    # Exact match (edge case)
    assert kb._attribute_maps_to_capability("options", "options") is True

    # No match
    assert kb._attribute_maps_to_capability("brightness", "fan_modes") is False
    assert kb._attribute_maps_to_capability("temperature", "preset_modes") is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge_base.py::test_attribute_maps_to_capability -xvs`

Expected: FAIL with "AttributeError: 'StateKnowledgeBase' object has no attribute '_attribute_maps_to_capability'"

**Step 3: Implement helper method**

Add method after line 311 (after current `get_valid_attributes()`):

```python
def _attribute_maps_to_capability(self, attribute: str, cap_key: str) -> bool:
    """Check if an attribute name maps to a capability key.

    Args:
        attribute: The attribute name being validated (e.g., "fan_mode")
        cap_key: The capability key (e.g., "fan_modes")

    Returns:
        True if attribute maps to this capability key

    Examples:
        fan_modes -> fan_mode (strip trailing 's')
        preset_modes -> preset_mode (strip trailing 's')
        options -> options (exact match)
    """
    # Strip trailing 's' from capability key and compare
    # fan_modes -> fan_mode, preset_modes -> preset_mode
    return cap_key.rstrip('s') == attribute or cap_key == attribute
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_attribute_maps_to_capability -xvs`

Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: add _attribute_maps_to_capability() helper for capability key matching"
```

---

## Task 6: Implement _get_capabilities_attribute_values() Method

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py` (add method before `_attribute_maps_to_capability`)
- Modify: `tests/test_knowledge_base.py` (add tests)

**Step 1: Write failing test**

```python
async def test_get_capabilities_attribute_values_climate(hass: HomeAssistant):
    """Test extracting attribute values from climate capabilities."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test",
        unique_id="test_climate_attrs",
        suggested_object_id="ac",
        capabilities={
            "hvac_modes": ["heat", "cool", "off"],
            "fan_modes": ["low", "medium", "high", "auto"],
            "preset_modes": ["eco", "comfort", "boost"],
        },
    )

    hass.states.async_set("climate.ac", "cool")
    await hass.async_block_till_done()

    # Get fan_mode attribute values
    fan_values = kb._get_capabilities_attribute_values("climate.ac", "fan_mode")
    assert fan_values == {"low", "medium", "high", "auto"}

    # Get preset_mode attribute values
    preset_values = kb._get_capabilities_attribute_values("climate.ac", "preset_mode")
    assert preset_values == {"eco", "comfort", "boost"}


async def test_get_capabilities_attribute_values_no_match(hass: HomeAssistant):
    """Test handling when no capability matches the attribute."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="light",
        platform="test",
        unique_id="test_light_1",
        suggested_object_id="bedroom",
        capabilities=None,
    )

    hass.states.async_set("light.bedroom", "on")
    await hass.async_block_till_done()

    # No capabilities, should return None
    result = kb._get_capabilities_attribute_values("light.bedroom", "brightness")
    assert result is None


async def test_get_capabilities_attribute_values_no_registry(hass: HomeAssistant):
    """Test handling entity not in registry."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("sensor.temp", "20")
    await hass.async_block_till_done()

    result = kb._get_capabilities_attribute_values("sensor.temp", "unit")
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_attribute_values_climate -xvs`

Expected: FAIL with "AttributeError: 'StateKnowledgeBase' object has no attribute '_get_capabilities_attribute_values'"

**Step 3: Implement method**

Add method after `get_valid_attributes()` (around line 312), before `_attribute_maps_to_capability()`:

```python
def _get_capabilities_attribute_values(
    self,
    entity_id: str,
    attribute: str
) -> set[str] | None:
    """Extract valid attribute values from entity registry capabilities.

    Args:
        entity_id: The entity ID
        attribute: The attribute name (e.g., "fan_mode")

    Returns:
        Set of valid attribute values, or None if not available
    """
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_attribute_values_climate -xvs`
Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_attribute_values_no_match -xvs`
Run: `pytest tests/test_knowledge_base.py::test_get_capabilities_attribute_values_no_registry -xvs`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: implement _get_capabilities_attribute_values() for attribute validation"
```

---

## Task 7: Integrate Capabilities into get_valid_attributes()

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py:291-311`
- Modify: `tests/test_knowledge_base.py` (add integration test)

**Step 1: Write failing integration test**

```python
async def test_get_valid_attributes_uses_capabilities(hass: HomeAssistant):
    """Test that get_valid_attributes() uses capabilities when state attributes unavailable."""
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test",
        unique_id="test_climate_attrs_int",
        suggested_object_id="hvac",
        capabilities={
            "hvac_modes": ["heat", "cool", "off"],
            "fan_modes": ["low", "high"],
            "preset_modes": ["eco", "away"],
        },
    )

    # Create state WITHOUT fan_modes in attributes (simulating entity in certain state)
    hass.states.async_set(
        "climate.hvac",
        "off",
        attributes={}  # No attributes set
    )
    await hass.async_block_till_done()

    # Should still get fan_mode values from capabilities
    fan_values = kb.get_valid_attributes("climate.hvac", "fan_mode")
    assert fan_values == {"low", "high"}

    # Should still get preset_mode values from capabilities
    preset_values = kb.get_valid_attributes("climate.hvac", "preset_mode")
    assert preset_values == {"eco", "away"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge_base.py::test_get_valid_attributes_uses_capabilities -xvs`

Expected: FAIL with assertion error (capabilities not yet checked)

**Step 3: Modify get_valid_attributes() to check capabilities**

Update `get_valid_attributes()` method (around line 291-311):

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

    # Try ATTRIBUTE_VALUE_SOURCES first (state attributes)
    source_attr = ATTRIBUTE_VALUE_SOURCES.get(attribute)
    if source_attr:
        values = state.attributes.get(source_attr)
        if values and isinstance(values, list):
            return set(str(v) for v in values)

    # Try capabilities if not found in state attributes (NEW)
    cap_values = self._get_capabilities_attribute_values(entity_id, attribute)
    if cap_values is not None:
        return cap_values

    return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_get_valid_attributes_uses_capabilities -xvs`

Expected: PASS

**Step 5: Run all tests to ensure no regression**

Run: `pytest tests/test_knowledge_base.py -xvs`

Expected: All tests PASS

**Step 6: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: integrate capabilities into get_valid_attributes() with fallback"
```

---

## Task 8: Add Fresh Install Simulation Test

**Files:**
- Modify: `tests/test_knowledge_base.py` (add comprehensive integration test)

**Step 1: Write comprehensive fresh install test**

```python
async def test_fresh_install_no_false_positives(hass: HomeAssistant):
    """Test that fresh install has no false positives with capabilities.

    Simulates a fresh Home Assistant install where:
    - Entity registry has capabilities
    - No recorder history exists
    - State attributes might be incomplete
    """
    from homeassistant.helpers import entity_registry as er

    kb = StateKnowledgeBase(hass)

    # Create select entity (no history, capabilities only)
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        domain="select",
        platform="test_integration",
        unique_id="fresh_select",
        suggested_object_id="input_mode",
        capabilities={"options": ["option_a", "option_b", "option_c"]},
    )
    hass.states.async_set("select.input_mode", "option_a")

    # Create climate entity (no history, capabilities only)
    entity_registry.async_get_or_create(
        domain="climate",
        platform="test_integration",
        unique_id="fresh_climate",
        suggested_object_id="thermostat",
        capabilities={
            "hvac_modes": ["heat", "cool", "auto", "off"],
            "fan_modes": ["low", "medium", "high"],
            "preset_modes": ["eco", "comfort"],
        },
    )
    hass.states.async_set(
        "climate.thermostat",
        "off",
        attributes={}  # Minimal attributes (like fresh install)
    )

    await hass.async_block_till_done()

    # Verify select options are valid (no false positives)
    select_states = kb.get_valid_states("select.input_mode")
    assert "option_a" in select_states
    assert "option_b" in select_states
    assert "option_c" in select_states

    # Verify climate hvac_modes are valid (no false positives)
    climate_states = kb.get_valid_states("climate.thermostat")
    assert "heat" in climate_states
    assert "cool" in climate_states
    assert "auto" in climate_states
    assert "off" in climate_states

    # Verify climate attribute values are valid
    fan_values = kb.get_valid_attributes("climate.thermostat", "fan_mode")
    assert fan_values == {"low", "medium", "high"}

    preset_values = kb.get_valid_attributes("climate.thermostat", "preset_mode")
    assert preset_values == {"eco", "comfort"}

    # Verify history is NOT required
    assert not kb.has_history_loaded()
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_fresh_install_no_false_positives -xvs`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_knowledge_base.py
git commit -m "test: add fresh install simulation test for capabilities"
```

---

## Task 9: Update Documentation and Run Full Test Suite

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py:1-3` (module docstring)
- Run: Full test suite

**Step 1: Update module docstring**

Update the module docstring at the top of `knowledge_base.py`:

```python
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
```

**Step 2: Run full test suite**

Run: `pytest tests/test_knowledge_base.py -xvs`

Expected: All tests PASS

Run: `pytest tests/ -k "not integration" -x`

Expected: All unit tests PASS

**Step 3: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py
git commit -m "docs: update knowledge_base docstring with capabilities data source"
```

---

## Task 10: Update index.md

**Files:**
- Modify: `index.md:58-59`

**Step 1: Update knowledge_base description**

Update line 58 in `index.md`:

```markdown
- **`knowledge_base.py`** - Builds valid state mappings from device classes, entity registry capabilities, schema introspection, and recorder history
```

**Step 2: Commit**

```bash
git add index.md
git commit -m "docs: update index.md to reflect capability data source"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] All new tests pass: `pytest tests/test_knowledge_base.py -xvs`
- [ ] No regressions: `pytest tests/ -k "not integration" -x`
- [ ] Fresh install scenario works (test_fresh_install_no_false_positives passes)
- [ ] Capabilities for select entities extracted correctly
- [ ] Capabilities for climate entities extracted correctly
- [ ] State sources (options, hvac_modes) separated from attribute sources (fan_modes, preset_modes)
- [ ] Edge cases handled (no capabilities, no registry, invalid formats)
- [ ] get_valid_states() integrates capabilities
- [ ] get_valid_attributes() integrates capabilities
- [ ] Documentation updated (docstrings, index.md)

---

## Success Criteria

✅ **Eliminates false positives on fresh install:**
- select/input_select options validate without history
- climate hvac_modes validate without history
- climate attribute modes (fan, preset, swing) validate without history

✅ **Maintains backward compatibility:**
- All existing tests pass
- Falls back gracefully when capabilities unavailable
- History and schema introspection still work

✅ **Proper error handling:**
- No crashes on missing registry entries
- No crashes on invalid capability formats
- Debug logging for troubleshooting

✅ **Clean separation:**
- State capabilities (options, hvac_modes) → valid_states
- Attribute capabilities (fan_modes, preset_modes) → valid_attributes
- No mixing of state vs attribute values

---

## Execution Notes

**Estimated duration:** 90-120 minutes for all 10 tasks

**Dependencies:**
- Home Assistant test fixtures (hass)
- Entity registry (homeassistant.helpers.entity_registry)
- pytest and async test support

**Common issues:**
- Entity registry entries need both registry creation AND state creation
- Capabilities must be dict with list values
- Test isolation: ensure entity IDs are unique across tests
