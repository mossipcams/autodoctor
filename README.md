# Autodoctor

[![GitHub Release](https://img.shields.io/github/v/release/mossipcams/autodoctor?style=flat-square)](https://github.com/mossipcams/autodoctor/releases)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

A Home Assistant custom integration that validates your automations and monitors their runtime health to detect issues before they cause silent failures.

## The Problem

You create an automation, it looks correct, but it never fires. No errors in the logs. Everything seems fine, but nothing happens.

Hours later you discover:
- You wrote `away` but the person entity uses `not_home`
- You typed `Armed_Away` but it's actually `armed_away`
- You have a typo: `binary_sensor.motion_sensor`
- A template has a syntax error: `{{ is_state('sensor.temp' }}`
- An automation that runs once a day suddenly fires 50 times in an hour

**Autodoctor catches these issues before they waste your time.**

## Features

- **Static Validation** -- Checks automation configs against known valid states, entity existence, and attribute values
- **Jinja Template Validation** -- Catches syntax errors in templates before they fail silently
- **Service Call Validation** -- Validates service calls against the HA service registry (existence, required params, select options)
- **Entity Suggestions** -- Suggests fixes for entity ID typos using fuzzy matching
- **One-Click Fixes** -- Preview and apply suggested fixes directly from the dashboard card
- **State Learning** -- Learns valid states when you dismiss false positives
- **Issue Suppression** -- Dismiss false positives globally (card, Repairs, sensors) with full management UI
- **Runtime Health Monitoring** -- Detects overactive and burst anomalies in automation trigger patterns using Bayesian changepoint detection
- **Validation Pipeline UI** -- Animated step-by-step validation progress in the dashboard card
- **Periodic Scanning** -- Configurable background re-validation interval

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

The card includes:
- Severity indicators (error/warning/info)
- Animated validation pipeline showing per-group progress
- Direct links to edit the automation (YAML and UI automations)
- Entity ID fix suggestions with one-click apply and undo
- Dismiss buttons (dismissing also teaches Autodoctor valid states)
- Suppression management view (list, unsuppress)

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
- **Dashboard Card** -- Custom Lovelace card with full issue details and fix actions
- **Repairs** -- Settings → Repairs shows actionable issues with edit links
- **Sensors** -- Issue count sensor and binary problem sensor for use in automations
- **Log warnings/errors** -- For monitoring and debugging

Suppressed issues are removed from all primary issue surfaces (dashboard card, Repairs, and Autodoctor entities). Suppression metadata is still retained for counts/history.

## Configuration Options

Access via Settings → Devices & Services → Autodoctor → Configure

### General

| Option | Default | Description |
|--------|---------|-------------|
| History lookback (days) | 30 | Days of state history to analyze for the knowledge base |
| Validate on reload | Yes | Auto-validate when automations reload |
| Debounce delay (seconds) | 5 | Wait before validating after reload |
| Periodic scan interval (hours) | 4 | Background re-validation interval |
| Strict template validation | No | Warn about unknown Jinja2 filters/tests (disable if using custom components) |
| Strict service validation | No | Warn about unknown service parameters |

### Runtime Health Monitoring

| Option | Default | Description |
|--------|---------|-------------|
| Enable runtime health monitoring | No | Turn on trigger-behavior anomaly detection |
| Baseline history (days) | 30 | Recorder history window for building behavior baselines |
| Warmup samples | 3 | Minimum active baseline days before scoring starts |
| Min expected events/day | 0 | Minimum daily trigger count needed before scoring starts |
| Hour ratio lookback (days) | 30 | Days of same-hour history used for time-of-day context scoring |
| Sensitivity | medium | Overall sensitivity (low/medium/high) |
| Burst multiplier | 4.0 | Short-window trigger rate multiplier for burst detection |
| Max alerts/day | 10 | Per-automation alert cap to limit noise |
| Smoothing window | 5 | Moving average window for score smoothing |
| Restart exclusion (minutes) | 5 | Ignore triggers within N minutes of HA restart |
| Auto-adapt baselines | Yes | Automatically adjust baselines as patterns change |

Runtime baseline must be larger than the internal cold-start window (7 days) so training data can be generated.

## How It Works

### State Knowledge Base

Autodoctor builds a knowledge base of valid states from multiple sources:

1. **Device class defaults** -- Known states for 30+ domains (e.g., `person` → `home`, `not_home`)
2. **Enum sensor options** -- Validates `device_class: enum` sensors against their declared `options` attribute
3. **Schema introspection** -- Reads `hvac_modes`, `options`, `effect_list` from entity attributes
4. **Recorder history** -- Learns actual states from your historical data
5. **User feedback** -- Remembers states you mark as valid when dismissing issues

### What Gets Validated

- State triggers (`to`, `from` values) -- conservative: only whitelisted domains
- Numeric state triggers (entity and attribute existence)
- State conditions
- Template syntax (Jinja2 parse errors, unknown filters/tests with strict mode)
- Service calls (existence, required params, select option validation)
- Entity references in triggers, conditions, and actions
- Device, area, and tag registry references

### Validation Rules

| Check | Severity | Example |
|-------|----------|---------|
| Entity doesn't exist | Error | `binary_sensor.motoin_sensor` (typo) |
| Entity removed | Info | Entity was renamed or deleted |
| State never valid | Error | `person.matt` → `"away"` (should be `not_home`) |
| Case mismatch | Warning | `"Armed_Away"` vs `"armed_away"` |
| Attribute doesn't exist | Warning | `state_attr('climate.hvac', 'temprature')` |
| Invalid attribute value | Warning | `fan_mode: "turbo"` not in known modes |
| Template syntax error | Error | `{{ is_state('sensor.temp' }}` (missing paren) |
| Service doesn't exist | Error | `light.trun_on` (typo) |
| Missing required param | Error | `light.turn_on` without `entity_id` |
| Invalid select option | Warning | Service param value not in allowed options |
| Unknown filter/test | Warning | Opt-in via strict template validation |
| Device/area/tag not found | Error | Registry ID doesn't exist |

### Runtime Health Monitoring

When enabled, Autodoctor monitors automation trigger patterns in real time and detects behavioral anomalies using **Bayesian Online Changepoint Detection (BOCPD)** with a Gamma-Poisson conjugate model. Models are seeded from recorder history on first enable and persisted across restarts.

Runtime monitoring detects two types of anomalies:

| Issue | Description |
|-------|-------------|
| **Overactive** | Daily trigger count is statistically unusual versus the BOCPD-estimated baseline |
| **Burst** | Short-window trigger spike exceeding the burst multiplier |

Key behaviors:
- **Time-bucket awareness** -- Models are segmented by weekday/weekend and morning/afternoon/evening/night to account for natural schedule variation
- **Recorder bootstrap** -- On first enable, bulk-imports trigger history from the recorder into SQLite so detection starts immediately rather than waiting for a full baseline window
- **Restart exclusion** -- Ignores triggers shortly after HA restarts to avoid false positives from startup activity
- **Alert caps** -- Per-automation and global daily alert limits prevent alert fatigue
- **Auto-adapt** -- Baselines automatically adjust as automation patterns evolve
- **State persistence** -- Trigger events are stored in a local SQLite database; BOCPD models are rebuilt from this store on startup

Practical guidance:
- Use baseline windows of 21–30 days for stable scoring
- Keep warmup samples less than or equal to baseline days
- Start with the default "medium" sensitivity and adjust from there
- Tune the burst multiplier if you have automations with legitimate traffic spikes
- Hour ratio lookback should match or exceed the baseline window for best results

### What Is NOT Validated

Autodoctor deliberately skips checks that generate false positives:

- **Entity references inside templates** -- Only syntax is checked; entity/state/attribute validation within `{{ }}` expressions is handled by the static analyzer, not re-validated in templates
- **Template variables** -- Blueprint inputs and trigger context are unknowable statically
- **State values for most sensors** -- Only `device_class: enum` sensors are validated (against their `options`); numeric and free-form sensors are skipped
- **State values for custom domains** -- Only well-known domains (binary_sensor, person, etc.) are validated
- **Custom Jinja2 filters/tests** -- Unless strict mode is enabled
- **Service parameter types** -- Only select/enum options are checked (YAML coercion makes type checking unreliable)

### Entity Suggestions and One-Click Fixes

When an entity ID is invalid or missing, Autodoctor suggests corrections using fuzzy matching within the same domain. For example, if you type `light.livingroom`, it will suggest `light.living_room`.

From the dashboard card, you can preview a suggested fix, apply it directly to your automation config, and undo if needed -- all without leaving the dashboard.

### State Learning

When you dismiss an issue as a false positive, Autodoctor learns that the state is valid for that integration. For example, if you dismiss an issue about a Roborock vacuum using `segment_cleaning`, Autodoctor will remember that `segment_cleaning` is valid for all Roborock vacuums.

## Requirements

- Home Assistant 2024.1 or newer
- Recorder integration (for history analysis and runtime health)

## License

MIT License - see [LICENSE](LICENSE) for details.
