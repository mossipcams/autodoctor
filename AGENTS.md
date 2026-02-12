# Agent Instructions

- NEVER open or update a PR until local CI parity checks pass.
- REQUIRED before PR creation or PR update:
  - Run `scripts/pre_pr_checks.sh`.
  - Ensure branch is rebased/merged with latest `origin/main` (the script enforces this).
  - If it changes files (format/build artifacts), commit those changes first.
  - Re-run `scripts/pre_pr_checks.sh` and confirm it passes with no errors.
- Minimum verification expectation remains: always run all tests before committing.
