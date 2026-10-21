"""Arabam.com — liste: JSON-LD ``Vehicle`` dizisi; detay: ``window.damage`` + ``DamageInfo``.

Eski sürüm Selenium ile yalnızca ilk 3 ilana bakıyor, yıl/km alanlarına kullanıcının
*arama kriterini* yazıyordu (gerçek değer yerine). Artık her şey sayfadaki
yapılandırılmış veriden okunuyor ve tarayıcı gerekmiyor.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from urllib.parse import urlencode, urlparse

from otogaleri.config import SITE_ARABAM
from otogaleri.damage import DamageReport, DamageState, classify, normalize_part, slugify
from otogaleri.models import Listing
from otogaleri.scrapers._parsing import brand_name, humanize_slug, jsonld_vehicles, to_int
from otogaleri.scrapers.base import Scraper, SearchQuery

log = logging.getLogger(__name__)

BASE = "https://www.arabam.com"
_ID_RE = re.compile(r"/(\d{5,12})/?$")
_DAMAGE_RE = re.compile(r"window\.damage\s*=\s*(\[.*?\]);", re.S)
_DAMAGE_INFO_RE = re.compile(r'"DamageInfo"\s*:\s*(\{[^{}]*\})')


_slug = slugify


def page_url(query: SearchQuery, page: int) -> str:
    path = f"{BASE}/ikinci-el/otomobil"
    if query.has_brand:
        path += "/" + _slug(query.brand)
    params: dict[str, object] = {"take": 50, "sort": "startedAt.desc"}
    if query.min_year:
        params["minYear"] = query.min_year
    if query.max_year:
        params["maxYear"] = query.max_year
    if query.min_price:
        params["minPrice"] = int(query.min_price)
    if query.max_price:
        params["maxPrice"] = int(query.max_price)
    if page > 1:
        params["page"] = page
    return f"{path}?{urlencode(params)}"


def _model_from_url(link: str, brand: str) -> tuple[str, str]:
    """``/ilan/galeriden-satilik-ford-focus-1-6-ti-vct-titanium/...`` → (``Focus``, ``1 6 Ti Vct Titanium``)."""
    segments = urlparse(link).path.strip("/").split("/")
    if len(segments) < 2:
        return "", ""
    slug = segments[1].split("satilik-", 1)[-1]
    brand_slug = _slug(brand)
    if brand_slug and slug.startswith(brand_slug + "-"):
        slug = slug[len(brand_slug) + 1 :]
    head, _, rest = slug.partition("-")
    return humanize_slug(head), humanize_slug(rest)


def parse_list(html: str) -> list[Listing]:
    out: list[Listing] = []
    for item in jsonld_vehicles(html):
        offers = item.get("offers") or {}
        link = str(item.get("url") or offers.get("url") or "")
        m = _ID_RE.search(link)
        if not m:
            continue
        brand = brand_name(item.get("brand")) or brand_name(item.get("manufacturer"))
        model, trim = _model_from_url(link, brand)
        out.append(
            Listing(
                source_site=SITE_ARABAM,
                listing_id=f"AR-{m.group(1)}",
                link=link,
                brand=brand,
                model=model,
                trim=trim,
                year=to_int(item.get("vehicleModelDate")),
                km=to_int((item.get("mileageFromOdometer") or {}).get("value")),
                price=to_int(offers.get("price")),
                title=str(item.get("name") or "").strip(),
            )
        )
    return out


def parse_detail(html: str) -> DamageReport | None:
    report: DamageReport | None = None
    m = _DAMAGE_RE.search(html)
    if m:
        try:
            entries = json.loads(m.group(1))
        except json.JSONDecodeError:
            entries = []
        report = DamageReport(source_note="Arabam.com satıcı beyanı")
        for entry in entries:
            part = normalize_part(entry.get("Name"))
            if part is not None:
                report.set(part, classify(entry.get("ValueText") or entry.get("ValueDescription")))
        # Satıcı hiçbir parçayı belirtmemişse rapor "bilinmiyor" sayılır
        if all(s is DamageState.UNKNOWN for s in report.parts.values()):
            report.parts = {}
    info = _DAMAGE_INFO_RE.search(html)
    if info:
        try:
            data = json.loads(info.group(1))
        except json.JSONDecodeError:
            data = {}
        if report is None:
            report = DamageReport(source_note="Arabam.com satıcı beyanı")
        if "DamagePrice" in data:
            report.tramer = to_int(data.get("DamagePrice"))
    return report


class ArabamScraper(Scraper):
    site = SITE_ARABAM

    def search(self, query: SearchQuery) -> Iterator[Listing]:
        for page in range(1, query.max_pages + 1):
            items = parse_list(self.http.get_text(page_url(query, page)))
            if not items:
                break
            yield from items
            if len(items) < 50:
                break

    def enrich(self, listing: Listing) -> Listing:
        listing.damage = parse_detail(self.http.get_text(listing.link))
        return listing
