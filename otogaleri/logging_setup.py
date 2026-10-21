"""Merkezi log yapılandırması.

* Konsol + boyutla dönen (rotating) dosya çıktısı
* ``OTOGALERI_LOG_JSON=true`` ile tek satır JSON (log toplayıcılar için)
* ``OTOGALERI_SENTRY_DSN`` tanımlı ve ``sentry-sdk`` kuruluysa hata takibi

Modüller ``logging.getLogger(__name__)`` kullanır; hepsi ``otogaleri`` kök
logger'ına bağlıdır. :func:`configure_logging` idempotenttir.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from otogaleri.config import Settings, get_settings

ROOT_LOGGER = "otogaleri"
_TEXT_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_configured = False


class JsonFormatter(logging.Formatter):
    """Her kaydı tek satır JSON olarak yazar."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings | None = None) -> logging.Logger:
    """Kök ``otogaleri`` logger'ını bir kez yapılandırır ve döndürür."""
    global _configured
    logger = logging.getLogger(ROOT_LOGGER)
    if _configured:
        return logger
    settings = settings or get_settings()

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False
    formatter: logging.Formatter = (
        JsonFormatter() if settings.log_json else logging.Formatter(_TEXT_FORMAT)
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    if settings.log_file:
        try:
            file_handler = RotatingFileHandler(
                settings.log_file,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:  # salt-okunur dosya sistemi (bazı bulut ortamları)
            logger.warning("Log dosyasi olusturulamadi (%s): %s", settings.log_file, exc)

    if settings.sentry_dsn:
        _init_sentry(settings.sentry_dsn, logger)

    _configured = True
    return logger


def _init_sentry(dsn: str, logger: logging.Logger) -> None:
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("OTOGALERI_SENTRY_DSN tanimli ama 'sentry-sdk' kurulu degil.")
        return
    from otogaleri import __version__

    sentry_sdk.init(dsn=dsn, release=f"otogaleri@{__version__}", traces_sample_rate=0.0)
    logger.info("Sentry hata takibi etkin.")
