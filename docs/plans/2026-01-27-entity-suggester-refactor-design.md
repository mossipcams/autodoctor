# Entity Suggester Refactor Design

## Problem

The current entity suggester produces poor suggestions. For example, `binary_sensor.frnt_door` suggests `binary_sensor.autodoctor_ok` - completely unrelated entities that only share the domain prefix.

The root cause: matching on the full entity ID (including domain) inflates similarity scores. Two unrelated entities in the same domain get ~50% similarity just from the `binary_sensor.` prefix, pushing garbage matches over the 0.6 threshold.

## Solution

### 1. Entity Suggestion Logic (validator.py + fix_engine.py)

**Current behavior:**
- Matches full entity ID string with 0.6 cutoff
- Suggests unrelated entities that share a domain prefix

**New behavior:**
- Split entity ID into domain + name
- Require exact domain match first
- Fuzzy match on name portion only with 0.75 cutoff
- Return `None` if no good match (no suggestion is better than a bad one)

```python
def _suggest_entity(self, invalid: str) -> str | None:
    if "." not in invalid:
        return None

    domain, name = invalid.split(".", 1)

    all_entities = self.knowledge_base.hass.states.async_all()
    same_domain = [
        e.entity_id for e in all_entities
        if e.entity_id.startswith(f"{domain}.")
    ]

    if not same_domain:
        return None

    names = {eid.split(".", 1)[1]: eid for eid in same_domain}
    matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

    return names[matches[0]] if matches else None
```

### 2. Dismiss Button (autodoctor-card.ts)

Add ability to dismiss unhelpful suggestions in the Lovelace card.

**State:**
```typescript
@state() private _dismissedSuggestions = new Set<string>();
```

**Key generation:**
```typescript
private _getSuggestionKey(issue: ValidationIssue): string {
  return `${issue.automation_id}:${issue.entity_id}:${issue.message}`;
}
```

**Behavior:**
- Session-only (resets on page reload)
- Small `✕` button in fix-suggestion row
- Clicking adds key to dismissed set, hides suggestion

## Files to Modify

| File | Change |
|------|--------|
| `custom_components/autodoctor/validator.py` | Refactor `_suggest_entity()` |
| `custom_components/autodoctor/fix_engine.py` | Refactor `_suggest_entity_fix()` |
| `www/autodoctor/autodoctor-card.ts` | Add dismiss state + button + styles |

## Examples

| Input | Before | After |
|-------|--------|-------|
| `binary_sensor.frnt_door` | `binary_sensor.autodoctor_ok` | `binary_sensor.front_door` (if exists) or `None` |
| `light.offce` | `switch.office_lamp` | `light.office` (if exists) or `None` |
| `sensor.xyz123` | random similar string | `None` |

## Not Included

- Cross-domain suggestions
- Multiple suggestions (just top match or nothing)
- Persistent dismissals (localStorage or server-side)
- Shared helper function between validator/fix_engine
