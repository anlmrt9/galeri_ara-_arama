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
