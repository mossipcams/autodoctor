"""Persistent storage for suppressed issues."""

from __future__ import annotations

import asyncio

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
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load suppressions from storage."""
        async with self._lock:
            data = await self._store.async_load()
            if data:
                self._suppressions = set(data.get("suppressions", []))

    async def async_save(self) -> None:
        """Save suppressions to storage.

        Note: Caller must hold _lock when calling this method.
        """
        await self._store.async_save({"suppressions": list(self._suppressions)})

    def is_suppressed(self, key: str) -> bool:
        """Check if an issue is suppressed."""
        # Reading from set is atomic in CPython, no lock needed
        return key in self._suppressions

    async def async_suppress(self, key: str) -> None:
        """Add a suppression."""
        async with self._lock:
            self._suppressions.add(key)
            await self.async_save()

    async def async_unsuppress(self, key: str) -> None:
        """Remove a single suppression by key."""
        async with self._lock:
            self._suppressions.discard(key)
            await self.async_save()

    async def async_clear_all(self) -> None:
        """Clear all suppressions."""
        async with self._lock:
            self._suppressions.clear()
            await self.async_save()

    @property
    def keys(self) -> frozenset[str]:
        """Return all suppression keys as an immutable snapshot."""
        return frozenset(self._suppressions)

    @property
    def count(self) -> int:
        """Return number of suppressions."""
        return len(self._suppressions)
