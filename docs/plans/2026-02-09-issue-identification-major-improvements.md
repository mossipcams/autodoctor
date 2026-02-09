# Issue Identification Major Improvements Plan

**Date:** 2026-02-09
**Status:** Complete (Iterations 1-15 complete)
**Objective:** Find substantially more real automation issues by expanding validation issue identification coverage.

## Why This Plan

Autodoctor currently prioritizes high precision. The next step is to increase **recall**: identify more true issues that are currently missed, while keeping precision above an acceptable floor.

## Success Metrics

1. Issues discovered per 100 automations: **+50%** versus current baseline.
2. Precision on curated fixtures: **>=85%**.
3. Coverage of supported HA structures (trigger/condition/action extraction): **>=95%**.
4. Every skip path records a reason code in run stats.

## High-Value Improvement Areas

1. **Deep reference extraction expansion**
- Ensure analyzer traverses all nested action structures and syntax variants.
- Expand extraction beyond entity_id to device_id/area_id wherever they are valid references.
- Impact: unlocks issue discovery currently missed before validators even run.

2. **Service-call semantic validation expansion**
- Add service-level checks for target/data placement, required field combinations, and high-confidence domain rules.
- Impact: catches common action misconfigurations that pass current checks.

3. **Template reference identification v2**
- Deterministically extract and validate references from high-confidence template patterns.
- Impact: improves coverage for template-heavy automations.

4. **Cross-field semantic issue detection**
- Add validators for contradictory or incompatible field combinations.
- Impact: identifies logical defects beyond single-field checks.

5. **High-recall rule packs**
- Add optional extended/aggressive packs for users who want maximum issue discovery.
- Impact: broad discovery growth without forcing noise on default users.

## Iteration Scope (This Implementation)

Implement the highest ROI extraction improvement with low regression risk:

1. Extract **service-call `device_id` and `area_id` references** from both:
- `action.target`
- `action.data`

2. Support both scalar and list forms.

3. Tag extracted references with correct `reference_type` (`device`/`area`) so the existing `ValidationEngine` can validate registry existence.

4. Keep templates conservative: templated `device_id`/`area_id` values are not validated as direct IDs.

## TDD Strategy

1. Add failing analyzer tests for service-call extraction of:
- `target.device_id`
- `target.area_id`
- `data.device_id`
- `data.area_id`
- mixed list/scalar combinations

2. Add failing end-to-end regression tests proving missing service target device/area IDs now produce validation issues.

3. Implement minimal code changes in `analyzer.py`.

4. Run targeted tests:
- `tests/test_analyzer.py`
- `tests/test_defect_regressions.py`
- relevant `tests/test_validator.py` checks

## Risks and Mitigations

1. **Risk:** Duplicate issues for same reference.
- **Mitigation:** Keep extraction locations stable and dedupe through existing issue equality semantics.

2. **Risk:** False positives on templated IDs.
- **Mitigation:** Continue skipping template-derived values for direct ID validation.

3. **Risk:** Behavior drift in existing extraction paths.
- **Mitigation:** Add narrow tests; avoid touching unrelated trigger/condition logic.

## Follow-Up After This Iteration

All three follow-up tracks were implemented in this plan:
1. Service semantic checks expanded across high-impact services.
2. Confidence tiers added for heuristic/high-recall checks.
3. Skip-reason telemetry implemented for validator availability and exception paths.

## Iteration 1 Delivered (2026-02-09, TDD)

1. Service-call reference extraction expanded in analyzer:
- Inline, `data`, and `target` extraction for `entity_id`, `device_id`, `area_id`
- Scalar and list forms supported
- Proper `reference_type` tagging (`service_call`, `device`, `area`)

2. ServiceCallValidator target coverage expanded:
- Validates `entity_id` from both `target` and `data`
- Validates `device_id` via device registry lookup
- Validates `area_id` via area registry lookup
- Detects malformed target field types (`SERVICE_INVALID_PARAM_TYPE`) instead of silently skipping

3. Test coverage added:
- New analyzer tests for service-call target extraction variants
- New service validator tests for `data` targets and device/area lookup
- New regression test for end-to-end issue identification of service target device/area references

## Iteration 2 Delivered (2026-02-09, TDD)

1. Service payload shape identification added:
- Non-mapping `target` payloads now emit `SERVICE_INVALID_PARAM_TYPE`
- Non-template, non-mapping `data` payloads now emit `SERVICE_INVALID_PARAM_TYPE`
- Template-string `data` remains conservatively skipped

2. Service target type hardening added:
- Invalid scalar/list item types for `entity_id`/`device_id`/`area_id` now emit explicit type issues
- Valid string entries in mixed lists continue to be validated for existence

3. Test coverage added:
- Payload-shape tests for `target` and `data`
- Target field type tests for scalar and list-item invalid types

## Iteration 3 Delivered (2026-02-09, TDD)

1. Cross-field target conflict identification added:
- Detects conflicting `entity_id` values between `data` and `target`
- Detects conflicting `device_id` values between `data` and `target`
- Detects conflicting `area_id` values between `data` and `target`

2. Conservative conflict semantics:
- Compares normalized non-template string sets only
- Does not flag when sets are equivalent
- Skips template-derived values to avoid false positives

3. Test coverage added:
- Conflict detection tests for entity/device targets
- No-conflict test for equivalent values across `data`/`target`

## Iteration 4 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation added:
- `input_datetime.set_datetime` now flags conflicting parameter modes:
  - `datetime` mixed with `date`/`time`/`timestamp`
  - `timestamp` mixed with `date`/`time`

2. Conservative rule behavior:
- `date + time` remains valid and is not flagged
- Rule runs only for mapping payloads

3. Test coverage added:
- Failing test first for `datetime + date` conflict
- Guard test ensuring `date + time` is accepted

## Iteration 5 Delivered (2026-02-09, TDD)

1. Skip-reason telemetry added for service validation:
- `ServiceCallValidator` now tracks per-run telemetry:
  - `total_calls`
  - `skipped_calls_by_reason`
- Current skip reasons tracked:
  - `templated_service_name`
  - `missing_service_descriptions`

2. Validation pipeline telemetry propagation:
- `_async_run_validators` now returns `skip_reasons` by group
- `validation_run_stats` now includes `skip_reasons`
- Both full and single-automation validation paths persist this telemetry

3. Test coverage added:
- Service validator telemetry initialization and skip counting
- Orchestration test proving skip telemetry appears in grouped results and persisted run stats

## Iteration 6 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation expanded:
- `climate.set_temperature` now flags conflicting setpoint modes:
  - `temperature` mixed with `target_temp_high` and/or `target_temp_low`

2. Conservative rule behavior:
- Range-only payloads (`target_temp_high` + `target_temp_low`) remain valid
- Rule runs only for mapping payloads

3. Test coverage added:
- Failing test first for mixed single+range setpoint conflict
- Guard test ensuring range-only payload is accepted

## Iteration 7 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation expanded:
- `media_player.play_media` now enforces paired parameters:
  - `media_content_id` requires `media_content_type`
  - `media_content_type` requires `media_content_id`

2. Rule behavior:
- Emits `SERVICE_MISSING_REQUIRED_PARAM` for missing pair member
- Leaves valid paired payloads unchanged

3. Test coverage added:
- Failing test first for missing `media_content_type` when `media_content_id` is present
- Guard test ensuring paired payload (`media_content_id` + `media_content_type`) is accepted

## Iteration 8 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation expanded:
- `remote.send_command` now enforces command presence when auxiliary parameters are used:
  - `device`
  - `delay_secs`
  - `num_repeats`

2. Rule behavior:
- Emits `SERVICE_MISSING_REQUIRED_PARAM` when aux params are present without `command`
- Leaves valid payloads with `command` unchanged

3. Test coverage added:
- Failing test first for aux-params-without-command
- Guard test ensuring payload with `command` is accepted

## Iteration 9 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation expanded:
- `tts.speak` now flags empty non-template `message` values

2. Rule behavior:
- Emits `SERVICE_INVALID_PARAM_TYPE` when `message` is an empty string
- Leaves non-empty messages unchanged
- Skips template message values conservatively

3. Test coverage added:
- Failing test first for empty `message`
- Guard test ensuring non-empty `message` is accepted

## Iteration 10 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation expanded:
- `remote.send_command` now flags empty `command` payload values:
  - empty string
  - empty list

2. Rule behavior:
- Emits `SERVICE_INVALID_PARAM_TYPE` for empty command payloads
- Existing rule for missing `command` with auxiliary params remains in place

3. Test coverage added:
- Failing test first for empty string command
- Failing test first for empty list command

## Iteration 11 Delivered (2026-02-09, TDD)

1. Domain-specific semantic validation expanded:
- `media_player.play_media` now flags empty string values for:
  - `media_content_id`
  - `media_content_type`

2. Rule behavior:
- Emits `SERVICE_INVALID_PARAM_TYPE` for empty non-template values
- Existing paired-parameter requirement (`id` + `type`) remains in place

3. Test coverage added:
- Failing test first for empty `media_content_id`
- Failing test first for empty `media_content_type`

## Iteration 12 Delivered (2026-02-09, TDD)

1. Skip-reason telemetry expanded beyond services:
- `_async_run_validators` now records `validator_unavailable` when:
  - template validator is missing
  - service validator is missing

2. Rule behavior:
- Missing families are explicitly surfaced under `skip_reasons` instead of silently omitted

3. Test coverage added:
- Failing test first verifying `validator_unavailable` in template and service group skip telemetry

## Iteration 13 Delivered (2026-02-09, TDD)

1. Skip-reason telemetry expanded for entity-state pipeline:
- `_async_run_validators` now records:
  - `skip_reasons.entity_state.validator_unavailable = 1`
  when analyzer/validator are missing

2. Behavior hardening:
- Missing entity-state validator families are treated as explicit skips (not per-automation failures)
- `analyzed_automations` now reports `0` when entity-state validation is unavailable

3. Test coverage added:
- Failing test first for missing entity-state validators:
  - skip reason emitted
  - `failed_automations == 0`
  - `analyzed_automations == 0`

## Iteration 14 Delivered (2026-02-09, TDD)

1. Skip-reason telemetry expanded for validation exceptions:
- `_async_run_validators` now records:
  - `skip_reasons.templates.validation_exception`
  - `skip_reasons.services.validation_exception`
  when those validator families raise exceptions

2. Behavior hardening:
- Exception paths are now visible in telemetry instead of only logs

3. Test coverage added:
- Failing test first for template validator exception telemetry
- Failing test first for service validator exception telemetry

## Iteration 15 Delivered (2026-02-09, TDD)

1. Confidence tiers implemented:
- `ValidationIssue` now includes `confidence` with default `"high"`
- `ValidationIssue.to_dict()` now serializes `confidence`

2. Heuristic issue confidence classification:
- Service semantic and cross-field heuristic issues are marked `"medium"` confidence
- Deterministic checks remain `"high"` by default

3. Test coverage added:
- Model tests for default/custom confidence and serialization
- Service semantic test asserting medium confidence on climate conflicting-setpoint heuristic
