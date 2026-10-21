# Güvenlik Politikası

## Güvenlik açığı bildirimi

Bir güvenlik açığı bulduysan **herkese açık bir issue açma**. Bunun yerine
depodaki [GitHub Security Advisories](https://github.com/anlmrt9/galeri_ara-_arama/security/advisories/new)
üzerinden özel bir bildirim oluştur veya depo sahibine özelden ulaş.

Şunları paylaş: etkilenen dosya/uç, yeniden üretme adımları, olası etki.
Makul bir sürede (genellikle birkaç gün) ilk yanıt verilir.

## Desteklenen sürümler

Yalnızca en son sürüm (`main` dalı + son etiket) desteklenir.

## Dağıtım güvenliği notları

- **REST API varsayılan olarak yalnızca localhost'a açıktır.** `OTOGALERI_API_KEY`
  tanımlanırsa tüm korumalı uçlar `X-API-Key` başlığı ister (sabit zamanlı
  karşılaştırma). Kimlik doğrulamayı tamamen kapatmak yalnızca bilinçli
  `OTOGALERI_API_ALLOW_UNAUTHENTICATED=true` ile mümkündür. İnternete açıyorsanız
  HTTPS arkasına alın.
- CORS varsayılan olarak kapalıdır. `OTOGALERI_CORS_ORIGINS` ile yalnızca kendi
  origin'lerinizi listeleyin.
- API'de IP başına hız sınırı (`OTOGALERI_RATE_LIMIT`, varsayılan 120/dk) ve
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` başlıkları vardır.
- Kazınan ilan verisi arayüzde HTML olarak basılmadan önce kaçışlanır ve yalnızca
  `http(s)` linklere izin verilir (depolanmış XSS'e karşı).
- `.env`, `.streamlit/secrets.toml`, `*.db` ve log dosyaları `.gitignore` ve
  `.dockerignore` kapsamındadır. Docker imajı root olmayan kullanıcıyla çalışır.
- Tüm SQL sorguları SQLAlchemy Core ile parametrelidir. SQL Server veritabanı adı
  `CREATE DATABASE`'e yalnızca `^[A-Za-z_][A-Za-z0-9_]*$` doğrulamasından sonra girer.
- CI'da `ruff` bandit (`S`) güvenlik kuralları çalışır. Dependabot bağımlılıkları
  haftalık günceller.

### Geçmişte sızan kimlik bilgileri

Eski sürümlerdeki `test_system.py` dosyası düz metin proxy kullanıcı adı/şifresi
içeriyordu ve git geçmişinde duruyor. Bu proxy hesaplarının şifreleri değiştirilmeli.
Gerekirse geçmiş `git filter-repo` ile temizlenmelidir.

## Kapsam dışı

Scraper'lar yalnızca hedef sitelerin **herkese açık** ilan sayfalarını okur.
Hedef sitelerin kullanım şartlarına uymak kullanıcının sorumluluğundadır; bu bir
güvenlik açığı sınıfı değildir.
