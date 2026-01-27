"""Tests for data models."""

import pytest
from datetime import datetime

from custom_components.autodoctor.models import (
    StateReference,
    ValidationIssue,
    OutcomeReport,
    Severity,
    Verdict,
    IssueType,
)


def test_state_reference_creation():
    """Test StateReference dataclass."""
    ref = StateReference(
        automation_id="automation.welcome_home",
        automation_name="Welcome Home",
        entity_id="person.matt",
        expected_state="home",
        expected_attribute=None,
        location="trigger[0].to",
        source_line=10,
    )
    assert ref.automation_id == "automation.welcome_home"
    assert ref.expected_state == "home"
    assert ref.expected_attribute is None


def test_validation_issue_creation():
    """Test ValidationIssue dataclass."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0]",
        message="Invalid state",
        suggestion="not_home",
        valid_states=["home", "not_home"],
    )
    assert issue.severity == Severity.ERROR
    assert issue.suggestion == "not_home"


def test_outcome_report_creation():
    """Test OutcomeReport dataclass."""
    report = OutcomeReport(
        automation_id="automation.test",
        automation_name="Test",
        triggers_valid=True,
        conditions_reachable=True,
        outcomes=["action: light.turn_on"],
        unreachable_paths=[],
        verdict=Verdict.ALL_REACHABLE,
    )
    assert report.verdict == Verdict.ALL_REACHABLE


def test_severity_ordering():
    """Test severity levels."""
    assert Severity.ERROR.value > Severity.WARNING.value
    assert Severity.WARNING.value > Severity.INFO.value


def test_issue_type_enum_values():
    """Test IssueType enum has expected values."""
    assert IssueType.ENTITY_NOT_FOUND.value == "entity_not_found"
    assert IssueType.ENTITY_REMOVED.value == "entity_removed"
    assert IssueType.INVALID_STATE.value == "invalid_state"
    assert IssueType.IMPOSSIBLE_CONDITION.value == "impossible_condition"
    assert IssueType.CASE_MISMATCH.value == "case_mismatch"
    assert IssueType.ATTRIBUTE_NOT_FOUND.value == "attribute_not_found"


def test_validation_issue_has_issue_type():
    """Test ValidationIssue accepts issue_type field."""
    issue = ValidationIssue(
        issue_type=IssueType.ENTITY_NOT_FOUND,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.missing",
        location="trigger[0]",
        message="Entity not found",
    )
    assert issue.issue_type == IssueType.ENTITY_NOT_FOUND


def test_validation_issue_to_dict():
    """Test ValidationIssue.to_dict() returns serializable dict."""
    issue = ValidationIssue(
        issue_type=IssueType.INVALID_STATE,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0].to",
        message="State 'away' is not valid",
        suggestion="not_home",
    )
    result = issue.to_dict()
    assert result["issue_type"] == "invalid_state"
    assert result["severity"] == "error"
    assert result["entity_id"] == "person.matt"
    assert result["message"] == "State 'away' is not valid"
    assert result["suggestion"] == "not_home"
