# file: chatbot.py
from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

# Coba import library Gemini (google-genai).
# Jika belum terinstal, fungsi akan kasih pesan error yang jelas.
try:
    from google import genai
    from google.genai import types as gtypes
except ImportError:  # tergantung environment
    genai = None
    gtypes = None

# NOTE: idealnya jangan hardcode API key di sini, tapi pakai env var saja.
# Untuk sementara mengikuti punyamu.
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "AIzaSyAJ511Y8MiyGquKPy0hZe8FX9mu6sKSF4s",
)

# =====================================================================
#                     STATE: LAST_RECOMMENDATION
# =====================================================================
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
    LAST_RECOMMENDATION = payload


def get_last_recommendation() -> Optional[Dict[str, Any]]:
    return LAST_RECOMMENDATION


# =====================================================================
#                         SKEMA REQUEST/RESPONSE
# =====================================================================
class Chatbot2Request(BaseModel):
    message: str


class Chatbot2Response(BaseModel):
    reply: str
    suggested_questions: Optional[List[str]] = None


# =====================================================================
#                         CONFIG & PROMPT GEMINI
# =====================================================================
SYSTEM_PROMPT = """
Kamu adalah chatbot penjelas untuk sistem rekomendasi mobil Indonesia.
Kamu TIDAK memilih mobil baru, tapi hanya menjelaskan hasil rekomendasi yang sudah ada.

KONTEKS DATA:
- Server sudah menyimpan objek LAST_RECOMMENDATION yang berisi:
  - needs: daftar kebutuhan pengguna (misal: ["fun", "keluarga"])
  - budget: angka budget dalam rupiah
  - items: list mobil terurut dari rank 1, 2, 3, dst.
- Tiap item mobil punya kolom penting, misalnya:
  - brand, model, price, fuel, fuel_code, fuel_label
  - seats, segmentasi, awd_flag, cluster_label
  - fit_score, need_score, price_fit, popularity_z
  - alasan (teks alasan singkat dari mesin rekomendasi)

GAYA JAWABAN:
- Bahasa Indonesia santai tapi tetap sopan.
- Jawaban singkat-padat (2–6 kalimat), tapi jelas.
- Boleh menyebut angka (kursi, harga, cc) jika relevan, jangan terlalu kering.

HAL-HAL YANG PERLU DILAKUKAN:
1. Jika user tanya:
   - "Kenapa mobil ini nomor 1?" atau mirip:
     - Jelaskan kenapa mobil peringkat 1 cocok: hubungkan kebutuhan (needs) dengan fitur mobil.
     - Boleh pakai informasi: seats, segmentasi (mpv/suv/...), fuel_label, awd_flag, fit_score.
     - Rangkum juga alasan dari field "alasan" jika ada (tanpa harus sama persis).
2. Jika user tanya:
   - "Apa beda mobil 1 dan 2 ..." (misal untuk keluarga/offroad):
     - Bandingkan 2 mobil teratas: kapasitas kursi, jenis BBM, segmen bodi, adanya AWD atau tidak,
       tren harga/performa jika terlihat dari data.
     - Fokus ke perbedaan yang paling terasa untuk kebutuhan yang disebut user (keluarga, offroad, dsb).
3. Jika user tanya:
   - "Kenapa kok banyak yang diesel?":
     - Hitung komposisi jenis BBM di daftar items.
     - Jelaskan kenapa diesel bisa sering muncul (irit, torsi besar, cocok niaga/perjalanan jauh, dll),
       kaitkan dengan kebutuhan yang tersimpan di needs.

ATURAN PENTING:
- Jangan mengarang data mobil di luar items yang diberikan di konteks.
- Kalau ternyata data kurang (misal cuma ada 1 mobil), jujur saja dan jelaskan sebisanya.
- Jika pertanyaan di luar tiga pola di atas, tetap jawab sebisanya dengan memakai data items
  dan kebutuhan yang ada; jika benar-benar di luar konteks, jelaskan batasanmu dengan sopan.
"""


def _get_gemini_client() -> "genai.Client":
    """Inisialisasi client Gemini, atau lempar error jika belum siap."""
    if genai is None:
        raise RuntimeError(
            "Library 'google-genai' belum terinstal. "
            "Jalankan: pip install google-genai"
        )
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Environment variable GEMINI_API_KEY belum diset. "
            "Set dulu API key Gemini Anda, misal:\n"
            "  export GEMINI_API_KEY='API_KEY_ANDA'"
        )
    client = genai.Client(api_key=GEMINI_API_KEY)
    return client


def _call_gemini(prompt: str, rec: Dict[str, Any]) -> str:
    """
    Panggil Gemini dengan konteks LAST_RECOMMENDATION.
    DI SINI TIDAK ADA LAGI Part.from_text → pakai 1 string panjang saja.
    """
    client = _get_gemini_client()

    # Konversi rec jadi JSON string agar model punya konteks mentah
    rec_json = json.dumps(rec, ensure_ascii=False)

    # Gabungkan system prompt + data + pertanyaan user jadi satu teks panjang
    full_prompt = (
        SYSTEM_PROMPT.strip()
        + "\n\n--- DATA REKOMENDASI TERAKHIR (JSON) ---\n"
        + rec_json
        + "\n\n--- PERTANYAAN PENGGUNA ---\n"
        + prompt
        + "\n\nJawab sesuai instruksi di atas."
    )

    # Config boleh pakai gtypes kalau ada, kalau tidak ya tanpa config
    cfg = (
        gtypes.GenerateContentConfig(
            max_output_tokens=512,
            temperature=0.4,
        )
        if gtypes is not None
        else None
    )

    if cfg is not None:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
            config=cfg,
        )
    else:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=full_prompt,
        )

    # Versi baru biasanya punya response.text
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    # Fallback: ambil dari candidates[0].content.parts
    try:
        if getattr(response, "candidates", None):
            c0 = response.candidates[0]
            if getattr(c0, "content", None) and getattr(c0.content, "parts", None):
                parts: List[str] = []
                for p in c0.content.parts:
                    if getattr(p, "text", None):
                        parts.append(p.text)
                joined = "\n".join(parts).strip()
                if joined:
                    return joined
    except Exception:
        pass

    return "Maaf, aku belum bisa menjawab sekarang."


# =====================================================================
#                      FUNGSI UTAMA UNTUK FASTAPI
# =====================================================================
def build_chatbot_reply(message: str) -> Chatbot2Response:
    """
    Dipanggil dari app.py (/chatbot2).
    - Baca LAST_RECOMMENDATION
    - Panggil Gemini (kalau tersedia)
    - Bungkus ke Chatbot2Response
    """
    msg = (message or "").strip()
    if not msg:
        return Chatbot2Response(
            reply=(
                "Silakan tuliskan dulu pertanyaannya, misalnya: "
                "'Kenapa mobil nomor 1 yang dipilih?'"
            ),
            suggested_questions=[
                "Kenapa mobil ini nomor 1?",
                "Apa beda mobil peringkat 1 dan 2?",
                "Kenapa kok banyak yang diesel?",
            ],
        )

    rec = get_last_recommendation()
    if not rec or not rec.get("items"):
        return Chatbot2Response(
            reply=(
                "Belum ada rekomendasi mobil yang tersimpan. "
                "Coba jalankan pencarian rekomendasi dulu, lalu tanya lagi di sini."
            ),
            suggested_questions=[
                "Bantu rekomendasikan mobil dulu dong?",
            ],
        )

    # Fallback jika Gemini belum siap (tidak ada library / API key)
    if genai is None or not GEMINI_API_KEY:
        return Chatbot2Response(
            reply=(
                "Chatbot pintar (Gemini) belum diaktifkan di server.\n"
                "Namun secara garis besar aku bisa jelaskan:\n"
                "- Mobil nomor 1 dipilih karena punya skor kecocokan tertinggi "
                "berdasarkan kebutuhan dan budgetmu.\n"
                "- Kalau mau chatbot yang lebih pintar seperti GPT/Gemini, "
                "aktifkan dulu API key Gemini di backend."
            ),
            suggested_questions=[
                "Kenapa mobil ini nomor 1?",
                "Apa beda mobil 1 dan 2 untuk keluarga?",
                "Kenapa kok banyak yang diesel?",
            ],
        )

    try:
        answer = _call_gemini(msg, rec)
    except Exception as e:
        return Chatbot2Response(
            reply=(
                "Lagi ada kendala saat memanggil model bahasa (Gemini): "
                f"{e}\n\n"
                "Sementara aku belum bisa menjawab lebih detail."
            ),
            suggested_questions=[
                "Kenapa mobil ini nomor 1?",
                "Apa beda mobil peringkat 1 dan 2?",
            ],
        )

    suggested = [
        "Apa kelebihan mobil nomor 1 dibanding nomor 2?",
        "Kalau fokus keluarga saja, ada rekomendasi lain?",
        "Kalau saya ingin hemat BBM, mana yang lebih cocok?",
    ]

    return Chatbot2Response(
        reply=answer,
        suggested_questions=suggested,
    )
