// Cliente de la API: cookie de sesión HttpOnly + cabecera CSRF en todo lo que cambia datos.
import { url } from './base.js';

let csrf = null;
let alExpirar = () => {};

// uid 0 y permiso «*» son del administrador. Sin `rol` (un servidor anterior a los usuarios) la sesión es la suya
export const sesion = { usuario: null, uid: null, rol: null, permisos: [], nombre: null };
export function configurar({ token, usuario, expira, uid, rol, permisos, nombre }) {
  csrf = token;
  sesion.usuario = usuario;
  sesion.rol = rol || 'admin';
  sesion.uid = uid ?? (rol ? null : 0);
  sesion.permisos = Array.isArray(permisos) ? permisos : (rol ? [] : ['*']);
  sesion.nombre = nombre ?? usuario ?? null;
  if (expira) alExpirar = expira;
}

/** ¿La sesión tiene el permiso? La interfaz solo oculta: el servidor decide. */
export const puede = (permiso) => sesion.permisos.includes('*') || sesion.permisos.includes(permiso);

export const SIN_CONEXION = 'Sin conexión. Lo escrito sigue aquí; intente de nuevo';

export class ErrorApi extends Error {
  constructor(estado, detalle) {
    const msg = typeof detalle === 'string' ? detalle : detalle?.mensaje || 'Error inesperado';
    super(msg);
    this.estado = estado;
    this.detalle = detalle;
  }
}

// Opciones de cada petición: `clave` va como Idempotency-Key (el formulario la genera al abrirse y la reusa en cada
// reintento) y `timeout` (ms) corta la espera con «Sin conexión» sin perder lo escrito. Sin timeout se espera como antes.
async function pedir(metodo, ruta, cuerpo, { formulario = false, clave = null, timeout = 0 } = {}) {
  const op = { method: metodo, credentials: 'same-origin', headers: {} };
  if (metodo !== 'GET') op.headers['X-CSRF-Token'] = csrf || '';
  if (clave) op.headers['Idempotency-Key'] = clave;
  if (cuerpo !== undefined) {
    if (formulario) op.body = cuerpo;
    else {
      op.headers['Content-Type'] = 'application/json';
      op.body = JSON.stringify(cuerpo);
    }
  }
  let reloj = null;
  if (timeout > 0) {
    const control = new AbortController();
    op.signal = control.signal;
    reloj = setTimeout(() => control.abort(), timeout);
  }
  try {
    const r = await fetch(url(ruta), op);
    if (r.status === 401 && ruta !== '/api/login' && ruta !== '/api/yo') {
      alExpirar();
      throw new ErrorApi(401, 'La sesión terminó');
    }
    const tipo = r.headers.get('content-type') || '';
    const datos = tipo.includes('json') ? await r.json() : await r.text();
    if (!r.ok) throw new ErrorApi(r.status, datos?.detail ?? datos);
    return datos;
  } catch (e) {
    if (e?.name === 'AbortError') throw new ErrorApi(0, SIN_CONEXION);
    throw e;
  } finally {
    if (reloj) clearTimeout(reloj);
  }
}

export const api = {
  get: (ruta, params, op) => {
    const q = params ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')) : '';
    return pedir('GET', ruta + q, undefined, op);
  },
  post: (ruta, cuerpo, op) => pedir('POST', ruta, cuerpo ?? {}, op),
  patch: (ruta, cuerpo, op) => pedir('PATCH', ruta, cuerpo, op),
  put: (ruta, cuerpo, op) => pedir('PUT', ruta, cuerpo, op),
  del: (ruta, op) => pedir('DELETE', ruta, undefined, op),
  subir: (ruta, formData, op) => pedir('POST', ruta, formData, { ...op, formulario: true }),
};

/** Descarga un archivo de la API (exportaciones) respetando la sesión. */
export async function descargar(ruta, params) {
  const q = params ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')) : '';
  const r = await fetch(url(ruta) + q, { credentials: 'same-origin' });
  if (!r.ok) throw new ErrorApi(r.status, 'No se pudo descargar');
  const nombre = /filename="([^"]+)"/.exec(r.headers.get('content-disposition') || '')?.[1] || 'descarga';
  const enlace = URL.createObjectURL(await r.blob());
  const a = Object.assign(document.createElement('a'), { href: enlace, download: nombre });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(enlace), 2000);
}
