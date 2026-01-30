# Comprehensive Trigger/Condition Coverage and Jinja2 Semantic Validation

**Date:** 2026-01-29
**Status:** Design
**Version:** 1.0

## Overview

This design enhances autodoctor's validation coverage across three dimensions:

1. **Trigger Type Coverage** - Expand from 3 to 17 supported trigger types
2. **Condition Type Coverage** - Expand from 3 to 10 supported condition types
3. **Jinja2 Semantic Validation** - Add HA-specific entity/state/attribute validation

**Current limitations:**
- Only validates 3/17 trigger types (state, template, numeric_state)
- Only validates 3/10 condition types (state, template, and/or/not)
- Jinja2 validation is syntax-only (no entity existence, state validity, or attribute checks)

**Impact:**
- Many automation issues go undetected (zone triggers, calendar triggers, numeric conditions, etc.)
- Templates can reference non-existent entities without warnings
- State values in templates aren't validated against knowledge base

---

## Architecture Principles

### Two-Tier Validation System

**Tier 1: Entity/Resource Existence** (actionable validation)
- Entity existence (entity_id references)
- Zone/device/area existence (registry lookups)
- Attribute existence (entity capability checks)
- State value validity (knowledge base checks)

**Tier 2: Reference Extraction Only** (coverage tracking)
- Extract references for completeness
- Don't validate external systems (MQTT topics, event types, webhook IDs)
- Don't validate arbitrary strings (integration-specific trigger types)

### Code Reuse Strategy

**Pattern extraction:** Reuse existing regex patterns from `analyzer.py`

**Validation logic:** Reuse existing validation from `validator.py`

**Knowledge base:** Leverage existing state/attribute knowledge

---

## Part 1: Trigger Type Coverage

### Current State

**Covered (3 types):**
1. ✅ **state** - Validates entity_id, to/from states
2. ✅ **template** - Parses value_template for references
3. ⚠️ **numeric_state** - Extracts entity_id but doesn't validate attributes

**Not Covered (14 types):**
- zone, sun, calendar, device, tag, geolocation, event, mqtt, webhook, persistent_notification, time, time_pattern, homeassistant, sentence

### Proposed Coverage by Category

#### Category A: Entity-Based Triggers

**1. Zone Triggers** (`trigger: zone`)

```yaml
trigger: zone
entity_id: device_tracker.paulus
zone: zone.home
event: enter  # or leave
```

**Validation:**
- Entity exists (device_tracker/person domain)
- Zone exists (zone.*)
- Extract both as StateReferences

**Implementation:**
```python
def _extract_from_trigger(self, trigger, index, auto_id, auto_name):
    # ... existing code

    elif platform == "zone":
        entity_ids = self._normalize_entity_ids(trigger.get("entity_id"))
        zone_id = trigger.get("zone")

        for entity_id in entity_ids:
            refs.append(StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=None,
                location=f"trigger[{index}].entity_id",
                reference_type="direct"
            ))

        if zone_id:
            refs.append(StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=zone_id,
                expected_state=None,
                expected_attribute=None,
                location=f"trigger[{index}].zone",
                reference_type="zone"
            ))
```

**2. Sun Triggers** (`trigger: sun`)

```yaml
trigger: sun
event: sunset  # or sunrise
offset: "-01:00:00"
```

**Validation:**
- Implicit reference to `sun.sun` entity
- Extract sun.sun as StateReference
- Don't validate event/offset (known values)

**Implementation:**
```python
elif platform == "sun":
    refs.append(StateReference(
        automation_id=auto_id,
        automation_name=auto_name,
        entity_id="sun.sun",
        expected_state=None,
        expected_attribute=None,
        location=f"trigger[{index}]",
        reference_type="direct"
    ))
```

**3. Calendar Triggers** (`trigger: calendar`)

```yaml
trigger: calendar
event: start  # or end
entity_id: calendar.events
offset: "-00:05:00"
```

**Validation:**
- Entity exists (calendar.* domain)
- Extract as StateReference

**Implementation:**
```python
elif platform == "calendar":
    entity_ids = self._normalize_entity_ids(trigger.get("entity_id"))

    for entity_id in entity_ids:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=entity_id,
            expected_state=None,
            expected_attribute=None,
            location=f"trigger[{index}].entity_id",
            reference_type="direct"
        ))
```

#### Category B: Resource-Based Triggers

**4. Device Triggers** (`trigger: device`)

```yaml
trigger: device
device_id: abc123
domain: mqtt
type: button_short_press
subtype: button_1
```

**Validation:**
- Device exists in device registry
- Extract device_id as reference (type: "device")
- Don't validate type/subtype (integration-specific)

**Implementation:**
```python
elif platform == "device":
    device_id = trigger.get("device_id")

    if device_id:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=device_id,
            expected_state=None,
            expected_attribute=None,
            location=f"trigger[{index}].device_id",
            reference_type="device"
        ))
```

**5. Tag Triggers** (`trigger: tag`)

```yaml
trigger: tag
tag_id: AABBCCDD
device_id: scanner_device_id  # optional
```

**Validation:**
- Device exists if device_id specified
- Extract tag_id as reference (type: "tag")
- Don't validate tag_id (not in registry)

**Implementation:**
```python
elif platform == "tag":
    tag_id = trigger.get("tag_id")
    device_id = trigger.get("device_id")

    if tag_id:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=tag_id,
            expected_state=None,
            expected_attribute=None,
            location=f"trigger[{index}].tag_id",
            reference_type="tag"
        ))

    if device_id:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=device_id,
            expected_state=None,
            expected_attribute=None,
            location=f"trigger[{index}].device_id",
            reference_type="device"
        ))
```

**6. Geolocation Triggers** (`trigger: geo_location`)

```yaml
trigger: geo_location
source: nsw_rural_fire_service_feed
zone: zone.home
event: enter  # or leave
```

**Validation:**
- Zone exists
- Extract zone as reference
- Don't validate source (external platform name)

**Implementation:**
```python
elif platform == "geo_location":
    zone_id = trigger.get("zone")

    if zone_id:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=zone_id,
            expected_state=None,
            expected_attribute=None,
            location=f"trigger[{index}].zone",
            reference_type="zone"
        ))
```

#### Category C: Non-Entity Triggers (Template Extraction Only)

**7. Event Triggers** (`trigger: event`)

```yaml
trigger: event
event_type: my_custom_event
event_data:
  entity: "{{ states('input_text.target') }}"
```

**Validation:**
- Extract templates from event_data values
- Don't validate event_type (unlimited possibilities)

**Implementation:**
```python
elif platform == "event":
    event_data = trigger.get("event_data", {})

    if isinstance(event_data, dict):
        for key, value in event_data.items():
            if isinstance(value, str):
                refs.extend(
                    self._extract_from_template(
                        value,
                        f"trigger[{index}].event_data.{key}",
                        auto_id,
                        auto_name
                    )
                )
```

**8. MQTT Triggers** (`trigger: mqtt`)

```yaml
trigger: mqtt
topic: "home/{{ states('input_text.room') }}/light"
payload: "ON"
```

**Validation:**
- Extract templates from topic/payload
- Don't validate topic (external MQTT broker)

**Implementation:**
```python
elif platform == "mqtt":
    topic = trigger.get("topic", "")
    payload = trigger.get("payload", "")

    if isinstance(topic, str):
        refs.extend(
            self._extract_from_template(
                topic,
                f"trigger[{index}].topic",
                auto_id,
                auto_name
            )
        )

    if isinstance(payload, str):
        refs.extend(
            self._extract_from_template(
                payload,
                f"trigger[{index}].payload",
                auto_id,
                auto_name
            )
        )
```

**9. Webhook Triggers** (`trigger: webhook`)

```yaml
trigger: webhook
webhook_id: my_webhook_123
allowed_methods:
  - POST
  - PUT
local_only: false
```

**Validation:**
- No entity references
- Extract templates from webhook_id if present

**Implementation:**
```python
elif platform == "webhook":
    webhook_id = trigger.get("webhook_id", "")

    if isinstance(webhook_id, str):
        refs.extend(
            self._extract_from_template(
                webhook_id,
                f"trigger[{index}].webhook_id",
                auto_id,
                auto_name
            )
        )
```

**10. Persistent Notification Triggers** (`trigger: persistent_notification`)

```yaml
trigger: persistent_notification
notification_id: "alert_{{ states('input_text.alert_name') }}"
update_type: added  # or removed, current
```

**Validation:**
- Extract templates from notification_id

**Implementation:**
```python
elif platform == "persistent_notification":
    notification_id = trigger.get("notification_id", "")

    if isinstance(notification_id, str):
        refs.extend(
            self._extract_from_template(
                notification_id,
                f"trigger[{index}].notification_id",
                auto_id,
                auto_name
            )
        )
```

#### Category D: Time-Based Triggers

**11. Time Triggers** (`trigger: time`)

```yaml
trigger: time
at:
  - input_datetime.wake_up_time
  - "07:30:00"
  - sensor.sunset_time
```

**Validation:**
- Validate entity references (input_datetime/sensor)
- Don't validate time strings

**Implementation:**
```python
elif platform == "time":
    at_values = trigger.get("at")
    if not isinstance(at_values, list):
        at_values = [at_values] if at_values else []

    for at_value in at_values:
        # If it looks like an entity_id (contains a dot), validate it
        if isinstance(at_value, str) and "." in at_value and not ":" in at_value:
            refs.append(StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=at_value,
                expected_state=None,
                expected_attribute=None,
                location=f"trigger[{index}].at",
                reference_type="direct"
            ))
```

**12. Time Pattern Triggers** (`trigger: time_pattern`)

```yaml
trigger: time_pattern
hours: "/2"
minutes: "5"
seconds: "0"
```

**Validation:**
- No entity references
- No validation needed

**Implementation:**
- Skip (no extraction needed)

**13. Homeassistant Triggers** (`trigger: homeassistant`)

```yaml
trigger: homeassistant
event: start  # or shutdown
```

**Validation:**
- No entity references
- No validation needed

**Implementation:**
- Skip (no extraction needed)

**14. Sentence Triggers** (`trigger: sentence`)

```yaml
trigger: sentence
sentence: "turn on the lights"
```

**Validation:**
- No entity references
- Don't validate sentence patterns

**Implementation:**
- Skip (no extraction needed)

---

## Part 2: Condition Type Coverage

### Current State

**Covered (3 types):**
1. ✅ **state** - Validates entity_id and state values
2. ✅ **template** - Parses value_template for references
3. ✅ **and/or/not** - Already recursive

**Not Covered (4 types):**
- numeric_state, zone, sun, time

**Note:** trigger and device conditions have limited validation scope

### Proposed Coverage

#### Category A: Entity-Based Conditions

**1. Numeric State Conditions** (`condition: numeric_state`)

```yaml
condition: numeric_state
entity_id: sensor.temperature
attribute: temperature  # optional
above: 20
below: 30
value_template: "{{ state.attributes.temperature }}"  # optional
```

**Validation:**
- Entity exists
- Attribute exists (if specified)
- Extract entity_id and attribute as StateReferences
- Don't validate above/below (could be templated)

**Implementation:**
```python
def _extract_from_condition(self, condition, index, auto_id, auto_name, location_prefix="condition"):
    # ... existing code

    elif cond_type == "numeric_state":
        entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
        attribute = condition.get("attribute")
        value_template = condition.get("value_template")

        for entity_id in entity_ids:
            refs.append(StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=attribute,
                location=f"{location_prefix}[{index}]",
                reference_type="direct"
            ))

        # Extract from value_template if present
        if value_template and isinstance(value_template, str):
            refs.extend(
                self._extract_from_template(
                    value_template,
                    f"{location_prefix}[{index}].value_template",
                    auto_id,
                    auto_name
                )
            )
```

**2. Zone Conditions** (`condition: zone`)

```yaml
condition: zone
entity_id: device_tracker.paulus
zone: zone.home
```

**Validation:**
- Entity exists (device_tracker/person)
- Zone exists
- Extract both as StateReferences

**Implementation:**
```python
elif cond_type == "zone":
    entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
    zone_id = condition.get("zone")

    for entity_id in entity_ids:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=entity_id,
            expected_state=None,
            expected_attribute=None,
            location=f"{location_prefix}[{index}].entity_id",
            reference_type="direct"
        ))

    if zone_id:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=zone_id,
            expected_state=None,
            expected_attribute=None,
            location=f"{location_prefix}[{index}].zone",
            reference_type="zone"
        ))
```

**3. Sun Conditions** (`condition: sun`)

```yaml
condition: sun
after: sunset
after_offset: "-01:00:00"
before: sunrise
before_offset: "01:00:00"
```

**Validation:**
- Implicit reference to sun.sun entity
- Extract sun.sun as StateReference
- Don't validate offset values

**Implementation:**
```python
elif cond_type == "sun":
    refs.append(StateReference(
        automation_id=auto_id,
        automation_name=auto_name,
        entity_id="sun.sun",
        expected_state=None,
        expected_attribute=None,
        location=f"{location_prefix}[{index}]",
        reference_type="direct"
    ))
```

#### Category B: Time-Based Conditions

**4. Time Conditions** (`condition: time`)

```yaml
condition: time
after: input_datetime.wake_up
before: "22:00:00"
weekday:
  - mon
  - tue
  - wed
```

**Validation:**
- Validate entity references in after/before (input_datetime/sensor)
- Don't validate time strings or weekdays

**Implementation:**
```python
elif cond_type == "time":
    for key in ["after", "before"]:
        value = condition.get(key)
        # If it looks like an entity_id, validate it
        if isinstance(value, str) and "." in value and ":" not in value:
            refs.append(StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=value,
                expected_state=None,
                expected_attribute=None,
                location=f"{location_prefix}[{index}].{key}",
                reference_type="direct"
            ))
```

#### Category C: Meta Conditions (No Validation)

**5. Trigger Conditions** (`condition: trigger`)

```yaml
condition: trigger
id:
  - trigger_1
  - trigger_2
```

**Validation:**
- No entity references
- Don't validate trigger IDs (internal to automation)

**Implementation:**
- Skip (no extraction needed)

#### Category D: Integration-Specific Conditions

**6. Device Conditions** (`condition: device`)

```yaml
condition: device
device_id: abc123
domain: light
type: is_on
```

**Validation:**
- Device exists in device registry
- Extract device_id as reference
- Don't validate type (integration-specific)

**Implementation:**
```python
elif cond_type == "device":
    device_id = condition.get("device_id")

    if device_id:
        refs.append(StateReference(
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=device_id,
            expected_state=None,
            expected_attribute=None,
            location=f"{location_prefix}[{index}].device_id",
            reference_type="device"
        ))
```

### Enhancement: Numeric State Trigger Attribute Validation

**Current behavior:**
- Extracts entity_id from numeric_state triggers
- Does NOT validate attribute existence

**Enhancement:**
```python
elif platform == "numeric_state":
    entity_ids = trigger.get("entity_id") or []
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]

    attribute = trigger.get("attribute")

    for entity_id in entity_ids:
        refs.append(
            StateReference(
                automation_id=automation_id,
                automation_name=automation_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=attribute,  # Now validates this
                location=f"trigger[{index}]",
            )
        )
```

---

## Part 3: Jinja2 HA-Specific Semantic Validation

### Current State

**jinja_validator.py current validation:**
- ✅ Syntax errors (TemplateSyntaxError)
- ✅ Unknown filters (not in built-in or HA filter list)
- ✅ Unknown tests (not in built-in or HA test list)

**Missing:**
- ❌ Entity existence checks in templates
- ❌ State value validation in is_state() calls
- ❌ Attribute existence checks in state_attr/is_state_attr

### Architecture Enhancement

**Current flow:**
```
Template → Parse AST → Check syntax → Check filters/tests → Done
```

**Enhanced flow:**
```
Template → Parse AST → Check syntax → Check filters/tests
         → Extract entity references (reuse analyzer patterns)
         → Validate references (reuse validator logic)
         → Return all issues
```

### Semantic Validations to Add

#### 1. Entity Existence in Templates

**Patterns to validate:**
```python
# All these should validate entity exists:
states.domain.entity           # → entity exists?
states('entity_id')            # → entity exists?
is_state('entity_id', 'on')    # → entity exists?
is_state_attr('entity_id', ...) # → entity exists?
state_attr('entity_id', ...)   # → entity exists?
expand('entity_id')            # → entity/group exists?
device_entities('device_id')   # → device exists?
area_entities('area_id')       # → area exists?
```

**Example validation:**
```yaml
condition: template
value_template: "{{ states.light.nonexistent.state == 'on' }}"
```

**Issue generated:**
```
IssueType: TEMPLATE_ENTITY_NOT_FOUND
Severity: ERROR
Message: Entity 'light.nonexistent' referenced in template does not exist
Location: condition[0].value_template
```

#### 2. State Value Validation in is_state()

**Pattern:**
```python
is_state('entity_id', 'state_value')
```

**Validation:**
1. Entity exists ✓
2. State value is valid for entity's domain/device class ✓

**Example validation:**
```yaml
condition: template
value_template: "{{ is_state('light.kitchen', 'invalid_state') }}"
```

**Issue generated:**
```
IssueType: TEMPLATE_INVALID_STATE
Severity: ERROR
Message: State 'invalid_state' is not valid for light.kitchen
Suggestion: Valid states: on, off, unavailable, unknown
Location: condition[0].value_template
```

#### 3. Attribute Existence in state_attr/is_state_attr

**Patterns:**
```python
state_attr('entity_id', 'attribute')
is_state_attr('entity_id', 'attribute', 'value')
```

**Validation:**
1. Entity exists ✓
2. Attribute exists on entity ✓
3. (For is_state_attr) Value is valid for attribute ✓

**Example validation:**
```yaml
condition: template
value_template: "{{ state_attr('climate.living_room', 'nonexistent_attr') }}"
```

**Issue generated:**
```
IssueType: TEMPLATE_ATTRIBUTE_NOT_FOUND
Severity: ERROR
Message: Attribute 'nonexistent_attr' not found on climate.living_room
Suggestion: Available attributes: temperature, hvac_mode, fan_mode, preset_mode
Location: condition[0].value_template
```

### Implementation Strategy

#### Step 1: Add Entity Reference Extraction to JinjaValidator

**New method in jinja_validator.py:**
```python
def _extract_entity_references(
    self,
    template: str,
    location: str,
    auto_id: str,
    auto_name: str
) -> list[StateReference]:
    """Extract entity references from template using analyzer patterns.

    Reuses regex patterns from AutomationAnalyzer._extract_from_template()
    to find all entity references in the template.
    """
    # Import analyzer patterns (avoid circular import)
    from .analyzer import (
        IS_STATE_PATTERN,
        IS_STATE_ATTR_PATTERN,
        STATE_ATTR_PATTERN,
        STATES_OBJECT_PATTERN,
        STATES_FUNCTION_PATTERN,
        EXPAND_PATTERN,
        AREA_ENTITIES_PATTERN,
        DEVICE_ENTITIES_PATTERN,
        INTEGRATION_ENTITIES_PATTERN,
        JINJA_COMMENT_PATTERN,
    )

    refs: list[StateReference] = []

    # Strip Jinja2 comments before parsing
    template = JINJA_COMMENT_PATTERN.sub("", template)

    # Extract is_state() calls - captures entity_id AND state value
    for match in IS_STATE_PATTERN.finditer(template):
        entity_id, state = match.groups()
        refs.append(
            StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=entity_id,
                expected_state=state,  # Capture state for validation
                expected_attribute=None,
                location=f"{location}.is_state",
            )
        )

    # Extract is_state_attr() calls - captures entity_id, attribute, AND value
    for match in IS_STATE_ATTR_PATTERN.finditer(template):
        entity_id, attribute, value = match.groups()
        refs.append(
            StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=attribute,  # Capture for validation
                location=f"{location}.is_state_attr",
            )
        )
        # TODO: Store attribute value for validation

    # Extract state_attr() calls
    for match in STATE_ATTR_PATTERN.finditer(template):
        entity_id, attribute = match.groups()
        refs.append(
            StateReference(
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=entity_id,
                expected_state=None,
                expected_attribute=attribute,
                location=f"{location}.state_attr",
            )
        )

    # Extract states.domain.entity references
    for match in STATES_OBJECT_PATTERN.finditer(template):
        domain, entity_name = match.groups()
        entity_id = f"{domain}.{entity_name}"
        if not any(r.entity_id == entity_id for r in refs):
            refs.append(
                StateReference(
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=None,
                    location=f"{location}.states_object",
                )
            )

    # Extract states('entity_id') function calls
    for match in STATES_FUNCTION_PATTERN.finditer(template):
        entity_id = match.group(1)
        if not any(r.entity_id == entity_id for r in refs):
            refs.append(
                StateReference(
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id=entity_id,
                    expected_state=None,
                    expected_attribute=None,
                    location=f"{location}.states_function",
                )
            )

    # Extract expand(), area_entities(), device_entities(), integration_entities()
    # (same logic as analyzer.py)

    return refs
```

#### Step 2: Add Semantic Validation Method

**New method in jinja_validator.py:**
```python
def _validate_entity_references(
    self,
    refs: list[StateReference]
) -> list[ValidationIssue]:
    """Validate entity references using knowledge base.

    Checks:
    - Entity existence
    - State value validity (for is_state calls)
    - Attribute existence (for state_attr/is_state_attr calls)

    Args:
        refs: List of StateReferences extracted from templates

    Returns:
        List of ValidationIssues found
    """
    if not self.hass:
        return []  # Can't validate without hass instance

    issues: list[ValidationIssue] = []

    for ref in refs:
        # 1. Check entity existence
        state = self.hass.states.get(ref.entity_id)

        # Handle special reference types
        if ref.reference_type == "zone":
            if not state:
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.TEMPLATE_ZONE_NOT_FOUND,
                        severity=Severity.ERROR,
                        automation_id=ref.automation_id,
                        automation_name=ref.automation_name,
                        entity_id=ref.entity_id,
                        location=ref.location,
                        message=f"Zone '{ref.entity_id}' referenced in template does not exist",
                    )
                )
            continue

        elif ref.reference_type == "device":
            # Check device registry
            from homeassistant.helpers import device_registry as dr
            device_reg = dr.async_get(self.hass)
            if not device_reg.async_get(ref.entity_id):
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.TEMPLATE_DEVICE_NOT_FOUND,
                        severity=Severity.ERROR,
                        automation_id=ref.automation_id,
                        automation_name=ref.automation_name,
                        entity_id=ref.entity_id,
                        location=ref.location,
                        message=f"Device '{ref.entity_id}' referenced in template does not exist",
                    )
                )
            continue

        elif ref.reference_type == "area":
            # Check area registry
            from homeassistant.helpers import area_registry as ar
            area_reg = ar.async_get(self.hass)
            if not area_reg.async_get_area(ref.entity_id):
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.TEMPLATE_AREA_NOT_FOUND,
                        severity=Severity.ERROR,
                        automation_id=ref.automation_id,
                        automation_name=ref.automation_name,
                        entity_id=ref.entity_id,
                        location=ref.location,
                        message=f"Area '{ref.entity_id}' referenced in template does not exist",
                    )
                )
            continue

        # Standard entity validation
        if not state:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_ENTITY_NOT_FOUND,
                    severity=Severity.ERROR,
                    automation_id=ref.automation_id,
                    automation_name=ref.automation_name,
                    entity_id=ref.entity_id,
                    location=ref.location,
                    message=f"Entity '{ref.entity_id}' referenced in template does not exist",
                )
            )
            continue

        # 2. Validate attribute existence if specified
        if ref.expected_attribute:
            if ref.expected_attribute not in state.attributes:
                issues.append(
                    ValidationIssue(
                        issue_type=IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND,
                        severity=Severity.ERROR,
                        automation_id=ref.automation_id,
                        automation_name=ref.automation_name,
                        entity_id=ref.entity_id,
                        location=ref.location,
                        message=f"Attribute '{ref.expected_attribute}' not found on {ref.entity_id}",
                        suggestion=f"Available attributes: {', '.join(sorted(state.attributes.keys())[:10])}",
                    )
                )

        # 3. Validate state value if specified (from is_state calls)
        if ref.expected_state:
            # Use validator to check if state is valid
            from .validator import AutodoctorValidator
            from .knowledge_base import KnowledgeBase

            kb = KnowledgeBase(self.hass)
            valid_states = kb.get_valid_states(ref.entity_id)

            if valid_states and ref.expected_state not in valid_states:
                # Check for case mismatch
                if ref.expected_state.lower() in {s.lower() for s in valid_states}:
                    severity = Severity.WARNING
                    issue_type = IssueType.CASE_MISMATCH
                else:
                    severity = Severity.ERROR
                    issue_type = IssueType.TEMPLATE_INVALID_STATE

                issues.append(
                    ValidationIssue(
                        issue_type=issue_type,
                        severity=severity,
                        automation_id=ref.automation_id,
                        automation_name=ref.automation_name,
                        entity_id=ref.entity_id,
                        location=ref.location,
                        message=f"State '{ref.expected_state}' is not valid for {ref.entity_id}",
                        suggestion=f"Valid states: {', '.join(sorted(valid_states)[:10])}",
                        valid_states=list(valid_states),
                    )
                )

    return issues
```

#### Step 3: Integrate into Template Checking

**Modify _check_template() in jinja_validator.py:**
```python
def _check_template(
    self,
    template: str,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Check a template for syntax errors and semantic issues.

    Returns a list of ValidationIssues (empty if no problems).
    """
    # 1. Syntax check (existing)
    try:
        ast = self._env.parse(template)
    except TemplateSyntaxError as err:
        error_msg = str(err.message) if err.message else str(err)
        line_info = f" (line {err.lineno})" if err.lineno else ""
        return [
            ValidationIssue(
                issue_type=IssueType.TEMPLATE_SYNTAX_ERROR,
                severity=Severity.ERROR,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id="",
                location=location,
                message=f"Jinja2 syntax error{line_info}: {error_msg}",
                suggestion=None,
            )
        ]
    except Exception as err:
        return [
            ValidationIssue(
                issue_type=IssueType.TEMPLATE_SYNTAX_ERROR,
                severity=Severity.ERROR,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id="",
                location=location,
                message=f"Template error: {err}",
                suggestion=None,
            )
        ]

    issues = []

    # 2. Semantic check for filters/tests (existing)
    issues.extend(self._check_ast_semantics(ast, location, auto_id, auto_name))

    # 3. NEW: Semantic check for entity references
    refs = self._extract_entity_references(template, location, auto_id, auto_name)
    issues.extend(self._validate_entity_references(refs))

    return issues
```

### New Issue Types

**Add to models.py:**
```python
class IssueType(str, Enum):
    """Types of validation issues."""

    # ... existing types
    TEMPLATE_SYNTAX_ERROR = "template_syntax_error"
    TEMPLATE_UNKNOWN_FILTER = "template_unknown_filter"
    TEMPLATE_UNKNOWN_TEST = "template_unknown_test"

    # NEW: HA-specific semantic errors
    TEMPLATE_ENTITY_NOT_FOUND = "template_entity_not_found"
    TEMPLATE_INVALID_STATE = "template_invalid_state"
    TEMPLATE_ATTRIBUTE_NOT_FOUND = "template_attribute_not_found"
    TEMPLATE_DEVICE_NOT_FOUND = "template_device_not_found"
    TEMPLATE_AREA_NOT_FOUND = "template_area_not_found"
    TEMPLATE_ZONE_NOT_FOUND = "template_zone_not_found"
```

---

## Implementation Plan

### Phase 1: Trigger Type Coverage (Priority: HIGH)

**Files to modify:**
- `custom_components/autodoctor/analyzer.py` - Add 14 new trigger type handlers
- `custom_components/autodoctor/models.py` - No changes needed (StateReference already supports reference_type)

**Test files:**
- `tests/test_analyzer.py` - Add tests for each new trigger type

**Estimated effort:** Medium (2-3 sessions)

### Phase 2: Condition Type Coverage (Priority: MEDIUM)

**Files to modify:**
- `custom_components/autodoctor/analyzer.py` - Add 4 new condition type handlers
- Enhance existing numeric_state trigger attribute validation

**Test files:**
- `tests/test_analyzer.py` - Add tests for each new condition type

**Estimated effort:** Small (1 session)

### Phase 3: Jinja2 Semantic Validation (Priority: HIGH)

**Files to modify:**
- `custom_components/autodoctor/jinja_validator.py` - Add entity reference extraction and validation
- `custom_components/autodoctor/models.py` - Add new issue types

**Test files:**
- `tests/test_jinja_validator.py` - Add semantic validation tests

**Estimated effort:** Medium (2 sessions)

### Implementation Order

**Week 1:**
1. Phase 1 - Category A triggers (zone, sun, calendar)
2. Phase 1 - Category B triggers (device, tag, geolocation)

**Week 2:**
3. Phase 1 - Category C triggers (event, mqtt, webhook, persistent_notification)
4. Phase 1 - Category D triggers (time, time_pattern, homeassistant, sentence)
5. Phase 2 - All condition types

**Week 3:**
6. Phase 3 - Jinja2 semantic validation
7. Integration testing and refinement

---

## Testing Strategy

### Unit Tests

**For each trigger/condition type:**
```python
def test_extract_zone_trigger():
    """Test zone trigger extraction."""
    automation = {
        "id": "test",
        "alias": "Test Zone Trigger",
        "trigger": {
            "platform": "zone",
            "entity_id": "device_tracker.paulus",
            "zone": "zone.home",
            "event": "enter"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    assert refs[0].entity_id == "device_tracker.paulus"
    assert refs[0].reference_type == "direct"
    assert refs[1].entity_id == "zone.home"
    assert refs[1].reference_type == "zone"
```

**For Jinja2 semantic validation:**
```python
def test_template_entity_not_found(hass):
    """Test entity existence validation in templates."""
    validator = JinjaValidator(hass)

    automation = {
        "id": "test",
        "alias": "Test",
        "condition": {
            "condition": "template",
            "value_template": "{{ states.light.nonexistent.state == 'on' }}"
        }
    }

    issues = validator.validate_automations([automation])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND
    assert "light.nonexistent" in issues[0].message

def test_template_invalid_state(hass):
    """Test state value validation in is_state() calls."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "off")

    validator = JinjaValidator(hass)

    automation = {
        "id": "test",
        "alias": "Test",
        "condition": {
            "condition": "template",
            "value_template": "{{ is_state('light.kitchen', 'invalid_state') }}"
        }
    }

    issues = validator.validate_automations([automation])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_STATE
    assert "invalid_state" in issues[0].message
```

### Integration Tests

**Test complete automation with multiple trigger/condition types:**
```python
def test_comprehensive_automation_validation(hass):
    """Test automation with multiple trigger and condition types."""
    automation = {
        "id": "comprehensive",
        "alias": "Comprehensive Test",
        "trigger": [
            {"platform": "zone", "entity_id": "device_tracker.paulus", "zone": "zone.home", "event": "enter"},
            {"platform": "sun", "event": "sunset"},
            {"platform": "calendar", "entity_id": "calendar.events", "event": "start"},
        ],
        "condition": [
            {"condition": "numeric_state", "entity_id": "sensor.temperature", "above": 20},
            {"condition": "zone", "entity_id": "device_tracker.anne", "zone": "zone.work"},
            {"condition": "template", "value_template": "{{ is_state('light.kitchen', 'on') }}"},
        ],
        "action": []
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Verify all entities extracted
    entity_ids = {ref.entity_id for ref in refs}
    assert "device_tracker.paulus" in entity_ids
    assert "zone.home" in entity_ids
    assert "sun.sun" in entity_ids
    assert "calendar.events" in entity_ids
    assert "sensor.temperature" in entity_ids
    assert "device_tracker.anne" in entity_ids
    assert "zone.work" in entity_ids
    assert "light.kitchen" in entity_ids
```

### Edge Cases

**Test malformed configurations:**
```python
def test_missing_entity_id_in_zone_trigger():
    """Test zone trigger without entity_id."""
    automation = {
        "id": "test",
        "trigger": {"platform": "zone", "zone": "zone.home", "event": "enter"}
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)
    # Should not crash, just extract zone
    assert len(refs) == 1
    assert refs[0].entity_id == "zone.home"

def test_template_with_syntax_and_semantic_errors(hass):
    """Test template with both syntax and semantic issues."""
    validator = JinjaValidator(hass)

    automation = {
        "id": "test",
        "condition": {
            "condition": "template",
            "value_template": "{{ states.light.nonexistent.state == 'on' }}"  # Entity doesn't exist
        }
    }

    issues = validator.validate_automations([automation])
    # Should report entity not found
    assert any(i.issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND for i in issues)
```

---

## Success Criteria

### Trigger Coverage Success

- [ ] All 17 trigger types have extraction logic
- [ ] Entity/zone/device/area references validated where applicable
- [ ] Templates in non-entity triggers extracted
- [ ] No regression in existing trigger validation
- [ ] Test coverage > 90% for new trigger handlers

### Condition Coverage Success

- [ ] All 10 condition types have extraction logic
- [ ] Numeric state conditions validate attributes
- [ ] Zone/sun/time conditions extract entity references
- [ ] No regression in existing condition validation
- [ ] Test coverage > 90% for new condition handlers

### Jinja2 Semantic Validation Success

- [ ] Entity existence validated in all template patterns
- [ ] State values validated in is_state() calls
- [ ] Attributes validated in state_attr/is_state_attr calls
- [ ] Device/area/zone references validated
- [ ] No performance regression (< 10% slowdown)
- [ ] Test coverage > 90% for semantic validation

### Overall Success

- [ ] Zero false negatives for entity-based triggers/conditions
- [ ] Template semantic errors caught before automation execution
- [ ] All existing tests pass
- [ ] Integration tests cover realistic automations
- [ ] Documentation updated in index.md

---

## Risks & Mitigations

### Risk: Performance Impact from Template Semantic Validation

**Impact:** Validation could slow down significantly

**Mitigation:**
- Reuse existing regex patterns (no new parsing overhead)
- Cache knowledge base lookups (already implemented)
- Only validate when hass instance available
- Profile validation speed before/after

### Risk: False Positives from Registry Lookups

**Impact:** Device/area/zone might not be in registry yet

**Mitigation:**
- Use INFO or WARNING severity for registry misses
- Allow learning/suppression as escape hatch
- Only validate if registry available

### Risk: Template Extraction Misses Edge Cases

**Impact:** Some entity references not validated

**Mitigation:**
- Comprehensive test suite with edge cases
- Reuse proven analyzer patterns
- Log debug info when extraction uncertain

### Risk: Breaking Changes in Existing Validation

**Impact:** Current automations fail new validation

**Mitigation:**
- Only add new validations, don't change existing
- Use appropriate severity levels (WARNING vs ERROR)
- Extensive regression testing

---

## Future Enhancements

### Dynamic Trigger/Condition Type Discovery

Instead of hardcoding trigger types, discover from HA:
```python
from homeassistant.helpers.trigger import async_validate_trigger_config

# Use HA's internal trigger validation registry
```

### Integration-Specific Device Trigger Validation

Validate device trigger types using integration schemas:
```python
# For MQTT device trigger, validate against MQTT schema
from homeassistant.components.mqtt import device_trigger
triggers = await device_trigger.async_get_triggers(hass, device_id)
```

### Template Variable Validation

Validate trigger variables in templates:
```python
# Validate that trigger.to_state exists for state trigger
"{{ trigger.to_state.state }}"  # Valid for state trigger
"{{ trigger.to_state.state }}"  # Invalid for time trigger
```

---

## References

- Home Assistant Triggers: https://www.home-assistant.io/docs/automation/trigger/
- Home Assistant Conditions: https://www.home-assistant.io/docs/scripts/conditions/
- Jinja2 Template Documentation: https://jinja.palletsprojects.com/
- HA Developer Docs: https://developers.home-assistant.io/docs/automations
- Current `analyzer.py`: Lines 128-582 (trigger/condition extraction)
- Current `jinja_validator.py`: Lines 86-547 (template validation)
- Current `models.py`: Lines 32-46 (StateReference), Lines 18-29 (IssueType)

---

## Changelog

**2026-01-29:** Initial design - comprehensive trigger/condition coverage and Jinja2 semantic validation
