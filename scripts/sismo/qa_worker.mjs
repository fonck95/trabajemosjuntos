// QA del motor sísmico en Chromium sin pantalla (contrato de la torre, 7.5, 7.7 y 13.1; data/sismo/ESQUEMA.md).
// Usa scripts/qa/comun.mjs (equipo D) sin modificarlo.
//
//   node scripts/sismo/qa_worker.mjs [--vendor <carpeta>] [--salida <carpeta>] [--sin-vista] [--rapido]
//
// Qué prueba:
//  1. Protocolo (7.5) con el trabajador real (web/js/sismo/trabajador.js, Worker de módulo) y la estructura real de la
//     torre (data/sismo/torre_hospital_estructura.json), sirviendo la raíz del repositorio en «/» y bajo la subruta
//     «/trabajemosjuntos/» (como GitHub Pages): «cargado», «listo», «movimiento» (Float32Array transferidos),
//     «progreso», «resultado» (arreglos tipados del 7.6) y «serie_elemento» después del resultado. La página de prueba
//     no es un archivo del repositorio: Playwright la entrega en una URL de la misma subruta.
//  2. Cancelar a la mitad de un análisis: terminate() del trabajador, aviso «cancelado» en ≤ 300 ms, y un trabajador
//     nuevo con «iniciar» que vuelve a calcular.
//  3. Respaldo sin Worker: motor.js en el hilo principal por tramos de ≈ 12 ms (cediendo con un MessageChannel) da los
//     mismos Resultados, bit a bit (SHA-256 de todos los arreglos y campos, sin duracion_calculo_ms ni id).
//  4. Tiempos del 7.7. Escritorio: el trabajador. Teléfono (proxy: CPU ×4 por CDP): Chromium solo frena las páginas
//     («Emulation.setCPUThrottlingRate: Operation is only supported for pages, not workers», medido), así que la
//     misma cuenta de motor.js corre en el hilo principal de la página frenada ×4 (de corrido, como en el
//     trabajador); se informa además el factor de freno medido con el mismo análisis a ×1. Memoria del trabajador:
//     montón de V8 y almacenamiento de los ArrayBuffer (Runtime.getHeapUsage del trabajador por CDP, después de
//     recoger la basura) más los Resultados transferidos.
//  5. Con --vendor (three y GSAP locales, scripts/qa/LEEME.md): la vista real (atlas.html?qa=1#torre, modo sismo) bajo
//     /trabajemosjuntos/: usa el trabajador, el botón «Cancelar» deja «Cálculo cancelado.» en ≤ 300 ms y vuelve a
//     calcular; sin Worker usa el respaldo y llega a los mismos Resultados. Si web/data todavía no trae
//     sismo_torre_estructura.json (lo exporta build_data.py), la prueba le sirve data/sismo/torre_hospital_estructura.json.
//
// Sale con código 1 si algo falla. El informe (JSON) queda en --salida (por omisión, una carpeta temporal del sistema).
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { opciones, servidor, navegador, abrir, esperar, informe, guardarJSON, RAIZ_REPO } from '../qa/comun.mjs';

const op = opciones(process.argv.slice(2), { raiz: '.', salida: join(tmpdir(), 'atlas_qa_worker') });
const RAPIDO = !!op.rapido;
const SUBRUTA = '/trabajemosjuntos/';
// 7.7: escritorio y teléfono (proxy CPU ×4)
const META = {
  iniciar: { escritorio: 300, telefono: 1200 },
  movimiento: { escritorio: 400, telefono: 1500 },
  analizar: { escritorio: 2500, telefono: 8000 },
  memoria_MB: 80,
  cancelar_ms: 300,
};
const ESC = (am, id) => {
  const e = am.escenarios.find((x) => x.id === id);
  return { Mw: e.Mw, profundidad_km: e.profundidad_km, distancia_epicentral_km: e.distancia_epicentral_km, vs30_m_s: am.controles.vs30_m_s.defecto, semilla: am.controles.semilla.defecto };
};
const amenaza = JSON.parse(readFileSync(join(RAIZ_REPO, 'data/sismo/amenaza.json'), 'utf8'));
const P_CIMITARRA = ESC(amenaza, 'cimitarra');
const P_NIDO = ESC(amenaza, 'nido_2015');
const DUR = RAPIDO ? 10 : 40;            // s de análisis (7.7: 40 s)

// ---------------------------------------------------------------------------------------------------------------
// Página de prueba (la entrega Playwright en <base>__qa_worker.html; las rutas son relativas a la raíz servida)
// ---------------------------------------------------------------------------------------------------------------
const PAGINA = `<!doctype html><html lang="es"><meta charset="utf-8"><title>QA del trabajador sísmico</title>
<script type="module">
const U = (r) => new URL(r, document.baseURI).href;
const RUTAS = { trabajador: U('web/js/sismo/trabajador.js'), motor: U('web/js/sismo/motor.js'),
  estructura: U('data/sismo/torre_hospital_estructura.json'), amenaza: U('data/sismo/amenaza.json') };
const msgIniciar = (id) => ({ tipo: 'iniciar', v: 1, id, url_estructura: RUTAS.estructura, url_amenaza: RUTAS.amenaza, opciones: {} });
const ceder = () => new Promise((ok) => { const c = new MessageChannel(); c.port1.onmessage = () => { c.port1.close(); ok(); }; c.port2.postMessage(0); });

// huella de unos Resultados: SHA-256 de los bytes de todos los arreglos tipados y del JSON del resto (sin tiempos ni id)
async function huella(R) {
  const partes = [], enc = new TextEncoder();
  const rec = (x, ruta) => {
    if (ArrayBuffer.isView(x)) { partes.push(enc.encode(ruta + ':' + x.constructor.name + ':')); partes.push(new Uint8Array(x.buffer, x.byteOffset, x.byteLength)); return; }
    if (x && typeof x === 'object') { for (const k of Object.keys(x).sort()) if (!(ruta === '' && (k === 'duracion_calculo_ms' || k === 'id'))) rec(x[k], ruta + '/' + k); return; }
    partes.push(enc.encode(ruta + '=' + JSON.stringify(x) + ';'));
  };
  rec(R, '');
  const n = partes.reduce((s, p) => s + p.length, 0), todo = new Uint8Array(n);
  let o = 0; for (const p of partes) { todo.set(p, o); o += p.length; }
  const h = new Uint8Array(await crypto.subtle.digest('SHA-256', todo));
  return Array.from(h, (b) => b.toString(16).padStart(2, '0')).join('');
}
function bytesTipados(x, vistos = new Set()) {
  if (ArrayBuffer.isView(x)) { if (vistos.has(x.buffer)) return 0; vistos.add(x.buffer); return x.byteLength; }
  if (!x || typeof x !== 'object') return 0;
  let s = 0; for (const v of Object.values(x)) s += bytesTipados(v, vistos); return s;
}

// cliente mínimo del trabajador
function abrirTrabajador() {
  return new Promise((ok, mal) => {
    const t0 = performance.now();
    let w;
    try { w = new Worker(RUTAS.trabajador, { type: 'module' }); } catch (e) { mal(e); return; }
    const pend = new Map();
    const t = setTimeout(() => mal(new Error('sin «cargado» en 3 s')), 3000);
    w.addEventListener('error', (e) => { e.preventDefault(); mal(new Error('error del trabajador: ' + (e.message || '?'))); });
    w.addEventListener('message', (ev) => {
      const m = ev.data || {};
      if (m.tipo === 'cargado') { clearTimeout(t); ok(c); c.t_cargado = performance.now() - t0; return; }
      const p = pend.get(m.id); if (!p) return;
      if (m.tipo === 'progreso') { p.progreso?.(m); return; }
      pend.delete(m.id); p.ok(m);
    });
    const c = {
      w, t_cargado: null,
      pedir(msg, progreso) { return new Promise((ok2) => { pend.set(msg.id, { ok: ok2, progreso }); w.postMessage(msg); }); },
      matar() { w.terminate(); for (const p of pend.values()) p.ok({ tipo: 'cancelado' }); pend.clear(); },
    };
  });
}

window.qa = {
  async protocolo({ params, opciones, serie }) {
    const r = { errores: [] };
    const c = await abrirTrabajador();
    r.t_cargado_ms = c.t_cargado;
    let t0 = performance.now();
    const listo = await c.pedir(msgIniciar('i1'));
    r.iniciar_con_descarga_ms = performance.now() - t0;
    if (listo.tipo !== 'listo') { r.errores.push('iniciar: ' + JSON.stringify(listo).slice(0, 300)); c.matar(); return r; }
    t0 = performance.now();
    const listo2 = await c.pedir(msgIniciar('i2'));       // mismas URL: el motor no vuelve a descargar
    r.iniciar_ms = performance.now() - t0;
    r.listo = { elementos: listo2.elementos.length, nodos: listo2.nodos.length, T1: listo2.modos.periodos_s[0], a0: listo2.amortiguamiento.a0, a1: listo2.amortiguamiento.a1 };
    t0 = performance.now();
    const mov = await c.pedir({ tipo: 'movimiento', id: 'm1', params });
    r.movimiento_ms = performance.now() - t0;
    if (mov.tipo !== 'movimiento') r.errores.push('movimiento: ' + JSON.stringify(mov).slice(0, 300));
    else {
      r.movimiento = { n: mov.registro.n, dt: mov.registro.dt, ax: mov.registro.ax.constructor.name, pga_x_g: mov.registro.intensidades.x.pga_g, espectro: mov.espectro.Sa_x.constructor.name, gmpe: mov.gmpe.length };
      if (!(mov.registro.ax instanceof Float32Array) || !(mov.espectro.Sa_x instanceof Float32Array)) r.errores.push('movimiento sin Float32Array');
    }
    let nprog = 0, tUlt = null, minIntervalo = Infinity;
    t0 = performance.now();
    const res = await c.pedir({ tipo: 'analizar', id: 'a1', params, opciones }, () => { const t = performance.now(); if (tUlt !== null) minIntervalo = Math.min(minIntervalo, t - tUlt); tUlt = t; nprog++; });
    r.analizar_ms = performance.now() - t0;
    if (res.tipo !== 'resultado') { r.errores.push('analizar: ' + JSON.stringify(res).slice(0, 400)); c.matar(); return r; }
    const R = res.resultados;
    r.progreso = { mensajes: nprog, intervalo_min_ms: Number.isFinite(minIntervalo) ? minIntervalo : null };
    const tipos = { t: Float32Array, u: Float32Array, giros: Float32Array, dc: Uint8Array, rotulas: Uint8Array, derivas_vector: Float32Array, cortante_basal: Float32Array, energia: Float32Array };
    for (const [k, T] of Object.entries(tipos)) if (!(R[k] instanceof T)) r.errores.push('resultado.' + k + ' no es ' + T.name);
    if (!(R.thp?.valores instanceof Int16Array)) r.errores.push('thp.valores no es Int16Array');
    r.resultado = { nt: R.t.length, nE: listo2.elementos.length, pasos: R.calidad_numerica.pasos, no_convergidos: R.calidad_numerica.no_convergidos,
      fluyen: R.thp.elementos.length, deriva_vector_max: Math.max(...R.envolventes.deriva_vector_max), error_energia: R.calidad_numerica.error_energia_max,
      bytes: bytesTipados(R) };
    r.huella = await huella(R);
    if (serie) {
      const s = await c.pedir({ tipo: 'serie_elemento', id: 's1', elemento: serie });
      if (s.tipo !== 'serie_elemento') r.errores.push('serie_elemento: ' + JSON.stringify(s).slice(0, 300));
      else {
        r.serie = { elemento: s.elemento, n: s.Mi.length, tipo: s.Mi.constructor.name };
        if (s.Mi.length !== R.t.length || !(s.Mi instanceof Float32Array)) r.errores.push('serie_elemento: largo o tipo distintos de Resultados.t');
        const ie = listo2.elementos.findIndex((e) => e.id === serie), nE = listo2.elementos.length;
        let dif = 0; for (let i = 0; i < R.t.length; i++) dif = Math.max(dif, Math.abs(Math.round(100 * s.dc[i]) - Math.min(255, R.dc[i * nE + ie])));
        r.serie.dif_dc_x100 = dif;
        if (dif > 1) r.errores.push('serie_elemento: dc distinto del de Resultados');
      }
    }
    window.__ultimoTrabajador = c;                         // para medir su memoria por CDP
    return r;
  },
  cerrarTrabajador() { window.__ultimoTrabajador?.matar(); window.__ultimoTrabajador = null; },

  async cancelar({ params, opciones, fraccion = 0.4 }) {
    const r = { errores: [] };
    const c = await abrirTrabajador();
    await c.pedir(msgIniciar('i1'));
    await c.pedir({ tipo: 'movimiento', id: 'm1', params });
    let estado = 'calculando', aMitad;
    const mitad = new Promise((ok) => { aMitad = ok; });
    const fin = c.pedir({ tipo: 'analizar', id: 'a1', params, opciones }, (m) => { if (m.fraccion >= fraccion) aMitad(m.fraccion); });
    r.fraccion_al_cancelar = await mitad;
    const t0 = performance.now();
    c.matar();                                            // la vista cancela así (7.5): terminate() y aviso
    const m = await fin;
    estado = m.tipo === 'cancelado' ? 'cancelado' : 'otro: ' + m.tipo;
    r.cancelar_ms = performance.now() - t0;
    r.estado = estado;
    // un trabajador nuevo con «iniciar» vuelve a calcular (menos duración, solo para comprobar)
    const t1 = performance.now();
    const c2 = await abrirTrabajador();
    const l2 = await c2.pedir(msgIniciar('i2'));
    r.reabrir_e_iniciar_ms = performance.now() - t1;
    const res = await c2.pedir({ tipo: 'analizar', id: 'a2', params, opciones: { ...opciones, duracion_s: 2 } });
    r.recalcula = res.tipo === 'resultado' && l2.tipo === 'listo';
    c2.matar();
    if (estado !== 'cancelado') r.errores.push('el análisis no quedó cancelado');
    if (!r.recalcula) r.errores.push('después de cancelar no volvió a calcular');
    return r;
  },

  // motor.js en el hilo principal. tramos: cede por tiempo (respaldo de la vista); si no, de corrido (proxy del
  // trabajador para medir con la CPU frenada, que CDP solo aplica a páginas)
  async hilo({ params, opciones, tramos }) {
    const r = {};
    const { crearMotor } = await import(RUTAS.motor);
    const m = crearMotor();
    await m.iniciar(msgIniciar('h0'));                    // descarga (no cuenta en el 7.7)
    let t0 = performance.now();
    await m.iniciar(msgIniciar('h1'));
    r.iniciar_ms = performance.now() - t0;
    t0 = performance.now();
    await m.movimiento(params);
    r.movimiento_ms = performance.now() - t0;
    let maxTramo = 0, ultimo = performance.now(), cortes = 0;
    const cederMedido = async () => { const t = performance.now(); maxTramo = Math.max(maxTramo, t - ultimo); cortes++; await ceder(); ultimo = performance.now(); };
    t0 = performance.now();
    const R = await m.analizar(params, tramos ? { ...opciones, presupuesto_ms: 12, ceder: cederMedido } : opciones, () => {});
    r.analizar_ms = performance.now() - t0;
    if (tramos) { const t = performance.now(); maxTramo = Math.max(maxTramo, t - ultimo); r.tramo_max_ms = maxTramo; r.cortes = cortes; }
    r.huella = await huella(R);
    r.bytes = bytesTipados(R);
    const h = m.historia;
    r.bytes_historia = h ? ['Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc', 't'].reduce((s, k) => s + (h[k]?.byteLength || 0), 0) + (h.u_completa?.byteLength || 0) : 0;
    r.nt = R.t.length;
    return r;
  },
};
window.__listo = true;
</script></html>`;

// ---------------------------------------------------------------------------------------------------------------
// Utilidades de Node
// ---------------------------------------------------------------------------------------------------------------
const informeFinal = { version: 1, generado_por: 'scripts/sismo/qa_worker.mjs', contrato: '7.5, 7.7 y 13.1', chequeos: [] };
let fallas = 0;
function chequeo(nombre, ok, detalle = '', extra = {}) {
  informeFinal.chequeos.push({ chequeo: nombre, ok: !!ok, detalle, ...extra });
  if (!ok) fallas++;
  console.log(`${ok ? '✓' : '✗'} ${nombre}${detalle ? ` · ${detalle}` : ''}`);
}
const ms = (x) => `${Math.round(x)} ms`;

async function paginaDePrueba(nav, srv) {
  const { page, contexto, registro, cerrar } = await abrir(nav, op, {});
  const url = `${srv.url}__qa_worker.html`;
  await contexto.route(url, (r) => r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: PAGINA }));
  await page.goto(url, { waitUntil: 'load' });
  if (!(await esperar(page, () => window.__listo === true, { ms: 10000 }))) throw new Error('la página de prueba no cargó');
  return { page, contexto, registro, cerrar, url };
}

/** CDP: sesión de la página y acceso a los trabajadores (modo no aplanado: Target.sendMessageToTarget). */
async function cdpDe(contexto, page) {
  const s = await contexto.newCDPSession(page);
  const trabajadores = [];
  const espera = new Map();
  let nid = 1000;
  s.on('Target.attachedToTarget', (e) => { if (e.targetInfo.type === 'worker') trabajadores.push(e.sessionId); });
  s.on('Target.detachedFromTarget', (e) => { const i = trabajadores.indexOf(e.sessionId); if (i >= 0) trabajadores.splice(i, 1); });
  s.on('Target.receivedMessageFromTarget', (e) => { const m = JSON.parse(e.message); if (espera.has(m.id)) { espera.get(m.id)(m); espera.delete(m.id); } });
  await s.send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: false });
  const aTrabajador = (sessionId, method, params = {}) => new Promise((ok) => {
    const id = ++nid; espera.set(id, ok);
    s.send('Target.sendMessageToTarget', { sessionId, message: JSON.stringify({ id, method, params }) }).catch((err) => { espera.delete(id); ok({ error: { message: err.message } }); });
  });
  return { s, trabajadores, aTrabajador };
}

// ---------------------------------------------------------------------------------------------------------------
// 1-4: protocolo, cancelar, respaldo y tiempos, en la raíz y en la subruta
// ---------------------------------------------------------------------------------------------------------------
async function pruebasDeProtocolo(nav) {
  const opAnal = { dt_s: 0.005, duracion_s: DUR };
  for (const base of ['/', SUBRUTA]) {
    const srv = await servidor({ ...op, base });
    const { page, contexto, registro, cerrar } = await paginaDePrueba(nav, srv);
    const etiqueta = base === '/' ? 'raíz' : `subruta ${base}`;
    const cdp = await cdpDe(contexto, page);
    console.log(`\n— Trabajador de módulo en la ${etiqueta} (${srv.url})`);
    // 1. protocolo completo con la torre real
    const p = await page.evaluate((a) => window.qa.protocolo(a), { params: P_CIMITARRA, opciones: opAnal, serie: 'C-A1-1@X' });
    chequeo(`${etiqueta}: cargado, listo, movimiento, progreso, resultado tipado y serie_elemento después del resultado`, p.errores.length === 0,
      p.errores.length ? p.errores.join(' | ') : `${p.listo.elementos} elementos, T1 = ${p.listo.T1.toFixed(4)} s; ${p.resultado.nt} salidas, ${p.resultado.fluyen} elementos con fluencia, ` +
        `${p.progreso.mensajes} mensajes de progreso; serie de ${p.serie?.elemento} con ${p.serie?.n} instantes`);
    chequeo(`${etiqueta}: 0 pasos sin converger y energía cerrada`, p.resultado && p.resultado.no_convergidos === 0 && p.resultado.error_energia < 0.01,
      p.resultado ? `error de energía ${p.resultado.error_energia.toExponential(2)}` : '');
    chequeo(`${etiqueta}: «progreso» cada ≥ 250 ms`, p.progreso && (p.progreso.intervalo_min_ms === null || p.progreso.intervalo_min_ms >= 240),
      p.progreso ? `intervalo mínimo ${p.progreso.intervalo_min_ms === null ? '—' : ms(p.progreso.intervalo_min_ms)}` : '');
    // memoria del trabajador (después de recoger la basura: queda la historia interna) + Resultados transferidos
    let mem = null;
    const sid = cdp.trabajadores.at(-1);
    if (sid) {
      await cdp.aTrabajador(sid, 'HeapProfiler.collectGarbage');
      const h = await cdp.aTrabajador(sid, 'Runtime.getHeapUsage');
      if (h.result) mem = { monton_MB: h.result.usedSize / 1e6, arraybuffers_MB: (h.result.backingStorageSize ?? 0) / 1e6, resultados_MB: p.resultado.bytes / 1e6 };
      // ¿CDP puede frenar la CPU de un trabajador? (se informa: Chromium lo rechaza)
      const fr = await cdp.aTrabajador(sid, 'Emulation.setCPUThrottlingRate', { rate: 4 });
      informeFinal.freno_en_trabajador = fr.error ? fr.error.message : 'aceptado';
      if (!fr.error) await cdp.aTrabajador(sid, 'Emulation.setCPUThrottlingRate', { rate: 1 });
    }
    await page.evaluate(() => window.qa.cerrarTrabajador());
    informeFinal[base === '/' ? 'raiz' : 'subruta'] = { protocolo: p, memoria: mem };
    if (base === '/') {
      const tot = mem ? mem.monton_MB + mem.arraybuffers_MB + mem.resultados_MB : null;
      chequeo('7.7 memoria pico del trabajador (resultados + historia interna) ≤ 80 MB', tot !== null && tot <= META.memoria_MB,
        mem ? `${tot.toFixed(1)} MB = montón ${mem.monton_MB.toFixed(1)} + ArrayBuffer ${mem.arraybuffers_MB.toFixed(1)} (historia) + resultados ${mem.resultados_MB.toFixed(1)}` : 'sin acceso al trabajador por CDP');
      // tiempos de escritorio (el mejor de dos corridas)
      const p2 = await page.evaluate((a) => window.qa.protocolo(a), { params: P_CIMITARRA, opciones: opAnal, serie: null });
      await page.evaluate(() => window.qa.cerrarTrabajador());
      const mejor = (k) => Math.min(p[k], p2[k]);
      informeFinal.tiempos_escritorio = { iniciar_ms: mejor('iniciar_ms'), iniciar_con_descarga_ms: mejor('iniciar_con_descarga_ms'), movimiento_ms: mejor('movimiento_ms'), analizar_ms: mejor('analizar_ms'), t_cargado_ms: mejor('t_cargado_ms') };
      const te = informeFinal.tiempos_escritorio;
      chequeo(`7.7 escritorio: iniciar ≤ ${META.iniciar.escritorio} ms`, te.iniciar_ms <= META.iniciar.escritorio, `${ms(te.iniciar_ms)} (con la descarga y lectura de la estructura: ${ms(te.iniciar_con_descarga_ms)})`);
      chequeo(`7.7 escritorio: movimiento ≤ ${META.movimiento.escritorio} ms`, te.movimiento_ms <= META.movimiento.escritorio, ms(te.movimiento_ms));
      chequeo(`7.7 escritorio: analizar ${DUR} s con Δt = 0,005 s ≤ ${META.analizar.escritorio} ms`, te.analizar_ms <= META.analizar.escritorio, ms(te.analizar_ms));
      chequeo('mismos Resultados en dos corridas del trabajador (determinismo)', p.huella === p2.huella, p.huella.slice(0, 16));
      // 2. cancelar a la mitad
      const c = await page.evaluate((a) => window.qa.cancelar(a), { params: P_CIMITARRA, opciones: opAnal, fraccion: 0.4 });
      informeFinal.cancelar = c;
      chequeo(`cancelar a la mitad (terminate y aviso) ≤ ${META.cancelar_ms} ms`, c.errores.length === 0 && c.cancelar_ms <= META.cancelar_ms,
        `${ms(c.cancelar_ms)} al ${Math.round(100 * c.fraccion_al_cancelar)} %; trabajador nuevo con iniciar en ${ms(c.reabrir_e_iniciar_ms)}, vuelve a calcular: ${c.recalcula ? 'sí' : 'no'}${c.errores.length ? ' · ' + c.errores.join(' | ') : ''}`);
      // 3. respaldo por tramos: mismos Resultados
      const h = await page.evaluate((a) => window.qa.hilo(a), { params: P_CIMITARRA, opciones: opAnal, tramos: true });
      informeFinal.respaldo = h;
      chequeo('respaldo sin Worker (motor.js por tramos de 12 ms): mismos Resultados, bit a bit', h.huella === p.huella,
        `${h.cortes} cesiones, ${ms(h.analizar_ms)}`);
      // 7.5: no más de ≈ 12 ms seguidos sin dibujar; un paso de Newmark no se parte (el primero, frío, tarda más)
      chequeo('respaldo: tramo más largo sin ceder ≤ 25 ms (presupuesto de 12 ms; un paso no se parte)', h.tramo_max_ms <= 25, `${h.tramo_max_ms.toFixed(1)} ms`);
      // 4. teléfono: CPU ×4 por CDP (solo en páginas): motor.js de corrido en el hilo principal
      const x1 = await page.evaluate((a) => window.qa.hilo(a), { params: P_CIMITARRA, opciones: { ...opAnal, calidad: 'baja' }, tramos: false });
      await cdp.s.send('Emulation.setCPUThrottlingRate', { rate: 4 });
      const x4 = await page.evaluate((a) => window.qa.hilo(a), { params: P_CIMITARRA, opciones: { ...opAnal, calidad: 'baja' }, tramos: false });
      const x4n = await page.evaluate((a) => window.qa.hilo(a), { params: P_CIMITARRA, opciones: opAnal, tramos: false });
      await cdp.s.send('Emulation.setCPUThrottlingRate', { rate: 1 });
      const frenoTrabajador = informeFinal.freno_en_trabajador ?? null;
      informeFinal.tiempos_telefono = {
        proxy: 'motor.js de corrido en el hilo principal de la página con Emulation.setCPUThrottlingRate = 4 (CDP no frena trabajadores)',
        respuesta_de_cdp_al_frenar_un_trabajador: frenoTrabajador,
        factor_de_freno_medido: x4.analizar_ms / x1.analizar_ms,
        iniciar_ms: x4.iniciar_ms, movimiento_ms: x4.movimiento_ms, analizar_calidad_baja_ms: x4.analizar_ms, analizar_normal_ms: x4n.analizar_ms,
        sin_freno: { iniciar_ms: x1.iniciar_ms, movimiento_ms: x1.movimiento_ms, analizar_calidad_baja_ms: x1.analizar_ms },
      };
      const tt = informeFinal.tiempos_telefono;
      // el freno de CDP no es exacto (se mide ×3 a ×4,2): si quedó por debajo de 4, los tiempos se llevan a ×4 (del lado seguro)
      const aX4 = Math.max(1, 4 / tt.factor_de_freno_medido);
      tt.correccion_a_x4 = aX4;
      for (const k of ['iniciar_ms', 'movimiento_ms', 'analizar_calidad_baja_ms', 'analizar_normal_ms']) tt[`${k.replace('_ms', '')}_x4_ms`] = tt[k] * aX4;
      console.log(`  freno de CPU medido con el mismo análisis: ×${tt.factor_de_freno_medido.toFixed(2)}; tiempos llevados a ×4 con ×${aX4.toFixed(2)} (CDP sobre el trabajador: «${frenoTrabajador}»)`);
      chequeo(`7.7 teléfono (CPU ×4): iniciar ≤ ${META.iniciar.telefono} ms`, tt.iniciar_x4_ms <= META.iniciar.telefono, ms(tt.iniciar_x4_ms));
      chequeo(`7.7 teléfono (CPU ×4): movimiento ≤ ${META.movimiento.telefono} ms`, tt.movimiento_x4_ms <= META.movimiento.telefono, ms(tt.movimiento_x4_ms));
      chequeo(`7.7 teléfono (CPU ×4): analizar ${DUR} s en calidad baja (Δt = 0,01 s) ≤ ${META.analizar.telefono} ms`, tt.analizar_calidad_baja_x4_ms <= META.analizar.telefono,
        `${ms(tt.analizar_calidad_baja_x4_ms)} (con Δt = 0,005 s: ${ms(tt.analizar_normal_x4_ms)})`);
    } else {
      chequeo(`${etiqueta}: mismos Resultados que en la raíz`, p.huella === informeFinal.raiz.protocolo.huella);
    }
    chequeo(`${etiqueta}: consola sin errores ni peticiones fallidas`, informe(registro, `página de prueba (${etiqueta})`));
    await cerrar();
    await srv.cerrar();
  }
}

// ---------------------------------------------------------------------------------------------------------------
// 5: la vista real (D) con el trabajador, cancelar y el respaldo sin Worker
// ---------------------------------------------------------------------------------------------------------------
async function pruebasDeVista(nav) {
  const opWeb = { ...op, raiz: 'web', raizAbs: join(RAIZ_REPO, 'web'), base: SUBRUTA };
  const srv = await servidor(opWeb);
  const enWeb = existsSync(join(RAIZ_REPO, 'web/data/sismo_torre_estructura.json'));
  const estructura = readFileSync(join(RAIZ_REPO, 'data/sismo/torre_hospital_estructura.json'));
  if (!enWeb) console.log('  (web/data no trae sismo_torre_estructura.json todavía: se sirve data/sismo/torre_hospital_estructura.json)');
  const esperados = [/\/js\/scenes\/torre\/[a-z_]+\.js$/];
  const huellas = {};
  for (const sinWorker of [false, true]) {
    const etiqueta = sinWorker ? 'vista sin Worker (respaldo)' : 'vista con el trabajador';
    const { page, contexto, registro, cerrar } = await abrir(nav, opWeb, { sinWorker, esperados });
    if (!enWeb) await contexto.route(/\/data\/sismo_torre_estructura\.json$/, (r) => r.fulfill({ status: 200, contentType: 'application/json', body: estructura }));
    await page.addInitScript(() => {
      window.__huellaR = async (R) => {
        const partes = [], enc = new TextEncoder();
        const rec = (x, ruta) => {
          if (ArrayBuffer.isView(x)) { partes.push(enc.encode(ruta + ':' + x.constructor.name + ':')); partes.push(new Uint8Array(x.buffer, x.byteOffset, x.byteLength)); return; }
          if (x && typeof x === 'object') { for (const k of Object.keys(x).sort()) if (!(ruta === '' && (k === 'duracion_calculo_ms' || k === 'id'))) rec(x[k], ruta + '/' + k); return; }
          partes.push(enc.encode(ruta + '=' + JSON.stringify(x) + ';'));
        };
        rec(R, '');
        const n = partes.reduce((s, p) => s + p.length, 0), todo = new Uint8Array(n);
        let o = 0; for (const p of partes) { todo.set(p, o); o += p.length; }
        return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', todo)), (b) => b.toString(16).padStart(2, '0')).join('');
      };
    });
    await page.goto(`${srv.url}atlas.html?qa=1#torre`, { waitUntil: 'load' });
    const hay = await esperar(page, () => window.__torreQA?.listo?.(), { ms: 60000 });
    if (!hay) { chequeo(`${etiqueta}: la vista de la torre carga`, false, 'sin __torreQA.listo()'); await cerrar(); continue; }
    // entrar al modo sismo: calcula nido_2015 por defecto
    await page.evaluate(() => window.__torreQA.modo('sismo'));
    const calc = await esperar(page, () => window.__torreQA.sismo.ultimo() !== null, { ms: 120000 });
    const ult = calc ? await page.evaluate(async () => { const u = window.__torreQA.sismo.ultimo(); return { motor: window.__torreQA.sismo.motor(), escenario: u.escenario, nt: u.nt, nE: u.nE, duracion_ms: u.duracion_ms, huella: await window.__huellaR(u.resultados) }; }) : null;
    const motorEsperado = sinWorker ? 'hilo_principal' : 'trabajador';
    chequeo(`${etiqueta}: calcula nido_2015 con el motor «${motorEsperado}»`, !!ult && ult.motor === motorEsperado,
      ult ? `${ult.nE} elementos, ${ult.nt} salidas en ${ms(ult.duracion_ms)} (motor ${ult.motor})` : 'no terminó en 120 s');
    if (ult) huellas[motorEsperado] = ult.huella;
    if (!sinWorker && ult) {
      // cancelar a la mitad con el botón de la vista: «Cálculo cancelado.» en ≤ 300 ms
      const c = await page.evaluate(async ({ dur }) => {
        const panel = document.querySelector('[data-slot="torre.panel.sismo"]') || document;
        const estado = () => panel.querySelector('[data-o="estado"]')?.textContent || '';
        window.__calc = window.__torreQA.sismo.calcular({ escenario: 'cimitarra' });
        const t00 = performance.now();
        // la vista dice el avance por cuartos («… estructura: más del 50 %»; antes, en por ciento): se cancela desde el 30 %
        while (!/estructura: (?:más del )?([3-9]\d) %/.test(estado())) { if (performance.now() - t00 > 60000) return { error: 'el cálculo no llegó al 30 %: ' + estado() }; await new Promise((r) => setTimeout(r, 5)); }
        const al = estado();
        const t0 = performance.now();
        panel.querySelector('[data-s="cancelar"]').click();
        while (estado() !== 'Cálculo cancelado.') { if (performance.now() - t0 > 5000) return { error: 'no quedó cancelado: ' + estado() }; await new Promise((r) => requestAnimationFrame(r)); }
        const dt = performance.now() - t0;
        const visible = !panel.querySelector('[data-s="calcular"]').hidden;
        const r = await window.__calc;
        return { cancelar_ms: dt, al, boton_calcular_visible: visible, respuesta: r };
      }, { dur: DUR });
      informeFinal.vista_cancelar = c;
      chequeo(`vista: «Cancelar» a la mitad deja «Cálculo cancelado.» en ≤ ${META.cancelar_ms} ms`, !c.error && c.cancelar_ms <= META.cancelar_ms && c.boton_calcular_visible,
        c.error || `${ms(c.cancelar_ms)} (${c.al})`);
      // vuelve a calcular con un trabajador nuevo
      const r2 = await page.evaluate(async () => { const u = await window.__torreQA.sismo.calcular({ escenario: 'nido_2015' }); return u && !u.cancelado ? { motor: window.__torreQA.sismo.motor(), huella: await window.__huellaR(u.resultados) } : u; });
      chequeo('vista: después de cancelar vuelve a calcular (trabajador nuevo) con los mismos Resultados', r2?.huella === ult.huella && r2?.motor === 'trabajador', r2?.huella ? '' : JSON.stringify(r2));
    }
    chequeo(`${etiqueta}: consola sin errores ni peticiones fallidas`, informe(registro, etiqueta));
    await cerrar();
  }
  if (huellas.trabajador && huellas.hilo_principal) {
    chequeo('vista: el respaldo sin Worker da los mismos Resultados que el trabajador, bit a bit', huellas.trabajador === huellas.hilo_principal, huellas.trabajador.slice(0, 16));
  }
  informeFinal.vista = { huellas, estructura_servida: enWeb ? 'web/data/sismo_torre_estructura.json' : 'data/sismo/torre_hospital_estructura.json (desvío de la prueba)' };
  await srv.cerrar();
}

// ---------------------------------------------------------------------------------------------------------------
const nav = await navegador(op);
try {
  await pruebasDeProtocolo(nav);
  if (op['sin-vista']) console.log('\n— Vista: omitida (--sin-vista)');
  else if (!op.vendor) console.log('\n— Vista: omitida (falta --vendor con three y GSAP; ver scripts/qa/LEEME.md)');
  else { console.log(`\n— Vista real bajo ${SUBRUTA}`); await pruebasDeVista(nav); }
} catch (e) {
  chequeo('la QA terminó sin excepciones', false, e.stack || e.message);
} finally {
  await nav.close();
}
informeFinal.fallas = fallas;
const ruta = await guardarJSON(op, 'qa_worker.json', informeFinal);
console.log(`\n${fallas ? `${fallas} chequeos con fallas` : 'Todo en verde'} · informe: ${ruta}`);
process.exit(fallas ? 1 : 0);
