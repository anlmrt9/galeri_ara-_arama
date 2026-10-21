"""Kazınmış (güvenilmeyen) veriyi HTML'e güvenle basmak için saf yardımcılar.

Eski arayüz ilan başlığı ve linkini ``unsafe_allow_html`` ile kaçışsız basıyordu
(depolanmış XSS). Burada her metin ``html.escape`` edilir, link yalnızca
``http(s)`` şemasındaysa bağlantıya dönüşür.
"""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlparse

from otogaleri.formatting import format_number, format_price

SITE_COLORS = {
    "Otoplus": "#e11d48",
    "Otokoç 2. El": "#ea580c",
    "Arabam.com": "#2563eb",
    "VavaCars": "#7c3aed",
}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def safe_url(value: Any) -> str | None:
    """Yalnızca mutlak ``http``/``https`` adreslerini kabul eder (``javascript:`` vb. reddedilir)."""
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return url
    return None


def deal_badge(deal_pct: float | None) -> str:
    if deal_pct is None:
        return ""
    if deal_pct >= 5:
        return f'<span class="og-badge og-good">Piyasanın %{deal_pct:.0f} altında</span>'
    if deal_pct <= -5:
        return f'<span class="og-badge og-warn">Piyasanın %{-deal_pct:.0f} üstünde</span>'
    return '<span class="og-badge">Piyasa seviyesinde</span>'


def listing_card(row: dict[str, Any]) -> str:
    site = str(row.get("source_site") or "")
    color = SITE_COLORS.get(site, "#475569")
    name = " ".join(str(row.get(k) or "") for k in ("brand", "model", "package_trim")).strip()
    url = safe_url(row.get("link"))
    link = (
        f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">İlana git ↗</a>'
        if url
        else ""
    )
    tramer = row.get("tramer_fee")
    tramer_txt = format_price(tramer) if tramer not in (None, "") else "bilinmiyor"
    drop = ""
    initial, price = row.get("initial_price") or 0, row.get("price") or 0
    if initial and price and price < initial:
        drop = f'<span class="og-badge og-good">↓ {esc(format_price(initial - price))}</span>'
    return f"""
<div class="og-card">
  <div class="og-card-head">
    <span class="og-site" style="background:{color}">{esc(site)}</span>
    {deal_badge(row.get("deal_pct"))} {drop}
  </div>
  <div class="og-title">{esc(name or row.get("title"))}</div>
  <div class="og-price">{esc(format_price(price))}</div>
  <div class="og-meta">{esc(row.get("year") or "-")} · {esc(format_number(row.get("km")))} km
     {("· " + esc(row.get("location"))) if row.get("location") else ""}</div>
  <div class="og-meta">Boya: {esc(row.get("painted_parts"))} · Değişen: {esc(row.get("changed_parts"))}
     · Tramer: {esc(tramer_txt)}</div>
  <div class="og-link">{link}</div>
</div>"""


CSS = """
<style>
.og-card { border: 1px solid rgba(128,128,128,.25); border-radius: 10px; padding: 14px 16px;
           margin-bottom: 12px; background: rgba(128,128,128,.04); }
.og-card-head { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 6px; }
.og-site { color: #fff; font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 4px; }
.og-badge { font-size: 12px; padding: 2px 8px; border-radius: 999px;
            border: 1px solid rgba(128,128,128,.35); opacity: .9; }
.og-good { border-color: #16a34a; color: #16a34a; }
.og-warn { border-color: #d97706; color: #d97706; }
.og-title { font-weight: 600; font-size: 15px; line-height: 1.3; }
.og-price { font-size: 20px; font-weight: 700; margin: 4px 0; font-variant-numeric: tabular-nums; }
.og-meta { font-size: 13px; opacity: .75; }
.og-link { margin-top: 6px; font-size: 13px; }
.og-chip { display: inline-block; font-size: 12px; padding: 3px 9px; border-radius: 999px;
           margin: 0 6px 6px 0; border: 1px solid rgba(128,128,128,.3); }
.og-chip.ok::before { content: "●"; color: #16a34a; margin-right: 5px; }
.og-chip.failed::before { content: "●"; color: #dc2626; margin-right: 5px; }
.og-chip.idle::before { content: "●"; color: #9ca3af; margin-right: 5px; }
</style>
"""


def site_chip(site: str, run: dict[str, Any] | None, when: str, *, ready: bool = True) -> str:
    if not ready:
        return f'<span class="og-chip idle">{esc(site)} · kurulum gerekli</span>'
    if run is None:
        return f'<span class="og-chip idle">{esc(site)} · henüz taranmadı</span>'
    status = "ok" if run.get("status") == "ok" else "failed"
    detail = (
        f'{run.get("new", 0)} yeni / {run.get("matched", 0)} uygun' if status == "ok" else "hata"
    )
    title = esc(run.get("error") or "")
    return f'<span class="og-chip {status}" title="{title}">{esc(site)} · {esc(detail)} · {esc(when)}</span>'
