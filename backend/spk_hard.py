# file: backend/spk_hard.py
from __future__ import annotations
from typing import List
import re

import numpy as np
import pandas as pd

from .spk_utils import _series_num
from .spk_features import has_turbo


def has_turbo_model(model: str) -> bool:
    """
    Wrapper kecil supaya pemanggilan di tempat lain lebih bersih.
    """
    return has_turbo(model)


def is_fast_enough(cc_s: pd.Series, model_s: pd.Series, fuel_s: pd.Series) -> pd.Series:
    """
    Dipakai kalau nanti kamu mau pakai proxy "cukup kencang" di tempat lain.
    """
    cc_ok = pd.to_numeric(cc_s, errors="coerce").fillna(0) >= 1500
    turbo_ok = model_s.astype(str).apply(has_turbo_model)
    fuel_ok = fuel_s.astype(str).str.lower().isin(["h", "p", "e"])  # HEV/PHEV/BEV
    return cc_ok | turbo_ok | fuel_ok


def _pw_series(cc: pd.Series, weight: pd.Series) -> pd.Series:
    """
    Power-to-weight ratio kasar: cc / berat(kg).
    """
    w = _series_num(weight).replace(0, np.nan)
    c = _series_num(cc)
    return c / w  # cc per kg


def hard_constraints_filter(cand_feat: pd.DataFrame, needs: List[str]) -> pd.Series:
    """
    Filter WAJIB berdasarkan:
    - kursi, segmen, ukuran, AWD, dll
    - kombinasi kebutuhan (keluarga, perkotaan, fun, offroad, niaga)

    Return: Series boolean dengan index sama dengan cand_feat.
    Perbaikan: Mengurangi kecenderungan "perkotaan" memilih mobil ultra-kecil.
    """
    needs = needs or []
    n = len(cand_feat)
    if n == 0:
        return pd.Series([], dtype=bool, index=cand_feat.index)

    # Numeric series (safe)
    seats = _series_num(cand_feat.get("seats"))
    seg = cand_feat["segmentasi"].astype(str) if "segmentasi" in cand_feat.columns else pd.Series(
        ["" ] * n, index=cand_feat.index, dtype="object"
    )
    model = cand_feat["model"].astype(str) if "model" in cand_feat.columns else pd.Series(
        ["" ] * n, index=cand_feat.index, dtype="object"
    )
    length = _series_num(cand_feat.get("length_mm"))
    width  = _series_num(cand_feat.get("width_mm"))
    weight = _series_num(cand_feat.get("vehicle_weight_kg"))
    wb     = _series_num(cand_feat.get("wheelbase_mm"))
    cc     = _series_num(cand_feat.get("cc_kwh_num"))
    awd    = _series_num(cand_feat.get("awd_flag")).fillna(0.0)
    rim    = _series_num(cand_feat.get("rim_inch"))
    tyr    = _series_num(cand_feat.get("tyre_w_mm"))
    doors  = _series_num(cand_feat.get("doors_num"))
    fuel   = cand_feat.get("fuel_code", pd.Series(["o"] * n, index=cand_feat.index)).astype(str)

    # ---------------------------------------------------------------------
    # Persentil — lebih lengkap & konservatif
    # ---------------------------------------------------------------------
    # gunakan try/guard supaya jika kolom kosong tidak melempar error
    def pct(s: pd.Series, q: float, fallback):
        try:
            if s.notna().any():
                return float(np.nanpercentile(s.dropna(), q))
            return fallback
        except Exception:
            return fallback

    p_len60 = pct(length, 60, -np.inf)
    p_len70 = pct(length, 70, -np.inf)
    p_wid60 = pct(width, 60, -np.inf)
    p_wgt50 = pct(weight, 50, np.inf)
    p_wb60  = pct(wb, 60, -np.inf)

    # Proxy power-to-weight
    pw     = _pw_series(cc, weight)
    p_pw55 = pct(pw, 55, -np.inf)

    # Cepat (FUN) heuristics
    turbo_ok = model.apply(has_turbo_model)
    fuel_ok  = fuel.str.lower().isin(["h", "p", "e"])
    cc_ok    = cc >= 1500
    rim_ok   = (rim >= 17) | (tyr >= 205)
    pw_ok    = pw >= p_pw55
    fast_ok  = turbo_ok | fuel_ok | (cc_ok & (pw_ok | rim_ok))

    # mulai dari semua True
    mask = pd.Series(True, index=cand_feat.index)

    # --- ATURAN BARU: KURSI >= 8 HANYA UNTUK NIAGA ---
    is_commuter_bus = seats >= 8
    if "niaga" not in needs:
        mask &= ~is_commuter_bus

    # --- KOMBO: fun + keluarga + perkotaan -> WAJIB ≥4 pintu ---
    if {"fun", "keluarga", "perkotaan"}.issubset(set(needs)):
        idx = cand_feat.index

        if "doors_num" in cand_feat.columns:
            doors_s = pd.to_numeric(cand_feat["doors_num"], errors="coerce").reindex(idx)
        else:
            doors_s = pd.Series(np.nan, index=idx, dtype="float64")

        two_dr_pat = r"\b(?:2[\s\-]?door|2dr|two\s*door)\b"
        if "model" in cand_feat.columns:
            two_dr_txt = cand_feat["model"].astype(str).str.contains(
                two_dr_pat, flags=re.I, regex=True, na=False
            ).reindex(idx)
        else:
            two_dr_txt = pd.Series(False, index=idx)

        if "segmentasi" in cand_feat.columns:
            two_dr_seg = cand_feat["segmentasi"].astype(str).str.contains(
                r"\bcoupe\b", flags=re.I, regex=True, na=False
            ).reindex(idx)
        else:
            two_dr_seg = pd.Series(False, index=idx)

        two_dr_hint = (two_dr_txt | two_dr_seg).fillna(False)

        doors_rule = (doors_s >= 4) | (doors_s.isna() & (~two_dr_hint))
        doors_rule = doors_rule.reindex(idx).fillna(False)

        mask = mask & doors_rule

    # --- keluarga ---
    if "keluarga" in needs:
        # jika fun/perkotaan masuk, izinkan 5-seater sebagai baseline, else minta minimal 6 (lebih aman)
        if "fun" in needs or "perkotaan" in needs:
            base_min = 5
        else:
            base_min = 6

        seats_ok = seats.fillna(0) >= base_min

        # Jika base_min == 5: pastikan tidak terlalu sempit
        if base_min == 5:
            # Lebar > 1.7m OR Wheelbase > 2.5m dianggap cukup
            is_spacious = (width >= 1700) | (wb >= 2500) | width.isna()
            seats_ok = seats_ok & is_spacious

        # hint 3 baris kursi kalau data seats kosong (untuk base_min=6)
        three_row_hint = seg.str.contains(
            r"\b(?:mpv|suv|minibus|van)\b", flags=re.I, regex=True, na=False
        ) & ((wb >= p_wb60) | (length >= p_len60))

        seats_ok = seats_ok | (seats.isna() & three_row_hint)
        mask &= seats_ok

    # --- offroad ---
    if "offroad" in needs:
        forbid_sedan = seg.str.contains(r"\bsedan\b", flags=re.I, regex=True, na=False)
        mask &= ~forbid_sedan
        mask &= (awd >= 0.5)

    # --- perkotaan (short trip) ---
    if "perkotaan" in needs:
        # Perbaikan:
        # - definisi "small" lebih ketat: length <= p_len50 AND width <= p_wid50 AND weight <= p_wgt50
        # - mobil efisien (EV/Hybrid/PHEV) boleh menjadi sedikit lebih panjang (<= p_len70)
        # - jangan mengandalkan width p40 yang terlalu agresif
        # Relaksasi: fokus pada width (parkir/gesit) dan efisiensi.
        # Width threshold pakai p_wid60 supaya sedan kompak masih lulus.
        small_by_width = ((width <= p_wid60) | width.isna()) 
        compact_length = ((length <= p_len70) | length.isna())

# efisien = EV/HEV/PHEV atau cc kecil
        efficient = fuel.str.lower().isin(["h", "p", "e"]) | (cc <= 1500) | cc.isna()

# Jika mobil efisien (EV), ijinkan panjang/berat lebih besar selama lebarnya wajar
        if "fun" in needs:
            base_city = (small_by_width & efficient) | (fast_ok & efficient) | (small_by_width & compact_length)
        else:
            base_city = efficient | (small_by_width) | (compact_length & (width <= p_wid60))

        mask &= base_city


    # --- fun ---
    if "fun" in needs:
        mask &= fast_ok
        if "perjalanan_jauh" not in needs:
            # Fun murni biasanya bukan MPV/Van (kecuali exceptional fast_ok)
            pass
        if "perkotaan" in needs:
            # Fun + City -> jangan MPV/Van/Minibus
            not_mpv = ~seg.str.contains(r"\b(?:mpv|van|minibus)\b", flags=re.I, regex=True, na=False)
            mask &= not_mpv

    # --- niaga ---
    niaga_pat = r"\b(?:pick\s*up|pickup|pu|box|blind\s*van|blindvan|niaga|light\s*truck|chassis|cab\s*/?\s*chassis|minibus)\b"
    if "niaga" in needs:
        allow = seg.str.contains(niaga_pat, flags=re.I, regex=True, na=False)
        mask &= allow
    if needs and "niaga" not in needs:
        is_niaga = seg.str.contains(niaga_pat, flags=re.I, regex=True, na=False)
        mask &= ~is_niaga

    # Pastikan dtype boolean dan index sama
    mask = mask.fillna(False).astype(bool)
    return mask
