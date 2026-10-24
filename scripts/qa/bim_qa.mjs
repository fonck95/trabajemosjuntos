#!/usr/bin/env node
// QA del modo «Modelo BIM» de la vista de la torre (equipo F; especificación de integración 17.5 y 17.7).
//
//   PLAYWRIGHT_MODULE=… node scripts/qa/bim_qa.mjs --vendor <carpeta> [--salida <carpeta>] [--solo terreno,vistas,sismo,seleccion,ifc,salida,movimiento]
//
// Sirve web/ con scripts/qa/comun.mjs (three y GSAP locales con --vendor), abre index.html?qa=1#torre en Chromium sin pantalla
// (WebGL por software) y recorre el modo con la API que publica torre.js en __torreQA.bim.api() (la misma que usan los botones):
//   · terreno: se entra a la cimentación antes de que llegue el suelo del sitio; cuando llega, todo el suelo a la vista lleva
//     la copia del modo (recortado o transparente) y un dado y la punta de dos pilotes se ven desde la cámara (rayo que
//     respeta el recorte y la transparencia), en «Cortado», en «Semitransparente» y en «Ver refuerzo» de un dado.
//   · vistas, en claro y oscuro, en escritorio (1400 × 900) y teléfono (390 × 844, táctil): el modelo entero, la cimentación
//     con el terreno cortado, cortes horizontales por nivel y verticales por eje con su tapa, el refuerzo de una columna, una
//     viga, un dado y un pilote (barras, kilos frente al despiece y esquema 2D con sección y alzado), el refuerzo de un eje,
//     la vista de corte de un elemento (tapa y secciones de las barras), el 5D (colores por capítulo y «Ver en 3D» de un ítem),
//     el 4D (lo construido crece con la fecha) y las interferencias con «Ir a»; en cada estado, llamadas de dibujo ≤ 60;
//     al final, consola sin errores, sin desborde horizontal y sin rutas ni claves internas en el texto visible.
//   · sismo: un cálculo real del motor del simulador (trabajador) y sus colores en el modelo: D/C de cada elemento con
//     análisis igual al de las envolventes del cálculo, rótulas y deriva por entrepiso; también con el sismo de diseño.
//   · seleccion: clic en el modelo (el elemento bajo el puntero abre su ficha), árbol por disciplina → nivel → clase →
//     elemento y buscador.
//   · ifc: descarga de los dos IFC desde la pestaña (nombre, tamaño y encabezado ISO-10303-21 con FILE_SCHEMA IFC4).
//   · salida: al volver a «Con la torre» todo queda como antes (exterior, suelo, recorte, árboles, llamadas de dibujo) y el
//     recorrido y el simulador siguen funcionando; al volver al modo BIM, se ve lo de antes.
//   · movimiento: el modo con animaciones (sin prefers-reduced-motion), sin errores.
// Las capturas van con prefers-reduced-motion (salvo «movimiento»): con WebGL por software, cada vuelo de cámara deja en cola
// decenas de cuadros y una captura puede tardar medio minuto. Sale con código 1 si algo falla. Capturas e informe
// (bim_qa.json) en --salida.
import { opciones, servidor, navegador, abrir, esperar, desborde, textosInternos, captura, informe, guardarJSON } from './comun.mjs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { readFile, stat } from 'node:fs/promises';

const op = opciones(process.argv.slice(2), { salida: join(tmpdir(), 'atlas_qa', 'bim') });
const solo = new Set(String(op.solo || 'terreno,vistas,sismo,seleccion,ifc,salida,movimiento').split(','));
const fallas = [], resultado = {};
const falla = (txt) => { fallas.push(txt); console.log(`  FALLA ${txt}`); };
const bien = (txt) => console.log(`  ok ${txt}`);
const comprobar = (cond, txt) => { if (cond) bien(txt); else falla(txt); return !!cond; };
const MAX_LLAMADAS = 60;
const nf = (v, d = 0) => (+v).toLocaleString('es-CO', { maximumFractionDigits: d });

const srv = await servidor({ ...op, raiz: op.raiz || 'web' });
const nav = await navegador(op);
const URL0 = `${srv.url}?qa=1#torre`;
const CAP = { timeout: 120000 };

async function pagina({ tema = 'claro', telefono = false, movimientoReducido = true } = {}) {
  const p = await abrir(nav, op, { url: URL0, tema, telefono, movimientoReducido });
  await esperar(p.page, () => window.__torreQA?.listo?.(), { ms: 40000 });
  await p.page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  return p;
}
async function entrarBIM(page) {
  await page.evaluate(() => window.__torreQA.modo('bim'));
  return esperar(page, () => window.__torreQA.bim.api()?.estado?.().cargado, { ms: 90000 });
}
const api = (page, f, ...a) => page.evaluate(([f, a]) => window.__torreQA.bim.api()[f](...a), [f, a]);
const estado = (page) => api(page, 'estado');
const stats = (page) => page.evaluate(() => window.__torreQA.stats());
const cuadros = (page, n = 3) => page.evaluate((n) => new Promise((r) => { let k = 0; const f = () => (++k >= n ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); }), n);
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
// el recuadro a la vista antes de cada captura (las capturas de la ficha y del panel desplazan la página)
const aLaVista = (page) => page.evaluate(() => { const e = document.querySelector('#v-torre .stage'), r = e.getBoundingClientRect(); if (r.top < 0 || r.bottom > innerHeight) e.scrollIntoView({ block: 'center' }); });
async function foto(page, nombre) {
  await aLaVista(page);
  await cuadros(page, 2);
  return captura(page, op, nombre, CAP);
}
async function presupuesto(page, nombre) {
  const s = await stats(page);
  comprobar(s.llamadas <= MAX_LLAMADAS, `${nombre}: ${s.llamadas} llamadas de dibujo ≤ ${MAX_LLAMADAS} (${nf(s.triangulos)} triángulos)`);
  return s;
}
function informar(registro, titulo) {
  const ok = informe(registro, titulo);
  for (const t of registro.avisos.slice(0, 4)) console.log(`    aviso: ${t.slice(0, 160)}`);
  return ok;
}
// datos publicados (lo que recibe el modo), para comparar
async function datos(page, f) { return page.evaluate((f) => window.__torreQA.datos(f), f); }

// ---------------------------------------------------------------- vistas en claro, oscuro y teléfono
async function vistas() {
  console.log('vistas: modelo, cimentación, cortes, refuerzo, 5D, 4D e interferencias');
  for (const [tema, telefono] of [['claro', false], ['oscuro', false], ['claro', true], ['oscuro', true]]) {
    const nombre = `${tema}${telefono ? '-telefono' : ''}`, R = (resultado[`vistas ${nombre}`] = {});
    const { page, registro, cerrar } = await pagina({ tema, telefono });
    const t0 = Date.now();
    if (!comprobar(await entrarBIM(page), `${nombre}: el modelo BIM carga (${Date.now() - t0} ms)`)) { await cerrar(); continue; }
    await cuadros(page);
    let e = await estado(page);
    const idx = await datos(page, 'torre_bim.json');
    comprobar(e.elementos === idx.totales.elementos, `${nombre}: ${nf(e.elementos)} elementos dibujados = ${nf(idx.totales.elementos)} del índice`);
    comprobar(e.visibles > 4000 && !e.corte && e.vista === 'modelo', `${nombre}: vista del modelo entero (${nf(e.visibles)} elementos a la vista; los espacios van ocultos)`);
    R.modelo = await presupuesto(page, `${nombre} modelo`);
    await foto(page, `bim-modelo-${nombre}`);

    // cimentación
    await api(page, 'pestana', 'cimentacion');
    await api(page, 'cimentacion', true, 'cortado');
    await cuadros(page);
    e = await estado(page);
    const cim = await page.evaluate(() => { const d = window.__torreQA.bim.api().depurar(), L = []; d.grupo.traverse((o) => { if (o.name === 'bim_foso') L.push(o.visible && o.parent.visible); }); return { foso: L[0] }; });
    comprobar(e.vista === 'cimentacion' && e.terreno === 'cortado' && cim.foso, `${nombre}: cimentación con el terreno cortado (excavación de muestra a la vista)`);
    comprobar(e.etiquetas >= (telefono ? 3 : 6), `${nombre}: ${e.etiquetas} etiquetas de cotas, dimensiones y cargas en la cimentación`);
    R.cimentacion = await presupuesto(page, `${nombre} cimentación`);
    await foto(page, `bim-cimentacion-${nombre}`);

    // cortes por nivel y por eje
    for (const [f, a, t] of [['cortarNivel', 'P2', 'horizontal en el piso 2'], ['cortarNivel', 'CIM', 'horizontal en la cimentación'], ['cortarEje', 'C', 'vertical por el eje C'], ['cortarEje', '4', 'vertical por el eje 4']]) {
      await api(page, f, a);
      await cuadros(page);
      e = await estado(page);
      comprobar(e.corte && e.tapa > 0 && e.vista === 'modelo', `${nombre}: corte ${t} con tapa (${nf(e.tapa)} triángulos de sección)`);
      R[`corte ${a}`] = await presupuesto(page, `${nombre} corte ${a}`);
      if (a === 'P2' || a === 'C') await foto(page, `bim-corte-${a}-${nombre}`);
    }
    await api(page, 'quitarCorte');

    // refuerzo de una columna, una viga, un dado y un pilote
    const MUESTRAS = [['C-B2-2', 'columna', 'P2', 'de la columna'], ['VX-2-BC-2', 'viga', 'P3', 'de la viga'], ['D-B2', 'dado', 'CIM', 'del dado'], ['PIL-D-B2-1', 'pilote', 'CIM-PIL', 'del pilote']];
    for (const [id, tipo, nivel, deTipo] of MUESTRAS) {
      const r = await api(page, 'verRefuerzo', id);
      await cuadros(page);
      e = await estado(page);
      const elem = (await datos(page, `torre_bim_${nivel}.json`))?.elementos.find((x) => x.id === id);
      const kgModelo = elem?.refuerzo?.kg;
      // en la viga se suman las barras corridas de los otros tramos que pasan por ella: los kilos son ≥ los suyos
      const kgOk = tipo === 'viga' ? r.kg >= kgModelo * 0.99 : Math.abs(r.kg - kgModelo) <= Math.max(1.5, 0.01 * kgModelo);
      comprobar(r && r.barras > 0 && e.refuerzo?.instancias > 0 && kgOk, `${nombre}: refuerzo ${deTipo} ${id}: ${nf(r?.barras)} barras, ${nf(r?.kg)} kg (despiece del elemento: ${nf(kgModelo)} kg), ${nf(e.refuerzo?.instancias)} tramos instanciados`);
      const svg = await page.evaluate(() => [...document.querySelectorAll('.bim-ficha .bd svg')].map((s) => ({ circulos: s.querySelectorAll('circle').length, lineas: s.querySelectorAll('polyline').length, cotas: s.querySelectorAll('.bd-cota text').length, zonas: s.querySelectorAll('.bd-zona').length })));
      const conPuntos = svg.some((s) => s.circulos > 0), conLineas = svg.every((s) => s.lineas > 0 || s.circulos > 0);
      comprobar(svg.length === 2 && conPuntos && conLineas && svg.every((s) => s.cotas >= 2), `${nombre}: despiece 2D de ${id} con sección y ${tipo === 'dado' ? 'planta' : 'alzado'} acotados (${svg.map((s) => `${s.circulos} barras cortadas, ${s.lineas} barras, ${s.zonas} zonas`).join(' · ')})`);
      comprobar(e.etiquetas >= (telefono ? 2 : 3), `${nombre}: ${e.etiquetas} etiquetas del armado sobre el 3D de ${id}`);
      // las llamadas del armado no se pisan y quedan dentro del recuadro (con el recuadro a la vista: fuera de ella no se dibuja)
      await aLaVista(page);
      await cuadros(page, 3);
      const llam = await page.evaluate(() => {
        const st = document.querySelector('#v-torre .stage').getBoundingClientRect();
        const R = [...document.querySelectorAll('#v-torre .bim-ancla > .bim-llamada')].filter((x) => x.offsetParent && x.closest('.lbl').style.display !== 'none').map((x) => x.getBoundingClientRect());
        let pisan = 0;
        for (let i = 0; i < R.length; i++) for (let j = i + 1; j < R.length; j++) { const a = R[i], b = R[j]; if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) pisan++; }
        const fuera = R.filter((r) => r.left < st.left - 1 || r.right > st.right + 1).length;
        return { n: R.length, pisan, fuera };
      });
      comprobar(llam.n >= (telefono ? 2 : 3) && llam.pisan === 0 && llam.fuera === 0, `${nombre}: las ${llam.n} llamadas del armado de ${id} no se pisan (${llam.pisan}) ni se salen del recuadro (${llam.fuera})`);
      if (tipo === 'viga') {
        const tot = await page.evaluate(() => document.querySelector('.bim-ficha .bd-total')?.textContent || '');
        const kgTramo = +(tot.match(/([\d.]+) kg de acero de 420 MPa de este tramo/)?.[1] || '').replace(/\./g, '');
        comprobar(Math.abs(kgTramo - kgModelo) <= 1, `${nombre}: la ficha de la viga da ${nf(kgTramo)} kg de este tramo (despiece del elemento: ${nf(kgModelo)} kg) y aparte los de las barras corridas que pasan`);
      }
      R[`refuerzo ${tipo}`] = { ...(await presupuesto(page, `${nombre} refuerzo ${tipo}`)), barras: r?.barras, kg: r?.kg };
      await foto(page, `bim-refuerzo-${tipo}-${nombre}`);
      if (!telefono) { const f = await page.$('#v-torre [data-slot="torre.ficha"] .bd'); if (f) await f.screenshot({ path: join(op.salida, `bim-despiece-${tipo}-${nombre}.png`), ...CAP }); }
    }
    // refuerzo de un eje y vista de corte de un elemento
    if (!telefono) {
      const r = await api(page, 'refuerzoEje', 'A', 'P2');
      await cuadros(page);
      e = await estado(page);
      comprobar(r?.hosts?.length >= 7 && e.refuerzo?.instancias > 1000, `${nombre}: refuerzo del eje A en el piso 2: ${r?.hosts?.length} elementos, ${nf(r?.barras)} barras, ${nf(e.refuerzo?.instancias)} tramos`);
      R['refuerzo eje'] = await presupuesto(page, `${nombre} refuerzo del eje`);
      await foto(page, `bim-refuerzo-eje-${nombre}`);
      const rc = await api(page, 'refuerzoEje', 'B', 'CIM');
      comprobar(rc?.hosts?.some((h) => /^PIL-/.test(h)) && rc.hosts.some((h) => /^D-/.test(h)), `${nombre}: refuerzo del eje B en la cimentación con dados y pilotes (${rc?.hosts?.length} elementos)`);
    }
    const c = await api(page, 'corteElemento', 'C-B2-2');
    await cuadros(page);
    e = await estado(page);
    comprobar(c?.corte && e.tapa > 0 && e.seccionesBarras >= 24, `${nombre}: vista de corte de la columna C-B2-2 con su tapa y ${e.seccionesBarras} barras cortadas`);
    await foto(page, `bim-corte-elemento-${nombre}`);
    await api(page, 'salirRefuerzo');
    await api(page, 'quitarCorte');

    // 5D
    await api(page, 'pestana', '5d');
    const caps = await api(page, 'color5D', true);
    await cuadros(page);
    e = await estado(page);
    comprobar(caps >= 10 && e.leyenda, `${nombre}: 5D, el modelo coloreado por ${caps} capítulos del presupuesto con su leyenda`);
    R['5D'] = await presupuesto(page, `${nombre} 5D`);
    await foto(page, `bim-5d-${nombre}`);
    const filas = await page.evaluate(() => document.querySelectorAll('[data-slot="torre.bim.tablas"] table.bim-t5d tbody tr').length);
    const item = await page.evaluate(() => { const b = document.querySelector('[data-slot="torre.bim.tablas"] button[data-item="3.01"]'); b?.click(); return !!b; });
    await cuadros(page);
    e = await estado(page);
    const n301 = (await Promise.all(idx.niveles.map((n) => datos(page, `torre_bim_${n.id}.json`)))).flatMap((d) => d?.elementos || []).filter((x) => (x.costo || []).some((c) => c.item === '3.01')).length;
    comprobar(filas >= 10 && item && e.aislados === n301, `${nombre}: tarjeta 5D (${filas} capítulos) y «Ver en 3D» del ítem 3.01 aísla sus ${nf(n301)} elementos (${nf(e.aislados)})`);
    await api(page, 'mostrarTodo');

    // 4D
    await api(page, 'pestana', '4d');
    const fechas = ['2028-10-01', '2028-12-20', '2029-04-15', '2029-08-01', '2029-12-01', '2030-02-28'], vis = [], pct = [];
    for (const f of fechas) {
      const a = await api(page, 'fecha4D', f);
      e = await estado(page);
      vis.push(e.visibles); pct.push(a?.pct ?? -1);
      if (f === '2029-04-15') { await cuadros(page); R['4D'] = await presupuesto(page, `${nombre} 4D`); await foto(page, `bim-4d-${nombre}`); }
    }
    const crece = vis.every((v, i) => !i || v >= vis[i - 1]) && pct.every((v, i) => !i || v >= pct[i - 1]);
    comprobar(crece && vis[0] < vis[vis.length - 1] && Math.abs(pct[pct.length - 1] - 100) < 0.5, `${nombre}: 4D, lo construido crece con la fecha (${vis.map(nf).join(' → ')} elementos; avance ${pct.map((v) => `${nf(v)} %`).join(' → ')})`);
    await api(page, 'pestana', 'modelo');
    e = await estado(page);
    comprobar(e.avance === null && e.visibles > 4000, `${nombre}: al salir de la pestaña 4D vuelve el modelo entero`);

    // interferencias
    await api(page, 'pestana', 'interferencias');
    await esperar(page, () => document.querySelectorAll('.bim-panel ul.bim-int button[data-int]').length > 0, { ms: 30000 });
    const intf = await datos(page, 'torre_bim_interferencias.json');
    const conBarras = intf.interferencias.find((x) => x.barras?.length && x.posicion && x.severidad === 'media');
    const r1 = await page.evaluate(() => { document.querySelector('.bim-panel ul.bim-int button[data-int]').click(); return document.querySelector('.bim-panel ul.bim-int button[data-int]').dataset.int; });
    await pausa(600); await cuadros(page);
    e = await estado(page);
    comprobar(/^Interferencia/.test(e.rotulo || '') && e.seleccion, `${nombre}: «Ir a» la interferencia ${r1} elige su elemento (${e.seleccion}) y marca el punto`);
    await foto(page, `bim-interferencia-${nombre}`);
    const r2 = await api(page, 'irAInterferencia', conBarras.id);
    await cuadros(page);
    e = await estado(page);
    comprobar(r2?.barras > 0 && e.refuerzo?.instancias > 0, `${nombre}: «Ir a» ${conBarras.id} (${conBarras.categoria}) muestra el refuerzo con las barras del hallazgo resaltadas`);
    R.interferencias = await presupuesto(page, `${nombre} interferencias`);
    await foto(page, `bim-interferencia-barras-${nombre}`);
    await api(page, 'salirRefuerzo');

    // pestañas del panel y su ficha (capturas del panel en escritorio claro y teléfono oscuro)
    if ((tema === 'claro' && !telefono) || (tema === 'oscuro' && telefono)) {
      for (const t of ['modelo', 'cortes', 'cimentacion', 'refuerzo', 'comportamiento', '5d', '4d', 'interferencias', 'ifc']) {
        await api(page, 'pestana', t);
        await pausa(200);
        const pnl = await page.$('#v-torre [data-slot="torre.panel"]');
        await pnl.screenshot({ path: join(op.salida, `bim-panel-${t}-${nombre}.png`), ...CAP });
      }
      await api(page, 'pestana', 'modelo');
      const tj = await page.$('#v-torre [data-slot="torre.bim"]');
      await tj.screenshot({ path: join(op.salida, `bim-tarjeta-5d-${nombre}.png`), ...CAP });
    }
    const d = await desborde(page);
    comprobar(d.ok, `${nombre}: sin desborde horizontal${d.ok ? '' : ` (${d.culpables.join(', ')})`}`);
    const internos = await textosInternos(page, '#v-torre');
    comprobar(!internos.length, `${nombre}: texto visible sin rutas ni claves internas${internos.length ? `: ${internos.slice(0, 3).join(' | ')}` : ''}`);
    comprobar(informar(registro, `vistas ${nombre}`), `${nombre}: consola sin errores ni peticiones fallidas`);
    await cerrar();
  }
}

// ---------------------------------------------------------------- terreno: la cimentación se ve aunque el suelo del sitio llegue después
// Se entra a la cimentación apenas carga el modelo (antes de que lleguen los modelos del sitio con su suelo «entorno») y,
// cuando ya llegaron, se revisa que todo el suelo a la vista lleve la copia del modo (recortado o transparente) y que un
// dado y la punta de un pilote se vean desde la cámara, en «Cortado», en «Semitransparente» y en «Ver refuerzo» de D-A1.
async function terreno() {
  console.log('terreno: suelo del sitio y cimentación a la vista');
  for (const [tema, telefono] of [['claro', false], ['oscuro', true]]) {
    const nombre = `${tema}${telefono ? '-telefono' : ''}`;
    const { page, registro, cerrar } = await pagina({ tema, telefono });
    if (!comprobar(await entrarBIM(page), `${nombre}: el modelo BIM carga`)) { await cerrar(); continue; }
    await api(page, 'pestana', 'cimentacion');
    await api(page, 'cimentacion', true, 'cortado');
    const s0 = await api(page, 'suelo');
    // los modelos del sitio (su suelo) llegan después: se espera a que el número de triángulos se estabilice
    let prev = -1;
    for (let k = 0; k < 60; k++) { const st_ = await stats(page); if (st_.triangulos > 1000 && st_.triangulos === prev) break; prev = st_.triangulos; await pausa(1000); }
    await pausa(800); await cuadros(page, 4);
    // el suelo no tapa ni el dado ni las puntas de sus pilotes (otro elemento delante sí puede taparlos: eso no es del suelo)
    const revisar = async (modo, txt, ref = false) => {
      const suelo = await api(page, 'suelo');
      const ok = suelo.length > 0 && suelo.every((q) => q.copia && (modo === 'cortado' ? q.recorte === 4 : q.transparente && q.opacidad <= 0.31));
      comprobar(ok, `${nombre}: ${txt}: las ${suelo.length} mallas del suelo a la vista llevan la copia ${modo === 'cortado' ? 'recortada' : 'transparente'} (al entrar había ${s0.length}: ${suelo.map((q) => q.nombre || 'suelo').slice(0, 5).join(', ')})`);
      const ids = [['D-A1', { fantasma: ref }], ['PIL-D-A1-1', { punta: true }], ['PIL-D-A1-3', { punta: true }]].concat(ref ? [] : [['PIL-D-B2-1', { punta: true }], ['PIL-LP-escalera_norte-1', { punta: true }]]);
      const vs = [];
      for (const [id, op_] of ids) vs.push([id, op_, await api(page, 'seVe', id, op_)]);
      const visibles = vs.filter(([, , v]) => v?.ve).length;
      comprobar(vs.every(([, , v]) => v && !v.suelo) && visibles >= 2, `${nombre}: ${txt}: el suelo no tapa el dado ni las puntas de los pilotes (${vs.map(([id, op_, v]) => `${op_.punta ? 'punta de ' : ''}${id}: ${v?.ve ? 'se ve' : `detrás de ${v?.tapa}`}`).join('; ')})`);
    };
    await revisar('cortado', 'cimentación con el terreno cortado');
    await foto(page, `bim-terreno-cortado-${nombre}`);
    await api(page, 'cimentacion', true, 'semi');
    await cuadros(page, 3);
    await revisar('semi', 'cimentación con el terreno semitransparente');
    await foto(page, `bim-terreno-semi-${nombre}`);
    const r = await api(page, 'verRefuerzo', 'D-A1');
    await cuadros(page, 3);
    const e = await estado(page);
    comprobar(e.terreno === 'semi' && r?.barras > 0 && e.refuerzo?.instancias > 0, `${nombre}: «Ver refuerzo» de D-A1 con el terreno semitransparente (${r?.barras} barras, ${e.refuerzo?.instancias} tramos)`);
    await revisar('semi', 'refuerzo de D-A1', true);
    await foto(page, `bim-terreno-refuerzo-D-A1-${nombre}`);
    await api(page, 'salirRefuerzo');
    const suelo = await api(page, 'suelo');
    comprobar(suelo.every((q) => !q.copia), `${nombre}: al volver al modelo el suelo recupera su material (${suelo.length} mallas)`);
    comprobar(informar(registro, `terreno ${nombre}`), `${nombre}: consola sin errores ni peticiones fallidas`);
    await cerrar();
  }
}

// ---------------------------------------------------------------- colores del último cálculo real del simulador
async function sismo() {
  console.log('sismo: colores del último cálculo real del motor');
  const { page, registro, cerrar } = await pagina({ tema: 'claro' });
  await entrarBIM(page);
  await api(page, 'pestana', 'comportamiento');
  const sin = await api(page, 'comportamiento', 'dc');
  const boton = await page.evaluate(() => !!document.querySelector('.bim-panel [data-pest="comportamiento"] button[data-b="abrir"]'));
  comprobar(sin?.ok === false && sin.motivo === 'sin_calculo' && boton, 'sin cálculo en la sesión, la pestaña ofrece abrir el simulador');
  for (const [p, nombre] of [['nido_2015', 'nido de Bucaramanga 2015'], [{ escenario: 'nido_2015', escala: 'nsr10' }, 'nivel de diseño NSR-10']]) {
    const t0 = Date.now();
    const res = await page.evaluate((p) => window.__torreQA.sismo.calcular(p), p);
    comprobar(res && !res.error && !res.cancelado && res.motor === 'trabajador', `cálculo real (${nombre}) con el motor «${res?.motor}» en ${Date.now() - t0} ms: ${res?.nt} pasos, D/C máx ${res?.dc_max?.toFixed(3)}, ${res?.rotulas} extremos con rótula`);
    await entrarBIM(page);
    const c = await api(page, 'comportamiento', 'dc');
    await cuadros(page);
    // lo esperado, calculado aparte con las envolventes del cálculo y el orden de los elementos del modelo estructural
    const esperado = await page.evaluate(async () => {
      const R = window.__torreQA.sismo.ultimo().resultados, est = await window.__torreQA.datos('sismo_torre_estructura.json');
      const ids = est.bloques.flatMap((b) => b.porticos.flatMap((p) => p.elementos.map((e) => e.id)));
      const k = new Map(ids.map((id, i) => [id, i])), out = { n: 0, max: 0 };
      for (const n of ['CIM', 'P1', 'P2', 'P3', 'P4', 'CUB']) {
        const d = await window.__torreQA.datos(`torre_bim_${n}.json`);
        for (const e of d?.elementos || []) {
          const ks = (e.analisis?.elementos || []).map((x) => k.get(x)).filter((x) => x != null);
          if (!ks.length) continue;
          const v = ks.map((q) => R.envolventes.dc_max[q]);
          out.n++; out.max = Math.max(out.max, v.length === 2 && e.clase === 'IfcColumn' ? (v[0] ** 1.5 + v[1] ** 1.5) ** (1 / 1.5) : Math.max(...v));
        }
      }
      out.deriva = Math.max(...R.envolventes.deriva_vector_max);
      return out;
    });
    comprobar(c?.ok && c.coloreados === esperado.n && Math.abs(c.dc_max - esperado.max) < 1e-6 && Math.abs(c.deriva_max - esperado.deriva) < 1e-9,
      `${nombre}: ${c?.coloreados} elementos coloreados con su D/C (máx ${c?.dc_max?.toFixed(3)} = ${esperado.max.toFixed(3)} de las envolventes) y deriva máx ${(100 * c?.deriva_max).toFixed(3)} %`);
    const e = await estado(page);
    comprobar(e.etiquetas >= 4 && e.leyenda, `${nombre}: deriva de cada entrepiso en una etiqueta y leyenda de D/C`);
    await presupuesto(page, `comportamiento (${nombre})`);
    await foto(page, `bim-sismo-dc-${p.escala || 'escenario'}`);
    const r = await api(page, 'comportamiento', 'rotulas');
    comprobar(r?.ok && r.rotulas === (res?.rotulas ?? -1), `${nombre}: ${r?.rotulas} rótulas dibujadas = ${res?.rotulas} extremos que fluyeron en el cálculo`);
    await foto(page, `bim-sismo-rotulas-${p.escala || 'escenario'}`);
  }
  // «Abrir en el simulador» desde la ficha de una columna
  await api(page, 'seleccionar', 'C-B2-2');
  await page.click('.bim-ficha button[data-acc="sismo"]');
  await esperar(page, () => window.__torreQA.modo() === 'sismo', { ms: 10000 });
  comprobar(await page.evaluate(() => window.__torreQA.modo() === 'sismo'), '«Abrir en el simulador» desde la ficha abre el simulador sísmico');
  comprobar(informar(registro, 'sismo'), 'sismo: consola sin errores ni peticiones fallidas');
  await cerrar();
}

// ---------------------------------------------------------------- selección con el puntero, árbol y buscador
async function seleccion() {
  console.log('seleccion: clic en el modelo, árbol y buscador');
  for (const telefono of [false, true]) {
    const nombre = telefono ? 'teléfono' : 'escritorio';
    const { page, registro, cerrar } = await pagina({ telefono });
    await entrarBIM(page);
    await api(page, 'vistaRapida', 'estructura');
    await cuadros(page);
    // un punto del recuadro sobre la estructura: lo que haya bajo el puntero debe quedar elegido
    const box = await page.evaluate(() => { const r = document.querySelector('#v-torre .stage').getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
    let hecho = false;
    for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.55], [0.55, 0.45], [0.5, 0.6], [0.4, 0.5]]) {
      const x = box.x + fx * box.w, y = box.y + fy * box.h;
      const id = await api(page, 'bloquePorClick', x, y);
      if (!id) continue;
      if (telefono) await page.touchscreen.tap(x, y); else await page.mouse.click(x, y);
      await pausa(300);
      const e = await estado(page);
      comprobar(e.seleccion === id && e.ficha, `${nombre}: tocar el modelo elige el elemento bajo el puntero (${id}: «${e.ficha}»)`);
      hecho = true;
      break;
    }
    if (!hecho) falla(`${nombre}: ningún punto de prueba cae sobre un elemento`);
    // árbol: Estructura → Piso 2 → Columnas → C-B2-2
    await api(page, 'pestana', 'modelo');
    const arbol = await page.evaluate(async () => {
      const q = (s) => document.querySelector(s);
      q('.bim-arbol details[data-ad="EST"]').open = true;
      q('.bim-arbol details[data-ad="EST"] details[data-an="P2"]').open = true;
      const cl = q('.bim-arbol details[data-ac="EST|P2|IfcColumn"]'); cl.open = true;
      await new Promise((r) => setTimeout(r, 100));
      const n = cl.querySelectorAll('.bim-els button[data-el]').length, cuenta = +cl.querySelector('.bim-n').textContent.replace(/\D/g, '');
      cl.querySelector('.bim-els button[data-el="C-B2-2"]').click();
      return { n, cuenta };
    });
    let e = await estado(page);
    comprobar(arbol.n === arbol.cuenta && arbol.n === 28 && e.seleccion === 'C-B2-2', `${nombre}: árbol Estructura → Piso 2 → Columnas lista sus ${arbol.n} elementos (contador ${arbol.cuenta}) y elige C-B2-2`);
    // ocultar una clase desde el árbol
    const v0 = e.visibles;
    await page.evaluate(() => { const i = document.querySelector('.bim-arbol input[data-clase="EST|P2|IfcColumn"]'); i.checked = false; i.dispatchEvent(new Event('change', { bubbles: true })); });
    e = await estado(page);
    comprobar(v0 - e.visibles === 28, `${nombre}: ocultar las columnas del piso 2 desde el árbol quita 28 elementos (${v0} → ${e.visibles})`);
    // disciplina transparente y aislada
    await api(page, 'modoDisciplina', 'CIM', 'aislar');
    e = await estado(page);
    comprobar(e.visibles === 248, `${nombre}: aislar la cimentación deja sus ${e.visibles} elementos`);
    await api(page, 'mostrarTodo');
    // buscador
    await page.fill('.bim-panel input[data-b="buscar"]', 'D-B2');
    await esperar(page, () => document.querySelectorAll('.bim-panel ul.bim-res button[data-el]').length > 0, { ms: 5000 });
    await page.click('.bim-panel ul.bim-res button[data-el="D-B2"]');
    e = await estado(page);
    comprobar(e.seleccion === 'D-B2', `${nombre}: el buscador encuentra y elige el dado D-B2`);
    await foto(page, `bim-seleccion-${telefono ? 'telefono' : 'escritorio'}`);
    comprobar(informar(registro, `seleccion ${nombre}`), `${nombre}: consola sin errores ni peticiones fallidas`);
    await cerrar();
  }
}

// ---------------------------------------------------------------- descarga del IFC
async function ifc() {
  console.log('ifc: descarga de los dos archivos IFC4');
  const { page, registro, cerrar } = await pagina({ tema: 'claro' });
  await entrarBIM(page);
  await api(page, 'pestana', 'ifc');
  const idx = await datos(page, 'torre_bim.json');
  for (const f of idx.ifc) {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.click(`.bim-panel a[data-ifc="${f.archivo}"]`)]);
    const ruta = join(op.salida, `descarga-${dl.suggestedFilename()}`);
    await dl.saveAs(ruta);
    const st = await stat(ruta), cab = (await readFile(ruta)).subarray(0, 4096).toString('latin1');
    comprobar(dl.suggestedFilename() === f.archivo && Math.abs(st.size / 1e6 - f.mb) < 0.02 && /^ISO-10303-21;/.test(cab) && /FILE_SCHEMA\s*\(\s*\(\s*'IFC4'/.test(cab),
      `descarga de ${f.archivo}: ${(st.size / 1e6).toFixed(2)} MB (índice ${f.mb} MB), encabezado ISO-10303-21 y esquema IFC4`);
  }
  await foto(page, 'bim-ifc');
  comprobar(informar(registro, 'ifc'), 'ifc: consola sin errores ni peticiones fallidas');
  await cerrar();
}

// ---------------------------------------------------------------- al salir, los otros modos siguen igual
async function salida() {
  console.log('salida: «Con la torre», el recorrido y el simulador quedan como estaban');
  const { page, registro, cerrar } = await pagina({ tema: 'claro' });
  const foto = () => page.evaluate(() => { const q = window.__torreQA; return { exterior: q.exterior(), modo: q.modo(), seleccionables: q.seleccionables() }; });
  // la base: con los modelos del sitio ya cargados (sus GLB llegan después de los datos) y la cámara en el encuadre de
  // «Con la torre», que es el mismo al que se vuelve al salir del modo
  let prev = -1;
  for (let k = 0; k < 60; k++) { const s = await stats(page); if (s.triangulos > 1000 && s.triangulos === prev) break; prev = s.triangulos; await pausa(1000); }
  await page.evaluate(() => window.__torreQA.modo('torre'));
  await pausa(500); await cuadros(page);
  const antes = { ...(await foto()), stats: await stats(page) };
  await foto(page, 'bim-salida-antes');
  await entrarBIM(page);
  const st0 = await page.evaluate(() => {
    const d = window.__torreQA.bim.api().depurar(), sc = d.st.scene, out = { suelo: [], polar: d.st.controls.maxPolarAngle };
    sc.traverse((o) => { if (o.isMesh && (o.geometry?.type === 'CircleGeometry' || o.name === 'entorno' || o.parent?.name === 'entorno')) out.suelo.push(o.material.uuid); });
    return out;
  });
  await api(page, 'cimentacion', true, 'cortado');
  await api(page, 'verRefuerzo', 'D-B2');
  await api(page, 'cortarNivel', 'P2');
  await api(page, 'pestana', '4d');
  await page.evaluate(() => window.__torreQA.modo('torre'));
  await pausa(500); await cuadros(page);
  const despues = { ...(await foto()), stats: await stats(page) };
  const sueloDespues = await page.evaluate(() => { const d = window.__torreQA.bim.api().depurar(), out = []; d.st.scene.traverse((o) => { if (o.isMesh && (o.geometry?.type === 'CircleGeometry' || o.name === 'entorno' || o.parent?.name === 'entorno')) out.push(o.material.uuid); }); return { suelo: out, enEscena: !!d.grupo.parent, clip: d.renderer.localClippingEnabled, polar: d.st.controls.maxPolarAngle }; });
  comprobar(sueloDespues.clip === false && Math.abs(sueloDespues.polar - st0.polar) < 1e-9, 'el recorte local del renderizador y el límite de la cámara vuelven a como estaban');
  comprobar(despues.exterior === null && despues.modo === 'torre' && despues.seleccionables === antes.seleccionables, `«Con la torre» vuelve con el exterior completo y ${despues.seleccionables} objetos seleccionables (antes ${antes.seleccionables})`);
  comprobar(JSON.stringify(sueloDespues.suelo) === JSON.stringify(st0.suelo) && !sueloDespues.enEscena, 'el suelo y el terreno vuelven a su material original y el modelo BIM sale de la escena');
  comprobar(despues.stats.llamadas === antes.stats.llamadas && despues.stats.triangulos === antes.stats.triangulos, `«Con la torre» dibuja lo mismo que antes de entrar: ${despues.stats.llamadas} llamadas y ${nf(despues.stats.triangulos)} triángulos (antes ${antes.stats.llamadas} y ${nf(antes.stats.triangulos)})`);
  const etqVisibles = await page.evaluate(() => [...document.querySelectorAll('#v-torre .bim-lbl, #v-torre .bim-ancla')].filter((e) => e.offsetParent && getComputedStyle(e.closest('.lbl') || e).display !== 'none').length);
  comprobar(etqVisibles === 0, `ninguna etiqueta del modo BIM queda sobre «Con la torre» (${etqVisibles})`);
  await foto(page, 'bim-salida-despues');
  // el recorrido y el simulador siguen funcionando
  await page.evaluate(() => window.__torreQA.modo('recorrido'));
  const reco = await esperar(page, () => !!window.__torreQA?.recorrido?.estado?.(), { ms: 60000 });
  comprobar(reco, 'el recorrido entra después del modo BIM');
  const res = await page.evaluate(() => window.__torreQA.sismo.calcular('nido_2015'));
  comprobar(res && !res.error && res.nt > 0, `el simulador calcula después del modo BIM (${res?.nt} pasos)`);
  // y de vuelta al modo BIM: sigue donde estaba (sin la cimentación ni el refuerzo, que se cerraron al salir con el 4D)
  await entrarBIM(page);
  await cuadros(page);
  const e = await estado(page);
  comprobar(e.cargado && e.visibles > 0 && e.etiquetas >= 0, `al volver al modo BIM se ve el modelo (${nf(e.visibles)} elementos, vista «${e.vista}»)`);
  await api(page, 'cimentacion', true, 'cortado');
  const e2 = await estado(page);
  comprobar(e2.etiquetas >= 6 && e2.terreno === 'cortado', 'al volver, la cimentación se arma de nuevo con sus etiquetas');
  comprobar(informar(registro, 'salida'), 'salida: consola sin errores ni peticiones fallidas');
  resultado.salida = { antes, despues };
  await cerrar();
}

// ---------------------------------------------------------------- con animaciones
async function movimiento() {
  console.log('movimiento: el modo con vuelos de cámara y el 4D en reproducción');
  const { page, registro, cerrar } = await pagina({ tema: 'oscuro', movimientoReducido: false });
  await entrarBIM(page);
  await api(page, 'verRefuerzo', 'C-B2-2');
  await pausa(1500);
  await api(page, 'cortarEje', 'B');
  await pausa(1500);
  await api(page, 'pestana', '4d');
  await page.click('.bim-hud button[data-b="play4d"]');
  await pausa(2500);
  const e = await estado(page);
  comprobar(e.avance && e.avance.pct > 0, `el 4D se reproduce (avance ${nf(e.avance?.pct)} % en 2,5 s)`);
  await page.click('.bim-hud button[data-b="play4d"]');
  // cambiar de modo en medio de un vuelo no deja nada cruzado
  await api(page, 'verRefuerzo', 'D-B2');
  await page.evaluate(() => window.__torreQA.modo('torre'));
  await pausa(1500);
  comprobar(await page.evaluate(() => window.__torreQA.modo() === 'torre' && window.__torreQA.exterior() === null), 'salir en medio de un vuelo deja «Con la torre» completa');
  comprobar(informar(registro, 'movimiento'), 'movimiento: consola sin errores ni peticiones fallidas');
  await cerrar();
}

const t0 = Date.now();
try {
  if (solo.has('terreno')) await terreno();
  if (solo.has('vistas')) await vistas();
  if (solo.has('sismo')) await sismo();
  if (solo.has('seleccion')) await seleccion();
  if (solo.has('ifc')) await ifc();
  if (solo.has('salida')) await salida();
  if (solo.has('movimiento')) await movimiento();
} catch (e) {
  falla(`excepción: ${e.stack || e}`);
}
await nav.close(); await srv.cerrar();
resultado.fallas = fallas;
resultado.segundos = Math.round((Date.now() - t0) / 1000);
await guardarJSON(op, 'bim_qa.json', resultado);
console.log(fallas.length ? `\n${fallas.length} fallas (informe y capturas en ${op.salida})` : `\nTodo en verde en ${resultado.segundos} s · informe y capturas en ${op.salida}`);
process.exit(fallas.length ? 1 : 0);
