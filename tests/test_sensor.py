"""Tests for Autodoctor sensor platform."""

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import IssueType, Severity, ValidationIssue
from custom_components.autodoctor.sensor import (
    RuntimeHealthAlertsSensor,
    ValidationIssuesSensor,
    async_setup_entry,
)


async def test_async_setup_entry_adds_entity(hass: HomeAssistant) -> None:
    """Test that async_setup_entry adds ValidationIssuesSensor to Home Assistant.

    Verifies that the sensor platform setup function correctly instantiates
    and registers a ValidationIssuesSensor entity with the async_add_entities callback.
    """
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    added = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert len(added) == 2
    assert isinstance(added[0], ValidationIssuesSensor)
    assert isinstance(added[1], RuntimeHealthAlertsSensor)


async def test_sensor_attributes(hass: HomeAssistant) -> None:
    """Test that ValidationIssuesSensor initializes with correct attributes.

    Verifies sensor name, icon, state class, entity name behavior, unique ID,
    initial native value, and device info are properly set during initialization.
    """
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    sensor = ValidationIssuesSensor(hass, entry)

    assert sensor._attr_name == "Issues"
    assert sensor._attr_icon == "mdi:alert-circle"
    assert sensor._attr_state_class == SensorStateClass.MEASUREMENT
    assert sensor._attr_has_entity_name is True
    assert sensor._attr_unique_id == "test_entry_id_issues_count"
    assert sensor._attr_native_value == 0
    assert sensor._attr_device_info is not None
    assert (DOMAIN, "test_entry_id") in sensor._attr_device_info["identifiers"]


async def test_native_value_with_issues(hass: HomeAssistant) -> None:
    """Test that native_value returns the count of active issues from reporter.

    Verifies the sensor correctly queries the reporter's active issues and
    returns the count as its state value for display in the UI.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset({"a", "b", "c"})
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    assert sensor.native_value == 3


async def test_native_value_no_reporter(hass: HomeAssistant) -> None:
    """Test that native_value returns 0 when reporter is unavailable.

    Ensures graceful degradation when the reporter hasn't been initialized yet
    or has been removed, preventing errors during startup or shutdown.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    hass.data[DOMAIN] = {}
    assert sensor.native_value == 0

    hass.data.pop(DOMAIN, None)
    assert sensor.native_value == 0


async def test_extra_state_attributes_with_issues(hass: HomeAssistant) -> None:
    """Test that extra_state_attributes includes issue IDs when issues exist.

    Verifies that users can access the list of specific issue IDs via sensor
    attributes for debugging or use in automations.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset({"issue_1", "issue_2"})
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    attrs = sensor.extra_state_attributes
    assert "issue_ids" in attrs
    assert set(attrs["issue_ids"]) == {"issue_1", "issue_2"}


async def test_extra_state_attributes_no_reporter(hass: HomeAssistant) -> None:
    """Test that extra_state_attributes returns empty dict when reporter unavailable.

    Ensures graceful behavior when the reporter hasn't been initialized yet,
    preventing AttributeError during Home Assistant startup.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    hass.data[DOMAIN] = {}
    assert sensor.extra_state_attributes == {}

    hass.data.pop(DOMAIN, None)
    assert sensor.extra_state_attributes == {}


async def test_runtime_health_sensor_reports_active_runtime_alerts(
    hass: HomeAssistant,
) -> None:
    """Runtime health sensor should expose active runtime alert metadata."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = RuntimeHealthAlertsSensor(hass, entry)

    mock_runtime_monitor = MagicMock()
    mock_runtime_monitor.get_active_runtime_alerts.return_value = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.kitchen",
            automation_name="Kitchen",
            entity_id="automation.kitchen",
            location="runtime.health.burst",
            message="Burst detected",
            issue_type=IssueType.RUNTIME_AUTOMATION_BURST,
        ),
        ValidationIssue(
            severity=Severity.WARNING,
            automation_id="automation.hallway",
            automation_name="Hallway",
            entity_id="automation.hallway",
            location="runtime.health.count",
            message="Count anomaly",
            issue_type=IssueType.RUNTIME_AUTOMATION_COUNT_ANOMALY,
        ),
    ]
    hass.data[DOMAIN] = {"runtime_monitor": mock_runtime_monitor}

    assert sensor.native_value == 2
    attrs = sensor.extra_state_attributes
    assert len(attrs["active_runtime_alerts"]) == 2
    assert attrs["active_runtime_alerts"][0]["issue_type"] == "runtime_automation_burst"
