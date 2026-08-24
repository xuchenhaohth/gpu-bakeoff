#!/usr/bin/env python3
"""Merge results into docs/BOSS_PACK.md executive summary placeholders."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "results" / "matrix.csv"
BOSS = ROOT / "docs" / "BOSS_PACK.md"


def main() -> int:
    if not CSV.exists():
        print(f"Missing {CSV} — run 02_run_bakeoff.py first")
        return 1
    rows = list(csv.DictReader(CSV.open()))
    fit: defaultdict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        if r.get("layer") != "A":
            continue
        fit[r["model"]][r["sku"]] = r.get("fit_status", "?")

    bullets = []
    for model, skus in sorted(fit.items()):
        ok = [s for s, v in skus.items() if v not in ("No", "")]
        no = [s for s, v in skus.items() if v == "No"]
        if no:
            bullets.append(f"- **{model}**: does not fit on {', '.join(no)}")
        if ok:
            bullets.append(f"- **{model}**: runs on {', '.join(ok)}")

    text = BOSS.read_text()
    summary = "\n".join(bullets) if bullets else "_No results yet._"

    tbd = (
        "_TBD: Under our budget options, which models run locally for video/image "
        "generation and coding agents, and which tier is the minimum viable purchase._"
    )
    if tbd in text:
        text = text.replace(tbd, summary)

    if "## Key findings (bullets)" in text:
        block = "## Key findings (bullets)\n\n" + summary + "\n"
        text = re.sub(
            r"## Key findings \(bullets\)\n\n.*?(?=\n---\n\n## Desk vs shared)",
            block,
            text,
            count=1,
            flags=re.DOTALL,
        )

    BOSS.write_text(text)
    print(f"Updated {BOSS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
