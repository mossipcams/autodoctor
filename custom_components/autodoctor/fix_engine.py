"""FixEngine - generates fix suggestions for validation issues."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from typing import TYPE_CHECKING

from .models import ValidationIssue, IssueType

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .knowledge_base import StateKnowledgeBase
    from .entity_graph import EntityGraph
    from .suggestion_learner import SuggestionLearner

# Threshold for suggesting entity fixes
# With scoring weights (fuzzy=0.3, relationship=0.5, service=0.2):
# - A good typo match (~0.95 similarity) with domain match (0.2 rel) gives ~0.59
# - A perfect match with device match (0.6 rel) gives 0.7
SUGGESTION_THRESHOLD = 0.5


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
    reasoning: str | None = None  # Why this suggestion was chosen


class FixEngine:
    """Generates fix suggestions for validation issues."""

    def __init__(
        self,
        hass: HomeAssistant,
        knowledge_base: StateKnowledgeBase,
        entity_graph: EntityGraph | None = None,
        suggestion_learner: SuggestionLearner | None = None,
    ) -> None:
        """Initialize the fix engine."""
        self.hass = hass
        self.knowledge_base = knowledge_base
        self._entity_graph = entity_graph
        self._suggestion_learner = suggestion_learner

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
        if "." not in issue.entity_id:
            return None

        domain, name = issue.entity_id.split(".", 1)

        # Only consider entities in the same domain
        all_entities = self.hass.states.async_all()
        same_domain = [
            e.entity_id for e in all_entities
            if e.entity_id.startswith(f"{domain}.")
        ]

        if not same_domain:
            return None

        # Use smart scoring if entity_graph or suggestion_learner available
        if self._entity_graph is not None or self._suggestion_learner is not None:
            # Score all candidates
            scored_candidates: list[tuple[str, float, str]] = []
            for candidate in same_domain:
                score, reasoning = self._calculate_entity_score(
                    issue.entity_id, candidate
                )
                scored_candidates.append((candidate, score, reasoning))

            # Sort by score descending
            scored_candidates.sort(key=lambda x: x[1], reverse=True)

            # Get best match above threshold
            if scored_candidates and scored_candidates[0][1] >= SUGGESTION_THRESHOLD:
                best_entity, best_score, reasoning = scored_candidates[0]
                return FixSuggestion(
                    description=f"Did you mean '{best_entity}'?",
                    confidence=best_score,
                    fix_value=best_entity,
                    field_path="entity_id",
                    reasoning=reasoning,
                )
            return None

        # Fallback: Match on name portion only with higher threshold
        names = {eid.split(".", 1)[1]: eid for eid in same_domain}
        matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

        if matches:
            matched_entity = names[matches[0]]
            similarity = self._calculate_similarity(name, matches[0])
            return FixSuggestion(
                description=f"Did you mean '{matched_entity}'?",
                confidence=similarity,
                fix_value=matched_entity,
                field_path="entity_id",
                reasoning="String similarity",
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

    def _calculate_entity_score(
        self, reference: str, candidate: str
    ) -> tuple[float, str]:
        """Calculate combined score for entity suggestion.

        Returns (score, reasoning).

        Scoring weights:
        - String similarity: 30%
        - Relationship score: 50%
        - Service compatibility: 20% (placeholder)
        """
        reasons: list[str] = []

        # Extract name portions for string comparison
        ref_name = reference.split(".", 1)[1] if "." in reference else reference
        cand_name = candidate.split(".", 1)[1] if "." in candidate else candidate

        # String similarity (30% weight)
        fuzzy_score = self._calculate_similarity(ref_name, cand_name)

        # Relationship score (50% weight)
        relationship_score = 0.0
        if self._entity_graph:
            relationship_score = self._entity_graph.relationship_score(
                reference, candidate
            )
            if self._entity_graph.same_device(reference, candidate):
                reasons.append("Same device")
            elif self._entity_graph.same_area(reference, candidate):
                reasons.append("Same area")
            elif self._entity_graph.same_domain(reference, candidate):
                # Domain is already filtered, so don't add to reasons
                pass

        # Service compatibility (20% weight) - placeholder for future
        service_score = 0.2

        # Calculate base score
        base_score = fuzzy_score * 0.3 + relationship_score * 0.5 + service_score

        # Apply learning penalty
        if self._suggestion_learner:
            multiplier = self._suggestion_learner.get_score_multiplier(
                reference, candidate
            )
            if multiplier < 1.0:
                reasons.append("Penalized (previously rejected)")
            base_score *= multiplier

        # Build reasoning string
        if not reasons:
            reasons.append("String similarity")

        return base_score, ", ".join(reasons)

    def _extract_invalid_state(self, message: str) -> str | None:
        """Extract the invalid state value from an error message."""
        # Pattern: "State 'away' is not valid"
        import re
        match = re.search(r"[Ss]tate ['\"]([^'\"]+)['\"]", message)
        return match.group(1) if match else None
