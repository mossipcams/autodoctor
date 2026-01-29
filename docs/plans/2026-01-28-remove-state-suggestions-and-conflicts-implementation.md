# Remove State Suggestions and Conflict Detection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove state synonym suggestions and entire conflict detection system to reduce maintenance burden while preserving entity ID suggestion functionality.

**Architecture:** Surgical removal of two independent features - state suggestions (synonym table + fuzzy matching) and conflict detection (detector, models, analyzer methods, WebSocket API). Each removal is isolated to minimize impact on core validation.

**Tech Stack:** Python 3.12+, Home Assistant, pytest

---

### Task 1: Remove State Suggestion Tests

**Files:**
- Modify: `tests/test_fix_engine.py`

**Step 1: Remove TestStateSynonyms class**

Delete lines 10-21 (entire TestStateSynonyms class).

**Step 2: Remove TestGetStateSuggestion class**

Delete lines 23-55 (entire TestGetStateSuggestion class).

**Step 3: Update imports**

Remove `STATE_SYNONYMS` and `get_state_suggestion` from import:

```python
from custom_components.autodoctor.fix_engine import (
    get_entity_suggestion,
)
```

**Step 4: Run tests to verify cleanup**

Run: `pytest tests/test_fix_engine.py -v`
Expected: Only `TestGetEntitySuggestion` tests remain and all pass

**Step 5: Commit**

```bash
git add tests/test_fix_engine.py
git commit -m "test: remove state suggestion tests"
```

---

### Task 2: Remove State Suggestions from fix_engine.py

**Files:**
- Modify: `custom_components/autodoctor/fix_engine.py:1-104`

**Step 1: Remove STATE_SYNONYMS dictionary**

Delete lines 7-57 (entire `STATE_SYNONYMS` dictionary).

**Step 2: Remove get_state_suggestion function**

Delete lines 60-84 (entire `get_state_suggestion()` function).

**Step 3: Update imports**

Change line 5 from:
```python
from difflib import get_close_matches
```

To only import what's needed for entity suggestions:
```python
from difflib import get_close_matches
```

Note: Keep the import since `get_entity_suggestion` still uses it.

**Step 4: Verify file structure**

File should now contain:
- Imports (lines 1-5)
- `get_entity_suggestion()` function only

**Step 5: Run tests to verify**

Run: `pytest tests/test_fix_engine.py -v`
Expected: All remaining tests pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/fix_engine.py
git commit -m "refactor: remove state synonym table and get_state_suggestion"
```

---

### Task 3: Remove State Suggestions from WebSocket API

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py:17,38-41,61-72`

**Step 1: Remove get_state_suggestion import**

Change line 17 from:
```python
from .fix_engine import get_entity_suggestion, get_state_suggestion
```

To:
```python
from .fix_engine import get_entity_suggestion
```

**Step 2: Remove _extract_invalid_state helper**

Delete lines 38-41 (entire `_extract_invalid_state()` function) - no longer needed.

**Step 3: Remove INVALID_STATE suggestion block**

In `_format_issues_with_fixes()`, delete lines 61-72:
```python
        elif issue.issue_type == IssueType.INVALID_STATE:
            invalid_state = _extract_invalid_state(issue.message)
            if invalid_state and issue.valid_states:
                suggestion = get_state_suggestion(
                    invalid_state, set(issue.valid_states)
                )
                if suggestion:
                    fix = {
                        "description": f"Did you mean '{suggestion}'?",
                        "confidence": 0.8,
                        "fix_value": suggestion,
                    }
```

**Step 4: Verify logic flow**

After removal, `_format_issues_with_fixes()` should:
- Check for `ENTITY_NOT_FOUND` and `ENTITY_REMOVED` → suggest entity
- All other issue types → `fix = None`

**Step 5: Run integration test**

Run: `pytest tests/test_websocket_api.py -v -k "fix"`
Expected: Tests pass (fix suggestions only for entity issues)

**Step 6: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py
git commit -m "refactor: remove state suggestion from WebSocket API"
```

---

### Task 4: Remove Conflict Detection WebSocket Handlers

**Files:**
- Modify: `custom_components/autodoctor/websocket_api.py:15,32-33,244-334`

**Step 1: Remove ConflictDetector import**

Delete line 15:
```python
from .conflict_detector import ConflictDetector
```

**Step 2: Remove command registrations**

In `async_setup_websocket_api()`, delete lines 32-33:
```python
    websocket_api.async_register_command(hass, websocket_get_conflicts)
    websocket_api.async_register_command(hass, websocket_run_conflicts)
```

**Step 3: Remove _format_conflicts helper**

Delete lines 244-258 (entire `_format_conflicts()` function).

**Step 4: Remove websocket_get_conflicts handler**

Delete lines 261-287 (entire `websocket_get_conflicts()` function with decorator).

**Step 5: Remove websocket_run_conflicts handler**

Delete lines 290-334 (entire `websocket_run_conflicts()` function with decorator).

**Step 6: Run tests to verify**

Run: `pytest tests/test_websocket_api.py -v`
Expected: All tests pass (conflict-related tests removed in next task)

**Step 7: Commit**

```bash
git add custom_components/autodoctor/websocket_api.py
git commit -m "refactor: remove conflict detection WebSocket handlers"
```

---

### Task 5: Delete Conflict Detection Files

**Files:**
- Delete: `custom_components/autodoctor/conflict_detector.py`
- Delete: `tests/test_conflict_detector.py`

**Step 1: Delete conflict_detector.py**

Run: `git rm custom_components/autodoctor/conflict_detector.py`

**Step 2: Delete test_conflict_detector.py**

Run: `git rm tests/test_conflict_detector.py`

**Step 3: Verify files deleted**

Run: `git status`
Expected: Both files shown as deleted

**Step 4: Run tests to check for broken imports**

Run: `pytest tests/ -v`
Expected: May fail due to model imports in analyzer.py (fixed in next tasks)

**Step 5: Commit**

```bash
git commit -m "refactor: delete conflict detection module and tests"
```

---

### Task 6: Remove Conflict Detection Models

**Files:**
- Modify: `custom_components/autodoctor/models.py:30-95`

**Step 1: Remove TriggerInfo class**

Delete lines 30-38 (entire `TriggerInfo` class with docstring).

**Step 2: Remove ConditionInfo class**

Delete lines 41-46 (entire `ConditionInfo` class with docstring).

**Step 3: Remove EntityAction class**

Delete lines 49-57 (entire `EntityAction` class with docstring).

**Step 4: Remove Conflict class**

Delete lines 60-95 (entire `Conflict` class including `to_dict()` and `get_suppression_key()` methods).

**Step 5: Verify remaining models**

File should contain:
- `Severity` enum
- `IssueType` enum
- `StateReference` dataclass
- `ValidationIssue` dataclass

**Step 6: Run tests to verify**

Run: `pytest tests/test_models.py -v`
Expected: Tests may fail if they test removed models (no test_models.py tests for these based on grep)

**Step 7: Commit**

```bash
git add custom_components/autodoctor/models.py
git commit -m "refactor: remove conflict detection data models"
```

---

### Task 7: Remove Conflict Detection Methods from Analyzer

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:9-14,477-820`

**Step 1: Remove model imports**

Change lines 9-14 from:
```python
from .models import (
    ConditionInfo,
    EntityAction,
    StateReference,
    TriggerInfo,
)
```

To:
```python
from .models import StateReference
```

**Step 2: Find end of extract_state_references methods**

Run: `grep -n "^    def extract_entity_actions" custom_components/autodoctor/analyzer.py`
Expected: Line 477 (or similar)

This tells us everything from line 477 onward is conflict-detection-only code.

**Step 3: Remove all conflict detection methods**

Delete from line 477 to end of file (line 820):
- `extract_entity_actions()`
- `_extract_actions_recursive()`
- `extract_triggers()`
- `extract_conditions()`
- All related helper methods

**Step 4: Verify file ends cleanly**

The file should end after the last state reference extraction method.

**Step 5: Run tests to verify**

Run: `pytest tests/test_analyzer.py::test_extract_state_trigger_to -v`
Expected: Core validation tests still pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/analyzer.py
git commit -m "refactor: remove conflict detection methods from analyzer"
```

---

### Task 8: Remove Conflict Detection Tests from test_analyzer.py

**Files:**
- Modify: `tests/test_analyzer.py`

**Step 1: Identify test functions to remove**

Run: `grep -n "^def test.*extract_entity_actions\|^def test.*extract_triggers\|^def test.*extract_conditions" tests/test_analyzer.py`

Expected output shows test line numbers (e.g., 857, 897, 944, 980).

**Step 2: Remove all extract_entity_actions tests**

Delete test functions:
- `test_extract_entity_actions_with_choose_conditions` (line 857+)
- `test_extract_entity_actions_with_if_conditions` (line 897+)
- `test_extract_entity_actions_with_repeat_while_conditions` (line 944+)
- `test_extract_entity_actions_nested_conditions_accumulate` (line 980+)

Plus any other `extract_entity_actions`, `extract_triggers`, or `extract_conditions` tests.

**Step 3: Find where to cut**

Run: `wc -l tests/test_analyzer.py`
Check if there are tests after line 980 that should be kept.

Run: `tail -50 tests/test_analyzer.py`
Verify the file ends after the conflict detection tests.

**Step 4: Remove from first conflict test to end**

If conflict tests are at the end (likely), delete from line 857 to end of file.

**Step 5: Run tests to verify**

Run: `pytest tests/test_analyzer.py -v`
Expected: Only state reference extraction tests remain and all pass

**Step 6: Commit**

```bash
git add tests/test_analyzer.py
git commit -m "test: remove conflict detection analyzer tests"
```

---

### Task 9: Update Documentation (index.md)

**Files:**
- Modify: `index.md:17,54,88-89,114`

**Step 1: Remove conflict_detector.py from directory structure**

Delete line 17:
```
│   ├── conflict_detector.py         # Automation conflict detection
```

**Step 2: Remove from Analysis Layer section**

Delete line 54:
```
- **`conflict_detector.py`** - Finds automations with opposing actions on same entity
```

**Step 3: Remove WebSocket API commands**

Delete lines 88-89:
```
| `autodoctor/conflicts` | Get detected conflicts |
| `autodoctor/conflicts/run` | Detect conflicts on demand |
```

**Step 4: Remove test file reference**

Delete line 114:
```
- `test_conflict_detector.py` - Conflict detection
```

**Step 5: Verify documentation consistency**

Read through index.md to ensure no other conflict detection references remain.

Run: `grep -i "conflict" index.md`
Expected: No results

**Step 6: Commit**

```bash
git add index.md
git commit -m "docs: remove conflict detection from index"
```

---

### Task 10: Run Full Test Suite

**Files:**
- None (verification only)

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 2: Run specific test files to verify**

Run: `pytest tests/test_fix_engine.py tests/test_websocket_api.py tests/test_analyzer.py tests/test_models.py -v`
Expected: All pass

**Step 3: Check for any remaining imports**

Run: `grep -r "ConflictDetector\|get_state_suggestion\|STATE_SYNONYMS\|EntityAction\|TriggerInfo\|ConditionInfo" custom_components/autodoctor/ tests/ --include="*.py"`
Expected: No results (or only in comments/strings)

**Step 4: Verify file counts**

Run: `git status`
Expected: Clean working directory, all changes committed

**Step 5: Create final summary commit if needed**

If any small cleanup is needed, make final commit:
```bash
git add .
git commit -m "chore: final cleanup after removing state suggestions and conflicts"
```

---

### Task 11: Verification and Summary

**Files:**
- None (verification only)

**Step 1: Count lines removed**

Run: `git diff main --stat`
Expected: ~600+ lines removed across multiple files

**Step 2: Verify core functionality intact**

Run: `pytest tests/test_validator.py -v`
Expected: All validation tests pass

**Step 3: Check git log**

Run: `git log --oneline -11`
Expected: Clean series of commits documenting the removal

**Step 4: Generate summary**

Output summary showing:
- Files modified: 6
- Files deleted: 2
- Lines removed: ~600+
- Tests passing: All
- Core validation: Intact

---

## Testing Strategy

Each task includes verification steps to ensure:
1. Tests pass after each change
2. Imports are clean (no broken references)
3. Core validation functionality remains intact
4. Documentation stays in sync

## Rollback Plan

Each task is committed separately. To rollback:
```bash
git revert <commit-hash>
```

Or to rollback the entire feature:
```bash
git revert HEAD~11..HEAD
```
