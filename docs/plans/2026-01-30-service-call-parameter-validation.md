# Service Call Parameter Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `extract_service_calls` fully recursive and expand `ServiceCallValidator` to validate required params, unknown params, and param types against the HA service registry.

**Architecture:** Refactor `extract_service_calls` in `analyzer.py` to recurse into choose/default, if/then/else, repeat/sequence, and parallel — mirroring `_extract_from_actions`. Expand `ServiceCallValidator` in `service_validator.py` to fetch service descriptions via `homeassistant.helpers.service.async_get_all_descriptions(hass)`, which returns `dict[str, dict[str, Any]]` with field metadata including `required`, `selector`, `name`. Add three new validation checks using the existing `IssueType` enum values that are already defined but not implemented.

**Tech Stack:** Python, pytest, homeassistant core APIs (`hass.services.has_service`, `homeassistant.helpers.service.async_get_all_descriptions`)

---

### Task 1: Write failing tests for recursive service call extraction

**Files:**
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add these tests at the end of `tests/test_analyzer.py`:

```python
def test_extract_service_calls_from_if_then_else():
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


def test_extract_service_calls_from_repeat_sequence():
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


def test_extract_service_calls_from_parallel():
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


def test_extract_service_calls_from_choose_default():
    """Test extracting service calls from choose default branch."""
    automation = {
        "id": "test",
        "alias": "Test",
        "action": [
            {
                "choose": [
                    {
                        "sequence": [{"service": "light.turn_on"}]
                    }
                ],
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


def test_extract_service_calls_deeply_nested():
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
                                "if": [{"condition": "state", "entity_id": "sensor.x", "state": "on"}],
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


def test_extract_service_calls_supports_action_key():
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


def test_extract_service_calls_supports_actions_key():
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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py -k "test_extract_service_calls_from_if or test_extract_service_calls_from_repeat or test_extract_service_calls_from_parallel or test_extract_service_calls_from_choose_default or test_extract_service_calls_deeply_nested or test_extract_service_calls_supports_action or test_extract_service_calls_supports_actions_key" -v`
Expected: FAIL — the current `extract_service_calls` doesn't recurse into if/then/else, repeat, parallel, or choose default.

---

### Task 2: Implement recursive `extract_service_calls`

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:1097-1131`

**Step 3: Refactor `extract_service_calls` to be recursive**

Replace the `extract_service_calls` method (lines 1097-1131) with:

```python
def extract_service_calls(self, automation: dict) -> list[ServiceCall]:
    """Extract all service calls from automation actions."""
    service_calls: list[ServiceCall] = []
    actions = automation.get("actions") or automation.get("action", [])
    if not isinstance(actions, list):
        actions = [actions]

    automation_id = automation.get("id", "unknown")
    automation_name = automation.get("alias", "Unknown")

    self._extract_service_calls_from_actions(
        actions, automation_id, automation_name, service_calls
    )
    return service_calls

def _extract_service_calls_from_actions(
    self,
    actions: list[dict[str, Any]],
    automation_id: str,
    automation_name: str,
    service_calls: list[ServiceCall],
) -> None:
    """Recursively extract service calls from a list of actions."""
    if not isinstance(actions, list):
        actions = [actions]

    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            continue

        # Direct service call (both 'service' and 'action' keys)
        service = action.get("service") or action.get("action")
        if service and isinstance(service, str):
            is_template = "{{" in service or "{%" in service
            service_calls.append(ServiceCall(
                automation_id=automation_id,
                automation_name=automation_name,
                service=service,
                location=f"action[{idx}]",
                target=action.get("target"),
                data=action.get("data"),
                is_template=is_template,
            ))

        # Choose branches
        if "choose" in action:
            options = action.get("choose") or []
            if isinstance(options, list):
                for opt_idx, option in enumerate(options):
                    if isinstance(option, dict):
                        sequence = option.get("sequence", [])
                        self._extract_service_calls_from_actions(
                            sequence, automation_id, automation_name, service_calls
                        )

            # Default branch
            default = action.get("default") or []
            if default:
                self._extract_service_calls_from_actions(
                    default, automation_id, automation_name, service_calls
                )

        # If/then/else
        if "if" in action:
            then_actions = action.get("then", [])
            self._extract_service_calls_from_actions(
                then_actions, automation_id, automation_name, service_calls
            )
            else_actions = action.get("else", [])
            if else_actions:
                self._extract_service_calls_from_actions(
                    else_actions, automation_id, automation_name, service_calls
                )

        # Repeat
        if "repeat" in action:
            repeat_config = action["repeat"]
            if isinstance(repeat_config, dict):
                sequence = repeat_config.get("sequence", [])
                self._extract_service_calls_from_actions(
                    sequence, automation_id, automation_name, service_calls
                )

        # Parallel
        if "parallel" in action:
            branches = action.get("parallel") or []
            if not isinstance(branches, list):
                branches = [branches]
            for branch in branches:
                if isinstance(branch, list):
                    self._extract_service_calls_from_actions(
                        branch, automation_id, automation_name, service_calls
                    )
                elif isinstance(branch, dict):
                    self._extract_service_calls_from_actions(
                        [branch], automation_id, automation_name, service_calls
                    )
```

Note: The `location` field will use the local `idx` within each recursion level. This is acceptable — the existing `_extract_from_actions` method does the same thing. The location gives enough context for debugging.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py -v`
Expected: ALL PASS — including both old and new tests.

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat: make extract_service_calls recursive into all action types"
```

---

### Task 3: Write failing tests for service parameter validation

**Files:**
- Test: `tests/test_service_validator.py`

**Step 6: Write the failing tests**

Add these tests at the end of `tests/test_service_validator.py`:

```python
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


async def test_validate_skips_required_check_when_templated(hass: HomeAssistant):
    """Test that required param check is skipped for templated service calls."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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


async def test_validate_invalid_param_type_number(hass: HomeAssistant):
    """Test validation for invalid parameter type (expected number, got string)."""
    from custom_components.autodoctor.models import ServiceCall, Severity, IssueType

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

    type_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(type_issues) == 1
    assert type_issues[0].severity == Severity.WARNING
    assert "brightness" in type_issues[0].message


async def test_validate_valid_param_type_number(hass: HomeAssistant):
    """Test that valid number type passes."""
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

    type_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(type_issues) == 0


async def test_validate_invalid_param_type_boolean(hass: HomeAssistant):
    """Test validation for invalid parameter type (expected boolean)."""
    from custom_components.autodoctor.models import ServiceCall, IssueType

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

    type_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(type_issues) == 1


async def test_validate_skips_type_check_for_templated_values(hass: HomeAssistant):
    """Test that type validation is skipped for templated values."""
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

    type_issues = [i for i in issues if i.issue_type == IssueType.SERVICE_INVALID_PARAM_TYPE]
    assert len(type_issues) == 0


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

    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {
        "test": {
            "service": {
                "fields": {
                    "required_field": {
                        "required": True,
                        "selector": {"text": {}},
                    },
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
        data={
            "brightness": "not_a_number",  # Wrong type
            "unknown_field": "value",       # Unknown param
            # Missing: required_field
        },
    )

    issues = validator.validate_service_calls([call])

    issue_types = {i.issue_type for i in issues}
    assert IssueType.SERVICE_MISSING_REQUIRED_PARAM in issue_types
    assert IssueType.SERVICE_UNKNOWN_PARAM in issue_types
    assert IssueType.SERVICE_INVALID_PARAM_TYPE in issue_types
```

**Step 7: Run tests to verify they fail**

Run: `pytest tests/test_service_validator.py -v`
Expected: FAIL — `ServiceCallValidator` doesn't have `_service_descriptions` or param validation logic yet.

---

### Task 4: Implement service parameter validation

**Files:**
- Modify: `custom_components/autodoctor/service_validator.py`

**Step 8: Replace service_validator.py with full implementation**

```python
"""Validates service calls against Home Assistant service registry."""

from __future__ import annotations

import logging
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any

from .models import IssueType, Severity, ValidationIssue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .models import ServiceCall

_LOGGER = logging.getLogger(__name__)

# Target fields are separate from data fields
_TARGET_FIELDS = frozenset({"entity_id", "device_id", "area_id"})

# Selector type to Python type mapping
_SELECTOR_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "number": (int, float),
    "boolean": (bool,),
    "text": (str,),
    "object": (dict,),
}


def _is_template_value(value: Any) -> bool:
    """Check if a value contains Jinja2 template syntax."""
    return isinstance(value, str) and ("{{" in value or "{%" in value)


class ServiceCallValidator:
    """Validates service calls against the Home Assistant service registry."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the service call validator."""
        self.hass = hass
        self._service_descriptions: dict[str, dict[str, Any]] | None = None

    async def async_load_descriptions(self) -> None:
        """Load service descriptions from Home Assistant."""
        try:
            from homeassistant.helpers.service import async_get_all_descriptions
            self._service_descriptions = await async_get_all_descriptions(self.hass)
        except Exception as err:
            _LOGGER.warning("Failed to load service descriptions: %s", err)
            self._service_descriptions = None

    def _get_service_fields(
        self, domain: str, service: str
    ) -> dict[str, Any] | None:
        """Get field definitions for a service.

        Returns None if descriptions are unavailable.
        Returns empty dict if service has no fields.
        """
        if self._service_descriptions is None:
            return None

        domain_services = self._service_descriptions.get(domain)
        if domain_services is None:
            return None

        service_desc = domain_services.get(service)
        if service_desc is None:
            return None

        return service_desc.get("fields", {})

    def validate_service_calls(
        self,
        service_calls: list[ServiceCall],
    ) -> list[ValidationIssue]:
        """Validate all service calls and return issues."""
        issues: list[ValidationIssue] = []

        for call in service_calls:
            # Skip templated service names
            if call.is_template:
                continue

            # Parse domain.service
            if "." not in call.service:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    automation_id=call.automation_id,
                    automation_name=call.automation_name,
                    entity_id="",
                    location=call.location,
                    message=f"Invalid service format: '{call.service}' (expected 'domain.service')",
                    issue_type=IssueType.SERVICE_NOT_FOUND,
                ))
                continue

            domain, service = call.service.split(".", 1)

            # Check if service exists
            if not self.hass.services.has_service(domain, service):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    automation_id=call.automation_id,
                    automation_name=call.automation_name,
                    entity_id="",
                    location=call.location,
                    message=f"Service '{call.service}' not found",
                    issue_type=IssueType.SERVICE_NOT_FOUND,
                ))
                continue

            # Get field definitions for parameter validation
            fields = self._get_service_fields(domain, service)
            if fields is None:
                # No descriptions available, skip parameter validation
                continue

            # Validate parameters
            issues.extend(self._validate_required_params(call, fields))
            issues.extend(self._validate_unknown_params(call, fields))
            issues.extend(self._validate_param_types(call, fields))

        return issues

    def _validate_required_params(
        self,
        call: ServiceCall,
        fields: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Check that all required parameters are provided."""
        issues: list[ValidationIssue] = []
        data = call.data or {}
        target = call.target or {}

        # Check if any data value is a template — if so, we can't fully
        # validate required params since templates may produce extra keys
        has_any_template = any(_is_template_value(v) for v in data.values())

        for field_name, field_schema in fields.items():
            if not isinstance(field_schema, dict):
                continue
            if not field_schema.get("required", False):
                continue

            # Check in both data and target
            if field_name in data or field_name in target:
                continue

            # If data has template values, skip — templates may produce this key
            if has_any_template:
                continue

            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                automation_id=call.automation_id,
                automation_name=call.automation_name,
                entity_id="",
                location=call.location,
                message=(
                    f"Missing required parameter '{field_name}' "
                    f"for service '{call.service}'"
                ),
                issue_type=IssueType.SERVICE_MISSING_REQUIRED_PARAM,
            ))

        return issues

    def _validate_unknown_params(
        self,
        call: ServiceCall,
        fields: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Check for parameters not in service schema."""
        issues: list[ValidationIssue] = []
        data = call.data or {}

        # If service has no fields defined at all, skip — it may accept
        # arbitrary extra keys
        if not fields:
            return issues

        for param_name in data:
            # Target fields are always valid in data
            if param_name in _TARGET_FIELDS:
                continue

            if param_name not in fields:
                suggestion = self._suggest_param(param_name, list(fields.keys()))
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    automation_id=call.automation_id,
                    automation_name=call.automation_name,
                    entity_id="",
                    location=call.location,
                    message=(
                        f"Unknown parameter '{param_name}' "
                        f"for service '{call.service}'"
                    ),
                    issue_type=IssueType.SERVICE_UNKNOWN_PARAM,
                    suggestion=suggestion,
                ))

        return issues

    def _validate_param_types(
        self,
        call: ServiceCall,
        fields: dict[str, Any],
    ) -> list[ValidationIssue]:
        """Validate parameter value types match schema selectors."""
        issues: list[ValidationIssue] = []
        data = call.data or {}

        for param_name, value in data.items():
            # Skip templated values
            if _is_template_value(value):
                continue

            # Only check params that exist in the schema
            if param_name not in fields:
                continue

            field_schema = fields[param_name]
            if not isinstance(field_schema, dict):
                continue

            selector = field_schema.get("selector")
            if not selector or not isinstance(selector, dict):
                continue

            issue = self._check_selector_type(call, param_name, value, selector)
            if issue:
                issues.append(issue)

        return issues

    def _check_selector_type(
        self,
        call: ServiceCall,
        param_name: str,
        value: Any,
        selector: dict[str, Any],
    ) -> ValidationIssue | None:
        """Check if a value matches the expected selector type."""
        # Check select options first (more specific)
        if "select" in selector:
            select_config = selector["select"]
            if isinstance(select_config, dict):
                options = select_config.get("options", [])
                if options and isinstance(options, list):
                    # Normalize options — they can be strings or dicts with 'value' key
                    valid_values = []
                    for opt in options:
                        if isinstance(opt, str):
                            valid_values.append(opt)
                        elif isinstance(opt, dict) and "value" in opt:
                            valid_values.append(opt["value"])

                    if valid_values and value not in valid_values:
                        return ValidationIssue(
                            severity=Severity.WARNING,
                            automation_id=call.automation_id,
                            automation_name=call.automation_name,
                            entity_id="",
                            location=call.location,
                            message=(
                                f"Parameter '{param_name}' value '{value}' "
                                f"is not a valid option for service '{call.service}'. "
                                f"Valid options: {valid_values}"
                            ),
                            issue_type=IssueType.SERVICE_INVALID_PARAM_TYPE,
                        )
            return None

        # Check basic type selectors
        for selector_type, expected_types in _SELECTOR_TYPE_MAP.items():
            if selector_type in selector:
                if not isinstance(value, expected_types):
                    return ValidationIssue(
                        severity=Severity.WARNING,
                        automation_id=call.automation_id,
                        automation_name=call.automation_name,
                        entity_id="",
                        location=call.location,
                        message=(
                            f"Parameter '{param_name}' has type "
                            f"'{type(value).__name__}' but expected "
                            f"'{selector_type}' for service '{call.service}'"
                        ),
                        issue_type=IssueType.SERVICE_INVALID_PARAM_TYPE,
                    )
                return None

        # Unknown selector type — skip
        return None

    def _suggest_param(
        self, invalid: str, valid_params: list[str]
    ) -> str | None:
        """Suggest a correction for an unknown parameter name."""
        matches = get_close_matches(invalid, valid_params, n=1, cutoff=0.6)
        return matches[0] if matches else None
```

**Step 9: Run tests to verify they pass**

Run: `pytest tests/test_service_validator.py -v`
Expected: ALL PASS

**Step 10: Commit**

```bash
git add custom_components/autodoctor/service_validator.py tests/test_service_validator.py
git commit -m "feat: add service call parameter validation (required, unknown, type)"
```

---

### Task 5: Wire up async description loading in __init__.py

**Files:**
- Modify: `custom_components/autodoctor/__init__.py:398-413`

**Step 11: Add description loading before validation**

In `__init__.py`, in the service validation block (around line 398-413), add an `await` to load descriptions before validating:

```python
    # Run service call validation
    if service_validator:
        try:
            await service_validator.async_load_descriptions()
            service_calls = []
            for automation in automations:
                service_calls.extend(analyzer.extract_service_calls(automation))

            service_issues = service_validator.validate_service_calls(service_calls)
            all_issues.extend(service_issues)
            _LOGGER.debug(
                "Service validation: found %d issues in %d service calls",
                len(service_issues),
                len(service_calls),
            )
        except Exception as ex:
            _LOGGER.exception("Service validation failed: %s", ex)
```

**Step 12: Run the full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 13: Commit**

```bash
git add custom_components/autodoctor/__init__.py
git commit -m "feat: load service descriptions before parameter validation"
```

---

### Task 6: Verify nothing is broken and update index.md if needed

**Step 14: Run full test suite one more time**

Run: `pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 15: Check if index.md needs updating**

Read `index.md` and verify the service_validator module description still accurately reflects its expanded functionality. If the description says something like "validates service existence", update it to mention parameter validation.

**Step 16: Final commit if index was updated**

```bash
git add index.md
git commit -m "docs: update index.md to reflect expanded service validation"
```

---

## Key Design Decisions

1. **Service descriptions are injected via `_service_descriptions` attribute** — tests set it directly, production code loads via `async_load_descriptions()`. This avoids mocking deep HA internals in tests.

2. **`_TARGET_FIELDS` are always allowed in data** — `entity_id`, `device_id`, `area_id` can appear in `data` for backwards compatibility even though modern HA uses `target`.

3. **Empty fields dict → skip unknown param check** — services with no field definitions may accept arbitrary keys (e.g., `homeassistant.restart`).

4. **Template-aware at every level** — `is_template` on the call skips everything; template values in data skip type checking; template values in data also skip required param checking (templates may produce extra keys).

5. **Severity: ERROR for missing required, WARNING for unknown/type** — matching the design doc and the existing pattern in `models.py`.

6. **`get_close_matches` with cutoff=0.6** — matches the pattern in `validator.py:_suggest_state`.
