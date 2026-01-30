"""Tests for ServiceCallValidator."""

import pytest
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.service_validator import ServiceCallValidator


async def test_service_validator_initialization(hass: HomeAssistant):
    """Test validator can be created."""
    validator = ServiceCallValidator(hass)
    assert validator is not None


async def test_validate_service_not_found(hass: HomeAssistant):
    """Test validation for non-existent service."""
    from custom_components.autodoctor.models import ServiceCall, Severity, IssueType

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
    assert "nonexistent.service" in issues[0].message


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
    from custom_components.autodoctor.models import ServiceCall, Severity, IssueType

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

    missing_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM]
    assert len(missing_issues) == 1
    assert missing_issues[0].severity == Severity.ERROR
    assert "brightness" in missing_issues[0].message


async def test_validate_missing_required_param_in_target(hass: HomeAssistant):
    """Test that required param in target is not flagged as missing."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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

    missing_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM]
    assert len(missing_issues) == 0


async def test_validate_skips_required_check_when_data_is_templated(hass: HomeAssistant):
    """Test required param check skipped when data values contain templates."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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
    missing_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM]
    assert len(missing_issues) == 0


async def test_validate_unknown_param(hass: HomeAssistant):
    """Test validation for unknown parameter."""
    from custom_components.autodoctor.models import ServiceCall, Severity, IssueType

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

    unknown_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM]
    assert len(unknown_issues) == 1
    assert unknown_issues[0].severity == Severity.WARNING
    assert "brigthness" in unknown_issues[0].message
    # Should suggest 'brightness' via fuzzy match
    assert unknown_issues[0].suggestion == "brightness"


async def test_validate_unknown_param_skips_no_fields(hass: HomeAssistant):
    """Test unknown param check skips services with no fields defined."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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

    unknown_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM]
    assert len(unknown_issues) == 0


async def test_validate_select_option_valid(hass: HomeAssistant):
    """Test validation passes for valid select option."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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

    type_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(type_issues) == 0


async def test_validate_select_option_invalid(hass: HomeAssistant):
    """Test validation flags invalid select option."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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

    type_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(type_issues) == 1
    assert "turbo" in type_issues[0].message


async def test_validate_no_description_available(hass: HomeAssistant):
    """Test validation when no service description is available."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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
        i for i in issues
        if i.issue_type in (
            IssueType.SERVICE_MISSING_REQUIRED_PARAM,
            IssueType.SERVICE_UNKNOWN_PARAM,
            IssueType.SERVICE_INVALID_PARAM_TYPE,
        )
    ]
    assert len(param_issues) == 0


async def test_validate_all_checks_combined(hass: HomeAssistant):
    """Test all validation checks work together."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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
            "mode": "turbo",          # Invalid select option
            "unknown_field": "value",  # Unknown param
            # Missing: required_field
        },
    )

    issues = validator.validate_service_calls([call])

    issue_types = {i.issue_type for i in issues}
    assert IssueType.SERVICE_MISSING_REQUIRED_PARAM in issue_types
    assert IssueType.SERVICE_UNKNOWN_PARAM in issue_types
    assert IssueType.SERVICE_INVALID_PARAM_TYPE in issue_types


async def test_validate_list_parameter_with_valid_options(hass: HomeAssistant):
    """Test that list parameters are validated per-item, not as whole list.

    This reproduces the false positive from the logs:
    Parameter 'include_folders' value '['config']' is not a valid option
    """
    from custom_components.autodoctor.models import ServiceCall, IssueType

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
                                "options": ["config", "share", "ssl", "media", "addons"],
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
    invalid_param_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(invalid_param_issues) == 0, f"False positive: {[i.message for i in invalid_param_issues]}"


async def test_validate_capability_dependent_light_params(hass: HomeAssistant):
    """Test that brightness, color_temp, kelvin are not flagged as unknown for light.turn_on.

    This reproduces the false positives from the logs:
    - Unknown parameter 'brightness' for service 'light.turn_on'
    - Unknown parameter 'color_temp' for service 'light.turn_on'
    - Unknown parameter 'kelvin' for service 'light.turn_on'
    """
    from custom_components.autodoctor.models import ServiceCall, IssueType

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
    unknown_param_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM]
    assert len(unknown_param_issues) == 0, f"False positives: {[i.message for i in unknown_param_issues]}"

async def test_unknown_param_not_flagged_without_strict_mode(hass: HomeAssistant):
    """Without strict mode, unknown params should not produce warnings."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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

    unknown_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_UNKNOWN_PARAM]
    assert len(unknown_issues) == 0


async def test_strict_service_mode_flag_stored_on_validator(hass: HomeAssistant):
    """The strict_service_validation flag should be stored correctly."""
    validator_default = ServiceCallValidator(hass)
    assert validator_default._strict_validation is False

    validator_strict = ServiceCallValidator(hass, strict_service_validation=True)
    assert validator_strict._strict_validation is True

