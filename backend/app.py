# file: backend/app.py
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .images import reload_images
from .meta_routes import router as meta_router
from .recommend_routes import router as recommend_router
from .chat_routes import router as chat_router

load_dotenv()

app = FastAPI(title="Rekomendasi Mobil API (JSON)", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reindeks gambar saat start
print(f"[images] reindexed:", reload_images())


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


# Daftarkan router-routes
app.include_router(meta_router)
app.include_router(recommend_router)
app.include_router(chat_router)
