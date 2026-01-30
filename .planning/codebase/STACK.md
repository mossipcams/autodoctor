# Technology Stack

**Analysis Date:** 2026-01-30

## Languages

**Primary:**
- Python 3.12+ - Backend integration code, validation engines, knowledge base management (`custom_components/autodoctor/`)

**Secondary:**
- TypeScript 5.3 - Lovelace card frontend (`www/autodoctor/`)
- JavaScript (compiled from TS) - Frontend card asset bundled into `custom_components/autodoctor/www/autodoctor-card.js`

## Runtime

**Environment:**
- Home Assistant 2024.1+ - Required runtime environment as Home Assistant custom integration
- Python 3.12+ runtime via Home Assistant's embedded Python

**Package Manager:**
- pip (Python) - Installed via Home Assistant's package manager
- npm (JavaScript) - For frontend development only (`www/autodoctor/`)
- No lockfile required for Python (manifest.json specifies no external dependencies)

## Frameworks

**Core:**
- Home Assistant Core Framework - Integration lifecycle, entity management, event bus, config entries
- Home Assistant Components API - WebSocket API, binary sensors, regular sensors, config flows
- Home Assistant Helpers - Entity registry, device registry, area registry, config validation

**Templating:**
- Jinja2 2.x (via Home Assistant) - Template syntax validation and semantic analysis in `custom_components/autodoctor/jinja_validator.py`

**Frontend:**
- Lit 3.1.0 - Reactive web component framework for Lovelace card
- custom-card-helpers 1.9.0 - Home Assistant frontend utilities for card integration
- Home Assistant WebSocket client (implicit via custom-card-helpers)

**Configuration:**
- voluptuous - Schema validation for config flow and service schemas in `custom_components/autodoctor/config_flow.py`, `custom_components/autodoctor/__init__.py`

**Testing:**
- pytest 8.0.0+ - Test runner
- pytest-asyncio 0.23.0+ - Async test support (required for Home Assistant's async operations)
- pytest-homeassistant-custom-component 0.13.0+ - Home Assistant-specific test fixtures and mocking

**Build/Dev Tools:**
- Rollup 4.9.0 - Module bundler for TypeScript frontend
- @rollup/plugin-typescript 11.1.6 - TypeScript compilation in Rollup
- @rollup/plugin-terser 0.4.4 - Minification for production builds
- TypeScript 5.3.0 - Type checking and compilation
- Prettier 3.2.0 - Code formatting for both Python and JavaScript
- Ruff (Python) - Linting and code quality (configured in pyproject.toml)

## Key Dependencies

**Critical:**
- voluptuous - Required for HA config flow and validation schema definitions; used in `custom_components/autodoctor/config_flow.py`, `custom_components/autodoctor/__init__.py`
- Jinja2 - Required for template validation in `custom_components/autodoctor/jinja_validator.py`; provided by Home Assistant

**Home Assistant Built-ins (via homeassistant package):**
- `homeassistant.core` - Core types (HomeAssistant, ServiceCall, Event)
- `homeassistant.components.http` - StaticPathConfig for serving frontend assets
- `homeassistant.components.websocket_api` - WebSocket command registration
- `homeassistant.components.recorder` - History API for state observation
- `homeassistant.helpers` - Registry access (entity_registry, device_registry, area_registry)
- `homeassistant.config_entries` - Config flow and entry management

**Optional:**
- tdd-guard-pytest - Development tool for test-driven development in CI

## Configuration

**Environment:**
- Single-instance integration via `UNIQUE_ID = DOMAIN` in `custom_components/autodoctor/config_flow.py`
- Config entry options stored in Home Assistant's config database (not external)
- No environment variables required for deployment

**Configuration Keys (in options):**
- `CONF_HISTORY_DAYS` (default: 30) - Recorder lookback for state history
- `CONF_VALIDATE_ON_RELOAD` (default: True) - Validate on automation reload
- `CONF_DEBOUNCE_SECONDS` (default: 5) - Debounce delay for validation
- `CONF_STRICT_TEMPLATE_VALIDATION` (default: False) - Opt-in unknown filter/test warnings
- `CONF_STRICT_SERVICE_VALIDATION` (default: False) - Opt-in unknown parameter warnings

**Build Configuration:**
- `pyproject.toml` - Python project config with pytest settings, Ruff lint/format rules
- `www/autodoctor/tsconfig.json` - TypeScript compiler config (ES2021 target)
- `www/autodoctor/rollup.config.js` - Rollup bundling configuration (implicit, uses defaults)
- `custom_components/autodoctor/manifest.json` - Integration metadata, dependencies on Home Assistant components

## Platform Requirements

**Development:**
- Python 3.12+
- Node.js 18+ (for frontend building)
- Home Assistant development environment

**Production:**
- Home Assistant 2024.1+ installation
- Python 3.12+ (provided by Home Assistant)
- Dependencies: automation, recorder, frontend, http, lovelace components

**No External Services:**
- All validation runs locally within Home Assistant
- No cloud dependencies
- No API calls to external services
- Recorder component must be enabled for historical state analysis

---

*Stack analysis: 2026-01-30*
