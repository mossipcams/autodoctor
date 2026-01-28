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


async def test_extract_wait_template_action(simulator, hass: HomeAssistant):
    """Test extraction of wait_template action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "wait_test",
        "alias": "Wait Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "wait_template": "{{ is_state('sensor.door', 'closed') }}",
                "timeout": "00:05:00",
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("wait_template" in o and "timeout" in o for o in report.outcomes)


async def test_extract_wait_for_trigger_action(simulator, hass: HomeAssistant):
    """Test extraction of wait_for_trigger action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "wait_trigger_test",
        "alias": "Wait Trigger Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "wait_for_trigger": [
                    {"platform": "state", "entity_id": "sensor.door", "to": "open"},
                    {"platform": "state", "entity_id": "sensor.window", "to": "open"},
                ]
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("wait_for_trigger: 2 trigger(s)" in o for o in report.outcomes)


async def test_extract_repeat_count_action(simulator, hass: HomeAssistant):
    """Test extraction of repeat with count."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "repeat_count_test",
        "alias": "Repeat Count Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "repeat": {
                    "count": 5,
                    "sequence": [{"service": "light.toggle"}],
                }
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("repeat: 5 times" in o for o in report.outcomes)
    assert any("light.toggle" in o for o in report.outcomes)


async def test_extract_repeat_while_action(simulator, hass: HomeAssistant):
    """Test extraction of repeat with while condition."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "repeat_while_test",
        "alias": "Repeat While Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "repeat": {
                    "while": [{"condition": "state", "entity_id": "sensor.test", "state": "on"}],
                    "sequence": [{"service": "light.turn_on"}],
                }
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("repeat: while condition" in o for o in report.outcomes)


async def test_extract_repeat_until_action(simulator, hass: HomeAssistant):
    """Test extraction of repeat with until condition."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "repeat_until_test",
        "alias": "Repeat Until Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "repeat": {
                    "until": [{"condition": "state", "entity_id": "sensor.test", "state": "off"}],
                    "sequence": [{"service": "light.turn_off"}],
                }
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("repeat: until condition" in o for o in report.outcomes)


async def test_extract_repeat_for_each_action(simulator, hass: HomeAssistant):
    """Test extraction of repeat with for_each."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "repeat_for_each_test",
        "alias": "Repeat For Each Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "repeat": {
                    "for_each": ["light.one", "light.two", "light.three"],
                    "sequence": [{"service": "light.turn_on"}],
                }
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("repeat: for_each" in o for o in report.outcomes)


async def test_extract_parallel_action(simulator, hass: HomeAssistant):
    """Test extraction of parallel action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "parallel_test",
        "alias": "Parallel Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "parallel": [
                    [{"service": "light.turn_on"}],
                    [{"service": "notify.mobile"}],
                ]
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("parallel: 2 branch(es)" in o for o in report.outcomes)
    assert any("light.turn_on" in o for o in report.outcomes)
    assert any("notify.mobile" in o for o in report.outcomes)


async def test_extract_delay_action(simulator, hass: HomeAssistant):
    """Test extraction of delay action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "delay_test",
        "alias": "Delay Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [{"delay": "00:00:30"}],
    }

    report = simulator.verify_outcomes(automation)
    assert any("delay: 00:00:30" in o for o in report.outcomes)


async def test_extract_delay_dict_action(simulator, hass: HomeAssistant):
    """Test extraction of delay action with dict format."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "delay_dict_test",
        "alias": "Delay Dict Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [{"delay": {"minutes": 5, "seconds": 30}}],
    }

    report = simulator.verify_outcomes(automation)
    assert any("delay:" in o and "minutes" in o for o in report.outcomes)


async def test_extract_stop_action(simulator, hass: HomeAssistant):
    """Test extraction of stop action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "stop_test",
        "alias": "Stop Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [{"stop": "User requested stop"}],
    }

    report = simulator.verify_outcomes(automation)
    assert any("stop: User requested stop" in o for o in report.outcomes)


async def test_extract_event_action(simulator, hass: HomeAssistant):
    """Test extraction of event action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "event_test",
        "alias": "Event Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [{"event": "my_custom_event"}],
    }

    report = simulator.verify_outcomes(automation)
    assert any("event: my_custom_event" in o for o in report.outcomes)


async def test_extract_variables_action(simulator, hass: HomeAssistant):
    """Test extraction of variables action."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "variables_test",
        "alias": "Variables Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [{"variables": {"my_var": 123, "another_var": "test"}}],
    }

    report = simulator.verify_outcomes(automation)
    assert any("variables:" in o and "my_var" in o for o in report.outcomes)


async def test_extract_choose_with_nested_actions(simulator, hass: HomeAssistant):
    """Test extraction of choose with nested actions."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "choose_nested_test",
        "alias": "Choose Nested Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [{"condition": "state", "entity_id": "sensor.test", "state": "on"}],
                        "sequence": [{"service": "light.turn_on"}],
                    },
                    {
                        "conditions": [{"condition": "state", "entity_id": "sensor.test", "state": "off"}],
                        "sequence": [{"service": "light.turn_off"}],
                    },
                ],
                "default": [{"service": "notify.mobile"}],
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("choose: 2 option(s)" in o for o in report.outcomes)
    assert any("option 1:" in o and "light.turn_on" in o for o in report.outcomes)
    assert any("option 2:" in o and "light.turn_off" in o for o in report.outcomes)
    assert any("default:" in o and "notify.mobile" in o for o in report.outcomes)


async def test_extract_if_with_nested_actions(simulator, hass: HomeAssistant):
    """Test extraction of if with nested then/else actions."""
    hass.states.async_set("sensor.test", "on")
    await hass.async_block_till_done()

    automation = {
        "id": "if_nested_test",
        "alias": "If Nested Test",
        "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
        "action": [
            {
                "if": [{"condition": "state", "entity_id": "sensor.test", "state": "on"}],
                "then": [{"service": "light.turn_on"}],
                "else": [{"service": "light.turn_off"}],
            }
        ],
    }

    report = simulator.verify_outcomes(automation)
    assert any("if: conditional path" in o for o in report.outcomes)
    assert any("then:" in o and "light.turn_on" in o for o in report.outcomes)
    assert any("else:" in o and "light.turn_off" in o for o in report.outcomes)
