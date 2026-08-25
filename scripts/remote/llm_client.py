#!/usr/bin/env python3
"""vLLM / llama.cpp client for agent benchmarks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

VLLM_PORT = int(os.environ.get("VLLM_PORT", "8000"))
VLLM_URL = f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions"
LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "8080"))
LLAMA_URL = f"http://127.0.0.1:{LLAMA_PORT}/v1/chat/completions"
LLAMA_BIN = os.environ.get("LLAMA_SERVER_BIN", "llama-server")
VLLM_LOG = Path("/workspace/bakeoff/vllm.log")
LLAMA_LOG = Path("/workspace/bakeoff/llama.log")

_vllm_model: str | None = None
_llama_model: str | None = None


def llm_extra_args(runtime: str, gpu_count: int) -> dict[str, list[str] | None]:
    """Build runtime-specific multi-GPU flags for 2-GPU SKUs."""
    if gpu_count < 2:
        return {"vllm": None, "llama": None}
    if runtime == "vllm":
        return {"vllm": ["--tensor-parallel-size", str(gpu_count)], "llama": None}
    if runtime == "llama_cpp":
        split = ",".join(["1"] * gpu_count)
        return {
            "vllm": None,
            "llama": ["--split-mode", "layer", "--tensor-split", split],
        }
    return {"vllm": None, "llama": None}


def _service_log_tail(path: Path, n: int = 20) -> str:
    if not path.is_file():
        return f"(no {path.name})"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:]) if lines else f"(empty {path.name})"
    except OSError as exc:
        return f"(could not read {path.name}: {exc})"


def vllm_running() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{VLLM_PORT}/health", timeout=2)
        return True
    except Exception:
        return False


def llama_running() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2)
        return True
    except Exception:
        return False


def start_vllm(model: str, extra_args: list[str] | None = None) -> bool:
    global _vllm_model
    if vllm_running() and _vllm_model == model:
        return True
    if not shutil.which("vllm"):
        return False
    if vllm_running():
        return True
    cmd = [
        "vllm",
        "serve",
        model,
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
        "--trust-remote-code",
    ]
    if extra_args:
        cmd.extend(extra_args)
    VLLM_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fh = VLLM_LOG.open("a", encoding="utf-8")
    subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    for _ in range(120):
        if vllm_running():
            _vllm_model = model
            return True
        time.sleep(2)
    return False


def start_llama_server(gguf_path: str | Path, extra_args: list[str] | None = None) -> bool:
    global _llama_model
    path = Path(gguf_path)
    if not path.exists():
        return False
    if llama_running() and _llama_model == str(path):
        return True
    if not shutil.which(LLAMA_BIN):
        return False
    cmd = [
        LLAMA_BIN,
        "--model",
        str(path),
        "--host",
        "0.0.0.0",
        "--port",
        str(LLAMA_PORT),
        "--ctx-size",
        "8192",
    ]
    if extra_args:
        cmd.extend(extra_args)
    LLAMA_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_fh = LLAMA_LOG.open("a", encoding="utf-8")
    subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    for _ in range(90):
        if llama_running():
            _llama_model = str(path)
            return True
        time.sleep(2)
    return False


def chat_openai(url: str, model: str, system: str, user: str, max_tokens: int = 128) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": True,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    ttft: float | None = None
    content_parts: list[str] = []
    out_toks = 0

    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content") or ""
            if text and ttft is None:
                ttft = time.perf_counter() - t0
            content_parts.append(text)
            usage = chunk.get("usage")
            if usage:
                out_toks = usage.get("completion_tokens", out_toks)

    elapsed = time.perf_counter() - t0
    content = "".join(content_parts)
    if not out_toks:
        out_toks = max(1, len(content.split()))
    decode_tps = out_toks / elapsed if elapsed > 0 else 0
    return {
        "wall_sec": round(elapsed, 3),
        "ttft_ms": round((ttft or elapsed) * 1000, 1),
        "prefill_tokens": len(user.split()),
        "output_tokens": out_toks,
        "decode_tps": round(decode_tps, 2),
        "content_len": len(content),
        "content": content,
        "status": "native",
        "mode": "openai_stream",
    }


def _error_response(runtime: str, note: str, log_path: Path | None = None) -> dict:
    detail = note
    if log_path is not None:
        detail = f"{note}\n{_service_log_tail(log_path)}"
    return {
        "pass": False,
        "status": "error",
        "mode": f"{runtime}_error",
        "decode_tps": 0,
        "output_tokens": 0,
        "note": detail,
        "error": note,
    }


def run_llm_job(
    runtime: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 128,
    fail_fast: bool = False,
    *,
    gguf_path: str | Path | None = None,
    gpu_count: int = 1,
    vllm_extra_args: list[str] | None = None,
    llama_extra_args: list[str] | None = None,
) -> dict:
    if fail_fast:
        return {"pass": False, "status": "no", "error": "fail-fast: model does not fit SKU"}

    if vllm_extra_args is None and llama_extra_args is None and gpu_count >= 2:
        extras = llm_extra_args(runtime, gpu_count)
        vllm_extra_args = extras.get("vllm")
        llama_extra_args = extras.get("llama")

    if runtime == "vllm":
        if start_vllm(model, vllm_extra_args) and vllm_running():
            return chat_openai(VLLM_URL, model, system, user, max_tokens)
        return _error_response(
            "vllm",
            "vLLM server did not start — install vllm on instance for real metrics",
            VLLM_LOG,
        )

    if runtime == "llama_cpp":
        if gguf_path and start_llama_server(gguf_path, llama_extra_args) and llama_running():
            return chat_openai(LLAMA_URL, model, system, user, max_tokens)
        return _error_response(
            "llama_cpp",
            "llama-server not running — prefetch GGUF and install llama.cpp",
            LLAMA_LOG,
        )

    return {"pass": False, "status": "error", "error": f"unknown runtime {runtime}"}
