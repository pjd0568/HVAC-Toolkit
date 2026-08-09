/* Minimal service worker — satisfies installability; caches shell static assets only. */
const CACHE = "hvac-calcs-v2-shell-2";
const PRECACHE = [
  "/static/css/v2.css",
  "/static/js/v2_shell.js",
  "/static/js/v2_draft.js",
  "/static/js/v2_wizard.js",
  "/static/manifest.webmanifest",
  "/static/images/brand/app-icon-192.png",
  "/static/images/brand/app-icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Network-first for app routes; cache-first for static shell assets.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copy));
        return res;
      }))
    );
  }
});
