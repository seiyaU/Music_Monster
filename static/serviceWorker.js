const CACHE_NAME = 'music-monster-v3';
const STATIC_ASSETS = ['/', '/manifest.json'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
});

self.addEventListener('fetch', (event) => {
  const { pathname } = new URL(event.request.url);
  const dynamicPaths = ['/analyze-taste', '/generate_api', '/result', '/generate/'];
  if (dynamicPaths.some((path) => pathname.startsWith(path))) {
    event.respondWith(fetch(event.request));
    return;
  }

  if (event.request.method === 'GET') {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      }).catch(() => caches.match('/')))
    );
  }
});
