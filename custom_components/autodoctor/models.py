"""Data models for Autodoctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


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
    IMPOSSIBLE_CONDITION = "impossible_condition"
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"
    TEMPLATE_SYNTAX_ERROR = "template_syntax_error"


@dataclass
class TriggerInfo:
    """Simplified trigger representation for conflict detection."""

    trigger_type: str  # "state", "time", "sun", "other"
    entity_id: str | None
    to_states: set[str] | None
    time_value: str | None  # "06:00:00" or None
    sun_event: str | None  # "sunrise", "sunset", or None


@dataclass
class ConditionInfo:
    """Simplified condition representation for conflict detection."""

    entity_id: str
    required_states: set[str]


@dataclass
class EntityAction:
    """An action that affects an entity, extracted from an automation."""

    automation_id: str
    entity_id: str
    action: str  # "turn_on", "turn_off", "toggle", "set"
    value: Any  # For set actions (brightness, temperature, etc.)
    conditions: list[ConditionInfo]  # Conditions that must be true for this action


@dataclass
class Conflict:
    """A detected conflict between two automations."""

    entity_id: str
    automation_a: str
    automation_b: str
    automation_a_name: str
    automation_b_name: str
    action_a: str
    action_b: str
    severity: Severity
    explanation: str
    scenario: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "entity_id": self.entity_id,
            "automation_a": self.automation_a,
            "automation_b": self.automation_b,
            "automation_a_name": self.automation_a_name,
            "automation_b_name": self.automation_b_name,
            "action_a": self.action_a,
            "action_b": self.action_b,
            "severity": self.severity.name.lower(),
            "explanation": self.explanation,
            "scenario": self.scenario,
        }

    def get_suppression_key(self) -> str:
        """Generate a unique key for suppressing this conflict."""
        # Sort automation IDs for consistent key regardless of order
        auto_ids = sorted([self.automation_a, self.automation_b])
        return f"{auto_ids[0]}:{auto_ids[1]}:{self.entity_id}:conflict"


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
        return hash((self.automation_id, self.issue_type, self.entity_id, self.message))

    def __eq__(self, other: object) -> bool:
        """Equality based on key fields for deduplication."""
        if not isinstance(other, ValidationIssue):
            return NotImplemented
        return (
            self.automation_id == other.automation_id
            and self.issue_type == other.issue_type
            and self.entity_id == other.entity_id
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
