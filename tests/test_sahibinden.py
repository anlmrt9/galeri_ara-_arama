"""Sahibinden ayrıştırıcıları — gerçek sayfalardan kırpılmış fixture'larla (ağsız)."""

from __future__ import annotations

import pytest

from otogaleri.damage import DamagePolicy, DamageState, evaluate
from otogaleri.scrapers import sahibinden
from otogaleri.scrapers.base import SearchQuery
from tests.conftest import fixture_html


def test_list():
    items = sahibinden.parse_list(fixture_html("sahibinden_list.html"))
    assert [i.listing_id for i in items] == ["SB-1300839906", "SB-1333553212", "SB-1321324395"]
    kia = items[0]
    assert (kia.brand, kia.model, kia.trim) == ("Kia", "Rio", "1.4 CRDi Comfort")
    assert (kia.year, kia.km, kia.price) == (2015, 200000, 715000)
    assert kia.location == "İstanbul Sultanbeyli"
    assert kia.link.startswith("https://www.sahibinden.com/ilan/vasita-otomobil-kia-")
    assert kia.link.endswith("-1300839906/detay")
    assert kia.damage is None


def test_detail_damage_map():
    report = sahibinden.parse_detail(fixture_html("sahibinden_detail.html"))
    assert report is not None
    assert len(report.parts) == 13
    assert set(report.painted) == {"kaput", "sag_arka_cam"}  # boyalı + lokal boyalı
    assert report.changed == ["sol_on_kapi"]
    assert report.parts["tavan"] is DamageState.ORIGINAL
    assert report.heavy_damage is False


def test_heavy_damage_is_always_rejected():
    html = fixture_html("sahibinden_detail.html").replace("Hayır", "Evet")
    report = sahibinden.parse_detail(html)
    assert report is not None and report.heavy_damage
    everything = frozenset(report.parts)
    assert evaluate(report, DamagePolicy(change_ok=everything)) == (False, "ağır hasar kayıtlı")


@pytest.mark.parametrize(
    "page",
    [
        "<html><head><title>Just a moment...</title></head></html>",
        "<html><head><title>Access to this page has been denied</title></head></html>",
        '<html><body><div id="px-captcha"></div></body></html>',
    ],
)
def test_block_pages_detected(page):
    assert sahibinden.is_challenge(page)


def test_normal_page_is_not_a_block():
    assert not sahibinden.is_challenge(fixture_html("sahibinden_list.html"))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (SearchQuery(), "https://www.sahibinden.com/otomobil?sorting=date_desc"),
        (
            SearchQuery(brand="Fiat", model="Egea", min_year=2018, max_price=900000),
            "https://www.sahibinden.com/fiat-egea?sorting=date_desc&price_max=900000&a5_min=2018",
        ),
        (
            SearchQuery(brand="BMW", model="3 Serisi"),
            "https://www.sahibinden.com/bmw-3-serisi?sorting=date_desc",
        ),
    ],
)
def test_page_url(query, expected):
    assert sahibinden.page_url(query, 1) == expected


def test_page_url_paging():
    assert sahibinden.page_url(SearchQuery(brand="Fiat"), 3).endswith("pagingOffset=40")


class FakeBrowser:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.current = ""
        self.opened: list[str] = []

    def uc_open_with_reconnect(self, url, _reconnect):  # type: ignore[no-untyped-def]
        self.opened.append(url)
        self.current = url

    def get_page_source(self) -> str:
        return self.pages.get(self.current, "<html></html>")


@pytest.fixture
def no_wait(monkeypatch, settings):  # type: ignore[no-untyped-def]
    settings.selenium_wait_sec = 0
    monkeypatch.setattr(sahibinden.time, "sleep", lambda _s: None)
    monkeypatch.setattr(sahibinden, "_blocked_until", 0.0)


def _scraper(browser: FakeBrowser) -> sahibinden.SahibindenScraper:
    scraper = sahibinden.SahibindenScraper()
    scraper._sb = browser
    return scraper


def test_search_and_enrich_flow(no_wait):
    query = SearchQuery(max_pages=3)
    list_url = sahibinden.page_url(query, 1)
    browser = FakeBrowser({list_url: fixture_html("sahibinden_list.html")})
    scraper = _scraper(browser)
    items = list(scraper.search(query))
    assert len(items) == 3
    assert browser.opened == [list_url]  # 20'den az sonuç → sonraki sayfa açılmaz
    browser.pages[items[0].link] = fixture_html("sahibinden_detail.html")
    assert scraper.enrich(items[0]).damage is not None
    assert scraper.max_details == 6


def test_block_raises_and_backs_off_without_retrying(no_wait):
    query = SearchQuery()
    denied = "<title>Access to this page has been denied</title>"
    browser = FakeBrowser({sahibinden.page_url(query, 1): denied})
    with pytest.raises(sahibinden.SahibindenBlockedError, match="60 dk"):
        list(_scraper(browser).search(query))
    assert sahibinden.blocked_remaining_min() > 0
    # bekleme süresince siteye hiç istek atılmaz
    browser.opened.clear()
    with pytest.raises(sahibinden.SahibindenBlockedError, match="kaldı"):
        list(_scraper(browser).search(query))
    assert browser.opened == []
