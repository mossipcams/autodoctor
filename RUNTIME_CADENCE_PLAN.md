# Runtime Cadence Plan (30-Day + Day-of-Week)

## Goal
Fix runtime false positives by making runtime checks respect 30-day cadence and weekday behavior, especially for:
- gap alerts
- stalled alerts
- overactive alerts

## Branch
`feat/runtime-cadence-30d`

## Plan
1. Add/verify gap cadence test coverage in `tests/test_runtime_gap_detector.py`.
2. Add weekday-specific stalled/overactive tests in `tests/test_runtime_monitor.py`.
3. Implement weekday-aware gating for stalled/overactive using baseline evidence from the full baseline window.
4. Re-run focused runtime tests and iterate until green.
5. Run broader runtime suite for regression confidence.

## Current Step
**Complete**

### Completed
- Step 1: Added gap cadence test `test_gap_check_respects_learned_active_weekdays`.
- Step 2: Added weekday-specific runtime tests:
  - `test_stalled_skipped_when_no_baseline_events_on_current_weekday`
  - `test_stalled_flags_when_baseline_events_exist_on_current_weekday`
  - `test_overactive_skipped_when_no_baseline_events_on_current_weekday`
- Step 3: Wired weekday-aware gating into `validate_automations`:
  - Uses `_is_current_weekday_expected_from_baseline_events(...)`
  - Falls back to existing day-type gating when weekday evidence is inconclusive
- Step 4: Re-ran focused runtime tests and resolved regressions.
- Step 5: Ran broader runtime regression tests.

### Verification
- `./.venv/bin/pytest -q tests/test_runtime_monitor.py -k "current_day_type or current_weekday"` → `6 passed`
- `./.venv/bin/pytest -q tests/test_runtime_gap_detector.py -k "learned_active_weekdays or cadence"` → `2 passed`
- `./.venv/bin/pytest -q` → `1080 passed`
