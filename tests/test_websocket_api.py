"""Tests for WebSocket API."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import Severity
from custom_components.autodoctor.websocket_api import (
    async_setup_websocket_api,
    websocket_get_issues,
    websocket_get_validation,
    websocket_run_validation,
)


@pytest.mark.asyncio
async def test_websocket_api_setup(hass: HomeAssistant):
    """Test WebSocket API can be set up."""
    with patch(
        "homeassistant.components.websocket_api.async_register_command"
    ) as mock_register:
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
async def test_websocket_run_validation_handles_error(hass: HomeAssistant):
    """Test that validation errors return proper error response."""
    hass.data[DOMAIN] = {}

    connection = MagicMock()
    connection.send_result = MagicMock()
    connection.send_error = MagicMock()

    msg = {"id": 1, "type": "autodoctor/validation/run"}

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
