// Mapa 3D del municipio: relieve, edificios, columnas hexagonales 3D y mapa de calor de la población.
import { api } from '../api.js';
import { temaOscuro } from '../app.js';
import { BASES, BBOX_YONDO, CASCO, baseSegunTema, cajaDe, cargarMapLibre, decorar, dispersar, hexagonos, rampa } from '../mapa3d.js';
import { $, $$, esc, html, montar, num, pct, titulo } from '../ui.js';

const RADIOS = { auto: null, 150: 150, 400: 400, 1000: 1000 };
const PRECISIONES = ['Dirección exacta', 'Dirección aproximada', 'Barrio', 'Caserío / centro poblado', 'Vereda', 'Corregimiento'];

export async function vistaMapa(el, { q, ir }) {
  const estado = {
    base: null, capas: { calor: true, columnas: true, puntos: true, veredas: true, reuniones: true, edificios: true, relieve: true },
    radio: 'auto', filtros: Object.fromEntries([...q.entries()]), datos: null, capasGeo: null, cat: null, seleccion: null,
  };
  montar(el, html`
    <div class="mapa"><div id="mapa" style="width:100%;height:100%"></div></div>
    <div class="cargador-mapa" id="cargador"><div style="text-align:center"><div class="giro" style="margin:auto"></div><p class="sec">Levantando el municipio en 3D…</p></div></div>
    <aside class="panel-mapa izq" id="panel-izq">
      <h1>Mapa de la población</h1>
      <div style="display:flex;align-items:baseline;gap:10px;margin-top:12px">
        <span class="gran-cifra" id="cifra">—</span><span class="sec" id="cifra-d"></span>
      </div>
      <h3>Capas</h3>
      ${[['columnas', 'Columnas 3D por hexágono'], ['calor', 'Mapa de calor'], ['puntos', 'Personas (al acercarse)'], ['veredas', 'Veredas y lugares'],
         ['reuniones', 'Reuniones'], ['edificios', 'Edificios 3D'], ['relieve', 'Relieve del terreno']].map(([k, t]) =>
        html`<label class="interruptor"><span>${t}</span><input type="checkbox" data-capa="${k}" ${estado.capas[k] ? 'checked' : ''}></label>`)}
      <h3>Tamaño del hexágono</h3>
      <div class="segmentado" id="radios">${Object.keys(RADIOS).map((k) => html`<button data-radio="${k}" aria-pressed="${k === 'auto'}">${k === 'auto' ? 'Auto' : k >= 1000 ? k / 1000 + ' km' : k + ' m'}</button>`)}</div>
      <h3>Filtros</h3>
      <div style="display:flex;flex-direction:column;gap:8px">
        <select class="entrada" data-f="zona"><option value="">Todas las zonas</option><option value="urbana">Casco urbano</option><option value="rural">Rural</option></select>
        <select class="entrada" data-f="fuente"><option value="">Todas las fuentes</option><option value="tramites">Base de trámites</option><option value="cedulas">Base con cédula</option><option value="ambas">En las dos bases</option><option value="reunion">Registradas en reuniones</option></select>
        <select class="entrada" data-f="precision"><option value="">Toda precisión</option><option value="exacta">Solo dirección exacta</option><option value="aproximada">Solo aproximadas</option></select>
        <select class="entrada" data-f="asistio"><option value="">Con o sin reuniones</option><option value="1">Asistieron a reuniones</option><option value="0">Aún sin reunión</option></select>
        <select class="entrada" data-f="etiqueta" id="f-etiqueta"><option value="">Cualquier necesidad</option></select>
        <select class="entrada" data-f="lista" id="f-lista"><option value="">Cualquier lista</option></select>
      </div>
      <h3>Mapa base</h3>
      <div class="segmentado" id="bases">${[['auto', 'Tema'], ['oscuro', 'Oscuro'], ['claro', 'Claro'], ['satelite', 'Satélite']].map(([k, t]) => html`<button data-base="${k}" aria-pressed="${k === 'auto'}">${t}</button>`)}</div>
    </aside>
    <aside class="panel-mapa der" id="panel-der">
      <h3 style="margin-top:0">En pantalla</h3>
      <div id="en-vista"></div>
      <div id="detalle"></div>
    </aside>
    <div class="panel-mapa abajo">
      <button class="btn fantasma chico" data-vista="municipio">Municipio</button>
      <button class="btn fantasma chico" data-vista="casco">Casco urbano</button>
      <button class="btn fantasma chico" data-vista="tigre">San Miguel del Tigre</button>
      <button class="btn fantasma chico" data-vista="girar" aria-pressed="false">Girar</button>
      <div style="padding:2px 10px;min-width:280px">
        <div class="rampa" id="rampa"></div><div class="rampa-et"><span>Menos</span><span>Más personas por hexágono</span></div>
      </div>
    </div>`);

  const [maplibregl, cat] = await Promise.all([cargarMapLibre(), api.get('/api/catalogos')]);
  estado.cat = cat;
  $('#f-etiqueta').append(...cat.etiquetas.map((e) => new Option(`${e.nombre} (${e.n})`, e.id)));
  $('#f-lista').append(...cat.listas.map((l) => new Option(l, l)));
  for (const s of $$('[data-f]', el)) s.value = estado.filtros[s.dataset.f] || '';

  const map = new maplibregl.Map({
    container: $('#mapa'), style: BASES[baseSegunTema()], bounds: BBOX_YONDO, fitBoundsOptions: { padding: 40 },
    pitch: 50, bearing: -15, maxPitch: 80, attributionControl: { compact: true }, hash: false,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  let girando = false, rafGiro = 0;
  const popup = new maplibregl.Popup({ closeButton: true, maxWidth: '280px' });

  function radioActual() {
    if (RADIOS[estado.radio]) return RADIOS[estado.radio];
    const z = map.getZoom();
    return z >= 15 ? 90 : z >= 13.5 ? 180 : z >= 12 ? 450 : z >= 10.5 ? 1100 : 2200;
  }

  function puntosVisibles() {
    return (estado.datos?.puntos || []).map((p) => {
      const [lon, lat] = dispersar(p[0], p[2], p[1], p[3]);
      return [lon, lat, p[0], p[5], p[3], p[4], p[6], p[7]];
    });
  }

  function geoPuntos(pts) {
    return { type: 'FeatureCollection', features: pts.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p[0], p[1]] },
      properties: { id: p[2], p: p[4], r: p[6] } })) };
  }

  let ultimoMax = 1;
  function actualizarHex() {
    if (!map.getSource('hex')) return;
    const { geo, max } = hexagonos(puntosVisibles(), radioActual());
    ultimoMax = max;
    map.getSource('hex').setData(geo);
    const radio = radioActual();
    map.setPaintProperty('hex-3d', 'fill-extrusion-height', ['*', ['get', 't'], Math.min(2600, radio * 3.4)]);
  }

  function pintarRampa() {
    const r = rampa(temaOscuro() || estado.base === 'oscuro' || estado.base === 'satelite');
    $('#rampa').style.background = `linear-gradient(90deg, ${r.join(',')})`;
  }

  function agregarCapas() {
    const oscuro = estado.base === 'satelite' || (estado.base || baseSegunTema()) === 'oscuro';
    const r = rampa(oscuro);
    decorar(map, { relieve: estado.capas.relieve, edificios: estado.capas.edificios, oscuro });
    const cg = estado.capasGeo;
    if (cg?.limite && !map.getSource('limite')) {
      map.addSource('limite', { type: 'geojson', data: cg.limite });
      map.addLayer({ id: 'limite-halo', type: 'line', source: 'limite', paint: { 'line-color': '#e3141b', 'line-width': 9, 'line-opacity': 0.18, 'line-blur': 6 } });
      map.addLayer({ id: 'limite', type: 'line', source: 'limite', paint: { 'line-color': '#e3141b', 'line-width': 2.2, 'line-dasharray': [3, 1.5] } });
    }
    if (cg && !map.getSource('veredas')) {
      map.addSource('veredas', { type: 'geojson', data: cg.veredas });
      map.addLayer({ id: 'veredas-relleno', type: 'fill', source: 'veredas', paint: {
        'fill-color': ['interpolate', ['linear'], ['get', 'n'], 0, r[0], 20, r[2], 200, r[4]], 'fill-opacity': 0.12 } });
      map.addLayer({ id: 'veredas-borde', type: 'line', source: 'veredas', paint: { 'line-color': oscuro ? '#8a8a84' : '#55554f', 'line-width': 0.8, 'line-opacity': 0.6 } });
      map.addSource('lugares', { type: 'geojson', data: cg.lugares });
      map.addLayer({ id: 'lugares-nombre', type: 'symbol', source: 'lugares', filter: ['>', ['get', 'n'], 0], layout: {
        'text-field': ['get', 'nombre'], 'text-font': ['Noto Sans Bold'], 'text-size': ['interpolate', ['linear'], ['get', 'n'], 1, 10, 400, 14],
        'text-transform': 'uppercase', 'text-letter-spacing': 0.04, 'text-max-width': 8, 'symbol-sort-key': ['-', 0, ['get', 'n']],
        'text-variable-anchor': ['top', 'bottom', 'left', 'right'], 'text-radial-offset': 0.6 },
        paint: { 'text-color': oscuro ? '#f3f3f0' : '#111', 'text-halo-color': oscuro ? 'rgba(0,0,0,.85)' : 'rgba(255,255,255,.9)', 'text-halo-width': 1.6 } });
    }
    if (!map.getSource('hex')) {
      map.addSource('hex', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'hex-3d', type: 'fill-extrusion', source: 'hex', paint: {
        'fill-extrusion-color': ['interpolate', ['linear'], ['get', 't'], 0, r[0], 0.25, r[1], 0.5, r[2], 0.75, r[3], 1, r[4]],
        'fill-extrusion-height': ['*', ['get', 't'], 1000], 'fill-extrusion-opacity': 0.88, 'fill-extrusion-vertical-gradient': true } });
      map.addSource('puntos', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'calor', type: 'heatmap', source: 'puntos', maxzoom: 17, paint: {
        'heatmap-weight': 1,
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, 0.6, 15, 1.6],
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 6, 12, 14, 15, 26, 17, 40],
        'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(0,0,0,0)', 0.15, '#2a78d6', 0.35, '#1baf7a', 0.55, '#eda100', 0.8, '#eb6834', 1, '#e3141b'],
        'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0.85, 17, 0.35] } });
      map.addLayer({ id: 'puntos', type: 'circle', source: 'puntos', minzoom: 13.5, paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 13.5, 2.2, 17, 6],
        'circle-color': ['case', ['<=', ['get', 'p'], 1], '#e3141b', ['>', ['get', 'r'], 0], '#eda100', oscuro ? '#cfcfc8' : '#3d3d3a'],
        'circle-stroke-color': oscuro ? '#111' : '#fff', 'circle-stroke-width': 1, 'circle-opacity': 0.9 } });
    }
    if (cg && !map.getSource('reuniones')) {
      map.addSource('reuniones', { type: 'geojson', data: cg.reuniones });
      map.addLayer({ id: 'reuniones', type: 'circle', source: 'reuniones', paint: {
        'circle-radius': 9, 'circle-color': '#e3141b', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2.5 } });
      map.addLayer({ id: 'reuniones-n', type: 'symbol', source: 'reuniones', layout: { 'text-field': ['to-string', ['get', 'n']],
        'text-font': ['Noto Sans Bold'], 'text-size': 10, 'text-allow-overlap': true }, paint: { 'text-color': '#fff' } });
    }
    aplicarVisibilidad();
    if (estado.datos) {
      map.getSource('puntos').setData(geoPuntos(puntosVisibles()));
      actualizarHex();
    }
    pintarRampa();
  }

  function aplicarVisibilidad() {
    const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    vis('hex-3d', estado.capas.columnas);
    vis('calor', estado.capas.calor);
    vis('puntos', estado.capas.puntos);
    ['veredas-relleno', 'veredas-borde', 'lugares-nombre'].forEach((id) => vis(id, estado.capas.veredas));
    ['reuniones', 'reuniones-n'].forEach((id) => vis(id, estado.capas.reuniones));
    vis('edificios-3d', estado.capas.edificios);
    if (map.getSource('dem')) map.setTerrain(estado.capas.relieve ? { source: 'dem', exaggeration: 1.7 } : null);
  }

  async function cargarDatos() {
    const d = await api.get('/api/mapa/puntos', estado.filtros);
    estado.datos = d;
    $('#cifra').textContent = num(d.ubicadas);
    $('#cifra-d').textContent = `ubicadas de ${num(d.total)} (${pct(d.ubicadas, d.total)} %)`;
    if (map.getSource('puntos')) {
      map.getSource('puntos').setData(geoPuntos(puntosVisibles()));
      actualizarHex();
    }
    resumenVista();
  }

  const nombreLugar = (id) => {
    const f = estado.capasGeo?.lugares.features.find((x) => x.properties.id === id) || estado.cat.lugares.find((l) => l.id === id);
    return f ? titulo((f.properties || f).nombre) : 'Sin barrio o vereda';
  };

  function resumenVista() {
    if (!estado.datos) return;
    const b = map.getBounds();
    const dentro = estado.datos.puntos.filter((p) => b.contains([p[2], p[1]]));
    const porLugar = new Map();
    let exactas = 0;
    for (const p of dentro) {
      porLugar.set(p[5], (porLugar.get(p[5]) || 0) + 1);
      if (p[3] === 0) exactas++;
    }
    const top = [...porLugar.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
    montar($('#en-vista'), html`<div class="gran-cifra" style="font-size:30px">${num(dentro.length)}</div>
      <div class="sec">personas · ${pct(exactas, dentro.length)} % con dirección exacta</div>
      <div class="lista-barras" style="margin-top:12px">${top.map(([id, n]) => html`<a class="f" href="/personas?lugar_id=${id || ''}" data-ruta><span>${nombreLugar(id)}</span>
        <span><span class="b" style="width:${(n / (top[0]?.[1] || 1)) * 100}%"></span></span><span class="n">${num(n)}</span></a>`)}</div>`);
  }

  function mostrarHex(props, lngLat) {
    const lugares = JSON.parse(props.lugares || '[]');
    const ids = props.ids;
    montar($('#detalle'), html`<h3>Hexágono seleccionado</h3>
      <div class="gran-cifra" style="font-size:30px">${num(props.n)}</div><div class="sec">personas en ~${radioActual() * 2} m de ancho</div>
      <div class="lista-barras" style="margin-top:10px">${lugares.map(([id, n]) => html`<div class="f"><span>${nombreLugar(id)}</span><span></span><span class="n">${num(n)}</span></div>`)}</div>
      <a class="btn chico" style="margin-top:12px" href="/personas?ids=${ids}" data-ruta>Ver la lista</a>`);
    popup.setLngLat(lngLat).setHTML(`<b>${esc(num(props.n))} personas</b><br><span class="sec">${esc(lugares.map(([id]) => nombreLugar(id)).join(', '))}</span>`).addTo(map);
  }

  map.on('style.load', agregarCapas);
  map.on('load', async () => {
    estado.capasGeo = await api.get('/api/mapa/capas');
    agregarCapas();
    await cargarDatos();
    $('#cargador').style.opacity = 0;
    setTimeout(() => $('#cargador')?.remove(), 450);
    if (estado.capasGeo.limite) map.fitBounds(cajaDe(estado.capasGeo.limite), { padding: 50, pitch: 52, bearing: -15, duration: 0 });
    setTimeout(() => map.flyTo({ ...CASCO, zoom: 13.2, pitch: 60, duration: 4200, essential: true }), 900);
  });
  let zPrev = 0;
  map.on('moveend', () => {
    resumenVista();
    const z = Math.round(map.getZoom() * 2);
    if (estado.radio === 'auto' && z !== zPrev) { zPrev = z; actualizarHex(); }
  });
  map.on('click', 'hex-3d', (e) => {
    if (map.queryRenderedFeatures(e.point, { layers: ['puntos', 'reuniones'].filter((l) => map.getLayer(l)) }).length) return;
    mostrarHex(e.features[0].properties, e.lngLat);
  });
  map.on('click', 'puntos', async (e) => {
    const id = e.features[0].properties.id;
    const p = await api.get(`/api/personas/${id}`);
    popup.setLngLat(e.lngLat).setHTML(`<b>${esc(p.nombre)}</b><br><span class="sec">${esc(p.direccion_norm || p.direccion || 'Sin dirección')}</span>
      <br><span class="sec">Completitud ${esc(p.completitud)} %</span><br><a href="/personas/${id}" data-ruta>Abrir ficha →</a>`).addTo(map);
  });
  map.on('click', 'reuniones', (e) => {
    const r = e.features[0].properties;
    popup.setLngLat(e.lngLat).setHTML(`<b>${esc(r.titulo)}</b><br><span class="sec">${esc(r.fecha)} · ${esc(r.n)} asistentes</span><br><a href="/reuniones/${r.id}" data-ruta>Abrir →</a>`).addTo(map);
  });
  for (const l of ['hex-3d', 'puntos', 'reuniones']) {
    map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'));
    map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
  }

  // Controles
  el.addEventListener('change', async (e) => {
    const c = e.target.closest('[data-capa]');
    if (c) { estado.capas[c.dataset.capa] = c.checked; aplicarVisibilidad(); return; }
    const f = e.target.closest('[data-f]');
    if (f) {
      if (f.value) estado.filtros[f.dataset.f] = f.value; else delete estado.filtros[f.dataset.f];
      history.replaceState({}, '', '/mapa?' + new URLSearchParams(estado.filtros));
      await cargarDatos();
    }
  });
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-radio]');
    if (b) {
      estado.radio = b.dataset.radio;
      $$('[data-radio]', el).forEach((x) => x.setAttribute('aria-pressed', x === b));
      actualizarHex();
      return;
    }
    const base = e.target.closest('[data-base]');
    if (base) {
      $$('[data-base]', el).forEach((x) => x.setAttribute('aria-pressed', x === base));
      estado.base = base.dataset.base === 'auto' ? null : base.dataset.base;
      map.setStyle(BASES[estado.base || baseSegunTema()], { diff: false });
      return;
    }
    const v = e.target.closest('[data-vista]');
    if (v) {
      const k = v.dataset.vista;
      if (k === 'municipio' && estado.capasGeo?.limite) map.fitBounds(cajaDe(estado.capasGeo.limite), { padding: 50, pitch: 50, bearing: -15, duration: 2500 });
      else if (k === 'casco') map.flyTo({ ...CASCO, duration: 2600 });
      else if (k === 'tigre') {
        const t = estado.capasGeo?.lugares.features.find((f) => f.properties.nombre.includes('SAN MIGUEL DEL TIGRE'));
        if (t) map.flyTo({ center: t.geometry.coordinates, zoom: 15, pitch: 60, bearing: 20, duration: 2600 });
      } else if (k === 'girar') {
        girando = !girando;
        v.setAttribute('aria-pressed', girando);
        const paso = () => { if (!girando) return; map.rotateTo(map.getBearing() + 0.08, { duration: 0 }); rafGiro = requestAnimationFrame(paso); };
        if (girando) paso(); else cancelAnimationFrame(rafGiro);
      }
    }
  });
  const alTema = () => { if (!estado.base) map.setStyle(BASES[baseSegunTema()], { diff: false }); };
  window.addEventListener('tema', alTema);
  window.__mapa = map; // útil para depurar desde la consola
  return () => { girando = false; cancelAnimationFrame(rafGiro); window.removeEventListener('tema', alTema); popup.remove(); map.remove(); delete window.__mapa; };
}
