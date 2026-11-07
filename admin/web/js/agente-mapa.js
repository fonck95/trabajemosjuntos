// Puente entre el asistente y la vista del mapa. Las acciones se aplican en orden; mientras el mapa no está montado y
// listo esperan en una cola (con tiempo límite) y, si hace falta, se navega a /mapa. La vista se registra al terminar
// de cargar (capas, zonas y puntos) y se quita al salir.
import { sinBase } from './base.js';

const ESPERA_MS = 30000;
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

/** La vista del mapa se registra al estar lista; devuelve la función que la quita (al salir de la vista). */
export function registrarMapa(c) {
  control = c;
  vaciar();
  return () => { if (control === c) control = null; };
}

export const mapaListo = () => !!control;
export const accionesEnCola = () => cola.length;
export const estadoMapa = () => (control ? control.estado() : null);

/** Aplica `acciones` ([{tipo, …}]) al mapa y resuelve con un resultado por acción. Si el mapa no está abierto navega
 * con `navegar` a /mapa (con los filtros de la primera acción «filtros» en la URL: la primera carga ya los trae). */
export function accionesMapa(acciones, { navegar, espera = ESPERA_MS } = {}) {
  const lista = [].concat(acciones || []);
  if (control) return enOrden(lista);
  return new Promise((ok, mal) => {
    const it = { acciones: lista, ok, mal };
    it.reloj = setTimeout(() => {
      const i = cola.indexOf(it);
      if (i >= 0) cola.splice(i, 1);
      mal(new Error('El mapa no terminó de cargar'));
    }, espera);
    cola.push(it);
    if (!enMapa() && navegar) {
      const f = lista.find((a) => a?.tipo === 'filtros')?.valores || {};
      const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v != null && v !== '')).toString();
      navegar('/mapa' + (qs ? `?${qs}` : ''));
    }
  });
}
