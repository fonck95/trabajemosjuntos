#!/usr/bin/env node
// QA del modo «Simulador sísmico» de la torre (equipo D; especificación de integración 8 y 13.4) en Chromium sin pantalla.
// Reúne las pruebas de la vista sísmica que se hicieron al construirla y en su revisión (antes solo en la carpeta temporal
// de la sesión), para que cualquiera las pueda repetir.
//
//   PLAYWRIGHT_MODULE=… node scripts/qa/sismo_qa.mjs --vendor <carpeta> [--salida <carpeta>] [--solo simulado,real,respaldo,sin_estructura,revision]
//
// Sirve la raíz del repositorio con scripts/qa/comun.mjs (para que existan los fixtures de scripts/fixtures/torre/) y abre
// web/index.html?qa=1#torre envuelto como lo hace build_site.py:
//   · simulado: trabajador simulado del equipo A (fixtures del Anexo A; «&motor=simulado»), en claro y oscuro, escritorio y
//     teléfono: ganchos, las 6 gráficas, cubierta dibujada = cm + u × escala, presupuesto de dibujo, textos de honestidad y
//     de Richter, tabla de variables, barra de tiempo, leyenda y etiquetas de deriva dentro del recuadro, series de un
//     elemento elegido en la lista, el deslizador con el teclado, un clic que no cambia la ficha de siempre, «Calcular» y
//     «Cancelar», y cambiar de modo a mitad de un cálculo sin dejar nada del simulador en los contenedores;
//   · real: el motor real en el trabajador con la estructura publicada (nido_2015 y local_hip) y la dotación de un piso
//     sobre su losa, dentro del presupuesto;
//   · respaldo: sin Worker, el cubo de prueba («&estructura=min») da el mismo resultado que con el trabajador; con
//     movimiento reducido no hay reproducción automática; «Cancelar» a la mitad en el hilo principal en ≤ 300 ms;
//   · sin_estructura: si el modelo estructural no está publicado (404), la vista lo dice;
//   · revision (correcciones de la revisión de la vista): torre.json tarde no deja pisos en la selección; durante el primer
//     cálculo no hay etiquetas vacías y la cámara girada por la persona no se reencuadra; las regiones vivas no se
//     reescriben con cada flecha ni con cada avance; el foco vuelve a «Calcular»; cambiar la histéresis, calcular y
//     cancelar deja el modelo dibujado; salir a mitad de un cálculo y volver; reproducir con el recuadro fuera de la
//     pantalla; 20 cambios del piso de los equipos sin dejar búferes de WebGL vivos.
// Sale con código 1 si algo falla. Capturas en --salida.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { opciones, servidor, navegador, abrir, esperar, desborde, textosInternos, captura, informe, envolverIndex, RAIZ_REPO } from './comun.mjs';

const op = opciones(process.argv.slice(2), { raiz: '.', salida: join(tmpdir(), 'atlas_qa', 'sismo') });
if (!op.vendor) { console.error('Falta --vendor <carpeta> con three/ y gsap/ (ver scripts/qa/LEEME.md)'); process.exit(2); }
const solo = new Set(String(op.solo || 'simulado,real,respaldo,sin_estructura,revision').split(','));
const srv = await servidor(op), nav = await navegador(op);
const base = `${srv.url}web/index.html`;
let fallas = 0;
const ok = (c, m) => { console.log(`  ${c ? 'ok' : 'FALLA'} ${m}`); if (!c) fallas++; return c; };
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
const ESPERADOS = [];

async function pagina({ tema = 'claro', telefono = false, sinWorker = false, movimientoReducido = false, q = '', retrasoTorre = 0, sinEstructura = false } = {}) {
  const r = await abrir(nav, op, { tema, telefono, sinWorker, movimientoReducido, esperados: sinEstructura ? [/sismo_torre_estructura\.json$/] : ESPERADOS });
  await r.page.route(/\/web\/index\.html(\?.*)?$/, (ruta) => ruta.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: envolverIndex(readFileSync(join(RAIZ_REPO, 'web/index.html'), 'utf8')) }));
  if (sinEstructura) await r.page.route(/\/web\/data\/sismo_torre_estructura\.json$/, (ruta) => ruta.fulfill({ status: 404, contentType: 'text/plain', body: 'no encontrado' }));
  if (retrasoTorre) await r.page.route(/\/web\/data\/torre\.json$/, async (ruta) => { await pausa(retrasoTorre); await ruta.continue(); });
  await r.page.goto(`${base}?qa=1${q}#torre`, { waitUntil: 'load' });
  await esperar(r.page, () => !!window.__torreQA && document.querySelector('#v-torre canvas.gl'), { ms: 30000 });
  return r;
}
const entrarSismo = async (page) => { await page.evaluate(() => window.__torreQA.modo('sismo')); return esperar(page, () => !!window.__torreQA.sismo.ultimo(), { ms: 180000 }); };
const alStage = (page) => page.evaluate(() => { const h = document.querySelector('header.top'), e = document.querySelector('#v-torre .stage'); scrollTo(0, e.getBoundingClientRect().top + scrollY - (getComputedStyle(h).position === 'sticky' ? h.offsetHeight : 0) - 8); });
// la escena del Stage activo, desde la página (el mismo core.js que usa torre.js)
const enEscena = (page, fn, arg) => page.evaluate(`(async () => { const core = await import(new URL('js/core.js', location.href).href); const st = core.engine.active; return (${fn.toString()})(st, ${JSON.stringify(arg ?? null)}); })()`);
const vigilar = (page, sel) => page.evaluate((sel) => { const e = document.querySelector(sel); window.__mut = { n: 0, textos: [] }; window.__obs?.disconnect(); window.__obs = new MutationObserver(() => { window.__mut.n++; window.__mut.textos.push(e.textContent.slice(0, 80)); }); window.__obs.observe(e, { childList: true, characterData: true, subtree: true }); }, sel);
const vigilado = (page) => page.evaluate(() => { window.__obs?.disconnect(); return window.__mut; });

// comprobaciones comunes de una página con un resultado a la vista
async function revisar(page, nombre, { telefono = false } = {}) {
  const info = await page.evaluate(() => {
    const Q = window.__torreQA, u = Q.sismo.ultimo(), R = u.resultados, nt = u.nt;
    let err = 0;
    for (let i = 0; i < nt; i++) { const a = Q.sismo.cubiertaDibujada(i), b = u.cubiertaEsperada(i); err = Math.max(err, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])); }
    const g = document.querySelectorAll('[data-slot="torre.sismo.graficas"] svg.mr-chart');
    const txt = document.querySelector('#v-torre').innerText;
    Q.stats();   // un cuadro con el mapa de sombras pendiente, si lo hay; se mide el siguiente
    return {
      motor: Q.sismo.motor(), nt, N: u.N, nE: u.nE, escala: u.escala, rotulas: u.rotulas, dc_max: u.dc_max, deriva: u.deriva_vector_max, dur: u.duracion_ms,
      err, graficas: g.length, vacias: [...g].filter((s) => !s.querySelector('path')).length, stats: Q.stats(),
      honestidad: txt.includes('Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado)'), richter: txt.includes('la que reemplazó a la escala de Richter'),
      tabla: document.querySelectorAll('.sismo-tabla tbody tr').length, panel: !document.querySelector('[data-slot="torre.panel.sismo"]').hidden,
      tarjeta: !document.querySelector('[data-slot="torre.sismo"]').hidden, exag: document.querySelector('[data-o="exag"]')?.textContent || '', equipos: R.equipos?.length || 0,
    };
  });
  console.log(`    motor ${info.motor} · ${info.nt} pasos · ${info.N} niveles · ${info.nE} elementos · ×${info.escala} · ${info.rotulas} rótulas · D/C máx ${info.dc_max?.toFixed?.(3)} · deriva ${(info.deriva * 100).toFixed(3)} % · ${info.equipos} equipos · ${info.dur} ms · ${info.exag}`);
  ok(info.motor === 'trabajador' || info.motor === 'hilo_principal', `${nombre}: motor() = ${info.motor}`);
  ok(info.graficas >= 6 && !info.vacias, `${nombre}: ${info.graficas} gráficas (vacías ${info.vacias})`);
  ok(info.err < 1e-4, `${nombre}: cubierta dibujada = cm + u × escala en los ${info.nt} pasos (error ${info.err.toExponential(2)} m)`);
  ok(info.stats.llamadas <= 60 && info.stats.triangulos <= 150000, `${nombre}: ${info.stats.llamadas} llamadas (≤ 60) y ${info.stats.triangulos} triángulos (≤ 150.000)`);
  ok(info.honestidad && info.richter, `${nombre}: textos de honestidad y de la escala de Richter`);
  ok(info.panel && info.tarjeta && info.tabla >= 10, `${nombre}: panel y tarjeta a la vista, ${info.tabla} filas en la tabla de variables`);
  const d = await desborde(page);
  ok(d.ok, `${nombre}: sin desborde horizontal${d.ok ? '' : ` (${d.culpables.join(', ')})`}`);
  const internos = await textosInternos(page, '#v-torre');
  ok(!internos.length, `${nombre}: sin textos internos${internos.length ? ` (${internos.join(' | ')})` : ''}`);
  const dentro = await page.evaluate(() => {
    const st = document.querySelector('#v-torre .stage').getBoundingClientRect();
    return ['.sismo-tiempo', '.sismo-ley'].map((s) => { const r = document.querySelector(s).getBoundingClientRect(); return r.left >= st.left - 1 && r.right <= st.right + 1 && r.top >= st.top - 1 && r.bottom <= st.bottom + 1; });
  });
  ok(dentro.every(Boolean), `${nombre}: barra de tiempo y leyenda dentro del recuadro`);
  await alStage(page);
  await pausa(500);
  const fuera = await page.evaluate(() => {
    const st = document.querySelector('#v-torre .stage').getBoundingClientRect();
    return [...document.querySelectorAll('.sismo-lbl > .lbl-node')].filter((e) => e.offsetParent && e.parentElement.style.display !== 'none').map((e) => e.getBoundingClientRect()).filter((r) => r.left < st.left - 1 || r.right > st.right + 1 || r.top < st.top - 1 || r.bottom > st.bottom + 1).length;
  });
  ok(!fuera, `${nombre}: etiquetas de deriva dentro del recuadro (${fuera} fuera)`);
  await captura(page, op, `sismo-${nombre}`);
  if (telefono) { await page.evaluate(() => document.querySelector('[data-slot="torre.panel.sismo"]').scrollIntoView({ block: 'start' })); await pausa(300); await captura(page, op, `sismo-${nombre}-panel`); }
  await page.evaluate(() => document.querySelector('[data-slot="torre.sismo"]').scrollIntoView());
  await pausa(400);
  await captura(page, op, `sismo-${nombre}-graficas`);
  // otro elemento desde la lista: llegan sus series (lazo M–θp, momentos y fuerzas)
  const el = await page.evaluate(async () => {
    const s = document.querySelector('[data-c="elemento"]'), antes = document.querySelector('[data-o="el-titulo"]').textContent;
    s.selectedIndex = Math.min(s.options.length - 1, 3); s.dispatchEvent(new Event('change'));
    for (let k = 0; k < 80; k++) { await new Promise((r) => setTimeout(r, 50)); if (document.querySelector('[data-o="el-titulo"]').textContent !== antes) break; }
    return { titulo: document.querySelector('[data-o="el-titulo"]').textContent, svgs: ['histeresis', 'momentos', 'fuerzas'].map((g) => !!document.querySelector(`[data-g="${g}"] svg.mr-chart path`)) };
  });
  ok(el.svgs.every(Boolean) && /Elemento seleccionado/.test(el.titulo), `${nombre}: series del elemento elegido en la lista (${el.titulo.slice(0, 60)})`);
  await alStage(page);
  return info;
}

// ---------------------------------------------------------------- 1. trabajador simulado
if (solo.has('simulado')) for (const tema of ['claro', 'oscuro']) for (const telefono of [false, true]) {
  const nombre = `simulado-${tema}${telefono ? '-telefono' : ''}`;
  console.log(`\n== ${nombre}`);
  const { page, registro, cerrar } = await pagina({ tema, telefono, q: '&motor=simulado' });
  const fichaBase = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
  if (!ok(await entrarSismo(page), `${nombre}: el primer cálculo terminó`)) { informe(registro, nombre); await cerrar(); continue; }
  await pausa(600);
  await revisar(page, nombre, { telefono });
  const tecla = await page.evaluate(() => { const r = document.querySelector('[data-c="t"]'); r.focus(); return { antes: +r.value, foco: document.activeElement === r }; });
  await page.keyboard.press(tecla.antes > 0 ? 'ArrowLeft' : 'ArrowRight');
  const despues = await page.evaluate(() => +document.querySelector('[data-c="t"]').value);
  ok(tecla.foco && despues !== tecla.antes, `${nombre}: el deslizador de tiempo responde al teclado (${tecla.antes} → ${despues})`);
  const caja = await page.evaluate(() => { const r = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [r.left + r.width * 0.3, r.top + r.height * 0.75]; });
  if (telefono) await page.touchscreen.tap(caja[0], caja[1]); else await page.mouse.click(caja[0], caja[1]);
  await pausa(200);
  ok(await page.evaluate((f) => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML === f, fichaBase), `${nombre}: un clic en el recuadro no cambia la ficha de siempre`);
  if (!telefono) {
    const c = await page.evaluate(async () => {
      document.querySelector('[data-s="calcular"]').click();
      await new Promise((r) => setTimeout(r, 250));
      const t0 = performance.now();
      document.querySelector('[data-s="cancelar"]').click();
      return { dt: performance.now() - t0, estado: document.querySelector('[data-o="estado"]').textContent, calcVisible: !document.querySelector('[data-s="calcular"]').hidden };
    });
    ok(c.dt <= 300 && /cancelado/i.test(c.estado) && c.calcVisible, `${nombre}: «Cancelar» responde en ${c.dt.toFixed(1)} ms («${c.estado}»)`);
    await page.evaluate(() => { window.__torreQA.sismo.calcular('local_hip'); });
    await pausa(150);
    await page.evaluate(() => window.__torreQA.modo('torre'));
    await pausa(900);
    const limpio = await page.evaluate(() => ({
      panel: document.querySelector('[data-slot="torre.panel.sismo"]').hidden && !document.querySelector('[data-slot="torre.panel.sismo"]').childNodes.length,
      hud: document.querySelector('[data-slot="torre.hud.sismo"]').hidden, tarjeta: document.querySelector('[data-slot="torre.sismo"]').hidden,
      ficha: document.querySelector('[data-slot="torre.ficha.modo"]').hidden, modo: window.__torreQA.modo(),
    }));
    ok(Object.values(limpio).every((v) => v === true || v === 'torre'), `${nombre}: cambiar de modo a mitad de un cálculo no deja nada del simulador (${JSON.stringify(limpio)})`);
    await page.evaluate(() => window.__torreQA.modo('sismo'));
    await pausa(600);
    ok(await page.evaluate(() => !document.querySelector('[data-slot="torre.panel.sismo"]').hidden && !!window.__torreQA.sismo.ultimo()), `${nombre}: al volver al simulador está el último resultado`);
  }
  ok(informe(registro, nombre), `${nombre}: consola sin errores`);
  await cerrar();
}

// ---------------------------------------------------------------- 2. motor real con la estructura publicada
if (solo.has('real')) for (const [tema, telefono] of [['claro', false], ['oscuro', true]]) {
  const nombre = `real-${tema}${telefono ? '-telefono' : ''}`;
  console.log(`\n== ${nombre}`);
  const { page, registro, cerrar } = await pagina({ tema, telefono });
  if (!ok(await entrarSismo(page), `${nombre}: nido_2015 terminó`)) { informe(registro, nombre); await cerrar(); continue; }
  await pausa(500);
  const a = await revisar(page, `${nombre}-nido`, { telefono });
  ok(a.motor === 'trabajador', `${nombre}: el motor real corre en el trabajador (${a.motor})`);
  if (!telefono) {
    const t0 = Date.now();
    const r = await page.evaluate(() => window.__torreQA.sismo.calcular({ escenario: 'local_hip' }));
    console.log(`    local_hip en ${Date.now() - t0} ms (${r?.nt} pasos)`);
    await pausa(500);
    await revisar(page, `${nombre}-local`, { telefono });
    await page.evaluate(() => { const s = document.querySelector('[data-c="piso-eq"]'); s.value = '2'; s.dispatchEvent(new Event('change')); });
    await pausa(300);
    const s = await page.evaluate(() => { window.__torreQA.stats(); return window.__torreQA.stats(); });
    ok(s.llamadas <= 60, `${nombre}: con los equipos del piso 2 sobre su losa, ${s.llamadas} llamadas (≤ 60) y ${s.triangulos} triángulos`);
    await captura(page, op, `sismo-${nombre}-equipos`);
  }
  ok(informe(registro, nombre), `${nombre}: consola sin errores`);
  await cerrar();
}

// ---------------------------------------------------------------- 3. respaldo sin Worker y movimiento reducido
if (solo.has('respaldo')) {
  const resumen = (p) => p.evaluate(() => { const u = window.__torreQA.sismo.ultimo(), R = u.resultados; let s = 0; for (let i = 0; i < R.u.length; i++) s += R.u[i]; return { motor: window.__torreQA.sismo.motor(), nt: u.nt, dc: u.dc_max, deriva: u.deriva_vector_max, suma_u: s, u_fin: Array.from(R.u.slice(-6)) }; });
  console.log('\n== respaldo (cubo de prueba, motor real)');
  const A = await pagina({ q: '&estructura=min' });
  ok(await entrarSismo(A.page), 'con trabajador: el cálculo terminó');
  const ra = await resumen(A.page);
  ok(informe(A.registro, 'cubo con trabajador'), 'consola sin errores');
  await A.cerrar();
  const B = await pagina({ q: '&estructura=min', sinWorker: true, movimientoReducido: true });
  ok(await entrarSismo(B.page), 'sin Worker: el cálculo terminó');
  const rb = await resumen(B.page);
  ok(ra.motor === 'trabajador' && rb.motor === 'hilo_principal', `motores ${ra.motor} / ${rb.motor}`);
  ok(ra.nt === rb.nt && ra.suma_u === rb.suma_u && ra.dc === rb.dc && JSON.stringify(ra.u_fin) === JSON.stringify(rb.u_fin), `el respaldo da el mismo resultado (${rb.nt} pasos, D/C ${rb.dc})`);
  await B.page.evaluate(() => window.__torreQA.sismo.calcular({ semilla: 7 }));
  ok(await B.page.evaluate(() => document.querySelector('[data-s="play"]').getAttribute('aria-pressed') === 'false'), 'con movimiento reducido no se reproduce solo');
  const c = await B.page.evaluate(async () => {
    const p = window.__torreQA.sismo.calcular({ Mw: 7.6, profundidad_km: 15, distancia_epicentral_km: 120 });
    let f = 0;
    for (let k = 0; k < 400 && f < 0.15; k++) { await new Promise((r) => setTimeout(r, 25)); f = +document.querySelector('[data-o="progreso"]').value || 0; }
    const t0 = performance.now();
    document.querySelector('[data-s="cancelar"]').click();
    const r = await p;
    return { f, dt: performance.now() - t0, r, estado: document.querySelector('[data-o="estado"]').textContent };
  });
  ok(c.dt <= 300 && c.r?.cancelado, `«Cancelar» en el hilo principal con ${(c.f * 100).toFixed(0)} % hecho: ${c.dt.toFixed(0)} ms («${c.estado}»)`);
  ok(informe(B.registro, 'cubo sin Worker'), 'consola sin errores');
  await B.cerrar();
}

// ---------------------------------------------------------------- 4. sin el modelo estructural publicado
if (solo.has('sin_estructura')) {
  console.log('\n== sin el modelo estructural publicado');
  const r = await pagina({ sinEstructura: true });
  const res = await r.page.evaluate(() => window.__torreQA.sismo.calcular());
  const estado = await r.page.evaluate(() => document.querySelector('[data-o="estado"]').textContent);
  ok(res?.error === 'datos' && /todavía no están publicados/.test(estado), `la vista lo explica: «${estado}»`);
  r.registro.errores = r.registro.errores.filter((e) => !/Failed to load resource.*404/.test(e));
  ok(informe(r.registro, 'sin estructura'), 'consola sin errores (salvo el 404 esperado)');
  await r.cerrar();
}

// ---------------------------------------------------------------- 5. correcciones de la revisión de la vista
if (solo.has('revision')) for (const [tema, telefono] of [['claro', false], ['oscuro', false], ['claro', true]]) {
  const nombre = `revision-${tema}${telefono ? '-telefono' : ''}`;
  console.log(`\n== ${nombre}`);
  {
    // A. torre.json 4 s tarde: el simulador no deja pisos ocultos en la selección del Stage
    const { page, registro, cerrar } = await pagina({ tema, telefono, q: '&motor=simulado', retrasoTorre: 4000 });
    const fichaBase = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
    await page.evaluate(() => window.__torreQA.modo('sismo'));
    await esperar(page, () => window.__torreQA.listo() && !!window.__torreQA.sismo.ultimo(), { ms: 60000 });
    await pausa(500);
    const n = await page.evaluate(() => window.__torreQA.seleccionables());
    const caja = await page.evaluate(() => { const r = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [r.left + r.width * 0.2, r.top + r.height * 0.6]; });
    if (telefono) await page.touchscreen.tap(caja[0], caja[1]); else await page.mouse.click(caja[0], caja[1]);
    await pausa(200);
    const igual = await page.evaluate((f) => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML === f, fichaBase);
    ok(n === 0 && igual, `torre.json 4 s tarde: ${n} objetos seleccionables en el simulador y un clic no cambia la ficha de siempre (${igual})`);
    ok(informe(registro, `${nombre} selección`), 'consola sin errores');
    await cerrar();
  }
  const { page, registro, cerrar } = await pagina({ tema, telefono });
  // B. primer cálculo: sin etiquetas de deriva vacías; la cámara girada por la persona no se reencuadra
  await enEscena(page, (st) => { window.__fb = 0; window.__tocada = false; const fb = st.frameBox.bind(st); st.frameBox = (...a) => { if (window.__tocada) window.__fb++; return fb(...a); }; st.controls.addEventListener('start', () => { window.__tocada = true; }); });
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  await page.evaluate(() => { window.__torreQA.modo('sismo'); });
  await esperar(page, () => /respuesta de la estructura/.test(document.querySelector('[data-o="estado"]')?.textContent || ''), { ms: 60000 });
  const vacias = await page.evaluate(() => [...document.querySelectorAll('.sismo-lbl')].filter((o) => o.style.display !== 'none' && getComputedStyle(o).visibility !== 'hidden' && o.offsetParent !== null && !o.textContent.trim()).length);
  ok(!vacias, `durante el primer cálculo no hay etiquetas de deriva vacías (${vacias})`);
  if (!telefono) {
    const box = await page.evaluate(() => { const b = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [b.left + b.width * 0.6, b.top + b.height * 0.5]; });
    await page.mouse.move(box[0], box[1]); await page.mouse.down();
    for (let k = 1; k <= 8; k++) { await page.mouse.move(box[0] + k * 15, box[1] + k * 3); await pausa(20); }
    await page.mouse.up();
  }
  await esperar(page, () => !!window.__torreQA.sismo.ultimo(), { ms: 180000 });
  await pausa(1500);
  if (!telefono) ok(await page.evaluate(() => window.__tocada && window.__fb === 0), `girar la cámara durante el primer cálculo: al terminar no se reencuadra (${await page.evaluate(() => window.__fb)} encuadres después)`);
  // C. la región viva del escenario no se reescribe con cada flecha de un control
  await vigilar(page, '[data-o="escenario"]');
  await page.focus('[data-c="vs30"]');
  for (let k = 0; k < 5; k++) await page.keyboard.press('ArrowRight');
  const mEsc = await vigilado(page);
  ok(mEsc.n === 0, `5 flechas en «Suelo: Vs30»: la región viva del escenario cambió ${mEsc.n} veces`);
  // D. la región viva del estado cambia por fases, no con cada avance; el foco vuelve a «Calcular»
  await vigilar(page, '[data-o="estado"]');
  await page.evaluate(() => { window.__u0 = window.__torreQA.sismo.ultimo(); });
  await page.focus('[data-s="calcular"]');
  await page.keyboard.press('Enter');
  await esperar(page, () => window.__torreQA.sismo.ultimo() !== window.__u0, { ms: 180000 });
  await pausa(300);
  const mEst = await vigilado(page), foco = await page.evaluate(() => document.activeElement?.dataset?.s || document.activeElement?.tagName);
  ok(mEst.n <= 8, `un cálculo cambió la región viva del estado ${mEst.n} veces (≤ 8)`);
  ok(foco === 'calcular', `con Enter en «Calcular», al terminar el foco queda en «Calcular» (${foco})`);
  // E. Clough + Calcular + Cancelar: el modelo sigue dibujado, con sus etiquetas
  const lineas = () => enEscena(page, (st) => { const g = st.scene.getObjectByName('estructura_sismo'); if (!g) return null; const ls = g.children.filter((o) => o.isLineSegments2 && o.visible); const a = ls[0].geometry.attributes.instanceStart.data.array; let nz = 0; for (let i = 0; i < a.length; i++) if (a[i] !== 0) nz++; return { nz, total: a.length, vis: ls.length }; });
  const l0 = await lineas();
  await page.evaluate(() => { const r = document.querySelector('input[name="sismo-histeresis"][value="clough"]'); r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); document.querySelector('[data-s="calcular"]').click(); });
  await esperar(page, () => /movimiento del suelo|respuesta de la estructura/.test(document.querySelector('[data-o="estado"]').textContent), { ms: 60000 });
  await page.evaluate(() => document.querySelector('[data-s="cancelar"]').click());
  await pausa(500);
  const l1 = await lineas();
  const lbl = await page.evaluate(() => [...document.querySelectorAll('.sismo-lbl')].filter((o) => o.style.display !== 'none' && o.offsetParent !== null).map((o) => o.textContent.trim()));
  ok(l1 && l1.nz === l0.nz && l1.vis === l0.vis && lbl.length && lbl.every(Boolean), `tras cambiar la histéresis, calcular y cancelar: líneas ${l1?.nz}/${l1?.total} (antes ${l0?.nz}), ${lbl.length} etiquetas con texto`);
  // F. salir a mitad de un cálculo y volver: el estado no queda congelado y las series siguen
  await page.evaluate(() => { const r = document.querySelector('input[name="sismo-histeresis"][value="bilineal"]'); r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); window.__p = window.__torreQA.sismo.calcular({ escenario: 'local_hip' }); });
  await esperar(page, () => (+document.querySelector('[data-o="progreso"]').value || 0) > 0.1, { ms: 60000 });
  await page.evaluate(() => window.__torreQA.modo('torre'));
  await pausa(400);
  const fuera = await page.evaluate(() => ({ panel: document.querySelector('[data-slot="torre.panel.sismo"]').hidden, ficha: document.querySelector('[data-slot="torre.ficha.modo"]').hidden }));
  await page.evaluate(() => window.__torreQA.modo('sismo'));
  await esperar(page, () => !document.querySelector('[data-o="progreso"]') || document.querySelector('[data-o="progreso"]').hidden, { ms: 60000 });
  await pausa(600);
  const vuelta = await page.evaluate(async () => {
    const s = document.querySelector('[data-c="elemento"]'), antes = document.querySelector('[data-o="el-titulo"]').textContent;
    s.selectedIndex = Math.min(s.options.length - 1, 4); s.dispatchEvent(new Event('change'));
    for (let k = 0; k < 80; k++) { await new Promise((r) => setTimeout(r, 50)); if (document.querySelector('[data-o="el-titulo"]').textContent !== antes) break; }
    return { estado: document.querySelector('[data-o="estado"]').textContent, titulo: document.querySelector('[data-o="el-titulo"]').textContent, graficas: ['histeresis', 'momentos', 'fuerzas'].every((g) => !!document.querySelector(`[data-g="${g}"] svg.mr-chart path`)) };
  });
  ok(fuera.panel && fuera.ficha && /^Listo/.test(vuelta.estado) && vuelta.graficas && !/no están disponibles/.test(vuelta.titulo), `salir a mitad de un cálculo y volver: «${vuelta.estado.slice(0, 60)}»; series de otro elemento: ${vuelta.graficas}`);
  // G. reproducir con el recuadro fuera de la pantalla: el tiempo sigue
  if (!telefono) {
    await page.evaluate(() => { const b = document.querySelector('[data-s="play"]'); if (b.getAttribute('aria-pressed') !== 'true') b.click(); });
    await page.evaluate(() => document.querySelector('[data-slot="torre.sismo"]').scrollIntoView({ block: 'start' }));
    await pausa(400);
    const t1 = await page.evaluate(() => document.querySelector('[data-o="t"]').textContent);
    await pausa(1500);
    const t2 = await page.evaluate(() => document.querySelector('[data-o="t"]').textContent);
    ok(t1 !== t2, `reproduciendo con el recuadro fuera de la vista el tiempo avanza («${t1}» → «${t2}»)`);
    await page.evaluate(() => { const b = document.querySelector('[data-s="play"]'); if (b.getAttribute('aria-pressed') === 'true') b.click(); document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }); });
  }
  // H. búferes de WebGL: 20 cambios del piso de los equipos sin dejar búferes vivos
  const net = await enEscena(page, async (st) => {
    const gl = (await import(new URL('js/core.js', location.href).href)).engine.renderer.getContext();
    const vivos = new Set(); const c0 = gl.createBuffer.bind(gl), d0 = gl.deleteBuffer.bind(gl);
    gl.createBuffer = () => { const b = c0(); vivos.add(b); return b; }; gl.deleteBuffer = (b) => { vivos.delete(b); return d0(b); };
    const s = document.querySelector('[data-c="piso-eq"]'), ops = [...s.options].map((o) => o.value).filter(Boolean);
    for (let k = 0; k < 20; k++) { s.value = ops[k % ops.length]; s.dispatchEvent(new Event('change')); await new Promise((r) => requestAnimationFrame(() => r())); }
    s.value = ''; s.dispatchEvent(new Event('change'));
    for (let k = 0; k < 3; k++) await new Promise((r) => requestAnimationFrame(() => r()));
    gl.createBuffer = c0; gl.deleteBuffer = d0;
    return vivos.size;
  });
  ok(net === 0, `20 cambios del piso de los equipos: ${net} búferes de WebGL creados y no borrados`);
  const dz = await desborde(page);
  ok(dz.ok, `sin desborde horizontal (${dz.scrollWidth} ≤ ${dz.innerWidth})`);
  ok(informe(registro, nombre), `${nombre}: consola sin errores`);
  await cerrar();
}

await nav.close(); await srv.cerrar();
console.log(fallas ? `\nQA del simulador sísmico con ${fallas} fallas` : '\nQA del simulador sísmico sin fallas');
process.exit(fallas ? 1 : 0);
