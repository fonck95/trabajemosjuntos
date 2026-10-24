// Fixtures del Anexo A.4 calculados con el motor real (contrato de la torre, A.4 y 12.1, ola 2; data/sismo/ESQUEMA.md,
// «Fixtures»): resultado_min.json, serie_elemento_min.json y el bloque generado de trabajador_simulado.js, todos sobre
// scripts/fixtures/torre/estructura_min.json.
//
//   node scripts/sismo/fixtures_min.mjs              # escribe los tres
//   node scripts/sismo/fixtures_min.mjs --verificar  # recalcula y compara byte a byte; sale 1 si algo cambió
//
// El caso es el mismo del cálculo de referencia de la ola 0 (scripts/sismo/referencia_min.py, que sigue como segunda
// implementación: prueba R0): el registro es un pulso de prueba (componente 1 = +1 m/s², componente 2 = −0,5 m/s²
// desde t = 0,005 s) ×25, porque en 0,04 s (nt = 3) ningún acelerograma sintético hace fluir nada; `params` conserva
// el escenario por defecto (nido_2015) y `origen_registro` dice qué se usó. Trae rótulas que fluyen, un equipo que
// desliza, uno que empieza a balancearse, uno anclado y el muro de mampostería con daño. Los reales van redondeados a
// Float32 (la representación decimal más corta que recupera el mismo Float32) y |x| < 10⁻¹² se escribe 0;
// duracion_calculo_ms se fija en 1 para que el archivo no cambie de una corrida a otra.
import { readFileSync, writeFileSync } from 'node:fs';
import { crearMotor } from '../../web/js/sismo/motor.js';
import { analizar } from '../../web/js/sismo/integrador.js';
import * as mov from '../../web/js/sismo/movimiento.js';

const RAIZ = new URL('../../', import.meta.url);
const FIX = new URL('scripts/fixtures/torre/', RAIZ);
const leer = (u) => JSON.parse(readFileSync(u, 'utf8'));
const VERIFICAR = process.argv.includes('--verificar');

const DT = 0.005, DT_SALIDA = 0.02, DURACION = 0.04, ESCALA = 25;
const ORIGEN = {
  tipo: 'pulso_prueba',
  descripcion: 'Pulso rectangular de prueba (componente 1: +1 m/s², componente 2: −0,5 m/s², desde t = 0,005 s) multiplicado por la escala; no es la síntesis de los parámetros del sismo (fixture calculado con el motor).',
};
// los equipos del cálculo de referencia (referencia_min.py): uno que desliza, uno que empieza a balancearse, uno anclado
const EQUIPOS = [
  { unidad: 'U-consulta_externa-2d1bfe-001', piso: 2, x: 1.2, y: 3.8, z_sobre_piso: 0, anclaje: 'apoyado', masa_kg: 60, h_cg_m: 0.45, mu: 0.3, bx_m: 0.3, by_m: 0.25, rot_z: 0 },
  { unidad: 'U-hospitalizacion-5d13f8-001', piso: 2, x: 4.4, y: 0.6, z_sobre_piso: 0, anclaje: 'apoyado', masa_kg: 90, h_cg_m: 0.95, mu: 0.5, bx_m: 0.3, by_m: 0.2, rot_z: Math.PI / 2 },
  { unidad: 'U-fijo-91b0de-001', piso: 'CUB', x: 3.5, y: 3.5, z_sobre_piso: 0, anclaje: 'anclado', masa_kg: 200, h_cg_m: 0.7, mu: 0.5, bx_m: 0.5, by_m: 0.4, rot_z: 0 },
];

// ---- números para el archivo --------------------------------------------------------------------------------
const RUIDO = 1e-12;
/** Float32 con la representación decimal más corta que lo recupera (como str(np.float32) en Python). */
function f32(x) {
  if (x === null || x === undefined) return x;
  const v = Math.fround(x);
  if (!Number.isFinite(v) || Math.abs(v) < RUIDO) return 0;
  for (let p = 1; p <= 9; p++) { const s = Number(v.toPrecision(p)); if (Math.fround(s) === v) return s; }
  return v;
}
const corto = (x, cifras = 7) => (x === null || x === undefined ? x : Math.abs(x) < RUIDO ? 0 : Number(x.toPrecision(cifras)));
const L32 = (a) => Array.from(a, f32);
const Lint = (a) => Array.from(a, (x) => x | 0);

/** JSON legible (el mismo estilo del cálculo de referencia): listas de números en una línea, una clave por línea. */
function aJSON(obj, sangria = 0) {
  const esp = '  '.repeat(sangria);
  if (Array.isArray(obj)) {
    if (obj.every((v) => v === null || typeof v !== 'object')) return `[${obj.map((v) => JSON.stringify(v)).join(', ')}]`;
    return `[\n${obj.map((v) => `${esp}  ${aJSON(v, sangria + 1)}`).join(',\n')}\n${esp}]`;
  }
  if (obj && typeof obj === 'object') {
    const ent = Object.entries(obj);
    if (!ent.length) return '{}';
    if (sangria >= 2 && ent.every(([, v]) => v === null || typeof v !== 'object' || (Array.isArray(v) && v.every((x) => x === null || typeof x !== 'object')))) {
      const linea = `{ ${ent.map(([k, v]) => `${JSON.stringify(k)}: ${aJSON(v)}`).join(', ')} }`;
      if (linea.length <= 240) return linea;
    }
    return `{\n${ent.map(([k, v]) => `${esp}  ${JSON.stringify(k)}: ${aJSON(v, sangria + 1)}`).join(',\n')}\n${esp}}`;
  }
  return JSON.stringify(obj);
}

// ---- cálculo ------------------------------------------------------------------------------------------------
const est = leer(new URL('estructura_min.json', FIX));
const amenaza = leer(new URL('data/sismo/amenaza.json', RAIZ));
const esc = amenaza.escenarios.find((e) => e.id === 'nido_2015');
const params = { Mw: esc.Mw, profundidad_km: esc.profundidad_km, distancia_epicentral_km: esc.distancia_epicentral_km,
  vs30_m_s: amenaza.controles.vs30_m_s.defecto, semilla: amenaza.controles.semilla.defecto };

const motor = crearMotor();
const listo = await motor.iniciar({ estructura: est, amenaza, id: 'prueba' });
const n = Math.round(DURACION / DT) + 1;
const ax = new Float64Array(n), ay = new Float64Array(n);
for (let i = 1; i < n; i++) { ax[i] = 1; ay[i] = -0.5; }
const { resultados: R, historia: H } = analizar(motor.modelo, { dt: DT, ax, ay }, {
  dt_s: DT, dt_salida_s: DT_SALIDA, duracion_s: DURACION, escala: ESCALA, equipos: EQUIPOS, params, id: 'prueba', origen_registro: ORIGEN,
});

// ---- resultado_min.json -------------------------------------------------------------------------------------
const E = R.envolventes;
const resultado = {
  version: R.version, id: 'prueba', duracion_calculo_ms: 1,
  params,
  opciones: { ...R.opciones },
  origen_registro: ORIGEN,
  factor_escala: R.factor_escala, iteraciones_escala: R.iteraciones_escala,
  amortiguamiento: { a0: corto(R.amortiguamiento.a0), a1: corto(R.amortiguamiento.a1), periodos_ancla_s: R.amortiguamiento.periodos_ancla_s.map((x) => corto(x)),
    xi_modos: L32(R.amortiguamiento.xi_modos) },
  t: L32(R.t), ag: L32(R.ag), u: L32(R.u), a_abs: L32(R.a_abs), giros: L32(R.giros), v_nodos: L32(R.v_nodos),
  dc: Lint(R.dc), dc_flexion: Lint(R.dc_flexion), dc_cortante: Lint(R.dc_cortante), dc_rotacion: Lint(R.dc_rotacion), rotulas: Lint(R.rotulas),
  thp: { elementos: Lint(R.thp.elementos), valores: Lint(R.thp.valores) },
  derivas: L32(R.derivas), derivas_vector: L32(R.derivas_vector), derivas_porticos_env: L32(R.derivas_porticos_env),
  cortante_basal: L32(R.cortante_basal), energia: L32(R.energia),
  envolventes: Object.fromEntries(Object.entries(E).map(([k, v]) => [k, k === 'gobierna' ? Lint(v) : L32(v)])),
  muros_mamposteria: R.muros_mamposteria.map((m) => ({ id: m.id, aislado: m.aislado, deriva_max: f32(m.deriva_max), estado: m.estado })),
  equipos: R.equipos.map((q) => Object.fromEntries(Object.entries(q).map(([k, v]) => [k, typeof v === 'number' ? f32(v) : v]))),
  calidad_numerica: {
    pasos: R.calidad_numerica.pasos, iteraciones_promedio: corto(R.calidad_numerica.iteraciones_promedio, 4),
    subdivisiones: R.calidad_numerica.subdivisiones, no_convergidos: R.calidad_numerica.no_convergidos,
    error_energia_max: corto(R.calidad_numerica.error_energia_max, 3), error_deformacion_max: corto(R.calidad_numerica.error_deformacion_max, 3),
    indice_estabilidad_max: corto(R.calidad_numerica.indice_estabilidad_max, 4),
  },
};

// ---- series de la historia interna (las de serie_elemento) -----------------------------------------------------
const CLAVES = ['Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc'];
const serieDe = (id) => {
  const ie = H.ids.indexOf(id);
  return Object.fromEntries(CLAVES.map((k) => [k, Array.from({ length: H.nt }, (_, i) => f32(H[k][i * H.nE + ie]))]));
};
const serie = { tipo: 'serie_elemento', id: 'prueba', elemento: 'C-A1-1@X', t: resultado.t, ...serieDe('C-A1-1@X') };
const series = Object.fromEntries(H.ids.map((id) => [id, serieDe(id)]));

// ---- bloque del trabajador simulado: listo (el del motor) y movimiento (el pulso, con espectros del motor) -----
const L = structuredClone(listo);
const redondearListo = (x) => (typeof x === 'number' ? corto(x) : Array.isArray(x) ? x.map(redondearListo) : x && typeof x === 'object' ? Object.fromEntries(Object.entries(x).map(([k, v]) => [k, redondearListo(v)])) : x);
L.resumen = redondearListo(L.resumen);
L.modos = redondearListo(L.modos);
L.amortiguamiento = { ...resultado.amortiguamiento, regla: listo.amortiguamiento.regla };
const ax25 = Float64Array.from(ax, (v) => ESCALA * v), ay25 = Float64Array.from(ay, (v) => ESCALA * v);
// espectro del pulso con 8 s de vibración libre después (como el cálculo de referencia)
const conCola = (a) => { const b = new Float64Array(a.length + Math.round(8 / DT)); b.set(a); return b; };
const T = mov.periodosLog(60);
const Sx = mov.espectroRespuesta(conCola(ax25), DT, T, 0.05).Sa_g, Sy = mov.espectroRespuesta(conCola(ay25), DT, T, 0.05).Sa_g;
const Fx = mov.espectroFourier(ax25, DT), Fy = mov.espectroFourier(ay25, DT);
const meta = mov.sintetizar(params, amenaza).meta;   // los parámetros de la fuente del escenario (el registro es el pulso)
const d = est.diseno;
const Ad = amenaza.nsr10.Ad.valor ?? amenaza.nsr10.Ad;
const intens = (a) => Object.fromEntries(Object.entries(mov.intensidades(a, DT)).map(([k, v]) => [k, corto(v, 6)]));
const movimiento = {
  tipo: 'movimiento', id: 'prueba',
  registro: {
    dt: DT, n, ax: L32(ax25), ay: L32(ay25),
    meta: Object.fromEntries(Object.entries(meta).map(([k, v]) => [k, typeof v === 'number' ? corto(v) : v])),
    intensidades: { x: intens(ax25), y: intens(ay25) },
    avisos: [`Trabajador simulado: el registro es el pulso de prueba del fixture (escala ×${ESCALA}), no la síntesis de estos parámetros.`,
      'Espectro de umbral de daño de A.12.3 con ξ = 2 % (el del prediseño; forma por confirmar).'],
  },
  espectro: { T: L32(T), Sa_x: L32(Sx), Sa_y: L32(Sy) },
  fourier: { f: L32(Fx.f_Hz), A_x: L32(Fx.A_m_s), A_y: L32(Fy.A_m_s) },
  gmpe: mov.gmpeEscenario(params, amenaza).map((g) => ({ nombre: g.nombre, modelo: g.modelo, regimen: g.regimen, peso: g.peso, T: Array.from(g.T),
    mediana_g: Array.from(g.mediana_g, (x) => corto(x, 5)), sigma_ln: Array.from(g.sigma_ln, (x) => corto(x, 4)) })),
  nsr10: {
    T: L32(T),
    con_I: L32(mov.espectroNSR10(T, { Aa: d.Aa, Av: d.Av, Fa: d.Fa, Fv: d.Fv, I: d.I })),
    sin_I: L32(mov.espectroNSR10(T, { Aa: d.Aa, Av: d.Av, Fa: d.Fa, Fv: d.Fv, I: 1 })),
    umbral_dano: L32(mov.espectroUmbralDano(T, { Ad, Fa: d.Fa, Fv: d.Fv })),
    xi: 0.05, xi_umbral_dano: mov.XI_UMBRAL_DANO,
  },
};

// ---- escritura ------------------------------------------------------------------------------------------------
const MARCA_INI = '/* >>> generado por scripts/sismo/fixtures_min.mjs (no editar a mano) */';
const MARCA_FIN = '/* <<< generado */';
const rutaJS = new URL('trabajador_simulado.js', FIX);
const js = readFileSync(rutaJS, 'utf8');
const i0 = js.indexOf('/* >>> generado'), i1 = js.indexOf(MARCA_FIN);
if (i0 < 0 || i1 < 0) { console.error('trabajador_simulado.js: faltan las marcas del bloque generado'); process.exit(1); }
const bloque = `${MARCA_INI}\nconst GENERADO = ${aJSON({ listo: L, movimiento, series })};\n${MARCA_FIN}`;
const salidas = [
  [new URL('resultado_min.json', FIX), `${aJSON(resultado)}\n`],
  [new URL('serie_elemento_min.json', FIX), `${aJSON(serie)}\n`],
  [rutaJS, js.slice(0, i0) + bloque + js.slice(i1 + MARCA_FIN.length)],
];
const distintos = [];
for (const [u, texto] of salidas) {
  let actual = null;
  try { actual = readFileSync(u, 'utf8'); } catch { /* no existe */ }
  if (actual === texto) continue;
  const rel = u.pathname.slice(RAIZ.pathname.length);
  if (VERIFICAR) distintos.push(rel);
  else { writeFileSync(u, texto); console.log(`escrito ${rel}`); }
}
const q = resultado.calidad_numerica;
console.log(`pasos ${q.pasos} · iteraciones promedio ${q.iteraciones_promedio} · error de energía ${q.error_energia_max} · ` +
  `elementos que fluyen ${resultado.thp.elementos.length} · equipos ${resultado.equipos.map((e) => e.regimen).join(', ')} · ` +
  `muro ${resultado.muros_mamposteria.map((m) => m.estado).join(', ')}`);
if (VERIFICAR) {
  if (distintos.length) { console.log(`DIFERENTES (correr sin --verificar y revisar el cambio): ${distintos.join(', ')}`); process.exit(1); }
  console.log('fixtures al día: idénticos byte a byte');
}
