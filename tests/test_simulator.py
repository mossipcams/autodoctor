"""Tests for SimulationEngine."""

import pytest

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.simulator import SimulationEngine
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import Verdict


@pytest.fixture
def knowledge_base(hass: HomeAssistant):
    """Create a knowledge base."""
    return StateKnowledgeBase(hass)


@pytest.fixture
def simulator(knowledge_base):
    """Create a simulator."""
    return SimulationEngine(knowledge_base)


async def test_simulator_initialization(simulator):
    """Test simulator can be initialized."""
    assert simulator is not None


async def test_verify_reachable_automation(simulator, hass: HomeAssistant):
    """Test verification of reachable automation."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()

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


async def test_verify_unreachable_contradictory_condition(simulator, hass: HomeAssistant):
    """Test detection of contradictory conditions."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()

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


async def test_verify_missing_trigger_entity(simulator, hass: HomeAssistant):
    """Test detection of missing trigger entity."""
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
