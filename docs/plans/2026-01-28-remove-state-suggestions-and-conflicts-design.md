# Remove State Suggestions and Conflict Detection

## Overview

Remove two features that are no longer needed:
1. State synonym table and state suggestion system
2. Entire conflict detection system

## Rationale

**State suggestions:** The `STATE_SYNONYMS` table and `get_state_suggestion()` function attempt to suggest corrections for invalid states but add maintenance burden and complexity. Entity suggestions remain useful for catching typos.

**Conflict detection:** The conflict detection system adds significant complexity and maintenance burden. The feature requires tracking triggers, conditions, and actions across automations, with limited real-world value.

## Part 1: Remove State Suggestions

### Changes to `fix_engine.py`

**Remove:**
- `STATE_SYNONYMS` dictionary (lines 7-57)
- `get_state_suggestion()` function (lines 60-84)
- Import of `get_close_matches` from difflib (no longer needed after removing state suggestion)

**Keep:**
- `get_entity_suggestion()` function - still useful for entity ID typo detection

### Changes to `websocket_api.py`

**Remove:**
- Import of `get_state_suggestion` (line 17)
- The `elif issue.issue_type == IssueType.INVALID_STATE:` block in `_format_issues_with_fixes()` (lines 61-72)

**Result:** Issues with invalid states will still be returned to the frontend, just without fix suggestions.

## Part 2: Remove Conflict Detection

### Files to Delete

- `custom_components/autodoctor/conflict_detector.py`
- `tests/test_conflict_detector.py`

### Changes to `websocket_api.py`

**Remove:**
- Import of `ConflictDetector` (line 15)
- Registration of `websocket_get_conflicts` command (line 32)
- Registration of `websocket_run_conflicts` command (line 33)
- `websocket_get_conflicts` handler function
- `websocket_run_conflicts` handler function

### Changes to `index.md`

**Remove:**
- `conflict_detector.py` from directory structure (line 17)
- Description from Analysis Layer section (line 54)
- `autodoctor/conflicts` command from WebSocket API table (line 88)
- `autodoctor/conflicts/run` command from WebSocket API table (line 89)
- `test_conflict_detector.py` from Test Files section (line 114)

## Part 3: Data Model Cleanup

These data models and analyzer methods are only used by conflict detection and can be safely removed.

### Changes to `models.py`

**Remove:**
- `Conflict` class
- `EntityAction` class
- `TriggerInfo` class
- `ConditionInfo` class

### Changes to `analyzer.py`

**Remove:**
- Import of `ConditionInfo`, `EntityAction`, `TriggerInfo` from models (lines 10, 11, 13)
- `extract_entity_actions()` method (line 588+)
- `extract_triggers()` method (line 712+)
- `extract_conditions()` method (line 788+)
- All related helper methods:
  - `_extract_actions_recursive()`
  - Any condition extraction helper methods
  - Any trigger extraction helper methods

**Keep:**
- `extract_state_references()` - core validation functionality
- All helper methods used for state reference extraction

### Changes to `tests/test_analyzer.py`

**Remove:**
- All tests for `extract_entity_actions()` (starting around line 494)
- All tests for `extract_triggers()` (if any)
- All tests for `extract_conditions()` (if any)

**Keep:**
- All tests for `extract_state_references()` and core validation functionality

### Changes to `tests/test_models.py`

**Remove:**
- Tests for `EntityAction` class
- Tests for `ConditionInfo` class
- Tests for `Conflict` class
- Tests for `TriggerInfo` class

## Impact Summary

**Removed:**
- ~500 lines of code across conflict detection
- State synonym table (50 lines)
- State suggestion logic (25 lines)
- 4 data model classes
- 3 analyzer methods and their helpers
- 2 WebSocket API commands
- 2 test files

**Preserved:**
- Entity ID suggestion system (typo detection)
- All validation functionality
- State reference extraction for validation

## Migration Notes

**No migration needed** - these are purely additive features. Removing them doesn't affect:
- Existing validation functionality
- Learned states
- Suppressions
- Repair integrations
