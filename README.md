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
2. **Conflict Detection** - Finds automations that take opposing actions on the same entity (with trigger overlap awareness)
3. **Smart Suggestions** - Suggests fixes using synonyms and fuzzy matching
4. **Issue Suppression** - Dismiss false positives so they don't reappear

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

Autodoctor includes a custom card with two tabs:

- **Validation** - Shows state validation issues (wrong states, typos, missing entities)
- **Conflicts** - Shows automations with opposing actions on the same entity

Add the card to your dashboard:

```yaml
type: custom:autodoctor-card
```

The card displays issues with:
- Severity indicators (error/warning)
- Direct links to edit the automation
- Smart fix suggestions
- Dismiss buttons to suppress false positives

## Usage

### Services

| Service | Description |
|---------|-------------|
| `autodoctor.validate` | Run validation on all automations (or a specific one) |
| `autodoctor.refresh_knowledge_base` | Rebuild the state knowledge base |

### Issue Reporting

Issues are reported via:
- **Log warnings/errors** - For monitoring
- **Repairs** - Settings → Repairs shows actionable issues

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| History lookback (days) | 30 | How many days of state history to analyze |
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

### Conflict Detection

Autodoctor detects when multiple automations take opposing actions on the same entity. The conflict detector is trigger-overlap aware:

- **No conflict if triggers can't fire together** - e.g., one triggers at 6am, another at 10pm
- **No conflict if conditions are mutually exclusive** - e.g., one requires `mode: on`, another requires `mode: off`
- **Conflicts only reported for turn_on vs turn_off** - toggle actions excluded (too noisy)

### Smart Suggestions

When a state is invalid, Autodoctor suggests corrections using:

1. **Synonym table** - Maps common mistakes like `away` → `not_home`, `true` → `on`
2. **Fuzzy matching** - Suggests close matches for typos

When an entity is missing, suggestions are based on same-domain fuzzy matching.

## Requirements

- Home Assistant 2024.1 or newer (supports both legacy `service:` and new `action:` formats)
- Recorder integration (for history analysis)

## License

MIT License - see [LICENSE](LICENSE) for details.
