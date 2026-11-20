// La voz de esta ventana (docs/agente.md, «La voz clonada de Mnemo» y «Respuestas habladas»): una sola salida de
// audio para todo lo que el panel dice en voz alta en una ventana: la narración del plan guiado (vistas/presentacion.js,
// con reproductor.js), las respuestas habladas del asistente (agente.js, con locutor.js) y la prueba de Ajustes
// (vistas/ajustes.js). Las tres comparten la misma voz: si cada una tuviera la suya, la sala oiría dos a la vez.
//
// * `tomarVoz(quien)` ('narracion', 'respuestas' o 'prueba') da una voz con la forma de voz.js (y `preparar`, `motor`
//   y `nivel` de voz-clonada.js). La primera la crea: la voz clonada de Mnemo (`crearVozClonada`) con la del navegador
//   (`crearVoz`) de respaldo; las demás reciben la misma, y `soltar()` de cada una la devuelve: con la última se suelta
//   de verdad (sin oyentes de la ventana, callada y con su audio cerrado). El asistente toma la suya la primera vez que
//   va a leer una respuesta y no la suelta (vive en document.body); la vista de la presentación, al montarse.
// * La narración manda: mientras suena un plan en esta ventana (`ocupada` de la narración: el reproductor tiene uno que
//   no está en pausa) o la voz dice una de sus frases, una respuesta no se dice (`decir` resuelve 'cortada'; el locutor
//   ya espera antes a que el plan se pause); y un plan que empieza (su primera precarga o su primera frase) calla la
//   respuesta en curso. `callar` de cada quien calla solo lo suyo: la
//   vista que se va (o el reproductor entre dos pasos) no corta la respuesta que se está leyendo, ni el asistente que
//   deja de leer corta la narración. La prueba de Ajustes es un clic del administrador: calla lo que suene.
// * El audio de la voz clonada lo pide `flujo('/api/agente/voz', ref, …)` de api.js (con la sesión y el CSRF, como el
//   chat): solo cuando GET /api/agente/estado dice que esta persona la puede usar (`voz.disponible`); si no, ni se
//   intenta (sin errores en la consola ni pedidos de más). Ese estado lo trae el asistente cuando lo lee
//   (`fijarInfoVoz`); en una ventana sin asistente (un rol que no lo usa) lo pide esta misma voz, y lo vuelve a pedir
//   con `agente:estado` (Ajustes cambió algo). Si la voz clonada pasa a la del navegador para la sesión (409 `sin_voz`,
//   403 `voz_rol`), se avisa `agente:estado`: el asistente vuelve a leer su estado y deja de ofrecer leer respuestas.
// Nada de lo que se dice se guarda: lo que va y vuelve es la referencia de la frase y su audio, en memoria.
import { api, flujo } from './api.js';
import { crearVoz } from './voz.js';
import { crearVozClonada } from './voz-clonada.js';

export const RUTA_VOZ = '/api/agente/voz';
export const QUIENES = ['narracion', 'respuestas', 'prueba'];
const EVENTO_ESTADO = 'agente:estado';   // el de agente.js y vistas/ajustes.js
const ESPERA_INFO_MS = 1200;             // lo que se espera al asistente (que lee el estado) antes de pedirlo aquí
const INACTIVIDAD_MS = 20000;            // sin una línea del flujo (el servidor manda un latido cada 15 s)
const MAX_NOMBRE = 60;

/** Sin voz clonada para esta persona: la voz del navegador. */
export const SIN_VOZ = Object.freeze({ disponible: false, nombre: null, respuestas: false, automatica: false });

/** `voz` de GET /api/agente/estado con la forma esperada ({disponible, nombre, respuestas, automatica}), o SIN_VOZ. */
export function vozDelEstado(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v) || v.disponible !== true) return SIN_VOZ;
  const nombre = typeof v.nombre === 'string' ? v.nombre.replace(/[\u0000-\u001f\u007f\s]+/g, ' ').trim().slice(0, MAX_NOMBRE) : '';
  return Object.freeze({ disponible: true, nombre: nombre || null, respuestas: v.respuestas === true,
    automatica: v.automatica === true });
}

let info = SIN_VOZ;
let deAgente = false;   // el asistente trae el estado (`fijarInfoVoz`): aquí no se pide
let leyendo = null;
let tInfo = 0;
let compartida = null;  // {voz, cuentas, hablando: quien | null, turno, ocupadas: Map, oyentes: Set, quitar}

const iguales = (a, b) => a.disponible === b.disponible && a.nombre === b.nombre && a.respuestas === b.respuestas
  && a.automatica === b.automatica;

function poner(nueva) {
  const cambio = !iguales(nueva, info);
  info = nueva;
  const c = compartida;
  if (!cambio || !c) return;
  // Recién ofrecida, en una ventana que ya tuvo un gesto: se activa sin esperar otro
  try { if (info.disponible && globalThis.navigator?.userActivation?.hasBeenActive === true) c.voz.gesto(); } catch { /* nada */ }
  avisarTodos(c);
}

/** El asistente leyó su estado (GET /api/agente/estado): la voz de esta ventana usa su `voz`. */
export function fijarInfoVoz(v) {
  deAgente = true;
  clearTimeout(tInfo);
  poner(vozDelEstado(v));
}

/** Lo último que se sabe de la voz clonada para esta persona ({disponible, nombre, respuestas, automatica}). */
export const infoVoz = () => info;

function leer() {
  leyendo ||= (async () => {
    try {
      const d = await api.get('/api/agente/estado');
      if (!deAgente) poner(vozDelEstado(d?.voz));
    } catch { /* sin estado: sigue la que había (la del navegador si nunca se supo) */ } finally { leyendo = null; }
  })();
  return leyendo;
}

const alEstado = () => { if (!deAgente) leer(); };

/** Lo que el panel responde por la voz clonada: el flujo de POST /api/agente/voz (voz-clonada.js lo lee). */
const pedir = (ref, { signal, alEvento }) => flujo(RUTA_VOZ, ref, { signal, alEvento, inactividad: INACTIVIDAD_MS });

function avisarTodos(c) {
  let e;
  try { e = c.voz.estado(); } catch { return; }
  for (const f of [...c.oyentes]) { try { f(e); } catch { /* el oyente se fue */ } }
}

function crear() {
  const c = { voz: null, cuentas: 0, hablando: null, turno: 0, ocupadas: new Map(), oyentes: new Set(), quitar: [] };
  const caer = () => { try { globalThis.dispatchEvent?.(new Event(EVENTO_ESTADO)); } catch { /* sin ventana */ } };
  c.voz = crearVozClonada({ ventana: globalThis, pedir, respaldo: crearVoz(), disponible: () => info.disponible, alCaer: caer });
  c.quitar.push(c.voz.alCambiar(() => avisarTodos(c)));
  try {
    globalThis.addEventListener?.(EVENTO_ESTADO, alEstado);
    c.quitar.push(() => globalThis.removeEventListener?.(EVENTO_ESTADO, alEstado));
  } catch { /* sin ventana */ }
  // Sin el asistente que traiga el estado (no lo usa este rol, o todavía no lo leyó), se pide aquí
  if (!deAgente) {
    clearTimeout(tInfo);
    tInfo = setTimeout(() => { if (!deAgente) leer(); }, ESPERA_INFO_MS);
  }
  return c;
}

/** ¿Suena (o está por sonar) la narración de un plan en esta ventana? */
function narracionOcupada(c) {
  if (c.hablando === 'narracion') return true;
  for (const f of c.ocupadas.values()) { try { if (f() === true) return true; } catch { /* nada */ } }
  return false;
}

/** La voz de esta ventana para `quien` ('narracion', 'respuestas' o 'prueba'). `ocupada()` (la narración): ¿hay un
 * plan sonando, que no está en pausa? (entre una frase y otra también: mientras tanto no se leen respuestas). */
export function tomarVoz(quien = 'narracion', { ocupada = null } = {}) {
  if (!QUIENES.includes(quien)) throw new Error(`tomarVoz: «${quien}» no es de ${QUIENES.join(', ')}`);
  compartida ||= crear();
  const c = compartida;
  c.cuentas++;
  const propia = {};   // la llave de esta voz en `ocupadas`
  if (quien === 'narracion' && typeof ocupada === 'function') c.ocupadas.set(propia, ocupada);
  const mios = new Set();   // sus oyentes de alCambiar (se van con `soltar`)
  let suelta = false;
  const viva = () => !suelta && compartida === c;

  function decir(texto, o = {}) {
    if (!viva()) return Promise.resolve('fallo');
    if (quien === 'respuestas' && narracionOcupada(c)) return Promise.resolve('cortada');
    const mia = ++c.turno;
    c.hablando = quien;
    return c.voz.decir(texto, o).then((r) => {
      if (c.turno === mia) c.hablando = null;
      return r;
    });
  }
  function callar() {
    if (!viva()) return;
    if (c.hablando === null || c.hablando === quien || quien === 'prueba') c.voz.callar();
  }
  function preparar(items) {
    if (!viva()) return;
    if (quien === 'respuestas' && narracionOcupada(c)) return;
    // un plan que empieza calla la respuesta que se estaba leyendo
    if (quien === 'narracion' && c.hablando === 'respuestas') c.voz.callar();
    c.voz.preparar(items);
  }

  return {
    estado: () => c.voz.estado(),
    encender: () => { if (viva()) c.voz.encender(); },
    apagar: () => { if (viva()) c.voz.apagar(); },
    activar: () => { if (viva()) c.voz.activar(); },
    gesto: () => { if (viva()) c.voz.gesto(); },
    decir, callar, preparar,
    motor: () => (viva() ? c.voz.motor() : 'navegador'),
    nivel: () => (viva() && c.hablando === quien ? c.voz.nivel() : 0),
    alCambiar(f) {
      if (typeof f !== 'function') return () => {};
      c.oyentes.add(f);
      mios.add(f);
      return () => { c.oyentes.delete(f); mios.delete(f); };
    },
    /** Esta voz deja de usarse: calla lo suyo y, si era la última, la voz de la ventana se suelta. */
    soltar() {
      if (suelta) return;
      if (c.hablando === quien) c.voz.callar();
      suelta = true;
      c.ocupadas.delete(propia);
      for (const f of mios) c.oyentes.delete(f);
      mios.clear();
      c.cuentas--;
      if (c.cuentas > 0) return;
      for (const q of c.quitar) { try { q(); } catch { /* nada */ } }
      try { c.voz.soltar(); } catch { /* nada */ }
      if (compartida === c) compartida = null;
      clearTimeout(tInfo);
    },
  };
}
