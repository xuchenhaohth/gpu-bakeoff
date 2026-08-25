"""Write /workspace/bakeoff/results/PROGRESS.json heartbeat for orchestrator polling."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REMOTE_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = REMOTE_ROOT / "results"
PROGRESS_PATH = RESULTS_DIR / "PROGRESS.json"

_state: dict[str, Any] = {}


def _sku() -> str:
    return os.environ.get("BAKEOFF_SKU", "unknown")


def write_progress(
    phase: str,
    *,
    job_index: int | None = None,
    job_total: int | None = None,
    model: str | None = None,
    prompt_id: str | None = None,
    stage: str | None = None,
    message: str | None = None,
    last_result: str | None = None,
    prefetch_index: int | None = None,
    prefetch_total: int | None = None,
) -> dict[str, Any]:
    """Update PROGRESS.json and print a one-line status to stdout."""
    global _state
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "phase": phase,
        "sku": _sku(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if job_index is not None:
        data["job_index"] = job_index
    if job_total is not None:
        data["job_total"] = job_total
    if model is not None:
        data["model"] = model
    if prompt_id is not None:
        data["prompt_id"] = prompt_id
    if stage is not None:
        data["stage"] = stage
    if message is not None:
        data["message"] = message
    if last_result is not None:
        data["last_result"] = last_result
    if prefetch_index is not None:
        data["prefetch_index"] = prefetch_index
    if prefetch_total is not None:
        data["prefetch_total"] = prefetch_total

    # Preserve last_result across updates when not supplied
    if last_result is None and _state.get("last_result"):
        data["last_result"] = _state["last_result"]

    _state = data
    PROGRESS_PATH.write_text(json.dumps(data, indent=2) + "\n")

    line = format_line(data)
    print(line, flush=True)
    return data


def format_line(data: dict[str, Any]) -> str:
    phase = data.get("phase", "?")
    parts: list[str] = [f"[progress] {phase}"]

    if phase == "prefetch":
        pi = data.get("prefetch_index")
        pt = data.get("prefetch_total")
        if pi is not None and pt is not None:
            parts.append(f"{pi}/{pt}")
        model = data.get("model")
        if model:
            parts.append(str(model))
    elif phase == "matrix":
        ji = data.get("job_index")
        jt = data.get("job_total")
        if ji is not None and jt is not None:
            parts.append(f"{ji}/{jt}")
        model = data.get("model")
        prompt_id = data.get("prompt_id")
        if model and prompt_id:
            parts.append(f"{model}/{prompt_id}")
        elif model:
            parts.append(str(model))
        stage = data.get("stage")
        if stage:
            parts.append(str(stage))
    else:
        msg = data.get("message")
        if msg:
            parts.append(str(msg))
        model = data.get("model")
        if model:
            parts.append(str(model))

    last = data.get("last_result")
    if last and phase == "matrix":
        parts.append(f"last={last}")

    return " ".join(parts)


def format_last_result(row: dict[str, Any]) -> str:
    model = row.get("model", "?")
    prompt = row.get("prompt_id", "?")
    fit = row.get("fit_status", "?")
    wall = row.get("wall_sec")
    if wall is not None:
        return f"{model}/{prompt} {fit} {wall}s"
    return f"{model}/{prompt} {fit}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update bakeoff PROGRESS.json")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--job-index", type=int)
    parser.add_argument("--job-total", type=int)
    parser.add_argument("--model")
    parser.add_argument("--prompt-id")
    parser.add_argument("--stage")
    parser.add_argument("--message")
    parser.add_argument("--last-result")
    parser.add_argument("--prefetch-index", type=int)
    parser.add_argument("--prefetch-total", type=int)
    args = parser.parse_args(argv)

    write_progress(
        args.phase,
        job_index=args.job_index,
        job_total=args.job_total,
        model=args.model,
        prompt_id=args.prompt_id,
        stage=args.stage,
        message=args.message,
        last_result=args.last_result,
        prefetch_index=args.prefetch_index,
        prefetch_total=args.prefetch_total,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
