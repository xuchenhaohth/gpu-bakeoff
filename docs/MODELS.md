# Models under test

## Gated licenses (accept before prefetch)

| Model | Hugging Face | License | Action |
|-------|--------------|---------|--------|
| MiniMax H3 | [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) | Open | Accept on HF |
| LTX-2.5 | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) | Open | Accept on HF |
| Ideogram 4 | [ideogram-ai/ideogram-4-nf4](https://huggingface.co/ideogram-ai/ideogram-4-nf4) | **Non-commercial** | Internal test only |
| FLUX.2-dev | [black-forest-labs/FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev) | Open | Accept on HF |
| Hunyuan 3 NF4 | [EricRollei/HunyuanImage-3-NF4-v2](https://huggingface.co/EricRollei/HunyuanImage-3-NF4-v2) | Open | Download |
| Qwen3.8-27B | [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | Apache 2.0 | Public |
| Qwen NVFP4 | [RadixArk/Qwen3.8-27B-NVFP4](https://huggingface.co/RadixArk/Qwen3.8-27B-NVFP4) | Apache 2.0 | Public |
| DeepSeek GGUF | [prometheusAIR/DeepSeek-V4-Flash-0731-GGUF](https://huggingface.co/prometheusAIR/DeepSeek-V4-Flash-0731-GGUF) | MIT | Public |

Set `HF_TOKEN` in `.env`. Remote prefetch uses `huggingface-cli login --token $HF_TOKEN`.

## Runtime stack (pinned for reproducibility)

| Component | Version target | Notes |
|-----------|----------------|-------|
| CUDA | ≥ 12.8 | Blackwell sm_120 / sm_121 |
| PyTorch | From `vastai/pytorch` tag | x86 instances |
| ComfyUI | Latest git @ run date | Image/video via `assets/workflows/` |
| vLLM | ≥ 0.27.x | Qwen + optional DeepSeek native |
| llama.cpp | server binary | DeepSeek GGUF |
| Python | 3.10+ | Remote `uv venv` in `onstart.sh` |

| Model | Workflow | Custom nodes |
|-------|----------|--------------|
| flux2_dev | `flux2_dev.json` | — |
| ideogram_4 | `ideogram_4.json` | — |
| hunyuan_image_3 | `hunyuan_image_3.json` | ComfyUI-HunyuanImage-3 |
| ltx_25 | `ltx_25.json` | ComfyUI-LTXVideo |
| minimax_h3 | `minimax_h3.json` | ComfyUI-LTXVideo |
| qwen38_27b | — (vLLM) | — |
| deepseek_v4_flash | — (llama.cpp GGUF) | — |

Record exact versions in `results/environment.json` after each run.

## Layer A checkpoints (shared quant)

See `config/models.yaml`. One precision per model across GPUs.

## Layer B (1× PRO 6000 only)

Higher precision re-runs: LTX BF16, Hunyuan INT8/BF16, FLUX FP16, Qwen BF16.

## DeepSeek rules

| SKU | Layer A | Layer B (optional) |
|-----|---------|-------------------|
| 5090 / 5090×2 | Fail-fast | — |
| 1× PRO 6000 | IQ2 GGUF llama.cpp | — |
| 2× PRO 6000 | Same IQ2 GGUF, layer split | Native vLLM FP8 |
| Spark | IQ2 GGUF | — |

Compare 1× vs 2× on **same GGUF**, not native vs quant.

## Ideogram 4 — boss disclaimer

Open weights are **non-commercial**. Matrix may show technical fit; production use requires a commercial deal with Ideogram.

## Expected fit (hypothesis — verify in CSV)

| Model | 5090 | 5090×2 | 1×6000 | 2×6000 | Spark |
|-------|------|--------|--------|--------|-------|
| MiniMax H3 | Quant tight | Quant | Quant | Quant/BF16 | Quant slow |
| LTX-2.5 | INT8 | INT8 | BF16 B | BF16 | Slow |
| Ideogram 4 | Yes | Yes | Yes | Yes | Yes |
| Hunyuan 3 | Offload | NF4 | INT8/BF16 | BF16 | NF4 |
| FLUX.2 | FP8 | FP8 | FP16 B | FP16 | FP16 slow |
| Qwen3.8 | NVFP4 | FP8 | BF16 B | BF16 | BF16 slow |
| DeepSeek | No | No | GGUF | GGUF/native | GGUF |

*B = Layer B run on 1×6000 only.*
