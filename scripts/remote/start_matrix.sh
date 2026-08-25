#!/usr/bin/env bash
# Start bakeoff harness in background; verify pid before SSH session exits.
set -euo pipefail
cd "$(dirname "$0")"
BAKEOFF_ROOT="$(pwd)"
PID_FILE="$BAKEOFF_ROOT/results/HARNESS.pid"
RUN_LOG="$BAKEOFF_ROOT/run.log"

chmod +x "$BAKEOFF_ROOT/onstart.sh" "$BAKEOFF_ROOT/install_stack.sh"
mkdir -p "$BAKEOFF_ROOT/results"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "Harness already running (pid $old_pid)"
    exit 0
  fi
fi

nohup bash --noprofile --norc -c \
  'cd /workspace/bakeoff && ./onstart.sh && python3 run_matrix.py; echo $? > results/DONE' \
  >>"$RUN_LOG" 2>&1 < /dev/null &
echo $! >"$PID_FILE"
sleep 1
if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "ERROR: harness died immediately" >&2
  tail -n 40 "$RUN_LOG" >&2 || true
  exit 1
fi
echo "Harness started pid=$(cat "$PID_FILE")"
