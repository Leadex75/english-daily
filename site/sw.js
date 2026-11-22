var CACHE_NAME = 'english-daily-20261122115247';
var APP_SHELL = [
  './',
  './index.html',
  './css/themes.css',
  './style.css',
  './app.js',
  './lib/store.js',
  './lib/branding.js',
  './lib/settings.js',
  './lib/links.js',
  './lib/progress.js',
  './lib/anki.js',
  './lib/exercises.js',
  './lib/tour.js',
  './lib/search.js',
  './lib/archive.js',
  './lib/pwa.js',
  './vendor/alpine.min.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './data/languages.json'
];

function assetUrl(path) {
  return new URL(path, self.registration.scope).toString();
}

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE_NAME).then(function (cache) {
    return cache.addAll(APP_SHELL.map(assetUrl));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (key) { return key !== CACHE_NAME; }).map(function (key) {
      return caches.delete(key);
    }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.toLowerCase().endsWith('.mp3') || url.pathname.indexOf('/api/') !== -1) return;

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(function () {
      return caches.match(assetUrl('./index.html'));
    }));
    return;
  }

  if (url.pathname.indexOf('/data/') !== -1) {
    event.respondWith(fetch(request).then(function (response) {
      var copy = response.clone();
      caches.open(CACHE_NAME).then(function (cache) { cache.put(request, copy); });
      return response;
    }).catch(function () { return caches.match(request); }));
    return;
  }

  event.respondWith(caches.match(request).then(function (cached) {
    var network = fetch(request).then(function (response) {
      var copy = response.clone();
      caches.open(CACHE_NAME).then(function (cache) { cache.put(request, copy); });
      return response;
    }).catch(function () { return cached; });
    return cached || network;
  }));
});
