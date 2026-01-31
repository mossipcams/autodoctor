"""WebSocket API for Autodoctor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .validator import get_entity_suggestion
from .models import IssueType, Severity, ValidationIssue, VALIDATION_GROUPS, VALIDATION_GROUP_ORDER

if TYPE_CHECKING:
    from .suppression_store import SuppressionStore

_LOGGER = logging.getLogger(__name__)

async def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Set up WebSocket API."""
    websocket_api.async_register_command(hass, websocket_get_issues)
    websocket_api.async_register_command(hass, websocket_refresh)
    websocket_api.async_register_command(hass, websocket_get_validation)
    websocket_api.async_register_command(hass, websocket_run_validation)
    websocket_api.async_register_command(hass, websocket_suppress)
    websocket_api.async_register_command(hass, websocket_clear_suppressions)
    websocket_api.async_register_command(hass, websocket_run_validation_steps)
    websocket_api.async_register_command(hass, websocket_get_validation_steps)

def _format_issues_with_fixes(
    hass: HomeAssistant,
    issues: list,
    all_entity_ids: list[str] | None = None,
) -> list[dict]:
    """Format issues with fix suggestions using simplified fix engine.

    Args:
        hass: Home Assistant instance.
        issues: List of ValidationIssue objects to format.
        all_entity_ids: Pre-computed entity ID list.  When *None* (default),
            entity IDs are fetched from ``hass.states``.  Callers that invoke
            this function multiple times in the same handler should pass a
            shared list to avoid redundant lookups.
    """
    if all_entity_ids is None:
        all_entity_ids = [s.entity_id for s in hass.states.async_all()]

    issues_with_fixes = []

    for issue in issues:
        fix = None

        # Generate suggestion based on issue type
        if issue.issue_type in (IssueType.ENTITY_NOT_FOUND, IssueType.ENTITY_REMOVED):
            suggestion = get_entity_suggestion(issue.entity_id, all_entity_ids)
            if suggestion:
                fix = {
                    "description": f"Did you mean '{suggestion}'?",
                    "confidence": 0.8,
                    "fix_value": suggestion,
                }

        automation_id = (
            issue.automation_id.replace("automation.", "")
            if issue.automation_id
            else ""
        )
        issues_with_fixes.append(
            {
                "issue": issue.to_dict(),
                "fix": fix,
                "edit_url": f"/config/automation/edit/{automation_id}",
            }
        )
    return issues_with_fixes

def _get_healthy_count(hass: HomeAssistant, issues: list) -> int:
    """Calculate healthy automation count."""
    automation_data = hass.data.get("automation")
    total_automations = 0
    if automation_data:
        if hasattr(automation_data, "entities"):
            total_automations = len(list(automation_data.entities))
        elif isinstance(automation_data, dict):
            total_automations = len(automation_data.get("config", []))

    automations_with_issues = len(set(i.automation_id for i in issues))
    return max(0, total_automations - automations_with_issues)

def _compute_group_status(issues: list) -> str:
    """Compute group status from its issues.

    Returns "fail" if any ERROR, "warning" if any WARNING, else "pass".
    INFO-severity issues do not affect status.
    """
    if any(i.severity == Severity.ERROR for i in issues):
        return "fail"
    if any(i.severity == Severity.WARNING for i in issues):
        return "warning"
    return "pass"

def _filter_suppressed(
    issues: list[ValidationIssue],
    suppression_store: SuppressionStore | None,
) -> tuple[list[ValidationIssue], int]:
    """Filter suppressed issues and return visible issues with suppressed count."""
    if suppression_store:
        visible = [i for i in issues if not suppression_store.is_suppressed(i.get_suppression_key())]
        suppressed_count = len(issues) - len(visible)
    else:
        visible = issues
        suppressed_count = 0
    return visible, suppressed_count

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/issues",
    }
)
@websocket_api.async_response
async def websocket_get_issues(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get current issues with fix suggestions."""
    data = hass.data.get(DOMAIN, {})
    issues: list = data.get("issues", [])

    issues_with_fixes = _format_issues_with_fixes(hass, issues)
    healthy_count = _get_healthy_count(hass, issues)

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
        },
    )

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/refresh",
    }
)
@websocket_api.async_response
async def websocket_refresh(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Trigger a validation refresh."""
    from . import async_validate_all

    issues = await async_validate_all(hass)

    connection.send_result(msg["id"], {"success": True, "issue_count": len(issues)})

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/validation",
    }
)
@websocket_api.async_response
async def websocket_get_validation(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get validation issues only."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    all_issues: list = data.get("validation_issues", [])
    last_run = data.get("validation_last_run")

    visible_issues, suppressed_count = _filter_suppressed(all_issues, suppression_store)

    issues_with_fixes = _format_issues_with_fixes(hass, visible_issues)
    healthy_count = _get_healthy_count(hass, visible_issues)

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
            "last_run": last_run,
            "suppressed_count": suppressed_count,
        },
    )

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/validation/run",
    }
)
@websocket_api.async_response
async def websocket_run_validation(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run validation and return results."""
    try:
        from . import async_validate_all

        data = hass.data.get(DOMAIN, {})
        suppression_store: SuppressionStore | None = data.get("suppression_store")

        all_issues = await async_validate_all(hass)

        visible_issues, suppressed_count = _filter_suppressed(all_issues, suppression_store)

        issues_with_fixes = _format_issues_with_fixes(hass, visible_issues)
        healthy_count = _get_healthy_count(hass, visible_issues)
        last_run = hass.data.get(DOMAIN, {}).get("validation_last_run")

        connection.send_result(
            msg["id"],
            {
                "issues": issues_with_fixes,
                "healthy_count": healthy_count,
                "last_run": last_run,
                "suppressed_count": suppressed_count,
            },
        )
    except Exception as err:
        _LOGGER.exception("Error in websocket_run_validation: %s", err)
        connection.send_error(
            msg["id"], "validation_failed", f"Validation error: {err}"
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/validation/run_steps",
    }
)
@websocket_api.async_response
async def websocket_run_validation_steps(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run validation and return per-group structured results."""
    try:
        from . import async_validate_all_with_groups

        data = hass.data.get(DOMAIN, {})
        suppression_store: SuppressionStore | None = data.get("suppression_store")

        result = await async_validate_all_with_groups(hass)

        # Pre-compute entity IDs once for all _format_issues_with_fixes calls
        all_entity_ids = [s.entity_id for s in hass.states.async_all()]

        # Build groups response with suppression filtering
        groups = []
        all_visible_issues = []
        total_suppressed = 0

        for gid in VALIDATION_GROUP_ORDER:
            raw_issues = result["group_issues"][gid]
            visible, suppressed_count = _filter_suppressed(raw_issues, suppression_store)
            total_suppressed += suppressed_count

            all_visible_issues.extend(visible)
            formatted = _format_issues_with_fixes(hass, visible, all_entity_ids)

            groups.append(
                {
                    "id": gid,
                    "label": VALIDATION_GROUPS[gid]["label"],
                    "status": _compute_group_status(visible),
                    "error_count": sum(
                        1 for i in visible if i.severity == Severity.ERROR
                    ),
                    "warning_count": sum(
                        1 for i in visible if i.severity == Severity.WARNING
                    ),
                    "issue_count": len(visible),
                    "issues": formatted,
                    "duration_ms": result["group_durations"][gid],
                }
            )

        connection.send_result(
            msg["id"],
            {
                "groups": groups,
                "issues": _format_issues_with_fixes(hass, all_visible_issues, all_entity_ids),
                "healthy_count": _get_healthy_count(hass, all_visible_issues),
                "last_run": result["timestamp"],
                "suppressed_count": total_suppressed,
            },
        )
    except Exception as err:
        _LOGGER.exception("Error in websocket_run_validation_steps: %s", err)
        connection.send_error(
            msg["id"], "validation_failed", f"Validation error: {err}"
        )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/validation/steps",
    }
)
@websocket_api.async_response
async def websocket_get_validation_steps(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get cached per-group validation results without re-running validation."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    last_run = data.get("validation_last_run")
    cached_groups = data.get("validation_groups")

    # Pre-compute entity IDs once for all _format_issues_with_fixes calls
    all_entity_ids = [s.entity_id for s in hass.states.async_all()]

    groups = []
    all_visible_issues = []
    total_suppressed = 0

    if cached_groups is None:
        # No validation has been run yet -- return empty groups
        for gid in VALIDATION_GROUP_ORDER:
            groups.append(
                {
                    "id": gid,
                    "label": VALIDATION_GROUPS[gid]["label"],
                    "status": "pass",
                    "error_count": 0,
                    "warning_count": 0,
                    "issue_count": 0,
                    "issues": [],
                    "duration_ms": 0,
                }
            )
    else:
        # Apply suppression filtering at READ time (not from cache)
        for gid in VALIDATION_GROUP_ORDER:
            raw_issues = cached_groups[gid]["issues"]
            visible, suppressed_count = _filter_suppressed(raw_issues, suppression_store)
            total_suppressed += suppressed_count

            all_visible_issues.extend(visible)
            formatted = _format_issues_with_fixes(hass, visible, all_entity_ids)

            groups.append(
                {
                    "id": gid,
                    "label": VALIDATION_GROUPS[gid]["label"],
                    "status": _compute_group_status(visible),
                    "error_count": sum(
                        1 for i in visible if i.severity == Severity.ERROR
                    ),
                    "warning_count": sum(
                        1 for i in visible if i.severity == Severity.WARNING
                    ),
                    "issue_count": len(visible),
                    "issues": formatted,
                    "duration_ms": cached_groups[gid]["duration_ms"],
                }
            )

    healthy_count = _get_healthy_count(hass, all_visible_issues)

    connection.send_result(
        msg["id"],
        {
            "groups": groups,
            "issues": _format_issues_with_fixes(hass, all_visible_issues, all_entity_ids),
            "healthy_count": healthy_count,
            "last_run": last_run,
            "suppressed_count": total_suppressed,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/suppress",
        vol.Required("automation_id"): str,
        vol.Required("entity_id"): str,
        vol.Required("issue_type"): str,
        vol.Optional("state"): str,  # State value for learning
    }
)
@websocket_api.async_response
async def websocket_suppress(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Suppress an issue, optionally learning the state."""
    from .learned_states_store import LearnedStatesStore

    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    learned_store: LearnedStatesStore | None = data.get("learned_states_store")

    if not suppression_store:
        connection.send_error(
            msg["id"], "not_ready", "Suppression store not initialized"
        )
        return

    # Learn state if this is an invalid_state issue with a state value
    if learned_store and msg["issue_type"] == "invalid_state" and "state" in msg:
        entity_id = msg["entity_id"]
        state = msg["state"]

        # Get integration from entity registry
        entity_registry = er.async_get(hass)
        entry = entity_registry.async_get(entity_id)

        if entry and entry.platform:
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            await learned_store.async_learn_state(domain, entry.platform, state)
            _LOGGER.info(
                "Learned state '%s' for %s entities from %s integration",
                state,
                domain,
                entry.platform,
            )

    # Suppress the issue
    key = f"{msg['automation_id']}:{msg['entity_id']}:{msg['issue_type']}"
    await suppression_store.async_suppress(key)

    connection.send_result(
        msg["id"], {"success": True, "suppressed_count": suppression_store.count}
    )

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/clear_suppressions",
    }
)
@websocket_api.async_response
async def websocket_clear_suppressions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Clear all suppressions."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")

    if not suppression_store:
        connection.send_error(
            msg["id"], "not_ready", "Suppression store not initialized"
        )
        return

    await suppression_store.async_clear_all()

    connection.send_result(msg["id"], {"success": True, "suppressed_count": 0})
