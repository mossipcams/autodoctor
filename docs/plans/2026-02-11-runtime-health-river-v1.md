# Runtime Health Monitor (River v1) Plan

## Goal
Add a runtime automation health monitor that is separate from static automation validation, uses River in v1 (no simple-threshold mode), and reuses existing suppression/dismissal infrastructure.

## Constraints
- Keep static validation and runtime health monitoring as separate pipelines.
- Runtime monitoring is opt-in.
- Use River for runtime anomaly detection in v1.
- Reuse existing issue transport/reporting/suppression mechanisms.

## Task 1 (5-15 min): Runtime Group + Issue Type Boundaries
- Test to write:
  - Update `tests/test_models.py` to require runtime issue types and dedicated runtime group coverage.
  - Update `tests/test_init.py` to assert static groups remain intact.
- Code to implement:
  - Add runtime issue types in `custom_components/autodoctor/models.py`.
  - Add dedicated `runtime_health` group and include it in canonical group order.
- Verify:
  - `pytest tests/test_models.py tests/test_init.py -q`

## Task 2 (5-15 min): River Runtime Monitor Module
- Test to write:
  - Add `tests/test_runtime_monitor.py` for warmup behavior, anomaly signaling, and no-op when insufficient data.
- Code to implement:
  - Add `custom_components/autodoctor/runtime_monitor.py` with River-based streaming anomaly detection.
  - Implement feature extraction from recorder-derived automation event history.
- Verify:
  - `pytest tests/test_runtime_monitor.py -q`

## Task 3 (5-15 min): Config + Dependency Wiring
- Test to write:
  - Update `tests/test_config_flow.py` for runtime options.
  - Update `tests/test_architectural_improvements.py` for runtime opt-in + ML guard.
- Code to implement:
  - Add runtime monitor config keys/defaults in `custom_components/autodoctor/const.py`.
  - Add options flow fields and translations.
  - Add River dependency in `pyproject.toml`.
- Verify:
  - `pytest tests/test_config_flow.py tests/test_architectural_improvements.py -q`

## Task 4 (5-15 min): Runtime Stage Orchestration
- Test to write:
  - Update `tests/test_init.py` for runtime stage inclusion and failure isolation.
- Code to implement:
  - Wire runtime monitor into `custom_components/autodoctor/__init__.py` as a separate stage.
  - Add runtime stage timing and skip telemetry.
- Verify:
  - `pytest tests/test_init.py -q`

## Task 5 (5-15 min): WebSocket + Suppression Reuse
- Test to write:
  - Update `tests/test_websocket_api.py` to cover runtime-group output and suppression behavior.
- Code to implement:
  - Ensure runtime issues flow through existing suppression filtering and response shaping.
- Verify:
  - `pytest tests/test_websocket_api.py -q`

## Task 6 (5-15 min): Regression Pass
- Test to write:
  - Run targeted suite for touched modules.
- Code to implement:
  - Fix regressions found in targeted suite.
- Verify:
  - `pytest tests/test_runtime_monitor.py tests/test_models.py tests/test_init.py tests/test_config_flow.py tests/test_websocket_api.py tests/test_architectural_improvements.py -q`

