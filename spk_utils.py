# file: spk_utils.py
from __future__ import annotations
from typing import Any, Dict, List
import re
import numpy as np
import pandas as pd

# ============================================================
# Konstanta & Regex Segmen / Kebutuhan
# ============================================================

SEG_SEDAN   = re.compile(r"\bsedan\b", re.I)
SEG_HATCH   = re.compile(r"\bhatch", re.I)
SEG_COUPE   = re.compile(r"\bcoupe\b", re.I)
SEG_MPV     = re.compile(r"\b(?:mpv|van|minibus)\b", re.I)
SEG_SUV     = re.compile(r"\b(?:suv|crossover)\b", re.I)
SEG_PICKUP  = re.compile(r"\b(?:pick\s*up|pickup|pu|light\s*truck|chassis)\b", re.I)

NEED_LABELS = ["perjalanan_jauh", "keluarga", "fun", "perkotaan", "niaga", "offroad"]


# ============================================================
# Util umum (statistik, string, dsb.)
# ============================================================

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

    compact = re.sub(r"[\s\-/_.]+", "", t)

    matic_keys = [
        "at", "automatic", "auto", "cvt", "dct", "amt",
        "ecvt", "e-cvt", "dualclutch", "duaclutch"
    ]
    if any(k in compact for k in matic_keys):
        return "matic"

    manual_keys = ["mt", "manual"]
    if any(k in compact for k in manual_keys):
        return "manual"

    return ""


def vector_match_trans(series: pd.Series, choice: str | List[str] | None) -> pd.Series:
    """
    Filter transmisi berbasis kategori 'matic' / 'manual'.
    """
    if not choice:
        return pd.Series(True, index=series.index)

    if isinstance(choice, (list, tuple, set)):
        normalized_choices = { _norm_trans(c) for c in choice if _norm_trans(c) }
    else:
        c_norm = _norm_trans(choice)
        normalized_choices = {c_norm} if c_norm else set()

    if not normalized_choices:
        return pd.Series(True, index=series.index)

    if normalized_choices == {"matic", "manual"}:
        return pd.Series(True, index=series.index)

    trans_norm = series.astype(str).map(_norm_trans)
    return trans_norm.isin(normalized_choices)


def get_standard_depreciation_rate(years: float) -> float:
    anchors: Dict[int, float] = {0: 1.00, 1: 0.80, 2: 0.70, 3: 0.60, 4: 0.52, 5: 0.45, 6: 0.40, 7: 0.36}
    if years <= 0:
        return 1.0
    if years >= 7:
        return anchors[7]
    lo = int(np.floor(years)); hi = int(np.ceil(years))
    if lo == hi:
        return anchors.get(lo, 0.6)
    frac = years - lo
    return anchors.get(lo, 0.6) * (1 - frac) + anchors.get(hi, 0.45) * frac


def fuel_to_code(v: str) -> str:
    """
    Normalisasi teks bahan bakar ke kode:
    g = bensin
    d = diesel
    h = hybrid (HEV)
    p = PHEV
    e = BEV / EV
    o = lainnya / tidak jelas
    """
    s = str(v or "").strip().lower()
    if not s or s in {"na", "n/a", "-"}:
        return "o"

    # 1) kalau sudah berupa kode langsung, jangan diutak–atik lagi
    if s in {"g", "d", "h", "p", "e"}:
        return s

    # 2) deteksi PHEV
    if "phev" in s or "plug-in" in s or "plugin" in s or "plug in" in s:
        return "p"

    # 3) deteksi hybrid (HEV)
    if "hybrid" in s or "hev" in s:
        return "h"

    # 4) deteksi BEV / EV
    if (
        "bev" in s
        or "battery" in s
        or "electric" in s
        or s in {"ev", "full ev", "full electric"}
    ):
        return "e"

    # 5) diesel
    if "diesel" in s or "dsl" in s or "solar" in s or s == "d":
        return "d"

    # 6) bensin / gasoline
    if "bensin" in s or "gasoline" in s or "petrol" in s or s == "g":
        return "g"

    # default: lainnya
    return "o"



def _series_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


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


def _ensure_df(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df, pd.DataFrame):
        return df
    return pd.DataFrame(
        columns=["rank","points","brand","model","price","fit_score","fuel","fuel_code","trans","seats","cc_kwh","alasan"]
    )


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
