"""
scan_service.py - Tarama Orkestrasyonu (paylaşımlı katman)
=========================================================
Streamlit arayüzü (``app.py``) ve REST API (``api.py``) aynı tarama döngüsünü
ve aynı kriter modelini buradan kullanır — mantık tek yerde durur.

İçerik:
    * ``ScanCriteria``   — tek kaynak (single source of truth) kriter modeli
    * ``run_scan_loop``  — süreli, durdurulabilir periyodik tarama döngüsü
    * ``ScanManager``    — thread + kilit + oturum durumu (API için)
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from config import ALL_SITES, settings
from db import mark_all_as_seen
from logger_setup import logger
from scrapers import run_one_cycle

# ---------- Kriter varsayılanları (app.py ve model tek yerden alır) ----------
DEFAULT_MIN_PRICE = 0.0
DEFAULT_MAX_PRICE = 999_999_999.0
DEFAULT_MIN_YEAR = 1970
DEFAULT_MAX_YEAR = 2030
DEFAULT_MIN_KM = 0.0
DEFAULT_MAX_KM = 1_000_000.0
DEFAULT_MAX_TRAMER = 999_999_999.0
DEFAULT_DURATION_HOURS = 24.0


class ScanCriteria(BaseModel):
    """Bir tarama oturumunun tüm parametreleri. Hem API gövdesi hem iç model."""

    sites: list[str] = Field(default_factory=lambda: list(ALL_SITES))
    brand: str = "Tümü"
    model: str = "Tümü"
    min_price: float = DEFAULT_MIN_PRICE
    max_price: float = DEFAULT_MAX_PRICE
    min_year: int = DEFAULT_MIN_YEAR
    max_year: int = DEFAULT_MAX_YEAR
    min_km: float = DEFAULT_MIN_KM
    max_km: float = DEFAULT_MAX_KM
    max_tramer: float = DEFAULT_MAX_TRAMER
    duration_hours: float = DEFAULT_DURATION_HOURS
    allowed_parts: list[str] = Field(default_factory=list)

    @field_validator("sites")
    @classmethod
    def _known_sites_only(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in ALL_SITES]
        if unknown:
            raise ValueError(f"Bilinmeyen site(ler): {unknown}. Geçerli: {ALL_SITES}")
        return v or list(ALL_SITES)

    @field_validator("duration_hours")
    @classmethod
    def _positive_duration(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("duration_hours 0'dan büyük olmalı")
        return v

    @model_validator(mode="after")
    def _ranges_ordered(self) -> ScanCriteria:
        if self.min_price > self.max_price:
            raise ValueError("min_price, max_price'tan büyük olamaz")
        if self.min_year > self.max_year:
            raise ValueError("min_year, max_year'tan büyük olamaz")
        if self.min_km > self.max_km:
            raise ValueError("min_km, max_km'tan büyük olamaz")
        return self

    @classmethod
    def from_optional(
        cls,
        *,
        sites: list[str] | None = None,
        brand: str | None = None,
        model: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        min_km: float | None = None,
        max_km: float | None = None,
        max_tramer: float | None = None,
        duration_hours: float | None = None,
        allowed_parts: list[str] | None = None,
    ) -> ScanCriteria:
        """``None`` gelen alanlara varsayılanı uygular (Streamlit formu için)."""
        return cls(
            sites=sites or list(ALL_SITES),
            brand=brand or "Tümü",
            model=model or "Tümü",
            min_price=DEFAULT_MIN_PRICE if min_price is None else min_price,
            max_price=DEFAULT_MAX_PRICE if max_price is None else max_price,
            min_year=DEFAULT_MIN_YEAR if min_year is None else min_year,
            max_year=DEFAULT_MAX_YEAR if max_year is None else max_year,
            min_km=DEFAULT_MIN_KM if min_km is None else min_km,
            max_km=DEFAULT_MAX_KM if max_km is None else max_km,
            max_tramer=DEFAULT_MAX_TRAMER if max_tramer is None else max_tramer,
            duration_hours=DEFAULT_DURATION_HOURS if duration_hours is None else duration_hours,
            allowed_parts=allowed_parts or [],
        )

    def to_scraper_dict(self) -> dict[str, Any]:
        """``run_one_cycle`` / scraper fonksiyonlarının beklediği düz sözlük."""
        return {
            "sites": list(self.sites),
            "brand": self.brand,
            "model": self.model,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "min_year": self.min_year,
            "max_year": self.max_year,
            "min_km": self.min_km,
            "max_km": self.max_km,
            "max_tramer": self.max_tramer,
            "duration": self.duration_hours,
            "allowed_parts": list(self.allowed_parts),
        }


def run_scan_loop(
    engine: Any,
    criteria: ScanCriteria,
    stop_event: threading.Event,
    session_id: str,
    *,
    label: str = "Scan",
) -> None:
    """``duration_hours`` boyunca ``stop_event`` set edilene kadar periyodik tarar.

    ``app.py`` ve ``api.py``'deki eski ``background_scan_thread``'lerin ortak gövdesi.
    """
    logger.info("[%s] Yeni tarama oturumu basladi: %s", label, session_id)
    scraper_criteria = criteria.to_scraper_dict()
    end_time = datetime.now() + timedelta(hours=criteria.duration_hours)

    mark_all_as_seen(engine)

    while datetime.now() < end_time:
        if stop_event.is_set():
            logger.info("[%s] Tarama stop_event ile durduruldu.", label)
            break
        try:
            run_one_cycle(engine, scraper_criteria, session_id=session_id)
        except Exception as exc:  # noqa: BLE001 - döngü tek bir çökme ile ölmesin
            logger.exception("[%s] run_one_cycle beklenmedik hata: %s", label, exc)
        stop_event.wait(timeout=settings.scraper_cycle_interval_sec)

    logger.info("[%s] Tarama dongusu tamamlandi.", label)


class ScanAlreadyRunningError(RuntimeError):
    """Zaten aktif bir tarama varken yeni tarama başlatılmaya çalışıldı."""


class ScanManager:
    """Tek seferde tek tarama çalıştıran thread yöneticisi (API için)."""

    def __init__(self, engine_provider: Callable[[], Any], *, label: str = "API") -> None:
        self._engine_provider = engine_provider
        self._label = label
        self._lock = threading.Lock()
        self._job: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            job = self._job
            if not job:
                return {"active": False}
            thread: threading.Thread = job["thread"]
            return {
                "active": thread.is_alive(),
                "session_id": job["session_id"],
                "started_at": job["started_at"].isoformat(),
            }

    def start(self, criteria: ScanCriteria) -> str:
        with self._lock:
            if self._job and self._job["thread"].is_alive():
                raise ScanAlreadyRunningError("Zaten aktif bir tarama var")

            engine = self._engine_provider()
            if engine is None:
                raise RuntimeError("Veritabanına bağlanılamadı")

            stop_event = threading.Event()
            session_id = str(uuid.uuid4())

            def _runner() -> None:
                try:
                    run_scan_loop(engine, criteria, stop_event, session_id, label=self._label)
                finally:
                    with self._lock:
                        if self._job and self._job["session_id"] == session_id:
                            self._job = None

            thread = threading.Thread(target=_runner, daemon=True, name=f"scan-{session_id[:8]}")
            self._job = {
                "session_id": session_id,
                "stop_event": stop_event,
                "started_at": datetime.now(),
                "thread": thread,
            }
            thread.start()
            return session_id

    def stop(self, *, timeout: float = 5.0) -> bool:
        """Aktif taramayı durdurur. Döndürdüğü değer: tarama aktif miydi."""
        with self._lock:
            job = self._job
            if not job:
                return False
            job["stop_event"].set()
            thread: threading.Thread = job["thread"]

        thread.join(timeout=timeout)
        with self._lock:
            self._job = None
        return True

    def shutdown(self) -> None:
        """Uygulama kapanışında çağrılır — çalışan taramayı nazikçe durdurur."""
        self.stop(timeout=10.0)
