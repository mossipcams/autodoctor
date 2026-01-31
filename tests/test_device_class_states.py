"""Tests for device class state mappings."""

from custom_components.autodoctor.device_class_states import (
    get_all_known_domains,
    get_device_class_states,
)


def test_binary_sensor_states():
    """Test binary_sensor returns on/off."""
    states = get_device_class_states("binary_sensor")
    assert states == {"on", "off"}


def test_person_states():
    """Test person returns home/not_home/away."""
    states = get_device_class_states("person")
    assert states == {"home", "not_home", "away"}


def test_lock_states():
    """Test lock returns all valid states."""
    states = get_device_class_states("lock")
    expected = {
        "locked",
        "unlocked",
        "locking",
        "unlocking",
        "jammed",
        "opening",
        "open",
    }
    assert states == expected


def test_alarm_control_panel_states():
    """Test alarm_control_panel returns all valid states."""
    states = get_device_class_states("alarm_control_panel")
    expected = {
        "disarmed",
        "armed_home",
        "armed_away",
        "armed_night",
        "armed_vacation",
        "armed_custom_bypass",
        "pending",
        "arming",
        "disarming",
        "triggered",
    }
    assert states == expected


def test_sun_states():
    """Test sun returns above_horizon/below_horizon."""
    states = get_device_class_states("sun")
    assert states == {"above_horizon", "below_horizon"}


def test_group_states():
    """Test group returns on/off/home/not_home."""
    states = get_device_class_states("group")
    assert states == {"on", "off", "home", "not_home"}


def test_unknown_domain_returns_none():
    """Test unknown domain returns None."""
    states = get_device_class_states("unknown_domain")
    assert states is None


def test_get_all_known_domains():
    """Test we can list all known domains."""
    domains = get_all_known_domains()
    assert "binary_sensor" in domains
    assert "lock" in domains
    assert "person" in domains
