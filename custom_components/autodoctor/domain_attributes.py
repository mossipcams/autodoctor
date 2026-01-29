"""Domain-specific attribute mappings for validation."""

from __future__ import annotations

# Standard attributes supported by each domain
DOMAIN_ATTRIBUTES: dict[str, list[str]] = {
    "light": [
        "brightness",
    ],
    "climate": [
        "temperature",
    ],
}


def get_domain_attributes(domain: str) -> list[str]:
    """Get the standard attributes for a domain."""
    return DOMAIN_ATTRIBUTES.get(domain, [])
