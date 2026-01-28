"""ConflictDetector - finds conflicting automations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .analyzer import AutomationAnalyzer
from .models import Conflict, EntityAction, Severity


class ConflictDetector:
    """Detects conflicts between automations by analyzing entity actions."""

    def __init__(self) -> None:
        """Initialize the conflict detector."""
        self._analyzer = AutomationAnalyzer()

    def detect_conflicts(self, automations: list[dict[str, Any]]) -> list[Conflict]:
        """Detect conflicts across all automations."""
        # Build entity -> actions map
        entity_actions: dict[str, list[EntityAction]] = defaultdict(list)

        for automation in automations:
            actions = self._analyzer.extract_entity_actions(automation)
            for action in actions:
                entity_actions[action.entity_id].append(action)

        # Find conflicts
        conflicts: list[Conflict] = []

        for entity_id, actions in entity_actions.items():
            if len(actions) < 2:
                continue

            conflicts.extend(self._find_conflicts_for_entity(entity_id, actions))

        return conflicts

    def _find_conflicts_for_entity(
        self,
        entity_id: str,
        actions: list[EntityAction],
    ) -> list[Conflict]:
        """Find conflicts for a single entity."""
        conflicts: list[Conflict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for i, action_a in enumerate(actions):
            for action_b in actions[i + 1:]:
                # Skip if same automation
                if action_a.automation_id == action_b.automation_id:
                    continue

                # Create consistent pair key
                pair_key = tuple(sorted([action_a.automation_id, action_b.automation_id]))
                if pair_key in seen_pairs:
                    continue

                conflict = self._check_conflict(entity_id, action_a, action_b)
                if conflict:
                    seen_pairs.add(pair_key)
                    conflicts.append(conflict)

        return conflicts

    def _check_conflict(
        self,
        entity_id: str,
        action_a: EntityAction,
        action_b: EntityAction,
    ) -> Conflict | None:
        """Check if two actions conflict."""
        type_a = action_a.action
        type_b = action_b.action

        # Toggle conflicts with anything
        if type_a == "toggle" or type_b == "toggle":
            return Conflict(
                entity_id=entity_id,
                automation_a=action_a.automation_id,
                automation_b=action_b.automation_id,
                action_a=type_a,
                action_b=type_b,
                severity=Severity.WARNING,
                explanation=f"Toggle action on {entity_id} may conflict",
                scenario="Toggle behavior is unpredictable with other automations",
            )

        # On/off conflict
        if {type_a, type_b} == {"turn_on", "turn_off"}:
            return Conflict(
                entity_id=entity_id,
                automation_a=action_a.automation_id,
                automation_b=action_b.automation_id,
                action_a=type_a,
                action_b=type_b,
                severity=Severity.ERROR,
                explanation=f"Both automations affect {entity_id} with opposing actions",
                scenario="May conflict when both triggers fire",
            )

        # No conflict for same action type
        return None
