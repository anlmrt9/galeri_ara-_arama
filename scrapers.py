"""
scrapers.py - Çoklu Site Araç Scraper Fonksiyonları
=====================================================
Otoplus / VavaCars / Otokoç / Arabam.com / Sahibinden
Her fonksiyon engine + criteria alır, filtrelere uyan araçları DB'ye yazar.
Genel (site-seviyesi) hatalar -> send_site_failure_notification ile bildirim.
Tekil ilan hataları -> sadece logger.error.
"""

import re
import json
import time
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests as cf

from config import (
    SITE_OTOPLUS, SITE_VAVACARS, SITE_OTOKOC, SITE_ARABAM, SITE_SAHIBINDEN,
    SCRAPER_REQUEST_TIMEOUT, SCRAPER_PAGE_WAIT_SEC, SCRAPER_SELENIUM_WAIT_SEC,
    MAX_NEW_LISTINGS_PER_CYCLE,
)
from logger_setup import logger
from db import listing_exists, insert_car
from notifications import send_desktop_notification, send_site_failure_notification


# ==========================================================================
#  YARDIMCI FONKSİYONLAR
# ==========================================================================

def _safe_int(value, default=0):
    """
    Güvenli int dönüştürme: None, boş string, float gibi beklenmeyen
    değerler geldiğinde patlamaz, default döner.
    BUG FIX: int() çağrısı None/hatalı veri gelirse patlıyordu.
    """
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def check_part_allowed(text_content, keyword, allowed_parts):
    """
    Belirli bir parçada boya/değişen olduğu metinde geçiyorsa,
    bu parçanın allowed_parts listesinde olup olmadığını kontrol eder.
    """
    if keyword in text_content and ("boya" in text_content or "değişen" in text_content or "lokal" in text_content):
        if keyword not in allowed_parts:
            return False
    return True


def extract_damaged_parts(text_content):
    """Metin içinden hasar görmüş parçaları ayıklar."""
    parts = [
        "kaput", "tavan", "bagaj", "sol ön çamurluk", "sağ ön çamurluk",
        "sol ön kapı", "sağ ön kapı", "sol arka kapı", "sağ arka kapı",
        "sol arka çamurluk", "sağ arka çamurluk"
    ]
    found_parts = []
    for p in parts:
        if p in text_content and ("boya" in text_content or "değiş" in text_content or "lokal" in text_content):
            found_parts.append(p.title())
    return ", ".join(found_parts) if found_parts else "Bilinmiyor/Metinde Yok"


def scrape_listing_details(session, link, allowed_parts=None):
    """Otoplus / Otokoç detay sayfasından tramer, boya, parça bilgilerini çeker."""
    if allowed_parts is None:
        allowed_parts = []
    details = {
        "model": "", "package_trim": "", "engine_power": "", "location": "",
        "tramer_fee": 0, "painted_parts": "Orijinal", "changed_parts": "Orijinal",
        "rejected": False
    }
    try:
        r = session.get(link, impersonate="chrome120", timeout=SCRAPER_REQUEST_TIMEOUT)

        if r.status_code != 200:
            logger.error(f"[Detay] HTTP {r.status_code} alindi: {link}")
            return details

        soup = BeautifulSoup(r.text, "lxml")
        text_content = soup.get_text().lower()

        tramer_match = re.search(r'tramer[\s:]*([\d\.]+)[\s]*tl', text_content)
        if tramer_match:
            details["tramer_fee"] = _safe_int(tramer_match.group(1).replace(".", ""))

        # Genel "boyasız", "hatasız" kontrolü
        if (re.search(r'(boya|boyalı).*?(yok|yoktur|bulunmamaktadır)', text_content)
                or "boyasız" in text_content
                or "hatasız" in text_content):
            pass  # Temiz araç
        else:
            # Kullanıcı SIFIR boya istiyorsa (allowed_parts boş) ve araçta boya varsa REDDET
            if len(allowed_parts) == 0 and ("boya" in text_content or "değiş" in text_content):
                details["rejected"] = True
                return details

            # Spesifik parça kontrolü
            all_parts = [
                "kaput", "tavan", "bagaj", "sol ön çamurluk", "sağ ön çamurluk",
                "sol ön kapı", "sağ ön kapı", "sol arka kapı", "sağ arka kapı",
                "sol arka çamurluk", "sağ arka çamurluk"
            ]
            for p in all_parts:
                if not check_part_allowed(text_content, p, allowed_parts):
                    details["rejected"] = True
                    return details

            extracted = extract_damaged_parts(text_content)
            if extracted != "Bilinmiyor/Metinde Yok":
                details["painted_parts"] = extracted
                details["changed_parts"] = extracted
            else:
                details["painted_parts"] = "Bazı parçalar boyalı (Detay Yok)"
                details["changed_parts"] = "Değişen olabilir (Detay Yok)"

    except Exception as e:
        # BUG FIX: Sessiz except:pass kaldırıldı — hata loglanıyor
        logger.error(f"[Detay] Sayfa isleme hatasi ({link}): {e}")
    return details


# ==========================================================================
#  OTOPLUS SCRAPER
# ==========================================================================

def scrape_otoplus(engine, criteria, max_pages_per_cycle=3):
    """Otoplus ikinci el araç sitesinden veri çeker (curl_cffi + JSON-LD)."""
    base_url = "https://www.otoplus.com/ikinci-el-araba"
    target_brand_slug = criteria['brand'].strip().lower().replace(" ", "-")
    if target_brand_slug and target_brand_slug != "tümü":
        base_url = f"https://www.otoplus.com/ikinci-el-araba/{target_brand_slug}"

    session = cf.Session()

    for page in range(1, max_pages_per_cycle + 1):
        url = base_url if page == 1 else f"{base_url}?sayfa={page}"
        try:
            r = session.get(url, impersonate="chrome120", timeout=SCRAPER_REQUEST_TIMEOUT)

            if r.status_code != 200:
                logger.error(f"[{SITE_OTOPLUS}] HTTP {r.status_code} alindi (sayfa {page})")
                # Site seviyesi hata → bildirim gönder
                send_site_failure_notification(SITE_OTOPLUS, f"HTTP {r.status_code} hatası")
                return

            soup = BeautifulSoup(r.text, "lxml")
            tags = soup.find_all("script", {"type": "application/ld+json"})

            for tag in tags:
                try:
                    data = json.loads(tag.string)
                    for item in data.get("@graph", []):
                        if item.get("@type") != "Vehicle":
                            continue

                        brand = item.get("brand", {}).get("name", "") if isinstance(item.get("brand"), dict) else ""
                        year = _safe_int(item.get("vehicleModelDate"))
                        km = _safe_int(item.get("mileageFromOdometer", {}).get("value"))
                        price = _safe_int(item.get("offers", {}).get("price"))

                        # 1. AŞAMA FİLTRE
                        if criteria['brand'] and criteria['brand'] != "Tümü" and criteria['brand'].lower() not in brand.lower():
                            continue
                        title = item.get("name", "").lower()
                        if criteria['model'] and criteria['model'] != "Tümü" and criteria['model'].lower() not in title:
                            continue
                        if price < criteria['min_price'] or price > criteria['max_price']:
                            continue
                        if year < criteria['min_year'] or year > criteria['max_year']:
                            continue
                        if km < criteria['min_km'] or km > criteria['max_km']:
                            continue

                        link = item.get("offers", {}).get("url") or item.get("url") or ""
                        lid_match = re.search(r"-(\d{5,8})$", link)
                        if not lid_match:
                            continue
                        listing_id = f"OP-{lid_match.group(1)}"

                        if listing_exists(engine, listing_id):
                            continue

                        # 2. AŞAMA FİLTRE (Detay sayfası: Tramer & Boya)
                        # BUG FIX: scrape_listing_details iki kez çağrılıyordu, tek çağrıya düşürüldü
                        details = scrape_listing_details(
                            session, link, allowed_parts=criteria.get("allowed_parts", [])
                        )
                        if details.get("rejected", False):
                            continue

                        tramer = details["tramer_fee"]
                        if tramer > criteria["max_tramer"]:
                            continue

                        car_data = {
                            "listing_id": listing_id, "source_site": SITE_OTOPLUS,
                            "brand": brand, "model": details["model"],
                            "package_trim": details["package_trim"],
                            "engine_power": details["engine_power"],
                            "year": year, "km": km, "price": price,
                            "location": details["location"], "tramer_fee": tramer,
                            "painted_parts": details["painted_parts"],
                            "changed_parts": details["changed_parts"],
                            "link": link,
                            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "is_new_listing": 1
                        }

                        if insert_car(engine, car_data):
                            logger.info(f"[{SITE_OTOPLUS}] HEDEFE UYAN ARAC BULUNDU: {brand} - {price} TL")
                            send_desktop_notification(brand, details["model"], price, details["painted_parts"])

                        time.sleep(1)

                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # Tekil ilan/tag parse hatası — bildirime gerek yok, sadece logla
                    logger.error(f"[{SITE_OTOPLUS}] JSON-LD parse hatasi: {e}")

        except Exception as e:
            # Site seviyesi genel hata → hem logla hem bildir
            logger.error(f"[{SITE_OTOPLUS}] Sayfa {page} hata: {e}")
            send_site_failure_notification(SITE_OTOPLUS, str(e))
            return

        time.sleep(SCRAPER_PAGE_WAIT_SEC)


# ==========================================================================
#  VAVACARS SCRAPER
# ==========================================================================

def scrape_vavacars(engine, criteria):
    """VavaCars için veri çekme (SeleniumBase UC Mode)."""
    target_brand = criteria['brand'].strip() if criteria['brand'] and criteria['brand'] != "Tümü" else ""
    base_url = f"https://tr.vava.cars/buy/cars/{target_brand}" if target_brand else "https://tr.vava.cars/buy/cars"

    try:
        from seleniumbase import SB
        with SB(uc=True, test=True, headless=True) as sb:
            sb.uc_open_with_reconnect(base_url, 4)
            time.sleep(SCRAPER_SELENIUM_WAIT_SEC)
            html = sb.get_page_source()
            soup = BeautifulSoup(html, 'html.parser')

            # Tüm ilan linklerini (a etiketlerini) bul
            car_links = soup.find_all('a', href=True)
            valid_cards = []
            for a in car_links:
                href = a['href']
                if '/buy/cars/' in href and len(href.split('/')) >= 4:
                    if a not in valid_cards:
                        valid_cards.append(a)

            new_cars_found = 0
            for a_tag in valid_cards:
                href = a_tag['href']
                listing_id = href.split('/')[-1]
                full_link = "https://tr.vava.cars" + href if href.startswith('/') else href

                if listing_exists(engine, listing_id):
                    continue

                new_cars_found += 1
                if new_cars_found > MAX_NEW_LISTINGS_PER_CYCLE:
                    break

                # HTML'den verileri ayıkla
                title_div = a_tag.find("div", class_=lambda c: c and "text-xl" in c)
                title = title_div.text.strip() if title_div else "Bilinmeyen"

                package_div = a_tag.find("div", class_=lambda c: c and "text-base" in c)
                package = package_div.text.strip() if package_div else ""

                tags_divs = a_tag.find_all("div", class_=lambda c: c and "text-sm" in c)
                tags = [t.text.strip() for t in tags_divs]
                # BUG FIX: _safe_int kullanılıyor, int() patlaması önlendi
                year = _safe_int(tags[0]) if len(tags) > 0 and tags[0].strip().isdigit() else 0
                km_text = tags[1] if len(tags) > 1 else "0"
                km_digits = re.sub(r'\D', '', km_text)
                km = _safe_int(km_digits) if km_digits else 0

                price_div = a_tag.find("div", class_=lambda c: c and "text-h3" in c)
                price_text = price_div.text.strip() if price_div else "0"
                price_digits = re.sub(r'\D', '', price_text)
                price = _safe_int(price_digits) if price_digits else 0

                badge = a_tag.find("span", class_=lambda c: c and "font-semibold" in c)
                damage_info = badge.text.strip() if badge else "Hasar Bilgisi Yok"

                brand_str = target_brand if target_brand else title.split(' ')[0]
                model_str = title.replace(brand_str, '').strip() if brand_str in title else title

                # Filtreler
                if price < criteria['min_price'] or price > criteria['max_price']:
                    continue
                if year < criteria['min_year'] or year > criteria['max_year']:
                    continue
                if km < criteria['min_km'] or km > criteria['max_km']:
                    continue
                if criteria['model'] and criteria['model'] != "Tümü" and criteria['model'].lower() not in model_str.lower():
                    continue

                # Hasar filtreleri
                has_damage = "boyasız, değişensiz" not in damage_info.lower() and damage_info != "Orijinal / Hatasız"
                if has_damage and len(criteria.get("allowed_parts", [])) == 0:
                    logger.info(f"[{SITE_VAVACARS}] SKIP - Hasar filtresine takildi: {title}")
                    continue

                car_data = {
                    "listing_id": listing_id, "source_site": SITE_VAVACARS,
                    "brand": brand_str, "model": model_str, "package_trim": package,
                    "engine_power": "", "year": year, "km": km, "price": price,
                    "location": "Bilinmiyor", "tramer_fee": 0,
                    "painted_parts": damage_info,
                    "changed_parts": "Detay İlanda",
                    "link": full_link,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "is_new_listing": 1
                }
                if insert_car(engine, car_data):
                    logger.info(f"[{SITE_VAVACARS}] HEDEFE UYAN ARAC BULUNDU: {title} - {price} TL")
                    send_desktop_notification(brand_str, model_str, price, damage_info)

            logger.info(f"[{SITE_VAVACARS}] Tarama tamamlandi. Yeni islenen ilan: {new_cars_found}")

    except Exception as e:
        # Site seviyesi genel hata (bağlantı, bot engeli, tarayıcı hatası vb.)
        logger.error(f"[{SITE_VAVACARS}] hata: {e}")
        send_site_failure_notification(SITE_VAVACARS, str(e))


# ==========================================================================
#  OTOKOÇ SCRAPER
# ==========================================================================

def scrape_otokoc(engine, criteria):
    """Otokoç 2. El için veri çekme (__NEXT_DATA__ JSON parse)."""
    target_brand_slug = (
        criteria['brand'].strip().lower().replace(" ", "-")
        if criteria['brand'] and criteria['brand'] != "Tümü" else ""
    )
    url = (
        f"https://www.otokocikinciel.com/ikinci-el-araba/{target_brand_slug}"
        if target_brand_slug else "https://www.otokocikinciel.com/ikinci-el-araba"
    )

    session = cf.Session()
    try:
        r = session.get(url, impersonate="chrome120", timeout=SCRAPER_REQUEST_TIMEOUT)

        if r.status_code != 200:
            logger.error(f"[{SITE_OTOKOC}] HTTP {r.status_code} alindi")
            send_site_failure_notification(SITE_OTOKOC, f"HTTP {r.status_code} hatası")
            return

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text, re.DOTALL | re.IGNORECASE
        )
        if not match:
            # BUG FIX: __NEXT_DATA__ bulunamazsa (sayfa yapısı değişmiş) artık bildirim gönderiliyor
            msg = "Sayfa yapisi degismis olabilir: __NEXT_DATA__ script bulunamadi"
            logger.error(f"[{SITE_OTOKOC}] {msg}")
            send_site_failure_notification(SITE_OTOKOC, msg)
            return

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.error(f"[{SITE_OTOKOC}] __NEXT_DATA__ JSON parse hatasi: {e}")
            send_site_failure_notification(SITE_OTOKOC, f"JSON parse hatası: {e}")
            return

        # Güvenli nested dict erişimi — her seviyede tip kontrolü
        props = data.get('props', {}) if isinstance(data, dict) else {}
        pageProps = props.get('pageProps', {}) if isinstance(props, dict) else {}
        iz = pageProps.get('initialZustandState', {}) if isinstance(pageProps, dict) else {}
        listing = iz.get('listing', {}) if isinstance(iz, dict) else {}
        vehicles = listing.get('results', []) if isinstance(listing, dict) else []

        if not isinstance(vehicles, list):
            logger.error(f"[{SITE_OTOKOC}] 'results' alan beklenmeyen tipte: {type(vehicles)}")
            return

        for item in vehicles:
            try:
                brand = item.get("brandName", "")
                model = item.get("modelName", "")
                # BUG FIX: _safe_int ile güvenli dönüştürme
                year = _safe_int(item.get("year"))
                km = _safe_int(item.get("mileage"))

                prices_list = item.get("prices", [])
                price = 0
                if isinstance(prices_list, list) and len(prices_list) > 0:
                    price = _safe_int(prices_list[0].get("price"))
                elif isinstance(prices_list, dict):
                    price = _safe_int(prices_list.get("cashPrice"))

                trim = item.get("versionName", "")

                if criteria['model'] and criteria['model'] != "Tümü" and criteria['model'].lower() not in model.lower():
                    continue
                if price < criteria['min_price'] or price > criteria['max_price']:
                    continue
                if year < criteria['min_year'] or year > criteria['max_year']:
                    continue
                if km < criteria['min_km'] or km > criteria['max_km']:
                    continue

                listing_id = str(item.get("id", ""))
                slug = item.get("slug", "")
                link = f"https://www.otokocikinciel.com/ikinci-el-araba/{slug}"

                if listing_exists(engine, listing_id):
                    continue

                details = scrape_listing_details(session, link, allowed_parts=criteria.get("allowed_parts", []))
                if details.get("rejected", False):
                    continue

                tramer = details["tramer_fee"]
                if tramer > criteria["max_tramer"]:
                    continue

                car_data = {
                    "listing_id": listing_id, "source_site": SITE_OTOKOC,
                    "brand": brand, "model": model, "package_trim": trim,
                    "engine_power": "", "year": year, "km": km, "price": price,
                    "location": item.get("cityName", ""), "tramer_fee": tramer,
                    "painted_parts": details["painted_parts"],
                    "changed_parts": details["changed_parts"],
                    "link": link,
                    "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "is_new_listing": 1
                }
                if insert_car(engine, car_data):
                    logger.info(f"[{SITE_OTOKOC}] HEDEFE UYAN ARAC BULUNDU: {brand} - {price} TL")
                    send_desktop_notification(brand, model, price, details["painted_parts"])

                time.sleep(1)

            except Exception as e:
                # Tekil ilan işleme hatası — logla, bildirim gönderme
                logger.error(f"[{SITE_OTOKOC}] Tekil ilan isleme hatasi: {e}")

    except Exception as e:
        # Site seviyesi genel hata
        logger.error(f"[{SITE_OTOKOC}] hata: {e}")
        send_site_failure_notification(SITE_OTOKOC, str(e))


# ==========================================================================
#  ARABAM.COM SCRAPER
# ==========================================================================

def scrape_arabam(engine, criteria):
    """Arabam.com için veri çekme (SeleniumBase UC Mode)."""
    target_brand_slug = (
        criteria['brand'].strip().lower().replace(" ", "-")
        if criteria['brand'] and criteria['brand'] != "Tümü" else ""
    )
    base_url = (
        f"https://www.arabam.com/ikinci-el/otomobil/{target_brand_slug}"
        if target_brand_slug else "https://www.arabam.com/ikinci-el/otomobil"
    )

    params = (
        f"?minPrice={criteria['min_price']}&maxPrice={criteria['max_price']}"
        f"&minYear={criteria['min_year']}&maxYear={criteria['max_year']}&take=20"
    )
    url = base_url + params

    try:
        from seleniumbase import SB
        with SB(uc=True, test=True, headless=True) as sb:
            sb.uc_open_with_reconnect(url, 4)
            time.sleep(SCRAPER_PAGE_WAIT_SEC)
            html = sb.get_page_source()
            soup = BeautifulSoup(html, 'html.parser')

            listing_links = []
            for a in soup.find_all('a', href=True):
                if '/ilan/' in a['href'] and '-satilik-' in a['href']:
                    full_url = "https://www.arabam.com" + a['href'] if a['href'].startswith('/') else a['href']
                    if full_url not in listing_links:
                        listing_links.append(full_url)

            new_links = []
            for link in listing_links:
                lid = link.split('/')[-1]
                if not listing_exists(engine, lid):
                    new_links.append((lid, link))
                if len(new_links) >= 3:
                    break

            # Bulunan ilk 3 YENİ ilanı gez
            for listing_id, link in new_links:
                try:
                    sb.uc_open_with_reconnect(link, 4)
                    time.sleep(SCRAPER_PAGE_WAIT_SEC)
                    detail_html = sb.get_page_source()
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')

                    price_div = detail_soup.find("div", {"class": "product-price"})
                    if not price_div:
                        price_div = detail_soup.find("span", {"class": "color-red4"})

                    price_text = price_div.text.strip().replace(".", "").replace("TL", "").strip() if price_div else "0"
                    price_digits = re.sub(r'\D', '', price_text)
                    price = _safe_int(price_digits) if price_digits else 0

                    if price < criteria['min_price'] or price > criteria['max_price']:
                        continue

                    title_h1 = detail_soup.find("h1")
                    title = title_h1.text.strip() if title_h1 else "Bilinmeyen Model"

                    text_content = detail_soup.get_text(separator=' ').lower()
                    damage_keywords = ["boyalı", "boyanmış", "boyalıdır", "değişen", "değişmiş", "hasar kaydı", "tramer kayıtlı"]
                    has_damage = any(kw in text_content for kw in damage_keywords)

                    if has_damage and len(criteria.get("allowed_parts", [])) == 0:
                        logger.info(f"[{SITE_ARABAM}] SKIP - Hasar filtresine takildi: {title[:20]}")
                        continue

                    car_data = {
                        "listing_id": listing_id, "source_site": SITE_ARABAM,
                        "brand": criteria['brand'] if criteria['brand'] != "Tümü" else "Arabam",
                        "model": title[:30], "package_trim": "",
                        "engine_power": "",
                        "year": _safe_int(criteria.get('min_year')),
                        "km": _safe_int(criteria.get('min_km')),
                        "price": price,
                        "location": "Bilinmiyor", "tramer_fee": 0,
                        "painted_parts": "Detay İlanda (Arabam)" if has_damage else "Temiz Görünüyor",
                        "changed_parts": "Detay İlanda",
                        "link": link,
                        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "is_new_listing": 1
                    }
                    if insert_car(engine, car_data):
                        logger.info(f"[{SITE_ARABAM}] HEDEFE UYAN ARAC BULUNDU: {title[:20]} - {price} TL")
                        send_desktop_notification(car_data["brand"], car_data["model"], price, car_data["painted_parts"])

                except Exception as e:
                    # Tekil ilan hatası — logla, bildirim gönderme
                    logger.error(f"[{SITE_ARABAM}] Tekil ilan isleme hatasi ({listing_id}): {e}")

            logger.info(f"[{SITE_ARABAM}] Tarama tamamlandi. {len(listing_links)} ilan listelendi.")

    except Exception as e:
        # Site seviyesi genel hata (bot engeli, bağlantı hatası, tarayıcı hatası)
        logger.error(f"[{SITE_ARABAM}] hata: {e}")
        send_site_failure_notification(SITE_ARABAM, str(e))


# ==========================================================================
#  SAHİBİNDEN SCRAPER (Devre dışı — Cloudflare + Captcha)
# ==========================================================================

def scrape_sahibinden(engine, criteria):
    """Sahibinden.com — güvenlik duvarı nedeniyle şu an devre dışı."""
    logger.warning(
        f"[{SITE_SAHIBINDEN}] Sahibinden.com güvenlik duvarı (Cloudflare + Captcha) "
        "headless modda aşılamıyor. Bu site şu an otomatik taramaya kapalıdır."
    )


# ==========================================================================
#  TEK DÖNGÜ ÇALIŞTIRICI
# ==========================================================================

def run_one_cycle(engine, criteria):
    """
    Seçilen tüm siteleri sırayla bir kez tarar.
    Her scraper'ın kendi try/except'i var ama burada da üst düzey bir
    güvenlik ağı bulunuyor: bir scraper tamamen çökerse (import hatası,
    beklenmedik TypeError vb.) kullanıcıya bildirim gönderilir.
    """
    site_scraper_map = {
        SITE_OTOPLUS: scrape_otoplus,
        SITE_VAVACARS: scrape_vavacars,
        SITE_OTOKOC: scrape_otokoc,
        SITE_ARABAM: scrape_arabam,
        SITE_SAHIBINDEN: scrape_sahibinden,
    }

    selected_sites = criteria.get("sites", [SITE_OTOPLUS])

    for site_name in selected_sites:
        scraper_fn = site_scraper_map.get(site_name)
        if not scraper_fn:
            logger.warning(f"Bilinmeyen site: {site_name}")
            continue
        try:
            if site_name == SITE_OTOPLUS:
                scraper_fn(engine, criteria, max_pages_per_cycle=3)
            else:
                scraper_fn(engine, criteria)
        except Exception as e:
            # Scraper fonksiyonu tamamen çöktü (beklenmedik hata)
            logger.error(f"[{site_name}] run_one_cycle icinde BEKLENMEDIK COKME: {e}")
            send_site_failure_notification(site_name, f"Beklenmedik çökme: {e}")
