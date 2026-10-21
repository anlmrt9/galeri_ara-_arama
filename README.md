# OtoGaleri Avcı Botu

[![CI](https://github.com/anlmrt9/galeri_ara-_arama/actions/workflows/ci.yml/badge.svg)](https://github.com/anlmrt9/galeri_ara-_arama/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Belirlediğiniz kriterlere (marka, model, fiyat, yıl, km, parça bazlı boya/değişen,
tramer) uyan ikinci el araç ilanlarını **Otoplus, Otokoç 2. El, Arabam.com ve
VavaCars**'ta periyodik olarak tarayan; yeni ilan ve **fiyat düşüşlerini** masaüstü,
Telegram veya e-posta ile bildiren bir tedarik (sourcing) botu.

## Özellikler

- **Yapılandırılmış ekspertiz okuma:** Hasar bilgisi sayfa metninde kelime aranarak
  değil, sitelerin kendi ekspertiz verisinden (Otoplus `inspection`, Otokoç
  `appearances`, Arabam `window.damage`) parça parça okunur.
- **Parça bazlı hasar toleransı:** 13 kaporta parçası için "orijinal olmalı / boya
  kabul / değişen kabul" seçimi. Çizik ve ezik gibi kozmetik kusurlar eleme sebebi
  değildir. Tramer limiti de belirlenebilir.
- **Fiyat geçmişi ve fiyat düşüşü bildirimi:** Kayıtlı ilanların fiyatı her turda
  izlenir, düşüş olunca bildirim gönderilir.
- **Fırsat skoru:** Aynı marka, model ve yıldaki kayıtlı ilanların medyanına göre
  "piyasanın %X altında" etiketi.
- **Dayanıklı tarama:** Taramalar veritabanı kuyruğundaki işlerdir. Sayfa yenilense,
  sekme kapansa ya da süreç yeniden başlasa da iş kaldığı yerden devam eder ve her
  zaman durdurulabilir. İsterseniz ayrı bir worker sürecinde çalışır.
- **Kanal sağlığı:** Her sitenin son tarama sonucu (bulunan/uygun/yeni ilan sayısı,
  hata) arayüzde görünür.
- **REST API + mobil uygulama**, PWA desteği, Docker Compose yığını.
- **Üç veritabanı:** PostgreSQL / Supabase, SQL Server ve SQLite. Sıfır kurulumla
  SQLite kullanılır. Şema Alembic migration'larıyla yönetilir.

## Hızlı başlangıç

```bash
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Hiçbir ayar yapmazsanız veriler proje kökündeki `otogaleri.db` (SQLite) dosyasına
yazılır ve tarama Streamlit süreci içinde çalışır. Ayarlar için:
`cp .env.example .env`.

### Docker Compose (PostgreSQL + API + arayüz + worker)

```bash
cp .env.example .env     # OTOGALERI_API_KEY ve POSTGRES_PASSWORD'ü değiştirin
docker compose up --build
```

| Servis | Adres | Görev |
|---|---|---|
| `web` | http://localhost:8501 | Streamlit arayüzü |
| `api` | http://localhost:8000/docs | REST API (OpenAPI belgeleri) |
| `worker` | — | Taramaları yürüten ayrı süreç |
| `db` | 127.0.0.1:5432 | PostgreSQL 16 |

## Mimari

```
app.py (Streamlit) ─┐                       ┌─> scrapers/  (site başına bir sınıf)
                    ├─> ScanManager ──> scan_jobs ──> Worker ──> ScanEngine ─┤
api.py (FastAPI) ───┘   (iş oluştur/durdur)  (DB kuyruğu)        (tur)      ├─> Repository (listings, price_history, site_runs)
                                                                            └─> Notifier (masaüstü / Telegram / e-posta)
```

| Modül | Görev |
|---|---|
| `otogaleri/config.py` | `pydantic-settings` ile tüm ayarlar, site listesi, marka/model kataloğu |
| `otogaleri/damage.py` | Parça adı normalizasyonu, hasar sınıflandırma, filtre kararı |
| `otogaleri/scrapers/` | `otoplus`, `otokoc`, `arabam`, `vavacars`: saf `parse_*` fonksiyonları + `Scraper` sınıfları |
| `otogaleri/http.py` | Retry, 429 `Retry-After`, 403/404'te hemen vazgeçme, istekler arası bekleme |
| `otogaleri/db.py` | SQLAlchemy Core şeması, engine fabrikası, `Repository` (upsert, fiyat geçmişi, iş kuyruğu) |
| `otogaleri/scan.py` | `ScanCriteria` (doğrulamalı kriter modeli) ve `ScanEngine` (tek tur) |
| `otogaleri/worker.py` | `Worker` (heartbeat'li iş yürütücü) ve `ScanManager` (UI/API cephesi) |
| `otogaleri/notifications.py` | Bildirim kanalları ve site hatası cooldown'u |
| `otogaleri/scoring.py` | Piyasa medyanı ve fırsat skoru |
| `otogaleri/api.py` | FastAPI: kimlik doğrulama, hız sınırı, güvenlik başlıkları |
| `migrations/` | Alembic migration'ları (eski `Cars` tablosundaki veriler otomatik aktarılır) |

## Desteklenen siteler

| Site | Yöntem | Hasar verisi | Tramer |
|---|---|---|---|
| Otoplus | HTTP + JSON-LD / Next.js verisi | Ekspertiz raporu (13 parça) | — |
| Otokoç 2. El | HTTP + Next.js verisi | Ekspertiz raporu | — |
| Arabam.com | HTTP + JSON-LD + `window.damage` | Satıcı beyanı | ✓ |
| VavaCars | Headless Chrome (SeleniumBase) | Yalnızca "boyasız/değişensiz/tramersiz" rozeti | ✓ (rozetliyse 0) |
| Sahibinden | Headless Chrome (SeleniumBase), tur başına ≤6 detay sayfası | Satıcı beyanı (13 parça) + ağır hasar kaydı | — |

**Sahibinden hakkında:** sahibinden.com düz HTTP isteklerini Cloudflare ile
engelliyor. Bu yüzden VavaCars gibi gerçek bir headless Chrome ile, sayfalar arasında
bekleyerek ve tur başına sınırlı sayıda detay sayfası açarak okunuyor. Captcha
çözülmüyor ve proxy döndürülmüyor; doğrulama sayfası gelirse o tur atlanıp bildirim
gönderiliyor. sahibinden.com kullanım şartları otomatik veri toplamayı kısıtlıyor;
aracı kişisel ölçekte ve düşük sıklıkta kullanın.

Siteler yapılarını değiştirdiğinde ilk olarak `tests/test_parsers.py` kırılır.
`tests/fixtures/` altındaki örnek sayfaları yenileyip beklentileri güncellemek
yeterlidir.

## Yapılandırma

Tüm değişkenler ve açıklamaları `.env.example` dosyasında. En önemlileri:

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL/Supabase URL'si (öncelikli) |
| `OTOGALERI_DB_SERVER` / `OTOGALERI_DB_NAME` | — / `OtoGaleriDB` | Yerel SQL Server (Windows Authentication) |
| `OTOGALERI_SQLITE_PATH` | `otogaleri.db` | Yukarıdakiler boşsa kullanılır |
| `OTOGALERI_CYCLE_INTERVAL` | `300` | Turlar arası bekleme (sn) |
| `OTOGALERI_MAX_PAGES` / `OTOGALERI_MAX_DETAIL` | `3` / `15` | Site başına liste sayfası / tur başına detay sayfası |
| `OTOGALERI_EMBEDDED_WORKER` | `true` | `false` ise `python -m otogaleri.worker` ayrıca çalıştırılmalı |
| `OTOGALERI_TELEGRAM_BOT_TOKEN` / `_CHAT_ID` | — | Telegram bildirimi |
| `OTOGALERI_SMTP_*` | — | E-posta bildirimi |
| `OTOGALERI_API_KEY` | — | Boşsa API yalnızca localhost'tan erişilebilir |

## REST API

| Uç | Açıklama |
|---|---|
| `GET /api/health` | Sürüm, DB bağlantısı, kimlik doğrulama modu |
| `GET /api/config` | Siteler, katalog, hasar parçaları |
| `GET /api/listings?limit=&offset=&site=&only_new=` | İlanlar (fırsat skoruyla) |
| `GET /api/listings/{id}/price-history` | Fiyat geçmişi |
| `DELETE /api/listings` | Tüm ilanları sil |
| `GET /api/stats` | Site bazında sayılar ve kanal sağlığı |
| `GET /api/scan/status` · `POST /api/scan/start` · `POST /api/scan/stop` | Tarama yönetimi |

Korumalı uçlar `X-API-Key` başlığı ister. Anahtar tanımlı değilse yalnızca
localhost'tan gelen istekler kabul edilir. Her IP için dakikada 120 istek sınırı
vardır. Mobil uygulamayı yerel ağdan bağlıyorsanız bir `OTOGALERI_API_KEY`
tanımlayın ve uygulamanın isteklerine bu başlığı ekleyin.

## Geliştirme

```bash
pip install -r requirements-dev.txt
pre-commit install
ruff check . && black --check . && mypy && pytest --cov
```

Testler ağa çıkmaz. Siteler kaydedilmiş HTML örnekleriyle, veritabanı geçici
SQLite ile, arayüz ise `streamlit.testing.AppTest` ile test edilir. CI aynı
repository/worker testlerini gerçek PostgreSQL üzerinde de çalıştırır.
Ayrıntılar için `CONTRIBUTING.md`.

## Sorumluluk

Bu araç yalnızca herkese açık ilan sayfalarını okur. İstekler arasında bekler ve
tur başına sınırlı sayıda sayfa açar. Hedef sitelerin kullanım şartlarına uymak
kullanıcının sorumluluğundadır.
