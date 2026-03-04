"""Tests for reachability/contradiction validator."""

from __future__ import annotations

from custom_components.autodoctor.models import IssueType, Severity
from custom_components.autodoctor.reachability_validator import ReachabilityValidator


def test_does_not_flag_cross_trigger_state_values_as_contradictions() -> None:
    """State trigger values are OR paths and must not become global facts."""
    automation = {
        "id": "reachability_state",
        "alias": "Reachability State",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "binary_sensor.motion_kitchen",
                "to": "on",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "binary_sensor.motion_kitchen",
                "state": "off",
            }
        ],
        "action": [],
    }

    validator = ReachabilityValidator()
    issues = validator.validate_automations([automation])

    assert issues == []


def test_does_not_flag_if_branch_from_trigger_only_constraint() -> None:
    """Branch conditions should not be constrained by OR trigger state facts alone."""
    automation = {
        "id": "reachability_if",
        "alias": "Reachability If",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "binary_sensor.motion_office",
                "to": "on",
            }
        ],
        "condition": [],
        "action": [
            {
                "if": [
                    {
                        "condition": "state",
                        "entity_id": "binary_sensor.motion_office",
                        "state": "off",
                    }
                ],
                "then": [{"service": "light.turn_on"}],
            }
        ],
    }

    validator = ReachabilityValidator()
    issues = validator.validate_automations([automation])

    assert issues == []


def test_detects_impossible_numeric_range_in_single_condition() -> None:
    """Numeric condition with above >= below is unreachable."""
    automation = {
        "id": "reachability_numeric",
        "alias": "Reachability Numeric",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "numeric_state",
                "entity_id": "sensor.office_temp",
                "above": 25,
                "below": 20,
            }
        ],
        "action": [],
    }

    validator = ReachabilityValidator()
    issues = validator.validate_automations([automation])

    assert len(issues) == 1
    issue = issues[0]
    assert issue.issue_type == IssueType.UNREACHABLE_NUMERIC_RANGE
    assert issue.severity == Severity.ERROR
    assert issue.location == "condition[0]"
    assert issue.entity_id == "sensor.office_temp"


def test_does_not_flag_numeric_trigger_condition_as_global_contradiction() -> None:
    """Numeric trigger constraints should not be treated as global always-true bounds."""
    automation = {
        "id": "reachability_numeric_cross",
        "alias": "Reachability Numeric Cross",
        "trigger": [
            {
                "platform": "numeric_state",
                "entity_id": "sensor.humidity",
                "above": 70,
            }
        ],
        "condition": [
            {
                "condition": "numeric_state",
                "entity_id": "sensor.humidity",
                "below": 60,
            }
        ],
        "action": [],
    }

    validator = ReachabilityValidator()
    issues = validator.validate_automations([automation])

    assert issues == []


def test_detects_impossible_numeric_choose_branch_without_global_constraints() -> None:
    """Choose branch with above>=below is unreachable even without global bounds."""
    automation = {
        "id": "reachability_choose_numeric",
        "alias": "Reachability Choose Numeric",
        "trigger": [{"platform": "time", "at": "09:00:00"}],
        "condition": [],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "numeric_state",
                                "entity_id": "sensor.pool_temp",
                                "above": 30,
                                "below": 20,
                            }
                        ],
                        "sequence": [{"service": "switch.turn_on"}],
                    }
                ],
                "default": [],
            }
        ],
    }

    validator = ReachabilityValidator()
    issues = validator.validate_automations([automation])

    assert len(issues) == 1
    issue = issues[0]
    assert issue.issue_type == IssueType.UNREACHABLE_NUMERIC_RANGE
    assert issue.entity_id == "sensor.pool_temp"
    assert issue.location == "action[0].choose[0].conditions[0]"
