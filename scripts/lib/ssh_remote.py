#!/usr/bin/env python3
"""SSH into a Vast instance (required — execute is not a shell on running VMs)."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from lib.vast import _vastai_cmd, local_ssh_identity, vast_cli_error

_ssh_url_cache: dict[int, str] = {}

SSH_WAIT_ATTEMPTS = int(os.environ.get("SSH_WAIT_ATTEMPTS", "20"))
SSH_WAIT_DELAY_SEC = float(os.environ.get("SSH_WAIT_DELAY_SEC", "4"))

HARNESS_ROOT = "/workspace/bakeoff"
HARNESS_START_SCRIPT = f"{HARNESS_ROOT}/start_matrix.sh"
HARNESS_RUN_MATRIX = f"{HARNESS_ROOT}/run_matrix.py"


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


def _ssh_connection(instance_id: int) -> tuple[Path, str, str, int]:
    identity = local_ssh_identity()
    if identity is None:
        raise RuntimeError(
            "No SSH private key for ~/.ssh/id_ed25519.pub (or id_rsa.pub). "
            "Vast has no VM password."
        )
    url = fetch_ssh_url(instance_id)
    user, host, port = parse_ssh_url(url)
    return identity, user, host, port


def ssh_push_dir(
    instance_id: int,
    local_dir: Path,
    remote_dir: str,
    *,
    timeout: int = 600,
) -> None:
    """Push a local directory tree into the container via tar over SSH."""
    local_path = local_dir.resolve()
    if not local_path.is_dir():
        raise RuntimeError(f"local directory missing: {local_path}")

    identity, user, host, port = _ssh_connection(instance_id)
    remote = remote_dir.rstrip("/")
    remote_cmd = f"mkdir -p {shlex.quote(remote)} && tar xzf - -C {shlex.quote(remote)}"
    ssh_cmd = _ssh_base_cmd(str(identity), user, host, port, remote_cmd)

    print(f"Push (ssh) {local_path} -> instance {instance_id}:{remote}/")

    tar_proc = subprocess.Popen(
        ["tar", "czf", "-", "-C", str(local_path), "."],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        ssh_proc = subprocess.Popen(
            ssh_cmd,
            stdin=tar_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if tar_proc.stdout is not None:
            tar_proc.stdout.close()
        _, ssh_err = ssh_proc.communicate(timeout=timeout)
        _, tar_err = tar_proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        invalidate_ssh_url(instance_id)
        raise RuntimeError(f"ssh push {instance_id} timed out after {timeout}s") from None

    if tar_proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        raise RuntimeError(
            f"tar pack failed ({tar_proc.returncode}): {tar_err.decode(errors='replace').strip()}"
        )
    if ssh_proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        err_text = ssh_err.decode(errors="replace").strip()
        raise RuntimeError(f"ssh push {instance_id} failed: {err_text or f'exit {ssh_proc.returncode}'}")


def ssh_push_bytes(
    instance_id: int,
    remote_path: str,
    data: bytes,
    *,
    mode: int = 0o600,
    timeout: int = 60,
) -> None:
    """Write bytes to a remote file via SSH stdin (token-safe — not in argv)."""
    identity, user, host, port = _ssh_connection(instance_id)
    quoted = shlex.quote(remote_path)
    remote_cmd = f"cat > {quoted} && chmod {mode:o} {quoted}"
    ssh_cmd = _ssh_base_cmd(str(identity), user, host, port, remote_cmd)

    print(f"Push (ssh) bytes -> instance {instance_id}:{remote_path}")
    try:
        proc = subprocess.run(
            ssh_cmd,
            input=data,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        invalidate_ssh_url(instance_id)
        raise RuntimeError(f"ssh push bytes {instance_id} timed out after {timeout}s") from None

    if proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        raw = proc.stderr or proc.stdout
        if isinstance(raw, bytes):
            err = raw.decode(errors="replace").strip()
        else:
            err = (raw or f"exit {proc.returncode}").strip()
        raise RuntimeError(f"ssh push bytes {instance_id} failed: {err}")


def ssh_pull_dir(
    instance_id: int,
    remote_dir: str,
    local_dir: Path,
    *,
    timeout: int = 600,
    required: bool = True,
) -> None:
    """Pull a remote directory tree via tar over SSH."""
    local_path = local_dir.resolve()
    local_path.mkdir(parents=True, exist_ok=True)

    identity, user, host, port = _ssh_connection(instance_id)
    remote = remote_dir.rstrip("/")
    if required:
        remote_cmd = (
            f"test -d {shlex.quote(remote)} && "
            f"tar czf - -C {shlex.quote(remote)} ."
        )
    else:
        remote_cmd = (
            f"if test -d {shlex.quote(remote)}; then "
            f"tar czf - -C {shlex.quote(remote)} .; fi"
        )
    ssh_cmd = _ssh_base_cmd(str(identity), user, host, port, remote_cmd)

    print(f"Pull (ssh) instance {instance_id}:{remote}/ -> {local_path}/")

    try:
        ssh_proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tar_proc = subprocess.Popen(
            ["tar", "xzf", "-", "-C", str(local_path)],
            stdin=ssh_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if ssh_proc.stdout is not None:
            ssh_proc.stdout.close()
        _, tar_err = tar_proc.communicate(timeout=timeout)
        _, ssh_err = ssh_proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        invalidate_ssh_url(instance_id)
        raise RuntimeError(f"ssh pull {instance_id} timed out after {timeout}s") from None

    if ssh_proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        err_text = ssh_err.decode(errors="replace").strip()
        raise RuntimeError(f"ssh pull {instance_id} failed: {err_text or f'exit {ssh_proc.returncode}'}")
    if tar_proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        raise RuntimeError(
            f"tar unpack failed ({tar_proc.returncode}): "
            f"{tar_err.decode(errors='replace').strip()}"
        )


def ssh_pull_file(
    instance_id: int,
    remote_file: str,
    local_file: Path,
    *,
    timeout: int = 120,
    required: bool = True,
) -> None:
    """Pull a single remote file over SSH."""
    local_path = local_file.resolve()
    local_path.parent.mkdir(parents=True, exist_ok=True)

    identity, user, host, port = _ssh_connection(instance_id)
    quoted = shlex.quote(remote_file)
    if required:
        remote_cmd = f"test -f {quoted} && cat {quoted}"
    else:
        remote_cmd = f"if test -f {quoted}; then cat {quoted}; fi"

    print(f"Pull (ssh) instance {instance_id}:{remote_file} -> {local_path}")

    ssh_cmd = _ssh_base_cmd(str(identity), user, host, port, remote_cmd)
    try:
        proc = subprocess.run(
            ssh_cmd,
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        invalidate_ssh_url(instance_id)
        raise RuntimeError(f"ssh pull file {instance_id} timed out after {timeout}s") from None

    if proc.returncode != 0:
        invalidate_ssh_url(instance_id)
        err_raw = proc.stderr or proc.stdout
        if isinstance(err_raw, bytes):
            err = err_raw.decode(errors="replace").strip()
        else:
            err = (err_raw or f"ssh exit {proc.returncode}").strip()
        raise RuntimeError(f"ssh pull file {instance_id} failed: {err}")

    if not proc.stdout and required:
        raise RuntimeError(f"ssh pull file {instance_id}: empty output for {remote_file}")

    local_path.write_bytes(proc.stdout)


def verify_harness(instance_id: int, *, timeout: int = 60) -> None:
    """Fail closed if bakeoff harness files are missing after push."""
    cmd = (
        f"test -f {shlex.quote(HARNESS_START_SCRIPT)} && "
        f"test -f {shlex.quote(HARNESS_RUN_MATRIX)} && echo verified"
    )
    ok, out, err = ssh_probe(instance_id, cmd, timeout=timeout)
    if not ok or out.strip() != "verified":
        raise RuntimeError(
            f"harness verify {instance_id} failed: harness files missing under {HARNESS_ROOT}"
            + (f" ({err})" if err else "")
        )
    print(f"  Harness verified on instance {instance_id}: start_matrix.sh + run_matrix.py")


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
