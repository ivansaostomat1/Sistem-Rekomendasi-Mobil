# backend/utils.py

import json
import numpy as np
import pandas as pd
from typing import Optional

def month_name_to_num(m: str) -> Optional[int]:
    if pd.isna(m):
        return None
    s = str(m).strip().upper()
    mapping = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
               "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
    if s in mapping:
        return mapping[s]
    try:
        val = int(float(s))
        if 1 <= val <= 12:
            return val
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
