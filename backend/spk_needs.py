# file: backend/spk_needs.py
from __future__ import annotations
from typing import List

from .spk_utils import NEED_LABELS


def _resolve_pair_keep_first(needs: List[str], a: str, b: str) -> List[str]:
    if a in needs and b in needs:
        if needs.index(a) < needs.index(b):
            return [n for n in needs if n != b]
        else:
            return [n for n in needs if n != a]
    return needs


def sanitize_needs(raw: List[str]) -> List[str]:
    """
    - Hilangkan duplikat (pertahankan urutan)
    - Mutual exclusion:
        fun ⟂ {offroad, niaga}
        perjalanan_jauh ⟂ perkotaan
    - Maks 3 kebutuhan.
    """
    if not raw:
        return []
    seen, needs = set(), []
    for n in raw:
        n = str(n).strip().lower()
        if n in NEED_LABELS and n not in seen:
            needs.append(n)
            seen.add(n)

    needs = _resolve_pair_keep_first(needs, "fun", "offroad")
    needs = _resolve_pair_keep_first(needs, "fun", "niaga")
    needs = _resolve_pair_keep_first(needs, "perjalanan_jauh", "perkotaan")

    if len(needs) > 3:
        needs = needs[:3]
    return needs
