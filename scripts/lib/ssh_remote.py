#!/usr/bin/env python3
"""SSH into a Vast instance (required — execute is not a shell on running VMs)."""

from __future__ import annotations

import subprocess
from urllib.parse import urlparse

from lib.vast import _vastai_cmd, local_ssh_identity, vast_cli_error

_ssh_url_cache: dict[int, str] = {}


def parse_ssh_url(url: str) -> tuple[str, str, int]:
    """Return (user, host, port) from an ssh:// URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("ssh", "scp"):
        raise ValueError(f"not an ssh URL: {url}")
    host = parsed.hostname
    port = parsed.port
    user = parsed.username or "root"
    if not host or not port:
        raise ValueError(f"ssh URL missing host or port: {url}")
    return user, host, port


def fetch_ssh_url(instance_id: int, *, refresh: bool = False) -> str:
    if not refresh and instance_id in _ssh_url_cache:
        return _ssh_url_cache[instance_id]

    # ssh-url prints the URL to stdout; --raw wraps a None return as null.
    proc = subprocess.run(
        _vastai_cmd("ssh-url", str(instance_id), raw=False),
        capture_output=True,
        text=True,
    )
    err = vast_cli_error(proc.stdout, proc.stderr)
    if proc.returncode != 0 or err:
        raise RuntimeError(
            f"vastai ssh-url failed for {instance_id}: {err or proc.stderr or proc.stdout}"
        )
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("error:"):
            raise RuntimeError(f"vastai ssh-url failed for {instance_id}: {line}")
        if line.startswith("ssh://") or line.startswith("scp://"):
            _ssh_url_cache[instance_id] = line
            return line
    raise RuntimeError(
        f"vastai ssh-url for {instance_id} did not return ssh:// URL\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )


def invalidate_ssh_url(instance_id: int) -> None:
    _ssh_url_cache.pop(instance_id, None)


def ssh_run(
    instance_id: int,
    command: str,
    *,
    check: bool = True,
    timeout: int = 60,
) -> str:
    """Run a remote command over SSH (BatchMode, publickey only)."""
    identity = local_ssh_identity()
    if identity is None:
        raise RuntimeError(
            "No SSH private key for ~/.ssh/id_ed25519.pub (or id_rsa.pub). "
            "Vast has no VM password."
        )

    url = fetch_ssh_url(instance_id)
    user, host, port = parse_ssh_url(url)
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "PasswordAuthentication=no",
        "-i",
        str(identity),
        "-p",
        str(port),
        f"{user}@{host}",
        command,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ssh {instance_id} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        msg = (proc.stderr or proc.stdout or f"ssh exit {proc.returncode}").strip()
        if check:
            raise RuntimeError(f"ssh {instance_id} failed: {msg}")
        return ""
    return proc.stdout.strip()
