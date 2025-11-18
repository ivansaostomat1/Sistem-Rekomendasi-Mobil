# klastering.py
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

# Konstanta umum
MAX_SAMPLES_CLUSTER = 2000
NEED_LABELS = ["perjalanan_jauh", "keluarga", "fun", "perkotaan", "niaga", "offroad"]

def cluster_and_label(
    cand: pd.DataFrame,
    k: int = 6
) -> Tuple[pd.DataFrame, Dict[int, str], np.ndarray, List[str], object, np.ndarray]:
    """
    KMeans atas fitur kendaraan (diasumsikan kolom fitur SUDAH ada di `cand`):
      ['length_mm','width_mm','height_mm','wheelbase_mm','vehicle_weight_kg',
       'cc_kwh_num','rim_inch','tyre_w_mm','awd_flag']

    Output:
      - cand_plus: df dengan kolom 'cluster_id'
      - cluster_to_label: peta centroid -> label need
      - C_scaled: pusat cluster pada ruang terstandarisasi
      - feat_cols: urutan nama fitur
      - scaler: StandardScaler yg dipakai
      - C_raw: pusat cluster pada skala asli
    """
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except Exception as e:
        raise RuntimeError("scikit-learn diperlukan untuk klastering") from e

    feat_cols = [
        "length_mm", "width_mm", "height_mm", "wheelbase_mm",
        "vehicle_weight_kg", "cc_kwh_num", "rim_inch", "tyre_w_mm", "awd_flag"
    ]

    X = cand[feat_cols].copy().apply(lambda col: col.fillna(col.median()), axis=0)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.values)

    n = len(cand)
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
    s_trip       = 0.7 * z(wheelb) - 0.3 * z(weight)
    s_family     = 0.6 * z(wheelb) + 0.4 * z(length)
    s_fun        = 0.7 * z(cc_per_w) - 0.3 * z(length)
    s_city       = - (0.6 * z(length) + 0.4 * z(width))
    s_commercial = 0.6 * z(weight) + 0.4 * z(length)
    s_offroad    = 2.0 * awd + 0.5 * z(wheelb) - 0.3 * z(rim)

    S = np.stack([s_trip, s_family, s_fun, s_city, s_commercial, s_offroad], axis=1)
    best = np.argmax(S, axis=1)
    cluster_to_label = {i: NEED_LABELS[j] for i, j in enumerate(best)}

    cand_plus = cand.copy()
    cand_plus["cluster_id"] = labels
    return cand_plus, cluster_to_label, C_scaled, feat_cols, scaler, C_raw


def need_similarity_scores(
    X_scaled: np.ndarray,
    C_scaled: np.ndarray,
    lbls: np.ndarray,
    cluster_to_label: Dict[int, str],
    want_labels: List[str]
) -> np.ndarray:
    """
    Hitung skor kesesuaian kebutuhan berbasis jarak ke centroid cluster yang berlabel sama.
    Mengembalikan vektor skor (0..1) per-barang, rata-rata atas semua kebutuhan yang diminta.
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
