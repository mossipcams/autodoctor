"""Tests for ServiceCallValidator.

Tests cover service validation including:
- Service existence checks
- Required parameter validation
- Unknown parameter detection (strict mode)
- Parameter type validation for select options
- Template handling (skipping validation for templated services/entities)
- Target entity validation
- Fuzzy matching for suggestions
"""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.core import ServiceCall as HAServiceCall

from custom_components.autodoctor.models import IssueType, ServiceCall, Severity
from custom_components.autodoctor.service_validator import ServiceCallValidator

# Shared no-op service handler for all registration tests


async def _noop_service_handler(call: HAServiceCall) -> None:
    pass


async def test_service_validator_initialization(hass: HomeAssistant) -> None:
    """Test that ServiceCallValidator can be initialized with HomeAssistant instance."""
    validator = ServiceCallValidator(hass)
    assert validator is not None
    stats = validator.get_last_run_stats()
    assert stats["total_calls"] == 0
    assert stats["skipped_calls_by_reason"] == {}


async def test_validate_service_not_found(hass: HomeAssistant) -> None:
    """Test validator detects when a service does not exist.

    Ensures users are warned when automations call services that are not
    registered in their Home Assistant instance.
    """
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


async def test_validate_service_exists_no_issues(hass: HomeAssistant) -> None:
    """Test that validation passes when service exists.

    No issues should be reported for a service that is registered
    in Home Assistant.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.service",
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 0


async def test_validate_skips_templated_service(hass: HomeAssistant) -> None:
    """Test that validation skips services with templated names.

    Service names containing Jinja2 templates cannot be validated at analysis
    time, so they should be skipped without producing issues.
    """

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


async def test_validate_tracks_skip_reasons(hass: HomeAssistant) -> None:
    """Validator should expose skip-reason telemetry for skipped calls."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    # Keep descriptions unavailable for the non-templated call.
    validator._service_descriptions = None

    issues = validator.validate_service_calls(
        [
            ServiceCall(
                automation_id="automation.test",
                automation_name="Test",
                service="{{ dynamic_service }}",
                location="action[0]",
                is_template=True,
            ),
            ServiceCall(
                automation_id="automation.test",
                automation_name="Test",
                service="light.turn_on",
                location="action[1]",
            ),
        ]
    )

    assert issues == []
    stats = validator.get_last_run_stats()
    assert stats["total_calls"] == 2
    assert stats["skipped_calls_by_reason"]["templated_service_name"] == 1
    assert stats["skipped_calls_by_reason"]["missing_service_descriptions"] == 1


async def test_validate_missing_required_param(hass: HomeAssistant) -> None:
    """Test validator detects missing required service parameters.

    Services may define required fields. When a service call omits these,
    an ERROR-level issue should be reported.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_missing_required_param_in_target(hass: HomeAssistant) -> None:
    """Test that required parameters specified in target are not flagged as missing.

    entity_id can appear in either data or target dict. When in target,
    it should satisfy the required parameter check.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_skips_required_check_when_templated(
    hass: HomeAssistant,
) -> None:
    """Test that required parameter checking skips templated service calls.

    Templated service names cannot be resolved at analysis time, so all
    parameter validation must be skipped.
    """

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
) -> None:
    """Test that required parameter checking handles templated data values.

    When data values contain templates, the parameter is considered present
    even though its runtime value is unknown.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_unknown_param(hass: HomeAssistant) -> None:
    """Test validator detects unknown parameters in strict mode.

    When strict_service_validation is enabled, parameters not defined in the
    service schema should produce WARNING-level issues with fuzzy suggestions.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_unknown_param_skips_no_fields(hass: HomeAssistant) -> None:
    """Test that unknown parameter checking skips services with no field definitions.

    Services without field schemas cannot be validated for unknown parameters.
    This prevents false positives for services with dynamic or undocumented schemas.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_invalid_param_type_number(hass: HomeAssistant) -> None:
    """Test that type validation was removed for number fields (v2.7.0).

    Type checking for number/boolean fields produced false positives and
    was removed. This test verifies no issues are raised for string values
    in number fields.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_valid_param_type_number(hass: HomeAssistant) -> None:
    """Test that valid number values do not produce type errors.

    Verifies correct number types pass validation without issues.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_invalid_param_type_boolean(hass: HomeAssistant) -> None:
    """Test that type validation was removed for boolean fields (v2.7.0).

    Boolean type checking produced false positives and was removed.
    This test verifies no issues are raised for string values in boolean fields.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_skips_type_check_for_templated_values(
    hass: HomeAssistant,
) -> None:
    """Test that type validation is skipped for templated values.

    Templated values cannot be type-checked at analysis time since their
    runtime value is unknown.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_select_option_valid(hass: HomeAssistant) -> None:
    """Test that valid select options pass validation.

    Select fields with defined options should accept values from their
    option list without producing issues.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_select_option_invalid(hass: HomeAssistant) -> None:
    """Test validator detects invalid select options.

    Select fields with defined options should produce WARNING-level issues
    when values are not in the option list.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_no_description_available(hass: HomeAssistant) -> None:
    """Test that validator gracefully handles missing service descriptions.

    When service descriptions are not available, only service existence
    should be checked. No parameter validation should occur.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_all_checks_combined(hass: HomeAssistant) -> None:
    """Test that multiple validation checks can run together.

    A single service call can trigger multiple validation issues:
    missing required params, unknown params, and invalid select options.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_validate_list_parameter_with_valid_options(hass: HomeAssistant) -> None:
    """Test that list parameters with multiple:true are validated per-item.

    Prevents false positives where list values like ['config'] were incorrectly
    compared against the string 'config' instead of validating each list item.
    """

    hass.services.async_register("auto_backup", "backup", _noop_service_handler)

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


async def test_validate_capability_dependent_light_params(hass: HomeAssistant) -> None:
    """Test that capability-dependent light parameters are not flagged as unknown.

    Prevents false positives for parameters like brightness, color_temp, and
    kelvin which depend on device capabilities and may not be in base schemas.
    These parameters are valid for light.turn_on but not always documented
    in service descriptions.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_unknown_param_not_flagged_without_strict_mode(
    hass: HomeAssistant,
) -> None:
    """Test that unknown parameters are not flagged without strict mode.

    Without strict_service_validation enabled, unknown parameters should
    be ignored to prevent false positives.
    """

    hass.services.async_register("test", "service", _noop_service_handler)

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


async def test_strict_service_mode_flag_stored_on_validator(
    hass: HomeAssistant,
) -> None:
    """Test that strict_service_validation flag is stored correctly.

    The validator should store the strict validation mode as an instance
    variable for use during validation.
    """
    validator_default = ServiceCallValidator(hass)
    assert validator_default._strict_validation is False

    validator_strict = ServiceCallValidator(hass, strict_service_validation=True)
    assert validator_strict._strict_validation is True


@pytest.mark.parametrize(
    ("service", "param"),
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
) -> None:
    """Test that capability-dependent parameters are not flagged as unknown.

    Many services have parameters that depend on device capabilities and may
    not appear in service schemas. These should be whitelisted to prevent
    false positives.
    """
    domain, svc = service.split(".", 1)

    hass.services.async_register(domain, svc, _noop_service_handler)

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


async def test_service_not_found_fuzzy_suggestion(hass: HomeAssistant) -> None:
    """Test that SERVICE_NOT_FOUND includes fuzzy suggestions for typos.

    When a service is not found but a similar service exists, the validator
    should suggest the closest match to help users fix typos.
    """

    hass.services.async_register("light", "turn_off", _noop_service_handler)
    hass.services.async_register("light", "turn_on", _noop_service_handler)
    hass.services.async_register("light", "toggle", _noop_service_handler)

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


async def test_service_not_found_no_suggestion_wrong_domain(
    hass: HomeAssistant,
) -> None:
    """Test that SERVICE_NOT_FOUND provides no suggestion for unknown domains.

    When the domain itself does not exist, no service suggestions can be made.
    """

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


async def test_service_not_found_no_suggestion_no_close_match(
    hass: HomeAssistant,
) -> None:
    """Test that SERVICE_NOT_FOUND provides no suggestion when name is too different.

    When the service name is completely unrelated to existing services,
    no fuzzy match should be suggested.
    """

    hass.services.async_register("light", "turn_off", _noop_service_handler)
    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_unknown_target_key_flagged(hass: HomeAssistant) -> None:
    """Test that non-standard keys in target dict are flagged in strict mode.

    Target dicts should only contain entity_id, device_id, and area_id.
    Other keys (like typos) should produce warnings with fuzzy suggestions.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_valid_target_keys_not_flagged(hass: HomeAssistant) -> None:
    """Test that standard target keys are not flagged.

    entity_id, device_id, and area_id are all valid target keys and should
    not produce unknown parameter warnings.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_refresh_service_descriptions(hass: HomeAssistant) -> None:
    """Test that validator can load service descriptions on demand.

    Service descriptions are lazy-loaded and should be populated when
    async_load_descriptions is called.
    """
    validator = ServiceCallValidator(hass)
    assert validator._service_descriptions is None

    await validator.async_load_descriptions()
    # After load, descriptions should be set (dict, possibly empty)
    assert validator._service_descriptions is not None


# --- Template entity skipping, entity existence, and loop hardening (SV-01, SV-02, SV-03) ---


async def test_template_entity_id_skips_validation(hass: HomeAssistant) -> None:
    """Test that templated entity_ids in target skip validation.

    Entity IDs containing '{{' are templates and cannot be validated at
    analysis time. They should be skipped without producing issues.

    Mutation test: Kills AddNot on 'if "{{" in entity_id' check.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_none_placeholder_entity_id_is_validated_as_missing(
    hass: HomeAssistant,
) -> None:
    """Blueprint entity_id='none' placeholder should be validated as missing."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": "none"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 1
    assert target_issues[0].entity_id == "none"


async def test_non_template_entity_validated(hass: HomeAssistant) -> None:
    """Test that non-template entity_ids are validated.

    Regular entity IDs (without templates) should be checked for existence
    and produce SERVICE_TARGET_NOT_FOUND issues when missing.

    Mutation test: Contrast test for SV-01, kills AddNot on template check.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_existing_target_entity_no_issue(hass: HomeAssistant) -> None:
    """Test that existing entity_ids in target do not produce issues.

    Entities that exist in Home Assistant state should not be flagged
    as missing.

    Mutation test: Kills Is->IsNot on 'hass.states.get(entity_id) is None'.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)
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


async def test_multiple_nonexistent_entities_all_produce_issues(
    hass: HomeAssistant,
) -> None:
    """Test that all nonexistent entity_ids in a list produce separate issues.

    When target contains multiple missing entities, each should produce its
    own SERVICE_TARGET_NOT_FOUND issue.

    Mutation test: Kills ReplaceContinueWithBreak on entity_id loop.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)

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


async def test_nonexistent_entity_id_in_data_produces_target_issue(
    hass: HomeAssistant,
) -> None:
    """Entity IDs in data should also be validated as service targets."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={"entity_id": "light.missing_from_data"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 1
    assert target_issues[0].entity_id == "light.missing_from_data"
    assert "Entity" in target_issues[0].message


async def test_nonexistent_device_and_area_ids_produce_target_issues(
    hass: HomeAssistant,
) -> None:
    """Missing device_id/area_id in target should produce service target issues."""

    hass.services.async_register("homeassistant", "toggle", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "homeassistant": {"toggle": {"fields": {"entity_id": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="homeassistant.toggle",
        location="action[0]",
        target={"device_id": "missing_device", "area_id": "missing_area"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 2
    by_entity = {i.entity_id: i.message for i in target_issues}
    assert "missing_device" in by_entity
    assert "missing_area" in by_entity
    assert "Device" in by_entity["missing_device"]
    assert "Area" in by_entity["missing_area"]


async def test_template_device_and_area_ids_skip_target_validation(
    hass: HomeAssistant,
) -> None:
    """Templated device/area targets should be skipped (not statically knowable)."""

    hass.services.async_register("homeassistant", "toggle", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "homeassistant": {"toggle": {"fields": {"entity_id": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="homeassistant.toggle",
        location="action[0]",
        target={"device_id": "{{ device_ref }}", "area_id": "{{ area_ref }}"},
    )

    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 0


async def test_invalid_target_entity_id_type_reports_issue(
    hass: HomeAssistant,
) -> None:
    """Non-string entity_id target values should produce type issues."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": 123},  # invalid type
    )

    issues = validator.validate_service_calls([call])
    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 1
    assert "entity_id" in type_issues[0].message
    assert "string or list of strings" in type_issues[0].message


async def test_invalid_target_device_id_list_item_type_reports_issue(
    hass: HomeAssistant,
) -> None:
    """Non-string device_id list items should produce type issues."""

    hass.services.async_register("homeassistant", "toggle", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "homeassistant": {"toggle": {"fields": {"entity_id": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="homeassistant.toggle",
        location="action[0]",
        target={"device_id": ["device_ok", 7]},  # invalid item type
    )

    issues = validator.validate_service_calls([call])
    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 1
    assert "device_id" in type_issues[0].message
    assert "non-string items" in type_issues[0].message


async def test_non_mapping_target_reports_invalid_type_issue(
    hass: HomeAssistant,
) -> None:
    """Non-mapping target payloads should be reported, not silently skipped."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target="light.kitchen",  # type: ignore[arg-type]
    )

    issues = validator.validate_service_calls([call])
    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 1
    assert "target" in type_issues[0].message
    assert "mapping" in type_issues[0].message


async def test_non_template_non_mapping_data_reports_invalid_type_issue(
    hass: HomeAssistant,
) -> None:
    """Non-mapping data payloads should be reported unless templated."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data="plain_string_not_template",  # type: ignore[arg-type]
    )

    issues = validator.validate_service_calls([call])
    type_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
    ]
    assert len(type_issues) == 1
    assert "data" in type_issues[0].message
    assert "mapping" in type_issues[0].message


async def test_conflicting_entity_id_between_data_and_target_reports_issue(
    hass: HomeAssistant,
) -> None:
    """Conflicting data/target entity_id values should be flagged."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.bedroom", "on")

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "light": {"turn_on": {"fields": {"brightness": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data={"entity_id": "light.kitchen"},
        target={"entity_id": "light.bedroom"},
    )

    issues = validator.validate_service_calls([call])
    conflict_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting values" in i.message
    ]
    assert len(conflict_issues) == 1
    assert "entity_id" in conflict_issues[0].message


async def test_matching_entity_id_between_data_and_target_no_conflict_issue(
    hass: HomeAssistant,
) -> None:
    """Matching data/target entity_id values should not be flagged."""

    hass.services.async_register("light", "turn_on", _noop_service_handler)
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
        data={"entity_id": ["light.kitchen"]},
        target={"entity_id": "light.kitchen"},
    )

    issues = validator.validate_service_calls([call])
    conflict_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting values" in i.message
    ]
    assert len(conflict_issues) == 0


async def test_conflicting_device_id_between_data_and_target_reports_issue(
    hass: HomeAssistant,
) -> None:
    """Conflicting data/target device_id values should be flagged."""

    hass.services.async_register("homeassistant", "toggle", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "homeassistant": {"toggle": {"fields": {"entity_id": {"required": False}}}}
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="homeassistant.toggle",
        location="action[0]",
        data={"device_id": "device_a"},
        target={"device_id": "device_b"},
    )

    issues = validator.validate_service_calls([call])
    conflict_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting values" in i.message
    ]
    assert len(conflict_issues) == 1
    assert "device_id" in conflict_issues[0].message


async def test_input_datetime_conflicting_datetime_and_date_reports_issue(
    hass: HomeAssistant,
) -> None:
    """input_datetime.set_datetime should flag conflicting time payload modes."""

    hass.services.async_register(
        "input_datetime", "set_datetime", _noop_service_handler
    )

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "input_datetime": {
            "set_datetime": {
                "fields": {
                    "date": {"required": False},
                    "time": {"required": False},
                    "datetime": {"required": False},
                    "timestamp": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="input_datetime.set_datetime",
        location="action[0]",
        data={"datetime": "2026-02-09 12:00:00", "date": "2026-02-09"},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting parameters" in i.message
    ]
    assert len(semantic_issues) == 1
    assert "datetime" in semantic_issues[0].message
    assert "date" in semantic_issues[0].message


async def test_input_datetime_date_and_time_allowed_no_conflict_issue(
    hass: HomeAssistant,
) -> None:
    """input_datetime.set_datetime should allow date+time together."""

    hass.services.async_register(
        "input_datetime", "set_datetime", _noop_service_handler
    )

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "input_datetime": {
            "set_datetime": {
                "fields": {
                    "date": {"required": False},
                    "time": {"required": False},
                    "datetime": {"required": False},
                    "timestamp": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="input_datetime.set_datetime",
        location="action[0]",
        data={"date": "2026-02-09", "time": "12:00:00"},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting parameters" in i.message
    ]
    assert len(semantic_issues) == 0


async def test_climate_set_temperature_conflicting_single_and_range_reports_issue(
    hass: HomeAssistant,
) -> None:
    """climate.set_temperature should flag mixed single+range setpoint payloads."""

    hass.services.async_register("climate", "set_temperature", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "climate": {
            "set_temperature": {
                "fields": {
                    "temperature": {"required": False},
                    "target_temp_high": {"required": False},
                    "target_temp_low": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="climate.set_temperature",
        location="action[0]",
        data={"temperature": 21, "target_temp_high": 24, "target_temp_low": 18},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting parameters" in i.message
    ]
    assert len(semantic_issues) == 1
    assert "temperature" in semantic_issues[0].message
    assert "target_temp_high" in semantic_issues[0].message
    assert "target_temp_low" in semantic_issues[0].message
    assert semantic_issues[0].confidence == "medium"


async def test_climate_set_temperature_range_only_allowed_no_conflict_issue(
    hass: HomeAssistant,
) -> None:
    """climate.set_temperature should allow range-only setpoint payloads."""

    hass.services.async_register("climate", "set_temperature", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "climate": {
            "set_temperature": {
                "fields": {
                    "temperature": {"required": False},
                    "target_temp_high": {"required": False},
                    "target_temp_low": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="climate.set_temperature",
        location="action[0]",
        data={"target_temp_high": 24, "target_temp_low": 18},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "conflicting parameters" in i.message
    ]
    assert len(semantic_issues) == 0


async def test_media_player_play_media_missing_type_reports_issue(
    hass: HomeAssistant,
) -> None:
    """media_player.play_media should require media_content_type with media_content_id."""

    hass.services.async_register("media_player", "play_media", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "media_player": {
            "play_media": {
                "fields": {
                    "media_content_id": {"required": False},
                    "media_content_type": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="media_player.play_media",
        location="action[0]",
        data={"media_content_id": "spotify:track:123"},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
        and "media_content_type" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_media_player_play_media_with_id_and_type_no_issue(
    hass: HomeAssistant,
) -> None:
    """media_player.play_media with id+type should not trigger semantic issues."""

    hass.services.async_register("media_player", "play_media", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "media_player": {
            "play_media": {
                "fields": {
                    "media_content_id": {"required": False},
                    "media_content_type": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="media_player.play_media",
        location="action[0]",
        data={
            "media_content_id": "spotify:track:123",
            "media_content_type": "music",
        },
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
        and "media_content_type" in i.message
    ]
    assert len(semantic_issues) == 0


async def test_remote_send_command_aux_params_without_command_reports_issue(
    hass: HomeAssistant,
) -> None:
    """remote.send_command should require command when aux params are present."""

    hass.services.async_register("remote", "send_command", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "remote": {
            "send_command": {
                "fields": {
                    "command": {"required": False},
                    "device": {"required": False},
                    "delay_secs": {"required": False},
                    "num_repeats": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="remote.send_command",
        location="action[0]",
        data={"device": "tv", "num_repeats": 2},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
        and "command" in i.message
        and "remote.send_command" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_remote_send_command_with_command_no_semantic_issue(
    hass: HomeAssistant,
) -> None:
    """remote.send_command with command should not trigger aux-param rule."""

    hass.services.async_register("remote", "send_command", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "remote": {
            "send_command": {
                "fields": {
                    "command": {"required": False},
                    "device": {"required": False},
                    "delay_secs": {"required": False},
                    "num_repeats": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="remote.send_command",
        location="action[0]",
        data={"command": "POWER", "device": "tv", "num_repeats": 2},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
        and "remote.send_command" in i.message
    ]
    assert len(semantic_issues) == 0


async def test_tts_speak_empty_message_reports_issue(
    hass: HomeAssistant,
) -> None:
    """tts.speak should flag empty message payloads."""

    hass.services.async_register("tts", "speak", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "tts": {
            "speak": {
                "fields": {
                    "message": {"required": False},
                    "cache": {"required": False},
                    "language": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="tts.speak",
        location="action[0]",
        data={"message": ""},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "message" in i.message
        and "tts.speak" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_tts_speak_non_empty_message_no_issue(
    hass: HomeAssistant,
) -> None:
    """tts.speak with non-empty message should not trigger semantic issue."""

    hass.services.async_register("tts", "speak", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "tts": {
            "speak": {
                "fields": {
                    "message": {"required": False},
                    "cache": {"required": False},
                    "language": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="tts.speak",
        location="action[0]",
        data={"message": "Garage door is open"},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "tts.speak" in i.message
        and "message" in i.message
    ]
    assert len(semantic_issues) == 0


async def test_remote_send_command_empty_string_command_reports_issue(
    hass: HomeAssistant,
) -> None:
    """remote.send_command should flag empty string command values."""

    hass.services.async_register("remote", "send_command", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "remote": {
            "send_command": {
                "fields": {
                    "command": {"required": False},
                    "device": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="remote.send_command",
        location="action[0]",
        data={"command": "   "},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "remote.send_command" in i.message
        and "command" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_remote_send_command_empty_list_command_reports_issue(
    hass: HomeAssistant,
) -> None:
    """remote.send_command should flag empty list command values."""

    hass.services.async_register("remote", "send_command", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "remote": {
            "send_command": {
                "fields": {
                    "command": {"required": False},
                    "device": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="remote.send_command",
        location="action[0]",
        data={"command": []},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "remote.send_command" in i.message
        and "command" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_media_player_play_media_empty_content_id_reports_issue(
    hass: HomeAssistant,
) -> None:
    """media_player.play_media should flag empty media_content_id values."""

    hass.services.async_register("media_player", "play_media", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "media_player": {
            "play_media": {
                "fields": {
                    "media_content_id": {"required": False},
                    "media_content_type": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="media_player.play_media",
        location="action[0]",
        data={"media_content_id": "   ", "media_content_type": "music"},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "media_player.play_media" in i.message
        and "media_content_id" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_media_player_play_media_empty_content_type_reports_issue(
    hass: HomeAssistant,
) -> None:
    """media_player.play_media should flag empty media_content_type values."""

    hass.services.async_register("media_player", "play_media", _noop_service_handler)

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "media_player": {
            "play_media": {
                "fields": {
                    "media_content_id": {"required": False},
                    "media_content_type": {"required": False},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="media_player.play_media",
        location="action[0]",
        data={"media_content_id": "spotify:track:123", "media_content_type": ""},
    )

    issues = validator.validate_service_calls([call])
    semantic_issues = [
        i
        for i in issues
        if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE
        and "media_player.play_media" in i.message
        and "media_content_type" in i.message
    ]
    assert len(semantic_issues) == 1


async def test_multiple_required_fields_all_checked(hass: HomeAssistant) -> None:
    """Test that all missing required fields produce separate issues.

    When multiple required parameters are missing, each should produce its
    own SERVICE_MISSING_REQUIRED_PARAM issue.

    Mutation test: Kills ReplaceContinueWithBreak on _validate_required_params loop.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)
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


async def test_multiple_unknown_params_all_checked(hass: HomeAssistant) -> None:
    """Test that all unknown parameters produce separate issues in strict mode.

    When multiple unknown parameters are present, each should produce its
    own SERVICE_UNKNOWN_PARAM issue.

    Mutation test: Kills ReplaceContinueWithBreak on _validate_unknown_params loop.
    """

    hass.services.async_register("light", "turn_on", _noop_service_handler)
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


async def test_suggest_target_entity_fuzzy_match_sensitivity(
    hass: HomeAssistant,
) -> None:
    """Test that entity fuzzy matching uses appropriate similarity threshold.

    Suggestions should be provided for close typos (>0.75 similarity) but
    not for completely different names.

    Mutation test: Kills NumberReplacer on cutoff=0.75 and n=1.
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


async def test_suggest_param_fuzzy_match_sensitivity(hass: HomeAssistant) -> None:
    """Test that parameter fuzzy matching uses appropriate similarity threshold.

    Parameter suggestions should be provided for close typos (>0.75 similarity)
    but not for completely different names.

    Mutation test: Kills NumberReplacer on cutoff=0.75 and n=1.
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


async def test_suggest_service_fuzzy_match_sensitivity(hass: HomeAssistant) -> None:
    """Test that service fuzzy matching uses lower similarity threshold (0.6).

    Service suggestions are more lenient than entity/param suggestions to
    help users with moderate typos.

    Mutation test: Kills NumberReplacer on cutoff=0.6 and n=1.
    """

    async def handler(call: HAServiceCall) -> None:
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


async def test_suggest_target_entity_with_multiple_same_domain(
    hass: HomeAssistant,
) -> None:
    """Test that fuzzy matching returns single best match when multiple exist.

    When multiple entities could match, only the closest match should be
    returned (n=1).

    Mutation test: Kills NumberReplacer on n=1.
    """
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.kitchen_ceiling", "on")
    hass.states.async_set("light.kitchen_island", "on")
    hass.states.async_set("light.bedroom", "on")

    validator = ServiceCallValidator(hass)

    # "kitchn" vs "kitchen" -- best match is "light.kitchen"
    result = validator._suggest_target_entity("light.kitchn")
    assert result == "light.kitchen"


async def test_validate_required_param_from_inline_params(
    hass: HomeAssistant,
) -> None:
    """Test that inline parameters merged into data satisfy required checks.

    Integration test: ServiceCall with data populated from inline params
    (like message: "text" at root level) should NOT trigger
    SERVICE_MISSING_REQUIRED_PARAM after the analyzer merges them.
    """

    hass.services.async_register("notify", "mobile_app_phone", _noop_service_handler)

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
