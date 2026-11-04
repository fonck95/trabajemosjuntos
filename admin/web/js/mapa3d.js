// Motor de mapas: carga MapLibre (compilación CSP, sin blob:), mapas base, relieve, edificios 3D y hexágonos.
import { temaOscuro } from './app.js';
import { url } from './base.js';

const V = url('/static/vendor/maplibre-gl-5.24.0');
let promesa = null;

export function cargarMapLibre() {
  if (promesa) return promesa;
  promesa = new Promise((ok, mal) => {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = `${V}/maplibre-gl.css`;
    document.head.append(css);
    const s = document.createElement('script');
    s.src = `${V}/maplibre-gl-csp.js`;
    s.onload = () => {
      window.maplibregl.setWorkerUrl(`${V}/maplibre-gl-csp-worker.js`);
      ok(window.maplibregl);
    };
    s.onerror = () => mal(new Error('No se pudo cargar el motor de mapas'));
    document.head.append(s);
  });
  return promesa;
}

export const CASCO = { center: [-73.9112, 7.0062], zoom: 14.6, pitch: 58, bearing: -18 };
export const BBOX_YONDO = [[-74.35, 6.55], [-73.83, 7.35]];
// Rango de coordenadas que acepta el servidor para personas, lugares y reuniones ([[lon, lat] mín., [lon, lat] máx.])
export const RANGO_YONDO = [[-74.6, 6.3], [-73.6, 7.5]];
export const dentroDeYondo = (lon, lat) => lon >= RANGO_YONDO[0][0] && lon <= RANGO_YONDO[1][0] && lat >= RANGO_YONDO[0][1] && lat <= RANGO_YONDO[1][1];
// Máximo de personas que viajan en el enlace «Ver la lista» de un hexágono (el servidor tampoco acepta más)
export const MAX_IDS = 500;

const FUENTES = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf';
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const DEM = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';

export const BASES = {
  oscuro: 'https://tiles.openfreemap.org/styles/dark',
  claro: 'https://tiles.openfreemap.org/styles/positron',
  calles: 'https://tiles.openfreemap.org/styles/liberty',
  satelite: {
    version: 8,
    glyphs: FUENTES,
    sources: {
      sat: { type: 'raster', tiles: [ESRI], tileSize: 256, maxzoom: 19,
        attribution: 'Imágenes © Esri, Maxar, Earthstar Geographics' },
    },
    layers: [{ id: 'satelite', type: 'raster', source: 'sat', paint: { 'raster-saturation': -0.15, 'raster-contrast': 0.05 } }],
  },
};
export const baseSegunTema = () => (temaOscuro() ? 'oscuro' : 'claro');

/** Rampa secuencial de un solo tono (azul): en fondo oscuro lo denso es lo más claro. */
export function rampa(oscuro) {
  return oscuro
    ? ['#184f95', '#256abf', '#3987e5', '#6da7ec', '#b7d3f6']
    : ['#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'];
}

/** Agrega relieve, sombreado, cielo y edificios 3D al estilo cargado. */
export function decorar(map, { relieve = true, edificios = true, oscuro = temaOscuro() } = {}) {
  if (!map.getSource('dem')) {
    map.addSource('dem', { type: 'raster-dem', tiles: [DEM], encoding: 'terrarium', tileSize: 256, maxzoom: 14,
      attribution: 'Relieve: Mapzen Terrain Tiles (AWS)' });
    map.addSource('dem-sombra', { type: 'raster-dem', tiles: [DEM], encoding: 'terrarium', tileSize: 256, maxzoom: 14 });
  }
  const primeraEtiqueta = map.getStyle().layers.find((l) => l.type === 'symbol')?.id;
  if (!map.getLayer('sombreado')) {
    map.addLayer({ id: 'sombreado', type: 'hillshade', source: 'dem-sombra',
      paint: { 'hillshade-exaggeration': 0.45, 'hillshade-shadow-color': oscuro ? '#000' : '#5b5b52',
        'hillshade-highlight-color': oscuro ? '#2a2a2a' : '#fff', 'hillshade-accent-color': oscuro ? '#111' : '#777' } }, primeraEtiqueta);
  }
  map.setTerrain(relieve ? { source: 'dem', exaggeration: 1.7 } : null);
  try {
    map.setSky({ 'sky-color': oscuro ? '#0b1020' : '#bcd6f5', 'horizon-color': oscuro ? '#1b2235' : '#eef4fb',
      'fog-color': oscuro ? '#0d0d0d' : '#f2f2ef', 'sky-horizon-blend': 0.6, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.25 });
  } catch { /* versiones sin cielo */ }
  if (!map.getSource('ofm')) map.addSource('ofm', { type: 'vector', url: 'https://tiles.openfreemap.org/planet' });
  if (!map.getLayer('edificios-3d')) {
    map.addLayer({
      id: 'edificios-3d', type: 'fill-extrusion', source: 'ofm', 'source-layer': 'building', minzoom: 14,
      layout: { visibility: edificios ? 'visible' : 'none' },
      paint: {
        'fill-extrusion-color': oscuro ? '#2b2b2b' : '#d8d6cf',
        'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 5],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
        'fill-extrusion-opacity': 0.85,
      },
    });
  }
}

// ───────── Hexágonos (malla en metros de Mercator) ─────────
const R = 6378137;
const aM = (lon, lat) => [R * (lon * Math.PI) / 180, R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))];
const aG = (x, y) => [(x / R) * (180 / Math.PI), (2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) * (180 / Math.PI)];

/** Agrupa puntos [lon, lat, id, lugar] en hexágonos de `radio` metros. Devuelve un GeoJSON con n, t (0-1) y ids. */
export function hexagonos(puntos, radio) {
  const celdas = new Map();
  const r3 = Math.sqrt(3);
  for (const p of puntos) {
    const [x, y] = aM(p[0], p[1]);
    let q = ((r3 / 3) * x - y / 3) / radio, s = ((2 / 3) * y) / radio;
    let cx = q, cz = s, cy = -q - s;
    let rx = Math.round(cx), ry = Math.round(cy), rz = Math.round(cz);
    const dx = Math.abs(rx - cx), dy = Math.abs(ry - cy), dz = Math.abs(rz - cz);
    if (dx > dy && dx > dz) rx = -ry - rz; else if (dy > dz) ry = -rx - rz; else rz = -rx - ry;
    const clave = rx + ',' + rz;
    let c = celdas.get(clave);
    if (!c) celdas.set(clave, (c = { q: rx, r: rz, n: 0, ids: [], lugares: new Map() }));
    c.n++;
    c.ids.push(p[2]);
    if (p[3]) c.lugares.set(p[3], (c.lugares.get(p[3]) || 0) + 1);
  }
  const max = Math.max(1, ...[...celdas.values()].map((c) => c.n));
  const features = [];
  for (const c of celdas.values()) {
    const cx = radio * r3 * (c.q + c.r / 2), cy = radio * 1.5 * c.r;
    const anillo = [];
    for (let i = 0; i <= 6; i++) {
      const a = (Math.PI / 180) * (60 * i - 30);
      anillo.push(aG(cx + radio * 0.9 * Math.cos(a), cy + radio * 0.9 * Math.sin(a)));
    }
    const top = [...c.lugares.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
    features.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [anillo] },
      properties: { n: c.n, t: Math.sqrt(c.n / max), ids: c.ids.slice(0, MAX_IDS).join(','), lugares: JSON.stringify(top) } });
  }
  return { geo: { type: 'FeatureCollection', features }, max };
}

/** Desplazamiento visual determinista para puntos de barrio o vereda (no altera el dato guardado). */
const RADIO_DISPERSION = [0, 20, 110, 260, 700, 1200];
export function dispersar(id, lon, lat, codigoPrecision) {
  const rad = RADIO_DISPERSION[codigoPrecision] || 0;
  if (!rad) return [lon, lat];
  let h = (id * 2654435761) >>> 0;
  const u = (h & 0xffff) / 0xffff;
  h = Math.imul(h ^ (h >>> 15), 2246822519) >>> 0;
  const v = (h & 0xffff) / 0xffff;
  const dist = Math.sqrt(u) * rad, ang = v * Math.PI * 2;
  const dLat = (dist * Math.sin(ang)) / 111320;
  const dLon = (dist * Math.cos(ang)) / (111320 * Math.cos((lat * Math.PI) / 180));
  return [lon + dLon, lat + dLat];
}

export function cajaDe(geojson) {
  let w = 180, s = 90, e = -180, n = -90;
  const rec = (c) => {
    if (typeof c[0] === 'number') { w = Math.min(w, c[0]); e = Math.max(e, c[0]); s = Math.min(s, c[1]); n = Math.max(n, c[1]); }
    else c.forEach(rec);
  };
  for (const f of geojson.features || [geojson]) rec((f.geometry || f).coordinates);
  return [[w, s], [e, n]];
}
