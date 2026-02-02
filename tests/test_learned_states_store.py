"""Tests for LearnedStatesStore."""

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
