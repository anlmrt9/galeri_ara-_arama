"""Streamlit arayüzü — ``streamlit run app.py``

Yalnızca görünüm katmanıdır: tarama işleri ``ScanManager`` üzerinden veritabanına
yazılır ve worker tarafından yürütülür. Sayfa yenilense ya da birden fazla sekme
açılsa da tek bir tarama vardır ve her zaman durdurulabilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pydantic import ValidationError

from otogaleri import __version__
from otogaleri.config import (
    ALL_SITES,
    ANY,
    CAR_CATALOG,
    SITES,
    available_sites,
    get_settings,
    site_ready,
)
from otogaleri.db import Repository, create_db_engine, init_db
from otogaleri.formatting import format_number, format_price, humanize_delta, to_local
from otogaleri.logging_setup import configure_logging
from otogaleri.scan import ScanCriteria
from otogaleri.scoring import annotate
from otogaleri.ui.pwa import inject_pwa
from otogaleri.ui.render import CSS, listing_card, site_chip
from otogaleri.worker import ScanAlreadyRunningError, ScanManager

st.set_page_config(page_title="OtoGaleri Avcı Botu", page_icon="🎯", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
inject_pwa()


# ==========================================================================
#  ÇALIŞMA ZAMANI (süreç başına tek örnek — tüm oturumlar paylaşır)
# ==========================================================================


@st.cache_resource(show_spinner="Veritabanına bağlanılıyor...")
def runtime() -> tuple[Repository, ScanManager]:
    settings = get_settings()
    configure_logging(settings)
    engine = create_db_engine(settings)
    init_db(engine)
    repo = Repository(engine)
    manager = ScanManager(repo, settings)
    if settings.embedded_worker:
        manager.ensure_worker()
    return repo, manager


try:
    repo, manager = runtime()
except Exception as exc:  # noqa: BLE001 - kullanıcıya anlaşılır hata göster
    st.error(
        "Veritabanına bağlanılamadı. `.env` dosyasındaki `DATABASE_URL` / "
        "`OTOGALERI_DB_SERVER` ayarlarını kontrol edin (hiçbiri yoksa yerel SQLite kullanılır)."
    )
    st.exception(exc)
    st.stop()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.rstrip("Z"))


DURATIONS: dict[str, float | None] = {
    "1 saat": 1,
    "6 saat": 6,
    "12 saat": 12,
    "1 gün": 24,
    "3 gün": 72,
    "1 hafta": 168,
    "Ben durdurana kadar": None,
}
INTERVALS: dict[str, int] = {"5 dk": 5, "10 dk": 10, "15 dk": 15, "30 dk": 30, "1 saat": 60}


def _remaining(status: dict[str, Any]) -> str:
    """Aktif tarama için "5 sa 12 dk" / "Süresiz" metni."""
    if status.get("indefinite"):
        return "Süresiz"
    ends = _parse_iso(status.get("ends_at"))
    if ends is None:
        return "-"
    left = int((ends - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
    if left <= 0:
        return "Bitiyor"
    days, rem = divmod(left, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days} gün {hours} sa"
    if hours:
        return f"{hours} sa {minutes} dk"
    return f"{max(minutes, 1)} dk"


def _fmt_local(value: datetime | None) -> str:
    local = to_local(value)
    return local.strftime("%d.%m %H:%M") if local else "-"


# ==========================================================================
#  ÜST BANT: durum + kanal sağlığı (10 sn'de bir kendini yeniler)
# ==========================================================================

st.title("🎯 OtoGaleri Avcı Botu")
st.caption(
    "Kriterlerinize uyan ikinci el araç ilanlarını Otoplus, Otokoç, Arabam.com, VavaCars ve "
    "Sahibinden'de "
    "periyodik olarak tarar; yeni ilan ve fiyat düşüşlerini bildirir."
)


@st.fragment(run_every=10)
def status_band() -> None:
    status = manager.status()
    active = status.get("active")
    state = status.get("status")
    cycles = int(status.get("cycles") or 0)
    found_total = int(status.get("found_total") or 0)
    last_new = int(status.get("last_cycle_new") or 0)
    c1, c2, c3, c4, c5 = st.columns(5)
    if active:
        label = {"pending": "⏳ Başlatılıyor", "stop_requested": "⏸ Durduruluyor"}.get(
            str(state), "🟢 Tarama aktif"
        )
        c1.metric("Durum", label)
        nxt = _parse_iso(status.get("next_cycle_at"))
        c3.metric(
            "Tamamlanan tur",
            cycles,
            help=f"Sonraki tur: {humanize_delta(nxt) if nxt else 'şu an sürüyor'}",
        )
        c4.metric(
            "Bu taramada bulunan",
            format_number(found_total),
            delta=f"+{last_new} son turda" if cycles else None,
            delta_color="normal" if last_new else "off",
            help="Tarama başladığından beri kriterlere uyan yeni araç sayısı",
        )
        c5.metric("Kalan süre", _remaining(status))
        if not status.get("worker_alive") and state != "pending":
            st.warning(
                "Worker'dan kalp atışı alınamıyor. `python -m otogaleri.worker` çalışıyor mu?"
            )
    else:
        c1.metric("Durum", "⚪ Beklemede")
        c3.metric(
            "Son tarama",
            {"completed": "Tamamlandı", "stopped": "Durduruldu", "failed": "Hata"}.get(
                str(state), "-"
            ),
        )
        c4.metric(
            "O taramada bulunan",
            format_number(found_total) if status.get("session_id") else "-",
            help=f"{cycles} turda toplam",
        )
        c5.metric("Bitiş", _fmt_local(_parse_iso(status.get("finished_at"))))
    total, new = repo.count_listings(), repo.count_listings(only_new=True)
    c2.metric("Kayıtlı ilan", format_number(total), delta=f"{new} yeni" if new else None)

    if cycles:
        st.caption(
            f"🔁 **{cycles}. tur** tamamlandı "
            f"({_fmt_local(_parse_iso(status.get('last_cycle_at')))}): "
            f"{format_number(status.get('last_cycle_seen'))} ilan tarandı, "
            f"{format_number(status.get('last_cycle_matched'))} kriterlere uydu, "
            f"**{last_new} yeni araç** bulundu · bu taramada toplam **{found_total}** araç."
        )
        # yeni tur bittiğinde bir kez bildirim balonu göster
        key = f"{status.get('session_id')}:{cycles}"
        if active and st.session_state.get("_last_cycle_seen_key") not in (None, key):
            st.toast(
                f"{cycles}. tur bitti: {last_new} yeni araç (toplam {found_total}).",
                icon="🚗" if last_new else "🔁",
            )
        st.session_state["_last_cycle_seen_key"] = key

    runs = repo.latest_site_runs()
    chips = "".join(
        site_chip(
            s,
            runs.get(s),
            humanize_delta(runs[s]["finished_at"]) if s in runs else "",
            ready=site_ready(s),
        )
        for s in ALL_SITES
    )
    st.markdown(chips, unsafe_allow_html=True)


status_band()

tab_scan, tab_list, tab_market = st.tabs(["🔎 Tarama", "🚗 İlanlar", "📈 Piyasa"])


# ==========================================================================
#  TARAMA SEKMESİ
# ==========================================================================

car_map = components.declare_component("car_map", path="car_map_component")

with tab_scan:
    current = manager.status()
    if current.get("active"):
        crit = current.get("criteria") or {}
        interval = crit.get("cycle_interval_min") or get_settings().cycle_interval_sec // 60
        until = (
            "siz durdurana kadar"
            if current.get("indefinite")
            else f"{_fmt_local(_parse_iso(current.get('ends_at')))} tarihine kadar"
        )
        model_txt = crit.get("model", "") if crit.get("model") != ANY else ""
        st.info(
            f"**Aktif tarama:** {crit.get('brand', ANY)} {model_txt} · "
            f"{', '.join(crit.get('sites', []))}  \n"
            f"Her **{interval} dk**'da bir, **{until}** taranıyor (kalan: {_remaining(current)})."
        )
        if st.button("⏹ Taramayı durdur", type="primary"):
            manager.stop()
            st.toast("Durdurma isteği gönderildi.")
            st.rerun()
    else:
        st.subheader("Hedef araç")
        c1, c2 = st.columns(2)
        brand = c1.selectbox("Marka", [ANY, *sorted(CAR_CATALOG)])
        model = c2.selectbox(
            "Model", [ANY, *sorted(CAR_CATALOG.get(brand, []))], disabled=brand == ANY
        )

        c1, c2, c3 = st.columns(3)
        min_price = c1.number_input(
            "En düşük fiyat (₺)", min_value=0, value=None, step=50_000, placeholder="Sınır yok"
        )
        max_price = c1.number_input(
            "En yüksek fiyat (₺)", min_value=0, value=None, step=50_000, placeholder="Sınır yok"
        )
        this_year = datetime.now(timezone.utc).year
        min_year = c2.number_input(
            "En eski model yılı", 1970, this_year + 1, value=None, placeholder="Sınır yok"
        )
        max_year = c2.number_input(
            "En yeni model yılı", 1970, this_year + 1, value=None, placeholder="Sınır yok"
        )
        min_km = c3.number_input(
            "En düşük km", min_value=0, value=None, step=10_000, placeholder="Sınır yok"
        )
        max_km = c3.number_input(
            "En yüksek km", min_value=0, value=None, step=10_000, placeholder="Sınır yok"
        )

        max_tramer = st.number_input(
            "Kabul edilen en yüksek tramer (₺)",
            min_value=0,
            value=None,
            step=5_000,
            placeholder="Sınır yok",
            help="Tramer bilgisini yalnızca Arabam.com ve VavaCars veriyor.",
        )

        site_help = " · ".join(f"**{s.name}**: {s.note}" for s in SITES if s.note)
        ready_sites = available_sites()
        sites = st.multiselect(
            "Taranacak siteler", ready_sites, default=ready_sites, help=site_help
        )

        st.subheader("Hasar toleransı")
        st.caption(
            "Varsayılan: tüm parçalar orijinal olmalı. İzin verdiğiniz parçaları işaretleyin. "
            "Çizik/ezik gibi kozmetik kusurlar eleme sebebi değildir."
        )
        damage_state: dict[str, str] = (
            car_map(key="car_map", initial=st.session_state.get("car_map_last"), default={}) or {}
        )
        st.session_state["car_map_last"] = damage_state
        include_unknown = st.checkbox(
            "Hasar bilgisi okunamayan ilanları da göster",
            value=True,
            help="Bazı ilanlarda (ör. VavaCars'ta rozetsiz araçlar) parça bazlı ekspertiz verisi yok.",
        )

        st.subheader("Tarama planı")
        c1, c2 = st.columns(2)
        duration_label = (
            c1.segmented_control(
                "Ne kadar sürsün?", list(DURATIONS), default="1 gün", key="duration_choice"
            )
            or "1 gün"
        )
        interval_label = (
            c2.segmented_control(
                "Ne sıklıkla taransın?",
                list(INTERVALS),
                default="5 dk",
                key="interval_choice",
                help="Sık tarama yeni ilanı daha erken yakalar ama sitelere daha çok istek atar.",
            )
            or "5 dk"
        )
        duration_hours = DURATIONS[duration_label]
        interval_min = INTERVALS[interval_label]
        if duration_hours is None:
            st.caption(f"⏱️ Siz **durdurana kadar** her {interval_min} dakikada bir taranır.")
        else:
            ends = datetime.now() + timedelta(hours=duration_hours)
            rounds = max(1, int(duration_hours * 60 // interval_min))
            st.caption(
                f"⏱️ **{ends:%d.%m %H:%M}**'e kadar her {interval_min} dakikada bir taranır "
                f"(yaklaşık {rounds} tur)."
            )

        if st.button("🚀 Taramayı başlat", type="primary", disabled=not sites):
            try:
                criteria = ScanCriteria(
                    sites=sites,
                    brand=brand,
                    model=model if brand != ANY else ANY,
                    min_price=min_price or 0,
                    max_price=max_price or 999_999_999,
                    min_year=min_year or 1970,
                    max_year=max_year or 2030,
                    min_km=min_km or 0,
                    max_km=max_km or 1_000_000,
                    max_tramer=999_999_999 if max_tramer is None else max_tramer,
                    duration_hours=duration_hours,
                    cycle_interval_min=interval_min,
                    allowed_parts=[
                        p for p, s in damage_state.items() if s in ("boyali", "degisen")
                    ],
                    changed_allowed_parts=[p for p, s in damage_state.items() if s == "degisen"],
                    include_unknown_damage=include_unknown,
                )
                manager.start(criteria)
            except ValidationError as exc:
                for err in exc.errors():
                    st.error(err.get("msg", str(err)))
            except ScanAlreadyRunningError as exc:
                st.warning(str(exc))
            else:
                st.toast("Tarama başlatıldı. İlk tur birkaç dakika sürebilir.", icon="🚀")
                st.rerun()


# ==========================================================================
#  İLANLAR SEKMESİ
# ==========================================================================


def _load_rows() -> list[dict[str, Any]]:
    return annotate(repo.list_listings())


DISPLAY_COLS = {
    "source_site": "Site",
    "brand": "Marka",
    "model": "Model",
    "package_trim": "Paket",
    "year": "Yıl",
    "km": "KM",
    "price": "Fiyat",
    "deal_pct": "Piyasaya göre",
    "tramer_fee": "Tramer",
    "painted_parts": "Boyalı",
    "changed_parts": "Değişen",
    "location": "Şehir",
    "first_seen_at": "İlk görülme",
    "link": "Link",
}

with tab_list:

    @st.fragment(run_every=20)
    def listings_view() -> None:
        rows = _load_rows()
        if not rows:
            st.info("Henüz kayıtlı ilan yok. **Tarama** sekmesinden kriter belirleyip başlatın.")
            return

        new_rows = [r for r in rows if r["is_new_listing"]][:12]
        if new_rows:
            st.subheader(f"🚨 Bu taramada yakalananlar ({sum(r['is_new_listing'] for r in rows)})")
            cols = st.columns(3)
            for i, row in enumerate(new_rows):
                cols[i % 3].markdown(listing_card(row), unsafe_allow_html=True)
            st.divider()

        df = pd.DataFrame(rows)
        f1, f2, f3 = st.columns([2, 2, 1])
        site_filter = f1.multiselect("Site", sorted(df["source_site"].unique()), placeholder="Tümü")
        query = f2.text_input("Ara (marka, model, paket)", placeholder="ör. egea dizel")
        only_deals = f3.toggle("Sadece fırsatlar", help="Piyasa medyanının en az %5 altında")
        if site_filter:
            df = df[df["source_site"].isin(site_filter)]
        if query:
            hay = (
                df["brand"] + " " + df["model"] + " " + df["package_trim"] + " " + df["title"]
            ).str.lower()
            for word in query.lower().split():
                df = df[hay.str.contains(word, regex=False)]
        if only_deals:
            df = df[df["deal_pct"].fillna(-100) >= 5]

        df = df.copy()
        local_tz = datetime.now().astimezone().tzinfo
        df["first_seen_at"] = (
            pd.to_datetime(df["first_seen_at"], utc=True)
            .dt.tz_convert(local_tz)
            .dt.tz_localize(None)
        )
        st.dataframe(
            df[list(DISPLAY_COLS)].rename(columns=DISPLAY_COLS),
            width="stretch",
            hide_index=True,
            height=480,
            column_config={
                "Link": st.column_config.LinkColumn("Link", display_text="Aç ↗"),
                "Fiyat": st.column_config.NumberColumn(format="%d ₺"),
                "Tramer": st.column_config.NumberColumn(format="%d ₺"),
                "KM": st.column_config.NumberColumn(format="%d"),
                "Yıl": st.column_config.NumberColumn(format="%d"),
                "Piyasaya göre": st.column_config.NumberColumn(
                    format="%.1f %%", help="Pozitif: piyasa medyanının altında (fırsat)"
                ),
                "İlk görülme": st.column_config.DatetimeColumn(format="DD.MM.YYYY HH:mm"),
            },
        )
        st.download_button(
            "⬇️ CSV olarak indir",
            df[list(DISPLAY_COLS)]
            .rename(columns=DISPLAY_COLS)
            .to_csv(index=False)
            .encode("utf-8-sig"),
            file_name=f"otogaleri_ilanlar_{datetime.now():%Y%m%d_%H%M}.csv",
            mime="text/csv",
        )

        with st.expander("📉 Fiyat geçmişi"):
            changed = [r for r in rows if r.get("price_changed_at")]
            options = {
                r[
                    "id"
                ]: f"{r['brand']} {r['model']} {r['year']} · {format_price(r['price'])} ({r['source_site']})"
                for r in (changed or rows)[:300]
            }
            pick = st.selectbox("İlan", list(options), format_func=options.__getitem__)
            if pick is not None:
                hist = pd.DataFrame(repo.get_price_history(pick))
                if len(hist) > 1:
                    st.line_chart(hist.set_index("observed_at")["price"])
                else:
                    st.caption("Bu ilan için henüz fiyat değişikliği gözlenmedi.")

    listings_view()

    with st.popover("🗑️ Tüm ilanları sil"):
        st.write("Bu işlem kayıtlı tüm ilanları ve fiyat geçmişini **kalıcı olarak** siler.")
        sure = st.checkbox("Eminim, sil")
        if st.button("Sil", type="primary", disabled=not sure):
            deleted = repo.clear_listings()
            st.toast(f"{deleted} ilan silindi.")
            st.rerun()


# ==========================================================================
#  PİYASA SEKMESİ
# ==========================================================================

with tab_market:
    rows = _load_rows()
    if not rows:
        st.info("Grafikler için önce ilan toplanmalı.")
    else:
        df = pd.DataFrame(rows)
        st.caption(
            "Değerler botun kaydettiği (kriterlerinize uyan) ilanlardan hesaplanır; tüm piyasayı değil, "
            "takip ettiğiniz segmenti yansıtır."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Siteye göre ilan sayısı**")
            st.bar_chart(
                df["source_site"].value_counts(), horizontal=True, y_label="", x_label="İlan"
            )
        with c2:
            st.markdown("**Markaya göre medyan fiyat (₺)**")
            med = df[df["price"] > 0].groupby("brand")["price"].median().sort_values().tail(15)
            st.bar_chart(med, horizontal=True, y_label="", x_label="Medyan fiyat")
        st.markdown("**Kilometre – fiyat dağılımı**")
        st.scatter_chart(df[df["price"] > 0], x="km", y="price", color="source_site", height=380)

        st.markdown("**En iyi 10 fırsat** (aynı marka/model/yıl medyanına göre)")
        deals = df.dropna(subset=["deal_pct"]).sort_values("deal_pct", ascending=False).head(10)
        if deals.empty:
            st.caption("Fırsat skoru için aynı model/yıldan en az 3 ilan gerekiyor.")
        else:
            for row in deals.to_dict("records"):
                st.markdown(listing_card(row), unsafe_allow_html=True)

st.caption(
    f"v{__version__} · "
    "Bu araç yalnızca herkese açık ilan sayfalarını okur; hedef sitelerin kullanım şartlarına "
    "uymak kullanıcının sorumluluğundadır."
)
