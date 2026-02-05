"""Tests for architectural improvements from the full review.

These are guard tests that prevent re-introduction of removed features
and ensure key architectural decisions remain in place.
"""

import ast
import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import custom_components.autodoctor.websocket_api as ws_mod
from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.const import (
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    DEFAULT_STRICT_SERVICE_VALIDATION,
    DEFAULT_STRICT_TEMPLATE_VALIDATION,
    MAX_RECURSION_DEPTH,
    STATE_VALIDATION_WHITELIST,
)
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.validator import get_entity_suggestion


def test_state_validation_whitelist_exists() -> None:
    """Guard: Ensure STATE_VALIDATION_WHITELIST exists and contains correct domains.

    This test protects the architectural decision to only validate state values
    for domains with well-defined, finite state sets. Domains with stable,
    small state sets are whitelisted; sensor is excluded because most sensors
    have free-form numeric/text states.

    See: PROJECT.md "Key Decisions" - Selective state validation
    """
    assert isinstance(STATE_VALIDATION_WHITELIST, frozenset)
    # Original domains
    assert "binary_sensor" in STATE_VALIDATION_WHITELIST
    assert "person" in STATE_VALIDATION_WHITELIST
    assert "sun" in STATE_VALIDATION_WHITELIST
    assert "device_tracker" in STATE_VALIDATION_WHITELIST
    assert "input_boolean" in STATE_VALIDATION_WHITELIST
    assert "group" in STATE_VALIDATION_WHITELIST
    # Expanded domains with stable state sets
    assert "vacuum" in STATE_VALIDATION_WHITELIST
    assert "media_player" in STATE_VALIDATION_WHITELIST
    assert "fan" in STATE_VALIDATION_WHITELIST
    assert "light" in STATE_VALIDATION_WHITELIST
    assert "switch" in STATE_VALIDATION_WHITELIST
    assert "timer" in STATE_VALIDATION_WHITELIST
    assert "weather" in STATE_VALIDATION_WHITELIST
    # Dynamic domains should not be in the whitelist
    assert "sensor" not in STATE_VALIDATION_WHITELIST


def test_strict_config_keys_exist() -> None:
    """Guard: Ensure strict validation config keys exist with correct defaults.

    This test protects the architectural decision to make strict validation
    opt-in (defaults to False) to avoid overwhelming users with warnings for
    edge cases while still allowing power users to enable stricter checks.

    See: PROJECT.md "Key Decisions" - Configurable strictness levels
    """
    assert CONF_STRICT_TEMPLATE_VALIDATION == "strict_template_validation"
    assert CONF_STRICT_SERVICE_VALIDATION == "strict_service_validation"
    assert DEFAULT_STRICT_TEMPLATE_VALIDATION is False
    assert DEFAULT_STRICT_SERVICE_VALIDATION is False


def test_max_recursion_depth_constant() -> None:
    """Guard: Ensure MAX_RECURSION_DEPTH constant exists and is set to 50.

    This test protects the architectural decision to limit recursion depth
    when analyzing nested automation structures (choose/if/repeat/parallel).
    Prevents infinite loops and performance degradation from pathological
    automation configs.

    See: PROJECT.md "Key Decisions" - Recursion depth limits
    """
    assert MAX_RECURSION_DEPTH == 50


def test_extract_from_actions_enforces_depth_limit() -> None:
    """Guard: Verify _extract_from_actions stops recursing beyond MAX_RECURSION_DEPTH.

    This test protects against performance degradation and infinite loops when
    analyzing deeply nested choose/sequence structures. Entities beyond the
    depth limit should not be extracted.

    Tests the recursion depth enforcement in choose/sequence nesting.

    See: test_max_recursion_depth_constant for architectural reasoning
    """
    analyzer = AutomationAnalyzer()

    # Build automation with 100-level deep nesting (exceeds MAX_RECURSION_DEPTH of 50)
    # The innermost action has a service call with entity_id "light.deep"
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep"}}]
    for _ in range(100):
        actions = [{"choose": [{"conditions": [], "sequence": actions}]}]

    automation = {
        "id": "deep_actions",
        "alias": "Deep Actions",
        "trigger": [
            {"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}
        ],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    assert isinstance(refs, list)
    # The trigger ref for binary_sensor.test should be extracted (not nested)
    trigger_refs = [r for r in refs if r.entity_id == "binary_sensor.test"]
    assert len(trigger_refs) == 1
    # The deeply nested light.deep should NOT be extracted (beyond depth limit)
    deep_refs = [r for r in refs if r.entity_id == "light.deep"]
    assert len(deep_refs) == 0


def test_extract_from_actions_depth_limit_if_then_else() -> None:
    """Guard: Verify depth limit applies to if/then/else nesting.

    This test ensures the recursion depth limit also protects against
    deeply nested if/then/else structures, not just choose/sequence.

    See: test_max_recursion_depth_constant for architectural reasoning
    """
    analyzer = AutomationAnalyzer()

    # Build 100-level deep nesting using if/then
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep_if"}}]
    for _ in range(100):
        actions = [{"if": [], "then": actions}]

    automation = {
        "id": "deep_if",
        "alias": "Deep If",
        "trigger": [
            {"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}
        ],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    deep_refs = [r for r in refs if r.entity_id == "light.deep_if"]
    assert len(deep_refs) == 0


def test_extract_from_actions_depth_limit_repeat() -> None:
    """Guard: Verify depth limit applies to repeat nesting.

    This test ensures the recursion depth limit also protects against
    deeply nested repeat/sequence structures.

    See: test_max_recursion_depth_constant for architectural reasoning
    """
    analyzer = AutomationAnalyzer()

    # Build 100-level deep nesting using repeat/sequence
    actions = [
        {"service": "light.turn_on", "target": {"entity_id": "light.deep_repeat"}}
    ]
    for _ in range(100):
        actions = [{"repeat": {"count": 1, "sequence": actions}}]

    automation = {
        "id": "deep_repeat",
        "alias": "Deep Repeat",
        "trigger": [
            {"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}
        ],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    deep_refs = [r for r in refs if r.entity_id == "light.deep_repeat"]
    assert len(deep_refs) == 0


def test_extract_from_actions_depth_limit_parallel() -> None:
    """Guard: Verify depth limit applies to parallel nesting.

    This test ensures the recursion depth limit also protects against
    deeply nested parallel branch structures.

    See: test_max_recursion_depth_constant for architectural reasoning
    """
    analyzer = AutomationAnalyzer()

    # Build 100-level deep nesting using parallel branches
    actions = [
        {"service": "light.turn_on", "target": {"entity_id": "light.deep_parallel"}}
    ]
    for _ in range(100):
        actions = [{"parallel": [actions]}]

    automation = {
        "id": "deep_parallel",
        "alias": "Deep Parallel",
        "trigger": [
            {"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}
        ],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    deep_refs = [r for r in refs if r.entity_id == "light.deep_parallel"]
    assert len(deep_refs) == 0


def test_extract_service_calls_enforces_depth_limit() -> None:
    """Guard: Verify extract_service_calls enforces depth limit.

    This test ensures service call extraction also respects the recursion
    depth limit, preventing performance issues when analyzing deeply nested
    automation structures.

    See: test_max_recursion_depth_constant for architectural reasoning
    """
    analyzer = AutomationAnalyzer()

    # Build 100-level deep choose nesting with a service call at the bottom
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep"}}]
    for _ in range(100):
        actions = [{"choose": [{"conditions": [], "sequence": actions}]}]

    automation = {
        "id": "deep_service",
        "alias": "Deep Service",
        "trigger": [],
        "action": actions,
    }

    calls = analyzer.extract_service_calls(automation)
    # The deeply nested service call should NOT be extracted
    deep_calls = [c for c in calls if c.service == "light.turn_on"]
    assert len(deep_calls) == 0


def test_extract_service_calls_depth_limit_if_repeat_parallel() -> None:
    """Guard: Verify service call depth limit applies to if/then, repeat, and parallel.

    This test ensures service call extraction respects depth limits across
    all branching structures (if/then, repeat, parallel), not just choose.

    See: test_max_recursion_depth_constant for architectural reasoning
    """
    analyzer = AutomationAnalyzer()

    # if/then nesting
    actions_if = [{"service": "light.turn_on", "target": {"entity_id": "light.if"}}]
    for _ in range(100):
        actions_if = [{"if": [], "then": actions_if}]
    auto_if = {"id": "deep_if", "alias": "X", "trigger": [], "action": actions_if}
    assert (
        len(
            [
                c
                for c in analyzer.extract_service_calls(auto_if)
                if c.service == "light.turn_on"
            ]
        )
        == 0
    )

    # repeat nesting
    actions_rpt = [{"service": "fan.turn_on", "target": {"entity_id": "fan.rpt"}}]
    for _ in range(100):
        actions_rpt = [{"repeat": {"count": 1, "sequence": actions_rpt}}]
    auto_rpt = {"id": "deep_rpt", "alias": "X", "trigger": [], "action": actions_rpt}
    assert (
        len(
            [
                c
                for c in analyzer.extract_service_calls(auto_rpt)
                if c.service == "fan.turn_on"
            ]
        )
        == 0
    )

    # parallel nesting
    actions_par = [{"service": "switch.toggle", "target": {"entity_id": "switch.par"}}]
    for _ in range(100):
        actions_par = [{"parallel": [actions_par]}]
    auto_par = {"id": "deep_par", "alias": "X", "trigger": [], "action": actions_par}
    assert (
        len(
            [
                c
                for c in analyzer.extract_service_calls(auto_par)
                if c.service == "switch.toggle"
            ]
        )
        == 0
    )


def test_get_entity_suggestion_importable_from_validator() -> None:
    """Guard: Ensure get_entity_suggestion is importable from validator module.

    This test protects the architectural decision to consolidate entity
    suggestion logic in the validator module after removing the fix_engine
    module. Prevents accidental re-introduction of the fix_engine or
    moving this function elsewhere.

    See: PROJECT.md "Key Decisions" - Module consolidation
    """
    # Basic smoke test - entity suggestion from validator
    all_entities = ["light.living_room", "light.bedroom", "switch.kitchen"]
    result = get_entity_suggestion("light.livingroom", all_entities)
    assert result == "light.living_room"


def test_websocket_api_imports_from_validator_not_fix_engine() -> None:
    """Guard: Prevent re-introduction of fix_engine module imports.

    This test protects the architectural decision to remove the fix_engine
    module and consolidate its functionality into validator. It ensures
    websocket_api imports get_entity_suggestion from validator, not from
    a resurrected fix_engine module.

    The fix_engine was removed because automatic fixes created more problems
    than they solved (users applying fixes without understanding implications).

    See: PROJECT.md "Key Decisions" - Removal of automatic fixes
    """
    with open(ws_mod.__file__) as f:
        source = ast.parse(f.read())

    imports = []
    for node in ast.walk(source):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.append((node.module, alias.name))

    # Should import from .validator
    assert any(
        "validator" in mod and name == "get_entity_suggestion" for mod, name in imports
    ), "websocket_api should import get_entity_suggestion from validator"

    # Should NOT import from .fix_engine
    assert not any("fix_engine" in mod for mod, name in imports), (
        "websocket_api should not import from fix_engine"
    )


@pytest.mark.asyncio
async def test_async_load_history_times_out_on_slow_recorder() -> None:
    """Guard: Verify async_load_history has internal timeout for slow recorder.

    This test protects the architectural decision to add timeout protection
    when loading history from the recorder. Without this timeout, a slow or
    hung recorder database could block the entire integration from loading.

    The history_timeout parameter ensures the integration remains responsive
    even when the recorder is under heavy load.

    See: PROJECT.md "Key Decisions" - Defensive timeout handling
    """
    mock_hass = MagicMock()
    mock_states = [MagicMock(entity_id="binary_sensor.test")]
    mock_hass.states.async_all.return_value = mock_states

    kb = StateKnowledgeBase(mock_hass, history_timeout=1)

    async def slow_executor_job(func: Any, *args: Any) -> Any:
        await asyncio.sleep(600)  # Simulates a very slow recorder
        return func(*args)

    mock_hass.async_add_executor_job = slow_executor_job

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        lambda *a, **kw: {},
    ):
        # Should complete without hanging - internal timeout should kick in
        try:
            await asyncio.wait_for(kb.async_load_history(), timeout=5)
        except TimeoutError:
            pytest.fail("async_load_history should have its own internal timeout")


def test_validation_issue_hash_includes_location() -> None:
    """Guard: Ensure ValidationIssue hash includes location field.

    This test protects the architectural decision to include location in
    the issue hash/equality check. Without this, duplicate issues at
    different locations in the same automation would be incorrectly
    deduplicated, hiding real problems from users.

    For example, if light.living_room is missing, and it's referenced in
    both the trigger and an action, users need to see both issues.

    See: PROJECT.md "Key Decisions" - Issue deduplication strategy
    """
    from custom_components.autodoctor.models import (
        IssueType,
        Severity,
        ValidationIssue,
    )

    issue_a = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.living_room",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue_b = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.living_room",
        location="action[2]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    # Same automation, entity, type, message - but different location
    assert hash(issue_a) != hash(issue_b)
    assert issue_a != issue_b


def test_validation_engine_has_invalidate_entity_cache() -> None:
    """Guard: Ensure ValidationEngine has invalidate_entity_cache method.

    This test protects the architectural decision to add cache invalidation
    support to ValidationEngine. Without this, the engine would continue
    using stale entity data after entities are added/removed/renamed,
    leading to false positives and false negatives.

    The cache is invalidated when entity registry changes are detected.

    See: test_init_registers_entity_registry_listener for the listener setup
    """
    from custom_components.autodoctor.validator import ValidationEngine

    mock_kb = MagicMock()
    engine = ValidationEngine(mock_kb)

    # Build the cache first
    mock_entity = MagicMock()
    mock_entity.entity_id = "light.test"
    mock_kb.hass.states.async_all.return_value = [mock_entity]
    engine._ensure_entity_cache()
    assert engine._entity_cache is not None

    # Invalidate should clear it
    engine.invalidate_entity_cache()
    assert engine._entity_cache is None


def test_init_registers_entity_registry_listener() -> None:
    """Guard: Ensure __init__.py registers entity registry change listener.

    This test protects the architectural decision to listen for entity
    registry changes and invalidate the ValidationEngine entity cache when
    entities are added, removed, or renamed.

    Without this listener, the validator would use stale entity lists,
    causing false positives (entities exist but validator says they don't)
    and false negatives (entities removed but validator says they're fine).

    See: PROJECT.md "Key Decisions" - Real-time entity tracking
    """
    import custom_components.autodoctor.__init__ as init_mod

    with open(init_mod.__file__) as f:
        source_text = f.read()
    ast.parse(source_text)

    # The init module should reference entity registry listener registration
    assert "async_track_entity_registry_updated_event" in source_text or (
        "entity_registry" in source_text and "invalidate_entity_cache" in source_text
    ), (
        "__init__.py should register an entity registry change listener that invalidates the entity cache"
    )


def test_init_cleans_up_entity_registry_listener_on_unload() -> None:
    """Guard: Ensure __init__.py cleans up entity registry listener on unload.

    This test protects against resource leaks by ensuring the entity registry
    listener is properly unsubscribed when the integration is unloaded.

    Without this cleanup, the listener would continue firing events and
    attempting to invalidate caches for an unloaded integration, causing
    memory leaks and potential errors.

    See: Home Assistant best practices - Proper cleanup in async_unload_entry
    """
    with open(
        __import__(
            "custom_components.autodoctor.__init__", fromlist=["__init__"]
        ).__file__
    ) as f:
        source_text = f.read()

    assert "unsub_entity_registry_listener" in source_text, (
        "__init__.py should store and clean up the entity registry listener unsub callback"
    )

    # Verify the unload function actually calls the unsub
    source = ast.parse(source_text)
    for node in ast.walk(source):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_unload_entry":
            body_text = ast.dump(node)
            assert (
                "unsub_entity_registry_listener" in body_text
                or "unsub_entity_reg" in body_text
            ), "async_unload_entry should clean up the entity registry listener"
            break
    else:
        pytest.fail("async_unload_entry function not found")
