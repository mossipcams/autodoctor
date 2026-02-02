# Autodoctor

## What This Is

A Home Assistant custom integration that validates automations to detect state-related issues before they cause silent failures. It performs static analysis on automation configurations — checking entity references, state values, service calls, and Jinja2 templates — and surfaces problems as actionable warnings before automations ever run.

## Core Value

Catch automation mistakes before they fail silently at runtime. Every validation must be high-confidence — better to miss an issue than generate a false positive that erodes trust.

## Requirements

### Validated

- Automation parsing with 21 trigger types and 10 condition types — existing
- State reference validation against entity/device/area registries — existing
- Knowledge base with multi-source state truth (device classes, learned states, capabilities, schema, history) — existing
- Service call validation against HA service registry — existing
- Jinja2 template syntax and filter/test validation — existing
- WebSocket API for frontend communication (10 commands) — existing
- Lovelace card for issue display — existing
- Issue suppression with state learning and orphan auto-cleanup — existing
- Conservative validation philosophy with opt-in strict modes — existing
- Sensor entities for issue count and health status — existing
- Enum sensor validation via device_class detection and fallback validator — v2.16.0
- Targeted single-automation validation on save — v2.15.0
- Removed for_each entity extraction (false positive source) — v2.14.0
- Removed filter argument count validation (unreliable with YAML coercion) — v2.14.0
- Removed duplicate template entity validation path (redundant with validator.py) — v2.14.0
- IssueType enum narrowed to 13 high-confidence members — v2.14.0
- Orphan suppression auto-cleanup on store load — v2.14.0

### Active

- [ ] Full Pyright strict type safety across production and test code
- [ ] pyrightconfig.json with strict mode, HA private import suppression
- [ ] CI typecheck job passes clean (0 errors)

### Deferred

- REQ-1: Replicate HA's template system implementation for Jinja2 validation — deferred from v2.7.0
- REQ-2: Comprehensive filter/test/global catalog matching HA's actual template.py — deferred from v2.7.0
- REQ-3: Reduce maintenance burden of hardcoded template semantics lists — deferred from v2.7.0
- REQ-4: Clean up dead code from removed validations — deferred from v2.7.0

### Out of Scope

- Runtime template rendering or execution — autodoctor does static analysis only
- Blueprint variable validation — too many false positives statically
- Automation sequence order dependency checking — beyond static analysis scope
- Custom integration filter/test discovery — no reliable mechanism exists

## Traceability

No active milestone — see `.planning/milestones/` for historical traceability.

## Context

- v2.14.0 shipped: removed 3 false-positive-generating validation paths (~1,676 lines cut)
- Pattern established: validation paths that can't achieve high confidence get cut rather than patched
- Previous removals: undefined template variable checking (40% FP rate), basic service parameter type checking (YAML coercion)
- Current validation: 13 high-confidence IssueType members across entity/state, service, and template syntax checks
- Jinja2 validation uses hardcoded filter/test lists in `template_semantics.py` and `jinja_validator.py` that must be manually synced with HA releases
- HA does not expose validation APIs or allow introspection of its template environment
- 5,921 LOC Python across custom_components/autodoctor/
- 477 tests passing (2 skipped pre-existing stubs), 10 guard tests protecting removed features
- CI pipeline: pytest + ruff + Pyright on every PR

## Constraints

- **Runtime**: Home Assistant 2024.1+, Python 3.12+
- **No external dependencies**: All validation runs locally within HA, no cloud services
- **False positive budget**: <5% false positive rate — conservative by default, strict modes opt-in
- **HA API surface**: Must use stable HA APIs; internal APIs may change between versions

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Conservative-first validation | Better to miss issues than generate false positives | Good |
| State validation whitelist (10 domains) | Only validate domains with stable, well-defined states | Good |
| Enum sensor validation without whitelist | Validate device_class: enum sensors via fallback path to avoid history queries for all sensors | Good |
| Opt-in strict modes for filters/tests/params | Users who want comprehensive checking can enable it | Good |
| Remove undefined variable checking | 40% false positive rate with blueprints unacceptable | Good |
| Static analysis over runtime rendering | Can validate before automations run, no execution risk | Good |
| Hardcoded filter/test lists | Only viable approach since HA doesn't expose introspection APIs | Revisit -- v2.7.0 replaces with HA-pattern catalog |
| Remove rather than patch false-positive paths | Unreliable heuristics erode trust; conservative philosophy requires high confidence | Good -- v2.14.0 |
| Guard tests for removed features | 10 tests prevent accidental re-addition of cut validation paths | Good -- v2.14.0 |
| Lazy orphan suppression cleanup | Clean on load rather than storage version bump; simpler and sufficient | Good -- v2.14.0 |

---
*Last updated: 2026-02-02 after v2.17.0 milestone start (Pyright Implementation)*
