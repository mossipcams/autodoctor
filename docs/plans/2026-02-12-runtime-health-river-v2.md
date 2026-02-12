# Runtime Health Monitor (River v2) Implementation Plan

## Goal
Improve runtime anomaly detection quality by expanding feature engineering, hardening scoring logic, and adding telemetry/review plumbing while preserving Autodoctor's high-precision bias.

## Task 1: Feature scaffolding + schema guardrails
- Test to write:
  - Extend `tests/test_runtime_monitor.py` to assert training/current rows share identical expanded feature keys.
- Code to implement:
  - Add a canonical feature builder in `custom_components/autodoctor/runtime_monitor.py` used for both historical and current rows.
- Verify:
  - `pytest tests/test_runtime_monitor.py -q`

## Task 2: Rolling count features
- Test to write:
  - Add tests for rolling 7-day and 24-hour counts on synthetic histories.
- Code to implement:
  - Add `rolling_7d_count` and keep/standardize `rolling_24h_count` feature extraction.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*rolling* -q`

## Task 3: Gap-based stalled feature
- Test to write:
  - Add tests for minutes since last trigger and normalization by median gap.
- Code to implement:
  - Add `minutes_since_last_trigger` and `gap_vs_median` features.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*gap* -q`

## Task 4: Time-context features
- Test to write:
  - Add tests for weekday/weekend and current-hour ratio vs 30-day same-hour average.
- Code to implement:
  - Add `is_weekend` and `hour_ratio_30d`.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*hour* tests/test_runtime_monitor.py::test_*weekend* -q`

## Task 5: Cross-automation cascade feature
- Test to write:
  - Add tests for counting other automations in same 5-minute window.
- Code to implement:
  - Add `other_automations_5m` using cross-automation 5-minute buckets.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*cascade* -q`

## Task 6: Cold-start handling
- Test to write:
  - Add tests that first 7 days of baseline are cold start and not scored.
- Code to implement:
  - Add cold-start exclusion from training/scoring eligibility.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*cold* -q`

## Task 7: Per-automation window sizing
- Test to write:
  - Add detector tests validating per-automation `window_size` scaling to ~30 days of typical events.
- Code to implement:
  - Replace static window-size logic with per-automation computed window size and sane bounds.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*window_size* -q`

## Task 8: Score smoothing + split thresholds
- Test to write:
  - Add tests for EMA(5) gating and separate thresholds for stalled vs overactive.
- Code to implement:
  - Track recent scores per automation and apply EMA before classification; split thresholds.
- Verify:
  - `pytest tests/test_runtime_monitor.py::test_*ema* tests/test_runtime_monitor.py::test_*threshold* -q`

## Task 9: Dismissal-aware threshold multiplier
- Test to write:
  - Add tests that prior runtime suppressions raise alert thresholds.
- Code to implement:
  - Integrate suppression-store check and apply threshold multiplier.
- Verify:
  - `pytest tests/test_runtime_monitor.py tests/test_websocket_api.py -q`

## Task 10: Training hygiene guards
- Test to write:
  - Add tests ensuring restart recovery cooldown skips learning/scoring.
- Code to implement:
  - Add startup cooldown guard.
- Verify:
  - `pytest tests/test_runtime_monitor.py tests/test_init.py -q`

## Task 11: Runtime score telemetry (SQLite)
- Test to write:
  - Add tests for writing score rows with timestamp/features.
- Code to implement:
  - Add local SQLite telemetry store for runtime scoring records.
- Verify:
  - `pytest tests/test_runtime_monitor.py tests/test_init.py -q`

## Task 12: Review workflow foundation
- Test to write:
  - Add websocket tests for listing flagged runtime events and marking TP/FP; add precision aggregation tests.
- Code to implement:
  - Add review data model, websocket endpoints, and minimal response plumbing.
- Verify:
  - `pytest tests/test_websocket_api.py tests/test_runtime_monitor.py -q`

## Task 13: Full regression pass
- Test to write:
  - Run full test suite.
- Code to implement:
  - Fix regressions.
- Verify:
  - `pytest -q`
