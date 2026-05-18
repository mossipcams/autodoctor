"""IssueReporter - outputs validation issues to logs, notifications, and repairs."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

from .const import DOMAIN
from .models import IssueType, Severity, ValidationIssue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Import issue registry with fallback.
# Some HA builds resolve this reliably only via the direct module path.
has_issue_registry = False
try:
    import homeassistant.helpers.issue_registry as _ir_module

    ir = cast(Any, _ir_module)
    has_issue_registry = True
except ImportError:
    try:
        from homeassistant.helpers import issue_registry as _ir_module

        ir = cast(Any, _ir_module)
        has_issue_registry = True
    except ImportError:

        class _IssueRegistryFallback:
            class IssueSeverity:
                ERROR = "error"
                WARNING = "warning"

            @staticmethod
            def async_create_issue(*args: Any, **kwargs: Any) -> None:
                pass

            @staticmethod
            def async_delete_issue(*args: Any, **kwargs: Any) -> None:
                pass

        ir = cast(Any, _IssueRegistryFallback)


class IssueReporter:
    """Reports validation issues through multiple channels."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reporter."""
        self.hass = hass
        # Use frozenset for thread-safe reads from sensors
        self._active_issues: frozenset[str] = frozenset()
        _LOGGER.debug(
            "IssueReporter initialized, has_issue_registry=%s", has_issue_registry
        )

    @property
    def active_issues(self) -> frozenset[str]:
        """Return the set of currently active issue IDs."""
        return self._active_issues

    def _automation_issue_id(self, automation_id: str) -> str:
        """Generate a unique issue ID for an automation."""
        return automation_id.replace(".", "_")

    def _severity_to_repair(self, severity: Severity) -> str:
        """Convert our severity to HA repair severity."""
        if severity == Severity.ERROR:
            return ir.IssueSeverity.ERROR
        return ir.IssueSeverity.WARNING

    def _why_issue_matters(self, issue: ValidationIssue) -> str:
        """Return a user-facing impact summary for an issue."""
        match issue.issue_type:
            case IssueType.ENTITY_NOT_FOUND | IssueType.ENTITY_REMOVED:
                return (
                    "Home Assistant cannot resolve this entity, so the automation "
                    "may never trigger, may skip a condition, or may fail during "
                    "an action."
                )
            case IssueType.INVALID_STATE | IssueType.CASE_MISMATCH:
                return (
                    "The automation is checking a state that may never match, so it "
                    "can look enabled while doing nothing."
                )
            case IssueType.ATTRIBUTE_NOT_FOUND | IssueType.INVALID_ATTRIBUTE_VALUE:
                return (
                    "The automation depends on an attribute value that may not exist "
                    "or may never match."
                )
            case IssueType.SERVICE_NOT_FOUND:
                return (
                    "The action calls a service Home Assistant does not currently "
                    "provide."
                )
            case (
                IssueType.SERVICE_MISSING_REQUIRED_PARAM
                | IssueType.SERVICE_INVALID_PARAM_TYPE
                | IssueType.SERVICE_UNKNOWN_PARAM
                | IssueType.SERVICE_TARGET_NOT_FOUND
            ):
                return (
                    "The action may fail when Home Assistant tries to call this "
                    "service."
                )
            case (
                IssueType.TEMPLATE_SYNTAX_ERROR
                | IssueType.TEMPLATE_UNKNOWN_FILTER
                | IssueType.TEMPLATE_UNKNOWN_TEST
            ):
                return (
                    "The template may fail to render, preventing this automation "
                    "path from working."
                )
            case (
                IssueType.UNREACHABLE_STATE_COMBINATION
                | IssueType.UNREACHABLE_NUMERIC_RANGE
            ):
                return (
                    "The trigger or condition is logically unreachable, so this "
                    "automation path is unlikely to run."
                )
            case (
                IssueType.RUNTIME_AUTOMATION_OVERDUE
                | IssueType.RUNTIME_AUTOMATION_OVERACTIVE
                | IssueType.RUNTIME_AUTOMATION_BURST
            ):
                return (
                    "Recent runtime behavior differs from the learned baseline for "
                    "this automation."
                )
            case _:
                return "This can make the automation behave differently than expected."

    def _next_action_for_issue(self, issue: ValidationIssue) -> str:
        """Return a concrete next step for an issue."""
        match issue.issue_type:
            case IssueType.ENTITY_NOT_FOUND | IssueType.ENTITY_REMOVED:
                return (
                    "Update the automation to use an existing entity or restore the "
                    "missing entity."
                )
            case IssueType.INVALID_STATE | IssueType.CASE_MISMATCH:
                return (
                    "Change the expected state to one Home Assistant actually "
                    "reports for this entity."
                )
            case IssueType.ATTRIBUTE_NOT_FOUND | IssueType.INVALID_ATTRIBUTE_VALUE:
                return (
                    "Check the entity attributes in Developer Tools and update this "
                    "reference."
                )
            case IssueType.SERVICE_NOT_FOUND:
                return (
                    "Choose a registered service from Developer Tools > Services or "
                    "update the integration that provides it."
                )
            case (
                IssueType.SERVICE_MISSING_REQUIRED_PARAM
                | IssueType.SERVICE_INVALID_PARAM_TYPE
                | IssueType.SERVICE_UNKNOWN_PARAM
            ):
                return (
                    "Compare the action data with the service schema and adjust the "
                    "YAML or UI action fields."
                )
            case IssueType.SERVICE_TARGET_NOT_FOUND:
                return (
                    "Update the action target to an existing entity, device, or area."
                )
            case (
                IssueType.TEMPLATE_SYNTAX_ERROR
                | IssueType.TEMPLATE_UNKNOWN_FILTER
                | IssueType.TEMPLATE_UNKNOWN_TEST
            ):
                return (
                    "Test the template in Developer Tools > Template and fix the "
                    "failing expression."
                )
            case (
                IssueType.UNREACHABLE_STATE_COMBINATION
                | IssueType.UNREACHABLE_NUMERIC_RANGE
            ):
                return (
                    "Review the trigger and condition together; one likely "
                    "contradicts the other."
                )
            case (
                IssueType.RUNTIME_AUTOMATION_OVERDUE
                | IssueType.RUNTIME_AUTOMATION_OVERACTIVE
                | IssueType.RUNTIME_AUTOMATION_BURST
            ):
                return (
                    "Check whether the automation should still be following its "
                    "usual schedule or trigger pattern."
                )
            case _:
                return (
                    "Open the automation and review the referenced entity, "
                    "condition, template, or action."
                )

    def _format_issues_for_repair(self, issues: list[ValidationIssue]) -> str:
        """Format multiple issues into a single repair description."""
        lines = []
        for issue in issues:
            issue_heading = self._format_issue_heading(issue)
            issue_lines = [
                issue_heading,
                f"  {issue.severity.name} / {issue.confidence} confidence",
                f"  What is wrong: {issue.message}",
                f"  Why it matters: {self._why_issue_matters(issue)}",
                f"  Next action: {self._next_action_for_issue(issue)}",
            ]
            if issue.suggestion:
                issue_lines.append(f"  Did you mean '{issue.suggestion}'?")
            if issue.valid_states:
                issue_lines.append(
                    f"  Known valid states: {', '.join(issue.valid_states)}"
                )
            lines.append("\n".join(issue_lines))
        return "\n\n".join(lines)

    def _format_issue_heading(self, issue: ValidationIssue) -> str:
        """Format the first line for a Repair issue entry."""
        if (
            issue.issue_type
            in {
                IssueType.RUNTIME_AUTOMATION_OVERDUE,
                IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
                IssueType.RUNTIME_AUTOMATION_BURST,
            }
            and issue.entity_id == issue.automation_id
            and issue.automation_name
        ):
            return (
                f"• **{issue.automation_name}** (`{issue.entity_id}`, {issue.location})"
            )
        return f"• **{issue.entity_id}** ({issue.location})"

    async def async_report_issues(self, issues: list[ValidationIssue]) -> None:
        """Report validation issues grouped by automation."""
        _LOGGER.debug("async_report_issues called with %d issues", len(issues))
        if not has_issue_registry:
            _LOGGER.warning(
                "Issue registry unavailable; cannot create Repairs entries for %d issues",
                len(issues),
            )
            return
        if not issues:
            _LOGGER.info("Automation validation complete: no issues found")
            current_issue_ids: set[str] = set()
            self._clear_resolved_issues(current_issue_ids)
            # Atomic assignment - sensors read this set, so assign complete set at once
            self._active_issues = frozenset()
            return

        # Group issues by automation
        issues_by_automation: dict[str, list[ValidationIssue]] = defaultdict(list)
        for issue in issues:
            issues_by_automation[issue.automation_id].append(issue)

            _LOGGER.debug(
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
        registry_ids: set[str] = set()

        if has_issue_registry and hasattr(ir, "async_get"):
            try:
                registry = ir.async_get(self.hass)
                registry_issues = getattr(registry, "issues", {})
                registry_ids = {
                    issue_id
                    for (domain, issue_id) in registry_issues
                    if domain == DOMAIN
                }
            except Exception as err:
                _LOGGER.debug(
                    "Could not query issue registry, using memory set: %s", err
                )

        active_ids = set(self._active_issues)
        all_known_ids = active_ids | registry_ids
        resolved = all_known_ids - current_ids

        orphan_count = len(resolved - active_ids)
        if orphan_count > 0:
            _LOGGER.info("Cleaning up %d orphaned repair(s)", orphan_count)

        for issue_id in resolved:
            try:
                # Note: ir.async_delete_issue is synchronous despite the name
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            except Exception as err:
                _LOGGER.warning("Failed to delete issue %s: %s", issue_id, err)
