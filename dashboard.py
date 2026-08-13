"""
Otoplus Scraper - Streamlit Dashboard v2
=========================================
Kullanıcı filtreleri girer → "Aramaya Başla" butonuna basar → 
Scraper çalışır → Sonuçlar ekranda ve veritabanında gösterilir.

Çalıştırma: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import datetime
from io import BytesIO
import logging
import time
import json
import random
import re
import sys
import os

from curl_cffi import requests as cf
from bs4 import BeautifulSoup

# ---------- SAYFA AYARLARI ----------
st.set_page_config(
    page_title="Otoplus Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- LOGLAMA ----------
logger = logging.getLogger("Dashboard")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler("dashboard_log.txt", encoding="utf-8")
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    logger.addHandler(fh)

# ---------- VERITABANI ----------
DB_SERVER = r"MERTPC\SQLEXPRESS"
DB_NAME = "OtoplusDB"

@st.cache_resource
def get_engine():
    try:
        conn_str = f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
        engine = create_engine(conn_str, pool_size=5, max_overflow=10, pool_pre_ping=True)
        return engine
    except Exception as e:
        logger.error(f"DB Engine hatasi: {e}")
        return None

def init_db(engine):
    if not engine:
        return
    try:
        from sqlalchemy import MetaData, Table, Column, Integer, String
        metadata = MetaData()
        Table('vehicles', metadata,
            Column('listing_id', String(50), primary_key=True),
            Column('title', String(255)), Column('brand', String(100)),
            Column('year', Integer), Column('km', Integer),
            Column('fuel', String(50)), Column('transmission', String(50)),
            Column('price', Integer), Column('currency', String(10)),
            Column('location', String(100)), Column('link', String(500)),
            Column('image', String(500)), Column('scraped_at', String(50))
        )
        Table('scraper_settings', metadata,
            Column('id', Integer, primary_key=True),
            Column('work_hours_start', Integer),
            Column('work_hours_end', Integer),
            Column('interval_hours', Integer)
        )
        metadata.create_all(engine)
        with engine.begin() as conn:
            if conn.execute(text("SELECT COUNT(*) FROM scraper_settings")).scalar() == 0:
                conn.execute(text("INSERT INTO scraper_settings (work_hours_start, work_hours_end, interval_hours) VALUES (9, 22, 2)"))
    except Exception as e:
        logger.error(f"init_db hatasi: {e}")

def load_data(engine):
    if not engine:
        return pd.DataFrame()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT * FROM vehicles"), conn)
        if not df.empty:
            for col in ["year", "km", "price"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            if "scraped_at" in df.columns:
                df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
        return df
    except Exception as e:
        logger.error(f"Veri cekme hatasi: {e}")
        return pd.DataFrame()

def save_to_db(engine, data_list):
    if not engine or not data_list:
        return 0, 0
    inserted, updated = 0, 0
    with engine.begin() as conn:
        for item in data_list:
            try:
                check = text("SELECT listing_id FROM vehicles WHERE listing_id = :listing_id")
                if conn.execute(check, {"listing_id": item['listing_id']}).fetchone():
                    upd = text("UPDATE vehicles SET price=:price, scraped_at=:scraped_at WHERE listing_id=:listing_id")
                    conn.execute(upd, item)
                    updated += 1
                else:
                    ins = text(
                        "INSERT INTO vehicles (listing_id,title,brand,year,km,fuel,transmission,price,currency,location,link,image,scraped_at) "
                        "VALUES (:listing_id,:title,:brand,:year,:km,:fuel,:transmission,:price,:currency,:location,:link,:image,:scraped_at)"
                    )
                    conn.execute(ins, item)
                    inserted += 1
            except Exception as e:
                logger.error(f"Kayit hatasi ({item.get('listing_id')}): {e}")
    return inserted, updated

# ---------- PROXY & SCRAPER ----------
PROXY_LIST_URL = "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt"

def fetch_proxy_list():
    """Ücretsiz proxy listesini internetten çeker. Her aramada güncel liste alınır."""
    try:
        import urllib.request
        resp = urllib.request.urlopen(PROXY_LIST_URL, timeout=10)
        raw = resp.read().decode("utf-8", errors="ignore")
        proxies = []
        for line in raw.strip().splitlines():
            line = line.strip()
            if line.startswith("http"):
                # Format: http://IP:PORT
                proxies.append({"http": line, "https": line})
        if proxies:
            logger.info(f"{len(proxies)} ücretsiz proxy yüklendi.")
            return proxies
    except Exception as e:
        logger.warning(f"Proxy listesi indirilemedi: {e}")
    return []

PROXY_LIST = fetch_proxy_list()

def parse_jsonld_vehicles(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    tags = soup.find_all("script", {"type": "application/ld+json"})
    results = []
    now_str = datetime.now().isoformat(timespec="seconds")
    for tag in tags:
        try:
            data = json.loads(tag.string)
            for item in data.get("@graph", []):
                if item.get("@type") != "Vehicle":
                    continue
                url = item.get("offers", {}).get("url") or item.get("url") or ""
                lid_match = re.search(r"-(\d{5,8})$", url)
                if not lid_match:
                    continue
                trans = item.get("vehicleTransmission", "")
                results.append({
                    "listing_id": lid_match.group(1),
                    "title": item.get("name", ""),
                    "brand": item.get("brand", {}).get("name", "") if isinstance(item.get("brand"), dict) else "",
                    "year": int(item.get("vehicleModelDate") or item.get("productionDate") or 0),
                    "km": int(item.get("mileageFromOdometer", {}).get("value", 0)),
                    "fuel": item.get("vehicleEngine", {}).get("fuelType", ""),
                    "transmission": "Otomatik" if "auto" in str(trans).lower() else "Manuel",
                    "price": int(item.get("offers", {}).get("price", 0)),
                    "currency": item.get("offers", {}).get("priceCurrency", "TRY"),
                    "location": "",
                    "link": url,
                    "image": item.get("image", ""),
                    "scraped_at": now_str
                })
        except Exception:
            pass
    return results


def find_working_proxies(proxy_list, max_test=30, status_text=None):
    """Proxy listesinden çalışanları hızlıca bulur (kısa timeout ile)."""
    import concurrent.futures
    working = []
    sample = random.sample(proxy_list, min(max_test, len(proxy_list)))

    if status_text:
        status_text.info(f"🔄 {len(sample)} proxy test ediliyor...")

    def test_one(proxy):
        try:
            s = cf.Session()
            r = s.get("https://www.otoplus.com/", impersonate="chrome120", proxies=proxy, timeout=6)
            if r.status_code == 200 and len(r.text) > 3000:
                return proxy
        except Exception:
            pass
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(test_one, p): p for p in sample}
        for f in concurrent.futures.as_completed(futures):
            result = f.result()
            if result:
                working.append(result)
                if len(working) >= 5:  # 5 çalışan proxy yeterli
                    break

    if status_text:
        if working:
            status_text.success(f"✅ {len(working)} çalışan proxy bulundu!")
        else:
            status_text.warning("⚠️ Çalışan proxy bulunamadı, direkt bağlantı denenecek.")
    return working

def run_scraper(max_pages, progress_bar, status_text):
    """Scraper pipeline — önce çalışan proxy bulur, sonra tarar."""
    base_url = "https://www.otoplus.com/ikinci-el-araba"
    all_listings = []
    seen = set()

    # Önce çalışan proxy'leri bul
    working_proxies = []
    if PROXY_LIST:
        working_proxies = find_working_proxies(PROXY_LIST, max_test=40, status_text=status_text)

    for page in range(1, max_pages + 1):
        progress_bar.progress(page / max_pages, text=f"Sayfa {page}/{max_pages} taranıyor...")
        status_text.info(f"🔍 Sayfa {page}/{max_pages} taranıyor...")

        url = base_url if page == 1 else f"{base_url}?sayfa={page}"
        html = None

        # Çalışan proxy'lerle dene
        for proxy in working_proxies:
            try:
                session = cf.Session()
                resp = session.get(url, impersonate="chrome120", proxies=proxy, timeout=12)
                if resp.status_code == 200 and len(resp.text) > 10000:
                    html = resp.text
                    break
            except Exception:
                pass

        # Proxy başarısız → Direkt bağlantı (fallback)
        if not html:
            try:
                session = cf.Session()
                resp = session.get(url, impersonate="chrome120", timeout=15)
                if resp.status_code == 200 and len(resp.text) > 10000:
                    html = resp.text
                    status_text.info(f"📡 Sayfa {page} direkt bağlantı ile alındı.")
            except Exception:
                pass

        if not html:
            status_text.warning(f"⚠️ Sayfa {page} alınamadı, atlanıyor.")
            continue

        vehicles = parse_jsonld_vehicles(html)
        for v in vehicles:
            if v["listing_id"] not in seen:
                seen.add(v["listing_id"])
                all_listings.append(v)

        status_text.success(f"✅ Sayfa {page}: {len(vehicles)} ilan bulundu.")
        if page < max_pages:
            time.sleep(random.uniform(3, 6))

    progress_bar.progress(1.0, text="Tarama tamamlandı!")
    return all_listings


# ---------- KARANLK TEMA CSS ----------
st.markdown("""
<style>
    .stApp { background-color: #0e0d12 !important; }
    [data-testid="stSidebar"] { background-color: #13121a !important; border-right: 1px solid rgba(255,255,255,0.06) !important; }

    [data-testid="stMetric"] {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 20px 24px;
    }
    [data-testid="stMetricLabel"] { color: rgba(255,255,255,0.45) !important; font-size: 12px !important; letter-spacing: 0.08em !important; }
    [data-testid="stMetricValue"] { color: #fff !important; font-weight: 200 !important; }

    .stButton > button {
        border-radius: 100px !important;
        border: 1px solid rgba(255,255,255,0.18) !important;
        background: rgba(255,255,255,0.06) !important;
        color: rgba(255,255,255,0.85) !important;
        font-size: 13px !important;
        padding: 10px 24px !important;
    }
    .stButton > button:hover {
        background: rgba(255,255,255,0.12) !important;
        border-color: rgba(255,255,255,0.35) !important;
    }

    .stDownloadButton > button {
        border-radius: 100px !important;
        border: 1px solid rgba(77,159,255,0.3) !important;
        background: rgba(77,159,255,0.08) !important;
        color: rgba(255,255,255,0.85) !important;
    }

    hr { border-color: rgba(255,255,255,0.06) !important; }
    h1, h2, h3 { color: #fff !important; font-weight: 200 !important; }

    .gradient-title {
        font-size: 32px; font-weight: 100;
        background: linear-gradient(135deg, #4d9fff 0%, #00e5c0 50%, #b066ff 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 4px;
    }
    .sub-label {
        font-size: 13px; color: rgba(255,255,255,0.35);
        letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 24px;
    }

    /* Büyük başlat butonu */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(77,159,255,0.25), rgba(0,229,192,0.2)) !important;
        border: 1px solid rgba(77,159,255,0.4) !important;
        color: #fff !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        padding: 14px 32px !important;
        letter-spacing: 0.06em !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, rgba(77,159,255,0.4), rgba(0,229,192,0.35)) !important;
        border-color: rgba(77,159,255,0.6) !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------- SESSION STATE ----------
if "favorites" not in st.session_state:
    st.session_state.favorites = set()
if "search_done" not in st.session_state:
    st.session_state.search_done = False
if "last_results" not in st.session_state:
    st.session_state.last_results = pd.DataFrame()

# ---------- DB INIT ----------
engine = get_engine()
if engine:
    init_db(engine)

# ==========================================
#          S I D E B A R  (KRİTERLER)
# ==========================================
with st.sidebar:
    st.markdown('<p class="gradient-title">🚗 Otoplus</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-label">Araç Arama & Analiz</p>', unsafe_allow_html=True)

    st.divider()
    st.subheader("🔧 Tarama Ayarları")

    max_pages = st.slider("Kaç sayfa taransın?", 1, 20, 5, key="max_pages")

    st.divider()
    st.subheader("🔎 Filtreleme Kriterleri")
    st.caption("Aşağıdaki kriterleri girin, ardından 'Aramaya Başla' butonuna basın.")

    # Sabit marka listesi (Otoplus'ta en yaygın markalar)
    BRAND_OPTIONS = [
        "Audi", "BMW", "Citroen", "Dacia", "Fiat", "Ford", "Honda", "Hyundai",
        "Kia", "Mercedes-Benz", "Nissan", "Opel", "Peugeot", "Renault", "Seat",
        "Skoda", "Toyota", "Volkswagen", "Volvo"
    ]
    selected_brands = st.multiselect("Marka", BRAND_OPTIONS, default=[], key="f_brand")

    FUEL_OPTIONS = ["Benzin", "Dizel", "Benzin & LPG", "Hybrid", "Elektrik"]
    selected_fuels = st.multiselect("Yakıt Tipi", FUEL_OPTIONS, default=[], key="f_fuel")

    TRANS_OPTIONS = ["Otomatik", "Manuel"]
    selected_trans = st.multiselect("Vites", TRANS_OPTIONS, default=[], key="f_trans")

    st.divider()

    price_range = st.slider("Fiyat Aralığı (₺)", 0, 5_000_000, (0, 5_000_000), step=50_000, format="%d ₺", key="f_price")
    km_range = st.slider("Kilometre Aralığı", 0, 500_000, (0, 500_000), step=10_000, format="%d km", key="f_km")
    year_range = st.slider("Model Yılı", 2005, 2026, (2005, 2026), key="f_year")

    st.divider()

    # ===== ANA BUTON =====
    start_search = st.button("🚀 ARAMAYA BAŞLA", use_container_width=True, type="primary", key="start_btn")

    st.divider()

    # Mevcut veriyi göster butonu
    show_existing = st.button("📂 Mevcut Verileri Göster", use_container_width=True, key="show_existing_btn")

# ==========================================
#          A N A   İ Ç E R İ K
# ==========================================
st.markdown('<p class="gradient-title">Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-label">Kriterleri girin → Aramaya Başla</p>', unsafe_allow_html=True)

# ---------- ARAMA BAŞLATILDI ----------
if start_search:
    st.session_state.search_done = False
    st.markdown("---")
    st.markdown("### ⏳ Tarama Süreci")

    progress_bar = st.progress(0, text="Hazırlanıyor...")
    status_area = st.empty()

    # Scraper çalıştır
    raw_results = run_scraper(max_pages, progress_bar, status_area)

    if raw_results:
        # Veritabanına kaydet
        if engine:
            ins, upd = save_to_db(engine, raw_results)
            st.success(f"✅ Tarama tamamlandı! **{len(raw_results)}** ilan bulundu. (DB: {ins} yeni, {upd} güncellendi)")
        else:
            st.warning(f"Tarama tamamlandı! {len(raw_results)} ilan bulundu ama DB bağlantısı yok.")

        # DataFrame oluştur
        df_results = pd.DataFrame(raw_results)
        for col in ["year", "km", "price"]:
            if col in df_results.columns:
                df_results[col] = pd.to_numeric(df_results[col], errors="coerce").fillna(0).astype(int)

        # Kullanıcının girdiği filtreleri uygula
        if selected_brands:
            df_results = df_results[df_results["brand"].isin(selected_brands)]
        if selected_fuels:
            df_results = df_results[df_results["fuel"].isin(selected_fuels)]
        if selected_trans:
            df_results = df_results[df_results["transmission"].isin(selected_trans)]
        df_results = df_results[(df_results["price"] >= price_range[0]) & (df_results["price"] <= price_range[1])]
        df_results = df_results[(df_results["km"] >= km_range[0]) & (df_results["km"] <= km_range[1])]
        df_results = df_results[(df_results["year"] >= year_range[0]) & (df_results["year"] <= year_range[1])]

        st.session_state.last_results = df_results
        st.session_state.search_done = True
    else:
        st.error("❌ Hiç ilan bulunamadı. Proxy'ler yanıt vermiyor olabilir.")
        st.session_state.search_done = False

# ---------- MEVCUT VERİLERİ GÖSTER ----------
if show_existing and engine:
    df_existing = load_data(engine)
    if not df_existing.empty:
        # Filtreleri uygula
        if selected_brands:
            df_existing = df_existing[df_existing["brand"].isin(selected_brands)]
        if selected_fuels:
            df_existing = df_existing[df_existing["fuel"].isin(selected_fuels)]
        if selected_trans:
            df_existing = df_existing[df_existing["transmission"].isin(selected_trans)]
        df_existing = df_existing[(df_existing["price"] >= price_range[0]) & (df_existing["price"] <= price_range[1])]
        df_existing = df_existing[(df_existing["km"] >= km_range[0]) & (df_existing["km"] <= km_range[1])]
        df_existing = df_existing[(df_existing["year"] >= year_range[0]) & (df_existing["year"] <= year_range[1])]
        st.session_state.last_results = df_existing
        st.session_state.search_done = True
        st.success(f"📂 Veritabanından **{len(df_existing)}** ilan yüklendi (filtrelendi).")
    else:
        st.warning("Veritabanında henüz veri yok. Önce 'Aramaya Başla' butonunu kullanın.")

# ==========================================
#    S O N U Ç L A R  (Tarama sonrası)
# ==========================================
if st.session_state.search_done and not st.session_state.last_results.empty:
    df = st.session_state.last_results

    st.divider()

    # --- KPI METRIKLER ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Toplam İlan", f"{len(df):,}")
    c2.metric("💰 Ort. Fiyat", f"{int(df['price'].mean()):,} ₺")
    c3.metric("🛣️ Ort. KM", f"{int(df['km'].mean()):,} km")
    c4.metric("🏷️ Marka Sayısı", f"{df['brand'].nunique()}")

    st.divider()

    # --- GRAFİKLER ---
    COLOR_PALETTE = ["#4d9fff", "#00e5c0", "#b066ff", "#ff6b6b", "#ffd93d", "#6bcf7f", "#ff9f43", "#a29bfe"]
    PLOT_LAYOUT = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="rgba(255,255,255,0.6)", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
        legend=dict(bgcolor="rgba(0,0,0,0)")
    )

    tab1, tab2, tab3 = st.tabs(["📈 Trend & Genel", "🏆 Top 10", "🗺️ Dağılımlar"])

    with tab1:
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("#### Fiyat Trendi")
            if "scraped_at" in df.columns:
                trend = df.copy()
                trend["scraped_at"] = pd.to_datetime(trend["scraped_at"], errors="coerce")
                trend = trend.dropna(subset=["scraped_at"])
                if not trend.empty:
                    trend["tarih"] = trend["scraped_at"].dt.date
                    trend_agg = trend.groupby("tarih")["price"].mean().reset_index()
                    trend_agg.columns = ["Tarih", "Ort. Fiyat"]
                    fig = px.line(trend_agg, x="Tarih", y="Ort. Fiyat", color_discrete_sequence=["#4d9fff"])
                    fig.update_layout(**PLOT_LAYOUT)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("Tarih verisi yok.")
            else:
                st.caption("Tarih verisi yok.")

        with col_r:
            st.markdown("#### Markalara Göre İlan Sayısı")
            bc = df["brand"].value_counts().head(15).reset_index()
            bc.columns = ["Marka", "Adet"]
            fig2 = px.bar(bc, x="Adet", y="Marka", orientation="h", color_discrete_sequence=["#00e5c0"])
            fig2.update_layout(**PLOT_LAYOUT)
            fig2.update_yaxes(autorange="reversed", gridcolor="rgba(255,255,255,0.04)")
            st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        col_c, col_e = st.columns(2)
        with col_c:
            st.markdown("#### 🟢 En Uygun 10 Araç")
            t10c = df.nsmallest(10, "price")[["title", "brand", "year", "km", "price"]].reset_index(drop=True)
            fig3 = px.bar(t10c, x="price", y="title", orientation="h", color_discrete_sequence=["#00e5c0"])
            fig3.update_layout(**PLOT_LAYOUT, height=400)
            fig3.update_yaxes(autorange="reversed", gridcolor="rgba(255,255,255,0.04)")
            st.plotly_chart(fig3, use_container_width=True)
        with col_e:
            st.markdown("#### 🔴 En Pahalı 10 Araç")
            t10e = df.nlargest(10, "price")[["title", "brand", "year", "km", "price"]].reset_index(drop=True)
            fig4 = px.bar(t10e, x="price", y="title", orientation="h", color_discrete_sequence=["#b066ff"])
            fig4.update_layout(**PLOT_LAYOUT, height=400)
            fig4.update_yaxes(autorange="reversed", gridcolor="rgba(255,255,255,0.04)")
            st.plotly_chart(fig4, use_container_width=True)

    with tab3:
        col_p, col_f = st.columns(2)
        with col_p:
            st.markdown("#### Şehir Dağılımı")
            loc = df[df["location"].astype(str).str.strip() != ""]
            if not loc.empty:
                lc = loc["location"].value_counts().head(10).reset_index()
                lc.columns = ["Şehir", "Adet"]
                fig5 = px.pie(lc, names="Şehir", values="Adet", color_discrete_sequence=COLOR_PALETTE, hole=0.45)
                fig5.update_layout(**PLOT_LAYOUT)
                st.plotly_chart(fig5, use_container_width=True)
            else:
                st.caption("Şehir verisi yok.")
        with col_f:
            st.markdown("#### Yakıt Tipi Dağılımı")
            fc = df["fuel"].value_counts().reset_index()
            fc.columns = ["Yakıt", "Adet"]
            fig6 = px.pie(fc, names="Yakıt", values="Adet", color_discrete_sequence=COLOR_PALETTE[2:], hole=0.45)
            fig6.update_layout(**PLOT_LAYOUT)
            st.plotly_chart(fig6, use_container_width=True)

    st.divider()

    # --- VERİ TABLOSU & EXPORT ---
    st.markdown("#### 📊 Filtrelenmiş Araç Verileri")
    display_cols = [c for c in ["listing_id","title","brand","year","km","fuel","transmission","price","currency","location","scraped_at","link"] if c in df.columns]
    col_rename = {
        "listing_id": "İlan ID", "title": "Başlık", "brand": "Marka", "year": "Yıl",
        "km": "KM", "fuel": "Yakıt", "transmission": "Vites", "price": "Fiyat (₺)",
        "currency": "Para Birimi", "location": "Şehir", "scraped_at": "Çekilme Tarihi", "link": "İlan Linki"
    }
    df_show = df[display_cols].rename(columns=col_rename)
    st.dataframe(
        df_show, 
        use_container_width=True, 
        height=450,
        column_config={
            "İlan Linki": st.column_config.LinkColumn("İlan Linki", display_text="İlana Git")
        }
    )
    st.caption(f"Toplam {len(df_show)} sonuç.")

    exp1, exp2, _ = st.columns([1, 1, 4])
    with exp1:
        csv = df_show.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 CSV İndir", csv, "otoplus_veriler.csv", "text/csv", use_container_width=True)
    with exp2:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
            df_show.to_excel(w, index=False, sheet_name="Araclar")
        st.download_button("📥 Excel İndir", buf.getvalue(), "otoplus_veriler.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    st.divider()

    # --- FAVORİLER & KARŞILAŞTIRMA ---
    st.markdown("#### ⭐ Favoriler & Karşılaştırma")
    fav_tab, cmp_tab = st.tabs(["⭐ Favorilere Ekle", "⚖️ Araç Karşılaştır"])

    with fav_tab:
        opts = df[["listing_id","title","brand","price"]].copy()
        opts["label"] = opts["brand"] + " - " + opts["title"] + " (" + opts["price"].astype(str) + " ₺)"
        sel = st.selectbox("Favorilere eklemek istediğiniz araç:", opts["label"].tolist(), key="fav_sel")
        ca, cb, _ = st.columns([1, 1, 4])
        with ca:
            if st.button("⭐ Ekle", key="add_f"):
                idx = opts[opts["label"] == sel]["listing_id"].values
                if len(idx) > 0:
                    st.session_state.favorites.add(idx[0])
                    st.success("Favorilere eklendi!")
        with cb:
            if st.button("🗑️ Temizle", key="clr_f"):
                st.session_state.favorites.clear()
                st.info("Favoriler temizlendi.")
        if st.session_state.favorites:
            fav_df = df[df["listing_id"].isin(st.session_state.favorites)]
            if not fav_df.empty:
                st.dataframe(fav_df[display_cols].rename(columns=col_rename), use_container_width=True, height=200)

    with cmp_tab:
        st.caption("2 veya 3 araç seçerek yan yana karşılaştırın.")
        opts2 = df[["listing_id","title","brand","price"]].copy()
        opts2["label"] = opts2["brand"] + " - " + opts2["title"] + " (" + opts2["price"].astype(str) + " ₺)"
        cmp_sel = st.multiselect("Karşılaştır:", opts2["label"].tolist(), max_selections=3, key="cmp_sel")
        if cmp_sel:
            cmp_ids = opts2[opts2["label"].isin(cmp_sel)]["listing_id"].tolist()
            cmp_df = df[df["listing_id"].isin(cmp_ids)]
            if not cmp_df.empty:
                cmp_cols = [c for c in ["title","brand","year","km","fuel","transmission","price","location"] if c in cmp_df.columns]
                cmp_show = cmp_df[cmp_cols].set_index("title").T
                cmp_show.index = [col_rename.get(i, i) for i in cmp_show.index]
                st.table(cmp_show)
                fig_c = go.Figure()
                fig_c.add_trace(go.Bar(name="Fiyat (₺)", x=cmp_df["title"], y=cmp_df["price"], marker_color="#4d9fff"))
                fig_c.add_trace(go.Bar(name="KM", x=cmp_df["title"], y=cmp_df["km"], marker_color="#00e5c0"))
                fig_c.update_layout(**PLOT_LAYOUT, barmode="group", title="Fiyat & KM Karşılaştırması", height=350)
                st.plotly_chart(fig_c, use_container_width=True)

# ---------- BOŞ DURUM ----------
elif not st.session_state.search_done:
    st.markdown("---")
    st.markdown("""
    <div style="text-align:center; padding:80px 20px;">
        <p style="font-size:48px; margin-bottom:16px;">🔍</p>
        <p style="font-size:20px; color:rgba(255,255,255,0.5); font-weight:200;">
            Sol panelden kriterleri girin ve<br>
            <span style="color:#4d9fff; font-weight:400;">"🚀 ARAMAYA BAŞLA"</span> butonuna basın.
        </p>
        <p style="font-size:13px; color:rgba(255,255,255,0.25); margin-top:12px; letter-spacing:0.1em;">
            Veya mevcut veritabanı verilerini görmek için "📂 Mevcut Verileri Göster" butonunu kullanın.
        </p>
    </div>
    """, unsafe_allow_html=True)

# ---------- FOOTER ----------
st.divider()
st.markdown(
    '<p style="text-align:center;color:rgba(255,255,255,0.2);font-size:12px;letter-spacing:0.1em;">'
    '© 2025 OTOPLUS DASHBOARD · Data-driven vehicle intelligence'
    '</p>',
    unsafe_allow_html=True
)
