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
//   órdenes absolutas (`seguir`: su capítulo, su paso y la explicación, si es la que mandó esta pestaña). Antes las
//   órdenes relativas se repetían en las dos y, en cuanto el paso cambiaba allá, cada una avanzaba desde el suyo y no se
//   reencontraban nunca. La barra de la vista muestra el estado del proyector (`estadoPresentacion`).
// * Al abrirse, el proyector se anuncia como recién llegado y la pestaña que tiene la vista abierta le manda su capítulo,
//   su paso y la explicación que muestra: las dos pantallas arrancan iguales (si no, el proyector empezaría en la
//   Portada). Mientras tanto la vista de aquí no lo sigue (iría a la Portada y volvería).
// * El proyector acusa recibo de cada orden en el acto, antes de aplicarla. Una ventana que se cerró sin avisar (el
//   «adios» de `pagehide` no siempre llega) o que se colgó no acusa: en ESPERA_ACUSE_MS se da por cerrada y la orden se
//   aplica en esta pestaña, sin esperar el plazo entero de la respuesta.
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
const ESPERA_PROYECTOR_MS = 15000;    // lo que se espera, después del acuse, la respuesta del proyector a una orden
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
// va justo después de «$» y en grupos de tres (`_MONTO` de la herramienta)
const MONTO = /^[0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]{1,2})?$/u;
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

/** El estado que manda la presentación, solo con lo que se espera: {capitulo, paso, total, nombre, titulo, explicacion}
 * o null. */
export function estadoValido(e) {
  if (!e || typeof e !== 'object' || Array.isArray(e)) return null;
  const { capitulo, paso, total } = e;
  if (typeof capitulo !== 'string' || !ID.test(capitulo)) return null;
  if (!Number.isInteger(total) || total < 1 || total > 60 || !Number.isInteger(paso) || paso < 1 || paso > total) return null;
  const corto = (v, n) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, n) : '');
  return { capitulo, paso, total, nombre: corto(e.nombre, 80), titulo: corto(e.titulo, 200), explicacion: e.explicacion === true };
}

// ───────── La vista de esta pestaña ─────────

const cola = [];
// {aplicar(lista) → Promise<resultados>, estado() → estado | null, proyector?: true, cambio?() (la vista repinta su
// barra: el estado del proyector cambió)}
let control = null;
let cadena = Promise.resolve();
let enPantalla = null;   // la última explicación que esta pestaña mandó a una pantalla (la de aquí o el proyector)
let textoLocal = null;   // la que se le mandó a la vista de esta pestaña (`seguir` no se la repite)

const enPresentacion = () => {
  try { return (sinBase(location.pathname).replace(/\/+$/, '') || '/') === '/presentacion'; } catch { return false; }
};

/** Lo que va a quedar en pantalla con `lista`: la última explicación que trae (o ninguna, si la quita). */
function anotar(lista, previa) {
  let t = previa;
  for (const a of lista) {
    if (a?.explicacion) t = a.explicacion;
    else if (a?.op === 'quitar_explicacion') t = null;
  }
  return t;
}

function enOrden(lista) {
  const p = cadena.then(() => {
    if (!control) throw new Error('La presentación se cerró antes de aplicar el cambio');
    textoLocal = anotar(lista, textoLocal);
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
const proyectores = new Map();   // id → {visto, estado, sincronizando?}
const esperando = new Map();     // nro → {ok, mal, reloj}
let nro = 0;
let latido = 0;
let canal = null;

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
  if (!control?.proyector) return;
  let e = null;
  try { e = estadoValido(control.estado()); } catch { e = null; }
  publicar({ tipo: 'proyector', id: yo, estado: e, ...(recien ? { recien: true } : {}) });
}

/** Un proyector que se acaba de abrir: si esta pestaña tiene la vista abierta, le manda su capítulo, su paso y la
 * explicación que está en pantalla (la vista de aquí la muestra si `explicacion` es true en su estado). Hasta que
 * responda, la vista de aquí no lo sigue ni su estado cuenta: todavía está en la Portada. */
function sincronizar(id) {
  if (!control || control.proyector) return;
  let e = null;
  try { e = estadoValido(control.estado()); } catch { e = null; }
  if (!e) return;
  const ir = { tipo: 'presentacion', op: 'ir', capitulo: e.capitulo, paso: e.paso };
  const t = e.explicacion && enPantalla ? accionPresentacion({ ...ir, explicacion: enPantalla }) : null;
  const p = proyectores.get(id);
  if (p) p.sincronizando = true;
  const fin = () => { if (p) p.sincronizando = false; cambio(); };
  alProyector([t || ir], { para: id }).then(fin, fin);
}

/** Lo último que se supo de un proyector (sin perder si se está sincronizando). */
function verProyector(id, estado) {
  const p = proyectores.get(id) || {};
  p.visto = Date.now();
  p.estado = estado;
  proyectores.set(id, p);
}

/** El proyector que manda: el vivo que se vio último, con estado y ya sincronizado; o null. */
function guia() {
  if (!proyectorVivo()) return null;
  let mejor = null;
  for (const p of proyectores.values()) if (p.estado && !p.sincronizando && (!mejor || p.visto > mejor.visto)) mejor = p;
  return mejor;
}

/** Cambió lo que se sabe del proyector: la vista repinta su barra y sigue al proyector. */
function cambio() {
  try { control?.cambio?.(); } catch { /* la vista se fue */ }
  seguir();
}

// La vista de esta pestaña sigue al proyector: si no está en su capítulo y su paso, va allá (con la explicación, si la
// que se ve allá es la que mandó esta pestaña); si está, pone o quita la explicación como allá. Siempre con órdenes
// absolutas: no importa desde dónde parta ni cuántos avisos se pierdan (el latido lo vuelve a decir). Una sola a la vez;
// si mientras tanto llega otro estado, se vuelve a mirar al terminar. Mientras se le lleva al proyector un paso de aquí
// (`llevar`), no: lo que él diga hasta confirmarlo es de antes
let siguiendo = false;
let otraVez = false;
async function seguir() {
  if (!control || control.proyector || llevando) return;
  if (siguiendo) { otraVez = true; return; }
  const e = guia()?.estado;
  let local = null;
  try { local = estadoValido(control.estado()); } catch { local = null; }
  if (!e || !local) return;
  const texto = e.explicacion ? enPantalla : null;   // null: allá no se ve ninguna, o no es de esta pestaña
  let lista = null;
  if (local.capitulo !== e.capitulo || local.paso !== e.paso) {
    lista = [{ tipo: 'presentacion', op: 'ir', capitulo: e.capitulo, paso: e.paso, ...(texto ? { explicacion: texto } : {}) }];
  } else if (texto && !(local.explicacion && textoLocal === texto)) {
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

async function alMensaje(m) {
  if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
  if (m.tipo === 'proyector' && typeof m.id === 'string' && ID_VENTANA.test(m.id) && m.id !== yo) {
    verProyector(m.id, m.estado == null ? null : estadoValido(m.estado));
    if (m.recien === true) sincronizar(m.id);
    cambio();
  } else if (m.tipo === 'adios' && typeof m.id === 'string') {
    if (proyectores.delete(m.id)) cambio();
  } else if (m.tipo === 'quien') {
    anunciar();
  } else if (m.tipo === 'ordenes' && control?.proyector && typeof m.de === 'string' && ID_VENTANA.test(m.de)
             && Number.isInteger(m.nro) && Array.isArray(m.acciones) && m.acciones.length >= 1 && m.acciones.length <= 20
             && (m.para === undefined || m.para === yo)) {
    // Soy el proyector: acuso recibo en el acto (la otra pestaña sabe que sigo aquí), aplico (lo que no tiene la forma
    // de una acción vuelve como error, sin aplicarse) y respondo
    publicar({ tipo: 'recibido', id: yo, para: m.de, nro: m.nro });
    const acciones = m.acciones.map(accionPresentacion);
    let resultados;
    try {
      const validas = acciones.filter(Boolean);
      const r = validas.length ? await enOrden(validas) : [];
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
    publicar({ tipo: 'hecho', id: yo, para: m.de, nro: m.nro, resultados, estado });
  } else if (m.tipo === 'recibido' && m.para === yo && esperando.has(m.nro)) {
    // El proyector está vivo y aplicándola: ahora se espera su respuesta, con el plazo largo
    const it = esperando.get(m.nro);
    clearTimeout(it.reloj);
    it.reloj = setTimeout(() => {
      esperando.delete(m.nro);
      it.mal(new Error('La pantalla del proyector no respondió'));
    }, ESPERA_PROYECTOR_MS);
    const p = typeof m.id === 'string' ? proyectores.get(m.id) : null;
    if (p) p.visto = Date.now();
  } else if (m.tipo === 'hecho' && m.para === yo && esperando.has(m.nro)) {
    const it = esperando.get(m.nro);
    esperando.delete(m.nro);
    clearTimeout(it.reloj);
    const suyo = typeof m.id === 'string' && ID_VENTANA.test(m.id) && proyectores.has(m.id);
    if (suyo) verProyector(m.id, estadoValido(m.estado));
    it.ok((Array.isArray(m.resultados) ? m.resultados : []).slice(0, 20).map(resultadoValido));
    if (suyo) cambio();
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
  if (control?.proyector) return false;
  const ahora = Date.now();
  for (const [id, p] of proyectores) {
    if (ahora - p.visto <= VIVO_MS) return true;
    proyectores.delete(id);
  }
  return false;
}

/** Manda `lista` al proyector (a todos, o solo a `para`). Si nadie acusa recibo en ESPERA_ACUSE_MS, los proyectores
 * se dan por cerrados y la promesa falla con `sinProyector` (quien llamó la aplica aquí). */
function alProyector(lista, { para } = {}) {
  return new Promise((ok, mal) => {
    const n = ++nro;
    const it = { ok, mal };
    it.reloj = setTimeout(() => {
      esperando.delete(n);
      for (const id of para ? [para] : [...proyectores.keys()]) proyectores.delete(id);
      try { control?.cambio?.(); } catch { /* la vista se fue */ }   // la barra vuelve a la vista de aquí
      mal(Object.assign(new Error('La pantalla del proyector no respondió'), { sinProyector: true }));
    }, ESPERA_ACUSE_MS);
    esperando.set(n, it);
    publicar({ tipo: 'ordenes', de: yo, nro: n, acciones: lista, ...(para ? { para } : {}) });
  });
}

// ───────── Lo que usan la vista y el asistente ─────────

/** La vista se registra cuando su presentación avisó que cargó; devuelve la función que la quita (al salir de la
 * vista). Con `proyector: true` (la ventana /presentacion?pantalla=1), además se anuncia en el canal con un latido. */
export function registrarPresentacion(c) {
  if (!c || typeof c.aplicar !== 'function' || typeof c.estado !== 'function') return () => {};
  control = c;
  if (c.proyector) {
    clearInterval(latido);
    latido = setInterval(anunciar, LATIDO_MS);
    latido?.unref?.();
    anunciar(true);   // recién abierto: la pestaña con la vista abierta le pasa dónde está
  }
  vaciar();
  seguir();   // la vista que se abre con un proyector ya vivo va adonde está él
  return () => {
    if (control !== c) return;
    control = null;
    if (c.proyector) {
      clearInterval(latido);
      publicar({ tipo: 'adios', id: yo });
    }
  };
}

/** La vista avisa cada cambio de estado. El proyector lo anuncia en el acto (así el asistente y la pestaña del chat lo
 * saben). En la pestaña del chat, un cambio que no vino de seguir al proyector (la persona usó el control, el teclado o
 * el índice de la presentación de aquí) se le manda a él, con una orden absoluta: si no, la vista de aquí volvería al
 * paso del proyector con el latido siguiente. */
export function avisarEstado() {
  anunciar();
  llevar();
}

// Mientras el proyector no confirma lo que se le llevó, lo que diga de antes (un latido o la respuesta a una orden
// anterior, que pueden cruzarse con esta) no cuenta: si no, la vista de aquí volvería al paso viejo y después otra vez
// al nuevo, y la persona la vería saltar. Un segundo cambio de la persona en ese tiempo también se le lleva
let llevando = 0;
let llevado = null;
function llevar() {
  if (!control || control.proyector || siguiendo || !proyectorVivo()) return;
  const e = llevando ? llevado : guia()?.estado;
  let local = null;
  try { local = estadoValido(control.estado()); } catch { local = null; }
  if (!e || !local || (local.capitulo === e.capitulo && local.paso === e.paso)) return;
  llevado = { capitulo: local.capitulo, paso: local.paso };
  llevando++;
  const fin = () => { llevando--; cambio(); };
  alProyector([{ tipo: 'presentacion', op: 'ir', ...llevado }]).then(fin, fin);
}

/** La vista no puede mostrar la presentación (no hay sitio en este servidor): lo que esperaba falla con ese motivo. */
export function presentacionNoDisponible(motivo) { rechazarCola(motivo || 'La presentación no está disponible'); }

export const presentacionLista = () => !!control;
export const accionesEnCola = () => cola.length;

/** Dónde está la presentación ({capitulo, paso, total, nombre, titulo, explicacion}) o null si no hay una abierta: la
 * del proyector si hay uno vivo (la que ve la sala: también la barra de la vista la muestra), si no la de esta pestaña.
 * Nunca lanza: va en el contexto de cada mensaje. */
export function estadoPresentacion() {
  try {
    const p = llevando ? null : guia();   // mientras se le lleva un paso, el que vale es el de aquí
    if (p) return p.estado;
    return control ? estadoValido(control.estado()) : null;
  } catch {
    return null;
  }
}

/** Aplica `acciones` (las de `accionPresentacion`) y resuelve con un resultado por acción ({op, ok, error?}). Con un
 * proyector vivo van solo a él, que las aplica desde su paso (la vista de esta pestaña, si está abierta, lo sigue); si
 * no, a la vista, y si no está abierta se navega con `navegar` a /presentacion y se aplican al quedar lista. Un
 * proyector que no acusa recibo (se cerró sin avisar) se da por cerrado y la lista va a esta pestaña, como si no hubiera
 * habido proyector: la vista de aquí estaba en su paso. */
export function accionesPresentacion(acciones, { navegar, espera = ESPERA_MS } = {}) {
  const lista = (Array.isArray(acciones) ? acciones : acciones ? [acciones] : []).slice(0, 20);
  enPantalla = anotar(lista, enPantalla);
  if (proyectorVivo()) {
    return alProyector(lista).catch((e) => {
      if (!e?.sinProyector) throw e;
      return enLaVista(lista, { navegar, espera });
    });
  }
  return enLaVista(lista, { navegar, espera });
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
globalThis.addEventListener?.('pagehide', () => { if (control?.proyector) publicar({ tipo: 'adios', id: yo }); });
