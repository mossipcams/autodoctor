# Autodoctor Codebase Index

A Home Assistant custom integration that validates automations to detect state-related issues before they cause silent failures.

**Version:** 2.1.0
**Requirements:** Home Assistant 2024.1+, Python 3.12+

## Directory Structure

```
autodoctor/
├── custom_components/autodoctor/    # Main integration code
│   ├── __init__.py                  # Integration setup & lifecycle
│   ├── analyzer.py                  # Automation parsing & extraction
│   ├── binary_sensor.py             # Integration health sensor
│   ├── config_flow.py               # Configuration UI
│   ├── conflict_detector.py         # Automation conflict detection
│   ├── const.py                     # Constants & defaults
│   ├── device_class_states.py       # Default state mappings
│   ├── domain_attributes.py         # Domain attribute mappings
│   ├── fix_engine.py                # Suggestion & correction logic
│   ├── jinja_validator.py           # Jinja2 template validation
│   ├── knowledge_base.py            # Valid state knowledge
│   ├── models.py                    # Core data structures
│   ├── reporter.py                  # Issue output & repairs
│   ├── sensor.py                    # Issue count sensor
│   ├── simulator.py                 # Outcome reachability verification
│   ├── learned_states_store.py      # User-learned state persistence
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
└── www/                             # Frontend build assets
```

## Core Modules

### Integration Lifecycle
- **`__init__.py`** - Entry point, HA lifecycle hooks, automation extraction

### Analysis Layer
- **`analyzer.py`** - Parses automation configs, extracts state references from triggers/conditions/actions
- **`validator.py`** - Validates state references against knowledge base
- **`jinja_validator.py`** - Validates Jinja2 template syntax
- **`conflict_detector.py`** - Finds automations with opposing actions on same entity
- **`simulator.py`** - Verifies automation outcomes are reachable (trigger/condition validity)

### Knowledge & Suggestions
- **`knowledge_base.py`** - Builds valid state mappings from device classes, schema introspection, and recorder history
- **`device_class_states.py`** - 30+ predefined domain state sets
- **`domain_attributes.py`** - Domain-specific attribute mappings to prevent false positives
- **`fix_engine.py`** - Synonym table, fuzzy matching for suggestions

### Data Models
- **`models.py`** - Core structures: `Severity`, `IssueType`, `StateReference`, `ValidationIssue`, `EntityAction`, `TriggerInfo`, `ConditionInfo`, `Conflict`, `Verdict`, `OutcomeReport`

### Persistence & API
- **`learned_states_store.py`** - Thread-safe storage of user-learned states
- **`suppression_store.py`** - Thread-safe storage of dismissed issues
- **`websocket_api.py`** - WebSocket commands for frontend communication
- **`reporter.py`** - Outputs issues to logs and repair entries

### Sensors
- **`sensor.py`** - Active validation issue count
- **`binary_sensor.py`** - Integration health status

### Configuration
- **`config_flow.py`** - Single-instance setup, options for history lookback, debounce delay
- **`const.py`** - Domain: "autodoctor", version, configuration keys

## WebSocket API

| Command | Description |
|---------|-------------|
| `autodoctor/issues` | Get current issues with fix suggestions |
| `autodoctor/refresh` | Trigger a validation refresh |
| `autodoctor/validation` | Get validation issues only |
| `autodoctor/validation/run` | Run validation on demand |
| `autodoctor/conflicts` | Get detected conflicts |
| `autodoctor/conflicts/run` | Detect conflicts on demand |
| `autodoctor/suppress` | Suppress an issue (optionally learn state) |
| `autodoctor/clear_suppressions` | Clear all suppressions |

## Services

- `autodoctor.validate` - Run validation (specific automation or all)
- `autodoctor.validate_automation` - Run validation on a specific automation
- `autodoctor.simulate` - Run outcome verification on automations
- `autodoctor.refresh_knowledge_base` - Rebuild state knowledge base

## Validation Rules

| Check | Severity |
|-------|----------|
| Entity doesn't exist | ERROR |
| State never valid | ERROR |
| Case mismatch | WARNING |
| Attribute doesn't exist | ERROR |
| Template syntax error | ERROR |
| Unknown template filter | WARNING |
| Unknown template test | WARNING |

## Test Files

- `test_analyzer.py` - Automation parsing
- `test_validator.py` - State validation
- `test_conflict_detector.py` - Conflict detection
- `test_knowledge_base.py` - State knowledge building
- `test_learned_states_store.py` - Learned states persistence
- `test_fix_engine.py` - Suggestion logic
- `test_models.py` - Data model serialization
- `test_reporter.py` - Issue reporting
- `test_websocket_api.py` - WebSocket endpoints
- `test_websocket_api_learning.py` - Learning on suppression
- `test_jinja_validator.py` - Jinja2 template validation
- `test_device_class_states.py` - Default states
- `test_init.py` - Integration lifecycle

## Scripts

- `scripts/extract_ha_states.py` - Extract valid states from Home Assistant source code
