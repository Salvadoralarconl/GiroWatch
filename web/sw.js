'use strict';
// Shows the saved "This page couldn't load" screen when GiroWatch's server cannot be reached.
const CACHE = 'girowatch-load-failure-v1';
const FILES = ['/offline.html', '/load-failure.css?v=1', '/load-failure.js?v=1'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (request.mode === 'navigate') {
    // Pages always come from the server; the saved screen is only the fallback.
    event.respondWith(fetch(request).then(response => response.status >= 500 ? caches.match('/offline.html') : response).catch(() => caches.match('/offline.html')));
  } else if (FILES.includes(url.pathname + url.search)) {
    event.respondWith(fetch(request).catch(() => caches.match(url.pathname + url.search)));
  }
});
