"""Tests for ha_catalog — HA-specific Jinja2 filter/test catalog."""

from __future__ import annotations

import importlib

import pytest

from custom_components.autodoctor.ha_catalog import (
    CatalogEntry,
    EntryKind,
    get_known_filters,
    get_known_tests,
)


class TestCatalogEntry:
    """Test the CatalogEntry dataclass."""

    def test_create_minimal_entry(self) -> None:
        """Test CatalogEntry creation with only required fields.

        Verifies that a catalog entry can be created with just name and kind,
        relying on default values for optional fields.
        """
        entry = CatalogEntry(
            name="float",
            kind=EntryKind.FILTER,
        )
        assert entry.name == "float"
        assert entry.kind == EntryKind.FILTER

    def test_create_full_entry(self) -> None:
        """Test CatalogEntry creation with all fields specified.

        Verifies that all optional fields (source, category) can be
        explicitly set when creating a catalog entry.
        """
        entry = CatalogEntry(
            name="regex_match",
            kind=EntryKind.FILTER,
            source="ha",
            category="regex",
        )
        assert entry.name == "regex_match"
        assert entry.source == "ha"
        assert entry.category == "regex"

    def test_entry_is_frozen(self) -> None:
        """Test that CatalogEntry is immutable after creation.

        Frozen dataclasses prevent accidental mutation, ensuring catalog
        entries remain constant throughout their lifetime.
        """
        entry = CatalogEntry(
            name="float",
            kind=EntryKind.FILTER,
        )
        with pytest.raises(AttributeError):
            entry.name = "int"  # type: ignore[misc]

    def test_no_arg_fields(self) -> None:
        """Test that min_args and max_args fields are not present.

        These fields were removed when argument counting validation
        was delegated to Jinja2's native error handling.
        """
        entry = CatalogEntry(
            name="iif",
            kind=EntryKind.FILTER,
        )
        assert not hasattr(entry, "min_args")
        assert not hasattr(entry, "max_args")

    def test_defaults(self) -> None:
        """Test that optional fields have correct default values.

        Source defaults to 'ha' and category defaults to empty string,
        allowing minimal catalog entries to be created easily.
        """
        entry = CatalogEntry(
            name="test_entry",
            kind=EntryKind.TEST,
        )
        assert entry.source == "ha"
        assert entry.category == ""


class TestEntryKind:
    """Test the EntryKind enum."""

    @pytest.mark.parametrize(
        ("kind", "expected_value"),
        [
            (EntryKind.FILTER, "filter"),
            (EntryKind.TEST, "test"),
        ],
        ids=["filter-kind", "test-kind"],
    )
    def test_entry_kind_values(self, kind: EntryKind, expected_value: str) -> None:
        """Test that EntryKind enum values match expected strings.

        These string values are used when serializing catalog entries
        and must remain stable for backward compatibility.
        """
        assert kind.value == expected_value


class TestRegistryAccessors:
    """Test the module-level accessor functions."""

    @pytest.mark.parametrize(
        ("accessor_func", "expected_type"),
        [
            (get_known_filters, frozenset),
            (get_known_tests, frozenset),
        ],
        ids=["filters-frozenset", "tests-frozenset"],
    )
    def test_accessor_returns_frozenset(
        self, accessor_func: object, expected_type: type[frozenset[str]]
    ) -> None:
        """Test that catalog accessors return immutable frozensets.

        Frozensets prevent external code from modifying the catalog,
        ensuring catalog integrity throughout the application lifecycle.
        """
        result = accessor_func()  # type: ignore[operator]
        assert isinstance(result, expected_type)
        assert len(result) > 0

    @pytest.mark.parametrize(
        "core_filter",
        [
            "as_datetime",
            "as_timestamp",
            "as_local",
            "to_json",
            "from_json",
            "float",
            "int",
            "bool",
            "regex_match",
            "regex_search",
            "regex_replace",
            "slugify",
            "base64_encode",
            "base64_decode",
            "md5",
            "sha1",
            "sha256",
            "sha512",
            "iif",
            "multiply",
            "add",
            "average",
            "median",
        ],
        ids=[
            "datetime-as_datetime",
            "datetime-as_timestamp",
            "datetime-as_local",
            "json-to_json",
            "json-from_json",
            "type-float",
            "type-int",
            "type-bool",
            "regex-match",
            "regex-search",
            "regex-replace",
            "string-slugify",
            "encoding-base64_encode",
            "encoding-base64_decode",
            "hash-md5",
            "hash-sha1",
            "hash-sha256",
            "hash-sha512",
            "misc-iif",
            "math-multiply",
            "math-add",
            "math-average",
            "math-median",
        ],
    )
    def test_known_filters_contain_core_ha_filter(self, core_filter: str) -> None:
        """Test that essential HA filters are present in the catalog.

        These filters are commonly used in Home Assistant templates and
        must be recognized by the validator to avoid false positives.
        """
        filters = get_known_filters()
        assert core_filter in filters, (
            f"Core filter '{core_filter}' missing from catalog"
        )

    @pytest.mark.parametrize(
        "core_test",
        [
            "match",
            "search",
            "is_number",
            "has_value",
            "contains",
            "is_list",
            "is_set",
            "is_tuple",
            "is_state",
            "is_state_attr",
        ],
        ids=[
            "regex-match",
            "regex-search",
            "validation-is_number",
            "validation-has_value",
            "collections-contains",
            "type-is_list",
            "type-is_set",
            "type-is_tuple",
            "entity-is_state",
            "entity-is_state_attr",
        ],
    )
    def test_known_tests_contain_core_ha_test(self, core_test: str) -> None:
        """Test that essential HA tests are present in the catalog.

        These Jinja2 tests are commonly used in Home Assistant templates
        and must be recognized to prevent incorrect validation errors.
        """
        tests = get_known_tests()
        assert core_test in tests, f"Core test '{core_test}' missing from catalog"

    @pytest.mark.parametrize(
        "removed_function",
        ["get_filter_entry", "get_test_entry"],
        ids=["filter-entry-removed", "test-entry-removed"],
    )
    def test_legacy_functions_removed(self, removed_function: str) -> None:
        """Test that legacy accessor functions have been removed.

        These functions exposed internal catalog structure and were removed
        in favor of simple name-set accessors (get_known_filters/tests).
        """
        import custom_components.autodoctor.ha_catalog as catalog

        assert not hasattr(catalog, removed_function), (
            f"{removed_function}() still exists in public API"
        )


class TestCatalogCompleteness:
    """Verify catalog completeness and migration state."""

    @pytest.mark.parametrize(
        ("accessor_func", "min_count", "item_type"),
        [
            (get_known_filters, 100, "filters"),
            (get_known_tests, 23, "tests"),
        ],
        ids=["filters-count", "tests-count"],
    )
    def test_catalog_minimum_counts(
        self, accessor_func: object, min_count: int, item_type: str
    ) -> None:
        """Test that catalog contains minimum expected number of entries.

        These minimum counts ensure the catalog isn't accidentally cleared
        or partially populated during refactoring or updates.
        """
        items = accessor_func()  # type: ignore[operator]
        actual_count = len(items)  # type: ignore[arg-type]
        assert actual_count >= min_count, (
            f"Catalog only has {actual_count} {item_type}, expected at least {min_count}"
        )

    def test_catalog_has_no_arg_fields(self) -> None:
        """Test that catalog entries no longer contain arg count fields.

        The min_args/max_args fields were removed when argument validation
        was delegated to Jinja2's native error handling system.
        """
        from custom_components.autodoctor.ha_catalog import _FILTER_REGISTRY

        for name, entry in _FILTER_REGISTRY.items():
            assert not hasattr(entry, "min_args"), f"Filter '{name}' still has min_args"
            assert not hasattr(entry, "max_args"), f"Filter '{name}' still has max_args"

    @pytest.mark.parametrize(
        "legacy_attribute",
        ["_HA_FILTERS", "_HA_TESTS"],
        ids=["filters-removed", "tests-removed"],
    )
    def test_legacy_jinja_validator_attributes_removed(
        self, legacy_attribute: str
    ) -> None:
        """Test that legacy catalog attributes removed from jinja_validator.

        After migration to ha_catalog module, the old _HA_FILTERS and
        _HA_TESTS constants should no longer exist in jinja_validator.py.
        """
        import custom_components.autodoctor.jinja_validator as jv

        assert not hasattr(jv, legacy_attribute), (
            f"{legacy_attribute} still exists in jinja_validator.py — migration incomplete"
        )

    def test_template_semantics_module_removed(self) -> None:
        """Test that deprecated template_semantics module has been deleted.

        The template_semantics module was replaced by ha_catalog and should
        no longer be importable. This prevents code from using the old API.
        """
        try:
            importlib.import_module("custom_components.autodoctor.template_semantics")
            msg = "template_semantics is still importable — delete it"
            raise AssertionError(msg)
        except ImportError:
            pass  # Expected
