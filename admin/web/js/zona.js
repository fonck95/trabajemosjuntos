// Zonas del mapa (6): dibujar con ratón o con el dedo un polígono exacto, moverlo, medirlo y codificarlo para la URL.
//
// * La geometría es la de app/geometria.py: área esférica de Turf y d3 (radio 6 378 137 m), perímetro haversine
//   (6 371 008,8 m) y cruces sobre millonésimas de grado. tests/test_areas.py compara los dos con Node; por eso este
//   módulo no importa nada ni toca el documento al cargarse.
// * Dibujo: «Mira» (retícula fija al centro y «+ Punto», para el dedo: el mapa se arrastra normal), «Por puntos» (clic o
//   toque; se cierra tocando el primero, con «Terminar», doble clic, doble toque o Enter) y «Lazo» (un trazo libre que se
//   simplifica a 100 vértices o menos). Edición: arrastrar vértices, «+» en cada lado, tocar un vértice para quitarlo
//   y «Deshacer» (también Retroceso o Ctrl+Z). Esc cancela el dibujo.

const R_AREA = 6378137, R_PERIMETRO = 6371008.8, K = Math.PI / 180;
export const MIN_VERTICES = 3;
export const MAX_VERTICES = 150;
export const AREA_MIN = 100;
export const AREA_MAX = 4000e6;
export const MAX_LAZO = 100;
// Paleta fija de las zonas guardadas (la misma de app/api/zonas.py). El rojo queda para «los lados se cruzan»
export const PALETA = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#3d3d3a'];
const ROJO = '#e3141b';

// ───────── Geometría (gemela de app/geometria.py) ─────────
const igual = (a, b) => a[0] === b[0] && a[1] === b[1];
function abierto(anillo) {
  const a = [...anillo];
  while (a.length > 1 && igual(a[0], a[a.length - 1])) a.pop();
  return a;
}

/** Área en m² (esférica, como Turf y d3). */
export const areaM2 = (anillo) => {
  const a = abierto(anillo);
  return Math.abs(a.reduce((s, [l1, f1], i) => {
    const [l2, f2] = a[(i + 1) % a.length];
    return s + (l2 - l1) * K * (2 + Math.sin(f1 * K) + Math.sin(f2 * K));
  }, 0) * R_AREA * R_AREA / 2);
};

function haversine([l1, f1], [l2, f2]) {
  const h = Math.sin((f2 - f1) * K / 2) ** 2 + Math.cos(f1 * K) * Math.cos(f2 * K) * Math.sin((l2 - l1) * K / 2) ** 2;
  return 2 * R_PERIMETRO * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Perímetro en metros (haversine), con el lado que cierra el anillo. */
export function perimetroM(anillo) {
  const a = abierto(anillo);
  if (a.length < 2) return 0;
  let s = 0;
  for (let i = 0; i < a.length; i++) s += haversine(a[i], a[(i + 1) % a.length]);
  return s;
}

/** ¿El punto [lon, lat] cae dentro del anillo? (aristas planas; el conteo oficial es el del servidor). */
export function dentro([x, y], anillo) {
  let d = false;
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
    const [xi, yi] = anillo[i], [xj, yj] = anillo[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d;
  }
  return d;
}

const orientacion = (a, b, c) => {
  const v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  return (v > 0) - (v < 0);
};
const sobre = (a, b, c) => Math.min(a[0], b[0]) <= c[0] && c[0] <= Math.max(a[0], b[0])
  && Math.min(a[1], b[1]) <= c[1] && c[1] <= Math.max(a[1], b[1]);
function seTocan(p1, p2, p3, p4) {
  const o1 = orientacion(p1, p2, p3), o2 = orientacion(p1, p2, p4), o3 = orientacion(p3, p4, p1), o4 = orientacion(p3, p4, p2);
  if (o1 !== o2 && o3 !== o4) return true;
  return (o1 === 0 && sobre(p1, p2, p3)) || (o2 === 0 && sobre(p1, p2, p4)) || (o3 === 0 && sobre(p3, p4, p1)) || (o4 === 0 && sobre(p3, p4, p2));
}

/** ¿Algún par de lados se cruza o se toca (fuera del vértice que comparten dos lados seguidos)? */
export function seCruza(anillo) {
  const a = abierto(anillo).map(([lon, lat]) => [Math.round(lon * 1e6), Math.round(lat * 1e6)]);
  const n = a.length;
  if (n < 3) return false;
  const lados = a.map((p, i) => [p, a[(i + 1) % n]]);
  for (let i = 0; i < n; i++) {
    const [p1, p2] = lados[i];
    for (let j = i + 1; j < n; j++) {
      const [p3, p4] = lados[j];
      if (j === i + 1 || (i === 0 && j === n - 1)) {
        // Seguidos: comparten un vértice. Se cruzan solo si vuelven sobre sí mismos (alineados y superpuestos)
        const [comun, x, y] = j === i + 1 ? [p2, p1, p4] : [p1, p2, p3];
        if (orientacion(x, comun, y) === 0 && (sobre(comun, x, y) || sobre(comun, y, x))) return true;
        continue;
      }
      if (seTocan(p1, p2, p3, p4)) return true;
    }
  }
  return false;
}

function distSegmento([x, y], [x1, y1], [x2, y2]) {
  const dx = x2 - x1, dy = y2 - y1, l = dx * dx + dy * dy;
  const t = l ? Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / l)) : 0;
  return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
}

/** Douglas-Peucker sobre puntos de pantalla [x, y] con tolerancia en píxeles. */
export function simplificar(puntos, tol) {
  if (puntos.length < 3) return puntos.slice();
  const marca = new Uint8Array(puntos.length);
  marca[0] = marca[puntos.length - 1] = 1;
  const pila = [[0, puntos.length - 1]];
  while (pila.length) {
    const [i, j] = pila.pop();
    let max = 0, k = -1;
    for (let m = i + 1; m < j; m++) {
      const d = distSegmento(puntos[m], puntos[i], puntos[j]);
      if (d > max) { max = d; k = m; }
    }
    if (max > tol) { marca[k] = 1; pila.push([i, k], [k, j]); }
  }
  return puntos.filter((_, i) => marca[i]);
}

const texto = (x) => {
  const s = x.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
  return s === '-0' || s === '' ? '0' : s;
};
/** «lon,lat;lon,lat;…» con 6 decimales como máximo (el parámetro `poligono` de la URL). */
export const codificar = (anillo) => abierto(anillo).map(([lon, lat]) => `${texto(lon)},${texto(lat)}`).join(';');

/** El anillo de un texto «lon,lat;…», o null si no se puede leer. */
export function decodificar(t) {
  if (typeof t !== 'string' || t.length > 4000) return null;
  const out = [];
  for (const par of t.split(';')) {
    if (!par.trim()) continue;
    const p = par.split(',');
    if (p.length !== 2 || !p.every((x) => /^\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/.test(x))) return null;
    out.push([Number(p[0]), Number(p[1])]);
  }
  return out;
}

const NUM = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 });
const ENTERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });
/** 850 m², 3,4 ha o 12,5 km². */
export const formatoArea = (m2) => (m2 < 10_000 ? `${ENTERO.format(m2)} m²` : m2 < 1e6 ? `${NUM.format(m2 / 1e4)} ha` : `${NUM.format(m2 / 1e6)} km²`);
export const formatoLargo = (m) => (m < 1000 ? `${ENTERO.format(m)} m` : `${NUM.format(m / 1000)} km`);

// ───────── Estilos (como cargarMapLibre en mapa3d.js) ─────────
let estilos = null;
export function cargarEstilos() {
  if (estilos) return estilos;
  estilos = new Promise((ok) => {
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = new URL('../css/zona.css', import.meta.url).href;
    l.dataset.zona = '';
    l.onload = l.onerror = () => ok();
    document.head.append(l);
  });
  return estilos;
}

// ───────── Herramienta ─────────
const VACIO = { type: 'FeatureCollection', features: [] };
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** Toque o clic sobre un marcador: por eventos de puntero (un arrastre corto del mapa no lo dispara) y, para el teclado,
 * por `click`. El evento no llega al mapa: `stopPropagation` en `pointerdown` y en `click`. */
function alTocar(el, fn) {
  let ini = null, hecho = 0;
  el.addEventListener('pointerdown', (e) => { e.stopPropagation(); ini = { x: e.clientX, y: e.clientY, id: e.pointerId }; });
  el.addEventListener('pointerup', (e) => {
    if (ini && e.pointerId === ini.id && Math.hypot(e.clientX - ini.x, e.clientY - ini.y) < 8) { hecho = performance.now(); fn(); }
    ini = null;
  });
  el.addEventListener('pointercancel', () => { ini = null; });
  el.addEventListener('click', (e) => { e.stopPropagation(); if (performance.now() - hecho > 700) fn(); });
}

/**
 * Herramienta de dibujo sobre un mapa de MapLibre.
 * `alCambiar(info)` en cada cambio (a lo sumo una vez por cuadro); `alTerminar(info)` cuando el polígono queda cerrado
 * o cambia ya cerrado (al soltar, agregar o quitar un vértice, deshacer o cargar); `alCancelar()` al cancelar.
 * `dentro(lon, lat)` dice qué puntos se aceptan (los de Yondó).
 */
export function crearHerramientaZona(map, maplibregl, { alCambiar = () => {}, alTerminar = () => {}, alCancelar = () => {},
  dentro: enRango = () => true, color = PALETA[0] } = {}) {
  const contenedor = map.getCanvasContainer();
  const caja = map.getContainer();
  const envoltura = caja.closest('.mapa') || caja;
  const st = { fase: 'inactiva', modo: null, v: [], hist: [], agregados: [], cursor: null, color, armado: false,
    trazo: null, mensaje: '', cruza: false, arrastrado: false, bloqueada: false };
  let marcas = [], medios = [], quitarPopup = null, cuadro = 0, conectada = false, tipo = null, zoomDobleAntes = true;

  const mira = document.createElement('div');
  mira.className = 'zona-mira';
  mira.hidden = true;
  mira.setAttribute('aria-hidden', 'true');
  caja.append(mira);

  const tactil = () => (tipo ? tipo !== 'mouse' : matchMedia('(pointer: coarse)').matches);
  const copia = () => ({ v: st.v.map((p) => [...p]), fase: st.fase });
  const guardar = () => { st.hist.push(copia()); if (st.hist.length > 200) st.hist.shift(); };
  const avisar = (m) => { st.mensaje = m; pintar(); };

  function info() {
    const n = st.v.length;
    const area = n >= 3 ? areaM2(st.v) : 0;
    let puede = st.fase === 'dibujo' && n >= 3 && !st.cruza && area >= AREA_MIN && area <= AREA_MAX;
    if (st.fase === 'dibujo' && st.trazo) puede = false;
    return { fase: st.fase, modo: st.modo, anillo: st.v.map((p) => [...p]), n, cruza: st.cruza, area,
      perimetro: n >= 2 ? perimetroM(st.v) : 0, puedeTerminar: puede, puedeDeshacer: st.hist.length > 0,
      mensaje: st.mensaje, armado: st.armado, trazando: !!st.trazo, color: st.color, bloqueada: st.bloqueada };
  }

  // ── Capas ──
  function agregarCapas() {
    try { agregarCapasYa(); } catch { /* el estilo todavía carga: se agregan en su style.load */ }
  }
  function agregarCapasYa() {
    if (!map.getSource('zona')) map.addSource('zona', { type: 'geojson', data: VACIO });
    if (!map.getSource('zona-guia')) map.addSource('zona-guia', { type: 'geojson', data: VACIO });
    const color = ['case', ['get', 'cruza'], ROJO, ['get', 'color']];
    if (!map.getLayer('zona-relleno')) {
      map.addLayer({ id: 'zona-relleno', type: 'fill', source: 'zona', filter: ['==', ['geometry-type'], 'Polygon'],
        paint: { 'fill-color': color, 'fill-opacity': 0.16 } });
    }
    if (!map.getLayer('zona-halo')) {
      map.addLayer({ id: 'zona-halo', type: 'line', source: 'zona', filter: ['==', ['geometry-type'], 'LineString'],
        layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.75 } });
    }
    if (!map.getLayer('zona-borde')) {
      map.addLayer({ id: 'zona-borde', type: 'line', source: 'zona', filter: ['==', ['geometry-type'], 'LineString'],
        layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': color, 'line-width': 3 } });
    }
    if (!map.getLayer('zona-guia')) {
      map.addLayer({ id: 'zona-guia', type: 'line', source: 'zona-guia',
        paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-dasharray': [2, 1.5], 'line-opacity': 0.9 } });
    }
    pintarYa();
  }

  function datosZona() {
    const props = { color: st.color, cruza: st.cruza };
    if (st.trazo) {
      const c = st.trazo.px.map((p) => { const q = map.unproject(p); return [q.lng, q.lat]; });
      return c.length >= 2 ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: props, geometry: { type: 'LineString', coordinates: c } }] } : VACIO;
    }
    const v = st.v, n = v.length;
    if (st.fase === 'inactiva' || !n) return VACIO;
    const f = [];
    if (n >= 3) f.push({ type: 'Feature', properties: props, geometry: { type: 'Polygon', coordinates: [[...v, v[0]]] } });
    if (n >= 2) f.push({ type: 'Feature', properties: props, geometry: { type: 'LineString', coordinates: st.fase === 'dibujo' ? v : [...v, v[0]] } });
    return { type: 'FeatureCollection', features: f };
  }

  function centro() {
    const p = map.unproject([caja.clientWidth / 2, caja.clientHeight / 2]);
    return [p.lng, p.lat];
  }

  function datosGuia() {
    if (st.fase !== 'dibujo' || !st.v.length || st.trazo) return VACIO;
    const p = st.modo === 'mira' ? centro() : st.cursor;
    if (!p) return VACIO;
    const c = [st.v[st.v.length - 1], p];
    if (st.v.length >= 2) c.push(st.v[0]);
    return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { color: st.color }, geometry: { type: 'LineString', coordinates: c } }] };
  }

  // ── Marcadores: vértices (Marker arrastrable, 44 px de área táctil y 14 px visibles) y «+» en cada lado ──
  function nuevoVertice() {
    const el = document.createElement('div');
    el.className = 'zona-vertice';
    el.tabIndex = 0;
    el.setAttribute('role', 'button');
    el.append(document.createElement('i'));
    const m = new maplibregl.Marker({ element: el, draggable: true, anchor: 'center' });
    let antes = null;
    alTocar(el, () => { if (!st.arrastrado) tocarVertice(+el.dataset.i); });
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); tocarVertice(+el.dataset.i); }
      else if ((e.key === 'Delete' || e.key === 'Backspace') && st.fase === 'edicion') { e.preventDefault(); e.stopPropagation(); quitar(+el.dataset.i); }
    });
    m.on('dragstart', () => { antes = copia(); st.arrastrado = true; quitarPopup?.remove(); });
    m.on('drag', () => {
      const p = m.getLngLat();
      st.v[+el.dataset.i] = [p.lng, p.lat];
      pintar();
    });
    m.on('dragend', () => {
      const i = +el.dataset.i, p = m.getLngLat();
      setTimeout(() => { st.arrastrado = false; }, 0);
      if (!enRango(p.lng, p.lat)) {
        st.v = antes.v;
        avisar('Ese punto queda fuera de Yondó');
      } else {
        st.v[i] = [p.lng, p.lat];
        st.hist.push(antes);
        st.mensaje = '';
        pintar();
      }
      if (st.fase === 'edicion') listo();
    });
    return m;
  }

  function nuevoMedio() {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'zona-medio';
    el.setAttribute('aria-label', 'Agregar un punto en este lado');
    el.textContent = '+';
    const m = new maplibregl.Marker({ element: el, anchor: 'center' });
    alTocar(el, () => insertar(+el.dataset.i));
    return m;
  }

  function sincronizarMarcas() {
    const n = st.trazo || st.fase === 'inactiva' || st.fase === 'vista' ? 0 : st.v.length;
    while (marcas.length > n) marcas.pop().remove();
    while (marcas.length < n) marcas.push(nuevoVertice().setLngLat(st.v[marcas.length]).addTo(map));
    marcas.forEach((m, i) => {
      const el = m.getElement();
      el.dataset.i = i;
      el.setAttribute('aria-label', st.fase === 'dibujo' && i === 0 && n >= 3 ? 'Primer punto: tóquelo para cerrar la zona' : `Punto ${i + 1} de ${n}`);
      el.classList.toggle('primero', st.fase === 'dibujo' && i === 0 && n >= 3);
      el.classList.toggle('bloqueado', st.bloqueada);
      if (m.isDraggable() === st.bloqueada) m.setDraggable(!st.bloqueada);
      const ll = m.getLngLat();
      if (ll.lng !== st.v[i][0] || ll.lat !== st.v[i][1]) m.setLngLat(st.v[i]);
    });
    const nm = st.fase === 'edicion' && !st.trazo && !st.bloqueada ? st.v.length : 0;
    while (medios.length > nm) medios.pop().remove();
    while (medios.length < nm) medios.push(nuevoMedio().setLngLat(st.v[0]).addTo(map));
    medios.forEach((m, i) => {
      const a = st.v[i], b = st.v[(i + 1) % st.v.length];
      m.getElement().dataset.i = i;
      m.setLngLat([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
    });
    visibilidad();
  }

  // Se ocultan los «+» de lados de menos de 40 px en pantalla y los vértices a menos de 20 px de otro visible
  function visibilidad() {
    if (!marcas.length) return;
    const px = st.v.map((p) => map.project(p));
    let previo = null;
    marcas.forEach((m, i) => {
      const extremo = i === 0 || i === marcas.length - 1;
      const oculto = !extremo && previo && dist(px[i], previo) < 20;
      m.getElement().classList.toggle('oculto', !!oculto);
      if (!oculto) previo = px[i];
    });
    medios.forEach((m, i) => m.getElement().classList.toggle('oculto', dist(px[i], px[(i + 1) % px.length]) < 40));
  }

  // ── Pintado (a lo sumo una vez por cuadro) ──
  function pintarYa() {
    cuadro = 0;
    st.cruza = st.v.length >= 3 && seCruza(st.v);
    map.getSource('zona')?.setData(datosZona());
    map.getSource('zona-guia')?.setData(datosGuia());
    mira.hidden = !(st.fase === 'dibujo' && st.modo === 'mira');
    envoltura.classList.toggle('zona-dibujo', st.fase === 'dibujo');
    sincronizarMarcas();
    alCambiar(info());
  }
  function pintar() { if (!cuadro) cuadro = requestAnimationFrame(pintarYa); }

  function listo() { pintarYa(); alTerminar(info()); }

  // ── Acciones ──
  function agregar(p, punto, t = performance.now()) {
    if (st.fase !== 'dibujo') return false;
    if (!enRango(p[0], p[1])) { avisar('Ese punto queda fuera de Yondó'); return false; }
    if (st.v.length >= MAX_VERTICES) { avisar(`La zona admite como mucho ${MAX_VERTICES} puntos`); return false; }
    // Un punto sobre el anterior no se repite (sería un lado de largo cero)
    const u = st.v[st.v.length - 1];
    if (u && dist(map.project(u), punto || map.project(p)) < 3) { avisar('Ese punto ya está: mueva el mapa o toque en otro lugar'); return false; }
    guardar();
    st.v.push(p);
    st.agregados.push({ t, px: punto || map.project(p) });
    if (st.agregados.length > 6) st.agregados.shift();
    st.mensaje = '';
    pintar();
    return true;
  }

  function terminar() {
    if (st.fase !== 'dibujo' || st.trazo) return false;
    const n = st.v.length;
    if (n < MIN_VERTICES) { avisar('Faltan puntos: la zona necesita al menos 3'); return false; }
    if (seCruza(st.v)) { st.cruza = true; avisar('Los lados se cruzan'); return false; }
    const a = areaM2(st.v);
    if (a < AREA_MIN) { avisar('La zona es demasiado pequeña (menos de 100 m²)'); return false; }
    if (a > AREA_MAX) { avisar('La zona es demasiado grande (más de 4 000 km²)'); return false; }
    guardar();
    st.fase = 'edicion';
    st.mensaje = '';
    desarmarLazo();
    listo();
    return true;
  }

  function insertar(i) {
    if (st.fase !== 'edicion') return;
    if (st.v.length >= MAX_VERTICES) { avisar(`La zona admite como mucho ${MAX_VERTICES} puntos`); return; }
    const a = st.v[i], b = st.v[(i + 1) % st.v.length];
    guardar();
    st.v.splice(i + 1, 0, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
    st.mensaje = '';
    listo();
  }

  function quitar(i) {
    quitarPopup?.remove();
    if (st.v.length <= MIN_VERTICES) { avisar('La zona necesita al menos 3 puntos'); return; }
    guardar();
    st.v.splice(i, 1);
    st.mensaje = '';
    if (st.fase === 'edicion') listo(); else pintar();
  }

  function tocarVertice(i) {
    if (st.bloqueada) return;
    if (st.fase === 'dibujo') {
      if (i === 0 && st.v.length >= MIN_VERTICES) terminar();
      return;
    }
    if (st.fase !== 'edicion') return;
    quitarPopup?.remove();
    const div = document.createElement('div');
    div.className = 'zona-quitar';
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn chico';
    b.textContent = 'Quitar punto';
    b.disabled = st.v.length <= MIN_VERTICES;
    if (b.disabled) b.title = 'La zona necesita al menos 3 puntos';
    b.addEventListener('click', () => quitar(i));
    div.append(b);
    quitarPopup = new maplibregl.Popup({ closeButton: false, offset: 22, className: 'zona-popup' })
      .setLngLat(st.v[i]).setDOMContent(div).addTo(map);
    b.focus({ preventScroll: true });
  }

  function deshacer() {
    if (st.trazo) { cancelarTrazo(); return; }
    const h = st.hist.pop();
    if (!h) return;
    quitarPopup?.remove();
    const cerrada = st.fase === 'edicion';
    st.v = h.v;
    st.fase = h.fase === 'vista' ? 'edicion' : h.fase;
    st.mensaje = '';
    if (st.fase === 'dibujo' && st.modo === 'lazo') armarLazo();
    if (st.fase === 'edicion' || cerrada) listo(); else pintar();
  }

  // ── Lazo ──
  function armarLazo() {
    if (st.armado) return;
    st.armado = true;
    map.dragPan.disable();
    envoltura.classList.add('lazo');
  }
  function desarmarLazo() {
    st.trazo = null;
    if (!st.armado) return;
    st.armado = false;
    map.dragPan.enable();
    envoltura.classList.remove('lazo');
  }
  function cancelarTrazo() {
    if (!st.trazo) return;
    st.trazo = null;
    pintar();
  }
  const enContenedor = (e) => {
    const r = contenedor.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  function lazoAbajo(e) {
    tipo = e.pointerType || tipo;
    if (!st.armado || st.fase !== 'dibujo') return;
    if (!e.isPrimary || (st.trazo && e.pointerId !== st.trazo.id)) { cancelarTrazo(); return; } // segundo dedo: pellizco
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (e.target.closest?.('.zona-vertice, .zona-medio, .maplibregl-ctrl, .maplibregl-popup')) return;
    st.trazo = { id: e.pointerId, px: [enContenedor(e)] };
    try { contenedor.setPointerCapture(e.pointerId); } catch { /* sin captura: sigue igual */ }
    if (e.pointerType === 'mouse') e.preventDefault();
    pintar();
  }
  function lazoMueve(e) {
    if (!st.trazo || e.pointerId !== st.trazo.id) return;
    const p = enContenedor(e), u = st.trazo.px[st.trazo.px.length - 1];
    if (Math.hypot(p[0] - u[0], p[1] - u[1]) >= 2) { st.trazo.px.push(p); pintar(); }
  }
  function lazoArriba(e) {
    if (!st.trazo || e.pointerId !== st.trazo.id) return;
    const px = st.trazo.px;
    try { contenedor.releasePointerCapture(e.pointerId); } catch { /* ya liberada */ }
    // Un trazo por vez: al soltar vuelve el arrastre del mapa, salga bien o no
    desarmarLazo();
    let tol = 3, s = simplificar(px, tol);
    while (s.length > MAX_LAZO) { tol *= 1.5; s = simplificar(px, tol); }
    while (s.length > 1 && Math.hypot(s[0][0] - s[s.length - 1][0], s[0][1] - s[s.length - 1][1]) <= tol) s.pop();
    if (s.length < MIN_VERTICES) { avisar('El trazo es muy corto: toque «Lazo» y rodee la zona sin soltar'); return; }
    const v = s.map((p) => { const q = map.unproject(p); return [q.lng, q.lat]; });
    if (!v.every(([lon, lat]) => enRango(lon, lat))) { avisar('El trazo sale de Yondó: toque «Lazo» para trazar otra vez'); return; }
    guardar();
    st.v = v;
    st.modo = 'puntos';
    if (!terminar()) pintar();
  }
  function lazoCancelado(e) { if (st.trazo && e.pointerId === st.trazo.id) cancelarTrazo(); }
  // Con el lazo armado nadie cancela el primer touchmove (el arrastre del mapa está apagado) y el navegador deja los
  // siguientes como no cancelables: el pellizco de MapLibre ya no podría frenar el desplazamiento de la página (y Chrome
  // lo avisa en la consola). Se cancela aquí; no toca los eventos de puntero del trazo
  function toqueMueve(e) { if (st.armado && e.cancelable) e.preventDefault(); }

  // ── Eventos del mapa ──
  function clic(e) {
    if (st.fase !== 'dibujo' || st.modo !== 'puntos' || st.armado || st.bloqueada) return;
    if (e.originalEvent?.target?.closest?.('.zona-vertice, .zona-medio')) return;
    // La hora del evento (no la del manejador): con el hilo ocupado, dos clics lentos no deben parecer un doble clic
    const toque = tactil(), ahora = e.originalEvent?.timeStamp || performance.now();
    if (st.v.length >= MIN_VERTICES && dist(map.project(st.v[0]), e.point) <= (toque ? 22 : 8)) { terminar(); return; }
    // El segundo clic o toque de un doble termina sin agregar otro vértice
    const u = st.agregados[st.agregados.length - 1];
    if (u && ahora - u.t < 300 && dist(u.px, e.point) < (toque ? 22 : 10)) {
      if (st.v.length >= MIN_VERTICES) terminar();
      return;
    }
    agregar([e.lngLat.lng, e.lngLat.lat], e.point, ahora);
  }
  function dobleClic(e) {
    e.preventDefault();
    if (st.fase !== 'dibujo') return;
    // Primero se quitan los vértices repetidos que dejó el doble clic (agregados hace menos de 300 ms, a menos de 10 px)
    const ahora = e.originalEvent?.timeStamp || performance.now();
    const recientes = st.agregados.filter((a) => ahora - a.t < 300 && dist(a.px, e.point) < 10);
    if (recientes.length > 1) {
      st.v.splice(st.v.length - (recientes.length - 1));
      st.agregados = st.agregados.filter((a) => !recientes.slice(1).includes(a));
    }
    terminar();
  }
  function mueve(e) {
    if (st.fase !== 'dibujo' || st.modo !== 'puntos') return;
    st.cursor = [e.lngLat.lng, e.lngLat.lat];
    pintar();
  }
  function movido() {
    if (st.fase === 'dibujo' && st.modo === 'mira') pintar();
    else if (marcas.length) visibilidad();
  }
  function tecla(e) {
    if (st.fase !== 'dibujo' && st.fase !== 'edicion') return;
    if (e.target.closest?.('input, textarea, select, [contenteditable="true"], dialog')) return;
    if (e.key === 'Escape') {
      if (quitarPopup?.isOpen()) { quitarPopup.remove(); return; }
      if (st.trazo) { cancelarTrazo(); return; }
      if (st.fase === 'dibujo') { e.preventDefault(); cancelar(); }
    } else if (e.key === 'Backspace' || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z')) {
      if (e.target.closest?.('.zona-vertice')) return;
      e.preventDefault();
      deshacer();
    } else if (e.key === 'Enter' && st.fase === 'dibujo' && !e.target.closest?.('button, a, .zona-vertice')) {
      e.preventDefault();
      terminar();
    }
  }
  const tipoAbajo = (e) => { tipo = e.pointerType || tipo; };

  function conectar() {
    if (conectada) return;
    conectada = true;
    zoomDobleAntes = map.doubleClickZoom.isEnabled();
    map.doubleClickZoom.disable();
    map.on('click', clic);
    map.on('dblclick', dobleClic);
    map.on('mousemove', mueve);
    map.on('move', movido);
    document.addEventListener('keydown', tecla);
    contenedor.addEventListener('pointerdown', tipoAbajo, true);
    contenedor.addEventListener('pointerdown', lazoAbajo);
    contenedor.addEventListener('pointermove', lazoMueve);
    contenedor.addEventListener('pointerup', lazoArriba);
    contenedor.addEventListener('pointercancel', lazoCancelado);
    contenedor.addEventListener('touchmove', toqueMueve, { passive: false });
  }
  function desconectar() {
    if (!conectada) return;
    conectada = false;
    if (zoomDobleAntes) map.doubleClickZoom.enable();
    map.off('click', clic);
    map.off('dblclick', dobleClic);
    map.off('mousemove', mueve);
    map.off('move', movido);
    document.removeEventListener('keydown', tecla);
    contenedor.removeEventListener('pointerdown', tipoAbajo, true);
    contenedor.removeEventListener('pointerdown', lazoAbajo);
    contenedor.removeEventListener('pointermove', lazoMueve);
    contenedor.removeEventListener('pointerup', lazoArriba);
    contenedor.removeEventListener('pointercancel', lazoCancelado);
    contenedor.removeEventListener('touchmove', toqueMueve, { passive: false });
  }

  function ponerModo(modo) {
    st.modo = ['mira', 'puntos', 'lazo'].includes(modo) ? modo : (matchMedia('(pointer: coarse)').matches ? 'mira' : 'puntos');
    st.cursor = null;
    if (st.modo === 'lazo' && st.fase === 'dibujo') armarLazo(); else desarmarLazo();
    pintar();
  }

  function desactivar() {
    desarmarLazo();
    quitarPopup?.remove();
    desconectar();
    Object.assign(st, { fase: 'inactiva', modo: null, v: [], hist: [], agregados: [], cursor: null, trazo: null, mensaje: '', cruza: false });
    pintarYa();
  }

  function cancelar() {
    desactivar();
    alCancelar();
  }

  map.on('style.load', agregarCapas);
  agregarCapas();

  return {
    /** Empieza a dibujar (o cambia de modo si ya dibuja): «mira», «puntos» o «lazo». */
    activar(modo) {
      conectar();
      if (st.fase !== 'dibujo') {
        if (st.fase !== 'inactiva') guardar();
        quitarPopup?.remove();
        st.fase = 'dibujo';
        st.v = [];
        st.agregados = [];
        st.mensaje = '';
      }
      ponerModo(modo);
    },
    desactivar,
    cancelar,
    /** Muestra un anillo ya cerrado: para editarlo (por defecto) o solo para verlo (`editable: false`). */
    cargar(anillo, { editable = true, color: c } = {}) {
      conectar();
      desarmarLazo();
      if (st.fase !== 'inactiva' && st.v.length) guardar();
      st.v = abierto(anillo).map((p) => [+p[0], +p[1]]);
      st.fase = editable ? 'edicion' : 'vista';
      if (c) st.color = c;
      st.mensaje = '';
      listo();
    },
    anillo: () => st.v.map((p) => [...p]),
    /** Pasa de solo ver a editar (vértices, «+» y «Quitar punto»). */
    editar() { if (st.fase === 'vista') { st.fase = 'edicion'; listo(); } },
    terminar,
    deshacer,
    /** «+ Punto» del modo Mira: el vértice va en el centro (cierra si queda sobre el primero). */
    agregarCentro() {
      if (st.fase !== 'dibujo') return false;
      const p = centro(), px = map.project(p);
      if (st.v.length >= MIN_VERTICES && dist(map.project(st.v[0]), px) <= 22) return terminar();
      return agregar(p, px);
    },
    color(c) { st.color = c || PALETA[0]; pintar(); },
    /** Con el relieve encendido en 3D la zona solo se mira: los vértices no se arrastran ni se agregan (la posición
     * sobre el relieve que da MapLibre no es exacta). Plano o inclinado sin relieve, se edita al píxel. */
    bloquear(si) { si = !!si; if (si !== st.bloqueada) { st.bloqueada = si; quitarPopup?.remove(); pintar(); } },
    info,
    agregarCapas,
    destruir() {
      desactivar();
      map.off('style.load', agregarCapas);
      mira.remove();
      for (const id of ['zona-guia', 'zona-borde', 'zona-halo', 'zona-relleno']) if (map.getLayer(id)) map.removeLayer(id);
      for (const id of ['zona', 'zona-guia']) if (map.getSource(id)) map.removeSource(id);
    },
  };
}
