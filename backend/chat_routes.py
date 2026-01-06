# file: backend/chat_routes.py
from __future__ import annotations
import os
import json
import re
import math
import time
import numpy as np  # Wajib import numpy
from typing import List, Optional, Dict, Any, Tuple

from fastapi import APIRouter, Body
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# Pastikan fungsi berikut ada di project Anda
from .spk import rank_candidates
from .data_loader import get_master_data
from .common_utils import attach_images, df_to_items, FUEL_LABEL_MAP
from .recommendation_state import set_last_recommendation, get_last_recommendation
from .spk_utils import fuel_to_code

load_dotenv()
router = APIRouter()

# --- KONFIGURASI AI ---
AI_MODE = "CLOUD"  # "LOCAL" jika pakai Ollama

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
    env: Dict[str, bool] = {}  # new: environment flags (bad road, coastal, etc.)
    step: str = "INIT"  # INIT, ASK_BUDGET, ASK_NEEDS, CONFIRM_NEEDS, READY


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
    """Ambil JSON dalam triple backticks bila ada, atau kembalikan string bersih."""
    s = (s or "").strip()
    if "```json" in s:
        try:
            return s.split("```json")[1].split("```")[0].strip()
        except Exception:
            pass
    if "```" in s:
        try:
            return s.split("```")[1].split("```")[0].strip()
        except Exception:
            pass
    return s


def normalize_budget_string(budget_str: str) -> Optional[float]:
    s = str(budget_str).lower().replace(" ", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)(jt|juta|m|miliar)?", s)
    if not m: return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ["m", "miliar"]: return num * 1_000_000_000
    if unit in ["jt", "juta"]: return num * 1_000_000
    # Ambiguitas: jika angka kecil (mis. '9' maksud 9 juta?), gunakan juta
    if num < 100: return num * 1_000_000
    return num * 1_000_000


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
        try:
            if math.isnan(score) or math.isinf(score): score = 0
        except Exception:
            score = 0
        text += f"Rank {i+1}. {car.get('brand')} {car.get('model')} ({price_str}) - Skor: {score:.2f}\n"
    return text


# --- tambahan: mapping & conflict resolver untuk chatty confirmation ---

# Canonical needs the SPK expects
VALID_NEEDS = {"perkotaan", "perjalanan_jauh", "keluarga", "fun", "offroad", "niaga"}

# Map common aliases/phrases to canonical needs
CANONICAL_NEEDS = {
    # perkotaan
    "perkotaan": "perkotaan",
    "harian": "perkotaan",
    "pemakaian harian": "perkotaan",
    "harian di kota": "perkotaan",
    "kota": "perkotaan",
    "macet": "perkotaan",
    "irit": "perkotaan",
    "gampang parkir": "perkotaan",
    "masuk gang": "perkotaan",
    "sempit": "perkotaan",

    # perjalanan jauh
    "perjalanan_jauh": "perjalanan_jauh",
    "mudik": "perjalanan_jauh",
    "luar kota": "perjalanan_jauh",
    "tol": "perjalanan_jauh",
    "roadtrip": "perjalanan_jauh",

    # keluarga
    "keluarga": "keluarga",
    "anak": "keluarga",
    "7 seater": "keluarga",
    "7-seater": "keluarga",
    "7seater": "keluarga",

    # fun
    "fun": "fun",
    "sport": "fun",
    "ngebut": "fun",
    "gaya": "fun",

    # offroad
    "offroad": "offroad",
    "medan berat": "offroad",
    "segala medan": "offroad",
    "gunung": "offroad",
    "banjir": "offroad",
    "proyek": "offroad",
    "jalan rusak": "offroad",
    "jalan jelek": "offroad",
    "jalan jelek": "offroad",

    # niaga
    "niaga": "niaga",
    "usaha": "niaga",
    "angkut": "niaga",
    "barang": "niaga",
    "pickup": "niaga",
}

_NEEDS_HUMAN_MAP = {
    "perkotaan": "harian di kota",
    "perjalanan_jauh": "perjalanan luar kota",
    "keluarga": "untuk keluarga",
    "fun": "yang penting fun buat nyetir",
    "offroad": "medan berat / off-road",
    "niaga": "usaha / angkut barang",
}

def needs_to_human(needs: List[str]) -> List[str]:
    return [ _NEEDS_HUMAN_MAP.get(n, n) for n in needs ]


def resolve_conflicts(needs: List[str]) -> Tuple[List[str], List[str]]:
    """
    Tangani konflik sederhana:
    - fun vs niaga -> hapus fun (lebih jarang dipakai bersama niaga)
    - perjalanan_jauh & perkotaan -> biarkan, tapi catat note
    Return: (clean_needs, notes)
    """
    notes = []
    clean = set(needs)

    if "fun" in clean and "niaga" in clean:
        clean.remove("fun")
        notes.append("Saya hilangkan preferensi 'fun' karena kurang cocok dengan kebutuhan niaga.")

    if "perjalanan_jauh" in clean and "perkotaan" in clean:
        notes.append("Kombinasi perjalanan jauh & penggunaan harian terdeteksi — saya akan seimbangkan rekomendasi.")

    return list(clean), notes


def normalize_need_token(token: str) -> Optional[str]:
    """Normalisasi satu token kebutuhan ke canonical (VALID_NEEDS) jika memungkinkan."""
    if not token:
        return None
    t = str(token).strip().lower()
    # direct canonical match
    if t in VALID_NEEDS:
        return t
    # exact map keys
    if t in CANONICAL_NEEDS:
        return CANONICAL_NEEDS[t]
    # fuzzy containment: check if any alias is substring of token
    for alias, canonical in CANONICAL_NEEDS.items():
        if alias in t:
            return canonical
    # also check token contains alias (reverse)
    for alias, canonical in CANONICAL_NEEDS.items():
        if t in alias:
            return canonical
    return None


def normalize_needs_list(raw_needs: List[Any]) -> List[str]:
    """Normalize list of raw needs (strings) to canonical needs (unique)."""
    out: List[str] = []
    for item in raw_needs:
        try:
            s = str(item)
        except Exception:
            continue
        # split comma/and if user sends combined phrases
        parts = re.split(r"[,\|;/]+|\band\b|\b&\b", s, flags=re.I)
        for p in parts:
            n = normalize_need_token(p)
            if n:
                out.append(n)
    return list(dict.fromkeys(out))  # dedupe preserving order


# --- Priority, hesitation, environment helpers ---
NEED_PRIORITY = {
    "keluarga": 3,
    "niaga": 3,
    "perkotaan": 2,
    "offroad": 2,
    "perjalanan_jauh": 1,
    "fun": 1,
}

HESITATION_WORDS = ["kayaknya", "mungkin", "sesekali", "jarang", "kadang", "biasanya tidak", "tapi kadang"]

def sort_needs_by_priority(needs: List[str]) -> List[str]:
    return sorted(
        list(dict.fromkeys(needs)),
        key=lambda n: NEED_PRIORITY.get(n, 1),
        reverse=True
    )

def has_hesitation(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in HESITATION_WORDS)

def detect_env_flags(text: str) -> Dict[str, bool]:
    flags: Dict[str,bool] = {}
    t = (text or "").lower()
    if re.search(r"jalan.*(rusak|jelek|bergelombang|berlubang|tidak rata|banyak lubang)", t):
        flags["bad_road"] = True
    if re.search(r"\b(banjir|sering banjir)\b", t):
        flags["flood_prone"] = True
    if re.search(r"\b(naik barang|angkut barang|usaha)\b", t):
        flags["cargo_need"] = True
    return flags


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
  "filters": { "brand": string|null, "trans": "matic"|"manual"|"ANY"|null, "fuel": "bensin"|"diesel"|"hybrid"|"ev"|null }
}

RULES:
- Jika user menyebut 'wajib' sebelum bahan bakar, anggap sebagai HARD constraint.
- Output harus JSON valid (murni).
"""

SYSTEM_PROMPT_ANALYST = """
Anda adalah Konsultan Otomotif AI VRoom.
Tugas: Jelaskan mengapa mobil tertentu direkomendasikan berdasarkan kebutuhan user.

PANDUAN:
- Ringkasan singkat 1-2 kalimat.
- Sebutkan 2 alasan utama.
- Jelaskan trade-off (kapan mobil ini tidak ideal).
- Jangan mengarang fakta.
- Jangan mengatakan 'hybrid mendekati diesel' atau sejenisnya.
- Gunakan bahasa santai, singkat, emoji seperlunya.
"""


# --- MAIN ENDPOINT ---
@router.post("/chat")
async def chat_endpoint(payload: ChatRequest = Body(...)):
    user_text = (payload.message or "").strip()
    current_state = payload.state or ConversationState()

    # --- FITUR 1: RESET ---
    if user_text.lower() in ["reset", "ulangi", "mulai baru", "clear", "ganti budget"]:
        return {
            "reply": "Halo Kak! 👋 Saya AI VRoom siap bantu.\n\n🤔 Saya lagi mikir nih, kira-kira Kakak nyiapin budget maksimal berapa ya?",
            "state": ConversationState(step="ASK_BUDGET"),
            "recommendation": None
        }

    # --- quick env detection from raw text (before NLU) ---
    try:
        env_flags = detect_env_flags(user_text)
        if env_flags:
            # merge into state.env
            current_state.env.update(env_flags)
    except Exception as e:
        print("[ENV DETECT ERROR]", e)

    # --- FITUR 2: ANALYST / RAG ---
    is_asking_reason = any(k in user_text.lower() for k in ["kenapa", "mengapa", "jelaskan", "kelebihan", "kekurangan", "analisis"])
    if "[analisis]" in user_text.lower() or (is_asking_reason and current_state.step == "READY"):
        last_rec = get_last_recommendation()
        if not last_rec or not last_rec.get("items"):
            return {"reply": "Maaf Kak, saya belum kasih rekomendasi mobil nih 😔. 🤔\nKita cari dulu yuk! Berapa budget maksimal Kakak?", "state": current_state}
        summary_data = build_summary_text(last_rec["items"])
        needs_context = ", ".join(needs_to_human(current_state.needs))
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

    # --- HANDLE CONFIRMATION (fast-path) ---
    if current_state.step == "CONFIRM_NEEDS":
        cmd = user_text.strip().lower()
        confirmations = {"iya", "ya", "betul", "oke", "lanjut", "sip"}
        negative = {"nggak", "tidak", "gak", "enggak", "batal"}

        if cmd in confirmations:
            current_state.step = "READY"  # lanjut SPK
        elif cmd in negative:
            current_state.step = "ASK_NEEDS"
            return {
                "reply": "Oke, nggak masalah. Ceritain lagi penggunaan singkat aja ya (misal: harian, keluarga, mudik).",
                "state": current_state,
                "recommendation": None,
            }
        # jika bukan jawaban singkat, biarkan NLU menangani pesan tersebut di bawah

    # --- FITUR 3: PENCARIAN & NLU ---
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
        extracted_raw = res.choices[0].message.content
        try:
            extracted = json.loads(clean_json_string(extracted_raw))
        except Exception:
            extracted = {}
    except Exception as e:
        print(f"[NLU ERROR] {e}")
        extracted = {}

    # Logic Budget
    extracted_budget = extracted.get("budget")
    manual_budget = normalize_budget_string(user_text)

    if manual_budget:
        current_state.budget = manual_budget
    elif extracted_budget:
        try:
            current_state.budget = float(extracted_budget)
        except Exception:
            pass

    # ---------- Detect explicit 'wajib' for fuel (hard constraint) ----------
    fuel_required_flag = False
    m_wajib = re.search(r"\bwajib\b", user_text.lower())
    if m_wajib:
        # check if near any fuel keyword
        if re.search(r"\b(wajib\b.*\b(diesel|bensin|hybrid|ev|electric|phev|hev))", user_text.lower()) or re.search(r"\b(diesel|bensin|hybrid|ev|electric|phev|hev)\b.*\bwajib\b", user_text.lower()):
            fuel_required_flag = True

    # Update Filters (handle 'fuel' mapping)
    new_filters = extracted.get("filters", {}) or {}

    # also accept top-level 'fuel'
    if extracted.get("fuel"):
        new_filters["fuel"] = extracted.get("fuel")

    if new_filters:
        for k, v in new_filters.items():
            if not v:
                continue
            # normalize "ANY" signals (NLU)
            if isinstance(v, str) and v.strip().upper() == "ANY":
                if k in current_state.filters:
                    del current_state.filters[k]
                continue

            # write raw value for traceability
            current_state.filters[k] = v

            # Normalize fuel to code(s) used by SPK — ensure we store `fuels` (list)
            if k in ["fuel", "fuel_type"]:
                # v might be list/str/dict
                cand_vals = []
                if isinstance(v, (list, tuple, set)):
                    cand_vals = list(v)
                else:
                    cand_vals = [v]

                codes = []
                for item in cand_vals:
                    try:
                        code = fuel_to_code(str(item))
                        if code and code != "o":
                            codes.append(code)
                    except Exception:
                        continue

                # dedupe
                codes = list(dict.fromkeys(codes))

                if codes:
                    # store as list expected by SPK
                    current_state.filters["fuels"] = codes
                    # also keep fuel_code single for backward/quick checks (first one)
                    current_state.filters["fuel_code"] = codes[0]
                    # keep human readable too
                    current_state.filters["fuel"] = v
                else:
                    # unknown -> keep raw string but do not create fuels list
                    current_state.filters["fuel"] = v

    # Update Needs (WITH NORMALIZATION to canonical values)
    raw_needs = extracted.get("needs", []) or []
    # also consider if user wrote needs directly in plain text (best-effort split)
    # e.g. "buat keluarga dan harian" -> try to extract tokens by splitting common separators
    if not raw_needs and user_text:
        # only attempt if user_text length reasonable and STATE indicates asking needs
        if current_state.step in ["ASK_NEEDS", "INIT"] or len(user_text) < 200:
            # naive split by comma/and/slash to find potential needs words
            cand_parts = re.split(r"[,\|;/]+|\band\b|\b&\b", user_text, flags=re.I)
            raw_needs = cand_parts

    normalized_from_nlu = normalize_needs_list(raw_needs)
    if normalized_from_nlu:
        current_state.needs.extend(normalized_from_nlu)
        current_state.needs = list(dict.fromkeys(current_state.needs))

    # === FIX: keluarga adalah ANCHOR NEED (tidak boleh hilang) ===
        if "keluarga" in normalized_from_nlu:
            current_state.needs = list(
                dict.fromkeys(["keluarga"] + current_state.needs)
            )

    # If env 'bad_road' detected, add offroad as contextual need (don't force if it's already present)
    try:
        if current_state.env.get("bad_road"):
            if "offroad" not in current_state.needs:
                # Append but keep order (will be re-ordered by priority later)
                current_state.needs.append("offroad")
    except Exception:
        pass

    # --- SMART CONFIRM_NEEDS LOGIC (implicit confirmation when appropriate) ---
    implicit_evidence = False
    if new_filters:
        implicit_evidence = True
    if len(normalized_from_nlu) > 1:
        implicit_evidence = True
    # more conservative: if text long but WITHOUT hesitation words -> implicit
    if len(user_text) > 40 and not has_hesitation(user_text):
        implicit_evidence = True

    if normalized_from_nlu and current_state.step in ["ASK_NEEDS", "INIT"]:
        # resolve conflicts and prepare confirmation text
        clean_needs, notes = resolve_conflicts(current_state.needs)
        current_state.needs = clean_needs

        if implicit_evidence:
            # implicit confirmation -> go ready
            current_state.step = "READY"
        else:
            # ask confirmation (chatty)
            current_state.step = "CONFIRM_NEEDS"
            bullets = "\n".join(f"• {t}" for t in needs_to_human(clean_needs))
            notes_txt = ("\n".join(f"💡 {n}" for n in notes)) if notes else ""
            reply_text = (
                "Kalau saya tangkap dari cerita Kakak, mobil ini nanti bakal dipakai untuk:\n\n"
                f"{bullets}\n\n"
                "Udah pas nggak? Kalau kurang/betul, bilang 'iya' atau koreksi aja ya 😊"
            )
            if notes_txt:
                reply_text += "\n\n" + notes_txt

            return {"reply": reply_text, "state": current_state, "recommendation": None}

    # If in CONFIRM_NEEDS but user added details in same message, treat as implicit confirm
    if current_state.step == "CONFIRM_NEEDS" and implicit_evidence:
        current_state.step = "READY"

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
            "reply": (
                f"Siap! Budget {human_budget} sudah saya catat 💰\n\n"
                "Sekarang saya mau kenal dulu pola pemakaian mobilnya ya, Kak.\n\n"
                "Biasanya mobil ini bakal lebih sering dipakai untuk apa?\n"
                "Contohnya bisa seperti:\n"
                "• Antar keluarga / aktivitas bareng anak\n"
                "• Dipakai harian di kota (compact dan irit)\n"
                "• Sering keluar kota atau perjalanan jauh\n"
                "• Medan berat atau kondisi jalan yang kurang bersahabat\n"
                "• Keperluan usaha atau angkut barang\n"
                "• Atau sekadar cari yang fun dan nyaman buat nyetir\n\n"
                "Boleh pilih satu atau kombinasinya sekalian.\n"
                "Kalau sudah ada preferensi khusus (merk, matic/manual, atau bahan bakar), "
                "langsung sebutkan juga ya 😊"
            ),
            "state": current_state,
            "recommendation": None,
        }

    # If CONFIRM_NEEDS remains (rare) -> ask for quick confirm
    if current_state.step == "CONFIRM_NEEDS":
        return {
            "reply": "Kalau sudah oke, ketik 'iya' atau 'lanjut' supaya saya bisa mulai cari rekomendasi ya 🙂",
            "state": current_state,
            "recommendation": None,
        }

    # --- PRE-SPK SANITY CHECKS (contoh: sangat ketat filter fuel+brand) ---
    # Jika user memasang filter fuel(s) + brand, cek dulu kasar apakah ada kandidat realistis.
    try:
        fuels_check = current_state.filters.get("fuels") or ([current_state.filters.get("fuel_code")] if current_state.filters.get("fuel_code") else None)
        brand_val = current_state.filters.get("brand")
        if fuels_check and brand_val:
            df_check = get_master_data()
            brand_lower = str(brand_val).strip().lower()
            df_check = df_check[df_check["brand"].fillna("").str.lower() == brand_lower]
            # gunakan kolom fuel_code jika ada
            if "fuel_code" in df_check.columns:
                df_check = df_check[df_check["fuel_code"].astype(str).str.lower().isin([str(x).lower() for x in fuels_check if x])]

            if df_check.empty:
                # jika user request 'wajib' fuel, jangan relax otomatis; minta user pilih
                if fuel_required_flag:
                    suggestion = (
                        "Catatan: untuk kombinasi merk + bahan bakar yang Kakak minta, pilihan benar-benar terbatas.\n\n"
                        "Mau saya tetap coba cari yang paling mendekati (jika ada), atau mau longgarkan kriteria (misal pilih bensin/hybrid)?"
                    )
                else:
                    suggestion = (
                        "Sedikit catatan nih — untuk kombinasi brand + bahan bakar yang Kakak sebut, pilihannya sangat terbatas.\n\n"
                        "Mau saya tetap cari yang paling mendekati (kalau ada), atau longgarkan kriteria (misal bensin/hybrid)?"
                    )
                return {"reply": suggestion, "state": current_state, "recommendation": None}
    except Exception as e:
        # jika cek gagal, jangan ganggu flow SPK; hanya log
        print(f"[SANITY CHECK ERROR] {e}")

    # --- FINAL GUARD: ensure current_state.needs only contains VALID_NEEDS ---
    try:
        # sort by priority first so SPK gets needs ordered by importance
        current_state.needs = sort_needs_by_priority([n for n in current_state.needs if n in VALID_NEEDS])
    except Exception:
        # fallback: reset sanitized list
        current_state.needs = [n for n in (current_state.needs or []) if isinstance(n, str) and n in VALID_NEEDS]

    # STEP 3: READY -> Jalankan SPK
    current_state.step = "READY"
    df = get_master_data()

    # DEBUG snapshot before SPK
    try:
        print("\n" + "=" * 40)
        print("[CHAT DEBUG] PRE-SPK SNAPSHOT")
        print(" Budget:", current_state.budget)
        print(" Needs:", current_state.needs)
        print(" Filters:", current_state.filters)
        print(" Env:", current_state.env)
        print(" Step:", current_state.step)
        print("=" * 40 + "\n")
    except Exception:
        pass

    results = None
    t0 = time.time()
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

    if results is None or (hasattr(results, "empty") and results.empty):
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

    # Inject fuel_label for client UI
    try:
        results = attach_images(results)
        if "fuel_code" in results.columns:
            results["fuel_label"] = results["fuel_code"].map(FUEL_LABEL_MAP).fillna("Lainnya")
    except Exception as e:
        print("[ATTACH_IMAGES ERROR]", e)

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

    filter_msg = ""
    if current_state.filters.get("brand"):
        filter_msg = f" (khusus {str(current_state.filters['brand']).title()})"

    reply_text = (
        f"Sip, datanya lengkap! 🤔 Sebentar saya cek dulu...\n\n"
        f"💡 AHA! Ketemu!\nBuat kebutuhan {needs_str} dengan budget {human_budget}{filter_msg}, ini dia rekomendasi yang paling pas buat Kakak:"
    )

    final_response = {
        "reply": reply_text,
        "state": current_state,
        "recommendation": rec_payload
    }

    # sanitize and return
    return sanitize_for_json(final_response)
