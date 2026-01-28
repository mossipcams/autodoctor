"""Device class state mappings for known Home Assistant domains."""

from __future__ import annotations

# Verified against Home Assistant 2024.x documentation
DEVICE_CLASS_STATES: dict[str, set[str]] = {
    "binary_sensor": {"on", "off"},
    "person": {"home", "not_home"},
    # device_tracker: home/not_home are defaults, but BLE trackers can have
    # area names - those come from entity history
    "device_tracker": {"home", "not_home"},
    "lock": {"locked", "unlocked", "locking", "unlocking", "jammed", "opening", "open"},
    "cover": {"open", "closed", "opening", "closing"},
    "alarm_control_panel": {
        "disarmed", "armed_home", "armed_away", "armed_night", "armed_vacation",
        "armed_custom_bypass", "pending", "arming", "disarming", "triggered"
    },
    "vacuum": {"cleaning", "docked", "idle", "paused", "returning", "error"},
    "media_player": {"off", "on", "idle", "playing", "paused", "standby", "buffering"},
    "switch": {"on", "off"},
    "light": {"on", "off"},
    "fan": {"on", "off"},
    "input_boolean": {"on", "off"},
    "script": {"on", "off"},
    "automation": {"on", "off"},
    # update entities: on = update available, off = up to date
    "update": {"on", "off"},
    # schedule entities: on = active (within time block), off = inactive
    "schedule": {"on", "off"},
}


def get_device_class_states(domain: str) -> set[str] | None:
    """Get known valid states for a domain.

    Args:
        domain: The entity domain (e.g., 'binary_sensor', 'lock')

    Returns:
        Set of valid states, or None if domain is unknown
    """
    return DEVICE_CLASS_STATES.get(domain)


def get_all_known_domains() -> set[str]:
    """Get all domains with known state mappings.

    Returns:
        Set of domain names
    """
    return set(DEVICE_CLASS_STATES.keys())
