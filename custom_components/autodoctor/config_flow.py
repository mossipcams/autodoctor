"""Config flow for Autodoctor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback

from .const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_HISTORY_DAYS,
    CONF_PERIODIC_SCAN_INTERVAL_HOURS,
    CONF_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
    CONF_RUNTIME_HEALTH_BASELINE_DAYS,
    CONF_RUNTIME_HEALTH_ENABLED,
    CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
    CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
    CONF_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
    CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    CONF_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS,
    DEFAULT_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
    DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS,
    DEFAULT_RUNTIME_HEALTH_ENABLED,
    DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
    DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
    DEFAULT_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
    DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES,
    DEFAULT_STRICT_SERVICE_VALIDATION,
    DEFAULT_STRICT_TEMPLATE_VALIDATION,
    DEFAULT_VALIDATE_ON_RELOAD,
    DOMAIN,
)

# Unique ID for single-instance integration
UNIQUE_ID = DOMAIN
_RUNTIME_HEALTH_COLD_START_DAYS = 7
_RUNTIME_HEALTH_MIN_TRAINING_ROWS = 1


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Autodoctor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    @staticmethod
    def _build_options_schema(defaults: Mapping[str, Any]) -> vol.Schema:
        """Build options schema using provided defaults."""
        return vol.Schema(
            {
                vol.Optional(
                    CONF_HISTORY_DAYS,
                    default=defaults.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                vol.Optional(
                    CONF_VALIDATE_ON_RELOAD,
                    default=defaults.get(
                        CONF_VALIDATE_ON_RELOAD, DEFAULT_VALIDATE_ON_RELOAD
                    ),
                ): bool,
                vol.Optional(
                    CONF_DEBOUNCE_SECONDS,
                    default=defaults.get(
                        CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_PERIODIC_SCAN_INTERVAL_HOURS,
                    default=defaults.get(
                        CONF_PERIODIC_SCAN_INTERVAL_HOURS,
                        DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
                vol.Optional(
                    CONF_STRICT_TEMPLATE_VALIDATION,
                    default=defaults.get(
                        CONF_STRICT_TEMPLATE_VALIDATION,
                        DEFAULT_STRICT_TEMPLATE_VALIDATION,
                    ),
                ): bool,
                vol.Optional(
                    CONF_STRICT_SERVICE_VALIDATION,
                    default=defaults.get(
                        CONF_STRICT_SERVICE_VALIDATION,
                        DEFAULT_STRICT_SERVICE_VALIDATION,
                    ),
                ): bool,
                vol.Optional(
                    CONF_RUNTIME_HEALTH_ENABLED,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_ENABLED,
                        DEFAULT_RUNTIME_HEALTH_ENABLED,
                    ),
                ): bool,
                vol.Optional(
                    CONF_RUNTIME_HEALTH_BASELINE_DAYS,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_BASELINE_DAYS,
                        DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=7, max=365)),
                vol.Optional(
                    CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
                        DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                vol.Optional(
                    CONF_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
                        DEFAULT_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
                vol.Optional(
                    CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
                        DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1000)),
                vol.Optional(
                    CONF_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
                        DEFAULT_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=100.0)),
                vol.Optional(
                    CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
                    default=defaults.get(
                        CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
                        DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options."""
        if user_input is not None:
            baseline_days = int(
                user_input.get(
                    CONF_RUNTIME_HEALTH_BASELINE_DAYS,
                    DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS,
                )
            )
            warmup_samples = int(
                user_input.get(
                    CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
                    DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES,
                )
            )
            runtime_enabled = bool(
                user_input.get(
                    CONF_RUNTIME_HEALTH_ENABLED,
                    DEFAULT_RUNTIME_HEALTH_ENABLED,
                )
            )
            if warmup_samples > baseline_days:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_options_schema(user_input),
                    errors={"base": "warmup_exceeds_baseline"},
                )
            effective_training_rows = baseline_days - _RUNTIME_HEALTH_COLD_START_DAYS
            if (
                runtime_enabled
                and effective_training_rows < _RUNTIME_HEALTH_MIN_TRAINING_ROWS
            ):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_options_schema(user_input),
                    errors={"base": "baseline_too_short_for_training"},
                )
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=self._build_options_schema(options),
        )
