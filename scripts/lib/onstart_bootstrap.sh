#!/usr/bin/env bash
# Vast --onstart bootstrap: clone public repo, run harness, upload results to HF.
# Uploaded at instance create time (not from git clone).
set -euo pipefail

GIT_URL="${BAKEOFF_GIT_URL:-https://github.com/xuchenhaohth/gpu-bakeoff.git}"
GIT_REF="${BAKEOFF_GIT_REF:-main}"
BAKEOFF_ROOT="/workspace/bakeoff"
CLONE_DIR="/tmp/bakeoff-clone"

echo "== bakeoff bootstrap =="
echo "GIT_URL=${GIT_URL} GIT_REF=${GIT_REF} SKU=${BAKEOFF_SKU:-unknown}"

export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq git rsync curl wget python3 procps build-essential >/dev/null 2>&1 || true
fi

mkdir -p "$BAKEOFF_ROOT"
rm -rf "$CLONE_DIR"
echo "[progress] onstart git_clone"
git clone --depth 1 --branch "$GIT_REF" "$GIT_URL" "$CLONE_DIR"

echo "[progress] onstart rsync_harness"
rsync -a "${CLONE_DIR}/scripts/remote/" "$BAKEOFF_ROOT/"
mkdir -p "$BAKEOFF_ROOT/config"
cp -a "${CLONE_DIR}/config/." "$BAKEOFF_ROOT/config/"

# Mirror SSH push .env.sku so onstart/run_matrix see Docker -e vars.
{
  echo "BAKEOFF_SKU=${BAKEOFF_SKU:-unknown}"
  echo "BAKEOFF_GPU_COUNT=${BAKEOFF_GPU_COUNT:-1}"
  if [[ -n "${BAKEOFF_MODELS:-}" ]]; then
    echo "BAKEOFF_MODELS=${BAKEOFF_MODELS}"
  fi
  if [[ -n "${BAKEOFF_SKIP_COMFY:-}" ]]; then
    echo "BAKEOFF_SKIP_COMFY=${BAKEOFF_SKIP_COMFY}"
  fi
  if [[ -n "${BAKEOFF_FORCE_RESTART:-}" ]]; then
    echo "BAKEOFF_FORCE_RESTART=${BAKEOFF_FORCE_RESTART}"
  fi
  if [[ -n "${LLAMA_SERVER_BIN:-}" ]]; then
    echo "LLAMA_SERVER_BIN=${LLAMA_SERVER_BIN}"
  fi
} >"$BAKEOFF_ROOT/.env.sku"

chmod +x "$BAKEOFF_ROOT/onstart.sh" "$BAKEOFF_ROOT/install_stack.sh"
cd "$BAKEOFF_ROOT"
mkdir -p results

# Tee to run.log and container logs (orchestrator polls vastai logs).
exec > >(tee -a "$BAKEOFF_ROOT/run.log") 2>&1

set +e
./onstart.sh
ONSTART_RC=$?
if [[ $ONSTART_RC -ne 0 ]]; then
  echo "BAKEOFF_DONE exit=${ONSTART_RC}"
  exit "$ONSTART_RC"
fi

python3 run_matrix.py
MATRIX_RC=$?
echo "$MATRIX_RC" > results/DONE

python3 upload_results.py || echo "WARN: upload_results failed"

echo "BAKEOFF_DONE exit=${MATRIX_RC}"
exit "$MATRIX_RC"
