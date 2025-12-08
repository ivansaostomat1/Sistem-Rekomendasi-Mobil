# file: backend/spk_rank.py
from __future__ import annotations
from typing import Dict, Any, List

import re
import time
import numpy as np
import pandas as pd

from .klastering import cluster_and_label, need_similarity_scores
from .spk_utils import (
    contains_ci,
    vector_match_trans,
    _series_num,
    assign_array_safe,
    _dbg,
    _ensure_df,
    price_fit_anchor,
    fuel_to_code,
    brand_match_mask,
)
from .spk_features import add_need_features
from .spk_needs import sanitize_needs
from .spk_hard import hard_constraints_filter, has_turbo_model
from .spk_soft import compute_percentiles, soft_multiplier, style_adjust_multiplier


def rank_candidates(
    df_master: pd.DataFrame,
    budget: float,
    spec_filters: Dict[str, Any],
    needs: List[str],
    topn: int = 15,
) -> pd.DataFrame:
    try:
        t0 = time.perf_counter()

        # --- DEBUG INPUT ---
        print("\n" + "=" * 50)
        print(" [SPK DEBUG] MULAI PERHITUNGAN")
        print(f" [INPUT] Budget: Rp {budget:,}")
        print(f" [INPUT] Needs (Raw): {needs}")
        print(f" [INPUT] Filters: {spec_filters}")
        print("=" * 50)

        # 0) Normalisasi kebutuhan
        needs = sanitize_needs(needs or [])
        needs_set = set(needs)
        print(f" [PROCESS] Needs Sanitized: {needs}")

        # 1) Filter harga (<= 115% budget)  & filter TOO-CHEAP (>= budget - 100jt)
        cap = budget * 1.15
        cand = df_master[df_master["price"] <= cap].copy()
        print(f" [FILTER] Harga <= {cap:,.0f} -> Sisa {len(cand)} mobil")

        if cand.empty:
            print(" [STOP] Tidak ada mobil masuk range harga.")
            return _ensure_df(cand)

        MAX_DOWN = 100_000_000.0
        lower_limit = max(0.0, budget - MAX_DOWN)

        n_before_price_lower = len(cand)
        cand = cand[cand["price"].notna() & (cand["price"] >= lower_limit)].copy()
        n_after_price_lower = len(cand)
        print(f" [FILTER] Hapus mobil harga < {lower_limit:,.0f} (max down {MAX_DOWN:,.0f}) -> Membuang {n_before_price_lower - n_after_price_lower}. Sisa {n_after_price_lower}.")

        if cand.empty:
            print(" [STOP] Tidak ada mobil setelah filter batas bawah harga.")
            return _ensure_df(cand)

        # 2) Filter brand (opsional)
        if spec_filters.get("brand"):
            cand = cand[brand_match_mask(cand["brand"], spec_filters["brand"])]
            print(f" [FILTER] Brand '{spec_filters['brand']}' -> Sisa {len(cand)} mobil")
            if cand.empty:
                return _ensure_df(cand)

        # 3) Filter transmisi
        trans_choice = spec_filters.get("trans_choice")
        cand = cand[vector_match_trans(cand["trans"], trans_choice)]
        print(f" [FILTER] Transmisi '{trans_choice}' -> Sisa {len(cand)} mobil")
        if cand.empty:
            return _ensure_df(cand)

        # 4) Filter fuel
        fuels = spec_filters.get("fuels", None)
        if fuels is not None:
            if isinstance(fuels, (str, bytes)):
                fuels_list = [fuels]
            else:
                try:
                    fuels_list = list(fuels)
                except TypeError:
                    fuels_list = [fuels]

            want_codes = set()
            for x in fuels_list:
                if x is None:
                    continue
                raw = x.get("code") if isinstance(x, dict) else x
                code = fuel_to_code(str(raw))
                if code and code != "o":
                    want_codes.add(code)

            if 0 < len(want_codes) < 5:
                cand = cand[cand["fuel_code"].astype(str).str.lower().isin(want_codes)]
                print(f" [FILTER] Fuel Codes {want_codes} -> Sisa {len(cand)} mobil")
                if cand.empty:
                    return _ensure_df(cand)

        # 5) Tambah fitur kebutuhan + hard constraints
        cand_feat = add_need_features(cand)
        hard_ok = hard_constraints_filter(cand_feat, needs or [])
        if not isinstance(hard_ok, pd.Series):
            hard_ok = pd.Series(bool(hard_ok), index=cand_feat.index)
        else:
            hard_ok = hard_ok.reindex(cand_feat.index)
        hard_ok = hard_ok.fillna(False).astype(bool)

        n_before = len(cand)
        cand = cand[hard_ok]
        cand_feat = cand_feat[hard_ok]
        n_after = len(cand)
        print(f" [FILTER] Hard Constraints (Kebutuhan) -> Membuang {n_before - n_after} mobil. Sisa {n_after}.")
        if cand.empty:
            return _ensure_df(cand)

        # 6) Klaster
        try:
            cand_feat2, cluster_to_label, C_scaled, feat_cols, scaler, _ = cluster_and_label(cand_feat, k=6)
            X_for_need = cand_feat2[feat_cols].apply(lambda col: col.fillna(col.median()), axis=0).values
            X_scaled = scaler.transform(X_for_need)
            cluster_ids = cand_feat2.get("cluster_id", np.zeros(len(cand_feat2), dtype=int))

            need_score = need_similarity_scores(X_scaled, C_scaled, np.asarray(cluster_ids), cluster_to_label, needs or [])
            cand = cand_feat2.copy()
        except Exception as e:
            print(f" [WARN] Clustering Error: {e}")
            need_score = 0.0
            cand = cand_feat.copy()

        assign_array_safe(cand, "need_score", need_score, fallback=0.0)

        # 7) Harga: price_fit
        p = pd.to_numeric(cand["price"], errors="coerce")
        if p.notna().any():
            p10 = float(np.nanpercentile(p.dropna(), 10))
            p90 = float(np.nanpercentile(p.dropna(), 90))
        else:
            p10, p90 = 0.0, 1.0
        p10 = max(p10, lower_limit)
        span = max(1.0, p90 - p10)
        price_rank = ((p - p10) / span).clip(0, 1)
        pmax_cand = float(p.max() if p.notna().any() else budget)
        price_anchor = p.apply(lambda x: price_fit_anchor(x, budget, pmax_cand))
        cand["price_fit"] = 0.5 * price_rank + 0.5 * price_anchor

        # 8) Skor atribut detail
        def _scale_01(series: pd.Series) -> pd.Series:
            s = pd.to_numeric(series, errors="coerce")
            s_valid = s.dropna()
            if s_valid.empty:
                return pd.Series(0.5, index=series.index, dtype=float)
            lo = float(np.nanpercentile(s_valid, 5))
            hi = float(np.nanpercentile(s_valid, 95))
            span = max(1e-6, hi - lo)
            return ((s - lo) / span).clip(0, 1)

        length = _series_num(cand.get("length_mm"))
        width = _series_num(cand.get("width_mm"))
        wb = _series_num(cand.get("wheelbase_mm"))
        weight = _series_num(cand.get("vehicle_weight_kg"))
        cc = _series_num(cand.get("cc_kwh_num"))
        rim = _series_num(cand.get("rim_inch"))
        tyr = _series_num(cand.get("tyre_w_mm"))
        awd = _series_num(cand.get("awd_flag")).fillna(0.0)
        seats = _series_num(cand.get("seats"))
        doors = _series_num(cand.get("doors_num"))

        fuel_c = cand.get("fuel_code", pd.Series(["o"] * len(cand), index=cand.index)).astype(str).str.lower()
        seg = cand.get("segmentasi", pd.Series([""] * len(cand), index=cand.index)).astype(str).str.lower()
        model = cand.get("model", pd.Series([""] * len(cand), index=cand.index)).astype(str)

        if weight.notna().any():
            weight_filled = weight.fillna(weight.median())
        else:
            weight_filled = weight.fillna(0.0)

        len_norm = _scale_01(length)
        wid_norm = _scale_01(width)
        wgt_norm = _scale_01(weight_filled)
        wb_norm = _scale_01(wb)
        cc_norm = _scale_01(cc)
        rim_norm = _scale_01(rim)
        tyr_norm = _scale_01(tyr)

        pw_raw = cc / weight_filled.replace(0, np.nan)
        pw_norm = _scale_01(pw_raw)

        turbo_flag = model.apply(has_turbo_model).astype(float)
        is_elec_hybrid = fuel_c.isin({"h", "p", "e"}).astype(float)
        is_diesel = (fuel_c == "d").astype(float)

        small_size = (0.45 * (1 - len_norm) + 0.45 * (1 - wid_norm) + 0.10 * (1 - wgt_norm))
        cc_small = 1 - cc_norm
        efficiency_score = (0.30 * cc_small + 0.20 * (1 - wgt_norm) + 0.50 * is_elec_hybrid).clip(0, 1)

        # EV-aware city_score
        is_ev = (fuel_c == "e")
        dim_comp_non_ev = 0.40 * (1 - wid_norm) + 0.30 * (1 - len_norm) + 0.30 * (1 - wgt_norm)
        dim_comp_ev = 0.30 * (1 - wid_norm) + 0.20 * (1 - len_norm) + 0.50 * (1 - wgt_norm)
        dim_comp = dim_comp_non_ev.where(~is_ev, dim_comp_ev)
        efficiency_boost = efficiency_score * (1.05 * is_ev + 1.0 * (~is_ev))
        city_score = (0.40 * dim_comp + 0.60 * efficiency_boost).clip(0, 1)

        perf_score = (0.50 * pw_norm + 0.15 * rim_norm + 0.15 * turbo_flag + 0.10 * tyr_norm + 0.10 * (awd > 0.5).astype(float)).clip(0, 1)

        seats_capped = seats.clip(upper=7)
        seats_norm = _scale_01(seats_capped)
        doors_good = (doors >= 5).astype(float)
        mpv_like = seg.str.contains(r"\b(?:mpv|van|minibus)\b", regex=True).astype(float)
        family_score = (0.50 * seats_norm + 0.30 * doors_good + 0.20 * mpv_like).clip(0, 1)

        if length.notna().any():
            len_p80 = float(np.nanpercentile(length.dropna(), 80))
            too_long = length > len_p80
            family_score[too_long & (seats >= 9)] *= 0.95

        comfort_score = (0.40 * wb_norm + 0.20 * wgt_norm + 0.20 * len_norm + 0.20 * (is_diesel * 0.8 + efficiency_score * 0.2)).clip(0, 1)
        suv_pickup = seg.str.contains(r"\b(?:suv|crossover|pick|truck)\b", flags=re.I, regex=True).astype(float)
        offroad_score = (0.45 * (awd.clip(0, 1)) + 0.25 * tyr_norm + 0.15 * rim_norm + 0.15 * suv_pickup).clip(0, 1)
        utility_score = (0.5 * len_norm + 0.5 * wgt_norm).clip(0, 1)

        # 9) PEMBOBOTAN DINAMIS
        score_map = {
            "fun": perf_score,
            "keluarga": family_score,
            "perjalanan_jauh": comfort_score,
            "perkotaan": city_score,
            "niaga": utility_score,
            "offroad": offroad_score,
        }

        n_needs = len(needs)
        if n_needs == 0:
            weights = []
        elif n_needs == 1:
            weights = [1.0]
        elif n_needs == 2:
            weights = [0.65, 0.35]
        else:
            weights = [0.55, 0.30, 0.15]

        attr_weighted = pd.Series(0.0, index=cand.index, dtype=float)
        w_total = 0.0
        print(f" [SCORE] Bobot Kebutuhan: {list(zip(needs[:3], weights))}")

        for i, need_key in enumerate(needs[:3]):
            if need_key in score_map:
                s_val = score_map[need_key]
                w_val = weights[i]
                attr_weighted += s_val * w_val
                w_total += w_val

        if w_total > 0:
            attr_score = (attr_weighted / w_total).clip(0, 1)
        else:
            attr_score = pd.to_numeric(cand.get("need_score", 0.5), errors="coerce").fillna(0.5)

        if needs:
            need_s = pd.to_numeric(cand.get("need_score", 0.5), errors="coerce").fillna(0.5)
            pref_score = (0.7 * attr_score + 0.3 * need_s).clip(0, 1)
        else:
            pref_score = attr_score

        # 10) Gabungkan dengan Price Fit
        alpha_price = 0.20 if ({"fun", "offroad"} & needs_set) else 0.30
        cand["fit_score"] = ((1.0 - alpha_price) * pref_score + alpha_price * cand["price_fit"]).clip(0, 1)

        # 11) Soft & style layer
        P = compute_percentiles(cand)
        cand["soft_mult"] = cand.apply(lambda r: soft_multiplier(r, needs or [], P), axis=1)
        cand["style_mult"] = cand.apply(lambda r: style_adjust_multiplier(r, needs or []), axis=1)

        cand["raw_score"] = cand["fit_score"]
        cand["fit_score"] = (cand["fit_score"] * cand["soft_mult"] * cand["style_mult"]).clip(0, 1.0)

        # === NORMALISASI MODEL_BASE YANG LEBIH AGGRESIF ===
        # token varian yang lebih lengkap (tambahkan jika perlu)
        variant_tokens = [
            "prime", "signature", "extended", "extended range", "extended-range", "extendedrange",
            "premium", "performance", "dynamic", "deluxe", "sport", "long range", "longrange", "lr",
            "standard", "base", "ultimate", "plus", "pro", "elite", "comfort", "tech", "advanced",
            "limited", "reguler", "reg", "two tone", "twotone", "two-tone", "premium extended range",
            "premiumextended", "premiumextendedrange"
        ]
        # buat pattern (word boundary) - escape semua token
        var_pat = r"\b(?:" + "|".join(re.escape(t) for t in variant_tokens) + r")\b"

        def infer_model_base(s: str) -> str:
            if not isinstance(s, str):
                s = str(s or "")
            s0 = s.lower()
            # hapus kata EV / BEV / PHEV / HEV / plugin / hybrid / plugin-hybrid
            s0 = re.sub(r"\b(ev|bev|phev|phev|hev|hybrid|plugin|plug-in|plugin-hybrid|electric)\b", " ", s0, flags=re.I)
            # hapus kata trim / varian menurut var_pat
            s0 = re.sub(var_pat, " ", s0, flags=re.I)
            # hapus angka versi / kode gen/v etc.
            s0 = re.sub(r"\b(v\d+|mk\d+|gen\d+|g\d+)\b", " ", s0, flags=re.I)
            # hapus common words like 'reguler', 'type', 'series'
            s0 = re.sub(r"\b(reguler|series|type|edition|line|limited|model)\b", " ", s0, flags=re.I)
            # hapus simbol / () - normalize whitespace
            s0 = re.sub(r"[\/\,\-\(\)]", " ", s0)
            s0 = re.sub(r"\s+", " ", s0).strip()
            # fallback: ambil 2 kata pertama kalau kosong
            if not s0:
                s0 = " ".join((s or "").split()[:2]).strip().lower()
            return s0

        # siapkan field bantu untuk trimming akhir
        cand["model_norm_full"] = cand.get("model", pd.Series([""] * len(cand), index=cand.index)).astype(str).str.strip()
        cand["model_norm_lc"] = cand["model_norm_full"].str.lower()
        cand["model_base"] = cand["model_norm_lc"].apply(infer_model_base)
        cand["brand_key_lc"] = cand.get("brand", pd.Series([""] * len(cand), index=cand.index)).astype(str).str.strip().str.lower()

        # Urutkan berdasarkan fit_score dulu (trim terbaik paling atas)
        cand = cand.sort_values(["fit_score"], ascending=[False])

        # BATASI TRIMS PER (brand, model_base)
        max_trims_per_model = 2  # ubah sesuai kebutuhan
        cand = cand.groupby(["brand_key_lc", "model_base"], sort=False).head(max_trims_per_model).reset_index(drop=True)

        # Hapus kolom bantu (tetap simpan model asli)
        cand = cand.drop(columns=["model_base", "brand_key_lc", "model_norm_lc"], errors="ignore")

        # 12) Alasan singkat
        def mk_reason(r):
            why = []
            if r["price"] <= budget:
                why.append("sesuai budget")
            elif r["price"] <= budget * 1.15:
                why.append("sedikit di atas budget")

            if needs:
                main = needs[0]
                if main == "keluarga":
                    s = float(r.get("seats", 0))
                    why.append(f"{int(s)}-seater")
                elif main == "perkotaan":
                    why.append("dimensi ringkas")
                elif main == "fun":
                    if has_turbo_model(str(r.get("model", ""))):
                        why.append("mesin turbo")
                    else:
                        why.append("mesin responsif")
                elif main == "offroad":
                    if float(r.get("awd_flag", 0)) >= 0.5:
                        why.append("penggerak AWD/4x4")
                elif main == "perjalanan_jauh":
                    if str(r.get("fuel_code", "")) == "d":
                        why.append("mesin diesel tangguh")
                    else:
                        why.append("nyaman jarak jauh")

            return ", ".join(why)

        cand["alasan"] = cand.apply(mk_reason, axis=1)

        # 13) Sortir, dedup, rank FINAL
        cand["model_norm"] = cand["model"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.lower()
        cand["price_int"] = pd.to_numeric(cand["price"], errors="coerce").fillna(-1).astype(int)

        cand = (
            cand.sort_values(["fit_score"], ascending=[False])
            .drop_duplicates(subset=["model_norm", "price_int"], keep="first")
            .drop(columns=["model_norm", "price_int", "model_norm_full"], errors="ignore")
            .reset_index(drop=True)
        )

        n_out = len(cand)
        cand["rank"] = np.arange(1, n_out + 1, dtype=int)
        if n_out > 1:
            cand["points"] = np.round(np.linspace(99, 60, num=n_out)).astype(int)
        elif n_out == 1:
            cand["points"] = [99]
        else:
            cand["points"] = []

        topn = 15 if (topn is None or topn <= 0) else int(topn)

        # DEBUG TOP
        print("\n [SPK DEBUG] TOP 5 KANDIDAT:")
        for i, row in cand.head(5).iterrows():
            print(f"   #{i+1} {row['brand']} {row['model']} | Price: {row['price']:,} | Score: {row['fit_score']:.4f}")
            print(f"       -> RawScore: {row.get('raw_score',0):.4f} | SoftMult: {row.get('soft_mult',1):.2f} | StyleMult: {row.get('style_mult',1):.2f}")
            print(f"       -> Alasan: {row['alasan']}")
        print("=" * 50 + "\n")

        t1 = time.perf_counter()
        return _ensure_df(cand.head(topn))

    except Exception as e:
        print(f"[rank] error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return _ensure_df(pd.DataFrame()).iloc[0:0]
