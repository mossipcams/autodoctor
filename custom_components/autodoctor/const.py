"""Constants for Autodoctor."""

import json
from pathlib import Path

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
DEFAULT_STRICT_TEMPLATE_VALIDATION = False
DEFAULT_STRICT_SERVICE_VALIDATION = False
DEFAULT_RUNTIME_HEALTH_ENABLED = False
DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS = 30
DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES = 14
DEFAULT_RUNTIME_HEALTH_ANOMALY_THRESHOLD = 0.8
DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS = 1
DEFAULT_RUNTIME_HEALTH_OVERACTIVE_FACTOR = 3.0

# Config keys
CONF_HISTORY_DAYS = "history_days"
CONF_VALIDATE_ON_RELOAD = "validate_on_reload"
CONF_DEBOUNCE_SECONDS = "debounce_seconds"
CONF_STRICT_TEMPLATE_VALIDATION = "strict_template_validation"
CONF_STRICT_SERVICE_VALIDATION = "strict_service_validation"
CONF_RUNTIME_HEALTH_ENABLED = "runtime_health_enabled"
CONF_RUNTIME_HEALTH_BASELINE_DAYS = "runtime_health_baseline_days"
CONF_RUNTIME_HEALTH_WARMUP_SAMPLES = "runtime_health_warmup_samples"
CONF_RUNTIME_HEALTH_ANOMALY_THRESHOLD = "runtime_health_anomaly_threshold"
CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS = "runtime_health_min_expected_events"
CONF_RUNTIME_HEALTH_OVERACTIVE_FACTOR = "runtime_health_overactive_factor"

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
