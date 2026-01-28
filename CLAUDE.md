# Claude Code Instructions

## Commit and PR Rules

**NEVER include Co-Authored-By lines in commits or pull requests.**

Do not add any of these to commit messages:
- `Co-Authored-By: Claude`
- `Co-Authored-By: Anthropic`
- `Co-Authored-By: Opus`
- `Co-Authored-By: Sonnet`
- Any variation mentioning Claude, Anthropic, or AI assistance

Commit messages should only contain the commit subject and optional body describing the changes.

## Index Maintenance

The `index.md` file contains a codebase index for context. Update it when:
- Adding, removing, or renaming modules in `custom_components/autodoctor/`
- Adding new WebSocket API commands
- Adding new services
- Changing the directory structure
- Adding new test files

Do NOT update for minor changes like bug fixes, refactoring within existing modules, or documentation updates.

## Pre-Commit Verification

Before committing, verify that `index.md` is accurate if structural changes were made. The pre-commit hook will remind you to check.
