# Validation Narrowing Implementation Checklist

## Phase 1: Remove Undefined Variable Checking (Priority: CRITICAL)

**Goal:** Eliminate the #1 source of false positives

### Code Changes

- [ ] **models.py**
  - [ ] Remove `TEMPLATE_UNKNOWN_VARIABLE = "template_unknown_variable"` (line 30)
  - [ ] Update docstring to document removal reason

- [ ] **jinja_validator.py**
  - [ ] Remove `_validate_variable()` method (lines 942-969)
  - [ ] Remove variable validation call in `_check_ast_semantics()` (lines 898-901)
  - [ ] Remove from docstring (if mentioned)
  - [ ] Remove `known_vars` parameter tracking (simplify the code)

- [ ] **Test Updates**
  - [ ] Remove `test_jinja_validator.py::test_undefined_variable_*` tests
  - [ ] Remove assertions expecting `TEMPLATE_UNKNOWN_VARIABLE` issues
  - [ ] Verify no tests fail after removal

### Verification
- [ ] Run `pytest tests/test_jinja_validator.py -v`
- [ ] Test with known blueprint automation
- [ ] Verify no variable-related false positives

---

## Phase 2: Make Filter/Test Validation Opt-In (Priority: HIGH)

**Goal:** Stop flagging custom filters/tests by default

### Code Changes

- [ ] **const.py**
  - [ ] Add `CONF_STRICT_TEMPLATE_VALIDATION = "strict_template_validation"`
  - [ ] Add to `DEFAULT_OPTIONS = {CONF_STRICT_TEMPLATE_VALIDATION: False}`

- [ ] **config_flow.py**
  - [ ] Add checkbox option in `async_step_init()`:
    ```python
    vol.Optional(
        CONF_STRICT_TEMPLATE_VALIDATION,
        default=options.get(CONF_STRICT_TEMPLATE_VALIDATION, False),
    ): bool
    ```
  - [ ] Add description: "Warn about unknown Jinja2 filters and tests (disable if using custom components)"

- [ ] **jinja_validator.py**
  - [ ] Pass config to `JinjaValidator.__init__(self, hass, config=None)`
  - [ ] Store `self._strict_validation = config.get(CONF_STRICT_TEMPLATE_VALIDATION, False) if config else False`
  - [ ] Wrap filter checking in `if self._strict_validation:` (lines 864-881)
  - [ ] Wrap test checking in `if self._strict_validation:` (lines 883-895)
  - [ ] Update docstring to document opt-in behavior

- [ ] **__init__.py** (integration entry point)
  - [ ] Pass options to `JinjaValidator` when instantiating
  - [ ] Update on config changes

### Verification
- [ ] Test default behavior (filters/tests not checked)
- [ ] Test with strict mode enabled (checks work)
- [ ] Test config option persists across restarts

---

## Phase 3: Conservative State Validation (Priority: HIGH)

**Goal:** Only validate states for well-known, stable domains

### Code Changes

- [ ] **validator.py**
  - [ ] Add constant after imports:
    ```python
    # Domains with stable, well-defined state values
    _STATE_VALIDATION_WHITELIST = frozenset({
        "binary_sensor",  # on/off
        "person",         # home/not_home/away/unknown
        "sun",            # above_horizon/below_horizon
        "device_tracker", # home/not_home/away
        "input_boolean",  # on/off
        "group",          # on/off
    })
    ```

  - [ ] Update `_validate_state()` method (lines 134-181):
    ```python
    def _validate_state(self, ref: StateReference) -> list[ValidationIssue]:
        """Validate the expected state."""
        issues: list[ValidationIssue] = []
        valid_states = self.knowledge_base.get_valid_states(ref.entity_id)

        if valid_states is None:
            return issues

        # Only validate for whitelisted domains with stable states
        domain = self.knowledge_base.get_domain(ref.entity_id)
        if domain not in _STATE_VALIDATION_WHITELIST:
            _LOGGER.debug(
                "Skipping state validation for %s (domain %s not in whitelist)",
                ref.entity_id, domain
            )
            return issues

        # ... rest of existing validation logic
    ```

  - [ ] Update `ENTITY_REMOVED` severity from ERROR to INFO (line 53)
  - [ ] Update `ATTRIBUTE_NOT_FOUND` severity from ERROR to WARNING (line 211)

- [ ] **jinja_validator.py**
  - [ ] Apply same domain whitelist to `_validate_entity_references()` (lines 813-843)
  - [ ] Import `_STATE_VALIDATION_WHITELIST` from validator
  - [ ] Add domain check before state validation

### Verification
- [ ] Test binary_sensor state validation still works
- [ ] Test sensor.* state validation is skipped
- [ ] Test light.* state validation is skipped
- [ ] Verify ENTITY_REMOVED is now INFO level
- [ ] Verify ATTRIBUTE_NOT_FOUND is now WARNING level

---

## Phase 4: Simplify Service Parameter Type Checking (Priority: MEDIUM)

**Goal:** Only validate discrete enum/select options, not basic types

### Code Changes

- [ ] **service_validator.py**
  - [ ] Simplify `_check_selector_type()` method (lines 260-340):
    ```python
    def _check_selector_type(
        self,
        call: ServiceCall,
        param_name: str,
        value: Any,
        selector: dict[str, Any],
    ) -> ValidationIssue | None:
        """Check if a value matches expected selector type.

        Only validates select options (discrete enums) as these are
        deterministic. Basic type checking (number, boolean, text) is
        unreliable due to YAML type coercion.
        """
        # Check select options (discrete enum - high confidence)
        if "select" in selector:
            # ... existing select validation ...
            return ...

        # Skip validation for other selector types (number, boolean, text, object)
        # These are hints, not strict contracts
        return None
    ```

  - [ ] Remove `_SELECTOR_TYPE_MAP` constant (lines 21-26) or document as unused
  - [ ] Update docstring to explain why only select is validated

### Verification
- [ ] Test select option validation still works
- [ ] Test number/boolean/text type checking is skipped
- [ ] Verify no false positives for flexible service params

---

## Phase 5: Make Service Unknown Param Checking Opt-In (Priority: LOW)

**Goal:** Allow users to disable unknown param warnings if desired

### Code Changes

- [ ] **const.py**
  - [ ] Add `CONF_STRICT_SERVICE_VALIDATION = "strict_service_validation"`
  - [ ] Add to defaults: `CONF_STRICT_SERVICE_VALIDATION: False`

- [ ] **config_flow.py**
  - [ ] Add checkbox option for strict service validation
  - [ ] Description: "Warn about unknown service parameters (may flag valid params for some services)"

- [ ] **service_validator.py**
  - [ ] Add config parameter to `ServiceCallValidator.__init__()`
  - [ ] Store `self._strict_validation = config.get(...)`
  - [ ] Wrap `_validate_unknown_params()` call with config check
  - [ ] Keep capability-dependent param handling regardless of config

### Verification
- [ ] Test default behavior (unknown params checked)
- [ ] Test with strict mode disabled (unknown params skipped)
- [ ] Verify capability-dependent params always allowed

---

## Phase 6: Improve Fuzzy Matching (Priority: LOW)

**Goal:** Better suggestions, fewer confusing ones

### Code Changes

- [ ] **validator.py**
  - [ ] Update `_suggest_state()` cutoff from 0.6 to 0.75 (line 228)
  - [ ] Update `_suggest_entity()` cutoff (already 0.75, keep as-is) (line 265)
  - [ ] Update `_suggest_attribute()` cutoff from 0.6 to 0.75 (line 271)

### Verification
- [ ] Test fuzzy matching still suggests clear typos
- [ ] Verify no suggestions when match is ambiguous

---

## Testing Plan

### Unit Tests to Update

- [ ] `test_jinja_validator.py`
  - [ ] Remove undefined variable tests
  - [ ] Add tests for strict mode config flag
  - [ ] Add tests for filter/test validation opt-in

- [ ] `test_validator.py`
  - [ ] Update severity expectations (ENTITY_REMOVED -> INFO, ATTRIBUTE_NOT_FOUND -> WARNING)
  - [ ] Add tests for domain whitelist
  - [ ] Add tests that non-whitelisted domains skip state validation

- [ ] `test_service_validator.py`
  - [ ] Remove type checking tests (except select options)
  - [ ] Add tests for select option validation
  - [ ] Add tests for strict mode config flag

### Integration Tests

- [ ] Test with real blueprint automations (no false positives)
- [ ] Test with custom component using custom filters (no warnings)
- [ ] Test with sensor.* entities using arbitrary states (no errors)
- [ ] Test with known binary_sensor states (still validated)

### Performance Tests

- [ ] Measure validation time before/after
- [ ] Verify no performance regression
- [ ] Expected improvement: Slightly faster (less validation work)

---

## Documentation Updates

### User Documentation

- [ ] Create `docs/validation-scope.md` (see audit report)
- [ ] Update README.md with new validation scope
- [ ] Document configuration options
- [ ] Create FAQ for "Why doesn't Autodoctor catch X?"

### Code Documentation

- [ ] Update module docstrings to reflect new scope
- [ ] Add comments explaining domain whitelist
- [ ] Document opt-in config options
- [ ] Add examples of what is/isn't validated

### Changelog

- [ ] Create `BREAKING_CHANGES.md` entry:
  ```markdown
  ## v2.7.0 - Validation Scope Narrowing

  ### Removed Validations
  - **Undefined template variables** - Removed due to false positives with blueprints
  - **Basic service parameter type checking** - Now only validates select/enum options

  ### Changed to Opt-In (Default: OFF)
  - **Unknown Jinja2 filters** - Enable via "Strict template validation" config
  - **Unknown Jinja2 tests** - Enable via "Strict template validation" config

  ### Changed Severity
  - **Removed entities** - Downgraded from ERROR to INFO
  - **Missing attributes** - Downgraded from ERROR to WARNING

  ### Conservative Mode
  - **State validation** - Now only validates well-known domains (binary_sensor, person, etc.)
  - Custom sensors and integrations skip state validation

  ### Why These Changes?
  Focus on high-confidence validations to achieve <5% false positive rate.
  Better to miss some issues than generate noise and reduce trust.
  ```

---

## Rollout Plan

### Version Strategy

**v2.7.0** - Breaking Changes Release
- Implement all phases
- Clear changelog documenting changes
- Migration guide for users who relied on removed features

### Communication

- [ ] GitHub release notes explaining rationale
- [ ] Home Assistant forums announcement
- [ ] Note in README about new validation philosophy
- [ ] Discord/Reddit posts if applicable

### Rollback Plan

- [ ] Tag v2.6.x as "legacy" branch for users who want old behavior
- [ ] Document how to revert if needed
- [ ] Keep removed code in git history for reference

---

## Success Criteria

### Quantitative
- [ ] False positive rate < 5% (measure via user reports)
- [ ] Test suite passes 100%
- [ ] No performance regression
- [ ] Config options work correctly

### Qualitative
- [ ] User feedback improves
- [ ] Fewer GitHub issues about false positives
- [ ] Clearer understanding of what Autodoctor validates
- [ ] Ready for mutation testing implementation

---

## Risk Assessment

### Low Risk Changes
- Removing undefined variable checking (already buggy)
- Making filter/test checking opt-in (low impact)
- Improving fuzzy matching thresholds (suggestions only)

### Medium Risk Changes
- Domain whitelist for state validation (may miss some valid checks)
- Downgrading severity levels (user perception of issues changes)

### Mitigation
- Comprehensive testing before release
- Clear documentation of changes
- User config options to enable strict mode
- Monitor user feedback closely post-release

---

## Estimated Effort

| Phase | Effort | Risk | Priority |
|-------|--------|------|----------|
| Phase 1: Remove undefined var | 2 hours | Low | Critical |
| Phase 2: Filter/test opt-in | 3 hours | Low | High |
| Phase 3: Conservative states | 4 hours | Medium | High |
| Phase 4: Simplify type check | 2 hours | Low | Medium |
| Phase 5: Service param opt-in | 2 hours | Low | Low |
| Phase 6: Fuzzy matching | 1 hour | Low | Low |
| Testing | 4 hours | - | - |
| Documentation | 3 hours | - | - |
| **TOTAL** | **~21 hours** | - | - |

---

## Dependencies

### No External Dependencies
All changes are internal to Autodoctor codebase.

### Home Assistant Version
- Current minimum: 2024.1+
- No change needed for this refactor

---

## Post-Implementation

### Monitoring
- [ ] Track GitHub issues for false positive reports
- [ ] Monitor user suppressions (if telemetry available)
- [ ] Collect feedback on new validation scope
- [ ] Adjust domain whitelist based on reports

### Future Improvements
- [ ] Add more domains to whitelist as they prove stable
- [ ] Consider ML-based false positive detection
- [ ] Implement mutation testing (as mentioned in context)
- [ ] Add validation confidence scores in UI

---

## Notes

- Keep git history clean with atomic commits per phase
- Write descriptive commit messages explaining "why" not just "what"
- Consider feature flag for gradual rollout if possible
- Benchmark false positive rate before/after if data available
