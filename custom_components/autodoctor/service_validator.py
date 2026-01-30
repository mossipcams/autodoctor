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

# Known entity-capability-dependent parameters that may not appear in service schemas
# These are valid parameters but depend on the target entity's capabilities
_CAPABILITY_DEPENDENT_PARAMS: dict[str, frozenset[str]] = {
    "light.turn_on": frozenset({
        "brightness", "brightness_pct", "brightness_step", "brightness_step_pct",
        "color_temp", "color_temp_kelvin", "kelvin",
        "hs_color", "rgb_color", "rgbw_color", "rgbww_color", "xy_color",
        "color_name", "white", "profile", "flash", "effect", "transition"
    }),
    "light.turn_off": frozenset({"transition", "flash"}),
    "climate.set_temperature": frozenset({
        "temperature", "target_temp_high", "target_temp_low"
    }),
    "climate.set_hvac_mode": frozenset({"hvac_mode"}),
    "cover.set_cover_position": frozenset({"position"}),
    "cover.set_cover_tilt_position": frozenset({"tilt_position"}),
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
                # Check if this is a known capability-dependent parameter
                capability_params = _CAPABILITY_DEPENDENT_PARAMS.get(call.service, frozenset())
                if param_name in capability_params:
                    continue

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

                    if valid_values:
                        # Check if selector allows multiple values
                        is_multiple = select_config.get("multiple", False)

                        # For list parameters with multiple=True, validate each item
                        if is_multiple and isinstance(value, list):
                            invalid_items = [v for v in value if v not in valid_values]
                            if invalid_items:
                                return ValidationIssue(
                                    severity=Severity.WARNING,
                                    automation_id=call.automation_id,
                                    automation_name=call.automation_name,
                                    entity_id="",
                                    location=call.location,
                                    message=(
                                        f"Parameter '{param_name}' has invalid items {invalid_items} "
                                        f"for service '{call.service}'. "
                                        f"Valid options: {valid_values}"
                                    ),
                                    issue_type=IssueType.SERVICE_INVALID_PARAM_TYPE,
                                )
                        # For single values, check directly
                        elif value not in valid_values:
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
