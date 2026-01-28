# Smart Conflict Detection: Condition Tracking Design

## Problem

The `EntityAction.conditions` field exists but is always empty. Actions inside `choose`, `if/then/else`, and `repeat` blocks have conditions that gate their execution, but this context is discarded. This causes false positive conflicts when two automations affect the same entity but under mutually exclusive conditions.

## Solution

Propagate conditions from parent blocks to nested actions, then use those conditions during conflict detection to eliminate false positives.

## Data Model Changes

### `models.py`

Update `EntityAction.conditions` from `list[str]` to `list[ConditionInfo]`:

```python
@dataclass
class EntityAction:
    """An action that affects an entity, extracted from an automation."""

    automation_id: str
    entity_id: str
    action: str  # "turn_on", "turn_off", "toggle", "set"
    value: Any  # For set actions (brightness, temperature, etc.)
    conditions: list[ConditionInfo]  # Conditions that must be true for this action to execute
```

Conditions accumulate through nesting:
```yaml
choose:
  - conditions: [A]
    sequence:
      - if:
          - B
        then:
          - service: light.turn_on  # conditions: [A, B]
```

## Analyzer Changes

### `analyzer.py`

Modify `_extract_actions_recursive()` to accept a `parent_conditions` parameter:

```python
def _extract_actions_recursive(
    self,
    actions: list[dict[str, Any]],
    parent_conditions: list[ConditionInfo] | None = None
) -> list[tuple[str, str, Any, list[ConditionInfo]]]:
```

Condition propagation logic:

1. **Choose blocks:** For each option, extract `ConditionInfo` from the option's conditions, append to `parent_conditions`, recurse into the sequence

2. **If blocks:** Extract `ConditionInfo` from the `if` conditions, append to `parent_conditions` for the `then` branch. For `else` branch, pass `parent_conditions` unchanged (can't represent "NOT condition")

3. **Repeat while/until:** Extract `ConditionInfo` from `while` or `until` conditions, append to `parent_conditions`

4. **Service calls:** Pass the accumulated `parent_conditions` when creating `EntityAction`

Reuse existing `_extract_from_condition()` logic to parse conditions into `ConditionInfo` objects.

## Conflict Detector Changes

### `conflict_detector.py`

When comparing two actions, combine automation-level and action-level conditions:

```python
combined_conditions1 = auto1_conditions + action1.conditions
combined_conditions2 = auto2_conditions + action2.conditions

if self._conditions_mutually_exclusive(combined_conditions1, combined_conditions2):
    # No conflict possible - skip
    continue
```

The existing `_conditions_mutually_exclusive()` logic already handles checking if any entity appears in both condition lists with disjoint state sets.

## Mutual Exclusivity Semantics

Two actions are mutually exclusive if **any** condition in their respective chains conflicts. This matches execution semantics - if any condition along the path is mutually exclusive, the actions can never both execute.

## Limitations

These are acceptable trade-offs for simplicity:

- **`else` branches:** Can't represent "NOT condition" - may produce some false positives
- **Template conditions:** Can't statically analyze `{{ states('sensor.x') }}` - treated as unknown
- **`or` conditions:** Current `ConditionInfo` assumes AND semantics
- **Non-state conditions:** Time, numeric_state, zone conditions not represented

## Files to Modify

1. `models.py` - Change `EntityAction.conditions` type
2. `analyzer.py` - Add `parent_conditions` parameter, propagate through recursion
3. `conflict_detector.py` - Combine automation + action conditions before checking exclusivity
4. `test_analyzer.py` - Add tests for condition propagation
5. `test_conflict_detector.py` - Add tests for action-level condition exclusivity

## Example

Before (false positive):
```
Automation A: turn_on light.kitchen when mode=night (inside choose block)
Automation B: turn_off light.kitchen when mode=day (inside choose block)
Result: CONFLICT flagged (incorrect)
```

After (correct):
```
Automation A: turn_on light.kitchen, conditions=[ConditionInfo("input_boolean.mode", {"night"})]
Automation B: turn_off light.kitchen, conditions=[ConditionInfo("input_boolean.mode", {"day"})]
Result: No conflict (conditions are mutually exclusive)
```
