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

All orchestrator scripts read `VAST_API_KEY` from `.env` and pass `--api-key` to every `vastai` call (including `copy` and `logs`).

## Transport: personal vs team API key

| | Personal API key | Team API key |
|---|------------------|--------------|
| SSH keys | Register at https://cloud.vast.ai/manage-keys/ | **Not supported** |
| Harness delivery | `vastai copy` + SSH start; writes `.env.hf` for Hub auth | Vast `--onstart` clones public git at boot |
| Progress | SSH poll `PROGRESS.json` | `vastai logs` — `[progress]` lines |
| Results | `vastai copy` pull | VM uploads to Hugging Face; local `snapshot_download` |

Preflight picks SSH when the local pubkey is registered; otherwise it uses **onstart** transport automatically.

**Personal SSH setup:**

```bash
vastai create ssh-key "$(cat ~/.ssh/id_ed25519.pub)"
vastai attach ssh <INSTANCE_ID> ~/.ssh/id_ed25519.pub   # if key added after create
```

**Team onstart setup** (no personal key needed):

1. Push harness to public `BAKEOFF_GIT_URL` (default `https://github.com/xuchenhaohth/gpu-bakeoff.git`, branch `BAKEOFF_GIT_REF=main`).
2. Set `HF_TOKEN` in `.env` (model prefetch + results dataset).
3. Optional `HF_RESULTS_REPO=your-username/gpu-bakeoff-results` (default: `{hf_user}/gpu-bakeoff-results`).

Do **not** use `vastai execute` for copy/start/poll on running instances — it only supports `ls`/`rm`/`du` on **stopped** VMs.

Idle instances created without `--onstart` are destroyed on the next run and relaunched with the bootstrap script.

## Instance lifecycle

Poll `vastai show instance <id> --raw`:

| `actual_status` | Action |
|-----------------|--------|
| `null`, `created`, `loading` | Wait (`WAIT_TIMEOUT_SEC`, default 25 min) |
| `running` | Matrix runs (onstart at boot or SSH push) |
| `exited`, `unknown`, `offline` | **Destroy immediately**, try next offer |
| `stopped` | Destroy — we use on-demand only |

**Orchestrator note:** Vast returns JSON `null` for `actual_status` while provisioning. Do not treat that as the string `unknown` — poll until a real status appears or timeout.

## Pipeline (this project)

```bash
uv run python scripts/01_search_offers.py    # writes config/offers.yaml
uv run python scripts/ssh_smoke_test.py --sku dgx_spark_gb10 --candidate-index 1
uv run python scripts/02_run_bakeoff.py      # serial per-SKU: launch → matrix → pull → destroy
uv run python scripts/02_run_bakeoff.py --destroy-only   # emergency cleanup
```

**SSH smoke test** (`ssh_smoke_test.py`): launches one offer with 40GB disk, attaches your pubkey, retries SSH like the bakeoff, runs `echo ok`, then destroys. Use before a full run to avoid paying for an 8h matrix on a bad host (`--offer ID` or `--sku` + `--candidate-index`).

Launch flags used:

- On-demand (no `--bid_price`)
- `--disk 400` (`DISK_GB`)
- `--ssh --direct`
- `--label bakeoff-<sku>`
- `--env '-e HF_TOKEN=… -e HUGGING_FACE_HUB_TOKEN=… -e TZ=… -e BAKEOFF_SKU=<sku> -e BAKEOFF_GIT_URL=… -e BAKEOFF_GIT_REF=…'`
- Team path: `--onstart scripts/lib/onstart_bootstrap.sh`

Matrix completion: SSH transport reads `/workspace/bakeoff/results/DONE`; onstart transport watches logs for `BAKEOFF_DONE exit=N` after HF upload (`MATRIX_TIMEOUT_SEC`, default 8 h).

**Live results:** After each matrix job, the remote harness copies image/video files and LLM transcripts into `artifacts/`, uploads to Hugging Face (team key), and the local poller pulls `results/{sku}/` when `job_index` advances. Open `results/report.html` while a SKU is still running. Instances are destroyed only after `results/{sku}/matrix.csv` exists locally (pull failure keeps the VM for retry). SKUs with existing `results/{sku}/matrix.csv` are skipped on re-run; use `--skip-sku` to force skip.

Fetch existing HF results without launching GPUs:

```bash
uv run python scripts/03_pull_hf_results.py --sku rtx5090_1x
```

Onstart progress (from `vastai logs` and local poller):

```text
== SKU dgx_spark_gb10 (1/5) transport=onstart instance=48614362 dph=$0.38/hr ==
  instance 48614362:  install pip_comfyui  2m elapsed  7h57m left
  instance 48614362:  install pip_vllm  8m elapsed  7h51m left  (unchanged 4m)
    hint: cloning ComfyUI-HunyuanImage-3 (see: vastai logs 48614362 --tail 80)
  instance 48614362:  install skip_vllm_arm64  9m elapsed  ...
  instance 48614362:  prefetch 1/6 ideogram_4  11m elapsed  ...
  instance 48614362:  matrix 1/14 ideogram_4/img01 warmup  45m elapsed  ...
```

Install sub-steps: `pip_comfyui`, `clone_*`, `pip_vllm`, `skip_vllm_arm64` (aarch64), `pip_llama_cpp`, `install_stack_done`.

Phases: `onstart` → `install` → `prefetch` → `matrix` → `report` → `upload` → `done`.

Manual checks:

```bash
# SSH transport
vastai ssh-url <INSTANCE_ID>
ssh … 'cat /workspace/bakeoff/results/PROGRESS.json'
ssh … 'tail -n 80 /workspace/bakeoff/run.log'

# Onstart / team transport
vastai logs <INSTANCE_ID> --tail 200
```

Harness stdout is in `/workspace/bakeoff/run.log` on the VM and mirrored to container logs via `tee`.

## Stale instances (reuse vs destroy)

On each run, before launching:

1. **Reconcile** — scan `vastai show instances` for matrix labels (`bakeoff-spark`, `bakeoff-5090`, …)
2. **Destroy** dead instances (`exited`, `unknown`, `offline`, `stopped`) and duplicate labels (keep one running instance if any)
3. **Onstart transport:** destroy running instances with no `[progress]` / bootstrap lines in logs (idle pre-onstart boxes)
4. **Reuse** when a healthy instance exists for the SKU:
   - `loading` / provisioning → wait on existing instance (no new launch)
   - `running` + matrix incomplete + harness active → resume (poll logs or SSH)
   - `running` + matrix done → pull results and destroy
5. **Launch** only when no reusable instance exists

State is saved to `config/instances.json` immediately after resolve/launch so `--destroy-only` works mid-run.

`--destroy-only` destroys instances listed in `instances.json` **and** any remaining bakeoff-labeled instances on the account.

## File copy (SSH transport only)

Harness push and result pull use **tar over the same `ssh-url` session** as matrix polling (`Push (ssh)` / `Pull (ssh)` in logs). Legacy `vastai copy` is not used for running instances — it can land files outside the container.

```bash
# Manual smoke: SSH auth + optional harness push (~minutes, 40GB disk)
uv run python scripts/ssh_smoke_test.py --sku dgx_spark_gb10 --candidate-index 1 --push
```

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
| Repeated `waiting` then abort `no_progress` (SSH) | Harness never wrote `PROGRESS.json` — check `results/{sku}/run.log` locally; re-run reuses instance if pid/progress exists. Common causes: SSH auth lag (orchestrator retries ~80s), or old `setsid nohup … &` start killing the job. Fix: `start_matrix.sh` runs in foreground and verifies pid. |
| Repeated `waiting` then abort `no_progress` (onstart) | Clone/bootstrap failed — check `vastai logs`, confirm `BAKEOFF_GIT_URL` is public and `BAKEOFF_GIT_REF` exists |
| `Permission denied (publickey)` right after `running` | Normal for a few seconds after `attach ssh` — orchestrator logs each SSH attempt and `ssh-url` host:port on first/last retry. Manual: wait 30–60s, or `vastai attach ssh <id> "$(cat ~/.ssh/id_ed25519.pub)"` |
| `Permission denied` for full retry window (~80s) | Host never accepted your key — not image lag. Orchestrator destroys that instance and tries the next offer in `offers.yaml`. `diag ls/ps` showing `SSH failed: …` means auth failed (not an empty VM). |
| `ssh auth failed (all candidates)` | Every Spark (or SKU) offer failed SSH — destroy stuck instances (`--destroy-only`) or pick new offers via `01_search_offers.py` |
| Pre-flight SSH on one offer | `uv run python scripts/ssh_smoke_test.py --sku dgx_spark_gb10 --candidate-index 1` (40GB disk, destroy on exit) |
| `start_matrix.sh: No such file or directory` | `vastai copy` missed the container — harness is pushed via SSH tar now. Smoke: `ssh_smoke_test.py --push`. Check log for `Push (ssh)` and `Harness verified`. |
| Same `install pip_*` line with `(unchanged Nm)` | Normal during long pip — read the `hint:` line or `vastai logs --tail 80` |
| Stuck on `install install_stack` (old harness) | Push latest `main` — expect sub-steps `pip_comfyui`, `pip_vllm`, etc. |
| `install skip_vllm_arm64` on Spark | Expected — vLLM has no reliable aarch64 wheel; Qwen LLM jobs stub |
| `Team SSH keys are not supported` | Expected on team keys — onstart transport is used automatically |
| SSH timeout / connection refused | Personal-key path only — attach key or destroy and retry |
| CUDA / sm_120 errors | Wrong image or driver on host — next candidate |
| OOM on Hunyuan | Check **host RAM** in CSV, not just VRAM |
| Interrupted run still billing | `uv run python scripts/02_run_bakeoff.py --destroy-only` |
| Re-run launches duplicate instance | Re-run should **reuse** running bakeoff-labeled instances — check reconcile log at startup |

## Console URLs

- Instances: https://console.vast.ai/instances/
- Create/search: https://console.vast.ai/create/
- API keys: https://console.vast.ai/manage-keys/
