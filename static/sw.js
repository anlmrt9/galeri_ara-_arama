// OtoGaleri Avcı Botu - service worker
// Streamlit statik dosya sunumu kısıtlaması nedeniyle kapsam /app/static/ ile
// sınırlıdır; uygulamanın asıl (dinamik) sayfası önbelleklenemez, bu yüzden
// tam çevrimdışı çalışma mümkün değildir. Bunun yerine iki şey yapılır:
//  1. Statik varlıklar (ikon/manifest/splash) cache-first önbelleklenir.
//  2. Sayfa navigasyonu ağ hatası verdiğinde kullanıcı dostu bir "çevrimdışı"
//     ekranı gösterilir (offline.html), boş beyaz ekran yerine.
const CACHE_NAME = "otogaleri-static-v4";
const OFFLINE_URL = "/app/static/offline.html";
const PRECACHE_URLS = [
  "/app/static/manifest.json",
  "/app/static/icon-192.png",
  "/app/static/icon-512.png",
  OFFLINE_URL,
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
  const request = event.request;
  if (request.method !== "GET") return;

  // Sayfa navigasyonu: ağ önce, hata olursa çevrimdışı ekranını göster.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE_URL).then((cached) => cached || Response.error())
      )
    );
    return;
  }

  const url = new URL(request.url);
  const isStaticAsset = url.pathname.includes("/app/static/");
  if (!isStaticAsset) return; // diğer istekler tarayıcının varsayılan davranışına bırakılır

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return response;
      });
    }).catch(() => caches.match(OFFLINE_URL))
  );
});
