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
