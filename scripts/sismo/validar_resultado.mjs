// Valida los `Resultados` del motor sísmico y la estructura con la que se calcularon
// (data/sismo/ESQUEMA.md, secciones «Resultados del motor» y «data/sismo/<id>_estructura.json»; contrato, 7.6).
//
// Uso:
//   node scripts/sismo/validar_resultado.mjs <resultado.json> [--estructura <estructura.json>] [--serie <serie.json>]
//   node scripts/sismo/validar_resultado.mjs --estructura <estructura.json>        (solo la estructura)
// Si no se dan, toma `estructura_min.json` y `serie_elemento_min.json` de la carpeta del resultado cuando existen.
// Comprueba además theta_y = My·L_f/(6·EI_fis) (o My·lp/EI_fis en muros) ± 1 % en la estructura dada y en
// data/sismo/torre_hospital_estructura.json si ya existe. Sale con código 1 si hay errores.
//
// Como módulo (sin dependencias de Node al importarlo; sirve en el navegador y en las pruebas):
//   import { validarResultado, validarEstructura, validarSerie, dimensiones, TIPOS_RESULTADOS } from './validar_resultado.mjs';
//   validarResultado(res, estructura) → { errores: string[], avisos: string[], dim }
// `res` puede traer arreglos tipados (salida del motor en memoria) o listas de números (JSON): en el primer caso
// se exige el tipo exacto del 7.6; en el segundo, que los valores quepan en ese tipo.

export const TIPOS_RESULTADOS = {
  t: 'Float32Array', ag: 'Float32Array', u: 'Float32Array', a_abs: 'Float32Array', giros: 'Float32Array', v_nodos: 'Float32Array',
  dc: 'Uint8Array', dc_flexion: 'Uint8Array', dc_cortante: 'Uint8Array', dc_rotacion: 'Uint8Array', rotulas: 'Uint8Array',
  derivas: 'Float32Array', derivas_vector: 'Float32Array', derivas_porticos_env: 'Float32Array', cortante_basal: 'Float32Array',
  energia: 'Float32Array',
};
export const CLAVES_ENVOLVENTES = ['u_max', 'deriva_max', 't_deriva_max', 'deriva_vector_max', 'punto_deriva_vector', 't_deriva_vector_max',
  'a_abs_max', 'dc_max', 't_dc_max', 'gobierna', 'Mi_max', 'Mj_max', 'V_max', 'N_min', 'N_max', 'thp_max', 't_primera_fluencia'];
export const REGIMENES_EQUIPO = ['desliza', 'balancea', 'frontera', 'anclado'];
export const ESTADOS_MURO = ['sin_dano', 'leve', 'moderado', 'extenso', 'colapso'];
// Rangos de los controles (data/sismo/amenaza.json → controles)
const RANGOS_PARAMS = { Mw: [4, 8], profundidad_km: [5, 200], distancia_epicentral_km: [0, 300], vs30_m_s: [150, 760] };
const RANGO_ENTERO = { Uint8Array: [0, 255], Int16Array: [-32768, 32767], Int32Array: [-2147483648, 2147483647] };

const esNum = (x) => typeof x === 'number' && Number.isFinite(x);
const esLista = (x) => Array.isArray(x) || ArrayBuffer.isView(x);
const maxAbs = (a) => { let m = 0; for (const x of a) m = Math.max(m, Math.abs(x)); return m; };

// ---------------------------------------------------------------------------------------------------------------
// Estructura
// ---------------------------------------------------------------------------------------------------------------
/** Tamaños e índices que fija la estructura: orden del archivo (bloques → pórticos → nodos/elementos). */
export function dimensiones(est) {
  const niveles = [], porticos = [], nodos = [], elementos = [], muros = [];
  let base = 0;
  for (const b of est.bloques || []) {
    const z = [0, ...b.niveles.map((n) => n.z)];
    b.niveles.forEach((n, k) => niveles.push({ ...n, bloque: b.id, k: k + 1, indice: base + k }));
    for (const p of b.porticos || []) {
      porticos.push({ ...p, bloque: b.id, base_nivel: base });
      const ns = new Map(p.nodos.map((n) => [n.id, n]));
      for (const n of p.nodos) nodos.push({ ...n, portico: p.id, z: z[n.nivel] });
      for (const e of p.elementos || []) {
        const ni = ns.get(e.i), nj = ns.get(e.j);
        const [di, dj] = e.brazo_rigido_m || [0, 0];
        let L = NaN;
        if (ni && nj) L = e.tipo === 'viga' ? Math.abs(nj.s - ni.s) : z[nj.nivel] - z[ni.nivel];
        elementos.push({ ...e, portico: p.id, L, Lf: L - di - dj, nivel_i: ni?.nivel, nivel_j: nj?.nivel,
          altura_entrepiso: b.niveles[(e.nivel || 1) - 1]?.altura_entrepiso });
      }
    }
    for (const r of b.resortes || []) if (r.tipo === 'muro_mamposteria') muros.push({ ...r, bloque: b.id });
    base += b.niveles.length;
  }
  return { N: niveles.length, nE: elementos.length, nN: nodos.length, nP: porticos.length, niveles, porticos, nodos, elementos, muros };
}

/** theta_y nominal y esperada de cada elemento contra la fórmula del esquema (± 1 %). */
export function filasThetaY(est) {
  const dim = dimensiones(est);
  const filas = [];
  for (const e of dim.elementos) {
    const s = est.secciones?.[e.seccion];
    const m = s && est.materiales?.[s.material];
    if (!s || !m || !esNum(m.Ec_MPa)) continue;
    const EI = m.Ec_MPa * 1000 * s.I * s.factor_fisuracion;
    let largo, formula;
    if (e.tipo === 'muro_concreto') {
      largo = s.lp_m ?? Math.min(0.5 * s.h, e.altura_entrepiso ?? Infinity);
      formula = 'My·lp/EI_fis';
    } else {
      largo = e.Lf / 6;
      formula = 'My·L_f/(6·EI_fis)';
    }
    for (const [campo, My] of [['theta_y', s.My_kNm], ['theta_y_e', s.My_e_kNm]]) {
      if (!esNum(s[campo]) || !esNum(My)) continue;
      const esperado = My * largo / EI;
      filas.push({ elemento: e.id, seccion: e.seccion, campo, formula, L_f: e.Lf, archivo: s[campo], esperado, error: s[campo] / esperado - 1 });
    }
  }
  return filas;
}

export function validarEstructura(est) {
  const errores = [], avisos = [];
  const E = (m) => errores.push(m), A = (m) => avisos.push(m);
  for (const k of ['id', 'nombre', 'tipo_dato', 'sistema_estructural', 'norma', 'materiales', 'secciones', 'bloques', 'amortiguamiento', 'limites', 'diseno']) {
    if (est[k] === undefined) E(`estructura: falta «${k}»`);
  }
  for (const k of ['fuentes', 'supuestos', 'incertidumbres']) if (!Array.isArray(est[k])) E(`estructura: «${k}» debe ser una lista`);
  if (typeof est.p_delta !== 'boolean') E('estructura: «p_delta» debe ser true o false');
  for (const k of ['generado_por', 'fecha']) if (est[k] === undefined) A(`estructura: sin «${k}» (E13)`);
  if (errores.length) return { errores, avisos, dim: null, theta: [] };

  for (const [id, m] of Object.entries(est.materiales)) {
    if (!m.tipo) E(`material ${id}: falta «tipo»`);
    if (m.tipo === 'concreto') for (const k of ['fc_MPa', 'Ec_MPa', 'nu', 'peso_kN_m3']) if (!esNum(m[k])) E(`material ${id}: falta «${k}»`);
    if (m.tipo === 'mamposteria') for (const k of ['Em_MPa', 'Gm_MPa']) if (!esNum(m[k])) E(`material ${id}: falta «${k}»`);
  }
  const reqSec = ['A', 'I', 'Av', 'factor_fisuracion', 'My_kNm', 'Mn_kNm', 'phiMn_kNm', 'Mpr_kNm', 'theta_y', 'theta_p_cap', 'Vn_kN', 'phiVn_kN', 'endurecimiento'];
  const e16 = ['My_e_kNm', 'Mn_e_kNm', 'Vn_e_kN', 'theta_y_e', 'theta_p_IO', 'theta_p_LS', 'theta_p_CP'];
  for (const [id, s] of Object.entries(est.secciones)) {
    if (!est.materiales[s.material]) E(`sección ${id}: material «${s.material}» no existe`);
    for (const k of reqSec) if (!esNum(s[k])) E(`sección ${id}: falta «${k}» (número)`);
    for (const k of e16) if (!esNum(s[k])) A(`sección ${id}: sin «${k}» (E16); el motor usa las propiedades nominales`);
    if (!['bilineal', 'clough'].includes(s.histeresis)) E(`sección ${id}: «histeresis» debe ser bilineal o clough`);
    if (esNum(s.theta_p_IO) && esNum(s.theta_p_LS) && esNum(s.theta_p_CP) && !(s.theta_p_IO <= s.theta_p_LS && s.theta_p_LS <= s.theta_p_CP)) {
      E(`sección ${id}: se espera theta_p_IO ≤ theta_p_LS ≤ theta_p_CP`);
    }
    if (esNum(s.factor_fisuracion) && !(s.factor_fisuracion > 0 && s.factor_fisuracion <= 1)) E(`sección ${id}: factor_fisuracion fuera de (0, 1]`);
    if (s.My_pos_kNm !== undefined && !esNum(s.My_pos_kNm)) E(`sección ${id}: My_pos_kNm debe ser número`);
    if (s.My_neg_kNm !== undefined && !esNum(s.My_neg_kNm)) E(`sección ${id}: My_neg_kNm debe ser número`);
  }

  const ids = new Set();
  const unico = (id, que) => { if (ids.has(id)) E(`id repetido: ${id} (${que})`); ids.add(id); };
  if (!Array.isArray(est.bloques) || !est.bloques.length) E('estructura: «bloques» vacío');
  for (const b of est.bloques || []) {
    unico(b.id, 'bloque');
    let zAnt = 0;
    b.niveles.forEach((n, k) => {
      unico(n.id, 'nivel');
      for (const c of ['z', 'altura_entrepiso', 'masa_t', 'Jz_t_m2', 'peso_sismico_kN']) if (!esNum(n[c])) E(`nivel ${n.id}: falta «${c}»`);
      if (!(Array.isArray(n.cm) && n.cm.length === 2)) E(`nivel ${n.id}: «cm» debe ser [x, y]`);
      if (esNum(n.z) && Math.abs(n.z - zAnt - n.altura_entrepiso) > 1e-6) E(`nivel ${n.id}: altura_entrepiso ≠ z − z del nivel de abajo`);
      if (esNum(n.z) && n.z <= zAnt) E(`nivel ${n.id}: z debe crecer`);
      zAnt = n.z;
      if (!(n.masa_t > 0) || !(n.Jz_t_m2 > 0)) E(`nivel ${n.id}: masa y Jz deben ser positivos`);
      if (!Array.isArray(n.contorno) || n.contorno.length < 3) A(`nivel ${n.id}: sin «contorno» (E7): no hay deriva vectorial`);
      else if (Array.isArray(n.cm) && !dentro(n.cm, n.contorno)) A(`nivel ${n.id}: el centro de masa queda fuera del contorno`);
      if (esNum(n.masa_t) && esNum(n.peso_sismico_kN) && Math.abs(n.peso_sismico_kN / (n.masa_t * 9.80665) - 1) > 0.01) {
        A(`nivel ${n.id}: peso_sismico_kN ≠ masa_t·g (diferencia > 1 %)`);
      }
    });
    const N = b.niveles.length;
    for (const p of b.porticos || []) {
      unico(p.id, 'pórtico');
      if (!['x', 'y'].includes(p.direccion)) E(`pórtico ${p.id}: «direccion» debe ser x o y`);
      if (!esNum(p.coordenada)) E(`pórtico ${p.id}: falta «coordenada»`);
      const ns = new Map();
      for (const n of p.nodos) {
        unico(n.id, 'nodo');
        ns.set(n.id, n);
        if (!esNum(n.s) || !Number.isInteger(n.nivel) || n.nivel < 0 || n.nivel > N) E(`nodo ${n.id}: «s» o «nivel» inválidos`);
        if (n.nivel === 0 && !(p.apoyos || {})[n.id]) E(`nodo ${n.id}: nodo de base sin apoyo`);
      }
      const ejes = est.ejes?.[p.direccion];
      if (Array.isArray(ejes)) {
        for (const n of p.nodos) if (!ejes.some((e) => Math.abs(e[p.direccion] - n.s) < 1e-6)) A(`nodo ${n.id}: s = ${n.s} no está en un eje ${p.direccion} (E12)`);
      }
      for (const [nid, tipo] of Object.entries(p.apoyos || {})) {
        if (!ns.has(nid)) E(`pórtico ${p.id}: apoyo en un nodo que no existe (${nid})`);
        if (!['empotrado', 'articulado'].includes(tipo)) E(`pórtico ${p.id}: apoyo «${tipo}» desconocido`);
      }
      for (const e of p.elementos || []) {
        unico(e.id, 'elemento');
        if (!['columna', 'viga', 'muro_concreto'].includes(e.tipo)) E(`elemento ${e.id}: tipo «${e.tipo}» desconocido`);
        if (!est.secciones[e.seccion]) E(`elemento ${e.id}: sección «${e.seccion}» no existe`);
        const ni = ns.get(e.i), nj = ns.get(e.j);
        if (!ni || !nj) { E(`elemento ${e.id}: nodos fuera de su pórtico`); continue; }
        if (e.tipo === 'viga') {
          if (ni.nivel !== nj.nivel) E(`viga ${e.id}: extremos en niveles distintos`);
          if (!(nj.s > ni.s)) E(`viga ${e.id}: el nodo j debe quedar a mayor s que el i`);
        } else {
          if (nj.nivel !== ni.nivel + 1) E(`${e.tipo} ${e.id}: j debe estar un nivel arriba de i`);
          if (Math.abs(ni.s - nj.s) > 1e-9) E(`${e.tipo} ${e.id}: no es vertical`);
          if (e.tipo === 'columna' && !e.fisico) A(`columna ${e.id}: sin «fisico» (E6)`);
        }
        if (e.brazo_rigido_m && !(Array.isArray(e.brazo_rigido_m) && e.brazo_rigido_m.length === 2 && e.brazo_rigido_m.every((x) => x >= 0))) {
          E(`elemento ${e.id}: brazo_rigido_m debe ser [di, dj] ≥ 0`);
        }
        if (e.w_gravedad_kN_m !== undefined && !esNum(e.w_gravedad_kN_m)) E(`elemento ${e.id}: w_gravedad_kN_m debe ser número`);
      }
    }
    for (const r of b.resortes || []) {
      unico(r.id, 'resorte');
      if (r.tipo !== 'muro_mamposteria') continue;
      if (typeof r.aislado !== 'boolean') A(`muro ${r.id}: sin «aislado» (E5); se toma como no aislado (el muro trabaja, como en la versión 1)`);
      for (const k of ['k0_kN_m', 'Vcr_kN', 'dcr_m', 'Vmax_kN', 'dmax_m', 'du_m', 'residual']) if (!esNum(r.envolvente?.[k])) E(`muro ${r.id}: falta envolvente.${k}`);
      if (!(r.envolvente?.dcr_m < r.envolvente?.dmax_m && r.envolvente?.dmax_m <= r.envolvente?.du_m)) E(`muro ${r.id}: se espera dcr < dmax ≤ du`);
      if (!Array.isArray(r.estados_de_dano) || !r.estados_de_dano.length) E(`muro ${r.id}: sin estados_de_dano`);
      if (!Number.isInteger(r.nivel) || r.nivel < 1 || r.nivel > N) E(`muro ${r.id}: nivel inválido`);
    }
  }
  const am = est.amortiguamiento;
  if (am.tipo !== 'rayleigh') E('amortiguamiento: tipo debe ser rayleigh');
  if (!(am.xi > 0 && am.xi < 0.2)) E('amortiguamiento: xi fuera de (0; 0,2)');
  if (am.periodos_ancla_s !== null && am.periodos_ancla_s !== undefined) {
    const p = am.periodos_ancla_s;
    if (!(Array.isArray(p) && p.length === 2 && p[0] > p[1] && p[1] > 0)) E('amortiguamiento: periodos_ancla_s debe ser [Ti, Tj] con Ti > Tj > 0, o null');
  } else if (am.periodos_ancla_s === undefined && !am.modos) {
    A('amortiguamiento: sin periodos_ancla_s (E8); el motor usa la regla por defecto');
  }
  if (am.modos) A('amortiguamiento: usa «modos» (E8: se recomienda periodos_ancla_s, que manda si están los dos)');
  if (am.rigidez && am.rigidez !== 'inicial_parte_elastica') A(`amortiguamiento: rigidez «${am.rigidez}» (E8 fija inicial_parte_elastica)`);
  if (!esNum(est.limites.deriva)) E('limites: falta «deriva»');
  for (const k of ['deriva_umbral_dano', 'deriva_umbral_dano_mamposteria']) if (!esNum(est.limites[k])) A(`limites: sin «${k}» (E9)`);
  for (const k of ['Aa', 'Av', 'Fa', 'Fv', 'I', 'R']) if (!esNum(est.diseno[k])) E(`diseno: falta «${k}»`);

  const theta = filasThetaY(est);
  for (const f of theta) {
    if (Math.abs(f.error) > 0.01) {
      E(`${f.campo} de ${f.seccion} en ${f.elemento}: archivo ${f.archivo}, ${f.formula} = ${f.esperado.toPrecision(5)} (L_f = ${f.L_f}); error ${(100 * f.error).toFixed(2)} % > 1 %`);
    }
  }
  return { errores, avisos, dim: dimensiones(est), theta };
}

function dentro([x, y], poli) {
  let c = false;
  for (let i = 0, j = poli.length - 1; i < poli.length; j = i++) {
    const [xi, yi] = poli[i], [xj, yj] = poli[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  // los puntos del borde cuentan como dentro
  for (let i = 0, j = poli.length - 1; i < poli.length; j = i++) {
    const [xi, yi] = poli[i], [xj, yj] = poli[j];
    const cruz = (xj - xi) * (y - yi) - (yj - yi) * (x - xi);
    if (Math.abs(cruz) < 1e-9 && x >= Math.min(xi, xj) - 1e-9 && x <= Math.max(xi, xj) + 1e-9 && y >= Math.min(yi, yj) - 1e-9 && y <= Math.max(yi, yj) + 1e-9) return true;
  }
  return c;
}

// ---------------------------------------------------------------------------------------------------------------
// Resultados
// ---------------------------------------------------------------------------------------------------------------
export function validarResultado(res, est = null, { tipado } = {}) {
  const errores = [], avisos = [];
  const E = (m) => errores.push(m), A = (m) => avisos.push(m);
  if (tipado === undefined) tipado = ArrayBuffer.isView(res?.t);

  for (const k of ['version', 'id', 'params', 'opciones', 'duracion_calculo_ms', 'factor_escala', 'iteraciones_escala', 'amortiguamiento',
    ...Object.keys(TIPOS_RESULTADOS), 'thp', 'envolventes', 'muros_mamposteria', 'equipos', 'calidad_numerica']) {
    if (!(k in (res || {}))) E(`falta el campo «${k}»`);
  }
  if (errores.length) return { errores, avisos, dim: null };
  if (res.version !== 1) E(`version = ${res.version}; se espera 1`);
  if (typeof res.id !== 'string' && typeof res.id !== 'number') E('id debe ser texto o número');
  if (!(esNum(res.duracion_calculo_ms) && res.duracion_calculo_ms >= 0)) E('duracion_calculo_ms debe ser ≥ 0');

  // tipos de los arreglos
  const revisarArreglo = (nombre, a, tipo) => {
    if (!esLista(a)) { E(`${nombre}: no es un arreglo`); return false; }
    if (tipado && a.constructor?.name !== tipo) E(`${nombre}: es ${a.constructor?.name}; se espera ${tipo}`);
    const rango = RANGO_ENTERO[tipo];
    for (let i = 0; i < a.length; i++) {
      const x = a[i];
      if (!esNum(x)) { E(`${nombre}[${i}] no es un número finito`); return false; }
      if (rango && (!Number.isInteger(x) || x < rango[0] || x > rango[1])) { E(`${nombre}[${i}] = ${x} no cabe en ${tipo}`); return false; }
      if (tipo === 'Float32Array' && !tipado && Math.abs(x) > 3.4e38) { E(`${nombre}[${i}] no cabe en Float32`); return false; }
    }
    return true;
  };
  for (const [k, tipo] of Object.entries(TIPOS_RESULTADOS)) revisarArreglo(k, res[k], tipo);
  if (!res.thp || typeof res.thp !== 'object') E('thp debe ser { elementos, valores }');
  else { revisarArreglo('thp.elementos', res.thp.elementos, 'Int32Array'); revisarArreglo('thp.valores', res.thp.valores, 'Int16Array'); }
  for (const k of CLAVES_ENVOLVENTES) {
    if (!(k in (res.envolventes || {}))) E(`envolventes: falta «${k}»`);
    else revisarArreglo(`envolventes.${k}`, res.envolventes[k], 'Float32Array');
  }
  if (errores.length) return { errores, avisos, dim: null };

  // tamaños
  const nt = res.t.length;
  let dim;
  if (est) dim = dimensiones(est);
  else {
    const N = res.u.length / (3 * nt);
    dim = { N, nE: res.dc.length / nt, nN: res.giros.length / nt, nP: res.derivas_porticos_env.length / N, niveles: [], porticos: [], elementos: [], muros: [], nodos: [] };
    A('sin estructura: los tamaños se deducen de los arreglos');
  }
  const { N, nE, nN, nP } = dim;
  const tam = {
    ag: nt * 2, u: nt * N * 3, a_abs: nt * N * 3, giros: nt * nN, v_nodos: nt * nN, dc: nt * nE, dc_flexion: nt * nE, dc_cortante: nt * nE,
    dc_rotacion: nt * nE, rotulas: nt * nE, derivas: nt * N * 2, derivas_vector: nt * N, derivas_porticos_env: nP * N, cortante_basal: nt * 3, energia: nt * 6,
  };
  const tamEnv = {
    u_max: N * 3, deriva_max: N * 2, t_deriva_max: N * 2, deriva_vector_max: N, punto_deriva_vector: N * 2, t_deriva_vector_max: N, a_abs_max: N * 3,
    dc_max: nE, t_dc_max: nE, gobierna: nE, Mi_max: nE, Mj_max: nE, V_max: nE, N_min: nE, N_max: nE, thp_max: nE * 2, t_primera_fluencia: nE * 2,
  };
  for (const [k, n] of Object.entries(tam)) if (res[k].length !== n) E(`${k}: tamaño ${res[k].length}; se espera ${n}`);
  for (const [k, n] of Object.entries(tamEnv)) if (res.envolventes[k].length !== n) E(`envolventes.${k}: tamaño ${res.envolventes[k].length}; se espera ${n}`);
  const k = res.thp.elementos.length;
  if (res.thp.valores.length !== nt * k * 2) E(`thp.valores: tamaño ${res.thp.valores.length}; se espera nt·k·2 = ${nt * k * 2}`);
  if (errores.length) return { errores, avisos, dim };

  // params y opciones
  const p = res.params, op = res.opciones;
  for (const [c, [a, b]] of Object.entries(RANGOS_PARAMS)) {
    if (!esNum(p[c])) E(`params.${c}: falta`);
    else if (p[c] < a || p[c] > b) E(`params.${c} = ${p[c]} fuera de [${a}, ${b}]`);
  }
  if (!Number.isInteger(p.semilla)) E('params.semilla debe ser entero');
  if (![0.005, 0.01].includes(op.dt_s)) E(`opciones.dt_s = ${op.dt_s}; se espera 0,005 o 0,01`);
  if (!['normal', 'baja'].includes(op.calidad)) E(`opciones.calidad = ${op.calidad}`);
  if ((op.calidad === 'baja') !== (op.dt_s === 0.01)) E('opciones: calidad baja va con dt_s = 0,01 y normal con 0,005');
  const pasoSal = op.dt_salida_s / op.dt_s;
  if (!(op.dt_salida_s >= op.dt_s) || Math.abs(pasoSal - Math.round(pasoSal)) > 1e-6) E('opciones.dt_salida_s debe ser múltiplo de dt_s');
  if (!esNum(op.angulo_deg) || op.angulo_deg < 0 || op.angulo_deg > 180) A(`opciones.angulo_deg = ${op.angulo_deg} fuera del control (0-180°)`);
  if (op.escala === 'nsr10') {
    if (!(esNum(res.factor_escala) && res.factor_escala > 0)) E('escala nsr10 sin factor_escala');
    if (!(Number.isInteger(res.iteraciones_escala) && res.iteraciones_escala >= 1 && res.iteraciones_escala <= 10)) E('iteraciones_escala debe estar entre 1 y 10');
  } else {
    if (!(esNum(op.escala) && op.escala > 0)) E(`opciones.escala = ${op.escala}; se espera un número > 0 o 'nsr10'`);
    if (res.factor_escala !== null) E('factor_escala debe ser null si la escala es numérica');
    if (res.iteraciones_escala !== 0) E('iteraciones_escala debe ser 0 si la escala es numérica');
  }
  if (res.origen_registro !== undefined && !(res.origen_registro && typeof res.origen_registro.tipo === 'string')) E('origen_registro debe traer «tipo»');
  const am = res.amortiguamiento;
  if (!(esNum(am.a0) && am.a0 >= 0 && esNum(am.a1) && am.a1 >= 0)) E('amortiguamiento: a0 y a1 deben ser ≥ 0');
  const pa = am.periodos_ancla_s;
  if (!(esLista(pa) && pa.length === 2 && pa[0] >= pa[1] && pa[1] > 0)) E('amortiguamiento.periodos_ancla_s debe ser [Ti, Tj] con Ti ≥ Tj > 0');
  if (!esLista(am.xi_modos)) E('amortiguamiento.xi_modos debe ser un arreglo');
  else {
    if (tipado && am.xi_modos.constructor.name !== 'Float32Array') E('amortiguamiento.xi_modos debe ser Float32Array');
    if (am.xi_modos.length !== Math.min(12, 3 * N)) E(`amortiguamiento.xi_modos: ${am.xi_modos.length} valores; se esperan min(12, 3N) = ${Math.min(12, 3 * N)}`);
    if (![...am.xi_modos].every((x) => esNum(x) && x > 0 && x < 1)) E('amortiguamiento.xi_modos fuera de (0, 1)');
  }

  // tiempo
  if (res.t[0] !== 0) E('t[0] debe ser 0');
  for (let i = 1; i < nt; i++) {
    if (Math.abs(res.t[i] - res.t[i - 1] - op.dt_salida_s) > 1e-5 * Math.max(1, res.t[i])) { E(`t no avanza de a dt_salida_s en i = ${i}`); break; }
  }
  const tFin = res.t[nt - 1];
  const enT = (x) => x >= -1e-6 && x <= tFin + 1e-5;

  // rangos físicos (cotas de plausibilidad, no de diseño)
  const cota = (nombre, a, max, unidad) => { const m = maxAbs(a); if (m > max) E(`${nombre}: |valor| = ${m} > ${max} ${unidad}`); };
  cota('ag', res.ag, 100, 'm/s²');
  for (let i = 0; i < nt * N; i++) {
    if (Math.abs(res.u[3 * i]) > 5 || Math.abs(res.u[3 * i + 1]) > 5) { E('u: desplazamiento > 5 m'); break; }
    if (Math.abs(res.u[3 * i + 2]) > 0.5) { E('u: giro rz > 0,5 rad'); break; }
  }
  cota('a_abs', res.a_abs, 500, 'm/s² o rad/s²');
  cota('giros', res.giros, 0.5, 'rad');
  cota('v_nodos', res.v_nodos, 1, 'm');
  for (const k2 of ['derivas', 'derivas_vector', 'derivas_porticos_env']) {
    if ([...res[k2]].some((x) => x < 0 || x > 0.5)) E(`${k2}: valores fuera de [0; 0,5]`);
  }

  // derivas: vector ≥ componentes; envolvente por pórtico = envolvente por dirección
  const porticoDentro = (pt, nv) => {
    if (!nv?.contorno) return false;
    const xs = nv.contorno.map((q) => q[0]), ys = nv.contorno.map((q) => q[1]);
    return pt.direccion === 'x' ? pt.coordenada >= Math.min(...ys) - 1e-9 && pt.coordenada <= Math.max(...ys) + 1e-9
      : pt.coordenada >= Math.min(...xs) - 1e-9 && pt.coordenada <= Math.max(...xs) + 1e-9;
  };
  if (est) {
    for (let kk = 0; kk < N; kk++) {
      const nv = dim.niveles[kk];
      if (!dim.porticos.every((pt) => porticoDentro(pt, nv))) continue;
      for (let i = 0; i < nt; i++) {
        const comp = Math.max(res.derivas[(i * N + kk) * 2], res.derivas[(i * N + kk) * 2 + 1]);
        if (res.derivas_vector[i * N + kk] < comp * (1 - 1e-5) - 1e-9) { E(`derivas_vector < deriva de un pórtico (paso ${i}, entrepiso ${kk + 1})`); break; }
      }
    }
    for (let kk = 0; kk < N; kk++) {
      for (const [c, dir] of [[0, 'x'], [1, 'y']]) {
        let m = 0;
        dim.porticos.forEach((pt, ip) => { if (pt.direccion === dir) m = Math.max(m, res.derivas_porticos_env[ip * N + kk]); });
        const env = res.envolventes.deriva_max[2 * kk + c];
        if (Math.abs(m - env) > 1e-5 * Math.max(env, 1e-12) + 1e-9) E(`derivas_porticos_env no coincide con envolventes.deriva_max (entrepiso ${kk + 1}, ${dir})`);
      }
    }
  }

  // envolventes contra las series (las envolventes se toman en cada Δt: deben ser ≥ que lo muestreado)
  const ev = res.envolventes;
  const geq = (nombre, envVal, serieVal, tol) => { if (envVal < serieVal - tol) E(`envolventes.${nombre} (${envVal}) < valor de la serie (${serieVal})`); };
  for (let j = 0; j < N * 3; j++) {
    let mu = 0, ma = 0;
    for (let i = 0; i < nt; i++) { mu = Math.max(mu, Math.abs(res.u[i * N * 3 + j])); ma = Math.max(ma, Math.abs(res.a_abs[i * N * 3 + j])); }
    geq(`u_max[${j}]`, ev.u_max[j], mu, 1e-6 * mu + 1e-12);
    geq(`a_abs_max[${j}]`, ev.a_abs_max[j], ma, 1e-6 * ma + 1e-9);
  }
  for (let j = 0; j < N * 2; j++) {
    let m = 0;
    for (let i = 0; i < nt; i++) m = Math.max(m, res.derivas[i * N * 2 + j]);
    geq(`deriva_max[${j}]`, ev.deriva_max[j], m, 1e-6 * m + 1e-12);
    if (!enT(ev.t_deriva_max[j])) E(`envolventes.t_deriva_max[${j}] fuera de [0, ${tFin}]`);
  }
  for (let kk = 0; kk < N; kk++) {
    let m = 0;
    for (let i = 0; i < nt; i++) m = Math.max(m, res.derivas_vector[i * N + kk]);
    geq(`deriva_vector_max[${kk}]`, ev.deriva_vector_max[kk], m, 1e-6 * m + 1e-12);
    if (!enT(ev.t_deriva_vector_max[kk])) E(`envolventes.t_deriva_vector_max[${kk}] fuera de [0, ${tFin}]`);
    const nv = dim.niveles[kk];
    if (est && nv?.contorno && ev.deriva_vector_max[kk] > 0) {
      const pt = [ev.punto_deriva_vector[2 * kk], ev.punto_deriva_vector[2 * kk + 1]];
      if (!nv.contorno.some((q) => Math.abs(q[0] - pt[0]) < 1e-4 && Math.abs(q[1] - pt[1]) < 1e-4)) E(`envolventes.punto_deriva_vector del entrepiso ${kk + 1} no es un vértice del contorno`);
    }
  }
  const fluyeAlguna = new Set();
  for (let e = 0; e < nE; e++) {
    let mdc = 0;
    for (let i = 0; i < nt; i++) {
      const d = res.dc[i * nE + e];
      mdc = Math.max(mdc, d);
      const m3 = Math.max(res.dc_flexion[i * nE + e], res.dc_cortante[i * nE + e], res.dc_rotacion[i * nE + e]);
      if (d !== m3) { E(`dc[${i}, ${e}] = ${d} no es el máximo de los tres cocientes (${m3})`); break; }
      const b = res.rotulas[i * nE + e];
      if (b & 3) fluyeAlguna.add(e);
      if ((b & 16) && !(b & 4)) E(`rotulas[${i}, ${e}]: LS en i sin IO en i`);
      if ((b & 32) && !(b & 8)) E(`rotulas[${i}, ${e}]: LS en j sin IO en j`);
      if ((b & 64) && !(b & 48)) E(`rotulas[${i}, ${e}]: CP sin LS`);
      if ((b & 1) && !(ev.t_primera_fluencia[2 * e] >= 0 && ev.t_primera_fluencia[2 * e] <= res.t[i] + 1e-5)) E(`rotulas[${i}, ${e}]: fluencia en i sin t_primera_fluencia ≤ t`);
      if ((b & 2) && !(ev.t_primera_fluencia[2 * e + 1] >= 0 && ev.t_primera_fluencia[2 * e + 1] <= res.t[i] + 1e-5)) E(`rotulas[${i}, ${e}]: fluencia en j sin t_primera_fluencia ≤ t`);
    }
    // dc va × 100 y redondeado: dc_max (cociente) ≥ max(dc)/100 − 0,005
    geq(`dc_max[${e}]`, ev.dc_max[e], mdc / 100, 0.0051);
    if (ev.dc_max[e] < 2.55 && ev.dc_max[e] * 100 > mdc + 100) A(`dc_max[${e}] mucho mayor que la serie (pico entre salidas)`);
    if (!enT(ev.t_dc_max[e])) E(`envolventes.t_dc_max[${e}] fuera de [0, ${tFin}]`);
    if (![0, 1, 2].includes(ev.gobierna[e])) E(`envolventes.gobierna[${e}] = ${ev.gobierna[e]}; se espera 0, 1 o 2`);
    for (const c of ['Mi_max', 'Mj_max', 'V_max']) if (ev[c][e] < 0) E(`envolventes.${c}[${e}] < 0`);
    if (ev.N_min[e] > ev.N_max[e]) E(`envolventes.N_min[${e}] > N_max`);
    for (const c of [0, 1]) {
      if (ev.thp_max[2 * e + c] < 0) E(`envolventes.thp_max[${2 * e + c}] < 0`);
      const tp = ev.t_primera_fluencia[2 * e + c];
      if (!(tp === -1 || enT(tp))) E(`envolventes.t_primera_fluencia[${2 * e + c}] = ${tp}; se espera −1 o un tiempo del análisis`);
      if (tp >= 0) fluyeAlguna.add(e);
    }
  }
  // thp
  const el = [...res.thp.elementos];
  for (let i = 1; i < el.length; i++) if (!(el[i] > el[i - 1])) { E('thp.elementos debe ir en orden creciente y sin repetir'); break; }
  if (el.some((x) => x < 0 || x >= nE)) E('thp.elementos fuera de [0, nE)');
  for (const e of fluyeAlguna) if (!el.includes(e)) E(`el elemento ${e} fluye y no está en thp.elementos`);
  el.forEach((e, j) => {
    for (const c of [0, 1]) {
      let m = 0;
      for (let i = 0; i < nt; i++) m = Math.max(m, Math.abs(res.thp.valores[(i * k + j) * 2 + c]));
      if (m * 1e-5 > ev.thp_max[2 * e + c] + 1.5e-5) E(`thp del elemento ${e} (extremo ${c ? 'j' : 'i'}) mayor que envolventes.thp_max`);
    }
  });

  // energía: columnas entrada, cinética, elástica, amortiguada, histerética, trabajo_PDelta (kJ)
  let eMax = 0;
  for (let i = 0; i < nt; i++) eMax = Math.max(eMax, Math.abs(res.energia[6 * i]));
  let amAnt = -Infinity;
  for (let i = 0; i < nt; i++) {
    const [ent, cin, ela, amo, his, pd] = [...res.energia.slice(6 * i, 6 * i + 6)];
    if (cin < -1e-9) E(`energia: cinética negativa en el paso ${i}`);
    if (amo < amAnt - 1e-6 * Math.max(1, Math.abs(amAnt))) E(`energia: la amortiguada decrece en el paso ${i}`);
    amAnt = amo;
    if (Math.abs(ent - (cin + ela + amo + his + pd)) > 0.01 * eMax + 1e-6) E(`energia: el balance no cierra en el paso ${i} (error > 1 % de la entrada máxima)`);
    if (pd > 1e-6 * Math.max(1, eMax)) A(`energia: trabajo_PDelta positivo en el paso ${i}`);
  }

  // muros de mampostería
  const murosEst = new Map(dim.muros.map((m) => [m.id, m]));
  if (!Array.isArray(res.muros_mamposteria)) E('muros_mamposteria debe ser una lista');
  else {
    for (const m of res.muros_mamposteria) {
      if (typeof m.id !== 'string' || typeof m.aislado !== 'boolean' || !esNum(m.deriva_max) || m.deriva_max < 0 || !ESTADOS_MURO.includes(m.estado)) {
        E(`muros_mamposteria: fila inválida ${JSON.stringify(m)}`);
        continue;
      }
      const me = murosEst.get(m.id);
      if (est && !me) { E(`muros_mamposteria: ${m.id} no está en la estructura`); continue; }
      if (me) {
        if ((me.aislado ?? false) !== m.aislado) A(`muros_mamposteria: ${m.id} con aislado distinto del de la estructura (escenario «sin aislar»)`);
        let esperado = 'sin_dano';
        for (const ed of me.estados_de_dano) if (m.deriva_max >= ed.deriva) esperado = ed.nombre;
        if (esperado !== m.estado) E(`muros_mamposteria: ${m.id} con deriva ${m.deriva_max} debería estar «${esperado}», no «${m.estado}»`);
      }
    }
    if (est && res.muros_mamposteria.length !== dim.muros.length) E(`muros_mamposteria: ${res.muros_mamposteria.length} filas; la estructura tiene ${dim.muros.length} muros`);
  }

  // equipos
  if (!Array.isArray(res.equipos)) E('equipos debe ser una lista');
  else for (const q of res.equipos) {
    const nom = `equipos[${q.unidad}]`;
    if (typeof q.unidad !== 'string' || typeof q.anclaje !== 'string') { E(`${nom}: faltan unidad o anclaje`); continue; }
    if (!REGIMENES_EQUIPO.includes(q.regimen)) E(`${nom}: régimen «${q.regimen}»`);
    for (const c of ['a_max_m_s2', 'deslizamiento_max_m', 'deslizamiento_final_m']) if (!(esNum(q[c]) && q[c] >= 0)) E(`${nom}: ${c} debe ser ≥ 0`);
    for (const c of ['desliza', 'inicia_balanceo']) if (typeof q[c] !== 'boolean') E(`${nom}: ${c} debe ser true o false`);
    if (q.deslizamiento_final_m > q.deslizamiento_max_m + 1e-9) E(`${nom}: deslizamiento final mayor que el máximo`);
    if (q.regimen === 'anclado') {
      if (!(esNum(q.fuerza_anclaje_kN) && q.fuerza_anclaje_kN >= 0)) E(`${nom}: anclado sin fuerza_anclaje_kN`);
      if (q.desliza || q.inicia_balanceo) E(`${nom}: anclado no desliza ni se balancea`);
    } else {
      if (q.fuerza_anclaje_kN !== null) E(`${nom}: fuerza_anclaje_kN debe ser null si no está anclado`);
      if (!(esNum(q.razon_vuelco) && q.razon_vuelco >= 0)) E(`${nom}: razon_vuelco debe ser ≥ 0`);
    }
    if (q.regimen === 'desliza' && q.inicia_balanceo) E(`${nom}: régimen desliza con inicio de balanceo`);
    if (q.regimen === 'balancea' && (q.desliza || q.deslizamiento_max_m > 0)) E(`${nom}: régimen balancea con deslizamiento`);
    if (q.desliza !== (q.deslizamiento_max_m > 0)) E(`${nom}: desliza no coincide con deslizamiento_max_m`);
  }

  // calidad numérica
  const cq = res.calidad_numerica;
  const pasosBase = Math.round(tFin / op.dt_s);
  for (const c of ['pasos', 'subdivisiones', 'no_convergidos']) if (!(Number.isInteger(cq[c]) && cq[c] >= 0)) E(`calidad_numerica.${c} debe ser entero ≥ 0`);
  if (cq.pasos < pasosBase) E(`calidad_numerica.pasos = ${cq.pasos} < ${pasosBase} (duración / dt_s)`);
  if (!(esNum(cq.iteraciones_promedio) && cq.iteraciones_promedio >= 1)) E('calidad_numerica.iteraciones_promedio debe ser ≥ 1');
  for (const c of ['error_energia_max', 'error_deformacion_max']) {
    if (!(esNum(cq[c]) && cq[c] >= 0)) E(`calidad_numerica.${c} debe ser ≥ 0`);
    else if (cq[c] >= 0.01) E(`calidad_numerica.${c} = ${cq[c]} ≥ 1 % (7.4)`);
  }
  if (!(esNum(cq.indice_estabilidad_max) && cq.indice_estabilidad_max >= 0)) E('calidad_numerica.indice_estabilidad_max debe ser ≥ 0');
  else if (cq.indice_estabilidad_max > 0.1) A(`índice de estabilidad ${cq.indice_estabilidad_max} > 0,10`);
  if (cq.no_convergidos > 0) A(`${cq.no_convergidos} pasos sin converger`);
  return { errores, avisos, dim };
}

// ---------------------------------------------------------------------------------------------------------------
// Serie de un elemento (mensaje serie_elemento del 7.5)
// ---------------------------------------------------------------------------------------------------------------
export function validarSerie(serie, res, est) {
  const errores = [], avisos = [];
  const E = (m) => errores.push(m);
  if (serie.tipo !== 'serie_elemento') E(`serie: tipo «${serie.tipo}»`);
  const dim = dimensiones(est);
  const ie = dim.elementos.findIndex((e) => e.id === serie.elemento);
  if (ie < 0) { E(`serie: elemento ${serie.elemento} no existe`); return { errores, avisos }; }
  const nt = res.t.length, nE = dim.nE;
  for (const c of ['t', 'Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc']) {
    if (!esLista(serie[c]) || serie[c].length !== nt) E(`serie.${c}: se esperan ${nt} valores`);
    else if (![...serie[c]].every(esNum)) E(`serie.${c}: valores no finitos`);
  }
  if (errores.length) return { errores, avisos };
  for (let i = 0; i < nt; i++) if (Math.abs(serie.t[i] - res.t[i]) > 1e-6) { E('serie.t distinto de resultados.t'); break; }
  const ev = res.envolventes;
  const tol = (x) => 1e-5 * Math.abs(x) + 1e-6;
  if (maxAbs(serie.Mi) > ev.Mi_max[ie] + tol(ev.Mi_max[ie])) E('serie.Mi supera envolventes.Mi_max');
  if (maxAbs(serie.Mj) > ev.Mj_max[ie] + tol(ev.Mj_max[ie])) E('serie.Mj supera envolventes.Mj_max');
  if (maxAbs(serie.V) > ev.V_max[ie] + tol(ev.V_max[ie])) E('serie.V supera envolventes.V_max');
  for (let i = 0; i < nt; i++) {
    if (serie.N[i] < ev.N_min[ie] - tol(ev.N_min[ie]) || serie.N[i] > ev.N_max[ie] + tol(ev.N_max[ie])) { E('serie.N fuera de [N_min, N_max]'); break; }
    // dc de la serie (cociente) frente a dc del resultado (× 100, redondeado)
    const d = res.dc[i * nE + ie];
    if (d < 255 && Math.abs(serie.dc[i] * 100 - d) > 0.51) { E(`serie.dc[${i}] = ${serie.dc[i]} no coincide con resultados.dc (${d}/100)`); break; }
  }
  const j = [...res.thp.elementos].indexOf(ie);
  const k = res.thp.elementos.length;
  for (let i = 0; i < nt; i++) {
    for (const [c, nom] of [[0, 'thp_i'], [1, 'thp_j']]) {
      const ref = j >= 0 ? res.thp.valores[(i * k + j) * 2 + c] * 1e-5 : 0;
      if (Math.abs(serie[nom][i] - ref) > 1.0e-5) { E(`serie.${nom}[${i}] = ${serie[nom][i]} no coincide con thp (${ref})`); return { errores, avisos }; }
    }
  }
  return { errores, avisos };
}

// ---------------------------------------------------------------------------------------------------------------
// Línea de comandos
// ---------------------------------------------------------------------------------------------------------------
async function cli() {
  const { readFileSync, existsSync } = await import('node:fs');
  const { dirname, join, resolve, relative } = await import('node:path');
  const { fileURLToPath } = await import('node:url');
  const raiz = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
  const args = process.argv.slice(2);
  const opt = (n) => { const i = args.indexOf(n); if (i < 0) return null; const v = args[i + 1]; args.splice(i, 2); return v; };
  let rutaEst = opt('--estructura'), rutaSerie = opt('--serie');
  const rutaRes = args.find((a) => !a.startsWith('--')) || null;
  if (!rutaRes && !rutaEst) {
    console.error('uso: node scripts/sismo/validar_resultado.mjs <resultado.json> [--estructura <estructura.json>] [--serie <serie.json>]');
    process.exit(2);
  }
  const leer = (r) => JSON.parse(readFileSync(r, 'utf8'));
  const rel = (r) => relative(process.cwd(), resolve(r)) || r;
  if (rutaRes && !rutaEst && existsSync(join(dirname(rutaRes), 'estructura_min.json'))) rutaEst = join(dirname(rutaRes), 'estructura_min.json');
  if (rutaRes && !rutaSerie && /_min\.json$/.test(rutaRes) && existsSync(join(dirname(rutaRes), 'serie_elemento_min.json'))) rutaSerie = join(dirname(rutaRes), 'serie_elemento_min.json');
  let errores = 0;
  const informe = (titulo, r) => {
    console.log(`${r.errores.length ? '✗' : '✓'} ${titulo}: ${r.errores.length} errores, ${r.avisos.length} avisos`);
    for (const m of r.errores.slice(0, 40)) console.log('    error: ' + m);
    if (r.errores.length > 40) console.log(`    … y ${r.errores.length - 40} errores más`);
    for (const m of r.avisos.slice(0, 20)) console.log('    aviso: ' + m);
    errores += r.errores.length;
  };
  const resumenTheta = (r) => {
    if (!r.theta?.length) return;
    const peor = r.theta.reduce((a, b) => (Math.abs(b.error) > Math.abs(a.error) ? b : a));
    const secciones = new Set(r.theta.map((f) => f.seccion));
    console.log(`    theta_y y theta_y_e: ${r.theta.length} comprobaciones en ${secciones.size} secciones; mayor diferencia ${(100 * peor.error).toFixed(2)} % (${peor.campo} de ${peor.seccion} en ${peor.elemento}; tolerancia ± 1 %)`);
  };
  let est = null;
  if (rutaEst) {
    est = leer(rutaEst);
    const r = validarEstructura(est);
    informe(`estructura ${rel(rutaEst)}`, r);
    resumenTheta(r);
  }
  const torre = join(raiz, 'data', 'sismo', 'torre_hospital_estructura.json');
  if (existsSync(torre) && (!rutaEst || resolve(rutaEst) !== torre)) {
    const r = validarEstructura(leer(torre));
    informe(`estructura ${rel(torre)}`, r);
    resumenTheta(r);
  } else if (!existsSync(torre)) {
    console.log(`· ${rel(torre)} todavía no existe (la genera scripts/sismo/estructura_torre.py): sin comprobar`);
  }
  if (rutaRes) {
    const res = leer(rutaRes);
    const r = validarResultado(res, est, { tipado: false });
    if (r.dim) console.log(`    tamaños: nt = ${res.t.length}, N = ${r.dim.N}, nE = ${r.dim.nE}, nN = ${r.dim.nN}, nP = ${r.dim.nP}; thp de ${res.thp.elementos.length} elementos`);
    informe(`resultados ${rel(rutaRes)}`, r);
    if (rutaSerie && est && !r.errores.length) informe(`serie ${rel(rutaSerie)}`, validarSerie(leer(rutaSerie), res, est));
  }
  process.exit(errores ? 1 : 0);
}

if (typeof process !== 'undefined' && process.argv?.[1]) {
  const { pathToFileURL } = await import('node:url');
  if (import.meta.url === pathToFileURL(process.argv[1]).href) await cli();
}
