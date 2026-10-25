// Ayudante de la prueba T19 (pruebas/movimiento.mjs): corre en un hilo de trabajo (worker_threads) un lote de
// síntesis y devuelve, para cada tarea [Mw, Repi, h], la mediana del PGA de las semillas dadas. El PGA de cada
// simulación es la media geométrica de sus dos componentes horizontales (√(PGAx·PGAy)): así la mediana mide el
// movimiento y no la orientación. test_motor.mjs no lo carga como módulo de pruebas (empieza por «_»).
import { parentPort, workerData } from 'node:worker_threads';
import { leerJSON } from './_util.mjs';
import { sintetizar } from '../../../web/js/sismo/movimiento.js';

const amenaza = leerJSON('data/sismo/amenaza.json');
const { tareas, semillas, vs30 } = workerData;

function mediana(v) {
  const s = [...v].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : 0.5 * (s[n / 2 - 1] + s[n / 2]);
}

const medianas = tareas.map(([Mw, Repi, h]) => mediana(semillas.map((semilla) => {
  const r = sintetizar({ Mw, profundidad_km: h, distancia_epicentral_km: Repi, vs30_m_s: vs30, semilla }, amenaza);
  return Math.sqrt(r.intensidades.x.pga_g * r.intensidades.y.pga_g);
})));
parentPort.postMessage(medianas);
