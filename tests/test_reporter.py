"""Tests for IssueReporter."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.models import Severity, ValidationIssue
from custom_components.autodoctor.reporter import IssueReporter


@pytest.fixture
def reporter(hass: HomeAssistant):
    """Create an IssueReporter instance."""
    return IssueReporter(hass)


def test_reporter_initialization(reporter):
    """Test reporter can be initialized."""
    assert reporter is not None


@pytest.mark.asyncio
async def test_report_issues_creates_repair(hass: HomeAssistant, reporter):
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

    # Register persistent_notification service for test
    async def mock_notification_service(call):
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
async def test_clear_resolved_issues(hass: HomeAssistant, reporter):
    """Test clearing resolved issues."""
    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue",
    ) as mock_delete:
        reporter._active_issues = frozenset({"issue_1", "issue_2"})
        reporter._clear_resolved_issues({"issue_1"})
        mock_delete.assert_called_once()


def test_clear_resolved_issues_continues_on_delete_error(hass: HomeAssistant):
    """Test that one failed delete doesn't stop others."""
    reporter = IssueReporter(hass)
    reporter._active_issues = frozenset({"issue1", "issue2", "issue3"})

    delete_calls = []

    def mock_delete(hass, domain, issue_id):
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
