"""Tests for IssueReporter."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.automation_mutation_tester.reporter import IssueReporter
from custom_components.automation_mutation_tester.models import ValidationIssue, Severity


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def reporter(mock_hass):
    """Create an IssueReporter instance."""
    return IssueReporter(mock_hass)


def test_reporter_initialization(reporter):
    """Test reporter can be initialized."""
    assert reporter is not None


@pytest.mark.asyncio
async def test_report_issues_creates_repair(mock_hass, reporter):
    """Test that reporting issues creates repair entries."""
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

    with patch(
        "custom_components.automation_mutation_tester.reporter.ir.async_create_issue"
    ) as mock_create:
        await reporter.async_report_issues(issues)
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_report_issues_creates_notification(mock_hass, reporter):
    """Test that reporting issues creates a notification."""
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

    with patch(
        "custom_components.automation_mutation_tester.reporter.ir.async_create_issue"
    ), patch(
        "custom_components.automation_mutation_tester.reporter.async_create"
    ) as mock_notify:
        await reporter.async_report_issues(issues)
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_clear_resolved_issues(mock_hass, reporter):
    """Test clearing resolved issues."""
    with patch(
        "custom_components.automation_mutation_tester.reporter.ir.async_delete_issue"
    ) as mock_delete:
        reporter._active_issues = {"issue_1", "issue_2"}
        await reporter.async_clear_resolved({"issue_1"})
        mock_delete.assert_called_once()
