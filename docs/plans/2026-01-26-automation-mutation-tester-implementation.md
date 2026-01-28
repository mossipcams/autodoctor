# Automation Mutation Tester Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Home Assistant custom integration that validates automations against known valid states before they fail in production.

**Architecture:** Two-phase validation: StateKnowledgeBase builds valid states from device classes, recorder history, and schema introspection. AutomationAnalyzer extracts state references from automations. ValidationEngine compares them and produces issues. SimulationEngine verifies action reachability. IssueReporter outputs to logs, notifications, and Repairs API.

**Tech Stack:** Python 3.12+, Home Assistant Core 2024.x+ APIs (recorder, repairs, automation internals), pytest for testing.

---

## Prerequisites

```bash
cd ~/Desktop/Projects/automut
python3 -m venv venv
source venv/bin/activate
pip install pytest pytest-asyncio homeassistant
```

---

## Task 1: Project Foundation

**Files:**
- Create: `custom_components/automation_mutation_tester/manifest.json`
- Create: `custom_components/automation_mutation_tester/const.py`
- Create: `pyproject.toml`
- Create: `.gitignore`

**Step 1: Create .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
*.egg-info/
dist/
build/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# OS
.DS_Store
```

**Step 2: Create pyproject.toml**

```toml
[project]
name = "automation-mutation-tester"
version = "1.0.0"
description = "Home Assistant integration for validating automations"
requires-python = ">=3.12"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "homeassistant>=2024.1.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 3: Create manifest.json**

```json
{
  "domain": "automation_mutation_tester",
  "name": "Automation Mutation Tester",
  "codeowners": [],
  "config_flow": true,
  "dependencies": ["automation", "recorder"],
  "after_dependencies": ["automation"],
  "documentation": "https://github.com/yourusername/automation-mutation-tester",
  "iot_class": "local_polling",
  "requirements": [],
  "version": "1.0.0"
}
```

**Step 4: Create const.py**

```python
"""Constants for Automation Mutation Tester."""

DOMAIN = "automation_mutation_tester"

# Defaults
DEFAULT_HISTORY_DAYS = 30
DEFAULT_STALENESS_THRESHOLD_DAYS = 30
DEFAULT_VALIDATE_ON_RELOAD = True
DEFAULT_DEBOUNCE_SECONDS = 5

# Config keys
CONF_HISTORY_DAYS = "history_days"
CONF_STALENESS_THRESHOLD_DAYS = "staleness_threshold_days"
CONF_VALIDATE_ON_RELOAD = "validate_on_reload"
CONF_DEBOUNCE_SECONDS = "debounce_seconds"
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add project foundation (manifest, const, config)"
```

---

## Task 2: Device Class States

**Files:**
- Create: `custom_components/automation_mutation_tester/device_class_states.py`
- Create: `tests/test_device_class_states.py`

**Step 1: Write the failing test**

```python
"""Tests for device class state mappings."""

import pytest

from custom_components.automation_mutation_tester.device_class_states import (
    get_device_class_states,
    get_all_known_domains,
)


def test_binary_sensor_states():
    """Test binary_sensor returns on/off."""
    states = get_device_class_states("binary_sensor")
    assert states == {"on", "off"}


def test_person_states():
    """Test person returns home/not_home."""
    states = get_device_class_states("person")
    assert states == {"home", "not_home"}


def test_lock_states():
    """Test lock returns all valid states."""
    states = get_device_class_states("lock")
    expected = {"locked", "unlocked", "locking", "unlocking", "jammed", "opening", "open"}
    assert states == expected


def test_alarm_control_panel_states():
    """Test alarm_control_panel returns all valid states."""
    states = get_device_class_states("alarm_control_panel")
    expected = {
        "disarmed", "armed_home", "armed_away", "armed_night", "armed_vacation",
        "armed_custom_bypass", "pending", "arming", "disarming", "triggered"
    }
    assert states == expected


def test_unknown_domain_returns_none():
    """Test unknown domain returns None."""
    states = get_device_class_states("unknown_domain")
    assert states is None


def test_get_all_known_domains():
    """Test we can list all known domains."""
    domains = get_all_known_domains()
    assert "binary_sensor" in domains
    assert "lock" in domains
    assert "person" in domains
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_device_class_states.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
"""Device class state mappings for known Home Assistant domains."""

from __future__ import annotations

# Verified against Home Assistant 2024.x documentation
DEVICE_CLASS_STATES: dict[str, set[str]] = {
    "binary_sensor": {"on", "off"},
    "person": {"home", "not_home"},
    "device_tracker": {"home", "not_home"},
    "lock": {"locked", "unlocked", "locking", "unlocking", "jammed", "opening", "open"},
    "cover": {"open", "closed", "opening", "closing"},
    "alarm_control_panel": {
        "disarmed", "armed_home", "armed_away", "armed_night", "armed_vacation",
        "armed_custom_bypass", "pending", "arming", "disarming", "triggered"
    },
    "vacuum": {"cleaning", "docked", "idle", "paused", "returning", "error"},
    "media_player": {"off", "on", "idle", "playing", "paused", "standby", "buffering"},
    "switch": {"on", "off"},
    "light": {"on", "off"},
    "fan": {"on", "off"},
    "input_boolean": {"on", "off"},
    "script": {"on", "off"},
    "automation": {"on", "off"},
}


def get_device_class_states(domain: str) -> set[str] | None:
    """Get known valid states for a domain.

    Args:
        domain: The entity domain (e.g., 'binary_sensor', 'lock')

    Returns:
        Set of valid states, or None if domain is unknown
    """
    return DEVICE_CLASS_STATES.get(domain)


def get_all_known_domains() -> set[str]:
    """Get all domains with known state mappings.

    Returns:
        Set of domain names
    """
    return set(DEVICE_CLASS_STATES.keys())
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_device_class_states.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add device class state mappings"
```

---

## Task 3: Data Models

**Files:**
- Create: `custom_components/automation_mutation_tester/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

```python
"""Tests for data models."""

import pytest
from datetime import datetime

from custom_components.automation_mutation_tester.models import (
    StateReference,
    ValidationIssue,
    OutcomeReport,
    Severity,
    Verdict,
)


def test_state_reference_creation():
    """Test StateReference dataclass."""
    ref = StateReference(
        automation_id="automation.welcome_home",
        automation_name="Welcome Home",
        entity_id="person.matt",
        expected_state="home",
        expected_attribute=None,
        location="trigger[0].to",
        source_line=10,
    )
    assert ref.automation_id == "automation.welcome_home"
    assert ref.expected_state == "home"
    assert ref.expected_attribute is None


def test_validation_issue_creation():
    """Test ValidationIssue dataclass."""
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0]",
        message="Invalid state",
        suggestion="not_home",
        valid_states=["home", "not_home"],
    )
    assert issue.severity == Severity.ERROR
    assert issue.suggestion == "not_home"


def test_outcome_report_creation():
    """Test OutcomeReport dataclass."""
    report = OutcomeReport(
        automation_id="automation.test",
        automation_name="Test",
        triggers_valid=True,
        conditions_reachable=True,
        outcomes=["action: light.turn_on"],
        unreachable_paths=[],
        verdict=Verdict.ALL_REACHABLE,
    )
    assert report.verdict == Verdict.ALL_REACHABLE


def test_severity_ordering():
    """Test severity levels."""
    assert Severity.ERROR.value > Severity.WARNING.value
    assert Severity.WARNING.value > Severity.INFO.value
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_models.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
"""Data models for Automation Mutation Tester."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, auto
from typing import Literal


class Severity(IntEnum):
    """Issue severity levels."""

    INFO = 1
    WARNING = 2
    ERROR = 3


class Verdict(IntEnum):
    """Outcome verification verdicts."""

    ALL_REACHABLE = auto()
    PARTIALLY_REACHABLE = auto()
    UNREACHABLE = auto()


@dataclass
class StateReference:
    """A reference to an entity state found in an automation."""

    automation_id: str
    automation_name: str
    entity_id: str
    expected_state: str | None
    expected_attribute: str | None
    location: str  # e.g., "trigger[0].to", "condition[1].state"
    source_line: int | None = None

    # Historical analysis results (populated by analyzer)
    historical_match: bool = True
    last_seen: datetime | None = None
    transition_from: str | None = None
    transition_valid: bool = True


@dataclass
class ValidationIssue:
    """An issue found during validation."""

    severity: Severity
    automation_id: str
    automation_name: str
    entity_id: str
    location: str
    message: str
    suggestion: str | None = None
    valid_states: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((self.automation_id, self.entity_id, self.location, self.message))


@dataclass
class OutcomeReport:
    """Report on whether automation outcomes are reachable."""

    automation_id: str
    automation_name: str
    triggers_valid: bool
    conditions_reachable: bool
    outcomes: list[str]
    unreachable_paths: list[str]
    verdict: Verdict
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_models.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add data models (StateReference, ValidationIssue, OutcomeReport)"
```

---

## Task 4: StateKnowledgeBase - Core Structure

**Files:**
- Create: `custom_components/automation_mutation_tester/knowledge_base.py`
- Create: `tests/test_knowledge_base.py`

**Step 1: Write the failing test**

```python
"""Tests for StateKnowledgeBase."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.automation_mutation_tester.knowledge_base import (
    StateKnowledgeBase,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    return hass


@pytest.mark.asyncio
async def test_knowledge_base_initialization(mock_hass):
    """Test knowledge base can be created."""
    kb = StateKnowledgeBase(mock_hass)
    assert kb is not None
    assert kb.hass == mock_hass


@pytest.mark.asyncio
async def test_get_valid_states_for_known_domain(mock_hass):
    """Test getting valid states for known domain entity."""
    kb = StateKnowledgeBase(mock_hass)

    # Mock an entity
    mock_state = MagicMock()
    mock_state.entity_id = "binary_sensor.motion"
    mock_state.domain = "binary_sensor"
    mock_state.state = "on"
    mock_hass.states.get = MagicMock(return_value=mock_state)

    states = kb.get_valid_states("binary_sensor.motion")
    assert "on" in states
    assert "off" in states


@pytest.mark.asyncio
async def test_get_valid_states_unknown_entity(mock_hass):
    """Test getting valid states for unknown entity."""
    kb = StateKnowledgeBase(mock_hass)
    mock_hass.states.get = MagicMock(return_value=None)

    states = kb.get_valid_states("sensor.nonexistent")
    assert states is None


@pytest.mark.asyncio
async def test_is_valid_state(mock_hass):
    """Test checking if a state is valid."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "binary_sensor.motion"
    mock_state.domain = "binary_sensor"
    mock_hass.states.get = MagicMock(return_value=mock_state)

    assert kb.is_valid_state("binary_sensor.motion", "on") is True
    assert kb.is_valid_state("binary_sensor.motion", "off") is True
    assert kb.is_valid_state("binary_sensor.motion", "maybe") is False


@pytest.mark.asyncio
async def test_entity_exists(mock_hass):
    """Test checking if entity exists."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_hass.states.get = MagicMock(return_value=mock_state)

    assert kb.entity_exists("binary_sensor.motion") is True

    mock_hass.states.get = MagicMock(return_value=None)
    assert kb.entity_exists("binary_sensor.missing") is False
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_knowledge_base.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
"""StateKnowledgeBase - builds and maintains valid states for entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .device_class_states import get_device_class_states

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class StateKnowledgeBase:
    """Builds and maintains the valid states map for all entities.

    Data sources (in priority order):
    1. Device class defaults (hardcoded mappings)
    2. Schema introspection (entity capabilities)
    3. Recorder history (observed states)
    """

    def __init__(self, hass: HomeAssistant, history_days: int = 30) -> None:
        """Initialize the knowledge base.

        Args:
            hass: Home Assistant instance
            history_days: Number of days of history to query
        """
        self.hass = hass
        self.history_days = history_days
        self._cache: dict[str, set[str]] = {}

    def entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists.

        Args:
            entity_id: The entity ID to check

        Returns:
            True if entity exists
        """
        return self.hass.states.get(entity_id) is not None

    def get_domain(self, entity_id: str) -> str:
        """Extract domain from entity ID.

        Args:
            entity_id: The entity ID (e.g., 'binary_sensor.motion')

        Returns:
            The domain (e.g., 'binary_sensor')
        """
        return entity_id.split(".")[0] if "." in entity_id else ""

    def get_valid_states(self, entity_id: str) -> set[str] | None:
        """Get valid states for an entity.

        Args:
            entity_id: The entity ID

        Returns:
            Set of valid states, or None if entity doesn't exist
        """
        # Check cache first
        if entity_id in self._cache:
            return self._cache[entity_id]

        # Check if entity exists
        state = self.hass.states.get(entity_id)
        if state is None:
            return None

        domain = self.get_domain(entity_id)

        # Start with device class defaults
        valid_states = get_device_class_states(domain)
        if valid_states is not None:
            valid_states = valid_states.copy()
        else:
            # Unknown domain - return empty set (will be populated by history)
            valid_states = set()

        # Always add unavailable/unknown as these are always valid
        valid_states.add("unavailable")
        valid_states.add("unknown")

        # Cache the result
        self._cache[entity_id] = valid_states

        return valid_states

    def is_valid_state(self, entity_id: str, state: str) -> bool:
        """Check if a state is valid for an entity.

        Args:
            entity_id: The entity ID
            state: The state to check

        Returns:
            True if state is valid, False otherwise
        """
        valid_states = self.get_valid_states(entity_id)
        if valid_states is None:
            return False
        return state.lower() in {s.lower() for s in valid_states}

    def clear_cache(self) -> None:
        """Clear the state cache."""
        self._cache.clear()
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_knowledge_base.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add StateKnowledgeBase core structure"
```

---

## Task 5: StateKnowledgeBase - Schema Introspection

**Files:**
- Modify: `custom_components/automation_mutation_tester/knowledge_base.py`
- Modify: `tests/test_knowledge_base.py`

**Step 1: Write the failing test**

Add to `tests/test_knowledge_base.py`:

```python
@pytest.mark.asyncio
async def test_schema_introspection_climate_hvac_modes(mock_hass):
    """Test extracting hvac_modes from climate entity."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "climate.living_room"
    mock_state.domain = "climate"
    mock_state.attributes = {"hvac_modes": ["off", "heat", "cool", "auto"]}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    states = kb.get_valid_states("climate.living_room")
    assert "off" in states
    assert "heat" in states
    assert "cool" in states
    assert "auto" in states


@pytest.mark.asyncio
async def test_schema_introspection_select_options(mock_hass):
    """Test extracting options from select entity."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "select.speed"
    mock_state.domain = "select"
    mock_state.attributes = {"options": ["low", "medium", "high"]}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    states = kb.get_valid_states("select.speed")
    assert "low" in states
    assert "medium" in states
    assert "high" in states


@pytest.mark.asyncio
async def test_schema_introspection_light_effect_list(mock_hass):
    """Test extracting effect_list from light entity."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "light.strip"
    mock_state.domain = "light"
    mock_state.attributes = {"effect_list": ["rainbow", "strobe", "solid"]}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    # Note: effect_list is for attributes, not states
    # Light states are still on/off
    states = kb.get_valid_states("light.strip")
    assert "on" in states
    assert "off" in states

    # But we should be able to get valid attributes
    attrs = kb.get_valid_attributes("light.strip", "effect")
    assert "rainbow" in attrs
    assert "strobe" in attrs
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_knowledge_base.py::test_schema_introspection_climate_hvac_modes -v`
Expected: FAIL (climate states not extracted)

**Step 3: Update implementation**

Add to `knowledge_base.py`:

```python
# Schema introspection attribute mappings
SCHEMA_ATTRIBUTES: dict[str, list[str]] = {
    "climate": ["hvac_modes", "preset_modes", "fan_modes", "swing_modes"],
    "fan": ["preset_modes"],
    "select": ["options"],
    "input_select": ["options"],
}

# Attribute value mappings (for attribute checking, not state checking)
ATTRIBUTE_VALUE_SOURCES: dict[str, str] = {
    "effect": "effect_list",
    "preset_mode": "preset_modes",
    "hvac_mode": "hvac_modes",
    "fan_mode": "fan_modes",
    "swing_mode": "swing_modes",
}
```

Update `get_valid_states` method:

```python
def get_valid_states(self, entity_id: str) -> set[str] | None:
    """Get valid states for an entity.

    Args:
        entity_id: The entity ID

    Returns:
        Set of valid states, or None if entity doesn't exist
    """
    # Check cache first
    if entity_id in self._cache:
        return self._cache[entity_id]

    # Check if entity exists
    state = self.hass.states.get(entity_id)
    if state is None:
        return None

    domain = self.get_domain(entity_id)

    # Start with device class defaults
    valid_states = get_device_class_states(domain)
    if valid_states is not None:
        valid_states = valid_states.copy()
    else:
        valid_states = set()

    # Schema introspection
    if domain in SCHEMA_ATTRIBUTES:
        for attr_name in SCHEMA_ATTRIBUTES[domain]:
            attr_value = state.attributes.get(attr_name)
            if attr_value and isinstance(attr_value, list):
                valid_states.update(str(v) for v in attr_value)

    # Always add unavailable/unknown
    valid_states.add("unavailable")
    valid_states.add("unknown")

    # Cache the result
    self._cache[entity_id] = valid_states

    return valid_states

def get_valid_attributes(self, entity_id: str, attribute: str) -> set[str] | None:
    """Get valid values for an entity attribute.

    Args:
        entity_id: The entity ID
        attribute: The attribute name (e.g., 'effect', 'preset_mode')

    Returns:
        Set of valid attribute values, or None if not found
    """
    state = self.hass.states.get(entity_id)
    if state is None:
        return None

    # Check if this attribute has a known source
    source_attr = ATTRIBUTE_VALUE_SOURCES.get(attribute)
    if source_attr:
        values = state.attributes.get(source_attr)
        if values and isinstance(values, list):
            return set(str(v) for v in values)

    return None
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_knowledge_base.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add schema introspection to StateKnowledgeBase"
```

---

## Task 6: StateKnowledgeBase - Recorder History

**Files:**
- Modify: `custom_components/automation_mutation_tester/knowledge_base.py`
- Modify: `tests/test_knowledge_base.py`

**Step 1: Write the failing test**

Add to `tests/test_knowledge_base.py`:

```python
@pytest.mark.asyncio
async def test_load_history_adds_observed_states(mock_hass):
    """Test that recorder history adds observed states."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "sensor.custom"
    mock_state.domain = "sensor"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    # Simulate history data
    history_states = [
        MagicMock(state="active"),
        MagicMock(state="idle"),
        MagicMock(state="active"),
        MagicMock(state="error"),
    ]

    with patch(
        "custom_components.automation_mutation_tester.knowledge_base.get_significant_states",
        new_callable=AsyncMock,
        return_value={"sensor.custom": history_states},
    ):
        await kb.async_load_history(["sensor.custom"])

    states = kb.get_valid_states("sensor.custom")
    assert "active" in states
    assert "idle" in states
    assert "error" in states


@pytest.mark.asyncio
async def test_history_excludes_unavailable_unknown(mock_hass):
    """Test that history loading excludes unavailable/unknown from observed."""
    kb = StateKnowledgeBase(mock_hass)

    mock_state = MagicMock()
    mock_state.entity_id = "sensor.custom"
    mock_state.domain = "sensor"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    history_states = [
        MagicMock(state="active"),
        MagicMock(state="unavailable"),
        MagicMock(state="unknown"),
    ]

    with patch(
        "custom_components.automation_mutation_tester.knowledge_base.get_significant_states",
        new_callable=AsyncMock,
        return_value={"sensor.custom": history_states},
    ):
        await kb.async_load_history(["sensor.custom"])

    # unavailable/unknown should be in valid states but not from history
    states = kb.get_valid_states("sensor.custom")
    assert "active" in states
    # These are always added but shouldn't count as "observed"
    observed = kb.get_observed_states("sensor.custom")
    assert "unavailable" not in observed
    assert "unknown" not in observed
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_knowledge_base.py::test_load_history_adds_observed_states -v`
Expected: FAIL (async_load_history not implemented)

**Step 3: Update implementation**

Add imports and method to `knowledge_base.py`:

```python
from datetime import datetime, timedelta

# Add mock for testing - will be replaced with actual import in HA
try:
    from homeassistant.components.recorder import get_significant_states
except ImportError:
    async def get_significant_states(*args, **kwargs):
        return {}
```

Add methods:

```python
async def async_load_history(self, entity_ids: list[str] | None = None) -> None:
    """Load state history from recorder.

    Args:
        entity_ids: Optional list of entity IDs to load. If None, loads all.
    """
    if entity_ids is None:
        # Get all entity IDs
        entity_ids = [s.entity_id for s in self.hass.states.async_all()]

    if not entity_ids:
        return

    start_time = datetime.now() - timedelta(days=self.history_days)
    end_time = datetime.now()

    try:
        history = await get_significant_states(
            self.hass,
            start_time,
            end_time,
            entity_ids,
            significant_changes_only=True,
        )
    except Exception as err:
        _LOGGER.warning("Failed to load recorder history: %s", err)
        return

    for entity_id, states in history.items():
        if entity_id not in self._observed_states:
            self._observed_states[entity_id] = set()

        for state in states:
            state_value = state.state
            # Exclude unavailable/unknown from observed states
            if state_value not in ("unavailable", "unknown"):
                self._observed_states[entity_id].add(state_value)

                # Also add to valid states cache
                if entity_id in self._cache:
                    self._cache[entity_id].add(state_value)

def get_observed_states(self, entity_id: str) -> set[str]:
    """Get states that have been observed in history.

    Args:
        entity_id: The entity ID

    Returns:
        Set of observed states (excludes unavailable/unknown)
    """
    return self._observed_states.get(entity_id, set())
```

Update `__init__`:

```python
def __init__(self, hass: HomeAssistant, history_days: int = 30) -> None:
    """Initialize the knowledge base."""
    self.hass = hass
    self.history_days = history_days
    self._cache: dict[str, set[str]] = {}
    self._observed_states: dict[str, set[str]] = {}
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_knowledge_base.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add recorder history loading to StateKnowledgeBase"
```

---

## Task 7: AutomationAnalyzer - State Trigger Extraction

**Files:**
- Create: `custom_components/automation_mutation_tester/analyzer.py`
- Create: `tests/test_analyzer.py`

**Step 1: Write the failing test**

```python
"""Tests for AutomationAnalyzer."""

import pytest
from unittest.mock import MagicMock

from custom_components.automation_mutation_tester.analyzer import AutomationAnalyzer
from custom_components.automation_mutation_tester.models import StateReference


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()


def test_extract_state_trigger_to():
    """Test extraction of 'to' state from state trigger."""
    automation = {
        "id": "welcome_home",
        "alias": "Welcome Home",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].automation_id == "automation.welcome_home"
    assert refs[0].entity_id == "person.matt"
    assert refs[0].expected_state == "home"
    assert refs[0].location == "trigger[0].to"


def test_extract_state_trigger_from_and_to():
    """Test extraction of 'from' and 'to' states."""
    automation = {
        "id": "left_home",
        "alias": "Left Home",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "from": "home",
                "to": "not_home",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    from_ref = next(r for r in refs if "from" in r.location)
    to_ref = next(r for r in refs if ".to" in r.location)

    assert from_ref.expected_state == "home"
    assert to_ref.expected_state == "not_home"


def test_extract_multiple_entity_ids():
    """Test extraction with multiple entity IDs in trigger."""
    automation = {
        "id": "motion_detected",
        "alias": "Motion Detected",
        "trigger": [
            {
                "platform": "state",
                "entity_id": ["binary_sensor.motion_1", "binary_sensor.motion_2"],
                "to": "on",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    entity_ids = {r.entity_id for r in refs}
    assert "binary_sensor.motion_1" in entity_ids
    assert "binary_sensor.motion_2" in entity_ids


def test_extract_state_condition():
    """Test extraction from state condition."""
    automation = {
        "id": "check_alarm",
        "alias": "Check Alarm",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "state",
                "entity_id": "alarm_control_panel.home",
                "state": "armed_away",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "alarm_control_panel.home"
    assert refs[0].expected_state == "armed_away"
    assert refs[0].location == "condition[0].state"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_analyzer.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
"""AutomationAnalyzer - extracts state references from automations."""

from __future__ import annotations

import logging
from typing import Any

from .models import StateReference

_LOGGER = logging.getLogger(__name__)


class AutomationAnalyzer:
    """Parses automation configs and extracts all state references."""

    def extract_state_references(self, automation: dict[str, Any]) -> list[StateReference]:
        """Extract all state references from an automation.

        Args:
            automation: The automation configuration dict

        Returns:
            List of StateReference objects
        """
        refs: list[StateReference] = []

        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = automation.get("alias", automation_id)

        # Extract from triggers
        triggers = automation.get("trigger", [])
        if not isinstance(triggers, list):
            triggers = [triggers]

        for idx, trigger in enumerate(triggers):
            refs.extend(
                self._extract_from_trigger(trigger, idx, automation_id, automation_name)
            )

        # Extract from conditions
        conditions = automation.get("condition", [])
        if not isinstance(conditions, list):
            conditions = [conditions]

        for idx, condition in enumerate(conditions):
            refs.extend(
                self._extract_from_condition(condition, idx, automation_id, automation_name)
            )

        return refs

    def _extract_from_trigger(
        self,
        trigger: dict[str, Any],
        index: int,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract state references from a trigger.

        Args:
            trigger: The trigger configuration
            index: Trigger index in the list
            automation_id: The automation ID
            automation_name: The automation name

        Returns:
            List of StateReference objects
        """
        refs: list[StateReference] = []
        platform = trigger.get("platform", "")

        if platform == "state":
            entity_ids = trigger.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            to_state = trigger.get("to")
            from_state = trigger.get("from")

            for entity_id in entity_ids:
                if to_state is not None:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=str(to_state),
                            expected_attribute=None,
                            location=f"trigger[{index}].to",
                            transition_from=str(from_state) if from_state else None,
                        )
                    )
                if from_state is not None:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=entity_id,
                            expected_state=str(from_state),
                            expected_attribute=None,
                            location=f"trigger[{index}].from",
                        )
                    )

        elif platform == "numeric_state":
            entity_ids = trigger.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            attribute = trigger.get("attribute")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=attribute,
                        location=f"trigger[{index}]",
                    )
                )

        return refs

    def _extract_from_condition(
        self,
        condition: dict[str, Any],
        index: int,
        automation_id: str,
        automation_name: str,
    ) -> list[StateReference]:
        """Extract state references from a condition.

        Args:
            condition: The condition configuration
            index: Condition index in the list
            automation_id: The automation ID
            automation_name: The automation name

        Returns:
            List of StateReference objects
        """
        refs: list[StateReference] = []
        cond_type = condition.get("condition", "")

        if cond_type == "state":
            entity_ids = condition.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            state = condition.get("state")

            for entity_id in entity_ids:
                if state is not None:
                    # State can be a list of valid states
                    states = state if isinstance(state, list) else [state]
                    for s in states:
                        refs.append(
                            StateReference(
                                automation_id=automation_id,
                                automation_name=automation_name,
                                entity_id=entity_id,
                                expected_state=str(s),
                                expected_attribute=None,
                                location=f"condition[{index}].state",
                            )
                        )

        return refs
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_analyzer.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add AutomationAnalyzer for state/condition extraction"
```

---

## Task 8: AutomationAnalyzer - Template Parsing

**Files:**
- Modify: `custom_components/automation_mutation_tester/analyzer.py`
- Modify: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_is_state_from_template():
    """Test extraction of is_state() calls from templates."""
    automation = {
        "id": "template_test",
        "alias": "Template Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ is_state('binary_sensor.motion', 'on') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "binary_sensor.motion"
    assert refs[0].expected_state == "on"


def test_extract_multiple_is_state_calls():
    """Test extraction of multiple is_state() calls."""
    automation = {
        "id": "multi_template",
        "alias": "Multi Template",
        "trigger": [{"platform": "time", "at": "08:00:00"}],
        "condition": [
            {
                "condition": "template",
                "value_template": "{{ is_state('person.matt', 'home') and is_state('sun.sun', 'below_horizon') }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    entities = {r.entity_id for r in refs}
    assert "person.matt" in entities
    assert "sun.sun" in entities


def test_extract_states_object_access():
    """Test extraction of states.domain.entity references."""
    automation = {
        "id": "states_access",
        "alias": "States Access",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ states.binary_sensor.motion.state == 'on' }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) >= 1
    assert any(r.entity_id == "binary_sensor.motion" for r in refs)


def test_extract_state_attr_from_template():
    """Test extraction of state_attr() calls."""
    automation = {
        "id": "attr_test",
        "alias": "Attr Test",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ state_attr('climate.living_room', 'current_temperature') > 25 }}",
            }
        ],
        "action": [],
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "current_temperature"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_analyzer.py::test_extract_is_state_from_template -v`
Expected: FAIL (template parsing not implemented)

**Step 3: Update implementation**

Add regex patterns and template extraction to `analyzer.py`:

```python
import re

# Regex patterns for template parsing
IS_STATE_PATTERN = re.compile(
    r"is_state\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)
STATE_ATTR_PATTERN = re.compile(
    r"state_attr\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)"
)
STATES_OBJECT_PATTERN = re.compile(
    r"states\.([a-z_]+)\.([a-z0-9_]+)(?:\.state)?"
)
```

Add template extraction method:

```python
def _extract_from_template(
    self,
    template: str,
    location: str,
    automation_id: str,
    automation_name: str,
) -> list[StateReference]:
    """Extract state references from a Jinja2 template.

    Args:
        template: The template string
        location: Location prefix for references
        automation_id: The automation ID
        automation_name: The automation name

    Returns:
        List of StateReference objects
    """
    refs: list[StateReference] = []

    # Extract is_state() calls
    for match in IS_STATE_PATTERN.finditer(template):
        entity_id, state = match.groups()
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                expected_state=state,
                expected_attribute=None,
                location=f"{location}.is_state",
            )
        )

    # Extract state_attr() calls
    for match in STATE_ATTR_PATTERN.finditer(template):
        entity_id, attribute = match.groups()
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=attribute,
                location=f"{location}.state_attr",
            )
        )

    # Extract states.domain.entity references
    for match in STATES_OBJECT_PATTERN.finditer(template):
        domain, entity_name = match.groups()
        entity_id = f"{domain}.{entity_name}"
        # Don't duplicate if already found via is_state
        if not any(r.entity_id == entity_id for r in refs):
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=None,
                    location=f"{location}.states_object",
                )
            )

    return refs
```

Update `_extract_from_trigger` to handle template triggers:

```python
elif platform == "template":
    value_template = trigger.get("value_template", "")
    refs.extend(
        self._extract_from_template(
            value_template, f"trigger[{index}]", automation_id, automation_name
        )
    )
```

Update `_extract_from_condition` to handle template conditions:

```python
elif cond_type == "template":
    value_template = condition.get("value_template", "")
    refs.extend(
        self._extract_from_template(
            value_template, f"condition[{index}]", automation_id, automation_name
        )
    )
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_analyzer.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add template parsing to AutomationAnalyzer"
```

---

## Task 9: ValidationEngine - Core Validation

**Files:**
- Create: `custom_components/automation_mutation_tester/validator.py`
- Create: `tests/test_validator.py`

**Step 1: Write the failing test**

```python
"""Tests for ValidationEngine."""

import pytest
from unittest.mock import MagicMock

from custom_components.automation_mutation_tester.validator import ValidationEngine
from custom_components.automation_mutation_tester.knowledge_base import StateKnowledgeBase
from custom_components.automation_mutation_tester.models import StateReference, Severity


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    return hass


@pytest.fixture
def knowledge_base(mock_hass):
    """Create a knowledge base with mocked data."""
    kb = StateKnowledgeBase(mock_hass)
    return kb


def test_validate_missing_entity(mock_hass, knowledge_base):
    """Test validation detects missing entity."""
    mock_hass.states.get = MagicMock(return_value=None)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="binary_sensor.nonexistent",
        expected_state="on",
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "does not exist" in issues[0].message.lower()


def test_validate_invalid_state(mock_hass, knowledge_base):
    """Test validation detects invalid state."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        expected_state="away",  # Invalid - should be "not_home"
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "away" in issues[0].message


def test_validate_case_mismatch(mock_hass, knowledge_base):
    """Test validation detects case mismatch."""
    mock_state = MagicMock()
    mock_state.entity_id = "alarm_control_panel.home"
    mock_state.domain = "alarm_control_panel"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="alarm_control_panel.home",
        expected_state="Armed_Away",  # Case mismatch
        expected_attribute=None,
        location="condition[0].state",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert "case" in issues[0].message.lower()
    assert issues[0].suggestion == "armed_away"


def test_validate_valid_state(mock_hass, knowledge_base):
    """Test validation passes for valid state."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        expected_state="home",
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_validator.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
"""ValidationEngine - compares state references against knowledge base."""

from __future__ import annotations

import logging
from difflib import get_close_matches

from .knowledge_base import StateKnowledgeBase
from .models import StateReference, ValidationIssue, Severity

_LOGGER = logging.getLogger(__name__)


class ValidationEngine:
    """Validates state references against known valid states."""

    def __init__(self, knowledge_base: StateKnowledgeBase) -> None:
        """Initialize the validation engine.

        Args:
            knowledge_base: The StateKnowledgeBase to validate against
        """
        self.knowledge_base = knowledge_base

    def validate_reference(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate a single state reference.

        Args:
            ref: The StateReference to validate

        Returns:
            List of ValidationIssue objects (empty if valid)
        """
        issues: list[ValidationIssue] = []

        # Check entity exists
        if not self.knowledge_base.entity_exists(ref.entity_id):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"Entity '{ref.entity_id}' does not exist",
                    suggestion=self._suggest_entity(ref.entity_id),
                )
            )
            return issues  # Can't validate further

        # Validate state if specified
        if ref.expected_state is not None:
            state_issues = self._validate_state(ref)
            issues.extend(state_issues)

        # Validate attribute if specified
        if ref.expected_attribute is not None:
            attr_issues = self._validate_attribute(ref)
            issues.extend(attr_issues)

        return issues

    def _validate_state(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate the expected state.

        Args:
            ref: The StateReference to validate

        Returns:
            List of ValidationIssue objects
        """
        issues: list[ValidationIssue] = []
        valid_states = self.knowledge_base.get_valid_states(ref.entity_id)

        if valid_states is None:
            return issues  # Can't validate without known states

        expected = ref.expected_state
        valid_states_list = list(valid_states)

        # Check exact match
        if expected in valid_states:
            return issues  # Valid

        # Check case-insensitive match
        lower_map = {s.lower(): s for s in valid_states}
        if expected.lower() in lower_map:
            correct_case = lower_map[expected.lower()]
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"State '{expected}' has incorrect case, should be '{correct_case}'",
                    suggestion=correct_case,
                    valid_states=valid_states_list,
                )
            )
            return issues

        # State is invalid - find suggestion
        suggestion = self._suggest_state(expected, valid_states)
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                automation_id=ref.automation_id,
                automation_name=ref.automation_name,
                entity_id=ref.entity_id,
                location=ref.location,
                message=f"State '{expected}' is not valid for {ref.entity_id}",
                suggestion=suggestion,
                valid_states=valid_states_list,
            )
        )

        return issues

    def _validate_attribute(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate the expected attribute exists.

        Args:
            ref: The StateReference to validate

        Returns:
            List of ValidationIssue objects
        """
        issues: list[ValidationIssue] = []

        state = self.knowledge_base.hass.states.get(ref.entity_id)
        if state is None:
            return issues

        if ref.expected_attribute not in state.attributes:
            available = list(state.attributes.keys())
            suggestion = self._suggest_attribute(ref.expected_attribute, available)
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"Attribute '{ref.expected_attribute}' does not exist on {ref.entity_id}",
                    suggestion=suggestion,
                    valid_states=available,
                )
            )

        return issues

    def _suggest_state(self, invalid: str, valid_states: set[str]) -> str | None:
        """Suggest a correction for an invalid state.

        Args:
            invalid: The invalid state
            valid_states: Set of valid states

        Returns:
            Suggested state or None
        """
        matches = get_close_matches(invalid.lower(), [s.lower() for s in valid_states], n=1, cutoff=0.6)
        if matches:
            # Find original case version
            lower_map = {s.lower(): s for s in valid_states}
            return lower_map.get(matches[0])
        return None

    def _suggest_entity(self, invalid: str) -> str | None:
        """Suggest a correction for an invalid entity ID.

        Args:
            invalid: The invalid entity ID

        Returns:
            Suggested entity ID or None
        """
        all_entities = [s.entity_id for s in self.knowledge_base.hass.states.async_all()]
        matches = get_close_matches(invalid, all_entities, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def _suggest_attribute(self, invalid: str, valid_attrs: list[str]) -> str | None:
        """Suggest a correction for an invalid attribute.

        Args:
            invalid: The invalid attribute
            valid_attrs: List of valid attributes

        Returns:
            Suggested attribute or None
        """
        matches = get_close_matches(invalid, valid_attrs, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def validate_all(self, refs: list[StateReference]) -> list[ValidationIssue]:
        """Validate a list of state references.

        Args:
            refs: List of StateReference objects

        Returns:
            List of all ValidationIssue objects
        """
        issues: list[ValidationIssue] = []
        for ref in refs:
            issues.extend(self.validate_reference(ref))
        return issues
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_validator.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add ValidationEngine for state validation"
```

---

## Task 10: IssueReporter

**Files:**
- Create: `custom_components/automation_mutation_tester/reporter.py`
- Create: `tests/test_reporter.py`

**Step 1: Write the failing test**

```python
"""Tests for IssueReporter."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.automation_mutation_tester.reporter import IssueReporter
from custom_components.automation_mutation_tester.models import ValidationIssue, Severity


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def reporter(mock_hass):
    """Create an IssueReporter instance."""
    return IssueReporter(mock_hass)


def test_reporter_initialization(reporter):
    """Test reporter can be initialized."""
    assert reporter is not None


@pytest.mark.asyncio
async def test_report_issues_creates_repair(mock_hass, reporter):
    """Test that reporting issues creates repair entries."""
    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="person.matt",
            location="trigger[0].to",
            message="State 'away' is not valid",
            suggestion="not_home",
            valid_states=["home", "not_home"],
        )
    ]

    with patch(
        "custom_components.automation_mutation_tester.reporter.ir.async_create_issue"
    ) as mock_create:
        await reporter.async_report_issues(issues)
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_report_issues_creates_notification(mock_hass, reporter):
    """Test that reporting issues creates a notification."""
    issues = [
        ValidationIssue(
            severity=Severity.ERROR,
            automation_id="automation.test",
            automation_name="Test",
            entity_id="person.matt",
            location="trigger[0].to",
            message="State 'away' is not valid",
            suggestion="not_home",
            valid_states=["home", "not_home"],
        )
    ]

    with patch(
        "custom_components.automation_mutation_tester.reporter.ir.async_create_issue"
    ), patch(
        "custom_components.automation_mutation_tester.reporter.async_create"
    ) as mock_notify:
        await reporter.async_report_issues(issues)
        mock_notify.assert_called_once()


@pytest.mark.asyncio
async def test_clear_resolved_issues(mock_hass, reporter):
    """Test clearing resolved issues."""
    with patch(
        "custom_components.automation_mutation_tester.reporter.ir.async_delete_issue"
    ) as mock_delete:
        reporter._active_issues = {"issue_1", "issue_2"}
        await reporter.async_clear_resolved({"issue_1"})

        # issue_2 should be cleared
        mock_delete.assert_called_once()
        assert "issue_2" in str(mock_delete.call_args)
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_reporter.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
"""IssueReporter - outputs validation issues to logs, notifications, and repairs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .const import DOMAIN
from .models import ValidationIssue, Severity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Import HA components - mock for testing
try:
    from homeassistant.helpers import issue_registry as ir
    from homeassistant.components.persistent_notification import async_create
except ImportError:
    # Mocks for testing
    class ir:
        class IssueSeverity:
            ERROR = "error"
            WARNING = "warning"

        @staticmethod
        async def async_create_issue(*args, **kwargs):
            pass

        @staticmethod
        async def async_delete_issue(*args, **kwargs):
            pass

    async def async_create(*args, **kwargs):
        pass


class IssueReporter:
    """Reports validation issues through multiple channels."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reporter.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._active_issues: set[str] = set()

    def _issue_id(self, issue: ValidationIssue) -> str:
        """Generate a unique issue ID.

        Args:
            issue: The validation issue

        Returns:
            Unique string ID
        """
        return f"{issue.automation_id}_{issue.entity_id}_{issue.location}".replace(".", "_")

    def _severity_to_repair(self, severity: Severity) -> str:
        """Convert our severity to HA repair severity.

        Args:
            severity: Our severity enum

        Returns:
            HA repair severity string
        """
        if severity == Severity.ERROR:
            return ir.IssueSeverity.ERROR
        return ir.IssueSeverity.WARNING

    async def async_report_issues(self, issues: list[ValidationIssue]) -> None:
        """Report validation issues.

        Args:
            issues: List of ValidationIssue objects
        """
        if not issues:
            _LOGGER.info("Automation validation complete: no issues found")
            return

        current_issue_ids: set[str] = set()

        for issue in issues:
            issue_id = self._issue_id(issue)
            current_issue_ids.add(issue_id)

            # Log the issue
            log_method = _LOGGER.error if issue.severity == Severity.ERROR else _LOGGER.warning
            log_method(
                "Automation '%s': %s (entity: %s, location: %s)",
                issue.automation_name,
                issue.message,
                issue.entity_id,
                issue.location,
            )

            # Create repair issue
            await ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=self._severity_to_repair(issue.severity),
                translation_key="validation_issue",
                translation_placeholders={
                    "automation": issue.automation_name,
                    "entity": issue.entity_id,
                    "message": issue.message,
                    "suggestion": issue.suggestion or "N/A",
                    "valid_states": ", ".join(issue.valid_states) if issue.valid_states else "N/A",
                },
            )

        # Create summary notification
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == Severity.WARNING)

        message = f"Found {len(issues)} issue(s): {error_count} errors, {warning_count} warnings. Check Settings → Repairs for details."

        await async_create(
            self.hass,
            message,
            title="Automation Validation",
            notification_id=f"{DOMAIN}_results",
        )

        # Clear resolved issues
        await self.async_clear_resolved(current_issue_ids)
        self._active_issues = current_issue_ids

    async def async_clear_resolved(self, current_ids: set[str]) -> None:
        """Clear issues that have been resolved.

        Args:
            current_ids: Set of current issue IDs
        """
        resolved = self._active_issues - current_ids
        for issue_id in resolved:
            await ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def async_clear_all(self) -> None:
        """Clear all issues."""
        for issue_id in self._active_issues:
            await ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._active_issues.clear()
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_reporter.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add IssueReporter for multi-channel output"
```

---

## Task 11: SimulationEngine - Outcome Verification

**Files:**
- Create: `custom_components/automation_mutation_tester/simulator.py`
- Create: `tests/test_simulator.py`

**Step 1: Write the failing test**

```python
"""Tests for SimulationEngine."""

import pytest
from unittest.mock import MagicMock

from custom_components.automation_mutation_tester.simulator import SimulationEngine
from custom_components.automation_mutation_tester.knowledge_base import StateKnowledgeBase
from custom_components.automation_mutation_tester.models import Verdict


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def knowledge_base(mock_hass):
    """Create a knowledge base."""
    return StateKnowledgeBase(mock_hass)


@pytest.fixture
def simulator(knowledge_base):
    """Create a simulator."""
    return SimulationEngine(knowledge_base)


def test_simulator_initialization(simulator):
    """Test simulator can be initialized."""
    assert simulator is not None


def test_verify_reachable_automation(simulator, mock_hass):
    """Test verification of reachable automation."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.state = "home"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    automation = {
        "id": "welcome_home",
        "alias": "Welcome Home",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [],
        "action": [
            {"service": "light.turn_on", "target": {"entity_id": "light.porch"}}
        ],
    }

    report = simulator.verify_outcomes(automation)

    assert report.verdict == Verdict.ALL_REACHABLE
    assert report.triggers_valid is True
    assert len(report.outcomes) > 0


def test_verify_unreachable_contradictory_condition(simulator, mock_hass):
    """Test detection of contradictory conditions."""
    mock_state = MagicMock()
    mock_state.entity_id = "person.matt"
    mock_state.domain = "person"
    mock_state.state = "home"
    mock_state.attributes = {}
    mock_hass.states.get = MagicMock(return_value=mock_state)

    automation = {
        "id": "contradiction",
        "alias": "Contradiction",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.matt",
                "to": "home",
            }
        ],
        "condition": [
            {"condition": "state", "entity_id": "person.matt", "state": "not_home"}
        ],
        "action": [{"service": "light.turn_on"}],
    }

    report = simulator.verify_outcomes(automation)

    assert report.verdict == Verdict.UNREACHABLE
    assert len(report.unreachable_paths) > 0


def test_verify_missing_trigger_entity(simulator, mock_hass):
    """Test detection of missing trigger entity."""
    mock_hass.states.get = MagicMock(return_value=None)

    automation = {
        "id": "missing",
        "alias": "Missing",
        "trigger": [
            {
                "platform": "state",
                "entity_id": "person.nonexistent",
                "to": "home",
            }
        ],
        "action": [],
    }

    report = simulator.verify_outcomes(automation)

    assert report.triggers_valid is False
```

**Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_simulator.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write implementation**

```python
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
        """Initialize the simulation engine.

        Args:
            knowledge_base: The StateKnowledgeBase for validation
        """
        self.knowledge_base = knowledge_base

    def verify_outcomes(self, automation: dict[str, Any]) -> OutcomeReport:
        """Verify that automation outcomes are reachable.

        Args:
            automation: The automation configuration

        Returns:
            OutcomeReport with reachability analysis
        """
        automation_id = f"automation.{automation.get('id', 'unknown')}"
        automation_name = automation.get("alias", automation_id)

        triggers_valid = self._verify_triggers(automation.get("trigger", []))
        conditions_result = self._verify_conditions(
            automation.get("trigger", []),
            automation.get("condition", []),
        )
        outcomes = self._extract_outcomes(automation.get("action", []))
        unreachable_paths: list[str] = []

        # Determine verdict
        if not triggers_valid:
            verdict = Verdict.UNREACHABLE
            unreachable_paths.append("Trigger entity does not exist")
        elif not conditions_result["reachable"]:
            verdict = Verdict.UNREACHABLE
            unreachable_paths.extend(conditions_result["reasons"])
        elif conditions_result["contradictions"]:
            verdict = Verdict.UNREACHABLE
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
        """Verify all trigger entities exist.

        Args:
            triggers: List of trigger configurations

        Returns:
            True if all trigger entities exist
        """
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
        """Verify conditions are reachable and not contradictory.

        Args:
            triggers: List of trigger configurations
            conditions: List of condition configurations

        Returns:
            Dict with reachable, contradictions, and reasons
        """
        result = {
            "reachable": True,
            "contradictions": [],
            "reasons": [],
        }

        if not isinstance(conditions, list):
            conditions = [conditions]

        # Extract trigger states
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

        # Check for contradictions with conditions
        for condition in conditions:
            if condition.get("condition") == "state":
                entity_id = condition.get("entity_id")
                cond_state = condition.get("state")

                if entity_id and cond_state and entity_id in trigger_states:
                    # Check if condition state contradicts trigger state
                    cond_states = {cond_state} if isinstance(cond_state, str) else set(cond_state)
                    trigger_state_set = trigger_states[entity_id]

                    if not trigger_state_set.intersection(cond_states):
                        result["contradictions"].append(
                            f"Trigger sets {entity_id} to {trigger_state_set}, but condition requires {cond_states}"
                        )
                        result["reachable"] = False

        return result

    def _extract_outcomes(self, actions: list[dict[str, Any]]) -> list[str]:
        """Extract outcome descriptions from actions.

        Args:
            actions: List of action configurations

        Returns:
            List of outcome descriptions
        """
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
```

**Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Projects/automut && python -m pytest tests/test_simulator.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add SimulationEngine for outcome verification"
```

---

## Task 12: Integration Entry Point

**Files:**
- Create: `custom_components/automation_mutation_tester/__init__.py`
- Create: `custom_components/automation_mutation_tester/config_flow.py`
- Create: `custom_components/automation_mutation_tester/services.yaml`
- Create: `custom_components/automation_mutation_tester/strings.json`

**Step 1: Create config_flow.py**

```python
"""Config flow for Automation Mutation Tester."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_HISTORY_DAYS,
    CONF_STALENESS_THRESHOLD_DAYS,
    CONF_VALIDATE_ON_RELOAD,
    CONF_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_STALENESS_THRESHOLD_DAYS,
    DEFAULT_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Automation Mutation Tester."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Automation Mutation Tester",
                data={},
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_HISTORY_DAYS,
                        default=options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                    vol.Optional(
                        CONF_STALENESS_THRESHOLD_DAYS,
                        default=options.get(
                            CONF_STALENESS_THRESHOLD_DAYS, DEFAULT_STALENESS_THRESHOLD_DAYS
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                    vol.Optional(
                        CONF_VALIDATE_ON_RELOAD,
                        default=options.get(
                            CONF_VALIDATE_ON_RELOAD, DEFAULT_VALIDATE_ON_RELOAD
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_DEBOUNCE_SECONDS,
                        default=options.get(
                            CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                }
            ),
        )
```

**Step 2: Create services.yaml**

```yaml
validate:
  name: Validate Automations
  description: Run validation on all automations or a specific one.
  fields:
    automation_id:
      name: Automation ID
      description: Optional automation ID to validate. If not specified, validates all.
      required: false
      example: automation.welcome_home
      selector:
        entity:
          domain: automation

validate_automation:
  name: Validate Specific Automation
  description: Run validation on a specific automation.
  fields:
    automation_id:
      name: Automation ID
      description: The automation ID to validate.
      required: true
      example: automation.welcome_home
      selector:
        entity:
          domain: automation

simulate:
  name: Simulate Outcomes
  description: Run outcome verification on automations.
  fields:
    automation_id:
      name: Automation ID
      description: Optional automation ID to simulate. If not specified, simulates all.
      required: false
      example: automation.welcome_home
      selector:
        entity:
          domain: automation

refresh_knowledge_base:
  name: Refresh Knowledge Base
  description: Rebuild the state knowledge base from recorder and schema.
```

**Step 3: Create strings.json**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Automation Mutation Tester",
        "description": "Set up automation validation to detect state-related issues."
      }
    },
    "abort": {
      "single_instance_allowed": "Only a single instance is allowed."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Options",
        "data": {
          "history_days": "History lookback (days)",
          "staleness_threshold_days": "Staleness warning threshold (days)",
          "validate_on_reload": "Validate on automation reload",
          "debounce_seconds": "Debounce delay (seconds)"
        }
      }
    }
  },
  "issues": {
    "validation_issue": {
      "title": "Automation Validation Issue: {automation}",
      "description": "**Entity:** {entity}\n\n**Issue:** {message}\n\n**Suggestion:** {suggestion}\n\n**Valid states:** {valid_states}"
    }
  }
}
```

**Step 4: Create __init__.py**

```python
"""Automation Mutation Tester integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    CONF_HISTORY_DAYS,
    CONF_VALIDATE_ON_RELOAD,
    CONF_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
)
from .knowledge_base import StateKnowledgeBase
from .analyzer import AutomationAnalyzer
from .validator import ValidationEngine
from .simulator import SimulationEngine
from .reporter import IssueReporter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Automation Mutation Tester component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Automation Mutation Tester from a config entry."""
    options = entry.options
    history_days = options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
    validate_on_reload = options.get(CONF_VALIDATE_ON_RELOAD, DEFAULT_VALIDATE_ON_RELOAD)
    debounce_seconds = options.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)

    # Initialize components
    knowledge_base = StateKnowledgeBase(hass, history_days)
    analyzer = AutomationAnalyzer()
    validator = ValidationEngine(knowledge_base)
    simulator = SimulationEngine(knowledge_base)
    reporter = IssueReporter(hass)

    # Store in hass.data
    hass.data[DOMAIN] = {
        "knowledge_base": knowledge_base,
        "analyzer": analyzer,
        "validator": validator,
        "simulator": simulator,
        "reporter": reporter,
        "entry": entry,
        "debounce_task": None,
    }

    # Set up event listener for automation reload
    if validate_on_reload:
        _setup_reload_listener(hass, debounce_seconds)

    # Register services
    await _async_setup_services(hass)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Load history after HA is started
    async def _async_load_history(_: Event) -> None:
        await knowledge_base.async_load_history()
        _LOGGER.info("State knowledge base loaded")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_load_history)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data.pop(DOMAIN, None)

    return unload_ok


def _setup_reload_listener(hass: HomeAssistant, debounce_seconds: int) -> None:
    """Set up listener for automation reload events."""

    @callback
    def _handle_automation_reload(_: Event) -> None:
        """Handle automation reload with debouncing."""
        data = hass.data.get(DOMAIN, {})

        # Cancel existing debounce task
        if data.get("debounce_task"):
            data["debounce_task"].cancel()

        async def _debounced_validate() -> None:
            await asyncio.sleep(debounce_seconds)
            await async_validate_all(hass)

        data["debounce_task"] = hass.async_create_task(_debounced_validate())

    hass.bus.async_listen("automation_reloaded", _handle_automation_reload)


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    async def handle_validate(call: Any) -> None:
        """Handle validate service call."""
        automation_id = call.data.get("automation_id")
        if automation_id:
            await async_validate_automation(hass, automation_id)
        else:
            await async_validate_all(hass)

    async def handle_simulate(call: Any) -> None:
        """Handle simulate service call."""
        automation_id = call.data.get("automation_id")
        if automation_id:
            await async_simulate_automation(hass, automation_id)
        else:
            await async_simulate_all(hass)

    async def handle_refresh(call: Any) -> None:
        """Handle refresh knowledge base service call."""
        data = hass.data.get(DOMAIN, {})
        kb = data.get("knowledge_base")
        if kb:
            kb.clear_cache()
            await kb.async_load_history()
            _LOGGER.info("Knowledge base refreshed")

    hass.services.async_register(DOMAIN, "validate", handle_validate)
    hass.services.async_register(DOMAIN, "validate_automation", handle_validate)
    hass.services.async_register(DOMAIN, "simulate", handle_simulate)
    hass.services.async_register(DOMAIN, "refresh_knowledge_base", handle_refresh)


async def async_validate_all(hass: HomeAssistant) -> list:
    """Validate all automations."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    reporter = data.get("reporter")

    if not all([analyzer, validator, reporter]):
        return []

    # Get all automations
    automations = hass.data.get("automation", {}).get("config", [])
    if not automations:
        _LOGGER.debug("No automations found to validate")
        return []

    all_issues = []
    for automation in automations:
        refs = analyzer.extract_state_references(automation)
        issues = validator.validate_all(refs)
        all_issues.extend(issues)

    await reporter.async_report_issues(all_issues)
    return all_issues


async def async_validate_automation(hass: HomeAssistant, automation_id: str) -> list:
    """Validate a specific automation."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    reporter = data.get("reporter")

    if not all([analyzer, validator, reporter]):
        return []

    # Find the automation
    automations = hass.data.get("automation", {}).get("config", [])
    automation = next(
        (a for a in automations if f"automation.{a.get('id')}" == automation_id),
        None,
    )

    if not automation:
        _LOGGER.warning("Automation %s not found", automation_id)
        return []

    refs = analyzer.extract_state_references(automation)
    issues = validator.validate_all(refs)
    await reporter.async_report_issues(issues)
    return issues


async def async_simulate_all(hass: HomeAssistant) -> list:
    """Simulate all automations."""
    data = hass.data.get(DOMAIN, {})
    simulator = data.get("simulator")

    if not simulator:
        return []

    automations = hass.data.get("automation", {}).get("config", [])
    reports = []
    for automation in automations:
        report = simulator.verify_outcomes(automation)
        reports.append(report)

    return reports


async def async_simulate_automation(hass: HomeAssistant, automation_id: str) -> Any:
    """Simulate a specific automation."""
    data = hass.data.get(DOMAIN, {})
    simulator = data.get("simulator")

    if not simulator:
        return None

    automations = hass.data.get("automation", {}).get("config", [])
    automation = next(
        (a for a in automations if f"automation.{a.get('id')}" == automation_id),
        None,
    )

    if not automation:
        _LOGGER.warning("Automation %s not found", automation_id)
        return None

    return simulator.verify_outcomes(automation)
```

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add integration entry point, config flow, and services"
```

---

## Task 13: Sensor Entities

**Files:**
- Create: `custom_components/automation_mutation_tester/sensor.py`
- Create: `custom_components/automation_mutation_tester/binary_sensor.py`

**Step 1: Create sensor.py**

```python
"""Sensor platform for Automation Mutation Tester."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    async_add_entities([ValidationIssuesSensor(hass, entry)])


class ValidationIssuesSensor(SensorEntity):
    """Sensor showing count of validation issues."""

    _attr_has_entity_name = True
    _attr_name = "Automation Validation Issues"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_issues_count"
        self._attr_native_value = 0

    @property
    def native_value(self) -> int:
        """Return the issue count."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            return len(reporter._active_issues)
        return 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            return {"issue_ids": list(reporter._active_issues)}
        return {}
```

**Step 2: Create binary_sensor.py**

```python
"""Binary sensor platform for Automation Mutation Tester."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    async_add_entities([ValidationOkSensor(hass, entry)])


class ValidationOkSensor(BinarySensorEntity):
    """Binary sensor indicating if validation passed."""

    _attr_has_entity_name = True
    _attr_name = "Automation Validation OK"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_validation_ok"

    @property
    def is_on(self) -> bool:
        """Return True if there are problems (issues > 0)."""
        data = self.hass.data.get(DOMAIN, {})
        reporter = data.get("reporter")
        if reporter:
            return len(reporter._active_issues) > 0
        return False
```

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add sensor and binary_sensor entities"
```

---

## Task 14: Translations

**Files:**
- Create: `custom_components/automation_mutation_tester/translations/en.json`

**Step 1: Create en.json**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Automation Mutation Tester",
        "description": "Set up automation validation to detect state-related issues before they cause failures."
      }
    },
    "abort": {
      "single_instance_allowed": "Only a single instance of Automation Mutation Tester is allowed."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Automation Mutation Tester Options",
        "data": {
          "history_days": "History lookback period (days)",
          "staleness_threshold_days": "Staleness warning threshold (days)",
          "validate_on_reload": "Automatically validate when automations are reloaded",
          "debounce_seconds": "Debounce delay before validation (seconds)"
        },
        "data_description": {
          "history_days": "Number of days of state history to analyze",
          "staleness_threshold_days": "Warn if a referenced state hasn't occurred in this many days",
          "validate_on_reload": "Run validation automatically whenever automations are reloaded",
          "debounce_seconds": "Wait this many seconds after reload before validating (prevents multiple rapid validations)"
        }
      }
    }
  },
  "issues": {
    "validation_issue": {
      "title": "Automation Issue: {automation}",
      "description": "**Entity:** `{entity}`\n\n**Problem:** {message}\n\n**Suggested fix:** {suggestion}\n\n**Valid states:** {valid_states}"
    }
  },
  "entity": {
    "sensor": {
      "automation_validation_issues": {
        "name": "Automation Validation Issues"
      }
    },
    "binary_sensor": {
      "automation_validation_ok": {
        "name": "Automation Validation OK"
      }
    }
  },
  "services": {
    "validate": {
      "name": "Validate Automations",
      "description": "Run validation on all automations or a specific one.",
      "fields": {
        "automation_id": {
          "name": "Automation ID",
          "description": "Optional: specific automation to validate. Leave empty to validate all."
        }
      }
    },
    "simulate": {
      "name": "Verify Outcomes",
      "description": "Verify that automation actions are reachable.",
      "fields": {
        "automation_id": {
          "name": "Automation ID",
          "description": "Optional: specific automation to verify. Leave empty to verify all."
        }
      }
    },
    "refresh_knowledge_base": {
      "name": "Refresh Knowledge Base",
      "description": "Rebuild the state knowledge base from recorder history and entity schemas."
    }
  }
}
```

**Step 2: Commit**

```bash
git add -A
git commit -m "feat: add English translations"
```

---

## Task 15: Final Testing & Cleanup

**Step 1: Create conftest.py for tests**

```python
"""Pytest configuration for Automation Mutation Tester tests."""

import sys
from pathlib import Path

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))
```

**Step 2: Run all tests**

```bash
cd ~/Desktop/Projects/automut
python -m pytest tests/ -v
```

Expected: All tests pass

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: add test configuration"
```

---

## Summary

This implementation plan covers:

1. **Project Foundation** - manifest, constants, config
2. **Device Class States** - hardcoded valid states
3. **Data Models** - StateReference, ValidationIssue, OutcomeReport
4. **StateKnowledgeBase** - core, schema introspection, recorder history
5. **AutomationAnalyzer** - trigger/condition extraction, template parsing
6. **ValidationEngine** - state validation, fuzzy matching
7. **IssueReporter** - logs, notifications, repairs
8. **SimulationEngine** - outcome verification
9. **Integration Entry Point** - setup, services, event listeners
10. **Sensors** - issue count, validation OK
11. **Translations** - English strings

Each task follows TDD with:
- Write failing test
- Run to verify failure
- Implement minimal code
- Run to verify pass
- Commit
