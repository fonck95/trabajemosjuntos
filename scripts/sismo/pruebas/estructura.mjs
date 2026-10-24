// Pruebas de la estructura real de la torre (data/sismo/torre_hospital_estructura.json, generada por
// scripts/sismo/estructura_torre.py) con el motor: T18 del contrato (7.8) y la verificación cruzada entre el análisis
// pseudotridimensional propio del prediseño (Python) y web/js/sismo/modelo.js, que usan la misma idealización.
//
//   T18  estructura real: nido_2015 y local_hip con Δt = 0,005 s, con y sin P-Delta: 0 pasos sin converger, errores de
//        energía < 1 %, validar_resultado pasa; reporta el índice de estabilidad máximo.
//   S1   la estructura cumple el esquema (validarEstructura: 0 errores, theta_y y theta_y_e ± 1 %).
//   S2   los 12 períodos del motor (rigidez inicial, sin P-Delta) son los del prediseño (< 10⁻³ relativo; las
//        propiedades del JSON van redondeadas a 5-6 cifras).
//   S3   períodos ancla de Rayleigh (E8): la regla del motor con periodos_ancla_s = null da los del archivo (< 10⁻³), y
//        el centro de rigidez de cada nivel del motor es el del prediseño (< 1 cm).
//   S4   gravedad: la suma de las cargas verticales del archivo (w_gravedad en las vigas y carga_kN en los nodos) es la
//        reacción vertical de la base en el análisis de gravedad del motor (equilibrio, 10⁻⁶).
//   S5   amortiguamiento con los muros de mampostería trabajando («Sin aislar», noEstructurales 'confinados'): las
//        anclas del archivo (del modelo con los muros aislados) no se usan; el motor ancla en T1 del modelo analizado y
//        ξ1 = 5 % exacto aunque la mampostería, que no amortigua, dé ≈ 60 % de la rigidez inicial (revisión A6).
import { crearMotor } from '../../../web/js/sismo/motor.js';
import { armarModelo, modos, amortiguamiento, resumenModelo, gravedad } from '../../../web/js/sismo/modelo.js';
import { validarEstructura, validarResultado } from '../validar_resultado.mjs';
import { leerJSON, caso, comprobar } from './_util.mjs';

const RUTA = 'data/sismo/torre_hospital_estructura.json';
const amenaza = () => leerJSON('data/sismo/amenaza.json');
const escenario = (am, id) => {
  const e = am.escenarios.find((x) => x.id === id);
  return { Mw: e.Mw, profundidad_km: e.profundidad_km, distancia_epicentral_km: e.distancia_epicentral_km,
    vs30_m_s: am.controles.vs30_m_s.defecto, semilla: am.controles.semilla.defecto };
};

async function t18() {
  const est = leerJSON(RUTA);
  const am = amenaza();
  const casos = [];
  for (const id of ['nido_2015', 'local_hip']) {
    for (const pDelta of [true, false]) {
      const m = crearMotor();
      await m.iniciar({ estructura: est, amenaza: am, opciones: { pDelta } });
      const r = await m.analizar(escenario(am, id), { dt_s: 0.005 });
      const v = validarResultado(r, est);
      const q = r.calidad_numerica;
      let dmax = 0;
      for (const x of r.envolventes.deriva_vector_max) dmax = Math.max(dmax, x);
      const ok = q.no_convergidos === 0 && q.error_energia_max < 0.01 && q.error_deformacion_max < 0.01 && v.errores.length === 0;
      casos.push(comprobar(`${id}, ${pDelta ? 'con' : 'sin'} P-Delta`, ok,
        `${q.pasos} pasos, ${q.no_convergidos} sin converger, error de energía ${q.error_energia_max.toExponential(2)} y de deformación ` +
        `${q.error_deformacion_max.toExponential(2)} (< 1 %), índice de estabilidad máximo ${q.indice_estabilidad_max.toFixed(4)}, ` +
        `deriva vectorial máxima ${(100 * dmax).toFixed(3)} %, validar_resultado: ${v.errores.length} errores` +
        (v.errores.length ? ` (${v.errores.slice(0, 2).join(' | ')})` : '')));
    }
  }
  return casos;
}

function s1() {
  const est = leerJSON(RUTA);
  const v = validarEstructura(est);
  let peor = 0;
  for (const f of v.theta) peor = Math.max(peor, Math.abs(f.error));
  return [
    comprobar('validarEstructura sin errores', v.errores.length === 0, v.errores.slice(0, 3).join(' | ') || `${v.avisos.length} avisos (nodos de muro en el centroide, fuera de los ejes)`),
    caso(`theta_y y theta_y_e en ${v.theta.length} comprobaciones`, peor, 0.01),
  ];
}

function s2() {
  const est = leerJSON(RUTA);
  const mod = armarModelo(est, { pDelta: false });
  const m = modos(mod, 12);
  const py = est.prediseno.periodos.modos.map((x) => x.T_s);
  let peor = 0;
  for (let i = 0; i < py.length; i++) peor = Math.max(peor, Math.abs(m.periodos_s[i] / py[i] - 1));
  return caso(`12 períodos: motor ${Array.from(m.periodos_s).slice(0, 3).map((x) => x.toFixed(4)).join(', ')} s… frente a ` +
    `prediseño ${py.slice(0, 3).map((x) => x.toFixed(4)).join(', ')} s…`, peor, 1e-3);
}

function s3() {
  const est = leerJSON(RUTA);
  const sin = { ...est, amortiguamiento: { ...est.amortiguamiento, periodos_ancla_s: null } };
  const am = amortiguamiento(armarModelo(sin));
  const [Ti, Tj] = est.amortiguamiento.periodos_ancla_s;
  const e1 = Math.max(Math.abs(am.periodos_ancla_s[0] / Ti - 1), Math.abs(am.periodos_ancla_s[1] / Tj - 1));
  const r = resumenModelo(armarModelo(est, { pDelta: false }));
  let e2 = 0;
  est.prediseno.centro_rigidez.forEach((c, k) => {
    e2 = Math.max(e2, Math.hypot(r.centro_rigidez[k][0] - c.centro_rigidez[0], r.centro_rigidez[k][1] - c.centro_rigidez[1]));
  });
  return [
    caso(`períodos ancla con la regla del motor (${am.periodos_ancla_s.map((x) => x.toFixed(4)).join(', ')} s) frente a los del archivo`, e1, 1e-3),
    caso('centro de rigidez de cada nivel: motor frente al prediseño (m)', e2, 0.01),
  ];
}

function s4() {
  const est = leerJSON(RUTA);
  const mod = armarModelo(est, { pDelta: false });
  const g = gravedad(mod);
  // cargas aplicadas: w·L en cada viga (toda la luz entre nodos) y las cargas puntuales de los nodos
  let W = 0;
  for (const b of est.bloques) for (const p of b.porticos) {
    const s = new Map(p.nodos.map((n) => [n.id, n.s]));
    for (const n of p.nodos) W += n.carga_kN ?? 0;
    for (const e of p.elementos) if (e.tipo === 'viga') W += (e.w_gravedad_kN_m ?? 0) * (s.get(e.j) - s.get(e.i));
  }
  // reacción: −N de los elementos verticales que llegan a la base (columnas y muros del nivel 1), tracción +
  let Rb = 0;
  const N = g.axiales;
  mod.el.id.forEach((id, i) => {
    const info = mod.el.info[i];
    if (info.tipo !== 'viga' && info.nivel === 1) Rb += -N[i];
  });
  return caso(`suma de cargas ${W.toFixed(1)} kN frente a la reacción de la base ${Rb.toFixed(1)} kN`, Math.abs(Rb / W - 1), 1e-6);
}

function s5() {
  const est = leerJSON(RUTA);
  const ais = armarModelo(est), conf = armarModelo(est, { noEstructurales: 'confinados' });
  const aA = amortiguamiento(ais), aC = amortiguamiento(conf);
  const mA = modos(ais, 12), mC = modos(conf, 12);
  const [Ti] = est.amortiguamiento.periodos_ancla_s;
  return [
    caso(`aislados: anclas del archivo (${aA.periodos_ancla_s.map((x) => x.toFixed(4)).join(', ')} s), ξ1 = ${(100 * aA.xi_modos[0]).toFixed(4)} %`,
      Math.max(Math.abs(aA.xi_modos[0] - 0.05), aA.periodos_ancla_s[0] === Ti ? 0 : 1), 1e-4),
    caso(`confinados: T1 = ${mC.periodos_s[0].toFixed(4)} s (aislados ${mA.periodos_s[0].toFixed(4)} s), anclas ` +
      `${aC.periodos_ancla_s.map((x) => x.toFixed(4)).join(', ')} s, ξ de los modos 1-3 ` +
      `${[...aC.xi_modos].slice(0, 3).map((x) => (100 * x).toFixed(2)).join(' / ')} % (con las anclas del archivo daban 3,22 / 2,77 / 2,57 %)`,
    Math.max(Math.abs(aC.xi_modos[0] - 0.05), Math.abs(aC.periodos_ancla_s[0] / mC.periodos_s[0] - 1)), 1e-3),
    comprobar('confinados: la regla dice por qué no usa las anclas del archivo', /no valen/.test(aC.regla), aC.regla),
  ];
}

export const pruebas = [
  { id: 'T18', nombre: 'Estructura real de la torre con el motor (nido_2015 y local_hip, Δt = 0,005 s, con y sin P-Delta)', fn: t18 },
  { id: 'S1', nombre: 'La estructura de la torre cumple el esquema (E1-E16, theta_y ± 1 %)', fn: s1 },
  { id: 'S2', nombre: 'Períodos del motor = períodos del prediseño en Python (misma idealización)', fn: s2 },
  { id: 'S3', nombre: 'Períodos ancla de Rayleigh y centro de rigidez: motor = prediseño', fn: s3 },
  { id: 'S4', nombre: 'Equilibrio de gravedad del motor con las cargas del prediseño', fn: s4 },
  { id: 'S5', nombre: 'Amortiguamiento con los muros de mampostería trabajando («Sin aislar»): ξ1 = 5 %', fn: s5 },
];
