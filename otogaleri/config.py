"""Merkezi ayarlar ve alan sabitleri.

Ayarlar ``pydantic-settings`` ile tek bir :class:`Settings` sınıfında toplanır ve şu
öncelikle okunur: ortam değişkenleri → proje kökündeki ``.env`` → sınıf varsayılanları.

Veritabanı seçimi (:meth:`Settings.resolved_database_url`):

1. ``DATABASE_URL`` (veya Streamlit ``secrets``) doluysa → o URL (PostgreSQL / Supabase / herhangi biri)
2. ``OTOGALERI_DB_SERVER`` doluysa → yerel SQL Server (Windows Authentication)
3. Hiçbiri yoksa → proje kökünde SQLite dosyası (``OTOGALERI_SQLITE_PATH``)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: "SQL Server'ı OTOGALERI_DB_SERVER / DB_NAME ayarlarından kur" işareti
MSSQL_FROM_SETTINGS = "mssql+pyodbc://"


def _database_url_from_streamlit_secrets() -> str:
    """Streamlit içinde çalışılıyorsa ``st.secrets['DATABASE_URL']`` değerini döndürür."""
    try:
        import streamlit as st

        return str(st.secrets.get("DATABASE_URL", "") or "")
    except Exception:  # noqa: BLE001 - secrets dosyası yok / Streamlit dışı çalışma
        return ""


class Settings(BaseSettings):
    """Ortam değişkeni / ``.env`` ile override edilebilen tüm ayarlar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ---------- VERİTABANI ----------
    database_url: str = Field(
        default="", validation_alias=AliasChoices("DATABASE_URL", "OTOGALERI_DATABASE_URL")
    )
    db_server: str = Field(default="", validation_alias="OTOGALERI_DB_SERVER")
    db_name: str = Field(default="OtoGaleriDB", validation_alias="OTOGALERI_DB_NAME")
    odbc_driver: str = Field(default="", validation_alias="OTOGALERI_ODBC_DRIVER")
    sqlite_path: str = Field(default="otogaleri.db", validation_alias="OTOGALERI_SQLITE_PATH")
    db_pool_size: int = Field(
        default=5, validation_alias=AliasChoices("OTOGALERI_DB_POOL_SIZE", "OTOGALERI_POOL_SIZE")
    )
    db_max_overflow: int = Field(
        default=10,
        validation_alias=AliasChoices("OTOGALERI_DB_MAX_OVERFLOW", "OTOGALERI_MAX_OVERFLOW"),
    )
    db_recycle_seconds: int = Field(default=1800, validation_alias="OTOGALERI_DB_RECYCLE")
    db_connect_timeout: int = Field(default=20, validation_alias="OTOGALERI_DB_TIMEOUT")

    # ---------- HTTP / SCRAPER ----------
    request_timeout: int = Field(default=20, validation_alias="OTOGALERI_TIMEOUT")
    retry_max_attempts: int = Field(default=3, validation_alias="OTOGALERI_RETRY_ATTEMPTS")
    retry_backoff_factor: float = Field(default=2.0, validation_alias="OTOGALERI_RETRY_BACKOFF")
    request_min_interval_sec: float = Field(
        default=1.0, validation_alias="OTOGALERI_REQUEST_MIN_INTERVAL"
    )
    max_pages_per_site: int = Field(default=3, validation_alias="OTOGALERI_MAX_PAGES")
    max_detail_fetch_per_site: int = Field(
        default=15, validation_alias=AliasChoices("OTOGALERI_MAX_DETAIL", "OTOGALERI_MAX_NEW")
    )
    selenium_wait_sec: int = Field(default=6, validation_alias="OTOGALERI_SELENIUM_WAIT")
    cycle_interval_sec: int = Field(default=300, validation_alias="OTOGALERI_CYCLE_INTERVAL")

    # ---------- WORKER ----------
    embedded_worker: bool = Field(default=True, validation_alias="OTOGALERI_EMBEDDED_WORKER")
    worker_poll_sec: float = Field(default=3.0, validation_alias="OTOGALERI_WORKER_POLL")
    job_stale_after_sec: int = Field(default=120, validation_alias="OTOGALERI_JOB_STALE_AFTER")

    # ---------- BİLDİRİM ----------
    notifications_enabled: bool = Field(
        default=True, validation_alias="OTOGALERI_NOTIFICATIONS_ENABLED"
    )
    desktop_notifications: bool = Field(
        default=True, validation_alias="OTOGALERI_DESKTOP_NOTIFICATIONS"
    )
    failure_cooldown_minutes: int = Field(default=15, validation_alias="OTOGALERI_FAILURE_COOLDOWN")
    price_drop_min_pct: float = Field(default=1.0, validation_alias="OTOGALERI_PRICE_DROP_MIN_PCT")
    telegram_bot_token: str = Field(default="", validation_alias="OTOGALERI_TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="OTOGALERI_TELEGRAM_CHAT_ID")
    smtp_host: str = Field(default="", validation_alias="OTOGALERI_SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="OTOGALERI_SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="OTOGALERI_SMTP_USER")
    smtp_password: str = Field(default="", validation_alias="OTOGALERI_SMTP_PASSWORD")
    smtp_from: str = Field(default="", validation_alias="OTOGALERI_SMTP_FROM")
    smtp_to: str = Field(default="", validation_alias="OTOGALERI_SMTP_TO")
    smtp_starttls: bool = Field(default=True, validation_alias="OTOGALERI_SMTP_STARTTLS")

    # ---------- LOG / GÖZLEMLENEBİLİRLİK ----------
    log_file: str = Field(default="otogaleri_log.txt", validation_alias="OTOGALERI_LOG_FILE")
    log_level: str = Field(default="INFO", validation_alias="OTOGALERI_LOG_LEVEL")
    log_json: bool = Field(default=False, validation_alias="OTOGALERI_LOG_JSON")
    log_max_bytes: int = Field(default=5_000_000, validation_alias="OTOGALERI_LOG_MAX_BYTES")
    log_backup_count: int = Field(default=3, validation_alias="OTOGALERI_LOG_BACKUP_COUNT")
    sentry_dsn: str = Field(default="", validation_alias="OTOGALERI_SENTRY_DSN")

    # ---------- API ----------
    api_key: str = Field(default="", validation_alias="OTOGALERI_API_KEY")
    api_allow_unauthenticated: bool = Field(
        default=False, validation_alias="OTOGALERI_API_ALLOW_UNAUTHENTICATED"
    )
    api_cors_origins: str = Field(default="", validation_alias="OTOGALERI_CORS_ORIGINS")
    api_rate_limit_per_minute: int = Field(default=120, validation_alias="OTOGALERI_RATE_LIMIT")

    @property
    def cors_origin_list(self) -> list[str]:
        """``OTOGALERI_CORS_ORIGINS`` metnini listeye çevirir (boş → CORS kapalı)."""
        raw = self.api_cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def resolved_database_url(self) -> str:
        """Seçilen veritabanının SQLAlchemy URL'si (bkz. modül açıklaması)."""
        url = self.database_url or _database_url_from_streamlit_secrets()
        if url:
            # Heroku/Supabase tarzı "postgres://" şemasını SQLAlchemy'nin anladığı hale getir
            if url.startswith("postgres://"):
                url = "postgresql+psycopg2://" + url[len("postgres://") :]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg2://" + url[len("postgresql://") :]
            return url
        if self.db_server:
            return MSSQL_FROM_SETTINGS  # gerçek bağlantı dizesi db.create_db_engine'de kurulur
        return f"sqlite:///{self.sqlite_path}"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_to and (self.smtp_from or self.smtp_user))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Süreç genelinde tek ``Settings`` örneği (testlerde ``cache_clear`` ile sıfırlanır)."""
    return Settings()


# ==========================================================================
#  SİTELER
# ==========================================================================

SITE_OTOPLUS = "Otoplus"
SITE_VAVACARS = "VavaCars"
SITE_OTOKOC = "Otokoç 2. El"
SITE_ARABAM = "Arabam.com"
SITE_SAHIBINDEN = "Sahibinden"


@dataclass(frozen=True)
class SiteInfo:
    name: str
    url: str
    enabled: bool = True
    requires_browser: bool = False
    needs_setup: bool = False
    note: str = ""


SITES: tuple[SiteInfo, ...] = (
    SiteInfo(SITE_OTOPLUS, "https://www.otoplus.com"),
    SiteInfo(SITE_OTOKOC, "https://www.otokocikinciel.com"),
    SiteInfo(SITE_ARABAM, "https://www.arabam.com"),
    SiteInfo(
        SITE_VAVACARS,
        "https://tr.vava.cars",
        requires_browser=True,
        note="İstemci tarafında render edilir; headless Chrome (SeleniumBase) gerektirir.",
    ),
    SiteInfo(
        SITE_SAHIBINDEN,
        "https://www.sahibinden.com",
        requires_browser=True,
        note=(
            "Cloudflare korumalı; headless Chrome ile yavaş okunur. Doğrulama sayfası "
            "gelirse o tur atlanır (captcha çözülmez)."
        ),
    ),
)

#: Desteklenen tüm siteler.
ALL_SITES: list[str] = [s.name for s in SITES if s.enabled]


def site_info(name: str) -> SiteInfo | None:
    return next((s for s in SITES if s.name == name), None)


def site_ready(name: str, settings: Settings | None = None) -> bool:
    """Site şu anki ayarlarla taranabilir mi (``needs_setup`` siteler için genişletme noktası)."""
    info = site_info(name)
    return info is not None and info.enabled


def available_sites(settings: Settings | None = None) -> list[str]:
    """Kurulumu tamam olan siteler — UI/API'deki varsayılan seçim."""
    return [s for s in ALL_SITES if site_ready(s, settings)]


# ==========================================================================
#  MARKA / MODEL KATALOĞU (UI + /api/config)
# ==========================================================================

CAR_CATALOG: dict[str, list[str]] = {
    "Audi": ["A3", "A4", "A5", "A6", "Q2", "Q3", "Q5", "Q7"],
    "BMW": ["1 Serisi", "2 Serisi", "3 Serisi", "4 Serisi", "5 Serisi", "X1", "X3", "X5"],
    "Citroen": ["C-Elysee", "C3", "C3 Aircross", "C4", "C5 Aircross"],
    "Dacia": ["Duster", "Sandero", "Sandero Stepway", "Logan"],
    "Fiat": ["Egea", "Egea Cross", "Fiorino", "Linea", "Punto", "Doblo"],
    "Ford": ["Focus", "Fiesta", "Courier", "Puma", "Kuga", "Mondeo"],
    "Honda": ["Civic", "CR-V", "City", "Accord", "HR-V"],
    "Hyundai": ["i20", "Tucson", "Bayon", "Elantra", "Accent Blue", "i10"],
    "Mercedes-Benz": ["A-Serisi", "B-Serisi", "C-Serisi", "E-Serisi", "CLA", "GLA"],
    "Opel": ["Astra", "Corsa", "Crossland", "Mokka", "Insignia"],
    "Peugeot": ["208", "2008", "308", "3008", "508", "Rifter"],
    "Renault": ["Megane", "Clio", "Symbol", "Taliant", "Captur", "Kadjar", "Austral"],
    "Seat": ["Leon", "Ibiza", "Arona", "Ateca"],
    "Skoda": ["Octavia", "Superb", "Scala", "Kamiq", "Karoq"],
    "Toyota": ["Corolla", "Yaris", "C-HR", "Auris", "RAV4"],
    "Volkswagen": ["Passat", "Golf", "Polo", "T-Roc", "Tiguan", "Jetta", "Caddy"],
    "Volvo": ["S60", "S90", "XC40", "XC60", "XC90"],
}

ANY = "Tümü"
