#!/usr/bin/env python3
"""Shared Vast instance launch helpers."""

from __future__ import annotations

import os
from typing import Any

from lib.sku_offers import validate_offer
from lib.vast import vastai

DISK_GB = int(os.environ.get("DISK_GB", "400"))


def resolve_image(sku_id: str, offer: dict[str, Any], sku_meta: dict[str, Any]) -> str:
    arch = sku_meta.get("arch") or offer.get("cpu_arch") or "x86_64"
    image = sku_meta.get("image") or offer.get("image")
    if not image:
        if arch == "aarch64":
            raise SystemExit(
                f"No container image for aarch64 SKU {sku_id} — "
                "re-run 01_search_offers.py or set image in matrix.yaml"
            )
        image = "vastai/pytorch:@vastai-automatic-tag"
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
    env_str = f"-e HF_TOKEN={hf} -e TZ={tz} -e BAKEOFF_SKU={sku_id}"

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
