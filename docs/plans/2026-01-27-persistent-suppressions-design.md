# Persistent Suppressions Design

## Problem

Users have no way to permanently suppress false positive issues. The current dismiss button is session-only and resets on page reload.

## Solution

Add persistent per-issue suppressions stored in Home Assistant's `.storage` directory.

### Suppression Key Format

```
{automation_id}:{entity_id}:{issue_type}
```

Example: `automation.morning_lights:binary_sensor.front_door:entity_not_found`

### Storage

File: `.storage/autodoctor.suppressions`

```json
{
  "version": 1,
  "data": {
    "suppressions": [
      "automation.morning_lights:binary_sensor.front_door:entity_not_found"
    ]
  }
}
```

### SuppressionStore Class

```python
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_KEY = "autodoctor.suppressions"
STORAGE_VERSION = 1

class SuppressionStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, list[str]]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._suppressions: set[str] = set()

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self._suppressions = set(data.get("suppressions", []))

    async def async_save(self) -> None:
        await self._store.async_save({"suppressions": list(self._suppressions)})

    def is_suppressed(self, key: str) -> bool:
        return key in self._suppressions

    async def async_suppress(self, key: str) -> None:
        self._suppressions.add(key)
        await self.async_save()

    async def async_clear_all(self) -> None:
        self._suppressions.clear()
        await self.async_save()

    @property
    def count(self) -> int:
        return len(self._suppressions)
```

### WebSocket API

**Filter suppressed issues:**
- All issue endpoints filter out suppressed issues
- Return `suppressed_count` in response

**New commands:**
- `autodoctor/suppress` - Add suppression (params: `automation_id`, `entity_id`, `issue_type`)
- `autodoctor/clear_suppressions` - Clear all suppressions

### Card UI

**Suppress button:** `⊘` icon next to each issue

**Suppressed badge:** Shows count with clear button
```
⊘ 3 ✕
```

## Files to Modify

| File | Changes |
|------|---------|
| `suppression_store.py` | NEW - SuppressionStore class |
| `models.py` | Add `get_suppression_key()` helper |
| `__init__.py` | Create store, load on startup |
| `websocket_api.py` | Filter issues, add suppress/clear commands |
| `autodoctor-card.ts` | Suppress button, badge, handlers, styles |

## Not Included

- Per-entity suppressions
- Per-automation suppressions
- Expiring suppressions
- Import/export
