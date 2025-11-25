# file: smart_chat.py
from __future__ import annotations

from typing import Literal
import re

from chat_schemas import ChatReply
from recommendation_state import get_last_recommendation
from bot_explain import build_explanation_reply
from bot_carinfo import build_carinfo_reply


# ======================= DETEKSI POLA PERTANYAAN =======================

def _looks_like_rank_ref(q: str) -> bool:
    """
    Deteksi kalimat yang menyebut nomor mobil / peringkat:
    'mobil nomor 2', 'mobil 3', 'peringkat 1', 'rank 2', dll.
    """
    return bool(
        re.search(r"\b(mobil|no|nomor|peringkat|rank)\s*\d+\b", q)
    )

def _looks_like_simulation(q: str) -> bool:
    """
    Deteksi pertanyaan gaya simulasi 'what-if'.
    CATATAN: kalau sudah jelas minta 'spek/spesifikasi/detail',
    JANGAN dianggap simulasi.
    """
    q = q.lower()

    # 🔴 Tambahan penting: kalau ada kata "spek"/"spesifikasi" → bukan simulasi
    if any(k in q for k in ["spek", "spesifikasi", "detail", "spek lengkap", "spesifikasi lengkap"]):
        return False

    # pola what-if klasik
    if any(w in q for w in ["kalau ", "misal ", "andaikan", "what if"]):
        return True

    if "budget" in q or "anggaran" in q or "harga" in q:
        if any(
            w in q
            for w in [
                "naik",
                "naikin",
                "naikkan",
                "tambah",
                "turun",
                "turunin",
                "turunkan",
                "kurang",
                "dipotong",
                "lebih besar",
                "lebih kecil",
                "jadi ",
                "menjadi ",
            ]
        ):
            return True

    if "diesel" in q and any(w in q for w in ["hindari", "jangan", "tanpa", "anti"]):
        return True

    if "transmisi" in q or "transmission" in q or "gearbox" in q:
        if any(w in q for w in ["automatic", "otomatis", "matic", "at", "manual", "mt"]):
            return True

    return False


def _detect_intent(message: str) -> Literal["explain", "simulate", "carinfo"]:
    q = (message or "").lower().strip()

    # --- INFO MOBIL / SPEK LENGKAP (chatbot 4) — PRIORITAS TERTINGGI ---
    # Kalau ada kata "spek/spesifikasi/detail", anggap ini permintaan spek,
    # walaupun ada "nomor 1", "rank 1", dll.
    if any(
        k in q
        for k in [
            "spek",
            "spesifikasi",
            "detail",
            "spek lengkap",
            "spesifikasi lengkap",
        ]
    ):
        return "carinfo"

    # --- PENJELASAN REKOMENDASI (chatbot 2) ---
    if any(k in q for k in ["kenapa", "mengapa", "alasan"]):
        return "explain"
    if any(k in q for k in ["nomor 1", "no 1", "rank 1", "peringkat 1", "mobil 1"]):
        return "explain"
    if "beda" in q or "perbedaan" in q or "banding" in q or " vs " in q:
        return "explain"
    if "diesel" in q:
        return "explain"

    # default: penjelasan rekomendasi
    return "explain"

# ============================ ENTRYPOINT ================================

def build_smart_reply(message: str) -> ChatReply:
    """
    Dipanggil dari endpoint /chat di app.py.
    - Tangani empty message
    - Blokir pertanyaan simulasi (bot 3 sudah dimatikan)
    - Route ke:
        * build_explanation_reply → bot 2 (penjelasan rekomendasi)
        * build_carinfo_reply     → bot 4 (info spek mobil)
    """
    msg = (message or "").strip()
    if not msg:
        return ChatReply(
            reply=(
                "Silakan tuliskan dulu pertanyaannya. Contoh:\n"
                "- Kenapa mobil peringkat 1 yang dipilih untuk saya?\n"
                "- Apa beda mobil nomor 1 dan 2?\n"
                "- Berikan spek lengkap All New Avanza."
            ),
            suggested_questions=[
                "Kenapa mobil ini nomor 1?",
                "Apa beda mobil 1 dan 2?",
                "Berikan spek lengkap Toyota All New Avanza.",
            ],
        )

    q = msg.lower()

    # 1) Pertanyaan gaya simulasi → jawab jujur fitur belum aktif
    if _looks_like_simulation(q):
        return ChatReply(
            reply=(
                "Fitur simulasi 'what-if' (misalnya naik/turun budget, ubah kebutuhan, "
                "hindari jenis BBM tertentu) untuk sementara belum diaktifkan.\n\n"
                "Sekarang aku fokus ke dua hal:\n"
                "1) Menjelaskan alasan dan perbedaan hasil rekomendasi mobil yang sudah muncul.\n"
                "2) Memberikan informasi spesifikasi mobil berdasarkan data yang ada di sistem."
            ),
            suggested_questions=[
                "Kenapa mobil peringkat 1 yang dipilih untuk saya?",
                "Apa beda mobil nomor 1 dan 2?",
                "Berikan spek lengkap Honda Brio Satya.",
            ],
        )

    # 2) Tentukan intent (explain / carinfo)
    intent = _detect_intent(msg)
    rec = get_last_recommendation()

    # EXPLAIN: butuh LAST_RECOMMENDATION
    if intent == "explain":
        if not rec or not rec.get("items"):
            return ChatReply(
                reply=(
                    "Belum ada hasil rekomendasi yang tersimpan di server.\n"
                    "Jalankan dulu form rekomendasi mobil, kemudian tanya lagi di sini "
                    "untuk penjelasan peringkat atau alasan pemilihan mobil."
                ),
                suggested_questions=[
                    "Bantu rekomendasikan mobil dulu dong?",
                ],
            )
        return build_explanation_reply(msg, rec)

    # CARINFO: info spek mobil berdasarkan nama/tipe
    return build_carinfo_reply(msg)
