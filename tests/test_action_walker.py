"""Tests for shared action traversal walker."""

from __future__ import annotations


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

    condition_locations: list[str] = []

    def on_action(action: dict, idx: int, location: str) -> None:
        pass

    def on_condition(condition: dict, idx: int, location: str) -> None:
        condition_locations.append(location)

    actions = [
        {
            "choose": [
                {
                    "conditions": [{"condition": "state"}],
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
    assert "action[0].choose[0].conditions[0]" in condition_locations
    assert "action[1].if[0]" in condition_locations
    assert "action[2].repeat.while[0]" in condition_locations


def test_analyzer_extract_service_calls_uses_walk_automation_actions() -> None:
    """_extract_service_calls_from_actions should not contain its own recursion."""
    import inspect

    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    source = inspect.getsource(AutomationAnalyzer._extract_service_calls_from_actions)
    # Should not contain structural recursion keywords anymore
    assert "choose" not in source, (
        "_extract_service_calls_from_actions should delegate to walk_automation_actions"
    )


def test_analyzer_extract_from_actions_uses_walk_automation_actions() -> None:
    """_extract_from_actions should not contain its own recursion."""
    import inspect

    from custom_components.autodoctor.analyzer import AutomationAnalyzer

    source = inspect.getsource(AutomationAnalyzer._extract_from_actions)
    assert '"parallel"' not in source, (
        "_extract_from_actions should delegate to walk_automation_actions"
    )


def test_jinja_validator_validate_actions_uses_walk_automation_actions() -> None:
    """_validate_actions should not contain its own recursion."""
    import inspect

    from custom_components.autodoctor.jinja_validator import JinjaValidator

    source = inspect.getsource(JinjaValidator._validate_actions)
    assert '"parallel"' not in source, (
        "_validate_actions should delegate to walk_automation_actions"
    )
