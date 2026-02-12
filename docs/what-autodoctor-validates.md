# What Autodoctor Validates (and Why)

> **Philosophy:** Better to miss some issues than generate false positives that reduce trust.

Autodoctor performs **static analysis** of Home Assistant automations to catch configuration errors before they cause silent failures. However, Home Assistant is a **dynamic runtime system** where many things can't be known until execution time.

This document explains what Autodoctor validates, what it doesn't, and why.

Suppressed issues are removed from all primary user-visible surfaces (dashboard card, Repairs, and Autodoctor entities). Autodoctor still keeps suppression metadata for counts and troubleshooting.

---

## ✅ Always Validated (High Confidence)

These checks have **>95% accuracy** and rarely produce false positives:

### 1. Entity Existence
**What:** Does the referenced entity ID exist in your Home Assistant instance?

**Examples:**
```yaml
# ✅ Valid - entity exists
trigger:
  - platform: state
    entity_id: binary_sensor.front_door

# ❌ Error - entity doesn't exist
trigger:
  - platform: state
    entity_id: binary_sensor.front_dor  # typo
```

**Why it works:** Direct lookup in entity registry - deterministic.

**Suggestion:** If entity is missing, Autodoctor will suggest similar names (e.g., "Did you mean `binary_sensor.front_door`?")

---

### 2. Service Existence
**What:** Is the service registered in Home Assistant?

**Examples:**
```yaml
# ✅ Valid - service exists
action:
  - service: light.turn_on
    target:
      entity_id: light.bedroom

# ❌ Error - service doesn't exist
action:
  - service: ligt.turn_on  # typo in domain
```

**Why it works:** Direct lookup in service registry - deterministic.

---

### 3. Template Syntax Errors
**What:** Does the Jinja2 template have valid syntax?

**Examples:**
```yaml
# ✅ Valid syntax
condition:
  - condition: template
    value_template: "{{ states('sensor.temperature') | float > 20 }}"

# ❌ Error - missing closing brace
condition:
  - condition: template
    value_template: "{{ states('sensor.temperature') | float > 20 }"
```

**Why it works:** Jinja2 parser catches syntax errors objectively - no interpretation needed.

---

### 4. Device/Area/Zone References
**What:** Do device_id, area_id, zone references exist in registries?

**Examples:**
```yaml
# ✅ Valid - device exists
trigger:
  - platform: device
    device_id: abc123def456  # valid device hash

# ❌ Error - device doesn't exist
trigger:
  - platform: device
    device_id: invalid_hash
```

**Why it works:** Direct registry lookups - deterministic.

---

### 5. Required Service Parameters
**What:** Are required service parameters provided?

**Examples:**
```yaml
# ✅ Valid - brightness provided
action:
  - service: light.turn_on
    data:
      entity_id: light.bedroom
      brightness: 255

# ❌ Error - missing required target
action:
  - service: notify.mobile_app
    data:
      message: "Hello"
      # Missing 'target' which is required
```

**Why it works:** Service schema defines required fields - deterministic (skips if templates present).

---

## ⚠️ Conservatively Validated (Medium Confidence)

These checks work for **common cases** but can have false positives:

### 6. State Values (Whitelisted Domains Only)
**What:** Is the state value valid for this entity?

**Validated domains:**
- `binary_sensor.*` - on/off
- `person.*` - home/not_home/away/unknown
- `sun.sun` - above_horizon/below_horizon
- `device_tracker.*` - home/not_home/away
- `input_boolean.*` - on/off
- `group.*` - on/off

**Examples:**
```yaml
# ✅ Valid - binary_sensor can be 'on'
condition:
  - condition: state
    entity_id: binary_sensor.motion
    state: 'on'

# ❌ Warning - 'active' not valid for binary_sensor
condition:
  - condition: state
    entity_id: binary_sensor.motion
    state: 'active'  # should be 'on'
```

**Not validated:**
- `sensor.*` - arbitrary numeric/text states
- `light.*`, `switch.*` - varies by device
- Custom component entities - unknown state space

**Why conservative:** State validation works for well-known domains with stable state sets, but fails for:
- Custom integrations with arbitrary states
- Sensors that haven't reported all possible states yet
- Dynamic state values

**Config option:** Cannot be disabled (core functionality for known-safe domains).

---

### 7. Attribute Existence
**What:** Does the attribute exist on this entity?

**Severity:** WARNING (not ERROR)

**Examples:**
```yaml
# ✅ Valid - brightness is a light attribute
condition:
  - condition: state
    entity_id: light.bedroom
    attribute: brightness

# ⚠️ Warning - 'power' may not exist
condition:
  - condition: state
    entity_id: light.bedroom
    attribute: power  # depends on device
```

**Why conservative:** Attributes can be:
- State-dependent (e.g., `brightness` only when light is on)
- Capability-dependent (e.g., `color_temp` only for color lights)
- Added by integrations dynamically

**Mitigation:** Autodoctor checks:
1. Current entity state attributes
2. Common domain attributes (from `domain_attributes.py`)
3. Only reports if attribute is missing from both

---

### 8. Service Parameter Options
**What:** For select/enum parameters, is the value a valid option?

**Examples:**
```yaml
# ✅ Valid - 'heat' is valid HVAC mode
action:
  - service: climate.set_hvac_mode
    data:
      entity_id: climate.thermostat
      hvac_mode: heat

# ⚠️ Warning - 'heating' not a standard mode
action:
  - service: climate.set_hvac_mode
    data:
      entity_id: climate.thermostat
      hvac_mode: heating  # should be 'heat'
```

**Why conservative:** Only validates discrete select options (enums). Does NOT validate:
- Number ranges (too flexible)
- Boolean values (obvious)
- Text fields (arbitrary input)
- Object structures (too complex)

**Mitigation:** Autodoctor skips validation if:
- Parameter uses template (`{{ ... }}`)
- Service schema is incomplete
- Parameter is capability-dependent (e.g., `light.turn_on` color modes)

---

### 9. Removed Entities
**What:** Did this entity exist before but is now missing?

**Severity:** INFO (not ERROR)

**Why INFO:** Entity may have been:
- Intentionally removed
- Renamed (and automation not updated yet)
- A test entity that was temporary

**Purpose:** Helps distinguish typos from removed entities.

---

### 10. Runtime Health Monitoring (Opt-In, Medium Confidence)
**What:** Detects unusual automation trigger behavior from recorder history.

**Types:**
- **Stalled** - baseline indicates expected activity, but 24h trigger count is zero.
- **Overactive** - 24h trigger count is abnormally high versus baseline.

**Why medium confidence:** Runtime behavior depends on occupancy patterns, seasonality, and intentional automation changes.

**Practical guidance:**
- Use baseline windows above the 7-day cold-start window (21-30 days is a good default).
- Warmup samples must be less than or equal to baseline days.
- Hour-ratio lookback days are configurable to match weekly vs monthly behavior patterns.

---

## ❌ NOT Validated (Too Many False Positives)

These checks were **removed** or made **opt-in only** due to high false positive rates:

### 11. Template Variables (REMOVED)
**What (previously):** Are template variables defined?

**Why removed:**
- **Blueprint inputs** are injected at runtime but unknown statically
- **Trigger context** (`trigger.to_state`, `trigger.event`) is runtime-only
- **Custom globals** from other integrations are unknowable
- **False positive rate:** ~40%

**Example of false positive:**
```yaml
# Autodoctor would incorrectly flag 'door_entity' as undefined
blueprint:
  input:
    door_entity:
      name: Door Sensor
      selector:
        entity:

automation:
  use_blueprint:
    path: door_watcher.yaml
    input:
      door_entity: binary_sensor.front_door

  # This is VALID but Autodoctor can't know 'door_entity' exists
  condition:
    - condition: template
      value_template: "{{ states(door_entity) == 'on' }}"
```

**Recommendation:** Trust that blueprints and trigger context provide needed variables.

---

### 12. Unknown Jinja2 Filters/Tests (OPT-IN)
**What:** Are filters and tests in Jinja2/HA built-ins?

**Why opt-in:**
- Custom components can register their own filters
- AppDaemon, Pyscript add custom filters/tests
- No way to statically discover all available filters
- **False positive rate:** ~15%

**Example of false positive:**
```yaml
# Custom component provides 'my_custom_filter'
# Autodoctor would incorrectly flag it as unknown
condition:
  - condition: template
    value_template: "{{ 'test' | my_custom_filter }}"
```

**Config option:**
```yaml
# In integration options
strict_template_validation: true  # Default: false
```

**When to enable:** Only if you **don't use** custom Jinja2 filters/tests.

---

### 12. Basic Service Parameter Types (REMOVED)
**What (previously):** Does parameter type match schema?

**Why removed:**
- YAML type coercion is complex
- Service schemas are hints, not strict contracts
- Some services accept flexible types (single value OR list)
- **False positive rate:** ~8%

**Example of false positive:**
```yaml
# HA accepts both number and string for brightness
action:
  - service: light.turn_on
    data:
      entity_id: light.bedroom
      brightness: "255"  # String is fine, HA converts it
```

**What IS still validated:**
- Select/enum options (discrete choices are high confidence)
- Required parameters (can't be omitted)

---

### 13. Arbitrary State Values (SKIPPED)
**What:** State values for sensors, custom domains

**Why skipped:**
- Sensors can have arbitrary numeric or text states
- Custom integrations define their own state space
- Dynamic states that haven't been observed yet

**Example:**
```yaml
# NOT validated (sensor states are arbitrary)
condition:
  - condition: state
    entity_id: sensor.temperature
    state: '72.5'  # Could be any number

# NOT validated (custom component)
condition:
  - condition: state
    entity_id: custom_component.my_device
    state: 'custom_state'  # Unknown state space
```

**Recommendation:** For custom sensors, rely on runtime behavior or integration documentation.

---

## Configuration Options

Control validation strictness in Autodoctor integration options:

### Option 1: Strict Template Validation
**Default:** OFF
**What it does:** Warns about unknown Jinja2 filters and tests

**Enable if:**
- You don't use custom components with custom filters
- You don't use AppDaemon or Pyscript
- You want maximum validation coverage

**Disable if:**
- You have custom Jinja2 filters/tests
- You're getting false positive warnings

---

### Option 2: Strict Service Validation
**Default:** OFF (future option)
**What it does:** Warns about unknown service parameters

**Enable if:**
- You want to catch typos in service parameters
- You're confident your service schemas are complete

**Disable if:**
- You're getting warnings about valid parameters
- You use services with flexible schemas

---

## FAQ

### Why doesn't Autodoctor validate X?
**Answer:** If validation has >5% false positive rate, we don't do it. False positives reduce trust and create noise.

### Can I enable stricter validation?
**Answer:** Yes, use "Strict template validation" in config options. But expect some false positives if you use custom components.

### How do I report a false positive?
**Answer:** Create a GitHub issue with:
1. The automation YAML
2. The false positive warning
3. Why it's actually valid
4. Your Home Assistant version and custom components

### How do I report a missed issue?
**Answer:** Same as above - we want to know! We'll consider adding validation if we can achieve >95% accuracy.

### What if I disagree with a warning?
**Answer:** Use the "Suppress" button in the UI. The warning will be hidden for this automation. You can also "Learn" a state to add it to your knowledge base.

---

## Design Philosophy

> **Static analysis of dynamic systems is inherently limited.**

Autodoctor's design philosophy:
1. **High precision over high recall** - Better to miss issues than cry wolf
2. **Trust but verify** - Trust HA's runtime, catch obvious mistakes
3. **User control** - Config options for strictness preferences
4. **Clear scope** - Document what we do/don't validate

By focusing on high-confidence validations, Autodoctor provides value without overwhelming users with false positives.

---

## Evolution

This validation scope was refined in **v2.7.0** after observing false positive patterns:

| Version | Change | Reason |
|---------|--------|--------|
| v2.6.2 | Fixed undefined variable FPs | Blueprint false positives |
| v2.6.1 | Fixed blueprint automation FPs | Blueprint inputs not recognized |
| v2.4.0 | Fixed Jinja2 break/continue FPs | Control flow not tracked |
| v2.7.0 | Removed undefined variable check | Fundamentally unsound for static analysis |
| v2.7.0 | Made filter/test checking opt-in | Custom filters/tests exist |
| v2.7.0 | Whitelisted state validation domains | Custom domains have unknown states |

**Next:** Mutation testing to verify validation effectiveness once scope is stable.

---

## Contributing

If you have ideas for:
- **High-confidence validations** we're missing (>95% accuracy)
- **False positive scenarios** we should handle better
- **Domain patterns** that could be whitelisted

Please open a GitHub issue or submit a PR!

---

## See Also

- [Validation Scope Audit](validation-scope-audit.md) - Technical details
- [Implementation Checklist](validation-narrowing-checklist.md) - Code changes needed
- [Home Assistant Template Documentation](https://www.home-assistant.io/docs/configuration/templating/)
