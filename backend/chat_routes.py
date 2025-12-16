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
# 1. KONFIGURASI AI (DUAL LANE: LOCAL vs CLOUD)
# ====================================================================

# 
# GANTI DI SINI UNTUK PINDAH JALUR: "CLOUD" atau "LOCAL"
AI_MODE = "CLOUD"

if AI_MODE == "CLOUD":
    print("--- 🚀 MODE AI: CLOUD (OpenRouter) ---")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("WARNING: OPENROUTER_API_KEY tidak ditemukan di .env!")
        api_key = "dummy"

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "VRoom Car Recommender",
        }
    )
    # Model Cepat & Gratis/Murah di OpenRouter
    # Rekomendasi: "google/gemini-2.0-flash-lite-preview-02-05:free" atau "openai/gpt-4o-mini"
    MODEL_NAME = "openai/gpt-oss-120b:free"

else:
    print("--- 🏠 MODE AI: LOCAL (Ollama) ---")
    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    )
    MODEL_NAME = "llama3.1"

# ====================================================================
# 2. SYSTEM PROMPTS (FINAL)
# ====================================================================

SYSTEM_PROMPT_NLU = """
Anda adalah NLU extractor untuk sistem rekomendasi mobil bernama "VRoom".
TUGAS UTAMA:
- Dari satu string user, ekstrak secara deterministik ke JSON sesuai skema yang diberikan.
- Output harus murni JSON (tanpa teks tambahan).

WAJIB — SKEMA JSON (OUTPUT)
{
  "intent": "SEARCH" | "OFF_TOPIC" | "ANALYZE" | "OTHER",
  "budget": int | null, 
  "needs": [string], 
  "filters": {
     "trans_choice": "matic"|"manual"|null,
     "brand": string|null,
     "fuels": [ "g"|"d"|"h"|"p"|"e" ]|null
  },
  "is_complete": boolean,
  "confidence": float,
  "parse_warnings": [string]
}

RULES PENTING:
1. OFF_TOPIC: Jika pesan membahas politik, kesehatan, ekonomi personal, atau barang non-otomotif -> {"intent":"OFF_TOPIC", "reply":"..."}.
2. INTENT ANALYZE: Jika user meminta "kenapa X rendah", "analisis", "jelaskan", set intent="ANALYZE".
3. BUDGET: "400jt" -> 400000000. Rentang "300-400jt" -> ambil batas atas.
4. NEEDS (MAPPING IMPLISIT):
   - "mudik", "luar kota", "tol", "touring", "liburan" -> ["perjalanan_jauh"]
   - "jalan rusak", "berlubang", "terjal", "banjir", "gunung" -> ["offroad"]
   - "macet", "gesit", "parkir", "harian", "antar anak", "kantor" -> ["perkotaan"]
   - "anak", "istri", "muat banyak", "7 seater", "keluarga kecil" -> ["keluarga"]
   - "ngebut", "kencang", "enak disetir" -> ["fun"]
   - "barang", "usaha", "pickup", "jualan" -> ["niaga"]
5. FUEL: Jika user sebut "listrik"/"ev" -> masukkan ke filters.fuels=["e"], JANGAN ke needs.
6. IS_COMPLETE: True jika budget atau needs tersedia.

CONTOH OUTPUT VALID:
{
  "intent":"SEARCH",
  "budget":400000000,
  "needs":["keluarga","perkotaan"],
  "filters":{"trans_choice":null,"brand":null,"fuels":null},
  "is_complete":true,
  "confidence":0.92,
  "parse_warnings":[]
}
"""

SYSTEM_PROMPT_ANALYST = """
Anda adalah Konsultan Otomotif VRoom yang cerdas dan adaptif.
Tugas Anda: Memberikan analisis perbandingan mobil yang SANGAT SPESIFIK dan ringkas terhadap KEBUTUHAN USER.

ATURAN KERAS (ANTI-HALUSINASI):
1. JANGAN menyebut fitur spesifik (Sunroof, ADAS) KECUALI ada di DATA SPEK.
2. Gunakan logika turunan:
   - Wheelbase panjang -> Kabin lega / Stabil.
   - RWD -> Kuat tanjakan.
   - FWD -> Efisien.
   - Diesel/Turbo -> Torsi besar.

LOGIKA ADAPTASI:
- "OFFROAD": Bahas Ground Clearance & Penggerak.
- "KELUARGA": Bahas Kursi & Ruang.
- "PERJALANAN JAUH": Bahas Kestabilan & Mesin Diesel.
- "FUN": Bahas Tenaga & Handling.
- "IRIT/KOTA": Bahas Dimensi & Konsumsi BBM.

INSTRUKSI JAWABAN:
1. Gunakan bahasa natural & ringkas (Maks 1 paragraf).
2. Jangan sebutkan skor angka.
3. Akhiri dengan rekomendasi singkat.
"""

# ====================================================================
# 3. MODELS & UTILS
# ====================================================================

class ChatMessage(BaseModel):
    message: str

class ImageAnalysisRequest(BaseModel):
    image_url: str
    prompt: Optional[str] = "Mobil apakah ini? Jelaskan spesifikasinya singkat."

def clean_json_string(s: str) -> str:
    s = s.strip()
    # Hapus markdown code blocks jika ada
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
    return data

def build_summary_text(rec_list: List[Dict[str, Any]]) -> str:
    text = ""
    for i, car in enumerate(rec_list[:6]):
        price = car.get('price', 0)
        price_str = f"{price:,}" if price else "N/A"
        text += f"Rank {i+1}. {car.get('brand')} {car.get('model')} (Rp {price_str})\n"
    return text

# --- OFF TOPIC CHECK ---
NON_AUTO_SIGNAL = [
    "politik", "presiden", "agama", "kesehatan", "obat", "dokter",
    "investasi", "saham", "kripto", "emas", "gaji", "hukum"
]
def quick_offtopic_check(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in NON_AUTO_SIGNAL)

OOT_REPLY = "Maaf, saya hanya bisa membantu rekomendasi mobil."

# --- BUDGET PARSING ---
def normalize_budget_string(budget_str: str) -> Optional[float]:
    s = str(budget_str).lower().replace(" ", "").replace(".", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)(jt|juta|m)?(?:-an)?", s)
    if not m: return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "m": return num * 1000000000
    if unit in ["jt", "juta"]: return num * 1000000
    if num > 1000000: return num 
    return num * 1000000 

def extract_budget_fallback(text: str) -> Optional[float]:
    text = text.lower().replace(".", "").replace(",", ".")
    m = re.search(r"(\d+)\s*(jt|juta|m)", text)
    if not m: return None
    num = float(m.group(1))
    if m.group(2) == "m": return num * 1000000000
    return num * 1000000

# ====================================================================
# 4. ENDPOINT CHAT
# ====================================================================

FUEL_KEYWORDS = ["bensin", "diesel", "hybrid", "listrik", "ev"]
VALID_NEEDS = ["keluarga", "perjalanan_jauh", "fun", "perkotaan", "offroad", "niaga"]

@router.post("/chat")
async def chat_endpoint(payload: ChatMessage = Body(...)):
    user_text = (payload.message or "").strip()
    print(f"[CHAT INPUT] {user_text}")

    if not user_text:
        return {"reply": "Pesan kosong.", "recommendation": None}

    if quick_offtopic_check(user_text):
        return {"reply": OOT_REPLY, "recommendation": None}

    df = get_master_data()
    if df.empty:
        return {"reply": "Database mobil kosong/belum siap.", "recommendation": None}

    # ===== A. DETEKSI MODE ANALISIS =====
    analyze_kw = ["analisis", "kenapa", "mengapa", "peringkat", "ranking", "jelaskan"]
    last_rec = get_last_recommendation()
    
    # Logic: Jika ada kata kunci analisis DAN ada history rekomendasi -> Mode Analyst
    if any(k in user_text.lower() for k in analyze_kw) and last_rec and last_rec.get("count", 0) > 0:
        summary = build_summary_text(last_rec["items"])
        try:
            res = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYST},
                    {"role": "user", "content": f"DATA:\n{summary}\n\nPERTANYAAN USER: {user_text}"}
                ],
                temperature=0.7,
            )
            return {
                "reply": res.choices[0].message.content,
                "recommendation": last_rec 
            }
        except Exception as e:
            print(f"[ERROR ANALYST] {e}")
            return {"reply": "Gagal membuat analisis.", "recommendation": None}

    # ===== B. NLU (EKSTRAKSI PARAMETER) =====
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_NLU},
                {"role": "user", "content": user_text}
            ],
            temperature=0.0, # Deterministik
        )
        raw_json = clean_json_string(res.choices[0].message.content)
        params = json.loads(raw_json)
        print(f"[DEBUG NLU] Params: {params}") 
    except Exception as e:
        print(f"[ERROR NLU] {e}")
        # Jika NLU gagal total, coba fallback budget manual
        budget_fallback = extract_budget_fallback(user_text)
        if budget_fallback:
             params = {"budget": budget_fallback, "needs": [], "filters": {}}
        else:
            return {
                "reply": "Maaf, saya kurang paham. Coba format: 'Cari mobil [kebutuhan] budget [angka]'",
                "recommendation": None
            }

    # Cek Intent dari NLU
    if params.get("intent") == "OFF_TOPIC":
        reply = params.get("reply", OOT_REPLY)
        return {"reply": reply, "recommendation": None}
    
    if params.get("intent") == "ANALYZE" and last_rec:
        # Redirect ke logic analyst di atas jika intent NLU deteksi analyze
        # (Recursive call atau logic ulang, disini kita simplifikasi minta ulang user)
        pass 

    # ===== C. SANITASI DATA (PENTING!) =====
    
    # 1. Budget
    budget_raw = params.get("budget")
    extracted_budget = normalize_budget_string(str(budget_raw)) if budget_raw else extract_budget_fallback(user_text)

    if not extracted_budget:
        return {
            "reply": "Oke, berapa **budget maksimal** Anda? (misal: 500 juta)",
            "parsed_constraints": params,
            "recommendation": None
        }

    # 2. Needs & Fuels (Pindahkan fuel dari needs ke filters)
    extracted_needs = params.get("needs", [])
    extracted_filters = params.get("filters", {}) or {}
    
    # Ambil fuels dari filters yang mungkin sudah diisi LLM
    found_fuels = set(extracted_filters.get("fuels", []) or [])
    final_needs = []

    for item in extracted_needs:
        token = item.lower().strip()
        # Cek apakah token sebenarnya adalah jenis bahan bakar (jika LLM salah masukin ke needs)
        if token in FUEL_KEYWORDS:
            if token in ["ev", "listrik"]: found_fuels.add("e") # Mapping ke kode SPK
            elif token == "diesel": found_fuels.add("d")
            elif token == "hybrid": found_fuels.add("h")
            elif token == "bensin": found_fuels.add("g")
        # Cek apakah valid need
        elif token in VALID_NEEDS:
            final_needs.append(token)
        # Mapping manual fallback
        elif token in ["mudik", "touring"]: final_needs.append("perjalanan_jauh")
        elif token in ["macet", "gesit"]: final_needs.append("perkotaan")
        elif token in ["banjir", "rusak", "terjal"]: final_needs.append("offroad")

    # Update filters
    if found_fuels:
        extracted_filters["fuels"] = list(found_fuels)
    
    # Default fuels jika kosong
    if not extracted_filters.get("fuels"):
        extracted_filters["fuels"] = ['g', 'd', 'h', 'p', 'e'] 

    # ===== D. JALANKAN SPK =====
    try:
        results = rank_candidates(
            df_master=df,
            budget=float(extracted_budget),
            spec_filters=extracted_filters,
            needs=final_needs,
            topn=6
        )
    except Exception as e:
        print(f"[ERROR SPK] {e}")
        return {"reply": "Gagal menghitung rekomendasi.", "recommendation": None}

    if results.empty:
        return {"reply": "Maaf, tidak ada mobil yang cocok dengan kriteria tersebut (cek budget/filter).", "recommendation": None}

    # Format Hasil
    results = attach_images(results)
    if "fuel_code" in results.columns:
        results["fuel_label"] = results["fuel_code"].map(FUEL_LABEL_MAP).fillna("Lainnya")
    
    rec_items = sanitize_for_json(df_to_items(results))
    
    payload = {
        "budget": extracted_budget,
        "needs": final_needs,
        "filters": extracted_filters,
        "count": len(rec_items),
        "items": rec_items
    }
    set_last_recommendation(payload)

    # Buat Balasan
    needs_str = ", ".join([n.replace("_", " ").title() for n in final_needs]) or "Umum"
    reply_text = f"Halo! Berdasarkan budget Rp {int(extracted_budget):,} dan kebutuhan **{needs_str}**, ini rekomendasi VRoom:"

    return {
        "reply": reply_text,
        "parsed_constraints": payload, 
        "recommendation": payload
    }

@router.post("/analyze-image")
async def analyze_image_endpoint(payload: ImageAnalysisRequest = Body(...)):
    return {"reply": "Fitur visi belum diaktifkan di model ini."}