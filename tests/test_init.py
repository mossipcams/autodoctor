"""Tests for autodoctor __init__.py.

Tests cover:
- Orchestration: async_validate_all, async_validate_all_with_groups, async_validate_automation
- Validation pipeline: _async_run_validators
- Grouped validation: issue classification, timing, status logic
- Configuration loading: _get_automation_configs
- Lovelace card registration: _async_register_card
- Reload detection: _setup_reload_listener, config snapshot diffing
- Service handlers: validate, validate_automation, refresh_knowledge_base
- Lifecycle: async_unload_entry
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.autodoctor import (
    async_validate_all,
    async_validate_all_with_groups,
    async_validate_automation,
)
from custom_components.autodoctor.const import (
    DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS,
    DOMAIN,
)
from custom_components.autodoctor.models import (
    VALIDATION_GROUP_ORDER,
    IssueType,
    Severity,
    ValidationIssue,
)


@pytest.fixture
def mock_hass() -> MagicMock:
    """Create mock Home Assistant instance.

    Provides a minimal mock with hass.data pre-initialized with an empty
    Autodoctor domain dict. Suitable for tests that need to populate
    hass.data with specific validators or state.
    """
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


@pytest.mark.asyncio
async def test_one_bad_automation_does_not_crash_all(mock_hass: MagicMock) -> None:
    """Test that one malformed automation doesn't stop validation of others.

    Ensures the orchestration layer is fault-tolerant: if one automation
    raises an exception during analysis, other automations continue to be
    processed. This prevents a single bad automation from blocking all
    validation.
    """
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
def grouped_hass(mock_hass: MagicMock) -> MagicMock:
    """Create mock hass pre-configured with all validators for grouped tests.

    Returns a mock Home Assistant instance with all three validator families
    (state ref, jinja, service) pre-configured with mocks. Suitable for
    testing grouped validation orchestration.
    """
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
async def test_validate_all_with_groups_classification(grouped_hass: MagicMock) -> None:
    """Test that issues are classified into the correct groups.

    Verifies that grouped validation correctly routes issues from each
    validator family to its designated group:
    - entity_state: ENTITY_NOT_FOUND from state ref validator
    - templates: TEMPLATE_SYNTAX_ERROR from jinja validator
    - services: SERVICE_NOT_FOUND from service validator
    """
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
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = [service_issue]
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
    assert result["group_issues"]["runtime_health"] == []

    # All issues present in flat list
    assert len(result["all_issues"]) == 3


@pytest.mark.asyncio
async def test_validate_all_with_groups_timing(grouped_hass: MagicMock) -> None:
    """Test that each group has a non-negative duration_ms value.

    Ensures timing instrumentation works: every validation group must report
    a non-negative duration, even if no validators ran or the group was
    skipped.
    """
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
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
async def test_validate_all_with_groups_includes_skip_reason_telemetry(
    grouped_hass: MagicMock,
) -> None:
    """Run stats should include per-group skip reason telemetry."""
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].get_last_run_stats.return_value = {
        "total_calls": 2,
        "skipped_calls_by_reason": {"templated_service_name": 1},
    }

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        result = await async_validate_all_with_groups(grouped_hass)

    assert result["skip_reasons"]["services"]["templated_service_name"] == 1
    assert result["skip_reasons"]["services"]["total_calls"] == 2
    run_stats = grouped_hass.data[DOMAIN]["validation_run_stats"]
    assert run_stats["skip_reasons"]["services"]["templated_service_name"] == 1


@pytest.mark.asyncio
async def test_validate_all_with_groups_status_logic(grouped_hass: MagicMock) -> None:
    """Test group status: fail for errors, warning for warnings only, pass for clean.

    Verifies the status computation logic for validation groups:
    - Groups with ERROR severity issues -> "fail"
    - Groups with only WARNING severity issues -> "warning"
    - Groups with no issues -> "pass"
    """
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
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
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
async def test_validate_all_with_groups_empty_automations(
    grouped_hass: MagicMock,
) -> None:
    """Test that empty automation list returns empty group structure.

    When no automations exist, grouped validation should return a well-formed
    result with empty issue lists and zero durations for all groups.
    """
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
async def test_validate_automation_includes_service_validation(
    grouped_hass: MagicMock,
) -> None:
    """Test that async_validate_automation includes service validation (C1 fix).

    Previously, async_validate_automation skipped service validation entirely,
    which was a critical bug (C1 in v2.14.0). After consolidation, targeted
    automation validation now routes through the shared core which includes
    all three validator families.
    """
    # Set up a service issue
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = [service_issue]
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
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.assert_called_once()


@pytest.mark.asyncio
async def test_validate_automation_includes_all_families(
    grouped_hass: MagicMock,
) -> None:
    """Test that async_validate_automation runs all three validator families.

    Verifies that targeted automation validation (triggered by the
    validate_automation service) executes state ref, jinja, and service
    validators.
    """
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.WARNING)
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)

    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = [service_issue]
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
async def test_validate_automation_not_found(grouped_hass: MagicMock) -> None:
    """Test that async_validate_automation returns empty when automation not found.

    When the requested automation_id doesn't exist in the automation configs,
    validation should gracefully return an empty issue list rather than crash.
    """
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "other", "alias": "Other"}],
    ):
        issues = await async_validate_automation(grouped_hass, "automation.nonexistent")

    assert issues == []


@pytest.mark.asyncio
async def test_validate_all_is_thin_wrapper(grouped_hass: MagicMock) -> None:
    """Test that async_validate_all returns same issues as grouped version.

    async_validate_all is a thin wrapper that calls async_validate_all_with_groups
    and returns the flat all_issues list. This maintains backward compatibility
    with code expecting a simple list of issues.
    """
    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
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


def test_no_dedup_cross_family_function() -> None:
    """Guard: Prevent re-introduction of _dedup_cross_family (removed in v2.14.0).

    Cross-family dedup is no longer needed because jinja_validator no longer
    produces entity validation issues (entity validation path was removed).
    This guard ensures the removed code stays removed.
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


def test_build_config_snapshot() -> None:
    """Test that _build_config_snapshot returns deterministic hashes keyed by id.

    Config snapshots enable targeted validation: by hashing each automation's
    config, we can detect which specific automation changed on reload and
    validate only that one instead of all automations.
    """
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


def test_build_config_snapshot_skips_configs_without_id() -> None:
    """Test that configs without an id field are skipped in the snapshot.

    Some automations (especially legacy or UI-created ones) may lack an id.
    These must be skipped gracefully in the snapshot to avoid crashes.
    """
    from custom_components.autodoctor import _build_config_snapshot

    configs = [
        {"id": "abc", "alias": "Has ID"},
        {"alias": "No ID"},  # No 'id' key
    ]
    snapshot = _build_config_snapshot(configs)
    assert set(snapshot.keys()) == {"abc"}


@pytest.mark.asyncio
async def test_reload_listener_single_automation_change(mock_hass: MagicMock) -> None:
    """Test targeted validation: when one automation changes, validate only that one.

    This is the key optimization for reload detection: by comparing config
    snapshots before and after reload, we can identify the single changed
    automation and run targeted validation instead of validating all.
    """
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
        {
            "id": "auto_2",
            "alias": "Auto 2 CHANGED",
            "trigger": [{"platform": "time", "at": "12:00"}],
        },
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

    with (
        patch(
            "custom_components.autodoctor._get_automation_configs",
            return_value=changed_configs,
        ),
        patch(
            "custom_components.autodoctor.async_validate_automation",
            new_callable=AsyncMock,
        ) as mock_validate_auto,
        patch(
            "custom_components.autodoctor.async_validate_all",
            new_callable=AsyncMock,
        ) as mock_validate_all,
    ):
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
async def test_reload_listener_bulk_reload_validates_all(mock_hass: MagicMock) -> None:
    """Test bulk reload: when 3+ automations change, validate all instead of targeted.

    Targeted validation is only efficient when 1-2 automations change. For
    bulk changes (3+), it's more efficient to validate everything at once
    rather than running multiple targeted validations.
    """
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

    with (
        patch(
            "custom_components.autodoctor._get_automation_configs",
            return_value=changed_configs,
        ),
        patch(
            "custom_components.autodoctor.async_validate_automation",
            new_callable=AsyncMock,
        ) as mock_validate_auto,
        patch(
            "custom_components.autodoctor.async_validate_all",
            new_callable=AsyncMock,
        ) as mock_validate_all,
    ):
        _setup_reload_listener(mock_hass, debounce_seconds=0)
        listener_callback(MagicMock())
        await asyncio.sleep(0.1)

        mock_validate_all.assert_called_once()
        mock_validate_auto.assert_not_called()


@pytest.mark.asyncio
async def test_reload_listener_no_snapshot_validates_all(mock_hass: MagicMock) -> None:
    """Test first-run behavior: when no previous snapshot exists, validate all.

    On the very first automation reload after integration startup, there's no
    baseline snapshot to compare against. In this case, we validate all
    automations and create the initial snapshot.
    """
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

    with (
        patch(
            "custom_components.autodoctor._get_automation_configs",
            return_value=configs,
        ),
        patch(
            "custom_components.autodoctor.async_validate_automation",
            new_callable=AsyncMock,
        ) as mock_validate_auto,
        patch(
            "custom_components.autodoctor.async_validate_all",
            new_callable=AsyncMock,
        ) as mock_validate_all,
    ):
        _setup_reload_listener(mock_hass, debounce_seconds=0)
        listener_callback(MagicMock())
        await asyncio.sleep(0.1)

        mock_validate_all.assert_called_once()
        mock_validate_auto.assert_not_called()


@pytest.mark.asyncio
async def test_snapshot_updated_after_validation(mock_hass: MagicMock) -> None:
    """Test that snapshot in hass.data is updated after reload validation completes.

    After processing a reload event, the stored snapshot must be updated to
    reflect the new automation configs. This ensures the next reload can
    correctly diff against the current state.
    """
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

    with (
        patch(
            "custom_components.autodoctor._get_automation_configs",
            return_value=configs,
        ),
        patch(
            "custom_components.autodoctor.async_validate_all",
            new_callable=AsyncMock,
        ),
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


def test_get_automation_configs_none_returns_empty() -> None:
    """Test that _get_automation_configs returns empty list when automation domain absent.

    When Home Assistant has no automation integration loaded (automation_data
    is None), the function must return an empty list gracefully rather than
    crash. This handles installations without automations.

    Mutation coverage: Kills AddNot on `if automation_data is None`.
    """
    from custom_components.autodoctor import _get_automation_configs

    hass = MagicMock()
    hass.data = {}  # No "automation" key at all
    result = _get_automation_configs(hass)
    assert result == []


def test_get_automation_configs_dict_mode() -> None:
    """Test that _get_automation_configs extracts from dict-based automation data.

    In some HA versions or test scenarios, automation_data is a plain dict
    with a "config" key containing the list of automation configs.

    Mutation coverage: Kills isinstance(automation_data, dict) guard and
    .get("config", []) extraction.
    """
    from custom_components.autodoctor import _get_automation_configs

    configs = [{"id": "a1", "alias": "Test"}]
    hass = MagicMock()
    hass.data = {"automation": {"config": configs}}
    result = _get_automation_configs(hass)
    assert result == configs
    assert len(result) == 1


def test_get_automation_configs_entity_component_mode() -> None:
    """Test that _get_automation_configs extracts from EntityComponent-based data.

    In most production HA environments, automation_data is an EntityComponent
    instance with an .entities attribute. Each entity has a raw_config
    containing the automation's configuration.

    Mutation coverage: Kills hasattr(automation_data, "entities") guard and
    raw_config extraction loop.
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
    assert result[0]["__entity_id"] == "automation.test1"
    assert result[1]["__entity_id"] == "automation.test2"


def test_get_automation_configs_entity_without_raw_config() -> None:
    """Test that entities without raw_config are skipped gracefully.

    Some automation entities may lack the raw_config attribute or have it set
    to None. These must be filtered out to prevent crashes.

    Mutation coverage: Kills hasattr/None check guard - if mutated to 'or'
    or inverted, would crash or include invalid entries.
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
async def test_register_card_path_missing() -> None:
    """Test that card registration exits gracefully when card file doesn't exist.

    If the Lovelace card JavaScript file is missing (e.g., incomplete
    installation), registration should abort without attempting to register
    a non-existent resource.

    Mutation coverage: Kills AddNot on `if not card_path.exists()`.
    """
    from custom_components.autodoctor import _async_register_card

    hass = MagicMock()
    with patch("pathlib.Path.exists", return_value=False):
        await _async_register_card(hass)
    # http.async_register_static_paths should NOT have been called
    hass.http.async_register_static_paths.assert_not_called()


@pytest.mark.asyncio
async def test_register_card_storage_mode_creates_resource() -> None:
    """Test that card resource is created in Lovelace storage mode when not present.

    When Lovelace is in storage mode (dashboard config in .storage/), the
    card resource must be programmatically registered via the resources API.

    Mutation coverage: Kills lovelace_mode == "storage" check,
    resources.async_create_item call, and current_exists check.
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
async def test_register_card_current_version_already_registered() -> None:
    """Test that card registration is idempotent when current version exists.

    If the exact version of the card is already registered (URL matches with
    version param), no action should be taken. This prevents redundant
    updates on every HA restart.

    Mutation coverage: Kills AddNot on `if current_exists` check.
    """
    from custom_components.autodoctor import CARD_URL_BASE, _async_register_card
    from custom_components.autodoctor.const import VERSION

    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    card_url = f"{CARD_URL_BASE}?v={VERSION}"
    mock_resources = MagicMock()
    mock_resources.async_items.return_value = [{"url": card_url, "id": "existing_id"}]
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
async def test_register_card_replaces_old_version() -> None:
    """Test that old card versions are replaced with new version on upgrade.

    When upgrading the integration, old card resources (different version
    param) must be removed and the new version registered. This ensures
    browsers always load the current card code.

    Mutation coverage: Kills ZeroIterationForLoop on resource iteration and
    resource_id extraction mutations.
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
async def test_register_card_yaml_mode_skips_resources() -> None:
    """Test that card resource registration is skipped in Lovelace YAML mode.

    When Lovelace is in YAML mode (dashboard defined in configuration.yaml),
    resources must be manually added to the YAML config. Programmatic
    registration via the API doesn't work and should be skipped.

    Mutation coverage: Kills Eq on `lovelace_mode == "storage"` - if
    mutated to !=, YAML mode would incorrectly attempt registration.
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
async def test_unload_entry_cancels_debounce_task() -> None:
    """Test that unload cancels active debounce task to prevent orphaned validation.

    When the integration is unloaded (removed or reloaded), any pending
    debounced validation task must be cancelled. Otherwise it would continue
    running against a partially torn-down integration.

    Mutation coverage: Kills AddNot on debounce_task guards and cancel() call.
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
async def test_unload_entry_calls_unsub_listeners() -> None:
    """Test that unload calls unsubscribe callbacks for event listeners.

    When unloading, event listeners (reload, entity registry) must be
    unsubscribed to prevent memory leaks and callbacks firing after unload.

    Mutation coverage: Kills AddNot on `if unsub_reload is not None` and
    `if unsub_entity_reg is not None` guards.
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
async def test_unload_entry_calls_unsub_periodic_scan_listener() -> None:
    """Unload should unsubscribe periodic scan listener."""
    from custom_components.autodoctor import async_unload_entry

    hass = MagicMock()
    entry = MagicMock()
    unsub_periodic = MagicMock()

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services.async_remove = MagicMock()
    hass.data = {
        DOMAIN: {
            "debounce_task": None,
            "unsub_reload_listener": None,
            "unsub_entity_registry_listener": None,
            "unsub_periodic_scan_listener": unsub_periodic,
        }
    }

    result = await async_unload_entry(hass, entry)
    assert result is True
    unsub_periodic.assert_called_once()


@pytest.mark.asyncio
async def test_unload_entry_removes_services() -> None:
    """Test that unload removes all three registered services.

    On unload, the integration's services (validate, validate_automation,
    refresh_knowledge_base) must be removed from the service registry to
    prevent stale service calls.

    Mutation coverage: Kills mutations on service name strings and
    async_remove calls.
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


@pytest.mark.asyncio
async def test_setup_periodic_scan_listener_runs_validate_all() -> None:
    """Periodic callback should invoke async_validate_all at configured interval."""
    from custom_components.autodoctor import _setup_periodic_scan_listener

    hass = MagicMock()
    captured: dict[str, object] = {}
    unsub = MagicMock()

    def _fake_track(_hass: MagicMock, action: object, interval: timedelta) -> MagicMock:
        captured["action"] = action
        captured["interval"] = interval
        return unsub

    with (
        patch(
            "custom_components.autodoctor.async_track_time_interval",
            side_effect=_fake_track,
        ) as mock_track_interval,
        patch(
            "custom_components.autodoctor.async_validate_all", new_callable=AsyncMock
        ) as mock_validate_all,
        patch("custom_components.autodoctor._LOGGER") as mock_logger,
    ):
        result_unsub = _setup_periodic_scan_listener(hass, 6)
        callback = captured["action"]
        await callback(datetime.now(UTC))  # type: ignore[misc]

    assert result_unsub is unsub
    assert captured["interval"] == timedelta(hours=6)
    mock_track_interval.assert_called_once()
    mock_validate_all.assert_awaited_once_with(hass)
    mock_logger.debug.assert_called_once_with("Running periodic validation scan")


# --- _async_run_validators tests (mutation hardening) ---


@pytest.mark.asyncio
async def test_run_validators_failed_automation_warning(
    grouped_hass: MagicMock,
) -> None:
    """Test that failed automation count is logged when 1+ automations fail validation.

    When an automation raises an exception during analysis (e.g., malformed
    config), a warning should be logged with the count of failed automations.
    This helps users identify problematic automations without crashing
    validation.

    Mutation coverage: Kills `> 0` mutations on failed_automations check and
    counter increment.
    """
    from custom_components.autodoctor import _async_run_validators

    grouped_hass.data[DOMAIN][
        "analyzer"
    ].extract_state_references.side_effect = Exception("boom")
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch("custom_components.autodoctor._LOGGER") as mock_logger:
        await _async_run_validators(grouped_hass, [{"id": "bad", "alias": "Bad"}])

    # Warning should mention 1 failed automation
    warning_calls = [
        c for c in mock_logger.warning.call_args_list if "failed automations" in str(c)
    ]
    assert len(warning_calls) == 1
    assert "1" in str(warning_calls[0])


@pytest.mark.asyncio
async def test_run_validators_no_failures_no_warning(grouped_hass: MagicMock) -> None:
    """Test that no warning is logged when all automations validate successfully.

    When all automations process cleanly without exceptions, the failed
    automation warning should not appear in logs.

    Mutation coverage: Kills `> 0` -> `>= 0` or `> -1` mutations on
    failed_automations check.
    """
    from custom_components.autodoctor import _async_run_validators

    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []

    with patch("custom_components.autodoctor._LOGGER") as mock_logger:
        await _async_run_validators(grouped_hass, [{"id": "good", "alias": "Good"}])

    # No "failed automations" warning
    warning_calls = [
        c for c in mock_logger.warning.call_args_list if "failed automations" in str(c)
    ]
    assert len(warning_calls) == 0


@pytest.mark.asyncio
async def test_run_validators_group_durations_and_mapping(
    grouped_hass: MagicMock,
) -> None:
    """Test that group durations are valid and issue_type_to_group mapping is correct.

    Verifies:
    1. All group durations are non-negative integers (timing instrumentation)
    2. Issues are correctly mapped to groups via issue_type_to_group dict

    Mutation coverage: Kills NumberReplacer on initial duration dict, and
    ZeroIterationForLoop on VALIDATION_GROUPS iteration for mapping setup.
    """
    from custom_components.autodoctor import _async_run_validators

    # Create a real issue that should be classified
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.ERROR)
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
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
async def test_handle_validate_with_automation_id() -> None:
    """Test that validate service handler calls targeted validation when automation_id provided.

    When the validate service is called with an automation_id parameter, it
    should route to async_validate_automation for targeted validation instead
    of validating all automations.

    Mutation coverage: Kills AddNot on `if automation_id` guard.
    """
    from custom_components.autodoctor import _async_setup_services

    hass = MagicMock()
    hass.services.async_register = MagicMock()

    await _async_setup_services(hass)

    # Extract the registered handler for "validate"
    validate_handler = hass.services.async_register.call_args_list[0][0][2]

    call = MagicMock()
    call.data = {"automation_id": "automation.test123"}

    with (
        patch(
            "custom_components.autodoctor.async_validate_automation",
            new_callable=AsyncMock,
        ) as mock_targeted,
        patch(
            "custom_components.autodoctor.async_validate_all",
            new_callable=AsyncMock,
        ) as mock_all,
    ):
        await validate_handler(call)

    mock_targeted.assert_called_once_with(hass, "automation.test123")
    mock_all.assert_not_called()


@pytest.mark.asyncio
async def test_handle_refresh_with_knowledge_base() -> None:
    """Test that refresh service handler clears cache and reloads history.

    When the refresh_knowledge_base service is called, it should clear the
    knowledge base's cached learned states and reload fresh history from the
    recorder.

    Mutation coverage: Kills AddNot on `if kb` guard - if inverted,
    kb.clear_cache() and async_load_history() would never execute.
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
async def test_validate_automation_matches_correct_id(grouped_hass: MagicMock) -> None:
    """Test that targeted validation only validates the requested automation by id.

    When multiple automations exist, async_validate_automation must match
    the exact automation_id (e.g., 'automation.auto_b') and validate only
    that one, not others.

    Mutation coverage: Kills mutations on id matching logic - wrong logic
    would validate the wrong automation or skip all.
    """
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
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
        await async_validate_automation(grouped_hass, "automation.auto_b")

    # validate_automations should be called with ONLY auto_b (single-element list)
    call_args = grouped_hass.data[DOMAIN][
        "jinja_validator"
    ].validate_automations.call_args
    validated = call_args[0][0]
    assert len(validated) == 1
    assert validated[0]["id"] == "auto_b"


@pytest.mark.asyncio
async def test_handle_validate_without_automation_id() -> None:
    """Test that validate service handler calls validate_all when no automation_id provided.

    When the validate service is called without an automation_id parameter,
    it should validate all automations instead of targeted validation.

    Mutation coverage: Paired with test_handle_validate_with_automation_id
    to kill if/else branching mutations.
    """
    from custom_components.autodoctor import _async_setup_services

    hass = MagicMock()
    hass.services.async_register = MagicMock()

    await _async_setup_services(hass)

    validate_handler = hass.services.async_register.call_args_list[0][0][2]

    call = MagicMock()
    call.data = {}  # No automation_id

    with (
        patch(
            "custom_components.autodoctor.async_validate_automation",
            new_callable=AsyncMock,
        ) as mock_targeted,
        patch(
            "custom_components.autodoctor.async_validate_all",
            new_callable=AsyncMock,
        ) as mock_all,
    ):
        await validate_handler(call)

    mock_all.assert_called_once()
    mock_targeted.assert_not_called()


@pytest.mark.asyncio
async def test_validate_all_with_groups_missing_validators(
    mock_hass: MagicMock,
) -> None:
    """Test that missing validators return empty result gracefully without crash.

    If any core validators (analyzer, validator, reporter) are missing from
    hass.data (e.g., partial initialization failure), validation should
    return an empty result structure instead of crashing.

    Mutation coverage: Kills mutations on `if not all([analyzer, validator, reporter])`.
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
async def test_run_validators_skips_missing_jinja_validator(
    mock_hass: MagicMock,
) -> None:
    """Test that jinja validation is skipped gracefully when jinja_validator is None.

    Optional validators (jinja, service) may be None in degraded mode or
    early initialization. Validation should skip these groups without crash.

    Mutation coverage: Kills AddNot on `if jinja_validator` guard.
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

    result = await _async_run_validators(mock_hass, [{"id": "test", "alias": "Test"}])

    assert result["group_issues"]["templates"] == []


@pytest.mark.asyncio
async def test_run_validators_all_issues_canonical_order(
    grouped_hass: MagicMock,
) -> None:
    """Test that all_issues list combines groups in canonical VALIDATION_GROUP_ORDER.

    The flat all_issues list must combine issues from all groups in the
    canonical order: entity_state, services, templates. This ensures
    consistent ordering in UI and reports.

    Mutation coverage: Kills ZeroIterationForLoop on VALIDATION_GROUP_ORDER
    iteration and mutations on all_issues.extend ordering.
    """
    from custom_components.autodoctor import _async_run_validators

    entity_issue = _make_issue(IssueType.ENTITY_NOT_FOUND, Severity.ERROR)
    service_issue = _make_issue(IssueType.SERVICE_NOT_FOUND, Severity.ERROR)
    template_issue = _make_issue(IssueType.TEMPLATE_SYNTAX_ERROR, Severity.ERROR)

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [entity_issue]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = [
        template_issue
    ]
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = [service_issue]
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


# --- Quick task 015: Coverage improvements for __init__.py ---


@pytest.mark.asyncio
async def test_async_setup() -> None:
    """Test async_setup initializes domain data structure."""
    from custom_components.autodoctor import async_setup

    hass = MagicMock()
    hass.data = {}

    result = await async_setup(hass, {})
    assert result is True
    assert DOMAIN in hass.data


@pytest.mark.asyncio
async def test_async_setup_entry_full_lifecycle() -> None:
    """Test async_setup_entry complete setup flow with all components."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {
        "history_days": 7,
        "validate_on_reload": True,
        "debounce_seconds": 3,
        "strict_template_validation": True,
        "strict_service_validation": True,
    }
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ) as mock_register_card,
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        result = await async_setup_entry(hass, entry)
        assert result is True
        assert DOMAIN in hass.data
        data = hass.data[DOMAIN]
        assert "knowledge_base" in data
        assert "analyzer" in data
        assert "validator" in data
        assert "unsub_reload_listener" in data
        hass.bus.async_listen_once.assert_called_once()
        mock_register_card.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_no_reload_listener() -> None:
    """Test async_setup_entry with validate_on_reload=False."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {"validate_on_reload": False}
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        await async_setup_entry(hass, entry)
        assert hass.data[DOMAIN]["unsub_reload_listener"] is None


@pytest.mark.asyncio
async def test_async_setup_entry_registers_periodic_scan_listener_default_interval() -> (
    None
):
    """Periodic listener should be registered using default interval."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {"validate_on_reload": False}
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    periodic_unsub = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch(
            "custom_components.autodoctor._setup_periodic_scan_listener",
            return_value=periodic_unsub,
        ) as mock_setup_periodic,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        await async_setup_entry(hass, entry)

    mock_setup_periodic.assert_called_once_with(
        hass, DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS
    )
    assert hass.data[DOMAIN]["unsub_periodic_scan_listener"] is periodic_unsub


@pytest.mark.asyncio
async def test_async_setup_entry_registers_periodic_scan_listener_custom_interval() -> (
    None
):
    """Periodic listener should honor configured scan interval."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {"validate_on_reload": False, "periodic_scan_interval_hours": 6}
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    periodic_unsub = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch(
            "custom_components.autodoctor._setup_periodic_scan_listener",
            return_value=periodic_unsub,
        ) as mock_setup_periodic,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        await async_setup_entry(hass, entry)

    mock_setup_periodic.assert_called_once_with(hass, 6)
    assert hass.data[DOMAIN]["unsub_periodic_scan_listener"] is periodic_unsub


@pytest.mark.asyncio
async def test_async_setup_entry_runtime_monitor_enabled() -> None:
    """Runtime monitor should be initialized when runtime health is enabled."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {
        "validate_on_reload": False,
        "runtime_health_enabled": True,
        "runtime_health_hour_ratio_days": 14,
    }
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch("custom_components.autodoctor.RuntimeHealthMonitor") as mock_runtime_cls,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        await async_setup_entry(hass, entry)

    assert "runtime_monitor" in hass.data[DOMAIN]
    assert hass.data[DOMAIN]["runtime_monitor"] is mock_runtime_cls.return_value
    assert hass.data[DOMAIN]["runtime_health_enabled"] is True
    assert mock_runtime_cls.call_args.kwargs["hour_ratio_days"] == 14


@pytest.mark.asyncio
async def test_validate_all_with_groups_filters_suppressed_before_reporting_and_cache(
    grouped_hass: MagicMock,
) -> None:
    """Suppressed issues should not flow into reporter/sensor-facing cached state."""
    suppressed_issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.hidden",
        location="trigger[0]",
        message="Suppressed issue",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    visible_issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="light.visible",
        location="trigger[1]",
        message="Visible issue",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    suppression_store = MagicMock()
    suppression_store.is_suppressed = MagicMock(
        side_effect=lambda key: key == suppressed_issue.get_suppression_key()
    )

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = [
        suppressed_issue,
        visible_issue,
    ]
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].async_load_descriptions = AsyncMock()
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["suppression_store"] = suppression_store

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "test", "alias": "Test"}],
    ):
        await async_validate_all_with_groups(grouped_hass)

    reported = grouped_hass.data[DOMAIN]["reporter"].async_report_issues.call_args[0][0]
    assert suppressed_issue not in reported
    assert visible_issue in reported

    assert grouped_hass.data[DOMAIN]["validation_issues"] == [visible_issue]
    assert grouped_hass.data[DOMAIN]["validation_issues_raw"] == [
        suppressed_issue,
        visible_issue,
    ]
    assert grouped_hass.data[DOMAIN]["validation_groups"]["entity_state"]["issues"] == [
        visible_issue
    ]
    assert grouped_hass.data[DOMAIN]["validation_groups_raw"]["entity_state"][
        "issues"
    ] == [suppressed_issue, visible_issue]


@pytest.mark.asyncio
async def test_register_card_exceptions() -> None:
    """Test card registration exception handling."""
    from custom_components.autodoctor import _async_register_card

    hass = MagicMock()
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock(
        side_effect=ValueError("Already registered")
    )
    hass.data = {}

    with patch("pathlib.Path.exists", return_value=True):
        await _async_register_card(hass)

    hass.http.async_register_static_paths.assert_called_once()


@pytest.mark.asyncio
async def test_run_validators_exception_isolation() -> None:
    """Test that validator exceptions don't stop other validators."""
    from custom_components.autodoctor import _async_run_validators

    mock_hass = MagicMock()
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_jinja = MagicMock()
    mock_service = MagicMock()

    mock_jinja.validate_automations.side_effect = Exception("Jinja failed")
    mock_service.async_load_descriptions = AsyncMock()
    mock_service.validate_service_calls.return_value = []
    mock_analyzer.extract_service_calls.return_value = []
    mock_analyzer.extract_state_references.return_value = []
    mock_validator.validate_all.return_value = []

    mock_hass.data = {
        DOMAIN: {
            "analyzer": mock_analyzer,
            "validator": mock_validator,
            "jinja_validator": mock_jinja,
            "service_validator": mock_service,
        }
    }

    result = await _async_run_validators(mock_hass, [{"id": "test", "alias": "Test"}])
    mock_jinja.validate_automations.assert_called_once()
    mock_validator.validate_all.assert_called_once()
    assert result["skip_reasons"]["templates"]["validation_exception"] == 1


@pytest.mark.asyncio
async def test_run_validators_includes_runtime_health_stage(
    grouped_hass: MagicMock,
) -> None:
    """Runtime monitor issues should be routed into runtime_health group."""
    from custom_components.autodoctor import _async_run_validators

    runtime_issue = _make_issue(
        IssueType.RUNTIME_AUTOMATION_STALLED,
        Severity.ERROR,
    )
    runtime_monitor = MagicMock()
    runtime_monitor.validate_automations = AsyncMock(return_value=[runtime_issue])

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].async_load_descriptions = AsyncMock()
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["runtime_monitor"] = runtime_monitor
    grouped_hass.data[DOMAIN]["runtime_health_enabled"] = True

    result = await _async_run_validators(
        grouped_hass, [{"id": "test", "alias": "Test"}]
    )

    assert runtime_issue in result["group_issues"]["runtime_health"]
    assert result["all_issues"][-1].issue_type == IssueType.RUNTIME_AUTOMATION_STALLED


@pytest.mark.asyncio
async def test_run_validators_logs_runtime_health_disabled(
    grouped_hass: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runtime health branch should emit debug log when disabled."""
    from custom_components.autodoctor import _async_run_validators

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].async_load_descriptions = AsyncMock()
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    # runtime_health_enabled not set → defaults to False

    with caplog.at_level(logging.DEBUG, logger="custom_components.autodoctor"):
        await _async_run_validators(grouped_hass, [{"id": "test", "alias": "Test"}])

    assert any("Runtime health: enabled=False" in msg for msg in caplog.messages)
    assert any("Runtime health: disabled" in msg for msg in caplog.messages)


@pytest.mark.asyncio
async def test_run_validators_logs_runtime_health_enabled(
    grouped_hass: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runtime health branch should emit debug log when enabled and running."""
    from custom_components.autodoctor import _async_run_validators

    runtime_monitor = MagicMock()
    runtime_monitor.validate_automations = AsyncMock(return_value=[])
    runtime_monitor.get_last_run_stats.return_value = {
        "total_automations": 1,
        "insufficient_warmup": 1,
    }

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].async_load_descriptions = AsyncMock()
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["runtime_monitor"] = runtime_monitor
    grouped_hass.data[DOMAIN]["runtime_health_enabled"] = True

    with caplog.at_level(logging.DEBUG, logger="custom_components.autodoctor"):
        await _async_run_validators(grouped_hass, [{"id": "test", "alias": "Test"}])

    assert any("Runtime health: enabled=True" in msg for msg in caplog.messages)
    assert any(
        "Runtime health validation: 0 issues found" in msg for msg in caplog.messages
    )
    assert any("Runtime health stats:" in msg for msg in caplog.messages)
    assert any("insufficient_warmup" in msg for msg in caplog.messages)


@pytest.mark.asyncio
async def test_run_validators_logs_runtime_health_monitor_unavailable(
    grouped_hass: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Runtime health branch should log when enabled but monitor is unavailable."""
    from custom_components.autodoctor import _async_run_validators

    grouped_hass.data[DOMAIN]["validator"].validate_all.return_value = []
    grouped_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    grouped_hass.data[DOMAIN]["jinja_validator"].validate_automations.return_value = []
    grouped_hass.data[DOMAIN][
        "service_validator"
    ].validate_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["service_validator"].async_load_descriptions = AsyncMock()
    grouped_hass.data[DOMAIN]["analyzer"].extract_service_calls.return_value = []
    grouped_hass.data[DOMAIN]["runtime_health_enabled"] = True
    # No runtime_monitor set → None

    with caplog.at_level(logging.DEBUG, logger="custom_components.autodoctor"):
        await _async_run_validators(grouped_hass, [{"id": "test", "alias": "Test"}])

    assert any(
        "enabled=True" in msg and "monitor=None" in msg for msg in caplog.messages
    )
    assert any("enabled but monitor unavailable" in msg for msg in caplog.messages)


@pytest.mark.asyncio
async def test_run_validators_records_service_validation_exception_skip_reason() -> (
    None
):
    """Service validator exceptions should be surfaced in skip-reason telemetry."""
    from custom_components.autodoctor import _async_run_validators

    mock_hass = MagicMock()
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()
    mock_jinja = MagicMock()
    mock_service = MagicMock()

    mock_jinja.validate_automations.return_value = []
    mock_service.async_load_descriptions = AsyncMock(side_effect=RuntimeError("boom"))
    mock_analyzer.extract_state_references.return_value = []
    mock_validator.validate_all.return_value = []

    mock_hass.data = {
        DOMAIN: {
            "analyzer": mock_analyzer,
            "validator": mock_validator,
            "jinja_validator": mock_jinja,
            "service_validator": mock_service,
        }
    }

    result = await _async_run_validators(mock_hass, [{"id": "test", "alias": "Test"}])
    assert result["skip_reasons"]["services"]["validation_exception"] == 1


@pytest.mark.asyncio
async def test_run_validators_records_missing_validator_skip_reasons() -> None:
    """Missing validator families should be reflected in skip-reason telemetry."""
    from custom_components.autodoctor import _async_run_validators

    mock_hass = MagicMock()
    mock_analyzer = MagicMock()
    mock_validator = MagicMock()

    mock_analyzer.extract_state_references.return_value = []
    mock_validator.validate_all.return_value = []

    mock_hass.data = {
        DOMAIN: {
            "analyzer": mock_analyzer,
            "validator": mock_validator,
            "jinja_validator": None,
            "service_validator": None,
        }
    }

    result = await _async_run_validators(mock_hass, [{"id": "test", "alias": "Test"}])
    assert result["skip_reasons"]["templates"]["validator_unavailable"] == 1
    assert result["skip_reasons"]["services"]["validator_unavailable"] == 1


@pytest.mark.asyncio
async def test_run_validators_records_missing_entity_validator_skip_reason() -> None:
    """Missing analyzer/validator should be tracked as entity_state skip reason."""
    from custom_components.autodoctor import _async_run_validators

    mock_hass = MagicMock()
    mock_hass.data = {
        DOMAIN: {
            "analyzer": None,
            "validator": None,
            "jinja_validator": None,
            "service_validator": None,
        }
    }

    result = await _async_run_validators(
        mock_hass,
        [{"id": "test", "alias": "Test"}],
    )
    assert result["skip_reasons"]["entity_state"]["validator_unavailable"] == 1
    assert result["failed_automations"] == 0
    assert result["analyzed_automations"] == 0


@pytest.mark.asyncio
async def test_validate_all_loads_history() -> None:
    """Test that validation loads history if needed."""
    mock_hass = MagicMock()
    mock_kb = MagicMock()
    mock_kb.has_history_loaded.return_value = False
    mock_kb.async_load_history = AsyncMock()

    mock_hass.data = {
        DOMAIN: {
            "analyzer": MagicMock(),
            "validator": MagicMock(),
            "reporter": AsyncMock(),
            "knowledge_base": mock_kb,
            "jinja_validator": None,
            "service_validator": None,
        }
    }
    mock_hass.data[DOMAIN]["analyzer"].extract_state_references.return_value = []
    mock_hass.data[DOMAIN]["validator"].validate_all.return_value = []

    with patch(
        "custom_components.autodoctor._get_automation_configs",
        return_value=[{"id": "t", "alias": "T"}],
    ):
        await async_validate_all_with_groups(mock_hass)

    mock_kb.async_load_history.assert_called_once()


@pytest.mark.asyncio
async def test_validate_automation_missing_validators() -> None:
    """Test async_validate_automation with missing validators."""
    mock_hass = MagicMock()
    mock_hass.data = {DOMAIN: {"analyzer": None, "validator": None, "reporter": None}}

    result = await async_validate_automation(mock_hass, "automation.test")
    assert result == []


@pytest.mark.asyncio
async def test_options_updated_reloads() -> None:
    """Test that options update triggers reload."""
    from custom_components.autodoctor import _async_options_updated

    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_123"

    await _async_options_updated(hass, entry)
    hass.config_entries.async_reload.assert_called_once_with("test_123")


@pytest.mark.asyncio
async def test_options_updated_notifies_when_runtime_health_enabled_and_river_missing() -> (
    None
):
    """Enabling runtime health should prompt restart if river is unavailable."""
    from custom_components.autodoctor import _async_options_updated

    hass = MagicMock()
    hass.data = {DOMAIN: {"runtime_health_enabled": False}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_123"
    entry.options = {"runtime_health_enabled": True}

    with patch("custom_components.autodoctor._is_river_available", return_value=False):
        await _async_options_updated(hass, entry)

    hass.services.async_call.assert_called_once()
    args = hass.services.async_call.call_args.args
    assert args[0] == "persistent_notification"
    assert args[1] == "create"
    hass.config_entries.async_reload.assert_called_once_with("test_123")


@pytest.mark.asyncio
async def test_options_updated_no_notification_when_runtime_health_already_enabled() -> (
    None
):
    """No notification when runtime health was already enabled."""
    from custom_components.autodoctor import _async_options_updated

    hass = MagicMock()
    hass.data = {DOMAIN: {"runtime_health_enabled": True}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_123"
    entry.options = {"runtime_health_enabled": True}

    with patch("custom_components.autodoctor._is_river_available", return_value=False):
        await _async_options_updated(hass, entry)

    hass.services.async_call.assert_not_called()
    hass.config_entries.async_reload.assert_called_once_with("test_123")


@pytest.mark.asyncio
async def test_options_updated_no_notification_when_runtime_health_stays_disabled() -> (
    None
):
    """No notification when runtime health remains disabled."""
    from custom_components.autodoctor import _async_options_updated

    hass = MagicMock()
    hass.data = {DOMAIN: {"runtime_health_enabled": False}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_123"
    entry.options = {"runtime_health_enabled": False}

    with patch("custom_components.autodoctor._is_river_available", return_value=False):
        await _async_options_updated(hass, entry)

    hass.services.async_call.assert_not_called()
    hass.config_entries.async_reload.assert_called_once_with("test_123")


@pytest.mark.asyncio
async def test_options_updated_no_notification_when_river_available() -> None:
    """No notification when river is already available."""
    from custom_components.autodoctor import _async_options_updated

    hass = MagicMock()
    hass.data = {DOMAIN: {"runtime_health_enabled": False}}
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_123"
    entry.options = {"runtime_health_enabled": True}

    with patch("custom_components.autodoctor._is_river_available", return_value=True):
        await _async_options_updated(hass, entry)

    hass.services.async_call.assert_not_called()
    hass.config_entries.async_reload.assert_called_once_with("test_123")


# --- Phase 30: Fix knowledge base loading on config reload ---


@pytest.mark.asyncio
async def test_setup_calls_load_history_directly() -> None:
    """Test that async_setup_entry loads knowledge base history immediately.

    This fixes INIT-01: On config reload, EVENT_HOMEASSISTANT_STARTED has
    already fired, so the event listener never triggers. The knowledge base
    must load history during setup, not just via the event listener.

    The event listener remains as a fallback for fresh HA starts.
    """
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {"validate_on_reload": False}
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch("custom_components.autodoctor.StateKnowledgeBase") as mock_kb_cls,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        # Mock knowledge base with async_load_history
        mock_kb = MagicMock()
        mock_kb.async_load_history = AsyncMock()
        mock_kb_cls.return_value = mock_kb

        result = await async_setup_entry(hass, entry)
        assert result is True

        # The critical assertion: history should be loaded directly during setup
        # NOT via the event listener (which won't fire on reload)
        mock_kb.async_load_history.assert_called_once()


@pytest.mark.asyncio
async def test_reload_reloads_knowledge_base_history() -> None:
    """Test that config reload triggers a fresh knowledge base history load.

    Simulates the reload scenario:
    1. First setup - history loaded immediately
    2. Unload
    3. Second setup - history loaded again immediately

    This verifies the reload path works without EVENT_HOMEASSISTANT_STARTED.
    """
    from custom_components.autodoctor import async_setup_entry, async_unload_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()
    hass.services.async_remove = MagicMock()

    entry = MagicMock()
    entry.options = {"validate_on_reload": False}
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch("custom_components.autodoctor.StateKnowledgeBase") as mock_kb_cls,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        # Mock knowledge base with async_load_history
        mock_kb = MagicMock()
        mock_kb.async_load_history = AsyncMock()
        mock_kb_cls.return_value = mock_kb

        # First setup
        result1 = await async_setup_entry(hass, entry)
        assert result1 is True
        assert mock_kb.async_load_history.call_count == 1

        # Simulate unload
        await async_unload_entry(hass, entry)

        # Reset hass.data for second setup (simulates reload)
        hass.data = {}

        # Second setup (reload scenario)
        result2 = await async_setup_entry(hass, entry)
        assert result2 is True

        # History should have been loaded again during the second setup
        assert mock_kb.async_load_history.call_count == 2


# --- Phase 30: Fix single-automation validation repair deletion bug ---


@pytest.mark.asyncio
async def test_validate_automation_reports_merged_issues(
    grouped_hass: MagicMock,
) -> None:
    """Test that async_validate_automation reports merged issues to prevent repair deletion.

    When a single automation is re-validated, the reporter should receive ALL
    issues (from the target automation plus all other automations), not just
    the target automation's issues. Otherwise, reporter._clear_resolved_issues
    deletes repairs for all other automations.

    This is the fix for INIT-02 defect.
    """
    # Set up existing issues from 3 different automations in hass.data
    existing_issues = [
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.auto_a",
            automation_name="Auto A",
            entity_id="sensor.a1",
            location="trigger[0]",
            message="Issue A1",
        ),
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.auto_a",
            automation_name="Auto A",
            entity_id="sensor.a2",
            location="trigger[1]",
            message="Issue A2",
        ),
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.auto_b",
            automation_name="Auto B",
            entity_id="sensor.b1",
            location="trigger[0]",
            message="Issue B1",
        ),
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.auto_c",
            automation_name="Auto C",
            entity_id="sensor.c1",
            location="trigger[0]",
            message="Issue C1",
        ),
    ]
    grouped_hass.data[DOMAIN]["validation_issues"] = existing_issues

    # Mock _async_run_validators to return 1 new issue for auto_b
    new_auto_b_issue = ValidationIssue(
        issue_type=IssueType.ENTITY_NOT_FOUND,
        severity=Severity.ERROR,
        automation_id="automation.auto_b",
        automation_name="Auto B",
        entity_id="sensor.b_new",
        location="action[0]",
        message="New issue B",
    )

    with (
        patch(
            "custom_components.autodoctor._get_automation_configs",
            return_value=[{"id": "auto_b", "alias": "Auto B"}],
        ),
        patch(
            "custom_components.autodoctor._async_run_validators",
            new_callable=AsyncMock,
        ) as mock_run_validators,
    ):
        mock_run_validators.return_value = {
            "all_issues": [new_auto_b_issue],
            "group_issues": {
                "entity_state": [new_auto_b_issue],
                "templates": [],
                "services": [],
            },
            "group_durations": {"entity_state": 0, "templates": 0, "services": 0},
            "timestamp": "2026-02-06T00:00:00Z",
        }

        await async_validate_automation(grouped_hass, "automation.auto_b")

    # Critical assertion: reporter.async_report_issues should have been called with
    # ALL 4 issues (2 from auto_a, 1 new from auto_b, 1 from auto_c)
    reporter_call_args = grouped_hass.data[DOMAIN][
        "reporter"
    ].async_report_issues.call_args
    reported_issues = reporter_call_args[0][0]

    assert len(reported_issues) == 4, f"Expected 4 issues, got {len(reported_issues)}"

    # Verify the merged set contains issues from all automations
    auto_a_issues = [
        i for i in reported_issues if i.automation_id == "automation.auto_a"
    ]
    auto_b_issues = [
        i for i in reported_issues if i.automation_id == "automation.auto_b"
    ]
    auto_c_issues = [
        i for i in reported_issues if i.automation_id == "automation.auto_c"
    ]

    assert len(auto_a_issues) == 2, "Should preserve 2 auto_a issues"
    assert len(auto_b_issues) == 1, "Should have 1 new auto_b issue"
    assert len(auto_c_issues) == 1, "Should preserve 1 auto_c issue"

    # The new auto_b issue should be present
    assert new_auto_b_issue in reported_issues


@pytest.mark.asyncio
async def test_validate_automation_preserves_other_repairs(
    grouped_hass: MagicMock,
) -> None:
    """Test that validating an automation with no issues doesn't wipe other repairs.

    When an automation is re-validated and has NO issues (empty result), the
    reporter should still receive issues from all OTHER automations, preserving
    their repair entries. This is an edge case of the INIT-02 fix.
    """
    # Set up existing issues from automations A and C
    existing_issues = [
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.auto_a",
            automation_name="Auto A",
            entity_id="sensor.a1",
            location="trigger[0]",
            message="Issue A1",
        ),
        ValidationIssue(
            issue_type=IssueType.ENTITY_NOT_FOUND,
            severity=Severity.ERROR,
            automation_id="automation.auto_c",
            automation_name="Auto C",
            entity_id="sensor.c1",
            location="trigger[0]",
            message="Issue C1",
        ),
    ]
    grouped_hass.data[DOMAIN]["validation_issues"] = existing_issues

    # Validate automation B which has NO issues (empty result)
    with (
        patch(
            "custom_components.autodoctor._get_automation_configs",
            return_value=[{"id": "auto_b", "alias": "Auto B"}],
        ),
        patch(
            "custom_components.autodoctor._async_run_validators",
            new_callable=AsyncMock,
        ) as mock_run_validators,
    ):
        mock_run_validators.return_value = {
            "all_issues": [],  # Empty - no issues for auto_b
            "group_issues": {"entity_state": [], "templates": [], "services": []},
            "group_durations": {"entity_state": 0, "templates": 0, "services": 0},
            "timestamp": "2026-02-06T00:00:00Z",
        }

        await async_validate_automation(grouped_hass, "automation.auto_b")

    # Reporter should still receive auto_a and auto_c issues
    reporter_call_args = grouped_hass.data[DOMAIN][
        "reporter"
    ].async_report_issues.call_args
    reported_issues = reporter_call_args[0][0]

    assert len(reported_issues) == 2, (
        f"Expected 2 issues preserved, got {len(reported_issues)}"
    )

    # Verify A and C issues are preserved
    auto_a_issues = [
        i for i in reported_issues if i.automation_id == "automation.auto_a"
    ]
    auto_c_issues = [
        i for i in reported_issues if i.automation_id == "automation.auto_c"
    ]

    assert len(auto_a_issues) == 1, "Should preserve auto_a issue"
    assert len(auto_c_issues) == 1, "Should preserve auto_c issue"

    # Verify hass.data also has the preserved issues
    assert len(grouped_hass.data[DOMAIN]["validation_issues"]) == 2


@pytest.mark.asyncio
async def test_async_setup_entry_logs_runtime_config_enabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup should log runtime monitor config when enabled."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {
        "validate_on_reload": False,
        "runtime_health_enabled": True,
        "runtime_health_baseline_days": 30,
    }
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.autodoctor"),
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch("custom_components.autodoctor.RuntimeHealthMonitor"),
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        await async_setup_entry(hass, entry)

    assert "Runtime health monitoring enabled" in caplog.text


@pytest.mark.asyncio
async def test_async_setup_entry_logs_runtime_config_disabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup should log when runtime health is disabled."""
    from custom_components.autodoctor import async_setup_entry

    hass = MagicMock()
    hass.data = {}
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()
    hass.bus.async_listen = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.options = {
        "validate_on_reload": False,
        "runtime_health_enabled": False,
    }
    entry.add_update_listener = MagicMock(return_value=None)
    entry.async_on_unload = MagicMock()

    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.autodoctor"),
        patch("custom_components.autodoctor.SuppressionStore") as mock_suppression_cls,
        patch("custom_components.autodoctor.LearnedStatesStore") as mock_learned_cls,
        patch(
            "custom_components.autodoctor._async_register_card", new_callable=AsyncMock
        ),
        patch(
            "custom_components.autodoctor.async_setup_websocket_api",
            new_callable=AsyncMock,
        ),
    ):
        mock_suppression = AsyncMock()
        mock_suppression.async_load = AsyncMock()
        mock_suppression_cls.return_value = mock_suppression

        mock_learned = AsyncMock()
        mock_learned.async_load = AsyncMock()
        mock_learned_cls.return_value = mock_learned

        await async_setup_entry(hass, entry)

    assert "Runtime health monitoring disabled" in caplog.text
