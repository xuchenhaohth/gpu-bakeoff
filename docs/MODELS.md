# Models under test

Six models, Layer A only (shared quant across SKUs).

## Gated licenses (accept before prefetch)

| Model | Hugging Face | License | Action |
|-------|--------------|---------|--------|
| MiniMax H3 | [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) | Open | Accept on HF |
| Ideogram 4 | [ideogram-ai/ideogram-4-nf4](https://huggingface.co/ideogram-ai/ideogram-4-nf4) | **Non-commercial** | Internal test only |
| FLUX.2-dev | [black-forest-labs/FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev) | Open | Accept on HF |
| Hunyuan 3 NF4 | [EricRollei/HunyuanImage-3-NF4-v2](https://huggingface.co/EricRollei/HunyuanImage-3-NF4-v2) | Open | Download |
| Qwen3.8-27B | [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | Apache 2.0 | Public |
| Qwen NVFP4 | [RadixArk/Qwen3.8-27B-NVFP4](https://huggingface.co/RadixArk/Qwen3.8-27B-NVFP4) | Apache 2.0 | Public |
| DeepSeek GGUF | [prometheusAIR/DeepSeek-V4-Flash-0731-GGUF](https://huggingface.co/prometheusAIR/DeepSeek-V4-Flash-0731-GGUF) | MIT | Public |

Set `HF_TOKEN` in `.env`. On the VM, `load_hf_env.sh` sources `.env.hf` (SSH push) or Docker `-e`; `onstart.sh` runs `python3 hf_auth.py login` before prefetch.

## Runtime stack (pinned for reproducibility)

| Component | Version target | Notes |
|-----------|----------------|-------|
| CUDA | ≥ 12.8 | Blackwell sm_120 / sm_121 |
| PyTorch | From `vastai/pytorch` tag | x86 instances |
| ComfyUI | Latest git @ run date | Image/video via `assets/workflows/` |
| vLLM | ≥ 0.27.x | Qwen NVFP4; `--tensor-parallel-size 2` on 2-GPU SKUs |
| llama.cpp | server binary | DeepSeek GGUF; layer split on 2-GPU SKUs |
| Python | 3.10+ | Remote `uv venv` in `onstart.sh` |

| Model | Workflow | Custom nodes |
|-------|----------|--------------|
| flux2_dev | `flux2_dev.json` | — |
| ideogram_4 | `ideogram_4.json` | — |
| hunyuan_image_3 | `hunyuan_image_3.json` | ComfyUI-HunyuanImage-3 |
| minimax_h3 | `minimax_h3.json` | ComfyUI-LTXVideo |
| qwen38_27b | — (vLLM on x86; GGUF llama-server on Spark) | — |
| deepseek_v4_flash | — (llama.cpp GGUF) | — |

ComfyUI image/video jobs use GPU 0 only. LLM jobs use tensor-parallel on `rtx5090_2x` and `pro6000_2x`.

Record exact versions in `results/environment.json` after each run.

## Layer A checkpoints (shared quant)

See `config/models.yaml`. One precision per model across GPUs.

## DeepSeek rules

| SKU | Behavior |
|-----|----------|
| 5090 / 5090×2 | **Fail-fast skip** — CSV rows only, no inference |
| 1× PRO 6000 | IQ2 GGUF llama.cpp |
| 2× PRO 6000 | IQ2 GGUF llama.cpp with layer tensor-split |
| Spark | IQ2 GGUF llama.cpp |

## Ideogram 4 — boss disclaimer

Open weights are **non-commercial**. Matrix may show technical fit; production use requires a commercial deal with Ideogram.

## Expected fit (hypothesis — verify in CSV)

| Model | 5090 | 5090×2 | 1×6000 | 2×6000 | Spark |
|-------|------|--------|--------|--------|-------|
| MiniMax H3 | Quant tight | Quant | Quant | Quant | Quant slow |
| Ideogram 4 | Yes | Yes | Yes | Yes | Yes |
| Hunyuan 3 | Offload | NF4 | NF4 | NF4 | NF4 |
| FLUX.2 | FP8 | FP8 | FP8 | FP8 | FP8 slow |
| Qwen3.8 | NVFP4 | NVFP4 + TP | NVFP4 | NVFP4 + TP | Q4_K_M GGUF (llama-server) |
| DeepSeek | No (skip) | No (skip) | GGUF | GGUF + TP | GGUF |
