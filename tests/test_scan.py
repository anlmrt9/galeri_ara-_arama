from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from otogaleri.config import ANY, SITE_ARABAM, SITE_OTOPLUS, available_sites
from otogaleri.damage import DamageReport, DamageState
from otogaleri.db import Repository
from otogaleri.models import Listing
from otogaleri.scan import ScanCriteria, ScanEngine
from otogaleri.scrapers.base import Scraper, SearchQuery


class TestCriteria:
    def test_defaults(self):
        c = ScanCriteria()
        assert c.sites == available_sites()
        assert c.brand == ANY
        assert c.damage_policy().max_tramer is None

    def test_sahibinden_is_selectable_like_other_sites(self):
        assert ScanCriteria(sites=["Sahibinden"]).sites == ["Sahibinden"]
        assert "Sahibinden" in ScanCriteria().sites

    def test_indefinite_duration_and_interval(self, settings):
        c = ScanCriteria(duration_hours=None, cycle_interval_min=10)
        assert c.indefinite
        assert c.duration().days >= 365
        assert c.interval_seconds(settings) == 600
        assert ScanCriteria().interval_seconds(settings) == settings.cycle_interval_sec
        assert ScanCriteria(duration_hours=6).duration().total_seconds() == 6 * 3600
        with pytest.raises(ValidationError):
            ScanCriteria(cycle_interval_min=0)

    def test_unknown_site_rejected(self):
        with pytest.raises(ValidationError, match="Bilinmeyen site"):
            ScanCriteria(sites=["foo"])

    def test_empty_sites_falls_back_to_all(self):
        assert ScanCriteria(sites=[]).sites == available_sites()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"min_price": 10, "max_price": 5},
            {"min_year": 2020, "max_year": 2010},
            {"min_km": 10, "max_km": 5},
            {"duration_hours": 0},
        ],
    )
    def test_invalid_ranges(self, kwargs):
        with pytest.raises(ValidationError):
            ScanCriteria(**kwargs)

    def test_parts_accept_legacy_names_and_change_implies_paint(self):
        c = ScanCriteria(allowed_parts=["sol ön çamurluk"], changed_allowed_parts=["Kaput"])
        assert c.allowed_parts == ["sol_on_cam", "kaput"]
        assert c.changed_allowed_parts == ["kaput"]

    def test_unknown_part_rejected(self):
        with pytest.raises(ValidationError, match="Bilinmeyen parça"):
            ScanCriteria(allowed_parts=["egzoz"])

    def test_matches_basic(self):
        c = ScanCriteria(
            brand="BMW", model="3 Serisi", min_price=500_000, max_price=2_000_000, min_year=2015
        )
        good = Listing(
            "x",
            "1",
            "l",
            brand="BMW",
            model="3",
            trim="Serisi 320i",
            year=2018,
            km=1,
            price=1_000_000,
        )
        assert c.matches_basic(good) == (True, "")
        assert (
            c.matches_basic(
                Listing("x", "2", "l", brand="Audi", model="A3", year=2018, price=1_000_000)
            )[1]
            == "marka"
        )
        assert (
            c.matches_basic(
                Listing("x", "3", "l", brand="BMW", model="X1", year=2018, price=1_000_000)
            )[1]
            == "model"
        )
        assert (
            c.matches_basic(
                Listing("x", "4", "l", brand="BMW", model="3 Serisi", year=2010, price=1_000_000)
            )[1]
            == "yıl"
        )
        assert (
            c.matches_basic(
                Listing("x", "5", "l", brand="BMW", model="3 Serisi", year=2018, price=0)
            )[1]
            == "fiyat okunamadı"
        )

    def test_brand_prefix_matching(self):
        c = ScanCriteria(brand="Mercedes-Benz")
        assert c.matches_basic(Listing("x", "1", "l", brand="Mercedes", year=2020, price=1))[0]

    def test_search_query_drops_sentinel_defaults(self):
        q = ScanCriteria().search_query(2)
        assert q == SearchQuery(max_pages=2)

    def test_json_roundtrip(self):
        c = ScanCriteria(brand="Fiat", allowed_parts=["kaput"])
        assert ScanCriteria.model_validate_json(c.model_dump_json()) == c


# ==========================================================================
#  ScanEngine — sahte scraper ile
# ==========================================================================


class FakeScraper(Scraper):
    site = SITE_OTOPLUS

    def __init__(
        self,
        items: list[Listing],
        details: dict[str, DamageReport | None] | None = None,
        fail: Exception | None = None,
    ):
        self.items = items
        self.details = details or {}
        self.fail = fail
        self.enriched: list[str] = []
        self.closed = False

    def search(self, query: SearchQuery) -> Iterator[Listing]:
        if self.fail:
            raise self.fail
        yield from (Listing(**i.__dict__) for i in self.items)

    def enrich(self, listing: Listing) -> Listing:
        self.enriched.append(listing.listing_id)
        listing.damage = self.details.get(listing.listing_id)
        return listing

    def close(self) -> None:
        self.closed = True


def _item(lid: str, price: int = 1_000_000, **kw) -> Listing:
    return Listing(
        SITE_OTOPLUS,
        lid,
        f"https://example.com/{lid}",
        brand="Fiat",
        model="Egea",
        year=2020,
        km=40_000,
        price=price,
        **kw,
    )


def _engine(repo, notifier, settings, scraper: FakeScraper) -> ScanEngine:
    return ScanEngine(repo, notifier, settings, scraper_factory=lambda site, http: scraper)


def _painted_kaput() -> DamageReport:
    r = DamageReport.all_original()
    r.parts["kaput"] = DamageState.PAINTED
    return r


CRITERIA = ScanCriteria(sites=[SITE_OTOPLUS])


def test_new_matching_listing_is_saved_and_notified(repo: Repository, notifier, channel, settings):
    scraper = FakeScraper([_item("A")], {"A": DamageReport.all_original()})
    result = _engine(repo, notifier, settings, scraper).run_cycle("job", CRITERIA)
    assert result.new == 1
    assert repo.count_listings() == 1
    assert any("Yeni araç" in t for t, _ in channel.sent)
    assert scraper.closed
    assert repo.latest_site_runs()[SITE_OTOPLUS]["status"] == "ok"


def test_damage_policy_rejects_and_remembers(repo, notifier, channel, settings):
    scraper = FakeScraper([_item("A")], {"A": _painted_kaput()})
    engine = _engine(repo, notifier, settings, scraper)
    engine.run_cycle("job", CRITERIA)
    engine.run_cycle("job", CRITERIA)
    assert repo.count_listings() == 0
    assert scraper.enriched == ["A"]  # ikinci turda detay sayfası tekrar indirilmez
    assert channel.sent == []


def test_allowed_part_lets_listing_through(repo, notifier, settings):
    scraper = FakeScraper([_item("A")], {"A": _painted_kaput()})
    criteria = ScanCriteria(sites=[SITE_OTOPLUS], allowed_parts=["kaput"])
    _engine(repo, notifier, settings, scraper).run_cycle("job", criteria)
    assert repo.list_listings()[0]["painted_parts"] == "Kaput"


def test_basic_filter_skips_detail_fetch(repo, notifier, settings):
    scraper = FakeScraper([_item("A", price=5_000_000)])
    _engine(repo, notifier, settings, scraper).run_cycle(
        "job", ScanCriteria(sites=[SITE_OTOPLUS], max_price=1_000_000)
    )
    assert scraper.enriched == []


def test_price_drop_on_known_listing_notifies(repo, notifier, channel, settings):
    _engine(
        repo,
        notifier,
        settings,
        FakeScraper([_item("A", 1_000_000)], {"A": DamageReport.all_original()}),
    ).run_cycle("job", CRITERIA)
    channel.sent.clear()
    scraper = FakeScraper([_item("A", 900_000)])
    result = _engine(repo, notifier, settings, scraper).run_cycle("job", CRITERIA)
    assert scraper.enriched == []  # bilinen ilan için detay yok
    assert result.sites[0].price_drops == 1
    assert any("Fiyat düştü" in t for t, _ in channel.sent)


def test_site_failure_is_recorded_and_notified(repo, notifier, channel, settings):
    scraper = FakeScraper([], fail=RuntimeError("HTTP 503"))
    result = _engine(repo, notifier, settings, scraper).run_cycle("job", CRITERIA)
    assert result.sites[0].status == "failed"
    assert repo.latest_site_runs()[SITE_OTOPLUS]["error"] == "HTTP 503"
    assert any("sorun" in t for t, _ in channel.sent)
    assert scraper.closed


def test_detail_failure_skips_only_that_listing(repo, notifier, settings):
    class Flaky(FakeScraper):
        def enrich(self, listing):
            if listing.listing_id == "A":
                raise RuntimeError("timeout")
            return super().enrich(listing)

    scraper = Flaky([_item("A"), _item("B")], {"B": DamageReport.all_original()})
    _engine(repo, notifier, settings, scraper).run_cycle("job", CRITERIA)
    assert repo.known_ids(SITE_OTOPLUS, ["A", "B"]) == {"B"}


def test_should_stop_interrupts(repo, notifier, settings):
    scraper = FakeScraper([_item("A")], {"A": DamageReport.all_original()})
    result = _engine(repo, notifier, settings, scraper).run_cycle(
        "job", ScanCriteria(sites=[SITE_OTOPLUS, SITE_ARABAM]), should_stop=lambda: True
    )
    assert result.sites == []


def test_unknown_damage_respects_flag(repo, notifier, settings):
    scraper = FakeScraper([_item("A")], {"A": None})
    _engine(repo, notifier, settings, scraper).run_cycle(
        "job", ScanCriteria(sites=[SITE_OTOPLUS], include_unknown_damage=False)
    )
    assert repo.count_listings() == 0
