"""Config flow for Autodoctor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_HISTORY_DAYS,
    CONF_PERIODIC_SCAN_INTERVAL_HOURS,
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    CONF_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS,
    DEFAULT_STRICT_SERVICE_VALIDATION,
    DEFAULT_STRICT_TEMPLATE_VALIDATION,
    DEFAULT_VALIDATE_ON_RELOAD,
    DOMAIN,
    RuntimeHealthConfig,
)

# Unique ID for single-instance integration
UNIQUE_ID = DOMAIN
_RUNTIME_HEALTH_COLD_START_DAYS = 7
_RUNTIME_HEALTH_MIN_TRAINING_ROWS = 1


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Autodoctor."""

    VERSION = 3

    _V1_REMOVED_KEYS = frozenset(
        {
            "runtime_event_store_enabled",
            "runtime_event_store_shadow_read",
            "runtime_event_store_cutover",
            "runtime_event_store_reconciliation_enabled",
            "runtime_schedule_anomaly_enabled",
            "runtime_daily_rollup_enabled",
            "runtime_health_overactive_factor",
        }
    )

    _V2_REMOVED_KEYS = frozenset(
        {
            "runtime_health_anomaly_threshold",
        }
    )

    @classmethod
    async def async_migrate_entry(
        cls, hass: HomeAssistant, entry: config_entries.ConfigEntry
    ) -> bool:
        """Migrate config entry from an older version."""
        if entry.version < 2:
            new_options = {
                k: v for k, v in entry.options.items() if k not in cls._V1_REMOVED_KEYS
            }
            hass.config_entries.async_update_entry(
                entry, options=new_options, version=2
            )
        if entry.version < 3:
            new_options = {
                k: v for k, v in entry.options.items() if k not in cls._V2_REMOVED_KEYS
            }
            hass.config_entries.async_update_entry(
                entry, options=new_options, version=3
            )
        return True

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
        rhc = RuntimeHealthConfig.from_options(dict(defaults))
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
                    "runtime_health_enabled",
                    default=rhc.enabled,
                ): bool,
                vol.Optional(
                    "runtime_health_baseline_days",
                    default=rhc.baseline_days,
                ): vol.All(vol.Coerce(int), vol.Range(min=7, max=365)),
                vol.Optional(
                    "runtime_health_warmup_samples",
                    default=rhc.warmup_samples,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                vol.Optional(
                    "runtime_health_min_expected_events",
                    default=rhc.min_expected_events,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1000)),
                vol.Optional(
                    "runtime_health_hour_ratio_days",
                    default=rhc.hour_ratio_days,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                vol.Optional(
                    "runtime_health_sensitivity",
                    default=rhc.sensitivity,
                ): vol.In(["low", "medium", "high"]),
                vol.Optional(
                    "runtime_health_burst_multiplier",
                    default=rhc.burst_multiplier,
                ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=100.0)),
                vol.Optional(
                    "runtime_health_max_alerts_per_day",
                    default=rhc.max_alerts_per_day,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
                vol.Optional(
                    "runtime_health_smoothing_window",
                    default=rhc.smoothing_window,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                vol.Optional(
                    "runtime_health_restart_exclusion_minutes",
                    default=rhc.restart_exclusion_minutes,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
                vol.Optional(
                    "runtime_health_auto_adapt",
                    default=rhc.auto_adapt,
                ): bool,
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options."""
        if user_input is not None:
            _input_rhc = RuntimeHealthConfig.from_options(user_input)
            baseline_days = _input_rhc.baseline_days
            warmup_samples = _input_rhc.warmup_samples
            runtime_enabled = _input_rhc.enabled
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
