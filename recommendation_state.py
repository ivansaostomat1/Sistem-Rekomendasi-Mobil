# file: recommendation_state.py
from __future__ import annotations

from typing import Any, Dict, Optional
import time

LAST_RECOMMENDATION: Optional[Dict[str, Any]] = None


def set_last_recommendation(payload: Optional[Dict[str, Any]]) -> None:
    """
    Diset dari /recommendations di app.py.

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
    global LAST_RECOMMENDATION
    if payload is None:
        LAST_RECOMMENDATION = None
    else:
        data = dict(payload)
        data.setdefault("timestamp", time.time())
        LAST_RECOMMENDATION = data


def get_last_recommendation() -> Optional[Dict[str, Any]]:
    return LAST_RECOMMENDATION
