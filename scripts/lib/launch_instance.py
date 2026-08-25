#!/usr/bin/env python3
"""Shared Vast instance launch helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lib.sku_offers import validate_offer
from lib.transport import default_git_ref, default_git_url, use_onstart_transport
from lib.vast import hf_token, vastai

DISK_GB = int(os.environ.get("DISK_GB", "400"))
DEFAULT_IMAGE = "vastai/pytorch:@vastai-automatic-tag"
BOOTSTRAP_SCRIPT = Path(__file__).resolve().parent / "onstart_bootstrap.sh"


def backup_offer_ids(candidates: list[dict[str, Any]], offer_id: Any | None) -> list[Any]:
    out: list[Any] = []
    for cand in candidates:
        cid = cand.get("id")
        if not cid or cid == offer_id:
            continue
        out.append(cid)
        if len(out) >= 3:
            break
    return out


def resolve_image(offer: dict[str, Any], sku_meta: dict[str, Any]) -> str:
    image = sku_meta.get("image") or offer.get("image")
    if not image:
        image = DEFAULT_IMAGE
    return image


def launch_one(sku_id: str, offer: dict[str, Any], sku_meta: dict[str, Any]) -> dict[str, Any] | None:
    err = validate_offer(sku_id, offer, sku_meta)
    if err:
        print(f"  REFUSE launch {sku_id} offer={offer.get('id')}: {err}")
        return None

    offer_id = offer["id"]
    label = sku_meta.get("label") or f"bakeoff-{sku_id}"
    image = resolve_image(offer, sku_meta)

    hf = hf_token()
    if not hf:
        print(f"  REFUSE launch {sku_id} offer={offer.get('id')}: HF_TOKEN empty in .env")
        return None

    tz = os.environ.get("TZ", "Australia/Melbourne")
    num_gpus = sku_meta.get("num_gpus", 1)
    git_url = default_git_url()
    git_ref = default_git_ref()
    hf_results = os.environ.get("HF_RESULTS_REPO", "").strip()

    env_str = (
        f"-e HF_TOKEN={hf} -e HUGGING_FACE_HUB_TOKEN={hf} -e TZ={tz} "
        f"-e BAKEOFF_SKU={sku_id} -e BAKEOFF_GPU_COUNT={num_gpus} "
        f"-e BAKEOFF_GIT_URL={git_url} -e BAKEOFF_GIT_REF={git_ref}"
    )
    if hf_results:
        env_str += f" -e HF_RESULTS_REPO={hf_results}"

    args: list[str] = [
        "create",
        "instance",
        str(offer_id),
        "--image",
        image,
        "--disk",
        str(DISK_GB),
        "--ssh",
        "--direct",
        "--label",
        label,
        "--env",
        env_str,
    ]
    if use_onstart_transport():
        if not BOOTSTRAP_SCRIPT.is_file():
            print(f"  REFUSE launch: missing bootstrap {BOOTSTRAP_SCRIPT}")
            return None
        args.extend(["--onstart", str(BOOTSTRAP_SCRIPT)])
        print(f"Launching {sku_id} offer={offer_id} label={label} image={image} (onstart bootstrap)")
    else:
        print(f"Launching {sku_id} offer={offer_id} label={label} image={image}")

    result = vastai(*args, check=False)
    if isinstance(result, dict) and result.get("success"):
        iid = result.get("new_contract") or result.get("id")
        print(f"  -> instance id {iid}")
        return {
            "sku_id": sku_id,
            "instance_id": iid,
            "offer_id": offer_id,
            "label": label,
            "image": image,
            "dph_total": offer.get("dph_total"),
            "gpu_name": offer.get("gpu_name"),
            "reliability": offer.get("reliability"),
            "status": "created",
            "transport": "onstart" if use_onstart_transport() else "ssh",
        }
    if isinstance(result, dict):
        msg = result.get("msg") or result.get("message")
        if msg:
            print(f"  FAILED: {msg}")
        else:
            print(f"  FAILED: {result}")
    else:
        print(f"  FAILED: {result or 'no response from vastai'}")
    return None


def launch_first_valid(
    sku_id: str,
    candidates: list[dict[str, Any]],
    sku_meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[Any]]:
    for offer in candidates:
        err = validate_offer(sku_id, offer, sku_meta)
        if err:
            print(f"  skip candidate {offer.get('id')}: {err}")
            continue
        rec = launch_one(sku_id, offer, sku_meta)
        if rec:
            return rec, backup_offer_ids(candidates, offer.get("id"))
    return None, []
