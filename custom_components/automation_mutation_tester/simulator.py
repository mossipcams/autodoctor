"""SimulationEngine - verifies automation outcomes are reachable."""

from __future__ import annotations

import logging
from typing import Any

from .knowledge_base import StateKnowledgeBase
from .models import OutcomeReport, Verdict

_LOGGER = logging.getLogger(__name__)


class SimulationEngine:
    """Verifies that automation actions are reachable."""

    def __init__(self, knowledge_base: StateKnowledgeBase) -> None:
        """Initialize the simulation engine."""
        self.knowledge_base = knowledge_base

    def verify_outcomes(self, automation: dict[str, Any]) -> OutcomeReport:
        """Verify that automation outcomes are reachable."""
        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = automation.get("alias", automation_id)

        triggers_valid = self._verify_triggers(automation.get("trigger", []))
        conditions_result = self._verify_conditions(
            automation.get("trigger", []),
            automation.get("condition", []),
        )
        outcomes = self._extract_outcomes(automation.get("action", []))
        unreachable_paths: list[str] = []

        if not triggers_valid:
            verdict = Verdict.UNREACHABLE
            unreachable_paths.append("Trigger entity does not exist")
        elif not conditions_result["reachable"] or conditions_result["contradictions"]:
            verdict = Verdict.UNREACHABLE
            unreachable_paths.extend(conditions_result["reasons"])
            unreachable_paths.extend(conditions_result["contradictions"])
        else:
            verdict = Verdict.ALL_REACHABLE

        return OutcomeReport(
            automation_id=automation_id,
            automation_name=automation_name,
            triggers_valid=triggers_valid,
            conditions_reachable=conditions_result["reachable"],
            outcomes=outcomes,
            unreachable_paths=unreachable_paths,
            verdict=verdict,
        )

    def _verify_triggers(self, triggers: list[dict[str, Any]]) -> bool:
        """Verify all trigger entities exist."""
        if not isinstance(triggers, list):
            triggers = [triggers]

        for trigger in triggers:
            platform = trigger.get("platform", "")

            if platform in ("state", "numeric_state"):
                entity_ids = trigger.get("entity_id", [])
                if isinstance(entity_ids, str):
                    entity_ids = [entity_ids]

                for entity_id in entity_ids:
                    if not self.knowledge_base.entity_exists(entity_id):
                        return False

        return True

    def _verify_conditions(
        self,
        triggers: list[dict[str, Any]],
        conditions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Verify conditions are reachable and not contradictory."""
        result: dict[str, Any] = {
            "reachable": True,
            "contradictions": [],
            "reasons": [],
        }

        if not isinstance(conditions, list):
            conditions = [conditions]

        trigger_states: dict[str, set[str]] = {}
        if not isinstance(triggers, list):
            triggers = [triggers]

        for trigger in triggers:
            if trigger.get("platform") == "state":
                entity_ids = trigger.get("entity_id", [])
                if isinstance(entity_ids, str):
                    entity_ids = [entity_ids]

                to_state = trigger.get("to")
                if to_state:
                    for entity_id in entity_ids:
                        if entity_id not in trigger_states:
                            trigger_states[entity_id] = set()
                        trigger_states[entity_id].add(str(to_state))

        for condition in conditions:
            if condition.get("condition") == "state":
                entity_id = condition.get("entity_id")
                cond_state = condition.get("state")

                if entity_id and cond_state and entity_id in trigger_states:
                    cond_states = {cond_state} if isinstance(cond_state, str) else set(cond_state)
                    trigger_state_set = trigger_states[entity_id]

                    if not trigger_state_set.intersection(cond_states):
                        result["contradictions"].append(
                            f"Trigger sets {entity_id} to {trigger_state_set}, but condition requires {cond_states}"
                        )
                        result["reachable"] = False

        return result

    def _extract_outcomes(self, actions: list[dict[str, Any]]) -> list[str]:
        """Extract outcome descriptions from actions."""
        outcomes: list[str] = []

        if not isinstance(actions, list):
            actions = [actions]

        for action in actions:
            if "service" in action:
                service = action["service"]
                target = action.get("target", {})
                entity = target.get("entity_id", "")
                outcomes.append(f"{service}({entity})" if entity else service)
            elif "choose" in action:
                outcomes.append("choose: multiple paths")
            elif "if" in action:
                outcomes.append("if: conditional path")

        return outcomes if outcomes else ["No actions defined"]
