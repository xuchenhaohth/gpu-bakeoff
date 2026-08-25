# Documentation index

## Procurement (business / PO)

| Doc | Audience | Notes |
|-----|----------|-------|
| [procurement/AU_QUOTES.md](procurement/AU_QUOTES.md) | IT + management | Source of truth for AU retailer quotes |
| [procurement/CONFLUENCE.md](procurement/CONFLUENCE.md) | Stakeholders | Published Confluence page + manual sync steps |
| [procurement/BOSS_PACK.md](procurement/BOSS_PACK.md) | Management | Draft one-pager; filled after bake-off |

## Bake-off operations (engineering)

| Doc | Purpose |
|-----|---------|
| [VAST.md](VAST.md) | Vast.ai instance lifecycle, transport, troubleshooting |
| [MODELS.md](MODELS.md) | Models under test and licences |
| [HF_ACCESS.md](HF_ACCESS.md) | Hugging Face gated model access |
| [STACK.md](STACK.md) | ComfyUI / vLLM / llama.cpp versions on instances |
| [FIT_MATRIX.md](FIT_MATRIX.md) | Human-readable fit matrix (auto-updated from results) |

Pull HF results without Vast: `uv run python scripts/03_pull_hf_results.py`
