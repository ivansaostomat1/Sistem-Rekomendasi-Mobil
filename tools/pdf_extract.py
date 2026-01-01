# tools/pdf_extract.py
from __future__ import annotations
import pdfplumber


def extract_text_from_pdf(path: str) -> str:
    """
    Ekstrak SEMUA teks dari PDF apa adanya.
    Tidak melakukan interpretasi.
    """
    text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)

    return "\n".join(text).strip()
