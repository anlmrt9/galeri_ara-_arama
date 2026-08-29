"""
app.py - OtoGaleriBot Streamlit Arayüzü (B2B Redesign)
======================================================
Sadece UI katmanı. İş mantığı scrapers.py, db.py, notifications.py'de.
B2B Stripe-style modern tasarımı uygular.
"""

import streamlit as st
import threading
import time
import uuid
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
    GÖREV 2: session_id UUID ile her tarama oturumu takip edilir.
    """
    session_id = str(uuid.uuid4())  # Benzersiz tarama oturumu ID'si
    logger.info(f"[Scan] Yeni tarama oturumu basladi: {session_id}")

    duration_hours = criteria['duration']
    end_time = datetime.now() + timedelta(hours=duration_hours)

    mark_all_as_seen(engine)

    while datetime.now() < end_time:
        if stop_event.is_set():
            logger.info("Tarama stop_event ile durduruldu.")
            break

        run_one_cycle(engine, criteria, session_id=session_id)
        stop_event.wait(timeout=SCRAPER_CYCLE_INTERVAL_SEC)

    logger.info("Tarama dongusu tamamlandi.")


# ==========================================================================
#  STREAMLIT CONFIG & CUSTOM B2B THEME
# ==========================================================================

st.set_page_config(page_title="OtoGaleri Avcı Botu | Sourcing Infrastructure", layout="wide", page_icon="🎯")

# Scan aktifse otomatik yenile
if st.session_state.get('scan_active', False):
    st_autorefresh(interval=15000, key="datarefresh")

# Inject Custom B2B Styling
st.markdown("""
<style>
    /* Global Styles */
    .stApp {
        background-color: #ffffff !important;
        color: #0d0c10 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Remove default streamlit header margin */
    .block-container {
        padding-top: 0rem !important;
        padding-left: 0rem !important;
        padding-right: 0rem !important;
        padding-bottom: 3rem !important;
    }
    
    /* Hero section styles with multi-stop pastel gradient band */
    .hero-container {
        background: linear-gradient(135deg, #a0c4ff 0%, #c8b6ff 30%, #bdf0e0 70%, #fffdd0 100%);
        padding: 5rem 10% 4rem 10%;
        border-bottom: 1px solid #eaeaea;
        color: #0d0c10;
        margin-bottom: 2rem;
    }
    
    .hero-headline {
        font-size: 62px;
        font-weight: 600;
        letter-spacing: -2px;
        line-height: 1.1;
        color: #0d0c10;
        margin-bottom: 1.5rem;
    }
    
    .hero-body {
        font-size: 18px;
        color: #687076;
        line-height: 1.5;
        margin-bottom: 2rem;
        max-width: 600px;
    }
    
    /* Feature cards styles */
    .feature-card {
        background-color: #ffffff;
        border-radius: 8px;
        padding: 1.5rem;
        border: 1px solid #e1e4e6;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        height: 100%;
    }
    
    .feature-icon-tile {
        width: 30px;
        height: 30px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .feature-title {
        font-size: 16px;
        margin: 0 0 8px 0;
        color: #0d0c10;
        font-weight: 600;
    }
    
    .feature-text {
        font-size: 13px;
        color: #687076;
        margin: 0;
        line-height: 1.4;
    }
    
    /* Logo Strip */
    .logo-strip {
        display: flex;
        justify-content: space-around;
        align-items: center;
        padding: 2rem 0;
        opacity: 0.4;
        border-top: 1px solid #eaeaea;
        border-bottom: 1px solid #eaeaea;
        margin: 3rem 10% 2rem 10%;
    }
    
    .logo-placeholder {
        height: 20px;
        background-color: #cbd5e1;
        border-radius: 4px;
    }
    
    /* Custom Streamlit component overrides */
    div.stButton > button {
        border-radius: 50px !important;
        padding: 0.5rem 2rem !important;
        font-weight: 600 !important;
        background-color: #ffffff !important;
        color: #0d0c10 !important;
        border: 1px solid #dcdfe3 !important;
        transition: all 0.2s ease;
    }
    
    div.stButton > button:hover {
        border-color: #0091ff !important;
        color: #0091ff !important;
    }
    
    /* Redefine Primary buttons */
    .primary-btn div.stButton > button {
        background-color: #0091ff !important;
        color: #ffffff !important;
        border: none !important;
    }
    
    .primary-btn div.stButton > button:hover {
        background-color: #0077d6 !important;
        color: #ffffff !important;
    }
    
    /* Custom Card container for parameters */
    .parameter-card {
        background-color: #ffffff;
        border: 1px solid #eaeaea;
        border-radius: 12px;
        padding: 2rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.02);
        margin: 0 10%;
    }
    
    .parameter-header {
        font-size: 20px;
        font-weight: 600;
        color: #0d0c10;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid #eaeaea;
        padding-bottom: 8px;
    }
    
    /* Hide default Streamlit sidebar */
    [data-testid="stSidebar"] {
        display: none;
    }
    
    .new-listing {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    
    .new-listing b {
        color: #0d0c10;
    }
    
    /* Normal headings styling */
    h3, h4 {
        color: #0d0c10 !important;
    }
</style>
""", unsafe_allow_html=True)

engine = get_engine()
if engine:
    init_tables(engine)

if "scan_active" not in st.session_state:
    st.session_state.scan_active = False
if "stop_event" not in st.session_state:
    st.session_state.stop_event = None

# ==========================================================================
#  HERO SECTION (HTML Banner with Gradient Background)
# ==========================================================================

# Code terminal values based on active state
if st.session_state.scan_active:
    status_comment = "Aktif Tarama Sürüyor... Arkanıza yaslanın, gerisini bize bırakın."
    status_color = "#00a35c"
else:
    status_comment = "Sistem Aramaya Hazır. Lütfen hedeflerinizi belirleyin."
    status_color = "#687076"

# We split the page layout dynamically inside the custom gradient band
st.markdown(f"""
<div class="hero-container" style="text-align: center; padding: 6rem 10% 5rem 10%;">
    <div style="max-width: 800px; margin: 0 auto;">
        <div class="hero-headline" style="font-size: 56px;">Akıllı Araç Tedarik Altyapısı.</div>
        <div class="hero-body" style="margin: 0 auto 2rem auto; font-size: 20px;">
            Sizin belirlediğiniz kriterlere göre piyasadaki en uygun araçları tespit eder. 
            Otoplus, VavaCars, Otokoç ve Arabam.com stoklarını saniyeler içinde tarar, 
            yeni bir araç eklendiği an dikkatinizi dağıtmadan size bildirir.
        </div>
        <div style="display: inline-block; padding: 8px 20px; background-color: rgba(255,255,255,0.7); border-radius: 50px; font-weight: 600; font-size: 15px; color: {status_color}; border: 1px solid rgba(0,0,0,0.05); box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
            <span style="margin-right: 8px;">🎯</span> {status_comment}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==========================================================================
#  FOUR FEATURE COLUMNS
# ==========================================================================

st.markdown("<div style='padding: 0 10% 2rem 10%;'>", unsafe_allow_html=True)
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #a0c4ff, #c8b6ff);">🔄</div>
        <div class="feature-title">Eşzamanlı Tarama</div>
        <div class="feature-text">Tüm platformları tek bir akışta birleştirerek anlık veri sağlar.</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #bdf0e0, #a0c4ff);">📈</div>
        <div class="feature-title">Hızlı Bildirim</div>
        <div class="feature-text">Kriterlerinize uyan bir araç ilana düştüğü an masaüstü bildirimi alırsınız.</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #c8b6ff, #fffdd0);">🛡️</div>
        <div class="feature-title">Hasar Koruması</div>
        <div class="feature-text">Gelişmiş NLP filtresi ile istemediğiniz boya veya değişenleri otomatik eler.</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #fffdd0, #bdf0e0);">🧠</div>
        <div class="feature-title">Psikolojik Rahatlık</div>
        <div class="feature-text">Siz işininize odaklanın, manuel ilan arama stresini bot devralsın.</div>
    </div>
    """, unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)


# ==========================================================================
#  LOGO STRIP OF NEUTRAL PLACEHOLDER BARS
# ==========================================================================

st.markdown("""
<div class="logo-strip">
    <div class="logo-placeholder" style="width: 110px;"></div>
    <div class="logo-placeholder" style="width: 90px;"></div>
    <div class="logo-placeholder" style="width: 130px;"></div>
    <div class="logo-placeholder" style="width: 85px;"></div>
    <div class="logo-placeholder" style="width: 100px;"></div>
</div>
""", unsafe_allow_html=True)


# ==========================================================================
#  PARAMETER CARD (THE PARAMETER FORM)
# ==========================================================================

st.markdown('<div class="parameter-card">', unsafe_allow_html=True)

# Form header
st.markdown('<div class="parameter-header">🎯 Hedef Araç Özellikleri</div>', unsafe_allow_html=True)

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

# Grid parameters
grid_col1, grid_col2 = st.columns(2)

with grid_col1:
    t_brand = st.selectbox("Marka Seçin", ["Tümü"] + sorted(list(CAR_CATALOG.keys())))
with grid_col2:
    if t_brand == "Tümü":
        t_model = st.selectbox("Model Seçin", ["Tümü"])
    else:
        t_model = st.selectbox("Model Seçin", ["Tümü"] + sorted(CAR_CATALOG[t_brand]))

p_col1, p_col2, p_col3 = st.columns(3)
with p_col1:
    t_min_price = st.number_input("Minimum Fiyat (TL)", value=None, placeholder="Örn: 500000", step=50000)
    t_max_price = st.number_input("Maksimum Fiyat (TL)", value=None, placeholder="Limit Yok", step=50000)
with p_col2:
    t_min_year = st.number_input("Minimum Yıl", value=None, placeholder="Örn: 2015", step=1)
    t_max_year = st.number_input("Maksimum Yıl", value=None, placeholder="Örn: 2024", step=1)
with p_col3:
    t_min_km = st.number_input("Minimum Kilometre (KM)", value=None, placeholder="Örn: 0", step=10000)
    t_max_km = st.number_input("Maksimum Kilometre (KM)", value=None, placeholder="Limit Yok (Örn: 120000)", step=10000)

p_col4, p_col5 = st.columns(2)
with p_col4:
    t_max_tramer = st.number_input("Maksimum Kabul Edilen Tramer (TL)", value=None, placeholder="Hasarsız (Örn: 15000)", step=5000)
with p_col5:
    t_duration = st.number_input("Tedarik Süreci Süresi (Saat)", value=24.0, step=1.0)

st.markdown("<br>", unsafe_allow_html=True)
target_sites = st.multiselect(
    "Hedef Kanallar / Siteler",
    ALL_SITES,
    default=ALL_SITES
)

# Allowed damages config
st.markdown("<br><b>🚘 İnteraktif Araç Hasar Haritası</b>", unsafe_allow_html=True)
st.markdown("<p style='font-size: 13px; color: #687076;'>Aşağıdaki şemada araç parçalarına tıklayarak izin verdiğiniz maksimum hasar durumunu seçin (Gri: Orijinal, Mavi: Boyalı, Kırmızı: Değişen).</p>", unsafe_allow_html=True)

import streamlit.components.v1 as components
car_map = components.declare_component("car_map", path="car_map_component")
car_state = car_map(key="car_map", default=None)

allowed_parts = []
if car_state:
    # Map component keys to scraper keys
    mapping = {
        "kaput": "kaput", "tavan": "tavan", "bagaj": "bagaj",
        "sol_on_cam": "sol ön çamurluk", "sag_on_cam": "sağ ön çamurluk",
        "sol_on_kapi": "sol ön kapı", "sag_on_kapi": "sağ ön kapı",
        "sol_arka_kapi": "sol arka kapı", "sag_arka_kapi": "sağ arka kapı",
        "sol_arka_cam": "sol arka çamurluk", "sag_arka_cam": "sağ arka çamurluk"
    }
    for js_key, val in car_state.items():
        if val in ["boyali", "degisen"]:
            if js_key in mapping:
                allowed_parts.append(mapping[js_key])

st.markdown("<br>", unsafe_allow_html=True)

# Sourcing Control Buttons
act_col1, act_col2 = st.columns(2)

with act_col1:
    # We place submit inside a custom class container for primary button style
    st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
    submit_btn = st.button("🚀 Tarama ve Tedarik Sürecini Başlat", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with act_col2:
    if st.session_state.scan_active:
        stop_btn = st.button("🛑 Tarama Oturumunu Sonlandır", use_container_width=True)
        if stop_btn:
            st.session_state.scan_active = False
            if st.session_state.stop_event:
                st.session_state.stop_event.set()
            st.rerun()
    else:
        st.button("🛑 Tarama Oturumunu Sonlandır (Devre Dışı)", use_container_width=True, disabled=True)

if submit_btn:
    st.session_state.scan_active = True
    stop_event = threading.Event()
    st.session_state.stop_event = stop_event

    criteria = {
        "sites": target_sites,
        "brand": t_brand, "model": t_model,
        "min_price": t_min_price if t_min_price is not None else 0,
        "max_price": t_max_price if t_max_price is not None else 999999999,
        "min_year": t_min_year if t_min_year is not None else 1970,
        "max_year": t_max_year if t_max_year is not None else 2030,
        "min_km": t_min_km if t_min_km is not None else 0,
        "max_km": t_max_km if t_max_km is not None else 1000000,
        "max_tramer": t_max_tramer if t_max_tramer is not None else 999999999,
        "duration": t_duration if t_duration is not None else 24.0,
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

st.markdown('</div>', unsafe_allow_html=True) # End parameter-card


# ==========================================================================
#  RESULTS SECTION
# ==========================================================================

st.markdown('<div style="margin: 3rem 10% 0 10%;">', unsafe_allow_html=True)

st.markdown('<h3>📊 Bulunan Araçlar</h3>', unsafe_allow_html=True)

df = load_data(engine)

if not df.empty:
    new_listings = df[df["is_new_listing"] == 1]
    if not new_listings.empty:
        st.markdown(f"#### 🚨 YENİ YAKALANAN ARAÇLAR ({len(new_listings)} ilan)")
        for idx, row in new_listings.iterrows():
            badge_color = (
                "#ff4b4b" if row['source_site'] == "Otoplus"
                else ("#1e90ff" if row['source_site'] == "VavaCars" else "#ffa500")
            )
            st.markdown(f"""
            <div class="new-listing">
                <span style="background:{badge_color}; color:#ffffff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold; margin-right:10px;">{row['source_site']}</span>
                <b>{row['brand']} {row['model']} {row['package_trim']}</b> ({row['year']} | {row['km']} km) -
                <span style="color:#00c0a0; font-size:18px;"><b>{row['price']:,} ₺</b></span>
                <br>
                <small style="color: #687076;">Boya: {row['painted_parts']} | Değişen: {row['changed_parts']} | Tramer: {row['tramer_fee']} ₺</small>
                <br>
                <a href="{row['link']}" target="_blank" style="color:#0091ff; font-size:12px; font-weight: 500;">İlana Git ↗</a>
            </div>
            """, unsafe_allow_html=True)
        st.divider()

    st.markdown(f"#### 📋 Tüm Kayıtlı Araçlar ({len(df)} toplam ilan)")

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
            "tramer_fee": st.column_config.NumberColumn("Tramer (TL)", format="%d ₺")
        }
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ Tüm Veritabanını Temizle (Bulunan Araçları Sil)"):
        clear_all(engine)
        st.success("Tüm araç verileri başarıyla silindi.")
        st.rerun()
else:
    st.info("Henüz sistemde eşleşen bir araç bulunamadı. Lütfen hedeflerinizi belirleyip taramayı başlatın.")

st.markdown('</div>', unsafe_allow_html=True)
