from __future__ import annotations

import sys


def resolve_required_base_branch(
    current_branch: str | None, pr_base_branch: str | None
) -> str | None:
    """Return the branch that must be up to date, or None to skip the check."""
    if current_branch == "dev":
        return None
    if pr_base_branch:
        return pr_base_branch
    return "main"


def main(argv: list[str]) -> int:
    current_branch = argv[1] if len(argv) > 1 else None
    pr_base_branch = argv[2] if len(argv) > 2 else None
    required_base_branch = resolve_required_base_branch(current_branch, pr_base_branch)
    if required_base_branch is None:
        print("SKIP")
    else:
        print(required_base_branch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
