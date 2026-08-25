#!/usr/bin/env bash
# Remote bootstrap on Vast instance — run from /workspace/bakeoff
set -euo pipefail
cd "$(dirname "$0")"
BAKEOFF_ROOT="$(pwd)"

mkdir -p results
python3 progress.py --phase onstart --message bootstrap

# shellcheck disable=SC1091
source "$BAKEOFF_ROOT/load_hf_env.sh"

echo "== bakeoff onstart =="
nvidia-smi || { echo "No GPU"; exit 1; }

export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null 2>&1; then
  python3 progress.py --phase onstart --message apt_packages
  apt-get update -qq
  apt-get install -y -qq git curl wget python3 procps build-essential >/dev/null 2>&1 || true
fi

export PATH="${HOME}/.local/bin:${PATH}"
if ! command -v uv >/dev/null 2>&1; then
  python3 progress.py --phase onstart --message uv_install
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1091
  source "${HOME}/.local/bin/env" 2>/dev/null || true
  export PATH="${HOME}/.local/bin:${PATH}"
fi

uv venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python3 progress.py --phase onstart --message pip_base
uv pip install -q pyyaml requests huggingface_hub psutil

python3 progress.py --phase onstart --message setup_venv

if [[ -f "$BAKEOFF_ROOT/install_stack.sh" ]]; then
  bash "$BAKEOFF_ROOT/install_stack.sh" || echo "WARN: install_stack partial failure"
fi

if [[ -n "${HF_TOKEN:-}" ]]; then
  python3 progress.py --phase onstart --message hf_login
  python3 hf_auth.py login || { echo "ERROR: huggingface_hub login failed" >&2; exit 1; }
fi

mkdir -p results artifacts config assets
python3 - <<'PY'
import json, subprocess, platform
from datetime import datetime, timezone
env = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "platform": platform.platform(),
    "python": platform.python_version(),
    "sku": __import__("os").environ.get("BAKEOFF_SKU", "unknown"),
}
try:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,power.limit", "--format=csv,noheader"],
        text=True,
    )
    env["gpus"] = [l.strip() for l in out.strip().split("\n") if l.strip()]
except Exception as e:
    env["gpu_error"] = str(e)
for cmd, key in [
    (["vllm", "--version"], "vllm_version"),
    (["llama-server", "--version"], "llama_server_version"),
]:
    try:
        env[key] = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        pass
try:
    env["pip_freeze"] = subprocess.check_output(["uv", "pip", "freeze"], text=True).strip().split("\n")
except Exception:
    pass
open("results/environment.json", "w").write(json.dumps(env, indent=2))
print("Wrote results/environment.json")
PY

echo "== onstart complete =="
python3 prefetch_models.py || echo "WARN: prefetch partial failure — check HF_TOKEN and licenses"
