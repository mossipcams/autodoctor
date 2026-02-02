"""Jinja2 template syntax validator for Home Assistant automations."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import jinja2.nodes as nodes
from jinja2 import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from .ha_catalog import get_known_filters, get_known_tests
from .models import IssueType, Severity, ValidationIssue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Pattern to detect if a string contains Jinja2 template syntax
TEMPLATE_PATTERN = re.compile(r"\{[{%#]")

# Maximum nesting depth for template condition/action traversal.
# Intentionally lower than const.MAX_RECURSION_DEPTH (50) because templates
# rarely nest deeply and this provides a tighter safety net for parsing.
_TEMPLATE_MAX_NESTING_DEPTH = 20


def _ensure_list(value: Any) -> list:
    """Wrap a value in a list if it isn't one already."""
    if not isinstance(value, list):
        return [value] if value is not None else []
    return value


class JinjaValidator:
    """Validates Jinja2 template syntax in automations."""

    def __init__(
        self,
        hass: HomeAssistant | None = None,
        strict_template_validation: bool = False,
    ) -> None:
        """Initialize the Jinja validator.

        Args:
            hass: Home Assistant instance (optional, for HA-specific template env)
            strict_template_validation: If True, warn about unknown filters/tests.
                Disable if using custom components that add custom Jinja filters.
        """
        self.hass = hass
        self._strict_validation = strict_template_validation
        # Use a sandboxed environment for safe parsing
        self._env = SandboxedEnvironment(extensions=["jinja2.ext.loopcontrols"])
        self._known_filters: frozenset[str] = (
            frozenset(self._env.filters.keys()) | get_known_filters()
        )
        self._known_tests: frozenset[str] = (
            frozenset(self._env.tests.keys()) | get_known_tests()
        )

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
            auto_id = f"automation.{auto.get('id', 'unknown')}"
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
        triggers = _ensure_list(
            automation.get("triggers") or automation.get("trigger", [])
        )
        for idx, trigger in enumerate(triggers):
            if isinstance(trigger, dict):
                issues.extend(
                    self._validate_trigger(trigger, idx, auto_id, auto_name, auto_vars)
                )

        # Validate conditions
        conditions = _ensure_list(
            automation.get("conditions") or automation.get("condition", [])
        )
        for idx, condition in enumerate(conditions):
            issues.extend(
                self._validate_condition(
                    condition, idx, auto_id, auto_name, "condition", auto_vars=auto_vars
                )
            )

        # Validate actions
        actions = _ensure_list(
            automation.get("actions") or automation.get("action", [])
        )
        issues.extend(
            self._validate_actions(actions, auto_id, auto_name, auto_vars=auto_vars)
        )

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
            issues.extend(
                self._check_template(
                    value_template,
                    f"trigger[{index}].value_template",
                    auto_id,
                    auto_name,
                    auto_vars=auto_vars,
                )
            )

        # Check to/from fields for Jinja expressions (template triggers)
        for field_name in ("to", "from"):
            field_value = trigger.get(field_name)
            if (
                field_value
                and isinstance(field_value, str)
                and self._is_template(field_value)
            ):
                issues.extend(
                    self._check_template(
                        field_value,
                        f"trigger[{index}].{field_name}",
                        auto_id,
                        auto_name,
                        auto_vars=auto_vars,
                    )
                )

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

        if _depth > _TEMPLATE_MAX_NESTING_DEPTH:
            _LOGGER.warning(
                "Max recursion depth exceeded in %s at %s, stopping validation",
                auto_id,
                location_prefix,
            )
            return issues

        # String condition (template shorthand)
        if isinstance(condition, str):
            if self._is_template(condition):
                issues.extend(
                    self._check_template(
                        condition,
                        f"{location_prefix}[{index}]",
                        auto_id,
                        auto_name,
                        auto_vars=auto_vars,
                    )
                )
            return issues

        if not isinstance(condition, dict):
            return issues

        # Check value_template
        value_template = condition.get("value_template")
        if value_template and isinstance(value_template, str):
            issues.extend(
                self._check_template(
                    value_template,
                    f"{location_prefix}[{index}].value_template",
                    auto_id,
                    auto_name,
                    auto_vars=auto_vars,
                )
            )

        # Check nested conditions (and/or/not)
        for key in ("conditions", "and", "or", "not"):
            nested = _ensure_list(condition.get(key, []))
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

        if _depth > _TEMPLATE_MAX_NESTING_DEPTH:
            _LOGGER.warning(
                "Max recursion depth exceeded in %s at %s, stopping validation",
                auto_id,
                location_prefix,
            )
            return issues

        actions = _ensure_list(actions)

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
                        data,
                        f"{location}.data",
                        auto_id,
                        auto_name,
                        auto_vars=action_level_vars,
                    )
                )

            # Check wait_template
            wait_template = action.get("wait_template")
            if wait_template and isinstance(wait_template, str):
                issues.extend(
                    self._check_template(
                        wait_template,
                        f"{location}.wait_template",
                        auto_id,
                        auto_name,
                        auto_vars=action_level_vars,
                    )
                )

            # Check choose blocks
            if "choose" in action:
                for opt_idx, option in enumerate(action.get("choose", [])):
                    if not isinstance(option, dict):
                        continue

                    # Validate conditions in option
                    opt_conditions = _ensure_list(option.get("conditions", []))
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
                            default,
                            auto_id,
                            auto_name,
                            f"{location}.default",
                            _depth + 1,
                            auto_vars=action_level_vars,
                        )
                    )

            # Check if/then/else blocks
            if "if" in action:
                if_conditions = _ensure_list(action.get("if", []))
                for cond_idx, cond in enumerate(if_conditions):
                    issues.extend(
                        self._validate_condition(
                            cond,
                            cond_idx,
                            auto_id,
                            auto_name,
                            f"{location}.if",
                            auto_vars=action_level_vars,
                        )
                    )

                then_actions = action.get("then", [])
                issues.extend(
                    self._validate_actions(
                        then_actions,
                        auto_id,
                        auto_name,
                        f"{location}.then",
                        _depth + 1,
                        auto_vars=action_level_vars,
                    )
                )

                else_actions = action.get("else", [])
                if else_actions:
                    issues.extend(
                        self._validate_actions(
                            else_actions,
                            auto_id,
                            auto_name,
                            f"{location}.else",
                            _depth + 1,
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
                    repeat_conditions = _ensure_list(repeat_config.get(cond_key, []))
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
                        sequence,
                        auto_id,
                        auto_name,
                        f"{location}.repeat.sequence",
                        _depth + 1,
                        auto_vars=action_level_vars,
                    )
                )

            # Check parallel blocks
            if "parallel" in action:
                branches = _ensure_list(action["parallel"])
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
                issues.extend(
                    self._check_template(
                        value,
                        f"{location}.{key}",
                        auto_id,
                        auto_name,
                        auto_vars=auto_vars,
                    )
                )
            elif isinstance(value, dict):
                issues.extend(
                    self._validate_data_templates(
                        value,
                        f"{location}.{key}",
                        auto_id,
                        auto_name,
                        auto_vars=auto_vars,
                    )
                )
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, str) and self._is_template(item):
                        issues.extend(
                            self._check_template(
                                item,
                                f"{location}.{key}[{idx}]",
                                auto_id,
                                auto_name,
                                auto_vars=auto_vars,
                            )
                        )
                    elif isinstance(item, dict):
                        issues.extend(
                            self._validate_data_templates(
                                item,
                                f"{location}.{key}[{idx}]",
                                auto_id,
                                auto_name,
                                auto_vars=auto_vars,
                            )
                        )

        return issues

    def _is_template(self, value: str) -> bool:
        """Check if a string contains Jinja2 template syntax."""
        return bool(TEMPLATE_PATTERN.search(value))

    def _check_ast_semantics(
        self,
        ast: nodes.Template,
        location: str,
        auto_id: str,
        auto_name: str,
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
                _LOGGER.debug(
                    "Found filter: %s, known: %s",
                    node.name,
                    node.name in self._known_filters,
                )
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
        except Exception:
            _LOGGER.warning(
                "Unexpected error checking template at %s in %s, skipping",
                location,
                auto_id,
                exc_info=True,
            )
            return []

        return self._check_ast_semantics(ast, location, auto_id, auto_name)
