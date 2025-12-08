# file: backend/schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# =========================
#    REKOMENDASI MOBIL
# =========================

class RecommendFilters(BaseModel):
    """
    Filter tambahan untuk endpoint rekomendasi mobil.
    - trans_choice: "Matic" / "Manual" / None
    - brand      : nama brand (bisa partial)
    - fuels      : ['g','d','h','p','e'] ATAU label yang nanti dinormalisasi
    """
    trans_choice: Optional[str] = None
    brand: Optional[str] = None
    fuels: Optional[List[str]] = None


class RecommendRequest(BaseModel):
    """
    Body request untuk /recommendations.
    """
    budget: float
    topn: Optional[int] = 6
    # pakai default_factory supaya tidak pakai list mutable shared
    needs: List[str] = Field(default_factory=list)
    filters: Optional[RecommendFilters] = None


# =========================
#    CHATBOT
# =========================

class ChatRequest(BaseModel):
    """
    Body request untuk endpoint /chat (kalau mau dipakai).
    """
    sender: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    """
    Response standar untuk chatbot (opsional, kalau mau dipakai di type hints).
    """
    sender: str
    reply: str
    suggested_questions: List[str] = Field(default_factory=list)
