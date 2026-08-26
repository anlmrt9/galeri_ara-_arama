"""
notifications.py - Masaüstü Bildirim Sistemi
===============================================
Yeni araç bulunduğunda ve site taramasında hata oluştuğunda
kullanıcıya Windows toast bildirimi gönderir.
Windows dışı platformlarda logger.warning ile loga düşer.
"""

import platform
from datetime import datetime
from config import SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES
from logger_setup import logger

# Cooldown: {site_name: son_bildirim_zamanı} — aynı site için art arda spam önlenir
_failure_notify_last_sent = {}


def send_desktop_notification(brand, model, price, painted_parts):
    """Yeni araç bulunduğunda masaüstü bildirimi gönderir."""
    title = "🚨 Yeni Araç Yakalandı!"
    # price güvenli format: None veya hatalı veri gelirse patlamasın
    try:
        price_str = f"{int(price):,}"
    except (TypeError, ValueError):
        price_str = str(price)

    message = f"{brand} {model}\nFiyat: {price_str} TL\nBoya/Değişen: {painted_parts}"

    if platform.system() == "Windows":
        try:
            from win11toast import toast
            toast(title, message, app_id="OtoGaleri Avcı Bot")
        except Exception as e:
            logger.error(f"Bildirim gonderilemedi: {e}")
    else:
        logger.warning(f"[Bildirim] {title}: {message}")


def send_site_failure_notification(site_name, reason):
    """
    Bir sitenin genel taraması başarısız olduğunda masaüstü bildirimi gönderir.
    Cooldown: Aynı site için SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES dakika içinde
    tekrar bildirim göndermez (spam önleme).
    """
    now = datetime.now()

    # Cooldown kontrolü
    last_sent = _failure_notify_last_sent.get(site_name)
    if last_sent:
        elapsed_minutes = (now - last_sent).total_seconds() / 60
        if elapsed_minutes < SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES:
            logger.info(
                f"[Bildirim] {site_name} hata bildirimi cooldown'da "
                f"(kalan: {SITE_FAILURE_NOTIFY_COOLDOWN_MINUTES - elapsed_minutes:.0f} dk)"
            )
            return

    # Cooldown geçti veya ilk bildirim, gönder
    _failure_notify_last_sent[site_name] = now

    title = f"⚠️ {site_name} taramasında sorun var"
    # Sebep metnini kısalt (toast çok uzun metni kesebilir)
    short_reason = str(reason)[:200] if reason else "Bilinmeyen hata"
    message = f"Sebep: {short_reason}"

    if platform.system() == "Windows":
        try:
            from win11toast import toast
            toast(title, message, app_id="OtoGaleri Avcı Bot")
        except Exception as e:
            logger.error(f"Site hata bildirimi gonderilemedi: {e}")
    else:
        logger.warning(f"[Bildirim] {title}: {message}")
