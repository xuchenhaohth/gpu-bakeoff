#!/usr/bin/env python3
"""Thin wrapper around vastai CLI — always uses --raw JSON."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _vastai_cmd(*args: str, raw: bool = True) -> list[str]:
    cmd = ["vastai", *args]
    api_key = os.environ.get("VAST_API_KEY")
    if api_key:
        cmd.extend(["--api-key", api_key])
    if raw:
        cmd.append("--raw")
    return cmd


def vastai(*args: str, check: bool = True) -> Any:
    proc = subprocess.run(_vastai_cmd(*args), capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    payload = stdout or stderr

    if proc.returncode != 0:
        if check:
            raise RuntimeError(
                f"vastai failed ({proc.returncode}): {' '.join(args)}\n"
                f"stderr: {stderr}\nstdout: {stdout}"
            )
        if payload:
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"success": False, "msg": payload}
        return None

    if not payload:
        return None
    try:
        result = json.loads(payload)
    except json.JSONDecodeError:
        return payload

    if isinstance(result, dict) and result.get("error"):
        if check:
            raise RuntimeError(
                f"vastai API error: {' '.join(args)}\n"
                f"response: {payload}"
            )
        return result
    return result


def vastai_copy(src: str, dst: str, check: bool = True) -> None:
    proc = subprocess.run(_vastai_cmd("copy", src, dst, raw=False), capture_output=True, text=True)
    if proc.returncode != 0 and check:
        raise RuntimeError(
            f"vastai copy failed ({proc.returncode}): {src} -> {dst}\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )


def vastai_execute(instance_id: int, cmd: str, check: bool = True) -> None:
    vastai_execute_output(instance_id, cmd, check=check)


def vastai_execute_output(instance_id: int, cmd: str, check: bool = False) -> str:
    proc = subprocess.run(
        _vastai_cmd("execute", str(instance_id), cmd, raw=False),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 and check:
        raise RuntimeError(
            f"vastai execute failed ({proc.returncode}) on {instance_id}\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )
    return proc.stdout.strip()


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        raise SystemExit("Install PyYAML: uv sync") from None
    return yaml.safe_load(path.read_text()) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml
    except ImportError:
        raise SystemExit("Install PyYAML: uv sync") from None
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def instances_path() -> Path:
    return ROOT / "config" / "instances.json"


def load_instances() -> dict:
    p = instances_path()
    if not p.exists():
        return {"instances": {}}
    return json.loads(p.read_text())


def save_instances(data: dict) -> None:
    instances_path().write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    load_dotenv()
    if len(sys.argv) < 2:
        print("Usage: python scripts/lib/vast.py show user")
        sys.exit(1)
    print(json.dumps(vastai(*sys.argv[1:]), indent=2))
