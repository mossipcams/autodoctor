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

# Entity-capability-dependent parameters that may not appear in service schemas.
#
# Home Assistant service descriptions advertise a base set of fields, but many
# parameters only apply when the target entity supports a specific capability
# (e.g. brightness for dimmable lights, color_temp for color-capable lights).
# These parameters are valid but absent from the schema, so strict unknown-param
# checking would false-positive on them.
#
# **Maintenance:** When adding a new service/domain, group entries under a domain
# comment and list every capability-dependent parameter that HA documents for that
# service.  Do NOT add parameters that are always in the schema -- only those that
# are conditionally present based on entity features.
_CAPABILITY_DEPENDENT_PARAMS: dict[str, frozenset[str]] = {
    # --- Light ---
    "light.turn_on": frozenset({
        "brightness", "brightness_pct", "brightness_step", "brightness_step_pct",
        "color_temp", "color_temp_kelvin", "kelvin",
        "hs_color", "rgb_color", "rgbw_color", "rgbww_color", "xy_color",
        "color_name", "white", "profile", "flash", "effect", "transition",
    }),
    "light.turn_off": frozenset({"transition", "flash"}),
    # --- Climate ---
    "climate.set_temperature": frozenset({
        "temperature", "target_temp_high", "target_temp_low",
    }),
    "climate.set_hvac_mode": frozenset({"hvac_mode"}),
    # --- Cover ---
    "cover.set_cover_position": frozenset({"position"}),
    "cover.set_cover_tilt_position": frozenset({"tilt_position"}),
    # --- Media player ---
    "media_player.play_media": frozenset({
        "media_content_id", "media_content_type", "enqueue", "announce",
    }),
    "media_player.select_source": frozenset({"source"}),
    "media_player.select_sound_mode": frozenset({"sound_mode"}),
    # --- Fan ---
    "fan.set_percentage": frozenset({"percentage"}),
    "fan.set_preset_mode": frozenset({"preset_mode"}),
    "fan.set_direction": frozenset({"direction"}),
    "fan.oscillate": frozenset({"oscillating"}),
    # --- Vacuum ---
    "vacuum.send_command": frozenset({"command", "params"}),
    # --- Alarm control panel ---
    "alarm_control_panel.alarm_arm_away": frozenset({"code"}),
    "alarm_control_panel.alarm_arm_home": frozenset({"code"}),
    "alarm_control_panel.alarm_arm_night": frozenset({"code"}),
    "alarm_control_panel.alarm_arm_vacation": frozenset({"code"}),
    "alarm_control_panel.alarm_disarm": frozenset({"code"}),
    "alarm_control_panel.alarm_trigger": frozenset({"code"}),
    # --- Number ---
    "number.set_value": frozenset({"value"}),
    # --- Input text ---
    "input_text.set_value": frozenset({"value"}),
    # --- Input number ---
    "input_number.set_value": frozenset({"value"}),
    # --- Input select ---
    "input_select.select_option": frozenset({"option"}),
    # --- Input datetime ---
    "input_datetime.set_datetime": frozenset({
        "date", "time", "datetime", "timestamp",
    }),
    # --- Select ---
    "select.select_option": frozenset({"option"}),
    # --- Text ---
    "text.set_value": frozenset({"value"}),
    # --- Lock ---
    "lock.lock": frozenset({"code"}),
    "lock.unlock": frozenset({"code"}),
    "lock.open": frozenset({"code"}),
    # --- Siren ---
    "siren.turn_on": frozenset({"tone", "volume_level", "duration"}),
    # --- Remote ---
    "remote.send_command": frozenset({
        "command", "device", "delay_secs", "num_repeats",
    }),
    # --- TTS ---
    "tts.speak": frozenset({"message", "cache", "language", "options"}),
    # --- Humidifier ---
    "humidifier.set_humidity": frozenset({"humidity"}),
    "humidifier.set_mode": frozenset({"mode"}),
    # --- Water heater ---
    "water_heater.set_temperature": frozenset({"temperature"}),
    "water_heater.set_operation_mode": frozenset({"operation_mode"}),
}


def _is_template_value(value: Any) -> bool:
    """Check if a value contains Jinja2 template syntax."""
    return isinstance(value, str) and ("{{" in value or "{%" in value)


class ServiceCallValidator:
    """Validates service calls against the Home Assistant service registry."""

    def __init__(
        self,
        hass: HomeAssistant,
        strict_service_validation: bool = False,
    ) -> None:
        """Initialize the service call validator.

        Args:
            hass: Home Assistant instance
            strict_service_validation: If True, warn about unknown service params.
                Disable if using custom components with non-standard params.
        """
        self.hass = hass
        self._strict_validation = strict_service_validation
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
                msg = f"Service '{call.service}' not found"
                suggestion = self._suggest_service(call.service)
                if suggestion:
                    msg += f". Did you mean '{suggestion}'?"
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    automation_id=call.automation_id,
                    automation_name=call.automation_name,
                    entity_id="",
                    location=call.location,
                    message=msg,
                    issue_type=IssueType.SERVICE_NOT_FOUND,
                    suggestion=suggestion,
                ))
                continue

            # Get field definitions for parameter validation
            fields = self._get_service_fields(domain, service)
            if fields is None:
                # No descriptions available, skip parameter validation
                continue

            # Validate target entity IDs
            issues.extend(self._validate_target_entities(call))

            # Validate parameters
            issues.extend(self._validate_required_params(call, fields))
            # Unknown param checking is opt-in — custom components may
            # add service params that don't appear in the schema
            if self._strict_validation:
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
        target = call.target or {}

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

        # Check target dict for non-standard keys
        for param_name in target:
            if param_name not in _TARGET_FIELDS:
                suggestion = self._suggest_param(
                    param_name, list(_TARGET_FIELDS)
                )
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    automation_id=call.automation_id,
                    automation_name=call.automation_name,
                    entity_id="",
                    location=call.location,
                    message=(
                        f"Unknown target key '{param_name}' "
                        f"for service '{call.service}'. "
                        f"Valid target keys: {sorted(_TARGET_FIELDS)}"
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
        """Check if a value matches the expected selector type.

        Only validates select options (discrete enums) as these are
        deterministic. Basic type checking (number, boolean, text) is
        skipped due to YAML type coercion making it unreliable.
        """
        # Only validate select options (discrete enum — high confidence)
        if "select" not in selector:
            return None

        select_config = selector["select"]
        if not isinstance(select_config, dict):
            return None

        options = select_config.get("options", [])
        if not options or not isinstance(options, list):
            return None

        # Normalize options — they can be strings or dicts with 'value' key
        valid_values = []
        for opt in options:
            if isinstance(opt, str):
                valid_values.append(opt)
            elif isinstance(opt, dict) and "value" in opt:
                valid_values.append(opt["value"])

        if not valid_values:
            return None

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

    def _validate_target_entities(
        self,
        call: ServiceCall,
    ) -> list[ValidationIssue]:
        """Validate entity IDs in the target dict exist."""
        issues: list[ValidationIssue] = []
        target = call.target or {}
        entity_ids = target.get("entity_id")
        if entity_ids is None:
            return issues

        # Normalize to list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        elif not isinstance(entity_ids, list):
            return issues

        for entity_id in entity_ids:
            if not isinstance(entity_id, str):
                continue
            # Skip templated entity IDs
            if "{{" in entity_id or "{%" in entity_id:
                continue
            if self.hass.states.get(entity_id) is None:
                suggestion = self._suggest_target_entity(entity_id)
                msg = f"Entity '{entity_id}' in service target does not exist"
                if suggestion:
                    msg += f". Did you mean '{suggestion}'?"
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    automation_id=call.automation_id,
                    automation_name=call.automation_name,
                    entity_id=entity_id,
                    location=call.location,
                    message=msg,
                    issue_type=IssueType.SERVICE_TARGET_NOT_FOUND,
                    suggestion=suggestion,
                ))
        return issues

    def _suggest_target_entity(self, invalid: str) -> str | None:
        """Suggest a correction for an invalid entity ID in target."""
        if "." not in invalid:
            return None
        domain, name = invalid.split(".", 1)
        same_domain = [
            s.entity_id
            for s in self.hass.states.async_all()
            if s.entity_id.startswith(f"{domain}.")
        ]
        if not same_domain:
            return None
        names = {eid.split(".", 1)[1]: eid for eid in same_domain}
        matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)
        return names[matches[0]] if matches else None

    def _suggest_param(
        self, invalid: str, valid_params: list[str]
    ) -> str | None:
        """Suggest a correction for an unknown parameter name."""
        matches = get_close_matches(invalid, valid_params, n=1, cutoff=0.75)
        return matches[0] if matches else None

    def _suggest_service(self, invalid_service: str) -> str | None:
        """Suggest a correction for an unknown service name.

        Looks up services in the same domain and uses fuzzy matching
        to find the closest service name.
        """
        if "." not in invalid_service:
            return None
        domain, service = invalid_service.split(".", 1)
        domain_services = list(
            self.hass.services.async_services().get(domain, {}).keys()
        )
        if not domain_services:
            return None
        matches = get_close_matches(service, domain_services, n=1, cutoff=0.6)
        return f"{domain}.{matches[0]}" if matches else None
