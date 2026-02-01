# Autodoctor Codebase Index

A Home Assistant custom integration that validates automations to detect state-related issues before they cause silent failures.

**Version:** 2.6.2
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
- **`validator.py`** - Validates state references against knowledge base (conservative mode: only validates whitelisted domains with stable states); also provides `get_entity_suggestion()` for fuzzy entity matching
- **`service_validator.py`** - Validates service calls against HA service registry (existence, required params, capability-dependent param handling, select/enum option validation)
- **`ha_catalog.py`** - Dataclass-based registry of HA's Jinja2 filters and tests (101 filters, 23 tests). Single source of truth for filter/test name recognition.
- **`jinja_validator.py`** - Validates Jinja2 template syntax and semantics (entity existence, state validity, attribute existence; opt-in filter/test validation)

### Knowledge & Suggestions
- **`knowledge_base.py`** - Builds valid state mappings from device classes, entity registry capabilities, schema introspection, and recorder history
- **`device_class_states.py`** - 30+ predefined domain state sets
- **`domain_attributes.py`** - Domain-specific attribute mappings to prevent false positives
### Data Models
- **`models.py`** - Core structures: `Severity`, `IssueType`, `StateReference`, `ValidationIssue`, `ServiceCall`, `VALIDATION_GROUPS`, `VALIDATION_GROUP_ORDER`

### Persistence & API
- **`learned_states_store.py`** - Thread-safe storage of user-learned states
- **`suppression_store.py`** - Thread-safe storage of dismissed issues
- **`websocket_api.py`** - WebSocket commands for frontend communication
- **`reporter.py`** - Outputs issues to logs and repair entries

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
Validates entity states, attributes, and registry references in triggers/conditions/actions. **Conservative mode**: state validation only applies to whitelisted domains with stable states (binary_sensor, person, sun, device_tracker, input_boolean, group).

| Check | Severity | Description |
|-------|----------|-------------|
| Entity doesn't exist | ERROR | Entity ID not found in entity registry |
| Entity existed historically | INFO | Entity was removed/renamed |
| State never valid | ERROR | State value never observed for entity (whitelisted domains only) |
| Case mismatch | WARNING | State exists but with different casing |
| Attribute doesn't exist | WARNING | Attribute not found on entity |
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
Validates Jinja2 template syntax and semantics using HA-specific context.

| Check | Severity | Description |
|-------|----------|-------------|
| Template syntax error | ERROR | Invalid Jinja2 syntax |
| Template entity not found | ERROR | Referenced entity doesn't exist |
| Template invalid state | ERROR | State comparison uses invalid value (whitelisted domains only) |
| Template attribute not found | WARNING | Attribute doesn't exist on entity |
| Template device/area/zone not found | ERROR | Registry reference invalid |
| Unknown template filter | WARNING | Filter not in HA/Jinja2 built-ins (opt-in via strict mode) |
| Unknown template test | WARNING | Test not in HA/Jinja2 built-ins (opt-in via strict mode) |

**Semantic validation:**
- Validates `states()`, `state_attr()`, `is_state()`, `is_state_attr()` calls
- Checks `device_id()`, `area_id()`, `area_name()` registry lookups
- Validates filter/test signatures against HA-specific implementations (when strict mode enabled)
- **Note**: Undefined variable checking removed to eliminate false positives with blueprints and input variables

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

- `test_analyzer.py` - Automation parsing
- `test_validator.py` - State validation
- `test_knowledge_base.py` - State knowledge building
- `test_learned_states_store.py` - Learned states persistence
- `test_entity_suggestion.py` - Entity suggestion (fuzzy matching via get_entity_suggestion)
- `test_models.py` - Data model serialization
- `test_reporter.py` - Issue reporting
- `test_websocket_api.py` - WebSocket endpoints
- `test_websocket_api_learning.py` - Learning on suppression
- `test_ha_catalog.py` - HA Jinja2 catalog (completeness, API surface, migration)
- `test_jinja_validator.py` - Jinja2 template validation
- `test_device_class_states.py` - Default states
- `test_init.py` - Integration lifecycle
- `test_architectural_improvements.py` - Architectural review implementations (config, depth limits, KB sharing)
- `test_service_validator.py` - Service call validation
- `test_suppression_store.py` - Suppression store (orphan cleanup)

## Scripts

- `scripts/extract_ha_states.py` - Extract valid states from Home Assistant source code

## Ongoing Refactoring (v2.7.0)

Autodoctor is undergoing a validation scope narrowing to reduce false positives and focus on high-confidence checks. Target: <5% false positive rate.

### Key Changes

**Removed Validations:**
- Undefined template variables (eliminated #1 source of false positives with blueprints)
- Basic service parameter type checking (number/boolean/text validation unreliable due to YAML coercion)

**Conservative State Validation:**
- State validation now only applies to domains with stable, well-defined states
- **Whitelisted domains**: `binary_sensor`, `person`, `sun`, `device_tracker`, `input_boolean`, `group`
- Custom sensors and flexible integrations skip state validation to avoid false positives

**Opt-In Strict Modes:**
- Unknown Jinja2 filters/tests: OFF by default (enable via "Strict template validation")
- Unknown service parameters: OFF by default (enable via "Strict service validation")

**Severity Adjustments:**
- Removed entities: ERROR → INFO
- Missing attributes: ERROR → WARNING

### Rationale

Better to miss some issues than generate noise and reduce trust. Focus on deterministic, high-confidence validations. Users can opt into stricter checking if they prefer comprehensive coverage over precision.

See `docs/validation-narrowing-checklist.md` for complete implementation plan.
