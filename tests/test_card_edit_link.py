"""Regression tests for edit-link rendering in the Autodoctor card."""

from __future__ import annotations

import re
from pathlib import Path


def test_autodoctor_card_renders_edit_link_conditionally() -> None:
    """Edit link markup should be gated behind a truthy edit_url check."""
    source = Path("custom_components/autodoctor/www/autodoctor-card.js").read_text(
        encoding="utf-8"
    )

    assert re.search(
        r"group\.edit_url\s*\?\s*b\s*`\s*<a href=\"\$\{group\.edit_url\}\" class=\"edit-link\"",
        source,
    )
