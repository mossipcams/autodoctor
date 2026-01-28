"""Binary sensor platform for Autodoctor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
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
    """Set up binary sensor entities."""
    async_add_entities([ValidationOkSensor(hass, entry)])


class ValidationOkSensor(BinarySensorEntity):
    """Binary sensor indicating if validation passed."""

    _attr_has_entity_name = True
    _attr_name = "Problems"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_validation_ok"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Autodoctor",
            manufacturer="Autodoctor",
            model="Automation Validator",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        """Return True if there are problems (issues > 0)."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            return len(reporter._active_issues) > 0
        return False
