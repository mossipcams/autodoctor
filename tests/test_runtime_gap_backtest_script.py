"""Tests for the runtime gap regression backtest harness script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_runtime_gap_backtest_script_supports_dry_run() -> None:
    """Backtest harness should expose deterministic dry-run suite output."""
    script = Path("scripts/runtime_gap_backtest.py")
    result = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "tests/test_runtime_gap_replay.py" in result.stdout
    assert "tests/test_runtime_gap_detector.py" in result.stdout
