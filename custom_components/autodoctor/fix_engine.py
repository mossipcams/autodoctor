"""Simplified fix engine - synonym table + fuzzy match."""

from __future__ import annotations

from difflib import get_close_matches

STATE_SYNONYMS: dict[str, str] = {
    # Common presence mistakes
    "away": "not_home",
    "gone": "not_home",
    "absent": "not_home",
    "present": "home",
    "arrived": "home",
    # Boolean variations
    "true": "on",
    "false": "off",
    "yes": "on",
    "no": "off",
    "1": "on",
    "0": "off",
    "enabled": "on",
    "disabled": "off",
    "active": "on",
    "inactive": "off",
    # Alarm panel
    "armed": "armed_away",
    "disarmed": "disarmed",
    # Cover states
    "open": "open",
    "closed": "closed",
    "opening": "opening",
    "closing": "closing",
    "shut": "closed",
    # Lock states
    "locked": "locked",
    "unlocked": "unlocked",
    "lock": "locked",
    "unlock": "unlocked",
    # Climate/HVAC variations
    "heating": "heat",
    "cooling": "cool",
    "auto_heat_cool": "heat_cool",
    "hvac_off": "off",
    # Media player variations
    "play": "playing",
    "pause": "paused",
    "stop": "idle",
    "stopped": "idle",
    # Vacuum/lawn mower variations
    "vacuuming": "cleaning",
    "charging": "docked",
    "returning_home": "returning",
    # Weather variations
    "partly_cloudy": "partlycloudy",
    "partly-cloudy": "partlycloudy",
    "clear": "sunny",
}


def get_state_suggestion(invalid_state: str, valid_states: set[str]) -> str | None:
    """Get a suggestion for an invalid state.

    Checks synonym table first, then falls back to fuzzy matching.
    """
    # Check synonym table
    normalized = invalid_state.lower().strip()
    if normalized in STATE_SYNONYMS:
        canonical = STATE_SYNONYMS[normalized]
        if canonical in valid_states:
            return canonical
        # Check case-insensitive match
        lower_map = {s.lower(): s for s in valid_states}
        if canonical.lower() in lower_map:
            return lower_map[canonical.lower()]

    # Fall back to fuzzy matching
    matches = get_close_matches(
        invalid_state.lower(), [s.lower() for s in valid_states], n=1, cutoff=0.6
    )
    if matches:
        lower_map = {s.lower(): s for s in valid_states}
        return lower_map.get(matches[0])

    return None


def get_entity_suggestion(invalid_entity: str, all_entities: list[str]) -> str | None:
    """Get a suggestion for an invalid entity ID."""
    if "." not in invalid_entity:
        return None

    domain, name = invalid_entity.split(".", 1)

    # Only consider entities in the same domain
    same_domain = [e for e in all_entities if e.startswith(f"{domain}.")]
    if not same_domain:
        return None

    # Match on name portion only
    names = {eid.split(".", 1)[1]: eid for eid in same_domain}
    matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

    return names[matches[0]] if matches else None
