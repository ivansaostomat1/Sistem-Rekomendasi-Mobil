# config.py
import os
import pandas as pd

# direktori data
DATA_DIR = os.environ.get("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)

def _p(*parts: str) -> str:
    import os
    return os.path.join(DATA_DIR, *parts)

# jendela waktu
WINDOW_START = pd.Timestamp("2025-01-01")
WINDOW_END   = pd.Timestamp("2025-09-30")  # inklusif

# pola/nama file
ALLOWED_SPEC_FILENAME = "daftar_mobil.json"
RETAIL_GLOB    = "Retail_*.json"
WHOLESALE_GLOB = "Wholesale_*.json"
