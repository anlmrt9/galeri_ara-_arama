# Değişiklik Günlüğü

Bu projedeki tüm önemli değişiklikler bu dosyada belgelenir.

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) temellidir ve
proje [Semantic Versioning](https://semver.org/lang/tr/) kullanır.

## [Unreleased]

### Düzeltildi

- **Arayüzde `NotFoundError: removeChild` çökmesi:** Streamlit sayfayı `lang="en"` ile
  sunduğu için Chrome Türkçe içeriği otomatik çeviriyor, değiştirdiği DOM düğümleri
  yüzünden React çöküyordu. Sayfa dili `tr` yapıldı, çeviri `translate="no"` ve
  `google=notranslate` ile kapatıldı.

### Eklendi

- **Sahibinden desteği:** Diğer siteler gibi aranacak siteler listesinden seçilebiliyor.
  Cloudflare yüzünden headless Chrome (SeleniumBase) ile okunuyor: liste sayfası (marka,
  seri, model, yıl, km, fiyat, il/ilçe) + detay sayfasındaki 13 parçalık boya/değişen
  haritası ve "Ağır Hasar Kayıtlı" beyanı. Tur başına en fazla 6 detay sayfası açılıyor;
  doğrulama ya da "Access denied" (PerimeterX) engel sayfası gelirse captcha çözülmüyor;
  site 60 dk boyunca hiç istenmiyor ve bildirim gönderiliyor.
- "Ağır hasar kayıtlı" ilanlar hasar toleransından bağımsız olarak eleniyor.
- **Tarama planı:** süre seçenekleri (1 saat … 1 hafta, **Ben durdurana kadar**) ve
  tarama sıklığı (5 dk … 1 saat) artık iş başına seçiliyor. Bitiş zamanı ve
  yaklaşık tur sayısı önceden gösteriliyor, aktif taramada **kalan süre** görünüyor.
  API: `duration_hours: null` (süresiz) ve `cycle_interval_min`.

## [2.0.0] - 2026-10-21

Proje `otogaleri/` paketi altında yeniden yapılandırıldı. Çalışma dizininin 1.0
öncesi dosyalarla üzerine yazılması sonucu oluşan bozuk durum (testlerin toplanamaması,
API'nin başlamaması) giderildi.

### Düzeltildi

- **Hasar filtresi bütün Otoplus ilanlarını eliyordu.** Otoplus her ilanda "Boyalı 0 /
  Değişen 0" yazdığı için sayfa metninde "boya" aramak, hasarsız araç istendiğinde
  hepsini reddediyordu. Hasar artık sitelerin yapılandırılmış ekspertiz verisinden
  parça parça okunuyor.
- **Otokoç scraper'ı hiç çalışmıyordu:** Site `__NEXT_DATA__`'dan Next.js App Router
  akışına geçmiş. Yeni ayrıştırıcı liste ve ekspertiz verisini bu akıştan okuyor.
- **Otoplus marka filtresi 404 dönüyordu** (`/ikinci-el-araba/<marka>` artık yok).
  Genel liste taranıp marka/model filtresi yerelde uygulanıyor. Model adı da artık
  doluyor (önceden hep boştu).
- **Otoplus yalnızca eski sayfaları tarıyordu:** Checkpoint her turda sayfa
  numarasını ilerletiyordu, yeni ilanların çıktığı ilk sayfaya hiç dönülmüyordu.
- **Arabam.com yıl/km alanlarına arama kriterini yazıyordu** (gerçek değer yerine)
  ve yalnızca ilk 3 ilana bakıyordu. Artık JSON-LD ve `window.damage` okunuyor,
  tarayıcı gerekmiyor, tramer bilgisi alınıyor.
- **Sahibinden her turda `TypeError` ile çöküyor ve hata bildirimi atıyordu.**
  Site listeden çıkarıldı (devre dışı olarak işaretli).
- **Arayüzde depolanmış XSS:** İlan başlığı ve linki kaçışsız HTML olarak
  basılıyordu. Artık kaçışlanıyor ve yalnızca `http(s)` linklere izin veriliyor.
- **Sahipsiz tarama thread'leri:** Sayfa yenilenince tarama durdurulamaz hâle
  geliyor, birden çok sekme paralel tarama başlatabiliyordu.
- `listing_id` siteler arası benzersizdi; aynı ID'yi kullanan iki sitenin ilanı
  çakışıyordu. Artık anahtar `(source_site, listing_id)`.
- Kontrol edip sonra ekleme yarışı (`listing_exists` → `insert_car`) yerine upsert.

### Eklendi

- **Ayrı worker ve veritabanı iş kuyruğu** (`scan_jobs`): heartbeat ile sahiplik,
  süreç ölünce devralma, gömülü veya `python -m otogaleri.worker` modu.
- **Fiyat geçmişi** (`price_history`) ve **fiyat düşüşü bildirimi**.
- **Fırsat skoru:** marka/model/yıl medyanına göre "piyasanın %X altında".
- **Telegram ve e-posta (SMTP) bildirim kanalları**; kanallar birbirinden yalıtılmış.
- **Kanal sağlığı** (`site_runs`): her sitenin son tur sonucu arayüzde ve `/api/stats`'ta.
- **Alembic migration'ları**; eski `Cars` tablosundaki ilanlar otomatik aktarılır.
- **SQLite desteği** (ayar yoksa varsayılan), PostgreSQL ve SQL Server ile birlikte.
- API: sayfalama, `/api/listings/{id}/price-history`, `/api/stats`, hız sınırı,
  güvenlik başlıkları.
- Arayüz: sekmeler (Tarama / İlanlar / Piyasa), arama ve fırsat filtresi, CSV dışa
  aktarma, fiyat geçmişi grafiği, onaylı silme, karanlık mod uyumu, erişilebilir
  hasar haritası (klavye, `aria-label`, seçimi koruma).
- JSON log seçeneği ve opsiyonel Sentry entegrasyonu.
- Testler: gerçek sayfalardan alınmış fixture'larla parser testleri, repository,
  worker, API, bildirim, HTTP retry ve Streamlit `AppTest` testleri (154 test,
  %86 kapsam). CI'a PostgreSQL ve Docker build işleri eklendi.

### Değişti

- **API varsayılan olarak yalnızca localhost'a açık.** Uzaktan erişim için
  `OTOGALERI_API_KEY` gerekir. Bu, 1.x davranışından farklıdır: mobil uygulama
  yerel ağdan bağlanıyorsa anahtar tanımlanmalıdır. CORS varsayılan olarak kapalı.
- Varsayılan veritabanı kişisel `MERTPC\SQLEXPRESS` yerine SQLite. SQL Server için
  `OTOGALERI_DB_SERVER` verilmelidir.
- Tur aralığı varsayılanı 60 sn → 300 sn (siteleri yormamak için).
- Docker imajı root olmayan kullanıcıyla çalışıyor; `HEALTHCHECK` ve `.dockerignore`
  eklendi; compose'a `worker` servisi eklendi.
- Kaldırıldı: `dashboard.py` (eski Otoplus panosu, ücretsiz proxy listesi
  kullanıyordu), `test_system.py`, `templates/`, `static/style.css`, eski
  `checkpoint` (`scan_sessions`) mekanizması.

## [1.1.0] - 2026-09-06

### Düzeltildi

- **PostgreSQL'de ilan ekleme:** `insert_car` artık `is_new_listing` alanını
  gerçek bir `bool`'a çeviriyor. Scraper'lar bu alanı `1` tamsayısı olarak
  veriyordu; SQL Server BIT kabul ediyor ama PostgreSQL BOOLEAN sütunu
  `DatatypeMismatch` ile reddediyordu — yani bulut/Supabase kurulumunda hiçbir
  ilan kaydedilemiyordu.
- `OTOGALERI_NOTIFICATIONS_ENABLED` ayarı artık gerçekten uygulanıyor. Önceden
  tanımlı ve belgeliydi ama hiçbir yerde okunmuyordu; `false` verildiğinde hem
  yeni araç bildirimi hem site hatası bildirimi sessizce atlanıyor.
- Retry dekoratörleri (`db.retry_on_db_error`, `scrapers.retry_http_request`)
  hatalı yapılandırmada (`max_*=0`) `raise None` yerine anlaşılır bir
  `RuntimeError` yükseltiyor.

### Değişti

- **Araç hasar haritası yeniden tasarlandı** (`car_map_component/index.html`):
  kutu ızgarası yerine oto ekspertiz raporu tarzı çok görünümlü SVG şema
  (ön / arka / sol yan / sağ yan / üstten) ve O/B/D rozetleri. Aynı 13 parça
  anahtarı ve 3 durumlu tıklama davranışı korundu; "Orijinal" rengi griden
  yeşile çevrildi. Tarayıcı otomatik çevirisine karşı `translate="no"`.
- Sayfa getirmede jenerik `raise Exception(...)` yerine adlandırılmış
  `scrapers.ScraperHTTPError`.
- `db.py`, `scrapers.py`, `notifications.py` içindeki tüm logger çağrıları lazy
  `%` biçimine geçirildi (f-string yerine) — tutarlılık ve `ruff` `G` kuralı.
- REST API sürümü artık paket meta verisinden okunuyor
  (`importlib.metadata`), tek kaynak.
- Geliştirme sürecinden kalan iç notlar temizlendi ("GÖREV n", "BUG FIX"
  etiketleri; modül docstring'leri yeniden yazıldı).

### Eklendi

- Depo hijyeni: `CONTRIBUTING.md`, `SECURITY.md`, `.editorconfig`,
  `.github/dependabot.yml`, issue ve PR şablonları.
- Testler: bildirim kill-switch'i, `ScanManager` thread yaşam döngüsü, retry
  sıfır-deneme koruması.
- Coverage yapılandırması (`[tool.coverage]`), CI'da `--cov-fail-under=38`.

### Araçlar / CI

- `ruff` kural seti genişletildi: `BLE`, `G`, `LOG`, `PT`, `RET`, `PIE`,
  `RUF`, `PLE`/`PLW`/`PLC`.
- `mypy` artık CI'da bloke edici (`continue-on-error` kaldırıldı) ve
  `notifications`, `logger_setup`, `format_utils` de sıkı tip kapsamında.
- CI Python 3.10–3.13 matrisinde çalışıyor; `permissions` ve `concurrency`
  eklendi.

## [1.0.0]

- İlk kararlı sürüm: çoklu site taraması (Otoplus, VavaCars, Otokoç,
  Arabam.com, Sahibinden), Streamlit arayüzü, FastAPI REST backend'i, paylaşılan
  `scan_service` katmanı, `pydantic-settings` yapılandırması, PostgreSQL /
  SQL Server desteği, checkpoint takibi, retry dekoratörleri, masaüstü
  bildirimleri, PWA katmanı, Docker Compose yığını, pytest + ruff + black +
  mypy + pre-commit + GitHub Actions.

[Unreleased]: https://github.com/anlmrt9/galeri_ara-_arama/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/anlmrt9/galeri_ara-_arama/compare/v1.1.0...v2.0.0
[1.1.0]: https://github.com/anlmrt9/galeri_ara-_arama/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/anlmrt9/galeri_ara-_arama/releases/tag/v1.0.0
