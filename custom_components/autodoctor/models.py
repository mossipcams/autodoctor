"""Data models for Autodoctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum, auto
from typing import Any


class Severity(IntEnum):
    """Issue severity levels."""

    INFO = 1
    WARNING = 2
    ERROR = 3


class Verdict(IntEnum):
    """Outcome verification verdicts."""

    ALL_REACHABLE = auto()
    PARTIALLY_REACHABLE = auto()
    UNREACHABLE = auto()


class IssueType(str, Enum):
    """Types of validation issues."""

    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_REMOVED = "entity_removed"
    INVALID_STATE = "invalid_state"
    IMPOSSIBLE_CONDITION = "impossible_condition"
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"


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

    # Historical analysis results (populated by analyzer)
    historical_match: bool = True
    last_seen: datetime | None = None
    transition_from: str | None = None
    transition_valid: bool = True


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
        return hash((self.automation_id, self.entity_id, self.location, self.message))

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


@dataclass
class OutcomeReport:
    """Report on whether automation outcomes are reachable."""

    automation_id: str
    automation_name: str
    triggers_valid: bool
    conditions_reachable: bool
    outcomes: list[str]
    unreachable_paths: list[str]
    verdict: Verdict


def outcome_report_to_issues(report: OutcomeReport) -> list[ValidationIssue]:
    """Convert an OutcomeReport to a list of ValidationIssue objects."""
    if report.verdict == Verdict.ALL_REACHABLE:
        return []

    issues = []
    for path in report.unreachable_paths:
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                automation_id=report.automation_id,
                automation_name=report.automation_name,
                entity_id="",
                location=path,
                message=f"Unreachable outcome: {path}",
                issue_type=IssueType.IMPOSSIBLE_CONDITION,
            )
        )
    return issues
