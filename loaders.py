# loaders.py
import os
import re
import glob
from typing import Optional, List
import numpy as np
import pandas as pd
from pandas.tseries.offsets import DateOffset

from config import _p, DATA_DIR, ALLOWED_SPEC_FILENAME, RETAIL_GLOB, WHOLESALE_GLOB, WINDOW_START, WINDOW_END
from utils import _read_json_flex, month_name_to_num

# --------------- LOADERS ---------------
def load_specs(path=_p(ALLOWED_SPEC_FILENAME)) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Tidak menemukan '{ALLOWED_SPEC_FILENAME}' di {os.path.abspath(DATA_DIR)}.")
    df = _read_json_flex(path)

    rename_map = {
        "type model": "model",
        "harga otr (idr)": "price",
        "cc / kwh": "cc_kwh",
        "cbu / ckd": "cbu_ckd",
        "drive sys": "drive_sys",
        "segmentasi": "segmentasi",
    }
    cols_lower = {c.lower(): c for c in df.columns}
    for raw, new in rename_map.items():
        key = raw.lower()
        if key in cols_lower:
            df = df.rename(columns={cols_lower[key]: new})

    if "brand" in df.columns:
        s = df["brand"].fillna("").astype(str).str.upper()
        s = s.str.replace(r"\bMORRIS GARAGE\b", "MG", regex=True)
        s = s.str.replace(r"\bMITSUBISHI MOTORS\b", "MITSUBISHI", regex=True)
        s = s.str.replace(r"MERCEDES0BENZ", "MERCEDES BENZ", regex=True)
        s = s.str.replace(r"\s+[0(]?(HMID|PC)\)?", "", regex=True)
        s = s.str.replace(r"\s+(HMID|PC)\b", "", regex=True)
        s = s.str.replace(r"\s+0$", "", regex=True)
        df["brand"] = s.str.strip()

    required = ["brand", "model", "price"]
    for r in required:
        if r not in df.columns:
            raise ValueError(f"Kolom wajib '{r}' tidak ada di {ALLOWED_SPEC_FILENAME}.")

    df["price"]  = pd.to_numeric(df["price"], errors="coerce")
    df["cc_kwh"] = pd.to_numeric(df.get("cc_kwh", np.nan), errors="coerce")
    df["seats"]  = pd.to_numeric(df.get("seats", np.nan), errors="coerce")
    for c in ["trans","fuel","segmentasi","drive_sys","cbu_ckd","image"]:
        if c not in df.columns: df[c] = np.nan

    # keys
    df["brand_key"] = df["brand"].astype(str).str.strip().str.lower()   # lower-case
    df["model_key"] = df["model"].astype(str).str.strip().str.lower()
    return df.dropna(subset=["brand","model","price"]).reset_index(drop=True)

def load_retail_brand_multi(start_year=2020, end_year=2025) -> pd.DataFrame:
    paths = []
    for y in range(start_year, end_year+1):
        p = _p(f"Retail_{y}.json")
        if os.path.exists(p): paths.append((y, p))
    if not paths:
        raise FileNotFoundError("Tidak ada Retail_YYYY.json (2020–2025).")

    longs = []
    for year, path in paths:
        df = _read_json_flex(path)

        # normalisasi kolom brand
        brand_col = next((c for c in df.columns if str(c).strip().upper()=="BRAND"), None)
        if brand_col is None:
            brand_col = "brand" if "brand" in df.columns else df.columns[0]
        df = df.rename(columns={brand_col: "brand"})

        # dukung wide (BRAND + JAN..DEC) atau long (brand, month, sales)
        cols_lower = {c.lower(): c for c in df.columns}
        month_cols = [c for c in df.columns if month_name_to_num(str(c)) is not None]

        if month_cols:
            wide = df[["brand"] + month_cols].copy()
        elif {"brand","month","sales"}.issubset(cols_lower):
            tmp = df.rename(columns={cols_lower["brand"]:"brand",
                                     cols_lower["month"]:"month",
                                     cols_lower["sales"]:"sales"})
            tmp["month"] = tmp["month"].astype(str).str[:3].str.upper()
            wide = tmp.pivot_table(index="brand", columns="month", values="sales", aggfunc="sum").reset_index()
            wide.columns.name = None
        else:
            raise ValueError(f"Format Retail tidak dikenali: {os.path.basename(path)}")

        dfl = wide.melt(id_vars=["brand"], var_name="month_name", value_name="sales")
        dfl["month"] = dfl["month_name"].apply(month_name_to_num)
        dfl["year"]  = year
        dfl["date"]  = pd.to_datetime(dict(year=dfl["year"], month=dfl["month"], day=1), errors="coerce")
        dfl["sales"] = pd.to_numeric(dfl["sales"], errors="coerce").fillna(0)
        dfl["brand_key"] = dfl["brand"].astype(str).str.strip().str.upper()
        longs.append(dfl[["date","brand","brand_key","sales"]])

    retail_long = pd.concat(longs, ignore_index=True).dropna(subset=["date"])
    retail_long = retail_long[(retail_long["date"] >= WINDOW_START) & (retail_long["date"] <= WINDOW_END)]
    brand_sum = retail_long.groupby("brand_key")["sales"].sum()
    total     = brand_sum.sum() + 1e-9
    return pd.DataFrame({"brand_key": brand_sum.index, "brand_share_ratio": (brand_sum/total).values})

def load_wholesale_model_multi(start_year=2020, end_year=2025) -> pd.DataFrame:
    paths = []
    for y in range(start_year, end_year+1):
        p = _p(f"Wholesale_{y}.json")
        if os.path.exists(p): paths.append((y, p))
    if not paths:
        raise FileNotFoundError("Tidak ada Wholesale_YYYY.json (2020–2025).")

    longs = []
    for year, path in paths:
        df = _read_json_flex(path)

        # normalisasi nama kolom umum
        rename_map = {"type model":"model", "Type Model":"model", "TYPE MODEL":"model"}
        cols_lower = {c.lower(): c for c in df.columns}
        for raw, new in rename_map.items():
            if raw.lower() in cols_lower:
                df = df.rename(columns={cols_lower[raw.lower()]: new})

        # toleransi alias
        alt = {c.lower(): c for c in df.columns}
        for target, cands in {
            "brand": ["brand","Brand","BRAND","merk","make"],
            "model": ["model","type_model","tipe","variant","Type Model","TYPE MODEL"],
            "month": ["month","Month","bulan","mon","month_name"],
            "sales": ["sales","Sales","jumlah","qty","volume","units"],
        }.items():
            if target not in df.columns:
                for c in cands:
                    if c in df.columns or c.lower() in alt:
                        real = c if c in df.columns else alt[c.lower()]
                        df = df.rename(columns={real: target}); break

        month_cols = [c for c in df.columns if month_name_to_num(str(c)) is not None]
        if month_cols:
            # WIDE -> LONG
            if not {"brand","model"}.issubset(df.columns):
                raise ValueError(f"Wholesale {os.path.basename(path)} (wide) butuh brand & model.")
            long_df = df.melt(id_vars=["brand","model"], value_vars=month_cols,
                              var_name="month", value_name="sales")
        else:
            if not {"brand","model","month","sales"}.issubset(df.columns):
                raise ValueError(
                    f"Wholesale {os.path.basename(path)} harus punya kolom: brand, model, month, sales (LONG). "
                    f"Kolom saat ini: {list(df.columns)}"
                )
            long_df = df[["brand","model","month","sales"]].copy()

        long_df["month"] = long_df["month"].apply(month_name_to_num)
        long_df["sales"] = pd.to_numeric(long_df["sales"], errors="coerce").fillna(0)
        long_df["year"]  = year
        long_df["date"]  = pd.to_datetime(dict(year=long_df["year"], month=long_df["month"], day=1), errors="coerce")
        long_df["brand_key"] = long_df["brand"].astype(str).str.strip().str.upper()
        long_df["model_key"] = long_df["model"].astype(str).str.strip().str.lower()
        longs.append(long_df[["date","brand_key","model_key","sales"]])

    wholesale_long = pd.concat(longs, ignore_index=True).dropna(subset=["date"])
    wholesale_long = wholesale_long[(wholesale_long["date"] >= WINDOW_START) & (wholesale_long["date"] <= WINDOW_END)]

    monthly = wholesale_long.groupby(["date","brand_key","model_key"], as_index=False)["sales"].sum()
    pop = monthly.groupby(["brand_key","model_key"], as_index=False)["sales"] \
                 .mean().rename(columns={"sales":"wh_avg_window"})
    latest_date = monthly["date"].max()
    if pd.isna(latest_date):
        return pd.DataFrame(columns=["brand_key","model_key","wh_avg_window","trend_3v3"])

    last6_cut = latest_date - DateOffset(months=6)
    last6 = monthly[monthly["date"] > last6_cut]

    def trend_3v3_func(g: pd.DataFrame) -> float:
        g = g.sort_values("date")
        g["ma3"] = g["sales"].rolling(3, min_periods=1).mean()
        last3 = g["ma3"].tail(3).mean()
        prev3 = g["ma3"].iloc[-6:-3].mean() if len(g) >= 6 else g["ma3"].iloc[:-3].tail(3).mean() if len(g) > 3 else np.nan
        if pd.isna(prev3) or prev3 == 0: return 0.0
        return (last3 - prev3) / (prev3 + 1e-9)

    # ✅ Hindari FutureWarning: apply hanya pada kolom yang dibutuhkan
    tr = (
        last6
        .groupby(["brand_key","model_key"])[["date","sales"]]
        .apply(trend_3v3_func)
        .reset_index(name="trend_3v3")
    )

    return pop.merge(tr, on=["brand_key","model_key"], how="outer").fillna(0)
