/* service-worker.js */
/* v2025-09-03 */
const VERSION = 'v9';
const HTML_CACHE   = `html-${VERSION}`;
const STATIC_CACHE = `static-${VERSION}`;
const FONT_CACHE   = `font-${VERSION}`;
const IMG_CACHE    = `img-${VERSION}`;
const OFFLINE_URL  = '/static/offline.html';

// (Opcional) Precache básico: agregá aquí tus assets críticos (hashed si usás WhiteNoise)
const PRECACHE_URLS = [
  '/',                     // si tenés home
  '/tracking/',            // pantalla principal de búsqueda
  '/static/manifest.json',
  OFFLINE_URL,
  // Ejemplos (ajustá rutas reales):
  // '/static/css/tracking.css',
  // '/static/img/icon-192.png',
  // '/static/img/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cacheHtml = await caches.open(HTML_CACHE);
    const cacheStatic = await caches.open(STATIC_CACHE);
    await cacheHtml.addAll([OFFLINE_URL]); // asegurar fallback
    await cacheStatic.addAll(['/static/manifest.json']); // manifest precache
    // Precache opcional
    try { await cacheHtml.addAll(PRECACHE_URLS); } catch (_) {}
    // Dejar listo para tomar control
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map(k => {
      if (![HTML_CACHE, STATIC_CACHE, FONT_CACHE, IMG_CACHE].includes(k)) {
        return caches.delete(k);
      }
    }));
    await self.clients.claim();
  })());
});

// Utilidades de estrategia
async function staleWhileRevalidate(request, cacheName, fallbackUrl = null) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then((networkRes) => {
    // Clonar y actualizar cache si ok
    if (networkRes && networkRes.status === 200) {
      cache.put(request, networkRes.clone());
    }
    return networkRes;
  }).catch((_) => null);
  // Si hay cache, devuelve rápido y revalida en background
  if (cached) return cached;
  // Si no hay cache, intentá red
  const networkRes = await fetchPromise;
  if (networkRes) return networkRes;
  // Falló red y no había cache
  if (fallbackUrl) return caches.match(fallbackUrl);
  return new Response('Sin conexión', { status: 503, headers: { 'Content-Type': 'text/plain' }});
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const networkRes = await fetch(request);
    if (networkRes && networkRes.status === 200) {
      cache.put(request, networkRes.clone());
    }
    return networkRes;
  } catch (e) {
    return new Response('Offline', { status: 503 });
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const isSameOrigin = url.origin === self.location.origin;

  // Navegaciones/HTML → stale-while-revalidate con fallback offline
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(staleWhileRevalidate(req, HTML_CACHE, OFFLINE_URL));
    return;
  }

  // Fuentes de Google: css (SWR), binarios (cache-first)
  if (url.origin.includes('fonts.googleapis.com')) {
    event.respondWith(staleWhileRevalidate(req, STATIC_CACHE));
    return;
  }
  if (url.origin.includes('fonts.gstatic.com')) {
    event.respondWith(cacheFirst(req, FONT_CACHE));
    return;
  }

  // Mis estáticos (mismo origen /static/…)
  if (isSameOrigin && url.pathname.startsWith('/static/')) {
    // Heurística por extensión
    if (/\.(?:css|js|woff2?|ttf|eot)$/.test(url.pathname)) {
      event.respondWith(cacheFirst(req, STATIC_CACHE));
      return;
    }
    if (/\.(?:png|jpg|jpeg|gif|svg|webp|ico)$/.test(url.pathname)) {
      event.respondWith(cacheFirst(req, IMG_CACHE));
      return;
    }
  }

  // Default: intentar SWR (seguro para GET)
  event.respondWith(staleWhileRevalidate(req, STATIC_CACHE));
});

// Mensaje para controlar updates desde la página
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

