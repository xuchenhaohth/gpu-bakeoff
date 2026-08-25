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
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".gif"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


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
        prev = out[model].get(sku)
        if not prev or status == "No":
            out[model][sku] = status
        elif prev == "No":
            pass
        else:
            out[model][sku] = status
    return dict(out)


def resolve_media_path(results_root: Path, csv_path: Path, row: dict, field: str) -> Path | None:
    rel = (row.get(field) or "").strip()
    if not rel:
        return None
    sku = row.get("sku", "")
    candidates = [
        results_root / sku / rel,
        csv_path.parent / rel,
        results_root / rel,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def media_html(path: Path) -> str:
    ext = path.suffix.lower()
    uri = html.escape(path.as_uri())
    if ext in VIDEO_EXTS:
        return f'<video controls width="320" src="{uri}"></video>'
    if ext in IMAGE_EXTS:
        return f'<img src="{uri}" alt="{html.escape(path.name)}" width="320">'
    return f'<a href="{uri}">{html.escape(path.name)}</a>'


def transcript_html(results_root: Path, csv_path: Path, row: dict) -> str:
    path = resolve_media_path(results_root, csv_path, row, "transcript_path")
    if path is None:
        note = row.get("note") or row.get("error") or ""
        return f"<pre>{html.escape(note)}</pre>" if note else "<em>—</em>"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return f"<pre>{html.escape(text)}</pre>"


def gallery_html(rows: list[dict], csv_path: Path, results_root: Path) -> str:
    if not rows:
        return "<h2>Outputs gallery</h2><p>No rows</p>"
    parts = ["<h2>Outputs gallery</h2>"]
    for r in rows:
        model = html.escape(str(r.get("model", "?")))
        prompt = html.escape(str(r.get("prompt_id", "?")))
        sku = html.escape(str(r.get("sku", "?")))
        fit = html.escape(str(r.get("fit_status", "")))
        parts.append(f"<section class='gallery-item'><h3>{sku} — {model}/{prompt} ({fit})</h3>")
        artifact = resolve_media_path(results_root, csv_path, r, "artifact_path")
        if artifact:
            parts.append(media_html(artifact))
        else:
            parts.append("<p><em>No image/video artifact</em></p>")
        parts.append(transcript_html(results_root, csv_path, r))
        parts.append("</section>")
    return "\n".join(parts)


def html_table(rows: list[dict], title: str) -> str:
    if not rows:
        return f"<h2>{html.escape(title)}</h2><p>No data</p>"
    keys = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(k)}</th>" for k in keys)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f"<td>{html.escape(str(r.get(k,'')))}</td>" for k in keys) + "</tr>"
    return f"<h2>{html.escape(title)}</h2><table border='1' cellpadding='4'><tr>{head}</tr>{body}</table>"


def build_html(rows: list[dict], out_path: Path, csv_path: Path, results_root: Path) -> None:
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

    gallery = gallery_html(rows, csv_path, results_root)

    content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>GPU Bake-off Report</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; margin-bottom: 2rem; }}
th {{ background: #f0f0f0; }}
.gallery-item {{ border: 1px solid #ddd; padding: 1rem; margin-bottom: 1.5rem; }}
.gallery-item pre {{ max-height: 240px; overflow: auto; background: #f8f8f8; padding: 0.5rem; }}
</style></head><body>
<h1>GPU bake-off — Harry the Hirer</h1>
<p>Generated from {html.escape(csv_path.name)} ({len(rows)} rows)</p>
{matrix_html}
{gallery}
{html_table(rows[:50], "Sample rows (first 50)")}
</body></html>"""
    out_path.write_text(content)
    print(f"Wrote {out_path}")


def boss_fit_status(status: str) -> str:
    """Map Stub to em-dash for boss-facing matrix; real evidence passes through."""
    if status == "Stub":
        return "—"
    return status


def update_fit_matrix_md(rows: list[dict]) -> None:
    if not DOCS_MATRIX.exists():
        return
    fit = pivot_fit(rows)
    skus = sorted({str(r["sku"]) for r in rows if r.get("sku")})
    note = "_Stub rows excluded from boss matrix._"
    lines = [note, "", "| Model | " + " | ".join(skus) + " |", "|-------|" + "|".join(["---"] * len(skus)) + "|"]
    for m in sorted(fit.keys()):
        cells = [boss_fit_status(fit[m].get(s, "—")) for s in skus]
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
    ap.add_argument("--results-root", type=Path, default=None)
    ap.add_argument("--update-docs", action="store_true")
    args = ap.parse_args()

    rows = load_csv(args.csv)
    html_path = args.html or args.csv.parent / "report.html"
    results_root = args.results_root or args.csv.parent.parent
    build_html(rows, html_path, args.csv, results_root)
    if args.update_docs:
        update_fit_matrix_md(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
