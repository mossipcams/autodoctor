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
- WebSocket API for frontend communication (6 commands) — existing
- Lovelace card for issue display — existing
- Issue suppression with state learning — existing
- Conservative validation philosophy with opt-in strict modes — existing
- Sensor entities for issue count and health status — existing

### Active

None — no milestone in progress.

### Completed (v2.14.0 — Validation Narrowing)

- [x] CUT-1: Remove duplicate template entity validation path from jinja_validator (Phase 24)
- [x] CUT-2: Remove filter argument count validation (Phase 23)
- [x] CUT-3: Remove for_each entity extraction from analyzer (Phase 22)

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

| Requirement | Phase | Status |
|-------------|-------|--------|
| CUT-1 | Phase 24 | Complete |
| CUT-2 | Phase 23 | Complete |
| CUT-3 | Phase 22 | Complete |

## Context

- v2.14.0 focuses on removing validation paths that generate false positives in the wild
- Three cuts identified: duplicate template entity validation, filter argument count checking, and for_each entity extraction
- Previous removals: undefined template variable checking (40% FP rate), basic service parameter type checking (YAML coercion)
- Pattern: validation paths that can't achieve high confidence get cut rather than patched
- Current Jinja2 validation uses hardcoded filter/test lists in `template_semantics.py` and `jinja_validator.py` that must be manually synced with HA releases
- HA does not expose validation APIs or allow introspection of its template environment

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

---
*Last updated: 2026-02-02 after quick-012 (enum sensor validation)*
