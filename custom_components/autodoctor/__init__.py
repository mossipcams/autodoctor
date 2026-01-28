"""Autodoctor integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .analyzer import AutomationAnalyzer
from .const import (
    CONF_DEBOUNCE_SECONDS,
    CONF_HISTORY_DAYS,
    CONF_VALIDATE_ON_RELOAD,
    DEFAULT_DEBOUNCE_SECONDS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_VALIDATE_ON_RELOAD,
    DOMAIN,
    VERSION,
)
from .jinja_validator import JinjaValidator
from .knowledge_base import StateKnowledgeBase
from .learned_states_store import LearnedStatesStore
from .reporter import IssueReporter
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
CARD_PATH = Path(__file__).parent / "www" / "autodoctor-card.js"


def _get_card_url() -> str:
    """Get card URL with cache-busting version based on file modification time."""
    try:
        mtime = int(CARD_PATH.stat().st_mtime)
        return f"{CARD_URL_BASE}?v={mtime}"
    except OSError:
        return f"{CARD_URL_BASE}?v={VERSION}"


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
        _LOGGER.debug(
            "EntityComponent mode: %d entities, %d configs extracted",
            entity_count,
            len(configs),
        )
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

    # Get versioned URL based on file modification time
    card_url = _get_card_url()

    # Register static path for the card (base URL without version query string)
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, str(CARD_PATH), cache_headers=False)]
        )
    except (ValueError, RuntimeError):
        # Path already registered from previous setup
        _LOGGER.debug("Static path %s already registered", CARD_URL_BASE)

    # Register as Lovelace resource (storage mode only)
    # In YAML mode, users must manually add the resource
    lovelace = hass.data.get("lovelace")
    # Handle both dict (older HA) and object (newer HA) access patterns
    lovelace_mode = getattr(lovelace, "mode", None) or (
        lovelace.get("mode") if isinstance(lovelace, dict) else None
    )
    if lovelace and lovelace_mode == "storage":
        resources = getattr(lovelace, "resources", None) or (
            lovelace.get("resources") if isinstance(lovelace, dict) else None
        )
        if resources:
            # Find all existing autodoctor resources
            # Note: lovelace.mode/resources use attribute access (HA 2026+)
            # but resource items from async_items() are dicts
            existing = [
                r for r in resources.async_items() if "autodoctor" in r.get("url", "")
            ]

            # Check if current version already registered
            current_exists = any(r.get("url") == card_url for r in existing)

            if current_exists:
                _LOGGER.debug("Autodoctor card already registered with current version")
            else:
                # Remove old versions first
                for resource in existing:
                    resource_id = resource.get("id")
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
    jinja_validator = JinjaValidator(hass)
    reporter = IssueReporter(hass)

    hass.data[DOMAIN] = {
        "knowledge_base": knowledge_base,
        "analyzer": analyzer,
        "validator": validator,
        "jinja_validator": jinja_validator,
        "reporter": reporter,
        "suppression_store": suppression_store,
        "learned_states_store": learned_states_store,
        "issues": [],  # Keep for backwards compatibility
        "validation_issues": [],
        "validation_last_run": None,
        "entry": entry,
        "debounce_task": None,
        "unsub_reload_listener": None,
    }

    if validate_on_reload:
        unsub = _setup_reload_listener(hass, debounce_seconds)
        hass.data[DOMAIN]["unsub_reload_listener"] = unsub

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

        # Remove event listener
        unsub_reload = data.get("unsub_reload_listener")
        if unsub_reload is not None:
            unsub_reload()

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
                await async_validate_all(hass)
            except asyncio.CancelledError:
                # Task was cancelled by a newer reload event - this is expected
                pass

        # Create and store new task atomically
        new_task = hass.async_create_task(_debounced_validate())
        data["debounce_task"] = new_task

    return hass.bus.async_listen("automation_reloaded", _handle_automation_reload)


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


async def async_validate_all(hass: HomeAssistant) -> list:
    """Validate all automations."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    jinja_validator = data.get("jinja_validator")
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
        _LOGGER.debug(
            "First automation keys: %s",
            list(first.keys()) if isinstance(first, dict) else type(first),
        )
        _LOGGER.debug(
            "First automation sample: %s",
            {k: type(v).__name__ for k, v in first.items()}
            if isinstance(first, dict)
            else first,
        )

    all_issues = []

    # Run Jinja template validation first
    if jinja_validator:
        jinja_issues = jinja_validator.validate_automations(automations)
        _LOGGER.debug(
            "Jinja validation: found %d template syntax issues", len(jinja_issues)
        )
        all_issues.extend(jinja_issues)

    # Run state reference validation
    for idx, automation in enumerate(automations):
        auto_name = automation.get("alias", automation.get("id", "unknown"))
        # Log trigger info for first few automations
        if idx < 3:
            _LOGGER.debug(
                "Automation '%s' trigger: %s",
                auto_name,
                automation.get("trigger", automation.get("triggers", "NO TRIGGER KEY")),
            )
        refs = analyzer.extract_state_references(automation)
        _LOGGER.debug(
            "Automation '%s': extracted %d state references", auto_name, len(refs)
        )
        issues = validator.validate_all(refs)
        _LOGGER.debug("Automation '%s': found %d issues", auto_name, len(issues))
        all_issues.extend(issues)

    _LOGGER.info(
        "Validation complete: %d total issues across %d automations",
        len(all_issues),
        len(automations),
    )
    await reporter.async_report_issues(all_issues)

    # Update all validation state atomically to prevent partial reads
    timestamp = datetime.now(UTC).isoformat()
    hass.data[DOMAIN].update(
        {
            "issues": all_issues,  # Keep for backwards compatibility
            "validation_issues": all_issues,
            "validation_last_run": timestamp,
        }
    )
    return all_issues


async def async_validate_automation(hass: HomeAssistant, automation_id: str) -> list:
    """Validate a specific automation."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    jinja_validator = data.get("jinja_validator")
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

    issues = []

    # Run Jinja validation
    if jinja_validator:
        jinja_issues = jinja_validator.validate_automations([automation])
        issues.extend(jinja_issues)

    # Run state reference validation
    refs = analyzer.extract_state_references(automation)
    issues.extend(validator.validate_all(refs))

    await reporter.async_report_issues(issues)
    return issues
