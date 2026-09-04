// OtoGaleri Avcı Botu - service worker
// Streamlit statik dosya sunumu kısıtlaması nedeniyle kapsam /app/static/ ile
// sınırlıdır; bu yüzden yalnızca ikonlar/manifest gibi statik varlıkları
// önbellekler (cache-first). Uygulamanın asıl (dinamik) sayfası bu kapsamın
// dışında kaldığından çevrimdışı çalışmaz - bu SW yalnızca "yüklenebilirlik"
// şartını karşılar ve statik varlık önbelleklemesini iyileştirir.
const CACHE_NAME = "otogaleri-static-v2";
const PRECACHE_URLS = [
  "app/static/manifest.json",
  "app/static/icon-192.png",
  "app/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isStaticAsset = url.pathname.includes("/app/static/");

  if (!isStaticAsset || event.request.method !== "GET") {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
        return response;
      });
    }).catch(() => fetch(event.request))
  );
});
