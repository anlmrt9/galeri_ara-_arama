"""Site scraper'ları ve kayıt defteri."""

from __future__ import annotations

from otogaleri.config import (
    SITE_ARABAM,
    SITE_OTOKOC,
    SITE_OTOPLUS,
    SITE_SAHIBINDEN,
    SITE_VAVACARS,
)
from otogaleri.http import HttpClient, ScraperHTTPError
from otogaleri.scrapers.arabam import ArabamScraper
from otogaleri.scrapers.base import Scraper, SearchQuery
from otogaleri.scrapers.otokoc import OtokocScraper
from otogaleri.scrapers.otoplus import OtoplusScraper
from otogaleri.scrapers.sahibinden import SahibindenScraper
from otogaleri.scrapers.vavacars import VavaCarsScraper

REGISTRY: dict[str, type[Scraper]] = {
    SITE_OTOPLUS: OtoplusScraper,
    SITE_OTOKOC: OtokocScraper,
    SITE_ARABAM: ArabamScraper,
    SITE_VAVACARS: VavaCarsScraper,
    SITE_SAHIBINDEN: SahibindenScraper,
}


def build_scraper(site: str, http: HttpClient | None = None) -> Scraper:
    try:
        cls = REGISTRY[site]
    except KeyError:
        raise ValueError(f"Desteklenmeyen site: {site}") from None
    return cls(http)


__all__ = [
    "REGISTRY",
    "HttpClient",
    "Scraper",
    "ScraperHTTPError",
    "SearchQuery",
    "build_scraper",
]
