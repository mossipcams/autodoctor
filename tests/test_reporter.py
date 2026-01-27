"""Tests for IssueReporter."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.reporter import IssueReporter
from custom_components.autodoctor.models import ValidationIssue, Severity


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

    with patch(
        "custom_components.autodoctor.reporter.ir.async_create_issue",
        new_callable=AsyncMock,
    ) as mock_create, patch(
        "custom_components.autodoctor.reporter.async_create",
        new_callable=AsyncMock,
    ):
        await reporter.async_report_issues(issues)
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_report_issues_creates_notification(hass: HomeAssistant, reporter):
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
        "custom_components.autodoctor.reporter.ir.async_create_issue",
        new_callable=AsyncMock,
    ), patch(
        "custom_components.autodoctor.reporter.async_create",
        new_callable=AsyncMock,
    ) as mock_notify:
        await reporter.async_report_issues(issues)
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_clear_resolved_issues(hass: HomeAssistant, reporter):
    """Test clearing resolved issues."""
    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue",
        new_callable=AsyncMock,
    ) as mock_delete:
        reporter._active_issues = {"issue_1", "issue_2"}
        await reporter.async_clear_resolved({"issue_1"})
        mock_delete.assert_called_once()
