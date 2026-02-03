"""Tests for LearnedStatesStore."""

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.learned_states_store import LearnedStatesStore


async def test_learned_states_store_initialization(hass: HomeAssistant) -> None:
    """Test LearnedStatesStore can be instantiated.

    Verifies basic store initialization works without errors.
    """
    store = LearnedStatesStore(hass)
    assert store is not None


async def test_learn_state_adds_to_store(hass: HomeAssistant) -> None:
    """Test learning a state adds it to the in-memory store.

    When a new state is learned via async_learn_state, it should be retrievable
    via get_learned_states for the same domain/integration pair.
    """
    store = LearnedStatesStore(hass)

    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    states = store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states


async def test_get_learned_states_empty_for_unknown(hass: HomeAssistant) -> None:
    """Test getting states for unknown domain/integration returns empty set.

    Queries for domain/integration pairs that have never been learned should
    return an empty set rather than raising errors or returning None.
    """
    store = LearnedStatesStore(hass)

    states = store.get_learned_states("vacuum", "unknown_brand")
    assert states == set()


async def test_learn_state_deduplicates(hass: HomeAssistant) -> None:
    """Test learning the same state multiple times doesn't create duplicates.

    The store should deduplicate states automatically, ensuring each unique
    state appears only once per domain/integration pair.
    """
    store = LearnedStatesStore(hass)

    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    states = store.get_learned_states("vacuum", "roborock")
    assert list(states).count("segment_cleaning") == 1


async def test_learned_states_persist_across_load(hass: HomeAssistant) -> None:
    """Test learned states persist across store instances via save/load.

    When states are learned and the store is saved, a new store instance
    should be able to load those states from persistent storage.
    """
    store1 = LearnedStatesStore(hass)
    await store1.async_learn_state("vacuum", "roborock", "segment_cleaning")

    # Create new store and load
    store2 = LearnedStatesStore(hass)
    await store2.async_load()

    states = store2.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states


async def test_async_save_data_verification(hass: HomeAssistant) -> None:
    """Test that _async_save is called with correct data structure.

    Previous tests didn't verify WHAT data was saved. This test checks
    the actual data passed to Store.async_save.
    """
    from unittest.mock import AsyncMock, patch

    store = LearnedStatesStore(hass)

    # Learn some states
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")
    await store.async_learn_state("vacuum", "roborock", "charging_error")

    # Learn another state and capture what's saved
    with patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save:
        await store.async_learn_state("vacuum", "ecovacs", "auto_clean")

    # Verify async_save was called
    mock_save.assert_called_once()
    saved_data = mock_save.call_args[0][0]

    # Check data structure
    assert isinstance(saved_data, dict)
    assert "vacuum" in saved_data
    assert isinstance(saved_data["vacuum"], dict)
    assert "roborock" in saved_data["vacuum"]
    assert "ecovacs" in saved_data["vacuum"]

    # Check state values
    assert "segment_cleaning" in saved_data["vacuum"]["roborock"]
    assert "charging_error" in saved_data["vacuum"]["roborock"]
    assert "auto_clean" in saved_data["vacuum"]["ecovacs"]


async def test_domain_isolation(hass: HomeAssistant) -> None:
    """Test that states are isolated by domain.

    States learned for one domain should not appear when querying a
    different domain, even with the same integration name.
    """
    store = LearnedStatesStore(hass)

    # Learn states for different domains with same integration
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")
    await store.async_learn_state("sensor", "roborock", "temperature_reading")

    # Query vacuum domain should only return vacuum states
    vacuum_states = store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in vacuum_states
    assert "temperature_reading" not in vacuum_states

    # Query sensor domain should only return sensor states
    sensor_states = store.get_learned_states("sensor", "roborock")
    assert "temperature_reading" in sensor_states
    assert "segment_cleaning" not in sensor_states


async def test_integration_isolation_within_domain(hass: HomeAssistant) -> None:
    """Test that states are isolated by integration within the same domain.

    States learned for one integration should not appear when querying a
    different integration, even within the same domain.
    """
    store = LearnedStatesStore(hass)

    # Learn states for different integrations under same domain
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")
    await store.async_learn_state("vacuum", "ecovacs", "auto_clean")
    await store.async_learn_state("vacuum", "roborock", "charging_error")

    # Query roborock should only return roborock states
    roborock_states = store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in roborock_states
    assert "charging_error" in roborock_states
    assert "auto_clean" not in roborock_states

    # Query ecovacs should only return ecovacs states
    ecovacs_states = store.get_learned_states("vacuum", "ecovacs")
    assert "auto_clean" in ecovacs_states
    assert "segment_cleaning" not in ecovacs_states
    assert "charging_error" not in ecovacs_states


async def test_async_load_with_none_returns_empty(hass: HomeAssistant) -> None:
    """Test that async_load handles None (no stored data) without crashing.

    Error handling test: When Store.async_load returns None (first run,
    corrupted data, etc.), the learned states store should initialize with
    an empty dict rather than crashing.
    """
    from unittest.mock import AsyncMock, patch

    store = LearnedStatesStore(hass)

    with patch.object(
        store._store, "async_load", new_callable=AsyncMock, return_value=None
    ):
        await store.async_load()

    # Should have empty learned states
    states = store.get_learned_states("vacuum", "roborock")
    assert states == set()


async def test_learn_state_with_empty_strings(hass: HomeAssistant) -> None:
    """Test that learning states with empty string values doesn't crash.

    Edge case: While unlikely in production, empty strings should be
    handled gracefully without raising errors.
    """
    store = LearnedStatesStore(hass)

    # Learn empty string state (shouldn't crash)
    await store.async_learn_state("vacuum", "roborock", "")

    # Should be retrievable
    states = store.get_learned_states("vacuum", "roborock")
    assert "" in states


async def test_learn_state_with_unicode(hass: HomeAssistant) -> None:
    """Test that learning states with unicode characters works correctly.

    States may contain unicode (emoji, international characters), which
    should be stored and retrieved without encoding issues.
    """
    store = LearnedStatesStore(hass)

    # Learn unicode state
    await store.async_learn_state("vacuum", "roborock", "清掃中")  # Chinese
    await store.async_learn_state("vacuum", "ecovacs", "Nettoyage🧹")  # French + emoji

    # Should be retrievable
    roborock_states = store.get_learned_states("vacuum", "roborock")
    assert "清掃中" in roborock_states

    ecovacs_states = store.get_learned_states("vacuum", "ecovacs")
    assert "Nettoyage🧹" in ecovacs_states


async def test_concurrent_learn_state_calls(hass: HomeAssistant) -> None:
    """Test that concurrent async_learn_state calls are handled safely with lock.

    Thread safety test: Multiple concurrent learn operations should not
    cause race conditions. The asyncio.Lock should ensure each operation
    completes atomically.
    """
    import asyncio

    store = LearnedStatesStore(hass)

    # Create multiple concurrent learn tasks for same domain/integration
    tasks = [
        store.async_learn_state("vacuum", "roborock", f"state_{i}") for i in range(10)
    ]

    # Run all learns concurrently
    await asyncio.gather(*tasks)

    # All 10 states should exist
    states = store.get_learned_states("vacuum", "roborock")
    assert len(states) == 10
    for i in range(10):
        assert f"state_{i}" in states


async def test_concurrent_read_write_race_condition(hass: HomeAssistant) -> None:
    """Test that concurrent reads during writes are handled safely.

    This test exercises the thread-safe read pattern in get_learned_states():
    - get_learned_states() uses atomic reference read pattern
    - async_learn_state() modifies self._learned WITH lock protection

    Previously identified race scenario (now fixed):
    1. Reader: checks "if domain not in self._learned" (False, passes)
    2. Writer: acquires lock, modifies self._learned structure
    3. Reader: accesses self._learned[domain] - could see inconsistent state

    Fix: get_learned_states() now captures an atomic reference to self._learned
    before any checks, and uses .get() with defaults to safely handle concurrent
    modifications. This significantly reduces the race condition window.
    """
    import asyncio

    store = LearnedStatesStore(hass)
    errors = []
    inconsistencies = []

    async def concurrent_reader():
        """Continuously read from store."""
        for i in range(200):
            try:
                states = store.get_learned_states("vacuum", "roborock")
                # Track if we see partial writes (should see 0 or N states, not in-between)
                state_count = len(states)
                if state_count > 0 and state_count < i and i > 10:
                    inconsistencies.append(f"Iteration {i}: saw {state_count} states")
                await asyncio.sleep(0)  # Yield to other tasks
            except (KeyError, RuntimeError, AttributeError) as e:
                errors.append(f"KeyError/RuntimeError on iteration {i}: {e}")

    async def concurrent_writer():
        """Continuously write to store."""
        for i in range(200):
            await store.async_learn_state("vacuum", "roborock", f"state_{i}")
            await asyncio.sleep(0)  # Yield to other tasks

    # Run readers and writer concurrently (3 readers, 1 writer)
    await asyncio.gather(
        concurrent_reader(),
        concurrent_reader(),
        concurrent_reader(),
        concurrent_writer(),
    )

    # This test is expected to FAIL without thread-safe read pattern
    # If errors occurred, the race condition was triggered
    if errors:
        # Print first few errors for debugging
        for error in errors[:3]:
            print(f"  Race condition error: {error}")

    # Assert no race condition errors occurred
    assert len(errors) == 0, f"Race condition detected: {len(errors)} errors occurred"


async def test_async_learn_state_save_failure_rollback(hass: HomeAssistant) -> None:
    """Test that async_learn_state rolls back state mutation if save fails.

    This test verifies the fix for defect #4: State mutation before persistence.

    Scenario:
    1. User learns a new state
    2. State is appended to in-memory _learned dict
    3. _async_save() fails (disk full, permissions, I/O error)
    4. State remains in memory but not persisted
    5. HA restarts
    6. async_load() loads from disk -> state is GONE

    Expected behavior after fix:
    - If save fails, the state should be removed from memory (rollback)
    - This maintains consistency between memory and disk
    - Error should be logged and re-raised
    """
    from unittest.mock import AsyncMock, patch

    store = LearnedStatesStore(hass)

    # Learn an initial state successfully
    await store.async_learn_state("vacuum", "roborock", "state_1")

    # Verify it's in memory
    states = store.get_learned_states("vacuum", "roborock")
    assert "state_1" in states

    # Now simulate save failure on next learn
    with (
        patch.object(
            store._store,
            "async_save",
            new_callable=AsyncMock,
            side_effect=OSError("Disk full"),
        ),
        pytest.raises(IOError, match="Disk full"),
    ):
        # Attempt to learn another state - should raise
        await store.async_learn_state("vacuum", "roborock", "state_2")

    # CRITICAL: state_2 should NOT be in memory after save failure
    # (rollback should have removed it)
    states_after_failure = store.get_learned_states("vacuum", "roborock")

    # This assertion will FAIL without the rollback fix
    assert "state_2" not in states_after_failure, (
        "State should be rolled back from memory when save fails"
    )

    # state_1 should still be there (not affected by rollback)
    assert "state_1" in states_after_failure
