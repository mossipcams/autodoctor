# Testing Patterns

**Analysis Date:** 2026-01-30

## Test Framework

**Runner:**
- Framework: pytest 8.0.0+
- Plugin: pytest-homeassistant-custom-component 0.13.0+ (Home Assistant test fixtures)
- Async support: pytest-asyncio 0.23.0+
- Guard: tdd-guard-pytest (test-driven development guard)
- Config: `pyproject.toml` lines 15-18
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  tdd_guard_project_root = "/Users/matt/Desktop/Projects/autodoctor"
  ```

**Assertion Library:**
- Built-in `assert` statements (pytest uses these directly)
- Example: `assert len(issues) == 1` from `test_validator.py` (line 34)

**Run Commands:**
```bash
pytest                          # Run all tests
pytest tests/test_validator.py  # Run specific test file
pytest -xvs                     # Run with verbose output, stop on first failure
pytest --cov                    # Run with coverage
pytest -k "test_validate"       # Run tests matching pattern
```

## Test File Organization

**Location:**
- Path: `/Users/matt/Desktop/Projects/autodoctor/tests/`
- Co-located with source: tests/ is separate directory (not alongside source files)

**Naming:**
- Pattern: `test_<module_name>.py`
- Examples: `test_validator.py`, `test_analyzer.py`, `test_jinja_validator.py`, `test_service_validator.py`, `test_websocket_api.py`
- Special: `conftest.py` for shared fixtures and pytest configuration

**Structure:**
```
tests/
├── __init__.py                          # Package marker
├── conftest.py                          # Shared fixtures (mock_recorder, auto_enable_custom_integrations)
├── test_analyzer.py                     # AutomationAnalyzer tests (~1200+ lines)
├── test_architectural_improvements.py   # Architecture validation tests
├── test_device_class_states.py          # Device class state tests
├── test_fix_engine.py                   # Deprecation tests (module removed)
├── test_init.py                         # Integration setup tests
├── test_jinja_validator.py              # Template syntax validation tests (~400+ lines)
├── test_knowledge_base.py               # State knowledge base tests (~400+ lines)
├── test_learned_states_store.py         # Learned states persistence tests
├── test_models.py                       # Data model tests
├── test_reporter.py                     # Issue reporter tests
├── test_service_validator.py            # Service call validation tests (~600+ lines)
├── test_template_semantics.py           # Template function/filter signature tests
├── test_validator.py                    # Validation engine tests (~600+ lines)
├── test_websocket_api.py                # WebSocket API tests
└── test_websocket_api_learning.py       # WebSocket learning mode tests
```

## Test Structure

**Suite Organization:**
- No explicit test classes; tests use functions
- Tests organized by functionality being tested
- Example from `test_validator.py`:
  ```python
  async def test_validate_missing_entity(hass: HomeAssistant, knowledge_base):
      """Test validation detects missing entity."""
      # Setup
      ref = StateReference(...)
      validator = ValidationEngine(knowledge_base)

      # Execute
      issues = validator.validate_reference(ref)

      # Assert
      assert len(issues) == 1
      assert issues[0].severity == Severity.ERROR
  ```

**Test Patterns:**
- Arrange-Act-Assert pattern (setup, execution, verification)
- Docstrings for every test explaining what is being tested
- Each test function is independent and self-contained
- Fixtures inject dependencies (hass, knowledge_base, etc.)

**Async Testing:**
```python
async def test_validate_invalid_state(hass: HomeAssistant, knowledge_base):
    """Test validation detects invalid state."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()  # Wait for state propagation

    # Test code here
```

- All async tests use `async def`
- `asyncio_mode = "auto"` in pytest config automatically handles async
- Use `await hass.async_block_till_done()` to wait for Home Assistant state changes

## Mocking

**Framework:** `unittest.mock` from standard library

**Patterns:**
- `MagicMock()` for synchronous mocks
- `AsyncMock()` for async function mocks
- `patch()` context manager for replacing functions/classes
- Example from `test_init.py` (lines 25-30):
  ```python
  mock_analyzer.extract_state_references.side_effect = [
      Exception("Malformed config"),
      [],  # Second automation succeeds
  ]
  ```

**WebSocket Testing Pattern:**
- Mock WebSocket connections with `MagicMock()`
- Test decorator-wrapped functions using `.__wrapped__` attribute
- Example from `test_websocket_api.py` (lines 44):
  ```python
  await websocket_get_issues.__wrapped__(hass, connection, msg)
  ```

**Common Mocking Patterns:**
- Patch Home Assistant services: `patch("homeassistant.components.websocket_api.async_register_command")`
- Mock internal functions: `patch("custom_components.autodoctor.async_validate_all", new_callable=AsyncMock)`
- Set mock return values: `mock.return_value = ...` or `mock_async.return_value = [...] (async)`
- Set side effects for multiple calls: `mock.side_effect = [result1, result2]`
- Verify calls: `assert mock.called`, `assert mock.call_count == 2`

**What to Mock:**
- Home Assistant internal components (websocket_api, services, config_entries)
- External integrations and APIs
- File I/O and persistence layers
- Long-running async operations

**What NOT to Mock:**
- Core validation logic being tested
- Data structures (use real dataclasses)
- Logging output (just verify it happens)
- Home Assistant state management (use hass fixture)

## Fixtures and Factories

**Test Data:**
- Direct construction of dataclasses in tests
- Example from `test_models.py` (lines 15-24):
  ```python
  def test_state_reference_creation():
      """Test StateReference dataclass."""
      ref = StateReference(
          automation_id="automation.welcome_home",
          automation_name="Welcome Home",
          entity_id="person.matt",
          expected_state="home",
          expected_attribute=None,
          location="trigger[0].to",
          source_line=10,
      )
      assert ref.automation_id == "automation.welcome_home"
  ```

**Shared Fixtures:**
- Location: `tests/conftest.py`
- Defined fixtures:
  - `auto_enable_custom_integrations(enable_custom_integrations)` - enables custom integrations for all tests (autouse=True)
  - `mock_recorder()` - patches knowledge_base.get_instance() with MagicMock
- Home Assistant fixtures provided by pytest-homeassistant-custom-component:
  - `hass: HomeAssistant` - Home Assistant test instance
  - `enable_custom_integrations` - enables custom component loading

**Custom Fixtures in Tests:**
- Example from `test_init.py` (lines 9-14):
  ```python
  @pytest.fixture
  def mock_hass():
      """Create mock Home Assistant instance."""
      hass = MagicMock()
      hass.data = {DOMAIN: {}}
      return hass
  ```
- Example from `test_validator.py` (lines 13-17):
  ```python
  @pytest.fixture
  def knowledge_base(hass: HomeAssistant):
      """Create a knowledge base with mocked data."""
      kb = StateKnowledgeBase(hass)
      return kb
  ```

**Test Automation Builders:**
- Inline automation dictionaries in tests (no factory)
- Example from `test_analyzer.py` (lines 8-19):
  ```python
  automation = {
      "id": "welcome_home",
      "alias": "Welcome Home",
      "trigger": [{"platform": "state", "entity_id": "person.matt", "to": "home"}],
      "action": [],
  }
  ```

## Coverage

**Requirements:** Not enforced by pyproject.toml (no coverage minimum specified)

**View Coverage:**
```bash
pytest --cov=custom_components.autodoctor --cov-report=html
```

**Coverage Status:**
- 16 test files with 1000+ total lines of tests
- Large test files indicate good coverage:
  - `test_analyzer.py` - 1226 lines (extraction logic)
  - `test_knowledge_base.py` - 400+ lines (state validation)
  - `test_service_validator.py` - 600+ lines (service validation)
  - `test_validator.py` - 600+ lines (validation engine)
  - `test_jinja_validator.py` - 400+ lines (template validation)

## Test Types

**Unit Tests:**
- Scope: Individual class/function behavior
- Example: `test_validate_missing_entity()` tests ValidationEngine.validate_reference()
- Approach: Direct instantiation and method calls with minimal setup
- Most tests in the suite are unit tests (test_models.py, test_device_class_states.py, most of test_analyzer.py)

**Integration Tests:**
- Scope: Multiple components working together
- Example: Tests in test_knowledge_base.py test knowledge base with Home Assistant state
- Approach: Use hass fixture with real state management
- Tests in test_validator.py integrate ValidationEngine with StateKnowledgeBase

**E2E Tests:**
- Framework: Not used (no e2e tests detected)
- WebSocket API tests act as partial e2e (test_websocket_api.py) by testing full flow

## Common Patterns

**Async Testing:**
```python
async def test_validate_invalid_state(hass: HomeAssistant, knowledge_base):
    """Test validation detects invalid state."""
    hass.states.async_set("person.matt", "home")
    await hass.async_block_till_done()

    ref = StateReference(
        automation_id="automation.test",
        automation_name="Test",
        entity_id="person.matt",
        expected_state="away",
        expected_attribute=None,
        location="trigger[0].to",
    )

    validator = ValidationEngine(knowledge_base)
    issues = validator.validate_reference(ref)

    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "away" in issues[0].message
```

**State Testing with Home Assistant:**
```python
async def test_entity_exists(hass: HomeAssistant):
    """Test checking if entity exists."""
    kb = StateKnowledgeBase(hass)

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    assert kb.entity_exists("binary_sensor.motion") is True
    assert kb.entity_exists("binary_sensor.missing") is False
```

**Error Testing:**
```python
async def test_validate_service_not_found(hass: HomeAssistant):
    """Test validation for non-existent service."""
    validator = ServiceCallValidator(hass)

    call = ServiceCall(
        automation_id="automation.test",
        automation_name="Test",
        service="nonexistent.service",
        location="action[0]",
    )

    issues = validator.validate_service_calls([call])

    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.SERVICE_NOT_FOUND
    assert issues[0].severity == Severity.ERROR
    assert "nonexistent.service" in issues[0].message
```

**Mocking External Calls:**
```python
@pytest.mark.asyncio
async def test_websocket_api_setup(hass: HomeAssistant):
    """Test WebSocket API can be set up."""
    with patch(
        "homeassistant.components.websocket_api.async_register_command"
    ) as mock_register:
        await async_setup_websocket_api(hass)
        assert mock_register.called
```

**Template Validation with Edge Cases:**
```python
def test_deeply_nested_conditions_do_not_stackoverflow():
    """Test that deeply nested conditions hit recursion limit gracefully."""
    validator = JinjaValidator()

    condition = {"condition": "state", "entity_id": "light.test", "state": "on"}
    for _ in range(25):
        condition = {"condition": "and", "conditions": [condition]}

    automation = {
        "id": "deep_nest",
        "alias": "Deeply Nested",
        "triggers": [{"platform": "time", "at": "12:00:00"}],
        "conditions": [condition],
        "actions": [],
    }

    issues = validator.validate_automations([automation])
    assert isinstance(issues, list)  # Should not crash
```

**Exception Handling Testing:**
```python
@pytest.mark.asyncio
async def test_one_bad_automation_does_not_crash_all(mock_hass):
    """Test that one malformed automation doesn't stop validation of others."""
    mock_analyzer = MagicMock()
    mock_analyzer.extract_state_references.side_effect = [
        Exception("Malformed config"),
        [],  # Second automation succeeds
    ]

    # Test expects resilience to exceptions
    with patch("custom_components.autodoctor._get_automation_configs", ...):
        issues = await async_validate_all(mock_hass)

    assert isinstance(issues, list)
```

## Test Execution Notes

**Key Behaviors:**
- `asyncio_mode = "auto"` means pytest-asyncio automatically detects async tests
- No need for `@pytest.mark.asyncio` explicitly (though it's still used in some tests for clarity)
- `autouse=True` on fixture means it runs for all tests automatically
- `hass` fixture is injected from pytest-homeassistant-custom-component

**Test Independence:**
- Each test function is independent
- Fixtures are created fresh for each test (default scope="function")
- No shared state between tests
- Tests can run in any order

**Common Test Assertions:**
- List length checks: `assert len(issues) == 1`
- Field value checks: `assert issues[0].severity == Severity.ERROR`
- String containment: `assert "message text" in issues[0].message`
- Type checks: `assert isinstance(issues, list)`
- Mock call verification: `assert mock_register.called`

---

*Testing analysis: 2026-01-30*
