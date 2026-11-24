// Shared GPS helpers (organizer capture and participant marking use the same method).
window.RallyGPS = (function () {
  'use strict';
  const median = a => {
    const s = a.slice().sort((x, y) => x - y), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };

  // Keep the best 60% of fixes by reported accuracy (at least 3), then take the median position.
  // fixes: [{lat, lon, acc}]. Returns lat, lon, median accuracy, RMS scatter in meters, fixes used.
  function summarize(list) {
    const best = list.slice().sort((a, b) => a.acc - b.acc)
                     .slice(0, Math.max(3, Math.ceil(list.length * 0.6)));
    const lat = median(best.map(f => f.lat)), lon = median(best.map(f => f.lon));
    const kx = 111320 * Math.cos(lat * Math.PI / 180), ky = 110540;
    const msq = best.reduce((t, f) => t + Math.pow((f.lon - lon) * kx, 2) + Math.pow((f.lat - lat) * ky, 2), 0) / best.length;
    return { lat: lat, lon: lon, acc: median(best.map(f => f.acc)), spread: Math.sqrt(msq), n: best.length };
  }

  return { median: median, summarize: summarize };
})();
