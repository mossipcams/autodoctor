"""Tests for Autodoctor binary sensor platform."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.binary_sensor import (
    ValidationOkSensor,
    async_setup_entry,
)
from custom_components.autodoctor.const import DOMAIN


async def test_async_setup_entry_adds_entity(hass: HomeAssistant):
    """async_setup_entry adds ValidationOkSensor."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    added = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert len(added) == 1
    assert isinstance(added[0], ValidationOkSensor)


async def test_sensor_attributes(hass: HomeAssistant):
    """ValidationOkSensor has correct class attributes."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    sensor = ValidationOkSensor(hass, entry)

    assert sensor._attr_name == "Problems"
    assert sensor._attr_device_class == BinarySensorDeviceClass.PROBLEM
    assert sensor._attr_has_entity_name is True
    assert sensor._attr_unique_id == "test_entry_id_validation_ok"
    assert sensor._attr_device_info is not None
    assert (DOMAIN, "test_entry_id") in sensor._attr_device_info["identifiers"]


async def test_is_on_with_active_issues(hass: HomeAssistant):
    """is_on returns True when reporter has active issues."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationOkSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset({"issue1", "issue2"})
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    assert sensor.is_on is True


async def test_is_on_no_issues(hass: HomeAssistant):
    """is_on returns False when reporter has no active issues."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationOkSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset()
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    assert sensor.is_on is False


async def test_is_on_no_reporter(hass: HomeAssistant):
    """is_on returns False when reporter is not available."""
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationOkSensor(hass, entry)

    hass.data[DOMAIN] = {}  # No reporter key
    assert sensor.is_on is False

    hass.data.pop(DOMAIN, None)  # No DOMAIN key at all
    assert sensor.is_on is False
