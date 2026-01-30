# Coding Conventions

**Analysis Date:** 2026-01-30

## Naming Patterns

**Files:**
- Snake case for all Python modules: `validator.py`, `jinja_validator.py`, `service_validator.py`
- Prefix private/internal modules with underscore if needed for clarity
- Test files follow pattern: `test_<module_name>.py` (e.g., `test_validator.py`, `test_analyzer.py`)

**Functions:**
- Snake case for all function names: `validate_reference()`, `extract_state_references()`, `get_valid_states()`
- Public methods: no leading underscore
- Private/internal methods: leading underscore: `_validate_state()`, `_validate_attribute()`, `_suggest_entity()`
- Async functions follow same convention: `async_validate_all()`, `async_setup_websocket_api()`

**Variables:**
- Snake case for all variables: `automation_id`, `entity_id`, `expected_state`, `valid_states`
- Constants: UPPER_CASE: `DOMAIN`, `VERSION`, `MAX_RECURSION_DEPTH`, `STATE_VALIDATION_WHITELIST`
- Constants defined at module level for reuse
- Private constants with leading underscore: `_LOGGER`, `_NON_ENTITY_REFERENCE_TYPES`, `_HA_FILTERS`

**Types/Classes:**
- PascalCase for all class names: `ValidationEngine`, `StateKnowledgeBase`, `JinjaValidator`, `AutomationAnalyzer`
- Enums in PascalCase: `Severity`, `IssueType`
- TypedDict/dataclass names in PascalCase: `StateReference`, `ValidationIssue`, `ServiceCall`, `ValidationConfig`

**Modules/Imports:**
- Import from relative modules using dot notation: `from .models import ...`, `from .knowledge_base import ...`
- Home Assistant imports using absolute paths from `homeassistant` package
- Group imports: Standard library → third-party → local imports

## Code Style

**Formatting:**
- Tool: Ruff formatter (integrated via pyproject.toml)
- Line length: 88 characters (set in `[tool.ruff.format]`)
- Quote style: Double quotes (enforced by `quote-style = "double"` in config)
- No trailing commas in single-line function calls

**Linting:**
- Tool: Ruff with comprehensive ruleset
- Enabled rules: E (pycodestyle errors), W (warnings), F (Pyflakes), I (isort), UP (pyupgrade), B (flake8-bugbear), SIM (flake8-simplify)
- Ignored rules: E501 (line length handled by formatter), SIM102 (nested ifs for readability), SIM108 (ternary clarity)
- Configuration: `pyproject.toml` lines 20-42
- Target: Python 3.12+

**Language Features:**
- Use `from __future__ import annotations` at top of every module for forward references
- Union types using `|` syntax (Python 3.10+): `str | None` instead of `Optional[str]`
- Use type hints throughout: all function parameters and returns must be annotated
- Use `TypedDict` for structured dictionaries: see `AutodoctorData` in `models.py` (lines 10-27)
- Use dataclasses with `@dataclass` decorator: `StateReference`, `ValidationIssue`, `ValidationConfig`

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first)
2. Standard library imports (`logging`, `asyncio`, `re`, etc.)
3. Third-party imports (`jinja2`, `voluptuous`, `homeassistant`)
4. Relative imports (`.models`, `.const`, etc.)
5. TYPE_CHECKING block for circular dependency prevention

**Path Aliases:**
- None detected; all imports use absolute paths or relative imports
- Relative imports preferred within `autodoctor` package: `from .validator import ValidationEngine`

**Circular Dependency Prevention:**
- Use `TYPE_CHECKING` block for imports needed only for type hints
- Example from `jinja_validator.py` (lines 23-24):
  ```python
  if TYPE_CHECKING:
      from homeassistant.core import HomeAssistant
  ```

## Error Handling

**Patterns:**
- Broad exception handling with specific logging: catch `Exception` and log context
- Example from `validator.py` (lines 85-89):
  ```python
  except Exception as err:
      _LOGGER.warning(
          "Error validating %s in %s: %s", ref.entity_id, ref.automation_id, err
      )
      # Return empty - avoid false positives on errors
  ```
- Graceful degradation: Return safe defaults (empty list, None) rather than raising on validation errors
- Specific exception handling for known issues (e.g., `TimeoutError` in `knowledge_base.py`)
- Nested try/except for import fallbacks: see `knowledge_base.py` (lines 32-44) for recorder history API compatibility

**Philosophy:**
- Catch exceptions high-level to prevent one bad automation from crashing all validation
- Log warnings, not errors, for validation failures (they're informational, not system errors)
- Return empty results rather than raising exceptions during validation

## Logging

**Framework:** `logging` module standard library

**Pattern:**
- Create module logger at top of file: `_LOGGER = logging.getLogger(__name__)`
- Use lazy string formatting with % operator: `_LOGGER.warning("message %s", var)`
- Log levels by purpose:
  - `debug()`: Internal state, detailed tracing
  - `info()`: Informational setup messages
  - `warning()`: Validation issues, graceful error handling
  - `error()`: Unrecoverable errors (rare)

**Examples from codebase:**
- `__init__.py` (line 66): `_LOGGER.debug("No automation data in hass.data")`
- `__init__.py` (line 87): `_LOGGER.debug("Entity %s: has raw_config=%s, raw_config type=%s", ...)`
- `validator.py` (line 87): `_LOGGER.warning("Error validating %s in %s: %s", ...)`

## Comments

**When to Comment:**
- Explain "why", not "what" (code should be self-documenting)
- Document non-obvious business logic: see `knowledge_base.py` (lines 2-12) explaining data source priority
- Mark complex regex patterns with inline comments: see `analyzer.py` (lines 14-23)
- Note compatibility workarounds: see `knowledge_base.py` (lines 32-44) for recorder history import fallbacks
- Document limits and assumptions: see `const.py` (lines 20-28) for STATE_VALIDATION_WHITELIST

**Docstrings:**
- Use triple-quote docstrings for all classes and public methods
- Format: One-line summary, blank line, detailed description (if needed), Args/Returns sections
- Google-style docstring format with `Args:` and `Returns:` sections
- Example from `knowledge_base.py` (lines 97-104):
  ```python
  """Initialize the knowledge base.

  Args:
      hass: Home Assistant instance
      history_days: Number of days of history to query
      learned_states_store: Optional store for user-learned states
      history_timeout: Timeout in seconds for history loading
  """
  ```

**Module Docstrings:**
- Include at very top of file before any imports
- Explain module purpose and key concepts
- Example from `knowledge_base.py` (lines 1-12) explains data source priority

## Function Design

**Size:**
- Aim for single responsibility: extract_state_references ~200 lines is acceptable for complex parsing
- Break down large functions into private helper methods: `_validate_state()`, `_validate_attribute()`, `_validate_non_entity_reference()`
- Functions should be under 50 lines on average; complex parsing functions can be longer

**Parameters:**
- Use positional parameters for essential inputs
- Use keyword-only parameters for optional/configuration parameters
- Maximum 5-6 parameters; use dataclasses for complex parameter groups
- Example: `validate_reference(self, ref: StateReference)` - single StateReference parameter

**Return Values:**
- Consistently return list of results: `validate_reference()` returns `list[ValidationIssue]`
- Use dataclasses for structured returns: `StateReference`, `ValidationIssue`
- Return `list | None` (not bare None) for "no results" - consistent with Home Assistant style
- Use `list[Type]` return type consistently

## Module Design

**Exports:**
- All public classes and functions are importable from the module
- No wildcard exports; be explicit about what's exported
- Private functions prefixed with underscore are not meant to be public
- Example from `models.py`: exports `Severity`, `IssueType`, `StateReference`, `ValidationIssue`, `ServiceCall`, `ValidationConfig`, `AutodoctorData`

**Barrel Files:**
- `custom_components/autodoctor/__init__.py` handles integration setup
- Individual modules are specialized: `validator.py`, `analyzer.py`, `jinja_validator.py`, `service_validator.py`
- No barrel re-exports; tests import directly from modules

**Organization:**
- One main class per module: `validator.py` → `ValidationEngine`, `analyzer.py` → `AutomationAnalyzer`
- Shared models in dedicated `models.py` module
- Constants in dedicated `const.py` module
- Helper functions in dedicated modules: `device_class_states.py`, `domain_attributes.py`, `template_semantics.py`

## Special Patterns

**Dataclass Usage:**
- Use `@dataclass` for structured data with type hints
- All field types must be specified: `entity_id: str`, `expected_state: str | None`
- Use `field(default_factory=...)` for mutable defaults
- Example from `models.py` (lines 29-41 for `ValidationConfig`):
  ```python
  @dataclass
  class ValidationConfig:
      """Configuration for validation behavior."""
      strict_template_validation: bool = False
      strict_service_validation: bool = False
      history_days: int = 30
      validate_on_reload: bool = True
      debounce_seconds: int = 5
  ```

**Enum Usage:**
- Use `class MyEnum(Enum):` for string enums: `IssueType(str, Enum)` allows string values
- Use `class MySeverity(IntEnum):` for ordered numeric values: `Severity(IntEnum)` for comparison
- Example from `models.py` (lines 43-49): `Severity` uses `IntEnum` for severity comparison

**Type Annotations:**
- All function signatures must have complete type hints (parameters and return)
- Use `| None` for optional types, not `Optional`
- Use `list[Type]` for lists, `dict[K, V]` for dicts
- Use string literals for forward references when `from __future__ import annotations` is used
- Example: `def validate_reference(self, ref: StateReference) -> list[ValidationIssue]:`

---

*Convention analysis: 2026-01-30*
