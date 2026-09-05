"""
api.py - OtoGaleri Avcı Botu REST API
======================================
Mobil (Expo/React Native) uygulamanın konuştuğu FastAPI backend'i.
İş mantığı tamamen config.py/db.py/scrapers.py/notifications.py içinde;
bu dosya yalnızca ince bir HTTP katmanıdır. Streamlit arayüzü (app.py)
bu dosyadan bağımsız olarak, aynı veritabanı üzerinde çalışmaya devam eder.

Çalıştırma:
    python -m uvicorn api:app --host 0.0.0.0 --port 8000
"""

import math
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import ALL_SITES, SCRAPER_CYCLE_INTERVAL_SEC, CAR_CATALOG, DAMAGE_PARTS
from db import get_engine, init_tables, load_data, mark_all_as_seen, clear_all
from logger_setup import logger
from scrapers import run_one_cycle

ENGINE = None
SCAN_LOCK = threading.Lock()
SCAN_JOB: Optional[dict] = None  # {"session_id", "stop_event", "started_at", "thread"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ENGINE
    ENGINE = get_engine()
    if ENGINE:
        init_tables(ENGINE)
    yield


app = FastAPI(title="OtoGaleri Avcı Botu API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanCriteria(BaseModel):
    sites: list[str] = Field(default_factory=lambda: list(ALL_SITES))
    brand: str = "Tümü"
    model: str = "Tümü"
    min_price: float = 0
    max_price: float = 999999999
    min_year: int = 1970
    max_year: int = 2030
    min_km: float = 0
    max_km: float = 1000000
    max_tramer: float = 999999999
    duration_hours: float = 24.0
    allowed_parts: list[str] = Field(default_factory=list)


def background_scan_thread(engine, criteria, stop_event, session_id):
    """app.py'deki background_scan_thread ile aynı döngü (Streamlit'e bağımlı değil)."""
    logger.info(f"[API] Yeni tarama oturumu basladi: {session_id}")

    duration_hours = criteria["duration"]
    end_time = datetime.now() + timedelta(hours=duration_hours)

    mark_all_as_seen(engine)

    while datetime.now() < end_time:
        if stop_event.is_set():
            logger.info("[API] Tarama stop_event ile durduruldu.")
            break
        run_one_cycle(engine, criteria, session_id=session_id)
        stop_event.wait(timeout=SCRAPER_CYCLE_INTERVAL_SEC)

    logger.info("[API] Tarama dongusu tamamlandi.")
    with SCAN_LOCK:
        global SCAN_JOB
        if SCAN_JOB and SCAN_JOB.get("session_id") == session_id:
            SCAN_JOB = None


def _clean_value(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _serialize_listings(df):
    if df is None or df.empty:
        return []
    records = df.to_dict(orient="records")
    return [{k: _clean_value(v) for k, v in row.items()} for row in records]


@app.get("/api/health")
def health():
    return {"db_connected": ENGINE is not None}


@app.get("/api/config")
def get_config():
    return {
        "sites": ALL_SITES,
        "cycle_interval_sec": SCRAPER_CYCLE_INTERVAL_SEC,
        "catalog": CAR_CATALOG,
        "damage_parts": DAMAGE_PARTS,
    }


@app.get("/api/listings")
def get_listings():
    if not ENGINE:
        raise HTTPException(status_code=503, detail="Veritabanına bağlanılamadı")
    df = load_data(ENGINE)
    listings = _serialize_listings(df)
    new_count = sum(1 for row in listings if row.get("is_new_listing") in (1, True))
    return {"listings": listings, "total": len(listings), "new_count": new_count}


@app.delete("/api/listings")
def delete_listings():
    if not ENGINE:
        raise HTTPException(status_code=503, detail="Veritabanına bağlanılamadı")
    clear_all(ENGINE)
    return {"ok": True}


@app.get("/api/scan/status")
def scan_status():
    with SCAN_LOCK:
        if not SCAN_JOB:
            return {"active": False}
        return {
            "active": True,
            "session_id": SCAN_JOB["session_id"],
            "started_at": SCAN_JOB["started_at"].isoformat(),
        }


@app.post("/api/scan/start")
def scan_start(criteria: ScanCriteria):
    if not ENGINE:
        raise HTTPException(status_code=503, detail="Veritabanına bağlanılamadı")

    global SCAN_JOB
    with SCAN_LOCK:
        if SCAN_JOB is not None:
            raise HTTPException(status_code=409, detail="Zaten aktif bir tarama var")

        stop_event = threading.Event()
        session_id = str(uuid.uuid4())
        criteria_dict = {
            "sites": criteria.sites,
            "brand": criteria.brand,
            "model": criteria.model,
            "min_price": criteria.min_price,
            "max_price": criteria.max_price,
            "min_year": criteria.min_year,
            "max_year": criteria.max_year,
            "min_km": criteria.min_km,
            "max_km": criteria.max_km,
            "max_tramer": criteria.max_tramer,
            "duration": criteria.duration_hours,
            "allowed_parts": criteria.allowed_parts,
        }

        def runner():
            background_scan_thread(ENGINE, criteria_dict, stop_event, session_id)

        thread = threading.Thread(target=runner, daemon=True)
        SCAN_JOB = {
            "session_id": session_id,
            "stop_event": stop_event,
            "started_at": datetime.now(),
            "thread": thread,
        }
        thread.start()

    return {"session_id": session_id}


@app.post("/api/scan/stop")
def scan_stop():
    global SCAN_JOB
    with SCAN_LOCK:
        if not SCAN_JOB:
            return {"ok": True, "was_active": False}
        SCAN_JOB["stop_event"].set()
        SCAN_JOB = None
    return {"ok": True, "was_active": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
