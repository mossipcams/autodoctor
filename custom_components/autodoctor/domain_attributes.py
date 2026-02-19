"""Domain-specific attribute mappings for validation.

Covers 23 HA domains with attributes commonly used in automations via
state_attr() calls. Only includes attributes exposed in state.attributes,
not internal Python properties (is_on, is_closed, native_value, native_unit_of_measurement).
"""

from __future__ import annotations

from typing import overload

# Standard attributes supported by each domain
DOMAIN_ATTRIBUTES: dict[str, list[str]] = {
    "light": [
        "brightness",
        "color_temp",
        "color_temp_kelvin",
        "min_color_temp_kelvin",
        "max_color_temp_kelvin",
        "hs_color",
        "rgb_color",
        "xy_color",
        "rgbw_color",
        "rgbww_color",
        "white_value",
        "color_mode",
        "supported_color_modes",
        "supported_features",
        "effect",
        "effect_list",
    ],
    "climate": [
        "temperature",
        "target_temp_high",
        "target_temp_low",
        "current_temperature",
        "humidity",
        "current_humidity",
        "fan_mode",
        "fan_modes",
        "swing_mode",
        "swing_modes",
        "preset_mode",
        "preset_modes",
        "hvac_action",
        "hvac_modes",
    ],
    "media_player": [
        "volume_level",
        "is_volume_muted",
        "media_content_id",
        "media_content_type",
        "media_duration",
        "media_position",
        "media_position_updated_at",
        "media_title",
        "media_artist",
        "media_album_name",
        "media_album_artist",
        "media_track",
        "media_series_title",
        "media_season",
        "media_episode",
        "media_image_url",
        "app_id",
        "app_name",
        "entity_picture_local",
        "group_members",
        "source",
        "source_list",
        "sound_mode",
        "sound_mode_list",
        "shuffle",
        "repeat",
    ],
    "cover": [
        "current_cover_position",
        "current_cover_tilt_position",
    ],
    "fan": [
        "percentage",
        "preset_mode",
        "preset_modes",
        "oscillating",
        "current_direction",
    ],
    "vacuum": [
        "fan_speed",
        "fan_speed_list",
        "status",
        "battery_level",
    ],
    "lock": [
        "changed_by",
        "code_format",
    ],
    "alarm_control_panel": [
        "code_arm_required",
        "code_format",
        "changed_by",
    ],
    "switch": [],
    "binary_sensor": [
        "device_class",
    ],
    "sensor": [
        "device_class",
        "state_class",
        "options",
    ],
    "number": [
        "min",
        "max",
        "step",
        "mode",
        "unit_of_measurement",
    ],
    "select": [
        "options",
    ],
    "input_text": [
        "min",
        "max",
        "pattern",
        "mode",
    ],
    "input_datetime": [
        "has_time",
        "has_date",
        "year",
        "month",
        "day",
        "timestamp",
    ],
    "automation": [
        "last_triggered",
        "mode",
        "current",
    ],
    "script": [
        "last_triggered",
        "mode",
        "current",
    ],
    "siren": [
        "available_tones",
        "supported_features",
    ],
    "remote": [
        "activity_list",
        "current_activity",
        "supported_features",
    ],
    "camera": [
        "is_streaming",
        "frontend_stream_type",
        "access_token",
    ],
    "text": [
        "min",
        "max",
        "pattern",
        "mode",
    ],
    "event": [
        "event_type",
        "event_types",
    ],
    "valve": [
        "current_valve_position",
        "supported_features",
    ],
}


@overload
def get_domain_attributes(domain: None = None) -> dict[str, list[str]]: ...


@overload
def get_domain_attributes(domain: str) -> list[str]: ...


def get_domain_attributes(
    domain: str | None = None,
) -> list[str] | dict[str, list[str]]:
    """Get the standard attributes for a domain, or the full mapping.

    Args:
        domain: The entity domain (e.g., 'light', 'climate').
                If None, returns the entire DOMAIN_ATTRIBUTES dict.

    Returns:
        List of attribute strings for the given domain, or the full dict if
        no domain is specified.
    """
    if domain is None:
        return DOMAIN_ATTRIBUTES
    return DOMAIN_ATTRIBUTES.get(domain, [])
