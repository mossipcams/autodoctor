"""Precision recall corpus: flag real defects, never false positives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import label_registry as lr

from custom_components.autodoctor.analyzer import AutomationAnalyzer
from custom_components.autodoctor.knowledge_base import StateKnowledgeBase
from custom_components.autodoctor.models import IssueType
from custom_components.autodoctor.reachability_validator import ReachabilityValidator
from custom_components.autodoctor.service_validator import ServiceCallValidator
from custom_components.autodoctor.validator import ValidationEngine

FIXTURES = Path(__file__).parent / "fixtures" / "precision"
MUST_FLAG = FIXTURES / "must_flag"
MUST_NOT_FLAG = FIXTURES / "must_not_flag"


def _load_automation(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    return data


def _collect_issues(
    hass: HomeAssistant,
    automation: dict[str, Any],
    *,
    tags_available: bool = False,
) -> list[Any]:
    """Run the same high-confidence validators used in production scans."""
    hass.states.async_set("light.kitchen", "off")
    hass.states.async_set("binary_sensor.motion_kitchen", "off")
    hass.services.async_register("light", "turn_on", lambda *a, **k: None)
    hass.services.async_register("light", "turn_off", lambda *a, **k: None)
    hass.services.async_register(
        "persistent_notification", "create", lambda *a, **k: None
    )

    label_reg = lr.async_get(hass)
    if label_reg.async_get_label("precision_label") is None:
        label_reg.async_create("Precision Label")
    floor_reg = fr.async_get(hass)
    if floor_reg.async_get_floor("precision_floor") is None:
        floor_reg.async_create("Precision Floor")

    if tags_available:
        hass.data["tag"] = _FakeTagStore({"known_tag"})

    analyzer = AutomationAnalyzer()
    kb = StateKnowledgeBase(hass)
    entity_validator = ValidationEngine(kb)
    service_validator = ServiceCallValidator(hass)
    service_validator._service_descriptions = {
        "light": {
            "turn_on": {"fields": {}},
            "turn_off": {"fields": {}},
        },
        "persistent_notification": {"create": {"fields": {}}},
    }
    reachability = ReachabilityValidator()

    refs = analyzer.extract_state_references(automation)
    issues = list(entity_validator.validate_all(refs))
    calls = analyzer.extract_service_calls(automation)
    issues.extend(service_validator.validate_service_calls(calls))
    issues.extend(reachability.validate_automations([automation]))
    return issues


class _FakeTagStore:
    """Minimal stand-in for TagStorageCollection used in tests."""

    def __init__(self, tag_ids: set[str]) -> None:
        self._items = {tag_id: {"id": tag_id} for tag_id in tag_ids}

    def async_items(self) -> dict[str, dict[str, str]]:
        return self._items


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture_path",
    sorted(MUST_FLAG.glob("*.yaml")),
    ids=lambda p: p.stem,
)
async def test_must_flag_fixtures(hass: HomeAssistant, fixture_path: Path) -> None:
    """Broken literal refs in the corpus must produce at least one issue."""
    automation = _load_automation(fixture_path)
    tags_available = fixture_path.stem == "missing_tag_trigger"
    issues = _collect_issues(hass, automation, tags_available=tags_available)
    assert issues, f"Expected issues for {fixture_path.name}, got none"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture_path",
    sorted(MUST_NOT_FLAG.glob("*.yaml")),
    ids=lambda p: p.stem,
)
async def test_must_not_flag_fixtures(hass: HomeAssistant, fixture_path: Path) -> None:
    """Healthy / ambiguous cases must stay clean (precision gate)."""
    automation = _load_automation(fixture_path)
    issues = _collect_issues(hass, automation)
    assert issues == [], (
        f"False positives in {fixture_path.name}: "
        f"{[(i.issue_type, i.message) for i in issues]}"
    )


@pytest.mark.asyncio
async def test_missing_label_and_floor_produce_service_target_issues(
    hass: HomeAssistant,
) -> None:
    """Service targets with unknown label/floor IDs are flagged."""
    hass.services.async_register("light", "turn_on", lambda *a, **k: None)
    validator = ServiceCallValidator(hass)
    validator._service_descriptions = {"light": {"turn_on": {"fields": {}}}}

    from custom_components.autodoctor.models import ServiceCall

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="light.turn_on",
        location="action[0]",
        target={
            "label_id": "missing_label",
            "floor_id": "missing_floor",
        },
    )
    issues = validator.validate_service_calls([call])
    target_issues = [
        i for i in issues if i.issue_type == IssueType.SERVICE_TARGET_NOT_FOUND
    ]
    assert len(target_issues) == 2
    by_id = {i.entity_id: i.message for i in target_issues}
    assert "Label" in by_id["missing_label"]
    assert "Floor" in by_id["missing_floor"]


def test_analyzer_extracts_label_and_floor_from_target() -> None:
    """Analyzer tags label_id/floor_id refs for registry validation."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "labelfloor",
        "alias": "Label Floor",
        "action": [
            {
                "service": "light.turn_on",
                "target": {"label_id": "kids", "floor_id": "upstairs"},
            }
        ],
    }
    refs = analyzer.extract_state_references(automation)
    label_refs = [r for r in refs if r.reference_type == "label"]
    floor_refs = [r for r in refs if r.reference_type == "floor"]
    assert len(label_refs) == 1
    assert label_refs[0].entity_id == "kids"
    assert len(floor_refs) == 1
    assert floor_refs[0].entity_id == "upstairs"


def test_analyzer_extracts_time_pattern_and_sentence_device() -> None:
    """time_pattern is recognized; sentence device_id is extracted when literal."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "triggers",
        "alias": "Triggers",
        "trigger": [
            {"platform": "time_pattern", "hours": "/1"},
            {
                "platform": "sentence",
                "command": "turn on lights",
                "device_id": "assist1",
            },
            {"platform": "conversation", "command": "hello", "device_id": "assist2"},
        ],
        "action": [],
    }
    refs = analyzer.extract_state_references(automation)
    device_refs = [r for r in refs if r.reference_type == "device"]
    assert {r.entity_id for r in device_refs} == {"assist1", "assist2"}


def test_analyzer_extracts_states_bracket_notation() -> None:
    """states.domain['entity'] literals are extracted for existence checks."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "bracket",
        "alias": "Bracket",
        "trigger": [
            {
                "platform": "template",
                "value_template": "{{ states.light['kitchen_missing'].state == 'on' }}",
            }
        ],
        "action": [],
    }
    refs = analyzer.extract_state_references(automation)
    assert any(r.entity_id == "light.kitchen_missing" for r in refs)


def test_single_trigger_condition_contradiction_is_flagged() -> None:
    """Single state trigger contradicted by top-level condition is unreachable."""
    automation = _load_automation(MUST_FLAG / "trigger_condition_contradiction.yaml")
    issues = ReachabilityValidator().validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.UNREACHABLE_STATE_COMBINATION


def test_or_triggers_do_not_create_global_contradiction() -> None:
    """Conflicting OR trigger paths must not be treated as always-true facts."""
    automation = _load_automation(
        MUST_NOT_FLAG / "or_triggers_not_global_contradiction.yaml"
    )
    issues = ReachabilityValidator().validate_automations([automation])
    assert issues == []


@pytest.mark.asyncio
async def test_tag_skip_when_registry_unavailable(hass: HomeAssistant) -> None:
    """Without tag storage, tag refs are skipped with telemetry."""
    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)
    from custom_components.autodoctor.models import StateReference

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="some_tag",
        expected_state=None,
        expected_attribute=None,
        location="trigger[0].tag_id",
        reference_type="tag",
    )
    issues = validator.validate_all([ref])
    assert issues == []
    stats = validator.get_last_run_stats()
    assert stats["skip_reasons"].get("tags.registry_unavailable", 0) >= 1


@pytest.mark.asyncio
async def test_tag_missing_when_registry_available(hass: HomeAssistant) -> None:
    """With tag storage present, unknown tag IDs are flagged."""
    hass.data["tag"] = _FakeTagStore({"known_tag"})
    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)
    from custom_components.autodoctor.models import StateReference

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="missing_tag",
        expected_state=None,
        expected_attribute=None,
        location="trigger[0].tag_id",
        reference_type="tag",
    )
    issues = validator.validate_all([ref])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.ENTITY_NOT_FOUND
    assert "Tag" in issues[0].message


@pytest.mark.asyncio
async def test_templated_tag_skipped_even_with_registry(hass: HomeAssistant) -> None:
    """Templated tag IDs must not be validated as literals."""
    hass.data["tag"] = _FakeTagStore({"known_tag"})
    kb = StateKnowledgeBase(hass)
    validator = ValidationEngine(kb)
    from custom_components.autodoctor.models import StateReference

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="{{ tag_id }}",
        expected_state=None,
        expected_attribute=None,
        location="trigger[0].tag_id",
        reference_type="tag",
    )
    issues = validator.validate_all([ref])
    assert issues == []
    assert validator.get_last_run_stats()["skip_reasons"].get("tags.templated", 0) >= 1


def test_analyzer_skips_templated_tag_and_jinja_label() -> None:
    """Analyzer must not extract templated tag/label/floor refs."""
    analyzer = AutomationAnalyzer()
    automation = {
        "id": "templated_refs",
        "alias": "Templated Refs",
        "trigger": [{"platform": "tag", "tag_id": "{{ tag_id }}"}],
        "action": [
            {
                "service": "light.turn_on",
                "target": {
                    "label_id": "{% set x = 'kids' %}{{ x }}",
                    "floor_id": "{% if true %}upstairs{% endif %}",
                },
            }
        ],
    }
    refs = analyzer.extract_state_references(automation)
    assert [r for r in refs if r.reference_type == "tag"] == []
    assert [r for r in refs if r.reference_type == "label"] == []
    assert [r for r in refs if r.reference_type == "floor"] == []
