"""Tests for data models."""

import pytest

from custom_components.autodoctor.models import (
    VALIDATION_GROUPS,
    IssueType,
    Severity,
    StateReference,
    ValidationIssue,
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


def test_severity_ordering():
    """Test severity levels."""
    assert Severity.ERROR.value > Severity.WARNING.value
    assert Severity.WARNING.value > Severity.INFO.value


def test_issue_type_enum_values():
    """Test IssueType enum has expected values."""
    assert IssueType.ENTITY_NOT_FOUND.value == "entity_not_found"
    assert IssueType.ENTITY_REMOVED.value == "entity_removed"
    assert IssueType.INVALID_STATE.value == "invalid_state"
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


def test_validation_issue_equality():
    """Test that ValidationIssue instances with same key fields are equal."""
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


def test_validation_issue_set_deduplication():
    """Test that duplicate ValidationIssue instances are deduplicated in sets."""
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
    issues_set = {issue1, issue2, issue3}
    assert len(issues_set) == 2  # Only 2 unique issues


def test_service_call_dataclass():
    """Test ServiceCall dataclass creation."""
    from custom_components.autodoctor.models import ServiceCall

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


def test_service_call_template_detection():
    """Test ServiceCall with templated service name."""
    from custom_components.autodoctor.models import ServiceCall

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="{{ service_var }}",
        location="action[0]",
        is_template=True,
    )

    assert call.is_template is True


def test_service_issue_types_exist():
    """Test new service-related issue types exist."""
    from custom_components.autodoctor.models import IssueType

    assert hasattr(IssueType, "SERVICE_NOT_FOUND")
    assert hasattr(IssueType, "SERVICE_MISSING_REQUIRED_PARAM")
    assert hasattr(IssueType, "SERVICE_INVALID_PARAM_TYPE")
    assert hasattr(IssueType, "SERVICE_UNKNOWN_PARAM")

    assert IssueType.SERVICE_NOT_FOUND.value == "service_not_found"
    assert (
        IssueType.SERVICE_MISSING_REQUIRED_PARAM.value
        == "service_missing_required_param"
    )
    assert IssueType.SERVICE_INVALID_PARAM_TYPE.value == "service_invalid_param_type"
    assert IssueType.SERVICE_UNKNOWN_PARAM.value == "service_unknown_param"


def test_removed_template_entity_issue_types():
    """Test that false-positive-generating TEMPLATE_* entity issue types were removed in v2.14.0."""
    removed_members = [
        "TEMPLATE_INVALID_ENTITY_ID",
        "TEMPLATE_ENTITY_NOT_FOUND",
        "TEMPLATE_INVALID_STATE",
        "TEMPLATE_ATTRIBUTE_NOT_FOUND",
        "TEMPLATE_DEVICE_NOT_FOUND",
        "TEMPLATE_AREA_NOT_FOUND",
        "TEMPLATE_ZONE_NOT_FOUND",
    ]
    for member_name in removed_members:
        assert not hasattr(IssueType, member_name), (
            f"IssueType.{member_name} should have been removed in v2.14.0"
        )

    # Exactly 13 members remain after removing 7
    assert len(IssueType) == 13, f"Expected 13 IssueType members, got {len(IssueType)}"


def test_templates_validation_group_narrowed():
    """Test that templates VALIDATION_GROUP contains only syntax-level checks after v2.14.0."""
    templates_group = VALIDATION_GROUPS["templates"]["issue_types"]
    expected = frozenset(
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


def test_validation_groups_cover_all_issue_types():
    """Test that every IssueType member appears in exactly one VALIDATION_GROUPS group."""
    all_enum_members = set(IssueType)

    # Collect all issue types from all groups
    all_grouped: list[IssueType] = []
    grouped_set: set[IssueType] = set()
    for _group_id, group_def in VALIDATION_GROUPS.items():
        issue_types = group_def["issue_types"]
        all_grouped.extend(issue_types)
        grouped_set |= issue_types

    # Every IssueType member must appear in some group (no missing members)
    missing = all_enum_members - grouped_set
    assert not missing, f"IssueType members missing from VALIDATION_GROUPS: {missing}"

    # No extra entries that aren't real IssueType members
    extras = grouped_set - all_enum_members
    assert not extras, f"VALIDATION_GROUPS contains non-IssueType entries: {extras}"

    # No duplicates across groups (each member in exactly one group)
    assert len(all_grouped) == len(all_enum_members), (
        f"Duplicate IssueType members across VALIDATION_GROUPS: "
        f"expected {len(all_enum_members)} entries, found {len(all_grouped)}"
    )
