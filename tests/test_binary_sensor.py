"""Tests for Autodoctor binary sensor platform."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.binary_sensor import (
    ValidationOkSensor,
    async_setup_entry,
)
from custom_components.autodoctor.const import DOMAIN


async def test_async_setup_entry_adds_entity(hass: HomeAssistant) -> None:
    """Test that async_setup_entry creates and registers ValidationOkSensor.

    Verifies the binary sensor platform setup correctly instantiates a
    ValidationOkSensor entity and passes it to the async_add_entities callback.
    """
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    added: list[ValidationOkSensor] = []

    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert len(added) == 1
    assert isinstance(added[0], ValidationOkSensor)


async def test_sensor_attributes(hass: HomeAssistant) -> None:
    """Test ValidationOkSensor has correct device attributes and configuration.

    Validates the sensor is properly configured with the PROBLEM device class,
    entity naming enabled, and correct device info linking to the integration.
    """
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    sensor = ValidationOkSensor(hass, entry)

    assert sensor._attr_name == "Problems"
    assert sensor._attr_device_class == BinarySensorDeviceClass.PROBLEM
    assert sensor._attr_has_entity_name is True
    assert sensor._attr_unique_id == "test_entry_id_validation_ok"
    assert sensor._attr_device_info is not None
    assert (DOMAIN, "test_entry_id") in sensor._attr_device_info["identifiers"]


async def test_is_on_with_active_issues(hass: HomeAssistant) -> None:
    """Test sensor reports ON (problem detected) when reporter has active issues.

    The Problems sensor should be ON when there are validation issues,
    allowing users to trigger automations on configuration problems.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationOkSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset({"issue1", "issue2"})
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    assert sensor.is_on is True


async def test_is_on_no_issues(hass: HomeAssistant) -> None:
    """Test sensor reports OFF (no problems) when reporter has no active issues.

    When all validation passes, the sensor should be OFF to indicate
    a healthy configuration state.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationOkSensor(hass, entry)

    mock_reporter = MagicMock()
    mock_reporter._active_issues = frozenset()
    hass.data[DOMAIN] = {"reporter": mock_reporter}

    assert sensor.is_on is False


async def test_is_on_no_reporter(hass: HomeAssistant) -> None:
    """Test sensor safely handles missing reporter during startup or reload.

    When the reporter is not yet initialized or has been unloaded, the sensor
    should gracefully return OFF rather than raising exceptions. This ensures
    the sensor entity remains stable during integration lifecycle events.
    """
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = ValidationOkSensor(hass, entry)

    hass.data[DOMAIN] = {}  # No reporter key
    assert sensor.is_on is False

    hass.data.pop(DOMAIN, None)  # No DOMAIN key at all
    assert sensor.is_on is False
