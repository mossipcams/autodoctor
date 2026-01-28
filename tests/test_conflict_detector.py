"""Tests for conflict detector with trigger overlap awareness."""

from custom_components.autodoctor.conflict_detector import ConflictDetector
from custom_components.autodoctor.models import ConditionInfo, TriggerInfo


class TestConflictDetector:
    """Test ConflictDetector class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = ConflictDetector()

    def test_no_conflicts_when_no_automations(self):
        """Test that empty automation list returns no conflicts."""
        conflicts = self.detector.detect_conflicts([])
        assert conflicts == []

    def test_no_conflicts_same_action(self):
        """Test that same actions don't conflict."""
        automations = [
            {
                "id": "auto1",
                "trigger": [
                    {"platform": "state", "entity_id": "input_boolean.test", "to": "on"}
                ],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": "input_boolean.test2",
                        "to": "on",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0

    def test_conflict_detected_opposing_actions(self):
        """Test that opposing actions on same entity are detected."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "06:00:00"}],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "06:00:00"}],
                "action": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 1
        assert conflicts[0].entity_id == "light.living"
        assert {conflicts[0].action_a, conflicts[0].action_b} == {"turn_on", "turn_off"}

    def test_no_conflict_different_times(self):
        """Test that different trigger times don't conflict."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "06:00:00"}],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0

    def test_no_conflict_disjoint_state_triggers(self):
        """Test that disjoint state triggers don't conflict."""
        automations = [
            {
                "id": "auto1",
                "trigger": [
                    {"platform": "state", "entity_id": "input_boolean.mode", "to": "on"}
                ],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": "input_boolean.mode",
                        "to": "off",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0

    def test_no_conflict_mutually_exclusive_conditions(self):
        """Test that mutually exclusive conditions don't conflict."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "06:00:00"}],
                "condition": [
                    {
                        "condition": "state",
                        "entity_id": "input_boolean.mode",
                        "state": "on",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_on",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "06:00:00"}],
                "condition": [
                    {
                        "condition": "state",
                        "entity_id": "input_boolean.mode",
                        "state": "off",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0


class TestTriggerOverlap:
    """Test trigger overlap detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = ConflictDetector()

    def test_same_time_triggers_overlap(self):
        """Test that same time triggers overlap."""
        triggers_a = [TriggerInfo("time", None, None, "06:00:00", None)]
        triggers_b = [TriggerInfo("time", None, None, "06:00:00", None)]
        assert self.detector._triggers_can_overlap(triggers_a, triggers_b)

    def test_different_time_triggers_no_overlap(self):
        """Test that different time triggers don't overlap."""
        triggers_a = [TriggerInfo("time", None, None, "06:00:00", None)]
        triggers_b = [TriggerInfo("time", None, None, "22:00:00", None)]
        assert not self.detector._triggers_can_overlap(triggers_a, triggers_b)

    def test_same_sun_event_overlaps(self):
        """Test that same sun events overlap."""
        triggers_a = [TriggerInfo("sun", None, None, None, "sunrise")]
        triggers_b = [TriggerInfo("sun", None, None, None, "sunrise")]
        assert self.detector._triggers_can_overlap(triggers_a, triggers_b)

    def test_different_sun_events_no_overlap(self):
        """Test that different sun events don't overlap."""
        triggers_a = [TriggerInfo("sun", None, None, None, "sunrise")]
        triggers_b = [TriggerInfo("sun", None, None, None, "sunset")]
        assert not self.detector._triggers_can_overlap(triggers_a, triggers_b)

    def test_disjoint_state_triggers_no_overlap(self):
        """Test that disjoint state triggers don't overlap."""
        triggers_a = [TriggerInfo("state", "input_boolean.test", {"on"}, None, None)]
        triggers_b = [TriggerInfo("state", "input_boolean.test", {"off"}, None, None)]
        assert not self.detector._triggers_can_overlap(triggers_a, triggers_b)


class TestConditionExclusivity:
    """Test condition mutual exclusivity detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = ConflictDetector()

    def test_mutually_exclusive_states(self):
        """Test that different required states are mutually exclusive."""
        conds_a = [ConditionInfo("input_boolean.mode", {"on"})]
        conds_b = [ConditionInfo("input_boolean.mode", {"off"})]
        assert self.detector._conditions_mutually_exclusive(conds_a, conds_b)

    def test_overlapping_states_not_exclusive(self):
        """Test that overlapping states are not mutually exclusive."""
        conds_a = [ConditionInfo("input_select.mode", {"home", "away"})]
        conds_b = [ConditionInfo("input_select.mode", {"away", "vacation"})]
        assert not self.detector._conditions_mutually_exclusive(conds_a, conds_b)

    def test_different_entities_not_exclusive(self):
        """Test that different entities are not mutually exclusive."""
        conds_a = [ConditionInfo("input_boolean.mode1", {"on"})]
        conds_b = [ConditionInfo("input_boolean.mode2", {"off"})]
        assert not self.detector._conditions_mutually_exclusive(conds_a, conds_b)


class TestActionLevelConditions:
    """Test conflict detection with action-level conditions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = ConflictDetector()

    def test_no_conflict_with_mutually_exclusive_action_conditions(self):
        """Test that mutually exclusive action conditions prevent conflicts."""
        automations = [
            {
                "id": "night_on",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_boolean.mode",
                                        "state": "night",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_on",
                                        "target": {"entity_id": "light.living"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "day_off",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_boolean.mode",
                                        "state": "day",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_off",
                                        "target": {"entity_id": "light.living"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0

    def test_conflict_with_compatible_action_conditions(self):
        """Test that compatible action conditions still allow conflicts."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_boolean.mode",
                                        "state": "night",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_on",
                                        "target": {"entity_id": "light.living"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_boolean.mode",
                                        "state": "night",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_off",
                                        "target": {"entity_id": "light.living"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        ]
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 1

    def test_combined_automation_and_action_conditions(self):
        """Test that automation-level and action-level conditions combine."""
        automations = [
            {
                "id": "auto1",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "condition": [
                    {
                        "condition": "state",
                        "entity_id": "input_boolean.enabled",
                        "state": "on",
                    }
                ],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_boolean.mode",
                                        "state": "night",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_on",
                                        "target": {"entity_id": "light.living"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "auto2",
                "trigger": [{"platform": "time", "at": "22:00:00"}],
                "condition": [
                    {
                        "condition": "state",
                        "entity_id": "input_boolean.enabled",
                        "state": "off",
                    }
                ],
                "action": [
                    {
                        "service": "light.turn_off",
                        "target": {"entity_id": "light.living"},
                    }
                ],
            },
        ]
        # Automation-level conditions are mutually exclusive (enabled on vs off)
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0

    def test_real_world_scenario_mode_based_automation(self):
        """Test real-world scenario: mode-based automations don't conflict."""
        automations = [
            {
                "id": "morning_routine",
                "alias": "Morning Routine",
                "trigger": [{"platform": "time", "at": "07:00:00"}],
                "action": [
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_select.house_mode",
                                        "state": "home",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_on",
                                        "target": {"entity_id": "light.kitchen"},
                                    },
                                    {
                                        "service": "light.turn_on",
                                        "target": {"entity_id": "light.living_room"},
                                    },
                                ],
                            },
                            {
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "input_select.house_mode",
                                        "state": "away",
                                    }
                                ],
                                "sequence": [
                                    {
                                        "service": "light.turn_off",
                                        "target": {"entity_id": "light.kitchen"},
                                    },
                                    {
                                        "service": "light.turn_off",
                                        "target": {"entity_id": "light.living_room"},
                                    },
                                ],
                            },
                        ],
                    }
                ],
            },
        ]
        # Same automation with choose branches should not conflict with itself
        conflicts = self.detector.detect_conflicts(automations)
        assert len(conflicts) == 0
