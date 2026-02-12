"""Pytest configuration for Autodoctor tests."""

import sys
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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
