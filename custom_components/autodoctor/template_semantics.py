"""Home Assistant Jinja2 filter and test signatures.

This module will contain semantic validation signatures for HA-specific Jinja2
filters and tests. Currently a stub to allow imports.
"""

import re

# Stub - to be implemented in later tasks
FILTER_SIGNATURES = {}
TEST_SIGNATURES = {}

# Entity ID pattern
ENTITY_ID_PATTERN = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")

# Functions that take entity IDs
ENTITY_ID_FUNCTIONS = {
    "states",
    "is_state",
    "state_attr",
    "is_state_attr",
}

# Known global variables in HA templates
KNOWN_GLOBALS = {
    "states",
    "trigger",
    "this",
    "repeat",
    "now",
    "utcnow",
    "as_timestamp",
    "relative_time",
    "timedelta",
}
