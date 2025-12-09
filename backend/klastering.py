# file: backend/klastering.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import re

# Konstanta umum
MAX_SAMPLES_CLUSTER = 2000
NEED_LABELS = ["perjalanan_jauh", "keluarga", "fun", "perkotaan", "niaga", "offroad"]

# Hanya tipe body yang ada di dataset Anda
# (sesuaikan jika ada varian kata lain; gunakan lower-case)
PASSENGER_BODY_TYPES = {
    "sedan", "wagon", "crossover", "suv", "pickup", "mpv",
    "hatchback", "coupe", "convertible", "blindvan", "van"
}

# Mapping normalisasi body_type (opsional): samakan varian umum ke kategori
BODY_NORMALIZE_MAP = {
    "cross-over": "crossover",
    "cross over": "crossover",
    "sport utility vehicle": "suv",
    "minivan": "mpv",
    "mini van": "mpv",
    "pickup truck": "pickup",
    "box van": "van",
    "people carrier": "mpv",
    "alphard": "mpv",
    "mpv-premium": "mpv"
}

def normalize_body_type(raw: Optional[str]) -> str:
    if not isinstance(raw, str):
        return ""
    s = raw.strip().lower()
    s = re.sub(r'[^a-z0-9\s\-]', '', s)
    s = BODY_NORMALIZE_MAP.get(s, s)
    return s

def parse_dimension(dim: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Parse string dimension (contoh: '5140 x 1928 x 1880' atau '4490 x 1788 x 1540')
    return (length_mm, width_mm, height_mm) atau (None, None, None).
    Menerima variasi tanda x, X, ×, spasi, dan kemungkinan label mm.
    """
    if not isinstance(dim, str):
        return None, None, None
    s = dim.strip().lower().replace("×", "x")
    # Hapus kata-kata seperti 'dimensi', 'p x l x t', 'mm'
    s = re.sub(r'(dimension|dimensi|p\s*x\s*l\s*x\s*t|mm)', '', s)
    # Split di 'x' atau '×' atau tanda lain
    parts = re.split(r'[x×\*]', s)
    parts = [p.strip().replace(",", "").replace(" ", "") for p in parts if p.strip()]
    if len(parts) < 3:
        return None, None, None
    try:
        L = float(parts[0])
        W = float(parts[1])
        H = float(parts[2])
        return L, W, H
    except Exception:
        return None, None, None

def is_obvious_commercial_by_dimension(length: Optional[float], width: Optional[float], height: Optional[float]) -> bool:
    """
    Indikasi kendaraan komersial bila sangat besar; threshold konservatif.
    """
    if length is None or width is None or height is None:
        return False
    if length >= 5200 or height >= 2000 or width >= 2100:
        return True
    if length >= 5400 and height >= 1850:
        return True
    return False

def _ensure_columns(cand: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisasi nama kolom yang umum berbeda di dataset: dimension, vehicle_weight, wheelbase, cc/kwh, seats, body_type.
    Mengembalikan DataFrame yang sudah punya kolom:
      - dimension (string)
      - vehicle_weight_kg (float)
      - wheelbase_mm (float)
      - length_mm, width_mm, height_mm (float) [jika ada]
      - cc_kwh_num (float)
      - seats (float/int)
      - body_type (string)
    """
    df = cand.copy()

    # mapping kolom umum ke nama standar
    col_map = {
        "DIMENSION P x L xT": "dimension",
        "DIMENSION": "dimension",
        "dimension_str": "dimension",
        "vehicle_weight": "vehicle_weight_kg",
        "vehicle_weight_kg": "vehicle_weight_kg",
        "WHEEL BASE": "wheelbase_mm",
        "WHEELBASE": "wheelbase_mm",
        "WHEEL & TYRE SIZE": "wheel_tyre_raw",
        "cc / kwh": "cc_kwh_num",
        "cc/kwh": "cc_kwh_num",
        "cc \\ / kwh": "cc_kwh_num",  # sometimes odd chars
        "seats": "seats",
        "seat": "seats",
        "body_type": "body_type",
        "segmentasi": "body_type",
        "type model": "model",
        "type_model": "model",
        "vehicle_weight (kg)": "vehicle_weight_kg",
        "PS / HP": "power_raw"
    }
    # lower-case matching keys
    existing = {c.lower(): c for c in df.columns}
    for src, dst in col_map.items():
        src_l = src.lower()
        if src_l in existing and dst not in df.columns:
            df[dst] = df[existing[src_l]]

    # jika length_mm, width_mm, height_mm sudah ada gunakan, kalau tidak coba parse dari 'dimension'
    for c in ["length_mm", "width_mm", "height_mm"]:
        if c not in df.columns:
            df[c] = np.nan

    if "dimension" in df.columns:
        parsed = df["dimension"].apply(parse_dimension)
        df["dim_length_mm"] = [p[0] for p in parsed]
        df["dim_width_mm"]  = [p[1] for p in parsed]
        df["dim_height_mm"] = [p[2] for p in parsed]
        # Jika length_mm kosong, isi dari parsed dim
        df["length_mm"] = df.apply(lambda r: r["length_mm"] if not pd.isna(r["length_mm"]) else r["dim_length_mm"], axis=1)
        df["width_mm"]  = df.apply(lambda r: r["width_mm"] if not pd.isna(r["width_mm"]) else r["dim_width_mm"], axis=1)
        df["height_mm"] = df.apply(lambda r: r["height_mm"] if not pd.isna(r["height_mm"]) else r["dim_height_mm"], axis=1)
    else:
        df["dim_length_mm"] = np.nan
        df["dim_width_mm"] = np.nan
        df["dim_height_mm"] = np.nan

    # normalisasi vehicle_weight
    if "vehicle_weight_kg" not in df.columns and "vehicle_weight" in df.columns:
        df["vehicle_weight_kg"] = df["vehicle_weight"]
    if "vehicle_weight_kg" not in df.columns:
        df["vehicle_weight_kg"] = np.nan

    # normalisasi cc_kwh_num
    if "cc_kwh_num" not in df.columns:
        # coba cari kolom berisi 'cc' atau 'kwh' secara case-insensitive
        for c in df.columns:
            if "cc" in c.lower() or "kwh" in c.lower():
                df["cc_kwh_num"] = pd.to_numeric(df[c].astype(str).str.extract(r'([\d\.]+)')[0], errors="coerce")
                break
        else:
            df["cc_kwh_num"] = np.nan

    # wheelbase
    if "wheelbase_mm" not in df.columns:
        # coba cari 'WHEEL BASE' variasi
        for c in df.columns:
            if "wheel" in c.lower() and "base" in c.lower():
                df["wheelbase_mm"] = pd.to_numeric(df[c], errors="coerce")
                break
        else:
            df["wheelbase_mm"] = np.nan

    # seats
    if "seats" not in df.columns:
        for c in df.columns:
            if "seat" in c.lower():
                df["seats"] = pd.to_numeric(df[c], errors="coerce")
                break
        else:
            df["seats"] = np.nan

    # body_type
    if "body_type" not in df.columns and "segmentasi" in df.columns:
        df["body_type"] = df["segmentasi"]
    if "body_type" not in df.columns:
        df["body_type"] = ""

    # normalize body_type
    df["body_type"] = df["body_type"].astype(str).apply(normalize_body_type)

    return df

def cluster_and_label(
    cand: pd.DataFrame,
    k: int = 6
) -> Tuple[pd.DataFrame, Dict[int, str], np.ndarray, List[str], object, np.ndarray]:
    """
    KMeans atas fitur kendaraan + heuristik rule-based tambahan.
    Pipeline:
      - normalisasi kolom input
      - clustering KMeans (fit pada fitur numerik)
      - scoring heuristik untuk tiap kebutuhan
      - koreksi per-item berdasarkan dimension/body_type/seats
    """
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except Exception as e:
        raise RuntimeError("scikit-learn diperlukan untuk klastering") from e

    # Normalisasi / map kolom input agar robust ke variasi dataset
    df = _ensure_columns(cand)

    # Fitur yang digunakan untuk clustering (harus ada di dataframe)
    feat_cols = [
        "length_mm", "width_mm", "height_mm", "wheelbase_mm",
        "vehicle_weight_kg", "cc_kwh_num", "rim_inch", "tyre_w_mm", "awd_flag"
    ]
    # Pastikan semua fitur ada (isi NaN bila tidak ada)
    for f in feat_cols:
        if f not in df.columns:
            df[f] = np.nan

    X = df[feat_cols].copy().apply(lambda col: col.fillna(col.median()), axis=0)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    n = len(df)
    k_eff = min(k, max(1, int(min(6, max(1, int(np.sqrt(max(1, n/2))))))))
    km = KMeans(
        n_clusters=k_eff, n_init=1, max_iter=150, tol=1e-4,
        algorithm="lloyd", random_state=42
    )

    if n > MAX_SAMPLES_CLUSTER:
        rng = np.random.RandomState(42)
        idx = rng.choice(n, size=MAX_SAMPLES_CLUSTER, replace=False)
        km.fit(X_scaled[idx])
        labels = km.predict(X_scaled)
    else:
        labels = km.fit_predict(X_scaled)

    C_scaled = km.cluster_centers_
    C_raw = scaler.inverse_transform(C_scaled)

    # Heuristik label centroid (skala asli)
    feat_idx = {c: i for i, c in enumerate(feat_cols)}
    length = C_raw[:, feat_idx["length_mm"]]
    width  = C_raw[:, feat_idx["width_mm"]]
    wheelb = C_raw[:, feat_idx["wheelbase_mm"]]
    weight = C_raw[:, feat_idx["vehicle_weight_kg"]]
    cc     = C_raw[:, feat_idx["cc_kwh_num"]]
    rim    = C_raw[:, feat_idx["rim_inch"]]
    awd    = C_raw[:, feat_idx["awd_flag"]]

    def z(v):
        v = np.asarray(v, dtype=float)
        mu, sd = np.nanmean(v), np.nanstd(v) + 1e-9
        return (v - mu) / sd

    cc_per_w = np.divide(cc, np.maximum(weight, 1), where=np.isfinite(weight))

    # Scoring heuristik (centroid-level)
    s_trip       = 0.6 * z(wheelb) + 0.3 * z(weight) + 0.2 * z(cc)
    s_family     = 0.5 * z(wheelb) + 0.4 * z(length) + 0.3 * z(width)
    s_fun        = 0.6 * z(cc_per_w) + 0.4 * z(cc) - 0.1 * z(weight)
    opt_len = 4450.0
    opt_wid = 1780.0
    s_city       = - (np.abs(z(length - opt_len)) * 0.6 + np.abs(z(width - opt_wid)) * 0.6)
    s_commercial = 0.5 * z(weight) - 0.3 * z(cc) - 0.3 * z(rim)
    s_offroad    = 2.5 * awd + 0.4 * z(rim) - 0.2 * z(length)

    S = np.stack([s_trip, s_family, s_fun, s_city, s_commercial, s_offroad], axis=1)
    best = np.argmax(S, axis=1)
    cluster_to_label = {i: NEED_LABELS[j] for i, j in enumerate(best)}

    # Pasca-proses per-barang: koreksi berdasarkan rules yang lebih deterministik
    df["cluster_id"] = labels
    df["pred_label"] = df["cluster_id"].map(cluster_to_label)

    def decide_label_for_row(row, initial_label):
        seats = row.get("seats", np.nan)
        body = row.get("body_type", "")
        dimL = row.get("dim_length_mm", None)
        dimW = row.get("dim_width_mm", None)
        dimH = row.get("dim_height_mm", None)
        length_mm = row.get("length_mm", dimL)
        weight_kg = row.get("vehicle_weight_kg", np.nan)

        # Jika dimensi jelas komersial dan body bukan passenger jenis di dataset -> niaga
        if is_obvious_commercial_by_dimension(dimL, dimW, dimH):
            if body not in PASSENGER_BODY_TYPES:
                return "niaga"
            # body passenger -> lanjutkan pemeriksaan

        # Hindari mem-label MPV/SUV/Van/Alphard-like sebagai niaga
        if body in PASSENGER_BODY_TYPES:
            if initial_label == "niaga":
                if (not np.isnan(seats) and seats >= 5) or (dimH is not None and dimH < 1900):
                    return "keluarga"
                if dimL and dimL > 5200 and body == "sedan":
                    return "perjalanan_jauh"
                return "keluarga" if (not np.isnan(seats) and seats >=5) else "perjalanan_jauh"

        # Seats logic
        if not np.isnan(seats):
            if seats >= 6:
                return "keluarga"
            if seats == 5:
                if (length_mm is not None) and (length_mm < 4000):
                    return "perkotaan"
                return "keluarga"

        # Berat besar + dimensi besar => niaga (kecuali body passenger)
        if (weight_kg is not None and not np.isnan(weight_kg) and weight_kg >= 2500) and (dimL is not None and dimL >= 5200):
            if body not in PASSENGER_BODY_TYPES:
                return "niaga"

        # Long sedan => perjalanan_jauh
        if dimL and dimL > 5200 and (body == "sedan" or (body == "" and length_mm and length_mm > 5200)):
            return "perjalanan_jauh"

        # Jika dimensi niaga tapi seats banyak -> family
        if is_obvious_commercial_by_dimension(dimL, dimW, dimH) and (not np.isnan(seats) and seats >=5):
            return "keluarga"

        return initial_label

    df["pred_label"] = df.apply(lambda r: decide_label_for_row(r, r["pred_label"]), axis=1)

    return df, cluster_to_label, C_scaled, feat_cols, scaler, C_raw

def need_similarity_scores(
    X_scaled: np.ndarray,
    C_scaled: np.ndarray,
    lbls: np.ndarray,
    cluster_to_label: Dict[int, str],
    want_labels: List[str]
) -> np.ndarray:
    """
    Hitung skor kesesuaian kebutuhan berbasis jarak ke centroid cluster.
    """
    try:
        from sklearn.metrics import pairwise_distances
    except Exception:
        return np.zeros(X_scaled.shape[0])

    if not want_labels:
        return np.zeros(X_scaled.shape[0])

    label_to_cids: Dict[str, List[int]] = {}
    for cid, lab in cluster_to_label.items():
        label_to_cids.setdefault(lab, []).append(cid)

    sims_per_need = []
    for need in want_labels:
        cids = label_to_cids.get(need, [])
        if not cids:
            sims_per_need.append(np.zeros(X_scaled.shape[0]))
            continue
        D = np.asarray(pairwise_distances(X_scaled, C_scaled[cids, :], metric="euclidean"))
        sim = 1.0 / (1.0 + D)  # 0..1
        sims_per_need.append(np.max(sim, axis=1))

    sims = np.vstack(sims_per_need)
    return sims.mean(axis=0)
