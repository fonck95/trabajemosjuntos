// Estructura sintética del tamaño de la torre (ayudante de las pruebas; test_motor.mjs salta los «_*.mjs»).
// Sirve para medir tiempos (7.7) y probar el determinismo (T17) con un modelo de ≈ 400 elementos mientras
// data/sismo/torre_hospital_estructura.json no exista (lo genera scripts/sismo/estructura_torre.py). Geometría del
// contrato (1.2): ejes A-D y 1-7, niveles 4,5 / 8,7 / 12,9 / 17,1 m, el piso 4 solo en las líneas 3-7, columnas de
// 0,60 × 0,60 m en cada cruce (en sus dos pórticos, como en TABS), vigas de 0,40 × 0,60 m y muros de 0,30 m en los
// núcleos del oriente. Propiedades y cargas: valores de prueba del orden de los del prediseño (estimación), NO de
// diseño; las secciones cumplen theta_y = My·L_f/(6·EI_fis) para que la estructura pase validar_resultado.mjs.

const EJES_X = [['A', -13.0], ['B', -5.8], ['C', 1.4], ['D', 8.6]];
const EJES_Y = [['1', -19.6], ['2', -12.4], ['3', -7.6], ['4', 0.8], ['5', 8.0], ['6', 14.0], ['7', 22.4]];
const Z = [0, 4.5, 8.7, 12.9, 17.1];
const EC = 24870, NU = 0.2;                                  // MPa (NSR-10 C.8.5.1, f'c = 28 MPa)

function rect(b, h, fis, My, extra = {}) {
  const A = b * h, I = (b * h ** 3) / 12;
  return { tipo: 'rectangular', b, h, material: 'concreto_28', A, I, Av: (5 / 6) * A, factor_fisuracion: fis, My_kNm: My, ...extra };
}

function seccionPorLongitud(base, Lf) {
  // theta_y = My·L_f/(6·EI_fis) con la L_f de esa familia de elementos (validar_resultado.mjs, ± 1 %)
  const EI = EC * 1000 * base.I * base.factor_fisuracion;
  const ty = (base.My_kNm * Lf) / (6 * EI), tye = ((base.My_e_kNm ?? base.My_kNm) * Lf) / (6 * EI);
  return { ...base, theta_y: Number(ty.toPrecision(4)), theta_y_e: Number(tye.toPrecision(4)) };
}

/** Estructura en el formato de data/sismo/<id>_estructura.json (ESQUEMA.md), ≈ 400 elementos y ≈ 300 nodos. */
export function torreSintetica({ conMuros = true, conMamposteria = true, aislada = true } = {}) {
  const secciones = {};
  const comunes = { Mn_kNm: 0, phiMn_kNm: 0, Mpr_kNm: 0, theta_p_cap: 0.03, theta_p_b: 0.05, Vn_kN: 0, phiVn_kN: 0, endurecimiento: 0.03, histeresis: 'bilineal' };
  const col = (nombre, Lf) => {
    const s = rect(0.6, 0.6, 0.7, 560, { ...comunes, P_gravedad_kN: 1500, Mn_kNm: 620, phiMn_kNm: 560, Mpr_kNm: 780, Vn_kN: 900, phiVn_kN: 675,
      My_e_kNm: 700, Mn_e_kNm: 775, Vn_e_kN: 1050, theta_p_IO: 0.005, theta_p_LS: 0.015, theta_p_CP: 0.02, calculo: 'valores de prueba (torre sintética)' });
    secciones[nombre] = seccionPorLongitud(s, Lf);
  };
  const viga = (nombre, Lf) => {
    const s = rect(0.4, 0.6, 0.35, 330, { ...comunes, My_pos_kNm: 240, My_neg_kNm: 330, Mn_kNm: 365, phiMn_kNm: 330, Mpr_kNm: 460, Vn_kN: 520, phiVn_kN: 390,
      My_e_kNm: 410, My_e_pos_kNm: 300, My_e_neg_kNm: 410, Mn_e_kNm: 455, Vn_e_kN: 600, theta_p_IO: 0.01, theta_p_LS: 0.02, theta_p_CP: 0.025, theta_p_cap: 0.025,
      calculo: 'valores de prueba (torre sintética)' });
    secciones[nombre] = seccionPorLongitud(s, Lf);
  };
  // familias por longitud flexible (columnas con brazo de 0,30 m arriba; vigas con 0,30 m en cada extremo)
  for (const h of [4.5, 4.2]) col(`C60-${h}`, h - 0.3);
  const luces = new Set();
  for (let i = 1; i < EJES_X.length; i++) luces.add(+(EJES_X[i][1] - EJES_X[i - 1][1]).toFixed(2));
  for (let i = 1; i < EJES_Y.length; i++) luces.add(+(EJES_Y[i][1] - EJES_Y[i - 1][1]).toFixed(2));
  for (const L of luces) viga(`V40x60-${L}`, L - 0.6);
  const muro = (nombre, L) => {
    const A = 0.3 * L, I = (0.3 * L ** 3) / 12, fis = 0.35, lp = Math.min(0.5 * L, 4.2);
    const My = 0.9 * 420e3 * (0.0025 * A) * 0.8 * L / 2 + 0.5 * 2000 * L * 0.8;   // estimación gruesa de prueba
    const EI = EC * 1000 * I * fis;
    secciones[nombre] = {
      tipo: 'muro', b: 0.3, h: L, material: 'concreto_28', A, I, Av: (5 / 6) * A, factor_fisuracion: fis, lp_m: lp,
      My_kNm: My, Mn_kNm: 1.1 * My, phiMn_kNm: My, Mpr_kNm: 1.4 * My, Vn_kN: 0.17 * Math.sqrt(28) * 1000 * 0.8 * A, phiVn_kN: 0.75 * 0.17 * Math.sqrt(28) * 1000 * 0.8 * A,
      My_e_kNm: 1.25 * My, Mn_e_kNm: 1.37 * My, Vn_e_kN: 1.15 * 0.17 * Math.sqrt(28) * 1000 * 0.8 * A,
      theta_y: Number(((My * lp) / EI).toPrecision(4)), theta_y_e: Number(((1.25 * My * lp) / EI).toPrecision(4)),
      theta_p_cap: 0.015, theta_p_b: 0.02, theta_p_IO: 0.004, theta_p_LS: 0.008, theta_p_CP: 0.012,
      endurecimiento: 0.02, histeresis: 'bilineal', calculo: 'valores de prueba (torre sintética)',
    };
  };

  const niveles = [];
  const contorno13 = [[-13.0, -19.6], [8.6, -19.6], [8.6, 22.4], [-13.0, 22.4]];
  const contorno4 = [[-13.0, -7.6], [8.6, -7.6], [8.6, 22.4], [-13.0, 22.4]];
  for (let k = 1; k <= 4; k++) {
    const c4 = k === 4;
    const a = 21.6, b = c4 ? 30 : 42, m = (c4 ? 0.85 : 1.05) * a * b;   // t: losa, muros, acabados y 25 % de la viva (estimación)
    const cm = [-2.2 + 0.1 * k, c4 ? 7.4 : 1.4];
    niveles.push({ id: `N${k}`, z: Z[k], altura_entrepiso: Z[k] - Z[k - 1], masa_t: +m.toFixed(1), Jz_t_m2: +((m * (a * a + b * b)) / 12).toFixed(1), cm,
      contorno: c4 ? contorno4 : contorno13, peso_sismico_kN: +(m * 9.80665).toFixed(1), P_sobre_entrepiso_kN: 0 });
  }
  const porticos = [];
  const lineaPresente = (ejeY, k) => k < 4 || ['3', '4', '5', '6', '7'].includes(ejeY);
  // pórticos X (a lo largo de x, en cada línea de y)
  for (const [ny, y] of EJES_Y) {
    const kMax = lineaPresente(ny, 4) ? 4 : 3;
    const p = { id: `X-${ny}`, direccion: 'x', coordenada: y, nodos: [], apoyos: {}, elementos: [] };
    for (let k = 0; k <= kMax; k++) for (const [nx, x] of EJES_X) p.nodos.push({ id: `X-${ny}/${nx}${k}`, s: x, nivel: k });
    for (const [nx] of EJES_X) p.apoyos[`X-${ny}/${nx}0`] = 'empotrado';
    for (let k = 1; k <= kMax; k++) {
      for (const [nx] of EJES_X) p.elementos.push({ id: `C-${nx}${ny}-${k}@X`, fisico: `C-${nx}${ny}-${k}`, tipo: 'columna', i: `X-${ny}/${nx}${k - 1}`, j: `X-${ny}/${nx}${k}`,
        seccion: `C60-${k === 1 ? 4.5 : 4.2}`, eje: `${nx}-${ny}`, nivel: k, brazo_rigido_m: [0, 0.3] });
      for (let i = 1; i < EJES_X.length; i++) {
        const [na, xa] = EJES_X[i - 1], [nb, xb] = EJES_X[i];
        p.elementos.push({ id: `VX-${ny}-${na}${nb}-${k}`, tipo: 'viga', i: `X-${ny}/${na}${k}`, j: `X-${ny}/${nb}${k}`, seccion: `V40x60-${+(xb - xa).toFixed(2)}`,
          eje: `${ny} entre ${na} y ${nb}`, nivel: k, w_gravedad_kN_m: k === 4 ? 22 : 30, brazo_rigido_m: [0.3, 0.3] });
      }
    }
    porticos.push(p);
  }
  // pórticos Y
  for (const [nx, x] of EJES_X) {
    const p = { id: `Y-${nx}`, direccion: 'y', coordenada: x, nodos: [], apoyos: {}, elementos: [] };
    for (let k = 0; k <= 4; k++) for (const [ny, y] of EJES_Y) if (lineaPresente(ny, k)) p.nodos.push({ id: `Y-${nx}/${ny}${k}`, s: y, nivel: k });
    for (const [ny] of EJES_Y) p.apoyos[`Y-${nx}/${ny}0`] = 'empotrado';
    for (let k = 1; k <= 4; k++) {
      const ys = EJES_Y.filter(([ny]) => lineaPresente(ny, k));
      for (const [ny] of ys) p.elementos.push({ id: `C-${nx}${ny}-${k}@Y`, fisico: `C-${nx}${ny}-${k}`, tipo: 'columna', i: `Y-${nx}/${ny}${k - 1}`, j: `Y-${nx}/${ny}${k}`,
        seccion: `C60-${k === 1 ? 4.5 : 4.2}`, eje: `${nx}-${ny}`, nivel: k, brazo_rigido_m: [0, 0.3] });
      for (let i = 1; i < ys.length; i++) {
        const [na, ya] = ys[i - 1], [nb, yb] = ys[i];
        p.elementos.push({ id: `VY-${nx}-${na}${nb}-${k}`, tipo: 'viga', i: `Y-${nx}/${na}${k}`, j: `Y-${nx}/${nb}${k}`, seccion: `V40x60-${+(yb - ya).toFixed(2)}`,
          eje: `${nx} entre ${na} y ${nb}`, nivel: k, w_gravedad_kN_m: k === 4 ? 22 : 30, brazo_rigido_m: [0.3, 0.3] });
      }
    }
    porticos.push(p);
  }
  // muros de los núcleos (oriente): en y sobre x = 3,1 (escaleras sur y norte) y en x sobre las líneas 6 y 7
  if (conMuros) {
    const muros = [
      { id: 'MY-E', dir: 'y', c: 3.1, s: -3.4, L: 8.4, kMin: 3 },     // escalera sur (y −7,6 a 0,8): existe en los 4 pisos
      { id: 'MY-F', dir: 'y', c: 3.1, s: 18.2, L: 8.4, kMin: 6 },     // escalera norte (y 14,0 a 22,4)
      { id: 'MY-G', dir: 'y', c: 3.1, s: 4.4, L: 5.6, kMin: 4 },      // foso de ascensores (y 1,6 a 7,2)
      { id: 'MX-6', dir: 'x', c: 14.0, s: 5.85, L: 5.5, kMin: 6 },
      { id: 'MX-7', dir: 'x', c: 22.4, s: 5.85, L: 5.5, kMin: 7 },
      { id: 'MX-3', dir: 'x', c: -7.6, s: 5.85, L: 5.5, kMin: 3 },
    ];
    for (const w of muros) {
      const nombre = `MURO-${w.L}`;
      if (!secciones[nombre]) muro(nombre, w.L);
      const p = { id: w.id, direccion: w.dir, coordenada: w.c, nodos: [], apoyos: { [`${w.id}/0`]: 'empotrado' }, elementos: [] };
      for (let k = 0; k <= 4; k++) p.nodos.push({ id: `${w.id}/${k}`, s: w.s, nivel: k, ...(k > 0 ? { carga_kN: 250 } : {}) });
      for (let k = 1; k <= 4; k++) p.elementos.push({ id: `${w.id}-${k}`, tipo: 'muro_concreto', i: `${w.id}/${k - 1}`, j: `${w.id}/${k}`, seccion: nombre, eje: w.id, nivel: k });
      porticos.push(p);
    }
  }
  const resortes = [];
  if (conMamposteria) {
    const env = { k0_kN_m: 200000, Vcr_kN: 90, dcr_m: 0.00045, Vmax_kN: 120, dmax_m: 0.0126, du_m: 0.042, residual: 0.2 };
    const estados = [{ nombre: 'leve', deriva: 0.001 }, { nombre: 'moderado', deriva: 0.003 }, { nombre: 'extenso', deriva: 0.006 }, { nombre: 'colapso', deriva: 0.01 }];
    let n = 0;
    for (let k = 1; k <= 3; k++) {
      for (const [dir, c] of [['x', -19.6], ['x', 22.4], ['y', -13.0], ['y', 8.6]]) {
        resortes.push({ id: `M-F${++n}`, tipo: 'muro_mamposteria', direccion: dir, coordenada: c, nivel: k, aislado: aislada, L: 7.2, t: 0.15, h: Z[k] - Z[k - 1] - 0.6,
          material: 'ladrillo', aberturas_pct: 30, envolvente: env, histeresis: 'tomazevic', modo_falla: 'tension_diagonal', estados_de_dano: estados, calculo: 'valores de prueba' });
      }
    }
  }
  return {
    id: 'torre_sintetica', nombre: 'Torre sintética de prueba (tamaño de la torre del hospital)', tipo_dato: 'estimacion',
    sistema_estructural: 'pórticos de concreto con muros en los núcleos (prueba)', norma: 'valores de prueba',
    materiales: {
      concreto_28: { tipo: 'concreto', fc_MPa: 28, Ec_MPa: EC, nu: NU, peso_kN_m3: 24, fuente: "NSR-10 C.8.5.1: Ec = 4700√f'c" },
      ladrillo: { tipo: 'mamposteria', fm_MPa: 4.0, Em_MPa: 2800, Gm_MPa: 1120, tau0_MPa: 0.12, peso_kN_m3: 18, fuente: 'valores de prueba' },
    },
    secciones,
    ejes: { x: EJES_X.map(([id, x]) => ({ id, x })), y: EJES_Y.map(([id, y]) => ({ id, y })) },
    bloques: [{ id: 'torre', niveles, porticos, resortes }],
    amortiguamiento: { tipo: 'rayleigh', xi: 0.05, periodos_ancla_s: null, rigidez: 'inicial_parte_elastica' },
    p_delta: true,
    limites: { deriva: 0.01, deriva_umbral_dano: 0.004, deriva_umbral_dano_mamposteria: 0.002, tipo_deriva: 'vectorial en los vértices del contorno', fuente: 'NSR-10 A.6.3.1, A.6.4.1 y Tabla A.12.5-1' },
    diseno: { Aa: 0.15, Av: 0.15, suelo: 'D', Fa: 1.5, Fv: 2.2, I: 1.5, Ta_s: 0.41, Sa_g: 0.84375, R: 5, Vs_kN: 0 },
    fuentes: [], supuestos: ['Estructura sintética para pruebas del motor: no es el prediseño de la torre.'], incertidumbres: [],
  };
}

/** Equipos de prueba repartidos por los pisos (EquipoRiesgo del 7.4). */
export function equiposSinteticos(n = 60) {
  const anclajes = ['apoyado', 'ruedas_con_freno', 'anclado', 'sobre', 'pared', 'apoyado'];
  const out = [];
  for (let i = 0; i < n; i++) {
    const piso = (i % 4) + 1;
    const ymin = piso === 4 ? -7.0 : -19.0;
    out.push({
      unidad: `U-prueba-${(0x100000 + i).toString(16).slice(-6)}-001`, piso, x: -12 + ((i * 7.3) % 20), y: ymin + ((i * 11.1) % (22 - ymin)),
      z_sobre_piso: 0, anclaje: anclajes[i % anclajes.length], masa_kg: 40 + (i % 9) * 30, h_cg_m: 0.4 + (i % 5) * 0.2,
      mu: 0.25 + (i % 4) * 0.1, bx_m: 0.2 + (i % 3) * 0.1, by_m: 0.15 + (i % 4) * 0.1, rot_z: (i % 8) * (Math.PI / 8),
    });
  }
  out.push({ unidad: 'U-fijo-cub001-001', piso: 'CUB', x: 0, y: 10, z_sobre_piso: 0, anclaje: 'anclado', masa_kg: 5000, h_cg_m: 1.2, mu: 0.5, bx_m: 1.0, by_m: 1.0, rot_z: 0 });
  return out;
}
