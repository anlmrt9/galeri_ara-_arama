"""Scraper sözleşmesi.

Her site iki adımda taranır:

1. :meth:`Scraper.search` — liste sayfalarından ilan *özetleri* (fiyat, yıl, km, link).
   Bu adım ucuzdur; fiyat değişimi takibi için zaten bilinen ilanlar da döner.
2. :meth:`Scraper.enrich` — yalnızca *yeni* ve temel filtreye uyan ilanlar için detay
   sayfasından hasar/tramer bilgisi.

Ayrıştırma mantığı her sitede ``parse_*`` saf fonksiyonlarındadır; HTML fixture'ları
ile ağsız test edilir (``tests/fixtures``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from otogaleri.config import ANY
from otogaleri.http import HttpClient
from otogaleri.models import Listing


@dataclass(frozen=True)
class SearchQuery:
    """Scraper'ın URL kurarken kullanabileceği (opsiyonel) sunucu tarafı filtreler."""

    brand: str = ANY
    model: str = ANY
    min_price: float | None = None
    max_price: float | None = None
    min_year: int | None = None
    max_year: int | None = None
    max_pages: int = 3

    @property
    def has_brand(self) -> bool:
        return bool(self.brand) and self.brand != ANY


class Scraper(ABC):
    #: ``config.SITES`` içindeki ad
    site: str = ""
    #: Headless tarayıcı gerektiriyor mu (worker bunu bir kez açıp paylaştırır)
    requires_browser: bool = False
    #: Tur başına açılacak detay sayfası üst sınırı (``None`` → genel ayar)
    max_details: int | None = None

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()

    @abstractmethod
    def search(self, query: SearchQuery) -> Iterator[Listing]:
        """Liste sayfalarındaki ilan özetlerini üretir."""

    def enrich(self, listing: Listing) -> Listing:
        """Detay sayfasından hasar/tramer bilgisini doldurur (varsayılan: değişiklik yok)."""
        return listing

    def close(self) -> None:  # noqa: B027 - opsiyonel kanca, varsayılan no-op
        """Tarayıcı vb. kaynakları serbest bırakır."""
