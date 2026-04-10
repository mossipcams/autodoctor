"""Tests for shared action traversal walker."""

from __future__ import annotations


def _nested_choose_action(
    depth: int, leaf_action: dict[str, str]
) -> list[dict[str, object]]:
    action: dict[str, object] = leaf_action
    for _ in range(depth):
        action = {"choose": [{"sequence": [action]}]}
    return [action]


def test_walk_automation_actions_visits_leaf_actions() -> None:
    """walk_automation_actions should call visit_action for each action dict."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    visited: list[tuple[int, str]] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        visited.append((idx, location))

    actions = [
        {"service": "light.turn_on"},
        {"service": "switch.turn_off"},
    ]
    walk_automation_actions(actions, visit_action=on_action)
    assert visited == [(0, "action[0]"), (1, "action[1]")]


def test_walk_recurses_into_choose_sequence_and_default() -> None:
    """Walker should recurse into choose option sequences and default."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    locations: list[str] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        locations.append(location)

    actions = [
        {
            "choose": [
                {"sequence": [{"service": "light.turn_on"}]},
            ],
            "default": [{"service": "switch.turn_off"}],
        },
    ]
    walk_automation_actions(actions, visit_action=on_action)
    assert "action[0]" in locations  # the choose action itself
    assert "action[0].choose[0].sequence[0]" in locations
    assert "action[0].default[0]" in locations


def test_walk_recurses_into_if_then_else() -> None:
    """Walker should recurse into if/then/else branches."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    locations: list[str] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        locations.append(location)

    actions = [
        {
            "if": [{"condition": "state"}],
            "then": [{"service": "light.turn_on"}],
            "else": [{"service": "light.turn_off"}],
        },
    ]
    walk_automation_actions(actions, visit_action=on_action)
    assert "action[0]" in locations
    assert "action[0].then[0]" in locations
    assert "action[0].else[0]" in locations


def test_walk_recurses_into_repeat_sequence() -> None:
    """Walker should recurse into repeat block sequences."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    locations: list[str] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        locations.append(location)

    actions = [
        {
            "repeat": {
                "count": 3,
                "sequence": [{"service": "light.toggle"}],
            },
        },
    ]
    walk_automation_actions(actions, visit_action=on_action)
    assert "action[0]" in locations
    assert "action[0].repeat.sequence[0]" in locations


def test_walk_recurses_into_parallel_branches() -> None:
    """Walker should recurse into parallel branch actions."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    locations: list[str] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        locations.append(location)

    actions = [
        {
            "parallel": [
                [{"service": "light.turn_on"}],
                {"service": "switch.turn_off"},
            ],
        },
    ]
    walk_automation_actions(actions, visit_action=on_action)
    assert "action[0]" in locations
    assert "action[0].parallel[0][0]" in locations
    assert "action[0].parallel[1][0]" in locations


def test_walk_respects_max_depth() -> None:
    """Walker should stop recursing when max_depth is reached."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    locations: list[str] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        locations.append(location)

    # Nest choose 3 levels deep, but set max_depth=2
    actions = [
        {
            "choose": [
                {
                    "sequence": [
                        {
                            "choose": [
                                {
                                    "sequence": [
                                        {"service": "light.turn_on"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    walk_automation_actions(actions, visit_action=on_action, max_depth=2)
    # depth 0: action[0] (choose)
    # depth 1: action[0].choose[0].sequence[0] (inner choose)
    # depth 2: would be the leaf, but max_depth=2 stops at depth >= 2
    assert "action[0]" in locations
    assert "action[0].choose[0].sequence[0]" in locations
    assert not any("light.turn_on" in loc for loc in locations)
    # The innermost leaf should NOT be visited
    deep_locations = [loc for loc in locations if loc.count(".") >= 4]
    assert deep_locations == []


def test_walk_calls_visit_condition_for_choose_and_if_and_repeat() -> None:
    """Walker should call visit_condition for conditions in choose, if, repeat."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    condition_calls: list[tuple[int, str]] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        pass

    def on_condition(condition: dict, idx: int, location: str) -> None:
        condition_calls.append((idx, location))

    actions = [
        {
            "choose": [
                {
                    "conditions": [
                        {"condition": "state"},
                        {"condition": "template"},
                    ],
                    "sequence": [],
                },
            ],
        },
        {
            "if": [{"condition": "template"}],
            "then": [],
        },
        {
            "repeat": {
                "while": [{"condition": "numeric_state"}],
                "sequence": [],
            },
        },
    ]
    walk_automation_actions(
        actions, visit_action=on_action, visit_condition=on_condition
    )
    assert condition_calls == [
        (0, "action[0].choose[0].conditions[0]"),
        (1, "action[0].choose[0].conditions[1]"),
        (0, "action[1].if[0]"),
        (0, "action[2].repeat.while[0]"),
    ]


def test_walk_calls_visit_trigger_for_wait_for_trigger() -> None:
    """Walker should call visit_trigger for wait_for_trigger entries."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    trigger_calls: list[tuple[int, str, str]] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        pass

    def on_trigger(trigger: dict, idx: int, location: str) -> None:
        trigger_calls.append((idx, location, str(trigger.get("platform"))))

    actions = [
        {
            "wait_for_trigger": [
                {
                    "platform": "state",
                    "entity_id": "binary_sensor.door",
                    "to": "on",
                },
                {
                    "platform": "template",
                    "value_template": "{{ is_state('switch.kettle', 'on') }}",
                },
            ]
        }
    ]

    walk_automation_actions(actions, visit_action=on_action, visit_trigger=on_trigger)

    assert trigger_calls == [
        (0, "action[0].wait_for_trigger[0]", "state"),
        (1, "action[0].wait_for_trigger[1]", "template"),
    ]


def test_walk_propagates_visit_condition_into_nested_branches() -> None:
    """Nested branch actions should keep visit_condition wired through recursion."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    condition_calls: list[tuple[int, str]] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        pass

    def on_condition(condition: dict, idx: int, location: str) -> None:
        condition_calls.append((idx, location))

    actions = [
        {
            "choose": [{"sequence": [{"if": [{"condition": "state"}], "then": []}]}],
            "default": [{"if": [{"condition": "template"}], "then": []}],
        },
        {
            "if": [{"condition": "state"}],
            "then": [
                {
                    "choose": [
                        {
                            "conditions": [{"condition": "numeric_state"}],
                            "sequence": [],
                        }
                    ]
                }
            ],
            "else": [{"if": [{"condition": "template"}], "then": []}],
        },
        {
            "repeat": {
                "sequence": [{"if": [{"condition": "state"}], "then": []}],
            }
        },
        {
            "parallel": [
                [{"if": [{"condition": "state"}], "then": []}],
                [
                    {
                        "repeat": {
                            "until": [{"condition": "numeric_state"}],
                            "sequence": [],
                        }
                    }
                ],
            ]
        },
    ]

    walk_automation_actions(
        actions, visit_action=on_action, visit_condition=on_condition
    )

    assert condition_calls == [
        (0, "action[0].choose[0].sequence[0].if[0]"),
        (0, "action[0].default[0].if[0]"),
        (0, "action[1].if[0]"),
        (0, "action[1].then[0].choose[0].conditions[0]"),
        (0, "action[1].else[0].if[0]"),
        (0, "action[2].repeat.sequence[0].if[0]"),
        (0, "action[3].parallel[0][0].if[0]"),
        (0, "action[3].parallel[1][0].repeat.until[0]"),
    ]


def test_ensure_list_is_public_export() -> None:
    """action_walker should export ensure_list as a public helper."""
    from custom_components.autodoctor.action_walker import ensure_list

    assert ensure_list(None) == []
    assert ensure_list("a") == ["a"]
    assert ensure_list([1, 2]) == [1, 2]


def test_condition_location_is_public_export() -> None:
    """action_walker should export condition_location as a public helper."""
    from custom_components.autodoctor.action_walker import condition_location

    assert condition_location("condition", 0) == "condition[0]"
    assert condition_location("condition[0]", 0) == "condition[0]"
    assert condition_location("condition[0]", 1) == "condition[0][1]"


def test_walk_automation_actions_default_max_depth_stops_before_depth_50() -> None:
    """The public default max_depth should stop before visiting depth-50 leaf actions."""
    from custom_components.autodoctor.action_walker import walk_automation_actions

    actions = _nested_choose_action(50, {"service": "light.turn_on"})
    default_leaf_locations: list[str] = []
    deeper_leaf_locations: list[str] = []

    def on_default_action(action: dict, idx: int, location: str) -> None:
        if action.get("service") == "light.turn_on":
            default_leaf_locations.append(location)

    def on_deeper_action(action: dict, idx: int, location: str) -> None:
        if action.get("service") == "light.turn_on":
            deeper_leaf_locations.append(location)

    walk_automation_actions(actions, visit_action=on_default_action)
    walk_automation_actions(actions, visit_action=on_deeper_action, max_depth=51)

    expected_leaf_location = "action[0]" + ".choose[0].sequence[0]" * 50
    assert default_leaf_locations == []
    assert deeper_leaf_locations == [expected_leaf_location]
