// Estructuras y registros pequeños para las pruebas del motor (ayudante; test_motor.mjs salta los «_*.mjs»).
// Todo en el formato de data/sismo/<id>_estructura.json (ESQUEMA.md), con los campos mínimos que lee modelo.js.

export const E_MPA = 30000;                 // MPa → E = 3·10⁷ kN/m²
export const E = E_MPA * 1000;

/** Sección elástica (fluencia inalcanzable salvo que se dé My). Sin Av: sin deformación por cortante (Av → ∞). */
export function seccion(I, { A = 1, Av, My = 1e12, Mpos, Mneg, alfa = 0.03, histeresis = 'bilineal', limites = true } = {}) {
  const s = { tipo: 'rectangular', material: 'm', A, I, factor_fisuracion: 1, My_kNm: My, My_e_kNm: My, Mn_e_kNm: 1.1 * My, Vn_e_kN: 1e12,
    endurecimiento: alfa, histeresis };
  if (Av !== undefined) s.Av = Av;
  if (Mpos !== undefined) { s.My_e_pos_kNm = Mpos; s.My_e_neg_kNm = Mneg ?? My; }
  if (limites) Object.assign(s, { theta_p_IO: 0.005, theta_p_LS: 0.015, theta_p_CP: 0.02 });
  return s;
}

/**
 * Pórtico plano de `n` niveles con columnas en las posiciones `s` (empotradas en la base) y vigas entre ellas.
 * col y viga: nombres de sección (col puede ser una función (k, i) → nombre). w: carga de gravedad de las vigas.
 */
export function portico({ id, dir, c, s, n, col, viga, w = 0, brazos = null, desde = 1 }) {
  const p = { id, direccion: dir, coordenada: c, nodos: [], apoyos: {}, elementos: [] };
  for (let k = desde - 1; k <= n; k++) s.forEach((x, i) => p.nodos.push({ id: `${id}/${i}-${k}`, s: x, nivel: k }));
  s.forEach((_, i) => { p.apoyos[`${id}/${i}-${desde - 1}`] = 'empotrado'; });
  for (let k = desde; k <= n; k++) {
    s.forEach((_, i) => p.elementos.push({ id: `C-${id}-${i}-${k}`, tipo: 'columna', i: `${id}/${i}-${k - 1}`, j: `${id}/${i}-${k}`,
      seccion: typeof col === 'function' ? col(k, i) : col, nivel: k, ...(brazos ? { brazo_rigido_m: brazos.col } : {}) }));
    if (viga) for (let i = 0; i + 1 < s.length; i++) {
      p.elementos.push({ id: `V-${id}-${i}-${k}`, tipo: 'viga', i: `${id}/${i}-${k}`, j: `${id}/${i + 1}-${k}`, seccion: typeof viga === 'function' ? viga(k, i) : viga,
        nivel: k, ...(w ? { w_gravedad_kN_m: w } : {}), ...(brazos ? { brazo_rigido_m: brazos.viga } : {}) });
    }
  }
  return p;
}

/** Estructura de un bloque. niveles: [{ h, m, Jz, cm, contorno?, W? }] (W: peso sísmico; por defecto m·g). */
export function estructura({ niveles, porticos, secciones, p_delta = false, resortes = [], xi = 0.05, periodos_ancla_s = null }) {
  let z = 0;
  return {
    id: 'prueba', nombre: 'estructura de prueba', tipo_dato: 'estimacion', sistema_estructural: 'prueba', norma: 'prueba',
    materiales: { m: { tipo: 'concreto', Ec_MPa: E_MPA, nu: 0.2 } },
    secciones,
    bloques: [{
      id: 'b', porticos, resortes,
      niveles: niveles.map((nv, k) => {
        z += nv.h;
        return { id: `N${k + 1}`, z, altura_entrepiso: nv.h, masa_t: nv.m, Jz_t_m2: nv.Jz, cm: nv.cm, contorno: nv.contorno,
          peso_sismico_kN: nv.W ?? nv.m * 9.80665 };
      }),
    }],
    amortiguamiento: { tipo: 'rayleigh', xi, periodos_ancla_s, rigidez: 'inicial_parte_elastica' },
    p_delta, limites: {}, diseno: { Aa: 0.15, Av: 0.15, Fa: 1.5, Fv: 2.2, I: 1.5 }, fuentes: [], supuestos: [], incertidumbres: [],
  };
}

/**
 * Edificio de planta rectangular Lx × Ly con dos pórticos X (en y = 0 e y = Ly) y dos Y (en x = 0 y x = Lx), de un
 * vano cada uno. colX/colY y vigaX/vigaY: secciones (o funciones (k, i) para la de X o Y según el pórtico).
 */
export function cajon({ n, h, Lx, Ly, m, Jz, secciones, colX, vigaX, colY, vigaY, p_delta = false, cm, W, resortes = [], colX2, vigaX2 }) {
  const contorno = [[0, 0], [Lx, 0], [Lx, Ly], [0, Ly]];
  const niveles = [];
  for (let k = 0; k < n; k++) niveles.push({ h: Array.isArray(h) ? h[k] : h, m: Array.isArray(m) ? m[k] : m, Jz: Array.isArray(Jz) ? Jz[k] : Jz,
    cm: cm ? (Array.isArray(cm[0]) ? cm[k] : cm) : [Lx / 2, Ly / 2], contorno, W: Array.isArray(W) ? W[k] : W });
  const porticos = [
    portico({ id: 'X1', dir: 'x', c: 0, s: [0, Lx], n, col: colX, viga: vigaX }),
    portico({ id: 'X2', dir: 'x', c: Ly, s: [0, Lx], n, col: colX2 ?? colX, viga: vigaX2 ?? vigaX }),
    portico({ id: 'Y1', dir: 'y', c: 0, s: [0, Ly], n, col: colY, viga: vigaY }),
    portico({ id: 'Y2', dir: 'y', c: Lx, s: [0, Ly], n, col: colY, viga: vigaY }),
  ];
  return estructura({ niveles, porticos, secciones, p_delta, resortes });
}

/**
 * Registro sintético determinista (dos componentes): suma de senos con una envolvente de Saragoni-Hart. Sirve para
 * las pruebas que no deben depender de movimiento.js. → { dt, ax, ay } en m/s² (pico ≈ pico_m_s2)
 */
export function registroPrueba({ dt = 0.005, duracion = 8, pico_m_s2 = 3 } = {}) {
  const n = Math.round(duracion / dt) + 1;
  const ax = new Float64Array(n), ay = new Float64Array(n);
  const f = [0.7, 1.3, 2.1, 3.4, 5.5, 8.9], fase = [0.3, 1.1, 2.0, 0.7, 2.8, 1.6];
  let mx = 0;
  for (let i = 0; i < n; i++) {
    const t = i * dt, tn = t / (0.4 * duracion);
    const env = tn > 0 ? Math.pow(tn, 1.5) * Math.exp(-1.5 * (tn - 1)) : 0;
    let sx = 0, sy = 0;
    f.forEach((fk, k) => { sx += Math.sin(2 * Math.PI * fk * t + fase[k]) / (1 + k * 0.3); sy += Math.cos(2 * Math.PI * fk * 1.07 * t + fase[k] * 0.6) / (1 + k * 0.4); });
    ax[i] = env * sx; ay[i] = env * sy * 0.8;
    mx = Math.max(mx, Math.abs(ax[i]));
  }
  for (let i = 0; i < n; i++) { ax[i] *= pico_m_s2 / mx; ay[i] *= pico_m_s2 / mx; }
  return { dt, ax, ay };
}

/** Parámetros válidos del movimiento (para los Resultados de las pruebas que usan registros propios). */
export const PARAMS_PRUEBA = { Mw: 6.2, profundidad_km: 150, distancia_epicentral_km: 92, vs30_m_s: 270, semilla: 2028 };
