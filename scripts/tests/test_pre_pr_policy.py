from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "pre_pr_policy.py"
    spec = importlib.util.spec_from_file_location("pre_pr_policy", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dev_branch_skips_base_sync():
    policy = _load_module()

    assert policy.resolve_required_base_branch("dev", "main") is None


def test_non_dev_branch_uses_pr_base_when_available():
    policy = _load_module()

    assert policy.resolve_required_base_branch("feature/nested-actions", "release") == (
        "release"
    )


def test_non_dev_branch_defaults_to_main_without_pr_base():
    policy = _load_module()

    assert policy.resolve_required_base_branch("feature/nested-actions", None) == "main"
