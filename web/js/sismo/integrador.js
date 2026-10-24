// Integrador del motor sísmico: análisis no lineal en el tiempo del modelo pseudotridimensional de modelo.js.
// Contrato de la torre (data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md), 7.4 y 7.6; data/sismo/ESQUEMA.md,
// «Motor» y «Resultados del motor». Módulo puro: sin DOM ni three; imports relativos con extensión.
//
// - Newmark de aceleración promedio (γ = 1/2, β = 1/4; Newmark, 1959): incondicionalmente estable en lo lineal y sin
//   disipación numérica; alarga el período en (ωΔt/2)/arctan(ωΔt/2) (Hilber y Hughes, 1978).
// - Newton-Raphson completo: en cada iteración los v y θ de los pórticos se condensan por complemento de Schur
//   (modelo.js, Nucleo) y su equilibrio se impone en la misma iteración (no hay iteración anidada). Convergencia:
//   ‖R‖∞ ≤ tolerancia·max(‖P‖∞, 1 kN) y ‖Δu‖∞ ≤ 10⁻⁹ m; si no converge en max_iter, el paso se parte en dos (con la
//   aceleración del suelo interpolada) hasta max_subdiv veces; si aun así no converge, error «no_converge» con los
//   resultados que alcanzaron a calcularse.
// - Ecuación de movimiento en los gdl del diafragma (relativos al suelo):
//     M·ü + a0·M·u̇ + F_pórticos(u, u̇) + F_mampostería(u) + K_PΔ·u = −M·ι·üg
//   con el amortiguamiento a1 dentro de la parte elástica de cada elemento (M = K_e·(e + a1·ė), E8) y las cargas de
//   gravedad constantes en los gdl condensados (el dinámico parte del estado de gravedad, E4).
// - Balance de energía relativo (Uang y Bertero, 1990), todo con la regla del trapecio sobre Δu («∫f·du»), que con
//   Newmark de aceleración promedio cierra exactamente salvo la tolerancia de Newton (deducción: sumar la ecuación
//   en n y n + 1, multiplicar por Δu/2 y usar Δu = Δt·(u̇n + u̇n+1)/2 y Δu̇ = Δt·(ün + ün+1)/2).
// - Qué se evalúa en cada Δt (no sobre la salida): envolventes, primera fluencia, bits de rótulas (O lógico entre
//   salidas), derivas por pórtico y vectoriales, D/C con propiedades esperadas (E16) y riesgo de los equipos.
import { G, ErrorMotor, gravedad, amortiguamiento, evaluarMuros, cajaMuros, derivaVectorial, VIGA } from './modelo.js';
import { factorLU, resolverLU } from './algebra.js';
import { ENVOLVENTE } from './histeresis.js';

const VERSION = 1;
const TOL_DU = 1e-9;                    // m o rad (7.4)
const PASOS_POR_TANDA = 50;             // pasos entre consultas del reloj
// bits de `rotulas` (7.6)
const B_FLU_I = 1, B_FLU_J = 2, B_IO_I = 4, B_IO_J = 8, B_LS_I = 16, B_LS_J = 32, B_CP = 64, B_V = 128;
// anclajes que no dejan deslizar ni balancear al equipo (ESQUEMA.md, «Equipos no anclados»); `dentro` sigue a su
// contenedor: se informa la fuerza que el contenedor debe darle
const ANCLADOS = new Set(['anclado', 'pared', 'cielo', 'en_nucleo', 'dentro']);
const LIBRES = new Set(['apoyado', 'ruedas_con_freno', 'ruedas_sin_freno', 'sobre']);
const ahora = () => (globalThis.performance?.now ? globalThis.performance.now() : Date.now());
const fallo = (m, d) => { throw new ErrorMotor('datos', m, d); };
const esNum = (x) => typeof x === 'number' && Number.isFinite(x);

function abortado() {
  const e = new Error('análisis cancelado');
  e.name = 'AbortError';
  e.codigo = 'cancelado';
  return e;
}

// =================================================================================================================
// Opciones y registro
// =================================================================================================================
function normalizarOpciones(registro, op) {
  if (!registro || !(registro.dt > 0) || !registro.ax || !registro.ay) fallo('registro inválido: se espera { dt, ax, ay }');
  const nReg = registro.ax.length;
  if (registro.ay.length !== nReg || nReg < 2) fallo('registro: ax y ay deben tener el mismo largo (≥ 2)');
  const dtR = registro.dt;
  const dt = esNum(op.dt_s) ? op.dt_s : dtR;
  // el paso de cálculo divide al del registro (el registro de calidad baja ya llega filtrado y diezmado a 0,01 s)
  const sub = Math.round(dtR / dt);
  if (!(dt > 0) || sub < 1 || Math.abs(sub * dt - dtR) > 1e-9 * dtR) {
    fallo(`dt_s = ${op.dt_s} no divide al paso del registro (${dtR} s); para calidad baja el registro se filtra y diezma antes`);
  }
  const dtSal = esNum(op.dt_salida_s) ? op.dt_salida_s : 0.02;
  const pasoSal = Math.round(dtSal / dt);
  if (pasoSal < 1 || Math.abs(pasoSal * dt - dtSal) > 1e-9 * dtSal) fallo(`dt_salida_s = ${dtSal} no es múltiplo de dt_s = ${dt}`);
  const duracion = esNum(op.duracion_s) ? op.duracion_s : (nReg - 1) * dtR;
  const nPasos = Math.max(1, Math.round(duracion / dt));
  let factor, factor_escala = null, iteraciones_escala = 0;
  const escala = op.escala ?? 1;
  if (escala === 'nsr10') {
    factor = op.factor_escala;
    if (!(factor > 0)) fallo('escala «nsr10» sin factor_escala (lo calcula motor.js)');
    factor_escala = factor;
    iteraciones_escala = Number.isInteger(op.iteraciones_escala) ? op.iteraciones_escala : 1;
  } else {
    factor = escala;
    if (!(esNum(factor) && factor > 0)) fallo(`escala = ${escala}: se espera un número > 0 o 'nsr10'`);
  }
  const angulo = esNum(op.angulo_deg) ? op.angulo_deg : 0;
  const tol = esNum(op.tolerancia) && op.tolerancia > 0 ? op.tolerancia : 1e-6;
  const maxIter = Number.isInteger(op.max_iter) && op.max_iter > 0 ? op.max_iter : 20;
  const maxSubdiv = Number.isInteger(op.max_subdiv) && op.max_subdiv >= 0 ? op.max_subdiv : 4;
  return {
    dt, dtR, sub, nReg, dtSal, pasoSal, duracion: nPasos * dt, nPasos, nt: Math.floor(nPasos / pasoSal) + 1,
    escala, factor, factor_escala, iteraciones_escala, angulo, tol, maxIter, maxSubdiv,
    calidad: op.calidad === 'baja' ? 'baja' : 'normal',
    equipos: Array.isArray(op.equipos) ? op.equipos : [],
    guardarCompleta: !!op.guardar_serie_completa,
    params: op.params ?? null, id: op.id ?? null, origen_registro: op.origen_registro,
    intervaloProgreso: esNum(op.intervalo_progreso_ms) ? op.intervalo_progreso_ms : 250,
  };
}

// =================================================================================================================
// Equipos no anclados (7.4): deslizamiento de Coulomb e inicio del balanceo (Shenton, 1996)
// =================================================================================================================
/**
 * Nivel del diafragma que sostiene al equipo (índice global; −1 = el suelo). Piso 1 y `BT` = suelo (el bloque
 * técnico es otra estructura); piso p = nivel p − 1; `cielo` = el nivel de arriba (la losa de la que cuelga); `CUB` =
 * el nivel más alto cuyo contorno contiene al equipo (la cubierta del piso 4 o la terraza del piso 3), o el último.
 */
export function nivelEquipo(mod, eq) {
  if (eq.piso === 1 || eq.piso === 'BT') return eq.anclaje === 'cielo' && mod ? baseBloque(mod, 0) : -1;
  if (!mod) fallo(`equipo ${eq.unidad}: sin modelo solo se admiten equipos en el suelo (piso 1 o BT)`);
  const blq = mod.bloques[0];
  if (eq.piso === 'CUB') {
    for (let k = blq.n; k >= 1; k--) if (dentroDe([eq.x, eq.y], mod.niveles[blq.base + k - 1].contorno)) return blq.base + k - 1;
    return blq.base + blq.n - 1;
  }
  const p = Number(eq.piso);
  if (!Number.isInteger(p) || p < 1 || p > blq.n + 1) fallo(`equipo ${eq.unidad}: piso «${eq.piso}» fuera de la estructura`);
  const k = eq.anclaje === 'cielo' ? Math.min(p, blq.n) : p - 1;
  return blq.base + k - 1;
}
const baseBloque = (mod, ib) => mod.bloques[ib].base;

function dentroDe([x, y], poli) {
  if (!poli || poli.length < 3) return false;
  let dentro = false;
  for (let i = 0, j = poli.length - 1; i < poli.length; j = i++) {
    const [xi, yi] = poli[i], [xj, yj] = poli[j];
    if ((yi > y) !== (yj > y) && x <= ((xj - xi) * (y - yi)) / (yj - yi) + xi + 1e-9) dentro = !dentro;
  }
  return dentro;
}

/** Memoria de riesgoEquipos: un estado por equipo, con el nivel que lo sostiene ya resuelto (mod = null: todos en el suelo). */
export function prepararEquipos(mod, equipos = []) {
  return equipos.map((eq) => {
    for (const c of ['masa_kg', 'h_cg_m', 'mu', 'bx_m', 'by_m', 'x', 'y']) if (!esNum(eq[c])) fallo(`equipo ${eq.unidad}: falta «${c}»`);
    if (!(eq.h_cg_m > 0 && eq.bx_m > 0 && eq.by_m > 0 && eq.mu >= 0)) fallo(`equipo ${eq.unidad}: dimensiones o μ inválidos`);
    const anclado = ANCLADOS.has(eq.anclaje);
    if (!anclado && !LIBRES.has(eq.anclaje)) fallo(`equipo ${eq.unidad}: anclaje «${eq.anclaje}»`);
    const g = nivelEquipo(mod, eq);
    const nv = g >= 0 ? mod.niveles[g] : null;
    return {
      eq, g, xc: nv ? nv.xc : 0, yc: nv ? nv.yc : 0, anclado, rot: esNum(eq.rot_z) ? eq.rot_z : 0,
      a_max: 0, regimen: null, rb_en_max: null, inicia_balanceo: false, s: [0, 0], sd: [0, 0], s_max: 0,
    };
  });
}

/**
 * Semiancho del bloque en la dirección de la aceleración (bloque rígido en 2D, 7.4): ψ = dirección de a en los ejes
 * del equipo (girados rot_z) y b_ψ = min(bx/|cos ψ|, by/|sen ψ|): la arista de vuelco es la del lado que la línea de
 * acción corta primero.
 */
export function bPsi(eq, ax, ay, rot = eq.rot_z || 0) {
  const c = Math.cos(rot), s = Math.sin(rot);
  const axl = c * ax + s * ay, ayl = -s * ax + c * ay;
  const n = Math.hypot(axl, ayl);
  if (n === 0) return Math.min(eq.bx_m, eq.by_m);
  const cp = Math.abs(axl) / n, sp = Math.abs(ayl) / n;
  let b = Infinity;
  if (cp > 1e-12) b = Math.min(b, eq.bx_m / cp);
  if (sp > 1e-12) b = Math.min(b, eq.by_m / sp);
  return b;
}

/** Régimen de Shenton (1996): desliza primero si μ < b/h, se balancea primero si μ > b/h; «frontera» a menos de 10 %. */
export function regimenBloque(mu, rb) {
  if (Math.abs(mu - rb) / Math.max(mu, rb) < 0.1) return 'frontera';
  return mu < rb ? 'desliza' : 'balancea';
}

/**
 * Un paso de los equipos. estadoPiso: { dt, ag_ini: [x, y], ag_fin: [x, y], a_ini, a_fin } con a_* las
 * aceleraciones relativas del diafragma (3N; null si todos están en el suelo). La aceleración absoluta en el equipo
 * es a = üg + (üx − (y − yc)·r̈z, üy + (x − xc)·r̈z) del diafragma que lo sostiene. memoria: de prepararEquipos.
 * El deslizamiento usa la aceleración media del paso, la misma cinemática de Newmark de aceleración promedio.
 */
export function riesgoEquipos(estadoPiso, equipos, memoria) {
  if (!memoria) fallo('riesgoEquipos: falta la memoria (prepararEquipos)');
  const { dt, ag_ini, ag_fin, a_ini, a_fin } = estadoPiso;
  for (const q of memoria) {
    let ix = ag_ini[0], iy = ag_ini[1], fx = ag_fin[0], fy = ag_fin[1];
    if (q.g >= 0) {
      const b = 3 * q.g, ex = q.eq.x - q.xc, ey = q.eq.y - q.yc;
      ix += a_ini[b] - ey * a_ini[b + 2]; iy += a_ini[b + 1] + ex * a_ini[b + 2];
      fx += a_fin[b] - ey * a_fin[b + 2]; fy += a_fin[b + 1] + ex * a_fin[b + 2];
    }
    pasoEquipo(q, ix, iy, fx, fy, dt);
  }
  return memoria;
}

function pasoEquipo(q, ix, iy, fx, fy, dt) {
  const eq = q.eq;
  const amag = Math.hypot(fx, fy);
  const rb = bPsi(eq, fx, fy, q.rot) / eq.h_cg_m;
  const reg = q.anclado ? 'anclado' : regimenBloque(eq.mu, rb);
  if (amag > q.a_max || q.regimen === null) { q.a_max = Math.max(q.a_max, amag); q.regimen = reg; q.rb_en_max = rb; }
  if (q.anclado) return;
  // balanceo: solo se marca el inicio, |a| > g·b_ψ/h_cg (no se calcula si cae)
  if ((reg === 'balancea' || reg === 'frontera') && amag > G * rb) q.inicia_balanceo = true;
  // deslizamiento: si el régimen lo permite, o si ya venía deslizando (un bloque en movimiento no se congela)
  const moviendose = q.sd[0] !== 0 || q.sd[1] !== 0;
  if (reg === 'balancea' && !moviendose) return;
  deslizar(q, 0.5 * (ix + fx), 0.5 * (iy + fy), dt);
}

/**
 * Bloque sobre el piso con fricción de Coulomb (μ) y aceleración del piso constante (amx, amy) durante dt. Variables
 * relativas al piso: s (m) y ṡ (m/s). Quieto: arranca si |a| > μg, con s̈ = −(|a| − μg)·â (la fricción le da al
 * bloque a lo sumo μg). Deslizando: s̈ = −a − μg·ṡ/|ṡ|; si la velocidad se anula dentro del paso, se detiene en ese
 * instante y, si |a| > μg, vuelve a arrancar en el tiempo que queda. Exacto en 1D con a constante por tramos.
 */
function deslizar(q, amx, amy, dt) {
  const mug = q.eq.mu * G;
  let [sx, sy] = q.s, [vx, vy] = q.sd;
  let resto = dt;
  for (let k = 0; k < 4 && resto > 0; k++) {
    const vn = Math.hypot(vx, vy);
    if (vn === 0) {
      const an = Math.hypot(amx, amy);
      if (an <= mug) break;
      const ax = (-(an - mug) * amx) / an, ay = (-(an - mug) * amy) / an;
      sx += 0.5 * ax * resto * resto; sy += 0.5 * ay * resto * resto;
      vx = ax * resto; vy = ay * resto;
      resto = 0;
    } else {
      const ax = -amx - (mug * vx) / vn, ay = -amy - (mug * vy) / vn;
      const proy = -(ax * vx + ay * vy) / vn;           // desaceleración a lo largo de la velocidad
      const ts = proy > 0 ? vn / proy : Infinity;
      if (ts < resto) {
        sx += vx * ts + 0.5 * ax * ts * ts; sy += vy * ts + 0.5 * ay * ts * ts;
        vx = 0; vy = 0;
        resto -= ts;
      } else {
        sx += vx * resto + 0.5 * ax * resto * resto; sy += vy * resto + 0.5 * ay * resto * resto;
        vx += ax * resto; vy += ay * resto;
        resto = 0;
      }
    }
    q.s_max = Math.max(q.s_max, Math.hypot(sx, sy));
  }
  q.s[0] = sx; q.s[1] = sy; q.sd[0] = vx; q.sd[1] = vy;
}

/**
 * Fila de Resultados.equipos (7.6). El régimen es el del instante de aceleración máxima (ESQUEMA.md); en un bloque
 * no cuadrado el régimen depende de la dirección, así que si en el registro pasó otra cosa se informa lo que pasó:
 * «desliza» si deslizó sin balancearse, «balancea» si se balanceó sin deslizar y «frontera» si ocurrieron las dos.
 */
export function resumenEquipos(memoria) {
  return memoria.map((q) => {
    const eq = q.eq;
    const rb = q.rb_en_max ?? bPsi(eq, 1, 0, q.rot) / eq.h_cg_m;
    let reg = q.regimen ?? (q.anclado ? 'anclado' : regimenBloque(eq.mu, rb));
    const deslizo = q.s_max > 0;
    if (!q.anclado) {
      if (deslizo && q.inicia_balanceo) reg = 'frontera';
      else if (deslizo && reg === 'balancea') reg = 'desliza';
      else if (!deslizo && q.inicia_balanceo && reg === 'desliza') reg = 'balancea';
    }
    const recibida = reg === 'desliza' ? Math.min(q.a_max, eq.mu * G) : q.a_max;
    return {
      unidad: eq.unidad, anclaje: eq.anclaje, regimen: reg, a_max_m_s2: q.a_max,
      desliza: !q.anclado && deslizo, deslizamiento_max_m: q.anclado ? 0 : q.s_max,
      deslizamiento_final_m: q.anclado ? 0 : Math.min(q.s_max, Math.hypot(q.s[0], q.s[1])),
      inicia_balanceo: !q.anclado && q.inicia_balanceo,
      razon_vuelco: q.anclado ? null : recibida / (G * rb),
      fuerza_anclaje_kN: q.anclado ? (eq.masa_kg * q.a_max) / 1000 : null,
    };
  });
}

// =================================================================================================================
// Análisis
// =================================================================================================================
/**
 * Un análisis en el tiempo, paso a paso: lo usan analizar (de corrido) y analizarPorTramos (cediendo al bucle de
 * eventos), con la misma secuencia de operaciones, así que dan los mismos resultados bit a bit.
 */
export class Analisis {
  constructor(mod, registro, op = {}) {
    this.t0 = ahora();
    this.mod = mod;
    const o = (this.o = normalizarOpciones(registro, op));
    const { nd, N, nE, nN, nP } = mod;
    const nuc = (this.nuc = mod.nucleo);

    // ---- movimiento del suelo en los instantes de cálculo: interpolación lineal (la excitación de Newmark y de
    // Nigam-Jennings es lineal por tramos), ceros después del registro, girado angulo_deg y escalado ------------
    const n1 = o.nPasos + 1;
    this.agx = new Float64Array(n1); this.agy = new Float64Array(n1);
    const th = (o.angulo * Math.PI) / 180, c = Math.cos(th), s = Math.sin(th);
    for (let i = 0; i < n1; i++) {
      const r = i / o.sub, k = Math.floor(r);
      let a1 = 0, a2 = 0;
      if (k < o.nReg - 1) {
        const f = r - k;
        a1 = f === 0 ? registro.ax[k] : (1 - f) * registro.ax[k] + f * registro.ax[k + 1];
        a2 = f === 0 ? registro.ay[k] : (1 - f) * registro.ay[k] + f * registro.ay[k + 1];
      } else if (k === o.nReg - 1 && r === k) { a1 = registro.ax[k]; a2 = registro.ay[k]; }
      this.agx[i] = o.factor * (c * a1 - s * a2);
      this.agy[i] = o.factor * (s * a1 + c * a2);
    }

    // ---- estado inicial: el de gravedad (E4), en reposo -------------------------------------------------------
    const g = (this.g = gravedad(mod));
    nuc.restaurar(g.elementos);
    const am = (this.am = amortiguamiento(mod));
    this.a0 = am.a0; this.a1 = am.a1;
    this.uD = Float64Array.from(g.uD); this.uC = Float64Array.from(g.uC);
    this.vD = new Float64Array(nd); this.aD = new Float64Array(nd);
    for (let k = 0; k < N; k++) { this.aD[3 * k] = -this.agx[0]; this.aD[3 * k + 1] = -this.agy[0]; }
    // de prueba y de trabajo
    this.uT = new Float64Array(nd); this.uCT = new Float64Array(mod.ncTot);
    this.duD = new Float64Array(nd); this.duC = new Float64Array(mod.ncTot);
    this.vN = new Float64Array(nd); this.aN = new Float64Array(nd);
    this.Rd = new Float64Array(nd); this.Fd = new Float64Array(nd); this.Fm = new Float64Array(nd);
    this.Pext = new Float64Array(nd); this.K = new Float64Array(nd * nd);
    this.piv = new Int32Array(nd); this.tmp = new Float64Array(nd);
    this.Fr = new Float64Array(nd); this.FrAnt = new Float64Array(nd);
    this.FdN = new Float64Array(nd); this.DdN = new Float64Array(nd);   // fuerza de los pórticos y su amortiguamiento, comprometidas
    this.facUlt = NaN;                                                     // fac de la última evaluación de los elementos
    // mampostería
    const nM = mod.muros.length;
    this.mur = cajaMuros(mod);
    this.dmaxM = Float64Array.from(g.dmaxMuros);
    this.FmAnt = Float64Array.from(g.FmMuros); this.DmAnt = Float64Array.from(g.DMuros);
    this.Wm = new Float64Array(nM);
    this.EmG = 0;
    for (let i = 0; i < nM; i++) this.EmG += 0.5 * g.FmMuros[i] * g.DMuros[i];
    this.derivaMuro = new Float64Array(nM);
    let pgMax = 0;
    for (const x of mod.Pg) pgMax = Math.max(pgMax, Math.abs(x));
    this.pgMax = pgMax;

    // ---- energía: referencias del estado de gravedad -----------------------------------------------------------
    this.E = { entrada: 0, a0: 0, amortEl: 0, hist: 0, def: 0 };
    this.EelG = nuc.energiaElastica();
    this.uCG = Float64Array.from(g.uC);
    this.WpdG = 0.5 * cuadratica(mod.Kpd, g.uD, nd);
    this.EinMax = 0; this.desbE = 0; this.desbD = 0;
    // F_r del estado inicial (≈ 0: equilibrio lateral de la gravedad)
    nuc.evaluar(this.uD, this.uC, 1, 0, 0);
    this.FrAnt.fill(0);
    nuc.fuerzaDiafragma(this.FrAnt);
    this.FdN.set(this.FrAnt);
    for (let a = 0; a < nd; a++) {
      let sKp = 0;
      for (let b = 0; b < nd; b++) sKp += mod.Kpd[a * nd + b] * this.uD[b];
      this.FrAnt[a] += sKp;
    }
    for (let i = 0; i < nM; i++) { const m = mod.muros[i]; for (let a = 0; a < nd; a++) this.FrAnt[a] += g.FmMuros[i] * m.b[a]; }
    nuc.restaurar(g.elementos);

    // ---- precálculos para evaluar cada Δt -----------------------------------------------------------------------
    const el = mod.el;
    this.vert = new Uint8Array(nE); this.dirE = new Uint8Array(nE); this.cE = new Float64Array(nE);
    for (let ie = 0; ie < nE; ie++) {
      const P = mod.porticos[el.port[ie]];
      this.vert[ie] = el.tipo[ie] === VIGA ? 0 : 1;
      this.dirE[ie] = P.dir; this.cE[ie] = P.c;
    }
    // entrepisos de los pórticos en arreglos planos: índices del desplazamiento lateral arriba (t, r, coef), abajo
    // (o −1 si es el suelo), pórtico, dirección y nivel global
    const ent = [];
    mod.porticos.forEach((P, ip) => P.entrepisos.forEach((e) => ent.push([P.latT[e.l], P.latR[e.l], P.latC[e.l],
      e.la >= 0 ? P.latT[e.la] : -1, e.la >= 0 ? P.latR[e.la] : -1, e.la >= 0 ? P.latC[e.la] : 0, ip, P.dir, e.g])));
    this.nEnt = ent.length;
    this.entI = Int32Array.from(ent.flatMap((e) => [e[0], e[1], e[3], e[4], e[6], e[7], e[8]]));
    this.entC = Float64Array.from(ent.flatMap((e) => [e[2], e[5]]));

    this.nodoT = new Int32Array(nN); this.nodoV = new Int32Array(nN);
    mod.nodos.forEach((n, k) => {
      const P = mod.porticos[n.ip];
      this.nodoT[k] = n.it < P.n ? P.offC + n.it - P.nl : -1;
      this.nodoV[k] = n.iv < P.n ? P.offC + n.iv - P.nl : -1;
    });
    // peso de los niveles de encima de cada entrepiso (índice de estabilidad, NSR-10 A.6.2.3)
    this.Parriba = new Float64Array(N);
    for (const blq of mod.bloques) {
      let acum = 0;
      for (let k = blq.n; k >= 1; k--) { acum += mod.niveles[blq.base + k - 1].peso; this.Parriba[blq.base + k - 1] = acum; }
    }
    const nv0 = mod.niveles[0];
    this.x0 = nv0.xc; this.y0 = nv0.yc;   // eje del momento torsor de la base: CM del nivel 1

    // ---- salidas ---------------------------------------------------------------------------------------------------
    const nt = o.nt;
    this.R = {
      t: new Float32Array(nt), ag: new Float32Array(nt * 2), u: new Float32Array(nt * N * 3), a_abs: new Float32Array(nt * N * 3),
      giros: new Float32Array(nt * nN), v_nodos: new Float32Array(nt * nN),
      dc: new Uint8Array(nt * nE), dc_flexion: new Uint8Array(nt * nE), dc_cortante: new Uint8Array(nt * nE), dc_rotacion: new Uint8Array(nt * nE),
      rotulas: new Uint8Array(nt * nE), derivas: new Float32Array(nt * N * 2), derivas_vector: new Float32Array(nt * N),
      cortante_basal: new Float32Array(nt * 3), energia: new Float32Array(nt * 6),
    };
    this.env = {
      u_max: new Float64Array(N * 3), deriva_max: new Float64Array(N * 2), t_deriva_max: new Float64Array(N * 2),
      deriva_vector_max: new Float64Array(N), punto_deriva_vector: new Float64Array(N * 2), t_deriva_vector_max: new Float64Array(N),
      a_abs_max: new Float64Array(N * 3), dc_max: new Float64Array(nE), t_dc_max: new Float64Array(nE), gobierna: new Float64Array(nE),
      Mi_max: new Float64Array(nE), Mj_max: new Float64Array(nE), V_max: new Float64Array(nE),
      N_min: new Float64Array(nE).fill(Infinity), N_max: new Float64Array(nE).fill(-Infinity),
      thp_max: new Float64Array(nE * 2), t_primera_fluencia: new Float64Array(nE * 2).fill(-1),
    };
    this.envPort = new Float64Array(nP * N);
    this.Vpiso = new Float64Array(N * 2); this.VpisoMax = new Float64Array(N * 2); this.DcmMax = new Float64Array(N * 2);
    this.der = new Float64Array(N * 2); this.dvec = new Float64Array(N); this.pvec = new Float64Array(N * 2);
    this.bits = new Uint8Array(nE);
    this.fluyo = new Uint8Array(2 * nE);
    this.historia = {
      nt, nE, ids: el.id.slice(), t: new Float32Array(nt),
      Mi: new Float32Array(nt * nE), Mj: new Float32Array(nt * nE), V: new Float32Array(nt * nE), N: new Float32Array(nt * nE),
      thp_i: new Float32Array(nt * nE), thp_j: new Float32Array(nt * nE), dc: new Float32Array(nt * nE),
      u_completa: o.guardarCompleta ? new Float64Array((o.nPasos + 1) * nd) : null,
    };
    this.equipos = prepararEquipos(mod, o.equipos);
    this.estadoPiso = { dt: 0, ag_ini: [0, 0], ag_fin: [0, 0], a_ini: this.aD, a_fin: this.aN };
    this.cal = { pasos: 0, iter: 0, subdivisiones: 0, no_convergidos: 0 };
    this.i = 0;                 // pasos de Δt completados
    this.jSal = 0;              // salidas escritas
    if (this.historia.u_completa) this.historia.u_completa.set(this.uD, 0);
    this._evaluar(0, true);
  }

  get terminado() { return this.i >= this.o.nPasos; }
  get fraccion() { return this.i / this.o.nPasos; }
  get t_s() { return this.i * this.o.dt; }

  /** Avanza hasta n pasos de Δt. Lanza ErrorMotor('no_converge') con los resultados parciales en `resultados`. */
  avanzar(n = PASOS_POR_TANDA) {
    const o = this.o;
    const fin = Math.min(o.nPasos, this.i + n);
    while (this.i < fin) {
      const i = this.i;
      try {
        this._paso(o.dt, this.agx[i], this.agy[i], this.agx[i + 1], this.agy[i + 1], 0, i * o.dt);
      } catch (e) {
        if (e instanceof ErrorMotor && e.codigo === 'no_converge') {
          e.resultados = this.resultados({ parcial: true });
          e.detalle = { ...(e.detalle || {}), t_s: i * o.dt, paso: i, salidas: this.jSal };
        }
        throw e;
      }
      this.i = i + 1;
      if (this.historia.u_completa) this.historia.u_completa.set(this.uD, this.i * this.mod.nd);
      this._evaluar(this.i, this.i % o.pasoSal === 0);
    }
    return this.terminado;
  }

  // ---- un paso (con partición si no converge) -------------------------------------------------------------------
  _paso(dt, gx0, gy0, gx1, gy1, prof, tIni) {
    const r = this._intentar(dt, gx1, gy1);
    this.cal.iter += r.it;
    if (r.ok) {
      this.cal.pasos++;
      this._comprometer(dt, gx0, gy0, gx1, gy1, tIni + dt);
      return;
    }
    if (prof >= this.o.maxSubdiv) {
      this.cal.no_convergidos++;
      throw new ErrorMotor('no_converge', `el paso de t = ${tIni.toFixed(4)} s no convergió ni partido ${prof} veces (Δt = ${dt} s)`,
        { t_s: tIni, dt_s: dt, residuo: r.nR });
    }
    this.cal.subdivisiones++;
    const mx = 0.5 * (gx0 + gx1), my = 0.5 * (gy0 + gy1);
    this._paso(dt / 2, gx0, gy0, mx, my, prof + 1, tIni);
    this._paso(dt / 2, mx, my, gx1, gy1, prof + 1, tIni + dt / 2);
  }

  /** Newton-Raphson del paso. Deja el estado de prueba en uT, uCT y en el núcleo. → { ok, it, nR } */
  _intentar(dt, gx1, gy1) {
    const mod = this.mod, nd = mod.nd, nuc = this.nuc, m = mod.masa, Kpd = mod.Kpd;
    const { uD, vD, aD, uT, uCT, duD, duC, Rd, Fd, Fm, Pext, K, piv, tmp } = this;
    const a0 = this.a0, a1 = this.a1;
    const c0 = 4 / (dt * dt), c1 = 2 / dt;          // 1/(βΔt²) y γ/(βΔt) con γ = 1/2, β = 1/4
    const fac = 1 + c1 * a1;                        // K̃_e = (1 + a1·γ/(βΔt))·K_e (E8)
    let pMax = this.pgMax;
    for (let a = 0; a < nd; a += 3) {
      Pext[a] = -m[a] * gx1; Pext[a + 1] = -m[a + 1] * gy1; Pext[a + 2] = 0;
      pMax = Math.max(pMax, Math.abs(Pext[a]), Math.abs(Pext[a + 1]));
    }
    const tolR = this.o.tol * Math.max(pMax, 1);
    // Predictor. Con la tangente comprometida (si es del mismo Δt): el incremento lineal de Newmark,
    //   K_ef·Δu = P_n+1 − M·ü(u_n) − a0·M·u̇(u_n) − (F_n − 2·D_n) − K_PΔ·u_n − F_m,n,
    // con ü(u_n) = −(4/Δt)·u̇_n − ü_n, u̇(u_n) = −u̇_n y D_n la fuerza de amortiguamiento de los elementos (su momento
    // en u_n con la historia del paso nuevo es M_n − 2·D_n, E8). Es la forma incremental clásica,
    // K̂·Δu = ΔP + (4M/Δt + 2C)·u̇_n + 2M·ü_n, así que un paso elástico converge en la primera evaluación. Si no,
    // aceleración nula al final del paso. Los condensados siguen la condensación de la última tangente (un pórtico
    // elástico arranca en equilibrio y no necesita su solución en banda).
    if (this.facUlt === fac) {
      K.set(nuc.rigidezDiafragma(fac));
      Fm.fill(0);
      evaluarMuros(mod, uD, this.dmaxM, this.mur, Fm, K);
      for (let a = 0; a < nd; a++) {
        let sKp = 0;
        const fila = a * nd;
        for (let b = 0; b < nd; b++) { const kp = Kpd[fila + b]; sKp += kp * uD[b]; K[fila + b] += kp; }
        Rd[a] = Pext[a] - m[a] * (-2 * c1 * vD[a] - aD[a] - a0 * vD[a]) - (this.FdN[a] - 2 * this.DdN[a]) - sKp - Fm[a];
        K[fila + a] += m[a] * (c0 + c1 * a0);
      }
      if (!factorLU(K, nd, piv)) throw new ErrorMotor('interno', 'la rigidez efectiva del paso es singular', { dt_s: dt });
      resolverLU(K, nd, piv, Rd, duD, tmp);
    } else {
      for (let a = 0; a < nd; a++) duD[a] = dt * vD[a] + 0.25 * dt * dt * aD[a];
    }
    for (let a = 0; a < nd; a++) uT[a] = uD[a] + duD[a];
    uCT.set(this.uC);
    nuc.predecirCondensados(duD, uCT);
    this.facUlt = fac;
    const omitir = 1e-3 * tolR;
    let nR = Infinity;
    for (let it = 1; it <= this.o.maxIter; it++) {
      try {
        nuc.evaluar(uT, uCT, fac, a1, dt);
        K.set(nuc.rigidezDiafragma(fac));
      } catch (e) {
        // retorno sin conjunto activo o pórtico inestable con este Δu: se trata como paso sin converger (se parte)
        if (e instanceof ErrorMotor && e.codigo === 'interno') return { ok: false, it, nR: Infinity };
        throw e;
      }
      Fm.fill(0);
      evaluarMuros(mod, uT, this.dmaxM, this.mur, Fm, K);
      Fd.fill(0);
      nuc.fuerzaDiafragma(Fd);
      nR = 0;
      for (let a = 0; a < nd; a++) {
        const du = uT[a] - uD[a];
        const acc = c0 * du - 2 * c1 * vD[a] - aD[a];
        const vel = c1 * du - vD[a];
        let sKp = 0;
        const fila = a * nd;
        for (let b = 0; b < nd; b++) { const kp = Kpd[fila + b]; sKp += kp * uT[b]; K[fila + b] += kp; }
        const r = Pext[a] - m[a] * (acc + a0 * vel) - sKp - Fm[a] - Fd[a];
        const ra = r < 0 ? -r : r;
        if (ra > nR) nR = ra;
        Rd[a] = r;
        K[fila + a] += m[a] * (c0 + c1 * a0);
      }
      const nRc = nuc.residuoCondensado(Rd, 1, false, omitir);
      if (nRc > nR) nR = nRc;
      if (!factorLU(K, nd, piv)) throw new ErrorMotor('interno', 'la rigidez efectiva del paso es singular', { dt_s: dt });
      resolverLU(K, nd, piv, Rd, duD, tmp);
      let mdu = nuc.recuperar(duD, duC);
      for (let a = 0; a < nd; a++) { const x = duD[a] < 0 ? -duD[a] : duD[a]; if (x > mdu) mdu = x; }
      if (nR <= tolR && mdu <= TOL_DU) return { ok: true, it, nR };
      if (!Number.isFinite(mdu)) return { ok: false, it, nR };
      for (let a = 0; a < nd; a++) uT[a] += duD[a];
      for (let a = 0; a < uCT.length; a++) uCT[a] += duC[a];
    }
    return { ok: false, it: this.o.maxIter, nR };
  }

  /** Compromete el paso convergido: energía por trapecios, rótulas, mampostería, equipos y estado de Newmark. */
  _comprometer(dt, gx0, gy0, gx1, gy1, tFin) {
    const mod = this.mod, nd = mod.nd, m = mod.masa, nuc = this.nuc;
    const { uD, vD, aD, uT, vN, aN, Fr, FrAnt, Fd, Fm } = this;
    const c0 = 4 / (dt * dt), c1 = 2 / dt;
    const E = this.E;
    let dEin = 0, dEa0 = 0, dEdef = 0;
    for (let a = 0; a < nd; a++) {
      const du = uT[a] - uD[a];
      aN[a] = c0 * du - 2 * c1 * vD[a] - aD[a];
      vN[a] = c1 * du - vD[a];
      dEa0 += du * this.a0 * m[a] * 0.5 * (vD[a] + vN[a]);
      let sKp = 0;
      for (let b = 0; b < nd; b++) sKp += mod.Kpd[a * nd + b] * uT[b];
      Fr[a] = Fd[a] + Fm[a] + sKp;                  // fuerza restauradora condensada + P-Delta (control de E_deformación)
      dEdef += du * 0.5 * (FrAnt[a] + Fr[a]);
    }
    for (let a = 0; a < nd; a += 3) dEin -= m[a] * ((uT[a] - uD[a]) * 0.5 * (gx0 + gx1) + (uT[a + 1] - uD[a + 1]) * 0.5 * (gy0 + gy1));
    E.entrada += dEin; E.a0 += dEa0; E.def += dEdef;
    // rótulas: primera fluencia y bits de este Δt (cualquier subpaso)
    const tipoT = nuc.tipoT, fluyo = this.fluyo, tpf = this.env.t_primera_fluencia;
    for (let h = 0; h < tipoT.length; h++) {
      if (tipoT[h] === ENVOLVENTE) { fluyo[h] = 1; if (tpf[h] < 0) tpf[h] = tFin; }
    }
    const inc = nuc.comprometer(dt, this.a1, this.DdN);
    this.FdN.set(Fd);
    E.hist += inc.hist; E.amortEl += inc.amort;
    // mampostería: trabajo por trapecios y deriva máxima
    const mur = this.mur;
    for (let i = 0; i < mod.muros.length; i++) {
      this.Wm[i] += (mur.D[i] - this.DmAnt[i]) * 0.5 * (this.FmAnt[i] + mur.F[i]);
      this.FmAnt[i] = mur.F[i]; this.DmAnt[i] = mur.D[i]; this.dmaxM[i] = mur.dmax[i];
    }
    // equipos (aceleración del diafragma al inicio y al final del subpaso)
    if (this.equipos.length) {
      const ep = this.estadoPiso;
      ep.dt = dt; ep.ag_ini[0] = gx0; ep.ag_ini[1] = gy0; ep.ag_fin[0] = gx1; ep.ag_fin[1] = gy1; ep.a_ini = aD; ep.a_fin = aN;
      riesgoEquipos(ep, null, this.equipos);
    }
    uD.set(uT); this.uC.set(this.uCT); vD.set(vN); aD.set(aN); FrAnt.set(Fr);
  }

  // ---- energía ------------------------------------------------------------------------------------------------
  _energias() {
    const mod = this.mod, nd = mod.nd, m = mod.masa, E = this.E;
    let Ecin = 0;
    for (let a = 0; a < nd; a++) Ecin += 0.5 * m[a] * this.vD[a] * this.vD[a];
    let Eel = this.nuc.energiaElastica() - this.EelG;
    // trabajo de las cargas de gravedad sobre los gdl condensados que se mueven (7.4)
    const Pg = mod.Pg;
    for (let i = 0; i < Pg.length; i++) Eel -= Pg[i] * (this.uC[i] - this.uCG[i]);
    // mampostería: ½·F·Δ es lo recuperable (descarga orientada al origen); el resto de su trabajo es histerético
    let EmEl = -this.EmG, Wm = 0;
    for (let i = 0; i < mod.muros.length; i++) { EmEl += 0.5 * this.FmAnt[i] * this.DmAnt[i]; Wm += this.Wm[i]; }
    Eel += EmEl;
    const Ehist = E.hist + (Wm - EmEl);
    const Wpd = 0.5 * cuadratica(mod.Kpd, this.uD, nd) - this.WpdG;
    const Eam = E.a0 + E.amortEl;
    return { entrada: E.entrada, cinetica: Ecin, elastica: Eel, amortiguada: Eam, histeretica: Ehist, pdelta: Wpd, deformacion: E.def, amortEl: E.amortEl };
  }

  // ---- lo que se evalúa en cada Δt (y se escribe si es instante de salida) ---------------------------------------
  _evaluar(i, salida) {
    const mod = this.mod, o = this.o, nd = mod.nd, N = mod.N, nE = mod.nE, el = mod.el, nuc = this.nuc;
    const t = i * o.dt;
    const gx = this.agx[i], gy = this.agy[i];
    const uD = this.uD, aD = this.aD, env = this.env;
    // diafragmas: desplazamientos y aceleraciones absolutas
    for (let a = 0; a < nd; a++) {
      const ua = Math.abs(uD[a]);
      if (ua > env.u_max[a]) env.u_max[a] = ua;
      const aa = Math.abs(aD[a] + (a % 3 === 0 ? gx : a % 3 === 1 ? gy : 0));
      if (aa > env.a_abs_max[a]) env.a_abs_max[a] = aa;
    }
    // derivas por pórtico (componentes) y su envolvente
    const der = this.der;
    der.fill(0);
    const EI = this.entI, EC = this.entC;
    for (let q = 0; q < this.nEnt; q++) {
      const o7 = 7 * q, g = EI[o7 + 6];
      const d1 = uD[EI[o7]] + EC[2 * q] * uD[EI[o7 + 1]];
      const d0 = EI[o7 + 2] >= 0 ? uD[EI[o7 + 2]] + EC[2 * q + 1] * uD[EI[o7 + 3]] : 0;
      const dr = Math.abs(d1 - d0) / mod.niveles[g].h;
      const k = 2 * g + EI[o7 + 5];
      if (dr > der[k]) der[k] = dr;
      const kp = EI[o7 + 4] * N + g;
      if (dr > this.envPort[kp]) this.envPort[kp] = dr;
    }
    for (let k = 0; k < 2 * N; k++) if (der[k] > env.deriva_max[k]) { env.deriva_max[k] = der[k]; env.t_deriva_max[k] = t; }
    // deriva vectorial en los vértices del contorno (E9) y deriva del centro de masa (índice de estabilidad)
    const dvec = this.dvec, pvec = this.pvec;
    derivaVectorial(mod, uD, dvec, pvec);
    for (let g = 0; g < N; g++) {
      const nv = mod.niveles[g], ab = nv.abajo, b = 3 * g;
      const nb = ab >= 0 ? mod.niveles[ab] : null, bb = 3 * ab;
      const mx = dvec[g];
      if (mx > env.deriva_vector_max[g]) { env.deriva_vector_max[g] = mx; env.punto_deriva_vector[2 * g] = pvec[2 * g]; env.punto_deriva_vector[2 * g + 1] = pvec[2 * g + 1]; env.t_deriva_vector_max[g] = t; }
      let cx = uD[b], cy = uD[b + 1];
      if (nb) { cx -= uD[bb] - (nv.yc - nb.yc) * uD[bb + 2]; cy -= uD[bb + 1] + (nv.xc - nb.xc) * uD[bb + 2]; }
      if (Math.abs(cx) > this.DcmMax[2 * g]) this.DcmMax[2 * g] = Math.abs(cx);
      if (Math.abs(cy) > this.DcmMax[2 * g + 1]) this.DcmMax[2 * g + 1] = Math.abs(cy);
    }
    // elementos
    const Q = nuc.Q, thp = nuc.thp, bits = this.bits, fluyo = this.fluyo, Vp = this.Vpiso;
    Vp.fill(0);
    let Vbx = 0, Vby = 0, Tq = 0;
    const R = this.R, H = this.historia, j = this.jSal, oS = j * nE;
    for (let ie = 0; ie < nE; ie++) {
      const Mi = Q[3 * ie], Mj = Q[3 * ie + 1], Nx = Q[3 * ie + 2];
      const Lf = el.Lf[ie], wl = 0.5 * el.w[ie] * Lf;
      const Vm = (Mi + Mj) / Lf, Vi = Vm - wl, Vj = Vm + wl;
      const aVi = Math.abs(Vi), aVj = Math.abs(Vj);
      const Va = aVi >= aVj ? aVi : aVj;
      const tpi = thp[2 * ie], tpj = thp[2 * ie + 1], ati = Math.abs(tpi), atj = Math.abs(tpj);
      const aMi = Math.abs(Mi), aMj = Math.abs(Mj);
      const fl = (aMi > aMj ? aMi : aMj) / el.Mn[ie];
      const co = Va / el.Vn[ie];
      const ro = (ati > atj ? ati : atj) / el.IO[ie];
      const dcm = fl >= co ? (fl >= ro ? fl : ro) : co >= ro ? co : ro;
      if (dcm > env.dc_max[ie]) { env.dc_max[ie] = dcm; env.t_dc_max[ie] = t; env.gobierna[ie] = fl >= co && fl >= ro ? 0 : co >= ro ? 1 : 2; }
      if (aMi > env.Mi_max[ie]) env.Mi_max[ie] = aMi;
      if (aMj > env.Mj_max[ie]) env.Mj_max[ie] = aMj;
      if (Va > env.V_max[ie]) env.V_max[ie] = Va;
      if (Nx < env.N_min[ie]) env.N_min[ie] = Nx;
      if (Nx > env.N_max[ie]) env.N_max[ie] = Nx;
      if (ati > env.thp_max[2 * ie]) env.thp_max[2 * ie] = ati;
      if (atj > env.thp_max[2 * ie + 1]) env.thp_max[2 * ie + 1] = atj;
      let b = 0;
      if (fluyo[2 * ie]) b |= B_FLU_I;
      if (fluyo[2 * ie + 1]) b |= B_FLU_J;
      if (el.conLimites[ie]) {
        if (ati > el.IO[ie]) b |= B_IO_I;
        if (atj > el.IO[ie]) b |= B_IO_J;
        if (ati > el.LS[ie]) b |= B_LS_I;
        if (atj > el.LS[ie]) b |= B_LS_J;
        if ((ati > atj ? ati : atj) > el.CP[ie]) b |= B_CP;
      }
      if (Va > el.Vn[ie]) b |= B_V;
      bits[ie] |= b;
      // cortantes de entrepiso de los elementos verticales (V = (Mi + Mj)/L_f, positivo con deriva positiva)
      if (this.vert[ie]) {
        const g = el.gPiso[ie], d = this.dirE[ie];
        Vp[2 * g + d] += Vm;
        if (el.piso[ie] === 1) {
          if (d === 0) { Vbx += Vm; Tq -= (this.cE[ie] - this.y0) * Vm; } else { Vby += Vm; Tq += (this.cE[ie] - this.x0) * Vm; }
        }
      }
      if (salida) {
        R.dc[oS + ie] = aU8(dcm); R.dc_flexion[oS + ie] = aU8(fl); R.dc_cortante[oS + ie] = aU8(co); R.dc_rotacion[oS + ie] = aU8(ro);
        R.rotulas[oS + ie] = bits[ie];
        H.Mi[oS + ie] = Mi; H.Mj[oS + ie] = Mj; H.V[oS + ie] = aVi >= aVj ? Vi : Vj; H.N[oS + ie] = Nx;
        H.thp_i[oS + ie] = tpi; H.thp_j[oS + ie] = tpj; H.dc[oS + ie] = dcm;
      }
    }
    fluyo.fill(0);
    // mampostería: deriva y fuerza en su entrepiso
    for (let im = 0; im < mod.muros.length; im++) {
      const mu = mod.muros[im];
      const dm = Math.abs(this.DmAnt[im]) / mu.h;
      if (dm > this.derivaMuro[im]) this.derivaMuro[im] = dm;
      const F = this.FmAnt[im];
      Vp[2 * mu.g + mu.dir] += F;
      if (mod.niveles[mu.g].abajo < 0) {
        if (mu.dir === 0) { Vbx += F; Tq -= (mu.c - this.y0) * F; } else { Vby += F; Tq += (mu.c - this.x0) * F; }
      }
    }
    for (let k = 0; k < 2 * N; k++) { const v = Math.abs(Vp[k]); if (v > this.VpisoMax[k]) this.VpisoMax[k] = v; }
    // balance de energía (las dos igualdades del 7.4)
    const en = this._energias();
    const aE = Math.abs(en.entrada);
    if (aE > this.EinMax) this.EinMax = aE;
    const dE = Math.abs(en.entrada - (en.cinetica + en.amortiguada + en.elastica + en.histeretica + en.pdelta));
    const dD = Math.abs(en.deformacion - (en.elastica + en.amortEl + en.histeretica + en.pdelta));
    if (dE > this.desbE) this.desbE = dE;
    if (dD > this.desbD) this.desbD = dD;
    if (!salida) return;
    // ---- salida j -------------------------------------------------------------------------------------------
    R.t[j] = j * o.dtSal; H.t[j] = R.t[j];
    R.ag[2 * j] = gx; R.ag[2 * j + 1] = gy;
    for (let a = 0; a < nd; a++) {
      R.u[j * nd + a] = uD[a];
      R.a_abs[j * nd + a] = aD[a] + (a % 3 === 0 ? gx : a % 3 === 1 ? gy : 0);
    }
    const nN = mod.nN, uC = this.uC;
    for (let k = 0; k < nN; k++) {
      R.giros[j * nN + k] = this.nodoT[k] >= 0 ? uC[this.nodoT[k]] : 0;
      R.v_nodos[j * nN + k] = this.nodoV[k] >= 0 ? uC[this.nodoV[k]] : 0;
    }
    bits.fill(0);
    for (let k = 0; k < 2 * N; k++) R.derivas[2 * N * j + k] = der[k];
    for (let g = 0; g < N; g++) R.derivas_vector[N * j + g] = dvec[g];
    R.cortante_basal[3 * j] = Vbx; R.cortante_basal[3 * j + 1] = Vby; R.cortante_basal[3 * j + 2] = Tq;
    const e6 = R.energia, o6 = 6 * j;
    e6[o6] = en.entrada; e6[o6 + 1] = en.cinetica; e6[o6 + 2] = en.elastica; e6[o6 + 3] = en.amortiguada; e6[o6 + 4] = en.histeretica; e6[o6 + 5] = en.pdelta;
    this.jSal = j + 1;
  }

  /** Resultados del 7.6 (con { parcial: true }, solo las salidas ya escritas). */
  resultados({ parcial = false } = {}) {
    const mod = this.mod, o = this.o, N = mod.N, nE = mod.nE, nN = mod.nN;
    const nt = parcial ? this.jSal : o.nt;
    const R = this.R, H = this.historia;
    const corta = (a, porPaso) => (nt === o.nt ? a : a.slice(0, nt * porPaso));
    // rotación plástica de los elementos que fluyen alguna vez, en 10⁻⁵ rad (Int16)
    const fluyen = [];
    for (let ie = 0; ie < nE; ie++) {
      if (this.env.t_primera_fluencia[2 * ie] >= 0 || this.env.t_primera_fluencia[2 * ie + 1] >= 0 || this.env.thp_max[2 * ie] > 0 || this.env.thp_max[2 * ie + 1] > 0) fluyen.push(ie);
    }
    const k = fluyen.length;
    const valores = new Int16Array(nt * k * 2);
    for (let it = 0; it < nt; it++) {
      fluyen.forEach((ie, jj) => {
        valores[(it * k + jj) * 2] = aI16(H.thp_i[it * nE + ie]);
        valores[(it * k + jj) * 2 + 1] = aI16(H.thp_j[it * nE + ie]);
      });
    }
    const env = {};
    for (const [c, v] of Object.entries(this.env)) env[c] = Float32Array.from(v, (x) => (Number.isFinite(x) ? x : 0));
    // índice de estabilidad con las envolventes: Q_k = P_k·Δ_k,max/(V_k,max·h_k) (NSR-10 A.6.2.3)
    let indice = 0;
    for (let g = 0; g < N; g++) {
      for (let c = 0; c < 2; c++) {
        const V = this.VpisoMax[2 * g + c];
        if (V > 0) indice = Math.max(indice, (this.Parriba[g] * this.DcmMax[2 * g + c]) / (V * mod.niveles[g].h));
      }
    }
    const muros = mod.muros.map((mu, im) => {
      let estado = 'sin_dano';
      const d = Math.fround(this.derivaMuro[im]);
      for (const ed of mu.estados) if (d >= ed.deriva) estado = ed.nombre;
      return { id: mu.id, aislado: mu.aislado, deriva_max: d, estado };
    });
    const ref = this.EinMax > 0 ? this.EinMax : 1;
    const am = this.am;
    const res = {
      version: VERSION, id: o.id, params: o.params,
      opciones: { dt_s: o.dt, dt_salida_s: o.dtSal, duracion_s: o.duracion, calidad: o.calidad, angulo_deg: o.angulo, escala: o.escala },
      duracion_calculo_ms: Math.max(0, ahora() - this.t0),
      factor_escala: o.factor_escala, iteraciones_escala: o.iteraciones_escala,
      amortiguamiento: { a0: am.a0, a1: am.a1, periodos_ancla_s: [...am.periodos_ancla_s], xi_modos: Float32Array.from(am.xi_modos) },
      t: corta(R.t, 1), ag: corta(R.ag, 2), u: corta(R.u, N * 3), a_abs: corta(R.a_abs, N * 3),
      giros: corta(R.giros, nN), v_nodos: corta(R.v_nodos, nN),
      dc: corta(R.dc, nE), dc_flexion: corta(R.dc_flexion, nE), dc_cortante: corta(R.dc_cortante, nE), dc_rotacion: corta(R.dc_rotacion, nE),
      rotulas: corta(R.rotulas, nE),
      thp: { elementos: Int32Array.from(fluyen), valores },
      derivas: corta(R.derivas, N * 2), derivas_vector: corta(R.derivas_vector, N),
      derivas_porticos_env: Float32Array.from(this.envPort),
      cortante_basal: corta(R.cortante_basal, 3), energia: corta(R.energia, 6),
      envolventes: env,
      muros_mamposteria: muros,
      equipos: resumenEquipos(this.equipos),
      calidad_numerica: {
        pasos: this.cal.pasos, iteraciones_promedio: this.cal.pasos ? this.cal.iter / this.cal.pasos : Math.max(1, this.cal.iter),
        subdivisiones: this.cal.subdivisiones, no_convergidos: this.cal.no_convergidos,
        error_energia_max: this.desbE / ref, error_deformacion_max: this.desbD / ref, indice_estabilidad_max: indice,
      },
    };
    if (o.origen_registro) res.origen_registro = o.origen_registro;
    if (parcial) res.parcial = { salidas: nt, t_s: this.t_s };
    return res;
  }
}

const aU8 = (x) => { const v = Math.round(100 * x); return v > 255 ? 255 : v < 0 ? 0 : v; };
const aI16 = (x) => { const v = Math.round(x * 1e5); return v > 32767 ? 32767 : v < -32768 ? -32768 : v; };

function cuadratica(K, u, n) {
  let s = 0;
  for (let a = 0; a < n; a++) { let r = 0; for (let b = 0; b < n; b++) r += K[a * n + b] * u[b]; s += u[a] * r; }
  return s;
}

// =================================================================================================================
// API del 7.4
// =================================================================================================================
/**
 * Análisis no lineal en el tiempo de corrido (dentro del trabajador). registro: { dt, ax, ay } (m/s²) — la
 * componente 1 y la 2, antes de girar y escalar. op: las del 7.4 (dt_s, dt_salida_s, duracion_s, angulo_deg, escala,
 * calidad, tolerancia, max_iter, max_subdiv, equipos, guardar_serie_completa) y, para Resultados, params, id,
 * origen_registro y factor_escala/iteraciones_escala (escala 'nsr10'). alProgreso(fraccion, t_s) cada ≥ 250 ms.
 * → { resultados: Resultados (7.6), historia: { t, Mi, Mj, V, N, thp_i, thp_j, dc (Float32, nt·nE), ids, u_completa } }
 */
export function analizar(modelo, registro, op = {}, alProgreso, senal) {
  if (senal?.aborted) throw abortado();
  const an = new Analisis(modelo, registro, op);
  let ultimo = ahora();
  while (!an.terminado) {
    an.avanzar(PASOS_POR_TANDA);
    if (alProgreso && ahora() - ultimo >= an.o.intervaloProgreso) { ultimo = ahora(); alProgreso(an.fraccion, an.t_s); }
  }
  return { resultados: an.resultados(), historia: an.historia };
}

const cederPorDefecto = () => new Promise((ok) => setTimeout(ok, 0));

/**
 * Lo mismo, cediendo al bucle de eventos cada ≈ presupuesto_ms de cálculo (respaldo en el hilo principal, 7.5): así no
 * hay más de ≈ 12 ms seguidos sin dibujar. Revisa `senal` (AbortSignal) entre tramos. Mismos resultados bit a bit.
 */
export async function analizarPorTramos(modelo, registro, op = {}, { presupuesto_ms = 12, ceder = cederPorDefecto, alProgreso, senal } = {}) {
  if (senal?.aborted) throw abortado();
  const an = new Analisis(modelo, registro, op);
  // el armado (gravedad, cajas de resultados de ≈ 30 MB) va en su propio tramo
  await ceder();
  if (senal?.aborted) throw abortado();
  let ultimo = ahora();
  while (!an.terminado) {
    const t0 = ahora();
    // de a un paso: un paso frío (primera factorización de los pórticos, compilación) puede tardar más que el
    // presupuesto, y con tandas de 10 el tramo llegaba a ≈ 25 ms en Chromium (qa_worker.mjs); los pasos son los mismos
    do an.avanzar(1); while (!an.terminado && ahora() - t0 < presupuesto_ms);
    if (alProgreso && ahora() - ultimo >= an.o.intervaloProgreso) { ultimo = ahora(); alProgreso(an.fraccion, an.t_s); }
    if (!an.terminado) {
      await ceder();
      if (senal?.aborted) throw abortado();
    }
  }
  return { resultados: an.resultados(), historia: an.historia };
}

// =================================================================================================================
// Oscilador de un grado (pruebas cerradas T1-T6)
// =================================================================================================================
/**
 * Oscilador de un grado con Newmark de aceleración promedio y Newton-Raphson:
 *   m·ü + c·u̇ + fs(u) − (P/h)·u = p(t) − m·üg(t)
 * fs: elastoplástico con endurecimiento cinemático; rigidez después de la fluencia alfa·k (alfa < 1); fy = Infinity
 * para lineal. P_h = P/h: P-Delta (rigidez geométrica −P/h). ag y p: arreglos de n + 1 valores (o null).
 * → { t, u, v, a_abs, fs, energia: { entrada, cinetica, amortiguada, elastica, histeretica, pdelta, deformacion },
 *     error_energia, error_deformacion } con la energía por trapecios sobre Δu, relativa al estado inicial.
 */
export function osciladorNewmark({ m, c = 0, k, fy = Infinity, alfa = 0, dt, n, ag = null, p = null, u0 = 0, v0 = 0, P_h = 0, tolerancia = 1e-12, max_iter = 50 }) {
  if (!(m > 0 && k > 0 && dt > 0 && n >= 1)) throw new Error('osciladorNewmark: m, k, dt > 0 y n ≥ 1');
  if (!(alfa >= 0 && alfa < 1)) throw new Error('osciladorNewmark: 0 ≤ alfa < 1');
  // endurecimiento cinemático de la parte plástica Hk con k·Hk/(k + Hk) = alfa·k
  const Hk = (alfa * k) / (1 - alfa);
  const AG = (i) => (ag ? ag[i] ?? 0 : 0), PP = (i) => (p ? p[i] ?? 0 : 0);
  const t = new Float64Array(n + 1), u = new Float64Array(n + 1), v = new Float64Array(n + 1), a_abs = new Float64Array(n + 1), fs = new Float64Array(n + 1);
  const en = {};
  for (const x of ['entrada', 'cinetica', 'amortiguada', 'elastica', 'histeretica', 'pdelta', 'deformacion']) en[x] = new Float64Array(n + 1);
  let up = 0, beta = 0;
  const resorte = (uu, upN, betaN) => {
    const f = k * (uu - upN), xi = f - betaN;
    if (!(Math.abs(xi) > fy)) return { f, kt: k, up: upN, beta: betaN };
    const s = Math.sign(xi), dl = (Math.abs(xi) - fy) / (k + Hk);
    return { f: f - k * s * dl, kt: (k * Hk) / (k + Hk), up: upN + s * dl, beta: betaN + Hk * s * dl };
  };
  let r0 = resorte(u0, 0, 0);
  up = r0.up; beta = r0.beta;
  u[0] = u0; v[0] = v0; fs[0] = r0.f;
  let acc = (PP(0) - m * AG(0) - c * v0 - r0.f + P_h * u0) / m;
  a_abs[0] = acc + AG(0);
  const Eel0 = (r0.f * r0.f) / (2 * k), Ek0 = 0.5 * m * v0 * v0, Wp0 = -0.5 * P_h * u0 * u0;
  let Ein = 0, Ed = 0, Eh = 0, Edef = 0, maxE = 0, desbE = 0, desbD = 0;
  const c0 = 4 / (dt * dt), c1 = 2 / dt;
  for (let i = 0; i < n; i++) {
    const un = u[i], vn = v[i], an = acc;
    const P1 = PP(i + 1) - m * AG(i + 1);
    let uu = un, r = null, conv = false;
    for (let it = 0; it < max_iter; it++) {
      r = resorte(uu, up, beta);
      const aa = c0 * (uu - un) - 2 * c1 * vn - an, vv = c1 * (uu - un) - vn;
      const R = P1 - m * aa - c * vv - r.f + P_h * uu;
      const Kt = m * c0 + c * c1 + r.kt - P_h;
      const du = R / Kt;
      uu += du;
      if (Math.abs(du) <= tolerancia * Math.max(1e-6, Math.abs(uu)) && Math.abs(R) <= tolerancia * Math.max(Math.abs(P1), k * Math.abs(uu), 1e-9)) { conv = true; r = resorte(uu, up, beta); break; }
    }
    if (!conv) r = resorte(uu, up, beta);
    const aa = c0 * (uu - un) - 2 * c1 * vn - an, vv = c1 * (uu - un) - vn;
    const du = uu - un;
    Ein += du * 0.5 * (PP(i) + PP(i + 1) - m * (AG(i) + AG(i + 1)));
    Ed += du * c * 0.5 * (vn + vv);
    Eh += (r.up - up) * 0.5 * (fs[i] + r.f);
    Edef += du * 0.5 * (fs[i] + r.f - P_h * (un + uu));
    up = r.up; beta = r.beta;
    u[i + 1] = uu; v[i + 1] = vv; acc = aa; fs[i + 1] = r.f; t[i + 1] = (i + 1) * dt; a_abs[i + 1] = aa + AG(i + 1);
    const Ek = 0.5 * m * vv * vv - Ek0, Eel = (r.f * r.f) / (2 * k) - Eel0, Wp = -0.5 * P_h * uu * uu - Wp0;
    en.entrada[i + 1] = Ein; en.cinetica[i + 1] = Ek; en.amortiguada[i + 1] = Ed; en.elastica[i + 1] = Eel;
    en.histeretica[i + 1] = Eh; en.pdelta[i + 1] = Wp; en.deformacion[i + 1] = Edef;
    maxE = Math.max(maxE, Math.abs(Ein), Ek0 + Eel0);
    desbE = Math.max(desbE, Math.abs(Ein - (Ek + Ed + Eel + Eh + Wp)));
    desbD = Math.max(desbD, Math.abs(Edef - (Eel + Eh + Wp)));
  }
  const ref = maxE > 0 ? maxE : 1;
  return { t, u, v, a_abs, fs, energia: en, error_energia: desbE / ref, error_deformacion: desbD / ref };
}
