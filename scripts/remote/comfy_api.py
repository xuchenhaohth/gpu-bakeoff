#!/usr/bin/env python3
"""ComfyUI HTTP API client."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

COMFY_PORT = int(__import__("os").environ.get("COMFY_PORT", "8188"))
COMFY_URL = f"http://127.0.0.1:{COMFY_PORT}"


def _post(path: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{COMFY_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _get(path: str, timeout: int = 30) -> Any:
    with urllib.request.urlopen(f"{COMFY_URL}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def server_up() -> bool:
    try:
        urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=2)
        return True
    except Exception:
        return False


def queue_prompt(workflow: dict, client_id: str | None = None) -> str:
    client_id = client_id or str(uuid.uuid4())
    result = _post("/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI /prompt failed: {result}")
    return prompt_id


def get_history(prompt_id: str) -> dict:
    return _get(f"/history/{prompt_id}")


def wait_for_prompt(prompt_id: str, timeout_sec: float = 900, poll_sec: float = 2.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        history = get_history(prompt_id)
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("completed"):
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI job failed: {status.get('messages')}")
        time.sleep(poll_sec)
    raise TimeoutError(f"ComfyUI prompt {prompt_id} timed out after {timeout_sec}s")


def extract_output_paths(history_entry: dict) -> list[str]:
    paths: list[str] = []
    outputs = history_entry.get("outputs", {})
    for node_out in outputs.values():
        for img in node_out.get("images", []):
            filename = img.get("filename")
            subfolder = img.get("subfolder", "")
            if filename:
                paths.append(f"{subfolder}/{filename}".strip("/"))
        for vid in node_out.get("gifs", []) + node_out.get("videos", []):
            filename = vid.get("filename")
            if filename:
                paths.append(filename)
    return paths
