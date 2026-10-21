"""Sahibinden — gerçek (headless) Chrome ile liste + detay sayfası okuma.

sahibinden.com düz HTTP isteklerini Cloudflare doğrulamasıyla (403) karşılar; bu
yüzden VavaCars gibi SeleniumBase (UC mode) ile gerçek bir tarayıcı açılır ve sayfa
normal bir kullanıcı gibi, sayfalar arası bekleyerek okunur.

Kasıtlı sınırlar:

* Captcha **çözülmez**, proxy döndürülmez. Doğrulama sayfası gelirse tur o site için
  "hata" olarak kaydedilir ve bildirim gönderilir; bir sonraki turda yeniden denenir.
* Tur başına en fazla :attr:`SahibindenScraper.max_details` detay sayfası açılır ve
  her sayfa arasında birkaç saniye beklenir.

sahibinden.com kullanım şartları otomatik veri toplamayı kısıtlar; aracı kişisel
kullanım ölçeğinde ve düşük sıklıkta çalıştırmak kullanıcının sorumluluğundadır.

Yapı:

* Liste: ``tr.searchResultsItem`` — marka / seri / model / başlık / yıl / km / fiyat / il-ilçe
* Detay: ``div.car-parts > div.<parça> <durum>-new`` — 13 parçalık boya/değişen haritası,
  ``Ağır Hasar Kayıtlı`` alanı
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from otogaleri.config import ANY, SITE_SAHIBINDEN, get_settings
from otogaleri.damage import DamageReport, classify, normalize_part, slugify
from otogaleri.models import Listing
from otogaleri.scrapers._parsing import to_int
from otogaleri.scrapers.base import Scraper, SearchQuery

log = logging.getLogger(__name__)

BASE = "https://www.sahibinden.com"
PAGE_SIZE = 20
_ID_RE = re.compile(r"-(\d{7,12})/detay")


class SahibindenBlockedError(RuntimeError):
    """Cloudflare / bot doğrulama sayfası geldi (çözülmeye çalışılmaz)."""


def page_url(query: SearchQuery, page: int) -> str:
    path = "/otomobil"
    if query.has_brand:
        path = "/" + slugify(query.brand)
        if query.model and query.model != ANY:
            path += "-" + slugify(query.model)
    params: dict[str, object] = {"sorting": "date_desc"}
    if query.min_price:
        params["price_min"] = int(query.min_price)
    if query.max_price:
        params["price_max"] = int(query.max_price)
    if query.min_year:
        params["a5_min"] = query.min_year
    if query.max_year:
        params["a5_max"] = query.max_year
    if page > 1:
        params["pagingOffset"] = (page - 1) * PAGE_SIZE
    return f"{BASE}{path}?{urlencode(params)}"


#: Cloudflare doğrulaması ve PerimeterX/HUMAN "Access denied" engel sayfası işaretleri
_BLOCK_MARKERS = (
    "Just a moment",
    "cf-chl",
    "Attention Required",
    "Access to this page has been denied",
    "px-captcha",
    "_pxAppId",
)
#: Engel görüldükten sonra siteye hiç istek atılmayan süre (dakika)
BLOCK_COOLDOWN_MIN = 60
_blocked_until = 0.0


def is_challenge(html: str) -> bool:
    head = html[:8000]
    return any(marker in head for marker in _BLOCK_MARKERS)


def blocked_remaining_min() -> int:
    """Engel bekleme süresinden kalan dakika (0 → istek atılabilir)."""
    return max(0, int((_blocked_until - time.monotonic() + 59) // 60))


def _mark_blocked() -> None:
    global _blocked_until
    _blocked_until = time.monotonic() + BLOCK_COOLDOWN_MIN * 60


def parse_list(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    out: list[Listing] = []
    for row in soup.select("tr.searchResultsItem"):
        lid = row.get("data-id")
        link_el = row.select_one("a.classifiedTitle") or row.select_one('a[href*="/ilan/"]')
        if not lid or link_el is None:
            continue  # reklam / sponsorlu satır
        href = str(link_el.get("href") or "")
        tags = [
            td.get_text(" ", strip=True) for td in row.select("td.searchResultsTagAttributeValue")
        ]
        attrs = [
            td.get_text(" ", strip=True) for td in row.select("td.searchResultsAttributeValue")
        ]
        title_el = row.select_one("td.searchResultsTitleValue")
        price_el = row.select_one("td.searchResultsPriceValue")
        loc_el = row.select_one("td.searchResultsLocationValue")
        year = next((to_int(a) for a in attrs if re.fullmatch(r"(19|20)\d{2}", a)), 0)
        km = next((to_int(a) for a in attrs if re.fullmatch(r"[\d.]+", a) and to_int(a) != year), 0)
        out.append(
            Listing(
                source_site=SITE_SAHIBINDEN,
                listing_id=f"SB-{lid}",
                link=href if href.startswith("http") else BASE + href,
                brand=tags[0] if tags else "",
                model=tags[1] if len(tags) > 1 else "",
                trim=tags[2] if len(tags) > 2 else "",
                year=year,
                km=km,
                price=to_int(price_el.get_text(" ", strip=True)) if price_el else 0,
                location=loc_el.get_text(" ", strip=True) if loc_el else "",
                title=title_el.get_text(" ", strip=True) if title_el else "",
            )
        )
    return out


def parse_detail(html: str) -> DamageReport | None:
    soup = BeautifulSoup(html, "lxml")
    parts = soup.select("div.car-parts > div")
    report: DamageReport | None = None
    if parts:
        report = DamageReport(source_note="Sahibinden satıcı beyanı")
        for div in parts:
            classes = [str(c) for c in (div.get("class") or [])]
            part = next((p for c in classes if (p := normalize_part(c))), None)
            state = next((c for c in classes if c.endswith("-new")), None)
            if part and state:
                report.set(part, classify(state.removesuffix("-new")))
        if not report.parts:
            report = None
    for item in soup.select("div.classifiedInfoItem, ul.classifiedInfoList li"):
        label = item.find(["dt", "strong"])
        value = item.find(["dd", "span"])
        if label and value and "Ağır Hasar" in label.get_text():
            heavy = value.get_text(strip=True).lower().startswith("evet")
            report = report or DamageReport(source_note="Sahibinden satıcı beyanı")
            report.heavy_damage = heavy
    return report


class SahibindenScraper(Scraper):
    site = SITE_SAHIBINDEN
    requires_browser = True
    #: Siteyi yormamak için tur başına açılacak en fazla detay sayfası
    max_details = 6

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

    def _open(self, url: str) -> str:
        sb = self._browser()
        sb.uc_open_with_reconnect(url, 5)
        time.sleep(get_settings().selenium_wait_sec + random.uniform(0, 2))  # noqa: S311
        html = str(sb.get_page_source())
        if is_challenge(html):
            _mark_blocked()
            raise SahibindenBlockedError(
                "Sahibinden bot engeli/doğrulama sayfası gösterdi; "
                f"{BLOCK_COOLDOWN_MIN} dk boyunca istek atılmayacak."
            )
        return html

    def search(self, query: SearchQuery) -> Iterator[Listing]:
        if (left := blocked_remaining_min()) > 0:
            raise SahibindenBlockedError(
                f"Sahibinden engeli nedeniyle bekleniyor ({left} dk kaldı); tur atlandı."
            )
        for page in range(1, query.max_pages + 1):
            items = parse_list(self._open(page_url(query, page)))
            if not items:
                break
            yield from items
            if len(items) < PAGE_SIZE:
                break

    def enrich(self, listing: Listing) -> Listing:
        listing.damage = parse_detail(self._open(listing.link))
        return listing

    def close(self) -> None:
        if self._ctx is not None:
            try:
                self._ctx.__exit__(None, None, None)
            except Exception:
                log.debug("Tarayici kapatilirken hata", exc_info=True)
        self._ctx = self._sb = None
