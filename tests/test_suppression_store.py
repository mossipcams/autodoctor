"""Tests for SuppressionStore orphan cleanup."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.suppression_store import SuppressionStore


@pytest.mark.asyncio
async def test_async_load_strips_orphaned_issue_types(hass: HomeAssistant) -> None:
    """Test that async_load removes orphaned suppressions from deleted issue types.

    When IssueType enum values are removed (e.g., template_entity_not_found,
    template_zone_not_found), existing suppressions referencing those types
    become orphaned. This test ensures SuppressionStore automatically detects
    and removes these orphaned entries during load, preventing database bloat
    and user confusion from seeing suppressions for non-existent issue types.
    """
    store = SuppressionStore(hass)

    # Simulate stored data with both valid and orphaned suppression keys.
    # "entity_not_found" is a valid IssueType value; "template_entity_not_found" was removed.
    stored_data: dict[str, Any] = {
        "suppressions": [
            "automation.a:light.a:entity_not_found",
            "automation.b:light.b:template_entity_not_found",
            "automation.c:sensor.c:template_zone_not_found",
        ]
    }

    with (
        patch.object(
            store._store, "async_load", new_callable=AsyncMock, return_value=stored_data
        ),
        patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save,
    ):
        await store.async_load()

    # Only the valid key should remain
    assert store.count == 1
    assert store.is_suppressed("automation.a:light.a:entity_not_found")
    assert not store.is_suppressed("automation.b:light.b:template_entity_not_found")
    assert not store.is_suppressed("automation.c:sensor.c:template_zone_not_found")

    # Should have persisted the cleaned set
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_async_clear_all_removes_all_suppressions(hass: HomeAssistant) -> None:
    """Test that async_clear_all removes all suppressions and persists changes.

    CRITICAL: This method is used in production (websocket_api.py) but was previously
    untested. Verifies that clearing suppressions:
    1. Empties the internal _suppressions set
    2. Updates count to 0
    3. Returns empty frozenset from keys property
    4. Removes all suppressions (is_suppressed returns False)
    5. Calls async_save to persist the empty state
    """
    store = SuppressionStore(hass)

    # Add multiple suppressions
    await store.async_suppress("automation.a:light.a:entity_not_found")
    await store.async_suppress("automation.b:light.b:invalid_state")
    await store.async_suppress("automation.c:sensor.c:attribute_not_found")

    # Verify they exist
    assert store.count == 3
    assert len(store.keys) == 3
    assert store.is_suppressed("automation.a:light.a:entity_not_found")

    # Clear all suppressions
    with patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save:
        await store.async_clear_all()

    # Verify all suppressions removed
    assert store.count == 0
    assert store.keys == frozenset()
    assert not store.is_suppressed("automation.a:light.a:entity_not_found")
    assert not store.is_suppressed("automation.b:light.b:invalid_state")
    assert not store.is_suppressed("automation.c:sensor.c:attribute_not_found")

    # Verify async_save was called to persist empty state
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_async_save_data_verification(hass: HomeAssistant) -> None:
    """Test that async_save is called with correct serialized data.

    Previous test only verified async_save was called, but didn't check WHAT
    data was passed. This test verifies the actual data structure passed to
    the Store.async_save method.
    """
    store = SuppressionStore(hass)

    # Add suppressions
    await store.async_suppress("automation.a:light.a:entity_not_found")
    await store.async_suppress("automation.b:sensor.b:invalid_state")

    # Suppress another and verify the saved data
    with patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save:
        await store.async_suppress("automation.c:switch.c:attribute_not_found")

    # Verify async_save was called with correct data structure
    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][0]

    # Check data structure
    assert isinstance(saved_data, dict)
    assert "suppressions" in saved_data
    assert isinstance(saved_data["suppressions"], list)

    # Check all three suppressions are in the saved data
    assert len(saved_data["suppressions"]) == 3
    assert "automation.a:light.a:entity_not_found" in saved_data["suppressions"]
    assert "automation.b:sensor.b:invalid_state" in saved_data["suppressions"]
    assert "automation.c:switch.c:attribute_not_found" in saved_data["suppressions"]


@pytest.mark.asyncio
async def test_async_load_with_none_returns_empty(hass: HomeAssistant) -> None:
    """Test that async_load handles None (no stored data) without crashing.

    Error handling test: When Store.async_load returns None (first run,
    corrupted data, etc.), the suppression store should initialize with
    an empty set rather than crashing.
    """
    store = SuppressionStore(hass)

    with patch.object(
        store._store, "async_load", new_callable=AsyncMock, return_value=None
    ):
        await store.async_load()

    # Should have empty suppressions
    assert store.count == 0
    assert store.keys == frozenset()
    assert not store.is_suppressed("any_key")


@pytest.mark.asyncio
async def test_async_load_all_keys_orphaned(hass: HomeAssistant) -> None:
    """Test async_load when ALL stored keys reference removed IssueTypes.

    Edge case: If every suppression in storage references a deleted IssueType,
    the cleanup should remove all of them and save an empty set.
    """
    store = SuppressionStore(hass)

    # All keys reference removed issue types
    stored_data: dict[str, Any] = {
        "suppressions": [
            "automation.a:light.a:template_entity_not_found",
            "automation.b:sensor.b:template_zone_not_found",
            "automation.c:switch.c:template_invalid_state",
        ]
    }

    with (
        patch.object(
            store._store, "async_load", new_callable=AsyncMock, return_value=stored_data
        ),
        patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save,
    ):
        await store.async_load()

    # All keys should be removed
    assert store.count == 0
    assert store.keys == frozenset()

    # Should have saved the empty set
    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][0]
    assert saved_data == {"suppressions": []}


@pytest.mark.asyncio
async def test_async_load_no_orphaned_keys(hass: HomeAssistant) -> None:
    """Test async_load when NO keys are orphaned (all valid).

    Edge case: When all stored keys reference valid IssueTypes, cleanup
    should not modify the set or call async_save (no changes needed).
    """
    store = SuppressionStore(hass)

    # All keys reference valid issue types
    stored_data: dict[str, Any] = {
        "suppressions": [
            "automation.a:light.a:entity_not_found",
            "automation.b:sensor.b:invalid_state",
            "automation.c:switch.c:attribute_not_found",
        ]
    }

    with (
        patch.object(
            store._store, "async_load", new_callable=AsyncMock, return_value=stored_data
        ),
        patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save,
    ):
        await store.async_load()

    # All keys should remain
    assert store.count == 3
    assert store.is_suppressed("automation.a:light.a:entity_not_found")
    assert store.is_suppressed("automation.b:sensor.b:invalid_state")
    assert store.is_suppressed("automation.c:switch.c:attribute_not_found")

    # Should NOT have called async_save (no cleanup needed)
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_async_load_with_malformed_keys(hass: HomeAssistant) -> None:
    """Test async_load handles malformed keys (no colons) without crashing.

    Edge case: If storage contains keys without the expected format
    (automation_id:entity_id:issue_type), they should be preserved since
    they don't match the orphan cleanup pattern (rsplit(":", 1) will fail).
    """
    store = SuppressionStore(hass)

    # Mix of valid, orphaned, and malformed keys
    stored_data: dict[str, Any] = {
        "suppressions": [
            "automation.a:light.a:entity_not_found",  # Valid (3 parts, valid IssueType)
            "automation.b:light.b:template_entity_not_found",  # Orphaned (removed IssueType)
            "malformed_key_no_colons",  # Malformed (0 colons, preserved - len(parts)==1)
            "only_one:entity_not_found",  # Malformed but preserved (happens to end with valid IssueType)
            "malformed:invalid_type",  # Malformed (1 colon but invalid second part - removed)
        ]
    }

    with (
        patch.object(
            store._store, "async_load", new_callable=AsyncMock, return_value=stored_data
        ),
        patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save,
    ):
        await store.async_load()

    # Valid 3-part key should remain
    assert store.is_suppressed("automation.a:light.a:entity_not_found")

    # Orphaned key should be removed (invalid IssueType)
    assert not store.is_suppressed("automation.b:light.b:template_entity_not_found")

    # Malformed key with no colons should be preserved (len(parts)==1, condition false)
    assert store.is_suppressed("malformed_key_no_colons")

    # Malformed key with 1 colon but valid IssueType should be preserved
    # (len(parts)==2 but parts[1] IS in valid_issue_types, condition false)
    assert store.is_suppressed("only_one:entity_not_found")

    # Malformed key with 1 colon and invalid type should be removed
    # (len(parts)==2 and parts[1] NOT in valid_issue_types, condition true)
    assert not store.is_suppressed("malformed:invalid_type")

    # Should have saved (cleanup happened)
    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_suppress_calls(hass: HomeAssistant) -> None:
    """Test that concurrent async_suppress calls are handled safely with lock.

    Thread safety test: Multiple concurrent suppress operations should not
    cause race conditions. The asyncio.Lock should ensure each operation
    completes atomically.
    """
    import asyncio

    store = SuppressionStore(hass)

    # Create multiple concurrent suppress tasks
    tasks = [
        store.async_suppress(f"automation.{i}:light.{i}:entity_not_found")
        for i in range(10)
    ]

    # Run all suppressions concurrently
    await asyncio.gather(*tasks)

    # All 10 suppressions should exist
    assert store.count == 10
    for i in range(10):
        assert store.is_suppressed(f"automation.{i}:light.{i}:entity_not_found")


@pytest.mark.asyncio
async def test_async_unsuppress_nonexistent_key(hass: HomeAssistant) -> None:
    """Test that unsuppressing a non-existent key doesn't crash.

    Error handling test: Calling async_unsuppress on a key that was never
    suppressed should be a no-op, not raise an error.
    """
    store = SuppressionStore(hass)

    # Add one suppression
    await store.async_suppress("automation.a:light.a:entity_not_found")
    assert store.count == 1

    # Unsuppress a key that doesn't exist (should not crash)
    with patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save:
        await store.async_unsuppress("automation.nonexistent:light.x:entity_not_found")

    # Count should remain 1
    assert store.count == 1

    # No write should occur when suppression set is unchanged
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_async_suppress_duplicate_key_skips_save(hass: HomeAssistant) -> None:
    """Suppressing an existing key should not re-persist identical data."""
    store = SuppressionStore(hass)
    key = "automation.a:light.a:entity_not_found"
    await store.async_suppress(key)

    with patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save:
        await store.async_suppress(key)

    assert store.count == 1
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_async_clear_all_empty_skips_save(hass: HomeAssistant) -> None:
    """Clearing an already-empty suppression set should not write to disk."""
    store = SuppressionStore(hass)
    assert store.count == 0

    with patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save:
        await store.async_clear_all()

    mock_save.assert_not_called()


async def test_is_suppressed_during_async_load_race(hass: HomeAssistant) -> None:
    """Test is_suppressed() behavior during concurrent async_load() calls.

    This test exercises the race condition identified in code review:
    - is_suppressed() reads self._suppressions without lock
    - async_load() REPLACES self._suppressions with new set (line 54/57)

    Race scenario:
    1. Reader: is_suppressed("key") starts executing
    2. Loader: async_load() executes self._suppressions = cleaned
    3. Reader: continues with old or new set (undefined)

    Real-world impact: During integration reload/restart, suppression state
    may briefly appear incorrect in UI. This is acceptable but should be
    tested to ensure it doesn't cause crashes.
    """
    import asyncio
    from unittest.mock import AsyncMock, patch

    store = SuppressionStore(hass)

    # Set up initial suppressions
    await store.async_suppress("automation.a:light.a:entity_not_found")
    await store.async_suppress("automation.b:light.b:invalid_state")

    errors = []
    check_results = []

    async def concurrent_checker():
        """Continuously check suppression state."""
        for i in range(100):
            try:
                # Check if a key is suppressed
                result = store.is_suppressed("automation.a:light.a:entity_not_found")
                check_results.append(result)
                await asyncio.sleep(0)
            except (AttributeError, RuntimeError, TypeError) as e:
                errors.append(f"Error on iteration {i}: {e}")

    async def concurrent_loader():
        """Simulate async_load() being called (e.g., during reload)."""
        for _i in range(5):
            # Mock async_load to replace suppressions
            mock_data = {
                "suppressions": [
                    "automation.a:light.a:entity_not_found",
                    "automation.c:switch.c:attribute_not_found",
                ]
            }
            with patch.object(
                store._store,
                "async_load",
                new_callable=AsyncMock,
                return_value=mock_data,
            ):
                await store.async_load()
            await asyncio.sleep(0)

    # Run checker and loader concurrently
    await asyncio.gather(
        concurrent_checker(),
        concurrent_checker(),
        concurrent_loader(),
    )

    # Should not have any errors (even if results are inconsistent)
    assert len(errors) == 0, f"Race condition caused errors: {errors}"

    # Results should be consistent (all True or a mix during brief window)
    # At least some should be True since the key exists before and after load
    assert any(check_results), "Key should be suppressed at least sometimes"


def test_filter_suppressed_issues_importable() -> None:
    """filter_suppressed_issues should be importable from suppression_store module."""
    from custom_components.autodoctor.suppression_store import filter_suppressed_issues

    # With no store, all issues pass through
    from custom_components.autodoctor.models import (
        IssueType,
        Severity,
        ValidationIssue,
    )

    issue = ValidationIssue(
        severity=Severity.WARNING,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.foo",
        issue_type=IssueType.ENTITY_NOT_FOUND,
        message="not found",
        location="trigger[0]",
    )
    visible, suppressed = filter_suppressed_issues([issue], None)
    assert visible == [issue]
    assert suppressed == 0


def test_no_duplicate_filter_in_init_or_websocket_api() -> None:
    """Guard: suppression filtering must use the shared filter_suppressed_issues function."""
    from pathlib import Path

    base = Path(__file__).parent.parent / "custom_components" / "autodoctor"
    for filename in ("__init__.py", "websocket_api.py"):
        source = (base / filename).read_text()
        assert "def _filter_suppressed" not in source, (
            f"{filename} still defines its own _filter_suppressed — "
            "use filter_suppressed_issues from suppression_store instead"
        )
