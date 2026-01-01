# tools/enrich_from_pdf.py
from __future__ import annotations

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from pdf_extract import extract_text_from_pdf

# =====================================================
# ENV
# =====================================================
load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    raise RuntimeError("OPENROUTER_API_KEY tidak ditemukan di .env")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
    default_headers={
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "VRoom Car Recommender",
    }
)

# =====================================================
# PATH (FIX SESUAI PROYEK KAMU)
# =====================================================
BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "data" / "brosur"
OUTPUT_JSON = BASE_DIR / "data" / "data_mobil_enriched.json"
FAILED_LOG = BASE_DIR / "data" / "pdf_failed_log.json"

# =====================================================
# PROMPT EKSTRAKSI TOTAL
# =====================================================
SYSTEM_PROMPT = """
Anda adalah SISTEM EKSTRAKSI DATA OTOMOTIF PROFESIONAL.

ATURAN MUTLAK:
1. EKSTRAK SEMUA SPESIFIKASI & FITUR YANG TERTULIS.
2. JANGAN menyimpulkan.
3. JANGAN menambah data dari pengetahuan luar.
4. Jika tidak tertulis → null.
5. OUTPUT HARUS JSON VALID.
6. Jika ada BEBERAPA VARIAN/TRIM → output ARRAY.
7. JANGAN sertakan teks penjelasan.
"""

def build_user_prompt(text: str) -> str:
    return f"""
TEKS BROSUR:
{text}

EKSTRAK KE FORMAT JSON BERIKUT:

[
  {{
    "brand": string|null,
    "model": string|null,
    "trim": string|null,
    "year": int|null,

    "dimensions": {{
      "length_mm": int|null,
      "width_mm": int|null,
      "height_mm": int|null,
      "wheelbase_mm": int|null,
      "ground_clearance_mm": int|null
    }},

    "powertrain": {{
      "fuel_type": "G|D|HEV|PHEV|BEV|null",
      "drivetrain": "FWD|RWD|AWD|4WD|null",
      "engine_cc": int|null,
      "battery_kwh": float|null,
      "motor_power_kw": float|null,
      "torque_nm": int|null
    }},

    "transmission": {{
      "category": "MT|AT|CVT|DCT|SingleSpeed|null",
      "technology_name": string|null,
      "manufacturer": string|null,
      "gears": int|null,
      "shift_mechanism": "TorqueConverter|DualClutch|Belt|DirectDrive|null",
      "paddle_shifter": boolean|null,
      "drive_modes": [string]
    }},

    "chassis": {{
      "body_type": string|null,
      "chassis_type": "Monocoque|Ladder|null"
    }},

    "suspension": {{
      "front": string|null,
      "rear": string|null,
      "adaptive": boolean|null,
      "air_suspension": boolean|null
    }},

    "braking": {{
      "front_brake": string|null,
      "rear_brake": string|null,
      "brake_material": "Steel|CarbonCeramic|null",
      "parking_brake": "Electric|Manual|null",
      "regen_braking": boolean|null
    }},

    "comfort": {{
      "seat_material": string|null,
      "seat_adjustment": string|null,
      "seat_heating": boolean|null,
      "seat_ventilation": boolean|null,
      "sunroof": boolean|null,
      "panoramic_roof": boolean|null
    }},

    "infotainment": {{
      "screen_size_inch": float|null,
      "android_auto": boolean|null,
      "apple_carplay": boolean|null,
      "wireless_projection": boolean|null,
      "speaker_brand": string|null,
      "speaker_count": int|null
    }},

    "safety": {{
      "airbag_count": int|null,
      "abs": boolean|null,
      "esc": boolean|null,
      "adas": [string]
    }}
  }}
]
"""

# =====================================================
# MAIN
# =====================================================
def main():
    if not PDF_DIR.exists():
        print(f"Folder PDF tidak ditemukan: {PDF_DIR}")
        return

    pdf_files = list(PDF_DIR.glob("*.pdf"))
    print(f"PDF ditemukan: {len(pdf_files)}")

    all_results = []
    failed_pdfs = []

    for pdf in pdf_files:
        print(f"[PDF] {pdf.name}")

        text = extract_text_from_pdf(str(pdf))
        if not text or len(text.strip()) < 50:
            failed_pdfs.append({
                "pdf": pdf.name,
                "error": "Teks kosong / terlalu pendek",
                "raw_preview": ""
            })
            continue

        prompt = build_user_prompt(text)

        try:
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )

            raw = res.choices[0].message.content.strip()
            data = json.loads(raw)

            for item in data:
                item["_source_pdf"] = pdf.name

            all_results.extend(data)

        except Exception as e:
            failed_pdfs.append({
                "pdf": pdf.name,
                "error": str(e),
                "raw_preview": raw[:300] if 'raw' in locals() else ""
            })

    # =================================================
    # SAVE OUTPUT
    # =================================================
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    with open(FAILED_LOG, "w", encoding="utf-8") as f:
        json.dump(failed_pdfs, f, indent=2, ensure_ascii=False)

    # =================================================
    # SUMMARY
    # =================================================
    print(f"\nSELESAI.")
    print(f"Total varian berhasil diekstrak : {len(all_results)}")
    print(f"Total PDF gagal diparse       : {len(failed_pdfs)}")

    if failed_pdfs:
        print("\nPDF GAGAL:")
        for i, err in enumerate(failed_pdfs, 1):
            print(f"{i}. {err['pdf']}")

if __name__ == "__main__":
    main()
