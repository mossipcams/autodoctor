"""Tests for autodoctor __init__.py."""

import asyncio

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from custom_components.autodoctor import (
    async_validate_all,
    async_validate_all_with_groups,
    async_validate_automation,
)
from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import (
    IssueType,
    Severity,
    ValidationIssue,
    VALIDATION_GROUP_ORDER,
)


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


@pytest.mark.asyncio
async def test_one_bad_automation_does_not_crash_all(mock_hass):
    """Test that one malformed automation doesn't stop validation of others."""
    # Setup mocks
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_reporter = AsyncMock()

    # First automation raises, second succeeds
    mock_analyzer.extract_state_references.side_effect = [
        Exception("Malformed config"),
        [],  # Second automation succeeds
    ]
    mock_validator.validate_all.return_value = []

    mock_hass.data[DOMAIN] = {
        "analyzer": mock_analyzer,
        "validator": mock_validator,
        "reporter": mock_reporter,
        "knowledge_base": None,
    }

    # Mock _get_automation_configs to return 2 automations
    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[
            {"id": "bad", "alias": "Bad Auto"},
            {"id": "good", "alias": "Good Auto"},
        ],
    ):
        issues = await async_validate_all(mock_hass)

    # Should have processed both automations (one failed, one succeeded)
    assert mock_analyzer.extract_state_references.call_count == 2
    assert isinstance(issues, list)


def _make_issue(issue_type: IssueType, severity: Severity) -> ValidationIssue:
    """Create a minimal ValidationIssue for testing."""
    return ValidationIssue(
        issue_type=issue_type,
        severity=severity,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.test",
        location="trigger[0]",
        message=f"Test issue ({issue_type.value})",
    )


@pytest.fixture
def grouped_hass(mock_hass):
    """Create mock hass pre-configured with all validators for grouped tests."""
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_reporter = AsyncMock()
    mock_jinja = MagicMock()
    mock_service = MagicMock()
    mock_service.async_load_descriptions = AsyncMock()

    mock_hass.data[DOMAIN] = {
        "analyzer": mock_analyzer,
        "validator": mock_validator,
        "reporter": mock_reporter,
        "jinja_validator": mock_jinja,
        "service_validator": mock_service,
        "knowledge_base": None,
        "issues": [],
        "validation_issues": [],
        "validation_last_run": None,
    }

    return mock_hass


@pytest.mark.asyncio
async def test_validate_all_with_groups_classification(grouped_hass):
    """Test that issues are classified into the correct groups."""
    # Set up entity-state issues from state ref validator
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    # Set up template issues from jinja validator
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]

    # Set up service issues from service validator
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [
        service_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Verify return structure
    assert "group_issues" in result
    assert "group_durations" in result
    assert "all_issues" in result
    assert "timestamp" in result

    # Verify entity issue classified into entity_state group
    assert entity_issue in result["group_issues"]["entity_state"]
    assert entity_issue not in result["group_issues"]["templates"]
    assert entity_issue not in result["group_issues"]["services"]

    # Verify template issue classified into templates group
    assert template_issue in result["group_issues"]["templates"]
    assert template_issue not in result["group_issues"]["entity_state"]

    # Verify service issue classified into services group
    assert service_issue in result["group_issues"]["services"]
    assert service_issue not in result["group_issues"]["entity_state"]

    # All issues present in flat list
    assert len(result["all_issues"]) == 3


@pytest.mark.asyncio
async def test_validate_all_with_groups_timing(grouped_hass):
    """Test that each group has a non-negative duration_ms value."""
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Every group must have a duration
    for gid in VALIDATION_GROUP_ORDER:
        duration = result["group_durations"][gid]
        assert isinstance(duration, int), f"Group '{gid}' duration is not an int"
        assert duration >= 0, f"Group '{gid}' has negative duration: {duration}"


@pytest.mark.asyncio
async def test_validate_all_with_groups_status_logic(grouped_hass):
    """Test group status: fail for errors, warning for warnings only, pass for clean."""
    # entity_state gets an ERROR issue -> status should be "fail"
    error_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [error_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    # templates gets a WARNING issue -> status should be "warning"
    warning_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        warning_issue
    ]

    # services gets no issues -> status should be "pass"
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # Import the status helper to verify status logic matches group issues
    from custom_components.autodoctor.websocket_api import _compute_group_status

    assert _compute_group_status(result["group_issues"]["entity_state"]) == "fail"
    assert _compute_group_status(result["group_issues"]["templates"]) == "warning"
    assert _compute_group_status(result["group_issues"]["services"]) == "pass"


@pytest.mark.asyncio
async def test_validate_all_with_groups_empty_automations(grouped_hass):
    """Test that empty automation list returns empty group structure."""
    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    # All groups should be empty
    for gid in VALIDATION_GROUP_ORDER:
        assert result["group_issues"][gid] == []
        assert result["group_durations"][gid] == 0

    assert result["all_issues"] == []
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_validate_automation_includes_service_validation(grouped_hass):
    """Test that async_validate_automation includes service validation (C1 fix).

    Previously, async_validate_automation skipped service validation entirely.
    After consolidation, it routes through the shared core which includes
    all three validator families.
    """
    # Set up a service issue
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [
        service_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    # No issues from other validators
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.test")

    # Service issue MUST be present (this was the C1 bug)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND

    # Verify service validator was actually called
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.assert_called_once()


@pytest.mark.asyncio
async def test_validate_automation_includes_all_families(grouped_hass):
    """Test that async_validate_automation runs all three validator families."""
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)

    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [
        service_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.test")

    # All three families should contribute issues
    assert len(issues) == 3
    issue_types = {i.issue_type for i in issues}
    assert IssueType.TEMPLATE_SYNTAX_ERROR in issue_types
    assert IssueType.SERVICE_NOT_FOUND in issue_types
    assert IssueType.ENTITY_NOT_FOUND in issue_types


@pytest.mark.asyncio
async def test_validate_automation_not_found(grouped_hass):
    """Test that async_validate_automation returns empty when automation not found."""
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "other", "alias": "Other"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.nonexistent")

    assert issues == []


@pytest.mark.asyncio
async def test_validate_all_is_thin_wrapper(grouped_hass):
    """Test that async_validate_all returns same issues as grouped version."""
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        flat_issues = await async_validate_all(grouped_hass)

    # Should return a flat list, not a dict
    assert isinstance(flat_issues, list)
    assert len(flat_issues) == 1
    assert flat_issues[0] is entity_issue


# --- Phase 24: Dedup removal guard test ---


def test_no_dedup_cross_family_function():
    """Module must NOT export _dedup_cross_family (removed in v2.14.0).

    Cross-family dedup is no longer needed because jinja_validator no longer
    produces entity validation issues (entity validation path was removed).
    """
    import custom_components.autodoctor as init_module
    assert not hasattr(init_module, "_dedup_cross_family"), (
        "_dedup_cross_family must be removed from __init__.py"
    )
    assert not hasattr(init_module, "_SEMANTIC_FAMILIES"), (
        "_SEMANTIC_FAMILIES must be removed from __init__.py"
    )
    assert not hasattr(init_module, "_PREFERRED_ISSUE_TYPES"), (
        "_PREFERRED_ISSUE_TYPES must be removed from __init__.py"
    )


# --- Config snapshot diff tests (single-automation validation on save) ---


def test_build_config_snapshot():
    """Test that _build_config_snapshot returns deterministic hashes keyed by id."""
    from custom_components.autodoctor import _build_config_snapshot

    configs = [
        {"id": "abc", "alias": "Test 1", "trigger": [{"platform": "state"}]},
        {"id": "def", "alias": "Test 2", "trigger": [{"platform": "time"}]},
    ]
    snapshot = _build_config_snapshot(configs)

    # Returns dict keyed by automation id
    assert isinstance(snapshot, dict)
    assert set(snapshot.keys()) == {"abc", "def"}

    # Hashes are strings
    assert isinstance(snapshot["abc"], str)
    assert isinstance(snapshot["def"], str)

    # Different configs produce different hashes
    assert snapshot["abc"] != snapshot["def"]

    # Same config always produces same hash (deterministic)
    snapshot2 = _build_config_snapshot(configs)
    assert snapshot == snapshot2


def test_build_config_snapshot_skips_configs_without_id():
    """Test that configs without an id field are skipped in the snapshot."""
    from custom_components.autodoctor import _build_config_snapshot

    configs = [
        {"id": "abc", "alias": "Has ID"},
        {"alias": "No ID"},  # No 'id' key
    ]
    snapshot = _build_config_snapshot(configs)
    assert set(snapshot.keys()) == {"abc"}


@pytest.mark.asyncio
async def test_reload_listener_single_automation_change(mock_hass):
    """When only one automation config changes, validate just that automation."""
    from custom_components.autodoctor import _build_config_snapshot, _setup_reload_listener

    # Build a baseline snapshot of 3 automations
    original_configs = [
        {"id": "auto_1", "alias": "Auto 1", "trigger": [{"platform": "state"}]},
        {"id": "auto_2", "alias": "Auto 2", "trigger": [{"platform": "time"}]},
        {"id": "auto_3", "alias": "Auto 3", "trigger": [{"platform": "sun"}]},
    ]
    original_snapshot = _build_config_snapshot(original_configs)

    # One automation changed
    changed_configs = [
        {"id": "auto_1", "alias": "Auto 1", "trigger": [{"platform": "state"}]},
        {"id": "auto_2", "alias": "Auto 2 CHANGED", "trigger": [{"platform": "time", "at": "12:00"}]},
        {"id": "auto_3", "alias": "Auto 3", "trigger": [{"platform": "sun"}]},
    ]

    mock_hass.data[DOMAIN] = {
        "debounce_task": None,
        "_automation_snapshot": original_snapshot,
    }
    mock_hass.async_create_task = lambda coro: asyncio.ensure_future(coro)

    # Capture what event listener is registered
    listener_callback = None

    def mock_async_listen(event_type, callback):
        nonlocal listener_callback
        listener_callback = callback
        return MagicMock()  # unsub

    mock_hass.bus.async_listen = mock_async_listen

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=changed_configs,
    ), patch(
        "custom_components.autodoctor.async_validate_automation",
        new_callable=AsyncMock,
    ) as mock_validate_auto, patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
    ) as mock_validate_all:
        _setup_reload_listener(mock_hass, debounce_seconds=0)
        assert listener_callback is not None

        # Fire the event
        listener_callback(MagicMock())

        # Wait for debounce (0s) + processing
        await asyncio.sleep(0.1)

        # Should have called targeted validation for auto_2 only
        mock_validate_auto.assert_called_once_with(mock_hass, "automation.auto_2")
        mock_validate_all.assert_not_called()


@pytest.mark.asyncio
async def test_reload_listener_bulk_reload_validates_all(mock_hass):
    """When 3+ automations change, validate all instead of targeted."""
    from custom_components.autodoctor import _build_config_snapshot, _setup_reload_listener

    original_configs = [
        {"id": "auto_1", "alias": "Auto 1"},
        {"id": "auto_2", "alias": "Auto 2"},
        {"id": "auto_3", "alias": "Auto 3"},
    ]
    original_snapshot = _build_config_snapshot(original_configs)

    # All three changed
    changed_configs = [
        {"id": "auto_1", "alias": "Auto 1 CHANGED"},
        {"id": "auto_2", "alias": "Auto 2 CHANGED"},
        {"id": "auto_3", "alias": "Auto 3 CHANGED"},
    ]

    mock_hass.data[DOMAIN] = {
        "debounce_task": None,
        "_automation_snapshot": original_snapshot,
    }
    mock_hass.async_create_task = lambda coro: asyncio.ensure_future(coro)

    listener_callback = None

    def mock_async_listen(event_type, callback):
        nonlocal listener_callback
        listener_callback = callback
        return MagicMock()

    mock_hass.bus.async_listen = mock_async_listen

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=changed_configs,
    ), patch(
        "custom_components.autodoctor.async_validate_automation",
        new_callable=AsyncMock,
    ) as mock_validate_auto, patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
    ) as mock_validate_all:
        _setup_reload_listener(mock_hass, debounce_seconds=0)
        listener_callback(MagicMock())
        await asyncio.sleep(0.1)

        mock_validate_all.assert_called_once()
        mock_validate_auto.assert_not_called()


@pytest.mark.asyncio
async def test_reload_listener_no_snapshot_validates_all(mock_hass):
    """When no previous snapshot exists (first run), validate all automations."""
    from custom_components.autodoctor import _setup_reload_listener

    configs = [
        {"id": "auto_1", "alias": "Auto 1"},
        {"id": "auto_2", "alias": "Auto 2"},
    ]

    # No _automation_snapshot key at all
    mock_hass.data[DOMAIN] = {
        "debounce_task": None,
    }
    mock_hass.async_create_task = lambda coro: asyncio.ensure_future(coro)

    listener_callback = None

    def mock_async_listen(event_type, callback):
        nonlocal listener_callback
        listener_callback = callback
        return MagicMock()

    mock_hass.bus.async_listen = mock_async_listen

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=configs,
    ), patch(
        "custom_components.autodoctor.async_validate_automation",
        new_callable=AsyncMock,
    ) as mock_validate_auto, patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
    ) as mock_validate_all:
        _setup_reload_listener(mock_hass, debounce_seconds=0)
        listener_callback(MagicMock())
        await asyncio.sleep(0.1)

        mock_validate_all.assert_called_once()
        mock_validate_auto.assert_not_called()


@pytest.mark.asyncio
async def test_snapshot_updated_after_validation(mock_hass):
    """Snapshot in hass.data is updated after reload validation completes."""
    from custom_components.autodoctor import _build_config_snapshot, _setup_reload_listener

    configs = [
        {"id": "auto_1", "alias": "Auto 1"},
    ]

    mock_hass.data[DOMAIN] = {
        "debounce_task": None,
    }
    mock_hass.async_create_task = lambda coro: asyncio.ensure_future(coro)

    listener_callback = None

    def mock_async_listen(event_type, callback):
        nonlocal listener_callback
        listener_callback = callback
        return MagicMock()

    mock_hass.bus.async_listen = mock_async_listen

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=configs,
    ), patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
    ):
        _setup_reload_listener(mock_hass, debounce_seconds=0)

        # No snapshot before first event
        assert "_automation_snapshot" not in mock_hass.data[DOMAIN]

        listener_callback(MagicMock())
        await asyncio.sleep(0.1)

        # Snapshot should now exist and match current configs
        expected = _build_config_snapshot(configs)
        assert mock_hass.data[DOMAIN]["_automation_snapshot"] == expected
