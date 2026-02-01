"""Tests for architectural improvements from the full review."""

import ast
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.const import (
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    DEFAULT_STRICT_SERVICE_VALIDATION,
    DEFAULT_STRICT_TEMPLATE_VALIDATION,
    MAX_RECURSION_DEPTH,
    STATE_VALIDATION_WHITELIST,
)
from custom_components.autodoctor.jinja_validator import JinjaValidator
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import (
    StateReference,
)
from custom_components.autodoctor.validator import get_entity_suggestion
import custom_components.autodoctor.websocket_api as ws_mod


def test_state_validation_whitelist_exists():
    """STATE_VALIDATION_WHITELIST should be importable from const."""
    assert isinstance(STATE_VALIDATION_WHITELIST, frozenset)
    assert "binary_sensor" in STATE_VALIDATION_WHITELIST
    assert "person" in STATE_VALIDATION_WHITELIST
    assert "sun" in STATE_VALIDATION_WHITELIST
    assert "device_tracker" in STATE_VALIDATION_WHITELIST
    assert "input_boolean" in STATE_VALIDATION_WHITELIST
    assert "group" in STATE_VALIDATION_WHITELIST
    # Dynamic domains should not be in the whitelist
    assert "sensor" not in STATE_VALIDATION_WHITELIST
    assert "light" not in STATE_VALIDATION_WHITELIST
    assert "switch" not in STATE_VALIDATION_WHITELIST


def test_strict_config_keys_exist():
    """Config keys for strict validation should exist in const."""
    assert CONF_STRICT_TEMPLATE_VALIDATION == "strict_template_validation"
    assert CONF_STRICT_SERVICE_VALIDATION == "strict_service_validation"
    assert DEFAULT_STRICT_TEMPLATE_VALIDATION is False
    assert DEFAULT_STRICT_SERVICE_VALIDATION is False


def test_max_recursion_depth_constant():
    """MAX_RECURSION_DEPTH should exist in const."""
    from custom_components.autodoctor.const import MAX_RECURSION_DEPTH

    assert MAX_RECURSION_DEPTH == 50


def test_extract_from_actions_enforces_depth_limit():
    """_extract_from_actions should stop recursing beyond MAX_RECURSION_DEPTH."""
    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    analyzer = AutomationAnalyzer()

    # Build automation with 100-level deep nesting (exceeds MAX_RECURSION_DEPTH of 50)
    # The innermost action has a service call with entity_id "light.deep"
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep"}}]
    for _ in range(100):
        actions = [{"choose": [{"conditions": [], "sequence": actions}]}]

    automation = {
        "id": "deep_actions",
        "alias": "Deep Actions",
        "trigger": [{"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}],
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


def test_extract_from_actions_depth_limit_if_then_else():
    """Depth limit should also apply to if/then/else nesting."""
    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    analyzer = AutomationAnalyzer()

    # Build 100-level deep nesting using if/then
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep_if"}}]
    for _ in range(100):
        actions = [{"if": [], "then": actions}]

    automation = {
        "id": "deep_if",
        "alias": "Deep If",
        "trigger": [{"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    deep_refs = [r for r in refs if r.entity_id == "light.deep_if"]
    assert len(deep_refs) == 0


def test_extract_from_actions_depth_limit_repeat():
    """Depth limit should also apply to repeat nesting."""
    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    analyzer = AutomationAnalyzer()

    # Build 100-level deep nesting using repeat/sequence
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep_repeat"}}]
    for _ in range(100):
        actions = [{"repeat": {"count": 1, "sequence": actions}}]

    automation = {
        "id": "deep_repeat",
        "alias": "Deep Repeat",
        "trigger": [{"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    deep_refs = [r for r in refs if r.entity_id == "light.deep_repeat"]
    assert len(deep_refs) == 0


def test_extract_from_actions_depth_limit_parallel():
    """Depth limit should also apply to parallel nesting."""
    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    analyzer = AutomationAnalyzer()

    # Build 100-level deep nesting using parallel branches
    actions = [{"service": "light.turn_on", "target": {"entity_id": "light.deep_parallel"}}]
    for _ in range(100):
        actions = [{"parallel": [actions]}]

    automation = {
        "id": "deep_parallel",
        "alias": "Deep Parallel",
        "trigger": [{"platform": "state", "entity_id": "binary_sensor.test", "to": "on"}],
        "action": actions,
    }

    refs = analyzer.extract_state_references(automation)
    deep_refs = [r for r in refs if r.entity_id == "light.deep_parallel"]
    assert len(deep_refs) == 0


def test_extract_service_calls_enforces_depth_limit():
    """extract_service_calls should also enforce depth limit."""
    from custom_components.autodoctor.analyzer import AutomationAnalyzer

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


def test_extract_service_calls_depth_limit_if_repeat_parallel():
    """Service call depth limit should apply to if/then, repeat, and parallel branches."""
    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    analyzer = AutomationAnalyzer()

    # if/then nesting
    actions_if = [{"service": "light.turn_on", "target": {"entity_id": "light.if"}}]
    for _ in range(100):
        actions_if = [{"if": [], "then": actions_if}]
    auto_if = {"id": "deep_if", "alias": "X", "trigger": [], "action": actions_if}
    assert len([c for c in analyzer.extract_service_calls(auto_if) if c.service == "light.turn_on"]) == 0

    # repeat nesting
    actions_rpt = [{"service": "fan.turn_on", "target": {"entity_id": "fan.rpt"}}]
    for _ in range(100):
        actions_rpt = [{"repeat": {"count": 1, "sequence": actions_rpt}}]
    auto_rpt = {"id": "deep_rpt", "alias": "X", "trigger": [], "action": actions_rpt}
    assert len([c for c in analyzer.extract_service_calls(auto_rpt) if c.service == "fan.turn_on"]) == 0

    # parallel nesting
    actions_par = [{"service": "switch.toggle", "target": {"entity_id": "switch.par"}}]
    for _ in range(100):
        actions_par = [{"parallel": [actions_par]}]
    auto_par = {"id": "deep_par", "alias": "X", "trigger": [], "action": actions_par}
    assert len([c for c in analyzer.extract_service_calls(auto_par) if c.service == "switch.toggle"]) == 0


def test_get_entity_suggestion_importable_from_validator():
    """get_entity_suggestion should be importable from validator module."""
    from custom_components.autodoctor.validator import get_entity_suggestion

    # Basic smoke test — entity suggestion from validator
    all_entities = ["light.living_room", "light.bedroom", "switch.kitchen"]
    result = get_entity_suggestion("light.livingroom", all_entities)
    assert result == "light.living_room"


def test_websocket_api_imports_from_validator_not_fix_engine():
    """websocket_api imports get_entity_suggestion from validator (not the removed fix_engine module)."""
    import ast

    import custom_components.autodoctor.websocket_api as ws_mod
    source = ast.parse(open(ws_mod.__file__).read())

    imports = []
    for node in ast.walk(source):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.append((node.module, alias.name))

    # Should import from .validator
    assert any(
        "validator" in mod and name == "get_entity_suggestion"
        for mod, name in imports
    ), "websocket_api should import get_entity_suggestion from validator"

    # Should NOT import from .fix_engine
    assert not any(
        "fix_engine" in mod
        for mod, name in imports
    ), "websocket_api should not import from fix_engine"


@pytest.mark.asyncio
async def test_async_load_history_times_out_on_slow_recorder():
    """async_load_history should timeout if recorder is too slow."""
    import asyncio

    mock_hass = MagicMock()
    mock_states = [MagicMock(entity_id="binary_sensor.test")]
    mock_hass.states.async_all.return_value = mock_states

    kb = StateKnowledgeBase(mock_hass, history_timeout=1)

    async def slow_executor_job(func, *args):
        await asyncio.sleep(600)  # Simulates a very slow recorder
        return func(*args)

    mock_hass.async_add_executor_job = slow_executor_job

    with patch(
        "custom_components.autodoctor.knowledge_base.get_significant_states",
        lambda *a, **kw: {},
    ):
        # Should complete without hanging — internal timeout should kick in
        try:
            await asyncio.wait_for(kb.async_load_history(), timeout=5)
        except asyncio.TimeoutError:
            pytest.fail("async_load_history should have its own internal timeout")


def test_validation_issue_hash_includes_location():
    """Two issues differing only in location should have different hashes."""
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

    # Same automation, entity, type, message — but different location
    assert hash(issue_a) != hash(issue_b)
    assert issue_a != issue_b


def test_validation_engine_has_invalidate_entity_cache():
    """ValidationEngine should have an invalidate_entity_cache method."""
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


def test_init_registers_entity_registry_listener():
    """__init__.py should register an entity registry change listener."""
    import ast

    import custom_components.autodoctor.__init__ as init_mod

    source = ast.parse(open(init_mod.__file__).read())
    source_text = open(init_mod.__file__).read()

    # The init module should reference entity registry listener registration
    assert "async_track_entity_registry_updated_event" in source_text or \
           "entity_registry" in source_text and "invalidate_entity_cache" in source_text, \
        "__init__.py should register an entity registry change listener that invalidates the entity cache"


def test_init_cleans_up_entity_registry_listener_on_unload():
    """__init__.py should unsubscribe the entity registry listener on unload."""
    source_text = open(
        __import__("custom_components.autodoctor.__init__", fromlist=["__init__"]).__file__
    ).read()

    assert "unsub_entity_registry_listener" in source_text, \
        "__init__.py should store and clean up the entity registry listener unsub callback"

    # Verify the unload function actually calls the unsub
    import ast
    source = ast.parse(source_text)
    for node in ast.walk(source):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_unload_entry":
            body_text = ast.dump(node)
            assert "unsub_entity_registry_listener" in body_text or \
                   "unsub_entity_reg" in body_text, \
                "async_unload_entry should clean up the entity registry listener"
            break
    else:
        pytest.fail("async_unload_entry function not found")
