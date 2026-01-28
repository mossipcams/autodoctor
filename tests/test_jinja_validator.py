"""Tests for JinjaValidator."""

import pytest
from custom_components.autodoctor.jinja_validator import JinjaValidator


def test_deeply_nested_conditions_do_not_stackoverflow():
    """Test that deeply nested conditions hit recursion limit gracefully."""
    validator = JinjaValidator()

    # Build deeply nested condition (25 levels deep)
    condition = {"condition": "state", "entity_id": "light.test", "state": "on"}
    for _ in range(25):
        condition = {"condition": "and", "conditions": [condition]}

    automation = {
        "id": "deep_nest",
        "alias": "Deeply Nested",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [condition],
        "actions": [],
    }

    # Should not raise RecursionError, should return (possibly with warning logged)
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)


def test_null_repeat_config_does_not_crash():
    """Test that repeat: null doesn't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": "null_repeat",
        "alias": "Null Repeat",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{"repeat": None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)


def test_null_parallel_config_does_not_crash():
    """Test that parallel: null doesn't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": "null_parallel",
        "alias": "Null Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{"parallel": None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)
