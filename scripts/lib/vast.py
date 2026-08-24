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
_SSH_PUBKEYS = (
    Path.home() / ".ssh" / "id_ed25519.pub",
    Path.home() / ".ssh" / "id_rsa.pub",
)
_SSH_BATCH_DIR = Path(__file__).resolve().parent / "ssh_batchmode"


def local_ssh_pubkey() -> Path | None:
    for path in _SSH_PUBKEYS:
        if path.is_file():
            return path
    return None


def local_ssh_identity() -> Path | None:
    pub = local_ssh_pubkey()
    if pub is None:
        return None
    identity = pub.with_suffix("")
    return identity if identity.is_file() else None


def _copy_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{_SSH_BATCH_DIR}{os.pathsep}{env.get('PATH', '')}"
    return env


def normalize_vast_list(raw: Any, nested_key: str | None = None) -> list[dict[str, Any]]:
    """Normalize vastai --raw JSON (list, single dict, or keyed wrapper) to a list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if nested_key and nested_key in raw:
            nested = raw[nested_key]
            return nested if isinstance(nested, list) else [nested]
        return [raw]
    return []


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
    from lib.execute_transfer import copy_via_execute, execute_copy_enabled

    if execute_copy_enabled():
        copy_via_execute(src, dst)
        return

    args: list[str] = ["copy", src, dst]
    identity = local_ssh_identity()
    if identity is not None:
        args.extend(["--identity", str(identity)])
    proc = subprocess.run(
        _vastai_cmd(*args, raw=False),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=_copy_env(),
    )
    if proc.returncode == 0:
        return
    lowered = f"{proc.stderr}\n{proc.stdout}".lower()
    if any(
        token in lowered
        for token in ("permission denied", "password", "authentication failed", "publickey")
    ):
        print("SSH copy failed (Vast has no VM password); falling back to execute transfer")
        os.environ["VAST_COPY_VIA_EXECUTE"] = "1"
        copy_via_execute(src, dst)
        return
    if check:
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
