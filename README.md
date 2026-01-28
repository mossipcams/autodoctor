# Autodoctor

A Home Assistant custom integration that validates your automations to detect state-related issues before they cause silent failures.

## The Problem

Automations can fail silently when they reference states that will never occur:

- **Wrong state values**: Trigger expects `away` but entity uses `not_home`
- **Case sensitivity**: `Armed_Away` vs `armed_away`
- **Typos**: `binary_sensor.motoin_sensor` instead of `motion`
- **Missing attributes**: `state_attr('climate.hvac', 'temprature')`
- **Impossible conditions**: Trigger on `home` but condition requires `not_home`
- **Conflicting automations**: One automation turns on a light while another turns it off

These issues cause automations to never fire or behave unpredictably, with no errors in the logs.

## Features

1. **Static Validation** - Analyzes automation configs against known valid states
2. **Outcome Verification** - Verifies that automation actions are actually reachable
3. **Conflict Detection** - Finds automations that take opposing actions on the same entity
4. **Smart Suggestions** - Suggests fixes based on entity relationships and learns from your feedback
5. **Issue Suppression** - Dismiss false positives so they don't reappear

## Installation

### Manual Installation

1. Copy `custom_components/autodoctor/` to your Home Assistant `custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "Autodoctor" and follow the setup flow

### HACS Installation

1. Add this repository as a custom repository in HACS
2. Install "Autodoctor" from HACS
3. Restart Home Assistant
4. Add the integration via Settings → Devices & Services

## Lovelace Card

Autodoctor includes a custom card with three tabs:

- **Validation** - Shows state validation issues (wrong states, typos, missing entities)
- **Outcomes** - Shows unreachable automation paths
- **Conflicts** - Shows automations with opposing actions on the same entity

Add the card to your dashboard:

```yaml
type: custom:autodoctor-card
```

The card displays issues with:
- Severity indicators (error/warning)
- Direct links to edit the automation
- Smart fix suggestions with confidence scores
- Dismiss buttons to suppress false positives

## Usage

### Services

| Service | Description |
|---------|-------------|
| `autodoctor.validate` | Run validation on all automations (or a specific one) |
| `autodoctor.simulate` | Verify that automation outcomes are reachable |
| `autodoctor.detect_conflicts` | Find conflicting actions across automations |
| `autodoctor.refresh_knowledge_base` | Rebuild the state knowledge base |

### Entities

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.autodoctor_issues` | Sensor | Count of current validation issues |
| `binary_sensor.autodoctor_ok` | Binary Sensor | `on` if there are problems |

### Issue Reporting

Issues are reported via:
- **Persistent notifications** - Summary with details
- **Log warnings/errors** - For monitoring
- **Repairs** - Settings → Repairs shows actionable issues

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| History lookback (days) | 30 | How many days of state history to analyze |
| Staleness threshold (days) | 30 | Warn if referenced state hasn't occurred recently |
| Validate on reload | Yes | Automatically validate when automations reload |
| Debounce delay (seconds) | 5 | Wait before validating after reload |

## How It Works

### State Knowledge Base

Autodoctor builds a knowledge base of valid states from:

1. **Device class defaults** - Known states for each domain (e.g., `person` → `home`, `not_home`)
2. **Schema introspection** - Reads `hvac_modes`, `options`, `effect_list` from entities
3. **Recorder history** - Learns actual states from your historical data

### What Gets Validated

- State triggers (`to`, `from` values)
- Numeric state triggers (entity and attribute existence)
- State conditions
- Template conditions (parses `is_state()`, `states.domain.entity`, `state_attr()`)

### Validation Rules

| Check | Severity | Example |
|-------|----------|---------|
| Entity doesn't exist | Error | `binary_sensor.motoin_sensor` (typo) |
| State never valid | Error | `person.matt` → `"away"` (should be `not_home`) |
| Case mismatch | Warning | `"Armed_Away"` vs `"armed_away"` |
| Attribute doesn't exist | Error | `state_attr('climate.hvac', 'temprature')` |
| Transition never occurred | Warning | `from: home` to `away` never happened |

### Conflict Detection

Autodoctor detects when multiple automations take opposing actions on the same entity:

| Conflict | Severity | Description |
|----------|----------|-------------|
| turn_on vs turn_off | Error | Direct conflict when both triggers fire |
| toggle vs anything | Warning | Toggle behavior is unpredictable with other automations |

### Smart Suggestions

When an entity is missing or removed, Autodoctor suggests replacements using:

- **String similarity** (30%) - Fuzzy matching on entity names
- **Relationship score** (50%) - Same device (+0.4), same area (+0.3), same domain (+0.2), shared labels (+0.1)
- **Learning** - Suggestions you dismiss are penalized in future recommendations

Suggestions show confidence percentages and reasoning (e.g., "Same area", "Same device").

## Requirements

- Home Assistant 2024.1 or newer (supports both legacy `service:` and new `action:` formats)
- Recorder integration (for history analysis)

## License

MIT License - see [LICENSE](LICENSE) for details.
