"""
app.py - OtoGaleriBot Streamlit Arayüzü (B2B Redesign)
======================================================
Sadece UI katmanı. İş mantığı scrapers.py, db.py, notifications.py'de.
B2B Stripe-style modern tasarımı uygular.
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
    """
    duration_hours = criteria['duration']
    end_time = datetime.now() + timedelta(hours=duration_hours)

    mark_all_as_seen(engine)

    while datetime.now() < end_time:
        if stop_event.is_set():
            logger.info("Tarama stop_event ile durduruldu.")
            break

        run_one_cycle(engine, criteria)
        stop_event.wait(timeout=SCRAPER_CYCLE_INTERVAL_SEC)

    logger.info("Tarama döngüsü tamamlandi.")


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
    
    /* Monospace Code Terminal styled on the right */
    .code-panel {
        background-color: #0d1117;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12);
        font-family: 'Fira Code', 'Courier New', monospace;
        color: #c9d1d9;
        font-size: 14px;
        border: 1px solid #21262d;
    }
    
    .code-tabs {
        display: flex;
        gap: 12px;
        margin-bottom: 12px;
        border-bottom: 1px solid #21262d;
        padding-bottom: 8px;
        font-size: 13px;
    }
    
    .code-tab-active {
        color: #58a6ff;
        font-weight: 600;
        border-bottom: 2px solid #58a6ff;
        padding-bottom: 8px;
    }
    
    .code-tab-inactive {
        color: #8b949e;
        padding-bottom: 8px;
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
    status_comment = "// Scan Status: SUCCESS - Active sourcing running..."
    status_color = "#7ee787"
else:
    status_comment = "// Scan Status: IDLE - Sourcing engine is ready."
    status_color = "#8b949e"

# We split the page layout dynamically inside the custom gradient band
st.markdown(f"""
<div class="hero-container">
    <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 3rem;">
        <div style="flex: 1; min-width: 320px;">
            <div class="hero-headline">OtoGaleri Sourcing Infrastructure.</div>
            <div class="hero-body">
                A high-speed automotive sourcing infrastructure matching customized criteria. 
                Monitors digital inventories across Otoplus, VavaCars, Otokoç, and Arabam automatically.
            </div>
        </div>
        <div style="flex: 1; min-width: 320px; max-width: 500px;">
            <div class="code-panel">
                <div class="code-tabs">
                    <span class="code-tab-active">config.yaml</span>
                    <span class="code-tab-inactive">api_response.json</span>
                </div>
                <div style="line-height: 1.6;">
                    <span style="color: #ff7b72;">engine</span>: <span style="color: #a5d6ff;">"OtoGaleriAvci"</span><br>
                    <span style="color: #ff7b72;">monitoring_channels</span>:<br>
                    &nbsp;&nbsp;- <span style="color: #a5d6ff;">"Otoplus"</span><br>
                    &nbsp;&nbsp;- <span style="color: #a5d6ff;">"VavaCars"</span><br>
                    &nbsp;&nbsp;- <span style="color: #a5d6ff;">"Otokoç 2. El"</span><br>
                    &nbsp;&nbsp;- <span style="color: #a5d6ff;">"Arabam.com"</span><br>
                    <span style="color: #ff7b72;">notification_alerts</span>: <span style="color: #79c0ff;">true</span><br>
                    <br>
                    <span style="color: {status_color}; font-weight: 500;">{status_comment}</span>
                </div>
            </div>
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
        <div class="feature-title">Unified Sourcing</div>
        <div class="feature-text">Aggregates multi-platform listings into a unified real-time stream.</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #bdf0e0, #a0c4ff);">📈</div>
        <div class="feature-title">Real-Time Routing</div>
        <div class="feature-text">Applies multi-threaded crawlers to route matching units directly.</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #c8b6ff, #fffdd0);">🛡️</div>
        <div class="feature-title">Damage Evaluation</div>
        <div class="feature-text">Advanced filters isolate and exclude specific structural repaint and repair details.</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon-tile" style="background: linear-gradient(135deg, #fffdd0, #bdf0e0);">🔔</div>
        <div class="feature-title">Instant Alerts</div>
        <div class="feature-text">Pushes immediate desktop toast notifications whenever matches are discovered.</div>
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
st.markdown('<div class="parameter-header">🎯 Target Specifications</div>', unsafe_allow_html=True)

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
    t_brand = st.selectbox("Brand Name", ["Tümü"] + sorted(list(CAR_CATALOG.keys())))
with grid_col2:
    if t_brand == "Tümü":
        t_model = st.selectbox("Model Name", ["Tümü"])
    else:
        t_model = st.selectbox("Model Name", ["Tümü"] + sorted(CAR_CATALOG[t_brand]))

p_col1, p_col2, p_col3 = st.columns(3)
with p_col1:
    t_min_price = st.number_input("Min Price (TRY)", value=0, step=50000)
    t_max_price = st.number_input("Max Price (TRY)", value=999999999, step=50000)
with p_col2:
    t_min_year = st.number_input("Min Year", value=1970, step=1)
    t_max_year = st.number_input("Max Year", value=2030, step=1)
with p_col3:
    t_min_km = st.number_input("Min Mileage (KM)", value=0, step=10000)
    t_max_km = st.number_input("Max Mileage (KM)", value=1000000, step=10000)

p_col4, p_col5 = st.columns(2)
with p_col4:
    t_max_tramer = st.number_input("Maximum Accepted Tramer (TRY)", value=999999999, step=5000)
with p_col5:
    t_duration = st.number_input("Sourcing Session Duration (Hours)", value=1.0, step=0.5)

st.markdown("<br>", unsafe_allow_html=True)
target_sites = st.multiselect(
    "Target Channels / Sites",
    ALL_SITES,
    default=ALL_SITES
)

# Allowed damages config
st.markdown("<br><b>🚘 Allowable Repairs (Boya/Değişen)</b>", unsafe_allow_html=True)
st.markdown("<p style='font-size: 13px; color: #687076;'>Select parts you are comfortable having repairs on. Unchecked areas with damage will reject the listing.</p>", unsafe_allow_html=True)

dmg_col1, dmg_col2, dmg_col3 = st.columns(3)

with dmg_col1:
    kaput = st.checkbox("Ön Kaput 🟥")
    sol_on_cam = st.checkbox("Sol Ön Çml.")
    sol_on_kapi = st.checkbox("Sol Ön Kapı")
    sol_arka_kapi = st.checkbox("Sol Arka Kapı")
    sol_arka_cam = st.checkbox("Sol Arka Çml.")

with dmg_col2:
    tavan = st.checkbox("Tavan 🟦")
    bagaj = st.checkbox("Arka Bagaj 🟪")

with dmg_col3:
    sag_on_cam = st.checkbox("Sağ Ön Çml.")
    sag_on_kapi = st.checkbox("Sağ Ön Kapı")
    sag_arka_kapi = st.checkbox("Sağ Arka Kapı")
    sag_arka_cam = st.checkbox("Sağ Arka Çml.")

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

# Sourcing Control Buttons
act_col1, act_col2 = st.columns(2)

with act_col1:
    # We place submit inside a custom class container for primary button style
    st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
    submit_btn = st.button("🚀 Start Sourcing Stream", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with act_col2:
    if st.session_state.scan_active:
        stop_btn = st.button("🛑 Terminate Sourcing Session", use_container_width=True)
        if stop_btn:
            st.session_state.scan_active = False
            if st.session_state.stop_event:
                st.session_state.stop_event.set()
            st.rerun()
    else:
        st.button("🛑 Terminate Sourcing Session (Disabled)", use_container_width=True, disabled=True)

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

st.markdown('</div>', unsafe_allow_html=True) # End parameter-card


# ==========================================================================
#  RESULTS SECTION
# ==========================================================================

st.markdown('<div style="margin: 3rem 10% 0 10%;">', unsafe_allow_html=True)

st.markdown('<h3>📊 Discovered Vehicles</h3>', unsafe_allow_html=True)

df = load_data(engine)

if not df.empty:
    new_listings = df[df["is_new_listing"] == 1]
    if not new_listings.empty:
        st.markdown(f"#### 🚨 NEW MATCHES ({len(new_listings)} items)")
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
                <a href="{row['link']}" target="_blank" style="color:#0091ff; font-size:12px; font-weight: 500;">Go to Listing ↗</a>
            </div>
            """, unsafe_allow_html=True)
        st.divider()

    st.markdown(f"#### 📋 Sourced Registry ({len(df)} total items)")

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
            "link": st.column_config.LinkColumn("Listing URL", display_text="Go to Listing"),
            "price": st.column_config.NumberColumn("Price (TRY)", format="%d ₺"),
            "tramer_fee": st.column_config.NumberColumn("Tramer (TRY)", format="%d ₺")
        }
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🗑️ Clear Database / Delete All Results"):
        clear_all(engine)
        st.success("All data successfully cleared.")
        st.rerun()
else:
    st.info("No matching vehicles have been discovered yet. Please define specifications above and start sourcing.")

st.markdown('</div>', unsafe_allow_html=True)
