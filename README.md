# OtoGaleri Avcı Botu

Belirlediğiniz kriterlere (marka, model, fiyat, yıl, kilometre, tramer) uyan ikinci el araç ilanlarını birden fazla galeri/pazaryeri sitesinden otomatik olarak tarayan, yeni ilan bulunduğunda masaüstü bildirimi gönderen ve sonuçları bir Streamlit arayüzünde listeleyen bir tedarik (sourcing) botu.

## Özellikler

- **Çoklu site taraması:** Otoplus, VavaCars, Otokoç 2. El, Arabam.com ve Sahibinden üzerinde eş zamanlı arama.
- **Filtreli arama:** Marka/model, min-max fiyat, min-max yıl, min-max kilometre ve maksimum kabul edilen tramer bedeline göre filtreleme.
- **Arka planda tarama:** Belirlenen süre boyunca (varsayılan döngü aralığıyla) periyodik olarak tekrar taranır; `threading` ile arayüzü kilitlemeden çalışır.
- **Masaüstü bildirimleri:** Yeni araç bulunduğunda veya bir sitenin taraması başarısız olduğunda Windows toast bildirimi gönderir (Windows dışı ortamlarda log'a düşer).
- **Checkpoint / oturum takibi:** Her tarama oturumu `session_id` ile izlenir, sayfa bazlı ilerleme `scan_sessions` tablosunda saklanır.
- **Otomatik yeniden deneme:** Veritabanı ve HTTP istekleri için exponential backoff ile retry mekanizması.
- **SQL Server tabanlı depolama:** Bulunan ilanlar `Cars` tablosunda saklanır, tekrarlanan ilanlar `listing_id` ile filtrelenir.

## Proje Yapısı

| Dosya | Açıklama |
|---|---|
| `app.py` | Ana Streamlit arayüzü. Kriter formu, tarama başlat/durdur kontrolü ve sonuç tablosu. |
| `scrapers.py` | Her site için scraping fonksiyonları ve `run_one_cycle` döngüsü. |
| `db.py` | SQLAlchemy/pyodbc ile SQL Server erişimi (tablo oluşturma, CRUD, checkpoint). |
| `notifications.py` | Windows toast bildirim gönderimi (yeni araç / site hatası). |
| `config.py` | Ortam değişkenleriyle override edilebilen merkezi ayarlar (DB, timeout, site listesi vb.). |
| `logger_setup.py` | Uygulama genelinde kullanılan logger yapılandırması. |
| `dashboard.py` | Otoplus'a özel, kendi içinde scraping yapan alternatif/eski Streamlit panosu (`streamlit run dashboard.py`). |
| `car_map_component/` | Araç konumlarını haritada göstermek için kullanılan HTML bileşeni. |
| `test_system.py` | Veritabanı bağlantısı gibi temel sistem kontrolleri için basit test betiği. |

## Gereksinimler

- Python 3.10+
- Microsoft SQL Server (yerel veya erişilebilir bir örnek) ve **ODBC Driver 17 for SQL Server**
- Windows (masaüstü bildirimleri için; diğer platformlarda bildirimler yerine log kaydı düşer)

Gerekli Python paketleri (proje içinde `requirements.txt` bulunmuyor, aşağıdaki paketleri kurmanız gerekir):

```bash
pip install streamlit streamlit-autorefresh pandas plotly sqlalchemy pyodbc curl_cffi beautifulsoup4 win11toast
```

## Kurulum

1. Depoyu/klasörü indirin ve klasöre girin.
2. Yukarıdaki bağımlılıkları kurun.
3. SQL Server'ın çalıştığından ve `Trusted_Connection` (Windows Authentication) ile erişilebilir olduğundan emin olun. Gerekirse aşağıdaki ortam değişkenleriyle bağlantı bilgilerini özelleştirin:

   | Değişken | Varsayılan | Açıklama |
   |---|---|---|
   | `OTOGALERI_DB_SERVER` | `MERTPC\SQLEXPRESS` | SQL Server adresi |
   | `OTOGALERI_DB_NAME` | `OtoGaleriDB` | Veritabanı adı (yoksa otomatik oluşturulur) |
   | `OTOGALERI_TIMEOUT` | `15` | HTTP istek timeout (saniye) |
   | `OTOGALERI_CYCLE_INTERVAL` | `60` | Tarama döngüleri arası bekleme (saniye) |
   | `OTOGALERI_MAX_NEW` | `5` | Döngü başına eklenecek maksimum yeni ilan |
   | `OTOGALERI_FAILURE_COOLDOWN` | `15` | Aynı site için hata bildirimi tekrar aralığı (dakika) |

   Diğer ayarlar için `config.py` dosyasına bakın.

## Çalıştırma

```bash
streamlit run app.py
```

Uygulama açıldıktan sonra:

1. Marka/model, fiyat, yıl, kilometre ve tramer kriterlerini girin.
2. Taranacak siteleri seçin.
3. **"Tarama ve Tedarik Sürecini Başlat"** butonuna basın; arka planda periyodik tarama başlar.
4. Bulunan ilanlar otomatik yenilenen tabloda listelenir; yeni ilan bulundukça masaüstü bildirimi alırsınız.
5. Taramayı durdurmak için **"Tarama Oturumunu Sonlandır"** butonunu kullanın.

Alternatif olarak, yalnızca Otoplus için kendi içinde scraping yapan eski panoyu çalıştırmak isterseniz:

```bash
streamlit run dashboard.py
```

## Notlar

- Scraping işlemleri hedef sitelerin HTML yapısına bağlıdır; site tasarımı değiştiğinde ilgili scraper fonksiyonunun güncellenmesi gerekebilir.
- Bu araç yalnızca herkese açık ilan sayfalarını okumak için tasarlanmıştır; hedef sitelerin kullanım şartlarına uymak kullanıcının sorumluluğundadır.
