# Automation Mutation Tester - Design Document

## Overview

A Home Assistant custom integration that performs on-demand mutation testing of automations to detect state-related issues before they cause failures in production.

**Problem:** Automation triggers can reference states that entities never produce (e.g., expecting `away` when entity uses `not_home`), have case sensitivity issues, reference missing entities, or check non-existent attributes. These issues cause automations to silently never fire.

**Solution:** Two-phase validation:
1. **Static validation** - analyze automations against known valid states
2. **Outcome verification** - dry-run simulation to verify actions are reachable

## Triggers

- **Manual service call** - on-demand analysis via `automation_mutation_tester.validate`
- **Automatic on automation save** - validate whenever automations are reloaded

## Issue Reporting

Issues are reported via three channels:
- Persistent notification
- Log warning/error
- Repair issue (Settings > Repairs)

## Scope

- All automations analyzed automatically (no opt-in required)
- Target: Home Assistant 2024.x+ (modern APIs)

---

## Architecture

### Core Components

1. **StateKnowledgeBase** - Builds valid states map from device class defaults, recorder history, and schema introspection
2. **AutomationAnalyzer** - Parses automation configs and extracts all state references
3. **ValidationEngine** - Compares references against knowledge base, produces issues
4. **SimulationEngine** - Dry-run verification that actions are reachable
5. **AutomationEventListener** - Hooks into automation reload events
6. **IssueReporter** - Unified output to logs, notifications, and Repairs API

---

## Component Details

### StateKnowledgeBase

Builds and maintains the "valid states" map for all entities.

**Data Sources (priority order):**

1. **Device Class Defaults:**

| Domain | Valid States |
|--------|-------------|
| `binary_sensor` | `on`, `off` |
| `person` | `home`, `not_home` |
| `device_tracker` | `home`, `not_home`, + zone names |
| `lock` | `locked`, `unlocked`, `locking`, `unlocking`, `jammed`, `opening`, `open` |
| `cover` | `open`, `closed`, `opening`, `closing` |
| `alarm_control_panel` | `disarmed`, `armed_home`, `armed_away`, `armed_night`, `armed_vacation`, `armed_custom_bypass`, `pending`, `arming`, `disarming`, `triggered` |
| `vacuum` | `cleaning`, `docked`, `idle`, `paused`, `returning`, `error` |
| `media_player` | `off`, `on`, `idle`, `playing`, `paused`, `standby`, `buffering` |

2. **Schema Introspection:**
   - `climate`: `hvac_modes`, `preset_modes`, `fan_modes`, `swing_modes`
   - `light`: `effect_list`
   - `select`/`input_select`: `options`
   - `fan`: `preset_modes`

3. **Recorder History:**
   - Query distinct states per entity over configurable lookback (default: 30 days)
   - Filters out `unknown`/`unavailable` as those are always valid but shouldn't be expected triggers

**Output Structure:**
```python
{
  "light.living_room": {"on", "off"},
  "climate.hvac": {"off", "heat", "cool", "auto"},
  "person.matt": {"home", "not_home"},
  "sensor.custom_thing": {"active", "idle", "error"}  # from history
}
```

---

### AutomationAnalyzer

Parses automation configs and extracts all entity/state references.

**Extraction Targets:**

1. **State Triggers** - `entity_id`, `to`, `from` values
2. **Numeric State Triggers** - `entity_id`, `attribute`
3. **State Conditions** - `entity_id`, `state`
4. **Template Conditions/Triggers** - Parse Jinja2 for `is_state()`, `states.domain.entity`, `state_attr()`

**Historical State Checks:**

1. **State Existence** - Has entity ever been in expected state?
2. **Transition Patterns** - Has `from` → `to` transition ever occurred?
3. **Staleness** - When was state last seen? Warn if > threshold

**Output Structure:**
```python
@dataclass
class StateReference:
    automation_id: str
    entity_id: str
    expected_state: str | None
    expected_attribute: str | None
    location: str  # "trigger[0]", "condition[2]", etc.
    source_line: int | None
    historical_match: bool
    last_seen: datetime | None
    transition_valid: bool  # for from/to triggers
```

---

### ValidationEngine

Compares extracted references against knowledge base.

**Validation Rules:**

| Check | Severity | Example |
|-------|----------|---------|
| Entity doesn't exist | Error | `binary_sensor.motoin_sensor` (typo) |
| State never valid | Error | `person.matt` → `"away"` (should be `not_home`) |
| State never observed | Error | Entity exists, state valid but never seen |
| Case mismatch | Warning | `"Armed_Away"` vs `"armed_away"` |
| Attribute doesn't exist | Error | `state_attr('climate.hvac', 'temprature')` |
| Transition never occurred | Warning | `from: home to: away` never happened |
| State is stale | Info | Last seen 45+ days ago |

**Fuzzy Matching:**
When mismatch found, use Levenshtein distance to suggest corrections.

**Issue Structure:**
```python
@dataclass
class ValidationIssue:
    severity: Literal["error", "warning", "info"]
    automation_id: str
    automation_name: str
    entity_id: str
    location: str
    message: str
    suggestion: str | None
    valid_states: list[str]
```

---

### SimulationEngine (Outcome Verification)

Verifies that each automation's actions are reachable.

**Purpose:** Answer "Can this automation ever actually do anything?"

**Analysis Per Automation:**
1. Identify all action paths
2. Trace reachability through conditions
3. Flag unreachable paths

**What Gets Flagged:**

| Issue | Example |
|-------|---------|
| Unreachable action | Condition requires impossible state |
| Contradictory conditions | `state: on` AND `state: off` for same entity |
| Unreachable branches | Template condition always false |
| Trigger-condition mismatch | Trigger on `home`, condition requires `not_home` |

**Output:**
```python
@dataclass
class OutcomeReport:
    automation_id: str
    automation_name: str
    triggers_valid: bool
    conditions_reachable: bool
    outcomes: list[OutcomePath]
    unreachable_paths: list[str]
    verdict: Literal["all_reachable", "partially_reachable", "unreachable"]
```

---

### AutomationEventListener

Triggers validation when automations change.

**Events Hooked:**
- `automation_reloaded`
- `config_entry_updated`
- `call_service` on `automation.reload`

**Debouncing:** 5-second delay to avoid spam during rapid edits.

---

### IssueReporter

Unified output to all channels.

**Channels:**
1. **Logs** - `_LOGGER.warning` / `.error`
2. **Persistent Notification** - Summary with link to Repairs
3. **Repairs API** - One issue per problem, auto-clears when resolved

**Severity Mapping:**
| Validation Result | Repairs Severity |
|-------------------|------------------|
| Error | `ERROR` |
| Warning | `WARNING` |
| Info | `WARNING` |

---

## Configuration

**Options (via UI):**

| Option | Default | Description |
|--------|---------|-------------|
| `history_days` | 30 | Recorder lookback |
| `staleness_threshold_days` | 30 | Warn if state not seen in X days |
| `validate_on_reload` | True | Auto-validate on automation reload |
| `debounce_seconds` | 5 | Delay before validation after reload |

---

## Services

| Service | Description |
|---------|-------------|
| `automation_mutation_tester.validate` | Run static validation |
| `automation_mutation_tester.validate_automation` | Validate specific automation |
| `automation_mutation_tester.simulate` | Run outcome verification |
| `automation_mutation_tester.refresh_knowledge_base` | Rebuild state knowledge |

---

## Entities

| Entity | Type | Purpose |
|--------|------|---------|
| `sensor.automation_validation_issues` | Sensor | Count of current issues |
| `binary_sensor.automation_validation_ok` | Binary Sensor | `on` if no errors |

---

## Project Structure

```
custom_components/automation_mutation_tester/
├── __init__.py              # Integration setup, event listeners
├── manifest.json            # Integration metadata
├── config_flow.py           # Config + options flow
├── const.py                 # Constants, domain, defaults
├── strings.json             # UI strings + repair translations
├── translations/
│   └── en.json
├── services.yaml            # Service definitions
├── sensor.py                # Issue count sensor
├── binary_sensor.py         # Validation OK sensor
├── knowledge_base.py        # StateKnowledgeBase class
├── analyzer.py              # AutomationAnalyzer class
├── validator.py             # ValidationEngine class
├── simulator.py             # SimulationEngine class
├── reporter.py              # IssueReporter class
└── device_class_states.py   # Hardcoded state mappings
```

**Dependencies:** `automation`, `recorder` (HA core only, no external packages)
