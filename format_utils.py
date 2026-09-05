"""
format_utils.py - Küçük biçimlendirme yardımcıları
==================================================
UI katmanından bağımsız, saf fonksiyonlar (test edilebilir).
"""

from __future__ import annotations


def format_try(value: object) -> str:
    """Sayıyı Türk Lirası yerel biçimine çevirir.

    ``34980.5`` -> ``"34.980,50"``   (binlik ``.``, ondalık ``,``)
    Geçersiz/boş değerlerde ``"0,00"`` döner.
    """
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0,00"
    # 1,234,567.89 (US) -> 1.234.567,89 (TR)
    return f"{number:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
