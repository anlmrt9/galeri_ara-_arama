// OtoGaleri Avcı Botu - minimal service worker (PWA yüklenebilirlik şartı için)
// Ağ trafiğine karışmaz; sadece tarayıcının "ana ekrana ekle" kriterini karşılar.
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
