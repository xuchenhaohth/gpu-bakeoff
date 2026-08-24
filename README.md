# GPU bake-off (Harry the Hirer)

24-hour **Vast.ai** evidence run for a boss-facing hardware × model fit matrix. This folder does **not** recommend a purchase until a **Vast GPU run** produces `results/matrix.csv` — local dry-run output is pipeline validation only, not purchase evidence.

> **Harness status:** Remote instances install ComfyUI, vLLM, and llama.cpp via `install_stack.sh`. Without a live GPU, `dry_run_local.py` records `Stub` rows for LLM jobs and GPU-warmup stubs for image/video.

## Prerequisites

1. [Vast.ai account](https://cloud.vast.ai/) with **≥ US$50** credit (plan assumes ~US$80–150 burn).
2. API key: [console.vast.ai/manage-keys](https://console.vast.ai/manage-keys/)
3. Hugging Face token with **gated licenses accepted** for LTX-2.5, Ideogram 4, MiniMax H3, FLUX.2-dev.
4. [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
5. `vastai` CLI installed (see below).
6. SSH key at `~/.ssh/id_ed25519.pub` (or ed25519 equivalent).

## One-time setup

```bash
cd gpu-bakeoff
cp .env.example .env
# Edit .env — set VAST_API_KEY and HF_TOKEN

# Install Vast CLI (macOS/Linux)
./scripts/install_vast_cli.sh
# or: curl -fsSL https://vast.ai/install.sh | bash

vastai set api-key "$VAST_API_KEY"
vastai create ssh-key ~/.ssh/id_ed25519.pub

uv sync   # local orchestrator + dev tools
./scripts/00_check_env.sh

# Validate CSV/report pipeline without Vast billing
uv run python scripts/dry_run_local.py

# Lint, typecheck, and smoke test
./scripts/check.sh
```

## 24-hour runbook

| Hour | Step | Command |
|------|------|---------|
| 0–1 | Check env | `./scripts/00_check_env.sh` |
| 0–1 | Discover offers | `uv run python scripts/01_search_offers.py` |
| 1 | Launch 5 instances | `uv run python scripts/02_launch.py` |
| 1–2 | Wait for SSH | `uv run python scripts/03_wait_running.py` |
| 2–6 | Prefetch + Layer A/B | `uv run python scripts/04_push_and_run.py` |
| 6–7 | Pull results | `uv run python scripts/05_pull_results.py` |
| 7 | Destroy (stop billing) | `uv run python scripts/06_destroy.py` |
| 7–8 | Boss pack | `uv run python scripts/fill_boss_pack.py` then review `docs/BOSS_PACK.md` |

**Full pipeline (interactive):** `./scripts/run_all.sh` — includes destroy trap on Ctrl+C.

**Critical:** Run `06_destroy.py` even if the matrix failed partway — storage charges continue until destroy.

## Outputs

| Path | Description |
|------|-------------|
| `results/matrix.csv` | One row per gpu × model × layer × prompt (from Vast pull) |
| `results/report.html` | Gallery + summary tables |
| `results/artifacts/` | PNG/MP4 samples (gitignored bulk) |
| `docs/FIT_MATRIX.md` | Human-readable matrix (auto-updated by pull step) |
| `docs/BOSS_PACK.md` | One-pager for management |

Dry-run writes to `scripts/remote/results/` only (cleaned up automatically).

## SKUs under test

| SKU | Maps to AU tier |
|-----|-----------------|
| RTX 5090 ×1 | Tier 1b desk workstation |
| RTX 5090 ×2 | Evidence only (not 64 GB VRAM) |
| RTX PRO 6000 ×1 | Tier 2 business workstation |
| RTX PRO 6000 ×2 | Tier 3 capacity |
| DGX Spark GB10 | Tier 1 low-power (ARM) |

## Layer A vs B

- **Layer A:** Same quantized checkpoint on every GPU that can load it (fair speed ladder).
- **Layer B:** Higher precision on **1× PRO 6000** (image/video/LLM) and **native DeepSeek vLLM on 2× PRO 6000**.

DeepSeek: IQ2 GGUF on 96 GB / 192 GB / Spark; fail-fast on 5090; optional native vLLM on 2× PRO 6000.

## Support

- Vast ops: [docs/VAST.md](docs/VAST.md)
- Models & licenses: [docs/MODELS.md](docs/MODELS.md)
- HF gated access: [docs/HF_ACCESS.md](docs/HF_ACCESS.md)
- Stack versions: [docs/STACK.md](docs/STACK.md)
- AU purchase quotes: [docs/AU_QUOTES.md](docs/AU_QUOTES.md)
