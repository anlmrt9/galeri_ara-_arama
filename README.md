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
| `static/manifest.json` | PWA manifest'i (ikonlar, tema rengi, kısayollar). |
| `static/sw.js` | Service worker: statik varlık önbellekleme + çevrimdışı sayfa yönlendirmesi. |
| `static/offline.html` | Bağlantı yokken gösterilen çevrimdışı bilgilendirme ekranı. |
| `static/splash/` | iOS "Ana Ekrana Ekle" sonrası açılışta gösterilen marka splash görselleri. |
| `api.py` | Mobil uygulamanın konuştuğu FastAPI backend'i (aynı `config`/`db`/`scrapers` mantığını REST üzerinden sunar). |

> **Not:** Expo (React Native) ile yazılmış gerçek mobil uygulama artık bu repoda değil, ayrı bir klasöre taşındı: `../otogaleri-mobile` (bu projeyle kardeş klasör). `api.py`'ye HTTP ile bağlanır.

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

## Gerçek Mobil Uygulama (FastAPI + Expo/React Native)

Streamlit'e ek olarak, aynı veritabanını kullanan gerçek bir mobil uygulama da mevcuttur: telefona kurulan, kendi ikonuyla açılan, sekmeli (Ana Sayfa / Filtreler / Sonuçlar / Ayarlar) bir React Native uygulaması. İş mantığı (scraping, veritabanı, bildirim) değişmedi — `api.py` bunu ince bir REST katmanıyla mobil uygulamaya açar.

### 1. Backend'i başlatın (bilgisayarınızda)

```bash
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Bilgisayarınızın yerel ağ IP adresini öğrenin (Windows'ta `ipconfig` → "IPv4 Address"), örn. `192.168.1.10`.

### 2. Mobil uygulamayı çalıştırın

```bash
cd ../otogaleri-mobile   # ayrı klasöre taşındı
npm install   # ilk seferde
npx expo start
```

Telefonunuza **Expo Go** uygulamasını kurun (Play Store / App Store), terminalde çıkan QR kodu okutun — telefon ve bilgisayar aynı Wi-Fi ağında olmalı. Uygulama açıldığında **Ayarlar** sekmesinden backend adresinizi girin: `http://192.168.1.10:8000` (yukarıda bulduğunuz IP).

### Neler çalışır / neler çalışmaz

- ✅ Marka/model/fiyat/yıl/km/tramer filtreleri, site seçimi, hasar haritası (13 parça, dokunarak orijinal→boyalı→değişen), tarama başlat/durdur/temizle, canlı sonuç listesi — hepsi Streamlit arayüzüyle birebir aynı mantığı kullanır.
- ✅ Uygulama açıkken/arka planda çalışırken periyodik kontrol (polling) ile yeni ilan bulunduğunda **yerel bildirim** gösterilir.
- ⚠️ Uygulama tamamen kapalıyken gerçek push bildirimi (masaüstündeki toast'ın tam karşılığı) bu sürümde yok — Expo Go artık uzak push'u desteklemiyor; bunun için ileride `eas build` ile bir development build gerekir.
- ⚠️ Play Store/App Store'a **yayınlamak** için `eas build` ile native paket (APK/IPA) üretmek ayrı bir adımdır (hesap/imzalama gerektirir); bu proje buna hazır şekilde (yönetilen Expo iş akışı) kuruldu.
- ℹ️ Mobil uygulama backend'e düz HTTP ile bağlanır — aynı Wi-Fi/ev ağı kullanımı için tasarlandı. İnternetten (ev ağı dışından) erişim isterseniz backend'i bir sunucuya deploy edip HTTPS arkasına almanız gerekir.

## Mobil Uygulama Olarak Kurulum (PWA)

Yukarıdaki gerçek mobil uygulamaya ek olarak, kurulum gerektirmeyen daha hafif bir alternatif de mevcuttur: Streamlit arayüzünün kendisi bir PWA olarak da açılabilir.

Uygulama, telefonunuzda gerçek bir uygulama gibi görünüp açılabilmesi için tam donanımlı bir **Progressive Web App (PWA)** katmanıyla donatılmıştır (`static/manifest.json`, `static/sw.js`, `static/offline.html`, `static/splash/`, uygulama ikonları). Bulutta deploy ettikten sonra (HTTPS zorunludur, bu yüzden yerel `localhost` üzerinde "Ana Ekrana Ekle" çalışmaz):

- **Android (Chrome):** Uygulama adresini açın → sağ üstteki ⋮ menüsü → **"Uygulamayı yükle"** veya **"Ana ekrana ekle"** (ekranın altında beliren **📲 Uygulamayı Yükle** butonuyla da tetiklenebilir).
- **iPhone (Safari):** Uygulama adresini açın → paylaş simgesi (□↑) → **"Ana Ekrana Ekle"** (ilk ziyarette ekranın altında bu adımları gösteren bir ipucu belirir).

Ekleme sonrası uygulama kendi ikonuyla, adres çubuğu olmadan tam ekran açılır. PWA katmanı şunları içerir:

- **Marka splash ekranı:** iOS'ta uygulama açılırken varsayılan boş beyaz ekran yerine `static/splash/` altındaki, tüm yaygın iPhone/iPad çözünürlükleri için üretilmiş koyu lacivert + logo splash görseli gösterilir.
- **Çevrimdışı ekranı:** Service worker sayfa yüklemesini önce ağdan dener; bağlantı yoksa `static/offline.html` içindeki "İnternet bağlantısı yok / Tekrar Dene" ekranını gösterir. Streamlit'in statik dosya sunumu kısıtlaması nedeniyle asıl (dinamik) sayfa tam olarak önbelleklenemez — bu yüzden çevrimdışıyken uygulama içeriği değil, bu bilgilendirme ekranı görünür. İkon/manifest/splash gibi statik varlıklar ise cache-first stratejisiyle önbelleklenir.
- **Kısayol (shortcut):** Android'de uygulama ikonuna uzun basıldığında doğrudan "Taramayı Başlat" formuna atlayan bir kısayol menüsü çıkar.
- **Dokunsal geri bildirim:** Hızlı işlem butonlarına (Başlat/Durdur/Temizle/Yenile) dokunulduğunda destekleyen cihazlarda hafif bir titreşimle native-app hissi verilir.

## Notlar

- Scraping işlemleri hedef sitelerin HTML yapısına bağlıdır; site tasarımı değiştiğinde ilgili scraper fonksiyonunun güncellenmesi gerekebilir.
- Bu araç yalnızca herkese açık ilan sayfalarını okumak için tasarlanmıştır; hedef sitelerin kullanım şartlarına uymak kullanıcının sorumluluğundadır.
