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
- Jinja2 template syntax and semantic validation — existing
- WebSocket API for frontend communication (6 commands) — existing
- Lovelace card for issue display — existing
- Issue suppression with state learning — existing
- Conservative validation philosophy with opt-in strict modes — existing
- Sensor entities for issue count and health status — existing

### Active (v2.7.0)

- [ ] REQ-1: Replicate HA's template system implementation for Jinja2 validation
- [ ] REQ-2: Comprehensive filter/test/global catalog matching HA's actual template.py
- [ ] REQ-3: Reduce maintenance burden of hardcoded template semantics lists
- [ ] REQ-4: Clean up dead code from removed validations (undefined variables, basic type checking)

### Out of Scope

- Runtime template rendering or execution — autodoctor does static analysis only
- Blueprint variable validation — too many false positives statically
- Automation sequence order dependency checking — beyond static analysis scope
- Custom integration filter/test discovery — no reliable mechanism exists

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-1 | Phase 2, Phase 4 | Pending |
| REQ-2 | Phase 3, Phase 4 | Pending |
| REQ-3 | Phase 3, Phase 4 | Pending |
| REQ-4 | Phase 1 | Pending |

## Context

- Autodoctor is undergoing v2.7.0 validation scope narrowing to reduce false positives (target: <5% FP rate)
- Undefined template variable checking was removed due to 40% false positive rate with blueprints
- Basic service parameter type checking was removed due to YAML coercion making it unreliable
- Current Jinja2 validation uses hardcoded filter/test lists in `template_semantics.py` and `jinja_validator.py` that must be manually synced with HA releases
- HA does not expose validation APIs or allow introspection of its template environment — static lists are the only viable approach for pre-execution validation
- The Jinja2 overhaul should adopt HA's organizational patterns for defining filters/tests/globals to make future syncing easier

## Constraints

- **Runtime**: Home Assistant 2024.1+, Python 3.12+
- **No external dependencies**: All validation runs locally within HA, no cloud services
- **False positive budget**: <5% false positive rate — conservative by default, strict modes opt-in
- **HA API surface**: Must use stable HA APIs; internal APIs may change between versions

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Conservative-first validation | Better to miss issues than generate false positives | Good |
| State validation whitelist (6 domains) | Only validate domains with stable, well-defined states | Good |
| Opt-in strict modes for filters/tests/params | Users who want comprehensive checking can enable it | Good |
| Remove undefined variable checking | 40% false positive rate with blueprints unacceptable | Good |
| Static analysis over runtime rendering | Can validate before automations run, no execution risk | Good |
| Hardcoded filter/test lists | Only viable approach since HA doesn't expose introspection APIs | Revisit -- v2.7.0 replaces with HA-pattern catalog |

---
*Last updated: 2026-01-30 after roadmap creation*
