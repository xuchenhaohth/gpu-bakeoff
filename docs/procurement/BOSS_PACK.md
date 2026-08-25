# Boss pack — in-house LLM / media hardware (Harry the Hirer)

> **Draft** — complete after `results/report.html` is generated. Do not send until FIT_MATRIX is filled.

**Prepared by:** IT  
**Date:** _TBD_  
**Evidence:** Serial Vast.ai rental bake-off (`gpu-bakeoff/results/`)

---

## Executive summary (3 sentences)

_TBD: Under our budget options, which models run locally for video/image generation and coding agents, and which tier is the minimum viable purchase._

---

## What we tested

Six open-weight models across five GPU configurations matching our shopping list:

- MiniMax H3 (video)
- Ideogram 4, Hunyuan Image 3.0, FLUX.2-dev (image)
- Qwen3.8-27B, DeepSeek-V4-Flash (agents)

Same prompts and Layer A quantization for fair comparison. LLM jobs use tensor-parallel on 2-GPU SKUs; ComfyUI uses one GPU.

---

## Three purchase tiers (Australia, inc GST)

| Tier | Machine | Indicative price | Best for |
|------|---------|------------------|----------|
| **1** | DGX Spark / GX10 (128 GB unified) | A$8.5k–11k | Low power, large model **fit**; slower media |
| **1b** | RTX 5090 workstation (32 GB) | A$10k–13k | Fast desk AI; tight on largest video models |
| **2** | 1× RTX PRO 6000 (96 GB ECC) | A$26k–33k | **Business workstation** — media + Qwen native |
| **3** | 2× RTX PRO 6000 (192 GB) | A$50k–70k | **DeepSeek native** + headroom |

See [AU_QUOTES.md](AU_QUOTES.md) for retailer links and warranty. Stakeholder-facing copy: [CONFLUENCE.md](CONFLUENCE.md).

---

## Support matrix (Layer A)

_Paste from FIT_MATRIX.md or report.html_

| Model | Spark | 5090 | 2×5090 | 1×6000 | 2×6000 |
|-------|-------|------|--------|--------|--------|
| _fill_ | | | | | |

**Legend:** Native / Quantized / Offload (+ RAM GB) / No / Slow

---

## Key findings (bullets)

_TBD after run — examples:_

- DeepSeek **does not fit** on 5090; Tier 3 or cloud API only for native quality.
- Hunyuan on 5090 required **_X_ GB host RAM** — hidden cost if we only buy the GPU.
- Spark runs models but video wait time **_X_×** longer than PRO 6000.
- Ideogram 4 works technically; **non-commercial** licence — not production generator.
- 2×5090 is **not** 64 GB VRAM — do not purchase for capacity.

---

## Desk vs shared IT

| Usage | Recommendation |
|-------|----------------|
| 1–2 staff at a desk | Tier 1 Spark or Tier 1b 5090 acceptable |
| Shared server for multiple staff | Tier 2+ RTX PRO 6000 (ECC, 3 yr warranty) |

---

## Rental cost of this test

_Vast.ai on-demand, ~US$80–150 for serial per-SKU run — not included in hardware budget._

---

## Recommended next step

_TBD: e.g. “Request quote from Scorptec for Tier 2 workstation” or “Pilot Tier 1 Spark for agent dev, Tier 2 for media team.”_

---

## Appendix

- Full CSV: `results/matrix.csv`
- Sample outputs: `results/{sku}/artifacts/` (images, video, LLM `.txt`)
- Methodology: [README.md](../../README.md)
