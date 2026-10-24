// Pruebas del motor y del trabajador (web/js/sismo/motor.js y trabajador.js): T17 del contrato (7.8) y además
//   W1  el trabajador responde los mensajes del 7.5 (cargado, listo, movimiento, progreso, resultado, serie_elemento,
//       errores) con arreglos tipados transferidos y resultados que pasan validar_resultado.mjs
//   E1  escala «nivel de diseño NSR-10» (7.4) y calidad baja (Δt = 0,01 s sobre el registro filtrado y diezmado)
//   R1  tiempos del 7.7 en escritorio con un modelo del tamaño de la torre (≈ 400 elementos) y memoria de los
//       resultados más la historia interna
// T18 (la estructura real de la torre) es de la ola 2: se escribe cuando exista data/sismo/torre_hospital_estructura.json.
import { readFile } from 'node:fs/promises';
import { crearMotor, cargarMovimiento } from '../../../web/js/sismo/motor.js';
import { validarResultado, validarSerie } from '../validar_resultado.mjs';
import { torreSintetica, equiposSinteticos } from './_torre_sintetica.mjs';
import { RAIZ, leerJSON, caso, comprobar, errorRelativo } from './_util.mjs';

const FIX = 'scripts/fixtures/torre/';
const ahora = () => performance.now();
const amenaza = () => leerJSON('data/sismo/amenaza.json');
const escenario = (am, id) => {
  const e = am.escenarios.find((x) => x.id === id);
  return { Mw: e.Mw, profundidad_km: e.profundidad_km, distancia_epicentral_km: e.distancia_epicentral_km, vs30_m_s: am.controles.vs30_m_s.defecto, semilla: am.controles.semilla.defecto };
};
const EQUIPOS = [
  { unidad: 'U-consulta_externa-2d1bfe-001', piso: 2, x: 1.2, y: 3.8, z_sobre_piso: 0, anclaje: 'apoyado', masa_kg: 60, h_cg_m: 0.45, mu: 0.3, bx_m: 0.3, by_m: 0.25, rot_z: 0 },
  { unidad: 'U-fijo-91b0de-001', piso: 'CUB', x: 3.5, y: 3.5, z_sobre_piso: 0, anclaje: 'anclado', masa_kg: 200, h_cg_m: 0.7, mu: 0.5, bx_m: 0.5, by_m: 0.4, rot_z: 0 },
];

/** Diferencias entre dos Resultados, bit a bit (salvo duracion_calculo_ms). → lista de rutas distintas */
function diferencias(a, b, ruta = '', out = []) {
  if (ruta === 'duracion_calculo_ms') return out;
  if (ArrayBuffer.isView(a) || ArrayBuffer.isView(b)) {
    if (!ArrayBuffer.isView(a) || !ArrayBuffer.isView(b) || a.constructor !== b.constructor || a.length !== b.length) out.push(ruta);
    else {
      const ba = new Uint8Array(a.buffer, a.byteOffset, a.byteLength), bb = new Uint8Array(b.buffer, b.byteOffset, b.byteLength);
      for (let i = 0; i < ba.length; i++) if (ba[i] !== bb[i]) { out.push(ruta); break; }
    }
  } else if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ks = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of ks) diferencias(a[k], b[k], ruta ? `${ruta}.${k}` : k, out);
  } else if (!Object.is(a, b)) out.push(ruta);
  return out;
}

// ---- T17: determinismo -------------------------------------------------------------------------------------------
async function t17() {
  const am = amenaza(), casos = [];
  const params = escenario(am, 'cimitarra');
  const op = { duracion_s: 12, escala: 4, equipos: EQUIPOS, angulo_deg: 30 };   // escala con fluencia y daño en la mampostería
  const correr = async (config = {}, extra = {}) => {
    const m = crearMotor(config);
    await m.iniciar({ estructura: leerJSON(FIX + 'estructura_min.json'), amenaza: am });
    const r = await m.analizar(params, { ...op, ...extra });
    return { r, s: m.serieElemento('VX-1-AB-1') };
  };
  const a = await correr(), b = await correr();
  const d = diferencias(a.r, b.r);
  casos.push(comprobar('dos motores, misma semilla y opciones: Resultados idénticos bit a bit', d.length === 0, d.length ? `distintos: ${d.slice(0, 5).join(', ')}` :
    `${a.r.thp.elementos.length} elementos con fluencia, ${a.r.t.length} salidas`));
  casos.push(comprobar('serie_elemento idéntica', diferencias(a.s, b.s).length === 0));
  // por tramos (respaldo del hilo principal), cediendo al bucle de eventos: lo mismo bit a bit
  let cesiones = 0;
  const ceder = () => new Promise((ok) => { cesiones++; setImmediate(ok); });
  const c = await correr({}, { ceder, presupuesto_ms: 2 });
  const dc = diferencias(a.r, c.r);
  casos.push(comprobar('por tramos (cediendo cada ≈ 2 ms) igual que de corrido, bit a bit', dc.length === 0 && cesiones > 0,
    dc.length ? `distintos: ${dc.slice(0, 5).join(', ')}` : `${cesiones} cesiones`));
  // la síntesis también: mismo registro con la misma semilla; otra semilla, otro registro
  const mov = await cargarMovimiento();
  const r1 = mov.sintetizar(params, am), r2 = mov.sintetizar(params, am), r3 = mov.sintetizar({ ...params, semilla: params.semilla + 7 }, am);
  casos.push(comprobar('sintetizar: misma semilla → mismo acelerograma; otra semilla → otro', diferencias(r1.ax, r2.ax).length === 0 && diferencias(r1.ax, r3.ax).length > 0));
  // un modelo del tamaño de la torre, 10 s
  const torre = torreSintetica();
  const correrT = async () => {
    const m = crearMotor();
    await m.iniciar({ estructura: torre, amenaza: am });
    return m.analizar(params, { duracion_s: 10, equipos: equiposSinteticos(20) });
  };
  const ta = await correrT(), tb = await correrT();
  const dt = diferencias(ta, tb);
  casos.push(comprobar('torre sintética (≈ 400 elementos), 10 s: idénticos bit a bit', dt.length === 0, dt.length ? dt.slice(0, 5).join(', ') : `${ta.thp.elementos.length} elementos con fluencia`));
  return casos;
}

// ---- W1: el trabajador ---------------------------------------------------------------------------------------------
async function w1() {
  const est = leerJSON(FIX + 'estructura_min.json');
  const recibidos = [];
  const selfFalso = { postMessage: (m, transferir) => recibidos.push({ m, transferir: transferir || [] }), onmessage: null };
  const selfAntes = globalThis.self, fetchAntes = globalThis.fetch;
  globalThis.self = selfFalso;
  globalThis.fetch = async (url) => {
    const u = new URL(url);
    if (u.protocol !== 'file:') return fetchAntes(url);
    try { const texto = await readFile(u, 'utf8'); return { ok: true, status: 200, json: async () => JSON.parse(texto) }; } catch { return { ok: false, status: 404, json: async () => null }; }
  };
  const casos = [];
  try {
    await import(new URL('web/js/sismo/trabajador.js', RAIZ).href + '?w1=' + Date.now());
    casos.push(comprobar('«cargado» al evaluar el módulo', recibidos[0]?.m.tipo === 'cargado'));
    const enviar = async (msg) => { recibidos.length = 0; await selfFalso.onmessage({ data: msg }); return recibidos.map((r) => r.m); };
    let r = await enviar({ tipo: 'analizar', id: 1, params: {}, opciones: {} });
    casos.push(comprobar('analizar antes de iniciar → error «datos»', r[0]?.tipo === 'error' && r[0].codigo === 'datos' && r[0].id === 1, r[0]?.mensaje));
    r = await enviar({ tipo: 'iniciar', v: 1, id: 2, url_estructura: new URL(FIX + 'estructura_min.json', RAIZ).href, url_amenaza: new URL('data/sismo/amenaza.json', RAIZ).href,
      opciones: { histeresis: 'bilineal', noEstructurales: 'aislados' } });
    const listo = r[0];
    casos.push(comprobar('listo: resumen, 24 elementos y 24 nodos de estructura_min.json, modos y amortiguamiento', listo?.tipo === 'listo' && listo.id === 2 &&
      listo.elementos.length === 24 && listo.nodos.length === 24 && listo.modos.periodos_s.length === 6 && listo.amortiguamiento.xi_modos.length === 6,
      listo ? `T1 = ${listo.modos.periodos_s[0].toFixed(4)} s, T1x = ${listo.modos.T1x.toFixed(4)} s; a0 = ${listo.amortiguamiento.a0.toFixed(4)}, a1 = ${listo.amortiguamiento.a1.toExponential(3)}` : JSON.stringify(r[0])));
    const am = amenaza();
    const params = escenario(am, 'nido_2015');
    r = await enviar({ tipo: 'movimiento', id: 3, params });
    const mv = r[0];
    casos.push(comprobar('movimiento: registro Float32 a 0,005 s, espectros, Fourier, GMPE y NSR-10, transferidos', mv?.tipo === 'movimiento' && mv.registro.ax instanceof Float32Array &&
      mv.registro.dt === 0.005 && mv.espectro.Sa_x.length === 60 && mv.gmpe.length > 0 && mv.nsr10.con_I.length === 60 && recibidos[0].transferir.length >= 10,
      mv?.registro ? `PGA x = ${mv.registro.intensidades.x.pga_g.toFixed(4)} g, ${mv.registro.n} muestras, ${recibidos[0].transferir.length} búferes` : JSON.stringify(mv)));
    r = await enviar({ tipo: 'analizar', id: 4, params, opciones: { duracion_s: 6, escala: 20, equipos: EQUIPOS, intervalo_progreso_ms: 0 } });
    const prog = r.filter((m) => m.tipo === 'progreso'), fin = r.find((m) => m.tipo === 'resultado');
    casos.push(comprobar('progreso y resultado', prog.length >= 1 && fin?.id === 4 && prog.every((p) => p.fraccion > 0 && p.fraccion <= 1), `${prog.length} mensajes de progreso`));
    if (fin) {
      const v = validarResultado(fin.resultados, est, { tipado: true });
      casos.push(caso('resultado tipado que pasa validar_resultado', v.errores.length, 0, v.errores[0] ?? `${fin.resultados.thp.elementos.length} elementos con fluencia; avisos: ${v.avisos.length}`));
      casos.push(comprobar('búferes de Resultados transferidos', recibidos.find((x) => x.m.tipo === 'resultado').transferir.length >= 30));
      // analizar usa el registro del último `movimiento` (mismos params): ag de salida j = 20 × ax[4j] (Δt_salida = 4·Δt)
      let peorAg = 0;
      for (let j = 0; j < fin.resultados.t.length; j++) peorAg = Math.max(peorAg, Math.abs(fin.resultados.ag[2 * j] - 20 * mv.registro.ax[4 * j]));
      casos.push(caso('analizar con el registro del último movimiento: ag = escala × registro (m/s²)', peorAg, 1e-5));
    }
    r = await enviar({ tipo: 'serie_elemento', id: 5, elemento: 'C-A1-1@X' });
    const s = r[0];
    if (s?.tipo === 'serie_elemento' && fin) {
      const resJson = JSON.parse(JSON.stringify(fin.resultados, (k, x) => (ArrayBuffer.isView(x) ? Array.from(x) : x)));
      const v = validarSerie({ ...s, t: [...s.t] }, resJson, est);
      casos.push(caso('serie_elemento después del resultado, coherente con él (historia interna)', v.errores.length, 0, v.errores[0] ?? `${s.t.length} instantes`));
    } else casos.push(comprobar('serie_elemento', false, JSON.stringify(s)));
    r = await enviar({ tipo: 'serie_elemento', id: 6, elemento: 'NO-EXISTE' });
    casos.push(comprobar('elemento desconocido → error «datos»', r[0]?.tipo === 'error' && r[0].codigo === 'datos'));
    r = await enviar({ tipo: 'otra_cosa', id: 7 });
    casos.push(comprobar('mensaje desconocido → error «datos»', r[0]?.tipo === 'error' && r[0].codigo === 'datos'));
    r = await enviar({ tipo: 'iniciar', v: 2, id: 8 });
    casos.push(comprobar('versión de mensajes distinta de 1 → error «datos»', r[0]?.tipo === 'error' && r[0].codigo === 'datos'));
  } finally {
    if (selfAntes === undefined) delete globalThis.self; else globalThis.self = selfAntes;
    globalThis.fetch = fetchAntes;
  }
  return casos;
}

// ---- E1: escala NSR-10 y calidad baja ------------------------------------------------------------------------------
async function e1() {
  const am = amenaza(), est = leerJSON(FIX + 'estructura_min.json'), casos = [];
  const m = crearMotor();
  const listo = await m.iniciar({ estructura: est, amenaza: am });
  const params = escenario(am, 'nido_2015');
  const r = await m.analizar(params, { duracion_s: 8, escala: 'nsr10' });
  const v = validarResultado(r, est, { tipado: true });
  casos.push(caso('escala nsr10: Resultados válidos', v.errores.length, 0, v.errores[0] ?? `factor ${r.factor_escala.toFixed(3)} en ${r.iteraciones_escala} vueltas`));
  // la media del espectro de la media geométrica (ξ = 5 %) en 0,8·T1 a 1,2·T1 (x e y) iguala la del espectro de diseño
  const mov = await cargarMovimiento();
  const { registro: reg, factor } = m.ultimoAnalisis;
  const per = [];
  for (const T1 of [listo.modos.T1x, listo.modos.T1y]) for (let i = 0; i <= 10; i++) per.push(T1 * (0.8 + 0.04 * i));
  const Tp = Float64Array.from(per);
  const sx = mov.espectroRespuesta(reg.ax.map((x) => x * factor), reg.dt, Tp).Sa_g, sy = mov.espectroRespuesta(reg.ay.map((x) => x * factor), reg.dt, Tp).Sa_g;
  const obj = mov.espectroNSR10(Tp, est.diseno);
  let mg = 0, mo = 0;
  for (let i = 0; i < Tp.length; i++) { mg += Math.sqrt(sx[i] * sy[i]) / Tp.length; mo += obj[i] / Tp.length; }
  casos.push(caso(`media de Sa (media geométrica) ${mg.toFixed(4)} g frente a la del diseño ${mo.toFixed(4)} g`, errorRelativo(mg, mo), 1e-9));
  casos.push(comprobar('ag de Resultados = registro × factor', Math.abs(r.ag[2 * 10] - Math.fround(reg.ax[40] * factor)) <= 1e-6 * Math.abs(reg.ax[40] * factor) + 1e-9));
  // calidad baja: Δt = 0,01 s con el registro filtrado a 20 Hz y diezmado
  const rb = await m.analizar(params, { duracion_s: 8, escala: 4, calidad: 'baja' });
  const vb = validarResultado(rb, est, { tipado: true });
  casos.push(caso('calidad baja: dt_s = 0,01 y Resultados válidos', vb.errores.length + (rb.opciones.dt_s === 0.01 ? 0 : 1), 0, vb.errores[0] ?? `${rb.calidad_numerica.pasos} pasos`));
  const rn = await m.analizar(params, { duracion_s: 8, escala: 4 });
  const dmax = (x) => Math.max(...x.envolventes.deriva_vector_max);
  casos.push(caso('calidad baja frente a normal: deriva vectorial máxima', errorRelativo(dmax(rb), dmax(rn)), 0.05,
    `${dmax(rb).toExponential(3)} y ${dmax(rn).toExponential(3)} (T20 lo prueba con nido_2015 y cimitarra)`));
  return casos;
}

// ---- R1: tiempos (7.7, escritorio) y memoria -------------------------------------------------------------------------
async function r1() {
  const am = amenaza(), est = torreSintetica();
  const params = escenario(am, 'cimitarra');
  const tI = [], tM = [], tA = [];
  let res = null, hist = null, listo = null;
  for (let k = 0; k < 2; k++) {
    const m = crearMotor();
    let t0 = ahora(); listo = await m.iniciar({ estructura: est, amenaza: am }); tI.push(ahora() - t0);
    t0 = ahora(); await m.movimiento(params); tM.push(ahora() - t0);
    t0 = ahora(); res = await m.analizar(params, { duracion_s: 40, equipos: equiposSinteticos() }); tA.push(ahora() - t0);
    hist = m.historia;
  }
  const bytes = (x) => (ArrayBuffer.isView(x) ? x.byteLength : x && typeof x === 'object' ? Object.values(x).reduce((s, v) => s + bytes(v), 0) : 0);
  const mb = (bytes(res) + bytes(hist)) / 1e6;
  const n = `${listo.resumen.elementos} elementos, ${listo.resumen.nodos} nodos, ${listo.resumen.gdl_condensados} gdl condensados`;
  return [
    caso(`iniciar (armar, gravedad, 12 modos, amortiguamiento): ${Math.min(...tI).toFixed(0)} ms`, Math.min(...tI), 300, n),
    caso(`movimiento (síntesis, 2 × 60 períodos, Fourier, GMPE): ${Math.min(...tM).toFixed(0)} ms`, Math.min(...tM), 400),
    caso(`analizar 40 s con Δt = 0,005 s (8000 pasos, cimitarra): ${Math.min(...tA).toFixed(0)} ms`, Math.min(...tA), 2500,
      `${res.thp.elementos.length} elementos con fluencia; ${res.calidad_numerica.iteraciones_promedio.toFixed(2)} iteraciones por paso; error de energía ${res.calidad_numerica.error_energia_max.toExponential(1)}`),
    caso(`resultados + historia interna: ${mb.toFixed(1)} MB`, mb, 80),
  ];
}

export const pruebas = [
  { id: 'T17', nombre: 'Determinismo: misma semilla y opciones → resultados idénticos', fn: t17 },
  { id: 'W1', nombre: 'El trabajador responde los mensajes del 7.5', fn: w1 },
  { id: 'E1', nombre: 'Escala nivel de diseño NSR-10 y calidad baja', fn: e1 },
  { id: 'R1', nombre: 'Tiempos del 7.7 (escritorio) con un modelo del tamaño de la torre', fn: r1 },
];
