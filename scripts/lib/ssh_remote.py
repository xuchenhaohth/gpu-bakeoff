#!/usr/bin/env python3
"""SSH into a Vast instance (required — execute is not a shell on running VMs)."""

from __future__ import annotations

import os
import subprocess
import time
from urllib.parse import urlparse

from lib.vast import _vastai_cmd, local_ssh_identity, vast_cli_error

_ssh_url_cache: dict[int, str] = {}

SSH_WAIT_ATTEMPTS = int(os.environ.get("SSH_WAIT_ATTEMPTS", "20"))
SSH_WAIT_DELAY_SEC = float(os.environ.get("SSH_WAIT_DELAY_SEC", "4"))


class SshNotReadyError(RuntimeError):
    """SSH auth/connect did not succeed within the retry window."""

    def __init__(
        self,
        instance_id: int,
        message: str,
        *,
        auth_denied: bool = False,
    ) -> None:
        self.instance_id = instance_id
        self.auth_denied = auth_denied
        super().__init__(message)


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


def format_ssh_endpoint(instance_id: int, *, refresh: bool = False) -> str:
    """Human-readable ssh target for logs (user@host:port)."""
    url = fetch_ssh_url(instance_id, refresh=refresh)
    user, host, port = parse_ssh_url(url)
    return f"{user}@{host}:{port} (ssh-url {url})"


def log_ssh_endpoint(instance_id: int, *, refresh: bool = False) -> None:
    try:
        print(f"  SSH endpoint instance {instance_id}: {format_ssh_endpoint(instance_id, refresh=refresh)}")
    except Exception as exc:
        print(f"  SSH endpoint instance {instance_id}: could not fetch ssh-url: {exc}")


def is_ssh_retryable(msg: str) -> bool:
    """True when SSH auth/connect errors may clear after attach/propagation."""
    lowered = msg.lower()
    return any(
        token in lowered
        for token in (
            "permission denied",
            "connection refused",
            "connection timed out",
            "connection reset",
            "no route to host",
            "ssh exit 255",
            "timed out",
            "try again",
        )
    )


def is_ssh_auth_denied(msg: str) -> bool:
    return "permission denied" in msg.lower()


def _ssh_base_cmd(identity: str, user: str, host: str, port: int, command: str) -> list[str]:
    return [
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
        "-o",
        "IdentitiesOnly=yes",
        "-i",
        identity,
        "-p",
        str(port),
        f"{user}@{host}",
        command,
    ]


def ssh_probe(
    instance_id: int,
    command: str,
    *,
    timeout: int = 60,
) -> tuple[bool, str, str]:
    """Run SSH; return (ok, stdout, error_msg). error_msg empty on success."""
    identity = local_ssh_identity()
    if identity is None:
        return False, "", (
            "No SSH private key for ~/.ssh/id_ed25519.pub (or id_rsa.pub). "
            "Vast has no VM password."
        )

    url = fetch_ssh_url(instance_id)
    user, host, port = parse_ssh_url(url)
    cmd = _ssh_base_cmd(str(identity), user, host, port, command)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        invalidate_ssh_url(instance_id)
        return False, "", f"ssh {instance_id} timed out after {timeout}s"
    if proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        err = (proc.stderr or proc.stdout or f"ssh exit {proc.returncode}").strip()
        return False, "", f"ssh {instance_id} failed: {err}"
    return True, proc.stdout.strip(), ""


def ssh_run(
    instance_id: int,
    command: str,
    *,
    check: bool = True,
    timeout: int = 60,
) -> str:
    """Run a remote command over SSH (BatchMode, publickey only)."""
    ok, stdout, err = ssh_probe(instance_id, command, timeout=timeout)
    if not ok:
        if check:
            raise RuntimeError(err)
        return ""
    return stdout


def wait_for_ssh(
    instance_id: int,
    *,
    attempts: int | None = None,
    delay_sec: float | None = None,
) -> None:
    """Retry SSH until auth/connect succeeds (Vast keys can lag after attach)."""
    tries = attempts if attempts is not None else SSH_WAIT_ATTEMPTS
    delay = delay_sec if delay_sec is not None else SSH_WAIT_DELAY_SEC
    last_err = ""
    endpoint_logged = False
    for attempt in range(1, tries + 1):
        ok, out, probe_err = ssh_probe(instance_id, "echo ok", timeout=30)
        if ok and out.strip() == "ok":
            if attempt > 1:
                print(f"  SSH ready on instance {instance_id} (attempt {attempt})")
            return
        last_err = probe_err if not ok else f"unexpected echo output: {out!r}"
        if not is_ssh_retryable(last_err):
            log_ssh_endpoint(instance_id, refresh=True)
            raise SshNotReadyError(
                instance_id,
                last_err,
                auth_denied=is_ssh_auth_denied(last_err),
            )
        if attempt == 1 or attempt == tries:
            if not endpoint_logged:
                log_ssh_endpoint(instance_id, refresh=True)
                endpoint_logged = True
        short = last_err if len(last_err) <= 160 else last_err[:157] + "..."
        print(f"  SSH attempt {attempt}/{tries}: {short}")
        invalidate_ssh_url(instance_id)
        if attempt < tries:
            time.sleep(delay)
    raise SshNotReadyError(
        instance_id,
        f"ssh {instance_id} not ready after {tries} attempts: {last_err}",
        auth_denied=is_ssh_auth_denied(last_err),
    )
