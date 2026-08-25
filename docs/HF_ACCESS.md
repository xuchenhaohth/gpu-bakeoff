# Hugging Face access checklist

Complete **before** `02_run_bakeoff.py` (remote prefetch runs on each instance).

## Token

1. Create token at https://huggingface.co/settings/tokens with **write** access (read-only tokens cannot create the results dataset or upload artifacts).
2. Set in `.env`: `HF_TOKEN=hf_...`
3. Optional: `HF_RESULTS_REPO=your-username/gpu-bakeoff-results` (default: `{hf_user}/gpu-bakeoff-results`)

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

## Pull results from Hugging Face (no GPU)

Team-key runs upload to `{hf_user}/gpu-bakeoff-results` during the matrix. To fetch without launching instances:

```bash
uv run python scripts/03_pull_hf_results.py              # all SKUs on HF
uv run python scripts/03_pull_hf_results.py --sku rtx5090_1x
```

Requires a **write-capable** `HF_TOKEN` for uploads; read access is enough for pull once the dataset exists.

## Verify locally

```bash
source .env
uv sync
PYTHONPATH=scripts uv run python -c "from lib.vast import load_dotenv, hf_token; from huggingface_hub import HfApi; load_dotenv(); print(HfApi().whoami(token=hf_token()))"
PYTHONPATH=scripts uv run python -c "from lib.vast import load_dotenv; from lib.hf_results import ensure_hf_results_repo; load_dotenv(); print('results repo:', ensure_hf_results_repo())"
```

## Remote verify (after harness start)

SSH into the instance (not `vastai execute` — that API is not a shell on running VMs).
SSH sessions do **not** inherit Docker `-e HF_TOKEN`. The SSH harness push writes `/workspace/bakeoff/.env.hf`; `load_hf_env.sh` sources it (or falls back to `/proc/1/environ` on onstart transport).

```bash
vastai ssh-url <INSTANCE_ID>    # prints ssh://root@host:port
ssh -p <port> -i ~/.ssh/id_ed25519 root@<host>
source /workspace/bakeoff/load_hf_env.sh   # or: source /workspace/bakeoff/.env.hf
echo "${HF_TOKEN:+HF_TOKEN set}"
python3 /workspace/bakeoff/hf_auth.py login && huggingface-cli whoami
```

`run.log` should not contain `unauthenticated requests to the HF Hub` after a successful start.

## Ideogram licence

Non-commercial open weights — **internal bake-off only**. Note in boss pack.
