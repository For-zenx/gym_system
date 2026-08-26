// sw.js — Service Worker mínimo para PWA en Perfect Line II
const CACHE_NAME = 'perfectline-v2';
const ASSETS = [
  '/tablet/enrolamiento_acceso/',
  '/tablet/acceso/',
  '/tablet/enrolamiento/',
  '/static/css/tablet.css?v=3.2',
  '/static/vendor/face-api.min.js',
  '/static/js/tablet_face_utils.js?v=1.6',
  '/static/js/tablet_enrollment.js?v=2.5',
  '/static/js/tablet_enrolamiento_acceso.js?v=1.17',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Estrategia: Network first, fallback to cache
self.addEventListener('fetch', (event) => {
  // Solo interceptar peticiones de nuestro propio origen y con métodos GET
  if (event.request.method !== 'GET') return;
  
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Clonar y guardar en caché si la respuesta es válida
        if (response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});
