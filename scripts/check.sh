#!/usr/bin/env bash
# Lint, typecheck, and smoke-test the bake-off pipeline.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPYCACHEPREFIX="$ROOT/.pycache"

echo "== ruff =="
uv run ruff check scripts/

echo "== compileall =="
uv run python -m compileall -q scripts/

echo "== mypy =="
uv run mypy scripts/

echo "== dry-run smoke =="
uv run python scripts/dry_run_local.py

echo "All checks passed."
