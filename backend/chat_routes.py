# file: backend/chat_routes.py
from __future__ import annotations
import os
import json
import math
import re
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Body
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

from .spk import rank_candidates
from .data_loader import get_master_data
from .common_utils import attach_images, df_to_items, FUEL_LABEL_MAP
from .recommendation_state import set_last_recommendation, get_last_recommendation
from .spk_utils import fuel_to_code, NEED_LABELS

load_dotenv()

router = APIRouter()

# ====================================================================
# KONFIGURASI OLLAMA (LOCAL)
# ====================================================================
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

MODEL_NAME = "llama3.1"

# ====================================================================
# SYSTEM PROMPTS (RESTORED FINE-TUNED NLU)
# ====================================================================
SYSTEM_PROMPT_NLU = """
Anda adalah NLU extractor untuk sistem rekomendasi mobil bernama "VRoom".
TUGAS UTAMA:
- Dari satu string user, ekstrak secara deterministik ke JSON sesuai skema yang diberikan.
- Output harus murni JSON (tanpa teks tambahan). Jika perlu konteks atau klarifikasi, set fields yang relevan dan tambahkan confidence rendah serta parse_warnings — jangan keluarkan narasi.

PRINSIP UMUM:
- Bersikap deterministik dan konservatif: bila ragu, isi dengan null / [] dan sertakan parse_warnings.
- Hati-hati terhadap topik non-otomotif: jika mayoritas isi pesan bukan otomotif, keluarkan intent "OFF_TOPIC" (lihat aturan OFF_TOPIC).
- Kembalikan juga "confidence" float 0.0–1.0 (interpretasi: >0.85 sangat yakin; 0.6–0.85 agak yakin; <0.6 ragu).
- Sertakan "parse_warnings": list string yang menjelaskan masalah parsing (mis. "budget_ambiguous", "needs_conflict", "needs_ambiguous", "budget_lower_bound", "possible_offtopic").

WAJIB — SKEMA JSON (OUTPUT)
{
  "intent": "SEARCH" | "OFF_TOPIC" | "ANALYZE" | "OTHER",
  "budget": int | null,                // dalam Rupiah penuh (contoh: 400000000)
  "needs": [string],                   // list label: keluarga, perjalanan_jauh, fun, perkotaan, offroad, niaga
  "filters": {
     "trans_choice": "matic"|"manual"|null,
     "brand": string|null,
     "fuels": [ "g"|"d"|"h"|"p"|"e" ]|null
  },
  "is_complete": boolean,
  "confidence": float,
  "parse_warnings": [string]
}

RULES PENTING (behavioural)
1. OFF_TOPIC:
   - Jika pesan membahas politik, kesehatan medis yang butuh saran dokter, ekonomi personal (diluar beli mobil), barang lain non-otomotif, instruksi ilegal, atau sangat generik tanpa konteks otomotif -> return:
     {"intent":"OFF_TOPIC","reply":"Maaf, saya hanya bisa membantu rekomendasi mobil."}
   - Untuk OFF_TOPIC juga isi confidence>=0.9.

2. INTENT ANALYZE:
   - Jika user meminta "kenapa X peringkat rendah", "analisis perbandingan", "jelaskan keunggulan", set intent="ANALYZE" dan jangan isi budget/needs kecuali disebut eksplisit.

3. BUDGET PARSING:
   - anggaran,memiliki dana,biaya,mau beli mobil dengan harga akan di anggap sebagai indikasi budget.
   - Tangani format: "400jt","400 juta","400-an","400000000","0.4M","400k","sekitar 400jt","maks 400jt","antara 300-400jt".
   - Jika rentang disebut, ambil Batas ATAS sebagai budget. (ex: "300-400jt" -> 400000000)
   - Normalisasi: hapus simbol, titik/komma sebagai pemisah ribuan.
   - Jika ada kata "lebih dari" -> treat as lower bound -> set budget = that value and add parse_warnings="budget_lower_bound".
   - Jika sangat ambigu (mis: "ada budget?") set budget=null, is_complete=False, confidence<0.6, parse_warnings contain "budget_missing".

4. NEEDS (multi-label rules):
   - Catat kebutuhan eksplisit + mapping implisit (lihat "mapping implisit" di bawah).
   - Jangan menambah kebutuhan yang tidak relevan; bila frasa ambigu sertakan parse_warnings "needs_ambiguous".
   - Jika user menyebut banyak frasa, masukkan semuanya kecuali bila ada konflik eksplisit (lihat aturan konflik di bawah).
   - Jika user menyebut "berlibur" atau sinonimnya (liburan, holiday, jalan-jalan untuk rekreasi) -> map ke "perjalanan_jauh".
   - Jika user menyebut "keluarga kecil" -> map ke "keluarga" dan catat constraint kapasitas: keluarga kecil berarti preferensi kendaraan yang dapat menampung minimal 5 orang (rekomendasikan/flag seat_count >=5 pada downstream; di NLU sertakan parse_warnings "keluarga_kecil_requires_5plus" bila perlu).
   - Jika ada kombinasi kebutuhan yang saling bertentangan, jangan keluarkan keduanya tanpa flag:
       * offroad dan fun tidak boleh dipilih bersamaan.
       * fun dan niaga tidak boleh dipilih bersamaan.
       * perjalanan_jauh (long) dan perkotaan pendek/short (short) tidak boleh dipilih bersama.
     Bila user menyebut kebutuhan bertentangan, pilih kebutuhan yang paling eksplisit/terakhir disebut (deterministik) **dan** tambahkan parse_warnings "needs_conflict" serta turunkan confidence sesuai ambiguitas. Jika tidak bisa menentukan preferensi, keluarkan [] atau pilih null dan set is_complete=False dengan parse_warnings "needs_conflict_unresolved".

5. FUEL MAPPING:
   - Normalize kata ke kode: bensin->"g", diesel->"d", hybrid->"h", phev/plugin->"p", listrik/ev/bev->"e".
   - Jika tidak ada fuel disebut, set fuels=null.

6. TRANSMISI:
   - "matic"/"otomatis" -> "matic"; "manual"/"mt" -> "manual"; bila tidak disebut -> null.

7. is_complete:
   - True jika paling tidak budget OR satu needs valid tersedia dan intent == "SEARCH".
   - False jika kedua-duanya hilang atau parsing gagal.

8. CONFIDENCE:
   - Hitung berdasarkan seberapa eksplisit fields diisi (budget explicit + needs explicit + brand explicit = confidence tinggi).
   - Jika confidence < 0.6, tambahkan parse_warnings "low_confidence".

9. OUTPUT FORMAT:
   - Output JSON harus valid, tanpa komentar atau kata ekstra.
   - Jika OFF_TOPIC, output field "reply" boleh disertakan (seperti contoh OFF_TOPIC di atas).

10. KONFLIK KEBUTUHAN (aturan khusus — harus ditegakkan):
    - Pastikan aturan mutual-exclusion diaplikasikan sebelum finalisasi needs. Jika terdeteksi kontradiksi, ikuti prosedur pada poin 4.
    - Untuk istilah "long" vs "short": normalnya "perjalanan_jauh" (long) dan "short" (singkat/perkotaan) dianggap bertentangan — tidak boleh bersama.

MAPPING IMPLISIT (RULES yang sering terlewat LLM — terapkan prioritas):
- "antar jemput anak" / "antar anak sekolah" -> ["keluarga","perkotaan"]
- "buat istri kerja" / "istri ke kantor" -> ["perkotaan"]
- "mudik sekeluarga" / "pulang kampung bawa keluarga" -> ["perjalanan_jauh","keluarga"]
- "sering ke luar kota" / "road trip" -> ["perjalanan_jauh"]
- "parkiran sempit" / "komplek perumahan" -> ["perkotaan"]
- "bawa barang dagangan" / "jualan" -> ["niaga"]
- "jalan desa jelek / tanjakan" -> ["offroad"]
- "berlibur" / "liburan" / "jalan-jalan rekreasi" -> ["perjalanan_jauh"]
- "keluarga kecil" -> ["keluarga"] (catat preferensi kapasitas >=5 orang; tambahkan parse_warnings "keluarga_kecil_requires_5plus" bila perlu)

ROBUSTNESS (typo / campur bahasa / noise)
- Toleran pada campur bahasa (id/en), typo, penulisan singkatan (jt/juta, m/ milyar).
- Jika kalimat penuh noise dan hanya mengandung satu kata kunci jelas -> gunakan yang jelas tapi sertakan parse_warnings.
- Jika format "40-an" → ubah jadi 400000000
- Jika format "400-an" → ubah jadi 400000000
- Jika format "440-an" → ubah jadi 440000000

EXAMPLES (beberapa contoh output yang valid)
Input: "Cari mobil untuk antar jemput anak dan belanja, budget 400jt"
Output:
{
  "intent":"SEARCH",
  "budget":400000000,
  "needs":["keluarga","perkotaan"],
  "filters":{"trans_choice":null,"brand":null,"fuels":null},
  "is_complete":true,
  "confidence":0.92,
  "parse_warnings":[]
}

Input: "Mau rekomendasi mobil bagus"
Output (tidak lengkap):
{
  "intent":"SEARCH",
  "budget":null,
  "needs":[],
  "filters":{"trans_choice":null,"brand":null,"fuels":null},
  "is_complete":false,
  "confidence":0.2,
  "parse_warnings":["budget_missing","needs_missing"]
}

Input (kontradiksi): "Butuh mobil fun dan juga buat jualan"
Possible output (konflik, pilih deterministik salah satu atau kosong):
{
  "intent":"SEARCH",
  "budget":null,
  "needs":["fun"],              // atau [], tergantung determinisme; wajib tambahkan parse_warnings
  "filters":{"trans_choice":null,"brand":null,"fuels":null},
  "is_complete":false,
  "confidence":0.45,
  "parse_warnings":["needs_conflict","fun_and_niaga_conflict"]
}

Input (off-topic): "Siapa calon presiden tahun depan?"
Output:
{"intent":"OFF_TOPIC","reply":"Maaf, saya hanya bisa membantu rekomendasi mobil.","budget":null,"needs":[],"filters":null,"is_complete":false,"confidence":0.95,"parse_warnings":["off_topic"]}

IMPLEMENTATION NOTES (saran agar LLM konsisten)
- Gunakan temperature rendah (0.0–0.2) saat memanggil model untuk determinisme.
- Beri instruction reinforcement: “OUTPUT ONLY JSON. NO TEXT.”
- Tambahkan 8–20 contoh (few-shot) di prompt kalau model masih keliru.

TAMBAHAN (opsional tapi direkomendasikan)
- Sertakan field "raw_budget_text" yang isinya potongan string budget asli bila ingin audit (tidak wajib).
"""
# ====================================================================
# SYSTEM PROMPT ANALYST


SYSTEM_PROMPT_ANALYST = """
Anda adalah Konsultan Otomotif VRoom yang cerdas dan adaptif.
Tugas Anda: Memberikan analisis perbandingan mobil yang SANGAT SPESIFIK dan ringkas terhadap KEBUTUHAN USER.

GUARDRAILS:
Jika pertanyaan user OOT, tolak dengan sopan.

ATURAN KERAS (ANTI-HALUSINASI):
1. JANGAN PERNAH menyebut fitur spesifik (Sunroof, ADAS, Captain Seat) KECUALI ada di DATA SPEK (6 seater adalah captain seat).
2. Gunakan logika turunan:
   - Wheelbase panjang -> Kabin lega / Stabil.
   - RWD -> Kuat tanjakan.
   - FWD -> Efisien.
   - Diesel/Turbo -> Torsi besar.
   - ev/hybrid/phev -> torsi instan.

INPUT ANDA:
1. Data Mobil Terpilih vs Pembanding (semua yang ada direkomendasi lalu bandingkan dengan  ranking lebih rendah atau lebih tinggi,sebutkan mobil yang dibandingkan). (contoh yang dipilih user rank 4, bandingkan dengan rank 1,2,3,5,6.)
2. CONTEXT USER (Budget & Kebutuhan).

LOGIKA ADAPTASI:
- "OFFROAD": Bahas Ground Clearance & Penggerak.
- "KELUARGA": Bahas Kursi & Ruang.
- "PERJALANAN JAUH": Bahas Kestabilan & Mesin Diesel.
- "FUN": Bahas Tenaga & Handling.
- "IRIT/KOTA": Bahas Dimensi & Konsumsi BBM.

INSTRUKSI JAWABAN:
1. JANGAN ULANGI DATA MENTAH DAN JANGAN MENYEBUTKAN SKOR.
2. Gunakan bahasa natural & ringkas (Maks 1 paragraf).
3. Jika User klik Rank Bawah: Jelaskan kenapa dia kalah (harga/skor), TAPI angkat keunggulan uniknya.
4. Jika User klik Rank Atas: Jelaskan kenapa dia unggul (harga/skor), TAPI sebutkan kekurangannya juga.
5. Tampilkan perbandingan yang paling relevan dengan kebutuhan user.
6. Jika tidak ada perbedaan signifikan, katakan "Kedua mobil ini cukup seimbang dalam hal [fitur]."
7. Jika ada fitur unik yang menonjol pada salah satu mobil, sorot itu dalam analisis Anda.
8. Akhiri dengan rekomendasi singkat: "Berdasarkan analisis ini, saya merekomendasikan [Mobil X] karena [alasan singkat]."
9. JANGAN SEBUTKAN BAHWA ANDA ADALAH AI MODEL.
10. JANGAN SEBUTKAN BAHWA ANDA TIDAK MEMILIKI DATA CUKUP.

"""

# ====================================================================
# MODELS & UTIL
# ====================================================================

class ChatMessage(BaseModel):
    message: str

class ImageAnalysisRequest(BaseModel):
    image_url: str
    prompt: Optional[str] = "Mobil apakah ini? Jelaskan spesifikasinya singkat."

def clean_json_string(s: str) -> str:
    s = s.strip()
    if "```json" in s:
        s = s.split("```json")[1].split("```")[0]
    elif "```" in s:
        s = s.split("```")[1].split("```")[0]
    return s.strip()

def sanitize_for_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data): return None
        return data
    elif hasattr(data, "item"):
        val = data.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)): return None
        return val
    else:
        return data

def build_summary_text(rec_list: List[Dict[str, Any]]) -> str:
    summary_text = ""
    for i, car in enumerate(rec_list[:5]):
        brand = car.get('brand', 'Unknown')
        model = car.get('model', 'Unknown')
        price = car.get('price', 0)
        price_str = f"{price:,}" if isinstance(price, (int, float)) and price is not None else str(price)
        summary_text += f"Rank {i+1}. {brand} {model} (Rp {price_str}).\n"
    return summary_text

NON_AUTO_SIGNAL = [
    "politik", "presiden", "pilkada", "agama", "islam", "kristen", "kesehatan", "obat",
    "resep", "dokter", "rumah sakit", "investasi", "saham", "kripto", "harga emas", "gaji",
    "hukum", "peraturan", "perpajakan", "lowongan kerja", "loker"
]

def quick_offtopic_check(text: str) -> bool:
    t = text.lower()
    for kw in NON_AUTO_SIGNAL:
        if kw in t:
            return True
    return False

OOT_REPLY = "Maaf, saya tidak bisa menjawab itu karena saya adalah asisten rekomendasi mobil VRoom yang hanya fokus membantu topik otomotif."

# ====================================================================
# NORMALISASI BUDGET
# ====================================================================
def normalize_budget_string(budget_str: str) -> Optional[float]:
    """
    Mengubah string budget variasi seperti:
    '600jt', '600jt-an', '1,2M', '1.2 M', '700 juta' dll
    menjadi angka float dalam juta
    """
    s = budget_str.lower().replace(" ", "").replace(".", "").replace(",", ".")
    # regex perbaikan, menangani "jt", "juta", "m", termasuk "-an"
    match = re.search(r"(\d+(?:\.\d+)?)(jt|juta|m)?(?:-an)?", s)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return number * 1000  # juta
    return number  # jt atau "juta"

def extract_budget_fallback(text: str) -> Optional[float]:
    """
    Fallback parsing langsung dari user_text jika NLU gagal
    """
    match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(jt|juta|m)", text.lower())
    if match:
        num = float(match.group(1).replace(",", "."))
        unit = match.group(2)
        if unit == "m":
            num *= 1000
        return num
    return None

# ====================================================================
# ENDPOINT CHAT UTAMA
# ====================================================================
@router.post("/chat")
async def chat_endpoint(payload: ChatMessage = Body(...)):
    user_text = (payload.message or "").strip()
    print(f"[CHAT] User text: {user_text}")

    if not user_text:
        return {"reply": "Teks kosong. Silakan masukkan permintaan Anda.", "recommendation": None}

    if quick_offtopic_check(user_text):
        return {"reply": OOT_REPLY, "recommendation": None}

    df = get_master_data()
    if df.empty:
        return {"reply": "Maaf, database mobil kosong.", "recommendation": None}

    # DETEKSI ANALYZE PRA-NLU
    ANALYZE_KEYWORDS = ["analisis", "jelaskan", "kenapa", "mengapa", "ranking", "peringkat"]
    last_rec_payload = get_last_recommendation()
    is_analysis_query = any(kw in user_text.lower() for kw in ANALYZE_KEYWORDS)

    if is_analysis_query and last_rec_payload and last_rec_payload.get("count", 0) > 0:
        summary = build_summary_text(last_rec_payload['items'])
        try:
            nlg_completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYST},
                    {"role": "user", "content": f"Context:\n{summary}\n\nUser asks: {user_text}"}
                ],
                temperature=0.7,
            )
            reply_text = nlg_completion.choices[0].message.content
            return sanitize_for_json({
                "reply": reply_text,
                "parsed_constraints": None,
                "recommendation": last_rec_payload
            })
        except Exception:
            return {"reply": "Terjadi kesalahan saat membuat analisis.", "recommendation": None}

    # PANGGIL NLU
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": SYSTEM_PROMPT_NLU}, {"role": "user", "content": user_text}],
            temperature=0.0,
        )
        raw_content = completion.choices[0].message.content
        cleaned_json = clean_json_string(raw_content)
        params = json.loads(cleaned_json)
    except Exception:
        return {"reply": "Maaf, saya kurang paham. Bisa ulangi dengan format: 'Cari mobil [kebutuhan] budget [angka]'", "recommendation": None}

    if not isinstance(params, dict):
        return {"reply": "Maaf, ekstraksi parameter gagal. Bisa ulangi dengan kalimat yang lebih sederhana?", "recommendation": None}

    if params.get("intent") == "OFF_TOPIC":
        return {"reply": OOT_REPLY, "recommendation": None}

    # Toleransi KELUARGA
    extracted_needs_raw = params.get("needs", []) or []
    if "keluarga" in extracted_needs_raw:
        match = re.search(r'(\d+)\s*orang', user_text.lower())
        if match:
            num_people = int(match.group(1))
            if num_people >= 3:
                params["is_complete"] = True
                if "needs_missing" in params.get("parse_warnings", []):
                    params["parse_warnings"].remove("needs_missing")

    # ===== Ekstraksi budget, fallback =====
    extracted_budget_raw = params.get("budget")
    extracted_budget = normalize_budget_string(str(extracted_budget_raw)) if extracted_budget_raw else None

    if not extracted_budget:
        extracted_budget = extract_budget_fallback(user_text)

    extracted_needs = extracted_needs_raw
    extracted_filters = params.get("filters", {}) or {}
    if not isinstance(extracted_filters, dict):
        extracted_filters = {}

    fuels_cur = extracted_filters.get("fuels") or []
    if isinstance(fuels_cur, (str, bytes)):
        fuels_cur = [fuels_cur]

    # Pindahkan token bahan bakar dari needs ke filters
    moved_fuels_tokens, moved_fuels_codes = [], []
    for token in list(extracted_needs):
        if not token:
            continue
        try:
            code = fuel_to_code(token.lower()) if fuel_to_code else None
        except Exception:
            code = None
        if code and code != "o":
            if code not in fuels_cur:
                fuels_cur.append(code)
            moved_fuels_tokens.append(token)
            moved_fuels_codes.append(code)
            if token in extracted_needs:
                extracted_needs.remove(token)

    # Normalisasi fuels
    fuels_norm: List[str] = []
    for f in fuels_cur:
        fs = str(f).strip().lower()
        if fs in {"g", "d", "h", "p", "e"}:
            ff = fs
        else:
            try:
                ff = fuel_to_code(fs)
            except Exception:
                ff = "o"
        if ff and ff != "o" and ff not in fuels_norm:
            fuels_norm.append(ff)
    extracted_filters["fuels"] = fuels_norm if fuels_norm else ['g','d','h','p','e']

    # Validasi needs
    valid_needs: List[str] = []
    for n in extracted_needs:
        n_norm = str(n).strip().lower()
        if n_norm in NEED_LABELS:
            valid_needs.append(n_norm)
        elif n_norm in {"kota", "city", "dalam kota", "urban", "gesit"}:
            valid_needs.append("perkotaan")
    extracted_needs = valid_needs

    if not extracted_budget:
        return {"reply": "Oke, saya siap bantu. Berapa **budget maksimal** Anda (mis. 600jt)?", "parsed_constraints": params, "recommendation": None}

    # PANGGIL SPK
    try:
        results = rank_candidates(
            df_master=df,
            budget=float(extracted_budget),
            spec_filters=extracted_filters,
            needs=extracted_needs,
            topn=6
        )

        if not results.empty:
            results = attach_images(results)
            if "fuel_code" in results.columns:
                results["fuel_code"] = results["fuel_code"].astype(str).str.lower()
                results["fuel_label"] = results["fuel_code"].map(FUEL_LABEL_MAP).fillna("Lainnya")
            results["fit_score"] = pd.to_numeric(results.get("fit_score", 0), errors="coerce").round(4)
            rec_list = sanitize_for_json(df_to_items(results))
        else:
            rec_list = []
        count = len(rec_list)

    except Exception:
        return {"reply": "Ada kesalahan saat menghitung rekomendasi.", "recommendation": None}

    # Susun reply ringkas
    if count == 0:
        reply_text = "Maaf, tidak ada mobil yang cocok dengan kriteria tersebut."
    else:
        needs_str = ", ".join([n.replace("_", " ").title() for n in extracted_needs]) or "tanpa kebutuhan spesifik"
        budget_str = f"Rp {int(extracted_budget):,}" if extracted_budget else "budget Anda"
        reply_text = f"Halo! Berdasarkan {budget_str} dan prioritas {needs_str}, ini rekomendasi terbaik:\n\nSilakan klik gambar mobil untuk analisis detail."

    rec_payload = {
        "budget": extracted_budget,
        "needs": extracted_needs,
        "filters": extracted_filters,
        "count": count,
        "items": rec_list
    }
    set_last_recommendation(rec_payload)

    return sanitize_for_json({
        "reply": reply_text,
        "parsed_constraints": {
            "budget": extracted_budget,
            "needs": extracted_needs,
            "filters": extracted_filters,
            "is_complete": params.get("is_complete", True)
        },
        "recommendation": rec_payload
    })


@router.post("/analyze-image")
async def analyze_image_endpoint(payload: ImageAnalysisRequest = Body(...)):
    return {"reply": "Fitur visi belum diaktifkan di model lokal ini."}