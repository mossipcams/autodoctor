"""JSON-backed runtime health monitor state storage."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

RUNTIME_HEALTH_STATE_SCHEMA_VERSION = 2
_DEFAULT_FILENAME = "autodoctor_runtime_health_state.json"


def _default_automation_state() -> dict[str, Any]:
    """Return default structure for a single automation runtime model state."""
    return {
        "count_model": {
            "buckets": {},
            "anomaly_streak": 0,
        },
        "gap_model": {
            "last_trigger": None,
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
        self._hass = hass
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
        self._dir_ensured = False

    @property
    def path(self) -> Path:
        """Return the configured state file path."""
        return self._path

    async def async_load(self) -> dict[str, Any]:
        """Load state from disk asynchronously via executor."""
        return await self._hass.async_add_executor_job(self.load)

    async def async_save(self, state: dict[str, Any]) -> None:
        """Persist state to disk asynchronously via executor."""
        await self._hass.async_add_executor_job(self.save, state)

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
        if not self._dir_ensured:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._dir_ensured = True
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
            self._migrate_automation_state(cast(dict[str, Any], automation_state))
            _deep_merge_defaults(
                cast(dict[str, Any], automation_state), _default_automation_state()
            )

        return migrated

    def _migrate_automation_state(self, automation_state: dict[str, Any]) -> None:
        count_model_raw = automation_state.get("count_model")
        count_model = (
            cast(dict[str, Any], count_model_raw)
            if isinstance(count_model_raw, dict)
            else {}
        )
        buckets_raw = count_model.get("buckets")
        buckets = (
            cast(dict[str, Any], buckets_raw) if isinstance(buckets_raw, dict) else {}
        )
        migrated_buckets: dict[str, Any] = {}
        for bucket_name, bucket_state_raw in list(buckets.items()):
            bucket_state = (
                cast(dict[str, Any], bucket_state_raw)
                if isinstance(bucket_state_raw, dict)
                else {}
            )
            migrated_buckets[bucket_name] = self._migrate_count_bucket(bucket_state)

        automation_state["count_model"] = {
            "buckets": migrated_buckets,
            "anomaly_streak": max(
                0, self._coerce_int(count_model.get("anomaly_streak"), 0)
            ),
        }

        gap_model_raw = automation_state.get("gap_model")
        gap_model = (
            cast(dict[str, Any], gap_model_raw)
            if isinstance(gap_model_raw, dict)
            else {}
        )
        last_trigger = gap_model.get("last_trigger")
        automation_state["gap_model"] = {
            "last_trigger": last_trigger if isinstance(last_trigger, str) else None
        }

    def _migrate_count_bucket(self, bucket_state: dict[str, Any]) -> dict[str, Any]:
        run_length_probs_raw = bucket_state.get("run_length_probs")
        observations_raw = bucket_state.get("observations")
        if isinstance(run_length_probs_raw, list) and isinstance(
            observations_raw, list
        ):
            run_length_probs_values = cast(list[Any], run_length_probs_raw)
            run_length_probs = self._normalize_probs(
                [self._coerce_float(value, 0.0) for value in run_length_probs_values]
            )
            observations = [
                max(0, self._coerce_int(value, 0))
                for value in cast(list[Any], observations_raw)
            ]
            map_run_length = self._coerce_int(
                bucket_state.get("map_run_length"),
                self._argmax(run_length_probs),
            )
            expected_rate = self._coerce_float(
                bucket_state.get("expected_rate"),
                self._mean(observations),
            )
            return {
                "run_length_probs": run_length_probs,
                "observations": observations,
                "current_day": str(bucket_state.get("current_day", "")),
                "current_count": max(
                    0, self._coerce_int(bucket_state.get("current_count"), 0)
                ),
                "map_run_length": max(0, map_run_length),
                "expected_rate": max(0.0, expected_rate),
            }

        legacy_counts_raw = bucket_state.get("counts")
        legacy_counts = (
            [
                max(0, self._coerce_int(value, 0))
                for value in cast(list[Any], legacy_counts_raw)
            ]
            if isinstance(legacy_counts_raw, list)
            else []
        )
        return {
            "run_length_probs": [1.0],
            "observations": legacy_counts,
            "current_day": str(bucket_state.get("current_day", "")),
            "current_count": max(
                0, self._coerce_int(bucket_state.get("current_count"), 0)
            ),
            "map_run_length": 0,
            "expected_rate": self._mean(legacy_counts),
        }

    @staticmethod
    def _normalize_probs(values: list[float]) -> list[float]:
        if not values:
            return [1.0]
        clamped = [max(0.0, float(value)) for value in values]
        total = float(sum(clamped))
        if total <= 0.0:
            return [1.0]
        normalized = [value / total for value in clamped]
        while len(normalized) > 1 and normalized[-1] <= 1e-15:
            normalized.pop()
        return normalized

    @staticmethod
    def _argmax(values: list[float]) -> int:
        if not values:
            return 0
        return int(max(range(len(values)), key=values.__getitem__))

    @staticmethod
    def _mean(values: list[int]) -> float:
        if not values:
            return 0.0
        return float(sum(values)) / float(len(values))

    @staticmethod
    def _coerce_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _coerce_float(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
