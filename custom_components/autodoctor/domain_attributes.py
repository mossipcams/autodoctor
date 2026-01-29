"""Domain-specific attribute mappings for validation."""

from __future__ import annotations

# Standard attributes supported by each domain
DOMAIN_ATTRIBUTES: dict[str, list[str]] = {
    "light": [
        "brightness",
        "color_temp",
        "hs_color",
        "rgb_color",
        "xy_color",
        "rgbw_color",
        "rgbww_color",
        "white_value",
        "color_mode",
        "supported_color_modes",
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
        "source",
        "source_list",
        "sound_mode",
        "sound_mode_list",
        "shuffle",
        "repeat",
    ],
}


def get_domain_attributes(domain: str) -> list[str]:
    """Get the standard attributes for a domain."""
    return DOMAIN_ATTRIBUTES.get(domain, [])
