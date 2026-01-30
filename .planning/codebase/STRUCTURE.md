# Codebase Structure

**Analysis Date:** 2026-01-30

## Directory Layout

```
autodoctor/
├── custom_components/autodoctor/    # Main integration code
│   ├── __init__.py                  # Entry point: lifecycle, validation orchestration
│   ├── analyzer.py                  # Extraction: triggers/conditions/actions → state refs + service calls
│   ├── validator.py                 # State reference validation vs knowledge base
│   ├── service_validator.py         # Service call validation vs HA registry
│   ├── jinja_validator.py           # Jinja2 template syntax/semantic validation
│   ├── knowledge_base.py            # Knowledge base: multi-source state truth
│   ├── learned_states_store.py      # Persistent storage: user-learned states
│   ├── suppression_store.py         # Persistent storage: dismissed issues
│   ├── template_semantics.py        # HA Jinja2 function/filter signatures
│   ├── models.py                    # Data classes: StateReference, ValidationIssue, ServiceCall
│   ├── reporter.py                  # Output: HA repairs + logs
│   ├── sensor.py                    # Entity: issue count sensor
│   ├── binary_sensor.py             # Entity: health status sensor
│   ├── config_flow.py               # UI: config entry setup
│   ├── const.py                     # Constants: domain, whitelists, defaults
│   ├── device_class_states.py       # Knowledge: default state mappings by device class
│   ├── domain_attributes.py         # Knowledge: domain-specific attribute mappings
│   ├── www/
│   │   └── autodoctor-card.js       # Frontend: Lovelace card (JavaScript)
│   ├── translations/                # i18n: language strings
│   ├── manifest.json                # Integration metadata
│   ├── services.yaml                # HA service definitions
│   └── strings.json                 # UI/i18n strings
├── tests/                           # Test suite
│   ├── conftest.py                  # Pytest fixtures
│   ├── test_*.py                    # Individual module tests (17 files)
│   └── __init__.py
├── scripts/                         # Utility scripts
│   └── extract_ha_states.py         # Script: extract valid states from HA source
├── docs/                            # Documentation
│   ├── plans/                       # Design documents
│   └── *.md                         # Analysis docs
└── www/                             # Frontend build output
    └── autodoctor/
        ├── autodoctor-card.js       # Bundled frontend assets
        └── node_modules/            # Build dependencies
```

## Directory Purposes

**`custom_components/autodoctor/`:**
- Purpose: Main integration code loaded by Home Assistant
- Contains: Validators, knowledge base, stores, API, sensors, config
- Key files: `__init__.py` (entry point), `models.py` (data shapes), `const.py` (config)

**`custom_components/autodoctor/www/`:**
- Purpose: Frontend Lovelace card (served as static asset)
- Contains: `autodoctor-card.js` (WebSocket client)
- Static: Committed to git; registered as static resource on setup

**`custom_components/autodoctor/translations/`:**
- Purpose: Internationalization strings
- Contains: Language-specific JSON files for UI/error messages
- Format: Home Assistant translation structure

**`tests/`:**
- Purpose: Test suite (pytest)
- Contains: 17 test files matching module names
- Patterns: Fixtures in `conftest.py`, mocking HA components, async test support

**`scripts/`:**
- Purpose: Development and maintenance utilities
- Contains: `extract_ha_states.py` (pulls valid states from HA source for device_class_states.py)

**`docs/`:**
- Purpose: Design decisions and implementation plans
- Contains: Plans for major features, analysis documents

## Key File Locations

**Entry Points:**
- `custom_components/autodoctor/__init__.py`: Integration lifecycle (setup, teardown, validation orchestration)
- `custom_components/autodoctor/websocket_api.py`: WebSocket command handlers (frontend communication)
- `custom_components/autodoctor/config_flow.py`: Configuration UI entry point

**Core Validation:**
- `custom_components/autodoctor/analyzer.py`: Extract state/service references from automations
- `custom_components/autodoctor/validator.py`: Validate state references + entity suggestions
- `custom_components/autodoctor/service_validator.py`: Validate service calls against registry
- `custom_components/autodoctor/jinja_validator.py`: Validate Jinja2 templates

**Knowledge & Persistence:**
- `custom_components/autodoctor/knowledge_base.py`: Multi-source state knowledge (device class defaults, learned, capabilities, schema, history)
- `custom_components/autodoctor/learned_states_store.py`: Persistent learned states (Thread-safe with asyncio.Lock)
- `custom_components/autodoctor/suppression_store.py`: Persistent suppressions (Thread-safe with asyncio.Lock)

**Data Models:**
- `custom_components/autodoctor/models.py`: StateReference, ValidationIssue, ServiceCall, AutodoctorData TypedDict
- `custom_components/autodoctor/template_semantics.py`: Jinja2 function/filter signatures for semantic validation

**Output & Reporting:**
- `custom_components/autodoctor/reporter.py`: Convert issues to HA repairs + logs
- `custom_components/autodoctor/sensor.py`: Issue count sensor entity
- `custom_components/autodoctor/binary_sensor.py`: Health status sensor entity

**Configuration:**
- `custom_components/autodoctor/const.py`: Constants (DOMAIN, STATE_VALIDATION_WHITELIST, MAX_RECURSION_DEPTH, defaults)
- `custom_components/autodoctor/config_flow.py`: Config entry UI (history days, debounce, strict modes)

**Reference Data:**
- `custom_components/autodoctor/device_class_states.py`: Default state mappings for 30+ device classes
- `custom_components/autodoctor/domain_attributes.py`: Domain-specific attribute mappings

## Naming Conventions

**Files:**
- Validators: `*_validator.py` (validator.py, service_validator.py, jinja_validator.py)
- Stores: `*_store.py` (learned_states_store.py, suppression_store.py)
- Entities: `sensor.py`, `binary_sensor.py`, `config_flow.py` (HA platform pattern)
- Core: `analyzer.py`, `knowledge_base.py`, `reporter.py`, `models.py`
- Helpers: `template_semantics.py`, `device_class_states.py`, `domain_attributes.py`

**Classes:**
- Validators: `*Validator` or `*Engine` (ValidationEngine, ServiceCallValidator, JinjaValidator)
- Stores: `*Store` (LearnedStatesStore, SuppressionStore)
- Data models: PascalCase with descriptive names (ValidationIssue, StateReference, ServiceCall)

**Functions:**
- Public async: `async_*()` (async_setup, async_validate_all, async_load_history)
- Callback handlers: `_handle_*()` or `_callback_*()` (follows HA convention)
- Helpers: Snake_case prefixed with `_` if private (`_get_automation_configs`, `_normalize_states`)

**Constants:**
- Config keys: `CONF_*` (CONF_HISTORY_DAYS, CONF_VALIDATE_ON_RELOAD)
- Defaults: `DEFAULT_*` (DEFAULT_HISTORY_DAYS, DEFAULT_DEBOUNCE_SECONDS)
- Special sets: `STATE_VALIDATION_WHITELIST`, `STORAGE_KEY`

## Where to Add New Code

**New Validation Check (State):**
- Primary code: `custom_components/autodoctor/validator.py` → Add method to `ValidationEngine` class
- Model: Add IssueType variant to `custom_components/autodoctor/models.py::IssueType` enum
- Tests: `tests/test_validator.py`
- Example location: `validator.py::ValidationEngine.validate_reference()` checks entity existence (line 46)

**New Validation Check (Service):**
- Primary code: `custom_components/autodoctor/service_validator.py` → Add validation in `validate_service_calls()` method
- Model: Add IssueType variant if needed
- Tests: `tests/test_service_validator.py`
- Known patterns: Capability-dependent params in `_CAPABILITY_DEPENDENT_PARAMS` dict

**New Validation Check (Jinja2):**
- Primary code: `custom_components/autodoctor/jinja_validator.py` → Add to `_validate_template_semantics()` or add new visitor method
- Signatures: Add to `custom_components/autodoctor/template_semantics.py` if new HA function
- Tests: `tests/test_jinja_validator.py`, `tests/test_template_semantics.py`

**New Trigger/Condition Type:**
- Primary code: `custom_components/autodoctor/analyzer.py` → Add handler in `extract_state_references()` method
- Handler method: Follow pattern `_extract_from_[trigger_type]()`
- Tests: `tests/test_analyzer.py`
- Index: Update `custom_components/autodoctor/const.py::MAX_RECURSION_DEPTH` if adding deep nesting

**New Knowledge Source:**
- Primary code: `custom_components/autodoctor/knowledge_base.py` → Add method to `StateKnowledgeBase`
- Priority: Add to source priority order in class docstring (device class → learned → capabilities → schema → history)
- Tests: `tests/test_knowledge_base.py`

**New WebSocket Command:**
- Primary code: `custom_components/autodoctor/websocket_api.py` → Add handler function + registration in `async_setup_websocket_api()`
- Command naming: Follow `autodoctor/command_name` pattern
- Tests: `tests/test_websocket_api.py`

**New Sensor/Entity:**
- Sensor: `custom_components/autodoctor/sensor.py` → Add class inheriting SensorEntity
- Binary sensor: `custom_components/autodoctor/binary_sensor.py` → Add class inheriting BinarySensorEntity
- Register in `__init__.py::PLATFORMS` list
- Tests: Test in integration tests or `tests/test_init.py`

**New Configuration Option:**
- Const: `custom_components/autodoctor/const.py` → Add CONF_* and DEFAULT_* constants
- UI: `custom_components/autodoctor/config_flow.py::OptionsFlowHandler.async_step_init()` → Add schema field
- Model: Update `custom_components/autodoctor/models.py::ValidationConfig` if option affects validation
- Strings: Update `strings.json` for UI labels

**Utility/Helper:**
- Location: Create in most relevant module or new `helpers.py` if shared by multiple
- Pattern: Private functions `_helper_name()` unless exported in `__all__`

## Special Directories

**`www/autodoctor/`:**
- Purpose: Frontend build environment (TypeScript/JavaScript)
- Generated: Yes (build output)
- Committed: No (only committed `www/autodoctor-card.js` compiled result to `custom_components/autodoctor/www/`)

**`translations/`:**
- Purpose: Internationalization files
- Generated: No (manually maintained)
- Committed: Yes (required by HA for UI strings)

**`tests/__pycache__/`, `custom_components/autodoctor/__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes (automatically)
- Committed: No (.gitignore)

---

*Structure analysis: 2026-01-30*
