# Conflict Detection & Smart Suggestions Design

## Problem

AutoDoctor catches state validation issues, but misses two important categories:

1. **Conflicting automations** - Two automations that fight each other (one turns on, another turns off the same entity)
2. **Low-accuracy suggestions** - Current fuzzy matching suggests wrong entities because it only uses string similarity

## Solution

### Part 1: Conflict Detection

Build an Entity-Action Graph that analyzes all automations together to find opposing actions on shared entities.

#### Core Data Structures

```python
@dataclass
class EntityAction:
    automation_id: str
    entity_id: str
    action: str  # "turn_on", "turn_off", "toggle", "set"
    value: Any   # For set actions (brightness, temperature, etc.)
    conditions: list[str]  # Human-readable condition summary

@dataclass
class Conflict:
    entity_id: str
    automation_a: str
    automation_b: str
    action_a: str
    action_b: str
    severity: Severity  # ERROR for on/off, WARNING for set conflicts
    explanation: str
    scenario: str  # "Occurs when motion detected AND nobody_home"
```

#### Graph Construction

1. **Parse each automation** - Extend analyzer to extract service calls and target entities
2. **Build adjacency map** - `Dict[entity_id, List[EntityAction]]`
3. **Detect opposing pairs**:
   - `turn_on` vs `turn_off` → ERROR
   - `toggle` vs anything → WARNING
   - `set` with different values → WARNING

#### Condition Overlap Check (Phase 1)

Simple mutual exclusion: if automations require mutually exclusive states on the same entity, they can't conflict.

```python
def conditions_can_overlap(auto_a, auto_b) -> bool:
    # If any entity requires mutually exclusive states, return False
    return True  # Conservative default
```

### Part 2: Smart Suggester

Replace string-only fuzzy matching with relationship-aware scoring.

#### Entity Relationship Graph

Query Home Assistant registries for entity relationships:

```python
@dataclass
class EntityRelationships:
    entity_id: str
    device_id: str | None
    area_id: str | None
    labels: list[str]
    domain: str
    device_class: str | None
```

#### Relationship Scoring

```python
def relationship_score(reference: str, candidate: str, context: AutomationContext) -> float:
    score = 0.0
    if same_device(reference, candidate):
        score += 0.4
    if same_area(reference, candidate):
        score += 0.3
    if same_domain(reference, candidate):
        score += 0.2
    if shares_labels_with_context(candidate, context):
        score += 0.1
    return score

final_score = (
    fuzzy_string_score * 0.3 +
    relationship_score * 0.5 +
    service_compatibility * 0.2
)
```

Threshold: Only suggest if `final_score >= 0.6`.

#### Suppression-Based Learning

Learn from rejected suggestions to reduce repeat noise.

Storage: `.storage/autodoctor.suggestion_feedback`

```json
{
  "version": 1,
  "negative_pairs": [
    {"from": "sensor.kitchen_temp", "to": "sensor.kitchen_humidity", "count": 3}
  ]
}
```

```python
def adjust_score_from_learning(from_entity: str, to_entity: str, base_score: float) -> float:
    feedback = suggestion_learner.get_feedback(from_entity, to_entity)
    if feedback and feedback.rejection_count >= 2:
        return base_score * 0.3  # Heavy penalty
    if feedback and feedback.rejection_count == 1:
        return base_score * 0.7  # Mild penalty
    return base_score
```

## UI Integration

### Conflicts Tab

Add third tab to Lovelace card:

```
┌─────────────┬─────────────┬─────────────┐
│ Validation  │  Outcomes   │  Conflicts  │
└─────────────┴─────────────┴─────────────┘
```

Conflict display:

```
⚠️ Conflict: light.living_room

  motion_lights_on        →  turn_on
  away_mode_lights_off    →  turn_off

  Scenario: Motion detected while presence is "not_home"

  [Edit motion_lights_on]  [Edit away_mode_lights_off]  [⊘ Suppress]
```

### Improved Suggestions

Show confidence and reasoning:

```
Entity not found: sensor.livingroom_temp

  Suggestions:
  ✓ sensor.living_room_temperature (92%)
    └─ Same area, same device class
```

### WebSocket API

```
autodoctor/conflicts        - Get all conflicts
autodoctor/conflicts/run    - Run conflict detection
```

## Implementation Phases

### Phase 1: Static Conflict Detection (v1.2.0)

1. Create `conflict_detector.py` with `EntityActionGraph`
2. Extend `analyzer.py` to extract service calls
3. Implement opposing-action detection
4. Add "Conflicts" tab to Lovelace card
5. WebSocket endpoints for conflicts

### Phase 2: Smart Suggester (v1.2.0)

1. Create `entity_graph.py` to query HA registries
2. Refactor `fix_engine.py` to use relationship scoring
3. Create `suggestion_learner.py` for suppression learning
4. Update UI with confidence percentages
5. Raise suggestion threshold to 0.6

### Phase 3: Symbolic Condition Analysis (v1.3.0)

1. Parse condition blocks into logical expressions
2. Implement condition overlap detection
3. Add "Scenario" explanation to conflict reports
4. Handle common template patterns

## Files to Create/Modify

| File | Changes |
|------|---------|
| `conflict_detector.py` | NEW - EntityActionGraph, conflict detection |
| `entity_graph.py` | NEW - HA registry queries, relationship scoring |
| `suggestion_learner.py` | NEW - Suppression-based learning |
| `analyzer.py` | Extend to extract service calls |
| `fix_engine.py` | Refactor to use smart suggester |
| `websocket_api.py` | Add conflict endpoints |
| `autodoctor-card.ts` | Add Conflicts tab, confidence display |

## Edge Cases

| Case | Handling |
|------|----------|
| Automation with no actions | Skip in conflict analysis |
| Entity in multiple areas | Use primary area from registry |
| Template-based entity IDs | Mark as "unanalyzable" for Phase 1 |
| User has no areas configured | Fall back to string matching only |
| Circular conflicts (A→B→C→A) | Detect and report as group |

## Not Included

- Real-time conflict detection on automation save
- Auto-fix suggestions for conflicts
- Cross-automation condition suggestions
- Machine learning-based conflict prediction
