# Service Call Validation Design

## Problem Statement

Autodoctor currently validates entity states, attributes, and Jinja templates in automations, but doesn't validate service calls in automation actions. This creates a gap where invalid service calls can silently fail at runtime:

1. **Service doesn't exist** - Typos or removed integrations cause automation failures
2. **Missing required parameters** - Service calls fail when required fields are omitted
3. **Wrong parameter types** - Type mismatches cause errors (e.g., string instead of number)
4. **Unknown parameters** - Typos in parameter names go undetected until runtime

## Solution Overview

Add service call validation to Autodoctor's validation pipeline by:

1. **Extracting service calls** from automation actions
2. **Validating against HA service registry** at parse time
3. **Reporting issues** through existing validation pipeline

This integrates seamlessly with existing state and template validation.

## Design

### Architecture

Service call validation integrates into the existing validation flow:

```
Automation config
    ↓
AutomationAnalyzer.extract_service_calls()
    ↓
ServiceCall objects
    ↓
ServiceCallValidator.validate()
    ↓                ↑
ValidationIssues    Service Registry (hass.services)
    ↓
Reporter → WebSocket API
```

Components run during the same validation cycle as state and template validation, producing `ValidationIssue` objects that flow through the existing reporter.

---

### Part 1: Service Call Extraction

#### New Component: `ServiceCallExtractor`

Parses automation actions to identify service calls in `analyzer.py`.

**Supported Action Types:**

1. Direct service calls
2. Service templates
3. Choose/if-then-else branches
4. Repeat/while/until loops
5. Parallel/sequence groups

**Extraction Logic:**

```python
def extract_service_calls(self, automation: dict) -> list[ServiceCall]:
    """Extract all service calls from automation actions."""
    service_calls = []
    actions = automation.get("action", [])

    for idx, action in enumerate(actions):
        location = f"action[{idx}]"
        self._extract_from_action(action, location, automation, service_calls)

    return service_calls

def _extract_from_action(
    self,
    action: dict,
    location: str,
    automation: dict,
    service_calls: list[ServiceCall]
) -> None:
    """Recursively extract service calls from action structure."""
    # Direct service call
    if "service" in action:
        service_calls.append(ServiceCall(
            automation_id=automation.get("id", "unknown"),
            automation_name=automation.get("alias", "Unknown"),
            service=action["service"],
            location=location,
            target=action.get("target"),
            data=action.get("data") or action.get("service_data"),
            is_template=self._is_template(action["service"])
        ))

    # Choose branches
    if "choose" in action:
        for idx, branch in enumerate(action["choose"]):
            branch_location = f"{location}.choose[{idx}]"
            for seq_idx, seq_action in enumerate(branch.get("sequence", [])):
                self._extract_from_action(
                    seq_action,
                    f"{branch_location}.sequence[{seq_idx}]",
                    automation,
                    service_calls
                )

    # If-then-else
    if "if" in action:
        for seq_idx, seq_action in enumerate(action.get("then", [])):
            self._extract_from_action(
                seq_action,
                f"{location}.then[{seq_idx}]",
                automation,
                service_calls
            )
        for seq_idx, seq_action in enumerate(action.get("else", [])):
            self._extract_from_action(
                seq_action,
                f"{location}.else[{seq_idx}]",
                automation,
                service_calls
            )

    # Repeat
    if "repeat" in action:
        for seq_idx, seq_action in enumerate(action["repeat"].get("sequence", [])):
            self._extract_from_action(
                seq_action,
                f"{location}.repeat.sequence[{seq_idx}]",
                automation,
                service_calls
            )

    # Parallel/sequence
    for key in ("parallel", "sequence"):
        if key in action:
            for seq_idx, seq_action in enumerate(action[key]):
                self._extract_from_action(
                    seq_action,
                    f"{location}.{key}[{seq_idx}]",
                    automation,
                    service_calls
                )

def _is_template(self, value: str) -> bool:
    """Check if value contains Jinja template syntax."""
    return "{{" in value or "{%" in value
```

---

### Part 2: Data Models

#### New dataclass in `models.py`

```python
@dataclass
class ServiceCall:
    """A service call found in an automation action."""

    automation_id: str
    automation_name: str
    service: str  # e.g., "light.turn_on" or "{{ dynamic_service }}"
    location: str  # e.g., "action[0].choose[1].sequence[2]"
    target: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    is_template: bool = False
    source_line: int | None = None
```

#### New IssueType enum values in `models.py`

```python
class IssueType(str, Enum):
    """Types of validation issues."""

    # ... existing values ...

    SERVICE_NOT_FOUND = "service_not_found"
    SERVICE_MISSING_REQUIRED_PARAM = "service_missing_required_param"
    SERVICE_INVALID_PARAM_TYPE = "service_invalid_param_type"
    SERVICE_UNKNOWN_PARAM = "service_unknown_param"
```

---

### Part 3: Service Validation

#### New Component: `ServiceCallValidator`

Validates service calls against the HA service registry.

**Initialization:**

```python
class ServiceCallValidator:
    """Validates service calls against the Home Assistant service registry."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._schema_cache: dict[str, dict] = {}

    def _get_service_schema(self, domain: str, service: str) -> dict | None:
        """Get service schema from registry with caching."""
        cache_key = f"{domain}.{service}"

        if cache_key in self._schema_cache:
            return self._schema_cache[cache_key]

        # Check if service exists
        if not self.hass.services.has_service(domain, service):
            return None

        # Get schema if available
        service_desc = self.hass.services.async_services().get(domain, {}).get(service)
        if service_desc:
            schema = service_desc.get("fields", {})
            self._schema_cache[cache_key] = schema
            return schema

        return {}
```

**Validation Methods:**

```python
def validate_service_calls(
    self,
    service_calls: list[ServiceCall]
) -> list[ValidationIssue]:
    """Validate all service calls and return issues."""
    issues = []

    for call in service_calls:
        # Skip templated service names (can't validate at parse time)
        if call.is_template:
            continue

        # Parse domain.service
        if "." not in call.service:
            issues.append(self._create_issue(
                call,
                Severity.ERROR,
                IssueType.SERVICE_NOT_FOUND,
                f"Invalid service format: '{call.service}' (expected 'domain.service')"
            ))
            continue

        domain, service = call.service.split(".", 1)

        # Check 1: Service exists
        if not self.hass.services.has_service(domain, service):
            issues.append(self._create_issue(
                call,
                Severity.ERROR,
                IssueType.SERVICE_NOT_FOUND,
                f"Service '{call.service}' not found"
            ))
            continue

        # Get schema for parameter validation
        schema = self._get_service_schema(domain, service)

        # Skip parameter validation if no schema available
        if schema is None:
            continue

        # Check 2: Required parameters
        issues.extend(self._validate_required_params(call, schema))

        # Check 3: Parameter types
        issues.extend(self._validate_param_types(call, schema))

        # Check 4: Unknown parameters
        issues.extend(self._validate_unknown_params(call, schema))

    return issues

def _validate_required_params(
    self,
    call: ServiceCall,
    schema: dict
) -> list[ValidationIssue]:
    """Check that all required parameters are provided."""
    issues = []
    data = call.data or {}
    target = call.target or {}

    for param_name, param_schema in schema.items():
        # Check if parameter is required
        if param_schema.get("required", False):
            # Check in both data and target
            if param_name not in data and param_name not in target:
                issues.append(self._create_issue(
                    call,
                    Severity.WARNING,
                    IssueType.SERVICE_MISSING_REQUIRED_PARAM,
                    f"Missing required parameter '{param_name}' for service '{call.service}'"
                ))

    return issues

def _validate_param_types(
    self,
    call: ServiceCall,
    schema: dict
) -> list[ValidationIssue]:
    """Validate parameter value types match schema."""
    issues = []
    data = call.data or {}

    for param_name, value in data.items():
        # Skip templated values (can't validate at parse time)
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            continue

        # Get expected type from schema
        if param_name not in schema:
            continue

        param_schema = schema[param_name]
        expected_type = param_schema.get("selector", {})

        # Validate basic types
        validation_result = self._check_type_match(value, expected_type)
        if not validation_result["valid"]:
            issues.append(self._create_issue(
                call,
                Severity.WARNING,
                IssueType.SERVICE_INVALID_PARAM_TYPE,
                f"Parameter '{param_name}' has type {validation_result['actual']} "
                f"but expected {validation_result['expected']}"
            ))

    return issues

def _validate_unknown_params(
    self,
    call: ServiceCall,
    schema: dict
) -> list[ValidationIssue]:
    """Check for parameters not in service schema."""
    issues = []
    data = call.data or {}

    for param_name in data.keys():
        if param_name not in schema and param_name not in ("entity_id", "target"):
            issues.append(self._create_issue(
                call,
                Severity.WARNING,
                IssueType.SERVICE_UNKNOWN_PARAM,
                f"Unknown parameter '{param_name}' for service '{call.service}'"
            ))

    return issues

def _check_type_match(self, value: Any, expected_type: dict) -> dict:
    """Check if value matches expected type from selector."""
    # Map selector types to Python types
    type_map = {
        "number": (int, float),
        "text": str,
        "boolean": bool,
        "object": dict,
        "select": (str, list),
    }

    # Extract selector type
    selector_type = None
    for key in expected_type.keys():
        if key in type_map:
            selector_type = key
            break

    if selector_type is None:
        return {"valid": True}

    expected_types = type_map[selector_type]
    if not isinstance(expected_types, tuple):
        expected_types = (expected_types,)

    if not isinstance(value, expected_types):
        return {
            "valid": False,
            "expected": selector_type,
            "actual": type(value).__name__
        }

    return {"valid": True}

def _create_issue(
    self,
    call: ServiceCall,
    severity: Severity,
    issue_type: IssueType,
    message: str
) -> ValidationIssue:
    """Create a ValidationIssue from a service call problem."""
    return ValidationIssue(
        severity=severity,
        automation_id=call.automation_id,
        automation_name=call.automation_name,
        entity_id="",  # Service calls don't always have entity_id
        location=call.location,
        message=message,
        issue_type=issue_type
    )
```

---

### Part 4: Integration Points

#### Modified `__init__.py`

Add service validator to setup:

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # ... existing setup ...

    # Initialize service validator
    service_validator = ServiceCallValidator(hass)

    hass.data[DOMAIN] = {
        "analyzer": analyzer,
        "validator": validator,
        "jinja_validator": jinja_validator,
        "service_validator": service_validator,  # NEW
        "knowledge_base": knowledge_base,
        "reporter": reporter,
        "suppression_store": suppression_store,
        "learned_states_store": learned_states_store,
    }
```

#### Modified `async_validate_all()` in `__init__.py`

Add service validation to validation pipeline:

```python
async def async_validate_all(hass: HomeAssistant) -> list:
    """Validate all automations."""
    data = hass.data.get(DOMAIN, {})
    analyzer = data.get("analyzer")
    validator = data.get("validator")
    jinja_validator = data.get("jinja_validator")
    service_validator = data.get("service_validator")  # NEW
    reporter = data.get("reporter")
    knowledge_base = data.get("knowledge_base")

    # ... existing validation logic ...

    # Run service call validation (NEW)
    if service_validator:
        try:
            service_calls = []
            for automation in automations:
                service_calls.extend(analyzer.extract_service_calls(automation))

            service_issues = service_validator.validate_service_calls(service_calls)
            all_issues.extend(service_issues)
            _LOGGER.debug(
                "Service validation: found %d issues in %d service calls",
                len(service_issues),
                len(service_calls)
            )
        except Exception as ex:
            _LOGGER.exception("Service validation failed: %s", ex)

    # ... rest of validation ...
```

---

### Part 5: Error Handling

**Template Handling:**
- Service name is templated → Skip validation entirely
- Parameter values are templated → Skip type validation for that parameter
- Log INFO when skipping templated service calls

**Missing Schema:**
- Service exists but no schema → Only validate existence, skip parameters
- Log DEBUG noting schema unavailable

**Service Registry:**
- Service registry not available → Defer validation
- Handle gracefully during initialization

**Performance:**
- Cache service schemas to avoid repeated lookups
- Limit to ~1000 service calls per validation run
- Validate concurrently with other checks

---

## File Changes Summary

| File | Change |
|------|--------|
| `models.py` | NEW - `ServiceCall` dataclass, new `IssueType` values |
| `analyzer.py` | MODIFIED - Add `extract_service_calls()` method |
| `validator.py` | NEW - `ServiceCallValidator` class (or new file) |
| `__init__.py` | MODIFIED - Initialize validator, add to pipeline |
| `const.py` | MODIFIED - Add new issue type constants if needed |

---

## Testing Strategy

### Unit Tests: `test_service_validator.py`

1. **Extraction tests:**
   - Direct service calls
   - Nested in choose/if/repeat/parallel
   - Template detection
   - Complex nested structures

2. **Validation tests:**
   - Service not found → ERROR
   - Missing required parameter → WARNING
   - Invalid parameter type → WARNING
   - Unknown parameter → WARNING
   - Templated service names → skip
   - Templated parameter values → skip type check

3. **Edge cases:**
   - Service without schema
   - Empty actions
   - Malformed service names
   - Target vs data parameters

### Integration Tests: `test_init.py`

1. End-to-end validation with service calls
2. Service registry integration
3. ValidationIssue generation
4. WebSocket API returns service issues

### Coverage Target

95%+ coverage for new `ServiceCallValidator` and extraction logic.

---

## Severity Mapping

| Issue Type | Severity | Rationale |
|------------|----------|-----------|
| SERVICE_NOT_FOUND | ERROR | Critical - automation will fail |
| SERVICE_MISSING_REQUIRED_PARAM | WARNING | May fail, but some services have smart defaults |
| SERVICE_INVALID_PARAM_TYPE | WARNING | May be coerced or handled gracefully |
| SERVICE_UNKNOWN_PARAM | WARNING | Ignored at runtime, might be typo |

---

## Future Enhancements

1. **Service suggestion engine** - Fuzzy match to suggest correct service names
2. **Parameter suggestion** - Suggest correct parameter names for typos
3. **Target expansion** - Validate entity_id lists from device/area targets
4. **Template analysis** - Parse simple templates to extract service names
5. **Service registry monitoring** - Re-validate when services are registered/unregistered

---

## Migration

No migration needed. Feature is additive:
- Existing validations continue to work
- Service validation adds new issue types
- No breaking changes to data models or APIs
- Frontend automatically displays new issue types via existing rendering logic
