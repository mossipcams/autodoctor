"""IssueReporter - outputs validation issues to logs, notifications, and repairs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .const import DOMAIN
from .models import ValidationIssue, Severity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Import issue registry with fallback
try:
    from homeassistant.helpers import issue_registry as ir
    HAS_ISSUE_REGISTRY = True
except ImportError:
    HAS_ISSUE_REGISTRY = False
    class ir:  # type: ignore
        class IssueSeverity:
            ERROR = "error"
            WARNING = "warning"

        @staticmethod
        def async_create_issue(*args, **kwargs):
            pass

        @staticmethod
        def async_delete_issue(*args, **kwargs):
            pass


class IssueReporter:
    """Reports validation issues through multiple channels."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reporter."""
        self.hass = hass
        self._active_issues: set[str] = set()

    def _issue_id(self, issue: ValidationIssue) -> str:
        """Generate a unique issue ID."""
        return f"{issue.automation_id}_{issue.entity_id}_{issue.location}".replace(".", "_")

    def _severity_to_repair(self, severity: Severity) -> str:
        """Convert our severity to HA repair severity."""
        if severity == Severity.ERROR:
            return ir.IssueSeverity.ERROR
        return ir.IssueSeverity.WARNING

    async def async_report_issues(self, issues: list[ValidationIssue]) -> None:
        """Report validation issues."""
        if not issues:
            _LOGGER.info("Automation validation complete: no issues found")
            return

        current_issue_ids: set[str] = set()

        for issue in issues:
            issue_id = self._issue_id(issue)
            current_issue_ids.add(issue_id)

            log_method = _LOGGER.error if issue.severity == Severity.ERROR else _LOGGER.warning
            log_method(
                "Automation '%s': %s (entity: %s, location: %s)",
                issue.automation_name,
                issue.message,
                issue.entity_id,
                issue.location,
            )

            # Note: ir.async_create_issue is synchronous despite the name
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=self._severity_to_repair(issue.severity),
                translation_key="validation_issue",
                translation_placeholders={
                    "automation": issue.automation_name,
                    "entity": issue.entity_id,
                    "message": issue.message,
                    "suggestion": issue.suggestion or "N/A",
                    "valid_states": ", ".join(issue.valid_states) if issue.valid_states else "N/A",
                },
            )

        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == Severity.WARNING)

        message = f"Found {len(issues)} issue(s): {error_count} errors, {warning_count} warnings. Check Settings > Repairs for details."

        # Use service call for notification (more reliable than direct import)
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": message,
                "title": "Automation Validation",
                "notification_id": f"{DOMAIN}_results",
            },
        )

        self._clear_resolved_issues(current_issue_ids)
        self._active_issues = current_issue_ids

    def _clear_resolved_issues(self, current_ids: set[str]) -> None:
        """Clear issues that have been resolved."""
        resolved = self._active_issues - current_ids
        for issue_id in resolved:
            # Note: ir.async_delete_issue is synchronous despite the name
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def clear_all_issues(self) -> None:
        """Clear all issues."""
        for issue_id in self._active_issues:
            # Note: ir.async_delete_issue is synchronous despite the name
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._active_issues.clear()
