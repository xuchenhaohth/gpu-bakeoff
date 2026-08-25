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

All orchestrator scripts read `VAST_API_KEY` from `.env` and pass `--api-key` to every `vastai` call (including `copy`).

**SSH is required.** There is no instance password. `vastai copy` and the matrix start/poll path authenticate as `root@<ssh_host>` using **account** SSH keys.

Team API keys cannot store SSH keys (`Team SSH keys are not supported`). The orchestrator **aborts** in that case — it does **not** fall back to `vastai execute`. That API is not a general shell: on CLI 1.5.x it only allows `ls` / `rm` / `du`, and only on **stopped** instances (`Execute command only avail on stopped instances. Use ssh to run commands on running instances.`). Using it as a copy/start fallback silently billed an idle GPU.

If you are on a personal account, register the local pubkey **before** launch:

```bash
vastai create ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
```

Or paste the pubkey at https://cloud.vast.ai/manage-keys/ (personal context). For an instance created before the key was registered:

```bash
vastai attach ssh <INSTANCE_ID> ~/.ssh/id_ed25519.pub
```

## Instance lifecycle

Poll `vastai show instance <id> --raw`:

| `actual_status` | Action |
|-----------------|--------|
| `null`, `created`, `loading` | Wait (`WAIT_TIMEOUT_SEC`, default 25 min) |
| `running` | Push harness, run matrix |
| `exited`, `unknown`, `offline` | **Destroy immediately**, try next offer |
| `stopped` | Destroy — we use on-demand only |

**Orchestrator note:** Vast returns JSON `null` for `actual_status` while provisioning. Do not treat that as the string `unknown` — poll until a real status appears or timeout.

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

The harness is started over SSH (`setsid nohup …`). While it runs, the orchestrator polls `/workspace/bakeoff/results/PROGRESS.json` over SSH every 30s. If nothing appears within `MATRIX_STARTUP_GRACE_SEC` (default 180s), the SKU aborts instead of waiting the full 8 h.

```text
instance 48605233: matrix 4/14 ideogram_4/img02 timed  12m elapsed  7h47m left  last=ideogram_4/img01 Quantized 12.3s
instance 48605233: prefetch 2/6 flux2_dev  4m elapsed  7h55m left
```

Phases: `onstart` → `install` → `prefetch` → `matrix` → `report` → `done`.

Manual checks on a live instance (SSH, not `vastai execute`):

```bash
url=$(vastai ssh-url <INSTANCE_ID>)   # ssh://root@host:port
# ssh -p <port> -i ~/.ssh/id_ed25519 root@<host> …
ssh … 'cat /workspace/bakeoff/results/PROGRESS.json'
ssh … 'tail -n 80 /workspace/bakeoff/run.log'
ssh … 'test -f /workspace/bakeoff/results/DONE && echo DONE || echo not-done'
```

Harness stdout is redirected to `/workspace/bakeoff/run.log` — **not** `vastai logs` (that shows container bootstrap, not the matrix runner).

## Stale instances (reuse vs destroy)

On each run, before launching:

1. **Reconcile** — scan `vastai show instances` for matrix labels (`bakeoff-spark`, `bakeoff-5090`, …)
2. **Destroy** dead instances (`exited`, `unknown`, `offline`, `stopped`) and duplicate labels (keep one running instance if any)
3. **Reuse** when a healthy instance exists for the SKU:
   - `loading` / provisioning → wait on existing instance (no new launch)
   - `running` + matrix incomplete → resume matrix or push harness if needed
   - `running` + `results/DONE` present → pull results and destroy
4. **Launch** only when no reusable instance exists

State is saved to `config/instances.json` immediately after resolve/launch so `--destroy-only` works mid-run.

`--destroy-only` destroys instances listed in `instances.json` **and** any remaining bakeoff-labeled instances on the account.

## File copy

```bash
vastai copy local:./scripts/remote/ <INSTANCE_ID>:/workspace/bakeoff/
```

The orchestrator copies with rsync (`vastai copy --identity`, SSH `BatchMode`). If SSH keys are missing or the API key is a team key, preflight **exits** instead of launching.

**Never** copy to `/root` or `/` — breaks SSH on some hosts.

## Images

| Arch | Image |
|------|-------|
| x86_64 (5090, PRO 6000) | `vastai/pytorch:@vastai-automatic-tag` |
| aarch64 (GB10 Spark) | `vastai/pytorch:@vastai-automatic-tag` (Vast resolves ARM64/Grace server-side) |

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
| Repeated `loading` during wait | Normal image pull / container start — watch `status_msg` and elapsed time in wait log; timeout is `WAIT_TIMEOUT_SEC` (25 min) then backup offer |
| Repeated `matrix running (running)` or opaque poll lines | Old harness without `PROGRESS.json` — tail `run.log` manually, or re-push harness on next SKU. With current harness, poll lines show phase/job/model |
| Repeated `waiting` then abort `no_progress` | Harness did not write `PROGRESS.json` within `MATRIX_STARTUP_GRACE_SEC` (default 180s) — check SSH start, or destroy and retry |
| SSH timeout / connection refused | Wait for the container, attach the key, or destroy and pick higher `reliability` |
| `vastai_kaalia@…'s password:` | No password exists. Team API keys cannot register SSH keys — switch to a **personal** API key, then `vastai create ssh-key "$(cat ~/.ssh/id_ed25519.pub)"` and `vastai attach ssh <id> ~/.ssh/id_ed25519.pub` |
| `Team SSH keys are not supported` | Preflight abort. Use a personal API key at https://cloud.vast.ai/manage-keys/ |
| CUDA / sm_120 errors | Wrong image or driver on host — next candidate |
| OOM on Hunyuan | Check **host RAM** in CSV, not just VRAM |
| Interrupted run still billing | `uv run python scripts/02_run_bakeoff.py --destroy-only` |
| Re-run launches duplicate instance | Re-run should **reuse** running bakeoff-labeled instances — check reconcile log at startup |

## Console URLs

- Instances: https://console.vast.ai/instances/
- Create/search: https://console.vast.ai/create/
- API keys: https://console.vast.ai/manage-keys/
