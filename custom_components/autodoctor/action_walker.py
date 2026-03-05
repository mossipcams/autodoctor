"""Shared recursive action traversal for automation configs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast


def walk_automation_actions(
    actions: list[dict[str, Any]],
    *,
    visit_action: Callable[[dict[str, Any], int, str], None],
    visit_condition: Callable[[dict[str, Any], int, str], None] | None = None,
    location_prefix: str = "action",
    max_depth: int = 50,
) -> None:
    """Walk automation actions, calling visit_action for each leaf action."""
    _walk(
        actions,
        visit_action=visit_action,
        visit_condition=visit_condition,
        location_prefix=location_prefix,
        max_depth=max_depth,
        _depth=0,
    )


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return cast(list[Any], value)
    if value is None:
        return []
    return [value]


def _visit_conditions(
    conditions: Any,
    visit_condition: Callable[[dict[str, Any], int, str], None],
    location_prefix: str,
) -> None:
    for cond_idx, cond in enumerate(_ensure_list(conditions)):
        if isinstance(cond, dict):
            visit_condition(cond, cond_idx, f"{location_prefix}[{cond_idx}]")


def _walk(
    actions: list[dict[str, Any]],
    *,
    visit_action: Callable[[dict[str, Any], int, str], None],
    visit_condition: Callable[[dict[str, Any], int, str], None] | None,
    location_prefix: str,
    max_depth: int,
    _depth: int,
) -> None:
    if _depth >= max_depth:
        return
    for idx, action in enumerate(actions):
        if not isinstance(action, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            continue
        location = f"{location_prefix}[{idx}]"
        visit_action(action, idx, location)

        if "choose" in action:
            options = cast(list[Any], action.get("choose") or [])
            if isinstance(options, list):  # pyright: ignore[reportUnnecessaryIsInstance]
                for opt_idx, option in enumerate(options):
                    if isinstance(option, dict):
                        if visit_condition:
                            _visit_conditions(
                                option.get("conditions"),
                                visit_condition,
                                f"{location}.choose[{opt_idx}].conditions",
                            )
                        sequence = cast(list[Any], option.get("sequence") or [])
                        _walk(
                            sequence,
                            visit_action=visit_action,
                            visit_condition=visit_condition,
                            location_prefix=f"{location}.choose[{opt_idx}].sequence",
                            max_depth=max_depth,
                            _depth=_depth + 1,
                        )
            default = action.get("default") or cast(list[Any], [])
            if isinstance(default, list) and default:
                _walk(
                    default,
                    visit_action=visit_action,
                    visit_condition=visit_condition,
                    location_prefix=f"{location}.default",
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )

        if "if" in action:
            if visit_condition:
                _visit_conditions(
                    action.get("if"),
                    visit_condition,
                    f"{location}.if",
                )
            then_actions = action.get("then") or cast(list[Any], [])
            if not isinstance(then_actions, list):
                then_actions = []
            _walk(
                then_actions,
                visit_action=visit_action,
                visit_condition=visit_condition,
                location_prefix=f"{location}.then",
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            else_actions = action.get("else") or cast(list[Any], [])
            if isinstance(else_actions, list) and else_actions:
                _walk(
                    else_actions,
                    visit_action=visit_action,
                    visit_condition=visit_condition,
                    location_prefix=f"{location}.else",
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )

        if "repeat" in action:
            repeat_config = action["repeat"]
            if isinstance(repeat_config, dict):
                if visit_condition:
                    for cond_key in ("while", "until"):
                        _visit_conditions(
                            repeat_config.get(cond_key),
                            visit_condition,
                            f"{location}.repeat.{cond_key}",
                        )
                sequence = cast(list[Any], repeat_config.get("sequence") or [])
                _walk(
                    sequence,
                    visit_action=visit_action,
                    visit_condition=visit_condition,
                    location_prefix=f"{location}.repeat.sequence",
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )

        if "parallel" in action:
            branches = cast(list[Any], action.get("parallel") or [])
            if not isinstance(branches, list):  # pyright: ignore[reportUnnecessaryIsInstance]
                branches = [branches]
            for branch_idx, branch in enumerate(branches):
                branch_actions = cast(
                    list[Any],
                    branch if isinstance(branch, list) else [branch],  # pyright: ignore[reportUnnecessaryIsInstance]
                )
                _walk(
                    branch_actions,
                    visit_action=visit_action,
                    visit_condition=visit_condition,
                    location_prefix=f"{location}.parallel[{branch_idx}]",
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )
