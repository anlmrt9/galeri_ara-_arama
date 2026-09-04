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

Gerekli Python paketleri `requirements.txt` içinde tanımlıdır:

```bash
pip install -r requirements.txt
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

## Bulut Dağıtımı (Streamlit Community Cloud + Supabase)

Proje, yerel SQL Server yerine bulut tabanlı bir PostgreSQL (Supabase) veritabanıyla da çalışacak şekilde hazırlanmıştır. `config.py`/`db.py` içinde `DATABASE_URL` tanımlıysa PostgreSQL, tanımlı değilse yerel SQL Server kullanılır — kod değişikliği gerekmez.

1. **Supabase projesi oluşturun** ([supabase.com](https://supabase.com)) ve *Settings → Database → Connection String → URI* kısmından bağlantı adresini alın.
2. **Bu repoyu GitHub'a bağlayın** (zaten `anlmrt9/galeri_ara-_arama` reposuna push edilmiş durumda).
3. [share.streamlit.io](https://share.streamlit.io) üzerinden GitHub hesabınızla giriş yapıp bu repoyu seçerek "New app" ile deploy edin (`app.py`'yi ana dosya olarak gösterin).
4. Uygulama ayarlarında **Secrets** bölümüne `.streamlit/secrets.toml.example` dosyasındaki şablonu kendi Supabase bağlantı adresinizle doldurup yapıştırın:
   ```toml
   DATABASE_URL = "postgresql://postgres:SIFRENIZ@db.XXXX.supabase.co:5432/postgres"
   ```
5. Deploy tamamlandığında size `https://<uygulama-adi>.streamlit.app` şeklinde herkese açık bir adres verilir.

**Önemli sınırlamalar:** Streamlit Community Cloud'un ücretsiz katmanı, uzun süre çalışan arka plan iş parçacıkları (`background_scan_thread`) için tasarlanmamıştır — uygulama bir süre etkileşim almazsa konteyner uyku moduna geçer ve aktif tarama durur. Ayrıca VavaCars ve Arabam.com scraperları `seleniumbase` ile gerçek bir Chrome tarayıcısı gerektirir; bu, Community Cloud'un varsayılan ortamında güvenilir çalışmayabilir. `curl_cffi` tabanlı Otoplus scraper'ı bu kısıtlamalardan etkilenmez. Kesintisiz 7/24 tarama için yerel çalıştırma (veya kendi sunucunuz) hâlâ en güvenilir yöntemdir; bulut dağıtımı daha çok "istediğiniz an açıp sonuçlara bakma" senaryosu için uygundur.

## Mobil Uygulama Olarak Kurulum (PWA)

Uygulama, telefonunuzda gerçek bir uygulama gibi görünüp açılabilmesi için bir **Progressive Web App (PWA)** katmanıyla donatılmıştır (`static/manifest.json`, `static/sw.js`, uygulama ikonları). Bulutta deploy ettikten sonra (HTTPS zorunludur, bu yüzden yerel `localhost` üzerinde "Ana Ekrana Ekle" çalışmaz):

- **Android (Chrome):** Uygulama adresini açın → sağ üstteki ⋮ menüsü → **"Uygulamayı yükle"** veya **"Ana ekrana ekle"**.
- **iPhone (Safari):** Uygulama adresini açın → paylaş simgesi (□↑) → **"Ana Ekrana Ekle"**.

Ekleme sonrası uygulama kendi ikonuyla, adres çubuğu olmadan tam ekran açılır. Streamlit'in statik dosya sunumundaki kısıtlama nedeniyle service worker'ın kapsamı `/app/static/` ile sınırlı kalır (bu yalnızca çevrimdışı önbellekleme özelliğini etkiler); ana ekrana ekleme, ikon ve tam ekran açılış davranışı bundan etkilenmez.

## Notlar

- Scraping işlemleri hedef sitelerin HTML yapısına bağlıdır; site tasarımı değiştiğinde ilgili scraper fonksiyonunun güncellenmesi gerekebilir.
- Bu araç yalnızca herkese açık ilan sayfalarını okumak için tasarlanmıştır; hedef sitelerin kullanım şartlarına uymak kullanıcının sorumluluğundadır.
