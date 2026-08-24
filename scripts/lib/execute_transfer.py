#!/usr/bin/env python3
"""Copy files to/from a Vast instance via `vastai execute` (no SSH)."""

from __future__ import annotations

import base64
import io
import os
import re
import shlex
import tarfile
from pathlib import Path

from lib.vast import vastai_execute, vastai_execute_output

_CHUNK = 40_000
_B64_RE = re.compile(r"[A-Za-z0-9+/=\n]+")


def parse_copy_spec(spec: str) -> tuple[int | None, str]:
    if spec.startswith("local:"):
        return None, spec[len("local:") :]
    left, sep, right = spec.partition(":")
    if sep and left.isdigit():
        return int(left), right
    raise ValueError(f"unsupported copy spec: {spec}")


def _tar_bytes(path: Path) -> bytes:
    path = Path(str(path).rstrip("/"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if path.is_dir():
            tar.add(path, arcname=".")
        else:
            tar.add(path, arcname=path.name)
    return buf.getvalue()


def _extract_tar_gz(data: bytes, dest: Path, is_dir: bool) -> None:
    dest = Path(str(dest).rstrip("/"))
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        if is_dir or str(dest).endswith("/") or dest.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            tar.extractall(dest)
            return
        files = [m for m in members if m.isfile()]
        if len(files) == 1:
            dest.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(files[0])
            if extracted is None:
                return
            dest.write_bytes(extracted.read())
            return
        dest.mkdir(parents=True, exist_ok=True)
        tar.extractall(dest)


def _append_b64_chunks(instance_id: int, b64: str, remote_path: str) -> None:
    vastai_execute(instance_id, f"rm -f {shlex.quote(remote_path)}", check=True)
    for i in range(0, len(b64), _CHUNK):
        chunk = b64[i : i + _CHUNK]
        snippet = f"open({remote_path!r}, 'a').write({chunk!r})"
        vastai_execute(instance_id, "python3 -c " + shlex.quote(snippet), check=True)


def push_via_execute(instance_id: int, local: Path, remote: str) -> None:
    local = Path(str(local).rstrip("/"))
    remote = remote.rstrip("/") or "/workspace"
    data = _tar_bytes(local)
    print(f"Execute-transfer {local} -> {instance_id}:{remote}/ ({len(data)} bytes)")
    payload = "/tmp/bakeoff_payload.b64"
    _append_b64_chunks(instance_id, base64.b64encode(data).decode("ascii"), payload)
    extract = (
        "import base64, tarfile, io, os\n"
        f"dest = {remote!r}\n"
        f"raw = base64.b64decode(open({payload!r}).read())\n"
        "os.makedirs(dest, exist_ok=True)\n"
        "tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz').extractall(dest)\n"
        "print('extracted', dest, len(raw))\n"
    )
    out = vastai_execute_output(instance_id, "python3 -c " + shlex.quote(extract), check=True)
    if out:
        print(f"  {out}")


def _decode_b64_blob(text: str) -> bytes:
    matches = _B64_RE.findall(text or "")
    if not matches:
        return b""
    blob = max(matches, key=len).replace("\n", "")
    if len(blob) < 8:
        return b""
    try:
        return base64.b64decode(blob, validate=False)
    except Exception:
        return b""


def pull_via_execute(instance_id: int, remote: str, local: Path) -> None:
    is_dir = remote.endswith("/") or str(local).endswith("/")
    remote_path = remote.rstrip("/") or remote
    local = Path(str(local).rstrip("/"))
    pack = (
        "import base64, tarfile, io, os, sys\n"
        f"src = {remote_path!r}\n"
        "if not os.path.exists(src):\n"
        "    raise SystemExit(0)\n"
        "buf = io.BytesIO()\n"
        "with tarfile.open(fileobj=buf, mode='w:gz') as tar:\n"
        "    name = os.path.basename(src.rstrip('/')) or 'data'\n"
        "    tar.add(src, arcname='.' if os.path.isdir(src) else name)\n"
        "sys.stdout.write(base64.b64encode(buf.getvalue()).decode('ascii'))\n"
    )
    print(f"Execute-transfer {instance_id}:{remote} -> {local}")
    out = vastai_execute_output(instance_id, "python3 -c " + shlex.quote(pack), check=False)
    data = _decode_b64_blob(out)
    if not data:
        print(f"  (empty or missing remote path {remote_path})")
        return
    _extract_tar_gz(data, local, is_dir=is_dir)


def copy_via_execute(src: str, dst: str) -> None:
    src_id, src_path = parse_copy_spec(src)
    dst_id, dst_path = parse_copy_spec(dst)
    if src_id is None and dst_id is not None:
        push_via_execute(dst_id, Path(src_path), dst_path)
        return
    if dst_id is None and src_id is not None:
        pull_via_execute(src_id, src_path, Path(dst_path))
        return
    raise RuntimeError(f"execute transfer only supports local <-> instance: {src} -> {dst}")


def execute_copy_enabled() -> bool:
    return os.environ.get("VAST_COPY_VIA_EXECUTE") == "1"
