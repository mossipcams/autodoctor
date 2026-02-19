"""Guard tests ensuring gap detector has been removed from runtime monitor."""

from __future__ import annotations

from custom_components.autodoctor.runtime_monitor import RuntimeHealthMonitor


def test_gap_detector_removed() -> None:
    """Gap detector was removed - check_gap_anomalies should not exist."""
    assert not hasattr(RuntimeHealthMonitor, "check_gap_anomalies"), (
        "check_gap_anomalies should have been removed"
    )


def test_bucket_duration_minutes_removed() -> None:
    """_BUCKET_DURATION_MINUTES was only used by gap detector and should be removed."""
    assert not hasattr(RuntimeHealthMonitor, "_BUCKET_DURATION_MINUTES"), (
        "_BUCKET_DURATION_MINUTES should have been removed"
    )


def test_dow_counts_removed_from_automation_state() -> None:
    """dow_counts was only used by gap detector and should be removed."""
    state = RuntimeHealthMonitor._empty_automation_state()
    assert "dow_counts" not in state, "dow_counts should have been removed"


def test_gap_threshold_multiplier_not_an_attribute() -> None:
    """gap_threshold_multiplier was only used by gap detector and should be removed."""
    import inspect

    sig = inspect.signature(RuntimeHealthMonitor.__init__)
    assert "gap_threshold_multiplier" not in sig.parameters, (
        "gap_threshold_multiplier parameter should have been removed"
    )


def test_gap_adaptation_keys_removed() -> None:
    """Gap-related adaptation keys should not exist in automation state."""
    state = RuntimeHealthMonitor._empty_automation_state()
    adaptation = state["adaptation"]
    for key in (
        "gap_threshold_multiplier",
        "gap_confirmation_required",
        "gap_recovery_events",
    ):
        assert key not in adaptation, f"adaptation['{key}'] should have been removed"


def test_reconcile_runtime_alert_surfaces_removed() -> None:
    """_async_reconcile_runtime_alert_surfaces was only called from gap listener."""
    import custom_components.autodoctor.__init__ as init_mod

    assert not hasattr(init_mod, "_async_reconcile_runtime_alert_surfaces"), (
        "_async_reconcile_runtime_alert_surfaces should have been removed "
        "— its only caller was the gap check listener"
    )


def test_replace_runtime_issues_removed() -> None:
    """_replace_runtime_issues was only called from reconcile function."""
    import custom_components.autodoctor.__init__ as init_mod

    assert not hasattr(init_mod, "_replace_runtime_issues"), (
        "_replace_runtime_issues should have been removed "
        "— its only caller was _async_reconcile_runtime_alert_surfaces"
    )


def test_runtime_issue_types_constant_removed() -> None:
    """_RUNTIME_ISSUE_TYPES was only used by reconcile function."""
    import custom_components.autodoctor.__init__ as init_mod

    assert not hasattr(init_mod, "_RUNTIME_ISSUE_TYPES"), (
        "_RUNTIME_ISSUE_TYPES should have been removed "
        "— its only consumer was _replace_runtime_issues"
    )


def test_record_issue_dismissed_does_not_write_gap_keys() -> None:
    """record_issue_dismissed should not write gap-related adaptation keys."""
    from unittest.mock import MagicMock

    hass = MagicMock()
    hass.create_task = MagicMock(side_effect=lambda coro, *a, **kw: coro.close())
    monitor = RuntimeHealthMonitor(hass, warmup_samples=0, min_expected_events=0)
    monitor.record_issue_dismissed("automation.test")
    state = monitor.get_runtime_state()
    adaptation = state["automations"]["automation.test"]["adaptation"]
    assert "gap_threshold_multiplier" not in adaptation
    assert "gap_confirmation_required" not in adaptation
    assert "gap_recovery_events" not in adaptation
