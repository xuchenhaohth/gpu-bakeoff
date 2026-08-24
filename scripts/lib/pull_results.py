#!/usr/bin/env python3
"""Pull per-SKU results from Vast instances and merge matrix CSVs."""

from __future__ import annotations

import csv
import subprocess
import sys
from glob import glob
from pathlib import Path

from lib.ssh_preflight import attach_instance_ssh
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


def pull_sku(instance_id: int, sku_id: str) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "artifacts").mkdir(exist_ok=True)
    sku_dir = RESULTS / sku_id
    attach_instance_ssh(instance_id)
    pull_remote(instance_id, "/workspace/bakeoff/results/", sku_dir, is_dir=True)
    pull_remote(instance_id, "/workspace/bakeoff/run.log", sku_dir / "run.log", is_dir=False)


def merge_results() -> bool:
    merged = RESULTS / "matrix.csv"
    header = None
    rows: list[dict[str, str]] = []
    for path in glob(str(RESULTS / "*/matrix.csv")):
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            if header is None:
                header = r.fieldnames
            rows.extend(list(r))
    if header and rows:
        with open(merged, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        print(f"Merged {len(rows)} rows -> {merged}")
        report_html = RESULTS / "report.html"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "remote" / "report.py"),
                "--csv",
                str(merged),
                "--html",
                str(report_html),
                "--update-docs",
            ],
            check=False,
        )
        return True
    print("No matrix.csv files found — no SKU produced results")
    return False
