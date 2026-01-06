from __future__ import annotations
import os
import json
import re
import math
import numpy as np  # Wajib import numpy
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Body
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# Pastikan import ini sesuai dengan struktur folder Anda
from .spk import rank_candidates
from .data_loader import get_master_data
from .common_utils import attach_images, df_to_items, FUEL_LABEL_MAP
from .recommendation_state import set_last_recommendation, get_last_recommendation

load_dotenv()
router = APIRouter()

# --- KONFIGURASI AI ---
AI_MODE = "CLOUD"  # Ganti "LOCAL" jika pakai Ollama

if AI_MODE == "CLOUD":
    api_key = os.getenv("OPENROUTER_API_KEY") or "dummy"
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={"HTTP-Referer": "http://localhost:3000", "X-Title": "VRoom"},
    )
    MODEL_NAME = "openai/gpt-4o-mini"
else:
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    MODEL_NAME = "llama3.1"


# --- DATA MODELS ---
class ConversationState(BaseModel):
    """Menyimpan ingatan percakapan"""
    budget: Optional[float] = None
    needs: List[str] = []
    filters: Dict[str, Any] = {}
    step: str = "INIT"  # INIT, ASK_BUDGET, ASK_NEEDS, READY


class ChatRequest(BaseModel):
    message: str
    state: Optional[ConversationState] = None


# --- UTILS & SANITIZER ---

def sanitize_for_json(data: Any) -> Any:
    """Membersihkan data dari NaN/Infinity agar JSON compliant."""
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data): return 0.0
        return data
    elif isinstance(data, (np.float32, np.float64)):
        if np.isnan(data) or np.isinf(data): return 0.0
        return float(data)
    elif isinstance(data, (np.int32, np.int64)):
        return int(data)
    elif data is None:
        return None
    return data


def clean_json_string(s: str) -> str:
    s = s.strip()
    if "```json" in s: s = s.split("```json")[1].split("```")[0]
    elif "```" in s: s = s.split("```")[1].split("```")[0]
    return s.strip()


def normalize_budget_string(budget_str: str) -> Optional[float]:
    s = str(budget_str).lower().replace(" ", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)(jt|juta|m|miliar)?", s)
    if not m: return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ["m", "miliar"]: return num * 1_000_000_000
    if unit in ["jt", "juta"]: return num * 1_000_000
    if num < 100: return num * 1_000_000_000 
    else: return num * 1_000_000      


def format_budget_human(amount: float) -> str:
    if amount >= 1_000_000_000:
        val = amount / 1_000_000_000
        formatted = f"{val:,.2f}".rstrip('0').rstrip('.')
        return f"Rp {formatted.replace('.', ',')} Miliar"
    elif amount >= 1_000_000:
        val = amount / 1_000_000
        formatted = f"{val:,.2f}".rstrip('0').rstrip('.')
        return f"Rp {formatted.replace('.', ',')} Juta"
    else:
        return f"Rp {int(amount):,}".replace(",", ".")


def build_summary_text(rec_list: List[Dict[str, Any]]) -> str:
    text = ""
    for i, car in enumerate(rec_list[:5]):
        price = car.get('price', 0)
        price_str = format_budget_human(price)
        score = car.get('fit_score', 0)
        if math.isnan(score) or math.isinf(score): score = 0
        text += f"Rank {i+1}. {car.get('brand')} {car.get('model')} ({price_str}) - Skor: {score:.2f}\n"
    return text


# --- PROMPTS ---

SYSTEM_PROMPT_NLU = """
Anda adalah NLU extractor untuk VRoom.
TUGAS: Ekstrak entitas dari teks user ke dalam format JSON.
JANGAN mengarang nilai yang tidak ada di teks.

SKEMA JSON:
{
  "intent": "SEARCH" | "RESET" | "INFO" | "OTHER",
  "budget": int | null, 
  "needs": [string],
  "filters": { "brand": string|null, "trans": "matic"|"manual"|"ANY"|null }
}

RULES:
1. "RESET" / "Ulangi" -> intent: RESET.
2. BUDGET: "300jt" -> 300000000.
3. NEEDS MAPPING:
   - "keluarga", "anak", "7 seater" -> "keluarga"
   - "irit", "kota", "macet", "harian" -> "perkotaan"
   - "luar kota", "tol", "mudik" -> "perjalanan_jauh"
   - "gunung", "proyek", "banjir" -> "offroad"
   - "ngebut", "sport", "gaya" -> "fun"
   - "usaha", "barang", "pickup" -> "niaga"
4. JIKA user hanya menjawab angka, biarkan budget null di JSON.
5. PEMBATALAN FILTER (PENTING):
   - Jika user bilang "jangan deh", "gak jadi", "bebas aja", "semua merk", "batal", "hapus filter" -> SET filters.brand = "ANY".
   - "ANY" adalah sinyal untuk menghapus filter tersebut.
"""

SYSTEM_PROMPT_ANALYST = """
Anda adalah Konsultan Otomotif AI VRoom.
Tugas: Jelaskan mengapa mobil tertentu direkomendasikan berdasarkan kebutuhan user.

RULES:
1. Gunakan gaya bahasa santai, akrab, tapi profesional.
2. Fokus pada alasan teknis yang relevan.
3. JANGAN HALUSINASI.
4. Gunakan emoji (💡, 🚗, ✅).
5. Jawab dengan ringkas.
"""


@router.post("/chat")
async def chat_endpoint(payload: ChatRequest = Body(...)):
    user_text = payload.message.strip()
    current_state = payload.state or ConversationState()

    # --- FITUR 1: RESET ---
    if user_text.lower() in ["reset", "ulangi", "mulai baru", "clear", "ganti budget"]:
        return {
            "reply": "Halo Kak! 👋 Saya AI VRoom siap bantu.\n\n🤔 Saya lagi mikir nih, kira-kira Kakak nyiapin budget maksimal berapa ya?",
            "state": ConversationState(step="ASK_BUDGET"), 
            "recommendation": None
        }

    # --- FITUR 2: ANALYST / RAG ---
    is_asking_reason = any(k in user_text.lower() for k in ["kenapa", "mengapa", "jelaskan", "kelebihan", "kekurangan", "analisis"])
    if "[ANALISIS]" in user_text or (is_asking_reason and current_state.step == "READY"):
        last_rec = get_last_recommendation()
        if not last_rec or not last_rec.get("items"):
            return {"reply": "Maaf Kak, saya belum kasih rekomendasi mobil nih 😔. 🤔\nKita cari dulu yuk! Berapa budget maksimal Kakak?", "state": current_state}
        
        summary_data = build_summary_text(last_rec["items"])
        needs_context = ", ".join(current_state.needs)
        
        try:
            res = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_ANALYST},
                    {"role": "user", "content": f"KONTEKS KEBUTUHAN USER: {needs_context}\n\nDATA REKOMENDASI TERAKHIR:\n{summary_data}\n\nPERTANYAAN USER: {user_text}"}
                ]
            )
            return sanitize_for_json({"reply": res.choices[0].message.content, "state": current_state})
        except Exception as e:
            print(f"[ANALYST ERROR] {e}")
            return {"reply": "Waduh, saya lagi pusing nih Kak. Coba tanya lagi nanti ya! 😵‍💫", "state": current_state}

    # --- FITUR 3: PENCARIAN & STATE MACHINE ---
    extracted = {}
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_NLU},
                {"role": "user", "content": user_text},
            ],
            temperature=0.0,
        )
        extracted = json.loads(clean_json_string(res.choices[0].message.content))
    except Exception as e:
        print(f"[NLU ERROR] {e}")

    # Logic Budget
    extracted_budget = extracted.get("budget")
    manual_budget = normalize_budget_string(user_text)
    
    if manual_budget:
        current_state.budget = manual_budget
    elif extracted_budget:
        current_state.budget = float(extracted_budget)

    # Update Needs
    new_needs = extracted.get("needs", [])
    if new_needs:
        current_state.needs.extend(new_needs)
        current_state.needs = list(set(current_state.needs))

    # --- UPDATE LOGIC FILTER (Handle "ANY") ---
    new_filters = extracted.get("filters", {})
    if new_filters:
        for k, v in new_filters.items():
            if v == "ANY": 
                # Jika NLU kirim sinyal "ANY", HAPUS filter dari state
                if k in current_state.filters:
                    del current_state.filters[k]
            elif v: 
                # Update biasa
                current_state.filters[k] = v

    # STEP 1: Cek Budget
    if not current_state.budget:
        current_state.step = "ASK_BUDGET"
        return {
            "reply": "Halo Kak! 👋 Saya carbot siap membantu.\n\n🤔 Saya mau tanya nih, kira-kira Kakak nyiapin budget maksimal berapa ya? (misal: 300 juta)",
            "state": current_state,
            "recommendation": None,
        }

    # STEP 2: Cek Needs
    if not current_state.needs:
        current_state.step = "ASK_NEEDS"
        human_budget = format_budget_human(current_state.budget)
        return {
            "reply": f"Oke, budget {human_budget} sudah saya catat! 💰\n\n💡Kira-kira mobil ini nanti bakal sering dipakai buat apa?\n\n(Misal: Buat Keluarga, Harian di Kota, atau Roadtrip Luar Kota?)",
            "state": current_state,
            "recommendation": None,
        }

    # STEP 3: READY -> Jalankan SPK
    current_state.step = "READY"
    df = get_master_data()
    
    results = None
    try:
        results = rank_candidates(
            df_master=df,
            budget=current_state.budget,
            needs=current_state.needs,
            spec_filters=current_state.filters,
            topn=5,
        )
    except Exception as e:
        print(f"[SPK ERROR] {e}")
        return {"reply": "Waduh, ada sedikit gangguan teknis nih Kak. Coba lagi nanti ya! 🛠️", "state": current_state}

    if results is None or results.empty:
        # Pesan khusus jika filter terlalu ketat
        if current_state.filters.get("brand"):
             return {
                "reply": f"Waduh... 🤔 Saya cari di database, {current_state.filters['brand'].title()} nggak ada yang masuk budget/kriteria Kakak nih.\n\n💡 Coba ganti merk lain atau ketik 'bebas' buat lihat semua merk.",
                "state": current_state,
            }
        return {
            "reply": "Waduh... 🤔 Saya sudah cari di database tapi belum nemu yang pas banget sama kriteria itu.\n\n💡 Coba naikkan sedikit budgetnya atau kurangi filternya ya Kak.",
            "state": current_state,
        }

    results = attach_images(results)
    if "fuel_code" in results.columns:
        results["fuel_label"] = results["fuel_code"].map(FUEL_LABEL_MAP).fillna("Lainnya")

    rec_items = df_to_items(results)

    rec_payload = {
        "budget": current_state.budget,
        "needs": current_state.needs,
        "filters": current_state.filters,
        "count": len(rec_items),
        "items": rec_items,
    }
    set_last_recommendation(rec_payload)

    needs_str = ", ".join(current_state.needs).title()
    human_budget = format_budget_human(current_state.budget)
    
    # Custom Reply jika ada filter Brand
    filter_msg = ""
    if current_state.filters.get("brand"):
        filter_msg = f" (khusus {current_state.filters['brand'].title()})"

    reply_text = f"Sip, datanya lengkap! 🤔 Sebentar saya cek dulu...\n\n💡 AHA! Ketemu! \nBuat kebutuhan {needs_str} dengan budget {human_budget}{filter_msg}, ini dia rekomendasi yang paling pas buat Kakak:"

    final_response = {
        "reply": reply_text,
        "state": current_state,
        "recommendation": rec_payload
    }
    
    return sanitize_for_json(final_response)