"""Autodoctor integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .analyzer import AutomationAnalyzer
from .const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_HISTORY_DAYS,
    CONF_PERIODIC_SCAN_INTERVAL_HOURS,
    CONF_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
    CONF_RUNTIME_HEALTH_AUTO_ADAPT,
    CONF_RUNTIME_HEALTH_BASELINE_DAYS,
    CONF_RUNTIME_HEALTH_BURST_MULTIPLIER,
    CONF_RUNTIME_HEALTH_ENABLED,
    CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
    CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY,
    CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
    CONF_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
    CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES,
    CONF_RUNTIME_HEALTH_SENSITIVITY,
    CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW,
    CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
    CONF_STRICT_SERVICE_VALIDATION,
    CONF_STRICT_TEMPLATE_VALIDATION,
    CONF_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS,
    DEFAULT_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
    DEFAULT_RUNTIME_HEALTH_AUTO_ADAPT,
    DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS,
    DEFAULT_RUNTIME_HEALTH_BURST_MULTIPLIER,
    DEFAULT_RUNTIME_HEALTH_ENABLED,
    DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
    DEFAULT_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY,
    DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
    DEFAULT_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
    DEFAULT_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES,
    DEFAULT_RUNTIME_HEALTH_SENSITIVITY,
    DEFAULT_RUNTIME_HEALTH_SMOOTHING_WINDOW,
    DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES,
    DEFAULT_STRICT_SERVICE_VALIDATION,
    DEFAULT_STRICT_TEMPLATE_VALIDATION,
    DEFAULT_VALIDATE_ON_RELOAD,
    DOMAIN,
    VERSION,
)
from .jinja_validator import JinjaValidator
from .knowledge_base import StateKnowledgeBase
from .learned_states_store import LearnedStatesStore
from .models import (
    VALIDATION_GROUP_ORDER,
    VALIDATION_GROUPS,
    IssueType,
    ValidationIssue,
)
from .reporter import IssueReporter
from .runtime_monitor import RuntimeHealthMonitor
from .service_validator import ServiceCallValidator
from .suppression_store import SuppressionStore
from .validator import ValidationEngine
from .websocket_api import async_setup_websocket_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

# Frontend card
CARD_URL_BASE = "/autodoctor/autodoctor-card.js"

# Service schemas
SERVICE_VALIDATE_SCHEMA = vol.Schema(
    {
        vol.Optional("automation_id"): cv.entity_id,
    }
)

SERVICE_REFRESH_SCHEMA = vol.Schema({})  # No parameters


def _build_config_snapshot(configs: list[dict[str, Any]]) -> dict[str, str]:
    """Build a snapshot of automation configs for change detection.

    Returns a dict mapping automation id -> MD5 hex digest of the config.
    Configs without an 'id' field are skipped.
    """
    snapshot: dict[str, str] = {}
    for config in configs:
        auto_id = config.get("id")
        if auto_id is None:
            continue
        config_str = json.dumps(config, sort_keys=True, default=str)
        snapshot[auto_id] = hashlib.md5(config_str.encode()).hexdigest()
    return snapshot


def _get_automation_configs(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get automation configurations from Home Assistant.

    The automation component stores data as an EntityComponent, not a plain dict.
    This helper properly extracts the configs from automation entities.
    """
    automation_data = hass.data.get("automation")
    if automation_data is None:
        _LOGGER.debug("No automation data in hass.data")
        return []

    _LOGGER.debug("automation_data type: %s", type(automation_data).__name__)

    # If it's a dict with "config" key (older HA versions or test mocks)
    if isinstance(automation_data, dict):
        configs = cast(list[dict[str, Any]], automation_data.get("config", []))
        _LOGGER.debug("Dict mode: found %d configs", len(configs))
        return configs

    # EntityComponent - get configs from entities
    if hasattr(automation_data, "entities"):
        configs: list[dict[str, Any]] = []
        entity_count = 0
        for entity in automation_data.entities:
            entity_count += 1
            _LOGGER.debug(
                "Entity %s: has raw_config=%s, raw_config type=%s",
                getattr(entity, "entity_id", "unknown"),
                hasattr(entity, "raw_config"),
                type(getattr(entity, "raw_config", None)).__name__,
            )
            # Automation entities store their config in raw_config attribute
            if hasattr(entity, "raw_config") and entity.raw_config is not None:
                config = cast(dict[str, Any], dict(entity.raw_config))
                entity_id = getattr(entity, "entity_id", None)
                if isinstance(entity_id, str) and entity_id:
                    config["__entity_id"] = entity_id
                configs.append(config)
        _LOGGER.debug(
            "EntityComponent mode: %d entities, %d configs extracted",
            entity_count,
            len(configs),
        )
        return configs

    _LOGGER.debug("automation_data has no 'entities' attribute")
    return []


def _filter_suppressed_issues(
    issues: list[ValidationIssue],
    suppression_store: SuppressionStore | None,
) -> tuple[list[ValidationIssue], int]:
    """Return visible issues and suppressed count for the given issue list."""
    if not suppression_store:
        return list(issues), 0

    visible: list[ValidationIssue] = []
    suppressed_count = 0
    for issue in issues:
        if suppression_store.is_suppressed(issue.get_suppression_key()):
            suppressed_count += 1
            continue
        visible.append(issue)
    return visible, suppressed_count


def _filter_group_issues_for_suppressions(
    group_issues: dict[str, list[ValidationIssue]],
    suppression_store: SuppressionStore | None,
) -> tuple[dict[str, list[ValidationIssue]], int]:
    """Filter grouped issues and return visible groups with total suppressed count."""
    visible_group_issues: dict[str, list[ValidationIssue]] = {
        gid: [] for gid in VALIDATION_GROUP_ORDER
    }
    total_suppressed = 0
    for gid in VALIDATION_GROUP_ORDER:
        visible, suppressed_count = _filter_suppressed_issues(
            group_issues.get(gid, []),
            suppression_store,
        )
        visible_group_issues[gid] = visible
        total_suppressed += suppressed_count
    return visible_group_issues, total_suppressed


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Autodoctor component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Register the frontend card."""
    card_path = Path(__file__).parent / "www" / "autodoctor-card.js"
    if not card_path.exists():
        _LOGGER.warning("Autodoctor card not found at %s", card_path)
        return

    # Get versioned URL using integration version for cache-busting
    card_url = f"{CARD_URL_BASE}?v={VERSION}"

    # Register static path for the card (base URL without version query string)
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(card_path), cache_headers=False)]
        )
    except (ValueError, RuntimeError):
        # Path already registered from previous setup
        _LOGGER.debug("Static path %s already registered", CARD_URL_BASE)

    # Register as Lovelace resource (storage mode only)
    # In YAML mode, users must manually add the resource
    lovelace: Any = hass.data.get("lovelace")
    # Handle both dict (older HA) and object (newer HA) access patterns
    lovelace_mode = cast(
        str | None,
        getattr(lovelace, "mode", None)
        or (lovelace.get("mode") if isinstance(lovelace, dict) else None),
    )
    if lovelace and lovelace_mode == "storage":
        resources = cast(
            Any,
            getattr(lovelace, "resources", None)
            or (lovelace.get("resources") if isinstance(lovelace, dict) else None),
        )
        if resources:
            # Find all existing autodoctor resources
            # Note: lovelace.mode/resources use attribute access (HA 2026+)
            # but resource items from async_items() are dicts
            existing: list[dict[str, Any]] = [
                r for r in resources.async_items() if "autodoctor" in r.get("url", "")
            ]

            # Check if current version already registered
            current_exists = any(r.get("url") == card_url for r in existing)

            if current_exists:
                _LOGGER.debug("Autodoctor card already registered with current version")
            else:
                # Remove old versions first
                for resource in existing:
                    resource_id: str | None = resource.get("id")
                    if resource_id:
                        try:
                            await resources.async_delete_item(resource_id)
                            _LOGGER.debug(
                                "Removed old autodoctor card resource: %s",
                                resource.get("url"),
                            )
                        except Exception as err:
                            _LOGGER.warning("Failed to remove old resource: %s", err)

                # Create new resource with current version
                try:
                    await resources.async_create_item(
                        {"url": card_url, "res_type": "module"}
                    )
                    _LOGGER.info(
                        "Registered autodoctor card as Lovelace resource: %s", card_url
                    )
                except Exception as err:
                    _LOGGER.warning("Failed to register Lovelace resource: %s", err)
    else:
        _LOGGER.debug(
            "Lovelace in YAML mode or not available - card must be manually added as resource"
        )

    _LOGGER.debug("Registered autodoctor card at %s", card_url)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Autodoctor from a config entry."""
    options = entry.options
    history_days = options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
    validate_on_reload = options.get(
        CONF_VALIDATE_ON_RELOAD, DEFAULT_VALIDATE_ON_RELOAD
    )
    debounce_seconds = options.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)
    periodic_scan_interval_hours = options.get(
        CONF_PERIODIC_SCAN_INTERVAL_HOURS,
        DEFAULT_PERIODIC_SCAN_INTERVAL_HOURS,
    )

    # Initialize stores first (they need to be loaded before use)
    suppression_store = SuppressionStore(hass)
    await suppression_store.async_load()

    learned_states_store = LearnedStatesStore(hass)
    await learned_states_store.async_load()

    # Initialize knowledge base with learned states store
    knowledge_base = StateKnowledgeBase(
        hass,
        history_days=history_days,
        learned_states_store=learned_states_store,
    )
    analyzer = AutomationAnalyzer()
    validator = ValidationEngine(knowledge_base)
    strict_template = options.get(
        CONF_STRICT_TEMPLATE_VALIDATION, DEFAULT_STRICT_TEMPLATE_VALIDATION
    )
    jinja_validator = JinjaValidator(
        hass,
        strict_template_validation=strict_template,
    )
    strict_service = options.get(
        CONF_STRICT_SERVICE_VALIDATION, DEFAULT_STRICT_SERVICE_VALIDATION
    )
    service_validator = ServiceCallValidator(
        hass, strict_service_validation=strict_service
    )
    runtime_enabled = options.get(
        CONF_RUNTIME_HEALTH_ENABLED, DEFAULT_RUNTIME_HEALTH_ENABLED
    )
    runtime_monitor = (
        RuntimeHealthMonitor(
            hass,
            baseline_days=options.get(
                CONF_RUNTIME_HEALTH_BASELINE_DAYS,
                DEFAULT_RUNTIME_HEALTH_BASELINE_DAYS,
            ),
            warmup_samples=options.get(
                CONF_RUNTIME_HEALTH_WARMUP_SAMPLES,
                DEFAULT_RUNTIME_HEALTH_WARMUP_SAMPLES,
            ),
            anomaly_threshold=options.get(
                CONF_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
                DEFAULT_RUNTIME_HEALTH_ANOMALY_THRESHOLD,
            ),
            min_expected_events=options.get(
                CONF_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
                DEFAULT_RUNTIME_HEALTH_MIN_EXPECTED_EVENTS,
            ),
            overactive_factor=options.get(
                CONF_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
                DEFAULT_RUNTIME_HEALTH_OVERACTIVE_FACTOR,
            ),
            hour_ratio_days=options.get(
                CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
                DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS,
            ),
            sensitivity=options.get(
                CONF_RUNTIME_HEALTH_SENSITIVITY,
                DEFAULT_RUNTIME_HEALTH_SENSITIVITY,
            ),
            burst_multiplier=options.get(
                CONF_RUNTIME_HEALTH_BURST_MULTIPLIER,
                DEFAULT_RUNTIME_HEALTH_BURST_MULTIPLIER,
            ),
            max_alerts_per_day=options.get(
                CONF_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY,
                DEFAULT_RUNTIME_HEALTH_MAX_ALERTS_PER_DAY,
            ),
            smoothing_window=options.get(
                CONF_RUNTIME_HEALTH_SMOOTHING_WINDOW,
                DEFAULT_RUNTIME_HEALTH_SMOOTHING_WINDOW,
            ),
            startup_recovery_minutes=options.get(
                CONF_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES,
                DEFAULT_RUNTIME_HEALTH_RESTART_EXCLUSION_MINUTES,
            ),
            auto_adapt=options.get(
                CONF_RUNTIME_HEALTH_AUTO_ADAPT,
                DEFAULT_RUNTIME_HEALTH_AUTO_ADAPT,
            ),
        )
        if runtime_enabled
        else None
    )
    if runtime_enabled:
        _LOGGER.debug("Runtime health monitoring enabled")
    else:
        _LOGGER.debug("Runtime health monitoring disabled")
    reporter = IssueReporter(hass)

    hass.data[DOMAIN] = {
        "knowledge_base": knowledge_base,
        "analyzer": analyzer,
        "validator": validator,
        "jinja_validator": jinja_validator,
        "service_validator": service_validator,
        "runtime_monitor": runtime_monitor,
        "runtime_health_enabled": runtime_enabled,
        "reporter": reporter,
        "suppression_store": suppression_store,
        "learned_states_store": learned_states_store,
        "issues": [],  # Keep for backwards compatibility
        "validation_issues": [],
        "validation_issues_raw": [],
        "validation_last_run": None,
        "validation_groups": None,
        "validation_groups_raw": None,
        "validation_run_stats": {
            "analyzed_automations": 0,
            "failed_automations": 0,
        },
        "entry": entry,
        "debounce_task": None,
        "unsub_reload_listener": None,
        "unsub_periodic_scan_listener": None,
        "unsub_runtime_trigger_listener": None,
        "unsub_runtime_gap_listener": None,
    }

    if validate_on_reload:
        unsub = _setup_reload_listener(hass, debounce_seconds)
        hass.data[DOMAIN]["unsub_reload_listener"] = unsub

    periodic_unsub = _setup_periodic_scan_listener(hass, periodic_scan_interval_hours)
    hass.data[DOMAIN]["unsub_periodic_scan_listener"] = periodic_unsub

    await _async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_websocket_api(hass)

    # Register frontend card once (not per config entry reload)
    if not hass.data[DOMAIN].get("card_registered"):
        await _async_register_card(hass)
        hass.data[DOMAIN]["card_registered"] = True

    # Load history immediately (handles reload case where HA_STARTED already fired)
    await knowledge_base.async_load_history()
    _LOGGER.info("State knowledge base loaded")

    if runtime_enabled and runtime_monitor is not None:
        try:
            await runtime_monitor.async_load_state()
        except Exception as err:
            _LOGGER.warning("Runtime state load failed during setup: %s", err)
        try:
            await runtime_monitor.async_backfill_from_recorder(
                _get_automation_configs(hass)
            )
        except Exception as err:
            _LOGGER.warning("Runtime history backfill failed during setup: %s", err)

    async def _async_load_history(_: Event) -> None:
        await knowledge_base.async_load_history()
        _LOGGER.info("State knowledge base loaded")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_load_history)

    # Invalidate entity cache when entities are added/removed/renamed
    @callback
    def _handle_entity_registry_change(_: Event) -> None:
        validator.invalidate_entity_cache()

    unsub_entity_reg = hass.bus.async_listen(
        er.EVENT_ENTITY_REGISTRY_UPDATED,  # pyright: ignore[reportArgumentType]
        _handle_entity_registry_change,
    )
    hass.data[DOMAIN]["unsub_entity_registry_listener"] = unsub_entity_reg

    if runtime_enabled and runtime_monitor is not None:

        @callback
        def _handle_runtime_trigger(event: Event) -> None:
            payload = event.data if isinstance(event.data, dict) else {}
            entity_id = payload.get("entity_id")
            if not isinstance(entity_id, str) or not entity_id.startswith(
                "automation."
            ):
                return
            suppression_store = hass.data.get(DOMAIN, {}).get("suppression_store")
            runtime_monitor.ingest_trigger_event(
                entity_id,
                occurred_at=event.time_fired,
                suppression_store=suppression_store,
            )

        unsub_runtime_trigger = hass.bus.async_listen(
            "automation_triggered",
            _handle_runtime_trigger,
        )
        hass.data[DOMAIN]["unsub_runtime_trigger_listener"] = unsub_runtime_trigger
        hass.data[DOMAIN]["unsub_runtime_gap_listener"] = (
            _setup_runtime_gap_check_listener(hass, runtime_monitor)
        )

    # Listen for options updates to reload the integration
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by reloading the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data.get(DOMAIN, {})

        # Cancel pending debounce task
        debounce_task = data.get("debounce_task")
        if debounce_task is not None and not debounce_task.done():
            debounce_task.cancel()

        # Remove event listeners
        unsub_reload = data.get("unsub_reload_listener")
        if unsub_reload is not None:
            unsub_reload()

        unsub_periodic = data.get("unsub_periodic_scan_listener")
        if unsub_periodic is not None:
            unsub_periodic()

        unsub_entity_reg = data.get("unsub_entity_registry_listener")
        if unsub_entity_reg is not None:
            unsub_entity_reg()

        unsub_runtime_trigger = data.get("unsub_runtime_trigger_listener")
        if unsub_runtime_trigger is not None:
            unsub_runtime_trigger()

        unsub_runtime_gap = data.get("unsub_runtime_gap_listener")
        if unsub_runtime_gap is not None:
            unsub_runtime_gap()

        runtime_monitor = data.get("runtime_monitor")
        if runtime_monitor is not None and hasattr(
            runtime_monitor, "async_flush_runtime_state"
        ):
            try:
                await runtime_monitor.async_flush_runtime_state()
            except Exception as err:
                _LOGGER.debug("Failed to flush runtime state during unload: %s", err)

        # Unregister services
        hass.services.async_remove(DOMAIN, "validate")
        hass.services.async_remove(DOMAIN, "validate_automation")
        hass.services.async_remove(DOMAIN, "refresh_knowledge_base")

        hass.data.pop(DOMAIN, None)
    return unload_ok


def _setup_reload_listener(
    hass: HomeAssistant, debounce_seconds: int
) -> Callable[[], None]:
    """Set up listener for automation reload events.

    Returns the unsub callback to remove the listener.
    """

    @callback
    def _handle_automation_reload(_: Event) -> None:
        data = hass.data.get(DOMAIN, {})

        # Cancel existing task if present - capture reference first to avoid race
        existing_task = data.get("debounce_task")
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()

        async def _debounced_validate() -> None:
            try:
                await asyncio.sleep(debounce_seconds)
                configs = _get_automation_configs(hass)
                new_snapshot = _build_config_snapshot(configs)
                old_snapshot = data.get("_automation_snapshot")
                if old_snapshot is not None:
                    all_ids = set(old_snapshot) | set(new_snapshot)
                    changed = [
                        a for a in all_ids if old_snapshot.get(a) != new_snapshot.get(a)
                    ]
                    if 1 <= len(changed) <= 2:
                        for aid in changed:
                            await async_validate_automation(hass, f"automation.{aid}")
                        data["_automation_snapshot"] = new_snapshot
                        return
                await async_validate_all(hass)
                data["_automation_snapshot"] = new_snapshot
            except asyncio.CancelledError:
                pass

        # Create and store new task atomically
        new_task = hass.async_create_task(_debounced_validate())
        data["debounce_task"] = new_task

    return hass.bus.async_listen("automation_reloaded", _handle_automation_reload)


def _setup_periodic_scan_listener(
    hass: HomeAssistant, interval_hours: int
) -> Callable[[], None]:
    """Set up listener for periodic full validation scans."""

    async def _handle_periodic_scan(_: datetime) -> None:
        _LOGGER.debug("Running periodic validation scan")
        try:
            await async_validate_all(hass)
        except Exception as err:
            _LOGGER.warning("Periodic validation scan failed: %s", err)

    return async_track_time_interval(
        hass,
        _handle_periodic_scan,
        timedelta(hours=interval_hours),
    )


def _setup_runtime_gap_check_listener(
    hass: HomeAssistant,
    runtime_monitor: RuntimeHealthMonitor,
) -> Callable[[], None]:
    """Set up hourly runtime gap anomaly checks."""

    async def _handle_runtime_gap_check(_: datetime) -> None:
        try:
            gap_issues = await hass.async_add_executor_job(
                runtime_monitor.check_gap_anomalies,
            )
            if gap_issues:
                _LOGGER.debug("Runtime gap check emitted %d issues", len(gap_issues))
        except Exception as err:
            _LOGGER.warning("Runtime gap check failed: %s", err)

    return async_track_time_interval(
        hass,
        _handle_runtime_gap_check,
        timedelta(hours=1),
    )


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    async def handle_validate(call: ServiceCall) -> None:
        automation_id = call.data.get("automation_id")
        if automation_id:
            await async_validate_automation(hass, automation_id)
        else:
            await async_validate_all(hass)

    async def handle_refresh(call: ServiceCall) -> None:
        data = hass.data.get(DOMAIN, {})
        kb = data.get("knowledge_base")
        if kb:
            kb.clear_cache()
            await kb.async_load_history()
            _LOGGER.info("Knowledge base refreshed")

    hass.services.async_register(
        DOMAIN, "validate", handle_validate, schema=SERVICE_VALIDATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "validate_automation", handle_validate, schema=SERVICE_VALIDATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "refresh_knowledge_base", handle_refresh, schema=SERVICE_REFRESH_SCHEMA
    )


async def _async_run_validators(
    hass: HomeAssistant,
    automations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run all validators on the given automations.

    This is the shared validation core used by all three public entry points.
    Returns a dict with keys: group_issues, group_durations, all_issues, timestamp,
    analyzed_automations, failed_automations, skip_reasons.
    """
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    jinja_validator = data.get("jinja_validator")
    service_validator = data.get("service_validator")

    # Initialize per-group collectors
    group_issues: dict[str, list[ValidationIssue]] = {
        gid: [] for gid in VALIDATION_GROUP_ORDER
    }
    group_durations: dict[str, int] = dict.fromkeys(VALIDATION_GROUP_ORDER, 0)

    # Build reverse mapping: IssueType -> group_id
    issue_type_to_group: dict[IssueType, str] = {}
    for gid, gdef in VALIDATION_GROUPS.items():
        for it in cast(frozenset[IssueType], gdef["issue_types"]):
            issue_type_to_group[it] = gid

    skip_reasons: dict[str, dict[str, int]] = {
        "templates": {},
        "services": {},
        "entity_state": {},
        "runtime_health": {},
    }

    # --- Templates group timing ---
    t0 = time.monotonic()
    if jinja_validator:
        try:
            jinja_issues = jinja_validator.validate_automations(automations)
            _LOGGER.debug(
                "Jinja validation: found %d template syntax issues",
                len(jinja_issues),
            )
            for issue in jinja_issues:
                gid = issue_type_to_group.get(issue.issue_type, "templates")
                group_issues[gid].append(issue)
        except Exception as err:
            _LOGGER.warning("Jinja validation failed: %s", err)
            skip_reasons["templates"]["validation_exception"] = (
                skip_reasons["templates"].get("validation_exception", 0) + 1
            )
    else:
        skip_reasons["templates"]["validator_unavailable"] = 1
    group_durations["templates"] = round((time.monotonic() - t0) * 1000)

    # --- Services group timing ---
    t0 = time.monotonic()
    if service_validator:
        try:
            await service_validator.async_load_descriptions()
            service_calls = []
            for automation in automations:
                service_calls.extend(analyzer.extract_service_calls(automation))

            service_issues = service_validator.validate_service_calls(service_calls)
            _LOGGER.debug(
                "Service validation: found %d issues in %d service calls",
                len(service_issues),
                len(service_calls),
            )
            for issue in service_issues:
                gid = issue_type_to_group.get(issue.issue_type, "services")
                group_issues[gid].append(issue)

            if hasattr(service_validator, "get_last_run_stats"):
                service_stats = cast(
                    dict[str, Any], service_validator.get_last_run_stats()
                )
                skipped = cast(
                    dict[str, int], service_stats.get("skipped_calls_by_reason", {})
                )
                skip_reasons["services"] = {
                    "total_calls": int(service_stats.get("total_calls", 0)),
                    **{k: int(v) for k, v in skipped.items()},
                }
        except Exception as ex:
            _LOGGER.warning("Service validation failed: %s", ex)
            skip_reasons["services"]["validation_exception"] = (
                skip_reasons["services"].get("validation_exception", 0) + 1
            )
    else:
        skip_reasons["services"]["validator_unavailable"] = 1
    group_durations["services"] = round((time.monotonic() - t0) * 1000)

    # --- Entity & State group timing ---
    t0 = time.monotonic()
    entity_validator_available = analyzer is not None and validator is not None
    failed_automations = 0
    total_automations = len(automations)
    if entity_validator_available:
        for automation in automations:
            auto_id = automation.get("id", "unknown")
            auto_name = automation.get("alias", auto_id)

            try:
                refs = analyzer.extract_state_references(automation)
                _LOGGER.debug(
                    "Automation '%s': extracted %d state references",
                    auto_name,
                    len(refs),
                )
                issues = validator.validate_all(refs)
                _LOGGER.debug(
                    "Automation '%s': found %d issues", auto_name, len(issues)
                )
                for issue in issues:
                    gid = issue_type_to_group.get(issue.issue_type, "entity_state")
                    group_issues[gid].append(issue)
            except Exception as err:
                failed_automations += 1
                _LOGGER.warning(
                    "Failed to validate automation '%s' (%s): %s",
                    auto_name,
                    auto_id,
                    err,
                )
                continue
    else:
        skip_reasons["entity_state"]["validator_unavailable"] = 1
    group_durations["entity_state"] = round((time.monotonic() - t0) * 1000)

    if failed_automations > 0:
        _LOGGER.warning(
            "Validation completed with %d failed automations (out of %d)",
            failed_automations,
            len(automations),
        )

    # --- Runtime health group timing ---
    t0 = time.monotonic()
    runtime_monitor = data.get("runtime_monitor")
    runtime_enabled = bool(data.get("runtime_health_enabled", False))
    _LOGGER.debug(
        "Runtime health: enabled=%s, monitor=%s",
        runtime_enabled,
        type(runtime_monitor).__name__ if runtime_monitor else None,
    )
    if runtime_enabled and runtime_monitor:
        try:
            runtime_issues = await runtime_monitor.validate_automations(automations)
            _LOGGER.debug(
                "Runtime health validation: %d issues found", len(runtime_issues)
            )
            for issue in runtime_issues:
                gid = issue_type_to_group.get(issue.issue_type, "runtime_health")
                group_issues[gid].append(issue)
            if hasattr(runtime_monitor, "get_last_run_stats"):
                runtime_stats = cast(
                    dict[str, int], runtime_monitor.get_last_run_stats()
                )
                _LOGGER.debug("Runtime health stats: %s", runtime_stats)
                skip_reasons["runtime_health"] = {
                    k: int(v) for k, v in runtime_stats.items()
                }
        except Exception as err:
            _LOGGER.warning("Runtime health validation failed: %s", err)
            skip_reasons["runtime_health"]["validation_exception"] = 1
    elif runtime_enabled and not runtime_monitor:
        _LOGGER.debug("Runtime health: enabled but monitor unavailable")
        skip_reasons["runtime_health"]["monitor_unavailable"] = 1
    else:
        _LOGGER.debug("Runtime health: disabled")
        skip_reasons["runtime_health"]["disabled"] = 1
    group_durations["runtime_health"] = round((time.monotonic() - t0) * 1000)

    # Combine all issues in canonical group order for flat list
    all_issues: list[ValidationIssue] = []
    for gid in VALIDATION_GROUP_ORDER:
        all_issues.extend(group_issues[gid])

    _LOGGER.info(
        "Validation complete: %d total issues across %d automations",
        len(all_issues),
        len(automations),
    )

    timestamp = datetime.now(UTC).isoformat()
    return {
        "group_issues": group_issues,
        "group_durations": group_durations,
        "all_issues": all_issues,
        "timestamp": timestamp,
        "analyzed_automations": (
            total_automations - failed_automations if entity_validator_available else 0
        ),
        "failed_automations": failed_automations,
        "skip_reasons": skip_reasons,
    }


async def async_validate_all_with_groups(hass: HomeAssistant) -> dict[str, Any]:
    """Run validation on all automations and return per-group structured results.

    This is THE primary validation entry point. All other validation functions
    route through _async_run_validators which this function also uses.

    Returns dict with keys: group_issues, group_durations, all_issues, timestamp,
    analyzed_automations, failed_automations.
    """
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    reporter = data.get("reporter")
    knowledge_base = data.get("knowledge_base")

    empty_result: dict[str, Any] = {
        "group_issues": {gid: [] for gid in VALIDATION_GROUP_ORDER},
        "group_durations": dict.fromkeys(VALIDATION_GROUP_ORDER, 0),
        "all_issues": [],
        "timestamp": datetime.now(UTC).isoformat(),
        "analyzed_automations": 0,
        "failed_automations": 0,
        "skip_reasons": {
            "templates": {},
            "services": {},
            "entity_state": {},
            "runtime_health": {},
        },
    }

    if not all([analyzer, validator, reporter]):
        return empty_result

    # Ensure history is loaded before validation
    if knowledge_base and not knowledge_base.has_history_loaded():
        _LOGGER.debug("Loading entity history before validation...")
        await knowledge_base.async_load_history()

    automations = _get_automation_configs(hass)
    if not automations:
        _LOGGER.debug("No automations found to validate")
        return empty_result

    _LOGGER.info("Validating %d automations (with groups)", len(automations))

    result = await _async_run_validators(hass, automations)

    suppression_store: SuppressionStore | None = data.get("suppression_store")
    visible_group_issues, _ = _filter_group_issues_for_suppressions(
        cast(dict[str, list[ValidationIssue]], result["group_issues"]),
        suppression_store,
    )
    visible_all_issues: list[ValidationIssue] = []
    for gid in VALIDATION_GROUP_ORDER:
        visible_all_issues.extend(visible_group_issues[gid])

    # Report only unsuppressed issues (Repairs + sensor surfaces).
    await reporter.async_report_issues(visible_all_issues)

    # Update all validation state atomically
    hass.data[DOMAIN].update(
        {
            "issues": visible_all_issues,  # Keep for backwards compatibility
            "validation_issues": visible_all_issues,
            "validation_issues_raw": result["all_issues"],
            "validation_last_run": result["timestamp"],
            "validation_groups": {
                gid: {
                    "issues": visible_group_issues[gid],
                    "duration_ms": result["group_durations"][gid],
                }
                for gid in VALIDATION_GROUP_ORDER
            },
            "validation_groups_raw": {
                gid: {
                    "issues": result["group_issues"][gid],
                    "duration_ms": result["group_durations"][gid],
                }
                for gid in VALIDATION_GROUP_ORDER
            },
            "validation_run_stats": {
                "analyzed_automations": result["analyzed_automations"],
                "failed_automations": result["failed_automations"],
                "skip_reasons": result.get("skip_reasons", {}),
            },
        }
    )

    return result


async def async_validate_all(hass: HomeAssistant) -> list[ValidationIssue]:
    """Validate all automations and return flat issue list.

    Thin wrapper around async_validate_all_with_groups that returns
    just the flat list for backward compatibility.
    """
    result = await async_validate_all_with_groups(hass)
    return result["all_issues"]


async def async_validate_automation(
    hass: HomeAssistant, automation_id: str
) -> list[ValidationIssue]:
    """Validate a specific automation.

    Routes through the shared validation core so that ALL validator families
    (jinja, service, entity/state) are included.
    """
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    reporter = data.get("reporter")

    if not all([analyzer, validator, reporter]):
        return []

    automations = _get_automation_configs(hass)
    automation = next(
        (a for a in automations if f"automation.{a.get('id')}" == automation_id),
        None,
    )

    if not automation:
        _LOGGER.warning("Automation %s not found", automation_id)
        return []

    result = await _async_run_validators(hass, [automation])
    suppression_store: SuppressionStore | None = data.get("suppression_store")
    visible_current_issues, _ = _filter_suppressed_issues(
        result["all_issues"],
        suppression_store,
    )

    # Merge single-automation results with existing issues for OTHER automations
    # to prevent reporter from clearing their repair entries. Reporter's
    # _clear_resolved_issues deletes all repairs NOT in the provided list.
    existing_issues: list[ValidationIssue] = data.get("validation_issues", [])
    other_issues = [i for i in existing_issues if i.automation_id != automation_id]
    merged_issues = other_issues + visible_current_issues

    existing_raw_issues: list[ValidationIssue] = data.get(
        "validation_issues_raw",
        existing_issues,
    )
    other_raw_issues = [
        i for i in existing_raw_issues if i.automation_id != automation_id
    ]
    merged_raw_issues = other_raw_issues + result["all_issues"]

    await reporter.async_report_issues(merged_issues)

    hass.data[DOMAIN].update(
        {
            "issues": merged_issues,
            "validation_issues": merged_issues,
            "validation_issues_raw": merged_raw_issues,
            "validation_last_run": result["timestamp"],
            "validation_run_stats": {
                "analyzed_automations": result.get("analyzed_automations", 0),
                "failed_automations": result.get("failed_automations", 0),
                "skip_reasons": result.get("skip_reasons", {}),
            },
        }
    )

    return visible_current_issues
