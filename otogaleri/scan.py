"""Tarama kriterleri ve tek tur tarama motoru.

Bir tur, seçili her site için şu adımları izler:

1. Liste sayfalarından ilan özetleri (``Scraper.search``)
2. Temel filtre: marka / model / fiyat / yıl / km
3. Zaten kayıtlı ilanlar → yalnızca fiyat/son görülme güncellemesi (fiyat düşüşü bildirimi)
4. Yeni ilanlar → detay sayfası (hasar/tramer) → hasar politikası → kayıt + bildirim
5. Site sonucu ``site_runs`` tablosuna yazılır; site hatası bildirim gönderir
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from otogaleri.config import (
    ALL_SITES,
    ANY,
    Settings,
    available_sites,
    get_settings,
    site_info,
    site_ready,
)
from otogaleri.damage import DamagePolicy, evaluate, fold, normalize_part
from otogaleri.db import Repository, utcnow
from otogaleri.http import HttpClient
from otogaleri.models import Listing
from otogaleri.notifications import NewListing, Notifier, PriceDrop, SiteFailure
from otogaleri.scoring import MarketReference, build_reference
from otogaleri.scrapers import Scraper, SearchQuery, build_scraper

log = logging.getLogger(__name__)

DEFAULT_MAX_PRICE = 999_999_999.0
DEFAULT_MIN_YEAR = 1970
DEFAULT_MAX_YEAR = 2030
DEFAULT_MAX_KM = 1_000_000.0
DEFAULT_MAX_TRAMER = 999_999_999.0
DEFAULT_DURATION_HOURS = 24.0
MAX_DURATION_HOURS = 24 * 30
#: Süresiz taramalar için kuyruğa yazılan bitiş: pratikte "durdurulana kadar"
INDEFINITE_DAYS = 3650


class ScanCriteria(BaseModel):
    """Bir tarama işinin tüm parametreleri — hem API gövdesi hem iş kuyruğu kaydı."""

    sites: list[str] = Field(default_factory=available_sites)
    brand: str = ANY
    model: str = ANY
    min_price: float = Field(default=0.0, ge=0)
    max_price: float = Field(default=DEFAULT_MAX_PRICE, ge=0)
    min_year: int = DEFAULT_MIN_YEAR
    max_year: int = DEFAULT_MAX_YEAR
    min_km: float = Field(default=0.0, ge=0)
    max_km: float = Field(default=DEFAULT_MAX_KM, ge=0)
    max_tramer: float = Field(default=DEFAULT_MAX_TRAMER, ge=0)
    #: Tarama süresi (saat). ``None`` → kullanıcı durdurana kadar sürer.
    duration_hours: float | None = Field(
        default=DEFAULT_DURATION_HOURS, gt=0, le=MAX_DURATION_HOURS
    )
    #: Turlar arası bekleme (dakika). ``None`` → ``OTOGALERI_CYCLE_INTERVAL`` ayarı.
    cycle_interval_min: int | None = Field(default=None, ge=1, le=24 * 60)
    #: Boyalı olmasına izin verilen parçalar (kanonik kimlik veya Türkçe ad kabul edilir)
    allowed_parts: list[str] = Field(default_factory=list)
    #: Değişen olmasına da izin verilen parçalar (boya da serbesttir)
    changed_allowed_parts: list[str] = Field(default_factory=list)
    #: Hasar bilgisi okunamayan ilanlar da kaydedilsin mi
    include_unknown_damage: bool = True

    @field_validator("sites")
    @classmethod
    def _known_sites_only(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in ALL_SITES]
        if bad:
            disabled = [s for s in bad if (info := site_info(s)) and not info.enabled]
            if disabled:
                raise ValueError(f"Devre dışı site(ler): {disabled}")
            raise ValueError(f"Bilinmeyen site(ler): {bad}. Geçerli: {ALL_SITES}")
        not_ready = [s for s in v if not site_ready(s)]
        if not_ready:
            raise ValueError(f"Kurulumu tamamlanmamış site(ler): {not_ready}.")
        return list(dict.fromkeys(v)) or available_sites()

    @field_validator("brand", "model")
    @classmethod
    def _blank_is_any(cls, v: str) -> str:
        return v.strip() or ANY

    @field_validator("allowed_parts", "changed_allowed_parts")
    @classmethod
    def _normalize_parts(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for name in v:
            part = normalize_part(name)
            if part is None:
                raise ValueError(f"Bilinmeyen parça: {name!r}")
            if part not in out:
                out.append(part)
        return out

    @model_validator(mode="after")
    def _check(self) -> ScanCriteria:
        if self.min_price > self.max_price:
            raise ValueError("min_price, max_price'tan büyük olamaz")
        if self.min_year > self.max_year:
            raise ValueError("min_year, max_year'tan büyük olamaz")
        if self.min_km > self.max_km:
            raise ValueError("min_km, max_km'tan büyük olamaz")
        # Değişen serbest bırakılan parçada boya da serbesttir
        for part in self.changed_allowed_parts:
            if part not in self.allowed_parts:
                self.allowed_parts.append(part)
        return self

    # ---------- türetilmiş görünümler ----------

    def damage_policy(self) -> DamagePolicy:
        return DamagePolicy(
            paint_ok=frozenset(self.allowed_parts),
            change_ok=frozenset(self.changed_allowed_parts),
            max_tramer=None if self.max_tramer >= DEFAULT_MAX_TRAMER else self.max_tramer,
            include_unknown=self.include_unknown_damage,
        )

    def search_query(self, max_pages: int) -> SearchQuery:
        return SearchQuery(
            brand=self.brand,
            model=self.model,
            min_price=self.min_price or None,
            max_price=None if self.max_price >= DEFAULT_MAX_PRICE else self.max_price,
            min_year=self.min_year if self.min_year > DEFAULT_MIN_YEAR else None,
            max_year=self.max_year if self.max_year < DEFAULT_MAX_YEAR else None,
            max_pages=max_pages,
        )

    def matches_basic(self, item: Listing) -> tuple[bool, str]:
        """Liste özetinin marka/model/fiyat/yıl/km filtresine uyup uymadığı."""
        if self.brand != ANY:
            want, have = fold(self.brand), fold(item.brand)
            if not have or not (have.startswith(want) or want.startswith(have)):
                return False, "marka"
        if self.model != ANY:
            haystack = fold(f"{item.model} {item.trim} {item.title}")
            if fold(self.model) not in haystack:
                return False, "model"
        if not item.price:
            return False, "fiyat okunamadı"
        if not self.min_price <= item.price <= self.max_price:
            return False, "fiyat"
        if not self.min_year <= item.year <= self.max_year:
            return False, "yıl"
        if not self.min_km <= item.km <= self.max_km:
            return False, "km"
        return True, ""

    @property
    def indefinite(self) -> bool:
        return self.duration_hours is None

    def duration(self) -> timedelta:
        if self.duration_hours is None:
            return timedelta(days=INDEFINITE_DAYS)
        return timedelta(hours=self.duration_hours)

    def interval_seconds(self, settings: Settings) -> int:
        if self.cycle_interval_min is None:
            return settings.cycle_interval_sec
        return self.cycle_interval_min * 60

    def summary(self) -> str:
        parts = [self.brand if self.brand != ANY else "Tüm markalar"]
        if self.model != ANY:
            parts.append(self.model)
        return " ".join(parts) + f" · {len(self.sites)} site"


# ==========================================================================
#  MOTOR
# ==========================================================================


@dataclass
class SiteResult:
    site: str
    status: str = "ok"
    seen: int = 0
    matched: int = 0
    new: int = 0
    price_drops: int = 0
    error: str | None = None


@dataclass
class CycleResult:
    sites: list[SiteResult] = field(default_factory=list)

    @property
    def new(self) -> int:
        return sum(s.new for s in self.sites)

    @property
    def seen(self) -> int:
        return sum(s.seen for s in self.sites)

    @property
    def matched(self) -> int:
        return sum(s.matched for s in self.sites)


ScraperFactory = Callable[[str, HttpClient], Scraper]


class ScanEngine:
    """Bir tarama işinin turlarını yürütür. Reddedilen ilanları iş boyunca hatırlar
    ki her turda aynı detay sayfaları yeniden indirilmesin."""

    def __init__(
        self,
        repo: Repository,
        notifier: Notifier,
        settings: Settings | None = None,
        scraper_factory: ScraperFactory = build_scraper,
    ) -> None:
        self.repo = repo
        self.notifier = notifier
        self.settings = settings or get_settings()
        self.scraper_factory = scraper_factory
        self.http = HttpClient(self.settings)
        self._rejected: set[tuple[str, str]] = set()

    def run_cycle(
        self,
        job_id: str,
        criteria: ScanCriteria,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> CycleResult:
        reference = build_reference(self.repo.list_listings())
        result = CycleResult()
        for site in criteria.sites:
            if should_stop():
                break
            result.sites.append(self._run_site(job_id, site, criteria, reference, should_stop))
        log.info(
            "[Tur] %s tamamlandi: %d yeni ilan (%s)",
            job_id[:8],
            result.new,
            ", ".join(f"{s.site}={s.status}" for s in result.sites),
        )
        return result

    def _run_site(
        self,
        job_id: str,
        site: str,
        criteria: ScanCriteria,
        reference: MarketReference,
        should_stop: Callable[[], bool],
    ) -> SiteResult:
        res = SiteResult(site)
        started = utcnow()
        scraper: Scraper | None = None
        try:
            scraper = self.scraper_factory(site, self.http)
            summaries = list(
                scraper.search(criteria.search_query(self.settings.max_pages_per_site))
            )
            res.seen = len(summaries)
            candidates = [s for s in summaries if criteria.matches_basic(s)[0]]
            res.matched = len(candidates)
            known = self.repo.known_ids(site, [c.listing_id for c in candidates])

            for item in (c for c in candidates if c.listing_id in known):
                self._refresh_known(item, res)

            fresh = [
                c for c in candidates if c.listing_id not in known and c.key not in self._rejected
            ]
            limit = self.settings.max_detail_fetch_per_site
            if scraper.max_details is not None:
                limit = min(limit, scraper.max_details)
            for item in fresh[:limit]:
                if should_stop():
                    break
                self._process_new(scraper, item, criteria, reference, res)
        except Exception as exc:
            log.exception("[%s] Site taramasi basarisiz", site)
            res.status, res.error = "failed", str(exc)[:500]
            self.notifier.notify(SiteFailure(site, str(exc)))
        finally:
            if scraper is not None:
                scraper.close()
            self.repo.record_site_run(
                job_id=job_id,
                site=site,
                started_at=started,
                finished_at=utcnow(),
                status=res.status,
                seen=res.seen,
                matched=res.matched,
                new=res.new,
                price_drops=res.price_drops,
                error=res.error,
            )
        return res

    def _refresh_known(self, item: Listing, res: SiteResult) -> None:
        upsert = self.repo.upsert_listing(item)
        if upsert.kind == "price_drop" and upsert.old_price:
            event = PriceDrop(item, upsert.old_price)
            if event.drop_pct >= self.settings.price_drop_min_pct:
                res.price_drops += 1
                self.notifier.notify(event)

    def _process_new(
        self,
        scraper: Scraper,
        item: Listing,
        criteria: ScanCriteria,
        reference: MarketReference,
        res: SiteResult,
    ) -> None:
        try:
            if item.damage is None:
                scraper.enrich(item)
        except Exception as exc:  # noqa: BLE001 - tek ilanın hatası siteyi durdurmasın
            log.warning("[%s] Detay alinamadi (%s): %s", item.source_site, item.link, exc)
            return
        ok, reason = evaluate(item.damage, criteria.damage_policy())
        if not ok:
            log.debug("[%s] Elendi (%s): %s", item.source_site, reason, item.link)
            self._rejected.add(item.key)
            return
        upsert = self.repo.upsert_listing(item)
        if upsert.kind == "new":
            res.new += 1
            deal = reference.deal_pct(item.brand, item.model, item.year, item.price)
            log.info(
                "[%s] HEDEFE UYAN ARAC: %s - %s TL", item.source_site, item.display_name, item.price
            )
            self.notifier.notify(NewListing(item, deal))


def criteria_from_json(raw: str | bytes | dict[str, Any]) -> ScanCriteria:
    if isinstance(raw, dict):
        return ScanCriteria.model_validate(raw)
    return ScanCriteria.model_validate_json(raw)
