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
//   nombre del capítulo, título del paso y la explicación a la vista. main.js lo anuncia con el evento `propuesta:paso`.
// main.js le entrega sus piezas (caps, estado, ir, vecino, abrirIndice, reencuadrar) al final del arranque: así este
// módulo no depende de la escena 3D y se prueba con Node (admin/tests/test_agente_presentacion.py).
export const CANAL = 'yondo-presentacion';
export const VERSION = 1;
export const MAX_EXPLICACION = 220;   // `MAX_EXPLICACION` de la herramienta y del puente del panel: una prueba los compara
const ID = /^[a-z_]{2,40}$/;
const ORIGEN = /^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/;
const ORIGEN_HTTPS = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/i;
// Lo que el subtítulo no muestra (`_explicacion_visible` de admin/app/agente/herramientas/interfaz.py, con las mismas
// reglas): de control, de formato (marcas de dirección, ancho cero), separadores de línea, sustitutos sueltos, de uso
// privado, sin asignar, los rellenos que se ven como nada y los selectores de variante; más de dos acentos apilados; y,
// en la forma NFKC del texto (así «＠», los dígitos en superíndice o de ancho completo y los guiones de compatibilidad
// cuentan como los comunes), una «@» o un número de 7 dígitos o más, también por grupos (TIRADA: con espacios, guiones,
// rayas, barras, paréntesis, o pegados con punto, coma o «_»), salvo un periodo («2028-2031») o un rango de cifras de la
// propuesta de menor a mayor («$116.294 – 210.000 M»). Antes se quitan las fechas que existen (FECHA: «15/11/2026»,
// «2026-11-15», de 1900 a 2099): cada una corta la tirada
const NO_SE_VE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\u{34f}\u{115f}\u{1160}\u{17b4}\u{17b5}\u{2800}\u{3164}\u{ffa0}\u{180b}-\u{180f}\u{fe00}-\u{fe0f}\u{e0000}-\u{e0fff}]/u;
const ACENTOS = /[\p{Mn}\p{Me}]{3,}/u;
const TIRADA = /\p{Nd}+(?:(?:[.,_\u00b7(]|\) ?|\)? ?[\-\u2010-\u2015\u2212\/] ?\(?| )\p{Nd}+)*/gu;
const PERIODO = /^((?:19|20)[0-9]{2}) ?[\-\u2010-\u2015\u2212\/] ?((?:19|20)[0-9]{2})$/u;
const RANGO = /^([0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?) ?[\-\u2010-\u2015\u2212] ?([0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?)$/u;
const FECHA = /(?<!\p{Nd})(?:([0-9]{4}) ?([.\-\u2010-\u2015\u2212\/]) ?([0-9]{1,2}) ?\2 ?([0-9]{1,2})|([0-9]{1,2}) ?([.\-\u2010-\u2015\u2212\/]) ?([0-9]{1,2}) ?\6 ?([0-9]{4}))(?!\p{Nd})/gu;
// Un monto en pesos con su signo y sus puntos de miles («$1.156.350», el costo por habitante del guion): la tirada
// va justo después de «$», en grupos de tres y con 7 cifras enteras a lo sumo (`_MONTO` de la herramienta): una cédula
// o un teléfono de 8 o más dígitos no pasa por llevar «$» delante
const MONTO = /^(?:[0-9]{1,3}|[0-9]\.[0-9]{3})\.[0-9]{3}(?:,[0-9]{1,2})?$/u;
const DIGITOS_MAX = 6;
// La pantalla chica (`acomodar`): la franja mínima donde escena.js encuadra la obra (`zonaPx`), el alto mínimo de la
// hoja inferior con el subtítulo (el de propuesta.html: el título del paso a la vista), el que no se pasa nunca (el
// asa y el comienzo del título) y los pasos de la letra del subtítulo, de la suya a la más chica
const FRANJA = 90;
const HOJA_MIN = 96;
const HOJA_PISO = 56;
const ESCALAS = [1, 0.93, 0.86, 0.8, 0.75];
// Claves que admite cada orden (además de canal, v, orden e id)
const CLAVES = new Map([
  ['ir', ['capitulo', 'paso', 'explicacion']], ['avanzar', ['d', 'explicacion']], ['explicar', ['explicacion']],
  ['quitar_explicacion', []], ['estado', []],
]);

const cifra = (t) => Number(t.replace(/\./g, '').replace(',', '.'));

/** ¿Es la fecha de FECHA un día que existe, de 1900 a 2099? («31/02/2026» no: se mira como cualquier número) */
function esFecha(m) {
  const [a, mes, dia] = (m[1] ? [m[1], m[3], m[4]] : [m[8], m[7], m[5]]).map(Number);
  const f = new Date(Date.UTC(a, mes - 1, dia));
  return a >= 1900 && a <= 2099 && f.getUTCFullYear() === a && f.getUTCMonth() === mes - 1 && f.getUTCDate() === dia;
}

/** ¿Trae `t` (en NFKC y con los espacios en uno) un número de más de DIGITOS_MAX dígitos que no es un periodo, un rango
 * de cifras, una fecha ni un monto en pesos? (las fechas que existen se quitan antes y cortan la tirada) */
function numeroLargo(t) {
  t = t.replace(FECHA, (...m) => (esFecha(m) ? ' | ' : m[0]));
  for (const { 0: tirada, index } of t.matchAll(TIRADA)) {
    if (tirada.match(/\p{Nd}/gu).length <= DIGITOS_MAX) continue;
    if (/\$ ?$/u.test(t.slice(0, index)) && MONTO.test(tirada)) continue;
    const p = PERIODO.exec(tirada);
    if (p && Number(p[1]) <= Number(p[2])) continue;
    const r = RANGO.exec(tirada);
    if (r && cifra(r[1]) <= cifra(r[2])) continue;
    return true;
  }
  return false;
}

/** La explicación lista para el subtítulo (los espacios seguidos quedan en uno, como los pinta el navegador; sin NFKC:
 * se muestra como vino), o null si no se puede mostrar tal cual: no es texto, está vacía, pasa de MAX_EXPLICACION o trae
 * lo que NO_SE_VE o ACENTOS prohíben, una «@» o un número largo. */
export function textoVisible(v) {
  if (typeof v !== 'string' || NO_SE_VE.test(v) || ACENTOS.test(v)) return null;
  const t = v.replace(/\s+/g, ' ').trim();
  if (!t || [...t].length > MAX_EXPLICACION) return null;
  const k = t.normalize('NFKC').replace(/\s+/g, ' ').trim();
  return k.includes('@') || numeroLargo(k) ? null : t;
}

/** Los orígenes de los que se aceptan órdenes y a los que se responde: el de la página (si es http o https; nunca
 * «null») y el del panel de <meta name="panel-origen"> si es un origen https limpio, escrito como lo entrega el
 * navegador en `e.origin` (el host en minúsculas y sin «:443»; build_site.py ya lo escribe así): con «Panel.example» o
 * «:443» tal cual, ninguna orden pasaría el filtro y la presentación igual avisaría «listo». */
export function origenesPermitidos(ventana, documento) {
  const out = new Set();
  const propio = ventana?.location?.origin;
  if (typeof propio === 'string' && ORIGEN.test(propio)) out.add(propio);
  const panel = documento?.querySelector?.('meta[name="panel-origen"]')?.content;
  if (typeof panel === 'string' && ORIGEN_HTTPS.test(panel)) {
    let origen = null;
    try { origen = new URL(panel).origin; } catch { origen = null; }
    if (typeof origen === 'string' && ORIGEN_HTTPS.test(origen)) out.add(origen);
  }
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
  const barra = documento.querySelector('.barra'), riel = documento.querySelector('.riel'), herr = documento.querySelector('.herr');
  const chica = ventana.matchMedia?.('(max-width: 1080px)');   // la misma frontera de propuesta.html y escena.js
  // el celular o la tableta en horizontal: el panel va de lado (propuesta.html)
  const deLado = ventana.matchMedia?.('(max-width: 1080px) and (orientation: landscape) and (max-height: 560px)');
  let listo = false;
  let origenPadre = null;       // el del panel que mandó la última orden válida: a él van los avisos siguientes
  let pasoDelSubtitulo = null;  // «capitulo/paso» al que corresponde la explicación en pantalla

  // Dentro del panel, los enlaces de la barra (el Home, el atlas) abren otra pestaña: si no, el iframe dejaría la
  // presentación y el asistente ya no la podría manejar
  for (const a of documento.querySelectorAll('.barra a[href]')) { a.target = '_blank'; a.rel = 'noopener'; }

  const clave = () => (caps[estado.ci] ? `${caps[estado.ci].id}/${estado.pi + 1}` : null);
  // El estado lleva la explicación que está a la vista (`texto`, la que pintó `subtitulo`): la pestaña del chat que sigue
  // a la ventana del proyector pone la misma, no la última que mandó ella (podía ser vieja o de otra pestaña)
  function actual() {
    const c = caps[estado.ci];
    if (!c) return { capitulo: null, paso: null, total: null, nombre: null, titulo: null, explicacion: false, texto: null };
    const p = c.pasos[estado.pi] || {};
    const visible = !!sub?.classList.contains('visible');
    return { capitulo: c.id, paso: estado.pi + 1, total: c.pasos.length, nombre: limpio(c.nombre, 80),
      titulo: limpio(p.titulo || c.nombre, 200), explicacion: visible, texto: visible ? texto?.textContent ?? null : null };
  }
  function enviar(msj, origen = null) {
    const destinos = origen ? [origen] : origenPadre ? [origenPadre] : [...permitidos];
    // A un origen que no es el del marco padre, el navegador no lo entrega: por eso se puede avisar a los dos permitidos
    for (const o of destinos) { try { padre.postMessage({ canal: CANAL, v: VERSION, ...msj }, o); } catch { /* el panel se fue */ } }
  }
  const responder = (id, tipo, origen, extra = {}) => enviar({ tipo, ...(id !== undefined ? { id } : {}), ...actual(), ...extra }, origen);

  // Junto a la leyenda (abajo a la derecha en pantalla grande): el subtítulo le deja su ancho o, si así no le queda
  // lugar o la explicación pasaría de tres renglones (una columna angosta y alta), se pone encima de ella, con todo el
  // ancho. Y dice si está a la vista y cuánto mide (.con-sub, --sub-h): en el celular la hoja inferior le cede ese alto
  // (propuesta.html), así se ve entero sin taparla. En la pantalla chica, además, se acomoda (`acomodar`)
  function medir() {
    if (!pres) return;
    const conLeyenda = !!leyenda?.childElementCount && !chica?.matches;
    const l = conLeyenda ? leyenda.getBoundingClientRect() : null;
    pres.style.setProperty('--ley-w', l ? `${Math.ceil(l.width + 12)}px` : '0px');
    pres.style.setProperty('--ley-h', l ? `${Math.ceil(l.height)}px` : '0px');
    const p = panel && !pres.classList.contains('sin-panel') ? panel.getBoundingClientRect() : null;
    const libre = (ventana.innerWidth || 0) - (p ? p.right + 16 : 100) - (l ? l.width + 28 : 16);
    const visible = !!sub?.classList.contains('visible');
    let sobre = !!l && libre < 320;
    if (l && !sobre && visible) {
      // se mide al lado de la leyenda (sin la clase), así la decisión no depende de dónde estaba
      pres.classList.remove('sub-sobre-leyenda');
      sobre = renglones() > 3;
    }
    pres.classList.toggle('sub-sobre-leyenda', sobre);
    pres.classList.toggle('con-sub', visible);
    if (chica?.matches) acomodar(visible);
    else for (const v of ['--sub-esc', '--hoja-min', '--sobre-sub', '--herr-w']) pres.style.removeProperty(v);
    const alto = visible ? sub.offsetHeight || 0 : 0;
    pres.style.setProperty('--sub-h', `${Math.ceil(alto)}px`);
  }

  // En la pantalla chica la explicación no puede tapar la franja donde escena.js encuadra la obra (`zonaPx`: bajo la
  // barra, la fila de capítulos y la leyenda de arriba, y nunca menos de FRANJA de alto). Se le reserva esa franja
  // encima (--sobre-sub: la hoja inferior baja lo que haga falta, propuesta.html) y, si así no cabe entera (la hoja en su
  // mínimo o, de lado, el alto entre esa franja y el control), se achica su letra un paso cada vez (--sub-esc). Si ni
  // con la más chica cabe, en vertical la hoja baja de su mínimo (--hoja-min): la obra y la explicación entera mandan.
  // Las medidas son las que no dependen de transiciones ni de transformaciones (offsetTop, offsetHeight)
  function acomodar(visible) {
    for (const v of ['--sub-esc', '--hoja-min']) pres.style.removeProperty(v);
    const lado = !!deLado?.matches;
    // De lado, la leyenda plegada va en la barra, a la izquierda de las herramientas
    pres.style.setProperty('--herr-w', lado && herr ? `${Math.ceil(herr.getBoundingClientRect().width)}px` : '0px');
    const H = ventana.innerHeight || 0, W = ventana.innerWidth || 0;
    const caja = (el) => el?.getBoundingClientRect?.() || null;
    let y0 = 0;
    const b = caja(barra);
    if (b?.height) y0 = b.bottom + 6;
    const l = leyenda?.childElementCount ? caja(leyenda) : null;
    if (l?.height && l.top < H / 2) y0 = Math.max(y0, l.bottom + 6);
    const r = caja(riel);
    if (r?.width > W * 0.7 && r.height) y0 = Math.max(y0, r.bottom + 4);
    // la franja, los 8 px que escena.js deja sobre el subtítulo y 4 de margen (los bordes caen en fracciones de píxel)
    const reserva = Math.ceil(y0 + FRANJA + 12);
    pres.style.setProperty('--sobre-sub', `${reserva}px`);
    if (!visible) return;
    const enHoja = !lado && !pres.classList.contains('sin-panel');
    // el borde de abajo del subtítulo: sobre la hoja en su mínimo, o el suyo (fijo, sobre el control)
    const piso = enHoja ? caja(panel).bottom - HOJA_MIN - 8 : sub.offsetTop + sub.offsetHeight;
    for (const e of ESCALAS) {
      if (e < 1) pres.style.setProperty('--sub-esc', String(e));
      if (sub.offsetHeight <= piso - reserva) return;
    }
    if (enHoja) {
      const hoja = Math.floor(caja(panel).bottom - 8 - reserva - sub.offsetHeight);
      pres.style.setProperty('--hoja-min', `${Math.max(HOJA_PISO, hoja)}px`);
    }
  }
  function renglones() {
    const alto = texto?.getBoundingClientRect?.().height || 0;
    const linea = parseFloat(ventana.getComputedStyle?.(texto)?.lineHeight) || 0;
    return linea ? Math.round(alto / linea) : 0;
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
  // El ancho de la leyenda y del panel cambia sin `resize` (otra leyenda al cambiar de paso, el iframe que se angosta o se
  // ensancha cuando se abre o se pliega el asistente, una letra que termina de cargar): se vuelve a medir en el acto, antes
  // de pintar, y el subtítulo nunca queda un cuadro encima de la leyenda con la medida vieja. También el alto del
  // subtítulo (la letra que carga lo hace crecer): la hoja o el panel que le ceden lugar siguen su medida
  if (typeof ventana.ResizeObserver === 'function') {
    const ro = new ventana.ResizeObserver(() => medir());
    for (const x of [pres, leyenda, panel, sub]) if (x) ro.observe(x);
  }
  if (caps[estado.ci]) { listo = true; enviar({ tipo: 'listo', ...actual() }); }
  return { subtitulo, estado: actual };
}
