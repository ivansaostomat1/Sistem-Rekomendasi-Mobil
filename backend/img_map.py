# file: backend/img_map.py
# Merge cars_map.suggest.json -> public/cars_map.json
# Dengan pencocokan toleran: case-insensitive + canonical stem

from __future__ import annotations

import os
import re
import json
import argparse
from typing import Dict, Tuple

from .images import IMG_FS_DIR, IMG_EXTS, reload_images
try:
    # index internal dari images.py: {stem_lower: fileActual}
    from .images import _index_fs_lower as _fs_index_lower  # type: ignore
except Exception:
    _fs_index_lower = None  # type: ignore

# -------------------------------------------------------------------
#  PATH DASAR: hitung relatif terhadap root project
# -------------------------------------------------------------------

# .../Sistem-Rekomendasi-Mobil/backend/img_map.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

DEFAULT_SUGGEST_PATH = os.path.join(
    PROJECT_ROOT, "reports", "cars_map.suggest.json"
)
DEFAULT_OUT_PATH = os.path.join(
    PROJECT_ROOT, "public", "cars_map.json"
)


# ------------------ util dasar ------------------

def _load_json(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} bukan dict JSON")
    out: Dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str):
            kk = " ".join(k.split()).lower()
            out[kk] = v.strip()
    return out


def _save_json(path: str, obj: Dict[str, str]) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ------------------ kanonisasi stem ------------------

def _canon(s: str) -> str:
    """
    Samakan format supaya:
      - 'A7 AT' ~ 'A7AT'
      - '4 x 4' ~ '4x4'
      - 'CR-V' ~ 'crv'
      - 'e:HEV' ~ 'ehev'
    """
    s = str(s)
    s = s.replace("–", "-").replace("—", "-")

    # Normalisasi transmisi
    s = re.sub(
        r"(\d+)\s*([AM])\s*/\s*T\b",
        r"\1\2T",
        s,
        flags=re.IGNORECASE,
    )  # 8A/T -> 8AT
    s = re.sub(
        r"\b([AM])\s*/\s*T\b",
        r"\1T",
        s,
        flags=re.IGNORECASE,
    )  # A/T  -> AT
    s = re.sub(
        r"(\d+)\s*([AM])\s*T\b",
        r"\1\2T",
        s,
        flags=re.IGNORECASE,
    )  # 8 AT -> 8AT

    # 4x4, 4 X 4 -> 4x4
    s = re.sub(r"\b(\d+)\s*[xX]\s*(\d+)\b", r"\1x\2", s)

    # e:HEV / e-HEV / e HEV -> ehev ; e:PHEV -> ephev
    s = re.sub(r"\be\s*[:\-\s]*hev\b", "ehev", s, flags=re.IGNORECASE)
    s = re.sub(r"\be\s*[:\-\s]*phev\b", "ephev", s, flags=re.IGNORECASE)

    # CR-V -> crv
    s = re.sub(r"\bCR[-\s]?V\b", "crv", s, flags=re.IGNORECASE)

    # Hilangkan tanda yang sering bikin beda tapi tidak esensial
    s = re.sub(r"[()]+", " ", s)  # buang kurung
    s = s.replace(",", " ").replace(".", " ")  # koma/titik jadi spasi
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


# ------------------ index filesystem ------------------

def _build_file_indexes() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    returns:
      - files_by_lower: {filename_lower: filename_actual}
      - stems_by_lower: {stem_lower: filename_actual}
    """
    files_by_lower: Dict[str, str] = {}
    stems_by_lower: Dict[str, str] = {}

    if os.path.isdir(IMG_FS_DIR):
        allow = {e.lower() for e in IMG_EXTS}
        for fn in os.listdir(IMG_FS_DIR):
            stem, ext = os.path.splitext(fn)
            if ext.lower() not in allow:
                continue
            files_by_lower[fn.lower()] = fn
            s_lower = stem.lower()
            if s_lower not in stems_by_lower:
                stems_by_lower[s_lower] = fn

    # perkaya dari index internal images.py kalau ada
    if callable(_fs_index_lower):
        try:
            idx = _fs_index_lower()  # {stem_lower: fileActual}
            for s_lower, fn in idx.items():
                stems_by_lower.setdefault(s_lower, fn)
        except Exception:
            pass

    return files_by_lower, stems_by_lower


def _build_canon_index(stems_by_lower: Dict[str, str]) -> Dict[str, str]:
    """
    Map {canon(stem): fileActual}. Jika bentrok, pertahankan entri pertama.
    """
    out: Dict[str, str] = {}
    for s_lower, fn in stems_by_lower.items():
        c = _canon(s_lower)
        out.setdefault(c, fn)
    return out


# ------------------ resolver ------------------

def _resolve_actual_filename(
    suggest_file: str,
    files_by_lower: Dict[str, str],
    stems_by_lower: Dict[str, str],
    canon_to_actual: Dict[str, str],
    verbose: bool = False,
) -> str:
    """
    Urutan:
      1) cocokkan full filename (case-insensitive)
      2) cocokkan stem (case-insensitive)
      3) cocokkan canonical stem (toleran spasi/format)
    """
    if not suggest_file:
        return ""

    lf = suggest_file.strip().lower()

    # 1) langsung by filename
    if lf in files_by_lower:
        return files_by_lower[lf]

    # 2) by stem persis
    stem, _ext = os.path.splitext(lf)
    if stem in stems_by_lower:
        return stems_by_lower[stem]

    # 3) by canonical stem
    c = _canon(stem)
    if c in canon_to_actual:
        return canon_to_actual[c]

    if verbose:
        print(
            f"[MISS-V] '{suggest_file}' -> stem='{stem}' canon='{c}' (tidak ada kandidat)"
        )
    return ""


# ------------------ main ------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Apply cars_map.suggest.json ke public/cars_map.json "
        "(validasi & normalisasi)."
    )
    ap.add_argument(
        "--suggest",
        default=DEFAULT_SUGGEST_PATH,
        help=f"Path JSON saran map (default: {DEFAULT_SUGGEST_PATH})",
    )
    ap.add_argument(
        "--out",
        default=DEFAULT_OUT_PATH,
        help=f"Path output cars_map.json (default: {DEFAULT_OUT_PATH})",
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Timpa entri lama jika key sama (default: keep existing)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Hanya tampilkan ringkasan tanpa menulis file",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Tampilkan detail pencocokan yang MISS",
    )
    args = ap.parse_args()

    cnt = reload_images()
    print(f"[images] reindexed: {cnt}")
    print(f"[images] IMG_FS_DIR = {IMG_FS_DIR}")

    base_map = _load_json(args.out)        # bisa kosong
    suggest_map = _load_json(args.suggest) # hasil dari tes.py
    print(f"[map] existing: {len(base_map)} keys | suggest: {len(suggest_map)} keys")

    files_by_lower, stems_by_lower = _build_file_indexes()
    canon_to_actual = _build_canon_index(stems_by_lower)

    final_map: Dict[str, str] = dict(base_map)
    add_ok = 0
    add_skip_exist = 0
    add_missing = 0

    for key, file_suggest in suggest_map.items():
        # hormati entri lama kecuali --overwrite
        if key in final_map and not args.overwrite:
            add_skip_exist += 1
            continue

        actual = _resolve_actual_filename(
            file_suggest,
            files_by_lower,
            stems_by_lower,
            canon_to_actual,
            verbose=args.verbose,
        )
        if actual:
            final_map[key] = actual  # simpan nama file versi asli
            add_ok += 1
        else:
            add_missing += 1

    print("\n=== RINGKASAN MERGE ===")
    print(f"ditambahkan  : {add_ok}")
    print(f"skip existing: {add_skip_exist} (pakai --overwrite untuk timpa)")
    print(f"file missing : {add_missing} (saran tidak ditulis)")
    print(f"total output : {len(final_map)} keys")

    if args.dry_run:
        print("\n[dry-run] Tidak menulis file apa pun.")
        return

    _save_json(args.out, final_map)
    print(f"[OK] cars_map.json ditulis ke: {args.out}")


if __name__ == "__main__":
    main()
