// Pruebas del modelo pseudotridimensional (web/js/sismo/modelo.js): T8-T11 y T22 del contrato (7.8).
// Cada referencia es una solución cerrada deducida aquí mismo; las estructuras se arman con pruebas/_estructuras.mjs.
import { armarModelo, modos, modosDe, rigidezLateral, rigidezPDelta, derivaVectorial } from '../../../web/js/sismo/modelo.js';
import { E, seccion, cajon, estructura, portico } from './_estructuras.mjs';
import { caso, comprobar, errorRelativo } from './_util.mjs';

const G = 9.80665;

/** Modos con más de 99,9 % de su masa modal (φᵀMφ = 1) en los gdl de la componente c (0 = ux, 1 = uy, 2 = rz). */
function modosDe_(md, m, c, umbral = 0.999) {
  const out = [];
  md.formas.forEach((phi, r) => {
    let f = 0;
    for (let a = c; a < phi.length; a += 3) f += m[a] * phi[a] * phi[a];
    if (f > umbral) out.push(md.periodos_s[r]);
  });
  return out;
}

/** Rigidez lateral de un pórtico de un vano por pendiente-deflexión: k = (24EIc/h³)·(6β + 1)/(6β + 4). */
function kPortico(EIc, h, beta) {
  // Giro igual en los dos nudos (antisimetría), bases empotradas, deriva Δ. Columnas: M_sup = (EIc/h)(4θ − 6Δ/h),
  // M_inf = (EIc/h)(2θ − 6Δ/h); viga con giros iguales: M = 6(EIb/L)θ. Nudo: M_sup + M_viga = 0 →
  // θ = (6Δ/h)/(4 + 6β). Cortante de cada columna V = −(M_sup + M_inf)/h = (12EIc/h³)·Δ·(6β + 1)/(6β + 4).
  return ((24 * EIc) / h ** 3) * ((6 * beta + 1) / (6 * beta + 4));
}

// ---- T8: pórtico de cortante de 4 pisos ------------------------------------------------------------------------
function t8() {
  const n = 4, h = 3, L = 6, m = 50, Ic = 0.002, EIc = E * Ic;
  // EI_viga = 10⁵·EI_col, EA = 10⁶·12EI/h², Av → ∞ (sin Av): el pórtico es de cortante con k = Σ 12EI/h³
  const A = (1e6 * 12 * EIc) / (h * h) / E;
  const secciones = { C: seccion(Ic, { A }), V: seccion(1e5 * Ic, { A }), CY: seccion(3 * Ic, { A }), VY: seccion(1e5 * 3 * Ic, { A }) };
  const est = cajon({ n, h, Lx: L, Ly: L, m, Jz: (m * 2 * L * L) / 12, secciones, colX: 'C', vigaX: 'V', colY: 'CY', vigaY: 'VY' });
  const mod = armarModelo(est);
  const md = modos(mod, 12);
  const Tx = modosDe_(md, mod.masa, 0).sort((a, b) => b - a);
  const k = 4 * (12 * EIc) / h ** 3;            // dos pórticos X con dos columnas cada uno
  const casos = [comprobar('4 modos en x identificados', Tx.length === 4, `T = ${Tx.map((x) => x.toFixed(5)).join(', ')} s`)];
  for (let r = 1; r <= 4; r++) {
    // ω_r = 2√(k/m)·sen((2r − 1)π/(2(2n + 1))) (pórtico de cortante uniforme; Chopra, cap. 12)
    const w = 2 * Math.sqrt(k / m) * Math.sin(((2 * r - 1) * Math.PI) / (2 * (2 * n + 1)));
    casos.push(caso(`modo ${r} en x: T = ${Tx[r - 1].toFixed(6)} s frente a ${((2 * Math.PI) / w).toFixed(6)} s`, errorRelativo(Tx[r - 1], (2 * Math.PI) / w), 1e-3));
  }
  return casos;
}

// ---- T9: pórtico de un vano y un piso -------------------------------------------------------------------------
function t9() {
  const h = 3, L = 2 * h, m = 30, Ic = 0.002, EIc = E * Ic;
  const A = (1e6 * 12 * EIc) / (h * h) / E;
  const casos = [];
  for (const beta of [0.25, 1, 4]) {
    // β = (EIb/L)/(EIc/h) → Ib = β·Ic·L/h
    const secciones = { C: seccion(Ic, { A }), V: seccion((beta * Ic * L) / h, { A }), CY: seccion(3 * Ic, { A }), VY: seccion(3 * Ic * 50, { A }) };
    const est = cajon({ n: 1, h, Lx: L, Ly: L, m, Jz: (m * 2 * L * L) / 12, secciones, colX: 'C', vigaX: 'V', colY: 'CY', vigaY: 'VY' });
    const mod = armarModelo(est);
    const md = modos(mod, 3);
    const Tx = modosDe_(md, mod.masa, 0);
    const Tref = 2 * Math.PI * Math.sqrt(m / (2 * kPortico(EIc, h, beta)));
    casos.push(caso(`β = ${beta}: T = ${Tx[0]?.toFixed(6)} s frente a ${Tref.toFixed(6)} s`, errorRelativo(Tx[0], Tref), 1e-3));
  }
  return casos;
}

// ---- T10: un piso con rigidez excéntrica --------------------------------------------------------------------------
function t10() {
  const h = 3, L = 6, m = 40, Jz = 40 * (2 * L * L) / 12, Ic = 0.002, EIc = E * Ic, beta = 1;
  const A = (1e6 * 12 * EIc) / (h * h) / E;
  // pórtico X2 (y = L) 2,5 veces más rígido en las columnas, con la viga en la misma proporción (mismo β)
  const secciones = { C: seccion(Ic, { A }), V: seccion((beta * Ic * L) / h, { A }), C2: seccion(2.5 * Ic, { A }), V2: seccion((beta * 2.5 * Ic * L) / h, { A }) };
  const est = cajon({ n: 1, h, Lx: L, Ly: L, m, Jz, secciones, colX: 'C', vigaX: 'V', colX2: 'C2', vigaX2: 'V2', colY: 'C', vigaY: 'V' });
  const mod = armarModelo(est);
  const md = modos(mod, 3);
  // Rigidez en (ux, rz) respecto al centro de masa (L/2, L/2): un pórtico X en y = c aporta k·bbᵀ con b = [1, −(c − yc)]
  const k1 = kPortico(EIc, h, beta), k2 = kPortico(2.5 * EIc, h, beta), ky = kPortico(EIc, h, beta);
  const yc = L / 2, xc = L / 2;
  const Kxx = k1 + k2, Kxr = -k1 * (0 - yc) - k2 * (L - yc), Krr = k1 * yc ** 2 + k2 * (L - yc) ** 2 + ky * (0 - xc) ** 2 + ky * (L - xc) ** 2;
  // det([[Kxx − λm, Kxr], [Kxr, Krr − λJz]]) = 0 → m·Jz·λ² − (Kxx·Jz + Krr·m)·λ + (Kxx·Krr − Kxr²) = 0
  const a = m * Jz, b = -(Kxx * Jz + Krr * m), c = Kxx * Krr - Kxr * Kxr;
  const disc = Math.sqrt(b * b - 4 * a * c);
  const lam = [(-b - disc) / (2 * a), (-b + disc) / (2 * a)];
  const Tref = lam.map((l) => (2 * Math.PI) / Math.sqrt(l));
  // modos acoplados ux–rz: los que no tienen uy
  const Tm = [];
  md.formas.forEach((phi, r) => { if (mod.masa[1] * phi[1] * phi[1] < 1e-9) Tm.push(md.periodos_s[r]); });
  Tm.sort((x, y) => y - x);
  return [
    comprobar('dos modos acoplados ux–rz', Tm.length === 2, `motor: ${Tm.map((x) => x.toFixed(6)).join(', ')} s`),
    caso(`modo 1 ux–rz: ${Tm[0]?.toFixed(6)} s frente a ${Tref[0].toFixed(6)} s`, errorRelativo(Tm[0], Tref[0]), 1e-3),
    caso(`modo 2 ux–rz: ${Tm[1]?.toFixed(6)} s frente a ${Tref[1].toFixed(6)} s`, errorRelativo(Tm[1], Tref[1]), 1e-3),
  ];
}

// ---- T11: P-Delta -----------------------------------------------------------------------------------------------
function t11() {
  const casos = [];
  // (a) oscilador: rigidez efectiva k − P/h
  {
    const h = 3, L = 6, m = 40, Ic = 0.002, EIc = E * Ic, beta = 1;
    const A = (1e6 * 12 * EIc) / (h * h) / E;
    const k = 2 * kPortico(EIc, h, beta);
    const W = 0.05 * k * h;                       // P/h = 5 % de k
    const secciones = { C: seccion(Ic, { A }), V: seccion((beta * Ic * L) / h, { A }), CY: seccion(3 * Ic, { A }), VY: seccion(3 * Ic * 50, { A }) };
    const est = cajon({ n: 1, h, Lx: L, Ly: L, m, Jz: (m * 2 * L * L) / 12, secciones, colX: 'C', vigaX: 'V', colY: 'CY', vigaY: 'VY', p_delta: true, W });
    const mod = armarModelo(est);
    const Tx = modosDe_(modos(mod, 3), mod.masa, 0)[0];
    const Tref = 2 * Math.PI * Math.sqrt(m / (k - W / h));
    casos.push(caso(`(a) un piso con P/h = 5 % de k: T = ${Tx.toFixed(6)} s frente a 2π√(m/(k − P/h)) = ${Tref.toFixed(6)} s`, errorRelativo(Tx, Tref), 1e-3));
  }
  // (b) dos niveles con los centros de masa desalineados (el de arriba 6 m al norte)
  {
    const h = [4.5, 4.2], L = 12, Ic = 0.003, EIc = E * Ic;
    const A = (1e6 * 12 * EIc) / (16) / E;
    const m = [300, 220], Jz = [300 * (2 * L * L) / 12, 220 * (L * L + 6 * 6) / 12];
    const cm = [[6, 6], [6, 12]];
    const W = [m[0] * G, m[1] * G];
    const secciones = { C: seccion(Ic, { A }), V: seccion(2 * Ic, { A }) };
    const est = estructura({
      niveles: [{ h: h[0], m: m[0], Jz: Jz[0], cm: cm[0], W: W[0] }, { h: h[1], m: m[1], Jz: Jz[1], cm: cm[1], W: W[1] }],
      porticos: [
        portico({ id: 'X1', dir: 'x', c: 0, s: [0, 6, 12], n: 2, col: 'C', viga: 'V' }),
        portico({ id: 'X2', dir: 'x', c: 12, s: [0, 6, 12], n: 2, col: 'C', viga: 'V' }),
        portico({ id: 'X3', dir: 'x', c: 18, s: [0, 6, 12], n: 2, col: 'C', viga: 'V' }),
        portico({ id: 'Y1', dir: 'y', c: 0, s: [0, 6, 12, 18], n: 2, col: 'C', viga: 'V' }),
        portico({ id: 'Y2', dir: 'y', c: 12, s: [0, 6, 12, 18], n: 2, col: 'C', viga: 'V' }),
      ],
      secciones, p_delta: true,
    });
    const mod = armarModelo(est);
    const nd = 6;
    const Kpd = rigidezPDelta(mod);
    // a mano: por cada nivel j, 4 columnas articuladas con W_j/4 en CM_j ± r_j (en x y en y), r_j = √(Jz_j/m_j),
    // del nivel j a la base; en cada entrepiso k ≤ j aportan −(P/h_k)·(δxᵀδx + δyᵀδy), δ = deriva del punto
    const Kmano = new Float64Array(nd * nd);
    const fila = (k, x, y, comp) => {              // desplazamiento del punto (x, y) del nivel k (1, 2) en la componente
      const v = new Float64Array(nd);
      if (k === 0) return v;
      const b = 3 * (k - 1), [xc, yc] = cm[k - 1];
      if (comp === 0) { v[b] = 1; v[b + 2] = -(y - yc); } else { v[b + 1] = 1; v[b + 2] = x - xc; }
      return v;
    };
    for (let j = 1; j <= 2; j++) {
      const r = Math.sqrt(Jz[j - 1] / m[j - 1]), [xj, yj] = cm[j - 1];
      const puntos = [[xj + r, yj], [xj - r, yj], [xj, yj + r], [xj, yj - r]];
      for (let k = 1; k <= j; k++) {
        const P = W[j - 1] / 4, hk = h[k - 1];
        for (const [x, y] of puntos) {
          for (const comp of [0, 1]) {
            const s1 = fila(k, x, y, comp), s0 = fila(k - 1, x, y, comp);
            const d = s1.map((v, i) => v - s0[i]);
            for (let a = 0; a < nd; a++) for (let c = 0; c < nd; c++) Kmano[a * nd + c] -= (P / hk) * d[a] * d[c];
          }
        }
      }
    }
    let dif = 0, ref = 0;
    for (let i = 0; i < nd * nd; i++) { dif = Math.max(dif, Math.abs(Kpd[i] - Kmano[i])); ref = Math.max(ref, Math.abs(Kmano[i])); }
    casos.push(caso('(b) K_PΔ del motor frente a 4 columnas articuladas por nivel (términos)', dif / ref, 1e-9, `máx |K_PΔ| = ${ref.toFixed(2)} kN/m`));
    const KL = rigidezLateral(mod);
    const Ka = Float64Array.from(KL, (x, i) => x + Kmano[i]);
    const md = modos(mod, 6), mref = modosDe(Ka, mod.masa, nd, 6);
    let peor = 0;
    for (let r = 0; r < 6; r++) peor = Math.max(peor, errorRelativo(md.periodos_s[r], mref.periodos_s[r]));
    casos.push(caso('(b) períodos con K_PΔ del motor frente a K_PΔ armada a mano', peor, 1e-3, `T1 = ${md.periodos_s[0].toFixed(5)} s`));
  }
  return casos;
}

// ---- T22: deriva vectorial ------------------------------------------------------------------------------------------
function t22() {
  const h = 3, L = 10, Ic = 0.002;
  const secciones = { C: seccion(Ic, { A: 1 }), V: seccion(Ic, { A: 1 }) };
  const est = cajon({ n: 1, h, Lx: L, Ly: L, m: 30, Jz: (30 * 2 * L * L) / 12, secciones, colX: 'C', vigaX: 'V', colY: 'C', vigaY: 'V' });
  const mod = armarModelo(est);
  const rz = 1e-3;
  const deriva = new Float64Array(1), punto = new Float64Array(2);
  derivaVectorial(mod, Float64Array.from([0, 0, rz]), deriva, punto);
  // solo giro: cada esquina se mueve rz·r con r = √(5² + 5²) desde el centro de masa (5, 5)
  const ref = (rz * Math.hypot(5, 5)) / h;
  const esEsquina = [[0, 0], [L, 0], [L, L], [0, L]].some(([x, y]) => x === punto[0] && y === punto[1]);
  return [
    caso(`deriva vectorial ${deriva[0].toExponential(6)} frente a rz·√(5² + 5²)/h = ${ref.toExponential(6)}`, errorRelativo(deriva[0], ref), 1e-9),
    comprobar('el vértice informado es una esquina', esEsquina, `(${punto[0]}, ${punto[1]})`),
  ];
}

export const pruebas = [
  { id: 'T8', nombre: 'Pórtico de cortante de 4 pisos (períodos)', fn: t8 },
  { id: 'T9', nombre: 'Pórtico de un vano y un piso (pendiente-deflexión)', fn: t9 },
  { id: 'T10', nombre: 'Un piso con rigidez excéntrica (ux–rz)', fn: t10 },
  { id: 'T11', nombre: 'P-Delta: oscilador y dos niveles con centros de masa desalineados', fn: t11 },
  { id: 'T22', nombre: 'Deriva vectorial en las esquinas', fn: t22 },
];
