"""Tests for AutomationAnalyzer.

The AutomationAnalyzer is responsible for parsing Home Assistant automation
configurations and extracting all entity references, state expectations, and
service calls. This includes support for:
- 21 trigger types (state, numeric_state, template, time, zone, sun, etc.)
- 10 condition types (state, numeric_state, template, zone, sun, time, etc.)
- Service call extraction from all action types
- Template parsing (is_state, states, expand, area_entities, etc.)
"""

from typing import Any

import pytest

from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.models import StateReference


# ============================================================================
# State Trigger Tests
# ============================================================================


def test_extract_state_trigger_to() -> None:
    """Test extraction of 'to' state from state trigger.

    State triggers with 'to' are the most common automation pattern,
    tracking when an entity changes to a specific state.
    """
    automation: dict[str, Any] = {
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


def test_extract_state_trigger_from_and_to() -> None:
    """Test extraction of 'from' and 'to' states in state trigger.

    State triggers can specify both from and to states to detect specific
    state transitions (e.g., person leaving home).
    """
    automation: dict[str, Any] = {
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


def test_extract_multiple_entity_ids() -> None:
    """Test extraction with multiple entity IDs in single trigger.

    Home Assistant allows specifying multiple entities in a single trigger,
    which creates references for each entity with the same state expectation.
    """
    automation: dict[str, Any] = {
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


def test_extract_state_condition() -> None:
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


def test_extract_is_state_from_template() -> None:
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


def test_extract_multiple_is_state_calls() -> None:
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


def test_extract_states_object_access() -> None:
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

    assert len(refs) == 1
    assert refs[0].entity_id == "binary_sensor.motion"
    assert refs[0].automation_id == "automation.states_access"
    assert refs[0].location == "trigger[0].states_object"


def test_extract_state_attr_from_template() -> None:
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


def test_extract_is_state_attr_from_template() -> None:
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


def test_extract_template_with_escaped_quotes() -> None:
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


def test_extract_multiline_template() -> None:
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


def test_extract_template_strips_jinja_comments() -> None:
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


@pytest.mark.parametrize(
    ("action_type", "entity_id", "expected_state"),
    [
        ("choose", "sensor.mode", "day"),
        ("if", "binary_sensor.presence", "on"),
        ("repeat_while", "sensor.temp", "high"),
        ("repeat_until", "lock.front", "locked"),
        ("wait_template", "binary_sensor.door", "off"),
    ],
    ids=["choose-action", "if-action", "repeat-while", "repeat-until", "wait-template"],
)
def test_extract_from_nested_action_structures(
    action_type: str, entity_id: str, expected_state: str
) -> None:
    """Test extraction from nested action structures (choose, if, repeat, wait).

    The analyzer must recursively walk nested action structures to find
    all entity references in embedded conditions and templates.
    """
    if action_type == "choose":
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
                                    "value_template": f"{{{{ is_state('{entity_id}', '{expected_state}') }}}}",
                                }
                            ],
                            "sequence": [{"service": "light.turn_on"}],
                        }
                    ]
                }
            ],
        }
    elif action_type == "if":
        automation = {
            "id": "if_test",
            "alias": "If Test",
            "trigger": [{"platform": "time", "at": "08:00:00"}],
            "action": [
                {
                    "if": [
                        {
                            "condition": "template",
                            "value_template": f"{{{{ is_state('{entity_id}', '{expected_state}') }}}}",
                        }
                    ],
                    "then": [{"service": "light.turn_on"}],
                }
            ],
        }
    elif action_type == "repeat_while":
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
                                "value_template": f"{{{{ is_state('{entity_id}', '{expected_state}') }}}}",
                            }
                        ],
                        "sequence": [{"service": "climate.set_temperature"}],
                    }
                }
            ],
        }
    elif action_type == "repeat_until":
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
                                "value_template": f"{{{{ is_state('{entity_id}', '{expected_state}') }}}}",
                            }
                        ],
                        "sequence": [{"service": "lock.lock"}],
                    }
                }
            ],
        }
    else:  # wait_template
        automation = {
            "id": "wait_template_test",
            "alias": "Wait Template Test",
            "trigger": [{"platform": "time", "at": "08:00:00"}],
            "action": [
                {
                    "wait_template": f"{{{{ is_state('{entity_id}', '{expected_state}') }}}}",
                }
            ],
        }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Strengthen assertion: verify exact entity found with expected state
    matching_refs = [r for r in refs if r.entity_id == entity_id]
    assert len(matching_refs) == 1
    assert matching_refs[0].expected_state == expected_state


def test_extract_from_parallel_action() -> None:
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

    # Verify both parallel branches were extracted
    assert len(refs) == 2
    entity_ids = {r.entity_id for r in refs}
    assert entity_ids == {"sensor.a", "sensor.b"}
    # Verify both have expected state
    for ref in refs:
        assert ref.expected_state == "ready"


def test_extract_from_nested_choose_default() -> None:
    """Test extraction from choose default sequence."""
    automation = {
        "id": "choose_default_test",
        "alias": "Choose Default Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "state",
                                "entity_id": "sensor.x",
                                "state": "on",
                            }
                        ],
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

    # Should extract from both choose condition and default sequence
    fallback_refs = [r for r in refs if r.entity_id == "sensor.fallback"]
    assert len(fallback_refs) == 1
    assert fallback_refs[0].expected_state == "ready"


def test_extract_implicit_state_condition_in_if() -> None:
    """Test extraction of implicit state condition (HA 2024+ shorthand)."""
    automation = {
        "id": "implicit_condition",
        "alias": "Implicit Condition",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "if": [
                    {
                        "entity_id": "binary_sensor.motion",
                        "state": "on",
                    }
                ],
                "then": [{"action": "light.turn_on"}],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "binary_sensor.motion"
    assert refs[0].expected_state == "on"


def test_extract_explicit_state_condition_in_if() -> None:
    """Test extraction of explicit state condition in if block."""
    automation = {
        "id": "explicit_condition",
        "alias": "Explicit Condition",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "if": [
                    {
                        "condition": "state",
                        "entity_id": "person.matt",
                        "state": "home",
                    }
                ],
                "then": [{"action": "light.turn_on"}],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "person.matt"
    assert refs[0].expected_state == "home"


def test_extract_state_condition_in_choose() -> None:
    """Test extraction of state condition in choose block."""
    automation = {
        "id": "choose_state",
        "alias": "Choose State",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "state",
                                "entity_id": "input_select.mode",
                                "state": "away",
                            }
                        ],
                        "sequence": [{"action": "light.turn_off"}],
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_select.mode"
    assert refs[0].expected_state == "away"


def test_extract_implicit_state_condition_in_repeat_while() -> None:
    """Test extraction of implicit state condition in repeat while."""
    automation = {
        "id": "repeat_implicit",
        "alias": "Repeat Implicit",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "repeat": {
                    "while": [
                        {
                            "entity_id": "binary_sensor.running",
                            "state": "on",
                        }
                    ],
                    "sequence": [{"delay": "00:00:01"}],
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "binary_sensor.running"
    assert refs[0].expected_state == "on"


def test_extract_implicit_state_condition_in_repeat_until() -> None:
    """Test extraction of implicit state condition in repeat until."""
    automation = {
        "id": "repeat_until_implicit",
        "alias": "Repeat Until Implicit",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "repeat": {
                    "until": [
                        {
                            "entity_id": "lock.front_door",
                            "state": "locked",
                        }
                    ],
                    "sequence": [{"action": "lock.lock"}],
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "lock.front_door"
    assert refs[0].expected_state == "locked"


@pytest.mark.parametrize(
    ("null_field", "automation_spec"),
    [
        (
            "state_trigger_entity_id",
            {
                "id": "test_null_entity",
                "alias": "Test Null Entity",
                "triggers": [{"platform": "state", "entity_id": None, "to": "on"}],
                "actions": [],
            },
        ),
        (
            "numeric_state_trigger_entity_id",
            {
                "id": "test_numeric_null",
                "alias": "Test Numeric Null",
                "triggers": [{"platform": "numeric_state", "entity_id": None, "above": 50}],
                "actions": [],
            },
        ),
        (
            "condition_entity_id",
            {
                "id": "test_cond_null",
                "alias": "Test Condition Null",
                "triggers": [{"platform": "time", "at": "12:00:00"}],
                "conditions": [{"condition": "state", "entity_id": None, "state": "on"}],
                "actions": [],
            },
        ),
        (
            "choose_options",
            {
                "id": "test_choose_null",
                "alias": "Test Choose Null",
                "triggers": [{"platform": "time", "at": "12:00:00"}],
                "actions": [{"choose": None}],
            },
        ),
        (
            "if_conditions",
            {
                "id": "test_if_null",
                "alias": "Test If Null",
                "triggers": [{"platform": "time", "at": "12:00:00"}],
                "actions": [{"if": None, "then": [{"service": "light.turn_on"}]}],
            },
        ),
        (
            "parallel_branches",
            {
                "id": "test_parallel_null",
                "alias": "Test Parallel Null",
                "triggers": [{"platform": "time", "at": "12:00:00"}],
                "actions": [{"parallel": None}],
            },
        ),
    ],
    ids=[
        "null-state-trigger-entity",
        "null-numeric-trigger-entity",
        "null-condition-entity",
        "null-choose-options",
        "null-if-conditions",
        "null-parallel-branches",
    ],
)
def test_extract_handles_null_values(null_field: str, automation_spec: dict[str, Any]) -> None:
    """Test that null values in various automation fields don't crash extraction.

    The analyzer must gracefully handle malformed or incomplete automation
    configurations without raising exceptions.
    """
    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation_spec)
    assert isinstance(refs, list)


def test_malformed_trigger_does_not_crash() -> None:
    """Test that malformed trigger dict doesn't crash extraction."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_malformed",
        "alias": "Test Malformed",
        "triggers": [
            "not a dict",  # String instead of dict
            {"platform": "state", "entity_id": "light.valid", "to": "on"},
        ],
        "actions": [],
    }
    refs = analyzer.extract_state_references(automation)
    # Should skip malformed trigger, extract from valid one
    assert len(refs) == 1
    assert refs[0].entity_id == "light.valid"
    assert refs[0].expected_state == "on"


def test_extract_states_function_basic() -> None:
    """Test extraction of states('entity_id') function calls."""
    automation = {
        "id": "states_function_test",
        "alias": "States Function Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temperature') == '25' }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.temperature"
    assert refs[0].expected_state is None  # states() doesn't capture expected state
    assert "states" in refs[0].location


def test_extract_states_function_with_double_quotes() -> None:
    """Test extraction of states() with double quotes."""
    automation = {
        "id": "states_double_quotes",
        "alias": "States Double Quotes",
        "trigger": [
            {
                "platform": "template",
                "value_template": '{{ states("light.bedroom") == "on" }}',
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "light.bedroom"


def test_extract_states_function_with_default_filter() -> None:
    """Test extraction of states() with | default() filter."""
    automation = {
        "id": "states_default_filter",
        "alias": "States Default Filter",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ states('binary_sensor.door') | default('unknown') == 'on' }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "binary_sensor.door"


def test_extract_states_function_multiline() -> None:
    """Test extraction of states() in multiline templates."""
    automation = {
        "id": "states_multiline",
        "alias": "States Multiline",
        "trigger": [
            {
                "platform": "template",
                "value_template": """{{
                    states(
                        'sensor.humidity'
                    ) | float > 60
                }}""",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.humidity"


def test_extract_states_function_deduplicates_with_is_state() -> None:
    """Test that states() doesn't duplicate entities already found by is_state()."""
    automation = {
        "id": "states_dedupe",
        "alias": "States Dedupe",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ is_state('sensor.test', 'on') and states('sensor.test') == 'on' }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should only have one reference for sensor.test, not two
    sensor_refs = [r for r in refs if r.entity_id == "sensor.test"]
    assert len(sensor_refs) == 1
    # The is_state match should take priority (has expected_state)
    assert sensor_refs[0].expected_state == "on"


@pytest.mark.parametrize(
    ("function", "argument", "expected_type"),
    [
        ("expand", "group.all_lights", "group"),
        ("area_entities", "living_room", "area"),
        ("device_entities", "abc123", "device"),
        ("integration_entities", "hue", "integration"),
    ],
    ids=["expand-group", "area-entities", "device-entities", "integration-entities"],
)
def test_extract_helper_functions(
    function: str, argument: str, expected_type: str
) -> None:
    """Test extraction of template helper functions (expand, area_entities, etc).

    These functions reference collections of entities or registry items
    and should be extracted with the appropriate reference_type.
    """
    automation = {
        "id": f"{function}_test",
        "alias": f"{function.title()} Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": f"{{{{ {function}('{argument}') | list | count > 0 }}}}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == argument
    assert refs[0].reference_type == expected_type


def test_normalize_entity_ids_single_string() -> None:
    """Test normalizing single entity_id string to list."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids("light.kitchen")
    assert result == ["light.kitchen"]


def test_normalize_entity_ids_list() -> None:
    """Test normalizing entity_id list."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids(["light.kitchen", "light.bedroom"])
    assert result == ["light.kitchen", "light.bedroom"]


def test_normalize_entity_ids_none() -> None:
    """Test normalizing None entity_id."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids(None)
    assert result == []


@pytest.mark.parametrize(
    ("platform", "expected_entity", "expected_type", "expected_location"),
    [
        ("sun", "sun.sun", "direct", "trigger[0]"),
        ("calendar", "calendar.events", "direct", "trigger[0].entity_id"),
    ],
    ids=["sun-trigger", "calendar-trigger"],
)
def test_extract_simple_entity_trigger(
    platform: str, expected_entity: str, expected_type: str, expected_location: str
) -> None:
    """Test extraction of simple triggers that reference a single entity.

    Sun and calendar triggers follow similar patterns - they create a single
    entity reference with known entity_id and reference_type.
    """
    if platform == "sun":
        automation = {
            "id": "test_sun",
            "alias": "Test Sun Trigger",
            "trigger": {"platform": "sun", "event": "sunset", "offset": "-01:00:00"},
        }
    else:  # calendar
        automation = {
            "id": "test_calendar",
            "alias": "Test Calendar Trigger",
            "trigger": {
                "platform": "calendar",
                "entity_id": "calendar.events",
                "event": "start",
                "offset": "-00:05:00",
            },
        }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == expected_entity
    assert refs[0].reference_type == expected_type
    assert refs[0].location == expected_location


def test_extract_zone_trigger() -> None:
    """Test zone trigger extraction.

    Zone triggers create two references: the tracked entity and the zone.
    """
    automation = {
        "id": "test_zone",
        "alias": "Test Zone Trigger",
        "trigger": {
            "platform": "zone",
            "entity_id": "device_tracker.paulus",
            "zone": "zone.home",
            "event": "enter",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    assert refs[0].entity_id == "device_tracker.paulus"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0].entity_id"
    assert refs[1].entity_id == "zone.home"
    assert refs[1].reference_type == "zone"
    assert refs[1].location == "trigger[0].zone"


@pytest.mark.parametrize(
    ("id_field", "id_value", "expected_type"),
    [
        ("device_id", "abc123def456", "device"),
        ("tag_id", "AABBCCDD", "tag"),
    ],
    ids=["device-trigger", "tag-trigger-single"],
)
def test_extract_registry_trigger(
    id_field: str, id_value: str, expected_type: str
) -> None:
    """Test extraction of registry-based triggers (device, tag).

    These triggers reference items in HA registries rather than entities.
    """
    if id_field == "device_id":
        automation = {
            "id": "test_device",
            "alias": "Test Device Trigger",
            "trigger": {
                "platform": "device",
                "device_id": id_value,
                "domain": "mqtt",
                "type": "button_short_press",
                "subtype": "button_1",
            },
        }
    else:  # tag_id
        automation = {
            "id": "test_tag_no_device",
            "alias": "Test Tag No Device",
            "trigger": {"platform": "tag", "tag_id": id_value},
        }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == id_value
    assert refs[0].reference_type == expected_type
    assert refs[0].location == f"trigger[0].{id_field}"


def test_extract_tag_trigger() -> None:
    """Test tag trigger extraction."""
    automation = {
        "id": "test_tag",
        "alias": "Test Tag Trigger",
        "trigger": {
            "platform": "tag",
            "tag_id": "AABBCCDD",
            "device_id": "scanner_device_123",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    assert refs[0].entity_id == "AABBCCDD"
    assert refs[0].reference_type == "tag"
    assert refs[0].location == "trigger[0].tag_id"
    assert refs[1].entity_id == "scanner_device_123"
    assert refs[1].reference_type == "device"
    assert refs[1].location == "trigger[0].device_id"




def test_extract_geo_location_trigger() -> None:
    """Test geo_location trigger extraction."""
    automation = {
        "id": "test_geo",
        "alias": "Test Geo Location Trigger",
        "trigger": {
            "platform": "geo_location",
            "source": "nsw_rural_fire_service_feed",
            "zone": "zone.home",
            "event": "enter",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "zone.home"
    assert refs[0].reference_type == "zone"
    assert refs[0].location == "trigger[0].zone"


def test_extract_event_trigger_with_template() -> None:
    """Test event trigger with template in event_data."""
    automation = {
        "id": "test_event",
        "alias": "Test Event Trigger",
        "trigger": {
            "platform": "event",
            "event_type": "my_custom_event",
            "event_data": {"entity": "{{ states('input_text.target') }}"},
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.target"
    assert refs[0].location == "trigger[0].event_data.entity.states_function"


def test_extract_mqtt_trigger_with_template() -> None:
    """Test MQTT trigger with template in topic."""
    automation = {
        "id": "test_mqtt",
        "alias": "Test MQTT Trigger",
        "trigger": {
            "platform": "mqtt",
            "topic": "home/{{ states('input_text.room') }}/light",
            "payload": "ON",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.room"
    assert refs[0].location == "trigger[0].topic.states_function"


def test_extract_webhook_trigger() -> None:
    """Test webhook trigger (no entity references expected)."""
    automation = {
        "id": "test_webhook",
        "alias": "Test Webhook Trigger",
        "trigger": {
            "platform": "webhook",
            "webhook_id": "my_webhook_123",
            "allowed_methods": ["POST", "PUT"],
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # No entity references expected for static webhook_id
    assert len(refs) == 0


def test_extract_webhook_trigger_with_template() -> None:
    """Test webhook trigger with template in webhook_id."""
    automation = {
        "id": "test_webhook_template",
        "alias": "Test Webhook Template",
        "trigger": {
            "platform": "webhook",
            "webhook_id": "webhook_{{ states('input_text.name') }}",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.name"


def test_extract_persistent_notification_trigger() -> None:
    """Test persistent_notification trigger with template."""
    automation = {
        "id": "test_notification",
        "alias": "Test Notification Trigger",
        "trigger": {
            "platform": "persistent_notification",
            "notification_id": "alert_{{ states('input_text.alert_name') }}",
            "update_type": "added",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.alert_name"


def test_extract_time_trigger_with_entity() -> None:
    """Test time trigger with entity reference."""
    automation = {
        "id": "test_time",
        "alias": "Test Time Trigger",
        "trigger": {"platform": "time", "at": "input_datetime.wake_up_time"},
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_datetime.wake_up_time"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0].at"


def test_extract_time_trigger_with_time_string() -> None:
    """Test time trigger with time string (no entity reference)."""
    automation = {
        "id": "test_time_string",
        "alias": "Test Time String",
        "trigger": {"platform": "time", "at": "07:30:00"},
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # No entity references for time strings
    assert len(refs) == 0


def test_extract_time_trigger_with_multiple() -> None:
    """Test time trigger with multiple at values."""
    automation = {
        "id": "test_time_multi",
        "alias": "Test Time Multiple",
        "trigger": {
            "platform": "time",
            "at": ["input_datetime.wake_up", "07:30:00", "sensor.sunset_time"],
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    entity_ids = [r.entity_id for r in refs]
    assert "input_datetime.wake_up" in entity_ids
    assert "sensor.sunset_time" in entity_ids


def test_extract_numeric_state_condition() -> None:
    """Test numeric_state condition extraction."""
    automation = {
        "id": "test_numeric_cond",
        "alias": "Test Numeric Condition",
        "condition": {
            "condition": "numeric_state",
            "entity_id": "sensor.temperature",
            "above": 20,
            "below": 30,
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.temperature"
    assert refs[0].expected_attribute is None
    assert refs[0].location == "condition[0]"


def test_extract_numeric_state_condition_with_attribute() -> None:
    """Test numeric_state condition with attribute."""
    automation = {
        "id": "test_numeric_attr",
        "alias": "Test Numeric Attribute",
        "condition": {
            "condition": "numeric_state",
            "entity_id": "climate.living_room",
            "attribute": "temperature",
            "above": 20,
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "temperature"
    assert refs[0].location == "condition[0]"


def test_extract_numeric_state_condition_with_template() -> None:
    """Test numeric_state condition with value_template."""
    automation = {
        "id": "test_numeric_template",
        "alias": "Test Numeric Template",
        "condition": {
            "condition": "numeric_state",
            "entity_id": "sensor.data",
            "value_template": "{{ state.attributes.value | float }}",
            "above": 10,
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract entity_id
    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.data"
    assert refs[0].location == "condition[0]"


def test_extract_zone_condition() -> None:
    """Test zone condition extraction."""
    automation = {
        "id": "test_zone_cond",
        "alias": "Test Zone Condition",
        "condition": {
            "condition": "zone",
            "entity_id": "device_tracker.paulus",
            "zone": "zone.home",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    assert refs[0].entity_id == "device_tracker.paulus"
    assert refs[0].location == "condition[0].entity_id"
    assert refs[1].entity_id == "zone.home"
    assert refs[1].reference_type == "zone"
    assert refs[1].location == "condition[0].zone"


def test_extract_sun_condition() -> None:
    """Test sun condition extraction."""
    automation = {
        "id": "test_sun_cond",
        "alias": "Test Sun Condition",
        "condition": {
            "condition": "sun",
            "after": "sunset",
            "after_offset": "-01:00:00",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sun.sun"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "condition[0]"


def test_extract_time_condition_with_entity() -> None:
    """Test time condition with entity references."""
    automation = {
        "id": "test_time_cond",
        "alias": "Test Time Condition",
        "condition": {
            "condition": "time",
            "after": "input_datetime.wake_up",
            "before": "22:00:00",
            "weekday": ["mon", "tue", "wed"],
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_datetime.wake_up"
    assert refs[0].location == "condition[0].after"


def test_extract_time_condition_no_entities() -> None:
    """Test time condition with time strings only."""
    automation = {
        "id": "test_time_cond_strings",
        "alias": "Test Time Strings",
        "condition": {"condition": "time", "after": "08:00:00", "before": "22:00:00"},
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # No entity references for time strings
    assert len(refs) == 0


def test_extract_device_condition() -> None:
    """Test device condition extraction."""
    automation = {
        "id": "test_device_cond",
        "alias": "Test Device Condition",
        "condition": {
            "condition": "device",
            "device_id": "abc123def456",
            "domain": "light",
            "type": "is_on",
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "abc123def456"
    assert refs[0].reference_type == "device"
    assert refs[0].location == "condition[0].device_id"


def test_extract_numeric_state_trigger_with_attribute() -> None:
    """Test numeric_state trigger now extracts attribute for validation."""
    automation = {
        "id": "test_numeric_trigger_attr",
        "alias": "Test Numeric Trigger Attribute",
        "trigger": {
            "platform": "numeric_state",
            "entity_id": "climate.living_room",
            "attribute": "temperature",
            "above": 20,
        },
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "temperature"
    assert refs[0].location == "trigger[0]"


def test_extract_direct_service_call() -> None:
    """Test extracting a direct service call."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "service": "light.turn_on",
                "target": {"entity_id": "light.living_room"},
                "data": {"brightness": 255},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].service == "light.turn_on"
    assert calls[0].location == "action[0]"
    assert calls[0].is_template is False


def test_extract_templated_service_call() -> None:
    """Test extracting a templated service call."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [{"service": "{{ service_var }}"}],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].is_template is True


def test_extract_service_call_inline_params() -> None:
    """Test that inline parameters (without data: wrapper) are captured in ServiceCall.data."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "service": "light.turn_on",
                "brightness": 255,
                "transition": 2,
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].data == {"brightness": 255, "transition": 2}


def test_extract_service_call_inline_params_merged_with_data() -> None:
    """Test that inline params are merged with explicit data: dict, with data: winning on conflict."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "service": "light.turn_on",
                "brightness": 255,
                "data": {"transition": 2, "brightness": 128},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    # Explicit data: values take precedence over inline params
    assert calls[0].data == {"transition": 2, "brightness": 128}


def test_extract_service_call_entity_id_not_inline_param() -> None:
    """Test that entity_id at action level is not treated as an inline param."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "service": "light.turn_on",
                "entity_id": "light.living_room",
                "brightness": 255,
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].data == {"brightness": 255}


def test_extract_service_call_no_inline_no_data() -> None:
    """Test action with only service + target produces data=None."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "service": "light.turn_off",
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].data is None


def test_extract_service_call_action_key_with_inline_params() -> None:
    """Test using 'action' key (HA 2024.x style) with inline params."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "action": "light.turn_on",
                "brightness": 255,
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].data == {"brightness": 255}


def test_extract_service_calls_from_choose() -> None:
    """Test extracting service calls from choose branches."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "choose": [
                    {"sequence": [{"service": "light.turn_on"}]},
                    {"sequence": [{"service": "light.turn_off"}]},
                ]
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 2
    assert calls[0].service == "light.turn_on"
    assert calls[0].location == "action[0].choose[0].sequence[0]"
    assert calls[1].service == "light.turn_off"
    assert calls[1].location == "action[0].choose[1].sequence[0]"


def test_extract_service_call_data_entity_id() -> None:
    """Test extraction from service call with data.entity_id."""
    automation = {
        "id": "turn_on_light",
        "alias": "Turn On Light",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {"service": "light.turn_on", "data": {"entity_id": "light.kitchen"}}
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract light.kitchen from service call
    service_refs = [r for r in refs if r.entity_id == "light.kitchen"]
    assert len(service_refs) == 1
    assert service_refs[0].location == "action[0].service.entity_id"
    assert service_refs[0].reference_type == "service_call"


def test_extract_service_call_multiple_entities() -> None:
    """Test extraction from service call with multiple entity_ids."""
    automation = {
        "id": "turn_on_lights",
        "alias": "Turn On Lights",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "service": "light.turn_on",
                "data": {"entity_id": ["light.kitchen", "light.bedroom"]},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract both lights
    service_refs = [r for r in refs if "light." in r.entity_id]
    assert len(service_refs) == 2
    entity_ids = {r.entity_id for r in service_refs}
    assert "light.kitchen" in entity_ids
    assert "light.bedroom" in entity_ids


def test_extract_service_call_target_entity_id() -> None:
    """Test extraction from service call with target.entity_id."""
    automation = {
        "id": "turn_on_light",
        "alias": "Turn On Light",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    service_refs = [r for r in refs if r.entity_id == "light.living_room"]
    assert len(service_refs) == 1
    assert service_refs[0].location == "action[0].service.entity_id"
    assert service_refs[0].reference_type == "service_call"


def test_extract_service_call_with_none_merged_data() -> None:
    """Test that service call extraction handles None merged_data gracefully.

    When inline params exist but no explicit data dict, merged_data may be None.
    This test ensures the analyzer doesn't crash on this edge case.
    """
    automation = {
        "id": "turn_on_with_inline",
        "alias": "Turn On With Inline",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "service": "light.turn_on",
                "target": {"entity_id": "light.bedroom"},
                # No data dict, only inline params handled by analyzer
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    # Should not crash
    refs = analyzer.extract_state_references(automation)
    calls = analyzer.extract_service_calls(automation)

    # Verify extraction succeeded
    assert len(refs) == 1
    assert refs[0].entity_id == "light.bedroom"
    assert refs[0].reference_type == "service_call"
    assert len(calls) == 1
    assert calls[0].service == "light.turn_on"


def test_extract_scene_turn_on() -> None:
    """Test extraction from scene.turn_on service."""
    automation = {
        "id": "activate_scene",
        "alias": "Activate Scene",
        "trigger": [{"platform": "time", "at": "20:00:00"}],
        "action": [
            {"service": "scene.turn_on", "target": {"entity_id": "scene.movie_time"}}
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    scene_refs = [r for r in refs if r.entity_id == "scene.movie_time"]
    assert len(scene_refs) == 1
    assert scene_refs[0].reference_type == "scene"


def test_extract_script_turn_on() -> None:
    """Test extraction from script.turn_on service."""
    automation = {
        "id": "run_script",
        "alias": "Run Script",
        "trigger": [{"platform": "time", "at": "22:00:00"}],
        "action": [
            {
                "service": "script.turn_on",
                "target": {"entity_id": "script.bedtime_routine"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    script_refs = [r for r in refs if r.entity_id == "script.bedtime_routine"]
    assert len(script_refs) == 1
    assert script_refs[0].reference_type == "script"


def test_extract_script_shorthand() -> None:
    """Test extraction from shorthand script call."""
    automation = {
        "id": "run_script_shorthand",
        "alias": "Run Script Shorthand",
        "trigger": [{"platform": "time", "at": "22:00:00"}],
        "action": [{"service": "script.bedtime_routine"}],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    script_refs = [r for r in refs if r.entity_id == "script.bedtime_routine"]
    assert len(script_refs) == 1
    assert script_refs[0].reference_type == "script"
    assert script_refs[0].location == "action[0].service"


def test_script_meta_service_not_extracted() -> None:
    """Test that script meta-services are not extracted as entities."""
    automation = {
        "id": "reload_scripts",
        "alias": "Reload Scripts",
        "trigger": [{"platform": "time", "at": "00:00:00"}],
        "action": [
            {"service": "script.reload"},
            {"service": "script.turn_off", "data": {"entity_id": "script.test"}},
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should only extract script.test from turn_off data, not reload
    script_refs = [r for r in refs if "script." in r.entity_id]
    assert len(script_refs) == 1
    assert script_refs[0].entity_id == "script.test"


def test_extract_device_id_function() -> None:
    """Test extraction from device_id() function."""
    automation = {
        "id": "check_device",
        "alias": "Check Device",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ device_id('light.kitchen') == device_id('light.bedroom') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    device_id_refs = [r for r in refs if r.reference_type == "metadata"]
    assert len(device_id_refs) == 2
    entity_ids = {r.entity_id for r in device_id_refs}
    assert "light.kitchen" in entity_ids
    assert "light.bedroom" in entity_ids


def test_extract_area_name_and_id_functions() -> None:
    """Test extraction from area_name() and area_id() functions."""
    automation = {
        "id": "check_area",
        "alias": "Check Area",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ area_name('sensor.temperature') == 'Kitchen' and area_id('light.bedroom') == 'bedroom' }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    area_refs = [r for r in refs if r.reference_type == "metadata"]
    assert len(area_refs) == 2
    entity_ids = {r.entity_id for r in area_refs}
    assert "sensor.temperature" in entity_ids
    assert "light.bedroom" in entity_ids


def test_extract_has_value_function() -> None:
    """Test extraction from has_value() function."""
    automation = {
        "id": "check_value",
        "alias": "Check Value",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ has_value('sensor.temperature') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    has_value_refs = [r for r in refs if r.location.endswith(".has_value")]
    assert len(has_value_refs) == 1
    assert has_value_refs[0].entity_id == "sensor.temperature"
    assert has_value_refs[0].reference_type == "entity"


def test_extract_deduplication_helper_functions() -> None:
    """Test that same entity via different patterns is deduplicated."""
    automation = {
        "id": "dedupe_test",
        "alias": "Dedupe Test",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ is_state('light.kitchen', 'on') and device_id('light.kitchen') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should only have 1 reference to light.kitchen (deduplicated)
    kitchen_refs = [r for r in refs if r.entity_id == "light.kitchen"]
    assert len(kitchen_refs) == 1


def test_extract_full_automation_with_all_patterns() -> None:
    """Test extraction from automation using all new patterns."""
    automation = {
        "id": "comprehensive_test",
        "alias": "Comprehensive Test",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "binary_sensor.motion",
                "to": "on",
            }
        ],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ has_value('sensor.temperature') }}",
            }
        ],
        "action": [
            {"service": "light.turn_on", "target": {"entity_id": "light.kitchen"}},
            {"service": "script.bedtime_routine"},
            {"service": "scene.turn_on", "data": {"entity_id": "scene.movie_time"}},
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Check each expected extraction
    # 1. State trigger
    motion_refs = [r for r in refs if r.entity_id == "binary_sensor.motion"]
    assert len(motion_refs) == 1
    assert "trigger" in motion_refs[0].location
    assert motion_refs[0].expected_state == "on"

    # 2. has_value in condition
    temp_refs = [r for r in refs if r.entity_id == "sensor.temperature"]
    assert len(temp_refs) == 1

    # 3. Service call target
    service_refs = [
        r
        for r in refs
        if r.entity_id == "light.kitchen" and r.reference_type == "service_call"
    ]
    assert len(service_refs) == 1

    # 4. Script shorthand
    script_refs = [
        r
        for r in refs
        if r.entity_id == "script.bedtime_routine" and r.reference_type == "script"
    ]
    assert len(script_refs) == 1

    # 5. Scene
    scene_refs = [
        r
        for r in refs
        if r.entity_id == "scene.movie_time" and r.reference_type == "scene"
    ]
    assert len(scene_refs) == 1


def test_extract_service_calls_from_if_then_else() -> None:
    """Test extracting service calls from if/then/else branches."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "if": [{"condition": "state", "entity_id": "sensor.x", "state": "on"}],
                "then": [{"service": "light.turn_on"}],
                "else": [{"service": "light.turn_off"}],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 2
    services = {c.service for c in calls}
    assert "light.turn_on" in services
    assert "light.turn_off" in services


def test_extract_service_calls_from_repeat_sequence() -> None:
    """Test extracting service calls from repeat sequence."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "repeat": {
                    "count": 3,
                    "sequence": [{"service": "light.toggle"}],
                }
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].service == "light.toggle"


def test_extract_service_calls_from_parallel() -> None:
    """Test extracting service calls from parallel branches."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "parallel": [
                    {"service": "light.turn_on"},
                    {"service": "notify.send_message"},
                ]
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 2
    services = {c.service for c in calls}
    assert "light.turn_on" in services
    assert "notify.send_message" in services


def test_extract_service_calls_from_choose_default() -> None:
    """Test extracting service calls from choose default branch."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "choose": [{"sequence": [{"service": "light.turn_on"}]}],
                "default": [{"service": "light.turn_off"}],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 2
    services = {c.service for c in calls}
    assert "light.turn_on" in services
    assert "light.turn_off" in services


def test_extract_service_calls_deeply_nested() -> None:
    """Test extracting service calls from deeply nested structure."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "choose": [
                    {
                        "sequence": [
                            {
                                "if": [
                                    {
                                        "condition": "state",
                                        "entity_id": "sensor.x",
                                        "state": "on",
                                    }
                                ],
                                "then": [
                                    {
                                        "repeat": {
                                            "count": 2,
                                            "sequence": [{"service": "light.turn_on"}],
                                        }
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].service == "light.turn_on"


def test_extract_service_calls_supports_action_key() -> None:
    """Test extracting service calls using 'action' key (newer HA syntax)."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {"action": "light.turn_on", "target": {"entity_id": "light.bedroom"}},
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].service == "light.turn_on"


def test_extract_service_calls_supports_actions_key() -> None:
    """Test extracting service calls from 'actions' key (alternate format)."""
    automation = {
        "id": "test",
        "alias": "Test",
        "actions": [
            {"service": "light.turn_on"},
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].service == "light.turn_on"


def test_extract_null_repeat_config_does_not_crash() -> None:
    """Test that action with repeat: null does not crash (C4 fix)."""
    automation = {
        "id": "null_repeat",
        "alias": "Null Repeat",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "repeat": None,
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should not crash, should return empty or minimal refs
    assert isinstance(refs, list)


def test_extract_valid_repeat_after_null_guard() -> None:
    """Test that valid repeat config still works after isinstance guard."""
    automation = {
        "id": "valid_repeat",
        "alias": "Valid Repeat",
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

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.temp"
    assert refs[0].expected_state == "high"


def test_extract_multi_key_action_service_and_choose() -> None:
    """Test that action with both service and choose processes all keys (M4 fix)."""
    automation = {
        "id": "multi_key",
        "alias": "Multi Key Action",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "service": "light.turn_on",
                "target": {"entity_id": "light.hallway"},
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "state",
                                "entity_id": "input_boolean.night_mode",
                                "state": "on",
                            }
                        ],
                        "sequence": [
                            {
                                "service": "light.turn_on",
                                "data": {"brightness": 50},
                                "target": {"entity_id": "light.bedroom"},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract service call reference from the top-level service
    hallway_refs = [r for r in refs if r.entity_id == "light.hallway"]
    assert len(hallway_refs) >= 1, "Top-level service entity_id not extracted"

    # Should ALSO extract references from the choose branch
    night_mode_refs = [r for r in refs if r.entity_id == "input_boolean.night_mode"]
    assert len(night_mode_refs) >= 1, "Choose branch condition entity not extracted"

    # And the nested service call
    bedroom_refs = [r for r in refs if r.entity_id == "light.bedroom"]
    assert len(bedroom_refs) >= 1, "Choose branch sequence service entity not extracted"


def test_extract_null_wait_template_does_not_crash() -> None:
    """Test that action with wait_template: null does not crash."""
    automation = {
        "id": "null_wait",
        "alias": "Null Wait Template",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "action": [
            {
                "wait_template": None,
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert isinstance(refs, list)
