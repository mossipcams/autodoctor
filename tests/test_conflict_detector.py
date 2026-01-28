"""Tests for ConflictDetector."""

import pytest
from custom_components.autodoctor.conflict_detector import ConflictDetector
from custom_components.autodoctor.models import Severity


def test_detect_on_off_conflict():
    """Test detection of turn_on vs turn_off conflict."""
    automations = [
        {
            "id": "motion_lights",
            "alias": "Motion Lights",
            "trigger": [{"platform": "state", "entity_id": "binary_sensor.motion", "to": "on"}],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "away_mode",
            "alias": "Away Mode",
            "trigger": [{"platform": "state", "entity_id": "person.matt", "to": "not_home"}],
            "action": [{"service": "light.turn_off", "target": {"entity_id": "light.living_room"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 1
    assert conflicts[0].entity_id == "light.living_room"
    assert conflicts[0].severity == Severity.ERROR
    assert "turn_on" in conflicts[0].action_a or "turn_on" in conflicts[0].action_b
    assert "turn_off" in conflicts[0].action_a or "turn_off" in conflicts[0].action_b


def test_no_conflict_different_entities():
    """Test no conflict when different entities."""
    automations = [
        {
            "id": "motion_lights",
            "alias": "Motion Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "away_mode",
            "alias": "Away Mode",
            "trigger": [],
            "action": [{"service": "light.turn_off", "target": {"entity_id": "light.kitchen"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 0


def test_toggle_warning():
    """Test toggle generates warning."""
    automations = [
        {
            "id": "toggle_lights",
            "alias": "Toggle Lights",
            "trigger": [],
            "action": [{"service": "light.toggle", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "turn_on_lights",
            "alias": "Turn On Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 1
    assert conflicts[0].severity == Severity.WARNING


def test_no_conflict_same_action():
    """Test no conflict when both do same action."""
    automations = [
        {
            "id": "motion_lights",
            "alias": "Motion Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
        {
            "id": "door_lights",
            "alias": "Door Lights",
            "trigger": [],
            "action": [{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 0


def test_multiple_conflicts():
    """Test detection of multiple conflicts."""
    automations = [
        {
            "id": "auto1",
            "alias": "Auto 1",
            "trigger": [],
            "action": [
                {"service": "light.turn_on", "target": {"entity_id": "light.living_room"}},
                {"service": "light.turn_on", "target": {"entity_id": "light.kitchen"}},
            ],
        },
        {
            "id": "auto2",
            "alias": "Auto 2",
            "trigger": [],
            "action": [
                {"service": "light.turn_off", "target": {"entity_id": "light.living_room"}},
                {"service": "light.turn_off", "target": {"entity_id": "light.kitchen"}},
            ],
        },
    ]

    detector = ConflictDetector()
    conflicts = detector.detect_conflicts(automations)

    assert len(conflicts) == 2
    entity_ids = {c.entity_id for c in conflicts}
    assert entity_ids == {"light.living_room", "light.kitchen"}
