"""WebSocket API for Autodoctor."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conflict_detector import ConflictDetector
from .const import DOMAIN
from .fix_engine import get_entity_suggestion
from .models import IssueType

if TYPE_CHECKING:
    from .suppression_store import SuppressionStore

_LOGGER = logging.getLogger(__name__)

async def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Set up WebSocket API."""
    websocket_api.async_register_command(hass, websocket_get_issues)
    websocket_api.async_register_command(hass, websocket_refresh)
    websocket_api.async_register_command(hass, websocket_get_validation)
    websocket_api.async_register_command(hass, websocket_run_validation)
    websocket_api.async_register_command(hass, websocket_get_conflicts)
    websocket_api.async_register_command(hass, websocket_run_conflicts)
    websocket_api.async_register_command(hass, websocket_suppress)
    websocket_api.async_register_command(hass, websocket_clear_suppressions)

def _format_issues_with_fixes(hass: HomeAssistant, issues: list) -> list[dict]:
    """Format issues with fix suggestions using simplified fix engine."""
    issues_with_fixes = []
    all_entity_ids = [s.entity_id for s in hass.states.async_all()]

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

    # Filter out suppressed issues
    if suppression_store:
        visible_issues = [
            issue
            for issue in all_issues
            if not suppression_store.is_suppressed(issue.get_suppression_key())
        ]
        suppressed_count = len(all_issues) - len(visible_issues)
    else:
        visible_issues = all_issues
        suppressed_count = 0

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

        # Filter out suppressed issues
        if suppression_store:
            visible_issues = [
                issue
                for issue in all_issues
                if not suppression_store.is_suppressed(issue.get_suppression_key())
            ]
            suppressed_count = len(all_issues) - len(visible_issues)
        else:
            visible_issues = all_issues
            suppressed_count = 0

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

def _format_conflicts(conflicts: list, suppression_store) -> tuple[list[dict], int]:
    """Format conflicts, filtering suppressed ones."""
    if suppression_store:
        visible = [
            c
            for c in conflicts
            if not suppression_store.is_suppressed(c.get_suppression_key())
        ]
        suppressed_count = len(conflicts) - len(visible)
    else:
        visible = conflicts
        suppressed_count = 0

    formatted = [c.to_dict() for c in visible]
    return formatted, suppressed_count

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/conflicts",
    }
)
@websocket_api.async_response
async def websocket_get_conflicts(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get conflict detection results."""
    data = hass.data.get(DOMAIN, {})
    conflicts = data.get("conflicts", [])
    last_run = data.get("conflicts_last_run")
    suppression_store = data.get("suppression_store")

    formatted, suppressed_count = _format_conflicts(conflicts, suppression_store)

    connection.send_result(
        msg["id"],
        {
            "conflicts": formatted,
            "last_run": last_run,
            "suppressed_count": suppressed_count,
        },
    )

@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/conflicts/run",
    }
)
@websocket_api.async_response
async def websocket_run_conflicts(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run conflict detection and return results."""
    from datetime import datetime

    from . import _get_automation_configs

    data = hass.data.get(DOMAIN, {})
    suppression_store = data.get("suppression_store")

    # Get automation configs
    automations = _get_automation_configs(hass)

    # Detect conflicts
    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    # Store results atomically to prevent partial reads
    last_run = datetime.now(UTC).isoformat()
    hass.data[DOMAIN].update(
        {
            "conflicts": conflicts,
            "conflicts_last_run": last_run,
        }
    )

    formatted, suppressed_count = _format_conflicts(conflicts, suppression_store)

    connection.send_result(
        msg["id"],
        {
            "conflicts": formatted,
            "last_run": last_run,
            "suppressed_count": suppressed_count,
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
