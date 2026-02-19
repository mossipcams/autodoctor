"""Data models for Autodoctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class Severity(IntEnum):
    """Issue severity levels."""

    INFO = 1
    WARNING = 2
    ERROR = 3


class IssueType(StrEnum):
    """Types of validation issues.

    Note: TEMPLATE_UNKNOWN_VARIABLE was removed in v2.7.0 due to high false
    positive rate with blueprint automations that define variables dynamically.
    """

    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_REMOVED = "entity_removed"
    INVALID_STATE = "invalid_state"
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"
    INVALID_ATTRIBUTE_VALUE = "invalid_attribute_value"
    TEMPLATE_SYNTAX_ERROR = "template_syntax_error"
    TEMPLATE_UNKNOWN_FILTER = "template_unknown_filter"
    TEMPLATE_UNKNOWN_TEST = "template_unknown_test"
    SERVICE_NOT_FOUND = "service_not_found"
    SERVICE_MISSING_REQUIRED_PARAM = "service_missing_required_param"
    SERVICE_INVALID_PARAM_TYPE = "service_invalid_param_type"
    SERVICE_UNKNOWN_PARAM = "service_unknown_param"
    SERVICE_TARGET_NOT_FOUND = "service_target_not_found"
    RUNTIME_AUTOMATION_SILENT = "runtime_automation_silent"
    RUNTIME_AUTOMATION_OVERACTIVE = "runtime_automation_overactive"
    RUNTIME_AUTOMATION_BURST = "runtime_automation_burst"


@dataclass
class StateReference:
    """A reference to an entity state found in an automation."""

    automation_id: str
    automation_name: str
    entity_id: str
    expected_state: str | None
    expected_attribute: str | None
    location: str  # e.g., "trigger[0].to", "condition[1].state"
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
    confidence: str = "high"
    suggestion: str | None = None
    valid_states: list[str] = field(default_factory=lambda: list[str]())

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash(
            (
                self.automation_id,
                self.issue_type,
                self.entity_id,
                self.location,
                self.message,
            )
        )

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
            "confidence": self.confidence,
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


# Validation group definitions: maps group ID to label and member IssueTypes.
# All IssueType enum members must appear in exactly one group.
VALIDATION_GROUPS: dict[str, dict[str, str | frozenset[IssueType]]] = {
    "entity_state": {
        "label": "Entity & State",
        "issue_types": frozenset(
            {
                IssueType.ENTITY_NOT_FOUND,
                IssueType.ENTITY_REMOVED,
                IssueType.INVALID_STATE,
                IssueType.CASE_MISMATCH,
                IssueType.ATTRIBUTE_NOT_FOUND,
                IssueType.INVALID_ATTRIBUTE_VALUE,
            }
        ),
    },
    "services": {
        "label": "Service Calls",
        "issue_types": frozenset(
            {
                IssueType.SERVICE_NOT_FOUND,
                IssueType.SERVICE_MISSING_REQUIRED_PARAM,
                IssueType.SERVICE_INVALID_PARAM_TYPE,
                IssueType.SERVICE_UNKNOWN_PARAM,
                IssueType.SERVICE_TARGET_NOT_FOUND,
            }
        ),
    },
    "templates": {
        "label": "Templates",
        "issue_types": frozenset(
            {
                IssueType.TEMPLATE_SYNTAX_ERROR,
                IssueType.TEMPLATE_UNKNOWN_FILTER,
                IssueType.TEMPLATE_UNKNOWN_TEST,
            }
        ),
    },
    "runtime_health": {
        "label": "Runtime Health",
        "issue_types": frozenset(
            {
                IssueType.RUNTIME_AUTOMATION_SILENT,
                IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
                IssueType.RUNTIME_AUTOMATION_BURST,
            }
        ),
    },
}

# Canonical group ordering for response serialization
VALIDATION_GROUP_ORDER: list[str] = [
    "entity_state",
    "services",
    "templates",
    "runtime_health",
]
