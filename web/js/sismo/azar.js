// Números aleatorios con semilla para la síntesis del movimiento del suelo (contrato de integración, 7.4).
// Módulo puro: sin DOM ni three. Misma semilla → misma secuencia, en cualquier equipo con el mismo motor de
// JavaScript (las operaciones enteras son exactas; Math.log, Math.cos y Math.sin son las de la plataforma).
//
// - mulberry32 (Tommy Ettinger, 2017; dominio público): generador de 32 bits con período 2³². Devuelve
//   uniformes en [0, 1) con 2⁻³² de resolución. Es más que suficiente para unas decenas de miles de
//   muestras por acelerograma y es fácil de replicar bit a bit en Python (scripts/sismo/estocastico.py).
// - Box y Muller (1958): dos uniformes independientes u1 ∈ (0, 1], u2 ∈ [0, 1) dan dos normales estándar
//   independientes z0 = r·cos(2π·u2), z1 = r·sen(2π·u2), con r = √(−2·ln u1). Se usan las dos, en ese orden.

/** Generador mulberry32: devuelve una función que da uniformes en [0, 1). La semilla se reduce a 32 bits. */
export function mulberry32(semilla) {
  let a = semilla | 0;
  return function uniforme() {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Llena `destino` (Float64Array) con normales estándar N(0, 1) por Box-Muller sobre mulberry32(semilla).
 * Si el largo es impar, el último par se usa a medias (se descarta z1). Devuelve `destino`.
 */
export function normales(semilla, destino) {
  const u = mulberry32(semilla);
  const n = destino.length;
  for (let i = 0; i < n; i += 2) {
    const u1 = 1 - u();          // (0, 1]: nunca ln 0
    const u2 = u();
    const r = Math.sqrt(-2 * Math.log(u1));
    const fase = 2 * Math.PI * u2;
    destino[i] = r * Math.cos(fase);
    if (i + 1 < n) destino[i + 1] = r * Math.sin(fase);
  }
  return destino;
}
