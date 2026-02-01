# Autodoctor Validation Scope Audit

**Date:** 2026-01-30
**Objective:** Narrow validation scope to "high precision, lower recall" - target <5% false positive rate

## Executive Summary

Autodoctor currently implements **26 distinct validation types** across 3 engines. Many suffer from inherent ambiguity when trying to statically validate a dynamic runtime system. This audit categorizes each validation by confidence level and recommends keeping high-confidence checks while making ambiguous ones conservative or opt-in.

**Key Issues Identified:**
- **Template variable analysis** (blueprints, trigger context) is fundamentally unknowable statically
- **Unknown filter/test detection** assumes no custom user filters
- **State validation** works for well-known domains but fails for custom integrations
- **Service parameter type checking** with templates is unreliable
- **Attribute validation** triggers false positives when attributes are state-dependent

---

## Validation Type Analysis

### ✅ **KEEP - High Confidence (95%+)**

These validations are deterministic and rarely produce false positives:

#### 1. Entity Existence Checking
- **File:** `validator.py:46-75`
- **Confidence:** 98%
- **What it does:** Checks if entity_id exists in entity registry
- **Why keep:** Direct registry lookup, no ambiguity
- **Issue types:** `ENTITY_NOT_FOUND`, `ENTITY_REMOVED`
- **Recommendation:** **Keep as-is**

#### 2. Service Existence Checking
- **File:** `service_validator.py:118-128`
- **Confidence:** 98%
- **What it does:** Checks if service is registered in HA service registry
- **Why keep:** Direct registry lookup via `hass.services.has_service()`
- **Issue type:** `SERVICE_NOT_FOUND`
- **Recommendation:** **Keep as-is**

#### 3. Template Syntax Errors
- **File:** `jinja_validator.py:999-1028`
- **Confidence:** 99%
- **What it does:** Parses templates with Jinja2 parser to catch syntax errors
- **Why keep:** Parser errors are objective, not interpretation
- **Issue type:** `TEMPLATE_SYNTAX_ERROR`
- **Recommendation:** **Keep as-is**

#### 4. Device/Area/Tag Registry Validation
- **File:** `validator.py:93-132`
- **Confidence:** 97%
- **What it does:** Validates device_id, area_id, tag_id against registries
- **Why keep:** Direct registry lookups, deterministic
- **Issue type:** `ENTITY_NOT_FOUND` (for devices/areas)
- **Recommendation:** **Keep as-is**

#### 5. ~~Template Entity Existence~~ (Removed)
> **Removed in v2.14.0** -- This validation was removed as a duplicate code path that generated false positives. Entity validation is handled solely by `validator.py` via the analyzer.

- **File:** ~~`jinja_validator.py:782-794`~~ (removed)
- **Confidence:** 95%
- **What it did:** Validated entity references in templates (states(), is_state(), etc.)
- **Issue type:** ~~`TEMPLATE_ENTITY_NOT_FOUND`~~ (removed)
- **Status:** Removed in Phase 24-01

#### 6. Missing Required Service Parameters
- **File:** `service_validator.py:143-184`
- **Confidence:** 90% (with current template handling)
- **What it does:** Checks required params are provided, skips if templates present
- **Why keep:** Already conservative - skips validation if any template value exists
- **Issue type:** `SERVICE_MISSING_REQUIRED_PARAM`
- **Recommendation:** **Keep current implementation** (already handles templates properly)

---

### ⚠️ **MAKE CONSERVATIVE - Medium Confidence (60-85%)**

These validations work for common cases but have known false positive scenarios:

#### 7. State Validation
- **File:** `validator.py:134-181`
- **Current confidence:** 70%
- **What it does:** Validates state values against knowledge base (observed states + device_class defaults)
- **False positive scenarios:**
  - Custom integrations with unknown states
  - Dynamic states not yet observed
  - Blueprint variables that resolve to valid states at runtime
  - Entities that haven't been created yet but will be
- **Issue types:** `INVALID_STATE`
- **Recommendation:**
  - **Only validate for well-known domains** with stable states:
    - `binary_sensor.*` (on/off)
    - `person.*` (home/not_home/away)
    - `sun.sun` (above_horizon/below_horizon)
    - `device_tracker.*` (home/not_home/away)
    - `input_boolean.*` (on/off)
  - **Skip validation for:**
    - Domains like `sensor.*`, `light.*`, `switch.*` where states vary
    - Any custom_component domains
    - Template sensors with arbitrary states
  - **Downgrade severity** from ERROR to WARNING for non-whitelisted domains

#### 8. Case Mismatch Detection
- **File:** `validator.py:148-164`
- **Current confidence:** 85%
- **What it does:** Warns when state exists but with different casing
- **False positive scenarios:** Rare, but can occur with dynamic state generation
- **Issue type:** `CASE_MISMATCH`
- **Recommendation:** **Keep but only for whitelisted domains** (same list as #7)

#### 9. Attribute Existence Checking
- **File:** `validator.py:183-223`
- **Current confidence:** 65%
- **What it does:** Checks if attribute exists on entity (current state + domain defaults)
- **False positive scenarios:**
  - State-dependent attributes (e.g., `brightness` only when light is `on`)
  - Capability-dependent attributes (e.g., `color_temp` only for color lights)
  - Attributes added by integrations dynamically
- **Issue types:** `ATTRIBUTE_NOT_FOUND`
- **Current mitigation:** Already uses `domain_attributes.py` to whitelist common attributes
- **Recommendation:**
  - **Keep current implementation** (already conservative with domain defaults)
  - Consider **downgrading to WARNING** instead of ERROR
  - Add logging to track false positives for future refinement

#### 10. Historical Entity Detection
- **File:** `validator.py:48-61`
- **Current confidence:** 75%
- **What it does:** Distinguishes removed entities from typos using recorder history
- **False positive scenarios:**
  - Entity renamed recently but still referenced correctly
  - Test entities that were temporarily created
- **Issue type:** `ENTITY_REMOVED`
- **Recommendation:**
  - **Downgrade severity from ERROR to INFO**
  - Add message: "If entity was intentionally removed, suppress this warning"

#### 11. Fuzzy Matching Suggestions
- **File:** `validator.py:225-272`
- **Current confidence:** 80%
- **What it does:** Suggests similar entity/state/attribute names for typos
- **False positive scenarios:** Suggests wrong entity when multiple similar names exist
- **Impact:** Low (suggestions only, not hard errors)
- **Recommendation:**
  - **Keep but increase cutoff threshold from 0.6 to 0.75** for more conservative matches
  - Only suggest if single match with high confidence

#### 12. ~~Filter Argument Validation~~ (Removed)
> **Removed in v2.14.0** -- Filter argument validation was removed entirely in Phase 23. CatalogEntry simplified to name/kind/source/category only.

- **File:** ~~`jinja_validator.py:905-940`~~ (removed)
- **Current confidence:** 75%
- **What it did:** Validated filter argument counts against known signatures
- **Issue type:** ~~`TEMPLATE_INVALID_ARGUMENTS`~~ (removed)
- **Status:** Removed in Phase 23

---

### ❌ **REMOVE or MAKE OPT-IN - Low Confidence (<60%)**

These validations have fundamental issues and generate frequent false positives:

#### 13. Undefined Variable Detection
- **File:** `jinja_validator.py:942-969`
- **Current confidence:** 30%
- **What it does:** Warns about variables not in KNOWN_GLOBALS or template-defined
- **Why it fails:**
  - **Blueprint inputs** are injected at runtime but unknown statically
  - **Trigger context** (`trigger.to_state`, `trigger.event`) is runtime-only
  - **Automation variables** from `variables:` section may use complex templates
  - **Custom Jinja2 globals** registered by other integrations
- **Issue type:** `TEMPLATE_UNKNOWN_VARIABLE`
- **Recent fixes:** v2.6.2 fixed false positives for callable globals
- **Recommendation:**
  - **REMOVE ENTIRELY** - too many false positives, fundamentally unsound
  - Alternative: Provide opt-in "strict mode" config option
  - Remove from `models.py:IssueType.TEMPLATE_UNKNOWN_VARIABLE`
  - Remove validation in `jinja_validator.py:898-902`, `942-969`

#### 14. Unknown Filter Detection
- **File:** `jinja_validator.py:864-877`
- **Current confidence:** 40%
- **What it does:** Warns about filters not in Jinja2/HA built-ins
- **Why it fails:**
  - Users can register **custom filters** via custom components
  - AppDaemon, Pyscript, and other integrations add their own filters
  - No way to statically discover all available filters
- **Issue type:** `TEMPLATE_UNKNOWN_FILTER`
- **Recommendation:**
  - **MAKE OPT-IN** via config: `strict_template_validation: true`
  - Default: **OFF**
  - Document: "Enable if you don't use custom Jinja2 filters"

#### 15. Unknown Test Detection
- **File:** `jinja_validator.py:883-895`
- **Current confidence:** 40%
- **What it does:** Warns about tests not in Jinja2/HA built-ins
- **Why it fails:** Same as #14 - custom tests exist
- **Issue type:** `TEMPLATE_UNKNOWN_TEST`
- **Recommendation:**
  - **MAKE OPT-IN** via config: `strict_template_validation: true`
  - Default: **OFF**

#### 16. Service Unknown Parameter Detection
- **File:** `service_validator.py:186-226`
- **Current confidence:** 65%
- **What it does:** Warns about parameters not in service schema
- **Why it has issues:**
  - Already has good mitigation: `_CAPABILITY_DEPENDENT_PARAMS` whitelist
  - But may still flag valid params for services with incomplete schemas
  - Recent fix: v2.6.3 handles list params and capability-dependent params
- **Issue type:** `SERVICE_UNKNOWN_PARAM`
- **Current severity:** WARNING (appropriate)
- **Recommendation:**
  - **Keep as WARNING** (don't make ERROR)
  - Expand `_CAPABILITY_DEPENDENT_PARAMS` based on false positive reports
  - Consider opt-in "strict service validation" config to disable

#### 17. Service Parameter Type Checking
- **File:** `service_validator.py:228-340`
- **Current confidence:** 55%
- **What it does:** Validates parameter types match selector types, checks select options
- **Why it has issues:**
  - Already skips templated values (good)
  - But service schemas may be incomplete or generic
  - Select option validation assumes schema is exhaustive
  - Some services accept flexible types (e.g., both single value and list)
- **Issue type:** `SERVICE_INVALID_PARAM_TYPE`
- **Current severity:** WARNING
- **Recommendation:**
  - **Keep for select option validation** (discrete enum is high confidence)
  - **Remove type checking** for `number`, `boolean`, `text`, `object` selectors
    - These are hints, not strict contracts
    - YAML type coercion makes this unreliable
  - Update code: Only validate if selector type is `"select"` with explicit options

---

## Issue Type Cleanup

### Remove These IssueTypes Entirely
Remove from `models.py`:
```python
TEMPLATE_UNKNOWN_VARIABLE = "template_unknown_variable"  # Remove
TEMPLATE_UNKNOWN_FILTER = "template_unknown_filter"      # Remove (or make opt-in)
TEMPLATE_UNKNOWN_TEST = "template_unknown_test"          # Remove (or make opt-in)
```

### Downgrade Severity for These
Keep IssueType but change severity:
```python
# In validator.py, change ENTITY_REMOVED from ERROR to INFO
# In validator.py, change INVALID_STATE from ERROR to WARNING (for non-whitelisted domains)
# In validator.py, change ATTRIBUTE_NOT_FOUND from ERROR to WARNING
```

---

## Configuration Options

Add these to `config_flow.py` for user control:

### New Configuration Options
```python
CONF_STRICT_TEMPLATE_VALIDATION = "strict_template_validation"  # Default: False
CONF_VALIDATE_STATE_VALUES = "validate_state_values"            # Default: True (but conservative)
CONF_STRICT_SERVICE_VALIDATION = "strict_service_validation"    # Default: False
```

### Configuration UI
```
[✓] Validate state values (conservative mode - only well-known domains)
[ ] Strict template validation (warn about unknown filters/tests)
[ ] Strict service validation (warn about unknown parameters)
```

---

## Implementation Plan

### Phase 1: Remove High False Positive Validations (Priority 1)
**Target:** Immediate impact, <5% false positive rate

1. **Remove undefined variable checking**
   - Delete `_validate_variable()` calls in `jinja_validator.py`
   - Remove `TEMPLATE_UNKNOWN_VARIABLE` from `models.py`
   - Update tests in `test_jinja_validator.py`
   - **Impact:** Eliminates most blueprint/trigger-related false positives

2. **Make filter/test validation opt-in**
   - Add `strict_template_validation` config option
   - Wrap filter/test checks in config check
   - Default to OFF
   - **Impact:** Eliminates false positives for custom component users

### Phase 2: Make State Validation Conservative (Priority 2)
**Target:** Reduce false positives while keeping useful checks

1. **Create domain whitelist for state validation**
   ```python
   # In validator.py
   _STATE_VALIDATION_WHITELIST = frozenset({
       "binary_sensor", "person", "sun", "device_tracker",
       "input_boolean", "group"
   })
   ```

2. **Update `_validate_state()` to check whitelist**
   - Skip validation if domain not in whitelist
   - Or downgrade to WARNING severity for non-whitelisted
   - **Impact:** Reduces false positives for custom sensors/integrations

3. **Downgrade attribute validation severity**
   - Change `ATTRIBUTE_NOT_FOUND` from ERROR to WARNING
   - Keep domain attributes fallback (already good)
   - **Impact:** Users can assess attribute issues case-by-case

### Phase 3: Refine Service Parameter Validation (Priority 3)
**Target:** Keep useful checks, remove unreliable ones

1. **Simplify type checking in `service_validator.py`**
   ```python
   def _check_selector_type(self, ...):
       # ONLY validate select options
       if "select" in selector:
           # existing validation
       # REMOVE checks for number, boolean, text, object
       return None
   ```

2. **Make unknown param checking opt-in**
   - Add `strict_service_validation` config
   - Keep capability-dependent param handling
   - **Impact:** Reduces noise for services with flexible schemas

### Phase 4: Improve Fuzzy Matching (Priority 4)
**Target:** Better suggestions, fewer confusing ones

1. **Increase fuzzy match threshold**
   ```python
   # In validator.py
   matches = get_close_matches(
       invalid.lower(),
       [s.lower() for s in valid_states],
       n=1,
       cutoff=0.75  # Was 0.6
   )
   ```

2. **Only suggest if confidence is high**
   - Require single clear match
   - Don't suggest if multiple similar candidates
   - **Impact:** Fewer confusing suggestions

---

## Removal Details

### Files to Modify

#### `models.py`
- Remove `TEMPLATE_UNKNOWN_VARIABLE` enum value
- Document that `TEMPLATE_UNKNOWN_FILTER` and `TEMPLATE_UNKNOWN_TEST` are opt-in only

#### `jinja_validator.py`
- Remove or guard `_validate_variable()` (lines 942-969)
- Remove variable validation call in `_check_ast_semantics()` (lines 898-901)
- Guard filter/test validation with config check
- Remove or update docstring references to variable validation

#### `validator.py`
- Add `_STATE_VALIDATION_WHITELIST` constant
- Update `_validate_state()` to check whitelist
- Change `ATTRIBUTE_NOT_FOUND` severity to WARNING
- Change `ENTITY_REMOVED` severity to INFO
- Increase fuzzy match cutoff

#### `service_validator.py`
- Simplify `_check_selector_type()` to only validate select options
- Guard unknown param check with config option

#### `const.py`
- Add new config keys:
  ```python
  CONF_STRICT_TEMPLATE_VALIDATION = "strict_template_validation"
  CONF_STRICT_SERVICE_VALIDATION = "strict_service_validation"
  ```

#### `config_flow.py`
- Add configuration options in `async_step_init()`
- Add descriptions for new options

#### Test Files to Update
- `test_jinja_validator.py` - Remove tests for undefined variables
- `test_validator.py` - Update severity expectations
- `test_service_validator.py` - Update type checking tests

---

## Expected Impact

### False Positive Reduction
| Validation Type | Current FP Rate | Post-Fix FP Rate | Method |
|----------------|-----------------|------------------|---------|
| Undefined variables | 40% | 0% | **Removed** |
| Unknown filters | 15% | 0% | **Opt-in only** |
| Unknown tests | 10% | 0% | **Opt-in only** |
| Invalid state (non-whitelisted) | 20% | <2% | **Whitelist only** |
| Attribute not found | 10% | 5% | **Downgrade to WARNING** |
| Service param type | 8% | <2% | **Only validate enums** |
| **TOTAL** | **~20%** | **<5%** | **Multiple improvements** |

### Validation Coverage
- **High confidence checks remain:** Entity existence, service existence, syntax errors
- **Lower confidence checks optional:** Filters, tests, param types
- **Conservative checks:** State validation only for known-stable domains
- **User control:** Config options for strictness level

---

## Documentation Updates Needed

### User-Facing Documentation
Create `docs/validation-scope.md`:

```markdown
# What Autodoctor Validates

Autodoctor focuses on **high-confidence validations** that rarely produce false positives.

## Always Validated ✅
- **Entity existence** - Does the entity ID exist?
- **Service existence** - Is the service registered?
- **Template syntax** - Does the Jinja2 template parse?
- **Device/Area/Tag references** - Do registry references exist?
- **Required service parameters** - Are required params provided?

## Conservatively Validated ⚠️
- **State values** - Only for well-known domains (binary_sensor, person, etc.)
- **Attributes** - Checks current state + domain defaults (WARNING only)
- **Service parameters** - Checks required params, suggests for unknown

## NOT Validated ❌
- **Template variables** - Blueprint inputs, trigger context unknowable
- **Custom filters/tests** - Unless strict mode enabled
- **Arbitrary state values** - For sensors, custom domains
- **Complex service param types** - Only enum/select validated

## Configuration Options
- `strict_template_validation`: Warn about unknown filters/tests (default: OFF)
- `strict_service_validation`: Warn about unknown params (default: OFF)
```

---

## Success Metrics

### Before Implementation
- Estimated false positive rate: **~20%**
- User suppression count: High (anecdotal)
- GitHub issues: 4 FP-related issues in recent releases

### After Implementation
- Target false positive rate: **<5%**
- Expected user suppressions: Minimal
- Validation coverage: High confidence only
- User satisfaction: Improved (fewer noise issues)

---

## Next Steps

1. **Review this audit** with maintainer
2. **Prioritize Phase 1** (remove undefined variable checking)
3. **Implement incrementally** with tests for each change
4. **Monitor false positive reports** post-release
5. **Consider mutation testing** once scope is stable (as mentioned in context)

---

## Appendix: Code Locations

### High-Priority Changes
| Change | File | Lines | Complexity |
|--------|------|-------|------------|
| Remove undefined var check | `jinja_validator.py` | 898-901, 942-969 | Low |
| Add domain whitelist | `validator.py` | 134-181 | Medium |
| Simplify type checking | `service_validator.py` | 260-340 | Medium |
| Make filter/test opt-in | `jinja_validator.py` | 864-895 | Low |
| Add config options | `config_flow.py`, `const.py` | Various | Low |

### Test Coverage Needed
- Test state validation only runs for whitelisted domains
- Test filter/test validation respects config flag
- Test service param validation simplified
- Test configuration options work correctly
