/**
 * Astral Audio — main.js
 * Starfield animation, transit wheel, form interactions
 */

// ── STARFIELD ──────────────────────────────────────────────
(function initStarfield() {
  const canvas = document.getElementById('stars');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  const stars = Array.from({ length: 140 }, () => ({
    x:     Math.random(),
    y:     Math.random(),
    r:     Math.random() * 0.9 + 0.2,
    a:     Math.random() * Math.PI * 2,
    speed: Math.random() * 0.004 + 0.001,
  }));

  function drawStars() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    stars.forEach(s => {
      s.a += s.speed;
      const alpha = ((Math.sin(s.a) + 1) / 2) * 0.6 + 0.1;
      ctx.beginPath();
      ctx.arc(s.x * canvas.width, s.y * canvas.height, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(245,240,232,${alpha})`;
      ctx.fill();
    });
    requestAnimationFrame(drawStars);
  }
  drawStars();
})();


// ── NAV DATE ──────────────────────────────────────────────
(function setNavDate() {
  const el = document.getElementById('navDate');
  if (!el) return;
  const d = new Date();
  el.textContent = d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
  });
})();


// ── TRANSIT WHEEL (decorative synastry diagram) ────────────
(function buildTransitWheel() {
  const svg = document.getElementById('transit-wheel');
  if (!svg) return;

  const ns = 'http://www.w3.org/2000/svg';
  const cx = 130, cy = 130;

  const R_OUTER   = 118;
  const R_ZODIAC  = 104;
  const R_TRANSIT =  88;
  const R_DIVIDER =  72;
  const R_NATAL   =  56;
  const R_CENTER  =  32;

  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    return e;
  }

  function polar(deg, r) {
    const rad = (deg - 90) * Math.PI / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  }

  // Rings
  svg.appendChild(el('circle', { cx, cy, r: R_OUTER,   fill: 'none', stroke: 'rgba(200,168,75,0.3)',   'stroke-width': '1'   }));
  svg.appendChild(el('circle', { cx, cy, r: R_ZODIAC,  fill: 'none', stroke: 'rgba(200,168,75,0.15)',  'stroke-width': '0.5' }));
  svg.appendChild(el('circle', { cx, cy, r: R_DIVIDER, fill: 'rgba(255,255,255,0.02)', stroke: 'rgba(255,255,255,0.18)', 'stroke-width': '1' }));
  svg.appendChild(el('circle', { cx, cy, r: R_CENTER,  fill: 'rgba(14,12,20,0.8)',    stroke: 'rgba(200,168,75,0.2)',   'stroke-width': '0.5' }));

  // Zodiac dividers + minor ticks
  for (let i = 0; i < 12; i++) {
    const deg = i * 30;
    const [x1, y1] = polar(deg, R_OUTER);
    const [x2, y2] = polar(deg, R_ZODIAC);
    svg.appendChild(el('line', { x1, y1, x2, y2, stroke: 'rgba(200,168,75,0.35)', 'stroke-width': '1' }));
  }
  for (let i = 0; i < 36; i++) {
    const deg = i * 10;
    const [x1, y1] = polar(deg, R_OUTER);
    const [x2, y2] = polar(deg, R_OUTER - 4);
    svg.appendChild(el('line', { x1, y1, x2, y2, stroke: 'rgba(255,255,255,0.12)', 'stroke-width': '0.5' }));
  }

  // Zodiac glyphs
  const zodiac = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓'];
  zodiac.forEach((glyph, i) => {
    const [x, y] = polar(i * 30 + 15, (R_OUTER + R_ZODIAC) / 2);
    const t = el('text', { x, y, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
      fill: 'rgba(200,168,75,0.5)', 'font-size': '8', 'font-family': 'serif' });
    t.textContent = glyph;
    svg.appendChild(t);
  });

  // Ring labels
  const tLabel = el('text', { x: cx, y: cy - R_DIVIDER + 10, 'text-anchor': 'middle',
    fill: 'rgba(122,179,200,0.5)', 'font-size': '5.5', 'font-family': 'DM Mono, monospace', 'letter-spacing': '2' });
  tLabel.textContent = 'TRANSITS';
  svg.appendChild(tLabel);

  const nLabel = el('text', { x: cx, y: cy - R_CENTER - 6, 'text-anchor': 'middle',
    fill: 'rgba(200,168,75,0.4)', 'font-size': '5.5', 'font-family': 'DM Mono, monospace', 'letter-spacing': '2' });
  nLabel.textContent = 'NATAL';
  svg.appendChild(nLabel);

  // Planet data — decorative positions representing archetypal sky
  const natal = [
    { glyph: '☉', deg:  14, color: '#c8a84b' },
    { glyph: '☽', deg: 224, color: '#e8d9a8' },
    { glyph: '☿', deg:  28, color: '#aaaaaa' },
    { glyph: '♀', deg: 188, color: '#c47a8a' },
    { glyph: '♂', deg: 112, color: '#b85c38' },
    { glyph: '♄', deg: 258, color: '#7ab3c8' },
  ];

  const transits = [
    { glyph: '☽', deg:  48, color: '#e8d9a8' },
    { glyph: '☿', deg: 142, color: '#aaaaaa' },
    { glyph: '♀', deg: 203, color: '#c47a8a' },
    { glyph: '♂', deg: 310, color: '#b85c38' },
    { glyph: '♄', deg: 322, color: '#7ab3c8' },
    { glyph: '♆', deg:  30, color: '#7ab3c8' },
    { glyph: '♅', deg: 288, color: '#d4924a' },
  ];

  // Aspect lines
  const aspectLines = [
    { natalDeg: 224, transitDeg:  48, color: 'rgba(122,179,200,0.6)',  dash: ''    },
    { natalDeg:  14, transitDeg: 142, color: 'rgba(196,122,138,0.55)', dash: ''    },
    { natalDeg: 112, transitDeg: 288, color: 'rgba(212,146,74,0.5)',   dash: '3,3' },
    { natalDeg: 258, transitDeg:  30, color: 'rgba(232,217,168,0.45)', dash: ''    },
  ];

  aspectLines.forEach(a => {
    const [x1, y1] = polar(a.natalDeg,   R_NATAL - 4);
    const [x2, y2] = polar(a.transitDeg, R_TRANSIT + 4);
    svg.appendChild(el('line', { x1, y1, x2, y2, stroke: a.color, 'stroke-width': '1',
      'stroke-dasharray': a.dash }));
  });

  // Transit planets
  transits.forEach(p => {
    const [x, y] = polar(p.deg, R_TRANSIT);
    const [tx1, ty1] = polar(p.deg, R_ZODIAC);
    const [tx2, ty2] = polar(p.deg, R_ZODIAC - 6);
    svg.appendChild(el('line', { x1: tx1, y1: ty1, x2: tx2, y2: ty2,
      stroke: p.color, 'stroke-width': '0.8', opacity: '0.4' }));
    svg.appendChild(el('circle', { cx: x, cy: y, r: 3, fill: p.color, opacity: '0.9' }));
    const [gx, gy] = polar(p.deg, R_TRANSIT + 11);
    const t = el('text', { x: gx, y: gy, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
      fill: p.color, 'font-size': '9', 'font-family': 'serif', opacity: '0.8' });
    t.textContent = p.glyph;
    svg.appendChild(t);
  });

  // Natal planets
  natal.forEach(p => {
    const [x, y] = polar(p.deg, R_NATAL);
    const [tx1, ty1] = polar(p.deg, R_DIVIDER - 1);
    const [tx2, ty2] = polar(p.deg, R_DIVIDER - 7);
    svg.appendChild(el('line', { x1: tx1, y1: ty1, x2: tx2, y2: ty2,
      stroke: p.color, 'stroke-width': '0.8', opacity: '0.5' }));
    svg.appendChild(el('circle', { cx: x, cy: y, r: 3.5, fill: 'none',
      stroke: p.color, 'stroke-width': '1.5', opacity: '0.95' }));
    const [gx, gy] = polar(p.deg, R_NATAL - 12);
    const t = el('text', { x: gx, y: gy, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
      fill: p.color, 'font-size': '9', 'font-family': 'serif', opacity: '0.75' });
    t.textContent = p.glyph;
    svg.appendChild(t);
  });

  // Center date
  const now = new Date();
  const dateStr = `${String(now.getMonth() + 1).padStart(2,'0')}.${String(now.getDate()).padStart(2,'0')}.${String(now.getFullYear()).slice(2)}`;
  const cl = el('text', { x: cx, y: cy + 4, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
    fill: 'rgba(200,168,75,0.35)', 'font-size': '6', 'font-family': 'DM Mono, monospace', 'letter-spacing': '1' });
  cl.textContent = dateStr;
  svg.appendChild(cl);
})();


// ── LIBRARY TOGGLE ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const optPool   = document.getElementById('optPool');
  const optUpload = document.getElementById('optUpload');
  const panelPool   = document.getElementById('panelPool');
  const panelUpload = document.getElementById('panelUpload');
  const choiceInput = document.getElementById('library_choice');

  if (!optPool) return; // not on index page

  function selectLibrary(choice) {
    choiceInput.value = choice;
    if (choice === 'pool') {
      optPool.classList.add('library-option-active');
      optUpload.classList.remove('library-option-active');
      panelPool.style.display   = 'block';
      panelUpload.style.display = 'none';
    } else {
      optUpload.classList.add('library-option-active');
      optPool.classList.remove('library-option-active');
      panelUpload.style.display = 'block';
      panelPool.style.display   = 'none';
    }
  }

  optPool.addEventListener('click',   () => selectLibrary('pool'));
  optUpload.addEventListener('click', () => selectLibrary('upload'));

  // File upload label
  document.getElementById('liked_songs_csv')?.addEventListener('change', function () {
    const label = document.getElementById('uploadPrimary');
    label.textContent = this.files.length > 0 ? this.files[0].name : 'Drop CSV here or click to browse';
    document.getElementById('uploadArea').classList.toggle('upload-area-filled', this.files.length > 0);
  });
});


// ── FORM SUBMIT + GEOCODE FALLBACK ─────────────────────────
window.initPlaces = function () {
  setupLocationField('birth_location_text',   'birth_lat',   'birth_lng',   'birth_tz',   'birth_location_status');
  setupLocationField('current_location_text', 'current_lat', 'current_lng', 'current_tz', 'current_location_status');
};

function setupLocationField(inputId, latId, lngId, tzId, statusId) {
  const input = document.getElementById(inputId);
  if (!input || typeof google === 'undefined') return;

  const ac = new google.maps.places.Autocomplete(input, {
    types: ['(regions)'],
    fields: ['geometry', 'formatted_address', 'name'],
  });

  ac.addListener('place_changed', async () => {
    const place = ac.getPlace();
    if (!place.geometry) return;

    const lat = place.geometry.location.lat();
    const lng = place.geometry.location.lng();

    document.getElementById(latId).value = lat;
    document.getElementById(lngId).value = lng;

    const status = document.getElementById(statusId);
    status.textContent = 'Resolving timezone…';

    try {
      const tz = await fetchTimezone(lat, lng);
      document.getElementById(tzId).value = tz;
      status.textContent = `✓ ${place.name} · ${tz}`;
    } catch {
      status.textContent = 'Could not resolve timezone';
    }
  });
}

async function fetchTimezone(lat, lng) {
  const res = await fetch(`/api/timezone?lat=${lat}&lng=${lng}`);
  if (!res.ok) throw new Error('Timezone API failed');
  const data = await res.json();
  return data.timezone || 'UTC';
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('birthForm');
  if (!form) return;

  const hasMapsKey = typeof window.GOOGLE_MAPS_KEY !== 'undefined';

  form.addEventListener('submit', async (e) => {
    const birthLat   = document.getElementById('birth_lat');
    const currentLat = document.getElementById('current_lat');

    if (!hasMapsKey) {
      if (!birthLat?.value || !currentLat?.value) {
        e.preventDefault();
        await geocodeFallback();
        if (birthLat?.value && currentLat?.value) form.submit();
      }
    } else {
      if (!birthLat?.value) {
        e.preventDefault();
        document.getElementById('birth_location_status').textContent = 'Please select a location from the dropdown';
        return;
      }
      if (!currentLat?.value) {
        e.preventDefault();
        document.getElementById('current_location_status').textContent = 'Please select a location from the dropdown';
        return;
      }
    }

    // loading state
    const btn = document.getElementById('submitBtn');
    if (btn) {
      btn.disabled = true;
      const txt = btn.querySelector('.btn-text');
      if (txt) txt.textContent = 'Reading the stars…';
    }
  });
});

async function geocodeFallback() {
  const birthText   = document.getElementById('birth_location_text')?.value;
  const currentText = document.getElementById('current_location_text')?.value;
  if (!birthText || !currentText) return;

  try {
    const [b, c] = await Promise.all([geocodeCity(birthText), geocodeCity(currentText)]);
    if (b) {
      document.getElementById('birth_lat').value = b.lat;
      document.getElementById('birth_lng').value = b.lng;
      document.getElementById('birth_tz').value  = b.tz;
      document.getElementById('birth_location_status').textContent = `✓ ${b.tz}`;
    }
    if (c) {
      document.getElementById('current_lat').value = c.lat;
      document.getElementById('current_lng').value = c.lng;
      document.getElementById('current_tz').value  = c.tz;
      document.getElementById('current_location_status').textContent = `✓ ${c.tz}`;
    }
  } catch (err) {
    console.error('Geocode fallback failed', err);
  }
}

async function geocodeCity(cityName) {
  const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(cityName)}&format=json&limit=1`;
  const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
  if (!res.ok) return null;
  const data = await res.json();
  if (!data.length) return null;

  const { lat, lon } = data[0];
  const tzRes = await fetch(`/api/timezone?lat=${lat}&lng=${lon}`);
  const tzData = await tzRes.json();
  return { lat: parseFloat(lat), lng: parseFloat(lon), tz: tzData.timezone || 'UTC' };
}
