# file: backend/recommendation_state.py
from __future__ import annotations

from typing import Any, Dict, Optional
import time

# payload terakhir yang disimpan dari mesin rekomendasi
_LAST_RECOMMENDATION: Optional[Dict[str, Any]] = None


def set_last_recommendation(payload: Optional[Dict[str, Any]]) -> None:
    """
    Diset dari /recommendations atau dari run_recommendation_from_chat.

    payload minimal:
    {
        "timestamp": float,
        "needs": List[str],
        "budget": float,
        "filters": Dict[str, Any],
        "count": int,
        "items": List[Dict[str, Any]]
    }
    """
    global _LAST_RECOMMENDATION
    if payload is None:
        _LAST_RECOMMENDATION = None
        return

    # copy tipis + pastikan ada timestamp
    data = dict(payload)
    data.setdefault("timestamp", time.time())
    _LAST_RECOMMENDATION = data


def get_last_recommendation() -> Optional[Dict[str, Any]]:
    """
    Ambil payload rekomendasi terakhir (bisa None).
    """
    return _LAST_RECOMMENDATION
