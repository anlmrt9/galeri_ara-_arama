"""
config.py - OtoGaleriBot Merkezi Ayarlar
=========================================
Tüm sabitler, veritabanı bilgileri, bekleme süreleri ve
ortam değişkeni override'ları burada tutulur.
"""

import os

# ---------- VERITABANI ----------
DB_SERVER = os.environ.get("OTOGALERI_DB_SERVER", r"MERTPC\SQLEXPRESS")
DB_NAME = os.environ.get("OTOGALERI_DB_NAME", "OtoGaleriDB")

# ---------- SCRAPER AYARLARI ----------
SCRAPER_REQUEST_TIMEOUT = int(os.environ.get("OTOGALERI_TIMEOUT", "15"))
SCRAPER_PAGE_WAIT_SEC = int(os.environ.get("OTOGALERI_PAGE_WAIT", "2"))
SCRAPER_SELENIUM_WAIT_SEC = int(os.environ.get("OTOGALERI_SELENIUM_WAIT", "5"))
SCRAPER_CYCLE_INTERVAL_SEC = int(os.environ.get("OTOGALERI_CYCLE_INTERVAL", "60"))
MAX_NEW_LISTINGS_PER_CYCLE = int(os.environ.get("OTOGALERI_MAX_NEW", "5"))

# ---------- DB POOL ----------
DB_POOL_SIZE = int(os.environ.get("OTOGALERI_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.environ.get("OTOGALERI_MAX_OVERFLOW", "10"))

# ---------- SITE İSİMLERİ ----------
SITE_OTOPLUS = "Otoplus"
SITE_VAVACARS = "VavaCars"
SITE_OTOKOC = "Otokoç 2. El"
SITE_ARABAM = "Arabam.com"
SITE_SAHIBINDEN = "Sahibinden"

ALL_SITES = [SITE_OTOPLUS, SITE_VAVACARS, SITE_OTOKOC, SITE_ARABAM, SITE_SAHIBINDEN]

# ---------- BİLDİRİM ----------
# Aynı site için hata bildirimi cooldown süresi (dakika)
SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES = int(os.environ.get("OTOGALERI_FAILURE_COOLDOWN", "15"))

# ---------- LOG DOSYASI ----------
LOG_FILE = os.environ.get("OTOGALERI_LOG_FILE", "otogaleri_log.txt")
