"""Tests for WebSocket API.

This module tests all WebSocket API commands exposed by Autodoctor,
including validation, issue retrieval, suppression management, and
step-based validation results.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import (
    IssueType,
    Severity,
    ValidationIssue,
)
from custom_components.autodoctor.websocket_api import (
    _compute_group_status,
    _format_issues_with_fixes,
    _resolve_automation_edit_config_id,
    async_setup_websocket_api,
    websocket_clear_suppressions,
    websocket_fix_apply,
    websocket_fix_preview,
    websocket_fix_undo,
    websocket_get_issues,
    websocket_get_validation,
    websocket_get_validation_steps,
    websocket_list_suppressions,
    websocket_refresh,
    websocket_run_validation,
    websocket_run_validation_steps,
    websocket_suppress,
    websocket_unsuppress,
)


async def _invoke_command(
    handler: Any,
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Invoke websocket handler by unwrapping decorators until coroutine function."""
    target = handler
    while not inspect.iscoroutinefunction(target):
        wrapped = getattr(target, "__wrapped__", None)
        if wrapped is None:
            break
        target = wrapped
    assert inspect.iscoroutinefunction(target)
    await target(hass, connection, msg)


@pytest.mark.asyncio
async def test_websocket_api_setup(hass: HomeAssistant) -> None:
    """Test that WebSocket API registers all commands.

    Verifies that async_setup_websocket_api registers all available
    WebSocket commands for the Autodoctor integration.
    """
    with patch(
        "homeassistant.components.websocket_api.async_register_command"
    ) as mock_register:
        await async_setup_websocket_api(hass)
        assert mock_register.call_count == 13


@pytest.mark.parametrize(
    ("handler", "msg"),
    [
        (websocket_refresh, {"id": 1, "type": "autodoctor/refresh"}),
        (websocket_run_validation, {"id": 2, "type": "autodoctor/validation/run"}),
        (
            websocket_run_validation_steps,
            {"id": 3, "type": "autodoctor/validation/run_steps"},
        ),
        (
            websocket_suppress,
            {
                "id": 4,
                "type": "autodoctor/suppress",
                "automation_id": "automation.test",
                "entity_id": "light.kitchen",
                "issue_type": "entity_not_found",
            },
        ),
        (
            websocket_clear_suppressions,
            {"id": 5, "type": "autodoctor/clear_suppressions"},
        ),
        (
            websocket_unsuppress,
            {
                "id": 6,
                "type": "autodoctor/unsuppress",
                "key": "automation.test:light.kitchen:entity_not_found",
            },
        ),
        (
            websocket_fix_apply,
            {
                "id": 7,
                "type": "autodoctor/fix_apply",
                "automation_id": "automation.test",
                "location": "trigger[0].entity_id",
                "current_value": "light.kitchen",
                "suggested_value": "light.kitchen_main",
            },
        ),
        (websocket_fix_undo, {"id": 8, "type": "autodoctor/fix_undo"}),
    ],
)
def test_mutating_websocket_commands_require_admin(
    hass: HomeAssistant,
    handler: Any,
    msg: dict[str, Any],
) -> None:
    """Mutating/expensive websocket commands should reject non-admin users."""
    connection = MagicMock(spec=ActiveConnection)
    connection.user = MagicMock(is_admin=False)

    with pytest.raises(Unauthorized):
        handler(hass, connection, msg)


@pytest.mark.asyncio
async def test_websocket_get_issues_returns_data(hass: HomeAssistant) -> None:
    """Test that websocket_get_issues returns formatted issue data.

    Verifies the command returns issues with fix suggestions and
    healthy automation count.
    """
    hass.data[DOMAIN] = {
        "issues": [],
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()

    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/issues"}

    # Access the underlying async function through __wrapped__
    # (the decorators wrap the function)
    await _invoke_command(websocket_get_issues, hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert "issues" in result
    assert "healthy_count" in result


@pytest.mark.asyncio
async def test_websocket_get_issues_applies_suppression_filtering_on_read(
    hass: HomeAssistant,
) -> None:
    """Issues endpoint should apply suppression filtering against raw cache."""
    suppressed_issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.hidden",
        location="trigger[0]",
        message="Suppressed issue",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=True)
    hass.data[DOMAIN] = {
        "issues": [suppressed_issue],
        "validation_issues_raw": [suppressed_issue],
        "suppression_store": suppression_store,
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/issues"}

    await _invoke_command(websocket_get_issues, hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_websocket_get_validation(hass: HomeAssistant) -> None:
    """Test that websocket_get_validation returns cached validation results.

    Verifies the command returns validation issues and last run timestamp
    without triggering a new validation run.
    """
    hass.data[DOMAIN] = {
        "validation_issues": [],
        "validation_last_run": "2026-01-27T12:00:00+00:00",
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()

    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation"}

    await _invoke_command(websocket_get_validation, hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert result["issues"] == []
    assert result["last_run"] == "2026-01-27T12:00:00+00:00"


@pytest.mark.asyncio
async def test_websocket_get_validation_uses_raw_cache_for_suppressed_count(
    hass: HomeAssistant,
) -> None:
    """Suppressed count should still be computed from raw cached issues."""
    suppressed_issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.hidden",
        location="trigger[0]",
        message="Suppressed issue",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=True)

    hass.data[DOMAIN] = {
        "validation_issues": [],
        "validation_issues_raw": [suppressed_issue],
        "validation_last_run": "2026-02-12T12:00:00+00:00",
        "suppression_store": suppression_store,
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation"}

    await _invoke_command(websocket_get_validation, hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["issues"] == []
    assert result["suppressed_count"] == 1


@pytest.mark.asyncio
async def test_websocket_run_validation(hass: HomeAssistant) -> None:
    """Test that websocket_run_validation executes validation and returns results.

    Verifies the command triggers async_validate_all and returns issues,
    healthy automation count, and timestamp.
    """
    hass.data[DOMAIN] = {
        "validation_issues": [],
        "validation_last_run": "2026-01-27T12:00:00+00:00",
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()

    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run"}

    with patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
        return_value=[],
    ):
        await _invoke_command(websocket_run_validation, hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert "issues" in result
    assert "healthy_count" in result
    assert "last_run" in result


@pytest.mark.asyncio
async def test_websocket_run_validation_handles_error(hass: HomeAssistant) -> None:
    """Test that websocket_run_validation handles exceptions gracefully.

    Verifies that validation errors result in proper error response via
    send_error instead of crashing.
    """
    hass.data[DOMAIN] = {}

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()
    connection.send_error = MagicMock()

    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run"}

    # Mock async_validate_all to raise an exception
    with patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
        side_effect=Exception("Validation failed"),
    ):
        await _invoke_command(websocket_run_validation, hass, connection, msg)

    # Should call send_error, not crash
    connection.send_error.assert_called_once()
    call_args = connection.send_error.call_args
    assert call_args[0][0] == 1  # message id


# === Fixtures ===


def _make_issue(
    issue_type: IssueType,
    severity: Severity,
    entity_id: str = "light.test",
    automation_id: str = "automation.test",
) -> ValidationIssue:
    """Create a test ValidationIssue for testing.

    Args:
        issue_type: Type of validation issue.
        severity: Severity level (ERROR, WARNING, INFO).
        entity_id: Entity ID associated with the issue.
        automation_id: Automation ID associated with the issue.

    Returns:
        ValidationIssue instance with provided parameters.
    """
    return ValidationIssue(
        severity=severity,
        automation_id=automation_id,
        automation_name="Test",
        entity_id=entity_id,
        location="trigger[0]",
        message=f"Test issue: {issue_type.value}",
        issue_type=issue_type,
    )


# === Step-Based Validation Commands ===


@pytest.mark.asyncio
async def test_websocket_run_validation_steps(hass: HomeAssistant) -> None:
    """Test that websocket_run_validation_steps returns grouped validation results.

    Verifies the command executes validation and returns results organized by
    validation group (entity_state, services, templates, runtime_health) with status, counts,
    and duration for each group.
    """
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    template_issue = _make_issue(
        IssueType.TEMPLATE_UNKNOWN_FILTER,
        Severity.WARNING,
        entity_id="sensor.template",
    )

    hass.data[DOMAIN] = {
        "suppression_store": None,
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run_steps"}

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {
                "entity_state": [entity_issue],
                "services": [],
                "templates": [template_issue],
            },
            "group_durations": {
                "entity_state": 45,
                "services": 120,
                "templates": 85,
            },
            "all_issues": [entity_issue, template_issue],
            "timestamp": "2026-01-30T12:00:00+00:00",
        },
    ):
        await _invoke_command(websocket_run_validation_steps, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    # Verify groups structure
    assert len(result["groups"]) == 4

    # entity_state group
    g0 = result["groups"][0]
    assert g0["id"] == "entity_state"
    assert g0["label"] == "Entity & State"
    assert g0["status"] == "fail"
    assert g0["error_count"] == 1
    assert g0["warning_count"] == 0
    assert g0["issue_count"] == 1
    assert g0["duration_ms"] == 45

    # services group
    g1 = result["groups"][1]
    assert g1["id"] == "services"
    assert g1["status"] == "pass"
    assert g1["error_count"] == 0
    assert g1["warning_count"] == 0
    assert g1["issue_count"] == 0
    assert g1["duration_ms"] == 120

    # templates group
    g2 = result["groups"][2]
    assert g2["id"] == "templates"
    assert g2["status"] == "warning"
    assert g2["error_count"] == 0
    assert g2["warning_count"] == 1
    assert g2["issue_count"] == 1
    assert g2["duration_ms"] == 85

    # runtime group
    g3 = result["groups"][3]
    assert g3["id"] == "runtime_health"
    assert g3["status"] == "pass"
    assert g3["duration_ms"] == 0

    # Verify flat issues and metadata
    assert "issues" in result
    assert "healthy_count" in result
    assert "analyzed_automations" in result
    assert "failed_automations" in result
    assert result["last_run"] == "2026-01-30T12:00:00+00:00"
    assert result["suppressed_count"] == 0


@pytest.mark.asyncio
async def test_websocket_run_validation_steps_with_suppression(
    hass: HomeAssistant,
) -> None:
    """Test that websocket_run_validation_steps filters suppressed issues.

    Verifies that issues marked as suppressed are not included in the
    returned results and that suppressed_count is accurate.
    """
    issue1 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.a"
    )
    issue2 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.b"
    )

    # Mock suppression store that suppresses issue1
    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(
        side_effect=lambda key: key == issue1.get_suppression_key()
    )

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run_steps"}

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {
                "entity_state": [issue1, issue2],
                "services": [],
                "templates": [],
            },
            "group_durations": {
                "entity_state": 50,
                "services": 100,
                "templates": 80,
            },
            "all_issues": [issue1, issue2],
            "timestamp": "2026-01-30T12:00:00+00:00",
        },
    ):
        await _invoke_command(websocket_run_validation_steps, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    # entity_state group should have 1 issue (issue2), not 2
    g0 = result["groups"][0]
    assert g0["issue_count"] == 1
    assert result["suppressed_count"] == 1


@pytest.mark.asyncio
async def test_websocket_get_validation_steps_cached(hass: HomeAssistant) -> None:
    """Test that websocket_get_validation_steps returns cached group results.

    Verifies the command returns previously cached validation group data
    without triggering a new validation run.
    """
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)

    hass.data[DOMAIN] = {
        "suppression_store": None,
        "validation_last_run": "2026-01-30T12:00:00+00:00",
        "validation_run_stats": {
            "analyzed_automations": 4,
            "failed_automations": 1,
            "skip_reasons": {
                "runtime_health": {
                    "insufficient_warmup": 2,
                }
            },
        },
        "validation_groups": {
            "entity_state": {
                "issues": [entity_issue],
                "duration_ms": 45,
            },
            "services": {
                "issues": [],
                "duration_ms": 120,
            },
            "templates": {
                "issues": [],
                "duration_ms": 85,
            },
        },
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/steps"}

    await _invoke_command(websocket_get_validation_steps, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    assert len(result["groups"]) == 4
    assert result["groups"][0]["id"] == "entity_state"
    assert result["groups"][0]["status"] == "fail"
    assert result["groups"][0]["error_count"] == 1
    assert result["groups"][0]["issue_count"] == 1
    assert result["groups"][0]["duration_ms"] == 45
    assert result["groups"][1]["status"] == "pass"
    assert result["groups"][2]["status"] == "pass"
    assert result["groups"][3]["status"] == "pass"
    assert result["last_run"] == "2026-01-30T12:00:00+00:00"
    assert result["suppressed_count"] == 0
    assert result["skip_reasons"]["runtime_health"]["insufficient_warmup"] == 2


@pytest.mark.asyncio
async def test_websocket_get_validation_steps_no_prior_run(hass: HomeAssistant) -> None:
    """Test that websocket_get_validation_steps handles no prior validation run.

    Verifies the command returns empty group results with "pass" status
    when validation has never been run.
    """
    hass.data[DOMAIN] = {
        "suppression_store": None,
        "validation_last_run": None,
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/steps"}

    await _invoke_command(websocket_get_validation_steps, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    assert len(result["groups"]) == 4
    for group in result["groups"]:
        assert group["status"] == "pass"
        assert group["error_count"] == 0
        assert group["warning_count"] == 0
        assert group["issue_count"] == 0
        assert group["issues"] == []
        assert group["duration_ms"] == 0
    assert result["last_run"] is None
    assert result["suppressed_count"] == 0


@pytest.mark.asyncio
async def test_websocket_get_validation_steps_applies_suppression_at_read_time(
    hass: HomeAssistant,
) -> None:
    """Test that websocket_get_validation_steps applies suppression filtering.

    Verifies that the cached steps command filters suppressed issues at
    read time, ensuring suppressed_count is accurate.
    """
    issue1 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.a"
    )
    issue2 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.b"
    )

    # Mock suppression store that suppresses issue1
    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(
        side_effect=lambda key: key == issue1.get_suppression_key()
    )

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "validation_last_run": "2026-01-30T12:00:00+00:00",
        "validation_groups": {
            "entity_state": {
                "issues": [issue1, issue2],
                "duration_ms": 50,
            },
            "services": {
                "issues": [],
                "duration_ms": 100,
            },
            "templates": {
                "issues": [],
                "duration_ms": 80,
            },
        },
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/steps"}

    await _invoke_command(websocket_get_validation_steps, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    # Should show only issue2 (issue1 is suppressed)
    g0 = result["groups"][0]
    assert g0["issue_count"] == 1
    assert result["suppressed_count"] == 1


@pytest.mark.asyncio
async def test_websocket_get_validation_steps_prefers_raw_groups_for_suppression_counts(
    hass: HomeAssistant,
) -> None:
    """Cached steps should use raw group cache when available."""
    issue1 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.a"
    )
    issue2 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.b"
    )
    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(
        side_effect=lambda key: key == issue1.get_suppression_key()
    )

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "validation_last_run": "2026-01-30T12:00:00+00:00",
        "validation_groups": {  # filtered cache
            "entity_state": {"issues": [issue2], "duration_ms": 50},
            "services": {"issues": [], "duration_ms": 100},
            "templates": {"issues": [], "duration_ms": 80},
        },
        "validation_groups_raw": {  # raw cache keeps full context
            "entity_state": {"issues": [issue1, issue2], "duration_ms": 50},
            "services": {"issues": [], "duration_ms": 100},
            "templates": {"issues": [], "duration_ms": 80},
        },
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/steps"}

    await _invoke_command(websocket_get_validation_steps, hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    g0 = result["groups"][0]
    assert g0["issue_count"] == 1
    assert result["suppressed_count"] == 1


@pytest.mark.asyncio
async def test_websocket_run_validation_steps_error_handling(
    hass: HomeAssistant,
) -> None:
    """Test that websocket_run_validation_steps handles exceptions gracefully.

    Verifies that validation errors result in proper error response via
    send_error instead of crashing.
    """
    hass.data[DOMAIN] = {}

    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()

    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run_steps"}

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        side_effect=Exception("Validation failed"),
    ):
        await _invoke_command(websocket_run_validation_steps, hass, connection, msg)

    connection.send_error.assert_called_once()
    call_args = connection.send_error.call_args
    assert call_args[0][0] == 1  # message id


def test_compute_group_status() -> None:
    """Test that _compute_group_status returns correct status for issue sets.

    Verifies that the helper function correctly determines group status
    based on issue severity: ERROR -> "fail", WARNING -> "warning",
    INFO/empty -> "pass", with ERROR taking precedence in mixed cases.
    """
    # ERROR issues -> "fail"
    issues_with_error = [
        _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR),
    ]
    assert _compute_group_status(issues_with_error) == "fail"

    # WARNING issues only -> "warning"
    issues_with_warning = [
        _make_issue(IssueType.TEMPLATE_UNKNOWN_FILTER, Severity.WARNING),
    ]
    assert _compute_group_status(issues_with_warning) == "warning"

    # INFO issues only -> "pass" (INFO does not affect status)
    issues_with_info = [
        _make_issue(IssueType.ENTITY_REMOVED, Severity.INFO),
    ]
    assert _compute_group_status(issues_with_info) == "pass"

    # Empty list -> "pass"
    assert _compute_group_status([]) == "pass"

    # Mixed ERROR + WARNING -> "fail" (ERROR takes precedence)
    mixed_issues = [
        _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR),
        _make_issue(IssueType.TEMPLATE_UNKNOWN_FILTER, Severity.WARNING),
    ]
    assert _compute_group_status(mixed_issues) == "fail"


# === Suppression Management Commands ===


@pytest.mark.asyncio
async def test_websocket_suppress_runtime_issue_records_dismissal(
    hass: HomeAssistant,
) -> None:
    """Suppressing runtime issues should feed dismissal learning into runtime monitor."""
    suppression_store = MagicMock()
    suppression_store.async_suppress = AsyncMock()
    suppression_store.count = 1
    runtime_monitor = MagicMock()

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": None,
        "runtime_monitor": runtime_monitor,
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()
    msg: dict[str, Any] = {
        "id": 1,
        "type": "autodoctor/suppress",
        "automation_id": "automation.runtime_test",
        "entity_id": "automation.runtime_test",
        "issue_type": "runtime_automation_gap",
    }

    await _invoke_command(websocket_suppress, hass, connection, msg)

    suppression_store.async_suppress.assert_called_once_with(
        "automation.runtime_test:automation.runtime_test:runtime_automation_gap"
    )
    runtime_monitor.record_issue_dismissed.assert_called_once_with(
        "automation.runtime_test"
    )


@pytest.mark.asyncio
async def test_websocket_suppress_reconciles_visible_issue_cache_and_reporter(
    hass: HomeAssistant,
) -> None:
    """Suppressing should update visible issue cache and repairs immediately."""
    issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.a")
    suppression_store = MagicMock()
    suppression_store.async_suppress = AsyncMock()
    suppression_store.is_suppressed = MagicMock(
        side_effect=lambda key: key == issue.get_suppression_key()
    )
    suppression_store.count = 1
    reporter = MagicMock()
    reporter.async_report_issues = AsyncMock()

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": None,
        "runtime_monitor": None,
        "reporter": reporter,
        "validation_issues_raw": [issue],
        "validation_issues": [issue],
        "issues": [issue],
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_result = MagicMock()
    msg: dict[str, Any] = {
        "id": 5,
        "type": "autodoctor/suppress",
        "automation_id": issue.automation_id,
        "entity_id": issue.entity_id,
        "issue_type": issue.issue_type.value,
    }

    await _invoke_command(websocket_suppress, hass, connection, msg)

    assert hass.data[DOMAIN]["issues"] == []
    assert hass.data[DOMAIN]["validation_issues"] == []
    reporter.async_report_issues.assert_awaited_once_with([])


@pytest.mark.asyncio
async def test_websocket_list_suppressions(hass: HomeAssistant) -> None:
    """Test that websocket_list_suppressions returns suppressed issues with metadata.

    Verifies the command returns all suppressed issues including their
    suppression keys, automation IDs, entity IDs, issue types, and messages.
    """
    issue1 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.a"
    )
    issue2 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.b"
    )

    suppression_store = MagicMock()
    suppression_store.keys = frozenset({issue1.get_suppression_key()})

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "validation_issues": [issue1, issue2],
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/list_suppressions"}

    await _invoke_command(websocket_list_suppressions, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert len(result["suppressions"]) == 1
    item = result["suppressions"][0]
    assert item["key"] == issue1.get_suppression_key()
    assert item["automation_id"] == "automation.test"
    assert item["entity_id"] == "light.a"
    assert item["issue_type"] == "entity_not_found"
    assert item["message"] == "Test issue: entity_not_found"


@pytest.mark.asyncio
async def test_websocket_list_suppressions_uses_raw_issue_cache(
    hass: HomeAssistant,
) -> None:
    """Suppression metadata should resolve from raw issues when filtered cache is empty."""
    issue1 = _make_issue(
        IssueType.ENTITY_NOT_FOUND, Severity.ERROR, entity_id="light.a"
    )

    suppression_store = MagicMock()
    suppression_store.keys = frozenset({issue1.get_suppression_key()})

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "validation_issues": [],
        "validation_issues_raw": [issue1],
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/list_suppressions"}

    await _invoke_command(websocket_list_suppressions, hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert len(result["suppressions"]) == 1
    assert result["suppressions"][0]["message"] == issue1.message


@pytest.mark.asyncio
async def test_websocket_list_suppressions_not_ready(hass: HomeAssistant) -> None:
    """Test that websocket_list_suppressions handles uninitialized store.

    Verifies the command returns "not_ready" error when the suppression
    store is not yet initialized.
    """
    hass.data[DOMAIN] = {}

    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/list_suppressions"}

    await _invoke_command(websocket_list_suppressions, hass, connection, msg)

    connection.send_error.assert_called_once()
    assert connection.send_error.call_args[0][1] == "not_ready"


@pytest.mark.asyncio
async def test_websocket_unsuppress(hass: HomeAssistant) -> None:
    """Test that websocket_unsuppress removes suppression for a given key.

    Verifies the command calls async_unsuppress on the suppression store
    and returns success with updated suppressed_count.
    """
    suppression_store = MagicMock()
    suppression_store.async_unsuppress = AsyncMock()
    suppression_store.count = 0

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
    }

    connection = MagicMock(spec=ActiveConnection)
    key = "automation.test:light.test:entity_not_found"
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/unsuppress", "key": key}

    await _invoke_command(websocket_unsuppress, hass, connection, msg)

    suppression_store.async_unsuppress.assert_called_once_with(key)
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["success"] is True
    assert result["suppressed_count"] == 0


@pytest.mark.asyncio
async def test_websocket_unsuppress_not_ready(hass: HomeAssistant) -> None:
    """Test that websocket_unsuppress handles uninitialized store.

    Verifies the command returns "not_ready" error when the suppression
    store is not yet initialized.
    """
    hass.data[DOMAIN] = {}

    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()
    msg: dict[str, Any] = {
        "id": 1,
        "type": "autodoctor/unsuppress",
        "key": "some:key:here",
    }

    await _invoke_command(websocket_unsuppress, hass, connection, msg)

    connection.send_error.assert_called_once()
    assert connection.send_error.call_args[0][1] == "not_ready"


@pytest.mark.asyncio
async def test_suppression_store_async_unsuppress(hass: HomeAssistant) -> None:
    """Test that SuppressionStore.async_unsuppress removes a suppression key.

    Verifies that async_unsuppress correctly removes a key from the store
    and updates the count accordingly.
    """
    from custom_components.autodoctor.suppression_store import SuppressionStore

    store = SuppressionStore(hass)
    await store.async_suppress("automation.a:light.a:entity_not_found")
    await store.async_suppress("automation.b:light.b:entity_not_found")
    assert store.count == 2

    await store.async_unsuppress("automation.a:light.a:entity_not_found")
    assert store.count == 1
    assert not store.is_suppressed("automation.a:light.a:entity_not_found")
    assert store.is_suppressed("automation.b:light.b:entity_not_found")


@pytest.mark.asyncio
async def test_suppression_store_keys_property(hass: HomeAssistant) -> None:
    """Test that SuppressionStore.keys returns immutable snapshot of all keys.

    Verifies that the keys property returns a frozenset containing all
    currently suppressed issue keys.
    """
    from custom_components.autodoctor.suppression_store import SuppressionStore

    store = SuppressionStore(hass)
    assert store.keys == frozenset()

    await store.async_suppress("automation.a:light.a:entity_not_found")
    await store.async_suppress("automation.b:light.b:entity_not_found")
    result = store.keys
    assert isinstance(result, frozenset)
    assert result == frozenset(
        {
            "automation.a:light.a:entity_not_found",
            "automation.b:light.b:entity_not_found",
        }
    )


def test_format_issues_fix_for_attribute_not_found(hass: HomeAssistant) -> None:
    """Test that fix is generated for ATTRIBUTE_NOT_FOUND with suggestion."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="fan.bedroom",
        location="condition[0]",
        message="Attribute 'fanmode' not found",
        issue_type=IssueType.ATTRIBUTE_NOT_FOUND,
        suggestion="fan_mode",
    )

    result = _format_issues_with_fixes(hass, [issue])

    assert len(result) == 1
    assert result[0]["fix"] is not None
    assert result[0]["fix"]["description"] == "Did you mean 'fan_mode'?"
    assert result[0]["fix"]["fix_value"] == "fan_mode"


def test_format_issues_fix_for_invalid_attribute_value_with_suggestion(
    hass: HomeAssistant,
) -> None:
    """Test that fix is generated for INVALID_ATTRIBUTE_VALUE with suggestion."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="fan.bedroom",
        location="condition[0]",
        message="Invalid value 'aut' for fan_mode",
        issue_type=IssueType.INVALID_ATTRIBUTE_VALUE,
        suggestion="auto",
        valid_states=["auto", "low", "high"],
    )

    result = _format_issues_with_fixes(hass, [issue])

    assert len(result) == 1
    assert result[0]["fix"] is not None
    assert result[0]["fix"]["fix_value"] == "auto"
    assert "auto" in result[0]["fix"]["description"]
    assert "Valid values:" in result[0]["fix"]["description"]


def test_format_issues_fix_for_invalid_attribute_value_valid_states_only(
    hass: HomeAssistant,
) -> None:
    """Test that fix is generated for INVALID_ATTRIBUTE_VALUE with valid_states only."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="fan.bedroom",
        location="condition[0]",
        message="Invalid value for fan_mode",
        issue_type=IssueType.INVALID_ATTRIBUTE_VALUE,
        suggestion=None,
        valid_states=["auto", "low", "high"],
    )

    result = _format_issues_with_fixes(hass, [issue])

    assert len(result) == 1
    assert result[0]["fix"] is not None
    assert "Valid values:" in result[0]["fix"]["description"]
    assert result[0]["fix"]["fix_value"] is None


def test_format_issues_fix_for_invalid_state_with_suggestion(
    hass: HomeAssistant,
) -> None:
    """Test that fix is generated for INVALID_STATE with suggestion."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.alice",
        location="trigger[0].to",
        message="State 'away' is not valid for person.alice",
        issue_type=IssueType.INVALID_STATE,
        suggestion="not_home",
        valid_states=["home", "not_home"],
    )

    result = _format_issues_with_fixes(hass, [issue])

    assert len(result) == 1
    assert result[0]["fix"] is not None
    assert result[0]["fix"]["fix_value"] == "not_home"
    assert "Did you mean 'not_home'?" in result[0]["fix"]["description"]
    assert "Valid values: home, not_home" in result[0]["fix"]["description"]
    assert result[0]["fix"]["fix_type"] == "replace_value"


def test_format_issues_fix_for_invalid_state_valid_states_only(
    hass: HomeAssistant,
) -> None:
    """Test that fix is generated for INVALID_STATE with valid_states only."""
    issue = ValidationIssue(
        severity=Severity.WARNING,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.alice",
        location="condition[0].state",
        message="State 'present' is not valid for person.alice",
        issue_type=IssueType.INVALID_STATE,
        suggestion=None,
        valid_states=["home", "not_home"],
    )

    result = _format_issues_with_fixes(hass, [issue])

    assert len(result) == 1
    assert result[0]["fix"] is not None
    assert result[0]["fix"]["fix_value"] is None
    assert result[0]["fix"]["fix_type"] == "reference"
    assert "Valid values: home, not_home" in result[0]["fix"]["description"]


def test_format_issues_fix_for_case_mismatch(hass: HomeAssistant) -> None:
    """Test that fix is generated for CASE_MISMATCH with suggestion."""
    issue = ValidationIssue(
        severity=Severity.WARNING,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.Living_Room",
        location="action[0].entity_id",
        message="Case mismatch: did you mean 'light.living_room'?",
        issue_type=IssueType.CASE_MISMATCH,
        suggestion="light.living_room",
    )

    result = _format_issues_with_fixes(hass, [issue])

    assert len(result) == 1
    assert result[0]["fix"] is not None
    assert result[0]["fix"]["description"] == "Did you mean 'light.living_room'?"
    assert result[0]["fix"]["fix_value"] == "light.living_room"
    assert result[0]["fix"]["confidence"] == 0.9
    assert result[0]["fix"]["fix_type"] == "replace_value"
    assert result[0]["fix"]["current_value"] == "light.Living_Room"
    assert result[0]["fix"]["suggested_value"] == "light.living_room"
    assert "Case mismatch" in result[0]["fix"]["reason"]


def test_format_issues_with_fixes_includes_edit_url_for_automations_yaml_source(
    hass: HomeAssistant,
) -> None:
    """Edit link should be present for automations defined in automations.yaml."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test_auto",
        automation_name="Test Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    raw_config = type(
        "RawConfig", (), {"__config_file__": "/config/automations.yaml"}
    )()
    entity = MagicMock()
    entity.raw_config = raw_config

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=entity)
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/test_auto"


def test_format_issues_with_fixes_omits_edit_url_for_package_source(
    hass: HomeAssistant,
) -> None:
    """Edit link should be omitted for package-based automations."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test_auto",
        automation_name="Test Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    raw_config = type(
        "RawConfig", (), {"__config_file__": "/config/packages/lighting.yaml"}
    )()
    entity = MagicMock()
    entity.raw_config = raw_config

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=entity)
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] is None


def test_format_issues_with_fixes_omits_edit_url_when_entity_not_found(
    hass: HomeAssistant,
) -> None:
    """Edit link should be omitted when automation entity cannot be resolved."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.missing",
        automation_name="Missing Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=None)
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] is None


def test_format_issues_with_fixes_dict_mode_keeps_edit_url_when_id_exists(
    hass: HomeAssistant,
) -> None:
    """Dict-mode automation data should still expose edit link when id exists."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    hass.data["automation"] = {
        "config": [{"id": "test", "alias": "Test Auto"}],
    }

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/test"


def test_format_issues_with_fixes_handles_dict_raw_config_metadata(
    hass: HomeAssistant,
) -> None:
    """Edit link should be present when raw_config stores __config_file__ as a dict key."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test_auto",
        automation_name="Test Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    entity = MagicMock()
    entity.raw_config = {
        "id": "test_auto",
        "__config_file__": "/config/automations.yaml",
    }

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=entity)
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/test_auto"


def test_format_issues_with_fixes_resolves_edit_url_when_entity_id_differs_from_id(
    hass: HomeAssistant,
) -> None:
    """Edit link should still resolve via raw config id when entity_id slug differs."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.runtime_id_123",
        automation_name="Runtime Test Auto",
        entity_id="automation.runtime_test_auto",
        location="trigger[0]",
        message="Runtime issue",
        issue_type=IssueType.RUNTIME_AUTOMATION_STALLED,
    )

    entity = MagicMock()
    entity.entity_id = "automation.runtime_test_auto"
    entity.raw_config = {
        "id": "runtime_id_123",
        "__config_file__": "/config/automations.yaml",
    }

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=None)
    automation_component.entities = [entity]
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/runtime_id_123"


def test_format_issues_with_fixes_generates_edit_url_when_config_file_absent(
    hass: HomeAssistant,
) -> None:
    """Edit link should still resolve when raw_config lacks __config_file__ metadata."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test_auto",
        automation_name="Test Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    entity = MagicMock()
    entity.raw_config = {"id": "test_auto"}

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=entity)
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/test_auto"


def test_format_issues_with_fixes_falls_back_to_short_id_without_metadata_or_id(
    hass: HomeAssistant,
) -> None:
    """Edit link should fall back to short id when raw_config lacks metadata and id."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test_auto",
        automation_name="Test Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    entity = MagicMock()
    entity.raw_config = {}

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=entity)
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/test_auto"


def test_format_issues_with_fixes_entities_fallback_without_config_file(
    hass: HomeAssistant,
) -> None:
    """Edit link should resolve via entities loop when __config_file__ is absent."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.fallback_auto",
        automation_name="Fallback Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    entity = MagicMock()
    entity.entity_id = "automation.fallback_auto"
    entity.raw_config = {"id": "fallback_auto"}

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=None)
    automation_component.entities = [entity]
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/fallback_auto"


def test_format_issues_with_fixes_entities_fallback_to_short_id_without_config_file_or_id(
    hass: HomeAssistant,
) -> None:
    """Entities loop should fall back to short_id when no __config_file__ and no id."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.no_id_auto",
        automation_name="No ID Auto",
        entity_id="light.kitchen",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    entity = MagicMock()
    entity.entity_id = "automation.no_id_auto"
    entity.raw_config = {}

    automation_component = MagicMock()
    automation_component.get_entity = MagicMock(return_value=None)
    automation_component.entities = [entity]
    hass.data["automation"] = automation_component

    result = _format_issues_with_fixes(hass, [issue])

    assert result[0]["edit_url"] == "/config/automation/edit/no_id_auto"


@pytest.mark.asyncio
async def test_websocket_run_validation_steps_reports_failed_automations(
    hass: HomeAssistant,
) -> None:
    """Test that run_steps response includes validation failure telemetry."""
    hass.data[DOMAIN] = {"suppression_store": None}
    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run_steps"}

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {"entity_state": [], "services": [], "templates": []},
            "group_durations": {"entity_state": 1, "services": 2, "templates": 3},
            "all_issues": [],
            "timestamp": "2026-02-09T12:00:00+00:00",
            "analyzed_automations": 4,
            "failed_automations": 1,
            "skip_reasons": {
                "runtime_health": {
                    "insufficient_baseline": 4,
                }
            },
        },
    ):
        await _invoke_command(websocket_run_validation_steps, hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["analyzed_automations"] == 4
    assert result["failed_automations"] == 1
    assert result["skip_reasons"]["runtime_health"]["insufficient_baseline"] == 4


@pytest.mark.asyncio
async def test_websocket_runtime_health_issue_can_be_suppressed(
    hass: HomeAssistant,
) -> None:
    """Runtime health issues should be filtered by existing suppression logic."""
    runtime_issue = _make_issue(
        IssueType.RUNTIME_AUTOMATION_STALLED,
        Severity.ERROR,
        entity_id="automation.runtime_test",
    )
    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(return_value=True)

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
    }
    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/validation/run_steps"}

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {
                "entity_state": [],
                "services": [],
                "templates": [],
                "runtime_health": [runtime_issue],
            },
            "group_durations": {
                "entity_state": 1,
                "services": 1,
                "templates": 1,
                "runtime_health": 5,
            },
            "all_issues": [runtime_issue],
            "timestamp": "2026-02-11T12:00:00+00:00",
        },
    ):
        await _invoke_command(websocket_run_validation_steps, hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    runtime_group = next(g for g in result["groups"] if g["id"] == "runtime_health")
    assert runtime_group["issue_count"] == 0
    assert result["suppressed_count"] == 1


@pytest.mark.asyncio
async def test_websocket_fix_preview_returns_proposed_change(
    hass: HomeAssistant,
) -> None:
    """Preview returns a concrete change when location resolves."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "test",
                "alias": "Test Automation",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": "light.Living_Room",
                    }
                ],
            }
        ]
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {
        "id": 42,
        "type": "autodoctor/fix_preview",
        "automation_id": "automation.test",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    await _invoke_command(websocket_fix_preview, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["applicable"] is True
    assert result["current_value"] == "light.Living_Room"
    assert result["suggested_value"] == "light.living_room"


@pytest.mark.asyncio
async def test_websocket_fix_preview_resolves_config_when_entity_id_differs_from_id(
    hass: HomeAssistant,
) -> None:
    """Preview should resolve dict-mode config via __entity_id fallback."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "runtime_id_123",
                "__entity_id": "automation.morning_lights",
                "trigger": [{"platform": "state", "entity_id": "light.Living_Room"}],
            }
        ]
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {
        "id": 43,
        "type": "autodoctor/fix_preview",
        "automation_id": "automation.morning_lights",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    await _invoke_command(websocket_fix_preview, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["applicable"] is True
    assert result["current_value"] == "light.Living_Room"


@pytest.mark.asyncio
async def test_websocket_fix_apply_resolves_config_when_entity_id_differs_from_id(
    hass: HomeAssistant,
) -> None:
    """Apply should mutate dict-mode config resolved via __entity_id."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "runtime_id_123",
                "__entity_id": "automation.morning_lights",
                "trigger": [{"platform": "state", "entity_id": "light.Living_Room"}],
            }
        ]
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {
        "id": 98,
        "type": "autodoctor/fix_apply",
        "automation_id": "automation.morning_lights",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {},
            "group_durations": {},
            "all_issues": [],
            "timestamp": "2026-01-01T00:00:00+00:00",
            "analyzed_automations": 0,
            "failed_automations": 0,
            "skip_reasons": {},
        },
    ) as mock_validate:
        await _invoke_command(websocket_fix_apply, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["applied"] is True
    assert (
        hass.data["automation"]["config"][0]["trigger"][0]["entity_id"]
        == "light.living_room"
    )
    mock_validate.assert_awaited_once_with(hass)


@pytest.mark.asyncio
async def test_websocket_fix_apply_updates_automation(
    hass: HomeAssistant,
) -> None:
    """Apply mutates the targeted value and re-validates the automation."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "test",
                "alias": "Test Automation",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": "light.Living_Room",
                    }
                ],
            }
        ]
    }

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {
        "id": 99,
        "type": "autodoctor/fix_apply",
        "automation_id": "automation.test",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {},
            "group_durations": {},
            "all_issues": [],
            "timestamp": "2026-01-01T00:00:00+00:00",
            "analyzed_automations": 0,
            "failed_automations": 0,
            "skip_reasons": {},
        },
    ) as mock_validate:
        await _invoke_command(websocket_fix_apply, hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["applied"] is True
    assert (
        hass.data["automation"]["config"][0]["trigger"][0]["entity_id"]
        == "light.living_room"
    )
    mock_validate.assert_awaited_once_with(hass)


@pytest.mark.asyncio
async def test_websocket_fix_apply_rejects_unexpected_current_value(
    hass: HomeAssistant,
) -> None:
    """Apply refuses updates when the current value no longer matches."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "test",
                "alias": "Test Automation",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": "light.kitchen",
                    }
                ],
            }
        ]
    }

    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()
    msg: dict[str, Any] = {
        "id": 100,
        "type": "autodoctor/fix_apply",
        "automation_id": "automation.test",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    await _invoke_command(websocket_fix_apply, hass, connection, msg)

    connection.send_error.assert_called_once()
    assert connection.send_error.call_args[0][1] == "fix_not_applicable"


@pytest.mark.asyncio
async def test_websocket_fix_apply_rejects_non_persistable_automation_source(
    hass: HomeAssistant,
) -> None:
    """Fix apply should reject config sources that cannot be persisted safely."""

    class _AutomationEntity:
        def __init__(self) -> None:
            self.entity_id = "automation.test"
            self.raw_config = {
                "id": "test",
                "__config_file__": "/config/other_source.yaml",
                "trigger": [{"entity_id": "light.kitchen"}],
            }

    hass.data["automation"] = SimpleNamespace(entities=[_AutomationEntity()])
    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()
    msg: dict[str, Any] = {
        "id": 101,
        "type": "autodoctor/fix_apply",
        "automation_id": "automation.test",
        "location": "trigger[0].entity_id",
        "current_value": "light.kitchen",
        "suggested_value": "light.kitchen_main",
    }

    await _invoke_command(websocket_fix_apply, hass, connection, msg)

    connection.send_error.assert_called_once()
    assert connection.send_error.call_args[0][1] == "fix_not_applicable"


@pytest.mark.asyncio
async def test_websocket_fix_apply_persists_yaml_and_triggers_reload(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Fix apply should persist automations.yaml edits and reload automations."""
    yaml_path = tmp_path / "automations.yaml"
    yaml_path.write_text(
        "- id: test\n  trigger:\n    - entity_id: light.Living_Room\n",
        encoding="utf-8",
    )

    class _AutomationEntity:
        def __init__(self) -> None:
            self.entity_id = "automation.test"
            self.raw_config = {
                "id": "test",
                "__config_file__": str(yaml_path),
                "trigger": [{"entity_id": "light.Living_Room"}],
            }

    hass.data["automation"] = SimpleNamespace(entities=[_AutomationEntity()])
    reload_handler = AsyncMock()
    hass.services.async_register("automation", "reload", reload_handler)

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {
        "id": 102,
        "type": "autodoctor/fix_apply",
        "automation_id": "automation.test",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {},
            "group_durations": {},
            "all_issues": [],
            "timestamp": "2026-01-01T00:00:00+00:00",
            "analyzed_automations": 0,
            "failed_automations": 0,
            "skip_reasons": {},
        },
    ):
        await _invoke_command(websocket_fix_apply, hass, connection, msg)

    connection.send_result.assert_called_once()
    assert "light.living_room" in yaml_path.read_text(encoding="utf-8")
    reload_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_websocket_fix_apply_preserves_unicode_in_persisted_yaml(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """Fix apply must preserve unicode characters (e.g. accented names) in YAML output."""
    yaml_path = tmp_path / "automations.yaml"
    yaml_path.write_text(
        "- id: test\n  alias: \"Lumi\u00e8re du salon\"\n  trigger:\n    - entity_id: light.Living_Room\n",
        encoding="utf-8",
    )

    class _AutomationEntity:
        def __init__(self) -> None:
            self.entity_id = "automation.test"
            self.raw_config = {
                "id": "test",
                "__config_file__": str(yaml_path),
                "alias": "Lumi\u00e8re du salon",
                "trigger": [{"entity_id": "light.Living_Room"}],
            }

    hass.data["automation"] = SimpleNamespace(entities=[_AutomationEntity()])
    reload_handler = AsyncMock()
    hass.services.async_register("automation", "reload", reload_handler)

    connection = MagicMock(spec=ActiveConnection)
    msg: dict[str, Any] = {
        "id": 110,
        "type": "autodoctor/fix_apply",
        "automation_id": "automation.test",
        "location": "trigger[0].entity_id",
        "current_value": "light.Living_Room",
        "suggested_value": "light.living_room",
    }

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {},
            "group_durations": {},
            "all_issues": [],
            "timestamp": "2026-01-01T00:00:00+00:00",
            "analyzed_automations": 0,
            "failed_automations": 0,
            "skip_reasons": {},
        },
    ):
        await _invoke_command(websocket_fix_apply, hass, connection, msg)

    connection.send_result.assert_called_once()
    written = yaml_path.read_text(encoding="utf-8")
    assert "Lumi\u00e8re du salon" in written, (
        f"Unicode alias was escaped or corrupted in output: {written!r}"
    )


@pytest.mark.asyncio
async def test_websocket_fix_undo_loads_snapshot_from_store(
    hass: HomeAssistant,
) -> None:
    """Undo should read snapshot from persistent store when memory cache is empty."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "test",
                "trigger": [{"entity_id": "light.living_room"}],
            }
        ]
    }
    hass.data[DOMAIN] = {}

    connection = MagicMock(spec=ActiveConnection)
    with (
        patch(
            "custom_components.autodoctor.websocket_api._get_fix_snapshot_store"
        ) as mock_store_factory,
        patch(
            "custom_components.autodoctor.async_validate_all_with_groups",
            new_callable=AsyncMock,
            return_value={
                "group_issues": {},
                "group_durations": {},
                "all_issues": [],
                "timestamp": "2026-01-01T00:00:00+00:00",
                "analyzed_automations": 0,
                "failed_automations": 0,
                "skip_reasons": {},
            },
        ),
    ):
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(
            return_value={
                "last_applied_fix": {
                    "automation_id": "automation.test",
                    "location": "trigger[0].entity_id",
                    "previous_value": "light.Living_Room",
                    "new_value": "light.living_room",
                }
            }
        )
        mock_store.async_save = AsyncMock()
        mock_store_factory.return_value = mock_store

        await _invoke_command(
            websocket_fix_undo,
            hass,
            connection,
            {"id": 103, "type": "autodoctor/fix_undo"},
        )

    connection.send_result.assert_called_once()
    assert (
        hass.data["automation"]["config"][0]["trigger"][0]["entity_id"]
        == "light.Living_Room"
    )


@pytest.mark.asyncio
async def test_websocket_fix_undo_reverts_last_applied_fix(
    hass: HomeAssistant,
) -> None:
    """Undo restores previous value from the last applied fix snapshot."""
    hass.data["automation"] = {
        "config": [
            {
                "id": "test",
                "trigger": [{"entity_id": "light.living_room"}],
            }
        ]
    }
    hass.data[DOMAIN] = {
        "last_applied_fix": {
            "automation_id": "automation.test",
            "location": "trigger[0].entity_id",
            "previous_value": "light.Living_Room",
            "new_value": "light.living_room",
        }
    }
    connection = MagicMock(spec=ActiveConnection)

    with patch(
        "custom_components.autodoctor.async_validate_all_with_groups",
        new_callable=AsyncMock,
        return_value={
            "group_issues": {},
            "group_durations": {},
            "all_issues": [],
            "timestamp": "2026-01-01T00:00:00+00:00",
            "analyzed_automations": 0,
            "failed_automations": 0,
            "skip_reasons": {},
        },
    ) as mock_validate:
        await _invoke_command(
            websocket_fix_undo,
            hass,
            connection,
            {"id": 7, "type": "autodoctor/fix_undo"},
        )

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["undone"] is True
    assert (
        hass.data["automation"]["config"][0]["trigger"][0]["entity_id"]
        == "light.Living_Room"
    )
    assert hass.data[DOMAIN].get("last_applied_fix") is None
    mock_validate.assert_awaited_once_with(hass)


@pytest.mark.asyncio
async def test_websocket_fix_undo_rejects_when_no_snapshot(
    hass: HomeAssistant,
) -> None:
    """Undo fails when there is no stored fix snapshot."""
    hass.data[DOMAIN] = {}
    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()

    await _invoke_command(
        websocket_fix_undo, hass, connection, {"id": 8, "type": "autodoctor/fix_undo"}
    )

    connection.send_error.assert_called_once()
    assert connection.send_error.call_args[0][1] == "fix_undo_unavailable"


def test_resolve_automation_edit_config_id_returns_none_when_automation_data_missing(
    hass: HomeAssistant,
) -> None:
    """_resolve_automation_edit_config_id should return None when hass.data has no automation key."""
    hass.data.pop("automation", None)

    assert _resolve_automation_edit_config_id(hass, "automation.test") is None
