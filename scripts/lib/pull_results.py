#!/usr/bin/env python3
"""Pull per-SKU results from Vast instances and merge matrix CSVs."""

from __future__ import annotations

import csv
import subprocess
import sys
from glob import glob
from pathlib import Path

from lib.hf_results import pull_sku_from_hf, sku_matrix_path, verify_sku_matrix
from lib.ssh_preflight import attach_instance_ssh
from lib.ssh_remote import ssh_run, wait_for_ssh
from lib.transport import use_onstart_transport
from lib.vast import ROOT, vastai_copy

RESULTS = ROOT / "results"
RUN_LOG_REMOTE = "/workspace/bakeoff/run.log"


def pull_remote(instance_id: int, remote: str, local: Path, *, is_dir: bool) -> None:
    src = f"{instance_id}:{remote}"
    if is_dir:
        local.mkdir(parents=True, exist_ok=True)
        dst = f"local:{local}/"
    else:
        local.parent.mkdir(parents=True, exist_ok=True)
        dst = f"local:{local}"
    print(f"Pull {src} -> {dst}")
    vastai_copy(src, dst, check=False)


def sku_has_results(sku_id: str) -> bool:
    return sku_matrix_path(RESULTS, sku_id).is_file()


def refresh_merged_report(update_docs: bool = False) -> bool:
    """Merge per-SKU matrix.csv files and rebuild results/report.html."""
    merged = RESULTS / "matrix.csv"
    header = None
    rows: list[dict[str, str]] = []
    for path in glob(str(RESULTS / "*/matrix.csv")):
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            if header is None:
                header = r.fieldnames
            rows.extend(list(r))
    if not header or not rows:
        return False
    with open(merged, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    print(f"Merged {len(rows)} rows -> {merged}")
    report_html = RESULTS / "report.html"
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "remote" / "report.py"),
        "--csv",
        str(merged),
        "--html",
        str(report_html),
        "--results-root",
        str(RESULTS),
    ]
    if update_docs:
        cmd.append("--update-docs")
    subprocess.run(cmd, check=False)
    return True


def merge_results() -> bool:
    ok = refresh_merged_report(update_docs=True)
    if not ok:
        print("No matrix.csv files found — no SKU produced results")
    return ok


def pull_sku(instance_id: int, sku_id: str) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if use_onstart_transport():
        pull_sku_from_hf(sku_id, RESULTS)
        return

    sku_dir = RESULTS / sku_id
    attach_instance_ssh(instance_id)
    wait_for_ssh(instance_id)
    pull_remote(instance_id, "/workspace/bakeoff/results/", sku_dir, is_dir=True)
    pull_remote(instance_id, "/workspace/bakeoff/artifacts/", sku_dir / "artifacts", is_dir=True)
    pull_remote(instance_id, RUN_LOG_REMOTE, sku_dir / "run.log", is_dir=False)
    verify_sku_matrix(RESULTS, sku_id)


def pull_run_log_best_effort(instance_id: int, sku_id: str) -> None:
    """Pull run.log for debugging when matrix did not finish."""
    if use_onstart_transport():
        return
    try:
        attach_instance_ssh(instance_id)
        wait_for_ssh(instance_id)
        pull_remote(instance_id, RUN_LOG_REMOTE, RESULTS / sku_id / "run.log", is_dir=False)
    except Exception as exc:
        print(f"  {sku_id}: could not pull run.log: {exc}")


def dump_ssh_diagnostics(instance_id: int) -> None:
    """Print remote ls/ps/run.log when matrix fails to start or finish."""
    if use_onstart_transport():
        return
    probes = [
        ("ls", "ls -la /workspace/bakeoff /workspace/bakeoff/results 2>&1 | head -n 30"),
        ("ps", "ps aux | grep -E 'onstart|run_matrix|python3' | grep -v grep || echo no-procs"),
        ("run.log", f"tail -n 40 {RUN_LOG_REMOTE} 2>&1 || echo no-runlog"),
    ]
    for label, cmd in probes:
        try:
            out = ssh_run(instance_id, cmd, check=False, timeout=45)
            snippet = out.strip().replace("\n", " | ")
            if len(snippet) > 400:
                snippet = snippet[:397] + "..."
            print(f"  diag {label}: {snippet or '(empty)'}")
        except Exception as exc:
            print(f"  diag {label}: {exc}")


def live_pull_sku(instance_id: int, sku_id: str) -> None:
    """Incremental pull while matrix is still running (throttled by caller)."""
    pull_sku(instance_id, sku_id)
    refresh_merged_report(update_docs=False)
