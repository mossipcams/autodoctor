"""Tests for autodoctor __init__.py."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from custom_components.autodoctor import (
    async_validate_all,
    async_validate_all_with_groups,
    async_validate_automation,
    _dedup_cross_family,
)
from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import (
    IssueType,
    Severity,
    ValidationIssue,
    VALIDATION_GROUP_ORDER,
)


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


@pytest.mark.asyncio
async def test_one_bad_automation_does_not_crash_all(mock_hass):
    """Test that one malformed automation doesn't stop validation of others."""
    # Setup mocks
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_reporter = AsyncMock()

    # First automation raises, second succeeds
    mock_analyzer.extract_state_references.side_effect = [
        Exception("Malformed config"),
        [],  # Second automation succeeds
    ]
    mock_validator.validate_all.return_value = []

    mock_hass.data[DOMAIN] = {
        "analyzer": mock_analyzer,
        "validator": mock_validator,
        "reporter": mock_reporter,
        "knowledge_base": None,
    }

    # Mock _get_automation_configs to return 2 automations
    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[
            {"id": "bad", "alias": "Bad Auto"},
            {"id": "good", "alias": "Good Auto"},
        ],
    ):
        issues = await async_validate_all(mock_hass)

    # Should have processed both automations (one failed, one succeeded)
    assert mock_analyzer.extract_state_references.call_count == 2
    assert isinstance(issues, list)


def _make_issue(issue_type: IssueType, severity: Severity) -> ValidationIssue:
    """Create a minimal ValidationIssue for testing."""
    return ValidationIssue(
        issue_type=issue_type,
        severity=severity,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.test",
        location="trigger[0]",
        message=f"Test issue ({issue_type.value})",
    )


@pytest.fixture
def grouped_hass(mock_hass):
    """Create mock hass pre-configured with all validators for grouped tests."""
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_reporter = AsyncMock()
    mock_jinja = MagicMock()
    mock_service = MagicMock()
    mock_service.async_load_descriptions = AsyncMock()

    mock_hass.data[DOMAIN] = {
        "analyzer": mock_analyzer,
        "validator": mock_validator,
        "reporter": mock_reporter,
        "jinja_validator": mock_jinja,
        "service_validator": mock_service,
        "knowledge_base": None,
        "issues": [],
        "validation_issues": [],
        "validation_last_run": None,
    }

    return mock_hass


@pytest.mark.asyncio
async def test_validate_all_with_groups_classification(grouped_hass):
    """Test that issues are classified into the correct groups."""
    # Set up entity-state issues from state ref validator
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    # Set up template issues from jinja validator
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]

    # Set up service issues from service validator
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [
        service_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Verify return structure
    assert "group_issues" in result
    assert "group_durations" in result
    assert "all_issues" in result
    assert "timestamp" in result

    # Verify entity issue classified into entity_state group
    assert entity_issue in result["group_issues"]["entity_state"]
    assert entity_issue not in result["group_issues"]["templates"]
    assert entity_issue not in result["group_issues"]["services"]

    # Verify template issue classified into templates group
    assert template_issue in result["group_issues"]["templates"]
    assert template_issue not in result["group_issues"]["entity_state"]

    # Verify service issue classified into services group
    assert service_issue in result["group_issues"]["services"]
    assert service_issue not in result["group_issues"]["entity_state"]

    # All issues present in flat list
    assert len(result["all_issues"]) == 3


@pytest.mark.asyncio
async def test_validate_all_with_groups_timing(grouped_hass):
    """Test that each group has a non-negative duration_ms value."""
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Every group must have a duration
    for gid in VALIDATION_GROUP_ORDER:
        duration = result["group_durations"][gid]
        assert isinstance(duration, int), f"Group '{gid}' duration is not an int"
        assert duration >= 0, f"Group '{gid}' has negative duration: {duration}"


@pytest.mark.asyncio
async def test_validate_all_with_groups_status_logic(grouped_hass):
    """Test group status: fail for errors, warning for warnings only, pass for clean."""
    # entity_state gets an ERROR issue -> status should be "fail"
    error_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [error_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    # templates gets a WARNING issue -> status should be "warning"
    warning_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        warning_issue
    ]

    # services gets no issues -> status should be "pass"
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Import the status helper to verify status logic matches group issues
    from custom_components.autodoctor.websocket_api import _compute_group_status

    assert _compute_group_status(result["group_issues"]["entity_state"]) == "fail"
    assert _compute_group_status(result["group_issues"]["templates"]) == "warning"
    assert _compute_group_status(result["group_issues"]["services"]) == "pass"


@pytest.mark.asyncio
async def test_validate_all_with_groups_empty_automations(grouped_hass):
    """Test that empty automation list returns empty group structure."""
    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # All groups should be empty
    for gid in VALIDATION_GROUP_ORDER:
        assert result["group_issues"][gid] == []
        assert result["group_durations"][gid] == 0

    assert result["all_issues"] == []
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_validate_automation_includes_service_validation(grouped_hass):
    """Test that async_validate_automation includes service validation (C1 fix).

    Previously, async_validate_automation skipped service validation entirely.
    After consolidation, it routes through the shared core which includes
    all three validator families.
    """
    # Set up a service issue
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [
        service_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    # No issues from other validators
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.test")

    # Service issue MUST be present (this was the C1 bug)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND

    # Verify service validator was actually called
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.assert_called_once()


@pytest.mark.asyncio
async def test_validate_automation_includes_all_families(grouped_hass):
    """Test that async_validate_automation runs all three validator families."""
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)

    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [
        service_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.test")

    # All three families should contribute issues
    assert len(issues) == 3
    issue_types = {i.issue_type for i in issues}
    assert IssueType.TEMPLATE_SYNTAX_ERROR in issue_types
    assert IssueType.SERVICE_NOT_FOUND in issue_types
    assert IssueType.ENTITY_NOT_FOUND in issue_types


@pytest.mark.asyncio
async def test_validate_automation_not_found(grouped_hass):
    """Test that async_validate_automation returns empty when automation not found."""
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "other", "alias": "Other"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.nonexistent")

    assert issues == []


@pytest.mark.asyncio
async def test_validate_all_is_thin_wrapper(grouped_hass):
    """Test that async_validate_all returns same issues as grouped version."""
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        flat_issues = await async_validate_all(grouped_hass)

    # Should return a flat list, not a dict
    assert isinstance(flat_issues, list)
    assert len(flat_issues) == 1
    assert flat_issues[0] is entity_issue


# --- Cross-family deduplication tests (C5) ---


def _make_issue_for_entity(
    issue_type: IssueType,
    severity: Severity,
    entity_id: str = "sensor.test",
    automation_id: str = "automation.test",
    message: str | None = None,
) -> ValidationIssue:
    """Create a ValidationIssue for dedup testing with explicit entity_id."""
    return ValidationIssue(
        issue_type=issue_type,
        severity=severity,
        automation_id=automation_id,
        automation_name="Test",
        entity_id=entity_id,
        location="trigger[0]",
        message=message or f"Test issue ({issue_type.value})",
    )


def test_dedup_cross_family_entity_not_found():
    """Test that ENTITY_NOT_FOUND and TEMPLATE_ENTITY_NOT_FOUND are deduped.

    When both validator.py and jinja_validator report the same entity as missing,
    only the non-TEMPLATE (authority) variant should be kept.
    """
    entity_issue = _make_issue_for_entity(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )
    template_issue = _make_issue_for_entity(
        IssueType.TEMPLATE_ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )

    group_issues = {
        "entity_state": [entity_issue],
        "services": [],
        "templates": [template_issue],
    }

    result = _dedup_cross_family(group_issues)

    # entity_state keeps its issue (preferred)
    assert entity_issue in result["entity_state"]
    # templates loses its duplicate
    assert template_issue not in result["templates"]
    assert len(result["templates"]) == 0

    # Total issue count: 1 (not 2)
    total = sum(len(issues) for issues in result.values())
    assert total == 1


def test_dedup_cross_family_prefers_authority():
    """Test that the non-TEMPLATE variant is preferred even if seen second."""
    # template_issue added to templates group first
    template_issue = _make_issue_for_entity(
        IssueType.TEMPLATE_ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )
    # entity_issue added to entity_state group second
    entity_issue = _make_issue_for_entity(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )

    group_issues = {
        "entity_state": [entity_issue],
        "services": [],
        "templates": [template_issue],
    }

    result = _dedup_cross_family(group_issues)

    # The preferred (non-TEMPLATE) issue should survive
    assert entity_issue in result["entity_state"]
    assert template_issue not in result["templates"]


def test_dedup_different_entity_ids_not_deduped():
    """Test that issues for different entities are NOT deduped."""
    issue_a = _make_issue_for_entity(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )
    issue_b = _make_issue_for_entity(
        IssueType.TEMPLATE_ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.bedroom"
    )

    group_issues = {
        "entity_state": [issue_a],
        "services": [],
        "templates": [issue_b],
    }

    result = _dedup_cross_family(group_issues)

    # Both should be kept -- different entities
    assert issue_a in result["entity_state"]
    assert issue_b in result["templates"]
    total = sum(len(issues) for issues in result.values())
    assert total == 2


def test_dedup_different_automations_not_deduped():
    """Test that issues for different automations are NOT deduped."""
    issue_a = _make_issue_for_entity(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR,
        entity_id="light.kitchen", automation_id="automation.morning",
    )
    issue_b = _make_issue_for_entity(
        IssueType.TEMPLATE_ENTITY_NOT_FOUND, Severity.ERROR,
        entity_id="light.kitchen", automation_id="automation.evening",
    )

    group_issues = {
        "entity_state": [issue_a],
        "services": [],
        "templates": [issue_b],
    }

    result = _dedup_cross_family(group_issues)

    # Both should be kept -- different automations
    total = sum(len(issues) for issues in result.values())
    assert total == 2


def test_dedup_non_family_issues_never_deduped():
    """Test that issues without a semantic family are never deduped."""
    syntax_issue = _make_issue_for_entity(
        IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING, entity_id="sensor.test"
    )
    service_issue = _make_issue_for_entity(
        IssueType.SERVICE_NOT_FOUND, Severity.ERROR, entity_id="sensor.test"
    )

    group_issues = {
        "entity_state": [],
        "services": [service_issue],
        "templates": [syntax_issue],
    }

    result = _dedup_cross_family(group_issues)

    # Both kept -- neither has a semantic family overlap
    assert syntax_issue in result["templates"]
    assert service_issue in result["services"]
    total = sum(len(issues) for issues in result.values())
    assert total == 2


def test_dedup_attribute_family():
    """Test dedup for attribute_missing semantic family."""
    attr_issue = _make_issue_for_entity(
        IssueType.ATTRIBUTE_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )
    template_attr_issue = _make_issue_for_entity(
        IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )

    group_issues = {
        "entity_state": [attr_issue],
        "services": [],
        "templates": [template_attr_issue],
    }

    result = _dedup_cross_family(group_issues)

    # Preferred variant survives
    assert attr_issue in result["entity_state"]
    assert template_attr_issue not in result["templates"]
    total = sum(len(issues) for issues in result.values())
    assert total == 1


def test_dedup_state_family():
    """Test dedup for invalid_state semantic family."""
    state_issue = _make_issue_for_entity(
        IssueType.INVALID_STATE, Severity.ERROR, entity_id="person.matt"
    )
    template_state_issue = _make_issue_for_entity(
        IssueType.TEMPLATE_INVALID_STATE, Severity.ERROR, entity_id="person.matt"
    )

    group_issues = {
        "entity_state": [state_issue],
        "services": [],
        "templates": [template_state_issue],
    }

    result = _dedup_cross_family(group_issues)

    assert state_issue in result["entity_state"]
    assert template_state_issue not in result["templates"]
    total = sum(len(issues) for issues in result.values())
    assert total == 1


@pytest.mark.asyncio
async def test_dedup_integration_through_validate_all(grouped_hass):
    """Test that cross-family dedup works through the full validation pipeline."""
    # Both validators report the same entity as missing
    entity_issue = _make_issue_for_entity(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )
    template_issue = _make_issue_for_entity(
        IssueType.TEMPLATE_ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.kitchen"
    )

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Only 1 issue should survive (deduped from 2)
    assert len(result["all_issues"]) == 1
    assert result["all_issues"][0].issue_type == IssueType.ENTITY_NOT_FOUND
