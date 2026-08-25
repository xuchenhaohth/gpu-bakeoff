# Australian purchase quotes (live-linked)

> **Confluence (stakeholders):** [Australian AI hardware purchase quotes](https://harrythehirer.atlassian.net/wiki/spaces/TT/pages/679542785/Australian+AI+hardware+purchase+quotes)

> **Re-quote live** before the boss pack goes out. Prices inc GST unless noted. Stock changes daily.

**Last verified:** 2026-08-25. **Verify at retailer checkout.** Table prices were checked against the linked product page where the site allows automated fetch (Core Electronics, PLE, Landmark, MSY HTML, Mediaform BCData). Scorptec and Mwave block bots — load those listings in a browser before PO.

> **Mediaform displays ex-GST on the product page** (e.g. A$8,180.91 + GST = A$8,999). The inc-GST figure in this table is correct; clicking through shows ex-GST unless you toggle GST.

> **RTX PRO 6000 validity:** NVIDIA raised RTX PRO 6000 MSRP to **US$16,000** around 12 Aug 2026 (GDDR7 shortage). Current AU listings at A$22,499–25,100 inc GST appear to be pre-increase stock — re-quote before PO.

## Tier 1 — desk / low power

### DGX Spark / GB10 appliance (complete system)

| Retailer | Product | Price (inc GST) | Stock / lead time | Power (W) | Warranty |
|----------|---------|-----------------|-------------------|-----------|----------|
| Mediaform | ASUS Ascent GX10 1TB (GX10-GG0013BN) | A$8,999 ([listing](https://www.mediaform.com.au/asus-ascent-gx10-ai-supercomputer-mini-pc-powered-by-nvidia-gb10/)) | OOS — call for ETA | 140 SoC TDP; 240 peak system | Check listing |
| Core Electronics | NVIDIA DGX Blackwell Spark FE, 4TB (CE10915) | A$8,999 ([listing](https://core-electronics.com.au/nvidia-blackwell-spark.html)) | Lead time — dispatch ~4–7 Sep 2026 | 140 typical; 273 GB/s mem BW | Check listing |
| Mediaform | MSI EdgeXpert GB10 **1TB** (EdgeXpert-34SAU) | A$8,999 ([listing](https://www.mediaform.com.au/msi-edgexpert-ai-supercomputer-mini-pc-powered-by-nvidia-gb10/)) | OOS — call for ETA | 140 SoC TDP; 240 peak system | 3 yr OS ADR |
| Mwave | ASUS Ascent GX10 1TB (GX10-GG0013BN) | A$9,631.95 ([listing](https://www.mwave.com.au/products/asus-ascent-gx10-ai-nvdia-gb10-128gb-ram-1tb-supercomputer-mini-pc-nvidia-dgx-os-ac92418)) | Verify at checkout | 140 SoC TDP; 240 peak system | 12 mo |
| Scorptec | ASUS Ascent GX10 1TB (GX10-GG0013BN) | A$10,999 ([listing](https://www.scorptec.com.au/product/branded-systems/nuc-mini-pc/120181-gx10-gg0013bn)) | Often sold out — verify checkout | 140 SoC TDP; 240 peak system | 1 yr |
| PLE | ASUS Ascent GX10 4TB (GX10-GG0032BN) — storage variant | A$13,999 ([listing](https://www.ple.com.au/products/686787/asus-ascent-gx10-ai-gb10-dgx-spark-supercomputer-mini-pc-4tb128gb)) | In stock at supplier (Sydney) | 140 SoC TDP; 240 peak system | 1 yr RTB |
| Dell | Pro Max with GB10 (FCM1253), 128 GB / 4TB | from A$12,238 ([listing](https://www.dell.com/en-au/shop/dell-desktop-computers/dell-pro-max-with-gb10/spd/dell-pro-max-fcm1253-micro/cto002_fcm1253_au)) — sample config A$17,413 | Extended delivery | 280 W Type-C PSU | 12 mo onsite (upgradeable) |

**Notes:** Complete mini PC, **128 GB unified memory**, ARM, ACL applies. **273 GB/s** memory bandwidth is the main throughput limit for large MoE models (e.g. DeepSeek-V4-Flash IQ2 loads here but runs slowly). Core Electronics is the NVIDIA DGX Spark FE (4TB), not the ASUS GX10 1TB. PLE 4TB row is a storage variant, not the cheap Tier 1 entry. **1 TB GB10 SKUs use TCG Pyrite SSDs, not Opal SED**; 4 TB PCIe 5.0 (PLE GX10 4TB) is Opal — matters only if self-encryption is cited as a control. Mwave previously appeared as A$6,999 in stale index data; linked page shows A$9,631.95. Mediaform lists two URLs for EdgeXpert-34SAU; both resolve to **1TB** at the same price (not 4TB). ASUS Ascent GX10 is an OEM GB10 appliance (same Grace Blackwell superchip family as DGX Spark).

## Tier 1b — desk / fast 32 GB

### RTX 5090 32 GB (GPU card only)

| Retailer | Example SKU | Price (inc GST) | Stock / lead time | Power (W) | Warranty |
|----------|-------------|-----------------|-------------------|-----------|----------|
| PCCG | ASUS TUF RTX 5090 (TUF-RTX5090-32G-GAMING) | A$6,799 ([listing](https://www.pccasegear.com/products/68108/asus-geforce-rtx-5090-tuf-gaming-gddr7-32gb)) | OOS | ~575 card; 1000 W+ PSU | Check listing |
| PLE | ASUS TUF RTX 5090 (TUF-RTX5090-32G-GAMING) | A$6,999 ([listing](https://www.ple.com.au/products/672344/asus-geforce-rtx-5090-tuf-gaming-32gb-gddr7)) | Not orderable online (limit 1/household) | ~575 card; 1000 W+ PSU | 3 yr RTB |
| Scorptec | Palit RTX 5090 GameRock OC (NE75090S19R5-GB2020G) | A$7,199 ([listing](https://www.scorptec.com.au/product/graphics-cards/nvidia/121949-ne75090s19r5-gb2020g)) | Verify at checkout | ~575 card; 1000 W+ PSU | 3 yr |
| MSY | ASUS TUF RTX 5090 OC (TUF-RTX5090-O32G-GAMING) | A$7,499 ([listing](https://www.msy.com.au/product/asus-tuf-geforce-rtx-5090-oc-32g-gaming-graphics-card-tuf-rtx5090-o32g-gaming-81416)) | Verify at checkout | ~575 card; 1000 W+ PSU | 3 yr |
| Scorptec | ASUS TUF RTX 5090 non-OC (TUF-RTX5090-32G-GAMING) | A$7,499 ([listing](https://www.scorptec.com.au/product/graphics-cards/nvidia/116067-tuf-rtx5090-32g-gaming)) | Top-of-market / often OOS | ~575 card; 1000 W+ PSU | 3 yr |

**Workstation build (estimate):** add ~A$3,000–5,000 (CPU, 128 GB RAM, PSU 1000 W+, NVMe) to a 5090 card → **~A$10,000–13,000** all-in. Example: [PLE TUF A$6,999](https://www.ple.com.au/products/672344/asus-geforce-rtx-5090-tuf-gaming-32gb-gddr7) + ~A$3,500 platform ≈ A$10,500.

**Desk vs shared:** GeForce is appropriate for **1–2 desk users**. Not recommended as shared IT inference server (licence + no ECC).

## Tier 2 — business workstation

### RTX PRO 6000 Blackwell 96 GB (GPU card)

| Retailer | SKU | Price (inc GST) | Stock / lead time | Power (W) | Warranty |
|----------|-----|-----------------|-------------------|-----------|----------|
| Landmark | 900-5G144-2500-000 (Workstation Edition) | A$22,499 ([listing](https://www.lmc.com.au/nvidia-rtx-pro-6000-blackwell-workstation-900-5g144-2500-000)) | Back-order | 600 W axial WE | Check listing |
| Scorptec | 900-5G144-2500-000 | A$24,999 ([listing](https://www.scorptec.com.au/product/graphics-cards/workstation/118886-900-5g144-2500-000)) | Verify at checkout | 600 W WE / 300 W Max-Q same $ | 3 yr |
| MSY | 900-5G144-2500-000 (Workstation Edition) | A$25,100 ([listing](https://www.msy.com.au/product/nvidia-rtx-pro-6000-blackwell-edition-96gb-workstation-graphics-card-900-5g144-2500-000-86216)) | In stock | 600 W | 3 yr |

**Workstation build (estimate):** Threadripper PRO / Xeon W, 256 GB ECC RAM, 1200 W+ PSU → **~A$30,000–38,000** all-in. Based on [Landmark PRO 6000 A$22,499](https://www.lmc.com.au/nvidia-rtx-pro-6000-blackwell-workstation-900-5g144-2500-000) + ~A$7,500–15,500 platform (TR PRO CPU + 256 GB ECC alone exceed A$3,500).

**Shared IT:** ECC, 3 yr NVIDIA workstation warranty, MIG optional. For **cupboard / closed IT use, specify PRO 6000 Max-Q (300 W blower)** — not the 600 W axial Workstation Edition. Scorptec lists Max-Q at the same A$24,999; PO must name SKU **900-5G144-2500-000** and form factor.

## Tier 3 — capacity

### 2× RTX PRO 6000

| Item | Estimate (inc GST) |
|------|-------------------|
| 2× PRO 6000 cards | ~A$45,000–50,200 (2× [Landmark A$22,499](https://www.lmc.com.au/nvidia-rtx-pro-6000-blackwell-workstation-900-5g144-2500-000) – 2× [MSY A$25,100](https://www.msy.com.au/product/nvidia-rtx-pro-6000-blackwell-edition-96gb-workstation-graphics-card-900-5g144-2500-000-86216)) |
| Dual-GPU platform (EPYC/TR Pro, 256 GB+ RAM, **2000 W** PSU, NVMe 2 TB) | ~A$8,000–15,000 (estimate) |
| **Total** | **~A$53,000–70,000** (estimate) |

**DeepSeek-V4-Flash-0731 at IQ2 (~91 GB, Unsloth UD-IQ2):** loads on **Tier 1** 128 GB unified memory with ~30 GB headroom, but **273 GB/s bandwidth** makes throughput poor for a 284B MoE. **1× 96 GB PRO 6000** fits ~90.9 GB weights but leaves ~5 GB for KV cache (trivial context only). **2× 96 GB** gives comfortable room for weights plus long context via **layer-split under llama.cpp** (not tensor-parallel). Budget **~10 GB extra** for DSpark speculative drafter (unrelated to DGX Spark). Tier 3 is the practical choice for usable DeepSeek context and bandwidth, not because Tier 1 cannot fit the weights.

Dual-GPU PSU: **2000 W** recommended (2× ~600 W Blackwell + EPYC transients); confirm GPO circuit capacity.

## Integrators (full workstations + on-site warranty)

- [Leader Computers](https://partner.leadersystems.com.au/contactusfordeler.html) (Leader Computers Pty Ltd trades as **Leader Systems**) — trade-only distributor; email [sales@leadersystems.com.au](mailto:sales@leadersystems.com.au) or **1300 453 233** for reseller quote (partner page typo: 1300 453 323). Confirm they stock DGX Spark / PRO 6000 before naming as channel — trade distributor ≠ authorised NVIDIA partner.
- [Dell Pro Max workstations](https://www.dell.com/en-au/shop/desktop-computers/scr/desktops/appref=precision-product-line) — request RTX PRO 6000 or GB10 configuration quote (Precision branding retired).
- [HP Z workstations](https://www.hp.com/au-en/workstations/desktop-workstation-pc.html) — request RTX PRO 6000 quote (Z8 Fury quotes Max-Q for thermally constrained installs).
- Local AV/IT integrators for Harry the Hirer

## Quote checklist for PO

- [ ] Retailer name + SKU (PRO 6000: Workstation vs Max-Q form factor)
- [ ] Price inc GST (Mediaform: confirm inc-GST total, not ex-GST page figure)
- [ ] In stock / lead time (see table column)
- [ ] Warranty years + RMA path (store vs manufacturer)
- [ ] Power draw (W) for facilities (see table column; dual-GPU: 2000 W PSU + circuit)
- [ ] Desk vs shared IT caption (Max-Q for cupboard)

## 5090 ×2 — do not buy for “64 GB”

Dual GeForce gives **two 32 GB pools**. LLM bake-off uses **vLLM tensor-parallel** on 2×5090 for Qwen only (DeepSeek is skip-listed). ComfyUI still uses one GPU. Not a recommended AU purchase unless Qwen TP numbers surprise.
