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
        if x is None: return np.nan
        val = pd.to_numeric(x, errors="coerce")
        if hasattr(val, "shape") and getattr(val, "shape") != ():
            try:
                if len(val) == 1: return float(val.iloc[0])
                else: return np.nan
            except Exception: return np.nan
        return float(val) if np.isfinite(val) else np.nan
    except Exception:
        return np.nan


def compute_percentiles(df: pd.DataFrame) -> Dict[str, float]:
    def P(series: Optional[pd.Series], q: float, default: float) -> float:
        if series is None: return float(default)
        s = pd.to_numeric(series, errors="coerce").dropna()
        if s.empty: return float(default)
        try: return float(np.nanpercentile(s.values, q))
        except Exception: return float(default)

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


def parse_dimension(dim: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if dim is None: return None, None, None
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
    except Exception: return None, None, None


def _is_large_commercial_dim(L: Optional[float], W: Optional[float], H: Optional[float]) -> bool:
    if L is None or W is None or H is None: return False
    if L >= 5140 and W >= 1928 and H >= 1880: return True
    if L >= 5200 or H >= 2000 or W >= 2100: return True
    if L >= 5400 and H >= 1850: return True
    return False


def soft_multiplier(r: pd.Series, needs: Optional[List[str]], P: Dict[str, float]) -> float:
    """
    Hitung multiplier 'soft' dengan LOGIKA JUJUR, ADIL, & REALISTIS (VERSI AWAM & WORTH IT).
    
    Revisi Utama:
    1. Cap maksimal diturunkan ke 1.30 (dari 1.50) untuk mencegah dominasi tunggal.
    2. Logika 'Fun' tidak lagi memberi bonus turbo pada mobil berat (>1.8 ton).
    3. Logika 'Offroad' lebih ke 'Jalan Rusak' (SUV 4x2 oke), bukan Hardcore 4x4.
    4. Bonus khusus untuk Brand Mainstream (Toyota, Honda, dll) demi 'Peace of Mind'.
    """
    needs = needs or []
    m = 1.0

    # --- 1. PREPARE DATA ---
    length = _safe_to_float(r.get("length_mm"))
    width = _safe_to_float(r.get("width_mm"))
    weight = _safe_to_float(r.get("vehicle_weight_kg"))
    wb = _safe_to_float(r.get("wheelbase_mm"))
    cc = _safe_to_float(r.get("cc_kwh_num"))
    rim = _safe_to_float(r.get("rim_inch"))
    tyr = _safe_to_float(r.get("tyre_w_mm"))
    awd = _safe_to_float(r.get("awd_flag")) or 0.0
    seats = _safe_to_float(r.get("seats")) or 5.0

    seg = str(r.get("segmentasi") or "").lower()
    model = str(r.get("model") or "")
    brand = str(r.get("brand") or "").lower()
    fuel_c = str(r.get("fuel_code") or "").lower()
    trans_str = str(r.get("trans") or "").lower()

    # Dimensi Fallback
    dim_col = None
    for k in ("dimension", "DIMENSION P x L xT", "dimension_str"):
        if k in r.index:
            dim_col = r.get(k)
            break
    dimL, dimW, dimH = parse_dimension(dim_col) if dim_col is not None else (None, None, None)
    if np.isnan(length) and dimL: length = dimL
    if np.isnan(width) and dimW: width = dimW
    if np.isnan(wb): wb = 2500

    # --- 2. IDENTIFIKASI TIPE ---
    is_mpv_boxy = bool(re.search(r"\b(?:mpv|van|minibus)\b", seg, flags=re.I))
    is_suv = bool(re.search(r"\b(?:suv|crossover|jeep)\b", seg, flags=re.I))
    is_city_car = bool(re.search(r"\b(?:hatchback|city|lcgc)\b", seg, flags=re.I)) or (not np.isnan(length) and length < 4200)
    is_sedan = bool(re.search(r"\bsedan\b", seg, flags=re.I))
    is_pickup = bool(re.search(r"\b(?:pickup|truck|box)\b", seg, flags=re.I))
    
    is_7_seater = (seats >= 6)
    is_5_seater = (seats <= 5)
    
    # FUEL IDENTIFIERS
    is_phev = (fuel_c == "p")
    is_hybrid = (fuel_c == "h")
    is_electric = (fuel_c == "e")
    is_diesel = (fuel_c == "d")
    is_small_petrol = (fuel_c == "g" and (not np.isnan(cc) and cc <= 1500))
    
    # Identifikasi Mobil Bongsor (Heavy) - Penting untuk membedakan 'Lincah' vs 'Badak'
    is_heavy = (not np.isnan(weight) and weight > 1800) # SUV Ladder frame biasanya > 1900kg

    pw = np.nan
    if (not np.isnan(weight)) and weight > 0:
        pw = cc / weight if not np.isnan(cc) else np.nan

    # =========================================================
    # LOGIKA INTERAKSI (Updated for "Worth It" & Awam)
    # =========================================================

    # --- SKENARIO 1: KELUARGA + PERKOTAAN ---
    if "keluarga" in needs and "perkotaan" in needs:
        if is_7_seater:
            # MPV Compact (Veloz, Xpander) lebih worth it di kota daripada Innova/Fortuner
            if not np.isnan(length) and length <= 4600: m *= 1.10 
            elif length > 4700: m *= 0.95 # Terlalu panjang buat kota
        elif is_5_seater:
            if is_city_car or (is_suv and length <= 4500): m *= 1.08
            elif is_sedan: m *= 0.95
        
        # Effisiensi
        if is_hybrid or is_phev: m *= 1.15
        elif is_electric: m *= 1.05 # EV enak di kota
        elif is_small_petrol: m *= 1.05
            
        if is_diesel: m *= 0.95 # Diesel kurang cocok buat stop-n-go kota (polusi/suara)

    # --- SKENARIO 2: KELUARGA + PERJALANAN JAUH ---
    elif "keluarga" in needs and "perjalanan_jauh" in needs:
        if is_7_seater: m *= 1.10
        elif is_5_seater:
            if is_city_car: m *= 0.85 # Capek naik city car jauh
            
        if not np.isnan(wb) and wb > 2700: m *= 1.05 # Kabin lega
        if is_diesel: m *= 1.10 # Diesel raja jarak jauh
        if is_heavy: m *= 1.05 # Mobil berat lebih stabil di tol

    # --- SKENARIO 3: HANYA KELUARGA ---
    elif "keluarga" in needs:
        if is_7_seater: m *= 1.10
        elif is_5_seater: m *= 0.95

    # --- SKENARIO 4: FUN + PERKOTAAN ---
    if "fun" in needs and "perkotaan" in needs:
        if is_mpv_boxy or is_pickup: m *= 0.70 # Gak enak
        if is_heavy: m *= 0.80 # Mobil berat di kota gak fun (susah parkir/manuver)
        elif is_city_car or is_sedan: m *= 1.15 # Kecil = Fun di kota

    # =========================================================
    # FITUR INDEPENDEN (STACKABLE) - REFINED
    # =========================================================
    
    # 1. OFFROAD (Versi Awam: "Jalan Rusak/Banjir", bukan Hardcore)
    if "offroad" in needs:
        if is_suv or is_pickup: m *= 1.15 # SUV cukup (bahkan 4x2 oke)
        if awd >= 0.5: m *= 1.05 # Bonus AWD dikecilkan (biar harga gak melambung)
        if is_sedan or is_city_car: m *= 0.60 # Pendek = Big No
        if is_mpv_boxy: m *= 0.85
        if is_diesel: m *= 1.05 # Diesel disukai untuk jalan berat

    # 2. NIAGA
    if "niaga" in needs:
        if _is_large_commercial_dim(dimL, dimW, dimH) or SEG_PICKUP.search(seg) or "van" in seg: m *= 1.20
        elif is_sedan or (is_mpv_boxy and length > 4800): m *= 0.80

    # 3. FUN (Versi Awam: "Lincah & Responsif")
    if "fun" in needs:
        # HAPUS BONUS TURBO UNTUK MOBIL BERAT
        # Turbo di Fortuner/MU-X itu untuk ngangkat bodi berat, bukan buat ngebut lincah.
        if has_turbo_model(model):
            if is_heavy: m *= 1.00 # No bonus
            else: m *= 1.08 # Bonus Turbo cuma buat mobil ringan (Raize, Civic, dll)
        
        if is_electric: m *= 1.10 # EV instan torque = Fun
        
        # Body Type Handling
        if is_sedan or is_city_car: m *= 1.10
        if is_mpv_boxy or is_heavy: m *= 0.90 # Mobil berat/kotak mengurangi fun handling

    # 4. PERJALANAN JAUH
    if "perjalanan_jauh" in needs:
        if is_diesel: m *= 1.08
        elif is_hybrid: m *= 1.05
        if is_city_car: m *= 0.85

    # 5. PERKOTAAN
    if "perkotaan" in needs:
        if is_heavy: m *= 0.90 # Hukum mobil besar di kota
        if is_city_car or (length is not None and length < 4300): m *= 1.05

    # =========================================================
    # *** NEW: BRAND PEACE OF MIND (The "Worth It" Factor) ***
    # =========================================================
    # Orang awam merasa worth it kalau brand-nya gampang servis & jual kembali.
    # Beri bonus kecil untuk brand mainstream.
    MAINSTREAM_BRANDS = ["toyota", "honda", "daihatsu", "suzuki", "mitsubishi", "hyundai", "wuling"]
    is_mainstream = any(b in brand for b in MAINSTREAM_BRANDS)
    
    if is_mainstream:
        m *= 1.05 # Bonus 5% untuk ketenangan pikiran
    else:
        # Brand niche/eropa/baru mungkin spek bagus, tapi aftersales PR buat awam
        # Kecuali user memang cari "Fun" (Hobi), kita tahan dikit nilainya
        if "fun" not in needs and "offroad" not in needs: 
            m *= 0.98 # Sedikit penalti jika user cari mobil fungsional biasa

    # =========================================================
    # FINAL CAP: TURUNKAN DARI 1.50 -> 1.30
    # =========================================================
    # Ini kuncinya. Jangan biarkan satu mobil menumpuk bonus terlalu banyak.
    return float(np.clip(m, 0.50, 1.30))


def style_adjust_multiplier(r: pd.Series, needs: Optional[List[str]]) -> float:
    """
    Guardrail terakhir. Logika tetap sama seperti sebelumnya.
    """
    needs = needs or []
    seg = str(r.get("segmentasi") or "").lower()
    fuel_c = str(r.get("fuel_code") or "").lower()
    cc = _safe_to_float(r.get("cc_kwh_num"))
    model = str(r.get("model") or "")
    m = 1.0

    if "fun" in needs:
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_COUPE.search(seg): m *= 1.10
        if (not np.isnan(cc) and cc < 1400) and (not has_turbo_model(model)) and fuel_c not in ("e", "h"): m *= 0.90

    if "perjalanan_jauh" in needs:
        if SEG_MPV.search(seg): m *= 1.05
        if SEG_SEDAN.search(seg): m *= 1.05
        if SEG_HATCH.search(seg) or re.search(r"\bcity\b", seg): m *= 0.95

    if "keluarga" in needs:
        if SEG_MPV.search(seg): m *= 1.05
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg): m *= 0.95

    if "perkotaan" in needs:
        if SEG_HATCH.search(seg): m *= 1.08
        if SEG_SUV.search(seg) and (not np.isnan(cc) and cc <= 1500): m *= 1.05
        if SEG_MPV.search(seg) or SEG_SUV.search(seg): m *= 0.98 

    return float(np.clip(m, 0.50, 1.50))