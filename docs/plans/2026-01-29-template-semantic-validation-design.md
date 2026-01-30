# Template Semantic Validation Design

**Date:** 2026-01-29
**Status:** Design
**Goal:** Add deep semantic validation to Jinja2 templates beyond syntax checking

## Overview

Enhance template validation to catch semantic issues: invalid filter/test arguments, undefined variables, and malformed entity IDs. All semantic issues reported as warnings to avoid false positives from custom integrations.

## Requirements

- Validate filter/test argument counts against known signatures
- Detect references to undefined variables (with scope tracking)
- Validate entity_id format in state functions
- Report all issues as warnings (non-blocking)
- Maintain single-pass AST traversal for performance
- Support format-only entity validation (no registry lookup)

## Architecture

### Module Structure

**New Module: `template_semantics.py`**
- Signature registry for filters and tests
- Known global variables set
- Entity ID pattern definitions
- Validation helper functions
- No dependencies on JinjaValidator

**Enhanced: `jinja_validator.py`**
- Imports signature registry from template_semantics
- Extends `_check_ast_semantics()` with new validations
- Maintains single-pass AST traversal
- Returns warnings for all semantic issues

**Enhanced: `models.py`**
- Add `TEMPLATE_INVALID_ARGUMENTS` issue type
- Add `TEMPLATE_UNKNOWN_VARIABLE` issue type
- Add `TEMPLATE_INVALID_ENTITY_ID` issue type

### Design Approach: Signature Registry + Validator (Data-Driven)

Create a signature registry with filter/test definitions as data structures, then walk AST once and validate against the registry. This separates "what to validate" (data) from "how to validate" (logic).

**Benefits:**
- Adding filters/tests is just adding data
- Easy to update when HA evolves
- Signature registry is reusable
- Clear separation of concerns
- Still single-pass for performance

## Detailed Design

### 1. Signature Registry

**Data Structures:**

```python
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

**Registry Dictionaries:**

```python
FILTER_SIGNATURES: dict[str, Signature] = {
    "float": Signature("float", 0, 1, (ArgSpec("default", False),)),
    "int": Signature("int", 0, 2, (ArgSpec("default", False), ArgSpec("base", False))),
    "multiply": Signature("multiply", 1, 2, (ArgSpec("amount", True), ArgSpec("default", False))),
    "add": Signature("add", 1, 2, (ArgSpec("amount", True), ArgSpec("default", False))),
    "iif": Signature("iif", 1, 3, (
        ArgSpec("if_true", False),
        ArgSpec("if_false", False),
        ArgSpec("if_none", False)
    )),
    "regex_match": Signature("regex_match", 1, 2, (
        ArgSpec("pattern", True),
        ArgSpec("ignorecase", False)
    )),
    "regex_replace": Signature("regex_replace", 2, 3, (
        ArgSpec("find", True),
        ArgSpec("replace", True),
        ArgSpec("ignorecase", False)
    )),
    "round": Signature("round", 0, 3, (
        ArgSpec("precision", False),
        ArgSpec("method", False),
        ArgSpec("default", False)
    )),
    "log": Signature("log", 0, 2, (ArgSpec("base", False), ArgSpec("default", False))),
    "clamp": Signature("clamp", 2, 3, (
        ArgSpec("min", True),
        ArgSpec("max", True),
        ArgSpec("default", False)
    )),
    # ~20-30 more common HA filters
}

TEST_SIGNATURES: dict[str, Signature] = {
    "is_state": Signature("is_state", 2, 2, (
        ArgSpec("entity_id", True),
        ArgSpec("state", True)
    )),
    "is_state_attr": Signature("is_state_attr", 3, 3, (
        ArgSpec("entity_id", True),
        ArgSpec("name", True),
        ArgSpec("value", True)
    )),
    "has_value": Signature("has_value", 1, 1, (ArgSpec("entity_id", True),)),
    "is_hidden_entity": Signature("is_hidden_entity", 1, 1, (ArgSpec("entity_id", True),)),
    "contains": Signature("contains", 1, 1, (ArgSpec("value", True),)),
    # ~5-10 more common HA tests
}
```

**Validation Logic:**

Count arguments from AST Filter/Test nodes and compare against min/max. Report warning if count is outside range.

**Scope:**

Focus on ~30 most common filters and ~10 most common tests. Argument count validation only (no type checking since Jinja is dynamically typed).

### 2. Variable Existence Validation

**Known Global Variables:**

```python
KNOWN_GLOBALS: frozenset[str] = frozenset({
    # State access
    "states", "now", "utcnow", "as_timestamp",
    "state_attr", "state_translated", "is_state", "is_state_attr",

    # Entity operations
    "expand", "closest", "distance", "has_value", "is_hidden_entity",

    # Device queries
    "device_entities", "device_attr", "is_device_attr", "device_id", "device_name",
    "config_entry_id", "config_entry_attr",

    # Area queries
    "area_entities", "area_id", "area_name", "area_devices",

    # Floor queries
    "floor_entities", "floor_id", "floor_name", "floor_areas",

    # Label queries
    "label_entities", "label_id", "label_name", "label_description",
    "label_areas", "label_devices",

    # Other
    "integration_entities",
})
```

**Scoped Variables:**

Track variables defined within templates:
- `{% set var = value %}` - adds 'var' to current scope
- `{% for item in items %}` - adds 'item' to loop scope
- Use stack to push/pop scopes as we traverse AST

**Special Context Variables:**

Permissively allow context-dependent variables:
- `trigger` - automation trigger context
- `this` - entity template context
- `repeat` - repeat block context

These are allowed without warnings since static analysis can't determine context. This prevents false positives.

**Validation Strategy:**

For each Name node in AST:
1. Check if name is in KNOWN_GLOBALS
2. Check if name is in current scope stack
3. Check if name is special context variable (trigger, this, repeat)
4. If none match, warn about undefined variable

### 3. Entity ID Format Validation

**Entity ID Pattern:**

```python
ENTITY_ID_PATTERN = re.compile(r'^[a-z_][a-z0-9_]*\.[a-z0-9_]+$')
```

Validates:
- Domain: starts with letter/underscore, contains letters/digits/underscores
- Separator: single dot
- Object ID: letters/digits/underscores

**Functions to Validate:**

Track Call nodes for these functions and validate entity_id arguments:

```python
ENTITY_ID_FUNCTIONS: dict[str, int] = {
    "states": 0,              # entity_id is arg 0
    "state_attr": 0,          # entity_id is arg 0
    "is_state": 0,            # entity_id is arg 0
    "is_state_attr": 0,       # entity_id is arg 0
    "has_value": 0,           # entity_id is arg 0
    "is_hidden_entity": 0,    # entity_id is arg 0
    "device_id": 0,           # entity_id is arg 0
    # Add more as needed
}
```

**Detection Strategy:**

1. Walk AST for Call nodes
2. Check if function name in ENTITY_ID_FUNCTIONS
3. Extract argument at specified position
4. If argument is Const node with string value, validate pattern
5. Warn if pattern doesn't match

**Limitations:**

Only validate string literals - not variables or expressions:
- `states("sensor.temp")` ✓ Validated
- `states(entity_var)` ✗ Not validated (unknown at static analysis)
- `states("sensor." ~ name)` ✗ Not validated (dynamic construction)

This keeps false positives low.

### 4. Implementation Details

**Enhanced `_check_ast_semantics()` Method:**

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

    # Initialize scope with known globals
    scope_stack: list[set[str]] = [KNOWN_GLOBALS.copy()]

    # First pass: collect scope information (Assign, For nodes)
    scope_map: dict[int, set[str]] = self._build_scope_map(ast)

    # Second pass: validate all nodes
    for node in ast.find_all((nodes.Filter, nodes.Test, nodes.Name, nodes.Call)):
        if isinstance(node, nodes.Filter):
            issues.extend(self._validate_filter_args(node, location, auto_id, auto_name))
        elif isinstance(node, nodes.Test):
            issues.extend(self._validate_test_args(node, location, auto_id, auto_name))
        elif isinstance(node, nodes.Name):
            # Determine scope at this node position
            current_scope = self._get_scope_at_node(node, scope_map)
            issues.extend(self._validate_variable(node, current_scope, location, auto_id, auto_name))
        elif isinstance(node, nodes.Call):
            issues.extend(self._validate_entity_id_call(node, location, auto_id, auto_name))

    return issues
```

**New Helper Methods:**

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

    arg_count = len(node.args) if node.args else 0
    if arg_count < sig.min_args or (sig.max_args is not None and arg_count > sig.max_args):
        return [ValidationIssue(
            issue_type=IssueType.TEMPLATE_INVALID_ARGUMENTS,
            severity=Severity.WARNING,
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id="",
            location=location,
            message=f"Filter '{node.name}' expects {sig.min_args}-{sig.max_args or '∞'} arguments, got {arg_count}",
        )]
    return []

def _validate_test_args(
    self,
    node: nodes.Test,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate test argument count."""
    # Similar to _validate_filter_args
    pass

def _validate_variable(
    self,
    node: nodes.Name,
    current_scope: set[str],
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate variable reference."""
    # Skip special context variables
    if node.name in ("trigger", "this", "repeat"):
        return []

    if node.name not in current_scope:
        return [ValidationIssue(
            issue_type=IssueType.TEMPLATE_UNKNOWN_VARIABLE,
            severity=Severity.WARNING,
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id="",
            location=location,
            message=f"Undefined variable '{node.name}'",
        )]
    return []

def _validate_entity_id_call(
    self,
    node: nodes.Call,
    location: str,
    auto_id: str,
    auto_name: str,
) -> list[ValidationIssue]:
    """Validate entity_id format in function calls."""
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
    if not isinstance(arg, nodes.Const) or not isinstance(arg.value, str):
        return []  # Not a string literal, skip validation

    entity_id = arg.value
    if not ENTITY_ID_PATTERN.match(entity_id):
        return [ValidationIssue(
            issue_type=IssueType.TEMPLATE_INVALID_ENTITY_ID,
            severity=Severity.WARNING,
            automation_id=auto_id,
            automation_name=auto_name,
            entity_id=entity_id,
            location=location,
            message=f"Invalid entity_id format: '{entity_id}' (expected 'domain.object_id')",
        )]
    return []

def _build_scope_map(self, ast: nodes.Template) -> dict[int, set[str]]:
    """Build map of node positions to available variables."""
    # Walk AST and track variable assignments
    pass

def _get_scope_at_node(self, node: nodes.Node, scope_map: dict[int, set[str]]) -> set[str]:
    """Get variables in scope at a specific node."""
    # Look up scope from map
    pass
```

## Testing Strategy

### Unit Tests for `template_semantics.py`

**Signature Registry (5 tests):**
- Test signature lookups return correct data
- Test ENTITY_ID_PATTERN matches valid formats
- Test ENTITY_ID_PATTERN rejects invalid formats
- Test KNOWN_GLOBALS contains expected functions
- Test ArgSpec and Signature dataclass creation

### Integration Tests for `test_jinja_validator.py`

**Filter/Test Argument Validation (15 tests):**
- ✓ Correct usage passes: `{{ x | multiply(2) }}`
- ✓ Optional args allowed: `{{ x | float }}` and `{{ x | float(0) }}`
- ✗ Too few args warns: `{{ x | multiply }}`
- ✗ Too many args warns: `{{ x | iif(1, 2, 3, 4) }}`
- ✓ Multiple filters chained: `{{ x | float | multiply(2) }}`
- ✗ Each invalid filter in chain warns separately
- ✓ Standard Jinja filters with correct args pass
- ✓ Regex filters with patterns: `{{ x | regex_match('\\d+') }}`
- ✗ Missing required pattern arg: `{{ x | regex_match }}`
- ✓ iif with 1 arg: `{{ x | iif(true_val) }}`
- ✓ iif with 2 args: `{{ x | iif(true_val, false_val) }}`
- ✓ iif with 3 args: `{{ x | iif(true_val, false_val, none_val) }}`
- ✗ iif with 0 args warns
- ✗ iif with 4 args warns
- ✓ Tests with correct args: `{% if x is is_state('sensor.temp', 'on') %}`

**Variable Existence (15 tests):**
- ✓ Known globals pass: `{{ states('sensor.temp') }}`, `{{ now() }}`
- ✓ Set vars pass: `{% set x = 1 %}{{ x }}`
- ✓ Loop vars pass: `{% for item in items %}{{ item }}{% endfor %}`
- ✓ Nested loops track scope correctly
- ✓ Special context allowed: `{{ trigger.platform }}`, `{{ this.state }}`, `{{ repeat.index }}`
- ✓ Special context attributes: `{{ trigger.to_state.state }}`
- ✗ Undefined vars warn: `{{ unknown_var }}`
- ✗ Typos warn: `{{ sates('sensor.temp') }}`  # "sates" instead of "states"
- ✓ Variable shadowing works (inner scope overrides outer)
- ✓ Variables out of scope after block: `{% for x in items %}{% endfor %}{{ x }}` warns
- ✓ Multiple set statements: `{% set a = 1 %}{% set b = 2 %}{{ a }}{{ b }}`
- ✗ Using variable before definition warns
- ✓ Jinja built-in variables: `{{ range(10) }}`, `{{ loop.index }}`
- ✓ Filter/test names don't count as variables
- ✗ Common typos: `{{ triger.platform }}`, `{{ repat.index }}`

**Entity ID Format (10 tests):**
- ✓ Valid formats pass: `{{ states('sensor.temp') }}`
- ✓ Valid with underscores: `{{ states('sensor.temp_sensor') }}`
- ✓ Valid with numbers: `{{ states('sensor.temp2') }}`
- ✗ Missing domain warns: `{{ states('temp') }}`
- ✗ Missing object_id warns: `{{ states('sensor.') }}`
- ✗ Uppercase warns: `{{ states('SENSOR.temp') }}`
- ✗ Hyphen warns: `{{ states('sensor.temp-sensor') }}`
- ✗ Space warns: `{{ states('sensor temp') }}`
- ✓ Non-literals ignored: `{{ states(entity_var) }}`
- ✓ Expressions ignored: `{{ states('sensor.' ~ name) }}`

**No Regression Tests (5 tests):**
- ✓ All existing valid template tests still pass
- ✓ Syntax errors still detected
- ✓ Unknown filters still detected
- ✓ Unknown tests still detected
- ✓ Valid automations produce no warnings

### Performance Tests

**Benchmark (2 tests):**
- Validate 100 automations with semantic checks
- Compare timing vs current validation
- Ensure <10% overhead

## Success Criteria

- ✅ Detect argument count issues for 20+ filters/tests
- ✅ Detect undefined variable references
- ✅ Validate entity_id format in state functions
- ✅ All issues reported as warnings (not errors)
- ✅ No false positives on valid templates
- ✅ Performance impact <10%
- ✅ 80%+ test coverage on new code
- ✅ All existing tests still pass

## Future Enhancements

Not included in this design but possible future additions:

1. **Type inference** - Track inferred types through AST and warn on mismatches
2. **Attribute validation** - Check attribute names against domain schemas
3. **Registry validation** - Optionally verify entity_id exists in registry
4. **Custom filter support** - Allow extending signature registry via config
5. **Auto-fix suggestions** - Suggest corrections for common typos

## Files to Modify

- `custom_components/autodoctor/models.py` - Add 3 new IssueType enums
- `custom_components/autodoctor/jinja_validator.py` - Add semantic validation methods
- `tests/test_jinja_validator.py` - Add ~40 new integration tests

## Files to Create

- `custom_components/autodoctor/template_semantics.py` - Signature registry and helpers
- `tests/test_template_semantics.py` - Unit tests for registry
