// Lo que pedimos: cierre con todas las propuestas a la vista y los pines de los módulos, desde el norte, con el río
// y el puente de fondo.
import { pinesDe } from './comun.js';

export function crear(esc, datos) {
  const pts = pinesDe(datos).map(({ x, y }) => [x, y]);
  return {
    completo: [],
    pasos: { '*': { todos: true, capas: ['portada.pines'], vista: () => esc.encuadrar(pts, { rumbo: 20, elev: 40, margen: 0.94, duracion: 2.4 }) } },
  };
}
