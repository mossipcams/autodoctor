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
            auto_data[auto_id] = AutomationData(
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

        # Check if conditions are mutually exclusive
        if self._conditions_mutually_exclusive(data_a.conditions, data_b.conditions):
            return None

        return Conflict(
            entity_id=entity_id,
            automation_a=auto_id_a,
            automation_b=auto_id_b,
            action_a=action_a.action,
            action_b=action_b.action,
            severity=Severity.ERROR,
            explanation=f"Both automations can fire simultaneously with opposing actions on {entity_id}",
            scenario="May conflict when both triggers fire",
        )

    def _triggers_can_overlap(
        self, triggers_a: list[TriggerInfo], triggers_b: list[TriggerInfo]
    ) -> bool:
        """Check if any trigger pair can potentially overlap."""
        # If either has no triggers, assume they could overlap (conservative)
        if not triggers_a or not triggers_b:
            return True

        # If ANY pair can overlap, return True (conservative)
        for ta in triggers_a:
            for tb in triggers_b:
                if self._trigger_pair_can_overlap(ta, tb):
                    return True
        return False

    def _trigger_pair_can_overlap(self, a: TriggerInfo, b: TriggerInfo) -> bool:
        """Check if two specific triggers can potentially fire at the same time."""
        # Same entity state triggers with disjoint to_states
        if a.trigger_type == "state" and b.trigger_type == "state":
            if a.entity_id == b.entity_id and a.to_states and b.to_states:
                if a.to_states.isdisjoint(b.to_states):
                    return False

        # Different specific times
        if a.trigger_type == "time" and b.trigger_type == "time":
            if a.time_value and b.time_value:
                if ":" in a.time_value and ":" in b.time_value:
                    if a.time_value != b.time_value:
                        return False

        # Different sun events
        if a.trigger_type == "sun" and b.trigger_type == "sun":
            if a.sun_event and b.sun_event and a.sun_event != b.sun_event:
                return False

        return True  # Conservative default

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
