(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const num = s => { const x = parseFloat(s); return isNaN(x) ? null : x; };

  // ---------- Photo: shrink on the phone before upload ----------
  const fileIn = $('photo'), prev = $('photo-preview'), pstat = $('photo-status');
  const MAX_SIDE = 1600;

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const img = new Image(), url = URL.createObjectURL(file);
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('unreadable')); };
      img.src = url;
    });
  }

  fileIn.addEventListener('change', async () => {
    const file = fileIn.files[0];
    if (!file) { prev.hidden = true; return; }
    pstat.textContent = 'Preparing photo...';
    try {
      const img = await loadImage(file);
      const s = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement('canvas');
      c.width = Math.round(img.naturalWidth * s);
      c.height = Math.round(img.naturalHeight * s);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.85));
      if (!blob) throw new Error('encode failed');
      const out = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
      const dt = new DataTransfer();
      dt.items.add(out);
      fileIn.files = dt.files;
      prev.src = URL.createObjectURL(out);
      pstat.textContent = 'Photo ready (' + Math.round(blob.size / 1024) + ' KB).';
    } catch (e) {
      prev.src = URL.createObjectURL(file);          // fall back to the original file
      pstat.textContent = 'Could not shrink this photo; the original will be uploaded.';
    }
    prev.hidden = false;
  });

  // ---------- GPS: sample while standing still, keep the best fixes ----------
  const F = { lat: $('lat'), lon: $('lon'), acc: $('acc_m'), spread: $('spread_m'), n: $('samples') };
  const startBtn = $('gps-start'), stopBtn = $('gps-stop'), gstat = $('gps-status');
  let watchId = null, ticker = null, fixes = [], endAt = 0, wake = null;

  const median = a => { const s = a.slice().sort((x, y) => x - y), m = s.length >> 1;
                        return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  function summarize(list) {
    // Keep the best 60% by reported accuracy (at least 3), then take the median position.
    const best = list.slice().sort((a, b) => a.acc - b.acc)
                     .slice(0, Math.max(3, Math.ceil(list.length * 0.6)));
    const lat = median(best.map(f => f.lat)), lon = median(best.map(f => f.lon));
    const kx = 111320 * Math.cos(lat * Math.PI / 180), ky = 110540;
    const msq = best.reduce((t, f) => t + Math.pow((f.lon - lon) * kx, 2) + Math.pow((f.lat - lat) * ky, 2), 0) / best.length;
    return { lat, lon, acc: median(best.map(f => f.acc)), spread: Math.sqrt(msq), n: best.length };
  }

  function onFix(pos) {
    const c = pos.coords;
    fixes.push({ lat: c.latitude, lon: c.longitude, acc: c.accuracy });
    refreshStatus();
  }

  function refreshStatus() {
    const left = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
    const last = fixes.length ? fixes[fixes.length - 1].acc : null;
    gstat.textContent = 'Sampling... ' + left + ' s left, ' + fixes.length + ' fixes' +
      (last !== null ? ', latest accuracy \u00b1' + last.toFixed(0) + ' m' : ', waiting for a fix');
    if (left === 0) finish();
  }

  function stopWatching() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    clearInterval(ticker);
    watchId = ticker = null;
    if (wake) { wake.release().catch(() => {}); wake = null; }
    startBtn.disabled = false;
    stopBtn.hidden = true;
  }

  function finish() {
    stopWatching();
    if (fixes.length < 3) {
      gstat.textContent = 'Only ' + fixes.length + ' fixes arrived. Move to open sky and try again.';
      return;
    }
    const r = summarize(fixes);
    F.lat.value = r.lat.toFixed(7);
    F.lon.value = r.lon.toFixed(7);
    F.acc.value = r.acc.toFixed(1);
    F.spread.value = r.spread.toFixed(1);
    F.n.value = r.n;
    gstat.textContent = 'Captured from ' + r.n + ' of ' + fixes.length + ' fixes: accuracy \u00b1' +
      r.acc.toFixed(0) + ' m, scatter ' + r.spread.toFixed(1) + ' m. Press Save object to keep it.';
    showOriginal();
  }

  function onError(err) {
    const why = { 1: 'Location permission was denied. Allow it for this site in the browser settings.',
                  2: 'The phone could not get a position. Try again in open sky.',
                  3: 'Timed out waiting for a position.' }[err.code] || err.message;
    if (err.code === 1) { stopWatching(); gstat.textContent = why; }
    else gstat.textContent = why + ' (' + fixes.length + ' fixes so far)';
  }

  startBtn.addEventListener('click', async () => {
    if (!navigator.geolocation) { gstat.textContent = 'This browser has no GPS support.'; return; }
    if (!window.isSecureContext) { gstat.textContent = 'GPS needs a secure (https) connection.'; return; }
    fixes = [];
    endAt = Date.now() + (parseInt($('gps-seconds').value, 10) || 30) * 1000;
    startBtn.disabled = true;
    stopBtn.hidden = false;
    try { if (navigator.wakeLock) wake = await navigator.wakeLock.request('screen'); } catch (e) { /* optional */ }
    watchId = navigator.geolocation.watchPosition(onFix, onError,
      { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
    ticker = setInterval(refreshStatus, 500);
    refreshStatus();
  });
  stopBtn.addEventListener('click', finish);

  // ---------- Map: show the captured pin, drag an adjusted pin ----------
  const A = { lat: $('adj_lat'), lon: $('adj_lon') };
  let map = null, origMk = null, adjMk = null;

  function ensureMap(lat, lon) {
    if (typeof L === 'undefined') return false;
    if (!map) {
      $('map').hidden = false;
      map = L.map('map').setView([lat, lon], 18);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    }
    return true;
  }

  function showOriginal() {
    const lat = num(F.lat.value), lon = num(F.lon.value);
    if (lat === null || lon === null || !ensureMap(lat, lon)) return;
    if (origMk) origMk.setLatLng([lat, lon]);
    else origMk = L.circleMarker([lat, lon], { radius: 8, color: '#0b4a9e', fillOpacity: 0.7 })
                   .bindTooltip('Captured position').addTo(map);
    map.setView([lat, lon], map.getZoom());
  }

  function placeAdjusted(lat, lon) {
    if (!ensureMap(lat, lon)) return;
    if (adjMk) { adjMk.setLatLng([lat, lon]); return; }
    adjMk = L.marker([lat, lon], { draggable: true }).bindTooltip('Adjusted position').addTo(map);
    adjMk.on('dragend', () => {
      const p = adjMk.getLatLng();
      A.lat.value = p.lat.toFixed(7);
      A.lon.value = p.lng.toFixed(7);
    });
  }

  $('adj-start').addEventListener('click', () => {
    const lat = num(A.lat.value) ?? num(F.lat.value), lon = num(A.lon.value) ?? num(F.lon.value);
    if (lat === null || lon === null) { gstat.textContent = 'Capture or enter a position first.'; return; }
    A.lat.value = lat.toFixed(7);
    A.lon.value = lon.toFixed(7);
    showOriginal();
    placeAdjusted(lat, lon);
  });
  $('adj-clear').addEventListener('click', () => {
    A.lat.value = A.lon.value = '';
    if (adjMk) { map.removeLayer(adjMk); adjMk = null; }
  });
  [F.lat, F.lon].forEach(el => el.addEventListener('change', showOriginal));
  [A.lat, A.lon].forEach(el => el.addEventListener('change', () => {
    const lat = num(A.lat.value), lon = num(A.lon.value);
    if (lat !== null && lon !== null) placeAdjusted(lat, lon);
  }));

  showOriginal();                                     // existing object: show its pins on load
  const al = num(A.lat.value), ao = num(A.lon.value);
  if (al !== null && ao !== null) placeAdjusted(al, ao);
})();
