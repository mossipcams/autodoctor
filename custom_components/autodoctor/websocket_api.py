"""WebSocket API for Autodoctor."""

from __future__ import annotations

import logging
import re
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
import yaml
from homeassistant.components import websocket_api
from homeassistant.config import AUTOMATION_CONFIG_PATH
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import (
    VALIDATION_GROUP_ORDER,
    VALIDATION_GROUPS,
    IssueType,
    Severity,
    ValidationIssue,
)
from .validator import get_entity_suggestion

if TYPE_CHECKING:
    from .suppression_store import SuppressionStore

_LOGGER = logging.getLogger(__name__)
_FIX_SNAPSHOT_STORAGE_KEY = "autodoctor.fix_snapshot"
_FIX_SNAPSHOT_STORAGE_VERSION = 1


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
    websocket_api.async_register_command(hass, websocket_list_suppressions)
    websocket_api.async_register_command(hass, websocket_unsuppress)
    websocket_api.async_register_command(hass, websocket_fix_preview)
    websocket_api.async_register_command(hass, websocket_fix_apply)
    websocket_api.async_register_command(hass, websocket_fix_undo)


def _raw_config_get(raw_config: Any, key: str) -> Any:
    """Read values from raw_config that may be mapping-like or attribute-based."""
    if raw_config is None:
        return None

    if isinstance(raw_config, dict):
        raw_config_dict = cast(dict[str, Any], raw_config)
        return raw_config_dict.get(key)

    getter = getattr(raw_config, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            pass

    return getattr(raw_config, key, None)


def _resolve_automation_edit_config_id(
    hass: HomeAssistant, automation_entity_id: str
) -> str | None:
    """Resolve automation config id for HA editor route, or None when not editable."""
    automation_data = hass.data.get("automation")
    short_id = automation_entity_id.replace("automation.", "", 1)

    # Dict mode is used in tests and some legacy paths.
    if isinstance(automation_data, dict):
        automation_dict = cast(dict[str, Any], automation_data)
        configs: list[Any] = automation_dict.get("config", [])
        for config in configs:
            if not isinstance(config, dict):
                continue
            config_dict = cast(dict[str, Any], config)
            config_id_raw = config_dict.get("id")
            config_id = config_id_raw if isinstance(config_id_raw, str) else None
            if isinstance(config_id, str) and config_id == short_id:
                return config_id
            config_entity_id_raw = config_dict.get("__entity_id")
            config_entity_id = (
                config_entity_id_raw if isinstance(config_entity_id_raw, str) else None
            )
            if (
                isinstance(config_entity_id, str)
                and config_entity_id == automation_entity_id
                and isinstance(config_id, str)
                and config_id
            ):
                return config_id
        return None

    if not automation_data:
        return None

    if hasattr(automation_data, "get_entity"):
        entity = automation_data.get_entity(automation_entity_id)
        if entity is not None:
            raw_config = getattr(entity, "raw_config", None)
            config_file = _raw_config_get(raw_config, "__config_file__")
            if isinstance(config_file, str):
                # Explicit source file — only editable when from automations.yaml
                if Path(config_file).name != AUTOMATION_CONFIG_PATH:
                    return None
                config_id = _raw_config_get(raw_config, "id")
                if isinstance(config_id, str) and config_id:
                    return config_id
                return short_id
            # No __config_file__ metadata — assume editable if config id exists
            config_id = _raw_config_get(raw_config, "id")
            if isinstance(config_id, str) and config_id:
                return config_id
            return short_id

    entities = getattr(automation_data, "entities", None)
    if entities is None:
        return None

    for entity in cast(list[Any], entities):
        raw_config = getattr(entity, "raw_config", None)
        config_file = _raw_config_get(raw_config, "__config_file__")
        if isinstance(config_file, str):
            # Explicit source file — skip non-automations.yaml sources
            if Path(config_file).name != AUTOMATION_CONFIG_PATH:
                continue

        config_id = _raw_config_get(raw_config, "id")
        entity_id = getattr(entity, "entity_id", None)
        if isinstance(config_id, str) and config_id == short_id:
            return config_id
        if isinstance(entity_id, str) and entity_id == automation_entity_id:
            if isinstance(config_id, str) and config_id:
                return config_id
            return short_id

    return None


def _format_issues_with_fixes(
    hass: HomeAssistant,
    issues: list[ValidationIssue],
    all_entity_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
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

    issues_with_fixes: list[dict[str, Any]] = []

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
                    "fix_type": "replace_value",
                    "current_value": issue.entity_id,
                    "suggested_value": suggestion,
                    "reason": "Entity ID is unknown; nearest known entity matched.",
                }
        elif issue.issue_type == IssueType.ATTRIBUTE_NOT_FOUND and issue.suggestion:
            fix = {
                "description": f"Did you mean '{issue.suggestion}'?",
                "confidence": 0.8,
                "fix_value": issue.suggestion,
                "fix_type": "replace_value",
                "current_value": None,
                "suggested_value": issue.suggestion,
                "reason": "Attribute name is unknown; closest known attribute matched.",
            }
        elif issue.issue_type == IssueType.INVALID_ATTRIBUTE_VALUE:
            if issue.suggestion:
                desc = f"Did you mean '{issue.suggestion}'?"
                if issue.valid_states:
                    desc += f" Valid values: {', '.join(issue.valid_states)}"
                fix = {
                    "description": desc,
                    "confidence": 0.8,
                    "fix_value": issue.suggestion,
                    "fix_type": "replace_value",
                    "current_value": None,
                    "suggested_value": issue.suggestion,
                    "reason": "Provided value is invalid for this attribute.",
                }
            elif issue.valid_states:
                fix = {
                    "description": f"Valid values: {', '.join(issue.valid_states)}",
                    "confidence": 0.6,
                    "fix_value": None,
                    "fix_type": "reference",
                    "current_value": None,
                    "suggested_value": None,
                    "reason": "No exact replacement found; valid values provided.",
                }
        elif issue.issue_type == IssueType.INVALID_STATE:
            if issue.suggestion:
                desc = f"Did you mean '{issue.suggestion}'?"
                if issue.valid_states:
                    desc += f" Valid values: {', '.join(issue.valid_states)}"
                fix = {
                    "description": desc,
                    "confidence": 0.8,
                    "fix_value": issue.suggestion,
                    "fix_type": "replace_value",
                    "current_value": None,
                    "suggested_value": issue.suggestion,
                    "reason": "Provided state is invalid for this entity.",
                }
            elif issue.valid_states:
                fix = {
                    "description": f"Valid values: {', '.join(issue.valid_states)}",
                    "confidence": 0.6,
                    "fix_value": None,
                    "fix_type": "reference",
                    "current_value": None,
                    "suggested_value": None,
                    "reason": "No exact replacement found; valid states provided.",
                }
        elif issue.issue_type == IssueType.CASE_MISMATCH and issue.suggestion:
            fix = {
                "description": f"Did you mean '{issue.suggestion}'?",
                "confidence": 0.9,
                "fix_value": issue.suggestion,
                "fix_type": "replace_value",
                "current_value": issue.entity_id,
                "suggested_value": issue.suggestion,
                "reason": "Case mismatch detected; entity IDs are case-sensitive.",
            }

        edit_url: str | None = None
        if issue.automation_id:
            config_id = _resolve_automation_edit_config_id(hass, issue.automation_id)
            if config_id is not None:
                edit_url = f"/config/automation/edit/{config_id}"

        issues_with_fixes.append(
            {
                "issue": issue.to_dict(),
                "fix": fix,
                "edit_url": edit_url,
            }
        )
    return issues_with_fixes


def _get_healthy_count(hass: HomeAssistant, issues: list[ValidationIssue]) -> int:
    """Calculate healthy automation count."""
    automation_data = hass.data.get("automation")
    total_automations = 0
    if automation_data:
        if hasattr(automation_data, "entities"):
            total_automations = len(list(automation_data.entities))
        elif isinstance(automation_data, dict):
            total_automations = len(automation_data.get("config", []))

    automations_with_issues = len({i.automation_id for i in issues})
    return max(0, total_automations - automations_with_issues)


_LOCATION_SEGMENT_RE = re.compile(r"^([a-zA-Z_]+)(?:\[(\d+)\])?$")


def _parse_location_path(location: str) -> list[str | int] | None:
    """Parse location strings like 'trigger[0].entity_id' into path segments."""
    segments: list[str | int] = []
    for part in location.split("."):
        match = _LOCATION_SEGMENT_RE.match(part)
        if not match:
            return None
        key = match.group(1)
        idx = match.group(2)
        segments.append(key)
        if idx is not None:
            segments.append(int(idx))
    return segments


def _resolve_parent_and_key(
    root: Any, path: list[str | int]
) -> tuple[Any, str | int, Any] | None:
    """Resolve path to parent container and terminal key/index."""
    if not path:
        return None

    node: Any = root
    for segment in path[:-1]:
        if isinstance(segment, str):
            if not isinstance(node, dict) or segment not in node:
                return None
            node = cast(dict[str, Any], node)[segment]
        else:
            if not isinstance(node, list) or segment < 0 or segment >= len(node):
                return None
            node = cast(list[Any], node)[segment]

    terminal = path[-1]
    if isinstance(terminal, str):
        if not isinstance(node, dict) or terminal not in node:
            return None
        dict_node = cast(dict[str, Any], node)
        return dict_node, terminal, dict_node[terminal]

    if not isinstance(node, list) or terminal < 0 or terminal >= len(node):
        return None
    list_node = cast(list[Any], node)
    return list_node, terminal, list_node[terminal]


def _find_automation_config(
    hass: HomeAssistant, automation_id: str
) -> dict[str, Any] | None:
    """Find mutable automation config dict by automation entity_id."""
    automation_data = hass.data.get("automation")
    short_id = automation_id.replace("automation.", "", 1)

    if isinstance(automation_data, dict):
        automation_dict = cast(dict[str, object], automation_data)
        raw_configs_obj = automation_dict.get("config", [])
        if isinstance(raw_configs_obj, list):
            for config_obj in cast(list[object], raw_configs_obj):
                if not isinstance(config_obj, dict):
                    continue
                config = cast(dict[str, Any], config_obj)
                config_id = config.get("id")
                if isinstance(config_id, str) and config_id == short_id:
                    return config
                config_entity_id = config.get("__entity_id")
                if (
                    isinstance(config_entity_id, str)
                    and config_entity_id == automation_id
                ):
                    return config
        return None

    entities = getattr(automation_data, "entities", None)
    if entities is not None:
        for entity in cast(list[Any], entities):
            raw_config = getattr(entity, "raw_config", None)
            if not isinstance(raw_config, dict):
                continue
            config = cast(dict[str, Any], raw_config)
            config_id = config.get("id")
            if isinstance(config_id, str) and config_id == short_id:
                return config
            config_entity_id = config.get("__entity_id")
            if isinstance(config_entity_id, str) and config_entity_id == automation_id:
                return config
            entity_id = getattr(entity, "entity_id", None)
            if isinstance(entity_id, str) and entity_id == automation_id:
                return config
    return None


def _is_dict_mode_automation_data(hass: HomeAssistant) -> bool:
    """Return True when automation data is the legacy/test dict shape."""
    return isinstance(hass.data.get("automation"), dict)


def _resolve_config_file_path(hass: HomeAssistant, config_file: str) -> Path:
    """Resolve config file path against HA config dir when given a relative path."""
    raw_path = Path(config_file)
    if raw_path.is_absolute():
        return raw_path
    if hasattr(hass, "config") and hasattr(hass.config, "path"):
        try:
            return Path(hass.config.path(config_file))
        except Exception:
            pass
    return raw_path


def _apply_fix_to_automation_yaml(
    *,
    file_path: Path,
    automation_id: str,
    location: str,
    expected_current: str | None,
    suggested_value: str,
    candidate_ids: list[str] | None = None,
) -> tuple[bool, str, str | None]:
    """Apply a scalar replacement directly to automations.yaml."""
    try:
        payload = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except OSError as err:
        return False, f"Unable to read automation config file: {err}", None
    except yaml.YAMLError as err:
        return False, f"Unable to parse automation config file: {err}", None

    if payload is None:
        payload = []
    if not isinstance(payload, list):
        return False, "Automation config file must contain a list of automations.", None

    path = _parse_location_path(location)
    if path is None:
        return False, "Unsupported location format.", None

    short_id = automation_id.replace("automation.", "", 1)
    candidate_id_set = {short_id}
    if candidate_ids:
        candidate_id_set.update(candidate_ids)
    candidate_entity_ids = {
        cid if cid.startswith("automation.") else f"automation.{cid}"
        for cid in candidate_id_set
    }
    candidate_entity_ids.add(automation_id)
    target_automation: dict[str, Any] | None = None
    for item in cast(list[Any], payload):
        if not isinstance(item, dict):
            continue
        item_dict = cast(dict[str, Any], item)
        raw_id = item_dict.get("id")
        raw_entity_id = (
            f"automation.{raw_id}" if isinstance(raw_id, str) and raw_id else None
        )
        raw_entity_hint = item_dict.get("__entity_id")
        if (
            (isinstance(raw_id, str) and raw_id in candidate_id_set)
            or (
                isinstance(raw_entity_id, str) and raw_entity_id in candidate_entity_ids
            )
            or (
                isinstance(raw_entity_hint, str)
                and raw_entity_hint in candidate_entity_ids
            )
        ):
            target_automation = item_dict
            break

    if target_automation is None:
        return False, "Automation not found in automations.yaml.", None

    resolved = _resolve_parent_and_key(target_automation, path)
    if resolved is None:
        return False, "Location does not resolve in automations.yaml.", None

    container, key, live_value = resolved
    if not isinstance(live_value, str):
        return False, "Target value is not a string.", None
    if expected_current is not None and live_value != expected_current:
        return False, "Current value mismatch; automation has changed.", live_value
    if live_value == suggested_value:
        return False, "Suggested value already applied.", live_value

    previous_value = live_value
    container[key] = suggested_value
    try:
        file_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as err:
        container[key] = previous_value
        return False, f"Unable to write automation config file: {err}", previous_value

    return True, "", previous_value


def _get_fix_snapshot_store(hass: HomeAssistant) -> Store[dict[str, Any]]:
    """Return persistent store used for last-applied-fix snapshots."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    store = domain_data.get("_fix_snapshot_store")
    if isinstance(store, Store):
        return cast(Store[dict[str, Any]], store)
    new_store: Store[dict[str, Any]] = Store(
        hass,
        _FIX_SNAPSHOT_STORAGE_VERSION,
        _FIX_SNAPSHOT_STORAGE_KEY,
    )
    domain_data["_fix_snapshot_store"] = new_store
    return new_store


async def _async_load_last_fix_snapshot(hass: HomeAssistant) -> dict[str, Any] | None:
    """Load last applied fix snapshot from memory or persistent storage."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    snapshot = domain_data.get("last_applied_fix")
    if isinstance(snapshot, dict):
        return cast(dict[str, Any], snapshot)

    store = _get_fix_snapshot_store(hass)
    payload = await store.async_load()
    loaded = (
        cast(dict[str, Any], payload.get("last_applied_fix"))
        if isinstance(payload, dict)
        and isinstance(payload.get("last_applied_fix"), dict)
        else None
    )
    domain_data["last_applied_fix"] = loaded
    return loaded


async def _async_save_last_fix_snapshot(
    hass: HomeAssistant, snapshot: dict[str, Any] | None
) -> None:
    """Persist last applied fix snapshot."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data["last_applied_fix"] = snapshot
    store = _get_fix_snapshot_store(hass)
    await store.async_save({"last_applied_fix": snapshot})


def _build_fix_preview(
    hass: HomeAssistant,
    automation_id: str,
    location: str,
    current_value: str | None,
    suggested_value: str,
) -> dict[str, Any]:
    """Build a guarded fix preview payload."""
    config = _find_automation_config(hass, automation_id)
    if config is None:
        return {
            "applicable": False,
            "reason": "Automation config not found or not editable.",
        }

    path = _parse_location_path(location)
    if path is None:
        return {"applicable": False, "reason": "Unsupported location format."}

    resolved = _resolve_parent_and_key(config, path)
    if resolved is None:
        return {"applicable": False, "reason": "Location does not resolve in config."}

    _, _, live_value = resolved
    if not isinstance(live_value, str):
        return {"applicable": False, "reason": "Target value is not a string."}

    if current_value is not None and live_value != current_value:
        return {
            "applicable": False,
            "reason": "Current value mismatch; automation has changed.",
            "current_value": live_value,
            "suggested_value": suggested_value,
        }

    if live_value == suggested_value:
        return {
            "applicable": False,
            "reason": "Suggested value already applied.",
            "current_value": live_value,
            "suggested_value": suggested_value,
        }

    return {
        "applicable": True,
        "automation_id": automation_id,
        "location": location,
        "current_value": live_value,
        "suggested_value": suggested_value,
        "fix_type": "replace_value",
    }


def _compute_group_status(issues: list[ValidationIssue]) -> str:
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
        visible = [
            i
            for i in issues
            if not suppression_store.is_suppressed(i.get_suppression_key())
        ]
        suppressed_count = len(issues) - len(visible)
    else:
        visible = issues
        suppressed_count = 0
    return visible, suppressed_count


async def _async_reconcile_visible_issues(hass: HomeAssistant) -> None:
    """Recompute visible issues from raw cache and update reporter-backed surfaces."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    raw_issues: list[ValidationIssue] = data.get(
        "validation_issues_raw",
        data.get("validation_issues", data.get("issues", [])),
    )
    visible_issues, _ = _filter_suppressed(raw_issues, suppression_store)

    data["issues"] = visible_issues
    data["validation_issues"] = visible_issues

    reporter = data.get("reporter")
    if reporter is not None and hasattr(reporter, "async_report_issues"):
        await reporter.async_report_issues(visible_issues)


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
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    all_issues: list[ValidationIssue] = data.get(
        "validation_issues_raw",
        data.get("validation_issues", data.get("issues", [])),
    )
    issues, _ = _filter_suppressed(all_issues, suppression_store)

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
@websocket_api.require_admin
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
    all_issues: list[ValidationIssue] = data.get(
        "validation_issues_raw",
        data.get("validation_issues", []),
    )
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
@websocket_api.require_admin
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

        visible_issues, suppressed_count = _filter_suppressed(
            all_issues, suppression_store
        )

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
@websocket_api.require_admin
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
            raw_issues = cast(
                list[ValidationIssue], result["group_issues"].get(gid, [])
            )
            visible, suppressed_count = _filter_suppressed(
                raw_issues, suppression_store
            )
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
                    "duration_ms": int(result["group_durations"].get(gid, 0)),
                }
            )

        connection.send_result(
            msg["id"],
            {
                "groups": groups,
                "issues": _format_issues_with_fixes(
                    hass, all_visible_issues, all_entity_ids
                ),
                "healthy_count": _get_healthy_count(hass, all_visible_issues),
                "last_run": result["timestamp"],
                "suppressed_count": total_suppressed,
                "analyzed_automations": result.get("analyzed_automations", 0),
                "failed_automations": result.get("failed_automations", 0),
                "skip_reasons": result.get("skip_reasons", {}),
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
    cached_groups = data.get("validation_groups_raw", data.get("validation_groups"))
    run_stats = data.get("validation_run_stats", {})

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
            bucket = cast(dict[str, Any], cached_groups.get(gid, {}))
            raw_issues = cast(list[ValidationIssue], bucket.get("issues", []))
            visible, suppressed_count = _filter_suppressed(
                raw_issues, suppression_store
            )
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
                    "duration_ms": int(bucket.get("duration_ms", 0)),
                }
            )

    healthy_count = _get_healthy_count(hass, all_visible_issues)

    connection.send_result(
        msg["id"],
        {
            "groups": groups,
            "issues": _format_issues_with_fixes(
                hass, all_visible_issues, all_entity_ids
            ),
            "healthy_count": healthy_count,
            "last_run": last_run,
            "suppressed_count": total_suppressed,
            "analyzed_automations": run_stats.get("analyzed_automations", 0),
            "failed_automations": run_stats.get("failed_automations", 0),
            "skip_reasons": run_stats.get("skip_reasons", {}),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/suppress",
        vol.Required("automation_id"): str,
        vol.Required("entity_id"): str,
        vol.Required("issue_type"): vol.In([it.value for it in IssueType]),
        vol.Optional("state"): str,  # State value for learning
    }
)
@websocket_api.require_admin
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
    await _async_reconcile_visible_issues(hass)

    runtime_issue_types = {
        IssueType.RUNTIME_AUTOMATION_SILENT.value,
        IssueType.RUNTIME_AUTOMATION_OVERACTIVE.value,
        IssueType.RUNTIME_AUTOMATION_BURST.value,
    }
    if msg["issue_type"] in runtime_issue_types:
        runtime_monitor = data.get("runtime_monitor")
        if runtime_monitor is not None and hasattr(
            runtime_monitor, "record_issue_dismissed"
        ):
            try:
                runtime_monitor.record_issue_dismissed(msg["automation_id"])
            except Exception as err:
                _LOGGER.debug("Failed recording runtime dismissal learning: %s", err)

    connection.send_result(
        msg["id"], {"success": True, "suppressed_count": suppression_store.count}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/clear_suppressions",
    }
)
@websocket_api.require_admin
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
    await _async_reconcile_visible_issues(hass)

    connection.send_result(msg["id"], {"success": True, "suppressed_count": 0})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/list_suppressions",
    }
)
@websocket_api.async_response
async def websocket_list_suppressions(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List all suppressed issues with metadata."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")

    if not suppression_store:
        connection.send_error(
            msg["id"], "not_ready", "Suppression store not initialized"
        )
        return

    validation_issues: list[ValidationIssue] = data.get(
        "validation_issues_raw",
        data.get("validation_issues", []),
    )

    # Build lookup dict for O(1) matching
    issue_by_key: dict[str, Any] = {}
    for issue in validation_issues:
        issue_by_key[issue.get_suppression_key()] = issue

    suppressions = []
    for key in suppression_store.keys:
        issue = issue_by_key.get(key)
        suppressions.append(
            {
                "key": key,
                "automation_id": issue.automation_id if issue else key.split(":")[0],
                "automation_name": issue.automation_name if issue else "",
                "entity_id": issue.entity_id
                if issue
                else (key.split(":")[1] if ":" in key else ""),
                "issue_type": issue.issue_type.value
                if issue and issue.issue_type
                else (key.split(":")[-1] if ":" in key else ""),
                "message": issue.message if issue else "",
            }
        )

    connection.send_result(msg["id"], {"suppressions": suppressions})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/unsuppress",
        vol.Required("key"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_unsuppress(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove a single suppression by key."""
    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")

    if not suppression_store:
        connection.send_error(
            msg["id"], "not_ready", "Suppression store not initialized"
        )
        return

    await suppression_store.async_unsuppress(msg["key"])
    await _async_reconcile_visible_issues(hass)

    connection.send_result(
        msg["id"], {"success": True, "suppressed_count": suppression_store.count}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/fix_preview",
        vol.Required("automation_id"): str,
        vol.Required("location"): str,
        vol.Optional("current_value"): vol.Any(str, None),
        vol.Required("suggested_value"): str,
    }
)
@websocket_api.async_response
async def websocket_fix_preview(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Preview whether a safe scalar replacement can be applied."""
    preview = _build_fix_preview(
        hass,
        msg["automation_id"],
        msg["location"],
        msg.get("current_value"),
        msg["suggested_value"],
    )
    connection.send_result(msg["id"], preview)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/fix_apply",
        vol.Required("automation_id"): str,
        vol.Required("location"): str,
        vol.Optional("current_value"): vol.Any(str, None),
        vol.Required("suggested_value"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_fix_apply(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Apply a guarded scalar replacement to automation config."""
    preview = _build_fix_preview(
        hass,
        msg["automation_id"],
        msg["location"],
        msg.get("current_value"),
        msg["suggested_value"],
    )
    if not preview.get("applicable"):
        connection.send_error(
            msg["id"], "fix_not_applicable", preview.get("reason", "")
        )
        return

    config = _find_automation_config(hass, msg["automation_id"])
    path = _parse_location_path(msg["location"])
    if config is None or path is None:
        connection.send_error(
            msg["id"], "fix_not_applicable", "Unable to resolve target"
        )
        return

    resolved = _resolve_parent_and_key(config, path)
    if resolved is None:
        connection.send_error(
            msg["id"], "fix_not_applicable", "Unable to resolve target"
        )
        return

    container, key, previous_value = resolved
    suggested_value = msg["suggested_value"]
    config_file_raw = config.get("__config_file__")
    persisted_file_change = False

    if isinstance(config_file_raw, str):
        config_path = _resolve_config_file_path(hass, config_file_raw)
        if config_path.name != AUTOMATION_CONFIG_PATH:
            connection.send_error(
                msg["id"],
                "fix_not_applicable",
                "Automation source is not safely persistable.",
            )
            return

        config_ids: list[str] = []
        raw_id = config.get("id")
        if isinstance(raw_id, str) and raw_id:
            config_ids.append(raw_id)
        raw_entity_id = config.get("__entity_id")
        if isinstance(raw_entity_id, str) and raw_entity_id.startswith("automation."):
            config_ids.append(raw_entity_id.replace("automation.", "", 1))

        ok, reason, persisted_previous = await hass.async_add_executor_job(
            partial(
                _apply_fix_to_automation_yaml,
                file_path=config_path,
                automation_id=msg["automation_id"],
                location=msg["location"],
                expected_current=preview.get("current_value"),
                suggested_value=suggested_value,
                candidate_ids=config_ids,
            )
        )
        if not ok:
            connection.send_error(msg["id"], "fix_not_applicable", reason)
            return

        previous_value = (
            persisted_previous
            if isinstance(persisted_previous, str)
            else previous_value
        )
        container[key] = suggested_value
        persisted_file_change = True
    elif _is_dict_mode_automation_data(hass):
        container[key] = suggested_value
    else:
        connection.send_error(
            msg["id"],
            "fix_not_applicable",
            "Automation source is not safely persistable.",
        )
        return

    if persisted_file_change:
        try:
            await hass.services.async_call("automation", "reload", {}, blocking=True)
        except Exception as err:
            _LOGGER.warning("Automation reload after fix failed: %s", err)

    try:
        from . import async_validate_all_with_groups

        await async_validate_all_with_groups(hass)
    except Exception as err:
        _LOGGER.warning("Post-fix validation failed: %s", err)

    snapshot = {
        "automation_id": msg["automation_id"],
        "location": msg["location"],
        "previous_value": previous_value,
        "new_value": suggested_value,
    }
    await _async_save_last_fix_snapshot(hass, snapshot)

    connection.send_result(
        msg["id"],
        {
            "applied": True,
            "automation_id": msg["automation_id"],
            "location": msg["location"],
            "previous_value": previous_value,
            "new_value": suggested_value,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/fix_undo",
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_fix_undo(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Undo the most recent successful fix application."""
    snapshot = await _async_load_last_fix_snapshot(hass)
    if not snapshot:
        connection.send_error(
            msg["id"], "fix_undo_unavailable", "No applied fix to undo"
        )
        return

    automation_id = snapshot.get("automation_id")
    location = snapshot.get("location")
    previous_value = snapshot.get("previous_value")
    new_value = snapshot.get("new_value")

    if (
        not isinstance(automation_id, str)
        or not isinstance(location, str)
        or not isinstance(previous_value, str)
        or not isinstance(new_value, str)
    ):
        connection.send_error(
            msg["id"], "fix_undo_unavailable", "Invalid undo snapshot"
        )
        return

    config = _find_automation_config(hass, automation_id)
    path = _parse_location_path(location)
    if config is None or path is None:
        connection.send_error(
            msg["id"], "fix_undo_failed", "Unable to resolve undo target"
        )
        return

    resolved = _resolve_parent_and_key(config, path)
    if resolved is None:
        connection.send_error(
            msg["id"], "fix_undo_failed", "Unable to resolve undo target"
        )
        return

    container, key, live_value = resolved
    if live_value != new_value:
        connection.send_error(
            msg["id"],
            "fix_undo_failed",
            "Undo no longer applicable because value has changed.",
        )
        return

    config_file_raw = config.get("__config_file__")
    persisted_file_change = False
    if isinstance(config_file_raw, str):
        config_path = _resolve_config_file_path(hass, config_file_raw)
        if config_path.name != AUTOMATION_CONFIG_PATH:
            connection.send_error(
                msg["id"], "fix_undo_failed", "Automation source is not persistable."
            )
            return

        config_ids: list[str] = []
        raw_id = config.get("id")
        if isinstance(raw_id, str) and raw_id:
            config_ids.append(raw_id)
        raw_entity_id = config.get("__entity_id")
        if isinstance(raw_entity_id, str) and raw_entity_id.startswith("automation."):
            config_ids.append(raw_entity_id.replace("automation.", "", 1))

        ok, reason, _ = await hass.async_add_executor_job(
            partial(
                _apply_fix_to_automation_yaml,
                file_path=config_path,
                automation_id=automation_id,
                location=location,
                expected_current=new_value,
                suggested_value=previous_value,
                candidate_ids=config_ids,
            )
        )
        if not ok:
            connection.send_error(msg["id"], "fix_undo_failed", reason)
            return
        container[key] = previous_value
        persisted_file_change = True
    elif _is_dict_mode_automation_data(hass):
        container[key] = previous_value
    else:
        connection.send_error(
            msg["id"], "fix_undo_failed", "Automation source is not persistable."
        )
        return

    if persisted_file_change:
        try:
            await hass.services.async_call("automation", "reload", {}, blocking=True)
        except Exception as err:
            _LOGGER.warning("Automation reload after undo failed: %s", err)

    try:
        from . import async_validate_all_with_groups

        await async_validate_all_with_groups(hass)
    except Exception as err:
        _LOGGER.warning("Post-undo validation failed: %s", err)

    await _async_save_last_fix_snapshot(hass, None)
    connection.send_result(
        msg["id"],
        {
            "undone": True,
            "automation_id": automation_id,
            "location": location,
            "restored_value": previous_value,
        },
    )
