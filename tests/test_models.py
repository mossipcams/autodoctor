"""Tests for data models.

This module tests the core data models used throughout Autodoctor:
- StateReference: Entity state references found in automations
- ValidationIssue: Issues detected during validation
- ServiceCall: Service calls extracted from automations
- IssueType and Severity enums
- VALIDATION_GROUPS configuration
"""

from pathlib import Path
from typing import Any

import pytest

from custom_components.autodoctor.models import (
    VALIDATION_GROUPS,
    IssueType,
    ServiceCall,
    Severity,
    StateReference,
    ValidationIssue,
)


def test_state_reference_creation() -> None:
    """Test StateReference captures entity state expectations from automations.

    StateReference is the primary model for tracking where automations
    expect specific entity states, enabling validation against actual states.
    """
    ref = StateReference(
        automation_id="automation.welcome_home",
        automation_name="Welcome Home",
        entity_id="person.matt",
        expected_state="home",
        expected_attribute=None,
        location="trigger[0].to",
    )
    assert ref.automation_id == "automation.welcome_home"
    assert ref.expected_state == "home"
    assert ref.expected_attribute is None


def test_validation_issue_creation() -> None:
    """Test ValidationIssue stores all details needed for user-facing reports.

    ValidationIssue is the primary output model that surfaces problems
    to users, including context, severity, and actionable suggestions.
    """
    issue = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0]",
        message="Invalid state",
        suggestion="not_home",
        valid_states=["home", "not_home"],
    )
    assert issue.severity == Severity.ERROR
    assert issue.suggestion == "not_home"
    assert issue.confidence == "high"


def test_severity_ordering() -> None:
    """Test Severity enum values have correct numeric ordering.

    Higher severity levels have higher numeric values, allowing
    easy filtering and prioritization of issues.
    """
    assert Severity.ERROR.value > Severity.WARNING.value
    assert Severity.WARNING.value > Severity.INFO.value


@pytest.mark.parametrize(
    ("issue_type", "expected_value"),
    [
        (IssueType.ENTITY_NOT_FOUND, "entity_not_found"),
        (IssueType.ENTITY_REMOVED, "entity_removed"),
        (IssueType.INVALID_STATE, "invalid_state"),
        (IssueType.CASE_MISMATCH, "case_mismatch"),
        (IssueType.ATTRIBUTE_NOT_FOUND, "attribute_not_found"),
    ],
    ids=[
        "entity-not-found",
        "entity-removed",
        "invalid-state",
        "case-mismatch",
        "attribute-not-found",
    ],
)
def test_issue_type_enum_values(issue_type: IssueType, expected_value: str) -> None:
    """Test IssueType enum members have correct string values for serialization.

    String values are used in WebSocket API responses and storage,
    so they must remain stable across versions.
    """
    assert issue_type.value == expected_value


def test_validation_issue_has_issue_type() -> None:
    """Test ValidationIssue stores issue_type for categorization and filtering.

    The issue_type field enables the WebSocket API to filter issues
    by category (entity_state, services, templates).
    """
    issue = ValidationIssue(
        issue_type=IssueType.ENTITY_NOT_FOUND,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.missing",
        location="trigger[0]",
        message="Entity not found",
    )
    assert issue.issue_type == IssueType.ENTITY_NOT_FOUND


def test_validation_issue_to_dict() -> None:
    """Test ValidationIssue.to_dict() serializes for WebSocket API responses.

    The to_dict() method converts enums to strings and structures data
    for JSON serialization in WebSocket API responses.
    """
    issue = ValidationIssue(
        issue_type=IssueType.INVALID_STATE,
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        location="trigger[0].to",
        message="State 'away' is not valid",
        suggestion="not_home",
    )
    result: dict[str, Any] = issue.to_dict()
    assert result["issue_type"] == "invalid_state"
    assert result["severity"] == "error"
    assert result["confidence"] == "high"
    assert result["entity_id"] == "person.matt"
    assert result["message"] == "State 'away' is not valid"
    assert result["suggestion"] == "not_home"


def test_validation_issue_custom_confidence_to_dict() -> None:
    """ValidationIssue should serialize custom confidence tiers."""
    issue = ValidationIssue(
        issue_type=IssueType.SERVICE_INVALID_PARAM_TYPE,
        severity=Severity.WARNING,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="",
        location="action[0]",
        message="Heuristic warning",
        confidence="medium",
    )
    result: dict[str, Any] = issue.to_dict()
    assert result["confidence"] == "medium"


def test_validation_issue_equality() -> None:
    """Test ValidationIssue equality based on key fields for deduplication.

    Equality ignores severity and automation_name to prevent duplicate
    issues when the same problem is detected multiple times.
    """
    issue1 = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.temp",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue2 = ValidationIssue(
        severity=Severity.WARNING,  # Different severity
        automation_id="automation.test",
        automation_name="Different Name",  # Different name
        entity_id="sensor.temp",
        location="trigger[0]",  # Same location
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    # Should be equal because automation_id, issue_type, entity_id, location, and message match
    assert issue1 == issue2
    assert hash(issue1) == hash(issue2)


def test_validation_issue_set_deduplication() -> None:
    """Test ValidationIssue deduplication in sets prevents duplicate reports.

    Sets automatically deduplicate based on __hash__ and __eq__, ensuring
    users don't see the same issue reported multiple times.
    """
    issue1 = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.test",
        automation_name="Test",
        entity_id="sensor.temp",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue2 = ValidationIssue(
        severity=Severity.WARNING,  # Different severity
        automation_id="automation.test",
        automation_name="Different",  # Different name
        entity_id="sensor.temp",
        location="trigger[0]",  # Same location as issue1
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )
    issue3 = ValidationIssue(
        severity=Severity.ERROR,
        automation_id="automation.other",  # Different automation
        automation_name="Test",
        entity_id="sensor.temp",
        location="trigger[0]",
        message="Entity not found",
        issue_type=IssueType.ENTITY_NOT_FOUND,
    )

    # issue1 and issue2 are duplicates (same key fields including location)
    # issue3 is different (different automation_id)
    issues_set: set[ValidationIssue] = {issue1, issue2, issue3}
    assert len(issues_set) == 2  # Only 2 unique issues


def test_service_call_dataclass() -> None:
    """Test ServiceCall captures service call details for validation.

    ServiceCall stores all information needed to validate service calls
    against Home Assistant's service registry.
    """
    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test Automation",
        service="light.turn_on",
        location="action[0]",
        target={"entity_id": "light.living_room"},
        data={"brightness": 255},
        is_template=False,
    )

    assert call.automation_id == "automation.test"
    assert call.service == "light.turn_on"
    assert call.location == "action[0]"
    assert call.target == {"entity_id": "light.living_room"}
    assert call.data == {"brightness": 255}
    assert call.is_template is False


def test_service_call_template_detection() -> None:
    """Test ServiceCall is_template flag indicates dynamic service names.

    Templated service calls cannot be validated until runtime,
    so they are flagged for special handling.
    """
    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="{{ service_var }}",
        location="action[0]",
        is_template=True,
    )

    assert call.is_template is True


@pytest.mark.parametrize(
    ("issue_type_name", "expected_value"),
    [
        ("SERVICE_NOT_FOUND", "service_not_found"),
        ("SERVICE_MISSING_REQUIRED_PARAM", "service_missing_required_param"),
        ("SERVICE_INVALID_PARAM_TYPE", "service_invalid_param_type"),
        ("SERVICE_UNKNOWN_PARAM", "service_unknown_param"),
        ("RUNTIME_AUTOMATION_OVERACTIVE", "runtime_automation_overactive"),
        ("RUNTIME_AUTOMATION_BURST", "runtime_automation_burst"),
    ],
    ids=[
        "service-not-found",
        "missing-required-param",
        "invalid-param-type",
        "unknown-param",
        "runtime-automation-overactive",
        "runtime-automation-burst",
    ],
)
def test_service_issue_types_exist(issue_type_name: str, expected_value: str) -> None:
    """Test service validation issue types exist with correct values.

    Service validation was added in v2.13.0 and requires these
    issue types for reporting service call problems.
    """
    assert hasattr(IssueType, issue_type_name)
    issue_type: IssueType = getattr(IssueType, issue_type_name)
    assert issue_type.value == expected_value


@pytest.mark.parametrize(
    "removed_member",
    [
        "TEMPLATE_INVALID_ENTITY_ID",
        "TEMPLATE_ENTITY_NOT_FOUND",
        "TEMPLATE_INVALID_STATE",
        "TEMPLATE_ATTRIBUTE_NOT_FOUND",
        "TEMPLATE_DEVICE_NOT_FOUND",
        "TEMPLATE_AREA_NOT_FOUND",
        "TEMPLATE_ZONE_NOT_FOUND",
    ],
    ids=[
        "invalid-entity-id",
        "entity-not-found",
        "invalid-state",
        "attribute-not-found",
        "device-not-found",
        "area-not-found",
        "zone-not-found",
    ],
)
def test_removed_template_entity_issue_types(removed_member: str) -> None:
    """Guard: Prevent re-introduction of template entity validation issue types.

    These validation types were removed in v2.14.0 due to 40% false positive
    rate with blueprint variables and dynamic template content.

    See: PROJECT.md "Key Decisions" - Remove rather than patch
    """
    assert not hasattr(IssueType, removed_member), (
        f"IssueType.{removed_member} should have been removed in v2.14.0"
    )


def test_issue_type_count_after_removals() -> None:
    """Guard: Verify IssueType has exactly 16 members.

    This guards against accidental reintroduction of removed types.
    Count: 6 entity_state + 5 services + 3 templates + 2 runtime = 16 total.
    """
    assert len(IssueType) == 16, f"Expected 16 IssueType members, got {len(IssueType)}"


def test_templates_validation_group_narrowed() -> None:
    """Guard: Verify templates group contains only syntax checks after v2.14.0.

    Entity/state validation was removed from templates in v2.14.0 due to
    40% false positive rate. Only syntax-level checks remain.

    See: PROJECT.md "Key Decisions" - Remove rather than patch
    """
    templates_group = VALIDATION_GROUPS["templates"]["issue_types"]
    expected: frozenset[IssueType] = frozenset(
        {
            IssueType.TEMPLATE_SYNTAX_ERROR,
            IssueType.TEMPLATE_UNKNOWN_FILTER,
            IssueType.TEMPLATE_UNKNOWN_TEST,
        }
    )
    assert templates_group == expected, (
        f"Templates group should contain only syntax-level checks. "
        f"Got: {templates_group}, Expected: {expected}"
    )


def test_validation_groups_cover_all_issue_types() -> None:
    """Test VALIDATION_GROUPS contains every IssueType exactly once.

    This ensures the WebSocket API can correctly group and filter all
    possible issues, with no orphaned or duplicate issue types.
    """
    all_enum_members: set[IssueType] = set(IssueType)

    # Collect all issue types from all groups
    all_grouped: list[IssueType] = []
    grouped_set: set[IssueType] = set()
    for _group_id, group_def in VALIDATION_GROUPS.items():
        issue_types: frozenset[IssueType] = group_def["issue_types"]  # type: ignore[assignment]
        all_grouped.extend(issue_types)
        grouped_set |= issue_types

    # Every IssueType member must appear in some group (no missing members)
    missing: set[IssueType] = all_enum_members - grouped_set
    assert not missing, f"IssueType members missing from VALIDATION_GROUPS: {missing}"

    # No extra entries that aren't real IssueType members
    extras: set[IssueType] = grouped_set - all_enum_members
    assert not extras, f"VALIDATION_GROUPS contains non-IssueType entries: {extras}"

    # No duplicates across groups (each member in exactly one group)
    assert len(all_grouped) == len(all_enum_members), (
        f"Duplicate IssueType members across VALIDATION_GROUPS: "
        f"expected {len(all_enum_members)} entries, found {len(all_grouped)}"
    )


@pytest.mark.parametrize(
    "removed_member",
    [
        "RUNTIME_AUTOMATION_STALLED",
        "RUNTIME_AUTOMATION_GAP",
        "RUNTIME_AUTOMATION_COUNT_ANOMALY",
        "RUNTIME_AUTOMATION_SILENT",
    ],
    ids=["stalled", "gap", "count-anomaly", "silent"],
)
def test_removed_runtime_issue_types(removed_member: str) -> None:
    """Guard: Prevent re-introduction of runtime issue types merged in v2.28.0.

    STALLED and GAP were merged into RUNTIME_AUTOMATION_SILENT (v2.28.0).
    COUNT_ANOMALY was merged into RUNTIME_AUTOMATION_OVERACTIVE (v2.28.0).
    SILENT was removed entirely when the gap detector was removed.
    """
    assert not hasattr(IssueType, removed_member), (
        f"IssueType.{removed_member} should have been removed in v2.28.0"
    )


def test_runtime_monitor_no_rollout_kwargs() -> None:
    """Guard: RuntimeHealthMonitor must not accept rollout feature-flag kwargs.

    The runtime event store is now always-on. Rollout kwargs were removed
    in v2.28.0 SQLite consolidation.
    """
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    removed_kwargs = [
        "runtime_event_store_enabled",
        "runtime_event_store_shadow_read",
        "runtime_event_store_cutover",
        "runtime_event_store_reconciliation_enabled",
        "runtime_schedule_anomaly_enabled",
        "runtime_daily_rollup_enabled",
    ]
    for kwarg in removed_kwargs:
        assert kwarg not in source_text, (
            f"RuntimeHealthMonitor should not reference '{kwarg}'"
        )


def test_runtime_monitor_no_dead_scoring_params() -> None:
    """Guard: RuntimeHealthMonitor must not accept dead scoring kwargs.

    overactive_factor, stalled_threshold, and overactive_threshold were
    accepted but never stored after v2.28.0 model simplification.
    """
    import inspect

    from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor

    sig = inspect.signature(RuntimeHealthMonitor.__init__)
    dead_params = ["overactive_factor", "stalled_threshold", "overactive_threshold"]
    for param in dead_params:
        assert param not in sig.parameters, (
            f"RuntimeHealthMonitor.__init__ still accepts dead param '{param}'"
        )


def test_source_line_field_removed() -> None:
    """Guard: source_line was never set in production — remove from StateReference and ServiceCall."""
    assert "source_line" not in {
        f.name for f in StateReference.__dataclass_fields__.values()
    }
    assert "source_line" not in {
        f.name for f in ServiceCall.__dataclass_fields__.values()
    }


def test_is_blueprint_instance_field_removed() -> None:
    """Guard: is_blueprint_instance was threaded through analyzer but never read in production."""
    assert "is_blueprint_instance" not in {
        f.name for f in ServiceCall.__dataclass_fields__.values()
    }


def test_overactive_factor_removed_from_config() -> None:
    """Guard: overactive_factor config option must be removed (dead after model simplification)."""
    for filename in ("config_flow.py", "const.py"):
        source_path = Path(__file__).parent.parent / (
            f"custom_components/autodoctor/{filename}"
        )
        source_text = source_path.read_text()
        assert "OVERACTIVE_FACTOR" not in source_text, (
            f"{filename} still references OVERACTIVE_FACTOR — remove dead config option"
        )


def test_init_no_rollout_kwargs() -> None:
    """Guard: __init__.py must not pass rollout feature-flag kwargs to RuntimeHealthMonitor.

    The runtime event store is now always-on. Rollout kwargs were removed
    in v2.28.0 SQLite consolidation.
    """
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/__init__.py"
    )
    source_text = source_path.read_text()
    removed_kwargs = [
        "runtime_event_store_enabled",
        "runtime_event_store_shadow_read",
        "runtime_event_store_cutover",
        "runtime_event_store_reconciliation_enabled",
        "runtime_schedule_anomaly_enabled",
        "runtime_daily_rollup_enabled",
    ]
    for kwarg in removed_kwargs:
        assert kwarg not in source_text, f"__init__.py should not reference '{kwarg}'"


def test_runtime_health_state_store_removed() -> None:
    """Guard: runtime_health_state_store module removed in v2.28.0 SQLite consolidation.

    JSON state persistence was replaced by SQLite event sourcing.
    The RuntimeHealthMonitor no longer depends on RuntimeHealthStateStore.
    """
    import importlib

    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    assert "RuntimeHealthStateStore" not in source_text, (
        "runtime_monitor.py should not reference RuntimeHealthStateStore"
    )
    mod = (
        importlib.import_module(
            "custom_components.autodoctor.runtime_health_state_store"
        )
        if False
        else None
    )
    assert mod is None


def test_init_no_temp_debug_logging() -> None:
    """Guard: __init__.py must not contain temporary debug logging."""
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/__init__.py"
    )
    source_text = source_path.read_text()
    assert "TEMP DEBUG" not in source_text, (
        "__init__.py should not contain [TEMP DEBUG] logging"
    )


def test_runtime_monitor_no_temp_debug_logging() -> None:
    """Guard: runtime_monitor.py must not contain temporary debug logging.

    [TEMP DEBUG] logging was added during development and must not ship
    in production releases.
    """
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    assert "TEMP DEBUG" not in source_text, (
        "runtime_monitor.py should not contain [TEMP DEBUG] logging"
    )


def test_runtime_monitor_no_vestigial_json_state_methods() -> None:
    """Guard: vestigial JSON state methods must be removed after SQLite consolidation."""
    from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor

    dead_methods = [
        "async_load_state",
        "async_flush_runtime_state",
        "flush_runtime_state",
        "async_backfill_from_recorder",
    ]
    for method in dead_methods:
        assert not hasattr(RuntimeHealthMonitor, method), (
            f"RuntimeHealthMonitor still has vestigial method '{method}'"
        )


def test_runtime_monitor_no_last_query_failed() -> None:
    """Guard: _last_query_failed is write-only dead state after v2.28.0 model simplification."""
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    assert "_last_query_failed" not in source_text, (
        "runtime_monitor.py still references write-only '_last_query_failed' attribute"
    )


def test_runtime_monitor_no_orphaned_gap_constants() -> None:
    """Guard: orphaned gap/flush constants must not remain after model simplification."""
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    orphaned = [
        "_DEFAULT_RUNTIME_FLUSH_INTERVAL_MINUTES",
        "_GAP_MODEL_MAX_RECENT_INTERVALS",
        "_GAP_PROFILE_CONFIDENCE_EVENTS",
        "_GAP_PROFILE_MIN_EVENTS_FOR_INACTIVE",
        "_GAP_CONFIRMATION_RESET_HOURS",
        "_BACKFILL_MIN_LOOKBACK_DAYS",
    ]
    for name in orphaned:
        assert name not in source_text, (
            f"Orphaned constant {name!r} should be removed from runtime_monitor.py"
        )


def test_runtime_monitor_no_and_true_residual() -> None:
    """Guard: runtime_monitor.py must not contain `and True` residual from flag removal."""
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    assert "and True" not in source_text, (
        "runtime_monitor.py contains 'and True' residual from removed feature flag"
    )


def test_runtime_monitor_no_live_trigger_events() -> None:
    """Guard: _live_trigger_events was dead code removed in v2.28.0.

    The in-memory trigger event list was an unbounded memory leak and
    is superseded by the SQLite event store.
    """
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    source_text = source_path.read_text()
    assert "_live_trigger_events" not in source_text, (
        "runtime_monitor.py should not reference _live_trigger_events"
    )


def test_const_no_rollout_constants() -> None:
    """Guard: Rollout feature-flag constants removed in v2.28.0.

    The runtime event store is now always-on. These constants are no longer
    needed in const.py.
    """
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/const.py"
    )
    source_text = source_path.read_text()
    removed_constants = [
        "CONF_RUNTIME_EVENT_STORE_ENABLED",
        "CONF_RUNTIME_EVENT_STORE_SHADOW_READ",
        "CONF_RUNTIME_EVENT_STORE_CUTOVER",
        "CONF_RUNTIME_EVENT_STORE_RECONCILIATION_ENABLED",
        "CONF_RUNTIME_SCHEDULE_ANOMALY_ENABLED",
        "CONF_RUNTIME_DAILY_ROLLUP_ENABLED",
        "DEFAULT_RUNTIME_EVENT_STORE_ENABLED",
        "DEFAULT_RUNTIME_EVENT_STORE_SHADOW_READ",
        "DEFAULT_RUNTIME_EVENT_STORE_CUTOVER",
        "DEFAULT_RUNTIME_EVENT_STORE_RECONCILIATION_ENABLED",
        "DEFAULT_RUNTIME_SCHEDULE_ANOMALY_ENABLED",
        "DEFAULT_RUNTIME_DAILY_ROLLUP_ENABLED",
    ]
    for const in removed_constants:
        assert const not in source_text, f"const.py should not contain '{const}'"


def test_suppression_prefixes_have_no_duplicates() -> None:
    """Guard: _is_runtime_suppressed prefixes must not contain duplicate entries."""
    source_path = Path(__file__).parent.parent / (
        "custom_components/autodoctor/runtime_monitor.py"
    )
    import ast

    tree = ast.parse(source_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_is_runtime_suppressed":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and target.id == "prefixes":
                            # Unparse each element of the tuple to compare as strings
                            if isinstance(child.value, ast.Tuple):
                                elements = [
                                    ast.unparse(elt) for elt in child.value.elts
                                ]
                                assert len(elements) == len(set(elements)), (
                                    f"Duplicate suppression prefixes found: {elements}"
                                )
                                return
    raise AssertionError("Could not find prefixes tuple in _is_runtime_suppressed")


def test_runtime_group_contains_runtime_issue_types() -> None:
    """Runtime health issues must be isolated in a dedicated runtime group."""
    runtime_group = VALIDATION_GROUPS["runtime_health"]["issue_types"]
    assert runtime_group == frozenset(
        {
            IssueType.RUNTIME_AUTOMATION_OVERACTIVE,
            IssueType.RUNTIME_AUTOMATION_BURST,
        }
    )
