"""Conservative reachability/contradiction validation for automations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from .action_walker import ensure_list
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
        initial_constraints: dict[tuple[str, str | None], StateConstraint] = {}
        initial_numeric: dict[tuple[str, str | None], NumericConstraint] = {}
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
                constraints=initial_constraints,
                numeric_constraints=initial_numeric,
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

        self._walk_actions_with_constraints(
            actions,
            automation_id=automation_id,
            automation_name=automation_name,
            constraints=initial_constraints,
            numeric_constraints=initial_numeric,
            declared_trigger_ids=declared_trigger_ids,
            issues=issues,
        )

        return issues

    def _walk_actions_with_constraints(
        self,
        actions: list[dict[str, Any]],
        *,
        automation_id: str,
        automation_name: str,
        constraints: dict[tuple[str, str | None], StateConstraint],
        numeric_constraints: dict[tuple[str, str | None], NumericConstraint],
        declared_trigger_ids: set[str],
        issues: list[ValidationIssue],
        location_prefix: str = "action",
        max_depth: int = 50,
        _depth: int = 0,
    ) -> None:
        if _depth >= max_depth:
            return

        active_constraints = dict(constraints)
        active_numeric = dict(numeric_constraints)

        for idx, action in enumerate(actions):
            if not isinstance(action, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                continue
            location = f"{location_prefix}[{idx}]"

            if self._is_condition_action(action):
                issue_count = len(issues)
                self._process_branch_condition(
                    condition=action,
                    location=location,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    global_constraints=active_constraints,
                    global_numeric=active_numeric,
                    declared_trigger_ids=declared_trigger_ids,
                    issues=issues,
                )
                if len(issues) != issue_count:
                    continue
                self._add_condition_to_active_constraints(
                    condition=action,
                    location=location,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    constraints=active_constraints,
                    numeric_constraints=active_numeric,
                    issues=issues,
                )
                continue

            if "choose" in action:
                options = self._as_list(action.get("choose"))
                for opt_idx, option in enumerate(options):
                    if isinstance(option, dict):
                        branch_constraints = dict(active_constraints)
                        branch_numeric = dict(active_numeric)
                        self._process_condition_list(
                            conditions=option.get("conditions"),
                            location_prefix=f"{location}.choose[{opt_idx}].conditions",
                            automation_id=automation_id,
                            automation_name=automation_name,
                            constraints=branch_constraints,
                            numeric_constraints=branch_numeric,
                            declared_trigger_ids=declared_trigger_ids,
                            issues=issues,
                        )
                        sequence = [
                            cast(dict[str, Any], nested_action)
                            for nested_action in self._as_list(option.get("sequence"))
                            if isinstance(nested_action, dict)
                        ]
                        self._walk_actions_with_constraints(
                            sequence,
                            automation_id=automation_id,
                            automation_name=automation_name,
                            constraints=branch_constraints,
                            numeric_constraints=branch_numeric,
                            declared_trigger_ids=declared_trigger_ids,
                            issues=issues,
                            location_prefix=f"{location}.choose[{opt_idx}].sequence",
                            max_depth=max_depth,
                            _depth=_depth + 1,
                        )
                default = [
                    cast(dict[str, Any], nested_action)
                    for nested_action in self._as_list(action.get("default"))
                    if isinstance(nested_action, dict)
                ]
                if default:
                    self._walk_actions_with_constraints(
                        default,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        constraints=active_constraints,
                        numeric_constraints=active_numeric,
                        declared_trigger_ids=declared_trigger_ids,
                        issues=issues,
                        location_prefix=f"{location}.default",
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )

            if "if" in action:
                branch_constraints = dict(active_constraints)
                branch_numeric = dict(active_numeric)
                self._process_condition_list(
                    conditions=action.get("if"),
                    location_prefix=f"{location}.if",
                    automation_id=automation_id,
                    automation_name=automation_name,
                    constraints=branch_constraints,
                    numeric_constraints=branch_numeric,
                    declared_trigger_ids=declared_trigger_ids,
                    issues=issues,
                )
                then_actions = [
                    cast(dict[str, Any], nested_action)
                    for nested_action in self._as_list(action.get("then"))
                    if isinstance(nested_action, dict)
                ]
                self._walk_actions_with_constraints(
                    then_actions,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    constraints=branch_constraints,
                    numeric_constraints=branch_numeric,
                    declared_trigger_ids=declared_trigger_ids,
                    issues=issues,
                    location_prefix=f"{location}.then",
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )
                else_actions = [
                    cast(dict[str, Any], nested_action)
                    for nested_action in self._as_list(action.get("else"))
                    if isinstance(nested_action, dict)
                ]
                if else_actions:
                    self._walk_actions_with_constraints(
                        else_actions,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        constraints=active_constraints,
                        numeric_constraints=active_numeric,
                        declared_trigger_ids=declared_trigger_ids,
                        issues=issues,
                        location_prefix=f"{location}.else",
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )

            if "repeat" in action:
                repeat_config = action.get("repeat")
                if isinstance(repeat_config, dict):
                    for cond_key in ("while", "until"):
                        loop_constraints = dict(active_constraints)
                        loop_numeric = dict(active_numeric)
                        self._process_condition_list(
                            conditions=repeat_config.get(cond_key),
                            location_prefix=f"{location}.repeat.{cond_key}",
                            automation_id=automation_id,
                            automation_name=automation_name,
                            constraints=loop_constraints,
                            numeric_constraints=loop_numeric,
                            declared_trigger_ids=declared_trigger_ids,
                            issues=issues,
                        )
                    sequence = [
                        cast(dict[str, Any], nested_action)
                        for nested_action in self._as_list(
                            repeat_config.get("sequence")
                        )
                        if isinstance(nested_action, dict)
                    ]
                    self._walk_actions_with_constraints(
                        sequence,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        constraints=active_constraints,
                        numeric_constraints=active_numeric,
                        declared_trigger_ids=declared_trigger_ids,
                        issues=issues,
                        location_prefix=f"{location}.repeat.sequence",
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )

            if "parallel" in action:
                branches = self._as_list(action.get("parallel"))
                for branch_idx, branch in enumerate(branches):
                    branch_actions = [
                        cast(dict[str, Any], nested_action)
                        for nested_action in self._as_list(branch)
                        if isinstance(nested_action, dict)
                    ]
                    self._walk_actions_with_constraints(
                        branch_actions,
                        automation_id=automation_id,
                        automation_name=automation_name,
                        constraints=active_constraints,
                        numeric_constraints=active_numeric,
                        declared_trigger_ids=declared_trigger_ids,
                        issues=issues,
                        location_prefix=f"{location}.parallel[{branch_idx}]",
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )

            if self._may_allow_state_changes(action):
                active_constraints = {}
                active_numeric = {}

    def _process_condition_list(
        self,
        *,
        conditions: Any,
        location_prefix: str,
        automation_id: str,
        automation_name: str,
        constraints: dict[tuple[str, str | None], StateConstraint],
        numeric_constraints: dict[tuple[str, str | None], NumericConstraint],
        declared_trigger_ids: set[str],
        issues: list[ValidationIssue],
    ) -> None:
        for idx, condition in enumerate(self._as_list(conditions)):
            if not isinstance(condition, dict):
                continue
            typed_condition = cast(dict[str, Any], condition)
            location = f"{location_prefix}[{idx}]"
            issue_count = len(issues)
            self._process_branch_condition(
                condition=typed_condition,
                location=location,
                automation_id=automation_id,
                automation_name=automation_name,
                global_constraints=constraints,
                global_numeric=numeric_constraints,
                declared_trigger_ids=declared_trigger_ids,
                issues=issues,
            )
            if len(issues) == issue_count:
                self._add_condition_to_active_constraints(
                    condition=typed_condition,
                    location=location,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    constraints=constraints,
                    numeric_constraints=numeric_constraints,
                    issues=issues,
                )

            for key in ("conditions", "and"):
                if key in typed_condition:
                    self._process_condition_list(
                        conditions=typed_condition.get(key),
                        location_prefix=f"{location}.{key}",
                        automation_id=automation_id,
                        automation_name=automation_name,
                        constraints=constraints,
                        numeric_constraints=numeric_constraints,
                        declared_trigger_ids=declared_trigger_ids,
                        issues=issues,
                    )

    def _add_condition_to_active_constraints(
        self,
        *,
        condition: dict[str, Any],
        location: str,
        automation_id: str,
        automation_name: str,
        constraints: dict[tuple[str, str | None], StateConstraint],
        numeric_constraints: dict[tuple[str, str | None], NumericConstraint],
        issues: list[ValidationIssue],
    ) -> None:
        cond_type_obj = condition.get("condition")
        cond_type = cond_type_obj if isinstance(cond_type_obj, str) else ""
        if self._is_state_condition(condition):
            states = self._normalize_values(condition.get("state"))
            if len(states) != 1 or is_template_value(states[0]):
                return
            attribute_obj = condition.get("attribute")
            attribute = attribute_obj if isinstance(attribute_obj, str) else None
            for entity_id in self._normalize_entity_ids(condition.get("entity_id")):
                self._add_state_constraint(
                    constraints=constraints,
                    issues=issues,
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    attribute=attribute,
                    state=states[0],
                    location=f"{location}.state",
                )
            return

        if cond_type == "numeric_state":
            self._process_numeric_constraint(
                constraint=condition,
                location=location,
                automation_id=automation_id,
                automation_name=automation_name,
                numeric_constraints=numeric_constraints,
                issues=issues,
            )

    def _is_condition_action(self, action: dict[str, Any]) -> bool:
        return (
            self._is_state_condition(action)
            or action.get("condition") == "numeric_state"
            or action.get("condition") == "trigger"
        )

    def _is_state_condition(self, condition: dict[str, Any]) -> bool:
        cond_type_obj = condition.get("condition")
        cond_type = cond_type_obj if isinstance(cond_type_obj, str) else ""
        return cond_type == "state" or (
            not cond_type and "entity_id" in condition and "state" in condition
        )

    def _may_allow_state_changes(self, action: dict[str, Any]) -> bool:
        return any(
            key in action
            for key in (
                "delay",
                "wait_template",
                "wait_for_trigger",
                "wait_for_completion",
                "service",
                "action",
                "scene",
                "event",
                "device_id",
                "choose",
                "if",
                "repeat",
                "parallel",
            )
        )

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
        if self._is_state_condition(cond):
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
        mutated_state_keys: set[tuple[str, str | None]] | None = None,
    ) -> None:
        cond_type_obj = condition.get("condition")
        cond_type = cond_type_obj if isinstance(cond_type_obj, str) else ""
        if self._is_state_condition(condition):
            states = self._normalize_values(condition.get("state"))
            if len(states) != 1 or is_template_value(states[0]):
                return
            state = states[0]
            attribute_obj = condition.get("attribute")
            attr_name = attribute_obj if isinstance(attribute_obj, str) else None
            entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
            for entity_id in entity_ids:
                key = (entity_id, attr_name)
                if mutated_state_keys is not None and key in mutated_state_keys:
                    continue
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
                mutated_state_keys=mutated_state_keys,
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
        mutated_state_keys: set[tuple[str, str | None]] | None,
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
            if (
                mutated_state_keys is not None
                and (entity_id, attr_name) in mutated_state_keys
            ):
                continue
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
