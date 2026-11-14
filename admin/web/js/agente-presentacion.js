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
//   con la orden ya acusada, tampoco se pierde: va al proyector que quede o a la vista de aquí. Un proyector que solo
//   estaba ocupado (armando su maqueta 3D) recibe la lista al liberarse y la aplica igual, salvo la que trae un
//   recorrido: esa caduca (`hasta`), porque ya suena aquí y sonaría en los dos. Cuando ese proyector vuelve, el recorrido
//   que suena aquí se le pasa desde la escena en curso, como al abrirse (`seguir`).
// * La pestaña que sigue a un proyector le pregunta cada latido si sigue ahí («quien») y él contesta en el acto: su
//   propio latido es un reloj, y el navegador espacia los relojes de una pestaña oculta (hasta uno por minuto).
//
// El recorrido narrado (reproductor.js, docs/agente.md): la acción `recorrido` trae las escenas ya absolutas y se
// valida aquí entera (`recorridoValido`) antes de reproducirse en la vista o en el proyector. El avance que va
// diciendo el reproductor (`avisarRecorrido`) llega a los oyentes de esta pestaña (la tarjeta del chat) y, si esta
// ventana es el proyector, a las demás por el canal (`recorrido`), aceptado solo del que manda. Los controles de la
// tarjeta (`controlRecorrido`) van adonde suena. Si se abre un proyector mientras el recorrido suena aquí, se le pasa
// desde la escena en curso (`sincronizar`); si el proyector que lo reproducía se cierra, la tarjeta lo sabe y ofrece
// reanudarlo. Mientras suena en el proyector, la persona que mueve la presentación de esta pestaña lo pausa allá (no se
// le lleva su paso: eso lo detendría como si el asistente hubiera pedido otra cosa).
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
const MARGEN_ACUSE_MS = 500;          // una lista que caduca vence esto antes del plazo del acuse (lo que tarda en volver)
const ESPERA_FILA_MS = 60000;         // lo que una orden acusada puede esperar en la fila del proyector a que la empiece
const ESPERA_PROYECTOR_MS = 15000;    // y desde que la empieza, su respuesta, por acción (él espera 12 s a la presentación)
const OPS = new Set(['ir', 'siguiente', 'anterior', 'explicar', 'quitar_explicacion', 'vista', 'visual', 'pantalla_completa',
  'recorrido', 'control_recorrido', 'preparando']);
// `vista`: lo que se ve sin cambiar de paso; `pantalla_completa`: la vista llena la ventana (la pone la vista, no mando)
const PARTES_VISTA = ['panel', 'indice', 'fichas'];
const ID = /^[a-z_]{2,40}$/;
const ID_PIEZA = /^[a-z0-9_]{1,40}$/;   // un componente o una inmersión de la propuesta
// `visual` (la presentación técnica): cada parte con los valores que admite (`VISUAL` de mando.js, `PARTES_VISUAL` de la
// herramienta y `VISUAL` de app/pantalla.py). null en enfoque, detalle, inmersion y rumbo es «lo del paso»
const CAMARAS = ['paso', 'aerea', 'oblicua', 'rasante', 'cerca', 'lejos'];
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
const PARTES_VISUAL = Object.keys(VISUAL);
// lo visual de cada paso (al cambiar de paso vuelve a esto; el tema no)
const VISUAL_INICIAL = { enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null };
const DEL_RECORRIDO = ['recorrido', 'desde', 'rid', 'accion', 'suave', 'motivo'];
const CLAVES = new Set(['tipo', 'op', 'capitulo', 'paso', 'explicacion', 'panel', 'indice', 'fichas', 'activar', ...PARTES_VISUAL,
  ...DEL_RECORRIDO]);
const ID_VENTANA = /^[a-z0-9]{8,40}$/;
// Lo que la explicación no puede traer (`texto_proyectable` de app/proyectable.py, `textoVisible` de mando.js, con las
// mismas reglas): se proyecta ante una sala. La «@», los números y la plata se buscan en la forma NFKC
// del texto (la «＠» y el «＄» de ancho completo, los dígitos en superíndice o de ancho completo y los guiones de
// compatibilidad cuentan como los comunes); TIRADA son los dígitos con lo que los separa al escribir un teléfono o una
// cédula (también pegados con el apóstrofo recto o tipográfico, el acento agudo o grave que se escribe en su lugar, la
// prima o un punto de viñeta: «71'234.567» o «71´234.567», con el
// apóstrofo de los millones, es como se escribe a mano una cédula en Colombia), y PERIODO y RANGO lo único que puede
// pasar de 6 dígitos (un periodo y un rango de cifras de la propuesta, de menor a mayor). Antes se quitan las fechas que
// existen (FECHA: «15/11/2026», «2026-11-15», de 1900 a 2099): cada una corta la tirada
const NO_SE_VE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\u{34f}\u{115f}\u{1160}\u{17b4}\u{17b5}\u{2800}\u{3164}\u{ffa0}\u{180b}-\u{180f}\u{fe00}-\u{fe0f}\u{e0000}-\u{e0fff}]/u;
const ACENTOS = /[\p{Mn}\p{Me}]{3,}/u;
// (pegados: . , _ · ( ' ‘ ’ ` ʹ ʼ ′ ‧ • ∙ ・, y «´», que en la forma NFKC es un espacio y un acento combinante; los de
// ancho completo ya quedaron como estos en la forma NFKC)
const TIRADA = /\p{Nd}+(?:(?:[.,_\u00b7'\u2018\u2019\u2032\u2027\u2022\u2219\u30fb\u0060\u02b9\u02bc(]| \u0301|\) ?|\)? ?[\-\u2010-\u2015\u2212\/] ?\(?| )\p{Nd}+)*/gu;
const PERIODO = /^((?:19|20)[0-9]{2}) ?[\-\u2010-\u2015\u2212\/] ?((?:19|20)[0-9]{2})$/u;
const RANGO = /^([0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?) ?[\-\u2010-\u2015\u2212] ?([0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?)$/u;
const FECHA = /(?<!\p{Nd})(?:([0-9]{4}) ?([.\-\u2010-\u2015\u2212\/]) ?([0-9]{1,2}) ?\2 ?([0-9]{1,2})|([0-9]{1,2}) ?([.\-\u2010-\u2015\u2212\/]) ?([0-9]{1,2}) ?\6 ?([0-9]{4}))(?!\p{Nd})/gu;
// Lo que delata un costo (`PLATA` de app/proyectable.py y de mando.js, la misma regla): el signo, «COP», «pesos»,
// «billones de», «billón de» o «millones de pesos», en mayúsculas o minúsculas. La presentación que maneja el panel es siempre la
// técnica, que no muestra plata: nada de lo que se le manda la lleva (ni la explicación ni el recorrido). La de
// tecnica.js, que limpia los datos de la propuesta, es otra cosa y no cambia con esta
const PLATA = /[$\u{1F4B2}]|\bcop\b|\bpesos\b|\bbill(?:ones|[o\u00f3\u00d3]n) de\b|millones de pesos/iu;
const DIGITOS_MAX = 6;

// ───────── El recorrido narrado (app/recorrido.py: los mismos topes y listas; una prueba los compara) ─────────
export const MAX_TITULO = 80;
export const MAX_FRASES = 3;
export const MAX_ESCENAS = 8;
export const MAX_PUNTO = 80;
export const MAX_CIERRE = 200;
export const MAX_SOSTENER_MS = 8000;
export const RESALTAR = { cifra: 12, punto: 20, leyenda: 12, especificacion: 20 };
export const FASES = ['preparando', 'narrando', 'sosteniendo', 'cierre', 'pausa', 'fin', 'detenido', 'error'];
export const TERMINALES = ['fin', 'detenido', 'error'];
// los que llegan a la vista (`reproducir` lo resuelve el servidor: vuelve como un recorrido nuevo)
export const CONTROLES = ['pausar', 'continuar', 'siguiente', 'anterior', 'repetir', 'detener'];
export const VOCES = ['activa', 'apagada', 'sin_activar', 'sin_voces'];
export const MOTIVOS = ['persona', 'tecla', 'boton', 'mensaje', 'otra_orden', 'reemplazo', 'proyector', 'sin_respuesta',
  'escena_fallida'];
export const AVISOS = ['atlas', 'resaltar', 'asiento', 'voz'];
const RID = /^[0-9a-f]{12}$/;
const VISUAL_ESCENA = Object.keys(VISUAL_INICIAL);
const entero = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const exactas = (o, claves) => !!o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).length === claves.length
  && claves.every((k) => Object.prototype.hasOwnProperty.call(o, k));
// un texto del recorrido: se proyecta tal cual (sin cambiarle nada: si no, no vale)
const tal = (v, max) => explicacionVisible(v, max) === v;

function resaltarValido(r) {
  if (r === null) return true;
  if (!r || typeof r !== 'object' || typeof r.tipo !== 'string') return false;
  if (r.tipo === 'componente') return exactas(r, ['tipo', 'id']) && typeof r.id === 'string' && ID_PIEZA.test(r.id);
  if (!Object.prototype.hasOwnProperty.call(RESALTAR, r.tipo)) return false;
  if (r.tipo === 'especificacion') return exactas(r, ['tipo', 'n', 'en']) && entero(r.n, 1, RESALTAR.especificacion) && (r.en === 'panel' || r.en === 'ficha');
  return exactas(r, ['tipo', 'n']) && entero(r.n, 1, RESALTAR[r.tipo]);
}

function escenaValida(e) {
  if (!exactas(e, ['capitulo', 'paso', 'panel', 'visual', 'resaltar', 'frases', 'sostener_ms'])) return null;
  if (typeof e.capitulo !== 'string' || !ID.test(e.capitulo) || !entero(e.paso, 1, 60) || typeof e.panel !== 'boolean') return null;
  if (!exactas(e.visual, VISUAL_ESCENA) || VISUAL_ESCENA.some((k) => !VISUAL[k](e.visual[k]))) return null;
  if (!resaltarValido(e.resaltar) || !entero(e.sostener_ms, 0, MAX_SOSTENER_MS)) return null;
  const f = e.frases;
  if (!Array.isArray(f) || !f.length || f.length > MAX_FRASES || !f.every((x) => tal(x, MAX_EXPLICACION))) return null;
  if (f.reduce((a, x) => a + [...x].length, 0) + f.length - 1 > MAX_EXPLICACION) return null;
  return { capitulo: e.capitulo, paso: e.paso, panel: e.panel, visual: { ...e.visual },
    resaltar: e.resaltar && { ...e.resaltar }, frases: [...f], sostener_ms: e.sostener_ms };
}

/** El recorrido absoluto que arma el servidor (`recorrido.validar`), copiado, o null si no tiene la forma exacta: id,
 * título, de 1 a MAX_ESCENAS escenas (cada una con su paso, lo visual completo, lo que resalta, de 1 a MAX_FRASES
 * frases que se proyectan tal cual y sin costos, y lo que se sostiene) y el cierre (null o de 1 a 3 puntos). */
export function recorridoValido(r) {
  if (!exactas(r, ['id', 'titulo', 'escenas', 'cierre'])) return null;
  if (typeof r.id !== 'string' || !RID.test(r.id) || !tal(r.titulo, MAX_TITULO)) return null;
  if (!Array.isArray(r.escenas) || !r.escenas.length || r.escenas.length > MAX_ESCENAS) return null;
  const escenas = r.escenas.map(escenaValida);
  if (escenas.some((e) => !e)) return null;
  let cierre = null;
  if (r.cierre !== null) {
    const pts = r.cierre?.puntos;
    if (!exactas(r.cierre, ['puntos']) || !Array.isArray(pts) || !pts.length || pts.length > 3) return null;
    if (!pts.every((x) => tal(x, MAX_PUNTO)) || pts.reduce((a, x) => a + [...x].length, 0) > MAX_CIERRE) return null;
    cierre = { puntos: [...pts] };
  }
  return { id: r.id, titulo: r.titulo, escenas, cierre };
}

/** El avance que dice el reproductor ({rid, n, de, fase, frase, voz, motivo?, aviso?, t_ms}, la forma de
 * `ProgresoEntrada` del servidor), o null. */
export function progresoValido(p) {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return null;
  const claves = ['rid', 'n', 'de', 'fase', 'frase', 'voz', 'motivo', 'aviso', 't_ms'];
  if (Object.keys(p).some((k) => !claves.includes(k))) return null;
  if (typeof p.rid !== 'string' || !RID.test(p.rid) || !entero(p.de, 1, MAX_ESCENAS) || !entero(p.n, 1, p.de)) return null;
  if (!FASES.includes(p.fase) || !entero(p.frase ?? 0, 0, MAX_FRASES - 1) || !VOCES.includes(p.voz)) return null;
  if (p.motivo != null && !MOTIVOS.includes(p.motivo)) return null;
  if (p.aviso != null && !AVISOS.includes(p.aviso)) return null;
  if (!entero(p.t_ms ?? 0, 0, 600000)) return null;
  return { rid: p.rid, n: p.n, de: p.de, fase: p.fase, frase: p.frase ?? 0, voz: p.voz,
    ...(p.motivo != null ? { motivo: p.motivo } : {}), ...(p.aviso != null ? { aviso: p.aviso } : {}), t_ms: p.t_ms ?? 0 };
}

/** Las acciones del recorrido: `recorrido` (el recorrido entero y, si se reanuda, `desde`), `control_recorrido` (rid,
 * accion de CONTROLES, `suave` solo con pausar y `motivo` 'otra_orden' solo con detener: el servidor lo cerró porque el
 * asistente mostró otra cosa) y `preparando` (activar: la píldora mientras el asistente arma). */
function accionRecorrido(a) {
  const solo = (claves) => Object.keys(a).every((k) => k === 'tipo' || k === 'op' || claves.includes(k));
  if (a.op === 'recorrido') {
    if (!solo(['recorrido', 'desde'])) return null;
    const r = recorridoValido(a.recorrido);
    if (!r || (a.desde !== undefined && !entero(a.desde, 1, r.escenas.length))) return null;
    return { tipo: 'presentacion', op: 'recorrido', recorrido: r, ...(a.desde !== undefined ? { desde: a.desde } : {}) };
  }
  if (a.op === 'control_recorrido') {
    if (!solo(['rid', 'accion', 'suave', 'motivo']) || typeof a.rid !== 'string' || !RID.test(a.rid) || !CONTROLES.includes(a.accion)) return null;
    if (a.suave !== undefined && (a.suave !== true || a.accion !== 'pausar')) return null;
    if (a.motivo !== undefined && (a.motivo !== 'otra_orden' || a.accion !== 'detener')) return null;
    return { tipo: 'presentacion', op: 'control_recorrido', rid: a.rid, accion: a.accion, ...(a.suave ? { suave: true } : {}),
      ...(a.motivo ? { motivo: a.motivo } : {}) };
  }
  if (!solo(['activar']) || typeof a.activar !== 'boolean') return null;
  return { tipo: 'presentacion', op: 'preparando', activar: a.activar };
}

/** La acción `presentacion` del servidor, normalizada, o null si no tiene la forma estricta: un objeto con solo las
 * claves conocidas, `op` de la lista, `capitulo` como id (obligatorio para `ir`), `paso` entero de 1 a 60 (solo con
 * `ir`), y `explicacion` de hasta MAX_EXPLICACION caracteres que se ve tal cual y sin costos (obligatoria para
 * `explicar`). `vista` lleva solo `panel`, `indice` y `fichas` (al menos una, cada una verdadero o falso; el índice y
 * las fichas no a la vez) y `pantalla_completa` solo `activar` (verdadero o falso). `visual` lleva solo sus partes (al
 * menos una, cada una con un valor de su lista). */
export function accionPresentacion(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || a.tipo !== 'presentacion') return null;
  if (Object.keys(a).some((k) => !CLAVES.has(k)) || typeof a.op !== 'string' || !OPS.has(a.op)) return null;
  if (a.op === 'recorrido' || a.op === 'control_recorrido' || a.op === 'preparando') return accionRecorrido(a);
  if (DEL_RECORRIDO.some((k) => a[k] !== undefined)) return null;
  const out = { tipo: 'presentacion', op: a.op };
  if (a.op === 'visual') {
    if (Object.keys(a).some((k) => k !== 'tipo' && k !== 'op' && !(k in VISUAL))) return null;
    const partes = PARTES_VISUAL.filter((k) => a[k] !== undefined);
    if (!partes.length || partes.some((k) => !VISUAL[k](a[k]))) return null;
    for (const k of partes) out[k] = a[k];
    return out;
  }
  if (PARTES_VISUAL.some((k) => a[k] !== undefined)) return null;
  if (a.op === 'vista' || a.op === 'pantalla_completa') {
    const suyas = a.op === 'vista' ? PARTES_VISTA : ['activar'];
    if (Object.keys(a).some((k) => k !== 'tipo' && k !== 'op' && !suyas.includes(k))) return null;
    for (const k of suyas) {
      if (a[k] === undefined) continue;
      if (typeof a[k] !== 'boolean') return null;
      out[k] = a[k];
    }
    if (a.op === 'vista' && (!PARTES_VISTA.some((k) => k in out) || (out.indice && out.fichas))) return null;
    if (a.op === 'pantalla_completa' && !('activar' in out)) return null;
    return out;
  }
  if ([...PARTES_VISTA, 'activar'].some((k) => a[k] !== undefined)) return null;
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
 * de cifras ni una fecha? (`numero_largo` de la herramienta: las fechas que existen se quitan antes y cortan la tirada).
 * Un monto en pesos («$1.156.350») ya no es excepción: PLATA lo frena antes */
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

/** El texto tal como se proyecta (los espacios seguidos en uno), o null si no se puede: la explicación de `explicar` y de
 * `ir`, la que dice el estado y los textos del recorrido, todos con la misma regla y sin una opción que deje pasar la
 * plata (así ninguno la proyecta por olvido). */
function explicacionVisible(v, max = MAX_EXPLICACION) {
  if (typeof v !== 'string' || NO_SE_VE.test(v) || ACENTOS.test(v)) return null;
  const t = v.replace(/\s+/g, ' ').trim();
  if (!t || [...t].length > max) return null;
  const k = t.normalize('NFKC').replace(/\s+/g, ' ').trim();
  if (PLATA.test(k)) return null;
  return k.includes('@') || numeroLargo(k) ? null : t;
}

/** El estado que manda la presentación, solo con lo que se espera: {capitulo, paso, total, nombre, titulo, explicacion,
 * texto, por, recorrido} o null. `texto` es la explicación que está a la vista (null si no hay, si no se puede mostrar
 * tal cual o si la presentación no lo dice); `por`: 'persona' si el último cambio lo hizo la persona (un paso, la
 * cámara: el recorrido que suena se pausa), si no 'orden'; `recorrido`: {rid, n, de} de la narración en pantalla. */
export function estadoValido(e) {
  if (!e || typeof e !== 'object' || Array.isArray(e)) return null;
  const { capitulo, paso, total } = e;
  if (typeof capitulo !== 'string' || !ID.test(capitulo)) return null;
  if (!Number.isInteger(total) || total < 1 || total > 60 || !Number.isInteger(paso) || paso < 1 || paso > total) return null;
  const corto = (v, n) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, n) : '');
  const explicacion = e.explicacion === true;
  const r = e.recorrido;
  const recorrido = r && typeof r === 'object' && typeof r.rid === 'string' && RID.test(r.rid) && entero(r.de, 1, MAX_ESCENAS)
    && entero(r.n, 1, r.de) ? { rid: r.rid, n: r.n, de: r.de } : null;
  return { capitulo, paso, total, nombre: corto(e.nombre, 80), titulo: corto(e.titulo, 200), explicacion,
    texto: explicacion ? explicacionVisible(e.texto) : null, por: e.por === 'persona' ? 'persona' : 'orden', recorrido };
}

// ───────── La pantalla en off (vistas/presentacion.js ?off=1, app/pantalla.py) ─────────

/** El estado de la pantalla en off que manda el servidor, o null si no tiene la forma exacta (lo aplica un iframe). */
export function estadoDePantalla(e) {
  if (!e || typeof e !== 'object' || Array.isArray(e)) return null;
  const { v, capitulo, paso, explicacion } = e;
  if (!Number.isInteger(v) || v < 0 || typeof capitulo !== 'string' || !ID.test(capitulo)) return null;
  if (!Number.isInteger(paso) || paso < 1 || paso > 60) return null;
  if (explicacion !== null && (typeof explicacion !== 'string' || !explicacion || explicacion.length > 400)) return null;
  if (['panel', 'indice', 'fichas', 'completa'].some((k) => typeof e[k] !== 'boolean')) return null;
  if (!Number.isSafeInteger(e.orden_completa) || e.orden_completa < 0) return null;
  // lo visual: lo que falta (un servidor de antes) es lo del paso; un valor que no cumple invalida el estado
  const visual = { ...VISUAL_INICIAL, tema: null };
  for (const k of PARTES_VISUAL) {
    if (e[k] === undefined) continue;
    if (k === 'tema' ? e[k] !== null && !VISUAL.tema(e[k]) : !VISUAL[k](e[k])) return null;
    visual[k] = e[k];
  }
  // El recorrido para esta pantalla (con su edad, que la calcula el servidor), el último control y el avance. Lo que no
  // tiene la forma se ignora (la pantalla aplica igual los campos base, que son la escena donde quedó)
  let recorrido = null, control = null, progreso = null;
  const x = e.recorrido;
  if (x && typeof x === 'object' && entero(x.edad_s, 0, 1e9)) {
    const r = recorridoValido({ id: x.id, titulo: x.titulo, escenas: x.escenas, cierre: x.cierre });
    if (r) recorrido = { ...r, edad_s: x.edad_s };
  }
  const c = e.control_recorrido;
  if (recorrido && c && typeof c === 'object' && c.rid === recorrido.id && (CONTROLES.includes(c.accion) || c.accion === 'reproducir')
      && entero(c.n, 1, 1e9)) control = { rid: c.rid, accion: c.accion, n: c.n };
  const pr = e.progreso;
  if (recorrido && pr && typeof pr === 'object' && pr.rid === recorrido.id && entero(pr.de, 1, MAX_ESCENAS) && entero(pr.n, 1, pr.de)
      && FASES.includes(pr.fase) && entero(pr.hace_s, 0, 1e9)) progreso = { rid: pr.rid, n: pr.n, de: pr.de, fase: pr.fase, hace_s: pr.hace_s };
  return { v, capitulo, paso, explicacion, panel: e.panel, indice: e.indice, fichas: e.fichas, completa: e.completa,
    orden_completa: e.orden_completa, ...visual, recorrido, control_recorrido: control, progreso };
}

/** Las órdenes para mando.js que llevan la presentación de `antes` (lo último que se aplicó, o null) a `e`. La pantalla
 * completa no va a mando: la pone la vista. Cambiar de paso cierra allá el índice y las fichas. */
export function ordenesHacia(antes, e) {
  const out = [];
  const otroPaso = !antes || antes.capitulo !== e.capitulo || antes.paso !== e.paso;
  if (otroPaso) {
    out.push({ orden: 'ir', capitulo: e.capitulo, paso: e.paso, ...(e.explicacion ? { explicacion: e.explicacion } : {}) });
  } else if (antes.explicacion !== e.explicacion) {
    out.push(e.explicacion ? { orden: 'explicar', explicacion: e.explicacion } : { orden: 'quitar_explicacion' });
  }
  const base = otroPaso ? { ...(antes || {}), indice: false, fichas: false, panel: antes ? antes.panel : true } : antes;
  const vista = {};
  for (const k of ['panel', 'indice', 'fichas']) if (base[k] !== e[k]) vista[k] = e[k];
  if (Object.keys(vista).length) out.push({ orden: 'vista', ...vista });
  // lo visual: al cambiar de paso la presentación lo deja como lo dice el paso (salvo el tema); se manda lo que difiere.
  // El tema solo va cuando hay uno (null es «el del navegador»: no se manda)
  const antesVisual = otroPaso ? { ...VISUAL_INICIAL, tema: antes?.tema ?? null } : antes;
  const visual = {};
  for (const k of PARTES_VISUAL) {
    const valor = e[k] === undefined ? (k === 'tema' ? null : VISUAL_INICIAL[k]) : e[k];
    const previo = antesVisual[k] === undefined ? (k === 'tema' ? null : VISUAL_INICIAL[k]) : antesVisual[k];
    if (valor !== previo && !(k === 'tema' && valor === null)) visual[k] = valor;
  }
  if (Object.keys(visual).length) out.push({ orden: 'visual', ...visual });
  return out;
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
// El recorrido: quién escucha el avance (la tarjeta del chat), lo último que se supo (de aquí o del proyector), lo que
// dijo cada proyector y los recorridos que esta pestaña le mandó a uno (para pasárselo a otro que se abra)
const oyentesRecorrido = new Set();
const avanceDe = new Map();      // id del proyector → su último avance
const enviados = new Map();      // rid → recorrido (los últimos 3)
let ultimoAvance = null;         // {p, donde: 'aqui'|'proyector'}
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
  // el recorrido que sonaba aquí lo sigue el nuevo (se lo pasa la pestaña del chat)
  try { control?.soltarRecorrido?.('reemplazo'); } catch { /* nada */ }
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
  if (soyProyector()) return;
  // Un recorrido que suena aquí pasa al proyector desde la escena en curso (allá está el audio de la sala); uno que
  // esta pestaña le había mandado a otro proyector que se retiró, también
  let lista = null;
  let enCurso = null;
  try { enCurso = control?.recorrido?.() || null; } catch { enCurso = null; }
  if (enCurso?.recorrido) {
    // lo último que dijo aquí cuenta como lo último del proyector hasta que él diga lo suyo: si se cierra antes, la
    // tarjeta lo sabe (`olvidar`) y ofrece reanudarlo, en vez de quedarse sonando
    const u = ultimoAvance?.p;
    if (u?.rid === enCurso.recorrido.id && !TERMINALES.includes(u.fase) && !avanceDe.has(id)) avanceDe.set(id, u);
    try { control.soltarRecorrido?.('proyector'); } catch { /* nada */ }
    lista = [{ tipo: 'presentacion', op: 'recorrido', recorrido: enCurso.recorrido, desde: enCurso.n }];
  } else if (ultimoAvance?.donde === 'proyector' && enviados.has(ultimoAvance.p.rid)
             && (!TERMINALES.includes(ultimoAvance.p.fase) || ultimoAvance.p.motivo === 'reemplazo')) {
    lista = [{ tipo: 'presentacion', op: 'recorrido', recorrido: enviados.get(ultimoAvance.p.rid), desde: ultimoAvance.p.n }];
  }
  if (!lista) {
    if (!control) return;
    let e = null;
    try { e = estadoValido(control.estado()); } catch { e = null; }
    if (!e) return;
    lista = [{ tipo: 'presentacion', op: 'ir', capitulo: e.capitulo, paso: e.paso, ...(e.texto ? { explicacion: e.texto } : {}) }];
  }
  const p = proyectores.get(id);
  if (p) p.sincronizando = true;
  const fin = () => { if (p) p.sincronizando = false; cambio(); };
  alProyector(lista, id).then(fin, fin);
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
  // el recorrido que sonaba allá se cortó: la tarjeta lo dice y ofrece reanudarlo
  const ult = avanceDe.get(id);
  avanceDe.delete(id);
  if (ult && !TERMINALES.includes(ult.fase)) alAvance({ ...ult, fase: 'detenido', motivo: 'proyector' }, 'proyector');
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
  // Un recorrido que suena aquí con un proyector que manda: se reprodujo aquí porque él no acusó a tiempo (ocupado), y
  // ya volvió. Se le pasa desde la escena en curso, como al abrirse (allá mira la sala), en vez de llevar la vista de
  // aquí a su paso: eso lo detendría como si el asistente hubiera pedido otra cosa
  let enCurso = null;
  try { enCurso = control.recorrido?.() || null; } catch { enCurso = null; }
  if (enCurso?.recorrido) {
    const p = elegido();
    if (p && !p.sincronizando) sincronizar(p.id);
    return;
  }
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
  } else if (m.tipo === 'recorrido' && otra) {
    // el avance del recorrido que suena en el proyector: solo del que manda
    const p = progresoValido(m.progreso);
    const el = elegido();
    if (p && el && el.id === m.id) {
      el.visto = Date.now();
      avanceDe.set(m.id, p);
      alAvance(p, 'proyector');
    }
  } else if (m.tipo === 'ordenes' && soyProyector() && typeof m.de === 'string' && ID_VENTANA.test(m.de)
             && Number.isInteger(m.nro) && Array.isArray(m.acciones) && m.acciones.length >= 1 && m.acciones.length <= 20
             && (m.para === undefined || m.para === yo)) {
    // Soy el proyector: acuso recibo en el acto (la otra pestaña sabe que sigo aquí), aviso cuando la empiezo, aplico (lo
    // que no tiene la forma de una acción vuelve como error, sin aplicarse) y respondo. Una lista que caducó mientras
    // esta ventana estaba ocupada no se aplica ni se acusa: la otra pestaña ya la aplicó en su vista (el mismo
    // navegador, el mismo reloj: el canal es por origen)
    if (Number.isFinite(m.hasta) && Date.now() > m.hasta) return;
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

function alAvance(p, donde) {
  ultimoAvance = { p, donde };
  for (const f of [...oyentesRecorrido]) { try { f(p, donde); } catch { /* el oyente se fue */ } }
}

/** El reproductor de esta pestaña avisa su avance: a los oyentes de aquí y, si esta ventana es el proyector, a las
 * demás pestañas. */
export function avisarRecorrido(p) {
  const v = progresoValido(p);
  if (!v) return;
  alAvance(v, 'aqui');
  if (soyProyector()) publicar({ tipo: 'recorrido', id: yo, progreso: v });
}

/** Escucha el avance de los recorridos (de aquí o del proyector que manda): f(progreso, donde). Devuelve cómo dejar de
 * escuchar. */
export function escucharRecorrido(f) {
  if (typeof f !== 'function') return () => {};
  oyentesRecorrido.add(f);
  return () => oyentesRecorrido.delete(f);
}

/** El último avance que se supo ({...progreso, donde}) si el recorrido sigue sonando, o null. */
export function recorridoEnCurso() {
  const u = ultimoAvance;
  return u && !TERMINALES.includes(u.p.fase) ? { ...u.p, donde: u.donde } : null;
}

/** Un control del recorrido `rid` (pausar, continuar, siguiente, anterior, repetir, detener) adonde suena: el proyector
 * que manda o la vista de aquí. Nunca abre la vista: sin una presentación abierta, falla. */
export function controlRecorrido(rid, accion, { suave = false } = {}) {
  const a = accionPresentacion({ tipo: 'presentacion', op: 'control_recorrido', rid, accion, ...(suave ? { suave: true } : {}) });
  if (!a) return Promise.reject(new Error('Control no válido'));
  const p = elegido();
  if (p) return alProyector([a], p.id).then((r) => r?.[0] || { ok: false });
  if (control) return enOrden([a]).then((r) => r?.[0] || { ok: false });
  return Promise.reject(new Error('No hay una presentación abierta'));
}

/** Un recorrido que esta pestaña le manda a un proyector: se guarda (los últimos 3) para pasárselo a otro que se abra. */
function recordar(lista) {
  for (const a of lista) {
    if (a?.op !== 'recorrido' || !a.recorrido) continue;
    enviados.delete(a.recorrido.id);
    enviados.set(a.recorrido.id, a.recorrido);
    while (enviados.size > 3) enviados.delete(enviados.keys().next().value);
  }
}

/** Manda `lista` al proyector `para`. Si no acusa recibo en ESPERA_ACUSE_MS, o se cierra antes de responder, se da por
 * cerrado y la promesa falla con `sinProyector` (quien llamó la aplica en otro lado). Con `caduca`, el proyector no la
 * aplica si le llega después de ese plazo (estaba ocupado): quien llamó ya la aplicó en otro lado. */
function alProyector(lista, para, { caduca = false } = {}) {
  return new Promise((ok, mal) => {
    const n = ++nro;
    recordar(lista);
    const it = { ok, mal, para, n: Math.max(1, lista.length) };
    it.reloj = setTimeout(() => {
      if (esperando.get(n) !== it) return;
      olvidar(para);
      cambio();   // la barra vuelve a la vista de aquí (o al proyector que quede)
    }, ESPERA_ACUSE_MS);
    esperando.set(n, it);
    publicar({ tipo: 'ordenes', de: yo, nro: n, acciones: lista, para,
      ...(caduca ? { hasta: Date.now() + ESPERA_ACUSE_MS - MARGEN_ACUSE_MS } : {}) });
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
  // Con un recorrido sonando en el proyector, la persona que mueve la presentación de aquí (su control, el teclado, el
  // índice: aquí no hay narración que los tome) no le lleva el paso, que lo detendría como si el asistente hubiera
  // pedido otra cosa: lo pausa, como cuando se mueve la imagen allá (docs/agente.md), y la vista de aquí vuelve a la
  // escena que se ve allá
  const rc = recorridoEnCurso();
  if (rc?.donde === 'proyector') {
    controlRecorrido(rc.rid, 'pausar').then(cambio, cambio);
    return;
  }
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
  // Un recorrido que el proyector no acusa a tiempo se reproduce aquí: si lo aplicara al liberarse, sonaría en los dos.
  // Las demás órdenes no caducan: aplicadas tarde, el proyector queda en el mismo paso que la vista de aquí (que lo
  // sigue), y sin ellas volvería a su paso viejo y la vista de aquí con él
  const caduca = lista.some((a) => a?.op === 'recorrido');
  const probados = new Set();
  for (let p = elegido(); p && !probados.has(p.id); p = elegido()) {
    probados.add(p.id);
    try {
      return sinPaso(await alProyector(conPaso(), p.id, { caduca }));
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
