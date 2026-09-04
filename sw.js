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

const VERSION = 'v5';
const SHELL = `europa-shell-${VERSION}`;
const DATA = `europa-data-${VERSION}`;

const SHELL_FILES = [
  './',
  './index.html',
  './styles.css?v=5',
  './app.js?v=5',
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

  // Data files: network first, so a fresh publish is picked up immediately,
  // falling back to the last good copy when offline.
  //
  // my-places.json is handled here rather than precached in SHELL_FILES on
  // purpose. It is optional and may not exist yet, and cache.addAll() rejects
  // as a whole if any one entry 404s, which would fail the install and leave
  // the site with no service worker at all. Fetching it here caches it on the
  // first successful load, which is exactly how trip-data.json is treated.
  if (
    url.pathname.endsWith('trip-data.json') ||
    url.pathname.endsWith('my-places.json')
  ) {
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
