# file: backend/common_utils.py
from __future__ import annotations
from typing import Any, Dict, List
import pandas as pd
import numpy as np

# Import logika gambar canggih
from .images import find_best_image_url

FUEL_LABEL_MAP = {
    "g": "Bensin",
    "d": "Diesel",
    "h": "Hybrid",
    "p": "PHEV",
    "e": "Listrik (BEV)",
    "o": "Lainnya"
}

def attach_images(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menambahkan kolom 'image_url' ke DataFrame hasil rekomendasi.
    """
    if df.empty:
        df["image_url"] = "/cars/default.jpg"
        return df

    # Helper function per baris
    def _get_url(row):
        brand = str(row.get("brand", "")).strip()
        model = str(row.get("model", "")).strip()
        
        # Panggil logika pencocokan gambar canggih
        url = find_best_image_url(brand, model)
        
        # Debugging ringan jika perlu (bisa dikomentari)
        # print(f"[img] {brand} | {model} -> {url}")
        
        return url

    df["image_url"] = df.apply(_get_url, axis=1)
    return df

def df_to_items(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Konversi DataFrame ke List of Dict untuk dikirim sebagai JSON.
    Mengurus handling NaN/Infinity agar JSON valid.
    """
    if df.empty:
        return []
    
    # Ganti NaN/Inf dengan None
    clean_df = df.replace([np.inf, -np.inf], np.nan)
    clean_df = clean_df.where(pd.notnull(clean_df), None)
    
    return clean_df.to_dict(orient="records")