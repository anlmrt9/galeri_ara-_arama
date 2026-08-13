"""
OtoGaleriDB - Hedef Odakli (Avci) Arac Scraper & Dashboard
============================================================
Once kullanici kriterleri (Marka, Model, Max Fiyat, Max Tramer) girer,
Sistem sadece bu kriterlere uyan araclari bulup getirir.
"""

import streamlit as st
import pyodbc
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from curl_cffi import requests as cf
from sqlalchemy import create_engine, text
import pandas as pd
import threading
import time
from streamlit_autorefresh import st_autorefresh
import logging
from curl_cffi import requests as cf
from streamlit.runtime.scriptrunner import add_script_run_ctx
import json
from win11toast import toast

# ---------- LOGLAMA ----------
logger = logging.getLogger("OtoGaleri")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logger.addHandler(ch)

# ---------- VERITABANI AYARLARI ----------
DB_SERVER = r"MERTPC\SQLEXPRESS"
DB_NAME = "OtoGaleriDB"

def create_db_if_not_exists():
    conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE=master;Trusted_Connection=yes;autocommit=True"
    try:
        conn = pyodbc.connect(conn_str, autocommit=True)
        cursor = conn.cursor()
        cursor.execute(f"SELECT name FROM sys.databases WHERE name = N'{DB_NAME}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {DB_NAME}")
            logger.info(f"{DB_NAME} olusturuldu.")
        conn.close()
    except Exception as e:
        pass

@st.cache_resource
def get_engine():
    create_db_if_not_exists()
    conn_str = f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
    try:
        return create_engine(conn_str, pool_size=5, max_overflow=10, pool_pre_ping=True)
    except:
        return None

def init_tables(engine):
    if not engine: return
    try:
        with engine.begin() as conn:
            conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Cars' AND xtype='U')
            BEGIN
                CREATE TABLE Cars (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    listing_id VARCHAR(50) UNIQUE,
                    source_site NVARCHAR(50),
                    brand NVARCHAR(100),
                    model NVARCHAR(100),
                    package_trim NVARCHAR(100),
                    engine_power NVARCHAR(100),
                    year INT,
                    km INT,
                    price BIGINT,
                    location NVARCHAR(100),
                    tramer_fee BIGINT,
                    painted_parts NVARCHAR(MAX),
                    changed_parts NVARCHAR(MAX),
                    link VARCHAR(500),
                    scraped_at DATETIME,
                    is_new_listing BIT
                )
            END
            """))
    except:
        pass

def load_data(engine):
    if not engine: return pd.DataFrame()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM Cars ORDER BY scraped_at DESC"), conn)
            for col in ["year", "km", "price", "tramer_fee"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            return df
    except:
        return pd.DataFrame()

# ---------- BILDIRIM SISTEMI ----------
def send_desktop_notification(brand, model, price, painted_parts):
    try:
        title = "🚨 Yeni Araç Yakalandı!"
        message = f"{brand} {model}\nFiyat: {price:,} TL\nBoya/Değişen: {painted_parts}"
        toast(title, message, app_id="OtoGaleri Avcı Bot")
    except Exception as e:
        logger.error(f"Bildirim gonderilemedi: {e}")

# ---------- HEDEF ODAKLI SCRAPER ----------
def check_part_allowed(text_content, keyword, allowed_parts):
    """
    Belirli bir parcada boya/degisen oldugu metinde geciyorsa (keyword),
    bu parcanin allowed_parts (izin verilenler) listesinde olup olmadigini kontrol eder.
    Eger izin verilmeyen bir parcada hasar varsa, False doner.
    """
    # Ornegin: "kaput boyali" yaziyorsa, kaput allowed mu?
    # Otoplus'ta genellikle boya kelimesi gecer.
    if keyword in text_content and ("boya" in text_content or "değişen" in text_content or "lokal" in text_content):
        if keyword not in allowed_parts:
            return False
    return True

def extract_damaged_parts(text_content):
    parts = ["kaput", "tavan", "bagaj", "sol ön çamurluk", "sağ ön çamurluk", "sol ön kapı", "sağ ön kapı", 
             "sol arka kapı", "sağ arka kapı", "sol arka çamurluk", "sağ arka çamurluk"]
    found_parts = []
    for p in parts:
        if p in text_content and ("boya" in text_content or "değiş" in text_content or "lokal" in text_content):
            found_parts.append(p.title())
    return ", ".join(found_parts) if found_parts else "Bilinmiyor/Metinde Yok"

def scrape_listing_details(session, link, allowed_parts=None):
    if allowed_parts is None: allowed_parts = []
    details = {
        "model": "", "package_trim": "", "engine_power": "", "location": "",
        "tramer_fee": 0, "painted_parts": "Orijinal", "changed_parts": "Orijinal",
        "rejected": False
    }
    try:
        r = session.get(link, impersonate="chrome120", timeout=15)
            
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            text_content = soup.get_text().lower()
            
            tramer_match = re.search(r'tramer[\s:]*([\d\.]+)[\s]*tl', text_content)
            if tramer_match:
                details["tramer_fee"] = int(tramer_match.group(1).replace(".", ""))
                
            # Genel "boyasiz", "hatasiz" kontrolu
            if re.search(r'(boya|boyalı).*?(yok|yoktur|bulunmamaktadır)', text_content) or "boyasız" in text_content or "hatasız" in text_content:
                pass # Temiz
            else:
                # Eger kullanici SIFIR boya istiyorsa (allowed_parts bos ise) ve aracta boya varsa REDDET
                if len(allowed_parts) == 0 and ("boya" in text_content or "değiş" in text_content):
                    details["rejected"] = True
                    return details
                
                # Spesifik parca kontrolu (Kullanici tavan haric dedi, tavan hasarli mi?)
                all_parts = ["kaput", "tavan", "bagaj", "sol ön çamurluk", "sağ ön çamurluk", "sol ön kapı", "sağ ön kapı", 
                             "sol arka kapı", "sağ arka kapı", "sol arka çamurluk", "sağ arka çamurluk"]
                
                for p in all_parts:
                    if not check_part_allowed(text_content, p, allowed_parts):
                        details["rejected"] = True # Izin verilmeyen parcada hasar bulundu!
                        return details
                        
                extracted = extract_damaged_parts(text_content)
                if extracted != "Bilinmiyor/Metinde Yok":
                    details["painted_parts"] = extracted
                    details["changed_parts"] = extracted
                else:
                    details["painted_parts"] = "Bazı parçalar boyalı (Detay Yok)"
                    details["changed_parts"] = "Değişen olabilir (Detay Yok)"
    except:
        pass
    return details

def scrape_otoplus(engine, criteria, max_pages_per_cycle=3):
    """Sadece 'criteria' sozluk degerlerine uyan ilanlari yakalar (Otoplus)."""
    base_url = "https://www.otoplus.com/ikinci-el-araba"
    
    target_brand_slug = criteria['brand'].strip().lower().replace(" ", "-")
    if target_brand_slug and target_brand_slug != "tümü":
        base_url = f"https://www.otoplus.com/ikinci-el-araba/{target_brand_slug}"
        
    session = cf.Session()
    
    for page in range(1, max_pages_per_cycle + 1):
        url = base_url if page == 1 else f"{base_url}?sayfa={page}"
        try:
            r = session.get(url, impersonate="chrome120", timeout=15)
                
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")
                tags = soup.find_all("script", {"type": "application/ld+json"})
                for tag in tags:
                    try:
                        data = json.loads(tag.string)
                        for item in data.get("@graph", []):
                            if item.get("@type") == "Vehicle":
                                brand = item.get("brand", {}).get("name", "") if isinstance(item.get("brand"), dict) else ""
                                year = int(item.get("vehicleModelDate") or 0)
                                km = int(item.get("mileageFromOdometer", {}).get("value", 0))
                                price = int(item.get("offers", {}).get("price", 0))
                                
                                # 1. ASAMA FILTRE (Yuzelsel Veriler)
                                if criteria['brand'] and criteria['brand'] != "Tümü" and criteria['brand'].lower() not in brand.lower(): continue
                                
                                # Eger model 'Tümü' degilse model kontrolu yap (Model cogu zaman baslik veya json-ld'de saklanabilir, basitce title icinde kontrol edelim)
                                title = item.get("name", "").lower()
                                if criteria['model'] and criteria['model'] != "Tümü" and criteria['model'].lower() not in title: continue
                                
                                if price < criteria['min_price'] or price > criteria['max_price']: continue
                                if year < criteria['min_year'] or year > criteria['max_year']: continue
                                if km < criteria['min_km'] or km > criteria['max_km']: continue
                                
                                link = item.get("offers", {}).get("url") or item.get("url") or ""
                                lid_match = re.search(r"-(\d{5,8})$", link)
                                if not lid_match: continue
                                listing_id = lid_match.group(1)
                                
                                # Ayni ilani daha once cektik mi?
                                with engine.connect() as conn:
                                    exists = conn.execute(text("SELECT 1 FROM Cars WHERE listing_id=:id"), {"id": listing_id}).scalar()
                                
                                if not exists:
                                    # 2. ASAMA FILTRE (Detay sayfasi: Tramer & Boya)
                                    details = scrape_listing_details(session, link)
                                    
                                    # Kriter Model uyusuyor mu? (Otoplus JSON-LD'de model yok, detayda var kabul ediyoruz veya baslikta)
                                    # Detay sayfasina git
                                    details = scrape_listing_details(session, link, allowed_parts=criteria.get("allowed_parts", []))
                                    if details.get("rejected", False):
                                        continue # Izin verilmeyen parcasi hasarli, araci ele!
                                        
                                    tramer = details["tramer_fee"]
                                    if tramer > criteria["max_tramer"]: continue
                                    
                                    car_data = {
                                        "listing_id": f"OP-{listing_id}", "source_site": "Otoplus",
                                        "brand": brand, "model": details["model"], "package_trim": details["package_trim"],
                                        "engine_power": details["engine_power"], "year": year, "km": km, "price": price,
                                        "location": details["location"], "tramer_fee": tramer,
                                        "painted_parts": details["painted_parts"], "changed_parts": details["changed_parts"],
                                        "link": link, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "is_new_listing": 1
                                    }
                                    
                                    with engine.begin() as conn:
                                        conn.execute(text("""
                                            INSERT INTO Cars (listing_id, source_site, brand, model, package_trim, engine_power, year, km, price, location, tramer_fee, painted_parts, changed_parts, link, scraped_at, is_new_listing)
                                            VALUES (:listing_id, :source_site, :brand, :model, :package_trim, :engine_power, :year, :km, :price, :location, :tramer_fee, :painted_parts, :changed_parts, :link, :scraped_at, :is_new_listing)
                                        """), car_data)
                                        logger.info(f"[Otoplus] HEDEFE UYAN ARAC BULUNDU: {brand} - {price} TL")
                                        
                                        # Masaustu Bildirimi Gonder
                                        send_desktop_notification(brand, details["model"], price, details["painted_parts"])
                                        
                                    time.sleep(1)
                    except: pass
        except: pass
        time.sleep(2)

def scrape_vavacars(engine, criteria):
    """VavaCars için veri çekme."""
    base_url = "https://app-vava-dtc-search-tr-prod.vava.cars/search/filter-preview"
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'origin': 'https://tr.vava.cars',
        'referer': 'https://tr.vava.cars/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # Basit bir payload
    payload = {
        "transmission": [], "fuelType": [], "driveType": [], "bodyType": [],
        "doorCount": [], "seatingCapacity": [], "carFeaturesCodes": [], "color": [],
        "colorCode": [], "locationCity": [], "tags": [], "hideBooked": True, "anyBooked": False
    }
    
    session = cf.Session()
    try:
        r = session.post(base_url, headers=headers, json=payload, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            for item in items:
                brand = item.get("make", "")
                model = item.get("model", "")
                price = int(item.get("price", 0))
                year = int(item.get("year", 0))
                km = int(item.get("mileage", 0))
                trim = item.get("trimLevel", "")
                is_damaged = item.get("isDamaged", False)
                is_repainted = item.get("isRepainted", False)
                is_replaced = item.get("isReplaced", False)
                
                # 1. Aşama Filtreler
                if criteria['brand'] and criteria['brand'] != "Tümü" and criteria['brand'].lower() not in brand.lower(): continue
                if criteria['model'] and criteria['model'] != "Tümü" and criteria['model'].lower() not in model.lower(): continue
                if price < criteria['min_price'] or price > criteria['max_price']: continue
                if year < criteria['min_year'] or year > criteria['max_year']: continue
                if km < criteria['min_km'] or km > criteria['max_km']: continue
                
                # 2. Aşama Filtreler (Hasar)
                allowed_parts = criteria.get("allowed_parts", [])
                has_any_damage = is_damaged or is_repainted or is_replaced
                
                if has_any_damage:
                    # Kullanıcı SIFIR boya istiyorsa (liste boşsa), reddet
                    if len(allowed_parts) == 0: continue
                    # Kullanıcı bazı parçaları işaretlemediyse (liste < 11), VavaCars net hasar bölgesi vermediği için güvenli tarafta kalıp REDDEDELİM.
                    # Veya sadece kullanıcının tüm hasarları kabul ettiği durumda (liste == 11) kabul edelim.
                    if len(allowed_parts) < 11: continue
                
                painted_parts = "Hasarlı/Boyalı (Detay VavaCars'ta)" if has_any_damage else "Orijinal / Hatasız"
                
                car_id = item.get("id", "")
                make_slug = brand.lower()
                model_slug = model.lower().replace(" ", "-")
                link = f"https://tr.vava.cars/buy/cars/{make_slug}/{model_slug}/{car_id}"
                
                with engine.connect() as conn:
                    exists = conn.execute(text("SELECT 1 FROM Cars WHERE listing_id=:id"), {"id": car_id}).scalar()
                    
                if not exists:
                    car_data = {
                        "listing_id": car_id, "source_site": "VavaCars",
                        "brand": brand, "model": model, "package_trim": trim,
                        "engine_power": "", "year": year, "km": km, "price": price,
                        "location": item.get("locationCity", ""), "tramer_fee": 0,
                        "painted_parts": painted_parts, "changed_parts": "Detay VavaCars'ta" if has_any_damage else "Orijinal",
                        "link": link, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "is_new_listing": 1
                    }
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO Cars (listing_id, source_site, brand, model, package_trim, engine_power, year, km, price, location, tramer_fee, painted_parts, changed_parts, link, scraped_at, is_new_listing)
                            VALUES (:listing_id, :source_site, :brand, :model, :package_trim, :engine_power, :year, :km, :price, :location, :tramer_fee, :painted_parts, :changed_parts, :link, :scraped_at, :is_new_listing)
                        """), car_data)
                        logger.info(f"[VavaCars] HEDEFE UYAN ARAC BULUNDU: {brand} - {price} TL")
                        send_desktop_notification(brand, model, price, painted_parts)
                        
    except Exception as e:
        logger.error(f"VavaCars hata: {e}")

def scrape_otokoc(engine, criteria):
    """Otokoç 2. El için veri çekme."""
    target_brand_slug = criteria['brand'].strip().lower().replace(" ", "-") if criteria['brand'] and criteria['brand'] != "Tümü" else ""
    url = f"https://www.otokocikinciel.com/ikinci-el-araba/{target_brand_slug}" if target_brand_slug else "https://www.otokocikinciel.com/ikinci-el-araba"
    
    session = cf.Session()
    try:
        r = session.get(url, impersonate="chrome120", timeout=15)
        if r.status_code == 200:
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL | re.IGNORECASE)
            if match:
                data = json.loads(match.group(1))
                if isinstance(data, dict):
                    props = data.get('props', {})
                    if isinstance(props, dict):
                        pageProps = props.get('pageProps', {})
                        if isinstance(pageProps, dict):
                            iz = pageProps.get('initialZustandState', {})
                            if isinstance(iz, dict):
                                listing = iz.get('listing', {})
                                if isinstance(listing, dict):
                                    vehicles = listing.get('results', [])
                                    if isinstance(vehicles, list):
                                        for item in vehicles:
                                            brand = item.get("brandName", "")
                                            model = item.get("modelName", "")
                                            year = int(item.get("year", 0))
                                            km = int(item.get("mileage", 0))
                                            
                                            prices_list = item.get("prices", [])
                                            price = 0
                                            if isinstance(prices_list, list) and len(prices_list) > 0:
                                                price = int(prices_list[0].get("price", 0))
                                            elif isinstance(prices_list, dict):
                                                price = int(prices_list.get("cashPrice", 0))
                                                
                                            trim = item.get("versionName", "")
                                            
                                            if criteria['model'] and criteria['model'] != "Tümü" and criteria['model'].lower() not in model.lower(): continue
                                            if price < criteria['min_price'] or price > criteria['max_price']: continue
                                            if year < criteria['min_year'] or year > criteria['max_year']: continue
                                            if km < criteria['min_km'] or km > criteria['max_km']: continue
                                            
                                            listing_id = str(item.get("id", ""))
                                            slug = item.get("slug", "")
                                            link = f"https://www.otokocikinciel.com/ikinci-el-araba/{slug}"
                                            
                                            with engine.connect() as conn:
                                                exists = conn.execute(text("SELECT 1 FROM Cars WHERE listing_id=:id"), {"id": listing_id}).scalar()
                                                
                                            if not exists:
                                                details = scrape_listing_details(session, link, allowed_parts=criteria.get("allowed_parts", []))
                                                if details.get("rejected", False): continue
                                                
                                                tramer = details["tramer_fee"]
                                                if tramer > criteria["max_tramer"]: continue
                                                
                                                car_data = {
                                                    "listing_id": listing_id, "source_site": "Otokoç 2. El",
                                                    "brand": brand, "model": model, "package_trim": trim,
                                                    "engine_power": "", "year": year, "km": km, "price": price,
                                                    "location": item.get("cityName", ""), "tramer_fee": tramer,
                                                    "painted_parts": details["painted_parts"], "changed_parts": details["changed_parts"],
                                                    "link": link, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "is_new_listing": 1
                                                }
                                                with engine.begin() as conn:
                                                    conn.execute(text("""
                                                        INSERT INTO Cars (listing_id, source_site, brand, model, package_trim, engine_power, year, km, price, location, tramer_fee, painted_parts, changed_parts, link, scraped_at, is_new_listing)
                                                        VALUES (:listing_id, :source_site, :brand, :model, :package_trim, :engine_power, :year, :km, :price, :location, :tramer_fee, :painted_parts, :changed_parts, :link, :scraped_at, :is_new_listing)
                                                    """), car_data)
                                                    logger.info(f"[Otokoç] HEDEFE UYAN ARAC BULUNDU: {brand} - {price} TL")
                                                    send_desktop_notification(brand, model, price, details["painted_parts"])
                                                    
                                                time.sleep(1)
    except Exception as e:
        logger.error(f"Otokoc hata: {e}")

def scrape_arabam(engine, criteria):
    """Arabam.com için veri çekme (SeleniumBase UC Mode)."""
    target_brand_slug = criteria['brand'].strip().lower().replace(" ", "-") if criteria['brand'] and criteria['brand'] != "Tümü" else ""
    base_url = f"https://www.arabam.com/ikinci-el/otomobil/{target_brand_slug}" if target_brand_slug else "https://www.arabam.com/ikinci-el/otomobil"
    
    # URL parametreleri (Arabam.com formatı)
    params = f"?minPrice={criteria['min_price']}&maxPrice={criteria['max_price']}&minYear={criteria['min_year']}&maxYear={criteria['max_year']}&take=20"
    url = base_url + params
    
    try:
        from seleniumbase import SB
        with SB(uc=True, test=True, headless=True) as sb:
            sb.uc_open_with_reconnect(url, 4)
            sb.uc_gui_click_captcha()
            html = sb.get_page_source()
            soup = BeautifulSoup(html, 'html.parser')
            
            listing_links = []
            for a in soup.find_all('a', href=True):
                if '/ilan/' in a['href'] and ('-satilik-' in a['href']):
                    full_url = "https://www.arabam.com" + a['href'] if a['href'].startswith('/') else a['href']
                    if full_url not in listing_links:
                        listing_links.append(full_url)
            
            # Sadece 3 ilanı gezelim ki bot yakalanmasın
            for link in listing_links[:3]:
                listing_id = link.split('/')[-1]
                
                with engine.connect() as conn:
                    exists = conn.execute(text("SELECT 1 FROM Cars WHERE listing_id=:id"), {"id": listing_id}).scalar()
                
                if not exists:
                    sb.uc_open_with_reconnect(link, 4)
                    sb.uc_gui_click_captcha()
                    time.sleep(1.5)
                    detail_html = sb.get_page_source()
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                    
                    price_div = detail_soup.find("div", {"class": "product-price"})
                    if not price_div:
                        price_div = detail_soup.find("span", {"class": "color-red4"})
                    
                    price_text = price_div.text.strip().replace(".", "").replace("TL", "").strip() if price_div else "0"
                    price = int(re.sub(r'\D', '', price_text)) if price_text else 0
                    
                    if price < criteria['min_price'] or price > criteria['max_price']: continue
                    
                    title_h1 = detail_soup.find("h1")
                    title = title_h1.text.strip() if title_h1 else "Bilinmeyen Model"
                    
                    text_content = detail_soup.get_text(separator=' ').lower()
                    has_damage = "boya" in text_content or "değiş" in text_content or "tramer" in text_content
                    
                    # Sıfır hata isteniyorsa ve hasar tespit edildiyse reddet
                    if has_damage and len(criteria.get("allowed_parts", [])) == 0: continue
                    
                    car_data = {
                        "listing_id": listing_id, "source_site": "Arabam.com",
                        "brand": criteria['brand'] if criteria['brand'] != "Tümü" else "Arabam", 
                        "model": title[:30], "package_trim": "",
                        "engine_power": "", "year": criteria['min_year'], "km": criteria['min_km'], "price": price,
                        "location": "Bilinmiyor", "tramer_fee": 0,
                        "painted_parts": "Detay İlanda (Arabam)" if has_damage else "Temiz Görünüyor", 
                        "changed_parts": "Detay İlanda",
                        "link": link, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "is_new_listing": 1
                    }
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO Cars (listing_id, source_site, brand, model, package_trim, engine_power, year, km, price, location, tramer_fee, painted_parts, changed_parts, link, scraped_at, is_new_listing)
                            VALUES (:listing_id, :source_site, :brand, :model, :package_trim, :engine_power, :year, :km, :price, :location, :tramer_fee, :painted_parts, :changed_parts, :link, :scraped_at, :is_new_listing)
                        """), car_data)
                        logger.info(f"[Arabam.com] HEDEFE UYAN ARAC BULUNDU: {title[:20]} - {price} TL")
                        send_desktop_notification(car_data["brand"], car_data["model"], price, car_data["painted_parts"])
                        
    except Exception as e:
        logger.error(f"Arabam.com hata: {e}")

def scrape_sahibinden(engine, criteria):
    """Sahibinden.com için veri çekme (SeleniumBase UC Mode)."""
    target_brand_slug = criteria['brand'].strip().lower().replace(" ", "-") if criteria['brand'] and criteria['brand'] != "Tümü" else ""
    base_url = f"https://www.sahibinden.com/{target_brand_slug}" if target_brand_slug else "https://www.sahibinden.com/otomobil"
    
    # URL parametreleri (Sahibinden formatı)
    params = f"?a5_min={criteria['min_year']}&a5_max={criteria['max_year']}&price_min={criteria['min_price']}&price_max={criteria['max_price']}"
    url = base_url + params
    
    try:
        from seleniumbase import SB
        with SB(uc=True, test=True, headless=True) as sb:
            sb.uc_open_with_reconnect(url, 4)
            sb.uc_gui_click_captcha()
            html = sb.get_page_source()
            soup = BeautifulSoup(html, 'html.parser')
            
            listing_links = []
            for a in soup.find_all('a', href=True):
                if '/ilan/' in a['href'] and ('/detay' in a['href']):
                    full_url = "https://www.sahibinden.com" + a['href'] if a['href'].startswith('/') else a['href']
                    if full_url not in listing_links:
                        listing_links.append(full_url)
            
            # Sahibinden için sadece 2 ilana girelim
            for link in listing_links[:2]:
                listing_id = link.split('-')[-1].replace('/detay', '')
                
                with engine.connect() as conn:
                    exists = conn.execute(text("SELECT 1 FROM Cars WHERE listing_id=:id"), {"id": listing_id}).scalar()
                
                if not exists:
                    sb.uc_open_with_reconnect(link, 4)
                    sb.uc_gui_click_captcha()
                    time.sleep(2)
                    detail_html = sb.get_page_source()
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                    
                    price_h3 = detail_soup.find("h3", string=re.compile(r'TL'))
                    if not price_h3:
                        price_h3 = detail_soup.find("div", {"class": "classifiedInfo"})
                        
                    price_text = price_h3.text.strip().replace(".", "").replace("TL", "").strip() if price_h3 else "0"
                    price = int(re.sub(r'\D', '', price_text)) if price_text else 0
                    
                    title_h1 = detail_soup.find("h1")
                    title = title_h1.text.strip() if title_h1 else "Sahibinden İlanı"
                    
                    text_content = detail_soup.get_text(separator=' ').lower()
                    has_damage = "boya" in text_content or "değiş" in text_content or "tramer" in text_content
                    
                    if has_damage and len(criteria.get("allowed_parts", [])) == 0: continue
                    
                    car_data = {
                        "listing_id": listing_id, "source_site": "Sahibinden",
                        "brand": criteria['brand'] if criteria['brand'] != "Tümü" else "Sahibinden", 
                        "model": title[:30], "package_trim": "",
                        "engine_power": "", "year": criteria['min_year'], "km": criteria['min_km'], "price": price,
                        "location": "Bilinmiyor", "tramer_fee": 0,
                        "painted_parts": "Detay İlanda (Sahibinden)" if has_damage else "Temiz Görünüyor", 
                        "changed_parts": "Detay İlanda",
                        "link": link, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "is_new_listing": 1
                    }
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO Cars (listing_id, source_site, brand, model, package_trim, engine_power, year, km, price, location, tramer_fee, painted_parts, changed_parts, link, scraped_at, is_new_listing)
                            VALUES (:listing_id, :source_site, :brand, :model, :package_trim, :engine_power, :year, :km, :price, :location, :tramer_fee, :painted_parts, :changed_parts, :link, :scraped_at, :is_new_listing)
                        """), car_data)
                        logger.info(f"[Sahibinden] HEDEFE UYAN ARAC BULUNDU: {title[:20]} - {price} TL")
                        send_desktop_notification(car_data["brand"], car_data["model"], price, car_data["painted_parts"])
                        
    except Exception as e:
        logger.error(f"Sahibinden hata: {e}")

def background_scan_thread(engine, criteria):
    duration_hours = criteria['duration']
    end_time = datetime.now() + timedelta(hours=duration_hours)
    
    # Eski ilani yeni statuden cikar
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE Cars SET is_new_listing = 0"))
    except: pass
    
    while datetime.now() < end_time:
        if not st.session_state.get('scan_active', False): break
        
        # Secilen siteleri sirayla tara
        if "Otoplus" in criteria.get("sites", ["Otoplus"]):
            scrape_otoplus(engine, criteria, max_pages_per_cycle=3)
        if "VavaCars" in target_sites:
            scrape_vavacars(engine, criteria)
        if "Otokoç 2. El" in target_sites:
            scrape_otokoc(engine, criteria)
        if "Arabam.com" in target_sites:
            scrape_arabam(engine, criteria)
        if "Sahibinden" in target_sites:
            scrape_sahibinden(engine, criteria)
            
        time.sleep(60) # Her tarama döngüsü arası 1 dakika bekleri tekrar yokla
        
    st.session_state.scan_active = False

# ==========================================
#          S T R E A M L I T  A P P
# ==========================================
st.set_page_config(page_title="OtoGaleri Hedef Avcısı", layout="wide", page_icon="🎯")

if st.session_state.get('scan_active', False):
    st_autorefresh(interval=15000, key="datarefresh") # Canli modda 15 saniyede bir sayfayi guncelle

st.markdown("""
<style>
    .stApp { background-color: #0e0d12; color: #fff; }
    .css-1d391kg { background-color: #13121a; }
    h1, h2, h3, h4 { color: #fff !important; font-weight: 200; }
    .new-listing { background: rgba(0, 229, 192, 0.15); border: 1px solid #00e5c0; border-radius: 8px; padding: 10px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

engine = get_engine()
if engine: init_tables(engine)

if "scan_active" not in st.session_state: st.session_state.scan_active = False

# --- SIDEBAR (Hedef Belirleme) ---
with st.sidebar:
    st.title("🎯 Hedef Belirle")
    st.markdown("Aramak istediğiniz araç özelliklerini girin. Sistem sadece bunlara uyan araçları bulacaktır.")
    
    CAR_CATALOG = {
        "Audi": ["A3", "A4", "A5", "A6", "Q2", "Q3", "Q5", "Q7"],
        "BMW": ["1 Serisi", "2 Serisi", "3 Serisi", "4 Serisi", "5 Serisi", "X1", "X3", "X5"],
        "Citroen": ["C-Elysee", "C3", "C3 Aircross", "C4", "C5 Aircross"],
        "Dacia": ["Duster", "Sandero", "Sandero Stepway", "Logan"],
        "Fiat": ["Egea", "Fiorino", "Linea", "Punto", "Doblo"],
        "Ford": ["Focus", "Fiesta", "Courier", "Puma", "Kuga", "Mondeo"],
        "Honda": ["Civic", "CR-V", "City", "Accord"],
        "Hyundai": ["i20", "Tucson", "Bayon", "Elantra", "Accent Blue", "i10"],
        "Mercedes-Benz": ["A-Serisi", "B-Serisi", "C-Serisi", "E-Serisi", "CLA", "GLA"],
        "Opel": ["Astra", "Corsa", "Crossland", "Mokka", "Insignia"],
        "Peugeot": ["208", "2008", "308", "3008", "508", "Rifter"],
        "Renault": ["Megane", "Clio", "Symbol", "Taliant", "Captur", "Kadjar"],
        "Seat": ["Leon", "Ibiza", "Arona", "Ateca"],
        "Skoda": ["Octavia", "Superb", "Scala", "Kamiq", "Karoq"],
        "Toyota": ["Corolla", "Yaris", "C-HR", "Auris", "RAV4"],
        "Volkswagen": ["Passat", "Golf", "Polo", "T-Roc", "Tiguan", "Jetta", "Caddy"],
        "Volvo": ["S60", "S90", "XC40", "XC60", "XC90"]
    }
    
    t_brand = st.selectbox("Marka Seçin", ["Tümü"] + sorted(list(CAR_CATALOG.keys())))
    
    if t_brand == "Tümü":
        t_model = st.selectbox("Model Seçin", ["Tümü"])
    else:
        t_model = st.selectbox("Model Seçin", ["Tümü"] + sorted(CAR_CATALOG[t_brand]))

    
    col1, col2 = st.columns(2)
    with col1: t_min_price = st.number_input("Min Fiyat", value=0, step=50000)
    with col2: t_max_price = st.number_input("Max Fiyat", value=999999999, step=50000)
    
    col3, col4 = st.columns(2)
    with col3: t_min_year = st.number_input("Min Yıl", value=1970, step=1)
    with col4: t_max_year = st.number_input("Max Yıl", value=2030, step=1)
        
    col5, col6 = st.columns(2)
    with col5: t_min_km = st.number_input("Min KM", value=0, step=10000)
    with col6: t_max_km = st.number_input("Max KM", value=1000000, step=10000)
        
    t_max_tramer = st.number_input("Kabul Edilen Max Tramer (TL)", value=999999999, step=5000)
    t_duration = st.number_input("Arama Kaç Saat Sürsün?", value=1.0, step=0.5)
    
    st.subheader("🎯 Arama Kriterleri")
    target_sites = st.multiselect(
        "Taranacak Siteler",
        ["Otoplus", "VavaCars", "Otokoç 2. El", "Arabam.com", "Sahibinden"],
        default=["Otoplus", "VavaCars", "Otokoç 2. El", "Arabam.com", "Sahibinden"]
    )
    
    st.markdown("### 🚘 Kabul Edilebilir Hasar/Boya")
    st.markdown("<small style='color:#bbb;'>Aşağıdaki parçalarda boya/değişen çıkarsa kabul ediyorum (İşaretlenmeyenlerde çıkarsa araç reddedilir):</small>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2: kaput = st.checkbox("Ön Kaput 🟥")
    
    c4, c5, c6 = st.columns(3)
    with c4:
        sol_on_cam = st.checkbox("Sol Ön Çml.")
        sol_on_kapi = st.checkbox("Sol Ön Kapı")
        sol_arka_kapi = st.checkbox("Sol Arka Kapı")
        sol_arka_cam = st.checkbox("Sol Arka Çml.")
    with c5:
        st.markdown("<br><br>", unsafe_allow_html=True)
        tavan = st.checkbox("Tavan 🟦")
    with c6:
        sag_on_cam = st.checkbox("Sağ Ön Çml.")
        sag_on_kapi = st.checkbox("Sağ Ön Kapı")
        sag_arka_kapi = st.checkbox("Sağ Arka Kapı")
        sag_arka_cam = st.checkbox("Sağ Arka Çml.")
        
    c7, c8, c9 = st.columns([1, 2, 1])
    with c8: bagaj = st.checkbox("Arka Bagaj 🟪")
    
    allowed_parts = []
    if kaput: allowed_parts.append("kaput")
    if tavan: allowed_parts.append("tavan")
    if bagaj: allowed_parts.append("bagaj")
    if sol_on_cam: allowed_parts.append("sol ön çamurluk")
    if sol_on_kapi: allowed_parts.append("sol ön kapı")
    if sol_arka_kapi: allowed_parts.append("sol arka kapı")
    if sol_arka_cam: allowed_parts.append("sol arka çamurluk")
    if sag_on_cam: allowed_parts.append("sağ ön çamurluk")
    if sag_on_kapi: allowed_parts.append("sağ ön kapı")
    if sag_arka_kapi: allowed_parts.append("sağ arka kapı")
    if sag_arka_cam: allowed_parts.append("sağ arka çamurluk")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    submit_btn = st.button("🚀 Hedefli Taramayı Başlat", use_container_width=True)

    if submit_btn:
        st.session_state.scan_active = True
        criteria = {
            "sites": t_sites,
            "brand": t_brand, "model": t_model,
            "min_price": t_min_price, "max_price": t_max_price,
            "min_year": t_min_year, "max_year": t_max_year,
            "min_km": t_min_km, "max_km": t_max_km,
            "max_tramer": t_max_tramer, "duration": t_duration,
            "allowed_parts": allowed_parts
        }
        t = threading.Thread(target=background_scan_thread, args=(engine, criteria), daemon=True)
        add_script_run_ctx(t)
        t.start()
        st.rerun()
        
    if st.session_state.scan_active:
        st.success("Avcı Modu Aktif! Yeni araçlar eklendikçe sayfaya düşecek.")
        if st.button("🛑 Taramayı Durdur", use_container_width=True):
            st.session_state.scan_active = False
            st.rerun()
            
    st.divider()
    if st.button("🗑️ Bulunan Tüm Sonuçları Sil (Veritabanını Temizle)"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM Cars"))
        st.success("Tüm sonuçlar silindi.")
        st.rerun()

# --- ANA EKRAN ---
st.title("🎯 Avcı Modu - Bulunan Hedef Araçlar")

df = load_data(engine)

if not df.empty:
    new_listings = df[df["is_new_listing"] == 1]
    if not new_listings.empty:
        st.markdown(f"### 🚨 YENİ YAKALANAN ARAÇLAR ({len(new_listings)} adet)")
        for idx, row in new_listings.iterrows():
            badge_color = "#ff4b4b" if row['source_site'] == "Otoplus" else ("#1e90ff" if row['source_site'] == "VavaCars" else "#ffa500")
            st.markdown(f"""
            <div class="new-listing">
                <span style="background:{badge_color}; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold; margin-right:10px;">{row['source_site']}</span>
                <b>{row['brand']} {row['model']} {row['package_trim']}</b> ({row['year']} | {row['km']} km) - 
                <span style="color:#00e5c0; font-size:18px;"><b>{row['price']:,} ₺</b></span>
                <br>
                <small>Boya: {row['painted_parts']} | Değişen: {row['changed_parts']} | Tramer: {row['tramer_fee']} ₺</small>
                <br>
                <a href="{row['link']}" target="_blank" style="color:#4d9fff; font-size:12px;">İlana Git ↗</a>
            </div>
            """, unsafe_allow_html=True)
        st.divider()

    st.markdown(f"### 📋 Şu Ana Kadar Bulunan Tüm Araçlar ({len(df)})")
    
    show_cols = ["source_site", "brand", "model", "package_trim", "engine_power", "year", "km", "price", "tramer_fee", "painted_parts", "changed_parts", "link", "scraped_at"]
    df_show = df[[c for c in show_cols if c in df.columns]].copy()
    
    st.dataframe(
        df_show, 
        use_container_width=True, 
        height=500,
        column_config={
            "link": st.column_config.LinkColumn("İlan Linki", display_text="İlana Git"),
            "price": st.column_config.NumberColumn("Fiyat (TL)", format="%d ₺"),
            "tramer_fee": st.column_config.NumberColumn("Tramer", format="%d ₺")
        }
    )
else:
    st.info("Henüz hedeflerinize uygun araç bulunamadı. Lütfen sol menüden hedef kriterlerinizi girip 'Hedefli Taramayı Başlat' butonuna basın.")
