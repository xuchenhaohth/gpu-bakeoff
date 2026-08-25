# Pinned inference stack (record exact versions in results/environment.json after run)

| Component | Target | x86 (5090 / PRO 6000) | ARM (GB10 Spark) |
|-----------|--------|-------------------------|------------------|
| Base image | Vast template | `vastai/pytorch:@vastai-automatic-tag` | `vastai/pytorch:@vastai-automatic-tag` |
| CUDA | Blackwell | ≥ 12.8 | ≥ 12.8 |
| PyTorch | From base image | sm_120 | sm_121 |
| ComfyUI | git HEAD @ run date | `/workspace/ComfyUI` via `install_stack.sh` | ARM build if available |
| vLLM | ≥ 0.27.x | Qwen NVFP4; `--tensor-parallel-size 2` on 2-GPU SKUs | **Skipped on aarch64** (no reliable wheel) |
| llama.cpp | server binary | DeepSeek IQ2 GGUF; layer split on 2-GPU SKUs | Same (best-effort pip) |
| Python | 3.10+ | remote `uv venv` in `onstart.sh` | remote `uv venv` |

## Remote install (`scripts/remote/install_stack.sh`)

Called from `onstart.sh` on each Vast instance. Each long step emits `[progress] install <message>` (visible in `vastai logs` and the local poller):

1. Clone ComfyUI → `/workspace/ComfyUI` (`clone_comfyui`)
2. `uv pip install -r ComfyUI/requirements.txt` (`pip_comfyui`)
3. Clone custom nodes (`clone_ltxvideo`, `clone_hunyuan_image_3`, or `clone_*_failed`):
   - ComfyUI-LTXVideo (MiniMax H3)
   - ComfyUI-HunyuanImage-3 (Hunyuan Image 3)
4. `uv pip install vllm` (`pip_vllm`) — **skipped on aarch64** (`skip_vllm_arm64`); timeout `INSTALL_VLLM_TIMEOUT_SEC` (default 600s) on x86
5. `uv pip install llama-cpp-python` (`pip_llama_cpp`) for `llama-server` (DeepSeek GGUF)
6. `install_stack_done`

## ComfyUI workflows

Model-specific workflow JSON lives in `scripts/remote/assets/workflows/{model_key}.json`. The harness injects prompt, seed, and resolution at runtime via `workflow_loader.py` and submits through `comfy_api.py`.

Checkpoint filenames in workflows must match files present in ComfyUI `models/checkpoints/` after prefetch.

## Version capture

`onstart.sh` writes `results/environment.json` with GPU info, vLLM/llama versions, and `uv pip freeze`. After pull, append manually if needed:

```bash
vllm --version >> results/environment.json 2>/dev/null || true
```
