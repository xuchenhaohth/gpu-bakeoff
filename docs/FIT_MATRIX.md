# Hardware × model fit matrix

> **Status:** Template — fill after `results/matrix.csv` is generated.

## Legend

| Status | Meaning |
|--------|---------|
| **Native** | BF16/FP16 or vendor FP8; usable quality |
| **Quantized** | INT8/FP8/NVFP4/GGUF only |
| **Offload** | Needs large host RAM (record GB in CSV) |
| **No** | OOM / fail-fast |
| **Slow** | Runs but above staff wait threshold |

## Matrix (Layer A — shared quant)

<!-- AUTO_MATRIX_START -->
| Model | _fill after run_ |
|-------|---|
| _example_ | _TBD_ |
<!-- AUTO_MATRIX_END -->

## Staff wait time (from CSV)

| Model | Spark | 5090 | 5090×2 | 1×6000 | 2×6000 |
|-------|-------|------|--------|--------|--------|
| _example image_ | — | ~Xs/image | — | — | — |
| _example video_ | — | ~Xs per 1s clip | — | — | — |
| _example LLM_ | — | ~X tok/s decode | — | — | — |

## Peak host RAM (GB)

| Model | 5090 | Notes |
|-------|------|-------|
| Hunyuan 3.0 | _TBD_ | If >128 GB, 5090 box quote must include RAM upgrade |

## How to refresh

```bash
uv run python scripts/remote/report.py --csv results/matrix.csv --update-docs
```

Or paste summary tables from `results/report.html`.
