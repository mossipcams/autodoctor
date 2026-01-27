"""Tests for WebSocket API."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.websocket_api import (
    async_setup_websocket_api,
    websocket_get_issues,
)


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
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
    from custom_components.autodoctor.fix_engine import FixEngine

    kb = StateKnowledgeBase(hass)
    fix_engine = FixEngine(hass, kb)

    hass.data[DOMAIN] = {
        "knowledge_base": kb,
        "fix_engine": fix_engine,
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
