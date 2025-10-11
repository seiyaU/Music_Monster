self.addEventListener("install", (e) => {
  console.log("Service Worker: Installed");
});

self.addEventListener("fetch", (e) => {
  // キャッシュ戦略（最初は単純でOK）
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
