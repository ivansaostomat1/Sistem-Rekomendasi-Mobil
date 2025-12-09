# file: backend/spk_soft.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
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
    Hitung persentil untuk kolom-kolom relevan dan kembalikan dictionary.
    Fallback konservatif bila data kosong.
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

    cc_s = df.get("cc_kwh_num")
    wgt_s = df.get("vehicle_weight_kg")
    pw_series = None
    if cc_s is not None and wgt_s is not None:
        wgt_safe = pd.to_numeric(wgt_s, errors="coerce").replace({0: np.nan})
        cc_num = pd.to_numeric(cc_s, errors="coerce")
        with np.errstate(divide="ignore", invalid="ignore"):
            pw_series = (cc_num / wgt_safe).replace([np.inf, -np.inf], np.nan)

    return {
        "len_p40": P(df.get("length_mm"), 40, np.inf),
        "len_p50": P(df.get("length_mm"), 50, np.inf),
        "len_p60": P(df.get("length_mm"), 60, -np.inf),
        "len_p70": P(df.get("length_mm"), 70, -np.inf),
        "len_p80": P(df.get("length_mm"), 80, -np.inf),
        "len_p90": P(df.get("length_mm"), 90, np.inf),

        "wid_p40": P(df.get("width_mm"), 40, np.inf),
        "wid_p50": P(df.get("width_mm"), 50, np.inf),
        "wid_p60": P(df.get("width_mm"), 60, -np.inf),

        "wgt_p50": P(df.get("vehicle_weight_kg"), 50, np.inf),
        "wgt_p60": P(df.get("vehicle_weight_kg"), 60, -np.inf),
        "wb_p60":  P(df.get("wheelbase_mm"), 60, -np.inf),
        "wb_p70":  P(df.get("wheelbase_mm"), 70, -np.inf),
        "rim_p60": P(df.get("rim_inch"), 60, -np.inf),
        "tyr_p60": P(df.get("tyre_w_mm"), 60, -np.inf),
        "pw_p60":  P(pw_series, 60, -np.inf),
    }


# Parsing dimension helper untuk soft rules (mendukung berbagai variasi format)
def parse_dimension(dim: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if dim is None:
        return None, None, None
    try:
        s = str(dim).lower()
        s = s.replace("×", "x").replace("mm", "")
        s = re.sub(r'[^0-9x\.\,\-\s]', ' ', s)
        parts = re.split(r'[x]', s)
        parts = [p.strip().replace(",", "") for p in parts if p.strip()]
        if len(parts) >= 3:
            return float(parts[0]), float(parts[1]), float(parts[2])
        nums = re.findall(r'(\d{3,4})', s)
        if len(nums) >= 3:
            return float(nums[0]), float(nums[1]), float(nums[2])
        return None, None, None
    except Exception:
        return None, None, None


def _is_large_commercial_dim(L: Optional[float], W: Optional[float], H: Optional[float]) -> bool:
    """
    Indikator dimensi besar yang cenderung niaga. Termasuk trigger khusus 5140x1928x1880.
    """
    if L is None or W is None or H is None:
        return False
    if L >= 5140 and W >= 1928 and H >= 1880:
        return True
    if L >= 5200 or H >= 2000 or W >= 2100:
        return True
    if L >= 5400 and H >= 1850:
        return True
    return False


def soft_multiplier(r: pd.Series, needs: Optional[List[str]], P: Dict[str, float]) -> float:
    """
    Hitung multiplier 'soft' untuk tiap baris (SAW-ish weight adjustments).
    Output dibatasi antara 0.85 dan 1.18 (sama seperti sebelumnya).
    """
    needs = needs or []
    m = 1.0

    # Ambil numerik dan atribut penting
    length = _safe_to_float(r.get("length_mm"))
    width = _safe_to_float(r.get("width_mm"))
    weight = _safe_to_float(r.get("vehicle_weight_kg"))
    wb = _safe_to_float(r.get("wheelbase_mm"))
    cc = _safe_to_float(r.get("cc_kwh_num"))
    rim = _safe_to_float(r.get("rim_inch"))
    tyr = _safe_to_float(r.get("tyre_w_mm"))
    awd = _safe_to_float(r.get("awd_flag")) or 0.0
    seats = _safe_to_float(r.get("seats")) or np.nan

    fuel_c = str(r.get("fuel_code") or "").lower()
    seg = str(r.get("segmentasi") or "").lower()
    model = str(r.get("model") or "")

    # parse dimension string bila ada (fallback)
    dim_col = None
    for k in ("dimension", "DIMENSION P x L xT", "dimension_str"):
        if k in r.index:
            dim_col = r.get(k)
            break
    dimL, dimW, dimH = parse_dimension(dim_col) if dim_col is not None else (None, None, None)

    # helper kecil
    def is_efficient() -> bool:
        return fuel_c in {"h", "p", "e"} or (not np.isnan(cc) and cc <= 1500)

    # power-to-weight scalar
    pw = np.nan
    if (not np.isnan(weight)) and weight > 0 and np.isfinite(weight):
        pw = cc / weight if not np.isnan(cc) else np.nan

    # ----------------
    # Perkotaan (short trip) — perbaikan:
    #  - jangan pilih yang *terlalu kecil* (microcar) yang mengorbankan kenyamanan
    #  - jangan pilih truk/niaga
    #  - beri toleransi untuk sedan kompak yang proporsional (lebar memadai)
    # ----------------
    if "perkotaan" in needs:
        small_city_cond = (
            (not np.isnan(length) and length <= P.get("len_p50", np.inf)) and
            (not np.isnan(width) and width <= P.get("wid_p50", np.inf)) and
            (not np.isnan(weight) and weight <= P.get("wgt_p50", np.inf))
        )

        # microcar sangat kecil -> penalti signifikan
        too_tiny = (not np.isnan(width) and not np.isnan(length)) and (width < 1550 and length < 3500)

        # deteksi 'truck-like' via dimensi besar atau segmentasi
        is_truck_like = _is_large_commercial_dim(dimL, dimW, dimH) or bool(re.search(r"\b(?:pickup|box|blindvan|light\s*truck|chassis|minibus|truck)\b", seg, flags=re.I))

        # sedan kompak boleh diterima jika lebarnya proporsional
        sedan_mask = bool(re.search(r"\bsedan\b", seg, flags=re.I))
        sedan_allow = sedan_mask and (not np.isnan(width) and width >= 1650)

        # Efisien/EV dapat lebih longgar
        if small_city_cond and is_efficient() and (not too_tiny):
            m *= 1.02
        elif too_tiny:
            m *= 0.92  # penalti karena terlalu sempit
        elif is_truck_like:
            m *= 0.88  # kuat tolak truck-like untuk kota (jika user tak minta niaga)
        elif sedan_allow:
            m *= 1.01
        else:
            m *= 1.00

        # MPV/SUV sedikit penalti untuk kota (manuver & parkir)
        if re.search(r"\b(?:mpv|van|minibus|suv|crossover)\b", seg, flags=re.I):
            m *= 0.98

    # ----------------
    # Keluarga
    # ----------------
    if "keluarga" in needs:
        # Rules:
        # - seats >=6 => kuat family
        # - seats ==5 => family kecil diterima jika lebarnya/wheelbase memadai atau body mpv/suv/van
        seats_ok_6 = (not np.isnan(seats)) and seats >= 6
        seats_eq_5 = (not np.isnan(seats)) and seats == 5

        roomy = False
        if seats_ok_6:
            roomy = True
        elif seats_eq_5:
            roomy = ((not np.isnan(width) and width >= 1700) or (not np.isnan(wb) and wb >= 2500)) or bool(re.search(r"\b(?:mpv|van|minibus|suv)\b", seg, flags=re.I))
        else:
            # jika seats NaN, infer dari wheelbase/segmentasi
            roomy = ((not np.isnan(wb) and wb >= P.get("wb_p60", -np.inf)) and bool(re.search(r"\b(?:mpv|van|minibus)\b", seg, flags=re.I)))

        if roomy:
            m *= 1.06
        else:
            # lebih toleran: penalti ringan saja — jangan tolak total bila 5 seat borderline
            if seats_eq_5:
                m *= 0.99  # sedikit penalti untuk family kecil yang sempit
            else:
                m *= 0.95

        # Jika dimensi besar yang jelas komersial (ex: 5140x1928x1880), kurangi kecenderungan family
        if _is_large_commercial_dim(dimL, dimW, dimH) and not bool(re.search(r"\b(?:mpv|van|suv|sedan|hatchback|crossover)\b", seg, flags=re.I)):
            m *= 0.88

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

        # Jangan beri boost fun besar pada MPV boxy kecuali sangat bertenaga
        if re.search(r"\b(?:mpv|van|minibus)\b", seg, flags=re.I) and not (np.isfinite(pw) and pw >= P.get("pw_p60", -np.inf)):
            fun_boost *= 0.90

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
            trip_boost *= 1.05
        elif fuel_c == "e":
            trip_boost *= 0.98
        if not np.isnan(weight) and weight >= P.get("wgt_p60", -np.inf):
            trip_boost *= 1.00
        m *= trip_boost

    # ----------------
    # Niaga
    # ----------------
    if "niaga" in needs:
        if (not np.isnan(weight) and weight >= P.get("wgt_p60", -np.inf)) or (not np.isnan(length) and length >= P.get("len_p60", -np.inf)) or _is_large_commercial_dim(dimL, dimW, dimH):
            m *= 1.06
        else:
            m *= 0.98
    else:
        # Jika user tidak minta niaga tapi dimensi jelas komersial -> penalti kuat
        if _is_large_commercial_dim(dimL, dimW, dimH) and not bool(re.search(r"\b(?:mpv|van|suv|sedan|hatchback|crossover)\b", seg, flags=re.I)):
            m *= 0.88

    # Clip result ke range yang aman
    return float(np.clip(m, 0.85, 1.18))


def style_adjust_multiplier(r: pd.Series, needs: Optional[List[str]]) -> float:
    """
    Penyesuaian gaya/segmentasi - mengembalikan multiplier.
    Range clip antara 0.50 dan 1.50 (sama seperti versi awal).
    """
    needs = needs or []
    seg = str(r.get("segmentasi") or "").lower()
    fuel_c = str(r.get("fuel_code") or "").lower()
    cc = _safe_to_float(r.get("cc_kwh_num"))
    model = str(r.get("model") or "")
    seats = _safe_to_float(r.get("seats")) or np.nan
    m = 1.0

    # FUN (dengan atau tanpa keluarga)
    if "fun" in needs:
        if "keluarga" in needs:
            if SEG_MPV.search(seg):
                m *= 0.88  # MPV boxy kurang fun tapi tidak terlalu harsh
            if SEG_SUV.search(seg) or re.search(r"\bcrossover\b", seg):
                m *= 1.04
        else:
            if SEG_MPV.search(seg):
                m *= 0.78
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_COUPE.search(seg):
            m *= 1.08
        if (not np.isnan(cc) and cc < 1400) and (not has_turbo_model(model)):
            m *= 0.92

    # PERJALANAN JAUH
    if "perjalanan_jauh" in needs:
        if SEG_MPV.search(seg):
            m *= 1.12
        if SEG_SEDAN.search(seg):
            m *= 1.08
        if SEG_SUV.search(seg):
            m *= 1.00
        if fuel_c == "d":
            m *= 1.04

    # KELUARGA
    if "keluarga" in needs:
        if SEG_MPV.search(seg):
            m *= 1.10
        if SEG_SUV.search(seg) and (not np.isnan(seats) and seats >= 7):
            m *= 1.03
        # 5-seat family: berikan sedikit toleransi, jangan banting harga
        if not np.isnan(seats) and seats == 5:
            m *= 1.01

    # PERKOTAAN
    if "perkotaan" in needs:
        if SEG_MPV.search(seg) or SEG_SUV.search(seg):
            m *= 0.94
        if SEG_HATCH.search(seg):
            m *= 1.06

    # OFFROAD
    if "offroad" in needs:
        if SEG_SUV.search(seg) or SEG_PICKUP.search(seg):
            m *= 1.05
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_MPV.search(seg):
            m *= 0.65

    return float(np.clip(m, 0.50, 1.50))
