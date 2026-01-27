"""FixEngine - generates fix suggestions for validation issues."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from typing import TYPE_CHECKING

from .models import ValidationIssue, IssueType

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .knowledge_base import StateKnowledgeBase


# Semantic mappings for common state synonyms
STATE_SYNONYMS: dict[str, str] = {
    "away": "not_home",
    "gone": "not_home",
    "absent": "not_home",
    "present": "home",
    "arrived": "home",
    "true": "on",
    "false": "off",
    "yes": "on",
    "no": "off",
    "enabled": "on",
    "disabled": "off",
    "active": "on",
    "inactive": "off",
    "open": "on",
    "closed": "off",
    "opened": "on",
}


@dataclass
class FixSuggestion:
    """A suggested fix for a validation issue."""

    description: str
    confidence: float  # 0.0 - 1.0
    fix_value: str | None
    field_path: str | None = None


class FixEngine:
    """Generates fix suggestions for validation issues."""

    def __init__(self, hass: HomeAssistant, knowledge_base: StateKnowledgeBase) -> None:
        """Initialize the fix engine."""
        self.hass = hass
        self.knowledge_base = knowledge_base

    def suggest_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Generate a fix suggestion for an issue."""
        if issue.issue_type == IssueType.ENTITY_NOT_FOUND:
            return self._suggest_entity_fix(issue)
        elif issue.issue_type == IssueType.ENTITY_REMOVED:
            return self._suggest_entity_fix(issue)
        elif issue.issue_type == IssueType.INVALID_STATE:
            return self._suggest_state_fix(issue)
        elif issue.issue_type == IssueType.IMPOSSIBLE_CONDITION:
            return self._suggest_condition_fix(issue)
        return None

    def _suggest_entity_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for missing entity."""
        all_entities = [s.entity_id for s in self.hass.states.async_all()]
        matches = get_close_matches(issue.entity_id, all_entities, n=1, cutoff=0.6)

        if matches:
            similarity = self._calculate_similarity(issue.entity_id, matches[0])
            return FixSuggestion(
                description=f"Did you mean '{matches[0]}'?",
                confidence=similarity,
                fix_value=matches[0],
                field_path="entity_id",
            )
        return None

    def _suggest_state_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for invalid state."""
        if not issue.valid_states:
            return None

        # Extract the invalid state from the message
        invalid_state = self._extract_invalid_state(issue.message)
        if not invalid_state:
            return None

        # First, check semantic synonyms
        synonym = STATE_SYNONYMS.get(invalid_state.lower())
        if synonym and synonym in issue.valid_states:
            return FixSuggestion(
                description=f"Did you mean '{synonym}'?",
                confidence=0.9,  # High confidence for semantic match
                fix_value=synonym,
                field_path="state",
            )

        # Fall back to fuzzy matching for typos
        matches = get_close_matches(invalid_state, issue.valid_states, n=1, cutoff=0.4)
        if matches:
            similarity = self._calculate_similarity(invalid_state, matches[0])
            return FixSuggestion(
                description=f"Did you mean '{matches[0]}'?",
                confidence=similarity,
                fix_value=matches[0],
                field_path="state",
            )
        return None

    def _suggest_condition_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for impossible condition."""
        if issue.suggestion:
            return FixSuggestion(
                description=f"Change condition state to '{issue.suggestion}'",
                confidence=0.95,
                fix_value=issue.suggestion,
                field_path="condition.state",
            )
        return None

    def _calculate_similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _extract_invalid_state(self, message: str) -> str | None:
        """Extract the invalid state value from an error message."""
        # Pattern: "State 'away' is not valid"
        import re
        match = re.search(r"[Ss]tate ['\"]([^'\"]+)['\"]", message)
        return match.group(1) if match else None
