"""AutomationAnalyzer - extracts state references from automations."""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import StateReference

_LOGGER = logging.getLogger(__name__)

# Regex patterns for template parsing
IS_STATE_PATTERN = re.compile(
    r"is_state\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)
STATE_ATTR_PATTERN = re.compile(
    r"state_attr\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)
STATES_OBJECT_PATTERN = re.compile(r"states\.([a-z_]+)\.([a-z0-9_]+)(?:\.state)?")


class AutomationAnalyzer:
    """Parses automation configs and extracts all state references."""

    def extract_state_references(
        self, automation: dict[str, Any]
    ) -> list[StateReference]:
        """Extract all state references from an automation."""
        refs: list[StateReference] = []

        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = automation.get("alias", automation_id)

        # Extract from triggers
        triggers = automation.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers]

        for idx, trigger in enumerate(triggers):
            refs.extend(
                self._extract_from_trigger(trigger, idx, automation_id, automation_name)
            )

        # Extract from conditions
        conditions = automation.get("condition", [])
        if not isinstance(conditions, list):
            conditions = [conditions]

        for idx, condition in enumerate(conditions):
            refs.extend(
                self._extract_from_condition(
                    condition, idx, automation_id, automation_name
                )
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
        platform = trigger.get("platform", "")

        if platform == "state":
            entity_ids = trigger.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            to_state = trigger.get("to")
            from_state = trigger.get("from")

            for entity_id in entity_ids:
                if to_state is not None:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=str(to_state),
                            expected_attribute=None,
                            location=f"trigger[{index}].to",
                            transition_from=str(from_state) if from_state else None,
                        )
                    )
                if from_state is not None:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=str(from_state),
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
        cond_type = condition.get("condition", "")

        if cond_type == "state":
            entity_ids = condition.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            state = condition.get("state")

            for entity_id in entity_ids:
                if state is not None:
                    states = state if isinstance(state, list) else [state]
                    for s in states:
                        refs.append(
                            StateReference(
                                automation_id=automation_id,
                                automation_name=automation_name,
                                entity_id=entity_id,
                                expected_state=str(s),
                                expected_attribute=None,
                                location=f"condition[{index}].state",
                            )
                        )

        elif cond_type == "template":
            value_template = condition.get("value_template", "")
            refs.extend(
                self._extract_from_template(
                    value_template,
                    f"condition[{index}]",
                    automation_id,
                    automation_name,
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
