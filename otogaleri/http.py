"""Scraper'ların ortak HTTP istemcisi.

* ``curl_cffi`` ile tarayıcı TLS parmak izi taklidi (bot korumalarına takılmamak için)
* Ağ hatası / 5xx → üstel geri çekilmeli (exponential backoff) yeniden deneme
* 429 → ``Retry-After`` başlığına uyarak bekleme
* 403 / 404 → yeniden denemeden anında :class:`ScraperHTTPError` (blok / yapı değişti)
* İstekler arası asgari bekleme (siteleri yormamak için)
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from otogaleri.config import Settings, get_settings

log = logging.getLogger(__name__)

_NO_RETRY_STATUSES = {400, 401, 403, 404, 410}


class ScraperHTTPError(RuntimeError):
    """Sayfa getirilemedi. ``status`` ağ hatasında ``None``'dır."""

    def __init__(self, url: str, status: int | None, message: str = "") -> None:
        self.url = url
        self.status = status
        super().__init__(message or f"HTTP {status} — {url}")


class _Response(Protocol):
    status_code: int
    text: str
    headers: Any


class _Session(Protocol):
    def get(self, url: str, **kwargs: Any) -> _Response: ...


def _default_session() -> _Session:
    from curl_cffi import requests as cf

    return cf.Session()


class HttpClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session_factory: Callable[[], _Session] = _default_session,
        sleep: Callable[[float], None] = time.sleep,
        impersonate: str = "chrome",
    ) -> None:
        self.settings = settings or get_settings()
        self._session_factory = session_factory
        self._session: _Session | None = None
        self._sleep = sleep
        self._impersonate = impersonate
        self._last_request = 0.0
        self._lock = threading.Lock()

    @property
    def session(self) -> _Session:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    def _throttle(self) -> None:
        gap = self.settings.request_min_interval_sec - (time.monotonic() - self._last_request)
        if gap > 0:
            self._sleep(gap)
        self._last_request = time.monotonic()

    def get_text(self, url: str) -> str:
        """URL'yi getirir ve gövdeyi döndürür; kalıcı hatada :class:`ScraperHTTPError`."""
        attempts = max(1, self.settings.retry_max_attempts)
        last_error: ScraperHTTPError | None = None
        with self._lock:
            for attempt in range(attempts):
                self._throttle()
                try:
                    resp = self.session.get(
                        url, impersonate=self._impersonate, timeout=self.settings.request_timeout
                    )
                except Exception as exc:  # noqa: BLE001 - curl_cffi ağ hataları tek tip değil
                    last_error = ScraperHTTPError(url, None, f"Ağ hatası: {exc}")
                else:
                    if resp.status_code == 200:
                        return resp.text
                    last_error = ScraperHTTPError(url, resp.status_code)
                    if resp.status_code in _NO_RETRY_STATUSES:
                        raise last_error
                    if resp.status_code == 429:
                        wait = _retry_after(resp) or 30.0
                        log.warning("HTTP 429 (rate limit) — %.0fs bekleniyor: %s", wait, url)
                        self._sleep(wait)
                        continue
                if attempt < attempts - 1:
                    wait = self.settings.retry_backoff_factor**attempt
                    log.warning(
                        "Istek basarisiz (%d/%d), %.1fs sonra tekrar: %s",
                        attempt + 1,
                        attempts,
                        wait,
                        last_error,
                    )
                    self._sleep(wait)
        raise last_error or ScraperHTTPError(url, None, "İstek yapılamadı")


def _retry_after(resp: _Response) -> float | None:
    try:
        value = resp.headers.get("Retry-After")
        return min(float(value), 300.0) if value else None
    except (TypeError, ValueError, AttributeError):
        return None
