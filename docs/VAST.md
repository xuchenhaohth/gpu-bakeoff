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

Spend cap in `.env`: `MAX_USD=180`. Launch script refuses if projected 24 h × 5 boxes exceeds cap.

All orchestrator scripts read `VAST_API_KEY` from `.env` and pass `--api-key` to every `vastai` call (including `copy` and `execute`).

## Instance lifecycle

Poll `vastai show instance <id> --raw`:

| `actual_status` | Action |
|-----------------|--------|
| `null`, `created`, `loading` | Wait (timeout 25 min) |
| `running` | Push harness, run matrix |
| `exited`, `unknown`, `offline` | **Destroy immediately**, try next offer |
| `stopped` | Destroy or start — we use on-demand only |

## Search & launch (this project)

```bash
python3 scripts/01_search_offers.py   # writes config/offers.yaml
python3 scripts/02_launch.py          # reads offers.yaml top candidate per SKU
python3 scripts/03_wait_running.py
```

Launch flags used:

- On-demand (no `--bid_price`)
- `--disk 400`
- `--ssh --direct`
- `--label bakeoff-<sku>`
- `--env '-e HF_TOKEN=… -e TZ=Australia/Melbourne'`

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

## GB10 / Spark fallback

If `01_search_offers.py` finds zero GB10 offers:

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

## Console URLs

- Instances: https://console.vast.ai/instances/
- Create/search: https://console.vast.ai/create/
- API keys: https://console.vast.ai/manage-keys/
