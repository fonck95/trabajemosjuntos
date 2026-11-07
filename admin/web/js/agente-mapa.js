// Puente entre el asistente y la vista del mapa. Las acciones se aplican en orden; mientras el mapa no está montado y
// listo esperan en una cola (con tiempo límite) y, si hace falta, se navega a /mapa. La vista se registra al terminar
// de cargar (capas, zonas y puntos) y se quita al salir.
// Solo importa base.js y `navegar` (el `ir` de app.js) llega por parámetro: así no depende de app.js, que es quien carga
// al asistente, y se puede probar sin navegador.
import { sinBase } from './base.js';

const ESPERA_MS = 30000;
const ESPERA_MAX_MS = 120000;
// Los filtros que viajan en la URL al abrir el mapa (así su primera carga ya los trae). Nunca `area_id` ni `poligono`:
// en la URL del mapa abren una zona sin pasar por la acción `zona`. Tampoco `ids` ni `mios`, que no son del mapa
const FUERA_DE_URL = new Set(['area_id', 'poligono', 'ids', 'ids_total', 'mios']);
const cola = [];
let control = null;
let cadena = Promise.resolve();

const enMapa = () => (sinBase(location.pathname).replace(/\/+$/, '') || '/') === '/mapa';

function enOrden(lista) {
  const p = cadena.then(() => {
    if (!control) throw new Error('El mapa se cerró antes de aplicar las acciones');
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

// Si la persona abre otra vista mientras el mapa carga (o el mapa no se pudo abrir), lo que esperaba en la cola ya no
// se aplicará: se responde en el acto en lugar de agotar el plazo. app.js anuncia cada vista pintada con el evento
// `vista`; sin él, todo sigue igual y vence el plazo
window.addEventListener('vista', (e) => {
  if (!cola.length || control) return;
  const { ruta, ok } = e?.detail || {};
  if (typeof ruta !== 'string') return;
  if (ruta === '/mapa' && ok === false) rechazarCola('El mapa no se pudo abrir');
  else if (ruta !== '/mapa' && !enMapa()) rechazarCola('Se abrió otra vista antes de que el mapa terminara de cargar');
});

// «?zona=rural&sexo=F» con los valores de la primera acción `filtros`, o «» si no hay o si alguno no es un valor
// sencillo (entonces la acción se aplica entera al cargar el mapa, o falla entera: nunca a medias)
function consulta(lista) {
  const v = lista.find((a) => a && typeof a === 'object' && a.tipo === 'filtros')?.valores;
  if (!v || typeof v !== 'object' || Array.isArray(v)) return '';
  const pares = [];
  for (const [k, x] of Object.entries(v)) {
    if (x === null || x === undefined || x === '') continue;
    const s = typeof x === 'boolean' ? (x ? '1' : '0') : typeof x === 'number' && Number.isFinite(x) ? String(x)
      : typeof x === 'string' ? x.trim() : null;
    if (!/^[a-z_]{1,40}$/.test(k) || FUERA_DE_URL.has(k) || !s || s.length > 120 || /[\u0000-\u001f\u007f]/.test(s)) return '';
    pares.push([k, s]);
  }
  const qs = new URLSearchParams(pares).toString();
  return qs ? `?${qs}` : '';
}

/** La vista del mapa se registra al estar lista; devuelve la función que la quita (al salir de la vista). */
export function registrarMapa(c) {
  if (!c || typeof c.aplicar !== 'function' || typeof c.estado !== 'function') return () => {};
  control = c;
  vaciar();
  return () => { if (control === c) control = null; };
}

export const mapaListo = () => !!control;
export const accionesEnCola = () => cola.length;
/** Instantánea del mapa abierto (cámara, base, capas, filtros, cifras) o null si no hay mapa listo. Nunca lanza: va en
 * el contexto de cada mensaje del asistente. */
export const estadoMapa = () => {
  if (!control) return null;
  try { return control.estado(); } catch { return null; }
};

/** Aplica `acciones` ([{tipo, …}]) al mapa y resuelve con un resultado por acción. Si el mapa no está abierto navega
 * con `navegar` a /mapa (con los filtros de la primera acción «filtros» en la URL: la primera carga ya los trae). */
export function accionesMapa(acciones, { navegar, espera = ESPERA_MS } = {}) {
  const lista = Array.isArray(acciones) ? acciones.slice() : acciones ? [acciones] : [];
  if (control) return enOrden(lista);
  const plazo = typeof espera === 'number' && espera > 0 ? Math.min(espera, ESPERA_MAX_MS) : ESPERA_MS;
  return new Promise((ok, mal) => {
    const it = { acciones: lista, ok, mal };
    it.reloj = setTimeout(() => {
      const i = cola.indexOf(it);
      if (i >= 0) cola.splice(i, 1);
      mal(new Error('El mapa no terminó de cargar'));
    }, plazo);
    cola.push(it);
    // Ya en /mapa (cargando) solo se espera: volver a navegar destruiría el mapa a medio cargar y empezaría de nuevo
    if (!enMapa() && typeof navegar === 'function') navegar('/mapa' + consulta(lista));
  });
}
