"""Data models for Autodoctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, TypedDict


class AutodoctorData(TypedDict, total=False):
    """Typed structure for hass.data[DOMAIN]."""

    knowledge_base: Any
    analyzer: Any
    validator: Any
    jinja_validator: Any
    service_validator: Any
    reporter: Any
    suppression_store: Any
    learned_states_store: Any
    issues: list[Any]
    validation_issues: list[Any]
    validation_last_run: Any
    entry: Any
    debounce_task: Any
    unsub_reload_listener: Any


@dataclass
class ValidationConfig:
    """Configuration for validation behavior.

    Single source of truth for all validation config, passed to validators.
    """

    strict_template_validation: bool = False
    strict_service_validation: bool = False
    history_days: int = 30
    validate_on_reload: bool = True
    debounce_seconds: int = 5


class Severity(IntEnum):
    """Issue severity levels."""

    INFO = 1
    WARNING = 2
    ERROR = 3


class IssueType(str, Enum):
    """Types of validation issues."""

    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_REMOVED = "entity_removed"
    INVALID_STATE = "invalid_state"
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"
    TEMPLATE_SYNTAX_ERROR = "template_syntax_error"
    TEMPLATE_UNKNOWN_FILTER = "template_unknown_filter"
    TEMPLATE_UNKNOWN_TEST = "template_unknown_test"
    TEMPLATE_INVALID_ARGUMENTS = "template_invalid_arguments"
    TEMPLATE_UNKNOWN_VARIABLE = "template_unknown_variable"
    TEMPLATE_INVALID_ENTITY_ID = "template_invalid_entity_id"
    SERVICE_NOT_FOUND = "service_not_found"
    SERVICE_MISSING_REQUIRED_PARAM = "service_missing_required_param"
    SERVICE_INVALID_PARAM_TYPE = "service_invalid_param_type"
    SERVICE_UNKNOWN_PARAM = "service_unknown_param"

    # NEW: HA-specific semantic errors
    TEMPLATE_ENTITY_NOT_FOUND = "template_entity_not_found"
    TEMPLATE_INVALID_STATE = "template_invalid_state"
    TEMPLATE_ATTRIBUTE_NOT_FOUND = "template_attribute_not_found"
    TEMPLATE_DEVICE_NOT_FOUND = "template_device_not_found"
    TEMPLATE_AREA_NOT_FOUND = "template_area_not_found"
    TEMPLATE_ZONE_NOT_FOUND = "template_zone_not_found"



@dataclass
class StateReference:
    """A reference to an entity state found in an automation."""

    automation_id: str
    automation_name: str
    entity_id: str
    expected_state: str | None
    expected_attribute: str | None
    location: str  # e.g., "trigger[0].to", "condition[1].state"
    source_line: int | None = None
    transition_from: str | None = None
    # Type of reference: direct entity, group, device, area, or integration
    reference_type: str = "direct"


@dataclass
class ValidationIssue:
    """An issue found during validation."""

    severity: Severity
    automation_id: str
    automation_name: str
    entity_id: str
    location: str
    message: str
    issue_type: IssueType | None = None
    suggestion: str | None = None
    valid_states: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((self.automation_id, self.issue_type, self.entity_id, self.location, self.message))

    def __eq__(self, other: object) -> bool:
        """Equality based on key fields for deduplication."""
        if not isinstance(other, ValidationIssue):
            return NotImplemented
        return (
            self.automation_id == other.automation_id
            and self.issue_type == other.issue_type
            and self.entity_id == other.entity_id
            and self.location == other.location
            and self.message == other.message
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "issue_type": self.issue_type.value if self.issue_type else None,
            "severity": self.severity.name.lower(),
            "automation_id": self.automation_id,
            "automation_name": self.automation_name,
            "entity_id": self.entity_id,
            "location": self.location,
            "message": self.message,
            "suggestion": self.suggestion,
            "valid_states": self.valid_states,
        }

    def get_suppression_key(self) -> str:
        """Generate a unique key for suppressing this issue."""
        issue_type = self.issue_type.value if self.issue_type else "unknown"
        return f"{self.automation_id}:{self.entity_id}:{issue_type}"


@dataclass
class ServiceCall:
    """A service call found in an automation action."""

    automation_id: str
    automation_name: str
    service: str
    location: str
    target: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    is_template: bool = False
    source_line: int | None = None
