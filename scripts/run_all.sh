#!/usr/bin/env bash
# Full 24-hour pipeline — run from gpu-bakeoff/ after .env is configured.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DESTROYED=0
cleanup() {
  if [[ "$DESTROYED" -eq 0 ]]; then
    echo ""
    echo "== trap: destroying instances to stop billing =="
    python3 scripts/06_destroy.py || true
    DESTROYED=1
  fi
}
trap cleanup EXIT INT TERM

echo "== gpu-bakeoff full pipeline =="

./scripts/00_check_env.sh
python3 scripts/01_search_offers.py
python3 scripts/02_launch.py
python3 scripts/03_wait_running.py
python3 scripts/04_push_and_run.py

echo ""
echo "Matrix running on instances. Monitor:"
echo "  vastai show instances --raw"
echo "  vastai logs <INSTANCE_ID> --tail 50"
echo ""
read -r -p "Press Enter when matrix completes (or Ctrl+C to abort — instances will be destroyed)..."

python3 scripts/05_pull_results.py
python3 scripts/fill_boss_pack.py
python3 scripts/06_destroy.py
DESTROYED=1

echo ""
echo "Done. Open results/report.html and complete docs/BOSS_PACK.md"
