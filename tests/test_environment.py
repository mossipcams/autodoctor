"""Test environment guardrails."""

import sys


def test_sys_path_has_no_editable_path_hook_placeholder() -> None:
    """Editable path hook placeholders should not be present during tests."""
    placeholders = [
        p
        for p in sys.path
        if p.startswith("__editable__.") and p.endswith(".__path_hook__")
    ]
    assert placeholders == []
