"""Tests for device class state mappings."""

import pytest

from custom_components.autodoctor.device_class_states import (
    get_all_known_domains,
    get_device_class_states,
)


@pytest.mark.parametrize(
    ("domain", "expected_states"),
    [
        ("binary_sensor", {"on", "off"}),
        ("person", {"home", "not_home", "away"}),
        (
            "lock",
            {
                "locked",
                "unlocked",
                "locking",
                "unlocking",
                "jammed",
                "opening",
                "open",
            },
        ),
        (
            "alarm_control_panel",
            {
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
            },
        ),
        ("sun", {"above_horizon", "below_horizon"}),
        ("group", {"on", "off", "home", "not_home"}),
    ],
    ids=[
        "binary_sensor",
        "person",
        "lock",
        "alarm_control_panel",
        "sun",
        "group",
    ],
)
def test_device_class_states(domain: str, expected_states: set[str]) -> None:
    """Test device class state mappings return correct known states.

    Validates that get_device_class_states() returns the complete set of
    valid states for each domain. These mappings are critical for state
    validation - they determine which states are considered valid in
    automations without requiring entity history lookup.
    """
    states = get_device_class_states(domain)
    assert states == expected_states


def test_unknown_domain_returns_none() -> None:
    """Test unknown domain returns None rather than empty set.

    When a domain has no predefined state mapping, None is returned to
    distinguish between "no known states" and "domain doesn't exist in
    our mappings". This allows the validator to fall back to entity
    history for state validation.
    """
    states = get_device_class_states("unknown_domain")
    assert states is None


def test_get_all_known_domains() -> None:
    """Test retrieval of all domains with predefined state mappings.

    This is used by the validation engine to determine which domains can
    be validated using hardcoded state lists versus requiring entity
    history lookup. Critical domains like binary_sensor, lock, and person
    must be present.
    """
    domains = get_all_known_domains()
    assert "binary_sensor" in domains
    assert "lock" in domains
    assert "person" in domains
