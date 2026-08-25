#!/usr/bin/env bash
# Install ComfyUI, custom nodes, and optional inference servers on Vast instance.
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
BAKEOFF_ROOT="$(cd "$(dirname "$0")" && pwd)"
export BAKEOFF_ROOT
VLLM_TIMEOUT="${INSTALL_VLLM_TIMEOUT_SEC:-600}"
LLAMA_TIMEOUT="${INSTALL_LLAMA_TIMEOUT_SEC:-900}"
# Pinned llama.cpp ref for qwen3.5 / recent GGUF arch support (see ggerganov/llama.cpp tags)
LLAMA_CPP_GIT_REF="${LLAMA_CPP_GIT_REF:-b5216}"
LLAMA_BIN_DIR="$BAKEOFF_ROOT/bin"

progress() {
  python3 "$BAKEOFF_ROOT/progress.py" --phase install --message "$1"
}

install_node() {
  local url=$1
  local name=$2
  local slug=$3
  local dest="$COMFY_DIR/custom_nodes/$name"
  if [[ -d "$dest/.git" ]]; then
    echo "  node exists: $name"
    return 0
  fi
  progress "clone_${slug}"
  echo "  cloning $name"
  if git clone --depth 1 "$url" "$dest"; then
    return 0
  fi
  progress "clone_${slug}_failed"
  echo "  WARN: failed to clone $name"
  return 0
}

llama_server_bin() {
  if command -v llama-server >/dev/null 2>&1; then
    command -v llama-server
    return 0
  fi
  if [[ -x "$LLAMA_BIN_DIR/llama-server" ]]; then
    echo "$LLAMA_BIN_DIR/llama-server"
    return 0
  fi
  return 1
}

llama_supports_jinja() {
  local bin
  bin="$(llama_server_bin)" || return 1
  "$bin" --help 2>&1 | grep -q -- '--jinja'
}

needs_llama_cpp() {
  python3 - <<'PY'
import os, sys, yaml
from pathlib import Path
from model_spec import model_selected, resolve_model_spec

root = Path(os.environ.get("BAKEOFF_ROOT", "."))
cfg = yaml.safe_load((root / "config" / "models.yaml").read_text())
sku = os.environ.get("BAKEOFF_SKU", "unknown")
for key, spec in cfg.get("models", {}).items():
    if not model_selected(key):
        continue
    resolved = resolve_model_spec(spec, sku)
    if resolved.get("runtime") == "llama_cpp":
        sys.exit(0)
sys.exit(1)
PY
}

needs_vllm() {
  python3 - <<'PY'
import os, sys, yaml
from pathlib import Path
from model_spec import model_selected, resolve_model_spec

root = Path(os.environ.get("BAKEOFF_ROOT", "."))
cfg = yaml.safe_load((root / "config" / "models.yaml").read_text())
sku = os.environ.get("BAKEOFF_SKU", "unknown")
for key, spec in cfg.get("models", {}).items():
    if not model_selected(key):
        continue
    resolved = resolve_model_spec(spec, sku)
    if resolved.get("runtime") == "vllm":
        sys.exit(0)
sys.exit(1)
PY
}

install_llama_server() {
  if llama_server_bin >/dev/null 2>&1; then
    echo "llama-server already installed: $(llama_server_bin)"
    return 0
  fi

  progress pip_llama_cpp
  if command -v timeout >/dev/null 2>&1; then
    timeout "$LLAMA_TIMEOUT" uv pip install 'llama-cpp-python[server]' \
      || timeout "$LLAMA_TIMEOUT" uv pip install llama-cpp-python \
      || echo "WARN: llama-cpp-python install failed"
  else
    uv pip install 'llama-cpp-python[server]' \
      || uv pip install llama-cpp-python \
      || echo "WARN: llama-cpp-python install failed"
  fi

  if llama_server_bin >/dev/null 2>&1; then
    return 0
  fi

  if python3 -c "import llama_cpp" 2>/dev/null; then
    mkdir -p "$LLAMA_BIN_DIR"
    cat >"$LLAMA_BIN_DIR/llama-server" <<'EOF'
#!/usr/bin/env bash
exec python3 -m llama_cpp.server "$@"
EOF
    chmod +x "$LLAMA_BIN_DIR/llama-server"
    echo "llama-server wrapper -> python3 -m llama_cpp.server"
    return 0
  fi

  if [[ "$(uname -m)" == "aarch64" ]]; then
    progress build_llama_cpp
    echo "Building llama.cpp for aarch64 (ref ${LLAMA_CPP_GIT_REF})..."
    build_dir="$(mktemp -d)"
    if git clone https://github.com/ggerganov/llama.cpp.git "$build_dir/llama.cpp"; then
      (
        cd "$build_dir/llama.cpp"
        default_head="$(git rev-parse HEAD)"
        if ! git fetch --depth 1 origin "$LLAMA_CPP_GIT_REF" 2>/dev/null; then
          git fetch --depth 1 origin "tag/$LLAMA_CPP_GIT_REF" 2>/dev/null || true
        fi
        if ! git checkout "$LLAMA_CPP_GIT_REF" 2>/dev/null; then
          echo "ERROR: could not checkout llama.cpp ref ${LLAMA_CPP_GIT_REF}" >&2
          exit 1
        fi
        if [[ "$(git rev-parse HEAD)" == "$default_head" ]] && [[ "$LLAMA_CPP_GIT_REF" != "$default_head" ]]; then
          echo "ERROR: llama.cpp checkout did not change HEAD (ref ${LLAMA_CPP_GIT_REF} invalid?)" >&2
          exit 1
        fi
        if command -v cmake >/dev/null 2>&1; then
          cmake -B build -DGGML_CUDA=ON -DLLAMA_CURL=OFF
          cmake --build build --config Release -j "$(nproc 2>/dev/null || echo 4)"
          mkdir -p "$LLAMA_BIN_DIR"
          cp build/bin/llama-server "$LLAMA_BIN_DIR/llama-server"
          chmod +x "$LLAMA_BIN_DIR/llama-server"
          echo "Built llama-server -> $LLAMA_BIN_DIR/llama-server"
        else
          echo "ERROR: cmake missing — cannot build llama.cpp on aarch64"
          rm -rf "$build_dir"
          return 1
        fi
      )
    else
      echo "ERROR: failed to clone llama.cpp"
      rm -rf "$build_dir"
      return 1
    fi
    rm -rf "$build_dir"
  fi

  if llama_server_bin >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

write_llama_env() {
  local bin
  if ! bin="$(llama_server_bin)"; then
    return 1
  fi
  if ! "$bin" --version >/dev/null 2>&1; then
    echo "ERROR: llama-server --version failed for $bin"
    return 1
  fi
  touch "$BAKEOFF_ROOT/.env.sku"
  if grep -q '^LLAMA_SERVER_BIN=' "$BAKEOFF_ROOT/.env.sku" 2>/dev/null; then
    sed -i "s/^LLAMA_SERVER_BIN=.*/LLAMA_SERVER_BIN=$bin/" "$BAKEOFF_ROOT/.env.sku"
  else
    echo "LLAMA_SERVER_BIN=$bin" >> "$BAKEOFF_ROOT/.env.sku"
  fi
  export LLAMA_SERVER_BIN="$bin"
  return 0
}

verify_comfy_running() {
  python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from comfy_client import start_comfy
from comfy_api import server_up
start_comfy()
if not server_up():
    sys.exit(1)
PY
}

echo "== install_stack =="
progress install_stack

if [[ "${BAKEOFF_SKIP_COMFY:-}" != "1" ]]; then
  if [[ ! -d "$COMFY_DIR/.git" ]]; then
    progress clone_comfyui
    echo "Cloning ComfyUI -> $COMFY_DIR"
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
  fi

  if [[ -f "$COMFY_DIR/requirements.txt" ]]; then
    progress pip_comfyui
    uv pip install -r "$COMFY_DIR/requirements.txt" || echo "WARN: ComfyUI requirements partial"
  fi

  mkdir -p "$COMFY_DIR/custom_nodes"
  install_node "https://github.com/Lightricks/ComfyUI-LTXVideo.git" "ComfyUI-LTXVideo" "ltxvideo"
  install_node "https://github.com/kijai/ComfyUI-HunyuanImage-3.git" "ComfyUI-HunyuanImage-3" "hunyuan_image_3"

  progress verify_comfy
  if ! verify_comfy_running; then
    echo "ERROR: ComfyUI did not bind :8188 after install" >&2
    tail -n 20 "$BAKEOFF_ROOT/comfy.log" 2>/dev/null || true
    exit 1
  fi
else
  progress skip_comfy
  echo "Skipping ComfyUI (BAKEOFF_SKIP_COMFY=1)"
fi

if [[ "$(uname -m)" == "aarch64" ]]; then
  progress skip_vllm_arm64
  echo "WARN: skipping vllm on aarch64 — use llama_cpp GGUF path for LLM jobs"
elif command -v vllm >/dev/null 2>&1; then
  echo "vllm already installed"
else
  progress pip_vllm
  vllm_ok=0
  if command -v timeout >/dev/null 2>&1; then
    timeout "$VLLM_TIMEOUT" uv pip install vllm && vllm_ok=1 || true
  else
    uv pip install vllm && vllm_ok=1 || true
  fi
  if needs_vllm && [[ "$vllm_ok" -ne 1 ]] && ! command -v vllm >/dev/null 2>&1; then
    echo "ERROR: vllm required for scheduled vLLM models but install failed" >&2
    exit 1
  fi
  if [[ "$vllm_ok" -ne 1 ]]; then
    echo "WARN: vllm install failed — LLM jobs may fail"
  fi
fi

if needs_llama_cpp; then
  if ! install_llama_server; then
    echo "ERROR: llama-server required for scheduled llama_cpp models but install failed" >&2
    exit 1
  fi
  if ! write_llama_env; then
    echo "ERROR: llama-server binary failed version probe" >&2
    exit 1
  fi
  if ! llama_supports_jinja; then
    echo "ERROR: llama-server lacks --jinja (required for Qwen GGUF)" >&2
    exit 1
  fi
else
  install_llama_server || true
  write_llama_env || true
fi

progress install_stack_done
echo "Stack install complete (ComfyUI at $COMFY_DIR)"
