// Cifras de los escenarios de referencia de la torre para docs/14 (contrato de la torre, 11.3 punto 8 y 12.1 ola 3):
// corre el motor real (web/js/sismo/) sobre data/sismo/torre_hospital_estructura.json con Δt = 0,005 s y escribe
// data/sismo/escenarios.json.
//
//   node scripts/sismo/escenarios.mjs              # escribe data/sismo/escenarios.json
//   node scripts/sismo/escenarios.mjs --verificar  # recalcula y compara byte a byte; sale 1 si algo cambió
//
// Escenarios: nido_2015, cimitarra y local_hip de amenaza.json con su registro físico (escala 1), y el «nivel de
// diseño NSR-10» (escala nsr10, 7.4: escenario hipotético) aplicado a los mismos tres registros; el de referencia
// para el texto es local_hip escalado (el mismo de la validación con OpenSees). Semilla y Vs30 por defecto
// (amenaza.json → controles), ángulo 0, histéresis de cada sección, muros no estructurales aislados, P-Delta.
// Los equipos no anclados salen del inventario publicado (web/data/torre_inventario*.json) con la misma regla de la
// vista (web/js/scenes/torre/sismo.js, equiposRiesgo); si el inventario no está, ese bloque queda en null.
// Todas las cifras son cálculo propio con el motor (tipo de dato: «cálculo propio»; el movimiento y el prediseño son
// estimaciones). El archivo es determinista: no guarda tiempos de cálculo.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { crearMotor } from '../../web/js/sismo/motor.js';
import * as mov from '../../web/js/sismo/movimiento.js';

const RAIZ = new URL('../../', import.meta.url);
const ruta = (r) => new URL(r, RAIZ);
const texto = (r) => readFileSync(ruta(r), 'utf8');
const VERIFICAR = process.argv.includes('--verificar');
const SALIDA = 'data/sismo/escenarios.json';
const G = 9.80665;

const textoE = texto('data/sismo/torre_hospital_estructura.json'), textoA = texto('data/sismo/amenaza.json');
const est = JSON.parse(textoE), amenaza = JSON.parse(textoA);
const sha1 = (s) => createHash('sha1').update(s).digest('hex');
const r4 = (x, c = 4) => (x === null || x === undefined || !Number.isFinite(x) ? null : Number(x.toPrecision(c)));

// ---- equipos del inventario publicado (la misma regla que equiposRiesgo de la vista) -------------------------
function equiposInventario(N) {
  const principal = 'web/data/torre_inventario.json';
  if (!existsSync(ruta(principal))) return null;
  let inv = JSON.parse(texto(principal));
  if (inv.partes?.archivos) {
    const { partes, ...todo } = inv;
    for (const f of partes.archivos) {
      const t = JSON.parse(texto(`web/data/${f}`));
      for (const [k, v] of Object.entries(t)) {
        if (Array.isArray(v)) todo[k] = (todo[k] || []).concat(v);
        else if (v && typeof v === 'object') todo[k] = Object.assign(todo[k] || {}, v);
        else todo[k] = v;
      }
    }
    inv = todo;
  }
  if (!inv.unidades?.length) return null;
  const col = Object.fromEntries((inv.columnas_unidades || []).map((c, k) => [c, k]));
  const PISOS = new Set([1, 2, 3, 4, 'BT', 'CUB']);
  const ANCLAJES = new Set(['apoyado', 'ruedas_con_freno', 'ruedas_sin_freno', 'sobre', 'anclado', 'pared', 'cielo', 'en_nucleo']);
  return inv.unidades.map((u) => {
    const l = inv.lineas?.[u[col.linea_idx]] || {}, c = inv.catalogo?.[l.modelo3d] || {};
    return { unidad: u[col.id], piso: u[col.piso], x: +u[col.x], y: +u[col.y], z: +u[col.z] || 0, rot: +u[col.rot_z] || 0, montaje: u[col.montaje],
      dentro: u[col.dentro_de_idx] >= 0, comp: u[col.componente_de_idx] >= 0, cat: c };
  }).filter((q) => PISOS.has(q.piso) && Array.isArray(q.cat?.dim) && q.cat.dim.length >= 3 && Number.isFinite(q.x) && Number.isFinite(q.y) && !q.dentro && !q.comp && q.montaje !== 'dentro')
    .filter((q) => (q.montaje === 'piso' || q.montaje === 'sobre' || q.cat.mont === 'piso') && (typeof q.piso !== 'number' || q.piso <= N + 1)
      && ANCLAJES.has(q.cat.anc || 'apoyado') && q.cat.masa > 0 && q.cat.hcg > 0 && q.cat.mu >= 0 && q.cat.dim[0] > 0 && q.cat.dim[1] > 0)
    .map((q) => ({ unidad: q.unidad, piso: q.piso, x: q.x, y: q.y, z_sobre_piso: q.z, anclaje: q.cat.anc || 'apoyado', masa_kg: q.cat.masa,
      h_cg_m: q.cat.hcg, mu: q.cat.mu, bx_m: q.cat.dim[0] / 2, by_m: q.cat.dim[1] / 2, rot_z: q.rot }));
}

// ---- un escenario ---------------------------------------------------------------------------------------------
function resumen(R, listo, reg, factor, nombreEsc, equipos) {
  const N = listo.resumen.niveles, el = listo.elementos, nE = el.length, E = R.envolventes;
  const nt = R.t.length;
  // intensidades del registro integrado (0,005 s; lineales en el factor)
  const ix = mov.intensidades(reg.ax, reg.dt), iy = mov.intensidades(reg.ay, reg.dt);
  const pga = [factor * ix.pga_g, factor * iy.pga_g];
  // cortante basal: picos de la serie de salida (0,02 s)
  const V = [0, 0, 0];
  for (let i = 0; i < nt; i++) for (let c = 0; c < 3; c++) V[c] = Math.max(V[c], Math.abs(R.cortante_basal[3 * i + c]));
  const peso = listo.resumen.peso_kN;
  // rótulas: elementos con θp ≠ 0 alguna vez, por nivel y por tipo; extremos más allá de IO, LS y CP
  const porNivel = {}, porTipo = { columna: 0, viga: 0, muro_concreto: 0 };
  for (const ie of R.thp.elementos) { const e = el[ie]; porNivel[e.nivel] = (porNivel[e.nivel] || 0) + 1; porTipo[e.tipo]++; }
  const union = new Uint8Array(nE);
  for (let i = 0; i < nt; i++) for (let k = 0; k < nE; k++) union[k] |= R.rotulas[i * nE + k];
  let io = 0, ls = 0, cp = 0, vn = 0;
  for (let k = 0; k < nE; k++) { if (union[k] & 12) io++; if (union[k] & 48) ls++; if (union[k] & 64) cp++; if (union[k] & 128) vn++; }
  // D/C máximo
  let kmax = 0, dc1 = 0;
  for (let k = 0; k < nE; k++) { if (E.dc_max[k] > E.dc_max[kmax]) kmax = k; if (E.dc_max[k] > 1) dc1++; }
  // primera fluencia
  let t1 = null;
  for (let k = 0; k < 2 * nE; k++) if (E.t_primera_fluencia[k] >= 0 && (t1 === null || E.t_primera_fluencia[k] < t1)) t1 = E.t_primera_fluencia[k];
  const Ef = (c) => R.energia[6 * (nt - 1) + c];
  const muros = {};
  for (const m of R.muros_mamposteria) muros[m.estado] = (muros[m.estado] || 0) + 1;
  const eq = equipos ? { evaluados: R.equipos.length, desliza: 0, balancea: 0, frontera: 0, anclado: 0, estable: 0, deslizamiento_max_m: 0, fuerza_anclaje_max_kN: 0 } : null;
  if (eq) for (const q of R.equipos) {
    if (q.regimen === 'anclado') { eq.anclado++; eq.fuerza_anclaje_max_kN = Math.max(eq.fuerza_anclaje_max_kN, q.fuerza_anclaje_kN || 0); continue; }
    if (q.desliza && q.inicia_balanceo) eq.frontera++;
    else if (q.desliza) eq.desliza++;
    else if (q.inicia_balanceo) eq.balancea++;
    else eq.estable++;
    eq.deslizamiento_max_m = Math.max(eq.deslizamiento_max_m, q.deslizamiento_max_m || 0);
  }
  if (eq) { eq.deslizamiento_max_m = r4(eq.deslizamiento_max_m, 3); eq.fuerza_anclaje_max_kN = r4(eq.fuerza_anclaje_max_kN, 3); }
  const niveles = Array.from({ length: N }, (_, g) => ({
    nivel: g + 1,
    deriva_vector_max: r4(E.deriva_vector_max[g]), punto: [r4(E.punto_deriva_vector[2 * g], 5), r4(E.punto_deriva_vector[2 * g + 1], 5)], t_s: r4(E.t_deriva_vector_max[g], 5),
    deriva_x_max: r4(E.deriva_max[2 * g]), deriva_y_max: r4(E.deriva_max[2 * g + 1]),
    u_max_m: [r4(E.u_max[3 * g]), r4(E.u_max[3 * g + 1])], rz_max_rad: r4(E.u_max[3 * g + 2]),
    a_abs_max_g: [r4(E.a_abs_max[3 * g] / G), r4(E.a_abs_max[3 * g + 1] / G)],
    elementos_que_fluyen: porNivel[g + 1] || 0,
  }));
  return {
    escenario: nombreEsc, params: R.params, escala: R.opciones.escala, factor: r4(factor, 5), iteraciones_escala: R.iteraciones_escala,
    duracion_s: r4(R.opciones.duracion_s, 5), dt_s: R.opciones.dt_s,
    pga_g: { x: r4(pga[0]), y: r4(pga[1]), media_geometrica: r4(Math.sqrt(pga[0] * pga[1])) },
    pgv_cm_s: { x: r4(factor * ix.pgv_cm_s), y: r4(factor * iy.pgv_cm_s) }, d595_s: { x: r4(ix.d595_s), y: r4(iy.d595_s) },
    deriva_vector_max: r4(Math.max(...E.deriva_vector_max)),
    niveles,
    cortante_basal_max_kN: { Vx: r4(V[0]), Vy: r4(V[1]), torsor_kNm: r4(V[2]) }, cortante_basal_sobre_peso: { x: r4(V[0] / peso), y: r4(V[1] / peso) },
    fluencia: { elementos: R.thp.elementos.length, por_tipo: porTipo, extremos_mas_alla_de_IO: io, de_LS: ls, de_CP: cp, cortante_mayor_que_Vn: vn, t_primera_s: t1 === null ? null : r4(t1, 5) },
    dc_max: { valor: r4(E.dc_max[kmax]), elemento: el[kmax].id, gobierna: ['flexión', 'cortante', 'rotación plástica'][E.gobierna[kmax]], elementos_con_dc_mayor_que_1: dc1 },
    energia_final_kJ: { entrada: r4(Ef(0)), cinetica: r4(Ef(1)), elastica: r4(Ef(2)), amortiguada: r4(Ef(3)), histeretica: r4(Ef(4)), trabajo_pdelta: r4(Ef(5)) },
    muros_mamposteria: muros, equipos: eq,
    calidad_numerica: { pasos: R.calidad_numerica.pasos, iteraciones_promedio: r4(R.calidad_numerica.iteraciones_promedio, 3), subdivisiones: R.calidad_numerica.subdivisiones,
      no_convergidos: R.calidad_numerica.no_convergidos, error_energia_max: r4(R.calidad_numerica.error_energia_max, 2), indice_estabilidad_max: r4(R.calidad_numerica.indice_estabilidad_max, 3) },
  };
}

// ---- corrida ---------------------------------------------------------------------------------------------------
const motor = crearMotor();
const listo = await motor.iniciar({ estructura: est, amenaza });
const N = listo.resumen.niveles;
const equipos = equiposInventario(N);
const params = (id) => {
  const e = amenaza.escenarios.find((x) => x.id === id);
  return { Mw: e.Mw, profundidad_km: e.profundidad_km, distancia_epicentral_km: e.distancia_epicentral_km, vs30_m_s: amenaza.controles.vs30_m_s.defecto, semilla: amenaza.controles.semilla.defecto };
};
const IDS = ['nido_2015', 'cimitarra', 'local_hip'];
const escenarios = [];
for (const escala of [1, 'nsr10']) {
  for (const id of IDS) {
    const p = params(id);
    const R = await motor.analizar(p, { dt_s: 0.005, escala, equipos: equipos || [] });
    const an = motor.ultimoAnalisis;
    const nombre = amenaza.escenarios.find((x) => x.id === id).nombre;
    const r = resumen(R, listo, an.registro, an.factor, nombre, equipos);
    escenarios.push({ id: escala === 1 ? id : `diseno_nsr10_${id}`, ...r });
    console.log(`${(escala === 1 ? id : `diseño NSR-10 (${id})`).padEnd(28)} factor ${String(r.factor).padEnd(7)} PGA ${r.pga_g.x}/${r.pga_g.y} g · deriva ${(100 * r.deriva_vector_max).toFixed(3)} % · ` +
      `Vx ${r.cortante_basal_max_kN.Vx} kN · fluyen ${r.fluencia.elementos} · D/C ${r.dc_max.valor} (${r.dc_max.elemento})` + (r.equipos ? ` · equipos: desliza ${r.equipos.desliza}, balancea ${r.equipos.balancea}` : ''));
  }
}
const md = listo.modos, am = listo.amortiguamiento;
const salida = {
  version: 1,
  generado_por: 'scripts/sismo/escenarios.mjs',
  contrato: 'ESPECIFICACION_INTEGRACION.md, 11.3 (punto 8) y 12.1 (ola 3)',
  tipo_dato: 'calculo_propio',
  nota: 'Cálculo propio con el motor del simulador (análisis no lineal en el tiempo con Δt = 0,005 s) sobre el prediseño de la torre (estimación) y movimientos sintéticos (estimación: Boore 2003 con los parámetros de amenaza.json). «Diseño NSR-10» es un escenario hipotético: el registro se multiplica para que su espectro, entre 0,8 y 1,2 veces el período fundamental en cada dirección, iguale en promedio el espectro de diseño de Yondó con I = 1,5. Una sola semilla por escenario: otra semilla da otras cifras (ver la dispersión en T15 de las pruebas del motor).',
  insumos_sha1: { 'data/sismo/torre_hospital_estructura.json': sha1(textoE), 'data/sismo/amenaza.json': sha1(textoA) },
  opciones: { dt_s: 0.005, dt_salida_s: 0.02, angulo_deg: 0, histeresis: 'la de cada sección', no_estructurales: 'aislados', p_delta: true,
    semilla: amenaza.controles.semilla.defecto, vs30_m_s: amenaza.controles.vs30_m_s.defecto, referencia_diseno: 'diseno_nsr10_local_hip' },
  modelo: {
    niveles: N, elementos: listo.resumen.elementos, masa_total_t: r4(listo.resumen.masa_total_t, 6), peso_kN: r4(listo.resumen.peso_kN, 6),
    periodos_s: md.periodos_s.map((x) => r4(x)), T1x_s: r4(md.T1x), T1y_s: r4(md.T1y),
    masa_participativa: { x: md.masa_participativa.x.map((x) => r4(x, 3)), y: md.masa_participativa.y.map((x) => r4(x, 3)), rz: md.masa_participativa.rz.map((x) => r4(x, 3)) },
    amortiguamiento: { a0: r4(am.a0), a1: r4(am.a1), periodos_ancla_s: am.periodos_ancla_s.map((x) => r4(x)), xi_modos: am.xi_modos.map((x) => r4(x, 3)) },
    equipos_evaluados: equipos ? equipos.length : null,
  },
  escenarios,
};
const nuevo = `${JSON.stringify(salida, null, 1)}\n`;
let actual = null;
try { actual = texto(SALIDA); } catch { /* no existe */ }
if (VERIFICAR) {
  if (actual !== nuevo) { console.log(`DIFERENTE: ${SALIDA} (correr sin --verificar y revisar el cambio)`); process.exit(1); }
  console.log(`${SALIDA} al día: idéntico byte a byte`);
} else if (actual !== nuevo) {
  writeFileSync(ruta(SALIDA), nuevo);
  console.log(`escrito ${SALIDA}`);
}
