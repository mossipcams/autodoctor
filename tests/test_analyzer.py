"""Tests for AutomationAnalyzer."""

import pytest
from unittest.mock import MagicMock

from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.models import IssueType, StateReference


def test_extract_state_trigger_to():
    """Test extraction of 'to' state from state trigger."""
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
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].automation_id == "automation.welcome_home"
    assert refs[0].entity_id == "person.matt"
    assert refs[0].expected_state == "home"
    assert refs[0].location == "trigger[0].to"


def test_extract_state_trigger_from_and_to():
    """Test extraction of 'from' and 'to' states."""
    automation = {
        "id": "left_home",
        "alias": "Left Home",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "from": "home",
                "to": "not_home",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    from_ref = next(r for r in refs if "from" in r.location)
    to_ref = next(r for r in refs if ".to" in r.location)

    assert from_ref.expected_state == "home"
    assert to_ref.expected_state == "not_home"


def test_extract_multiple_entity_ids():
    """Test extraction with multiple entity IDs in trigger."""
    automation = {
        "id": "motion_detected",
        "alias": "Motion Detected",
        "trigger": [
            {
                "platform": "state",
                "entity_id": ["binary_sensor.motion_1", "binary_sensor.motion_2"],
                "to": "on",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    entity_ids = {r.entity_id for r in refs}
    assert "binary_sensor.motion_1" in entity_ids
    assert "binary_sensor.motion_2" in entity_ids


def test_extract_state_condition():
    """Test extraction from state condition."""
    automation = {
        "id": "check_alarm",
        "alias": "Check Alarm",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "state",
                "entity_id": "alarm_control_panel.home",
                "state": "armed_away",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "alarm_control_panel.home"
    assert refs[0].expected_state == "armed_away"
    assert refs[0].location == "condition[0].state"


def test_extract_is_state_from_template():
    """Test extraction of is_state() calls from templates."""
    automation = {
        "id": "template_test",
        "alias": "Template Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ is_state('binary_sensor.motion', 'on') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "binary_sensor.motion"
    assert refs[0].expected_state == "on"


def test_extract_multiple_is_state_calls():
    """Test extraction of multiple is_state() calls."""
    automation = {
        "id": "multi_template",
        "alias": "Multi Template",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ is_state('person.matt', 'home') and is_state('sun.sun', 'below_horizon') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    entities = {r.entity_id for r in refs}
    assert "person.matt" in entities
    assert "sun.sun" in entities


def test_extract_states_object_access():
    """Test extraction of states.domain.entity references."""
    automation = {
        "id": "states_access",
        "alias": "States Access",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ states.binary_sensor.motion.state == 'on' }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) >= 1
    assert any(r.entity_id == "binary_sensor.motion" for r in refs)


def test_extract_state_attr_from_template():
    """Test extraction of state_attr() calls."""
    automation = {
        "id": "attr_test",
        "alias": "Attr Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ state_attr('climate.living_room', 'current_temperature') > 25 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "current_temperature"


def test_check_trigger_condition_compatibility_detects_impossible():
    """Test detection of impossible trigger/condition combinations."""
    analyzer = AutomationAnalyzer()

    automation = {
        "id": "test",
        "alias": "Test Automation",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "person.matt",
                "state": "not_home",
            }
        ],
    }

    issues = analyzer.check_trigger_condition_compatibility(automation)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.IMPOSSIBLE_CONDITION
    assert "home" in issues[0].message
    assert "not_home" in issues[0].message


def test_check_trigger_condition_compatibility_allows_matching():
    """Test that matching trigger/condition passes."""
    analyzer = AutomationAnalyzer()

    automation = {
        "id": "test",
        "alias": "Test Automation",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "person.matt",
                "state": "home",
            }
        ],
    }

    issues = analyzer.check_trigger_condition_compatibility(automation)
    assert len(issues) == 0


def test_check_trigger_condition_compatibility_allows_list_match():
    """Test that condition with list including trigger state passes."""
    analyzer = AutomationAnalyzer()

    automation = {
        "id": "test",
        "alias": "Test Automation",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "person.matt",
                "state": ["home", "away"],
            }
        ],
    }

    issues = analyzer.check_trigger_condition_compatibility(automation)
    assert len(issues) == 0


def test_extract_is_state_attr_from_template():
    """Test extraction of is_state_attr() calls from templates."""
    automation = {
        "id": "state_attr_test",
        "alias": "State Attr Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ is_state_attr('climate.living_room', 'hvac_mode', 'heat') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "hvac_mode"


def test_extract_template_with_escaped_quotes():
    """Test extraction handles escaped quotes in templates."""
    automation = {
        "id": "escaped_quotes_test",
        "alias": "Escaped Quotes Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": r"{{ is_state('sensor.name_with_quote', 'value\'s_here') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.name_with_quote"


def test_extract_multiline_template():
    """Test extraction handles multiline templates."""
    automation = {
        "id": "multiline_test",
        "alias": "Multiline Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": """{{
                    is_state('sensor.test',
                             'on')
                }}""",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.test"
    assert refs[0].expected_state == "on"


def test_extract_template_strips_jinja_comments():
    """Test that Jinja2 comments are stripped before parsing."""
    automation = {
        "id": "comment_test",
        "alias": "Comment Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": """{# This is a comment #}{{ is_state('sensor.test', 'on') }}{# Another comment #}""",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.test"


def test_extract_from_choose_action():
    """Test extraction from choose action conditions."""
    automation = {
        "id": "choose_test",
        "alias": "Choose Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "template",
                                "value_template": "{{ is_state('sensor.mode', 'day') }}",
                            }
                        ],
                        "sequence": [{"service": "light.turn_on"}],
                    }
                ]
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "sensor.mode" for r in refs)


def test_extract_from_if_action():
    """Test extraction from if action conditions."""
    automation = {
        "id": "if_test",
        "alias": "If Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "if": [
                    {
                        "condition": "template",
                        "value_template": "{{ is_state('binary_sensor.presence', 'on') }}",
                    }
                ],
                "then": [{"service": "light.turn_on"}],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "binary_sensor.presence" for r in refs)


def test_extract_from_repeat_while_action():
    """Test extraction from repeat while condition."""
    automation = {
        "id": "repeat_while_test",
        "alias": "Repeat While Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "repeat": {
                    "while": [
                        {
                            "condition": "template",
                            "value_template": "{{ is_state('sensor.temp', 'high') }}",
                        }
                    ],
                    "sequence": [{"service": "climate.set_temperature"}],
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "sensor.temp" for r in refs)


def test_extract_from_repeat_until_action():
    """Test extraction from repeat until condition."""
    automation = {
        "id": "repeat_until_test",
        "alias": "Repeat Until Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "repeat": {
                    "until": [
                        {
                            "condition": "template",
                            "value_template": "{{ is_state('lock.front', 'locked') }}",
                        }
                    ],
                    "sequence": [{"service": "lock.lock"}],
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "lock.front" for r in refs)


def test_extract_from_wait_template_action():
    """Test extraction from wait_template action."""
    automation = {
        "id": "wait_template_test",
        "alias": "Wait Template Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "wait_template": "{{ is_state('binary_sensor.door', 'off') }}",
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "binary_sensor.door" for r in refs)


def test_extract_from_parallel_action():
    """Test extraction from parallel action branches."""
    automation = {
        "id": "parallel_test",
        "alias": "Parallel Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "parallel": [
                    [
                        {
                            "wait_template": "{{ is_state('sensor.a', 'ready') }}",
                        }
                    ],
                    [
                        {
                            "wait_template": "{{ is_state('sensor.b', 'ready') }}",
                        }
                    ],
                ]
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "sensor.a" for r in refs)
    assert any(r.entity_id == "sensor.b" for r in refs)


def test_extract_from_nested_choose_default():
    """Test extraction from choose default sequence."""
    automation = {
        "id": "choose_default_test",
        "alias": "Choose Default Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [{"condition": "state", "entity_id": "sensor.x", "state": "on"}],
                        "sequence": [],
                    }
                ],
                "default": [
                    {
                        "wait_template": "{{ is_state('sensor.fallback', 'ready') }}",
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert any(r.entity_id == "sensor.fallback" for r in refs)


def test_extract_service_calls_turn_on():
    """Test extraction of turn_on service call."""
    automation = {
        "id": "motion_lights",
        "alias": "Motion Lights",
        "trigger": [],
        "action": [
            {
                "service": "light.turn_on",
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].automation_id == "automation.motion_lights"
    assert actions[0].entity_id == "light.living_room"
    assert actions[0].action == "turn_on"


def test_extract_service_calls_turn_off():
    """Test extraction of turn_off service call."""
    automation = {
        "id": "away_mode",
        "alias": "Away Mode",
        "trigger": [],
        "action": [
            {
                "service": "light.turn_off",
                "entity_id": "light.living_room",
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].action == "turn_off"


def test_extract_service_calls_toggle():
    """Test extraction of toggle service call."""
    automation = {
        "id": "toggle_lights",
        "alias": "Toggle Lights",
        "trigger": [],
        "action": [
            {
                "service": "light.toggle",
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].action == "toggle"


def test_extract_service_calls_nested_choose():
    """Test extraction from nested choose blocks."""
    automation = {
        "id": "complex",
        "alias": "Complex",
        "trigger": [],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [],
                        "sequence": [
                            {
                                "service": "light.turn_on",
                                "target": {"entity_id": "light.bedroom"},
                            }
                        ],
                    }
                ],
                "default": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.bedroom"},
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 2
    action_types = {a.action for a in actions}
    assert action_types == {"turn_on", "turn_off"}


def test_extract_service_calls_multiple_entities():
    """Test extraction with multiple entity targets."""
    automation = {
        "id": "all_off",
        "alias": "All Off",
        "trigger": [],
        "action": [
            {
                "service": "light.turn_off",
                "target": {
                    "entity_id": ["light.living_room", "light.kitchen"],
                },
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 2
    entity_ids = {a.entity_id for a in actions}
    assert entity_ids == {"light.living_room", "light.kitchen"}
