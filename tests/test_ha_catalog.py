"""Tests for ha_catalog — HA-specific Jinja2 filter/test catalog."""

import pytest

from custom_components.autodoctor.ha_catalog import (
    CatalogEntry,
    EntryKind,
    get_known_filters,
    get_known_tests,
)


class TestCatalogEntry:
    """Test the CatalogEntry dataclass."""

    def test_create_minimal_entry(self):
        """CatalogEntry can be created with required fields only."""
        entry = CatalogEntry(
            name="float",
            kind=EntryKind.FILTER,
        )
        assert entry.name == "float"
        assert entry.kind == EntryKind.FILTER

    def test_create_full_entry(self):
        """CatalogEntry can be created with all fields."""
        entry = CatalogEntry(
            name="regex_match",
            kind=EntryKind.FILTER,
            source="ha",
            category="regex",
        )
        assert entry.name == "regex_match"
        assert entry.source == "ha"
        assert entry.category == "regex"

    def test_entry_is_frozen(self):
        """CatalogEntry is immutable (frozen dataclass)."""
        entry = CatalogEntry(
            name="float",
            kind=EntryKind.FILTER,
        )
        with pytest.raises(AttributeError):
            entry.name = "int"

    def test_no_arg_fields(self):
        """CatalogEntry no longer has min_args or max_args fields."""
        entry = CatalogEntry(
            name="iif",
            kind=EntryKind.FILTER,
        )
        assert not hasattr(entry, "min_args")
        assert not hasattr(entry, "max_args")

    def test_defaults(self):
        """Optional fields have sensible defaults."""
        entry = CatalogEntry(
            name="test_entry",
            kind=EntryKind.TEST,
        )
        assert entry.source == "ha"
        assert entry.category == ""


class TestEntryKind:
    """Test the EntryKind enum."""

    def test_filter_kind(self):
        assert EntryKind.FILTER.value == "filter"

    def test_test_kind(self):
        assert EntryKind.TEST.value == "test"


class TestRegistryAccessors:
    """Test the module-level accessor functions."""

    def test_get_known_filters_returns_frozenset(self):
        """get_known_filters() returns a frozenset of filter names."""
        filters = get_known_filters()
        assert isinstance(filters, frozenset)
        assert len(filters) > 0

    def test_get_known_tests_returns_frozenset(self):
        """get_known_tests() returns a frozenset of test names."""
        tests = get_known_tests()
        assert isinstance(tests, frozenset)
        assert len(tests) > 0

    def test_known_filters_contain_core_ha_filters(self):
        """Core HA filters must be in the catalog."""
        filters = get_known_filters()
        core_filters = {
            "as_datetime", "as_timestamp", "as_local",
            "to_json", "from_json",
            "float", "int", "bool",
            "regex_match", "regex_search", "regex_replace",
            "slugify", "base64_encode", "base64_decode",
            "md5", "sha1", "sha256", "sha512",
            "iif", "multiply", "add", "average", "median",
        }
        missing = core_filters - filters
        assert not missing, f"Missing core filters: {missing}"

    def test_known_tests_contain_core_ha_tests(self):
        """Core HA tests must be in the catalog."""
        tests = get_known_tests()
        core_tests = {
            "match", "search",
            "is_number", "has_value", "contains",
            "is_list", "is_set", "is_tuple",
            "is_state", "is_state_attr",
        }
        missing = core_tests - tests
        assert not missing, f"Missing core tests: {missing}"

    def test_get_filter_entry_removed(self):
        """get_filter_entry() no longer exists in the public API."""
        import custom_components.autodoctor.ha_catalog as catalog
        assert not hasattr(catalog, "get_filter_entry")

    def test_get_test_entry_removed(self):
        """get_test_entry() no longer exists in the public API."""
        import custom_components.autodoctor.ha_catalog as catalog
        assert not hasattr(catalog, "get_test_entry")


class TestCatalogCompleteness:
    """Verify catalog completeness and migration state."""

    def test_catalog_filter_count(self):
        """Catalog has at least 100 HA-specific filters."""
        assert len(get_known_filters()) >= 100, (
            f"Catalog only has {len(get_known_filters())} filters, expected at least 100"
        )

    def test_catalog_test_count(self):
        """Catalog has at least 23 HA-specific tests."""
        assert len(get_known_tests()) >= 23, (
            f"Catalog only has {len(get_known_tests())} tests, expected at least 23"
        )

    def test_catalog_has_no_arg_fields(self):
        """CatalogEntry no longer carries min_args/max_args."""
        from custom_components.autodoctor.ha_catalog import _FILTER_REGISTRY
        for name, entry in _FILTER_REGISTRY.items():
            assert not hasattr(entry, "min_args"), f"Filter '{name}' still has min_args"
            assert not hasattr(entry, "max_args"), f"Filter '{name}' still has max_args"

    def test_ha_filters_not_in_jinja_validator(self):
        """After migration, _HA_FILTERS should not exist in jinja_validator.py."""
        import custom_components.autodoctor.jinja_validator as jv
        assert not hasattr(jv, "_HA_FILTERS"), (
            "_HA_FILTERS still exists in jinja_validator.py — migration incomplete"
        )

    def test_ha_tests_not_in_jinja_validator(self):
        """After migration, _HA_TESTS should not exist in jinja_validator.py."""
        import custom_components.autodoctor.jinja_validator as jv
        assert not hasattr(jv, "_HA_TESTS"), (
            "_HA_TESTS still exists in jinja_validator.py — migration incomplete"
        )

    def test_template_semantics_not_importable(self):
        """After migration, template_semantics module should not exist."""
        import importlib
        try:
            importlib.import_module("custom_components.autodoctor.template_semantics")
            assert False, "template_semantics is still importable — delete it"
        except ImportError:
            pass  # Expected
