"""Tests for ha_catalog — HA-specific Jinja2 filter/test catalog."""

import pytest
from custom_components.autodoctor.ha_catalog import (
    CatalogEntry,
    EntryKind,
    get_known_filters,
    get_known_tests,
    get_filter_entry,
    get_test_entry,
)


class TestCatalogEntry:
    """Test the CatalogEntry dataclass."""

    def test_create_minimal_entry(self):
        """CatalogEntry can be created with required fields only."""
        entry = CatalogEntry(
            name="float",
            kind=EntryKind.FILTER,
            min_args=0,
            max_args=1,
        )
        assert entry.name == "float"
        assert entry.kind == EntryKind.FILTER
        assert entry.min_args == 0
        assert entry.max_args == 1

    def test_create_full_entry(self):
        """CatalogEntry can be created with all fields."""
        entry = CatalogEntry(
            name="regex_match",
            kind=EntryKind.FILTER,
            min_args=1,
            max_args=2,
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
            min_args=0,
            max_args=1,
        )
        with pytest.raises(AttributeError):
            entry.name = "int"

    def test_unlimited_args(self):
        """max_args=None means unlimited arguments."""
        entry = CatalogEntry(
            name="iif",
            kind=EntryKind.FILTER,
            min_args=1,
            max_args=None,
        )
        assert entry.max_args is None

    def test_defaults(self):
        """Optional fields have sensible defaults."""
        entry = CatalogEntry(
            name="test_entry",
            kind=EntryKind.TEST,
            min_args=0,
            max_args=0,
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

    def test_get_filter_entry_returns_entry(self):
        """get_filter_entry() returns a CatalogEntry for known filters."""
        entry = get_filter_entry("float")
        assert entry is not None
        assert isinstance(entry, CatalogEntry)
        assert entry.name == "float"
        assert entry.kind == EntryKind.FILTER

    def test_get_filter_entry_returns_none_for_unknown(self):
        """get_filter_entry() returns None for unknown filters."""
        entry = get_filter_entry("totally_fake_filter")
        assert entry is None

    def test_get_test_entry_returns_entry(self):
        """get_test_entry() returns a CatalogEntry for known tests."""
        entry = get_test_entry("match")
        assert entry is not None
        assert isinstance(entry, CatalogEntry)
        assert entry.name == "match"
        assert entry.kind == EntryKind.TEST

    def test_get_test_entry_returns_none_for_unknown(self):
        """get_test_entry() returns None for unknown tests."""
        entry = get_test_entry("totally_fake_test")
        assert entry is None

    def test_filter_entry_has_valid_args(self):
        """All filter entries have min_args <= max_args (when max_args is set)."""
        for name in get_known_filters():
            entry = get_filter_entry(name)
            assert entry is not None, f"Filter '{name}' in names but no entry"
            assert entry.min_args >= 0, f"Filter '{name}' has negative min_args"
            if entry.max_args is not None:
                assert entry.min_args <= entry.max_args, (
                    f"Filter '{name}' has min_args={entry.min_args} > max_args={entry.max_args}"
                )

    def test_test_entry_has_valid_args(self):
        """All test entries have min_args <= max_args (when max_args is set)."""
        for name in get_known_tests():
            entry = get_test_entry(name)
            assert entry is not None, f"Test '{name}' in names but no entry"
            assert entry.min_args >= 0, f"Test '{name}' has negative min_args"
            if entry.max_args is not None:
                assert entry.min_args <= entry.max_args, (
                    f"Test '{name}' has min_args={entry.min_args} > max_args={entry.max_args}"
                )


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

    def test_all_filter_entries_have_signatures(self):
        """Every filter entry has min_args and max_args defined (not just name)."""
        for name in get_known_filters():
            entry = get_filter_entry(name)
            assert entry is not None
            assert isinstance(entry.min_args, int), f"Filter '{name}' has non-int min_args"
            assert entry.max_args is None or isinstance(entry.max_args, int), (
                f"Filter '{name}' has invalid max_args type"
            )

    def test_all_test_entries_have_signatures(self):
        """Every test entry has min_args and max_args defined."""
        for name in get_known_tests():
            entry = get_test_entry(name)
            assert entry is not None
            assert isinstance(entry.min_args, int), f"Test '{name}' has non-int min_args"
            assert entry.max_args is None or isinstance(entry.max_args, int), (
                f"Test '{name}' has invalid max_args type"
            )

    def test_all_entries_have_categories(self):
        """Every catalog entry has a non-empty category."""
        for name in get_known_filters():
            entry = get_filter_entry(name)
            assert entry.category, f"Filter '{name}' has empty category"
        for name in get_known_tests():
            entry = get_test_entry(name)
            assert entry.category, f"Test '{name}' has empty category"

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
