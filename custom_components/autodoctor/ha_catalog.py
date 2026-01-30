"""Home Assistant Jinja2 filter/test catalog.

Dataclass-based registry of HA's template filters and tests with
argument signatures. Replaces hardcoded frozensets with structured
entries that support argument validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
        min_args: Minimum number of positional arguments (excluding the piped value).
        max_args: Maximum number of positional arguments, or None for unlimited.
        source: Origin of the entry ("ha" for Home Assistant, "jinja2" for built-in).
        category: Grouping category (e.g., "datetime", "math", "regex").
    """

    name: str
    kind: EntryKind
    min_args: int
    max_args: int | None
    source: str = "ha"
    category: str = ""


def _f(name: str, min_args: int, max_args: int | None, category: str = "") -> CatalogEntry:
    """Shorthand for creating a filter entry."""
    return CatalogEntry(name=name, kind=EntryKind.FILTER, min_args=min_args, max_args=max_args, source="ha", category=category)


def _t(name: str, min_args: int, max_args: int | None, category: str = "") -> CatalogEntry:
    """Shorthand for creating a test entry."""
    return CatalogEntry(name=name, kind=EntryKind.TEST, min_args=min_args, max_args=max_args, source="ha", category=category)


# ---------------------------------------------------------------------------
# Filter registry
# ---------------------------------------------------------------------------
_FILTER_REGISTRY: dict[str, CatalogEntry] = {e.name: e for e in [
    # Datetime / timestamp
    _f("as_datetime", 0, 0, "datetime"),
    _f("as_timestamp", 0, 1, "datetime"),
    _f("as_local", 0, 0, "datetime"),
    _f("as_timedelta", 0, 0, "datetime"),
    _f("timestamp_custom", 0, 2, "datetime"),
    _f("timestamp_local", 0, 0, "datetime"),
    _f("timestamp_utc", 0, 0, "datetime"),
    _f("relative_time", 0, 0, "datetime"),
    _f("time_since", 0, 0, "datetime"),
    _f("time_until", 0, 0, "datetime"),
    # JSON
    _f("to_json", 0, 3, "json"),
    _f("from_json", 0, 1, "json"),
    # Type conversion (HA overrides Jinja2 built-ins with default-parameter support)
    _f("float", 0, 1, "type_conversion"),
    _f("int", 0, 2, "type_conversion"),
    _f("bool", 0, 1, "type_conversion"),
    # Validation
    _f("is_defined", 0, 0, "validation"),
    _f("is_number", 0, 0, "validation"),
    _f("has_value", 0, 0, "validation"),
    # Math (round is a Jinja2 built-in that HA overrides with default-parameter support)
    _f("round", 0, 3, "math"),
    _f("log", 0, 2, "math"),
    _f("sin", 0, 0, "math"),
    _f("cos", 0, 0, "math"),
    _f("tan", 0, 0, "math"),
    _f("asin", 0, 0, "math"),
    _f("acos", 0, 0, "math"),
    _f("atan", 0, 0, "math"),
    _f("atan2", 1, 1, "math"),
    _f("sqrt", 0, 1, "math"),
    _f("multiply", 1, 2, "math"),
    _f("add", 1, 2, "math"),
    _f("average", 0, 0, "math"),
    _f("median", 0, 0, "math"),
    _f("statistical_mode", 0, 0, "math"),
    _f("clamp", 2, 3, "math"),
    _f("wrap", 2, 2, "math"),
    _f("remap", 4, 4, "math"),
    # Bitwise
    _f("bitwise_and", 1, 1, "bitwise"),
    _f("bitwise_or", 1, 1, "bitwise"),
    _f("bitwise_xor", 1, 1, "bitwise"),
    _f("ord", 0, 0, "bitwise"),
    # Encoding
    _f("base64_encode", 0, 0, "encoding"),
    _f("base64_decode", 0, 0, "encoding"),
    _f("from_hex", 0, 0, "encoding"),
    # Hashing
    _f("md5", 0, 0, "hashing"),
    _f("sha1", 0, 0, "hashing"),
    _f("sha256", 0, 0, "hashing"),
    _f("sha512", 0, 0, "hashing"),
    # Regex
    _f("regex_match", 1, 2, "regex"),
    _f("regex_search", 1, 2, "regex"),
    _f("regex_replace", 2, 3, "regex"),
    _f("regex_findall", 1, 1, "regex"),
    _f("regex_findall_index", 1, 2, "regex"),
    # String
    _f("slugify", 0, 1, "string"),
    _f("ordinal", 0, 0, "string"),
    # Collections
    _f("set", 0, 0, "collections"),
    _f("shuffle", 0, 0, "collections"),
    _f("flatten", 0, 1, "collections"),
    _f("intersect", 1, 1, "collections"),
    _f("difference", 1, 1, "collections"),
    _f("symmetric_difference", 1, 1, "collections"),
    _f("union", 1, 1, "collections"),
    _f("combine", 1, 1, "collections"),
    _f("contains", 1, 1, "collections"),
    # Entity / device / area / floor / label lookups
    _f("expand", 0, None, "entity"),
    _f("closest", 0, None, "entity"),
    _f("distance", 0, None, "entity"),
    _f("state_attr", 1, 2, "entity"),
    _f("is_state_attr", 2, 3, "entity"),
    _f("is_state", 1, 2, "entity"),
    _f("state_translated", 0, 1, "entity"),
    _f("is_hidden_entity", 0, 1, "entity"),
    _f("device_entities", 0, 1, "entity"),
    _f("device_attr", 1, 2, "entity"),
    _f("is_device_attr", 2, 3, "entity"),
    _f("device_id", 0, 1, "entity"),
    _f("device_name", 0, 1, "entity"),
    _f("config_entry_id", 0, 1, "entity"),
    _f("config_entry_attr", 1, 2, "entity"),
    _f("area_id", 0, 1, "entity"),
    _f("area_name", 0, 1, "entity"),
    _f("area_entities", 0, 1, "entity"),
    _f("area_devices", 0, 1, "entity"),
    _f("floor_id", 0, 1, "entity"),
    _f("floor_name", 0, 1, "entity"),
    _f("floor_areas", 0, 1, "entity"),
    _f("floor_entities", 0, 1, "entity"),
    _f("label_id", 0, 1, "entity"),
    _f("label_name", 0, 1, "entity"),
    _f("label_description", 0, 1, "entity"),
    _f("label_areas", 0, 1, "entity"),
    _f("label_devices", 0, 1, "entity"),
    _f("label_entities", 0, 1, "entity"),
    _f("integration_entities", 0, 1, "entity"),
    # Misc
    _f("iif", 1, 3, "misc"),
    _f("version", 0, 0, "misc"),
    _f("pack", 1, None, "misc"),
    _f("unpack", 1, 2, "misc"),
    _f("apply", 0, None, "misc"),
    _f("as_function", 0, 0, "misc"),
    _f("merge_response", 0, 0, "misc"),
    _f("typeof", 0, 0, "misc"),
]}

# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------
_TEST_REGISTRY: dict[str, CatalogEntry] = {e.name: e for e in [
    _t("match", 1, 1, "regex"),
    _t("search", 1, 1, "regex"),
    _t("is_number", 0, 0, "validation"),
    _t("has_value", 0, 0, "validation"),
    _t("contains", 1, 1, "collections"),
    _t("is_list", 0, 0, "type_check"),
    _t("is_set", 0, 0, "type_check"),
    _t("is_tuple", 0, 0, "type_check"),
    _t("is_datetime", 0, 0, "type_check"),
    _t("is_string_like", 0, 0, "type_check"),
    _t("is_boolean", 0, 0, "type_check"),
    _t("is_callable", 0, 0, "type_check"),
    _t("is_float", 0, 0, "type_check"),
    _t("is_integer", 0, 0, "type_check"),
    _t("is_iterable", 0, 0, "type_check"),
    _t("is_mapping", 0, 0, "type_check"),
    _t("is_sequence", 0, 0, "type_check"),
    _t("is_string", 0, 0, "type_check"),
    _t("is_state", 1, 2, "entity"),
    _t("is_state_attr", 2, 3, "entity"),
    _t("is_device_attr", 2, 3, "entity"),
    _t("is_hidden_entity", 0, 1, "entity"),
    _t("apply", 0, None, "misc"),
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


def get_filter_entry(name: str) -> CatalogEntry | None:
    """Return the CatalogEntry for a filter, or None if unknown."""
    return _FILTER_REGISTRY.get(name)


def get_test_entry(name: str) -> CatalogEntry | None:
    """Return the CatalogEntry for a test, or None if unknown."""
    return _TEST_REGISTRY.get(name)
