"""Jinja2 template syntax validator for Home Assistant automations."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import jinja2.nodes as nodes
from jinja2 import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from .models import IssueType, Severity, ValidationIssue
from .template_semantics import (
    ENTITY_ID_FUNCTIONS,
    ENTITY_ID_PATTERN,
    FILTER_SIGNATURES,
    KNOWN_CALLABLE_GLOBALS,
    KNOWN_GLOBALS,
    TEST_SIGNATURES,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Pattern to detect if a string contains Jinja2 template syntax
TEMPLATE_PATTERN = re.compile(r"\{[{%#]")

# Maximum recursion depth for nested conditions/actions
MAX_RECURSION_DEPTH = 20

# HA-specific filters (added on top of Jinja2 built-ins).
# Source: https://www.home-assistant.io/docs/configuration/templating
_HA_FILTERS: frozenset[str] = frozenset({
    # Datetime / timestamp
    "as_datetime", "as_timestamp", "as_local", "as_timedelta",
    "timestamp_custom", "timestamp_local", "timestamp_utc",
    "relative_time", "time_since", "time_until",
    # JSON
    "to_json", "from_json",
    # Type conversion (override Jinja2 built-ins)
    "float", "int", "bool",
    # Validation
    "is_defined", "is_number", "has_value",
    # Math
    "log", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sqrt",
    "multiply", "add", "average", "median", "statistical_mode",
    "clamp", "wrap", "remap",
    # Bitwise
    "bitwise_and", "bitwise_or", "bitwise_xor", "ord",
    # Encoding
    "base64_encode", "base64_decode", "from_hex",
    # Hashing
    "md5", "sha1", "sha256", "sha512",
    # Regex
    "regex_match", "regex_search", "regex_replace",
    "regex_findall", "regex_findall_index",
    # String
    "slugify", "ordinal",
    # Collections
    "set", "shuffle", "flatten",
    "intersect", "difference", "symmetric_difference", "union", "combine",
    "contains",
    # Entity / device / area / floor / label lookups
    "expand", "closest", "distance",
    "state_attr", "is_state_attr", "is_state", "state_translated",
    "is_hidden_entity",
    "device_entities", "device_attr", "is_device_attr", "device_id", "device_name",
    "config_entry_id", "config_entry_attr",
    "area_id", "area_name", "area_entities", "area_devices",
    "floor_id", "floor_name", "floor_areas", "floor_entities",
    "label_id", "label_name", "label_description",
    "label_areas", "label_devices", "label_entities",
    "integration_entities",
    # Misc
    "iif", "version", "pack", "unpack",
    "apply", "as_function", "merge_response", "typeof",
})

# HA-specific tests (added on top of Jinja2 built-ins).
_HA_TESTS: frozenset[str] = frozenset({
    "match", "search",
    "is_number", "has_value", "contains",
    "is_list", "is_set", "is_tuple", "is_datetime", "is_string_like",
    "is_boolean", "is_callable", "is_float", "is_integer",
    "is_iterable", "is_mapping", "is_sequence", "is_string",
    "is_state", "is_state_attr", "is_device_attr", "is_hidden_entity",
    "apply",
})


class JinjaValidator:
    """Validates Jinja2 template syntax in automations."""

    def __init__(
        self,
        hass: HomeAssistant | None = None,
        knowledge_base: Any = None,
        strict_template_validation: bool = False,
    ) -> None:
        """Initialize the Jinja validator.

        Args:
            hass: Home Assistant instance (optional, for HA-specific template env)
            knowledge_base: Shared StateKnowledgeBase instance (avoids creating new ones)
            strict_template_validation: If True, warn about unknown filters/tests.
                Disable if using custom components that add custom Jinja filters.
        """
        self.hass = hass
        self.knowledge_base = knowledge_base
        self._strict_validation = strict_template_validation
        # Use a sandboxed environment for safe parsing
        self._env = SandboxedEnvironment(extensions=["jinja2.ext.loopcontrols"])
        self._known_filters: frozenset[str] = frozenset(self._env.filters.keys()) | _HA_FILTERS
        self._known_tests: frozenset[str] = frozenset(self._env.tests.keys()) | _HA_TESTS

    def validate_automations(
        self, automations: list[dict[str, Any]]
    ) -> list[ValidationIssue]:
        """Validate all templates in a list of automations.

        Args:
            automations: List of automation configurations

        Returns:
            List of validation issues for template syntax errors
        """
        issues: list[ValidationIssue] = []

        for auto in automations:
            auto_id = f"automation.{auto.get("id", "unknown")}"
            auto_name = auto.get("alias", auto_id)
            issues.extend(self._validate_automation(auto, auto_id, auto_name))

        return issues

    def _validate_automation(
        self,
        automation: dict[str, Any],
        auto_id: str,
        auto_name: str,
    ) -> list[ValidationIssue]:
        """Validate all templates in a single automation."""
        issues: list[ValidationIssue] = []

        # Extract automation-level variables (from variables: section or blueprint inputs)
        # These are injected into the template context at runtime
        auto_vars = self._extract_automation_variables(automation)

        # Validate triggers
        triggers = automation.get("triggers") or automation.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers]
        for idx, trigger in enumerate(triggers):
            if isinstance(trigger, dict):
                issues.extend(self._validate_trigger(trigger, idx, auto_id, auto_name, auto_vars))

        # Validate conditions
        conditions = automation.get("conditions") or automation.get("condition", [])
        if not isinstance(conditions, list):
            conditions = [conditions]
        for idx, condition in enumerate(conditions):
            issues.extend(
                self._validate_condition(
                    condition, idx, auto_id, auto_name, "condition", auto_vars=auto_vars
                )
            )

        # Validate actions
        actions = automation.get("actions") or automation.get("action", [])
        if not isinstance(actions, list):
            actions = [actions]
        issues.extend(self._validate_actions(actions, auto_id, auto_name, auto_vars=auto_vars))

        return issues

    def _extract_automation_variables(self, automation: dict[str, Any]) -> set[str]:
        """Extract variable names defined at the automation level.

        Collects variables from the automation's 'variables' section.
        These are injected into the template context at runtime and are
        available to all templates in the automation (triggers, conditions,
        actions). Blueprint-based automations use this section to expose
        blueprint input values as template variables.
        """
        auto_vars: set[str] = set()

        variables = automation.get("variables")
        if isinstance(variables, dict):
            auto_vars.update(variables.keys())

        return auto_vars

    def _validate_trigger(
        self,
        trigger: dict[str, Any],
        index: int,
        auto_id: str,
        auto_name: str,
        auto_vars: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate templates in a trigger."""
        issues: list[ValidationIssue] = []

        # Check value_template
        value_template = trigger.get("value_template")
        if value_template and isinstance(value_template, str):
            issues.extend(self._check_template(
                value_template, f"trigger[{index}].value_template", auto_id, auto_name,
                auto_vars=auto_vars,
            ))

        return issues

    def _validate_condition(
        self,
        condition: Any,
        index: int,
        auto_id: str,
        auto_name: str,
        location_prefix: str,
        _depth: int = 0,
        auto_vars: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate templates in a condition."""
        issues: list[ValidationIssue] = []

        if _depth > MAX_RECURSION_DEPTH:
            _LOGGER.warning(
                "Max recursion depth exceeded in %s at %s, stopping validation",
                auto_id, location_prefix
            )
            return issues

        # String condition (template shorthand)
        if isinstance(condition, str):
            if self._is_template(condition):
                issues.extend(self._check_template(
                    condition, f"{location_prefix}[{index}]", auto_id, auto_name,
                    auto_vars=auto_vars,
                ))
            return issues

        if not isinstance(condition, dict):
            return issues

        # Check value_template
        value_template = condition.get("value_template")
        if value_template and isinstance(value_template, str):
            issues.extend(self._check_template(
                value_template,
                f"{location_prefix}[{index}].value_template",
                auto_id,
                auto_name,
                auto_vars=auto_vars,
            ))

        # Check nested conditions (and/or/not)
        for key in ("conditions", "and", "or"):
            nested = condition.get(key, [])
            if not isinstance(nested, list):
                nested = [nested]
            for nested_idx, nested_cond in enumerate(nested):
                issues.extend(
                    self._validate_condition(
                        nested_cond,
                        nested_idx,
                        auto_id,
                        auto_name,
                        f"{location_prefix}[{index}].{key}",
                        _depth + 1,
                        auto_vars=auto_vars,
                    )
                )

        # Check 'not' condition
        not_cond = condition.get("not")
        if not_cond:
            if isinstance(not_cond, list):
                for nested_idx, nested_cond in enumerate(not_cond):
                    issues.extend(
                        self._validate_condition(
                            nested_cond,
                            nested_idx,
                            auto_id,
                            auto_name,
                            f"{location_prefix}[{index}].not",
                            _depth + 1,
                            auto_vars=auto_vars,
                        )
                    )
            else:
                issues.extend(
                    self._validate_condition(
                        not_cond,
                        0,
                        auto_id,
                        auto_name,
                        f"{location_prefix}[{index}].not",
                        _depth + 1,
                        auto_vars=auto_vars,
                    )
                )

        return issues

    def _validate_actions(
        self,
        actions: list[Any],
        auto_id: str,
        auto_name: str,
        location_prefix: str = "action",
        _depth: int = 0,
        auto_vars: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate templates in actions recursively."""
        issues: list[ValidationIssue] = []

        if _depth > MAX_RECURSION_DEPTH:
            _LOGGER.warning(
                "Max recursion depth exceeded in %s at %s, stopping validation",
                auto_id, location_prefix
            )
            return issues

        if not isinstance(actions, list):
            actions = [actions]

        # Accumulate variables across the action sequence.
        # In HA, a variables: action makes those names available to all
        # subsequent actions in the same sequence.
        accumulated_vars = set(auto_vars) if auto_vars else set()

        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                continue

            location = f"{location_prefix}[{idx}]"

            # Collect variables defined at this action level and add to
            # accumulated scope so later actions in the sequence can see them
            action_variables = action.get("variables")
            if isinstance(action_variables, dict):
                accumulated_vars = accumulated_vars | set(action_variables.keys())

            action_level_vars = accumulated_vars

            # Check service/action data for templates
            data = action.get("data", {})
            if isinstance(data, dict):
                issues.extend(
                    self._validate_data_templates(
                        data, f"{location}.data", auto_id, auto_name,
                        auto_vars=action_level_vars,
                    )
                )

            # Check wait_template
            wait_template = action.get("wait_template")
            if wait_template and isinstance(wait_template, str):
                issues.extend(self._check_template(
                    wait_template, f"{location}.wait_template", auto_id, auto_name,
                    auto_vars=action_level_vars,
                ))

            # Check choose blocks
            if "choose" in action:
                for opt_idx, option in enumerate(action.get("choose", [])):
                    if not isinstance(option, dict):
                        continue

                    # Validate conditions in option
                    opt_conditions = option.get("conditions", [])
                    if not isinstance(opt_conditions, list):
                        opt_conditions = [opt_conditions]
                    for cond_idx, cond in enumerate(opt_conditions):
                        issues.extend(
                            self._validate_condition(
                                cond,
                                cond_idx,
                                auto_id,
                                auto_name,
                                f"{location}.choose[{opt_idx}].conditions",
                                auto_vars=action_level_vars,
                            )
                        )

                    # Recurse into sequence
                    sequence = option.get("sequence", [])
                    issues.extend(
                        self._validate_actions(
                            sequence,
                            auto_id,
                            auto_name,
                            f"{location}.choose[{opt_idx}].sequence",
                            _depth + 1,
                            auto_vars=action_level_vars,
                        )
                    )

                # Recurse into default
                default = action.get("default", [])
                if default:
                    issues.extend(
                        self._validate_actions(
                            default, auto_id, auto_name, f"{location}.default", _depth + 1,
                            auto_vars=action_level_vars,
                        )
                    )

            # Check if/then/else blocks
            if "if" in action:
                if_conditions = action.get("if", [])
                if not isinstance(if_conditions, list):
                    if_conditions = [if_conditions]
                for cond_idx, cond in enumerate(if_conditions):
                    issues.extend(
                        self._validate_condition(
                            cond, cond_idx, auto_id, auto_name, f"{location}.if",
                            auto_vars=action_level_vars,
                        )
                    )

                then_actions = action.get("then", [])
                issues.extend(
                    self._validate_actions(
                        then_actions, auto_id, auto_name, f"{location}.then", _depth + 1,
                        auto_vars=action_level_vars,
                    )
                )

                else_actions = action.get("else", [])
                if else_actions:
                    issues.extend(
                        self._validate_actions(
                            else_actions, auto_id, auto_name, f"{location}.else", _depth + 1,
                            auto_vars=action_level_vars,
                        )
                    )

            # Check repeat blocks
            if "repeat" in action:
                repeat_config = action.get("repeat")
                if not isinstance(repeat_config, dict):
                    continue

                # Check while/until conditions
                for cond_key in ("while", "until"):
                    repeat_conditions = repeat_config.get(cond_key, [])
                    if not isinstance(repeat_conditions, list):
                        repeat_conditions = [repeat_conditions]
                    for cond_idx, cond in enumerate(repeat_conditions):
                        issues.extend(
                            self._validate_condition(
                                cond,
                                cond_idx,
                                auto_id,
                                auto_name,
                                f"{location}.repeat.{cond_key}",
                                auto_vars=action_level_vars,
                            )
                        )

                # Recurse into sequence
                sequence = repeat_config.get("sequence", [])
                issues.extend(
                    self._validate_actions(
                        sequence, auto_id, auto_name, f"{location}.repeat.sequence", _depth + 1,
                        auto_vars=action_level_vars,
                    )
                )

            # Check parallel blocks
            if "parallel" in action:
                branches = action["parallel"]
                if not isinstance(branches, list):
                    branches = [branches]
                for branch_idx, branch in enumerate(branches):
                    branch_actions = branch if isinstance(branch, list) else [branch]
                    issues.extend(
                        self._validate_actions(
                            branch_actions,
                            auto_id,
                            auto_name,
                            f"{location}.parallel[{branch_idx}]",
                            _depth + 1,
                            auto_vars=action_level_vars,
                        )
                    )

        return issues

    def _validate_data_templates(
        self,
        data: dict[str, Any],
        location: str,
        auto_id: str,
        auto_name: str,
        auto_vars: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Validate templates in action data fields."""
        issues: list[ValidationIssue] = []

        for key, value in data.items():
            if isinstance(value, str) and self._is_template(value):
                issues.extend(self._check_template(
                    value, f"{location}.{key}", auto_id, auto_name,
                    auto_vars=auto_vars,
                ))
            elif isinstance(value, dict):
                issues.extend(
                    self._validate_data_templates(
                        value, f"{location}.{key}", auto_id, auto_name,
                        auto_vars=auto_vars,
                    )
                )
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, str) and self._is_template(item):
                        issues.extend(self._check_template(
                            item, f"{location}.{key}[{idx}]", auto_id, auto_name,
                            auto_vars=auto_vars,
                        ))
                    elif isinstance(item, dict):
                        issues.extend(
                            self._validate_data_templates(
                                item, f"{location}.{key}[{idx}]", auto_id, auto_name,
                                auto_vars=auto_vars,
                            )
                        )

        return issues

    def _is_template(self, value: str) -> bool:
        """Check if a string contains Jinja2 template syntax."""
        return bool(TEMPLATE_PATTERN.search(value))

    def _extract_entity_references(
        self,
        template: str,
        location: str,
        auto_id: str,
        auto_name: str,
    ) -> list["StateReference"]:
        """Extract entity references from template using analyzer patterns.

        Reuses regex patterns from AutomationAnalyzer._extract_from_template()
        to find all entity references in the template.
        """
        # Import analyzer patterns (avoid circular import at module level)
        from .analyzer import (
            IS_STATE_PATTERN,
            IS_STATE_ATTR_PATTERN,
            STATE_ATTR_PATTERN,
            STATES_OBJECT_PATTERN,
            STATES_FUNCTION_PATTERN,
            EXPAND_PATTERN,
            AREA_ENTITIES_PATTERN,
            DEVICE_ENTITIES_PATTERN,
            INTEGRATION_ENTITIES_PATTERN,
            JINJA_COMMENT_PATTERN,
        )
        from .models import StateReference

        refs: list[StateReference] = []

        # Strip Jinja2 comments before parsing
        template = JINJA_COMMENT_PATTERN.sub("", template)

        # Extract is_state() calls - captures entity_id AND state value
        for match in IS_STATE_PATTERN.finditer(template):
            entity_id, state = match.groups()
            refs.append(
                StateReference(
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id=entity_id,
                    expected_state=state,  # Capture state for validation
                    expected_attribute=None,
                    location=f"{location}.is_state",
                )
            )

        # Extract is_state_attr() calls - captures entity_id, attribute, AND value
        for match in IS_STATE_ATTR_PATTERN.finditer(template):
            entity_id, attribute, _value = match.groups()
            refs.append(
                StateReference(
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=attribute,  # Capture for validation
                    location=f"{location}.is_state_attr",
                )
            )

        # Extract state_attr() calls
        for match in STATE_ATTR_PATTERN.finditer(template):
            entity_id, attribute = match.groups()
            refs.append(
                StateReference(
                    automation_id=auto_id,
                    automation_name=auto_name,
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
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.states_object",
                    )
                )

        # Extract states('entity_id') function calls
        for match in STATES_FUNCTION_PATTERN.finditer(template):
            entity_id = match.group(1)
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.states_function",
                    )
                )

        # Extract expand() calls
        for match in EXPAND_PATTERN.finditer(template):
            entity_id = match.group(1)
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=auto_id,
                        automation_name=auto_name,
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
                        automation_id=auto_id,
                        automation_name=auto_name,
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
                        automation_id=auto_id,
                        automation_name=auto_name,
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
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=integration_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.integration_entities",
                        reference_type="integration",
                    )
                )

        return refs

    def _validate_entity_references(
        self,
        refs: list["StateReference"],
    ) -> list[ValidationIssue]:
        """Validate entity references using knowledge base.

        Checks:
        - Entity existence
        - State value validity (for is_state calls)
        - Attribute existence (for state_attr/is_state_attr calls)

        Args:
            refs: List of StateReferences extracted from templates

        Returns:
            List of ValidationIssues found
        """
        if not self.hass:
            return []  # Can't validate without hass instance

        issues: list[ValidationIssue] = []

        for ref in refs:
            # 1. Check entity existence
            state = self.hass.states.get(ref.entity_id)

            # Handle special reference types
            if ref.reference_type == "zone":
                if not state:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_ZONE_NOT_FOUND,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Zone '{ref.entity_id}' referenced in template does not exist",
                        )
                    )
                continue

            elif ref.reference_type == "device":
                # Check device registry
                from homeassistant.helpers import device_registry as dr

                device_reg = dr.async_get(self.hass)
                if not device_reg.async_get(ref.entity_id):
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_DEVICE_NOT_FOUND,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Device '{ref.entity_id}' referenced in template does not exist",
                        )
                    )
                continue

            elif ref.reference_type == "area":
                # Check area registry
                from homeassistant.helpers import area_registry as ar

                area_reg = ar.async_get(self.hass)
                if not area_reg.async_get_area(ref.entity_id):
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_AREA_NOT_FOUND,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Area '{ref.entity_id}' referenced in template does not exist",
                        )
                    )
                continue

            # Standard entity validation
            if not state:
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.TEMPLATE_ENTITY_NOT_FOUND,
                        severity=Severity.ERROR,
                        automation_id=ref.automation_id,
                        automation_name=ref.automation_name,
                        entity_id=ref.entity_id,
                        location=ref.location,
                        message=f"Entity '{ref.entity_id}' referenced in template does not exist",
                    )
                )
                continue

            # 2. Validate attribute existence if specified
            if ref.expected_attribute:
                if ref.expected_attribute not in state.attributes:
                    available_attrs = sorted(state.attributes.keys())[:10]
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Attribute '{ref.expected_attribute}' not found on {ref.entity_id}",
                            suggestion=f"Available attributes: {', '.join(available_attrs)}",
                        )
                    )

            # 3. Validate state value if specified (from is_state calls)
            #    Only for domains in the whitelist with stable state values.
            if ref.expected_state:
                from .const import STATE_VALIDATION_WHITELIST

                entity_domain = ref.entity_id.split(".")[0] if "." in ref.entity_id else ""
                if entity_domain not in STATE_VALIDATION_WHITELIST:
                    continue

                # Use shared knowledge base if available, otherwise create one
                kb = self.knowledge_base
                if kb is None:
                    from .knowledge_base import StateKnowledgeBase

                    kb = StateKnowledgeBase(self.hass)
                valid_states = kb.get_valid_states(ref.entity_id)

                if valid_states and ref.expected_state not in valid_states:
                    # Check for case mismatch
                    if ref.expected_state.lower() in {s.lower() for s in valid_states}:
                        severity = Severity.WARNING
                        issue_type = IssueType.CASE_MISMATCH
                    else:
                        severity = Severity.ERROR
                        issue_type = IssueType.TEMPLATE_INVALID_STATE

                    issues.append(
                        ValidationIssue(
                            issue_type=issue_type,
                            severity=severity,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"State '{ref.expected_state}' is not valid for {ref.entity_id}",
                            suggestion=f"Valid states: {', '.join(sorted(valid_states)[:10])}",
                            valid_states=list(valid_states),
                        )
                    )

        return issues


    def _check_ast_semantics(
        self,
        ast: nodes.Template,
        location: str,
        auto_id: str,
        auto_name: str,
        auto_vars: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Walk the parsed AST to check for semantic issues.

        Note: Variable reference validation was removed in v2.7.0 due to high
        false positive rate with blueprint automations.
        """
        issues: list[ValidationIssue] = []

        # Filter/test validation is opt-in via strict_template_validation config.
        # Custom components may add custom Jinja filters/tests that we don't know
        # about, leading to false positives when strict mode is off.
        if self._strict_validation:
            for node in ast.find_all(nodes.Filter):
                _LOGGER.debug(f"Found filter: {node.name}, known: {node.name in self._known_filters}")
                if node.name not in self._known_filters:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_UNKNOWN_FILTER,
                            severity=Severity.WARNING,
                            automation_id=auto_id,
                            automation_name=auto_name,
                            entity_id="",
                            location=location,
                            message=f"Unknown filter '{node.name}' — not a built-in Jinja2 or Home Assistant filter",
                        )
                    )
                else:
                    # Validate arguments for known filters
                    _LOGGER.debug(f"Calling _validate_filter_args for {node.name}")
                    issues.extend(self._validate_filter_args(node, location, auto_id, auto_name))

            for node in ast.find_all(nodes.Test):
                if node.name not in self._known_tests:
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_UNKNOWN_TEST,
                            severity=Severity.WARNING,
                            automation_id=auto_id,
                            automation_name=auto_name,
                            entity_id="",
                            location=location,
                            message=f"Unknown test '{node.name}' — not a built-in Jinja2 or Home Assistant test",
                        )
                    )

        return issues

    def _validate_filter_args(
        self,
        node: nodes.Filter,
        location: str,
        auto_id: str,
        auto_name: str,
    ) -> list[ValidationIssue]:
        """Validate filter argument count."""
        sig = FILTER_SIGNATURES.get(node.name)
        if not sig:
            return []  # Unknown filter already handled elsewhere

        # Count arguments - args can be None or a list
        arg_count = len(node.args) if node.args else 0
        _LOGGER.debug(f"Validating filter '{node.name}': args={arg_count}, min={sig.min_args}, max={sig.max_args}")

        if arg_count < sig.min_args or (sig.max_args is not None and arg_count > sig.max_args):
            if sig.max_args is None:
                expected = f"{sig.min_args}+"
            elif sig.min_args == sig.max_args:
                expected = str(sig.min_args)
            else:
                expected = f"{sig.min_args}-{sig.max_args}"

            return [
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_INVALID_ARGUMENTS,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Filter '{node.name}' expects {expected} arguments, got {arg_count}",
                )
            ]
        return []

    def _collect_template_variables(self, ast: nodes.Template) -> set[str]:
        """Collect all variables defined in the template."""
        defined_vars = set()

        # Collect from {% set var = ... %}
        for node in ast.find_all(nodes.Assign):
            if isinstance(node.target, nodes.Name):
                defined_vars.add(node.target.name)

        # Collect from {% for var in ... %}
        for node in ast.find_all(nodes.For):
            if isinstance(node.target, nodes.Name):
                defined_vars.add(node.target.name)

        return defined_vars

    def _check_template(
        self,
        template: str,
        location: str,
        auto_id: str,
        auto_name: str,
        auto_vars: set[str] | None = None,
    ) -> list[ValidationIssue]:
        """Check a template for syntax errors and semantic issues.

        Returns a list of ValidationIssues (empty if no problems).
        """
        try:
            ast = self._env.parse(template)
        except TemplateSyntaxError as err:
            error_msg = str(err.message) if err.message else str(err)
            line_info = f" (line {err.lineno})" if err.lineno else ""
            return [
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_SYNTAX_ERROR,
                    severity=Severity.ERROR,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Jinja2 syntax error{line_info}: {error_msg}",
                    suggestion=None,
                )
            ]
        except Exception as err:
            return [
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_SYNTAX_ERROR,
                    severity=Severity.ERROR,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Template error: {err}",
                    suggestion=None,
                )
            ]

        issues = []

        # 2. Semantic check for filters/tests (existing)
        issues.extend(self._check_ast_semantics(ast, location, auto_id, auto_name, auto_vars=auto_vars))

        # 3. NEW: Semantic check for entity references
        refs = self._extract_entity_references(template, location, auto_id, auto_name)
        issues.extend(self._validate_entity_references(refs))

        return issues
