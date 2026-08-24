#!/usr/bin/env python3
"""Shared Vast instance launch helpers."""

from __future__ import annotations

import os
from typing import Any

from lib.sku_offers import validate_offer
from lib.vast import vastai

DISK_GB = int(os.environ.get("DISK_GB", "400"))
DEFAULT_IMAGE = "vastai/pytorch:@vastai-automatic-tag"


def resolve_image(sku_id: str, offer: dict[str, Any], sku_meta: dict[str, Any]) -> str:
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
    image = resolve_image(sku_id, offer, sku_meta)

    hf = os.environ.get("HF_TOKEN", "")
    tz = os.environ.get("TZ", "Australia/Melbourne")
    num_gpus = sku_meta.get("num_gpus", 1)
    env_str = (
        f"-e HF_TOKEN={hf} -e TZ={tz} -e BAKEOFF_SKU={sku_id} "
        f"-e BAKEOFF_GPU_COUNT={num_gpus}"
    )

    print(f"Launching {sku_id} offer={offer_id} label={label} image={image}")
    result = vastai(
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
        check=False,
    )
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
        }
    print(f"  FAILED: {result}")
    return None


def launch_first_valid(
    sku_id: str,
    candidates: list[dict[str, Any]],
    sku_meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[Any]]:
    for i, offer in enumerate(candidates):
        err = validate_offer(sku_id, offer, sku_meta)
        if err:
            print(f"  skip candidate {offer.get('id')}: {err}")
            continue
        rec = launch_one(sku_id, offer, sku_meta)
        if rec:
            backup_ids = [c["id"] for c in candidates[i + 1 : i + 4]]
            return rec, backup_ids
    return None, []
