"""Tests for Autodoctor config flow.

These tests exercise config_flow.py directly (ConfigFlow and OptionsFlowHandler)
without loading the full integration, since the integration has heavy HA
dependencies (recorder, frontend, etc.) that aren't available in the test env.
"""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.autodoctor.config_flow import ConfigFlow, OptionsFlowHandler
from custom_components.autodoctor.const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_HISTORY_DAYS,
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    CONF_VALIDATE_ON_RELOAD,
)


def _init_flow(flow, hass):
    """Initialize a config flow with required context."""
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.flow_id = "test_flow"
    flow._flow_result = lambda **kwargs: kwargs  # noqa: ARG005
    return flow


async def test_user_step_shows_form(hass: HomeAssistant):
    """First call with no input shows the confirmation form."""
    flow = ConfigFlow()
    _init_flow(flow, hass)

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry(hass: HomeAssistant):
    """Submitting user step creates a config entry."""
    flow = ConfigFlow()
    _init_flow(flow, hass)

    result = await flow.async_step_user(user_input={})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Autodoctor"
    assert result["data"] == {}


async def test_user_step_aborts_if_already_configured(hass: HomeAssistant):
    """Second config entry is aborted (single-instance)."""
    from homeassistant.data_entry_flow import AbortFlow

    flow = ConfigFlow()
    _init_flow(flow, hass)

    # Make _abort_if_unique_id_configured raise AbortFlow
    flow._abort_if_unique_id_configured = MagicMock(
        side_effect=AbortFlow("already_configured")
    )

    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user(user_input=None)


def test_get_options_flow_returns_handler():
    """async_get_options_flow returns OptionsFlowHandler."""
    entry = MagicMock()
    with patch.object(OptionsFlowHandler, "__init__", lambda self, e: None):
        handler = ConfigFlow.async_get_options_flow(entry)
    assert isinstance(handler, OptionsFlowHandler)


async def test_options_step_init_shows_form(hass: HomeAssistant):
    """Options init step with no input shows form with schema."""
    mock_entry = MagicMock()
    mock_entry.options = {}

    with patch.object(OptionsFlowHandler, "__init__", lambda self, e: None):
        handler = OptionsFlowHandler(mock_entry)
    handler.hass = hass
    handler.flow_id = "test_options"
    # Patch the read-only config_entry property to return our mock
    with patch.object(type(handler), "config_entry", new_callable=lambda: property(lambda self: mock_entry)):
        result = await handler.async_step_init(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"] is not None


async def test_options_step_init_saves_input(hass: HomeAssistant):
    """Options init step with user input creates entry with data."""
    mock_entry = MagicMock()
    mock_entry.options = {}

    with patch.object(OptionsFlowHandler, "__init__", lambda self, e: None):
        handler = OptionsFlowHandler(mock_entry)
    handler.hass = hass
    handler.flow_id = "test_options"

    user_input = {
        CONF_HISTORY_DAYS: 14,
        CONF_VALIDATE_ON_RELOAD: False,
        CONF_DEBOUNCE_SECONDS: 10,
        CONF_STRICT_TEMPLATE_VALIDATION: True,
        CONF_STRICT_SERVICE_VALIDATION: True,
    }

    result = await handler.async_step_init(user_input=user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == user_input
