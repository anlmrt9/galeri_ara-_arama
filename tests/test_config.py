from config import Settings


def _fresh_settings(monkeypatch, **env) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # .env dosyasını yok say ki testler makineye bağlı olmasın
    return Settings(_env_file=None)


def test_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = _fresh_settings(monkeypatch)
    assert s.scraper_request_timeout == 15
    assert s.retry_max_attempts == 3
    assert s.db_name == "OtoGaleriDB"
    assert s.api_key == ""


def test_env_override_with_legacy_names(monkeypatch):
    s = _fresh_settings(
        monkeypatch,
        OTOGALERI_TIMEOUT="30",
        OTOGALERI_CYCLE_INTERVAL="120",
        OTOGALERI_DB_NAME="TestDB",
    )
    assert s.scraper_request_timeout == 30
    assert s.scraper_cycle_interval_sec == 120
    assert s.db_name == "TestDB"


def test_pool_size_accepts_both_alias_spellings(monkeypatch):
    s = _fresh_settings(monkeypatch, OTOGALERI_POOL_SIZE="7")
    assert s.db_connection_pool_size == 7


def test_cors_origin_list_parsing(monkeypatch):
    assert _fresh_settings(monkeypatch, OTOGALERI_CORS_ORIGINS="*").cors_origin_list == ["*"]
    s = _fresh_settings(monkeypatch, OTOGALERI_CORS_ORIGINS="https://a.com, https://b.com")
    assert s.cors_origin_list == ["https://a.com", "https://b.com"]


def test_database_url_env_wins(monkeypatch):
    s = _fresh_settings(monkeypatch, DATABASE_URL="postgresql://u:p@h:5432/db")
    assert s.effective_database_url == "postgresql://u:p@h:5432/db"
