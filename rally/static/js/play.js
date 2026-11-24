// Participant pages: offline-tolerant mark queue, plus the Mark button on object pages.
(function () {
  'use strict';
  const cfg = document.getElementById('play-config');
  if (!cfg) return;
  const $ = id => document.getElementById(id);
  const MARK_URL = cfg.dataset.markUrl, QKEY = 'rally-queue-' + cfg.dataset.team;

  // ---------- Queue: marks are kept on the phone until the server confirms them ----------
  const readQ = () => { try { return JSON.parse(localStorage.getItem(QKEY) || '[]'); } catch (e) { return []; } };
  const writeQ = q => { try { localStorage.setItem(QKEY, JSON.stringify(q)); } catch (e) { /* storage full or blocked */ } };
  const banner = $('queue-banner');
  let flushing = false, notice = '';

  function paint() {
    const q = readQ(), pend = new Set(q.map(x => String(x.object_id)));
    document.querySelectorAll('[data-pending-for]').forEach(el => { el.hidden = !pend.has(el.dataset.pendingFor); });
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
    paint();
    return flush();
  }

  window.addEventListener('online', flush);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) flush(); });
  paint();
  flush();

  // ---------- Mark button (object pages) ----------
  const btn = $('mark-btn');
  if (!btn) return;
  const panel = $('mark-panel'), ready = $('gps-ready'), result = $('mark-result');
  const OBJECT_ID = parseInt(panel.dataset.objectId, 10);
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
    const item = { object_id: OBJECT_ID, lat: r.lat, lon: r.lon, accuracy_m: Math.round(r.acc * 10) / 10,
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
