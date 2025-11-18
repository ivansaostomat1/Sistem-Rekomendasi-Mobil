# utils.py
import json
import re
import numpy as np
import pandas as pd
from typing import Optional

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def zscore(s: pd.Series):
    s = s.astype(float)
    denom = (s.std(ddof=0) + 1e-9)
    if denom == 0 or np.isnan(denom):
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / denom

def price_fit_score(price, budget):
    if budget <= 0 or pd.isna(price):
        return 0.0
    return max(0.0, 1.0 - abs(price - budget) / (budget + 1e-9))

def contains_ci(series: pd.Series, val):
    return series.fillna("").astype(str).str.lower().str.contains(str(val).lower(), na=False)

def month_name_to_num(m: str) -> Optional[int]:
    if pd.isna(m): return None
    s = str(m).strip().upper()
    mapping = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
    if s in mapping: return mapping[s]
    try:
        val = int(float(s))
        if 1 <= val <= 12: return val
    except Exception:
        pass
    return None

def _read_json_flex(path: str) -> pd.DataFrame:
    try:
        return pd.read_json(path)
    except ValueError:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
            return pd.json_normalize(raw["data"])
        return pd.json_normalize(raw)

def get_standard_depreciation_rate(years: float) -> float:
    years = max(0, float(years))
    if years == 0:
        return 1.0
    value = 1.0
    if years >= 1:
        value *= (1.0 - 0.20); years_left = years - 1
    else:
        return 1.0 - (0.20 * years)
    if years_left >= 1:
        value *= (1.0 - 0.15); years_left -= 1
    elif years_left > 0:
        value *= (1.0 - (0.15 * years_left)); return value
    if years_left > 0:
        value *= ((1.0 - 0.10) ** years_left)
    return value
