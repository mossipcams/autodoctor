# State Reference Extraction Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract entity references from service calls, scenes, scripts, for-each loops, and helper functions that are currently missed.

**Architecture:** Add new regex patterns for helper functions (device_id, area_name, has_value), new method `_extract_from_service_call()` for service/scene/script extraction, and enhance repeat handling for for-each support.

**Tech Stack:** Python 3.12+, pytest, Home Assistant entity reference patterns

---

## Task 1: Service Call Extraction - Basic Tests

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write test for service with data.entity_id**

Add to `tests/test_analyzer.py`:

```python
def test_extract_service_call_data_entity_id():
    """Test extraction from service call with data.entity_id."""
    automation = {
        "id": "turn_on_light",
        "alias": "Turn On Light",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "service": "light.turn_on",
                "data": {
                    "entity_id": "light.kitchen"
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract light.kitchen from service call
    service_refs = [r for r in refs if r.entity_id == "light.kitchen"]
    assert len(service_refs) == 1
    assert service_refs[0].location == "action[0].service.entity_id"
    assert service_refs[0].reference_type == "service_call"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_service_call_data_entity_id -v`

Expected: FAIL (service call extraction not implemented yet)

**Step 3: Write test for service with multiple entity_ids**

Add to `tests/test_analyzer.py`:

```python
def test_extract_service_call_multiple_entities():
    """Test extraction from service call with multiple entity_ids."""
    automation = {
        "id": "turn_on_lights",
        "alias": "Turn On Lights",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "service": "light.turn_on",
                "data": {
                    "entity_id": ["light.kitchen", "light.bedroom"]
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract both lights
    service_refs = [r for r in refs if "light." in r.entity_id]
    assert len(service_refs) == 2
    entity_ids = {r.entity_id for r in service_refs}
    assert "light.kitchen" in entity_ids
    assert "light.bedroom" in entity_ids
```

**Step 4: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_service_call_multiple_entities -v`

Expected: FAIL

**Step 5: Write test for service with target.entity_id**

Add to `tests/test_analyzer.py`:

```python
def test_extract_service_call_target_entity_id():
    """Test extraction from service call with target.entity_id."""
    automation = {
        "id": "turn_on_light",
        "alias": "Turn On Light",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "service": "light.turn_on",
                "target": {
                    "entity_id": "light.living_room"
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    service_refs = [r for r in refs if r.entity_id == "light.living_room"]
    assert len(service_refs) == 1
    assert service_refs[0].location == "action[0].service.entity_id"
    assert service_refs[0].reference_type == "service_call"
```

**Step 6: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_service_call_target_entity_id -v`

Expected: FAIL

**Step 7: Commit tests**

```bash
git add tests/test_analyzer.py
git commit -m "test: add service call extraction tests"
```

---

## Task 2: Service Call Extraction - Implementation

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`

**Step 1: Add _extract_from_service_call method**

Add method to `AutomationAnalyzer` class in `custom_components/autodoctor/analyzer.py` (after `_extract_from_template` method, around line 432):

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

**Step 2: Call _extract_from_service_call from _extract_from_actions**

Modify `_extract_from_actions` method in `custom_components/autodoctor/analyzer.py` (around line 445):

Find this section:
```python
for idx, action in enumerate(actions):
    # Extract from choose option conditions and sequences
```

Add BEFORE the existing `# Extract from choose option conditions`:
```python
for idx, action in enumerate(actions):
    # Extract from service calls
    refs.extend(
        self._extract_from_service_call(
            action, idx, automation_id, automation_name
        )
    )

    # Extract from choose option conditions and sequences
```

**Step 3: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_service_call_data_entity_id tests/test_analyzer.py::test_extract_service_call_multiple_entities tests/test_analyzer.py::test_extract_service_call_target_entity_id -v`

Expected: PASS (all 3 tests)

**Step 4: Run all tests to check for regressions**

Run: `pytest tests/test_analyzer.py -v`

Expected: All tests PASS

**Step 5: Commit implementation**

```bash
git add custom_components/autodoctor/analyzer.py
git commit -m "feat: extract entity references from service calls"
```

---

## Task 3: Scene and Script Detection - Tests

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write test for scene.turn_on**

Add to `tests/test_analyzer.py`:

```python
def test_extract_scene_turn_on():
    """Test extraction from scene.turn_on service."""
    automation = {
        "id": "activate_scene",
        "alias": "Activate Scene",
        "trigger": [{"platform": "time", "at": "20:00:00"}],
        "action": [
            {
                "service": "scene.turn_on",
                "target": {
                    "entity_id": "scene.movie_time"
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    scene_refs = [r for r in refs if r.entity_id == "scene.movie_time"]
    assert len(scene_refs) == 1
    assert scene_refs[0].reference_type == "scene"
```

**Step 2: Write test for script.turn_on**

Add to `tests/test_analyzer.py`:

```python
def test_extract_script_turn_on():
    """Test extraction from script.turn_on service."""
    automation = {
        "id": "run_script",
        "alias": "Run Script",
        "trigger": [{"platform": "time", "at": "22:00:00"}],
        "action": [
            {
                "service": "script.turn_on",
                "target": {
                    "entity_id": "script.bedtime_routine"
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    script_refs = [r for r in refs if r.entity_id == "script.bedtime_routine"]
    assert len(script_refs) == 1
    assert script_refs[0].reference_type == "script"
```

**Step 3: Write test for script shorthand**

Add to `tests/test_analyzer.py`:

```python
def test_extract_script_shorthand():
    """Test extraction from shorthand script call."""
    automation = {
        "id": "run_script_shorthand",
        "alias": "Run Script Shorthand",
        "trigger": [{"platform": "time", "at": "22:00:00"}],
        "action": [
            {
                "service": "script.bedtime_routine"
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    script_refs = [r for r in refs if r.entity_id == "script.bedtime_routine"]
    assert len(script_refs) == 1
    assert script_refs[0].reference_type == "script"
    assert script_refs[0].location == "action[0].service"
```

**Step 4: Write test for script meta-service (should not extract)**

Add to `tests/test_analyzer.py`:

```python
def test_script_meta_service_not_extracted():
    """Test that script meta-services are not extracted as entities."""
    automation = {
        "id": "reload_scripts",
        "alias": "Reload Scripts",
        "trigger": [{"platform": "time", "at": "00:00:00"}],
        "action": [
            {"service": "script.reload"},
            {"service": "script.turn_off", "data": {"entity_id": "script.test"}},
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should only extract script.test from turn_off data, not reload
    script_refs = [r for r in refs if "script." in r.entity_id]
    assert len(script_refs) == 1
    assert script_refs[0].entity_id == "script.test"
```

**Step 5: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_scene_turn_on tests/test_analyzer.py::test_extract_script_turn_on tests/test_analyzer.py::test_extract_script_shorthand tests/test_analyzer.py::test_script_meta_service_not_extracted -v`

Expected: First 3 PASS (scene/script reference_type already handled), last test FAIL (shorthand not implemented)

**Step 6: Commit tests**

```bash
git add tests/test_analyzer.py
git commit -m "test: add scene and script detection tests"
```

---

## Task 4: Script Shorthand Detection - Implementation

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`

**Step 1: Add shorthand script detection to _extract_from_service_call**

Modify `_extract_from_service_call` method in `custom_components/autodoctor/analyzer.py`.

Find this section (around line 440):
```python
# Get service name (both 'service' and 'action' keys)
service = action.get("service") or action.get("action")
if not service:
    return refs
```

Add AFTER the `if not service:` check:
```python
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
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_script_shorthand tests/test_analyzer.py::test_script_meta_service_not_extracted -v`

Expected: PASS (both tests)

**Step 3: Run all analyzer tests**

Run: `pytest tests/test_analyzer.py -v`

Expected: All tests PASS

**Step 4: Commit implementation**

```bash
git add custom_components/autodoctor/analyzer.py
git commit -m "feat: extract script references from shorthand syntax"
```

---

## Task 5: For-each Support - Tests

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write test for for-each with static list**

Add to `tests/test_analyzer.py`:

```python
def test_extract_for_each_static_list():
    """Test extraction from repeat.for_each with static entity list."""
    automation = {
        "id": "iterate_lights",
        "alias": "Iterate Lights",
        "trigger": [{"platform": "time", "at": "20:00:00"}],
        "action": [
            {
                "repeat": {
                    "for_each": ["light.kitchen", "light.bedroom", "light.living_room"],
                    "sequence": [
                        {
                            "service": "light.turn_on",
                            "target": {"entity_id": "{{ repeat.item }}"}
                        }
                    ]
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    for_each_refs = [r for r in refs if r.reference_type == "for_each"]
    assert len(for_each_refs) == 3
    entity_ids = {r.entity_id for r in for_each_refs}
    assert "light.kitchen" in entity_ids
    assert "light.bedroom" in entity_ids
    assert "light.living_room" in entity_ids
    assert all(r.location == "action[0].repeat.for_each" for r in for_each_refs)
```

**Step 2: Write test for for-each with template**

Add to `tests/test_analyzer.py`:

```python
def test_extract_for_each_template():
    """Test extraction from repeat.for_each with template."""
    automation = {
        "id": "iterate_group",
        "alias": "Iterate Group",
        "trigger": [{"platform": "time", "at": "20:00:00"}],
        "action": [
            {
                "repeat": {
                    "for_each": "{{ expand('group.all_lights') | map(attribute='entity_id') | list }}",
                    "sequence": [
                        {
                            "service": "light.turn_on",
                            "target": {"entity_id": "{{ repeat.item }}"}
                        }
                    ]
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract group.all_lights via expand() pattern
    group_refs = [r for r in refs if r.entity_id == "group.all_lights"]
    assert len(group_refs) == 1
    assert group_refs[0].reference_type == "group"
```

**Step 3: Write test for for-each with area_entities**

Add to `tests/test_analyzer.py`:

```python
def test_extract_for_each_area_entities():
    """Test extraction from repeat.for_each with area_entities."""
    automation = {
        "id": "iterate_area",
        "alias": "Iterate Area",
        "trigger": [{"platform": "time", "at": "20:00:00"}],
        "action": [
            {
                "repeat": {
                    "for_each": "{{ area_entities('bedroom') }}",
                    "sequence": [
                        {
                            "service": "homeassistant.turn_off",
                            "target": {"entity_id": "{{ repeat.item }}"}
                        }
                    ]
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract bedroom via area_entities() pattern
    area_refs = [r for r in refs if r.entity_id == "bedroom"]
    assert len(area_refs) == 1
    assert area_refs[0].reference_type == "area"
```

**Step 4: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_for_each_static_list tests/test_analyzer.py::test_extract_for_each_template tests/test_analyzer.py::test_extract_for_each_area_entities -v`

Expected: FAIL (for-each extraction not implemented)

**Step 5: Commit tests**

```bash
git add tests/test_analyzer.py
git commit -m "test: add for-each iteration extraction tests"
```

---

## Task 6: For-each Support - Implementation

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`

**Step 1: Add for-each extraction to repeat handling**

Modify `_extract_from_actions` method in `custom_components/autodoctor/analyzer.py`.

Find the repeat handling section (around line 516):
```python
# Extract from repeat while/until conditions (all types, not just template)
elif "repeat" in action:
    repeat_config = action["repeat"]
```

Add AFTER `repeat_config = action["repeat"]`:
```python
# Extract from for_each
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
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_for_each_static_list tests/test_analyzer.py::test_extract_for_each_template tests/test_analyzer.py::test_extract_for_each_area_entities -v`

Expected: PASS (all 3 tests)

**Step 3: Run all analyzer tests**

Run: `pytest tests/test_analyzer.py -v`

Expected: All tests PASS

**Step 4: Commit implementation**

```bash
git add custom_components/autodoctor/analyzer.py
git commit -m "feat: extract entity references from for-each iterations"
```

---

## Task 7: Helper Functions - Regex Patterns

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`

**Step 1: Add regex patterns for helper functions**

Add to module-level patterns in `custom_components/autodoctor/analyzer.py` (after `INTEGRATION_ENTITIES_PATTERN`, around line 62):

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

**Step 2: Verify patterns compile**

Run: `python -c "import custom_components.autodoctor.analyzer"`

Expected: No errors

**Step 3: Commit patterns**

```bash
git add custom_components/autodoctor/analyzer.py
git commit -m "feat: add regex patterns for helper function extraction"
```

---

## Task 8: Helper Functions - Tests

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write test for device_id()**

Add to `tests/test_analyzer.py`:

```python
def test_extract_device_id_function():
    """Test extraction from device_id() function."""
    automation = {
        "id": "check_device",
        "alias": "Check Device",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ device_id('light.kitchen') == device_id('light.bedroom') }}"
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    device_id_refs = [r for r in refs if r.reference_type == "metadata"]
    assert len(device_id_refs) == 2
    entity_ids = {r.entity_id for r in device_id_refs}
    assert "light.kitchen" in entity_ids
    assert "light.bedroom" in entity_ids
```

**Step 2: Write test for area_name() and area_id()**

Add to `tests/test_analyzer.py`:

```python
def test_extract_area_name_and_id_functions():
    """Test extraction from area_name() and area_id() functions."""
    automation = {
        "id": "check_area",
        "alias": "Check Area",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ area_name('sensor.temperature') == 'Kitchen' and area_id('light.bedroom') == 'bedroom' }}"
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    area_refs = [r for r in refs if r.reference_type == "metadata"]
    assert len(area_refs) == 2
    entity_ids = {r.entity_id for r in area_refs}
    assert "sensor.temperature" in entity_ids
    assert "light.bedroom" in entity_ids
```

**Step 3: Write test for has_value()**

Add to `tests/test_analyzer.py`:

```python
def test_extract_has_value_function():
    """Test extraction from has_value() function."""
    automation = {
        "id": "check_value",
        "alias": "Check Value",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ has_value('sensor.temperature') }}"
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    has_value_refs = [r for r in refs if r.location.endswith(".has_value")]
    assert len(has_value_refs) == 1
    assert has_value_refs[0].entity_id == "sensor.temperature"
    assert has_value_refs[0].reference_type == "entity"
```

**Step 4: Write test for deduplication**

Add to `tests/test_analyzer.py`:

```python
def test_extract_deduplication_helper_functions():
    """Test that same entity via different patterns is deduplicated."""
    automation = {
        "id": "dedupe_test",
        "alias": "Dedupe Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ is_state('light.kitchen', 'on') and device_id('light.kitchen') }}"
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should only have 1 reference to light.kitchen (deduplicated)
    kitchen_refs = [r for r in refs if r.entity_id == "light.kitchen"]
    assert len(kitchen_refs) == 1
```

**Step 5: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_device_id_function tests/test_analyzer.py::test_extract_area_name_and_id_functions tests/test_analyzer.py::test_extract_has_value_function tests/test_analyzer.py::test_extract_deduplication_helper_functions -v`

Expected: FAIL (helper function extraction not implemented)

**Step 6: Commit tests**

```bash
git add tests/test_analyzer.py
git commit -m "test: add helper function extraction tests"
```

---

## Task 9: Helper Functions - Implementation

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`

**Step 1: Add helper function extraction to _extract_from_template**

Modify `_extract_from_template` method in `custom_components/autodoctor/analyzer.py`.

Find the end of the method (after `integration_entities()` extraction, around line 429):

Add BEFORE the `return refs` statement:

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

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_device_id_function tests/test_analyzer.py::test_extract_area_name_and_id_functions tests/test_analyzer.py::test_extract_has_value_function tests/test_analyzer.py::test_extract_deduplication_helper_functions -v`

Expected: PASS (all 4 tests)

**Step 3: Run all analyzer tests**

Run: `pytest tests/test_analyzer.py -v`

Expected: All tests PASS

**Step 4: Commit implementation**

```bash
git add custom_components/autodoctor/analyzer.py
git commit -m "feat: extract entity references from helper functions"
```

---

## Task 10: Integration Test

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write comprehensive integration test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_full_automation_with_all_patterns():
    """Test extraction from automation using all new patterns."""
    automation = {
        "id": "comprehensive_test",
        "alias": "Comprehensive Test",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "binary_sensor.motion",
                "to": "on",
            }
        ],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ has_value('sensor.temperature') }}"
            }
        ],
        "action": [
            {
                "service": "light.turn_on",
                "target": {
                    "entity_id": "light.kitchen"
                }
            },
            {
                "service": "script.bedtime_routine"
            },
            {
                "service": "scene.turn_on",
                "data": {
                    "entity_id": "scene.movie_time"
                }
            },
            {
                "repeat": {
                    "for_each": ["light.bedroom", "light.living_room"],
                    "sequence": [
                        {
                            "service": "light.turn_off",
                            "target": {"entity_id": "{{ repeat.item }}"}
                        }
                    ]
                }
            },
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Check each expected extraction
    # 1. State trigger
    assert any(r.entity_id == "binary_sensor.motion" and "trigger" in r.location for r in refs)

    # 2. has_value in condition
    assert any(r.entity_id == "sensor.temperature" for r in refs)

    # 3. Service call target
    service_refs = [r for r in refs if r.entity_id == "light.kitchen" and r.reference_type == "service_call"]
    assert len(service_refs) == 1

    # 4. Script shorthand
    script_refs = [r for r in refs if r.entity_id == "script.bedtime_routine" and r.reference_type == "script"]
    assert len(script_refs) == 1

    # 5. Scene
    scene_refs = [r for r in refs if r.entity_id == "scene.movie_time" and r.reference_type == "scene"]
    assert len(scene_refs) == 1

    # 6. For-each static list
    for_each_refs = [r for r in refs if r.reference_type == "for_each"]
    assert len(for_each_refs) == 2
    for_each_entities = {r.entity_id for r in for_each_refs}
    assert "light.bedroom" in for_each_entities
    assert "light.living_room" in for_each_entities
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py::test_extract_full_automation_with_all_patterns -v`

Expected: PASS

**Step 3: Run all analyzer tests for final verification**

Run: `pytest tests/test_analyzer.py -v`

Expected: All tests PASS

**Step 4: Commit integration test**

```bash
git add tests/test_analyzer.py
git commit -m "test: add comprehensive integration test for all extraction patterns"
```

---

## Task 11: Run Full Test Suite

**Files:**
- All test files

**Step 1: Run entire test suite**

Run: `pytest tests/ -v`

Expected: All tests PASS

**Step 2: Check test coverage**

Run: `pytest tests/test_analyzer.py --cov=custom_components.autodoctor.analyzer --cov-report=term-missing`

Expected: Coverage > 95% for analyzer.py

**Step 3: If coverage is low, identify gaps**

Review coverage report output to see which lines are not covered.

**Step 4: Run linting**

Run: `ruff check custom_components/autodoctor/analyzer.py`

Expected: No errors

**Step 5: Verify no regressions in other modules**

Run: `pytest tests/ -v`

Expected: All tests PASS

---

## Task 12: Update Documentation

**Files:**
- Modify: `docs/plans/2026-01-29-state-extraction-improvements-design.md`

**Step 1: Update design document status**

Change line 4 in `docs/plans/2026-01-29-state-extraction-improvements-design.md`:

From:
```markdown
**Status:** Design
```

To:
```markdown
**Status:** Implemented
```

**Step 2: Mark success criteria as complete**

Find the "Success Criteria" section (line 676) and mark all items as complete:

```markdown
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
```

**Step 3: Commit documentation update**

```bash
git add docs/plans/2026-01-29-state-extraction-improvements-design.md
git commit -m "docs: mark state extraction improvements as implemented"
```

---

## Verification Commands

After completing all tasks, run these commands to verify everything works:

```bash
# Run all tests
pytest tests/test_analyzer.py -v

# Check coverage
pytest tests/test_analyzer.py --cov=custom_components.autodoctor.analyzer --cov-report=term-missing

# Run linting
ruff check custom_components/autodoctor/

# Verify no import errors
python -c "from custom_components.autodoctor.analyzer import AutomationAnalyzer; print('Import successful')"
```

Expected results:
- All tests pass
- Coverage > 95%
- No linting errors
- Import successful

---

## Success Criteria

- [x] Service call entity extraction implemented and tested
- [x] Scene/script detection implemented and tested
- [x] For-each support implemented and tested
- [x] Helper functions (device_id, area_name, area_id, has_value) implemented and tested
- [x] Integration test covers all patterns
- [x] All existing tests pass (no regressions)
- [x] Test coverage > 95% for new code
- [x] Documentation updated

---

## Notes

**Reference Types Used:**
- `service_call` - Entity in service data/target
- `scene` - Scene entity
- `script` - Script entity
- `for_each` - Entity in for-each list
- `metadata` - Entity in device_id/area_name/area_id
- `entity` - Entity in has_value

**Deduplication:** The existing deduplication logic in `_extract_from_template` (checking `if not any(r.entity_id == entity_id for r in refs)`) prevents duplicate StateReferences when the same entity is referenced via multiple patterns.
