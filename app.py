"""
app.py - OtoGaleriBot Streamlit Arayüzü
==========================================
Sadece UI katmanı. İş mantığı scrapers.py, db.py, notifications.py'de.
"""

import streamlit as st
import threading
import time
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
from streamlit.runtime.scriptrunner import add_script_run_ctx

from config import ALL_SITES, SCRAPER_CYCLE_INTERVAL_SEC
from logger_setup import logger
from db import get_engine, init_tables, load_data, mark_all_as_seen, clear_all
from scrapers import run_one_cycle


# ==========================================================================
#  ARKA PLAN TARAMA THREAD'İ
# ==========================================================================

def background_scan_thread(engine, criteria, stop_event):
    """
    Arka plan tarama döngüsü. Thread-safe durdurma için threading.Event kullanır.
    BUG FIX: Eski kodda st.session_state thread içinden okunuyordu — bu thread-safe
    değildi çünkü Streamlit session_state yalnızca ana thread'den güvenli erişilebilir.
    Şimdi threading.Event kullanılıyor: stop_event.set() ile güvenle durdurulabiliyor.
    """
    duration_hours = criteria['duration']
    end_time = datetime.now() + timedelta(hours=duration_hours)

    # Eski ilanları "görüldü" olarak işaretle
    mark_all_as_seen(engine)

    while datetime.now() < end_time:
        if stop_event.is_set():
            logger.info("Tarama stop_event ile durduruldu.")
            break

        run_one_cycle(engine, criteria)

        # Döngü arası bekleme — stop_event ile erken çıkılabilir
        stop_event.wait(timeout=SCRAPER_CYCLE_INTERVAL_SEC)

    logger.info("Tarama döngüsü tamamlandi.")


# ==========================================================================
#  STREAMLIT ARAYÜZÜ
# ==========================================================================

st.set_page_config(page_title="OtoGaleri Hedef Avcısı", layout="wide", page_icon="🎯")

# Scan aktifse otomatik yenile
if st.session_state.get('scan_active', False):
    st_autorefresh(interval=15000, key="datarefresh")

st.markdown("""
<style>
    .stApp { background-color: #0e0d12; color: #fff; }
    .css-1d391kg { background-color: #13121a; }
    h1, h2, h3, h4 { color: #fff !important; font-weight: 200; }
    .new-listing { background: rgba(0, 229, 192, 0.15); border: 1px solid #00e5c0; border-radius: 8px; padding: 10px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

engine = get_engine()
if engine:
    init_tables(engine)

if "scan_active" not in st.session_state:
    st.session_state.scan_active = False
if "stop_event" not in st.session_state:
    st.session_state.stop_event = None

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
    with col1:
        t_min_price = st.number_input("Min Fiyat", value=0, step=50000)
    with col2:
        t_max_price = st.number_input("Max Fiyat", value=999999999, step=50000)

    col3, col4 = st.columns(2)
    with col3:
        t_min_year = st.number_input("Min Yıl", value=1970, step=1)
    with col4:
        t_max_year = st.number_input("Max Yıl", value=2030, step=1)

    col5, col6 = st.columns(2)
    with col5:
        t_min_km = st.number_input("Min KM", value=0, step=10000)
    with col6:
        t_max_km = st.number_input("Max KM", value=1000000, step=10000)

    t_max_tramer = st.number_input("Kabul Edilen Max Tramer (TL)", value=999999999, step=5000)
    t_duration = st.number_input("Arama Kaç Saat Sürsün?", value=1.0, step=0.5)

    st.subheader("🎯 Arama Kriterleri")
    target_sites = st.multiselect(
        "Taranacak Siteler",
        ALL_SITES,
        default=ALL_SITES
    )

    st.markdown("### 🚘 Kabul Edilebilir Hasar/Boya")
    st.markdown(
        "<small style='color:#bbb;'>Aşağıdaki parçalarda boya/değişen çıkarsa kabul ediyorum "
        "(İşaretlenmeyenlerde çıkarsa araç reddedilir):</small>",
        unsafe_allow_html=True
    )

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        kaput = st.checkbox("Ön Kaput 🟥")

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
    with c8:
        bagaj = st.checkbox("Arka Bagaj 🟪")

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
        stop_event = threading.Event()
        st.session_state.stop_event = stop_event

        criteria = {
            "sites": target_sites,
            "brand": t_brand, "model": t_model,
            "min_price": t_min_price, "max_price": t_max_price,
            "min_year": t_min_year, "max_year": t_max_year,
            "min_km": t_min_km, "max_km": t_max_km,
            "max_tramer": t_max_tramer, "duration": t_duration,
            "allowed_parts": allowed_parts
        }
        t = threading.Thread(
            target=background_scan_thread,
            args=(engine, criteria, stop_event),
            daemon=True
        )
        add_script_run_ctx(t)
        t.start()
        st.rerun()

    if st.session_state.scan_active:
        st.success("Avcı Modu Aktif! Yeni araçlar eklendikçe sayfaya düşecek.")
        if st.button("🛑 Taramayı Durdur", use_container_width=True):
            st.session_state.scan_active = False
            # BUG FIX: Thread-safe durdurma — stop_event ile sinyal gönder
            if st.session_state.stop_event:
                st.session_state.stop_event.set()
            st.rerun()

    st.divider()
    if st.button("🗑️ Bulunan Tüm Sonuçları Sil (Veritabanını Temizle)"):
        clear_all(engine)
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
            badge_color = (
                "#ff4b4b" if row['source_site'] == "Otoplus"
                else ("#1e90ff" if row['source_site'] == "VavaCars" else "#ffa500")
            )
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

    show_cols = [
        "source_site", "brand", "model", "package_trim", "engine_power",
        "year", "km", "price", "tramer_fee", "painted_parts", "changed_parts",
        "link", "scraped_at"
    ]
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
