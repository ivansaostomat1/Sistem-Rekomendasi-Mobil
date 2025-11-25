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

# ==== IMPORT UNTUK CHAT PINTAR ====
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
#                 HINT KETIKA TIDAK ADA REKOMENDASI
# =====================================================================
def compute_empty_hint(
    master: pd.DataFrame,
    budget: float,
    filters: Dict[str, Any],
    needs: List[str],
) -> Dict[str, Any]:
    """
    Dipakai ketika rank_candidates mengembalikan DataFrame kosong.
    Tujuan: kasih saran lebih rinci:
    - filter mana saja yang benar-benar aktif
    - kebutuhan mana yang tidak bisa dipenuhi (strict & versi longgar)
    - kisaran budget yang lebih realistis
    """
    try:
        df = master.copy()

        # ---------- helper kolom aman ----------
        def num_col(name: str) -> pd.Series:
            """Ambil kolom numerik; kalau tidak ada → NaN semua."""
            if name in df.columns:
                return pd.to_numeric(df[name], errors="coerce")
            return pd.Series(np.nan, index=df.index, dtype="float64")

        def cat_col(name: str, default: str = "") -> pd.Series:
            """Ambil kolom kategorikal; kalau tidak ada → string default."""
            if name in df.columns:
                return df[name].astype(str)
            return pd.Series([default] * len(df), index=df.index, dtype="object")

        # Harga termurah setelah filter dasar (global dalam konteks filter)
        prices_all = num_col("price")
        prices_all_valid = prices_all[prices_all.notna()]
        min_overall = float(prices_all_valid.min()) if not prices_all_valid.empty else None

        # ---------- Terapkan filter dasar TANPA batas budget ----------
        filters_summary: Dict[str, Any] = {
            "brand": None,
            "trans_choice": None,
            "fuels": None,
        }

        # Brand
        brand = filters.get("brand")
        if brand and "brand" in df.columns:
            brand_str = str(brand).strip()
            filters_summary["brand"] = brand_str
            df = df[
                df["brand"].astype(str)
                .str.lower()
                .str.contains(brand_str.lower(), na=False)
            ]

        # Transmisi (approx, tidak pakai vector_match_trans biar simpel)
        trans_choice = filters.get("trans_choice")
        if trans_choice and "trans" in df.columns:
            tc_raw = str(trans_choice).strip()
            tc = tc_raw.lower()
            if tc not in {"all", "any", ""}:
                filters_summary["trans_choice"] = tc_raw
                df = df[df["trans"].astype(str).str.lower().str.contains(tc, na=False)]

        # Fuels (sudah dinormalisasi ke kode ['g','d','h','p','e'])
        fuels = filters.get("fuels")
        if fuels and "fuel_code" in df.columns:
            fuel_set = {str(c).lower() for c in fuels}
            filters_summary["fuels"] = sorted(fuel_set)
            df = df[df["fuel_code"].astype(str).str.lower().isin(fuel_set)]

        # Kalau setelah filter dasar saja sudah kosong → kombinasi filter-nya tidak ada di data
        if df.empty:
            return {
                "reason": "NO_MATCH_FILTERS",
                "message": "Tidak ada mobil di data yang cocok dengan kombinasi brand / transmisi / BBM saat ini.",
                "current_budget": float(budget),
                "min_price_overall": min_overall,
                "min_price_filtered": None,
                "max_price_allowed": None,
                "suggested_budget": None,
                "filters_summary": filters_summary,
                "needs_diag": [],
            }

        # ---------- Analisis harga setelah filter dasar ----------
        p = num_col("price")
        mask_price_valid = p.notna()
        p_valid = p[mask_price_valid]

        if p_valid.empty:
            return {
                "reason": "UNKNOWN",
                "message": "Sistem tidak menemukan informasi harga yang valid untuk kombinasi filter ini.",
                "current_budget": float(budget),
                "min_price_overall": min_overall,
                "min_price_filtered": None,
                "max_price_allowed": None,
                "suggested_budget": None,
                "filters_summary": filters_summary,
                "needs_diag": [],
            }

        min_price_filtered = float(p_valid.min())
        cap = float(budget * 1.15)  # batas harga yang dipertimbangkan ranker
        df_cap = df[mask_price_valid & (p <= cap)]

        # ---------- Analisis per-kebutuhan (diagnostik) ----------
        needs_diag: List[Dict[str, Any]] = []

        seg = cat_col("segmentasi").str.lower()
        awd = num_col("awd_flag").fillna(0.0)
        seats = num_col("seats")
        length = num_col("length_mm")
        width = num_col("width_mm")
        weight = num_col("vehicle_weight_kg")
        wb = num_col("wheelbase_mm")
        cc = num_col("cc_kwh_num")
        fuel_code = (
            df["fuel_code"].astype(str).str.lower()
            if "fuel_code" in df.columns
            else pd.Series(["o"] * len(df), index=df.index, dtype="object")
        )

        def _q(series: pd.Series, q: float, default: float | None = None) -> float | None:
            s = pd.to_numeric(series, errors="coerce").dropna()
            if s.empty:
                return default
            return float(np.nanpercentile(s, q))

        len_p40 = _q(length, 40, None)
        wid_p40 = _q(width, 40, None)
        wgt_p50 = _q(weight, 50, None)
        wb_p70 = _q(wb, 70, None)

        def add_need_diag(
            need_key: str,
            mask_core: pd.Series,
            mask_loose: pd.Series | None = None,
        ):
            """Tambahkan entry diagnostik untuk satu kebutuhan.

            - mask_core  : definisi strict (sama seperti hard_constraints_filter/logic utama)
            - mask_loose : definisi longgar (contoh: SUV/pickup untuk offroad)
            """
            mask_core = mask_core.reindex(df.index).fillna(False)
            mask_all = mask_core & mask_price_valid

            total = int(mask_all.sum())
            if total > 0:
                p_all = p[mask_all]
                min_price_all = float(p_all.min())
            else:
                min_price_all = None

            mask_cap_local = mask_all & (p <= cap)
            under_cap = int(mask_cap_local.sum())
            if under_cap > 0:
                p_cap = p[mask_cap_local]
                min_price_under_cap = float(p_cap.min())
            else:
                min_price_under_cap = None

            total_loose = None
            min_price_loose = None
            if mask_loose is not None:
                ml = mask_loose.reindex(df.index).fillna(False) & mask_price_valid
                total_loose = int(ml.sum())
                if total_loose > 0:
                    min_price_loose = float(p[ml].min())

            needs_diag.append(
                {
                    "need": need_key,
                    "total": total,
                    "under_cap": under_cap,
                    "min_price_all": min_price_all,
                    "min_price_under_cap": min_price_under_cap,
                    # versi longgar
                    "total_loose": total_loose,
                    "min_price_loose": min_price_loose,
                }
            )

        need_set = set(needs or [])

        for need_key in need_set:
            if need_key == "offroad":
                # strict: AWD/4x4 atau SUV/pickup berat badan tertentu
                core = ((awd >= 0.5) | seg.str.contains(r"\b(suv|pickup|double\s*cabin|4x4|4wd)\b", regex=True, na=False)) \
           & (~seg.str.contains(r"\bsedan\b", regex=True, na=False))
                # longgar: semua SUV / crossover / pickup / double cabin
                offroad_loose_pat = r"\b(suv|crossover|pick\s*up|pickup|double\s*cab(?:in)?|4x4|4wd|dcab)\b"
                loose = seg.str.contains(offroad_loose_pat, regex=True, na=False)

                add_need_diag("offroad", core, loose)

            elif need_key == "keluarga":
                # strict: sama seperti hard constraint
                min_seats = 5 if "perkotaan" in need_set else 6
                core = seats >= min_seats

                # longgar: minimal 5 kursi
                loose = seats >= 5
                add_need_diag("keluarga", core, loose)

            elif need_key == "perkotaan":
                small = pd.Series(True, index=df.index)
                if len_p40 is not None:
                    small &= (length <= len_p40) | length.isna()
                if wid_p40 is not None:
                    small &= (width <= wid_p40) | width.isna()
                if wgt_p50 is not None:
                    small &= (weight <= wgt_p50) | weight.isna()

                efficient = fuel_code.isin({"h", "p", "e"}) | (cc <= 1500) | cc.isna()
                core = small & efficient

                # longgar: salah satu dari "kecil" atau "efisien"
                loose = small | efficient
                add_need_diag("perkotaan", core, loose)

            elif need_key == "perjalanan_jauh":
                if wb_p70 is not None:
                    long_wb = wb >= wb_p70
                else:
                    long_wb = pd.Series(False, index=df.index)

                diesel_or_efficient = (fuel_code == "d") | (cc <= 1500) | fuel_code.isin(
                    {"h", "p"}
                )
                core = long_wb | diesel_or_efficient

                # longgar: diesel ATAU wheelbase di atas median
                wb_med = _q(wb, 50, None)
                if wb_med is not None:
                    loose = (fuel_code == "d") | (wb >= wb_med)
                else:
                    loose = (fuel_code == "d")
                add_need_diag("perjalanan_jauh", core, loose)

            elif need_key == "niaga":
                niaga_pat = r"\b(pick\s*up|pickup|pu|box|blind\s*van|blindvan|niaga|light\s*truck|chassis|minibus)\b"
                core = seg.str.contains(niaga_pat, regex=True, na=False)
                loose = core.copy()  # di sini strict == loose
                add_need_diag("niaga", core, loose)

            elif need_key == "fun":
                # strict: cc>=1500 atau hybrid/PHEV/BEV (mirip hard constraints)
                core = (cc >= 1500) | fuel_code.isin({"h", "p", "e"})

                # longgar: cc >= 1300 atau hybrid/BEV (lebih banyak kandidat)
                loose = (cc >= 1300) | fuel_code.isin({"h", "p", "e"})
                add_need_diag("fun", core, loose)

        # ---------- Tentukan "reason" utama ----------
        need_total_zero_any = any(
            (d.get("total") or 0) == 0 for d in needs_diag
        ) if needs_diag else False

        need_under_cap_zero_any = any(
            (d.get("total") or 0) > 0 and (d.get("under_cap") or 0) == 0
            for d in needs_diag
        ) if needs_diag else False

        any_loose_available = any(
            (d.get("total") or 0) == 0 and (d.get("total_loose") or 0) > 0
            for d in needs_diag
        ) if needs_diag else False

        df_cap_empty = df_cap.empty

        reason = "CONSTRAINTS_TOO_STRICT"
        message = (
            "Budget dan filter dasar sebenarnya sudah cukup, tetapi kombinasi kebutuhan "
            "dan aturan sistem membuat semua kandidat gugur."
        )
        suggested_budget = None

        if needs and need_total_zero_any:
            if any_loose_available:
                reason = "NO_MATCH_NEEDS_BUT_LOOSE"
                message = (
                    "Secara definisi ketat, belum ada mobil di data yang benar-benar memenuhi "
                    "satu atau lebih kebutuhan yang dipilih. Namun, jika definisinya sedikit "
                    "dilonggarkan, ada beberapa mobil yang mendekati — lihat ringkasan di bawah."
                )
            else:
                reason = "NO_MATCH_NEEDS"
                message = (
                    "Tidak ada mobil di data yang memenuhi satu atau lebih kebutuhan yang dipilih."
                )
        elif needs and need_under_cap_zero_any:
            reason = "BUDGET_TOO_LOW_FOR_NEEDS"
            message = (
                "Budget saat ini belum cukup untuk memenuhi kebutuhan yang dipilih secara realistis."
            )
        elif df_cap_empty:
            reason = "BUDGET_TOO_LOW"
            message = (
                "Semua mobil yang cocok filter berada di atas kisaran harga yang dihitung dari "
                "budget kamu."
            )

        # ---------- Hitung budget minimal yang lebih realistis ----------
        step = 5_000_000  # dibulatkan ke atas per 5 juta

        if reason in {"BUDGET_TOO_LOW_FOR_NEEDS", "NO_MATCH_NEEDS_BUT_LOOSE"} and needs_diag:
            offending_prices = [
                d.get("min_price_all")
                for d in needs_diag
                if (d.get("total") or 0) > 0
                and (d.get("under_cap") or 0) == 0
                and d.get("min_price_all") is not None
            ]
            if offending_prices:
                min_offending = float(min(offending_prices))
                raw_min_budget = min_offending / 1.15
                suggested_budget = float(np.ceil(raw_min_budget / step) * step)
        elif reason == "BUDGET_TOO_LOW":
            raw_min_budget = min_price_filtered / 1.15
            suggested_budget = float(np.ceil(raw_min_budget / step) * step)

        return {
            "reason": reason,
            "message": message,
            "current_budget": float(budget),
            "min_price_overall": min_overall,
            "min_price_filtered": min_price_filtered,
            "max_price_allowed": cap,
            "suggested_budget": suggested_budget,
            "filters_summary": filters_summary,
            "needs_diag": needs_diag,
        }

    except Exception as e:
        print(f"[hint] error compute_empty_hint: {type(e).__name__}: {e}")
        return {
            "reason": "ERROR",
            "message": "Terjadi kendala saat menghitung saran. Coba ubah kriteria sedikit lalu jalankan ulang.",
            "current_budget": float(budget),
            "min_price_overall": None,
            "min_price_filtered": None,
            "max_price_allowed": None,
            "suggested_budget": None,
            "filters_summary": {},
            "needs_diag": [],
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

        # Hitung hint supaya front-end bisa kasih saran konkret
        empty_hint = compute_empty_hint(master, budget, filters, needs)

        # kosongkan state chatbot
        set_last_recommendation(None)
        return {
            "count": 0,
            "items": [],
            "needs": needs,
            "hint": empty_hint,
        }

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
