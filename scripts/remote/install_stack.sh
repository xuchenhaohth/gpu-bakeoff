#!/usr/bin/env bash
# Install ComfyUI, custom nodes, and optional inference servers on Vast instance.
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
BAKEOFF_ROOT="$(cd "$(dirname "$0")" && pwd)"
VLLM_TIMEOUT="${INSTALL_VLLM_TIMEOUT_SEC:-600}"
LLAMA_TIMEOUT="${INSTALL_LLAMA_TIMEOUT_SEC:-600}"

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

echo "== install_stack =="
progress install_stack

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

if [[ "$(uname -m)" == "aarch64" ]]; then
  progress skip_vllm_arm64
  echo "WARN: skipping vllm on aarch64 — Qwen LLM jobs may stub"
elif command -v vllm >/dev/null 2>&1; then
  echo "vllm already installed"
else
  progress pip_vllm
  if command -v timeout >/dev/null 2>&1; then
    timeout "$VLLM_TIMEOUT" uv pip install vllm || echo "WARN: vllm install failed — LLM jobs may stub"
  else
    uv pip install vllm || echo "WARN: vllm install failed — LLM jobs may stub"
  fi
fi

if command -v llama-server >/dev/null 2>&1; then
  echo "llama-server already installed"
else
  progress pip_llama_cpp
  if command -v timeout >/dev/null 2>&1; then
    timeout "$LLAMA_TIMEOUT" uv pip install llama-cpp-python || echo "WARN: llama-cpp-python install failed"
  else
    uv pip install llama-cpp-python || echo "WARN: llama-cpp-python install failed"
  fi
fi

progress install_stack_done
echo "Stack install complete (ComfyUI at $COMFY_DIR)"
