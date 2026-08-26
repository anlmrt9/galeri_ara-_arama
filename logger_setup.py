"""
logger_setup.py - Merkezi Logger Konfigürasyonu
=================================================
Konsol + dosya çıktısı üreten tek bir logger objesi sağlar.
Tüm modüller buradan import edilen logger'ı kullanır.
"""

import logging
from config import LOG_FILE

logger = logging.getLogger("OtoGaleri")
logger.setLevel(logging.INFO)

if not logger.handlers:
    # Konsol handler
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logger.addHandler(ch)

    # Dosya handler
    try:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
        logger.addHandler(fh)
    except Exception as e:
        logger.warning(f"Log dosyasi olusturulamadi ({LOG_FILE}): {e}")
