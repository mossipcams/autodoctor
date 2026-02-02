"""Tests for Autodoctor sensor platform."""

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.sensor import (
    ValidationIssuesSensor,
    async_setup_entry,
)
from custom_components.autodoctor.const import DOMAIN


async def test_async_setup_entry_adds_entity(hass: HomeAssistant):
    """async_setup_entry adds ValidationIssuesSensor."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    added = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert len(added) == 1
    assert isinstance(added[0], ValidationIssuesSensor)


async def test_sensor_attributes(hass: HomeAssistant):
    """ValidationIssuesSensor has correct class attributes."""
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


async def test_native_value_with_issues(hass: HomeAssistant):
    """native_value returns issue count from reporter."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset({"a", "b", "c"})
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    assert sensor.native_value == 3


async def test_native_value_no_reporter(hass: HomeAssistant):
    """native_value returns 0 when no reporter available."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    hass.data[DOMAIN] = {}
    assert sensor.native_value == 0

    hass.data.pop(DOMAIN, None)
    assert sensor.native_value == 0


async def test_extra_state_attributes_with_issues(hass: HomeAssistant):
    """extra_state_attributes returns issue IDs when reporter has issues."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset({"issue_1", "issue_2"})
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    attrs = sensor.extra_state_attributes
    assert "issue_ids" in attrs
    assert set(attrs["issue_ids"]) == {"issue_1", "issue_2"}


async def test_extra_state_attributes_no_reporter(hass: HomeAssistant):
    """extra_state_attributes returns empty dict when no reporter."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationIssuesSensor(hass, entry)

    hass.data[DOMAIN] = {}
    assert sensor.extra_state_attributes == {}

    hass.data.pop(DOMAIN, None)
    assert sensor.extra_state_attributes == {}
