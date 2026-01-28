# Smart Condition Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Propagate conditions from choose/if/repeat blocks to nested actions, then use those conditions during conflict detection to eliminate false positives.

**Architecture:** Modify `_extract_actions_recursive()` to accept and propagate `parent_conditions`, change `EntityAction.conditions` type from `list[str]` to `list[ConditionInfo]`, and combine action-level conditions with automation-level conditions in conflict checking.

**Tech Stack:** Python 3.14, pytest, Home Assistant automation YAML

---

### Task 1: Update EntityAction.conditions Type

**Files:**
- Modify: `custom_components/autodoctor/models.py:57`

**Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_entity_action_conditions_type():
    """Test that EntityAction.conditions accepts ConditionInfo objects."""
    from custom_components.autodoctor.models import EntityAction, ConditionInfo

    condition = ConditionInfo(entity_id="input_boolean.mode", required_states={"night"})
    action = EntityAction(
        automation_id="automation.test",
        entity_id="light.kitchen",
        action="turn_on",
        value=None,
        conditions=[condition],
    )

    assert len(action.conditions) == 1
    assert action.conditions[0].entity_id == "input_boolean.mode"
    assert action.conditions[0].required_states == {"night"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_entity_action_conditions_type -v`
Expected: FAIL (type mismatch or assertion error)

**Step 3: Update the type annotation**

In `custom_components/autodoctor/models.py`, change line 57 from:
```python
    conditions: list[str]  # Human-readable condition summary
```
to:
```python
    conditions: list[ConditionInfo]  # Conditions that must be true for this action
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py::test_entity_action_conditions_type -v`
Expected: PASS

**Step 5: Run all model tests**

Run: `pytest tests/test_models.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/models.py tests/test_models.py
git commit -m "refactor: change EntityAction.conditions type to list[ConditionInfo]"
```

---

### Task 2: Add Helper Method to Extract ConditionInfo from Condition Dict

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_condition_to_condition_info():
    """Test extraction of ConditionInfo from a condition dict."""
    analyzer = AutomationAnalyzer()

    # Explicit state condition
    condition = {
        "condition": "state",
        "entity_id": "input_boolean.mode",
        "state": "night",
    }
    result = analyzer._condition_to_condition_info(condition)
    assert result is not None
    assert result.entity_id == "input_boolean.mode"
    assert result.required_states == {"night"}


def test_condition_to_condition_info_implicit():
    """Test extraction of ConditionInfo from implicit condition (HA 2024+)."""
    analyzer = AutomationAnalyzer()

    # Implicit state condition (no "condition" key)
    condition = {
        "entity_id": "binary_sensor.motion",
        "state": "on",
    }
    result = analyzer._condition_to_condition_info(condition)
    assert result is not None
    assert result.entity_id == "binary_sensor.motion"
    assert result.required_states == {"on"}


def test_condition_to_condition_info_list_states():
    """Test extraction with list of states."""
    analyzer = AutomationAnalyzer()

    condition = {
        "condition": "state",
        "entity_id": "input_select.mode",
        "state": ["home", "away"],
    }
    result = analyzer._condition_to_condition_info(condition)
    assert result is not None
    assert result.required_states == {"home", "away"}


def test_condition_to_condition_info_template_returns_none():
    """Test that template conditions return None (can't extract ConditionInfo)."""
    analyzer = AutomationAnalyzer()

    condition = {
        "condition": "template",
        "value_template": "{{ is_state('sensor.x', 'on') }}",
    }
    result = analyzer._condition_to_condition_info(condition)
    assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_condition_to_condition_info -v`
Expected: FAIL (AttributeError: 'AutomationAnalyzer' object has no attribute '_condition_to_condition_info')

**Step 3: Implement the helper method**

Add to `custom_components/autodoctor/analyzer.py` after line 620 (before `_parse_service_call`):

```python
    def _condition_to_condition_info(
        self, condition: dict[str, Any] | str
    ) -> ConditionInfo | None:
        """Extract ConditionInfo from a condition dict if possible.

        Returns None for conditions that can't be represented as ConditionInfo
        (template conditions, time conditions, etc.).
        """
        if isinstance(condition, str):
            # Template shorthand - can't extract structured info
            return None

        if not isinstance(condition, dict):
            return None

        cond_type = condition.get("condition", "")

        # Handle state conditions (explicit or implicit)
        is_state_condition = cond_type == "state" or (
            not cond_type and "entity_id" in condition and "state" in condition
        )

        if not is_state_condition:
            return None

        entity_id = condition.get("entity_id")
        if not isinstance(entity_id, str):
            # Multiple entity_ids not supported for ConditionInfo
            return None

        states = self._normalize_states(condition.get("state"))
        if not states:
            return None

        return ConditionInfo(entity_id=entity_id, required_states=set(states))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_condition_to_condition_info tests/test_analyzer.py::test_condition_to_condition_info_implicit tests/test_analyzer.py::test_condition_to_condition_info_list_states tests/test_analyzer.py::test_condition_to_condition_info_template_returns_none -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat: add _condition_to_condition_info helper method"
```

---

### Task 3: Modify _extract_actions_recursive to Accept parent_conditions

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:464-511`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_entity_actions_with_choose_conditions():
    """Test that actions inside choose blocks inherit conditions."""
    from custom_components.autodoctor.models import ConditionInfo

    automation = {
        "id": "night_mode",
        "alias": "Night Mode",
        "trigger": [{"platform": "time", "at": "22:00:00"}],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "state",
                                "entity_id": "input_boolean.mode",
                                "state": "night",
                            }
                        ],
                        "sequence": [
                            {
                                "service": "light.turn_off",
                                "target": {"entity_id": "light.kitchen"},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].entity_id == "light.kitchen"
    assert len(actions[0].conditions) == 1
    assert actions[0].conditions[0].entity_id == "input_boolean.mode"
    assert actions[0].conditions[0].required_states == {"night"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_entity_actions_with_choose_conditions -v`
Expected: FAIL (conditions list is empty)

**Step 3: Modify _extract_actions_recursive signature and propagation**

In `custom_components/autodoctor/analyzer.py`, update `_extract_actions_recursive` (lines 464-511):

```python
    def _extract_actions_recursive(
        self,
        action_list: list[dict[str, Any]],
        automation_id: str,
        parent_conditions: list[ConditionInfo] | None = None,
    ) -> list[EntityAction]:
        """Recursively extract EntityActions from action blocks."""
        results: list[EntityAction] = []
        if parent_conditions is None:
            parent_conditions = []

        for action in action_list:
            if not isinstance(action, dict):
                continue

            # Direct service call (supports both "service" and "action" keys)
            if "service" in action or "action" in action:
                results.extend(self._parse_service_call(action, automation_id, parent_conditions))

            # Choose block
            if "choose" in action:
                for option in action.get("choose", []):
                    # Extract conditions from this option
                    option_conditions = list(parent_conditions)
                    for cond in option.get("conditions", []):
                        cond_info = self._condition_to_condition_info(cond)
                        if cond_info:
                            option_conditions.append(cond_info)

                    sequence = option.get("sequence", [])
                    results.extend(self._extract_actions_recursive(sequence, automation_id, option_conditions))

                # Default has no additional conditions
                default = action.get("default", [])
                if default:
                    results.extend(self._extract_actions_recursive(default, automation_id, parent_conditions))

            # If/then/else block
            if "if" in action:
                # Extract conditions from if
                if_conditions = list(parent_conditions)
                for cond in action.get("if", []):
                    cond_info = self._condition_to_condition_info(cond)
                    if cond_info:
                        if_conditions.append(cond_info)

                then_actions = action.get("then", [])
                else_actions = action.get("else", [])
                results.extend(self._extract_actions_recursive(then_actions, automation_id, if_conditions))
                # Else branch: can't represent NOT condition, pass parent unchanged
                if else_actions:
                    results.extend(self._extract_actions_recursive(else_actions, automation_id, parent_conditions))

            # Repeat block
            if "repeat" in action:
                repeat_config = action["repeat"]
                repeat_conditions = list(parent_conditions)

                # Extract while conditions
                for cond in repeat_config.get("while", []):
                    cond_info = self._condition_to_condition_info(cond)
                    if cond_info:
                        repeat_conditions.append(cond_info)

                # Extract until conditions
                for cond in repeat_config.get("until", []):
                    cond_info = self._condition_to_condition_info(cond)
                    if cond_info:
                        repeat_conditions.append(cond_info)

                sequence = repeat_config.get("sequence", [])
                results.extend(self._extract_actions_recursive(sequence, automation_id, repeat_conditions))

            # Parallel block
            if "parallel" in action:
                branches = action["parallel"]
                if not isinstance(branches, list):
                    branches = [branches]
                for branch in branches:
                    branch_actions = branch if isinstance(branch, list) else [branch]
                    results.extend(self._extract_actions_recursive(branch_actions, automation_id, parent_conditions))

        return results
```

**Step 4: Update _parse_service_call to accept and use parent_conditions**

Update the signature and body of `_parse_service_call` (lines 622-693):

```python
    def _parse_service_call(
        self,
        action: dict[str, Any],
        automation_id: str,
        parent_conditions: list[ConditionInfo] | None = None,
    ) -> list[EntityAction]:
        """Parse a service call action into EntityAction objects."""
        results: list[EntityAction] = []
        if parent_conditions is None:
            parent_conditions = []

        # Support both "service" (old format) and "action" (HA 2024+ format)
        service = action.get("service") or action.get("action", "")
        if not service or "." not in service:
            return results

        domain, service_name = service.split(".", 1)

        # Determine the action type
        if service_name in ("turn_on",):
            action_type = "turn_on"
        elif service_name in ("turn_off",):
            action_type = "turn_off"
        elif service_name in ("toggle",):
            action_type = "toggle"
        else:
            action_type = "set"

        # Extract entity IDs from target, entity_id, or data.entity_id
        entity_ids: list[str] = []

        target = action.get("target", {})
        if isinstance(target, dict):
            target_entities = target.get("entity_id", [])
            if isinstance(target_entities, str):
                entity_ids.append(target_entities)
            elif isinstance(target_entities, list):
                entity_ids.extend(target_entities)

        # Also check direct entity_id field
        direct_entity = action.get("entity_id")
        if direct_entity:
            if isinstance(direct_entity, str):
                entity_ids.append(direct_entity)
            elif isinstance(direct_entity, list):
                entity_ids.extend(direct_entity)

        # Also check data.entity_id (legacy format)
        data = action.get("data", {})
        if isinstance(data, dict):
            data_entity = data.get("entity_id")
            if data_entity:
                if isinstance(data_entity, str):
                    if data_entity not in entity_ids:
                        entity_ids.append(data_entity)
                elif isinstance(data_entity, list):
                    for eid in data_entity:
                        if eid not in entity_ids:
                            entity_ids.append(eid)

        # Get optional value for set actions
        value = action.get("data", {}) if action_type == "set" else None

        for entity_id in entity_ids:
            results.append(
                EntityAction(
                    automation_id=automation_id,
                    entity_id=entity_id,
                    action=action_type,
                    value=value,
                    conditions=list(parent_conditions),
                )
            )

        return results
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py::test_extract_entity_actions_with_choose_conditions -v`
Expected: PASS

**Step 6: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat: propagate conditions from choose blocks to actions"
```

---

### Task 4: Add Tests for If and Repeat Condition Propagation

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write the tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_entity_actions_with_if_conditions():
    """Test that actions inside if blocks inherit conditions."""
    from custom_components.autodoctor.models import ConditionInfo

    automation = {
        "id": "if_test",
        "alias": "If Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "if": [
                    {
                        "condition": "state",
                        "entity_id": "person.matt",
                        "state": "home",
                    }
                ],
                "then": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living_room"},
                    }
                ],
                "else": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.living_room"},
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 2

    # Then branch should have the condition
    then_action = next(a for a in actions if a.action == "turn_on")
    assert len(then_action.conditions) == 1
    assert then_action.conditions[0].entity_id == "person.matt"

    # Else branch should NOT have the condition (can't represent NOT)
    else_action = next(a for a in actions if a.action == "turn_off")
    assert len(else_action.conditions) == 0


def test_extract_entity_actions_with_repeat_while_conditions():
    """Test that actions inside repeat while blocks inherit conditions."""
    from custom_components.autodoctor.models import ConditionInfo

    automation = {
        "id": "repeat_test",
        "alias": "Repeat Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "repeat": {
                    "while": [
                        {
                            "condition": "state",
                            "entity_id": "binary_sensor.running",
                            "state": "on",
                        }
                    ],
                    "sequence": [
                        {
                            "service": "notify.mobile",
                            "target": {"entity_id": "notify.phone"},
                        }
                    ],
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert len(actions[0].conditions) == 1
    assert actions[0].conditions[0].entity_id == "binary_sensor.running"


def test_extract_entity_actions_nested_conditions_accumulate():
    """Test that nested conditions accumulate."""
    from custom_components.autodoctor.models import ConditionInfo

    automation = {
        "id": "nested_test",
        "alias": "Nested Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {"entity_id": "input_boolean.mode", "state": "night"}
                        ],
                        "sequence": [
                            {
                                "if": [
                                    {"entity_id": "person.matt", "state": "home"}
                                ],
                                "then": [
                                    {
                                        "service": "light.turn_on",
                                        "target": {"entity_id": "light.bedroom"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert len(actions[0].conditions) == 2

    entity_ids = {c.entity_id for c in actions[0].conditions}
    assert entity_ids == {"input_boolean.mode", "person.matt"}
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_entity_actions_with_if_conditions tests/test_analyzer.py::test_extract_entity_actions_with_repeat_while_conditions tests/test_analyzer.py::test_extract_entity_actions_nested_conditions_accumulate -v`
Expected: PASS (implementation from Task 3 should handle these)

**Step 3: Commit**

```bash
git add tests/test_analyzer.py
git commit -m "test: add tests for if/repeat condition propagation"
```

---

### Task 5: Update Conflict Detector to Use Action Conditions

**Files:**
- Modify: `custom_components/autodoctor/conflict_detector.py:76-110`
- Test: `tests/test_conflict_detector.py`

**Step 1: Write the failing test**

Add to `tests/test_conflict_detector.py`:

```python
class TestActionLevelConditions:
    """Test conflict detection with action-level conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = ConflictDetector()

    def test_no_conflict_with_mutually_exclusive_action_conditions(self):
        """Test that mutually exclusive action conditions prevent conflicts."""
        automations = [
            {
                "id": "night_on",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_boolean.mode", "state": "night"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_on", "target": {"entity_id": "light.living"}}
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "day_off",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_boolean.mode", "state": "day"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_off", "target": {"entity_id": "light.living"}}
                                ],
                            }
                        ],
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0

    def test_conflict_with_compatible_action_conditions(self):
        """Test that compatible action conditions still allow conflicts."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_boolean.mode", "state": "night"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_on", "target": {"entity_id": "light.living"}}
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_boolean.mode", "state": "night"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_off", "target": {"entity_id": "light.living"}}
                                ],
                            }
                        ],
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 1

    def test_combined_automation_and_action_conditions(self):
        """Test that automation-level and action-level conditions combine."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "condition": [{"condition": "state", "entity_id": "input_boolean.enabled", "state": "on"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_boolean.mode", "state": "night"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_on", "target": {"entity_id": "light.living"}}
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "condition": [{"condition": "state", "entity_id": "input_boolean.enabled", "state": "off"}],
                "action": [
                    {"service": "light.turn_off", "target": {"entity_id": "light.living"}}
                ],
            },
        ]
        # Automation-level conditions are mutually exclusive (enabled on vs off)
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_conflict_detector.py::TestActionLevelConditions -v`
Expected: FAIL (first test should fail because action conditions aren't being checked)

**Step 3: Update _check_conflict to combine conditions**

In `custom_components/autodoctor/conflict_detector.py`, update `_check_conflict` (lines 76-110):

```python
    def _check_conflict(
        self,
        entity_id: str,
        auto_id_a: str,
        action_a: EntityAction,
        data_a: AutomationData,
        auto_id_b: str,
        action_b: EntityAction,
        data_b: AutomationData,
    ) -> Conflict | None:
        """Check if two actions conflict."""
        # Only care about turn_on vs turn_off (skip toggle - too noisy)
        if {action_a.action, action_b.action} != {"turn_on", "turn_off"}:
            return None

        # Check if triggers can overlap
        if not self._triggers_can_overlap(data_a.triggers, data_b.triggers):
            return None

        # Combine automation-level and action-level conditions
        combined_conditions_a = data_a.conditions + action_a.conditions
        combined_conditions_b = data_b.conditions + action_b.conditions

        # Check if combined conditions are mutually exclusive
        if self._conditions_mutually_exclusive(combined_conditions_a, combined_conditions_b):
            return None

        return Conflict(
            entity_id=entity_id,
            automation_a=auto_id_a,
            automation_b=auto_id_b,
            automation_a_name=data_a.name,
            automation_b_name=data_b.name,
            action_a=action_a.action,
            action_b=action_b.action,
            severity=Severity.ERROR,
            explanation=f"Both automations can fire simultaneously with opposing actions on {entity_id}",
            scenario="May conflict when both triggers fire",
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_conflict_detector.py::TestActionLevelConditions -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/conflict_detector.py tests/test_conflict_detector.py
git commit -m "feat: combine action-level conditions in conflict detection"
```

---

### Task 6: Run Full Test Suite and Fix Any Regressions

**Files:**
- All modified files

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 2: Fix any failing tests**

If any tests fail due to the type change (e.g., tests that expected `conditions=[]` as strings), update them to use `ConditionInfo` or expect empty list.

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: update tests for new conditions type"
```

---

### Task 7: Final Integration Test

**Files:**
- Test: `tests/test_conflict_detector.py`

**Step 1: Add comprehensive integration test**

Add to `tests/test_conflict_detector.py`:

```python
    def test_real_world_scenario_mode_based_automation(self):
        """Test real-world scenario: mode-based automations don't conflict."""
        automations = [
            {
                "id": "morning_routine",
                "alias": "Morning Routine",
                "trigger": [{"platform": "time", "at": "07:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_select.house_mode", "state": "home"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_on", "target": {"entity_id": "light.kitchen"}},
                                    {"service": "light.turn_on", "target": {"entity_id": "light.living_room"}},
                                ],
                            },
                            {
                                "conditions": [
                                    {"condition": "state", "entity_id": "input_select.house_mode", "state": "away"}
                                ],
                                "sequence": [
                                    {"service": "light.turn_off", "target": {"entity_id": "light.kitchen"}},
                                    {"service": "light.turn_off", "target": {"entity_id": "light.living_room"}},
                                ],
                            },
                        ],
                    }
                ],
            },
        ]
        # Same automation with choose branches should not conflict with itself
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0
```

**Step 2: Run the test**

Run: `pytest tests/test_conflict_detector.py::TestActionLevelConditions::test_real_world_scenario_mode_based_automation -v`
Expected: PASS

**Step 3: Final commit**

```bash
git add tests/test_conflict_detector.py
git commit -m "test: add real-world integration test for mode-based automations"
```

---

### Summary

After completing all tasks:

1. `EntityAction.conditions` is now `list[ConditionInfo]`
2. `_extract_actions_recursive` propagates conditions through choose/if/repeat blocks
3. `_check_conflict` combines automation-level and action-level conditions
4. Full test coverage for the new functionality
