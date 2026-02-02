"""Sensor platform for Autodoctor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VERSION


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
    _attr_name = "Issues"
    _attr_icon = "mdi:alert-circle"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_issues_count"
        self._attr_native_value = 0
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Autodoctor",
            manufacturer="Autodoctor",
            model="Automation Validator",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int:
        """Return the issue count."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            # _active_issues is a frozenset, safe to read directly
            return len(reporter._active_issues)
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            # Take snapshot - frozenset is immutable so this is safe
            issues = reporter._active_issues
            return {"issue_ids": list(issues)}
        return {}
