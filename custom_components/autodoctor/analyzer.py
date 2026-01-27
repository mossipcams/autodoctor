"""AutomationAnalyzer - extracts state references from automations."""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import IssueType, Severity, StateReference, ValidationIssue

_LOGGER = logging.getLogger(__name__)

# Regex patterns for template parsing
IS_STATE_PATTERN = re.compile(
    r"is_state\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)
STATE_ATTR_PATTERN = re.compile(
    r"state_attr\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)
STATES_OBJECT_PATTERN = re.compile(
    r"states\.([a-z_]+)\.([a-z0-9_]+)(?:\.state)?"
)


class AutomationAnalyzer:
    """Parses automation configs and extracts all state references."""

    def _normalize_states(self, value: Any) -> list[str]:
        """Normalize state value(s) to a list of strings.

        HA configs can have states as:
        - A single string: "on"
        - A list of strings: ["on", "off"]
        - YAML node classes that behave like lists but don't pass isinstance(list)
        """
        if value is None:
            return []

        # Handle list-like objects (including YAML NodeListClass)
        # Check for list behavior rather than exact type
        if hasattr(value, "__iter__") and not isinstance(value, str):
            return [str(v) for v in value]

        return [str(value)]

    def extract_state_references(self, automation: dict[str, Any]) -> list[StateReference]:
        """Extract all state references from an automation."""
        refs: list[StateReference] = []

        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = automation.get("alias", automation_id)

        # Extract from triggers (support both 'trigger' and 'triggers' keys)
        triggers = automation.get("triggers") or automation.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers]

        for idx, trigger in enumerate(triggers):
            refs.extend(
                self._extract_from_trigger(trigger, idx, automation_id, automation_name)
            )

        # Extract from conditions (support both 'condition' and 'conditions' keys)
        conditions = automation.get("conditions") or automation.get("condition", [])
        if not isinstance(conditions, list):
            conditions = [conditions]

        for idx, condition in enumerate(conditions):
            refs.extend(
                self._extract_from_condition(condition, idx, automation_id, automation_name)
            )

        return refs

    def _extract_from_trigger(
        self,
        trigger: dict[str, Any],
        index: int,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract state references from a trigger."""
        refs: list[StateReference] = []
        # Support both 'platform' (old format) and 'trigger' (new format) keys
        platform = trigger.get("platform") or trigger.get("trigger", "")

        if platform == "state":
            entity_ids = trigger.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            to_states = self._normalize_states(trigger.get("to"))
            from_states = self._normalize_states(trigger.get("from"))

            for entity_id in entity_ids:
                for state in to_states:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=state,
                            expected_attribute=None,
                            location=f"trigger[{index}].to",
                            transition_from=from_states[0] if from_states else None,
                        )
                    )
                for state in from_states:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=state,
                            expected_attribute=None,
                            location=f"trigger[{index}].from",
                        )
                    )

        elif platform == "numeric_state":
            entity_ids = trigger.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            attribute = trigger.get("attribute")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=attribute,
                        location=f"trigger[{index}]",
                    )
                )

        elif platform == "template":
            value_template = trigger.get("value_template", "")
            refs.extend(
                self._extract_from_template(
                    value_template, f"trigger[{index}]", automation_id, automation_name
                )
            )

        return refs

    def _extract_from_condition(
        self,
        condition: dict[str, Any],
        index: int,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract state references from a condition."""
        refs: list[StateReference] = []
        # Support both 'condition' key (used in both old and new formats for condition type)
        cond_type = condition.get("condition", "")

        if cond_type == "state":
            entity_ids = condition.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            states = self._normalize_states(condition.get("state"))

            for entity_id in entity_ids:
                for state in states:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=state,
                            expected_attribute=None,
                            location=f"condition[{index}].state",
                        )
                    )

        elif cond_type == "template":
            value_template = condition.get("value_template", "")
            refs.extend(
                self._extract_from_template(
                    value_template, f"condition[{index}]", automation_id, automation_name
                )
            )

        return refs

    def _extract_from_template(
        self,
        template: str,
        location: str,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract state references from a Jinja2 template."""
        refs: list[StateReference] = []

        # Extract is_state() calls
        for match in IS_STATE_PATTERN.finditer(template):
            entity_id, state = match.groups()
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    expected_state=state,
                    expected_attribute=None,
                    location=f"{location}.is_state",
                )
            )

        # Extract state_attr() calls
        for match in STATE_ATTR_PATTERN.finditer(template):
            entity_id, attribute = match.groups()
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=attribute,
                    location=f"{location}.state_attr",
                )
            )

        # Extract states.domain.entity references
        for match in STATES_OBJECT_PATTERN.finditer(template):
            domain, entity_name = match.groups()
            entity_id = f"{domain}.{entity_name}"
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.states_object",
                    )
                )

        return refs

    def check_trigger_condition_compatibility(
        self, automation: dict[str, Any]
    ) -> list[ValidationIssue]:
        """Check if triggers and conditions are compatible.

        Detects impossible conditions where a trigger fires on one state
        but the condition requires a different (incompatible) state for
        the same entity.
        """
        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = automation.get("alias", automation_id)

        triggers = automation.get("triggers") or automation.get("trigger", [])
        conditions = automation.get("conditions") or automation.get("condition", [])

        if not isinstance(triggers, list):
            triggers = [triggers]
        if not isinstance(conditions, list):
            conditions = [conditions]

        # Build map of entity_id -> trigger "to" states
        trigger_states: dict[str, set[str]] = {}
        for trigger in triggers:
            platform = trigger.get("platform") or trigger.get("trigger", "")
            if platform == "state":
                entity_ids = trigger.get("entity_id", [])
                if isinstance(entity_ids, str):
                    entity_ids = [entity_ids]

                to_state = trigger.get("to")
                if to_state is not None:
                    to_states = self._normalize_states(to_state)
                    for entity_id in entity_ids:
                        if entity_id not in trigger_states:
                            trigger_states[entity_id] = set()
                        trigger_states[entity_id].update(to_states)

        issues: list[ValidationIssue] = []

        for idx, condition in enumerate(conditions):
            if condition.get("condition") == "state":
                entity_id = condition.get("entity_id")
                required_states = self._normalize_states(condition.get("state"))

                if entity_id and entity_id in trigger_states:
                    trigger_to_states = trigger_states[entity_id]
                    required_set = set(required_states)

                    # Check if there's any overlap
                    if not trigger_to_states.intersection(required_set):
                        issues.append(
                            ValidationIssue(
                                issue_type=IssueType.IMPOSSIBLE_CONDITION,
                                severity=Severity.ERROR,
                                automation_id=automation_id,
                                automation_name=automation_name,
                                entity_id=entity_id,
                                location=f"condition[{idx}].state",
                                message=f"Condition requires '{', '.join(required_states)}' but trigger fires on '{', '.join(trigger_to_states)}'",
                                suggestion=list(trigger_to_states)[0] if trigger_to_states else None,
                            )
                        )

        return issues
