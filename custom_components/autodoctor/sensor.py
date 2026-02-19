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
    async_add_entities(
        [
            ValidationIssuesSensor(hass, entry),
            RuntimeHealthAlertsSensor(hass, entry),
        ]
    )


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
        validation_issues = data.get("validation_issues")
        if isinstance(validation_issues, list):
            return len(validation_issues)

        reporter = data.get("reporter")
        if reporter:
            # Backward compatibility fallback for older in-memory shape.
            return len(reporter.active_issues)
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        runtime_monitor = data.get("runtime_monitor")
        attrs: dict[str, Any] = {}
        if reporter:
            # Take snapshot - frozenset is immutable so this is safe
            issues = reporter.active_issues
            attrs["issue_ids"] = list(issues)

        if runtime_monitor:
            attrs["runtime_alert_count"] = len(
                runtime_monitor.get_active_runtime_alerts()
            )

        return attrs


class RuntimeHealthAlertsSensor(SensorEntity):
    """Sensor showing count of active runtime health alerts."""

    _attr_has_entity_name = True
    _attr_name = "Runtime Alerts"
    _attr_icon = "mdi:heart-pulse"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize runtime health alerts sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_runtime_alerts"
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
        """Return the active runtime alert count."""
        data = self.hass.data.get(DOMAIN, {})
        runtime_monitor = data.get("runtime_monitor")
        if runtime_monitor:
            return len(runtime_monitor.get_active_runtime_alerts())
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return runtime alert metadata for diagnostics."""
        data = self.hass.data.get(DOMAIN, {})
        runtime_monitor = data.get("runtime_monitor")
        if not runtime_monitor:
            return {}

        runtime_alerts = runtime_monitor.get_active_runtime_alerts()
        attrs: dict[str, Any] = {
            "active_runtime_alerts": [
                {
                    "automation_id": issue.automation_id,
                    "issue_type": issue.issue_type.value if issue.issue_type else None,
                    "severity": issue.severity.name.lower(),
                    "message": issue.message,
                    "location": issue.location,
                }
                for issue in runtime_alerts
            ]
        }
        if hasattr(runtime_monitor, "get_event_store_diagnostics"):
            store_diag = runtime_monitor.get_event_store_diagnostics()
            attrs["runtime_event_store_enabled"] = store_diag["enabled"]
            attrs["runtime_event_store_cutover"] = store_diag["cutover"]
            attrs["runtime_event_store_degraded"] = store_diag["degraded"]
            attrs["runtime_event_store_pending_jobs"] = store_diag["pending_jobs"]
            attrs["runtime_event_store_write_failures"] = store_diag["write_failures"]
            attrs["runtime_event_store_dropped_events"] = store_diag["dropped_events"]
        return attrs
