"""Tests for data models.

This module tests the core data models used throughout Autodoctor:
- StateReference: Entity state references found in automations
- ValidationIssue: Issues detected during validation
- ServiceCall: Service calls extracted from automations
- IssueType and Severity enums
- VALIDATION_GROUPS configuration
"""

from typing import Any

import pytest

from custom_components.autodoctor.models import (
    VALIDATION_GROUPS,
    IssueType,
    ServiceCall,
    Severity,
    StateReference,
    ValidationIssue,
)


def test_state_reference_creation() -> None:
    """Test StateReference captures entity state expectations from automations.

    StateReference is the primary model for tracking where automations
    expect specific entity states, enabling validation against actual states.
    """
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


def test_validation_issue_creation() -> None:
    """Test ValidationIssue stores all details needed for user-facing reports.

    ValidationIssue is the primary output model that surfaces problems
    to users, including context, severity, and actionable suggestions.
    """
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


def test_severity_ordering() -> None:
    """Test Severity enum values have correct numeric ordering.

    Higher severity levels have higher numeric values, allowing
    easy filtering and prioritization of issues.
    """
    assert Severity.ERROR.value > Severity.WARNING.value
    assert Severity.WARNING.value > Severity.INFO.value


@pytest.mark.parametrize(
    ("issue_type", "expected_value"),
    [
        (IssueType.ENTITY_NOT_FOUND, "entity_not_found"),
        (IssueType.ENTITY_REMOVED, "entity_removed"),
        (IssueType.INVALID_STATE, "invalid_state"),
        (IssueType.CASE_MISMATCH, "case_mismatch"),
        (IssueType.ATTRIBUTE_NOT_FOUND, "attribute_not_found"),
    ],
    ids=[
        "entity-not-found",
        "entity-removed",
        "invalid-state",
        "case-mismatch",
        "attribute-not-found",
    ],
)
def test_issue_type_enum_values(issue_type: IssueType, expected_value: str) -> None:
    """Test IssueType enum members have correct string values for serialization.

    String values are used in WebSocket API responses and storage,
    so they must remain stable across versions.
    """
    assert issue_type.value == expected_value


def test_validation_issue_has_issue_type() -> None:
    """Test ValidationIssue stores issue_type for categorization and filtering.

    The issue_type field enables the WebSocket API to filter issues
    by category (entity_state, services, templates).
    """
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


def test_validation_issue_to_dict() -> None:
    """Test ValidationIssue.to_dict() serializes for WebSocket API responses.

    The to_dict() method converts enums to strings and structures data
    for JSON serialization in WebSocket API responses.
    """
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
    result: dict[str, Any] = issue.to_dict()
    assert result["issue_type"] == "invalid_state"
    assert result["severity"] == "error"
    assert result["entity_id"] == "person.matt"
    assert result["message"] == "State 'away' is not valid"
    assert result["suggestion"] == "not_home"


@pytest.mark.skip(reason="OutcomeReport not yet implemented in models.py")
def test_outcome_report_to_issues_all_reachable():
    """All reachable returns empty list."""
    from custom_components.autodoctor.models import (
        OutcomeReport,
        Verdict,
        outcome_report_to_issues,
    )

    report = OutcomeReport(
        automation_id="automation.test",
        automation_name="Test Automation",
        triggers_valid=True,
        conditions_reachable=True,
        outcomes=["action.call_service"],
        unreachable_paths=[],
        verdict=Verdict.ALL_REACHABLE,
    )
    issues = outcome_report_to_issues(report)
    assert issues == []


@pytest.mark.skip(reason="OutcomeReport not yet implemented in models.py")
def test_outcome_report_to_issues_unreachable():
    """Unreachable paths become ValidationIssue objects."""
    from custom_components.autodoctor.models import (
        OutcomeReport,
        Verdict,
        outcome_report_to_issues,
    )

    report = OutcomeReport(
        automation_id="automation.test",
        automation_name="Test Automation",
        triggers_valid=True,
        conditions_reachable=False,
        outcomes=["action.call_service"],
        unreachable_paths=[
            "condition[0]: state requires 'home' but trigger sets 'away'"
        ],
        verdict=Verdict.UNREACHABLE,
    )
    issues = outcome_report_to_issues(report)

    assert len(issues) == 1
    assert issues[0].automation_id == "automation.test"
    assert issues[0].automation_name == "Test Automation"
    assert issues[0].severity == Severity.WARNING
    assert issues[0].issue_type == IssueType.IMPOSSIBLE_CONDITION
    assert "condition[0]" in issues[0].location


def test_validation_issue_equality() -> None:
    """Test ValidationIssue equality based on key fields for deduplication.

    Equality ignores severity and automation_name to prevent duplicate
    issues when the same problem is detected multiple times.
    """
    issue1 = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.temp",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue2 = ValidationIssue(
        severity=Severity.WARNING,  # Different severity
        automation_id="automation.test",
        automation_name="Different Name",  # Different name
        entity_id="sensor.temp",
        location="trigger[0]",  # Same location
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    # Should be equal because automation_id, issue_type, entity_id, location, and message match
    assert issue1 == issue2
    assert hash(issue1) == hash(issue2)


def test_validation_issue_set_deduplication() -> None:
    """Test ValidationIssue deduplication in sets prevents duplicate reports.

    Sets automatically deduplicate based on __hash__ and __eq__, ensuring
    users don't see the same issue reported multiple times.
    """
    issue1 = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.temp",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue2 = ValidationIssue(
        severity=Severity.WARNING,  # Different severity
        automation_id="automation.test",
        automation_name="Different",  # Different name
        entity_id="sensor.temp",
        location="trigger[0]",  # Same location as issue1
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue3 = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.other",  # Different automation
        automation_name="Test",
        entity_id="sensor.temp",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    # issue1 and issue2 are duplicates (same key fields including location)
    # issue3 is different (different automation_id)
    issues_set: set[ValidationIssue] = {issue1, issue2, issue3}
    assert len(issues_set) == 2  # Only 2 unique issues


def test_service_call_dataclass() -> None:
    """Test ServiceCall captures service call details for validation.

    ServiceCall stores all information needed to validate service calls
    against Home Assistant's service registry.
    """
    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test Automation",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": "light.living_room"},
        data={"brightness": 255},
        is_template=False,
    )

    assert call.automation_id == "automation.test"
    assert call.service == "light.turn_on"
    assert call.location == "action[0]"
    assert call.target == {"entity_id": "light.living_room"}
    assert call.data == {"brightness": 255}
    assert call.is_template is False


def test_service_call_template_detection() -> None:
    """Test ServiceCall is_template flag indicates dynamic service names.

    Templated service calls cannot be validated until runtime,
    so they are flagged for special handling.
    """
    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="{{ service_var }}",
        location="action[0]",
        is_template=True,
    )

    assert call.is_template is True


@pytest.mark.parametrize(
    ("issue_type_name", "expected_value"),
    [
        ("SERVICE_NOT_FOUND", "service_not_found"),
        ("SERVICE_MISSING_REQUIRED_PARAM", "service_missing_required_param"),
        ("SERVICE_INVALID_PARAM_TYPE", "service_invalid_param_type"),
        ("SERVICE_UNKNOWN_PARAM", "service_unknown_param"),
    ],
    ids=[
        "service-not-found",
        "missing-required-param",
        "invalid-param-type",
        "unknown-param",
    ],
)
def test_service_issue_types_exist(
    issue_type_name: str, expected_value: str
) -> None:
    """Test service validation issue types exist with correct values.

    Service validation was added in v2.13.0 and requires these
    issue types for reporting service call problems.
    """
    assert hasattr(IssueType, issue_type_name)
    issue_type: IssueType = getattr(IssueType, issue_type_name)
    assert issue_type.value == expected_value


@pytest.mark.parametrize(
    "removed_member",
    [
        "TEMPLATE_INVALID_ENTITY_ID",
        "TEMPLATE_ENTITY_NOT_FOUND",
        "TEMPLATE_INVALID_STATE",
        "TEMPLATE_ATTRIBUTE_NOT_FOUND",
        "TEMPLATE_DEVICE_NOT_FOUND",
        "TEMPLATE_AREA_NOT_FOUND",
        "TEMPLATE_ZONE_NOT_FOUND",
    ],
    ids=[
        "invalid-entity-id",
        "entity-not-found",
        "invalid-state",
        "attribute-not-found",
        "device-not-found",
        "area-not-found",
        "zone-not-found",
    ],
)
def test_removed_template_entity_issue_types(removed_member: str) -> None:
    """Guard: Prevent re-introduction of template entity validation issue types.

    These validation types were removed in v2.14.0 due to 40% false positive
    rate with blueprint variables and dynamic template content.

    See: PROJECT.md "Key Decisions" - Remove rather than patch
    """
    assert not hasattr(IssueType, removed_member), (
        f"IssueType.{removed_member} should have been removed in v2.14.0"
    )


def test_issue_type_count_after_removals() -> None:
    """Guard: Verify IssueType has exactly 13 members after v2.14.0 removals.

    This guards against accidental reintroduction of removed types.
    Count: 5 entity_state + 5 services + 3 templates = 13 total.
    """
    assert len(IssueType) == 13, f"Expected 13 IssueType members, got {len(IssueType)}"


def test_templates_validation_group_narrowed() -> None:
    """Guard: Verify templates group contains only syntax checks after v2.14.0.

    Entity/state validation was removed from templates in v2.14.0 due to
    40% false positive rate. Only syntax-level checks remain.

    See: PROJECT.md "Key Decisions" - Remove rather than patch
    """
    templates_group = VALIDATION_GROUPS["templates"]["issue_types"]
    expected: frozenset[IssueType] = frozenset(
        {
            IssueType.TEMPLATE_SYNTAX_ERROR,
            IssueType.TEMPLATE_UNKNOWN_FILTER,
            IssueType.TEMPLATE_UNKNOWN_TEST,
        }
    )
    assert templates_group == expected, (
        f"Templates group should contain only syntax-level checks. "
        f"Got: {templates_group}, Expected: {expected}"
    )


def test_validation_groups_cover_all_issue_types() -> None:
    """Test VALIDATION_GROUPS contains every IssueType exactly once.

    This ensures the WebSocket API can correctly group and filter all
    possible issues, with no orphaned or duplicate issue types.
    """
    all_enum_members: set[IssueType] = set(IssueType)

    # Collect all issue types from all groups
    all_grouped: list[IssueType] = []
    grouped_set: set[IssueType] = set()
    for _group_id, group_def in VALIDATION_GROUPS.items():
        issue_types: frozenset[IssueType] = group_def["issue_types"]  # type: ignore[assignment]
        all_grouped.extend(issue_types)
        grouped_set |= issue_types

    # Every IssueType member must appear in some group (no missing members)
    missing: set[IssueType] = all_enum_members - grouped_set
    assert not missing, f"IssueType members missing from VALIDATION_GROUPS: {missing}"

    # No extra entries that aren't real IssueType members
    extras: set[IssueType] = grouped_set - all_enum_members
    assert not extras, f"VALIDATION_GROUPS contains non-IssueType entries: {extras}"

    # No duplicates across groups (each member in exactly one group)
    assert len(all_grouped) == len(all_enum_members), (
        f"Duplicate IssueType members across VALIDATION_GROUPS: "
        f"expected {len(all_enum_members)} entries, found {len(all_grouped)}"
    )
