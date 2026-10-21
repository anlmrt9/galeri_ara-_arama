"""Tarama işçisi ve ``ScanManager`` cephesi.

Tarama artık web sürecinin bir thread'ine bağlı değil: UI ve API yalnızca
``scan_jobs`` tablosuna *istek* yazar, :class:`Worker` işi üstlenip yürütür.

* Ayrı süreç:  ``python -m otogaleri.worker`` (Docker Compose'daki ``worker`` servisi)
* Gömülü mod:  ``OTOGALERI_EMBEDDED_WORKER=true`` (varsayılan) — API/Streamlit süreci
  içinde tek bir daemon thread olarak çalışır; tek makinelik kurulum için yeterli.

İşler kalp atışıyla (heartbeat) sahiplenilir. Worker ölürse (süreç kapandı, makine
yeniden başladı) ``job_stale_after_sec`` sonra başka/yeniden başlayan bir worker işi
kaldığı yerden devralır. Aynı anda en fazla bir aktif iş bulunur.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from otogaleri.config import Settings, get_settings
from otogaleri.db import ACTIVE_STATUSES, Repository, create_db_engine, init_db, utcnow
from otogaleri.notifications import Notifier
from otogaleri.scan import CycleResult, ScanCriteria, ScanEngine, criteria_from_json

log = logging.getLogger(__name__)

EngineFactory = Callable[[Repository, Settings], ScanEngine]


def _default_engine_factory(repo: Repository, settings: Settings) -> ScanEngine:
    return ScanEngine(repo, Notifier(settings), settings)


class Worker:
    def __init__(
        self,
        repo: Repository,
        settings: Settings | None = None,
        *,
        engine_factory: EngineFactory = _default_engine_factory,
        worker_id: str | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings or get_settings()
        self.engine_factory = engine_factory
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._stale = timedelta(seconds=self.settings.job_stale_after_sec)
        self._last_beat = 0.0
        self._last_status: str | None = None

    # ---------- ana döngü ----------

    def run_forever(self, stop_event: threading.Event) -> None:
        log.info("[Worker %s] basladi.", self.worker_id)
        while not stop_event.is_set():
            try:
                job = self.repo.claim_job(self.worker_id, self._stale)
                if job:
                    self.run_job(job, stop_event)
                    continue
            except Exception:
                log.exception(
                    "[Worker] Beklenmedik hata; %ss sonra devam.", self.settings.worker_poll_sec
                )
            stop_event.wait(self.settings.worker_poll_sec)
        log.info("[Worker %s] durdu.", self.worker_id)

    def run_job(self, job: dict[str, Any], stop_event: threading.Event) -> None:
        job_id: str = job["id"]
        try:
            criteria = criteria_from_json(job["criteria_json"])
        except ValueError as exc:
            self.repo.finish_job(job_id, "failed", f"Gecersiz kriter: {exc}")
            return
        if not job.get("cycles"):
            self.repo.mark_all_seen()
        log.info("[Worker] Is %s yurutuluyor: %s", job_id[:8], criteria.summary())
        engine = self.engine_factory(self.repo, self.settings)
        cycles = int(job.get("cycles") or 0)
        found_total = int(job.get("found_total") or 0)
        ends_at: datetime = job["ends_at"]

        while True:
            status = self._beat(job_id, force=True)
            if status is None:
                log.warning("[Worker] Is %s sahipligi kaybedildi.", job_id[:8])
                return
            if status == "stop_requested":
                self.repo.finish_job(job_id, "stopped")
                log.info("[Worker] Is %s kullanici istegiyle durduruldu.", job_id[:8])
                return
            if status != "running":
                return
            if stop_event.is_set():
                return  # süreç kapanıyor: iş "running" kalır, yeniden başlayınca devralınır
            if utcnow() >= ends_at:
                self.repo.finish_job(job_id, "completed")
                log.info("[Worker] Is %s suresi doldu, tamamlandi.", job_id[:8])
                return

            def should_stop() -> bool:
                return stop_event.is_set() or self._beat(job_id) != "running"

            result = CycleResult()
            try:
                result = engine.run_cycle(job_id, criteria, should_stop)
            except Exception as exc:
                log.exception("[Worker] Tur hatasi")
                self.repo.heartbeat(job_id, self.worker_id, error=str(exc)[:500])

            cycles += 1
            found_total += result.new
            next_at = utcnow() + timedelta(seconds=criteria.interval_seconds(self.settings))
            self.repo.heartbeat(
                job_id,
                self.worker_id,
                cycles=cycles,
                last_cycle_at=utcnow(),
                next_cycle_at=next_at,
                last_cycle_seen=result.seen,
                last_cycle_matched=result.matched,
                last_cycle_new=result.new,
                found_total=found_total,
            )
            log.info(
                "[Worker] %d. tur bitti: %d ilan tarandi, %d uydu, %d yeni (toplam %d).",
                cycles,
                result.seen,
                result.matched,
                result.new,
                found_total,
            )
            if not self._wait_until(job_id, next_at, stop_event):
                continue  # durum değişti: döngü başı karar verir

    def _wait_until(self, job_id: str, until: datetime, stop_event: threading.Event) -> bool:
        """Bir sonraki tura kadar bekler; ``False`` → bekleme erken kesildi."""
        while (remaining := (until - utcnow()).total_seconds()) > 0:
            if stop_event.wait(min(remaining, 5.0)):
                return False
            if self._beat(job_id) != "running":
                return False
        return True

    def _beat(self, job_id: str, *, force: bool = False) -> str | None:
        """En fazla ~5 sn'de bir kalp atışı yazar; arada son bilinen durumu döndürür."""
        now = time.monotonic()
        if force or now - self._last_beat >= 5.0:
            self._last_status = self.repo.heartbeat(job_id, self.worker_id)
            self._last_beat = now
        return self._last_status


# ==========================================================================
#  CEPHE (UI / API)
# ==========================================================================


class ScanAlreadyRunningError(RuntimeError):
    """Zaten aktif bir tarama varken yenisi başlatılmaya çalışıldı."""


class ScanManager:
    """UI ve API'nin kullandığı ince katman: iş oluştur / durdur / durum oku."""

    def __init__(self, repo: Repository, settings: Settings | None = None) -> None:
        self.repo = repo
        self.settings = settings or get_settings()
        self._stale = timedelta(seconds=self.settings.job_stale_after_sec)
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._worker_stop = threading.Event()

    def start(self, criteria: ScanCriteria) -> str:
        with self._lock:
            active = self.repo.active_job()
            if active and not self._is_orphan(active):
                raise ScanAlreadyRunningError("Zaten aktif bir tarama var")
            if active:  # sahibi ölmüş eski iş: kapat
                self.repo.finish_job(active["id"], "stopped", "Sahipsiz kaldigi icin kapatildi")
            job_id = str(uuid.uuid4())
            ends_at = utcnow() + criteria.duration()
            self.repo.create_job(job_id, criteria.model_dump_json(), ends_at)
        if self.settings.embedded_worker:
            self.ensure_worker()
        log.info("[ScanManager] Is olusturuldu: %s (%s)", job_id[:8], criteria.summary())
        return job_id

    def stop(self) -> bool:
        active = self.repo.active_job()
        if not active:
            return False
        return self.repo.request_stop(active["id"], self._stale)

    def status(self) -> dict[str, Any]:
        job = self.repo.active_job() or self.repo.latest_job()
        if not job:
            return {"active": False}
        active = job["status"] in ACTIVE_STATUSES
        hb = job.get("heartbeat_at")
        try:
            criteria: dict[str, Any] | None = criteria_from_json(job["criteria_json"]).model_dump()
        except ValueError:
            criteria = None
        return {
            "active": active,
            "session_id": job["id"],
            "status": job["status"],
            "started_at": _iso(job.get("started_at") or job.get("created_at")),
            "ends_at": _iso(job.get("ends_at")),
            "finished_at": _iso(job.get("finished_at")),
            "cycles": job.get("cycles") or 0,
            "last_cycle_seen": job.get("last_cycle_seen") or 0,
            "last_cycle_matched": job.get("last_cycle_matched") or 0,
            "last_cycle_new": job.get("last_cycle_new") or 0,
            "found_total": job.get("found_total") or 0,
            "last_cycle_at": _iso(job.get("last_cycle_at")),
            "next_cycle_at": _iso(job.get("next_cycle_at")),
            "worker_alive": bool(hb and hb >= utcnow() - self._stale),
            "indefinite": bool(criteria and criteria.get("duration_hours") is None),
            "error": job.get("error"),
            "criteria": criteria,
        }

    def _is_orphan(self, job: dict[str, Any]) -> bool:
        if job["status"] == "pending":
            return False
        hb = job.get("heartbeat_at")
        return hb is None or hb < utcnow() - self._stale

    # ---------- gömülü worker ----------

    def ensure_worker(self) -> None:
        """Bu süreçte gömülü worker thread'i yoksa başlatır (idempotent)."""
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return
            self._worker_stop.clear()
            worker = Worker(self.repo, self.settings)
            self._worker_thread = threading.Thread(
                target=worker.run_forever,
                args=(self._worker_stop,),
                name="otogaleri-worker",
                daemon=True,
            )
            self._worker_thread.start()

    def shutdown(self, timeout: float = 10.0) -> None:
        self._worker_stop.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)


def _iso(value: datetime | None) -> str | None:
    """UTC → ISO 8601 (``Z`` sonekli) metin."""
    return value.isoformat() + "Z" if value else None


# ==========================================================================
#  BAĞIMSIZ SÜREÇ: python -m otogaleri.worker
# ==========================================================================


def main() -> None:
    from otogaleri.logging_setup import configure_logging

    configure_logging()
    settings = get_settings()
    engine = create_db_engine(settings)
    init_db(engine)
    stop = threading.Event()

    def _handle(signum: int, _frame: Any) -> None:
        log.info("Sinyal %s alindi, worker durduruluyor...", signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    Worker(Repository(engine), settings).run_forever(stop)


if __name__ == "__main__":
    main()
