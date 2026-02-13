"""Tests for runtime health JSON state persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.autodoctor.runtime_health_state_store import (
    RUNTIME_HEALTH_STATE_SCHEMA_VERSION,
    RuntimeHealthStateStore,
)


def test_load_returns_defaults_when_file_missing(tmp_path: Path) -> None:
    """Missing state file should return a migrated default state."""
    state_path = tmp_path / "runtime_state.json"
    store = RuntimeHealthStateStore(path=state_path)

    state = store.load()

    assert state["schema_version"] == RUNTIME_HEALTH_STATE_SCHEMA_VERSION
    assert state["automations"] == {}
    assert state["alerts"]["global_count"] == 0


def test_v2_round_trip_preserves_bocpd_state(tmp_path: Path) -> None:
    """Schema-v2 BOCPD state should round-trip without mutation."""
    state_path = tmp_path / "runtime_state.json"
    store = RuntimeHealthStateStore(path=state_path)
    input_state = {
        "schema_version": RUNTIME_HEALTH_STATE_SCHEMA_VERSION,
        "automations": {
            "automation.kitchen": {
                "count_model": {
                    "buckets": {
                        "weekday_morning": {
                            "run_length_probs": [0.2, 0.8],
                            "observations": [2, 3],
                            "current_day": "2026-02-13",
                            "current_count": 1,
                            "map_run_length": 1,
                            "expected_rate": 2.5,
                        }
                    }
                },
                "gap_model": {"last_trigger": "2026-02-13T12:00:00+00:00"},
                "burst_model": {"recent_triggers": []},
            }
        },
        "alerts": {"date": "2026-02-13", "global_count": 3},
    }

    store.save(input_state)
    loaded = store.load()

    bucket = loaded["automations"]["automation.kitchen"]["count_model"]["buckets"][
        "weekday_morning"
    ]
    assert bucket["run_length_probs"] == [0.2, 0.8]
    assert bucket["observations"] == [2, 3]
    assert loaded["automations"]["automation.kitchen"]["gap_model"] == {
        "last_trigger": "2026-02-13T12:00:00+00:00"
    }
    assert loaded["alerts"] == {"date": "2026-02-13", "global_count": 3}


def test_save_uses_atomic_replace(tmp_path: Path, monkeypatch) -> None:
    """State save should write to a temp file and atomically replace target."""
    state_path = tmp_path / "runtime_state.json"
    store = RuntimeHealthStateStore(path=state_path)
    replaced: list[tuple[Path, Path]] = []

    def _capture_replace(self: Path, target: Path) -> Path:
        replaced.append((self, target))
        return Path.rename(self, target)

    monkeypatch.setattr(Path, "replace", _capture_replace)
    store.save({"schema_version": RUNTIME_HEALTH_STATE_SCHEMA_VERSION})

    assert replaced, "Expected save() to use Path.replace() for atomic write"
    assert replaced[0][1] == state_path
    assert state_path.exists()


def test_load_applies_schema_migration_defaults(tmp_path: Path) -> None:
    """Older JSON payloads should be migrated with new required keys."""
    state_path = tmp_path / "runtime_state.json"
    state_path.write_text(json.dumps({"automations": {"automation.legacy": {}}}))

    store = RuntimeHealthStateStore(path=state_path)
    loaded = store.load()

    assert loaded["schema_version"] == RUNTIME_HEALTH_STATE_SCHEMA_VERSION
    assert "alerts" in loaded
    legacy = loaded["automations"]["automation.legacy"]
    assert "count_model" in legacy
    assert "gap_model" in legacy
    assert "burst_model" in legacy


def test_migrate_sets_schema_version_2(tmp_path: Path) -> None:
    """Loading legacy payload should always bump schema to v2."""
    state_path = tmp_path / "runtime_state.json"
    state_path.write_text(json.dumps({"schema_version": 1, "automations": {}}))

    store = RuntimeHealthStateStore(path=state_path)
    loaded = store.load()

    assert loaded["schema_version"] == 2


def test_migrate_v1_to_v2_converts_buckets_to_bocpd(tmp_path: Path) -> None:
    """Legacy count buckets should migrate to BOCPD-compatible fields."""
    state_path = tmp_path / "runtime_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "automations": {
                    "automation.legacy": {
                        "count_model": {
                            "buckets": {
                                "weekday_morning": {
                                    "counts": [2, 4, 3],
                                    "current_day": "2026-02-13",
                                    "current_count": 1,
                                    "alpha": 10.0,
                                    "beta": 4.0,
                                    "mean": 3.0,
                                    "variance": 2.0,
                                    "vmr": 0.66,
                                }
                            }
                        }
                    }
                },
            }
        )
    )

    store = RuntimeHealthStateStore(path=state_path)
    loaded = store.load()

    bucket = loaded["automations"]["automation.legacy"]["count_model"]["buckets"][
        "weekday_morning"
    ]
    assert bucket["observations"] == [2, 4, 3]
    assert sum(bucket["run_length_probs"]) == pytest.approx(1.0)
    assert bucket["map_run_length"] >= 0
    assert bucket["expected_rate"] > 0.0
    assert "counts" not in bucket
    assert "alpha" not in bucket
    assert "beta" not in bucket
    assert "vmr" not in bucket


def test_migrate_v1_to_v2_strips_gap_model_fields(tmp_path: Path) -> None:
    """Legacy gap-model fields should be removed except last_trigger."""
    state_path = tmp_path / "runtime_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "automations": {
                    "automation.legacy": {
                        "gap_model": {
                            "intervals_minutes": [10.0, 12.0],
                            "lambda_per_minute": 0.1,
                            "p99_minutes": 30.0,
                            "last_trigger": "2026-02-13T11:50:00+00:00",
                        }
                    }
                },
            }
        )
    )

    store = RuntimeHealthStateStore(path=state_path)
    loaded = store.load()

    gap_model = loaded["automations"]["automation.legacy"]["gap_model"]
    assert gap_model == {"last_trigger": "2026-02-13T11:50:00+00:00"}
