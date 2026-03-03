"""Tests for reachability/contradiction validation."""

from custom_components.autodoctor.reachability_validator import ReachabilityValidator


def test_detects_state_trigger_condition_contradiction() -> None:
    """Trigger-to and condition-state contradictions on same entity are flagged."""
    automations = [
        {
            "id": "contradict_state",
            "alias": "Contradict State",
            "trigger": [
                {"platform": "state", "entity_id": "binary_sensor.door", "to": "on"}
            ],
            "condition": [
                {
                    "condition": "state",
                    "entity_id": "binary_sensor.door",
                    "state": "off",
                }
            ],
            "action": [],
        }
    ]

    issues = ReachabilityValidator().validate_automations(automations)

    assert len(issues) == 1
    assert "contradiction" in issues[0].message.lower()
    assert issues[0].automation_id == "automation.contradict_state"
    assert issues[0].entity_id == "binary_sensor.door"


def test_detects_impossible_numeric_range() -> None:
    """Numeric-state with below less than above is unreachable."""
    automations = [
        {
            "id": "contradict_numeric",
            "alias": "Contradict Numeric",
            "trigger": [
                {
                    "platform": "numeric_state",
                    "entity_id": "sensor.temperature",
                    "above": 30,
                    "below": 20,
                }
            ],
            "action": [],
        }
    ]

    issues = ReachabilityValidator().validate_automations(automations)

    assert len(issues) == 1
    assert "below" in issues[0].message
    assert "above" in issues[0].message
    assert issues[0].automation_id == "automation.contradict_numeric"
    assert issues[0].entity_id == "sensor.temperature"
