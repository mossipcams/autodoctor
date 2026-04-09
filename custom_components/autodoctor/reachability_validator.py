"""Conservative reachability/contradiction validation for automations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from .action_walker import ensure_list, walk_automation_actions
from .models import IssueType, Severity, ValidationIssue
from .template_utils import is_template_value

StateConstraint = tuple[str, str]
NumericConstraint = tuple[float | None, float | None, str | None, str | None]


class ReachabilityValidator:
    """Find high-confidence unreachable state combinations."""

    def validate_automations(
        self,
        automations: list[dict[str, Any]],
    ) -> list[ValidationIssue]:
        """Validate multiple automations."""
        issues: list[ValidationIssue] = []
        for automation in automations:
            issues.extend(self._validate_automation(automation))
        return issues

    def _validate_automation(self, automation: dict[str, Any]) -> list[ValidationIssue]:
        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = str(automation.get("alias", automation_id))

        issues: list[ValidationIssue] = []
        global_constraints: dict[tuple[str, str | None], StateConstraint] = {}
        global_numeric: dict[tuple[str, str | None], NumericConstraint] = {}
        declared_trigger_ids = self._collect_trigger_ids(
            automation=automation,
        )

        # Do not treat trigger states/thresholds as global facts.
        # Triggers are OR paths in Home Assistant and would cause false positives.

        conditions = self._as_list(
            automation.get("conditions") or automation.get("condition")
        )
        for idx, condition in enumerate(conditions):
            self._process_top_level_condition(
                condition=condition,
                idx=idx,
                automation_id=automation_id,
                automation_name=automation_name,
                constraints=global_constraints,
                numeric_constraints=global_numeric,
                declared_trigger_ids=declared_trigger_ids,
                issues=issues,
            )

        actions_raw = self._as_list(
            automation.get("actions") or automation.get("action")
        )
        actions: list[dict[str, Any]] = [
            cast(dict[str, Any], action)
            for action in actions_raw
            if isinstance(action, dict)
        ]

        issues.extend(
            self._validate_action_condition_blocks(
                actions=actions,
                automation_id=automation_id,
                automation_name=automation_name,
            )
        )

        def _visit_condition(cond: dict[str, Any], _idx: int, location: str) -> None:
            self._process_branch_condition(
                condition=cond,
                location=location,
                automation_id=automation_id,
                automation_name=automation_name,
                global_constraints=global_constraints,
                global_numeric=global_numeric,
                declared_trigger_ids=declared_trigger_ids,
                issues=issues,
            )

        walk_automation_actions(
            actions,
            visit_action=lambda _a, _i, _l: None,
            visit_condition=_visit_condition,
        )

        return issues

    def _validate_action_condition_blocks(
        self,
        *,
        actions: list[dict[str, Any]],
        automation_id: str,
        automation_name: str,
        location_prefix: str = "action",
    ) -> list[ValidationIssue]:
        """Validate contradictions within action-local condition blocks."""
        issues: list[ValidationIssue] = []

        for idx, action in enumerate(actions):
            location = f"{location_prefix}[{idx}]"

            if "choose" in action:
                options = self._as_list(action.get("choose"))
                for opt_idx, option in enumerate(options):
                    if not isinstance(option, dict):
                        continue
                    issues.extend(
                        self._validate_condition_block(
                            conditions=option.get("conditions"),
                            location_prefix=f"{location}.choose[{opt_idx}].conditions",
                            automation_id=automation_id,
                            automation_name=automation_name,
                        )
                    )
                    issues.extend(
                        self._validate_action_condition_blocks(
                            actions=[
                                cast(dict[str, Any], branch_action)
                                for branch_action in self._as_list(
                                    option.get("sequence")
                                )
                                if isinstance(branch_action, dict)
                            ],
                            automation_id=automation_id,
                            automation_name=automation_name,
                            location_prefix=f"{location}.choose[{opt_idx}].sequence",
                        )
                    )
                issues.extend(
                    self._validate_action_condition_blocks(
                        actions=[
                            cast(dict[str, Any], branch_action)
                            for branch_action in self._as_list(action.get("default"))
                            if isinstance(branch_action, dict)
                        ],
                        automation_id=automation_id,
                        automation_name=automation_name,
                        location_prefix=f"{location}.default",
                    )
                )

            if "if" in action:
                issues.extend(
                    self._validate_condition_block(
                        conditions=action.get("if"),
                        location_prefix=f"{location}.if",
                        automation_id=automation_id,
                        automation_name=automation_name,
                    )
                )
                issues.extend(
                    self._validate_action_condition_blocks(
                        actions=[
                            cast(dict[str, Any], branch_action)
                            for branch_action in self._as_list(action.get("then"))
                            if isinstance(branch_action, dict)
                        ],
                        automation_id=automation_id,
                        automation_name=automation_name,
                        location_prefix=f"{location}.then",
                    )
                )
                issues.extend(
                    self._validate_action_condition_blocks(
                        actions=[
                            cast(dict[str, Any], branch_action)
                            for branch_action in self._as_list(action.get("else"))
                            if isinstance(branch_action, dict)
                        ],
                        automation_id=automation_id,
                        automation_name=automation_name,
                        location_prefix=f"{location}.else",
                    )
                )

            if "repeat" in action:
                repeat_config = action.get("repeat")
                if isinstance(repeat_config, dict):
                    for cond_key in ("while", "until"):
                        issues.extend(
                            self._validate_condition_block(
                                conditions=repeat_config.get(cond_key),
                                location_prefix=f"{location}.repeat.{cond_key}",
                                automation_id=automation_id,
                                automation_name=automation_name,
                            )
                        )
                    issues.extend(
                        self._validate_action_condition_blocks(
                            actions=[
                                cast(dict[str, Any], branch_action)
                                for branch_action in self._as_list(
                                    repeat_config.get("sequence")
                                )
                                if isinstance(branch_action, dict)
                            ],
                            automation_id=automation_id,
                            automation_name=automation_name,
                            location_prefix=f"{location}.repeat.sequence",
                        )
                    )

            if "parallel" in action:
                branches = self._as_list(action.get("parallel"))
                for branch_idx, branch in enumerate(branches):
                    issues.extend(
                        self._validate_action_condition_blocks(
                            actions=[
                                cast(dict[str, Any], branch_action)
                                for branch_action in self._as_list(branch)
                                if isinstance(branch_action, dict)
                            ],
                            automation_id=automation_id,
                            automation_name=automation_name,
                            location_prefix=f"{location}.parallel[{branch_idx}]",
                        )
                    )

        return issues

    def _validate_condition_block(
        self,
        *,
        conditions: Any,
        location_prefix: str,
        automation_id: str,
        automation_name: str,
    ) -> list[ValidationIssue]:
        """Validate contradictions within a list of sibling conditions."""
        issues: list[ValidationIssue] = []
        local_constraints: dict[tuple[str, str | None], StateConstraint] = {}
        local_numeric: dict[tuple[str, str | None], NumericConstraint] = {}
        block_conditions = self._as_list(conditions)
        has_multiple_siblings = (
            sum(1 for condition in block_conditions if isinstance(condition, dict)) > 1
        )

        for cond_idx, condition in enumerate(block_conditions):
            if not isinstance(condition, dict):
                continue
            typed_condition = cast(dict[str, Any], condition)
            location = f"{location_prefix}[{cond_idx}]"
            cond_type_obj = typed_condition.get("condition")
            cond_type = cond_type_obj if isinstance(cond_type_obj, str) else ""
            is_state_condition = cond_type == "state" or (
                not cond_type
                and "entity_id" in typed_condition
                and "state" in typed_condition
            )
            if is_state_condition and has_multiple_siblings:
                states = self._normalize_values(typed_condition.get("state"))
                if len(states) != 1 or is_template_value(states[0]):
                    continue
                attribute_obj = typed_condition.get("attribute")
                attribute = attribute_obj if isinstance(attribute_obj, str) else None
                for entity_id in self._normalize_entity_ids(
                    typed_condition.get("entity_id")
                ):
                    self._add_state_constraint(
                        constraints=local_constraints,
                        issues=issues,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        attribute=attribute,
                        state=states[0],
                        location=f"{location}.state",
                    )
                continue

            if cond_type == "numeric_state" and has_multiple_siblings:
                self._process_numeric_constraint(
                    constraint=typed_condition,
                    location=location,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    numeric_constraints=local_numeric,
                    issues=issues,
                )
                continue

            # Only recurse into nested AND-style groups; OR/NOT would require
            # different semantics and are skipped to stay conservative.
            for key in ("conditions", "and"):
                if key in typed_condition:
                    issues.extend(
                        self._validate_condition_block(
                            conditions=typed_condition.get(key),
                            location_prefix=f"{location}.{key}",
                            automation_id=automation_id,
                            automation_name=automation_name,
                        )
                    )

        return issues

    def _process_top_level_condition(
        self,
        *,
        condition: Any,
        idx: int,
        automation_id: str,
        automation_name: str,
        constraints: dict[tuple[str, str | None], StateConstraint],
        numeric_constraints: dict[tuple[str, str | None], NumericConstraint],
        declared_trigger_ids: set[str],
        issues: list[ValidationIssue],
    ) -> None:
        if not isinstance(condition, dict):
            return
        cond = cast(dict[str, Any], condition)
        cond_type_obj = cond.get("condition")
        cond_type = cond_type_obj if isinstance(cond_type_obj, str) else ""
        is_state_condition = cond_type == "state" or (
            not cond_type and "entity_id" in cond and "state" in cond
        )
        if is_state_condition:
            states = self._normalize_values(cond.get("state"))
            if len(states) != 1 or is_template_value(states[0]):
                return
            attribute_obj = cond.get("attribute")
            attribute = attribute_obj if isinstance(attribute_obj, str) else None
            entity_ids = self._normalize_entity_ids(cond.get("entity_id"))
            for entity_id in entity_ids:
                self._add_state_constraint(
                    constraints=constraints,
                    issues=issues,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    attribute=attribute,
                    state=states[0],
                    location=f"condition[{idx}].state",
                )
            return

        if cond_type == "numeric_state":
            self._process_numeric_constraint(
                constraint=cond,
                location=f"condition[{idx}]",
                automation_id=automation_id,
                automation_name=automation_name,
                numeric_constraints=numeric_constraints,
                issues=issues,
            )
            return

        if cond_type == "trigger":
            self._validate_trigger_condition_ids(
                condition=cond,
                location=f"condition[{idx}]",
                automation_id=automation_id,
                automation_name=automation_name,
                declared_trigger_ids=declared_trigger_ids,
                issues=issues,
            )

    def _process_branch_condition(
        self,
        *,
        condition: dict[str, Any],
        location: str,
        automation_id: str,
        automation_name: str,
        global_constraints: dict[tuple[str, str | None], StateConstraint],
        global_numeric: dict[tuple[str, str | None], NumericConstraint],
        declared_trigger_ids: set[str],
        issues: list[ValidationIssue],
    ) -> None:
        cond_type_obj = condition.get("condition")
        cond_type = cond_type_obj if isinstance(cond_type_obj, str) else ""
        is_state_condition = cond_type == "state" or (
            not cond_type and "entity_id" in condition and "state" in condition
        )
        if is_state_condition:
            states = self._normalize_values(condition.get("state"))
            if len(states) != 1 or is_template_value(states[0]):
                return
            state = states[0]
            attribute_obj = condition.get("attribute")
            attr_name = attribute_obj if isinstance(attribute_obj, str) else None
            entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
            for entity_id in entity_ids:
                key = (entity_id, attr_name)
                existing = global_constraints.get(key)
                if existing and existing[0] != state:
                    existing_state, existing_location = existing
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.UNREACHABLE_STATE_COMBINATION,
                            severity=Severity.ERROR,
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            location=f"{location}.state",
                            message=(
                                f"Unreachable branch: {entity_id} must be '{existing_state}' "
                                f"at {existing_location} but branch requires '{state}'"
                            ),
                        )
                    )
            return

        if cond_type == "numeric_state":
            self._check_branch_numeric_constraint(
                condition=condition,
                location=location,
                automation_id=automation_id,
                automation_name=automation_name,
                global_numeric=global_numeric,
                issues=issues,
            )
            return

        if cond_type == "trigger":
            self._validate_trigger_condition_ids(
                condition=condition,
                location=location,
                automation_id=automation_id,
                automation_name=automation_name,
                declared_trigger_ids=declared_trigger_ids,
                issues=issues,
            )

    def _collect_trigger_ids(
        self,
        *,
        automation: dict[str, Any],
    ) -> set[str]:
        """Collect declared trigger IDs, including HA's implicit index IDs."""
        declared_ids: set[str] = set()
        triggers = self._as_list(
            automation.get("triggers") or automation.get("trigger")
        )
        for idx, trigger in enumerate(triggers):
            declared_ids.add(str(idx))
            if not isinstance(trigger, dict):
                continue
            for trigger_id in self._normalize_trigger_ids(trigger.get("id")):
                declared_ids.add(trigger_id)
        return declared_ids

    def _validate_trigger_condition_ids(
        self,
        *,
        condition: dict[str, Any],
        location: str,
        automation_id: str,
        automation_name: str,
        declared_trigger_ids: set[str],
        issues: list[ValidationIssue],
    ) -> None:
        """Validate condition: trigger IDs against declared trigger IDs."""
        for trigger_id in self._normalize_trigger_ids(condition.get("id")):
            if trigger_id in declared_trigger_ids:
                continue
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.UNKNOWN_TRIGGER_ID,
                    severity=Severity.ERROR,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=trigger_id,
                    location=f"{location}.id",
                    message=f"Trigger condition references unknown trigger id '{trigger_id}'",
                )
            )

    def _normalize_trigger_ids(self, value: Any) -> list[str]:
        """Normalize trigger id values to a list of non-template strings."""
        if value is None:
            return []
        if isinstance(value, str):
            return [] if is_template_value(value) or value == "" else [value]
        if isinstance(value, Iterable):
            ids: list[str] = []
            iterable = cast(Iterable[Any], value)
            for item in iterable:
                if isinstance(item, str) and item and not is_template_value(item):
                    ids.append(item)
            return ids
        return []

    def _add_state_constraint(
        self,
        *,
        constraints: dict[tuple[str, str | None], StateConstraint],
        issues: list[ValidationIssue],
        automation_id: str,
        automation_name: str,
        entity_id: str,
        attribute: str | None,
        state: str,
        location: str,
    ) -> None:
        key = (entity_id, attribute)
        existing = constraints.get(key)
        if existing is None:
            constraints[key] = (state, location)
            return
        if existing[0] == state:
            return
        issues.append(
            ValidationIssue(
                issue_type=IssueType.UNREACHABLE_STATE_COMBINATION,
                severity=Severity.ERROR,
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                location=location,
                message=(
                    f"Unreachable state combination: {entity_id} is required as "
                    f"'{existing[0]}' at {existing[1]} and '{state}' at {location}"
                ),
            )
        )

    def _normalize_values(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            values: list[str] = []
            iterable = cast(Iterable[Any], value)
            for item in iterable:
                if isinstance(item, str):
                    values.append(item)
                elif item is not None:
                    values.append(str(item))
            return values
        return [str(value)]

    def _normalize_entity_ids(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            entity_ids: list[str] = []
            iterable = cast(Iterable[Any], value)
            for item in iterable:
                if isinstance(item, str):
                    entity_ids.append(item)
            return entity_ids
        return []

    def _as_list(self, value: Any) -> list[Any]:
        return ensure_list(value)

    def _process_numeric_constraint(
        self,
        *,
        constraint: dict[str, Any],
        location: str,
        automation_id: str,
        automation_name: str,
        numeric_constraints: dict[tuple[str, str | None], NumericConstraint],
        issues: list[ValidationIssue],
    ) -> None:
        entity_ids = self._normalize_entity_ids(constraint.get("entity_id"))
        attribute_obj = constraint.get("attribute")
        attr_name = attribute_obj if isinstance(attribute_obj, str) else None
        above = self._to_number(constraint.get("above"))
        below = self._to_number(constraint.get("below"))
        if above is None and below is None:
            return

        for entity_id in entity_ids:
            self._add_numeric_constraint(
                numeric_constraints=numeric_constraints,
                issues=issues,
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                attribute=attr_name,
                above=above,
                below=below,
                location=location,
            )

    def _add_numeric_constraint(
        self,
        *,
        numeric_constraints: dict[tuple[str, str | None], NumericConstraint],
        issues: list[ValidationIssue],
        automation_id: str,
        automation_name: str,
        entity_id: str,
        attribute: str | None,
        above: float | None,
        below: float | None,
        location: str,
    ) -> None:
        key = (entity_id, attribute)
        existing = numeric_constraints.get(key)
        if existing is None:
            existing_lower, existing_upper, lower_loc, upper_loc = (
                None,
                None,
                None,
                None,
            )
        else:
            existing_lower, existing_upper, lower_loc, upper_loc = existing

        new_lower = existing_lower
        new_upper = existing_upper
        new_lower_loc = lower_loc
        new_upper_loc = upper_loc
        if above is not None and (new_lower is None or above > new_lower):
            new_lower = above
            new_lower_loc = location
        if below is not None and (new_upper is None or below < new_upper):
            new_upper = below
            new_upper_loc = location

        numeric_constraints[key] = (new_lower, new_upper, new_lower_loc, new_upper_loc)

        if new_lower is not None and new_upper is not None and new_lower >= new_upper:
            details = f"({new_lower} >= {new_upper})"
            if new_lower_loc and new_upper_loc:
                details = f"({new_lower} from {new_lower_loc} >= {new_upper} from {new_upper_loc})"
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.UNREACHABLE_NUMERIC_RANGE,
                    severity=Severity.ERROR,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    location=location,
                    message=f"Unreachable numeric range for {entity_id} {details}",
                )
            )

    def _check_branch_numeric_constraint(
        self,
        *,
        condition: dict[str, Any],
        location: str,
        automation_id: str,
        automation_name: str,
        global_numeric: dict[tuple[str, str | None], NumericConstraint],
        issues: list[ValidationIssue],
    ) -> None:
        entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
        attribute_obj = condition.get("attribute")
        attr_name = attribute_obj if isinstance(attribute_obj, str) else None
        above = self._to_number(condition.get("above"))
        below = self._to_number(condition.get("below"))
        if above is None and below is None:
            return

        for entity_id in entity_ids:
            existing = global_numeric.get((entity_id, attr_name))
            combined_lower = existing[0] if existing else None
            combined_upper = existing[1] if existing else None
            if above is not None and (combined_lower is None or above > combined_lower):
                combined_lower = above
            if below is not None and (combined_upper is None or below < combined_upper):
                combined_upper = below

            if (
                combined_lower is not None
                and combined_upper is not None
                and combined_lower >= combined_upper
            ):
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.UNREACHABLE_NUMERIC_RANGE,
                        severity=Severity.ERROR,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        location=location,
                        message=(
                            f"Unreachable branch numeric range for {entity_id} "
                            f"({combined_lower} >= {combined_upper})"
                        ),
                    )
                )

    def _to_number(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value and not is_template_value(value):
            try:
                return float(value)
            except ValueError:
                return None
        return None
