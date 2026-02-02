"""Tests for Autodoctor config flow.

These tests exercise config_flow.py directly (ConfigFlow and OptionsFlowHandler)
without loading the full integration, since the integration has heavy HA
dependencies (recorder, frontend, etc.) that aren't available in the test env.
"""

from typing import Any
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


def _init_flow(flow: ConfigFlow, hass: HomeAssistant) -> ConfigFlow:
    """Initialize a config flow with required context.

    Sets up the minimal flow attributes needed for testing without invoking
    the full Home Assistant flow machinery.
    """
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.flow_id = "test_flow"
    flow._flow_result = lambda **kwargs: kwargs
    return flow


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test that initial config flow step displays the user form.

    Verifies that users see a form when they first attempt to configure
    Autodoctor, before submitting any configuration data.
    """
    flow = ConfigFlow()
    _init_flow(flow, hass)

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    """Test that submitting the config flow creates a valid config entry.

    Autodoctor requires no initial configuration data, so submitting
    an empty form should successfully create the integration entry.
    """
    flow = ConfigFlow()
    _init_flow(flow, hass)

    result = await flow.async_step_user(user_input={})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Autodoctor"
    assert result["data"] == {}


async def test_user_step_aborts_if_already_configured(hass: HomeAssistant) -> None:
    """Test that attempting to configure Autodoctor twice is prevented.

    Autodoctor is a single-instance integration. This test ensures that
    the config flow aborts if a user tries to add a second instance.
    """
    from homeassistant.data_entry_flow import AbortFlow

    flow = ConfigFlow()
    _init_flow(flow, hass)

    # Make _abort_if_unique_id_configured raise AbortFlow
    flow._abort_if_unique_id_configured = MagicMock(
        side_effect=AbortFlow("already_configured")
    )

    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user(user_input=None)


def test_get_options_flow_returns_handler() -> None:
    """Test that config flow provides an options handler.

    Verifies the integration exposes an options flow handler to allow
    users to configure runtime options after initial setup.
    """
    entry = MagicMock()
    with patch.object(OptionsFlowHandler, "__init__", lambda self, e: None):
        handler = ConfigFlow.async_get_options_flow(entry)
    assert isinstance(handler, OptionsFlowHandler)


async def test_options_step_init_shows_form(hass: HomeAssistant) -> None:
    """Test that options flow displays configuration form with current values.

    Verifies that when users access integration options, they see a form
    with all configurable settings (history days, validation flags, etc.).
    """
    mock_entry = MagicMock()
    mock_entry.options = {}

    with patch.object(OptionsFlowHandler, "__init__", lambda self, e: None):
        handler = OptionsFlowHandler(mock_entry)
    handler.hass = hass
    handler.flow_id = "test_options"
    # Patch the read-only config_entry property to return our mock
    with patch.object(
        type(handler),
        "config_entry",
        new_callable=lambda: property(lambda self: mock_entry),
    ):
        result = await handler.async_step_init(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["data_schema"] is not None


async def test_options_step_init_saves_input(hass: HomeAssistant) -> None:
    """Test that options flow saves user-provided configuration changes.

    Verifies that when users submit the options form with updated values,
    those values are persisted to the config entry. This enables runtime
    configuration of history retention, validation strictness, etc.
    """
    mock_entry = MagicMock()
    mock_entry.options = {}

    with patch.object(OptionsFlowHandler, "__init__", lambda self, e: None):
        handler = OptionsFlowHandler(mock_entry)
    handler.hass = hass
    handler.flow_id = "test_options"

    user_input: dict[str, Any] = {
        CONF_HISTORY_DAYS: 14,
        CONF_VALIDATE_ON_RELOAD: False,
        CONF_DEBOUNCE_SECONDS: 10,
        CONF_STRICT_TEMPLATE_VALIDATION: True,
        CONF_STRICT_SERVICE_VALIDATION: True,
    }

    result = await handler.async_step_init(user_input=user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == user_input
