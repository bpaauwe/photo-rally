// Service worker for the participant pages (scope: /play/).
// - Pages: network first, but fall back to the saved copy if the network is slow or gone.
// - Photos: cache first (their file names change when a photo changes).
// - Static files: serve the saved copy and refresh it in the background.
// The page asks this worker to save everything for the rally (see play.js and /play/offline-manifest).
'use strict';

const VERSION = 'v2';
const PAGES = 'rally-pages-' + VERSION, MEDIA = 'rally-media-' + VERSION, STATIC = 'rally-static-' + VERSION;
const KEEP = [PAGES, MEDIA, STATIC];
const NAV_TIMEOUT_MS = 3000;
const SCOPE_PATH = new URL(self.registration.scope).pathname;           // e.g. /prefix/play/
const ROOT = new URL('../', self.registration.scope).pathname;          // e.g. /prefix/

self.addEventListener('install', () => { self.skipWaiting(); });

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith('rally-') && !KEEP.includes(name)) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

function offlineResponse() {
  return new Response(
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>Offline</title><body style="font-family:system-ui;margin:1.5rem">' +
    '<h1>You\'re offline</h1><p>This page wasn\'t saved on your phone yet. ' +
    'Go back to the object list, or try again when you have signal.</p>',
    { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

async function networkFirst(req) {
  const cache = await caches.open(PAGES);
  const net = fetch(req).then(res => {
    if (res.ok && !res.redirected) cache.put(req, res.clone());          // never keep redirects (e.g. to the join page)
    return res;
  });
  net.catch(() => {});                                                   // the race below handles failures
  const slow = new Promise(resolve => setTimeout(() => resolve(null), NAV_TIMEOUT_MS));
  try {
    const res = await Promise.race([net, slow]);
    if (res) return res;
  } catch (e) { /* offline: fall through to the saved copy */ }
  const saved = await cache.match(req);
  if (saved) return saved;
  try { return await net; } catch (e) { return offlineResponse(); }
}

async function cacheFirst(req, name) {
  const cache = await caches.open(name);
  const saved = await cache.match(req);
  if (saved) return saved;
  const res = await fetch(req);
  if (res.ok) cache.put(req, res.clone());
  return res;
}

async function staleWhileRevalidate(req, name) {
  const cache = await caches.open(name);
  const saved = await cache.match(req);
  const refresh = fetch(req).then(res => { if (res.ok) cache.put(req, res.clone()); return res; });
  if (saved) { refresh.catch(() => {}); return saved; }
  return refresh;
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  const p = url.pathname;
  if (req.mode === 'navigate') {
    if (p.startsWith(SCOPE_PATH) && !p.startsWith(SCOPE_PATH + 'join')) e.respondWith(networkFirst(req));
  } else if (p.startsWith(ROOT + 'photo/')) {
    e.respondWith(cacheFirst(req, MEDIA));
  } else if (p.startsWith(ROOT + 'static/')) {
    e.respondWith(staleWhileRevalidate(req, STATIC));
  }
});

// ---- Saving everything for offline use, on request from the page ----
async function broadcast(msg) {
  for (const c of await self.clients.matchAll({ includeUncontrolled: true })) c.postMessage(msg);
}

async function precache(d) {
  if (d.reset) await caches.delete(PAGES);
  const jobs = []
    .concat((d.pages || []).map(url => ({ url, cache: PAGES, refresh: true })))
    .concat((d.assets || []).map(url => ({ url, cache: STATIC, refresh: true })))
    .concat((d.media || []).map(url => ({ url, cache: MEDIA, refresh: false })));
  let done = 0, failed = 0, next = 0;
  async function run(job) {
    try {
      const cache = await caches.open(job.cache);
      if (!job.refresh && await cache.match(job.url)) return;
      const res = await fetch(job.url, { credentials: 'same-origin', cache: job.refresh ? 'no-cache' : 'default' });
      if (res.ok && !res.redirected) await cache.put(job.url, res);
      else failed++;
    } catch (e) { failed++; }
  }
  await Promise.all(Array.from({ length: 3 }, async () => {
    while (next < jobs.length) {
      await run(jobs[next++]);
      done++;
      await broadcast({ type: 'precache-progress', done, total: jobs.length });
    }
  }));
  await broadcast({ type: 'precache-done', failed, total: jobs.length });
}

self.addEventListener('message', e => {
  const d = e.data || {};
  if (d.type === 'reset') e.waitUntil(caches.delete(PAGES));
  else if (d.type === 'precache') e.waitUntil(precache(d));
});
