"""WebSocket API for Autodoctor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

if TYPE_CHECKING:
    from .fix_engine import FixEngine
    from .suppression_store import SuppressionStore

_LOGGER = logging.getLogger(__name__)


async def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Set up WebSocket API."""
    websocket_api.async_register_command(hass, websocket_get_issues)
    websocket_api.async_register_command(hass, websocket_refresh)
    websocket_api.async_register_command(hass, websocket_get_validation)
    websocket_api.async_register_command(hass, websocket_run_validation)
    websocket_api.async_register_command(hass, websocket_get_outcomes)
    websocket_api.async_register_command(hass, websocket_run_outcomes)
    websocket_api.async_register_command(hass, websocket_suppress)
    websocket_api.async_register_command(hass, websocket_clear_suppressions)


def _format_issues_with_fixes(issues: list, fix_engine) -> list[dict]:
    """Format issues with fix suggestions."""
    issues_with_fixes = []
    for issue in issues:
        fix = fix_engine.suggest_fix(issue) if fix_engine else None
        automation_id = issue.automation_id.replace("automation.", "") if issue.automation_id else ""
        issues_with_fixes.append({
            "issue": issue.to_dict(),
            "fix": {
                "description": fix.description,
                "confidence": fix.confidence,
                "fix_value": fix.fix_value,
            } if fix else None,
            "edit_url": f"/config/automation/edit/{automation_id}",
        })
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
    fix_engine: FixEngine | None = data.get("fix_engine")
    issues: list = data.get("issues", [])

    issues_with_fixes = _format_issues_with_fixes(issues, fix_engine)
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
    hass.data[DOMAIN]["issues"] = issues

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
    fix_engine: FixEngine | None = data.get("fix_engine")
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    all_issues: list = data.get("validation_issues", [])
    last_run = data.get("validation_last_run")

    # Filter out suppressed issues
    if suppression_store:
        visible_issues = [
            issue for issue in all_issues
            if not suppression_store.is_suppressed(issue.get_suppression_key())
        ]
        suppressed_count = len(all_issues) - len(visible_issues)
    else:
        visible_issues = all_issues
        suppressed_count = 0

    issues_with_fixes = _format_issues_with_fixes(visible_issues, fix_engine)
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
    from . import async_validate_all

    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")
    suppression_store: SuppressionStore | None = data.get("suppression_store")

    all_issues = await async_validate_all(hass)

    # Filter out suppressed issues
    if suppression_store:
        visible_issues = [
            issue for issue in all_issues
            if not suppression_store.is_suppressed(issue.get_suppression_key())
        ]
        suppressed_count = len(all_issues) - len(visible_issues)
    else:
        visible_issues = all_issues
        suppressed_count = 0

    issues_with_fixes = _format_issues_with_fixes(visible_issues, fix_engine)
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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/outcomes",
    }
)
@websocket_api.async_response
async def websocket_get_outcomes(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get outcome issues only."""
    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    all_issues: list = data.get("outcome_issues", [])
    last_run = data.get("outcomes_last_run")

    # Filter out suppressed issues
    if suppression_store:
        visible_issues = [
            issue for issue in all_issues
            if not suppression_store.is_suppressed(issue.get_suppression_key())
        ]
        suppressed_count = len(all_issues) - len(visible_issues)
    else:
        visible_issues = all_issues
        suppressed_count = 0

    issues_with_fixes = _format_issues_with_fixes(visible_issues, fix_engine)
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
        vol.Required("type"): "autodoctor/outcomes/run",
    }
)
@websocket_api.async_response
async def websocket_run_outcomes(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run outcome simulation and return results."""
    from . import async_simulate_all

    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")
    suppression_store: SuppressionStore | None = data.get("suppression_store")

    all_issues = await async_simulate_all(hass)

    # Filter out suppressed issues
    if suppression_store:
        visible_issues = [
            issue for issue in all_issues
            if not suppression_store.is_suppressed(issue.get_suppression_key())
        ]
        suppressed_count = len(all_issues) - len(visible_issues)
    else:
        visible_issues = all_issues
        suppressed_count = 0

    issues_with_fixes = _format_issues_with_fixes(visible_issues, fix_engine)
    healthy_count = _get_healthy_count(hass, visible_issues)
    last_run = hass.data.get(DOMAIN, {}).get("outcomes_last_run")

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
        vol.Required("type"): "autodoctor/suppress",
        vol.Required("automation_id"): str,
        vol.Required("entity_id"): str,
        vol.Required("issue_type"): str,
    }
)
@websocket_api.async_response
async def websocket_suppress(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Suppress an issue."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")

    if not suppression_store:
        connection.send_error(msg["id"], "not_ready", "Suppression store not initialized")
        return

    key = f"{msg['automation_id']}:{msg['entity_id']}:{msg['issue_type']}"
    await suppression_store.async_suppress(key)

    connection.send_result(msg["id"], {"success": True, "suppressed_count": suppression_store.count})


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
        connection.send_error(msg["id"], "not_ready", "Suppression store not initialized")
        return

    await suppression_store.async_clear_all()

    connection.send_result(msg["id"], {"success": True, "suppressed_count": 0})
