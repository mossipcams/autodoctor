"""Tests for Autodoctor config flow.

These tests exercise config_flow.py directly (ConfigFlow and OptionsFlowHandler)
without loading the full integration, since the integration has heavy HA
dependencies (recorder, frontend, etc.) that aren't available in the test env.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.autodoctor.config_flow import ConfigFlow, OptionsFlowHandler
from custom_components.autodoctor.const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_HISTORY_DAYS,
    CONF_PERIODIC_SCAN_INTERVAL_HOURS,
    CONF_RUNTIME_HEALTH_AUTO_ADAPT,
    CONF_RUNTIME_HEALTH_BASELINE_DAYS,
    CONF_RUNTIME_HEALTH_BURST_MULTIPLIER,
    CONF_RUNTIME_HEALTH_ENABLED,
    CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
    CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY,
    CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
    CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES,
    CONF_RUNTIME_HEALTH_SENSITIVITY,
    CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW,
    CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    CONF_VALIDATE_ON_RELOAD,
    DOMAIN,
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
    handler = ConfigFlow.async_get_options_flow(entry)
    assert isinstance(handler, OptionsFlowHandler)


async def test_options_step_init_shows_form(hass: HomeAssistant) -> None:
    """Test that options flow displays configuration form with current values.

    Verifies that when users access integration options, they see a form
    with all configurable settings (history days, validation flags, etc.).
    """
    mock_entry = MagicMock()
    mock_entry.options = {}

    handler = OptionsFlowHandler()
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

    handler = OptionsFlowHandler()
    handler.hass = hass
    handler.flow_id = "test_options"

    user_input: dict[str, Any] = {
        CONF_HISTORY_DAYS: 14,
        CONF_VALIDATE_ON_RELOAD: False,
        CONF_DEBOUNCE_SECONDS: 10,
        CONF_PERIODIC_SCAN_INTERVAL_HOURS: 4,
        CONF_STRICT_TEMPLATE_VALIDATION: True,
        CONF_STRICT_SERVICE_VALIDATION: True,
        CONF_RUNTIME_HEALTH_ENABLED: True,
        CONF_RUNTIME_HEALTH_BASELINE_DAYS: 30,
        CONF_RUNTIME_HEALTH_WARMUP_SAMPLES: 14,
        CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS: 1,
    }

    result = await handler.async_step_init(user_input=user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == user_input


async def test_options_step_init_rejects_warmup_over_baseline(
    hass: HomeAssistant,
) -> None:
    """Warmup samples cannot exceed baseline days."""
    mock_entry = MagicMock()
    mock_entry.options = {}

    handler = OptionsFlowHandler()
    handler.hass = hass
    handler.flow_id = "test_options"

    user_input: dict[str, Any] = {
        CONF_HISTORY_DAYS: 14,
        CONF_VALIDATE_ON_RELOAD: False,
        CONF_DEBOUNCE_SECONDS: 10,
        CONF_PERIODIC_SCAN_INTERVAL_HOURS: 4,
        CONF_STRICT_TEMPLATE_VALIDATION: True,
        CONF_STRICT_SERVICE_VALIDATION: True,
        CONF_RUNTIME_HEALTH_ENABLED: True,
        CONF_RUNTIME_HEALTH_BASELINE_DAYS: 7,
        CONF_RUNTIME_HEALTH_WARMUP_SAMPLES: 14,
        CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS: 1,
    }

    with patch.object(
        type(handler),
        "config_entry",
        new_callable=lambda: property(lambda self: mock_entry),
    ):
        result = await handler.async_step_init(user_input=user_input)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"]["base"] == "warmup_exceeds_baseline"


async def test_options_step_init_rejects_baseline_too_short_for_training_rows(
    hass: HomeAssistant,
) -> None:
    """Baseline should be long enough to produce runtime training rows."""
    mock_entry = MagicMock()
    mock_entry.options = {}

    handler = OptionsFlowHandler()
    handler.hass = hass
    handler.flow_id = "test_options"

    user_input: dict[str, Any] = {
        CONF_HISTORY_DAYS: 14,
        CONF_VALIDATE_ON_RELOAD: False,
        CONF_DEBOUNCE_SECONDS: 10,
        CONF_PERIODIC_SCAN_INTERVAL_HOURS: 4,
        CONF_STRICT_TEMPLATE_VALIDATION: True,
        CONF_STRICT_SERVICE_VALIDATION: True,
        CONF_RUNTIME_HEALTH_ENABLED: True,
        CONF_RUNTIME_HEALTH_BASELINE_DAYS: 7,
        CONF_RUNTIME_HEALTH_WARMUP_SAMPLES: 3,
        CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS: 1,
    }

    with patch.object(
        type(handler),
        "config_entry",
        new_callable=lambda: property(lambda self: mock_entry),
    ):
        result = await handler.async_step_init(user_input=user_input)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"]["base"] == "baseline_too_short_for_training"


def test_options_schema_anomaly_threshold_removed() -> None:
    """Guard: anomaly_threshold was dead (never read) and removed in v3."""
    schema = OptionsFlowHandler._build_options_schema(defaults={})
    schema_keys = {str(k) for k in schema.schema}
    assert "runtime_health_anomaly_threshold" not in schema_keys


def test_options_schema_runtime_health_hour_ratio_days_range() -> None:
    """Hour-ratio lookback should be bounded by schema range checks."""
    schema = OptionsFlowHandler._build_options_schema(defaults={})

    valid = schema({CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS: 30})
    assert valid[CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS] == 30

    with pytest.raises(vol.Invalid):
        schema({CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS: 0})


def test_options_schema_rollout_flags_removed() -> None:
    """Guard: Rollout flags removed in v2.28.0 SQLite consolidation.

    The runtime event store is now always-on. Shadow-read, cutover,
    reconciliation, schedule-anomaly, and daily-rollup flags are gone.
    """
    schema = OptionsFlowHandler._build_options_schema(defaults={})
    schema_keys = {str(k) for k in schema.schema}
    removed = {
        "runtime_event_store_enabled",
        "runtime_event_store_shadow_read",
        "runtime_event_store_cutover",
        "runtime_event_store_reconciliation_enabled",
        "runtime_schedule_anomaly_enabled",
        "runtime_daily_rollup_enabled",
    }
    found = removed & schema_keys
    assert not found, f"Rollout flags should be removed from options schema: {found}"


# ===== CFG-01/CFG-02 Fix Tests =====


def test_options_flow_factory_no_args() -> None:
    """Test that async_get_options_flow returns handler without passing config_entry.

    HA 2025.12+ provides config_entry automatically via parent OptionsFlow class.
    The factory should instantiate OptionsFlowHandler with no arguments.
    """
    config_entry = MagicMock()
    handler = ConfigFlow.async_get_options_flow(config_entry)
    assert isinstance(handler, OptionsFlowHandler)


def test_options_flow_handler_has_no_custom_init() -> None:
    """Test that OptionsFlowHandler relies on parent class for config_entry.

    HA 2025.12+ provides self.config_entry automatically via the parent
    OptionsFlow class. We should NOT define a custom __init__ that stores it.
    """
    # Verify no custom __init__ is defined (relies on parent)
    assert "__init__" not in OptionsFlowHandler.__dict__


async def test_options_flow_step_init_shows_form_without_custom_init() -> None:
    """Test that async_step_init can show the options form.

    Verifies that OptionsFlowHandler can access self.config_entry.options
    in async_step_init when the parent OptionsFlow class provides it,
    without needing a custom __init__ to store the config_entry.
    """
    handler = OptionsFlowHandler()

    # Simulate what HA does: provide config_entry via parent property
    mock_entry = MagicMock()
    mock_entry.options = {}

    # Mock the hass object that OptionsFlow needs
    handler.hass = MagicMock()

    # Patch the read-only config_entry property to return our mock
    with patch.object(
        type(handler),
        "config_entry",
        new_callable=lambda: property(lambda self: mock_entry),
    ):
        result = await handler.async_step_init(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"]
    assert CONF_PERIODIC_SCAN_INTERVAL_HOURS in schema.schema
    assert CONF_RUNTIME_HEALTH_ENABLED in schema.schema
    assert CONF_RUNTIME_HEALTH_BASELINE_DAYS in schema.schema
    assert CONF_RUNTIME_HEALTH_WARMUP_SAMPLES in schema.schema
    assert CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS in schema.schema


def test_options_schema_includes_three_model_runtime_fields() -> None:
    """Three-model runtime monitor options should be exposed in options schema."""
    schema = OptionsFlowHandler._build_options_schema(defaults={})

    assert CONF_RUNTIME_HEALTH_SENSITIVITY in schema.schema
    assert CONF_RUNTIME_HEALTH_BURST_MULTIPLIER in schema.schema
    assert CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY in schema.schema
    assert CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW in schema.schema
    assert CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES in schema.schema
    assert CONF_RUNTIME_HEALTH_AUTO_ADAPT in schema.schema


async def test_options_flow_saves_three_model_runtime_fields(
    hass: HomeAssistant,
) -> None:
    """Options flow should persist three-model runtime monitor tuning fields."""
    handler = OptionsFlowHandler()
    handler.hass = hass
    handler.flow_id = "test_options"

    user_input: dict[str, Any] = {
        CONF_HISTORY_DAYS: 14,
        CONF_VALIDATE_ON_RELOAD: False,
        CONF_DEBOUNCE_SECONDS: 5,
        CONF_PERIODIC_SCAN_INTERVAL_HOURS: 4,
        CONF_RUNTIME_HEALTH_ENABLED: True,
        CONF_RUNTIME_HEALTH_BASELINE_DAYS: 30,
        CONF_RUNTIME_HEALTH_WARMUP_SAMPLES: 7,
        CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS: 0,
        CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS: 30,
        CONF_RUNTIME_HEALTH_SENSITIVITY: "medium",
        CONF_RUNTIME_HEALTH_BURST_MULTIPLIER: 4.0,
        CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY: 10,
        CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW: 5,
        CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES: 5,
        CONF_RUNTIME_HEALTH_AUTO_ADAPT: True,
    }

    result = await handler.async_step_init(user_input=user_input)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RUNTIME_HEALTH_SENSITIVITY] == "medium"
    assert result["data"][CONF_RUNTIME_HEALTH_BURST_MULTIPLIER] == 4.0


def test_config_flow_version_is_3() -> None:
    """Config flow version must be 3 after anomaly_threshold removal."""
    assert ConfigFlow.VERSION == 3


@pytest.mark.asyncio
async def test_migrate_entry_v1_strips_removed_options(
    hass: HomeAssistant,
) -> None:
    """Migration from v1 should strip removed rollout option keys."""
    removed_keys = [
        "runtime_event_store_enabled",
        "runtime_event_store_shadow_read",
        "runtime_event_store_cutover",
        "runtime_event_store_reconciliation_enabled",
        "runtime_schedule_anomaly_enabled",
        "runtime_daily_rollup_enabled",
        "runtime_health_overactive_factor",
    ]
    old_options = dict.fromkeys(removed_keys, False)
    old_options[CONF_HISTORY_DAYS] = 14
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        options=old_options,
    )
    entry.add_to_hass(hass)

    result = await ConfigFlow.async_migrate_entry(hass, entry)

    assert result is True
    for key in removed_keys:
        assert key not in entry.options, f"Removed key {key!r} still in options"
    assert entry.options[CONF_HISTORY_DAYS] == 14


@pytest.mark.asyncio
async def test_module_level_migrate_entry_exists_and_works(
    hass: HomeAssistant,
) -> None:
    """HA requires async_migrate_entry as a module-level function in __init__.py."""
    from custom_components.autodoctor import async_migrate_entry

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        options={
            "runtime_event_store_enabled": True,
            CONF_HISTORY_DAYS: 14,
        },
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert "runtime_event_store_enabled" not in entry.options
    assert entry.options[CONF_HISTORY_DAYS] == 14


@pytest.mark.asyncio
async def test_migrate_entry_v2_strips_anomaly_threshold(
    hass: HomeAssistant,
) -> None:
    """Migration from v2 should strip dead anomaly_threshold option."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        options={
            "runtime_health_anomaly_threshold": 1.3,
            CONF_HISTORY_DAYS: 14,
        },
    )
    entry.add_to_hass(hass)

    result = await ConfigFlow.async_migrate_entry(hass, entry)

    assert result is True
    assert "runtime_health_anomaly_threshold" not in entry.options
    assert entry.options[CONF_HISTORY_DAYS] == 14
