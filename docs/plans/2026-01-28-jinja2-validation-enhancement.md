# Jinja2 Validation Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix HA-incompatible Jinja2 syntax validation, then add AST-based semantic analysis to catch unknown filters and tests.

**Architecture:** Two-layer validation: (1) parse templates with an HA-compatible Jinja2 environment to catch syntax errors without false positives, (2) walk the parsed AST to verify all filter and test names exist in HA's known set. Unknown filters/tests are reported as warnings since custom integrations may add their own.

**Tech Stack:** Jinja2 AST (`jinja2.nodes`), `SandboxedEnvironment` with `loopcontrols` extension, pytest

---

### Task 1: Fix SandboxedEnvironment — Add `loopcontrols`

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py:37`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_jinja_validator.py`:

```python
def test_break_continue_do_not_produce_false_positives():
    """Templates using {% break %} and {% continue %} are valid in HA."""
    validator = JinjaValidator()
    automation = {
        "id": "loop_control_test",
        "alias": "Loop Control Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [],
        "actions": [
            {
                "data": {
                    "message": """{% for item in items %}
{% if item == 'skip' %}{% continue %}{% endif %}
{% if item == 'stop' %}{% break %}{% endif %}
{{ item }}
{% endfor %}"""
                }
            }
        ],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_jinja_validator.py::test_break_continue_do_not_produce_false_positives -v`
Expected: FAIL — the plain `SandboxedEnvironment` doesn't understand `{% break %}` or `{% continue %}`

**Step 3: Write minimal implementation**

In `custom_components/autodoctor/jinja_validator.py`, change line 37 from:

```python
self._env = SandboxedEnvironment()
```

to:

```python
self._env = SandboxedEnvironment(extensions=["jinja2.ext.loopcontrols"])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_jinja_validator.py::test_break_continue_do_not_produce_false_positives -v`
Expected: PASS

**Step 5: Add a test that real syntax errors are still caught**

Add to `tests/test_jinja_validator.py`:

```python
def test_valid_template_produces_no_issues():
    """A valid HA template should produce no issues."""
    validator = JinjaValidator()
    automation = {
        "id": "valid_template",
        "alias": "Valid Template",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float > 20 }}",
            }
        ],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{{ is_state('binary_sensor.motion', 'on') and now().hour > 6 }}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 0


def test_invalid_template_produces_syntax_error():
    """A template with bad syntax should produce an error."""
    validator = JinjaValidator()
    automation = {
        "id": "bad_syntax",
        "alias": "Bad Syntax",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | float > }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR
    assert issues[0].severity == Severity.ERROR
```

This test requires adding imports to the test file:

```python
from custom_components.autodoctor.models import IssueType, Severity
```

**Step 6: Run all jinja validator tests**

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All pass

**Step 7: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py tests/test_jinja_validator.py
git commit -m "fix(jinja): add loopcontrols extension to prevent false positives on break/continue"
```

---

### Task 2: Add new IssueTypes for semantic analysis

**Files:**
- Modify: `custom_components/autodoctor/models.py:26-27`
- Test: `tests/test_jinja_validator.py`

**Step 1: Write the failing test**

Add to `tests/test_jinja_validator.py`:

```python
def test_unknown_filter_produces_warning():
    """A template using a filter that doesn't exist in HA should produce a warning."""
    validator = JinjaValidator()
    automation = {
        "id": "bad_filter",
        "alias": "Bad Filter",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | as_timestmp }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_UNKNOWN_FILTER
    assert issues[0].severity == Severity.WARNING
    assert "as_timestmp" in issues[0].message


def test_unknown_test_produces_warning():
    """A template using a test that doesn't exist in HA should produce a warning."""
    validator = JinjaValidator()
    automation = {
        "id": "bad_test",
        "alias": "Bad Test",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [
            {
                "condition": "template",
                "value_template": "{% if states('sensor.temp') is mach('\\\\d+') %}true{% endif %}",
            }
        ],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_UNKNOWN_TEST
    assert issues[0].severity == Severity.WARNING
    assert "mach" in issues[0].message
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jinja_validator.py::test_unknown_filter_produces_warning tests/test_jinja_validator.py::test_unknown_test_produces_warning -v`
Expected: FAIL — `IssueType.TEMPLATE_UNKNOWN_FILTER` doesn't exist yet

**Step 3: Add IssueTypes to models.py**

In `custom_components/autodoctor/models.py`, add to the `IssueType` enum (after line 27):

```python
TEMPLATE_UNKNOWN_FILTER = "template_unknown_filter"
TEMPLATE_UNKNOWN_TEST = "template_unknown_test"
```

**Step 4: Run tests again — still failing**

Run: `pytest tests/test_jinja_validator.py::test_unknown_filter_produces_warning -v`
Expected: FAIL — the validator doesn't produce these issues yet (will be implemented in Task 3)

**Step 5: Commit the model change**

```bash
git add custom_components/autodoctor/models.py
git commit -m "feat(models): add TEMPLATE_UNKNOWN_FILTER and TEMPLATE_UNKNOWN_TEST issue types"
```

---

### Task 3: Implement AST-based filter and test validation

**Files:**
- Modify: `custom_components/autodoctor/jinja_validator.py`
- Test: `tests/test_jinja_validator.py`

**Step 1: Add HA filter and test allowlists**

Add these module-level constants to `custom_components/autodoctor/jinja_validator.py`, after the existing `MAX_RECURSION_DEPTH` constant:

```python
import jinja2.nodes as nodes

# HA-specific filters (added on top of Jinja2 built-ins).
# Source: https://www.home-assistant.io/docs/configuration/templating
_HA_FILTERS: frozenset[str] = frozenset({
    # Datetime / timestamp
    "as_datetime", "as_timestamp", "as_local", "as_timedelta",
    "timestamp_custom", "timestamp_local", "timestamp_utc",
    "relative_time", "time_since", "time_until",
    # JSON
    "to_json", "from_json",
    # Type conversion (override Jinja2 built-ins)
    "float", "int", "bool",
    # Validation
    "is_defined", "is_number", "has_value",
    # Math
    "log", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sqrt",
    "multiply", "add", "average", "median", "statistical_mode",
    "clamp", "wrap", "remap",
    # Bitwise
    "bitwise_and", "bitwise_or", "bitwise_xor", "ord",
    # Encoding
    "base64_encode", "base64_decode", "from_hex",
    # Hashing
    "md5", "sha1", "sha256", "sha512",
    # Regex
    "regex_match", "regex_search", "regex_replace",
    "regex_findall", "regex_findall_index",
    # String
    "slugify", "ordinal",
    # Collections
    "set", "shuffle", "flatten",
    "intersect", "difference", "symmetric_difference", "union", "combine",
    "contains",
    # Entity / device / area / floor / label lookups
    "expand", "closest", "distance",
    "state_attr", "is_state_attr", "is_state", "state_translated",
    "is_hidden_entity",
    "device_entities", "device_attr", "is_device_attr", "device_id", "device_name",
    "config_entry_id", "config_entry_attr",
    "area_id", "area_name", "area_entities", "area_devices",
    "floor_id", "floor_name", "floor_areas", "floor_entities",
    "label_id", "label_name", "label_description",
    "label_areas", "label_devices", "label_entities",
    "integration_entities",
    # Misc
    "iif", "version", "pack", "unpack",
    "apply", "as_function", "merge_response", "typeof",
})

# HA-specific tests (added on top of Jinja2 built-ins).
_HA_TESTS: frozenset[str] = frozenset({
    "match", "search",
    "is_number", "has_value", "contains",
    "is_list", "is_set", "is_tuple", "is_datetime", "is_string_like",
    "is_boolean", "is_callable", "is_float", "is_integer",
    "is_iterable", "is_mapping", "is_sequence", "is_string",
    "is_state", "is_state_attr", "is_device_attr", "is_hidden_entity",
    "apply",
})
```

**Step 2: Build the known-names sets from built-in + HA**

In `JinjaValidator.__init__`, after creating `self._env`, build the combined sets:

```python
self._known_filters: frozenset[str] = frozenset(self._env.filters.keys()) | _HA_FILTERS
self._known_tests: frozenset[str] = frozenset(self._env.tests.keys()) | _HA_TESTS
```

**Step 3: Add AST analysis method**

Add a new method to `JinjaValidator`:

```python
def _check_ast_semantics(
    self,
    template: str,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Walk the parsed AST to check for unknown filters and tests."""
    issues: list[ValidationIssue] = []

    try:
        ast = self._env.parse(template)
    except Exception:
        # Syntax errors handled elsewhere; skip semantic check
        return issues

    # Check filters
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

    # Check tests
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

**Step 4: Call AST analysis from `_check_template`**

Modify `_check_template` to return a list instead of a single issue, and call the AST analysis after a successful parse. Change the method signature and body:

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
    try:
        self._env.parse(template)
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

    # Syntax OK — run semantic checks
    return self._check_ast_semantics(template, location, auto_id, auto_name)
```

**Step 5: Update all callers of `_check_template`**

Since `_check_template` now returns a list instead of `Optional[ValidationIssue]`, update every call site. There are 4 locations:

In `_validate_trigger` (around line 108), change:
```python
# OLD
issue = self._check_template(...)
if issue:
    issues.append(issue)
# NEW
issues.extend(self._check_template(...))
```

In `_validate_condition` (around line 150), same pattern change.

In `_validate_actions` for `wait_template` (around line 245), same pattern change.

In `_validate_data_templates` (around line 381 and 395), same pattern change for both string and list-item checks.

**Step 6: Run the full test suite**

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All pass, including the new `test_unknown_filter_produces_warning` and `test_unknown_test_produces_warning` tests from Task 2.

**Step 7: Commit**

```bash
git add custom_components/autodoctor/jinja_validator.py
git commit -m "feat(jinja): add AST-based semantic validation for unknown filters and tests"
```

---

### Task 4: Add comprehensive test coverage

**Files:**
- Modify: `tests/test_jinja_validator.py`

**Step 1: Add tests for HA-specific filters and tests passing validation**

```python
def test_ha_filters_are_accepted():
    """Common HA filters should not produce warnings."""
    validator = JinjaValidator()
    templates = [
        "{{ states('sensor.temp') | float }}",
        "{{ states('sensor.temp') | as_timestamp }}",
        "{{ states('sensor.temp') | from_json }}",
        "{{ states('sensor.temp') | to_json }}",
        "{{ states('sensor.temp') | regex_match('\\\\d+') }}",
        "{{ states('sensor.temp') | slugify }}",
        "{{ states('sensor.temp') | base64_encode }}",
        "{{ states('sensor.temp') | md5 }}",
        "{{ states('sensor.temp') | iif('yes', 'no') }}",
        "{{ states('sensor.temp') | as_datetime }}",
        "{{ states('sensor.temp') | multiply(2) }}",
        "{{ [1, 2, 3] | average }}",
        "{{ [1, 2, 3] | median }}",
    ]
    for tmpl in templates:
        automation = {
            "id": "filter_test",
            "alias": "Filter Test",
            "triggers": [{"platform": "template", "value_template": tmpl}],
            "conditions": [],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert len(issues) == 0, f"Unexpected issue for template: {tmpl}: {issues}"


def test_ha_tests_are_accepted():
    """Common HA tests should not produce warnings."""
    validator = JinjaValidator()
    templates = [
        "{% if states('sensor.temp') is match('\\\\d+') %}t{% endif %}",
        "{% if states('sensor.temp') is search('\\\\d+') %}t{% endif %}",
        "{% if states('sensor.temp') is is_number %}t{% endif %}",
        "{% if states('sensor.temp') is has_value %}t{% endif %}",
        "{% if states('sensor.temp') is contains('x') %}t{% endif %}",
        "{% if states('sensor.temp') is is_list %}t{% endif %}",
    ]
    for tmpl in templates:
        automation = {
            "id": "test_test",
            "alias": "Test Test",
            "triggers": [{"platform": "time", "at": "12:00:00"}],
            "conditions": [{"condition": "template", "value_template": tmpl}],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert len(issues) == 0, f"Unexpected issue for template: {tmpl}: {issues}"


def test_standard_jinja2_filters_are_accepted():
    """Standard Jinja2 built-in filters should not produce warnings."""
    validator = JinjaValidator()
    templates = [
        "{{ items | join(', ') }}",
        "{{ name | upper }}",
        "{{ name | lower }}",
        "{{ items | first }}",
        "{{ items | last }}",
        "{{ items | length }}",
        "{{ items | sort }}",
        "{{ items | unique | list }}",
        "{{ name | replace('a', 'b') }}",
        "{{ name | trim }}",
        "{{ items | map(attribute='state') | list }}",
        "{{ items | selectattr('state', 'eq', 'on') | list }}",
        "{{ items | rejectattr('state', 'eq', 'off') | list }}",
        "{{ value | default('N/A') }}",
        "{{ items | batch(3) | list }}",
        "{{ text | truncate(20) }}",
    ]
    for tmpl in templates:
        automation = {
            "id": "builtin_filter",
            "alias": "Builtin Filter",
            "triggers": [{"platform": "template", "value_template": tmpl}],
            "conditions": [],
            "actions": [],
        }
        issues = validator.validate_automations([automation])
        assert len(issues) == 0, f"Unexpected issue for template: {tmpl}: {issues}"


def test_multiple_unknown_filters_all_reported():
    """Multiple unknown filters in one template should each produce a warning."""
    validator = JinjaValidator()
    automation = {
        "id": "multi_bad_filter",
        "alias": "Multi Bad Filter",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | florb | blargh }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    assert len(issues) == 2
    names = {i.message for i in issues}
    assert any("florb" in m for m in names)
    assert any("blargh" in m for m in names)


def test_syntax_error_skips_semantic_check():
    """When there's a syntax error, semantic checks should not run."""
    validator = JinjaValidator()
    automation = {
        "id": "syntax_then_semantic",
        "alias": "Syntax Then Semantic",
        "triggers": [
            {
                "platform": "template",
                "value_template": "{{ states('sensor.temp') | }}",
            }
        ],
        "conditions": [],
        "actions": [],
    }
    issues = validator.validate_automations([automation])
    # Should only get syntax error, not also unknown filter
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.TEMPLATE_SYNTAX_ERROR
```

**Step 2: Run all tests**

Run: `pytest tests/test_jinja_validator.py -v`
Expected: All pass

**Step 3: Run the full project test suite**

Run: `pytest tests/ -v`
Expected: All pass — no regressions from the changes

**Step 4: Commit**

```bash
git add tests/test_jinja_validator.py
git commit -m "test(jinja): add comprehensive tests for syntax and semantic validation"
```

---

### Task 5: Update index.md if needed

**Files:**
- Check: `index.md`

**Step 1: Review whether structural changes require an index update**

The changes add new `IssueType` enum values and new functionality to `jinja_validator.py`, but do not add/remove/rename modules or add new API commands or services. An index update is **not required** unless the index specifically documents IssueType values or validation capabilities in detail.

**Step 2: Check and update if needed**

Read `index.md` and update only if it documents IssueType values or Jinja validation features.
