"""Ortak test fikstürleri.

Testler geliştiricinin ``.env`` dosyasından etkilenmesin diye ``Settings`` .env
okumayacak şekilde ayarlanır; her test kendi geçici SQLite veritabanını kullanır.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from otogaleri.config import Settings, get_settings

Settings.model_config["env_file"] = None

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    for key in ("DATABASE_URL", "OTOGALERI_DB_SERVER", "OTOGALERI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OTOGALERI_SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OTOGALERI_LOG_FILE", "")
    monkeypatch.setenv("OTOGALERI_DESKTOP_NOTIFICATIONS", "false")
    monkeypatch.setenv("OTOGALERI_EMBEDDED_WORKER", "false")
    monkeypatch.setenv("OTOGALERI_REQUEST_MIN_INTERVAL", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


#: CI'daki PostgreSQL işi bu değişkenle aynı testleri gerçek PostgreSQL'de koşturur.
TEST_DATABASE_URL = os.environ.get("OTOGALERI_TEST_DATABASE_URL", "")


@pytest.fixture
def repo(settings: Settings):  # type: ignore[no-untyped-def]
    import sqlalchemy as sa

    from otogaleri.db import Repository, create_db_engine, init_db, metadata

    engine = create_db_engine(settings, url=TEST_DATABASE_URL or None)
    if TEST_DATABASE_URL:  # her test temiz şema ile başlasın
        metadata.drop_all(engine)
        with engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    init_db(engine)
    yield Repository(engine)
    engine.dispose()


class RecordingChannel:
    name = "test"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, body: str) -> None:
        self.sent.append((title, body))


@pytest.fixture
def channel() -> RecordingChannel:
    return RecordingChannel()


@pytest.fixture
def notifier(settings: Settings, channel: RecordingChannel):  # type: ignore[no-untyped-def]
    from otogaleri.notifications import Notifier

    return Notifier(settings, channels=[channel])
