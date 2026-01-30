# External Integrations

**Analysis Date:** 2026-01-30

## APIs & External Services

**None.** Autodoctor does not integrate with external APIs or services. All validation is performed locally within the Home Assistant instance.

## Data Storage

**Databases:**
- Home Assistant's built-in database (SQLite by default) - Used by recorder component for state history
  - Connection: Integrated via `homeassistant.components.recorder` (implicit, no direct connection string)
  - Access: Via `get_significant_states()` from recorder history API in `custom_components/autodoctor/knowledge_base.py`
  - Purpose: Reading historical state observations for state validation knowledge base

**File Storage:**
- Local filesystem only
  - Configuration: Home Assistant's config directory (`/config/custom_components/autodoctor/`)
  - Suppression store: JSON file in Home Assistant config directory (via `custom_components/autodoctor/suppression_store.py`)
  - Learned states store: JSON file in Home Assistant config directory (via `custom_components/autodoctor/learned_states_store.py`)
  - Frontend assets: `custom_components/autodoctor/www/autodoctor-card.js` served via Home Assistant's static file server

**Caching:**
- In-memory only (Python runtime)
- No external caching service
- State knowledge base cached in memory during runtime in `custom_components/autodoctor/knowledge_base.py`

## Authentication & Identity

**Auth Provider:**
- Home Assistant's built-in authentication
  - WebSocket API commands are authenticated via Home Assistant's session system
  - No separate API keys or credentials required
  - Configuration entries managed by Home Assistant's core

## Home Assistant Component Dependencies

**Required Components (manifest.json dependencies):**
- `automation` - Access to automation entity registry and configs
- `recorder` - Historical state data via `get_significant_states()`
- `frontend` - Lovelace UI framework for card rendering
- `http` - Static file serving for frontend assets
- `lovelace` - Lovelace card system integration

**Loaded After:**
- `automation` (specified in `after_dependencies`) - Ensures automations are loaded before validation begins

**Home Assistant Registries (via helpers):**
- Entity Registry (`homeassistant.helpers.entity_registry`) - Entity existence checks in `custom_components/autodoctor/validator.py`
- Device Registry (`homeassistant.helpers.device_registry`) - Device ID validation in `custom_components/autodoctor/validator.py`
- Area Registry (`homeassistant.helpers.area_registry`) - Area ID validation in `custom_components/autodoctor/validator.py`

## Monitoring & Observability

**Error Tracking:**
- None - Errors logged to Home Assistant's log system via Python's logging module
- All exceptions caught and reported as validation issues or repair suggestions

**Logs:**
- Python logging to Home Assistant logs (`_LOGGER = logging.getLogger(__name__)` in all modules)
- Log level controlled by Home Assistant's logging configuration
- No external log aggregation

## CI/CD & Deployment

**Hosting:**
- Home Assistant user's instance only
- No cloud hosting or central deployment
- Manual installation via HACS or direct file copying

**CI Pipeline:**
- GitHub Actions (implicit from git repo structure, not documented in this analysis)
- pytest for test execution
- Ruff for linting

## Services

**Outgoing Services:**
- `autodoctor.validate` - Service to run validation (defined in `custom_components/autodoctor/services.yaml`)
- `autodoctor.validate_automation` - Service to validate specific automation
- `autodoctor.refresh_knowledge_base` - Service to rebuild state knowledge base

**Service Validation:**
- Home Assistant's service registry is read but not written to
- Service call validation in `custom_components/autodoctor/service_validator.py` validates against registry
- No service calls made to external systems

## Webhooks & Callbacks

**Incoming:**
- WebSocket API commands (authentication required)
  - `autodoctor/issues` - Get current issues
  - `autodoctor/refresh` - Trigger validation refresh
  - `autodoctor/validation` - Get validation issues only
  - `autodoctor/validation/run` - Run validation on demand
  - `autodoctor/suppress` - Suppress an issue (with optional state learning)
  - `autodoctor/clear_suppressions` - Clear all suppressions
- Implemented in `custom_components/autodoctor/websocket_api.py`

**Outgoing:**
- None - Autodoctor does not initiate webhooks or callbacks
- Unsubscribe listeners cleanup in `custom_components/autodoctor/__init__.py` for reload handling

## Event Integration

**Home Assistant Events:**
- `EVENT_HOMEASSISTANT_STARTED` - Hook for initial validation (in `custom_components/autodoctor/__init__.py`)
- Listens to automation reload events via config entry reload listener
- No custom events published

## Frontend Communication

**WebSocket Messages:**
- Bidirectional WebSocket API via Home Assistant's websocket_api component
- Messages formatted as JSON with `type` field
- All responses include message ID for request-response correlation
- Error responses include error code and message
- Implemented in `custom_components/autodoctor/websocket_api.py`

## Entity Management

**Published Entities:**
- `sensor.autodoctor_issue_count` - Current number of validation issues (via `custom_components/autodoctor/sensor.py`)
- `binary_sensor.autodoctor_health` - Integration health status (via `custom_components/autodoctor/binary_sensor.py`)
- Entities registered via Home Assistant's entity platform system

## Template Variables

**Jinja2 Built-ins:**
- Standard Jinja2 functions (filter, if, for, etc.)
- Home Assistant filters (as_datetime, as_timestamp, etc.) - Reference list in `custom_components/autodoctor/jinja_validator.py`
- Home Assistant custom filters (is_defined, is_number, has_value, etc.)
- No external template plugins

## Repair Framework

**Issue Reporting:**
- Home Assistant's Repair framework (implicit via reported issues)
- Fix suggestions provided through WebSocket API
- Entity suggestions via fuzzy matching in `custom_components/autodoctor/validator.py`

---

*Integration audit: 2026-01-30*
