// Cliente de la API: cookie de sesión HttpOnly + cabecera CSRF en todo lo que cambia datos, tiempo límite,
// Idempotency-Key, reingreso sin perder lo escrito y catálogos en memoria con ETag (7.0).
import { url } from './base.js';

let csrf = null;
let alExpirar = () => {};
let alReingresar = null;   // abre el ingreso en un diálogo y resuelve con los datos de la sesión nueva
let alPendiente = () => {}; // 403 cambiar_clave o compromiso: la cuenta tiene algo pendiente

// uid 0 y permiso «*» son del administrador. Sin `rol` (un servidor anterior a los usuarios) la sesión es la suya
export const sesion = { usuario: null, uid: null, rol: null, permisos: [], nombre: null, debeCambiarClave: false,
  compromisoPendiente: false };
export function configurar({ token, usuario, expira, uid, rol, permisos, nombre, debe_cambiar_clave, compromiso_pendiente,
  reingresar, pendiente }) {
  csrf = token;
  sesion.usuario = usuario;
  sesion.rol = rol || 'admin';
  sesion.uid = uid ?? (rol ? null : 0);
  sesion.permisos = Array.isArray(permisos) ? permisos : (rol ? [] : ['*']);
  sesion.nombre = nombre ?? usuario ?? null;
  sesion.debeCambiarClave = !!debe_cambiar_clave;
  sesion.compromisoPendiente = !!compromiso_pendiente;
  if (expira) alExpirar = expira;
  if (reingresar) alReingresar = reingresar;
  if (pendiente) alPendiente = pendiente;
}

/** ¿La sesión tiene el permiso? La interfaz solo oculta: el servidor decide. */
export const puede = (permiso) => sesion.permisos.includes('*') || sesion.permisos.includes(permiso);

export const SIN_CONEXION = 'Sin conexión. Lo escrito sigue aquí; intente de nuevo';
// Tiempo límite: 15 s en lecturas y 30 s en escrituras. Lo que tarda por naturaleza (subir Excel, recalcular todas
// las ubicaciones, exportar) espera sin límite, como antes
const ESPERA_LECTURA = 15000;
const ESPERA_ESCRITURA = 30000;
const SIN_LIMITE = ['/api/importar', '/api/georreferenciar', '/api/exportar.xlsx'];

export class ErrorApi extends Error {
  constructor(estado, detalle) {
    const msg = typeof detalle === 'string' ? detalle : detalle?.mensaje || 'Error inesperado';
    super(msg);
    this.estado = estado;
    this.detalle = detalle;
    this.codigo = typeof detalle === 'object' && detalle ? detalle.codigo || null : null;
  }
}

/** Clave nueva para Idempotency-Key: el formulario la genera al abrirse y la reusa en cada reintento. */
export function nuevaClave() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  return [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
}

// Formularios con cambios sin guardar: con uno abierto, un 401 abre el ingreso en un diálogo en vez de recargar
const pendientes = new Set();
/** Registra una función que dice si hay algo escrito sin guardar; devuelve la que la quita (al cerrar el formulario). */
export function registrarPendiente(fn) {
  pendientes.add(fn);
  return () => pendientes.delete(fn);
}
const hayPendientes = () => [...pendientes].some((fn) => { try { return !!fn(); } catch { return false; } });

let reingreso = null; // un solo diálogo aunque fallen varias peticiones a la vez
function reingresar() {
  if (!alReingresar) return Promise.reject(new ErrorApi(401, 'La sesión terminó'));
  reingreso ||= Promise.resolve(alReingresar()).finally(() => { reingreso = null; });
  return reingreso;
}

const NO_CAMBIO = Symbol('304');

// Opciones de cada petición: `clave` va como Idempotency-Key y `timeout` (ms) corta la espera con «Sin conexión» sin
// perder lo escrito (0: sin límite). `cabeceras` se suman a las de siempre; `alResponder(r)` recibe la respuesta
async function pedir(metodo, ruta, cuerpo, op = {}, reintento = false) {
  const { formulario = false, clave = null, cabeceras = null, alResponder = null } = op;
  const sinLimite = SIN_LIMITE.some((r) => ruta === r || ruta.startsWith(r + '?'));
  const timeout = op.timeout ?? (sinLimite ? 0 : metodo === 'GET' ? ESPERA_LECTURA : ESPERA_ESCRITURA);
  const o = { method: metodo, credentials: 'same-origin', headers: { ...(cabeceras || {}) } };
  if (metodo !== 'GET') o.headers['X-CSRF-Token'] = csrf || '';
  if (clave) o.headers['Idempotency-Key'] = clave;
  if (cuerpo !== undefined) {
    if (formulario) o.body = cuerpo;
    else {
      o.headers['Content-Type'] = 'application/json';
      o.body = JSON.stringify(cuerpo);
    }
  }
  let reloj = null;
  if (timeout > 0) {
    const control = new AbortController();
    o.signal = control.signal;
    reloj = setTimeout(() => control.abort(), timeout);
  }
  let r;
  try {
    r = await fetch(url(ruta), o);
  } catch (e) {
    // Sin señal o tiempo agotado: el formulario sigue abierto con lo escrito
    throw new ErrorApi(0, SIN_CONEXION);
  } finally {
    if (reloj) clearTimeout(reloj);
  }
  // /api/yo sin sesión configurada es la pregunta del arranque («¿hay sesión?»), no una sesión que terminó
  if (r.status === 401 && ruta !== '/api/login' && !(ruta === '/api/yo' && !csrf)) {
    // Con algo escrito (o enviándolo), se ingresa de nuevo en un diálogo y se reintenta; si no, se recarga como antes
    if (!reintento && (metodo !== 'GET' || hayPendientes()) && alReingresar) {
      try { await reingresar(); } catch { throw new ErrorApi(401, 'La sesión terminó'); }
      return pedir(metodo, ruta, cuerpo, op, true);
    }
    alExpirar();
    throw new ErrorApi(401, 'La sesión terminó');
  }
  alResponder?.(r);
  if (r.status === 304) return NO_CAMBIO;
  const tipo = r.headers.get('content-type') || '';
  let datos;
  try {
    datos = tipo.includes('json') ? await r.json() : await r.text();
  } catch {
    throw new ErrorApi(0, SIN_CONEXION);
  }
  if (!r.ok) {
    const e = new ErrorApi(r.status, datos?.detail ?? datos);
    if (r.status === 403 && (e.codigo === 'cambiar_clave' || e.codigo === 'compromiso')) alPendiente(e.codigo);
    throw e;
  }
  return datos;
}

const conParams = (ruta, params) => (params
  ? ruta + '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== ''))
  : ruta);

// Catálogos de la sesión, revalidados con If-None-Match: el servidor responde 304 si no cambiaron
let catalogosGuardados = null;
let catalogosEnCurso = null;
async function catalogos({ forzar = false } = {}) {
  if (!catalogosEnCurso) {
    const previo = forzar ? null : catalogosGuardados;
    catalogosEnCurso = (async () => {
      let etiqueta = null;
      const op = { alResponder: (r) => { etiqueta = r.headers.get('etag'); } };
      if (previo) op.cabeceras = { 'If-None-Match': previo.etiqueta };
      let datos = await pedir('GET', '/api/catalogos', undefined, op);
      if (datos === NO_CAMBIO && previo) return previo.datos;
      if (datos === NO_CAMBIO) datos = await pedir('GET', '/api/catalogos', undefined, { alResponder: op.alResponder });
      catalogosGuardados = etiqueta ? { etiqueta, datos } : null;
      return datos;
    })().finally(() => { catalogosEnCurso = null; });
  }
  // Cada vista recibe su copia: lo que cambie no toca lo guardado
  return structuredClone(await catalogosEnCurso);
}
/** Olvida los catálogos guardados (al cerrar sesión). */
export function olvidarCatalogos() { catalogosGuardados = null; }

export const api = {
  get: (ruta, params, op) => {
    // Los catálogos sin parámetros salen de la memoria de la sesión (con revalidación)
    if (ruta === '/api/catalogos' && !params && !op) return catalogos();
    return pedir('GET', conParams(ruta, params), undefined, op);
  },
  post: (ruta, cuerpo, op) => pedir('POST', ruta, cuerpo ?? {}, op),
  patch: (ruta, cuerpo, op) => pedir('PATCH', ruta, cuerpo, op),
  put: (ruta, cuerpo, op) => pedir('PUT', ruta, cuerpo, op),
  del: (ruta, op) => pedir('DELETE', ruta, undefined, op),
  subir: (ruta, formData, op) => pedir('POST', ruta, formData, { timeout: 0, ...op, formulario: true }),
  catalogos,
};

/** Descarga un archivo de la API (exportaciones) respetando la sesión. */
export async function descargar(ruta, params) {
  const r = await fetch(url(conParams(ruta, params)), { credentials: 'same-origin' });
  if (!r.ok) {
    let detalle = 'No se pudo descargar';
    try { detalle = (await r.json()).detail || detalle; } catch { /* no era JSON */ }
    throw new ErrorApi(r.status, detalle);
  }
  const nombre = /filename="([^"]+)"/.exec(r.headers.get('content-disposition') || '')?.[1] || 'descarga';
  const enlace = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement('a'), { href: enlace, download: nombre });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(enlace), 2000);
}

// ───────── Borrador del formulario abierto (decisión 10.1.2) ─────────
// Solo el único formulario abierto, en sessionStorage (nunca en localStorage); se borra al guardar, al cancelar, al
// cerrar sesión o pasadas 2 h. Con BORRADOR_ACTIVO en false no queda nada en el dispositivo.
export const BORRADOR_ACTIVO = true;
const BORRADOR = 'yj_borrador';
const BORRADOR_MS = 2 * 3600 * 1000;

/** Guarda el borrador del formulario `clave` (reemplaza el de cualquier otro formulario). */
export function guardarBorrador(clave, datos) {
  if (!BORRADOR_ACTIVO) return;
  try { sessionStorage.setItem(BORRADOR, JSON.stringify({ clave, datos, t: Date.now(), uid: sesion.uid })); } catch { /* lleno o bloqueado */ }
}
/** El borrador del formulario `clave`, si es de esta sesión y tiene menos de 2 h; si no, null. */
export function leerBorrador(clave) {
  try {
    const b = JSON.parse(sessionStorage.getItem(BORRADOR) || 'null');
    if (!b || Date.now() - b.t > BORRADOR_MS || b.uid !== sesion.uid) { borrarBorrador(); return null; }
    return b.clave === clave ? b.datos : null;
  } catch { return null; }
}
/** Borra el borrador (de ese formulario, o cualquiera sin `clave`). */
export function borrarBorrador(clave) {
  try {
    const b = JSON.parse(sessionStorage.getItem(BORRADOR) || 'null');
    if (!clave || !b || b.clave === clave) sessionStorage.removeItem(BORRADOR);
  } catch { /* nada */ }
}
