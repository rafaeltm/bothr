const CACHE_NAME = 'bothr-v2';

// Static assets safe to cache (no sensitive data)
const PRECACHE_URLS = [
  '/',
  '/dashboard',
  '/calendar',
  '/logs',
  '/settings',
  '/offline',
  '/manifest.json',
  '/static/css/style.css',
  '/static/js/calendar.js',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never intercept API calls, auth challenges, or cross-origin requests
  if (
    url.pathname.startsWith('/api/') ||
    url.origin !== self.location.origin
  ) {
    return;
  }

  // Network-first for HTML pages so fresh content is always preferred
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          return response;
        })
        .catch(async () => {
          const cachedPage = await caches.match(event.request);
          if (cachedPage) return cachedPage;

          const routeFallback = await caches.match(url.pathname);
          if (routeFallback) return routeFallback;

          return caches.match('/offline');
        })
    );
    return;
  }

  // Stale-while-revalidate for static assets
  event.respondWith(
    caches.match(event.request).then(async (cached) => {
      const networkFetch = fetch(event.request)
        .then((response) => {
          if (response && response.ok) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return response;
        })
        .catch(async () => {
          if (cached) return cached;
          if (event.request.destination === 'document') {
            return caches.match('/offline');
          }
          return new Response('Offline', { status: 503, statusText: 'Offline' });
        });

      return cached || networkFetch;
    })
  );
});
