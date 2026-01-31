## TDD Fundamentals

### The TDD Cycle
The foundation of TDD is the Red-Green-Refactor cycle:

1. **Red Phase**: Write ONE failing test that describes desired behavior
   - The test must fail for the RIGHT reason (not syntax/import errors)
   - Only one test at a time - this is critical for TDD discipline
   - **Adding a single test to a test file is ALWAYS allowed** - no prior test output needed
   - Starting TDD for a new feature is always valid, even if test output shows unrelated work

2. **Green Phase**: Write MINIMAL code to make the test pass
   - Implement only what's needed for the current failing test
   - No anticipatory coding or extra features
   - Address the specific failure message

3. **Refactor Phase**: Improve code structure while keeping tests green
   - Only allowed when relevant tests are passing
   - Requires proof that tests have been run and are green
   - Applies to BOTH implementation and test code
   - No refactoring with failing tests - fix them first

### Core Violations

1. **Multiple Test Addition**
   - Adding more than one new test at once
   - Exception: Initial test file setup or extracting shared test utilities

2. **Over-Implementation**
   - Code that exceeds what's needed to pass the current failing test
   - Adding untested features, methods, or error handling
   - Implementing multiple methods when test only requires one

3. **Premature Implementation**
   - Adding implementation before a test exists and fails properly
   - Adding implementation without running the test first
   - Refactoring when tests haven't been run or are failing

### Critical Principle: Incremental Development
Each step in TDD should address ONE specific issue:
- Test fails `ImportError` or `ModuleNotFoundError` → Create the module/class stub only
- Test fails `AttributeError` → Add method stub only
- Test fails `AssertionError` → Implement minimal logic only

### Project-Specific Rules (autodoctor)

#### Test Runner
- Run tests: `.venv/bin/python -m pytest tests/ -x`
- Run a single file: `.venv/bin/python -m pytest tests/test_<module>.py -v`
- Run a single test: `.venv/bin/python -m pytest tests/test_<module>.py::test_name -v`
- Always use `-x` (fail-fast) during Red/Green phases to stop at the first failure

#### Module-to-Test Mapping
| Module | Test File |
|---|---|
| `validator.py` | `test_validator.py` |
| `service_validator.py` | `test_service_validator.py` |
| `jinja_validator.py` | `test_jinja_validator.py` |
| `knowledge_base.py` | `test_knowledge_base.py` |
| `analyzer.py` | `test_analyzer.py` |
| `models.py` | `test_models.py` |
| `ha_catalog.py` | `test_ha_catalog.py` |
| `device_class_states.py` | `test_device_class_states.py` |
| `learned_states_store.py` | `test_learned_states_store.py` |
| `reporter.py` | `test_reporter.py` |
| `__init__.py` | `test_init.py` |
| `websocket_api.py` | `test_websocket_api.py`, `test_websocket_api_learning.py` |

Do not create new test files for existing modules — add tests to the corresponding file.

#### Async Testing Patterns
- Most HA-interacting tests use `async def test_*` with the `hass` fixture
- Use `await hass.async_block_till_done()` after state changes
- Use `AsyncMock` for mocking async functions, `MagicMock` for sync
- `asyncio_mode = "auto"` means `@pytest.mark.asyncio` is optional

#### Mutation Testing Awareness
mutmut is used on `validator.py`, `service_validator.py`, `jinja_validator.py`, `knowledge_base.py`. When writing tests for these modules:
- Prefer specific assertions (`assert result.issue_type == "missing_entity"`) over existence checks (`assert result is not None`)
- Test boundary conditions and edge cases to catch mutations
- Each conditional branch should have a test that fails if removed

#### Parametrized Tests Are One Test
Adding or extending a `@pytest.mark.parametrize` decorator with multiple cases counts as ONE test, not multiple. This project validates domains, attributes, service parameters, and template patterns — these are naturally expressed as parametrized cases covering one logical behavior. For example:
- Adding parametrized cases for a new domain's valid attributes in test_validator.py
- Adding parametrized template extraction cases in test_jinja_validator.py
- Adding parametrized service/parameter combinations in test_service_validator.py

The test function itself is the unit. Adding cases to it is not a violation.

#### Data Registry Additions Are Minimal Implementation
This project has pure data registries that map domains to valid states, attributes, or catalog entries:
- `device_class_states.py` — domain/device_class → valid states
- `domain_attributes.py` — domain → valid attributes
- `ha_catalog.py` — Jinja filter/test catalog entries

Adding entries to these registries to make a failing test pass is minimal implementation, even if it means adding multiple dictionary keys or dataclass instances. These are data, not logic. Do not block adding a complete domain entry (e.g., all fan attributes) when a test expects that domain to be recognized.

#### Cross-Module Refactoring
The validator modules (validator.py, service_validator.py, jinja_validator.py) share patterns like fuzzy matching, template detection, and issue creation. Applying the same structural refactoring across these related modules in one step is allowed during the refactor phase — it is a single logical change, not multiple unrelated changes.

#### Home Assistant Integration Boilerplate
The following are HA framework requirements, not application logic. They may be created or updated without a prior failing test when they are scaffolding for a feature that IS being test-driven:
- `manifest.json` fields (version, dependencies, requirements)
- `strings.json` / `translations/` entries for new issue types or config options
- `const.py` constant additions (CONF_* keys, domain lists)
- `config_flow.py` schema additions for new options that are tested via integration tests

This does NOT exempt new validation logic, service handlers, or WebSocket commands — those require tests first.

#### Frontend Code (www/)
The frontend uses TypeScript/Lit with Vitest, a separate test stack from pytest. TDD-Guard's pytest reporter does not capture frontend test results. When the agent is editing files under `www/`, do not block based on missing or stale pytest output. Frontend TDD discipline is enforced separately.

### General Information
- Sometimes the test output shows as no tests have been run when a new test is failing due to a missing import or constructor. In such cases, allow the agent to create simple stubs. Ask them if they forgot to create a stub if they are stuck.
- It is never allowed to introduce new logic without evidence of relevant failing tests. However, stubs and simple implementation to make imports and test infrastructure work is fine.
- In the refactor phase, it is perfectly fine to refactor both test and implementation code. That said, completely new functionality is not allowed. Types, clean up, abstractions, and helpers are allowed as long as they do not introduce new behavior.
- Adding types, interfaces, or a constant in order to replace magic values is perfectly fine during refactoring.
- Provide the agent with helpful directions so that they do not get stuck when blocking them.
