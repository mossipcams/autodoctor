"""Tests for SimulationEngine."""

import pytest
from unittest.mock import MagicMock

from custom_components.automation_mutation_tester.simulator import SimulationEngine
from custom_components.automation_mutation_tester.knowledge_base import StateKnowledgeBase
from custom_components.automation_mutation_tester.models import Verdict


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def knowledge_base(mock_hass):
    """Create a knowledge base."""
    return StateKnowledgeBase(mock_hass)


@pytest.fixture
def simulator(knowledge_base):
    """Create a simulator."""
    return SimulationEngine(knowledge_base)


def test_simulator_initialization(simulator):
    """Test simulator can be initialized."""
    assert simulator is not None


def test_verify_reachable_automation(simulator, mock_hass):
    """Test verification of reachable automation."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.state = "home"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    automation = {
        "id": "welcome_home",
        "alias": "Welcome Home",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [],
        "action": [
            {"service": "light.turn_on", "target": {"entity_id": "light.porch"}}
        ],
    }

    report = simulator.verify_outcomes(automation)

    assert report.verdict == Verdict.ALL_REACHABLE
    assert report.triggers_valid is True
    assert len(report.outcomes) > 0


def test_verify_unreachable_contradictory_condition(simulator, mock_hass):
    """Test detection of contradictory conditions."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.state = "home"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    automation = {
        "id": "contradiction",
        "alias": "Contradiction",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {"condition": "state", "entity_id": "person.matt", "state": "not_home"}
        ],
        "action": [{"service": "light.turn_on"}],
    }

    report = simulator.verify_outcomes(automation)

    assert report.verdict == Verdict.UNREACHABLE
    assert len(report.unreachable_paths) > 0


def test_verify_missing_trigger_entity(simulator, mock_hass):
    """Test detection of missing trigger entity."""
    mock_hass.states.get = MagicMock(return_value=None)

    automation = {
        "id": "missing",
        "alias": "Missing",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.nonexistent",
                "to": "home",
            }
        ],
        "action": [],
    }

    report = simulator.verify_outcomes(automation)

    assert report.triggers_valid is False
