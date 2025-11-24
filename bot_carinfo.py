# file: bot_carinfo.py
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from chat_schemas import ChatReply
from recommendation_state import get_last_recommendation
from loaders import load_specs

# Gemini (opsional)
try:
    from google import genai
    from google.genai import types as gtypes
except ImportError:
    genai = None
    gtypes = None


SYSTEM_PROMPT_CARINFO = """
Kamu adalah asisten spesifikasi mobil untuk pasar Indonesia.

Kamu akan diberi satu objek JSON bernama car_internal dari sistem internal pengguna.
Field-field di dalam car_internal berasal dari dataset internal dan HARUS menjadi acuan utama
untuk angka teknis.

ATURAN PENTING (WAJIB):
- Jika suatu field di car_internal TIDAK kosong (misalnya: price, cc_kwh, fuel, seats,
  doors, trans, drive_sys, segmentasi), JANGAN mengubah nilainya di jawaban.
- Jangan menambah varian mesin atau konfigurasi lain yang bertentangan dengan car_internal.
  Contoh:
  - Jika fuel = "Diesel", jangan bilang "tersedia bensin atau diesel".
  - Jika seats = 7, jangan bilang 8 kursi.
  - Jika trans = "AT", jangan bilang ada MT kecuali kamu jelaskan itu varian lain di negara lain.
- Kamu boleh menambah spesifikasi tambahan (tenaga, torsi, fitur kenyamanan, fitur keselamatan)
  berdasarkan pengetahuanmu, tapi jangan bertentangan dengan jenis BBM, kursi/pintu, transmisi,
  atau sistem penggerak di car_internal.

GAYA JAWABAN:
- Bahasa Indonesia, 1–3 paragraf, bukan bullet point super panjang.
- Paragraf 1:
  - Sebutkan nama lengkap mobil (brand + type_model kalau ada).
  - Ringkas spesifikasi inti: segmen bodi, jumlah kursi & pintu, jenis BBM, kapasitas mesin/baterai,
    sistem penggerak, jenis transmisi, dan kisaran harga (pakai angka di car_internal).
- Paragraf 2 (opsional):
  - Tambahkan gambaran karakter mobil: lebih ke keluarga, fun-to-drive, offroad, dll.
  - Boleh sebut fitur safety/kenyamanan umum (contoh: airbag, ESC, ADAS) tanpa harus sangat spesifik.
- Paragraf 3 (opsional, singkat):
  - Beri disclaimer bahwa data utama diambil dari dataset internal pengguna dan tetap
    perlu dicek lagi ke brosur/website resmi untuk keputusan beli nyata.

Jika informasi tertentu tidak ada di car_internal dan kamu tidak yakin, gunakan kata-kata seperti
"sekitar", "kurang lebih", atau "umumnya", dan jangan terkesan terlalu pasti.
"""


def _get_gemini_client():
    """Inisialisasi client Gemini dari environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if genai is None:
        raise RuntimeError("Library 'google-genai' belum terinstal.")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY belum diset di environment.")
    return genai.Client(api_key=api_key)


def _normalize(s: Any) -> str:
    return str(s or "").strip()


def _norm_lower(s: Any) -> str:
    return _normalize(s).lower()


# ================== AMBIL MOBIL DARI LAST_RECOMMENDATION ==================

def _extract_rank_from_message(q: str) -> Optional[int]:
    """
    Cari pola 'rank 1', 'peringkat 2', 'mobil 3', 'no 4', dsb.
    Return rank (1-based) atau None.
    """
    m = re.search(r"(mobil|no|nomor|peringkat|rank)\s*([0-9]+)", q)
    if not m:
        return None
    try:
        k = int(m.group(2))
        return k if k >= 1 else None
    except Exception:
        return None


def _pick_car_from_last_recommendation(message: str) -> Optional[Dict[str, Any]]:
    rec = get_last_recommendation()
    if not rec or not rec.get("items"):
        return None

    items: List[Dict[str, Any]] = rec["items"]

    q = message.lower()

    # 1) Jika ada penyebutan rank eksplisit
    r = _extract_rank_from_message(q)
    if r is not None and 1 <= r <= len(items):
        return items[r - 1]

    # 2) Kalau tidak, coba cocokkan brand/model di teks
    best = None
    best_score = 0
    for it in items:
        brand = _norm_lower(it.get("brand"))
        model = _norm_lower(it.get("model") or it.get("type model") or it.get("type_model"))
        key = f"{brand} {model}".strip()
        if not key:
            continue

        score = 0
        for token in key.split():
            if token and token in q:
                score += 1

        if score > best_score:
            best_score = score
            best = it

    return best


# ======================== AMBIL MOBIL DARI load_specs =====================

def _load_specs_cached() -> pd.DataFrame:
    """Wrapper kecil kalau nanti mau dikasih cache."""
    return load_specs()


def _pick_car_from_specs(message: str) -> Optional[Dict[str, Any]]:
    """
    Cari mobil di daftar spesifikasi (daftar_mobil.json / load_specs) berdasarkan teks.
    Fokus ke kombinasi brand + 'type model' (atau 'model').
    """
    q = message.lower()
    df = _load_specs_cached()
    if df is None or df.empty:
        return None

    # Siapkan kolom yang sering dipakai
    cols = {c.lower(): c for c in df.columns}
    col_brand = cols.get("brand")
    col_type_model = cols.get("type model") or cols.get("type_model")
    col_model = cols.get("model")

    if not col_brand or not (col_type_model or col_model):
        return None

    best_idx: Optional[int] = None
    best_score = 0

    for idx, row in df.iterrows():
        brand = _norm_lower(row.get(col_brand))
        tm = _norm_lower(row.get(col_type_model)) if col_type_model else ""
        md = _norm_lower(row.get(col_model)) if col_model else ""
        key = " ".join([brand, tm or md]).strip()
        if not key:
            continue

        score = 0
        # Tokenisasi kasar dari key
        for token in key.split():
            if token and token in q:
                score += 1

        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx is None or best_score == 0:
        return None

    row = df.loc[best_idx]
    # Ubah ke dict biasa
    safe = row.replace([np.nan, np.inf, -np.inf], None)
    return safe.to_dict()


# ====================== BANGUN car_internal UNTUK PROMPT ===================

def _build_car_internal(
    src: Dict[str, Any],
    source_label: str = "unknown",
) -> Dict[str, Any]:
    """
    Ambil field penting dari dict (baik dari LAST_RECOMMENDATION maupun specs)
    dan normalisasikan ke struktur yang lebih rapi untuk dikirim ke Gemini.
    """
    d: Dict[str, Any] = {}

    # Nama & identitas
    d["source"] = source_label
    d["brand"] = _normalize(src.get("brand"))
    d["model"] = _normalize(src.get("model"))
    d["type_model"] = _normalize(
        src.get("type model") or src.get("type_model") or src.get("model")
    )

    # Harga
    for key in ["harga otr (idr)", "harga otr", "price"]:
        if key in src and src.get(key) not in [None, "", "NA", "NaN"]:
            try:
                d["price"] = float(str(src.get(key)).replace(".", "").replace(",", ""))
            except Exception:
                d["price"] = src.get(key)
            break

    # Kursi & pintu
    d["seats"] = src.get("seats") or src.get("seat")
    d["doors"] = src.get("DOOR") or src.get("door")

    # Bahan bakar
    d["fuel"] = _normalize(src.get("fuel"))
    d["segmentasi"] = _normalize(src.get("segmentasi") or src.get("segment"))

    # Transmisi
    d["trans"] = _normalize(src.get("trans") or src.get("transmisi") or src.get("transmission"))

    # Mesin / baterai
    d["cc_kwh"] = src.get("cc / kwh") or src.get("cc_kwh") or src.get("cc") or src.get("kwh")

    # Sistem penggerak
    d["drive_sys"] = _normalize(
        src.get("drive sys") or src.get("drive_sys") or src.get("drivetrain")
    )

    # Dimensi & berat (kalau ada)
    d["dimension_raw"] = _normalize(src.get("DIMENSION P x L xT") or src.get("dimension"))
    d["vehicle_weight"] = src.get("vehicle_weight") or src.get("weight")

    # Tenaga (ps/hp) jika ada
    d["ps_hp"] = _normalize(src.get("PS / HP") or src.get("ps_hp") or src.get("power"))

    return d


# ========================= PANGGIL GEMINI UNTUK SPEK ======================

def _call_gemini_carinfo(message: str, car_internal: Dict[str, Any]) -> str:
    client = _get_gemini_client()
    car_json = json.dumps(car_internal, ensure_ascii=False)

    full_prompt = (
        SYSTEM_PROMPT_CARINFO.strip()
        + "\n\nDATA_INTERNAL MOBIL (car_internal, JSON):\n"
        + car_json
        + "\n\nPERTANYAAN PENGGUNA:\n"
        + message
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=full_prompt,
        config=gtypes.GenerateContentConfig(
            max_output_tokens=640,
            temperature=0.4,
        ),
    )
    text = getattr(response, "text", "") or ""
    text = text.strip()
    if not text:
        return (
            "Maaf, aku belum bisa mengambil spesifikasi lengkap mobil ini sekarang. "
            "Coba lagi beberapa saat lagi atau cek brosur resmi."
        )
    return text


# =========================== FALLBACK TANPA GEMINI ========================

def _fallback_carinfo(car_internal: Dict[str, Any]) -> str:
    """
    Kalau Gemini error / tidak aktif, kasih jawaban deterministik
    berdasarkan data internal saja.
    """
    brand = car_internal.get("brand") or ""
    type_model = car_internal.get("type_model") or car_internal.get("model") or ""
    name = (str(brand).strip() + " " + str(type_model).strip()).strip()

    price = car_internal.get("price")
    seg = car_internal.get("segmentasi") or ""
    seats = car_internal.get("seats")
    doors = car_internal.get("doors")
    fuel = car_internal.get("fuel") or ""
    trans = car_internal.get("trans") or ""
    cc_kwh = car_internal.get("cc_kwh")
    drive_sys = car_internal.get("drive_sys") or ""

    def fmt_rp(v: Any) -> str:
        try:
            return "Rp{:,.0f}".format(float(v)).replace(",", ".")
        except Exception:
            return "-"

    parts: List[str] = []
    if name:
        parts.append(f"Berikut ringkasan spesifikasi dari dataset internal untuk {name}.")

    if price:
        parts.append(f"Harga OTR (perkiraan) sekitar {fmt_rp(price)}.")
    if seg:
        parts.append(f"Masuk segmen/jenis bodi {seg.lower()}.")
    if seats:
        parts.append(f"Kapasitas sekitar {seats} penumpang.")
    if doors:
        parts.append(f"Jumlah pintu sekitar {doors}.")
    if fuel:
        parts.append(f"Jenis bahan bakar: {fuel}.")
    if cc_kwh:
        parts.append(f"Kapasitas mesin/baterai (cc/kWh) sekitar {cc_kwh}.")
    if trans:
        parts.append(f"Transmisi: {trans}.")
    if drive_sys:
        parts.append(f"Sistem penggerak: {drive_sys}.")

    parts.append(
        "Detail lain seperti tenaga, torsi, dan fitur bisa berbeda tergantung tahun dan trim. "
        "Data ini murni dari dataset internal dan sebaiknya tetap dicek ke brosur / website resmi "
        "untuk keputusan pembelian."
    )

    return " ".join(parts)


# ============================= API UTAMA BOT 4 ===========================

def build_carinfo_reply(message: str) -> ChatReply:
    """
    Chatbot 4 — Info / spek mobil.

    Alur:
    1) Coba cari mobil dari LAST_RECOMMENDATION (rank / nama).
    2) Kalau gagal, cari di load_specs() berdasarkan brand + type model / model.
    3) Bangun car_internal dari dict hasil.
    4) Coba panggil Gemini dengan SYSTEM_PROMPT_CARINFO + car_internal.
       Jika gagal (API error) → fallback ke _fallback_carinfo().
    """
    msg = (message or "").strip()
    q = msg.lower()

    # 1) Dari hasil rekomendasi terakhir (kalau ada)
    car_dict = _pick_car_from_last_recommendation(q)
    source_label = "last_recommendation"

    # 2) Kalau belum ketemu, coba dari specs
    if car_dict is None:
        car_dict = _pick_car_from_specs(q)
        source_label = "specs"

    if car_dict is None:
        # Tidak ketemu sama sekali → jawaban jujur
        return ChatReply(
            reply=(
                "Aku belum bisa memastikan mobil mana yang kamu maksud dari data di sistem.\n"
                "Coba tuliskan nama mobil lebih lengkap, misalnya:\n"
                "- 'spek lengkap Hyundai Palisade 2.2 CRDi Signature'\n"
                "- 'spesifikasi lengkap Subaru BRZ 2.4 AT ES ZD8'\n"
                "atau jalankan rekomendasi dulu lalu tanya 'spek lengkap mobil nomor 1'."
            ),
            suggested_questions=[
                "Spek lengkap Hyundai Palisade 2.2 CRDi Signature.",
                "Spek lengkap Subaru BRZ 2.4 AT ES ZD8.",
                "Spek lengkap mobil nomor 1.",
            ],
        )

    # 3) Bangun car_internal
    car_internal = _build_car_internal(car_dict, source_label=source_label)

    # 4) Coba pakai Gemini dulu
    try:
        answer = _call_gemini_carinfo(msg, car_internal)
    except Exception:
        # Jangan bocorkan error teknis ke user
        answer = _fallback_carinfo(car_internal)

    return ChatReply(
        reply=answer,
        suggested_questions=[
            "Spek lengkap mobil nomor 1.",
            "Apa beda mobil nomor 1 dan 2?",
        ],
    )
