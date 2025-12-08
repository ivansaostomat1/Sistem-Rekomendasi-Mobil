# file: spk.py
from __future__ import annotations

# Wrapper supaya import lama seperti `from spk import build_master, rank_candidates`
# tetap bekerja setelah file dipecah menjadi beberapa modul.

from .spk_utils import (
    SEG_SEDAN, SEG_HATCH, SEG_COUPE, SEG_MPV, SEG_SUV, SEG_PICKUP,
    NEED_LABELS,
    zscore, sigmoid, price_fit_score,
    contains_ci, _norm_trans, vector_match_trans,
    get_standard_depreciation_rate, fuel_to_code,
    _series_num, assign_array_safe, _dbg, _ensure_df, price_fit_anchor,
)

from .spk_features import (
    has_turbo,
    add_need_features,
    build_master,
)

from .spk_rank import (
    sanitize_needs,
    hard_constraints_filter,
    compute_percentiles,
    soft_multiplier,
    style_adjust_multiplier,
    rank_candidates,
)

# Alias bermanfaat (kalau mau dipakai langsung)
has_turbo_model = has_turbo
