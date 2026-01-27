"""Autodoctor integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    VERSION,
    CONF_HISTORY_DAYS,
    CONF_VALIDATE_ON_RELOAD,
    CONF_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
)
from .knowledge_base import StateKnowledgeBase
from .analyzer import AutomationAnalyzer
from .validator import ValidationEngine
from .simulator import SimulationEngine
from .reporter import IssueReporter
from .fix_engine import FixEngine
from .websocket_api import async_setup_websocket_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

# Frontend card
CARD_URL_BASE = "/autodoctor/autodoctor-card.js"
CARD_URL = f"{CARD_URL_BASE}?v={VERSION}"
CARD_PATH = Path(__file__).parent / "www" / "autodoctor-card.js"


def _get_automation_configs(hass: HomeAssistant) -> list[dict]:
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
        configs = automation_data.get("config", [])
        _LOGGER.debug("Dict mode: found %d configs", len(configs))
        return configs

    # EntityComponent - get configs from entities
    if hasattr(automation_data, "entities"):
        configs = []
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
                configs.append(entity.raw_config)
        _LOGGER.debug("EntityComponent mode: %d entities, %d configs extracted", entity_count, len(configs))
        return configs

    _LOGGER.debug("automation_data has no 'entities' attribute")
    return []


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Autodoctor component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Register the frontend card."""
    if not CARD_PATH.exists():
        _LOGGER.warning("Autodoctor card not found at %s", CARD_PATH)
        return

    # Register static path for the card (base URL without version query string)
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(CARD_PATH), cache_headers=False)]
        )
    except ValueError:
        # Path already registered from previous setup
        _LOGGER.debug("Static path %s already registered", CARD_URL_BASE)

    # Register as Lovelace resource (storage mode only)
    # In YAML mode, users must manually add the resource
    lovelace = hass.data.get("lovelace")
    if lovelace and lovelace.mode == "storage":
        resources = lovelace.resources
        if resources:
            # Check if already registered
            existing = [r for r in resources.async_items() if CARD_URL_BASE in r.get("url", "")]
            if not existing:
                try:
                    await resources.async_create_item({"url": CARD_URL, "res_type": "module"})
                    _LOGGER.info("Registered autodoctor card as Lovelace resource")
                except Exception as err:
                    _LOGGER.warning("Failed to register Lovelace resource: %s", err)
            else:
                # Update existing resource if version changed
                resource = existing[0]
                if resource.get("url") != CARD_URL:
                    try:
                        await resources.async_update_item(
                            resource["id"], {"url": CARD_URL, "res_type": "module"}
                        )
                        _LOGGER.info("Updated autodoctor card resource to %s", CARD_URL)
                    except Exception as err:
                        _LOGGER.warning("Failed to update Lovelace resource: %s", err)
                else:
                    _LOGGER.debug("Autodoctor card already registered with current version")
    else:
        _LOGGER.debug(
            "Lovelace in YAML mode or not available - card must be manually added as resource"
        )

    _LOGGER.debug("Registered autodoctor card at %s", CARD_URL)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Autodoctor from a config entry."""
    options = entry.options
    history_days = options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
    validate_on_reload = options.get(CONF_VALIDATE_ON_RELOAD, DEFAULT_VALIDATE_ON_RELOAD)
    debounce_seconds = options.get(CONF_DEBOUNCE_SECONDS, DEFAULT_DEBOUNCE_SECONDS)

    knowledge_base = StateKnowledgeBase(hass, history_days)
    analyzer = AutomationAnalyzer()
    validator = ValidationEngine(knowledge_base)
    simulator = SimulationEngine(knowledge_base)
    reporter = IssueReporter(hass)
    fix_engine = FixEngine(hass, knowledge_base)

    hass.data[DOMAIN] = {
        "knowledge_base": knowledge_base,
        "analyzer": analyzer,
        "validator": validator,
        "simulator": simulator,
        "reporter": reporter,
        "fix_engine": fix_engine,
        "issues": [],
        "entry": entry,
        "debounce_task": None,
    }

    if validate_on_reload:
        _setup_reload_listener(hass, debounce_seconds)

    await _async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_websocket_api(hass)

    # Register frontend card once (not per config entry reload)
    if not hass.data[DOMAIN].get("card_registered"):
        await _async_register_card(hass)
        hass.data[DOMAIN]["card_registered"] = True

    async def _async_load_history(_: Event) -> None:
        await knowledge_base.async_load_history()
        _LOGGER.info("State knowledge base loaded")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_load_history)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN, None)
    return unload_ok


def _setup_reload_listener(hass: HomeAssistant, debounce_seconds: int) -> None:
    """Set up listener for automation reload events."""

    @callback
    def _handle_automation_reload(_: Event) -> None:
        data = hass.data.get(DOMAIN, {})
        if data.get("debounce_task"):
            data["debounce_task"].cancel()

        async def _debounced_validate() -> None:
            await asyncio.sleep(debounce_seconds)
            await async_validate_all(hass)

        data["debounce_task"] = hass.async_create_task(_debounced_validate())

    hass.bus.async_listen("automation_reloaded", _handle_automation_reload)


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services."""

    async def handle_validate(call: Any) -> None:
        automation_id = call.data.get("automation_id")
        if automation_id:
            await async_validate_automation(hass, automation_id)
        else:
            await async_validate_all(hass)

    async def handle_simulate(call: Any) -> None:
        automation_id = call.data.get("automation_id")
        if automation_id:
            await async_simulate_automation(hass, automation_id)
        else:
            await async_simulate_all(hass)

    async def handle_refresh(call: Any) -> None:
        data = hass.data.get(DOMAIN, {})
        kb = data.get("knowledge_base")
        if kb:
            kb.clear_cache()
            await kb.async_load_history()
            _LOGGER.info("Knowledge base refreshed")

    hass.services.async_register(DOMAIN, "validate", handle_validate)
    hass.services.async_register(DOMAIN, "validate_automation", handle_validate)
    hass.services.async_register(DOMAIN, "simulate", handle_simulate)
    hass.services.async_register(DOMAIN, "refresh_knowledge_base", handle_refresh)


async def async_validate_all(hass: HomeAssistant) -> list:
    """Validate all automations."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    reporter = data.get("reporter")
    knowledge_base = data.get("knowledge_base")

    if not all([analyzer, validator, reporter]):
        return []

    # Ensure history is loaded before validation
    if knowledge_base and not knowledge_base._observed_states:
        _LOGGER.debug("Loading entity history before validation...")
        await knowledge_base.async_load_history()

    automations = _get_automation_configs(hass)
    if not automations:
        _LOGGER.debug("No automations found to validate")
        return []

    _LOGGER.info("Validating %d automations", len(automations))

    # Log first automation structure for debugging
    if automations:
        first = automations[0]
        _LOGGER.debug("First automation keys: %s", list(first.keys()) if isinstance(first, dict) else type(first))
        _LOGGER.debug("First automation sample: %s", {k: type(v).__name__ for k, v in first.items()} if isinstance(first, dict) else first)

    all_issues = []
    for idx, automation in enumerate(automations):
        auto_name = automation.get("alias", automation.get("id", "unknown"))
        # Log trigger info for first few automations
        if idx < 3:
            _LOGGER.debug(
                "Automation '%s' trigger: %s",
                auto_name,
                automation.get("trigger", automation.get("triggers", "NO TRIGGER KEY"))
            )
        refs = analyzer.extract_state_references(automation)
        _LOGGER.debug("Automation '%s': extracted %d state references", auto_name, len(refs))
        issues = validator.validate_all(refs)
        _LOGGER.debug("Automation '%s': found %d issues", auto_name, len(issues))
        all_issues.extend(issues)

    _LOGGER.info("Validation complete: %d total issues across %d automations", len(all_issues), len(automations))
    await reporter.async_report_issues(all_issues)
    hass.data[DOMAIN]["issues"] = all_issues
    return all_issues


async def async_validate_automation(hass: HomeAssistant, automation_id: str) -> list:
    """Validate a specific automation."""
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

    refs = analyzer.extract_state_references(automation)
    issues = validator.validate_all(refs)
    await reporter.async_report_issues(issues)
    return issues


async def async_simulate_all(hass: HomeAssistant) -> list:
    """Simulate all automations."""
    data = hass.data.get(DOMAIN, {})
    simulator = data.get("simulator")

    if not simulator:
        return []

    automations = _get_automation_configs(hass)
    reports = []
    for automation in automations:
        report = simulator.verify_outcomes(automation)
        reports.append(report)

    return reports


async def async_simulate_automation(hass: HomeAssistant, automation_id: str) -> Any:
    """Simulate a specific automation."""
    data = hass.data.get(DOMAIN, {})
    simulator = data.get("simulator")

    if not simulator:
        return None

    automations = _get_automation_configs(hass)
    automation = next(
        (a for a in automations if f"automation.{a.get('id')}" == automation_id),
        None,
    )

    if not automation:
        _LOGGER.warning("Automation %s not found", automation_id)
        return None

    return simulator.verify_outcomes(automation)
