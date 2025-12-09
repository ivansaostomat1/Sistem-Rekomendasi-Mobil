# file: backend/spk_hard.py
from __future__ import annotations
from typing import List, Optional, Tuple
import re

import numpy as np
import pandas as pd

from .spk_utils import _series_num
from .spk_features import has_turbo


def has_turbo_model(model: str) -> bool:
    """
    Wrapper kecil supaya pemanggilan di tempat lain lebih bersih.
    """
    return has_turbo(model)


def is_fast_enough(cc_s: pd.Series, model_s: pd.Series, fuel_s: pd.Series) -> pd.Series:
    """
    Dipakai kalau nanti kamu mau pakai proxy "cukup kencang" di tempat lain.
    """
    cc_ok = pd.to_numeric(cc_s, errors="coerce").fillna(0) >= 1500
    turbo_ok = model_s.astype(str).apply(has_turbo_model)
    fuel_ok = fuel_s.astype(str).str.lower().isin(["h", "p", "e"])  # HEV/PHEV/BEV
    return cc_ok | turbo_ok | fuel_ok


def _pw_series(cc: pd.Series, weight: pd.Series) -> pd.Series:
    """
    Power-to-weight ratio kasar: cc / berat(kg).
    """
    w = _series_num(weight).replace(0, np.nan)
    c = _series_num(cc)
    return c / w  # cc per kg


# Helper: parse dimension string menjadi (L, W, H) dalam mm
def parse_dimension(dim: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Parse variasi string dimension menjadi tuple (length_mm, width_mm, height_mm).
    Menerima '4490 x 1788 x 1540', '4490 X 1788 X 1540', '4490×1788×1540', dsb.
    Jika gagal, kembalikan (None, None, None).
    """
    if dim is None:
        return None, None, None
    try:
        s = str(dim).lower()
        s = s.replace("×", "x").replace("mm", "")
        # bersihkan kata-kata non-digit kecuali 'x' dan '-' '.' ','
        s = re.sub(r'[^0-9x\.\,\-\s]', ' ', s)
        parts = re.split(r'[x]', s)
        parts = [p.strip().replace(",", "") for p in parts if p.strip()]
        if len(parts) < 3:
            # ada kemungkinan format "P x L x T: 4490 x 1788 x 1540" -> ambil angka saja
            nums = re.findall(r'(\d{3,4})', s)
            if len(nums) >= 3:
                return float(nums[0]), float(nums[1]), float(nums[2])
            return None, None, None
        L = float(parts[0])
        W = float(parts[1])
        H = float(parts[2])
        return L, W, H
    except Exception:
        return None, None, None


# ganti fungsi lama dengan ini di backend/spk_hard.py
def is_obvious_commercial_by_dimension(length, width, height):
    """
    Versi yang aman untuk scalar atau array-like (pandas Series / numpy array).
    - Untuk scalar: kembalikan bool.
    - Untuk array-like (pd.Series / np.ndarray): kembalikan pd.Series[bool] dengan index input (jika Series).
    Threshold konservatif; juga memasukkan trigger khusus 5140x1928x1880.
    """
    import numpy as _np
    import pandas as _pd

    # helper untuk cek apakah input tampak seperti Series/array
    is_series_like = isinstance(length, (_pd.Series, _np.ndarray)) or isinstance(width, (_pd.Series, _np.ndarray)) or isinstance(height, (_pd.Series, _np.ndarray))

    if is_series_like:
        # ubah semua input ke Series yang aligned pada index jika salah satunya Series
        # prefer index dari salah satu Series; jika semuanya array-like tanpa index, gunakan RangeIndex
        def to_series(x):
            if isinstance(x, _pd.Series):
                return x.astype(float)
            if isinstance(x, _np.ndarray):
                return _pd.Series(x.astype(float))
            # scalar -> series broadcast
            try:
                return _pd.Series([float(x)] * 1)
            except Exception:
                return _pd.Series([_np.nan] * 1)

        # jika salah satu adalah Series, gunakan indexnya untuk broadcasting scalar/ndarray
        idx = None
        for v in (length, width, height):
            if isinstance(v, _pd.Series):
                idx = v.index
                break

        # buat Series dengan index yang konsisten
        if idx is not None:
            Ls = _pd.Series(length) if not isinstance(length, _pd.Series) else length.astype(float)
            Ws = _pd.Series(width)  if not isinstance(width,  _pd.Series) else width.astype(float)
            Hs = _pd.Series(height) if not isinstance(height, _pd.Series) else height.astype(float)
            # reindex broadcast scalar/numpy to idx if needed
            if not isinstance(length, _pd.Series):
                Ls = Ls.reindex(idx).astype(float)
            else:
                Ls = Ls.reindex(idx).astype(float)
            if not isinstance(width, _pd.Series):
                Ws = Ws.reindex(idx).astype(float)
            else:
                Ws = Ws.reindex(idx).astype(float)
            if not isinstance(height, _pd.Series):
                Hs = Hs.reindex(idx).astype(float)
            else:
                Hs = Hs.reindex(idx).astype(float)
        else:
            # tidak ada Series input — gunakan numpy broadcast ke panjang max dari arrays (jika ada)
            arr_lengths = []
            for v in (length, width, height):
                if isinstance(v, _np.ndarray):
                    arr_lengths.append(len(v))
            maxlen = max(arr_lengths) if arr_lengths else 1
            def broadcast_to_len(v):
                if isinstance(v, _np.ndarray):
                    return _pd.Series(v.astype(float))
                if isinstance(v, _pd.Series):
                    return v.astype(float).reset_index(drop=True)
                # scalar
                return _pd.Series([float(v)] * maxlen)
            Ls = broadcast_to_len(length)
            Ws = broadcast_to_len(width)
            Hs = broadcast_to_len(height)

        # sekarang lakukan vektorisasi kondisi
        cond_strict = (Ls >= 5140) & (Ws >= 1928) & (Hs >= 1880)
        cond_general = (Ls >= 5200) | (Hs >= 2000) | (Ws >= 2100) | ((Ls >= 5400) & (Hs >= 1850))
        return (cond_strict | cond_general).fillna(False).astype(bool)

    else:
        # scalar path (existing behavior)
        try:
            L = float(length) if length is not None else None
            W = float(width)  if width  is not None else None
            H = float(height) if height is not None else None
        except Exception:
            return False

        if L is None or W is None or H is None:
            return False

        if L >= 5140 and W >= 1928 and H >= 1880:
            return True
        if L >= 5200 or H >= 2000 or W >= 2100:
            return True
        if L >= 5400 and H >= 1850:
            return True
        return False


def hard_constraints_filter(cand_feat: pd.DataFrame, needs: List[str]) -> pd.Series:
    """
    Filter WAJIB berdasarkan:
    - kursi, segmen, ukuran, AWD, dll
    - kombinasi kebutuhan (keluarga, perkotaan, fun, offroad, niaga)

    Perbaikan & aturan tambahan:
    - Di kota jangan pilih yang terlalu kecil (microcar) tapi juga jangan pilih truk/niaga
    - Keluarga minimal 6 kursi, keluarga kecil 5 kursi (dengan pengecekan ruang)
    - Jika dimension = 5140 x 1928 x 1880 -> prefer niaga (sesuai permintaan)
    - Jangan sampai SUV/MPV/Alphard-like (mis. 4450 x 1775 x 1710) masuk niaga
    - Tambah kolom debug 'spk_hard_reason' jika diinginkan (tidak wajib)
    """
    needs = needs or []
    n = len(cand_feat)
    if n == 0:
        return pd.Series([], dtype=bool, index=cand_feat.index)

    # Numeric series (safe)
    seats = _series_num(cand_feat.get("seats"))
    seg = cand_feat.get("segmentasi", pd.Series([""] * n, index=cand_feat.index)).astype(str)
    model = cand_feat.get("model", pd.Series([""] * n, index=cand_feat.index)).astype(str)
    length = _series_num(cand_feat.get("length_mm"))
    width = _series_num(cand_feat.get("width_mm"))
    weight = _series_num(cand_feat.get("vehicle_weight_kg"))
    wb = _series_num(cand_feat.get("wheelbase_mm"))
    cc = _series_num(cand_feat.get("cc_kwh_num"))
    awd = _series_num(cand_feat.get("awd_flag")).fillna(0.0)
    rim = _series_num(cand_feat.get("rim_inch"))
    tyr = _series_num(cand_feat.get("tyre_w_mm"))
    doors = _series_num(cand_feat.get("doors_num"))
    fuel = cand_feat.get("fuel_code", pd.Series(["o"] * n, index=cand_feat.index)).astype(str)

    # parsing dimension raw jika ada beberapa varian nama kolom
    # coba kolom umum 'DIMENSION P x L xT', 'dimension', 'dimension_str', dsb.
    dim_candidates = None
    for col in cand_feat.columns:
        if col.lower().startswith("dimension") or "p x l" in col.lower() or "dimension p" in col.lower():
            dim_candidates = cand_feat[col]
            break
    if dim_candidates is None and "dimension" in cand_feat.columns:
        dim_candidates = cand_feat["dimension"]
    if dim_candidates is None:
        dim_candidates = pd.Series([None] * n, index=cand_feat.index)

    parsed_dims = dim_candidates.apply(parse_dimension)
    dimL = pd.Series([p[0] for p in parsed_dims], index=cand_feat.index)
    dimW = pd.Series([p[1] for p in parsed_dims], index=cand_feat.index)
    dimH = pd.Series([p[2] for p in parsed_dims], index=cand_feat.index)

    # Normalize seg/body_type small set
    def norm_body(s: str) -> str:
        if not isinstance(s, str):
            return ""
        s0 = s.strip().lower()
        s0 = re.sub(r'[^a-z0-9\s\-]', '', s0)
        # map beberapa varian
        s0 = s0.replace("cross over", "crossover").replace("cross-over", "crossover")
        return s0

    seg_norm = seg.astype(str).apply(norm_body)

    # ---------------------------------------------------------------------
    # Persentil — adaptif terhadap inventory
    # ---------------------------------------------------------------------
    def pct(s: pd.Series, q: float, fallback):
        try:
            if s.dropna().size > 0:
                return float(np.nanpercentile(s.dropna(), q))
            return fallback
        except Exception:
            return fallback

    p_len60 = pct(length, 60, -np.inf)
    p_len70 = pct(length, 70, -np.inf)
    p_len50 = pct(length, 50, -np.inf)
    p_len10 = pct(length, 10, -np.inf)

    p_wid60 = pct(width, 60, -np.inf)
    p_wid50 = pct(width, 50, -np.inf)
    p_wid10 = pct(width, 10, -np.inf)

    p_wgt50 = pct(weight, 50, np.inf)
    p_wgt90 = pct(weight, 90, np.inf)

    p_wb60 = pct(wb, 60, -np.inf)

    # Proxy power-to-weight
    pw = _pw_series(cc, weight)
    p_pw55 = pct(pw, 55, -np.inf)

    # Cepat (FUN) heuristics
    turbo_ok = model.apply(has_turbo_model)
    fuel_ok = fuel.str.lower().isin(["h", "p", "e"])
    cc_ok = cc >= 1500
    rim_ok = (rim >= 17) | (tyr >= 205)
    pw_ok = pw >= p_pw55
    fast_ok = turbo_ok | fuel_ok | (cc_ok & (pw_ok | rim_ok))

    # mulai dari semua True
    mask = pd.Series(True, index=cand_feat.index)

    # optional: kolom debug alasan (tidak wajib; ada jika ingin analisa)
    reasons: Optional[pd.Series] = pd.Series("", index=cand_feat.index)

    # --- ATURAN BARU: KURSI >= 8 HANYA UNTUK NIAGA ---
    is_commuter_bus = seats >= 8
    if "niaga" not in needs:
        mask &= ~is_commuter_bus
        reasons = reasons.where(~is_commuter_bus, "rejected: seats>=8 && niaga not requested")

    # --- KOMBO: fun + keluarga + perkotaan -> WAJIB ≥4 pintu ---
    if {"fun", "keluarga", "perkotaan"}.issubset(set(needs)):
        idx = cand_feat.index
        if "doors_num" in cand_feat.columns:
            doors_s = pd.to_numeric(cand_feat["doors_num"], errors="coerce").reindex(idx)
        else:
            doors_s = pd.Series(np.nan, index=idx, dtype="float64")
        two_dr_pat = r"\b(?:2[\s\-]?door|2dr|two\s*door)\b"
        two_dr_txt = cand_feat.get("model", pd.Series([""] * n, index=cand_feat.index)).astype(str).str.contains(
            two_dr_pat, flags=re.I, regex=True, na=False
        ).reindex(idx)
        two_dr_seg = seg.astype(str).str.contains(r"\bcoupe\b", flags=re.I, regex=True, na=False).reindex(idx)
        two_dr_hint = (two_dr_txt | two_dr_seg).fillna(False)
        doors_rule = (doors_s >= 4) | (doors_s.isna() & (~two_dr_hint))
        doors_rule = doors_rule.reindex(idx).fillna(False)
        mask = mask & doors_rule
        reasons = reasons.where(doors_rule, "rejected: need >=4 doors for fun+keluarga+perkotaan")

    # --- keluarga ---
    if "keluarga" in needs:
        # jika fun/perkotaan masuk, izinkan 5-seater sebagai baseline, else minta minimal 6 (lebih aman)
        if "fun" in needs or "perkotaan" in needs:
            base_min = 5
        else:
            base_min = 6

        seats_ok = seats.fillna(0) >= base_min

        # Jika base_min == 5: pastikan tidak terlalu sempit
        if base_min == 5:
            # Lebar > 1.7m OR Wheelbase > 2.5m dianggap cukup; bila width NaN, biarkan (tolong validasi data)
            is_spacious = (width >= 1700) | (wb >= 2500) | width.isna()
            seats_ok = seats_ok & is_spacious

        # hint 3 baris kursi kalau data seats kosong (untuk base_min=6)
        three_row_hint = seg_norm.str.contains(
            r"\b(?:mpv|suv|minibus|van)\b", flags=re.I, regex=True, na=False
        ) & ((wb >= p_wb60) | (length >= p_len60))

        seats_ok = seats_ok | (seats.isna() & three_row_hint)
        mask &= seats_ok
        reasons = reasons.where(seats_ok, f"rejected: keluarga need seats>={base_min} or 3-row hint")

    # --- offroad ---
    if "offroad" in needs:
        forbid_sedan = seg_norm.str.contains(r"\bsedan\b", flags=re.I, regex=True, na=False)
        mask &= ~forbid_sedan
        mask &= (awd >= 0.5)
        reasons = reasons.where((~forbid_sedan) & (awd >= 0.5), "rejected: offroad needs AWD and not sedan")

    # --- perkotaan (short trip) ---
    if "perkotaan" in needs:
        # microcar: sangat pendek & sempit (<= 10th percentile)
        is_microcar = ((length <= p_len10) & (width <= p_wid10)) | seg_norm.str.contains(
            r"\b(?:city\s*car|kei|mini\s*car|microcar)\b", flags=re.I, regex=True, na=False
        )

        # deteksi truk/niaga berdasarkan segmentasi / pattern niaga
        niaga_pat = r"\b(?:pick\s*up|pickup|pu|box|blind\s*van|blindvan|niaga|light\s*truck|chassis|cab\s*/?\s*chassis|minibus|truck|lorry)\b"
        is_truck = seg_norm.str.contains(niaga_pat, flags=re.I, regex=True, na=False) | (weight >= p_wgt90)

        # definisi small_by_width agak longgar: fokus ke lebar agar parkir/gesit
        small_by_width = ((width <= p_wid60) | width.isna())

        # compact_length: panjang tidak terlalu panjang dibanding populasi (70th percentile)
        compact_length = ((length <= p_len70) | length.isna())

        # efisien = EV/HEV/PHEV atau cc kecil
        efficient = fuel.str.lower().isin(["h", "p", "e"]) | (cc <= 1500) | cc.isna()

        # special allowance untuk sedan kompak:
        sedan_mask = seg_norm.str.contains(r"\bsedan\b", flags=re.I, regex=True, na=False)
        allow_sedan_compact = sedan_mask & (width >= 1650) & (length <= p_len70) & (weight <= p_wgt50)

        # kalau mobil efisien (EV), ijinkan panjang/berat lebih besar selama lebarnya wajar
        if "fun" in needs:
            base_city = (small_by_width & efficient) | (fast_ok & efficient) | (small_by_width & compact_length) | allow_sedan_compact
        else:
            base_city = efficient | (small_by_width) | (compact_length & (width <= p_wid60)) | allow_sedan_compact

        # Hilangkan microcar dan truk dari opsi perkotaan (kecuali user minta niaga)
        base_city = base_city & (~is_microcar) & (~is_truck)

        # Tambahan: jangan biarkan kendaraan 'terlalu kecil' yang mengorbankan kenyamanan
        # (lihat distribusi: jika width < 1550 dan length < 3500 -> anggap terlalu kecil)
        too_tiny = (width < 1550) & (length < 3500)
        base_city = base_city & (~too_tiny)

        mask &= base_city
        reasons = reasons.where(base_city, "rejected: not suitable for perkotaan (size/efficiency/truck)")

    # --- fun ---
    if "fun" in needs:
        mask &= fast_ok
        if "perjalanan_jauh" not in needs:
            # Fun murni biasanya bukan MPV/Van (kecuali exceptional fast_ok)
            pass
        if "perkotaan" in needs:
            # Fun + City -> jangan MPV/Van/Minibus
            not_mpv = ~seg_norm.str.contains(r"\b(?:mpv|van|minibus)\b", flags=re.I, regex=True, na=False)
            mask &= not_mpv
            reasons = reasons.where(not_mpv, "rejected: fun+perkotaan excludes mpv/van/minibus")

    # --- niaga ---
    niaga_pat = r"\b(?:pick\s*up|pickup|pu|box|blind\s*van|blindvan|niaga|light\s*truck|chassis|cab\s*/?\s*chassis|minibus)\b"
    if "niaga" in needs:
        allow = seg_norm.str.contains(niaga_pat, flags=re.I, regex=True, na=False) | is_obvious_commercial_by_dimension(dimL, dimW, dimH)
        mask &= allow
        reasons = reasons.where(allow, "rejected: niaga requested but not truck/van/large-dim")
    if needs and "niaga" not in needs:
        # tambahkan rule eksplisit: jika seg menunjukkan komersial -> keluarkan
        is_niaga_by_seg = seg_norm.str.contains(niaga_pat, flags=re.I, regex=True, na=False)
        # juga jika dimension jelas komersial (contoh 5140x1928x1880) keluarkan (kecuali user memang minta niaga)
        is_niaga_by_dim = is_obvious_commercial_by_dimension(dimL, dimW, dimH)
        mask &= ~is_niaga_by_seg
        mask &= ~is_niaga_by_dim
        reasons = reasons.where(~(is_niaga_by_seg | is_niaga_by_dim), "rejected: niaga/truck or very large dimension (user didn't ask niaga)")

    # --- RULE KHUSUS: contoh yang Anda minta ---
    # Jika dimensinya >= 5140 x 1928 x 1880, maka kategorikan sebagai niaga (kecuali segmentasi eksplisit passenger yang kuat?)
    # Di sini kita tolak kandidat tersebut bila user tidak meminta niaga (sudah dilakukan di atas).
    # Namun jika kita tetap ingin menandai hal ini, alasan sudah tercatat di 'reasons'.

    # Pastikan dtype boolean dan index sama
    mask = mask.fillna(False).astype(bool)

    # Jika ingin debug, we could attach reasons ke dataframe luar. Untuk saat ini kembalikan mask saja.
    # Jika Anda mau, saya bisa ubah agar fungsi ini juga mengembalikan Series alasan:
    # return mask, reasons

    return mask
