# Katkı Rehberi

Her değişiklik lint, biçim, tip ve test kontrollerinden geçmelidir.

## Geliştirme ortamı

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Çalıştırma

```bash
streamlit run app.py                         # arayüz (gömülü worker ile)
python -m uvicorn api:app --port 8000        # REST API
python -m otogaleri.worker                   # ayrı worker (OTOGALERI_EMBEDDED_WORKER=false iken)
alembic upgrade head                         # migration'ları elle uygula (uygulama da açılışta yapar)
docker compose up --build                    # Postgres + API + arayüz + worker
```

## Kontroller

```bash
ruff check .        # lint + güvenlik (bandit) kuralları
black --check .
mypy                # otogaleri paketinin tamamı disallow_untyped_defs ile
pytest --cov        # CI eşiği: %80
```

## Kod standartları

- Satır uzunluğu 100, biçim `black`, lint `ruff` (kurallar `pyproject.toml` içinde).
- Logger çağrılarında lazy `%` biçimi kullanın: `log.info("x=%s", x)`.
- Geniş `except Exception` yalnızca gerekçeli olabilir ve
  `# noqa: BLE001 - <sebep>` taşımalıdır.
- Kazınmış (güvenilmeyen) metni HTML'e basarken her zaman
  `otogaleri.ui.render.esc` / `safe_url` kullanın.
- Şema değişikliği yalnızca yeni bir Alembic migration'ı ile yapılır
  (`alembic revision -m "..."`). `otogaleri/db.py` içindeki `metadata` ile
  migration'lar uyumlu tutulmalıdır.

## Yeni site eklemek

1. `otogaleri/scrapers/<site>.py` dosyasında saf `parse_list(html)` ve
   `parse_detail(html)` fonksiyonlarını, ardından `Scraper` alt sınıfını yazın.
2. `config.SITES` ve `scrapers.REGISTRY`'ye ekleyin.
3. Gerçek sayfadan kırpılmış ve kişisel bilgileri (plaka, isim, imzalı URL)
   temizlenmiş örnekleri `tests/fixtures/` altına koyun ve `tests/test_parsers.py`
   dosyasına testlerini ekleyin.
4. Hasar etiketleri `damage.classify` / `damage.normalize_part` tarafından
   tanınmıyorsa eş anlamlı ifadeleri oraya ekleyin.

## Sürümleme

[Semantic Versioning](https://semver.org/lang/tr/) ve
[Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) kullanılır. Sürüm numarası
`otogaleri/__init__.py` dosyasındadır. Kullanıcıyı etkileyen her değişikliği
`CHANGELOG.md` dosyasına ekleyin.
