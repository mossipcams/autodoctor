"""Tests for runtime event-store feature flag constants."""

from custom_components.autodoctor.const import (
    CONF_RUNTIME_DAILY_ROLLUP_ENABLED,
    CONF_RUNTIME_EVENT_STORE_CUTOVER,
    CONF_RUNTIME_EVENT_STORE_ENABLED,
    CONF_RUNTIME_EVENT_STORE_RECONCILIATION_ENABLED,
    CONF_RUNTIME_EVENT_STORE_SHADOW_READ,
    CONF_RUNTIME_SCHEDULE_ANOMALY_ENABLED,
    DEFAULT_RUNTIME_DAILY_ROLLUP_ENABLED,
    DEFAULT_RUNTIME_EVENT_STORE_CUTOVER,
    DEFAULT_RUNTIME_EVENT_STORE_ENABLED,
    DEFAULT_RUNTIME_EVENT_STORE_RECONCILIATION_ENABLED,
    DEFAULT_RUNTIME_EVENT_STORE_SHADOW_READ,
    DEFAULT_RUNTIME_SCHEDULE_ANOMALY_ENABLED,
)


def test_runtime_event_store_feature_flag_defaults() -> None:
    """Runtime store rollout flags should default to conservative/off settings."""
    assert CONF_RUNTIME_EVENT_STORE_ENABLED == "runtime_event_store_enabled"
    assert CONF_RUNTIME_EVENT_STORE_SHADOW_READ == "runtime_event_store_shadow_read"
    assert CONF_RUNTIME_EVENT_STORE_CUTOVER == "runtime_event_store_cutover"
    assert (
        CONF_RUNTIME_EVENT_STORE_RECONCILIATION_ENABLED
        == "runtime_event_store_reconciliation_enabled"
    )
    assert CONF_RUNTIME_SCHEDULE_ANOMALY_ENABLED == "runtime_schedule_anomaly_enabled"
    assert CONF_RUNTIME_DAILY_ROLLUP_ENABLED == "runtime_daily_rollup_enabled"

    assert DEFAULT_RUNTIME_EVENT_STORE_ENABLED is False
    assert DEFAULT_RUNTIME_EVENT_STORE_SHADOW_READ is False
    assert DEFAULT_RUNTIME_EVENT_STORE_CUTOVER is False
    assert DEFAULT_RUNTIME_EVENT_STORE_RECONCILIATION_ENABLED is False
    assert DEFAULT_RUNTIME_SCHEDULE_ANOMALY_ENABLED is False
    assert DEFAULT_RUNTIME_DAILY_ROLLUP_ENABLED is False
