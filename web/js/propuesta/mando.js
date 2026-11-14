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
//   no se ven, sin números de 7 o más dígitos ni «@» y sin costos (se proyecta ante una sala, y la presentación que
//   maneja el panel es siempre la técnica, que no muestra plata).
// * `vista` cambia lo que se ve de la presentación sin cambiar de paso: el panel de texto (o «Solo 3D»), el índice, las
//   fichas y los botones de la presentación (la pantalla en off del panel, que nadie toca, los oculta). Sin controles
//   tampoco atiende el teclado (la presentación enfoca el índice al abrirlo y las flechas la moverían): solo le avisa al
//   panel de Escape (`tecla`), que allá devuelve la ventana.
// * `visual` (solo en la presentación técnica, ?modo=tecnica) cambia lo que se ve sin cambiar de paso: la cámara (camara,
//   rumbo, girar), la obra que enfoca (enfoque), hoy o con el proyecto (comparar), la ficha técnica de un componente
//   (detalle), un modelo del atlas a pantalla completa (inmersion) y el tema. Aquí se revisa la forma de cada valor (los
//   ids, las listas, los tipos); que el componente exista en el capítulo o la inmersión en el catálogo lo revisa
//   visual.js, que responde el error sin mover nada.
// * El recorrido narrado (admin/web/js/reproductor.js, en la página del panel que enmarca la presentación): `escena`
//   es una orden atómica (el paso, «Solo 3D», lo visual, el resaltado y la narración de una escena, con el título del
//   recorrido y su avance) que se valida entera antes de mover nada y responde cuando la imagen se asentó (el telón, el
//   panel, el vuelo de la cámara, el modelo del atlas): recién entonces pinta la narración en el subtítulo, frase por
//   frase, con textContent. `narracion` ilumina una frase (cuando la voz empieza a decirla), marca la pausa, dice si hay
//   voz o muestra la píldora «El asistente prepara la explicación…»; `cierre`, el resumen y «¿Preguntas?». Mientras suena
//   un recorrido, las flechas, la barra espaciadora, P y Escape (y los botones del control) no cambian de paso: se le
//   avisan al panel (`tecla`), que maneja el recorrido. Y si la persona mueve la presentación a mano (un paso, la
//   cámara), el estado que sale de ESE cambio lo dice (`por: 'persona'`; todos los demás, las respuestas a las órdenes
//   incluidas, llevan `por: 'orden'`): el recorrido se pausa. Es un aviso de lo que acaba de pasar, no un estado que
//   quede pegado: si no, la escena siguiente (o la misma, al seguir) se pausaba sola. Una escena que otra orden dejó
//   atrás (otra escena, quitar la explicación, explicar, ir o avanzar, el cierre) no resalta ni narra al asentarse:
//   responde `reemplazada` y no pinta una narración vieja sobre lo nuevo ni deja el teclado tomado.
// * Cada toque o tecla de la persona en la presentación (con controles) se le avisa al panel (`gesto`, a lo sumo uno por
//   segundo): la voz del recorrido vive en el panel y el navegador solo la deja hablar después de un gesto, que en la
//   ventana del proyector cae aquí dentro y no allá.
// * Cada cambio de paso (también por el teclado o un clic) se le avisa al panel con el estado: capítulo, paso, total,
//   nombre del capítulo, título del paso, la explicación a la vista y, en la técnica, lo visual. main.js lo anuncia con
//   el evento `propuesta:paso` (y visual.js, `propuesta:visual`).
// main.js le entrega sus piezas (caps, estado, ir, vecino, abrirIndice, abrirFichas, verPanel, reencuadrar y, en la
// técnica, visual) al final del arranque: así este
// módulo no depende de la escena 3D y se prueba con Node (admin/tests/test_agente_presentacion.py).
export const CANAL = 'yondo-presentacion';
export const VERSION = 1;
export const MAX_EXPLICACION = 220;   // `MAX_EXPLICACION` de la herramienta y del puente del panel: una prueba los compara
const ID = /^[a-z_]{2,40}$/;
const ID_PIEZA = /^[a-z0-9_]{1,40}$/;   // un componente o una inmersión (los ids de la propuesta)
// El recorrido narrado (`app/recorrido.py` y agente-presentacion.js con los mismos valores: una prueba los compara)
export const MAX_TITULO = 80;
export const MAX_FRASES = 3;
export const MAX_ESCENAS = 8;
export const MAX_PUNTO = 80;
export const MAX_CIERRE = 200;
export const RID = /^[0-9a-f]{12}$/;
export const RESALTAR = { cifra: 12, punto: 20, leyenda: 12, especificacion: 20 };
export const TECLAS = ['Escape', 'siguiente', 'anterior', 'pausa', 'detener'];
// Lo que delata un costo en un texto proyectado (`PLATA` de app/proyectable.py y de agente-presentacion.js, la misma
// regla): el signo, «COP», «pesos», «billones de», «billón de» o «millones de pesos», en mayúsculas o minúsculas. Nada de lo que se
// proyecta en la presentación técnica la lleva: ni la explicación ni el recorrido. (La de tecnica.js, que limpia los datos
// de la propuesta, es otra cosa y no cambia con esta)
const PLATA = /[$\u{1F4B2}]|\bcop\b|\bpesos\b|\bbill(?:ones|[o\u00f3\u00d3]n) de\b|millones de pesos/iu;
const ASIENTO_MS = 5000, ASIENTO_ATLAS_MS = 15000;   // lo que espera, a lo sumo, que la imagen se asiente
// `visual`: los valores que admite cada parte (visual.js y `_VISUAL` de la herramienta)
export const CAMARAS = ['paso', 'aerea', 'oblicua', 'rasante', 'cerca', 'lejos'];
const VISUAL = {
  enfoque: (v) => v === null || (typeof v === 'string' && ID_PIEZA.test(v)),
  detalle: (v) => v === null || (typeof v === 'string' && ID_PIEZA.test(v)),
  inmersion: (v) => v === null || (typeof v === 'string' && ID_PIEZA.test(v)),
  camara: (v) => CAMARAS.includes(v),
  rumbo: (v) => v === null || (Number.isInteger(v) && v >= 0 && v <= 359),
  girar: (v) => typeof v === 'boolean',
  comparar: (v) => v === 'hoy' || v === 'proyecto',
  tema: (v) => v === 'claro' || v === 'oscuro',
};
const ORIGEN = /^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/;
const ORIGEN_HTTPS = /^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/i;
// Lo que el subtítulo no muestra (`_explicacion_visible` de admin/app/agente/herramientas/interfaz.py, con las mismas
// reglas): de control, de formato (marcas de dirección, ancho cero), separadores de línea, sustitutos sueltos, de uso
// privado, sin asignar, los rellenos que se ven como nada y los selectores de variante; más de dos acentos apilados; y,
// en la forma NFKC del texto (así «＠», los dígitos en superíndice o de ancho completo y los guiones de compatibilidad
// cuentan como los comunes), una «@» o un número de 7 dígitos o más, también por grupos (TIRADA: con espacios, guiones,
// rayas, barras, paréntesis, o pegados con punto, coma, «_», el apóstrofo recto o tipográfico, el acento agudo o grave
// que se escribe en su lugar, la prima o un punto de viñeta: «71'234.567» o «71´234.567», con el apóstrofo de los millones, es como se escribe a mano una cédula en Colombia), salvo un
// periodo («2028-2031») o un rango de cifras de menor a mayor («116.294 – 210.000»). Antes se quitan las fechas que
// existen (FECHA: «15/11/2026», «2026-11-15», de 1900 a 2099): cada una corta la tirada
const NO_SE_VE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\u{34f}\u{115f}\u{1160}\u{17b4}\u{17b5}\u{2800}\u{3164}\u{ffa0}\u{180b}-\u{180f}\u{fe00}-\u{fe0f}\u{e0000}-\u{e0fff}]/u;
const ACENTOS = /[\p{Mn}\p{Me}]{3,}/u;
// (pegados: . , _ · ( ' ‘ ’ ` ʹ ʼ ′ ‧ • ∙ ・, y «´», que en la forma NFKC es un espacio y un acento combinante; los de
// ancho completo ya quedaron como estos en la forma NFKC)
const TIRADA = /\p{Nd}+(?:(?:[.,_\u00b7'\u2018\u2019\u2032\u2027\u2022\u2219\u30fb\u0060\u02b9\u02bc(]| \u0301|\) ?|\)? ?[\-\u2010-\u2015\u2212\/] ?\(?| )\p{Nd}+)*/gu;
const PERIODO = /^((?:19|20)[0-9]{2}) ?[\-\u2010-\u2015\u2212\/] ?((?:19|20)[0-9]{2})$/u;
const RANGO = /^([0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?) ?[\-\u2010-\u2015\u2212] ?([0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?)$/u;
const FECHA = /(?<!\p{Nd})(?:([0-9]{4}) ?([.\-\u2010-\u2015\u2212\/]) ?([0-9]{1,2}) ?\2 ?([0-9]{1,2})|([0-9]{1,2}) ?([.\-\u2010-\u2015\u2212\/]) ?([0-9]{1,2}) ?\6 ?([0-9]{4}))(?!\p{Nd})/gu;
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
  ['quitar_explicacion', []], ['estado', []], ['vista', ['panel', 'indice', 'fichas', 'controles']],
  ['visual', Object.keys(VISUAL)],
  ['escena', ['capitulo', 'paso', 'panel', 'visual', 'resaltar', 'frases', 'titulo', 'n', 'de', 'voz', 'rid']],
  ['narracion', ['frase', 'pausa', 'voz', 'preparando']],
  ['cierre', ['puntos', 'rid']],
]);
const VISUAL_ESCENA = ['enfoque', 'camara', 'rumbo', 'girar', 'comparar', 'detalle', 'inmersion'];

const cifra = (t) => Number(t.replace(/\./g, '').replace(',', '.'));

/** ¿Es la fecha de FECHA un día que existe, de 1900 a 2099? («31/02/2026» no: se mira como cualquier número) */
function esFecha(m) {
  const [a, mes, dia] = (m[1] ? [m[1], m[3], m[4]] : [m[8], m[7], m[5]]).map(Number);
  const f = new Date(Date.UTC(a, mes - 1, dia));
  return a >= 1900 && a <= 2099 && f.getUTCFullYear() === a && f.getUTCMonth() === mes - 1 && f.getUTCDate() === dia;
}

/** ¿Trae `t` (en NFKC y con los espacios en uno) un número de más de DIGITOS_MAX dígitos que no es un periodo, un rango
 * de cifras ni una fecha? (las fechas que existen se quitan antes y cortan la tirada). Un monto en pesos («$1.156.350»)
 * ya no es excepción: PLATA lo frena antes */
function numeroLargo(t) {
  t = t.replace(FECHA, (...m) => (esFecha(m) ? ' | ' : m[0]));
  for (const [tirada] of t.matchAll(TIRADA)) {
    if (tirada.match(/\p{Nd}/gu).length <= DIGITOS_MAX) continue;
    const p = PERIODO.exec(tirada);
    if (p && Number(p[1]) <= Number(p[2])) continue;
    const r = RANGO.exec(tirada);
    if (r && cifra(r[1]) <= cifra(r[2])) continue;
    return true;
  }
  return false;
}

/** La explicación lista para el subtítulo (los espacios seguidos quedan en uno, como los pinta el navegador; sin NFKC:
 * se muestra como vino), o null si no se puede mostrar tal cual: no es texto, está vacía, pasa de `max` (por omisión
 * MAX_EXPLICACION) o trae lo que NO_SE_VE o ACENTOS prohíben, una «@», un número largo o un costo (PLATA). Es la regla
 * de todo lo que se proyecta (la explicación, el título, las frases y el cierre del recorrido): sin una opción que deje
 * pasar la plata, así nada de lo que pinta este módulo la muestra por olvido (`texto_proyectable` de
 * app/proyectable.py y `explicacionVisible` del puente deciden lo mismo). */
export function textoVisible(v, max = MAX_EXPLICACION) {
  if (typeof v !== 'string' || NO_SE_VE.test(v) || ACENTOS.test(v)) return null;
  const t = v.replace(/\s+/g, ' ').trim();
  if (!t || [...t].length > max) return null;
  const k = t.normalize('NFKC').replace(/\s+/g, ' ').trim();
  if (PLATA.test(k)) return null;
  return k.includes('@') || numeroLargo(k) ? null : t;
}

const entero = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const exactas = (o, claves) => !!o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).length === claves.length
  && claves.every((k) => Object.prototype.hasOwnProperty.call(o, k));

/** ¿Es `r` un resaltado de la forma exacta? (null, {tipo, n}, {tipo: 'especificacion', n, en} o {tipo: 'componente', id}) */
export function resaltarValido(r) {
  if (r === null) return true;
  if (!r || typeof r !== 'object' || typeof r.tipo !== 'string') return false;
  if (r.tipo === 'componente') return exactas(r, ['tipo', 'id']) && typeof r.id === 'string' && ID_PIEZA.test(r.id);
  if (!(r.tipo in RESALTAR)) return false;
  if (r.tipo === 'especificacion') return exactas(r, ['tipo', 'n', 'en']) && entero(r.n, 1, RESALTAR.especificacion) && (r.en === 'panel' || r.en === 'ficha');
  return exactas(r, ['tipo', 'n']) && entero(r.n, 1, RESALTAR[r.tipo]);
}

/** Las frases de una escena si se pueden proyectar tal cual (de 1 a MAX_FRASES, sin plata, juntas hasta
 * MAX_EXPLICACION), o null. */
export function frasesVisibles(frases) {
  if (!Array.isArray(frases) || !frases.length || frases.length > MAX_FRASES) return null;
  const out = frases.map((f) => textoVisible(f, MAX_EXPLICACION));
  if (out.some((f, i) => f === null || f !== frases[i])) return null;
  return out.reduce((a, f) => a + [...f].length, 0) + out.length - 1 <= MAX_EXPLICACION ? out : null;
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
export function montarMando({ caps, estado, ir, vecino, abrirIndice = () => {}, abrirFichas = () => {}, verPanel = () => {},
  reencuadrar = () => {}, visual = null, asentada = async () => true, resaltar = () => true, restaurarEncuadre = () => {},
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
  let sinTeclado = false;       // vista {controles: false}: la pantalla en off del panel
  let textoActual = null;       // lo que dice el subtítulo (la explicación, las frases o el cierre), para el estado
  let narracion = null;         // el recorrido que narra: {rid, n, de, frases, frase}
  let aplicando = 0;            // órdenes en curso: un cambio sin ninguna es de la persona
  let escenaVigente = 0;        // la última `escena` (o la orden que la dejó atrás): una más vieja no narra al asentarse
  let ultimoGesto = 0;          // cuándo salió el último `gesto` (a lo sumo uno por segundo)

  // Dentro del panel, los enlaces de la barra (el Home, el atlas) abren otra pestaña: si no, el iframe dejaría la
  // presentación y el asistente ya no la podría manejar
  for (const a of documento.querySelectorAll('.barra a[href]')) { a.target = '_blank'; a.rel = 'noopener'; }

  const clave = () => (caps[estado.ci] ? `${caps[estado.ci].id}/${estado.pi + 1}` : null);
  // El estado lleva la explicación que está a la vista (`texto`, la que pintó `subtitulo`): la pestaña del chat que sigue
  // a la ventana del proyector pone la misma, no la última que mandó ella (podía ser vieja o de otra pestaña). `por` es
  // siempre 'orden': solo el aviso que sale de un cambio de la persona lo cambia (ver `propuesta:paso` y
  // `propuesta:visual`)
  function actual() {
    const c = caps[estado.ci];
    if (!c) return { capitulo: null, paso: null, total: null, nombre: null, titulo: null, explicacion: false, texto: null };
    const p = c.pasos[estado.pi] || {};
    const visible = !!sub?.classList.contains('visible');
    return { capitulo: c.id, paso: estado.pi + 1, total: c.pasos.length, nombre: limpio(c.nombre, 80),
      titulo: limpio(p.titulo || c.nombre, 200), explicacion: visible, texto: visible ? textoActual : null,
      por: 'orden', recorrido: narracion ? { rid: narracion.rid, n: narracion.n, de: narracion.de } : null,
      ...(visual ? { visual: visual.estado() } : {}) };
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
    // el borde derecho del panel donde queda (sin el transform con que vuelve al quitar «Solo 3D»)
    const p = panel && !pres.classList.contains('sin-panel') ? panel.offsetLeft + panel.offsetWidth : null;
    const libre = (ventana.innerWidth || 0) - (p !== null ? p + 16 : 100) - (l ? l.width + 28 : 16);
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
  // Las medidas son las del lugar donde quedan el panel y el subtítulo, no las de un cuadro de sus transiciones (ver
  // `bajoPanel` y `pisoFinal`): se mide en el acto, a veces con todo en movimiento (el giro del celular, «Solo 3D»), y
  // al terminar la transición nada cambia de tamaño, así que nadie vuelve a medir
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
    // el borde de abajo del subtítulo: sobre la hoja en su mínimo, o el suyo (fijo, sobre el control o al pie)
    const piso = enHoja ? bajoPanel() - HOJA_MIN - 8 : pisoFinal();
    for (const e of ESCALAS) {
      if (e < 1) pres.style.setProperty('--sub-esc', String(e));
      if (sub.offsetHeight <= piso - reserva) return;
    }
    if (enHoja) {
      const hoja = Math.floor(bajoPanel() - 8 - reserva - sub.offsetHeight);
      pres.style.setProperty('--hoja-min', `${Math.max(HOJA_PISO, hoja)}px`);
    }
  }
  // El borde de abajo de la hoja: el de su caja sin el transform con que entra y sale («Solo 3D»), que es fijo (sobre
  // el control) aunque su alto esté en transición. offsetTop es el de la ventana: el panel es `position: fixed`
  function bajoPanel() { return panel ? panel.offsetTop + panel.offsetHeight : ventana.innerHeight || 0; }
  // El borde de abajo del subtítulo cuando termine de moverse. Su `bottom` tiene transición (sigue a la hoja, baja
  // hasta el control con «Solo 3D», pasa al pie al girar el celular) y offsetTop la sigue cuadro a cuadro: medido a
  // mitad de camino, el piso quedaba más arriba y la letra se achicaba de más, para siempre. El destino lo dice la
  // transición
  function pisoFinal() {
    const piso = sub.offsetTop + sub.offsetHeight;
    const t = sub.getAnimations?.().find((a) => a.transitionProperty === 'bottom');
    const k = t?.effect?.getKeyframes?.() || [];
    const hasta = parseFloat(k[k.length - 1]?.bottom);
    return Number.isFinite(hasta) ? piso + (parseFloat(ventana.getComputedStyle(sub).bottom) || 0) - hasta : piso;
  }
  function renglones() {
    const alto = texto?.getBoundingClientRect?.().height || 0;
    const linea = parseFloat(ventana.getComputedStyle?.(texto)?.lineHeight) || 0;
    return linea ? Math.round(alto / linea) : 0;
  }
  function subtitulo(t, paso = clave()) {
    if (!sub || !texto) return;
    const antes = sub.classList.contains('visible');
    salirDeNarracion();
    if (t) {
      texto.textContent = t;
      textoActual = t;
      sub.classList.add('visible');
      pasoDelSubtitulo = paso;
    } else {
      sub.classList.remove('visible');   // el texto se queda mientras se desvanece
      pasoDelSubtitulo = null;
      textoActual = null;
    }
    medir();
    // En la pantalla chica el subtítulo le quita alto a la maqueta: la cámara vuelve a encuadrar (si nadie la movió)
    if (antes !== !!t && chica?.matches) reencuadrar();
  }

  // ── La narración de un recorrido, en la misma caja del subtítulo (así `medir` y `acomodar` siguen valiendo): una
  // cabecera con el título, el avance en puntos (sin números) y las barras de la voz, y las frases en spans. Todo con
  // createElement y textContent: nada del recorrido se pinta como HTML
  const nuevo = (etiqueta, clase, t) => { const e = documento.createElement(etiqueta); if (clase) e.className = clase; if (t != null) e.textContent = t; return e; };
  let cab = null;
  function cabecera(titulo, n, de) {
    if (!sub || typeof documento.createElement !== 'function') return null;
    if (!cab) { cab = nuevo('div', 'sub-cab'); sub.insertBefore(cab, texto); }
    const puntos = nuevo('span', 'sub-puntos');
    for (let i = 1; i <= de; i++) puntos.append(nuevo('i', i < n ? 'hecha' : i === n ? 'actual' : ''));
    const voz = nuevo('span', 'sub-voz');
    voz.setAttribute('aria-hidden', 'true');
    voz.append(nuevo('i'), nuevo('i'), nuevo('i'));
    cab.replaceChildren(nuevo('b', 'sub-titulo', titulo), puntos, voz, nuevo('span', 'sub-pausa', 'En pausa'));
    return cab;
  }
  function salirDeNarracion() {
    narracion = null;
    sub?.classList.remove('narracion', 'cierre', 'pausado', 'con-voz', 'cambiando', 'preparando');
    cab?.remove();
    cab = null;
    resaltar(null);
  }
  function pintarFrases(frases, activa) {
    texto.replaceChildren(...frases.map((f, i) => nuevo('span', `frase${i === activa ? ' activa' : i < activa ? ' dicha' : ''}`, f)));
  }
  function narrar({ titulo, n, de, frases, voz, rid }) {
    if (!sub || !texto || typeof documento.createElement !== 'function') return;
    const antes = sub.classList.contains('visible');
    sub.classList.remove('cierre', 'cambiando', 'preparando', 'pausado');
    sub.classList.add('narracion', 'visible');
    sub.classList.toggle('con-voz', !!voz);
    sub.setAttribute('aria-live', voz ? 'off' : 'polite');   // con voz no se lee dos veces
    cabecera(titulo, n, de);
    pintarFrases(frases, 0);
    narracion = { rid, n, de, frases, frase: 0, titulo };
    textoActual = frases.join(' ');
    pasoDelSubtitulo = clave();
    medir();
    if (!antes && chica?.matches) reencuadrar();
  }
  function cierre(puntos) {
    sub.classList.add('cierre');
    sub.classList.remove('pausado', 'cambiando');
    // el resumen es del recorrido entero: lo señalado en la última escena deja de estarlo
    resaltar?.(null);
    const b = cab?.querySelector('.sub-titulo');
    if (b) b.textContent = puntos ? 'En resumen' : '¿Preguntas?';
    cab?.querySelector('.sub-puntos')?.replaceChildren();
    if (puntos) {
      texto.replaceChildren(...puntos.map((x) => nuevo('span', 'punto', x)));
      textoActual = puntos.join(' · ');
    }
    medir();
  }
  // La píldora mientras el asistente prepara: solo si no hay narración ni explicación a la vista; se apaga sola
  let tPreparando = 0;
  function preparando(v) {
    clearTimeout(tPreparando);
    if (!sub || !texto) return;
    if (v && !sub.classList.contains('visible')) {
      sub.classList.add('preparando', 'visible');
      texto.textContent = 'El asistente prepara la explicación…';
      textoActual = null;
      pasoDelSubtitulo = null;
      tPreparando = setTimeout(() => preparando(false), 25000);
      medir();
    } else if (!v && sub.classList.contains('preparando')) {
      sub.classList.remove('preparando', 'visible');
      medir();
    }
  }

  // La orden `escena`: todo validado antes de mover nada
  function escenaInvalida(m) {
    const ci = typeof m.capitulo === 'string' && ID.test(m.capitulo) ? caps.findIndex((c) => c.id === m.capitulo) : -1;
    if (ci < 0) return 'La presentación no tiene ese capítulo';
    if (!entero(m.paso, 1, caps[ci].pasos.length)) return 'Ese capítulo no tiene ese paso';
    if (typeof m.panel !== 'boolean' || typeof m.voz !== 'boolean') return 'panel y voz van con verdadero o falso';
    if (!exactas(m.visual, VISUAL_ESCENA) || VISUAL_ESCENA.some((k) => !VISUAL[k](m.visual[k]))) return 'Lo visual de la escena no tiene la forma';
    if (!resaltarValido(m.resaltar)) return 'El resaltado no tiene la forma';
    if (!frasesVisibles(m.frases)) return 'La narración no se puede mostrar tal como es';
    if (textoVisible(m.titulo, MAX_TITULO) !== m.titulo) return 'El título no se puede mostrar tal como es';
    if (!entero(m.n, 1, MAX_ESCENAS) || !entero(m.de, m.n, MAX_ESCENAS)) return 'El avance de la escena no vale';
    if (typeof m.rid !== 'string' || !RID.test(m.rid)) return 'El recorrido no tiene un id válido';
    const malo = visual.validar?.(m.visual, ci);
    return malo || null;
  }
  // Las órdenes se atienden a la vez y una escena tarda (el telón, el vuelo de la cámara, hasta 15 s el modelo del atlas):
  // si mientras tanto llega otra escena (un salto, otro recorrido) o una orden que la deja atrás (quitar la explicación al
  // detener, explicar, ir o avanzar, el cierre), al terminar cada espera ya no es la vigente y sale sin tocar nada más:
  // no aplica lo visual ni resalta ni narra. Si no, pintaba sus frases sobre las de la escena siguiente (la voz decía
  // una y el subtítulo mostraba la otra) o volvía a poner la narración después de quitada, y con ella el teclado quedaba
  // tomado para un recorrido que ya no suena. Responde `reemplazada` (la vista ya pasó a otra cosa)
  const dejarAtras = () => { escenaVigente++; };
  async function escena(m) {
    const ci = caps.findIndex((c) => c.id === m.capitulo), pi = m.paso - 1;
    const t0 = Date.now();
    const mia = ++escenaVigente;
    const superada = () => mia !== escenaVigente;
    aplicando++;
    try {
      sub?.classList.add('cambiando');   // la narración anterior se apaga mientras la imagen cambia
      resaltar(null);
      if (ci !== estado.ci || pi !== estado.pi) {
        abrirIndice(false);
        abrirFichas(false);
        const dir = ci < estado.ci || (ci === estado.ci && pi < estado.pi) ? -1 : 1;
        await ir(ci, pi, { dir });
        if (superada()) return { reemplazada: true };
      }
      const conPanel = !pres?.classList.contains('sin-panel');
      if (conPanel !== m.panel) verPanel(m.panel);
      const ahora = visual.estado(), cambios = {};
      for (const k of VISUAL_ESCENA) if (ahora[k] !== m.visual[k]) cambios[k] = m.visual[k];
      let aviso = null;
      if (Object.keys(cambios).length && await visual.aplicar(cambios)) aviso = 'atlas';
      if (superada()) return { reemplazada: true };
      restaurarEncuadre();
      if (m.resaltar && !resaltar(m.resaltar)) aviso = aviso || 'resaltar';
      const atlas = !!visual.cargando?.();
      const asento = await asentada({ tope: atlas ? ASIENTO_ATLAS_MS : ASIENTO_MS });
      if (superada()) return { reemplazada: true };
      if (!asento) aviso = aviso || (visual.cargando?.() ? 'atlas' : 'asiento');
      narrar(m);
      return { asentada: asento, ms: Date.now() - t0, ...(aviso ? { aviso } : {}) };
    } finally {
      aplicando--;
    }
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
    // El recorrido narrado: la escena (atómica), la frase que suena, la pausa, la voz, la píldora y el cierre
    if (m.orden === 'escena') {
      if (!visual) return fallo('Esta presentación no tiene la capa visual: es la de la presentación técnica (?modo=tecnica)');
      const malo = escenaInvalida(m);
      if (malo) return fallo(String(malo).slice(0, 160));
      const extra = await escena(m);
      return responder(id, 'estado', origen, extra);
    }
    if (m.orden === 'narracion') {
      const partes = CLAVES.get('narracion').filter((k) => m[k] !== undefined);
      if (!partes.length) return fallo('La orden no dice qué cambiar de la narración');
      if (m.frase !== undefined && (!narracion || !entero(m.frase, 0, narracion.frases.length - 1))) return fallo('No hay esa frase en la narración');
      if (['pausa', 'voz', 'preparando'].some((k) => m[k] !== undefined && typeof m[k] !== 'boolean')) return fallo('pausa, voz y preparando van con verdadero o falso');
      if ((m.pausa !== undefined || m.voz !== undefined) && !narracion) return fallo('No hay una narración en pantalla');
      if (m.frase !== undefined) { narracion.frase = m.frase; sub.classList.remove('pausado'); pintarFrases(narracion.frases, m.frase); }
      if (m.pausa !== undefined) sub.classList.toggle('pausado', m.pausa);
      if (m.voz !== undefined) { sub.classList.toggle('con-voz', m.voz); sub.setAttribute('aria-live', m.voz ? 'off' : 'polite'); }
      if (m.preparando !== undefined) preparando(m.preparando);
      return responder(id, 'estado', origen);
    }
    if (m.orden === 'cierre') {
      if (m.puntos !== null) {
        const ok = Array.isArray(m.puntos) && m.puntos.length >= 1 && m.puntos.length <= 3
          && m.puntos.every((x) => textoVisible(x, MAX_PUNTO) === x)
          && m.puntos.reduce((a, x) => a + [...x].length, 0) <= MAX_CIERRE;
        if (!ok) return fallo('El cierre no se puede mostrar tal como es');
      }
      // El reproductor ya pasó al cierre (el suyo o el de otro recorrido): una escena que todavía se asienta no narra
      // encima del resumen, aunque este no se pueda pintar
      dejarAtras();
      if (!narracion || m.rid !== narracion.rid) return fallo('El cierre no es del recorrido en pantalla');
      cierre(m.puntos);
      return responder(id, 'estado', origen);
    }
    // Lo que se ve, sin cambiar de paso: cada parte con verdadero o falso (las que no vienen quedan como están). El índice
    // y las fichas tapan la presentación: no se abren a la vez
    if (m.orden === 'vista') {
      const partes = CLAVES.get('vista').filter((k) => m[k] !== undefined);
      if (!partes.length) return fallo('La vista no dice qué mostrar');
      if (partes.some((k) => typeof m[k] !== 'boolean')) return fallo('Cada parte de la vista va con verdadero o falso');
      if (m.indice === true && m.fichas === true) return fallo('El índice y las fichas no se abren a la vez');
      if (m.indice === true) abrirFichas(false);
      if (m.fichas === true) abrirIndice(false);
      if (m.panel !== undefined) verPanel(m.panel);
      if (m.indice !== undefined) abrirIndice(m.indice);
      if (m.fichas !== undefined) abrirFichas(m.fichas);
      if (m.controles !== undefined) { pres?.classList.toggle('sin-controles', !m.controles); sinTeclado = !m.controles; }
      return responder(id, 'estado', origen);
    }
    // Lo visual, sin cambiar de paso: solo las partes que vienen, cada una con un valor de su lista
    if (m.orden === 'visual') {
      if (!visual) return fallo('Esta presentación no tiene la capa visual: es la de la presentación técnica (?modo=tecnica)');
      const partes = Object.keys(VISUAL).filter((k) => m[k] !== undefined);
      if (!partes.length) return fallo('La orden visual no dice qué cambiar');
      const malas = partes.filter((k) => !VISUAL[k](m[k]));
      if (malas.length) return fallo(`Valor que la presentación no admite en: ${malas.join(', ')}`);
      const error = await visual.aplicar(Object.fromEntries(partes.map((k) => [k, m[k]])));
      if (error) return fallo(String(error).slice(0, 160));
      return responder(id, 'estado', origen);
    }
    if (m.orden === 'explicar' || m.orden === 'quitar_explicacion') {
      if (m.orden === 'explicar' && !explicacion) return fallo('Falta la explicación');
      dejarAtras();
      subtitulo(explicacion);   // también sale del modo narración (quita el resaltado y el recorrido)
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
    dejarAtras();
    // La explicación va antes del paso: el encuadre del paso nuevo ya le deja su lugar. Sin explicación nueva, la del
    // paso anterior se quita al cambiar de paso (ver `propuesta:paso`)
    if (explicacion) subtitulo(explicacion, `${caps[ci].id}/${pi + 1}`);
    abrirIndice(false);
    abrirFichas(false);
    const dir = m.orden === 'avanzar' ? m.d : ci < estado.ci || (ci === estado.ci && pi < estado.pi) ? -1 : 1;
    aplicando++;
    try { await ir(ci, pi, { dir }); } finally { aplicando--; }
    return responder(id, 'estado', origen);
  }

  ventana.addEventListener('message', (e) => {
    if (e.source !== padre || !permitidos.has(e.origin)) return;
    const m = e.data;
    if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
    origenPadre = e.origin;
    const conOrden = m.orden !== 'estado';
    if (conOrden) aplicando++;
    atender(m, e.origin).catch(() => responder(undefined, 'error', e.origin, { error: 'La presentación no pudo aplicar la orden' }))
      .finally(() => { if (conOrden) aplicando--; });
  });
  // Un paso que cambió sin ninguna orden en curso lo movió la persona: ESTE aviso lo dice, y solo él (un recorrido que
  // suena se pausa con él). Los que salen mientras se aplica una orden (el `ir` de una escena, el del asistente) son de la
  // orden, aunque antes la persona haya tocado algo: si no, el recorrido que empieza después se pausaba solo
  ventana.addEventListener('propuesta:paso', () => {
    const dePersona = listo && !aplicando;
    if (pasoDelSubtitulo && pasoDelSubtitulo !== clave()) subtitulo(null);
    medir();
    enviar({ tipo: listo ? 'estado' : 'listo', ...actual(), por: dePersona ? 'persona' : 'orden' });
    listo = true;
  });
  // Lo visual que cambia sin orden (la persona arrastra la cámara y deja de girar, cierra la ficha): el panel lo sabe; solo
  // lo que visual.js marca como de la persona (tomó la cámara) pausa el recorrido
  ventana.addEventListener('propuesta:visual', (e) => {
    const dePersona = !aplicando && e?.detail?.por === 'persona';
    if (listo) enviar({ tipo: 'estado', ...actual(), por: dePersona ? 'persona' : 'orden' });
  });
  // Sin controles, ninguna tecla mueve la presentación (en captura: antes que las de main.js); Escape va al panel. Con un
  // recorrido sonando, las teclas de avanzar, retroceder, pausar y Escape lo manejan a él (el panel decide), no al paso
  const TECLA = { ArrowRight: 'siguiente', PageDown: 'siguiente', ' ': 'siguiente', Enter: 'siguiente', ArrowLeft: 'anterior',
    PageUp: 'anterior', Backspace: 'anterior', p: 'pausa', P: 'pausa', k: 'pausa', K: 'pausa', Escape: 'detener' };
  // El gesto de la persona sobre la presentación (con controles; la pantalla en off no se toca): el panel enciende con él
  // la voz que ya estaba elegida. En la ventana del proyector la presentación ocupa todo y tiene el foco, así que los
  // toques y las teclas caen aquí y el panel no los ve. Solo los que le dan al navegador la activación del usuario (una
  // tecla que no es Escape, el botón del ratón al bajar, el dedo o el lápiz al levantarse): esa activación también vale
  // para el marco padre, que así puede hacer hablar a la voz; con otro evento todavía no podría. Uno por segundo basta
  function gesto(e) {
    if (sinTeclado) return;
    const activa = e.type === 'keydown' ? e.key !== 'Escape'
      : e.pointerType === 'mouse' ? e.type === 'pointerdown' : e.type === 'pointerup';
    const ahora = Date.now();
    if (!activa || ahora - ultimoGesto < 1000) return;
    ultimoGesto = ahora;
    enviar({ tipo: 'gesto' });
  }
  ventana.addEventListener('pointerdown', gesto, true);
  ventana.addEventListener('pointerup', gesto, true);
  ventana.addEventListener('keydown', (e) => {
    gesto(e);
    if (sinTeclado) {
      e.stopImmediatePropagation();
      e.preventDefault();
      if (e.key === 'Escape') enviar({ tipo: 'tecla', tecla: 'Escape' });
      return;
    }
    if (!narracion || e.altKey || e.ctrlKey || e.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || '')) return;
    const t = TECLA[e.key];
    if (!t || (e.key === 'Escape' && documento.querySelector('.indice:not([hidden]), .fichas:not([hidden])'))) return;
    if (e.key === 'Enter' && e.target?.closest?.('button,a')) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    enviar({ tipo: 'tecla', tecla: t });
  }, true);
  // Y los botones del control de la presentación, mientras suena: avanzan o retroceden escenas, no pasos
  documento.addEventListener?.('click', (e) => {
    const b = narracion && !sinTeclado ? e.target?.closest?.('.control [data-accion="sig"], .control [data-accion="ant"]') : null;
    if (!b) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    enviar({ tipo: 'tecla', tecla: b.dataset.accion === 'sig' ? 'siguiente' : 'anterior' });
  }, true);
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
  // «Solo 3D» y la altura de la hoja (main.js: sin-panel, hoja-mini, panel-grande) mueven el subtítulo sin cambiar el
  // tamaño de nada observado (en vertical el panel sale y vuelve con transform): sin esto, al volver el panel la
  // explicación medida sin él tapaba la franja de la obra, y al ocultarlo quedaba con la letra achicada. Solo esas tres
  // clases: las que pone `medir` no lo vuelven a llamar
  if (pres && typeof ventana.MutationObserver === 'function') {
    const DE_MAIN = ['sin-panel', 'hoja-mini', 'panel-grande'];
    const de = (c) => { const s = String(c ?? '').split(/\s+/); return DE_MAIN.filter((x) => s.includes(x)).join(); };
    new ventana.MutationObserver((cambios) => { if (de(cambios[0].oldValue) !== de(pres.className)) medir(); })
      .observe(pres, { attributes: true, attributeFilter: ['class'], attributeOldValue: true });
  }
  if (caps[estado.ci]) { listo = true; enviar({ tipo: 'listo', ...actual() }); }
  return { subtitulo, estado: actual, narrar };
}
