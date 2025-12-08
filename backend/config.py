# file: backend/config.py
from __future__ import annotations

import os
import pandas as pd

# Direktori data utama
DATA_DIR = os.environ.get("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)


def _p(*parts: str) -> str:
    """
    Join path relatif terhadap DATA_DIR.
    Contoh: _p("Retail_2024.json") -> "./data/Retail_2024.json"
    """
    return os.path.join(DATA_DIR, *parts)


# Jendela waktu (kalau nanti dipakai di analisis tren)
WINDOW_START = pd.Timestamp("2025-01-01")
WINDOW_END = pd.Timestamp("2025-09-30")  # inklusif

# Pola / nama file
ALLOWED_SPEC_FILENAME = "daftar_mobil.json"
RETAIL_GLOB = "Retail_*.json"
WHOLESALE_GLOB = "Wholesale_*.json"
