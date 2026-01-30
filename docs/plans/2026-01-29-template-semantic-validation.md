# Template Semantic Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deep semantic validation to Jinja2 templates: filter/test argument validation, variable existence checking, and entity ID format validation.

**Architecture:** Data-driven signature registry in new `template_semantics.py` module, enhanced `_check_ast_semantics()` in `jinja_validator.py` for single-pass validation, all issues reported as warnings.

**Tech Stack:** Python 3.12+, Jinja2 AST, pytest, dataclasses

---

## Task 1: Add New IssueTypes

**Files:**
- Modify: `custom_components/autodoctor/models.py:18-28`

**Step 1: Read existing IssueType enum**

Read `custom_components/autodoctor/models.py` to see current enum structure.

**Step 2: Add new issue types**

Add after line 28 (after `TEMPLATE_UNKNOWN_TEST`):

```python
TEMPLATE_INVALID_ARGUMENTS = "template_invalid_arguments"
TEMPLATE_UNKNOWN_VARIABLE = "template_unknown_variable"
TEMPLATE_INVALID_ENTITY_ID = "template_invalid_entity_id"
```

**Step 3: Verify syntax**

Run: `python -m py_compile custom_components/autodoctor/models.py`
Expected: No output (successful compilation)

**Step 4: Commit**

```bash
git add custom_components/autodoctor/models.py
git commit -m "feat(models): add semantic validation issue types"
```

---

## Task 2: Create Template Semantics Module - Data Structures

**Files:**
- Create: `custom_components/autodoctor/template_semantics.py`
- Test: `tests/test_template_semantics.py`

**Step 1: Write test for ArgSpec dataclass**

Create `tests/test_template_semantics.py`:

```python
"""Tests for template_semantics module."""

from custom_components.autodoctor.template_semantics import ArgSpec, Signature


def test_argspec_creation():
    """Test ArgSpec dataclass creation."""
    arg = ArgSpec(name="default", required=False)
    assert arg.name == "default"
    assert arg.required is False


def test_argspec_required():
    """Test required ArgSpec."""
    arg = ArgSpec(name="amount", required=True)
    assert arg.name == "amount"
    assert arg.required is True


def test_signature_creation():
    """Test Signature dataclass creation."""
    sig = Signature(
        name="multiply",
        min_args=1,
        max_args=2,
        arg_specs=(ArgSpec("amount", True), ArgSpec("default", False)),
    )
    assert sig.name == "multiply"
    assert sig.min_args == 1
    assert sig.max_args == 2
    assert len(sig.arg_specs) == 2


def test_signature_unlimited_args():
    """Test Signature with unlimited max args."""
    sig = Signature(name="join", min_args=0, max_args=None)
    assert sig.max_args is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_template_semantics.py -v`
Expected: FAIL - module doesn't exist

**Step 3: Create minimal template_semantics.py**

Create `custom_components/autodoctor/template_semantics.py`:

```python
"""Template semantics registry for Jinja2 validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArgSpec:
    """Specification for a single argument."""

    name: str
    required: bool


@dataclass(frozen=True)
class Signature:
    """Signature for a filter or test."""

    name: str
    min_args: int
    max_args: int | None  # None = unlimited
    arg_specs: tuple[ArgSpec, ...] = ()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_template_semantics.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add custom_components/autodoctor/template_semantics.py tests/test_template_semantics.py
git commit -m "feat(semantics): add ArgSpec and Signature dataclasses"
```

---

## Task 3: Create Filter Signature Registry

**Files:**
- Modify: `custom_components/autodoctor/template_semantics.py`
- Modify: `tests/test_template_semantics.py`

**Step 1: Write tests for filter signature lookups**

Add to `tests/test_template_semantics.py`:

```python
from custom_components.autodoctor.template_semantics import FILTER_SIGNATURES


def test_filter_signatures_exist():
    """Test that filter signatures dictionary exists."""
    assert isinstance(FILTER_SIGNATURES, dict)
    assert len(FILTER_SIGNATURES) > 0


def test_multiply_filter_signature():
    """Test multiply filter signature."""
    sig = FILTER_SIGNATURES["multiply"]
    assert sig.name == "multiply"
    assert sig.min_args == 1
    assert sig.max_args == 2


def test_iif_filter_signature():
    """Test iif filter signature."""
    sig = FILTER_SIGNATURES["iif"]
    assert sig.name == "iif"
    assert sig.min_args == 1
    assert sig.max_args == 3


def test_float_filter_signature():
    """Test float filter with optional default."""
    sig = FILTER_SIGNATURES["float"]
    assert sig.min_args == 0
    assert sig.max_args == 1


def test_regex_match_filter_signature():
    """Test regex_match filter signature."""
    sig = FILTER_SIGNATURES["regex_match"]
    assert sig.min_args == 1
    assert sig.max_args == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_template_semantics.py::test_filter_signatures_exist -v`
Expected: FAIL - FILTER_SIGNATURES doesn't exist

**Step 3: Add filter signature registry**

Add to `custom_components/autodoctor/template_semantics.py` after dataclasses:

```python
# Filter signatures for Home Assistant template filters
FILTER_SIGNATURES: dict[str, Signature] = {
    # Type conversion
    "float": Signature("float", 0, 1, (ArgSpec("default", False),)),
    "int": Signature(
        "int", 0, 2, (ArgSpec("default", False), ArgSpec("base", False))
    ),
    "bool": Signature("bool", 0, 1, (ArgSpec("default", False),)),
    # Arithmetic
    "multiply": Signature(
        "multiply", 1, 2, (ArgSpec("amount", True), ArgSpec("default", False))
    ),
    "add": Signature("add", 1, 2, (ArgSpec("amount", True), ArgSpec("default", False))),
    "round": Signature(
        "round",
        0,
        3,
        (
            ArgSpec("precision", False),
            ArgSpec("method", False),
            ArgSpec("default", False),
        ),
    ),
    # Math functions
    "log": Signature("log", 0, 2, (ArgSpec("base", False), ArgSpec("default", False))),
    "sin": Signature("sin", 0, 0),
    "cos": Signature("cos", 0, 0),
    "tan": Signature("tan", 0, 0),
    "sqrt": Signature("sqrt", 0, 1, (ArgSpec("default", False),)),
    "clamp": Signature(
        "clamp",
        2,
        3,
        (ArgSpec("min", True), ArgSpec("max", True), ArgSpec("default", False)),
    ),
    # Statistical
    "average": Signature("average", 0, 0),
    "median": Signature("median", 0, 0),
    "statistical_mode": Signature("statistical_mode", 0, 0),
    # Conditional
    "iif": Signature(
        "iif",
        1,
        3,
        (ArgSpec("if_true", False), ArgSpec("if_false", False), ArgSpec("if_none", False)),
    ),
    # JSON
    "to_json": Signature(
        "to_json",
        0,
        3,
        (
            ArgSpec("ensure_ascii", False),
            ArgSpec("pretty_print", False),
            ArgSpec("sort_keys", False),
        ),
    ),
    "from_json": Signature("from_json", 0, 1, (ArgSpec("default", False),)),
    # Regex
    "regex_match": Signature(
        "regex_match", 1, 2, (ArgSpec("pattern", True), ArgSpec("ignorecase", False))
    ),
    "regex_search": Signature(
        "regex_search", 1, 2, (ArgSpec("pattern", True), ArgSpec("ignorecase", False))
    ),
    "regex_replace": Signature(
        "regex_replace",
        2,
        3,
        (ArgSpec("find", True), ArgSpec("replace", True), ArgSpec("ignorecase", False)),
    ),
    "regex_findall": Signature("regex_findall", 1, 1, (ArgSpec("pattern", True),)),
    "regex_findall_index": Signature(
        "regex_findall_index", 1, 2, (ArgSpec("pattern", True), ArgSpec("index", False))
    ),
    # Encoding
    "base64_encode": Signature("base64_encode", 0, 0),
    "base64_decode": Signature("base64_decode", 0, 0),
    # Hashing
    "md5": Signature("md5", 0, 0),
    "sha1": Signature("sha1", 0, 0),
    "sha256": Signature("sha256", 0, 0),
    "sha512": Signature("sha512", 0, 0),
    # String
    "slugify": Signature("slugify", 0, 0),
    # Timestamp
    "as_timestamp": Signature("as_timestamp", 0, 0),
    "as_datetime": Signature("as_datetime", 0, 0),
    "as_local": Signature("as_local", 0, 0),
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_template_semantics.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add custom_components/autodoctor/template_semantics.py tests/test_template_semantics.py
git commit -m "feat(semantics): add filter signature registry"
```

---

## Task 4: Create Test Signature Registry

**Files:**
- Modify: `custom_components/autodoctor/template_semantics.py`
- Modify: `tests/test_template_semantics.py`

**Step 1: Write tests for test signature lookups**

Add to `tests/test_template_semantics.py`:

```python
from custom_components.autodoctor.template_semantics import TEST_SIGNATURES


def test_test_signatures_exist():
    """Test that test signatures dictionary exists."""
    assert isinstance(TEST_SIGNATURES, dict)
    assert len(TEST_SIGNATURES) > 0


def test_is_state_test_signature():
    """Test is_state test signature."""
    sig = TEST_SIGNATURES["is_state"]
    assert sig.name == "is_state"
    assert sig.min_args == 2
    assert sig.max_args == 2


def test_has_value_test_signature():
    """Test has_value test signature."""
    sig = TEST_SIGNATURES["has_value"]
    assert sig.min_args == 1
    assert sig.max_args == 1


def test_contains_test_signature():
    """Test contains test signature."""
    sig = TEST_SIGNATURES["contains"]
    assert sig.min_args == 1
    assert sig.max_args == 1
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_template_semantics.py::test_test_signatures_exist -v`
Expected: FAIL - TEST_SIGNATURES doesn't exist

**Step 3: Add test signature registry**

Add to `custom_components/autodoctor/template_semantics.py` after FILTER_SIGNATURES:

```python
# Test signatures for Home Assistant template tests
TEST_SIGNATURES: dict[str, Signature] = {
    "is_state": Signature(
        "is_state", 2, 2, (ArgSpec("entity_id", True), ArgSpec("state", True))
    ),
    "is_state_attr": Signature(
        "is_state_attr",
        3,
        3,
        (ArgSpec("entity_id", True), ArgSpec("name", True), ArgSpec("value", True)),
    ),
    "has_value": Signature("has_value", 1, 1, (ArgSpec("entity_id", True),)),
    "is_hidden_entity": Signature(
        "is_hidden_entity", 1, 1, (ArgSpec("entity_id", True),)
    ),
    "contains": Signature("contains", 1, 1, (ArgSpec("value", True),)),
    "match": Signature("match", 1, 1, (ArgSpec("pattern", True),)),
    "search": Signature("search", 1, 1, (ArgSpec("pattern", True),)),
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_template_semantics.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add custom_components/autodoctor/template_semantics.py tests/test_template_semantics.py
git commit -m "feat(semantics): add test signature registry"
```

---

## Task 5: Create Global Variables and Entity ID Pattern

**Files:**
- Modify: `custom_components/autodoctor/template_semantics.py`
- Modify: `tests/test_template_semantics.py`

**Step 1: Write tests for globals and pattern**

Add to `tests/test_template_semantics.py`:

```python
import re
from custom_components.autodoctor.template_semantics import (
    KNOWN_GLOBALS,
    ENTITY_ID_PATTERN,
    ENTITY_ID_FUNCTIONS,
)


def test_known_globals_contains_states():
    """Test KNOWN_GLOBALS contains common functions."""
    assert "states" in KNOWN_GLOBALS
    assert "now" in KNOWN_GLOBALS
    assert "utcnow" in KNOWN_GLOBALS
    assert "state_attr" in KNOWN_GLOBALS


def test_entity_id_pattern_valid():
    """Test ENTITY_ID_PATTERN matches valid entity IDs."""
    assert ENTITY_ID_PATTERN.match("sensor.temperature")
    assert ENTITY_ID_PATTERN.match("light.living_room")
    assert ENTITY_ID_PATTERN.match("binary_sensor.motion_1")
    assert ENTITY_ID_PATTERN.match("switch.device_123")


def test_entity_id_pattern_invalid():
    """Test ENTITY_ID_PATTERN rejects invalid entity IDs."""
    assert not ENTITY_ID_PATTERN.match("sensor")  # Missing object_id
    assert not ENTITY_ID_PATTERN.match("sensor.")  # Empty object_id
    assert not ENTITY_ID_PATTERN.match("SENSOR.temp")  # Uppercase
    assert not ENTITY_ID_PATTERN.match("sensor.temp-sensor")  # Hyphen
    assert not ENTITY_ID_PATTERN.match("sensor temp")  # Space


def test_entity_id_functions_exist():
    """Test ENTITY_ID_FUNCTIONS dictionary exists."""
    assert isinstance(ENTITY_ID_FUNCTIONS, dict)
    assert "states" in ENTITY_ID_FUNCTIONS
    assert "is_state" in ENTITY_ID_FUNCTIONS
    assert ENTITY_ID_FUNCTIONS["states"] == 0  # entity_id is arg 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_template_semantics.py::test_known_globals_contains_states -v`
Expected: FAIL - KNOWN_GLOBALS doesn't exist

**Step 3: Add globals and patterns**

Add to `custom_components/autodoctor/template_semantics.py` after TEST_SIGNATURES:

```python
import re

# Known global variables available in Home Assistant templates
KNOWN_GLOBALS: frozenset[str] = frozenset({
    # State access
    "states",
    "now",
    "utcnow",
    "as_timestamp",
    "state_attr",
    "state_translated",
    "is_state",
    "is_state_attr",
    # Entity operations
    "expand",
    "closest",
    "distance",
    "has_value",
    "is_hidden_entity",
    # Device queries
    "device_entities",
    "device_attr",
    "is_device_attr",
    "device_id",
    "device_name",
    "config_entry_id",
    "config_entry_attr",
    # Area queries
    "area_entities",
    "area_id",
    "area_name",
    "area_devices",
    # Floor queries
    "floor_entities",
    "floor_id",
    "floor_name",
    "floor_areas",
    # Label queries
    "label_entities",
    "label_id",
    "label_name",
    "label_description",
    "label_areas",
    "label_devices",
    # Other
    "integration_entities",
})

# Pattern for valid entity IDs: domain.object_id
ENTITY_ID_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")

# Functions that take entity_id as argument (maps function name to arg index)
ENTITY_ID_FUNCTIONS: dict[str, int] = {
    "states": 0,
    "state_attr": 0,
    "is_state": 0,
    "is_state_attr": 0,
    "has_value": 0,
    "is_hidden_entity": 0,
    "device_id": 0,
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_template_semantics.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add custom_components/autodoctor/template_semantics.py tests/test_template_semantics.py
git commit -m "feat(semantics): add global variables and entity ID pattern"
```

---

## Task 6: Implement Filter Argument Validation

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Modify: `tests/test_jinja_validator.py`

**Step 1: Write failing test for filter argument validation**

Add to `tests/test_jinja_validator.py`:

```python
def test_multiply_filter_missing_required_arg():
    """Test multiply filter without required amount argument."""
    validator = JinjaValidator()
    automation = {
        "id": "multiply_test",
        "alias": "Multiply Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ 5 | multiply }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS
    assert "multiply" in issues[0].message
    assert "0" in issues[0].message or "1" in issues[0].message


def test_multiply_filter_correct_args():
    """Test multiply filter with correct arguments."""
    validator = JinjaValidator()
    automation = {
        "id": "multiply_ok",
        "alias": "Multiply OK",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ 5 | multiply(2) }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_iif_filter_too_many_args():
    """Test iif filter with too many arguments."""
    validator = JinjaValidator()
    automation = {
        "id": "iif_test",
        "alias": "IIF Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ true | iif(1, 2, 3, 4) }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS
    assert "iif" in issues[0].message


def test_float_filter_optional_arg():
    """Test float filter with and without optional default."""
    validator = JinjaValidator()
    # Without default
    automation1 = {
        "id": "float_no_default",
        "alias": "Float No Default",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ value | float }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues1 = validator.validate_automations([automation1])
    assert len(issues1) == 0

    # With default
    automation2 = {
        "id": "float_with_default",
        "alias": "Float With Default",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ value | float(0) }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues2 = validator.validate_automations([automation2])
    assert len(issues2) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_multiply_filter_missing_required_arg -v`
Expected: FAIL - validation not implemented yet

**Step 3: Add filter validation method to JinjaValidator**

Add import at top of `custom_components/autodoctor/jinja_validator.py`:

```python
from .template_semantics import FILTER_SIGNATURES, TEST_SIGNATURES
```

Add new method to `JinjaValidator` class (after `_check_ast_semantics`):

```python
def _validate_filter_args(
    self,
    node: nodes.Filter,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate filter argument count."""
    sig = FILTER_SIGNATURES.get(node.name)
    if not sig:
        return []  # Unknown filter already handled elsewhere

    # Count arguments - args can be None or a list
    arg_count = len(node.args) if node.args else 0

    if arg_count < sig.min_args or (sig.max_args is not None and arg_count > sig.max_args):
        if sig.max_args is None:
            expected = f"{sig.min_args}+"
        elif sig.min_args == sig.max_args:
            expected = str(sig.min_args)
        else:
            expected = f"{sig.min_args}-{sig.max_args}"

        return [
            ValidationIssue(
                issue_type=IssueType.TEMPLATE_INVALID_ARGUMENTS,
                severity=Severity.WARNING,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id="",
                location=location,
                message=f"Filter '{node.name}' expects {expected} arguments, got {arg_count}",
            )
        ]
    return []
```

**Step 4: Call validation in _check_ast_semantics**

Modify `_check_ast_semantics` method to validate filters:

```python
def _check_ast_semantics(
    self,
    ast: nodes.Template,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Walk the parsed AST to check for unknown filters and tests."""
    issues: list[ValidationIssue] = []

    for node in ast.find_all(nodes.Filter):
        if node.name not in self._known_filters:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_FILTER,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown filter '{node.name}' — not a built-in Jinja2 or Home Assistant filter",
                )
            )
        else:
            # Validate arguments for known filters
            issues.extend(self._validate_filter_args(node, location, auto_id, auto_name))

    for node in ast.find_all(nodes.Test):
        if node.name not in self._known_tests:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_TEST,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown test '{node.name}' — not a built-in Jinja2 or Home Assistant test",
                )
            )

    return issues
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_multiply_filter_missing_required_arg -v`
Expected: PASS

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "feat(jinja): add filter argument validation"
```

---

## Task 7: Implement Test Argument Validation

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Modify: `tests/test_jinja_validator.py`

**Step 1: Write failing test for test argument validation**

Add to `tests/test_jinja_validator.py`:

```python
def test_is_state_test_missing_args():
    """Test is_state test without required arguments."""
    validator = JinjaValidator()
    automation = {
        "id": "is_state_test",
        "alias": "Is State Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{% if sensor.temp is is_state %}true{% endif %}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS
    assert "is_state" in issues[0].message


def test_is_state_test_correct_args():
    """Test is_state test with correct arguments."""
    validator = JinjaValidator()
    automation = {
        "id": "is_state_ok",
        "alias": "Is State OK",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{% if sensor.temp is is_state('sensor.temp', 'on') %}true{% endif %}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_has_value_test_too_many_args():
    """Test has_value test with too many arguments."""
    validator = JinjaValidator()
    automation = {
        "id": "has_value_test",
        "alias": "Has Value Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{% if x is has_value('sensor.temp', 'extra') %}true{% endif %}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS
    assert "has_value" in issues[0].message
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_is_state_test_missing_args -v`
Expected: FAIL - test validation not implemented yet

**Step 3: Add test validation method**

Add new method to `JinjaValidator` class (after `_validate_filter_args`):

```python
def _validate_test_args(
    self,
    node: nodes.Test,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate test argument count."""
    sig = TEST_SIGNATURES.get(node.name)
    if not sig:
        return []  # Unknown test already handled elsewhere

    # Count arguments - args can be None or a list
    arg_count = len(node.args) if node.args else 0

    if arg_count < sig.min_args or (sig.max_args is not None and arg_count > sig.max_args):
        if sig.max_args is None:
            expected = f"{sig.min_args}+"
        elif sig.min_args == sig.max_args:
            expected = str(sig.min_args)
        else:
            expected = f"{sig.min_args}-{sig.max_args}"

        return [
            ValidationIssue(
                issue_type=IssueType.TEMPLATE_INVALID_ARGUMENTS,
                severity=Severity.WARNING,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id="",
                location=location,
                message=f"Test '{node.name}' expects {expected} arguments, got {arg_count}",
            )
        ]
    return []
```

**Step 4: Call validation in _check_ast_semantics**

Modify the test validation section in `_check_ast_semantics`:

```python
    for node in ast.find_all(nodes.Test):
        if node.name not in self._known_tests:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_TEST,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown test '{node.name}' — not a built-in Jinja2 or Home Assistant test",
                )
            )
        else:
            # Validate arguments for known tests
            issues.extend(self._validate_test_args(node, location, auto_id, auto_name))
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_is_state_test_missing_args -v`
Expected: PASS

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "feat(jinja): add test argument validation"
```

---

## Task 8: Implement Entity ID Format Validation

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Modify: `tests/test_jinja_validator.py`

**Step 1: Write failing tests for entity ID validation**

Add to `tests/test_jinja_validator.py`:

```python
def test_states_function_invalid_entity_id_format():
    """Test states() with invalid entity_id format."""
    validator = JinjaValidator()
    automation = {
        "id": "invalid_entity",
        "alias": "Invalid Entity",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor_temp') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_ENTITY_ID
    assert "sensor_temp" in issues[0].message


def test_states_function_valid_entity_id():
    """Test states() with valid entity_id."""
    validator = JinjaValidator()
    automation = {
        "id": "valid_entity",
        "alias": "Valid Entity",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temperature') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_entity_id_uppercase_rejected():
    """Test that uppercase entity IDs are rejected."""
    validator = JinjaValidator()
    automation = {
        "id": "uppercase_entity",
        "alias": "Uppercase Entity",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('SENSOR.temp') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_INVALID_ENTITY_ID


def test_entity_id_variable_not_validated():
    """Test that entity_id variables are not validated."""
    validator = JinjaValidator()
    automation = {
        "id": "entity_var",
        "alias": "Entity Var",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states(entity_id) }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    # Should only warn about undefined variable, not entity ID format
    assert all(i.issue_type != IssueType.TEMPLATE_INVALID_ENTITY_ID for i in issues)


def test_is_state_function_entity_id_validation():
    """Test is_state() function validates entity_id."""
    validator = JinjaValidator()
    automation = {
        "id": "is_state_invalid",
        "alias": "Is State Invalid",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{{ is_state('sensor', 'on') }}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert any(i.issue_type == IssueType.TEMPLATE_INVALID_ENTITY_ID for i in issues)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_states_function_invalid_entity_id_format -v`
Expected: FAIL - entity ID validation not implemented

**Step 3: Add entity ID validation method**

Add import at top of `custom_components/autodoctor/jinja_validator.py`:

```python
from .template_semantics import (
    ENTITY_ID_FUNCTIONS,
    ENTITY_ID_PATTERN,
    FILTER_SIGNATURES,
    TEST_SIGNATURES,
)
```

Add new method to `JinjaValidator` class (after `_validate_test_args`):

```python
def _validate_entity_id_call(
    self,
    node: nodes.Call,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate entity_id format in function calls."""
    # Check if this is a function call we track
    if not isinstance(node.node, nodes.Name):
        return []

    func_name = node.node.name
    arg_index = ENTITY_ID_FUNCTIONS.get(func_name)
    if arg_index is None:
        return []

    # Extract argument at specified index
    if not node.args or len(node.args) <= arg_index:
        return []

    arg = node.args[arg_index]

    # Only validate string literals, not variables or expressions
    if not isinstance(arg, nodes.Const) or not isinstance(arg.value, str):
        return []

    entity_id = arg.value
    if not ENTITY_ID_PATTERN.match(entity_id):
        return [
            ValidationIssue(
                issue_type=IssueType.TEMPLATE_INVALID_ENTITY_ID,
                severity=Severity.WARNING,
                automation_id=auto_id,
                automation_name=auto_name,
                entity_id=entity_id,
                location=location,
                message=f"Invalid entity_id format: '{entity_id}' (expected 'domain.object_id')",
            )
        ]
    return []
```

**Step 4: Call validation in _check_ast_semantics**

Modify `_check_ast_semantics` to add Call node validation:

```python
def _check_ast_semantics(
    self,
    ast: nodes.Template,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Walk the parsed AST to check for semantic issues."""
    issues: list[ValidationIssue] = []

    for node in ast.find_all(nodes.Filter):
        if node.name not in self._known_filters:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_FILTER,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown filter '{node.name}' — not a built-in Jinja2 or Home Assistant filter",
                )
            )
        else:
            issues.extend(self._validate_filter_args(node, location, auto_id, auto_name))

    for node in ast.find_all(nodes.Test):
        if node.name not in self._known_tests:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_TEST,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown test '{node.name}' — not a built-in Jinja2 or Home Assistant test",
                )
            )
        else:
            issues.extend(self._validate_test_args(node, location, auto_id, auto_name))

    # Validate entity IDs in function calls
    for node in ast.find_all(nodes.Call):
        issues.extend(self._validate_entity_id_call(node, location, auto_id, auto_name))

    return issues
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_states_function_invalid_entity_id_format -v`
Expected: PASS

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "feat(jinja): add entity ID format validation"
```

---

## Task 9: Implement Variable Existence Validation

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Modify: `tests/test_jinja_validator.py`

**Step 1: Write failing tests for variable validation**

Add to `tests/test_jinja_validator.py`:

```python
def test_undefined_variable_warns():
    """Test that undefined variables produce warnings."""
    validator = JinjaValidator()
    automation = {
        "id": "undefined_var",
        "alias": "Undefined Var",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ unknown_variable }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_UNKNOWN_VARIABLE
    assert "unknown_variable" in issues[0].message


def test_known_global_variables_pass():
    """Test that known global variables don't produce warnings."""
    validator = JinjaValidator()
    templates = [
        "{{ states('sensor.temp') }}",
        "{{ now() }}",
        "{{ utcnow() }}",
        "{{ state_attr('sensor.temp', 'unit') }}",
    ]
    for tmpl in templates:
        automation = {
            "id": "global_test",
            "alias": "Global Test",
            "triggers": [
                {
                    "platform": "template",
                    "value_template": tmpl,
                }
            ],
            "conditions": [],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert all(i.issue_type != IssueType.TEMPLATE_UNKNOWN_VARIABLE for i in issues), \
            f"Unexpected variable warning for: {tmpl}"


def test_set_variable_in_scope():
    """Test that {% set %} variables are in scope."""
    validator = JinjaValidator()
    automation = {
        "id": "set_var",
        "alias": "Set Var",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "data": {
                    "message": "{% set my_var = 42 %}{{ my_var }}",
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert all(i.issue_type != IssueType.TEMPLATE_UNKNOWN_VARIABLE for i in issues)


def test_for_loop_variable_in_scope():
    """Test that loop variables are in scope."""
    validator = JinjaValidator()
    automation = {
        "id": "loop_var",
        "alias": "Loop Var",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "data": {
                    "message": "{% for item in items %}{{ item }}{% endfor %}",
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    # Should not warn about 'item' being undefined
    assert all(
        i.issue_type != IssueType.TEMPLATE_UNKNOWN_VARIABLE or "item" not in i.message
        for i in issues
    )


def test_special_context_variables_allowed():
    """Test that special context variables are allowed."""
    validator = JinjaValidator()
    templates = [
        "{{ trigger.platform }}",
        "{{ this.state }}",
        "{{ repeat.index }}",
    ]
    for tmpl in templates:
        automation = {
            "id": "context_test",
            "alias": "Context Test",
            "triggers": [
                {
                    "platform": "template",
                    "value_template": tmpl,
                }
            ],
            "conditions": [],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert all(i.issue_type != IssueType.TEMPLATE_UNKNOWN_VARIABLE for i in issues), \
            f"Unexpected variable warning for: {tmpl}"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_undefined_variable_warns -v`
Expected: FAIL - variable validation not implemented

**Step 3: Add import for KNOWN_GLOBALS**

Update import in `custom_components/autodoctor/jinja_validator.py`:

```python
from .template_semantics import (
    ENTITY_ID_FUNCTIONS,
    ENTITY_ID_PATTERN,
    FILTER_SIGNATURES,
    KNOWN_GLOBALS,
    TEST_SIGNATURES,
)
```

**Step 4: Add variable validation method**

Add new method to `JinjaValidator` class (after `_validate_entity_id_call`):

```python
def _validate_variable(
    self,
    node: nodes.Name,
    known_vars: set[str],
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate variable reference."""
    # Skip special context variables
    if node.name in ("trigger", "this", "repeat"):
        return []

    # Skip if variable is known
    if node.name in known_vars:
        return []

    return [
        ValidationIssue(
            issue_type=IssueType.TEMPLATE_UNKNOWN_VARIABLE,
            severity=Severity.WARNING,
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id="",
            location=location,
            message=f"Undefined variable '{node.name}'",
        )
    ]
```

**Step 5: Add scope tracking helper**

Add new method to `JinjaValidator` class (after `_validate_variable`):

```python
def _collect_template_variables(self, ast: nodes.Template) -> set[str]:
    """Collect all variables defined in the template."""
    defined_vars = set()

    # Collect from {% set var = ... %}
    for node in ast.find_all(nodes.Assign):
        if isinstance(node.target, nodes.Name):
            defined_vars.add(node.target.name)

    # Collect from {% for var in ... %}
    for node in ast.find_all(nodes.For):
        if isinstance(node.target, nodes.Name):
            defined_vars.add(node.target.name)

    return defined_vars
```

**Step 6: Update _check_ast_semantics to validate variables**

Modify `_check_ast_semantics` to add variable validation:

```python
def _check_ast_semantics(
    self,
    ast: nodes.Template,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Walk the parsed AST to check for semantic issues."""
    issues: list[ValidationIssue] = []

    # Collect template-defined variables
    template_vars = self._collect_template_variables(ast)
    known_vars = KNOWN_GLOBALS | template_vars

    for node in ast.find_all(nodes.Filter):
        if node.name not in self._known_filters:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_FILTER,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown filter '{node.name}' — not a built-in Jinja2 or Home Assistant filter",
                )
            )
        else:
            issues.extend(self._validate_filter_args(node, location, auto_id, auto_name))

    for node in ast.find_all(nodes.Test):
        if node.name not in self._known_tests:
            issues.append(
                ValidationIssue(
                    issue_type=IssueType.TEMPLATE_UNKNOWN_TEST,
                    severity=Severity.WARNING,
                    automation_id=auto_id,
                    automation_name=auto_name,
                    entity_id="",
                    location=location,
                    message=f"Unknown test '{node.name}' — not a built-in Jinja2 or Home Assistant test",
                )
            )
        else:
            issues.extend(self._validate_test_args(node, location, auto_id, auto_name))

    # Validate entity IDs in function calls
    for node in ast.find_all(nodes.Call):
        issues.extend(self._validate_entity_id_call(node, location, auto_id, auto_name))

    # Validate variable references
    for node in ast.find_all(nodes.Name):
        # Only validate Name nodes in 'load' context (reading variables)
        if node.ctx == "load":
            issues.extend(self._validate_variable(node, known_vars, location, auto_id, auto_name))

    return issues
```

**Step 7: Run tests to verify they pass**

Run: `pytest tests/test_jinja_validator.py::test_undefined_variable_warns -v`
Expected: PASS

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All tests pass

**Step 8: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "feat(jinja): add variable existence validation"
```

---

## Task 10: Add Comprehensive Edge Case Tests

**Files:**
- Modify: `tests/test_jinja_validator.py`

**Step 1: Add edge case tests**

Add to `tests/test_jinja_validator.py`:

```python
def test_chained_filters_each_validated():
    """Test that each filter in a chain is validated."""
    validator = JinjaValidator()
    automation = {
        "id": "chained_filters",
        "alias": "Chained Filters",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ value | float | multiply }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    # Should warn about multiply missing required arg
    assert any(
        i.issue_type == IssueType.TEMPLATE_INVALID_ARGUMENTS and "multiply" in i.message
        for i in issues
    )


def test_multiple_issues_in_one_template():
    """Test that multiple issues are all reported."""
    validator = JinjaValidator()
    automation = {
        "id": "multi_issue",
        "alias": "Multi Issue",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ unknown_var | multiply | states('SENSOR') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    # Should have: undefined variable, invalid multiply args, invalid entity_id
    assert len(issues) >= 3


def test_regex_match_filter_with_pattern():
    """Test regex_match filter with pattern argument."""
    validator = JinjaValidator()
    automation = {
        "id": "regex_test",
        "alias": "Regex Test",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ value | regex_match('\\\\d+') }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert all(i.issue_type != IssueType.TEMPLATE_INVALID_ARGUMENTS for i in issues)


def test_nested_templates_in_choose():
    """Test that templates in choose blocks are validated."""
    validator = JinjaValidator()
    automation = {
        "id": "choose_test",
        "alias": "Choose Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "template",
                                "value_template": "{{ states('sensor_temp') }}",
                            }
                        ],
                        "sequence": [],
                    }
                ]
            }
        ],
    }
    issues = validator.validate_automations([automation])
    # Should detect invalid entity_id format
    assert any(i.issue_type == IssueType.TEMPLATE_INVALID_ENTITY_ID for i in issues)


def test_jinja_builtin_variables_accepted():
    """Test that Jinja built-in variables don't cause warnings."""
    validator = JinjaValidator()
    automation = {
        "id": "builtin_vars",
        "alias": "Builtin Vars",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "data": {
                    "message": "{% for i in range(10) %}{{ loop.index }}{% endfor %}",
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    # Should not warn about 'loop' or 'range'
    assert all(
        i.issue_type != IssueType.TEMPLATE_UNKNOWN_VARIABLE
        or ("loop" not in i.message and "range" not in i.message)
        for i in issues
    )
```

**Step 2: Add Jinja builtins to KNOWN_GLOBALS**

Modify `custom_components/autodoctor/template_semantics.py` to add Jinja builtins to KNOWN_GLOBALS:

```python
# Known global variables available in Home Assistant templates
KNOWN_GLOBALS: frozenset[str] = frozenset({
    # State access
    "states",
    "now",
    "utcnow",
    "as_timestamp",
    "state_attr",
    "state_translated",
    "is_state",
    "is_state_attr",
    # Entity operations
    "expand",
    "closest",
    "distance",
    "has_value",
    "is_hidden_entity",
    # Device queries
    "device_entities",
    "device_attr",
    "is_device_attr",
    "device_id",
    "device_name",
    "config_entry_id",
    "config_entry_attr",
    # Area queries
    "area_entities",
    "area_id",
    "area_name",
    "area_devices",
    # Floor queries
    "floor_entities",
    "floor_id",
    "floor_name",
    "floor_areas",
    # Label queries
    "label_entities",
    "label_id",
    "label_name",
    "label_description",
    "label_areas",
    "label_devices",
    # Other
    "integration_entities",
    # Jinja2 built-ins
    "range",
    "dict",
    "list",
    "set",
    "tuple",
    "zip",
    "loop",  # Available in for loops
})
```

**Step 3: Run all tests**

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add custom_components/autodoctor/template_semantics.py tests/test_jinja_validator.py
git commit -m "test(jinja): add comprehensive edge case tests"
```

---

## Task 11: Run Full Test Suite and Verify

**Files:**
- All test files

**Step 1: Run all jinja validator tests**

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All tests pass

**Step 2: Run all template semantics tests**

Run: `pytest tests/test_template_semantics.py -v`
Expected: All tests pass

**Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass, no regressions

**Step 4: Check test coverage**

Run: `pytest tests/test_jinja_validator.py tests/test_template_semantics.py --cov=custom_components/autodoctor/jinja_validator --cov=custom_components/autodoctor/template_semantics --cov-report=term-missing`
Expected: >80% coverage on new code

**Step 5: Verify no regressions**

Ensure all existing tests still pass and no new failures introduced.

---

## Task 12: Update Documentation

**Files:**
- Modify: `index.md` (if structural changes made)

**Step 1: Check if index.md needs updating**

Read `index.md` and determine if new IssueTypes or modules need to be documented.

**Step 2: Update index.md if needed**

If index.md documents validation capabilities or IssueTypes, update it to include:
- New IssueTypes: TEMPLATE_INVALID_ARGUMENTS, TEMPLATE_UNKNOWN_VARIABLE, TEMPLATE_INVALID_ENTITY_ID
- New module: template_semantics.py

**Step 3: Commit documentation**

If updated:
```bash
git add index.md
git commit -m "docs: update index for semantic validation"
```

---

## Task 13: Final Integration Test

**Files:**
- Create: `tests/test_semantic_validation_integration.py`

**Step 1: Create comprehensive integration test**

Create `tests/test_semantic_validation_integration.py`:

```python
"""Integration tests for complete semantic validation."""

from custom_components.autodoctor.jinja_validator import JinjaValidator
from custom_components.autodoctor.models import IssueType


def test_realistic_automation_with_multiple_semantic_issues():
    """Test realistic automation with various semantic issues."""
    validator = JinjaValidator()
    automation = {
        "id": "realistic_test",
        "alias": "Realistic Test",
        "triggers": [
            {
                "platform": "template",
                # Invalid: multiply missing arg, undefined var, invalid entity_id
                "value_template": "{{ unknown_sensor | multiply | states('sensor_temp') }}",
            }
        ],
        "conditions": [
            {
                "condition": "template",
                # Invalid: iif too many args
                "value_template": "{{ true | iif(1, 2, 3, 4) }}",
            }
        ],
        "actions": [
            {
                "data": {
                    # Invalid: is_state wrong arg count
                    "message": "{% if x is is_state %}on{% endif %}",
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])

    # Verify we caught all the issues
    issue_types = {i.issue_type for i in issues}
    assert IssueType.TEMPLATE_INVALID_ARGUMENTS in issue_types
    assert IssueType.TEMPLATE_UNKNOWN_VARIABLE in issue_types
    assert IssueType.TEMPLATE_INVALID_ENTITY_ID in issue_types

    # Should have at least 5 issues total
    assert len(issues) >= 5


def test_realistic_automation_all_valid():
    """Test realistic automation with all valid semantics."""
    validator = JinjaValidator()
    automation = {
        "id": "realistic_valid",
        "alias": "Realistic Valid",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temperature') | float(0) > 20 }}",
            }
        ],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{{ is_state('binary_sensor.motion', 'on') }}",
            }
        ],
        "actions": [
            {
                "data": {
                    "message": "{% set temp = states('sensor.temperature') | float(0) %}Temperature is {{ temp | multiply(1.8) | add(32) | round(1) }}°F",
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])

    # Should have no semantic issues
    assert len(issues) == 0
```

**Step 2: Run integration test**

Run: `pytest tests/test_semantic_validation_integration.py -v`
Expected: PASS (2 tests)

**Step 3: Commit integration test**

```bash
git add tests/test_semantic_validation_integration.py
git commit -m "test(jinja): add semantic validation integration tests"
```

---

## Success Criteria

- ✅ All new tests pass
- ✅ No regressions in existing tests
- ✅ Filter/test argument validation works
- ✅ Variable existence checking works
- ✅ Entity ID format validation works
- ✅ All issues reported as warnings
- ✅ Test coverage >80% on new code
- ✅ Documentation updated if needed

## Files Modified

- `custom_components/autodoctor/models.py` - Added 3 new IssueType enums
- `custom_components/autodoctor/jinja_validator.py` - Added 5 new validation methods
- `custom_components/autodoctor/template_semantics.py` - Created new module (250+ lines)
- `tests/test_jinja_validator.py` - Added 30+ new tests
- `tests/test_template_semantics.py` - Created new test file (15+ tests)
- `tests/test_semantic_validation_integration.py` - Created integration test file (2 tests)
- `index.md` - Updated if needed

## Total Commits

Expected: 13 commits following TDD approach
