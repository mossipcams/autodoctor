# Comprehensive Trigger/Condition Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand autodoctor validation from 3 trigger types and 3 condition types to 17 trigger types and 10 condition types, plus add HA-specific semantic validation to Jinja2 templates.

**Architecture:** Add trigger/condition type handlers to analyzer.py following existing patterns, add semantic validation layer to jinja_validator.py reusing analyzer patterns, add new issue types to models.py.

**Tech Stack:** Python 3.12+, Home Assistant core helpers (device_registry, area_registry), pytest

---

## Prerequisites

**Design Document:** `docs/plans/2026-01-29-comprehensive-trigger-condition-coverage.md`

**Key Files:**
- `custom_components/autodoctor/analyzer.py` - Add trigger/condition handlers
- `custom_components/autodoctor/jinja_validator.py` - Add semantic validation
- `custom_components/autodoctor/models.py` - Add new issue types
- `tests/test_analyzer.py` - Test trigger/condition extraction
- `tests/test_jinja_validator.py` - Test semantic validation

---

## Task 1: Add Helper Method for Entity ID Normalization

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:70-86`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_normalize_entity_ids_single_string():
    """Test normalizing single entity_id string to list."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids("light.kitchen")
    assert result == ["light.kitchen"]


def test_normalize_entity_ids_list():
    """Test normalizing entity_id list."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids(["light.kitchen", "light.bedroom"])
    assert result == ["light.kitchen", "light.bedroom"]


def test_normalize_entity_ids_none():
    """Test normalizing None entity_id."""
    analyzer = AutomationAnalyzer()
    result = analyzer._normalize_entity_ids(None)
    assert result == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_normalize_entity_ids_single_string tests/test_analyzer.py::test_normalize_entity_ids_list tests/test_analyzer.py::test_normalize_entity_ids_none -v`

Expected: FAIL with "AttributeError: 'AutomationAnalyzer' object has no attribute '_normalize_entity_ids'"

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/analyzer.py` after the `_normalize_states` method (around line 86):

```python
def _normalize_entity_ids(self, value: Any) -> list[str]:
    """Normalize entity_id value(s) to a list of strings.

    HA configs can have entity_id as:
    - A single string: "light.kitchen"
    - A list of strings: ["light.kitchen", "light.bedroom"]
    - None
    """
    if value is None:
        return []

    # Handle list-like objects
    if hasattr(value, "__iter__") and not isinstance(value, str):
        return [str(v) for v in value]

    return [str(value)]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py::test_normalize_entity_ids_single_string tests/test_analyzer.py::test_normalize_entity_ids_list tests/test_analyzer.py::test_normalize_entity_ids_none -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add entity_id normalization helper method"
```

---

## Task 2: Add Category A Entity-Based Triggers (zone, sun, calendar)

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:128-209`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_zone_trigger():
    """Test zone trigger extraction."""
    automation = {
        "id": "test_zone",
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
    assert refs[0].location == "trigger[0].entity_id"
    assert refs[1].entity_id == "zone.home"
    assert refs[1].reference_type == "zone"
    assert refs[1].location == "trigger[0].zone"


def test_extract_zone_trigger_multiple_entities():
    """Test zone trigger with multiple entity_ids."""
    automation = {
        "id": "test_zone_multi",
        "alias": "Test Zone Multiple",
        "trigger": {
            "platform": "zone",
            "entity_id": ["device_tracker.paulus", "device_tracker.anne"],
            "zone": "zone.work",
            "event": "leave"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 3
    entity_ids = [r.entity_id for r in refs]
    assert "device_tracker.paulus" in entity_ids
    assert "device_tracker.anne" in entity_ids
    assert "zone.work" in entity_ids


def test_extract_sun_trigger():
    """Test sun trigger extraction."""
    automation = {
        "id": "test_sun",
        "alias": "Test Sun Trigger",
        "trigger": {
            "platform": "sun",
            "event": "sunset",
            "offset": "-01:00:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sun.sun"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0]"


def test_extract_calendar_trigger():
    """Test calendar trigger extraction."""
    automation = {
        "id": "test_calendar",
        "alias": "Test Calendar Trigger",
        "trigger": {
            "platform": "calendar",
            "entity_id": "calendar.events",
            "event": "start",
            "offset": "-00:05:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "calendar.events"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0].entity_id"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_zone_trigger tests/test_analyzer.py::test_extract_zone_trigger_multiple_entities tests/test_analyzer.py::test_extract_sun_trigger tests/test_analyzer.py::test_extract_calendar_trigger -v`

Expected: FAIL (4 tests) - triggers not extracted, refs list is empty or incomplete

**Step 3: Write minimal implementation**

In `custom_components/autodoctor/analyzer.py`, add to `_extract_from_trigger` method after the `elif platform == "template":` block (around line 207):

```python
        elif platform == "zone":
            entity_ids = self._normalize_entity_ids(trigger.get("entity_id"))
            zone_id = trigger.get("zone")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].entity_id",
                        reference_type="direct",
                    )
                )

            if zone_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=zone_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].zone",
                        reference_type="zone",
                    )
                )

        elif platform == "sun":
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id="sun.sun",
                    expected_state=None,
                    expected_attribute=None,
                    location=f"trigger[{index}]",
                    reference_type="direct",
                )
            )

        elif platform == "calendar":
            entity_ids = self._normalize_entity_ids(trigger.get("entity_id"))

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].entity_id",
                        reference_type="direct",
                    )
                )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_zone_trigger tests/test_analyzer.py::test_extract_zone_trigger_multiple_entities tests/test_analyzer.py::test_extract_sun_trigger tests/test_analyzer.py::test_extract_calendar_trigger -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add zone, sun, and calendar trigger extraction"
```

---

## Task 3: Add Category B Resource-Based Triggers (device, tag, geolocation)

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py` (after previous trigger additions)
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_device_trigger():
    """Test device trigger extraction."""
    automation = {
        "id": "test_device",
        "alias": "Test Device Trigger",
        "trigger": {
            "platform": "device",
            "device_id": "abc123def456",
            "domain": "mqtt",
            "type": "button_short_press",
            "subtype": "button_1"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "abc123def456"
    assert refs[0].reference_type == "device"
    assert refs[0].location == "trigger[0].device_id"


def test_extract_tag_trigger():
    """Test tag trigger extraction."""
    automation = {
        "id": "test_tag",
        "alias": "Test Tag Trigger",
        "trigger": {
            "platform": "tag",
            "tag_id": "AABBCCDD",
            "device_id": "scanner_device_123"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    assert refs[0].entity_id == "AABBCCDD"
    assert refs[0].reference_type == "tag"
    assert refs[0].location == "trigger[0].tag_id"
    assert refs[1].entity_id == "scanner_device_123"
    assert refs[1].reference_type == "device"
    assert refs[1].location == "trigger[0].device_id"


def test_extract_tag_trigger_no_device():
    """Test tag trigger without device_id."""
    automation = {
        "id": "test_tag_no_device",
        "alias": "Test Tag No Device",
        "trigger": {
            "platform": "tag",
            "tag_id": "EEFFGGHH"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "EEFFGGHH"
    assert refs[0].reference_type == "tag"


def test_extract_geo_location_trigger():
    """Test geo_location trigger extraction."""
    automation = {
        "id": "test_geo",
        "alias": "Test Geo Location Trigger",
        "trigger": {
            "platform": "geo_location",
            "source": "nsw_rural_fire_service_feed",
            "zone": "zone.home",
            "event": "enter"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "zone.home"
    assert refs[0].reference_type == "zone"
    assert refs[0].location == "trigger[0].zone"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_device_trigger tests/test_analyzer.py::test_extract_tag_trigger tests/test_analyzer.py::test_extract_tag_trigger_no_device tests/test_analyzer.py::test_extract_geo_location_trigger -v`

Expected: FAIL (4 tests)

**Step 3: Write minimal implementation**

Add to `_extract_from_trigger` method in `analyzer.py` after the calendar trigger block:

```python
        elif platform == "device":
            device_id = trigger.get("device_id")

            if device_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].device_id",
                        reference_type="device",
                    )
                )

        elif platform == "tag":
            tag_id = trigger.get("tag_id")
            device_id = trigger.get("device_id")

            if tag_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=tag_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].tag_id",
                        reference_type="tag",
                    )
                )

            if device_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].device_id",
                        reference_type="device",
                    )
                )

        elif platform == "geo_location":
            zone_id = trigger.get("zone")

            if zone_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=zone_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"trigger[{index}].zone",
                        reference_type="zone",
                    )
                )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_device_trigger tests/test_analyzer.py::test_extract_tag_trigger tests/test_analyzer.py::test_extract_tag_trigger_no_device tests/test_analyzer.py::test_extract_geo_location_trigger -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add device, tag, and geo_location trigger extraction"
```

---

## Task 4: Add Category C Non-Entity Triggers (event, mqtt, webhook, persistent_notification)

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_event_trigger_with_template():
    """Test event trigger with template in event_data."""
    automation = {
        "id": "test_event",
        "alias": "Test Event Trigger",
        "trigger": {
            "platform": "event",
            "event_type": "my_custom_event",
            "event_data": {
                "entity": "{{ states('input_text.target') }}"
            }
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.target"
    assert refs[0].location == "trigger[0].event_data.entity.states_function"


def test_extract_mqtt_trigger_with_template():
    """Test MQTT trigger with template in topic."""
    automation = {
        "id": "test_mqtt",
        "alias": "Test MQTT Trigger",
        "trigger": {
            "platform": "mqtt",
            "topic": "home/{{ states('input_text.room') }}/light",
            "payload": "ON"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.room"
    assert refs[0].location == "trigger[0].topic.states_function"


def test_extract_webhook_trigger():
    """Test webhook trigger (no entity references expected)."""
    automation = {
        "id": "test_webhook",
        "alias": "Test Webhook Trigger",
        "trigger": {
            "platform": "webhook",
            "webhook_id": "my_webhook_123",
            "allowed_methods": ["POST", "PUT"]
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # No entity references expected for static webhook_id
    assert len(refs) == 0


def test_extract_webhook_trigger_with_template():
    """Test webhook trigger with template in webhook_id."""
    automation = {
        "id": "test_webhook_template",
        "alias": "Test Webhook Template",
        "trigger": {
            "platform": "webhook",
            "webhook_id": "webhook_{{ states('input_text.name') }}"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.name"


def test_extract_persistent_notification_trigger():
    """Test persistent_notification trigger with template."""
    automation = {
        "id": "test_notification",
        "alias": "Test Notification Trigger",
        "trigger": {
            "platform": "persistent_notification",
            "notification_id": "alert_{{ states('input_text.alert_name') }}",
            "update_type": "added"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_text.alert_name"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_event_trigger_with_template tests/test_analyzer.py::test_extract_mqtt_trigger_with_template tests/test_analyzer.py::test_extract_webhook_trigger tests/test_analyzer.py::test_extract_webhook_trigger_with_template tests/test_analyzer.py::test_extract_persistent_notification_trigger -v`

Expected: FAIL (5 tests)

**Step 3: Write minimal implementation**

Add to `_extract_from_trigger` method in `analyzer.py`:

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
                                automation_id,
                                automation_name,
                            )
                        )

        elif platform == "mqtt":
            topic = trigger.get("topic", "")
            payload = trigger.get("payload", "")

            if isinstance(topic, str):
                refs.extend(
                    self._extract_from_template(
                        topic,
                        f"trigger[{index}].topic",
                        automation_id,
                        automation_name,
                    )
                )

            if isinstance(payload, str):
                refs.extend(
                    self._extract_from_template(
                        payload,
                        f"trigger[{index}].payload",
                        automation_id,
                        automation_name,
                    )
                )

        elif platform == "webhook":
            webhook_id = trigger.get("webhook_id", "")

            if isinstance(webhook_id, str):
                refs.extend(
                    self._extract_from_template(
                        webhook_id,
                        f"trigger[{index}].webhook_id",
                        automation_id,
                        automation_name,
                    )
                )

        elif platform == "persistent_notification":
            notification_id = trigger.get("notification_id", "")

            if isinstance(notification_id, str):
                refs.extend(
                    self._extract_from_template(
                        notification_id,
                        f"trigger[{index}].notification_id",
                        automation_id,
                        automation_name,
                    )
                )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_event_trigger_with_template tests/test_analyzer.py::test_extract_mqtt_trigger_with_template tests/test_analyzer.py::test_extract_webhook_trigger tests/test_analyzer.py::test_extract_webhook_trigger_with_template tests/test_analyzer.py::test_extract_persistent_notification_trigger -v`

Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add event, mqtt, webhook, and persistent_notification triggers"
```

---

## Task 5: Add Category D Time-Based Trigger (time)

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_time_trigger_with_entity():
    """Test time trigger with entity reference."""
    automation = {
        "id": "test_time",
        "alias": "Test Time Trigger",
        "trigger": {
            "platform": "time",
            "at": "input_datetime.wake_up_time"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_datetime.wake_up_time"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "trigger[0].at"


def test_extract_time_trigger_with_time_string():
    """Test time trigger with time string (no entity reference)."""
    automation = {
        "id": "test_time_string",
        "alias": "Test Time String",
        "trigger": {
            "platform": "time",
            "at": "07:30:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # No entity references for time strings
    assert len(refs) == 0


def test_extract_time_trigger_with_multiple():
    """Test time trigger with multiple at values."""
    automation = {
        "id": "test_time_multi",
        "alias": "Test Time Multiple",
        "trigger": {
            "platform": "time",
            "at": [
                "input_datetime.wake_up",
                "07:30:00",
                "sensor.sunset_time"
            ]
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    entity_ids = [r.entity_id for r in refs]
    assert "input_datetime.wake_up" in entity_ids
    assert "sensor.sunset_time" in entity_ids
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_time_trigger_with_entity tests/test_analyzer.py::test_extract_time_trigger_with_time_string tests/test_analyzer.py::test_extract_time_trigger_with_multiple -v`

Expected: FAIL (3 tests)

**Step 3: Write minimal implementation**

Add to `_extract_from_trigger` method in `analyzer.py`:

```python
        elif platform == "time":
            at_values = trigger.get("at")
            if not isinstance(at_values, list):
                at_values = [at_values] if at_values else []

            for at_value in at_values:
                # If it looks like an entity_id (contains a dot but not a colon), validate it
                if isinstance(at_value, str) and "." in at_value and ":" not in at_value:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=at_value,
                            expected_state=None,
                            expected_attribute=None,
                            location=f"trigger[{index}].at",
                            reference_type="direct",
                        )
                    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_time_trigger_with_entity tests/test_analyzer.py::test_extract_time_trigger_with_time_string tests/test_analyzer.py::test_extract_time_trigger_with_multiple -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add time trigger extraction with entity support"
```

---

## Task 6: Add Numeric State Condition

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:211-277`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_numeric_state_condition():
    """Test numeric_state condition extraction."""
    automation = {
        "id": "test_numeric_cond",
        "alias": "Test Numeric Condition",
        "condition": {
            "condition": "numeric_state",
            "entity_id": "sensor.temperature",
            "above": 20,
            "below": 30
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sensor.temperature"
    assert refs[0].expected_attribute is None
    assert refs[0].location == "condition[0]"


def test_extract_numeric_state_condition_with_attribute():
    """Test numeric_state condition with attribute."""
    automation = {
        "id": "test_numeric_attr",
        "alias": "Test Numeric Attribute",
        "condition": {
            "condition": "numeric_state",
            "entity_id": "climate.living_room",
            "attribute": "temperature",
            "above": 20
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "temperature"
    assert refs[0].location == "condition[0]"


def test_extract_numeric_state_condition_with_template():
    """Test numeric_state condition with value_template."""
    automation = {
        "id": "test_numeric_template",
        "alias": "Test Numeric Template",
        "condition": {
            "condition": "numeric_state",
            "entity_id": "sensor.data",
            "value_template": "{{ state.attributes.value | float }}",
            "above": 10
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # Should extract entity_id
    assert len(refs) >= 1
    entity_ids = [r.entity_id for r in refs]
    assert "sensor.data" in entity_ids
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_numeric_state_condition tests/test_analyzer.py::test_extract_numeric_state_condition_with_attribute tests/test_analyzer.py::test_extract_numeric_state_condition_with_template -v`

Expected: FAIL (3 tests)

**Step 3: Write minimal implementation**

Add to `_extract_from_condition` method in `analyzer.py` after the template condition block (around line 275):

```python
        elif cond_type == "numeric_state":
            entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
            attribute = condition.get("attribute")
            value_template = condition.get("value_template")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=attribute,
                        location=f"{location_prefix}[{index}]",
                        reference_type="direct",
                    )
                )

            # Extract from value_template if present
            if value_template and isinstance(value_template, str):
                refs.extend(
                    self._extract_from_template(
                        value_template,
                        f"{location_prefix}[{index}].value_template",
                        automation_id,
                        automation_name,
                    )
                )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_numeric_state_condition tests/test_analyzer.py::test_extract_numeric_state_condition_with_attribute tests/test_analyzer.py::test_extract_numeric_state_condition_with_template -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add numeric_state condition extraction"
```

---

## Task 7: Add Zone, Sun, and Time Conditions

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing tests**

Add to `tests/test_analyzer.py`:

```python
def test_extract_zone_condition():
    """Test zone condition extraction."""
    automation = {
        "id": "test_zone_cond",
        "alias": "Test Zone Condition",
        "condition": {
            "condition": "zone",
            "entity_id": "device_tracker.paulus",
            "zone": "zone.home"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 2
    assert refs[0].entity_id == "device_tracker.paulus"
    assert refs[0].location == "condition[0].entity_id"
    assert refs[1].entity_id == "zone.home"
    assert refs[1].reference_type == "zone"
    assert refs[1].location == "condition[0].zone"


def test_extract_sun_condition():
    """Test sun condition extraction."""
    automation = {
        "id": "test_sun_cond",
        "alias": "Test Sun Condition",
        "condition": {
            "condition": "sun",
            "after": "sunset",
            "after_offset": "-01:00:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "sun.sun"
    assert refs[0].reference_type == "direct"
    assert refs[0].location == "condition[0]"


def test_extract_time_condition_with_entity():
    """Test time condition with entity references."""
    automation = {
        "id": "test_time_cond",
        "alias": "Test Time Condition",
        "condition": {
            "condition": "time",
            "after": "input_datetime.wake_up",
            "before": "22:00:00",
            "weekday": ["mon", "tue", "wed"]
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "input_datetime.wake_up"
    assert refs[0].location == "condition[0].after"


def test_extract_time_condition_no_entities():
    """Test time condition with time strings only."""
    automation = {
        "id": "test_time_cond_strings",
        "alias": "Test Time Strings",
        "condition": {
            "condition": "time",
            "after": "08:00:00",
            "before": "22:00:00"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    # No entity references for time strings
    assert len(refs) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_analyzer.py::test_extract_zone_condition tests/test_analyzer.py::test_extract_sun_condition tests/test_analyzer.py::test_extract_time_condition_with_entity tests/test_analyzer.py::test_extract_time_condition_no_entities -v`

Expected: FAIL (4 tests)

**Step 3: Write minimal implementation**

Add to `_extract_from_condition` method in `analyzer.py` after numeric_state condition block:

```python
        elif cond_type == "zone":
            entity_ids = self._normalize_entity_ids(condition.get("entity_id"))
            zone_id = condition.get("zone")

            for entity_id in entity_ids:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].entity_id",
                        reference_type="direct",
                    )
                )

            if zone_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=zone_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].zone",
                        reference_type="zone",
                    )
                )

        elif cond_type == "sun":
            refs.append(
                StateReference(
                    automation_id=automation_id,
                    automation_name=automation_name,
                    entity_id="sun.sun",
                    expected_state=None,
                    expected_attribute=None,
                    location=f"{location_prefix}[{index}]",
                    reference_type="direct",
                )
            )

        elif cond_type == "time":
            for key in ["after", "before"]:
                value = condition.get(key)
                # If it looks like an entity_id (contains dot but not colon), validate it
                if isinstance(value, str) and "." in value and ":" not in value:
                    refs.append(
                        StateReference(
                            automation_id=automation_id,
                            automation_name=automation_name,
                            entity_id=value,
                            expected_state=None,
                            expected_attribute=None,
                            location=f"{location_prefix}[{index}].{key}",
                            reference_type="direct",
                        )
                    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py::test_extract_zone_condition tests/test_analyzer.py::test_extract_sun_condition tests/test_analyzer.py::test_extract_time_condition_with_entity tests/test_analyzer.py::test_extract_time_condition_no_entities -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add zone, sun, and time condition extraction"
```

---

## Task 8: Add Device Condition

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_device_condition():
    """Test device condition extraction."""
    automation = {
        "id": "test_device_cond",
        "alias": "Test Device Condition",
        "condition": {
            "condition": "device",
            "device_id": "abc123def456",
            "domain": "light",
            "type": "is_on"
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "abc123def456"
    assert refs[0].reference_type == "device"
    assert refs[0].location == "condition[0].device_id"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_device_condition -v`

Expected: FAIL

**Step 3: Write minimal implementation**

Add to `_extract_from_condition` method in `analyzer.py` after time condition block:

```python
        elif cond_type == "device":
            device_id = condition.get("device_id")

            if device_id:
                refs.append(
                    StateReference(
                        automation_id=automation_id,
                        automation_name=automation_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location_prefix}[{index}].device_id",
                        reference_type="device",
                    )
                )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py::test_extract_device_condition -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add device condition extraction"
```

---

## Task 9: Enhance Numeric State Trigger with Attribute Validation

**Files:**
- Modify: `custom_components/autodoctor/analyzer.py:182-199`
- Test: `tests/test_analyzer.py`

**Step 1: Write the failing test**

Add to `tests/test_analyzer.py`:

```python
def test_extract_numeric_state_trigger_with_attribute():
    """Test numeric_state trigger now extracts attribute for validation."""
    automation = {
        "id": "test_numeric_trigger_attr",
        "alias": "Test Numeric Trigger Attribute",
        "trigger": {
            "platform": "numeric_state",
            "entity_id": "climate.living_room",
            "attribute": "temperature",
            "above": 20
        }
    }

    analyzer = AutomationAnalyzer()
    refs = analyzer.extract_state_references(automation)

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "temperature"
    assert refs[0].location == "trigger[0]"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py::test_extract_numeric_state_trigger_with_attribute -v`

Expected: FAIL (expected_attribute is None, should be "temperature")

**Step 3: Modify implementation**

In `analyzer.py`, find the numeric_state trigger block (around line 182-199) and update it to extract the attribute:

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
                        expected_attribute=attribute,  # Now captures attribute
                        location=f"trigger[{index}]",
                    )
                )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_analyzer.py::test_extract_numeric_state_trigger_with_attribute -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_analyzer.py custom_components/autodoctor/analyzer.py
git commit -m "feat(analyzer): add attribute validation to numeric_state triggers"
```

---

## Task 10: Add New Issue Types for Jinja2 Semantic Validation

**Files:**
- Modify: `custom_components/autodoctor/models.py:18-29`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_new_template_issue_types():
    """Test new template-related issue types exist."""
    assert hasattr(IssueType, "TEMPLATE_ENTITY_NOT_FOUND")
    assert hasattr(IssueType, "TEMPLATE_INVALID_STATE")
    assert hasattr(IssueType, "TEMPLATE_ATTRIBUTE_NOT_FOUND")
    assert hasattr(IssueType, "TEMPLATE_DEVICE_NOT_FOUND")
    assert hasattr(IssueType, "TEMPLATE_AREA_NOT_FOUND")
    assert hasattr(IssueType, "TEMPLATE_ZONE_NOT_FOUND")

    assert IssueType.TEMPLATE_ENTITY_NOT_FOUND.value == "template_entity_not_found"
    assert IssueType.TEMPLATE_INVALID_STATE.value == "template_invalid_state"
    assert IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND.value == "template_attribute_not_found"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py::test_new_template_issue_types -v`

Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

In `custom_components/autodoctor/models.py`, add to the IssueType enum (after TEMPLATE_UNKNOWN_TEST):

```python
class IssueType(str, Enum):
    """Types of validation issues."""

    ENTITY_NOT_FOUND = "entity_not_found"
    ENTITY_REMOVED = "entity_removed"
    INVALID_STATE = "invalid_state"
    CASE_MISMATCH = "case_mismatch"
    ATTRIBUTE_NOT_FOUND = "attribute_not_found"
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

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py::test_new_template_issue_types -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_models.py custom_components/autodoctor/models.py
git commit -m "feat(models): add new issue types for Jinja2 semantic validation"
```

---

## Task 11: Add Entity Reference Extraction to JinjaValidator

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_jinja_validator.py`:

```python
def test_extract_entity_references_from_is_state():
    """Test extracting entity references from is_state() calls."""
    validator = JinjaValidator()

    template = "{{ is_state('light.kitchen', 'on') }}"
    refs = validator._extract_entity_references(
        template,
        "test_location",
        "automation.test",
        "Test Automation"
    )

    assert len(refs) == 1
    assert refs[0].entity_id == "light.kitchen"
    assert refs[0].expected_state == "on"
    assert refs[0].location == "test_location.is_state"


def test_extract_entity_references_from_state_attr():
    """Test extracting entity references from state_attr() calls."""
    validator = JinjaValidator()

    template = "{{ state_attr('climate.living_room', 'temperature') }}"
    refs = validator._extract_entity_references(
        template,
        "test_location",
        "automation.test",
        "Test Automation"
    )

    assert len(refs) == 1
    assert refs[0].entity_id == "climate.living_room"
    assert refs[0].expected_attribute == "temperature"
    assert refs[0].location == "test_location.state_attr"


def test_extract_entity_references_from_states_object():
    """Test extracting entity references from states.domain.entity syntax."""
    validator = JinjaValidator()

    template = "{{ states.light.bedroom.state }}"
    refs = validator._extract_entity_references(
        template,
        "test_location",
        "automation.test",
        "Test Automation"
    )

    assert len(refs) == 1
    assert refs[0].entity_id == "light.bedroom"
    assert refs[0].location == "test_location.states_object"


def test_extract_entity_references_multiple_patterns():
    """Test extracting from template with multiple patterns."""
    validator = JinjaValidator()

    template = "{{ is_state('light.kitchen', 'on') and states.sensor.temp.state | float > 20 }}"
    refs = validator._extract_entity_references(
        template,
        "test_location",
        "automation.test",
        "Test Automation"
    )

    assert len(refs) == 2
    entity_ids = [r.entity_id for r in refs]
    assert "light.kitchen" in entity_ids
    assert "sensor.temp" in entity_ids
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_extract_entity_references_from_is_state tests/test_jinja_validator.py::test_extract_entity_references_from_state_attr tests/test_jinja_validator.py::test_extract_entity_references_from_states_object tests/test_jinja_validator.py::test_extract_entity_references_multiple_patterns -v`

Expected: FAIL with AttributeError (method doesn't exist)

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/jinja_validator.py` after the `_is_template` method (around line 461):

```python
    def _extract_entity_references(
        self,
        template: str,
        location: str,
        auto_id: str,
        auto_name: str,
    ) -> list[StateReference]:
        """Extract entity references from template using analyzer patterns.

        Reuses regex patterns from AutomationAnalyzer._extract_from_template()
        to find all entity references in the template.
        """
        # Import analyzer patterns (avoid circular import at module level)
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
            entity_id, attribute, _value = match.groups()
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

        # Extract expand() calls
        for match in EXPAND_PATTERN.finditer(template):
            entity_id = match.group(1)
            if not any(r.entity_id == entity_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=entity_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.expand",
                        reference_type="group",
                    )
                )

        # Extract area_entities() calls
        for match in AREA_ENTITIES_PATTERN.finditer(template):
            area_id = match.group(1)
            if not any(r.entity_id == area_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=area_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.area_entities",
                        reference_type="area",
                    )
                )

        # Extract device_entities() calls
        for match in DEVICE_ENTITIES_PATTERN.finditer(template):
            device_id = match.group(1)
            if not any(r.entity_id == device_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=device_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.device_entities",
                        reference_type="device",
                    )
                )

        # Extract integration_entities() calls
        for match in INTEGRATION_ENTITIES_PATTERN.finditer(template):
            integration_id = match.group(1)
            if not any(r.entity_id == integration_id for r in refs):
                refs.append(
                    StateReference(
                        automation_id=auto_id,
                        automation_name=auto_name,
                        entity_id=integration_id,
                        expected_state=None,
                        expected_attribute=None,
                        location=f"{location}.integration_entities",
                        reference_type="integration",
                    )
                )

        return refs
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_extract_entity_references_from_is_state tests/test_jinja_validator.py::test_extract_entity_references_from_state_attr tests/test_jinja_validator.py::test_extract_entity_references_from_states_object tests/test_jinja_validator.py::test_extract_entity_references_multiple_patterns -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/test_jinja_validator.py custom_components/autodoctor/jinja_validator.py
git commit -m "feat(jinja): add entity reference extraction to JinjaValidator"
```

---

## Task 12: Add Semantic Validation to JinjaValidator

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing tests**

Add to `tests/test_jinja_validator.py`:

```python
def test_validate_entity_not_found(hass):
    """Test entity existence validation."""
    validator = JinjaValidator(hass)

    # Create a reference to non-existent entity
    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.nonexistent",
            expected_state=None,
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ENTITY_NOT_FOUND
    assert "light.nonexistent" in issues[0].message


def test_validate_attribute_not_found(hass):
    """Test attribute existence validation."""
    # Setup entity in hass
    hass.states.async_set("climate.living_room", "heat", {"temperature": 20})

    validator = JinjaValidator(hass)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="climate.living_room",
            expected_state=None,
            expected_attribute="nonexistent_attr",
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND
    assert "nonexistent_attr" in issues[0].message


def test_validate_invalid_state(hass):
    """Test state value validation."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "off")

    validator = JinjaValidator(hass)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.kitchen",
            expected_state="invalid_state",
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    # Should find invalid state issue
    assert len(issues) >= 1
    assert any(i.issue_type == IssueType.TEMPLATE_INVALID_STATE for i in issues)


def test_validate_entity_exists_no_issues(hass):
    """Test validation passes for existing entity."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "on")

    validator = JinjaValidator(hass)

    refs = [
        StateReference(
            automation_id="automation.test",
            automation_name="Test",
            entity_id="light.kitchen",
            expected_state=None,
            expected_attribute=None,
            location="test_location",
        )
    ]

    issues = validator._validate_entity_references(refs)

    assert len(issues) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_validate_entity_not_found tests/test_jinja_validator.py::test_validate_attribute_not_found tests/test_jinja_validator.py::test_validate_invalid_state tests/test_jinja_validator.py::test_validate_entity_exists_no_issues -v`

Expected: FAIL with AttributeError (method doesn't exist)

**Step 3: Write minimal implementation**

Add to `custom_components/autodoctor/jinja_validator.py` after `_extract_entity_references`:

```python
    def _validate_entity_references(
        self,
        refs: list[StateReference],
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
                    available_attrs = sorted(state.attributes.keys())[:10]
                    issues.append(
                        ValidationIssue(
                            issue_type=IssueType.TEMPLATE_ATTRIBUTE_NOT_FOUND,
                            severity=Severity.ERROR,
                            automation_id=ref.automation_id,
                            automation_name=ref.automation_name,
                            entity_id=ref.entity_id,
                            location=ref.location,
                            message=f"Attribute '{ref.expected_attribute}' not found on {ref.entity_id}",
                            suggestion=f"Available attributes: {', '.join(available_attrs)}",
                        )
                    )

            # 3. Validate state value if specified (from is_state calls)
            if ref.expected_state:
                # Use knowledge base to check if state is valid
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

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_validate_entity_not_found tests/test_jinja_validator.py::test_validate_attribute_not_found tests/test_jinja_validator.py::test_validate_invalid_state tests/test_jinja_validator.py::test_validate_entity_exists_no_issues -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/test_jinja_validator.py custom_components/autodoctor/jinja_validator.py
git commit -m "feat(jinja): add semantic validation for entity references"
```

---

## Task 13: Integrate Semantic Validation into Template Checking

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py:503-546`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_jinja_validator.py`:

```python
def test_template_validation_end_to_end(hass):
    """Test complete template validation with entity and state checks."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "off")

    validator = JinjaValidator(hass)

    automation = {
        "id": "test_e2e",
        "alias": "Test End to End",
        "condition": {
            "condition": "template",
            "value_template": "{{ is_state('light.nonexistent', 'on') and is_state('light.kitchen', 'invalid_state') }}"
        }
    }

    issues = validator.validate_automations([automation])

    # Should find both entity not found and invalid state
    assert len(issues) >= 2
    issue_types = {i.issue_type for i in issues}
    assert IssueType.TEMPLATE_ENTITY_NOT_FOUND in issue_types
    assert IssueType.TEMPLATE_INVALID_STATE in issue_types


def test_template_validation_passes_for_valid_template(hass):
    """Test template validation passes for valid template."""
    # Setup entity in hass
    hass.states.async_set("light.kitchen", "on")

    validator = JinjaValidator(hass)

    automation = {
        "id": "test_valid",
        "alias": "Test Valid",
        "condition": {
            "condition": "template",
            "value_template": "{{ is_state('light.kitchen', 'on') }}"
        }
    }

    issues = validator.validate_automations([automation])

    # Should have no issues
    assert len(issues) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_template_validation_end_to_end tests/test_jinja_validator.py::test_template_validation_passes_for_valid_template -v`

Expected: FAIL (semantic validation not integrated yet)

**Step 3: Modify implementation**

In `custom_components/autodoctor/jinja_validator.py`, modify the `_check_template` method (around line 503-546):

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

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_template_validation_end_to_end tests/test_jinja_validator.py::test_template_validation_passes_for_valid_template -v`

Expected: PASS (2 tests)

**Step 5: Run all jinja_validator tests**

Run: `pytest tests/test_jinja_validator.py -v`

Expected: ALL PASS

**Step 6: Commit**

```bash
git add tests/test_jinja_validator.py custom_components/autodoctor/jinja_validator.py
git commit -m "feat(jinja): integrate semantic validation into template checking"
```

---

## Task 14: Run Full Test Suite and Update Index

**Files:**
- Test: all test files
- Modify: `index.md`

**Step 1: Run full test suite**

Run: `pytest tests/ -v`

Expected: ALL PASS

**Step 2: Update index.md**

Read current `index.md` to understand structure.

Run: `cat index.md`

**Step 3: Update Validation Rules section**

Update the "Validation Rules" section in `index.md` to reflect new capabilities:

```markdown
## Validation Rules

| Check | Severity |
|-------|----------|
| Entity doesn't exist | ERROR |
| State never valid | ERROR |
| Case mismatch | WARNING |
| Attribute doesn't exist | ERROR |
| Template syntax error | ERROR |
| Template entity not found | ERROR |
| Template invalid state | ERROR |
| Template attribute not found | ERROR |
| Template device/area/zone not found | ERROR |
| Unknown template filter | WARNING |
| Unknown template test | WARNING |

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
```

**Step 4: Commit**

```bash
git add index.md
git commit -m "docs: update index.md with comprehensive trigger/condition coverage"
```

**Step 5: Final verification**

Run: `pytest tests/ -v --cov=custom_components/autodoctor --cov-report=term-missing`

Expected: ALL PASS with coverage > 90%

---

## Completion

All tasks complete! The implementation adds:

1. ✅ 14 new trigger type handlers (zone, sun, calendar, device, tag, geo_location, event, mqtt, webhook, persistent_notification, time)
2. ✅ 5 new condition type handlers (numeric_state, zone, sun, time, device)
3. ✅ Enhanced numeric_state trigger with attribute validation
4. ✅ 6 new issue types for Jinja2 semantic errors
5. ✅ Entity reference extraction in JinjaValidator
6. ✅ Semantic validation for entity existence, state values, and attributes
7. ✅ Integration of semantic validation into template checking
8. ✅ Updated documentation

**Verification Commands:**
- `pytest tests/ -v` - All tests pass
- `pytest tests/test_analyzer.py -v` - Trigger/condition tests pass
- `pytest tests/test_jinja_validator.py -v` - Semantic validation tests pass

**Next Steps:**
- Use @superpowers:finishing-a-development-branch to complete this work
- Run final verification and create PR
