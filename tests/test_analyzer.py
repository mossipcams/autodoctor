"""Tests for AutomationAnalyzer."""

from custom_components.autodoctor.analyzer import AutomationAnalyzer


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

    assert any(r.entity_id == "sensor.fallback" for r in refs)


def test_extract_implicit_state_condition_in_if():
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

    assert any(
        r.entity_id == "binary_sensor.motion" and r.expected_state == "on" for r in refs
    )


def test_extract_explicit_state_condition_in_if():
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

    assert any(
        r.entity_id == "person.matt" and r.expected_state == "home" for r in refs
    )


def test_extract_state_condition_in_choose():
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

    assert any(
        r.entity_id == "input_select.mode" and r.expected_state == "away" for r in refs
    )


def test_extract_implicit_state_condition_in_repeat_while():
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

    assert any(
        r.entity_id == "binary_sensor.running" and r.expected_state == "on"
        for r in refs
    )


def test_extract_implicit_state_condition_in_repeat_until():
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

    assert any(
        r.entity_id == "lock.front_door" and r.expected_state == "locked" for r in refs
    )


def test_extract_handles_null_entity_id_in_trigger():
    """Test that null entity_id in trigger doesn't crash extraction."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_null_entity",
        "alias": "Test Null Entity",
        "triggers": [
            {
                "platform": "state",
                "entity_id": None,  # Explicitly null
                "to": "on",
            }
        ],
        "actions": [],
    }
    # Should not raise, should return empty list
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_entity_id_in_numeric_state_trigger():
    """Test null entity_id in numeric_state trigger."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_numeric_null",
        "alias": "Test Numeric Null",
        "triggers": [
            {
                "platform": "numeric_state",
                "entity_id": None,
                "above": 50,
            }
        ],
        "actions": [],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_entity_id_in_condition():
    """Test null entity_id in condition."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_cond_null",
        "alias": "Test Condition Null",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "state",
                "entity_id": None,
                "state": "on",
            }
        ],
        "actions": [],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_choose_options():
    """Test null choose options don't crash."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_choose_null",
        "alias": "Test Choose Null",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [
            {
                "choose": None,  # Explicitly null
            }
        ],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_if_conditions():
    """Test null if conditions don't crash."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_if_null",
        "alias": "Test If Null",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [
            {
                "if": None,  # Explicitly null
                "then": [{"service": "light.turn_on"}],
            }
        ],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_parallel_branches():
    """Test null parallel branches don't crash."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_parallel_null",
        "alias": "Test Parallel Null",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [
            {
                "parallel": None,  # Explicitly null
            }
        ],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_malformed_trigger_does_not_crash():
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
    assert len(refs) >= 1
    assert any(r.entity_id == "light.valid" for r in refs)


def test_extract_states_function_basic():
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


def test_extract_states_function_with_double_quotes():
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


def test_extract_states_function_with_default_filter():
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


def test_extract_states_function_multiline():
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


def test_extract_states_function_deduplicates_with_is_state():
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


def test_extract_expand_group():
    """Test extraction of expand('group.xxx') calls."""
    automation = {
        "id": "expand_group_test",
        "alias": "Expand Group Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ expand('group.all_lights') | selectattr('state', 'eq', 'on') | list | count > 0 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "group.all_lights"


def test_expand_group_has_reference_type():
    """Test that expand() references have reference_type='group'."""
    automation = {
        "id": "expand_ref_type",
        "alias": "Expand Ref Type",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ expand('group.lights') | list | count > 0 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].reference_type == "group"


def test_extract_area_entities():
    """Test extraction of area_entities() calls."""
    automation = {
        "id": "area_entities_test",
        "alias": "Area Entities Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ area_entities('living_room') | list | count > 0 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "living_room"
    assert refs[0].reference_type == "area"


def test_extract_device_entities():
    """Test extraction of device_entities() calls."""
    automation = {
        "id": "device_entities_test",
        "alias": "Device Entities Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ device_entities('abc123') | list | count > 0 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "abc123"
    assert refs[0].reference_type == "device"


def test_extract_integration_entities():
    """Test extraction of integration_entities() calls."""
    automation = {
        "id": "integration_entities_test",
        "alias": "Integration Entities Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ integration_entities('hue') | list | count > 0 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "hue"
    assert refs[0].reference_type == "integration"


def test_normalize_entity_ids_single_string():
    """Test normalizing single entity_id string to list."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids("light.kitchen")
    assert result == ["light.kitchen"]


def test_normalize_entity_ids_list():
    """Test normalizing entity_id list."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids(["light.kitchen", "light.bedroom"])
    assert result == ["light.kitchen", "light.bedroom"]


def test_normalize_entity_ids_none():
    """Test normalizing None entity_id."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids(None)
    assert result == []


def test_extract_zone_trigger():
    """Test zone trigger extraction."""
    automation = {
        "id": "test_zone",
        "alias": "Test Zone Trigger",
        "trigger": {
            "platform": "zone",
            "entity_id": "device_tracker.paulus",
            "zone": "zone.home",
            "event": "enter"
        }
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


def test_extract_sun_trigger():
    """Test sun trigger extraction."""
    automation = {
        "id": "test_sun",
        "alias": "Test Sun Trigger",
        "trigger": {
            "platform": "sun",
            "event": "sunset",
            "offset": "-01:00:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sun.sun"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0]"


def test_extract_calendar_trigger():
    """Test calendar trigger extraction."""
    automation = {
        "id": "test_calendar",
        "alias": "Test Calendar Trigger",
        "trigger": {
            "platform": "calendar",
            "entity_id": "calendar.events",
            "event": "start",
            "offset": "-00:05:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "calendar.events"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0].entity_id"


def test_extract_direct_service_call():
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


def test_extract_templated_service_call():
    """Test extracting a templated service call."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {"service": "{{ service_var }}"}
        ],
    }

    analyzer = AutomationAnalyzer()
    calls = analyzer.extract_service_calls(automation)

    assert len(calls) == 1
    assert calls[0].is_template is True


def test_extract_service_calls_from_choose():
    """Test extracting service calls from choose branches."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "choose": [
                    {
                        "sequence": [
                            {"service": "light.turn_on"}
                        ]
                    },
                    {
                        "sequence": [
                            {"service": "light.turn_off"}
                        ]
                    }
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
