// Movimiento del suelo para el simulador sísmico de la torre (contrato de integración, 7.4; data/sismo/ESQUEMA.md).
// Módulo puro: sin DOM, sin three, imports relativos con extensión. Unidades SI en las salidas (m/s², m/s, m, s, g),
// salvo donde el nombre del campo dice otra cosa (cm/s, dina·cm, bar, g/cm³, km/s, km).
//
// Qué hace:
//   - sintetiza dos componentes horizontales con el método estocástico de fuente puntual de Boore (2003), con los
//     12 pasos de amenaza.json → notas_para_implementar y los parámetros de amenaza.json (cortical, intraplaca
//     profunda y la banda de transición de profundidad de 40 a 70 km, cambio E15);
//   - calcula intensidades (PGA, PGV, PGD, Arias, D5-95), el espectro de respuesta exacto para excitación lineal
//     por tramos (Nigam y Jennings, 1969), el espectro de Fourier y el espectro objetivo;
//   - evalúa cuatro ecuaciones de predicción (GMPE) con los coeficientes copiados de amenaza.json, el espectro
//     elástico de la NSR-10 y los avisos de combinación;
//   - filtra y diezma el registro para la calidad baja (FIR de fase cero a 20 Hz, una de cada dos muestras).
//
// ── Magnitud: Richter (ML) y magnitud de momento (Mw) ──────────────────────────────────────────────────────────
// La persona habla de «la escala de Richter»; el control de la vista es Mw y el texto lo dice así: «Magnitud Mw (la
// escala que reemplazó a la de Richter)» (amenaza.json → magnitud.control_en_pantalla). Por qué:
//   - ML (Richter, 1935) = log10 A − log10 A0(Δ): A es la amplitud máxima en mm de un sismógrafo Wood-Anderson
//     (período propio 0,8 s) y A0(Δ) la de un sismo de referencia a la misma distancia. Mide ondas de ≈ 1 s, así que
//     se satura: por encima de ML ≈ 6,5 a 7 sismos muy distintos marcan casi lo mismo.
//   - Mw (Hanks y Kanamori, 1979) sale del momento sísmico M0 = μ·A·D (rigidez × área rota × deslizamiento):
//     Mw = (2/3)·log10 M0[dina·cm] − 10,7, es decir M0 = 10^(1,5·Mw + 16,05) dina·cm (16,05 = 1,5 × 10,7). No se
//     satura y es la magnitud que piden la física de la fuente (f0, Δσ) y las GMPE. Este módulo solo usa Mw.
//     (La norma IASPEI de 2013 usa log10 M0[N·m] = 1,5·Mw + 9,1, es decir 16,1 en dina·cm: 0,03 unidades de Mw de
//     diferencia. Se usa 16,05 porque con esa constante se calibraron Δσ y se escribieron f0 y los escenarios de
//     amenaza.json, igual que en SMSIM, pyrvt y StochasticGroundMotionSimulation.jl.)
//   - No hay una conversión única ML → Mw: para sismos moderados difieren en pocas décimas y la relación de la red
//     colombiana está por confirmar (amenaza.json → magnitud.explicacion_ciudadana). Por eso ni este módulo ni la
//     vista convierten: el deslizador es Mw (de 4 a 8), la vista muestra Mw, M0 y la energía, y explica que
//     «Richter» es el nombre popular de la magnitud. Quien piense en «6,2 en la escala de Richter» puede poner Mw 6,2:
//     en sismos moderados la diferencia es de décimas, y de los grandes las agencias (SGC, USGS) ya reportan Mw.
//   - Energía radiada aproximada Es ≈ M0/20.000 (Kanamori, 1977) → log10 Es[J] ≈ 1,5·Mw + 4,75; cada punto de Mw es
//     10^1,5 ≈ 32 veces más energía y 0,2 puntos son el doble (10^0,3 = 2).
//
// Convenciones de la síntesis (decisiones de este módulo, escritas en ESQUEMA.md, «Movimiento del suelo»):
//   - Δt = 0,005 s siempre (contrato, 7.4). Misma semilla y mismos parámetros → mismo acelerograma.
//   - El ruido con ventana empieza en t_pre = max(5·τ, 1 s), con τ = 1/(2π·f0): el filtro A(f) es de fase cero
//     (real y positivo), así que su respuesta al impulso es simétrica y deja un precursor antes de la ventana. Su parte
//     de baja frecuencia decae como e^(−|t|/τ) (A ∝ f²/(1 + (f/f0)²) ↔ δ(t) − π·f0·e^(−2π·f0·|t|), deducción
//     propia); con 5·τ queda < 1 % (e^−5 = 0,7 %). El mínimo de 1 s cubre la cola de κ y de Q, más corta. El registro
//     entregado termina t_pre después del fin de la ventana por la misma razón. SMSIM (Boore, 2003) hace lo mismo con
//     sus rellenos «tpadl» y «tpadt». La energía que queda fuera se mide y va en meta.fraccion_energia_fuera (del
//     orden de 10⁻⁷ en los escenarios de amenaza.json). sim.py de la investigación empieza la ventana en t = 0 y el
//     precursor da la vuelta al final del búfer circular: la estadística es la misma (T15 lo comprueba).
//   - PGV y PGD se integran en el tiempo (trapecios, desde reposo) en lugar de por FFT (paso 10): sirve igual para
//     cualquier registro (también el filtrado de la calidad baja) y no hay desplazamiento residual que corregir,
//     porque A(f) ∝ f² cerca de f = 0 (la integral de a y la de v son nulas).
//   - N (potencia de 2) ≥ muestras antes de la ventana + ventana + 40 s de ceros (paso 5 de las notas).
//   - Las dos componentes comparten el PGA en roca de la no linealidad del suelo: la media geométrica de los PGA en
//     roca de las dos (BSSA14 define PGAr como la mediana de la media de las dos horizontales; el suelo es uno solo).
//   - La caída de esfuerzos intraplaca depende de la profundidad, con la pendiente y el tope de las GMPE con que se
//     calibró (DSIGMA_INTRAPLACA_PROF, revisión A6); BSSA14 pierde su peso entre 15 y 25 km en la comparación con las
//     GMPE, porque no tiene término de profundidad (fraccionBSSA14).

import { rfft, irfft, siguientePotencia2 } from './fft.js';
import { normales } from './azar.js';

export const G = 9.80665;                  // m/s² (ESQUEMA.md, «Unidades y ejes»)
export const DT_SINTESIS = 0.005;          // s (contrato 7.4; amenaza.json → parametros_estocasticos.comunes.simulacion.dt_s)
export const PERIODOS_GMPE_S = [0, 0.2, 0.5, 1.0];   // períodos con coeficientes en amenaza.json (0 = PGA)

// Constantes que en amenaza.json están solo dentro de fórmulas escritas (no como números sueltos). Las pruebas
// (scripts/sismo/pruebas/movimiento.mjs, MOV1) comprueban que esas fórmulas siguen diciendo lo mismo.
const BRUNE_F0 = 4.906e6;   // f0 = 4,906e6·βs·(Δσ/M0)^(1/3) [Hz; km/s, bar, dina·cm] (Brune 1970; Boore 2003). Deducción:
//   f0 = 2,34·β/(2π·r) y Δσ = 7·M0/(16·r³) → f0 = 0,4903·β·(Δσ/M0)^(1/3) en cgs; β ×10⁵ cm/s y Δσ ×10⁶ dina/cm²
//   ((10⁶)^(1/3) = 100) dan 4,903e6; 4,906e6 es el valor de amenaza.json (4,9058e6 en StochasticGroundMotionSimulation.jl).
const MW_A_M0 = { a: 1.5, b: 16.05 };       // M0 = 10^(1,5·Mw + 16,05) dina·cm (Hanks y Kanamori 1979)
const ES_SOBRE_M0 = 1 / 20000;              // Es ≈ M0/20.000 (Kanamori 1977; amenaza.json → magnitud.formulas)
const H_FF = { a: -0.405, b: 0.235 };       // h_ff = 10^(−0,405 + 0,235·Mw) km (Yenier y Atkinson 2015)
const BT14_MAS_ALLA = { R: 270, T: 34.2, b: 0.156 };   // Tcamino = 34,2 + 0,156·(R − 270) para R > 270 km
const TCAMINO_INTRAPLACA_B = 0.05;          // Tcamino = 0,05·R (Atkinson y Silva 2000; Campbell 2003)
// Caída de esfuerzos intraplaca según la profundidad (regla del motor, revisión A6; ESQUEMA.md, «Profundidad»):
//   Δσ(h) = Δσ_ref·exp((3/2)·θ·(min(h, hc) − hc)),  Δσ_ref = 800 bar (amenaza.json, calibrado con h de 100 a 150 km).
// θ = 0,0135/km es la media de las pendientes de profundidad del PGA de las GMPE con que se calibró Δσ_ref:
// BC Hydro 2016, fdepth = θ11·(min(Zh, 120) − 60) con θ11 = 0,013, y Zhao et al. 2006, e·(min(h, 125) − 15) con
// e = 0,0141 (amenaza.json → gmpe). hc = 120 km es el tope de BC Hydro (Zhao usa 125). El 3/2: en alta frecuencia
// (f ≫ f0) la amplitud de Fourier de Brune es ∝ M0·f0² ∝ M0^(1/3)·Δσ^(2/3), así que d ln A/dh = θ pide
// d ln Δσ/dh = (3/2)·θ. Con Δσ fijo, entre 40 y 120 km la simulación iba al revés de las GMPE: a igual distancia
// epicentral el PGA subía 2,1-2,4 veces de h = 40 a 70 km y bajaba después (a 70 km quedaba 1,5-2,7 veces sobre sus
// GMPE). Para h ≥ 120 km (el nido, 150 km) Δσ = Δσ_ref: los escenarios calibrados no cambian.
const DSIGMA_INTRAPLACA_PROF = { theta: 0.0135, hc: 120 };
const IMPEDANCIA_REF = { rho: 2.8, beta: 3.5 };   // Fimp = √(ρs·βs/(2,8·3,5)): corteza de la amplificación genérica
const RELLENO_S = 40;                        // ≥ 40 s de ceros después de la ventana (notas, paso 5)
const F_CERO = 1e-6;                         // «usar f_0 = 1e-6 para no dividir por cero» (notas, paso 5)
const PGA_BSSA_F3 = 0.1;                     // g; Fnl = f2·ln((PGAr + 0,1)/0,1) (Seyhan y Stewart 2014)
const VREF_BSSA = 760;                       // m/s, roca de referencia de BSSA14
const CONSTANTES_TIEMPO_COLA = 5;            // e^−5 = 0,7 % (ver arriba)
const COLA_MINIMA_S = 1;                     // cubre la cola de κ (núcleo de Cauchy de ancho ≈ κ/2) y de Q

// ── Utilidades ────────────────────────────────────────────────────────────────────────────────────────────────
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const coma = (x, d = 1) => x.toFixed(d).replace('.', ',');

function errorDatos(mensaje) {
  const e = new Error(mensaje);
  e.codigo = 'datos';
  return e;
}

/** Interpolación lineal de y(x) con x creciente; fuera del rango se recorta al extremo (como numpy.interp). */
function interp(x, xs, ys) {
  const n = xs.length;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[n - 1]) return ys[n - 1];
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1;
    if (xs[m] <= x) lo = m; else hi = m;
  }
  return ys[lo] + ((x - xs[lo]) / (xs[hi] - xs[lo])) * (ys[hi] - ys[lo]);
}

// ── Magnitud ──────────────────────────────────────────────────────────────────────────────────────────────────
/** Momento sísmico y energía radiada aproximada de una Mw (ver la explicación de ML y Mw arriba). */
export function momentoSismico(Mw) {
  const M0_dina_cm = Math.pow(10, MW_A_M0.a * Mw + MW_A_M0.b);
  const M0_N_m = M0_dina_cm * 1e-7;          // 1 dina·cm = 10⁻⁷ N·m
  return { M0_dina_cm, M0_N_m, energia_J_aprox: M0_N_m * ES_SOBRE_M0 };
}

// ── Régimen por profundidad (E15) ────────────────────────────────────────────────────────────────────────────
/** → { regimen: 'cortical' | 'transicion' | 'intraplaca_profunda', w } con w = clamp((h − 40)/30, 0, 1). */
export function regimenPorProfundidad(h_km) {
  const w = clamp((h_km - 40) / 30, 0, 1);
  return { regimen: w <= 0 ? 'cortical' : w >= 1 ? 'intraplaca_profunda' : 'transicion', w };
}

// ── Lectura de amenaza.json ──────────────────────────────────────────────────────────────────────────────────
const CACHE_PARAMETROS = new WeakMap();

function leerParametros(amenaza) {
  let P = CACHE_PARAMETROS.get(amenaza);
  if (P) return P;
  const pe = amenaza?.parametros_estocasticos;
  if (!pe?.comunes || !pe.cortical || !pe.intraplaca_profunda) throw errorDatos('amenaza.json sin parametros_estocasticos completos');
  const c = pe.comunes;
  const sh = c.ventana_saragoni_hart;
  const sitio = amenaza.amplificacion_sitio;
  const filas = sitio.factor_suelo_BSSA14.filas;   // [T, c, Vc, f4, f5]
  const comunes = {
    Rtp: c.patron_radiacion_Rtp.valor,
    F: c.superficie_libre_F.valor,
    V: Math.SQRT1_2,      // partición en dos horizontales: 1/√2 (amenaza.json guarda 0,7071 redondeado)
    R0: c.R0_km.valor,
    unidades: c.factor_unidades.valor,
    eps: sh.epsilon, eta: sh.eta, fTgm: sh.f_Tgm,
    dt: c.simulacion.dt_s,
  };
  const regimen = (r, clave) => ({
    regimen: clave,
    dsigma: r.delta_sigma_bar.valor,
    rho: r.rho_s_g_cm3.valor,
    beta: r.beta_s_km_s.valor,
    tramos: r.dispersion_geometrica.tramos,
    Q0: r.Q.Q0, etaQ: r.Q.eta, betaQ: r.Q.beta_Q_km_s,
    kappa: r.kappa0_s.valor,
  });
  const cort = regimen(pe.cortical, 'cortical');
  const dc = pe.cortical.duracion_camino;
  cort.durR = dc.tabla_R_km;
  cort.durT = dc.tabla_Tcamino_s;
  cort.fimp = 1;
  const intra = regimen(pe.intraplaca_profunda, 'intraplaca_profunda');
  intra.fimp = Math.sqrt((intra.rho * intra.beta) / (IMPEDANCIA_REF.rho * IMPEDANCIA_REF.beta));
  P = {
    comunes, cortical: cort, intraplaca_profunda: intra,
    a760: { lnf: sitio.A760.f_Hz.map(Math.log), A: sitio.A760.A },
    suelo: {
      lnT: filas.map((f) => Math.log(f[0])), c: filas.map((f) => f[1]), Vc: filas.map((f) => f[2]),
      f4: filas.map((f) => f[3]), f5: filas.map((f) => f[4]),
      Tmin: filas[0][0], Tmax: filas[filas.length - 1][0],
    },
    controles: amenaza.controles,
  };
  CACHE_PARAMETROS.set(amenaza, P);
  return P;
}

/** Valida y completa los parámetros del movimiento (los que faltan toman el `defecto` de amenaza.json). */
function normalizarParametros(p, amenaza) {
  const ctl = amenaza.controles || {};
  const q = { ...p };
  const campos = ['Mw', 'profundidad_km', 'distancia_epicentral_km', 'vs30_m_s'];
  for (const k of campos) {
    if (q[k] === undefined && ctl[k]?.defecto !== undefined) q[k] = ctl[k].defecto;
    if (typeof q[k] !== 'number' || !Number.isFinite(q[k])) throw errorDatos(`parámetro ${k} = ${q[k]} no es un número finito`);
    const r = ctl[k];
    if (r && (q[k] < r.min - 1e-9 || q[k] > r.max + 1e-9)) throw errorDatos(`parámetro ${k} = ${q[k]} fuera del rango ${r.min}…${r.max}`);
  }
  if (q.semilla === undefined) q.semilla = ctl.semilla?.defecto ?? 2028;
  if (!Number.isInteger(q.semilla)) throw errorDatos(`semilla = ${q.semilla} no es un entero`);
  if (q.regimen === undefined) q.regimen = 'auto';
  if (!['auto', 'cortical', 'intraplaca_profunda'].includes(q.regimen)) throw errorDatos(`regimen = ${q.regimen} no es 'auto', 'cortical' ni 'intraplaca_profunda'`);
  if (q.escala_pgar === undefined) q.escala_pgar = 1;
  if (!(q.escala_pgar > 0 && Number.isFinite(q.escala_pgar))) throw errorDatos(`escala_pgar = ${q.escala_pgar} debe ser > 0`);
  return q;
}

// ── Términos del espectro (un régimen o dos con su peso) ─────────────────────────────────────────────────────
function dispersionGeometrica(R, tramos) {
  // Z(R) por tramos continuos con R0 = 1 km (amenaza.json → notas_para_implementar.dispersion_js)
  let g = 1, r0 = 1;
  for (const { exponente: p, hasta_km: re } of tramos) {
    const r1 = re == null ? R : Math.min(R, re);
    if (r1 > r0) { g *= Math.pow(r0 / r1, p); r0 = r1; }
    if (re == null || R <= re) break;
  }
  return g;
}

function tcaminoBT14(R, t) {
  // Boore y Thompson (2014), regiones activas: lineal en R por la tabla; después de 270 km, recta
  if (R > BT14_MAS_ALLA.R) return BT14_MAS_ALLA.T + BT14_MAS_ALLA.b * (R - BT14_MAS_ALLA.R);
  return interp(R, t.durR, t.durT);
}

/** Términos del espectro: [{ regimen, peso, M0, f0, C, Ref, Z, Tgm, … }]. Uno solo fuera de la banda E15. */
function terminos(q, P) {
  const { Mw, profundidad_km: h, distancia_epicentral_km: Repi } = q;
  let w;
  if (q.regimen === 'cortical') w = 0;
  else if (q.regimen === 'intraplaca_profunda') w = 1;
  else w = regimenPorProfundidad(h).w;
  const { M0_dina_cm: M0 } = momentoSismico(Mw);
  const Rhip = Math.hypot(Repi, h);
  const c = P.comunes;
  const lista = [];
  const agregar = (t, peso) => {
    // Δσ del término: intraplaca, según la profundidad (DSIGMA_INTRAPLACA_PROF); cortical, el de amenaza.json
    const dsigma = t.regimen === 'cortical' ? t.dsigma
      : t.dsigma * Math.exp(1.5 * DSIGMA_INTRAPLACA_PROF.theta * (Math.min(h, DSIGMA_INTRAPLACA_PROF.hc) - DSIGMA_INTRAPLACA_PROF.hc));
    const f0 = BRUNE_F0 * t.beta * Math.cbrt(dsigma / M0);
    // C = Rθφ·F·V/(4π·ρs·βs³·R0)·10⁻²⁰: con M0 en dina·cm, ρ en g/cm³, β en km/s y R en km el espectro de
    // desplazamiento sale en cm·s (10⁵ cm/km elevado a 4: (km/s)³·km); ×(2πf)² da aceleración en cm/s.
    const C = (c.Rtp * c.F * c.V) / (4 * Math.PI * t.rho * t.beta ** 3 * c.R0) * c.unidades;
    let Ref, Tcamino;
    if (t.regimen === 'cortical') {
      const hff = Math.pow(10, H_FF.a + H_FF.b * Mw);   // saturación cerca de la falla (falla finita)
      Ref = Math.hypot(Rhip, hff);
      Tcamino = tcaminoBT14(Ref, t);
    } else {
      Ref = Rhip;                                          // fuente ≥ 50 km: sin factor de falla finita
      Tcamino = TCAMINO_INTRAPLACA_B * Ref;
    }
    const Tgm = 1 / f0 + Tcamino;                           // Tfuente = 1/f0 (Brune) + camino
    lista.push({ regimen: t.regimen, peso, t, dsigma, M0, f0, C, Rhip, Ref, Z: dispersionGeometrica(Ref, t.tramos), Tcamino, Tgm });
  };
  if (w < 1) agregar(P.cortical, 1 - w);
  if (w > 0) agregar(P.intraplaca_profunda, w);
  return { w, lista };
}

/** ln de la amplitud de Fourier en roca 760 (cm/s) de un término, en la frecuencia f > 0 (paso 6 de las notas). */
function lnAmplitudTermino(T, f, lnA760) {
  const t = T.t;
  const Q = t.Q0 * Math.pow(f, t.etaQ);
  return Math.log(T.C * T.M0) + 2 * Math.log(2 * Math.PI * f) - Math.log(1 + (f / T.f0) ** 2) + Math.log(T.Z)
    - (Math.PI * f * T.Ref) / (Q * t.betaQ) + lnA760 + Math.log(t.fimp) - Math.PI * t.kappa * f;
}

/** A760(f), Boore (2016): lineal en ln f, recortada a los extremos de la tabla. */
function amp760(P, f) {
  return interp(Math.log(f), P.a760.lnf, P.a760.A);
}

/** Factor de sitio de BSSA14 (Seyhan y Stewart 2014) en T = 1/f: { lin: Flin, f2 }, Fnl = f2·ln((PGAr + 0,1)/0,1). */
function factorSueloCoef(P, f, vs30) {
  const s = P.suelo;
  const T = clamp(1 / f, s.Tmin, s.Tmax);
  const x = Math.log(T);
  const c = interp(x, s.lnT, s.c), Vc = interp(x, s.lnT, s.Vc), f4 = interp(x, s.lnT, s.f4), f5 = interp(x, s.lnT, s.f5);
  const lin = c * Math.log(Math.min(vs30, Vc) / VREF_BSSA);
  const f2 = f4 * (Math.exp(f5 * (Math.min(vs30, VREF_BSSA) - 360)) - Math.exp(f5 * (VREF_BSSA - 360)));
  return { lin, f2 };
}

const lnNoLineal = (pgar_g) => Math.log((pgar_g + PGA_BSSA_F3) / PGA_BSSA_F3);

/** Valores para mostrar de la mezcla (logarítmica en lo multiplicativo, lineal en κ0, η y Tgm). */
function resumenTerminos(T) {
  const L = T.lista;
  const lg = (k) => Math.exp(L.reduce((s, x) => s + x.peso * Math.log(k(x)), 0));
  const li = (k) => L.reduce((s, x) => s + x.peso * k(x), 0);
  return {
    f0_Hz: lg((x) => x.f0), delta_sigma_bar: lg((x) => x.dsigma), beta_s_km_s: lg((x) => x.t.beta), rho_s_g_cm3: lg((x) => x.t.rho),
    Q0: lg((x) => x.t.Q0), eta: li((x) => x.t.etaQ), kappa0_s: li((x) => x.t.kappa), Ref_km: lg((x) => x.Ref),
    Tgm_s: li((x) => x.Tgm),
  };
}

// ── Espectro objetivo (determinista) ─────────────────────────────────────────────────────────────────────────
function lnAmplitudMezcla(T, P, f) {
  const lnA760 = Math.log(amp760(P, f));
  let s = 0;
  for (const x of T.lista) s += x.peso * lnAmplitudTermino(x, f, lnA760);
  return s;
}

/** PGA esperado (g) de un espectro de Fourier por vibración aleatoria (RVT): Boore (2003) con el factor de pico de
 *  Cartwright y Longuet-Higgins (1956). a_rms = √(m0/Tgm), m_k = 2∫(2πf)^k·A² df hasta Nyquist (100 Hz con Δt = 0,005 s),
 *  Nz = √(m2/m0)·Tgm/π, Ne = √(m4/m2)·Tgm/π, pico/rms = √2·∫0^∞ {1 − [1 − ξ·e^(−z²)]^Ne} dz con ξ = Nz/Ne. */
function pgaRVT(Afun, Tgm, fNyq) {
  const nf = 4000, f1 = 1e-3;
  const r = Math.log(fNyq / f1) / (nf - 1);
  let m0 = 0, m2 = 0, m4 = 0, fa = f1, ga = Afun(f1) ** 2;
  for (let i = 1; i < nf; i++) {
    const fb = f1 * Math.exp(r * i), gb = Afun(fb) ** 2;
    const df = fb - fa, wa = (2 * Math.PI * fa) ** 2, wb = (2 * Math.PI * fb) ** 2;
    m0 += df * (ga + gb);              // trapecio: (ga + gb)/2·df, ×2 del espectro de dos lados
    m2 += df * (wa * ga + wb * gb);
    m4 += df * (wa * wa * ga + wb * wb * gb);
    fa = fb; ga = gb;
  }
  const arms = Math.sqrt(m0 / Tgm);
  const Nz = Math.sqrt(m2 / m0) * Tgm / Math.PI;
  const Ne = Math.max(Math.sqrt(m4 / m2) * Tgm / Math.PI, Nz);
  const xi = Nz / Ne;
  const zmax = Math.sqrt(Math.log(Math.max(Ne * xi, 1)) + 40);   // allí Ne·ξ·e^(−z²) < e^−40
  const nz = 4000, h = zmax / nz;
  const fz = (z) => -Math.expm1(Ne * Math.log1p(-xi * Math.exp(-z * z)));
  let s = fz(0) + fz(zmax);
  for (let i = 1; i < nz; i++) s += (i % 2 ? 4 : 2) * fz(i * h);   // Simpson
  const factorPico = Math.SQRT2 * s * h / 3;
  return { pga_g: factorPico * arms / G, a_rms_m_s2: arms, factor_pico: factorPico, Nz, Ne };
}

/**
 * Espectro de amplitud de Fourier objetivo en roca (Vs30 = 760 m/s) y en el suelo del sitio, en m/s (Boore 2003;
 * en la banda de transición, mezcla logarítmica del 7.4). `pgar_g`: PGA en roca (sin escalar) que fija la no
 * linealidad del suelo; si no se da, se usa el PGA esperado por vibración aleatoria (pgaRVT) del espectro en roca.
 * Como en sintetizar, la no linealidad usa pgar_g × p.escala_pgar. Para dibujar el objetivo de un registro ya
 * sintetizado se pasa pgar_g = registro.meta.pga_roca_g con los mismos p: así es exactamente el filtro que se aplicó.
 * → { roca: Float64Array, suelo: Float64Array, pgar_g, metodo_pgar: 'dado' | 'rvt', w_transicion, Tgm_s }
 */
export function espectroObjetivo(p, amenaza, f_Hz, { pgar_g } = {}) {
  const q = normalizarParametros(p, amenaza);
  const P = leerParametros(amenaza);
  const T = terminos(q, P);
  const Tgm = T.lista.reduce((s, x) => s + x.peso * x.Tgm, 0);
  const n = f_Hz.length;
  const roca = new Float64Array(n), suelo = new Float64Array(n);
  let metodo = 'dado';
  if (pgar_g === undefined || pgar_g === null) {
    const Aroca = (f) => Math.exp(lnAmplitudMezcla(T, P, f)) * 0.01;   // cm/s → m/s
    pgar_g = pgaRVT(Aroca, Tgm, 1 / (2 * P.comunes.dt)).pga_g;
    metodo = 'rvt';
  }
  if (!(pgar_g >= 0)) throw errorDatos(`espectroObjetivo: pgar_g = ${pgar_g} no válido`);
  const L = lnNoLineal(pgar_g * q.escala_pgar);
  for (let i = 0; i < n; i++) {
    const f = f_Hz[i];
    if (!(f > 0)) continue;              // f ≤ 0: amplitud 0 (el espectro de aceleración es ∝ f² cerca de 0)
    roca[i] = Math.exp(lnAmplitudMezcla(T, P, f)) * 0.01;
    const s = factorSueloCoef(P, f, q.vs30_m_s);
    suelo[i] = roca[i] * Math.exp(s.lin + s.f2 * L);
  }
  return { roca, suelo, pgar_g, metodo_pgar: metodo, w_transicion: T.w, Tgm_s: Tgm };
}

/** PGA esperado por RVT (g) en roca y en suelo para los parámetros p (para comparar con la síntesis). */
export function pgaEsperadoRVT(p, amenaza) {
  const q = normalizarParametros(p, amenaza);
  const P = leerParametros(amenaza);
  const T = terminos(q, P);
  const Tgm = T.lista.reduce((s, x) => s + x.peso * x.Tgm, 0);
  const fNyq = 1 / (2 * P.comunes.dt);
  const Ar = (f) => Math.exp(lnAmplitudMezcla(T, P, f)) * 0.01;
  const roca = pgaRVT(Ar, Tgm, fNyq);
  const L = lnNoLineal(roca.pga_g * q.escala_pgar);
  const As = (f) => { const s = factorSueloCoef(P, f, q.vs30_m_s); return Ar(f) * Math.exp(s.lin + s.f2 * L); };
  return { roca_g: roca.pga_g, suelo_g: pgaRVT(As, Tgm, fNyq).pga_g, Tgm_s: Tgm };
}

// ── Síntesis estocástica (Boore 2003) ────────────────────────────────────────────────────────────────────────
/** Ventana de Saragoni y Hart (1974) en la forma de Boore (2003): w(t) = a·(t/tη)^b·e^(−c·t/tη) en 0 ≤ t ≤ tη, con
 *  b = −ε·ln η/[1 + ε·(ln ε − 1)], c = b/ε y a = (e/ε)^b: máximo 1 en t = ε·tη y η del máximo en t = tη. */
function ventanaSaragoniHart(c) {
  const b = (-c.eps * Math.log(c.eta)) / (1 + c.eps * (Math.log(c.eps) - 1));
  const cc = b / c.eps;
  const aa = Math.pow(Math.E / c.eps, b);
  return (t, tEta) => {
    const x = t / tEta;
    return t < 0 || x > 1 ? 0 : aa * Math.pow(x, b) * Math.exp(-cc * x);
  };
}

let ultimoPlan = null;   // caché de un solo plan (mismos parámetros salvo la semilla: pruebas de conjunto)

/** Pasos 1 a 6 de las notas: régimen, distancias, M0 y f0, duración y ventana, malla de la FFT y espectro objetivo. */
function planSintesis(q, amenaza) {
  const clave = JSON.stringify([q.Mw, q.profundidad_km, q.distancia_epicentral_km, q.vs30_m_s, q.regimen]);
  if (ultimoPlan && ultimoPlan.amenaza === amenaza && ultimoPlan.clave === clave) return ultimoPlan;
  const P = leerParametros(amenaza);
  const c = P.comunes;
  const dt = c.dt;
  if (Math.abs(dt - DT_SINTESIS) > 1e-12) throw errorDatos(`amenaza.json pide dt = ${dt} s; el contrato fija ${DT_SINTESIS} s`);
  const T = terminos(q, P);
  const Tgm = T.lista.reduce((s, x) => s + x.peso * x.Tgm, 0);            // E15: Tgm lineal en w
  const tEta = c.fTgm * Tgm;                                              // tη = 2·Tgm
  const nw = Math.floor(tEta / dt + 0.5);                                 // round(tη/dt) (mitades hacia arriba)
  const f0min = Math.min(...T.lista.map((x) => x.f0));
  const tPad = Math.max(CONSTANTES_TIEMPO_COLA / (2 * Math.PI * f0min), COLA_MINIMA_S);
  const nPre = Math.ceil(tPad / dt);
  const N = siguientePotencia2(nPre + nw + Math.round(RELLENO_S / dt));
  const nReg = Math.min(N, nPre + nw + nPre);
  const vSH = ventanaSaragoniHart(c);
  const ventana = new Float64Array(nw);
  for (let i = 0; i < nw; i++) ventana[i] = vSH(i * dt, tEta);
  // Espectro objetivo en roca (m/s) y coeficientes del suelo en la malla f_k = k/(N·Δt), k = 0…N/2
  const M = N >> 1;
  const Aroca = new Float64Array(M + 1), lin = new Float64Array(M + 1), f2 = new Float64Array(M + 1);
  for (let k = 0; k <= M; k++) {
    const f = k === 0 ? F_CERO : k / (N * dt);
    Aroca[k] = Math.exp(lnAmplitudMezcla(T, P, f)) * 0.01;
    const s = factorSueloCoef(P, f, q.vs30_m_s);
    lin[k] = s.lin; f2[k] = s.f2;
  }
  ultimoPlan = { amenaza, clave, q, P, T, Tgm, tEta, nw, nPre, N, nReg, dt, ventana, Aroca, lin, f2, tPad };
  return ultimoPlan;
}

/** Paso 7: ruido gaussiano con ventana, FFT y normalización Zn = Z/√(media |Z|²) sobre los N/2 + 1 coeficientes. */
function ruidoNormalizado(plan, semilla) {
  const { nw, nPre, N, ventana } = plan;
  const ruido = normales(semilla, new Float64Array(nw));
  const x = new Float64Array(N);
  for (let i = 0; i < nw; i++) x[nPre + i] = ruido[i] * ventana[i];
  const Z = rfft(x, N);
  let s = 0;
  for (let k = 0; k < Z.re.length; k++) s += Z.re[k] * Z.re[k] + Z.im[k] * Z.im[k];
  const escala = 1 / Math.sqrt(s / Z.re.length);
  for (let k = 0; k < Z.re.length; k++) { Z.re[k] *= escala; Z.im[k] *= escala; }
  return Z;
}

/** Pasos 8 y 9: X_k = Zn_k·A(f_k)·factor_k/Δt y a = IFFT(X) (m/s²) en todo el búfer de N muestras. */
function pasada(plan, Zn, factor) {
  const { N, Aroca, dt } = plan;
  const M = N >> 1;
  const re = new Float64Array(M + 1), im = new Float64Array(M + 1);
  for (let k = 0; k <= M; k++) {
    const A = (factor ? Aroca[k] * factor[k] : Aroca[k]) / dt;
    re[k] = Zn.re[k] * A;
    im[k] = Zn.im[k] * A;
  }
  return irfft(re, im, N);
}

function maxAbs(a, n = a.length) {
  let m = 0;
  for (let i = 0; i < n; i++) { const v = Math.abs(a[i]); if (v > m) m = v; }
  return m;
}

/**
 * Sintetiza las dos componentes horizontales del movimiento en la superficie del sitio.
 * p: { Mw: 4..8, profundidad_km: 5..200, distancia_epicentral_km: 0..300, vs30_m_s: 150..760, semilla: entero,
 *      regimen?: 'auto'|'cortical'|'intraplaca_profunda', escala_pgar?: número (multiplica el PGA en roca de la
 *      pasada de suelo, para la escala «nsr10»; el registro NO se escala aquí) }
 * → Registro { dt, n, ax, ay (Float64Array, m/s²), meta, intensidades: { x, y }, avisos }
 */
export function sintetizar(p, amenaza) {
  const q = normalizarParametros(p, amenaza);
  const plan = planSintesis(q, amenaza);
  const { N, nReg, dt, T } = plan;
  const semillas = [q.semilla, q.semilla + 1];
  // Pasada en roca de las dos componentes (paso 8)
  const Zn = semillas.map((s) => ruidoNormalizado(plan, s));
  const roca = Zn.map((z) => pasada(plan, z, null));
  const pgaRoca = roca.map((a) => maxAbs(a) / G);
  const pgar = Math.sqrt(pgaRoca[0] * pgaRoca[1]);           // media geométrica (ver el encabezado)
  // Pasada en suelo con el mismo ruido normalizado (paso 9)
  const L = lnNoLineal(pgar * q.escala_pgar);
  const M = N >> 1;
  const factor = new Float64Array(M + 1);
  for (let k = 0; k <= M; k++) factor[k] = Math.exp(plan.lin[k] + plan.f2[k] * L);
  const suelo = Zn.map((z) => pasada(plan, z, factor));
  // Registro entregado: [0, nReg) del búfer; lo demás es la cola despreciable del filtro de fase cero
  let eTot = 0, eReg = 0;
  for (const a of suelo) for (let i = 0; i < N; i++) { const e = a[i] * a[i]; eTot += e; if (i < nReg) eReg += e; }
  const ax = suelo[0].slice(0, nReg), ay = suelo[1].slice(0, nReg);
  const R = resumenTerminos(T);
  const mom = momentoSismico(q.Mw);
  const meta = {
    M0_dina_cm: mom.M0_dina_cm, M0_N_m: mom.M0_N_m, energia_J_aprox: mom.energia_J_aprox,
    f0_Hz: R.f0_Hz, delta_sigma_bar: R.delta_sigma_bar, beta_s_km_s: R.beta_s_km_s, rho_s_g_cm3: R.rho_s_g_cm3,
    Q0: R.Q0, eta: R.eta, kappa0_s: R.kappa0_s,
    Rhip_km: Math.hypot(q.distancia_epicentral_km, q.profundidad_km), Ref_km: R.Ref_km,
    Tgm_s: plan.Tgm, t_eta_s: plan.tEta,
    regimen: T.lista.length === 2 ? 'transicion' : T.lista[0].regimen, w_transicion: T.w,
    regimen_pedido: q.regimen,
    pga_roca_g: pgar, pga_roca_x_g: pgaRoca[0], pga_roca_y_g: pgaRoca[1], escala_pgar: q.escala_pgar,
    vs30_m_s: q.vs30_m_s, semillas,
    terminos: T.lista.map((x) => ({
      regimen: x.regimen, peso: x.peso, f0_Hz: x.f0, delta_sigma_bar: x.dsigma, beta_s_km_s: x.t.beta, rho_s_g_cm3: x.t.rho,
      Q0: x.t.Q0, eta: x.t.etaQ, beta_Q_km_s: x.t.betaQ, kappa0_s: x.t.kappa, Ref_km: x.Ref, Z: x.Z,
      Tcamino_s: x.Tcamino, Tgm_s: x.Tgm, Fimp: x.t.fimp,
    })),
    t_inicio_ventana_s: plan.nPre * dt, n_fft: N, duracion_s: nReg * dt,
    fraccion_energia_fuera: eTot > 0 ? 1 - eReg / eTot : 0,
    nota_mezcla: T.lista.length === 2
      ? 'Banda de transición: f0, Δσ, βs, ρs, Q0 y Ref son medias geométricas ponderadas (solo para mostrar); κ0, η y Tgm, medias lineales. Cada término usa sus propios parámetros (ver terminos).'
      : undefined,
  };
  return {
    dt, n: nReg, ax, ay, meta,
    intensidades: { x: intensidades(ax, dt), y: intensidades(ay, dt) },
    avisos: avisos(q, amenaza),
  };
}

// ── Intensidades ─────────────────────────────────────────────────────────────────────────────────────────────
/** a en m/s², muestreada cada dt. Integración por trapecios desde reposo (v0 = d0 = 0), sin corrección de línea base.
 *  → { pga_g, pgv_cm_s, pgd_cm, arias_m_s, d595_s, t5_s, t95_s } (Arias = π/(2g)·∫a² dt). */
export function intensidades(a, dt) {
  const n = a.length;
  let pga = 0, v = 0, d = 0, pgv = 0, pgd = 0;
  const cum = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const ai = a[i];
    if (Math.abs(ai) > pga) pga = Math.abs(ai);
    if (i > 0) {
      const vn = v + 0.5 * (a[i - 1] + ai) * dt;
      d += 0.5 * (v + vn) * dt;
      v = vn;
      cum[i] = cum[i - 1] + 0.5 * (a[i - 1] * a[i - 1] + ai * ai) * dt;
    }
    if (Math.abs(v) > pgv) pgv = Math.abs(v);
    if (Math.abs(d) > pgd) pgd = Math.abs(d);
  }
  const tot = n ? cum[n - 1] : 0;
  const instante = (frac) => {
    if (!(tot > 0)) return 0;
    const meta = frac * tot;
    let i = 0;
    while (i < n - 1 && cum[i] < meta) i++;
    if (i === 0) return 0;
    const de = cum[i] - cum[i - 1];
    return (i - 1 + (de > 0 ? (meta - cum[i - 1]) / de : 0)) * dt;
  };
  const t5 = instante(0.05), t95 = instante(0.95);
  return { pga_g: pga / G, pgv_cm_s: pgv * 100, pgd_cm: pgd * 100, arias_m_s: (Math.PI / (2 * G)) * tot, d595_s: t95 - t5, t5_s: t5, t95_s: t95 };
}

// ── Espectro de respuesta (Nigam y Jennings, 1969) ───────────────────────────────────────────────────────────
/**
 * Respuesta máxima de osciladores lineales de un grado con amortiguamiento ξ a la aceleración a (m/s²), exacta si a
 * varía linealmente entre muestras (Nigam y Jennings, 1969): ü + 2ξωu̇ + ω²u = −a(t), u(0) = u̇(0) = 0. Después del
 * registro sigue la vibración libre durante un período amortiguado (el máximo de una vibración libre amortiguada está
 * en su primer medio ciclo), para no perder el pico que llega cuando ya se apagó el suelo.
 * → { Sa_g: Float64Array (pseudoaceleración ω²·max|u| en g), Sd_m: Float64Array (max|u| en m) }
 */
export function espectroRespuesta(a, dt, periodos, xi = 0.05) {
  if (!(xi >= 0 && xi < 1)) throw new Error(`espectroRespuesta: ξ = ${xi} fuera de [0, 1)`);
  const nT = periodos.length, n = a.length;
  const Sa_g = new Float64Array(nT), Sd_m = new Float64Array(nT);
  const raiz = Math.sqrt(1 - xi * xi);
  let pga = -1;
  for (let j = 0; j < nT; j++) {
    if (!(periodos[j] > 0)) {
      // T = 0: oscilador infinitamente rígido, u = 0 y su aceleración absoluta es la del suelo → Sa(0) = PGA
      if (!(periodos[j] === 0)) throw new Error(`espectroRespuesta: período ${periodos[j]} no válido`);
      if (pga < 0) { pga = 0; for (let i = 0; i < n; i++) pga = Math.max(pga, Math.abs(a[i])); }
      Sa_g[j] = pga / G;
      Sd_m[j] = 0;
      continue;
    }
    const w = (2 * Math.PI) / periodos[j];
    const wd = w * raiz;
    const E = Math.exp(-xi * w * dt), S = Math.sin(wd * dt), C = Math.cos(wd * dt);
    const r = xi / raiz;
    // Matriz de transición del estado (u, u̇) sin excitación
    const a11 = E * (r * S + C), a12 = (E * S) / wd;
    const a21 = (-w / raiz) * E * S, a22 = E * (C - r * S);
    // Respuesta a la excitación lineal entre a_i y a_{i+1} (solución particular de la rampa)
    const t1 = (2 * xi * xi - 1) / (w * w * dt), t2 = (2 * xi) / (w * w * w * dt);
    const b11 = E * ((t1 + xi / w) * S / wd + (t2 + 1 / (w * w)) * C) - t2;
    const b12 = -E * (t1 * S / wd + t2 * C) - 1 / (w * w) + t2;
    const b21 = E * ((t1 + xi / w) * (C - r * S) - (t2 + 1 / (w * w)) * (wd * S + xi * w * C)) + 1 / (w * w * dt);
    const b22 = -E * (t1 * (C - r * S) - t2 * (wd * S + xi * w * C)) - 1 / (w * w * dt);
    const extra = Math.ceil((2 * Math.PI) / wd / dt);
    let u = 0, v = 0, umax = 0;
    for (let i = 0; i < n - 1 + extra; i++) {
      const ai = i < n ? a[i] : 0, aj = i + 1 < n ? a[i + 1] : 0;
      const un = a11 * u + a12 * v + b11 * ai + b12 * aj;
      v = a21 * u + a22 * v + b21 * ai + b22 * aj;
      u = un;
      if (Math.abs(u) > umax) umax = Math.abs(u);
    }
    Sd_m[j] = umax;
    Sa_g[j] = (w * w * umax) / G;
  }
  return { Sa_g, Sd_m };
}

/** Períodos logarítmicos (n puntos de T1 a T2, incluidos los extremos). Por defecto los 60 de 0,02 a 5 s del 7.7. */
export function periodosLog(n = 60, T1 = 0.02, T2 = 5) {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) out[i] = T1 * Math.pow(T2 / T1, n === 1 ? 0 : i / (n - 1));
  return out;
}

// ── Espectro de Fourier ──────────────────────────────────────────────────────────────────────────────────────
/** |Δt·FFT(a)| con relleno de ceros hasta la potencia de 2 siguiente; f_k = k/(N·Δt), k = 1…N/2 (sin f = 0).
 *  → { f_Hz, A_m_s } (a en m/s² → amplitud en m/s). */
export function espectroFourier(a, dt) {
  const N = siguientePotencia2(Math.max(2, a.length));
  const X = rfft(a, N);
  const M = N >> 1;
  const f_Hz = new Float64Array(M), A_m_s = new Float64Array(M);
  for (let k = 1; k <= M; k++) {
    f_Hz[k - 1] = k / (N * dt);
    A_m_s[k - 1] = dt * Math.hypot(X.re[k], X.im[k]);
  }
  return { f_Hz, A_m_s };
}

// ── Calidad baja: FIR de fase cero a 20 Hz y diezmado ×2 ─────────────────────────────────────────────────────
// Ventana de Kaiser (Kaiser, 1974): banda de paso hasta 20 Hz con rizado ≤ 10⁻³ (0,1 %), banda de rechazo desde
// 30 Hz con ≥ 60 dB; la frecuencia de corte del seno cardinal ideal es el centro, 25 Hz. β = 0,1102·(A − 8,7) para
// A ≥ 50 dB y N − 1 = (A − 7,95)/(14,36·Δf/fs). Esas fórmulas son aproximadas (con A = 60 dB el rizado medido fue
// 1,1·10⁻³): se diseña con A = 65 dB (rizado esperado 10^(−65/20) = 5,6·10⁻⁴) y la prueba MOV4 mide la respuesta exacta
// del filtro contra 10⁻³ y 60 dB. Al diezmar a Δt = 0,01 s (Nyquist 50 Hz) solo se repliega lo que está sobre 50 Hz,
// que el filtro ya bajó más de 60 dB; la banda útil (≤ 20 Hz, T ≥ 0,05 s) queda intacta.
const FIR = { fPaso: 20, fRechazo: 30, atenuacion_dB: 65 };
const CACHE_FIR = new Map();

function besselI0(x) {
  // I0(x) = Σ ((x/2)^k / k!)²; converge rápido para x ≤ 10
  let s = 1, t = 1;
  for (let k = 1; k < 60; k++) {
    t *= (x / (2 * k)) * (x / (2 * k));
    s += t;
    if (t < 1e-17 * s) break;
  }
  return s;
}

/** Coeficientes del FIR de calidad baja para un paso dt (simétricos: h[L + k] = h[L − k], suma 1). */
export function coeficientesFIR(dt) {
  let h = CACHE_FIR.get(dt);
  if (h) return h;
  const fs = 1 / dt;
  if (FIR.fRechazo > fs / 4 + 1e-9) throw new Error(`filtrarYDiezmar: con dt = ${dt} s el diezmado ×2 replegaría la banda de 20-30 Hz`);
  const A = FIR.atenuacion_dB;
  const beta = 0.1102 * (A - 8.7);
  const df = (FIR.fRechazo - FIR.fPaso) / fs;
  let largo = Math.ceil((A - 7.95) / (14.36 * df)) + 1;
  if (largo % 2 === 0) largo++;                      // tipo I: largo impar, retardo entero (L muestras)
  const L = (largo - 1) / 2;
  const fc = (FIR.fPaso + FIR.fRechazo) / 2 / fs;    // ciclos por muestra
  h = new Float64Array(largo);
  const i0b = besselI0(beta);
  let suma = 0;
  for (let k = -L; k <= L; k++) {
    const ideal = k === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * k) / (Math.PI * k);
    const r = k / L;
    const kaiser = besselI0(beta * Math.sqrt(Math.max(0, 1 - r * r))) / i0b;
    h[k + L] = ideal * kaiser;
    suma += h[k + L];
  }
  for (let i = 0; i < largo; i++) h[i] /= suma;      // ganancia exacta 1 en f = 0
  CACHE_FIR.set(dt, h);
  return h;
}

/** FIR pasabajos de fase cero (centrado) y una de cada dos muestras. Fuera del registro la señal vale 0.
 *  → { a: Float64Array (ceil(n/2) muestras), dt: 2·dt } */
export function filtrarYDiezmar(a, dt) {
  const h = coeficientesFIR(dt);
  const L = (h.length - 1) >> 1;
  const n = a.length, m = Math.ceil(n / 2);
  const out = new Float64Array(m);
  for (let j = 0; j < m; j++) {
    const c = 2 * j;
    let s = 0;
    const k0 = Math.max(-L, c - (n - 1)), k1 = Math.min(L, c);
    for (let k = k0; k <= k1; k++) s += h[k + L] * a[c - k];
    out[j] = s;
  }
  return { a: out, dt: 2 * dt };
}

// ── Espectro elástico de la NSR-10 ───────────────────────────────────────────────────────────────────────────
/**
 * Sa (g) del espectro elástico de diseño de la NSR-10 (A.2.6; amenaza.json → nsr10.espectro_elastico):
 * T ≤ TC: 2,5·Aa·Fa·I; TC < T ≤ TL: 1,2·Av·Fv·I/T; T > TL: 1,2·Av·Fv·TL·I/T²; TC = 0,48·Av·Fv/(Aa·Fa), TL = 2,4·Fv.
 * Con rama_corta = true, para T < T0 = 0,10·Av·Fv/(Aa·Fa) usa la rama del análisis dinámico 2,5·Aa·Fa·I·(0,4 + 0,6·T/T0).
 * T número → número; T arreglo → Float64Array.
 */
export function espectroNSR10(T, { Aa, Av, Fa, Fv, I = 1, rama_corta = false }) {
  const TC = (0.48 * Av * Fv) / (Aa * Fa), TL = 2.4 * Fv, T0 = (0.1 * Av * Fv) / (Aa * Fa);
  const meseta = 2.5 * Aa * Fa * I;
  const uno = (t) => {
    if (rama_corta && t < T0) return meseta * (0.4 + (0.6 * t) / T0);
    if (t <= TC) return meseta;
    if (t <= TL) return (1.2 * Av * Fv * I) / t;
    return (1.2 * Av * Fv * TL * I) / (t * t);
  };
  if (typeof T === 'number') return uno(T);
  const out = new Float64Array(T.length);
  for (let i = 0; i < T.length; i++) out[i] = uno(T[i]);
  return out;
}

/**
 * Espectro del umbral de daño (NSR-10 A.12.3; ξ = 2 %, sin I), el mismo con que el prediseño revisa la deriva ≤ 0,4 %
 * del grupo IV (scripts/sismo/estructura_torre.py, espectro_umbral): meseta 3,0·Ad·Fa hasta TC = 0,5·Fv/Fa y
 * 1,5·Ad·Fv/T después. Es la forma de la NSR-98 (3,0·Ad y 1,5·Ad·S/T) con los coeficientes de sitio de la NSR-10:
 * 3,0 = 2,5·1,2 y 1,5 = 1,2·1,25 son la meseta y la rama del espectro de diseño llevadas de 5 % a 2 % de
 * amortiguamiento. Texto exacto de A.12.3 por confirmar. Por ser de 2 %, no se compara a la par con un espectro del
 * registro calculado con 5 %.
 */
export const XI_UMBRAL_DANO = 0.02;
export function espectroUmbralDano(T, { Ad, Fa, Fv }) {
  const TC = (0.5 * Fv) / Fa;
  const uno = (t) => (t <= TC ? 3.0 * Ad * Fa : (1.5 * Ad * Fv) / t);
  if (typeof T === 'number') return uno(T);
  const out = new Float64Array(T.length);
  for (let i = 0; i < T.length; i++) out[i] = uno(T[i]);
  return out;
}

// ── Ecuaciones de predicción (GMPE) ──────────────────────────────────────────────────────────────────────────
// Coeficientes copiados con exactitud de data/sismo/amenaza.json → gmpe (la prueba T13 los compara número a número
// con el archivo). Solo hay filas para PGA, 0,2, 0,5 y 1,0 s: gmpe() da PGA para T ≤ 0,01 s (incluido T = 0), los
// valores exactos en 0,2, 0,5 y 1,0 s, interpola ln Sa y σ linealmente en ln T entre 0,2 y 1,0 s (amenaza.json →
// gmpe.otras_periodos) y devuelve NaN fuera de eso: entre 0,01 y 0,2 s la meseta de las GMPE no se puede
// reconstruir con PGA y 0,2 s sin inventarla.
export const GMPE_COEF = {
  bchydro2016_intraslab: {
    columnas: ['IMT', 'Vlin', 'b', 'theta1', 'theta2', 'theta6', 'theta7', 'theta8', 'theta10', 'theta11', 'theta12', 'theta13', 'theta14', 'phi', 'tau', 'sigma'],
    coeficientes: [
      ['PGA', 865.1, -1.186, 4.2203, -1.35, -0.0012, 1.0988, -1.42, 3.12, 0.013, 0.98, -0.0135, -0.4, 0.6, 0.43, 0.74],
      ['0.2', 748.2, -2.188, 5.2684, -1.4, -0.0018, 1.1648, -1.49, 3.03, 0.0129, 2.076, -0.0162, -0.35, 0.6, 0.43, 0.74],
      ['0.5', 456.6, -2.669, 4.0181, -1.08, -0.0044, 0.5799, -0.82, 1.92, 0.0125, 2.399, -0.0231, -0.19, 0.6, 0.43, 0.74],
      ['1.0', 400.0, -1.955, 2.7981, -0.85, -0.0062, 0.1746, -0.34, 1.1, 0.0114, 1.47, -0.0363, -0.07, 0.6, 0.43, 0.74],
    ],
    constantes: { n: 1.18, c: 1.88, theta3: 0.1, theta4: 0.9, theta5: 0.0, theta9: 0.4, c4: 10.0, C1: 7.8, DeltaC1_intraplaca: -0.3 },
  },
  zhao2006_intraslab: {
    columnas: ['IMT', 'a', 'b', 'c', 'd', 'e', 'CH', 'C1', 'C2', 'C3', 'C4', 'sigma', 'SS', 'SSL', 'PS', 'QS', 'WS', 'tauS'],
    coeficientes: [
      ['PGA', 1.101, -0.00564, 0.0055, 1.08, 0.01412, 0.293, 1.111, 1.344, 1.355, 1.42, 0.604, 2.607, -0.528, 0.1392, 0.1584, -0.0529, 0.321],
      ['0.2', 1.147, -0.00659, 0.012, 1.014, 0.01462, 1.28, 1.669, 2.085, 2.001, 2.03, 0.692, 1.901, -0.372, 0.1631, 0.1856, -0.0644, 0.324],
      ['0.5', 1.25, -0.00338, 0.006, 1.008, 0.01114, -0.207, 0.071, 0.515, 0.934, 0.955, 0.653, 2.629, -0.554, 0.1381, 0.1078, -0.0008, 0.272],
      ['1.0', 1.479, -0.0022, 0.002, 1.115, 0.01005, -2.451, -2.152, -1.776, -1.523, -1.084, 0.657, 2.233, -0.509, 0.106, 0.0314, 0.0498, 0.286],
    ],
  },
  zhao2006_cortical: {
    columnas: ['IMT', 'FR', 'QC', 'WC', 'tauC'],
    coeficientes: [
      ['PGA', 0.251, 0.0, 0.0, 0.303],
      ['0.2', 0.26, 0.0, 0.0, 0.312],
      ['0.5', 0.247, -0.0126, 0.0116, 0.338],
      ['1.0', 0.211, -0.0899, 0.044, 0.338],
    ],
  },
  bssa14: {
    columnas: ['IMT', 'e0', 'e1', 'e2', 'e3', 'e4', 'e5', 'e6', 'Mh', 'c1', 'c2', 'c3', 'h', 'c', 'Vc', 'f4', 'f5', 'R1', 'R2', 'DphiR', 'DphiV', 'phi1', 'phi2', 'tau1', 'tau2'],
    coeficientes: [
      ['PGA', 0.4473, 0.4856, 0.2459, 0.4539, 1.431, 0.05053, -0.1662, 5.5, -1.134, 0.1917, -0.008088, 4.5, -0.6, 1500.0, -0.15, -0.00701, 110.0, 270.0, 0.1, 0.07, 0.695, 0.495, 0.398, 0.348],
      ['0.2', 1.3255, 1.359, 1.122, 1.3414, 1.1349, -0.11096, -0.15852, 5.92, -1.0607, 0.14489, -0.007717, 4.61, -0.68762, 1392.61, -0.24658, -0.00614, 90.91, 270.0, 0.136, 0.045, 0.711, 0.539, 0.344, 0.309],
      ['0.5', 0.96991, 0.99106, 0.7615, 1.012, 1.0384, -0.23522, 0.029119, 6.2, -1.1459, 0.12015, -0.00322, 5.34, -0.9693, 1203.91, -0.175, -0.00744, 105.54, 265.0, 0.109, 0.06, 0.615, 0.599, 0.41, 0.224],
      ['1.0', 0.3932, 0.4218, 0.207, 0.4124, 1.5004, -0.18983, 0.17895, 6.2, -1.193, 0.10248, -0.00121, 5.74, -1.05, 1109.95, -0.10521, -0.00844, 116.39, 270.0, 0.098, 0.02, 0.553, 0.625, 0.498, 0.298],
    ],
  },
};

const NOMBRES_GMPE = {
  bchydro2016_intraslab: 'BC Hydro 2016 (intraplaca)',
  zhao2006_intraslab: 'Zhao et al. 2006 (intraplaca)',
  zhao2006_cortical: 'Zhao et al. 2006 (cortical)',
  bssa14: 'BSSA14 (cortical)',
};

/** Fila de coeficientes como objeto { columna: valor }. */
function fila(modelo, imt) {
  const t = GMPE_COEF[modelo];
  const f = t.coeficientes.find((r) => r[0] === imt);
  const o = {};
  t.columnas.forEach((c, i) => { o[c] = f[i]; });
  return o;
}

// BC Hydro 2016 (Abrahamson, Gregor y Addo), intraplaca (Fevent = 1), fFABA = 0 salvo trasarco.
function bchydro(imt, M, R, Zh, vs30, trasarco) {
  const K = GMPE_COEF.bchydro2016_intraslab.constantes;
  const dC1 = K.DeltaC1_intraplaca;
  const nucleo = (C) => {
    const Mc = K.C1 + dC1;
    const fmag = (M <= Mc ? K.theta4 : K.theta5) * (M - Mc) + C.theta13 * (10 - M) ** 2;
    const fdist = (C.theta2 + C.theta14 + K.theta3 * (M - 7.8)) * Math.log(R + K.c4 * Math.exp((M - 6) * K.theta9)) + C.theta6 * R + C.theta10;
    const fdepth = C.theta11 * (Math.min(Zh, 120) - 60);
    const ffaba = trasarco ? C.theta7 + C.theta8 * Math.log(Math.max(R, 85) / 40) : 0;
    return C.theta1 + K.theta4 * dC1 + fmag + fdist + fdepth + ffaba;
  };
  const Cp = fila('bchydro2016_intraslab', 'PGA');
  const pga1000 = Math.exp(nucleo(Cp) + (Cp.theta12 + Cp.b * K.n) * Math.log(1000 / Cp.Vlin));
  const C = fila('bchydro2016_intraslab', imt);
  const vs = Math.min(vs30, 1000);
  const fsite = vs30 < C.Vlin
    ? C.theta12 * Math.log(vs / C.Vlin) - C.b * Math.log(pga1000 + K.c) + C.b * Math.log(pga1000 + K.c * (vs / C.Vlin) ** K.n)
    : (C.theta12 + C.b * K.n) * Math.log(vs / C.Vlin);
  return { ln: nucleo(C) + fsite, sigma: C.sigma };
}

// Zhao et al. (2006): intraplaca y cortical (ln y en cm/s²; se pasa a g con g = 980,665 cm/s²).
function zhao(imt, M, x, h, vs30, intraplaca, inversa) {
  const C = fila('zhao2006_intraslab', imt);
  const xx = Math.max(x, 0.1);
  const r = xx + C.c * Math.exp(C.d * M);
  const hh = Math.min(h, 125), hc = 15;
  const prof = hh >= hc ? C.e * (hh - hc) : 0;
  const Ck = vs30 > 1100 ? C.CH : vs30 > 600 ? C.C1 : vs30 > 300 ? C.C2 : vs30 > 200 ? C.C3 : C.C4;
  let ln = C.a * M + C.b * xx - Math.log(r) + prof + Ck, tau;
  if (intraplaca) {
    ln += C.SS + C.SSL * Math.log(xx) + C.PS * (M - 6.5) + C.QS * (M - 6.5) ** 2 + C.WS;
    tau = C.tauS;
  } else {
    const K = fila('zhao2006_cortical', imt);
    ln += (inversa ? K.FR : 0) + K.QC * (M - 6.3) ** 2 + K.WC;
    tau = K.tauC;
  }
  return { ln: ln - Math.log(G * 100), sigma: Math.sqrt(C.sigma ** 2 + tau ** 2) };
}

// BSSA14 (Boore, Stewart, Seyhan y Atkinson 2014), sin término de cuenca, Δc3 = 0 (global).
function bssa14(imt, M, Rjb, vs30, mecanismo) {
  const roca = (C) => {
    const e = { U: C.e0, SS: C.e1, NS: C.e2, RS: C.e3 }[mecanismo];
    if (e === undefined) throw errorDatos(`BSSA14: mecanismo ${mecanismo} no es U, SS, NS ni RS`);
    const FE = M <= C.Mh ? e + C.e4 * (M - C.Mh) + C.e5 * (M - C.Mh) ** 2 : e + C.e6 * (M - C.Mh);
    const R = Math.hypot(Rjb, C.h);
    return FE + (C.c1 + C.c2 * (M - 4.5)) * Math.log(R / 1) + C.c3 * (R - 1);
  };
  const pgar = Math.exp(roca(fila('bssa14', 'PGA')));
  const C = fila('bssa14', imt);
  const Flin = C.c * Math.log(Math.min(vs30, C.Vc) / VREF_BSSA);
  const f2 = C.f4 * (Math.exp(C.f5 * (Math.min(vs30, VREF_BSSA) - 360)) - Math.exp(C.f5 * (VREF_BSSA - 360)));
  const Fnl = f2 * lnNoLineal(pgar);
  const tau = M <= 4.5 ? C.tau1 : M >= 5.5 ? C.tau2 : C.tau1 + (C.tau2 - C.tau1) * (M - 4.5);
  let phi = M <= 4.5 ? C.phi1 : M >= 5.5 ? C.phi2 : C.phi1 + (C.phi2 - C.phi1) * (M - 4.5);
  if (Rjb > C.R2) phi += C.DphiR;
  else if (Rjb > C.R1) phi += C.DphiR * Math.log(Rjb / C.R1) / Math.log(C.R2 / C.R1);
  if (vs30 <= 225) phi -= C.DphiV;
  else if (vs30 <= 300) phi -= C.DphiV * Math.log(300 / vs30) / Math.log(300 / 225);
  return { ln: roca(C) + Flin + Fnl, sigma: Math.hypot(tau, phi) };
}

function evaluarIMT(modelo, imt, e) {
  switch (modelo) {
    case 'bchydro2016_intraslab': return bchydro(imt, e.Mw, e.Rhip, e.h, e.vs30, e.trasarco);
    case 'zhao2006_intraslab': return zhao(imt, e.Mw, e.Rrup, e.h, e.vs30, true, false);
    case 'zhao2006_cortical': return zhao(imt, e.Mw, e.Rrup, e.h, e.vs30, false, e.inversa);
    case 'bssa14': return bssa14(imt, e.Mw, e.Rjb, e.vs30, e.mecanismo);
    default: throw errorDatos(`GMPE desconocida: ${modelo}`);
  }
}

/**
 * Mediana (g) y σ (ln) de una GMPE en los períodos pedidos.
 * modelo: 'bchydro2016_intraslab' | 'zhao2006_intraslab' | 'zhao2006_cortical' | 'bssa14'
 * esc: { Mw, profundidad_km, distancia_epicentral_km, vs30_m_s, Rhip_km?, Rrup_km?, Rjb_km?, mecanismo? = 'U',
 *        trasarco? = false, inversa? = false }. Distancias de fuente puntual por defecto (amenaza.json → gmpe):
 *        BC Hydro con la hipocentral; Zhao con la hipocentral como distancia a la ruptura; BSSA14 con Rjb ≈ epicentral.
 * → { mediana_g: Float64Array, sigma_ln: Float64Array } (NaN donde no hay coeficientes; ver arriba)
 */
export function gmpe(modelo, esc, periodos) {
  if (!GMPE_COEF[modelo]) throw errorDatos(`GMPE desconocida: ${modelo}`);
  const h = esc.profundidad_km, Repi = esc.distancia_epicentral_km;
  const Rhip = esc.Rhip_km ?? Math.hypot(Repi, h);
  const e = {
    Mw: esc.Mw, h, vs30: esc.vs30_m_s, Rhip, Rrup: esc.Rrup_km ?? Rhip, Rjb: esc.Rjb_km ?? Repi,
    mecanismo: esc.mecanismo ?? 'U', trasarco: !!esc.trasarco, inversa: !!esc.inversa,
  };
  // Cada modelo pide solo sus datos: BC Hydro, Rhip y h; Zhao, Rrup y h; BSSA14, Rjb (sin profundidad).
  const necesita = { bchydro2016_intraslab: ['Rhip', 'h'], zhao2006_intraslab: ['Rrup', 'h'], zhao2006_cortical: ['Rrup', 'h'], bssa14: ['Rjb'] }[modelo];
  for (const k of ['Mw', 'vs30', ...necesita]) {
    if (!Number.isFinite(e[k])) throw errorDatos(`gmpe (${modelo}): ${k} = ${e[k]} no es un número finito`);
  }
  const tabla = [['PGA', 0.01], ['0.2', 0.2], ['0.5', 0.5], ['1.0', 1.0]];
  const memo = new Map();
  const imtEn = (imt) => { if (!memo.has(imt)) memo.set(imt, evaluarIMT(modelo, imt, e)); return memo.get(imt); };
  const n = periodos.length;
  const mediana_g = new Float64Array(n), sigma_ln = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const T = periodos[i];
    let ln = NaN, s = NaN;
    if (!(T >= 0)) throw errorDatos(`gmpe: período ${T} no válido`);
    if (T <= 0.01) ({ ln, sigma: s } = imtEn('PGA'));
    else if (T >= 0.2 - 1e-12 && T <= 1.0 + 1e-12) {
      let j = 1;
      while (j < tabla.length - 2 && T > tabla[j + 1][1]) j++;
      const [ia, Ta] = tabla[j], [ib, Tb] = tabla[j + 1];
      const A = imtEn(ia), B = imtEn(ib);
      const u = (Math.log(T) - Math.log(Ta)) / (Math.log(Tb) - Math.log(Ta));
      ln = A.ln + u * (B.ln - A.ln);
      s = A.sigma + u * (B.sigma - A.sigma);
    }
    mediana_g[i] = Math.exp(ln);
    sigma_ln[i] = s;
  }
  return { mediana_g, sigma_ln };
}

/**
 * Fracción de su parte que conserva BSSA14 según la profundidad (regla del motor, revisión A6): 1 hasta 15 km,
 * 0 desde 25 km, lineal entre. BSSA14 se ajustó con sismos corticales someros de NGA-West2 (focos de hasta ≈ 20 km;
 * por confirmar) y no tiene término de profundidad: su distancia es √(Rjb² + h_coef²) con una seudoprofundidad fija
 * (4,5 km para el PGA) y, con Rjb ≈ Repi, da lo mismo para un foco a 10 que a 65 km. Lo que pierde pasa a Zhao 2006
 * cortical, que sí tiene término de profundidad y usa la hipocentral. La rampa evita otro salto con h.
 */
const BSSA14_PROF = { plena_km: 15, nula_km: 25 };
export function fraccionBSSA14(h_km) {
  return clamp((BSSA14_PROF.nula_km - h_km) / (BSSA14_PROF.nula_km - BSSA14_PROF.plena_km), 0, 1);
}

/**
 * GMPE del escenario con su peso (para la gráfica de espectros): las de cada régimen de
 * amenaza.json → seleccion_de_regimen.gmpe_por_regimen, con peso (1 − w)/2 las corticales y w/2 las intraplaca
 * (w de E15, o 0/1 si el régimen está forzado). BSSA14 conserva solo fraccionBSSA14(h) de su parte y el resto va a
 * las demás corticales (Zhao 2006 cortical). Se omiten las de peso 0.
 * → [{ nombre, modelo, regimen, peso, T, mediana_g, sigma_ln }]
 */
export function gmpeEscenario(p, amenaza, periodos = PERIODOS_GMPE_S) {
  const q = normalizarParametros(p, amenaza);
  const w = q.regimen === 'cortical' ? 0 : q.regimen === 'intraplaca_profunda' ? 1 : regimenPorProfundidad(q.profundidad_km).w;
  const porRegimen = amenaza.seleccion_de_regimen?.gmpe_por_regimen ?? {
    cortical: ['bssa14', 'zhao2006_cortical'], intraplaca_profunda: ['bchydro2016_intraslab', 'zhao2006_intraslab'],
  };
  const out = [];
  for (const [regimen, pesoRegimen] of [['cortical', 1 - w], ['intraplaca_profunda', w]]) {
    if (!(pesoRegimen > 0)) continue;
    const lista = porRegimen[regimen];
    const base = pesoRegimen / lista.length;
    const otras = lista.filter((m) => m !== 'bssa14').length;
    const fB = lista.includes('bssa14') && otras > 0 ? fraccionBSSA14(q.profundidad_km) : 1;
    for (const modelo of lista) {
      const peso = modelo === 'bssa14' ? base * fB : base + (lista.includes('bssa14') ? (base * (1 - fB)) / otras : 0);
      if (!(peso > 0)) continue;
      const r = gmpe(modelo, q, periodos);
      out.push({ nombre: NOMBRES_GMPE[modelo], modelo, regimen, peso, T: Float64Array.from(periodos), ...r });
    }
  }
  return out;
}

// ── Avisos ───────────────────────────────────────────────────────────────────────────────────────────────────
// Las reglas de amenaza.json → controles.avisos_de_combinacion vienen como texto («profundidad ≥ 50 km y (… o …)»).
// Se leen con un analizador pequeño (y = conjunción, o = disyunción, paréntesis, «X entre a y b» con los extremos
// incluidos, comparadores ≥ ≤ < > =, decimales con punto o coma, unidades km y m/s que se ignoran). Una regla que no
// se pueda leer lanza un error: mejor fallar que callar un aviso.
const VARIABLES = { profundidad: 'profundidad_km', distancia: 'distancia_epicentral_km', Mw: 'Mw', vs30: 'vs30_m_s', Vs30: 'vs30_m_s' };
const UNIDADES = new Set(['km', 'm/s']);
const CACHE_REGLAS = new Map();

function compilarCondicion(texto) {
  if (CACHE_REGLAS.has(texto)) return CACHE_REGLAS.get(texto);
  const tok = texto.replace(/\(/g, ' ( ').replace(/\)/g, ' ) ').replace(/(≥|≤|>=|<=)/g, ' $1 ').replace(/([^<>≥≤=])([<>=])(?!=)/g, '$1 $2 ')
    .split(/\s+/).filter(Boolean);
  let i = 0;
  const falla = (m) => { throw new Error(`avisos: no se pudo leer la regla «${texto}» (${m})`); };
  const numero = () => {
    const t = tok[i++];
    const v = Number(String(t).replace(',', '.'));
    if (!Number.isFinite(v)) falla(`se esperaba un número y llegó «${t}»`);
    if (UNIDADES.has(tok[i])) i++;
    return v;
  };
  const OPS = { '≥': (a, b) => a >= b, '>=': (a, b) => a >= b, '≤': (a, b) => a <= b, '<=': (a, b) => a <= b, '<': (a, b) => a < b, '>': (a, b) => a > b, '=': (a, b) => a === b };
  function factor() {
    if (tok[i] === '(') { i++; const e = expr(); if (tok[i++] !== ')') falla('falta «)»'); return e; }
    const v = VARIABLES[tok[i]];
    if (!v) falla(`variable desconocida «${tok[i]}»`);
    i++;
    if (tok[i] === 'entre') {
      i++;
      const a = numero();
      if (tok[i++] !== 'y') falla('«entre a y b» sin «y»');
      const b = numero();
      return (q) => q[v] >= Math.min(a, b) && q[v] <= Math.max(a, b);
    }
    const op = OPS[tok[i++]];
    if (!op) falla(`comparador desconocido «${tok[i - 1]}»`);
    const b = numero();
    return (q) => op(q[v], b);
  }
  function termino() {
    const fs = [factor()];
    while (tok[i] === 'y') { i++; fs.push(factor()); }
    return (q) => fs.every((f) => f(q));
  }
  function expr() {
    const ts = [termino()];
    while (tok[i] === 'o') { i++; ts.push(termino()); }
    return (q) => ts.some((t) => t(q));
  }
  const fn = expr();
  if (i !== tok.length) falla(`sobra «${tok.slice(i).join(' ')}»`);
  CACHE_REGLAS.set(texto, fn);
  return fn;
}

/** Avisos de combinación (amenaza.json → controles.avisos_de_combinacion), de régimen forzado incompatible y de la
 *  banda de transición E15. → string[] */
export function avisos(p, amenaza) {
  const q = normalizarParametros(p, amenaza);
  const out = [];
  const reglas = amenaza.controles?.avisos_de_combinacion?.reglas ?? [];
  for (const r of reglas) if (compilarCondicion(r.si)(q)) out.push(r.aviso);
  const h = q.profundidad_km;
  if (q.regimen === 'intraplaca_profunda' && h < 40) {
    out.push(`Régimen intraplaca forzado con h < 40 km (h = ${coma(h, 0)} km): a esa profundidad el foco estaría en la corteza, no dentro de la placa que se hunde. Escenario hipotético.`);
  }
  if (q.regimen === 'cortical' && h > 60) {
    out.push(`Régimen cortical forzado con h > 60 km (h = ${coma(h, 0)} km): la corteza bajo el Magdalena Medio tiene del orden de 30-45 km (por confirmar). Escenario hipotético.`);
  }
  {
    const w = q.regimen === 'cortical' ? 0 : q.regimen === 'intraplaca_profunda' ? 1 : regimenPorProfundidad(h).w;
    const fB = fraccionBSSA14(h);
    if (w < 1 && fB < 1) {
      out.push(`BSSA14 fuera de su rango de profundidad (sismos corticales someros, sin término de profundidad): con h = ${coma(h, 0)} km pesa ${coma(100 * fB, 0)} % de su parte en la comparación con las GMPE y el resto pasa a Zhao 2006 cortical (rango de 15 a 25 km por confirmar).`);
    }
  }
  if (q.regimen === 'auto') {
    const { w } = regimenPorProfundidad(h);
    if (w > 0 && w < 1) {
      out.push(`Banda de transición corteza-placa (40-70 km): el espectro mezcla los dos regímenes, ${coma(100 * (1 - w), 0)} % cortical y ${coma(100 * w, 0)} % intraplaca (cambio E15). La profundidad cambia la distancia al foco y el tipo de sismo.`);
    }
  }
  return [...new Set(out)];
}

// ── Para las pruebas (scripts/sismo/pruebas/movimiento.mjs) ──────────────────────────────────────────────────
/** Funciones internas expuestas solo para comprobarlas contra los fragmentos de amenaza.json → notas_para_implementar. */
export const __pruebas = {
  dispersionGeometrica,
  tcaminoBT14: (R, amenaza) => tcaminoBT14(R, leerParametros(amenaza).cortical),
  ventana: (t, tEta, amenaza) => ventanaSaragoniHart(leerParametros(amenaza).comunes)(t, tEta),
  constantes: { BRUNE_F0, MW_A_M0, H_FF, BT14_MAS_ALLA, TCAMINO_INTRAPLACA_B, IMPEDANCIA_REF, RELLENO_S, F_CERO, PGA_BSSA_F3 },
  compilarCondicion,
};
