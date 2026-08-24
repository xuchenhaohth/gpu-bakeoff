#!/usr/bin/env python3
"""Build HTML report and optionally refresh docs/FIT_MATRIX.md from matrix.csv."""

from __future__ import annotations

import argparse
import csv
import html
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_MATRIX = ROOT / "docs" / "FIT_MATRIX.md"


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def pivot_fit(rows: list[dict]) -> dict[str, dict[str, str]]:
    """model -> sku -> fit_status (Layer A only)."""
    out: defaultdict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        if r.get("layer") != "A":
            continue
        model = r.get("model", "")
        sku = r.get("sku", "")
        status = r.get("fit_status") or ("No" if r.get("pass") == "False" else "?")
        # Keep worst status per cell
        prev = out[model].get(sku)
        if not prev or status == "No":
            out[model][sku] = status
        elif prev == "No":
            pass
        else:
            out[model][sku] = status
    return dict(out)


def html_table(rows: list[dict], title: str) -> str:
    if not rows:
        return f"<h2>{html.escape(title)}</h2><p>No data</p>"
    keys = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(k)}</th>" for k in keys)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{html.escape(str(r.get(k,'')))}</td>" for k in keys) + "</tr>"
    return f"<h2>{html.escape(title)}</h2><table border='1' cellpadding='4'><tr>{head}</tr>{body}</table>"


def build_html(rows: list[dict], out_path: Path) -> None:
    fit = pivot_fit(rows)
    skus = sorted({str(r["sku"]) for r in rows if r.get("sku")})
    models = sorted(fit.keys())

    matrix_html = "<h2>Fit matrix (Layer A)</h2><table border='1' cellpadding='6'><tr><th>Model</th>"
    for s in skus:
        matrix_html += f"<th>{html.escape(s)}</th>"
    matrix_html += "</tr>"
    for m in models:
        matrix_html += f"<tr><td>{html.escape(m)}</td>"
        for s in skus:
            matrix_html += f"<td>{html.escape(fit.get(m, {}).get(s, '—'))}</td>"
        matrix_html += "</tr>"
    matrix_html += "</table>"

    content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>GPU Bake-off Report</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; margin-bottom: 2rem; }}
th {{ background: #f0f0f0; }}
</style></head><body>
<h1>GPU bake-off — Harry the Hirer</h1>
<p>Generated from matrix.csv ({len(rows)} rows)</p>
{matrix_html}
{html_table(rows[:50], "Sample rows (first 50)")}
</body></html>"""
    out_path.write_text(content)
    print(f"Wrote {out_path}")


def update_fit_matrix_md(rows: list[dict]) -> None:
    if not DOCS_MATRIX.exists():
        return
    fit = pivot_fit(rows)
    skus = sorted({str(r["sku"]) for r in rows if r.get("sku")})
    lines = ["| Model | " + " | ".join(skus) + " |", "|-------|" + "|".join(["---"] * len(skus)) + "|"]
    for m in sorted(fit.keys()):
        cells = [fit[m].get(s, "—") for s in skus]
        lines.append("| " + m + " | " + " | ".join(cells) + " |")
    block = "\n".join(lines)
    text = DOCS_MATRIX.read_text()
    marker_start = "<!-- AUTO_MATRIX_START -->"
    marker_end = "<!-- AUTO_MATRIX_END -->"
    if marker_start in text:
        before = text.split(marker_start)[0] + marker_start + "\n"
        after = text.split(marker_end)[-1]
        DOCS_MATRIX.write_text(before + block + "\n" + marker_end + after)
        print(f"Updated {DOCS_MATRIX}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--html", type=Path, default=None)
    ap.add_argument("--update-docs", action="store_true")
    args = ap.parse_args()

    rows = load_csv(args.csv)
    html_path = args.html or args.csv.parent / "report.html"
    build_html(rows, html_path)
    if args.update_docs:
        update_fit_matrix_md(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
