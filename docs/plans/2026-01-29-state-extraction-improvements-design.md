# State Reference Extraction Improvements

**Date:** 2026-01-29
**Status:** Implemented
**Version:** 1.0

## Overview

This design enhances the AutomationAnalyzer to extract additional entity reference patterns that are currently missed. The focus is on service calls, scene/script references, for-each iterations, and entity lookup helper functions.

## Current Coverage

The analyzer (`analyzer.py`) currently extracts entity references from:

### Triggers
- **State triggers:** `entity_id`, `to`, `from` states
- **Numeric state triggers:** `entity_id`, `attribute`
- **Template triggers:** Jinja2 templates

### Conditions
- **State conditions:** `entity_id`, `state` values
- **Template conditions:** Jinja2 templates (including shorthand)

### Templates
- `is_state(entity_id, state)`
- `is_state_attr(entity_id, attribute, value)`
- `state_attr(entity_id, attribute)`
- `states.domain.entity` object access
- `states(entity_id)` function calls
- `expand(entity_id)` for groups
- `area_entities(area_id)`
- `device_entities(device_id)`
- `integration_entities(integration_id)`

### Actions
- Recursively handles: `choose`, `if`, `repeat`, `wait_template`, `parallel`

## Gaps Identified

The following patterns are not currently extracted:

1. **Service call targets** - `data.entity_id`, `target.entity_id` in service actions
2. **Scene references** - `scene.turn_on` service calls
3. **Script references** - `script.turn_on` and shorthand `script.my_script` syntax
4. **For-each iteration** - `repeat.for_each` entity lists (static and template)
5. **Entity lookup helpers** - `device_id()`, `area_name()`, `area_id()`, `has_value()`
6. **Dynamic entity IDs** - Template-constructed entity IDs (addressed conservatively)

## Solution Design

### Pattern 1: Service Call Entity References

#### Use Cases

**Direct entity_id in data:**
```yaml
action:
  - service: light.turn_on
    data:
      entity_id: light.kitchen
```

**Multiple entities:**
```yaml
action:
  - service: light.turn_on
    data:
      entity_id:
        - light.kitchen
        - light.bedroom
```

**Target syntax (HA 2023.4+):**
```yaml
action:
  - service: light.turn_on
    target:
      entity_id: light.kitchen
```

**Template entity_id:**
```yaml
action:
  - service: light.turn_on
    data:
      entity_id: "{{ trigger.entity_id }}"
```

#### Implementation

Add new method `_extract_from_service_call()`:

```python
def _extract_from_service_call(
    self,
    action: dict[str, Any],
    index: int,
    automation_id: str,
    automation_name: str,
) -> list[StateReference]:
    """Extract entity references from service calls.

    Args:
        action: The action dict containing service call
        index: Action index in the automation
        automation_id: Automation entity ID
        automation_name: Automation friendly name

    Returns:
        List of StateReference objects for entities in service call
    """
    refs: list[StateReference] = []

    # Get service name (both 'service' and 'action' keys)
    service = action.get("service") or action.get("action")
    if not service:
        return refs

    # Check data.entity_id
    data = action.get("data", {})
    entity_ids = self._normalize_states(data.get("entity_id"))

    # Check target.entity_id (newer syntax)
    target = action.get("target", {})
    entity_ids.extend(self._normalize_states(target.get("entity_id")))

    # Determine reference type based on service
    reference_type = "service_call"
    if service == "scene.turn_on":
        reference_type = "scene"
    elif service == "script.turn_on":
        reference_type = "script"

    for entity_id in entity_ids:
        # If it's a template, extract from template
        if "{{" in entity_id:
            refs.extend(
                self._extract_from_template(
                    entity_id,
                    f"action[{index}].data.entity_id",
                    automation_id,
                    automation_name,
                )
            )
        else:
            # Direct entity reference
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=None,
                    location=f"action[{index}].service.entity_id",
                    reference_type=reference_type,
                )
            )

    return refs
```

Call from `_extract_from_actions()`:

```python
for idx, action in enumerate(actions):
    # NEW: Extract from service calls
    refs.extend(
        self._extract_from_service_call(
            action, idx, automation_id, automation_name
        )
    )

    # Existing: Extract from choose option conditions...
```

### Pattern 2: Scene and Script References

#### Use Cases

**Scene activation:**
```yaml
action:
  - service: scene.turn_on
    target:
      entity_id: scene.movie_time
```

**Script via turn_on:**
```yaml
action:
  - service: script.turn_on
    target:
      entity_id: script.bedtime_routine
```

**Script shorthand syntax:**
```yaml
action:
  - service: script.bedtime_routine
```

#### Implementation

Enhance `_extract_from_service_call()` to detect shorthand script calls:

```python
def _extract_from_service_call(
    self,
    action: dict[str, Any],
    index: int,
    automation_id: str,
    automation_name: str,
) -> list[StateReference]:
    """Extract entity references from service calls."""
    refs: list[StateReference] = []

    service = action.get("service") or action.get("action")
    if not service:
        return refs

    # Shorthand script call: service: script.my_script
    if service.startswith("script.") and service not in ("script.turn_on", "script.reload", "script.turn_off"):
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=service,  # e.g., "script.bedtime_routine"
                expected_state=None,
                expected_attribute=None,
                location=f"action[{index}].service",
                reference_type="script",
            )
        )
        return refs  # Shorthand doesn't have additional entity_id

    # ... rest of service call extraction (data/target entity_id)
```

**Note:** Excludes `script.turn_on`, `script.reload`, `script.turn_off` which are meta-services.

### Pattern 3: For-each Iteration Targets

#### Use Cases

**Static entity list:**
```yaml
action:
  - repeat:
      for_each:
        - light.kitchen
        - light.bedroom
        - light.living_room
      sequence:
        - service: light.turn_on
          target:
            entity_id: "{{ repeat.item }}"
```

**Template-based list:**
```yaml
action:
  - repeat:
      for_each: "{{ expand('group.all_lights') | map(attribute='entity_id') | list }}"
      sequence:
        - service: light.turn_on
          target:
            entity_id: "{{ repeat.item }}"
```

**Area-based iteration:**
```yaml
action:
  - repeat:
      for_each: "{{ area_entities('living_room') }}"
      sequence:
        - service: homeassistant.turn_off
          target:
            entity_id: "{{ repeat.item }}"
```

#### Implementation

Enhance existing repeat handling in `_extract_from_actions()`:

```python
# Inside _extract_from_actions(), in the "repeat" handling section:

elif "repeat" in action:
    repeat_config = action["repeat"]

    # NEW: Extract from for_each
    if "for_each" in repeat_config:
        for_each_value = repeat_config["for_each"]

        # Handle list format (static entities)
        if isinstance(for_each_value, list):
            for item in for_each_value:
                if isinstance(item, str):
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=item,
                            expected_state=None,
                            expected_attribute=None,
                            location=f"action[{idx}].repeat.for_each",
                            reference_type="for_each",
                        )
                    )

        # Handle template format
        elif isinstance(for_each_value, str):
            refs.extend(
                self._extract_from_template(
                    for_each_value,
                    f"action[{idx}].repeat.for_each",
                    automation_id,
                    automation_name,
                )
            )

    # EXISTING: Check while conditions
    while_conditions = repeat_config.get("while", [])
    # ... rest of existing code
```

### Pattern 4: Entity Lookup Helper Functions

#### Use Cases

**Device ID lookup:**
```yaml
template:
  - "{{ device_id('light.kitchen') }}"
```

**Area name/ID lookup:**
```yaml
template:
  - "{{ area_name('light.kitchen') }}"
  - "{{ area_id('sensor.temperature') }}"
```

**Entity value check:**
```yaml
template:
  - "{{ has_value('sensor.temperature') }}"
```

**Device attributes:**
```yaml
template:
  - "{{ device_attr(device_id('light.kitchen'), 'manufacturer') }}"
```

#### Implementation

Add new regex patterns at module level:

```python
# Pattern for device_id('entity_id')
DEVICE_ID_PATTERN = re.compile(
    rf"device_id\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)

# Pattern for area_name('entity_id') and area_id('entity_id')
AREA_NAME_PATTERN = re.compile(
    rf"area_(?:name|id)\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)

# Pattern for has_value('entity_id')
HAS_VALUE_PATTERN = re.compile(
    rf"has_value\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
```

Add to `_extract_from_template()`:

```python
# Extract device_id() calls
for match in DEVICE_ID_PATTERN.finditer(template):
    entity_id = match.group(1)
    if not any(r.entity_id == entity_id for r in refs):
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=None,
                location=f"{location}.device_id",
                reference_type="metadata",
            )
        )

# Extract area_name/area_id() calls
for match in AREA_NAME_PATTERN.finditer(template):
    entity_id = match.group(1)
    if not any(r.entity_id == entity_id for r in refs):
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=None,
                location=f"{location}.area_lookup",
                reference_type="metadata",
            )
        )

# Extract has_value() calls
for match in HAS_VALUE_PATTERN.finditer(template):
    entity_id = match.group(1)
    if not any(r.entity_id == entity_id for r in refs):
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=None,
                location=f"{location}.has_value",
                reference_type="entity",
            )
        )
```

### Pattern 5: Dynamic Entity IDs (Conservative Approach)

#### Decision

**Do NOT extract dynamically constructed entity IDs** to avoid false positives.

**Rationale:**
- Templates like `"light.{{ room }}"` or `"{{ trigger.entity_id }}"` cannot be resolved statically
- Extracting arbitrary `domain.name` patterns from templates creates noise
- Most real entity references are caught by explicit function calls (states(), is_state(), etc.)
- Users employing dynamic entity IDs are advanced and likely know what they're doing
- Autodoctor's value is in high signal, low noise validation

**Implementation:**
- No regex patterns added for dynamic entity IDs
- No special tracking of `trigger.entity_id` usage
- Template entity_ids in service calls are still parsed for embedded function calls

### Pattern 6: State Comparisons

#### Decision

**No changes needed** - already covered by existing patterns.

**Rationale:**
- `states('sensor.temperature') | float > 20` already extracts `sensor.temperature` via `STATES_FUNCTION_PATTERN`
- `state_attr('climate.x', 'temp') | float < 18` already extracts via `STATE_ATTR_PATTERN`
- `states.sensor.temp.state | float > 20` already extracts via `STATES_OBJECT_PATTERN`
- Comparison operators (`>`, `<`, `==`) don't affect entity extraction

## New Reference Types

Add to `models.py` if `reference_type` is validated as an enum:

- `service_call` - Entity referenced in service call data/target
- `scene` - Scene entity in scene.turn_on
- `script` - Script entity in script.turn_on or shorthand
- `for_each` - Entity in repeat.for_each iteration
- `metadata` - Entity in device_id(), area_name(), area_id() lookup

Existing types:
- `entity` (default)
- `group` (expand)
- `area` (area_entities)
- `device` (device_entities)
- `integration` (integration_entities)

## Testing Strategy

### Test File

`tests/test_analyzer.py` - Expand with new test cases

### Test Cases

#### Service Call Extraction

1. **Service with data.entity_id (single)**
   ```python
   action = {"service": "light.turn_on", "data": {"entity_id": "light.kitchen"}}
   # Expect: StateReference(entity_id="light.kitchen", reference_type="service_call")
   ```

2. **Service with data.entity_id (multiple)**
   ```python
   action = {"service": "light.turn_on", "data": {"entity_id": ["light.kitchen", "light.bedroom"]}}
   # Expect: 2 StateReferences
   ```

3. **Service with target.entity_id**
   ```python
   action = {"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}
   # Expect: StateReference(entity_id="light.living_room", reference_type="service_call")
   ```

4. **Service with template entity_id**
   ```python
   action = {"service": "light.turn_on", "data": {"entity_id": "{{ trigger.entity_id }}"}}
   # Expect: Extract entities from template (if any explicit references)
   ```

5. **Service with both data and target (both extracted)**
   ```python
   action = {
       "service": "light.turn_on",
       "data": {"entity_id": "light.kitchen"},
       "target": {"entity_id": "light.bedroom"}
   }
   # Expect: 2 StateReferences
   ```

#### Scene/Script Extraction

6. **Scene via scene.turn_on**
   ```python
   action = {"service": "scene.turn_on", "target": {"entity_id": "scene.movie_time"}}
   # Expect: StateReference(entity_id="scene.movie_time", reference_type="scene")
   ```

7. **Script via script.turn_on**
   ```python
   action = {"service": "script.turn_on", "target": {"entity_id": "script.bedtime"}}
   # Expect: StateReference(entity_id="script.bedtime", reference_type="script")
   ```

8. **Script shorthand**
   ```python
   action = {"service": "script.bedtime_routine"}
   # Expect: StateReference(entity_id="script.bedtime_routine", reference_type="script")
   ```

9. **Script meta-service (not extracted as shorthand)**
   ```python
   action = {"service": "script.reload"}
   # Expect: No StateReference (meta-service, not a script entity)
   ```

#### For-each Extraction

10. **For-each with static list**
    ```python
    action = {
        "repeat": {
            "for_each": ["light.kitchen", "light.bedroom"],
            "sequence": []
        }
    }
    # Expect: 2 StateReferences with reference_type="for_each"
    ```

11. **For-each with template**
    ```python
    action = {
        "repeat": {
            "for_each": "{{ expand('group.all_lights') | map(attribute='entity_id') | list }}",
            "sequence": []
        }
    }
    # Expect: StateReference for group.all_lights via expand() pattern
    ```

12. **For-each with area_entities template**
    ```python
    action = {
        "repeat": {
            "for_each": "{{ area_entities('living_room') }}",
            "sequence": []
        }
    }
    # Expect: StateReference(entity_id="living_room", reference_type="area")
    ```

#### Helper Function Extraction

13. **device_id() function**
    ```python
    template = "{{ device_id('light.kitchen') }}"
    # Expect: StateReference(entity_id="light.kitchen", reference_type="metadata")
    ```

14. **area_name() function**
    ```python
    template = "{{ area_name('sensor.temperature') }}"
    # Expect: StateReference(entity_id="sensor.temperature", reference_type="metadata")
    ```

15. **area_id() function**
    ```python
    template = "{{ area_id('light.bedroom') }}"
    # Expect: StateReference(entity_id="light.bedroom", reference_type="metadata")
    ```

16. **has_value() function**
    ```python
    template = "{{ has_value('sensor.temperature') }}"
    # Expect: StateReference(entity_id="sensor.temperature", reference_type="entity")
    ```

17. **Multiple helper functions in same template**
    ```python
    template = "{{ device_id('light.kitchen') == device_id('light.bedroom') }}"
    # Expect: 2 StateReferences (deduplicated if same entity_id)
    ```

#### Deduplication

18. **Same entity via different patterns**
    ```python
    template = "{{ is_state('light.kitchen', 'on') and device_id('light.kitchen') }}"
    # Expect: 1 StateReference for light.kitchen (deduplicated)
    ```

#### Integration Tests

19. **Full automation with multiple patterns**
    ```yaml
    automation:
      trigger:
        - platform: state
          entity_id: binary_sensor.motion
          to: 'on'
      action:
        - service: light.turn_on
          target:
            entity_id: light.kitchen
        - service: script.bedtime_routine
        - repeat:
            for_each: "{{ area_entities('bedroom') }}"
            sequence:
              - service: homeassistant.turn_off
                target:
                  entity_id: "{{ repeat.item }}"
    ```
    Expected extractions:
    - binary_sensor.motion (state trigger)
    - light.kitchen (service target)
    - script.bedtime_routine (shorthand)
    - bedroom (area_entities)

## Implementation Order

### Phase 1: Service Call Extraction
- Add `_extract_from_service_call()` method
- Call from `_extract_from_actions()`
- Add tests 1-5

### Phase 2: Scene/Script Detection
- Enhance `_extract_from_service_call()` for shorthand scripts
- Add scene/script reference type tagging
- Add tests 6-9

### Phase 3: For-each Support
- Enhance repeat handling in `_extract_from_actions()`
- Add tests 10-12

### Phase 4: Helper Functions
- Add regex patterns (DEVICE_ID_PATTERN, AREA_NAME_PATTERN, HAS_VALUE_PATTERN)
- Add extraction in `_extract_from_template()`
- Add tests 13-17

### Phase 5: Integration Testing
- Add deduplication test (18)
- Add full automation integration test (19)

## Success Criteria

- [x] Service calls with `data.entity_id` extract correctly
- [x] Service calls with `target.entity_id` extract correctly
- [x] Template entity_ids in service calls are parsed
- [x] Scene references via `scene.turn_on` are tagged as `scene` type
- [x] Script shorthand syntax (service: script.X) extracts correctly
- [x] Script meta-services (reload, turn_off) are NOT extracted as entities
- [x] For-each with static lists extracts all entities
- [x] For-each with templates parses template for entity references
- [x] device_id(), area_name(), area_id(), has_value() extract entities
- [x] Deduplication prevents duplicate StateReferences for same entity
- [x] All existing tests pass (no regressions)
- [x] New test coverage > 95% for new code

## Performance Considerations

### Regex Performance

New patterns are compiled at module level (no runtime compilation cost):
- `DEVICE_ID_PATTERN`
- `AREA_NAME_PATTERN`
- `HAS_VALUE_PATTERN`

Pattern complexity is similar to existing patterns (single capture group, no backtracking).

### Service Call Extraction

Additional method call per action, but:
- Only iterates actions once (already happening)
- Fast dict lookups for service/data/target keys
- No significant overhead

### For-each Extraction

Adds one conditional check per repeat action:
- `if "for_each" in repeat_config:` is O(1)
- List iteration is bounded by for_each size (typically small)

**Expected impact:** < 5% overhead on automation extraction time.

## Risks & Mitigations

### Risk: False Positives from Service Calls

**Impact:** Service calls with non-entity data in `entity_id` field

**Mitigation:**
- Template entity_ids are parsed, not blindly extracted
- Deduplication prevents multiple references
- Validation layer will catch non-existent entities

### Risk: Script Shorthand Ambiguity

**Impact:** Non-script services starting with "script." could be misidentified

**Mitigation:**
- Exclude known meta-services: `script.turn_on`, `script.reload`, `script.turn_off`
- HA convention: only script entities use `script.entity_name` service syntax
- Low risk in practice

### Risk: For-each Non-Entity Lists

**Impact:** For-each iterating over non-entity values (numbers, strings)

**Mitigation:**
- Validation layer will flag non-existent entities
- Users can suppress if intentional
- Reference type `for_each` helps distinguish context

### Risk: Helper Function Argument Misparse

**Impact:** Regex captures non-entity arguments to helper functions

**Mitigation:**
- Patterns require `domain.entity_name` format
- Entity validation will catch invalid references
- Pattern is anchored to function call syntax

## Future Enhancements

### Additional Helper Functions

Consider adding patterns for:
- `entity_picture(entity_id)`
- `state_translated(entity_id)`
- `is_hidden_entity(entity_id)`

### Service Call Data Fields

Extract entity references from other service data fields:
- `data.target_sensor` (template sensor)
- `data.source` (media_player)

### Automation References

Extract references to other automations:
- `automation.turn_on`/`automation.turn_off` service calls
- `automation.trigger` service calls

### Blueprint Input Selectors

Extract entities from blueprint input selectors:
- `!input my_entity` references

## References

- Current analyzer: `custom_components/autodoctor/analyzer.py`
- Current models: `custom_components/autodoctor/models.py`
- Current tests: `tests/test_analyzer.py`
- Home Assistant templates: https://www.home-assistant.io/docs/configuration/templating/
- Home Assistant service calls: https://www.home-assistant.io/docs/scripts/service-calls/

## Changelog

**2026-01-29:** Initial design - service calls, scenes, scripts, for-each, helper functions
