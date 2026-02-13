"""JSON-backed runtime health monitor state storage."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

RUNTIME_HEALTH_STATE_SCHEMA_VERSION = 1
_DEFAULT_FILENAME = "autodoctor_runtime_health_state.json"


def _default_automation_state() -> dict[str, Any]:
    """Return default structure for a single automation runtime model state."""
    return {
        "count_model": {
            "buckets": {},
            "negative_binomial_buckets": [],
            "anomaly_streak": 0,
        },
        "gap_model": {
            "intervals_minutes": [],
            "last_trigger": None,
            "lambda_per_minute": 0.0,
            "p99_minutes": 0.0,
        },
        "burst_model": {
            "recent_triggers": [],
            "baseline_rate_5m": 0.0,
        },
        "rate_limit": {
            "date": "",
            "count": 0,
            "last_alert": None,
        },
        "adaptation": {
            "threshold_multiplier": 1.0,
            "dismissed_count": 0,
        },
    }


def _default_state() -> dict[str, Any]:
    """Return default runtime health persisted state."""
    return {
        "schema_version": RUNTIME_HEALTH_STATE_SCHEMA_VERSION,
        "updated_at": "",
        "automations": {},
        "alerts": {
            "date": "",
            "global_count": 0,
        },
    }


def _deep_merge_defaults(payload: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Mutate payload by recursively filling any missing default keys."""
    for key, default_value in defaults.items():
        if key not in payload:
            payload[key] = deepcopy(default_value)
            continue
        if isinstance(default_value, dict) and isinstance(payload[key], dict):
            _deep_merge_defaults(payload[key], default_value)


class RuntimeHealthStateStore:
    """Persist runtime health model state in JSON with migration defaults."""

    def __init__(self, hass: Any | None = None, *, path: str | Path | None = None):
        if path is not None:
            self._path = Path(path)
        elif (
            hass is not None
            and hasattr(hass, "config")
            and hasattr(hass.config, "path")
        ):
            self._path = Path(hass.config.path(_DEFAULT_FILENAME))
        else:
            self._path = Path(_DEFAULT_FILENAME)

    @property
    def path(self) -> Path:
        """Return the configured state file path."""
        return self._path

    def load(self) -> dict[str, Any]:
        """Load state from disk, returning migrated defaults on failure or absence."""
        if not self._path.exists():
            return self._migrate({})
        try:
            raw_data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw_data, dict):
                return self._migrate({})
            return self._migrate(raw_data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return self._migrate({})

    def save(self, state: dict[str, Any]) -> None:
        """Persist state to disk using an atomic replace write."""
        migrated = self._migrate(state)
        migrated["updated_at"] = datetime.now(UTC).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(migrated, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self._path)

    def _migrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fill schema defaults and normalize automation state payloads."""
        migrated = deepcopy(payload)
        defaults = _default_state()
        _deep_merge_defaults(migrated, defaults)
        migrated["schema_version"] = RUNTIME_HEALTH_STATE_SCHEMA_VERSION

        automations = migrated.get("automations", {})
        if not isinstance(automations, dict):
            automations = {}
            migrated["automations"] = automations
        automations_dict = cast(dict[str, Any], automations)

        for automation_id, automation_state in list(automations_dict.items()):
            if not isinstance(automation_state, dict):
                automation_state = {}
                automations_dict[automation_id] = automation_state
            _deep_merge_defaults(automation_state, _default_automation_state())

        return migrated
