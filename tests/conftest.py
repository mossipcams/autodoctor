"""Pytest configuration for Autodoctor tests."""

import inspect
import sys
from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.autodoctor.models import IssueType, Severity, ValidationIssue
from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor

# Import fixtures from pytest-homeassistant-custom-component
pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations for all tests.

    This fixture runs automatically for every test and ensures custom
    integrations can be loaded during test execution.
    """
    return


@pytest.fixture(autouse=True)
def scrub_editable_path_hook_placeholder() -> None:
    """Remove editable install path-hook placeholders from sys.path.

    Setuptools editable installs can inject values like
    ``__editable__.pkg-x.y.z.finder.__path_hook__`` into ``sys.path``.
    Home Assistant's loader teardown may treat each sys.path entry as a
    filesystem directory and call ``Path.iterdir()``, which crashes on these
    placeholders.
    """
    sys.path[:] = [
        p
        for p in sys.path
        if not (p.startswith("__editable__.") and p.endswith(".__path_hook__"))
    ]


@pytest.fixture
def mock_recorder() -> Generator[MagicMock, None, None]:
    """Mock the Home Assistant recorder component.

    Prevents tests from attempting to access a real database.
    Yields a MagicMock instance that can be configured per test.
    """
    with patch("custom_components.autodoctor.knowledge_base.get_instance") as mock:
        mock.return_value = MagicMock()
        yield mock


def build_runtime_monitor(now: datetime, **kwargs: object) -> RuntimeHealthMonitor:
    """Create a RuntimeHealthMonitor with sensible test defaults."""
    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    return RuntimeHealthMonitor(
        hass,
        now_factory=lambda: now,
        warmup_samples=0,
        min_expected_events=0,
        **kwargs,
    )


def make_issue(
    issue_type: IssueType,
    severity: Severity,
    *,
    automation_id: str = "automation.test",
    automation_name: str = "Test",
    entity_id: str = "light.test",
    location: str = "trigger[0]",
    message: str | None = None,
) -> ValidationIssue:
    """Create a minimal ValidationIssue for testing."""
    return ValidationIssue(
        issue_type=issue_type,
        severity=severity,
        automation_id=automation_id,
        automation_name=automation_name,
        entity_id=entity_id,
        location=location,
        message=message or f"Test issue: {issue_type.value}",
    )


async def invoke_command(
    handler: Any,
    hass: Any,
    connection: Any,
    msg: dict[str, Any],
) -> None:
    """Invoke websocket handler by unwrapping decorators until coroutine function."""
    target = handler
    while not inspect.iscoroutinefunction(target):
        wrapped = getattr(target, "__wrapped__", None)
        if wrapped is None:
            break
        target = wrapped
    assert inspect.iscoroutinefunction(target)
    await target(hass, connection, msg)
