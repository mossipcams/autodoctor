"""Tests for IssueReporter."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.autodoctor.models import Severity, ValidationIssue
from custom_components.autodoctor.reporter import IssueReporter


@pytest.fixture
def reporter(hass: HomeAssistant) -> IssueReporter:
    """Create an IssueReporter instance.

    Returns a reporter with no active issues, ready for testing issue
    reporting and lifecycle management.
    """
    return IssueReporter(hass)


def test_reporter_initialization(reporter: IssueReporter) -> None:
    """Test IssueReporter initializes with empty active issues set.

    Ensures the reporter starts in a clean state with no pre-existing
    issues, ready to track validation results.
    """
    assert reporter is not None
    assert len(reporter._active_issues) == 0


@pytest.mark.asyncio
async def test_report_issues_creates_repair(
    hass: HomeAssistant, reporter: IssueReporter
) -> None:
    """Test that async_report_issues creates repair entries.

    When validation issues are reported, they should be converted into
    Home Assistant repair entries that appear in the UI for users to see.
    """
    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="person.matt",
            location="trigger[0].to",
            message="State 'away' is not valid",
            suggestion="not_home",
            valid_states=["home", "not_home"],
        )
    ]

    # Register persistent_notification service for test
    async def mock_notification_service(call: ServiceCall) -> None:
        pass

    hass.services.async_register(
        "persistent_notification", "create", mock_notification_service
    )

    with patch(
        "custom_components.autodoctor.reporter.ir.async_create_issue",
    ) as mock_create:
        await reporter.async_report_issues(issues)
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_clear_resolved_issues(
    hass: HomeAssistant, reporter: IssueReporter
) -> None:
    """Test that resolved issues are deleted from repair registry.

    When an issue no longer appears in validation results, it should be
    removed from Home Assistant's repair registry so the UI stays clean.
    """
    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue",
    ) as mock_delete:
        reporter._active_issues = frozenset({"issue_1", "issue_2"})
        reporter._clear_resolved_issues({"issue_1"})
        mock_delete.assert_called_once()


def test_clear_resolved_issues_continues_on_delete_error(
    hass: HomeAssistant,
) -> None:
    """Test that failed issue deletion doesn't prevent other deletions.

    If deleting one repair entry fails (e.g., due to registry error), the
    reporter should continue attempting to delete other resolved issues
    rather than stopping at the first error.
    """
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset({"issue1", "issue2", "issue3"})

    delete_calls: list[str] = []

    def mock_delete(hass: HomeAssistant, domain: str, issue_id: str) -> None:
        delete_calls.append(issue_id)
        if issue_id == "issue2":
            raise Exception("Delete failed")

    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue",
        side_effect=mock_delete,
    ):
        reporter._clear_resolved_issues(set())  # All should be cleared

    # Should have attempted all 3 deletes
    assert len(delete_calls) == 3


def test_clear_resolved_issues_queries_registry_for_orphans(
    hass: HomeAssistant,
) -> None:
    """Reporter should delete registry orphans even when memory set is empty."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset()

    mock_registry = type(
        "MockRegistry",
        (),
        {
            "issues": {
                ("autodoctor", "orphan_1"): object(),
                ("autodoctor", "orphan_2"): object(),
                ("other_domain", "ignore_me"): object(),
            }
        },
    )()

    with (
        patch(
            "custom_components.autodoctor.reporter.ir.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.autodoctor.reporter.ir.async_delete_issue"
        ) as mock_delete,
    ):
        reporter._clear_resolved_issues(set())

    deleted_ids = {call.args[2] for call in mock_delete.call_args_list}
    assert deleted_ids == {"orphan_1", "orphan_2"}


def test_clear_resolved_issues_preserves_current_ids_from_registry(
    hass: HomeAssistant,
) -> None:
    """Reporter should keep current IDs even if they exist in registry."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset()

    mock_registry = type(
        "MockRegistry",
        (),
        {
            "issues": {
                ("autodoctor", "keep"): object(),
                ("autodoctor", "orphan"): object(),
            }
        },
    )()

    with (
        patch(
            "custom_components.autodoctor.reporter.ir.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.autodoctor.reporter.ir.async_delete_issue"
        ) as mock_delete,
    ):
        reporter._clear_resolved_issues({"keep"})

    deleted_ids = [call.args[2] for call in mock_delete.call_args_list]
    assert deleted_ids == ["orphan"]


def test_clear_resolved_issues_fallback_without_issue_registry(
    hass: HomeAssistant,
) -> None:
    """When registry support is unavailable, memory cleanup still works."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset({"mem"})

    with (
        patch("custom_components.autodoctor.reporter.has_issue_registry", False),
        patch(
            "custom_components.autodoctor.reporter.ir.async_delete_issue"
        ) as mock_delete,
    ):
        reporter._clear_resolved_issues(set())

    mock_delete.assert_called_once_with(hass, "autodoctor", "mem")


def test_clear_resolved_issues_registry_exception_falls_back(
    hass: HomeAssistant,
) -> None:
    """Registry lookup errors should not break memory-based cleanup."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset({"mem"})

    with (
        patch("custom_components.autodoctor.reporter.has_issue_registry", True),
        patch(
            "custom_components.autodoctor.reporter.ir.async_get",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "custom_components.autodoctor.reporter.ir.async_delete_issue"
        ) as mock_delete,
    ):
        reporter._clear_resolved_issues(set())

    mock_delete.assert_called_once_with(hass, "autodoctor", "mem")


@pytest.mark.asyncio
async def test_async_report_issues_cleans_orphans_after_restart(
    hass: HomeAssistant,
) -> None:
    """Reporting after restart should clear stale registry repairs."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset()

    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.new",
            automation_name="New",
            entity_id="light.kitchen",
            location="trigger[0]",
            message="Entity not found",
        )
    ]

    mock_registry = type(
        "MockRegistry",
        (),
        {
            "issues": {
                ("autodoctor", "automation_old"): object(),
            }
        },
    )()

    with (
        patch("custom_components.autodoctor.reporter.has_issue_registry", True),
        patch(
            "custom_components.autodoctor.reporter.ir.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.autodoctor.reporter.ir.async_create_issue"
        ) as mock_create,
        patch(
            "custom_components.autodoctor.reporter.ir.async_delete_issue"
        ) as mock_delete,
    ):
        await reporter.async_report_issues(issues)

    mock_create.assert_called_once()
    deleted_ids = [call.args[2] for call in mock_delete.call_args_list]
    assert deleted_ids == ["automation_old"]
    assert reporter._active_issues == frozenset({"automation_new"})


def test_clear_resolved_issues_logs_orphan_count(
    hass: HomeAssistant,
) -> None:
    """Reporter should emit orphan cleanup count for registry-only issues."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset()

    mock_registry = type(
        "MockRegistry",
        (),
        {
            "issues": {
                ("autodoctor", "orphan_1"): object(),
                ("autodoctor", "orphan_2"): object(),
            }
        },
    )()

    with (
        patch(
            "custom_components.autodoctor.reporter.ir.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.autodoctor.reporter.ir.async_delete_issue"
        ) as mock_delete,
        patch("custom_components.autodoctor.reporter._LOGGER.info") as mock_info,
    ):
        reporter._clear_resolved_issues(set())

    assert mock_delete.call_count == 2
    mock_info.assert_called_once_with("Cleaning up %d orphaned repair(s)", 2)


# --- Quick task 015: Coverage improvements for reporter.py ---


@pytest.mark.asyncio
async def test_clear_all_issues(hass: HomeAssistant) -> None:
    """Test clear_all_issues removes all active issues from registry."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset({"issue_a", "issue_b"})

    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue"
    ) as mock_delete:
        reporter.clear_all_issues()

    assert reporter._active_issues == frozenset()
    assert mock_delete.call_count == 2


@pytest.mark.asyncio
async def test_report_issues_create_exception_continues(hass: HomeAssistant) -> None:
    """Test that issue creation exception doesn't stop other issues."""
    reporter = IssueReporter(hass)

    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test1",
            automation_name="Test 1",
            entity_id="sensor.a",
            location="trigger[0]",
            message="Issue 1",
        ),
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test2",
            automation_name="Test 2",
            entity_id="sensor.b",
            location="trigger[0]",
            message="Issue 2",
        ),
    ]

    with patch(
        "custom_components.autodoctor.reporter.ir.async_create_issue",
        side_effect=Exception("Failed"),
    ):
        await reporter.async_report_issues(issues)

    # Both attempts should have been made despite failures
    assert len(reporter._active_issues) == 2


def test_severity_to_repair_warning(hass: HomeAssistant) -> None:
    """Test severity conversion for WARNING level."""
    reporter = IssueReporter(hass)

    from custom_components.autodoctor.reporter import ir

    result = reporter._severity_to_repair(Severity.WARNING)
    assert result == ir.IssueSeverity.WARNING


def test_severity_to_repair_error(hass: HomeAssistant) -> None:
    """Test severity conversion for ERROR level."""
    reporter = IssueReporter(hass)

    from custom_components.autodoctor.reporter import ir

    result = reporter._severity_to_repair(Severity.ERROR)
    assert result == ir.IssueSeverity.ERROR


def test_format_issues_for_repair(hass: HomeAssistant) -> None:
    """Test formatting multiple issues into repair description."""
    reporter = IssueReporter(hass)

    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="sensor.temp",
            location="trigger[0]",
            message="Invalid state",
        ),
        ValidationIssue(
            severity=Severity.WARNING,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="sensor.humidity",
            location="action[1]",
            message="Unknown entity",
        ),
    ]

    result = reporter._format_issues_for_repair(issues)

    assert "sensor.temp" in result
    assert "sensor.humidity" in result
    assert "trigger[0]" in result
    assert "action[1]" in result
    assert "Invalid state" in result
    assert "Unknown entity" in result


@pytest.mark.asyncio
async def test_report_issues_groups_by_automation(hass: HomeAssistant) -> None:
    """Test that issues are grouped by automation ID for repair creation."""
    reporter = IssueReporter(hass)

    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.auto1",
            automation_name="Auto 1",
            entity_id="sensor.a",
            location="trigger[0]",
            message="Issue A",
        ),
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.auto2",
            automation_name="Auto 2",
            entity_id="sensor.b",
            location="trigger[0]",
            message="Issue B",
        ),
    ]

    with patch(
        "custom_components.autodoctor.reporter.ir.async_create_issue"
    ) as mock_create:
        await reporter.async_report_issues(issues)

    # Should create one repair per automation
    assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_report_issues_uses_highest_severity(hass: HomeAssistant) -> None:
    """Test that highest severity (ERROR) is used when automation has mixed severities."""
    reporter = IssueReporter(hass)

    issues = [
        ValidationIssue(
            severity=Severity.WARNING,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="sensor.a",
            location="trigger[0]",
            message="Warning issue",
        ),
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="sensor.b",
            location="action[0]",
            message="Error issue",
        ),
    ]

    from custom_components.autodoctor.reporter import ir

    with patch(
        "custom_components.autodoctor.reporter.ir.async_create_issue"
    ) as mock_create:
        await reporter.async_report_issues(issues)

    call_kwargs = mock_create.call_args[1]
    assert call_kwargs["severity"] == ir.IssueSeverity.ERROR


@pytest.mark.asyncio
async def test_report_issues_no_issues_logs_clean(hass: HomeAssistant) -> None:
    """Test that empty issue list logs clean validation without creating repairs."""
    reporter = IssueReporter(hass)

    with patch(
        "custom_components.autodoctor.reporter.ir.async_create_issue"
    ) as mock_create:
        await reporter.async_report_issues([])

    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_async_report_issues_empty_clears_existing_repairs(
    hass: HomeAssistant,
) -> None:
    """Empty issue reports should clear previously active repair issues."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset({"automation_test"})

    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue"
    ) as mock_delete:
        await reporter.async_report_issues([])

    mock_delete.assert_called_once_with(hass, "autodoctor", "automation_test")
    assert reporter._active_issues == frozenset()


def test_format_issues_for_repair_includes_suggestion(hass: HomeAssistant) -> None:
    """Test that repair text includes suggestion hint when issue.suggestion is set."""
    reporter = IssueReporter(hass)

    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="person.matt",
            location="trigger[0].to",
            message="State 'away' is not valid",
            suggestion="not_home",
        )
    ]

    result = reporter._format_issues_for_repair(issues)

    assert "Did you mean 'not_home'?" in result


def test_format_issues_for_repair_no_suggestion_unchanged(hass: HomeAssistant) -> None:
    """Test that repair text is unchanged when issue.suggestion is None."""
    reporter = IssueReporter(hass)

    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="sensor.temp",
            location="trigger[0]",
            message="Entity not found",
            suggestion=None,
        )
    ]

    result = reporter._format_issues_for_repair(issues)

    assert "Did you mean" not in result
    assert "sensor.temp" in result
    assert "Entity not found" in result
