"""Otoplus — liste: JSON-LD ``Vehicle``; detay: Next.js flight verisindeki ``inspection``."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote, urlparse

from otogaleri.config import SITE_OTOPLUS
from otogaleri.damage import DamageReport, classify, normalize_part, worst
from otogaleri.models import Listing
from otogaleri.scrapers._parsing import (
    brand_name,
    humanize_slug,
    json_values_after,
    jsonld_vehicles,
    next_flight_text,
    to_int,
)
from otogaleri.scrapers.base import Scraper, SearchQuery

log = logging.getLogger(__name__)

BASE = "https://www.otoplus.com"
LIST_URL = f"{BASE}/ikinci-el-araba"
_ID_RE = re.compile(r"-(\d{4,9})/?$")


def page_url(page: int) -> str:
    # Marka bazlı alt sayfalar (/ikinci-el-araba/ford) artık 404 dönüyor; genel liste
    # taranıp marka/model filtresi yerelde uygulanıyor.
    return LIST_URL if page <= 1 else f"{LIST_URL}?sayfa={page}"


def parse_list(html: str) -> list[Listing]:
    out: list[Listing] = []
    for item in jsonld_vehicles(html):
        offers = item.get("offers") or {}
        link = str(offers.get("url") or item.get("url") or "")
        m = _ID_RE.search(link)
        if not m:
            continue
        brand = brand_name(item.get("brand")) or brand_name(item.get("manufacturer"))
        # URL: /<marka>/<model>/<paket>/<açıklama>-<id>
        segments = [unquote(s) for s in urlparse(link).path.strip("/").split("/")]
        model = humanize_slug(segments[1]) if len(segments) >= 3 else ""
        trim = humanize_slug(segments[2]) if len(segments) >= 4 else ""
        engine: dict[str, Any] = item.get("vehicleEngine") or {}
        out.append(
            Listing(
                source_site=SITE_OTOPLUS,
                listing_id=f"OP-{m.group(1)}",
                link=link,
                brand=brand,
                model=model,
                trim=trim,
                year=to_int(item.get("vehicleModelDate")),
                km=to_int((item.get("mileageFromOdometer") or {}).get("value")),
                price=to_int(offers.get("price")),
                fuel=str(engine.get("fuelType") or ""),
                transmission=str(item.get("vehicleTransmission") or ""),
                title=str(item.get("name") or ""),
            )
        )
    return out


def parse_detail(html: str) -> DamageReport | None:
    """``inspection.report.carExterior`` → parça bazlı rapor. Tramer bilgisi sitede yok."""
    flight = next_flight_text(html)
    inspections = json_values_after(flight, '"inspection":{')
    for inspection in inspections:
        report = (inspection or {}).get("report") or {}
        exterior = report.get("carExterior") or {}
        entries = [e for group in exterior.values() if isinstance(group, list) for e in group]
        if not entries:
            continue
        result = DamageReport(source_note="Otoplus ekspertiz raporu")
        for entry in entries:
            part = normalize_part(entry.get("code")) or normalize_part(entry.get("location"))
            if part is None:
                continue
            types = entry.get("damageType") or []
            result.set(part, worst(classify(t) for t in types) if types else classify(None))
        if result.parts:
            return result
    return None


class OtoplusScraper(Scraper):
    site = SITE_OTOPLUS

    def search(self, query: SearchQuery) -> Iterator[Listing]:
        for page in range(1, query.max_pages + 1):
            items = parse_list(self.http.get_text(page_url(page)))
            if not items:
                break
            yield from items

    def enrich(self, listing: Listing) -> Listing:
        listing.damage = parse_detail(self.http.get_text(listing.link))
        if listing.damage is None:
            log.info("[%s] Ekspertiz verisi bulunamadi: %s", self.site, listing.link)
        return listing
