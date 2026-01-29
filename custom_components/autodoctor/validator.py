"""ValidationEngine - compares state references against knowledge base."""

from __future__ import annotations

import logging
from difflib import get_close_matches

from .domain_attributes import get_domain_attributes
from .knowledge_base import StateKnowledgeBase
from .models import IssueType, Severity, StateReference, ValidationIssue

_LOGGER = logging.getLogger(__name__)


class ValidationEngine:
    """Validates state references against known valid states."""

    def __init__(self, knowledge_base: StateKnowledgeBase) -> None:
        """Initialize the validation engine.

        Args:
            knowledge_base: The state knowledge base
        """
        self.knowledge_base = knowledge_base
        self._entity_cache: dict[str, list[str]] | None = None

    def validate_reference(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate a single state reference."""
        issues: list[ValidationIssue] = []

        try:
            if not self.knowledge_base.entity_exists(ref.entity_id):
                # Check if entity existed in history (removed/renamed vs typo)
                historical_ids = self.knowledge_base.get_historical_entity_ids()
                if ref.entity_id in historical_ids:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.ENTITY_REMOVED,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Entity '{ref.entity_id}' existed in history but is now missing (removed or renamed)",
                            suggestion=self._suggest_entity(ref.entity_id),
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.ENTITY_NOT_FOUND,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Entity '{ref.entity_id}' does not exist",
                            suggestion=self._suggest_entity(ref.entity_id),
                        )
                    )
                return issues

            if ref.expected_state is not None:
                state_issues = self._validate_state(ref)
                issues.extend(state_issues)

            if ref.expected_attribute is not None:
                attr_issues = self._validate_attribute(ref)
                issues.extend(attr_issues)

        except Exception as err:
            _LOGGER.warning(
                "Error validating %s in %s: %s", ref.entity_id, ref.automation_id, err
            )
            # Return empty - avoid false positives on errors

        return issues

    def _validate_state(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate the expected state."""
        issues: list[ValidationIssue] = []
        valid_states = self.knowledge_base.get_valid_states(ref.entity_id)

        if valid_states is None:
            return issues

        expected = ref.expected_state
        valid_states_list = list(valid_states)

        if expected in valid_states:
            return issues

        lower_map = {s.lower(): s for s in valid_states}
        if expected.lower() in lower_map:
            correct_case = lower_map[expected.lower()]
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.CASE_MISMATCH,
                    severity=Severity.WARNING,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"State '{expected}' has incorrect case, should be '{correct_case}'",
                    suggestion=correct_case,
                    valid_states=valid_states_list,
                )
            )
            return issues

        suggestion = self._suggest_state(expected, valid_states)
        issues.append(
            ValidationIssue(
                issue_type=IssueType.INVALID_STATE,
                severity=Severity.ERROR,
                automation_id=ref.automation_id,
                automation_name=ref.automation_name,
                entity_id=ref.entity_id,
                location=ref.location,
                message=f"State '{expected}' is not valid for {ref.entity_id}",
                suggestion=suggestion,
                valid_states=valid_states_list,
            )
        )

        return issues

    def _validate_attribute(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate the expected attribute exists.

        Checks against supported attributes for the domain, not just current state.
        This prevents false positives (e.g., light.brightness when light is off).
        """
        issues: list[ValidationIssue] = []

        state = self.knowledge_base.hass.states.get(ref.entity_id)
        if state is None:
            return issues

        # Check if attribute is in current state
        if ref.expected_attribute in state.attributes:
            return issues

        # Check if attribute is supported by this domain
        domain = self.knowledge_base.get_domain(ref.entity_id)
        domain_attrs = get_domain_attributes(domain)
        if ref.expected_attribute in domain_attrs:
            # Attribute is supported by this domain, don't report error
            return issues

        # Attribute not found in current state or domain defaults
        available = list(state.attributes.keys())
        suggestion = self._suggest_attribute(ref.expected_attribute, available)
        issues.append(
            ValidationIssue(
                issue_type=IssueType.ATTRIBUTE_NOT_FOUND,
                severity=Severity.ERROR,
                automation_id=ref.automation_id,
                automation_name=ref.automation_name,
                entity_id=ref.entity_id,
                location=ref.location,
                message=f"Attribute '{ref.expected_attribute}' does not exist on {ref.entity_id}",
                suggestion=suggestion,
                valid_states=available,
            )
        )

        return issues

    def _suggest_state(self, invalid: str, valid_states: set[str]) -> str | None:
        """Suggest a correction for an invalid state."""
        matches = get_close_matches(
            invalid.lower(), [s.lower() for s in valid_states], n=1, cutoff=0.6
        )
        if matches:
            lower_map = {s.lower(): s for s in valid_states}
            return lower_map.get(matches[0])
        return None

    def _ensure_entity_cache(self) -> None:
        """Build entity cache if not present."""
        if self._entity_cache is not None:
            return

        self._entity_cache = {}
        try:
            for entity in self.knowledge_base.hass.states.async_all():
                domain = entity.entity_id.split(".")[0]
                if domain not in self._entity_cache:
                    self._entity_cache[domain] = []
                self._entity_cache[domain].append(entity.entity_id)
        except Exception as err:
            _LOGGER.warning("Failed to build entity cache: %s", err)
            self._entity_cache = {}

    def _suggest_entity(self, invalid: str) -> str | None:
        """Suggest a correction for an invalid entity ID."""
        if "." not in invalid:
            return None

        self._ensure_entity_cache()
        domain, name = invalid.split(".", 1)

        same_domain = self._entity_cache.get(domain, [])
        if not same_domain:
            return None

        # Match on name portion only with higher threshold
        names = {eid.split(".", 1)[1]: eid for eid in same_domain}
        matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

        return names[matches[0]] if matches else None

    def _suggest_attribute(self, invalid: str, valid_attrs: list[str]) -> str | None:
        """Suggest a correction for an invalid attribute."""
        matches = get_close_matches(invalid, valid_attrs, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def validate_all(self, refs: list[StateReference]) -> list[ValidationIssue]:
        """Validate a list of state references."""
        issues: list[ValidationIssue] = []
        for ref in refs:
            issues.extend(self.validate_reference(ref))
        return issues
