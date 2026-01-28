# Conflict Detection & Smart Suggestions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add conflict detection between automations and improve suggestion accuracy using entity relationships.

**Architecture:** Build an Entity-Action Graph to find opposing actions on shared entities. Enhance the fix engine with HA registry queries (areas, devices, labels) and suppression-based learning.

**Tech Stack:** Python 3.12+, Home Assistant Core APIs, pytest-homeassistant-custom-component

---

## Task 1: Add Conflict Data Models

**Files:**
- Modify: `custom_components/autodoctor/models.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_entity_action_creation():
    """Test EntityAction dataclass."""
    from custom_components.autodoctor.models import EntityAction

    action = EntityAction(
        automation_id="automation.motion_lights",
        entity_id="light.living_room",
        action="turn_on",
        value=None,
        conditions=["motion detected"],
    )

    assert action.automation_id == "automation.motion_lights"
    assert action.entity_id == "light.living_room"
    assert action.action == "turn_on"


def test_conflict_creation():
    """Test Conflict dataclass."""
    from custom_components.autodoctor.models import Conflict, Severity

    conflict = Conflict(
        entity_id="light.living_room",
        automation_a="automation.motion_lights",
        automation_b="automation.away_mode",
        action_a="turn_on",
        action_b="turn_off",
        severity=Severity.ERROR,
        explanation="Both automations affect light.living_room",
        scenario="Motion detected while nobody_home",
    )

    assert conflict.entity_id == "light.living_room"
    assert conflict.severity == Severity.ERROR


def test_conflict_to_dict():
    """Test Conflict serialization."""
    from custom_components.autodoctor.models import Conflict, Severity

    conflict = Conflict(
        entity_id="light.living_room",
        automation_a="automation.motion_lights",
        automation_b="automation.away_mode",
        action_a="turn_on",
        action_b="turn_off",
        severity=Severity.ERROR,
        explanation="Both automations affect light.living_room",
        scenario="Motion detected while nobody_home",
    )

    d = conflict.to_dict()
    assert d["entity_id"] == "light.living_room"
    assert d["severity"] == "error"
    assert d["automation_a"] == "automation.motion_lights"


def test_conflict_suppression_key():
    """Test Conflict suppression key generation."""
    from custom_components.autodoctor.models import Conflict, Severity

    conflict = Conflict(
        entity_id="light.living_room",
        automation_a="automation.motion_lights",
        automation_b="automation.away_mode",
        action_a="turn_on",
        action_b="turn_off",
        severity=Severity.ERROR,
        explanation="Both automations affect light.living_room",
        scenario="Motion detected while nobody_home",
    )

    key = conflict.get_suppression_key()
    assert key == "automation.motion_lights:automation.away_mode:light.living_room:conflict"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_entity_action_creation -v`
Expected: FAIL with "cannot import name 'EntityAction'"

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/models.py` after `StateReference`:

```python
@dataclass
class EntityAction:
    """An action that affects an entity, extracted from an automation."""

    automation_id: str
    entity_id: str
    action: str  # "turn_on", "turn_off", "toggle", "set"
    value: Any  # For set actions (brightness, temperature, etc.)
    conditions: list[str]  # Human-readable condition summary


@dataclass
class Conflict:
    """A detected conflict between two automations."""

    entity_id: str
    automation_a: str
    automation_b: str
    action_a: str
    action_b: str
    severity: Severity
    explanation: str
    scenario: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "entity_id": self.entity_id,
            "automation_a": self.automation_a,
            "automation_b": self.automation_b,
            "action_a": self.action_a,
            "action_b": self.action_b,
            "severity": self.severity.name.lower(),
            "explanation": self.explanation,
            "scenario": self.scenario,
        }

    def get_suppression_key(self) -> str:
        """Generate a unique key for suppressing this conflict."""
        # Sort automation IDs for consistent key regardless of order
        auto_ids = sorted([self.automation_a, self.automation_b])
        return f"{auto_ids[0]}:{auto_ids[1]}:{self.entity_id}:conflict"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -k "entity_action or conflict" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/models.py tests/test_models.py
git commit -m "feat(models): add EntityAction and Conflict dataclasses"
```

---

## Task 2: Extract Service Calls from Actions

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_service_calls_turn_on():
    """Test extraction of turn_on service call."""
    automation = {
        "id": "motion_lights",
        "alias": "Motion Lights",
        "trigger": [],
        "action": [
            {
                "service": "light.turn_on",
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].automation_id == "automation.motion_lights"
    assert actions[0].entity_id == "light.living_room"
    assert actions[0].action == "turn_on"


def test_extract_service_calls_turn_off():
    """Test extraction of turn_off service call."""
    automation = {
        "id": "away_mode",
        "alias": "Away Mode",
        "trigger": [],
        "action": [
            {
                "service": "light.turn_off",
                "entity_id": "light.living_room",
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].action == "turn_off"


def test_extract_service_calls_toggle():
    """Test extraction of toggle service call."""
    automation = {
        "id": "toggle_lights",
        "alias": "Toggle Lights",
        "trigger": [],
        "action": [
            {
                "service": "light.toggle",
                "target": {"entity_id": "light.living_room"},
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 1
    assert actions[0].action == "toggle"


def test_extract_service_calls_nested_choose():
    """Test extraction from nested choose blocks."""
    automation = {
        "id": "complex",
        "alias": "Complex",
        "trigger": [],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [],
                        "sequence": [
                            {
                                "service": "light.turn_on",
                                "target": {"entity_id": "light.bedroom"},
                            }
                        ],
                    }
                ],
                "default": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.bedroom"},
                    }
                ],
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 2
    action_types = {a.action for a in actions}
    assert action_types == {"turn_on", "turn_off"}


def test_extract_service_calls_multiple_entities():
    """Test extraction with multiple entity targets."""
    automation = {
        "id": "all_off",
        "alias": "All Off",
        "trigger": [],
        "action": [
            {
                "service": "light.turn_off",
                "target": {
                    "entity_id": ["light.living_room", "light.kitchen"],
                },
            }
        ],
    }

    analyzer = AutomationAnalyzer()
    actions = analyzer.extract_entity_actions(automation)

    assert len(actions) == 2
    entity_ids = {a.entity_id for a in actions}
    assert entity_ids == {"light.living_room", "light.kitchen"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_service_calls_turn_on -v`
Expected: FAIL with "has no attribute 'extract_entity_actions'"

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/analyzer.py`:

```python
from .models import EntityAction  # Add to imports

# Add this method to AutomationAnalyzer class:

def extract_entity_actions(self, automation: dict[str, Any]) -> list[EntityAction]:
    """Extract all entity actions (service calls) from an automation."""
    actions: list[EntityAction] = []

    automation_id = f"automation.{automation.get('id', 'unknown')}"

    # Get actions (support both 'action' and 'actions' keys)
    action_list = automation.get("actions") or automation.get("action", [])
    if not isinstance(action_list, list):
        action_list = [action_list]

    actions.extend(self._extract_actions_recursive(action_list, automation_id))

    return actions

def _extract_actions_recursive(
    self,
    action_list: list[dict[str, Any]],
    automation_id: str,
) -> list[EntityAction]:
    """Recursively extract EntityActions from action blocks."""
    results: list[EntityAction] = []

    for action in action_list:
        if not isinstance(action, dict):
            continue

        # Direct service call
        if "service" in action:
            results.extend(
                self._parse_service_call(action, automation_id)
            )

        # Choose block
        if "choose" in action:
            for option in action.get("choose", []):
                sequence = option.get("sequence", [])
                results.extend(
                    self._extract_actions_recursive(sequence, automation_id)
                )
            default = action.get("default", [])
            if default:
                results.extend(
                    self._extract_actions_recursive(default, automation_id)
                )

        # If/then/else block
        if "if" in action:
            then_actions = action.get("then", [])
            else_actions = action.get("else", [])
            results.extend(
                self._extract_actions_recursive(then_actions, automation_id)
            )
            if else_actions:
                results.extend(
                    self._extract_actions_recursive(else_actions, automation_id)
                )

        # Repeat block
        if "repeat" in action:
            sequence = action["repeat"].get("sequence", [])
            results.extend(
                self._extract_actions_recursive(sequence, automation_id)
            )

        # Parallel block
        if "parallel" in action:
            branches = action["parallel"]
            if not isinstance(branches, list):
                branches = [branches]
            for branch in branches:
                branch_actions = branch if isinstance(branch, list) else [branch]
                results.extend(
                    self._extract_actions_recursive(branch_actions, automation_id)
                )

    return results

def _parse_service_call(
    self,
    action: dict[str, Any],
    automation_id: str,
) -> list[EntityAction]:
    """Parse a service call action into EntityAction objects."""
    results: list[EntityAction] = []

    service = action.get("service", "")
    if not service or "." not in service:
        return results

    domain, service_name = service.split(".", 1)

    # Determine the action type
    if service_name in ("turn_on",):
        action_type = "turn_on"
    elif service_name in ("turn_off",):
        action_type = "turn_off"
    elif service_name in ("toggle",):
        action_type = "toggle"
    else:
        action_type = "set"

    # Extract entity IDs from target or entity_id
    entity_ids: list[str] = []

    target = action.get("target", {})
    if isinstance(target, dict):
        target_entities = target.get("entity_id", [])
        if isinstance(target_entities, str):
            entity_ids.append(target_entities)
        elif isinstance(target_entities, list):
            entity_ids.extend(target_entities)

    # Also check direct entity_id field
    direct_entity = action.get("entity_id")
    if direct_entity:
        if isinstance(direct_entity, str):
            entity_ids.append(direct_entity)
        elif isinstance(direct_entity, list):
            entity_ids.extend(direct_entity)

    # Get optional value for set actions
    value = action.get("data", {}) if action_type == "set" else None

    for entity_id in entity_ids:
        results.append(
            EntityAction(
                automation_id=automation_id,
                entity_id=entity_id,
                action=action_type,
                value=value,
                conditions=[],  # Will be populated later
            )
        )

    return results
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py -k "extract_service" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat(analyzer): extract service calls as EntityActions"
```

---

## Task 3: Create Conflict Detector

**Files:**
- Create: `custom_components/autodoctor/conflict_detector.py`
- Create: `tests/test_conflict_detector.py`

**Step 1: Write the failing test**

Create `tests/test_conflict_detector.py`:

```python
"""Tests for ConflictDetector."""

import pytest
from custom_components.autodoctor.conflict_detector import ConflictDetector
from custom_components.autodoctor.models import Severity


def test_detect_on_off_conflict():
    """Test detection of turn_on vs turn_off conflict."""
    automations = [
        {
            "id": "motion_lights",
            "alias": "Motion Lights",
            "trigger": [{"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "away_mode",
            "alias": "Away Mode",
            "trigger": [{"platform": "state", "entity_id": "person.matt", "to": "not_home"}],
            "action": [{"service": "light.turn_off", "target": {"entity_id": "light.living_room"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 1
    assert conflicts[0].entity_id == "light.living_room"
    assert conflicts[0].severity == Severity.ERROR
    assert "turn_on" in conflicts[0].action_a or "turn_on" in conflicts[0].action_b
    assert "turn_off" in conflicts[0].action_a or "turn_off" in conflicts[0].action_b


def test_no_conflict_different_entities():
    """Test no conflict when different entities."""
    automations = [
        {
            "id": "motion_lights",
            "alias": "Motion Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "away_mode",
            "alias": "Away Mode",
            "trigger": [],
            "action": [{"service": "light.turn_off", "target": {"entity_id": "light.kitchen"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 0


def test_toggle_warning():
    """Test toggle generates warning."""
    automations = [
        {
            "id": "toggle_lights",
            "alias": "Toggle Lights",
            "trigger": [],
            "action": [{"service": "light.toggle", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "turn_on_lights",
            "alias": "Turn On Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 1
    assert conflicts[0].severity == Severity.WARNING


def test_no_conflict_same_action():
    """Test no conflict when both do same action."""
    automations = [
        {
            "id": "motion_lights",
            "alias": "Motion Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "door_lights",
            "alias": "Door Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 0


def test_multiple_conflicts():
    """Test detection of multiple conflicts."""
    automations = [
        {
            "id": "auto1",
            "alias": "Auto 1",
            "trigger": [],
            "action": [
                {"service": "light.turn_on", "target": {"entity_id": "light.living_room"}},
                {"service": "light.turn_on", "target": {"entity_id": "light.kitchen"}},
            ],
        },
        {
            "id": "auto2",
            "alias": "Auto 2",
            "trigger": [],
            "action": [
                {"service": "light.turn_off", "target": {"entity_id": "light.living_room"}},
                {"service": "light.turn_off", "target": {"entity_id": "light.kitchen"}},
            ],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 2
    entity_ids = {c.entity_id for c in conflicts}
    assert entity_ids == {"light.living_room", "light.kitchen"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_conflict_detector.py::test_detect_on_off_conflict -v`
Expected: FAIL with "No module named 'custom_components.autodoctor.conflict_detector'"

**Step 3: Write minimal implementation**

Create `custom_components/autodoctor/conflict_detector.py`:

```python
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
        """Detect conflicts across all automations.

        Args:
            automations: List of automation configurations.

        Returns:
            List of detected conflicts.
        """
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

            conflicts.extend(
                self._find_conflicts_for_entity(entity_id, actions)
            )

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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_conflict_detector.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/conflict_detector.py tests/test_conflict_detector.py
git commit -m "feat: add ConflictDetector for automation conflict analysis"
```

---

## Task 4: Add WebSocket API for Conflicts

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py`
- Modify: `custom_components/autodoctor/__init__.py`
- Test: `tests/test_websocket_api.py`

**Step 1: Write the failing test**

Add to `tests/test_websocket_api.py`:

```python
@pytest.mark.asyncio
async def test_websocket_get_conflicts(hass, mock_connection):
    """Test getting conflicts via WebSocket."""
    from custom_components.autodoctor.websocket_api import websocket_get_conflicts
    from custom_components.autodoctor.models import Conflict, Severity
    from custom_components.autodoctor.const import DOMAIN

    # Set up mock data
    hass.data[DOMAIN] = {
        "conflicts": [
            Conflict(
                entity_id="light.living_room",
                automation_a="automation.motion",
                automation_b="automation.away",
                action_a="turn_on",
                action_b="turn_off",
                severity=Severity.ERROR,
                explanation="Test conflict",
                scenario="Test scenario",
            )
        ],
        "conflicts_last_run": "2026-01-27T12:00:00",
        "suppression_store": None,
    }

    msg = {"id": 1, "type": "autodoctor/conflicts"}

    await websocket_get_conflicts(hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    result = mock_connection.send_result.call_args[0][1]
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["entity_id"] == "light.living_room"


@pytest.mark.asyncio
async def test_websocket_run_conflicts(hass, mock_connection):
    """Test running conflict detection via WebSocket."""
    from custom_components.autodoctor.websocket_api import websocket_run_conflicts
    from custom_components.autodoctor.const import DOMAIN

    # Set up mock automation data
    hass.data["automation"] = {
        "config": [
            {
                "id": "motion",
                "alias": "Motion",
                "trigger": [],
                "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
            },
            {
                "id": "away",
                "alias": "Away",
                "trigger": [],
                "action": [{"service": "light.turn_off", "target": {"entity_id": "light.living_room"}}],
            },
        ]
    }
    hass.data[DOMAIN] = {"suppression_store": None}

    msg = {"id": 1, "type": "autodoctor/conflicts/run"}

    await websocket_run_conflicts(hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    result = mock_connection.send_result.call_args[0][1]
    assert len(result["conflicts"]) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_websocket_api.py::test_websocket_get_conflicts -v`
Expected: FAIL with "cannot import name 'websocket_get_conflicts'"

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/websocket_api.py`:

```python
# Add import at top
from .conflict_detector import ConflictDetector

# Add to async_setup_websocket_api function:
websocket_api.async_register_command(hass, websocket_get_conflicts)
websocket_api.async_register_command(hass, websocket_run_conflicts)

# Add these functions:

def _format_conflicts(conflicts: list, suppression_store) -> tuple[list[dict], int]:
    """Format conflicts, filtering suppressed ones."""
    if suppression_store:
        visible = [
            c for c in conflicts
            if not suppression_store.is_suppressed(c.get_suppression_key())
        ]
        suppressed_count = len(conflicts) - len(visible)
    else:
        visible = conflicts
        suppressed_count = 0

    formatted = [c.to_dict() for c in visible]
    return formatted, suppressed_count


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/conflicts",
    }
)
@websocket_api.async_response
async def websocket_get_conflicts(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get conflict detection results."""
    data = hass.data.get(DOMAIN, {})
    conflicts = data.get("conflicts", [])
    last_run = data.get("conflicts_last_run")
    suppression_store = data.get("suppression_store")

    formatted, suppressed_count = _format_conflicts(conflicts, suppression_store)

    connection.send_result(
        msg["id"],
        {
            "conflicts": formatted,
            "last_run": last_run,
            "suppressed_count": suppressed_count,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/conflicts/run",
    }
)
@websocket_api.async_response
async def websocket_run_conflicts(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run conflict detection and return results."""
    from datetime import datetime, timezone

    data = hass.data.get(DOMAIN, {})
    suppression_store = data.get("suppression_store")

    # Get automation configs
    automation_data = hass.data.get("automation", {})
    if isinstance(automation_data, dict):
        automations = automation_data.get("config", [])
    elif hasattr(automation_data, "entities"):
        automations = [
            e.raw_config for e in automation_data.entities
            if hasattr(e, "raw_config") and e.raw_config
        ]
    else:
        automations = []

    # Detect conflicts
    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    # Store results
    last_run = datetime.now(timezone.utc).isoformat()
    hass.data[DOMAIN]["conflicts"] = conflicts
    hass.data[DOMAIN]["conflicts_last_run"] = last_run

    formatted, suppressed_count = _format_conflicts(conflicts, suppression_store)

    connection.send_result(
        msg["id"],
        {
            "conflicts": formatted,
            "last_run": last_run,
            "suppressed_count": suppressed_count,
        },
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_websocket_api.py -k "conflicts" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py tests/test_websocket_api.py
git commit -m "feat(api): add WebSocket endpoints for conflict detection"
```

---

## Task 5: Create Entity Graph for Relationship Queries

**Files:**
- Create: `custom_components/autodoctor/entity_graph.py`
- Create: `tests/test_entity_graph.py`

**Step 1: Write the failing test**

Create `tests/test_entity_graph.py`:

```python
"""Tests for EntityGraph."""

import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance with registries."""
    hass = MagicMock()

    # Mock entity registry
    entity_registry = MagicMock()
    entity_registry.async_get.return_value = MagicMock(
        entity_id="light.kitchen",
        device_id="device_kitchen",
        area_id="area_kitchen",
        labels={"ceiling"},
    )
    hass.data = {"entity_registry": entity_registry}

    # Mock helpers
    from unittest.mock import patch

    return hass


def test_entity_graph_same_area():
    """Test same_area check."""
    from custom_components.autodoctor.entity_graph import EntityGraph

    graph = EntityGraph()

    # Manually populate for testing
    graph._entity_areas = {
        "light.kitchen": "kitchen",
        "switch.kitchen_fan": "kitchen",
        "light.bedroom": "bedroom",
    }

    assert graph.same_area("light.kitchen", "switch.kitchen_fan") is True
    assert graph.same_area("light.kitchen", "light.bedroom") is False


def test_entity_graph_same_device():
    """Test same_device check."""
    from custom_components.autodoctor.entity_graph import EntityGraph

    graph = EntityGraph()

    graph._entity_devices = {
        "sensor.temp": "device_1",
        "sensor.humidity": "device_1",
        "sensor.motion": "device_2",
    }

    assert graph.same_device("sensor.temp", "sensor.humidity") is True
    assert graph.same_device("sensor.temp", "sensor.motion") is False


def test_entity_graph_same_domain():
    """Test same_domain check."""
    from custom_components.autodoctor.entity_graph import EntityGraph

    graph = EntityGraph()

    assert graph.same_domain("light.kitchen", "light.bedroom") is True
    assert graph.same_domain("light.kitchen", "switch.kitchen") is False


def test_entity_graph_relationship_score():
    """Test relationship scoring."""
    from custom_components.autodoctor.entity_graph import EntityGraph

    graph = EntityGraph()

    # Set up test data
    graph._entity_areas = {
        "light.kitchen": "kitchen",
        "switch.kitchen_fan": "kitchen",
    }
    graph._entity_devices = {
        "light.kitchen": "device_1",
        "switch.kitchen_fan": "device_1",
    }
    graph._entity_labels = {
        "light.kitchen": {"ceiling"},
        "switch.kitchen_fan": {"ceiling"},
    }

    # Same device + same area + shared labels = high score
    score = graph.relationship_score("light.kitchen", "switch.kitchen_fan")
    assert score >= 0.8  # Should be high

    # Different entities with no relationship
    graph._entity_areas["light.bedroom"] = "bedroom"
    graph._entity_devices["light.bedroom"] = "device_2"
    graph._entity_labels["light.bedroom"] = set()

    score = graph.relationship_score("light.kitchen", "light.bedroom")
    assert score < 0.4  # Should be low (only domain match)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_entity_graph.py::test_entity_graph_same_area -v`
Expected: FAIL with "No module named 'custom_components.autodoctor.entity_graph'"

**Step 3: Write minimal implementation**

Create `custom_components/autodoctor/entity_graph.py`:

```python
"""EntityGraph - queries entity relationships from HA registries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EntityGraph:
    """Provides entity relationship queries based on HA registries."""

    def __init__(self) -> None:
        """Initialize the entity graph."""
        self._entity_areas: dict[str, str | None] = {}
        self._entity_devices: dict[str, str | None] = {}
        self._entity_labels: dict[str, set[str]] = {}
        self._loaded = False

    async def async_load(self, hass: HomeAssistant) -> None:
        """Load entity relationships from HA registries."""
        try:
            from homeassistant.helpers import (
                entity_registry as er,
                device_registry as dr,
                area_registry as ar,
            )

            entity_registry = er.async_get(hass)
            device_registry = dr.async_get(hass)

            for entry in entity_registry.entities.values():
                entity_id = entry.entity_id

                # Get area (direct or via device)
                area_id = entry.area_id
                if not area_id and entry.device_id:
                    device = device_registry.async_get(entry.device_id)
                    if device:
                        area_id = device.area_id

                self._entity_areas[entity_id] = area_id
                self._entity_devices[entity_id] = entry.device_id
                self._entity_labels[entity_id] = set(entry.labels) if entry.labels else set()

            self._loaded = True
            _LOGGER.debug("EntityGraph loaded %d entities", len(self._entity_areas))

        except Exception as e:
            _LOGGER.warning("Failed to load entity graph: %s", e)

    def same_area(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are in the same area."""
        area_a = self._entity_areas.get(entity_a)
        area_b = self._entity_areas.get(entity_b)
        return area_a is not None and area_a == area_b

    def same_device(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are on the same device."""
        device_a = self._entity_devices.get(entity_a)
        device_b = self._entity_devices.get(entity_b)
        return device_a is not None and device_a == device_b

    def same_domain(self, entity_a: str, entity_b: str) -> bool:
        """Check if two entities are in the same domain."""
        if "." not in entity_a or "." not in entity_b:
            return False
        return entity_a.split(".")[0] == entity_b.split(".")[0]

    def shared_labels(self, entity_a: str, entity_b: str) -> set[str]:
        """Get labels shared between two entities."""
        labels_a = self._entity_labels.get(entity_a, set())
        labels_b = self._entity_labels.get(entity_b, set())
        return labels_a & labels_b

    def relationship_score(self, reference: str, candidate: str) -> float:
        """Calculate a relationship score between two entities.

        Returns a score from 0.0 to 1.0 based on:
        - Same device: 0.4
        - Same area: 0.3
        - Same domain: 0.2
        - Shared labels: 0.1
        """
        score = 0.0

        if self.same_device(reference, candidate):
            score += 0.4

        if self.same_area(reference, candidate):
            score += 0.3

        if self.same_domain(reference, candidate):
            score += 0.2

        if self.shared_labels(reference, candidate):
            score += 0.1

        return score

    def get_area(self, entity_id: str) -> str | None:
        """Get the area for an entity."""
        return self._entity_areas.get(entity_id)

    def get_device(self, entity_id: str) -> str | None:
        """Get the device for an entity."""
        return self._entity_devices.get(entity_id)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_entity_graph.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/entity_graph.py tests/test_entity_graph.py
git commit -m "feat: add EntityGraph for relationship-based queries"
```

---

## Task 6: Create Suggestion Learner

**Files:**
- Create: `custom_components/autodoctor/suggestion_learner.py`
- Create: `tests/test_suggestion_learner.py`

**Step 1: Write the failing test**

Create `tests/test_suggestion_learner.py`:

```python
"""Tests for SuggestionLearner."""

import pytest
from unittest.mock import MagicMock, AsyncMock


def test_record_rejection():
    """Test recording a suggestion rejection."""
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner

    learner = SuggestionLearner()

    learner.record_rejection("sensor.temp", "sensor.humidity")

    assert learner.get_rejection_count("sensor.temp", "sensor.humidity") == 1

    learner.record_rejection("sensor.temp", "sensor.humidity")

    assert learner.get_rejection_count("sensor.temp", "sensor.humidity") == 2


def test_penalty_after_rejections():
    """Test penalty calculation after rejections."""
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner

    learner = SuggestionLearner()

    # No rejections = no penalty
    assert learner.get_score_multiplier("a", "b") == 1.0

    # 1 rejection = mild penalty
    learner.record_rejection("a", "b")
    assert learner.get_score_multiplier("a", "b") == 0.7

    # 2+ rejections = heavy penalty
    learner.record_rejection("a", "b")
    assert learner.get_score_multiplier("a", "b") == 0.3


def test_persistence_format():
    """Test data serialization format."""
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner

    learner = SuggestionLearner()
    learner.record_rejection("sensor.a", "sensor.b")
    learner.record_rejection("sensor.a", "sensor.b")
    learner.record_rejection("light.x", "light.y")

    data = learner.to_dict()

    assert "negative_pairs" in data
    assert len(data["negative_pairs"]) == 2

    # Verify can be restored
    learner2 = SuggestionLearner()
    learner2.from_dict(data)

    assert learner2.get_rejection_count("sensor.a", "sensor.b") == 2
    assert learner2.get_rejection_count("light.x", "light.y") == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_suggestion_learner.py::test_record_rejection -v`
Expected: FAIL with "No module named 'custom_components.autodoctor.suggestion_learner'"

**Step 3: Write minimal implementation**

Create `custom_components/autodoctor/suggestion_learner.py`:

```python
"""SuggestionLearner - learns from suppressed suggestions."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = "autodoctor.suggestion_feedback"
STORAGE_VERSION = 1


class SuggestionLearner:
    """Learns from rejected suggestions to improve future recommendations."""

    def __init__(self) -> None:
        """Initialize the suggestion learner."""
        self._rejections: dict[tuple[str, str], int] = defaultdict(int)
        self._store: Store | None = None

    async def async_setup(self, hass: HomeAssistant) -> None:
        """Set up persistent storage."""
        from homeassistant.helpers.storage import Store

        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        data = await self._store.async_load()
        if data:
            self.from_dict(data)

    async def async_save(self) -> None:
        """Save to persistent storage."""
        if self._store:
            await self._store.async_save(self.to_dict())

    def record_rejection(self, from_entity: str, to_entity: str) -> None:
        """Record that a suggestion was rejected."""
        key = (from_entity, to_entity)
        self._rejections[key] += 1

    def get_rejection_count(self, from_entity: str, to_entity: str) -> int:
        """Get the number of times this suggestion was rejected."""
        return self._rejections.get((from_entity, to_entity), 0)

    def get_score_multiplier(self, from_entity: str, to_entity: str) -> float:
        """Get the score multiplier based on rejection history.

        Returns:
            1.0 for no rejections
            0.7 for 1 rejection (mild penalty)
            0.3 for 2+ rejections (heavy penalty)
        """
        count = self.get_rejection_count(from_entity, to_entity)

        if count == 0:
            return 1.0
        elif count == 1:
            return 0.7
        else:
            return 0.3

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "negative_pairs": [
                {"from": k[0], "to": k[1], "count": v}
                for k, v in self._rejections.items()
            ]
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore from dictionary."""
        self._rejections.clear()
        for pair in data.get("negative_pairs", []):
            key = (pair["from"], pair["to"])
            self._rejections[key] = pair["count"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_suggestion_learner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/suggestion_learner.py tests/test_suggestion_learner.py
git commit -m "feat: add SuggestionLearner for rejection-based learning"
```

---

## Task 7: Integrate Smart Suggestions into Fix Engine

**Files:**
- Modify: `custom_components/autodoctor/fix_engine.py`
- Modify: `tests/test_fix_engine.py`

**Step 1: Write the failing test**

Add to `tests/test_fix_engine.py`:

```python
def test_smart_entity_suggestion_same_area():
    """Test entity suggestions prefer same area."""
    from custom_components.autodoctor.fix_engine import FixEngine
    from custom_components.autodoctor.entity_graph import EntityGraph
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner
    from custom_components.autodoctor.models import ValidationIssue, IssueType, Severity

    # Set up mocks
    hass = MagicMock()
    hass.states.async_all.return_value = [
        MagicMock(entity_id="light.kitchen_main"),
        MagicMock(entity_id="light.bedroom_main"),
    ]

    kb = MagicMock()

    entity_graph = EntityGraph()
    entity_graph._entity_areas = {
        "light.kitchen_main": "kitchen",
        "light.bedroom_main": "bedroom",
    }
    entity_graph._entity_devices = {}
    entity_graph._entity_labels = {}

    learner = SuggestionLearner()

    engine = FixEngine(hass, kb, entity_graph, learner)

    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.kichen_main",  # Typo
        location="trigger[0]",
        message="Entity not found: light.kichen_main",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    # Simulate automation context is kitchen-focused
    engine._automation_context = {"primary_area": "kitchen"}

    fix = engine.suggest_fix(issue)

    assert fix is not None
    assert fix.fix_value == "light.kitchen_main"  # Should prefer kitchen


def test_suggestion_penalized_after_rejection():
    """Test suggestions are penalized after rejection."""
    from custom_components.autodoctor.fix_engine import FixEngine
    from custom_components.autodoctor.entity_graph import EntityGraph
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner
    from custom_components.autodoctor.models import ValidationIssue, IssueType, Severity

    hass = MagicMock()
    hass.states.async_all.return_value = [
        MagicMock(entity_id="sensor.kitchen_temp"),
        MagicMock(entity_id="sensor.kitchen_humidity"),
    ]

    kb = MagicMock()
    entity_graph = EntityGraph()
    learner = SuggestionLearner()

    # Record that kitchen_humidity was rejected twice for kitchen_tmp
    learner.record_rejection("sensor.kitchen_tmp", "sensor.kitchen_humidity")
    learner.record_rejection("sensor.kitchen_tmp", "sensor.kitchen_humidity")

    engine = FixEngine(hass, kb, entity_graph, learner)

    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.kitchen_tmp",  # Typo
        location="trigger[0]",
        message="Entity not found: sensor.kitchen_tmp",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    fix = engine.suggest_fix(issue)

    # Should suggest kitchen_temp, not kitchen_humidity (which was rejected)
    assert fix is not None
    assert fix.fix_value == "sensor.kitchen_temp"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_fix_engine.py::test_smart_entity_suggestion_same_area -v`
Expected: FAIL (FixEngine constructor signature mismatch)

**Step 3: Write minimal implementation**

Update `custom_components/autodoctor/fix_engine.py`:

```python
"""FixEngine - generates fix suggestions for validation issues."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from typing import TYPE_CHECKING

from .models import ValidationIssue, IssueType

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .knowledge_base import StateKnowledgeBase
    from .entity_graph import EntityGraph
    from .suggestion_learner import SuggestionLearner


# Semantic mappings for common state synonyms
STATE_SYNONYMS: dict[str, str] = {
    "away": "not_home",
    "gone": "not_home",
    "absent": "not_home",
    "present": "home",
    "arrived": "home",
    "true": "on",
    "false": "off",
    "yes": "on",
    "no": "off",
    "enabled": "on",
    "disabled": "off",
    "active": "on",
    "inactive": "off",
    "open": "on",
    "closed": "off",
    "opened": "on",
}

# Minimum score threshold for suggestions
SUGGESTION_THRESHOLD = 0.6


@dataclass
class FixSuggestion:
    """A suggested fix for a validation issue."""

    description: str
    confidence: float  # 0.0 - 1.0
    fix_value: str | None
    field_path: str | None = None
    reasoning: str | None = None  # Why this suggestion was chosen


class FixEngine:
    """Generates fix suggestions for validation issues."""

    def __init__(
        self,
        hass: HomeAssistant,
        knowledge_base: StateKnowledgeBase,
        entity_graph: EntityGraph | None = None,
        suggestion_learner: SuggestionLearner | None = None,
    ) -> None:
        """Initialize the fix engine."""
        self.hass = hass
        self.knowledge_base = knowledge_base
        self._entity_graph = entity_graph
        self._suggestion_learner = suggestion_learner
        self._automation_context: dict = {}

    def set_automation_context(self, context: dict) -> None:
        """Set context about the current automation being analyzed."""
        self._automation_context = context

    def suggest_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Generate a fix suggestion for an issue."""
        if issue.issue_type == IssueType.ENTITY_NOT_FOUND:
            return self._suggest_entity_fix(issue)
        elif issue.issue_type == IssueType.ENTITY_REMOVED:
            return self._suggest_entity_fix(issue)
        elif issue.issue_type == IssueType.INVALID_STATE:
            return self._suggest_state_fix(issue)
        elif issue.issue_type == IssueType.IMPOSSIBLE_CONDITION:
            return self._suggest_condition_fix(issue)
        return None

    def _suggest_entity_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for missing entity using smart matching."""
        if "." not in issue.entity_id:
            return None

        domain, name = issue.entity_id.split(".", 1)

        # Get entities in same domain
        all_entities = self.hass.states.async_all()
        same_domain = [
            e.entity_id for e in all_entities
            if e.entity_id.startswith(f"{domain}.")
        ]

        if not same_domain:
            return None

        # Score all candidates
        scored_candidates: list[tuple[str, float, str]] = []

        for candidate in same_domain:
            score, reasoning = self._calculate_entity_score(
                issue.entity_id, candidate
            )
            if score >= SUGGESTION_THRESHOLD:
                scored_candidates.append((candidate, score, reasoning))

        if not scored_candidates:
            # Fall back to pure fuzzy matching with lower threshold
            names = {eid.split(".", 1)[1]: eid for eid in same_domain}
            matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)
            if matches:
                matched_entity = names[matches[0]]
                similarity = self._calculate_similarity(name, matches[0])
                return FixSuggestion(
                    description=f"Did you mean '{matched_entity}'?",
                    confidence=similarity,
                    fix_value=matched_entity,
                    field_path="entity_id",
                    reasoning="String similarity",
                )
            return None

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_entity, best_score, reasoning = scored_candidates[0]

        return FixSuggestion(
            description=f"Did you mean '{best_entity}'?",
            confidence=best_score,
            fix_value=best_entity,
            field_path="entity_id",
            reasoning=reasoning,
        )

    def _calculate_entity_score(
        self, reference: str, candidate: str
    ) -> tuple[float, str]:
        """Calculate a combined score for an entity suggestion.

        Returns (score, reasoning).
        """
        reasons = []

        # String similarity (30% weight)
        ref_name = reference.split(".", 1)[1] if "." in reference else reference
        cand_name = candidate.split(".", 1)[1] if "." in candidate else candidate
        fuzzy_score = self._calculate_similarity(ref_name, cand_name)

        # Relationship score (50% weight)
        relationship_score = 0.0
        if self._entity_graph:
            relationship_score = self._entity_graph.relationship_score(
                reference, candidate
            )
            if relationship_score > 0:
                if self._entity_graph.same_device(reference, candidate):
                    reasons.append("Same device")
                elif self._entity_graph.same_area(reference, candidate):
                    reasons.append("Same area")

        # Service compatibility placeholder (20% weight)
        # TODO: Check if candidate supports the service being called
        service_score = 0.2  # Assume compatible for now

        # Combine scores
        base_score = (
            fuzzy_score * 0.3 +
            relationship_score * 0.5 +
            service_score
        )

        # Apply learning penalty
        if self._suggestion_learner:
            multiplier = self._suggestion_learner.get_score_multiplier(
                reference, candidate
            )
            if multiplier < 1.0:
                reasons.append(f"Penalized (previously rejected)")
            base_score *= multiplier

        if not reasons:
            reasons.append("String similarity")

        return base_score, ", ".join(reasons)

    def _suggest_state_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for invalid state."""
        if not issue.valid_states:
            return None

        # Extract the invalid state from the message
        invalid_state = self._extract_invalid_state(issue.message)
        if not invalid_state:
            return None

        # First, check semantic synonyms
        synonym = STATE_SYNONYMS.get(invalid_state.lower())
        if synonym and synonym in issue.valid_states:
            return FixSuggestion(
                description=f"Did you mean '{synonym}'?",
                confidence=0.9,  # High confidence for semantic match
                fix_value=synonym,
                field_path="state",
                reasoning="Semantic synonym",
            )

        # Fall back to fuzzy matching for typos
        matches = get_close_matches(invalid_state, issue.valid_states, n=1, cutoff=0.4)
        if matches:
            similarity = self._calculate_similarity(invalid_state, matches[0])
            return FixSuggestion(
                description=f"Did you mean '{matches[0]}'?",
                confidence=similarity,
                fix_value=matches[0],
                field_path="state",
                reasoning="String similarity",
            )
        return None

    def _suggest_condition_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for impossible condition."""
        if issue.suggestion:
            return FixSuggestion(
                description=f"Change condition state to '{issue.suggestion}'",
                confidence=0.95,
                fix_value=issue.suggestion,
                field_path="condition.state",
                reasoning="Matches trigger state",
            )
        return None

    def _calculate_similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _extract_invalid_state(self, message: str) -> str | None:
        """Extract the invalid state value from an error message."""
        # Pattern: "State 'away' is not valid"
        import re
        match = re.search(r"[Ss]tate ['\"]([^'\"]+)['\"]", message)
        return match.group(1) if match else None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_fix_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/fix_engine.py tests/test_fix_engine.py
git commit -m "feat(fix-engine): integrate smart suggestions with entity graph and learning"
```

---

## Task 8: Update Integration Initialization

**Files:**
- Modify: `custom_components/autodoctor/__init__.py`

**Step 1: Update imports and initialization**

Add entity_graph and suggestion_learner to the initialization in `__init__.py`:

```python
# Add imports
from .entity_graph import EntityGraph
from .suggestion_learner import SuggestionLearner

# In async_setup_entry, after creating knowledge_base:
entity_graph = EntityGraph()
await entity_graph.async_load(hass)

suggestion_learner = SuggestionLearner()
await suggestion_learner.async_setup(hass)

# Update FixEngine instantiation:
fix_engine = FixEngine(hass, knowledge_base, entity_graph, suggestion_learner)

# Store in hass.data:
hass.data[DOMAIN]["entity_graph"] = entity_graph
hass.data[DOMAIN]["suggestion_learner"] = suggestion_learner
```

**Step 2: Run integration test**

Run: `pytest tests/test_init.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add custom_components/autodoctor/__init__.py
git commit -m "feat: wire up EntityGraph and SuggestionLearner in integration init"
```

---

## Task 9: Add Conflicts Tab to Lovelace Card

**Files:**
- Modify: `www/autodoctor/autodoctor-card.ts`
- Modify: `www/autodoctor/types.ts`

**Step 1: Add types**

Add to `www/autodoctor/types.ts`:

```typescript
export interface Conflict {
  entity_id: string;
  automation_a: string;
  automation_b: string;
  action_a: string;
  action_b: string;
  severity: string;
  explanation: string;
  scenario: string;
}

export interface ConflictsTabData {
  conflicts: Conflict[];
  last_run: string | null;
  suppressed_count: number;
}
```

**Step 2: Update card to add Conflicts tab**

The card already has a tabbed structure. Add "Conflicts" as a third tab following the same pattern as Validation and Outcomes tabs.

Key changes:
1. Add `"conflicts"` to `TabType`
2. Add `_conflictsData` state property
3. Add tab button for Conflicts
4. Add `_renderConflictsContent()` method
5. Add conflict-specific styling

**Step 3: Build and test**

```bash
cd www/autodoctor && npm run build
```

**Step 4: Commit**

```bash
git add www/autodoctor/
git commit -m "feat(card): add Conflicts tab to Lovelace card"
```

---

## Task 10: Final Integration Test

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

**Step 2: Manual testing checklist**

- [ ] Validation tab works as before
- [ ] Outcomes tab works as before
- [ ] Conflicts tab shows detected conflicts
- [ ] Suggestions show confidence percentages
- [ ] Suggestions show reasoning
- [ ] Suppressing a suggestion penalizes future suggestions

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete conflict detection and smart suggestions implementation"
```

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | models.py | Add EntityAction and Conflict dataclasses |
| 2 | analyzer.py | Extract service calls from actions |
| 3 | conflict_detector.py | Create ConflictDetector class |
| 4 | websocket_api.py | Add conflict WebSocket endpoints |
| 5 | entity_graph.py | Create EntityGraph for relationship queries |
| 6 | suggestion_learner.py | Create SuggestionLearner for rejection tracking |
| 7 | fix_engine.py | Integrate smart suggestions |
| 8 | __init__.py | Wire up new components |
| 9 | autodoctor-card.ts | Add Conflicts tab to UI |
| 10 | - | Integration testing |
