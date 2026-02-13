#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUFF_BIN="${RUFF_BIN:-.venv/bin/ruff}"
PYTEST_BIN="${PYTEST_BIN:-.venv/bin/pytest}"
PYRIGHT_BIN="${PYRIGHT_BIN:-.venv/bin/pyright}"
USE_SYSTEM_NODE="${USE_SYSTEM_NODE:-0}"
SKIP_MAIN_SYNC_CHECK="${SKIP_MAIN_SYNC_CHECK:-0}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"

CI_WORKFLOW_PATH=".github/workflows/ci.yml"
CARD_WORKFLOW_PATH=".github/workflows/build-card.yml"
CI_PYTHON_VERSION_DEFAULT="3.13"
CI_NODE_MAJOR_DEFAULT="20"

CI_PYTHON_VERSION="$(
  sed -nE 's/.*python-version:[[:space:]]*"?([0-9]+\.[0-9]+)"?.*/\1/p' "$CI_WORKFLOW_PATH" | head -n1
)"
if [[ -z "$CI_PYTHON_VERSION" ]]; then
  CI_PYTHON_VERSION="$CI_PYTHON_VERSION_DEFAULT"
fi

CI_NODE_MAJOR="$(
  sed -nE 's/.*node-version:[[:space:]]*"?([0-9]+)"?.*/\1/p' "$CARD_WORKFLOW_PATH" | head -n1
)"
if [[ -z "$CI_NODE_MAJOR" ]]; then
  CI_NODE_MAJOR="$CI_NODE_MAJOR_DEFAULT"
fi

if [[ ! -x "$RUFF_BIN" || ! -x "$PYTEST_BIN" || ! -x "$PYRIGHT_BIN" ]]; then
  echo "ERROR: Missing Python tooling in .venv."
  echo "Expected executables:"
  echo "  $RUFF_BIN"
  echo "  $PYTEST_BIN"
  echo "  $PYRIGHT_BIN"
  echo "Install with: python -m venv .venv && .venv/bin/pip install '.[dev]' pyright ruff"
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Missing Python interpreter for parity checks: $PYTHON_BIN"
  echo "Expected .venv to be created with Python $CI_PYTHON_VERSION to match CI."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required for frontend checks."
  exit 1
fi

VENV_PYTHON_MM="$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
if [[ "$VENV_PYTHON_MM" != "$CI_PYTHON_VERSION" ]]; then
  echo "ERROR: Python version mismatch with CI."
  echo "CI requires Python $CI_PYTHON_VERSION, but local env uses Python $VENV_PYTHON_MM."
  echo "Recreate .venv with Python $CI_PYTHON_VERSION, for example:"
  echo "  python$CI_PYTHON_VERSION -m venv .venv"
  echo "  .venv/bin/pip install '.[dev]' pyright ruff"
  exit 1
fi

if [[ "$SKIP_MAIN_SYNC_CHECK" != "1" ]]; then
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
NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]")"
if [[ "$NODE_MAJOR" != "$CI_NODE_MAJOR" ]]; then
  if [[ "$USE_SYSTEM_NODE" == "1" ]]; then
    echo "ERROR: System Node.js version mismatch with CI."
    echo "CI requires Node.js $CI_NODE_MAJOR, but current Node.js is $NODE_MAJOR."
    echo "Unset USE_SYSTEM_NODE to run npm commands through Node.js $CI_NODE_MAJOR parity mode."
    exit 1
  fi

  NPM_CLI_PATH="$(npm root -g)/npm/bin/npm-cli.js"
  if [[ ! -f "$NPM_CLI_PATH" ]]; then
    echo "ERROR: Unable to locate npm-cli.js for Node $CI_NODE_MAJOR parity mode."
    exit 1
  fi
  NPM_CMD=("npx" "-y" "node@${CI_NODE_MAJOR}" "$NPM_CLI_PATH")
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
