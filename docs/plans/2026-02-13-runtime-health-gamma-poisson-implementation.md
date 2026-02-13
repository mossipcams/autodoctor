# Runtime Health Gamma-Poisson Implementation Plan

## Goal
Replace default runtime health anomaly scoring with a Home Assistant-friendly Gamma-Poisson detector, while keeping runtime issue behavior stable and fully test-covered.

## Task 1: Add Gamma-Poisson detector tests
- Test to write:
  - Add unit tests in `tests/test_runtime_monitor.py` for a new `_GammaPoissonDetector`.
  - Verify stalled/overactive-like current counts score higher than normal-like counts.
- Code to implement:
  - None in this task (test-first).
- Verify:
  - `./.venv/bin/pytest tests/test_runtime_monitor.py -k "gamma_poisson_detector" -v`

## Task 2: Make Gamma-Poisson the default detector
- Test to write:
  - Add failing test that `RuntimeHealthMonitor(detector=None)` defaults to `_GammaPoissonDetector`.
- Code to implement:
  - Add `_GammaPoissonDetector` in `custom_components/autodoctor/runtime_monitor.py`.
  - Update default detector selection in `RuntimeHealthMonitor.__init__`.
- Verify:
  - `./.venv/bin/pytest tests/test_runtime_monitor.py -k "gamma_poisson_detector or defaults_to_gamma" -v`

## Task 3: Preserve scoring fallback compatibility
- Test to write:
  - Ensure `_score_current` still falls back when detector rejects `window_size`.
- Code to implement:
  - Keep/adjust `_score_current` fallback path and logging as needed.
- Verify:
  - `./.venv/bin/pytest tests/test_runtime_monitor.py -k "type_error_fallback" -v`

## Task 4: Remove River-required enablement behavior
- Test to write:
  - Update options-update tests to assert enabling runtime health no longer triggers River restart notifications.
- Code to implement:
  - Update `custom_components/autodoctor/__init__.py` options update path to remove River availability gating notification.
- Verify:
  - `./.venv/bin/pytest tests/test_init.py -k "options_updated and runtime_health" -v`

## Task 5: Align outdated River-specific runtime tests
- Test to write:
  - Update tests that rely on River-only log text or assumptions for detector unavailability/defaults.
- Code to implement:
  - Minimal runtime monitor log/message adjustments only if needed for consistency.
- Verify:
  - `./.venv/bin/pytest tests/test_runtime_monitor.py tests/test_init.py -v`

## Task 6: Full regression validation
- Test to write:
  - No new tests; run full suite for regression detection.
- Code to implement:
  - Fix regressions found by the full run.
- Verify:
  - `./.venv/bin/pytest tests -v`
