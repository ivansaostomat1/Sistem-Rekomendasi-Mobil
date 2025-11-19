# spk.py
from __future__ import annotations
from typing import Dict, Any, List
import re
import time
import numpy as np
import pandas as pd

# Import klastering (akan ditangani try/except di pemanggilan)
from klastering import cluster_and_label, need_similarity_scores

# ============================================================
# ---------------------- UTIL MANDIRI ------------------------
# ============================================================
SEG_SEDAN   = re.compile(r"\bsedan\b", re.I)
SEG_HATCH   = re.compile(r"\bhatch", re.I)
SEG_COUPE   = re.compile(r"\bcoupe\b", re.I)
SEG_MPV     = re.compile(r"\b(?:mpv|van|minibus)\b", re.I)
SEG_SUV     = re.compile(r"\b(?:suv|crossover)\b", re.I)
SEG_PICKUP  = re.compile(r"\b(?:pick\s*up|pickup|pu|light\s*truck|chassis)\b", re.I)

NEED_LABELS = ["perjalanan_jauh", "keluarga", "fun", "perkotaan", "niaga", "offroad"]

def zscore(x: pd.Series | np.ndarray) -> np.ndarray:
    a = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
    m = np.nanmean(a) if np.isfinite(np.nanmean(a)) else 0.0
    s = np.nanstd(a) if np.isfinite(np.nanstd(a)) and np.nanstd(a) > 0 else 1.0
    return (a - m) / s

def sigmoid(x: Any) -> np.ndarray:
    a = pd.to_numeric(pd.Series(x), errors="coerce").fillna(0).to_numpy(dtype=float)
    return 1.0 / (1.0 + np.exp(-a))

def price_fit_score(price: float, budget: float) -> float:
    if not np.isfinite(budget) or budget <= 0 or not np.isfinite(price):
        return 0.0
    if price <= budget:
        return 1.0
    cap = budget * 1.15
    if price >= cap:
        return 0.0
    return float(1.0 - (price - budget) / (cap - budget))

def contains_ci(series: pd.Series, term: str | List[str]) -> pd.Series:
    if term is None or (isinstance(term, str) and not term.strip()):
        return pd.Series(True, index=series.index)
    if isinstance(term, (list, tuple, set)):
        pat = "|".join([re.escape(str(t)) for t in term if str(t).strip()])
    else:
        pat = re.escape(str(term).strip())
    if not pat:
        return pd.Series(True, index=series.index)
    return series.astype(str).str.contains(pat, case=False, regex=True, na=False)

def _norm_trans(s: str) -> str:
    """
    Normalisasi teks transmisi ke kode sederhana:
    - 'matic' untuk AT / CVT / DCT / otomatis
    - 'manual' untuk MT / manual
    - '' kalau tidak dikenali
    """
    t = str(s or "").strip().lower()
    if not t:
        return ""

    # satukan spasi, '-' dan '/' supaya 'A/T', '6 AT', '6AT' jadi mirip
    compact = re.sub(r"[\s\-/_.]+", "", t)

    # --- grup matic / automatic ---
    matic_keys = [
        "at", "automatic", "auto", "cvt", "dct", "amt",
        "ecvt", "e-cvt", "dualclutch", "duaclutch"
    ]
    if any(k in compact for k in matic_keys):
        return "matic"

    # --- grup manual ---
    manual_keys = ["mt", "manual"]
    if any(k in compact for k in manual_keys):
        return "manual"

    return ""


def vector_match_trans(series: pd.Series, choice: str | List[str] | None) -> pd.Series:
    """
    Filter transmisi berbasis kategori 'matic' / 'manual', dengan normalisasi
    dari berbagai bentuk teks (AT, A/T, CVT, MT, Manual, dsb).
    """
    # Tidak ada pilihan -> jangan filter
    if not choice:
        return pd.Series(True, index=series.index)

    # Normalisasi pilihan user
    if isinstance(choice, (list, tuple, set)):
        normalized_choices = { _norm_trans(c) for c in choice if _norm_trans(c) }
    else:
        c_norm = _norm_trans(choice)
        normalized_choices = {c_norm} if c_norm else set()

    # Kalau setelah normalisasi kosong (user kirim string aneh), JANGAN bunuh semua kandidat
    if not normalized_choices:
        return pd.Series(True, index=series.index)

    # Kalau user memilih dua-duanya (matic & manual) -> anggap tidak difilter
    if normalized_choices == {"matic", "manual"}:
        return pd.Series(True, index=series.index)

    # Normalisasi kolom transmisi di data
    trans_norm = series.astype(str).map(_norm_trans)

    # Hanya ambil yang masuk kategori yang diminta
    return trans_norm.isin(normalized_choices)

def get_standard_depreciation_rate(years: float) -> float:
    anchors = {0: 1.00, 1: 0.80, 2: 0.70, 3: 0.60, 4: 0.52, 5: 0.45, 6: 0.40, 7: 0.36}
    if years <= 0:
        return 1.0
    if years >= 7:
        return anchors[7]
    lo = int(np.floor(years)); hi = int(np.ceil(years))
    if lo == hi:
        return anchors.get(lo, 0.6)
    frac = years - lo
    return anchors.get(lo, 0.6) * (1 - frac) + anchors.get(hi, 0.45) * frac

# ============================================================
# ------------------- PARSER & NORMALISASI -------------------
# ============================================================

_TURBO_POS = re.compile(
    r"""
    (?:\bTurbo\b)
    |(?:\b\d+(?:\.\d+)?\s*T\b)
    |(?:\b\d+(?:\.\d+)?T\b)
    |(?:\b(?:TSI|TFSI|T-GDI|GDI-T|EcoBoost|BoosterJet|VTEC\s*Turbo|TwinPower\s*Turbo|D-4T)\b)
    """, re.IGNORECASE | re.VERBOSE
)

def has_turbo(model: str) -> bool:
    s = str(model or "")
    s = re.sub(r"\b(CVT|A/T|AT|M/T|MT|DCT)\b", " ", s, flags=re.IGNORECASE)
    return bool(_TURBO_POS.search(s))

def _to_float(x, default=np.nan):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return default

def _parse_dims_pxlxt(s: str):
    t = str(s)
    nums = re.findall(r"[\d.]+", t.replace(",", "."))
    vals = [_to_float(n) for n in nums[:3]]
    if len(vals) < 3:
        return np.nan, np.nan, np.nan
    p, l, h = vals
    scale = 1000 if p < 100 else 1
    return p * scale, l * scale, h * scale

def _parse_wheel_size(s: str):
    st = str(s).upper().replace(" ", "")
    rim = re.search(r"R(\d{2})", st)
    rim_inch = _to_float(rim.group(1)) if rim else np.nan
    w = re.search(r"(\d{3})/\d{2}", st)
    tyre_w_mm = _to_float(w.group(1)) if w else np.nan
    return tyre_w_mm, rim_inch

def _has_awd_text(text: str) -> float:
    s = str(text or "").upper()
    return 1.0 if any(k in s for k in ["4X4", "4WD", "AWD"]) else 0.0

def fuel_to_code(v: str) -> str:
    s = str(v or "").strip().lower()
    if not s or s in {"na", "n/a", "-"}:
        return "o"
    if "phev" in s or "plug-in" in s or "plugin" in s or "plug in" in s:
        return "p"
    if "hybrid" in s or "hev" in s:
        return "h"
    if "bev" in s or "battery" in s or "electric" in s or s == "ev":
        return "e"
    if s == "d" or "diesel" in s or "dsl" in s or "solar" in s:
        return "d"
    if s == "g" or "bensin" in s or "gasoline" in s or "petrol" in s:
        return "g"
    return "o"

# ---------- Helper pick kolom (robust alias) ----------
def _pick_str(df: pd.DataFrame, names: List[str], default: str = "") -> pd.Series:
    for n in names:
        if n in df.columns:
            return df[n].astype(str)
    return pd.Series([default] * len(df), index=df.index, dtype="object")

def _pick_num(df: pd.DataFrame, names: List[str]) -> pd.Series:
    for n in names:
        if n in df.columns:
            return pd.to_numeric(df[n], errors="coerce")
    return pd.Series([np.nan] * len(df), index=df.index, dtype="float64")

def add_need_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # --- kolom dasar ---
    seats = _pick_num(out, ["seats", "seat", "kursi", "jumlah_kursi", "seating", "seating_capacity"])
    out["seats"] = seats

    trans = _pick_str(out, ["trans", "transmission", "gearbox"], default="")
    out["trans"] = trans

    seg = _pick_str(
        out,
        ["segmentasi", "body_type", "body", "bodystyle", "jenis_bodi", "type", "segmen", "kategori"],
        ""
    )
    out["segmentasi"] = seg

    out["wheelbase_mm"] = _pick_num(out, ["WHEEL BASE", "WHEELBASE", "wheelbase", "Wheelbase (mm)"])

    # --- DIMENSI ---
    dims_raw = _pick_str(out, [
        "DIMENSION P x L x T", "DIMENSION P x L xT", "DIMENSION PxLxT",
        "Dimension (P x L x T)", "Dimensi (P x L x T)",
        "dimensions", "dimensi", "size"
    ], default="")

    Ls, Ws, Hs = [], [], []
    for s in dims_raw:
        p, l, h = _parse_dims_pxlxt(s)
        Ls.append(p); Ws.append(l); Hs.append(h)
    out["length_mm"] = pd.to_numeric(pd.Series(Ls, index=out.index), errors="coerce")
    out["width_mm"]  = pd.to_numeric(pd.Series(Ws, index=out.index), errors="coerce")
    out["height_mm"] = pd.to_numeric(pd.Series(Hs, index=out.index), errors="coerce")

    # --- BAN & PELEK ---
    tyre_raw = _pick_str(out, ["WHEEL & TYRE SIZE", "WHEEL & TIRE SIZE", "TIRE SIZE", "TYRE SIZE", "Ban & Velg"], "")
    TWs, Rims = [], []
    for s in tyre_raw:
        tw, rim = _parse_wheel_size(s)
        TWs.append(tw); Rims.append(rim)
    out["tyre_w_mm"] = pd.to_numeric(pd.Series(TWs, index=out.index), errors="coerce")
    out["rim_inch"]  = pd.to_numeric(pd.Series(Rims, index=out.index), errors="coerce")

    # --- berat & cc/kwh ---
    out["vehicle_weight_kg"] = _pick_num(out, ["vehicle_weight", "weight", "curb_weight", "berat", "berat_kosong"])
    out["cc_kwh_num"]       = _pick_num(out, ["cc_kwh", "cc", "engine_cc", "kapasitas_mesin", "engine", "battery_kwh", "kwh"])

    # --- JUMLAH PINTU ---
    out["doors_num"] = _pick_num(out, ["doors", "door", "pintu", "num_door", "jumlah_pintu"])

    # --- AWD: gabungan teks penggerak + model/varian sebagai hint ---
    drivestr   = _pick_str(out, ["drive_sys", "DRIVE SYS", "DRIVE SYSTEM", "DRIVETRAIN", "DRIVE TRAIN", "penggerak", "penggerak roda"], "")
    model_hint = _pick_str(out, ["model", "type model", "type_model", "variant"], "")
    awd_text   = (drivestr + " " + model_hint).astype(str)
    out["awd_flag"] = awd_text.apply(_has_awd_text).astype(float)

    # --- fuel code ---
    fuel_str = _pick_str(out, ["fuel", "fuel type", "fuel_type", "bahan bakar", "jenis_bahan_bakar"], "")
    out["fuel_code"] = fuel_str.apply(fuel_to_code)

    return out

# ============================================================
# ------------- ATURAN PILIHAN KEBUTUHAN (SANITASI) ----------
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
            needs.append(n); seen.add(n)
    needs = _resolve_pair_keep_first(needs, "fun", "offroad")
    needs = _resolve_pair_keep_first(needs, "fun", "niaga")
    needs = _resolve_pair_keep_first(needs, "perjalanan_jauh", "perkotaan")
    if len(needs) > 3:
        needs = needs[:3]
    return needs

# ============================================================
# ------------------ HARD CONSTRAINTS (WAJIB) ----------------
# ============================================================

def has_turbo_model(model: str) -> bool:
    return has_turbo(model)

def is_fast_enough(cc_s: pd.Series, model_s: pd.Series, fuel_s: pd.Series) -> pd.Series:
    cc_ok    = pd.to_numeric(cc_s, errors="coerce").fillna(0) >= 1500
    turbo_ok = model_s.astype(str).apply(has_turbo_model)
    fuel_ok  = fuel_s.astype(str).str.lower().isin(["h","p","e"])  # HEV/PHEV/BEV
    return cc_ok | turbo_ok | fuel_ok

def _series_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")

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
    seg   = cand_feat["segmentasi"].astype(str) if "segmentasi" in cand_feat.columns else pd.Series([""] * n, index=cand_feat.index, dtype="object")
    model = cand_feat["model"].astype(str) if "model" in cand_feat.columns else pd.Series([""] * n, index=cand_feat.index, dtype="object")
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

    # persentil untuk "kompak" & "besar"
    p_len40 = float(np.nanpercentile(length.dropna(), 40)) if length.notna().any() else np.inf
    p_wid40 = float(np.nanpercentile(width.dropna(),  40)) if width.notna().any()  else np.inf
    p_wgt50 = float(np.nanpercentile(weight.dropna(), 50)) if weight.notna().any() else np.inf
    p_wb60  = float(np.nanpercentile(wb.dropna(),     60)) if wb.notna().any()     else -np.inf
    p_len60 = float(np.nanpercentile(length.dropna(), 60)) if length.notna().any() else -np.inf

    # proxy power-to-weight
    pw = _pw_series(cc, weight)
    p_pw55 = float(np.nanpercentile(pw.dropna(), 55)) if pw.notna().any() else -np.inf

    # cepat (FUN)
    turbo_ok = model.apply(has_turbo_model)
    fuel_ok  = fuel.str.lower().isin(["h","p","e"])
    cc_ok    = cc >= 1500
    rim_ok   = (rim >= 17) | (tyr >= 205)
    pw_ok    = pw >= p_pw55
    fast_ok  = turbo_ok | fuel_ok | (cc_ok & (pw_ok | rim_ok))

    # mulai dari semua True
    mask = pd.Series(True, index=cand_feat.index)

    # --- KOMBO: fun + keluarga + perkotaan -> WAJIB ≥4 pintu ---
    if {"fun", "keluarga", "perkotaan"}.issubset(set(needs)):
        idx = cand_feat.index

        # doors sebagai Series berindeks sama
        if "doors_num" in cand_feat.columns:
            doors_s = pd.to_numeric(cand_feat["doors_num"], errors="coerce").reindex(idx)
        else:
            doors_s = pd.Series(np.nan, index=idx, dtype="float64")

        # deteksi 2-door via teks (non-capturing group)
        two_dr_pat = r"\b(?:2[\s\-]?door|2dr|two\s*door)\b"
        if "model" in cand_feat.columns:
            two_dr_txt = cand_feat["model"].astype(str).str.contains(two_dr_pat, flags=re.I, regex=True, na=False).reindex(idx)
        else:
            two_dr_txt = pd.Series(False, index=idx)

        if "segmentasi" in cand_feat.columns:
            two_dr_seg = cand_feat["segmentasi"].astype(str).str.contains(r"\bcoupe\b", flags=re.I, regex=True, na=False).reindex(idx)
        else:
            two_dr_seg = pd.Series(False, index=idx)

        two_dr_hint = (two_dr_txt | two_dr_seg).fillna(False)

        # Aturan final:
        # - Jika doors_num ada -> wajib >=4
        # - Jika doors_num NaN -> gugurkan hanya jika ada hint 2-door
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
        forbid_sedan = seg.str.contains(r"\bsedan\b", flags=re.I, regex=True, na=False)
        mask &= ~forbid_sedan
        mask &= (awd >= 0.5)

    # --- perkotaan (short trip) ---
    if "perkotaan" in needs:
        small = ((length <= p_len40) | length.isna()) & ((width <= p_wid40) | width.isna()) & ((weight <= p_wgt50) | weight.isna())
        efficient = fuel.str.lower().isin(["h","p","e"]) | (cc <= 1500) | cc.isna()
        if "fun" in needs:
            mask &= (small & efficient) | (fast_ok & efficient)
        else:
            mask &= small & efficient

    # --- fun (wajib cepat) ---
    if "fun" in needs:
        mask &= fast_ok
        if "perjalanan_jauh" not in needs:
            not_suv = ~seg.str.contains(r"\b(?:suv|crossover)\b", flags=re.I, regex=True, na=False)
            mask &= not_suv
        if "perkotaan" in needs:
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

    return mask

# ============================================================
# ----------------- SOFT SCORING & PERSENTIL -----------------
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

    length = float(pd.to_numeric(r.get("length_mm"), errors="coerce") or np.nan)
    width  = float(pd.to_numeric(r.get("width_mm"),  errors="coerce") or np.nan)
    weight = float(pd.to_numeric(r.get("vehicle_weight_kg"), errors="coerce") or np.nan)
    wb     = float(pd.to_numeric(r.get("wheelbase_mm"), errors="coerce") or np.nan)
    cc     = float(pd.to_numeric(r.get("cc_kwh_num"), errors="coerce") or np.nan)
    rim    = float(pd.to_numeric(r.get("rim_inch"), errors="coerce") or np.nan)
    tyr    = float(pd.to_numeric(r.get("tyre_w_mm"), errors="coerce") or np.nan)
    awd    = float(pd.to_numeric(r.get("awd_flag"), errors="coerce") or 0.0)
    seats  = float(pd.to_numeric(r.get("seats"), errors="coerce") or 0.0)
    fuel_c = str(r.get("fuel_code") or "").lower()
    seg    = str(r.get("segmentasi") or "").lower()
    model  = str(r.get("model") or "")

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
            big = (length >= P["len_p70"]) or (width >= P["wid_p60"]) or (weight >= P["wgt_p60"])
            m *= 0.97 if big else 1.0
        if re.search(r"\b(mpv|van|minibus|suv|crossover)\b", seg, flags=re.I):
            m *= 0.98

    # Keluarga
    if "keluarga" in needs:
        roomy = (seats >= 7) or ((seats >= 6) and (wb >= P["wb_p60"]) and (width >= P["wid_p60"]))
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
        if SEG_MPV.search(seg):   m *= 0.90
        if SEG_SUV.search(seg):   m *= 0.96
        if SEG_SEDAN.search(seg) or SEG_HATCH.search(seg) or SEG_COUPE.search(seg):
            m *= 1.06
        if (cc and cc < 1400) and (not has_turbo_model(model)):
            m *= 0.92

    if "perjalanan_jauh" in needs:
        if fuel_c == "d":  m *= 1.04
        if SEG_SEDAN.search(seg): m *= 1.02

    if "keluarga" in needs:
        seats = float(pd.to_numeric(r.get("seats"), errors="coerce") or 0.0)
        if seats >= 7: m *= 1.03
        if SEG_MPV.search(seg): m *= 1.02

    if "perkotaan" in needs:
        if SEG_MPV.search(seg) or SEG_SUV.search(seg): m *= 0.98
        if SEG_HATCH.search(seg): m *= 1.02

    if "offroad" in needs:
        if SEG_SUV.search(seg) or SEG_PICKUP.search(seg): m *= 1.03

    return float(np.clip(m, 0.85, 1.18))

# ============================================================
# ---------------------- BUILD MASTER ------------------------
# ============================================================

def build_master(
    specs: pd.DataFrame,
    wh_features: pd.DataFrame,
    retail_brand_share: pd.DataFrame,
    pred_years: float
) -> pd.DataFrame:
    specs = specs.copy()
    specs["brand_key_upper"] = specs["brand"].astype(str).str.strip().str.upper()

    specs_wh = specs.merge(
        wh_features,
        left_on=["brand_key_upper", "model_key"],
        right_on=["brand_key", "model_key"],
        how="left",
        suffixes=("", "_wh"),
    ).drop(columns=[c for c in ["brand_key_wh"] if c in wh_features.columns], errors="ignore")

    df = specs_wh.merge(
        retail_brand_share,
        left_on="brand_key_upper",
        right_on="brand_key",
        how="left",
        suffixes=("", "_ret"),
    ).drop(columns=[c for c in ["brand_key_ret"] if c in retail_brand_share.columns], errors="ignore")

    if "wh_avg_window" not in df.columns: df["wh_avg_window"] = 0.0
    if "trend_3v3" not in df.columns:     df["trend_3v3"] = 0.0
    df["brand_share_ratio"] = df.get("brand_share_ratio", 0.0)

    if df["wh_avg_window"].notna().sum() > 1:
        df["popularity_z"] = zscore(df["wh_avg_window"].fillna(0))
    else:
        df["popularity_z"] = 0.0

    standard_rate = get_standard_depreciation_rate(pred_years)
    df["standard_resale_rate"] = standard_rate

    market_adjustment = (
        0.15 * sigmoid(df["trend_3v3"].replace([np.inf, -np.inf], 0).fillna(0))
        + 0.05 * sigmoid(df["popularity_z"])
        + 0.05 * sigmoid(zscore(df["brand_share_ratio"]))
    )
    df["resale_multiplier"] = (standard_rate + market_adjustment)
    clip_min = max(0.30, standard_rate * 0.8)
    clip_max = min(1.0, standard_rate * 1.25) if pred_years >= 1 else 1.0
    df["resale_multiplier"] = df["resale_multiplier"].clip(clip_min, clip_max)
    df["predicted_resale_value"] = (df["price"] * df["resale_multiplier"]).round(0)

    # fuel_code pasti ada
    df["fuel_code"] = df.get("fuel", pd.Series([""]*len(df), index=df.index)).apply(fuel_to_code)

    return df.drop(columns=["brand_key_upper"], errors="ignore")

# ============================================================
# ------------------ RANKING & PRESENTATION ------------------
# ============================================================

def _ensure_df(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df, pd.DataFrame):
        return df
    return pd.DataFrame(
        columns=["rank","points","brand","model","price","fit_score","fuel","fuel_code","trans","seats","cc_kwh","alasan"]
    )

def assign_array_safe(df: pd.DataFrame, col: str, values: Any, fallback: float = 0.0):
    try:
        if isinstance(values, np.ndarray):
            arr = np.asarray(values).reshape(-1)
            if arr.shape[0] == len(df):
                df[col] = arr
            else:
                df[col] = fallback
        elif pd.api.types.is_list_like(values) and not isinstance(values, (str, bytes)):
            seq = list(values)
            if len(seq) == len(df):
                df[col] = seq
            else:
                df[col] = fallback
        elif np.isscalar(values):
            df[col] = float(values)
        else:
            df[col] = fallback
    except Exception:
        df[col] = fallback

def _dbg(tag: str, df: pd.DataFrame) -> pd.DataFrame:
    try:
        print(f"[dbg] {tag}: {len(df)}")
    except Exception:
        pass
    return df

def price_fit_anchor(price: float, budget: float, pmax_cand: float) -> float:
    """
    Anchor lembut: puncak di target = min(0.9*budget, pmax_cand)
    - Di bawah ~0.6*budget skornya kecil
    - Turun ke 0 saat 1.15*budget
    """
    if not (np.isfinite(price) and np.isfinite(budget)) or budget <= 0:
        return 0.0
    cap_hi = 1.15 * budget
    target = min(0.9 * budget, max(1.0, pmax_cand))
    lo = 0.6 * budget

    if price <= lo:
        return max(0.0, min(1.0, (price / lo) * 0.6))
    if price <= target:
        return 0.6 + 0.4 * (price - lo) / max(1.0, (target - lo))
    if price <= budget:
        return 1.0 - 0.1 * (price - target) / max(1.0, (budget - target))
    if price >= cap_hi:
        return 0.0
    return max(0.0, 1.0 - (price - budget) / max(1.0, (cap_hi - budget)))

def rank_candidates(
    df_master: pd.DataFrame,
    budget: float,
    spec_filters: Dict[str, Any],
    needs: List[str],
    topn: int = 15
) -> pd.DataFrame:
    try:
        t0 = time.perf_counter()

        needs = sanitize_needs(needs or [])

        # 1) Harga
        cap = budget * 1.15
        cand = _dbg("start", df_master[df_master["price"] <= cap].copy())
        if cand.empty:
            return _ensure_df(cand)

        # 2) Brand (opsional)
        if spec_filters.get("brand"):
            cand = _dbg("brand", cand[contains_ci(cand["brand"], spec_filters["brand"])])
            if cand.empty:
                return _ensure_df(cand)

        # 3) Transmisi (opsional)
        cand = _dbg("trans", cand[vector_match_trans(cand["trans"], spec_filters.get("trans_choice"))])
        if cand.empty:
            return _ensure_df(cand)

        # 4) Fuel multi-select (opsional)
        fuels = spec_filters.get("fuels")
        if fuels:
            want = {str(x).lower() for x in fuels}
            cand = _dbg("fuel", cand[cand["fuel_code"].isin(want)])
            if cand.empty:
                return _ensure_df(cand)

        # 5) Fitur + hard constraints
        print(f"[dbg] before_features: {len(cand)}")
        cand_feat = add_need_features(cand)
        print(f"[dbg] after_features:  {len(cand_feat)}")

        # --- hard filter ---
        hard_ok = hard_constraints_filter(cand_feat, needs or [])

        # Normalisasi hard_ok => selalu boolean Series berindeks cand_feat.index
        if not isinstance(hard_ok, pd.Series):
            hard_ok = pd.Series(bool(hard_ok), index=cand_feat.index)
        else:
            hard_ok = hard_ok.reindex(cand_feat.index)
        hard_ok = hard_ok.fillna(False).astype(bool)

        cand      = _dbg("hard_ok", cand[hard_ok])
        cand_feat = cand_feat[hard_ok]
        if cand.empty:
            return _ensure_df(cand)

        # 6) Klaster + need_score
        try:
            cand_feat2, cluster_to_label, C_scaled, feat_cols, scaler, _ = cluster_and_label(cand_feat, k=6)
            X_for_need = cand_feat2[feat_cols].apply(lambda col: col.fillna(col.median()), axis=0).values
            X_scaled = scaler.transform(X_for_need)
            need_score = need_similarity_scores(
                X_scaled, C_scaled, cand_feat2["cluster_id"].values, cluster_to_label, needs or []
            )
            cand = cand_feat2.copy()
        except Exception:
            need_score = 0.0
            cand = cand_feat.copy()

        assign_array_safe(cand, "need_score", need_score, fallback=0.0)

        # --- PRICE FEATURES: rank (p10..p90) + anchor ke budget ---
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

        # 7) SAW (need vs price)
        if needs and isinstance(need_score, np.ndarray):
            alpha_price = 0.20 if ("fun" in needs) else 0.30
            cand["fit_score"] = (1.0 - alpha_price) * cand["need_score"] + alpha_price * cand["price_fit"]
        else:
            cand["fit_score"] = cand["price_fit"]

        # 8) Soft layer + style layer
        P = compute_percentiles(cand)
        cand["soft_mult"]  = cand.apply(lambda r: soft_multiplier(r, needs or [], P), axis=1)
        cand["fit_score"]  = (cand["fit_score"] * cand["soft_mult"]).clip(0, 1.0)
        cand["style_mult"] = cand.apply(lambda r: style_adjust_multiplier(r, needs or []), axis=1)
        cand["fit_score"]  = (cand["fit_score"] * cand["style_mult"]).clip(0, 1.0)

        # 9) Alasan
        def mk_reason(r):
            why = []
            why.append("harga sesuai budget" if r["price"] <= budget else "±15% dari budget")
            if "keluarga" in (needs or []):
                min_seats = 5 if "perkotaan" in (needs or []) else 6
                why.append(f"kursi ≥{min_seats}")
            if "offroad" in (needs or []):
                why.append("AWD/4x4 & siap offroad" if r.get("awd_flag",0)>=0.5 else "butuh AWD/4x4")
            if "perkotaan" in (needs or []):
                why.append("kompak & efisien")
            if "perjalanan_jauh" in (needs or []):
                why.append("diesel cocok perjalanan jauh" if str(r.get("fuel_code","")) == "d" else "stabil & efisien jarak jauh")
            if "fun" in (needs or []):
                bits = []
                if pd.to_numeric(r.get("cc_kwh_num"), errors="coerce") >= 1600: bits.append("mesin responsif")
                if has_turbo_model(str(r.get("model",""))): bits.append("turbo")
                if r.get("awd_flag",0) >= 0.5: bits.append("traksi baik")
                if bits: why.append("fun: " + ", ".join(bits))
            return ", ".join([w for w in why if w])

        cand["alasan"] = cand.apply(mk_reason, axis=1)

        # 10) Sortir & deduplikasi
        cand["model_norm"] = cand["model"].astype(str).str.replace(r"\s+"," ",regex=True).str.strip().str.lower()
        cand["price_int"]  = pd.to_numeric(cand["price"], errors="coerce").fillna(-1).astype(int)
        cand = (
            cand.sort_values(["fit_score"], ascending=[False])
                .drop_duplicates(subset=["model_norm","price_int"], keep="first")
                .drop(columns=["model_norm","price_int"])
        )

        # 11) Rank & points
        cand = cand.reset_index(drop=True)
        cand["rank"] = cand["fit_score"].rank(ascending=False, method="first").astype(int)
        n_out = len(cand); den = max(1, n_out - 1)
        cand["points"] = (((n_out - cand["rank"]) / den) * 98 + 1).round(0).astype(int)

        # 12) Kolom tampil minimal
        show_cols = ["rank","points","brand","model","price","fit_score","fuel","fuel_code","trans","seats","cc_kwh","alasan"]
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
