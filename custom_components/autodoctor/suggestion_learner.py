"""SuggestionLearner - learns from suppressed suggestions."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "autodoctor.suggestion_feedback"
STORAGE_VERSION = 1


class SuggestionLearner:
    """Learns from rejected suggestions to improve future recommendations."""

    def __init__(self) -> None:
        """Initialize the suggestion learner."""
        self._rejections: dict[tuple[str, str], int] = defaultdict(int)
        self._store: Store | None = None

    async def async_setup(self, hass: HomeAssistant) -> None:
        """Set up persistent storage."""
        from homeassistant.helpers.storage import Store

        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        data = await self._store.async_load()
        if data:
            self.from_dict(data)

    async def async_save(self) -> None:
        """Save to persistent storage."""
        if self._store:
            await self._store.async_save(self.to_dict())

    def record_rejection(self, from_entity: str, to_entity: str) -> None:
        """Record that a suggestion was rejected."""
        key = (from_entity, to_entity)
        self._rejections[key] += 1

    def get_rejection_count(self, from_entity: str, to_entity: str) -> int:
        """Get the number of times this suggestion was rejected."""
        return self._rejections.get((from_entity, to_entity), 0)

    def get_score_multiplier(self, from_entity: str, to_entity: str) -> float:
        """Get the score multiplier based on rejection history.

        Returns:
            1.0 for no rejections
            0.7 for 1 rejection (mild penalty)
            0.3 for 2+ rejections (heavy penalty)
        """
        count = self.get_rejection_count(from_entity, to_entity)

        if count == 0:
            return 1.0
        elif count == 1:
            return 0.7
        else:
            return 0.3

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "negative_pairs": [
                {"from": k[0], "to": k[1], "count": v}
                for k, v in self._rejections.items()
            ]
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore from dictionary."""
        self._rejections.clear()
        for pair in data.get("negative_pairs", []):
            key = (pair["from"], pair["to"])
            self._rejections[key] = pair["count"]
