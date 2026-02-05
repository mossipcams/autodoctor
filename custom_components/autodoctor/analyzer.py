"""AutomationAnalyzer - extracts state references from automations."""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from .const import MAX_RECURSION_DEPTH
from .models import ServiceCall, StateReference

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
# Pattern for device_id('entity_id')
DEVICE_ID_PATTERN = re.compile(
    rf"device_id\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
# Pattern for area_name('entity_id') and area_id('entity_id')
AREA_NAME_PATTERN = re.compile(
    rf"area_(?:name|id)\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
# Pattern for has_value('entity_id')
HAS_VALUE_PATTERN = re.compile(
    rf"has_value\s*\(\s*['\"]({_QUOTED_STRING})['\"]\s*\)",
    re.DOTALL,
)
# Pattern to strip Jinja2 comments before parsing
JINJA_COMMENT_PATTERN = re.compile(r"\{#.*?#\}", re.DOTALL)

# Keys at the action dict level that are structural (not service parameters).
# Any key NOT in this set is treated as an inline service parameter.
_ACTION_STRUCTURAL_KEYS = frozenset(
    {
        "service",
        "action",
        "data",
        "target",
        "entity_id",
        "enabled",
        "alias",
        "continue_on_error",
        "response_variable",
        # Control flow keys (handled separately)
        "choose",
        "default",
        "if",
        "then",
        "else",
        "repeat",
        "parallel",
        "sequence",
        "for_each",
        "wait_template",
        "wait_for_trigger",
        "delay",
        "event",
        "scene",
        "stop",
        "variables",
        "set_conversation_response",
        "device_id",
        "domain",
        "type",  # device action keys
        "metadata",
    }
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

    def _normalize_entity_ids(self, value: Any) -> list[str]:
        """Normalize entity_id value(s) to a list of strings."""
        if value is None:
            return []
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
        if not isinstance(trigger, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            _LOGGER.warning(
                "Skipping non-dict trigger[%d] in %s: %s",
                index,
                automation_id,
                type(trigger).__name__,
            )
            return refs

        # Support both 'platform' (old format) and 'trigger' (new format) keys
        platform = trigger.get("platform") or trigger.get("trigger", "")

        if platform == "state":
            entity_ids = cast(Any, trigger.get("entity_id") or [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            to_states = self._normalize_states(trigger.get("to"))
            from_states = self._normalize_states(trigger.get("from"))
            trigger_attribute = trigger.get("attribute")

            for entity_id in entity_ids:
                for state in to_states:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=state,
                            expected_attribute=trigger_attribute,
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
                            expected_attribute=trigger_attribute,
                            location=f"trigger[{index}].from",
                        )
                    )

        elif platform == "numeric_state":
            entity_ids = cast(Any, trigger.get("entity_id") or [])
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

        elif platform == "zone":
            entity_ids = self._normalize_entity_ids(trigger.get("entity_id"))
            zone_id = trigger.get("zone")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].entity_id",
                        reference_type="direct",
                    )
                )

            if zone_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=zone_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].zone",
                        reference_type="zone",
                    )
                )

        elif platform == "sun":
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id="sun.sun",
                    expected_state=None,
                    expected_attribute=None,
                    location=f"trigger[{index}]",
                    reference_type="direct",
                )
            )

        elif platform == "calendar":
            entity_ids = self._normalize_entity_ids(trigger.get("entity_id"))

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].entity_id",
                        reference_type="direct",
                    )
                )

        elif platform == "device":
            device_id = trigger.get("device_id")
            if device_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].device_id",
                        reference_type="device",
                    )
                )

        elif platform == "tag":
            tag_id = trigger.get("tag_id")
            if tag_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=tag_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].tag_id",
                        reference_type="tag",
                    )
                )

            device_id = trigger.get("device_id")
            if device_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].device_id",
                        reference_type="device",
                    )
                )

        elif platform == "geo_location":
            zone = trigger.get("zone")
            if zone:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=zone,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].zone",
                        reference_type="zone",
                    )
                )

        elif platform == "event":
            event_data = trigger.get("event_data", {})

            if isinstance(event_data, dict):
                for key, value in cast(dict[str, Any], event_data).items():
                    if isinstance(value, str):
                        refs.extend(
                            self._extract_from_template(
                                value,
                                f"trigger[{index}].event_data.{key}",
                                automation_id,
                                automation_name,
                            )
                        )

        elif platform == "mqtt":
            topic = trigger.get("topic", "")
            payload = trigger.get("payload", "")

            if isinstance(topic, str):
                refs.extend(
                    self._extract_from_template(
                        topic,
                        f"trigger[{index}].topic",
                        automation_id,
                        automation_name,
                    )
                )

            if isinstance(payload, str):
                refs.extend(
                    self._extract_from_template(
                        payload,
                        f"trigger[{index}].payload",
                        automation_id,
                        automation_name,
                    )
                )

        elif platform == "webhook":
            webhook_id = trigger.get("webhook_id", "")

            if isinstance(webhook_id, str):
                refs.extend(
                    self._extract_from_template(
                        webhook_id,
                        f"trigger[{index}].webhook_id",
                        automation_id,
                        automation_name,
                    )
                )

        elif platform == "persistent_notification":
            notification_id = trigger.get("notification_id", "")

            if isinstance(notification_id, str):
                refs.extend(
                    self._extract_from_template(
                        notification_id,
                        f"trigger[{index}].notification_id",
                        automation_id,
                        automation_name,
                    )
                )

        elif platform == "time":
            at_values: Any = trigger.get("at")
            if not isinstance(at_values, list):
                at_values = [at_values] if at_values else []

            for at_value in cast(list[Any], at_values):
                # If it looks like an entity_id (contains a dot but not a colon), validate it
                if (
                    isinstance(at_value, str)
                    and "." in at_value
                    and ":" not in at_value
                ):
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=at_value,
                            expected_state=None,
                            expected_attribute=None,
                            location=f"trigger[{index}].at",
                            reference_type="direct",
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
        if not isinstance(condition, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            return refs

        # Support both 'condition' key (used in both old and new formats for condition type)
        cond_type = condition.get("condition", "")

        # Handle explicit state condition OR implicit shorthand (entity_id + state without condition key)
        is_state_condition = cond_type == "state" or (
            not cond_type and "entity_id" in condition and "state" in condition
        )

        if is_state_condition:
            entity_ids = cast(Any, condition.get("entity_id") or [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            states = self._normalize_states(condition.get("state"))
            condition_attribute = condition.get("attribute")

            for entity_id in entity_ids:
                for state in states:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=state,
                            expected_attribute=condition_attribute,
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

        elif cond_type == "numeric_state":
            entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
            attribute = condition.get("attribute")
            value_template = condition.get("value_template")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=attribute,
                        location=f"{location_prefix}[{index}]",
                        reference_type="direct",
                    )
                )

            # Extract from value_template if present
            if value_template and isinstance(value_template, str):
                refs.extend(
                    self._extract_from_template(
                        value_template,
                        f"{location_prefix}[{index}].value_template",
                        automation_id,
                        automation_name,
                    )
                )

        elif cond_type == "zone":
            entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
            zone_id = condition.get("zone")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].entity_id",
                        reference_type="direct",
                    )
                )

            if zone_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=zone_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].zone",
                        reference_type="zone",
                    )
                )

        elif cond_type == "sun":
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id="sun.sun",
                    expected_state=None,
                    expected_attribute=None,
                    location=f"{location_prefix}[{index}]",
                    reference_type="direct",
                )
            )

        elif cond_type == "time":
            # Check after and before for entity IDs
            after_value = condition.get("after")
            before_value = condition.get("before")

            # If it looks like an entity_id (contains a dot but not a colon), validate it
            if (
                after_value
                and isinstance(after_value, str)
                and "." in after_value
                and ":" not in after_value
            ):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=after_value,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].after",
                        reference_type="direct",
                    )
                )

            if (
                before_value
                and isinstance(before_value, str)
                and "." in before_value
                and ":" not in before_value
            ):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=before_value,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].before",
                        reference_type="direct",
                    )
                )

        elif cond_type == "device":
            device_id = condition.get("device_id")

            if device_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].device_id",
                        reference_type="device",
                    )
                )

        return refs

    def _extract_from_template(
        self,
        template: Any,  # Can be str or any type from YAML
        location: str,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract state references from a Jinja2 template."""
        refs: list[StateReference] = []

        # Fix: property-based testing found crash on non-string template values
        if not isinstance(template, str):
            return refs

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
            entity_id, attribute, attr_value = match.groups()
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    expected_state=attr_value,
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

        # Extract device_id() calls
        for match in DEVICE_ID_PATTERN.finditer(template):
            entity_id = match.group(1)
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.device_id",
                        reference_type="metadata",
                    )
                )

        # Extract area_name/area_id() calls
        for match in AREA_NAME_PATTERN.finditer(template):
            entity_id = match.group(1)
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.area_lookup",
                        reference_type="metadata",
                    )
                )

        # Extract has_value() calls
        for match in HAS_VALUE_PATTERN.finditer(template):
            entity_id = match.group(1)
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.has_value",
                        reference_type="entity",
                    )
                )

        return refs

    def _extract_from_service_call(
        self,
        action: dict[str, Any],
        index: int,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract entity references from service calls.

        Args:
            action: The action dict containing service call
            index: Action index in the automation
            automation_id: Automation entity ID
            automation_name: Automation friendly name

        Returns:
            List of StateReference objects for entities in service call
        """
        refs: list[StateReference] = []

        # Get service name (both 'service' and 'action' keys)
        service = action.get("service") or action.get("action")
        if not service:
            return refs

        # Fix: property-based testing found crash on non-string service values
        if not isinstance(service, str):
            return refs

        # Shorthand script call: service: script.my_script
        if service.startswith("script.") and service not in (
            "script.turn_on",
            "script.reload",
            "script.turn_off",
        ):
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=service,  # e.g., "script.bedtime_routine"
                    expected_state=None,
                    expected_attribute=None,
                    location=f"action[{index}].service",
                    reference_type="script",
                )
            )
            return refs  # Shorthand doesn't have additional entity_id

        # Check data.entity_id
        data = action.get("data", {})
        entity_ids = self._normalize_states(data.get("entity_id"))

        # Check target.entity_id (newer syntax)
        target = action.get("target", {})
        entity_ids.extend(self._normalize_states(target.get("entity_id")))

        # Determine reference type based on service
        reference_type = "service_call"
        if service == "scene.turn_on":
            reference_type = "scene"
        elif service == "script.turn_on":
            reference_type = "script"

        for entity_id in entity_ids:
            # If it's a template, extract from template
            if "{{" in entity_id:
                refs.extend(
                    self._extract_from_template(
                        entity_id,
                        f"action[{index}].data.entity_id",
                        automation_id,
                        automation_name,
                    )
                )
            else:
                # Direct entity reference
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"action[{index}].service.entity_id",
                        reference_type=reference_type,
                    )
                )

        return refs

    def _extract_from_actions(
        self,
        actions: list[dict[str, Any]],
        automation_id: str,
        automation_name: str,
        _depth: int = 0,
    ) -> list[StateReference]:
        """Recursively extract state references from actions."""
        if _depth >= MAX_RECURSION_DEPTH:
            _LOGGER.warning(
                "Max recursion depth (%d) reached in automation '%s'",
                MAX_RECURSION_DEPTH,
                automation_name,
            )
            return []

        refs: list[StateReference] = []

        if not isinstance(actions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
            actions = [actions]

        for idx, action in enumerate(actions):
            if not isinstance(action, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                continue

            # Extract from service calls
            refs.extend(
                self._extract_from_service_call(
                    action, idx, automation_id, automation_name
                )
            )

            # Extract from choose option conditions and sequences
            if "choose" in action:
                options = cast(list[Any], action.get("choose") or [])
                default = cast(list[Any], action.get("default") or [])

                for opt_idx, option in enumerate(options):
                    # Check conditions in each option (all types, not just template)
                    conditions = cast(list[Any], option.get("conditions") or [])
                    if not isinstance(conditions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
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
                    opt_sequence = cast(list[Any], option.get("sequence") or [])
                    refs.extend(
                        self._extract_from_actions(
                            opt_sequence, automation_id, automation_name, _depth + 1
                        )
                    )

                # Recurse into default
                if default:
                    refs.extend(
                        self._extract_from_actions(
                            default, automation_id, automation_name, _depth + 1
                        )
                    )

            # Extract from if conditions (all types, not just template)
            if "if" in action:
                conditions = cast(list[Any], action.get("if") or [])
                if not isinstance(conditions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
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
                        then_actions, automation_id, automation_name, _depth + 1
                    )
                )
                if else_actions:
                    refs.extend(
                        self._extract_from_actions(
                            else_actions, automation_id, automation_name, _depth + 1
                        )
                    )

            # Extract from repeat while/until conditions (all types, not just template)
            if "repeat" in action:
                repeat_config = action["repeat"]
                if isinstance(repeat_config, dict):
                    repeat_config = cast(dict[str, Any], repeat_config)
                    # Check while conditions
                    while_conditions = cast(list[Any], repeat_config.get("while") or [])
                    if not isinstance(while_conditions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
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
                    until_conditions = cast(list[Any], repeat_config.get("until") or [])
                    if not isinstance(until_conditions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
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
                    repeat_sequence = cast(
                        list[Any], repeat_config.get("sequence") or []
                    )
                    refs.extend(
                        self._extract_from_actions(
                            repeat_sequence, automation_id, automation_name, _depth + 1
                        )
                    )

            # Extract from wait_template
            if "wait_template" in action:
                template = action["wait_template"]
                if isinstance(template, str):
                    refs.extend(
                        self._extract_from_template(
                            template,
                            f"action[{idx}].wait_template",
                            automation_id,
                            automation_name,
                        )
                    )

            # Extract from parallel branches
            if "parallel" in action:
                branches = cast(list[Any], action.get("parallel") or [])
                if not isinstance(branches, list):  # pyright: ignore[reportUnnecessaryIsInstance]
                    branches = [branches]
                for branch in branches:
                    branch_actions = cast(
                        list[Any], branch if isinstance(branch, list) else [branch]
                    )
                    refs.extend(
                        self._extract_from_actions(
                            branch_actions, automation_id, automation_name, _depth + 1
                        )
                    )

        return refs

    def extract_service_calls(self, automation: dict[str, Any]) -> list[ServiceCall]:
        """Extract all service calls from automation actions."""
        service_calls: list[ServiceCall] = []
        actions = cast(
            list[dict[str, Any]],
            automation.get("actions") or automation.get("action") or [],
        )
        if not isinstance(actions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
            actions = [actions]

        automation_id: str = automation.get("id", "unknown")
        automation_name: str = automation.get("alias", "Unknown")

        self._extract_service_calls_from_actions(
            cast(list[dict[str, Any]], actions),
            automation_id,
            automation_name,
            "action",
            service_calls,
        )
        return service_calls

    def _extract_service_calls_from_actions(
        self,
        actions: list[dict[str, Any]],
        automation_id: str,
        automation_name: str,
        location_prefix: str,
        service_calls: list[ServiceCall],
        _depth: int = 0,
    ) -> None:
        """Recursively extract service calls from a list of actions."""
        if _depth >= MAX_RECURSION_DEPTH:
            _LOGGER.warning(
                "Max recursion depth (%d) reached extracting service calls in automation '%s'",
                MAX_RECURSION_DEPTH,
                automation_name,
            )
            return

        if not isinstance(actions, list):  # pyright: ignore[reportUnnecessaryIsInstance]
            actions = [actions]

        for idx, action in enumerate(actions):
            if not isinstance(action, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                continue

            location = f"{location_prefix}[{idx}]"

            # Direct service call (both 'service' and 'action' keys)
            service = action.get("service") or action.get("action")
            if service and isinstance(service, str):
                is_template = "{{" in service or "{%" in service

                # Merge inline params with explicit data: dict.
                # HA allows params at action level without a data: wrapper.
                explicit_data: Any = action.get("data")
                if isinstance(explicit_data, str):
                    # Template string in data: — pass through as-is
                    merged_data: dict[str, Any] | None = cast(
                        dict[str, Any] | None, explicit_data
                    )
                else:
                    inline_params = {
                        k: v
                        for k, v in action.items()
                        if k not in _ACTION_STRUCTURAL_KEYS
                    }
                    explicit_data = cast(dict[str, Any], explicit_data or {})
                    merged_data = (
                        {**inline_params, **explicit_data}
                        if inline_params
                        else explicit_data
                    ) or None

                service_calls.append(
                    ServiceCall(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        service=service,
                        location=location,
                        target=action.get("target"),
                        data=merged_data,
                        is_template=is_template,
                    )
                )

            # Choose branches
            if "choose" in action:
                options = cast(list[Any], action.get("choose") or [])
                if isinstance(options, list):  # pyright: ignore[reportUnnecessaryIsInstance]
                    for opt_idx, option in enumerate(options):
                        if isinstance(option, dict):
                            sequence = cast(list[Any], option.get("sequence") or [])
                            self._extract_service_calls_from_actions(
                                sequence,
                                automation_id,
                                automation_name,
                                f"{location}.choose[{opt_idx}].sequence",
                                service_calls,
                                _depth + 1,
                            )

                # Default branch
                default = cast(list[Any], action.get("default") or [])
                if default:
                    self._extract_service_calls_from_actions(
                        default,
                        automation_id,
                        automation_name,
                        f"{location}.default",
                        service_calls,
                        _depth + 1,
                    )

            # If/then/else
            if "if" in action:
                then_actions = action.get("then", [])
                self._extract_service_calls_from_actions(
                    then_actions,
                    automation_id,
                    automation_name,
                    f"{location}.then",
                    service_calls,
                    _depth + 1,
                )
                else_actions = action.get("else", [])
                if else_actions:
                    self._extract_service_calls_from_actions(
                        else_actions,
                        automation_id,
                        automation_name,
                        f"{location}.else",
                        service_calls,
                        _depth + 1,
                    )

            # Repeat
            if "repeat" in action:
                repeat_config = action["repeat"]
                if isinstance(repeat_config, dict):
                    repeat_config = cast(dict[str, Any], repeat_config)
                    sequence = cast(list[Any], repeat_config.get("sequence") or [])
                    self._extract_service_calls_from_actions(
                        sequence,
                        automation_id,
                        automation_name,
                        f"{location}.repeat.sequence",
                        service_calls,
                        _depth + 1,
                    )

            # Parallel
            if "parallel" in action:
                branches = cast(list[Any], action.get("parallel") or [])
                if not isinstance(branches, list):  # pyright: ignore[reportUnnecessaryIsInstance]
                    branches = [branches]
                for branch in branches:
                    if isinstance(branch, list):
                        self._extract_service_calls_from_actions(
                            cast(list[dict[str, Any]], branch),
                            automation_id,
                            automation_name,
                            f"{location}.parallel",
                            service_calls,
                            _depth + 1,
                        )
                    elif isinstance(branch, dict):
                        self._extract_service_calls_from_actions(
                            [branch],
                            automation_id,
                            automation_name,
                            f"{location}.parallel",
                            service_calls,
                            _depth + 1,
                        )
