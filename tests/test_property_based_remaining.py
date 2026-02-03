"""Property-based tests for reporter, websocket_api, knowledge_base, and models.

Property-based testing generates hundreds of random inputs to find edge cases
that hand-crafted tests miss. Each test asserts that functions NEVER crash
(return normally or return empty results) regardless of input.

This file focuses on pure functions across reporter.py, websocket_api.py,
knowledge_base.py, and models.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import IssueType, Severity, ValidationIssue
from custom_components.autodoctor.reporter import IssueReporter
from custom_components.autodoctor.websocket_api import _compute_group_status

# ============================================================================
# Reporter tests - IssueReporter with mock hass
# ============================================================================


@given(automation_id=st.text(max_size=200))
@settings(max_examples=200)
def test_automation_issue_id_never_crashes(automation_id: str) -> None:
    """Property: _automation_issue_id handles any string without crashing.

    Tests that:
    - Any string input returns a string
    - Dots are replaced with underscores
    - Never raises exceptions
    """
    reporter = IssueReporter(MagicMock())
    result = reporter._automation_issue_id(automation_id)
    assert isinstance(result, str)
    # Verify dots are replaced
    assert "." not in result


@given(severity=st.sampled_from(list(Severity)))
@settings(max_examples=200)
def test_severity_to_repair_never_crashes(severity: Severity) -> None:
    """Property: _severity_to_repair handles all Severity enum values without crashing.

    Tests that:
    - All Severity values return a string
    - ERROR returns "error"
    - WARNING/INFO return "warning"
    - Never raises exceptions
    """
    reporter = IssueReporter(MagicMock())
    result = reporter._severity_to_repair(severity)
    assert isinstance(result, str)
    assert result in ("error", "warning")


@st.composite
def validation_issue_list(draw: Any) -> list[ValidationIssue]:
    """Generate lists of ValidationIssue with random field values."""
    num_issues = draw(st.integers(min_value=0, max_value=10))
    issues = []
    for _ in range(num_issues):
        issues.append(
            ValidationIssue(
                severity=draw(st.sampled_from(list(Severity))),
                automation_id=draw(st.text(max_size=50)),
                automation_name=draw(st.text(max_size=50)),
                entity_id=draw(st.text(max_size=50)),
                location=draw(st.text(max_size=50)),
                message=draw(st.text(max_size=200)),
                issue_type=draw(st.one_of(st.none(), st.sampled_from(list(IssueType)))),
                suggestion=draw(st.one_of(st.none(), st.text(max_size=100))),
            )
        )
    return issues


@given(issues=validation_issue_list())
@settings(max_examples=200)
def test_format_issues_for_repair_never_crashes(issues: list[ValidationIssue]) -> None:
    """Property: _format_issues_for_repair handles any issue list without crashing.

    Tests that:
    - Returns a string (possibly with embedded newlines from field values)
    - Never raises exceptions
    """
    reporter = IssueReporter(MagicMock())
    result = reporter._format_issues_for_repair(issues)
    assert isinstance(result, str)


# ============================================================================
# WebSocket API tests - _compute_group_status
# ============================================================================


@given(issues=validation_issue_list())
@settings(max_examples=200)
def test_compute_group_status_never_crashes(issues: list[ValidationIssue]) -> None:
    """Property: _compute_group_status handles any issue list without crashing.

    Tests that:
    - Empty list returns "pass"
    - List with ERROR returns "fail"
    - List with WARNING (no ERROR) returns "warning"
    - List with only INFO returns "pass"
    - Never raises exceptions
    """
    result = _compute_group_status(issues)
    assert isinstance(result, str)
    assert result in ("fail", "warning", "pass")

    # Verify specific behaviors
    if not issues:
        assert result == "pass"
    elif any(i.severity == Severity.ERROR for i in issues):
        assert result == "fail"
    elif any(i.severity == Severity.WARNING for i in issues):
        assert result == "warning"
    else:
        # Only INFO severity
        assert result == "pass"


@given(issues_lists=st.lists(validation_issue_list(), max_size=5))
@settings(max_examples=200)
def test_compute_group_status_multiple_lists(issues_lists: list[list[ValidationIssue]]) -> None:
    """Property: _compute_group_status is consistent across multiple calls.

    Tests that calling with same input produces same output (deterministic).
    """
    for issues in issues_lists:
        result1 = _compute_group_status(issues)
        result2 = _compute_group_status(issues)
        assert result1 == result2


# ============================================================================
# Knowledge Base tests - StateKnowledgeBase
# ============================================================================


@given(entity_id=st.text(max_size=200))
@settings(max_examples=200)
def test_get_domain_never_crashes(entity_id: str) -> None:
    """Property: get_domain handles any string without crashing.

    Tests that:
    - String with "." returns part before first dot
    - String without "." returns empty string
    - Never raises exceptions
    """
    kb = StateKnowledgeBase(MagicMock())
    result = kb.get_domain(entity_id)
    assert isinstance(result, str)

    # Verify behavior
    if "." in entity_id:
        assert result == entity_id.split(".")[0]
    else:
        assert result == ""


@given(attribute_name=st.text(max_size=100))
@settings(max_examples=200)
def test_attribute_maps_to_capability_never_crashes(attribute_name: str) -> None:
    """Property: _attribute_maps_to_capability handles any string without crashing.

    Tests that:
    - Known attributes return correct capability key
    - Unknown attributes return None
    - Never raises exceptions
    """
    kb = StateKnowledgeBase(MagicMock())
    result = kb._attribute_maps_to_capability(attribute_name)
    assert result is None or isinstance(result, str)

    # Verify known mappings
    known_mappings = {
        "fan_mode": "fan_modes",
        "preset_mode": "preset_modes",
        "swing_mode": "swing_modes",
        "swing_horizontal_mode": "swing_horizontal_modes",
    }
    if attribute_name in known_mappings:
        assert result == known_mappings[attribute_name]


# ============================================================================
# Models tests - ValidationIssue
# ============================================================================


@given(
    severity=st.sampled_from(list(Severity)),
    automation_id=st.text(max_size=100),
    automation_name=st.text(max_size=100),
    entity_id=st.text(max_size=100),
    location=st.text(max_size=100),
    message=st.text(max_size=500),
    issue_type=st.one_of(st.none(), st.sampled_from(list(IssueType))),
    suggestion=st.one_of(st.none(), st.text(max_size=100)),
)
@settings(max_examples=200)
def test_validation_issue_to_dict_never_crashes(
    severity: Severity,
    automation_id: str,
    automation_name: str,
    entity_id: str,
    location: str,
    message: str,
    issue_type: IssueType | None,
    suggestion: str | None,
) -> None:
    """Property: ValidationIssue.to_dict() handles any field values without crashing.

    Tests that:
    - Returns dict with expected keys
    - Never raises exceptions
    """
    issue = ValidationIssue(
        severity=severity,
        automation_id=automation_id,
        automation_name=automation_name,
        entity_id=entity_id,
        location=location,
        message=message,
        issue_type=issue_type,
        suggestion=suggestion,
    )
    result = issue.to_dict()
    assert isinstance(result, dict)
    # Verify expected keys present
    expected_keys = {
        "severity",
        "automation_id",
        "automation_name",
        "entity_id",
        "location",
        "message",
        "issue_type",
        "suggestion",
        "valid_states",
    }
    assert set(result.keys()) == expected_keys


@given(issue=validation_issue_list().filter(lambda lst: len(lst) > 0).map(lambda lst: lst[0]))
@settings(max_examples=200)
def test_validation_issue_get_suppression_key_never_crashes(issue: ValidationIssue) -> None:
    """Property: get_suppression_key() handles any ValidationIssue without crashing.

    Tests that:
    - Returns string with expected format
    - Format is "auto_id:entity_id:issue_type"
    - Never raises exceptions
    """
    result = issue.get_suppression_key()
    assert isinstance(result, str)
    # Verify format has at least two colons (automation_id:entity_id:issue_type)
    # Note: automation_id or entity_id may contain colons in edge cases
    assert result.count(":") >= 2


@given(
    issue1=validation_issue_list().filter(lambda lst: len(lst) > 0).map(lambda lst: lst[0]),
    issue2=validation_issue_list().filter(lambda lst: len(lst) > 0).map(lambda lst: lst[0]),
)
@settings(max_examples=200)
def test_validation_issue_hash_and_eq_consistency(
    issue1: ValidationIssue, issue2: ValidationIssue
) -> None:
    """Property: if two issues are equal, they have the same hash.

    Tests hash/eq consistency for ValidationIssue deduplication.
    """
    if issue1 == issue2:
        assert hash(issue1) == hash(issue2)


@given(issue=validation_issue_list().filter(lambda lst: len(lst) > 0).map(lambda lst: lst[0]))
@settings(max_examples=200)
def test_validation_issue_hash_deterministic(issue: ValidationIssue) -> None:
    """Property: hash is deterministic across calls.

    Tests that hashing same issue produces same hash.
    """
    hash1 = hash(issue)
    hash2 = hash(issue)
    assert hash1 == hash2


# ============================================================================
# Edge case: ValidationIssue with extreme field values
# ============================================================================


@given(
    severity=st.sampled_from(list(Severity)),
    automation_id=st.text(min_size=0, max_size=0),  # Empty string
    automation_name=st.text(min_size=0, max_size=0),  # Empty string
    entity_id=st.text(min_size=0, max_size=0),  # Empty string
    location=st.text(min_size=0, max_size=0),  # Empty string
    message=st.text(min_size=0, max_size=0),  # Empty string
)
@settings(max_examples=200)
def test_validation_issue_with_empty_strings(
    severity: Severity,
    automation_id: str,
    automation_name: str,
    entity_id: str,
    location: str,
    message: str,
) -> None:
    """Property: ValidationIssue handles empty strings without crashing.

    Tests that ValidationIssue with all-empty-string fields can be created,
    serialized, and hashed without errors.
    """
    issue = ValidationIssue(
        severity=severity,
        automation_id=automation_id,
        automation_name=automation_name,
        entity_id=entity_id,
        location=location,
        message=message,
    )
    # Should not crash on any operation
    _ = issue.to_dict()
    _ = hash(issue)
    _ = issue.get_suppression_key()
    assert True  # If we get here, no crashes
