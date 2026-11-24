(function () {
  'use strict';
  const el = document.getElementById('map-data');
  if (!el || typeof L === 'undefined') return;
  const d = JSON.parse(el.textContent);
  const map = L.map('map');
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);

  const ref = [d.ref.lat, d.ref.lon], pts = [ref];
  if (d.orig) {
    L.circleMarker([d.orig.lat, d.orig.lon], { radius: 8, color: '#0b4a9e', fillOpacity: 0.1, dashArray: '3 3' })
      .bindTooltip('Original capture').addTo(map);
    pts.push([d.orig.lat, d.orig.lon]);
  }
  L.marker(ref).bindTooltip(d.adjusted ? 'Scoring pin (adjusted)' : 'Organizer pin').addTo(map);
  if (d.suggested) {
    const s = [d.suggested.lat, d.suggested.lon];
    L.circleMarker(s, { radius: 11, color: '#d97706', fill: false, weight: 3 })
      .bindTooltip('Median of marks').addTo(map);
    pts.push(s);
  }
  d.marks.forEach(m => {
    const color = m.capped ? '#b00020' : '#0f6b4b', p = [m.lat, m.lon];
    L.polyline([ref, p], { color: color, weight: 2, opacity: 0.6 }).addTo(map);
    L.circleMarker(p, { radius: 5, color: color, fillOpacity: 0.8 })
      .bindTooltip(m.team + ': ' + m.err + ' m').addTo(map);
    pts.push(p);
  });
  if (pts.length > 1) map.fitBounds(L.latLngBounds(pts).pad(0.2), { maxZoom: 19 });
  else map.setView(ref, 18);
})();
