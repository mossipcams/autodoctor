"""Detect high-confidence reachability contradictions in automations."""

from __future__ import annotations

from typing import Any

from .models import IssueType, Severity, ValidationIssue
from .template_utils import is_template_value


class ReachabilityValidator:
    """Conservative static checks for obviously unreachable logic."""

    def validate_automations(
        self, automations: list[dict[str, Any]]
    ) -> list[ValidationIssue]:
        """Validate automations and return high-confidence contradiction issues."""
        issues: list[ValidationIssue] = []
        for automation in automations:
            issues.extend(self._validate_single_automation(automation))
        return issues

    def _validate_single_automation(
        self, automation: dict[str, Any]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = str(automation.get("alias", automation_id))

        triggers_raw = automation.get("triggers") or automation.get("trigger") or []
        conditions_raw = (
            automation.get("conditions") or automation.get("condition") or []
        )
        triggers = triggers_raw if isinstance(triggers_raw, list) else [triggers_raw]
        conditions = (
            conditions_raw if isinstance(conditions_raw, list) else [conditions_raw]
        )

        issues.extend(
            self._detect_state_trigger_condition_contradictions(
                triggers, conditions, automation_id, automation_name
            )
        )
        issues.extend(
            self._detect_impossible_numeric_ranges(
                triggers, conditions, automation_id, automation_name
            )
        )
        return issues

    def _detect_state_trigger_condition_contradictions(
        self,
        triggers: list[Any],
        conditions: list[Any],
        automation_id: str,
        automation_name: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for trig_idx, trigger in enumerate(triggers):
            if not isinstance(trigger, dict):
                continue
            platform = trigger.get("platform") or trigger.get("trigger")
            if platform != "state":
                continue

            trigger_to = trigger.get("to")
            if not isinstance(trigger_to, str) or is_template_value(trigger_to):
                continue

            trigger_entities = self._normalize_entity_ids(trigger.get("entity_id"))
            if not trigger_entities:
                continue

            for cond_idx, condition in enumerate(conditions):
                if not isinstance(condition, dict):
                    continue
                cond_type = condition.get("condition")
                if cond_type != "state":
                    continue
                condition_state = condition.get("state")
                if (
                    not isinstance(condition_state, str)
                    or is_template_value(condition_state)
                ):
                    continue

                condition_entities = self._normalize_entity_ids(
                    condition.get("entity_id")
                )
                if not condition_entities:
                    continue

                for entity_id in trigger_entities:
                    if entity_id in condition_entities and trigger_to != condition_state:
                        issues.append(
                            ValidationIssue(
                                severity=Severity.ERROR,
                                automation_id=automation_id,
                                automation_name=automation_name,
                                entity_id=entity_id,
                                location=f"trigger[{trig_idx}].to",
                                message=(
                                    "State contradiction: trigger requires "
                                    f"'{entity_id}' to be '{trigger_to}' but "
                                    f"condition[{cond_idx}] requires '{condition_state}'"
                                ),
                                issue_type=IssueType.INVALID_STATE,
                            )
                        )
        return issues

    def _detect_impossible_numeric_ranges(
        self,
        triggers: list[Any],
        conditions: list[Any],
        automation_id: str,
        automation_name: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for idx, trigger in enumerate(triggers):
            issue = self._numeric_range_issue(
                node=trigger,
                node_type_key=("platform", "trigger"),
                expected_type="numeric_state",
                location=f"trigger[{idx}]",
                automation_id=automation_id,
                automation_name=automation_name,
            )
            if issue is not None:
                issues.append(issue)

        for idx, condition in enumerate(conditions):
            issue = self._numeric_range_issue(
                node=condition,
                node_type_key=("condition",),
                expected_type="numeric_state",
                location=f"condition[{idx}]",
                automation_id=automation_id,
                automation_name=automation_name,
            )
            if issue is not None:
                issues.append(issue)

        return issues

    def _numeric_range_issue(
        self,
        node: Any,
        node_type_key: tuple[str, ...],
        expected_type: str,
        location: str,
        automation_id: str,
        automation_name: str,
    ) -> ValidationIssue | None:
        if not isinstance(node, dict):
            return None

        node_type = ""
        for key in node_type_key:
            val = node.get(key)
            if isinstance(val, str) and val:
                node_type = val
                break
        if node_type != expected_type:
            return None

        above = self._coerce_number(node.get("above"))
        below = self._coerce_number(node.get("below"))
        if above is None or below is None:
            return None
        if below > above:
            return None

        entity_ids = self._normalize_entity_ids(node.get("entity_id"))
        entity_id = entity_ids[0] if entity_ids else ""
        return ValidationIssue(
            severity=Severity.ERROR,
            automation_id=automation_id,
            automation_name=automation_name,
            entity_id=entity_id,
            location=location,
            message=(
                "Numeric-state contradiction: 'below' must be greater than 'above' "
                f"(got below={below}, above={above})"
            ),
            issue_type=IssueType.INVALID_STATE,
        )

    def _normalize_entity_ids(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        if isinstance(value, str):
            return [value]
        return []

    def _coerce_number(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            if is_template_value(value):
                return None
            try:
                return float(value)
            except ValueError:
                return None
        return None
