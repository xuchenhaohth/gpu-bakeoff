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
from lib.ssh_remote import (
    HARNESS_ROOT,
    ssh_probe,
    ssh_pull_dir,
    ssh_pull_file,
    wait_for_ssh,
)
from lib.transport import use_onstart_transport
from lib.vast import ROOT

RESULTS = ROOT / "results"
RUN_LOG_REMOTE = f"{HARNESS_ROOT}/run.log"


def pull_remote_ssh(
    instance_id: int,
    remote: str,
    local: Path,
    *,
    is_dir: bool,
    required: bool = True,
) -> None:
    if is_dir:
        ssh_pull_dir(instance_id, remote, local, required=required)
    else:
        ssh_pull_file(instance_id, remote, local, required=required)


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
    pull_remote_ssh(instance_id, f"{HARNESS_ROOT}/results/", sku_dir, is_dir=True)
    pull_remote_ssh(
        instance_id,
        f"{HARNESS_ROOT}/artifacts/",
        sku_dir / "artifacts",
        is_dir=True,
        required=False,
    )
    pull_remote_ssh(instance_id, RUN_LOG_REMOTE, sku_dir / "run.log", is_dir=False, required=False)
    verify_sku_matrix(RESULTS, sku_id)


def pull_run_log_best_effort(instance_id: int, sku_id: str) -> None:
    """Pull run.log for debugging when matrix did not finish."""
    if use_onstart_transport():
        return
    try:
        attach_instance_ssh(instance_id)
        wait_for_ssh(instance_id)
        pull_remote_ssh(
            instance_id,
            RUN_LOG_REMOTE,
            RESULTS / sku_id / "run.log",
            is_dir=False,
            required=False,
        )
    except Exception as exc:
        print(f"  {sku_id}: could not pull run.log: {exc}")


def dump_ssh_diagnostics(instance_id: int) -> None:
    """Print remote ls/ps/run.log when matrix fails to start or finish."""
    if use_onstart_transport():
        return
    probes = [
        ("ls", f"ls -la {HARNESS_ROOT} {HARNESS_ROOT}/results 2>&1 | head -n 30"),
        ("ps", "ps aux | grep -E 'onstart|run_matrix|python3' | grep -v grep || echo no-procs"),
        ("run.log", f"tail -n 40 {RUN_LOG_REMOTE} 2>&1 || echo no-runlog"),
    ]
    for label, cmd in probes:
        try:
            ok, out, err = ssh_probe(instance_id, cmd, timeout=45)
            if not ok:
                print(f"  diag {label}: SSH failed: {err}")
                continue
            snippet = out.strip().replace("\n", " | ")
            if len(snippet) > 400:
                snippet = snippet[:397] + "..."
            print(f"  diag {label}: {snippet or '(empty output)'}")
        except Exception as exc:
            print(f"  diag {label}: {exc}")


def live_pull_sku(instance_id: int, sku_id: str) -> None:
    """Incremental pull while matrix is still running (throttled by caller)."""
    pull_sku(instance_id, sku_id)
    refresh_merged_report(update_docs=False)
