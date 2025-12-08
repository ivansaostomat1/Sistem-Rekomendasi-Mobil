# file: backend/spk_utils.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
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

# --- DARI FILTERS.PY (Pilihan Anda) ---
MATIC_REGEX = re.compile(
    r"\b(?:AT|A/T|AUTO(?:MATIC)?|CVT|DCT|AMT|E-CVT|IVT|DSG|PDK)\b",
    flags=re.IGNORECASE,
)
MANUAL_REGEX = re.compile(
    r"\b(?:MT|M/T|MANUAL)\b",
    flags=re.IGNORECASE,
)

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
    """
    Sederhana: score 1.0 jika price <= budget, else turun linear sampai cap 1.15*budget.
    (Fungsi ini dipertahankan untuk penggunaan lain; bukan pengontrol utama rule 100jt.)
    """
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


def _norm_brand_token(s: str) -> str:
    """
    Normalisasi nama brand:
    - lowercase
    - buang karakter non-alfanumerik
    - kompres huruf berulang: 'cherry' -> 'chery', 'tooyota' -> 'toyota'
    """
    t = str(s or "").strip().lower()
    t = re.sub(r"[^a-z0-9]+", "", t)
    t = re.sub(r"(.)\1+", r"\1", t)
    return t


def brand_match_mask(series: pd.Series, term: str | List[str]) -> pd.Series:
    """
    Matching brand yang lebih toleran ejaan.
    """
    if term is None or (isinstance(term, str) and not term.strip()):
        return pd.Series(True, index=series.index)

    if isinstance(term, (list, tuple, set)):
        raw_terms = [str(t) for t in term if str(t).strip()]
    else:
        raw_terms = [str(term)]

    if not raw_terms:
        return pd.Series(True, index=series.index)

    norm_terms = {_norm_brand_token(t) for t in raw_terms}
    s_norm = series.fillna("").astype(str).map(_norm_brand_token)

    return s_norm.isin(norm_terms)


def _norm_trans(s: str) -> str:
    """
    (Deprecated) Digantikan oleh Regex logic di bawah, tapi dibiarkan 
    jika ada file lama yg import.
    """
    return str(s).lower()


def vector_match_trans(series: pd.Series, choice: str | List[str] | None) -> pd.Series:
    """
    Pilih baris yang cocok dengan preferensi transmisi MENGGUNAKAN REGEX (Simple Logic).
    - "matic"  -> cocok pola MATIC_REGEX (AT, CVT, DCT, dll)
    - "manual" -> cocok pola MANUAL_REGEX (MT, Manual)
    """
    # 1. Handle input list/string
    if not choice:
        return pd.Series(True, index=series.index)

    targets = set()
    if isinstance(choice, (list, tuple, set)):
        for c in choice:
            if c: targets.add(str(c).lower().strip())
    else:
        targets.add(str(choice).lower().strip())

    # Jika user pilih keduanya atau kosong, return True
    if not targets or ({"matic", "manual"}.issubset(targets)):
        return pd.Series(True, index=series.index)

    s = series.fillna("").astype(str)
    
    # Logic matching
    mask = pd.Series(False, index=series.index)
    
    if "matic" in targets:
        mask |= s.str.contains(MATIC_REGEX, na=False)
    
    if "manual" in targets:
        mask |= s.str.contains(MANUAL_REGEX, na=False)
        
    return mask


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
    Normalisasi teks bahan bakar ke kode g/d/h/p/e/o.
    """
    s = str(v or "").strip().lower()
    if not s or s in {"na", "n/a", "-"}:
        return "o"

    if s in {"g", "d", "h", "p", "e"}:
        return s

    if "phev" in s or "plug-in" in s or "plugin" in s or "plug in" in s:
        return "p"

    if "hybrid" in s or "hev" in s:
        return "h"

    if (
        "bev" in s
        or "battery" in s
        or "electric" in s
        or s in {"ev", "full ev", "full electric"}
    ):
        return "e"

    if "diesel" in s or "dsl" in s or "solar" in s or s == "d":
        return "d"

    if "bensin" in s or "gasoline" in s or "petrol" in s or s == "g":
        return "g"

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
    # Utility untuk debug jumlah baris, bisa di-comment kalau production
    # try:
    #     print(f"[dbg] {tag}: {len(df)}")
    # except Exception:
    #     pass
    return df


def _ensure_df(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df, pd.DataFrame):
        return df
    return pd.DataFrame(
        columns=["rank","points","brand","model","price","fit_score","fuel","fuel_code","trans","seats","cc_kwh","alasan"]
    )


# ============================
# price_fit_anchor (DIREVISI)
# ============================
def price_fit_anchor(price: float, budget: float, pmax_cand: float) -> float:
    """
    Logika Harga Cerdas V3 — versi dengan aturan "tidak boleh lebih murah > 100 juta dari budget".

    Perilaku:
    - Jika price >= cap_hi (budget * 1.15) -> 0.0 (terlalu mahal)
    - Jika price < (budget - 100_000_000) -> 0.0 (terlalu murah; beda kelas)
    - Zona ideal:
        * Jika price dalam [budget - 100jt, budget] -> skor naik linear dari 0.5 -> 1.0 (mendekati budget lebih baik)
        * Jika price dalam (budget, cap_hi) -> turun linear dari 1.0 -> 0.0
    - Parameter pmax_cand tidak dipakai langsung di sini tetapi disimpan untuk kompatibilitas caller.
    """
    # Validasi input
    if not (np.isfinite(price) and np.isfinite(budget)) or budget <= 0:
        return 0.0

    # Toleransi atas/bawah
    cap_hi = 1.15 * budget
    max_down = 100_000_000.0  # batas bawah maksimal selisih (100 juta)
    lower_limit = budget - max_down

    # Jika kandidat terlalu mahal -> nol
    if price >= cap_hi:
        return 0.0

    # Jika kandidat terlalu murah (lebih dari 100jt di bawah budget) -> nol
    # (aturan yang Anda minta)
    if price < lower_limit:
        return 0.0

    # Jika kandidat sedikit di atas budget -> turun linear ke cap_hi
    if price > budget:
        return max(0.0, 1.0 - (price - budget) / (cap_hi - budget))

    # Pada rentang [lower_limit, budget] kita beri nilai progresif: dari 0.5 -> 1.0
    # sehingga mobil yang dekat ke bawah batas tetap mendapat minimal skor 0.5
    if price >= lower_limit:
        # Hindari pembagian nol jika budget == lower_limit (sangat kecil budget)
        denom = (budget - lower_limit) if (budget - lower_limit) > 0 else 1.0
        ratio = (price - lower_limit) / denom  # 0..1
        return float(0.5 + 0.5 * ratio)

    # Fallback
    return 0.0
