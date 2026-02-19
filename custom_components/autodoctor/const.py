"""Constants for Autodoctor."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

DOMAIN = "autodoctor"


def _read_version() -> str:
    """Read version from manifest.json (single source of truth)."""
    manifest = Path(__file__).parent / "manifest.json"
    try:
        return json.loads(manifest.read_text())["version"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return "0.0.0"


VERSION = _read_version()

# Defaults
DEFAULT_HISTORY_DAYS = 30
DEFAULT_VALIDATE_ON_RELOAD = True
DEFAULT_DEBOUNCE_SECONDS = 5
DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS = 4
DEFAULT_STRICT_TEMPLATE_VALIDATION = False
DEFAULT_STRICT_SERVICE_VALIDATION = False
DEFAULT_RUNTIME_HEALTH_ENABLED = False
DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS = 30
DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES = 3
DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS = 0
DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS = 30
DEFAULT_RUNTIME_HEALTH_SENSITIVITY = "medium"
DEFAULT_RUNTIME_HEALTH_BURST_MULTIPLIER = 4.0
DEFAULT_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY = 10
DEFAULT_RUNTIME_HEALTH_SMOOTHING_WINDOW = 5
DEFAULT_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES = 5
DEFAULT_RUNTIME_HEALTH_AUTO_ADAPT = True
# Config keys
CONF_HISTORY_DAYS = "history_days"
CONF_VALIDATE_ON_RELOAD = "validate_on_reload"
CONF_DEBOUNCE_SECONDS = "debounce_seconds"
CONF_PERIODIC_SCAN_INTERVAL_HOURS = "periodic_scan_interval_hours"
CONF_STRICT_TEMPLATE_VALIDATION = "strict_template_validation"
CONF_STRICT_SERVICE_VALIDATION = "strict_service_validation"
CONF_RUNTIME_HEALTH_ENABLED = "runtime_health_enabled"
CONF_RUNTIME_HEALTH_BASELINE_DAYS = "runtime_health_baseline_days"
CONF_RUNTIME_HEALTH_WARMUP_SAMPLES = "runtime_health_warmup_samples"
CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS = "runtime_health_min_expected_events"
CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS = "runtime_health_hour_ratio_days"
CONF_RUNTIME_HEALTH_SENSITIVITY = "runtime_health_sensitivity"
CONF_RUNTIME_HEALTH_BURST_MULTIPLIER = "runtime_health_burst_multiplier"
CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY = "runtime_health_max_alerts_per_day"
CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW = "runtime_health_smoothing_window"
CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES = (
    "runtime_health_restart_exclusion_minutes"
)
CONF_RUNTIME_HEALTH_AUTO_ADAPT = "runtime_health_auto_adapt"


@dataclass(frozen=True)
class RuntimeHealthConfig:
    """Bundled runtime health monitoring configuration."""

    enabled: bool = DEFAULT_RUNTIME_HEALTH_ENABLED
    baseline_days: int = DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS
    warmup_samples: int = DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES
    min_expected_events: int = DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS
    hour_ratio_days: int = DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS
    sensitivity: str = DEFAULT_RUNTIME_HEALTH_SENSITIVITY
    burst_multiplier: float = DEFAULT_RUNTIME_HEALTH_BURST_MULTIPLIER
    max_alerts_per_day: int = DEFAULT_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY
    smoothing_window: int = DEFAULT_RUNTIME_HEALTH_SMOOTHING_WINDOW
    restart_exclusion_minutes: int = DEFAULT_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES
    auto_adapt: bool = DEFAULT_RUNTIME_HEALTH_AUTO_ADAPT

    # Mapping from HA options dict keys to dataclass field names
    _OPTION_TO_FIELD: ClassVar[dict[str, str]] = {
        CONF_RUNTIME_HEALTH_ENABLED: "enabled",
        CONF_RUNTIME_HEALTH_BASELINE_DAYS: "baseline_days",
        CONF_RUNTIME_HEALTH_WARMUP_SAMPLES: "warmup_samples",
        CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS: "min_expected_events",
        CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS: "hour_ratio_days",
        CONF_RUNTIME_HEALTH_SENSITIVITY: "sensitivity",
        CONF_RUNTIME_HEALTH_BURST_MULTIPLIER: "burst_multiplier",
        CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY: "max_alerts_per_day",
        CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW: "smoothing_window",
        CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES: "restart_exclusion_minutes",
        CONF_RUNTIME_HEALTH_AUTO_ADAPT: "auto_adapt",
    }

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> RuntimeHealthConfig:
        """Create config from Home Assistant options dict."""
        kwargs: dict[str, Any] = {}
        for option_key, field_name in cls._OPTION_TO_FIELD.items():
            if option_key in options:
                kwargs[field_name] = options[option_key]
        return cls(**kwargs)


# Domains with well-defined, stable state sets suitable for state validation.
STATE_VALIDATION_WHITELIST: frozenset[str] = frozenset(
    {
        "alarm_control_panel",
        "automation",
        "binary_sensor",
        "calendar",
        "climate",
        "cover",
        "device_tracker",
        "fan",
        "group",
        "humidifier",
        "input_boolean",
        "input_select",
        "lawn_mower",
        "light",
        "lock",
        "media_player",
        "person",
        "remote",
        "schedule",
        "script",
        "select",
        "siren",
        "sun",
        "switch",
        "timer",
        "update",
        "vacuum",
        "valve",
        "water_heater",
        "weather",
    }
)

# Maximum recursion depth for nested action/condition parsing
MAX_RECURSION_DEPTH = 50
