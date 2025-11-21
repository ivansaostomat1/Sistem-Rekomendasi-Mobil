# file: spk_features.py
from __future__ import annotations
from typing import Any, List
import re
import numpy as np
import pandas as pd

from spk_utils import fuel_to_code, get_standard_depreciation_rate, zscore, sigmoid


# ============================================================
# Parser turbo / dimensi / ban
# ============================================================

_TURBO_POS = re.compile(
    r"""
    (?:\bTurbo\b)
    |(?:\b\d+(?:\.\d+)?\s*T\b)
    |(?:\b\d+(?:\.\d+)?T\b)
    |(?:\b(?:TSI|TFSI|T-GDI|GDI-T|EcoBoost|BoosterJet|VTEC\s*Turbo|TwinPower\s*Turbo|D-4T)\b)
    """, re.IGNORECASE | re.VERBOSE
)


def has_turbo(model: str) -> bool:
    s = str(model or "")
    s = re.sub(r"\b(CVT|A/T|AT|M/T|MT|DCT)\b", " ", s, flags=re.IGNORECASE)
    return bool(_TURBO_POS.search(s))


def _to_float(x, default=np.nan):
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return default


def _parse_dims_pxlxt(s: str):
    t = str(s)
    nums = re.findall(r"[\d.]+", t.replace(",", "."))
    vals = [_to_float(n) for n in nums[:3]]
    if len(vals) < 3:
        return np.nan, np.nan, np.nan
    p, l, h = vals
    scale = 1000 if p < 100 else 1
    return p * scale, l * scale, h * scale


def _parse_wheel_size(s: str):
    st = str(s).upper().replace(" ", "")
    rim = re.search(r"R(\d{2})", st)
    rim_inch = _to_float(rim.group(1)) if rim else np.nan
    w = re.search(r"(\d{3})/\d{2}", st)
    tyre_w_mm = _to_float(w.group(1)) if w else np.nan
    return tyre_w_mm, rim_inch


def _has_awd_text(text: str) -> float:
    s = str(text or "").upper()
    return 1.0 if any(k in s for k in ["4X4", "4WD", "AWD"]) else 0.0


# ---------- Helper pick kolom (robust alias) ----------

def _pick_str(df: pd.DataFrame, names: List[str], default: str = "") -> pd.Series:
    for n in names:
        if n in df.columns:
            return df[n].astype(str)
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _pick_num(df: pd.DataFrame, names: List[str]) -> pd.Series:
    for n in names:
        if n in df.columns:
            return pd.to_numeric(df[n], errors="coerce")
    return pd.Series([np.nan] * len(df), index=df.index, dtype="float64")


def add_need_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # --- kolom dasar ---
    seats = _pick_num(out, ["seats", "seat", "kursi", "jumlah_kursi", "seating", "seating_capacity"])
    out["seats"] = seats

    trans = _pick_str(out, ["trans", "transmission", "gearbox"], default="")
    out["trans"] = trans

    seg = _pick_str(
        out,
        ["segmentasi", "body_type", "body", "bodystyle", "jenis_bodi", "type", "segmen", "kategori"],
        ""
    )
    out["segmentasi"] = seg

    out["wheelbase_mm"] = _pick_num(out, ["WHEEL BASE", "WHEELBASE", "wheelbase", "Wheelbase (mm)"])

    # --- DIMENSI ---
    dims_raw = _pick_str(out, [
        "DIMENSION P x L x T", "DIMENSION P x L xT", "DIMENSION PxLxT",
        "Dimension (P x L x T)", "Dimensi (P x L x T)",
        "dimensions", "dimensi", "size"
    ], default="")

    Ls, Ws, Hs = [], [], []
    for s in dims_raw:
        p, l, h = _parse_dims_pxlxt(s)
        Ls.append(p); Ws.append(l); Hs.append(h)
    out["length_mm"] = pd.to_numeric(pd.Series(Ls, index=out.index), errors="coerce")
    out["width_mm"]  = pd.to_numeric(pd.Series(Ws, index=out.index), errors="coerce")
    out["height_mm"] = pd.to_numeric(pd.Series(Hs, index=out.index), errors="coerce")

    # --- BAN & PELEK ---
    tyre_raw = _pick_str(out, ["WHEEL & TYRE SIZE", "WHEEL & TIRE SIZE", "TIRE SIZE", "TYRE SIZE", "Ban & Velg"], "")
    TWs, Rims = [], []
    for s in tyre_raw:
        tw, rim = _parse_wheel_size(s)
        TWs.append(tw); Rims.append(rim)
    out["tyre_w_mm"] = pd.to_numeric(pd.Series(TWs, index=out.index), errors="coerce")
    out["rim_inch"]  = pd.to_numeric(pd.Series(Rims, index=out.index), errors="coerce")

    # --- berat & cc/kwh ---
    out["vehicle_weight_kg"] = _pick_num(out, ["vehicle_weight", "weight", "curb_weight", "berat", "berat_kosong"])
    out["cc_kwh_num"]       = _pick_num(out, ["cc_kwh", "cc", "engine_cc", "kapasitas_mesin", "engine", "battery_kwh", "kwh"])

    # --- JUMLAH PINTU ---
    out["doors_num"] = _pick_num(out, ["doors", "door", "pintu", "num_door", "jumlah_pintu"])

    # --- AWD: gabungan teks penggerak + model/varian sebagai hint ---
    drivestr   = _pick_str(out, ["drive_sys", "DRIVE SYS", "DRIVE SYSTEM", "DRIVETRAIN", "DRIVE TRAIN", "penggerak", "penggerak roda"], "")
    model_hint = _pick_str(out, ["model", "type model", "type_model", "variant"], "")
    awd_text   = (drivestr + " " + model_hint).astype(str)
    out["awd_flag"] = awd_text.apply(_has_awd_text).astype(float)

    # --- fuel code ---
    fuel_str = _pick_str(out, ["fuel", "fuel type", "fuel_type", "bahan bakar", "jenis_bahan_bakar"], "")
    out["fuel_code"] = fuel_str.apply(fuel_to_code)

    return out


# ============================================================
# BUILD MASTER (gabung wholesale + retail + depresiasi)
# ============================================================

def build_master(
    specs: pd.DataFrame,
    wh_features: pd.DataFrame,
    retail_brand_share: pd.DataFrame,
    pred_years: float
) -> pd.DataFrame:
    specs = specs.copy()
    specs["brand_key_upper"] = specs["brand"].astype(str).str.strip().str.upper()

    specs_wh = specs.merge(
        wh_features,
        left_on=["brand_key_upper", "model_key"],
        right_on=["brand_key", "model_key"],
        how="left",
        suffixes=("", "_wh"),
    ).drop(columns=[c for c in ["brand_key_wh"] if c in wh_features.columns], errors="ignore")

    df = specs_wh.merge(
        retail_brand_share,
        left_on="brand_key_upper",
        right_on="brand_key",
        how="left",
        suffixes=("", "_ret"),
    ).drop(columns=[c for c in ["brand_key_ret"] if c in retail_brand_share.columns], errors="ignore")

    if "wh_avg_window" not in df.columns: df["wh_avg_window"] = 0.0
    if "trend_3v3" not in df.columns:     df["trend_3v3"] = 0.0
    df["brand_share_ratio"] = df.get("brand_share_ratio", 0.0)

    if df["wh_avg_window"].notna().sum() > 1:
        df["popularity_z"] = zscore(df["wh_avg_window"].fillna(0))
    else:
        df["popularity_z"] = 0.0

    standard_rate = get_standard_depreciation_rate(pred_years)
    df["standard_resale_rate"] = standard_rate

    market_adjustment = (
        0.15 * sigmoid(df["trend_3v3"].replace([np.inf, -np.inf], 0).fillna(0))
        + 0.05 * sigmoid(df["popularity_z"])
        + 0.05 * sigmoid(zscore(df["brand_share_ratio"]))
    )
    df["resale_multiplier"] = (standard_rate + market_adjustment)
    clip_min = max(0.30, standard_rate * 0.8)
    clip_max = min(1.0, standard_rate * 1.25) if pred_years >= 1 else 1.0
    df["resale_multiplier"] = df["resale_multiplier"].clip(clip_min, clip_max)
    df["predicted_resale_value"] = (df["price"] * df["resale_multiplier"]).round(0)

    df["fuel_code"] = df.get("fuel", pd.Series([""]*len(df), index=df.index)).apply(fuel_to_code)

    return df.drop(columns=["brand_key_upper"], errors="ignore")
