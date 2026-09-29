// Author: Daen
// CyberDeck Service Worker
const CACHE_NAME = 'cyberdeck-v3';

self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  // Network first for realtime dashboard responsiveness
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
