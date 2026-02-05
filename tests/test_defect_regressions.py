"""Regression tests for P0/P1 defects found in architectural review.

Tests cover:
- P0 #1: async_validate_automation must update hass.data[DOMAIN] state
- P1 #4: Template string as call.data must not crash service validator
- P1 #3: Template in one field must not skip checks for other required fields
- P1 #11: Entity cache must recover after transient errors
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor import async_validate_automation
from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import (
    IssueType,
    ServiceCall,
    Severity,
    ValidationIssue,
)
from custom_components.autodoctor.service_validator import ServiceCallValidator
from custom_components.autodoctor.validator import ValidationEngine


def _make_issue(
    issue_type: IssueType,
    severity: Severity,
    automation_id: str = "automation.test",
    entity_id: str = "light.test",
) -> ValidationIssue:
    """Create a minimal ValidationIssue for testing."""
    return ValidationIssue(
        severity=severity,
        automation_id=automation_id,
        automation_name="Test",
        entity_id=entity_id,
        location="trigger[0]",
        message=f"Test issue: {issue_type.value}",
        issue_type=issue_type,
    )


@pytest.fixture
def grouped_hass() -> MagicMock:
    """Create mock hass with all validators pre-configured."""
    hass = MagicMock()
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_reporter = AsyncMock()
    mock_jinja = MagicMock()
    mock_service = MagicMock()
    mock_service.async_load_descriptions = AsyncMock()

    hass.data = {
        DOMAIN: {
            "analyzer": mock_analyzer,
            "validator": mock_validator,
            "reporter": mock_reporter,
            "jinja_validator": mock_jinja,
            "service_validator": mock_service,
            "knowledge_base": None,
            "issues": [],
            "validation_issues": [],
            "validation_last_run": None,
        }
    }

    return hass


@pytest.mark.asyncio
async def test_validate_automation_updates_hass_data(grouped_hass: MagicMock) -> None:
    """Test that async_validate_automation updates hass.data[DOMAIN] state.

    After single-automation re-validation, the WebSocket API must serve
    fresh data. This requires hass.data to be updated with the new issues
    and timestamp. Without this, the frontend shows stale results.
    """
    issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        await async_validate_automation(grouped_hass, "automation.test")

    # hass.data MUST be updated with the new issues
    domain_data = grouped_hass.data[DOMAIN]
    assert len(domain_data["validation_issues"]) == 1
    assert domain_data["validation_issues"][0] is issue
    assert domain_data["validation_last_run"] is not None


# === P1 #4: Template string as call.data must not crash ===


async def test_template_string_data_does_not_crash(hass: HomeAssistant) -> None:
    """Test that a service call with template string as data doesn't crash.

    When analyzer extracts a service call where data is a Jinja2 template
    string (not a dict), the validator must handle it gracefully instead
    of crashing on data.values().
    """
    validator = ServiceCallValidator(hass)

    async def dummy(call: Any) -> None:
        pass

    hass.services.async_register("light", "turn_on", dummy)

    # Inject service descriptions so we reach parameter validation code
    validator._service_descriptions = {
        "light": {
            "turn_on": {
                "fields": {
                    "brightness": {"selector": {"number": {}}},
                }
            }
        }
    }

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        data="{{ states.light.template_data }}",  # type: ignore[arg-type]
    )

    # Must not raise AttributeError on str.values()
    issues = validator.validate_service_calls([call])
    assert isinstance(issues, list)


# === P1 #3: Template in one field must not skip checks for other required fields ===


async def test_template_in_one_field_does_not_skip_other_required_params(
    hass: HomeAssistant,
) -> None:
    """Test that a template value in one field doesn't skip checks for other fields.

    If data has {field_a: '{{ template }}'} but missing required field_b,
    the template in field_a should not cause missing field_b to be skipped.
    """
    validator = ServiceCallValidator(hass)

    async def dummy(call: Any) -> None:
        pass

    hass.services.async_register("test", "svc", dummy)

    validator._service_descriptions = {
        "test": {
            "svc": {
                "fields": {
                    "field_a": {"required": True, "selector": {"text": {}}},
                    "field_b": {"required": True, "selector": {"text": {}}},
                }
            }
        }
    }

    # field_a is a template, field_b is entirely missing
    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="test.svc",
        location="action[0]",
        data={"field_a": "{{ some_template }}"},
    )

    issues = validator.validate_service_calls([call])
    missing = [
        i for i in issues if i.issue_type == IssueType.SERVICE_MISSING_REQUIRED_PARAM
    ]
    # field_b is required and NOT provided — must be flagged
    assert len(missing) == 1
    assert "field_b" in missing[0].message


# === P1 #11: Entity cache must recover after transient errors ===


async def test_entity_cache_recovers_after_error(hass: HomeAssistant) -> None:
    """Test that entity cache rebuilds after a transient error.

    If _ensure_entity_cache() fails on first call, subsequent calls
    must retry building the cache rather than permanently serving an
    empty cache.
    """
    kb = StateKnowledgeBase(hass)
    engine = ValidationEngine(kb)

    # First call: simulate error during cache building by temporarily
    # replacing hass with a mock that raises on async_all
    mock_hass = MagicMock()
    mock_hass.states.async_all.side_effect = RuntimeError("transient error")
    engine.knowledge_base = MagicMock()
    engine.knowledge_base.hass = mock_hass
    engine._ensure_entity_cache()

    # Cache should NOT be permanently locked to empty — must allow retry
    # Second call: restore real hass with an actual entity
    engine.knowledge_base.hass = hass
    hass.states.async_set("light.kitchen", "on")
    engine._ensure_entity_cache()

    assert engine._entity_cache is not None
    assert "light" in engine._entity_cache
    assert "light.kitchen" in engine._entity_cache["light"]
