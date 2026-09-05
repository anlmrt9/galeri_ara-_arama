"""
config.py - OtoGaleri Avcı Botu Merkezi Ayarlar
================================================
Tüm ayarlar ``pydantic-settings`` ile tek bir ``Settings`` sınıfında toplanır.
Değerler şu öncelikle okunur:

    1. Ortam değişkenleri (ör. ``OTOGALERI_TIMEOUT``)
    2. Proje kökündeki ``.env`` dosyası
    3. Sınıftaki varsayılanlar

Veritabanı seçimi:
    * ``DATABASE_URL`` tanımlıysa  → PostgreSQL / Supabase (bulut)
    * Tanımlı değilse             → yerel SQL Server (Windows geliştirme)

Geriye dönük uyumluluk: Eski ``BÜYÜK_HARF`` modül sabitleri (``DB_SERVER``,
``SCRAPER_REQUEST_TIMEOUT`` vb.) hâlâ dışa aktarılır; diğer modüller bunları
``from config import ...`` ile kullanmaya devam edebilir.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _database_url_from_streamlit_secrets() -> str:
    """Streamlit çalışıyorsa ``st.secrets['DATABASE_URL']`` değerini döndürür."""
    try:
        import streamlit as st

        return str(st.secrets.get("DATABASE_URL", "") or "")
    except Exception:
        return ""


class Settings(BaseSettings):
    """Ortam değişkeni / ``.env`` ile override edilebilen merkezi ayarlar."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- VERİTABANI ----------
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "OTOGALERI_DATABASE_URL"),
    )
    db_server: str = Field(default=r"MERTPC\SQLEXPRESS", validation_alias="OTOGALERI_DB_SERVER")
    db_name: str = Field(default="OtoGaleriDB", validation_alias="OTOGALERI_DB_NAME")

    # ---------- DB POOL & RETRY ----------
    db_connection_pool_size: int = Field(
        default=10,
        validation_alias=AliasChoices("OTOGALERI_DB_POOL_SIZE", "OTOGALERI_POOL_SIZE"),
    )
    db_connection_max_overflow: int = Field(
        default=20,
        validation_alias=AliasChoices("OTOGALERI_DB_MAX_OVERFLOW", "OTOGALERI_MAX_OVERFLOW"),
    )
    db_connection_recycle_seconds: int = Field(
        default=3600, validation_alias="OTOGALERI_DB_RECYCLE"
    )
    db_query_timeout: int = Field(default=20, validation_alias="OTOGALERI_DB_TIMEOUT")
    retry_max_attempts: int = Field(default=3, validation_alias="OTOGALERI_RETRY_ATTEMPTS")
    retry_backoff_factor: int = Field(default=2, validation_alias="OTOGALERI_RETRY_BACKOFF")

    # ---------- SCRAPER ----------
    scraper_request_timeout: int = Field(default=15, validation_alias="OTOGALERI_TIMEOUT")
    scraper_page_wait_sec: int = Field(default=2, validation_alias="OTOGALERI_PAGE_WAIT")
    scraper_selenium_wait_sec: int = Field(default=5, validation_alias="OTOGALERI_SELENIUM_WAIT")
    scraper_cycle_interval_sec: int = Field(default=60, validation_alias="OTOGALERI_CYCLE_INTERVAL")
    max_new_listings_per_cycle: int = Field(default=5, validation_alias="OTOGALERI_MAX_NEW")

    # ---------- BİLDİRİM ----------
    site_failure_notify_cooldown_minutes: int = Field(
        default=15, validation_alias="OTOGALERI_FAILURE_COOLDOWN"
    )
    notifications_enabled: bool = Field(
        default=True, validation_alias="OTOGALERI_NOTIFICATIONS_ENABLED"
    )

    # ---------- LOG ----------
    log_file: str = Field(default="otogaleri_log.txt", validation_alias="OTOGALERI_LOG_FILE")
    log_level: str = Field(default="INFO", validation_alias="OTOGALERI_LOG_LEVEL")
    log_max_bytes: int = Field(default=5_000_000, validation_alias="OTOGALERI_LOG_MAX_BYTES")
    log_backup_count: int = Field(default=3, validation_alias="OTOGALERI_LOG_BACKUP_COUNT")

    # ---------- API ----------
    api_key: str = Field(default="", validation_alias="OTOGALERI_API_KEY")
    api_cors_origins: str = Field(default="*", validation_alias="OTOGALERI_CORS_ORIGINS")

    @property
    def cors_origin_list(self) -> list[str]:
        """``api_cors_origins`` metnini virgülle ayırarak listeye çevirir."""
        raw = self.api_cors_origins.strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        """Env/`.env` boşsa Streamlit secrets'a düşen nihai ``DATABASE_URL``."""
        return self.database_url or _database_url_from_streamlit_secrets()


settings = Settings()

# ==========================================================================
#  GERİYE DÖNÜK UYUMLU MODÜL SABİTLERİ
# ==========================================================================
DATABASE_URL = settings.effective_database_url
DB_SERVER = settings.db_server
DB_NAME = settings.db_name

SCRAPER_REQUEST_TIMEOUT = settings.scraper_request_timeout
SCRAPER_PAGE_WAIT_SEC = settings.scraper_page_wait_sec
SCRAPER_SELENIUM_WAIT_SEC = settings.scraper_selenium_wait_sec
SCRAPER_CYCLE_INTERVAL_SEC = settings.scraper_cycle_interval_sec
MAX_NEW_LISTINGS_PER_CYCLE = settings.max_new_listings_per_cycle

DB_CONNECTION_POOL_SIZE = settings.db_connection_pool_size
DB_CONNECTION_MAX_OVERFLOW = settings.db_connection_max_overflow
DB_CONNECTION_RECYCLE_SECONDS = settings.db_connection_recycle_seconds
DB_QUERY_TIMEOUT = settings.db_query_timeout
RETRY_MAX_ATTEMPTS = settings.retry_max_attempts
RETRY_BACKOFF_FACTOR = settings.retry_backoff_factor

SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES = settings.site_failure_notify_cooldown_minutes
LOG_FILE = settings.log_file

# ---------- SITE İSİMLERİ ----------
SITE_OTOPLUS = "Otoplus"
SITE_VAVACARS = "VavaCars"
SITE_OTOKOC = "Otokoç 2. El"
SITE_ARABAM = "Arabam.com"
SITE_SAHIBINDEN = "Sahibinden"

ALL_SITES = [SITE_OTOPLUS, SITE_VAVACARS, SITE_OTOKOC, SITE_ARABAM, SITE_SAHIBINDEN]

# ---------- MARKA / MODEL KATALOĞU ----------
# Streamlit arayüzü (app.py) ve mobil uygulama (api.py -> /api/config) aynı
# kataloğu kullanır, tek kaynaktan yönetilir.
CAR_CATALOG = {
    "Audi": ["A3", "A4", "A5", "A6", "Q2", "Q3", "Q5", "Q7"],
    "BMW": ["1 Serisi", "2 Serisi", "3 Serisi", "4 Serisi", "5 Serisi", "X1", "X3", "X5"],
    "Citroen": ["C-Elysee", "C3", "C3 Aircross", "C4", "C5 Aircross"],
    "Dacia": ["Duster", "Sandero", "Sandero Stepway", "Logan"],
    "Fiat": ["Egea", "Fiorino", "Linea", "Punto", "Doblo"],
    "Ford": ["Focus", "Fiesta", "Courier", "Puma", "Kuga", "Mondeo"],
    "Honda": ["Civic", "CR-V", "City", "Accord"],
    "Hyundai": ["i20", "Tucson", "Bayon", "Elantra", "Accent Blue", "i10"],
    "Mercedes-Benz": ["A-Serisi", "B-Serisi", "C-Serisi", "E-Serisi", "CLA", "GLA"],
    "Opel": ["Astra", "Corsa", "Crossland", "Mokka", "Insignia"],
    "Peugeot": ["208", "2008", "308", "3008", "508", "Rifter"],
    "Renault": ["Megane", "Clio", "Symbol", "Taliant", "Captur", "Kadjar"],
    "Seat": ["Leon", "Ibiza", "Arona", "Ateca"],
    "Skoda": ["Octavia", "Superb", "Scala", "Kamiq", "Karoq"],
    "Toyota": ["Corolla", "Yaris", "C-HR", "Auris", "RAV4"],
    "Volkswagen": ["Passat", "Golf", "Polo", "T-Roc", "Tiguan", "Jetta", "Caddy"],
    "Volvo": ["S60", "S90", "XC40", "XC60", "XC90"],
}

# ---------- HASAR HARİTASI PARÇALARI ----------
# car_map_component/index.html ile birebir aynı 13 parça anahtarı. `scraper_key`
# doluysa, bu parça "boyalı"/"değişen" seçildiğinde run_one_cycle'a gönderilen
# allowed_parts listesine bu Türkçe adla eklenir (tamponlarda None: mevcut
# davranışta tamponlar allowed_parts'a dahil edilmiyor).
DAMAGE_PARTS = [
    {"id": "on_tampon", "label": "Ön Tampon", "scraper_key": None},
    {"id": "kaput", "label": "Kaput", "scraper_key": "kaput"},
    {"id": "tavan", "label": "Tavan", "scraper_key": "tavan"},
    {"id": "bagaj", "label": "Bagaj", "scraper_key": "bagaj"},
    {"id": "arka_tampon", "label": "Arka Tampon", "scraper_key": None},
    {"id": "sol_on_cam", "label": "Sol Ön Çamurluk", "scraper_key": "sol ön çamurluk"},
    {"id": "sag_on_cam", "label": "Sağ Ön Çamurluk", "scraper_key": "sağ ön çamurluk"},
    {"id": "sol_on_kapi", "label": "Sol Ön Kapı", "scraper_key": "sol ön kapı"},
    {"id": "sag_on_kapi", "label": "Sağ Ön Kapı", "scraper_key": "sağ ön kapı"},
    {"id": "sol_arka_kapi", "label": "Sol Arka Kapı", "scraper_key": "sol arka kapı"},
    {"id": "sag_arka_kapi", "label": "Sağ Arka Kapı", "scraper_key": "sağ arka kapı"},
    {"id": "sol_arka_cam", "label": "Sol Arka Çamurluk", "scraper_key": "sol arka çamurluk"},
    {"id": "sag_arka_cam", "label": "Sağ Arka Çamurluk", "scraper_key": "sağ arka çamurluk"},
]
