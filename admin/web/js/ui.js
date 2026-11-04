// Utilidades de interfaz: plantillas con escape, formato, avisos, diálogos e íconos.
import { CANALES_AUTORIZACION, ESTADOS_AUTORIZACION, autorizacionDe, textoAbordaje } from './modelo.js';

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);

class Crudo { constructor(s) { this.s = s; } toString() { return this.s; } }
/** Marca un texto como HTML de confianza (solo para fragmentos que arma el propio código). */
export const crudo = (s) => new Crudo(s);

/** Plantilla que escapa todo lo interpolado salvo fragmentos `crudo` o listas de ellos. */
export function html(partes, ...vals) {
  let s = partes[0];
  vals.forEach((v, i) => {
    if (Array.isArray(v)) s += v.map((x) => (x instanceof Crudo ? x.s : esc(x))).join('');
    else s += v instanceof Crudo ? v.s : esc(v);
    s += partes[i + 1];
  });
  return new Crudo(s);
}

export const $ = (sel, raiz = document) => raiz.querySelector(sel);
export const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

export function montar(el, contenido) {
  el.innerHTML = String(contenido);
  return el;
}

const NUM = new Intl.NumberFormat('es-CO');
export const num = (n) => (n == null ? '—' : NUM.format(n));
export const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
export function fecha(iso, conHora = false) {
  if (!iso) return '—';
  const d = new Date(iso.length <= 10 ? iso + 'T12:00:00' : iso);
  if (Number.isNaN(d.getTime())) return iso;
  let s = `${d.getDate()} ${MESES[d.getMonth()]} ${d.getFullYear()}`;
  if (conHora) s += ` · ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  return s;
}
export const mesCorto = (ym) => { const [a, m] = ym.split('-'); return `${MESES[+m - 1]} ${a.slice(2)}`; };
export const titulo = (s) => (s || '').toLowerCase().replace(/(^|\s)(\S)/g, (m, a, b) => a + b.toUpperCase())
  .replace(/\b(De|Del|La|Las|Los|Y|El|En)\b/g, (m, w, i) => (i ? m.toLowerCase() : m));
export const iniciales = (n) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('');
export const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

/** Retrasa `fn` hasta que dejen de llamarla; `.cancel()` descarta la llamada pendiente (al salir de una vista). */
export function debounce(fn, ms = 250) {
  let t;
  const f = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  f.cancel = () => clearTimeout(t);
  return f;
}

export function aviso(msg, tipo = 'ok', ms = 3600) {
  // Con un diálogo abierto el aviso va dentro de él: fuera quedaría debajo del fondo del modal
  const caja = [...document.querySelectorAll('dialog[open] > .avisos')].pop() || document.getElementById('avisos');
  const el = document.createElement('div');
  el.className = 'aviso' + (tipo === 'error' ? ' error' : '');
  el.textContent = msg;
  caja.append(el);
  setTimeout(() => el.remove(), ms);
}

/** Muestra el error de una acción (el 401 ya lo avisa api.js al cerrar la sesión). */
export function avisoError(err, ms = 6000) {
  if (err?.estado === 401) return;
  aviso(err?.message || 'Error inesperado', 'error', ms);
}

/** Diálogo modal. `cuerpo` es HTML (crudo); devuelve {el, cerrar, listo} donde `listo` resuelve al cerrar. */
export function dialogo({ titulo: t, cuerpo, pie = '', ancho = false, alAbrir }) {
  const d = document.createElement('dialog');
  if (ancho) d.classList.add('ancho');
  d.innerHTML = String(html`<div class="cab"><h2>${t}</h2><button class="btn fantasma chico" data-cerrar aria-label="Cerrar">✕</button></div>
    <div class="cuerpo">${cuerpo}</div>${pie ? html`<div class="pie">${pie}</div>` : ''}<div class="avisos" role="status" aria-live="polite"></div>`);
  document.body.append(d);
  let resolver;
  const listo = new Promise((r) => (resolver = r));
  const cerrar = (v) => { d.close(); d.remove(); resolver(v); };
  d.addEventListener('click', (e) => {
    if (e.target === d || e.target.closest('[data-cerrar]')) cerrar(null);
  });
  d.addEventListener('cancel', (e) => { e.preventDefault(); cerrar(null); });
  d.showModal();
  alAbrir?.(d, cerrar);
  return { el: d, cerrar, listo };
}

export function confirmar(texto, { si = 'Confirmar', peligro = false } = {}) {
  const { el, cerrar, listo } = dialogo({
    titulo: 'Confirmar',
    cuerpo: html`<p>${texto}</p>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn ${peligro ? 'primario' : 'oscuro'}" data-si>${si}</button>`,
  });
  el.querySelector('[data-si]').addEventListener('click', () => cerrar(true));
  return listo.then((v) => v === true);
}

export function datosForm(form) {
  const d = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.type === 'number') d[el.name] = el.value === '' ? null : Number(el.value);
    else d[el.name] = el.value.trim() === '' ? null : el.value.trim();
  }
  return d;
}

const P = {
  panel: '<path d="M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z"/>',
  mapa: '<path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2-6-2zm0 0v14m6-12v14" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  personas: '<path d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm-8 0a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm0 2c-2.7 0-6 1.3-6 3.5V19h7v-2.5c0-1 .4-2 1.2-2.8A9 9 0 0 0 8 13zm8 0c-3 0-7 1.5-7 4v2h14v-2c0-2.5-4-4-7-4z"/>',
  reuniones: '<path d="M7 2v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2zm-2 8h14v10H5zm2 2v2h2v-2zm4 0v2h2v-2zm4 0v2h2v-2z"/>',
  calidad: '<path d="m12 2 8 3v6c0 5-3.4 9.4-8 11-4.6-1.6-8-6-8-11V5zm-1.2 13.4 6-6-1.4-1.4-4.6 4.6-2.2-2.2L7.2 11.8z"/>',
  importar: '<path d="M12 3v11m0 0-4-4m4 4 4-4M4 17v3h16v-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  ajustes: '<path d="M19.4 13a7.5 7.5 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.6 7.6 0 0 0-1.7-1L15 3h-4l-.4 2.9a7.6 7.6 0 0 0-1.7 1l-2.5-1-2 3.5L6.6 11a7.5 7.5 0 0 0 0 2l-2.1 1.6 2 3.5 2.5-1a7.6 7.6 0 0 0 1.7 1L11 21h4l.4-2.9a7.6 7.6 0 0 0 1.7-1l2.5 1 2-3.5zM13 15.5A3.5 3.5 0 1 1 16.5 12 3.5 3.5 0 0 1 13 15.5z"/>',
  buscar: '<path d="m21 21-4.3-4.3M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  mas: '<path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  salir: '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  luna: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  descargar: '<path d="M12 4v11m0 0-4-4m4 4 4-4M4 19h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  pin: '<path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 14.5 9 2.5 2.5 0 0 1 12 11.5z"/>',
  trabajo: '<path d="M4 7h16v12H4zm5 0V4h6v3M4 12h16" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  usuarios: '<path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-7 10a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7.5M18 14a6 6 0 0 1 4 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  cuenta: '<path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9zm-8 9a8 8 0 0 1 16 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  zona: '<path d="m5 7 8-4 8 7-4 10-12-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="5" cy="7" r="2"/><circle cx="13" cy="3" r="2"/><circle cx="21" cy="10" r="2"/><circle cx="17" cy="20" r="2"/><circle cx="5" cy="17" r="2"/>',
  telefono: '<path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.6 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1 11.4 11.4 0 0 0 .6 3.6 1 1 0 0 1-.25 1z"/>',
  acercamiento: '<path d="M4 4h16v12H9l-5 4zm4 5h8m-8 3h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  whatsapp: '<path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.6-1.2A9 9 0 1 0 12 3zm4.4 12.4c-.2.5-1.1 1-1.6 1-.4.1-1 .1-1.6-.1a10 10 0 0 1-1.4-.5 11 11 0 0 1-4.3-3.8c-.5-.7-.9-1.5-.9-2.4 0-.9.5-1.4.7-1.6.2-.2.4-.3.6-.3h.4c.1 0 .3 0 .5.4l.7 1.6c.1.1.1.3 0 .4l-.3.5-.3.3c-.1.1-.2.3-.1.5.1.2.6 1 1.3 1.6.9.8 1.6 1 1.9 1.2.2.1.4.1.5-.1l.7-.8c.2-.2.3-.2.5-.1l1.5.7c.2.1.4.2.4.3.1.1.1.6-.2 1.2z"/>',
  gps: '<circle cx="12" cy="12" r="3.5"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M12 5.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  puntos: '<circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/>',
  siguiente: '<path d="M5 12h13m-5-6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  hogar: '<path d="m3 11 9-7 9 7M5 9.5V20h5v-6h4v6h5V9.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  completar: '<path d="M4 20h4L19 9l-4-4L4 16zm9-13 4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  filtro: '<path d="M3 5h18l-7 8v6l-4 2v-8z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
};
// Los íconos salen de la tabla P (texto fijo de este archivo): por eso se marcan como HTML sin pasar por `crudo`
export const icono = (n) => new Crudo(`<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${P[n] || ''}</svg>`);

/** ¿Pantalla de celular? (la misma frontera de 900 px de app.css) */
export const esMovil = () => matchMedia('(max-width: 900px)').matches;
const NOMBRES_PRECISION = {
  direccion: 'Dirección exacta', manual: 'Puesta a mano', direccion_aprox: 'Dirección aproximada', barrio: 'Barrio', sector: 'Sector',
  caserio: 'Caserío', centro_poblado: 'Centro poblado', vereda: 'Vereda', corregimiento: 'Corregimiento', sin: 'Sin ubicar',
};
export const precisionNombre = (p) => NOMBRES_PRECISION[p || 'sin'] || p;
export const chipPrecision = (p) => {
  const clase = p === 'direccion' || p === 'manual' ? 'verde' : p ? 'azul' : 'ambar';
  return html`<span class="chip ${clase}">${precisionNombre(p)}</span>`;
};
export const FUENTES = {
  tramites: 'Trámites', cedulas: 'Base con cédula', reunion: 'Reunión', manual: 'Registro manual',
  planilla: 'Planilla de campo', consultor: 'Consultor', otra_base: 'Otra base', panel: 'Panel',
};

/** Chip de abordaje de una fila o ficha (4.6). */
export const chipAbordaje = (ab) => {
  const { clase, texto } = textoAbordaje(ab);
  return html`<span class="chip ${clase}">${texto}</span>`;
};

/** Chip de autorización, con los canales si autorizó. */
export const chipAutorizacion = (p, { conCanales = true } = {}) => {
  const a = autorizacionDe(p);
  const clase = a.estado === 'si' ? 'verde' : a.estado === 'no' || a.estado === 'revocada' ? 'rojo' : 'ambar';
  const canales = conCanales && a.estado === 'si' && a.canales?.length
    ? ' · ' + a.canales.map((c) => CANALES_AUTORIZACION[c] || c).join(', ') : '';
  const sinHabilitar = a.estado === 'si' && a.habilitado === false ? ' (por confirmar)' : '';
  return html`<span class="chip ${clase}" title="Autorización de tratamiento de datos">${ESTADOS_AUTORIZACION[a.estado] || a.estado}${canales}${sinHabilitar}</span>`;
};
