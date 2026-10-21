"""Scraper'lar ile veritabanı arasında dolaşan ilan modeli."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from otogaleri.damage import DamageReport, DamageState


@dataclass
class Listing:
    """Tek bir ilan. Liste sayfasından gelen özet hâlinde ``damage`` boş olabilir;
    ``Scraper.enrich`` detay sayfasından hasar/tramer bilgisini doldurur."""

    source_site: str
    listing_id: str
    link: str
    brand: str = ""
    model: str = ""
    trim: str = ""
    year: int = 0
    km: int = 0
    price: int = 0
    location: str = ""
    fuel: str = ""
    transmission: str = ""
    title: str = ""
    damage: DamageReport | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_site, self.listing_id)

    @property
    def display_name(self) -> str:
        return " ".join(p for p in (self.brand, self.model, self.trim) if p).strip() or self.title

    @property
    def tramer(self) -> int | None:
        return self.damage.tramer if self.damage else None

    def damage_columns(self) -> dict[str, Any]:
        """``painted_parts`` / ``changed_parts`` metin sütunları (geriye uyumlu)."""
        if self.damage is None:
            return {"painted_parts": "Bilinmiyor", "changed_parts": "Bilinmiyor"}
        return {
            "painted_parts": self.damage.label(DamageState.PAINTED),
            "changed_parts": self.damage.label(DamageState.CHANGED),
        }
