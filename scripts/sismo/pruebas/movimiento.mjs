// Pruebas del movimiento del suelo: web/js/sismo/movimiento.js, fft.js y azar.js (contrato de integración, 7.8:
// T13, T14, T15, T15b, T15c, T16, T19 y T20; más MOV1-MOV5, propias de este módulo).
//
// Referencias independientes que usan:
//   - amenaza.json (coeficientes de las GMPE, valores de prueba, escenarios calculados por la investigación);
//   - data/sismo/fuentes_investigacion/gmpe.py (transcripción de las GMPE hecha por la investigación desde OpenQuake,
//     con sus propias copias de los coeficientes): se llama con el python3 del sistema;
//   - scripts/sismo/estocastico.py (referencia en Python, solo biblioteca estándar; a su vez se valida contra numpy
//     y contra sim.py de la investigación con `--validar`);
//   - soluciones cerradas (DFT directa, escalón en un oscilador, seno) y el método del espectro por FFT.
// Variable de entorno PYTHON: intérprete para T13 y T15b (por defecto python3).

import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';
import { availableParallelism } from 'node:os';
import { RAIZ, leerJSON, errorRelativo, caso, comprobar } from './_util.mjs';
import * as MOV from '../../../web/js/sismo/movimiento.js';
import { rfft, irfft, siguientePotencia2 } from '../../../web/js/sismo/fft.js';
import { mulberry32, normales } from '../../../web/js/sismo/azar.js';

const amenaza = leerJSON('data/sismo/amenaza.json');
const G = 9.80665;
const PY = process.env.PYTHON || 'python3';
const ruta = (r) => fileURLToPath(new URL(r, RAIZ));

// ── Ayudantes ─────────────────────────────────────────────────────────────────────────────────────────────────
/** Parámetros de un escenario de amenaza.json (Vs30 270 m/s, el del sitio). */
function escenario(id, extra = {}) {
  const e = amenaza.escenarios.find((x) => x.id === id);
  if (!e) throw new Error(`escenario ${id} no está en amenaza.json`);
  return { Mw: e.Mw, profundidad_km: e.profundidad_km, distancia_epicentral_km: e.distancia_epicentral_km, vs30_m_s: 270, ...extra };
}

const mediaGeometrica = (v) => Math.exp(v.reduce((s, x) => s + Math.log(x), 0) / v.length);

/** Corre un guion de Python con JSON por la entrada estándar y devuelve el JSON de la salida. */
function python(args, entrada) {
  const r = spawnSync(PY, ['-I', ...args], { input: JSON.stringify(entrada), encoding: 'utf8', maxBuffer: 1 << 28 });
  if (r.error) throw new Error(`no se pudo correr ${PY} (${r.error.message}); defina PYTHON con un Python ≥ 3.11`);
  if (r.status !== 0) throw new Error(`${PY} ${args.join(' ')} salió con código ${r.status}: ${r.stderr.slice(-600)}`);
  return JSON.parse(r.stdout);
}
const estocastico = (consultas) => python([ruta('scripts/sismo/estocastico.py'), '--consultas'], consultas);

/** Máximo del error relativo entre dos listas (0/0 cuenta como 0). */
function errorRelativoMax(a, b) {
  let m = 0;
  for (let i = 0; i < b.length; i++) m = Math.max(m, a[i] === b[i] ? 0 : errorRelativo(a[i], b[i]));
  return m;
}

/** Sa (g) por FFT: u(f) = H(f)·A(f), H = −1/(ωn² − ω² + 2iξωnω), con N ≥ 9·n (relleno de ceros ≥ 8 veces la duración,
 *  para que la vibración libre no dé la vuelta al búfer circular). Supone el registro limitado en banda (interpolación
 *  sinc entre muestras), mientras que Nigam y Jennings lo suponen lineal por tramos: en la frecuencia f del oscilador
 *  la diferencia esperada es del orden de 1 − sinc²(f·Δt) (0,8 % en T = 0,1 s con Δt = 0,005 s; deducción propia). */
function espectroPorFFT(a, dt, periodos, xi = 0.05) {
  const N = siguientePotencia2(9 * a.length);
  const X = rfft(a, N);
  const M = N >> 1;
  const re = new Float64Array(M + 1), im = new Float64Array(M + 1);
  return Float64Array.from(periodos, (T) => {
    const wn = (2 * Math.PI) / T;
    for (let k = 0; k <= M; k++) {
      const w = (2 * Math.PI * k) / (N * dt);
      const dr = wn * wn - w * w, di = 2 * xi * wn * w, d = dr * dr + di * di;
      const hr = -dr / d, hi = di / d;                     // −1/(dr + i·di)
      re[k] = X.re[k] * hr - X.im[k] * hi;
      im[k] = X.re[k] * hi + X.im[k] * hr;
    }
    const u = irfft(re, im, N);
    let m = 0;
    for (let i = 0; i < N; i++) m = Math.max(m, Math.abs(u[i]));
    return (wn * wn * m) / G;
  });
}

/** Deriva máxima de un edificio de cortante lineal de 4 pisos (alturas de la torre: 4,5/4,2/4,2/4,2 m; masas y
 *  rigideces iguales, k fijada para que el primer modo tenga T1; Rayleigh de 5 % anclado en ω1 y 5·ω1), integrado con
 *  Newmark de aceleración promedio (γ = 1/2, β = 1/4) como el integrador del motor. Solo se usa en T20 para aislar el
 *  efecto del filtro, del diezmado y de Δt = 0,01 s (no reemplaza la corrida con el modelo de la torre). */
function derivaCortante(ag, dt, { T1 = 0.6, h = [4.5, 4.2, 4.2, 4.2], xi = 0.05 } = {}) {
  const n = h.length, m = 1;
  const w1 = (2 * Math.PI) / T1;
  // ω_r = 2·√(k/m)·sen((2r − 1)·π/(2(2n + 1))) (cortante uniforme, base empotrada; Chopra, cap. 12)
  const k = m * (w1 / (2 * Math.sin(Math.PI / (2 * (2 * n + 1))))) ** 2;
  const K = Array.from({ length: n }, () => new Float64Array(n));
  for (let i = 0; i < n; i++) {
    K[i][i] += k;
    if (i + 1 < n) { K[i][i] += k; K[i][i + 1] -= k; K[i + 1][i] -= k; }
  }
  const wj = 5 * w1, a0 = (2 * xi * w1 * wj) / (w1 + wj), a1 = (2 * xi) / (w1 + wj);
  const g = 0.5, b = 0.25, c1 = 1 / (b * dt * dt), c2 = 1 / (b * dt), c3 = 1 / (2 * b) - 1;
  const cg = g / (b * dt), cv = g / b - 1, ca = dt * (g / (2 * b) - 1);
  // K̂ = K + (γ/(βΔt))·C + M/(βΔt²), C = a0·M + a1·K; inversa por Gauss-Jordan (4 × 4)
  const A = K.map((fila, i) => [...Array.from(fila, (v, j) => v * (1 + a1 * cg) + (i === j ? m * (a0 * cg + c1) : 0)), ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let c = 0; c < n; c++) {
    const p = A[c][c];
    for (let j = 0; j < 2 * n; j++) A[c][j] /= p;
    for (let r = 0; r < n; r++) if (r !== c) { const f = A[r][c]; for (let j = 0; j < 2 * n; j++) A[r][j] -= f * A[c][j]; }
  }
  const Ki = A.map((fila) => fila.slice(n));
  let u = new Float64Array(n), v = new Float64Array(n), a = new Float64Array(n).fill(-ag[0]);
  const tC = new Float64Array(n), rhs = new Float64Array(n);
  let dmax = 0;
  for (let s = 0; s < ag.length - 1; s++) {
    for (let i = 0; i < n; i++) tC[i] = cg * u[i] + cv * v[i] + ca * a[i];
    for (let i = 0; i < n; i++) {
      let Kt = 0;
      for (let j = 0; j < n; j++) Kt += K[i][j] * tC[j];
      rhs[i] = -m * ag[s + 1] + m * (c1 * u[i] + c2 * v[i] + c3 * a[i]) + a1 * Kt + a0 * m * tC[i];
    }
    const un = Float64Array.from(Ki, (fila) => fila.reduce((acc, x, j) => acc + x * rhs[j], 0));
    for (let i = 0; i < n; i++) {
      const an = c1 * (un[i] - u[i]) - c2 * v[i] - c3 * a[i];
      v[i] += dt * ((1 - g) * a[i] + g * an);
      a[i] = an;
    }
    u = un;
    for (let i = 0; i < n; i++) dmax = Math.max(dmax, Math.abs(u[i] - (i ? u[i - 1] : 0)) / h[i]);
  }
  return dmax;
}

/** Corre tareas en hilos de trabajo repartidas en partes iguales (intercaladas) y junta los resultados en orden. */
async function enHilos(archivo, tareas, datos) {
  const nH = Math.max(1, Math.min(availableParallelism(), 8, tareas.length));
  const partes = Array.from({ length: nH }, () => []);
  tareas.forEach((_, i) => partes[i % nH].push(i));
  const out = new Array(tareas.length);
  await Promise.all(partes.map((idx) => new Promise((ok, mal) => {
    const w = new Worker(new URL(archivo, import.meta.url), { workerData: { ...datos, tareas: idx.map((i) => tareas[i]) } });
    w.once('message', (r) => { r.forEach((v, j) => { out[idx[j]] = v; }); ok(); w.terminate(); });
    w.once('error', mal);
    w.once('exit', (c) => { if (c !== 0 && c !== 1) mal(new Error(`hilo terminó con código ${c}`)); });
  })));
  return out;
}

// ── T13 · GMPE ────────────────────────────────────────────────────────────────────────────────────────────────
const IMT = ['PGA', '0.2', '0.5', '1.0'];
const T_IMT = [0, 0.2, 0.5, 1.0];

function t13() {
  const casos = [];
  // (a) Copia exacta de los coeficientes
  for (const [modelo, t] of Object.entries(MOV.GMPE_COEF)) {
    const ref = amenaza.gmpe[modelo];
    let total = 0, distintos = 0;
    const columnas = JSON.stringify(t.columnas) === JSON.stringify(ref.columnas);
    if (t.coeficientes.length !== ref.coeficientes.length) distintos++;
    for (const fila of ref.coeficientes) {
      const mia = t.coeficientes.find((r) => r[0] === fila[0]);
      fila.forEach((v, i) => { total++; if (!mia || mia[i] !== v) distintos++; });
    }
    for (const [k, v] of Object.entries(t.constantes ?? {})) { total++; if (ref.constantes[k] !== v) distintos++; }
    casos.push(comprobar(`${modelo}: ${total} números iguales a amenaza.json`, columnas && distintos === 0, distintos ? `${distintos} distintos` : undefined));
  }
  // (b) Valores de prueba de amenaza.json (< 0,5 %)
  const entradas = {
    bchydro2016_intraslab: { esc: { Mw: 6.2, Rhip_km: 176, profundidad_km: 150, vs30_m_s: 270 }, numeros: ['6,2', '176', '150', '270'] },
    zhao2006_intraslab: { esc: { Mw: 6.0, Rrup_km: 150, profundidad_km: 150, vs30_m_s: 250 }, numeros: ['6,0', '150', '250'] },
    bssa14: { esc: { Mw: 6.5, Rjb_km: 25, vs30_m_s: 270 }, numeros: ['6,5', '25', '270'] },
  };
  for (const [modelo, { esc, numeros }] of Object.entries(entradas)) {
    const pr = amenaza.gmpe[modelo].prueba;
    if (!numeros.every((x) => pr.entrada.includes(x))) throw new Error(`la entrada de prueba de ${modelo} cambió: «${pr.entrada}»`);
    const r = MOV.gmpe(modelo, esc, T_IMT).mediana_g;
    const ref = [pr.PGA_g, pr.Sa_0_2_g, pr.Sa_0_5_g, pr.Sa_1_0_g];
    casos.push(caso(`${modelo}: valores de prueba (${pr.entrada})`, errorRelativoMax(r, ref), 0.005,
      `PGA ${r[0].toFixed(5)} · Sa(0,2) ${r[1].toFixed(5)} · Sa(0,5) ${r[2].toFixed(5)} · Sa(1,0) ${r[3].toFixed(5)} g`));
  }
  // (c) Medianas de los 8 escenarios de amenaza.json (4 decimales: tolerancia 0,5 % más media unidad del redondeo).
  //     Es la única referencia publicada para Zhao 2006 cortical, que no trae bloque de prueba.
  const nombres = { 'BC Hydro 2016': 'bchydro2016_intraslab', 'Zhao 2006 intraplaca': 'zhao2006_intraslab', 'BSSA14 (Rjb = Repi)': 'bssa14', 'Zhao 2006 cortical': 'zhao2006_cortical' };
  const porModelo = {};
  for (const e of amenaza.escenarios) {
    for (const [nombre, valores] of Object.entries(e.resultado_gmpe_vs30_270_g)) {
      const modelo = nombres[nombre];
      if (!modelo) throw new Error(`GMPE «${nombre}» del escenario ${e.id} sin modelo`);
      const r = MOV.gmpe(modelo, escenario(e.id), T_IMT).mediana_g;
      ['pga', '0.2', '0.5', '1.0'].forEach((k, i) => {
        const ref = valores[k];
        const err = Math.abs(r[i] - ref) / (0.005 * ref + 0.00005);
        porModelo[modelo] = Math.max(porModelo[modelo] ?? 0, err);
      });
    }
  }
  for (const [modelo, err] of Object.entries(porModelo)) {
    casos.push(caso(`${modelo}: escenarios de amenaza.json (error / (0,5 % + redondeo))`, err, 1));
  }
  // (d) Contra gmpe.py de la investigación (otra transcripción, con sus propias copias de los coeficientes de
  //     OpenQuake y pygmm): medianas y σ en 4 magnitudes × 5 geometrías × 4 Vs30 × 4 IMT por modelo.
  const consultas = [];
  for (const modelo of Object.keys(MOV.GMPE_COEF)) {
    for (const Mw of [4.5, 5.0, 6.2, 7.4]) {
      for (const [Repi, h] of [[0, 10], [20, 10], [92, 150], [200, 60], [300, 200]]) {
        for (const vs30 of [180, 270, 450, 760]) consultas.push({ modelo, Mw, Repi, h, vs30 });
      }
    }
  }
  const codigo = `
import importlib.util, json, math, sys
spec = importlib.util.spec_from_file_location('gmpe_investigacion', sys.argv[1])
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
out = []
for c in json.load(sys.stdin):
    M, Re, h, vs = c['Mw'], c['Repi'], c['h'], c['vs30']
    R = math.hypot(Re, h)
    fila = []
    for imt in ('pga', 0.2, 0.5, 1.0):
        if c['modelo'] == 'bchydro2016_intraslab': v = g.bchydro_slab(imt, M, R, h, vs)
        elif c['modelo'] == 'zhao2006_intraslab': v = g.zhao06_slab(imt, M, R, h, vs)
        elif c['modelo'] == 'zhao2006_cortical': v = g.zhao06_asc(imt, M, R, h, vs)
        else: v = g.bssa14(imt, M, Re, vs)
        fila.append([v[0], v[1]])
    out.append(fila)
json.dump(out, sys.stdout)`;
  const ref = python(['-c', codigo, ruta('data/sismo/fuentes_investigacion/gmpe.py')], consultas);
  const peor = {};
  consultas.forEach((c, i) => {
    const r = MOV.gmpe(c.modelo, { Mw: c.Mw, profundidad_km: c.h, distancia_epicentral_km: c.Repi, vs30_m_s: c.vs30 }, T_IMT);
    for (let j = 0; j < 4; j++) {
      const e = Math.max(errorRelativo(r.mediana_g[j], ref[i][j][0]), errorRelativo(r.sigma_ln[j], ref[i][j][1]));
      peor[c.modelo] = Math.max(peor[c.modelo] ?? 0, e);
    }
  });
  for (const [modelo, e] of Object.entries(peor)) casos.push(caso(`${modelo}: contra gmpe.py de la investigación (80 casos × 4 IMT, mediana y σ)`, e, 1e-9));
  // (e) Períodos sin coeficientes: NaN (no se inventa la meseta entre 0,01 y 0,2 s ni se extrapola sobre 1 s)
  const escB = { Mw: 6.5, Rjb_km: 25, vs30_m_s: 270 };
  const r = MOV.gmpe('bssa14', escB, [0.01, 0.1, 0.35, 2]);
  const [pga, sa02, sa05] = MOV.gmpe('bssa14', escB, [0, 0.2, 0.5]).mediana_g;
  const u = Math.log(0.35 / 0.2) / Math.log(0.5 / 0.2);
  const interp = Math.exp((1 - u) * Math.log(sa02) + u * Math.log(sa05));
  casos.push(comprobar('T ≤ 0,01 s = PGA; 0,2-1,0 s interpolado en ln-ln; 0,1 y 2 s sin dato (NaN)',
    r.mediana_g[0] === pga && Number.isNaN(r.mediana_g[1]) && Math.abs(r.mediana_g[2] / interp - 1) < 1e-12 && Number.isNaN(r.mediana_g[3])));
  return casos;
}

// ── T14 · Espectro NSR-10 ─────────────────────────────────────────────────────────────────────────────────────
function t14() {
  const d = amenaza.nsr10;
  const par = { Aa: d.Aa.valor, Av: d.Av.valor, Fa: d.Fa.valor_yondo, Fv: d.Fv.valor_yondo, I: d.I.valor };
  const v = d.espectro_elastico.valores_yondo_suelo_D;
  const casos = [];
  const tres = (nombre, x, ref) => casos.push(caso(`${nombre} = ${x.toFixed(4)} g (referencia ${ref})`, Math.abs(x - ref), 0.0005));
  tres('Sa(0,5 s) con I = 1,5', MOV.espectroNSR10(0.5, par), 0.844);   // contrato, 7.8
  tres('Sa(1,0 s) con I = 1,5', MOV.espectroNSR10(1.0, par), 0.594);
  tres('Sa(0,2 s) con I = 1,5', MOV.espectroNSR10(0.2, par), v.Sa_0_2_g);
  tres('Sa(2,0 s) con I = 1,5', MOV.espectroNSR10(2.0, par), v.Sa_2_0_g);
  const sinI = MOV.espectroNSR10(Float64Array.of(0.2, 0.5, 1.0), { ...par, I: 1 });
  v.Sa_sin_I_0_2_0_5_1_0_g.forEach((ref, i) => tres(`Sa(${[0.2, 0.5, 1.0][i]} s) sin I`, sinI[i], ref));
  // Continuidad en TC y en TL (la meseta y las dos ramas deben empalmar: TC = 0,48·Av·Fv/(Aa·Fa), TL = 2,4·Fv)
  const eps = 1e-9;
  const tc = (0.48 * par.Av * par.Fv) / (par.Aa * par.Fa), tl = 2.4 * par.Fv;
  casos.push(caso(`TC = 0,48·Av·Fv/(Aa·Fa) = ${tc.toFixed(4)} s (amenaza.json ${v.TC_s})`, Math.abs(tc - v.TC_s), 0.0005));
  casos.push(caso(`TL = 2,4·Fv = ${tl.toFixed(2)} s (amenaza.json ${v.TL_s})`, Math.abs(tl - v.TL_s), 0.005));
  casos.push(caso('empalme de la meseta con 1,2·Av·Fv·I/T en TC (g)', Math.abs(MOV.espectroNSR10(tc - eps, par) - MOV.espectroNSR10(tc + eps, par)), 1e-6));
  casos.push(caso('empalme en TL (g)', Math.abs(MOV.espectroNSR10(tl - eps, par) - MOV.espectroNSR10(tl + eps, par)), 1e-6));
  return casos;
}

// ── T15 · Síntesis estocástica (conjunto) ─────────────────────────────────────────────────────────────────────
function conjunto(p, nSim = 24, semilla0 = 7) {
  const acc = { PGA_g: [], Sa02_g: [], Sa05_g: [], Sa10_g: [], PGV_cm_s: [], D595_s: [], PGA_roca760_g: [] };
  let meta;
  for (let k = 0; k < nSim; k++) {
    const r = MOV.sintetizar({ ...p, semilla: semilla0 + 2 * k }, amenaza);   // s y s + 1 por síntesis: sin repetir
    meta = r.meta;
    for (const [c, a] of [['x', r.ax], ['y', r.ay]]) {
      const i = r.intensidades[c];
      const sa = MOV.espectroRespuesta(a, r.dt, [0.2, 0.5, 1.0]).Sa_g;
      acc.PGA_g.push(i.pga_g); acc.PGV_cm_s.push(i.pgv_cm_s); acc.D595_s.push(i.d595_s);
      acc.Sa02_g.push(sa[0]); acc.Sa05_g.push(sa[1]); acc.Sa10_g.push(sa[2]);
    }
    acc.PGA_roca760_g.push(meta.pga_roca_g);
  }
  return { medias: Object.fromEntries(Object.entries(acc).map(([k, v]) => [k, mediaGeometrica(v)])), meta };
}

function t15() {
  const casos = [];
  for (const id of ['nido_2015', 'cimitarra']) {
    const e = amenaza.escenarios.find((x) => x.id === id);
    const ref = e.resultado_estocastico_vs30_270;
    const { medias, meta } = conjunto(escenario(id));
    for (const k of ['PGA_g', 'PGA_roca760_g', 'Sa02_g', 'Sa05_g', 'Sa10_g', 'PGV_cm_s', 'D595_s']) {
      casos.push(caso(`${id}: ${k} = ${medias[k].toPrecision(3)} (amenaza.json ${ref[k]})`, errorRelativo(medias[k], ref[k]), 0.25));
    }
    casos.push(caso(`${id}: f0 = ${meta.f0_Hz.toFixed(4)} Hz (amenaza.json ${ref.f0_Hz})`, errorRelativo(meta.f0_Hz, ref.f0_Hz), 0.005));
    casos.push(caso(`${id}: Tgm = ${meta.Tgm_s.toFixed(2)} s (amenaza.json ${ref.Tgm_s})`, errorRelativo(meta.Tgm_s, ref.Tgm_s), 0.005));
  }
  // Contrato (7.8) y notas_para_implementar: f0 de Mw 6,2 con Δσ 800 bar, βs 4,5 km/s → 0,727 Hz
  const r = MOV.sintetizar(escenario('nido_2015', { semilla: 1 }), amenaza);
  casos.push(caso(`f0 de Mw 6,2 intraplaca = ${r.meta.f0_Hz.toFixed(4)} Hz (0,727)`, errorRelativo(r.meta.f0_Hz, 0.727), 0.005));
  return casos;
}

// ── T15b · Espectro objetivo contra estocastico.py ────────────────────────────────────────────────────────────
function t15b() {
  const f = [0.1, 0.5, 1, 5, 20];
  const conjuntos = [
    ['nido_2015', escenario('nido_2015')],
    ['cimitarra', escenario('cimitarra')],
    ['transición, h = 55 km', { Mw: 6.2, profundidad_km: 55, distancia_epicentral_km: 92, vs30_m_s: 270 }],
    ['cimitarra en Vs30 180 con escala_pgar 3', escenario('cimitarra', { vs30_m_s: 180, escala_pgar: 3 })],
  ];
  const consultas = [];
  for (const [, p] of conjuntos) for (const pgar of [0.05, 0.3, null]) consultas.push({ accion: 'objetivo', p, f_Hz: f, pgar_g: pgar });
  const semilla = 2028, pSint = escenario('local_hip', { semilla });
  consultas.push({ accion: 'mulberry32', semilla: 2028, n: 1000 });
  consultas.push({ accion: 'sintetizar', p: pSint });
  const ref = estocastico(consultas);
  const casos = [];
  let i = 0;
  for (const [nombre, p] of conjuntos) {
    for (const pgar of [0.05, 0.3, null]) {
      const js = MOV.espectroObjetivo(p, amenaza, Float64Array.from(f), { pgar_g: pgar ?? undefined });
      const py = ref[i++];
      const err = Math.max(errorRelativoMax(js.roca, py.roca), errorRelativoMax(js.suelo, py.suelo), errorRelativo(js.pgar_g, py.pgar_g));
      casos.push(caso(`${nombre}, PGAr ${pgar === null ? `por RVT (${js.pgar_g.toFixed(4)} g)` : `${pgar} g`}: roca y suelo en 0,1-20 Hz`, err, 0.001));
    }
  }
  // Más allá del contrato: el generador y la síntesis completa coinciden con Python (mismo algoritmo, otra máquina
  // de números: solo pueden diferir en el último bit de exp, log, sen y cos de cada biblioteca).
  const u = mulberry32(2028), uPy = ref[i++].u;
  let distintos = 0;
  for (let k = 0; k < uPy.length; k++) if (u() !== uPy[k]) distintos++;
  casos.push(comprobar('mulberry32: 1.000 uniformes idénticos bit a bit a los de Python', distintos === 0, distintos ? `${distintos} distintos` : undefined));
  const py = ref[i++];
  const js = MOV.sintetizar(pSint, amenaza);
  let e = js.n === py.n ? 0 : Infinity;
  for (const c of ['x', 'y']) {
    const a = js['a' + c], b = py['a' + c];
    let d = 0, m = 0;
    for (let k = 0; k < b.length; k++) { d = Math.max(d, Math.abs(a[k] - b[k])); m = Math.max(m, Math.abs(b[k])); }
    e = Math.max(e, d / m);
    for (const k of ['pga_g', 'pgv_cm_s', 'pgd_cm', 'arias_m_s', 'd595_s']) e = Math.max(e, errorRelativo(js.intensidades[c][k], py.intensidades[c][k]));
  }
  casos.push(caso(`local_hip, semilla ${semilla}: acelerogramas e intensidades de JS y Python (max|Δa|/PGA)`, e, 1e-9));
  return casos;
}

// ── T15c · Normalización del ruido ────────────────────────────────────────────────────────────────────────────
function t15c() {
  // Bandas de tercio de octava con las frecuencias centrales normalizadas 10^(k/10) (0,2 a 20 Hz), bordes fc·2^(±1/6).
  const centros = [];
  for (let k = -7; k <= 13; k++) centros.push(10 ** (k / 10));
  const casos = [];
  for (const id of ['nido_2015', 'palestina']) {
    const p = escenario(id);
    const suma = new Float64Array(centros.length), n = new Float64Array(centros.length);
    for (let s = 0; s < 100; s++) {                     // 100 síntesis × 2 componentes = 200 realizaciones
      const r = MOV.sintetizar({ ...p, semilla: 5000 + 2 * s }, amenaza);
      for (const a of [r.ax, r.ay]) {
        const F = MOV.espectroFourier(a, r.dt);           // |Δt·FFT(a)|
        // Objetivo exacto de esta realización: el del suelo con el PGA en roca que fijó su no linealidad
        const A = MOV.espectroObjetivo(p, amenaza, F.f_Hz, { pgar_g: r.meta.pga_roca_g }).suelo;
        for (let i = 0; i < F.f_Hz.length; i++) {
          const fi = F.f_Hz[i];
          if (fi < centros[0] * 2 ** (-1 / 6) || fi >= centros.at(-1) * 2 ** (1 / 6)) continue;
          const b = Math.round(10 * Math.log10(fi)) + 7;   // banda cuyo centro está más cerca en escala log
          suma[b] += (F.A_m_s[i] / A[i]) ** 2;
          n[b]++;
        }
      }
    }
    let peor = 0, bPeor = 0;
    const razones = Array.from(suma, (s, b) => s / n[b]);
    razones.forEach((q, b) => { if (Math.abs(q - 1) > peor) { peor = Math.abs(q - 1); bPeor = b; } });
    casos.push(caso(`${id}: |media de |Δt·FFT(a)|²/A(f)² − 1| en 21 bandas de 0,2 a 20 Hz`, peor, 0.1,
      `peor banda ${centros[bPeor].toPrecision(2)} Hz (${razones[bPeor].toFixed(3)}); de ${Math.min(...razones).toFixed(3)} a ${Math.max(...razones).toFixed(3)}`));
  }
  return casos;
}

// ── T16 · Espectro de respuesta: Nigam y Jennings contra FFT ──────────────────────────────────────────────────
function t16() {
  const T = MOV.periodosLog(60, 0.02, 5);
  const casos = [];
  for (const id of ['nido_2015', 'cimitarra']) {
    const r = MOV.sintetizar(escenario(id, { semilla: 2028 }), amenaza);
    for (const [c, a] of [['x', r.ax], ['y', r.ay]]) {
      const nj = MOV.espectroRespuesta(a, r.dt, T).Sa_g;
      const ff = espectroPorFFT(a, r.dt, T);
      let largo = 0, corto = 0;
      for (let j = 0; j < T.length; j++) {
        const e = errorRelativo(nj[j], ff[j]);
        if (T[j] >= 0.1) largo = Math.max(largo, e); else corto = Math.max(corto, e);
      }
      casos.push(caso(`${id} ${c}: T ≥ 0,1 s`, largo, 0.01));
      casos.push(caso(`${id} ${c}: 0,02 ≤ T < 0,1 s`, corto, 0.03));
    }
  }
  return casos;
}

// ── T19 · Continuidad con la profundidad (E15) ────────────────────────────────────────────────────────────────
async function t19() {
  const combinaciones = [];
  for (const Mw of [5, 6.2, 7]) for (const Repi of [0, 92, 200]) combinaciones.push([Mw, Repi]);
  const tareas = [];
  for (const [Mw, Repi] of combinaciones) for (let h = 5; h <= 200; h++) tareas.push([Mw, Repi, h]);
  // Las mismas 24 semillas en cada profundidad (números aleatorios comunes): el cociente mide la física, no el azar
  const semillas = Array.from({ length: 24 }, (_, k) => 101 + 2 * k);
  const medianas = await enHilos('./_movimiento_t19.mjs', tareas, { semillas, vs30: 270 });
  const casos = [];
  let j = 0;
  for (const [Mw, Repi] of combinaciones) {
    let lo = Infinity, hi = -Infinity, hLo = 0, hHi = 0;
    for (let h = 5; h <= 199; h++) {
      const q = medianas[j + h - 5 + 1] / medianas[j + h - 5];
      if (q < lo) { lo = q; hLo = h; }
      if (q > hi) { hi = q; hHi = h; }
    }
    j += 196;
    casos.push({ caso: `Mw ${Mw}, Repi ${Repi} km: PGA(h + 1)/PGA(h) entre ${lo.toFixed(3)} (h = ${hLo}) y ${hi.toFixed(3)} (h = ${hHi})`,
      ok: lo >= 0.85 && hi <= 1.18, detalle: 'tolerancia 0,85 a 1,18' });
  }
  return casos;
}

// ── T20 · Calidad baja ────────────────────────────────────────────────────────────────────────────────────────
async function t20() {
  const casos = [];
  const registros = {};
  for (const id of ['nido_2015', 'cimitarra']) {
    const r = MOV.sintetizar(escenario(id, { semilla: 2028 }), amenaza);
    registros[id] = r;
    for (const [c, a] of [['x', r.ax], ['y', r.ay]]) {
      const fd = MOV.filtrarYDiezmar(a, r.dt);
      const p0 = MOV.intensidades(a, r.dt).pga_g, p1 = MOV.intensidades(fd.a, fd.dt).pga_g;
      casos.push(caso(`${id} ${c}: PGA filtrado y diezmado ${p1.toFixed(4)} g contra ${p0.toFixed(4)} g`, errorRelativo(p1, p0), 0.03));
      // Deriva de un edificio de cortante de 4 pisos con T1 de 0,3, 0,6 (≈ la torre) y 1,0 s
      let peor = 0;
      for (const T1 of [0.3, 0.6, 1.0]) peor = Math.max(peor, errorRelativo(derivaCortante(fd.a, fd.dt, { T1 }), derivaCortante(a, r.dt, { T1 })));
      casos.push(caso(`${id} ${c}: deriva máxima de un edificio de cortante (T1 0,3/0,6/1,0 s), Δt 0,01 s filtrado contra 0,005 s`, peor, 0.05));
    }
  }
  // Con el integrador del motor y la estructura (la de la torre si ya existe; si no, el fixture del Anexo A.3)
  const rutaIntegrador = new URL('web/js/sismo/integrador.js', RAIZ);
  if (!existsSync(rutaIntegrador)) {
    casos.push(comprobar('deriva con el integrador del motor: integrador.js todavía no existe (se prueba cuando exista)', true));
    return casos;
  }
  const { armarModelo } = await import(new URL('web/js/sismo/modelo.js', RAIZ).href);
  const { analizar } = await import(rutaIntegrador.href);
  const rutaTorre = 'data/sismo/torre_hospital_estructura.json';
  const estructura = existsSync(new URL(rutaTorre, RAIZ)) ? leerJSON(rutaTorre) : leerJSON('scripts/fixtures/torre/estructura_min.json');
  const modelo = armarModelo(estructura);
  for (const [id, reg] of Object.entries(registros)) {
    const deriva = async (registro, op) => {
      const { resultados } = await analizar(modelo, registro, { duracion_s: reg.n * reg.dt, ...op });
      return Math.max(...resultados.envolventes.deriva_vector_max);
    };
    // Como motor.js en calidad baja: las dos componentes filtradas y diezmadas, y el integrador con Δt = 0,01 s
    const fx = MOV.filtrarYDiezmar(reg.ax, reg.dt), fy = MOV.filtrarYDiezmar(reg.ay, reg.dt);
    const d0 = await deriva(reg, { dt_s: 0.005, calidad: 'normal' });
    const d1 = await deriva({ dt: fx.dt, n: fx.a.length, ax: fx.a, ay: fy.a }, { dt_s: 0.01, calidad: 'baja' });
    casos.push(caso(`${id}: deriva vectorial máxima de ${estructura.id ?? 'la estructura'} con Δt 0,01 s (calidad baja) contra 0,005 s`, errorRelativo(d1, d0), 0.05,
      `${(100 * d1).toFixed(4)} % contra ${(100 * d0).toFixed(4)} %`));
  }
  return casos;
}

// ── MOV1 · Fórmulas de amenaza.json ───────────────────────────────────────────────────────────────────────────
function mov1() {
  const casos = [];
  const notas = amenaza.notas_para_implementar;
  // Los fragmentos de JavaScript de las notas, evaluados tal cual, contra las funciones del módulo
  const ventanaRef = new Function(`${notas.ventana_js}; return ventana;`)();
  const ZRef = new Function(`${notas.dispersion_js}; return Z;`)();
  const btRef = new Function(`${notas.duracion_bt14_js}; return TcaminoBT14;`)();
  let e = 0;
  for (let t = -1; t <= 25; t += 0.0137) e = Math.max(e, Math.abs(MOV.__pruebas.ventana(t, 20.34, amenaza) - ventanaRef(t, 20.34)));
  casos.push(caso('ventana de Saragoni-Hart = ventana_js de las notas', e, 1e-12));
  e = 0;
  for (const tramos of [amenaza.parametros_estocasticos.cortical.dispersion_geometrica.tramos, amenaza.parametros_estocasticos.intraplaca_profunda.dispersion_geometrica.tramos,
    amenaza.parametros_estocasticos.cortical.dispersion_geometrica.alternativa_ENA.tramos]) {
    for (let R = 0.5; R < 400; R *= 1.07) e = Math.max(e, errorRelativo(MOV.__pruebas.dispersionGeometrica(R, tramos), ZRef(R, tramos)));
  }
  casos.push(caso('dispersión geométrica por tramos = dispersion_js de las notas', e, 1e-12));
  e = 0;
  for (let R = 0; R < 400; R += 0.731) e = Math.max(e, Math.abs(MOV.__pruebas.tcaminoBT14(R, amenaza) - btRef(R)));
  casos.push(caso('duración del camino de Boore y Thompson (2014) = duracion_bt14_js de las notas', e, 1e-12));
  // Constantes que en amenaza.json solo están dentro de fórmulas escritas
  const K = MOV.__pruebas.constantes, pe = amenaza.parametros_estocasticos;
  const textos = [
    [pe.comunes.espectro_fuente.formula, '4,906e6', K.BRUNE_F0 === 4.906e6],
    [amenaza.magnitud.formulas.momento_desde_Mw.formula, '10^(1,5·Mw + 16,05)', K.MW_A_M0.a === 1.5 && K.MW_A_M0.b === 16.05],
    [pe.cortical.distancia_efectiva_falla_finita.formula, '10^(−0,405 + 0,235·Mw)', K.H_FF.a === -0.405 && K.H_FF.b === 0.235],
    [pe.cortical.duracion_camino.mas_alla_270_km, '34,2 + 0,156·(R − 270)', K.BT14_MAS_ALLA.R === 270 && K.BT14_MAS_ALLA.T === 34.2 && K.BT14_MAS_ALLA.b === 0.156],
    [pe.intraplaca_profunda.duracion_camino.formula, '0,05·R', K.TCAMINO_INTRAPLACA_B === 0.05],
    [pe.intraplaca_profunda.factor_impedancia_fuente_profunda.formula, '(2,8·3,5)', K.IMPEDANCIA_REF.rho === 2.8 && K.IMPEDANCIA_REF.beta === 3.5],
    [amenaza.amplificacion_sitio.factor_suelo_BSSA14.Fnl, '(PGAr + 0,1)/0,1', K.PGA_BSSA_F3 === 0.1],
    [pe.comunes.simulacion.relleno_s, '40 s', K.RELLENO_S === 40],
    [notas.orden[4], 'f_0 = 1e-6', K.F_CERO === 1e-6],
  ];
  for (const [texto, fragmento, igual] of textos) casos.push(comprobar(`«${fragmento}» en amenaza.json y en el módulo`, texto.includes(fragmento) && igual));
  const fimp = Math.sqrt((pe.intraplaca_profunda.rho_s_g_cm3.valor * pe.intraplaca_profunda.beta_s_km_s.valor) / (2.8 * 3.5));
  casos.push(caso(`Fimp = ${fimp.toFixed(4)} (amenaza.json ${pe.intraplaca_profunda.factor_impedancia_fuente_profunda.valor})`,
    Math.abs(fimp - pe.intraplaca_profunda.factor_impedancia_fuente_profunda.valor), 0.005));
  casos.push(caso('partición 1/√2 contra 0,7071 de amenaza.json', Math.abs(Math.SQRT1_2 - pe.comunes.particion_V.valor), 5e-5));
  const m = MOV.momentoSismico(amenaza.magnitud.ejemplo.Mw);
  casos.push(caso('M0 de Mw 6,2 = 2,2387e25 dina·cm (amenaza.json → magnitud.ejemplo)', errorRelativo(m.M0_dina_cm, amenaza.magnitud.ejemplo.M0_dina_cm), 5e-5));
  return casos;
}

// ── MOV2 · FFT y azar ─────────────────────────────────────────────────────────────────────────────────────────
function mov2() {
  const casos = [];
  // rfft contra la DFT directa X_k = Σ x_n·e^{−2πikn/N} (suma en orden, con ángulos reducidos módulo N)
  let e = 0, eInv = 0;
  for (const N of [2, 4, 8, 16, 64, 512]) {
    const x = normales(N, new Float64Array(N));
    const X = rfft(x, N);
    let ref = 0, eN = 0;
    for (let k = 0; k <= N / 2; k++) {
      let sr = 0, si = 0;
      for (let n = 0; n < N; n++) { const ang = (-2 * Math.PI * ((k * n) % N)) / N; sr += x[n] * Math.cos(ang); si += x[n] * Math.sin(ang); }
      eN = Math.max(eN, Math.hypot(X.re[k] - sr, X.im[k] - si));
      ref = Math.max(ref, Math.hypot(sr, si));
    }
    e = Math.max(e, eN / ref);
    const y = irfft(X.re, X.im, N);
    for (let n = 0; n < N; n++) eInv = Math.max(eInv, Math.abs(y[n] - x[n]));
  }
  casos.push(caso('rfft contra la DFT directa (N = 2 a 512)', e, 1e-12));
  casos.push(caso('irfft(rfft(x)) = x', eInv, 1e-12));
  // Parseval en N = 16.384 con relleno de ceros: Σx² = (|X0|² + 2·Σ|Xk|² + |X_{N/2}|²)/N
  const N = 16384, x = normales(99, new Float64Array(10000));
  const X = rfft(x, N);
  let ex = 0, eX = 0;
  for (const v of x) ex += v * v;
  for (let k = 0; k <= N / 2; k++) eX += (k === 0 || k === N / 2 ? 1 : 2) * (X.re[k] ** 2 + X.im[k] ** 2);
  casos.push(caso('Parseval con relleno de ceros (N = 16.384)', errorRelativo(eX / N, ex), 1e-12));
  // Box-Muller: media 0, varianza 1, curtosis 3 en 10⁶ muestras (errores estándar ≈ 0,001; 0,0014; 0,005)
  const z = normales(2028, new Float64Array(1e6));
  let s1 = 0, s2 = 0, s4 = 0;
  for (const v of z) { s1 += v; s2 += v * v; s4 += v ** 4; }
  const n = z.length, media = s1 / n, varianza = s2 / n - media * media;
  casos.push(caso('normales: |media| (10⁶ muestras)', Math.abs(media), 0.005));
  casos.push(caso('normales: |varianza − 1|', Math.abs(varianza - 1), 0.007));
  casos.push(caso('normales: |curtosis − 3|', Math.abs(s4 / n / (varianza * varianza) - 3), 0.025));
  const a = normales(7, new Float64Array(9)), b = normales(7, new Float64Array(9));
  casos.push(comprobar('misma semilla → misma secuencia; semilla distinta → otra', a.every((v, i) => v === b[i]) && normales(8, new Float64Array(9))[0] !== a[0]));
  return casos;
}

// ── MOV3 · Nigam y Jennings: escalón con solución cerrada ─────────────────────────────────────────────────────
function mov3() {
  // ü + 2ξωu̇ + ω²u = −a0 desde reposo: u = −(a0/ω²)·[1 − e^(−ξωt)·(cos ωd·t + ξ/√(1 − ξ²)·sen ωd·t)]. El escalón es
  // lineal por tramos (constante), así que el método debe ser exacto en las muestras. El máximo es el primer pico
  // (en π/ωd); al terminar el registro el oscilador ya está quieto en −a0/ω² y oscila con amplitud a0/ω², menor.
  const casos = [];
  const dt = 0.005, a0 = 1.3, n = 8000;
  const a = new Float64Array(n).fill(a0);
  for (const xi of [0.02, 0.05, 0.2]) {
    const periodos = [0.05, 0.37, 1.0, 2.9];
    const r = MOV.espectroRespuesta(a, dt, periodos, xi);
    let e = 0;
    periodos.forEach((T, j) => {
      const w = (2 * Math.PI) / T, wd = w * Math.sqrt(1 - xi * xi);
      let m = 0;
      for (let i = 0; i < n; i++) {
        const t = i * dt;
        m = Math.max(m, Math.abs((a0 / (w * w)) * (1 - Math.exp(-xi * w * t) * (Math.cos(wd * t) + (xi / Math.sqrt(1 - xi * xi)) * Math.sin(wd * t)))));
      }
      e = Math.max(e, errorRelativo(r.Sd_m[j], m), errorRelativo(r.Sa_g[j], (w * w * m) / G));
    });
    casos.push(caso(`escalón, ξ = ${xi}: Sd y Sa en 4 períodos contra la solución cerrada`, e, 1e-9));
  }
  const s = MOV.espectroRespuesta(a, dt, [0]);
  casos.push(comprobar('T = 0: Sa = PGA y Sd = 0', s.Sa_g[0] === a0 / G && s.Sd_m[0] === 0));
  return casos;
}

// ── MOV4 · Contrato del registro, régimen, avisos y filtro ────────────────────────────────────────────────────
function mov4() {
  const casos = [];
  const p = escenario('nido_2015', { semilla: 31 });
  const r1 = MOV.sintetizar(p, amenaza), r2 = MOV.sintetizar(p, amenaza);
  const iguales = (a, b) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  casos.push(comprobar('Δt = 0,005 s; ax y ay en Float64Array; misma semilla → mismos bits', r1.dt === 0.005 && r1.ax instanceof Float64Array
    && r1.ay instanceof Float64Array && r1.ax.length === r1.n && iguales(r1.ax, r2.ax) && iguales(r1.ay, r2.ay)));
  const claves = ['M0_dina_cm', 'M0_N_m', 'energia_J_aprox', 'f0_Hz', 'delta_sigma_bar', 'beta_s_km_s', 'rho_s_g_cm3', 'Q0', 'eta', 'kappa0_s',
    'Rhip_km', 'Ref_km', 'Tgm_s', 't_eta_s', 'regimen', 'w_transicion', 'pga_roca_g'];
  const faltan = claves.filter((k) => r1.meta[k] === undefined);
  casos.push(comprobar('meta trae los campos del contrato (7.4)', faltan.length === 0, faltan.length ? `faltan ${faltan.join(', ')}` : undefined));
  // Componente y con la semilla s + 1: su pasada en roca es la de la componente x de la síntesis con semilla s + 1
  // (la pasada en suelo difiere porque el PGA en roca de la no linealidad es la media de las dos componentes).
  const otra = MOV.sintetizar({ ...p, semilla: 32 }, amenaza);
  casos.push(comprobar('componentes con semillas s y s + 1: PGA en roca de y(s) = el de x(s + 1); otra semilla, otro registro',
    r1.meta.pga_roca_y_g === otra.meta.pga_roca_x_g && !iguales(otra.ax, r1.ax)));
  // Régimen por profundidad (E15)
  const reg = [39, 40, 55, 70, 71].map((h) => MOV.regimenPorProfundidad(h));
  casos.push(comprobar('regimenPorProfundidad: 39 y 40 km cortical (w 0), 55 km transición (w 0,5), 70 y 71 km intraplaca (w 1)',
    reg[0].regimen === 'cortical' && reg[1].regimen === 'cortical' && reg[2].regimen === 'transicion' && reg[2].w === 0.5
      && reg[3].regimen === 'intraplaca_profunda' && reg[4].w === 1));
  const tr = MOV.sintetizar({ Mw: 6.2, profundidad_km: 55, distancia_epicentral_km: 92, vs30_m_s: 270, semilla: 3 }, amenaza);
  const Tc = tr.meta.terminos.find((x) => x.regimen === 'cortical'), Ti = tr.meta.terminos.find((x) => x.regimen === 'intraplaca_profunda');
  casos.push(caso('transición en h = 55 km: Tgm = (1 − w)·Tgm,c + w·Tgm,i', Math.abs(tr.meta.Tgm_s - (0.5 * Tc.Tgm_s + 0.5 * Ti.Tgm_s)), 1e-12));
  // ln A de la mezcla = (1 − w)·ln A_c + w·ln A_i
  const f = Float64Array.of(0.3, 2, 9);
  const mez = MOV.espectroObjetivo({ Mw: 6.2, profundidad_km: 49, distancia_epicentral_km: 92, vs30_m_s: 270 }, amenaza, f, { pgar_g: 0.02 }).roca;
  const co = MOV.espectroObjetivo({ Mw: 6.2, profundidad_km: 49, distancia_epicentral_km: 92, vs30_m_s: 270, regimen: 'cortical' }, amenaza, f, { pgar_g: 0.02 }).roca;
  const ip = MOV.espectroObjetivo({ Mw: 6.2, profundidad_km: 49, distancia_epicentral_km: 92, vs30_m_s: 270, regimen: 'intraplaca_profunda' }, amenaza, f, { pgar_g: 0.02 }).roca;
  let e = 0;
  for (let i = 0; i < 3; i++) e = Math.max(e, Math.abs(Math.log(mez[i]) - (0.7 * Math.log(co[i]) + 0.3 * Math.log(ip[i]))));
  casos.push(caso('h = 49 km (w = 0,3): ln A = 0,7·ln A_cortical + 0,3·ln A_intraplaca', e, 1e-12));
  // Avisos
  const av = (q) => MOV.avisos({ Mw: 6.2, distancia_epicentral_km: 92, vs30_m_s: 270, ...q }, amenaza);
  casos.push(comprobar('avisos: intraplaca forzada con h < 40 km, cortical forzada con h > 60 km, banda de transición, Mw < 4,5 y nido',
    av({ profundidad_km: 30, regimen: 'intraplaca_profunda' }).some((t) => t.includes('h < 40 km'))
      && av({ profundidad_km: 100, regimen: 'cortical' }).some((t) => t.includes('h > 60 km'))
      && av({ profundidad_km: 55 }).some((t) => t.includes('40-70 km'))
      && av({ profundidad_km: 150, Mw: 4.2 }).some((t) => t.startsWith('Sismo pequeño'))
      && av({ profundidad_km: 150 }).length === 0
      && av({ profundidad_km: 90 }).some((t) => t.startsWith('Sismo profundo fuera del nido'))));
  // Filtro de la calidad baja: respuesta en frecuencia exacta del FIR simétrico, H(f) = h0 + 2·Σ hk·cos(2πfkΔt)
  const h = MOV.coeficientesFIR(0.005), L = (h.length - 1) / 2;
  let paso = 0, rechazo = 0, simetria = 0;
  for (let fi = 0; fi <= 100; fi += 0.05) {
    let H = h[L];
    for (let k = 1; k <= L; k++) H += 2 * h[L + k] * Math.cos(2 * Math.PI * fi * k * 0.005);
    if (fi <= 20) paso = Math.max(paso, Math.abs(H - 1));
    if (fi >= 30) rechazo = Math.max(rechazo, Math.abs(H));
  }
  for (let k = 1; k <= L; k++) simetria = Math.max(simetria, Math.abs(h[L + k] - h[L - k]));
  casos.push(caso(`FIR de ${h.length} coeficientes: rizado en 0-20 Hz`, paso, 1e-3));
  casos.push(caso('FIR: ganancia en 30-100 Hz (≥ 60 dB de atenuación)', rechazo, 1e-3));
  casos.push(caso('FIR simétrico (fase cero)', simetria, 0));
  const fd = MOV.filtrarYDiezmar(r1.ax, r1.dt);
  casos.push(comprobar('filtrarYDiezmar: Δt 0,01 s y ⌈n/2⌉ muestras', fd.dt === 0.01 && fd.a.length === Math.ceil(r1.n / 2)));
  return casos;
}

// ── MOV5 · Intensidades de un seno ────────────────────────────────────────────────────────────────────────────
function mov5() {
  // a = A·sen(ωt) en 5 ciclos desde reposo: v = (A/ω)(1 − cos ωt) → PGV = 2A/ω; d = (A/ω)(t − sen(ωt)/ω) crece →
  // PGD = (A/ω)·t_fin; Arias = π/(2g)·A²·t_fin/2; energía acumulada E(t) = (A²/2)(t − sen(2ωt)/(2ω)).
  const A = 2.5, Tp = 0.8, ciclos = 5, dt = Tp / 2000, n = 2000 * ciclos + 1, w = (2 * Math.PI) / Tp, tFin = ciclos * Tp;
  const a = Float64Array.from({ length: n }, (_, i) => A * Math.sin(w * i * dt));
  const r = MOV.intensidades(a, dt);
  const E = (t) => (A * A / 2) * (t - Math.sin(2 * w * t) / (2 * w));
  const raiz = (meta) => { let lo = 0, hi = tFin; for (let k = 0; k < 80; k++) { const m = (lo + hi) / 2; if (E(m) < meta) lo = m; else hi = m; } return (lo + hi) / 2; };
  const d595 = raiz(0.95 * E(tFin)) - raiz(0.05 * E(tFin));
  return [
    caso('PGA', errorRelativo(r.pga_g, A / G), 1e-12),
    caso('PGV = 2A/ω (trapecios: error ≈ (ωΔt)²/12)', errorRelativo(r.pgv_cm_s, (100 * 2 * A) / w), 1e-5),
    caso('PGD = (A/ω)·t_fin', errorRelativo(r.pgd_cm, (100 * A * tFin) / w), 1e-5),
    caso('Arias = π/(2g)·A²·t_fin/2', errorRelativo(r.arias_m_s, (Math.PI / (2 * G)) * A * A * tFin / 2), 1e-9),
    caso('D5-95 contra la energía acumulada exacta', errorRelativo(r.d595_s, d595), 1e-4),
  ];
}

export const pruebas = [
  { id: 'T13', nombre: 'GMPE: coeficientes, valores de prueba, escenarios y gmpe.py de la investigación', fn: t13 },
  { id: 'T14', nombre: 'Espectro elástico NSR-10 (Yondó, suelo D)', fn: t14 },
  { id: 'T15', nombre: 'Síntesis estocástica: conjunto de 24 simulaciones contra amenaza.json', fn: t15 },
  { id: 'T15b', nombre: 'Espectro objetivo y síntesis contra scripts/sismo/estocastico.py', fn: t15b },
  { id: 'T15c', nombre: 'Normalización del ruido: |Δt·FFT(a)|²/A(f)² en tercios de octava (200 realizaciones)', fn: t15c },
  { id: 'T16', nombre: 'Espectro de respuesta: Nigam y Jennings contra FFT (60 períodos)', fn: t16 },
  { id: 'T19', nombre: 'Continuidad con la profundidad (E15): PGA(h + 1)/PGA(h), h de 5 a 199 km', fn: t19 },
  { id: 'T20', nombre: 'Calidad baja: filtro FIR de 20 Hz, diezmado y Δt = 0,01 s', fn: t20 },
  { id: 'MOV1', nombre: 'Fragmentos y constantes de amenaza.json → notas_para_implementar', fn: mov1 },
  { id: 'MOV2', nombre: 'FFT radix-2 (DFT directa, inversa, Parseval) y normales de Box-Muller', fn: mov2 },
  { id: 'MOV3', nombre: 'Nigam y Jennings: escalón con solución cerrada', fn: mov3 },
  { id: 'MOV4', nombre: 'Registro, régimen E15, avisos y filtro de la calidad baja', fn: mov4 },
  { id: 'MOV5', nombre: 'Intensidades de un seno con solución cerrada', fn: mov5 },
];
