// Motor sísmico: toda la lógica que usan el trabajador (trabajador.js) y el respaldo en el hilo principal
// (web/js/scenes/torre/sismo.js). Contrato de la torre, 7.5; data/sismo/ESQUEMA.md, «Mensajes del trabajador».
// Módulo puro: sin DOM ni three; imports relativos con extensión. movimiento.js se importa de forma dinámica la
// primera vez que se necesita (armar el modelo no depende de él).
//
//   const motor = crearMotor();
//   const listo = await motor.iniciar({ url_estructura, url_amenaza, opciones })   // o { estructura, amenaza }
//   const mov = await motor.movimiento(params)
//   const res = await motor.analizar(params, opciones, (fraccion, t_s) => …, senal)  // Resultados (7.6)
//   const s = motor.serieElemento('C-A3-1@X')                                       // copias de la historia interna
//   motor.cancelar()
//
// analizar corre de corrido (dentro del trabajador) o, si opciones.ceder es una función (o crearMotor({ modo:
// 'tramos' })), por tramos de ≈ presupuesto_ms cediendo al bucle de eventos: mismos resultados bit a bit.
import {
  armarModelo, gravedad, modos, amortiguamiento, resumenModelo, infoElementos, infoNodos, ErrorMotor,
} from './modelo.js';
import { analizar as analizarDeCorrido, analizarPorTramos } from './integrador.js';

let promesaMovimiento = null;
/** movimiento.js, cargado una vez (import dinámico). */
export function cargarMovimiento() {
  promesaMovimiento ??= import('./movimiento.js').catch((e) => {
    promesaMovimiento = null;
    throw new ErrorMotor('interno', `no se pudo cargar movimiento.js: ${e.message}`);
  });
  return promesaMovimiento;
}

const DT_SINTESIS = 0.005;   // s: la síntesis siempre a 0,005 s (7.4)
const DT_BAJA = 0.01;        // s: calidad baja (registro filtrado a 20 Hz y diezmado)
const OPCIONES_ANALISIS = ['dt_salida_s', 'duracion_s', 'angulo_deg', 'escala', 'calidad', 'tolerancia', 'max_iter', 'max_subdiv', 'equipos', 'guardar_serie_completa', 'intervalo_progreso_ms'];

async function leerJSONPorDefecto(url) {
  let r;
  try { r = await fetch(url); } catch (e) { throw new ErrorMotor('datos', `no se pudo leer ${url}: ${e.message}`); }
  if (!r.ok) throw new ErrorMotor('datos', `no se pudo leer ${url} (${r.status})`);
  try { return await r.json(); } catch (e) { throw new ErrorMotor('datos', `${url} no es JSON válido: ${e.message}`); }
}

/** Clave de los parámetros del movimiento (los mismos parámetros dan el mismo registro). */
function claveParams(p) {
  const q = p || {};
  return JSON.stringify(['Mw', 'profundidad_km', 'distancia_epicentral_km', 'vs30_m_s', 'semilla', 'regimen'].map((k) => q[k] ?? null));
}

const f32 = (a) => Float32Array.from(a);

/** Parámetros del espectro de la NSR-10: los de la estructura (`diseno`) o los de amenaza.json → nsr10. */
function parametrosNSR10(estructura, amenaza) {
  const d = estructura?.diseno || {};
  const n = amenaza?.nsr10 || {};
  const val = (x) => (typeof x === 'number' ? x : x?.valor ?? x?.valor_yondo);
  const p = { Aa: d.Aa ?? val(n.Aa), Av: d.Av ?? val(n.Av), Fa: d.Fa ?? val(n.Fa), Fv: d.Fv ?? val(n.Fv), I: d.I ?? val(n.I), Ad: val(n.Ad) ?? 0.04 };
  for (const k of ['Aa', 'Av', 'Fa', 'Fv', 'I']) if (!(p[k] > 0)) throw new ErrorMotor('datos', `falta el parámetro ${k} del espectro de la NSR-10`);
  return p;
}

export function crearMotor(config = {}) {
  const leer = config.leer ?? leerJSONPorDefecto;
  let estructura = null, amenaza = null, urlE = null, urlA = null;
  let modelo = null, listo = null;
  let periodosEscala = null;     // { T1x, T1y }: los del modelo de diseño, para la escala «nsr10»
  let ultimoMov = null;          // { clave, reg } — registro de 0,005 s (Float64) del último `movimiento`
  let historia = null;
  let ultimo = null;             // { registro (0,005 s, sin escalar), factor, iteraciones } del último análisis
  let control = null;            // AbortController del análisis en curso

  function exigirModelo() {
    if (!modelo) throw new ErrorMotor('datos', 'falta el mensaje iniciar (no hay modelo armado)');
  }
  function exigirAmenaza() {
    if (!amenaza) throw new ErrorMotor('datos', 'falta amenaza.json (url_amenaza en iniciar)');
  }

  /**
   * Arma el modelo, la gravedad, los 12 modos y el amortiguamiento. op: el mensaje `iniciar` del 7.5
   * ({ v: 1, url_estructura, url_amenaza, opciones: { histeresis, noEstructurales, pDelta } }) o, en Node y en las
   * pruebas, { estructura, amenaza, opciones } con los objetos ya leídos. → la carga de `listo` (7.5).
   */
  async function iniciar(op = {}) {
    if (op.v !== undefined && op.v !== 1) throw new ErrorMotor('datos', `versión de mensajes no soportada: ${op.v}`);
    if (op.estructura) { estructura = op.estructura; urlE = null; }
    else if (op.url_estructura && (op.url_estructura !== urlE || !estructura)) { estructura = await leer(op.url_estructura); urlE = op.url_estructura; }
    if (op.amenaza) { amenaza = op.amenaza; urlA = null; }
    else if (op.url_amenaza && (op.url_amenaza !== urlA || !amenaza)) { amenaza = await leer(op.url_amenaza); urlA = op.url_amenaza; }
    if (!estructura) throw new ErrorMotor('datos', 'iniciar sin estructura (url_estructura)');
    const o = op.opciones || {};
    modelo = null; listo = null; historia = null; periodosEscala = null;
    const opModelo = { histeresis: o.histeresis ?? null, noEstructurales: o.noEstructurales ?? 'aislados', pDelta: o.pDelta };
    const mod = armarModelo(estructura, opModelo);
    const g = gravedad(mod);
    const md = modos(mod, 12);
    const am = amortiguamiento(mod);
    // Escala «nsr10»: con los períodos del modelo de diseño (muros de mampostería como dice el archivo), sea cual sea
    // el escenario. Así «Aislados» y «Sin aislar» reciben el mismo movimiento del suelo y el contraste de E5 muestra
    // solo el efecto de la estructura (revisión A6: con los períodos de «Sin aislar» el factor subía 12-14 %).
    const mdDiseno = mod.muros.some((m) => m.aislado !== m.aisladoArchivo)
      ? modos(armarModelo(estructura, { ...opModelo, noEstructurales: 'aislados' }), 12) : md;
    periodosEscala = { T1x: mdDiseno.T1x, T1y: mdDiseno.T1y, modelo: mdDiseno === md ? 'el analizado' : 'el de diseño (muros de mampostería como en el archivo)' };
    modelo = mod;
    listo = {
      tipo: 'listo', id: op.id ?? null,
      resumen: resumenModelo(mod),
      elementos: infoElementos(mod),
      nodos: infoNodos(mod),
      modos: {
        periodos_s: [...md.periodos_s],
        masa_participativa: { x: [...md.masa_participativa.x], y: [...md.masa_participativa.y], rz: [...md.masa_participativa.rz] },
        formas: md.formas.map((f) => [...f]),
        T1x: md.T1x, T1y: md.T1y,
      },
      amortiguamiento: { a0: am.a0, a1: am.a1, periodos_ancla_s: [...am.periodos_ancla_s], xi_modos: [...am.xi_modos], regla: am.regla },
      escala_nsr10: { ...periodosEscala },
      gravedad: { iteraciones: g.iteraciones },
      avisos: [...mod.avisos],
    };
    return listo;
  }

  /** Registro de 0,005 s de estos parámetros (el del último `movimiento` si son los mismos). */
  async function registroDe(params) {
    exigirAmenaza();
    const clave = claveParams(params);
    if (ultimoMov && ultimoMov.clave === clave) return ultimoMov.reg;
    const mov = await cargarMovimiento();
    const reg = mov.sintetizar(params, amenaza);
    ultimoMov = { clave, reg };
    return reg;
  }

  /** Síntesis, espectros, Fourier, GMPE y espectro de la NSR-10. → la carga del mensaje `movimiento` (7.5). */
  async function movimiento(params) {
    const mov = await cargarMovimiento();
    const reg = await registroDe(params);
    const T = mov.periodosLog(60);
    const Sx = mov.espectroRespuesta(reg.ax, reg.dt, T, 0.05).Sa_g;
    const Sy = mov.espectroRespuesta(reg.ay, reg.dt, T, 0.05).Sa_g;
    const Fx = mov.espectroFourier(reg.ax, reg.dt), Fy = mov.espectroFourier(reg.ay, reg.dt);
    const gm = mov.gmpeEscenario(params, amenaza);
    const n10 = parametrosNSR10(estructura, amenaza);
    return {
      tipo: 'movimiento',
      registro: { dt: reg.dt, n: reg.n ?? reg.ax.length, ax: f32(reg.ax), ay: f32(reg.ay), meta: reg.meta, intensidades: reg.intensidades, avisos: [...(reg.avisos || [])] },
      espectro: { T: f32(T), Sa_x: f32(Sx), Sa_y: f32(Sy) },
      fourier: { f: f32(Fx.f_Hz), A_x: f32(Fx.A_m_s), A_y: f32(Fy.A_m_s) },
      gmpe: gm.map((x) => ({ nombre: x.nombre, modelo: x.modelo, regimen: x.regimen, peso: x.peso, T: f32(x.T), mediana_g: f32(x.mediana_g), sigma_ln: f32(x.sigma_ln) })),
      nsr10: {
        T: f32(T),
        con_I: f32(mov.espectroNSR10(T, { ...n10 })),
        sin_I: f32(mov.espectroNSR10(T, { ...n10, I: 1 })),
        // umbral de daño (A.12.3; ξ = 2 %, sin I): el mismo espectro con que el prediseño revisa la deriva ≤ 0,4 %
        umbral_dano: f32(mov.espectroUmbralDano(T, { Ad: n10.Ad, Fa: n10.Fa, Fv: n10.Fv })),
        xi: 0.05, xi_umbral_dano: mov.XI_UMBRAL_DANO,
      },
    };
  }

  /**
   * Escala «nivel de diseño NSR-10» (7.4): f iguala la media, en los períodos de 0,8·T1 a 1,2·T1 (de x y de y), del
   * espectro de la media geométrica de las dos componentes (ξ = 5 %) con la del espectro de diseño con I. T1x y T1y
   * son los del modelo de diseño (muros de mampostería como en el archivo), también en «Sin aislar». Como el factor
   * de suelo no lineal depende del PGA en roca, la pasada de suelo se repite con PGAr × f hasta que f cambie < 1 %
   * (máximo 10 vueltas). → { reg (sin escalar), f, iteraciones }
   */
  async function escalaNSR10(params, pausa = async () => {}) {
    const mov = await cargarMovimiento();
    const per = [];
    for (const T1 of [periodosEscala.T1x, periodosEscala.T1y]) for (let i = 0; i <= 10; i++) per.push(T1 * (0.8 + 0.04 * i));
    const Tp = Float64Array.from(per);
    const n10 = parametrosNSR10(estructura, amenaza);
    const obj = mov.espectroNSR10(Tp, { ...n10 });
    let mObj = 0;
    for (const x of obj) mObj += x / obj.length;
    let reg = await registroDe(params), f = NaN, it = 0;
    for (it = 1; it <= 10; it++) {
      if (it > 1) { await pausa(); reg = mov.sintetizar({ ...params, escala_pgar: f }, amenaza); }
      const sx = mov.espectroRespuesta(reg.ax, reg.dt, Tp, 0.05).Sa_g, sy = mov.espectroRespuesta(reg.ay, reg.dt, Tp, 0.05).Sa_g;
      let mGm = 0;
      for (let i = 0; i < Tp.length; i++) mGm += Math.sqrt(sx[i] * sy[i]) / Tp.length;
      if (!(mGm > 0)) throw new ErrorMotor('datos', 'escala nsr10: el registro no tiene respuesta en el rango de períodos');
      const fN = mObj / mGm;
      const cambio = it > 1 ? Math.abs(fN - f) / f : Infinity;
      f = fN;
      if (cambio < 0.01) break;
    }
    return { reg, f, iteraciones: Math.min(it, 10) };
  }

  /**
   * Análisis no lineal en el tiempo. params: los del movimiento; opciones: las del 7.4 (dt_salida_s, duracion_s,
   * angulo_deg, escala, calidad, equipos, …) y, para el respaldo, ceder y presupuesto_ms. → Resultados (7.6).
   * La historia interna (series por elemento) se queda aquí para serieElemento y nunca se transfiere.
   */
  async function analizar(params, opciones = {}, alProgreso, senal) {
    exigirModelo();
    const o = opciones || {};
    const calidad = o.calidad === 'baja' ? 'baja' : 'normal';
    // señal propia (cancelar) unida a la de quien llama
    control = new AbortController();
    const mia = control;
    if (senal) { if (senal.aborted) mia.abort(); else senal.addEventListener('abort', () => mia.abort(), { once: true }); }
    const porTramos = typeof o.ceder === 'function' || config.modo === 'tramos';
    const ceder = o.ceder ?? config.ceder ?? (() => new Promise((ok) => setTimeout(ok, 0)));
    // por tramos, también se cede entre las etapas previas (síntesis, vueltas de la escala nsr10, filtro)
    const pausa = async () => {
      if (!porTramos) return;
      await ceder();
      if (mia.signal.aborted) { const e = new Error('análisis cancelado'); e.name = 'AbortError'; e.codigo = 'cancelado'; throw e; }
    };
    let reg, factor = null, iteraciones = 0;
    if (o.escala === 'nsr10') ({ reg, f: factor, iteraciones } = await escalaNSR10(params, pausa));
    else reg = await registroDe(params);
    await pausa();
    if (Math.abs(reg.dt - DT_SINTESIS) > 1e-12) throw new ErrorMotor('interno', `registro con dt = ${reg.dt}; la síntesis debe ser de ${DT_SINTESIS} s`);
    let regCalc = reg;
    if (calidad === 'baja') {
      const mov = await cargarMovimiento();
      const fx = mov.filtrarYDiezmar(reg.ax, reg.dt), fy = mov.filtrarYDiezmar(reg.ay, reg.dt);
      regCalc = { dt: fx.dt, ax: fx.a, ay: fy.a };
      await pausa();
    }
    const op = { dt_s: calidad === 'baja' ? DT_BAJA : DT_SINTESIS };
    for (const k of OPCIONES_ANALISIS) if (o[k] !== undefined) op[k] = o[k];
    op.calidad = calidad;
    if (o.escala === 'nsr10') { op.escala = 'nsr10'; op.factor_escala = factor; op.iteraciones_escala = iteraciones; }
    op.params = { ...params };
    op.id = o.id ?? 'analisis';
    let r;
    try {
      r = porTramos
        ? await analizarPorTramos(modelo, regCalc, op, { presupuesto_ms: o.presupuesto_ms ?? config.presupuesto_ms ?? 12, ceder, alProgreso, senal: mia.signal })
        : analizarDeCorrido(modelo, regCalc, op, alProgreso, mia.signal);
    } finally {
      if (control === mia) control = null;
    }
    historia = r.historia;
    ultimo = { registro: reg, factor: factor ?? (typeof o.escala === 'number' ? o.escala : 1), iteraciones };
    return r.resultados;
  }

  /** Series de un elemento (copias de la historia interna, Float32Array). → la carga de `serie_elemento` (7.5). */
  function serieElemento(id) {
    if (!historia) throw new ErrorMotor('datos', 'todavía no hay un análisis del que sacar la serie');
    const ie = modelo.indiceElemento.get(id);
    if (ie === undefined) throw new ErrorMotor('datos', `elemento desconocido: ${id}`);
    const { nt, nE } = historia;
    const sacar = (a) => { const s = new Float32Array(nt); for (let i = 0; i < nt; i++) s[i] = a[i * nE + ie]; return s; };
    return {
      tipo: 'serie_elemento', elemento: id, t: historia.t.slice(),
      Mi: sacar(historia.Mi), Mj: sacar(historia.Mj), V: sacar(historia.V), N: sacar(historia.N),
      thp_i: sacar(historia.thp_i), thp_j: sacar(historia.thp_j), dc: sacar(historia.dc),
    };
  }

  function cancelar() { control?.abort(); }

  return {
    iniciar, movimiento, analizar, serieElemento, cancelar,
    /** Para las pruebas y para exportar_caso.mjs (ola 2): el modelo armado, la estructura y la historia. */
    get modelo() { return modelo; },
    get estructura() { return estructura; },
    get historia() { return historia; },
    get ultimoAnalisis() { return ultimo; },
  };
}
