"""Tests for WebSocket API.

This module tests all WebSocket API commands exposed by Autodoctor,
including validation, issue retrieval, suppression management, and
step-based validation results.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import (
    IssueType,
    Severity,
    ValidationIssue,
)
from custom_components.autodoctor.websocket_api import (
    _compute_group_status,
    _format_issues_with_fixes,
    async_setup_websocket_api,
    websocket_get_issues,
    websocket_get_validation,
    websocket_get_validation_steps,
    websocket_list_suppressions,
    websocket_run_validation,
    websocket_run_validation_steps,
    websocket_unsuppress,
)


@pytest.mark.asyncio
async def test_websocket_api_setup(hass: HomeAssistant) -> None:
    """Test that WebSocket API registers all 10 commands.

    Verifies that async_setup_websocket_api registers all available
    WebSocket commands for the Autodoctor integration.
    """
    with patch(
        "homeassistant.components.websocket_api.async_register_command"
    ) as mock_register:
        await async_setup_websocket_api(hass)
        assert mock_register.call_count == 10


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
    await websocket_get_issues.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert "issues" in result
    assert "healthy_count" in result


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

    await websocket_get_validation.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert result["issues"] == []
    assert result["last_run"] == "2026-01-27T12:00:00+00:00"


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
        await websocket_run_validation.__wrapped__(hass, connection, msg)

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
        await websocket_run_validation.__wrapped__(hass, connection, msg)

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
    validation group (entity_state, services, templates) with status, counts,
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
        await websocket_run_validation_steps.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    # Verify groups structure
    assert len(result["groups"]) == 3

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
        await websocket_run_validation_steps.__wrapped__(hass, connection, msg)

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

    await websocket_get_validation_steps.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    assert len(result["groups"]) == 3
    assert result["groups"][0]["id"] == "entity_state"
    assert result["groups"][0]["status"] == "fail"
    assert result["groups"][0]["error_count"] == 1
    assert result["groups"][0]["issue_count"] == 1
    assert result["groups"][0]["duration_ms"] == 45
    assert result["groups"][1]["status"] == "pass"
    assert result["groups"][2]["status"] == "pass"
    assert result["last_run"] == "2026-01-30T12:00:00+00:00"
    assert result["suppressed_count"] == 0


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

    await websocket_get_validation_steps.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    assert len(result["groups"]) == 3
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

    await websocket_get_validation_steps.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    # Should show only issue2 (issue1 is suppressed)
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
        await websocket_run_validation_steps.__wrapped__(hass, connection, msg)

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

    await websocket_list_suppressions.__wrapped__(hass, connection, msg)

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
async def test_websocket_list_suppressions_not_ready(hass: HomeAssistant) -> None:
    """Test that websocket_list_suppressions handles uninitialized store.

    Verifies the command returns "not_ready" error when the suppression
    store is not yet initialized.
    """
    hass.data[DOMAIN] = {}

    connection = MagicMock(spec=ActiveConnection)
    connection.send_error = MagicMock()
    msg: dict[str, Any] = {"id": 1, "type": "autodoctor/list_suppressions"}

    await websocket_list_suppressions.__wrapped__(hass, connection, msg)

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

    await websocket_unsuppress.__wrapped__(hass, connection, msg)

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

    await websocket_unsuppress.__wrapped__(hass, connection, msg)

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
        },
    ):
        await websocket_run_validation_steps.__wrapped__(hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["analyzed_automations"] == 4
    assert result["failed_automations"] == 1
