// Participant pages: offline-tolerant mark queue, plus the Mark button on photo spot pages.
(function () {
  'use strict';
  const cfg = document.getElementById('play-config');
  if (!cfg) return;
  const $ = id => document.getElementById(id);
  const MARK_URL = cfg.dataset.markUrl, QKEY = 'rally-queue-' + cfg.dataset.team;

  // ---------- Queue: marks are kept on the phone until the server confirms them ----------
  const readQ = () => { try { return JSON.parse(localStorage.getItem(QKEY) || '[]'); } catch (e) { return []; } };
  const writeQ = q => { try { localStorage.setItem(QKEY, JSON.stringify(q)); } catch (e) { /* storage full or blocked */ } };
  const MKEY = 'rally-marked-' + cfg.dataset.team;
  const readMarked = () => { try { return new Set(JSON.parse(localStorage.getItem(MKEY) || '[]')); } catch (e) { return new Set(); } };
  const rememberMarked = id => { const m = readMarked(); m.add(String(id)); try { localStorage.setItem(MKEY, JSON.stringify([...m])); } catch (e) { /* ignore */ } };
  const banner = $('queue-banner');
  let flushing = false, notice = '';

  function paint() {
    const q = readQ(), pend = new Set(q.map(x => String(x.spot || x.object_id)));
    document.querySelectorAll('[data-pending-for]').forEach(el => { el.hidden = !pend.has(el.dataset.pendingFor); });
    const mine = readMarked();          // a saved page may predate a mark made on this phone
    document.querySelectorAll('[data-marked-for]').forEach(el => { if (mine.has(el.dataset.markedFor)) el.hidden = false; });
    document.querySelectorAll('[data-unmarked-for]').forEach(el => { if (mine.has(el.dataset.unmarkedFor)) el.hidden = true; });
    const parts = [];
    if (q.length) parts.push(q.length + (q.length === 1 ? ' mark is' : ' marks are') +
                             ' saved on this phone and waiting to send.');
    if (notice) parts.push(notice);
    banner.hidden = parts.length === 0;
    banner.textContent = parts.join(' ');
    if (q.length) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'link'; b.textContent = 'Send now';
      b.addEventListener('click', flush);
      banner.append(' ', b);
    }
  }

  async function flush() {
    if (flushing) return;
    flushing = true;
    try {
      for (let q = readQ(); q.length; q = readQ()) {
        const item = q[0];
        let res;
        try {
          res = await fetch(MARK_URL, { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(item) });
        } catch (e) { break; }                              // no signal: try again later
        if (res.status === 401 || res.status >= 500) break; // not signed in / server trouble: keep it
        if (!res.ok && res.status !== 409) notice = 'A mark was rejected by the server (is the rally still open?).';
        writeQ(readQ().filter(x => x.client_uuid !== item.client_uuid));
      }
    } finally { flushing = false; paint(); }
  }

  function enqueue(item) {
    writeQ(readQ().concat([item]));
    rememberMarked(item.spot || item.object_id);
    paint();
    return flush();
  }

  const switchForm = $('switch-form');
  if (switchForm) switchForm.addEventListener('submit', e => {
    const n = readQ().length;
    if (n && !confirm(n + (n === 1 ? ' mark is' : ' marks are') + ' still waiting to send from this phone. ' +
        'They stay saved, but only send when you join this team again. Switch team anyway?')) e.preventDefault();
  });

  window.addEventListener('online', flush);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) flush(); });
  paint();
  flush();

  // ---------- Offline: service worker, and saving the rally's pages and photos ----------
  const status = $('offline-status'), say2 = t => { if (status) status.textContent = t; };
  const TEAMKEY = 'rally-offline-team', SAVEDKEY = 'rally-offline-saved-' + cfg.dataset.team;
  const THROTTLE_MS = 5 * 60 * 1000;

  function onSwMessage(ev) {
    const m = ev.data || {};
    if (m.type === 'precache-progress') say2('Saving for offline use... ' + m.done + '/' + m.total);
    else if (m.type === 'precache-done') {
      if (m.failed === 0) {
        try { localStorage.setItem(SAVEDKEY, String(Date.now())); } catch (e) { /* ignore */ }
        say2('Saved for offline use \u2713');
      } else {
        say2('Saved most of it, but ' + m.failed + ' item' + (m.failed === 1 ? '' : 's') +
             ' could not be saved. Reload when you have a good connection to retry.');
      }
    }
  }

  async function saveForOffline(reg, reset) {
    if (!navigator.onLine) { say2('Offline. Showing pages saved on this phone.'); return; }
    let last = 0;
    try { last = parseInt(localStorage.getItem(SAVEDKEY) || '0', 10); } catch (e) { /* ignore */ }
    if (Date.now() - last < THROTTLE_MS) { say2('Saved for offline use \u2713'); return; }
    try {
      const res = await fetch(cfg.dataset.manifestUrl, { credentials: 'same-origin', cache: 'no-store' });
      if (!res.ok) return;
      const m = await res.json();
      say2('Saving for offline use...');
      reg.active.postMessage({ type: 'precache', reset: !!reset, pages: m.pages, media: m.media, assets: m.assets });
    } catch (e) { say2('Could not save for offline use yet. Will retry when online.'); }
  }

  async function setupOffline() {
    if (!('serviceWorker' in navigator) || !window.isSecureContext) {
      say2('Offline use needs a secure (https) connection.');
      return;
    }
    try {
      await navigator.serviceWorker.register(cfg.dataset.swUrl, { scope: cfg.dataset.scope });
      const reg = await navigator.serviceWorker.ready;
      navigator.serviceWorker.addEventListener('message', onSwMessage);
      let prevTeam = null;
      try { prevTeam = localStorage.getItem(TEAMKEY); localStorage.setItem(TEAMKEY, cfg.dataset.team); } catch (e) { /* ignore */ }
      const reset = !!prevTeam && prevTeam !== cfg.dataset.team;   // another team used this browser: drop its saved pages
      if (reset) { try { localStorage.removeItem(SAVEDKEY); } catch (e) { /* ignore */ } }
      saveForOffline(reg, reset);
      window.addEventListener('online', () => saveForOffline(reg));
    } catch (e) { say2('Offline use isn\'t available in this browser.'); }
  }
  setupOffline();

  // ---------- Mark button (photo spot pages) ----------
  const btn = $('mark-btn');
  if (!btn) return;
  const panel = $('mark-panel'), ready = $('gps-ready'), result = $('mark-result');
  const SPOT = panel.dataset.spot;
  const MOVING_MS = 2.2;                 // about 5 mph
  const SAMPLE_S = 8, GIVE_UP_S = 20, MIN_FIXES = 3;
  let latest = null, sampling = false, sample = [], t0 = 0, ticker = null, wake = null;
  let marked = parseInt(panel.dataset.marks, 10) > 0;

  const say = (html, cls) => { result.className = cls || ''; result.textContent = html; };
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID()
    : 'm' + Date.now().toString(16) + Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2));

  async function keepAwake() {
    try { if (navigator.wakeLock && !wake) { wake = await navigator.wakeLock.request('screen');
                                             wake.addEventListener('release', () => { wake = null; }); } }
    catch (e) { /* optional */ }
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) keepAwake(); });

  function onFix(pos) {
    const c = pos.coords;
    latest = { lat: c.latitude, lon: c.longitude, acc: c.accuracy, speed: c.speed, t: Date.now() };
    if (sampling) sample.push(latest);
    else {
      ready.textContent = 'GPS ready (\u00b1' + c.accuracy.toFixed(0) + ' m).';
      btn.disabled = false;
    }
  }

  function onError(err) {
    if (err.code === 1) {
      ready.textContent = 'Location permission is off. Allow location for this site in your browser settings, then reload.';
      btn.disabled = true;
    } else if (!latest) ready.textContent = 'Waiting for a GPS signal...';
  }

  function tick() {
    const s = (Date.now() - t0) / 1000;
    ready.textContent = 'Hold still... ' + Math.max(0, Math.ceil(SAMPLE_S - s)) + ' s (' + sample.length + ' readings)';
    if ((s >= SAMPLE_S && sample.length >= MIN_FIXES) || s >= GIVE_UP_S) finishSample();
  }

  function stopSampling() {
    clearInterval(ticker);
    sampling = false;
    btn.disabled = false;
    ready.textContent = latest ? 'GPS ready (\u00b1' + latest.acc.toFixed(0) + ' m).' : 'Waiting for a GPS signal...';
  }

  async function finishSample() {
    const fixes = sample;
    stopSampling();
    if (fixes.length < MIN_FIXES) {
      say('Could not get a steady GPS position. Move to open sky and press Mark again.', 'warn');
      return;
    }
    const withSpeed = fixes.filter(f => f.speed !== null && !isNaN(f.speed));
    const r = RallyGPS.summarize(fixes);
    if ((withSpeed.length && withSpeed.filter(f => f.speed > MOVING_MS).length / withSpeed.length > 0.3) || r.spread > 30) {
      say('The car seems to be moving. Stop somewhere safe, then press Mark again.', 'warn');
      return;
    }
    const item = { spot: SPOT, lat: r.lat, lon: r.lon, accuracy_m: Math.round(r.acc * 10) / 10,
                   n_samples: r.n, client_ts: new Date().toISOString(), client_uuid: uuid() };
    marked = true;
    btn.textContent = 'Mark again';
    say('Marked \u2713 (\u00b1' + r.acc.toFixed(0) + ' m)' + (r.acc > 25 ? '. Weak GPS here. You can mark again from a spot with a clearer view of the sky.' : '.'), 'ok');
    await enqueue(item);
    const stillWaiting = readQ().some(x => x.client_uuid === item.client_uuid);
    result.append(' ', document.createTextNode(stillWaiting
      ? 'Saved on this phone. It will send when you have signal.' : 'Sent.'));
  }

  btn.addEventListener('click', () => {
    if (sampling) return;
    if (latest && latest.speed !== null && !isNaN(latest.speed) && latest.speed > MOVING_MS) {
      say('You seem to be moving. Stop somewhere safe, then press Mark.', 'warn');
      return;
    }
    sampling = true; sample = []; t0 = Date.now();
    btn.disabled = true;
    say('', '');
    ticker = setInterval(tick, 250);
    tick();
  });

  if (!navigator.geolocation) { ready.textContent = 'This browser has no GPS support.'; return; }
  if (!window.isSecureContext) { ready.textContent = 'GPS needs a secure (https) connection.'; return; }
  keepAwake();
  navigator.geolocation.watchPosition(onFix, onError, { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
})();
