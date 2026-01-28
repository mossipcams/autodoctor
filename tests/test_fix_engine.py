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


def test_smart_entity_suggestion_same_area():
    """Test entity suggestions prefer same area."""
    from custom_components.autodoctor.fix_engine import FixEngine
    from custom_components.autodoctor.entity_graph import EntityGraph
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner
    from custom_components.autodoctor.models import ValidationIssue, IssueType, Severity
    from unittest.mock import MagicMock

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

    fix = engine.suggest_fix(issue)

    assert fix is not None
    assert fix.fix_value == "light.kitchen_main"  # Should prefer kitchen due to string similarity


def test_suggestion_penalized_after_rejection():
    """Test suggestions are penalized after rejection."""
    from custom_components.autodoctor.fix_engine import FixEngine
    from custom_components.autodoctor.entity_graph import EntityGraph
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner
    from custom_components.autodoctor.models import ValidationIssue, IssueType, Severity
    from unittest.mock import MagicMock

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


def test_fix_suggestion_has_reasoning():
    """Test that fix suggestions include reasoning."""
    from custom_components.autodoctor.fix_engine import FixEngine
    from custom_components.autodoctor.entity_graph import EntityGraph
    from custom_components.autodoctor.suggestion_learner import SuggestionLearner
    from custom_components.autodoctor.models import ValidationIssue, IssueType, Severity
    from unittest.mock import MagicMock

    hass = MagicMock()
    hass.states.async_all.return_value = [
        MagicMock(entity_id="light.living_room"),
    ]

    kb = MagicMock()
    entity_graph = EntityGraph()
    learner = SuggestionLearner()

    engine = FixEngine(hass, kb, entity_graph, learner)

    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.living_rom",  # Typo
        location="trigger[0]",
        message="Entity not found: light.living_rom",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    fix = engine.suggest_fix(issue)

    assert fix is not None
    assert fix.reasoning is not None  # Should have reasoning field
