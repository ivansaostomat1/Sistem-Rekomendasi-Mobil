# file: backend/spk_soft.py
from __future__ import annotations
from typing import Dict, List, Optional
import re

import numpy as np
import pandas as pd

from .spk_utils import SEG_SEDAN, SEG_HATCH, SEG_COUPE, SEG_MPV, SEG_SUV, SEG_PICKUP
from .spk_hard import has_turbo_model


def _safe_to_float(x) -> float:
    """Konversi aman ke float; mengembalikan np.nan jika tidak bisa."""
    try:
        if x is None:
            return np.nan
        val = pd.to_numeric(x, errors="coerce")
        # Jika Series atau Index, ambil scalar jika panjang 1
        if hasattr(val, "shape") and getattr(val, "shape") != ():
            try:
                if len(val) == 1:
                    return float(val.iloc[0])
                else:
                    return np.nan
            except Exception:
                return np.nan
        return float(val) if np.isfinite(val) else np.nan
    except Exception:
        return np.nan


def compute_percentiles(df: pd.DataFrame) -> Dict[str, float]:
    """
    Hitung persentil untuk kolom-kolom relevan dan kembalikan dictionary
    dengan kunci yang dipakai di modul lain. Jika data kosong, gunakan fallback
    yang aman (np.inf untuk batas atas yang membuat kondisi '<= inf' selalu True,
    atau -np.inf untuk batas bawah yang membuat kondisi '>=' selalu True).
    """
    def P(series: Optional[pd.Series], q: float, default: float) -> float:
        if series is None:
            return float(default)
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty:
            return float(default)
        try:
            return float(np.nanpercentile(s.values, q))
        except Exception:
            return float(default)

    # power-to-weight series (cc / weight) dengan penanganan pembagi 0
    cc_s = df.get("cc_kwh_num")
    wgt_s = df.get("vehicle_weight_kg")
    pw_series = None
    if cc_s is not None and wgt_s is not None:
        wgt_safe = pd.to_numeric(wgt_s, errors="coerce").replace({0: np.nan})
        cc_num = pd.to_numeric(cc_s, errors="coerce")
        with np.errstate(divide="ignore", invalid="ignore"):
            pw_series = (cc_num / wgt_safe).replace([np.inf, -np.inf], np.nan)

    return {
        # length percentiles
        "len_p40": P(df.get("length_mm"), 40, np.inf),
        "len_p50": P(df.get("length_mm"), 50, np.inf),
        "len_p60": P(df.get("length_mm"), 60, -np.inf),
        "len_p70": P(df.get("length_mm"), 70, -np.inf),
        "len_p80": P(df.get("length_mm"), 80, -np.inf),
        "len_p90": P(df.get("length_mm"), 90, np.inf),

        # width percentiles
        "wid_p40": P(df.get("width_mm"), 40, np.inf),
        "wid_p50": P(df.get("width_mm"), 50, np.inf),
        "wid_p60": P(df.get("width_mm"), 60, -np.inf),

        # weight / wheelbase / wheel percentiles
        "wgt_p50": P(df.get("vehicle_weight_kg"), 50, np.inf),
        "wgt_p60": P(df.get("vehicle_weight_kg"), 60, -np.inf),
        "wb_p60":  P(df.get("wheelbase_mm"), 60, -np.inf),
        "wb_p70":  P(df.get("wheelbase_mm"), 70, -np.inf),
        "rim_p60": P(df.get("rim_inch"), 60, -np.inf),
        "tyr_p60": P(df.get("tyre_w_mm"), 60, -np.inf),
        "pw_p60":  P(pw_series, 60, -np.inf),
    }


def soft_multiplier(r: pd.Series, needs: Optional[List[str]], P: Dict[str, float]) -> float:
    """
    Hitung multiplier 'soft' berdasarkan atribut baris (r) dan daftar kebutuhan (needs).
    Mengembalikan float yang sudah dipotong (clipped) antara 0.85 dan 1.18.
    """
    needs = needs or []
    m = 1.0

    # Ambil nilai numerik dengan aman
    length = _safe_to_float(r.get("length_mm"))
    width = _safe_to_float(r.get("width_mm"))
    weight = _safe_to_float(r.get("vehicle_weight_kg"))
    wb = _safe_to_float(r.get("wheelbase_mm"))
    cc = _safe_to_float(r.get("cc_kwh_num"))
    rim = _safe_to_float(r.get("rim_inch"))
    tyr = _safe_to_float(r.get("tyre_w_mm"))
    awd = _safe_to_float(r.get("awd_flag")) or 0.0
    seats = _safe_to_float(r.get("seats")) or 0.0

    fuel_c = str(r.get("fuel_code") or "").lower()
    seg = str(r.get("segmentasi") or "").lower()
    model = str(r.get("model") or "")

    def is_small_city() -> bool:
        return (not np.isnan(length) and length <= P.get("len_p60", np.inf)) and \
               (not np.isnan(width) and width <= P.get("wid_p40", np.inf)) and \
               (not np.isnan(weight) and weight <= P.get("wgt_p50", np.inf))

    def is_efficient() -> bool:
        return fuel_c in {"h", "p", "e"} or (not np.isnan(cc) and cc <= 1500)

    # power-to-weight kalkulasi scalar
    pw = np.nan
    if (not np.isnan(weight)) and weight > 0 and np.isfinite(weight):
        pw = cc / weight if not np.isnan(cc) else np.nan

    # ----------------
    # Perkotaan (short trip)
    # ----------------
    if "perkotaan" in needs:
        # Definisi small_city memakai median (len_p50/wid_p50/wgt_p50) -> lebih konservatif
        small_city_cond = (
            (not np.isnan(length) and length <= P.get("len_p50", np.inf)) and
            (not np.isnan(width) and width <= P.get("wid_p50", np.inf)) and
            (not np.isnan(weight) and weight <= P.get("wgt_p50", np.inf))
        )

        # Jika small_city dan efisien, beri sedikit boost — tapi kecil supaya tidak dominan
        if small_city_cond and is_efficient():
            m *= 1.00  # moderate boost for compact + efficient city cars
        else:
            # definisi 'big' gunakan len_p70 (lebih konservatif daripada len_p90)
            big = (
                (not np.isnan(length) and length >= P.get("len_p70", -np.inf)) or
                (not np.isnan(width) and width >= P.get("wid_p60", -np.inf)) or
                (not np.isnan(weight) and weight >= P.get("wgt_p60", -np.inf))
            )
            # sedikit penalti untuk model besar di perkotaan
            m *= 0.99 if big else 1.0

        # MPV / SUV / Van sedikit penalti untuk kota
        if re.search(r"\b(?:mpv|van|minibus|suv|crossover)\b", seg, flags=re.I):
            m *= 0.98

    # ----------------
    # Keluarga
    # ----------------
    if "keluarga" in needs:
        roomy = (seats >= 7) or ((seats >= 6) and (not np.isnan(wb) and wb >= P.get("wb_p60", -np.inf)) and (not np.isnan(width) and width >= P.get("wid_p60", -np.inf)))
        m *= 1.06 if roomy else 0.98

    # ----------------
    # Fun to Drive
    # ----------------
    if "fun" in needs:
        fun_boost = 1.0
        if np.isfinite(pw) and not np.isnan(pw) and pw >= P.get("pw_p60", -np.inf):
            fun_boost *= 1.06
        if has_turbo_model(model):
            fun_boost *= 1.04
        if (not np.isnan(rim) and rim >= P.get("rim_p60", -np.inf)) and (not np.isnan(tyr) and tyr >= P.get("tyr_p60", -np.inf)):
            fun_boost *= 1.03
        if awd >= 0.5:
            fun_boost *= 1.02

        trans_str = str(r.get("trans") or "").lower()
        is_matic = any(tok in trans_str for tok in ("matic", "at", "a/t"))
        if is_matic and has_turbo_model(model):
            fun_boost *= 1.02

        if (not has_turbo_model(model)) and (not np.isnan(cc) and cc < 1400):
            fun_boost *= 0.92

        m *= fun_boost

    # ----------------
    # Offroad
    # ----------------
    if "offroad" in needs:
        m *= 1.07 if awd >= 0.5 else 0.90
        if not np.isnan(tyr) and tyr >= P.get("tyr_p60", -np.inf):
            m *= 1.02

    # ----------------
    # Perjalanan Jauh
    # ----------------
    if "perjalanan_jauh" in needs:
        trip_boost = 1.0
        if not np.isnan(wb) and wb >= P.get("wb_p70", -np.inf):
            trip_boost *= 1.05
        if is_efficient():
            trip_boost *= 1.02
        if fuel_c == "d":
            trip_boost *= 1.10
        elif fuel_c == "e":
            trip_boost *= 0.97
        if not np.isnan(weight) and weight >= P.get("wgt_p60", -np.inf):
            trip_boost *= 0.98
        m *= trip_boost

    # ----------------
    # Niaga
    # ----------------
    if "niaga" in needs:
        if (not np.isnan(weight) and weight >= P.get("wgt_p60", -np.inf)) or (not np.isnan(length) and length >= P.get("len_p60", -np.inf)):
            m *= 1.06
        else:
            m *= 0.97

    return float(np.clip(m, 0.85, 1.18))


def style_adjust_multiplier(r: pd.Series, needs: Optional[List[str]]) -> float:
    """
    Penyesuaian gaya/segmentasi - mengembalikan multiplier yang dipotong antara 0.50 dan 1.50.
    """
    needs = needs or []
    seg = str(r.get("segmentasi") or "").lower()
    fuel_c = str(r.get("fuel_code") or "").lower()
    cc = _safe_to_float(r.get("cc_kwh_num"))
    model = str(r.get("model") or "")
    m = 1.0

    # FUN (dengan atau tanpa keluarga)
    if "fun" in needs:
        if "keluarga" in needs:
            # MPV boxy kurang fun -> penalti sedang
            if SEG_MPV.search(seg):
                m *= 0.85
            # SUV/Crossover -> boost
            if SEG_SUV.search(seg):
                m *= 1.05
        else:
            # Pure fun tanpa keluarga: MPV boxy -> penalti berat
            if SEG_MPV.search(seg):
                m *= 0.70

        # Sedan/Hatch/Coupe cenderung fun
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_COUPE.search(seg):
            m *= 1.10

        # Mesin lemah tanpa turbo -> penalti
        if (not np.isnan(cc) and cc < 1400) and (not has_turbo_model(model)):
            m *= 0.90

    # PERJALANAN JAUH
    if "perjalanan_jauh" in needs:
        if SEG_MPV.search(seg):
            m *= 1.15
        if SEG_SEDAN.search(seg):
            m *= 1.10
        if SEG_SUV.search(seg):
            m *= 0.98
        if fuel_c == "d":
            m *= 1.05

    # KELUARGA
    if "keluarga" in needs:
        seats = _safe_to_float(r.get("seats")) or 0.0
        if SEG_MPV.search(seg):
            m *= 1.12
        if SEG_SUV.search(seg) and seats >= 7:
            m *= 1.03

    # PERKOTAAN
    if "perkotaan" in needs:
        if SEG_MPV.search(seg) or SEG_SUV.search(seg):
            m *= 0.90
        if SEG_HATCH.search(seg):
            m *= 1.10

    # OFFROAD
    if "offroad" in needs:
        if SEG_SUV.search(seg) or SEG_PICKUP.search(seg):
            m *= 1.05
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_MPV.search(seg):
            m *= 0.60

    return float(np.clip(m, 0.50, 1.50))
