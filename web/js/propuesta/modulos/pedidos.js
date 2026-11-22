// Lo que pedimos: cierre con todas las propuestas a la vista y los pines de los módulos, desde el norte, con el río
// y el puente de fondo.
import { pinesDe } from './comun.js';

export function crear(esc, datos) {
  const pts = pinesDe(datos).map(({ x, y }) => [x, y]);
  // desde el norte, los pines del casco (y del acueducto) quedan al fondo, arriba del cuadro: sin aire encima no tenían
  // dónde correrse y se encimaban. Un punto a 1.800 m sobre su centro los baja en la pantalla
  const casco = pts.filter(([, y]) => y < 1000);
  const aire = casco.length ? [[casco.reduce((a, p) => a + p[0], 0) / casco.length, casco.reduce((a, p) => a + p[1], 0) / casco.length, 1800]] : [];
  return {
    completo: [],
    pasos: { '*': { todos: true, capas: ['portada.pines'], vista: () => esc.encuadrar([...pts, ...aire], { rumbo: 20, elev: 40, margen: 0.94, duracion: 2.4 }) } },
  };
}
