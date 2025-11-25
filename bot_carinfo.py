# file: bot_carinfo.py
from __future__ import annotations

import os
import re
import json
from typing import Any, Dict, List, Optional

from chat_schemas import ChatReply
from recommendation_state import get_last_recommendation

# Gemini (opsional; untuk spek dari internet)
try:
    from google import genai
    from google.genai import types as gtypes
except ImportError:
    genai = None
    gtypes = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SYSTEM_PROMPT_CARINFO = """
Kamu adalah chatbot spesialis informasi spesifikasi mobil.

TUJUAN:
- Menjawab permintaan seperti:
  - "spek lengkap Palisade"
  - "spesifikasi lengkap rank 1"
  - "spek detail Subaru BRZ 2.4 AT ES ZD8"
- Fokus pada SPEK TEKNIS, bukan sekadar deskripsi pemasaran.

DATA INTERNAL:
- Server kadang mengirim JSON INTERNAL_SPEC yang berisi:
  - brand, model, type_model (atau "type model"), price, fuel/fuel_label
  - seats, doors, segmentasi, cc_kwh, trans, drive_sys, vehicle_weight, dimension
- Data internal TIDAK SELALU lengkap/benar, tapi:
  - brand, model, type_model, dan jenis BBM biasanya benar dan harus dihormati.
  - kamu boleh melengkapi dan sedikit mengoreksi detil (misalnya tenaga/torsi),
    tapi jangan mengganti merek atau model.

TUGAS:
1. Gunakan pengetahuanmu + sumber eksternal untuk mencari spesifikasi teknis
   mobil yang diminta (jika memungkinkan untuk pasar global/Indonesia).
2. Selalu kaitkan jawabanmu dengan INTERNAL_SPEC kalau ada:
   - Kalau INTERNAL_SPEC bilang mobilnya coupe 2 pintu 4 kursi,
     jangan bilang itu MPV 7 kursi.
3. Jawaban utamakan ANGKA dan fitur teknis, bukan promosi.

FORMAT JAWABAN:
- Satu kalimat pembuka (singkat).
- Lanjutkan dengan bullet point (-) yang terstruktur, misalnya:
  - Harga kisaran (jika diketahui, boleh kisaran Indonesia atau global).
  - Tipe bodi / segmen.
  - Mesin: konfigurasi, kapasitas pasti (cc), tenaga (PS/hp + rpm), torsi (Nm + rpm).
  - Transmisi: jenis dan jumlah percepatan.
  - Sistem penggerak: FWD/RWD/AWD/4WD (FF/FR, dsb).
  - Dimensi: panjang x lebar x tinggi, wheelbase.
  - Berat kosong (kalau ada).
  - Ukuran ban/velg (kalau ada).
  - Kapasitas kursi dan jumlah pintu.
  - Kapasitas bagasi dan tangki (kalau ada).
  - Fitur keselamatan utama: jumlah airbag, ABS/EBD, ESC, ADAS (AEB, lane keep, dsb).
  - Fitur kenyamanan/infotainment penting.
- Jika ada perbedaan spek antar pasar:
  - jelaskan bahwa spesifikasi bisa berbeda tergantung negara,
    lalu tetap berikan nilai "umumnya" (kisaran yang realistis).

ATURAN:
- Kalau kamu ragu dengan angka persis, beri penjelasan "sekitar" atau "umumnya"
  tapi tetap berikan angka estimasi (misalnya "sekitar 6 airbag").
- Jangan mengarang spek yang jelas tidak masuk akal.
- Di akhir jawaban, tambahkan 1 kalimat disclaimer bahwa
  data perlu dicek lagi ke brosur resmi/website ATPM sebelum keputusan beli.
"""


# ============================== UTIL ===================================

def _get_gemini_client():
    if genai is None:
        raise RuntimeError(
            "Library 'google-genai' belum terinstal. "
            "Jalankan: pip install google-genai"
        )
    if not GEMINI_API_KEY:
        raise RuntimeError("Environment variable GEMINI_API_KEY belum diset.")
    return genai.Client(api_key=GEMINI_API_KEY)


def _fmt_rp(v: Any) -> str:
    try:
        return "Rp{:,.0f}".format(float(v)).replace(",", ".")
    except Exception:
        return "-"


def _clean_str(x: Any) -> str:
    return str(x or "").strip()


# ================== PILIH MOBIL TARGET DARI REKOMENDASI =================

_RANK_PATTERN = re.compile(r"(rank|peringkat|nomor|no)\s*(\d+)", re.IGNORECASE)


def _extract_rank_from_message(q: str) -> Optional[int]:
    """
    Cari 'rank 1', 'nomor 2', 'no 3' di teks → return index (1-based).
    """
    m = _RANK_PATTERN.search(q)
    if not m:
        return None
    try:
        return int(m.group(2))
    except Exception:
        return None


def _select_item_from_rec(message: str, rec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    - Kalau user sebut 'rank 1 / nomor 2' → ambil item sesuai.
    - Kalau user sebut nama mobil (mini, palisade, brz, dll),
      coba cari yang mengandung brand/model/type_model.
    """
    if not rec:
        return None

    items: List[Dict[str, Any]] = rec.get("items") or []
    if not items:
        return None

    q = (message or "").lower()

    # 1) Referensi rank eksplisit
    r = _extract_rank_from_message(q)
    if r is not None and 1 <= r <= len(items):
        return items[r - 1]

    # 2) Coba cocokkan nama brand/model yang disebut
    #    Jika ada banyak, ambil yang pertama cocok.
    best_idx = None
    best_score = 0

    for idx, it in enumerate(items):
        brand = _clean_str(it.get("brand")).lower()
        model = _clean_str(it.get("model")).lower()
        type_model = _clean_str(it.get("type_model") or it.get("type model")).lower()

        score = 0
        if brand and brand in q:
            score += 2
        if model and model in q:
            score += 3
        if type_model and type_model in q:
            score += 3

        # contoh: 'mini jcw' → brand 'mini', model/type_model mengandung 'jcw'
        if "mini" in q and ("jcw" in q or "john cooper works" in q):
            if brand == "mini":
                score += 4

        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx is not None and best_score > 0:
        return items[best_idx]

    # 3) Tidak ketemu nama spesifik → kalau dia sebut "rank 1" tanpa data items,
    #    tapi kita tidak bisa parse → fallback ke item[0].
    return items[0]


def _build_internal_spec(item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not item:
        return None

    return {
        "brand": _clean_str(item.get("brand")),
        "model": _clean_str(item.get("model")),
        "type_model": _clean_str(item.get("type_model") or item.get("type model")),
        "price": item.get("price"),
        "price_str": _fmt_rp(item.get("price")),
        "segmentasi": _clean_str(item.get("segmentasi") or item.get("segment")),
        "seats": item.get("seats"),
        "doors": item.get("DOOR") or item.get("door") or item.get("doors"),
        "fuel": _clean_str(item.get("fuel")),
        "fuel_label": _clean_str(item.get("fuel_label")),
        "cc_kwh": item.get("cc_kwh") or item.get("cc / kwh"),
        "trans": _clean_str(item.get("trans")),
        "drive_sys": _clean_str(item.get("drive sys") or item.get("drive_sys") or item.get("drivetrain")),
        "vehicle_weight": item.get("vehicle_weight"),
        "dimension": _clean_str(item.get("DIMENSION P x L xT") or item.get("dimension")),
        "wheel_base": item.get("WHEEL BASE") or item.get("wheelbase"),
        "ps_hp": _clean_str(item.get("PS / HP") or item.get("PS \/ HP") or item.get("ps_hp")),
    }


# ===================== PANGGIL GEMINI UNTUK SPEK =======================

def _call_gemini_carinfo(user_message: str, internal_spec: Optional[Dict[str, Any]]) -> str:
    client = _get_gemini_client()

    internal_json = json.dumps(internal_spec or {}, ensure_ascii=False)

    full_prompt = (
        SYSTEM_PROMPT_CARINFO.strip()
        + "\n\nINTERNAL_SPEC_JSON:\n"
        + internal_json
        + "\n\nPERTANYAAN_PENGGUNA:\n"
        + user_message
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=full_prompt,
        config=gtypes.GenerateContentConfig(
            max_output_tokens=800,
            temperature=0.4,
        ),
    )

    text = getattr(response, "text", "") or ""
    text = text.strip()
    if not text:
        return (
            "Aku belum bisa mengambil spesifikasi lengkap sekarang. "
            "Silakan cek brosur resmi atau website ATPM sebagai referensi utama."
        )
    return text


# ======================= FALLBACK TANPA GEMINI =========================

def _fallback_internal_only(internal_spec: Optional[Dict[str, Any]]) -> str:
    if not internal_spec:
        return (
            "Untuk fitur spek lengkap mobil, aku mengandalkan layanan Gemini "
            "untuk mengambil informasi dari luar. Saat ini Gemini belum aktif "
            "atau terjadi kendala, jadi aku belum bisa mengambil spesifikasi detail.\n"
            "Silakan cek brosur resmi atau website ATPM untuk sementara."
        )

    b = internal_spec
    brand = b.get("brand") or ""
    model = b.get("model") or b.get("type_model") or ""
    name = f"{brand} {model}".strip()

    lines: List[str] = []
    lines.append(f"Berikut spesifikasi utama dari data internal untuk {name}:")

    if b.get("price_str") and b["price_str"] != "-":
        lines.append(f"- Harga OTR (perkiraan dari dataset): {b['price_str']}")
    if b.get("segmentasi"):
        lines.append(f"- Segmen/jenis bodi: {b['segmentasi']}")
    if b.get("seats"):
        lines.append(f"- Kapasitas kursi (dataset): {b['seats']} penumpang")
    if b.get("doors"):
        lines.append(f"- Jumlah pintu (dataset): {b['doors']}")
    if b.get("trans"):
        lines.append(f"- Transmisi (dataset): {b['trans']}")
    if b.get("fuel_label") or b.get("fuel"):
        fuel = b.get("fuel_label") or b.get("fuel")
        lines.append(f"- Jenis bahan bakar (dataset): {fuel}")
    if b.get("cc_kwh"):
        lines.append(f"- Kapasitas mesin/baterai (cc/kWh, dataset): {b['cc_kwh']}")
    if b.get("drive_sys"):
        lines.append(f"- Sistem penggerak (dataset): {b['drive_sys']}")
    if b.get("vehicle_weight"):
        lines.append(f"- Berat kendaraan (dataset): {b['vehicle_weight']}")
    if b.get("dimension"):
        lines.append(f"- Dimensi (PxLxT, dataset): {b['dimension']}")
    if b.get("ps_hp"):
        lines.append(f"- Tenaga (PS/HP, dataset): {b['ps_hp']}")

    lines.append(
        "Catatan: data di atas murni dari dataset internal dan belum diverifikasi "
        "ke brosur resmi. Untuk keputusan beli, tetap cek spesifikasi terbaru dari "
        "website atau dealer resmi."
    )
    return "\n".join(lines)


# ============================ ENTRYPOINT ================================

def build_carinfo_reply(message: str) -> ChatReply:
    """
    Chatbot 4: info spek mobil.
    - Kalau Gemini aktif → gunakan Gemini + anchor internal_spec.
    - Kalau Gemini mati/error → fallback ke ringkasan data internal.
    """
    msg = (message or "").strip()
    rec = get_last_recommendation()
    item = _select_item_from_rec(msg, rec)
    internal_spec = _build_internal_spec(item)

    # Kalau Gemini tidak siap → pure internal
    if genai is None or not GEMINI_API_KEY:
        reply = _fallback_internal_only(internal_spec)
        return ChatReply(
            reply=reply,
            suggested_questions=[
                "Kenapa mobil ini nomor 1?",
                "Apa beda mobil nomor 1 dan 2?",
            ],
        )

    try:
        answer = _call_gemini_carinfo(msg, internal_spec)
    except Exception:
        # Jangan bocorkan error teknis ke user, cukup fallback rapi
        answer = _fallback_internal_only(internal_spec)

    return ChatReply(
        reply=answer,
        suggested_questions=[
            "Kenapa mobil ini nomor 1?",
            "Apa beda mobil nomor 1 dan 2?",
        ],
    )
