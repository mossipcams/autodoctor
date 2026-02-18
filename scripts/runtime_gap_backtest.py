#!/usr/bin/env python3
"""Run runtime-gap regression guardrail suites."""

from __future__ import annotations

import argparse
import subprocess
import sys

GUARDRAIL_SUITES = [
    "tests/test_runtime_gap_replay.py",
    "tests/test_runtime_gap_detector.py",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected suites without executing pytest.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        for suite in GUARDRAIL_SUITES:
            print(suite)
        return 0

    cmd = [sys.executable, "-m", "pytest", "-q", *GUARDRAIL_SUITES]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
