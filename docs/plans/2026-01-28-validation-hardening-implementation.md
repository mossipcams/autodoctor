# Validation Pipeline Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the validation pipeline against malformed configs, add error handling, fix bugs, and improve performance.

**Architecture:** Add defensive error handling throughout analyzer → validator → reporter pipeline. Cache expensive lookups (entities, zones, areas). Run blocking calls in executor. Isolate per-automation failures so one bad config doesn't crash entire validation.

**Tech Stack:** Python 3.12+, Home Assistant custom component, pytest, pytest-asyncio

**Design Doc:** `docs/plans/2026-01-28-validation-pipeline-hardening-design.md`

---

## Phase 1: Critical Bugs

### Task 1: Fix null entity_id in analyzer triggers

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:116-123`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_handles_null_entity_id_in_trigger():
    """Test that null entity_id in trigger doesn't crash extraction."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_null_entity",
        "alias": "Test Null Entity",
        "triggers": [
            {
                "platform": "state",
                "entity_id": None,  # Explicitly null
                "to": "on",
            }
        ],
        "actions": [],
    }
    # Should not raise, should return empty list
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)
```

**Step 2: Run test to verify it fails**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py::test_extract_handles_null_entity_id_in_trigger -v`

Expected: FAIL with `TypeError: 'NoneType' object is not iterable`

**Step 3: Fix null handling in _extract_from_trigger**

In `custom_components/autodoctor/analyzer.py`, find line ~116 and change:

```python
# Before
entity_ids = trigger.get("entity_id", [])

# After
entity_ids = trigger.get("entity_id") or []
```

**Step 4: Run test to verify it passes**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py::test_extract_handles_null_entity_id_in_trigger -v`

Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "fix(analyzer): handle null entity_id in triggers"
```

---

### Task 2: Fix null entity_id in all analyzer locations

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py` (lines ~149, ~213, ~333, ~371, ~455)

**Step 1: Write additional failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_handles_null_entity_id_in_numeric_state_trigger():
    """Test null entity_id in numeric_state trigger."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_numeric_null",
        "alias": "Test Numeric Null",
        "triggers": [
            {
                "platform": "numeric_state",
                "entity_id": None,
                "above": 50,
            }
        ],
        "actions": [],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_entity_id_in_condition():
    """Test null entity_id in condition."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_cond_null",
        "alias": "Test Condition Null",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "state",
                "entity_id": None,
                "state": "on",
            }
        ],
        "actions": [],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)


def test_extract_handles_null_choose_options():
    """Test null choose options don't crash."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_choose_null",
        "alias": "Test Choose Null",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [
            {
                "choose": None,  # Explicitly null
            }
        ],
    }
    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)
```

**Step 2: Run tests to verify they fail**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py -k "null" -v`

Expected: Multiple FAILs

**Step 3: Apply fix pattern to all locations**

In `custom_components/autodoctor/analyzer.py`, apply `or []` pattern:

Line ~149 (numeric_state trigger):
```python
entity_ids = trigger.get("entity_id") or []
```

Line ~213 (condition):
```python
entity_ids = condition.get("entity_id") or []
```

Line ~333 (choose):
```python
options = action.get("choose") or []
default = action.get("default") or []
```

Line ~371 (if/then):
```python
conditions = action.get("if") or []
```

Line ~455 (parallel):
```python
branches = action.get("parallel") or []
```

**Step 4: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py -k "null" -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "fix(analyzer): handle null values in all extraction locations"
```

---

### Task 3: Add recursion depth limit to jinja_validator

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_jinja_validator.py` (create if doesn't exist):

```python
import pytest
from custom_components.autodoctor.jinja_validator import JinjaValidator


def test_deeply_nested_conditions_do_not_stackoverflow():
    """Test that deeply nested conditions hit recursion limit gracefully."""
    validator = JinjaValidator()

    # Build deeply nested condition (25 levels deep)
    condition = {"condition": "state", "entity_id": "light.test", "state": "on"}
    for _ in range(25):
        condition = {"condition": "and", "conditions": [condition]}

    automation = {
        "id": "deep_nest",
        "alias": "Deeply Nested",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [condition],
        "actions": [],
    }

    # Should not raise RecursionError, should return (possibly with warning logged)
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_jinja_validator.py::test_deeply_nested_conditions_do_not_stackoverflow -v`

Expected: May pass or fail depending on Python recursion limit (test the behavior)

**Step 3: Add recursion depth constant and parameter**

In `custom_components/autodoctor/jinja_validator.py`, add at top after imports:

```python
MAX_RECURSION_DEPTH = 20
```

Update `_validate_condition` signature and add depth check:

```python
def _validate_condition(
    self,
    condition: Any,
    index: int,
    auto_id: str,
    auto_name: str,
    location_prefix: str,
    _depth: int = 0,
) -> list[ValidationIssue]:
    """Validate a single condition for Jinja syntax errors."""
    issues: list[ValidationIssue] = []

    if _depth > MAX_RECURSION_DEPTH:
        _LOGGER.warning(
            "Max recursion depth exceeded in %s at %s, stopping validation",
            auto_id, location_prefix
        )
        return issues

    # ... rest of method, passing _depth + 1 to recursive calls
```

Update all recursive calls to pass `_depth + 1`.

**Step 4: Run test to verify it passes**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_jinja_validator.py::test_deeply_nested_conditions_do_not_stackoverflow -v`

Expected: PASS

**Step 5: Apply same pattern to _validate_actions**

Add `_depth: int = 0` parameter and depth check to `_validate_actions` method.

**Step 6: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "fix(jinja_validator): add recursion depth limits"
```

---

### Task 4: Add type guards in jinja_validator

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py:299, 327`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_jinja_validator.py`:

```python
def test_null_repeat_config_does_not_crash():
    """Test that repeat: null doesn't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": "null_repeat",
        "alias": "Null Repeat",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{"repeat": None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)


def test_null_parallel_config_does_not_crash():
    """Test that parallel: null doesn't crash validation."""
    validator = JinjaValidator()
    automation = {
        "id": "null_parallel",
        "alias": "Null Parallel",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [{"parallel": None}],
    }
    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)
```

**Step 2: Run tests to verify they fail**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_jinja_validator.py -k "null" -v`

Expected: FAIL with `AttributeError: 'NoneType' has no attribute 'get'`

**Step 3: Add type guards**

In `custom_components/autodoctor/jinja_validator.py`, around line 299:

```python
# Before
if "repeat" in action:
    repeat_config = action["repeat"]
    sequence = repeat_config.get("sequence", [])

# After
if "repeat" in action:
    repeat_config = action.get("repeat")
    if not isinstance(repeat_config, dict):
        continue
    sequence = repeat_config.get("sequence") or []
```

Around line 327:

```python
# Before
if "parallel" in action:
    branches = action["parallel"]

# After
if "parallel" in action:
    branches = action.get("parallel")
    if not isinstance(branches, list):
        continue
```

**Step 4: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_jinja_validator.py -k "null" -v`

Expected: PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "fix(jinja_validator): add type guards for null repeat/parallel"
```

---

### Task 5: Add error isolation in async_validate_all

**Files:**
- Modify: `custom_components/autodoctor/__init__.py:398-413`
- Test: `tests/test_init.py`

**Step 1: Write the failing test**

Add to `tests/test_init.py` (create if needed):

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from custom_components.autodoctor import async_validate_all
from custom_components.autodoctor.const import DOMAIN


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


@pytest.mark.asyncio
async def test_one_bad_automation_does_not_crash_all(mock_hass):
    """Test that one malformed automation doesn't stop validation of others."""
    # Setup mocks
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_reporter = AsyncMock()

    # First automation raises, second succeeds
    mock_analyzer.extract_state_references.side_effect = [
        Exception("Malformed config"),
        [],  # Second automation succeeds
    ]
    mock_validator.validate_all.return_value = []

    mock_hass.data[DOMAIN] = {
        "analyzer": mock_analyzer,
        "validator": mock_validator,
        "reporter": mock_reporter,
        "knowledge_base": None,
    }

    # Mock _get_automation_configs to return 2 automations
    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[
            {"id": "bad", "alias": "Bad Auto"},
            {"id": "good", "alias": "Good Auto"},
        ],
    ):
        issues = await async_validate_all(mock_hass)

    # Should have processed both automations (one failed, one succeeded)
    assert mock_analyzer.extract_state_references.call_count == 2
    assert isinstance(issues, list)
```

**Step 2: Run test to verify current behavior**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_init.py::test_one_bad_automation_does_not_crash_all -v`

Expected: Likely FAIL (exception propagates)

**Step 3: Add error isolation**

In `custom_components/autodoctor/__init__.py`, modify `async_validate_all`:

```python
async def async_validate_all(hass: HomeAssistant) -> list:
    """Validate all automations."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    jinja_validator = data.get("jinja_validator")
    reporter = data.get("reporter")
    knowledge_base = data.get("knowledge_base")

    if not all([analyzer, validator, reporter]):
        _LOGGER.warning("Autodoctor components not initialized, skipping validation")
        return []

    # Clear validator cache before each run (if method exists)
    if hasattr(validator, "clear_cache"):
        validator.clear_cache()

    # Load history if needed
    if knowledge_base:
        try:
            if hasattr(knowledge_base, "has_history_loaded"):
                needs_history = not knowledge_base.has_history_loaded()
            else:
                needs_history = not knowledge_base._observed_states
            if needs_history:
                await knowledge_base.async_load_history()
        except Exception as err:
            _LOGGER.warning("Failed to load history, continuing without: %s", err)

    try:
        automations = _get_automation_configs(hass)
    except Exception as err:
        _LOGGER.error("Failed to get automation configs: %s", err)
        return []

    if not automations:
        _LOGGER.debug("No automations found to validate")
        return []

    _LOGGER.info("Validating %d automations", len(automations))

    all_issues = []
    failed_automations = 0

    # Run Jinja template validation first
    if jinja_validator:
        try:
            jinja_issues = jinja_validator.validate_automations(automations)
            all_issues.extend(jinja_issues)
        except Exception as err:
            _LOGGER.warning("Jinja validation failed: %s", err)

    # Run state reference validation - isolate each automation
    for automation in automations:
        auto_id = automation.get("id", "unknown")
        auto_name = automation.get("alias", auto_id)

        try:
            refs = analyzer.extract_state_references(automation)
            issues = validator.validate_all(refs)
            all_issues.extend(issues)
        except Exception as err:
            failed_automations += 1
            _LOGGER.warning(
                "Failed to validate automation '%s' (%s): %s",
                auto_name, auto_id, err
            )
            continue

    if failed_automations > 0:
        _LOGGER.warning(
            "Validation completed with %d failed automations (out of %d)",
            failed_automations, len(automations)
        )

    _LOGGER.info(
        "Validation complete: %d issues found",
        len(all_issues),
    )

    try:
        await reporter.async_report_issues(all_issues)
    except Exception as err:
        _LOGGER.error("Failed to report issues: %s", err)

    # Update state atomically
    timestamp = datetime.now(UTC).isoformat()
    hass.data[DOMAIN].update({
        "issues": all_issues,
        "validation_issues": all_issues,
        "validation_last_run": timestamp,
    })

    return all_issues
```

**Step 4: Run test to verify it passes**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_init.py::test_one_bad_automation_does_not_crash_all -v`

Expected: PASS

**Step 5: Run all tests to check for regressions**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/ -v`

Expected: All pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/__init__.py tests/test_init.py
git commit -m "fix(init): isolate per-automation errors in validation"
```

---

## Phase 2: Error Handling

### Task 6: Add error handling to analyzer extraction methods

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_malformed_trigger_does_not_crash():
    """Test that malformed trigger dict doesn't crash extraction."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "test_malformed",
        "alias": "Test Malformed",
        "triggers": [
            "not a dict",  # String instead of dict
            {"platform": "state", "entity_id": "light.valid", "to": "on"},
        ],
        "actions": [],
    }
    refs = analyzer.extract_state_references(automation)
    # Should skip malformed trigger, extract from valid one
    assert len(refs) >= 1
    assert any(r.entity_id == "light.valid" for r in refs)
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py::test_malformed_trigger_does_not_crash -v`

**Step 3: Add type guard and try/except to _extract_from_trigger**

In `custom_components/autodoctor/analyzer.py`:

```python
def _extract_from_trigger(
    self,
    trigger: dict[str, Any],
    index: int,
    automation_id: str,
    automation_name: str,
) -> list[StateReference]:
    """Extract state references from a trigger."""
    refs: list[StateReference] = []

    # Guard: skip non-dict triggers
    if not isinstance(trigger, dict):
        _LOGGER.warning(
            "Skipping non-dict trigger[%d] in %s: %s",
            index, automation_id, type(trigger).__name__
        )
        return refs

    try:
        # ... existing extraction logic ...
    except Exception as err:
        _LOGGER.warning(
            "Error extracting from trigger[%d] in %s: %s",
            index, automation_id, err
        )

    return refs
```

**Step 4: Apply same pattern to other extraction methods**

- `_extract_from_condition`
- `_extract_from_template`
- `_extract_from_actions`
- `_parse_service_call`

Each should:
1. Check input type at start
2. Wrap logic in try/except
3. Log warning and return partial results on error

**Step 5: Run tests to verify they pass**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py -v`

Expected: All PASS

**Step 6: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat(analyzer): add error handling to extraction methods"
```

---

### Task 7: Add recursion depth limit to analyzer

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_deeply_nested_actions_do_not_stackoverflow():
    """Test that deeply nested actions hit recursion limit gracefully."""
    analyzer = AutomationAnalyzer()

    # Build deeply nested choose (25 levels)
    action = {"service": "light.turn_on", "target": {"entity_id": "light.test"}}
    for _ in range(25):
        action = {"choose": [{"conditions": [], "sequence": [action]}]}

    automation = {
        "id": "deep_actions",
        "alias": "Deeply Nested Actions",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "actions": [action],
    }

    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py::test_deeply_nested_actions_do_not_stackoverflow -v`

**Step 3: Add depth limiting**

Add constant at top of `analyzer.py`:

```python
MAX_RECURSION_DEPTH = 20
```

Update `_extract_from_actions` signature:

```python
def _extract_from_actions(
    self,
    actions: list[dict[str, Any]],
    automation_id: str,
    automation_name: str,
    _depth: int = 0,
) -> list[StateReference]:
    """Recursively extract state references from actions."""
    refs: list[StateReference] = []

    if _depth > MAX_RECURSION_DEPTH:
        _LOGGER.warning(
            "Max recursion depth exceeded in %s, stopping extraction",
            automation_id
        )
        return refs

    # ... rest with _depth + 1 on recursive calls
```

Apply same to `_extract_actions_recursive`.

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_analyzer.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/analyzer.py tests/test_analyzer.py
git commit -m "feat(analyzer): add recursion depth limits"
```

---

### Task 8: Add error handling to validator

**Files:**
- Modify: `custom_components/autodoctor/validator.py`
- Test: `tests/test_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_validator.py`:

```python
from unittest.mock import MagicMock
from custom_components.autodoctor.validator import ValidationEngine
from custom_components.autodoctor.models import StateReference


def test_validate_reference_handles_knowledge_base_error():
    """Test that knowledge_base errors don't crash validation."""
    mock_kb = MagicMock()
    mock_kb.entity_exists.side_effect = Exception("KB error")

    validator = ValidationEngine(mock_kb)
    ref = StateReference(
        entity_id="light.test",
        automation_id="test_auto",
        automation_name="Test",
        location="trigger[0]",
    )

    # Should not raise, should return empty list
    issues = validator.validate_reference(ref)
    assert issues == []
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_validator.py::test_validate_reference_handles_knowledge_base_error -v`

Expected: FAIL (exception propagates)

**Step 3: Add try/except to validate_reference**

In `custom_components/autodoctor/validator.py`:

```python
def validate_reference(self, ref: StateReference) -> list[ValidationIssue]:
    """Validate a single state reference."""
    issues: list[ValidationIssue] = []

    try:
        if not self.knowledge_base.entity_exists(ref.entity_id):
            # ... existing logic
            return issues

        if ref.expected_state is not None:
            issues.extend(self._validate_state(ref))

        if ref.expected_attribute is not None:
            issues.extend(self._validate_attribute(ref))

    except Exception as err:
        _LOGGER.warning(
            "Error validating %s in %s: %s",
            ref.entity_id, ref.automation_id, err
        )
        # Return empty - avoid false positives on errors

    return issues
```

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_validator.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/validator.py tests/test_validator.py
git commit -m "feat(validator): add error handling to validate_reference"
```

---

### Task 9: Add error handling to WebSocket handlers

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py`
- Test: `tests/test_websocket_api.py`

**Step 1: Write the failing test**

Add to `tests/test_websocket_api.py`:

```python
@pytest.mark.asyncio
async def test_websocket_run_validation_handles_error(hass, mock_connection):
    """Test that validation errors return proper error response."""
    from custom_components.autodoctor.websocket_api import websocket_run_validation

    hass.data[DOMAIN] = {}  # Missing required components

    msg = {"id": 1, "type": "autodoctor/validation/run"}

    await websocket_run_validation(hass, mock_connection, msg)

    # Should call send_error, not crash
    assert mock_connection.send_error.called or mock_connection.send_result.called
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_websocket_api.py::test_websocket_run_validation_handles_error -v`

**Step 3: Add try/except to handlers**

In `custom_components/autodoctor/websocket_api.py`, wrap each handler:

```python
@websocket_api.async_response
async def websocket_run_validation(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Run validation and return results."""
    try:
        from . import async_validate_all
        # ... existing logic ...
    except Exception as err:
        _LOGGER.exception("Error in websocket_run_validation: %s", err)
        connection.send_error(
            msg["id"], "validation_failed", f"Validation error: {err}"
        )
```

Apply to all handlers.

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_websocket_api.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py tests/test_websocket_api.py
git commit -m "feat(websocket): add error handling to all handlers"
```

---

### Task 10: Add error handling to reporter delete loop

**Files:**
- Modify: `custom_components/autodoctor/reporter.py:142-147`
- Test: `tests/test_reporter.py`

**Step 1: Write test**

Add to `tests/test_reporter.py`:

```python
def test_clear_resolved_issues_continues_on_delete_error(hass):
    """Test that one failed delete doesn't stop others."""
    from unittest.mock import patch, MagicMock
    from custom_components.autodoctor.reporter import IssueReporter

    reporter = IssueReporter(hass)
    reporter._active_issues = {"issue1", "issue2", "issue3"}

    delete_calls = []
    def mock_delete(hass, domain, issue_id):
        delete_calls.append(issue_id)
        if issue_id == "issue2":
            raise Exception("Delete failed")

    with patch(
        "custom_components.autodoctor.reporter.ir.async_delete_issue",
        side_effect=mock_delete
    ):
        reporter._clear_resolved_issues(set())  # All should be cleared

    # Should have attempted all 3 deletes
    assert len(delete_calls) == 3
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_reporter.py::test_clear_resolved_issues_continues_on_delete_error -v`

**Step 3: Add try/except to delete loop**

In `custom_components/autodoctor/reporter.py`:

```python
def _clear_resolved_issues(self, current_ids: set[str]) -> None:
    """Clear issues that have been resolved."""
    resolved = self._active_issues - current_ids
    for issue_id in resolved:
        try:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        except Exception as err:
            _LOGGER.warning("Failed to delete issue %s: %s", issue_id, err)
    self._active_issues = current_ids.copy()
```

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_reporter.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): add error handling to delete loop"
```

---

## Phase 3: Performance

### Task 11: Add entity suggestion caching to validator

**Files:**
- Modify: `custom_components/autodoctor/validator.py`
- Test: `tests/test_validator.py`

**Step 1: Write test for caching behavior**

Add to `tests/test_validator.py`:

```python
def test_validator_caches_entity_suggestions():
    """Test that entity cache is built once and reused."""
    mock_kb = MagicMock()
    mock_hass = MagicMock()
    mock_kb.hass = mock_hass

    # Return same entities each time
    mock_entity1 = MagicMock()
    mock_entity1.entity_id = "light.living_room"
    mock_entity2 = MagicMock()
    mock_entity2.entity_id = "light.bedroom"
    mock_hass.states.async_all.return_value = [mock_entity1, mock_entity2]

    validator = ValidationEngine(mock_kb)

    # Call _suggest_entity twice
    validator._suggest_entity("light.living_rom")  # Typo
    validator._suggest_entity("light.bedroon")  # Typo

    # async_all should only be called once (cached)
    assert mock_hass.states.async_all.call_count == 1
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_validator.py::test_validator_caches_entity_suggestions -v`

Expected: FAIL (async_all called multiple times)

**Step 3: Add caching**

In `custom_components/autodoctor/validator.py`:

```python
class ValidationEngine:
    def __init__(self, knowledge_base: StateKnowledgeBase) -> None:
        self.knowledge_base = knowledge_base
        self._entity_cache: dict[str, list[str]] | None = None

    def clear_cache(self) -> None:
        """Clear caches (call before each validation run)."""
        self._entity_cache = None

    def _ensure_entity_cache(self) -> None:
        """Build entity cache if not present."""
        if self._entity_cache is not None:
            return

        self._entity_cache = {}
        try:
            for entity in self.knowledge_base.hass.states.async_all():
                domain = entity.entity_id.split(".")[0]
                if domain not in self._entity_cache:
                    self._entity_cache[domain] = []
                self._entity_cache[domain].append(entity.entity_id)
        except Exception as err:
            _LOGGER.warning("Failed to build entity cache: %s", err)
            self._entity_cache = {}

    def _suggest_entity(self, invalid: str) -> str | None:
        """Suggest a correction for an invalid entity ID."""
        if "." not in invalid:
            return None

        self._ensure_entity_cache()
        domain, name = invalid.split(".", 1)

        same_domain = self._entity_cache.get(domain, [])
        if not same_domain:
            return None

        names = {eid.split(".", 1)[1]: eid for eid in same_domain}
        matches = get_close_matches(name, names.keys(), n=1, cutoff=0.75)

        return names[matches[0]] if matches else None
```

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_validator.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/validator.py tests/test_validator.py
git commit -m "perf(validator): cache entity suggestions"
```

---

### Task 12: Add zone/area caching to knowledge_base

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py`
- Test: `tests/test_knowledge_base.py`

**Step 1: Write test**

Add to `tests/test_knowledge_base.py`:

```python
def test_zone_names_are_cached(hass):
    """Test that zone names are only fetched once."""
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    # Call _get_zone_names twice
    zones1 = kb._get_zone_names()
    zones2 = kb._get_zone_names()

    # Should be same object (cached)
    assert zones1 is zones2
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_knowledge_base.py::test_zone_names_are_cached -v`

Expected: FAIL (method doesn't exist yet)

**Step 3: Add zone/area caching**

In `custom_components/autodoctor/knowledge_base.py`:

```python
class StateKnowledgeBase:
    def __init__(self, ...):
        # ... existing init ...
        self._zone_names: set[str] | None = None
        self._area_names: set[str] | None = None

    def _get_zone_names(self) -> set[str]:
        """Get all zone names (cached)."""
        if self._zone_names is not None:
            return self._zone_names

        self._zone_names = set()
        try:
            for zone_state in self.hass.states.async_all("zone"):
                zone_name = zone_state.attributes.get(
                    "friendly_name", zone_state.entity_id.split(".")[1]
                )
                self._zone_names.add(zone_name)
        except Exception as err:
            _LOGGER.warning("Failed to load zone names: %s", err)

        return self._zone_names

    def _get_area_names(self) -> set[str]:
        """Get all area names (cached)."""
        if self._area_names is not None:
            return self._area_names

        self._area_names = set()
        try:
            area_registry = ar.async_get(self.hass)
            for area in area_registry.async_list_areas():
                self._area_names.add(area.name)
                self._area_names.add(area.name.lower())
        except Exception as err:
            _LOGGER.warning("Failed to load area names: %s", err)

        return self._area_names

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._zone_names = None
        self._area_names = None
```

Update `get_valid_states` to use these cached methods instead of inline iteration.

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_knowledge_base.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "perf(knowledge_base): cache zone and area names"
```

---

### Task 13: Run get_significant_states in executor

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py:324`
- Test: `tests/test_knowledge_base.py`

**Step 1: Write test**

Add to `tests/test_knowledge_base.py`:

```python
@pytest.mark.asyncio
async def test_load_history_uses_executor(hass):
    """Test that history loading uses executor for blocking call."""
    from unittest.mock import patch, AsyncMock
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    # Mock async_add_executor_job
    hass.async_add_executor_job = AsyncMock(return_value={})

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states"
    ) as mock_get:
        await kb.async_load_history(["light.test"])

    # Should have called async_add_executor_job
    assert hass.async_add_executor_job.called
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_knowledge_base.py::test_load_history_uses_executor -v`

Expected: FAIL (direct call, not executor)

**Step 3: Use executor**

In `custom_components/autodoctor/knowledge_base.py`:

```python
async def async_load_history(self, entity_ids: list[str] | None = None) -> None:
    """Load state history from recorder."""
    if get_significant_states is None:
        _LOGGER.warning(
            "Recorder history not available - get_significant_states not found"
        )
        return

    async with self._lock:
        # ... setup code ...

        try:
            # Run blocking call in executor
            history = await self.hass.async_add_executor_job(
                get_significant_states,
                self.hass,
                start_time,
                end_time,
                entity_ids,
                None,  # filters
                True,  # include_start_time_state
                True,  # significant_changes_only
            )
        except Exception as err:
            _LOGGER.warning("Failed to load recorder history: %s", err)
            return

        # ... rest unchanged
```

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_knowledge_base.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py tests/test_knowledge_base.py
git commit -m "perf(knowledge_base): run get_significant_states in executor"
```

---

## Phase 4: Cleanup

### Task 14: Add has_history_loaded public method

**Files:**
- Modify: `custom_components/autodoctor/knowledge_base.py`
- Modify: `custom_components/autodoctor/__init__.py`
- Test: `tests/test_knowledge_base.py`

**Step 1: Write test**

Add to `tests/test_knowledge_base.py`:

```python
def test_has_history_loaded(hass):
    """Test has_history_loaded public method."""
    from custom_components.autodoctor.knowledge_base import StateKnowledgeBase

    kb = StateKnowledgeBase(hass)

    # Initially empty
    assert kb.has_history_loaded() is False

    # After adding observed states
    kb._observed_states["light.test"] = {"on", "off"}
    assert kb.has_history_loaded() is True
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_knowledge_base.py::test_has_history_loaded -v`

Expected: FAIL (method doesn't exist)

**Step 3: Add method**

In `custom_components/autodoctor/knowledge_base.py`:

```python
def has_history_loaded(self) -> bool:
    """Check if history has been loaded."""
    return bool(self._observed_states)
```

**Step 4: Update __init__.py to use public method**

Replace:
```python
if knowledge_base and not knowledge_base._observed_states:
```

With:
```python
if knowledge_base and not knowledge_base.has_history_loaded():
```

**Step 5: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/ -v`

Expected: All PASS

**Step 6: Commit**

```bash
git add custom_components/autodoctor/knowledge_base.py custom_components/autodoctor/__init__.py tests/test_knowledge_base.py
git commit -m "refactor(knowledge_base): add has_history_loaded public method"
```

---

### Task 15: Remove duplicated automation extraction in websocket_api

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py:303-313`

**Step 1: Verify current duplication**

Check that `websocket_run_conflicts` duplicates `_get_automation_configs` logic.

**Step 2: Import and use shared function**

In `custom_components/autodoctor/websocket_api.py`:

```python
from . import _get_automation_configs

# In websocket_run_conflicts, replace lines 303-313:
automations = _get_automation_configs(hass)
```

**Step 3: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_websocket_api.py -v`

Expected: All PASS

**Step 4: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py
git commit -m "refactor(websocket): use shared _get_automation_configs"
```

---

### Task 16: Remove redundant data storage in websocket_api

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py:145`

**Step 1: Remove redundant line**

In `websocket_refresh`, remove:
```python
hass.data[DOMAIN]["issues"] = issues
```

This is already done by `async_validate_all`.

**Step 2: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_websocket_api.py -v`

Expected: All PASS

**Step 3: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py
git commit -m "refactor(websocket): remove redundant data storage"
```

---

### Task 17: Fix ValidationIssue hash/eq

**Files:**
- Modify: `custom_components/autodoctor/models.py`
- Test: `tests/test_models.py`

**Step 1: Write test**

Add to `tests/test_models.py`:

```python
def test_validation_issue_hash_eq_consistency():
    """Test that hash and eq use same fields."""
    from custom_components.autodoctor.models import ValidationIssue, IssueType

    issue1 = ValidationIssue(
        automation_id="auto1",
        automation_name="Auto 1",
        entity_id="light.test",
        location="trigger[0]",
        message="Test message",
        issue_type=IssueType.INVALID_STATE,
        severity="warning",
    )

    # Same hash fields, different non-hash field
    issue2 = ValidationIssue(
        automation_id="auto1",
        automation_name="Different Name",  # Different
        entity_id="light.test",
        location="trigger[0]",
        message="Test message",
        issue_type=IssueType.ENTITY_NOT_FOUND,  # Different
        severity="error",  # Different
    )

    # Should be equal and have same hash (based on hash fields only)
    assert issue1 == issue2
    assert hash(issue1) == hash(issue2)

    # Should work in sets
    issue_set = {issue1, issue2}
    assert len(issue_set) == 1
```

**Step 2: Run test**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_models.py::test_validation_issue_hash_eq_consistency -v`

Expected: FAIL (eq compares all fields)

**Step 3: Add explicit __eq__**

In `custom_components/autodoctor/models.py`:

```python
@dataclass
class ValidationIssue:
    # ... fields ...

    def __hash__(self) -> int:
        """Hash for deduplication."""
        return hash((self.automation_id, self.entity_id, self.location, self.message))

    def __eq__(self, other: object) -> bool:
        """Equality based on hash fields."""
        if not isinstance(other, ValidationIssue):
            return NotImplemented
        return (
            self.automation_id == other.automation_id
            and self.entity_id == other.entity_id
            and self.location == other.location
            and self.message == other.message
        )
```

**Step 4: Run tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/test_models.py -v`

Expected: All PASS

**Step 5: Commit**

```bash
git add custom_components/autodoctor/models.py tests/test_models.py
git commit -m "fix(models): align ValidationIssue hash and eq"
```

---

## Final Steps

### Task 18: Run full test suite

**Step 1: Run all tests**

Run: `/Users/matt/Desktop/Projects/autodoctor/.venv/bin/pytest tests/ -v`

Expected: All PASS (124+ tests)

**Step 2: Run linter**

Run: `ruff check custom_components/autodoctor/`

Expected: No errors

### Task 19: Update index.md if needed

Check if any structural changes require updating `index.md`. The changes in this plan are internal refactoring, so likely no update needed.

### Task 20: Create PR

Use: `superpowers:finishing-a-development-branch`

---

## Summary

| Phase | Tasks | Commits |
|-------|-------|---------|
| 1: Critical Bugs | 1-5 | 5 |
| 2: Error Handling | 6-10 | 5 |
| 3: Performance | 11-13 | 3 |
| 4: Cleanup | 14-17 | 4 |
| Final | 18-20 | 1 |

**Total: 18 commits across 17 implementation tasks**
