"""ConflictDetector - finds conflicting automations with trigger overlap awareness."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .analyzer import AutomationAnalyzer
from .models import Conflict, ConditionInfo, EntityAction, Severity, TriggerInfo


@dataclass
class AutomationData:
    """Extracted automation data for conflict detection."""

    name: str
    triggers: list[TriggerInfo]
    conditions: list[ConditionInfo]
    actions: list[EntityAction]


class ConflictDetector:
    """Detects conflicts between automations with trigger overlap awareness."""

    def __init__(self) -> None:
        """Initialize the conflict detector."""
        self._analyzer = AutomationAnalyzer()

    def detect_conflicts(self, automations: list[dict[str, Any]]) -> list[Conflict]:
        """Detect conflicts across all automations."""
        # 1. Build per-automation data
        auto_data: dict[str, AutomationData] = {}
        for auto in automations:
            auto_id = f"automation.{auto.get('id', 'unknown')}"
            auto_name = auto.get("alias") or auto_id
            auto_data[auto_id] = AutomationData(
                name=auto_name,
                triggers=self._analyzer.extract_triggers(auto),
                conditions=self._analyzer.extract_conditions(auto),
                actions=self._analyzer.extract_entity_actions(auto),
            )

        # 2. Group actions by target entity
        actions_by_entity: dict[str, list[tuple[str, EntityAction]]] = defaultdict(list)
        for auto_id, data in auto_data.items():
            for action in data.actions:
                actions_by_entity[action.entity_id].append((auto_id, action))

        # 3. Check each entity for conflicts
        conflicts: list[Conflict] = []
        seen_pairs: set[tuple[str, str, str]] = set()  # (auto_a, auto_b, entity)

        for entity_id, action_list in actions_by_entity.items():
            for i, (auto_id_a, action_a) in enumerate(action_list):
                for auto_id_b, action_b in action_list[i + 1:]:
                    if auto_id_a == auto_id_b:
                        continue

                    # Create consistent pair key
                    pair_key = tuple(sorted([auto_id_a, auto_id_b]) + [entity_id])
                    if pair_key in seen_pairs:
                        continue

                    conflict = self._check_conflict(
                        entity_id,
                        auto_id_a, action_a, auto_data[auto_id_a],
                        auto_id_b, action_b, auto_data[auto_id_b],
                    )
                    if conflict:
                        seen_pairs.add(pair_key)
                        conflicts.append(conflict)

        return conflicts

    def _check_conflict(
        self,
        entity_id: str,
        auto_id_a: str,
        action_a: EntityAction,
        data_a: AutomationData,
        auto_id_b: str,
        action_b: EntityAction,
        data_b: AutomationData,
    ) -> Conflict | None:
        """Check if two actions conflict."""
        # Only care about turn_on vs turn_off (skip toggle - too noisy)
        if {action_a.action, action_b.action} != {"turn_on", "turn_off"}:
            return None

        # Check if triggers can overlap
        if not self._triggers_can_overlap(data_a.triggers, data_b.triggers):
            return None

        # Combine automation-level and action-level conditions
        combined_conditions_a = data_a.conditions + action_a.conditions
        combined_conditions_b = data_b.conditions + action_b.conditions

        # Check if combined conditions are mutually exclusive
        if self._conditions_mutually_exclusive(combined_conditions_a, combined_conditions_b):
            return None

        return Conflict(
            entity_id=entity_id,
            automation_a=auto_id_a,
            automation_b=auto_id_b,
            automation_a_name=data_a.name,
            automation_b_name=data_b.name,
            action_a=action_a.action,
            action_b=action_b.action,
            severity=Severity.ERROR,
            explanation=f"Both automations can fire simultaneously with opposing actions on {entity_id}",
            scenario="May conflict when both triggers fire",
        )

    def _triggers_can_overlap(
        self, triggers_a: list[TriggerInfo], triggers_b: list[TriggerInfo]
    ) -> bool:
        """Check if any trigger pair can potentially overlap.

        Uses strict matching - only returns True if triggers are very likely
        to fire at the same time.
        """
        # If either has no triggers, can't determine - assume no overlap
        if not triggers_a or not triggers_b:
            return False

        # Check if ANY pair can overlap
        for ta in triggers_a:
            for tb in triggers_b:
                if self._trigger_pair_can_overlap(ta, tb):
                    return True
        return False

    def _trigger_pair_can_overlap(self, a: TriggerInfo, b: TriggerInfo) -> bool:
        """Check if two specific triggers can potentially fire at the same time.

        Strict mode: only returns True when triggers are very likely to coincide.
        """
        # Different trigger types rarely fire at the same moment
        if a.trigger_type != b.trigger_type:
            return False

        # Same type - check specifics
        if a.trigger_type == "state":
            # Different entities = different triggers, won't fire together
            if a.entity_id != b.entity_id:
                return False
            # Same entity - check if to_states overlap
            if a.to_states and b.to_states:
                return not a.to_states.isdisjoint(b.to_states)
            # Same entity, at least one has no to_state filter = could overlap
            return True

        if a.trigger_type == "time":
            # Only overlap if same time
            if a.time_value and b.time_value:
                return a.time_value == b.time_value
            return False

        if a.trigger_type == "sun":
            # Only overlap if same sun event
            if a.sun_event and b.sun_event:
                return a.sun_event == b.sun_event
            return False

        # Other trigger types (template, event, etc.) - assume no overlap
        return False

    def _conditions_mutually_exclusive(
        self, conds_a: list[ConditionInfo], conds_b: list[ConditionInfo]
    ) -> bool:
        """Check if conditions are mutually exclusive."""
        for ca in conds_a:
            for cb in conds_b:
                if ca.entity_id == cb.entity_id:
                    # Same entity, different required states = mutually exclusive
                    if ca.required_states.isdisjoint(cb.required_states):
                        return True
        return False
