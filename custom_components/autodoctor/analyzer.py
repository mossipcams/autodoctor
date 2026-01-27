"""AutomationAnalyzer - extracts state references from automations."""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import IssueType, Severity, StateReference, ValidationIssue

_LOGGER = logging.getLogger(__name__)

# Regex patterns for template parsing
# Use pattern that handles escaped quotes: [^'"\\]*(?:\\.[^'"\\]*)*
_QUOTED_STRING = r"[^'\"\\]*(?:\\.[^'\"\\]*)*"

IS_STATE_PATTERN = re.compile(
    rf"is_state\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*,\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
IS_STATE_ATTR_PATTERN = re.compile(
    rf"is_state_attr\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*,\s*['\"]({_QUOTED_STRING})['\"]\s*,\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
STATE_ATTR_PATTERN = re.compile(
    rf"state_attr\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*,\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
STATES_OBJECT_PATTERN = re.compile(
    r"states\.([a-z_]+)\.([a-z0-9_]+)(?:\.state)?",
    re.DOTALL,
)
# Pattern to strip Jinja2 comments before parsing
JINJA_COMMENT_PATTERN = re.compile(r"\{#.*?#\}", re.DOTALL)


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

        # Extract from actions (support both 'action' and 'actions' keys)
        actions = automation.get("actions") or automation.get("action", [])
        if not isinstance(actions, list):
            actions = [actions]

        refs.extend(self._extract_from_actions(actions, automation_id, automation_name))

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

        # Strip Jinja2 comments before parsing
        template = JINJA_COMMENT_PATTERN.sub("", template)

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

        # Extract is_state_attr() calls
        for match in IS_STATE_ATTR_PATTERN.finditer(template):
            entity_id, attribute, _value = match.groups()
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=attribute,
                    location=f"{location}.is_state_attr",
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

    def _extract_from_actions(
        self,
        actions: list[dict[str, Any]],
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Recursively extract state references from actions."""
        refs: list[StateReference] = []

        if not isinstance(actions, list):
            actions = [actions]

        for idx, action in enumerate(actions):
            # Extract from choose option conditions and sequences
            if "choose" in action:
                options = action.get("choose", [])
                default = action.get("default", [])

                for opt_idx, option in enumerate(options):
                    # Check conditions in each option
                    conditions = option.get("conditions", [])
                    if not isinstance(conditions, list):
                        conditions = [conditions]

                    for cond_idx, condition in enumerate(conditions):
                        if condition.get("condition") == "template":
                            template = condition.get("value_template", "")
                            refs.extend(
                                self._extract_from_template(
                                    template,
                                    f"action[{idx}].choose[{opt_idx}].conditions[{cond_idx}]",
                                    automation_id,
                                    automation_name,
                                )
                            )

                    # Recurse into sequence
                    sequence = option.get("sequence", [])
                    refs.extend(
                        self._extract_from_actions(sequence, automation_id, automation_name)
                    )

                # Recurse into default
                if default:
                    refs.extend(
                        self._extract_from_actions(default, automation_id, automation_name)
                    )

            # Extract from if condition templates
            elif "if" in action:
                conditions = action.get("if", [])
                if not isinstance(conditions, list):
                    conditions = [conditions]

                for cond_idx, condition in enumerate(conditions):
                    if condition.get("condition") == "template":
                        template = condition.get("value_template", "")
                        refs.extend(
                            self._extract_from_template(
                                template,
                                f"action[{idx}].if[{cond_idx}]",
                                automation_id,
                                automation_name,
                            )
                        )

                # Recurse into then/else
                then_actions = action.get("then", [])
                else_actions = action.get("else", [])
                refs.extend(
                    self._extract_from_actions(then_actions, automation_id, automation_name)
                )
                if else_actions:
                    refs.extend(
                        self._extract_from_actions(else_actions, automation_id, automation_name)
                    )

            # Extract from repeat while/until conditions
            elif "repeat" in action:
                repeat_config = action["repeat"]

                # Check while conditions
                while_conditions = repeat_config.get("while", [])
                if not isinstance(while_conditions, list):
                    while_conditions = [while_conditions]
                for cond_idx, condition in enumerate(while_conditions):
                    if condition.get("condition") == "template":
                        template = condition.get("value_template", "")
                        refs.extend(
                            self._extract_from_template(
                                template,
                                f"action[{idx}].repeat.while[{cond_idx}]",
                                automation_id,
                                automation_name,
                            )
                        )

                # Check until conditions
                until_conditions = repeat_config.get("until", [])
                if not isinstance(until_conditions, list):
                    until_conditions = [until_conditions]
                for cond_idx, condition in enumerate(until_conditions):
                    if condition.get("condition") == "template":
                        template = condition.get("value_template", "")
                        refs.extend(
                            self._extract_from_template(
                                template,
                                f"action[{idx}].repeat.until[{cond_idx}]",
                                automation_id,
                                automation_name,
                            )
                        )

                # Recurse into sequence
                sequence = repeat_config.get("sequence", [])
                refs.extend(
                    self._extract_from_actions(sequence, automation_id, automation_name)
                )

            # Extract from wait_template
            elif "wait_template" in action:
                template = action["wait_template"]
                refs.extend(
                    self._extract_from_template(
                        template,
                        f"action[{idx}].wait_template",
                        automation_id,
                        automation_name,
                    )
                )

            # Extract from parallel branches
            elif "parallel" in action:
                branches = action["parallel"]
                if not isinstance(branches, list):
                    branches = [branches]
                for branch in branches:
                    branch_actions = branch if isinstance(branch, list) else [branch]
                    refs.extend(
                        self._extract_from_actions(
                            branch_actions, automation_id, automation_name
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
