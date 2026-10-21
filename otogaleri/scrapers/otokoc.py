"""Otokoç 2. El — liste ve detay verisi Next.js flight akışında (``listing.results``,
``appearances``). Eski ``__NEXT_DATA__`` yapısı sitede artık yok."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from otogaleri.config import ANY, SITE_OTOKOC
from otogaleri.damage import DamageReport, classify, normalize_part, slugify
from otogaleri.http import ScraperHTTPError
from otogaleri.models import Listing
from otogaleri.scrapers._parsing import json_values_after, next_flight_text, to_int
from otogaleri.scrapers.base import Scraper, SearchQuery

log = logging.getLogger(__name__)

BASE = "https://www.otokocikinciel.com"


def page_url(query: SearchQuery, page: int) -> str:
    path = f"{BASE}/ikinci-el"
    if query.has_brand:
        path += "/" + slugify(query.brand)
    return path if page <= 1 else f"{path}?page={page}"


def _price(prices: Any) -> int:
    if isinstance(prices, list) and prices:
        retail = [
            p for p in prices if isinstance(p, dict) and p.get("pricingTypeName") == "RetailPrice"
        ]
        chosen = retail[0] if retail else prices[0]
        return to_int(chosen.get("price") if isinstance(chosen, dict) else None)
    if isinstance(prices, dict):
        return to_int(prices.get("cashPrice") or prices.get("price"))
    return 0


def parse_list(html: str) -> list[Listing]:
    out: list[Listing] = []
    for results in json_values_after(next_flight_text(html), '"results":['):
        for item in results:
            if not isinstance(item, dict) or "slug" not in item:
                continue
            spec = item.get("specifications") or {}
            out.append(
                Listing(
                    source_site=SITE_OTOKOC,
                    listing_id=f"OK-{item.get('id')}",
                    link=f"{BASE}/ilan/{item['slug']}",
                    brand=str(spec.get("make") or "").title(),
                    model=str(spec.get("model") or "").title(),
                    trim=str(spec.get("equipmentLevelName") or ""),
                    year=to_int(spec.get("modelYear")),
                    km=to_int(spec.get("mileages")),
                    price=_price(item.get("prices")),
                    location=str(item.get("cityName") or ""),
                    fuel=str(spec.get("fuelTypeName") or ""),
                    transmission=str(spec.get("transmissionTypeName") or ""),
                    title=str(item.get("advertName") or ""),
                )
            )
        if out:
            break
    return out


def parse_detail(html: str) -> DamageReport | None:
    """``appearances`` yalnızca kusurlu parçaları listeler; listede olmayan parça orijinaldir."""
    found = json_values_after(next_flight_text(html), '"appearances":[')
    if not found:
        return None
    report = DamageReport.all_original(note="Otokoç ekspertiz raporu")
    for entry in found[0]:
        if not isinstance(entry, dict):
            continue
        part = normalize_part(entry.get("partNameTR")) or normalize_part(entry.get("partNameEN"))
        if part is None:
            continue  # far, stop lambası, direk... kaporta haritası dışında
        report.set(part, classify(entry.get("damageNameEN") or entry.get("damageNameTR")))
    return report


class OtokocScraper(Scraper):
    site = SITE_OTOKOC

    def search(self, query: SearchQuery) -> Iterator[Listing]:
        try:
            first = self.http.get_text(page_url(query, 1))
        except ScraperHTTPError as exc:
            if exc.status != 404 or not query.has_brand:
                raise
            log.info("[%s] Marka sayfasi yok (%s), genel liste taranacak.", self.site, query.brand)
            query = replace(query, brand=ANY)
            first = self.http.get_text(page_url(query, 1))
        for page in range(1, query.max_pages + 1):
            html = first if page == 1 else self.http.get_text(page_url(query, page))
            items = parse_list(html)
            if not items:
                break
            yield from items

    def enrich(self, listing: Listing) -> Listing:
        listing.damage = parse_detail(self.http.get_text(listing.link))
        return listing
