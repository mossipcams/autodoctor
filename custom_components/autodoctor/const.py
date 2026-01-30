"""Constants for Autodoctor."""

DOMAIN = "autodoctor"
VERSION = "2.4.0"

# Defaults
DEFAULT_HISTORY_DAYS = 30
DEFAULT_VALIDATE_ON_RELOAD = True
DEFAULT_DEBOUNCE_SECONDS = 5
DEFAULT_STRICT_TEMPLATE_VALIDATION = False
DEFAULT_STRICT_SERVICE_VALIDATION = False

# Config keys
CONF_HISTORY_DAYS = "history_days"
CONF_VALIDATE_ON_RELOAD = "validate_on_reload"
CONF_DEBOUNCE_SECONDS = "debounce_seconds"
CONF_STRICT_TEMPLATE_VALIDATION = "strict_template_validation"
CONF_STRICT_SERVICE_VALIDATION = "strict_service_validation"

# Domains with well-defined, stable state sets suitable for state validation.
STATE_VALIDATION_WHITELIST: frozenset[str] = frozenset({
    "binary_sensor",
    "person",
    "sun",
    "device_tracker",
    "input_boolean",
    "group",
})

# Maximum recursion depth for nested action/condition parsing
MAX_RECURSION_DEPTH = 50
