"""Tests for ServiceCallValidator."""

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.service_validator import ServiceCallValidator


async def test_service_validator_initialization(hass: HomeAssistant):
    """Test validator can be created."""
    validator = ServiceCallValidator(hass)
    assert validator is not None


async def test_validate_service_not_found(hass: HomeAssistant):
    """Test validation for non-existent service."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="nonexistent.service",
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == ""
    assert "nonexistent.service" in issues[0].message
    assert issues[0].suggestion is None


async def test_validate_service_exists_no_issues(hass: HomeAssistant):
    """Test validation passes for existing service."""
    from custom_components.autodoctor.models import ServiceCall

    # Register a test service
    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 0


async def test_validate_skips_templated_service(hass: HomeAssistant):
    """Test validation skips templated service names."""
    from custom_components.autodoctor.models import ServiceCall

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="{{ service_var }}",
        location="action[0]",
        is_template=True,
    )

    issues = validator.validate_service_calls([call])

    # Should skip validation for templates
    assert len(issues) == 0


async def test_validate_missing_required_param(hass: HomeAssistant):
    """Test validation for missing required parameter."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    # Register a test service
    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)

    # Mock service descriptions to include a required field
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "brightness": {
                        "required": True,
                        "selector": {"number": {"min": 0, "max": 255}},
                    },
                    "color": {
                        "required": False,
                        "selector": {"text": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"color": "red"},  # Missing required 'brightness'
    )

    issues = validator.validate_service_calls([call])

    missing_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
    ]
    assert len(missing_issues) == 1
    assert missing_issues[0].severity == Severity.ERROR
    assert missing_issues[0].entity_id == ""
    assert "brightness" in missing_issues[0].message
    assert missing_issues[0].suggestion is None


async def test_validate_missing_required_param_in_target(hass: HomeAssistant):
    """Test that required param in target is not flagged as missing."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "entity_id": {
                        "required": True,
                        "selector": {"entity": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={},
        target={"entity_id": "light.kitchen"},  # Required param in target
    )

    issues = validator.validate_service_calls([call])

    missing_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
    ]
    assert len(missing_issues) == 0


async def test_validate_skips_required_check_when_templated(hass: HomeAssistant):
    """Test that required param check is skipped for templated service calls."""
    from custom_components.autodoctor.models import ServiceCall

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="{{ my_service }}",
        location="action[0]",
        is_template=True,
        data={},
    )

    issues = validator.validate_service_calls([call])

    # Templated services should be completely skipped
    assert len(issues) == 0


async def test_validate_skips_required_check_when_data_is_templated(
    hass: HomeAssistant,
):
    """Test required param check skipped when data values contain templates."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "brightness": {
                        "required": True,
                        "selector": {"number": {}},
                    },
                    "entity_id": {
                        "required": True,
                        "selector": {"entity": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"brightness": "{{ brightness_var }}", "entity_id": "light.kitchen"},
    )

    issues = validator.validate_service_calls([call])

    # Should not flag brightness as missing since it's present (even though templated)
    missing_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
    ]
    assert len(missing_issues) == 0


async def test_validate_unknown_param(hass: HomeAssistant):
    """Test validation for unknown parameter."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass, strict_service_validation=True)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "brightness": {
                        "required": False,
                        "selector": {"number": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"brigthness": 128},  # Typo: brigthness instead of brightness
    )

    issues = validator.validate_service_calls([call])

    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 1
    assert unknown_issues[0].severity == Severity.WARNING
    assert unknown_issues[0].entity_id == ""
    assert "brigthness" in unknown_issues[0].message
    # Should suggest 'brightness' via fuzzy match
    assert unknown_issues[0].suggestion == "brightness"


async def test_validate_unknown_param_skips_no_fields(hass: HomeAssistant):
    """Test unknown param check skips services with no fields defined."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {}  # No fields defined
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"anything": "goes"},
    )

    issues = validator.validate_service_calls([call])

    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 0


async def test_validate_invalid_param_type_number(hass: HomeAssistant):
    """Test validation for invalid parameter type (expected number, got string)."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "brightness": {
                        "required": False,
                        "selector": {"number": {"min": 0, "max": 255}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"brightness": "not_a_number"},
    )

    issues = validator.validate_service_calls([call])

    # Type checking removed v2.7.0 — verify no false positives
    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 0


async def test_validate_valid_param_type_number(hass: HomeAssistant):
    """Test that valid number type passes."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "brightness": {
                        "required": False,
                        "selector": {"number": {"min": 0, "max": 255}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"brightness": 128},
    )

    issues = validator.validate_service_calls([call])

    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 0


async def test_validate_invalid_param_type_boolean(hass: HomeAssistant):
    """Test validation for invalid parameter type (expected boolean)."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "enabled": {
                        "required": False,
                        "selector": {"boolean": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"enabled": "yes"},  # String instead of bool
    )

    issues = validator.validate_service_calls([call])

    # Type checking removed v2.7.0 — verify no false positives
    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 0


async def test_validate_skips_type_check_for_templated_values(hass: HomeAssistant):
    """Test that type validation is skipped for templated values."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "brightness": {
                        "required": False,
                        "selector": {"number": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"brightness": "{{ brightness_var }}"},
    )

    issues = validator.validate_service_calls([call])

    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 0


async def test_validate_select_option_valid(hass: HomeAssistant):
    """Test validation passes for valid select option."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "mode": {
                        "required": False,
                        "selector": {"select": {"options": ["auto", "manual", "off"]}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"mode": "auto"},
    )

    issues = validator.validate_service_calls([call])

    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 0


async def test_validate_select_option_invalid(hass: HomeAssistant):
    """Test validation flags invalid select option."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "mode": {
                        "required": False,
                        "selector": {"select": {"options": ["auto", "manual", "off"]}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"mode": "turbo"},  # Not in options
    )

    issues = validator.validate_service_calls([call])

    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 1
    assert type_issues[0].severity == Severity.WARNING
    assert type_issues[0].entity_id == ""
    assert "turbo" in type_issues[0].message


async def test_validate_no_description_available(hass: HomeAssistant):
    """Test validation when no service description is available."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {}  # No descriptions loaded

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"anything": "value"},
    )

    issues = validator.validate_service_calls([call])

    # Should only check existence, no param validation without descriptions
    param_issues = [
        i
        for i in issues
        if i.issue_type
        in (
            IssueType.SERVICE_MISSING_REQUIRED_PARAM,
            IssueType.SERVICE_UNKNOWN_PARAM,
            IssueType.SERVICE_INVALID_PARAM_TYPE,
        )
    ]
    assert len(param_issues) == 0


async def test_validate_all_checks_combined(hass: HomeAssistant):
    """Test all validation checks work together."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass, strict_service_validation=True)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "required_field": {
                        "required": True,
                        "selector": {"text": {}},
                    },
                    "mode": {
                        "required": False,
                        "selector": {"select": {"options": ["auto", "manual"]}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={
            "mode": "turbo",  # Invalid select option
            "unknown_field": "value",  # Unknown param
            # Missing: required_field
        },
    )

    issues = validator.validate_service_calls([call])

    issue_types = {i.issue_type for i in issues}
    assert IssueType.SERVICE_MISSING_REQUIRED_PARAM in issue_types
    assert IssueType.SERVICE_UNKNOWN_PARAM in issue_types
    assert IssueType.SERVICE_INVALID_PARAM_TYPE in issue_types

    # Verify severity for each issue type
    for issue in issues:
        if issue.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM:
            assert issue.severity == Severity.ERROR
        elif (
            issue.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
            or issue.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        ):
            assert issue.severity == Severity.WARNING


async def test_validate_list_parameter_with_valid_options(hass: HomeAssistant):
    """Test that list parameters are validated per-item, not as whole list.

    This reproduces the false positive from the logs:
    Parameter 'include_folders' value '['config']' is not a valid option
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("auto_backup", "backup", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "auto_backup": {
            "backup": {
                "fields": {
                    "include_folders": {
                        "required": False,
                        "selector": {
                            "select": {
                                "options": [
                                    "config",
                                    "share",
                                    "ssl",
                                    "media",
                                    "addons",
                                ],
                                "multiple": True,
                            }
                        },
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="auto_backup.backup",
        location="action[0]",
        data={"include_folders": ["config"]},  # Valid list with valid items
    )

    issues = validator.validate_service_calls([call])

    # Should NOT report any issues - ['config'] contains valid items
    invalid_param_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(invalid_param_issues) == 0, (
        f"False positive: {[i.message for i in invalid_param_issues]}"
    )


async def test_validate_capability_dependent_light_params(hass: HomeAssistant):
    """Test that brightness, color_temp, kelvin are not flagged as unknown for light.turn_on.

    This reproduces the false positives from the logs:
    - Unknown parameter 'brightness' for service 'light.turn_on'
    - Unknown parameter 'color_temp' for service 'light.turn_on'
    - Unknown parameter 'kelvin' for service 'light.turn_on'
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass)
    # Simulate incomplete service description (common in HA)
    # These capability-dependent params may not be in the base schema
    validator._service_descriptions = {
        "light": {
            "turn_on": {
                "fields": {
                    "entity_id": {
                        "required": False,
                        "selector": {"entity": {"domain": "light"}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={
            "brightness": 255,
            "color_temp": 400,
            "kelvin": 3000,
        },
    )

    issues = validator.validate_service_calls([call])

    # Should NOT report these as unknown - they're valid light.turn_on params
    unknown_param_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_param_issues) == 0, (
        f"False positives: {[i.message for i in unknown_param_issues]}"
    )


async def test_unknown_param_not_flagged_without_strict_mode(hass: HomeAssistant):
    """Without strict mode, unknown params should not produce warnings."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("test", "service", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "known_field": {
                        "required": False,
                        "selector": {"text": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
        data={"unknown_field": "value"},
    )

    issues = validator.validate_service_calls([call])

    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 0


async def test_strict_service_mode_flag_stored_on_validator(hass: HomeAssistant):
    """The strict_service_validation flag should be stored correctly."""
    validator_default = ServiceCallValidator(hass)
    assert validator_default._strict_validation is False

    validator_strict = ServiceCallValidator(hass, strict_service_validation=True)
    assert validator_strict._strict_validation is True


@pytest.mark.parametrize(
    "service,param",
    [
        ("media_player.play_media", "media_content_id"),
        ("media_player.play_media", "media_content_type"),
        ("media_player.select_source", "source"),
        ("media_player.select_sound_mode", "sound_mode"),
        ("fan.set_percentage", "percentage"),
        ("fan.set_preset_mode", "preset_mode"),
        ("fan.set_direction", "direction"),
        ("vacuum.send_command", "command"),
        ("alarm_control_panel.alarm_arm_away", "code"),
        ("alarm_control_panel.alarm_arm_home", "code"),
        ("alarm_control_panel.alarm_disarm", "code"),
        ("number.set_value", "value"),
        ("input_text.set_value", "value"),
        ("input_number.set_value", "value"),
        ("input_select.select_option", "option"),
        ("input_datetime.set_datetime", "date"),
        ("input_datetime.set_datetime", "time"),
        ("input_datetime.set_datetime", "datetime"),
        ("input_datetime.set_datetime", "timestamp"),
        ("select.select_option", "option"),
        ("text.set_value", "value"),
        ("lock.lock", "code"),
        ("lock.unlock", "code"),
        ("lock.open", "code"),
        ("siren.turn_on", "tone"),
        ("siren.turn_on", "volume_level"),
        ("siren.turn_on", "duration"),
        ("remote.send_command", "command"),
        ("remote.send_command", "device"),
        ("remote.send_command", "delay_secs"),
        ("remote.send_command", "num_repeats"),
        ("tts.speak", "message"),
        ("tts.speak", "cache"),
        ("tts.speak", "language"),
        ("tts.speak", "options"),
        ("humidifier.set_humidity", "humidity"),
        ("humidifier.set_mode", "mode"),
        ("water_heater.set_temperature", "temperature"),
        ("water_heater.set_operation_mode", "operation_mode"),
    ],
)
async def test_capability_dependent_params_not_flagged(
    hass: HomeAssistant, service: str, param: str
):
    """Capability-dependent params should not be flagged as unknown."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    domain, svc = service.split(".", 1)

    async def test_service(call):
        pass

    hass.services.async_register(domain, svc, test_service)

    validator = ServiceCallValidator(hass, strict_service_validation=True)
    validator._service_descriptions = {
        domain: {
            svc: {
                "fields": {
                    "entity_id": {
                        "required": False,
                        "selector": {"entity": {"domain": domain}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service=service,
        location="action[0]",
        data={param: "test_value"},
    )

    issues = validator.validate_service_calls([call])

    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 0, (
        f"Parameter '{param}' flagged as unknown for '{service}': "
        f"{[i.message for i in unknown_issues]}"
    )


async def test_service_not_found_fuzzy_suggestion(hass: HomeAssistant):
    """Test SERVICE_NOT_FOUND includes fuzzy suggestion for close match."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    # Register "turn_off" so "turn_of" (typo) can be suggested
    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_off", test_service)
    hass.services.async_register("light", "turn_on", test_service)
    hass.services.async_register("light", "toggle", test_service)

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_of",  # Typo: missing trailing 'f'
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == ""
    assert "Did you mean 'light.turn_off'?" in issues[0].message
    assert issues[0].suggestion == "light.turn_off"


async def test_service_not_found_no_suggestion_wrong_domain(hass: HomeAssistant):
    """Test SERVICE_NOT_FOUND without suggestion when domain has no services."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="nonexistent.service",
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == ""
    assert "Did you mean" not in issues[0].message
    assert issues[0].suggestion is None


async def test_service_not_found_no_suggestion_no_close_match(hass: HomeAssistant):
    """Test SERVICE_NOT_FOUND without suggestion when no close match exists."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_off", test_service)
    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.zzzzzzzzz",  # Completely unrelated
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == ""
    assert "Did you mean" not in issues[0].message
    assert issues[0].suggestion is None


async def test_unknown_target_key_flagged(hass: HomeAssistant):
    """Test that non-standard keys in target dict are flagged."""
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass, strict_service_validation=True)
    validator._service_descriptions = {
        "light": {
            "turn_on": {
                "fields": {
                    "brightness": {
                        "required": False,
                        "selector": {"number": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={"brightness": 128},
        target={"entity_id": "light.kitchen", "entitiy_id": "light.bedroom"},  # Typo
    )

    issues = validator.validate_service_calls([call])

    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 1
    assert unknown_issues[0].severity == Severity.WARNING
    assert unknown_issues[0].entity_id == ""
    assert "Unknown target key 'entitiy_id'" in unknown_issues[0].message
    assert "entity_id" in (unknown_issues[0].suggestion or "")


async def test_valid_target_keys_not_flagged(hass: HomeAssistant):
    """Test that standard target keys (entity_id, device_id, area_id) are not flagged."""
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass, strict_service_validation=True)
    validator._service_descriptions = {
        "light": {
            "turn_on": {
                "fields": {
                    "brightness": {
                        "required": False,
                        "selector": {"number": {}},
                    },
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={},
        target={
            "entity_id": "light.kitchen",
            "device_id": "abc123",
            "area_id": "living_room",
        },
    )

    issues = validator.validate_service_calls([call])

    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 0


async def test_refresh_service_descriptions(hass: HomeAssistant):
    """Validator can refresh service descriptions on demand."""
    validator = ServiceCallValidator(hass)
    assert validator._service_descriptions is None

    await validator.async_load_descriptions()
    # After load, descriptions should be set (dict, possibly empty)
    assert validator._service_descriptions is not None


# --- Template entity skipping, entity existence, and loop hardening (SV-01, SV-02, SV-03) ---


async def test_template_entity_id_skips_validation(hass: HomeAssistant):
    """Entity ID containing '{{' in target should skip validation entirely.

    Kills: AddNot on 'if "{{" in entity_id' -- if the condition is inverted,
    the template entity would be validated and produce a target-not-found issue.
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": "{{ my_entity }}"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 0


async def test_non_template_entity_validated(hass: HomeAssistant):
    """Non-template entity_id IS validated and produces issue when missing.

    Contrast test for SV-01: proves non-template entities are validated.
    Kills AddNot on template check (both directions covered).
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall, Severity

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": "light.nonexistent"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 1
    assert target_issues[0].severity == Severity.WARNING
    assert target_issues[0].entity_id == "light.nonexistent"


async def test_existing_target_entity_no_issue(hass: HomeAssistant):
    """Existing entity_id in target should NOT produce SERVICE_TARGET_NOT_FOUND.

    Kills: Is->IsNot on 'hass.states.get(entity_id) is None' -- if mutated
    to 'is not None', existing entities would be incorrectly flagged.
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)
    hass.states.async_set("light.kitchen", "on")

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": "light.kitchen"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 0


async def test_multiple_nonexistent_entities_all_produce_issues(hass: HomeAssistant):
    """Multiple nonexistent entity_ids must ALL produce issues.

    Kills: ReplaceContinueWithBreak on entity_id loop in _validate_target_entities.
    If break replaces continue, only the first entity would be checked and the
    loop would exit early, producing only 1 issue instead of 3.
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": ["light.fake1", "light.fake2", "light.fake3"]},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 3
    flagged_entities = {i.entity_id for i in target_issues}
    assert flagged_entities == {"light.fake1", "light.fake2", "light.fake3"}


async def test_multiple_required_fields_all_checked(hass: HomeAssistant):
    """Multiple missing required fields must ALL produce issues.

    Kills: ReplaceContinueWithBreak on _validate_required_params loop.
    If break replaces continue, only the first missing field would be reported.
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)
    hass.states.async_set("light.kitchen", "on")

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {
            "turn_on": {
                "fields": {
                    "field_a": {"required": True},
                    "field_b": {"required": True},
                    "field_c": {"required": True},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={},
        target={"entity_id": "light.kitchen"},
    )

    issues = validator.validate_service_calls([call])
    missing_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
    ]
    assert len(missing_issues) == 3


async def test_multiple_unknown_params_all_checked(hass: HomeAssistant):
    """Multiple unknown params must ALL produce issues in strict mode.

    Kills: ReplaceContinueWithBreak on _validate_unknown_params data loop.
    If break replaces continue, only the first unknown param would be reported.
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    async def test_service(call):
        pass

    hass.services.async_register("light", "turn_on", test_service)
    hass.states.async_set("light.kitchen", "on")

    validator = ServiceCallValidator(hass, strict_service_validation=True)
    validator._service_descriptions = {
        "light": {
            "turn_on": {
                "fields": {
                    "brightness": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={"unknown1": "a", "unknown2": "b", "unknown3": "c"},
        target={"entity_id": "light.kitchen"},
    )

    issues = validator.validate_service_calls([call])
    unknown_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM
    ]
    assert len(unknown_issues) == 3


# --- Fuzzy match parameter mutations (SV-04) ---


async def test_suggest_target_entity_fuzzy_match_sensitivity(hass: HomeAssistant):
    """Entity suggestion returns match for close typo, None for distant input.

    Kills: NumberReplacer on cutoff=0.75 (1.0 rejects close match, 0.0 accepts
    distant match) and n=1 (n=0 returns empty list).
    """
    hass.states.async_set("light.living_room", "on")
    hass.states.async_set("light.bedroom", "on")

    validator = ServiceCallValidator(hass)

    # Close typo: "living_roam" vs "living_room" (~0.9 similarity) -- matches at 0.75
    result = validator._suggest_target_entity("light.living_roam")
    assert result == "light.living_room"

    # Distant input: completely different name -- no match at 0.75
    result = validator._suggest_target_entity("light.zzzzzzzzz")
    assert result is None

    # No dot in entity_id -- early return None
    result = validator._suggest_target_entity("nodot")
    assert result is None


async def test_suggest_param_fuzzy_match_sensitivity(hass: HomeAssistant):
    """Param suggestion returns match for close typo, None for distant input.

    Kills: NumberReplacer on cutoff=0.75 and n=1 in _suggest_param.
    """
    validator = ServiceCallValidator(hass)

    # Close typo: "brigthness" vs "brightness" (~0.9 similarity)
    result = validator._suggest_param(
        "brigthness", ["brightness", "color_temp", "transition"]
    )
    assert result == "brightness"

    # Distant input: no match at 0.75
    result = validator._suggest_param(
        "zzzzz", ["brightness", "color_temp", "transition"]
    )
    assert result is None


async def test_suggest_service_fuzzy_match_sensitivity(hass: HomeAssistant):
    """Service suggestion returns match for close/moderate typos, None for distant.

    _suggest_service uses cutoff=0.6 (lower than others' 0.75).
    Kills: NumberReplacer on cutoff=0.6 and n=1 in _suggest_service.
    """

    async def handler(call):
        pass

    hass.services.async_register("light", "turn_on", handler)
    hass.services.async_register("light", "turn_off", handler)
    hass.services.async_register("light", "toggle", handler)

    validator = ServiceCallValidator(hass)

    # Close typo: "turn_of" vs "turn_off" (~0.92 similarity)
    result = validator._suggest_service("light.turn_of")
    assert result == "light.turn_off"

    # Moderate typo that works at 0.6 cutoff: "toggl" vs "toggle" (~0.83)
    result = validator._suggest_service("light.toggl")
    assert result == "light.toggle"

    # Distant input: no match even at 0.6
    result = validator._suggest_service("light.zzzzzzzzz")
    assert result is None

    # No dot: early return None
    result = validator._suggest_service("nodot")
    assert result is None


async def test_suggest_target_entity_with_multiple_same_domain(hass: HomeAssistant):
    """With multiple entities in same domain, best match is returned (n=1).

    Kills: NumberReplacer on n=1 -- n=0 returns empty list (None result),
    so asserting a match IS returned catches the mutation.
    """
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.kitchen_ceiling", "on")
    hass.states.async_set("light.kitchen_island", "on")
    hass.states.async_set("light.bedroom", "on")

    validator = ServiceCallValidator(hass)

    # "kitchn" vs "kitchen" -- best match is "light.kitchen"
    result = validator._suggest_target_entity("light.kitchn")
    assert result == "light.kitchen"


async def test_validate_required_param_from_inline_params(hass: HomeAssistant):
    """Test that inline params (merged into data) satisfy required param validation.

    End-to-end integration test: a ServiceCall with data populated from inline
    params should NOT trigger SERVICE_MISSING_REQUIRED_PARAM.
    """
    from custom_components.autodoctor.models import IssueType, ServiceCall

    # Register a test service
    async def test_service(call):
        pass

    hass.services.async_register("notify", "mobile_app_phone", test_service)

    validator = ServiceCallValidator(hass)

    # Mock service descriptions with a required 'message' field
    validator._service_descriptions = {
        "notify": {
            "mobile_app_phone": {
                "fields": {
                    "message": {
                        "required": True,
                        "selector": {"text": {}},
                    },
                    "title": {
                        "required": False,
                        "selector": {"text": {}},
                    },
                }
            }
        }
    }

    # Simulate what the analyzer produces after merging inline params
    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="notify.mobile_app_phone",
        location="action[0]",
        data={"message": "Hello", "title": "Alert"},
    )

    issues = validator.validate_service_calls([call])

    missing_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
    ]
    assert len(missing_issues) == 0
