"""Site ayrıştırıcıları — gerçek sayfalardan alınmış (kırpılmış, anonimleştirilmiş) HTML ile.

Bir site yapısını değiştirdiğinde ilk kırılacak testler bunlardır: ``tests/fixtures``
altındaki örnekleri yenileyip beklentileri güncellemek yeterlidir.
"""

from __future__ import annotations

import pytest

from otogaleri.damage import DamageState
from otogaleri.scrapers import arabam, otokoc, otoplus, vavacars
from otogaleri.scrapers._parsing import (
    humanize_slug,
    json_values_after,
    next_flight_text,
    to_int,
)
from otogaleri.scrapers.base import SearchQuery
from tests.conftest import fixture_html


class TestHelpers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1.650.000 ₺", 1650000),
            ("23.218 km", 23218),
            (2024, 2024),
            (None, 0),
            ("", 0),
            (True, 0),
        ],
    )
    def test_to_int(self, raw, expected):
        assert to_int(raw) == expected

    def test_humanize_slug(self):
        assert humanize_slug("3-serisi") == "3 Serisi"
        assert humanize_slug("hs") == "HS"
        assert humanize_slug("egea") == "Egea"

    def test_flight_chunks_are_joined_before_parsing(self):
        html = (
            '<script>self.__next_f.push([1,"a:{\\"x\\":[1,"])</script>'
            '<script>self.__next_f.push([1,"2]}"])</script>'
        )
        assert json_values_after(next_flight_text(html), '"x":[') == [[1, 2]]

    def test_json_values_after_respects_brackets_inside_strings(self):
        assert json_values_after('{"k":{"s":"a]}b","n":1}}', '"k":{') == [{"s": "a]}b", "n": 1}]

    def test_json_values_after_requires_opening_bracket(self):
        with pytest.raises(ValueError, match="bitmeli"):
            json_values_after("{}", '"k":')


class TestOtoplus:
    def test_list(self):
        items = otoplus.parse_list(fixture_html("otoplus_list.html"))
        assert [i.listing_id for i in items] == ["OP-578103", "OP-578102", "OP-578079"]
        first = items[0]
        assert (first.brand, first.model, first.year, first.km, first.price) == (
            "Mg",
            "HS",
            2024,
            23218,
            1650000,
        )
        assert first.link.startswith("https://www.otoplus.com/mg/hs/")
        assert first.damage is None

    def test_detail_reads_structured_inspection(self):
        report = otoplus.parse_detail(fixture_html("otoplus_detail.html"))
        assert report is not None
        assert len(report.parts) == 13
        # "hit_major" (göçük) kozmetik sayılır, boya/değişen değildir
        assert report.parts["sol_on_cam"] is DamageState.COSMETIC
        assert report.painted == [] and report.changed == []

    def test_detail_without_inspection_returns_none(self):
        assert otoplus.parse_detail("<html>Boyalı 0 Değişen 0</html>") is None

    def test_page_url(self):
        assert otoplus.page_url(1).endswith("/ikinci-el-araba")
        assert otoplus.page_url(3).endswith("?sayfa=3")


class TestOtokoc:
    def test_list(self):
        items = otokoc.parse_list(fixture_html("otokoc_list.html"))
        assert len(items) == 3
        dacia = items[0]
        assert dacia.listing_id == "OK-74560"
        assert (dacia.brand, dacia.model, dacia.year, dacia.km) == ("Dacia", "Duster", 2022, 98928)
        assert dacia.price == 1135000
        assert dacia.location == "Konya"
        assert dacia.link.endswith(
            "/ilan/vasita-suv-dacia-duster-dacia-duster-comfort-13-tce-150-bg-4x4-74560"
        )

    def test_detail_unlisted_parts_are_original(self):
        report = otokoc.parse_detail(fixture_html("otokoc_detail.html"))
        assert report is not None
        assert set(report.painted) == {"bagaj", "sag_on_cam", "sag_arka_cam"}
        assert report.changed == []
        assert report.parts["tavan"] is DamageState.ORIGINAL

    def test_brand_url(self):
        assert otokoc.page_url(SearchQuery(brand="Mercedes-Benz"), 2).endswith(
            "/ikinci-el/mercedes-benz?page=2"
        )


class TestArabam:
    def test_list(self):
        items = arabam.parse_list(fixture_html("arabam_list.html"))
        assert [i.listing_id for i in items] == ["AR-44947964", "AR-39790890", "AR-44982861"]
        focus = items[0]
        assert (focus.brand, focus.model, focus.year, focus.km, focus.price) == (
            "Ford",
            "Focus",
            2011,
            128000,
            815000,
        )

    def test_detail_parts_and_tramer(self):
        report = arabam.parse_detail(fixture_html("arabam_detail.html"))
        assert report is not None
        assert set(report.painted) == {"sol_arka_cam", "sag_arka_cam"}
        assert set(report.changed) == {"on_tampon", "arka_tampon"}
        assert report.parts["kaput"] is DamageState.UNKNOWN  # satıcı "belirtilmemiş"
        assert report.tramer == 3400

    def test_page_url_has_server_side_filters(self):
        url = arabam.page_url(
            SearchQuery(brand="Mercedes-Benz", min_year=2015, max_price=900000), 1
        )
        assert "/otomobil/mercedes-benz?" in url
        assert "minYear=2015" in url and "maxPrice=900000" in url and "sort=startedAt.desc" in url


class TestVavaCars:
    def test_list_and_clean_badge(self):
        items = vavacars.parse_list(fixture_html("vava_list.html"))
        assert len(items) == 3
        tesla, egea, bmw = items
        assert (tesla.brand, tesla.model, tesla.year, tesla.km, tesla.price) == (
            "Tesla",
            "Model Y",
            2024,
            31053,
            2600000,
        )
        assert tesla.damage is not None and tesla.damage.tramer == 0
        assert tesla.damage.painted == [] and tesla.damage.is_known
        assert egea.damage is None  # rozet yok → bilinmiyor
        assert (bmw.fuel, bmw.transmission) == ("Benzin", "Otomatik")


class FakeHttp:
    """URL → HTML (veya istisna) eşlemesi; sıra ile çağrılan URL'leri kaydeder."""

    def __init__(self, pages: dict[str, object]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get_text(self, url: str) -> str:
        self.calls.append(url)
        page = self.pages.get(url, "<html></html>")
        if isinstance(page, Exception):
            raise page
        return str(page)


class TestScraperFlow:
    def test_otoplus_stops_at_empty_page_and_enriches(self):
        http = FakeHttp(
            {
                otoplus.page_url(1): fixture_html("otoplus_list.html"),
                otoplus.page_url(2): "<html></html>",
            }
        )
        scraper = otoplus.OtoplusScraper(http)  # type: ignore[arg-type]
        items = list(scraper.search(SearchQuery(max_pages=5)))
        assert len(items) == 3
        assert http.calls == [otoplus.page_url(1), otoplus.page_url(2)]
        http.pages[items[0].link] = fixture_html("otoplus_detail.html")
        assert scraper.enrich(items[0]).damage is not None

    def test_otokoc_brand_404_falls_back_to_generic_list(self):
        from otogaleri.http import ScraperHTTPError

        query = SearchQuery(brand="Lada", max_pages=1)
        http = FakeHttp(
            {
                otokoc.page_url(query, 1): ScraperHTTPError("u", 404),
                otokoc.page_url(SearchQuery(), 1): fixture_html("otokoc_list.html"),
            }
        )
        items = list(otokoc.OtokocScraper(http).search(query))  # type: ignore[arg-type]
        assert len(items) == 3

    def test_otokoc_other_errors_propagate(self):
        from otogaleri.http import ScraperHTTPError

        query = SearchQuery(brand="Fiat")
        http = FakeHttp({otokoc.page_url(query, 1): ScraperHTTPError("u", 503)})
        with pytest.raises(ScraperHTTPError):
            list(otokoc.OtokocScraper(http).search(query))  # type: ignore[arg-type]

    def test_arabam_single_short_page(self):
        query = SearchQuery(max_pages=3)
        http = FakeHttp({arabam.page_url(query, 1): fixture_html("arabam_list.html")})
        scraper = arabam.ArabamScraper(http)  # type: ignore[arg-type]
        items = list(scraper.search(query))
        assert len(items) == 3
        assert len(http.calls) == 1  # 50'den az sonuç → sonraki sayfa istenmez
        http.pages[items[0].link] = fixture_html("arabam_detail.html")
        assert scraper.enrich(items[0]).damage.tramer == 3400  # type: ignore[union-attr]

    def test_registry(self):
        from otogaleri.config import ALL_SITES
        from otogaleri.scrapers import REGISTRY, build_scraper

        assert set(REGISTRY) == set(ALL_SITES)
        with pytest.raises(ValueError, match="Desteklenmeyen"):
            build_scraper("Letgo")
