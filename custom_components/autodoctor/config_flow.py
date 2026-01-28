"""Config flow for Autodoctor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_HISTORY_DAYS,
    CONF_VALIDATE_ON_RELOAD,
    CONF_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
)

# Unique ID for single-instance integration
UNIQUE_ID = DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Autodoctor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Set unique ID to prevent duplicate entries
        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Autodoctor",
                data={},
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HISTORY_DAYS,
                        default=options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                    vol.Optional(
                        CONF_VALIDATE_ON_RELOAD,
                        default=options.get(
                            CONF_VALIDATE_ON_RELOAD, DEFAULT_VALIDATE_ON_RELOAD
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_DEBOUNCE_SECONDS,
                        default=options.get(
                            CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
        )
