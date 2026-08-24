#!/usr/bin/env python3
"""Load ComfyUI workflow JSON and inject runtime parameters."""

from __future__ import annotations

import copy
import json

from paths import WORKFLOWS_DIR


def load_workflow(model_key: str) -> dict:
    path = WORKFLOWS_DIR / f"{model_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"No workflow template: {path}")
    return json.loads(path.read_text())


def _parse_resolution(resolution: str) -> tuple[int, int]:
    if "x" in resolution.lower():
        w, h = resolution.lower().split("x", 1)
        return int(w), int(h)
    size = int(resolution)
    return size, size


def inject_params(
    workflow: dict,
    *,
    prompt: str,
    seed: int,
    resolution: str = "1024x1024",
    checkpoint: str | None = None,
    negative: str = "",
) -> dict:
    wf = copy.deepcopy(workflow)
    width, height = _parse_resolution(resolution)
    positive_set = False

    for node in wf.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")

        if class_type == "KSampler" and "seed" in inputs:
            inputs["seed"] = seed

        if class_type == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height

        if class_type in ("CheckpointLoaderSimple", "UNETLoader", "DualCLIPLoader"):
            if checkpoint and "ckpt_name" in inputs:
                inputs["ckpt_name"] = checkpoint
            if checkpoint and "unet_name" in inputs:
                inputs["unet_name"] = checkpoint

        if class_type == "CLIPTextEncode" and "text" in inputs:
            if not positive_set:
                inputs["text"] = prompt
                positive_set = True
            else:
                inputs["text"] = negative

        if class_type in ("LTXVImgToVideo", "VHS_VideoCombine") and "text" in inputs:
            inputs["text"] = prompt

    return wf
