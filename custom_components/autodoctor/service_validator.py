"""Validates service calls against Home Assistant service registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import IssueType, Severity, ValidationIssue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .models import ServiceCall


class ServiceCallValidator:
    """Validates service calls against the Home Assistant service registry."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the service call validator."""
        self.hass = hass

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

        return issues
