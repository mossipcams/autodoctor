# Autodoctor MVP Refactor Plan

## Overview

Refactor autodoctor to focus on core value: validating automation state references and detecting real conflicts. Remove over-engineered features that add complexity without proportional value.

### Target Metrics

| Metric | Before | After |
|--------|--------|-------|
| Python files | 15 | 11 |
| Lines of code | ~3,500 | ~1,500 |
| Features | 7 | 3 (validation, suggestions, conflicts) |
| False positive rate | High | Low |

### Core Features (Keep)

1. **State Validation** - Entity not found, invalid states, case mismatches
2. **Knowledge Base** - 3-tier approach (device class → schema → history)
3. **Smart Suggestions** - Synonym table + fuzzy matching
4. **Conflict Detection** - Rewritten with trigger overlap awareness

### Features to Remove

- Simulator/outcome verification (misleading, trivial checks)
- Entity graph (only serves over-built scoring)
- Suggestion learner (over-engineered)
- Staleness warnings (false positive generator)
- Complex relationship scoring in fix engine

---

## Phase 1: Delete Dead Code

| Task | File | Action |
|------|------|--------|
| 1.1 | `simulator.py` | Delete entire file |
| 1.2 | `entity_graph.py` | Delete entire file |
| 1.3 | `suggestion_learner.py` | Delete entire file |
| 1.4 | `suppression_store.py` | Keep (still needed for dismissing issues) |
| 1.5 | `__init__.py` | Remove imports and references to deleted modules |
| 1.6 | `__init__.py` | Remove `simulate` service registration |
| 1.7 | `websocket_api.py` | Remove `/outcomes` endpoint and handler |
| 1.8 | `www/autodoctor-card.js` | Remove "Outcomes" tab entirely |

---

## Phase 2: Simplify Knowledge Base

| Task | File | Action |
|------|------|--------|
| 2.1 | `knowledge_base.py` | Remove `_last_seen` dict and all staleness tracking |
| 2.2 | `knowledge_base.py` | Remove `get_state_last_seen()` method |
| 2.3 | `validator.py` | Remove `_check_staleness()` method |
| 2.4 | `validator.py` | Remove `staleness_threshold_days` parameter and logic |
| 2.5 | `config_flow.py` | Remove staleness threshold configuration option |
| 2.6 | `const.py` | Remove `CONF_STALENESS_THRESHOLD` constant |

---

## Phase 3: Simplify Fix Engine

| Task | File | Action |
|------|------|--------|
| 3.1 | `fix_engine.py` | Keep only `STATE_SYNONYMS` dict (lines 25-42) |
| 3.2 | `fix_engine.py` | Keep `get_state_suggestion()` with synonym lookup + `difflib.get_close_matches()` |
| 3.3 | `fix_engine.py` | Remove `FixEngine` class entirely |
| 3.4 | `fix_engine.py` | Remove relationship scoring logic |
| 3.5 | `fix_engine.py` | Remove entity graph integration |
| 3.6 | `fix_engine.py` | Target: ~50 lines (simple module with synonym table + fuzzy match function) |

---

## Phase 4: Rewrite Conflict Detector

| Task | File | Action |
|------|------|--------|
| 4.1 | `models.py` | Add `TriggerInfo` dataclass with fields: `trigger_type`, `entity_id`, `to_states`, `time_value`, `sun_event` |
| 4.2 | `models.py` | Add `ConditionInfo` dataclass with fields: `entity_id`, `required_states` |
| 4.3 | `analyzer.py` | Add `extract_triggers(automation) -> list[TriggerInfo]` method |
| 4.4 | `analyzer.py` | Add `extract_conditions(automation) -> list[ConditionInfo]` method |
| 4.5 | `conflict_detector.py` | Rewrite `ConflictDetector` class |
| 4.6 | `conflict_detector.py` | Add `_triggers_can_overlap(a: TriggerInfo, b: TriggerInfo) -> bool` |
| 4.7 | `conflict_detector.py` | Add `_conditions_mutually_exclusive(a: list[ConditionInfo], b: list[ConditionInfo]) -> bool` |
| 4.8 | `conflict_detector.py` | Modify `_check_conflict()` to only flag when triggers overlap AND conditions don't exclude |
| 4.9 | `conflict_detector.py` | Remove toggle conflict warnings (too noisy) |

### Conflict Detection Logic

**Mutual exclusivity rules:**

| Trigger Type | Rule |
|--------------|------|
| Same entity, different `to:` states | `to: on` vs `to: off` → mutually exclusive |
| Same entity, one has `to:`, other doesn't | Potentially overlapping (conservative) |
| Different entities | Potentially overlapping (conservative) |
| Specific times | `"06:00:00"` vs `"22:00:00"` → mutually exclusive |
| Sun events | `sunrise` vs `sunset` → mutually exclusive |
| Periodic/template triggers | Assume potentially overlapping |

**Condition check:** If both automations have a condition on the same entity requiring different states → mutually exclusive.

---

## Phase 5: Simplify Analyzer

| Task | File | Action |
|------|------|--------|
| 5.1 | `analyzer.py` | Keep `extract_state_references()` as-is |
| 5.2 | `analyzer.py` | Keep `extract_entity_actions()` as-is (needed for conflict detection) |
| 5.3 | `analyzer.py` | Keep template parsing regexes as-is |
| 5.4 | `analyzer.py` | Remove `check_trigger_condition_compatibility()` (folded into conflict detector) |

---

## Phase 6: Simplify Reporter

| Task | File | Action |
|------|------|--------|
| 6.1 | `reporter.py` | Keep only HA Repairs integration |
| 6.2 | `reporter.py` | Remove persistent notification channel (redundant) |
| 6.3 | `reporter.py` | Simplify to single reporting path |

---

## Phase 7: Simplify WebSocket API

| Task | File | Action |
|------|------|--------|
| 7.1 | `websocket_api.py` | Remove `handle_outcomes` handler |
| 7.2 | `websocket_api.py` | Remove `handle_run_outcomes` handler |
| 7.3 | `websocket_api.py` | Keep `handle_validation`, `handle_conflicts`, `handle_suppress` |
| 7.4 | `websocket_api.py` | Simplify suggestion generation to use new simple fix_engine |

---

## Phase 8: Update Tests

| Task | File | Action |
|------|------|--------|
| 8.1 | `tests/test_simulator.py` | Delete entire file |
| 8.2 | `tests/test_entity_graph.py` | Delete entire file |
| 8.3 | `tests/test_suggestion_learner.py` | Delete entire file |
| 8.4 | `tests/test_conflict_detector.py` | Rewrite tests for new overlap-aware logic |
| 8.5 | `tests/test_conflict_detector.py` | Add test: same trigger, opposing actions → conflict |
| 8.6 | `tests/test_conflict_detector.py` | Add test: sunrise vs sunset triggers → no conflict |
| 8.7 | `tests/test_conflict_detector.py` | Add test: different specific times → no conflict |
| 8.8 | `tests/test_conflict_detector.py` | Add test: mutually exclusive conditions → no conflict |
| 8.9 | `tests/test_fix_engine.py` | Simplify to test synonym lookup + fuzzy match only |
| 8.10 | `tests/test_validator.py` | Remove staleness tests |

---

## Phase 9: Update Manifest & Docs

| Task | File | Action |
|------|------|--------|
| 9.1 | `README.md` | Remove "Outcome Verification" section |
| 9.2 | `README.md` | Update conflict detection description to explain overlap detection |
| 9.3 | `README.md` | Remove staleness threshold from configuration docs |
| 9.4 | `manifest.json` | Verify dependencies are still accurate |

---

## Reference: Conflict Detector Implementation

```python
# conflict_detector.py - target implementation

@dataclass
class TriggerInfo:
    """Simplified trigger representation."""
    trigger_type: str  # "state", "time", "sun", "other"
    entity_id: str | None
    to_states: set[str] | None
    time_value: str | None  # "06:00:00" or None
    sun_event: str | None   # "sunrise", "sunset", or None

@dataclass
class ConditionInfo:
    """Simplified condition representation."""
    entity_id: str
    required_states: set[str]

@dataclass
class AutomationData:
    """Extracted automation data for conflict detection."""
    triggers: list[TriggerInfo]
    conditions: list[ConditionInfo]
    actions: list[EntityAction]


class ConflictDetector:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.analyzer = AutomationAnalyzer()

    def detect_conflicts(self, automations: list[dict]) -> list[Conflict]:
        # 1. Build per-automation data
        auto_data: dict[str, AutomationData] = {}
        for auto in automations:
            auto_id = f"automation.{auto.get('id', 'unknown')}"
            auto_data[auto_id] = AutomationData(
                triggers=self.analyzer.extract_triggers(auto),
                conditions=self.analyzer.extract_conditions(auto),
                actions=self.analyzer.extract_entity_actions(auto),
            )

        # 2. Group actions by target entity
        actions_by_entity: dict[str, list[tuple[str, EntityAction]]] = {}
        for auto_id, data in auto_data.items():
            for action in data.actions:
                actions_by_entity.setdefault(action.entity_id, []).append((auto_id, action))

        # 3. Check each entity for conflicts
        conflicts = []
        for entity_id, action_list in actions_by_entity.items():
            for i, (auto_id_a, action_a) in enumerate(action_list):
                for auto_id_b, action_b in action_list[i+1:]:
                    if auto_id_a == auto_id_b:
                        continue
                    conflict = self._check_conflict(
                        entity_id,
                        auto_id_a, action_a, auto_data[auto_id_a],
                        auto_id_b, action_b, auto_data[auto_id_b],
                    )
                    if conflict:
                        conflicts.append(conflict)

        return conflicts

    def _check_conflict(self, entity_id, auto_id_a, action_a, data_a, auto_id_b, action_b, data_b) -> Conflict | None:
        # Only care about turn_on vs turn_off
        if {action_a.action, action_b.action} != {"turn_on", "turn_off"}:
            return None

        # Check if triggers can overlap
        if not self._triggers_can_overlap(data_a.triggers, data_b.triggers):
            return None

        # Check if conditions are mutually exclusive
        if self._conditions_mutually_exclusive(data_a.conditions, data_b.conditions):
            return None

        return Conflict(
            entity_id=entity_id,
            automation_a=auto_id_a,
            automation_b=auto_id_b,
            action_a=action_a.action,
            action_b=action_b.action,
            severity=Severity.ERROR,
            explanation=f"Both automations can fire simultaneously with opposing actions on {entity_id}",
        )

    def _triggers_can_overlap(self, triggers_a: list[TriggerInfo], triggers_b: list[TriggerInfo]) -> bool:
        # If ANY pair can overlap, return True (conservative)
        for ta in triggers_a:
            for tb in triggers_b:
                if self._trigger_pair_can_overlap(ta, tb):
                    return True
        return False

    def _trigger_pair_can_overlap(self, a: TriggerInfo, b: TriggerInfo) -> bool:
        # Same entity state triggers with disjoint to_states
        if a.trigger_type == "state" and b.trigger_type == "state":
            if a.entity_id == b.entity_id and a.to_states and b.to_states:
                if a.to_states.isdisjoint(b.to_states):
                    return False

        # Different specific times
        if a.trigger_type == "time" and b.trigger_type == "time":
            if a.time_value and b.time_value:
                if ":" in a.time_value and ":" in b.time_value:
                    if a.time_value != b.time_value:
                        return False

        # Different sun events
        if a.trigger_type == "sun" and b.trigger_type == "sun":
            if a.sun_event and b.sun_event and a.sun_event != b.sun_event:
                return False

        return True  # Conservative default

    def _conditions_mutually_exclusive(self, conds_a: list[ConditionInfo], conds_b: list[ConditionInfo]) -> bool:
        for ca in conds_a:
            for cb in conds_b:
                if ca.entity_id == cb.entity_id:
                    if ca.required_states.isdisjoint(cb.required_states):
                        return True
        return False
```

---

## Reference: Simplified Fix Engine

```python
# fix_engine.py - target implementation (~50 lines)

from difflib import get_close_matches

STATE_SYNONYMS: dict[str, str] = {
    # Common mistakes
    "away": "not_home",
    "home": "home",
    "true": "on",
    "false": "off",
    "yes": "on",
    "no": "off",
    "1": "on",
    "0": "off",
    "armed": "armed_away",
    "disarmed": "disarmed",
    # Cover states
    "open": "open",
    "closed": "closed",
    "opening": "opening",
    "closing": "closing",
    # Lock states
    "locked": "locked",
    "unlocked": "unlocked",
}


def get_state_suggestion(invalid_state: str, valid_states: set[str]) -> str | None:
    """Get a suggestion for an invalid state.

    Checks synonym table first, then falls back to fuzzy matching.
    """
    # Check synonym table
    normalized = invalid_state.lower().strip()
    if normalized in STATE_SYNONYMS:
        canonical = STATE_SYNONYMS[normalized]
        if canonical in valid_states:
            return canonical
        # Check case-insensitive match
        lower_map = {s.lower(): s for s in valid_states}
        if canonical.lower() in lower_map:
            return lower_map[canonical.lower()]

    # Fall back to fuzzy matching
    matches = get_close_matches(
        invalid_state.lower(),
        [s.lower() for s in valid_states],
        n=1,
        cutoff=0.6
    )
    if matches:
        lower_map = {s.lower(): s for s in valid_states}
        return lower_map.get(matches[0])

    return None


def get_entity_suggestion(invalid_entity: str, all_entities: list[str]) -> str | None:
    """Get a suggestion for an invalid entity ID."""
    if "." not in invalid_entity:
        return None

    domain, name = invalid_entity.split(".", 1)

    # Only consider entities in the same domain
    same_domain = [e for e in all_entities if e.startswith(f"{domain}.")]
    if not same_domain:
        return None

    # Match on name portion
    names = {eid.split(".", 1)[1]: eid for eid in same_domain}
    matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

    return names[matches[0]] if matches else None
```

---

## Known Limitations (Document in README)

### State Validation

Template parsing uses regex and cannot handle:
- Dynamic entity IDs: `is_state(trigger.entity_id, 'on')`
- Variables: `{% set entity = 'light.kitchen' %}{{ is_state(entity, 'on') }}`
- String concatenation: `is_state('light.' ~ room_name, 'on')`
- Expand/area helpers with dynamic references

### Conflict Detection

Conservative approach - may flag conflicts that aren't real issues:
- Different trigger entities are assumed to potentially overlap
- Template triggers are assumed to potentially overlap
- Periodic time triggers are assumed to potentially overlap

Will correctly identify non-conflicts for:
- Same entity with different `to:` states
- Specific time triggers at different times
- Sunrise vs sunset triggers
- Conditions requiring mutually exclusive states
