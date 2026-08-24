# Vast.ai operations (gpu-bakeoff)

Reference for this test. Official skill: `~/.agents/skills/vastai/SKILL.md`.

## CLI conventions

- Command: `vastai` (lowercase)
- **Always** pass `--raw` in scripts for JSON
- Destroy: `vastai destroy instance <id> -y` (required for non-interactive)

## Auth & billing

```bash
vastai set api-key <KEY>
vastai show user --raw          # balance, email
vastai show invoices-v1 --charges --limit 20
```

Credits: https://cloud.vast.ai/billing/

**Charges:**

| Event | Billing |
|-------|---------|
| `create instance` | Disk/storage starts |
| `actual_status=running` | GPU hourly starts |
| `stop instance` | GPU stops; disk continues |
| `destroy instance -y` | All charges stop |

Spend cap in `.env`: `MAX_USD=180`. The bake-off script refuses if projected serial spend exceeds cap (`sum(dph × MATRIX_TIMEOUT_SEC)` per SKU, default 8 h each). Only one instance runs at a time.

All orchestrator scripts read `VAST_API_KEY` from `.env` and pass `--api-key` to every `vastai` call (including `copy` and `execute`).

## Instance lifecycle

Poll `vastai show instance <id> --raw`:

| `actual_status` | Action |
|-----------------|--------|
| `null`, `created`, `loading` | Wait (`WAIT_TIMEOUT_SEC`, default 25 min) |
| `running` | Push harness, run matrix |
| `exited`, `unknown`, `offline` | **Destroy immediately**, try next offer |
| `stopped` | Destroy — we use on-demand only |

## Pipeline (this project)

```bash
uv run python scripts/01_search_offers.py    # writes config/offers.yaml
uv run python scripts/02_run_bakeoff.py      # serial per-SKU: launch → matrix → pull → destroy
uv run python scripts/02_run_bakeoff.py --destroy-only   # emergency cleanup
```

Launch flags used:

- On-demand (no `--bid_price`)
- `--disk 400` (`DISK_GB`)
- `--ssh --direct`
- `--label bakeoff-<sku>`
- `--env '-e HF_TOKEN=… -e TZ=Australia/Melbourne -e BAKEOFF_SKU=<sku>'`

Matrix completion is detected via `/workspace/bakeoff/results/DONE` on the remote instance (`MATRIX_TIMEOUT_SEC`, default 8 h).

## File copy

```bash
vastai copy local:./scripts/remote/ <INSTANCE_ID>:/workspace/bakeoff/
```

**Never** copy to `/root` or `/` — breaks SSH on some hosts.

## Images

| Arch | Image |
|------|-------|
| x86_64 (5090, PRO 6000) | `vastai/pytorch:@vastai-automatic-tag` |
| aarch64 (GB10 Spark) | From offer `image` field captured by `01_search_offers.py` — launch fails fast if missing |

## GB10 / Spark search

Vast lists GB10 hosts as `gpu_name=GB10` with `cpu_arch=arm64` (~119 GB VRAM). The CLI filter `gpu_name=GB10` often returns **zero** results (indexing quirk), so `01_search_offers.py` searches:

```text
cpu_arch=arm64 num_gpus=1 gpu_ram>=115 gpu_ram<=125 verified=true rentable=true direct_port_count>=1
```

then post-filters to GB10/Spark names. Use `--debug-spark` to see why offers drop.

## GB10 / Spark fallback

If `01_search_offers.py` finds zero GB10 offers after the ARM fallback:

1. Spark column in matrix = `no rental today`
2. Footnote Enverge Spark Cloud (~US$0.75/hr) as manual option
3. Continue with other four SKUs — do not block the run

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` | Re-run `vastai set api-key` |
| `Insufficient credits` | Top up billing |
| SSH timeout | Wait longer or destroy and pick higher `reliability` offer |
| CUDA / sm_120 errors | Wrong image or driver on host — next candidate |
| OOM on Hunyuan | Check **host RAM** in CSV, not just VRAM |
| Interrupted run still billing | `uv run python scripts/02_run_bakeoff.py --destroy-only` |

## Console URLs

- Instances: https://console.vast.ai/instances/
- Create/search: https://console.vast.ai/create/
- API keys: https://console.vast.ai/manage-keys/
