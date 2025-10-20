// serviceWorker.js

const CACHE_NAME = 'spotify-ai-card-v1';
const STATIC_ASSETS = [
  '/', '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  console.log('🟢 Service Worker installed');
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  console.log('🟠 Service Worker activated');
});

self.addEventListener('fetch', (event) => {
  const url = event.request.url;

  // 🚫 認証や動的APIはキャッシュしない（これが最重要）
  if (
    url.includes('/generate_api') ||
    url.includes('/result/') ||
    url.includes('/callback') ||
    url.includes('/login')
  ) {
    console.log('🚫 APIリクエストはキャッシュしません:', url);
    event.respondWith(fetch(event.request)); 
    return;
  }

  // ✅ 静的ファイルのみキャッシュ（オフライン時のPWA安定化）
  event.respondWith(
    caches.match(event.request).then(response =>
      response || fetch(event.request).then(fetchRes => {
        if (event.request.method === 'GET') {
          const resClone = fetchRes.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, resClone));
        }
        return fetchRes;
      })
    )
  );
});
