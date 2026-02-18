# Agent Instructions

- NEVER open or update a PR until local CI parity checks pass.
- REQUIRED before PR creation or PR update:
  - Run `scripts/pre_pr_checks.sh`.
  - Ensure branch is rebased/merged with latest `origin/main` (the script enforces this).
  - If it changes files (format/build artifacts), commit those changes first.
  - Re-run `scripts/pre_pr_checks.sh` and confirm it passes with no errors.
- Minimum verification expectation remains: always run all tests before committing.
- For Home Assistant debugging tasks, automatically call the `ha-logs` MCP tools (start with `core_logs`, then use `query_core_logs`/`summarize_core_logs`/`triage_core_logs` as needed) before proposing fixes.
- TDD strict red/green is not required for Markdown-only documentation edits (`*.md` files).
