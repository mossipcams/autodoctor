"""Data models for Autodoctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, auto


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
    suggestion: str | None = None
    valid_states: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((self.automation_id, self.entity_id, self.location, self.message))


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
