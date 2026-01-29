"""Simplified fix engine - entity ID fuzzy match."""

from __future__ import annotations

from difflib import get_close_matches


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
