"""Tests for data models."""

import pytest

from custom_components.autodoctor.models import (
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


@pytest.mark.skip(reason="OutcomeReport not yet implemented in models.py")
def test_outcome_report_creation():
    """Test OutcomeReport dataclass."""
    from custom_components.autodoctor.models import OutcomeReport, Verdict

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


def test_entity_action_creation():
    """Test EntityAction dataclass."""
    from custom_components.autodoctor.models import EntityAction

    action = EntityAction(
        automation_id="automation.motion_lights",
        entity_id="light.living_room",
        action="turn_on",
        value=None,
        conditions=[],
    )

    assert action.automation_id == "automation.motion_lights"
    assert action.entity_id == "light.living_room"
    assert action.action == "turn_on"
    assert action.conditions == []


def test_conflict_creation():
    """Test Conflict dataclass."""
    from custom_components.autodoctor.models import Conflict, Severity

    conflict = Conflict(
        entity_id="light.living_room",
        automation_a="automation.motion_lights",
        automation_b="automation.away_mode",
        automation_a_name="Motion Lights",
        automation_b_name="Away Mode",
        action_a="turn_on",
        action_b="turn_off",
        severity=Severity.ERROR,
        explanation="Both automations affect light.living_room",
        scenario="Motion detected while nobody_home",
    )

    assert conflict.entity_id == "light.living_room"
    assert conflict.severity == Severity.ERROR


def test_conflict_to_dict():
    """Test Conflict serialization."""
    from custom_components.autodoctor.models import Conflict, Severity

    conflict = Conflict(
        entity_id="light.living_room",
        automation_a="automation.motion_lights",
        automation_b="automation.away_mode",
        automation_a_name="Motion Lights",
        automation_b_name="Away Mode",
        action_a="turn_on",
        action_b="turn_off",
        severity=Severity.ERROR,
        explanation="Both automations affect light.living_room",
        scenario="Motion detected while nobody_home",
    )

    d = conflict.to_dict()
    assert d["entity_id"] == "light.living_room"
    assert d["severity"] == "error"
    assert d["automation_a"] == "automation.motion_lights"


def test_conflict_suppression_key():
    """Test Conflict suppression key generation."""
    from custom_components.autodoctor.models import Conflict, Severity

    conflict = Conflict(
        entity_id="light.living_room",
        automation_a="automation.motion_lights",
        automation_b="automation.away_mode",
        automation_a_name="Motion Lights",
        automation_b_name="Away Mode",
        action_a="turn_on",
        action_b="turn_off",
        severity=Severity.ERROR,
        explanation="Both automations affect light.living_room",
        scenario="Motion detected while nobody_home",
    )

    key = conflict.get_suppression_key()
    assert (
        key
        == "automation.away_mode:automation.motion_lights:light.living_room:conflict"
    )


def test_entity_action_conditions_type():
    """Test that EntityAction.conditions accepts ConditionInfo objects."""
    from custom_components.autodoctor.models import ConditionInfo, EntityAction

    condition = ConditionInfo(entity_id="input_boolean.mode", required_states={"night"})
    action = EntityAction(
        automation_id="automation.test",
        entity_id="light.kitchen",
        action="turn_on",
        value=None,
        conditions=[condition],
    )

    assert len(action.conditions) == 1
    assert action.conditions[0].entity_id == "input_boolean.mode"
    assert action.conditions[0].required_states == {"night"}


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
        location="condition[0]",  # Different location
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    # Should be equal because automation_id, issue_type, entity_id, and message match
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
        location="condition[0]",  # Different location
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

    # issue1 and issue2 are duplicates (same key fields)
    # issue3 is different (different automation_id)
    issues_set = {issue1, issue2, issue3}
    assert len(issues_set) == 2  # Only 2 unique issues
