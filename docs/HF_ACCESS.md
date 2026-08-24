# Hugging Face access checklist

Complete **before** `04_push_and_run.py` (remote prefetch).

## Token

1. Create token at https://huggingface.co/settings/tokens (read access).
2. Set in `.env`: `HF_TOKEN=hf_...`

## Accept gated model licenses

Log in to Hugging Face and click **Agree** on each model page:

| Model | URL |
|-------|-----|
| MiniMax H3 | https://huggingface.co/MiniMaxAI/MiniMax-H3 |
| LTX-2.5 | https://huggingface.co/Lightricks/LTX-2.5 |
| Ideogram 4 NF4 | https://huggingface.co/ideogram-ai/ideogram-4-nf4 |
| FLUX.2-dev | https://huggingface.co/black-forest-labs/FLUX.2-dev |

Non-gated but required downloads:

- Qwen/Qwen3.8-27B
- RadixArk/Qwen3.8-27B-NVFP4
- EricRollei/HunyuanImage-3-NF4-v2
- prometheusAIR/DeepSeek-V4-Flash-0731-GGUF

## Verify locally

```bash
source .env  # or export HF_TOKEN
uv sync
uv run python -c "from huggingface_hub import HfApi; print(HfApi().whoami(token='$HF_TOKEN'))"
```

## Remote verify (after instance running)

```bash
vastai execute <INSTANCE_ID> "huggingface-cli whoami"
```

## Ideogram licence

Non-commercial open weights — **internal bake-off only**. Note in boss pack.
