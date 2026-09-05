"""
api.py - OtoGaleri Avcı Botu REST API
======================================
Mobil (Expo/React Native) uygulamanın konuştuğu FastAPI backend'i.
İş mantığı config.py / db.py / scrapers.py / scan_service.py içinde;
bu dosya yalnızca ince bir HTTP katmanıdır. Streamlit arayüzü (app.py)
bu dosyadan bağımsız olarak, aynı veritabanı üzerinde çalışır.

Çalıştırma:
    python -m uvicorn api:app --host 0.0.0.0 --port 8000

Kimlik doğrulama:
    OTOGALERI_API_KEY tanımlıysa yazma uçları (start/stop/temizle) ve liste
    uçları ``X-API-Key`` başlığını zorunlu kılar. Boşsa auth kapalıdır
    (yalnızca güvenli yerel ağ senaryosu için).
"""

from __future__ import annotations

import math
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import CAR_CATALOG, DAMAGE_PARTS, settings
from db import clear_all, get_engine, init_tables, load_data
from logger_setup import logger
from scan_service import ScanAlreadyRunningError, ScanCriteria, ScanManager

_state: dict[str, Any] = {"engine": None}


def _get_engine() -> Any:
    return _state["engine"]


scan_manager = ScanManager(_get_engine, label="API")


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine = get_engine()
    _state["engine"] = engine
    if engine:
        init_tables(engine)
    else:
        logger.error("[API] Veritabani baglantisi kurulamadi — uclar 503 donecek.")
    try:
        yield
    finally:
        scan_manager.shutdown()


app = FastAPI(title="OtoGaleri Avcı Botu API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ==========================================================================
#  KİMLİK DOĞRULAMA
# ==========================================================================


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """OTOGALERI_API_KEY tanımlıysa ``X-API-Key`` başlığını doğrular."""
    expected = settings.api_key
    if not expected:
        return  # auth kapalı
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz veya eksik API anahtarı"
        )


def require_engine() -> Any:
    engine = _state["engine"]
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Veritabanına bağlanılamadı"
        )
    return engine


# ==========================================================================
#  YARDIMCILAR
# ==========================================================================


def _clean_value(v: Any) -> Any:
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _serialize_listings(df: Any) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return [{k: _clean_value(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


# ==========================================================================
#  UÇLAR
# ==========================================================================


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"db_connected": _state["engine"] is not None}


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return {
        "sites": list(ScanCriteria().sites),
        "cycle_interval_sec": settings.scraper_cycle_interval_sec,
        "catalog": CAR_CATALOG,
        "damage_parts": DAMAGE_PARTS,
    }


@app.get("/api/listings", dependencies=[Depends(require_api_key)])
def get_listings(engine: Any = Depends(require_engine)) -> dict[str, Any]:
    listings = _serialize_listings(load_data(engine))
    new_count = sum(1 for row in listings if row.get("is_new_listing") in (1, True))
    return {"listings": listings, "total": len(listings), "new_count": new_count}


@app.delete("/api/listings", dependencies=[Depends(require_api_key)])
def delete_listings(engine: Any = Depends(require_engine)) -> dict[str, bool]:
    clear_all(engine)
    return {"ok": True}


@app.get("/api/scan/status", dependencies=[Depends(require_api_key)])
def scan_status() -> dict[str, Any]:
    return scan_manager.status()


@app.post("/api/scan/start", dependencies=[Depends(require_api_key)])
def scan_start(criteria: ScanCriteria, _: Any = Depends(require_engine)) -> dict[str, str]:
    try:
        session_id = scan_manager.start(criteria)
    except ScanAlreadyRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return {"session_id": session_id}


@app.post("/api/scan/stop", dependencies=[Depends(require_api_key)])
def scan_stop() -> dict[str, bool]:
    was_active = scan_manager.stop()
    return {"ok": True, "was_active": was_active}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
