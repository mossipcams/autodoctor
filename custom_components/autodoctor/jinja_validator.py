"""Jinja2 template syntax validator for Home Assistant automations."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

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


def _ensure_list(value: Any) -> list[Any]:
    """Wrap a value in a list if it isn't one already."""
    if not isinstance(value, list):
        return [value] if value is not None else []
    return cast(list[Any], value)


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

        # Validate triggers
        triggers = _ensure_list(
            automation.get("triggers") or automation.get("trigger", [])
        )
        for idx, trigger in enumerate(triggers):
            if isinstance(trigger, dict):
                issues.extend(
                    self._validate_trigger(trigger, idx, auto_id, auto_name)
                )

        # Validate conditions
        conditions = _ensure_list(
            automation.get("conditions") or automation.get("condition", [])
        )
        for idx, condition in enumerate(conditions):
            issues.extend(
                self._validate_condition(
                    condition, idx, auto_id, auto_name, "condition"
                )
            )

        # Validate actions
        actions = _ensure_list(
            automation.get("actions") or automation.get("action", [])
        )
        issues.extend(
            self._validate_actions(actions, auto_id, auto_name)
        )

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
            issues.extend(
                self._check_template(
                    value_template,
                    f"trigger[{index}].value_template",
                    auto_id,
                    auto_name,
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
                    )
                )
            return issues

        if not isinstance(condition, dict):
            return issues
        condition = cast(dict[str, Any], condition)

        # Check value_template
        value_template = condition.get("value_template")
        if value_template and isinstance(value_template, str):
            issues.extend(
                self._check_template(
                    value_template,
                    f"{location_prefix}[{index}].value_template",
                    auto_id,
                    auto_name,
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
        """Validate templates in actions using shared walker."""
        from .action_walker import walk_automation_actions

        issues: list[ValidationIssue] = []

        def _visit_action(action: dict[str, Any], idx: int, location: str) -> None:
            data = action.get("data", {})
            if isinstance(data, dict):
                issues.extend(
                    self._validate_data_templates(
                        data, f"{location}.data", auto_id, auto_name,
                    )
                )
            wait_template = action.get("wait_template")
            if wait_template and isinstance(wait_template, str):
                issues.extend(
                    self._check_template(
                        wait_template, f"{location}.wait_template", auto_id, auto_name,
                    )
                )

        def _visit_condition(
            condition: dict[str, Any], cond_idx: int, location: str,
        ) -> None:
            issues.extend(
                self._validate_condition(
                    condition, cond_idx, auto_id, auto_name, location,
                )
            )

        walk_automation_actions(
            _ensure_list(actions),
            visit_action=_visit_action,
            visit_condition=_visit_condition,
            location_prefix=location_prefix,
            max_depth=_TEMPLATE_MAX_NESTING_DEPTH + 1,
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
                issues.extend(
                    self._check_template(
                        value,
                        f"{location}.{key}",
                        auto_id,
                        auto_name,
                    )
                )
            elif isinstance(value, dict):
                issues.extend(
                    self._validate_data_templates(
                        value,
                        f"{location}.{key}",
                        auto_id,
                        auto_name,
                    )
                )
            elif isinstance(value, list):
                for idx, item in enumerate(cast(list[Any], value)):
                    if isinstance(item, str) and self._is_template(item):
                        issues.extend(
                            self._check_template(
                                item,
                                f"{location}.{key}[{idx}]",
                                auto_id,
                                auto_name,
                            )
                        )
                    elif isinstance(item, dict):
                        issues.extend(
                            self._validate_data_templates(
                                item,
                                f"{location}.{key}[{idx}]",
                                auto_id,
                                auto_name,
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
