#!/usr/bin/env bash
# Free local checks before ./scripts/smoke_qwen.sh (no Vast billing).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

./scripts/00_check_env.sh
uv run python scripts/preflight_smoke.py
