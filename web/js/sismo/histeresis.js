// Rótulas del elemento de Giberson y envolvente de la mampostería (contrato de la torre, 7.4; data/sismo/ESQUEMA.md).
//
// Una rótula es un resorte rotacional rígido-plástico en serie con la parte elástica del elemento. Su ley se escribe
// como θp = Φ(M): una función de M no decreciente y lineal por tramos que se arma desde el estado comprometido al
// comienzo del paso (tramos rígidos con pendiente 0, de recarga y de la envolvente). Con dos rótulas, el elemento
// cumple f̃·M + Φ(M) = r (f̃ = K̃⁻¹ es simétrica definida positiva y Φ es diagonal y monótona), un sistema monótono con
// solución única: se prueba la combinación de tramos que sugiere el momento de prueba elástico y, si no es la buena,
// todas las combinaciones (con el bilineal son las 4 del contrato: ninguna, i, j o las dos rótulas activas). La
// tangente consistente es K_t = (f̃ + diag(b))⁻¹, con b = dθp/dM del tramo (0 si es rígido; 1/H en la envolvente).
//
// Modelos:
//  - BILINEAL: endurecimiento cinemático. Rígida mientras −inf ≤ M − β ≤ sup, con β = H·θp; después, pendiente H.
//  - CLOUGH: envolvente bilineal fija M = ±(My + H·|θp|) (con θp ≥ 0 en la rama positiva y ≤ 0 en la negativa: la
//    envolvente arranca en θp = 0 en los dos sentidos). Mientras el momento conserva el signo de la excursión, la
//    descarga y la recarga son rígidas hasta la rama de la que salió; al cruzar M = 0 recarga en línea recta desde
//    (θp, 0) hacia el pico anterior del sentido opuesto (o hacia (0, ±My) si en ese sentido no hubo fluencia) y al
//    llegar sigue la envolvente. Sin endurecimiento cinemático. Es la regla del 7.4 y reproduce la tabla de T7.
//
// Estado por rótula (NE números en un Float64Array, desde el desplazamiento o):
//   [o]   θp          [o+1] dir (signo de la última excursión: 1, −1 o 0)   [o+2] θp al cruzar M = 0 (inicio de la recarga)
//   [o+3] θp del pico +   [o+4] M del pico + (> 0)   [o+5] θp del pico −   [o+6] M del pico − (< 0)   [o+7] libre
// (el bilineal usa solo θp).

export const SIN_ROTULA = 0, BILINEAL = 1, CLOUGH = 2;
export const NE = 8;
/** Campos de cada tramo en el arreglo de tramos: [inferior, superior, a, b, tipo] con θp = a + b·M en [inf, sup]. */
export const NT = 5;
/** Tipos de tramo: rígido (θp constante), recarga (Clough) y envolvente (fluencia). */
export const RIGIDO = 0, RECARGA = 1, ENVOLVENTE = 2;
export const MAX_TRAMOS = 5;

/** Estado inicial de una rótula con fluencia sup (momento positivo) e inf (magnitud del negativo). */
export function estadoInicial(sup, inf, st, o) {
  st[o] = 0; st[o + 1] = 0; st[o + 2] = 0;
  st[o + 3] = 0; st[o + 4] = sup; st[o + 5] = 0; st[o + 6] = -inf; st[o + 7] = 0;
}

/**
 * Intervalo de M en el que la rótula queda rígida desde su estado comprometido (camino rápido: si el momento de
 * prueba cae aquí, θp no cambia). Escribe [inferior, superior] en out[0], out[1].
 */
export function intervaloRigido(modelo, sup, inf, H, st, o, out) {
  if (modelo === SIN_ROTULA) { out[0] = -Infinity; out[1] = Infinity; return; }
  const thp = st[o];
  if (modelo === BILINEAL) { const beta = H * thp; out[0] = beta - inf; out[1] = beta + sup; return; }
  const dir = st[o + 1], thpR = st[o + 2], tP = st[o + 3], MP = st[o + 4], tN = st[o + 5], MN = st[o + 6];
  if (dir >= 0) {
    out[0] = tN === thp ? MN : 0;
    out[1] = tP === thpR ? MP : Math.min(MP, (MP * (thp - thpR)) / (tP - thpR));
  } else {
    out[0] = tN === thpR ? MN : Math.max(MN, (MN * (thp - thpR)) / (tN - thpR));
    out[1] = tP === thp ? MP : 0;
  }
}

function tramo(P, k, lo, hi, a, b, tipo) {
  const o = k * NT;
  P[o] = lo; P[o + 1] = hi; P[o + 2] = a; P[o + 3] = b; P[o + 4] = tipo;
  return k + 1;
}

/** Arma los tramos de Φ desde el estado comprometido. Devuelve cuántos (≤ MAX_TRAMOS), en orden creciente de M. */
export function tramos(modelo, sup, inf, H, st, o, P) {
  const thp = st[o];
  if (modelo === SIN_ROTULA) return tramo(P, 0, -Infinity, Infinity, thp, 0, RIGIDO);
  if (modelo === BILINEAL) {
    // envolvente inferior: M − H·θp = −inf → θp = (M + inf)/H; superior: θp = (M − sup)/H
    const beta = H * thp;
    let k = tramo(P, 0, -Infinity, beta - inf, inf / H, 1 / H, ENVOLVENTE);
    k = tramo(P, k, beta - inf, beta + sup, thp, 0, RIGIDO);
    return tramo(P, k, beta + sup, Infinity, -sup / H, 1 / H, ENVOLVENTE);
  }
  const dir = st[o + 1], thpR = st[o + 2], tP = st[o + 3], MP = st[o + 4], tN = st[o + 5], MN = st[o + 6];
  let k = tramo(P, 0, -Infinity, MN, inf / H, 1 / H, ENVOLVENTE);   // envolvente negativa: M = −inf + H·θp
  if (dir >= 0) {
    // sentido opuesto: rígida hasta M = 0 y recarga desde (θp, 0) hacia el pico negativo
    const bN = (tN - thp) / MN;
    k = tramo(P, k, MN, 0, thp, bN, bN === 0 ? RIGIDO : RECARGA);
    const Rhi = tP === thpR ? MP : Math.min(MP, (MP * (thp - thpR)) / (tP - thpR));
    k = tramo(P, k, 0, Rhi, thp, 0, RIGIDO);
    if (Rhi < MP) k = tramo(P, k, Rhi, MP, thpR, (tP - thpR) / MP, RECARGA);
  } else {
    const Rlo = tN === thpR ? MN : Math.max(MN, (MN * (thp - thpR)) / (tN - thpR));
    if (Rlo > MN) k = tramo(P, k, MN, Rlo, thpR, (tN - thpR) / MN, RECARGA);
    k = tramo(P, k, Rlo, 0, thp, 0, RIGIDO);
    const bP = (tP - thp) / MP;
    k = tramo(P, k, 0, MP, thp, bP, bP === 0 ? RIGIDO : RECARGA);
  }
  return tramo(P, k, MP, Infinity, -sup / H, 1 / H, ENVOLVENTE);  // envolvente positiva: M = sup + H·θp
}

/**
 * Nuevo estado comprometido (en stT desde oT) a partir del anterior (stN desde oN), del momento final M, de θp final
 * y del tipo de tramo en el que quedó.
 */
export function actualizar(modelo, stN, oN, M, thp, tipo, stT, oT) {
  const thpAnt = stN[oN], dir = stN[oN + 1];   // se leen antes de escribir: stT puede ser stN (en el lugar)
  if (stT !== stN || oT !== oN) for (let i = 0; i < NE; i++) stT[oT + i] = stN[oN + i];
  stT[oT] = thp;
  if (modelo !== CLOUGH) return;
  // al cruzar M = 0 empieza una excursión nueva; la recarga sale del θp que tenía la rótula (rígida hasta M = 0)
  if (M > 0 && dir <= 0) { stT[oT + 1] = 1; stT[oT + 2] = thpAnt; }
  else if (M < 0 && dir >= 0) { stT[oT + 1] = -1; stT[oT + 2] = thpAnt; }
  if (tipo === ENVOLVENTE) {
    if (M > 0 && M > stT[oT + 4]) { stT[oT + 3] = thp; stT[oT + 4] = M; }
    else if (M < 0 && M < stT[oT + 6]) { stT[oT + 5] = thp; stT[oT + 6] = M; }
  }
}

function buscarTramo(P, n, M, tol) {
  for (let k = 0; k < n; k++) if (M >= P[k * NT] - tol && M <= P[k * NT + 1] + tol) return k;
  return n - 1;
}

/**
 * Resuelve f̃·M + Φ(M) = r para las dos rótulas de un elemento (sistema 2 × 2 simétrico definido positivo más una
 * función diagonal monótona lineal por tramos). (Mg1, Mg2) es el momento de prueba elástico, que sugiere los tramos.
 * Escribe en out: [M1, M2, b1, b2, tramo1, tramo2]. Devuelve false si no encuentra una combinación consistente.
 */
export function resolver2x2(f11, f12, f22, r1, r2, P1, n1, P2, n2, Mg1, Mg2, tol, out) {
  let i1 = buscarTramo(P1, n1, Mg1, tol), i2 = buscarTramo(P2, n2, Mg2, tol);
  for (let intento = 0; intento < 8; intento++) {
    if (prueba(f11, f12, f22, r1, r2, P1, i1, P2, i2, tol, out)) return true;
    const j1 = buscarTramo(P1, n1, out[0], tol), j2 = buscarTramo(P2, n2, out[1], tol);
    if (j1 === i1 && j2 === i2) break;
    i1 = j1; i2 = j2;
  }
  for (i1 = 0; i1 < n1; i1++) for (i2 = 0; i2 < n2; i2++) if (prueba(f11, f12, f22, r1, r2, P1, i1, P2, i2, tol, out)) return true;
  return false;
}

function prueba(f11, f12, f22, r1, r2, P1, i1, P2, i2, tol, out) {
  const o1 = i1 * NT, o2 = i2 * NT;
  const b1 = P1[o1 + 3], b2 = P2[o2 + 3];
  const A11 = f11 + b1, A22 = f22 + b2;
  const det = A11 * A22 - f12 * f12;
  const s1 = r1 - P1[o1 + 2], s2 = r2 - P2[o2 + 2];
  const M1 = (A22 * s1 - f12 * s2) / det, M2 = (A11 * s2 - f12 * s1) / det;
  out[0] = M1; out[1] = M2; out[2] = b1; out[3] = b2; out[4] = i1; out[5] = i2;
  return M1 >= P1[o1] - tol && M1 <= P1[o1 + 1] + tol && M2 >= P2[o2] - tol && M2 <= P2[o2 + 1] + tol;
}

/**
 * Una rótula en serie con su parte elástica k_e (prueba T7 y validación con OpenSees, 7.9): `imponer(θ)` lleva el
 * conjunto a un giro total θ desde el estado comprometido y devuelve { M, thp, fluye } ya comprometido. Usa las mismas
 * funciones que el elemento (camino rápido, tramos, resolver2x2 y actualizar).
 */
export function rotulaEnSerie({ modelo = BILINEAL, My_pos, My_neg = My_pos, alfa, ke }) {
  const H = (alfa > 0 ? alfa : 1e-4) * ke;
  const st = new Float64Array(NE), stT = new Float64Array(NE), stJ = new Float64Array(NE);
  estadoInicial(My_pos, My_neg, st, 0);
  const P1 = new Float64Array(MAX_TRAMOS * NT), P2 = new Float64Array(NT), out = new Float64Array(6), ri = new Float64Array(2);
  const nj = tramos(SIN_ROTULA, 0, 0, 0, stJ, 0, P2);
  const tol = 1e-11 * (My_pos + My_neg);
  return {
    imponer(theta) {
      const Mtr = ke * (theta - st[0]);
      intervaloRigido(modelo, My_pos, My_neg, H, st, 0, ri);
      let M = Mtr, thp = st[0], tipo = RIGIDO;
      if (Mtr < ri[0] || Mtr > ri[1]) {
        const n1 = tramos(modelo, My_pos, My_neg, H, st, 0, P1);
        if (!resolver2x2(1 / ke, 0, 1, theta, 0, P1, n1, P2, nj, Mtr, 0, tol, out)) throw new Error('rótula sin solución');
        M = out[0];
        const o = out[4] * NT;
        thp = P1[o + 2] + P1[o + 3] * M;
        tipo = P1[o + 4];
      }
      actualizar(modelo, st, 0, M, thp, tipo, stT, 0);
      st.set(stT);
      return { M, thp, fluye: tipo === ENVOLVENTE };
    },
    estado: st,
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Mampostería: envolvente trilineal de Tomaževič con descarga orientada al origen (secante), sin degradación cíclica
// ---------------------------------------------------------------------------------------------------------------
/**
 * Fuerza y pendiente de la envolvente para x = |Δ| ≥ 0: (0, 0) → (dcr, Vcr) → (dmax, Vmax) → (du, Vmax) →
 * (1,2·du, residual·Vmax) y constante después (Tomaževič, 1999; la rama de caída hasta 1,2·du es la del cálculo de
 * referencia de la ola 0). Escribe [F, k] en out.
 */
export function envolventeMuro(env, x, out) {
  const x1 = env.dcr_m, x2 = env.dmax_m, x3 = env.du_m, x4 = 1.2 * env.du_m;
  const y1 = env.Vcr_kN, y2 = env.Vmax_kN, y4 = env.residual * env.Vmax_kN;
  if (x <= x1) { out[1] = y1 / x1; out[0] = out[1] * x; return out; }
  if (x <= x2) { out[1] = (y2 - y1) / (x2 - x1); out[0] = y1 + out[1] * (x - x1); return out; }
  if (x <= x3) { out[1] = 0; out[0] = y2; return out; }
  if (x <= x4) { out[1] = (y4 - y2) / (x4 - x3); out[0] = y2 + out[1] * (x - x3); return out; }
  out[0] = y4; out[1] = 0;
  return out;
}

/**
 * Respuesta del muro para la deriva Δ del entrepiso en su línea, con dmax el mayor |Δ| comprometido: sobre la
 * envolvente si |Δ| ≥ dmax; si no, la secante al punto de la envolvente en dmax (descarga orientada al origen).
 * Escribe [F, k, dmax_nuevo] en out. Los muros aislados no aportan fuerza (pero se sigue su deriva).
 */
export function respuestaMuro(env, aislado, Delta, dmax, out) {
  const x = Math.abs(Delta);
  if (aislado) { out[0] = 0; out[1] = 0; out[2] = x > dmax ? x : dmax; return out; }
  if (x >= dmax) {
    envolventeMuro(env, x, out);
    out[0] = Delta < 0 ? -out[0] : out[0];
    out[2] = x;
    return out;
  }
  envolventeMuro(env, dmax, out);
  const ks = out[0] / dmax;
  out[0] = ks * Delta; out[1] = ks; out[2] = dmax;
  return out;
}
