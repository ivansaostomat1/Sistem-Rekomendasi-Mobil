# tes.py
# Cek kecocokan "type model" (dari data/daftar_mobil.json) dengan gambar di public/cars.
# - Menggunakan resolver dari images.py (find_best_image_url, find_image_by_type_model, reload_images)
# - Membuat laporan CSV dan file sugesti cars_map.suggest.json untuk yang "MISS"

import os
import sys
import json
import csv
import argparse
from typing import Any, Dict, List, Tuple

# --- impor dari images.py (wajib ada di PYTHONPATH yang sama dengan app.py) ---
try:
    from images import (
        find_best_image_url,
        find_image_by_type_model,
        reload_images,
        IMG_FS_DIR,
        IMG_BASE_REL,
    )
    # fungsi internal (kalau ada) agar laporan lebih kaya; aman jika tidak tersedia
    try:
        from images import _index_fs_lower as _fs_index_lower  # type: ignore
    except Exception:
        _fs_index_lower = None  # type: ignore
    try:
        from images import _variants_from_model as _variants  # type: ignore
    except Exception:
        _variants = None  # type: ignore
except Exception as e:
    print("[ERR] Gagal impor images.py. Pastikan file itu ada di path yang sama.")
    raise

# -------- util --------
def _ensure_dir(p: str) -> None:
    d = os.path.dirname(os.path.abspath(p))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def _load_json_records(path: str) -> List[Dict[str, Any]]:
    """Muat JSON list of objects. Jika JSONL/NDJSON, baca per baris."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Tidak menemukan file: {path}")
    # coba biasa (list)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "records" in data and isinstance(data["records"], list):
            return data["records"]
        else:
            # fallback: jika bukan list, coba treat sebagai JSONL
            raise ValueError("bukan list, coba JSONL")
    except Exception:
        # JSONL / NDJSON
        out: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out.append(obj)
                except Exception:
                    pass
        if out:
            return out
        raise ValueError(f"Format tidak dikenali untuk {path}. Harap berikan list JSON atau JSONL yang valid.")

def _pick_brand_model(rec: Dict[str, Any]) -> Tuple[str, str]:
    """Ambil brand & model dari berbagai kemungkinan kolom."""
    # brand candidates
    for k in ["brand", "merek", "merk"]:
        if k in rec and rec[k] is not None:
            b = str(rec[k]).strip()
            if b:
                break
    else:
        b = ""

    # model candidates (prioritas 'type model')
    for k in ["type model", "type_model", "type", "model"]:
        if k in rec and rec[k] is not None:
            m = str(rec[k]).strip()
            if m:
                break
    else:
        m = ""

    return b, m

def _split_url_filename(url: str) -> str:
    """Ambil nama file dari '/cars/xxx.jpg'."""
    try:
        return url.rsplit("/", 1)[-1]
    except Exception:
        return url

def _is_default(url: str) -> bool:
    return url.strip().lower().endswith("/default.jpg")

def _first_variant(model: str) -> str:
    """Ambil variant pertama sebagai saran nama file (tanpa ekstensi)."""
    if callable(_variants):
        try:
            vs = _variants(model)  # type: ignore
            if isinstance(vs, list) and vs:
                return vs[0]
        except Exception:
            pass
    # fallback minimal kalau fungsi internal tak tersedia
    s = str(model).replace("–", "-").replace("—", "-")
    s = s.replace("/", " ").replace("\\", " ")
    s = " ".join(s.split())
    return s

# -------- proses utama --------
def main():
    parser = argparse.ArgumentParser(description="Cek kecocokan gambar dengan type model.")
    parser.add_argument("--json", default=os.path.abspath("./data/daftar_mobil.json"),
                        help="Path ke data JSON (default: ./data/daftar_mobil.json)")
    parser.add_argument("--out", default=os.path.abspath("./reports/image_check.csv"),
                        help="Path output CSV laporan (default: ./reports/image_check.csv)")
    parser.add_argument("--miss", default=os.path.abspath("./reports/image_missing.csv"),
                        help="Path output CSV khusus yang MISS (default: ./reports/image_missing.csv)")
    parser.add_argument("--map", default=os.path.abspath("./reports/cars_map.suggest.json"),
                        help="Path output JSON sugesti cars_map.json (default: ./reports/cars_map.suggest.json)")
    parser.add_argument("--limit", type=int, default=0, help="Batasi jumlah baris yang dicek (0=semua)")
    args = parser.parse_args()

    # index ulang gambar (images.py akan memindai ./public/cars)
    reidx = reload_images()
    print(f"[images] reindexed: {reidx}")
    print(f"[images] IMG_FS_DIR: {IMG_FS_DIR}")

    # baca data
    recs = _load_json_records(args.json)
    if args.limit and args.limit > 0:
        recs = recs[: args.limit]
    print(f"[data] total record dibaca: {len(recs)}")

    # siapkan laporan
    _ensure_dir(args.out)
    _ensure_dir(args.miss)
    _ensure_dir(args.map)

    # coba index lower-case file (untuk info tambahan)
    fs_index = {}
    if callable(_fs_index_lower):
        try:
            fs_index = _fs_index_lower()  # type: ignore
        except Exception:
            fs_index = {}
    else:
        # fallback: bangun sendiri
        if os.path.isdir(IMG_FS_DIR):
            for fn in os.listdir(IMG_FS_DIR):
                stem, ext = os.path.splitext(fn)
                if ext.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    fs_index[stem.lower()] = fn

    rows: List[Dict[str, Any]] = []
    miss_rows: List[Dict[str, Any]] = []
    suggest_map: Dict[str, str] = {}

    total = 0
    ok_exact = 0
    ok_other = 0
    miss = 0

    for rec in recs:
        total += 1
        brand, model = _pick_brand_model(rec)
        if not model:
            status = "SKIP_NO_MODEL"
            rows.append({
                "brand": brand, "model": model,
                "exact_url": "", "best_url": "", "status": status,
                "matched_file": "", "note": "baris dilewati karena model kosong"
            })
            continue

        # 1) exact by model (varian di resolver)
        exact_url = find_image_by_type_model(model) or ""
        # 2) best (manual map / strip brand / default)
        best_url = find_best_image_url(brand, model) or ""

        # tentukan status
        if best_url and not _is_default(best_url):
            matched_file = _split_url_filename(best_url)
            if exact_url and exact_url == best_url:
                status = "OK_EXACT"
                ok_exact += 1
            else:
                status = "OK_RESOLVER"  # bisa manual-map atau strip-brand
                ok_other += 1
        else:
            status = "MISS"
            matched_file = ""
            miss += 1
            # buat sugesti nama file
            sug_stem = _first_variant(model)
            # pilih ekstensi default .jpg jika tidak ada di FS
            suggest_map[model.lower()] = f"{sug_stem}.jpg"

        rows.append({
            "brand": brand,
            "model": model,
            "exact_url": exact_url,
            "best_url": best_url,
            "status": status,
            "matched_file": matched_file,
            "note": "",
        })

        if status == "MISS":
            miss_rows.append(rows[-1])

    # tulis CSV lengkap
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            "brand","model","exact_url","best_url","status","matched_file","note"
        ])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # tulis CSV miss
    if miss_rows:
        with open(args.miss, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(miss_rows[0].keys()))
            w.writeheader()
            for r in miss_rows:
                w.writerow(r)

    # tulis sugesti cars_map.suggest.json
    with open(args.map, "w", encoding="utf-8") as f:
        json.dump(suggest_map, f, ensure_ascii=False, indent=2)

    # ringkasan
    print("\n=== RINGKASAN ===")
    print(f"Total   : {total}")
    print(f"OK exact: {ok_exact}")
    print(f"OK lain : {ok_other}  (manual-map / strip-brand)")
    print(f"MISS    : {miss}")
    print(f"- CSV lengkap : {args.out}")
    print(f"- CSV MISS    : {args.miss}")
    print(f"- Map sugesti : {args.map}")
    if miss > 0:
        print("\nCatatan:")
        print("- File 'cars_map.suggest.json' bisa disalin ke 'public/cars_map.json' lalu panggil /images/reload")
        print("- Atau, buat file gambar sesuai saran nama (stem pertama + .jpg) di public/cars")

if __name__ == "__main__":
    sys.exit(main())
