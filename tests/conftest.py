"""Pytest configuration for Autodoctor tests."""

from unittest.mock import MagicMock, patch

import pytest

# Import fixtures from pytest-homeassistant-custom-component
pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_recorder():
    """Mock the recorder component."""
    with patch("custom_components.autodoctor.knowledge_base.get_instance") as mock:
        mock.return_value = MagicMock()
        yield mock
