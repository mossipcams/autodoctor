"""Home Assistant Jinja2 filter/test catalog.

Dataclass-based registry of HA's template filters and tests.
Used for unknown-filter/test detection in strict validation mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EntryKind(Enum):
    """Kind of catalog entry."""

    FILTER = "filter"
    TEST = "test"


@dataclass(frozen=True)
class CatalogEntry:
    """A single filter or test in the catalog.

    Attributes:
        name: The filter/test name as used in templates.
        kind: Whether this is a filter or test.
        source: Origin of the entry ("ha" for Home Assistant, "jinja2" for built-in).
        category: Grouping category (e.g., "datetime", "math", "regex").
    """

    name: str
    kind: EntryKind
    source: str = "ha"
    category: str = ""


def _f(name: str, category: str = "") -> CatalogEntry:
    """Shorthand for creating a filter entry."""
    return CatalogEntry(name=name, kind=EntryKind.FILTER, source="ha", category=category)


def _t(name: str, category: str = "") -> CatalogEntry:
    """Shorthand for creating a test entry."""
    return CatalogEntry(name=name, kind=EntryKind.TEST, source="ha", category=category)


# ---------------------------------------------------------------------------
# Filter registry
# ---------------------------------------------------------------------------
_FILTER_REGISTRY: dict[str, CatalogEntry] = {e.name: e for e in [
    # Datetime / timestamp
    _f("as_datetime", "datetime"),
    _f("as_timestamp", "datetime"),
    _f("as_local", "datetime"),
    _f("as_timedelta", "datetime"),
    _f("timestamp_custom", "datetime"),
    _f("timestamp_local", "datetime"),
    _f("timestamp_utc", "datetime"),
    _f("relative_time", "datetime"),
    _f("time_since", "datetime"),
    _f("time_until", "datetime"),
    # JSON
    _f("to_json", "json"),
    _f("from_json", "json"),
    # Type conversion (HA overrides Jinja2 built-ins with default-parameter support)
    _f("float", "type_conversion"),
    _f("int", "type_conversion"),
    _f("bool", "type_conversion"),
    # Validation
    _f("is_defined", "validation"),
    _f("is_number", "validation"),
    _f("has_value", "validation"),
    # Math (round is a Jinja2 built-in that HA overrides with default-parameter support)
    _f("round", "math"),
    _f("log", "math"),
    _f("sin", "math"),
    _f("cos", "math"),
    _f("tan", "math"),
    _f("asin", "math"),
    _f("acos", "math"),
    _f("atan", "math"),
    _f("atan2", "math"),
    _f("sqrt", "math"),
    _f("multiply", "math"),
    _f("add", "math"),
    _f("average", "math"),
    _f("median", "math"),
    _f("statistical_mode", "math"),
    _f("clamp", "math"),
    _f("wrap", "math"),
    _f("remap", "math"),
    # Bitwise
    _f("bitwise_and", "bitwise"),
    _f("bitwise_or", "bitwise"),
    _f("bitwise_xor", "bitwise"),
    _f("ord", "bitwise"),
    # Encoding
    _f("base64_encode", "encoding"),
    _f("base64_decode", "encoding"),
    _f("from_hex", "encoding"),
    # Hashing
    _f("md5", "hashing"),
    _f("sha1", "hashing"),
    _f("sha256", "hashing"),
    _f("sha512", "hashing"),
    # Regex
    _f("regex_match", "regex"),
    _f("regex_search", "regex"),
    _f("regex_replace", "regex"),
    _f("regex_findall", "regex"),
    _f("regex_findall_index", "regex"),
    # String
    _f("slugify", "string"),
    _f("ordinal", "string"),
    # Collections
    _f("set", "collections"),
    _f("shuffle", "collections"),
    _f("flatten", "collections"),
    _f("intersect", "collections"),
    _f("difference", "collections"),
    _f("symmetric_difference", "collections"),
    _f("union", "collections"),
    _f("combine", "collections"),
    _f("contains", "collections"),
    # Entity / device / area / floor / label lookups
    _f("expand", "entity"),
    _f("closest", "entity"),
    _f("distance", "entity"),
    _f("state_attr", "entity"),
    _f("is_state_attr", "entity"),
    _f("is_state", "entity"),
    _f("state_translated", "entity"),
    _f("is_hidden_entity", "entity"),
    _f("device_entities", "entity"),
    _f("device_attr", "entity"),
    _f("is_device_attr", "entity"),
    _f("device_id", "entity"),
    _f("device_name", "entity"),
    _f("config_entry_id", "entity"),
    _f("config_entry_attr", "entity"),
    _f("area_id", "entity"),
    _f("area_name", "entity"),
    _f("area_entities", "entity"),
    _f("area_devices", "entity"),
    _f("floor_id", "entity"),
    _f("floor_name", "entity"),
    _f("floor_areas", "entity"),
    _f("floor_entities", "entity"),
    _f("label_id", "entity"),
    _f("label_name", "entity"),
    _f("label_description", "entity"),
    _f("label_areas", "entity"),
    _f("label_devices", "entity"),
    _f("label_entities", "entity"),
    _f("integration_entities", "entity"),
    # Misc
    _f("iif", "misc"),
    _f("version", "misc"),
    _f("pack", "misc"),
    _f("unpack", "misc"),
    _f("apply", "misc"),
    _f("as_function", "misc"),
    _f("merge_response", "misc"),
    _f("typeof", "misc"),
]}

# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------
_TEST_REGISTRY: dict[str, CatalogEntry] = {e.name: e for e in [
    _t("match", "regex"),
    _t("search", "regex"),
    _t("is_number", "validation"),
    _t("has_value", "validation"),
    _t("contains", "collections"),
    _t("is_list", "type_check"),
    _t("is_set", "type_check"),
    _t("is_tuple", "type_check"),
    _t("is_datetime", "type_check"),
    _t("is_string_like", "type_check"),
    _t("is_boolean", "type_check"),
    _t("is_callable", "type_check"),
    _t("is_float", "type_check"),
    _t("is_integer", "type_check"),
    _t("is_iterable", "type_check"),
    _t("is_mapping", "type_check"),
    _t("is_sequence", "type_check"),
    _t("is_string", "type_check"),
    _t("is_state", "entity"),
    _t("is_state_attr", "entity"),
    _t("is_device_attr", "entity"),
    _t("is_hidden_entity", "entity"),
    _t("apply", "misc"),
]}


# ---------------------------------------------------------------------------
# Public API — accessor functions
# ---------------------------------------------------------------------------

def get_known_filters() -> frozenset[str]:
    """Return the set of all known HA filter names."""
    return frozenset(_FILTER_REGISTRY.keys())


def get_known_tests() -> frozenset[str]:
    """Return the set of all known HA test names."""
    return frozenset(_TEST_REGISTRY.keys())
