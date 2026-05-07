"""Sensor platform for Autodoctor."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VERSION
from .models import Severity, ValidationIssue


def _validation_issue_list(value: Any) -> list[ValidationIssue]:
    """Return validation issues from an untyped Home Assistant data payload."""
    if not isinstance(value, list):
        return []
    return [
        issue for issue in cast(list[Any], value) if isinstance(issue, ValidationIssue)
    ]


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
        data = cast(dict[str, Any], self.hass.data.get(DOMAIN, {}))
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
        data = cast(dict[str, Any], self.hass.data.get(DOMAIN, {}))
        reporter = data.get("reporter")
        runtime_monitor = data.get("runtime_monitor")
        attrs: dict[str, Any] = {}

        validation_issues = data.get("validation_issues")
        if isinstance(validation_issues, list):
            issues = _validation_issue_list(validation_issues)
            raw_issues = data.get("validation_issues_raw")
            raw_issue_count = (
                len(raw_issues) if isinstance(raw_issues, list) else len(issues)
            )
            run_stats_obj: Any = data.get("validation_run_stats")
            run_stats = (
                cast(dict[str, Any], run_stats_obj)
                if isinstance(run_stats_obj, dict)
                else {}
            )

            attrs.update(
                {
                    "error_count": sum(
                        1 for issue in issues if issue.severity == Severity.ERROR
                    ),
                    "warning_count": sum(
                        1 for issue in issues if issue.severity == Severity.WARNING
                    ),
                    "info_count": sum(
                        1 for issue in issues if issue.severity == Severity.INFO
                    ),
                    "suppressed_count": max(0, raw_issue_count - len(issues)),
                    "last_run": data.get("validation_last_run"),
                    "analyzed_automations": int(
                        run_stats.get("analyzed_automations", 0)
                    ),
                    "failed_automations": int(run_stats.get("failed_automations", 0)),
                    "skip_reasons": run_stats.get("skip_reasons", {}),
                    "affected_automations": sorted(
                        {issue.automation_id for issue in issues}
                    ),
                    "top_issues": [
                        {
                            "automation_id": issue.automation_id,
                            "automation_name": issue.automation_name,
                            "entity_id": issue.entity_id,
                            "issue_type": (
                                issue.issue_type.value if issue.issue_type else None
                            ),
                            "severity": issue.severity.name.lower(),
                            "message": issue.message,
                            "location": issue.location,
                        }
                        for issue in issues[:5]
                    ],
                }
            )

            validation_groups_obj: Any = data.get("validation_groups")
            if isinstance(validation_groups_obj, dict):
                validation_groups = cast(dict[str, Any], validation_groups_obj)
                attrs["groups"] = {
                    str(group_id): _summarize_group(bucket)
                    for group_id, bucket in validation_groups.items()
                    if isinstance(bucket, dict)
                }

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
        data = cast(dict[str, Any], self.hass.data.get(DOMAIN, {}))
        runtime_monitor = data.get("runtime_monitor")
        if runtime_monitor:
            return len(runtime_monitor.get_active_runtime_alerts())
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return runtime alert metadata for diagnostics."""
        data = cast(dict[str, Any], self.hass.data.get(DOMAIN, {}))
        runtime_monitor = data.get("runtime_monitor")
        if not runtime_monitor:
            return {}

        runtime_alerts = cast(
            list[ValidationIssue],
            runtime_monitor.get_active_runtime_alerts(),
        )
        attrs: dict[str, Any] = {
            "error_count": sum(
                1 for issue in runtime_alerts if issue.severity == Severity.ERROR
            ),
            "warning_count": sum(
                1 for issue in runtime_alerts if issue.severity == Severity.WARNING
            ),
            "active_runtime_alerts": [
                {
                    "automation_id": issue.automation_id,
                    "issue_type": issue.issue_type.value if issue.issue_type else None,
                    "severity": issue.severity.name.lower(),
                    "message": issue.message,
                    "location": issue.location,
                }
                for issue in runtime_alerts
            ],
        }
        if hasattr(runtime_monitor, "get_last_run_stats"):
            stats_obj: Any = runtime_monitor.get_last_run_stats()
            if isinstance(stats_obj, dict):
                stats = cast(dict[str, Any], stats_obj)
                attrs["monitored_automations"] = int(stats.get("total_automations", 0))
                attrs["skip_reasons"] = {
                    str(key): int(value)
                    for key, value in stats.items()
                    if key
                    not in {
                        "total_automations",
                        "overactive_alerts",
                        "overdue_alerts",
                        "burst_alerts",
                    }
                    and isinstance(value, int)
                    and value > 0
                }
                attrs["runtime_detection_stats"] = {
                    str(key): int(value)
                    for key, value in stats.items()
                    if isinstance(value, int)
                }
        if hasattr(runtime_monitor, "get_runtime_state"):
            runtime_state_obj: Any = runtime_monitor.get_runtime_state()
            if isinstance(runtime_state_obj, dict):
                runtime_state = cast(dict[str, Any], runtime_state_obj)
                attrs["last_weekly_maintenance"] = runtime_state.get(
                    "last_weekly_maintenance"
                )
                alert_state_obj: Any = runtime_state.get("alerts")
                if isinstance(alert_state_obj, dict):
                    alert_state = cast(dict[str, Any], alert_state_obj)
                    attrs["runtime_alerts_today"] = int(
                        alert_state.get("global_count", 0)
                    )
        if hasattr(runtime_monitor, "get_event_store_diagnostics"):
            store_diag = runtime_monitor.get_event_store_diagnostics()
            if isinstance(store_diag, dict):
                attrs["runtime_event_store_degraded"] = store_diag["degraded"]
                attrs["runtime_event_store_pending_jobs"] = store_diag["pending_jobs"]
                attrs["runtime_event_store_write_failures"] = store_diag[
                    "write_failures"
                ]
                attrs["runtime_event_store_dropped_events"] = store_diag[
                    "dropped_events"
                ]
        return attrs


def _group_status(issues: list[ValidationIssue]) -> str:
    """Return a compact pass/warning/fail status for sensor attributes."""
    if any(issue.severity == Severity.ERROR for issue in issues):
        return "fail"
    if any(issue.severity == Severity.WARNING for issue in issues):
        return "warning"
    return "pass"


def _summarize_group(bucket: dict[str, Any]) -> dict[str, Any]:
    """Summarize one validation group for dashboard attributes."""
    raw_issues = bucket.get("issues", [])
    issues = _validation_issue_list(raw_issues)
    return {
        "status": _group_status(issues),
        "issue_count": len(issues),
        "error_count": sum(1 for issue in issues if issue.severity == Severity.ERROR),
        "warning_count": sum(
            1 for issue in issues if issue.severity == Severity.WARNING
        ),
        "duration_ms": int(bucket.get("duration_ms", 0)),
    }
