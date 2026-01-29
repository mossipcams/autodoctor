"""AutomationAnalyzer - extracts state references from automations."""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import (
    ConditionInfo,
    EntityAction,
    StateReference,
    TriggerInfo,
)

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
# Pattern for states('entity_id') function calls
# Matches: states('sensor.temperature'), states("light.bedroom") | default('unknown')
STATES_FUNCTION_PATTERN = re.compile(
    rf"states\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
# Pattern for expand() function calls
# Matches: expand('group.all_lights'), expand('light.bedroom', 'light.kitchen')
EXPAND_PATTERN = re.compile(
    rf"expand\s*\(\s*['\"]({_QUOTED_STRING})['\"]",
    re.DOTALL,
)
# Pattern for area_entities() calls
# Matches: area_entities('living_room')
AREA_ENTITIES_PATTERN = re.compile(
    rf"area_entities\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
# Pattern for device_entities() calls
# Matches: device_entities('device_id_here')
DEVICE_ENTITIES_PATTERN = re.compile(
    rf"device_entities\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
# Pattern for integration_entities() calls
# Matches: integration_entities('hue')
INTEGRATION_ENTITIES_PATTERN = re.compile(
    rf"integration_entities\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
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

    def extract_state_references(
        self, automation: dict[str, Any]
    ) -> list[StateReference]:
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
                self._extract_from_condition(
                    condition, idx, automation_id, automation_name
                )
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

        # Guard: skip non-dict triggers
        if not isinstance(trigger, dict):
            _LOGGER.warning(
                "Skipping non-dict trigger[%d] in %s: %s",
                index, automation_id, type(trigger).__name__
            )
            return refs

        # Support both 'platform' (old format) and 'trigger' (new format) keys
        platform = trigger.get("platform") or trigger.get("trigger", "")

        if platform == "state":
            entity_ids = trigger.get("entity_id") or []
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
            entity_ids = trigger.get("entity_id") or []
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
        condition: dict[str, Any] | str,
        index: int,
        automation_id: str,
        automation_name: str,
        location_prefix: str = "condition",
    ) -> list[StateReference]:
        """Extract state references from a condition."""
        refs: list[StateReference] = []

        # Handle string conditions (template shorthand)
        if isinstance(condition, str):
            refs.extend(
                self._extract_from_template(
                    condition,
                    f"{location_prefix}[{index}]",
                    automation_id,
                    automation_name,
                )
            )
            return refs

        # Skip if not a dict
        if not isinstance(condition, dict):
            return refs

        # Support both 'condition' key (used in both old and new formats for condition type)
        cond_type = condition.get("condition", "")

        # Handle explicit state condition OR implicit shorthand (entity_id + state without condition key)
        is_state_condition = cond_type == "state" or (
            not cond_type and "entity_id" in condition and "state" in condition
        )

        if is_state_condition:
            entity_ids = condition.get("entity_id") or []
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
                            location=f"{location_prefix}[{index}].state",
                        )
                    )

        elif cond_type == "template":
            value_template = condition.get("value_template", "")
            refs.extend(
                self._extract_from_template(
                    value_template,
                    f"{location_prefix}[{index}]",
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

        # Extract states('entity_id') function calls
        for match in STATES_FUNCTION_PATTERN.finditer(template):
            entity_id = match.group(1)
            # Deduplicate - don't add if already found via other patterns
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.states_function",
                    )
                )

        # Extract expand() function calls
        for match in EXPAND_PATTERN.finditer(template):
            entity_id = match.group(1)
            # Deduplicate - don't add if already found via other patterns
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.expand",
                        reference_type="group",
                    )
                )

        # Extract area_entities() calls
        for match in AREA_ENTITIES_PATTERN.finditer(template):
            area_id = match.group(1)
            if not any(r.entity_id == area_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=area_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.area_entities",
                        reference_type="area",
                    )
                )

        # Extract device_entities() calls
        for match in DEVICE_ENTITIES_PATTERN.finditer(template):
            device_id = match.group(1)
            if not any(r.entity_id == device_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.device_entities",
                        reference_type="device",
                    )
                )

        # Extract integration_entities() calls
        for match in INTEGRATION_ENTITIES_PATTERN.finditer(template):
            integration_id = match.group(1)
            if not any(r.entity_id == integration_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=integration_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.integration_entities",
                        reference_type="integration",
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
                options = action.get("choose") or []
                default = action.get("default") or []

                for opt_idx, option in enumerate(options):
                    # Check conditions in each option (all types, not just template)
                    conditions = option.get("conditions", [])
                    if not isinstance(conditions, list):
                        conditions = [conditions]

                    for cond_idx, condition in enumerate(conditions):
                        refs.extend(
                            self._extract_from_condition(
                                condition,
                                cond_idx,
                                automation_id,
                                automation_name,
                                f"action[{idx}].choose[{opt_idx}].conditions",
                            )
                        )

                    # Recurse into sequence
                    sequence = option.get("sequence", [])
                    refs.extend(
                        self._extract_from_actions(
                            sequence, automation_id, automation_name
                        )
                    )

                # Recurse into default
                if default:
                    refs.extend(
                        self._extract_from_actions(
                            default, automation_id, automation_name
                        )
                    )

            # Extract from if conditions (all types, not just template)
            elif "if" in action:
                conditions = action.get("if", [])
                if not isinstance(conditions, list):
                    conditions = [conditions]

                for cond_idx, condition in enumerate(conditions):
                    refs.extend(
                        self._extract_from_condition(
                            condition,
                            cond_idx,
                            automation_id,
                            automation_name,
                            f"action[{idx}].if",
                        )
                    )

                # Recurse into then/else
                then_actions = action.get("then", [])
                else_actions = action.get("else", [])
                refs.extend(
                    self._extract_from_actions(
                        then_actions, automation_id, automation_name
                    )
                )
                if else_actions:
                    refs.extend(
                        self._extract_from_actions(
                            else_actions, automation_id, automation_name
                        )
                    )

            # Extract from repeat while/until conditions (all types, not just template)
            elif "repeat" in action:
                repeat_config = action["repeat"]

                # Check while conditions
                while_conditions = repeat_config.get("while", [])
                if not isinstance(while_conditions, list):
                    while_conditions = [while_conditions]
                for cond_idx, condition in enumerate(while_conditions):
                    refs.extend(
                        self._extract_from_condition(
                            condition,
                            cond_idx,
                            automation_id,
                            automation_name,
                            f"action[{idx}].repeat.while",
                        )
                    )

                # Check until conditions
                until_conditions = repeat_config.get("until", [])
                if not isinstance(until_conditions, list):
                    until_conditions = [until_conditions]
                for cond_idx, condition in enumerate(until_conditions):
                    refs.extend(
                        self._extract_from_condition(
                            condition,
                            cond_idx,
                            automation_id,
                            automation_name,
                            f"action[{idx}].repeat.until",
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
                branches = action.get("parallel") or []
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

    def extract_entity_actions(self, automation: dict[str, Any]) -> list[EntityAction]:
        """Extract all entity actions (service calls) from an automation."""
        actions: list[EntityAction] = []

        automation_id = f"automation.{automation.get('id', 'unknown')}"

        action_list = automation.get("actions") or automation.get("action", [])
        if not isinstance(action_list, list):
            action_list = [action_list]

        actions.extend(self._extract_actions_recursive(action_list, automation_id))

        return actions

    def _extract_actions_recursive(
        self,
        action_list: list[dict[str, Any]],
        automation_id: str,
        parent_conditions: list[ConditionInfo] | None = None,
    ) -> list[EntityAction]:
        """Recursively extract EntityActions from action blocks."""
        results: list[EntityAction] = []
        if parent_conditions is None:
            parent_conditions = []

        for action in action_list:
            if not isinstance(action, dict):
                continue

            # Direct service call (supports both "service" and "action" keys)
            if "service" in action or "action" in action:
                results.extend(
                    self._parse_service_call(action, automation_id, parent_conditions)
                )

            # Choose block
            if "choose" in action:
                for option in action.get("choose", []):
                    # Extract conditions from this option
                    option_conditions = list(parent_conditions)
                    for cond in option.get("conditions", []):
                        cond_info = self._condition_to_condition_info(cond)
                        if cond_info:
                            option_conditions.append(cond_info)

                    sequence = option.get("sequence", [])
                    results.extend(
                        self._extract_actions_recursive(
                            sequence, automation_id, option_conditions
                        )
                    )

                # Default has no additional conditions
                default = action.get("default") or []
                if default:
                    results.extend(
                        self._extract_actions_recursive(
                            default, automation_id, parent_conditions
                        )
                    )

            # If/then/else block
            if "if" in action:
                # Extract conditions from if
                if_conditions = list(parent_conditions)
                for cond in action.get("if", []):
                    cond_info = self._condition_to_condition_info(cond)
                    if cond_info:
                        if_conditions.append(cond_info)

                then_actions = action.get("then", [])
                else_actions = action.get("else", [])
                results.extend(
                    self._extract_actions_recursive(
                        then_actions, automation_id, if_conditions
                    )
                )
                # Else branch: can't represent NOT condition, pass parent unchanged
                if else_actions:
                    results.extend(
                        self._extract_actions_recursive(
                            else_actions, automation_id, parent_conditions
                        )
                    )

            # Repeat block
            if "repeat" in action:
                repeat_config = action["repeat"]
                repeat_conditions = list(parent_conditions)

                # Extract while conditions
                for cond in repeat_config.get("while", []):
                    cond_info = self._condition_to_condition_info(cond)
                    if cond_info:
                        repeat_conditions.append(cond_info)

                # Extract until conditions
                for cond in repeat_config.get("until", []):
                    cond_info = self._condition_to_condition_info(cond)
                    if cond_info:
                        repeat_conditions.append(cond_info)

                sequence = repeat_config.get("sequence", [])
                results.extend(
                    self._extract_actions_recursive(
                        sequence, automation_id, repeat_conditions
                    )
                )

            # Parallel block
            if "parallel" in action:
                branches = action["parallel"]
                if not isinstance(branches, list):
                    branches = [branches]
                for branch in branches:
                    branch_actions = branch if isinstance(branch, list) else [branch]
                    results.extend(
                        self._extract_actions_recursive(
                            branch_actions, automation_id, parent_conditions
                        )
                    )

        return results

    def extract_triggers(self, automation: dict[str, Any]) -> list[TriggerInfo]:
        """Extract simplified trigger info for conflict detection."""
        triggers: list[TriggerInfo] = []

        trigger_list = automation.get("triggers") or automation.get("trigger", [])
        if not isinstance(trigger_list, list):
            trigger_list = [trigger_list]

        for trigger in trigger_list:
            if not isinstance(trigger, dict):
                continue

            # Support both 'platform' (old) and 'trigger' (new) keys
            platform = trigger.get("platform") or trigger.get("trigger", "")

            if platform == "state":
                entity_ids = trigger.get("entity_id", [])
                if isinstance(entity_ids, str):
                    entity_ids = [entity_ids]

                to_states = self._normalize_states(trigger.get("to"))

                for entity_id in entity_ids:
                    triggers.append(
                        TriggerInfo(
                            trigger_type="state",
                            entity_id=entity_id,
                            to_states=set(to_states) if to_states else None,
                            time_value=None,
                            sun_event=None,
                        )
                    )

            elif platform == "time":
                at_value = trigger.get("at")
                # Handle time as string like "06:00:00"
                time_str = None
                if isinstance(at_value, str) and ":" in at_value:
                    time_str = at_value

                triggers.append(
                    TriggerInfo(
                        trigger_type="time",
                        entity_id=None,
                        to_states=None,
                        time_value=time_str,
                        sun_event=None,
                    )
                )

            elif platform == "sun":
                event = trigger.get("event")  # "sunrise" or "sunset"
                triggers.append(
                    TriggerInfo(
                        trigger_type="sun",
                        entity_id=None,
                        to_states=None,
                        time_value=None,
                        sun_event=event,
                    )
                )

            else:
                # Other triggers (template, numeric_state, etc.)
                triggers.append(
                    TriggerInfo(
                        trigger_type="other",
                        entity_id=None,
                        to_states=None,
                        time_value=None,
                        sun_event=None,
                    )
                )

        return triggers

    def extract_conditions(self, automation: dict[str, Any]) -> list[ConditionInfo]:
        """Extract simplified condition info for conflict detection."""
        conditions: list[ConditionInfo] = []

        condition_list = automation.get("conditions") or automation.get("condition", [])
        if not isinstance(condition_list, list):
            condition_list = [condition_list]

        for condition in condition_list:
            if not isinstance(condition, dict):
                continue

            cond_type = condition.get("condition", "")

            # Handle state conditions
            is_state_condition = cond_type == "state" or (
                not cond_type and "entity_id" in condition and "state" in condition
            )

            if is_state_condition:
                entity_id = condition.get("entity_id")
                if isinstance(entity_id, str):
                    states = self._normalize_states(condition.get("state"))
                    if states:
                        conditions.append(
                            ConditionInfo(
                                entity_id=entity_id,
                                required_states=set(states),
                            )
                        )

        return conditions

    def _condition_to_condition_info(
        self, condition: dict[str, Any] | str
    ) -> ConditionInfo | None:
        """Extract ConditionInfo from a condition dict if possible.

        Returns None for conditions that can't be represented as ConditionInfo
        (template conditions, time conditions, etc.).
        """
        if isinstance(condition, str):
            # Template shorthand - can't extract structured info
            return None

        if not isinstance(condition, dict):
            return None

        cond_type = condition.get("condition", "")

        # Handle state conditions (explicit or implicit)
        is_state_condition = cond_type == "state" or (
            not cond_type and "entity_id" in condition and "state" in condition
        )

        if not is_state_condition:
            return None

        entity_id = condition.get("entity_id")
        if not isinstance(entity_id, str):
            # Multiple entity_ids not supported for ConditionInfo
            return None

        states = self._normalize_states(condition.get("state"))
        if not states:
            return None

        return ConditionInfo(entity_id=entity_id, required_states=set(states))

    def _parse_service_call(
        self,
        action: dict[str, Any],
        automation_id: str,
        parent_conditions: list[ConditionInfo] | None = None,
    ) -> list[EntityAction]:
        """Parse a service call action into EntityAction objects."""
        results: list[EntityAction] = []
        if parent_conditions is None:
            parent_conditions = []

        # Support both "service" (old format) and "action" (HA 2024+ format)
        service = action.get("service") or action.get("action", "")
        if not service or "." not in service:
            return results

        domain, service_name = service.split(".", 1)

        # Determine the action type
        if service_name in ("turn_on",):
            action_type = "turn_on"
        elif service_name in ("turn_off",):
            action_type = "turn_off"
        elif service_name in ("toggle",):
            action_type = "toggle"
        else:
            action_type = "set"

        # Extract entity IDs from target, entity_id, or data.entity_id
        entity_ids: list[str] = []

        target = action.get("target", {})
        if isinstance(target, dict):
            target_entities = target.get("entity_id", [])
            if isinstance(target_entities, str):
                entity_ids.append(target_entities)
            elif isinstance(target_entities, list):
                entity_ids.extend(target_entities)

        # Also check direct entity_id field
        direct_entity = action.get("entity_id")
        if direct_entity:
            if isinstance(direct_entity, str):
                entity_ids.append(direct_entity)
            elif isinstance(direct_entity, list):
                entity_ids.extend(direct_entity)

        # Also check data.entity_id (legacy format)
        data = action.get("data", {})
        if isinstance(data, dict):
            data_entity = data.get("entity_id")
            if data_entity:
                if isinstance(data_entity, str):
                    if data_entity not in entity_ids:
                        entity_ids.append(data_entity)
                elif isinstance(data_entity, list):
                    for eid in data_entity:
                        if eid not in entity_ids:
                            entity_ids.append(eid)

        # Get optional value for set actions
        value = action.get("data", {}) if action_type == "set" else None

        for entity_id in entity_ids:
            results.append(
                EntityAction(
                    automation_id=automation_id,
                    entity_id=entity_id,
                    action=action_type,
                    value=value,
                    conditions=list(parent_conditions),
                )
            )

        return results
