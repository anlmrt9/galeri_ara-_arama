"""
app.py - OtoGaleriBot Streamlit Arayüzü (Neo-Fintech Redesign)
================================================================
Sadece UI katmanı. İş mantığı scrapers.py, db.py, notifications.py'de.
Monzo/Revolut tarzı koyu lacivert (neo-fintech) tasarımı uygular.
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


def format_try(value):
    """34.980.5 -> '34.980,50' bicimine (TR yerel ayari) cevirir."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0,00"
    formatted = f"{value:,.2f}"
    # 1,234,567.89 (US) -> 1.234.567,89 (TR)
    formatted = formatted.replace(",", "§").replace(".", ",").replace("§", ".")
    return formatted


# ==========================================================================
#  STREAMLIT CONFIG & NEO-FINTECH DARK THEME
# ==========================================================================

st.set_page_config(page_title="OtoGaleri Avcı Botu | Sourcing Infrastructure", layout="wide", page_icon="🎯")

# Scan aktifse otomatik yenile
if st.session_state.get('scan_active', False):
    st_autorefresh(interval=15000, key="datarefresh")

if "display_id" not in st.session_state:
    st.session_state.display_id = str(uuid.uuid4())[:4].upper()

# ==========================================================================
#  PWA: manifest + service worker (telefonda "Ana Ekrana Ekle" desteği)
# ==========================================================================
import streamlit.components.v1 as pwa_components
pwa_components.html("""
<script>
(function() {
    const doc = window.parent.document;
    const win = window.parent;

    function addMeta(name, content) {
        if (doc.querySelector(`meta[name="${name}"]`)) return;
        const m = doc.createElement('meta');
        m.name = name;
        m.content = content;
        doc.head.appendChild(m);
    }

    if (!doc.getElementById('pwa-manifest')) {
        const manifest = doc.createElement('link');
        manifest.id = 'pwa-manifest';
        manifest.rel = 'manifest';
        manifest.href = 'app/static/manifest.json';
        doc.head.appendChild(manifest);

        const appleTouchIcon = doc.createElement('link');
        appleTouchIcon.rel = 'apple-touch-icon';
        appleTouchIcon.href = 'app/static/icon-192.png';
        doc.head.appendChild(appleTouchIcon);

        addMeta('theme-color', '#0f1225');
        addMeta('mobile-web-app-capable', 'yes');
        addMeta('apple-mobile-web-app-capable', 'yes');
        addMeta('apple-mobile-web-app-status-bar-style', 'black-translucent');
        addMeta('apple-mobile-web-app-title', 'OtoGaleri');
        addMeta('format-detection', 'telephone=no');

        const viewport = doc.querySelector('meta[name="viewport"]');
        if (viewport && viewport.content.indexOf('viewport-fit') === -1) {
            viewport.content = viewport.content + ', viewport-fit=cover';
        }
    }

    if ('serviceWorker' in win.navigator) {
        win.navigator.serviceWorker.register('app/static/sw.js', { scope: '/' }).catch(function() {
            win.navigator.serviceWorker.register('app/static/sw.js').catch(function() {});
        });
    }

    // ---- "Uygulamayı Yükle" yüzen buton (Android/Chrome: beforeinstallprompt) ----
    if (!doc.getElementById('pwa-install-btn')) {
        const btn = doc.createElement('button');
        btn.id = 'pwa-install-btn';
        btn.type = 'button';
        btn.textContent = '📲 Uygulamayı Yükle';
        btn.style.cssText = `
            position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%) translateY(80px);
            z-index: 999999; display: flex; align-items: center; gap: 8px;
            padding: 12px 22px; border: none; border-radius: 50px;
            background: linear-gradient(135deg, #6a3df5 0%, #b84ffb 100%);
            color: #ffffff; font-family: 'Inter', -apple-system, sans-serif;
            font-size: 14px; font-weight: 600; cursor: pointer;
            box-shadow: 0 12px 28px rgba(106, 61, 245, 0.5);
            opacity: 0; pointer-events: none; transition: opacity 0.25s ease, transform 0.25s ease;
            padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
        `;
        doc.body.appendChild(btn);

        let deferredPrompt = null;
        win.addEventListener('beforeinstallprompt', function(e) {
            e.preventDefault();
            deferredPrompt = e;
            btn.style.opacity = '1';
            btn.style.pointerEvents = 'auto';
            btn.style.transform = 'translateX(-50%) translateY(0)';
        });

        btn.addEventListener('click', function() {
            if (!deferredPrompt) return;
            btn.style.opacity = '0';
            btn.style.pointerEvents = 'none';
            deferredPrompt.prompt();
            deferredPrompt.finally && deferredPrompt.finally(function() { deferredPrompt = null; });
            deferredPrompt = null;
        });

        win.addEventListener('appinstalled', function() {
            btn.style.opacity = '0';
            btn.style.pointerEvents = 'none';
        });
    }

    // ---- iOS Safari: manuel "Ana Ekrana Ekle" ipucu (bir kere gösterilir) ----
    const isIOS = /iphone|ipad|ipod/i.test(win.navigator.userAgent);
    const isStandalone = win.navigator.standalone === true ||
        win.matchMedia('(display-mode: standalone)').matches;
    if (isIOS && !isStandalone && !doc.getElementById('pwa-ios-hint')) {
        let dismissed = false;
        try { dismissed = win.localStorage.getItem('otogaleri_ios_hint_dismissed') === '1'; } catch (e) {}
        if (!dismissed) {
            const hint = doc.createElement('div');
            hint.id = 'pwa-ios-hint';
            hint.style.cssText = `
                position: fixed; left: 16px; right: 16px; bottom: 16px; z-index: 999999;
                background: #191d33; color: #ffffff; border: 1px solid rgba(255,255,255,0.1);
                border-radius: 14px; padding: 12px 16px; font-family: 'Inter', -apple-system, sans-serif;
                font-size: 13px; line-height: 1.4; display: flex; align-items: center; gap: 10px;
                box-shadow: 0 12px 28px rgba(0,0,0,0.4);
                padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
            `;
            hint.innerHTML = `
                <span style="flex:1;">📲 Uygulama olarak kullanmak için paylaş (⬆️) simgesine, ardından
                <b>"Ana Ekrana Ekle"</b> seçeneğine dokunun.</span>
                <button id="pwa-ios-hint-close" style="background:none;border:none;color:#8a8fb8;font-size:18px;cursor:pointer;padding:0 4px;">✕</button>
            `;
            doc.body.appendChild(hint);
            doc.getElementById('pwa-ios-hint-close').addEventListener('click', function() {
                hint.remove();
                try { win.localStorage.setItem('otogaleri_ios_hint_dismissed', '1'); } catch (e) {}
            });
        }
    }
})();
</script>
""", height=0, width=0)

# Inject Custom Neo-Fintech Styling
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    :root {
        --navy: #0f1225;
        --surface: #191d33;
        --surface-hover: #22274a;
        --violet: #6a3df5;
        --pink: #b84ffb;
        --green: #2ecc71;
        --muted: #8a8fb8;
    }

    /* Global Styles */
    html, body, .stApp {
        background-color: var(--navy) !important;
        color: #ffffff !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .tnum {
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum" 1;
        font-weight: 700;
    }

    /* Remove default streamlit header margin */
    .block-container {
        padding-top: 1.5rem !important;
        padding-left: 0rem !important;
        padding-right: 0rem !important;
        padding-bottom: 3rem !important;
        max-width: 1100px;
    }

    [data-testid="stHeader"] { background-color: var(--navy) !important; }
    [data-testid="stSidebar"] { display: none; }

    /* ---------- TOP BAR ---------- */
    .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 10% 1.5rem 10%;
    }
    .greeting-hello { font-size: 13px; font-weight: 400; color: var(--muted); display: block; }
    .greeting-name { font-size: 20px; font-weight: 600; color: #ffffff; }
    .topbar-right { display: flex; align-items: center; gap: 16px; }
    .sparkline { display: flex; align-items: flex-end; gap: 3px; height: 26px; }
    .sparkline span {
        display: block; width: 4px; height: var(--h); border-radius: 2px;
        background: linear-gradient(180deg, var(--pink) 0%, var(--violet) 100%);
        opacity: 0.9;
    }
    .bell-wrap { position: relative; width: 38px; height: 38px; border-radius: 50%;
        background: var(--surface); display: flex; align-items: center; justify-content: center; }
    .notif-dot { position: absolute; top: 7px; right: 8px; width: 8px; height: 8px;
        border-radius: 50%; background: #ff4d6a; box-shadow: 0 0 0 2px var(--surface); }

    /* ---------- BALANCE ---------- */
    .balance-block { text-align: center; margin-bottom: 1.75rem; }
    .balance-label { font-size: 13px; font-weight: 500; color: var(--muted); margin-bottom: 6px; }
    .balance-amount { font-size: 34px; font-weight: 700; letter-spacing: -0.5px; }

    /* ---------- HERO CARD ---------- */
    .hero-card-wrap { display: flex; justify-content: center; margin-bottom: 2rem; }
    .hero-card {
        width: 200px; height: 126px; border-radius: 14px; padding: 16px;
        background: linear-gradient(135deg, var(--violet) 0%, var(--pink) 100%);
        box-shadow: 0 18px 34px rgba(106, 61, 245, 0.45);
        transform: rotate(-6deg);
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .hero-card-top { display: flex; align-items: flex-start; justify-content: space-between; }
    .chip { width: 26px; height: 20px; border-radius: 4px; background: linear-gradient(135deg, #ffe9a8, #d8b45c); }
    .hero-card-brand { font-size: 14px; font-weight: 700; letter-spacing: 1.5px; color: #ffffff; }
    .hero-card-number { font-size: 15px; font-weight: 600; letter-spacing: 1.5px; color: rgba(255,255,255,0.95); }

    /* ---------- QUICK ACTIONS ---------- */
    .qa-label {
        text-align: center; font-size: 12.5px; font-weight: 500; color: #c7cae3;
        margin-top: 6px; display: block;
    }
    div[data-testid="stColumn"] .qa-btn button {
        width: 52px !important; height: 52px !important; border-radius: 50% !important;
        background: var(--surface) !important; border: none !important;
        font-size: 19px !important; display: flex !important; align-items: center; justify-content: center;
        margin: 0 auto !important; padding: 0 !important;
    }
    div[data-testid="stColumn"] .qa-btn button:hover { background: var(--surface-hover) !important; }
    div[data-testid="stColumn"] .qa-btn button:disabled { opacity: 0.35 !important; }
    .qa-anchor {
        width: 52px; height: 52px; border-radius: 50%; background: var(--surface);
        display: flex; align-items: center; justify-content: center; font-size: 19px;
        margin: 0 auto; text-decoration: none;
    }
    .qa-anchor:hover { background: var(--surface-hover); }

    /* ---------- TODAY / SON BULUNANLAR LIST ---------- */
    .today-title { font-size: 17px; font-weight: 600; margin: 0.5rem 0 1rem 0; color: #ffffff; }
    .tx-row { display: flex; align-items: center; gap: 12px; padding: 11px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
    .tx-emoji { width: 40px; height: 40px; min-width: 40px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center; font-size: 18px; }
    .tx-info { display: flex; flex-direction: column; flex: 1; line-height: 1.35; min-width: 0; }
    .tx-name { font-size: 14.5px; font-weight: 500; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .tx-time { font-size: 12.5px; font-weight: 400; color: var(--muted); }
    .tx-amount { font-size: 15px; font-weight: 700; color: #ffffff; white-space: nowrap; }
    .tx-amount.income { color: var(--green); }
    .tx-row.upcoming { opacity: 0.45; }

    /* ---------- BUTTONS ---------- */
    div.stButton > button {
        border-radius: 50px !important;
        padding: 0.6rem 1.6rem !important;
        font-weight: 600 !important;
        background-color: var(--surface) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover { border-color: var(--pink) !important; color: var(--pink) !important; }

    .primary-btn div.stButton > button {
        background: linear-gradient(135deg, var(--violet) 0%, var(--pink) 100%) !important;
        color: #ffffff !important; border: none !important;
    }
    .primary-btn div.stButton > button:hover { filter: brightness(1.08); }

    /* ---------- PARAMETER CARD ---------- */
    .parameter-card {
        background-color: var(--surface);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 16px;
        padding: 2rem;
        margin: 0 10%;
    }
    .parameter-header { font-size: 18px; font-weight: 600; color: #ffffff; margin-bottom: 1.5rem;
        border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 10px; }

    /* Streamlit input widgets -> dark surfaces */
    .stTextInput input, .stNumberInput input, div[data-baseweb="select"] > div, .stMultiSelect div[data-baseweb="select"] > div {
        background-color: var(--navy) !important;
        color: #ffffff !important;
        border-color: rgba(255,255,255,0.1) !important;
    }
    label, .stMarkdown p { color: #c7cae3 !important; }
    h1, h2, h3, h4 { color: #ffffff !important; }

    .new-listing {
        background: var(--navy);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .new-listing b { color: #ffffff; }

    /* ---------- FİLTRE PANELİ (st.expander) ---------- */
    div[data-testid="stExpander"] {
        background-color: var(--navy) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 12px !important;
        margin-bottom: 1.5rem;
    }
    div[data-testid="stExpander"] summary {
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 14.5px !important;
        padding: 0.9rem 1rem !important;
    }
    div[data-testid="stExpander"] summary:hover { color: var(--pink) !important; }
    div[data-testid="stExpander"] svg { fill: var(--muted) !important; }
    div[data-testid="stExpanderDetails"] { padding: 0.25rem 1rem 1rem 1rem !important; }

    /* ---------- QUICK ACTIONS: dar ekranlarda da yatay kalsın ---------- */
    .st-key-quick_actions div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 8px !important;
    }
    .st-key-quick_actions div[data-testid="stColumn"] {
        min-width: 0 !important;
        width: auto !important;
        flex: 1 1 0 !important;
    }

    /* ---------- Genel mobil ayarları ---------- */
    @media (max-width: 480px) {
        .topbar { padding: 0 6% 1.5rem 6%; }
        .parameter-card { margin: 0 6%; padding: 1.5rem 1.25rem; }
        div[style*="padding: 0 10%"] { padding: 0 6% !important; }
        .balance-amount { font-size: 28px; }
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

df = load_data(engine)
new_listings_df = df[df["is_new_listing"] == 1] if not df.empty else df
total_value = df["price"].sum() if not df.empty else 0

# ==========================================================================
#  TOP BAR: GREETING + NOTIFICATION DOT + SPARKLINE
# ==========================================================================

hour = datetime.now().hour
greeting_word = "Günaydın" if hour < 12 else ("İyi günler" if hour < 18 else "İyi akşamlar")

if not df.empty:
    site_counts = df["source_site"].value_counts()
    bar_heights = [min(100, max(20, int(v / site_counts.max() * 100))) for v in site_counts.tolist()[:7]]
else:
    bar_heights = [30, 45, 35, 60, 40, 70, 55]
sparkline_html = "".join(f'<span style="--h:{h}%"></span>' for h in bar_heights)

notif_dot_html = '<span class="notif-dot"></span>' if len(new_listings_df) > 0 else ""

st.markdown(f"""
<div class="topbar">
    <div>
        <span class="greeting-hello">{greeting_word}</span>
        <span class="greeting-name">Avcı Botu 🎯</span>
    </div>
    <div class="topbar-right">
        <div class="sparkline">{sparkline_html}</div>
        <div class="bell-wrap">🔔{notif_dot_html}</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==========================================================================
#  BALANCE: TOPLAM TESPİT EDİLEN DEĞER
# ==========================================================================

st.markdown(f"""
<div class="balance-block">
    <p class="balance-label">Toplam Tespit Edilen Değer</p>
    <h1 class="balance-amount tnum">₺{format_try(total_value)}</h1>
</div>
""", unsafe_allow_html=True)


# ==========================================================================
#  HERO CARD (TILTED BRAND CARD)
# ==========================================================================

st.markdown(f"""
<div class="hero-card-wrap">
    <div class="hero-card">
        <div class="hero-card-top">
            <div class="chip"></div>
            <span class="hero-card-brand">OTOGALERİ</span>
        </div>
        <div class="hero-card-number tnum">•••• {st.session_state.display_id}</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==========================================================================
#  QUICK ACTIONS: BAŞLAT / DURDUR / TEMİZLE / YENİLE
# ==========================================================================

with st.container(key="quick_actions"):
    qa1, qa2, qa3, qa4 = st.columns(4)

    with qa1:
        st.markdown('<a class="qa-anchor" href="#hedef-arac-ozellikleri">▶️</a><span class="qa-label">Başlat</span>', unsafe_allow_html=True)

    with qa2:
        st.markdown('<div class="qa-btn">', unsafe_allow_html=True)
        stop_clicked = st.button("⏹", key="qa_stop", disabled=not st.session_state.scan_active)
        st.markdown('</div><span class="qa-label">Durdur</span>', unsafe_allow_html=True)
        if stop_clicked:
            st.session_state.scan_active = False
            if st.session_state.stop_event:
                st.session_state.stop_event.set()
            st.rerun()

    with qa3:
        st.markdown('<div class="qa-btn">', unsafe_allow_html=True)
        clear_clicked = st.button("🧹", key="qa_clear", disabled=df.empty)
        st.markdown('</div><span class="qa-label">Temizle</span>', unsafe_allow_html=True)
        if clear_clicked:
            clear_all(engine)
            st.rerun()

    with qa4:
        st.markdown('<div class="qa-btn">', unsafe_allow_html=True)
        refresh_clicked = st.button("🔄", key="qa_refresh")
        st.markdown('</div><span class="qa-label">Yenile</span>', unsafe_allow_html=True)
        if refresh_clicked:
            st.rerun()

st.markdown("<div style='height: 2.5rem;'></div>", unsafe_allow_html=True)


# ==========================================================================
#  "SON BULUNANLAR" LİSTESİ
# ==========================================================================

st.markdown('<div style="padding: 0 10%;">', unsafe_allow_html=True)
st.markdown('<p class="today-title">Son Bulunanlar</p>', unsafe_allow_html=True)

SITE_EMOJI = {
    "Otoplus": "🚗", "VavaCars": "🚙", "Otokoç 2. El": "🚘",
    "Arabam.com": "🏎️", "Sahibinden": "🚓",
}
SITE_EMOJI_BG = {
    "Otoplus": "#2a2140", "VavaCars": "#132a2a", "Otokoç 2. El": "#3a2418",
    "Arabam.com": "#173021", "Sahibinden": "#242742",
}

if not df.empty:
    recent = df.sort_values("scraped_at", ascending=False).head(6)
    for _, row in recent.iterrows():
        emoji = SITE_EMOJI.get(row["source_site"], "🚘")
        bg = SITE_EMOJI_BG.get(row["source_site"], "#242742")
        is_new = row.get("is_new_listing", 0) == 1
        amount_class = "tx-amount income tnum" if is_new else "tx-amount tnum"
        sign = "+" if is_new else "-"
        try:
            time_str = row["scraped_at"].strftime("%H:%M") if row["scraped_at"] else "--:--"
        except Exception:
            time_str = "--:--"
        st.markdown(f"""
        <div class="tx-row">
            <span class="tx-emoji" style="background:{bg}">{emoji}</span>
            <div class="tx-info">
                <span class="tx-name">{row['brand']} {row['model']}</span>
                <span class="tx-time">{row['source_site']} · {time_str}</span>
            </div>
            <span class="{amount_class}">{sign}₺{format_try(row['price'])}</span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="tx-row" style="border-bottom:none;">
        <div class="tx-info">
            <span class="tx-name">Henüz araç bulunamadı</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

if st.session_state.scan_active:
    upcoming_text = f"Sıradaki tarama ~{SCRAPER_CYCLE_INTERVAL_SEC} saniye içinde"
else:
    upcoming_text = "Tarama başlatıldığında burada görünecek"

st.markdown(f"""
<div class="tx-row upcoming">
    <span class="tx-emoji" style="background:#242742">⏱️</span>
    <div class="tx-info">
        <span class="tx-name">Sıradaki Tarama</span>
        <span class="tx-time">{upcoming_text}</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<div style='height: 2.5rem;'></div>", unsafe_allow_html=True)


# ==========================================================================
#  PARAMETER CARD (THE PARAMETER FORM)
# ==========================================================================

st.markdown('<div id="hedef-arac-ozellikleri"></div>', unsafe_allow_html=True)
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

with st.expander("🎚️ Fiyat / Yıl / Kilometre / Tramer Filtreleri", expanded=False):
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
st.markdown("<p style='font-size: 13px; color: var(--muted);'>Aşağıdaki şemada araç parçalarına tıklayarak izin verdiğiniz maksimum hasar durumunu seçin (Gri: Orijinal, Mavi: Boyalı, Kırmızı: Değişen).</p>", unsafe_allow_html=True)

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

if not df.empty:
    if not new_listings_df.empty:
        st.markdown(f"#### 🚨 YENİ YAKALANAN ARAÇLAR ({len(new_listings_df)} ilan)")
        for idx, row in new_listings_df.iterrows():
            badge_color = (
                "#ff4b4b" if row['source_site'] == "Otoplus"
                else ("#1e90ff" if row['source_site'] == "VavaCars" else "#ffa500")
            )
            st.markdown(f"""
            <div class="new-listing">
                <span style="background:{badge_color}; color:#ffffff; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:bold; margin-right:10px;">{row['source_site']}</span>
                <b>{row['brand']} {row['model']} {row['package_trim']}</b> ({row['year']} | {row['km']} km) -
                <span class="tnum" style="color: var(--green); font-size:18px;">₺{format_try(row['price'])}</span>
                <br>
                <small style="color: var(--muted);">Boya: {row['painted_parts']} | Değişen: {row['changed_parts']} | Tramer: {row['tramer_fee']} ₺</small>
                <br>
                <a href="{row['link']}" target="_blank" style="color:var(--pink); font-size:12px; font-weight: 500;">İlana Git ↗</a>
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
