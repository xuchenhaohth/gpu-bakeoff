# Hugging Face access checklist

Complete **before** `02_run_bakeoff.py` (remote prefetch runs on each instance).

## Token

1. Create token at https://huggingface.co/settings/tokens (read access).
2. Set in `.env`: `HF_TOKEN=hf_...`

## Accept gated model licenses

Log in to Hugging Face and click **Agree** on each model page:

| Model | URL |
|-------|-----|
| MiniMax H3 | https://huggingface.co/MiniMaxAI/MiniMax-H3 |
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

SSH into the instance (not `vastai execute` — that API is not a shell on running VMs):

```bash
vastai ssh-url <INSTANCE_ID>    # prints ssh://root@host:port
ssh -p <port> -i ~/.ssh/id_ed25519 root@<host> huggingface-cli whoami
```

## Ideogram licence

Non-commercial open weights — **internal bake-off only**. Note in boss pack.
