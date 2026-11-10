// Mapa 3D del municipio: relieve, edificios, columnas hexagonales 3D y mapa de calor de la población. Zonas (6): dibujar
// con ratón o dedo un polígono exacto, medirlo, ver su distribución, abrir esas personas en Habitantes, exportarlas y
// guardar la zona con nombre y asignación. En el celular el detalle (hexágono o zona) va en una hoja inferior.
// El asistente del panel también lo maneja (volar, filtros, capas, resaltar…): al terminar de cargar, la vista se
// registra en agente-mapa.js con `aplicar(acciones)` y `estado()`, y lo que dibuja va en su propia fuente `agente`.
import { api, descargar, puede } from '../api.js';
import { temaOscuro } from '../app.js';
import { BASES, BBOX_YONDO, CASCO, MAX_IDS, RANGO_YONDO, anilloMayor, baseSegunTema, cajaDe, cargarMapLibre, decorar, dentroDeYondo, dispersar, hexagonos, rampa } from '../mapa3d.js';
import { apilada, barras, piramide } from '../graficos.js';
import { ESTADOS_ABORDAJE, ESTADOS_AUTORIZACION, ETIQUETAS_CAMPOS, SEXOS } from '../modelo.js';
import { $, $$, aviso, avisoError, confirmar, dialogo, html, icono, montar, num, pct, titulo } from '../ui.js';
import { url } from '../base.js';
import { registrarMapa } from '../agente-mapa.js';
import { MAX_VERTICES, PALETA, cargarEstilos, codificar, crearHerramientaZona, decodificar, dentro, formatoArea, formatoLargo, seCruza, simplificar } from '../zona.js';

const RADIOS = { auto: null, 150: 150, 400: 400, 1000: 1000 };
const MODOS = [['mira', 'Mira'], ['puntos', 'Por puntos'], ['lazo', 'Lazo']];
const AYUDA = {
  mira: 'Mueva el mapa hasta que la cruz quede sobre el punto y toque «+ Punto». «Terminar» cierra la zona.',
  puntos: 'Toque o haga clic en cada esquina. Se cierra tocando el primer punto, con doble clic, Enter o «Terminar». Esc cancela; Retroceso deshace.',
  lazo: 'Rodee la zona con el dedo o el ratón sin soltar. Al soltar queda lista para ajustar. Dos dedos mueven el mapa.',
};
const NOMBRES_COLOR = { '#2a78d6': 'Azul', '#eb6834': 'Naranja', '#1baf7a': 'Verde', '#eda100': 'Amarillo', '#e87ba4': 'Rosado',
  '#008300': 'Verde oscuro', '#6250d6': 'Morado', '#3d3d3a': 'Gris' };
const DEMOGRAFIA = { estado_civil: 'Estado civil', nivel_educativo: 'Nivel educativo', situacion_laboral: 'Situación laboral',
  estrato: 'Estrato', tenencia_vivienda: 'Vivienda', regimen_salud: 'Régimen de salud' };
const FUENTES_N = { tramites: 'Base de trámites', cedulas: 'Base con cédula', manual: 'Panel', reunion: 'Reuniones', planilla: 'Planilla',
  consultor: 'Consultor', otra_base: 'Otra base' };
const modoPreferido = () => (matchMedia('(pointer: coarse)').matches ? 'mira' : 'puntos');
const esNumero = (x) => typeof x === 'number' && Number.isFinite(x);

// ── Control del asistente ──
// Las acciones llegan validadas y resueltas por el servidor (docs/agente.md §6), pero las arma un modelo de lenguaje:
// aquí se validan otra vez (tipos, rangos, dentro de Yondó, cantidades) antes de tocar el mapa
const MAX_ACCIONES = 20;
const PLAZO_ACCION_MS = 25000; // red de seguridad: una acción que se cuelga no deja la cola esperando para siempre
const VUELO_MS = 2400;
// Lo mínimo de mapa a la vista (px de ancho) entre el panel izquierdo y el del asistente abierto: con menos, se pliega
// el izquierdo
const HUECO_AGENTE = 300;
const COLOR_AGENTE = '#e3141b';
const COLOR_OK = /^#[0-9a-fA-F]{6}$/;
const BASES_OK = ['auto', 'oscuro', 'claro', 'satelite'];
const RECORRIDOS = ['municipio', 'casco', 'tigre'];
// Los filtros de Habitantes (`filtros.Filtros`) que el asistente puede poner en el mapa. Fuera: `poligono` y `area_id`
// (son zonas: acción `zona`), `ids` (va por `resaltar`) y `mios` (no aplica al mapa)
const CLAVES_FILTRO = new Set(['q', 'zona', 'lugar_id', 'fuente', 'lista', 'etiqueta', 'con_cedula', 'con_telefono', 'precision',
  'reunion_id', 'asistio', 'consentimiento', 'lider', 'sexo', 'completitud_max', 'edad_min', 'edad_max', 'tipo_documento',
  'cedula_verificada', 'puesto_id', 'con_puesto', 'con_mesa', 'votacion_estado', 'donde', 'abordado', 'contactado',
  'abordaje_estado', 'ultimo_resultado', 'sin_acercamiento_dias', 'proximo_vencido', 'canal_autorizado', 'situacion',
  'creado_por', 'actualizado_por', 'menor', 'requiere_actualizacion', 'varios_telefonos', 'telefono_estado', 'estado_civil',
  'nivel_educativo', 'situacion_laboral', 'estrato', 'tenencia_vivienda', 'regimen_salud', 'tratables',
  ...['cedula', 'telefono', 'sexo', 'edad', 'lugar', 'puesto', 'mesa', 'direccion', 'puesto_mesa'].map((c) => `sin_${c}`)]);
const esObjeto = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
const idValido = (x) => Number.isInteger(x) && x > 0 && x <= 2 ** 31;
const fallo = (mensaje) => { throw new Error(mensaje); };
// Etiqueta de un punto resaltado: se dibuja en WebGL (nunca como HTML), en una línea y con 80 caracteres como mucho.
// Sin caracteres de control ni marcas de dirección del texto, que la desordenarían en pantalla
function etiquetaSegura(v) {
  if (typeof v !== 'string') return null;
  const t = v.replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, ' ').replace(/\s+/g, ' ').trim();
  const letras = Array.from(t); // por puntos de código: no parte una tilde ni un emoji a la mitad
  return !t ? null : letras.length > 80 ? letras.slice(0, 79).join('') + '…' : t;
}
// Valor de un filtro como lo lleva la URL: texto corto de una línea; sí/no como 1/0; null o vacío lo quita
function valorFiltro(clave, v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'boolean') return v ? '1' : '0';
  if (esNumero(v)) return String(v);
  if (typeof v === 'string' && v.trim().length <= 120 && !/[\u0000-\u001f\u007f]/.test(v)) return v.trim() || null;
  return fallo(`Valor no válido para el filtro ${clave}`);
}
const mismosFiltros = (a, b) => {
  const ka = Object.keys(a);
  return ka.length === Object.keys(b).length && ka.every((k) => Object.hasOwn(b, k) && String(b[k]) === String(a[k]));
};

export async function vistaMapa(el, { q, ir }) {
  const filtros = Object.fromEntries([...q.entries()]);
  const zonaUrl = { area_id: filtros.area_id, poligono: filtros.poligono };
  delete filtros.area_id;
  delete filtros.poligono;
  const gestiona = puede('zonas.gestionar');
  const estado = {
    base: null, capas: { calor: true, columnas: true, puntos: true, veredas: true, reuniones: true, edificios: true, relieve: true, areas: true },
    radio: 'auto', filtros, datos: null, capasGeo: null, cat: null, seleccion: null,
    // Zona: sesión abierta (dibujo, edición o una guardada a la vista), la guardada que se ve, si cambió, lo que dice la
    // herramienta, la distribución del servidor y si el servidor ya filtra por polígono
    dibujo: false, zona: null, zonaCambiada: false, info: null, dist: null, soporteZona: null, turnoDist: 0, plano: null,
    hexSel: null, areas: [], expandida: !matchMedia('(max-width: 900px)').matches, faseVista: null,
    // Del asistente: puntos resaltados (Feature de GeoJSON), el polígono del lugar al que voló, el turno de la carga de
    // puntos (la última respuesta gana) y si alguien ya movió la cámara (la presentación inicial no la pisa)
    resalte: [], foco: null, turnoDatos: 0, camaraTomada: false,
  };
  const capasLista = [['columnas', 'Columnas 3D por hexágono'], ['calor', 'Mapa de calor'], ['puntos', 'Personas (al acercarse)'], ['veredas', 'Veredas y lugares'],
    ['reuniones', 'Reuniones'], ['edificios', 'Edificios 3D'], ['relieve', 'Relieve del terreno'], ...(gestiona ? [['areas', 'Zonas guardadas']] : [])];
  montar(el, html`
    <div class="mapa"><div id="mapa" style="width:100%;height:100%"></div></div>
    <div class="cargador-mapa" id="cargador"><div style="text-align:center"><div class="giro" style="margin:auto"></div><p class="sec">Levantando el municipio en 3D…</p></div></div>
    <aside class="panel-mapa izq" id="panel-izq">
      <div class="cabeza-izq"><h1>Mapa de la población</h1>
        <button class="btn fantasma chico plegar" id="plegar" aria-expanded="true" aria-controls="cuerpo-izq">Ocultar</button></div>
      <div style="display:flex;align-items:baseline;gap:10px;margin-top:12px">
        <span class="gran-cifra" id="cifra">—</span><span class="sec" id="cifra-d"></span>
      </div>
      <div id="filtros-asistente" hidden></div>
      <div class="cuerpo-izq" id="cuerpo-izq">
      ${gestiona ? html`<h3>Zonas guardadas</h3>
        <select class="entrada zonas-guardadas" id="zonas-guardadas" aria-label="Zonas guardadas"><option value="">Elegir una zona…</option></select>` : ''}
      <h3>Capas</h3>
      ${capasLista.map(([k, t]) => html`<label class="interruptor"><span>${t}</span><input type="checkbox" data-capa="${k}" ${estado.capas[k] ? 'checked' : ''}></label>`)}
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
      </div>
    </aside>
    <aside class="panel-mapa der hoja" id="panel-der" aria-label="Detalle del mapa">
      <div class="asa" aria-hidden="true"></div>
      <button class="btn fantasma chico cerrar-hoja" id="cerrar-hoja" aria-label="Cerrar el detalle">✕</button>
      <section id="sec-vista"><h3 style="margin-top:0">En pantalla</h3><div id="en-vista"></div></section>
      <div id="detalle"></div>
    </aside>
    <div class="panel-mapa abajo" id="abajo">
      <button class="btn fantasma chico" data-vista="municipio">Municipio</button>
      <button class="btn fantasma chico" data-vista="casco">Casco urbano</button>
      <button class="btn fantasma chico" data-vista="tigre">San Miguel del Tigre</button>
      <button class="btn fantasma chico" data-vista="girar" aria-pressed="false">Girar</button>
      ${gestiona ? html`<button class="btn chico oscuro" data-vista="zona" id="btn-zona" aria-pressed="false">${icono('zona')} Medir zona</button>` : ''}
      <div style="padding:2px 10px;min-width:280px">
        <div class="rampa" id="rampa"></div><div class="rampa-et"><span>Menos</span><span>Más personas por hexágono</span></div>
      </div>
    </div>`);

  const [maplibregl, cat] = await Promise.all([cargarMapLibre(), api.get('/api/catalogos'), cargarEstilos()]);
  // Mientras cargaba se pidió otra vista: no se crea un mapa sobre un contenedor que ya no está
  if (!el.isConnected) return;
  estado.cat = cat;
  $('#f-etiqueta', el).append(...(cat.etiquetas || []).map((e) => new Option(`${e.nombre} (${e.n})`, e.id)));
  $('#f-lista', el).append(...(cat.listas || []).map((l) => new Option(l, l)));
  for (const s of $$('[data-f]', el)) s.value = estado.filtros[s.dataset.f] || '';

  const tactil = matchMedia('(pointer: coarse)').matches;
  const movil = matchMedia('(max-width: 900px)');
  const map = new maplibregl.Map({
    container: $('#mapa', el), style: BASES[baseSegunTema()], bounds: BBOX_YONDO, fitBoundsOptions: { padding: 40 },
    pitch: 50, bearing: -15, maxPitch: 80, attributionControl: { compact: true }, hash: false,
    // Con el dedo, un toque con temblor sigue siendo un toque (agrega el vértice): solo se puede fijar al crear el mapa
    clickTolerance: tactil ? 10 : 3,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  let girando = false, rafGiro = 0, herramienta = null, rafVivo = 0, tDist = 0, vivoClave = '', vivo = null;
  // Presentación inicial pendiente, la función que quita el control del asistente y las esperas de eventos del mapa en
  // curso (se sueltan todas al salir de la vista)
  let tIntro = 0, quitarControl = null;
  const esperas = new Set();
  // MapLibre emite `load` dentro de un cuadro, cuando ya cargó todo: si la última tesela que faltaba respondió con error
  // (un 404 del servidor de mapas) puede no venir otro cuadro y `load` no llega nunca (el cargador queda en pantalla y
  // el asistente espera en vano). Pedir un cuadro cada tanto mientras carga lo destraba; se detiene en `load`.
  const empujar = setInterval(() => map.triggerRepaint(), 2000);
  const popup = new maplibregl.Popup({ closeButton: true, maxWidth: '280px' });
  const hoja = $('#panel-der', el), abajo = $('#abajo', el), detalle = $('#detalle', el), izq = $('#panel-izq', el);

  // ───────── Hoja inferior (celular) ─────────
  function medirHoja() {
    const h = !movil.matches ? 0 : hoja.classList.contains('abierta') ? hoja.offsetHeight : abajo.offsetHeight + 18;
    $('.mapa', el)?.style.setProperty('--alto-hoja', `${h}px`);
  }
  const ro = new ResizeObserver(medirHoja);
  ro.observe(hoja);
  ro.observe(abajo);
  movil.addEventListener('change', medirHoja);
  function plegarIzq(plegar) {
    izq.classList.toggle('plegado', plegar);
    $('#plegar', el).setAttribute('aria-expanded', String(!plegar));
    $('#plegar', el).textContent = plegar ? 'Capas y filtros' : 'Ocultar';
  }
  if (movil.matches) plegarIzq(true);
  function abrirHoja() {
    hoja.classList.add('abierta');
    if (movil.matches) plegarIzq(true);
    medirHoja();
  }
  function cerrarHoja() {
    hoja.classList.remove('abierta');
    if (!estado.dibujo) montar(detalle, '');
    medirHoja();
  }

  function radioActual() {
    if (RADIOS[estado.radio]) return RADIOS[estado.radio];
    const z = map.getZoom();
    return z >= 15 ? 90 : z >= 13.5 ? 180 : z >= 12 ? 450 : z >= 10.5 ? 1100 : 2200;
  }

  // Mientras hay una zona abierta, los puntos aproximados se pintan en su coordenada guardada (sin dispersar): lo que se
  // ve coincide con lo que se cuenta
  function puntosVisibles() {
    return (estado.datos?.puntos || []).map((p) => {
      const [lon, lat] = estado.dibujo ? [p[2], p[1]] : dispersar(p[0], p[2], p[1], p[3]);
      return [lon, lat, p[0], p[5], p[3], p[4], p[6], p[7]];
    });
  }

  function geoPuntos(pts) {
    return { type: 'FeatureCollection', features: pts.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p[0], p[1]] },
      properties: { id: p[2], p: p[4], r: p[6] } })) };
  }

  function actualizarHex() {
    if (!map.getSource('hex')) return;
    const { geo } = hexagonos(puntosVisibles(), radioActual());
    map.getSource('hex').setData(geo);
    const radio = radioActual();
    // Columnas más bajas en hexágonos pequeños: de cerca no deben tapar el casco urbano
    map.setPaintProperty('hex-3d', 'fill-extrusion-height', ['*', ['get', 't'], Math.min(2600, radio * (radio < 300 ? 1.8 : 3))]);
  }

  function repintarPuntos() {
    if (!map.getSource('puntos') || !estado.datos) return;
    map.getSource('puntos').setData(geoPuntos(puntosVisibles()));
    actualizarHex();
  }

  function pintarRampa() {
    const r = rampa(temaOscuro() || estado.base === 'oscuro' || estado.base === 'satelite');
    $('#rampa', el).style.background = `linear-gradient(90deg, ${r.join(',')})`;
  }

  function geoAreas() {
    const abierta = estado.dibujo && estado.zona ? estado.zona.id : null;
    return { type: 'FeatureCollection', features: estado.areas.filter((a) => a.id !== abierta && a.poligono?.length >= 3).map((a) => ({
      type: 'Feature', geometry: { type: 'Polygon', coordinates: [[...a.poligono, a.poligono[0]]] }, properties: { id: a.id, nombre: a.nombre, color: a.color || PALETA[0] } })) };
  }

  function agregarCapas() {
    const oscuro = estado.base === 'satelite' || (estado.base || baseSegunTema()) === 'oscuro';
    const r = rampa(oscuro);
    decorar(map, { relieve: estado.capas.relieve && !estado.plano, edificios: estado.capas.edificios, oscuro });
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
        'fill-extrusion-height': ['*', ['get', 't'], 1000], 'fill-extrusion-vertical-gradient': true,
        'fill-extrusion-opacity': ['interpolate', ['linear'], ['zoom'], 12, 0.9, 15, 0.5] } });
      map.addSource('puntos', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'calor', type: 'heatmap', source: 'puntos', maxzoom: 17, paint: {
        'heatmap-weight': 1,
        // Segunda escala secuencial (las columnas van en azul): un solo tono naranja, de transparente a intenso
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 8, 0.35, 12, 0.55, 15, 0.9, 17, 1.2],
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 8, 4, 12, 9, 15, 18, 17, 30],
        'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(235,104,52,0)', 0.12, 'rgba(251,217,201,0.55)',
          0.35, '#f6b391', 0.6, '#f08550', 0.85, '#eb6834', 1, '#b9431a'],
        'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0.8, 17, 0.35] } });
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
    if (gestiona && !map.getSource('areas')) {
      map.addSource('areas', { type: 'geojson', data: geoAreas() });
      map.addLayer({ id: 'areas-relleno', type: 'fill', source: 'areas', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 } });
      map.addLayer({ id: 'areas-borde', type: 'line', source: 'areas', paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-dasharray': [2, 1] } });
    }
    // Lo que dibuja el asistente: el polígono del lugar al que voló y los puntos resaltados con su etiqueta. Como todo lo
    // de aquí, se rehace desde `estado` en cada style.load: así sobrevive al cambio de mapa base (setStyle lo borra todo)
    if (!map.getSource('agente')) {
      map.addSource('agente', { type: 'geojson', data: geoAgente() });
      const color = ['coalesce', ['get', 'color'], COLOR_AGENTE];
      const poligono = ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false];
      map.addLayer({ id: 'agente-relleno', type: 'fill', source: 'agente', filter: poligono, paint: { 'fill-color': color, 'fill-opacity': 0.12 } });
      map.addLayer({ id: 'agente-borde', type: 'line', source: 'agente', filter: poligono, layout: { 'line-join': 'round' },
        paint: { 'line-color': color, 'line-width': 3 } });
      map.addLayer({ id: 'agente-puntos', type: 'circle', source: 'agente', filter: ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false],
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 5, 16, 8], 'circle-color': color,
          'circle-stroke-color': '#fff', 'circle-stroke-width': 2.5 } });
      // El nombre va como texto del mapa (WebGL): nunca pasa por HTML
      map.addLayer({ id: 'agente-etiquetas', type: 'symbol', source: 'agente', filter: ['has', 'etiqueta'], layout: {
        'text-field': ['get', 'etiqueta'], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-anchor': 'top',
        'text-offset': [0, 0.9], 'text-max-width': 10 },
        paint: { 'text-color': oscuro ? '#f3f3f0' : '#111', 'text-halo-color': oscuro ? 'rgba(0,0,0,.85)' : 'rgba(255,255,255,.9)', 'text-halo-width': 1.6 } });
    }
    aplicarVisibilidad();
    repintarPuntos();
    pintarRampa();
  }

  const geoAgente = () => ({ type: 'FeatureCollection', features: [...(estado.foco ? [estado.foco] : []), ...estado.resalte] });
  // Mientras carga otro mapa base la fuente no existe: queda en `estado` y agregarCapas la crea con esto
  const pintarAgente = () => map.getSource('agente')?.setData(geoAgente());

  function aplicarVisibilidad() {
    const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    vis('hex-3d', estado.capas.columnas && !estado.plano);
    // Con una zona abierta en 3D, las columnas se vuelven translúcidas para que la zona pegada al relieve se vea
    if (map.getLayer('hex-3d')) map.setPaintProperty('hex-3d', 'fill-extrusion-opacity', estado.dibujo ? 0.3 : ['interpolate', ['linear'], ['zoom'], 12, 0.9, 15, 0.5]);
    vis('calor', estado.capas.calor);
    vis('puntos', estado.capas.puntos);
    ['veredas-relleno', 'veredas-borde', 'lugares-nombre'].forEach((id) => vis(id, estado.capas.veredas));
    ['reuniones', 'reuniones-n'].forEach((id) => vis(id, estado.capas.reuniones));
    ['areas-relleno', 'areas-borde'].forEach((id) => vis(id, estado.capas.areas));
    vis('edificios-3d', estado.capas.edificios);
    if (map.getSource('dem')) map.setTerrain(estado.capas.relieve && !estado.plano ? { source: 'dem', exaggeration: 1.7 } : null);
    herramienta?.bloquear(estado.dibujo && estado.capas.relieve && !estado.plano);
  }

  // Cada pedido lleva su turno: con la persona y el asistente cambiando filtros a la vez, las respuestas pueden llegar en
  // otro orden y solo se pinta la del último pedido. Devuelve false si la respuesta ya sobraba. Los errores del último
  // pedido se lanzan: quien llama decide (un aviso en la interfaz, un resultado con error para el asistente)
  async function cargarDatos() {
    const turno = ++estado.turnoDatos;
    let d;
    try {
      d = await api.get('/api/mapa/puntos', estado.filtros);
    } catch (err) {
      if (turno !== estado.turnoDatos || !el.isConnected) return false;
      throw err;
    }
    if (turno !== estado.turnoDatos || !el.isConnected) return false;
    estado.datos = d;
    vivoClave = '';
    $('#cifra', el).textContent = num(d.ubicadas);
    $('#cifra-d', el).textContent = `ubicadas de ${num(d.total)} (${pct(d.ubicadas, d.total)} %)`;
    repintarPuntos();
    resumenVista();
    if (estado.dibujo) { actualizarZona(); programarDistribucion(); }
    return true;
  }

  const nombreLugar = (id) => {
    const f = estado.capasGeo?.lugares.features.find((x) => x.properties.id === id) || (estado.cat.lugares || []).find((l) => l.id === id);
    return f ? titulo((f.properties || f).nombre) : 'Sin barrio o vereda';
  };

  // ── Filtros sin control a la vista ──
  // Los selects muestran seis filtros con sus opciones. El asistente (o un enlace) puede poner otros, o un valor que no
  // está entre las opciones (el select se ve vacío): sin este aviso, el mapa filtraría en silencio
  function filtrosOcultos() {
    const selects = new Map($$('[data-f]', el).map((s) => [s.dataset.f, s]));
    return Object.keys(estado.filtros).filter((k) => {
      const v = String(estado.filtros[k] ?? '');
      const s = selects.get(k);
      return v !== '' && (!s || ![...s.options].some((o) => o.value === v));
    });
  }
  function etiquetaFiltro(k, v) {
    const s = String(v ?? '');
    if (k === 'sexo') return `Sexo: ${SEXOS[s] || (s === 'sin' ? 'sin dato' : s)}`;
    if (k === 'edad_min') return `Desde ${s} años`;
    if (k === 'edad_max') return `Hasta ${s} años`;
    if (k === 'lugar_id') return s === '0' ? 'Sin barrio o vereda' : nombreLugar(Number(s));
    if (k === 'zona' && s === 'sin') return 'Sin zona';
    if (k === 'consentimiento') return `Autorización: ${ESTADOS_AUTORIZACION[s] || s}`;
    if (k === 'abordaje_estado') return `Abordaje: ${ESTADOS_ABORDAJE[s] || s}`;
    if (k === 'completitud_max') return `Perfil hasta ${s} %`;
    if (k === 'reunion_id') return `Asistentes de la reunión ${s}`;
    if (k.startsWith('sin_') && s === '1') return `Sin ${(ETIQUETAS_CAMPOS[k.slice(4)] || k.slice(4).replace(/_/g, ' ')).toLowerCase()}`;
    return `${k.replace(/_/g, ' ')}: ${s === '1' ? 'sí' : s === '0' ? 'no' : s}`;
  }
  function pintarFiltrosAsistente() {
    const caja = $('#filtros-asistente', el);
    if (!caja) return;
    const ocultos = filtrosOcultos();
    caja.hidden = !ocultos.length;
    if (!ocultos.length) { montar(caja, ''); return; }
    const texto = ocultos.map((k) => etiquetaFiltro(k, estado.filtros[k])).join(' · ');
    montar(caja, html`<div class="chips" style="margin-top:10px;align-items:center">
      <button class="chip rojo" type="button" data-quitar-asistente title="Quitar: ${texto}" aria-label="Quitar los filtros del asistente: ${texto}">Filtros del asistente · Quitar ✕</button>
      <span class="sec" style="font-size:12.5px">${texto}</span></div>`);
  }
  function sincronizarFiltros() { for (const s of $$('[data-f]', el)) s.value = estado.filtros[s.dataset.f] || ''; }
  function alCambiarFiltros() {
    sincronizarFiltros();
    ponerUrl();
    pintarFiltrosAsistente();
  }
  async function quitarFiltrosAsistente() {
    const ocultos = filtrosOcultos();
    if (!ocultos.length) return;
    const nuevos = { ...estado.filtros };
    for (const k of ocultos) delete nuevos[k];
    estado.filtros = nuevos;
    alCambiarFiltros();
    try { await cargarDatos(); } catch (err) { avisoError(err); }
  }

  function resumenVista() {
    if (!estado.datos) return;
    const b = map.getBounds();
    const dentroVista = estado.datos.puntos.filter((p) => b.contains([p[2], p[1]]));
    const porLugar = new Map();
    let exactas = 0;
    for (const p of dentroVista) {
      porLugar.set(p[5], (porLugar.get(p[5]) || 0) + 1);
      if (p[3] === 0) exactas++;
    }
    const top = [...porLugar.entries()].sort((a, b2) => b2[1] - a[1]).slice(0, 6);
    // Cada barrio enlaza al directorio con los filtros del mapa y solo a personas con ubicación (las que el mapa
    // cuenta); «Sin barrio o vereda» usa lugar_id=0
    const fila = (id, n) => html`<span>${nombreLugar(id)}</span>
        <span><span class="b" style="width:${(n / (top[0]?.[1] || 1)) * 100}%"></span></span><span class="n">${num(n)}</span>`;
    montar($('#en-vista', el), html`<div class="gran-cifra" style="font-size:30px">${num(dentroVista.length)}</div>
      <div class="sec">personas · ${pct(exactas, dentroVista.length)} % con dirección exacta</div>
      <div class="lista-barras" style="margin-top:12px">${top.map(([id, n]) =>
        html`<a class="f" href="/personas?${new URLSearchParams({ ...estado.filtros, lugar_id: id || 0, precision: estado.filtros.precision || 'ubicada' })}" data-ruta>${fila(id, n)}</a>`)}</div>`);
  }

  function globo(contenido) {
    const d = document.createElement('div');
    montar(d, contenido);
    return d;
  }

  function mostrarHex(props, lngLat, anillo) {
    const lugares = JSON.parse(props.lugares || '[]');
    estado.hexSel = anillo || null;
    montar(detalle, html`<h3>Hexágono seleccionado</h3>
      <div class="gran-cifra" style="font-size:30px">${num(props.n)}</div><div class="sec">personas en ~${radioActual() * 2} m de ancho</div>
      <div class="lista-barras" style="margin-top:10px">${lugares.map(([id, n]) => html`<div class="f"><span>${nombreLugar(id)}</span><span></span><span class="n">${num(n)}</span></div>`)}</div>
      <div class="zona-acciones">
        <a class="btn chico" href="/personas?ids=${props.ids}&ids_total=${props.n}" data-ruta>Ver la lista</a>
        ${gestiona && anillo ? html`<button class="btn chico" type="button" data-z="hex">${icono('zona')} Medir este hexágono</button>` : ''}
      </div>
      ${props.n > MAX_IDS ? html`<p class="sec" style="margin:8px 0 0">La lista muestra ${num(MAX_IDS)} de ${num(props.n)} personas. Acérquese, elija un hexágono más pequeño o mídalo como zona para verlas todas.</p>` : ''}`);
    abrirHoja();
    popup.setLngLat(lngLat).setDOMContent(globo(html`<b>${num(props.n)} personas</b><br><span class="sec">${lugares.map(([id]) => nombreLugar(id)).join(', ')}</span>`)).addTo(map);
  }

  // ───────── Zonas ─────────
  const anilloInfo = () => estado.info?.anillo || [];
  function zonaParams() {
    const i = estado.info;
    if (!i || i.n < 3 || (i.fase !== 'edicion' && i.fase !== 'vista')) return {};
    if (estado.zona && !estado.zonaCambiada) return { area_id: estado.zona.id };
    return { poligono: codificar(i.anillo) };
  }
  function ponerUrl() {
    const z = estado.dibujo ? zonaParams() : {};
    history.replaceState(history.state, '', url('/mapa?' + new URLSearchParams({ ...estado.filtros, ...z })));
  }
  function relleno() {
    const m = movil.matches;
    return m ? { top: 70, left: 30, right: 30, bottom: 30 + (hoja.offsetHeight || 140) }
      : { top: 40, bottom: 90, left: izq.classList.contains('plegado') ? 40 : 340, right: 330 };
  }
  function encuadrar(anillo) {
    if (anillo?.length >= 3) map.fitBounds(cajaDe({ type: 'Polygon', coordinates: [anillo] }), { padding: relleno(), maxZoom: 17, duration: 900 });
  }

  function pintarAreas() {
    map.getSource('areas')?.setData(geoAreas());
    const s = $('#zonas-guardadas', el);
    if (!s) return;
    const actual = estado.zona?.id;
    s.replaceChildren(new Option(estado.areas.length ? `Elegir una zona (${estado.areas.length})…` : 'Aún no hay zonas guardadas', ''),
      ...estado.areas.map((a) => new Option(`${a.nombre} · ${formatoArea(a.area_m2 || 0)}`, a.id)));
    s.value = actual != null && estado.dibujo ? String(actual) : '';
  }
  async function cargarAreas() {
    if (!gestiona) return;
    try {
      const r = await api.get('/api/areas');
      estado.areas = r.areas || [];
    } catch (err) {
      if (err?.estado !== 404) avisoError(err);
      estado.areas = [];
    }
    if (el.isConnected) pintarAreas();
  }

  function aplanar() {
    if (estado.plano) return;
    estado.plano = { pitch: map.getPitch(), bearing: map.getBearing() };
    aplicarVisibilidad();
    map.easeTo({ pitch: 0, duration: 700 });
  }
  // Al salir vuelve la inclinación guardada; «Ver en 3D» inclina al menos 45° aunque se hubiera entrado con el mapa plano
  function restaurar3d(minimo = 0) {
    const v = estado.plano;
    if (!v) return;
    estado.plano = null;
    aplicarVisibilidad();
    map.easeTo({ pitch: Math.max(v.pitch, minimo), bearing: v.bearing, duration: 900 });
  }

  function pararGiro() {
    girando = false;
    cancelAnimationFrame(rafGiro);
    $('[data-vista="girar"]', el)?.setAttribute('aria-pressed', 'false');
  }
  // El giro es un rotateTo en cada cuadro, y cada rotateTo detiene la animación de cámara en curso: mientras gira no hay
  // vuelo que llegue. Por eso toda acción de cámara (botones y asistente) lo detiene antes de moverse
  function iniciarGiro() {
    if (girando || estado.dibujo) return girando;
    girando = true;
    $('[data-vista="girar"]', el)?.setAttribute('aria-pressed', 'true');
    const paso = () => { if (!girando) return; map.rotateTo(map.getBearing() + 0.08, { duration: 0 }); rafGiro = requestAnimationFrame(paso); };
    paso();
    return true;
  }

  // La presentación inicial (un vuelo al casco a los 0,9 s de cargar) no pisa una cámara que ya pidió alguien: un botón
  // o una acción del asistente que esperaba en la cola a que el mapa terminara de cargar
  function cancelarPresentacion() {
    estado.camaraTomada = true;
    clearTimeout(tIntro);
  }
  // Antes de que el asistente mueva la cámara: sin presentación, sin giro y sin la animación en curso (map.stop la corta
  // y emite su moveend ya, no en medio del vuelo nuevo)
  function tomarCamara() {
    cancelarPresentacion();
    pararGiro();
    popup.remove();
    map.stop();
  }
  const lugarTigre = () => estado.capasGeo?.lugares?.features?.find((f) => f.properties?.nombre?.includes('SAN MIGUEL DEL TIGRE'));
  /** Recorridos de la barra de abajo (municipio, casco, tigre): false si no hay con qué (el límite o el punto). Con
   * `hueco` (el relleno que pide el asistente: rellenoAgente()), el destino queda en lo que dejan libre los paneles. */
  function irVista(k, hueco = null) {
    pararGiro();
    const aPunto = (centro, { zoom, ...op }) => (hueco ? volarAlPunto(centro, zoom, op, hueco)
      : map.flyTo({ ...op, center: centro, zoom }));
    if (k === 'municipio') {
      if (!estado.capasGeo?.limite) return false;
      map.fitBounds(cajaDe(estado.capasGeo.limite), { padding: hueco || 50, pitch: estado.plano ? 0 : 50, bearing: -15,
        duration: 2500 });
    } else if (k === 'casco') {
      aPunto(CASCO.center, { zoom: CASCO.zoom, pitch: estado.plano ? 0 : CASCO.pitch, bearing: CASCO.bearing,
        duration: 2600 });
    } else if (k === 'tigre') {
      const t = lugarTigre();
      if (!t) return false;
      aPunto(t.geometry.coordinates, { zoom: 15, pitch: estado.plano ? 0 : 60, bearing: 20, duration: 2600 });
    } else return false;
    return true;
  }
  /** Vuela a `punto` con `zoom` y lo deja en medio de lo que deja libre `relleno` (los paneles): se encuadra el punto
   * solo, así el centro se corre según el relleno. Funciona también con el movimiento reducido (salta sin animar). */
  function volarAlPunto(punto, zoom, op, relleno) {
    map.fitBounds([punto, punto], { ...op, padding: relleno, maxZoom: zoom });
  }
  // Mapa base: auto (según el tema), oscuro, claro o satelite. Solo recarga si cambia el estilo que se ve: setStyle borra
  // fuentes, capas, relieve y cielo (agregarCapas los rehace en style.load) y vuelve a pedir todas las teselas
  const estiloDe = (base) => BASES[base || baseSegunTema()];
  // El relieve es del mapa, no del estilo: si sigue puesto mientras carga el estilo nuevo, un cuadro intermedio lo dibuja
  // sin proyección y MapLibre lanza (TypeError en useProgram). Se quita antes; agregarCapas lo vuelve a poner en
  // style.load
  function cambiarEstilo(estilo) {
    try {
      if (map.getTerrain()) map.setTerrain(null);
    } catch { /* el estilo anterior todavía cargaba: aún no tenía relieve */ }
    map.setStyle(estilo, { diff: false });
  }
  function ponerBase(k) {
    $$('[data-base]', el).forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.base === k)));
    const antes = estiloDe(estado.base);
    estado.base = k === 'auto' ? null : k;
    if (estiloDe(estado.base) === antes) { pintarRampa(); return false; }
    cambiarEstilo(estiloDe(estado.base));
    return true;
  }
  function ponerRadio(k) {
    estado.radio = k;
    $$('[data-radio]', el).forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.radio === k)));
    actualizarHex();
  }

  function entrarZona() {
    if (estado.dibujo) return;
    estado.dibujo = true;
    estado.expandida = !movil.matches;
    popup.remove();
    pararGiro();
    if (movil.matches) plegarIzq(true);
    aplanar();
    hoja.classList.add('dibujando');
    $('#btn-zona', el)?.setAttribute('aria-pressed', 'true');
    repintarPuntos();
    abrirHoja();
  }
  function salirZona() {
    if (herramienta && herramienta.info().fase !== 'inactiva') herramienta.desactivar();
    clearTimeout(tDist);
    estado.turnoDist++;
    Object.assign(estado, { dibujo: false, zona: null, zonaCambiada: false, info: null, dist: null, faseVista: null });
    restaurar3d();
    aplicarVisibilidad();
    hoja.classList.remove('dibujando');
    $('#btn-zona', el)?.setAttribute('aria-pressed', 'false');
    repintarPuntos();
    pintarAreas();
    cerrarHoja();
    ponerUrl();
  }

  function empezarDibujo(modo = modoPreferido()) {
    entrarZona();
    aplanar(); // cada dibujo nuevo empieza con el mapa plano, también después de «Ver en 3D»
    estado.zona = null;
    estado.zonaCambiada = false;
    estado.dist = null;
    herramienta.activar(modo);
    pintarAreas();
  }

  function cargarAnillo(anillo, { guardada = null, editable = true, encuadre = true } = {}) {
    entrarZona();
    estado.zona = guardada;
    estado.zonaCambiada = false;
    estado.dist = null;
    herramienta.cargar(anillo, { editable, color: guardada?.color || PALETA[0] });
    pintarAreas();
    if (encuadre) encuadrar(anillo);
  }

  // La zona guardada: de la lista ya cargada o, si no está, de la API (lanza su error)
  async function traerArea(id) {
    return estado.areas.find((x) => x.id === +id) || api.get(`/api/areas/${+id}`);
  }
  async function abrirArea(id) {
    let a;
    try {
      a = await traerArea(id);
    } catch (err) { avisoError(err); return; }
    if (!el.isConnected) return;
    cargarAnillo(a.poligono, { guardada: a, editable: false });
  }

  // Lo que se cuenta en el navegador mientras se dibuja (sin consultar el servidor): `estado.datos.puntos` con su
  // coordenada guardada, [id, lat, lon, precisión, rural, lugar, reuniones, completitud]
  function contarDentro(anillo) {
    const clave = anillo.length >= 3 ? codificar(anillo) : '';
    if (clave === vivoClave && vivo) return vivo;
    const r = { n: 0, exactas: 0, aprox: 0, rural: 0, urbano: 0, reuniones: 0, comp: 0, lugares: new Map() };
    if (anillo.length >= 3) {
      let w = 180, s = 90, e = -180, n = -90;
      for (const [x, y] of anillo) { w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); }
      for (const p of estado.datos?.puntos || []) {
        const lon = p[2], lat = p[1];
        if (lon < w || lon > e || lat < s || lat > n || !dentro([lon, lat], anillo)) continue;
        r.n++;
        if (p[3] === 0) r.exactas++; else r.aprox++;
        if (p[4]) r.rural++; else r.urbano++;
        if (p[6] > 0) r.reuniones++;
        r.comp += p[7] || 0;
        r.lugares.set(p[5], (r.lugares.get(p[5]) || 0) + 1);
      }
    }
    vivoClave = clave;
    vivo = r;
    return r;
  }

  function cifras(i, c) {
    const km2 = i.area / 1e6;
    return html`<div class="zona-cifras">
      <div><b>${num(c.n)}</b><span>personas ubicadas dentro</span></div>
      <div><b>${i.n >= 3 ? formatoArea(i.area) : '—'}</b><span>área</span></div>
      <div><b>${i.n >= 2 ? formatoLargo(i.perimetro) : '—'}</b><span>perímetro</span></div>
      <div><b>${km2 > 0 ? num(Math.round(c.n / km2)) : '—'}</b><span>personas por km²</span></div>
    </div>`;
  }

  function nota(c) {
    const z = estado.datos ? Math.max(0, estado.datos.total - estado.datos.ubicadas) : null;
    return html`${num(c.exactas)} exactas · ${num(c.aprox)} aproximadas, contadas en el punto de su barrio o vereda (caen enteras dentro o fuera)${z != null ? html` · ${num(z)} sin ubicación, que no se cuentan` : ''}.`;
  }

  function vivoHtml(c) {
    const top = [...c.lugares.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
    return html`${c.n ? apilada([{ etiqueta: 'Casco urbano', valor: c.urbano, color: 'var(--s1)' }, { etiqueta: 'Rural', valor: c.rural, color: 'var(--s3)' }]) : ''}
      ${top.length ? html`<h4>Barrios y veredas</h4>${barras(top.map(([id, n]) => ({ etiqueta: nombreLugar(id), valor: n })), { total: c.n })}` : ''}
      ${c.n ? html`<p class="sec zona-nota">${num(c.reuniones)} asistieron a reuniones · completitud media ${num(Math.round(c.comp / c.n))} %</p>` : ''}`;
  }

  function mensajeZona(i) {
    if (i.cruza) return i.fase === 'dibujo' ? 'Los lados se cruzan' : 'Los lados se cruzan: mueva un punto o deshaga';
    if (i.bloqueada && i.fase === 'edicion') return i.mensaje || 'En 3D con relieve la zona solo se mira: vuelva a plano para mover sus puntos';
    return i.mensaje;
  }

  function renderZona() {
    cancelAnimationFrame(rafVivo); // un repintado pendiente traería datos de antes de este
    const i = estado.info;
    if (!i || i.fase === 'inactiva') return;
    estado.faseVista = `${i.fase}|${i.modo}|${!!estado.zona}`;
    const c = contarDentro(i.anillo);
    if (i.fase === 'dibujo') {
      const veredas = (estado.capasGeo?.veredas?.features || []).filter((f) => anilloMayor(f)).sort((a, b) => a.properties.nombre.localeCompare(b.properties.nombre));
      montar(detalle, html`<section class="zona-panel" data-fase="dibujo" aria-label="Medir zona">
        <div class="zona-cab"><h3>Medir zona · ${i.n} ${i.n === 1 ? 'punto' : 'puntos'}</h3>
          <button class="btn fantasma chico" type="button" data-z="cancelar" aria-label="Cerrar la herramienta de zonas">✕</button></div>
        <div class="segmentado zona-modos" role="group" aria-label="Modo de dibujo">${MODOS.map(([k, t]) =>
          html`<button type="button" data-zmodo="${k}" aria-pressed="${i.modo === k}">${t}</button>`)}</div>
        <div class="zona-botones">
          <button class="btn chico" type="button" data-z="deshacer" ${i.puedeDeshacer ? '' : 'disabled'}>Deshacer</button>
          ${i.modo === 'mira' ? html`<button class="btn chico oscuro" type="button" data-z="punto">+ Punto</button>` : ''}
          <button class="btn chico primario" type="button" data-z="terminar" ${i.puedeTerminar ? '' : 'disabled'}>Terminar</button>
          <button class="btn chico" type="button" data-z="cancelar">Cancelar</button>
        </div>
        <p class="zona-msg" role="status" aria-live="polite" id="zona-msg">${mensajeZona(i)}</p>
        <p class="sec zona-ayuda">${i.armado && i.modo === 'lazo' ? 'Lazo listo: ' : ''}${AYUDA[i.modo]}</p>
        <div id="zona-vivo-cifras">${cifras(i, c)}</div>
        <div class="zona-vivo" id="zona-vivo">${vivoHtml(c)}</div>
        <details class="zona-atajos"><summary>Atajos</summary><div class="fila">
          <button class="btn chico" type="button" data-z="hex" ${estado.hexSel ? '' : 'disabled'} title="${estado.hexSel ? '' : 'Primero toque un hexágono del mapa'}">Usar este hexágono</button>
          <select class="entrada" data-z-vereda aria-label="Usar vereda"><option value="">Usar vereda…</option>${veredas.map((f) => html`<option value="${f.properties.id}">${titulo(f.properties.nombre)}</option>`)}</select>
          <button class="btn chico" type="button" data-z="vista">Usar lo que se ve</button>
        </div></details>
      </section>`);
    } else {
      const guardada = estado.zona;
      const titulo_ = guardada ? guardada.nombre : 'Zona dibujada';
      montar(detalle, html`<section class="zona-panel ${estado.expandida ? 'expandida' : ''}" data-fase="${i.fase}" aria-label="${titulo_}">
        <div class="zona-cab"><h3>${titulo_}</h3>
          <button class="btn fantasma chico" type="button" data-z="cerrar" aria-label="Cerrar la zona">✕</button></div>
        <div id="zona-vivo-cifras">${cifras(i, c)}</div>
        <p class="zona-msg" role="status" aria-live="polite" id="zona-msg">${mensajeZona(i)}</p>
        <div class="zona-botones">
          ${i.fase === 'edicion' ? html`<button class="btn chico" type="button" data-z="deshacer" ${i.puedeDeshacer ? '' : 'disabled'}>Deshacer</button>` : html`<button class="btn chico" type="button" data-z="editar">Editar</button>`}
          <button class="btn chico" type="button" data-z="3d" aria-pressed="${!estado.plano}">${estado.plano ? 'Ver en 3D' : 'Volver a plano'}</button>
          <button class="btn chico" type="button" data-z="otra">Dibujar otra</button>
        </div>
        <button class="btn chico zona-expandir" type="button" data-z="expandir" aria-expanded="${estado.expandida}" aria-controls="zona-detalle">${estado.expandida ? 'Ocultar distribución' : 'Ver distribución'}</button>
        <div class="zona-detalle" id="zona-detalle">
          <p class="sec zona-nota" id="zona-nota">${nota(c)}</p>
          <div class="zona-vivo" id="zona-vivo">${vivoHtml(c)}</div>
          <div id="zona-dist">${distHtml()}</div>
          <div class="zona-acciones" id="zona-acciones">${accionesHtml()}</div>
        </div>
      </section>`);
    }
    medirHoja();
  }

  function accionesHtml() {
    const z = zonaParams();
    const listo = !!(z.area_id || z.poligono) && !estado.info?.cruza;
    const filtra = estado.soporteZona === true;
    const motivo = estado.soporteZona === false ? 'El servidor todavía no filtra por zona' : 'Espere la distribución';
    const enlace = `/personas?${new URLSearchParams({ ...estado.filtros, ...z })}`;
    return html`${listo && filtra ? html`<a class="btn chico" href="${enlace}" data-ruta>Ver en Habitantes</a>`
        : html`<button class="btn chico" type="button" disabled title="${motivo}">Ver en Habitantes</button>`}
      ${puede('exportar') ? html`<button class="btn chico" type="button" data-z="exportar" ${listo && filtra ? '' : 'disabled'} title="${filtra ? '' : motivo}">Exportar</button>` : ''}
      ${estado.zona ? html`${estado.zonaCambiada || estado.info?.fase === 'edicion' ? html`<button class="btn chico primario" type="button" data-z="guardar" ${listo ? '' : 'disabled'}>Guardar cambios</button>` : ''}
          <button class="btn chico" type="button" data-z="datos-zona">Nombre y asignación</button>
          <button class="btn chico peligro" type="button" data-z="borrar">Borrar</button>`
        : html`<button class="btn chico primario" type="button" data-z="guardar" ${listo ? '' : 'disabled'}>Guardar zona</button>`}`;
  }

  function actualizarZona() {
    const i = estado.info;
    if (!i || i.fase === 'inactiva' || !detalle.querySelector('.zona-panel')) return;
    if (estado.faseVista !== `${i.fase}|${i.modo}|${!!estado.zona}`) { renderZona(); return; }
    cancelAnimationFrame(rafVivo);
    // Con el dibujo lento (un celular modesto) entre este pedido y el cuadro puede llegar otro cambio: se pinta lo último
    rafVivo = requestAnimationFrame(() => {
      const i = estado.info;
      if (!el.isConnected || !i || i.fase === 'inactiva' || !detalle.querySelector('.zona-panel')) return;
      if (estado.faseVista !== `${i.fase}|${i.modo}|${!!estado.zona}`) { renderZona(); return; }
      const c = contarDentro(i.anillo);
      const msg = $('#zona-msg', el);
      if (msg) msg.textContent = mensajeZona(i);
      const h3 = $('.zona-panel[data-fase="dibujo"] .zona-cab h3', el);
      if (h3) h3.textContent = `Medir zona · ${i.n} ${i.n === 1 ? 'punto' : 'puntos'}`;
      const ayuda = $('.zona-panel[data-fase="dibujo"] .zona-ayuda', el);
      if (ayuda) ayuda.textContent = `${i.armado && i.modo === 'lazo' ? 'Lazo listo: ' : ''}${AYUDA[i.modo]}`;
      const set = (sel, on) => { const b = $(sel, el); if (b) b.disabled = !on; };
      set('[data-z="deshacer"]', i.puedeDeshacer);
      set('[data-z="terminar"]', i.puedeTerminar);
      const cif = $('#zona-vivo-cifras', el);
      if (cif) montar(cif, cifras(i, c));
      const v = $('#zona-vivo', el);
      if (v) montar(v, vivoHtml(c));
      const n = $('#zona-nota', el);
      if (n) montar(n, nota(c));
      const a = $('#zona-acciones', el);
      if (a) montar(a, accionesHtml());
    });
  }

  function distHtml() {
    const d = estado.dist;
    if (estado.info?.cruza) return html`<p class="zona-aviso">Mientras los lados se crucen no se pide la distribución.</p>`;
    if (!d) return html`<p class="sec">Calculando la distribución…</p>`;
    if (d.error) return html`<p class="zona-aviso">${d.error}</p>`;
    if (!('area' in d)) {
      return html`<p class="zona-aviso">El servidor todavía no filtra por zona: la distribución completa, «Ver en Habitantes» y
        «Exportar» llegan con esa actualización. Las cifras de arriba son las del navegador.</p>`;
    }
    const k = d.kpi || {};
    const total = esNumero(k.personas) ? k.personas : null;
    const area = d.area?.m2;
    const encabezado = html`<h4>Conteo oficial</h4><div class="zona-cifras">
        <div><b>${total != null ? num(total) : k.personas || '—'}</b><span>personas en la zona</span></div>
        <div><b>${esNumero(area) && total != null && area > 0 ? num(Math.round(total / (area / 1e6))) : '—'}</b><span>personas por km²</span></div>
      </div>${esNumero(d.sin_ubicacion) ? html`<p class="sec zona-nota">${num(d.sin_ubicacion)} personas con estos filtros no tienen ubicación y no se cuentan.</p>` : ''}`;
    if (d.pocas || total == null) return html`${encabezado}<p class="zona-aviso">Menos de 10 personas: no se muestran desgloses.</p>`;
    const items = (obj, nombres = {}) => Object.entries(obj || {}).filter(([, n]) => esNumero(n) && n > 0)
      .map(([c, n]) => ({ etiqueta: nombres[c] || (c === 'sin' || c === 'null' ? 'Sin dato' : titulo(String(c))), valor: n }))
      .sort((a, b) => b.valor - a.valor);
    const sexo = d.sexo || {};
    const puestos = (d.puestos || []).slice(0, 8).map((p) => ({ etiqueta: titulo(p.nombre || `Puesto ${p.codigo || p.id}`), valor: p.n }));
    const mesas = (d.mesas || []).length;
    const ab = d.abordaje || {}, au = d.autorizacion || {};
    return html`${encabezado}
      <h4>Sexo</h4>${apilada([{ etiqueta: SEXOS.F, valor: sexo.F || 0, color: 'var(--s2)' }, { etiqueta: SEXOS.M, valor: sexo.M || 0, color: 'var(--s1)' },
        { etiqueta: SEXOS.N, valor: sexo.N || 0, color: 'var(--s7)' }, { etiqueta: 'Sin dato', valor: sexo.sin || 0, color: 'var(--axis)' }])}
      <h4>Edades</h4>${piramide(d.edades || [])}
      <h4>Puestos y mesas</h4>${barras(puestos, { color: 'var(--s7)', total })}
      <p class="sec zona-nota">${num(k.con_puesto)} con puesto · ${num(k.con_mesa)} con mesa${mesas ? ` · ${num(mesas)} mesas distintas` : ''} · ${num(d.sin_puesto)} sin puesto</p>
      <h4>Cédula</h4>${apilada([{ etiqueta: 'Con cédula', valor: Math.max(0, total - (k.sin_cedula || 0)), color: 'var(--s3)' }, { etiqueta: 'Sin cédula', valor: k.sin_cedula || 0, color: 'var(--axis)' }])}
      <p class="sec zona-nota">${num(k.cedulas_verificadas)} cédulas verificadas</p>
      <h4>Abordaje</h4>${apilada(Object.entries(ESTADOS_ABORDAJE).map(([c, t], j) => ({ etiqueta: t, valor: ab[c] || 0, color: ['var(--axis)', 'var(--s4)', 'var(--s3)', 'var(--crit)'][j] || 'var(--s1)' })))}
      <h4>Autorización</h4>${apilada([['si', 'var(--s3)'], ['pendiente', 'var(--s4)'], ['no', 'var(--crit)'], ['por_confirmar', 'var(--s1)']].map(([c, color]) =>
        ({ etiqueta: ESTADOS_AUTORIZACION[c] || 'Por confirmar', valor: au[c] || 0, color })))}
      <h4>Fuentes</h4>${barras(items(d.fuentes, FUENTES_N), { color: 'var(--s1)', total })}
      ${(d.necesidades || []).length ? html`<h4>Necesidades</h4>${barras(d.necesidades.slice(0, 8).map((x) => ({ etiqueta: x.nombre, valor: x.n })), { color: 'var(--s2)', total })}` : ''}
      ${Object.entries(DEMOGRAFIA).filter(([c]) => items(d.demografia?.[c]).length).map(([c, t]) => html`<h4>${t}</h4>${barras(items(d.demografia[c]).slice(0, 6), { color: 'var(--s1)', total })}`)}
      ${(d.listas || []).length ? html`<h4>Listas</h4>${barras(d.listas.map((x) => ({ etiqueta: x.lista, valor: x.n })), { color: 'var(--s4)', total })}` : ''}
      ${d.sensibles ? Object.entries(d.sensibles).map(([c, x]) => html`<h4>${c}</h4>${barras(Object.entries(x || {}).map(([e, n]) => ({ etiqueta: e, valor: esNumero(n) ? n : 0 })), { color: 'var(--s5)' })}`) : ''}`;
  }

  function programarDistribucion() {
    clearTimeout(tDist);
    tDist = setTimeout(pedirDistribucion, 400);
  }
  async function pedirDistribucion() {
    const z = zonaParams();
    if (!z.area_id && !z.poligono) return;
    const turno = ++estado.turnoDist;
    if (estado.info?.cruza) { estado.dist = null; pintarDist(); return; }
    estado.dist = null;
    pintarDist();
    let d;
    try {
      d = await api.get('/api/indicadores', { ...estado.filtros, ...z, alcance: 'zona' });
    } catch (err) {
      if (turno !== estado.turnoDist || !el.isConnected) return;
      if (err?.estado === 401) return;
      estado.dist = { error: err?.message || 'No se pudo calcular la distribución' };
      pintarDist();
      return;
    }
    if (turno !== estado.turnoDist || !el.isConnected) return; // respuesta vieja: llegó otra después
    estado.dist = d;
    estado.soporteZona = 'area' in d;
    pintarDist();
  }
  function pintarDist() {
    const caja = $('#zona-dist', el);
    if (caja) montar(caja, distHtml());
    const a = $('#zona-acciones', el);
    if (a) montar(a, accionesHtml());
  }

  // ── Usar vereda / hexágono / lo que se ve ──
  // El anillo abierto con 150 vértices o menos (Douglas-Peucker en grados, subiendo la tolerancia ×1,5)
  function aMaximo(anillo) {
    const abierto = anillo.slice();
    if (abierto.length > 1 && abierto[0][0] === abierto[abierto.length - 1][0] && abierto[0][1] === abierto[abierto.length - 1][1]) abierto.pop();
    let a = abierto, tol = 1e-5;
    while (a.length > MAX_VERTICES) { a = simplificar([...abierto, abierto[0]], tol).slice(0, -1); tol *= 1.5; }
    return a;
  }
  function usarAnillo(anillo, nombre) {
    if (!anillo || anillo.length < 3) { aviso('No hay un polígono que usar', 'error'); return; }
    const a = aMaximo(anillo).filter(([lon, lat]) => dentroDeYondo(lon, lat));
    if (a.length < 3) { aviso('Ese polígono queda fuera de Yondó', 'error'); return; }
    cargarAnillo(a);
    if (seCruza(a)) aviso(`${nombre}: los lados se cruzan; ajuste los puntos`, 'error');
  }
  function usarLoQueSeVe() {
    const b = map.getBounds();
    const w = Math.max(b.getWest(), RANGO_YONDO[0][0]), e = Math.min(b.getEast(), RANGO_YONDO[1][0]);
    const s = Math.max(b.getSouth(), RANGO_YONDO[0][1]), n = Math.min(b.getNorth(), RANGO_YONDO[1][1]);
    if (w >= e || s >= n) { aviso('La vista queda fuera de Yondó', 'error'); return; }
    entrarZona();
    estado.zona = null;
    estado.dist = null;
    herramienta.cargar([[w, s], [e, s], [e, n], [w, n]]);
  }

  // ── Guardar, editar datos y borrar ──
  async function guardarZona({ soloDatos = false } = {}) {
    const i = estado.info, z = estado.zona;
    if (!i || i.n < 3 || i.cruza) return;
    const asignados = new Set(z?.asignada_a || []);
    const usuarios = (estado.cat.usuarios || []).filter((u) => (u.rol === 'planillero' || u.rol === 'consultor') && (u.activo || asignados.has(u.id)));
    const color = z?.color || PALETA[0];
    const rol = (r) => (r === 'planillero' ? 'Planillero' : 'Consultor');
    const { el: d, cerrar } = dialogo({
      titulo: z ? (soloDatos ? 'Nombre y asignación' : 'Guardar cambios de la zona') : 'Guardar zona',
      cuerpo: html`<form id="f-zona" class="form-zona" novalidate>
        <label>Nombre<input class="entrada" name="nombre" required minlength="2" maxlength="80" autocomplete="off" value="${z?.nombre || ''}"></label>
        <label>Descripción<textarea class="entrada" name="descripcion" maxlength="500" rows="2">${z?.descripcion || ''}</textarea></label>
        <fieldset class="zona-paleta"><legend>Color</legend><div class="muestras">${PALETA.map((c) => html`<label title="${NOMBRES_COLOR[c]}"><input type="radio" name="color" value="${c}" ${c === color ? 'checked' : ''}><span class="color" style="background:${c}"></span><span class="sr">${NOMBRES_COLOR[c]}</span></label>`)}</div></fieldset>
        <fieldset><legend>Asignar a</legend><div class="zona-asignar">${usuarios.length ? usuarios.map((u) => html`<label><input type="checkbox" name="asignada_a" value="${u.id}" ${asignados.has(u.id) ? 'checked' : ''}> ${u.nombre || u.usuario} · ${rol(u.rol)}${u.activo ? '' : ' (inactivo)'}</label>`)
          : html`<p class="sec">No hay planilleros ni consultores. Se crean en Usuarios.</p>`}</div></fieldset>
        <p class="sec">${formatoArea(i.area)} · ${formatoLargo(i.perimetro)} de perímetro · ${i.n} puntos</p>
      </form>`,
      pie: html`<button class="btn" type="button" data-cerrar>Cancelar</button><button class="btn primario" type="submit" form="f-zona">Guardar</button>`,
    });
    const f = $('#f-zona', d);
    f.nombre.focus();
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      const avisos = $('.avisos', d);
      const nombre = f.nombre.value.trim();
      if (nombre.length < 2) { avisos.textContent = 'Escriba un nombre de al menos 2 letras'; f.nombre.focus(); return; }
      const cuerpo = { nombre, descripcion: f.descripcion.value.trim() || null, color: f.color.value || PALETA[0],
        asignada_a: $$('input[name="asignada_a"]:checked', f).map((x) => +x.value) };
      if (!z || !soloDatos) cuerpo.poligono = estado.info.anillo;
      const boton = $('button[type="submit"]', d);
      boton.disabled = true;
      try {
        const r = z ? await api.patch(`/api/areas/${z.id}`, cuerpo) : await api.post('/api/areas', cuerpo);
        estado.areas = [...estado.areas.filter((a) => a.id !== r.id), r].sort((a, b) => a.nombre.localeCompare(b.nombre));
        cerrar(true);
        aviso(z ? 'Zona actualizada' : 'Zona guardada');
        if (!el.isConnected) return;
        // Queda a la vista como zona guardada (se puede abrir con /mapa?area_id=…)
        cargarAnillo(r.poligono, { guardada: r, editable: false, encuadre: false });
      } catch (err) {
        boton.disabled = false;
        avisos.textContent = err?.message || 'No se pudo guardar';
      }
    });
  }

  async function borrarZona() {
    const z = estado.zona;
    if (!z) return;
    const asig = (z.asignados || []).length;
    if (!await confirmar(`¿Borrar la zona «${z.nombre}»?${asig ? ` Deja de estar asignada a ${asig} ${asig === 1 ? 'persona' : 'personas'} del equipo.` : ''} El dibujo sigue en el mapa hasta que lo cierre.`, { si: 'Borrar', peligro: true })) return;
    try {
      await api.del(`/api/areas/${z.id}`);
    } catch (err) { avisoError(err); return; }
    estado.areas = estado.areas.filter((a) => a.id !== z.id);
    aviso('Zona borrada');
    const anillo = anilloInfo();
    estado.zona = null;
    if (el.isConnected) cargarAnillo(anillo, { encuadre: false });
  }

  // ───────── Mapa ─────────
  pintarFiltrosAsistente(); // los de la URL que no tienen select (un enlace o el asistente que abrió el mapa con ellos)
  map.on('style.load', agregarCapas);
  map.on('load', async () => {
    clearInterval(empujar);
    try {
      estado.capasGeo = await api.get('/api/mapa/capas');
    } catch (err) {
      // Sin capas el mapa sigue sirviendo (puntos, hexágonos, el asistente con coordenadas): mejor que el cargador fijo
      if (!el.isConnected) return;
      avisoError(err);
      const vacia = () => ({ type: 'FeatureCollection', features: [] });
      estado.capasGeo = { limite: null, veredas: vacia(), lugares: vacia(), reuniones: vacia() };
    }
    if (!el.isConnected) return; // se salió del mapa mientras cargaba
    agregarCapas();
    if (gestiona) {
      herramienta = crearHerramientaZona(map, maplibregl, {
        dentro: dentroDeYondo,
        alCambiar(i) {
          const antes = estado.info;
          estado.info = i;
          if (estado.zona && i.fase === 'edicion') estado.zonaCambiada = i.n < 3 || codificar(i.anillo) !== estado.zona.codificado;
          if (!antes || antes.fase !== i.fase || antes.modo !== i.modo || !detalle.querySelector('.zona-panel')) renderZona();
          else actualizarZona();
        },
        alTerminar() {
          if (!estado.dibujo) return;
          ponerUrl();
          programarDistribucion();
        },
        alCancelar: salirZona,
      });
      window.__zona = herramienta;
      await cargarAreas();
      if (!el.isConnected) return;
    }
    try {
      await cargarDatos();
    } catch (err) {
      // Un filtro de la URL que la API rechaza (422) no deja el mapa a medias: se avisa y el aviso de filtros permite
      // quitarlo
      if (el.isConnected) avisoError(err);
    }
    if (!el.isConnected) return;
    $('#cargador', el).style.opacity = 0;
    setTimeout(() => $('#cargador', el)?.remove(), 450);
    if (herramienta && (zonaUrl.area_id || zonaUrl.poligono)) {
      // /mapa?area_id=3 abre una zona guardada; /mapa?poligono=… una dibujada
      if (zonaUrl.area_id) await abrirArea(zonaUrl.area_id);
      else {
        const a = decodificar(zonaUrl.poligono);
        if (a && a.length >= 3) cargarAnillo(a); else aviso('El polígono del enlace no se puede leer', 'error');
      }
      if (!el.isConnected) return;
    } else {
      if (estado.capasGeo.limite) map.fitBounds(cajaDe(estado.capasGeo.limite), { padding: 50, pitch: 52, bearing: -15, duration: 0 });
      tIntro = setTimeout(() => el.isConnected && !estado.dibujo && !estado.camaraTomada
        && map.flyTo({ ...CASCO, zoom: 13.2, pitch: 60, duration: 4200, essential: true }), 900);
    }
    // Listo: capas, zonas y puntos cargados. Lo que el asistente dejó en cola mientras tanto se aplica ahora, después de
    // programar la presentación (su primera acción de cámara la cancela)
    quitarControl = registrarMapa({ aplicar: aplicarAcciones, estado: instantanea });
  });
  let zPrev = 0;
  map.on('moveend', () => {
    resumenVista();
    const z = Math.round(map.getZoom() * 2);
    if (estado.radio === 'auto' && z !== zPrev) { zPrev = z; actualizarHex(); }
  });
  // Con una zona abierta, los clics de las capas no hacen nada (son para dibujar)
  map.on('click', 'hex-3d', (e) => {
    if (estado.dibujo) return;
    if (map.queryRenderedFeatures(e.point, { layers: ['puntos', 'reuniones', 'agente-puntos'].filter((l) => map.getLayer(l)) }).length) return;
    const f = e.features[0];
    mostrarHex(f.properties, e.lngLat, f.geometry?.coordinates?.[0]);
  });
  async function mostrarPersona(id, lngLat) {
    let p;
    try {
      p = await api.get(`/api/personas/${id}`, { resumen: 1 });
    } catch (err) { avisoError(err); return; }
    if (!el.isConnected || estado.dibujo) return;
    const lugar = p.lugar_nombre || p.direccion_norm || p.direccion;
    const datos = [SEXOS[p.sexo], p.rango_edad ? `${p.rango_edad} años` : null].filter(Boolean).join(' · ');
    const abordaje = ESTADOS_ABORDAJE[p.abordaje?.estado || p.abordaje] || null;
    popup.setLngLat(lngLat).setDOMContent(globo(html`<div class="globo-persona"><b>${p.nombre}</b>
      ${lugar ? html`<span class="sec">${titulo(lugar)}</span>` : ''}${datos ? html`<span class="sec">${datos}</span>` : ''}
      <span class="sec">Completitud ${num(p.completitud ?? 0)} %${abordaje ? ` · ${abordaje}` : ''}${p.consentimiento ? ` · ${ESTADOS_AUTORIZACION[p.consentimiento] || p.consentimiento}` : ''}</span>
      <a href="/personas/${id}" data-ruta>Abrir ficha →</a></div>`)).addTo(map);
  }
  map.on('click', 'puntos', (e) => {
    if (estado.dibujo) return;
    // Encima hay un punto resaltado por el asistente: lo atiende su capa (un solo globo, una sola consulta)
    if (map.getLayer('agente-puntos') && map.queryRenderedFeatures(e.point, { layers: ['agente-puntos'] }).length) return;
    mostrarPersona(e.features[0].properties.id, e.lngLat);
  });
  map.on('click', 'agente-puntos', (e) => {
    if (estado.dibujo) return;
    const id = e.features[0]?.properties?.id;
    if (idValido(id)) mostrarPersona(id, e.lngLat);
  });
  map.on('click', 'reuniones', (e) => {
    if (estado.dibujo) return;
    const r = e.features[0].properties;
    popup.setLngLat(e.lngLat).setDOMContent(globo(html`<b>${r.titulo}</b><br><span class="sec">${r.fecha} · ${r.n} asistentes</span><br><a href="/reuniones/${r.id}" data-ruta>Abrir →</a>`)).addTo(map);
  });
  for (const l of ['hex-3d', 'puntos', 'reuniones', 'agente-puntos']) {
    map.on('mouseenter', l, () => { if (!estado.dibujo) map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
  }

  // ───────── Controles ─────────
  el.addEventListener('change', async (e) => {
    const c = e.target.closest('[data-capa]');
    if (c) { estado.capas[c.dataset.capa] = c.checked; aplicarVisibilidad(); return; }
    if (e.target.id === 'zonas-guardadas') {
      if (e.target.value) await abrirArea(e.target.value);
      return;
    }
    if (e.target.matches('[data-z-vereda]')) {
      const id = +e.target.value;
      const f = (estado.capasGeo?.veredas?.features || []).find((x) => x.properties.id === id);
      e.target.value = '';
      if (f) usarAnillo(anilloMayor(f), titulo(f.properties.nombre));
      return;
    }
    const f = e.target.closest('[data-f]');
    if (f) {
      if (f.value) estado.filtros[f.dataset.f] = f.value; else delete estado.filtros[f.dataset.f];
      ponerUrl();
      pintarFiltrosAsistente();
      try { await cargarDatos(); } catch (err) { avisoError(err); }
    }
  });
  el.addEventListener('click', (e) => {
    if (e.target.closest('[data-quitar-asistente]')) { quitarFiltrosAsistente(); return; }
    const zm = e.target.closest('[data-zmodo]');
    if (zm && herramienta) { herramienta.activar(zm.dataset.zmodo); return; }
    const z = e.target.closest('[data-z]');
    if (z && herramienta) {
      const k = z.dataset.z;
      if (k === 'deshacer') herramienta.deshacer();
      else if (k === 'punto') herramienta.agregarCentro();
      else if (k === 'terminar') herramienta.terminar();
      else if (k === 'cancelar' || k === 'cerrar') salirZona();
      else if (k === 'otra') empezarDibujo(estado.info?.modo || modoPreferido());
      else if (k === 'editar') herramienta.editar();
      else if (k === 'hex') usarAnillo(estado.hexSel, 'El hexágono');
      else if (k === 'vista') usarLoQueSeVe();
      else if (k === '3d') { if (estado.plano) restaurar3d(45); else aplanar(); renderZona(); }
      else if (k === 'expandir') {
        estado.expandida = !estado.expandida;
        $('.zona-panel', el)?.classList.toggle('expandida', estado.expandida);
        z.setAttribute('aria-expanded', String(estado.expandida));
        z.textContent = estado.expandida ? 'Ocultar distribución' : 'Ver distribución';
        medirHoja();
      } else if (k === 'guardar') guardarZona();
      else if (k === 'datos-zona') guardarZona({ soloDatos: true });
      else if (k === 'borrar') borrarZona();
      else if (k === 'exportar') descargar('/api/exportar.xlsx', { ...estado.filtros, ...zonaParams() }).catch(avisoError);
      return;
    }
    if (e.target.closest('#cerrar-hoja')) { popup.remove(); cerrarHoja(); return; }
    if (e.target.closest('#plegar')) { plegarIzq(!izq.classList.contains('plegado')); return; }
    const b = e.target.closest('[data-radio]');
    if (b) { ponerRadio(b.dataset.radio); return; }
    const base = e.target.closest('[data-base]');
    if (base) { ponerBase(base.dataset.base); return; }
    const v = e.target.closest('[data-vista]');
    if (v) {
      const k = v.dataset.vista;
      if (RECORRIDOS.includes(k)) { cancelarPresentacion(); irVista(k); }
      else if (k === 'girar') {
        if (estado.dibujo) return;
        if (girando) pararGiro();
        else { cancelarPresentacion(); iniciarGiro(); }
      } else if (k === 'zona' && herramienta) {
        if (estado.dibujo) salirZona(); else empezarDibujo();
      }
    }
  });

  // ───────── Control del asistente (agente-mapa.js) ─────────
  // Cada acción responde {tipo, ok, …} o {tipo, ok: false, error} y `aplicar` nunca lanza. Lo validado aquí es lo que
  // el servidor ya validó: si algo no cumple, la acción falla con un motivo legible y el mapa no se toca.
  function exigirVista() { if (!el.isConnected) fallo('El mapa se cerró'); }
  function numero(v, nombre, min, max) {
    if (v === undefined || v === null) return undefined;
    if (!esNumero(v) || v < min || v > max) fallo(`${nombre}: un número entre ${min} y ${max}`);
    return v;
  }
  function siNo(v, nombre, defecto) {
    if (v === undefined || v === null) return defecto;
    if (typeof v !== 'boolean') fallo(`${nombre}: true o false`);
    return v;
  }
  // Espera un evento del mapa con tiempo límite: true si llegó, false si venció el plazo o se salió de la vista
  function esperar(evento, ms) {
    return new Promise((ok) => {
      let hecho = false;
      const fin = (llego) => {
        if (hecho) return;
        hecho = true;
        clearTimeout(reloj);
        map.off(evento, alEvento);
        esperas.delete(fin);
        ok(llego);
      };
      const alEvento = () => fin(true);
      const reloj = setTimeout(() => fin(false), ms);
      esperas.add(fin);
      map.once(evento, alEvento);
    });
  }
  // Tras pedir un movimiento: si animó, hasta su moveend; si fue un salto (movimiento reducido) o no cabía, ya terminó
  const trasMover = (ms) => (map.isMoving() ? esperar('moveend', ms) : Promise.resolve(true));
  const camara = () => ({ centro: map.getCenter().toArray().map((x) => +x.toFixed(6)), zoom: +map.getZoom().toFixed(2),
    pitch: Math.round(map.getPitch()), bearing: Math.round(map.getBearing()) });
  /** El rectángulo del panel del asistente si está abierto sobre el mapa (en el escritorio), o null. */
  function chatEncima() {
    const chat = document.getElementById('agente-panel');
    if (!chat || chat.hidden || movil.matches) return null;
    const c = chat.getBoundingClientRect(), caja = map.getContainer().getBoundingClientRect();
    const encima = c.width > 0 && c.left < caja.right && c.right > caja.left && c.top < caja.bottom && c.bottom > caja.top;
    return encima ? c : null;
  }
  // El relleno de los paneles (relleno()) y, en el escritorio, el del asistente si está abierto sobre el mapa. En un
  // escritorio angosto, entre el panel izquierdo y el del asistente casi no queda mapa: el izquierdo se pliega (vuelve
  // con «Capas y filtros»). Nunca tanto que no quepa el encuadre: MapLibre no mueve la cámara si el relleno no deja
  // espacio
  function rellenoAgente() {
    const r = { ...relleno() };
    const caja = map.getContainer().getBoundingClientRect();
    const c = chatEncima();
    if (c) {
      r.right = Math.max(r.right, caja.right - c.left + 16);
      if (caja.width - r.left - r.right < HUECO_AGENTE && !izq.classList.contains('plegado')) {
        plegarIzq(true);
        r.left = relleno().left;
      }
    }
    const fx = Math.min(1, (caja.width * 0.7) / Math.max(1, r.left + r.right));
    const fy = Math.min(1, (caja.height * 0.7) / Math.max(1, r.top + r.bottom));
    return { top: r.top * fy, bottom: r.bottom * fy, left: r.left * fx, right: r.right * fx };
  }

  // volar {lugar?: {id, nombre, tipo, lat, lon, poligono}, lat?, lon?, zoom?, pitch?, bearing?}: con polígono encuadra la
  // vereda entera (y la marca); si no, vuela a su punto
  async function accVolar(a) {
    const zoom = numero(a.zoom, 'zoom', 8, 19), pitch = numero(a.pitch, 'pitch', 0, 80), bearing = numero(a.bearing, 'bearing', -180, 180);
    let poligono = null, centro = null, zoomPunto = 15, lugar = null;
    if (a.lugar !== undefined && a.lugar !== null) {
      const l = a.lugar;
      if (!esObjeto(l) || !idValido(l.id)) fallo('volar: el lugar no es válido');
      lugar = { id: l.id, nombre: typeof l.nombre === 'string' ? titulo(l.nombre.slice(0, 120)) : null };
      if (l.poligono === true) {
        const f = (estado.capasGeo?.veredas?.features || []).find((x) => x?.properties?.id === l.id);
        if (f && anilloMayor(f)) poligono = f;
      }
      if (!poligono) {
        let lat = l.lat, lon = l.lon;
        if (!esNumero(lat) || !esNumero(lon)) {
          const p = (estado.capasGeo?.lugares?.features || []).find((x) => x?.properties?.id === l.id);
          [lon, lat] = p?.geometry?.coordinates || [];
        }
        if (!esNumero(lat) || !esNumero(lon) || !dentroDeYondo(lon, lat)) fallo(`${lugar.nombre || 'Ese lugar'} no tiene punto ni polígono en el mapa`);
        centro = [lon, lat];
        zoomPunto = l.tipo === 'barrio' ? 16.5 : 15;
      }
    } else {
      if (!esNumero(a.lat) || !esNumero(a.lon)) fallo('volar: falta el destino (un lugar, o lat y lon)');
      if (!dentroDeYondo(a.lon, a.lat)) fallo('Ese punto queda fuera de Yondó');
      centro = [a.lon, a.lat];
    }
    tomarCamara();
    const vista = { pitch: estado.plano ? 0 : pitch ?? map.getPitch(), bearing: bearing ?? map.getBearing(), duration: VUELO_MS };
    estado.foco = poligono ? { type: 'Feature', geometry: poligono.geometry, properties: { color: COLOR_AGENTE } } : null;
    pintarAgente();
    if (poligono) map.fitBounds(cajaDe(poligono), { ...vista, padding: rellenoAgente(), maxZoom: zoom ?? 15.5 });
    else if (chatEncima()) volarAlPunto(centro, zoom ?? zoomPunto, vista, rellenoAgente());
    else map.flyTo({ ...vista, center: centro, zoom: zoom ?? zoomPunto });
    await trasMover(VUELO_MS + 4000);
    exigirVista();
    return { ...camara(), ...(lugar ? { lugar } : {}), encuadre: poligono ? 'poligono' : 'punto' };
  }

  // filtros {valores: {clave: valor}, reemplazar}: los de Habitantes, con su URL; si la API los rechaza (422), vuelven
  // los de antes
  async function accFiltros(a) {
    const valores = a.valores ?? {};
    if (!esObjeto(valores)) fallo('filtros: valores debe ser un objeto');
    const claves = Object.keys(valores);
    if (claves.length > CLAVES_FILTRO.size) fallo('filtros: demasiadas claves');
    const nuevos = siNo(a.reemplazar, 'reemplazar', false) ? {} : { ...estado.filtros };
    for (const k of claves) {
      if (!CLAVES_FILTRO.has(k)) fallo(`Filtro no disponible en el mapa: ${k.slice(0, 40)}`);
      const v = valorFiltro(k, valores[k]);
      if (v === null) delete nuevos[k]; else nuevos[k] = v;
    }
    if (!mismosFiltros(nuevos, estado.filtros) || !estado.datos) {
      const antes = estado.filtros;
      estado.filtros = nuevos;
      alCambiarFiltros();
      try {
        await cargarDatos();
      } catch (err) {
        if (estado.filtros === nuevos) { estado.filtros = antes; alCambiarFiltros(); }
        throw err;
      }
    }
    return { filtros: { ...estado.filtros }, total: estado.datos?.total ?? null, ubicadas: estado.datos?.ubicadas ?? null };
  }

  // capas {valores: {calor?, columnas?, puntos?, veredas?, reuniones?, edificios?, relieve?, areas?}}: true o false
  function accCapas(a) {
    if (!esObjeto(a.valores)) fallo('capas: faltan los valores');
    const claves = Object.keys(a.valores);
    if (!claves.length) fallo('capas: indique al menos una capa');
    for (const k of claves) {
      if (!Object.hasOwn(estado.capas, k) || (k === 'areas' && !gestiona)) fallo(`Capa desconocida: ${k.slice(0, 40)}`);
      if (typeof a.valores[k] !== 'boolean') fallo(`La capa ${k} va con true o false`);
    }
    for (const k of claves) estado.capas[k] = a.valores[k];
    for (const c of $$('[data-capa]', el)) c.checked = !!estado.capas[c.dataset.capa];
    aplicarVisibilidad();
    const capas = { ...estado.capas };
    if (!gestiona) delete capas.areas;
    return { capas };
  }

  // base {base}: espera el estilo nuevo, así lo que sigue (resaltar, capas) ya encuentra sus capas
  async function accBase(a) {
    if (!BASES_OK.includes(a.base)) fallo('Mapa base: auto, oscuro, claro o satelite');
    const cambia = estiloDe(a.base === 'auto' ? null : a.base) !== estiloDe(estado.base);
    const listo = cambia ? esperar('style.load', 15000) : null;
    ponerBase(a.base);
    if (listo && !(await listo)) { exigirVista(); fallo('El mapa base no terminó de cargar'); }
    exigirVista();
    return { base: a.base, recargado: cambia };
  }

  function accHexagono(a) {
    const k = esNumero(a.tamano) ? String(a.tamano) : a.tamano;
    if (typeof k !== 'string' || !Object.hasOwn(RADIOS, k)) fallo('Tamaño del hexágono: auto, 150, 400 o 1000');
    ponerRadio(k);
    return { hexagono: k, radio_m: radioActual() };
  }

  async function accRecorrido(a) {
    if (!RECORRIDOS.includes(a.nombre)) fallo('Recorrido: municipio, casco o tigre');
    if (a.nombre === 'municipio' && !estado.capasGeo?.limite) fallo('El límite del municipio no está en el mapa');
    if (a.nombre === 'tigre' && !lugarTigre()) fallo('San Miguel del Tigre no tiene coordenada en el mapa');
    tomarCamara();
    irVista(a.nombre, chatEncima() ? rellenoAgente() : null);
    await trasMover(7000);
    exigirVista();
    return camara();
  }

  function accGiro(a) {
    const activo = siNo(a.activo, 'activo');
    if (activo === undefined) fallo('giro: falta activo (true o false)');
    if (activo) {
      if (estado.dibujo) fallo('Con una zona abierta el mapa no gira');
      cancelarPresentacion();
      iniciarGiro();
    } else pararGiro();
    return { giro: girando };
  }

  // resaltar {puntos: [{id?, lat, lon, etiqueta?}], color?, encuadrar?, sumar?}: como mucho MAX_IDS a la vez y en total;
  // los puntos fuera de Yondó se cuentan y no se pintan
  async function accResaltar(a) {
    if (!Array.isArray(a.puntos) || !a.puntos.length) fallo('resaltar: faltan los puntos');
    if (a.puntos.length > MAX_IDS) fallo(`resaltar: como mucho ${num(MAX_IDS)} puntos`);
    if (a.color != null && (typeof a.color !== 'string' || !COLOR_OK.test(a.color))) fallo('El color va como #rrggbb');
    const color = a.color ? a.color.toLowerCase() : COLOR_AGENTE;
    const encuadrar = siNo(a.encuadrar, 'encuadrar', true), sumar = siNo(a.sumar, 'sumar', false);
    const nuevos = [];
    let fuera = 0;
    for (const p of a.puntos) {
      if (!esObjeto(p) || !esNumero(p.lat) || !esNumero(p.lon) || !dentroDeYondo(p.lon, p.lat)) { fuera++; continue; }
      const props = { color };
      if (idValido(p.id)) props.id = p.id;
      const etiqueta = etiquetaSegura(p.etiqueta);
      if (etiqueta) props.etiqueta = etiqueta;
      nuevos.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [p.lon, p.lat] }, properties: props });
    }
    if (!nuevos.length) fallo('Ningún punto queda dentro de Yondó');
    estado.resalte = (sumar ? [...estado.resalte, ...nuevos] : nuevos).slice(-MAX_IDS);
    pintarAgente();
    if (encuadrar) {
      tomarCamara();
      map.fitBounds(cajaDe({ type: 'FeatureCollection', features: estado.resalte }), { padding: rellenoAgente(), maxZoom: 16.5, duration: 1600 });
      await trasMover(1600 + 4000);
      exigirVista();
    }
    return { resaltados: estado.resalte.length, nuevos: nuevos.length, fuera_de_yondo: fuera };
  }

  function accLimpiar(a) {
    const todo = siNo(a.todo, 'todo', false);
    estado.resalte = [];
    estado.foco = null;
    pintarAgente();
    popup.remove();
    if (!estado.dibujo) cerrarHoja();
    if (todo) {
      pararGiro();
      if (estado.dibujo) salirZona();
    }
    return { resaltados: 0 };
  }

  // zona {area_id? | lugar_id? | cerrar?}: abre como zona un área guardada o una vereda (con su distribución), o la cierra
  async function accZona(a) {
    if (!herramienta) fallo('Su rol no abre zonas en el mapa');
    const cerrar = siNo(a.cerrar, 'cerrar', false);
    if ([a.area_id != null, a.lugar_id != null, cerrar].filter(Boolean).length !== 1) fallo('zona: indique area_id, lugar_id o cerrar');
    if (cerrar) {
      if (estado.dibujo) salirZona();
      return { zona: null };
    }
    if (a.area_id != null) {
      if (!idValido(a.area_id)) fallo('zona: area_id no es válido');
      const area = await traerArea(a.area_id);
      exigirVista();
      if (!Array.isArray(area?.poligono) || area.poligono.length < 3) fallo('Esa zona guardada no tiene polígono');
      tomarCamara();
      cargarAnillo(area.poligono, { guardada: area, editable: false });
    } else {
      if (!idValido(a.lugar_id)) fallo('zona: lugar_id no es válido');
      const f = (estado.capasGeo?.veredas?.features || []).find((x) => x?.properties?.id === a.lugar_id);
      const anillo = f && anilloMayor(f);
      if (!anillo) fallo('Ese lugar no tiene polígono en el mapa: solo las veredas y el corregimiento');
      if (aMaximo(anillo).filter(([lon, lat]) => dentroDeYondo(lon, lat)).length < 3) fallo('Ese polígono queda fuera de Yondó');
      tomarCamara();
      usarAnillo(anillo, titulo(f.properties.nombre));
    }
    await trasMover(5000);
    exigirVista();
    const i = estado.info;
    return { zona: estado.zona ? { id: estado.zona.id, nombre: estado.zona.nombre } : null, fase: i?.fase ?? null,
      puntos: i?.n ?? 0, area_m2: Math.round(i?.area || 0), personas_navegador: i ? contarDentro(i.anillo).n : 0 };
  }

  // Lo que ve la persona, para el asistente (contexto de cada mensaje) y para las pruebas: cámara, base, capas, filtros
  // y cifras. Nunca nombres ni coordenadas de personas
  function instantanea() {
    const b = map.getBounds();
    const i = estado.dibujo ? estado.info : null;
    const capas = { ...estado.capas };
    if (!gestiona) delete capas.areas;
    return {
      ...camara(), base: estado.base || 'auto', capas, hexagono: estado.radio, radio_m: radioActual(),
      filtros: { ...estado.filtros }, total: estado.datos?.total ?? null, ubicadas: estado.datos?.ubicadas ?? null,
      en_pantalla: (estado.datos?.puntos || []).filter((p) => b.contains([p[2], p[1]])).length, giro: girando,
      resaltados: estado.resalte.length, foco: !!estado.foco,
      zona: i ? { id: estado.zona?.id ?? null, nombre: estado.zona?.nombre ?? null, fase: i.fase, puntos: i.n,
        area_m2: Math.round(i.area || 0), personas_navegador: contarDentro(i.anillo).n,
        personas_servidor: esNumero(estado.dist?.kpi?.personas) ? estado.dist.kpi.personas : null } : null,
    };
  }

  // Un Map y no un objeto: un `tipo` como «constructor» o «__proto__» no debe encontrar nada
  const ACCIONES = new Map(Object.entries({ volar: accVolar, filtros: accFiltros, capas: accCapas, base: accBase,
    hexagono: accHexagono, recorrido: accRecorrido, giro: accGiro, resaltar: accResaltar, limpiar: accLimpiar, zona: accZona }));
  async function aplicarAcciones(lista) {
    const out = [];
    for (const [i, a] of (Array.isArray(lista) ? lista.slice(0, 100) : []).entries()) {
      const tipo = esObjeto(a) && typeof a.tipo === 'string' ? a.tipo.slice(0, 40) : null;
      let reloj = 0;
      try {
        if (i >= MAX_ACCIONES) fallo(`Se aplican como mucho ${MAX_ACCIONES} acciones por vez`);
        exigirVista();
        const fn = tipo ? ACCIONES.get(tipo) : null;
        if (!fn) fallo(tipo ? `Acción desconocida: ${tipo}` : 'Acción no válida');
        const plazo = new Promise((_, mal) => { reloj = setTimeout(() => mal(new Error('La acción tardó demasiado')), PLAZO_ACCION_MS); });
        const r = await Promise.race([fn(a), plazo]);
        out.push({ ...(esObjeto(r) ? r : {}), tipo, ok: true });
      } catch (err) {
        out.push({ tipo, ok: false, error: (typeof err?.message === 'string' && err.message.slice(0, 200)) || 'No se pudo aplicar' });
      } finally {
        clearTimeout(reloj);
      }
    }
    return out;
  }
  const alTema = () => { if (!estado.base) cambiarEstilo(BASES[baseSegunTema()]); };
  window.addEventListener('tema', alTema);
  window.__mapa = map; // útil para depurar desde la consola (también la herramienta de zonas, en window.__zona)
  return () => {
    quitarControl?.(); // el asistente ya no aplica aquí: la próxima acción vuelve a abrir el mapa
    clearTimeout(tIntro);
    clearInterval(empujar);
    estado.turnoDatos++; // una respuesta de puntos en camino ya no pinta nada
    for (const fin of [...esperas]) fin(false);
    girando = false;
    cancelAnimationFrame(rafGiro);
    cancelAnimationFrame(rafVivo);
    clearTimeout(tDist);
    estado.turnoDist++;
    ro.disconnect();
    movil.removeEventListener('change', medirHoja);
    window.removeEventListener('tema', alTema);
    popup.remove();
    herramienta?.destruir();
    map.remove();
    delete window.__mapa;
    delete window.__zona;
  };
}
