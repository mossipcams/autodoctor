"""Tests for WebSocket API."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.websocket_api import (
    async_setup_websocket_api,
    websocket_get_issues,
    websocket_get_validation,
    websocket_run_validation,
    websocket_get_conflicts,
    websocket_run_conflicts,
)
from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import Conflict, Severity


@pytest.mark.asyncio
async def test_websocket_api_setup(hass: HomeAssistant):
    """Test WebSocket API can be set up."""
    with patch("homeassistant.components.websocket_api.async_register_command") as mock_register:
        await async_setup_websocket_api(hass)
        assert mock_register.called


@pytest.mark.asyncio
async def test_websocket_get_issues_returns_data(hass: HomeAssistant):
    """Test websocket_get_issues returns issue data."""
    from custom_components.autodoctor.const import DOMAIN

    hass.data[DOMAIN] = {
        "issues": [],
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {"id": 1, "type": "autodoctor/issues"}

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
async def test_websocket_get_validation(hass: HomeAssistant):
    """Test getting validation issues only."""
    hass.data[DOMAIN] = {
        "validation_issues": [],
        "validation_last_run": "2026-01-27T12:00:00+00:00",
        "fix_engine": None,
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {"id": 1, "type": "autodoctor/validation"}

    await websocket_get_validation.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert result["issues"] == []
    assert result["last_run"] == "2026-01-27T12:00:00+00:00"


@pytest.mark.asyncio
async def test_websocket_run_validation(hass: HomeAssistant):
    """Test running validation and getting results."""
    hass.data[DOMAIN] = {
        "validation_issues": [],
        "validation_last_run": "2026-01-27T12:00:00+00:00",
        "fix_engine": None,
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {"id": 1, "type": "autodoctor/validation/run"}

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
async def test_websocket_get_conflicts(hass: HomeAssistant):
    """Test getting conflicts via WebSocket."""
    # Set up mock data
    hass.data[DOMAIN] = {
        "conflicts": [
            Conflict(
                entity_id="light.living_room",
                automation_a="automation.motion",
                automation_b="automation.away",
                automation_a_name="Motion",
                automation_b_name="Away",
                action_a="turn_on",
                action_b="turn_off",
                severity=Severity.ERROR,
                explanation="Test conflict",
                scenario="Test scenario",
            )
        ],
        "conflicts_last_run": "2026-01-27T12:00:00",
        "suppression_store": None,
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {"id": 1, "type": "autodoctor/conflicts"}

    await websocket_get_conflicts.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["entity_id"] == "light.living_room"
    assert result["last_run"] == "2026-01-27T12:00:00"
    assert result["suppressed_count"] == 0


@pytest.mark.asyncio
async def test_websocket_run_conflicts(hass: HomeAssistant):
    """Test running conflict detection via WebSocket."""
    # Set up mock automation data with overlapping triggers (same time)
    hass.data["automation"] = {
        "config": [
            {
                "id": "motion",
                "alias": "Motion",
                "trigger": [{"platform": "time", "at": "08:00:00"}],
                "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
            },
            {
                "id": "away",
                "alias": "Away",
                "trigger": [{"platform": "time", "at": "08:00:00"}],
                "action": [{"service": "light.turn_off", "target": {"entity_id": "light.living_room"}}],
            },
        ]
    }
    hass.data[DOMAIN] = {"suppression_store": None}

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {"id": 1, "type": "autodoctor/conflicts/run"}

    await websocket_run_conflicts.__wrapped__(hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert len(result["conflicts"]) == 1
    assert "last_run" in result
    assert result["suppressed_count"] == 0
