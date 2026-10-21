"""PWA katmanı: manifest, ikonlar, iOS splash ekranları ve service worker kaydı.

Streamlit ``<head>``'e doğrudan erişim vermediği için küçük bir bileşen iframe'inden
üst belgeye eklenir. ``.streamlit/config.toml`` içinde ``enableStaticServing = true``
gereklidir (``static/`` klasörü ``/app/static/`` altında sunulur).
"""

from __future__ import annotations

import streamlit as st

_SNIPPET = """
<script>
(function () {
  const doc = window.parent.document, win = window.parent;
  // Streamlit sayfayı lang="en" ile sunuyor; Türkçe içerik yüzünden Chrome sayfayı
  // "İngilizce" sanıp otomatik çeviriyor, metin düğümlerini değiştiriyor ve React
  // "removeChild ... not a child of this node" hatasıyla çöküyor. Dili düzelt ve
  // çeviriyi kapat.
  const html = doc.documentElement;
  html.lang = "tr";
  html.setAttribute("translate", "no");
  html.classList.add("notranslate");
  if (doc.body) { doc.body.setAttribute("translate", "no"); doc.body.classList.add("notranslate"); }
  if (!doc.querySelector('meta[name="google"]')) {
    const g = doc.createElement("meta"); g.name = "google"; g.content = "notranslate";
    doc.head.appendChild(g);
  }
  if (doc.getElementById("pwa-manifest")) return;
  const link = (rel, href, extra) => {
    const el = doc.createElement("link");
    el.rel = rel; el.href = href; Object.assign(el, extra || {});
    doc.head.appendChild(el);
    return el;
  };
  link("manifest", "app/static/manifest.json").id = "pwa-manifest";
  link("apple-touch-icon", "app/static/icon-192.png");
  [["theme-color", "#14532d"], ["mobile-web-app-capable", "yes"],
   ["apple-mobile-web-app-capable", "yes"], ["apple-mobile-web-app-title", "OtoGaleri"],
   ["apple-mobile-web-app-status-bar-style", "default"]].forEach(([n, c]) => {
    if (doc.querySelector(`meta[name="${n}"]`)) return;
    const m = doc.createElement("meta"); m.name = n; m.content = c; doc.head.appendChild(m);
  });
  [["se1",320,568,2],["iphone8",375,667,2],["iphonex",375,812,3],["iphone12",390,844,3],
   ["iphone14pro",393,852,3],["iphone8plus",414,736,3],["iphonexr",414,896,2],
   ["iphonexsmax",414,896,3],["iphone12promax",428,926,3],["iphone14promax",430,932,3],
   ["ipad97",768,1024,2],["ipad102",810,1080,2],["ipadpro11",834,1194,2],["ipadpro129",1024,1366,2]
  ].forEach(([n, w, h, r]) => link("apple-touch-startup-image", `app/static/splash/${n}.png`, {
    media: `(device-width: ${w}px) and (device-height: ${h}px) and (-webkit-device-pixel-ratio: ${r}) and (orientation: portrait)`
  }));
  if ("serviceWorker" in win.navigator) {
    win.navigator.serviceWorker.register("app/static/sw.js").catch(() => {});
  }
})();
</script>
"""


def inject_pwa() -> None:
    if hasattr(st, "iframe"):  # Streamlit >= 1.50
        st.iframe(_SNIPPET, height=1)
    else:  # pragma: no cover - eski Streamlit
        import streamlit.components.v1 as components

        components.html(_SNIPPET, height=0)
