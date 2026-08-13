"""Tum sistem testi"""
import pyodbc
import urllib.request
import sys

print("=" * 60)
print("  OTOPLUS PROJE - SISTEM TESTI")
print("=" * 60)

# ---- TEST 1: MSSQL ----
print("\n[TEST 1] MSSQL Veritabani Baglantisi")
try:
    conn = pyodbc.connect(
        r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=MERTPC\SQLEXPRESS;DATABASE=OtoplusDB;Trusted_Connection=yes;",
        timeout=5
    )
    cursor = conn.cursor()
    print("  [OK] MSSQL baglantisi basarili!")

    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"  [OK] Tablolar: {tables}")

    cursor.execute("SELECT COUNT(*) FROM vehicles")
    count = cursor.fetchone()[0]
    print(f"  [OK] vehicles tablosunda {count} kayit var.")

    if count > 0:
        cursor.execute("SELECT TOP 3 listing_id, brand, price FROM vehicles")
        for row in cursor.fetchall():
            print(f"       -> ID:{row[0]} | {row[1]} | {row[2]} TL")

    cursor.execute("SELECT work_hours_start, work_hours_end, interval_hours FROM scraper_settings")
    row = cursor.fetchone()
    if row:
        print(f"  [OK] scraper_settings: Basla={row[0]}:00, Bitis={row[1]}:00, Aralik={row[2]} saat")
    else:
        print("  [UYARI] scraper_settings tablosu bos!")

    conn.close()
except Exception as e:
    print(f"  [HATA] MSSQL: {e}")

# ---- TEST 2: Flask (port 5000) ----
print("\n[TEST 2] Flask Sunucusu (port 5000)")
try:
    resp = urllib.request.urlopen("http://localhost:5000", timeout=5)
    code = resp.getcode()
    body = resp.read().decode("utf-8", errors="ignore")
    has_dashboard_link = "8501" in body
    print(f"  [OK] HTTP {code} - Sayfa basariyla yuklendi.")
    print(f"  [OK] Dashboard butonu {'MEVCUT' if has_dashboard_link else 'EKSIK'}.")
except Exception as e:
    print(f"  [HATA] Flask erisim: {e}")

# ---- TEST 3: Streamlit (port 8501) ----
print("\n[TEST 3] Streamlit Dashboard (port 8501)")
try:
    resp = urllib.request.urlopen("http://localhost:8501", timeout=5)
    code = resp.getcode()
    print(f"  [OK] HTTP {code} - Streamlit basariyla yuklendi.")
except Exception as e:
    print(f"  [HATA] Streamlit erisim: {e}")

# ---- TEST 4: Proxy ----
print("\n[TEST 4] Proxy Testi (ilk proxy)")
try:
    from curl_cffi import requests as cf
    proxy_url = "http://tsopwmzy:4fk9a8lixuuy@191.96.254.138:6185"
    proxies = {"http": proxy_url, "https": proxy_url}
    session = cf.Session()
    r = session.get("https://httpbin.org/ip", impersonate="chrome120", proxies=proxies, timeout=10)
    if r.status_code == 200:
        print(f"  [OK] Proxy calisiyor! IP: {r.json().get('origin', '?')}")
    else:
        print(f"  [UYARI] Proxy yanit verdi ama status: {r.status_code}")
except Exception as e:
    print(f"  [UYARI] Proxy: {e}")

# ---- TEST 5: Scraper Parse ----
print("\n[TEST 5] Scraper Parse Fonksiyonu")
try:
    from curl_cffi import requests as cf
    import json, re
    from bs4 import BeautifulSoup
    
    proxy_url = "http://tsopwmzy:4fk9a8lixuuy@142.111.67.146:5611"
    proxies = {"http": proxy_url, "https": proxy_url}
    session = cf.Session()
    
    resp = session.get("https://www.otoplus.com/ikinci-el-araba", impersonate="chrome120", proxies=proxies, timeout=15)
    if resp.status_code == 200 and len(resp.text) > 5000:
        soup = BeautifulSoup(resp.text, "lxml")
        tags = soup.find_all("script", {"type": "application/ld+json"})
        vehicle_count = 0
        for tag in tags:
            try:
                data = json.loads(tag.string)
                for item in data.get("@graph", []):
                    if item.get("@type") == "Vehicle":
                        vehicle_count += 1
            except:
                pass
        print(f"  [OK] Sayfa basariyla cekildi ({len(resp.text)} byte)")
        print(f"  [OK] JSON-LD icerisinde {vehicle_count} arac bulundu.")
    else:
        print(f"  [UYARI] Sayfa cekildi ama icerik yetersiz (status: {resp.status_code}, boyut: {len(resp.text)})")
except Exception as e:
    print(f"  [UYARI] Scraper test: {e}")

print("\n" + "=" * 60)
print("  TEST TAMAMLANDI")
print("=" * 60)
