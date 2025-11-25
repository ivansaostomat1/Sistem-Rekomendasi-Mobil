# file: spk_rank.py
from __future__ import annotations
from typing import Dict, Any, List
import time
import re
import numpy as np
import pandas as pd

from klastering import cluster_and_label, need_similarity_scores

from spk_utils import (
    SEG_SEDAN, SEG_HATCH, SEG_COUPE, SEG_MPV, SEG_SUV, SEG_PICKUP,
    NEED_LABELS,
    contains_ci, vector_match_trans,
    _series_num, assign_array_safe, _dbg, _ensure_df, price_fit_anchor,
    fuel_to_code,  # ← TAMBAH INI
)



from spk_features import add_need_features, has_turbo


# ============================================================
# Sanitasi kebutuhan
# ============================================================

def _resolve_pair_keep_first(needs: List[str], a: str, b: str) -> List[str]:
    if a in needs and b in needs:
        if needs.index(a) < needs.index(b):
            return [n for n in needs if n != b]
        else:
            return [n for n in needs if n != a]
    return needs


def sanitize_needs(raw: List[str]) -> List[str]:
    """
    - Hilangkan duplikat (pertahankan urutan)
    - Mutual exclusion:
        fun ⟂ {offroad, niaga}
        perjalanan_jauh ⟂ perkotaan
    - Maks 3 kebutuhan.
    """
    if not raw:
        return []
    seen, needs = set(), []
    for n in raw:
        n = str(n).strip().lower()
        if n in NEED_LABELS and n not in seen:
            needs.append(n)
            seen.add(n)
    needs = _resolve_pair_keep_first(needs, "fun", "offroad")
    needs = _resolve_pair_keep_first(needs, "fun", "niaga")
    needs = _resolve_pair_keep_first(needs, "perjalanan_jauh", "perkotaan")
    if len(needs) > 3:
        needs = needs[:3]
    return needs


# ============================================================
# Hard constraints (WAJIB)
# ============================================================

def has_turbo_model(model: str) -> bool:
    return has_turbo(model)


def is_fast_enough(cc_s: pd.Series, model_s: pd.Series, fuel_s: pd.Series) -> pd.Series:
    cc_ok = pd.to_numeric(cc_s, errors="coerce").fillna(0) >= 1500
    turbo_ok = model_s.astype(str).apply(has_turbo_model)
    fuel_ok = fuel_s.astype(str).str.lower().isin(
        ["h", "p", "e"])  # HEV/PHEV/BEV
    return cc_ok | turbo_ok | fuel_ok


def _pw_series(cc: pd.Series, weight: pd.Series) -> pd.Series:
    w = _series_num(weight).replace(0, np.nan)
    c = _series_num(cc)
    return c / w  # cc per kg (proxy power-to-weight)


def hard_constraints_filter(cand_feat: pd.DataFrame, needs: List[str]) -> pd.Series:
    needs = needs or []
    n = len(cand_feat)
    if n == 0:
        return pd.Series([], dtype=bool, index=cand_feat.index)

    seats = _series_num(cand_feat.get("seats"))
    seg = cand_feat["segmentasi"].astype(str) if "segmentasi" in cand_feat.columns else pd.Series([
        ""] * n, index=cand_feat.index, dtype="object")
    model = cand_feat["model"].astype(str) if "model" in cand_feat.columns else pd.Series([
        ""] * n, index=cand_feat.index, dtype="object")
    length = _series_num(cand_feat.get("length_mm"))
    width = _series_num(cand_feat.get("width_mm"))
    weight = _series_num(cand_feat.get("vehicle_weight_kg"))
    wb = _series_num(cand_feat.get("wheelbase_mm"))
    cc = _series_num(cand_feat.get("cc_kwh_num"))
    awd = _series_num(cand_feat.get("awd_flag")).fillna(0.0)
    rim = _series_num(cand_feat.get("rim_inch"))
    tyr = _series_num(cand_feat.get("tyre_w_mm"))
    doors = _series_num(cand_feat.get("doors_num"))
    fuel = cand_feat.get("fuel_code", pd.Series(
        ["o"] * n, index=cand_feat.index)).astype(str)

    # persentil untuk "kompak" & "besar"
    p_len40 = float(np.nanpercentile(length.dropna(), 40)
                    ) if length.notna().any() else np.inf
    p_wid40 = float(np.nanpercentile(width.dropna(),  40)
                    ) if width.notna().any() else np.inf
    p_wgt50 = float(np.nanpercentile(weight.dropna(), 50)
                    ) if weight.notna().any() else np.inf
    p_wb60 = float(np.nanpercentile(wb.dropna(),     60)
                   ) if wb.notna().any() else -np.inf
    p_len60 = float(np.nanpercentile(length.dropna(), 60)
                    ) if length.notna().any() else -np.inf

    # proxy power-to-weight
    pw = _pw_series(cc, weight)
    p_pw55 = float(np.nanpercentile(pw.dropna(), 55)
                   ) if pw.notna().any() else -np.inf

    # cepat (FUN)
    turbo_ok = model.apply(has_turbo_model)
    fuel_ok = fuel.str.lower().isin(["h", "p", "e"])
    cc_ok = cc >= 1500
    rim_ok = (rim >= 17) | (tyr >= 205)
    pw_ok = pw >= p_pw55
    fast_ok = turbo_ok | fuel_ok | (cc_ok & (pw_ok | rim_ok))

    # mulai dari semua True
    mask = pd.Series(True, index=cand_feat.index)

    # --- KOMBO: fun + keluarga + perkotaan -> WAJIB ≥4 pintu ---
    if {"fun", "keluarga", "perkotaan"}.issubset(set(needs)):
        idx = cand_feat.index

        if "doors_num" in cand_feat.columns:
            doors_s = pd.to_numeric(
                cand_feat["doors_num"], errors="coerce").reindex(idx)
        else:
            doors_s = pd.Series(np.nan, index=idx, dtype="float64")

        two_dr_pat = r"\b(?:2[\s\-]?door|2dr|two\s*door)\b"
        if "model" in cand_feat.columns:
            two_dr_txt = cand_feat["model"].astype(str).str.contains(
                two_dr_pat, flags=re.I, regex=True, na=False).reindex(idx)
        else:
            two_dr_txt = pd.Series(False, index=idx)

        if "segmentasi" in cand_feat.columns:
            two_dr_seg = cand_feat["segmentasi"].astype(str).str.contains(
                r"\bcoupe\b", flags=re.I, regex=True, na=False).reindex(idx)
        else:
            two_dr_seg = pd.Series(False, index=idx)

        two_dr_hint = (two_dr_txt | two_dr_seg).fillna(False)

        doors_rule = (doors_s >= 4) | (doors_s.isna() & (~two_dr_hint))
        doors_rule = doors_rule.reindex(idx).fillna(False)

        mask = mask & doors_rule

    # --- keluarga ---
    if "keluarga" in needs:
        min_seats = 5 if "perkotaan" in needs else 6
        seats_ok = (seats.fillna(0) >= min_seats)
        three_row_hint = seg.str.contains(r"\b(?:mpv|suv|minibus|van)\b", flags=re.I, regex=True, na=False) & \
            ((wb >= p_wb60) | (length >= p_len60))
        seats_ok = seats_ok | (seats.isna() & three_row_hint)
        mask &= seats_ok

    # --- offroad ---
    if "offroad" in needs:
        forbid_sedan = seg.str.contains(
            r"\bsedan\b", flags=re.I, regex=True, na=False)
        mask &= ~forbid_sedan
        mask &= (awd >= 0.5)

    # --- perkotaan (short trip) ---
    if "perkotaan" in needs:
        small = ((length <= p_len40) | length.isna()) & (
            (width <= p_wid40) | width.isna()) & ((weight <= p_wgt50) | weight.isna())
        efficient = fuel.str.lower().isin(
            ["h", "p", "e"]) | (cc <= 1500) | cc.isna()
        if "fun" in needs:
            mask &= (small & efficient) | (fast_ok & efficient)
        else:
            mask &= small & efficient

    # --- fun (wajib cepat) ---
    if "fun" in needs:
        mask &= fast_ok
        if "perjalanan_jauh" not in needs:
            not_suv = ~seg.str.contains(
                r"\b(?:suv|crossover)\b", flags=re.I, regex=True, na=False)
            mask &= not_suv
        if "perkotaan" in needs:
            not_mpv = ~seg.str.contains(
                r"\b(?:mpv|van|minibus)\b", flags=re.I, regex=True, na=False)
            mask &= not_mpv

    # --- niaga ---
    niaga_pat = r"\b(?:pick\s*up|pickup|pu|box|blind\s*van|blindvan|niaga|light\s*truck|chassis|cab\s*/?\s*chassis|minibus)\b"
    if "niaga" in needs:
        allow = seg.str.contains(niaga_pat, flags=re.I, regex=True, na=False)
        mask &= allow
    if needs and "niaga" not in needs:
        is_niaga = seg.str.contains(
            niaga_pat, flags=re.I, regex=True, na=False)
        mask &= ~is_niaga

    return mask


# ============================================================
# Soft scoring & percentiles
# ============================================================

def compute_percentiles(df: pd.DataFrame) -> Dict[str, float]:
    def P(series: pd.Series | None, q: float, default: float) -> float:
        if series is None:
            return default
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return default
        try:
            return float(np.nanpercentile(s, q))
        except Exception:
            return default

    return {
        "len_p40": P(df.get("length_mm"), 40, np.inf),
        "wid_p40": P(df.get("width_mm"),  40, np.inf),
        "wgt_p50": P(df.get("vehicle_weight_kg"), 50, np.inf),
        "wb_p60":  P(df.get("wheelbase_mm"), 60, -np.inf),
        "wb_p70":  P(df.get("wheelbase_mm"), 70, -np.inf),
        "len_p60": P(df.get("length_mm"), 60, -np.inf),
        "len_p70": P(df.get("length_mm"), 70, -np.inf),
        "wid_p60": P(df.get("width_mm"), 60, -np.inf),
        "wgt_p60": P(df.get("vehicle_weight_kg"), 60, -np.inf),
        "rim_p60": P(df.get("rim_inch"), 60, -np.inf),
        "tyr_p60": P(df.get("tyre_w_mm"), 60, -np.inf),
        "pw_p60":  P(df.get("cc_kwh_num") / df.get("vehicle_weight_kg").replace(0, np.nan), 60, -np.inf),
    }


def soft_multiplier(r: pd.Series, needs: List[str], P: Dict[str, float]) -> float:
    needs = needs or []
    m = 1.0

    length = float(pd.to_numeric(
        r.get("length_mm"), errors="coerce") or np.nan)
    width = float(pd.to_numeric(r.get("width_mm"),  errors="coerce") or np.nan)
    weight = float(pd.to_numeric(
        r.get("vehicle_weight_kg"), errors="coerce") or np.nan)
    wb = float(pd.to_numeric(r.get("wheelbase_mm"), errors="coerce") or np.nan)
    cc = float(pd.to_numeric(r.get("cc_kwh_num"), errors="coerce") or np.nan)
    rim = float(pd.to_numeric(r.get("rim_inch"), errors="coerce") or np.nan)
    tyr = float(pd.to_numeric(r.get("tyre_w_mm"), errors="coerce") or np.nan)
    awd = float(pd.to_numeric(r.get("awd_flag"), errors="coerce") or 0.0)
    seats = float(pd.to_numeric(r.get("seats"), errors="coerce") or 0.0)
    fuel_c = str(r.get("fuel_code") or "").lower()
    seg = str(r.get("segmentasi") or "").lower()
    model = str(r.get("model") or "")

    def is_small_city():
        return (length <= P["len_p40"]) and (width <= P["wid_p40"]) and (weight <= P["wgt_p50"])

    def is_efficient():
        return fuel_c in {"h", "p", "e"} or (cc and cc <= 1500)

    pw = np.nan
    if weight and weight > 0 and np.isfinite(weight):
        pw = (cc or np.nan) / weight

    # Perkotaan
    if "perkotaan" in needs:
        if is_small_city() and is_efficient():
            m *= 1.08
        else:
            big = (length >= P["len_p70"]) or (
                width >= P["wid_p60"]) or (weight >= P["wgt_p60"])
            m *= 0.97 if big else 1.0
        if re.search(r"\b(mpv|van|minibus|suv|crossover)\b", seg, flags=re.I):
            m *= 0.98

    # Keluarga
    if "keluarga" in needs:
        roomy = (seats >= 7) or ((seats >= 6) and (
            wb >= P["wb_p60"]) and (width >= P["wid_p60"]))
        m *= 1.06 if roomy else 0.98

    # Fun to Drive
    if "fun" in needs:
        fun_boost = 1.0
        if np.isfinite(pw) and pw >= P["pw_p60"]:
            fun_boost *= 1.06
        if has_turbo_model(model):
            fun_boost *= 1.04
        if (rim >= P["rim_p60"]) and (tyr >= P["tyr_p60"]):
            fun_boost *= 1.03
        if awd >= 0.5:
            fun_boost *= 1.02
        if (not has_turbo_model(model)) and (cc and cc < 1400):
            fun_boost *= 0.92
        m *= fun_boost

    # Offroad
    if "offroad" in needs:
        m *= 1.07 if awd >= 0.5 else 0.90
        if tyr >= P["tyr_p60"]:
            m *= 1.02

    # Perjalanan Jauh
    if "perjalanan_jauh" in needs:
        trip_boost = 1.0
        if wb >= P["wb_p70"]:
            trip_boost *= 1.05
        if is_efficient():
            trip_boost *= 1.02
        if fuel_c == "d":
            trip_boost *= 1.08
        elif fuel_c == "e":
            trip_boost *= 0.97
        if weight >= P["wgt_p60"]:
            trip_boost *= 0.98
        m *= trip_boost

    # Niaga
    if "niaga" in needs:
        if (weight >= P["wgt_p60"]) or (length >= P["len_p60"]):
            m *= 1.06
        else:
            m *= 0.97

    return float(np.clip(m, 0.85, 1.18))


def style_adjust_multiplier(r: pd.Series, needs: List[str]) -> float:
    seg = str(r.get("segmentasi") or "").lower()
    fuel_c = str(r.get("fuel_code") or "").lower()
    cc = float(pd.to_numeric(r.get("cc_kwh_num"), errors="coerce") or np.nan)
    model = str(r.get("model") or "")
    m = 1.0

    if "fun" in needs:
        if SEG_MPV.search(seg):
            m *= 0.90
        if SEG_SUV.search(seg):
            m *= 0.96
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_COUPE.search(seg):
            m *= 1.06
        if (cc and cc < 1400) and (not has_turbo_model(model)):
            m *= 0.92

    if "perjalanan_jauh" in needs:
        if fuel_c == "d":
            m *= 1.04
        if SEG_SEDAN.search(seg):
            m *= 1.02

    if "keluarga" in needs:
        seats = float(pd.to_numeric(r.get("seats"), errors="coerce") or 0.0)
        if seats >= 7:
            m *= 1.03
        if SEG_MPV.search(seg):
            m *= 1.02

    if "perkotaan" in needs:
        if SEG_MPV.search(seg) or SEG_SUV.search(seg):
            m *= 0.98
        if SEG_HATCH.search(seg):
            m *= 1.02

    if "offroad" in needs:
        if SEG_SUV.search(seg) or SEG_PICKUP.search(seg):
            m *= 1.03

    return float(np.clip(m, 0.85, 1.18))


# ============================================================
# RANKING & PRESENTATION
# ============================================================

def rank_candidates(
    df_master: pd.DataFrame,
    budget: float,
    spec_filters: Dict[str, Any],
    needs: List[str],
    topn: int = 15
) -> pd.DataFrame:
    try:
        t0 = time.perf_counter()

        # ------------------------------------------------------------
        # 0) Normalisasi kebutuhan
        # ------------------------------------------------------------
        needs = sanitize_needs(needs or [])
        needs_set = set(needs)

        # ------------------------------------------------------------
        # 1) Filter harga (<= 115% budget)
        # ------------------------------------------------------------
        cap = budget * 1.15
        cand = _dbg("start", df_master[df_master["price"] <= cap].copy())
        if cand.empty:
            return _ensure_df(cand)

        # ------------------------------------------------------------
        # 2) Filter brand (opsional)
        # ------------------------------------------------------------
        if spec_filters.get("brand"):
            cand = _dbg("brand", cand[contains_ci(cand["brand"], spec_filters["brand"])])
            if cand.empty:
                return _ensure_df(cand)

        # ------------------------------------------------------------
        # 3) Filter transmisi (opsional)
        # ------------------------------------------------------------
        cand = _dbg("trans", cand[vector_match_trans(cand["trans"], spec_filters.get("trans_choice"))])
        if cand.empty:
            return _ensure_df(cand)

        # ------------------------------------------------------------
        # 4) Filter fuel multi-select (opsional, robust)
        # ------------------------------------------------------------
        fuels = spec_filters.get("fuels", None)
        print("[dbg] spec_filters.fuels (raw):", fuels)

        if fuels is not None:
            # Normalisasi ke list
            if isinstance(fuels, (str, bytes)):
                fuels_list = [fuels]
            else:
                try:
                    fuels_list = list(fuels)
                except TypeError:
                    fuels_list = [fuels]

            # Konversi apa pun yang datang (code / label / dict) ke kode 'g/d/h/p/e'
            want_codes = set()
            for x in fuels_list:
                if x is None:
                    continue
                if isinstance(x, dict) and "code" in x:
                    raw = x["code"]
                else:
                    raw = x
                code = fuel_to_code(str(raw))
                if code and code != "o":
                    want_codes.add(code)

            want_codes_sorted = sorted(want_codes)
            print("[dbg] fuel codes wanted:", want_codes_sorted)

            # Kalau ada subset spesifik (0 < len < 5) → batasi
            if 0 < len(want_codes) < 5:
                cand = _dbg("fuel", cand[cand["fuel_code"].astype(str).str.lower().isin(want_codes)])
                if cand.empty:
                    return _ensure_df(cand)

        # ------------------------------------------------------------
        # 5) Tambah fitur kebutuhan + hard constraints
        # ------------------------------------------------------------
        print(f"[dbg] before_features: {len(cand)}")
        cand_feat = add_need_features(cand)
        print(f"[dbg] after_features:  {len(cand_feat)}")

        hard_ok = hard_constraints_filter(cand_feat, needs or [])

        # Pastikan hard_ok adalah boolean Series sesuai index
        if not isinstance(hard_ok, pd.Series):
            hard_ok = pd.Series(bool(hard_ok), index=cand_feat.index)
        else:
            hard_ok = hard_ok.reindex(cand_feat.index)
        hard_ok = hard_ok.fillna(False).astype(bool)

        cand = _dbg("hard_ok", cand[hard_ok])
        cand_feat = cand_feat[hard_ok]
        if cand.empty:
            return _ensure_df(cand)

        # ------------------------------------------------------------
        # 6) Klaster + basic need_score (berbasis centroid)
        # ------------------------------------------------------------
        try:
            cand_feat2, cluster_to_label, C_scaled, feat_cols, scaler, _ = cluster_and_label(cand_feat, k=6)
            X_for_need = cand_feat2[feat_cols].apply(lambda col: col.fillna(col.median()), axis=0).values
            X_scaled = scaler.transform(X_for_need)
            cluster_ids = cand_feat2.get("cluster_id")
            if cluster_ids is None:
                cluster_ids_arr = np.zeros(len(cand_feat2), dtype=int)
            else:
                cluster_ids_arr = np.asarray(cluster_ids)

            need_score = need_similarity_scores(
                X_scaled, C_scaled, cluster_ids_arr, cluster_to_label, needs or []
            )
            cand = cand_feat2.copy()

            if "cluster_id" in cand.columns and cluster_to_label is not None:
                try:
                    cand["cluster_label"] = cand["cluster_id"].map(cluster_to_label)
                except Exception:
                    cand["cluster_label"] = cand["cluster_id"].astype(str)
        except Exception:
            need_score = 0.0
            cand = cand_feat.copy()

        assign_array_safe(cand, "need_score", need_score, fallback=0.0)

        # ------------------------------------------------------------
        # 7) Harga: price_fit (rank + anchor ke budget)
        # ------------------------------------------------------------
        p = pd.to_numeric(cand["price"], errors="coerce")
        if p.notna().any():
            p10 = float(np.nanpercentile(p.dropna(), 10))
            p90 = float(np.nanpercentile(p.dropna(), 90))
        else:
            p10, p90 = 0.0, 1.0
        span = max(1.0, p90 - p10)

        price_rank = ((p - p10) / span).clip(0, 1)  # makin mahal di antara kandidat → makin tinggi
        pmax_cand = float(p.max() if p.notna().any() else budget)
        price_anchor = p.apply(lambda x: price_fit_anchor(x, budget, pmax_cand))
        cand["price_fit"] = 0.5 * price_rank + 0.5 * price_anchor  # 0..1

        # ------------------------------------------------------------
        # 8) Skor atribut eksplisit (power-to-weight, family, city, long trip, offroad, niaga)
        #    + kombinasi khusus kebutuhan (fun+keluarga, longtrip+keluarga, dst.)
        # ------------------------------------------------------------
        # Helper normalisasi 0..1
        def _scale_01(series: pd.Series) -> pd.Series:
            s = pd.to_numeric(series, errors="coerce")
            s_valid = s.dropna()
            if s_valid.empty:
                return pd.Series(0.5, index=series.index, dtype=float)
            lo = float(np.nanpercentile(s_valid, 5))
            hi = float(np.nanpercentile(s_valid, 95))
            if not np.isfinite(lo):
                lo = float(np.nanmin(s_valid))
            if not np.isfinite(hi):
                hi = float(np.nanmax(s_valid))
            span = max(1e-6, hi - lo)
            return ((s - lo) / span).clip(0, 1)

        # Ambil fitur numerik yang dibutuhkan
        length = _series_num(cand.get("length_mm"))
        width  = _series_num(cand.get("width_mm"))
        height = _series_num(cand.get("height_mm"))
        wb     = _series_num(cand.get("wheelbase_mm"))
        weight = _series_num(cand.get("vehicle_weight_kg"))
        cc     = _series_num(cand.get("cc_kwh_num"))
        rim    = _series_num(cand.get("rim_inch"))
        tyr    = _series_num(cand.get("tyre_w_mm"))
        awd    = _series_num(cand.get("awd_flag")).fillna(0.0)
        seats  = _series_num(cand.get("seats"))
        doors  = _series_num(cand.get("doors_num"))

        fuel_c = cand.get("fuel_code", pd.Series(["o"] * len(cand), index=cand.index)).astype(str).str.lower()
        seg    = cand.get("segmentasi", pd.Series([""] * len(cand), index=cand.index)).astype(str).str.lower()
        model  = cand.get("model", pd.Series([""] * len(cand), index=cand.index)).astype(str)

        # Power-to-weight ratio
        w_safe = weight.replace(0, np.nan)
        pw_raw = cc / w_safe.replace(0, np.nan)
        pw_norm = _scale_01(pw_raw)

        # Normalisasi untuk ukuran
        len_norm = _scale_01(length)
        wid_norm = _scale_01(width)
        wgt_norm = _scale_01(weight)
        wb_norm  = _scale_01(wb)
        cc_norm  = _scale_01(cc)
        rim_norm = _scale_01(rim)
        tyr_norm = _scale_01(tyr)

        small_size = ((1 - len_norm) + (1 - wid_norm) + (1 - wgt_norm)) / 3.0

        # Flag turbo
        turbo_flag = model.apply(has_turbo_model).astype(float)

        # Efisiensi (untuk city / irit)
        cc_small   = 1 - cc_norm
        wgt_small  = 1 - wgt_norm
        is_elec_hybrid = fuel_c.isin({"h", "p", "e"}).astype(float)

        efficiency_score = (
            0.4 * cc_small +
            0.4 * wgt_small +
            0.2 * is_elec_hybrid
        ).clip(0, 1)

        # Skor FUN: PW tinggi + turbo + ban besar + AWD
        perf_score = (
            0.55 * pw_norm +
            0.15 * rim_norm +
            0.10 * tyr_norm +
            0.15 * turbo_flag +
            0.05 * (awd > 0.5).astype(float)
        ).clip(0, 1)

        # Skor KELUARGA: kursi, pintu, MPV/van, dengan cap di 7 kursi (di atas 7 tidak tambah skor)
        seats_capped = seats.copy()
        seats_capped[seats_capped > 7] = 7
        seats_norm = _scale_01(seats_capped)

        doors_good = (doors >= 5).astype(float)
        mpv_like = seg.str.contains(r"\b(mpv|van|minibus)\b", regex=True).astype(float)

        family_score = (0.5 * seats_norm + 0.3 * doors_good + 0.2 * mpv_like).clip(0, 1)

        # Penalti ringan untuk bus besar (>=8 kursi dan bodi panjang)
        if length.notna().any():
            len_p70 = float(np.nanpercentile(length.dropna(), 70))
        else:
            len_p70 = np.inf
        many_seats = seats >= 8
        long_body = length >= len_p70
        big_bus_mask = many_seats & long_body
        family_penalty = pd.Series(1.0, index=cand.index, dtype=float)
        family_penalty[big_bus_mask] = 0.95
        family_score = (family_score * family_penalty).clip(0, 1)

        # Skor LONG TRIP (perjalanan jauh): wheelbase, berat, panjang, diesel / efisien
        is_diesel = (fuel_c == "d").astype(float)
        comfort_score = (
            0.45 * wb_norm +
            0.20 * wgt_norm +
            0.15 * len_norm +
            0.20 * (is_diesel * 0.7 + efficiency_score * 0.3)
        ).clip(0, 1)

        # Skor CITY (short trip / perkotaan): kompak + irit
        city_core = (
            0.6 * small_size +
            0.4 * efficiency_score
        ).clip(0, 1)
        city_score = city_core

        # Skor OFFROAD: AWD + ban besar + SUV/pickup
        is_suv = SEG_SUV.search if False else None  # placeholder untuk type hint saja

        suv_like = cand["segmentasi"].astype(str).str.contains(
            r"\b(suv|crossover)\b", flags=re.I, regex=True, na=False
        ).astype(float)
        pickup_like = cand["segmentasi"].astype(str).str.contains(
            r"\b(pick\s*up|pickup|pu|light\s*truck|chassis)\b", flags=re.I, regex=True, na=False
        ).astype(float)

        offroad_score = (
            0.5 * (awd.clip(0, 1)) +
            0.2 * tyr_norm +
            0.15 * rim_norm +
            0.15 * (suv_like + pickup_like).clip(0, 1)
        ).clip(0, 1)

        # Skor NIAGA: panjang + berat (kapasitas), tapi tidak terlalu tergantung PW
        utility_score = (
            0.5 * len_norm +
            0.5 * wgt_norm
        ).clip(0, 1)

        # --------------------------------------------------------
        # 9) Gabungkan skor atribut sesuai kebutuhan + KOMBINASI KHUSUS
        # --------------------------------------------------------
        need_s = pd.to_numeric(cand.get("need_score", 0.5), errors="coerce").fillna(0.5)

        # Default: rata-rata tertimbang skor atribut per-need
        attr_num = pd.Series(0.0, index=cand.index, dtype=float)
        w_attr = 0.0

        if "fun" in needs_set:
            attr_num += 0.4 * perf_score
            w_attr += 0.4
        if "keluarga" in needs_set:
            attr_num += 0.4 * family_score
            w_attr += 0.4
        if "perjalanan_jauh" in needs_set:
            attr_num += 0.4 * comfort_score
            w_attr += 0.4
        if "perkotaan" in needs_set:
            attr_num += 0.4 * city_score
            w_attr += 0.4
        if "niaga" in needs_set:
            attr_num += 0.4 * utility_score
            w_attr += 0.4
        if "offroad" in needs_set:
            attr_num += 0.4 * offroad_score
            w_attr += 0.4

        if w_attr > 0:
            attr_score = (attr_num / w_attr).clip(0, 1)
        else:
            attr_score = need_s.copy()

        # ---------- Kombinasi khusus ----------
        combo_attr = None

        # 9.1 fun + keluarga + perkotaan
        if {"fun", "keluarga", "perkotaan"}.issubset(needs_set):
            combo_attr = (
                0.45 * perf_score +
                0.35 * family_score +
                0.20 * city_score
            ).clip(0, 1)

            # tambahan: penalti ukuran terlalu besar (biar lebih lincah)
            if length.notna().any():
                len_p70_combo = float(np.nanpercentile(length.dropna(), 70))
            else:
                len_p70_combo = np.inf
            if weight.notna().any():
                wgt_p70_combo = float(np.nanpercentile(weight.dropna(), 70))
            else:
                wgt_p70_combo = np.inf

            too_big = (length >= len_p70_combo) | (weight >= wgt_p70_combo)
            size_penalty = pd.Series(1.0, index=cand.index, dtype=float)
            size_penalty[too_big] = 0.90
            combo_attr = (combo_attr * size_penalty).clip(0, 1)

        # 9.2 fun + keluarga (tanpa long trip)
        elif {"fun", "keluarga"}.issubset(needs_set) and "perjalanan_jauh" not in needs_set:
            combo_attr = (
                0.6 * perf_score +    # kencang
                0.4 * family_score    # tetap family-friendly
            ).clip(0, 1)

            # penalti ekstra untuk mobil yang terlalu besar (bus MPV besar)
            if length.notna().any():
                len_p70_combo = float(np.nanpercentile(length.dropna(), 70))
            else:
                len_p70_combo = np.inf
            if weight.notna().any():
                wgt_p70_combo = float(np.nanpercentile(weight.dropna(), 70))
            else:
                wgt_p70_combo = np.inf

            too_big = (length >= len_p70_combo) | (weight >= wgt_p70_combo)
            size_penalty = pd.Series(1.0, index=cand.index, dtype=float)
            size_penalty[too_big] = 0.90
            combo_attr = (combo_attr * size_penalty).clip(0, 1)

        # 9.3 long trip + keluarga
        elif {"perjalanan_jauh", "keluarga"}.issubset(needs_set):
            combo_attr = (
                0.55 * comfort_score +   # nyaman & stabil
                0.45 * family_score      # kursi cukup & layout keluarga
            ).clip(0, 1)

        # 9.4 keluarga + short trip (perkotaan)
        elif {"keluarga", "perkotaan"}.issubset(needs_set):
            combo_attr = (
                0.45 * family_score +
                0.30 * city_score +
                0.25 * efficiency_score
            ).clip(0, 1)

        # 9.5 long trip + fun
        elif {"perjalanan_jauh", "fun"}.issubset(needs_set):
            combo_attr = (
                0.5 * perf_score +
                0.5 * comfort_score
            ).clip(0, 1)

        # 9.6 short trip + fun (perkotaan + fun)
        elif {"perkotaan", "fun"}.issubset(needs_set):
            combo_attr = (
                0.5 * perf_score +
                0.3 * efficiency_score +
                0.2 * city_score
            ).clip(0, 1)

        # 9.7 offroad + long trip
        elif {"offroad", "perjalanan_jauh"}.issubset(needs_set):
            combo_attr = (
                0.5 * offroad_score +
                0.5 * comfort_score
            ).clip(0, 1)

        # 9.8 offroad + short trip
        elif {"offroad", "perkotaan"}.issubset(needs_set):
            combo_attr = (
                0.6 * offroad_score +
                0.4 * city_score
            ).clip(0, 1)

        # 9.9 keluarga + offroad
        elif {"keluarga", "offroad"}.issubset(needs_set):
            combo_attr = (
                0.5 * offroad_score +
                0.5 * family_score
            ).clip(0, 1)

        # Jika ada kombinasi khusus, pakai untuk override attr_score
        if combo_attr is not None:
            # blending supaya masih respect need_score klaster
            attr_score = combo_attr

        # Gabungkan need_score (klaster) + attr_score eksplisit
        if needs and isinstance(need_score, np.ndarray):
            # skor preferensi murni kebutuhan
            pref_score = (
                0.6 * attr_score +
                0.4 * need_s
            ).clip(0, 1)
        else:
            pref_score = attr_score

        # ------------------------------------------------------------
        # 10) Gabungkan dengan harga → fit_score awal
        # ------------------------------------------------------------
        if needs:
            alpha_price = 0.20 if ("fun" in needs_set) else 0.30
            cand["fit_score"] = (
                (1.0 - alpha_price) * pref_score +
                alpha_price * cand["price_fit"]
            ).clip(0, 1)
        else:
            cand["fit_score"] = cand["price_fit"]

        # ------------------------------------------------------------
        # 11) Soft layer + style layer (lapisan halus)
        # ------------------------------------------------------------
        P = compute_percentiles(cand)
        cand["soft_mult"]  = cand.apply(lambda r: soft_multiplier(r, needs or [], P), axis=1)
        cand["fit_score"]  = (cand["fit_score"] * cand["soft_mult"]).clip(0, 1.0)
        cand["style_mult"] = cand.apply(lambda r: style_adjust_multiplier(r, needs or []), axis=1)
        cand["fit_score"]  = (cand["fit_score"] * cand["style_mult"]).clip(0, 1.0)

        # ------------------------------------------------------------
        # 12) Alasan sederhana
        # ------------------------------------------------------------
        def mk_reason(r):
            why = []
            why.append("harga sesuai budget" if r["price"] <= budget else "±15% dari budget")
            if "keluarga" in (needs or []):
                min_seats = 5 if "perkotaan" in (needs or []) else 6
                why.append(f"kursi ≥{min_seats}")
            if "offroad" in (needs or []):
                why.append("AWD/4x4 & siap offroad" if r.get("awd_flag", 0) >= 0.5 else "butuh AWD/4x4")
            if "perkotaan" in (needs or []):
                why.append("kompak & efisien")
            if "perjalanan_jauh" in (needs or []):
                why.append("diesel cocok perjalanan jauh" if str(r.get("fuel_code", "")) == "d" else "stabil & efisien jarak jauh")
            if "fun" in (needs or []):
                bits = []
                if pd.to_numeric(r.get("cc_kwh_num"), errors="coerce") >= 1600:
                    bits.append("mesin responsif")
                if has_turbo_model(str(r.get("model", ""))):
                    bits.append("turbo")
                if r.get("awd_flag", 0) >= 0.5:
                    bits.append("traksi baik")
                if bits:
                    why.append("fun: " + ", ".join(bits))
            return ", ".join([w for w in why if w])

        cand["alasan"] = cand.apply(mk_reason, axis=1)

                # ------------------------------------------------------------
        # 13) Sortir, deduplikasi, rank & points (robust terhadap NaN)
        # ------------------------------------------------------------
        # Buang inf, ganti ke NaN dulu
        cand = cand.replace([np.inf, -np.inf], np.nan)

        # Pastikan fit_score numerik
        cand["fit_score"] = pd.to_numeric(cand.get("fit_score"), errors="coerce")

        # Jika semua fit_score NaN → tidak ada rekomendasi yang layak
        valid_fit = cand["fit_score"].notna()
        if not valid_fit.any():
            return _ensure_df(cand.iloc[0:0])

        # Hanya pakai baris yang fit_score-nya valid
        cand = cand[valid_fit].copy()

        # Normalisasi nama model + price untuk dedup
        cand["model_norm"] = cand["model"].astype(str) \
            .str.replace(r"\s+", " ", regex=True) \
            .str.strip() \
            .str.lower()

        cand["price_int"] = pd.to_numeric(cand["price"], errors="coerce") \
            .fillna(-1) \
            .astype(int)

        # Sortir dari fit_score tertinggi, lalu deduplikasi
        cand = (
            cand.sort_values(["fit_score"], ascending=[False])
                .drop_duplicates(subset=["model_norm", "price_int"], keep="first")
                .drop(columns=["model_norm", "price_int"])
        )

        cand = cand.reset_index(drop=True)

        # Rank urut manual 1..N (tanpa .rank() yang bisa bikin NaN)
        n_out = len(cand)
        cand["rank"] = np.arange(1, n_out + 1, dtype=int)

        # Points 1..99 (kurang lebih linear dari rank)
        den = max(1, n_out - 1)
        cand["points"] = (((n_out - cand["rank"]) / den) * 98 + 1) \
            .round(0) \
            .astype(int)

        # ------------------------------------------------------------
        # 14) Kolom minimal untuk JSON
        # ------------------------------------------------------------
        show_cols = [
            "rank", "points", "brand", "model", "price", "fit_score",
            "fuel", "fuel_code", "trans", "seats", "cc_kwh", "alasan"
        ]
        for c in show_cols:
            if c not in cand.columns:
                cand[c] = np.nan

        topn = 15 if (topn is None or (isinstance(topn, (int, float)) and topn <= 0)) else int(topn)

        t1 = time.perf_counter()
        shape_ns = getattr(need_score, "shape", None)
        print(f"[rank] n_out={len(cand)} time={t1-t0:.3f}s needs={needs} need_score_shape={shape_ns}")
        try:
            print("max price passing hard:", float(pd.to_numeric(cand["price"], errors="coerce").max()))
        except Exception:
            pass

        return _ensure_df(cand.head(topn))

    except Exception as e:
        print(f"[rank] error: {type(e).__name__}: {e}")
        return _ensure_df(pd.DataFrame()).iloc[0:0]
