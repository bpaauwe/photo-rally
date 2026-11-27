// Runs the service worker's logic against in-memory fakes of the Cache API, fetch and clients.
// Usage: node tests/sw_test.js
const vm = require('vm'), fs = require('fs'), path = require('path'), assert = require('assert');
const code = fs.readFileSync(path.join(__dirname, '..', 'rally/static/js/sw.js'), 'utf8');

function setup() {
  const listeners = {}, store = new Map(), messages = [];
  const key = r => (typeof r === 'string' ? r : r.url);
  const caches = {
    async open(n) {
      if (!store.has(n)) store.set(n, new Map());
      const m = store.get(n);
      return { async match(r) { return m.get(key(r)); }, async put(r, res) { m.set(key(r), res); } };
    },
    async keys() { return [...store.keys()]; },
    async delete(n) { return store.delete(n); },
  };
  const net = { online: true, hang: false, routes: {} };       // routes: url -> {ok, redirected}
  const mk = (url, o = {}) => { const r = { url, ok: o.ok !== false, status: o.ok === false ? 404 : 200, redirected: !!o.redirected };
                                r.clone = () => r; return r; };
  const sandbox = {
    URL, console, Promise,
    location: { origin: 'https://h' },
    setTimeout: (f, ms) => setTimeout(f, ms >= 3000 ? 20 : ms),
    Response: function (body, init) { this.body = body; this.status = init.status; this.ok = init.status < 400; },
    caches,
    fetch: async url => {
      const u = key(url);
      if (!net.online) throw new Error('offline');
      if (net.hang) return new Promise(() => {});
      return mk(u, net.routes[u]);
    },
    registration: { scope: 'https://h/prefix/play/' },
    skipWaiting() {},
    clients: { claim() {}, matchAll: async () => [{ postMessage: m => messages.push(m) }] },
    addEventListener: (t, f) => { listeners[t] = f; },
  };
  sandbox.self = sandbox;
  vm.runInNewContext(code, sandbox);
  const fire = async (type, ev) => {
    const waits = [];
    ev.waitUntil = p => waits.push(p);
    ev.respondWith = p => { ev.response = p; };
    listeners[type](ev);
    await Promise.all(waits);
    return ev.response ? ev.response : undefined;
  };
  const nav = url => fire('fetch', { request: { url, method: 'GET', mode: 'navigate' } });
  const sub = url => fire('fetch', { request: { url, method: 'GET', mode: 'no-cors' } });
  return { fire, nav, sub, store, net, messages };
}

const T = [];
const test = (name, fn) => T.push([name, fn]);
const PAGE = 'https://h/prefix/play/object/3', PHOTO = 'https://h/prefix/photo/abc.jpg', CSS = 'https://h/prefix/static/css/style.css';

test('navigation: online serves and saves, offline serves the saved copy', async () => {
  const w = setup();
  assert.ok((await w.nav(PAGE)).ok);
  w.net.online = false;
  const res = await w.nav(PAGE);
  assert.strictEqual(res.url, PAGE);
});
test('navigation: unsaved page offline gives the 503 fallback', async () => {
  const w = setup(); w.net.online = false;
  assert.strictEqual((await w.nav(PAGE)).status, 503);
});
test('navigation: slow network falls back to the saved copy', async () => {
  const w = setup();
  await w.nav(PAGE);
  w.net.hang = true;
  assert.strictEqual((await w.nav(PAGE)).url, PAGE);
});
test('navigation: redirects and errors are not saved', async () => {
  const w = setup();
  w.net.routes[PAGE] = { redirected: true };
  await w.nav(PAGE);
  const saved = w.store.get('rally-pages-v2');
  assert.ok(!saved || saved.size === 0);
});
test('join page, other scopes, non-GET and cross-origin are left alone', async () => {
  const w = setup();
  assert.strictEqual(await w.nav('https://h/prefix/play/join'), undefined);
  assert.strictEqual(await w.nav('https://h/prefix/admin/'), undefined);
  assert.strictEqual(await w.fire('fetch', { request: { url: PAGE, method: 'POST', mode: 'cors' } }), undefined);
  assert.strictEqual(await w.sub('https://other.example/prefix/photo/x.jpg'), undefined);
});
test('photos: cache first', async () => {
  const w = setup();
  await w.sub(PHOTO);
  w.net.online = false;
  assert.strictEqual((await w.sub(PHOTO)).url, PHOTO);
});
test('static: served from the saved copy, refreshed in the background', async () => {
  const w = setup();
  await w.sub(CSS);
  w.net.online = false;
  assert.strictEqual((await w.sub(CSS)).url, CSS);
});
test('precache saves pages, assets and media with progress, counts failures', async () => {
  const w = setup();
  w.net.routes['https://h/prefix/play/bad'] = { ok: false };
  w.net.routes['https://h/prefix/play/moved'] = { redirected: true };
  await w.fire('message', { data: { type: 'precache', pages: ['https://h/prefix/play/', 'https://h/prefix/play/bad', 'https://h/prefix/play/moved'],
                                    assets: [CSS], media: [PHOTO] } });
  const done = w.messages.filter(m => m.type === 'precache-done')[0];
  assert.deepStrictEqual([done.total, done.failed], [5, 2]);
  assert.strictEqual(w.messages.filter(m => m.type === 'precache-progress').length, 5);
  assert.ok(w.store.get('rally-media-v2').has(PHOTO) && w.store.get('rally-static-v2').has(CSS));
  assert.ok(w.store.get('rally-pages-v2').has('https://h/prefix/play/') && !w.store.get('rally-pages-v2').has('https://h/prefix/play/moved'));
});
test('precache does not refetch photos it already has; reset clears pages', async () => {
  const w = setup();
  await w.fire('message', { data: { type: 'precache', pages: ['https://h/prefix/play/'], media: [PHOTO] } });
  w.net.online = false;                                           // media is cached, so no failure for it
  await w.fire('message', { data: { type: 'precache', pages: [], media: [PHOTO] } });
  assert.strictEqual(w.messages.filter(m => m.type === 'precache-done').pop().failed, 0);
  await w.fire('message', { data: { type: 'precache', reset: true, pages: [], media: [] } });
  assert.ok(!w.store.get('rally-pages-v2') || w.store.get('rally-pages-v2').size === 0);
});
test('activate removes caches from older versions only', async () => {
  const w = setup();
  for (const n of ['rally-pages-v0', 'rally-media-v2', 'unrelated']) await (async () => { (await w.store.set(n, new Map())); })();
  await w.fire('activate', {});
  assert.deepStrictEqual([...w.store.keys()].sort(), ['rally-media-v2', 'unrelated']);
});

(async () => {
  let failed = 0;
  for (const [name, fn] of T) {
    try { await fn(); console.log('ok   -', name); } catch (e) { failed++; console.log('FAIL -', name, '\n      ', e.message); }
  }
  process.exit(failed ? 1 : 0);
})();
