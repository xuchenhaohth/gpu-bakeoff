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
from lib.transport import use_onstart_transport
from lib.vast import ROOT, vastai_copy

RESULTS = ROOT / "results"


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
    pull_remote(instance_id, "/workspace/bakeoff/results/", sku_dir, is_dir=True)
    pull_remote(instance_id, "/workspace/bakeoff/artifacts/", sku_dir / "artifacts", is_dir=True)
    pull_remote(instance_id, "/workspace/bakeoff/run.log", sku_dir / "run.log", is_dir=False)
    verify_sku_matrix(RESULTS, sku_id)


def live_pull_sku(instance_id: int, sku_id: str) -> None:
    """Incremental pull while matrix is still running (throttled by caller)."""
    pull_sku(instance_id, sku_id)
    refresh_merged_report(update_docs=False)
