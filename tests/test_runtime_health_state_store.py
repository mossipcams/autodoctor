"""Tests for runtime health JSON state persistence."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    """Saved runtime state should be loaded back without data loss."""
    state_path = tmp_path / "runtime_state.json"
    store = RuntimeHealthStateStore(path=state_path)
    input_state = {
        "schema_version": RUNTIME_HEALTH_STATE_SCHEMA_VERSION,
        "automations": {
            "automation.kitchen": {
                "count_model": {"buckets": {}},
                "gap_model": {"intervals_minutes": [10.0, 12.0]},
                "burst_model": {"recent_triggers": []},
            }
        },
        "alerts": {"date": "2026-02-13", "global_count": 3},
    }

    store.save(input_state)
    loaded = store.load()

    assert loaded["automations"]["automation.kitchen"]["gap_model"][
        "intervals_minutes"
    ] == [10.0, 12.0]
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
