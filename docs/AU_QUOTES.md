# Australian purchase quotes (indicative)

> **Re-quote live** before the boss pack goes out. Prices inc GST unless noted. Stock changes daily.

Last template update: 2026-08-24. **Verify at retailer checkout.**

## Tier 1 — desk / low power

### DGX Spark / GB10 appliance (complete system)

| Retailer | Product | Price (inc GST) | Warranty | URL |
|----------|---------|-----------------|----------|-----|
| Centrecom | ASUS Ascent GX10 128GB/1TB | ~A$6,249 | Check listing | centrecom.com.au |
| Scorptec | ASUS Ascent GX10 1TB | ~A$6,999 | Check listing | scorptec.com.au |
| PLE | ASUS Ascent GX10 1TB | ~A$6,999 | Check listing | ple.com.au |
| PCCG | ASUS Ascent GX10 | ~A$6,999 | Check listing | pccasegear.com |
| Core Electronics | NVIDIA DGX Blackwell Spark | A$8,999 | Check listing | core-electronics.com.au |
| Scorptec | MSI EdgeXpert GB10 4TB | ~A$7,999 | Check listing | scorptec.com.au |

**Notes:** Complete mini PC, ~140–240 W, 128 GB unified memory, ARM. ACL applies.

## Tier 1b — desk / fast 32 GB

### RTX 5090 32 GB (GPU card only)

| Retailer | Example SKU | Price (inc GST) | Warranty | URL |
|----------|-------------|-----------------|----------|-----|
| Scorptec | Palit RTX 5090 GameRock OC | ~A$7,199 | 3 yr typical AIB | scorptec.com.au |
| Scorptec | ASUS TUF RTX 5090 OC | ~A$7,499 | 3 yr | scorptec.com.au |

**Workstation build:** add ~A$3,000–5,000 (CPU, 128 GB RAM, PSU 1000 W+, NVMe) → **~A$10,000–13,000** all-in.

**Desk vs shared:** GeForce is appropriate for **1–2 desk users**. Not recommended as shared IT inference server (licence + no ECC).

## Tier 2 — business workstation

### RTX PRO 6000 Blackwell 96 GB (GPU card)

| Retailer | SKU | Price (inc GST) | Warranty | URL |
|----------|-----|-----------------|----------|-----|
| MMT | 900-5G144-2500-000 | RRP A$21,690 | 3 yr | mmt.com.au |
| Scorptec | RTX PRO 6000 96GB | A$24,999 | **3 yr** | scorptec.com.au |
| MSY | RTX PRO 6000 96GB | A$25,100 | Check listing | msy.com.au |

**Workstation build:** Threadripper PRO / Xeon W, 256 GB ECC RAM, 1200 W+ PSU → **~A$26,000–33,000** all-in.

**Shared IT:** ECC, 3 yr NVIDIA workstation warranty, MIG optional — preferred for cupboard/server use.

## Tier 3 — capacity

### 2× RTX PRO 6000

| Item | Estimate (inc GST) |
|------|-------------------|
| 2× PRO 6000 cards | ~A$50,000–50,200 |
| Dual-GPU platform (EPYC/TR Pro, 256 GB+ RAM, 1600 W PSU, NVMe 2 TB) | ~A$8,000–15,000 |
| **Total** | **~A$50,000–70,000** |

Only tier that runs **DeepSeek-V4-Flash native** (~170 GB weights) without heavy GGUF.

## Integrators (full workstations + on-site warranty)

- Leader Computers (AU)
- Dell Precision / HP Z (request RTX PRO 6000 quote)
- Local AV/IT integrators for Harry the Hirer

## Quote checklist for PO

- [ ] Retailer name + SKU
- [ ] Price inc GST
- [ ] In stock / lead time
- [ ] Warranty years + RMA path (store vs manufacturer)
- [ ] Power draw (W) for facilities
- [ ] Desk vs shared IT caption

## 5090 ×2 — do not buy for “64 GB”

Dual GeForce gives **two 32 GB pools**. Not a recommended AU purchase unless bake-off shows unexpected sharding win (unlikely).
