"""VavaCars — istemci tarafında render edilen SPA; SeleniumBase (UC mode) gerektirir.

Kart metinleri sırası: ``[rozet?] başlık, paket, yıl, km, vites, yakıt, plaka, fiyat``.
Sınıf adlarına (Tailwind) değil metin kalıplarına göre ayrıştırılır. Kartta
"Boyasız, değişensiz, tramersiz" rozeti yoksa hasar durumu *bilinmiyor* sayılır.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup

from otogaleri.config import SITE_VAVACARS, get_settings
from otogaleri.damage import DamageReport, fold
from otogaleri.models import Listing
from otogaleri.scrapers._parsing import to_int
from otogaleri.scrapers.base import Scraper, SearchQuery

log = logging.getLogger(__name__)

BASE = "https://tr.vava.cars"
_HREF_RE = re.compile(r"^/buy/cars/([^/]+)/([^/]+)/([0-9a-fA-F-]{8,})/?$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_PLATE_RE = re.compile(r"^\d{2}[A-ZÇĞİÖŞÜ]{1,3}\d{2,4}$")


def page_url(query: SearchQuery) -> str:
    return f"{BASE}/buy/cars/{quote(query.brand)}" if query.has_brand else f"{BASE}/buy/cars"


def parse_list(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        m = _HREF_RE.match(href)
        if not m or m.group(3) in seen:
            continue
        seen.add(m.group(3))
        texts = list(a.stripped_strings)
        clean = bool(texts) and "boyasiz" in fold(texts[0])
        if clean:
            texts = texts[1:]
        brand, model = unquote(m.group(1)), unquote(m.group(2))
        year = next((to_int(t) for t in texts if _YEAR_RE.match(t)), 0)
        km = next((to_int(t) for t in texts if t.lower().endswith("km")), 0)
        price = next((to_int(t) for t in texts if "₺" in t or t.endswith("TL")), 0)
        title = texts[0] if texts else f"{brand} {model}"
        trim = texts[1] if len(texts) > 1 and not _YEAR_RE.match(texts[1]) else ""
        rest = [t for t in texts[2:] if not (_YEAR_RE.match(t) or _PLATE_RE.match(t))]
        transmission = next((t for t in rest if t in ("Otomatik", "Manuel", "Yarı Otomatik")), "")
        fuel = next((t for t in rest if t in ("Benzin", "Dizel", "Elektrik", "Hibrit", "LPG")), "")
        out.append(
            Listing(
                source_site=SITE_VAVACARS,
                listing_id=f"VV-{m.group(3)}",
                link=BASE + href,
                brand=brand,
                model=model,
                trim=trim,
                year=year,
                km=km,
                price=price,
                fuel=fuel,
                transmission=transmission,
                title=title,
                damage=(
                    DamageReport.all_original(
                        tramer=0, note="VavaCars: boyasız/değişensiz/tramersiz"
                    )
                    if clean
                    else None
                ),
            )
        )
    return out


class VavaCarsScraper(Scraper):
    site = SITE_VAVACARS
    requires_browser = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._ctx: Any = None
        self._sb: Any = None

    def _browser(self) -> Any:
        if self._sb is None:
            from seleniumbase import SB

            self._ctx = SB(uc=True, headless=True)
            self._sb = self._ctx.__enter__()
        return self._sb

    def search(self, query: SearchQuery) -> Iterator[Listing]:
        sb = self._browser()
        sb.uc_open_with_reconnect(page_url(query), 4)
        time.sleep(get_settings().selenium_wait_sec)
        items = parse_list(sb.get_page_source())
        if not items:
            log.warning("[%s] Sayfada ilan karti bulunamadi (yapi degismis olabilir).", self.site)
        yield from items

    def close(self) -> None:
        if self._ctx is not None:
            try:
                self._ctx.__exit__(None, None, None)
            except Exception:
                log.debug("Tarayici kapatilirken hata", exc_info=True)
        self._ctx = self._sb = None
