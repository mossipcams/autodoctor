"""Tests for SuppressionStore orphan cleanup."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.autodoctor.suppression_store import SuppressionStore


@pytest.mark.asyncio
async def test_async_load_strips_orphaned_issue_types(hass: HomeAssistant):
    """Test that async_load removes entries referencing IssueType values no longer in the enum."""
    store = SuppressionStore(hass)

    # Simulate stored data with both valid and orphaned suppression keys.
    # "entity_not_found" is a valid IssueType value; "template_entity_not_found" was removed.
    stored_data = {
        "suppressions": [
            "automation.a:light.a:entity_not_found",
            "automation.b:light.b:template_entity_not_found",
            "automation.c:sensor.c:template_zone_not_found",
        ]
    }

    with (
        patch.object(
            store._store, "async_load", new_callable=AsyncMock, return_value=stored_data
        ),
        patch.object(store._store, "async_save", new_callable=AsyncMock) as mock_save,
    ):
        await store.async_load()

    # Only the valid key should remain
    assert store.count == 1
    assert store.is_suppressed("automation.a:light.a:entity_not_found")
    assert not store.is_suppressed("automation.b:light.b:template_entity_not_found")
    assert not store.is_suppressed("automation.c:sensor.c:template_zone_not_found")

    # Should have persisted the cleaned set
    mock_save.assert_called_once()
