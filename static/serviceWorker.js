// serviceWorker.js

const CACHE_NAME = 'spotify-ai-card-v2';
const STATIC_ASSETS = [
  '/', 
  '/manifest.json',
  '/static/favicon.ico'
];

const doNotCache = ['/login', '/callback', '/generate', '/session-check'];

self.addEventListener('fetch', event => {
  if (doNotCache.some(url => event.request.url.includes(url))) {
    return; // 通常 fetch（キャッシュしない）
  }
  // 通常キャッシュ処理
});


// ==============================
// 🔹 インストール
// ==============================
self.addEventListener('install', (event) => {
  console.log('🟢 Service Worker: Installed');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
});

// ==============================
// 🔹 アクティベート（古いキャッシュ削除）
// ==============================
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  console.log('🟠 Service Worker: Activated');
});

// ==============================
// 🔹 Fetch イベント処理
// ==============================
self.addEventListener('fetch', (event) => {
  const url = event.request.url;

  // 🚫 Spotify 認証や画像生成など動的APIはキャッシュしない
  if (
    url.includes('/generate_api') ||
    url.includes('/callback') ||
    url.includes('/login') ||
    url.includes('/result') ||
    url.includes('/generate/')
  ) {
    console.log('🚫 APIリクエストはキャッシュせず直接取得:', url);
    event.respondWith(fetch(event.request));
    return;
  }

  // ✅ GET リクエストで静的ファイルのみキャッシュ利用
  if (event.request.method === 'GET') {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request)
          .then((networkResponse) => {
            const cloned = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, cloned);
            });
            return networkResponse;
          })
          .catch(() => {
            // オフライン時 fallback
            return caches.match('/');
          });
      })
    );
  }
});
