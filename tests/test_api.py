from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from otogaleri import api as api_module
from otogaleri.config import get_settings
from otogaleri.db import Repository
from otogaleri.models import Listing
from otogaleri.worker import ScanManager

LOCAL = ("127.0.0.1", 50000)
REMOTE = ("192.168.1.20", 50000)


@pytest.fixture
def wired(repo: Repository, settings) -> Iterator[Repository]:  # type: ignore[no-untyped-def]
    api_module._state.update(repo=repo, manager=ScanManager(repo, settings))
    api_module._limiter._hits.clear()
    yield repo
    api_module._state.update(repo=None, manager=None)


def _client(addr=LOCAL) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(api_module.app, client=addr)


def _seed(repo: Repository, n: int = 3) -> None:
    for i in range(n):
        repo.upsert_listing(
            Listing(
                "Otoplus",
                f"OP-{i}",
                f"https://x/{i}",
                brand="Fiat",
                model="Egea",
                year=2020,
                km=1,
                price=1_000_000 + i,
            )
        )


def test_health_and_config_are_public(wired):
    with _client(REMOTE) as c:
        health = c.get("/api/health").json()
        assert health["db_connected"] is True
        assert health["auth"] == "localhost"
        config = c.get("/api/config").json()
    assert "Sahibinden" in config["sites"]
    assert {p["id"] for p in config["damage_parts"]} >= {"kaput", "on_tampon"}
    assert all(s["ready"] for s in config["site_details"])


def test_security_headers(wired):
    with _client() as c:
        r = c.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"


class TestAuth:
    def test_remote_without_key_is_forbidden(self, wired):
        with _client(REMOTE) as c:
            assert c.get("/api/listings").status_code == 403

    def test_localhost_without_key_is_allowed(self, wired):
        with _client(LOCAL) as c:
            assert c.get("/api/listings").status_code == 200

    def test_allow_unauthenticated_opt_in(self, wired, monkeypatch):
        monkeypatch.setenv("OTOGALERI_API_ALLOW_UNAUTHENTICATED", "true")
        get_settings.cache_clear()
        with _client(REMOTE) as c:
            assert c.get("/api/listings").status_code == 200

    def test_api_key_required_when_configured(self, wired, monkeypatch):
        monkeypatch.setenv("OTOGALERI_API_KEY", "s3cret")
        get_settings.cache_clear()
        with _client(LOCAL) as c:
            assert c.get("/api/listings").status_code == 401
            assert c.get("/api/listings", headers={"X-API-Key": "wrong"}).status_code == 401
            assert c.get("/api/listings", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_listings_pagination_and_shape(wired):
    _seed(wired, 5)
    with _client() as c:
        body = c.get("/api/listings", params={"limit": 2, "offset": 1}).json()
    assert body["total"] == 5 and body["new_count"] == 5
    assert len(body["listings"]) == 2
    row = body["listings"][0]
    for key in (
        "id",
        "brand",
        "price",
        "link",
        "is_new_listing",
        "scraped_at",
        "deal_pct",
        "damage",
    ):
        assert key in row
    assert row["scraped_at"].endswith("Z")


def test_price_history_endpoint(wired):
    _seed(wired, 1)
    pk = wired.list_listings()[0]["id"]
    with _client() as c:
        hist = c.get(f"/api/listings/{pk}/price-history").json()["history"]
    assert len(hist) == 1


def test_delete_listings(wired):
    _seed(wired, 2)
    with _client() as c:
        assert c.delete("/api/listings").json() == {"ok": True, "deleted": 2}
    assert wired.count_listings() == 0


def test_scan_lifecycle(wired):
    with _client() as c:
        assert c.get("/api/scan/status").json() == {"active": False}
        sid = c.post(
            "/api/scan/start", json={"brand": "Fiat", "allowed_parts": ["sol ön çamurluk"]}
        ).json()["session_id"]
        assert c.post("/api/scan/start", json={}).status_code == 409
        status = c.get("/api/scan/status").json()
        assert status["active"] and status["session_id"] == sid
        assert c.post("/api/scan/stop").json() == {"ok": True, "was_active": True}
        assert c.get("/api/scan/status").json()["active"] is False


def test_invalid_criteria_is_422(wired):
    with _client() as c:
        assert c.post("/api/scan/start", json={"sites": ["Letgo"]}).status_code == 422
        assert c.post("/api/scan/start", json={"min_price": 10, "max_price": 1}).status_code == 422


def test_stats(wired):
    _seed(wired, 2)
    with _client() as c:
        body = c.get("/api/stats").json()
    assert body["per_site"]["Otoplus"] == 2


def test_503_without_database(monkeypatch):
    def unreachable(*_a, **_kw):  # type: ignore[no-untyped-def]
        raise OSError("connection refused")

    monkeypatch.setattr(api_module, "create_db_engine", unreachable)
    api_module._state.update(repo=None, manager=None)
    api_module._limiter._hits.clear()
    with TestClient(api_module.app, client=LOCAL) as c:
        assert c.get("/api/listings").status_code == 503
        assert c.get("/api/scan/status").status_code == 503
        assert c.get("/api/health").json()["db_connected"] is False


def test_rate_limiter_window():
    limiter = api_module.RateLimiter(per_minute=2)
    assert limiter.allow("a", now=0) and limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)
    assert limiter.allow("b", now=2)
    assert limiter.allow("a", now=62)
