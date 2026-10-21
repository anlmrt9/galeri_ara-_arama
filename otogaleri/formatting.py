"""UI'dan bağımsız biçimlendirme yardımcıları (saf fonksiyonlar)."""

from __future__ import annotations

from datetime import datetime, timezone


def format_number(value: object) -> str:
    """``1650000`` → ``"1.650.000"`` (Türkçe binlik ayırıcı). Geçersiz değerde ``"-"``."""
    try:
        number = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"
    return f"{number:,}".replace(",", ".")


def format_price(value: object) -> str:
    """``1650000`` → ``"1.650.000 ₺"``."""
    text = format_number(value)
    return text if text == "-" else f"{text} ₺"


def format_try(value: object) -> str:
    """``34980.5`` → ``"34.980,50"`` (binlik ``.``, ondalık ``,``); geçersizde ``"0,00"``."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0,00"
    return f"{number:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def to_local(dt: datetime | None) -> datetime | None:
    """Veritabanındaki saat dilimsiz UTC zamanı makinenin yerel saatine çevirir."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def humanize_delta(dt: datetime | None, now: datetime | None = None) -> str:
    """UTC zaman damgası için ``"3 dk önce"`` / ``"2 sa sonra"`` gibi kısa metin."""
    if dt is None:
        return "-"
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    seconds = int((now - dt).total_seconds())
    suffix = "önce" if seconds >= 0 else "sonra"
    seconds = abs(seconds)
    if seconds < 60:
        return "az önce" if suffix == "önce" else "birazdan"
    if seconds < 3600:
        return f"{seconds // 60} dk {suffix}"
    if seconds < 86400:
        return f"{seconds // 3600} sa {suffix}"
    return f"{seconds // 86400} gün {suffix}"
