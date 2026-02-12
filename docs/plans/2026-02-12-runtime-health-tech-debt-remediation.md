# Runtime Health Tech-Debt Remediation Plan

## Goal
Harden automation runtime-health monitoring in three areas:
1. Make suppression behavior global (WebSocket, Repairs, and entity sensors).
2. Prevent "too-short baseline" configurations from silently disabling anomaly detection.
3. Make the hour-ratio lookback window configurable via integration options.

## Scope
- Runtime health monitor pipeline and telemetry behavior.
- Options/config flow, constants, and translations.
- Validation result shaping used by reporter, sensors, and websocket API.

## Task 1 (10 min): Add Suppression Contract Tests at Validation Core Boundary
- Test to write:
  - Add tests in `tests/test_init.py` that run `_async_run_validators`/`async_validate_all_with_groups` with a suppressed runtime issue and assert:
    - suppressed issues are excluded from the list passed to reporter
    - cached `validation_issues` excludes suppressed issues
    - (if kept) a raw issue cache still retains total issue context
- Code to implement:
  - Add a single suppression-filter helper in `custom_components/autodoctor/__init__.py` used before reporter/state updates.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_init.py -k "runtime and suppress"`

## Task 2 (10 min): Keep Suppressed Counts Without Reintroducing Visible Noise
- Test to write:
  - Update `tests/test_websocket_api.py` assertions so `suppressed_count` remains correct for step responses after core filtering changes.
- Code to implement:
  - Preserve enough metadata (for example, raw issue totals or explicit suppressed counters) so websocket responses can still report suppressed counts accurately.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_websocket_api.py -k "runtime_health or validation_steps or suppressed_count"`

## Task 3 (10 min): Ensure Repairs and Sensors Reflect Unsuppressed Issues Only
- Test to write:
  - Add/adjust tests in `tests/test_reporter.py`, `tests/test_sensor.py`, and `tests/test_binary_sensor.py` to assert suppressed runtime issues do not surface via active reporter issue set and entity state.
- Code to implement:
  - Route only unsuppressed issues into reporter-facing state updates.
  - Keep sensor logic unchanged if it already reads reporter state; otherwise align it to unsuppressed issue data.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_reporter.py tests/test_sensor.py tests/test_binary_sensor.py`

## Task 4 (10 min): Add Baseline Adequacy Guardrails in Options Validation
- Test to write:
  - Add `tests/test_config_flow.py` cases for:
    - rejecting baseline windows that cannot produce effective training rows
    - preserving the existing warmup<=baseline rule
- Code to implement:
  - Add config validation in `custom_components/autodoctor/config_flow.py` for effective training feasibility (baseline vs warmup and cold-start assumptions).
  - Add a user-facing error key in translations/strings.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_config_flow.py`

## Task 5 (10 min): Surface Explicit Runtime Skip Reason for Insufficient Training Rows
- Test to write:
  - Add monitor tests in `tests/test_runtime_monitor.py` asserting an explicit skip reason when feature rows are too few for anomaly scoring.
- Code to implement:
  - Add explicit skip telemetry key (for example, `insufficient_training_rows`) in `custom_components/autodoctor/runtime_monitor.py`.
  - Ensure it flows into `skip_reasons.runtime_health` via existing runtime stats plumbing.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_runtime_monitor.py tests/test_init.py -k "runtime and training"`

## Task 6 (10 min): Introduce Configurable Hour-Ratio Lookback Option
- Test to write:
  - Add tests in `tests/test_config_flow.py` and `tests/test_architectural_improvements.py` for new option key/default/range.
  - Add runtime monitor unit tests proving hour-ratio uses configured days, not hardcoded 30.
- Code to implement:
  - Add new config key/default in `custom_components/autodoctor/const.py`:
    - `CONF_RUNTIME_HEALTH_HOUR_RATIO_DAYS`
    - `DEFAULT_RUNTIME_HEALTH_HOUR_RATIO_DAYS`
  - Add options schema field + descriptions in `custom_components/autodoctor/config_flow.py`, `custom_components/autodoctor/strings.json`, and `custom_components/autodoctor/translations/en.json`.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_config_flow.py tests/test_architectural_improvements.py tests/test_runtime_monitor.py -k "hour_ratio or runtime_health"`

## Task 7 (10 min): Wire New Option Through Setup into Runtime Monitor
- Test to write:
  - Add setup wiring test in `tests/test_init.py` asserting `RuntimeHealthMonitor` receives the new hour-ratio days argument.
- Code to implement:
  - Pass configured hour-ratio window from `custom_components/autodoctor/__init__.py` into `RuntimeHealthMonitor(...)`.
  - Store and apply this value inside feature generation logic in `custom_components/autodoctor/runtime_monitor.py`.
- How to verify:
  - `.venv/bin/python -m pytest -q tests/test_init.py tests/test_runtime_monitor.py -k "hour_ratio or setup_entry_runtime"`

## Task 8 (10 min): Align Documentation with Runtime-Health Behavior
- Test to write:
  - Add/update docs assertions if present (otherwise rely on review checklist in PR description).
- Code to implement:
  - Update `README.md` (required) and `docs/what-autodoctor-validates.md` to document:
    - global suppression behavior
    - practical baseline guidance for anomaly stability
    - configurable hour-ratio lookback option
- How to verify:
  - Manual docs review + optional targeted lint/test command if available.

## Task 9 (10 min): Full Regression Pass
- Test to write:
  - None (regression execution only).
- Code to implement:
  - Fix any regressions discovered in the full run.
- How to verify:
  - `.venv/bin/python -m pytest -q`

## Exit Criteria
- Suppressed runtime issues do not appear in websocket issue lists, Repairs, or sensor/binary_sensor issue state.
- Runtime skip reasons clearly explain when anomaly detection could not run due to inadequate training window.
- Hour-ratio feature window is user-configurable in options and applied end-to-end in monitor behavior.
- All tests pass.
