# file: backend/needs.py
from __future__ import annotations

from typing import Iterable, List, Any

# --- Normalisasi alias kebutuhan di backend (kanonik) ---
CANON_NEED = {
    # long trip
    "perjalanan_jauh": "perjalanan_jauh",
    "long trip": "perjalanan_jauh",
    "long_trip": "perjalanan_jauh",
    "longtrip": "perjalanan_jauh",
    "trip jauh": "perjalanan_jauh",

    # short trip / city
    "perkotaan": "perkotaan",
    "short trip": "perkotaan",
    "short_trip": "perkotaan",
    "shorttrip": "perkotaan",
    "city": "perkotaan",
    "urban": "perkotaan",

    # fun to drive
    "fun": "fun",
    "fun to drive": "fun",
    "fun_to_drive": "fun",
    "fun2drive": "fun",
    "sporty": "fun",

    # offroad
    "offroad": "offroad",
    "off road": "offroad",
    "off_road": "offroad",

    # niaga
    "niaga": "niaga",
    "usaha": "niaga",
    "commercial": "niaga",

    # keluarga
    "keluarga": "keluarga",
    "family": "keluarga",
}

NEED_SET = {"perjalanan_jauh", "perkotaan", "fun", "offroad", "niaga", "keluarga"}


def canon_need_list(raw: Iterable[Any] | None) -> List[str]:
    """
    Normalisasi list kebutuhan (dari frontend / LLM) ke bentuk kanonik
    dan hilangkan duplikat dengan menjaga urutan pertama muncul.

    Contoh:
        ["Long Trip", "keluarga", "fun to drive", "keluarga"]
        -> ["perjalanan_jauh", "keluarga", "fun"]
    """
    if not raw:
        return []

    out: List[str] = []
    seen = set()

    for n in raw:
        s = str(n).strip().lower()
        k = CANON_NEED.get(s, s)
        if k in NEED_SET and k not in seen:
            out.append(k)
            seen.add(k)

    return out
