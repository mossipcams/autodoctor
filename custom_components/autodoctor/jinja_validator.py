"""Jinja2 template syntax validator for Home Assistant automations."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from jinja2 import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from .models import IssueType, Severity, ValidationIssue

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Pattern to detect if a string contains Jinja2 template syntax
TEMPLATE_PATTERN = re.compile(r"\{[{%#]")

# Maximum recursion depth for nested conditions/actions
MAX_RECURSION_DEPTH = 20


class JinjaValidator:
    """Validates Jinja2 template syntax in automations."""

    def __init__(self, hass: HomeAssistant | None = None) -> None:
        """Initialize the Jinja validator.

        Args:
            hass: Home Assistant instance (optional, for HA-specific template env)
        """
        self.hass = hass
        # Use a sandboxed environment for safe parsing
        self._env = SandboxedEnvironment(extensions=["jinja2.ext.loopcontrols"])

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

        # Validate triggers
        triggers = automation.get("triggers") or automation.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers]
        for idx, trigger in enumerate(triggers):
            if isinstance(trigger, dict):
                issues.extend(self._validate_trigger(trigger, idx, auto_id, auto_name))

        # Validate conditions
        conditions = automation.get("conditions") or automation.get("condition", [])
        if not isinstance(conditions, list):
            conditions = [conditions]
        for idx, condition in enumerate(conditions):
            issues.extend(
                self._validate_condition(
                    condition, idx, auto_id, auto_name, "condition"
                )
            )

        # Validate actions
        actions = automation.get("actions") or automation.get("action", [])
        if not isinstance(actions, list):
            actions = [actions]
        issues.extend(self._validate_actions(actions, auto_id, auto_name))

        return issues

    def _validate_trigger(
        self,
        trigger: dict[str, Any],
        index: int,
        auto_id: str,
        auto_name: str,
    ) -> list[ValidationIssue]:
        """Validate templates in a trigger."""
        issues: list[ValidationIssue] = []

        # Check value_template
        value_template = trigger.get("value_template")
        if value_template and isinstance(value_template, str):
            issue = self._check_template(
                value_template, f"trigger[{index}].value_template", auto_id, auto_name
            )
            if issue:
                issues.append(issue)

        return issues

    def _validate_condition(
        self,
        condition: Any,
        index: int,
        auto_id: str,
        auto_name: str,
        location_prefix: str,
        _depth: int = 0,
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
                issue = self._check_template(
                    condition, f"{location_prefix}[{index}]", auto_id, auto_name
                )
                if issue:
                    issues.append(issue)
            return issues

        if not isinstance(condition, dict):
            return issues

        # Check value_template
        value_template = condition.get("value_template")
        if value_template and isinstance(value_template, str):
            issue = self._check_template(
                value_template,
                f"{location_prefix}[{index}].value_template",
                auto_id,
                auto_name,
            )
            if issue:
                issues.append(issue)

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

        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                continue

            location = f"{location_prefix}[{idx}]"

            # Check service/action data for templates
            data = action.get("data", {})
            if isinstance(data, dict):
                issues.extend(
                    self._validate_data_templates(
                        data, f"{location}.data", auto_id, auto_name
                    )
                )

            # Check wait_template
            wait_template = action.get("wait_template")
            if wait_template and isinstance(wait_template, str):
                issue = self._check_template(
                    wait_template, f"{location}.wait_template", auto_id, auto_name
                )
                if issue:
                    issues.append(issue)

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
                        )
                    )

                # Recurse into default
                default = action.get("default", [])
                if default:
                    issues.extend(
                        self._validate_actions(
                            default, auto_id, auto_name, f"{location}.default", _depth + 1
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
                            cond, cond_idx, auto_id, auto_name, f"{location}.if"
                        )
                    )

                then_actions = action.get("then", [])
                issues.extend(
                    self._validate_actions(
                        then_actions, auto_id, auto_name, f"{location}.then", _depth + 1
                    )
                )

                else_actions = action.get("else", [])
                if else_actions:
                    issues.extend(
                        self._validate_actions(
                            else_actions, auto_id, auto_name, f"{location}.else", _depth + 1
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
                            )
                        )

                # Recurse into sequence
                sequence = repeat_config.get("sequence", [])
                issues.extend(
                    self._validate_actions(
                        sequence, auto_id, auto_name, f"{location}.repeat.sequence", _depth + 1
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
                        )
                    )

        return issues

    def _validate_data_templates(
        self,
        data: dict[str, Any],
        location: str,
        auto_id: str,
        auto_name: str,
    ) -> list[ValidationIssue]:
        """Validate templates in action data fields."""
        issues: list[ValidationIssue] = []

        for key, value in data.items():
            if isinstance(value, str) and self._is_template(value):
                issue = self._check_template(
                    value, f"{location}.{key}", auto_id, auto_name
                )
                if issue:
                    issues.append(issue)
            elif isinstance(value, dict):
                issues.extend(
                    self._validate_data_templates(
                        value, f"{location}.{key}", auto_id, auto_name
                    )
                )
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, str) and self._is_template(item):
                        issue = self._check_template(
                            item, f"{location}.{key}[{idx}]", auto_id, auto_name
                        )
                        if issue:
                            issues.append(issue)
                    elif isinstance(item, dict):
                        issues.extend(
                            self._validate_data_templates(
                                item, f"{location}.{key}[{idx}]", auto_id, auto_name
                            )
                        )

        return issues

    def _is_template(self, value: str) -> bool:
        """Check if a string contains Jinja2 template syntax."""
        return bool(TEMPLATE_PATTERN.search(value))

    def _check_template(
        self,
        template: str,
        location: str,
        auto_id: str,
        auto_name: str,
    ) -> ValidationIssue | None:
        """Check a template for syntax errors.

        Returns a ValidationIssue if there's an error, None otherwise.
        """
        try:
            # Try to parse the template
            self._env.parse(template)
            return None
        except TemplateSyntaxError as err:
            # Extract useful error info
            error_msg = str(err.message) if err.message else str(err)
            line_info = f" (line {err.lineno})" if err.lineno else ""

            return ValidationIssue(
                issue_type=IssueType.TEMPLATE_SYNTAX_ERROR,
                severity=Severity.ERROR,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id="",  # Templates don't have a specific entity
                location=location,
                message=f"Jinja2 syntax error{line_info}: {error_msg}",
                suggestion=None,
            )
        except Exception as err:
            # Catch any other parsing errors
            return ValidationIssue(
                issue_type=IssueType.TEMPLATE_SYNTAX_ERROR,
                severity=Severity.ERROR,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id="",
                location=location,
                message=f"Template error: {err}",
                suggestion=None,
            )
