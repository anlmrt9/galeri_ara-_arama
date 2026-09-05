"""
logger_setup.py - Merkezi Logger Konfigürasyonu
=================================================
Konsol + döner (rotating) dosya çıktısı üreten tek bir ``logger`` objesi sağlar.
Tüm modüller buradan import edilen ``logger``'ı kullanır.

Ayarlar ``config.settings`` üzerinden (ortam değişkeni / ``.env``):
    OTOGALERI_LOG_LEVEL         (varsayılan INFO)
    OTOGALERI_LOG_FILE          (varsayılan otogaleri_log.txt)
    OTOGALERI_LOG_MAX_BYTES     (varsayılan 5 MB)
    OTOGALERI_LOG_BACKUP_COUNT  (varsayılan 3)
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config import settings

_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"

logger = logging.getLogger("OtoGaleri")
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
logger.propagate = False

if not logger.handlers:
    _formatter = logging.Formatter(_FORMAT)

    _console = logging.StreamHandler()
    _console.setFormatter(_formatter)
    logger.addHandler(_console)

    try:
        _file = RotatingFileHandler(
            settings.log_file,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        _file.setFormatter(_formatter)
        logger.addHandler(_file)
    except OSError as exc:  # dosya sistemi salt-okunur / izin yok (ör. bazı bulut ortamları)
        logger.warning("Log dosyasi olusturulamadi (%s): %s", settings.log_file, exc)
