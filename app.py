# file: app.py
import os
import glob
import json
import time
import numpy as np
import pandas as pd

from dotenv import load_dotenv

load_dotenv()  

from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from images import find_best_image_url, IMG_BASE_REL, reload_images, IMG_EXTS
from schemas import RecommendRequest
from loaders import (
    load_specs,
    load_retail_brand_multi,
    load_wholesale_model_multi,
    _p,
    RETAIL_GLOB,
    WHOLESALE_GLOB,
)
from spk import build_master, rank_candidates, fuel_to_code

# ==== IMPORT BARU UNTUK CHAT PINTAR ====
from recommendation_state import set_last_recommendation
from chat_schemas import ChatRequest, ChatReply
from smart_chat import build_smart_reply
from chatbot import (
    set_last_recommendation,
)


app = FastAPI(title="Rekomendasi Mobil API (JSON)", version="1.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reindeks gambar saat start
print(f"[images] reindexed:", reload_images())


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


# =====================================================================
#                           META / KEBUTUHAN
# =====================================================================
IMG_NEED_DIR = os.path.abspath("./public/kebutuhan")
IMG_NEED_BASE = "/kebutuhan"

DEFAULT_NEEDS = [
    {"key": "perkotaan", "label": "Perkotaan", "image": f"{IMG_NEED_BASE}/perkotaan.png"},
    {"key": "keluarga", "label": "Keluarga", "image": f"{IMG_NEED_BASE}/keluarga.png"},
    {"key": "fun", "label": "Fun to Drive", "image": f"{IMG_NEED_BASE}/fun.png"},
    {"key": "offroad", "label": "Offroad", "image": f"{IMG_NEED_BASE}/offroad.png"},
    {"key": "perjalanan_jauh", "label": "Perjalanan Jauh", "image": f"{IMG_NEED_BASE}/perjalanan_jauh.png"},
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


FUEL_LABEL_MAP = {
    "g": "Bensin",
    "d": "Diesel",
    "h": "Hybrid (HEV)",
    "p": "PHEV",
    "e": "BEV",
    "o": "Lainnya",
}

# --- Normalisasi alias kebutuhan di backend (kanonik) ---
CANON_NEED = {
    # long trip
    "perjalanan_jauh": "perjalanan_jauh",
    "long trip": "perjalanan_jauh",
    "long_trip": "perjalanan_jauh",
    "longtrip": "perjalanan_jauh",
    "trip jauh": "perjalanan_jauh",
    # short trip / city
    "perkotaan": "perkotaan",
    "short trip": "perkotaan",
    "short_trip": "perkotaan",
    "shorttrip": "perkotaan",
    "city": "perkotaan",
    "urban": "perkotaan",
    # fun to drive
    "fun": "fun",
    "fun to drive": "fun",
    "fun_to_drive": "fun",
    "fun2drive": "fun",
    "sporty": "fun",
    # offroad
    "offroad": "offroad",
    "off road": "offroad",
    "off_road": "offroad",
    # niaga
    "niaga": "niaga",
    "usaha": "niaga",
    "commercial": "niaga",
    # keluarga
    "keluarga": "keluarga",
    "family": "keluarga",
}
NEED_SET = {"perjalanan_jauh", "perkotaan", "fun", "offroad", "niaga", "keluarga"}


def canon_need_list(raw):
    if not raw:
        return []
    out, seen = [], set()
    for n in raw:
        k = CANON_NEED.get(str(n).strip().lower(), str(n).strip().lower())
        if k in NEED_SET and k not in seen:
            out.append(k)
            seen.add(k)
    return out


@app.get("/meta")
def meta():
    specs = load_specs()
    brands = sorted(specs["brand"].dropna().astype(str).unique().tolist())

    FUEL_LABEL_SIMPLE = {
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
        "data_ready": {"specs": True, "retail": have_retail, "wholesale": have_wh},
    }


# =====================================================================
#                     UTIL SERIALISASI DATAFRAME
# =====================================================================
def df_to_items(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Ubah DataFrame ke list[dict] JSON-safe (tanpa NaN/Inf & tanpa numpy scalar)."""
    if df is None or df.empty:
        return []
    safe = df.replace([np.inf, -np.inf], np.nan)
    safe = safe.where(pd.notnull(safe), None)
    return json.loads(safe.to_json(orient="records"))


# =====================================================================
#                        ENDPOINT REKOMENDASI
# =====================================================================
@app.post("/recommendations")
def recommendations(req: RecommendRequest):
    t0 = time.perf_counter()
    specs = load_specs()

    try:
        retail_share = load_retail_brand_multi(2020, 2025)
    except FileNotFoundError:
        brand_keys = (
            specs["brand"].astype(str).str.strip().str.upper().unique().tolist()
        )
        retail_share = pd.DataFrame(
            {"brand_key": brand_keys, "brand_share_ratio": [0.0] * len(brand_keys)}
        )

    try:
        wholesale_feats = load_wholesale_model_multi(2020, 2025)
    except FileNotFoundError:
        wholesale_feats = pd.DataFrame(
            columns=["brand_key", "model_key", "wh_avg_window", "trend_3v3"]
        )

    master = build_master(specs, wholesale_feats, retail_share, pred_years=0.0)

    # Normalisasi input filter
    filters: Dict[str, Any] = {}
    if getattr(req, "filters", None) is not None:
        filters = req.filters.dict() if hasattr(req.filters, "dict") else dict(req.filters)

    # Konversi fuels (label/kode campur) → kode ['g','d','h','p','e']
    fuels_in = filters.get("fuels")
    if fuels_in:
        filters["fuels"] = [
            c for c in {fuel_to_code(v) for v in fuels_in} if c in {"g", "d", "h", "p", "e"}
        ]

    # Normalisasi needs ke kanonik
    needs = canon_need_list(req.needs or []) if getattr(req, "needs", None) is not None else []

    topn = int(getattr(req, "topn", 6) or 6)
    budget = float(req.budget)

    # Ranking
    cand = rank_candidates(master, budget, filters, needs, topn)
    if not isinstance(cand, pd.DataFrame):
        # kosongkan state kalau terjadi error
        set_last_recommendation(None)
        raise HTTPException(
            status_code=500,
            detail="rank_candidates mengembalikan nilai tak terduga",
        )

    if cand.empty:
        t1 = time.perf_counter()
        print(f"[REC] empty result — load+rank={t1 - t0:.3f}s")
        # kosongkan state chatbot
        set_last_recommendation(None)
        return {"count": 0, "items": [], "needs": needs}

    # --- Ambil brand & model yang robust ---
    brand_s = cand.get("brand", pd.Series([""] * len(cand), index=cand.index)).astype(str).str.strip()

    base = pd.Series([""] * len(cand), index=cand.index, dtype="object")
    model_s = base.copy()
    for c in ["model", "type model", "type_model"]:
        if c in cand.columns:
            s = cand[c].astype(str)
            model_s = model_s.mask((model_s.isna()) | (model_s.eq("")), s)
    model_s = model_s.fillna("").str.strip()

    # --- Resolver gambar aman ---
    def _safe_url(b: str, m: str) -> str:
        try:
            u = find_best_image_url(b, m)
            return u or f"{IMG_BASE_REL}/default.jpg"
        except Exception:
            return f"{IMG_BASE_REL}/default.jpg"

    urls = [_safe_url(b, m) for b, m in zip(brand_s, model_s)]
    cand["image_url"] = pd.Series(urls, index=cand.index, dtype="object")
    cand["image"] = cand["image_url"]

    for b, m, u in list(zip(brand_s, model_s, urls))[:3]:
        print("[img]", b, "|", m, "->", u)

    # Kolom minimal yang wajib ada (untuk front-end sekarang)
    display = [
        "rank",
        "points",
        "brand",
        "model",
        "price",
        "fit_score",
        "fuel",
        "fuel_code",
        "trans",
        "seats",
        "cc_kwh",
        "alasan",
        "image_url",
        "image",
    ]
    for col in display:
        if col not in cand.columns:
            cand[col] = np.nan

    # Tambah label bbm manusiawi
    cand["fuel_code"] = cand["fuel_code"].astype(str).str.lower()
    cand["fuel_label"] = cand["fuel_code"].map(FUEL_LABEL_MAP).fillna("Lainnya")

    # Format angka
    cand["price"] = pd.to_numeric(cand["price"], errors="coerce").round(0)
    cand["fit_score"] = pd.to_numeric(cand["fit_score"], errors="coerce").round(4)

    # Kirim semua kolom (supaya chat bisa baca fitur lengkap)
    items = df_to_items(cand)

    # Siapkan payload lengkap untuk disimpan di state chatbot
    payload = {
        "timestamp": time.time(),
        "needs": needs,
        "budget": budget,
        "filters": filters,
        "count": len(items),
        "items": items,
    }
    set_last_recommendation(payload)

    t1 = time.perf_counter()
    print(f"[REC] rows_master={len(master)} rows_out={len(items)} load+rank={t1 - t0:.3f}s")

    return {
        "count": len(items),
        "items": items,
        "needs": needs,
    }


# =====================================================================
#                       ENDPOINT CHAT PINTAR (SMART)
# =====================================================================
@app.post("/chat", response_model=ChatReply)
def chat_endpoint(req: ChatRequest) -> ChatReply:
    """
    Satu endpoint chat pintar.
    Di dalamnya nanti akan milih:
    - mode jelaskan rekomendasi
    - atau simulasi what-if
    berdasarkan isi pesan.
    """
    return build_smart_reply(req.message)


# =====================================================================
#                           IMAGES ENDPOINT
# =====================================================================
@app.post("/images/reload")
def images_reload():
    cnt = reload_images()
    return {"ok": True, "count": int(cnt)}
