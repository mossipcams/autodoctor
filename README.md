# Autodoctor

[![GitHub Release](https://img.shields.io/github/v/release/mossipcams/autodoctor?style=flat-square)](https://github.com/mossipcams/autodoctor/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

A Home Assistant custom integration that validates your automations to detect issues before they cause silent failures.

## The Problem

You create an automation, it looks correct, but it never fires. No errors in the logs. Everything seems fine, but nothing happens.

Hours later you discover:
- You wrote `away` but the person entity uses `not_home`
- You typed `Armed_Away` but it's actually `armed_away`
- You have a typo: `binary_sensor.motion_sensor`
- A template has a syntax error: `{{ is_state('sensor.temp' }}`

**Autodoctor catches these issues before they waste your time.**

## Features

- **Static Validation** - Checks automation configs against known valid states
- **Jinja Template Validation** - Catches syntax errors in templates before they fail
- **Service Call Validation** - Validates service calls against the HA service registry
- **Entity Suggestions** - Suggests fixes for entity ID typos using fuzzy matching
- **State Learning** - Learns valid states when you dismiss false positives
- **Issue Suppression** - Dismiss false positives globally (card, Repairs, sensors)
- **Runtime Health Monitoring (ML)** - Detects stalled and overactive automations from recorder history

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → Custom repositories
3. Add `https://github.com/mossipcams/autodoctor` as an Integration
4. Install "Autodoctor" from HACS
5. Restart Home Assistant
6. Go to Settings → Devices & Services → Add Integration → Autodoctor

### Manual Installation

1. Copy `custom_components/autodoctor/` to your Home Assistant `custom_components/` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration → Autodoctor

## Dashboard Card

Autodoctor includes a custom Lovelace card that displays validation issues.

Add the card to your dashboard:

```yaml
type: custom:autodoctor-card
```

The card displays issues with:
- Severity indicators (error/warning)
- Direct links to edit the automation
- Entity ID fix suggestions for typos
- Dismiss buttons (dismissing also teaches Autodoctor valid states)

## Services

| Service | Description |
|---------|-------------|
| `autodoctor.validate` | Run validation on all automations (or a specific one) |
| `autodoctor.validate_automation` | Run validation on a specific automation (required `automation_id`) |
| `autodoctor.refresh_knowledge_base` | Rebuild the state knowledge base from history |

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.autodoctor_issues` | Sensor | Count of active validation issues |
| `binary_sensor.autodoctor_problems` | Binary Sensor | On if there are any issues |

## Issue Reporting

Issues are reported via:
- **Repairs** - Settings → Repairs shows actionable issues
- **Log warnings/errors** - For monitoring and debugging

Suppressed issues are removed from all primary issue surfaces (dashboard card, Repairs, and Autodoctor entities). Suppression metadata is still retained for counts/history.

## Configuration Options

Access via Settings → Devices & Services → Autodoctor → Configure

| Option | Default | Description |
|--------|---------|-------------|
| History lookback (days) | 30 | Days of state history to analyze |
| Validate on reload | Yes | Auto-validate when automations reload |
| Debounce delay (seconds) | 5 | Wait before validating after reload |
| Strict template validation | No | Warn about unknown Jinja2 filters/tests (disable if using custom components) |
| Strict service validation | No | Warn about unknown service parameters |
| Runtime health monitoring (ML) | No | Enable trigger-behavior anomaly detection |
| Runtime baseline history (days) | 30 | Recorder history window for runtime behavior baseline |
| Runtime warmup samples | 3 | Minimum active baseline days before anomaly scoring starts |
| Runtime anomaly threshold | 0.8 | Score threshold for runtime anomaly issue generation |
| Runtime minimum expected events/day | 0 | Minimum daily baseline activity required for stalling checks |
| Runtime overactive multiplier | 3.0 | 24h trigger count multiplier over baseline for overactive detection |
| Runtime hour-ratio lookback (days) | 30 | Lookback window used for same-hour activity ratio features |

Runtime baseline must be larger than the internal cold-start window (7 days) so anomaly training rows can be generated.

## How It Works

### State Knowledge Base

Autodoctor builds a knowledge base of valid states from multiple sources:

1. **Device class defaults** - Known states for 30+ domains (e.g., `person` → `home`, `not_home`)
2. **Enum sensor options** - Validates `device_class: enum` sensors against their declared `options` attribute
3. **Schema introspection** - Reads `hvac_modes`, `options`, `effect_list` from entity attributes
4. **Recorder history** - Learns actual states from your historical data
5. **User feedback** - Remembers states you mark as valid when dismissing issues

### What Gets Validated

- State triggers (`to`, `from` values) -- conservative: only whitelisted domains
- Numeric state triggers (entity and attribute existence)
- State conditions
- Template syntax (Jinja2 parse errors, unknown filters/tests with strict mode)
- Service calls (existence, required params, select option validation)
- Entity references in triggers, conditions, and actions

### Validation Rules

| Check | Severity | Example |
|-------|----------|---------|
| Entity doesn't exist | Error | `binary_sensor.motoin_sensor` (typo) |
| State never valid | Error | `person.matt` → `"away"` (should be `not_home`) |
| Case mismatch | Warning | `"Armed_Away"` vs `"armed_away"` |
| Attribute doesn't exist | Warning | `state_attr('climate.hvac', 'temprature')` |
| Template syntax error | Error | `{{ is_state('sensor.temp' }}` (missing paren) |
| Service doesn't exist | Error | `light.trun_on` (typo) |
| Missing required param | Error | `light.turn_on` without `entity_id` |
| Unknown filter/test | Warning | Opt-in via strict template validation |

### Runtime Health Monitoring

When enabled, runtime monitoring analyzes automation trigger history and can report:
- **Stalled automations** - expected trigger activity has dropped to zero in the last 24h.
- **Overactive automations** - last 24h trigger rate is abnormally high versus baseline.

Practical guidance:
- Use baseline windows comfortably above 7 days (for example 21-30 days) for stable scoring.
- Keep warmup samples less than or equal to baseline days.
- Tune hour-ratio lookback days if your automations have strong weekly/monthly hour-of-day patterns.

### What Is NOT Validated

Autodoctor deliberately skips checks that generate false positives:

- **Entity references inside templates** -- Only syntax is checked; entity/state/attribute validation within `{{ }}` expressions is handled by the static analyzer, not re-validated in templates
- **Template variables** -- Blueprint inputs and trigger context are unknowable statically
- **State values for most sensors** -- Only `device_class: enum` sensors are validated (against their `options`); numeric and free-form sensors are skipped
- **State values for custom domains** -- Only well-known domains (binary_sensor, person, etc.) are validated
- **Custom Jinja2 filters/tests** -- Unless strict mode is enabled
- **Service parameter types** -- Only select/enum options are checked (YAML coercion makes type checking unreliable)

### Entity Suggestions

When an entity ID is invalid or missing, Autodoctor suggests corrections using fuzzy matching within the same domain. For example, if you type `light.livingroom`, it will suggest `light.living_room`.

### State Learning

When you dismiss an issue as a false positive, Autodoctor learns that the state is valid for that integration. For example, if you dismiss an issue about a Roborock vacuum using `segment_cleaning`, Autodoctor will remember that `segment_cleaning` is valid for all Roborock vacuums.

## Requirements

- Home Assistant 2024.1 or newer
- Recorder integration (for history analysis)

## License

MIT License - see [LICENSE](LICENSE) for details.
