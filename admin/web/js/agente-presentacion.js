// Puente entre el asistente y la presentación de la propuesta (vistas/presentacion.js), con el patrón de agente-mapa.js:
// las acciones se aplican en orden; mientras la vista no está abierta y lista (su iframe avisó que cargó) esperan en una
// cola, con plazo, y si hace falta se navega a /presentacion una sola vez.
//
// El modo proyector: la ventana /presentacion?pantalla=1 (otra pestaña del panel, a pantalla completa en el proyector) se
// anuncia por BroadcastChannel con un latido. Mientras haya un proyector vivo, esta pestaña le manda a él las órdenes en
// vez de abrir la vista aquí (si la vista está abierta aquí también, la sigue), y el proyector devuelve su estado. Todo
// mensaje del canal se valida: lo manda otra pestaña del mismo origen, pero sigue siendo una entrada.
//
// Solo importa base.js y `navegar` (el `ir` de app.js) llega por parámetro: así no depende de app.js y se prueba con
// Node (admin/tests/test_agente_presentacion.py).
import { sinBase } from './base.js';

export const CANAL = 'yondo-presentacion';
export const VERSION = 1;
export const MAX_EXPLICACION = 400;   // `MAX_EXPLICACION` de la herramienta y de mando.js: una prueba los compara
const ESPERA_MS = 30000;              // la presentación carga datos y la maqueta 3D: en un equipo lento, varios segundos
const ESPERA_MAX_MS = 120000;
const LATIDO_MS = 2000;               // el proyector se anuncia cada tanto
const VIVO_MS = 6500;                 // sin anuncios en este tiempo, se da por cerrado
const ESPERA_PROYECTOR_MS = 15000;    // lo que se espera la respuesta del proyector a una orden
const OPS = new Set(['ir', 'siguiente', 'anterior', 'explicar', 'quitar_explicacion']);
const CLAVES = new Set(['tipo', 'op', 'capitulo', 'paso', 'explicacion']);
const ID = /^[a-z_]{2,40}$/;
const ID_VENTANA = /^[a-z0-9]{8,40}$/;
// Lo que la explicación no puede traer (`_explicacion_visible` de la herramienta, `textoVisible` de mando.js): se
// proyecta ante una sala
const NO_SE_VE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\u{34f}\u{115f}\u{1160}\u{17b4}\u{17b5}\u{2800}\u{3164}\u{ffa0}\u{180b}-\u{180f}\u{fe00}-\u{fe0f}\u{e0000}-\u{e0fff}]/u;
const ACENTOS = /[\p{Mn}\p{Me}]{3,}/u;
const DIGITOS = /\p{Nd}(?:[ .-]?\p{Nd}){6,}/u;

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

function explicacionVisible(v) {
  if (typeof v !== 'string' || NO_SE_VE.test(v) || ACENTOS.test(v)) return null;
  const t = v.replace(/\s+/g, ' ').trim();
  if (!t || [...t].length > MAX_EXPLICACION || DIGITOS.test(t) || t.includes('@')) return null;
  return t;
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
let control = null;   // {aplicar(lista) → Promise<resultados>, estado() → estado | null, proyector?: true}
let cadena = Promise.resolve();

const enPresentacion = () => {
  try { return (sinBase(location.pathname).replace(/\/+$/, '') || '/') === '/presentacion'; } catch { return false; }
};

function enOrden(lista) {
  const p = cadena.then(() => {
    if (!control) throw new Error('La presentación se cerró antes de aplicar el cambio');
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
const proyectores = new Map();   // id → {visto, estado}
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

function anunciar() {
  if (!control?.proyector) return;
  let e = null;
  try { e = estadoValido(control.estado()); } catch { e = null; }
  publicar({ tipo: 'proyector', id: yo, estado: e });
}

async function alMensaje(m) {
  if (!m || typeof m !== 'object' || Array.isArray(m) || m.canal !== CANAL || m.v !== VERSION) return;
  if (m.tipo === 'proyector' && typeof m.id === 'string' && ID_VENTANA.test(m.id) && m.id !== yo) {
    proyectores.set(m.id, { visto: Date.now(), estado: m.estado == null ? null : estadoValido(m.estado) });
  } else if (m.tipo === 'adios' && typeof m.id === 'string') {
    proyectores.delete(m.id);
  } else if (m.tipo === 'quien') {
    anunciar();
  } else if (m.tipo === 'ordenes' && control?.proyector && typeof m.de === 'string' && ID_VENTANA.test(m.de)
             && Number.isInteger(m.nro) && Array.isArray(m.acciones) && m.acciones.length >= 1 && m.acciones.length <= 20) {
    // Soy el proyector: aplico (lo que no tiene la forma de una acción vuelve como error, sin aplicarse) y respondo
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
  } else if (m.tipo === 'hecho' && m.para === yo && esperando.has(m.nro)) {
    const it = esperando.get(m.nro);
    esperando.delete(m.nro);
    clearTimeout(it.reloj);
    if (typeof m.id === 'string' && ID_VENTANA.test(m.id) && proyectores.has(m.id)) {
      proyectores.set(m.id, { visto: Date.now(), estado: estadoValido(m.estado) });
    }
    it.ok((Array.isArray(m.resultados) ? m.resultados : []).slice(0, 20).map(resultadoValido));
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

function alProyector(lista) {
  return new Promise((ok, mal) => {
    const n = ++nro;
    const reloj = setTimeout(() => {
      esperando.delete(n);
      mal(new Error('La pantalla del proyector no respondió'));
    }, ESPERA_PROYECTOR_MS);
    esperando.set(n, { ok, mal, reloj });
    publicar({ tipo: 'ordenes', de: yo, nro: n, acciones: lista });
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
    anunciar();
  }
  vaciar();
  return () => {
    if (control !== c) return;
    control = null;
    if (c.proyector) {
      clearInterval(latido);
      publicar({ tipo: 'adios', id: yo });
    }
  };
}

/** La vista avisa cada cambio de estado (para el proyector: el latido sale en el acto, así el asistente lo sabe). */
export function avisarEstado() { anunciar(); }

/** La vista no puede mostrar la presentación (no hay sitio en este servidor): lo que esperaba falla con ese motivo. */
export function presentacionNoDisponible(motivo) { rechazarCola(motivo || 'La presentación no está disponible'); }

export const presentacionLista = () => !!control;
export const accionesEnCola = () => cola.length;

/** Dónde está la presentación ({capitulo, paso, total, nombre, titulo, explicacion}) o null si no hay una abierta: la
 * del proyector si hay uno vivo, si no la de esta pestaña. Nunca lanza: va en el contexto de cada mensaje. */
export function estadoPresentacion() {
  try {
    if (proyectorVivo()) {
      const vivos = [...proyectores.values()].sort((a, b) => b.visto - a.visto);
      if (vivos[0]?.estado) return vivos[0].estado;
    }
    return control ? estadoValido(control.estado()) : null;
  } catch {
    return null;
  }
}

/** Aplica `acciones` (las de `accionPresentacion`) y resuelve con un resultado por acción ({op, ok, error?}). Con un
 * proyector vivo van a él (y a la vista de esta pestaña, si está abierta); si no, a la vista, y si no está abierta se
 * navega con `navegar` a /presentacion y se aplican al quedar lista. */
export function accionesPresentacion(acciones, { navegar, espera = ESPERA_MS } = {}) {
  const lista = (Array.isArray(acciones) ? acciones : acciones ? [acciones] : []).slice(0, 20);
  if (proyectorVivo()) {
    if (control) enOrden(lista).catch(() => {});   // la vista de aquí acompaña; lo que vale es lo del proyector
    return alProyector(lista);
  }
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
