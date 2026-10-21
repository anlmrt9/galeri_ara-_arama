"""REST API (FastAPI) — mobil uygulama ve diğer istemciler için ince HTTP katmanı.

Çalıştırma::

    uvicorn api:app --host 0.0.0.0 --port 8000      # veya: python -m otogaleri.api

Kimlik doğrulama (``require_auth``):

* ``OTOGALERI_API_KEY`` tanımlıysa korumalı uçlar ``X-API-Key`` başlığı ister
  (sabit-zamanlı karşılaştırma).
* Tanımlı değilse yalnızca aynı makineden (loopback) gelen istekler kabul edilir;
  yerel ağdan erişim için ya anahtar tanımlayın ya da bilinçli olarak
  ``OTOGALERI_API_ALLOW_UNAUTHENTICATED=true`` verin.

Uç sözleşmeleri 1.x mobil uygulamasıyla geriye uyumludur (``listings`` / ``total`` /
``new_count``, ``session_id`` / ``active`` ...); yeni alanlar yalnızca eklendi.
"""

from __future__ import annotations

import ipaddress
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from otogaleri import __version__
from otogaleri.config import (
    ALL_SITES,
    CAR_CATALOG,
    SITES,
    Settings,
    available_sites,
    get_settings,
    site_ready,
)
from otogaleri.damage import PARTS
from otogaleri.db import Repository, create_db_engine, init_db
from otogaleri.logging_setup import configure_logging
from otogaleri.scan import ScanCriteria
from otogaleri.scoring import annotate, build_reference
from otogaleri.worker import ScanAlreadyRunningError, ScanManager

log = logging.getLogger(__name__)

_state: dict[str, Any] = {"repo": None, "manager": None}


def _connect(settings: Settings) -> None:
    try:
        engine = create_db_engine(settings)
        init_db(engine)
    except Exception:
        log.exception("[API] Veritabanina baglanilamadi — korumali uclar 503 donecek.")
        return
    repo = Repository(engine)
    manager = ScanManager(repo, settings)
    _state.update(repo=repo, manager=manager)
    if settings.embedded_worker:
        manager.ensure_worker()  # yarım kalmış işi devral


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    if not settings.api_key and not settings.api_allow_unauthenticated:
        log.warning(
            "[API] OTOGALERI_API_KEY tanimli degil: yalnizca localhost istekleri kabul edilecek."
        )
    if _state["repo"] is None:
        _connect(settings)
    try:
        yield
    finally:
        if _state["manager"] is not None:
            _state["manager"].shutdown()


app = FastAPI(
    title="OtoGaleri Avcı Botu API",
    version=__version__,
    lifespan=lifespan,
    description="İkinci el araç ilanı tarama botunun REST arayüzü.",
)

_cors = get_settings().cors_origin_list
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )


# ==========================================================================
#  MIDDLEWARE: hız sınırı + güvenlik başlıkları
# ==========================================================================


class RateLimiter:
    """İstemci IP'si başına kayan pencereli (60 sn) basit hız sınırlayıcı."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


_limiter = RateLimiter(get_settings().api_rate_limit_per_minute)


@app.middleware("http")
async def _guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    client = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/api/") and not _limiter.allow(client):
        return JSONResponse({"detail": "Çok fazla istek, lütfen biraz bekleyin."}, status_code=429)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# ==========================================================================
#  BAĞIMLILIKLAR
# ==========================================================================


def _is_loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def require_auth(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.api_key:
        if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz veya eksik API anahtarı")
        return
    if settings.api_allow_unauthenticated:
        return
    if not _is_loopback(request.client.host if request.client else None):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "API anahtarı tanımlı değil; uzaktan erişim için OTOGALERI_API_KEY ayarlayın.",
        )


def require_repo() -> Repository:
    repo = _state["repo"]
    if repo is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Veritabanına bağlanılamadı")
    return repo


def require_manager(_: Repository = Depends(require_repo)) -> ScanManager:
    return _state["manager"]


# ==========================================================================
#  UÇLAR
# ==========================================================================


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() + "Z" if hasattr(v, "isoformat") else v) for k, v in row.items()}


@app.get("/api/health", tags=["sistem"])
def health() -> dict[str, Any]:
    repo: Repository | None = _state["repo"]
    manager: ScanManager | None = _state["manager"]
    settings = get_settings()
    return {
        "version": __version__,
        "db_connected": bool(repo and repo.ping()),
        "auth": (
            "api_key"
            if settings.api_key
            else ("open" if settings.api_allow_unauthenticated else "localhost")
        ),
        "scan_active": bool(manager and manager.status().get("active")),
    }


@app.get("/api/config", tags=["sistem"])
def get_config() -> dict[str, Any]:
    settings = get_settings()
    return {
        "sites": available_sites(),
        "site_details": [
            {
                "name": s.name,
                "enabled": s.enabled,
                "requires_browser": s.requires_browser,
                "ready": site_ready(s.name),
                "note": s.note,
            }
            for s in SITES
        ],
        "cycle_interval_sec": settings.cycle_interval_sec,
        "catalog": CAR_CATALOG,
        # 1.x mobil uygulaması "scraper_key" alanını allowed_parts'a gönderiyor; artık
        # kanonik kimlik de etiket de kabul edildiğinden scraper_key = id.
        "damage_parts": [{"id": pid, "label": label, "scraper_key": pid} for pid, label in PARTS],
    }


@app.get("/api/listings", tags=["ilanlar"], dependencies=[Depends(require_auth)])
def get_listings(
    repo: Repository = Depends(require_repo),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    site: str | None = Query(None),
    only_new: bool = Query(False),
) -> dict[str, Any]:
    rows = repo.list_listings(limit=limit, offset=offset, site=site, only_new=only_new)
    annotate(rows, build_reference(repo.list_listings()))
    return {
        "listings": [_jsonable(r) for r in rows],
        "total": repo.count_listings(site=site, only_new=only_new),
        "new_count": repo.count_listings(only_new=True),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/listings/{pk}/price-history", tags=["ilanlar"], dependencies=[Depends(require_auth)])
def price_history(pk: int, repo: Repository = Depends(require_repo)) -> dict[str, Any]:
    return {"listing_id": pk, "history": [_jsonable(r) for r in repo.get_price_history(pk)]}


@app.delete("/api/listings", tags=["ilanlar"], dependencies=[Depends(require_auth)])
def delete_listings(repo: Repository = Depends(require_repo)) -> dict[str, Any]:
    deleted = repo.clear_listings()
    log.warning("[API] Tum ilanlar silindi (%d kayit).", deleted)
    return {"ok": True, "deleted": deleted}


@app.get("/api/stats", tags=["sistem"], dependencies=[Depends(require_auth)])
def stats(repo: Repository = Depends(require_repo)) -> dict[str, Any]:
    return {
        "total": repo.count_listings(),
        "new": repo.count_listings(only_new=True),
        "per_site": {s: repo.count_listings(site=s) for s in ALL_SITES},
        "site_health": {k: _jsonable(v) for k, v in repo.latest_site_runs().items()},
    }


@app.get("/api/scan/status", tags=["tarama"], dependencies=[Depends(require_auth)])
def scan_status(manager: ScanManager = Depends(require_manager)) -> dict[str, Any]:
    return manager.status()


@app.post("/api/scan/start", tags=["tarama"], dependencies=[Depends(require_auth)])
def scan_start(
    criteria: ScanCriteria, manager: ScanManager = Depends(require_manager)
) -> dict[str, str]:
    try:
        return {"session_id": manager.start(criteria)}
    except ScanAlreadyRunningError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@app.post("/api/scan/stop", tags=["tarama"], dependencies=[Depends(require_auth)])
def scan_stop(manager: ScanManager = Depends(require_manager)) -> dict[str, bool]:
    was_active = manager.stop()
    return {"ok": True, "was_active": was_active}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
