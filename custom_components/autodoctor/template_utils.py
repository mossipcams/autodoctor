"""Shared Jinja2 template detection utilities."""

from __future__ import annotations

import re
from typing import Any

# Matches Jinja2 expression ({{), statement ({%), and comment ({#) openers.
_TEMPLATE_PATTERN = re.compile(r"\{[{%#]")


def is_template_value(value: Any) -> bool:
    """Check if a value contains Jinja2 template syntax."""
    return isinstance(value, str) and bool(_TEMPLATE_PATTERN.search(value))
