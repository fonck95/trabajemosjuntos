// Mando a distancia de la presentación. La vista Presentación del panel del equipo (admin/web/js/vistas/presentacion.js)
// la muestra en un <iframe> y el asistente del panel la maneja: ir a un capítulo y paso, avanzar o retroceder y mostrar
// su explicación en un subtítulo. Las órdenes llegan por postMessage y aquí se valida todo, porque vienen de otra página:
// * Solo dentro de un iframe (window.parent !== window), del marco que la contiene (e.source === window.parent) y de un
//   origen permitido: el de esta misma página (el panel en /panel/ del servicio único) o el del panel desplegado aparte,
//   que scripts/build_site.py escribe en <meta name="panel-origen"> a partir de PANEL_URL (solo https). Las respuestas van
//   a ese mismo origen, nunca a '*': una página ajena que enmarque la presentación no recibe nada ni manda nada.
// * Cada mensaje es {canal: 'yondo-presentacion', v: 1, orden, id?, …}: con otro canal o versión se ignora; una orden que
//   no está en la lista, una clave de más, un capítulo o un paso que no existen o una explicación que no se ve tal cual
//   responden `error` y no mueven nada.
// * El subtítulo se pinta con textContent (nunca como HTML) y con las mismas reglas que pone el panel: sin caracteres que
//   no se ven, sin números de 7 o más dígitos ni «@» (se proyecta ante una sala).
// * Cada cambio de paso (también por el teclado o un clic) se le avisa al panel con el estado: capítulo, paso, total,
//   nombre del capítulo y título del paso. main.js lo anuncia con el evento `propuesta:paso`.
// main.js le entrega sus piezas (caps, estado, ir, vecino, abrirIndice, reencuadrar) al final del arranque: así este
// módulo no depende de la escena 3D y se prueba con Node (admin/tests/test_agente_presentacion.py).
export const CANAL = 'yondo-presentacion';
export const VERSION = 1;
export const MAX_EXPLICACION = 400;   // `MAX_EXPLICACION` de la herramienta y del puente del panel: una prueba los compara
const ID = /^[a-z_]{2,40}$/;
const ORIGEN = /^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/;
const ORIGEN_HTTPS = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/;
// Lo que el subtítulo no muestra (`_explicacion_visible` de admin/app/agente/herramientas/interfaz.py): de control, de
// formato (marcas de dirección, ancho cero), separadores de línea, sustitutos sueltos, de uso privado, sin asignar, los
// rellenos que se ven como nada y los selectores de variante; más de dos acentos apilados; 7 dígitos o más; «@»
const NO_SE_VE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\u{34f}\u{115f}\u{1160}\u{17b4}\u{17b5}\u{2800}\u{3164}\u{ffa0}\u{180b}-\u{180f}\u{fe00}-\u{fe0f}\u{e0000}-\u{e0fff}]/u;
const ACENTOS = /[\p{Mn}\p{Me}]{3,}/u;
const DIGITOS = /\p{Nd}(?:[ .-]?\p{Nd}){6,}/u;
// Claves que admite cada orden (además de canal, v, orden e id)
const CLAVES = new Map([
  ['ir', ['capitulo', 'paso', 'explicacion']], ['avanzar', ['d', 'explicacion']], ['explicar', ['explicacion']],
  ['quitar_explicacion', []], ['estado', []],
]);

/** La explicación lista para el subtítulo (los espacios seguidos quedan en uno, como los pinta el navegador), o null si
 * no se puede mostrar tal cual: no es texto, está vacía, pasa de MAX_EXPLICACION o trae lo que NO_SE_VE, ACENTOS o
 * DIGITOS prohíben, o una «@». */
export function textoVisible(v) {
  if (typeof v !== 'string' || NO_SE_VE.test(v) || ACENTOS.test(v)) return null;
  const t = v.replace(/\s+/g, ' ').trim();
  if (!t || [...t].length > MAX_EXPLICACION || DIGITOS.test(t) || t.includes('@')) return null;
  return t;
}

/** Los orígenes de los que se aceptan órdenes y a los que se responde: el de la página (si es http o https; nunca
 * «null») y el del panel de <meta name="panel-origen"> si es un origen https limpio. */
export function origenesPermitidos(ventana, documento) {
  const out = new Set();
  const propio = ventana?.location?.origin;
  if (typeof propio === 'string' && ORIGEN.test(propio)) out.add(propio);
  const panel = documento?.querySelector?.('meta[name="panel-origen"]')?.content;
  if (typeof panel === 'string' && ORIGEN_HTTPS.test(panel)) out.add(panel);
  return out;
}

// Un nombre o un título para el panel: sin los espacios que no se cortan ni las uniones de palabras de build_propuesta.py
const limpio = (t, n) => String(t ?? '').replace(/[\xa0\u{202f}]/gu, ' ').replace(/[\u{2060}\xad]/gu, '')
  .replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim().slice(0, n);

/** Monta el mando si la presentación está dentro de un iframe; si no, no escucha nada y devuelve null. Devuelve
 * {subtitulo(texto|null), estado()} (para las pruebas y por si main.js lo necesita). */
export function montarMando({ caps, estado, ir, vecino, abrirIndice = () => {}, reencuadrar = () => {},
  ventana = globalThis.window, documento = globalThis.document } = {}) {
  if (!ventana || !documento || !Array.isArray(caps) || !estado || typeof ir !== 'function' || typeof vecino !== 'function') return null;
  let padre = null;
  try { padre = ventana.parent; } catch { return null; }
  if (!padre || padre === ventana) return null;   // sola, la presentación no recibe órdenes de nadie
  const permitidos = origenesPermitidos(ventana, documento);
  if (!permitidos.size) return null;
  const pres = documento.querySelector('#pres'), sub = documento.querySelector('.subtitulo'), texto = sub?.querySelector('p');
  const leyenda = documento.querySelector('.leyenda3d'), panel = documento.querySelector('.panel');
  const chica = ventana.matchMedia?.('(max-width: 1080px)');   // la misma frontera de propuesta.html y escena.js
  let listo = false;
  let origenPadre = null;       // el del panel que mandó la última orden válida: a él van los avisos siguientes
  let pasoDelSubtitulo = null;  // «capitulo/paso» al que corresponde la explicación en pantalla

  // Dentro del panel, los enlaces de la barra (el Home, el atlas) abren otra pestaña: si no, el iframe dejaría la
  // presentación y el asistente ya no la podría manejar
  for (const a of documento.querySelectorAll('.barra a[href]')) { a.target = '_blank'; a.rel = 'noopener'; }

  const clave = () => (caps[estado.ci] ? `${caps[estado.ci].id}/${estado.pi + 1}` : null);
  function actual() {
    const c = caps[estado.ci];
    if (!c) return { capitulo: null, paso: null, total: null, nombre: null, titulo: null, explicacion: false };
    const p = c.pasos[estado.pi] || {};
    return { capitulo: c.id, paso: estado.pi + 1, total: c.pasos.length, nombre: limpio(c.nombre, 80),
      titulo: limpio(p.titulo || c.nombre, 200), explicacion: !!sub?.classList.contains('visible') };
  }
  function enviar(msj, origen = null) {
    const destinos = origen ? [origen] : origenPadre ? [origenPadre] : [...permitidos];
    // A un origen que no es el del marco padre, el navegador no lo entrega: por eso se puede avisar a los dos permitidos
    for (const o of destinos) { try { padre.postMessage({ canal: CANAL, v: VERSION, ...msj }, o); } catch { /* el panel se fue */ } }
  }
  const responder = (id, tipo, origen, extra = {}) => enviar({ tipo, ...(id !== undefined ? { id } : {}), ...actual(), ...extra }, origen);

  // Junto a la leyenda (abajo a la derecha en pantalla grande): el subtítulo le deja su ancho o, si así no le queda
  // lugar, se pone encima de ella
  function medir() {
    if (!pres) return;
    const conLeyenda = !!leyenda?.childElementCount && !chica?.matches;
    const l = conLeyenda ? leyenda.getBoundingClientRect() : null;
    pres.style.setProperty('--ley-w', l ? `${Math.ceil(l.width + 12)}px` : '0px');
    pres.style.setProperty('--ley-h', l ? `${Math.ceil(l.height)}px` : '0px');
    const p = panel && !pres.classList.contains('sin-panel') ? panel.getBoundingClientRect() : null;
    const libre = (ventana.innerWidth || 0) - (p ? p.right + 16 : 100) - (l ? l.width + 28 : 16);
    pres.classList.toggle('sub-sobre-leyenda', !!l && libre < 320);
  }
  function subtitulo(t, paso = clave()) {
    if (!sub || !texto) return;
    const antes = sub.classList.contains('visible');
    if (t) {
      texto.textContent = t;
      sub.classList.add('visible');
      pasoDelSubtitulo = paso;
    } else {
      sub.classList.remove('visible');   // el texto se queda mientras se desvanece
      pasoDelSubtitulo = null;
    }
    medir();
    // En la pantalla chica el subtítulo le quita alto a la maqueta: la cámara vuelve a encuadrar (si nadie la movió)
    if (antes !== !!t && chica?.matches) reencuadrar();
  }

  async function atender(m, origen) {
    const id = Number.isInteger(m.id) && m.id >= 0 && m.id <= 2 ** 31 ? m.id : undefined;
    const fallo = (error) => responder(id, 'error', origen, { error });
    if (typeof m.orden !== 'string' || !CLAVES.has(m.orden)) return fallo('La presentación no conoce esa orden');
    const permitidas = new Set(['canal', 'v', 'orden', 'id', ...CLAVES.get(m.orden)]);
    if (Object.keys(m).some((k) => !permitidas.has(k))) return fallo('La orden trae datos que la presentación no usa');
    let explicacion = null;
    if (m.explicacion !== undefined) {
      explicacion = textoVisible(m.explicacion);
      if (!explicacion) return fallo('La explicación no se puede mostrar tal como es');
    }
    if (m.orden === 'estado') return responder(id, 'estado', origen);
    if (m.orden === 'explicar' || m.orden === 'quitar_explicacion') {
      if (m.orden === 'explicar' && !explicacion) return fallo('Falta la explicación');
      subtitulo(explicacion);
      return responder(id, 'estado', origen);
    }
    let destino;
    if (m.orden === 'ir') {
      const ci = typeof m.capitulo === 'string' && ID.test(m.capitulo) ? caps.findIndex((c) => c.id === m.capitulo) : -1;
      if (ci < 0) return fallo('La presentación no tiene ese capítulo');
      const paso = m.paso === undefined ? 1 : m.paso;
      if (!Number.isInteger(paso) || paso < 1 || paso > caps[ci].pasos.length) return fallo('Ese capítulo no tiene ese paso');
      destino = [ci, paso - 1];
    } else {
      if (m.d !== 1 && m.d !== -1) return fallo('Se avanza de a un paso: 1 o -1');
      if (!caps[estado.ci]) return fallo('La presentación todavía no muestra ningún paso');
      destino = vecino(estado.ci, estado.pi, m.d);
    }
    const [ci, pi] = destino;
    // La explicación va antes del paso: el encuadre del paso nuevo ya le deja su lugar. Sin explicación nueva, la del
    // paso anterior se quita al cambiar de paso (ver `propuesta:paso`)
    if (explicacion) subtitulo(explicacion, `${caps[ci].id}/${pi + 1}`);
    abrirIndice(false);
    const dir = m.orden === 'avanzar' ? m.d : ci < estado.ci || (ci === estado.ci && pi < estado.pi) ? -1 : 1;
    await ir(ci, pi, { dir });
    return responder(id, 'estado', origen);
  }

  ventana.addEventListener('message', (e) => {
    if (e.source !== padre || !permitidos.has(e.origin)) return;
    const m = e.data;
    if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
    origenPadre = e.origin;
    atender(m, e.origin).catch(() => responder(undefined, 'error', e.origin, { error: 'La presentación no pudo aplicar la orden' }));
  });
  ventana.addEventListener('propuesta:paso', () => {
    if (pasoDelSubtitulo && pasoDelSubtitulo !== clave()) subtitulo(null);
    medir();
    enviar({ tipo: listo ? 'estado' : 'listo', ...actual() });
    listo = true;
  });
  let tMedir = 0;
  ventana.addEventListener('resize', () => { clearTimeout(tMedir); tMedir = setTimeout(medir, 120); });
  if (caps[estado.ci]) { listo = true; enviar({ tipo: 'listo', ...actual() }); }
  return { subtitulo, estado: actual };
}
