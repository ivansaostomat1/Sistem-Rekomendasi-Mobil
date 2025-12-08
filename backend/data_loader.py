# file: backend/data_loader.py
from __future__ import annotations
import pandas as pd

# Kita import fungsi canggih dari loaders.py milik Anda
from .loaders import load_specs, load_retail_brand_multi, load_wholesale_model_multi
from .spk_features import build_master

# Variable global untuk caching (Singleton)
_CACHED_MASTER_DF: pd.DataFrame | None = None

def reload_master_data() -> pd.DataFrame:
    """
    Fungsi utama untuk me-reload data:
    1. Panggil loaders.py untuk baca raw data
    2. Panggil build_master untuk hitung skor jual kembali dll
    3. Simpan di cache
    """
    global _CACHED_MASTER_DF
    
    print("[LOADER] Memuat spesifikasi mobil...")
    try:
        specs = load_specs()
    except Exception as e:
        print(f"[ERROR] Gagal load specs: {e}")
        return pd.DataFrame() # Return empty kalau gagal total

    # Load Sales Data (Opsional - Try Except agar tidak crash kalau file json sales tidak lengkap)
    try:
        print("[LOADER] Memuat data retail sales...")
        # Sesuaikan tahun start/end dengan data yang Anda punya
        retail_share = load_retail_brand_multi(start_year=2020, end_year=2025)
    except Exception as e:
        print(f"[WARN] Gagal load retail sales (menggunakan default 0): {e}")
        # Bikin dataframe dummy kalau gagal
        retail_share = pd.DataFrame(columns=["brand_key", "brand_share_ratio"])

    try:
        print("[LOADER] Memuat data wholesale...")
        wh_features = load_wholesale_model_multi(start_year=2020, end_year=2025)
    except Exception as e:
        print(f"[WARN] Gagal load wholesale (menggunakan default 0): {e}")
        wh_features = pd.DataFrame(columns=["brand_key", "model_key", "wh_avg_window", "trend_3v3"])

    # Panggil fungsi core SPK untuk menggabungkan semuanya
    print("[LOADER] Menjalankan build_master...")
    df_final = build_master(specs, wh_features, retail_share, pred_years=3.0)
    
    # Reset index & Cache
    df_final = df_final.reset_index(drop=True)
    _CACHED_MASTER_DF = df_final
    
    print(f"[LOADER] Selesai. Total {len(df_final)} varian mobil siap.")
    return df_final

def get_master_data() -> pd.DataFrame:
    """
    Fungsi ini yang akan dipanggil oleh Chatbot & API.
    """
    global _CACHED_MASTER_DF
    if _CACHED_MASTER_DF is None:
        return reload_master_data()
    return _CACHED_MASTER_DF