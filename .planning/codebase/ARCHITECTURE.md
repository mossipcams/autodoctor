# Architecture

**Analysis Date:** 2026-01-30

## Pattern Overview

**Overall:** Multi-layer validation pipeline with pluggable analysis engines

**Key Characteristics:**
- **Separation of concerns**: Parsing (analyzer), validation (three independent validators), knowledge (knowledge base), and reporting are decoupled
- **Conservative-first philosophy**: State validation only applies to whitelisted domains with stable states; opt-in strict modes for aggressive checking
- **Knowledge-driven validation**: Validator decisions based on ground-truth knowledge base built from multiple sources
- **WebSocket-driven UI**: Frontend communicates via WebSocket API commands, not direct data access
- **Persistent learning**: User feedback (issue suppressions) teaches the knowledge base new valid states
- **Async/concurrent design**: Validation and history loading can run in parallel; thread-safe stores with locks

## Layers

**Automation Extraction Layer:**
- Purpose: Parse automation configs and extract all referenceable entities, states, and service calls
- Location: `custom_components/autodoctor/analyzer.py`
- Contains: AutomationAnalyzer class with regex-based extraction (state references, service calls) and 21 trigger type handlers
- Depends on: None (pure parsing logic)
- Used by: Entry point (`__init__.py`) to feed data to validators

**Knowledge Layer:**
- Purpose: Build and maintain ground-truth mappings of valid entity states, attributes, and registries
- Location: `custom_components/autodoctor/knowledge_base.py`
- Contains: StateKnowledgeBase class with multi-source state merging (device class defaults, learned states, entity capabilities, schema introspection, recorder history)
- Depends on: LearnedStatesStore (learns from user suppressions)
- Used by: ValidationEngine for all state/attribute decisions

**Validation Layer (Three validators):**
- **State Reference Validator** (`validator.py`):
  - Validates entities exist, states are valid (whitelisted domains only), attributes exist
  - Returns ValidationIssue objects with severity/suggestions
  - Handles non-entity references (device, area, tag, integration) against HA registries

- **Service Call Validator** (`service_validator.py`):
  - Validates service existence, required parameters, and select/enum options
  - Handles capability-dependent parameters (e.g., light.turn_on color modes)
  - Skips validation on templated targets/data fields

- **Jinja2 Template Validator** (`jinja_validator.py`):
  - Validates Jinja2 syntax and semantic correctness
  - Checks entity references, state validity, attribute existence
  - Opt-in validation for unknown filters/tests (strict_template_validation mode)
  - Uses HA-specific template semantics (`template_semantics.py`) for HA function signatures

**Persistence Layer:**
- Purpose: Store dismissals and learned states persistently
- Location: `learned_states_store.py`, `suppression_store.py`
- Contains: Thread-safe stores using Home Assistant's Store API with async/lock patterns
- Used by: Knowledge base (reads learned states), WebSocket API (writes suppressions)

**API & Output Layer:**
- **Reporter** (`reporter.py`): Converts ValidationIssue objects to HA repair entries and logs
- **WebSocket API** (`websocket_api.py`): Six WebSocket commands (issues, refresh, validation, suppress, clear_suppressions)
- **Sensors** (`sensor.py`, `binary_sensor.py`): Entity count and health status displays

**Configuration Layer:**
- Location: `config_flow.py`, `const.py`
- Contains: Single-instance config flow with history days, debounce delay, and opt-in strict validation flags
- Controls: ValidationConfig object passed to validators

## Data Flow

**On-Demand Validation (Service/WebSocket):**

1. User calls `autodoctor.validate` service or WebSocket `autodoctor/validation/run`
2. Entry point (`__init__.py::async_validate_all`) retrieves automation configs via `_get_automation_configs()`
3. **Jinja validation phase**: JinjaValidator processes all automations (syntax + semantic checks)
4. **Service validation phase**: Analyzer extracts all service calls; ServiceCallValidator validates against registry
5. **State validation phase** (per-automation): Analyzer extracts state references; ValidationEngine validates each
6. All issues aggregated, deduplicated, reported via IssueReporter
7. Issues stored in `hass.data[DOMAIN]["validation_issues"]` (atomic update)
8. WebSocket returns issues with fix suggestions (fuzzy entity matching via `get_entity_suggestion()`)

**On Reload (if CONF_VALIDATE_ON_RELOAD=True):**

1. HA fires `automation_reloaded` event
2. `_setup_reload_listener` debounces (default 5s) and queues `async_validate_all()`
3. Prevents repeated validation if multiple automations reload in sequence

**Learning Flow (Suppression):**

1. User suppresses issue via WebSocket `autodoctor/suppress`
2. SuppressionStore records it; LearnedStatesStore optionally learns the state as valid
3. Knowledge base includes learned states in future validation decisions
4. Next validation run uses expanded knowledge base (no reload needed)

**History Loading (Background):**

1. On HA startup (`EVENT_HOMEASSISTANT_STARTED`): `knowledge_base.async_load_history()` loads recorder history
2. Extracts all observed entity states from past 30 days (configurable)
3. Populates state knowledge base (lowest priority after device classes/learned/capabilities/schema)
4. Runs async to not block startup

## Key Abstractions

**StateReference:**
- Purpose: Represents a single entity/state reference found in automation
- Examples: `entity_id`, `expected_state`, `expected_attribute`, `reference_type` (direct/device/area/tag/integration)
- Pattern: Immutable dataclass; created by Analyzer, validated by ValidationEngine

**ValidationIssue:**
- Purpose: Represents a detected problem with severity and fix suggestion
- Examples: ENTITY_NOT_FOUND, INVALID_STATE, SERVICE_UNKNOWN_PARAM
- Pattern: Hashable/equality-based for deduplication; converts to dict for JSON serialization

**ServiceCall:**
- Purpose: Represents a service call action found in automation
- Examples: `service`, `target` (entity/device/area), `data` (parameters)
- Pattern: Flags templated fields to skip validation

**AutodoctorData (TypedDict):**
- Purpose: Type-safe container for all integration state in `hass.data[DOMAIN]`
- Contains: Validators, stores, sensors, issues, last run timestamp, debounce task
- Pattern: Single source of truth; used by all entry point functions

## Entry Points

**Integration Setup (`__init__.py`):**
- `async_setup()`: Platform registration (called once per HA instance)
- `async_setup_entry()`: Creates all validators, stores, sensors; registers WebSocket API and services
- `async_setup_entry()` → `_async_register_card()`: Registers Lovelace card as static resource
- `async_setup_entry()` → `_async_setup_services()`: Registers `autodoctor.validate`, `autodoctor.validate_automation`, `autodoctor.refresh_knowledge_base`
- Returns: True on success

**Validation Entry Points:**
- `async_validate_all()`: Validates all automations (called by service, reload listener, WebSocket)
- `async_validate_automation()`: Validates single automation (called by service with automation_id)
- Both call `_get_automation_configs()` to extract from HA's automation component

**WebSocket Entry Points (`websocket_api.py`):**
- `websocket_get_issues()`: Returns current issues with fix suggestions
- `websocket_run_validation()`: Triggers validation on demand
- `websocket_suppress()`: Records suppression and optionally learns state

## Error Handling

**Strategy:** Fail gracefully with logging; validation errors don't block HA

**Patterns:**
- Analyzer: Catches exceptions during extraction, logs warning, continues with next automation
- Validators: Each validator wrapped in try/except at call site; logs but doesn't raise
- Knowledge base: Handles missing recorder component gracefully (get_significant_states import fallback)
- Service loading: Async_load_descriptions fails silently if service registry unavailable
- Store loading: Skips if storage component not ready; no data loss

**Example** (`__init__.py::async_validate_all`):
```python
for idx, automation in enumerate(automations):
    try:
        refs = analyzer.extract_state_references(automation)
        issues = validator.validate_all(refs)
        all_issues.extend(issues)
    except Exception as err:
        failed_automations += 1
        _LOGGER.warning("Failed to validate automation '%s': %s", auto_name, err)
        continue
```

## Cross-Cutting Concerns

**Logging:**
- Each module uses `_LOGGER = logging.getLogger(__name__)` for namespaced logs
- Key operations log at INFO level (validation start/end, knowledge base load)
- Debug logs for intermediate steps (entity extraction, issue counts)

**Validation Philosophy:**
- **Conservative by default**: State validation only on STATE_VALIDATION_WHITELIST domains
- **Opt-in strictness**: Strict modes for unknown filters/parameters (disabled by default)
- **Entity registries always checked**: Device, area, tag, integration references never skipped
- **Recorder fallback**: Learned states + history provides safety net for unknown entity states

**Concurrency:**
- LearnedStatesStore and SuppressionStore use asyncio.Lock() for thread-safe updates
- Stores use HA's Store API (async-safe storage layer)
- Debounce task cancellation prevents races in reload listener
- Reporter._active_issues uses frozenset for atomic reads from sensors

**Configuration:**
- All config read from ConfigEntry.options (not from YAML)
- Single instance enforced via UNIQUE_ID in config_flow.py
- Changes trigger async_reload to apply new settings atomically

---

*Architecture analysis: 2026-01-30*
