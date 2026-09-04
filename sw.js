/* Europa Trip Atlas service worker.
 *
 * Caches the app shell and the trip data so the plan is readable offline,
 * which matters for 76 days across 14 countries on roaming data.
 *
 * Map tiles are deliberately NOT cached. The OpenStreetMap tile usage policy
 * prohibits prefetching or bulk-downloading tiles for offline use:
 *   https://operations.osmfoundation.org/policies/tiles/
 * If you switch app.js to a provider that permits caching (CARTO with a key,
 * or self-hosted tiles), you can add the tile host here.
 */

const VERSION = 'v2';
const SHELL = `europa-shell-${VERSION}`;
const DATA = `europa-data-${VERSION}`;

const SHELL_FILES = [
  './',
  './index.html',
  './styles.css?v=2',
  './app.js?v=2',
  './favicon.svg',
  './manifest.webmanifest',
  './404.html',
  './vendor/leaflet/leaflet.css',
  './vendor/leaflet/leaflet.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Never touch map tiles or any other cross-origin request.
  if (url.origin !== self.location.origin) return;

  // Trip data: network first, so a fresh publish is picked up immediately,
  // falling back to the last good copy when offline.
  if (url.pathname.endsWith('trip-data.json')) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(DATA).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request).then((r) => r || Response.error()))
    );
    return;
  }

  // Shell: cache first, refresh in the background.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
