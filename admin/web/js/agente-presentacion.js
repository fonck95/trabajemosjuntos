// Puente entre el asistente y la presentación de la propuesta (vistas/presentacion.js), con el patrón de agente-mapa.js:
// las acciones se aplican en orden; mientras la vista no está abierta y lista (su iframe avisó que cargó) esperan en una
// cola, con plazo, y si hace falta se navega a /presentacion una sola vez.
//
// El modo proyector: la ventana /presentacion?pantalla=1 (otra pestaña del panel, a pantalla completa en el proyector) se
// anuncia por BroadcastChannel con un latido y con cada cambio de paso. Mientras haya un proyector vivo, esta pestaña le
// manda a él las órdenes, y solo a él, en vez de abrir la vista aquí, y el proyector devuelve su estado. Todo mensaje
// del canal se valida: lo manda otra pestaña del mismo origen, pero sigue siendo una entrada.
// * El proyector manda: lo que se ve en la sala es lo que vale, y el paso también cambia allá sin pasar por aquí (el
//   control remoto, el teclado o un clic en esa ventana). Por eso las órdenes (también las relativas, «siguiente» de los
//   botones o del asistente) las aplica solo él, desde su paso, y la vista de esta pestaña, si está abierta, lo sigue con
//   órdenes absolutas (`seguir`: su capítulo, su paso y la explicación que se ve allá, que viene en su estado). Antes las
//   órdenes relativas se repetían en las dos y, en cuanto el paso cambiaba allá, cada una avanzaba desde el suyo y no se
//   reencontraban nunca. La barra de la vista muestra el estado del proyector (`estadoPresentacion`).
// * Manda un solo proyector, el que se abrió último (`desde`; a la par, el id mayor), y las órdenes van solo a él: no se
//   elige por el último latido, que con dos ventanas (un doble clic en «Abrir en otra pantalla») se alternaba y la vista
//   de aquí saltaba entre los pasos de las dos. El que se abrió antes, al saberlo, se retira: deja de anunciarse y de
//   aceptar órdenes y su vista sigue al nuevo como la de la pestaña del chat, así que cualquiera de las dos que esté en la
//   sala muestra lo mismo y lo que se haga en ella va al que manda. Si el nuevo se cierra, el retirado vuelve a mandar.
// * Al abrirse, el proyector se anuncia como recién llegado y las pestañas con la vista abierta (también un proyector
//   ya retirado) le mandan su capítulo, su paso y la explicación que muestran: las pantallas arrancan iguales (si no, el
//   proyector empezaría en la Portada). Mientras tanto la vista de aquí no lo sigue (iría a la Portada y volvería). Y
//   nadie sigue a un proyector que todavía no tomó un paso (`listo`: aplicó una orden o la persona lo movió), que sigue
//   en la Portada con la que abrió: así no saltan a la Portada y vuelven ni el proyector que se retira por él ni la
//   pestaña del chat cuando el nuevo, ocupado armando su maqueta 3D, no acusa a tiempo el paso que se le pasa y se lo da
//   por cerrado un momento.
// * El proyector acusa recibo de cada orden en el acto, avisa cuando la empieza (antes puede esperar en su fila, detrás
//   de otras) y responde al terminarla. El plazo de la respuesta corre desde que la empieza: antes corría desde el acuse
//   y, con varias en fila, las últimas vencían, y la vista de aquí volvía al paso viejo del proyector.
// * Una ventana que se cerró sin avisar (el «adios» de `pagehide` no siempre llega) o que se colgó no acusa: en
//   ESPERA_ACUSE_MS se da por cerrada y la orden se aplica en esta pestaña. Si se cierra (avisando o dejando de latir)
//   con la orden ya acusada, tampoco se pierde: va al proyector que quede o a la vista de aquí.
// * La pestaña que sigue a un proyector le pregunta cada latido si sigue ahí («quien») y él contesta en el acto: su
//   propio latido es un reloj, y el navegador espacia los relojes de una pestaña oculta (hasta uno por minuto).
//
// Solo importa base.js y `navegar` (el `ir` de app.js) llega por parámetro: así no depende de app.js y se prueba con
// Node (admin/tests/test_agente_presentacion.py).
import { sinBase } from './base.js';

export const CANAL = 'yondo-presentacion';
export const VERSION = 1;
export const MAX_EXPLICACION = 220;   // `MAX_EXPLICACION` de la herramienta y de mando.js: una prueba los compara
const ESPERA_MS = 30000;              // la presentación carga datos y la maqueta 3D: en un equipo lento, varios segundos
const ESPERA_MAX_MS = 120000;
const LATIDO_MS = 2000;               // el proyector se anuncia cada tanto
const VIVO_MS = 6500;                 // sin anuncios en este tiempo, se da por cerrado
const ESPERA_ACUSE_MS = 2500;         // lo que se espera el acuse del proyector (llega en milisegundos si está vivo)
const ESPERA_FILA_MS = 60000;         // lo que una orden acusada puede esperar en la fila del proyector a que la empiece
const ESPERA_PROYECTOR_MS = 15000;    // y desde que la empieza, su respuesta, por acción (él espera 12 s a la presentación)
const OPS = new Set(['ir', 'siguiente', 'anterior', 'explicar', 'quitar_explicacion']);
const CLAVES = new Set(['tipo', 'op', 'capitulo', 'paso', 'explicacion']);
const ID = /^[a-z_]{2,40}$/;
const ID_VENTANA = /^[a-z0-9]{8,40}$/;
// Lo que la explicación no puede traer (`_explicacion_visible` de la herramienta, `textoVisible` de mando.js, con las
// mismas reglas): se proyecta ante una sala. La «@» y los números se buscan en la forma NFKC del texto (la «＠» de
// ancho completo, los dígitos en superíndice o de ancho completo y los guiones de compatibilidad cuentan como los
// comunes); TIRADA son los dígitos con lo que los separa al escribir un teléfono o una cédula, y PERIODO y RANGO lo
// único que puede pasar de 6 dígitos (un periodo y un rango de cifras de la propuesta, de menor a mayor). Antes se
// quitan las fechas que existen (FECHA: «15/11/2026», «2026-11-15», de 1900 a 2099): cada una corta la tirada
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

/** La acción `presentacion` del servidor, normalizada, o null si no tiene la forma estricta: un objeto con solo las
 * claves conocidas, `op` de la lista, `capitulo` como id (obligatorio para `ir`), `paso` entero de 1 a 60 (solo con
 * `ir`), y `explicacion` de hasta MAX_EXPLICACION caracteres que se ve tal cual (obligatoria para `explicar`). */
export function accionPresentacion(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || a.tipo !== 'presentacion') return null;
  if (Object.keys(a).some((k) => !CLAVES.has(k)) || typeof a.op !== 'string' || !OPS.has(a.op)) return null;
  const out = { tipo: 'presentacion', op: a.op };
  if (a.op === 'ir') {
    if (typeof a.capitulo !== 'string' || !ID.test(a.capitulo)) return null;
    out.capitulo = a.capitulo;
    if (a.paso !== undefined) {
      if (!Number.isInteger(a.paso) || a.paso < 1 || a.paso > 60) return null;
      out.paso = a.paso;
    }
  } else if (a.capitulo !== undefined || a.paso !== undefined) {
    return null;
  }
  if (a.explicacion !== undefined) {
    if (a.op === 'quitar_explicacion') return null;
    const t = explicacionVisible(a.explicacion);
    if (!t) return null;
    out.explicacion = t;
  } else if (a.op === 'explicar') {
    return null;
  }
  return out;
}

const cifra = (t) => Number(t.replace(/\./g, '').replace(',', '.'));

/** ¿Es la fecha de FECHA un día que existe, de 1900 a 2099? (`_es_fecha` de la herramienta: «31/02/2026» no) */
function esFecha(m) {
  const [a, mes, dia] = (m[1] ? [m[1], m[3], m[4]] : [m[8], m[7], m[5]]).map(Number);
  const f = new Date(Date.UTC(a, mes - 1, dia));
  return a >= 1900 && a <= 2099 && f.getUTCFullYear() === a && f.getUTCMonth() === mes - 1 && f.getUTCDate() === dia;
}

/** ¿Trae `t` (en NFKC y con los espacios en uno) un número de más de DIGITOS_MAX dígitos que no es un periodo, un rango
 * de cifras, una fecha ni un monto en pesos? (`numero_largo` de la herramienta: las fechas que existen se quitan antes y
 * cortan la tirada) */
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

function explicacionVisible(v) {
  if (typeof v !== 'string' || NO_SE_VE.test(v) || ACENTOS.test(v)) return null;
  const t = v.replace(/\s+/g, ' ').trim();
  if (!t || [...t].length > MAX_EXPLICACION) return null;
  const k = t.normalize('NFKC').replace(/\s+/g, ' ').trim();
  return k.includes('@') || numeroLargo(k) ? null : t;
}

/** El estado que manda la presentación, solo con lo que se espera: {capitulo, paso, total, nombre, titulo, explicacion,
 * texto} o null. `texto` es la explicación que está a la vista (null si no hay, si no se puede mostrar tal cual o si la
 * presentación no lo dice). */
export function estadoValido(e) {
  if (!e || typeof e !== 'object' || Array.isArray(e)) return null;
  const { capitulo, paso, total } = e;
  if (typeof capitulo !== 'string' || !ID.test(capitulo)) return null;
  if (!Number.isInteger(total) || total < 1 || total > 60 || !Number.isInteger(paso) || paso < 1 || paso > total) return null;
  const corto = (v, n) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, n) : '');
  const explicacion = e.explicacion === true;
  return { capitulo, paso, total, nombre: corto(e.nombre, 80), titulo: corto(e.titulo, 200), explicacion,
    texto: explicacion ? explicacionVisible(e.texto) : null };
}

// ───────── La vista de esta pestaña ─────────

const cola = [];
// {aplicar(lista) → Promise<resultados>, estado() → estado | null, proyector?: true, cambio?() (la vista repinta su
// barra: el estado del proyector cambió)}
let control = null;
let cadena = Promise.resolve();

const enPresentacion = () => {
  try { return (sinBase(location.pathname).replace(/\/+$/, '') || '/') === '/presentacion'; } catch { return false; }
};

/** Aplica `lista` en la vista de esta pestaña, después de lo que ya se le mandó. `alEmpezar` corre justo antes (cuando
 * le toca); si lanza, la lista no se aplica. */
function enOrden(lista, alEmpezar) {
  const p = cadena.then(() => {
    if (!control) throw new Error('La presentación se cerró antes de aplicar el cambio');
    alEmpezar?.();
    return control.aplicar(lista);
  });
  cadena = p.catch(() => {});
  return p;
}

function vaciar() {
  while (control && cola.length) {
    const it = cola.shift();
    clearTimeout(it.reloj);
    enOrden(it.acciones).then(it.ok, it.mal);
  }
}

function rechazarCola(motivo) {
  while (cola.length) {
    const it = cola.shift();
    clearTimeout(it.reloj);
    it.mal(new Error(motivo));
  }
}

// Si la persona abre otra vista mientras la presentación carga (o no se pudo abrir), lo que esperaba ya no se aplicará:
// se responde en el acto en vez de agotar el plazo (como el mapa)
globalThis.addEventListener?.('vista', (e) => {
  if (!cola.length || control) return;
  const { ruta, ok } = e?.detail || {};
  if (typeof ruta !== 'string') return;
  if (ruta === '/presentacion' && ok === false) rechazarCola('La presentación no se pudo abrir');
  else if (ruta !== '/presentacion' && !enPresentacion()) rechazarCola('Se abrió otra vista antes de que la presentación terminara de cargar');
});

// ───────── El canal con el proyector ─────────

const yo = idVentana();
const proyectores = new Map();   // id → {id, visto, desde, listo, estado, sincronizando?}
const esperando = new Map();     // nro → {ok, mal, reloj, para, n, vence?, empezo?}: lo mandado a un proyector
let nro = 0;
let latido = 0;
let sondeo = 0;
let canal = null;
let desde = 0;          // cuándo se abrió esta ventana como proyector: entre dos, manda la más nueva
let retirado = false;   // esta ventana de proyector se retiró porque se abrió otra: su vista sigue a la nueva
let tomo = false;       // esta ventana de proyector ya tomó un paso (una orden, o la persona la movió): se la puede seguir
let inicial = null;     // el paso con el que abrió (`capitulo/paso/texto`)
const clave = (e) => (e ? `${e.capitulo}/${e.paso}/${e.texto || ''}` : null);

const soyProyector = () => !!control?.proyector && !retirado;
const masNuevo = (a, b) => a.desde > b.desde || (a.desde === b.desde && a.id > b.id);

function idVentana() {
  try {
    const b = new Uint8Array(12);
    globalThis.crypto.getRandomValues(b);
    return [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  } catch {
    return `v${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  }
}

function publicar(msj) {
  try { canal?.postMessage({ canal: CANAL, v: VERSION, ...msj }); } catch { /* canal cerrado */ }
}

function anunciar(recien = false) {
  if (!soyProyector()) return;
  let e = null;
  try { e = estadoValido(control.estado()); } catch { e = null; }
  publicar({ tipo: 'proyector', id: yo, desde, listo: tomo, estado: e, ...(recien ? { recien: true } : {}) });
}

// El latido del proyector. El que se retiró vuelve a mandar cuando ya no queda vivo ninguno más nuevo (se cerró)
function latir() {
  if (retirado && control?.proyector && !elegido()) volver();
  anunciar();
}

/** Se abrió un proyector más nuevo: esta ventana deja de serlo (las otras pestañas la olvidan con el «adios») y su vista
 * lo sigue, como la de la pestaña del chat. */
function retirarse() {
  retirado = true;
  publicar({ tipo: 'adios', id: yo });
  sondear();
}

function volver() {
  retirado = false;
  sondear();
  anunciar();
}

/** Un proyector que se acaba de abrir: si esta pestaña tiene la vista abierta, le manda su capítulo, su paso y la
 * explicación que está en pantalla. Hasta que responda, la vista de aquí no lo sigue ni su estado cuenta: todavía está
 * en la Portada. */
function sincronizar(id) {
  if (!control || soyProyector()) return;
  let e = null;
  try { e = estadoValido(control.estado()); } catch { e = null; }
  if (!e) return;
  const p = proyectores.get(id);
  if (p) p.sincronizando = true;
  const fin = () => { if (p) p.sincronizando = false; cambio(); };
  const ir = { tipo: 'presentacion', op: 'ir', capitulo: e.capitulo, paso: e.paso, ...(e.texto ? { explicacion: e.texto } : {}) };
  alProyector([ir], id).then(fin, fin);
}

/** Lo último que se supo de un proyector (sin perder si se está sincronizando). `listo` falta en el de una versión
 * anterior: se lo sigue. */
function verProyector(id, estado, desdeSuyo, listo) {
  const p = proyectores.get(id) || { id, desde: 0, listo: true };
  p.visto = Date.now();
  p.estado = estado;
  if (desdeSuyo !== undefined) p.desde = desdeSuyo;
  if (listo !== undefined) p.listo = listo !== false;
  proyectores.set(id, p);
  sondear();
  return p;
}

// Mientras haya un proyector, la pestaña que no lo es le pregunta cada latido si sigue ahí: él contesta desde el
// mensaje, en el acto, aunque su pestaña esté oculta (sus relojes no: el navegador los espacia)
function sondear() {
  if (soyProyector() || !elegido()) {
    clearInterval(sondeo);
    sondeo = 0;
  } else if (!sondeo) {
    sondeo = setInterval(() => { if (!soyProyector() && elegido()) publicar({ tipo: 'quien' }); else sondear(); }, LATIDO_MS);
    sondeo?.unref?.();   // en Node (las pruebas) no retiene el proceso
  }
}

/** Un proyector que se cerró (avisó, no acusó recibo o dejó de latir): sale de la lista y lo que esperaba su respuesta
 * falla con `sinProyector` (quien lo mandó lo aplica en otro lado), con el paso desde el que lo empezó, si lo empezó.
 * Antes se esperaba el plazo entero y la orden se perdía. */
function olvidar(id) {
  const habia = proyectores.delete(id);
  for (const [n, it] of esperando) {
    if (it.para !== id) continue;
    esperando.delete(n);
    clearTimeout(it.reloj);
    it.mal(Object.assign(new Error('La pantalla del proyector se cerró'), { sinProyector: true, empezo: it.empezo || null }));
  }
  return habia;
}

/** El proyector que manda: de los vivos, el que se abrió último; o null. En la propia ventana del proyector, null. */
function elegido() {
  if (soyProyector()) return null;
  const ahora = Date.now();
  let mejor = null;
  for (const [id, p] of proyectores) {
    if (ahora - p.visto > VIVO_MS) olvidar(id);
    else if (!mejor || masNuevo(p, mejor)) mejor = p;
  }
  return mejor;
}

/** El proyector que la vista de aquí sigue: el que manda, si ya dijo su estado, ya tomó un paso y no se está
 * sincronizando; o null. */
function guia() {
  const p = elegido();
  return p?.estado && p.listo && !p.sincronizando ? p : null;
}

/** Cambió lo que se sabe del proyector: la vista repinta su barra y sigue al proyector. */
function cambio() {
  try { control?.cambio?.(); } catch { /* la vista se fue */ }
  seguir();
}

// La vista de esta pestaña sigue al proyector: si no está en su capítulo y su paso, va allá (con la explicación que se
// ve allá); si está, pone, cambia o quita la explicación como allá. Siempre con órdenes absolutas: no importa desde
// dónde parta ni cuántos avisos se pierdan (el latido lo vuelve a decir). La explicación es la que dice el estado del
// proyector, no la última que mandó esta pestaña: esa podía ser vieja, de otro paso o tapada por la de otra pestaña. Una
// sola a la vez; si mientras tanto llega otro estado, se vuelve a mirar al terminar. Mientras se le lleva al proyector
// un paso de aquí (`llevar`), no: lo que él diga hasta confirmarlo es de antes
let siguiendo = false;
let otraVez = false;
async function seguir() {
  if (!control || soyProyector() || llevando) return;
  if (siguiendo) { otraVez = true; return; }
  const e = guia()?.estado;
  let local = null;
  try { local = estadoValido(control.estado()); } catch { local = null; }
  if (!e || !local) return;
  const texto = e.explicacion ? e.texto : null;   // null: allá no se ve ninguna (o una presentación vieja no dice cuál)
  let lista = null;
  if (local.capitulo !== e.capitulo || local.paso !== e.paso) {
    lista = [{ tipo: 'presentacion', op: 'ir', capitulo: e.capitulo, paso: e.paso, ...(texto ? { explicacion: texto } : {}) }];
  } else if (texto && !(local.explicacion && local.texto === texto)) {
    lista = [{ tipo: 'presentacion', op: 'explicar', explicacion: texto }];
  } else if (!e.explicacion && local.explicacion) {
    lista = [{ tipo: 'presentacion', op: 'quitar_explicacion' }];
  }
  if (!lista) return;
  siguiendo = true;
  try { await enOrden(lista); } catch { /* la vista se cerró */ }
  siguiendo = false;
  if (otraVez) { otraVez = false; seguir(); }
}

// Lo que espera la respuesta de un proyector que ya acusó recibo: cada latido se mira que siga vivo (si se cerró sin
// avisar, `olvidar`: la orden va a otro lado) y que no haya vencido el plazo (`vence`: el de la fila hasta que la
// empieza, después el de la respuesta)
function vigilar(n) {
  const it = esperando.get(n);
  if (!it) return;
  clearTimeout(it.reloj);
  it.reloj = setTimeout(() => {
    if (esperando.get(n) !== it) return;
    const p = proyectores.get(it.para);
    if (!p || Date.now() - p.visto > VIVO_MS) {
      olvidar(it.para);
      cambio();
    } else if (Date.now() > it.vence) {
      esperando.delete(n);
      it.mal(new Error('La pantalla del proyector no respondió'));
    } else {
      vigilar(n);
    }
  }, LATIDO_MS);
}

async function alMensaje(m) {
  if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
  const otra = typeof m.id === 'string' && ID_VENTANA.test(m.id) && m.id !== yo;
  // la respuesta de un proyector a una orden de esta pestaña: solo vale la del que la recibió
  const mia = otra && m.para === yo && esperando.get(m.nro)?.para === m.id ? esperando.get(m.nro) : null;
  if (m.tipo === 'proyector' && otra) {
    const p = verProyector(m.id, m.estado == null ? null : estadoValido(m.estado),
      typeof m.desde === 'number' && Number.isFinite(m.desde) && m.desde > 0 ? m.desde : 0, m.listo);
    // Un proyector más nuevo: este se retira (no le pasa su paso: lo sincronizan las pestañas con la vista abierta, y
    // con un doble clic este también acaba de abrirse y está en la Portada)
    if (soyProyector() && masNuevo(p, { id: yo, desde })) retirarse();
    else if (m.recien === true) sincronizar(m.id);
    cambio();
  } else if (m.tipo === 'adios' && otra) {
    const habia = olvidar(m.id);
    if (retirado && control?.proyector && !elegido()) volver();
    if (habia) cambio();
  } else if (m.tipo === 'quien') {
    anunciar();
  } else if (m.tipo === 'ordenes' && soyProyector() && typeof m.de === 'string' && ID_VENTANA.test(m.de)
             && Number.isInteger(m.nro) && Array.isArray(m.acciones) && m.acciones.length >= 1 && m.acciones.length <= 20
             && (m.para === undefined || m.para === yo)) {
    // Soy el proyector: acuso recibo en el acto (la otra pestaña sabe que sigo aquí), aviso cuando la empiezo, aplico (lo
    // que no tiene la forma de una acción vuelve como error, sin aplicarse) y respondo
    publicar({ tipo: 'recibido', id: yo, para: m.de, nro: m.nro });
    const acciones = m.acciones.map(accionPresentacion);
    const empezar = () => {
      // Si mientras esperaba en la fila esta ventana se retiró, no la aplica: la otra pestaña ya la mandó al que manda
      if (!soyProyector()) throw new Error('Esta ventana dejó de ser la del proyector');
      let e = null;
      try { e = estadoValido(control.estado()); } catch { e = null; }
      publicar({ tipo: 'empieza', id: yo, para: m.de, nro: m.nro, estado: e });
    };
    let resultados;
    try {
      const validas = acciones.filter(Boolean);
      const r = validas.length ? await enOrden(validas, empezar) : [];
      // Ya tomó un paso (la primera, la de la pestaña que lo sincroniza): desde ahora se lo sigue. Al terminarla, no
      // antes: un latido a mitad de camino diría que se lo puede seguir en la Portada
      if (!tomo && soyProyector() && Array.isArray(r) && r.some((x) => x?.ok === true)) {
        tomo = true;
        anunciar();
      }
      let i = 0;
      const deLaVista = () => (Array.isArray(r) ? r[i++] : null);
      resultados = acciones.map((a, k) => (a
        ? deLaVista() || { op: a.op, ok: false, error: 'La presentación no respondió' }
        : { op: typeof m.acciones[k]?.op === 'string' ? m.acciones[k].op.slice(0, 30) : null, ok: false, error: 'Acción no válida' }));
    } catch (e) {
      resultados = acciones.map((a) => ({ op: a?.op ?? null, ok: false, error: String(e?.message || e).slice(0, 160) }));
    }
    let estado = null;
    try { estado = estadoValido(control?.estado()); } catch { estado = null; }
    publicar({ tipo: 'hecho', id: yo, para: m.de, nro: m.nro, resultados, estado, listo: tomo });
  } else if (m.tipo === 'recibido' && mia) {
    // El proyector está vivo: la orden espera en su fila hasta que la empiece
    const p = proyectores.get(m.id);
    if (p) p.visto = Date.now();
    mia.vence = Date.now() + ESPERA_FILA_MS;
    vigilar(m.nro);
  } else if (m.tipo === 'empieza' && mia) {
    // Desde aquí corre el plazo de la respuesta; y si el proyector se cierra antes de terminarla, se sabe desde qué paso
    // la empezó (`aplicarDonde`)
    const p = proyectores.get(m.id);
    if (p) p.visto = Date.now();
    mia.empezo = estadoValido(m.estado);
    mia.vence = Date.now() + ESPERA_PROYECTOR_MS * mia.n;
    vigilar(m.nro);
  } else if (m.tipo === 'hecho' && mia) {
    esperando.delete(m.nro);
    clearTimeout(mia.reloj);
    verProyector(m.id, estadoValido(m.estado), undefined, m.listo);
    mia.ok((Array.isArray(m.resultados) ? m.resultados : []).slice(0, 20).map(resultadoValido));
    cambio();
  }
}

function resultadoValido(r) {
  if (!r || typeof r !== 'object') return { op: null, ok: false, error: 'Respuesta no válida' };
  return { op: typeof r.op === 'string' ? r.op.slice(0, 30) : null, ok: r.ok === true,
    ...(typeof r.error === 'string' ? { error: r.error.slice(0, 160) } : {}) };
}

try {
  if (typeof globalThis.BroadcastChannel === 'function') {
    canal = new BroadcastChannel(CANAL);
    canal.unref?.();   // en Node (las pruebas) no retiene el proceso
    canal.onmessage = (e) => { alMensaje(e?.data).catch(() => {}); };
    publicar({ tipo: 'quien' });   // un proyector ya abierto se anuncia en el acto
  }
} catch { canal = null; }

/** ¿Hay una ventana de proyector viva (otra pestaña del panel en /presentacion?pantalla=1)? En la propia ventana del
 * proyector, no: ahí se aplica sobre la vista. */
export function proyectorVivo() {
  return !!elegido();
}

/** Manda `lista` al proyector `para`. Si no acusa recibo en ESPERA_ACUSE_MS, o se cierra antes de responder, se da por
 * cerrado y la promesa falla con `sinProyector` (quien llamó la aplica en otro lado). */
function alProyector(lista, para) {
  return new Promise((ok, mal) => {
    const n = ++nro;
    const it = { ok, mal, para, n: Math.max(1, lista.length) };
    it.reloj = setTimeout(() => {
      if (esperando.get(n) !== it) return;
      olvidar(para);
      cambio();   // la barra vuelve a la vista de aquí (o al proyector que quede)
    }, ESPERA_ACUSE_MS);
    esperando.set(n, it);
    publicar({ tipo: 'ordenes', de: yo, nro: n, acciones: lista, para });
  });
}

// ───────── Lo que usan la vista y el asistente ─────────

/** La vista se registra cuando su presentación avisó que cargó; devuelve la función que la quita (al salir de la
 * vista). Con `proyector: true` (la ventana /presentacion?pantalla=1), además se anuncia en el canal con un latido. */
export function registrarPresentacion(c) {
  if (!c || typeof c.aplicar !== 'function' || typeof c.estado !== 'function') return () => {};
  control = c;
  if (c.proyector) {
    retirado = false;
    tomo = false;
    desde = Date.now();
    try { inicial = clave(estadoValido(c.estado())); } catch { inicial = null; }
    clearInterval(latido);
    latido = setInterval(latir, LATIDO_MS);
    latido?.unref?.();
    sondear();
    anunciar(true);   // recién abierto: las pestañas con la vista abierta le pasan dónde están
  }
  vaciar();
  seguir();   // la vista que se abre con un proyector ya vivo va adonde está él
  return () => {
    if (control !== c) return;
    control = null;
    if (c.proyector) {
      clearInterval(latido);
      if (!retirado) publicar({ tipo: 'adios', id: yo });
      retirado = false;
    }
  };
}

/** La vista avisa cada cambio de estado. El proyector lo anuncia en el acto (así el asistente y la pestaña del chat lo
 * saben). En la pestaña del chat, un cambio que no vino de seguir al proyector (la persona usó el control, el teclado o
 * el índice de la presentación de aquí) se le manda a él, con una orden absoluta: si no, la vista de aquí volvería al
 * paso del proyector con el latido siguiente. */
export function avisarEstado() {
  if (control?.proyector && !tomo) {
    // La persona lo movió (el control remoto, el teclado), una orden ya lo llevó a otro paso o, retirado, siguió al que
    // manda: ya tomó un paso (si vuelve a mandar, se lo sigue)
    let e = null;
    try { e = estadoValido(control.estado()); } catch { e = null; }
    if (e && clave(e) !== inicial) tomo = true;
  }
  anunciar();
  llevar();
}

// Mientras el proyector no confirma lo que se le llevó, lo que diga de antes (un latido o la respuesta a una orden
// anterior, que pueden cruzarse con esta) no cuenta: si no, la vista de aquí volvería al paso viejo y después otra vez
// al nuevo, y la persona la vería saltar. Un segundo cambio de la persona en ese tiempo también se le lleva
let llevando = 0;
let llevado = null;
function llevar() {
  if (!control || soyProyector() || siguiendo) return;
  const p = elegido();
  const e = llevando ? llevado : guia()?.estado;
  let local = null;
  try { local = estadoValido(control.estado()); } catch { local = null; }
  if (!p || !e || !local || (local.capitulo === e.capitulo && local.paso === e.paso)) return;
  llevado = { capitulo: local.capitulo, paso: local.paso };
  llevando++;
  const fin = () => { llevando--; cambio(); };
  alProyector([{ tipo: 'presentacion', op: 'ir', ...llevado }], p.id).then(fin, fin);
}

/** La vista no puede mostrar la presentación (no hay sitio en este servidor): lo que esperaba falla con ese motivo. */
export function presentacionNoDisponible(motivo) { rechazarCola(motivo || 'La presentación no está disponible'); }

export const presentacionLista = () => !!control;
export const accionesEnCola = () => cola.length;

/** Dónde está la presentación ({capitulo, paso, total, nombre, titulo, explicacion, texto}) o null si no hay una
 * abierta: la del proyector si hay uno vivo (la que ve la sala: también la barra de la vista la muestra), si no la de
 * esta pestaña. Nunca lanza: va en el contexto de cada mensaje. */
export function estadoPresentacion() {
  try {
    const p = llevando ? null : guia();   // mientras se le lleva un paso, el que vale es el de aquí
    if (p) return p.estado;
    if (control) return estadoValido(control.estado());
    return elegido()?.estado ?? null;   // un proyector que nadie sincronizó (sin la vista abierta aquí)
  } catch {
    return null;
  }
}

/** Aplica `acciones` (las de `accionesPresentacion`) y resuelve con un resultado por acción ({op, ok, error?}). Con un
 * proyector vivo van solo al que manda, que las aplica desde su paso (la vista de esta pestaña, si está abierta, lo
 * sigue); si no, a la vista, y si no está abierta se navega con `navegar` a /presentacion y se aplican al quedar lista.
 * Un proyector que no acusa recibo, o que se cierra con la orden en curso, se da por cerrado y la lista va al proyector
 * que quede o a esta pestaña, como si no hubiera habido proyector: la vista de aquí estaba en su paso. */
export function accionesPresentacion(acciones, { navegar, espera = ESPERA_MS } = {}) {
  const lista = (Array.isArray(acciones) ? acciones : acciones ? [acciones] : []).slice(0, 20);
  return aplicarDonde(lista, { navegar, espera });
}

const relativa = (a) => a?.op === 'siguiente' || a?.op === 'anterior';

async function aplicarDonde(lista, opciones) {
  // Si el proyector que se cerró ya había empezado una lista con «siguiente» o «anterior», quizá ya se movió (y la vista
  // de aquí con él): donde vaya, la lista parte del paso desde el que él la empezó, y no se da un paso de más
  let desdeAlla = null;
  const conPaso = () => (desdeAlla
    ? [{ tipo: 'presentacion', op: 'ir', capitulo: desdeAlla.capitulo, paso: desdeAlla.paso }, ...lista] : lista);
  const sinPaso = (r) => (desdeAlla && Array.isArray(r) ? r.slice(1) : r);
  const probados = new Set();
  for (let p = elegido(); p && !probados.has(p.id); p = elegido()) {
    probados.add(p.id);
    try {
      return sinPaso(await alProyector(conPaso(), p.id));
    } catch (e) {
      if (!e?.sinProyector) throw e;
      if (e.empezo && !desdeAlla && lista.length < 20 && lista.some(relativa)) desdeAlla = e.empezo;
    }
  }
  return sinPaso(await enLaVista(conPaso(), opciones));
}

function enLaVista(lista, { navegar, espera }) {
  if (control) return enOrden(lista);
  const plazo = typeof espera === 'number' && espera > 0 ? Math.min(espera, ESPERA_MAX_MS) : ESPERA_MS;
  return new Promise((ok, mal) => {
    const it = { acciones: lista, ok, mal };
    it.reloj = setTimeout(() => {
      const i = cola.indexOf(it);
      if (i >= 0) cola.splice(i, 1);
      mal(new Error('La presentación no terminó de cargar'));
    }, plazo);
    cola.push(it);
    // Ya en /presentacion (cargando) solo se espera: volver a navegar recargaría la presentación
    if (!enPresentacion() && typeof navegar === 'function') navegar('/presentacion');
  });
}

// Al cerrar la ventana del proyector, las demás pestañas lo saben en el acto (sin esperar a que venza el latido)
globalThis.addEventListener?.('pagehide', () => { if (soyProyector()) publicar({ tipo: 'adios', id: yo }); });
