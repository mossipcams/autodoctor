"""Sensor platform for Autodoctor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    async_add_entities([ValidationIssuesSensor(hass, entry)])


class ValidationIssuesSensor(SensorEntity):
    """Sensor showing count of validation issues."""

    _attr_has_entity_name = True
    _attr_name = "Autodoctor Issues"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_issues_count"
        self._attr_native_value = 0

    @property
    def native_value(self) -> int:
        """Return the issue count."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            return len(reporter._active_issues)
        return 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            return {"issue_ids": list(reporter._active_issues)}
        return {}
