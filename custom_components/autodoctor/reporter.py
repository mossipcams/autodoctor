"""IssueReporter - outputs validation issues to logs, notifications, and repairs."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from .const import DOMAIN
from .models import Severity, ValidationIssue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Import issue registry with fallback
try:
    from homeassistant.helpers import (
        issue_registry as ir,  # pyright: ignore[reportAssignmentType]
    )

    HAS_ISSUE_REGISTRY = True
except ImportError:
    HAS_ISSUE_REGISTRY = False  # pyright: ignore[reportConstantRedefinition]

    class ir:
        class IssueSeverity:
            ERROR = "error"
            WARNING = "warning"

        @staticmethod
        def async_create_issue(*args: Any, **kwargs: Any) -> None:
            pass

        @staticmethod
        def async_delete_issue(*args: Any, **kwargs: Any) -> None:
            pass


class IssueReporter:
    """Reports validation issues through multiple channels."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reporter."""
        self.hass = hass
        # Use frozenset for thread-safe reads from sensors
        self._active_issues: frozenset[str] = frozenset()
        _LOGGER.debug(
            "IssueReporter initialized, HAS_ISSUE_REGISTRY=%s", HAS_ISSUE_REGISTRY
        )

    def _automation_issue_id(self, automation_id: str) -> str:
        """Generate a unique issue ID for an automation."""
        return automation_id.replace(".", "_")

    def _severity_to_repair(self, severity: Severity) -> str:
        """Convert our severity to HA repair severity."""
        if severity == Severity.ERROR:
            return ir.IssueSeverity.ERROR
        return ir.IssueSeverity.WARNING

    def _format_issues_for_repair(self, issues: list[ValidationIssue]) -> str:
        """Format multiple issues into a single repair description."""
        lines = []
        for issue in issues:
            lines.append(f"• **{issue.entity_id}** ({issue.location}): {issue.message}")
        return "\n".join(lines)

    async def async_report_issues(self, issues: list[ValidationIssue]) -> None:
        """Report validation issues grouped by automation."""
        _LOGGER.debug("async_report_issues called with %d issues", len(issues))
        if not issues:
            _LOGGER.info("Automation validation complete: no issues found")
            return

        # Group issues by automation
        issues_by_automation: dict[str, list[ValidationIssue]] = defaultdict(list)
        for issue in issues:
            issues_by_automation[issue.automation_id].append(issue)

            # Still log each issue individually
            log_method = (
                _LOGGER.error if issue.severity == Severity.ERROR else _LOGGER.warning
            )
            log_method(
                "Automation '%s': %s (entity: %s, location: %s)",
                issue.automation_name,
                issue.message,
                issue.entity_id,
                issue.location,
            )

        current_issue_ids: set[str] = set()

        # Create one repair per automation
        for automation_id, automation_issues in issues_by_automation.items():
            issue_id = self._automation_issue_id(automation_id)
            current_issue_ids.add(issue_id)

            automation_name = automation_issues[0].automation_name
            issue_count = len(automation_issues)

            # Use highest severity among all issues for this automation
            has_error = any(i.severity == Severity.ERROR for i in automation_issues)
            severity = Severity.ERROR if has_error else Severity.WARNING

            # Format all issues for this automation
            issues_text = self._format_issues_for_repair(automation_issues)

            # Note: ir.async_create_issue is synchronous despite the name
            _LOGGER.debug(
                "Creating repair issue: domain=%s, issue_id=%s, severity=%s, automation=%s",
                DOMAIN,
                issue_id,
                severity,
                automation_name,
            )
            try:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    is_persistent=True,
                    issue_domain=DOMAIN,
                    severity=self._severity_to_repair(severity),
                    translation_key="automation_issues",
                    translation_placeholders={
                        "automation": automation_name,
                        "count": str(issue_count),
                        "issues": issues_text,
                    },
                )
                _LOGGER.debug("Repair issue created: %s", issue_id)
            except Exception as err:
                _LOGGER.error("Failed to create repair issue %s: %s", issue_id, err)

        # Clear resolved issues before updating active set
        self._clear_resolved_issues(current_issue_ids)
        # Atomic assignment - sensors read this set, so assign complete set at once
        self._active_issues = frozenset(current_issue_ids)

    def _clear_resolved_issues(self, current_ids: set[str]) -> None:
        """Clear issues that have been resolved."""
        resolved = self._active_issues - current_ids
        for issue_id in resolved:
            try:
                # Note: ir.async_delete_issue is synchronous despite the name
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            except Exception as err:
                _LOGGER.warning("Failed to delete issue %s: %s", issue_id, err)

    def clear_all_issues(self) -> None:
        """Clear all issues."""
        # Take snapshot of current issues before clearing
        issues_to_clear = self._active_issues
        for issue_id in issues_to_clear:
            # Note: ir.async_delete_issue is synchronous despite the name
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        # Atomic assignment
        self._active_issues = frozenset()
