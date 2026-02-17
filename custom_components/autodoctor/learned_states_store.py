"""Persistent storage for learned states from user dismissals."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_KEY = "autodoctor.learned_states"
STORAGE_VERSION = 1


class LearnedStatesStore:
    """Persistent storage for learned states.

    Stores states that users have marked as valid by dismissing
    false positive validation issues. States are stored per
    domain and integration (platform).

    Structure:
        {
            "vacuum": {
                "roborock": ["segment_cleaning", "charging_error"],
                "ecovacs": ["auto_clean"]
            }
        }
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the learned states store."""
        self._hass = hass
        self._store: Store[dict[str, dict[str, list[str]]]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._learned: dict[str, dict[str, list[str]]] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load learned states from storage."""
        async with self._lock:
            data = await self._store.async_load()
            if data:
                self._learned = data

    async def _async_save(self) -> None:
        """Save learned states to storage.

        Note: Caller must hold _lock when calling this method.
        """
        await self._store.async_save(self._learned)

    def get_learned_states(self, domain: str, integration: str) -> set[str]:
        """Get learned states for a domain/integration combination.

        Args:
            domain: Entity domain (e.g., 'vacuum')
            integration: Integration/platform name (e.g., 'roborock')

        Returns:
            Set of learned state values

        Thread-safety:
            Uses atomic reference read to minimize race condition window with
            concurrent async_learn_state() calls. While not perfectly thread-safe,
            this pattern significantly reduces the risk of KeyError crashes by
            working with a consistent snapshot of the learned states dict.
        """
        # Atomic reference read - capture current state before any checks
        learned = self._learned
        if domain not in learned:
            return set()
        # Use .get() with default to safely handle concurrent modifications
        domain_data = learned.get(domain, {})
        return set(domain_data.get(integration, []))

    async def async_learn_state(
        self, domain: str, integration: str, state: str
    ) -> None:
        """Learn a state as valid for a domain/integration.

        Args:
            domain: Entity domain (e.g., 'vacuum')
            integration: Integration/platform name (e.g., 'roborock')
            state: The state value to learn
        """
        async with self._lock:
            if domain not in self._learned:
                self._learned[domain] = {}

            if integration not in self._learned[domain]:
                self._learned[domain][integration] = []

            if state not in self._learned[domain][integration]:
                self._learned[domain][integration].append(state)
                try:
                    await self._async_save()
                except Exception as err:
                    # Rollback the mutation on save failure to maintain consistency
                    # between in-memory state and persisted state
                    integration_states = self._learned[domain][integration]
                    integration_states.remove(state)
                    if not integration_states:
                        del self._learned[domain][integration]
                    if not self._learned[domain]:
                        del self._learned[domain]
                    _LOGGER.error(
                        "Failed to save learned state %s for %s.%s: %s",
                        state,
                        domain,
                        integration,
                        err,
                    )
                    raise
