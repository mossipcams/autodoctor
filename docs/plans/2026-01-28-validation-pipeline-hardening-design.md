# Validation Pipeline Hardening Design

**Date:** 2026-01-28
**Status:** Draft
**Scope:** Critical path (analyzer → validator → reporter) + supporting modules

## Problem Statement

The validation pipeline lacks defensive error handling and has performance concerns:

1. **Silent failures** - Malformed automation configs crash validation with no user feedback
2. **Missing error handling** - No try/except in analyzer.py or validator.py
3. **Performance** - Repeated expensive operations (zone iteration, entity lookups) per entity
4. **Blocking calls** - `get_significant_states` blocks the event loop
5. **Bugs** - Null handling issues, unbounded recursion, duplicated code

## Fixes Overview

| # | Module | Type | Severity |
|---|--------|------|----------|
| 1 | analyzer.py | Bug fix | HIGH - Null entity_id crashes |
| 2 | analyzer.py | Error handling | HIGH - Malformed configs crash |
| 3 | analyzer.py | Safety | MEDIUM - Unbounded recursion |
| 4 | jinja_validator.py | Bug fix | HIGH - Unbounded recursion |
| 5 | jinja_validator.py | Bug fix | MEDIUM - Dict access without guard |
| 6 | validator.py | Error handling | MEDIUM - No exception handling |
| 7 | validator.py | Performance | MEDIUM - O(n) per invalid entity |
| 8 | knowledge_base.py | Performance | MEDIUM - Zone/area not cached |
| 9 | knowledge_base.py | Blocking call | MEDIUM - Blocks event loop |
| 10 | knowledge_base.py | Encapsulation | LOW - Add public method |
| 11 | __init__.py | Error isolation | HIGH - One bad automation crashes all |
| 12 | __init__.py | Error handling | MEDIUM - Config extraction failures |
| 13 | websocket_api.py | Bug fix | MEDIUM - Duplicated logic |
| 14 | websocket_api.py | Error handling | MEDIUM - No handler error catching |
| 15 | websocket_api.py | Cleanup | LOW - Redundant data storage |
| 16 | reporter.py | Error handling | LOW - Delete loop failures |
| 17 | models.py | Bug fix | LOW - Hash/eq mismatch |

---

## Detailed Fixes

### Fix 1: Null entity_id handling (analyzer.py)

**Problem:** `trigger.get("entity_id", [])` returns `None` when key exists with null value, causing `TypeError` on iteration.

**Locations:**
- Line 116: trigger entity_id
- Line 149: numeric_state entity_id
- Line 213: condition entity_id
- Line 333: choose options
- Line 371: if conditions
- Line 455: parallel branches

**Fix:** Use `or []` pattern instead of default parameter.

```python
# Before
entity_ids = trigger.get("entity_id", [])

# After
entity_ids = trigger.get("entity_id") or []
```

Also apply to:
```python
# Choose/parallel blocks
options = action.get("choose") or []
branches = action.get("parallel") or []
default = action.get("default") or []
```

---

### Fix 2: Error handling in analyzer.py

**Problem:** Zero try/except - malformed configs crash validation.

**Approach:** Wrap each extraction method, log and skip bad data.

```python
def _extract_from_trigger(
    self,
    trigger: dict[str, Any],
    index: int,
    automation_id: str,
    automation_name: str,
) -> list[StateReference]:
    """Extract state references from a trigger."""
    refs: list[StateReference] = []

    # Guard: skip non-dict triggers
    if not isinstance(trigger, dict):
        _LOGGER.warning(
            "Skipping non-dict trigger in %s: %s",
            automation_id, type(trigger).__name__
        )
        return refs

    try:
        platform = trigger.get("platform") or trigger.get("trigger", "")
        # ... rest of extraction logic
    except Exception as err:
        _LOGGER.warning(
            "Error extracting from trigger[%d] in %s: %s",
            index, automation_id, err
        )

    return refs
```

**Apply to:**
- `_extract_from_trigger`
- `_extract_from_condition`
- `_extract_from_template`
- `_extract_from_actions`
- `_extract_actions_recursive`
- `_parse_service_call`

---

### Fix 3: Recursion depth limiting (analyzer.py)

**Problem:** `_extract_from_actions` and `_extract_actions_recursive` recurse without limit.

**Fix:** Add depth parameter with limit.

```python
MAX_RECURSION_DEPTH = 20

def _extract_from_actions(
    self,
    actions: list[dict[str, Any]],
    automation_id: str,
    automation_name: str,
    _depth: int = 0,
) -> list[StateReference]:
    """Recursively extract state references from actions."""
    refs: list[StateReference] = []

    if _depth > MAX_RECURSION_DEPTH:
        _LOGGER.warning(
            "Max recursion depth exceeded in %s, stopping extraction",
            automation_id
        )
        return refs

    # ... rest with _depth + 1 on recursive calls
```

Apply same pattern to `_extract_actions_recursive`.

---

### Fix 4: Recursion depth limiting (jinja_validator.py)

**Problem:** Same unbounded recursion in `_validate_condition` and `_validate_actions`.

**Fix:** Same pattern as Fix 3.

```python
MAX_RECURSION_DEPTH = 20

def _validate_condition(
    self,
    condition: Any,
    index: int,
    auto_id: str,
    auto_name: str,
    location_prefix: str,
    _depth: int = 0,
) -> list[ValidationIssue]:
    if _depth > MAX_RECURSION_DEPTH:
        _LOGGER.warning(
            "Max recursion depth exceeded in %s at %s",
            auto_id, location_prefix
        )
        return []

    # ... rest with _depth + 1 on recursive calls
```

---

### Fix 5: Type guards in jinja_validator.py

**Problem:** Direct dict access on `action["repeat"]` and `action["parallel"]` without checking type.

**Fix:** Add type guards.

```python
# Before (line 299)
if "repeat" in action:
    repeat_config = action["repeat"]
    sequence = repeat_config.get("sequence", [])

# After
if "repeat" in action:
    repeat_config = action.get("repeat")
    if not isinstance(repeat_config, dict):
        continue
    sequence = repeat_config.get("sequence") or []
```

Same for parallel blocks.

---

### Fix 6: Error handling in validator.py

**Problem:** No exception handling, direct HA state access.

**Fix:** Wrap validation methods.

```python
def validate_reference(self, ref: StateReference) -> list[ValidationIssue]:
    """Validate a single state reference."""
    issues: list[ValidationIssue] = []

    try:
        if not self.knowledge_base.entity_exists(ref.entity_id):
            # ... existing logic
            return issues

        if ref.expected_state is not None:
            issues.extend(self._validate_state(ref))

        if ref.expected_attribute is not None:
            issues.extend(self._validate_attribute(ref))

    except Exception as err:
        _LOGGER.warning(
            "Error validating %s in %s: %s",
            ref.entity_id, ref.automation_id, err
        )
        # Return empty - avoid false positives on errors

    return issues
```

---

### Fix 7: Cache entity suggestions (validator.py)

**Problem:** `_suggest_entity` calls `hass.states.async_all()` per invalid entity.

**Fix:** Cache entity list by domain at validation start.

```python
class ValidationEngine:
    def __init__(self, knowledge_base: StateKnowledgeBase) -> None:
        self.knowledge_base = knowledge_base
        self._entity_cache: dict[str, list[str]] | None = None

    def clear_cache(self) -> None:
        """Clear caches (call before each validation run)."""
        self._entity_cache = None

    def _ensure_entity_cache(self) -> None:
        """Build entity cache if not present."""
        if self._entity_cache is not None:
            return

        self._entity_cache = {}
        try:
            for entity in self.knowledge_base.hass.states.async_all():
                domain = entity.entity_id.split(".")[0]
                if domain not in self._entity_cache:
                    self._entity_cache[domain] = []
                self._entity_cache[domain].append(entity.entity_id)
        except Exception as err:
            _LOGGER.warning("Failed to build entity cache: %s", err)
            self._entity_cache = {}

    def _suggest_entity(self, invalid: str) -> str | None:
        if "." not in invalid:
            return None

        self._ensure_entity_cache()
        domain, name = invalid.split(".", 1)

        same_domain = self._entity_cache.get(domain, [])
        if not same_domain:
            return None

        names = {eid.split(".", 1)[1]: eid for eid in same_domain}
        matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

        return names[matches[0]] if matches else None
```

---

### Fix 8: Cache zone/area names (knowledge_base.py)

**Problem:** Zone and area iteration happens per-entity, not cached.

**Fix:** Cache zone and area names.

```python
class StateKnowledgeBase:
    def __init__(self, ...):
        # ... existing
        self._zone_names: set[str] | None = None
        self._area_names: set[str] | None = None

    def _get_zone_names(self) -> set[str]:
        """Get all zone names (cached)."""
        if self._zone_names is not None:
            return self._zone_names

        self._zone_names = set()
        try:
            for zone_state in self.hass.states.async_all("zone"):
                zone_name = zone_state.attributes.get(
                    "friendly_name", zone_state.entity_id.split(".")[1]
                )
                self._zone_names.add(zone_name)
        except Exception as err:
            _LOGGER.warning("Failed to load zone names: %s", err)

        return self._zone_names

    def _get_area_names(self) -> set[str]:
        """Get all area names (cached)."""
        if self._area_names is not None:
            return self._area_names

        self._area_names = set()
        try:
            area_registry = ar.async_get(self.hass)
            for area in area_registry.async_list_areas():
                self._area_names.add(area.name)
                self._area_names.add(area.name.lower())
        except Exception as err:
            _LOGGER.warning("Failed to load area names: %s", err)

        return self._area_names

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._zone_names = None
        self._area_names = None
```

Update `get_valid_states()` to use cached methods instead of inline iteration.

---

### Fix 9: Run get_significant_states in executor (knowledge_base.py)

**Problem:** `get_significant_states` is synchronous, blocks event loop.

**Fix:** Use `hass.async_add_executor_job`.

```python
async def async_load_history(self, entity_ids: list[str] | None = None) -> None:
    # ... setup code ...

    try:
        # Run blocking call in executor
        history = await self.hass.async_add_executor_job(
            get_significant_states,
            self.hass,
            start_time,
            end_time,
            entity_ids,
            None,  # filters
            True,  # include_start_time_state
            True,  # significant_changes_only
        )
    except Exception as err:
        _LOGGER.warning("Failed to load recorder history: %s", err)
        return

    # ... rest unchanged
```

---

### Fix 10: Add public history check method (knowledge_base.py)

**Problem:** `__init__.py` accesses private `_observed_states`.

**Fix:** Add public method.

```python
# knowledge_base.py
def has_history_loaded(self) -> bool:
    """Check if history has been loaded."""
    return bool(self._observed_states)
```

```python
# __init__.py - update line 362
if knowledge_base and not knowledge_base.has_history_loaded():
```

---

### Fix 11: Error isolation in async_validate_all (__init__.py)

**Problem:** One bad automation crashes entire validation.

**Fix:** Wrap each automation in try/except, continue on failure.

```python
async def async_validate_all(hass: HomeAssistant) -> list:
    # ... setup ...

    # Clear validator cache before each run
    validator.clear_cache()

    all_issues = []
    failed_automations = 0

    for automation in automations:
        auto_id = automation.get("id", "unknown")
        auto_name = automation.get("alias", auto_id)

        try:
            refs = analyzer.extract_state_references(automation)
            issues = validator.validate_all(refs)
            all_issues.extend(issues)
        except Exception as err:
            failed_automations += 1
            _LOGGER.warning(
                "Failed to validate automation '%s' (%s): %s",
                auto_name, auto_id, err
            )
            continue

    if failed_automations > 0:
        _LOGGER.warning(
            "Validation completed with %d failed automations (out of %d)",
            failed_automations, len(automations)
        )

    # ... rest unchanged
```

---

### Fix 12: Error handling in _get_automation_configs (__init__.py)

**Problem:** Entity iteration has no error handling.

**Fix:** Wrap entity access.

```python
def _get_automation_configs(hass: HomeAssistant) -> list[dict]:
    # ... existing dict handling ...

    if hasattr(automation_data, "entities"):
        configs = []
        skipped = 0
        for entity in automation_data.entities:
            try:
                if hasattr(entity, "raw_config") and entity.raw_config is not None:
                    configs.append(entity.raw_config)
            except Exception as err:
                skipped += 1
                entity_id = getattr(entity, "entity_id", "unknown")
                _LOGGER.warning(
                    "Failed to extract config from %s: %s", entity_id, err
                )

        if skipped > 0:
            _LOGGER.warning(
                "Skipped %d automations due to extraction errors", skipped
            )

        return configs
```

---

### Fix 13: Remove duplicated automation extraction (websocket_api.py)

**Problem:** `websocket_run_conflicts` duplicates logic from `_get_automation_configs`.

**Fix:** Import and use the shared function.

```python
# websocket_api.py
from . import _get_automation_configs

@websocket_api.async_response
async def websocket_run_conflicts(...):
    # ...

    # Use shared function instead of duplicating
    automations = _get_automation_configs(hass)

    # ...
```

---

### Fix 14: Error handling in WebSocket handlers (websocket_api.py)

**Problem:** Unhandled exceptions kill the WebSocket connection.

**Fix:** Wrap each handler in try/except.

```python
@websocket_api.async_response
async def websocket_run_validation(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run validation and return results."""
    try:
        from . import async_validate_all
        # ... existing logic ...
    except Exception as err:
        _LOGGER.exception("Error in websocket_run_validation: %s", err)
        connection.send_error(
            msg["id"], "validation_failed", f"Validation error: {err}"
        )
```

Apply to all handlers:
- `websocket_get_issues`
- `websocket_refresh`
- `websocket_get_validation`
- `websocket_run_validation`
- `websocket_get_conflicts`
- `websocket_run_conflicts`

---

### Fix 15: Remove redundant data storage (websocket_api.py)

**Problem:** Line 145 overwrites data already stored by `async_validate_all`.

**Fix:** Remove redundant assignment.

```python
# Before (line 144-145)
issues = await async_validate_all(hass)
hass.data[DOMAIN]["issues"] = issues  # Remove this line

# After
issues = await async_validate_all(hass)
# async_validate_all already stores to hass.data[DOMAIN]
```

---

### Fix 16: Error handling in _clear_resolved_issues (reporter.py)

**Problem:** One failed delete stops all remaining deletes.

**Fix:** Wrap each delete.

```python
def _clear_resolved_issues(self, current_ids: set[str]) -> None:
    """Clear issues that have been resolved."""
    resolved = self._active_issues - current_ids
    for issue_id in resolved:
        try:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        except Exception as err:
            _LOGGER.warning("Failed to delete issue %s: %s", issue_id, err)
```

---

### Fix 17: Fix ValidationIssue hash/eq (models.py)

**Problem:** `__hash__` uses 4 fields but default `__eq__` compares all fields.

**Fix:** Define `__eq__` to match `__hash__`.

```python
@dataclass
class ValidationIssue:
    # ... fields ...

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((self.automation_id, self.entity_id, self.location, self.message))

    def __eq__(self, other: object) -> bool:
        """Equality based on hash fields."""
        if not isinstance(other, ValidationIssue):
            return NotImplemented
        return (
            self.automation_id == other.automation_id
            and self.entity_id == other.entity_id
            and self.location == other.location
            and self.message == other.message
        )
```

---

## Implementation Order

1. **Phase 1 - Critical bugs** (Fixes 1, 4, 5, 11)
   - Null handling in analyzer.py
   - Recursion limits in jinja_validator.py
   - Type guards in jinja_validator.py
   - Error isolation in __init__.py

2. **Phase 2 - Error handling** (Fixes 2, 3, 6, 12, 14, 16)
   - Try/except in analyzer.py
   - Recursion limit in analyzer.py
   - Try/except in validator.py
   - Config extraction error handling
   - WebSocket handler error handling
   - Reporter delete error handling

3. **Phase 3 - Performance** (Fixes 7, 8, 9)
   - Entity suggestion caching
   - Zone/area caching
   - Executor for blocking call

4. **Phase 4 - Cleanup** (Fixes 10, 13, 15, 17)
   - Public history check method
   - Remove duplicated code
   - Remove redundant storage
   - Fix hash/eq mismatch

## Testing Strategy

- Existing tests should continue to pass
- Add tests for malformed configs (null entity_id, deeply nested actions)
- Add tests for error recovery (one bad automation doesn't crash all)
- Performance: no new async_all() calls in hot paths

## Rollback Plan

All changes are additive (try/except, caching). If issues arise:
- Caching can be disabled by always returning None from cache checks
- Error handling can be loosened by re-raising exceptions
