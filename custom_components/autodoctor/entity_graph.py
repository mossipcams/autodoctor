"""EntityGraph - queries entity relationships from HA registries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EntityGraph:
    """Provides entity relationship queries based on HA registries."""

    def __init__(self) -> None:
        """Initialize the entity graph."""
        self._entity_areas: dict[str, str | None] = {}
        self._entity_devices: dict[str, str | None] = {}
        self._entity_labels: dict[str, set[str]] = {}
        self._loaded = False

    async def async_load(self, hass: HomeAssistant) -> None:
        """Load entity relationships from HA registries."""
        try:
            from homeassistant.helpers import (
                entity_registry as er,
                device_registry as dr,
                area_registry as ar,
            )

            entity_registry = er.async_get(hass)
            device_registry = dr.async_get(hass)

            for entry in entity_registry.entities.values():
                entity_id = entry.entity_id

                # Get area (direct or via device)
                area_id = entry.area_id
                if not area_id and entry.device_id:
                    device = device_registry.async_get(entry.device_id)
                    if device:
                        area_id = device.area_id

                self._entity_areas[entity_id] = area_id
                self._entity_devices[entity_id] = entry.device_id
                self._entity_labels[entity_id] = set(entry.labels) if entry.labels else set()

            self._loaded = True
            _LOGGER.debug("EntityGraph loaded %d entities", len(self._entity_areas))

        except Exception as e:
            _LOGGER.warning("Failed to load entity graph: %s", e)

    def same_area(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are in the same area."""
        area_a = self._entity_areas.get(entity_a)
        area_b = self._entity_areas.get(entity_b)
        return area_a is not None and area_a == area_b

    def same_device(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are on the same device."""
        device_a = self._entity_devices.get(entity_a)
        device_b = self._entity_devices.get(entity_b)
        return device_a is not None and device_a == device_b

    def same_domain(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are in the same domain."""
        if "." not in entity_a or "." not in entity_b:
            return False
        return entity_a.split(".")[0] == entity_b.split(".")[0]

    def shared_labels(self, entity_a: str, entity_b: str) -> set[str]:
        """Get labels shared between two entities."""
        labels_a = self._entity_labels.get(entity_a, set())
        labels_b = self._entity_labels.get(entity_b, set())
        return labels_a & labels_b

    def relationship_score(self, reference: str, candidate: str) -> float:
        """Calculate a relationship score between two entities.

        Returns a score from 0.0 to 1.0 based on:
        - Same device: 0.4
        - Same area: 0.3
        - Same domain: 0.2
        - Shared labels: 0.1
        """
        score = 0.0

        if self.same_device(reference, candidate):
            score += 0.4

        if self.same_area(reference, candidate):
            score += 0.3

        if self.same_domain(reference, candidate):
            score += 0.2

        if self.shared_labels(reference, candidate):
            score += 0.1

        return score

    def get_area(self, entity_id: str) -> str | None:
        """Get the area for an entity."""
        return self._entity_areas.get(entity_id)

    def get_device(self, entity_id: str) -> str | None:
        """Get the device for an entity."""
        return self._entity_devices.get(entity_id)
