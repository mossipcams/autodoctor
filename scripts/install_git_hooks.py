from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

HOOK_NAMES = ("pre-commit", "pre-push")

RunGitCommand = Callable[..., CompletedProcess[str]]


def resolve_git_hooks_dir(
    repo_root: Path,
    run: RunGitCommand = subprocess.run,
) -> Path:
    """Return Git's real hooks directory, including linked worktree setups."""
    result = run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    hooks_path = Path(result.stdout.strip())
    if hooks_path.is_absolute():
        return hooks_path
    return repo_root / hooks_path


def install_hooks(repo_root: Path, hooks_dir: Path) -> list[Path]:
    template_dir = repo_root / "scripts" / "git-hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    installed: list[Path] = []
    for hook_name in HOOK_NAMES:
        source = template_dir / hook_name
        destination = hooks_dir / hook_name
        shutil.copyfile(source, destination)
        current_mode = destination.stat().st_mode
        executable_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        os.chmod(destination, executable_mode)
        installed.append(destination)

    return installed


def main(argv: list[str]) -> int:
    repo_root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    hooks_dir = resolve_git_hooks_dir(repo_root)
    installed = install_hooks(repo_root, hooks_dir)

    for hook_path in installed:
        print(f"Installed {hook_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
