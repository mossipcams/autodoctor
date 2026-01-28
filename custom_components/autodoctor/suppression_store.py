"""Persistent storage for suppressed issues."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_KEY = "autodoctor.suppressions"
STORAGE_VERSION = 1


class SuppressionStore:
    """Persistent storage for suppressed issues."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the suppression store."""
        self._store: Store[dict[str, list[str]]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._suppressions: set[str] = set()

    async def async_load(self) -> None:
        """Load suppressions from storage."""
        data = await self._store.async_load()
        if data:
            self._suppressions = set(data.get("suppressions", []))

    async def async_save(self) -> None:
        """Save suppressions to storage."""
        await self._store.async_save({"suppressions": list(self._suppressions)})

    def is_suppressed(self, key: str) -> bool:
        """Check if an issue is suppressed."""
        return key in self._suppressions

    async def async_suppress(self, key: str) -> None:
        """Add a suppression."""
        self._suppressions.add(key)
        await self.async_save()

    async def async_clear_all(self) -> None:
        """Clear all suppressions."""
        self._suppressions.clear()
        await self.async_save()

    @property
    def count(self) -> int:
        """Return number of suppressions."""
        return len(self._suppressions)
