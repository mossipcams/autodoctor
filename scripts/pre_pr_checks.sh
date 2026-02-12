#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUFF_BIN="${RUFF_BIN:-.venv/bin/ruff}"
PYTEST_BIN="${PYTEST_BIN:-.venv/bin/pytest}"
PYRIGHT_BIN="${PYRIGHT_BIN:-.venv/bin/pyright}"
USE_SYSTEM_NODE="${USE_SYSTEM_NODE:-0}"

if [[ ! -x "$RUFF_BIN" || ! -x "$PYTEST_BIN" || ! -x "$PYRIGHT_BIN" ]]; then
  echo "ERROR: Missing Python tooling in .venv."
  echo "Expected executables:"
  echo "  $RUFF_BIN"
  echo "  $PYTEST_BIN"
  echo "  $PYRIGHT_BIN"
  echo "Install with: python -m venv .venv && .venv/bin/pip install '.[dev]' pyright ruff"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required for frontend checks."
  exit 1
fi

if [[ "$USE_SYSTEM_NODE" != "1" ]]; then
  echo "[0/8] Verify branch is up to date with origin/main"
  git fetch --quiet origin main
  ORIGIN_MAIN_SHA="$(git rev-parse origin/main)"
  MERGE_BASE_SHA="$(git merge-base HEAD origin/main)"
  if [[ "$MERGE_BASE_SHA" != "$ORIGIN_MAIN_SHA" ]]; then
    echo "ERROR: Branch is not up to date with origin/main."
    echo "Rebase or merge main before opening/updating a PR:"
    echo "  git fetch origin main && git rebase origin/main"
    exit 1
  fi
fi

NPM_CMD=("npm")
if [[ "$USE_SYSTEM_NODE" != "1" ]]; then
  NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
  if [[ "$NODE_MAJOR" != "20" ]]; then
    NPM_CLI_PATH="$(npm root -g)/npm/bin/npm-cli.js"
    if [[ ! -f "$NPM_CLI_PATH" ]]; then
      echo "ERROR: Unable to locate npm-cli.js for Node 20 parity mode."
      echo "Set USE_SYSTEM_NODE=1 to bypass, but this may diverge from CI."
      exit 1
    fi
    NPM_CMD=("npx" "-y" "node@20" "$NPM_CLI_PATH")
  fi
fi

echo "[1/8] Ruff lint"
"$RUFF_BIN" check custom_components/ tests/

echo "[2/8] Ruff format check"
"$RUFF_BIN" format --check custom_components/ tests/

echo "[3/8] Pyright"
"$PYRIGHT_BIN" custom_components/

echo "[4/8] Python tests"
"$PYTEST_BIN" tests/ -v --tb=short

echo "[5/8] Frontend tests"
pushd www/autodoctor >/dev/null
"${NPM_CMD[@]}" ci
"${NPM_CMD[@]}" test

echo "[6/8] Frontend build"
"${NPM_CMD[@]}" run build
popd >/dev/null

echo "[7/8] Verify generated card is committed and in sync"
if ! git diff --quiet custom_components/autodoctor/www/autodoctor-card.js; then
  echo "ERROR: custom_components/autodoctor/www/autodoctor-card.js is out of date."
  echo "Run: cd www/autodoctor && npm run build"
  git --no-pager diff --stat custom_components/autodoctor/www/autodoctor-card.js
  exit 1
fi

if ! cmp -s \
  custom_components/autodoctor/www/autodoctor-card.js \
  www/autodoctor/autodoctor-card.js; then
  echo "ERROR: Built card artifacts are out of sync:"
  echo "  custom_components/autodoctor/www/autodoctor-card.js"
  echo "  www/autodoctor/autodoctor-card.js"
  echo "Run: cd www/autodoctor && npm run build"
  exit 1
fi

echo "[8/8] Done"
echo "All pre-PR checks passed."
