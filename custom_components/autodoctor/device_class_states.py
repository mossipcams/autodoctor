"""Device class state mappings for known Home Assistant domains."""

from __future__ import annotations

# Verified against Home Assistant 2024.x/2025.x documentation
DEVICE_CLASS_STATES: dict[str, set[str]] = {
    "binary_sensor": {"on", "off"},
    "person": {"home", "not_home"},
    # device_tracker: home/not_home are defaults, but BLE trackers can have
    # area names - those come from entity history
    "device_tracker": {"home", "not_home"},
    "lock": {"locked", "unlocked", "locking", "unlocking", "jammed", "opening", "open"},
    "cover": {"open", "closed", "opening", "closing", "stopped"},
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
    # climate: hvac modes (hvac_action is an attribute, not the state)
    "climate": {"off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"},
    # water_heater: operation modes
    "water_heater": {
        "off", "eco", "electric", "gas", "heat_pump", "high_demand", "performance",
        "heat", "auto"
    },
    # humidifier: on/off (action is an attribute)
    "humidifier": {"on", "off"},
    # lawn_mower: activity states
    "lawn_mower": {"mowing", "paused", "docked", "returning", "error", "idle"},
    # valve: open/closed states
    "valve": {"open", "closed", "opening", "closing"},
    # siren: on/off
    "siren": {"on", "off"},
    # button/event: no meaningful state (press-only)
    "button": {"unknown"},
    "event": {"unknown"},
    # input_button: no meaningful state
    "input_button": {"unknown"},
    # scene: no meaningful state (activate-only)
    "scene": {"unknown"},
    # remote: on/off
    "remote": {"on", "off"},
    # select/input_select: any string (handled by schema introspection)
    # number/input_number: numeric (skip validation)
    # text/input_text: any string (skip validation)
    # datetime/input_datetime: datetime string (skip validation)
    # timer: idle, active, paused
    "timer": {"idle", "active", "paused"},
    # counter: numeric (skip validation)
    # image: URL string (skip validation)
    # calendar: on/off (event active or not)
    "calendar": {"on", "off"},
    # weather: conditions
    "weather": {
        "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
        "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
        "snowy-rainy", "sunny", "windy", "windy-variant"
    },
    # device_tracker states beyond home/not_home handled by knowledge_base
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
