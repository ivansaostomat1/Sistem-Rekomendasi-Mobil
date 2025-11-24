# file: bot_explain.py
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Tuple, Optional

import numpy as np

from chat_schemas import ChatReply

# Gemini
try:
    from google import genai
    from google.genai import types as gtypes
except ImportError:
    genai = None
    gtypes = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

SYSTEM_PROMPT_EXPLAIN = """
Kamu adalah chatbot penjelas untuk sistem rekomendasi mobil Indonesia.
Kamu TIDAK memilih mobil baru dari nol, tapi menjelaskan hasil rekomendasi yang
sudah dihitung oleh mesin.

KONTEKS DATA (JSON):
- Server mengirim objek LAST_RECOMMENDATION:
  - needs: daftar kebutuhan pengguna (misal: ["fun", "keluarga"])
  - budget: budget dalam rupiah
  - items: list mobil terurut dari rank 1, 2, 3, dst.
- Setiap item punya field penting:
  - brand, model, price, fuel_label/fuel, seats, segmentasi, awd_flag
  - fit_score, need_score, price_fit, popularity_z
  - alasan: teks alasan singkat dari mesin rekomendasi.

GAYA JAWABAN:
- Bahasa Indonesia santai tapi sopan.
- 2–6 kalimat, singkat tapi jelas.
- Boleh menyebut angka (kursi, harga, cc, tipe BBM) kalau relevan.

KASUS KHUSUS:
1) Jika user bertanya "Kenapa mobil ini nomor 1?" / "Kenapa mobil no 1?" dll:
   - Jelaskan kenapa item rank 1 cocok:
     * Hubungkan kebutuhan pengguna (needs) dengan fitur mobil (seats, segmen MPV/SUV,
       awd_flag, jenis BBM, dll).
     * Gunakan informasi dari field 'alasan' sebagai bahan, boleh diparafrase.

2) Jika user bertanya perbedaan mobil 1 dan 2:
   - Bandingkan 2 mobil teratas:
     * kapasitas kursi
     * jenis BBM / fuel_label
     * segmen bodi (segmentasi)
     * ada AWD/4x4 atau tidak
   - Fokuskan penjelasan sesuai kebutuhan (keluarga, offroad, perjalanan_jauh, dll).

3) Jika user bertanya kenapa banyak yang diesel:
   - Hitung komposisi jenis BBM di items (berapa diesel, bensin, hybrid, dsb).
   - Jelaskan kenapa diesel sering muncul:
     * torsi besar, cocok untuk muatan/jalan jelek
     * irit untuk perjalanan jauh, dll.
   - Hubungkan dengan needs yang ada.

ATURAN:
- Jangan karang mobil di luar yang ada di JSON.
- Jika data kurang (misal cuma 1 mobil), jujur saja dan jelaskan sebisanya.
- Kalau pertanyaan di luar 3 pola di atas, tetap jawab sebisanya pakai data items dan needs.
"""


# ============================= UTIL UMUM ==============================

def _get_items(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(rec.get("items") or [])


def _fmt_rp(v: Any) -> str:
    try:
        return "Rp{:,.0f}".format(float(v)).replace(",", ".")
    except Exception:
        return "-"


def _extract_rank_from_message(message: str) -> int:
    """
    Ambil rank yang disebut user:
      - 'mobil nomor 2', 'mobil no 3', 'rank 4', 'peringkat 2', 'mobil 1'
    Kalau tidak ketemu → default 1.
    """
    q = message.lower()
    # Cari pola yang eksplisit menyebut rank
    m = re.search(r"(mobil|no|nomor|rank|peringkat)\s*([1-9]\d*)", q)
    if m:
        try:
            n = int(m.group(2))
            return max(1, n)
        except Exception:
            pass

    # fallback: cari angka kecil pertama di kalimat
    nums = re.findall(r"\b([1-9]\d*)\b", q)
    for s in nums:
        try:
            n = int(s)
            if 1 <= n <= 50:
                return n
        except Exception:
            continue

    return 1


def _extract_compare_ranks(message: str) -> Optional[Tuple[int, int]]:
    """
    Untuk pertanyaan 'apa beda mobil 1 dan 2', dll.
    Ambil dua angka kecil pertama → (1,2).
    """
    nums = []
    for s in re.findall(r"\b([1-9]\d*)\b", message):
        try:
            n = int(s)
            if 1 <= n <= 50:
                nums.append(n)
        except Exception:
            continue
    if len(nums) >= 2:
        return nums[0], nums[1]
    return None


def _get_car_by_rank(rec: Dict[str, Any], rank_req: int) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Ambil mobil berdasarkan rank (1-based).
    Kalau rank di luar range, dipaksa ke 1..len(items).
    """
    items = _get_items(rec)
    if not items:
        return None, 0
    if rank_req < 1:
        rank_req = 1
    if rank_req > len(items):
        rank_req = len(items)
    return items[rank_req - 1], rank_req


def _describe_car_short(car: Dict[str, Any]) -> str:
    brand = str(car.get("brand") or "").title()
    model = str(car.get("model") or "")
    seats = car.get("seats")
    seg = (car.get("segmentasi") or car.get("segment") or "").lower()
    fuel = str(car.get("fuel_label") or car.get("fuel") or "").strip()

    parts = [f"{brand} {model}".strip()]
    if seats:
        parts.append(f"{seats} kursi")
    if seg:
        parts.append(seg)
    if fuel:
        parts.append(f"bahan bakar {fuel}")
    return ", ".join(parts)


def _is_spec_query(q: str) -> bool:
    """
    Deteksi permintaan spek/detail lengkap.
    Contoh:
      - 'spek lengkap mobil nomor 1'
      - 'spesifikasi lengkap mobil 2'
      - 'beri info lengkap tentang mobil nomor 3'
      - 'jelaskan mobil nomor 2'
    """
    if any(k in q for k in ["spek", "spesifikasi", "spesifkasi", "detail lengkap", "info lengkap"]):
        return True
    if "jelaskan" in q and "mobil" in q:
        return True
    return False


# ============================ GEMINI WRAPPER ===========================

def _get_gemini_client():
    if genai is None:
        raise RuntimeError(
            "Library 'google-genai' belum terinstal. "
            "Jalankan: pip install google-genai"
        )
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Environment variable GEMINI_API_KEY belum diset. "
            "Set dulu, misalnya:\n"
            "  export GEMINI_API_KEY='API_KEY_ANDA'"
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def _call_gemini_explain(message: str, rec: Dict[str, Any]) -> str:
    client = _get_gemini_client()
    rec_json = json.dumps(rec, ensure_ascii=False)

    full_prompt = (
        SYSTEM_PROMPT_EXPLAIN.strip()
        + "\n\nDATA REKOMENDASI (JSON):\n"
        + rec_json
        + "\n\nPERTANYAAN PENGGUNA:\n"
        + message
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=full_prompt,
        config=gtypes.GenerateContentConfig(
            max_output_tokens=512,
            temperature=0.4,
        ),
    )

    text = getattr(response, "text", "") or ""
    text = text.strip()
    if not text:
        return "Maaf, aku belum bisa menjawab sekarang."
    return text


# ===================== FALLBACK: SPEK & PENJELASAN =====================

def _format_car_full_spec_for_rank(rec: Dict[str, Any], rank_req: int) -> str:
    items = _get_items(rec)
    if not items:
        return (
            "Belum ada data rekomendasi yang bisa dijelaskan. "
            "Coba jalankan pencarian rekomendasi dulu."
        )

    car, rank = _get_car_by_rank(rec, rank_req)
    if not car:
        return "Tidak ditemukan mobil dengan peringkat yang diminta."

    brand = str(car.get("brand") or "").title()
    model = str(car.get("model") or "")
    price = car.get("price")
    seats = car.get("seats")
    seg = car.get("segmentasi") or car.get("segment") or "-"
    trans = car.get("trans") or "-"
    fuel = car.get("fuel_label") or car.get("fuel") or "-"
    cc = car.get("cc_kwh") or car.get("cc") or car.get("kwh") or None

    awd = car.get("awd_flag")
    drive = None
    for k in ["drive", "drive sys", "drive_sys", "drivetrain"]:
        if isinstance(car.get(k), str) and car[k].strip():
            drive = car[k].strip()
            break

    fit_score = car.get("fit_score")
    need_score = car.get("need_score")
    price_fit = car.get("price_fit")
    pop_z = car.get("popularity_z")
    alasan = car.get("alasan") or ""

    lines: List[str] = []
    lines.append(
        f"Berikut spesifikasi utama mobil peringkat {rank}: {brand} {model}."
    )

    if price is not None:
        lines.append(f"- Harga OTR (perkiraan): {_fmt_rp(price)}")
    if seats:
        lines.append(f"- Kapasitas kursi: {seats} penumpang")
    if seg and seg != "-":
        lines.append(f"- Segmen/jenis bodi: {seg}")
    if trans and trans != "-":
        lines.append(f"- Transmisi: {trans}")
    if fuel and fuel != "-":
        lines.append(f"- Jenis bahan bakar: {fuel}")
    if cc is not None:
        try:
            cc_val = float(cc)
            if cc_val > 0:
                lines.append(f"- Mesin / kapasitas (cc/kWh): ~{int(cc_val)}")
        except Exception:
            pass
    if awd is not None:
        try:
            awd_flag = bool(awd)
            if awd_flag:
                lines.append("- Penggerak: AWD/4x4 (lebih siap jalan licin/offroad)")
        except Exception:
            pass
    elif drive:
        lines.append(f"- Sistem penggerak: {drive}")

    # Skor internal (jika ada)
    score_parts = []
    if fit_score is not None:
        score_parts.append(f"skor kecocokan total ≈ {fit_score:.3f}")
    if need_score is not None:
        score_parts.append(f"skor kecocokan kebutuhan ≈ {need_score:.3f}")
    if price_fit is not None:
        score_parts.append(f"skor kecocokan harga ≈ {price_fit:.3f}")
    if pop_z is not None and pop_z == pop_z:
        score_parts.append(f"indikator popularitas (z-score) ≈ {pop_z:.2f}")

    if score_parts:
        lines.append("Beberapa skor internal sistem rekomendasi:")
        lines.append("- " + "; ".join(score_parts))

    if alasan:
        lines.append("Ringkasan alasan dari mesin rekomendasi:")
        lines.append(f"- {alasan}")

    return "\n".join(lines)


def _fallback_simple_explain(message: str, rec: Dict[str, Any]) -> str:
    """
    Penjelasan singkat 1 mobil (rank bisa 1, 2, 3, ... sesuai pertanyaan).
    Contoh:
      - 'kenapa mobil nomor 2?'
      - 'jelaskan mobil 3'
    """
    items = _get_items(rec)
    if not items:
        return (
            "Belum ada data rekomendasi yang bisa dijelaskan. "
            "Coba jalankan pencarian rekomendasi dulu."
        )

    rank_req = _extract_rank_from_message(message)
    car, rank = _get_car_by_rank(rec, rank_req)
    if not car:
        return (
            "Tidak ditemukan mobil dengan peringkat yang diminta. "
            "Coba cek lagi nomor peringkatnya."
        )

    brand = str(car.get("brand") or "").title()
    model = str(car.get("model") or "")
    price = car.get("price")
    seats = car.get("seats")
    fuel = car.get("fuel_label") or car.get("fuel")
    needs = rec.get("needs") or []
    alasan = car.get("alasan") or ""

    parts: List[str] = []
    parts.append(f"Secara sederhana, mobil peringkat {rank} adalah {brand} {model}.")

    if price is not None:
        try:
            parts.append(f"Harganya sekitar {_fmt_rp(price)}.")
        except Exception:
            pass
    if seats:
        parts.append(f"Mobil ini punya sekitar {seats} kursi.")
    if fuel:
        parts.append(f"Menggunakan jenis bahan bakar {fuel}.")
    if needs:
        parts.append(
            "Mobil ini diprioritaskan karena cocok dengan kebutuhan: "
            + ", ".join(needs)
            + "."
        )
    if alasan:
        parts.append(f"Alasan ringkas dari mesin: {alasan}.")

    return " ".join(parts)


def _fallback_compare_two(rec: Dict[str, Any], r1: int, r2: int) -> str:
    """
    Perbandingan singkat dua mobil (misal rank 1 dan 2).
    """
    items = _get_items(rec)
    if len(items) < 2:
        return (
            "Di sistem saat ini belum ada cukup mobil untuk dibandingkan "
            f"(jumlah mobil hanya {len(items)})."
        )

    car1, rank1 = _get_car_by_rank(rec, r1)
    car2, rank2 = _get_car_by_rank(rec, r2)
    if not car1 or not car2:
        return "Tidak bisa menemukan dua mobil dengan peringkat yang diminta."

    desc1 = _describe_car_short(car1)
    desc2 = _describe_car_short(car2)

    seats1 = car1.get("seats")
    seats2 = car2.get("seats")
    seg1 = (car1.get("segmentasi") or car1.get("segment") or "").lower()
    seg2 = (car2.get("segmentasi") or car2.get("segment") or "").lower()
    fuel1 = str(car1.get("fuel_label") or car1.get("fuel") or "").strip()
    fuel2 = str(car2.get("fuel_label") or car2.get("fuel") or "").strip()
    trans1 = car1.get("trans")
    trans2 = car2.get("trans")

    lines: List[str] = []
    lines.append(
        f"Secara garis besar, mobil peringkat {rank1} adalah {desc1}, "
        f"sedangkan peringkat {rank2} adalah {desc2}."
    )

    # Highlight perbedaan penting
    diff_parts = []
    if seats1 and seats2 and seats1 != seats2:
        diff_parts.append(f"kapasitas kursi {seats1} vs {seats2}")
    if seg1 and seg2 and seg1 != seg2:
        diff_parts.append(f"segmen bodi {seg1} vs {seg2}")
    if fuel1 and fuel2 and fuel1 != fuel2:
        diff_parts.append(f"jenis BBM {fuel1} vs {fuel2}")
    if trans1 and trans2 and trans1 != trans2:
        diff_parts.append(f"transmisi {trans1} vs {trans2}")

    if diff_parts:
        lines.append(
            "Perbedaan yang cukup terasa antara keduanya: "
            + "; ".join(diff_parts)
            + "."
        )
    else:
        lines.append(
            "Secara spesifikasi dasar, keduanya cukup mirip; perbedaan utama biasanya ada "
            "pada detail fitur, rasa berkendara, dan preferensi pribadi."
        )

    return " ".join(lines)


# =============================== ENTRYPOINT ============================

def build_explanation_reply(message: str, rec: Dict[str, Any]) -> ChatReply:
    """
    Dipakai kalau intent-nya penjelasan rekomendasi (eks chatbot 2).
    - Bisa menjawab:
      * 'Kenapa mobil nomor 1?'
      * 'Apa beda mobil nomor 1 dan 2?'
      * 'Berikan spek lengkap mobil rank 2'
      * 'Jelaskan mobil nomor 3'
    """
    q = (message or "").lower()
    items = _get_items(rec)
    if not items:
        return ChatReply(
            reply=(
                "Belum ada data rekomendasi yang bisa dijelaskan. "
                "Coba jalankan pencarian rekomendasi dulu."
            ),
            suggested_questions=[
                "Bantu rekomendasikan mobil dulu dong?",
            ],
        )

    # 1) Kalau ada kata 'beda/perbedaan/banding/vs' → bandingkan 2 mobil
    if any(k in q for k in ["beda", "perbedaan", "banding", " vs "]):
        ranks = _extract_compare_ranks(message) or (1, 2)
        reply = _fallback_compare_two(rec, ranks[0], ranks[1])
        return ChatReply(
            reply=reply,
            suggested_questions=[
                "Berikan spek lengkap mobil peringkat 1.",
                "Berikan spek lengkap mobil peringkat 2.",
            ],
        )

    # 2) Kalau terlihat sebagai permintaan spek/detail lengkap → formatter deterministik
    if _is_spec_query(q):
        rank_req = _extract_rank_from_message(message)
        reply = _format_car_full_spec_for_rank(rec, rank_req)
        return ChatReply(
            reply=reply,
            suggested_questions=[
                "Apa beda mobil peringkat 1 dan 2?",
                "Kenapa mobil peringkat 1 yang dipilih untuk saya?",
            ],
        )

    # 3) Selain itu: pakai Gemini kalau ada, fallback → penjelasan singkat (rank bisa 1/2/3…)
    if genai is None or not GEMINI_API_KEY:
        reply = _fallback_simple_explain(message, rec)
        return ChatReply(
            reply=reply,
            suggested_questions=[
                "Apa beda mobil nomor 1 dan 2?",
                "Kalau fokus keluarga saja, mana yang lebih cocok?",
            ],
        )

    try:
        answer = _call_gemini_explain(message, rec)
    except Exception as e:
        answer = (
            "Lagi ada kendala saat memanggil model bahasa (Gemini): "
            f"{e}\n\nUntuk sementara aku jelaskan singkat pakai data mentah."
        )
        return ChatReply(
            reply=answer,
            suggested_questions=[
                "Apa beda mobil nomor 1 dan 2?",
                "Kalau fokus keluarga saja, mana yang lebih cocok?",
            ],
        )

    return ChatReply(
        reply=answer,
        suggested_questions=[
            "Apa kelebihan mobil nomor 1 dibanding nomor 2?",
            "Kalau fokus keluarga saja, mana yang lebih cocok?",
        ],
    )
