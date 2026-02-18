# Autodoctor Codebase Index

A Home Assistant custom integration that validates automations to detect state-related issues before they cause silent failures.

**Version:** 2.13.3
**Requirements:** Home Assistant 2024.1+, Python 3.12+

## Directory Structure

```
autodoctor/
├── custom_components/autodoctor/    # Main integration code
│   ├── __init__.py                  # Integration setup & lifecycle
│   ├── analyzer.py                  # Automation parsing & extraction
│   ├── binary_sensor.py             # Integration health sensor
│   ├── config_flow.py               # Configuration UI
│   ├── const.py                     # Constants & defaults
│   ├── device_class_states.py       # Default state mappings
│   ├── domain_attributes.py         # Domain attribute mappings
│   ├── ha_catalog.py                # HA Jinja2 filter/test catalog
│   ├── jinja_validator.py           # Jinja2 template validation
│   ├── knowledge_base.py            # Valid state knowledge
│   ├── models.py                    # Core data structures
│   ├── reporter.py                  # Issue output & repairs
│   ├── runtime_health_state_store.py # Runtime health model state persistence
│   ├── runtime_event_store.py       # Runtime event/score SQLite storage
│   ├── runtime_monitor.py           # River-based runtime health monitoring
│   ├── sensor.py                    # Issue count sensor
│   ├── learned_states_store.py      # User-learned state persistence
│   ├── service_validator.py         # Service call validation
│   ├── suppression_store.py         # Dismissed issue persistence
│   ├── validator.py                 # State reference validation
│   ├── websocket_api.py             # Frontend communication
│   ├── www/                         # Frontend assets
│   │   └── autodoctor-card.js       # Lovelace card
│   ├── translations/                # i18n strings
│   ├── manifest.json                # Integration metadata
│   ├── services.yaml                # Service definitions
│   └── strings.json                 # UI strings
├── scripts/                         # Utility scripts
│   └── extract_ha_states.py         # Extract valid states from HA source
├── tests/                           # Test suite
├── docs/plans/                      # Design documents
└── www/autodoctor/                  # Frontend source (TypeScript)
    ├── autodoctor-card.ts           # Main Lovelace card component
    ├── autodoctor-card-editor.ts    # Card config editor
    ├── autodoc-issue-group.ts       # Issue group sub-component
    ├── autodoc-pipeline.ts          # Validation pipeline sub-component
    ├── autodoc-suppressions.ts      # Suppressions management sub-component
    ├── types.ts                     # Shared TypeScript interfaces
    └── styles.ts                    # Shared CSS design tokens & styles
```

## Core Modules

### Integration Lifecycle
- **`__init__.py`** - Entry point, HA lifecycle hooks, automation extraction

### Analysis Layer
- **`analyzer.py`** - Parses automation configs, extracts state references from triggers/conditions/actions (21 trigger types, 10 condition types, depth-limited recursion)
- **`validator.py`** - Validates state references and attribute values against knowledge base (conservative mode: only validates whitelisted domains with stable states); also provides `get_entity_suggestion()` for fuzzy entity matching
- **`service_validator.py`** - Validates service calls against HA service registry (existence, required params, capability-dependent param handling, select/enum option validation)
- **`ha_catalog.py`** - Dataclass-based registry of HA's Jinja2 filters and tests (101 filters, 23 tests). Single source of truth for filter/test name recognition.
- **`jinja_validator.py`** - Validates Jinja2 template syntax and semantics (syntax errors; opt-in unknown filter/test warnings). Entity validation handled solely by `validator.py` via the analyzer path.

### Knowledge & Suggestions
- **`knowledge_base.py`** - Builds valid state mappings from device classes, enum sensor options, entity registry capabilities, schema introspection, and recorder history
- **`device_class_states.py`** - 30+ predefined domain state sets
- **`domain_attributes.py`** - Domain-specific attribute mappings to prevent false positives
### Data Models
- **`models.py`** - Core structures: `Severity`, `IssueType`, `StateReference`, `ValidationIssue`, `ServiceCall`, `VALIDATION_GROUPS`, `VALIDATION_GROUP_ORDER`

### Persistence & API
- **`learned_states_store.py`** - Thread-safe storage of user-learned states
- **`runtime_health_state_store.py`** - JSON-backed storage for runtime three-model state (count/gap/burst baselines and alert counters)
- **`runtime_event_store.py`** - Local SQLite runtime event and score history store (trigger events, backfill metadata, score telemetry)
- **`suppression_store.py`** - Thread-safe storage of dismissed issues (auto-cleans orphaned suppressions referencing removed issue types)
- **`websocket_api.py`** - WebSocket commands for frontend communication
- **`reporter.py`** - Outputs issues to logs and repair entries
- **`runtime_monitor.py`** - Runtime trigger-behavior anomaly detection with River (opt-in)

### Sensors
- **`sensor.py`** - Active validation issue count
- **`binary_sensor.py`** - Integration health status

### Configuration
- **`config_flow.py`** - Single-instance setup, options for history lookback, debounce delay, strict validation modes
- **`const.py`** - Domain, version, configuration keys, `STATE_VALIDATION_WHITELIST`, `MAX_RECURSION_DEPTH`, strict validation flags

## WebSocket API

| Command | Description |
|---------|-------------|
| `autodoctor/issues` | Get current issues with fix suggestions |
| `autodoctor/refresh` | Trigger a validation refresh |
| `autodoctor/validation` | Get validation issues only |
| `autodoctor/validation/run` | Run validation on demand |
| `autodoctor/suppress` | Suppress an issue (optionally learn state) |
| `autodoctor/clear_suppressions` | Clear all suppressions |
| `autodoctor/validation/run_steps` | Run validation and return per-group structured results |
| `autodoctor/validation/steps` | Get cached per-group validation results |
| `autodoctor/list_suppressions` | List all suppressed issues with metadata |
| `autodoctor/unsuppress` | Remove a single suppression by key |

## Services

- `autodoctor.validate` - Run validation (specific automation or all)
- `autodoctor.validate_automation` - Run validation on a specific automation
- `autodoctor.refresh_knowledge_base` - Rebuild state knowledge base

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| History lookback | 30 days | How far back to check recorder history for valid states |
| Validate on reload | ON | Auto-validate when automations are reloaded |
| Debounce delay | 5s | Delay before running validation after config changes |
| **Strict template validation** | OFF | Enable warnings for unknown Jinja2 filters/tests (disable if using custom components) |
| **Strict service validation** | OFF | Enable warnings for unknown service parameters (may flag valid capability-dependent params) |

**Validation Philosophy**: Autodoctor defaults to high-confidence validations to minimize false positives. Strict modes are opt-in for users who want more comprehensive checking and are willing to manage occasional false positives.

## Validation Families

Autodoctor performs three distinct families of validation:

### 1. State Reference Validation (`validator.py`)
Validates entity states, attributes, attribute values, and registry references in triggers/conditions/actions. **Conservative mode**: state validation only applies to whitelisted domains with stable states (`alarm_control_panel`, `automation`, `binary_sensor`, `calendar`, `climate`, `cover`, `device_tracker`, `fan`, `group`, `humidifier`, `input_boolean`, `input_select`, `lawn_mower`, `light`, `lock`, `media_player`, `person`, `remote`, `schedule`, `script`, `select`, `siren`, `sun`, `switch`, `timer`, `update`, `vacuum`, `valve`, `water_heater`, `weather`) plus enum sensors (device_class: enum with declared options).

| Check | Severity | Description |
|-------|----------|-------------|
| Entity doesn't exist | ERROR | Entity ID not found in entity registry |
| Entity existed historically | INFO | Entity was removed/renamed |
| State never valid | ERROR | State value never observed for entity (whitelisted domains only) |
| Case mismatch | WARNING | State or attribute value exists but with different casing |
| Attribute doesn't exist | WARNING | Attribute not found on entity |
| Invalid attribute value | WARNING | Attribute value not in known valid values (e.g., fan_mode, preset_mode) |
| Device not found | ERROR | Device ID not in device registry |
| Area not found | ERROR | Area ID not in area registry |
| Tag not found | ERROR | Tag ID not in tag registry |

### 2. Service Call Validation (`service_validator.py`)
Validates service calls against Home Assistant service registry.

| Check | Severity | Description |
|-------|----------|-------------|
| Service doesn't exist | ERROR | Service not registered in HA |
| Missing required parameter | ERROR | Required service parameter not provided |
| Unknown parameter | WARNING | Parameter not in service schema (with suggestions; opt-in via config) |
| Invalid select option | WARNING | Parameter value not in allowed select options |
| Template in target field | INFO | Target uses template (runtime validation skipped) |

**Special handling:**
- Capability-dependent parameters (e.g., `light.turn_on` color modes) are not flagged as unknown
- List-type parameters allow both single values and lists
- Templates in data/target fields skip validation
- **Type checking simplified**: Only validates discrete select/enum options (not basic types like number/boolean/text)

### 3. Jinja2 Template Validation (`jinja_validator.py`)
Validates Jinja2 template syntax and filter/test usage. Entity validation is handled exclusively by `validator.py` through the analyzer path (v2.14.0).

| Check | Severity | Description |
|-------|----------|-------------|
| Template syntax error | ERROR | Invalid Jinja2 syntax |
| Unknown template filter | WARNING | Filter not in HA/Jinja2 built-ins (opt-in via strict mode) |
| Unknown template test | WARNING | Test not in HA/Jinja2 built-ins (opt-in via strict mode) |

**Scope (v2.14.0):**
- Syntax validation of all Jinja2 templates in triggers, conditions, actions, and data fields
- Validates filter/test names against HA-specific catalog (when strict mode enabled)
- Recursively walks nested action structures (choose, if/then/else, repeat, parallel) with depth limiting
- **Removed in v2.14.0**: Entity existence, state validity, attribute existence, and registry reference checks (were a duplicate code path generating false positives)

## Trigger Type Coverage

Supports all 17 Home Assistant trigger types:
- State, numeric_state, template (entity/state validation)
- Zone, sun, calendar (entity validation)
- Device, tag, geo_location (registry validation)
- Event, MQTT, webhook, persistent_notification (template extraction)
- Time (entity reference validation)
- Time pattern, homeassistant, sentence (no validation needed)

## Condition Type Coverage

Supports all 10 Home Assistant condition types:
- State, template (entity/state validation)
- Numeric state, zone, sun, time (entity/attribute validation)
- Device (registry validation)
- And, or, not (recursive)
- Trigger (no validation needed)

## Test Files

**Test Suite Quality:** All test files fully type-annotated (460+ test functions with `-> None` return types and typed parameters). Comprehensive docstrings explain what each test validates and why it matters. See `.planning/test-refactor-summary.md` for details.

**Test Coverage:** 693 tests passing (2 skipped stubs), ~15,600 lines

**Core Test Files:**
- `test_analyzer.py` (99 tests) - Automation parsing (21 trigger types, 10 condition types, depth limits)
- `test_validator.py` (39 tests) - State validation engine
- `test_knowledge_base.py` (52 tests) - Multi-source state truth (device classes, learned states, capabilities, history)
- `test_service_validator.py` (40 tests, 78 parameterized cases) - Service call validation
- `test_jinja_validator.py` (60 tests) - Jinja2 template syntax and semantics
- `test_init.py` (38 tests) - Integration lifecycle and orchestration
- `test_websocket_api.py` (20 tests) - WebSocket API commands
- `test_models.py` (16 tests, 28 parameterized cases) - Data models and enum validation
- `test_ha_catalog.py` (19 tests, 50 parameterized cases) - HA Jinja2 catalog completeness
- `test_architectural_improvements.py` (16 tests) - Guard tests for architectural decisions (with "Guard:" docstrings)
- `test_reporter.py` (4 tests) - Issue reporting to repair registry
- `test_learned_states_store.py` (14 tests) - Learned state persistence, domain/integration isolation, unicode, concurrency
- `test_entity_suggestion.py` (4 tests, 8 parameterized cases) - Fuzzy entity matching
- `test_device_class_states.py` (8 tests) - Device class default states
- `test_websocket_api_learning.py` (3 tests) - State learning on suppression
- `test_suppression_store.py` (10 tests) - Orphan cleanup, async_clear_all (CRITICAL), data verification, edge cases, concurrency
- `test_config_flow.py` (6 tests) - Configuration UI flow
- `test_sensor.py` (6 tests) - Issue count sensor platform
- `test_binary_sensor.py` (5 tests) - Health status sensor platform
- `test_defect_regressions.py` (4 tests) - P0/P1 defect regression tests (hass.data update, template data crash, required param skip, entity cache recovery)
- `test_attribute_value_validation.py` (11 tests) - Attribute value validation (analyzer extraction, validator checks, edge cases)

**Property-Based Test Files (Hypothesis fuzzing, 200 examples each):**
- `test_property_based.py` (8 tests) - Analyzer/service-validator functions: automation extraction, template parsing, state normalization
- `test_property_based_validator.py` (12 tests) - Validator/device-class/domain-attribute pure functions: entity suggestions, state lookups, attribute mappings
- `test_property_based_jinja.py` (9 tests) - Jinja validator pure functions: template validation, nested action structures, variable extraction
- `test_property_based_remaining.py` (12 tests) - Reporter, websocket_api, knowledge_base, and models pure functions: issue formatting, status computation, domain extraction
- `test_property_based_stores.py` (16 tests) - LearnedStatesStore and SuppressionStore: hierarchical isolation, key parsing, orphan cleanup, unicode handling
- `test_property_based_analyzer_advanced.py` (11 tests) - Advanced analyzer patterns: filter chains, nested control flow, registry functions, parallel actions, multiline templates
- `conftest.py` - Shared fixtures (all type-annotated)

## Scripts

- `scripts/extract_ha_states.py` - Extract valid states from Home Assistant source code

## Validation Narrowing (v2.7.0 -- v2.14.0)

Autodoctor has undergone validation scope narrowing to reduce false positives and focus on high-confidence checks. Target: <5% false positive rate.

### Key Changes

**Removed Validations:**
- Undefined template variables (eliminated #1 source of false positives with blueprints)
- Basic service parameter type checking (number/boolean/text validation unreliable due to YAML coercion)
- Filter argument count validation (CatalogEntry simplified to name/kind/source/category only)
- `for_each` template variable extraction (produced false positives)
- **Template entity validation (v2.14.0)**: Entity existence, state validity, attribute existence, and registry reference checks removed from `jinja_validator.py` -- these were a duplicate code path also covered by `validator.py` via the analyzer, and generated false positives. 7 TEMPLATE_* IssueType members removed (14 remain). Cross-family dedup machinery removed.

**Conservative State Validation:**
- State validation now only applies to domains with stable, well-defined states
- **Whitelisted domains** (30): `alarm_control_panel`, `automation`, `binary_sensor`, `calendar`, `climate`, `cover`, `device_tracker`, `fan`, `group`, `humidifier`, `input_boolean`, `input_select`, `lawn_mower`, `light`, `lock`, `media_player`, `person`, `remote`, `schedule`, `script`, `select`, `siren`, `sun`, `switch`, `timer`, `update`, `vacuum`, `valve`, `water_heater`, `weather`
- **Enum sensors**: `device_class: enum` sensors validated against their declared `options` attribute (without adding sensor domain to whitelist)
- Non-enum sensors and flexible integrations skip state validation to avoid false positives

**Opt-In Strict Modes:**
- Unknown Jinja2 filters/tests: OFF by default (enable via "Strict template validation")
- Unknown service parameters: OFF by default (enable via "Strict service validation")

**Severity Adjustments:**
- Removed entities: ERROR -> INFO
- Missing attributes: ERROR -> WARNING

**Suppression Auto-Cleanup (v2.14.0):**
- Suppressions referencing removed IssueType members are automatically cleaned on load

### Rationale

Better to miss some issues than generate noise and reduce trust. Focus on deterministic, high-confidence validations. Users can opt into stricter checking if they prefer comprehensive coverage over precision.
