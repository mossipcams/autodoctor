"""Tests for WebSocket API learning on suppression."""

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.learned_states_store import LearnedStatesStore
from custom_components.autodoctor.suppression_store import SuppressionStore
from custom_components.autodoctor.websocket_api import websocket_suppress


async def test_suppress_learns_state_for_invalid_state_issue(hass: HomeAssistant):
    """Test that suppressing an invalid state issue learns the state."""
    # Set up stores
    learned_store = LearnedStatesStore(hass)
    suppression_store = SuppressionStore(hass)

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": learned_store,
    }

    # Mock entity registry
    mock_entry = MagicMock()
    mock_entry.platform = "roborock"
    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    # Mock connection
    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {
        "id": 1,
        "type": "autodoctor/suppress",
        "automation_id": "automation.test",
        "entity_id": "vacuum.roborock_s7",
        "issue_type": "invalid_state",
        "state": "segment_cleaning",
    }

    with patch(
        "custom_components.autodoctor.websocket_api.er.async_get",
        return_value=mock_registry,
    ):
        await websocket_suppress.__wrapped__(hass, connection, msg)

    # Verify state was learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states

    # Verify suppression was added
    assert suppression_store.is_suppressed(
        "automation.test:vacuum.roborock_s7:invalid_state"
    )


async def test_suppress_does_not_learn_for_non_state_issues(hass: HomeAssistant):
    """Test that non-state issues don't trigger learning."""
    learned_store = LearnedStatesStore(hass)
    suppression_store = SuppressionStore(hass)

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": learned_store,
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {
        "id": 1,
        "type": "autodoctor/suppress",
        "automation_id": "automation.test",
        "entity_id": "vacuum.unknown",
        "issue_type": "entity_not_found",  # Not a state issue
    }

    await websocket_suppress.__wrapped__(hass, connection, msg)

    # Verify no states were learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert len(states) == 0


async def test_suppress_does_not_learn_without_state_param(hass: HomeAssistant):
    """Test that invalid_state without state param doesn't trigger learning."""
    learned_store = LearnedStatesStore(hass)
    suppression_store = SuppressionStore(hass)

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": learned_store,
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {
        "id": 1,
        "type": "autodoctor/suppress",
        "automation_id": "automation.test",
        "entity_id": "vacuum.roborock_s7",
        "issue_type": "invalid_state",
        # No state param provided
    }

    await websocket_suppress.__wrapped__(hass, connection, msg)

    # Verify no states were learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert len(states) == 0

    # But suppression was still added
    assert suppression_store.is_suppressed(
        "automation.test:vacuum.roborock_s7:invalid_state"
    )
