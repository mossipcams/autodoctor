"""Tests for Autodoctor integration initialization."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.autodoctor import async_setup_entry
from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.entity_graph import EntityGraph
from custom_components.autodoctor.suggestion_learner import SuggestionLearner
from custom_components.autodoctor.fix_engine import FixEngine


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.options = {}
    entry.data = {}
    return entry


@pytest.mark.asyncio
async def test_async_setup_entry_initializes_entity_graph_and_suggestion_learner(
    hass: HomeAssistant, mock_config_entry
):
    """Test that async_setup_entry initializes EntityGraph and SuggestionLearner."""
    with patch(
        "custom_components.autodoctor.async_setup_websocket_api",
        new_callable=AsyncMock,
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
    ), patch(
        "custom_components.autodoctor._async_register_card",
        new_callable=AsyncMock,
    ):
        # Run setup
        result = await async_setup_entry(hass, mock_config_entry)

        # Verify setup succeeded
        assert result is True

        # Verify EntityGraph was created and stored
        assert "entity_graph" in hass.data[DOMAIN]
        entity_graph = hass.data[DOMAIN]["entity_graph"]
        assert isinstance(entity_graph, EntityGraph)

        # Verify SuggestionLearner was created and stored
        assert "suggestion_learner" in hass.data[DOMAIN]
        suggestion_learner = hass.data[DOMAIN]["suggestion_learner"]
        assert isinstance(suggestion_learner, SuggestionLearner)

        # Verify FixEngine was created with EntityGraph and SuggestionLearner
        assert "fix_engine" in hass.data[DOMAIN]
        fix_engine = hass.data[DOMAIN]["fix_engine"]
        assert isinstance(fix_engine, FixEngine)
        assert fix_engine._entity_graph is entity_graph
        assert fix_engine._suggestion_learner is suggestion_learner
