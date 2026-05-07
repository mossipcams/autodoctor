from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "install_git_hooks.py"
    spec = importlib.util.spec_from_file_location("install_git_hooks", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_install_hooks_copies_pre_commit_and_pre_push_templates(tmp_path):
    installer = _load_module()
    repo_root = tmp_path / "repo"
    hooks_dir = tmp_path / "hooks"
    template_dir = repo_root / "scripts" / "git-hooks"
    template_dir.mkdir(parents=True)
    hooks_dir.mkdir()
    (template_dir / "pre-commit").write_text("#!/usr/bin/env bash\necho pre-commit\n")
    (template_dir / "pre-push").write_text("#!/usr/bin/env bash\necho pre-push\n")

    installed = installer.install_hooks(repo_root, hooks_dir)

    assert installed == [hooks_dir / "pre-commit", hooks_dir / "pre-push"]
    assert (
        hooks_dir / "pre-commit"
    ).read_text() == "#!/usr/bin/env bash\necho pre-commit\n"
    assert (
        hooks_dir / "pre-push"
    ).read_text() == "#!/usr/bin/env bash\necho pre-push\n"
    assert os.access(hooks_dir / "pre-commit", os.X_OK)
    assert os.access(hooks_dir / "pre-push", os.X_OK)


def test_resolve_git_hooks_dir_supports_worktree_absolute_path(tmp_path):
    installer = _load_module()
    hooks_dir = tmp_path / "main" / ".git" / "hooks"

    class FakeResult:
        stdout = f"{hooks_dir}\n"

    def fake_run(cmd, cwd, capture_output, text, check):
        assert cmd == ["git", "rev-parse", "--git-path", "hooks"]
        assert cwd == tmp_path
        assert capture_output is True
        assert text is True
        assert check is True
        return FakeResult()

    assert installer.resolve_git_hooks_dir(tmp_path, run=fake_run) == hooks_dir


def test_tracked_hooks_run_pre_pr_checks_for_dev_push_and_dev_upstream():
    repo_root = Path(__file__).resolve().parents[2]
    pre_commit = repo_root / "scripts" / "git-hooks" / "pre-commit"
    pre_push = repo_root / "scripts" / "git-hooks" / "pre-push"
    pre_pr_checks = repo_root / "scripts" / "pre_pr_checks.sh"

    pre_commit_text = pre_commit.read_text()
    pre_push_text = pre_push.read_text()
    pre_pr_checks_text = pre_pr_checks.read_text()

    assert "scripts/pre_pr_checks.sh" in pre_commit_text
    assert "refs/remotes/origin/dev" in pre_commit_text
    assert "AUTODOCTOR_PRE_PR_BASE_BRANCH=dev" in pre_commit_text
    assert "scripts/pre_pr_checks.sh" in pre_push_text
    assert "refs/heads/dev" in pre_push_text
    assert "AUTODOCTOR_PRE_PR_BASE_BRANCH=dev" in pre_push_text
    assert "AUTODOCTOR_PRE_PR_BASE_BRANCH" in pre_pr_checks_text
