# Codebase Concerns

**Analysis Date:** 2026-01-30

## Tech Debt

### Hardcoded Filter/Test Signatures in template_semantics.py

**Issue:** Filter and test signatures are manually defined as Python dictionaries and must be manually synced with Home Assistant releases when HA adds new filters/tests or changes their signatures.

**Files:** `custom_components/autodoctor/template_semantics.py:27-136` (FILTER_SIGNATURES, TEST_SIGNATURES)

**Impact:**
- When HA releases new filters/tests, autodoctor lags behind
- Risk of validation errors for new HA features until manual update
- Currently only covers ~50 filters and ~6 tests; HA has 80+ filters and 15+ tests
- Maintenance burden increases with each HA release cycle
- Users with HA 2026.1+ features get warnings about "unknown" filters until autodoctor updates

**Fix approach:**
1. **Short term:** Document which HA version signatures target (currently undocumented)
2. **Medium term:** Create automated extraction script that parses HA source code during CI/CD
3. **Long term:** Consider making filter/test validation opt-in-only to reduce maintenance burden, or implement dynamic signature discovery from HA itself

**Priority:** Medium (current workaround: strict_template_validation defaults to OFF)

---

### Service Validator Type Checking Still Active Despite Audit Recommendation

**Issue:** The audit (docs/validation-scope-audit.md:219-236) recommends removing basic type checking for number/boolean/text/object selectors, but `service_validator.py:320-337` still implements this validation, causing false positives.

**Files:** `custom_components/autodoctor/service_validator.py:260-340` (_check_selector_type method)

**Impact:**
- YAML type coercion makes type checking unreliable (e.g., "255" string accepted as number by HA)
- Generates WARNING-level false positives for valid automations
- Lines 320-337 check basic type selectors but should only validate select/enum options (already implemented lines 269-318)

**Current state:** Only select options are correctly validated; basic types still checked (should be removed)

**Fix approach:**
1. Remove lines 320-337 that check basic type selectors
2. Keep select/enum validation (lines 269-318)
3. Update tests in `tests/test_service_validator.py` to remove type-checking test cases

**Priority:** High (documented false positive issue, should be completed before v2.7.0 release)

---

### Analyzer Complexity and Brittle Regex Patterns

**Issue:** `analyzer.py` (1226 lines) contains 18+ regex patterns for template parsing that are fragile and could miss edge cases or produce false negatives.

**Files:**
- `custom_components/autodoctor/analyzer.py:14-80` (regex patterns)
- `custom_components/autodoctor/analyzer.py:152-437` (_extract_from_trigger through _extract_from_template)

**Impact:**
- Regex patterns don't handle all Jinja2 syntax variations (escaped quotes, nested templates, custom functions)
- Lines 15-16 use complex escaped quote handling but may miss edge cases with triple quotes or raw strings
- Changes to automation syntax could break extraction (e.g., if HA adds new template functions)
- Test coverage in `tests/test_analyzer.py` (2178 lines) is comprehensive but fragile patterns still risky

**Examples of brittleness:**
- `STATES_OBJECT_PATTERN` line 31 assumes `domain.object_id` format but won't catch `states['entity.id']` dict syntax
- `EXPAND_PATTERN` line 42 only captures first argument but expand() can take multiple entities
- Custom Jinja2 functions added by integrations won't be recognized

**Fix approach:**
1. **Refactor to AST-based parsing:** Replace regex with Python's Jinja2 AST parser (already partially done for jinja_validator.py)
2. **Improve coverage:** Add tests for edge cases (escaped quotes, nested templates, raw strings)
3. **Document limitations:** Add comments about what patterns don't handle
4. **Consider deprecation:** Flag custom template extraction as low-confidence (already opt-in via strict mode)

**Priority:** Low-Medium (current workaround: template-based validation already opts out for templates, regex extraction is best-effort)

---

### Analyzer Recursion Depth Limit Not Documented in Code

**Issue:** `const.py:7` defines `MAX_RECURSION_DEPTH = 20` but code doesn't document why 20 is safe or what happens when limit is hit.

**Files:**
- `custom_components/autodoctor/const.py:7`
- `custom_components/autodoctor/analyzer.py` (used in multiple _extract methods)

**Impact:**
- If automation has >20 levels of nested conditions/actions, extraction silently stops
- Users won't know why deeply nested automations aren't fully validated
- No logging or warning when depth limit is hit
- Limit of 20 may be too strict for complex automations or too loose for performance

**Fix approach:**
1. Add comment explaining why 20 is chosen (stack safety, performance, typical use case)
2. Add warning log when limit is hit: "Recursion depth exceeded, stopping extraction"
3. Consider making this configurable via options (already in const.py, used in config_flow.py)
4. Test performance with various recursion depths

**Priority:** Low (affects edge cases, current default is reasonable)

---

## Known Issues

### Service Validator Doesn't Handle Capability-Dependent Parameters Comprehensively

**Issue:** `service_validator.py:30-44` hardcodes capability-dependent parameters for only 6 services (light.turn_on, light.turn_off, climate.*, cover.*), but many more services have capability-dependent params.

**Files:** `custom_components/autodoctor/service_validator.py:30-44` (_CAPABILITY_DEPENDENT_PARAMS)

**Impact:**
- Services like `fan.oscillate`, `fan.set_speed`, `media_player.play_media` have capability-dependent params not in the whitelist
- Users get false "unknown parameter" warnings for valid capability-dependent params
- Maintenance burden: every new HA service with capability-dependent params requires manual update

**Affected services (incomplete list):**
- `fan.*` (speed, oscillation, direction depend on device capabilities)
- `media_player.*` (many media-specific params)
- `climate.set_preset_mode` (presets depend on device)
- `cover.set_cover_position` (tilt depends on device type)
- `humidifier.*` (modes depend on device)

**Fix approach:**
1. Expand whitelist for all known capability-dependent services (medium effort)
2. Or: Make unknown param detection opt-in only (already configurable but defaults to ON)
3. Or: Query HA's entity registry for actual capabilities at validation time

**Priority:** Medium (users of affected services get warnings they can suppress)

---

### Template Variable Checking Removed But Documentation Incomplete

**Issue:** Undefined variable checking was removed in v2.6.2 to fix false positives with blueprints, but multiple files still reference it in comments or have partial implementations.

**Files:**
- `custom_components/autodoctor/jinja_validator.py:950-969` (_validate_variable method still exists but unused)
- `tests/test_jinja_validator.py` (old tests may reference removed checks)
- `models.py` (TEMPLATE_UNKNOWN_VARIABLE enum still exists but shouldn't be used)

**Impact:**
- Dead code (_validate_variable method) should be removed
- TEMPLATE_UNKNOWN_VARIABLE enum never generated but still in code
- Confuses future maintainers about what's actually validated
- Tests may include outdated test cases

**Fix approach:**
1. Remove `_validate_variable()` method entirely from jinja_validator.py
2. Remove TEMPLATE_UNKNOWN_VARIABLE from models.py IssueType enum
3. Remove tests for undefined variables from test_jinja_validator.py
4. Remove call to _validate_variable in _check_ast_semantics (if it still exists)

**Priority:** Medium (cleanup/maintenance debt, no functional impact)

---

## Security Considerations

### Service Descriptions Cached Indefinitely

**Issue:** `service_validator.py:58` caches service descriptions (`self._service_descriptions`) without expiration or refresh mechanism.

**Files:** `custom_components/autodoctor/service_validator.py:55-88` (ServiceCallValidator.__init__ and async_load_descriptions)

**Impact:**
- If user installs new custom component, service descriptions aren't reloaded
- Validation uses stale service definitions until HA restart
- Could miss new services or misvalidate updated service schemas
- Affects production automations if services change during HA session

**Attack surface:** Low (integrity issue, not security vulnerability)

**Fix approach:**
1. Add refresh mechanism triggered by `device_registry.SIGNAL_DEVICE_REGISTRY_UPDATED` or HA service registry events
2. Or: Set cache timeout (e.g., reload every 1 hour)
3. Or: Add option to manually refresh via service call `autodoctor.refresh_knowledge_base` (already exists per index.md, verify it reloads service descriptions)

**Priority:** Low (workaround: restart HA if services change, uncommon in production)

---

## Performance Bottlenecks

### Knowledge Base History Loading Could Be Expensive

**Issue:** `knowledge_base.py:466-486` loads recorder history for all entities to build valid state knowledge base. For instances with thousands of entities, this could be slow.

**Files:** `custom_components/autodoctor/knowledge_base.py:466-486` (async_load_history)

**Impact:**
- First validation pass after HA restart loads all history (network + I/O bound)
- For large instances (>5000 entities), could take 10-30 seconds
- Blocks validation until complete (though async, still affects responsiveness)
- No progress indicator or timeout

**Scaling limits:**
- Current approach likely fine for <10k entities
- >20k entities: may timeout or use excessive memory
- History lookback (default 30 days) affects query time linearly

**Fix approach:**
1. Add progress logging every N entities processed
2. Add timeout parameter (default 60s)
3. Implement pagination if possible with recorder API
4. Cache results to disk (already done with learned_states_store.py)
5. Skip history loading for initial setup, defer to background

**Priority:** Low (typical HA instances have <5k entities, timeout already handled implicitly)

---

### Jinja2 AST Parsing Could Be Slow for Complex Templates

**Issue:** `jinja_validator.py` uses Jinja2 AST parsing for every template in every automation. Complex templates with deep nesting could be slow.

**Files:** `custom_components/autodoctor/jinja_validator.py:135-950` (full validation pipeline)

**Impact:**
- Each template is parsed independently
- No caching of parsed templates
- Users with 100+ automations with complex templates may see slow validation

**Scaling limits:**
- Single template with 1000+ lines or 50+ nested filters: parsing could take 100ms
- 100 automations × 5 templates each × 50ms = 25 seconds total

**Fix approach:**
1. Add LRU cache for parsed ASTs (templates are often repeated)
2. Profile actual performance with real automation configs
3. Add timeout for individual template parsing

**Priority:** Low (templates are typically small, profiling needed first)

---

## Fragile Areas

### Domain Attributes Manually Maintained

**Issue:** `domain_attributes.py` manually defines attribute mappings for each domain to prevent false positives when checking for attributes.

**Files:** `custom_components/autodoctor/domain_attributes.py:1-65`

**Impact:**
- If Home Assistant adds new domain or entity class with new attributes, false positives occur until manual update
- Maintenance burden: requires knowledge of all HA domains and their standard attributes
- Currently only covers ~15 domains; HA has 50+ domains
- Attributes are capability-dependent; current mapping is a best guess

**Safe modification:**
- Add new domain attributes to the dict in alphabetical order
- Test with actual entity state to verify attributes exist
- Document which HA version the attributes target

**Test coverage:** `tests/test_validator.py` (636 lines) includes attribute validation tests

**Priority:** Low (attribute validation already downgraded to WARNING, users can suppress false positives)

---

### State Validation Whitelist Could Miss Valid Domains

**Issue:** `const.py:21-28` defines `STATE_VALIDATION_WHITELIST` with only 6 domains (binary_sensor, person, sun, device_tracker, input_boolean, group). Any other domain's state validation is skipped.

**Files:** `custom_components/autodoctor/const.py:21-28`

**Impact:**
- Custom domains with stable state sets won't be validated
- Users with custom integrations get no state validation (by design, conservative)
- Legitimate state values in unlisted domains are not caught

**Safe modification:**
- Add domains only if they have well-documented, stable state sets
- Verify with actual HA source code that state set is fixed
- Add corresponding tests to verify state validation works for new domain

**Current whitelist rationale:**
- binary_sensor: on/off (stable)
- person: home/not_home/away (stable per HA docs)
- sun: above_horizon/below_horizon (stable)
- device_tracker: home/not_home/away (stable)
- input_boolean: on/off (user-defined, stable)
- group: on/off (computed, stable)

**Priority:** Low (conservative approach reduces false positives, intentional design)

---

### Jinja2 Environment Not Fully Isolated

**Issue:** `jinja_validator.py:97-110` creates a SandboxedEnvironment but doesn't fully replicate Home Assistant's template environment.

**Files:** `custom_components/autodoctor/jinja_validator.py:97-110` (JinjaValidator.__init__)

**Impact:**
- Template validation may pass even if HA's template engine would reject it
- Conversely, validation may fail for templates HA would accept
- Mismatch between validation and runtime behavior (rare but possible)

**Examples of potential mismatch:**
- Custom HA globals registered by integrations won't be in KNOWN_GLOBALS
- HA-specific context variables (trigger, this, state_translated) may not be available
- Some HA filters may have different behavior in sandboxed environment

**Fix approach:**
1. Document known differences between validation environment and HA runtime
2. Consider sharing HA's template environment directly instead of creating separate one
3. Add integration test validating real HA templates

**Priority:** Low (current approach is conservative, false positives rare)

---

## Test Coverage Gaps

### No Mutation Testing for Validation Rules

**Issue:** The codebase has extensive unit tests (6100+ lines) but no mutation testing to verify validation rules are actually effective.

**Files:** Multiple test files in `tests/` directory

**Impact:**
- Tests may pass even if validation logic is broken or ineffective
- Edge cases in validation rules may not be caught
- Can't measure mutation survival rate for each validation type
- No visibility into which rules are most/least robust

**Example gap:** A test for "entity exists" validation may pass even if the actual existence check is removed, if the test focuses on the error message rather than the condition.

**Current test coverage:**
- `test_analyzer.py`: 2178 lines (automation parsing)
- `test_service_validator.py`: 702 lines
- `test_validator.py`: 636 lines
- `test_jinja_validator.py`: 514 lines
- Others: 500+ lines

**Fix approach:**
1. Run mutation testing tool (e.g., mutmut or cosmic-ray for Python)
2. Focus on validation rule mutations (change > to <, remove checks, etc.)
3. Add tests for any rules with >20% mutation survival rate
4. Target: <5% mutation survival rate for critical validation rules

**Priority:** Medium (planned per index.md: "Mutation testing once scope is stable")

---

### Limited Coverage for Strict Modes

**Issue:** Config options `strict_template_validation` and `strict_service_validation` have minimal test coverage.

**Files:**
- `const.py:17-18` (config definitions)
- `models.py:36-37` (ValidationConfig)
- `tests/` (need to search for strict mode tests)

**Impact:**
- Strict modes may not work correctly
- Changes to validation logic could break strict mode without being caught
- Users enabling strict mode get untested code paths

**Fix approach:**
1. Add test suite for each strict mode (test_strict_template_validation, test_strict_service_validation)
2. Verify that unknown filter/test warnings appear when strict_template_validation=True
3. Verify that unknown param warnings appear when strict_service_validation=True
4. Test interaction with config flow

**Priority:** Medium (strict modes are opt-in, but should be reliable)

---

## Scaling Limits

### Regex Patterns Could Fail on Large Automations

**Issue:** `analyzer.py` uses regex patterns compiled globally, which are evaluated for every automation. Large automations (>50KB) could cause performance degradation.

**Files:** `custom_components/autodoctor/analyzer.py:18-80` (all regex patterns)

**Impact:**
- Catastrophic backtracking possible with certain templates (unlikely but possible)
- Large automations with many nested triggers/conditions/actions take longer to parse
- No timeout on regex matching

**Scaling limits:**
- Automations <100KB: fine
- Automations >500KB: may be slow (rare in practice)

**Fix approach:**
1. Add timeout to regex operations (can't easily do with standard re module)
2. Profile with real large automations
3. Consider switching to Jinja2 AST parsing where regex is most fragile

**Priority:** Low (most automations are <50KB, edge case)

---

### Validation Issues List Not Deduplicated at Scale

**Issue:** `__init__.py` collects validation issues from multiple validators but doesn't deduplicate if the same issue is found by multiple code paths.

**Files:** `custom_components/autodoctor/__init__.py:345-468` (async_validate_all)

**Impact:**
- Users may see duplicate warnings for the same problem
- Issue count sensor would be inflated
- UI could show same issue multiple times

**Current mitigation:** `models.py:117-135` (ValidationIssue class) defines __hash__ and __eq__, suggesting deduplication intended but unclear if used

**Fix approach:**
1. Verify deduplication is actually applied in __init__.py
2. Add test case where same issue is found by multiple validators
3. If not deduplicated, convert issues list to set before returning

**Priority:** Low (deduplication likely already works, verify needed)

---

## Dependencies at Risk

### Jinja2 Sandbox Environment May Evolve Incompatibly

**Issue:** Code depends on `jinja2.sandbox.SandboxedEnvironment` which is part of Jinja2's internals.

**Files:** `custom_components/autodoctor/jinja_validator.py:11`

**Impact:**
- If Jinja2 updates SandboxedEnvironment behavior or APIs, code could break
- No version constraint on Jinja2 in manifest.json (uses HA's version)
- HA may update Jinja2 independently

**Fix approach:**
1. Add version constraint on Jinja2 in manifest.json if not present
2. Monitor Jinja2 changelog for breaking changes
3. Test after HA updates that include Jinja2 updates

**Priority:** Low (Jinja2 is stable, HA manages dependency)

---

### Home Assistant API Surface Could Change

**Issue:** Code uses HA internal APIs that could change between HA versions.

**Files:** Multiple files import from `homeassistant.*`:
- `__init__.py:7-13` (hass.config_entries, services, automations)
- `service_validator.py:60-66` (async_get_all_descriptions)
- `knowledge_base.py` (entity_registry, device_registry)

**Impact:**
- Breaking changes in HA's internal APIs could require updates
- Currently targets HA 2024.1+, may need updates for newer versions
- No version constraints in manifest.json beyond HA version

**Fix approach:**
1. Document which HA APIs are used and their version stability
2. Add integration tests with multiple HA versions
3. Monitor HA changelog for API changes
4. Add version constraints if needed

**Priority:** Low (HA has good backwards compatibility, documentation needed)

---

## Missing Critical Features

### No Validation for Blueprint Variables

**Issue:** Blueprints define input variables that are injected at runtime, but autodoctor can't validate that blueprint uses are providing required inputs.

**Files:** `analyzer.py` partially handles this (lines 1-80 note blueprint inputs), but no full validation

**Impact:**
- Users can create automation from blueprint missing required inputs
- No warning until automation runs and crashes at runtime
- Currently accepted limitation per validation-scope-audit.md

**Design decision:** Intentionally not validated (too many false positives statically)

**Alternative:** Provide opt-in "blueprint variable validation" that checks input declarations match usage

**Priority:** Low (intentional limitation, documented)

---

### No Validation for Automation Sequence Order Dependencies

**Issue:** Some automations have implicit dependencies on execution order (e.g., automation A modifies state that automation B reads). No validation that dependencies are met.

**Files:** No existing code for this

**Impact:**
- Race conditions possible if automations run in unexpected order
- Difficult to debug (depends on timing)
- Beyond static analysis scope

**Design decision:** Out of scope for static analysis tool

**Priority:** Very Low (architectural, not suitable for static analysis)

---

## Future Improvement Opportunities

### Implement Caching Layer for Validation Results

**Issue:** Each validation run re-validates all automations even if they haven't changed.

**Opportunity:**
- Cache validation results by automation SHA256 hash
- Invalidate cache when:
  - Entity registry changes
  - Service registry changes
  - User learns new state
- Could reduce validation time by 80%+ for unchanged automations

**Priority:** Low (nice-to-have optimization)

---

### Add Machine Learning for False Positive Detection

**Issue:** Some validation types inherently have false positives (state validation, attribute validation).

**Opportunity:**
- Collect telemetry of suppressed issues
- Train model to predict likely false positives
- Reduce severity or skip validation for high-FP-probability issues

**Priority:** Very Low (research-level idea)

---

## Summary

**Critical issues (blocks v2.7.0 release):**
- Service validator type checking still validates basic types (should be removed per audit)

**Important issues (should fix soon):**
- Hardcoded filter/test signatures need maintenance tracking
- Capability-dependent parameters incomplete
- Jinja2 template variable checking dead code should be removed

**Nice-to-have improvements:**
- Mutation testing for validation rules
- Caching of validation results
- Better performance profiling
- Expanded attribute/domain mappings

**By design (not issues):**
- Conservative validation to minimize false positives
- No blueprint variable validation
- Limited state validation to whitelisted domains
- Regex-based template extraction (best-effort)

---

*Concerns audit: 2026-01-30*
