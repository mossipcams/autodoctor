# Validation Improvements and Fix Suggestions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add entity removal detection, impossible condition detection, fix suggestions with confidence scores, and a TypeScript Lovelace card to surface issues.

**Architecture:** Extend the existing validation pipeline with new issue types and a FixEngine that generates suggestions. Expose issues via WebSocket API for a custom Lovelace card built with Lit and TypeScript.

**Tech Stack:** Python 3.12+, Home Assistant 2024.1+, TypeScript, Lit 3.x, WebSocket API

---

## Task 1: Add IssueType Enum to Models

**Files:**
- Modify: `custom_components/autodoctor/models.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
from custom_components.autodoctor.models import IssueType


def test_issue_type_enum_values():
    """Test IssueType enum has expected values."""
    assert IssueType.ENTITY_NOT_FOUND.value == "entity_not_found"
    assert IssueType.ENTITY_REMOVED.value == "entity_removed"
    assert IssueType.INVALID_STATE.value == "invalid_state"
    assert IssueType.IMPOSSIBLE_CONDITION.value == "impossible_condition"
    assert IssueType.CASE_MISMATCH.value == "case_mismatch"
    assert IssueType.ATTRIBUTE_NOT_FOUND.value == "attribute_not_found"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_issue_type_enum_values -v`
Expected: FAIL with "cannot import name 'IssueType'"

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/models.py` after the `Severity` class:

```python
from enum import Enum, IntEnum, auto


class IssueType(str, Enum):
    """Types of validation issues."""

    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_REMOVED = "entity_removed"
    INVALID_STATE = "invalid_state"
    IMPOSSIBLE_CONDITION = "impossible_condition"
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py::test_issue_type_enum_values -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/models.py tests/test_models.py
git commit -m "feat(models): add IssueType enum for categorizing validation issues"
```

---

## Task 2: Add issue_type and to_dict to ValidationIssue

**Files:**
- Modify: `custom_components/autodoctor/models.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_validation_issue_has_issue_type():
    """Test ValidationIssue accepts issue_type field."""
    issue = ValidationIssue(
        issue_type=IssueType.ENTITY_NOT_FOUND,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.missing",
        location="trigger[0]",
        message="Entity not found",
    )
    assert issue.issue_type == IssueType.ENTITY_NOT_FOUND


def test_validation_issue_to_dict():
    """Test ValidationIssue.to_dict() returns serializable dict."""
    issue = ValidationIssue(
        issue_type=IssueType.INVALID_STATE,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0].to",
        message="State 'away' is not valid",
        suggestion="not_home",
    )
    result = issue.to_dict()
    assert result["issue_type"] == "invalid_state"
    assert result["severity"] == "error"
    assert result["entity_id"] == "person.matt"
    assert result["message"] == "State 'away' is not valid"
    assert result["suggestion"] == "not_home"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_validation_issue_has_issue_type tests/test_models.py::test_validation_issue_to_dict -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `ValidationIssue` in `custom_components/autodoctor/models.py`:

```python
@dataclass
class ValidationIssue:
    """An issue found during validation."""

    severity: Severity
    automation_id: str
    automation_name: str
    entity_id: str
    location: str
    message: str
    issue_type: IssueType | None = None
    suggestion: str | None = None
    valid_states: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((self.automation_id, self.entity_id, self.location, self.message))

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "issue_type": self.issue_type.value if self.issue_type else None,
            "severity": self.severity.name.lower(),
            "automation_id": self.automation_id,
            "automation_name": self.automation_name,
            "entity_id": self.entity_id,
            "location": self.location,
            "message": self.message,
            "suggestion": self.suggestion,
            "valid_states": self.valid_states,
        }
```

Add import at top: `from typing import Any`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/models.py tests/test_models.py
git commit -m "feat(models): add issue_type field and to_dict method to ValidationIssue"
```

---

## Task 3: Add get_historical_entity_ids to KnowledgeBase

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py`
- Test: `tests/test_knowledge_base.py`

**Step 1: Write the failing test**

Add to `tests/test_knowledge_base.py`:

```python
@pytest.mark.asyncio
async def test_get_historical_entity_ids(hass: HomeAssistant):
    """Test getting historical entity IDs from recorder."""
    kb = StateKnowledgeBase(hass)

    # Simulate loading history with entities
    history_states = [
        MagicMock(state="on"),
        MagicMock(state="off"),
    ]

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        return_value={
            "sensor.old_entity": history_states,
            "sensor.another_old": history_states,
        },
    ):
        await kb.async_load_history(["sensor.old_entity", "sensor.another_old"])

    historical = kb.get_historical_entity_ids()
    assert "sensor.old_entity" in historical
    assert "sensor.another_old" in historical
    assert "sensor.nonexistent" not in historical
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge_base.py::test_get_historical_entity_ids -v`
Expected: FAIL with "has no attribute 'get_historical_entity_ids'"

**Step 3: Write minimal implementation**

Add to `StateKnowledgeBase` class in `custom_components/autodoctor/knowledge_base.py`:

```python
def get_historical_entity_ids(self) -> set[str]:
    """Get entity IDs that have been observed in history."""
    return set(self._observed_states.keys())
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge_base.py::test_get_historical_entity_ids -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat(knowledge_base): add get_historical_entity_ids method"
```

---

## Task 4: Add entity_existed_in_history check to Validator

**Files:**
- Modify: `custom_components/autodoctor/validator.py`
- Test: `tests/test_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_validator.py`:

```python
@pytest.mark.asyncio
async def test_validate_detects_removed_entity(hass: HomeAssistant):
    """Test that validator detects entities that existed in history but are now gone."""
    kb = StateKnowledgeBase(hass)

    # Simulate that this entity was seen in history
    kb._observed_states["sensor.old_sensor"] = {"on", "off"}

    validator = ValidationEngine(kb)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.old_sensor",
        expected_state="on",
        expected_attribute=None,
        location="trigger[0].to",
    )

    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.ENTITY_REMOVED
    assert "existed in history" in issues[0].message.lower() or "removed" in issues[0].message.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_validator.py::test_validate_detects_removed_entity -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Update `validate_reference` in `custom_components/autodoctor/validator.py`:

```python
def validate_reference(self, ref: StateReference) -> list[ValidationIssue]:
    """Validate a single state reference."""
    issues: list[ValidationIssue] = []

    if not self.knowledge_base.entity_exists(ref.entity_id):
        # Check if entity existed in history (removed/renamed vs typo)
        historical_ids = self.knowledge_base.get_historical_entity_ids()
        if ref.entity_id in historical_ids:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.ENTITY_REMOVED,
                    severity=Severity.ERROR,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"Entity '{ref.entity_id}' existed in history but is now missing (removed or renamed)",
                    suggestion=self._suggest_entity(ref.entity_id),
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.ENTITY_NOT_FOUND,
                    severity=Severity.ERROR,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"Entity '{ref.entity_id}' does not exist",
                    suggestion=self._suggest_entity(ref.entity_id),
                )
            )
        return issues

    if ref.expected_state is not None:
        state_issues = self._validate_state(ref)
        issues.extend(state_issues)

    if ref.expected_attribute is not None:
        attr_issues = self._validate_attribute(ref)
        issues.extend(attr_issues)

    return issues
```

Add import at top: `from .models import StateReference, ValidationIssue, Severity, IssueType`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_validator.py -v`
Expected: PASS

**Step 5: Update existing tests to include issue_type**

Some existing tests may need updating to expect `issue_type` in ValidationIssue. Run full test suite:

Run: `pytest tests/ -v`

Fix any failures by adding appropriate `issue_type` to existing ValidationIssue creations.

**Step 6: Commit**

```bash
git add custom_components/autodoctor/validator.py tests/test_validator.py
git commit -m "feat(validator): detect entities that existed in history but are now missing"
```

---

## Task 5: Add trigger/condition compatibility check to Analyzer

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_check_trigger_condition_compatibility_detects_impossible():
    """Test detection of impossible trigger/condition combinations."""
    analyzer = AutomationAnalyzer()

    automation = {
        "id": "test",
        "alias": "Test Automation",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "person.matt",
                "state": "not_home",
            }
        ],
    }

    issues = analyzer.check_trigger_condition_compatibility(automation)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.IMPOSSIBLE_CONDITION
    assert "home" in issues[0].message
    assert "not_home" in issues[0].message


def test_check_trigger_condition_compatibility_allows_matching():
    """Test that matching trigger/condition passes."""
    analyzer = AutomationAnalyzer()

    automation = {
        "id": "test",
        "alias": "Test Automation",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "person.matt",
                "state": "home",
            }
        ],
    }

    issues = analyzer.check_trigger_condition_compatibility(automation)
    assert len(issues) == 0


def test_check_trigger_condition_compatibility_allows_list_match():
    """Test that condition with list including trigger state passes."""
    analyzer = AutomationAnalyzer()

    automation = {
        "id": "test",
        "alias": "Test Automation",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "person.matt",
                "state": ["home", "away"],
            }
        ],
    }

    issues = analyzer.check_trigger_condition_compatibility(automation)
    assert len(issues) == 0
```

Add import at top of test file: `from custom_components.autodoctor.models import IssueType`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_check_trigger_condition_compatibility_detects_impossible -v`
Expected: FAIL with "has no attribute 'check_trigger_condition_compatibility'"

**Step 3: Write minimal implementation**

Add to `AutomationAnalyzer` class in `custom_components/autodoctor/analyzer.py`:

```python
from .models import StateReference, ValidationIssue, Severity, IssueType


def check_trigger_condition_compatibility(
    self, automation: dict[str, Any]
) -> list[ValidationIssue]:
    """Check if triggers and conditions are compatible."""
    automation_id = f"automation.{automation.get('id', 'unknown')}"
    automation_name = automation.get("alias", automation_id)

    triggers = automation.get("triggers") or automation.get("trigger", [])
    conditions = automation.get("conditions") or automation.get("condition", [])

    if not isinstance(triggers, list):
        triggers = [triggers]
    if not isinstance(conditions, list):
        conditions = [conditions]

    # Build map of entity_id -> trigger "to" states
    trigger_states: dict[str, set[str]] = {}
    for trigger in triggers:
        platform = trigger.get("platform") or trigger.get("trigger", "")
        if platform == "state":
            entity_ids = trigger.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            to_state = trigger.get("to")
            if to_state is not None:
                to_states = self._normalize_states(to_state)
                for entity_id in entity_ids:
                    if entity_id not in trigger_states:
                        trigger_states[entity_id] = set()
                    trigger_states[entity_id].update(to_states)

    issues: list[ValidationIssue] = []

    for idx, condition in enumerate(conditions):
        if condition.get("condition") == "state":
            entity_id = condition.get("entity_id")
            required_states = self._normalize_states(condition.get("state"))

            if entity_id and entity_id in trigger_states:
                trigger_to_states = trigger_states[entity_id]
                required_set = set(required_states)

                # Check if there's any overlap
                if not trigger_to_states.intersection(required_set):
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.IMPOSSIBLE_CONDITION,
                            severity=Severity.ERROR,
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            location=f"condition[{idx}].state",
                            message=f"Condition requires '{', '.join(required_states)}' but trigger fires on '{', '.join(trigger_to_states)}'",
                            suggestion=list(trigger_to_states)[0] if trigger_to_states else None,
                        )
                    )

    return issues
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat(analyzer): add trigger/condition compatibility check"
```

---

## Task 6: Create FixEngine

**Files:**
- Create: `custom_components/autodoctor/fix_engine.py`
- Create: `tests/test_fix_engine.py`

**Step 1: Write the failing test**

Create `tests/test_fix_engine.py`:

```python
"""Tests for FixEngine."""

import pytest
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.fix_engine import FixEngine, FixSuggestion
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import ValidationIssue, Severity, IssueType


@pytest.fixture
def knowledge_base(hass: HomeAssistant):
    """Create a StateKnowledgeBase instance."""
    return StateKnowledgeBase(hass)


@pytest.fixture
def fix_engine(hass: HomeAssistant, knowledge_base):
    """Create a FixEngine instance."""
    return FixEngine(hass, knowledge_base)


def test_fix_engine_initialization(fix_engine):
    """Test fix engine can be initialized."""
    assert fix_engine is not None


@pytest.mark.asyncio
async def test_suggest_fix_for_missing_entity(hass: HomeAssistant, fix_engine):
    """Test fix suggestion for missing entity with similar match."""
    # Set up an existing entity that's similar
    hass.states.async_set("sensor.temperature", "23")
    await hass.async_block_till_done()

    issue = ValidationIssue(
        issue_type=IssueType.ENTITY_NOT_FOUND,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.temperatur",  # typo
        location="trigger[0]",
        message="Entity not found",
    )

    fix = fix_engine.suggest_fix(issue)

    assert fix is not None
    assert fix.fix_value == "sensor.temperature"
    assert fix.confidence > 0.5


@pytest.mark.asyncio
async def test_suggest_fix_for_invalid_state(hass: HomeAssistant, knowledge_base, fix_engine):
    """Test fix suggestion for invalid state value."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()

    issue = ValidationIssue(
        issue_type=IssueType.INVALID_STATE,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0].to",
        message="State 'away' is not valid",
        valid_states=["home", "not_home"],
    )

    fix = fix_engine.suggest_fix(issue)

    assert fix is not None
    assert fix.fix_value == "not_home"  # closest match to "away"


def test_fix_suggestion_dataclass():
    """Test FixSuggestion dataclass."""
    fix = FixSuggestion(
        description="Did you mean 'sensor.temperature'?",
        confidence=0.85,
        fix_value="sensor.temperature",
        field_path="entity_id",
    )
    assert fix.description == "Did you mean 'sensor.temperature'?"
    assert fix.confidence == 0.85
    assert fix.fix_value == "sensor.temperature"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_fix_engine.py -v`
Expected: FAIL with "No module named 'custom_components.autodoctor.fix_engine'"

**Step 3: Write minimal implementation**

Create `custom_components/autodoctor/fix_engine.py`:

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


@dataclass
class FixSuggestion:
    """A suggested fix for a validation issue."""

    description: str
    confidence: float  # 0.0 - 1.0
    fix_value: str | None
    field_path: str | None = None


class FixEngine:
    """Generates fix suggestions for validation issues."""

    def __init__(self, hass: HomeAssistant, knowledge_base: StateKnowledgeBase) -> None:
        """Initialize the fix engine."""
        self.hass = hass
        self.knowledge_base = knowledge_base

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
        """Suggest fix for missing entity."""
        all_entities = [s.entity_id for s in self.hass.states.async_all()]
        matches = get_close_matches(issue.entity_id, all_entities, n=1, cutoff=0.6)

        if matches:
            similarity = self._calculate_similarity(issue.entity_id, matches[0])
            return FixSuggestion(
                description=f"Did you mean '{matches[0]}'?",
                confidence=similarity,
                fix_value=matches[0],
                field_path="entity_id",
            )
        return None

    def _suggest_state_fix(self, issue: ValidationIssue) -> FixSuggestion | None:
        """Suggest fix for invalid state."""
        if not issue.valid_states:
            return None

        # Extract the invalid state from the message
        invalid_state = self._extract_invalid_state(issue.message)
        if not invalid_state:
            return None

        matches = get_close_matches(invalid_state, issue.valid_states, n=1, cutoff=0.4)
        if matches:
            similarity = self._calculate_similarity(invalid_state, matches[0])
            return FixSuggestion(
                description=f"Did you mean '{matches[0]}'?",
                confidence=similarity,
                fix_value=matches[0],
                field_path="state",
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
git commit -m "feat: add FixEngine for generating fix suggestions"
```

---

## Task 7: Create WebSocket API

**Files:**
- Create: `custom_components/autodoctor/websocket_api.py`
- Create: `tests/test_websocket_api.py`

**Step 1: Write the failing test**

Create `tests/test_websocket_api.py`:

```python
"""Tests for WebSocket API."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.autodoctor.websocket_api import (
    async_setup_websocket_api,
    websocket_get_issues,
)


@pytest.mark.asyncio
async def test_websocket_api_setup(hass: HomeAssistant):
    """Test WebSocket API can be set up."""
    with patch("homeassistant.components.websocket_api.async_register_command") as mock_register:
        await async_setup_websocket_api(hass)
        assert mock_register.called


@pytest.mark.asyncio
async def test_websocket_get_issues_returns_data(hass: HomeAssistant):
    """Test websocket_get_issues returns issue data."""
    from custom_components.autodoctor.const import DOMAIN
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
    from custom_components.autodoctor.fix_engine import FixEngine

    kb = StateKnowledgeBase(hass)
    fix_engine = FixEngine(hass, kb)

    hass.data[DOMAIN] = {
        "knowledge_base": kb,
        "fix_engine": fix_engine,
        "issues": [],
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {"id": 1, "type": "autodoctor/issues"}

    await websocket_get_issues(hass, connection, msg)

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    assert call_args[0][0] == 1  # message id
    result = call_args[0][1]
    assert "issues" in result
    assert "healthy_count" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_websocket_api.py -v`
Expected: FAIL with "No module named"

**Step 3: Write minimal implementation**

Create `custom_components/autodoctor/websocket_api.py`:

```python
"""WebSocket API for Autodoctor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

if TYPE_CHECKING:
    from .fix_engine import FixEngine

_LOGGER = logging.getLogger(__name__)


async def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Set up WebSocket API."""
    websocket_api.async_register_command(hass, websocket_get_issues)
    websocket_api.async_register_command(hass, websocket_refresh)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/issues",
    }
)
@websocket_api.async_response
async def websocket_get_issues(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get current issues with fix suggestions."""
    data = hass.data.get(DOMAIN, {})
    fix_engine: FixEngine | None = data.get("fix_engine")
    issues: list = data.get("issues", [])

    issues_with_fixes = []
    for issue in issues:
        fix = fix_engine.suggest_fix(issue) if fix_engine else None
        automation_id = issue.automation_id.replace("automation.", "") if issue.automation_id else ""
        issues_with_fixes.append({
            "issue": issue.to_dict(),
            "fix": {
                "description": fix.description,
                "confidence": fix.confidence,
                "fix_value": fix.fix_value,
            } if fix else None,
            "edit_url": f"/config/automation/edit/{automation_id}",
        })

    # Count healthy automations
    automation_data = hass.data.get("automation")
    total_automations = 0
    if automation_data:
        if hasattr(automation_data, "entities"):
            total_automations = len(list(automation_data.entities))
        elif isinstance(automation_data, dict):
            total_automations = len(automation_data.get("config", []))

    automations_with_issues = len(set(i.automation_id for i in issues))
    healthy_count = max(0, total_automations - automations_with_issues)

    connection.send_result(
        msg["id"],
        {
            "issues": issues_with_fixes,
            "healthy_count": healthy_count,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/refresh",
    }
)
@websocket_api.async_response
async def websocket_refresh(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Trigger a validation refresh."""
    from . import async_validate_all

    issues = await async_validate_all(hass)
    hass.data[DOMAIN]["issues"] = issues

    connection.send_result(msg["id"], {"success": True, "issue_count": len(issues)})
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_websocket_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py tests/test_websocket_api.py
git commit -m "feat: add WebSocket API for frontend communication"
```

---

## Task 8: Register WebSocket API and FixEngine in __init__.py

**Files:**
- Modify: `custom_components/autodoctor/__init__.py`

**Step 1: Update imports and setup**

Add to imports in `custom_components/autodoctor/__init__.py`:

```python
from .fix_engine import FixEngine
from .websocket_api import async_setup_websocket_api
```

**Step 2: Update async_setup_entry**

In the `async_setup_entry` function, after creating other components:

```python
fix_engine = FixEngine(hass, knowledge_base)

hass.data[DOMAIN] = {
    "knowledge_base": knowledge_base,
    "analyzer": analyzer,
    "validator": validator,
    "simulator": simulator,
    "reporter": reporter,
    "fix_engine": fix_engine,  # Add this
    "issues": [],  # Add this
    "entry": entry,
    "debounce_task": None,
}

# After platforms setup
await async_setup_websocket_api(hass)  # Add this
```

**Step 3: Update async_validate_all to store issues**

At the end of `async_validate_all`:

```python
hass.data[DOMAIN]["issues"] = all_issues  # Add before return
return all_issues
```

**Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add custom_components/autodoctor/__init__.py
git commit -m "feat: register WebSocket API and FixEngine in integration setup"
```

---

## Task 9: Create TypeScript Card - Types

**Files:**
- Create: `www/autodoctor/types.ts`

**Step 1: Create directory and types file**

```bash
mkdir -p www/autodoctor
```

Create `www/autodoctor/types.ts`:

```typescript
export interface ValidationIssue {
  issue_type: string | null;
  severity: string;
  automation_id: string;
  automation_name: string;
  entity_id: string;
  location: string;
  message: string;
  suggestion: string | null;
  valid_states: string[];
}

export interface FixSuggestion {
  description: string;
  confidence: number;
  fix_value: string | null;
}

export interface IssueWithFix {
  issue: ValidationIssue;
  fix: FixSuggestion | null;
  edit_url: string;
}

export interface AutodoctorData {
  issues: IssueWithFix[];
  healthy_count: number;
}

export interface AutodoctorCardConfig {
  type: string;
  title?: string;
}
```

**Step 2: Commit**

```bash
git add www/autodoctor/types.ts
git commit -m "feat(card): add TypeScript type definitions"
```

---

## Task 10: Create TypeScript Card - Main Component

**Files:**
- Create: `www/autodoctor/autodoctor-card.ts`
- Create: `www/autodoctor/package.json`
- Create: `www/autodoctor/tsconfig.json`

**Step 1: Create package.json**

Create `www/autodoctor/package.json`:

```json
{
  "name": "autodoctor-card",
  "version": "1.0.0",
  "description": "Lovelace card for Autodoctor automation health",
  "type": "module",
  "scripts": {
    "build": "rollup -c",
    "watch": "rollup -c --watch"
  },
  "devDependencies": {
    "@rollup/plugin-node-resolve": "^15.2.3",
    "@rollup/plugin-typescript": "^11.1.6",
    "lit": "^3.1.0",
    "rollup": "^4.9.0",
    "rollup-plugin-terser": "^7.0.2",
    "typescript": "^5.3.0"
  },
  "dependencies": {
    "custom-card-helpers": "^1.9.0"
  }
}
```

**Step 2: Create tsconfig.json**

Create `www/autodoctor/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2021",
    "module": "ESNext",
    "lib": ["ES2021", "DOM"],
    "declaration": true,
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitThis": true,
    "alwaysStrict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "inlineSourceMap": true,
    "inlineSources": true,
    "experimentalDecorators": true,
    "useDefineForClassFields": false,
    "moduleResolution": "node",
    "esModuleInterop": true
  },
  "include": ["*.ts"],
  "exclude": ["node_modules"]
}
```

**Step 3: Create autodoctor-card.ts**

Create `www/autodoctor/autodoctor-card.ts`:

```typescript
import { LitElement, html, css, CSSResultGroup, TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { HomeAssistant } from "custom-card-helpers";

import type { AutodoctorCardConfig, AutodoctorData, IssueWithFix } from "./types";

@customElement("autodoctor-card")
export class AutodoctorCard extends LitElement {
  @property({ attribute: false }) public hass!: HomeAssistant;
  @property({ attribute: false }) public config!: AutodoctorCardConfig;

  @state() private _data: AutodoctorData | null = null;
  @state() private _loading = true;
  @state() private _error: string | null = null;

  public setConfig(config: AutodoctorCardConfig): void {
    this.config = config;
  }

  protected async firstUpdated(): Promise<void> {
    await this._fetchData();
  }

  private async _fetchData(): Promise<void> {
    this._loading = true;
    this._error = null;

    try {
      this._data = await this.hass.callWS<AutodoctorData>({
        type: "autodoctor/issues",
      });
    } catch (err) {
      console.error("Failed to fetch autodoctor data:", err);
      this._error = "Failed to load automation health data";
    }

    this._loading = false;
  }

  private async _refresh(): Promise<void> {
    await this.hass.callWS({ type: "autodoctor/refresh" });
    await this._fetchData();
  }

  protected render(): TemplateResult {
    if (this._loading) {
      return html`
        <ha-card header="${this.config.title || "Automation Health"}">
          <div class="card-content loading">Loading...</div>
        </ha-card>
      `;
    }

    if (this._error) {
      return html`
        <ha-card header="${this.config.title || "Automation Health"}">
          <div class="card-content error">${this._error}</div>
        </ha-card>
      `;
    }

    if (!this._data) {
      return html`
        <ha-card header="${this.config.title || "Automation Health"}">
          <div class="card-content">No data available</div>
        </ha-card>
      `;
    }

    return html`
      <ha-card header="${this.config.title || "Automation Health"}">
        <div class="card-content">
          ${this._data.issues.length > 0
            ? html`
                <div class="issue-count">
                  ${this._data.issues.length} issue${this._data.issues.length > 1 ? "s" : ""} found
                </div>
                ${this._data.issues.map((item) => this._renderIssue(item))}
              `
            : html`<div class="no-issues">No issues detected</div>`}
          <div class="healthy">
            ${this._data.healthy_count} automation${this._data.healthy_count !== 1 ? "s" : ""} healthy
          </div>
          <button class="refresh-btn" @click=${this._refresh}>Refresh</button>
        </div>
      </ha-card>
    `;
  }

  private _renderIssue(item: IssueWithFix): TemplateResult {
    const { issue, fix, edit_url } = item;
    const isError = issue.severity === "error";

    return html`
      <div class="issue ${isError ? "error" : "warning"}">
        <div class="issue-header">
          <span class="severity-icon">${isError ? "✕" : "!"}</span>
          <span class="automation-name">${issue.automation_name}</span>
        </div>
        <div class="issue-message">${issue.message}</div>
        ${fix
          ? html`
              <div class="fix-suggestion">
                <span class="fix-label">Suggested fix:</span> ${fix.description}
                ${fix.confidence > 0.9
                  ? html`<span class="confidence high">High confidence</span>`
                  : fix.confidence > 0.6
                  ? html`<span class="confidence medium">Medium confidence</span>`
                  : ""}
              </div>
            `
          : ""}
        <a href="${edit_url}" class="edit-link">Edit automation</a>
      </div>
    `;
  }

  static get styles(): CSSResultGroup {
    return css`
      .card-content {
        padding: 16px;
      }

      .loading,
      .error {
        text-align: center;
        padding: 32px 16px;
      }

      .error {
        color: var(--error-color);
      }

      .issue-count {
        font-weight: bold;
        margin-bottom: 16px;
        color: var(--error-color);
      }

      .no-issues {
        color: var(--success-color);
        margin-bottom: 16px;
      }

      .issue {
        border-left: 4px solid var(--error-color);
        padding: 12px;
        margin-bottom: 12px;
        background: var(--secondary-background-color);
        border-radius: 0 4px 4px 0;
      }

      .issue.warning {
        border-left-color: var(--warning-color);
      }

      .issue-header {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: bold;
      }

      .severity-icon {
        color: var(--error-color);
        font-weight: bold;
      }

      .issue.warning .severity-icon {
        color: var(--warning-color);
      }

      .issue-message {
        margin: 8px 0;
        color: var(--secondary-text-color);
        font-size: 0.9em;
      }

      .fix-suggestion {
        margin: 8px 0;
        padding: 8px;
        background: var(--primary-background-color);
        border-radius: 4px;
        font-size: 0.9em;
      }

      .fix-label {
        font-weight: 500;
      }

      .confidence {
        margin-left: 8px;
        font-size: 0.8em;
        padding: 2px 6px;
        border-radius: 4px;
      }

      .confidence.high {
        background: var(--success-color);
        color: white;
      }

      .confidence.medium {
        background: var(--warning-color);
        color: white;
      }

      .edit-link {
        display: inline-block;
        margin-top: 8px;
        color: var(--primary-color);
        text-decoration: none;
        font-size: 0.9em;
      }

      .edit-link:hover {
        text-decoration: underline;
      }

      .healthy {
        color: var(--success-color);
        margin-top: 16px;
        padding-top: 16px;
        border-top: 1px solid var(--divider-color);
      }

      .refresh-btn {
        margin-top: 16px;
        padding: 8px 16px;
        background: var(--primary-color);
        color: var(--text-primary-color);
        border: none;
        border-radius: 4px;
        cursor: pointer;
      }

      .refresh-btn:hover {
        opacity: 0.9;
      }
    `;
  }

  public getCardSize(): number {
    return 3;
  }
}

// Register card with HA
(window as any).customCards = (window as any).customCards || [];
(window as any).customCards.push({
  type: "autodoctor-card",
  name: "Autodoctor Card",
  description: "Shows automation health and validation issues",
});
```

**Step 4: Commit**

```bash
git add www/autodoctor/
git commit -m "feat(card): add TypeScript Lovelace card for automation health"
```

---

## Task 11: Create Rollup Build Config

**Files:**
- Create: `www/autodoctor/rollup.config.js`

**Step 1: Create rollup config**

Create `www/autodoctor/rollup.config.js`:

```javascript
import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import { terser } from "rollup-plugin-terser";

export default {
  input: "autodoctor-card.ts",
  output: {
    file: "autodoctor-card.js",
    format: "es",
  },
  plugins: [
    resolve(),
    typescript(),
    terser(),
  ],
};
```

**Step 2: Build the card**

```bash
cd www/autodoctor
npm install
npm run build
```

**Step 3: Commit**

```bash
git add www/autodoctor/
git commit -m "build(card): add Rollup build configuration"
```

---

## Task 12: Final Integration Test

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass

**Step 2: Verify card builds**

```bash
cd www/autodoctor && npm run build
```

Expected: `autodoctor-card.js` is generated

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: complete validation improvements and fix suggestions feature"
```

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 1 | Add IssueType enum | Pending |
| 2 | Add issue_type and to_dict to ValidationIssue | Pending |
| 3 | Add get_historical_entity_ids | Pending |
| 4 | Add entity history check to validator | Pending |
| 5 | Add trigger/condition compatibility check | Pending |
| 6 | Create FixEngine | Pending |
| 7 | Create WebSocket API | Pending |
| 8 | Register components in __init__.py | Pending |
| 9 | Create TypeScript types | Pending |
| 10 | Create TypeScript card | Pending |
| 11 | Create Rollup build | Pending |
| 12 | Final integration test | Pending |
