"""Tests for WebSocket API learning on suppression."""

import inspect
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.learned_states_store import LearnedStatesStore
from custom_components.autodoctor.suppression_store import SuppressionStore
from custom_components.autodoctor.websocket_api import websocket_suppress


async def _invoke_command(handler, hass, connection, msg) -> None:
    """Invoke websocket command coroutine underneath decorator wrappers."""
    command = handler
    while hasattr(command, "__wrapped__") and not inspect.iscoroutinefunction(command):
        command = command.__wrapped__
    if not inspect.iscoroutinefunction(command):
        raise AssertionError("Expected wrapped websocket handler coroutine")
    await command(hass, connection, msg)


async def test_suppress_learns_state_for_invalid_state_issue(
    hass: HomeAssistant,
) -> None:
    """Test that suppressing invalid_state issues learns the state.

    When a user suppresses an invalid_state issue, the state should be
    automatically learned for that entity's platform. This prevents future
    warnings about the same valid state.
    """
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
        await _invoke_command(websocket_suppress, hass, connection, msg)

    # Verify state was learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states

    # Verify suppression was added
    assert suppression_store.is_suppressed(
        "automation.test:vacuum.roborock_s7:invalid_state"
    )


async def test_suppress_does_not_learn_for_non_state_issues(
    hass: HomeAssistant,
) -> None:
    """Test that non-state issues don't trigger automatic learning.

    Only invalid_state issues should trigger state learning. Other issue types
    like entity_not_found should be suppressed without modifying learned states.
    """
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

    await _invoke_command(websocket_suppress, hass, connection, msg)

    # Verify no states were learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert len(states) == 0


async def test_suppress_does_not_learn_without_state_param(hass: HomeAssistant) -> None:
    """Test that invalid_state issues require state parameter for learning.

    If the state parameter is missing from an invalid_state suppression,
    learning should not occur (since we don't know what state to learn).
    The suppression itself should still be recorded.
    """
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

    await _invoke_command(websocket_suppress, hass, connection, msg)

    # Verify no states were learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert len(states) == 0

    # But suppression was still added
    assert suppression_store.is_suppressed(
        "automation.test:vacuum.roborock_s7:invalid_state"
    )
