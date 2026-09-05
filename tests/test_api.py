from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def no_db_client(monkeypatch):
    """Veritabanı bağlantısı KURULAMAMIŞ bir API (engine None)."""
    monkeypatch.setattr(api, "get_engine", lambda: None)
    monkeypatch.setattr(api.settings, "api_key", "", raising=False)
    with TestClient(api.app) as c:
        yield c


@pytest.fixture
def client(monkeypatch):
    """Sahte (ama None olmayan) engine ile API — DB'ye gerçekten dokunmaz."""
    monkeypatch.setattr(api, "get_engine", lambda: MagicMock(name="fake-engine"))
    monkeypatch.setattr(api, "init_tables", lambda _engine: None)
    monkeypatch.setattr(api.settings, "api_key", "", raising=False)
    with TestClient(api.app) as c:
        yield c


def test_health_reports_no_db(no_db_client):
    r = no_db_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"db_connected": False}


def test_config_endpoint_shape(no_db_client):
    body = no_db_client.get("/api/config").json()
    assert isinstance(body["sites"], list) and body["sites"]
    assert "catalog" in body and "damage_parts" in body
    assert body["cycle_interval_sec"] > 0


def test_listings_returns_503_without_engine(no_db_client):
    assert no_db_client.get("/api/listings").status_code == 503


def test_scan_start_returns_503_without_engine(no_db_client):
    assert no_db_client.post("/api/scan/start", json={"brand": "BMW"}).status_code == 503


def test_scan_start_rejects_invalid_criteria(client):
    r = client.post("/api/scan/start", json={"min_price": 100, "max_price": 1})
    assert r.status_code == 422


def test_scan_status_idle(client):
    assert client.get("/api/scan/status").json() == {"active": False}


class TestApiKeyAuth:
    @pytest.fixture
    def secured_client(self, monkeypatch):
        monkeypatch.setattr(api, "get_engine", lambda: None)
        monkeypatch.setattr(api.settings, "api_key", "secret", raising=False)
        with TestClient(api.app) as c:
            yield c

    def test_protected_endpoint_needs_key(self, secured_client):
        assert secured_client.get("/api/scan/status").status_code == 401

    def test_protected_endpoint_accepts_valid_key(self, secured_client):
        r = secured_client.get("/api/scan/status", headers={"X-API-Key": "secret"})
        assert r.status_code == 200

    def test_health_stays_public(self, secured_client):
        assert secured_client.get("/api/health").status_code == 200
