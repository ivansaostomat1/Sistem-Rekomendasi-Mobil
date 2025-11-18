# filters.py
import re
import numpy as np
import pandas as pd

MATIC_REGEX  = re.compile(r'\b(?:AT|A/T|AUTO(?:MATIC)?|CVT|DCT|AMT)\b', flags=re.IGNORECASE)
MANUAL_REGEX = re.compile(r'\b(?:MT|M/T|MANUAL)\b', flags=re.IGNORECASE)

def vector_match_trans(series: pd.Series, choice: str | None) -> pd.Series:
    s = series.fillna("").astype(str)
    if choice and choice.lower() == "matic":
        return s.str.contains(MATIC_REGEX, na=False)
    if choice and choice.lower() == "manual":
        return s.str.contains(MANUAL_REGEX, na=False)
    return pd.Series([True] * len(s), index=s.index)

def is_irit_row(r: pd.Series) -> bool:
    fuel = str(r.get("fuel", "")).strip().lower()
    cc = pd.to_numeric(r.get("cc_kwh", np.nan), errors="coerce")
    if "bev" in fuel or "battery" in fuel or "electric" in fuel or re.search(r"\bev\b", fuel): return True
    if "hybrid" in fuel or "phev" in fuel:  return (cc < 2500) if not pd.isna(cc) else False
    if "diesel" in fuel:                    return (cc < 2500) if not pd.isna(cc) else False
    if "bensin" in fuel or "gasoline" in fuel or "petrol" in fuel or fuel == "g":
        return (cc < 1500) if not pd.isna(cc) else False
    return False
