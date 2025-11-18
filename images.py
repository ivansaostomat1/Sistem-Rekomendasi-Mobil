# images.py — exact + canonical manual map, case-insensitive FS, brand-strip, varian ekstra
import os, re, json
from functools import lru_cache
from typing import List, Dict, Optional

IMG_BASE_REL = "/cars"
IMG_FS_DIR = os.environ.get("IMG_FS_DIR", os.path.abspath("./public/cars"))
IMG_EXTS = [".jpg", ".jpeg", ".png", ".webp"]
IMG_EXTS_SET = {e.lower() for e in IMG_EXTS}

# ---------- util dasar ----------
def _norm_spaces(s: str) -> str:
    # rapikan whitespace jadi satu spasi (termasuk spasi ganda, tab, NBSP)
    return re.sub(r"\s+", " ", str(s)).strip()

def _collapse_all_new(s: str) -> str:
    # "All New ..." -> "Allnew ..." agar variasi nama lebih mudah
    return re.sub(r"\ball\s+new\b", "Allnew", str(s), flags=re.IGNORECASE)

def _safe_stem(s: str) -> str:
    """Normalisasi agresif untuk *model/file stem*:
       - satukan varian transmisi A/T -> AT, "8 A/T" -> "8AT", "8 AT" -> "8AT"
       - 4 X 4 / 4x4 -> 4x4
       - e:HEV/e-HEV -> eHEV; e:PHEV -> ePHEV
       - CR-V -> CRV
       - hilangkan pemecah path & karakter ilegal FS
       - rapikan spasi
    """
    s = str(s).replace("–", "-").replace("—", "-")

    # --- TRANSMISI ---
    s = re.sub(r"(\d+)\s*([AM])\s*/\s*T\b", r"\1\2T", s, flags=re.IGNORECASE)  # 8A/T -> 8AT
    s = re.sub(r"\b([AM])\s*/\s*T\b", r"\1T", s, flags=re.IGNORECASE)           # A/T  -> AT
    s = re.sub(r"(\d+)\s*([AM])\s*T\b", r"\1\2T", s, flags=re.IGNORECASE)       # 8 AT -> 8AT
    s = re.sub(r"\b([AM])\s+T\b", r"\1T", s, flags=re.IGNORECASE)               # A T  -> AT

    # --- 4x4 / 4 X 4 ---
    s = re.sub(r"\b(\d+)\s*[xX]\s*(\d+)\b", r"\1x\2", s)

    # --- e:HEV / e:PHEV ---
    s = re.sub(r"\be\s*[:\-\s]*hev\b",  "eHEV",  s, flags=re.IGNORECASE)
    s = re.sub(r"\be\s*[:\-\s]*phev\b", "ePHEV", s, flags=re.IGNORECASE)

    # --- CR-V -> CRV ---
    s = re.sub(r"\bCR[-\s]?V\b", "CRV", s, flags=re.IGNORECASE)

    # pemecah path & karakter ilegal
    s = s.replace("/", " ").replace("\\", " ")
    s = re.sub(r'[<>:"|?*]+', " ", s)

    return _norm_spaces(s)

def _canon_key(s: str) -> str:
    """Kanonisasi *kunci manual map*: gabungkan normalisasi seperti _safe_stem
       + hapus tanda baca non (word|.|-) agar '1,5' & '1.5' selaras.
    """
    s = _safe_stem(_norm_spaces(s).lower())
    # buang semua non-word kecuali '.' dan '-' (biar '1,5' vs '1.5' vs '1 5' seragam)
    s = re.sub(r"[^\w.\-]+", "", s)
    return s

# ---------- varian kandidat nama file ----------
def _variants_from_model(model: str) -> List[str]:
    s = _safe_stem(model)
    c = _collapse_all_new(s)
    bases = [s, s.lower(), c, c.lower()]
    out: List[str] = []
    seen = set()

    def add(x: str):
        if x and x not in seen:
            out.append(x); seen.add(x)

    for src in bases:
        add(src)
        add(re.sub(r"\s+", "_", src))
        add(re.sub(r"\s+", "-", src))
        add(re.sub(r"\s+", "", src))
        keep = re.sub(r"[^\w.\-]+", "", src)  # buang non word kecuali . dan -
        add(keep)
        no_dot = src.replace(".", "").replace(",", "")
        add(no_dot)
        add(re.sub(r"\s+", "_", no_dot))
        add(re.sub(r"\s+", "-", no_dot))
        add(re.sub(r"[^\w.\-]+", "", no_dot))

    return out

# ---------- index filesystem (case-insensitive) ----------
@lru_cache(maxsize=1)
def _index_fs_lower() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if os.path.isdir(IMG_FS_DIR):
        for fn in os.listdir(IMG_FS_DIR):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in IMG_EXTS_SET:
                out[stem.lower()] = fn
    return out

def _file_exists_for_stem(stem: str) -> Optional[str]:
    idx = _index_fs_lower()
    fn = idx.get(stem.lower())
    return f"{IMG_BASE_REL}/{fn}" if fn else None

# ---------- manual map ----------
@lru_cache(maxsize=1)
def _load_manual_map_raw() -> Dict[str, str]:
    """Muat public/cars_map.json (atau IMG_MODEL_MAP) -> {key_norm_lower: filename}."""
    MODEL_MAP_PATH = os.environ.get("IMG_MODEL_MAP", os.path.abspath("./public/cars_map.json"))
    out: Dict[str, str] = {}
    try:
        if os.path.exists(MODEL_MAP_PATH):
            with open(MODEL_MAP_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str):
                        out[_norm_spaces(k).lower()] = v.strip()
    except Exception:
        pass
    return out

@lru_cache(maxsize=1)
def _manual_map_canon() -> Dict[str, str]:
    """Turunan kanonis dari manual map: {canon_key: filename}."""
    raw = _load_manual_map_raw()
    out: Dict[str, str] = {}
    for k, v in raw.items():
        ck = _canon_key(k)
        if ck and ck not in out:
            out[ck] = v
    return out

def _manual_lookup(brand: str, model: str) -> Optional[str]:
    """Urutan:
       1) exact key:  'brand + model'  lalu 'model'
       2) canonical:  _canon_key(kandidat) cocok ke _manual_map_canon()
    """
    mp_raw = _load_manual_map_raw()
    mp_can = _manual_map_canon()

    # kandidat kunci
    cand = [
        _norm_spaces(f"{brand} {model}").lower(),
        _norm_spaces(model).lower(),
    ]
    # 1) exact
    for key in cand:
        fn = mp_raw.get(key)
        if fn:
            full = os.path.join(IMG_FS_DIR, fn)
            if os.path.exists(full):
                return f"{IMG_BASE_REL}/{fn}"
    # 2) canonical
    for key in cand:
        ck = _canon_key(key)
        fn = mp_can.get(ck)
        if fn:
            full = os.path.join(IMG_FS_DIR, fn)
            if os.path.exists(full):
                return f"{IMG_BASE_REL}/{fn}"
    return None

# ---------- resolver utama ----------
def find_image_by_type_model(model: str) -> Optional[str]:
    for stem in _variants_from_model(model):
        url = _file_exists_for_stem(stem)
        if url:
            return url
    return None

def _strip_brand_prefix(brand: str, model: str) -> str:
    b = _norm_spaces(brand).lower()
    m = _norm_spaces(model)
    if not b or not m:
        return model
    if m.lower().startswith(b + " "):
        return m[len(b) + 1 :].strip()
    return model

def find_best_image_url(brand: str, model: str) -> str:
    # 1) manual map (exact/canonical)
    url = _manual_lookup(brand or "", model or "")
    if url:
        return url
    # 2) exact by model penuh (varian stem)
    url = find_image_by_type_model(model or "")
    if url:
        return url
    # 3) exact tanpa prefix brand
    model_wo = _strip_brand_prefix(brand or "", model or "")
    if model_wo and model_wo != model:
        url = find_image_by_type_model(model_wo)
        if url:
            return url
    # 4) default
    return f"{IMG_BASE_REL}/default.jpg"

def reload_images():
    # kosongkan semua cache terkait
    _index_fs_lower.cache_clear()
    _load_manual_map_raw.cache_clear()
    _manual_map_canon.cache_clear()
    if not os.path.isdir(IMG_FS_DIR):
        return 0
    return sum(
        1 for n in os.listdir(IMG_FS_DIR)
        if os.path.splitext(n)[1].lower() in IMG_EXTS_SET
    )
