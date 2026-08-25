#!/usr/bin/env python3
"""Pull per-SKU bakeoff results from Hugging Face (no Vast billing)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.hf_results import pull_sku_from_hf, resolve_hf_results_repo  # noqa: E402
from lib.pull_results import refresh_merged_report  # noqa: E402
from lib.vast import load_dotenv  # noqa: E402

RESULTS = ROOT / "results"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pull bakeoff results from Hugging Face")
    parser.add_argument("--sku", help="SKU id to pull (default: all SKUs with matrix.csv on HF)")
    parser.add_argument("--dest", type=Path, default=RESULTS, help="Local results root")
    args = parser.parse_args()

    load_dotenv()
    dest = args.dest
    dest.mkdir(parents=True, exist_ok=True)

    if args.sku:
        pull_sku_from_hf(args.sku, dest)
        refresh_merged_report(update_docs=False)
        print(f"OK  {dest / args.sku / 'matrix.csv'}")
        return 0

    from huggingface_hub import HfApi

    repo_id = resolve_hf_results_repo()
    token = os.environ.get("HF_TOKEN", "").strip() or None
    api = HfApi(token=token)
    files = api.list_repo_files(repo_id, repo_type="dataset")
    skus = sorted({f.split("/")[0] for f in files if f.endswith("matrix.csv")})
    for sku in skus:
        pull_sku_from_hf(sku, dest)
    refresh_merged_report(update_docs=False)
    print(f"Pulled {len(skus)} SKU(s) to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
