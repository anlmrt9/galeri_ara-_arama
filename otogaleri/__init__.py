"""OtoGaleri Avcı Botu — ikinci el araç ilanı tedarik (sourcing) botu.

Paket düzeni:

* ``config``         — ortam değişkeni / ``.env`` tabanlı ayarlar, site & katalog sabitleri
* ``damage``         — parça adı normalizasyonu, hasar sınıflandırma ve filtre değerlendirmesi
* ``models``         — ``Listing`` veri modeli
* ``http``           — retry / rate-limit farkındalıklı HTTP istemcisi
* ``scrapers``       — her site için ayrı, saf ayrıştırıcılı scraper sınıfları
* ``db``             — SQLAlchemy Core şeması, engine fabrikası, ``Repository``
* ``scan``           — ``ScanCriteria``, tek tur tarama motoru (``ScanEngine``)
* ``worker``         — veritabanı kuyruklu tarama işçisi + ``ScanManager`` cephesi
* ``notifications``  — masaüstü / Telegram / e-posta bildirim kanalları
* ``scoring``        — piyasa medyanı ve fırsat skoru
* ``api``            — FastAPI REST katmanı
"""

__version__ = "2.0.0"
