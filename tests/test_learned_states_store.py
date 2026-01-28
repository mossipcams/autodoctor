"""Tests for LearnedStatesStore."""

import pytest

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.learned_states_store import LearnedStatesStore


async def test_learned_states_store_initialization(hass: HomeAssistant):
    """Test store can be created."""
    store = LearnedStatesStore(hass)
    assert store is not None


async def test_learn_state_adds_to_store(hass: HomeAssistant):
    """Test learning a state adds it to the store."""
    store = LearnedStatesStore(hass)

    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    states = store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states


async def test_get_learned_states_empty_for_unknown(hass: HomeAssistant):
    """Test getting states for unknown domain/integration returns empty set."""
    store = LearnedStatesStore(hass)

    states = store.get_learned_states("vacuum", "unknown_brand")
    assert states == set()


async def test_learn_state_deduplicates(hass: HomeAssistant):
    """Test learning same state twice doesn't duplicate."""
    store = LearnedStatesStore(hass)

    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    states = store.get_learned_states("vacuum", "roborock")
    assert list(states).count("segment_cleaning") == 1


async def test_learned_states_persist_across_load(hass: HomeAssistant):
    """Test learned states persist after save/load cycle."""
    store1 = LearnedStatesStore(hass)
    await store1.async_learn_state("vacuum", "roborock", "segment_cleaning")

    # Create new store and load
    store2 = LearnedStatesStore(hass)
    await store2.async_load()

    states = store2.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states
