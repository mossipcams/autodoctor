# State Validation Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve state validation to work for any Home Assistant installation by extracting states from HA source and learning from user dismissals.

**Architecture:** Two-part solution: (1) Build-time script extracts valid states from HA core enums into device_class_states.py, (2) Runtime learning stores integration-specific states when users dismiss false positives.

**Tech Stack:** Python 3.11+, Home Assistant helpers (entity_registry, Store), pytest

---

## Task 1: Learned States Store

Create a new store class for persisting learned states, following the existing SuppressionStore pattern.

**Files:**
- Create: `custom_components/autodoctor/learned_states_store.py`
- Test: `tests/test_learned_states_store.py`

**Step 1: Write the test file**

```python
# tests/test_learned_states_store.py
"""Tests for LearnedStatesStore."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant


async def test_learned_states_store_initialization(hass: HomeAssistant):
    """Test store can be created."""
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    store = LearnedStatesStore(hass)
    assert store is not None


async def test_learn_state_adds_to_store(hass: HomeAssistant):
    """Test learning a state adds it to the store."""
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    store = LearnedStatesStore(hass)

    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    states = store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states


async def test_get_learned_states_empty_for_unknown(hass: HomeAssistant):
    """Test getting states for unknown domain/integration returns empty set."""
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    store = LearnedStatesStore(hass)

    states = store.get_learned_states("vacuum", "unknown_brand")
    assert states == set()


async def test_learn_state_deduplicates(hass: HomeAssistant):
    """Test learning same state twice doesn't duplicate."""
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    store = LearnedStatesStore(hass)

    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    states = store.get_learned_states("vacuum", "roborock")
    assert list(states).count("segment_cleaning") == 1


async def test_learned_states_persist_across_load(hass: HomeAssistant):
    """Test learned states persist after save/load cycle."""
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    store1 = LearnedStatesStore(hass)
    await store1.async_learn_state("vacuum", "roborock", "segment_cleaning")

    # Create new store and load
    store2 = LearnedStatesStore(hass)
    await store2.async_load()

    states = store2.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states
```

**Step 2: Run tests to verify they fail**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_learned_states_store.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'custom_components.autodoctor.learned_states_store'"

**Step 3: Write minimal implementation**

```python
# custom_components/autodoctor/learned_states_store.py
"""Persistent storage for learned states from user dismissals."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

STORAGE_KEY = "autodoctor.learned_states"
STORAGE_VERSION = 1


class LearnedStatesStore:
    """Persistent storage for learned states.

    Stores states that users have marked as valid by dismissing
    false positive validation issues. States are stored per
    domain and integration (platform).

    Structure:
        {
            "vacuum": {
                "roborock": ["segment_cleaning", "charging_error"],
                "ecovacs": ["auto_clean"]
            }
        }
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the learned states store."""
        self._hass = hass
        self._store: Store[dict[str, dict[str, list[str]]]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
        )
        self._learned: dict[str, dict[str, list[str]]] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load learned states from storage."""
        async with self._lock:
            data = await self._store.async_load()
            if data:
                self._learned = data

    async def _async_save(self) -> None:
        """Save learned states to storage.

        Note: Caller must hold _lock when calling this method.
        """
        await self._store.async_save(self._learned)

    def get_learned_states(self, domain: str, integration: str) -> set[str]:
        """Get learned states for a domain/integration combination.

        Args:
            domain: Entity domain (e.g., 'vacuum')
            integration: Integration/platform name (e.g., 'roborock')

        Returns:
            Set of learned state values
        """
        if domain not in self._learned:
            return set()
        return set(self._learned[domain].get(integration, []))

    async def async_learn_state(
        self, domain: str, integration: str, state: str
    ) -> None:
        """Learn a state as valid for a domain/integration.

        Args:
            domain: Entity domain (e.g., 'vacuum')
            integration: Integration/platform name (e.g., 'roborock')
            state: The state value to learn
        """
        async with self._lock:
            if domain not in self._learned:
                self._learned[domain] = {}

            if integration not in self._learned[domain]:
                self._learned[domain][integration] = []

            if state not in self._learned[domain][integration]:
                self._learned[domain][integration].append(state)
                await self._async_save()
```

**Step 4: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_learned_states_store.py -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/learned_states_store.py tests/test_learned_states_store.py
git commit -m "feat: add LearnedStatesStore for persisting user-learned states"
```

---

## Task 2: Integration Lookup Helper

Add a helper method to get the integration/platform that owns an entity.

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py`
- Test: `tests/test_knowledge_base.py`

**Step 1: Write the test**

Add to `tests/test_knowledge_base.py`:

```python
async def test_get_integration_from_entity_registry(hass: HomeAssistant):
    """Test getting integration name from entity registry."""
    from unittest.mock import MagicMock, patch
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    # Mock entity registry
    mock_entry = MagicMock()
    mock_entry.platform = "roborock"

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry
    ):
        integration = kb.get_integration("vacuum.roborock_s7")

    assert integration == "roborock"


async def test_get_integration_returns_none_for_unknown(hass: HomeAssistant):
    """Test getting integration returns None for unknown entity."""
    from unittest.mock import MagicMock, patch
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = None

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry
    ):
        integration = kb.get_integration("vacuum.unknown")

    assert integration is None
```

**Step 2: Run tests to verify they fail**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_knowledge_base.py::test_get_integration_from_entity_registry tests/test_knowledge_base.py::test_get_integration_returns_none_for_unknown -v`

Expected: FAIL with "AttributeError: 'StateKnowledgeBase' object has no attribute 'get_integration'"

**Step 3: Write minimal implementation**

Add import at top of `knowledge_base.py`:

```python
from homeassistant.helpers import entity_registry as er
```

Add method to `StateKnowledgeBase` class:

```python
def get_integration(self, entity_id: str) -> str | None:
    """Get the integration/platform that owns an entity.

    Args:
        entity_id: The entity ID to look up

    Returns:
        Integration name (e.g., 'roborock'), or None if not found
    """
    entity_registry = er.async_get(self.hass)
    entry = entity_registry.async_get(entity_id)
    return entry.platform if entry else None
```

**Step 4: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_knowledge_base.py::test_get_integration_from_entity_registry tests/test_knowledge_base.py::test_get_integration_returns_none_for_unknown -v`

Expected: Both tests PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: add get_integration helper to knowledge base"
```

---

## Task 3: Integrate Learned States into Knowledge Base

Wire up the LearnedStatesStore to the knowledge base so learned states are considered during validation.

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py`
- Test: `tests/test_knowledge_base.py`

**Step 1: Write the test**

Add to `tests/test_knowledge_base.py`:

```python
async def test_get_valid_states_includes_learned_states(hass: HomeAssistant):
    """Test that learned states are included in valid states."""
    from unittest.mock import MagicMock, patch, AsyncMock
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore

    # Set up entity
    hass.states.async_set("vacuum.roborock_s7", "cleaning")
    await hass.async_block_till_done()

    # Create store with learned state
    store = LearnedStatesStore(hass)
    await store.async_learn_state("vacuum", "roborock", "segment_cleaning")

    # Create knowledge base with store
    kb = StateKnowledgeBase(hass, learned_states_store=store)

    # Mock entity registry
    mock_entry = MagicMock()
    mock_entry.platform = "roborock"
    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.autodoctor.knowledge_base.er.async_get",
        return_value=mock_registry
    ):
        states = kb.get_valid_states("vacuum.roborock_s7")

    # Should include learned state
    assert "segment_cleaning" in states
    # Should still include device class defaults
    assert "cleaning" in states
    assert "docked" in states
```

**Step 2: Run tests to verify they fail**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_knowledge_base.py::test_get_valid_states_includes_learned_states -v`

Expected: FAIL with "TypeError: StateKnowledgeBase.__init__() got an unexpected keyword argument 'learned_states_store'"

**Step 3: Write minimal implementation**

Modify `StateKnowledgeBase.__init__()`:

```python
def __init__(
    self,
    hass: HomeAssistant,
    history_days: int = 30,
    learned_states_store: LearnedStatesStore | None = None,
) -> None:
    """Initialize the knowledge base.

    Args:
        hass: Home Assistant instance
        history_days: Number of days of history to query
        learned_states_store: Optional store for user-learned states
    """
    self.hass = hass
    self.history_days = history_days
    self._cache: dict[str, set[str]] = {}
    self._observed_states: dict[str, set[str]] = {}
    self._learned_states_store = learned_states_store
    self._lock = asyncio.Lock()
```

Add import at top:

```python
from .learned_states_store import LearnedStatesStore
```

Add helper method:

```python
def _get_learned_states(self, entity_id: str) -> set[str]:
    """Get learned states for an entity from the store.

    Args:
        entity_id: The entity ID

    Returns:
        Set of learned states, or empty set if none
    """
    if not self._learned_states_store:
        return set()

    domain = self.get_domain(entity_id)
    integration = self.get_integration(entity_id)

    if not integration:
        return set()

    return self._learned_states_store.get_learned_states(domain, integration)
```

Modify `get_valid_states()` to include learned states after device class defaults:

```python
# Start with device class defaults
device_class_defaults = get_device_class_states(domain)
if device_class_defaults is not None:
    valid_states = device_class_defaults.copy()
    _LOGGER.debug(
        "Entity %s (domain=%s): device class defaults = %s",
        entity_id, domain, device_class_defaults
    )
else:
    valid_states = set()
    _LOGGER.debug(
        "Entity %s (domain=%s): no device class defaults",
        entity_id, domain
    )

# Add learned states for this integration (NEW)
learned = self._get_learned_states(entity_id)
if learned:
    valid_states.update(learned)
    _LOGGER.debug(
        "Entity %s: added learned states = %s",
        entity_id, learned
    )
```

**Step 4: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_knowledge_base.py::test_get_valid_states_includes_learned_states -v`

Expected: PASS

**Step 5: Run all knowledge base tests to check for regressions**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_knowledge_base.py -v`

Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "feat: integrate learned states into knowledge base validation"
```

---

## Task 4: Wire Up Learning on Suppression

Modify the WebSocket suppress handler to learn states when a state validation issue is dismissed.

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py`
- Modify: `custom_components/autodoctor/__init__.py` (to wire up store)
- Test: `tests/test_websocket_api_learning.py` (new test file)

**Step 1: Write the test file**

```python
# tests/test_websocket_api_learning.py
"""Tests for WebSocket API learning on suppression."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


async def test_suppress_learns_state_for_invalid_state_issue(hass):
    """Test that suppressing an invalid state issue learns the state."""
    from custom_components.autodoctor.websocket_api import websocket_suppress
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore
    from custom_components.autodoctor.suppression_store import SuppressionStore
    from custom_components.autodoctor.const import DOMAIN

    # Set up stores
    learned_store = LearnedStatesStore(hass)
    suppression_store = SuppressionStore(hass)

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": learned_store,
    }

    # Mock entity registry
    mock_entry = MagicMock()
    mock_entry.platform = "roborock"
    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    # Mock connection
    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {
        "id": 1,
        "type": "autodoctor/suppress",
        "automation_id": "automation.test",
        "entity_id": "vacuum.roborock_s7",
        "issue_type": "invalid_state",
        "state": "segment_cleaning",
    }

    with patch(
        "custom_components.autodoctor.websocket_api.er.async_get",
        return_value=mock_registry
    ):
        await websocket_suppress(hass, connection, msg)

    # Verify state was learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert "segment_cleaning" in states

    # Verify suppression was added
    assert suppression_store.is_suppressed("automation.test:vacuum.roborock_s7:invalid_state")


async def test_suppress_does_not_learn_for_non_state_issues(hass):
    """Test that non-state issues don't trigger learning."""
    from custom_components.autodoctor.websocket_api import websocket_suppress
    from custom_components.autodoctor.learned_states_store import LearnedStatesStore
    from custom_components.autodoctor.suppression_store import SuppressionStore
    from custom_components.autodoctor.const import DOMAIN

    learned_store = LearnedStatesStore(hass)
    suppression_store = SuppressionStore(hass)

    hass.data[DOMAIN] = {
        "suppression_store": suppression_store,
        "learned_states_store": learned_store,
    }

    connection = MagicMock()
    connection.send_result = MagicMock()

    msg = {
        "id": 1,
        "type": "autodoctor/suppress",
        "automation_id": "automation.test",
        "entity_id": "vacuum.unknown",
        "issue_type": "entity_not_found",  # Not a state issue
    }

    await websocket_suppress(hass, connection, msg)

    # Verify no states were learned
    states = learned_store.get_learned_states("vacuum", "roborock")
    assert len(states) == 0
```

**Step 2: Run tests to verify they fail**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_websocket_api_learning.py -v`

Expected: FAIL (likely missing 'state' parameter in schema)

**Step 3: Modify websocket_api.py**

Update the suppress command schema:

```python
@websocket_api.websocket_command(
    {
        vol.Required("type"): "autodoctor/suppress",
        vol.Required("automation_id"): str,
        vol.Required("entity_id"): str,
        vol.Required("issue_type"): str,
        vol.Optional("state"): str,  # NEW: state value for learning
    }
)
@websocket_api.async_response
async def websocket_suppress(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Suppress an issue, optionally learning the state."""
    from homeassistant.helpers import entity_registry as er
    from .learned_states_store import LearnedStatesStore

    data = hass.data.get(DOMAIN, {})
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    learned_store: LearnedStatesStore | None = data.get("learned_states_store")

    if not suppression_store:
        connection.send_error(msg["id"], "not_ready", "Suppression store not initialized")
        return

    # Learn state if this is an invalid_state issue with a state value
    if (
        learned_store
        and msg["issue_type"] == "invalid_state"
        and "state" in msg
    ):
        entity_id = msg["entity_id"]
        state = msg["state"]

        # Get integration from entity registry
        entity_registry = er.async_get(hass)
        entry = entity_registry.async_get(entity_id)

        if entry and entry.platform:
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            await learned_store.async_learn_state(domain, entry.platform, state)
            _LOGGER.info(
                "Learned state '%s' for %s entities from %s integration",
                state, domain, entry.platform
            )

    # Suppress the issue
    key = f"{msg['automation_id']}:{msg['entity_id']}:{msg['issue_type']}"
    await suppression_store.async_suppress(key)

    connection.send_result(msg["id"], {"success": True, "suppressed_count": suppression_store.count})
```

**Step 4: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/test_websocket_api_learning.py -v`

Expected: Both tests PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py tests/test_websocket_api_learning.py
git commit -m "feat: learn states when suppressing invalid_state issues"
```

---

## Task 5: Initialize Stores in __init__.py

Wire up the LearnedStatesStore in the integration initialization.

**Files:**
- Modify: `custom_components/autodoctor/__init__.py`

**Step 1: Read current __init__.py**

Check how SuppressionStore is initialized and follow the same pattern.

**Step 2: Add LearnedStatesStore initialization**

Add import:

```python
from .learned_states_store import LearnedStatesStore
```

In `async_setup_entry()`, after SuppressionStore initialization:

```python
# Initialize learned states store
learned_states_store = LearnedStatesStore(hass)
await learned_states_store.async_load()

# Store references
hass.data[DOMAIN]["learned_states_store"] = learned_states_store
```

Update knowledge base creation to use the store:

```python
knowledge_base = StateKnowledgeBase(
    hass,
    history_days=config.get("history_days", 30),
    learned_states_store=learned_states_store,
)
```

**Step 3: Run integration tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/ -v --ignore=tests/test_init.py --ignore=tests/test_simulator.py --ignore=tests/test_suggestion_learner.py --ignore=tests/test_websocket_api.py --ignore=tests/test_entity_graph.py -k "not staleness and not trigger_condition_compatibility and not notification"`

Expected: Tests pass (excluding known failing tests)

**Step 4: Commit**

```bash
git add custom_components/autodoctor/__init__.py
git commit -m "feat: initialize LearnedStatesStore in integration setup"
```

---

## Task 6: HA State Extraction Script

Create the build-time script to extract valid states from Home Assistant source.

**Files:**
- Create: `scripts/extract_ha_states.py`

**Step 1: Write the extraction script**

```python
#!/usr/bin/env python3
"""Extract valid entity states from Home Assistant source code.

This script parses HA core to extract state enums and generates
an updated device_class_states.py file.

Usage:
    python scripts/extract_ha_states.py --ha-path ~/home-assistant/core

Requirements:
    - Clone of home-assistant/core repository
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


# Known domain-to-enum mappings
DOMAIN_ENUM_MAPPINGS: dict[str, list[str]] = {
    "vacuum": ["VacuumActivity"],
    "alarm_control_panel": ["AlarmControlPanelState"],
    "climate": ["HVACMode"],
    "lock": ["LockState"],
    "cover": ["CoverState"],
    "media_player": ["MediaPlayerState"],
    "water_heater": ["WaterHeaterOperation"],
    "lawn_mower": ["LawnMowerActivity"],
    "humidifier": ["HumidifierAction"],  # Note: may use on/off instead
}

# Regex patterns
ENUM_CLASS_PATTERN = re.compile(
    r'class\s+(\w+)\s*\(\s*(?:str\s*,\s*)?(?:Str)?Enum\s*\)\s*:',
    re.MULTILINE
)
ENUM_VALUE_PATTERN = re.compile(
    r'^\s+(\w+)\s*=\s*["\']([^"\']+)["\']',
    re.MULTILINE
)


def find_const_file(ha_path: Path, domain: str) -> Path | None:
    """Find const.py for a domain."""
    const_path = ha_path / "homeassistant" / "components" / domain / "const.py"
    if const_path.exists():
        return const_path
    return None


def extract_enum_values(content: str, enum_name: str) -> set[str]:
    """Extract values from an enum class definition."""
    values = set()

    # Find the enum class
    pattern = rf'class\s+{enum_name}\s*\([^)]+\)\s*:'
    match = re.search(pattern, content)
    if not match:
        return values

    # Get content after class definition
    start = match.end()
    lines = content[start:].split('\n')

    for line in lines:
        # Stop at next class/function definition
        if re.match(r'^class\s+|^def\s+|^async\s+def\s+', line):
            break

        # Extract enum value
        value_match = ENUM_VALUE_PATTERN.match(line)
        if value_match:
            values.add(value_match.group(2))

    return values


def extract_domain_states(ha_path: Path, domain: str) -> set[str] | None:
    """Extract valid states for a domain from HA source."""
    const_path = find_const_file(ha_path, domain)
    if not const_path:
        return None

    content = const_path.read_text()

    # Try known enum mappings first
    enum_names = DOMAIN_ENUM_MAPPINGS.get(domain, [])
    for enum_name in enum_names:
        values = extract_enum_values(content, enum_name)
        if values:
            return values

    # Fallback: look for any State/Activity/Mode enum
    for match in ENUM_CLASS_PATTERN.finditer(content):
        enum_name = match.group(1)
        if any(x in enum_name for x in ["State", "Activity", "Mode", "Operation"]):
            values = extract_enum_values(content, enum_name)
            if values:
                return values

    return None


def get_git_info(ha_path: Path) -> str:
    """Get git commit info from HA repo."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ha_path,
            capture_output=True,
            text=True
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def generate_output(states_by_domain: dict[str, set[str]], ha_commit: str) -> str:
    """Generate the device_class_states.py content."""
    lines = [
        '"""Device class state mappings for known Home Assistant domains.',
        '',
        f'Auto-generated by scripts/extract_ha_states.py',
        f'Source: home-assistant/core @ {ha_commit}',
        f'Generated: {datetime.now().isoformat()}',
        '',
        'Do not edit the EXTRACTED_STATES section manually.',
        'Manual additions should go in MANUAL_STATES below.',
        '"""',
        '',
        'from __future__ import annotations',
        '',
        '# States extracted from Home Assistant source',
        'EXTRACTED_STATES: dict[str, set[str]] = {',
    ]

    for domain in sorted(states_by_domain.keys()):
        states = states_by_domain[domain]
        states_str = ", ".join(f'"{s}"' for s in sorted(states))
        lines.append(f'    "{domain}": {{{states_str}}},')

    lines.extend([
        '}',
        '',
        '# Manual additions for domains not extracted from source',
        '# Edit this section to add domain states not in HA core',
        'MANUAL_STATES: dict[str, set[str]] = {',
        '    "binary_sensor": {"on", "off"},',
        '    "switch": {"on", "off"},',
        '    "light": {"on", "off"},',
        '    "fan": {"on", "off"},',
        '    "input_boolean": {"on", "off"},',
        '    "script": {"on", "off"},',
        '    "automation": {"on", "off"},',
        '    "update": {"on", "off"},',
        '    "schedule": {"on", "off"},',
        '    "humidifier": {"on", "off"},',
        '    "siren": {"on", "off"},',
        '    "remote": {"on", "off"},',
        '    "calendar": {"on", "off"},',
        '    "button": {"unknown"},',
        '    "event": {"unknown"},',
        '    "input_button": {"unknown"},',
        '    "scene": {"unknown"},',
        '    "person": {"home", "not_home"},',
        '    "device_tracker": {"home", "not_home"},',
        '    "timer": {"idle", "active", "paused"},',
        '}',
        '',
        '# Combined states (extracted + manual)',
        'DEVICE_CLASS_STATES: dict[str, set[str]] = {',
        '    **EXTRACTED_STATES,',
        '    **MANUAL_STATES,',
        '}',
        '',
        '',
        'def get_device_class_states(domain: str) -> set[str] | None:',
        '    """Get known valid states for a domain.',
        '',
        '    Args:',
        '        domain: The entity domain (e.g., \'binary_sensor\', \'lock\')',
        '',
        '    Returns:',
        '        Set of valid states, or None if domain is unknown',
        '    """',
        '    return DEVICE_CLASS_STATES.get(domain)',
        '',
        '',
        'def get_all_known_domains() -> set[str]:',
        '    """Get all domains with known state mappings.',
        '',
        '    Returns:',
        '        Set of domain names',
        '    """',
        '    return set(DEVICE_CLASS_STATES.keys())',
        '',
    ])

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extract valid states from Home Assistant source"
    )
    parser.add_argument(
        "--ha-path",
        type=Path,
        required=True,
        help="Path to home-assistant/core repository"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: custom_components/autodoctor/device_class_states.py)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output instead of writing to file"
    )

    args = parser.parse_args()

    if not args.ha_path.exists():
        print(f"Error: HA path does not exist: {args.ha_path}", file=sys.stderr)
        sys.exit(1)

    # Extract states from each domain
    states_by_domain: dict[str, set[str]] = {}

    for domain in DOMAIN_ENUM_MAPPINGS.keys():
        states = extract_domain_states(args.ha_path, domain)
        if states:
            states_by_domain[domain] = states
            print(f"Extracted {len(states)} states for {domain}")
        else:
            print(f"Warning: Could not extract states for {domain}")

    # Generate output
    ha_commit = get_git_info(args.ha_path)
    output = generate_output(states_by_domain, ha_commit)

    if args.dry_run:
        print(output)
    else:
        output_path = args.output or Path("custom_components/autodoctor/device_class_states.py")
        output_path.write_text(output)
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
```

**Step 2: Make script executable and test manually**

```bash
chmod +x scripts/extract_ha_states.py
python scripts/extract_ha_states.py --ha-path /path/to/home-assistant/core --dry-run
```

**Step 3: Commit**

```bash
git add scripts/extract_ha_states.py
git commit -m "feat: add script to extract states from HA source"
```

---

## Task 7: Update Index and Documentation

Update the codebase index with new modules.

**Files:**
- Modify: `index.md`

**Step 1: Add new modules to index**

Add under the appropriate section:

```markdown
### State Learning
- `learned_states_store.py` - Persistent storage for user-learned states
```

Add to scripts section:

```markdown
### Scripts
- `scripts/extract_ha_states.py` - Extract valid states from HA source
```

**Step 2: Commit**

```bash
git add index.md
git commit -m "docs: update index with new state learning modules"
```

---

## Task 8: Final Integration Test

Run full test suite and verify the feature works end-to-end.

**Step 1: Run all tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/python -m pytest tests/ -v --ignore=tests/test_init.py --ignore=tests/test_simulator.py --ignore=tests/test_suggestion_learner.py --ignore=tests/test_websocket_api.py --ignore=tests/test_entity_graph.py`

Expected: New tests pass, existing tests still pass (minus known failures)

**Step 2: Verify learned states flow**

Manual verification checklist:
1. LearnedStatesStore persists states
2. KnowledgeBase includes learned states in validation
3. WebSocket suppress command learns states for invalid_state issues
4. States are stored per domain+integration

**Step 3: Final commit if any cleanup needed**

```bash
git status
# If any uncommitted changes, commit them
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | LearnedStatesStore | 5 new tests |
| 2 | get_integration helper | 2 new tests |
| 3 | Knowledge base integration | 1 new test |
| 4 | WebSocket learning | 2 new tests |
| 5 | Init wiring | Integration test |
| 6 | Extraction script | Manual test |
| 7 | Documentation | N/A |
| 8 | Final verification | Full suite |

Total new tests: ~10
Commits: ~8
