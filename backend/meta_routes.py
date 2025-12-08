# file: backend/meta_routes.py
from __future__ import annotations

import glob
import os
from typing import Any, Dict, List

from fastapi import APIRouter

from .config import _p, RETAIL_GLOB, WHOLESALE_GLOB
from .images import IMG_EXTS
from .loaders import load_specs
from .spk_utils import fuel_to_code

router = APIRouter(tags=["meta"])

IMG_NEED_DIR = os.path.abspath("./public/kebutuhan")
IMG_NEED_BASE = "/kebutuhan"

DEFAULT_NEEDS = [
    {"key": "perkotaan", "label": "Perkotaan", "image": f"{IMG_NEED_BASE}/perkotaan.png"},
    {"key": "keluarga", "label": "Keluarga", "image": f"{IMG_NEED_BASE}/keluarga.png"},
    {"key": "fun", "label": "Fun to Drive", "image": f"{IMG_NEED_BASE}/fun.png"},
    {"key": "offroad", "label": "Offroad", "image": f"{IMG_NEED_BASE}/offroad.png"},
    {
        "key": "perjalanan_jauh",
        "label": "Perjalanan Jauh",
        "image": f"{IMG_NEED_BASE}/perjalanan_jauh.png",
    },
    {"key": "niaga", "label": "Niaga", "image": f"{IMG_NEED_BASE}/niaga.png"},
]

NEEDS_DIR_CANDIDATES = [
    IMG_NEED_DIR,
    os.path.abspath("../public/kebutuhan"),
    os.path.abspath("../../public/kebutuhan"),
]


def _collect_needs_from_fs() -> List[Dict[str, Any]]:
    for d in NEEDS_DIR_CANDIDATES:
        if not os.path.isdir(d):
            continue
        items: List[Dict[str, Any]] = []
        for n in os.listdir(d):
            stem, ext = os.path.splitext(n)
            if ext.lower() in IMG_EXTS:
                items.append(
                    {
                        "key": stem.lower(),
                        "label": stem.replace("_", " ").title(),
                        "image": f"{IMG_NEED_BASE}/{n}",
                    }
                )
        if items:
            print(f"[meta] kebutuhan: pakai dir {d}, count={len(items)}")
            return sorted(items, key=lambda x: x["label"])
    print("[meta] kebutuhan: folder tidak ditemukan/kosong, pakai DEFAULT_NEEDS")
    return DEFAULT_NEEDS


@router.get("/meta")
def meta():
    specs = load_specs()
    brands = sorted(specs["brand"].dropna().astype(str).unique().tolist())

    FUEL_LABEL_SIMPLE: Dict[str, str] = {
        "g": "Bensin",
        "d": "Diesel",
        "h": "Hybrid",
        "p": "PHEV",
        "e": "BEV",
    }

    if "fuel" in specs.columns:
        codes = [fuel_to_code(x) for x in specs["fuel"].dropna().astype(str).tolist()]
        codes = [c for c in codes if c in FUEL_LABEL_SIMPLE]
        order = ["Bensin", "Diesel", "Hybrid", "PHEV", "BEV"]
        fuels_strings = sorted(
            {FUEL_LABEL_SIMPLE[c] for c in codes},
            key=lambda x: order.index(x) if x in order else 99,
        )
    else:
        fuels_strings = ["Bensin", "Diesel", "Hybrid", "PHEV", "BEV"]

    needs = _collect_needs_from_fs()
    have_retail = bool(glob.glob(_p(RETAIL_GLOB)))
    have_wh = bool(glob.glob(_p(WHOLESALE_GLOB)))

    return {
        "brands": brands,
        "fuels": fuels_strings,
        "needs": needs,
        "data_ready": {
            "specs": True,
            "retail": have_retail,
            "wholesale": have_wh,
        },
    }
