// Exporta un caso del motor sísmico para la validación con OpenSees (contrato de la torre, 7.9; data/sismo/ESQUEMA.md,
// «Validación con OpenSees»): el registro tal como lo integra el motor (mismo Δt, girado, escalado y, en calidad baja,
// filtrado y diezmado), a0 y a1, el modelo de referencia con las propiedades que el motor usa de verdad (para que
// scripts/sismo/validar_opensees.py arme la réplica sin reimplementar la síntesis ni las reglas de las secciones) y los
// resultados del motor sobre ese mismo caso.
//
// Uso:
//   node scripts/sismo/exportar_caso.mjs <escenario> <salida.json> [opciones]
//     <escenario>      id de amenaza.json → escenarios (nido_2015, cimitarra, local_hip, …) o «ninguno» (solo el modelo)
//     --estructura R   estructura (por defecto data/sismo/torre_hospital_estructura.json)
//     --escala X       número o nsr10 (por defecto 1)
//     --angulo G       dirección de la componente 1, grados antihorarios desde el este (por defecto 0)
//     --calidad C      normal | baja
//     --duracion S     s de análisis (por defecto, la del registro)
//     --sin-pdelta     arma el modelo sin P-Delta
//     --histeresis H   bilineal | clough (por defecto, la de cada sección)
//     --semilla N, --vs30 V   cambian los del escenario (por defecto, los de amenaza.json → controles)
//     --sin-analisis   no corre el motor (solo modelo y registro)
//
// Unidades: kN, m, s, t (= kN·s²/m), rad. Los ángulos y momentos de extremo siguen la convención del esquema: en el
// plano de cada pórtico, s a la derecha y z arriba, antihorario positivo (en un pórtico X eso es −θy global; en uno Y,
// +θx). Sale determinista (sin fechas): mismo caso, mismo archivo.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { crearMotor } from '../../web/js/sismo/motor.js';
import {
  armarModelo, gravedad, modos, amortiguamiento, rigidezLateral, rigidezPDelta, modosDe, resumenModelo, COLUMNA, VIGA, MURO, G,
} from '../../web/js/sismo/modelo.js';
import { SIN_ROTULA, BILINEAL, CLOUGH } from '../../web/js/sismo/histeresis.js';

const RAIZ = new URL('../../', import.meta.url);
const leer = (ruta) => JSON.parse(readFileSync(new URL(ruta, RAIZ), 'utf8'));

function argumentos(argv) {
  const pos = [], op = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { pos.push(a); continue; }
    const k = a.slice(2);
    if (k === 'sin-pdelta' || k === 'sin-analisis') op[k] = true;
    else op[k] = argv[++i];
  }
  return { pos, op };
}

const NOMBRE_TIPO = { [COLUMNA]: 'columna', [VIGA]: 'viga', [MURO]: 'muro_concreto' };
const NOMBRE_ROTULA = { [SIN_ROTULA]: 'ninguna', [BILINEAL]: 'bilineal', [CLOUGH]: 'clough' };
const lista = (a) => Array.from(a, (x) => (Number.isFinite(x) ? x : null));
const matriz = (K, n) => Array.from({ length: n }, (_, a) => Array.from(K.subarray(a * n, (a + 1) * n)));
const esNum = (x) => typeof x === 'number' && Number.isFinite(x);

/**
 * Propiedades de cada elemento tal como las usa modelo.js (mismas reglas: E del material en kPa, G = E/(2(1 + ν)),
 * I·factor_fisuracion, L_f = L − di − dj, k_e = 6EI/L_f o EI/lp en muros, H = α·k_e) más las que el motor ya armó
 * (f11, f12, kax, momentos de fluencia de cada extremo y su modelo), para que la réplica no las vuelva a deducir.
 */
function elementosDe(mod, est) {
  const el = mod.el, secs = est.secciones, mats = est.materiales;
  const fuente = [];
  for (const b of est.bloques) for (const p of b.porticos || []) for (const e of p.elementos || []) fuente.push(e);
  return fuente.map((e, ie) => {
    const sec = secs[e.seccion], mat = mats[sec.material];
    const Ec = (mat.Ec_MPa ?? mat.E_MPa ?? mat.Es_MPa) * 1000;
    const nu = esNum(mat.nu) ? mat.nu : 0.2;
    const [di, dj] = Array.isArray(e.brazo_rigido_m) ? e.brazo_rigido_m : [0, 0];
    const alfa = esNum(sec.endurecimiento) && sec.endurecimiento > 0 ? sec.endurecimiento : 1e-4;
    const rot = [0, 1].map((k) => {
      const h = 2 * ie + k;
      const modelo = el.rmod[h];
      if (modelo === SIN_ROTULA) return { modelo: 'ninguna' };
      const ke = el.H[h] / alfa;
      return { modelo: NOMBRE_ROTULA[modelo], sup: el.sup[h], inf: el.inf[h], H: el.H[h], ke, alfa };
    });
    const P = mod.porticos[el.port[ie]];
    return {
      id: el.id[ie], tipo: NOMBRE_TIPO[el.tipo[ie]], portico: P.id, i: e.i, j: e.j, nivel: el.info[ie].nivel,
      L: el.L[ie], Lf: el.Lf[ie], di, dj,
      E: Ec, G: Ec / (2 * (1 + nu)), A: sec.A, I_fis: sec.I * sec.factor_fisuracion, Av: esNum(sec.Av) && sec.Av > 0 ? sec.Av : null,
      w: el.w[ie], f11: el.f11[ie], f12: el.f12[ie], kax: el.kax[ie],
      rotula_i: rot[0], rotula_j: rot[1],
      Mn_e: el.Mn[ie], Vn_e: Number.isFinite(el.Vn[ie]) ? el.Vn[ie] : null, theta_p_IO: Number.isFinite(el.IO[ie]) ? el.IO[ie] : null,
    };
  });
}

function modeloDe(mod, est) {
  const nd = mod.nd;
  const g = gravedad(mod);
  const md = modos(mod, Math.min(12, nd));
  // modos sin P-Delta (rigidez elástica condensada sola), para separar las dos fuentes de diferencia
  const K = rigidezLateral(mod);
  const md0 = modosDe(K, mod.masa, nd, Math.min(12, nd));
  const KC = rigidezLateral(mod, undefined, { conMuros: false });
  return {
    G,
    niveles: mod.niveles.map((n) => ({
      id: n.id, bloque: n.bloque, g: n.g, abajo: n.abajo, z: n.z, h: n.h, masa_t: n.masa, Jz_t_m2: n.Jz, cm: [n.xc, n.yc], peso_kN: n.peso,
      contorno: n.contorno,
    })),
    porticos: mod.porticos.map((P) => ({
      id: P.id, bloque: P.bloque, direccion: P.dir === 0 ? 'x' : 'y', coordenada: P.c,
      nodos: P.nodos.map((n) => ({ id: n.id, s: n.s, nivel: n.nivel, z: n.z, apoyo: n.apoyo, carga_kN: n.carga, xyz: n.xyz })),
      elementos: Array.from({ length: P.e1 - P.e0 }, (_, k) => P.e0 + k),
    })),
    elementos: elementosDe(mod, est),
    muros_mamposteria: mod.muros.map((m) => ({ id: m.id, direccion: m.dir === 0 ? 'x' : 'y', coordenada: m.c, nivel_g: m.g, aislado: m.aislado, envolvente: m.env })),
    masa: lista(mod.masa),
    K_lateral: matriz(K, nd),                 // pórticos + mampostería que trabaja, condensada, sin P-Delta (estado de gravedad)
    K_porticos: matriz(KC, nd),               // solo pórticos: la parte que amortigua con a1
    K_PDelta: matriz(rigidezPDelta(mod), nd),
    modos: { periodos_s: md.periodos_s, formas: md.formas.map(lista), masa_participativa: md.masa_participativa, T1x: md.T1x, T1y: md.T1y },
    modos_sin_pdelta: { periodos_s: md0.periodos_s },
    gravedad: { uD: lista(g.uD), iteraciones: g.iteraciones, reaccion_vertical_kN: -Array.from(mod.Pg).reduce((s, x) => s + x, 0) },
    resumen: resumenModelo(mod),
    p_delta: mod.op.pDelta,
  };
}

/** Lo que la validación compara del motor (series a la salida, envolventes de cada Δt y desplazamientos de cada Δt). */
function resultadosDe(r, historia, mod) {
  const nE = mod.nE, env = r.envolventes;
  const fluyen = Array.from(r.thp.elementos, (ie) => mod.el.id[ie]);
  const tpf = [];
  for (let ie = 0; ie < nE; ie++) {
    const a = env.t_primera_fluencia[2 * ie], b = env.t_primera_fluencia[2 * ie + 1];
    const t = a >= 0 && b >= 0 ? Math.min(a, b) : a >= 0 ? a : b;
    if (t >= 0) tpf.push([mod.el.id[ie], t]);
  }
  const nt = r.t.length, E = r.energia;
  return {
    calidad_numerica: r.calidad_numerica, duracion_calculo_ms: r.duracion_calculo_ms, factor_escala: r.factor_escala, iteraciones_escala: r.iteraciones_escala,
    opciones: r.opciones,
    t: lista(r.t), u: lista(r.u), cortante_basal: lista(r.cortante_basal), derivas_vector: lista(r.derivas_vector), energia: lista(r.energia),
    energia_final_kJ: { entrada: E[6 * (nt - 1)], cinetica: E[6 * (nt - 1) + 1], elastica: E[6 * (nt - 1) + 2], amortiguada: E[6 * (nt - 1) + 3], histeretica: E[6 * (nt - 1) + 4], pdelta: E[6 * (nt - 1) + 5] },
    envolventes: {
      u_max: lista(env.u_max), deriva_vector_max: lista(env.deriva_vector_max), deriva_max: lista(env.deriva_max),
      punto_deriva_vector: lista(env.punto_deriva_vector), t_deriva_vector_max: lista(env.t_deriva_vector_max),
      a_abs_max: lista(env.a_abs_max), thp_max: lista(env.thp_max),
    },
    fluyen, primera_fluencia: tpf,
    u_completa: historia.u_completa ? lista(historia.u_completa) : null,
  };
}

async function principal() {
  const { pos, op } = argumentos(process.argv.slice(2));
  if (pos.length < 2) {
    console.error('uso: node scripts/sismo/exportar_caso.mjs <escenario|ninguno> <salida.json> [--estructura R] [--escala X|nsr10] [--angulo G] [--calidad normal|baja] [--duracion S] [--sin-pdelta] [--histeresis H] [--semilla N] [--vs30 V] [--sin-analisis]');
    process.exit(2);
  }
  const [idEsc, salida] = pos;
  const rutaE = op.estructura ?? 'data/sismo/torre_hospital_estructura.json';
  const textoE = readFileSync(resolve(rutaE), 'utf8');
  const est = JSON.parse(textoE);
  const am = leer('data/sismo/amenaza.json');
  const opcModelo = { histeresis: op.histeresis ?? null, noEstructurales: 'aislados', pDelta: op['sin-pdelta'] ? false : undefined };
  const mod = armarModelo(est, opcModelo);
  const am0 = amortiguamiento(mod);
  const caso = {
    version: 1,
    generado_por: 'scripts/sismo/exportar_caso.mjs',
    estructura: { ruta: rutaE, id: est.id ?? null, sha1: createHash('sha1').update(textoE).digest('hex') },
    escenario: null, opciones: null, registro: null,
    amortiguamiento: { a0: am0.a0, a1: am0.a1, periodos_ancla_s: am0.periodos_ancla_s, xi_modos: lista(am0.xi_modos), regla: am0.regla },
    modelo: modeloDe(mod, est),
    motor: null,
  };
  if (idEsc !== 'ninguno') {
    const e = am.escenarios.find((x) => x.id === idEsc);
    if (!e) throw new Error(`escenario «${idEsc}» no está en amenaza.json (${am.escenarios.map((x) => x.id).join(', ')})`);
    const params = {
      Mw: e.Mw, profundidad_km: e.profundidad_km, distancia_epicentral_km: e.distancia_epicentral_km,
      vs30_m_s: op.vs30 !== undefined ? Number(op.vs30) : am.controles.vs30_m_s.defecto,
      semilla: op.semilla !== undefined ? Number(op.semilla) : am.controles.semilla.defecto,
    };
    const escala = op.escala === undefined ? 1 : op.escala === 'nsr10' ? 'nsr10' : Number(op.escala);
    const opciones = { escala, angulo_deg: op.angulo !== undefined ? Number(op.angulo) : 0, calidad: op.calidad === 'baja' ? 'baja' : 'normal', guardar_serie_completa: true };
    if (op.duracion !== undefined) opciones.duracion_s = Number(op.duracion);
    const motor = crearMotor();
    await motor.iniciar({ estructura: est, amenaza: am, opciones: { histeresis: opcModelo.histeresis, pDelta: opcModelo.pDelta } });
    const r = await motor.analizar(params, opciones);
    const an = motor.ultimoAnalisis;
    // el registro tal como lo integró el motor: interpolado a cada Δt, girado y escalado (la misma cuenta que Analisis)
    const mov = await import('../../web/js/sismo/movimiento.js');
    let reg = an.registro;
    const dt = r.opciones.dt_s;
    if (r.opciones.calidad === 'baja') {
      const fx = mov.filtrarYDiezmar(reg.ax, reg.dt), fy = mov.filtrarYDiezmar(reg.ay, reg.dt);
      reg = { dt: fx.dt, ax: fx.a, ay: fy.a };
    }
    const sub = Math.round(reg.dt / dt), nReg = reg.ax.length;
    const nPasos = Math.round(r.opciones.duracion_s / dt);
    const th = (r.opciones.angulo_deg * Math.PI) / 180, c = Math.cos(th), s = Math.sin(th);
    const f = an.factor;
    const agx = new Float64Array(nPasos + 1), agy = new Float64Array(nPasos + 1);
    for (let i = 0; i <= nPasos; i++) {
      const q = i / sub, k = Math.floor(q);
      let a1 = 0, a2 = 0;
      if (k < nReg - 1) { const fr = q - k; a1 = fr === 0 ? reg.ax[k] : (1 - fr) * reg.ax[k] + fr * reg.ax[k + 1]; a2 = fr === 0 ? reg.ay[k] : (1 - fr) * reg.ay[k] + fr * reg.ay[k + 1]; }
      else if (k === nReg - 1 && q === k) { a1 = reg.ax[k]; a2 = reg.ay[k]; }
      agx[i] = f * (c * a1 - s * a2); agy[i] = f * (s * a1 + c * a2);
    }
    caso.escenario = { id: idEsc, nombre: e.nombre, params };
    caso.opciones = { ...r.opciones, factor: f, factor_escala: r.factor_escala, p_delta: mod.op.pDelta, histeresis: opcModelo.histeresis ?? 'la de cada sección' };
    caso.registro = { dt, n: nPasos + 1, agx: lista(agx), agy: lista(agy), pga_x_g: Math.max(...agx.map(Math.abs)) / G, pga_y_g: Math.max(...agy.map(Math.abs)) / G };
    if (!op['sin-analisis']) caso.motor = resultadosDe(r, motor.historia, motor.modelo);
  }
  writeFileSync(salida, JSON.stringify(caso));
  const q = caso.motor?.calidad_numerica;
  console.log(`${salida}: ${caso.modelo.elementos.length} elementos, ${caso.modelo.niveles.length} niveles; a0 = ${caso.amortiguamiento.a0.toFixed(5)}, a1 = ${caso.amortiguamiento.a1.toExponential(4)}` +
    (caso.registro ? `; registro de ${caso.registro.n} instantes a ${caso.registro.dt} s (factor ${caso.opciones.factor.toFixed(4)})` : '') +
    (q ? `; motor: ${q.pasos} pasos, ${caso.motor.fluyen.length} elementos con fluencia` : ''));
}

principal().catch((e) => { console.error(`exportar_caso: ${e.message}`); if (process.env.DEPURAR) console.error(e.stack); process.exit(1); });
