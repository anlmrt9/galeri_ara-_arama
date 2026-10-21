"""config, http istemcisi, scoring, biçimlendirme ve UI kaçış yardımcıları."""

from __future__ import annotations

from datetime import datetime

import pytest

from otogaleri.config import ALL_SITES, Settings, available_sites
from otogaleri.formatting import format_number, format_price, format_try, humanize_delta
from otogaleri.http import HttpClient, ScraperHTTPError
from otogaleri.scoring import annotate, build_reference
from otogaleri.ui.render import esc, listing_card, safe_url

# ---------------------------------------------------------------- config


class TestSettings:
    def test_sqlite_is_default(self, settings: Settings):
        assert settings.resolved_database_url().startswith("sqlite:///")

    def test_postgres_scheme_normalized(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
        assert Settings().resolved_database_url() == "postgresql+psycopg2://u:p@h:5432/db"

    def test_sql_server_when_server_given(self, monkeypatch):
        monkeypatch.setenv("OTOGALERI_DB_SERVER", r"PC\SQLEXPRESS")
        assert Settings().resolved_database_url().startswith("mssql")

    def test_legacy_env_alias(self, monkeypatch):
        monkeypatch.setenv("OTOGALERI_MAX_NEW", "7")
        assert Settings().max_detail_fetch_per_site == 7

    @pytest.mark.parametrize(("raw", "expected"), [("", []), ("*", ["*"]), ("a, b,", ["a", "b"])])
    def test_cors(self, monkeypatch, raw, expected):
        monkeypatch.setenv("OTOGALERI_CORS_ORIGINS", raw)
        assert Settings().cors_origin_list == expected

    def test_all_five_sites_available(self):
        assert available_sites() == ALL_SITES
        assert {"Otoplus", "Otokoç 2. El", "Arabam.com", "VavaCars", "Sahibinden"} == set(ALL_SITES)


# ---------------------------------------------------------------- http


class Resp:
    def __init__(self, status: int, text: str = "", headers: dict | None = None):
        self.status_code, self.text, self.headers = status, text, headers or {}


class FakeSession:
    def __init__(self, responses):  # type: ignore[no-untyped-def]
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, **kw):  # type: ignore[no-untyped-def]
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _client(settings, responses):  # type: ignore[no-untyped-def]
    session = FakeSession(responses)
    sleeps: list[float] = []
    client = HttpClient(settings, session_factory=lambda: session, sleep=sleeps.append)
    return client, session, sleeps


class TestHttpClient:
    def test_success(self, settings):
        client, _, _ = _client(settings, [Resp(200, "ok")])
        assert client.get_text("u") == "ok"

    def test_retries_5xx_and_network_errors_with_backoff(self, settings):
        client, session, sleeps = _client(
            settings, [Resp(503), ConnectionError("x"), Resp(200, "ok")]
        )
        assert client.get_text("u") == "ok"
        assert session.calls == 3
        assert sleeps == [1.0, 2.0]

    def test_403_is_not_retried(self, settings):
        client, session, _ = _client(settings, [Resp(403), Resp(200)])
        with pytest.raises(ScraperHTTPError) as exc:
            client.get_text("u")
        assert exc.value.status == 403 and session.calls == 1

    def test_429_honours_retry_after(self, settings):
        client, _, sleeps = _client(
            settings, [Resp(429, headers={"Retry-After": "7"}), Resp(200, "ok")]
        )
        assert client.get_text("u") == "ok"
        assert 7.0 in sleeps

    def test_gives_up_after_max_attempts(self, settings):
        client, session, _ = _client(settings, [Resp(500)] * 3)
        with pytest.raises(ScraperHTTPError):
            client.get_text("u")
        assert session.calls == settings.retry_max_attempts


# ---------------------------------------------------------------- scoring


def test_market_reference_and_deal_pct():
    rows = [{"brand": "Fiat", "model": "Egea", "year": 2020, "price": p} for p in (900, 1000, 1100)]
    rows.append({"brand": "Fiat", "model": "Egea", "year": 2020, "price": 800})
    annotate(rows)
    assert rows[-1]["market_median"] == 950
    assert rows[-1]["deal_pct"] == pytest.approx(15.8, abs=0.1)


def test_small_groups_have_no_reference():
    ref = build_reference([{"brand": "A", "model": "B", "year": 1, "price": 10}])
    assert ref.deal_pct("A", "B", 1, 10) is None


def test_reference_falls_back_to_model_group():
    rows = [
        {"brand": "Fiat", "model": "Egea", "year": y, "price": 1000} for y in (2018, 2019, 2020)
    ]
    assert build_reference(rows).median_for("Fiat", "Egea", 2021) == 1000


# ---------------------------------------------------------------- formatting


def test_formatting():
    assert format_number(1650000) == "1.650.000"
    assert format_price("1650000") == "1.650.000 ₺"
    assert format_price(None) == "-"
    assert format_try(34980.5) == "34.980,50"
    assert format_try("abc") == "0,00"


def test_humanize_delta():
    now = datetime(2026, 1, 1, 12, 0)
    assert humanize_delta(datetime(2026, 1, 1, 11, 55), now) == "5 dk önce"
    assert humanize_delta(datetime(2026, 1, 1, 14, 0), now) == "2 sa sonra"
    assert humanize_delta(None) == "-"


# ---------------------------------------------------------------- UI güvenliği


def test_safe_url_rejects_non_http():
    assert safe_url("https://www.arabam.com/ilan/1") == "https://www.arabam.com/ilan/1"
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("//evil.com") is None


def test_listing_card_escapes_scraped_text():
    html = listing_card(
        {
            "source_site": "Otoplus",
            "brand": "<img src=x onerror=alert(1)>",
            "model": "Egea",
            "price": 1,
            "link": "javascript:alert(1)",
            "painted_parts": "<b>",
            "changed_parts": "",
        }
    )
    assert "<img" not in html and esc("<img") in html
    assert "javascript:" not in html
