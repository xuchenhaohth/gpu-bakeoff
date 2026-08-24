#!/usr/bin/env bash
# Full pipeline — run from gpu-bakeoff/ after .env is configured.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DESTROYED=0
cleanup() {
  if [[ "$DESTROYED" -eq 0 ]]; then
    echo ""
    echo "== trap: destroying instances to stop billing =="
    uv run python scripts/02_run_bakeoff.py --destroy-only || true
    DESTROYED=1
  fi
}
trap cleanup EXIT INT TERM

echo "== gpu-bakeoff full pipeline (serial per SKU) =="

./scripts/00_check_env.sh
uv run python scripts/01_search_offers.py
uv run python scripts/02_run_bakeoff.py
uv run python scripts/fill_boss_pack.py
DESTROYED=1

echo ""
echo "Done. Open results/report.html and complete docs/BOSS_PACK.md"
