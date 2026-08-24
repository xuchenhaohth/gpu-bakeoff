#!/usr/bin/env bash
# Install ComfyUI, custom nodes, and optional inference servers on Vast instance.
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
BAKEOFF_ROOT="$(cd "$(dirname "$0")" && pwd)"

install_node() {
  local url=$1
  local name=$2
  local dest="$COMFY_DIR/custom_nodes/$name"
  if [[ -d "$dest/.git" ]]; then
    echo "  node exists: $name"
    return 0
  fi
  echo "  cloning $name"
  git clone --depth 1 "$url" "$dest" 2>/dev/null || echo "  WARN: failed to clone $name"
}

echo "== install_stack =="

if [[ ! -d "$COMFY_DIR/.git" ]]; then
  echo "Cloning ComfyUI -> $COMFY_DIR"
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
fi

if [[ -f "$COMFY_DIR/requirements.txt" ]]; then
  uv pip install -q -r "$COMFY_DIR/requirements.txt" || echo "WARN: ComfyUI requirements partial"
fi

mkdir -p "$COMFY_DIR/custom_nodes"
install_node "https://github.com/Lightricks/ComfyUI-LTXVideo.git" "ComfyUI-LTXVideo"
install_node "https://github.com/kijai/ComfyUI-HunyuanImage-3.git" "ComfyUI-HunyuanImage-3"

uv pip install -q vllm 2>/dev/null || echo "WARN: vllm install failed — LLM jobs may stub"

if ! command -v llama-server >/dev/null 2>&1; then
  uv pip install -q llama-cpp-python 2>/dev/null || echo "WARN: llama-cpp-python install failed"
fi

echo "Stack install complete (ComfyUI at $COMFY_DIR)"
