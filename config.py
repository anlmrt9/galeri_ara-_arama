"""
config.py - OtoGaleriBot Merkezi Ayarlar
=========================================
Tüm sabitler, veritabanı bilgileri, bekleme süreleri ve
ortam değişkeni override'ları burada tutulur.

Bulut (Streamlit Cloud / Supabase) için DATABASE_URL,
Lokal Windows için DB_SERVER / DB_NAME kullanılır.
"""

import os

# ---------- VERİTABANI (Öncelik sırası) ----------
# 1) Streamlit secrets'tan DATABASE_URL (PostgreSQL / Supabase)
# 2) Ortam değişkeninden DATABASE_URL
# 3) Lokal SQL Server (Windows geliştirme)

def _get_database_url():
    """Streamlit secrets veya ortam değişkeninden DATABASE_URL okur."""
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return url
    except Exception:
        pass
    return os.environ.get("DATABASE_URL", "")

DATABASE_URL = _get_database_url()  # Boşsa SQL Server kullanılır

DB_SERVER = os.environ.get("OTOGALERI_DB_SERVER", r"MERTPC\SQLEXPRESS")
DB_NAME   = os.environ.get("OTOGALERI_DB_NAME", "OtoGaleriDB")

# ---------- SCRAPER AYARLARI ----------
SCRAPER_REQUEST_TIMEOUT    = int(os.environ.get("OTOGALERI_TIMEOUT", "15"))
SCRAPER_PAGE_WAIT_SEC      = int(os.environ.get("OTOGALERI_PAGE_WAIT", "2"))
SCRAPER_SELENIUM_WAIT_SEC  = int(os.environ.get("OTOGALERI_SELENIUM_WAIT", "5"))
SCRAPER_CYCLE_INTERVAL_SEC = int(os.environ.get("OTOGALERI_CYCLE_INTERVAL", "60"))
MAX_NEW_LISTINGS_PER_CYCLE = int(os.environ.get("OTOGALERI_MAX_NEW", "5"))

# ---------- DB POOL ----------
DB_POOL_SIZE     = int(os.environ.get("OTOGALERI_POOL_SIZE", "5"))
DB_MAX_OVERFLOW  = int(os.environ.get("OTOGALERI_MAX_OVERFLOW", "10"))

# ---------- SITE İSİMLERİ ----------
SITE_OTOPLUS    = "Otoplus"
SITE_VAVACARS   = "VavaCars"
SITE_OTOKOC     = "Otokoç 2. El"
SITE_ARABAM     = "Arabam.com"
SITE_SAHIBINDEN = "Sahibinden"

ALL_SITES = [SITE_OTOPLUS, SITE_VAVACARS, SITE_OTOKOC, SITE_ARABAM, SITE_SAHIBINDEN]

# ---------- BİLDİRİM ----------
SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES = int(os.environ.get("OTOGALERI_FAILURE_COOLDOWN", "15"))

# ---------- LOG DOSYASI ----------
LOG_FILE = os.environ.get("OTOGALERI_LOG_FILE", "otogaleri_log.txt")

# ========== DATABASE POOL & RETRY ==========
DB_CONNECTION_POOL_SIZE        = int(os.getenv("OTOGALERI_DB_POOL_SIZE", "10"))
DB_CONNECTION_MAX_OVERFLOW     = int(os.getenv("OTOGALERI_DB_MAX_OVERFLOW", "20"))
DB_CONNECTION_RECYCLE_SECONDS  = int(os.getenv("OTOGALERI_DB_RECYCLE", "3600"))
DB_QUERY_TIMEOUT               = int(os.getenv("OTOGALERI_DB_TIMEOUT", "20"))
RETRY_MAX_ATTEMPTS             = int(os.getenv("OTOGALERI_RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_FACTOR           = int(os.getenv("OTOGALERI_RETRY_BACKOFF", "2"))

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
