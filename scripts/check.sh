#!/usr/bin/env bash
# Lint, typecheck, and smoke-test the bake-off pipeline.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPYCACHEPREFIX="$ROOT/.pycache"

echo "== ruff =="
python3 -m ruff check scripts/

echo "== compileall =="
python3 -m compileall -q scripts/

echo "== mypy =="
python3 -m mypy scripts/

echo "== dry-run smoke =="
python3 scripts/dry_run_local.py

echo "All checks passed."
