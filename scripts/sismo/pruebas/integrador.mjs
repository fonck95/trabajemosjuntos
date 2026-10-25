// Pruebas del integrador (web/js/sismo/integrador.js): T1-T7, T12 y T21 del contrato (7.8), más R0: el motor
// contra una segunda implementación del mismo cálculo (scripts/sismo/referencia_min.py → referencia_min.json).
import { osciladorNewmark, analizar, Analisis, prepararEquipos, riesgoEquipos, resumenEquipos, bPsi, regimenBloque } from '../../../web/js/sismo/integrador.js';
import { rotulaEnSerie, BILINEAL, CLOUGH } from '../../../web/js/sismo/histeresis.js';
import { armarModelo } from '../../../web/js/sismo/modelo.js';
import { validarResultado } from '../validar_resultado.mjs';
import { registroPrueba, PARAMS_PRUEBA } from './_estructuras.mjs';
import { leerJSON, caso, comprobar, errorRelativo } from './_util.mjs';

const G = 9.80665;
const FIX = 'scripts/fixtures/torre/';
const W1 = 2 * Math.PI;              // ω de T = 1 s
const copia = (x) => JSON.parse(JSON.stringify(x));

/** Período discreto exacto de Newmark de aceleración promedio: T̄/T = (ωΔt/2)/arctan(ωΔt/2). */
const alargamiento = (w, dt) => (w * dt) / 2 / Math.atan((w * dt) / 2);

// ---- T1: oscilador libre sin amortiguar ---------------------------------------------------------------------
function t1() {
  const casos = [];
  for (const div of [20, 50]) {
    const dt = 1 / div, n = 50 * div;
    const r = osciladorNewmark({ m: 1, k: W1 * W1, dt, n, u0: 1 });
    // energía: ½ku² + ½mu̇² constante (Newmark de aceleración promedio no disipa)
    const E0 = 0.5 * W1 * W1;
    let dE = 0;
    for (let i = 0; i <= n; i++) dE = Math.max(dE, Math.abs(0.5 * W1 * W1 * r.u[i] ** 2 + 0.5 * r.v[i] ** 2 - E0) / E0);
    casos.push(caso(`Δt = T/${div}: energía constante (50 ciclos)`, dE, 1e-9));
    // período: del primer al último cruce por cero (interpolación lineal) contra T̄/T exacto
    const cruces = [];
    for (let i = 0; i < n; i++) if (r.u[i] === 0 || Math.sign(r.u[i]) !== Math.sign(r.u[i + 1])) cruces.push(r.t[i] + (dt * r.u[i]) / (r.u[i] - r.u[i + 1]));
    const Tm = (2 * (cruces.at(-1) - cruces[0])) / (cruces.length - 1);
    const Tb = alargamiento(W1, dt);
    casos.push(caso(`Δt = T/${div}: T̄ medido ${Tm.toFixed(7)} s frente a (ωΔt/2)/arctan(ωΔt/2) = ${Tb.toFixed(7)} s`, errorRelativo(Tm, Tb), 1e-4));
  }
  return casos;
}

// ---- T2: oscilador libre amortiguado ------------------------------------------------------------------------
function exactoAmortiguado(t, xi, w, u0, v0) {
  const wd = w * Math.sqrt(1 - xi * xi);
  return Math.exp(-xi * w * t) * (u0 * Math.cos(wd * t) + ((v0 + xi * w * u0) / wd) * Math.sin(wd * t));
}
function errorLibreAmortiguado(div, ciclos) {
  const xi = 0.05, u0 = 1, v0 = 0.5, dt = 1 / div, n = ciclos * div;
  const r = osciladorNewmark({ m: 1, c: 2 * xi * W1, k: W1 * W1, dt, n, u0, v0 });
  let e = 0;
  for (let i = 0; i <= n; i++) e = Math.max(e, Math.abs(r.u[i] - exactoAmortiguado(r.t[i], xi, W1, u0, v0)));
  return e;
}
function t2() {
  const e = errorLibreAmortiguado(200, 15);
  return caso('Δt = T/200, ξ = 5 %, 15 ciclos: max|u − exacto|/u0', e, 1e-3);
}

// ---- T3: forzado armónico ------------------------------------------------------------------------------------
function t3() {
  const casos = [], xi = 0.05, k = W1 * W1, p0 = 1, dt = 1 / 100;
  for (const rr of [0.5, 1, 2]) {
    const Om = rr * W1, Tf = (2 * Math.PI) / Om, n = Math.round((60 * Tf) / dt);
    const p = Float64Array.from({ length: n + 1 }, (_, i) => p0 * Math.sin(Om * i * dt));
    const r = osciladorNewmark({ m: 1, c: 2 * xi * W1, k, dt, n, p });
    // amplitud estacionaria: mínimos cuadrados de a·sen Ωt + b·cos Ωt en los últimos 10 ciclos (sin error de muestreo)
    const i0 = n - Math.round((10 * Tf) / dt);
    let ss = 0, cc = 0, sc = 0, us = 0, uc = 0;
    for (let i = i0; i <= n; i++) {
      const s = Math.sin(Om * r.t[i]), c = Math.cos(Om * r.t[i]);
      ss += s * s; cc += c * c; sc += s * c; us += r.u[i] * s; uc += r.u[i] * c;
    }
    const det = ss * cc - sc * sc, a = (us * cc - uc * sc) / det, b = (uc * ss - us * sc) / det;
    const amp = Math.hypot(a, b), ref = (p0 / k) / Math.sqrt((1 - rr * rr) ** 2 + (2 * xi * rr) ** 2);
    casos.push(caso(`r = ${rr}: amplitud ${(amp * k / p0).toFixed(5)}·p0/k frente a ${(ref * k / p0).toFixed(5)}`, errorRelativo(amp, ref), 5e-3));
  }
  return casos;
}

// ---- T4: escalón en la base -----------------------------------------------------------------------------------
function t4() {
  const dt = 1 / 100, n = 20 * 100, g0 = 1.5;
  const ag = new Float64Array(n + 1).fill(g0);
  const r = osciladorNewmark({ m: 1, k: W1 * W1, dt, n, ag });
  // la solución discreta es exacta con la frecuencia de Newmark ω̄ = ω/(T̄/T): u_n = −(ag/ω²)(1 − cos ω̄t_n)
  const wb = W1 / alargamiento(W1, dt);
  let eD = 0, eC = 0, umax = 0;
  for (let i = 0; i <= n; i++) {
    const ref = -(g0 / W1 ** 2);
    eD = Math.max(eD, Math.abs(r.u[i] - ref * (1 - Math.cos(wb * r.t[i]))));
    eC = Math.max(eC, Math.abs(r.u[i] - ref * (1 - Math.cos(W1 * r.t[i]))));
    umax = Math.max(umax, Math.abs(r.u[i]));
  }
  const pico = (2 * g0) / W1 ** 2;
  return [
    caso('amplitud: max|u| frente a 2·ag/ω²', errorRelativo(umax, pico), 5e-3),
    caso('historia frente a −(ag/ω²)(1 − cos ω̄t) con ω̄ de Newmark', eD / pico, 5e-3,
      `contra la fase continua (ω) el error crece con el desfase acumulado: ${(100 * eC / pico).toFixed(2)} % a los 20 ciclos (≈ 20·2π·(π²/3)(Δt/T)²/2)`),
  ];
}

// ---- T5: orden de convergencia ---------------------------------------------------------------------------------
function t5() {
  const e = [20, 40, 80].map((d) => errorLibreAmortiguado(d, 5));
  return [
    caso(`Δt T/20 → T/40: cociente de errores ${(e[0] / e[1]).toFixed(3)}`, Math.abs(e[0] / e[1] - 4), 0.4),
    caso(`Δt T/40 → T/80: cociente de errores ${(e[1] / e[2]).toFixed(3)}`, Math.abs(e[1] / e[2] - 4), 0.4),
  ];
}

// ---- T6: balance de energía ------------------------------------------------------------------------------------
function t6() {
  const casos = [];
  const reg = registroPrueba({ dt: 0.005, duracion: 10, pico_m_s2: 3 });
  const n = reg.ax.length - 1, m = 1, k = W1 * W1, xi = 0.05, c = 2 * xi * Math.sqrt(k * m);
  // fuerza elástica máxima de la corrida lineal → fy = 0,5 de ella
  const lin = osciladorNewmark({ m, c, k, dt: reg.dt, n, ag: reg.ax });
  let fmax = 0;
  for (const f of lin.fs) fmax = Math.max(fmax, Math.abs(f));
  for (const [nombre, fy, tolE] of [['elástico', Infinity, 5e-3], ['elastoplástico (fy = 0,5·fmax)', 0.5 * fmax, 1e-2]]) {
    for (const Ph of [0, 0.02 * k]) {
      const r = osciladorNewmark({ m, c, k, fy, alfa: 0.02, dt: reg.dt, n, ag: reg.ax, P_h: Ph });
      const et = `oscilador ${nombre}${Ph ? ', P/h = 2 % de k' : ''}`;
      casos.push(caso(`${et}: entrada = cinética + amortiguada + elástica + histerética + P-Delta`, r.error_energia, tolE,
        `E_hist/E_entrada = ${(r.energia.histeretica[n] / r.energia.entrada[n]).toFixed(3)}`));
      casos.push(caso(`${et}: ∫(fs − (P/h)u)du = elástica + histerética + P-Delta`, r.error_deformacion, tolE));
    }
  }
  // el motor completo sobre el cubo del Anexo A.3 (con amortiguamiento a1 dentro de los elementos y condensación)
  const est = leerJSON(FIX + 'estructura_min.json');
  const sinMuro = copia(est);
  sinMuro.bloques[0].resortes = [];
  for (const [nombre, e, escala, tolE] of [['motor elástico', sinMuro, 0.3, 5e-3], ['motor no lineal (rótulas y mampostería)', est, 4, 1e-2]]) {
    for (const pd of [false, true]) {
      const mod = armarModelo(e, { pDelta: pd });
      const { resultados: r } = analizar(mod, reg, { dt_s: 0.005, escala, params: PARAMS_PRUEBA, id: 't6' });
      const cn = r.calidad_numerica;
      const et = `${nombre}${pd ? ', con P-Delta' : ''}`;
      casos.push(caso(`${et}: igualdad de la energía de entrada`, cn.error_energia_max, tolE, `${r.thp.elementos.length} elementos con fluencia`));
      casos.push(caso(`${et}: control de la energía de deformación`, cn.error_deformacion_max, tolE));
      if (nombre === 'motor elástico') casos.push(comprobar(`${et}: ningún elemento fluye`, r.thp.elementos.length === 0));
      else casos.push(comprobar(`${et}: hay fluencia y trabajo P-Delta ${pd ? 'negativo' : 'nulo'}`, r.thp.elementos.length > 0 && (pd ? Math.min(...r.energia.filter((_, i) => i % 6 === 5)) < 0 : r.energia.every((x, i) => i % 6 !== 5 || x === 0))));
    }
  }
  return casos;
}

// ---- T7: ciclo cuasiestático de una rótula en serie con su parte elástica --------------------------------------
function t7() {
  const My = 100, ke = 1e4, alfa = 0.03, H = alfa * ke;
  const kpost = (ke * H) / (ke + H);                  // 291,262 kN·m/rad
  const Mp = My + kpost * 0.02, tp = (Mp - My) / H;   // pico: 105,825 kN·m con θp = 0,019417 rad
  // lazos de referencia (θ, M) por medias vueltas, con las reglas del 7.4
  const bil = [[[0, 0], [0.01, My], [0.03, Mp]], [[0.03, Mp], [tp, 0], [tp - (2 * My - Mp) / ke, -(2 * My - Mp)], [-0.03, -Mp]],
    [[-0.03, -Mp], [-tp, 0], [-tp + (2 * My - Mp) / ke, 2 * My - Mp], [0.03, Mp]]];
  const clo = [[[0, 0], [0.01, My], [0.03, Mp]], [[0.03, Mp], [tp, 0], [-0.01, -My], [-0.03, -Mp]], [[-0.03, -Mp], [-tp, 0], [0.03, Mp]]];
  // tabla del 7.8 (θ, M, θp impresos) y los mismos puntos exactos, en el orden del recorrido
  const tabla = {
    bilineal: [[0.01, 100, 0], [0.03, 105.825, 0.019417], [0.019417, 0, 0.019417], [0.01, -94.175, 0.019417], [-0.03, -105.825, -0.019417], [-0.019417, 0, -0.019417], [-0.01, 94.175, -0.019417]],
    clough: [[0.01, 100, 0], [0.03, 105.825, 0.019417], [0.019417, 0, 0.019417], [-0.01, -100, 0], [-0.03, -105.825, -0.019417], [-0.019417, 0, -0.019417], [0.03, 105.825, 0.019417]],
  };
  const exactos = {
    bilineal: [0.01, 0.03, tp, tp - (2 * My - Mp) / ke, -0.03, -tp, -tp + (2 * My - Mp) / ke],
    clough: [0.01, 0.03, tp, -0.01, -0.03, -tp, 0.03],
  };
  const casos = [];
  const vueltas = [[0, 0.03], [0.03, -0.03], [-0.03, 0.03]];
  for (const [nombre, modelo, lazo] of [['bilineal', BILINEAL, bil], ['clough', CLOUGH, clo]]) {
    // 1) los puntos de la tabla, impuestos con su θ exacto en el orden del lazo; se comparan θ, M y θp con las cifras
    //    impresas (6 decimales en θ y θp, 3 en M): error en medias unidades de la última cifra
    let r = rotulaEnSerie({ modelo, My_pos: My, alfa, ke });
    let peorTabla = 0;
    exactos[nombre].forEach((th, i) => {
      const { M, thp } = r.imponer(th);
      const [tT, MT, pT] = tabla[nombre][i];
      peorTabla = Math.max(peorTabla, Math.abs(th - tT) / 5e-7, Math.abs(M - MT) / 5e-4, Math.abs(thp - pT) / 5e-7);
    });
    casos.push(caso(`${nombre}: los 7 puntos de la tabla del 7.8`, peorTabla, 1, 'error en medias unidades de la última cifra impresa'));
    // 2) 200 puntos intermedios del lazo (θ recorre 0 → 0,03 → −0,03 → 0,03) contra el lazo lineal por tramos exacto
    r = rotulaEnSerie({ modelo, My_pos: My, alfa, ke });
    let peor = 0, n = 0;
    lazo.forEach((v, iv) => {
      const [a, b] = vueltas[iv];
      const pasos = iv === 0 ? 40 : 80;
      for (let s = 1; s <= pasos; s++) {
        const th = a + ((b - a) * s) / pasos;
        const { M } = r.imponer(th);
        let ref = null;
        for (let q = 0; q + 1 < v.length; q++) {
          const [t0, M0] = v[q], [t1, M1] = v[q + 1];
          if ((th - t0) * (th - t1) <= 1e-15) { ref = M0 + ((M1 - M0) * (th - t0)) / (t1 - t0); break; }
        }
        peor = Math.max(peor, Math.abs(M - ref) / My);
        n++;
      }
    });
    casos.push(caso(`${nombre}: ${n} puntos del lazo contra el lazo exacto (|ΔM|/My)`, peor, 1e-6));
  }
  return casos;
}

// ---- T12: equilibrio en la base ------------------------------------------------------------------------------------
function t12() {
  const casos = [];
  const est = leerJSON(FIX + 'estructura_min.json');
  // centro de masa del nivel 2 corrido 1,5 m al norte para que haya torsión y el término de P-Delta no sea simétrico
  est.bloques[0].niveles[1].cm = [2.5, 4.0];
  const reg = registroPrueba({ dt: 0.005, duracion: 4, pico_m_s2: 4 });
  for (const pd of [false, true]) {
    const mod = armarModelo(est, { pDelta: pd });
    const an = new Analisis(mod, reg, { dt_s: 0.005, escala: 1, tolerancia: 1e-10, angulo_deg: 30 });
    const el = mod.el, nuc = mod.nucleo, nv = mod.niveles, N = mod.N;
    const x0 = nv[0].xc, y0 = nv[0].yc, h1 = nv[0].h;
    let peorV = 0, peorT = 0, refV = 0, refT = 0;
    while (!an.terminado) {
      an.avanzar(1);
      const i = an.i, gx = an.agx[i], gy = an.agy[i], u = an.uD, v = an.vD, a = an.aD;
      // inercia: Σ m·a_abs y su momento respecto del eje vertical por el CM del nivel 1
      let Ix = 0, Iy = 0, It = 0, Ax = 0, Ay = 0, At = 0;
      for (let k = 0; k < N; k++) {
        const m = nv[k].masa, J = nv[k].Jz, b = 3 * k, ax = a[b] + gx, ay = a[b + 1] + gy;
        Ix += m * ax; Iy += m * ay; It += J * a[b + 2] + (nv[k].xc - x0) * m * ay - (nv[k].yc - y0) * m * ax;
        const a0 = an.a0;
        Ax += a0 * m * v[b]; Ay += a0 * m * v[b + 1]; At += a0 * (J * v[b + 2] + (nv[k].xc - x0) * m * v[b + 1] - (nv[k].yc - y0) * m * v[b]);
      }
      // cortante de los elementos del entrepiso 1 (incluido su amortiguamiento) y de la mampostería
      let Vx = 0, Vy = 0, Vt = 0;
      for (let ie = 0; ie < mod.nE; ie++) {
        if (an.vert[ie] !== 1 || el.piso[ie] !== 1) continue;
        const V = (nuc.Q[3 * ie] + nuc.Q[3 * ie + 1]) / el.Lf[ie], c = an.cE[ie];
        if (an.dirE[ie] === 0) { Vx += V; Vt -= (c - y0) * V; } else { Vy += V; Vt += (c - x0) * V; }
      }
      mod.muros.forEach((mu, im) => {
        if (mod.niveles[mu.g].abajo >= 0) return;
        const F = an.FmAnt[im];
        if (mu.dir === 0) { Vx += F; Vt -= (mu.c - y0) * F; } else { Vy += F; Vt += (mu.c - x0) * F; }
      });
      // P-Delta del entrepiso 1: Σ_j (W_j/h1)·δ1(CM_j) y su momento, con el giro del nivel 1 sobre r_j² = Jz_j/m_j
      let Px = 0, Py = 0, Pt = 0;
      if (pd) {
        for (let j = 0; j < N; j++) {
          const W = nv[j].peso, xj = nv[j].xc, yj = nv[j].yc, r2 = nv[j].Jz / nv[j].masa;
          const dx = u[0] - (yj - nv[0].yc) * u[2], dy = u[1] + (xj - nv[0].xc) * u[2];
          Px += (W / h1) * dx; Py += (W / h1) * dy; Pt += (W / h1) * ((xj - x0) * dy - (yj - y0) * dx + r2 * u[2]);
        }
      }
      refV = Math.max(refV, Math.abs(Ix), Math.abs(Iy)); refT = Math.max(refT, Math.abs(It));
      peorV = Math.max(peorV, Math.abs(Ix + Vx + Ax - Px), Math.abs(Iy + Vy + Ay - Py));
      peorT = Math.max(peorT, Math.abs(It + Vt + At - Pt));
    }
    const et = pd ? 'con P-Delta' : 'sin P-Delta';
    casos.push(caso(`${et}: Σm·a_abs = −(V_elem + V_a0) + V_PΔ,1 (x e y)`, peorV / refV, 1e-6, `máx |Σm·a_abs| = ${refV.toFixed(1)} kN`));
    casos.push(caso(`${et}: lo mismo para el momento torsor`, peorT / refT, 1e-6, `máx = ${refT.toFixed(1)} kN·m`));
  }
  return casos;
}

// ---- T21: equipos no anclados ------------------------------------------------------------------------------------
function pulsoEnSuelo(eq, a, pasosPulso, pasosLibres, dt, dir = [1, 0]) {
  const mem = prepararEquipos(null, [eq]);
  const ag = [a * dir[0], a * dir[1]], cero = [0, 0];
  for (let i = 0; i < pasosPulso; i++) riesgoEquipos({ dt, ag_ini: ag, ag_fin: ag, a_ini: null, a_fin: null }, null, mem);
  for (let i = 0; i < pasosLibres; i++) riesgoEquipos({ dt, ag_ini: cero, ag_fin: cero, a_ini: null, a_fin: null }, null, mem);
  return resumenEquipos(mem)[0];
}
function t21() {
  const base = { unidad: 'U-prueba-000001-001', piso: 1, x: 0, y: 0, z_sobre_piso: 0, anclaje: 'apoyado', masa_kg: 100, rot_z: 0 };
  const casos = [];
  // (a) b/h = 0,5, μ = 0,3, |a| = 0,6 g: solo desliza; deslizamiento contra Coulomb con pulso rectangular
  {
    const eq = { ...base, h_cg_m: 0.5, bx_m: 0.25, by_m: 0.25, mu: 0.3 };
    const dt = 0.013, np = 16, tp = np * dt, a = 0.6 * G;
    const r = pulsoEnSuelo(eq, a, np, 60, dt);
    // pulso: s̈ = −(a − μg) durante tp; después frena con μg hasta detenerse (t_s = (a − μg)·tp/(μg), dentro de un paso)
    const v1 = (a - 0.3 * G) * tp, s = 0.5 * (a - 0.3 * G) * tp * tp + (v1 * v1) / (2 * 0.3 * G);
    casos.push(comprobar('(a) b/h = 0,5, μ = 0,3, 0,6 g: régimen «desliza» sin balanceo', r.regimen === 'desliza' && r.desliza && !r.inicia_balanceo));
    casos.push(caso(`(a) deslizamiento ${(r.deslizamiento_max_m * 1000).toFixed(4)} mm frente a Coulomb ${(s * 1000).toFixed(4)} mm`, errorRelativo(r.deslizamiento_max_m, s), 1e-6,
      `se detiene a los ${(tp + v1 / (0.3 * G)).toFixed(4)} s, dentro del paso ${Math.floor((tp + v1 / (0.3 * G)) / dt)}`));
  }
  // (b) μ = 0,6, b/h = 0,3, |a| = 0,4 g: solo se balancea
  {
    const eq = { ...base, h_cg_m: 1.0, bx_m: 0.3, by_m: 0.3, mu: 0.6 };
    const r = pulsoEnSuelo(eq, 0.4 * G, 10, 5, 0.01);
    casos.push(comprobar('(b) μ = 0,6, b/h = 0,3, 0,4 g: régimen «balancea», inicia el balanceo y no desliza', r.regimen === 'balancea' && r.inicia_balanceo && !r.desliza && r.deslizamiento_max_m === 0));
  }
  // (c) cocientes a menos de 10 %: frontera
  {
    const eq = { ...base, h_cg_m: 1.0, bx_m: 0.52, by_m: 0.52, mu: 0.5 };
    const r = pulsoEnSuelo(eq, 0.3 * G, 5, 5, 0.01);
    casos.push(comprobar('(c) μ = 0,5 y b/h = 0,52 (a 3,8 %): régimen «frontera»', r.regimen === 'frontera' && regimenBloque(0.5, 0.52) === 'frontera'));
  }
  // (d) bloque en 2D con la aceleración a 45° de sus ejes: b_ψ = min(bx/|cos ψ|, by/|sen ψ|)
  {
    const eq = { ...base, h_cg_m: 1.0, bx_m: 0.3, by_m: 0.2, mu: 0.9 };
    const s2 = Math.SQRT1_2;
    const b45 = bPsi(eq, s2, s2, 0), ref45 = Math.min(0.3 / s2, 0.2 / s2);
    const b15 = bPsi(eq, Math.cos(Math.PI / 4), Math.sin(Math.PI / 4), Math.PI / 6), ref15 = Math.min(0.3 / Math.cos(Math.PI / 12), 0.2 / Math.sin(Math.PI / 12));
    casos.push(caso(`(d) a a 45° de los ejes: b_ψ = ${b45.toFixed(6)} m frente a ${ref45.toFixed(6)} m`, errorRelativo(b45, ref45), 1e-12));
    casos.push(caso(`(d) equipo girado 30°, a a 45° (ψ = 15°): b_ψ = ${b15.toFixed(6)} m frente a ${ref15.toFixed(6)} m`, errorRelativo(b15, ref15), 1e-12));
    const r = pulsoEnSuelo(eq, 0.35 * G, 3, 0, 0.01, [s2, s2]);
    casos.push(caso('(d) razón de vuelco = |a|/(g·b_ψ/h) con b_ψ de 45°', errorRelativo(r.razon_vuelco, 0.35 / (ref45 / 1.0)), 1e-12, `régimen ${r.regimen}`));
  }
  return casos;
}

// ---- R0: el motor contra el cálculo de referencia (segunda implementación, en Python con numpy) ---------------------
// Mismo modelo (estructura_min.json), pulso de prueba ×25 y equipos de referencia_min.py, con las mismas reglas del
// esquema (θ0 sin el término de cortante, ξ de los modos sin la mampostería). Diferencias esperadas: el redondeo a
// Float32 del archivo y la tolerancia de Newton (10⁻⁶).
const EQUIPOS_REF = [
  { unidad: 'U-consulta_externa-2d1bfe-001', piso: 2, x: 1.2, y: 3.8, z_sobre_piso: 0, anclaje: 'apoyado', masa_kg: 60, h_cg_m: 0.45, mu: 0.3, bx_m: 0.3, by_m: 0.25, rot_z: 0 },
  { unidad: 'U-hospitalizacion-5d13f8-001', piso: 2, x: 4.4, y: 0.6, z_sobre_piso: 0, anclaje: 'apoyado', masa_kg: 90, h_cg_m: 0.95, mu: 0.5, bx_m: 0.3, by_m: 0.2, rot_z: Math.PI / 2 },
  { unidad: 'U-fijo-91b0de-001', piso: 'CUB', x: 3.5, y: 3.5, z_sobre_piso: 0, anclaje: 'anclado', masa_kg: 200, h_cg_m: 0.7, mu: 0.5, bx_m: 0.5, by_m: 0.4, rot_z: 0 },
];
function r0() {
  const est = leerJSON(FIX + 'estructura_min.json'), ref = leerJSON(FIX + 'referencia_min.json');
  const mod = armarModelo(est);
  const n = 9, ax = new Float64Array(n), ay = new Float64Array(n);
  for (let i = 1; i < n; i++) { ax[i] = 1; ay[i] = -0.5; }
  const { resultados: r, historia: h } = analizar(mod, { dt: 0.005, ax, ay }, { dt_s: 0.005, dt_salida_s: 0.02, duracion_s: 0.04, escala: 25, equipos: EQUIPOS_REF,
    params: ref.params, id: 'prueba', origen_registro: ref.origen_registro });
  const casos = [];
  let peor = 0, cual = '';
  const comparar = (k, a, b) => {
    let m = 0, s = 0;
    for (let i = 0; i < b.length; i++) { m = Math.max(m, Math.abs(a[i] - b[i])); s = Math.max(s, Math.abs(b[i])); }
    const e = s ? m / s : m;
    if (e > peor) { peor = e; cual = k; }
  };
  for (const k of ['u', 'a_abs', 'giros', 'v_nodos', 'derivas', 'derivas_vector', 'derivas_porticos_env', 'cortante_basal', 'energia']) comparar(k, r[k], ref[k]);
  for (const k of Object.keys(ref.envolventes)) comparar(`envolventes.${k}`, r.envolventes[k], ref.envolventes[k]);
  // serie de C-A1-1@X (historia interna del motor)
  const ie = h.ids.indexOf(ref.serie_elemento.elemento);
  for (const k of ['Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc']) comparar(`serie.${k}`, Array.from({ length: h.nt }, (_, i) => h[k][i * h.nE + ie]), ref.serie_elemento[k]);
  casos.push(caso('series, envolventes y serie de C-A1-1@X (error relativo al máximo de cada arreglo)', peor, 1e-6, `el peor: ${cual}`));
  const enteros = ['dc', 'dc_flexion', 'dc_cortante', 'dc_rotacion', 'rotulas'].every((k) => r[k].every((x, i) => x === ref[k][i]));
  casos.push(comprobar('D/C × 100, bits de rótulas y thp idénticos', enteros && r.thp.valores.every((x, i) => x === ref.thp.valores[i]) && r.thp.elementos.join() === ref.thp.elementos.join(),
    `elementos con fluencia: ${[...r.thp.elementos].join(', ')}`));
  const eqOk = r.equipos.every((q, i) => q.regimen === ref.equipos[i].regimen && q.inicia_balanceo === ref.equipos[i].inicia_balanceo &&
    errorRelativo(q.deslizamiento_max_m, ref.equipos[i].deslizamiento_max_m) < 1e-6 && errorRelativo(q.a_max_m_s2, ref.equipos[i].a_max_m_s2) < 1e-6);
  casos.push(comprobar('equipos (régimen, balanceo, deslizamiento, aceleración) y muro de mampostería', eqOk && r.muros_mamposteria[0].estado === ref.muros_mamposteria[0].estado));
  casos.push(caso('a0, a1, períodos ancla y ξ de los modos', Math.max(errorRelativo(r.amortiguamiento.a0, ref.amortiguamiento.a0), errorRelativo(r.amortiguamiento.a1, ref.amortiguamiento.a1),
    errorRelativo(r.amortiguamiento.periodos_ancla_s[1], ref.amortiguamiento.periodos_ancla_s[1]),
    ...ref.amortiguamiento.xi_modos.map((x, k) => errorRelativo(r.amortiguamiento.xi_modos[k], x))), 1e-6));
  const v = validarResultado(r, est, { tipado: true });
  casos.push(caso('validar_resultado.mjs (tipado)', v.errores.length, 0, v.errores[0]));
  return casos;
}

export const pruebas = [
  { id: 'T1', nombre: 'Oscilador libre sin amortiguar (energía y período de Newmark)', fn: t1 },
  { id: 'T2', nombre: 'Oscilador libre amortiguado', fn: t2 },
  { id: 'T3', nombre: 'Forzado armónico (factor dinámico)', fn: t3 },
  { id: 'T4', nombre: 'Escalón en la base', fn: t4 },
  { id: 'T5', nombre: 'Orden de convergencia con Δt', fn: t5 },
  { id: 'T6', nombre: 'Balance de energía (oscilador y motor, con y sin P-Delta)', fn: t6 },
  { id: 'T7', nombre: 'Ciclo cuasiestático de una rótula (bilineal y Clough)', fn: t7 },
  { id: 'T12', nombre: 'Equilibrio en la base, con y sin P-Delta', fn: t12 },
  { id: 'T21', nombre: 'Equipos no anclados (Shenton, Coulomb)', fn: t21 },
  { id: 'R0', nombre: 'Motor contra el cálculo de referencia (referencia_min.py)', fn: r0 },
];
