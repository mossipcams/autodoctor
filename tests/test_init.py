"""Tests for autodoctor __init__.py."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.autodoctor import (
    async_validate_all,
    async_validate_all_with_groups,
    async_validate_automation,
)
from custom_components.autodoctor.const import DOMAIN
from custom_components.autodoctor.models import (
    VALIDATION_GROUP_ORDER,
    IssueType,
    Severity,
    ValidationIssue,
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
    from custom_components.autodoctor import (
        _build_config_snapshot,
        _setup_reload_listener,
    )

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
    from custom_components.autodoctor import (
        _build_config_snapshot,
        _setup_reload_listener,
    )

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
    from custom_components.autodoctor import (
        _build_config_snapshot,
        _setup_reload_listener,
    )

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


# --- _get_automation_configs tests (mutation hardening) ---


def test_get_automation_configs_none_returns_empty():
    """When automation_data is None, returns empty list.

    Kills: AddNot on `if automation_data is None` (L88) --
    if inverted, None would fall through and crash.
    """
    from custom_components.autodoctor import _get_automation_configs

    hass = MagicMock()
    hass.data = {}  # No "automation" key at all
    result = _get_automation_configs(hass)
    assert result == []


def test_get_automation_configs_dict_mode():
    """When automation_data is a dict with "config" key, returns configs.

    Kills: isinstance(automation_data, dict) guard (L95) and
    .get("config", []) at L96.
    """
    from custom_components.autodoctor import _get_automation_configs

    configs = [{"id": "a1", "alias": "Test"}]
    hass = MagicMock()
    hass.data = {"automation": {"config": configs}}
    result = _get_automation_configs(hass)
    assert result == configs
    assert len(result) == 1


def test_get_automation_configs_entity_component_mode():
    """When automation_data is EntityComponent-like with .entities, extracts raw_config.

    Kills: hasattr(automation_data, "entities") guard (L101) and
    raw_config extraction loop (L104-L114).
    """
    from custom_components.autodoctor import _get_automation_configs

    entity1 = MagicMock()
    entity1.entity_id = "automation.test1"
    entity1.raw_config = {"id": "test1", "alias": "Test 1"}

    entity2 = MagicMock()
    entity2.entity_id = "automation.test2"
    entity2.raw_config = {"id": "test2", "alias": "Test 2"}

    component = MagicMock()
    component.entities = [entity1, entity2]

    hass = MagicMock()
    hass.data = {"automation": component}
    result = _get_automation_configs(hass)
    assert len(result) == 2
    assert result[0]["id"] == "test1"
    assert result[1]["id"] == "test2"


def test_get_automation_configs_entity_without_raw_config():
    """Entity without raw_config is skipped.

    Kills: `if hasattr(entity, "raw_config") and entity.raw_config is not None`
    guard (L113) -- if and->or or AddNot, entities without raw_config would
    crash or be included.
    """
    from custom_components.autodoctor import _get_automation_configs

    entity_with = MagicMock()
    entity_with.entity_id = "automation.good"
    entity_with.raw_config = {"id": "good", "alias": "Good"}

    entity_without = MagicMock(spec=["entity_id"])  # No raw_config attribute
    entity_without.entity_id = "automation.bad"

    entity_none = MagicMock()
    entity_none.entity_id = "automation.none"
    entity_none.raw_config = None

    component = MagicMock()
    component.entities = [entity_with, entity_without, entity_none]

    hass = MagicMock()
    hass.data = {"automation": component}
    result = _get_automation_configs(hass)
    assert len(result) == 1
    assert result[0]["id"] == "good"


# --- _async_register_card tests (mutation hardening) ---


@pytest.mark.asyncio
async def test_register_card_path_missing():
    """Card path doesn't exist -> returns early, no crash.

    Kills: AddNot on `if not card_path.exists()` (L135) --
    if inverted, non-existent path would continue and crash.
    """
    from custom_components.autodoctor import _async_register_card

    hass = MagicMock()
    with patch("pathlib.Path.exists", return_value=False):
        await _async_register_card(hass)
    # http.async_register_static_paths should NOT have been called
    hass.http.async_register_static_paths.assert_not_called()


@pytest.mark.asyncio
async def test_register_card_storage_mode_creates_resource():
    """Card path exists, lovelace storage mode, no existing resource -> creates.

    Kills: mutations on lovelace_mode == "storage" (L158),
    resources.async_create_item call (L191), and current_exists check (L171).
    """
    from custom_components.autodoctor import _async_register_card

    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    # Mock lovelace in storage mode with resources
    mock_resources = MagicMock()
    mock_resources.async_items.return_value = []  # No existing resources
    mock_resources.async_create_item = AsyncMock()

    mock_lovelace = MagicMock()
    mock_lovelace.mode = "storage"
    mock_lovelace.resources = mock_resources
    hass.data = {"lovelace": mock_lovelace}

    with patch("pathlib.Path.exists", return_value=True):
        await _async_register_card(hass)

    # Should have registered static path and created resource
    hass.http.async_register_static_paths.assert_called_once()
    mock_resources.async_create_item.assert_called_once()
    call_args = mock_resources.async_create_item.call_args[0][0]
    assert call_args["res_type"] == "module"
    assert "autodoctor" in call_args["url"]


@pytest.mark.asyncio
async def test_register_card_current_version_already_registered():
    """Current version already registered -> no create/delete.

    Kills: AddNot on `if current_exists` (L173) -- if inverted,
    already-registered version would be re-created.
    """
    from custom_components.autodoctor import CARD_URL_BASE, _async_register_card
    from custom_components.autodoctor.const import VERSION

    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    card_url = f"{CARD_URL_BASE}?v={VERSION}"
    mock_resources = MagicMock()
    mock_resources.async_items.return_value = [
        {"url": card_url, "id": "existing_id"}
    ]
    mock_resources.async_create_item = AsyncMock()
    mock_resources.async_delete_item = AsyncMock()

    mock_lovelace = MagicMock()
    mock_lovelace.mode = "storage"
    mock_lovelace.resources = mock_resources
    hass.data = {"lovelace": mock_lovelace}

    with patch("pathlib.Path.exists", return_value=True):
        await _async_register_card(hass)

    # Should NOT create or delete anything
    mock_resources.async_create_item.assert_not_called()
    mock_resources.async_delete_item.assert_not_called()


@pytest.mark.asyncio
async def test_register_card_replaces_old_version():
    """Old version exists -> removes old, creates new.

    Kills: ZeroIterationForLoop on `for resource in existing` (L177) and
    mutations on resource_id extraction (L178-L181).
    """
    from custom_components.autodoctor import _async_register_card

    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    mock_resources = MagicMock()
    mock_resources.async_items.return_value = [
        {"url": "/autodoctor/autodoctor-card.js?v=0.0.1", "id": "old_id"}
    ]
    mock_resources.async_create_item = AsyncMock()
    mock_resources.async_delete_item = AsyncMock()

    mock_lovelace = MagicMock()
    mock_lovelace.mode = "storage"
    mock_lovelace.resources = mock_resources
    hass.data = {"lovelace": mock_lovelace}

    with patch("pathlib.Path.exists", return_value=True):
        await _async_register_card(hass)

    # Should delete old and create new
    mock_resources.async_delete_item.assert_called_once_with("old_id")
    mock_resources.async_create_item.assert_called_once()


@pytest.mark.asyncio
async def test_register_card_yaml_mode_skips_resources():
    """Lovelace in YAML mode -> skips resource registration.

    Kills: Eq on `lovelace_mode == "storage"` (L158) -- if == becomes !=,
    YAML mode would try to register resources.
    """
    from custom_components.autodoctor import _async_register_card

    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    mock_lovelace = MagicMock()
    mock_lovelace.mode = "yaml"
    mock_lovelace.resources = MagicMock()
    hass.data = {"lovelace": mock_lovelace}

    with patch("pathlib.Path.exists", return_value=True):
        await _async_register_card(hass)

    # Static path registered, but NO resource operations
    hass.http.async_register_static_paths.assert_called_once()
    mock_lovelace.resources.async_items.assert_not_called()


# --- async_unload_entry tests (mutation hardening) ---


@pytest.mark.asyncio
async def test_unload_entry_cancels_debounce_task():
    """Unload cancels active debounce task.

    Kills: AddNot on `if debounce_task is not None and not debounce_task.done()`
    (L312) and debounce_task.cancel() call (L313).
    """
    from custom_components.autodoctor import async_unload_entry

    hass = MagicMock()
    entry = MagicMock()
    mock_task = MagicMock()
    mock_task.done.return_value = False

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services.async_remove = MagicMock()
    hass.data = {
        DOMAIN: {
            "debounce_task": mock_task,
            "unsub_reload_listener": None,
            "unsub_entity_registry_listener": None,
        }
    }

    result = await async_unload_entry(hass, entry)
    assert result is True
    mock_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_unload_entry_calls_unsub_listeners():
    """Unload calls unsub callbacks for reload and entity registry listeners.

    Kills: AddNot on `if unsub_reload is not None` (L317) and
    `if unsub_entity_reg is not None` (L320).
    """
    from custom_components.autodoctor import async_unload_entry

    hass = MagicMock()
    entry = MagicMock()
    unsub_reload = MagicMock()
    unsub_entity_reg = MagicMock()

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services.async_remove = MagicMock()
    hass.data = {
        DOMAIN: {
            "debounce_task": None,
            "unsub_reload_listener": unsub_reload,
            "unsub_entity_registry_listener": unsub_entity_reg,
        }
    }

    result = await async_unload_entry(hass, entry)
    assert result is True
    unsub_reload.assert_called_once()
    unsub_entity_reg.assert_called_once()


@pytest.mark.asyncio
async def test_unload_entry_removes_services():
    """Unload removes all three registered services.

    Kills: mutations on service name strings at L325-L327 and
    hass.services.async_remove calls.
    """
    from custom_components.autodoctor import async_unload_entry

    hass = MagicMock()
    entry = MagicMock()

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services.async_remove = MagicMock()
    hass.data = {
        DOMAIN: {
            "debounce_task": None,
            "unsub_reload_listener": None,
            "unsub_entity_registry_listener": None,
        }
    }

    await async_unload_entry(hass, entry)

    # All three services should be removed
    calls = [c[0] for c in hass.services.async_remove.call_args_list]
    assert (DOMAIN, "validate") in calls
    assert (DOMAIN, "validate_automation") in calls
    assert (DOMAIN, "refresh_knowledge_base") in calls
    assert hass.services.async_remove.call_count == 3


# --- _async_run_validators tests (mutation hardening) ---


@pytest.mark.asyncio
async def test_run_validators_failed_automation_warning(grouped_hass):
    """1 failing automation -> warning logged with count.

    Kills: `> 0` mutations on `if failed_automations > 0` (L501) and
    failed_automations counter increment (L491).
    """
    from custom_components.autodoctor import _async_run_validators

    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.side_effect = Exception("boom")
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch("custom_components.autodoctor._LOGGER") as mock_logger:
        result = await _async_run_validators(
            grouped_hass, [{"id": "bad", "alias": "Bad"}]
        )

    # Warning should mention 1 failed automation
    warning_calls = [c for c in mock_logger.warning.call_args_list
                     if "failed automations" in str(c)]
    assert len(warning_calls) == 1
    assert "1" in str(warning_calls[0])


@pytest.mark.asyncio
async def test_run_validators_no_failures_no_warning(grouped_hass):
    """0 failed automations -> no failure warning logged.

    Kills: `> 0` -> `>= 0` or `> -1` mutations on
    `if failed_automations > 0` (L501).
    """
    from custom_components.autodoctor import _async_run_validators

    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch("custom_components.autodoctor._LOGGER") as mock_logger:
        await _async_run_validators(
            grouped_hass, [{"id": "good", "alias": "Good"}]
        )

    # No "failed automations" warning
    warning_calls = [c for c in mock_logger.warning.call_args_list
                     if "failed automations" in str(c)]
    assert len(warning_calls) == 0


@pytest.mark.asyncio
async def test_run_validators_group_durations_and_mapping(grouped_hass):
    """Group durations are non-negative integers, issue_type_to_group maps correctly.

    Kills: NumberReplacer on `{gid: 0 for gid in ...}` (L423) -- if 0 becomes
    1 or -1, initial durations would be non-zero even for skipped validators.
    Kills: ZeroIterationForLoop on `for gid, gdef in VALIDATION_GROUPS.items()`
    (L427) and `for it in gdef["issue_types"]` (L428).
    """
    from custom_components.autodoctor import _async_run_validators

    # Create a real issue that should be classified
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.ERROR)
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [template_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    result = await _async_run_validators(
        grouped_hass, [{"id": "test", "alias": "Test"}]
    )

    # All groups have non-negative durations
    for gid in VALIDATION_GROUP_ORDER:
        assert result["group_durations"][gid] >= 0

    # Template issue classified into templates group
    assert template_issue in result["group_issues"]["templates"]
    assert template_issue not in result["group_issues"]["entity_state"]
    assert template_issue not in result["group_issues"]["services"]


# --- Service handler tests (mutation hardening) ---


@pytest.mark.asyncio
async def test_handle_validate_with_automation_id():
    """handle_validate with automation_id calls targeted validation.

    Kills: AddNot on `if automation_id` (L381) -- if inverted,
    targeted validation would never fire.
    """
    from custom_components.autodoctor import _async_setup_services

    hass = MagicMock()
    hass.services.async_register = MagicMock()

    await _async_setup_services(hass)

    # Extract the registered handler for "validate"
    validate_handler = hass.services.async_register.call_args_list[0][0][2]

    call = MagicMock()
    call.data = {"automation_id": "automation.test123"}

    with patch(
        "custom_components.autodoctor.async_validate_automation",
        new_callable=AsyncMock,
    ) as mock_targeted, patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
    ) as mock_all:
        await validate_handler(call)

    mock_targeted.assert_called_once_with(hass, "automation.test123")
    mock_all.assert_not_called()


@pytest.mark.asyncio
async def test_handle_refresh_with_knowledge_base():
    """handle_refresh with kb present clears cache and loads history.

    Kills: AddNot on `if kb` (L389) -- if inverted, kb.clear_cache()
    and async_load_history() would never fire.
    """
    from custom_components.autodoctor import _async_setup_services

    hass = MagicMock()
    hass.services.async_register = MagicMock()

    mock_kb = MagicMock()
    mock_kb.async_load_history = AsyncMock()
    hass.data = {DOMAIN: {"knowledge_base": mock_kb}}

    await _async_setup_services(hass)

    # Extract the registered handler for "refresh_knowledge_base"
    refresh_handler = hass.services.async_register.call_args_list[2][0][2]

    call = MagicMock()
    call.data = {}

    await refresh_handler(call)

    mock_kb.clear_cache.assert_called_once()
    mock_kb.async_load_history.assert_called_once()


@pytest.mark.asyncio
async def test_validate_automation_matches_correct_id(grouped_hass):
    """async_validate_automation only validates the matching automation.

    Kills: mutations on `f"automation.{a.get('id')}" == automation_id`
    at L614 -- wrong matching would validate wrong or no automation.
    """
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[
            {"id": "auto_a", "alias": "Auto A"},
            {"id": "auto_b", "alias": "Auto B"},
        ],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.auto_b")

    # validate_automations should be called with ONLY auto_b (single-element list)
    call_args = grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.call_args
    validated = call_args[0][0]
    assert len(validated) == 1
    assert validated[0]["id"] == "auto_b"


@pytest.mark.asyncio
async def test_handle_validate_without_automation_id():
    """handle_validate without automation_id calls validate_all.

    Paired with test_handle_validate_with_automation_id to kill
    if/else branching mutations at L381-L384.
    """
    from custom_components.autodoctor import _async_setup_services

    hass = MagicMock()
    hass.services.async_register = MagicMock()

    await _async_setup_services(hass)

    validate_handler = hass.services.async_register.call_args_list[0][0][2]

    call = MagicMock()
    call.data = {}  # No automation_id

    with patch(
        "custom_components.autodoctor.async_validate_automation",
        new_callable=AsyncMock,
    ) as mock_targeted, patch(
        "custom_components.autodoctor.async_validate_all",
        new_callable=AsyncMock,
    ) as mock_all:
        await validate_handler(call)

    mock_all.assert_called_once()
    mock_targeted.assert_not_called()


@pytest.mark.asyncio
async def test_validate_all_with_groups_missing_validators(mock_hass):
    """Missing validators -> returns empty result without crash.

    Kills: mutations on `if not all([analyzer, validator, reporter])` (L549).
    """
    mock_hass.data[DOMAIN] = {
        "analyzer": None,
        "validator": None,
        "reporter": None,
        "knowledge_base": None,
    }

    result = await async_validate_all_with_groups(mock_hass)
    assert result["all_issues"] == []
    for gid in VALIDATION_GROUP_ORDER:
        assert result["group_issues"][gid] == []


@pytest.mark.asyncio
async def test_run_validators_skips_missing_jinja_validator(mock_hass):
    """When jinja_validator is None, jinja validation is skipped.

    Kills: AddNot on `if jinja_validator` (L433).
    """
    from custom_components.autodoctor import _async_run_validators

    mock_hass.data[DOMAIN] = {
        "analyzer": MagicMock(),
        "validator": MagicMock(),
        "jinja_validator": None,
        "service_validator": None,
    }
    mock_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    mock_hass.data[DOMAIN]["validator"].validate_all.return_value = []

    result = await _async_run_validators(
        mock_hass, [{"id": "test", "alias": "Test"}]
    )

    assert result["group_issues"]["templates"] == []


@pytest.mark.asyncio
async def test_run_validators_all_issues_canonical_order(grouped_hass):
    """all_issues combines groups in VALIDATION_GROUP_ORDER.

    Kills: ZeroIterationForLoop on `for gid in VALIDATION_GROUP_ORDER` (L510)
    and mutations on all_issues.extend ordering.
    """
    from custom_components.autodoctor import _async_run_validators

    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.ERROR)

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [template_issue]
    grouped_hass.data[DOMAIN]["service_validator"].validate_service_calls.return_value = [service_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    result = await _async_run_validators(
        grouped_hass, [{"id": "test", "alias": "Test"}]
    )

    # all_issues should contain all 3 issues
    assert len(result["all_issues"]) == 3
    # Order: entity_state first, services second, templates third
    assert result["all_issues"][0].issue_type == IssueType.ENTITY_NOT_FOUND
    assert result["all_issues"][1].issue_type == IssueType.SERVICE_NOT_FOUND
    assert result["all_issues"][2].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR
