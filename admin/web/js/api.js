// Cliente de la API: cookie de sesión HttpOnly + cabecera CSRF en todo lo que cambia datos.
import { url } from './base.js';

let csrf = null;
let alExpirar = () => {};

export const sesion = { usuario: null };
export function configurar({ token, usuario, expira }) {
  csrf = token;
  sesion.usuario = usuario;
  if (expira) alExpirar = expira;
}

export class ErrorApi extends Error {
  constructor(estado, detalle) {
    const msg = typeof detalle === 'string' ? detalle : detalle?.mensaje || 'Error inesperado';
    super(msg);
    this.estado = estado;
    this.detalle = detalle;
  }
}

async function pedir(metodo, ruta, cuerpo, { formulario = false } = {}) {
  const op = { method: metodo, credentials: 'same-origin', headers: {} };
  if (metodo !== 'GET') op.headers['X-CSRF-Token'] = csrf || '';
  if (cuerpo !== undefined) {
    if (formulario) op.body = cuerpo;
    else {
      op.headers['Content-Type'] = 'application/json';
      op.body = JSON.stringify(cuerpo);
    }
  }
  const r = await fetch(url(ruta), op);
  if (r.status === 401 && ruta !== '/api/login' && ruta !== '/api/yo') {
    alExpirar();
    throw new ErrorApi(401, 'La sesión terminó');
  }
  const tipo = r.headers.get('content-type') || '';
  const datos = tipo.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new ErrorApi(r.status, datos?.detail ?? datos);
  return datos;
}

export const api = {
  get: (ruta, params) => {
    const q = params ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')) : '';
    return pedir('GET', ruta + q);
  },
  post: (ruta, cuerpo) => pedir('POST', ruta, cuerpo ?? {}),
  patch: (ruta, cuerpo) => pedir('PATCH', ruta, cuerpo),
  put: (ruta, cuerpo) => pedir('PUT', ruta, cuerpo),
  del: (ruta) => pedir('DELETE', ruta),
  subir: (ruta, formData) => pedir('POST', ruta, formData, { formulario: true }),
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
