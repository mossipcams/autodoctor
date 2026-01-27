"""Autodoctor integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
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

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]


def _get_automation_configs(hass: HomeAssistant) -> list[dict]:
    """Get automation configurations from Home Assistant.

    The automation component stores data as an EntityComponent, not a plain dict.
    This helper properly extracts the configs from automation entities.
    """
    automation_data = hass.data.get("automation")
    if automation_data is None:
        return []

    # If it's a dict with "config" key (older HA versions or test mocks)
    if isinstance(automation_data, dict):
        return automation_data.get("config", [])

    # EntityComponent - get configs from entities
    if hasattr(automation_data, "entities"):
        configs = []
        for entity in automation_data.entities:
            # Automation entities store their config in _config attribute
            if hasattr(entity, "_config"):
                configs.append(entity._config)
        return configs

    return []


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Autodoctor component."""
    hass.data.setdefault(DOMAIN, {})
    return True


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

    hass.data[DOMAIN] = {
        "knowledge_base": knowledge_base,
        "analyzer": analyzer,
        "validator": validator,
        "simulator": simulator,
        "reporter": reporter,
        "entry": entry,
        "debounce_task": None,
    }

    if validate_on_reload:
        _setup_reload_listener(hass, debounce_seconds)

    await _async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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

    if not all([analyzer, validator, reporter]):
        return []

    automations = _get_automation_configs(hass)
    if not automations:
        _LOGGER.debug("No automations found to validate")
        return []

    all_issues = []
    for automation in automations:
        refs = analyzer.extract_state_references(automation)
        issues = validator.validate_all(refs)
        all_issues.extend(issues)

    await reporter.async_report_issues(all_issues)
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
