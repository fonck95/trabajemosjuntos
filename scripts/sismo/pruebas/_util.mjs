// Ayudantes de las pruebas del motor sísmico (no es un módulo de pruebas: test_motor.mjs salta los «_*.mjs»).
import { readFileSync } from 'node:fs';

/** URL de la raíz del repositorio (termina en «/»). */
export const RAIZ = new URL('../../../', import.meta.url);

/** Lee un JSON por su ruta desde la raíz del repositorio. */
export function leerJSON(ruta) {
  return JSON.parse(readFileSync(new URL(ruta, RAIZ), 'utf8'));
}

/** |a − b| / |b| (o |a − b| si b = 0). */
export function errorRelativo(a, b) {
  return b === 0 ? Math.abs(a - b) : Math.abs(a - b) / Math.abs(b);
}

/** Máximo de |a_i − b_i| / max(|b|) sobre dos listas del mismo largo. */
export function errorMaximo(a, b) {
  if (a.length !== b.length) throw new Error(`largos distintos: ${a.length} y ${b.length}`);
  let m = 0, ref = 0;
  for (let i = 0; i < a.length; i++) { m = Math.max(m, Math.abs(a[i] - b[i])); ref = Math.max(ref, Math.abs(b[i])); }
  return ref === 0 ? m : m / ref;
}

/** Un caso con su error y su tolerancia (lo que imprime test_motor.mjs). */
export function caso(nombre, error, tolerancia, detalle) {
  return { caso: nombre, error, tolerancia, ok: error <= tolerancia, detalle };
}

/** Caso de sí o no. */
export function comprobar(nombre, ok, detalle) {
  return { caso: nombre, ok: !!ok, detalle };
}
