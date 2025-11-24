# file: chatbot.py
from __future__ import annotations

from typing import Any, Dict, Optional

# ---------------------------------------------------------------------
# Import model & state
# ---------------------------------------------------------------------
from chat_schemas import ChatRequest, ChatReply
from recommendation_state import (
    set_last_recommendation as _set_last_recommendation,
    get_last_recommendation as _get_last_recommendation,
)

# Smart router (deteksi intent otomatis: explain / simulate / carinfo)
from smart_chat import build_smart_reply

# ---------------------------------------------------------------------
# Alias nama lama → tipe yang sebenarnya
# (supaya app.py tetap bisa import Chatbot2Request/Response, dst.)
# ---------------------------------------------------------------------

# Chatbot 2 = chatbot pintar (smart): jelasin rekomendasi + bisa tangkap what-if dasar
Chatbot2Request = ChatRequest
Chatbot2Response = ChatReply

# Chatbot 3 = simulasi what-if eksplisit
Chatbot3Request = ChatRequest
Chatbot3Response = ChatReply


# ---------------------------------------------------------------------
# Bungkus fungsi state rekomendasi
# ---------------------------------------------------------------------
def set_last_recommendation(payload: Optional[Dict[str, Any]]) -> None:
    """
    Dipanggil dari app.py setelah /recommendations.
    State sebenarnya disimpan di recommendation_state.py
    """
    _set_last_recommendation(payload)


def get_last_recommendation() -> Optional[Dict[str, Any]]:
    """
    Disediakan kalau mau dipakai juga di tempat lain.
    """
    return _get_last_recommendation()


# ---------------------------------------------------------------------
# Fungsi yang dipakai endpoint /chatbot2 dan /chatbot3 di app.py
# ---------------------------------------------------------------------
def build_chatbot_reply(message: str) -> Chatbot2Response:
    """
    Chat utama (bekas 'chatbot2'):
    - Menggunakan smart_chat.build_smart_reply
    - Bisa:
      * jelaskan kenapa mobil nomor 1
      * bandingkan mobil 1 & 2
      * jelaskan komposisi diesel/bensin/hybrid
      * tangkap beberapa skenario what-if (kalau budget naik/turun, hindari diesel, dll)
    """
    resp: ChatReply = build_smart_reply(message)
    return resp  # sudah ChatReply, alias-nya Chatbot2Response




__all__ = [
    "Chatbot2Request",
    "Chatbot2Response",
    "set_last_recommendation",
    "get_last_recommendation",
    "build_chatbot_reply",
]
