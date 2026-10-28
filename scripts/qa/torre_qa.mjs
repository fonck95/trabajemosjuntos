#!/usr/bin/env node
// QA global de la vista «Torre del hospital» y del resto del sitio (equipo D; especificación de integración 10.1, 13.4,
// 13.6 y 17.7). Complementa, sin repetirlas, las pruebas de cada modo: recorrido_qa.mjs (C), sismo_qa.mjs (D),
// bim_qa.mjs (F), equipos_qa.mjs (C) y scripts/sismo/qa_worker.mjs (A).
//
//   PLAYWRIGHT_MODULE=… node scripts/qa/torre_qa.mjs --vendor <carpeta> [--raiz web|site] [--base /subruta/] [--url <sitio>]
//                       [--salida <carpeta>] [--solo datos,modos,sismo,carrera,vistas,publicado,rendimiento] [--rapido]
//
// Etapas (todas por omisión):
//   · datos (sin navegador): cada archivo de web/data que usan las vistas existe, con sus partes, y pesa menos que su
//     límite del 10.1; ninguno lleva campos internos (origen, ref, fuente_reparto, nota_interna, insumos_sha1…); las
//     huellas (insumos_sha1) de todos los generados están al día, siguiendo la cadena (plantas → inventario → matriz →
//     modelo BIM…); la estructura que publica build_data.py da, con el motor, el mismo cálculo bit a bit que la completa de
//     data/sismo (local_hip al nivel de diseño, con rótulas); «servicio habilitado» no aparece en la web.
//   · modos, en claro y oscuro, escritorio (1400 × 900) y teléfono (390 × 844, táctil): Hoy, Con la torre, la capa
//     Proyecto tipo, Pisos por servicio (planta real, leyenda de 8 grupos, etiquetas dentro del recuadro, tocar un piso),
//     Laboratorio (abre el recorrido en el laboratorio del piso 2), Recorrer por dentro, Simulador sísmico (el primer
//     cálculo real, en el trabajador) y Modelo BIM; en cada uno, presupuesto de dibujo, sin desborde horizontal y sin rutas
//     ni claves internas en el texto visible; al volver a «Con la torre», ningún contenedor de los modos queda a la vista;
//     las tarjetas de abajo (habilitación y contraste) sin textos internos, la Res. 1732 solo como revocada; consola sin
//     errores.
//   · sismo (13.4): nido_2015 y local_hip con el motor real; las 6 gráficas; la cubierta dibujada coincide con cm + u ×
//     escala en todos los pasos; ≤ 60 llamadas y ≤ 150.000 triángulos; un clic donde hay un piso oculto no cambia la ficha;
//     sin Worker, el respaldo en el hilo principal da el mismo resultado y «Cancelar» a la mitad responde en ≤ 300 ms.
//   · carrera (13.4): cambiar de modo en medio de un cálculo o de un vuelo de cámara no deja contenidos de un modo en los
//     contenedores del otro ni mueve la cámara del modo nuevo.
//   · vistas: las otras 9 vistas del sitio en claro, oscuro y teléfono, con su lienzo 3D, sin errores ni desborde.
//   · publicado: el sitio servido como en GitHub Pages (site/ bajo /trabajemosjuntos/, después de build_site.py) o el que
//     diga --url (Caddy con el Caddyfile del repositorio, un despliegue): la vista junta los archivos partidos, el simulador
//     corre en el Worker de módulo y los dos IFC se descargan (ISO-10303-21, IFC4).
//   · rendimiento: prueba de humo en teléfono con la CPU ×4 (CDP): entrar al recorrido, calcular un sismo y abrir el modelo
//     BIM; tiempos y tareas largas en el informe. El trabajador no se frena con la CPU de la página (Chromium solo frena
//     páginas), así que el tiempo del cálculo es el del trabajador; WebGL corre por software, más lento que un teléfono.
// Sale con código 1 si algo falla. Capturas e informe (torre_qa.json) en --salida.
import { opciones, servidor, navegador, abrir, esperar, irAVista, desborde, textosInternos, captura, informe, guardarJSON, RAIZ_REPO } from './comun.mjs';
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

const op = opciones(process.argv.slice(2), { salida: join(tmpdir(), 'atlas_qa', 'torre') });
const ETAPAS = ['datos', 'modos', 'sismo', 'carrera', 'vistas', 'publicado', 'rendimiento'];
const solo = new Set(String(op.solo || ETAPAS.join(',')).split(','));
const fallas = [], resultado = { etapas: {} };
const falla = (txt) => { fallas.push(txt); console.log(`  FALLA ${txt}`); };
const bien = (txt) => console.log(`  ok ${txt}`);
const comprobar = (cond, txt) => { if (cond) bien(txt); else falla(txt); return !!cond; };
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
const cuadros = (page, n = 3) => page.evaluate((n) => new Promise((r) => { let k = 0; const f = () => (++k >= n ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); }), n);
const alRecuadro = (page) => page.evaluate(() => { const e = document.querySelector('#v-torre .stage'), r = e.getBoundingClientRect(); if (r.top < 0 || r.bottom > innerHeight) e.scrollIntoView({ block: 'center' }); });
const stats = (page) => page.evaluate(() => window.__torreQA.stats());
// capturas: con WebGL por software una captura con un vuelo de cámara en curso puede tardar; una que no sale no detiene la QA
const foto = async (page, nombre, o) => { try { await captura(page, op, nombre, { timeout: 60000, ...o }); } catch (e) { console.log(`  (sin captura ${nombre}: ${String(e.message).split('\n')[0]})`); } };
const WEB = join(RAIZ_REPO, 'web'), DATA = join(RAIZ_REPO, 'data');
const COMBOS = op.rapido ? [['claro', false], ['oscuro', true]] : [['claro', false], ['oscuro', false], ['claro', true], ['oscuro', true]];
const nombreCombo = (tema, tel) => `${tema}${tel ? '-telefono' : ''}`;
// presupuestos de dibujo (llamadas por cuadro con todo lo que se ve): «Con la torre» y «Hoy» no tienen cifra en el contrato
// (hoy ≈ 67: el GLB de la torre y el del hospital); el resto, 8.3, 8.8, 13.3 y 17.5
const PRESUPUESTO = { hoy: 90, torre: 90, tipo: 95, pisos: 60, sismo: 60, bim: 60, recorrido: { escritorio: 45, telefono: 30 } };

// ================================================================================================ datos (sin navegador)
const LIMITES_KB = { 'torre.json': 620, 'torre_plantas.json': 500, 'torre_inventario.json': 700, 'torre_habilitacion.json': 300, 'torre_contraste.json': 150,
  'sismo_torre_estructura.json': 250, 'sismo_amenaza.json': 90, 'torre_bim.json': 150, 'torre_bim_interferencias.json': 900 };
const limite = (n) => LIMITES_KB[n] ?? (/^torre_bim_ref_/.test(n) ? 900 : /^torre_bim_/.test(n) ? 1100 : LIMITES_KB[n.replace(/_[^_]+\.json$/, '.json')] ?? null);
const leerJSON = (ruta) => JSON.parse(readFileSync(ruta, 'utf8'));
const sha1 = (ruta) => createHash('sha1').update(readFileSync(ruta)).digest('hex');
// dónde se buscan los insumos que nombra insumos_sha1 (como en build_data.py)
const CARPETAS = ['data/edificios', 'data/proyectos/torre_hospital', 'data/sismo', 'data', 'data/proyectos/torre_hospital/fuentes_investigacion', 'data/sismo/fuentes_investigacion'].map((c) => join(RAIZ_REPO, c));
const rutaInsumo = (n) => (n.includes('/') && existsSync(join(RAIZ_REPO, n)) ? join(RAIZ_REPO, n) : CARPETAS.map((c) => join(c, n)).find((r) => existsSync(r)) || null);
const memo = new Map();
function viejos(ruta, pila = []) {
  if (memo.has(ruta)) return memo.get(ruta);
  let d = null;
  try { d = leerJSON(ruta); } catch { memo.set(ruta, []); return []; }
  const malos = [];
  for (const [n, h] of Object.entries(d?.insumos_sha1 || {})) {
    const r = rutaInsumo(n);
    if (!r) malos.push(`${n} (no se encuentra)`);
    else if (sha1(r) !== h) malos.push(`${n} (cambió)`);
    else if (r.endsWith('.json') && !pila.includes(r) && statSync(r).size < 50e6) { const s = viejos(r, [...pila, ruta]); if (s.length) malos.push(`${n} (desactualizado: ${s.join(', ')})`); }
  }
  memo.set(ruta, malos);
  return malos;
}
function etapaDatos() {
  console.log('\n== datos: archivos de web/data, límites del 10.1, campos internos, huellas y estructura del simulador');
  const r = { archivos: {} };
  const usados = ['torre.json', 'torre_plantas.json', 'torre_inventario.json', 'torre_habilitacion.json', 'torre_contraste.json', 'sismo_torre_estructura.json', 'sismo_amenaza.json',
    'torre_bim.json', 'torre_bim_interferencias.json'];
  const todos = new Set(usados);
  for (const n of usados) {
    const ruta = join(WEB, 'data', n);
    if (!comprobar(existsSync(ruta), `${n} está publicado`)) continue;
    const d = leerJSON(ruta);
    for (const p of d?.partes?.archivos || []) todos.add(p);
    if (n === 'torre_bim.json') for (const grupo of Object.values(d.archivos || {})) for (const p of Object.values(grupo)) todos.add(p);
  }
  const malosKB = [], internos = [];
  for (const n of [...todos].sort()) {
    const ruta = join(WEB, 'data', n);
    if (!existsSync(ruta)) { falla(`${n} falta (lo nombra otro archivo publicado)`); continue; }
    const kb = statSync(ruta).size / 1024, lim = limite(n);
    r.archivos[n] = { kb: Math.round(kb), limite: lim };
    if (lim && kb > lim) malosKB.push(`${n} ${kb.toFixed(0)} KB > ${lim}`);
    // campos internos (10.1): en el BIM, «origen» es un punto de la geometría (lista de números), no una traza
    const pila = [leerJSON(ruta)];
    while (pila.length) {
      const o = pila.pop();
      if (Array.isArray(o)) { for (const x of o) if (x && typeof x === 'object') pila.push(x); continue; }
      for (const [k, v] of Object.entries(o)) {
        if (['ref', 'fuente_reparto', 'nota_interna', 'insumos_sha1', 'sha256_dotacion', 'generado_por'].includes(k) || (k === 'origen' && typeof v === 'string')) internos.push(`${n}: ${k}`);
        if (v && typeof v === 'object') pila.push(v);
      }
    }
  }
  comprobar(!malosKB.length, `${todos.size} archivos dentro de su límite del 10.1${malosKB.length ? `: ${malosKB.join(', ')}` : ''}`);
  comprobar(!internos.length, `sin campos internos en web/data${internos.length ? `: ${[...new Set(internos)].slice(0, 8).join(', ')}` : ''}`);
  // huellas de todos los generados (también los que no van a la web y dan cifras a la vista o a los documentos)
  const generados = ['data/edificios/torre_hospital_plantas.json', 'data/proyectos/torre_hospital/exigencias_3100.json', 'data/proyectos/torre_hospital/inventario_dotacion.json',
    'data/proyectos/torre_hospital/habilitacion.json', 'data/sismo/torre_hospital_estructura.json', 'data/sismo/escenarios.json', 'data/bim/torre_hospital.bim.json',
    'data/bim/interferencias.json', 'data/bim/validacion_ifc.json'];
  for (const g of generados) {
    const ruta = join(RAIZ_REPO, g);
    if (!existsSync(ruta)) { falla(`${g} no existe`); continue; }
    const v = viejos(ruta);
    comprobar(!v.length, `huellas de ${g} al día${v.length ? `: ${v.join('; ')}` : ''}`);
  }
  // la estructura de la web (sin lo descriptivo) da el mismo cálculo bit a bit que la completa
  const caso = (estructura, salida) => spawnSync(process.execPath, [join(RAIZ_REPO, 'scripts/sismo/exportar_caso.mjs'), 'local_hip', salida, '--duracion', op.rapido ? '4' : '8', '--escala', 'nsr10', '--estructura', estructura], { cwd: RAIZ_REPO, encoding: 'utf8' });
  const a = join(op.salida, 'caso_data.json'), b = join(op.salida, 'caso_web.json');
  spawnSync('mkdir', ['-p', op.salida]);
  const ca = caso('data/sismo/torre_hospital_estructura.json', a), cb = caso('web/data/sismo_torre_estructura.json', b);
  if (comprobar(ca.status === 0 && cb.status === 0, 'exportar_caso.mjs corre con la estructura completa y con la publicada')) {
    const sin = (o) => { const { estructura, ...resto } = o; if (resto.motor) delete resto.motor.duracion_calculo_ms; return JSON.stringify(resto); };
    const A = leerJSON(a), B = leerJSON(b);
    comprobar(sin(A) === sin(B), `mismo cálculo bit a bit con las dos (local_hip al nivel de diseño: ${(cb.stdout.match(/motor: (\d+) pasos/) || [])[1] ?? '?'} pasos, ${(cb.stdout.match(/(\d+) elementos con fluencia/) || [])[1] ?? '?'} elementos con fluencia)`);
  } else console.log(ca.stderr, cb.stderr);
  // 13.6: la frase «servicio habilitado» no aparece en la web (datos ni código)
  const conFrase = [];
  for (const dir of ['web/data', 'web/js/scenes', 'web/js/scenes/torre']) for (const f of readdirSync(join(RAIZ_REPO, dir))) {
    const ruta = join(RAIZ_REPO, dir, f);
    if (statSync(ruta).isFile() && /servicio habilitado/i.test(readFileSync(ruta, 'utf8'))) conFrase.push(`${dir}/${f}`);
  }
  if (/servicio habilitado/i.test(readFileSync(join(WEB, 'atlas.html'), 'utf8'))) conFrase.push('web/atlas.html');
  comprobar(!conFrase.length, `«servicio habilitado» no aparece en la web${conFrase.length ? `: ${conFrase.join(', ')}` : ''}`);
  resultado.etapas.datos = r;
}

// ================================================================================================ navegador
const ESPERADOS = [];
let srv = null, nav = null;
async function pagina(o = {}) {
  const r = await abrir(nav, op, { esperados: ESPERADOS, ...o, url: undefined });
  await r.page.goto(`${srv.url}atlas.html?qa=1${o.q || ''}#torre`, { waitUntil: 'load' });
  r.listo = await esperar(r.page, () => window.__torreQA?.listo?.() && document.querySelector('#v-torre canvas.gl'), { ms: 60000 });
  await alRecuadro(r.page);
  return r;
}
// texto visible de la vista con la Res. 1732 sin decir que fue revocada (13.5 y el pedido de esta tarea), por bloque
const sin1732 = (page) => page.evaluate(() => {
  const out = [], w = document.createTreeWalker(document.querySelector('#v-torre'), NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    if (!/1732/.test(n.textContent) || !n.parentElement?.offsetParent) continue;
    // textContent: el texto de un <details> cerrado también cuenta (innerText lo da vacío)
    const b = n.parentElement.closest('p, li, td, dd, dt, summary, small, div, h4, span');
    if (!/revoc/i.test(b?.textContent || '')) out.push((b?.textContent || '').trim().slice(0, 140));
  }
  return out;
});
// contenedores de los modos nuevos: al salir de un modo no queda nada suyo a la vista ni escrito
const contenedores = (page) => page.evaluate(() => {
  const q = (s) => document.querySelector(`[data-slot="${s}"]`);
  const r = {};
  for (const m of ['recorrido', 'sismo', 'bim']) {
    const p = q(`torre.panel.${m}`), h = q(`torre.hud.${m}`);
    r[m] = { panel: !!p && !p.hidden, panelLleno: !!p && p.childElementCount > 0 && !p.hidden, hud: !!h && !h.hidden };
  }
  r.tarjetaSismo = !q('torre.sismo').hidden; r.tarjetaBIM = !!q('torre.bim') && !q('torre.bim').hidden; r.fichaModo = !q('torre.ficha.modo').hidden;
  return r;
});
const nadaDe = (c, menos = null) => Object.entries(c).every(([k, v]) => k === menos || (typeof v === 'object' ? !v.panel && !v.hud : !v));
// etiquetas visibles fuera del recuadro 3D
const etiquetasFuera = (page) => page.evaluate(() => {
  const st = document.querySelector('#v-torre .stage').getBoundingClientRect();
  return [...document.querySelectorAll('#v-torre .stage .lbl-node')].filter((e) => {
    if (!e.offsetParent || getComputedStyle(e).visibility === 'hidden' || +getComputedStyle(e).opacity === 0) return false;
    let p = e; while (p && p !== document.body) { if (p.style?.display === 'none') return false; p = p.parentElement; }
    const r = e.getBoundingClientRect();
    return r.width > 0 && (r.left < st.left - 2 || r.right > st.right + 2 || r.top < st.top - 2 || r.bottom > st.bottom + 2);
  }).map((e) => e.innerText.split('\n')[0]);
});

async function revisarModo(page, nombre, modoQA, tel, extra = {}) {
  await alRecuadro(page);
  await cuadros(page, 3);
  // el primer cuadro después de st.updateShadows() dibuja también el mapa de sombras (una sola vez, no en cada cuadro):
  // el presupuesto se mide en un cuadro corriente
  const s0 = await stats(page), s = await stats(page);
  const lim = typeof PRESUPUESTO[modoQA] === 'object' ? PRESUPUESTO[modoQA][tel ? 'telefono' : 'escritorio'] : PRESUPUESTO[modoQA];
  const d = await desborde(page), internos = await textosInternos(page, '#v-torre');
  // cámara, objetivo y volumen de la sombra finitos: un encuadre con una caja vacía los deja en ∞/NaN y el mapa de sombras
  // se vuelve a dibujar en cada cuadro (el doble de llamadas)
  const finito = await page.evaluate(async () => { const st = (await import(new URL('js/core.js', location.href).href)).engine.active, sc = st.sunLight.shadow.camera; return [...st.camera.position.toArray(), ...st.controls.target.toArray(), sc.left, sc.right, sc.top, sc.bottom].every(Number.isFinite); });
  comprobar(finito, `${nombre}: cámara, objetivo y volumen de la sombra con valores finitos`);
  comprobar(s.llamadas <= lim && d.ok && !internos.length,
    `${nombre}: ${s.llamadas} llamadas (≤ ${lim}) y ${s.triangulos.toLocaleString('es-CO')} triángulos · desborde ${d.ok ? 'no' : `sí (${d.culpables.join(', ')})`} · textos internos ${internos.length ? internos.slice(0, 3).join(' | ') : 'ninguno'}`);
  await foto(page, nombre);
  return { ...s, con_sombras: s0.llamadas, ...extra };
}

async function etapaModos() {
  console.log('\n== modos de la vista de la torre × claro/oscuro × escritorio/teléfono');
  const r = {};
  for (const [tema, tel] of COMBOS) {
    const combo = nombreCombo(tema, tel);
    console.log(`-- ${combo}`);
    // con prefers-reduced-motion (como bim_qa.mjs): sin vuelos de cámara que dejen decenas de cuadros en cola por software;
    // las animaciones se prueban en bim_qa.mjs («movimiento») y en sismo_qa.mjs
    const { page, registro, cerrar, listo } = await pagina({ tema, telefono: tel, movimientoReducido: !op.movimiento });
    if (!comprobar(listo, `${combo}: la vista carga con sus datos`)) { informe(registro, combo); await cerrar(); continue; }
    const rc = r[combo] = {};
    const fichaBase0 = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
    // Hoy y Con la torre
    for (const m of ['hoy', 'torre']) {
      await page.evaluate((m) => window.__torreQA.modo(m), m);
      await pausa(1500);
      rc[m] = await revisarModo(page, `torre-${m}-${combo}`, m, tel);
    }
    // capa «Proyecto tipo»
    await page.click('[data-capa-torre="tipo"]');
    const tipo = await esperar(page, () => [...document.querySelectorAll('#v-torre .stage .lbl-node')].some((e) => e.offsetParent && /tipo/i.test(e.innerText)), { ms: 20000 });
    await pausa(1600);
    comprobar(tipo, `${combo}: la capa «Proyecto tipo» pone la placa del puesto tipo con su etiqueta`);
    rc.tipo = await revisarModo(page, `torre-tipo-${combo}`, 'tipo', tel);
    await page.click('[data-capa-torre="tipo"]');
    // Pisos por servicio (8.8)
    await page.evaluate(() => window.__torreQA.modo('pisos'));
    const armados = await esperar(page, () => { const p = window.__torreQA.pisos(); return p.pisos >= 4 && p.sep > 0.999; }, { ms: 60000 });
    await pausa(1800);   // el encuadre vuela 1,4 s
    const pz = await page.evaluate(() => window.__torreQA.pisos());
    const ley = await page.evaluate(() => { const l = document.querySelector('[data-slot="torre.leyenda"]'); return { n: l.children.length, visible: !l.hidden && getComputedStyle(l).display !== 'none', textos: [...l.children].map((x) => x.textContent) }; });
    comprobar(armados && pz.planta && pz.pisos === 4 && ley.n === 8 && !ley.textos.some((t) => !t.trim()),
      `${combo}: «Pisos por servicio» con la planta real (${pz.pisos} pisos; planta ${pz.planta}) y leyenda de ${ley.n} grupos${ley.visible ? '' : ' (oculta en esta pantalla por espacio)'}`);
    const fuera0 = await etiquetasFuera(page);
    comprobar(!fuera0.length, `${combo}: etiquetas de «Pisos por servicio» dentro del recuadro${fuera0.length ? `: ${fuera0.join(', ')}` : ''}`);
    rc.pisos = await revisarModo(page, `torre-pisos-${combo}`, 'pisos', tel);
    // tocar un piso abre su ficha con sus ambientes
    const c = await page.evaluate(() => { const r = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [r.left + r.width * 0.5, r.top + r.height * 0.5]; });
    if (tel) await page.touchscreen.tap(c[0], c[1]); else await page.mouse.click(c[0], c[1]);
    await pausa(600);
    const fp = await page.evaluate(() => ({ titulo: document.querySelector('[data-slot="torre.ficha.base"] h4')?.textContent || '', filas: document.querySelectorAll('[data-slot="torre.ficha.base"] tbody tr').length, elegido: window.__torreQA.pisos().elegido }));
    comprobar(/^Piso \d/.test(fp.titulo) && fp.filas > 0 && fp.elegido != null, `${combo}: tocar un piso abre su ficha («${fp.titulo}», ${fp.filas} ambientes)`);
    await alRecuadro(page); await cuadros(page, 3);
    const fuera1 = await etiquetasFuera(page);
    comprobar(!fuera1.length, `${combo}: con un piso elegido, sus etiquetas quedan dentro del recuadro${fuera1.length ? `: ${fuera1.join(', ')}` : ''}`);
    await foto(page, `torre-pisos-elegido-${combo}`);
    // Laboratorio → recorrido parado en la puerta del laboratorio del piso 2
    await page.click('[data-modo-torre="laboratorio"]');
    const enLab = await esperar(page, () => !!window.__torreQA.recorrido.estado(), { ms: 90000 });
    await pausa(800);
    const lab = await page.evaluate(async () => {
      const e = window.__torreQA.recorrido.estado(), pl = await window.__torreQA.datos('torre_plantas.json');
      const r = pl?.niveles?.find((n) => n.id === e?.nivel)?.recintos?.find((x) => x.id === e?.recinto);
      return { modo: window.__torreQA.modo(), nivel: e?.nivel, recinto: r ? `${r.servicio_programa || ''}: ${r.ambiente || r.id}` : e?.recinto, en_muro: e?.en_muro,
        pulsado: document.querySelector('[data-modo-torre="laboratorio"]').getAttribute('aria-pressed') };
    });
    comprobar(enLab && lab.modo === 'recorrido' && lab.nivel === 'P2' && /laborat/i.test(lab.recinto || '') && lab.en_muro === false && lab.pulsado === 'true',
      `${combo}: «Laboratorio» abre el recorrido en el piso 2, en «${(lab.recinto || '').slice(0, 70)}», con el botón pulsado`);
    rc.laboratorio = await revisarModo(page, `torre-laboratorio-${combo}`, 'recorrido', tel);
    // Recorrer por dentro (desde «Con la torre», en la entrada)
    await page.evaluate(() => window.__torreQA.modo('torre'));
    await pausa(500);
    await page.evaluate(() => window.__torreQA.modo('recorrido'));
    const enReco = await esperar(page, () => !!window.__torreQA.recorrido.estado(), { ms: 90000 });
    await pausa(800);
    const er = await page.evaluate(() => window.__torreQA.recorrido.estado());
    comprobar(enReco && er && er.en_muro === false, `${combo}: «Recorrer por dentro» entra en ${er?.nivel} sin quedar en un muro`);
    rc.recorrido = await revisarModo(page, `torre-recorrido-${combo}`, 'recorrido', tel);
    // Simulador sísmico: el primer cálculo (nido_2015) con el motor real en el trabajador
    const t0 = Date.now();
    await page.evaluate(() => window.__torreQA.modo('sismo'));
    const calc = await esperar(page, () => !!window.__torreQA.sismo.ultimo(), { ms: 180000 });
    await pausa(800);
    const u = await page.evaluate(() => { const u = window.__torreQA.sismo.ultimo(); return u && { motor: window.__torreQA.sismo.motor(), nt: u.nt, dc: u.dc_max, deriva: u.deriva_vector_max, graficas: document.querySelectorAll('[data-slot="torre.sismo.graficas"] svg.mr-chart').length }; });
    comprobar(calc && u?.motor === 'trabajador' && u.nt > 0 && u.graficas >= 6,
      `${combo}: el simulador calcula el escenario por defecto en el trabajador (${u?.nt} pasos, D/C máx ${u?.dc?.toFixed?.(2)}, deriva ${(100 * (u?.deriva || 0)).toFixed(3)} %, ${u?.graficas} gráficas, ${((Date.now() - t0) / 1000).toFixed(1)} s)`);
    rc.sismo = await revisarModo(page, `torre-sismo-${combo}`, 'sismo', tel, { calculo_s: (Date.now() - t0) / 1000 });
    // Modelo BIM
    const t1 = Date.now();
    await page.evaluate(() => window.__torreQA.modo('bim'));
    const bim = await esperar(page, () => window.__torreQA.bim?.api?.()?.estado?.().cargado, { ms: 120000 });
    await pausa(1500);
    const eb = await page.evaluate(() => { const e = window.__torreQA.bim.api().estado(); return { elementos: e.elementos, vista: e.vista, relleno: window.__torreQA.relleno('bim') }; });
    comprobar(bim && eb.elementos > 0 && eb.relleno === false, `${combo}: el modelo BIM carga (${eb.elementos} elementos, ${((Date.now() - t1) / 1000).toFixed(1)} s)`);
    rc.bim = await revisarModo(page, `torre-bim-${combo}`, 'bim', tel);
    // de vuelta en «Con la torre»: nada de los modos a la vista, la selección del Stage de vuelta, el exterior completo
    await page.evaluate(() => window.__torreQA.modo('torre'));
    await pausa(1500);
    const cont = await contenedores(page), vuelta = await page.evaluate(() => ({ exterior: window.__torreQA.exterior(), sel: window.__torreQA.seleccionables(), ficha: !document.querySelector('[data-slot="torre.ficha.base"]').hidden, tiles: !document.querySelector('[data-slot="torre.tiles"]').hidden }));
    const fichaBase1 = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
    comprobar(nadaDe(cont) && vuelta.exterior === null && vuelta.sel > 0 && vuelta.ficha && vuelta.tiles && fichaBase1 === fichaBase0,
      `${combo}: al volver a «Con la torre» no queda nada de los modos (${JSON.stringify(cont).slice(0, 160)}), el exterior está completo, la ficha es la original y hay ${vuelta.sel} objetos seleccionables`);
    rc.torre_vuelta = await revisarModo(page, `torre-vuelta-${combo}`, 'torre', tel);
    // tarjetas de abajo (se cargan al acercarse): habilitación y contraste, sin textos internos y con la Res. 1732 revocada
    for (const s of ['torre.habilitacion', 'torre.tipo']) { await page.evaluate((s) => document.querySelector(`[data-slot="${s}"]`).scrollIntoView({ block: 'center' }), s); await pausa(1200); }
    const tarjetas = await esperar(page, () => document.querySelector('[data-slot="torre.habilitacion"]').innerText.length > 200 && document.querySelector('[data-slot="torre.tipo"]').innerText.length > 200, { ms: 30000 });
    const internosT = await textosInternos(page, '#v-torre'), r1732 = await sin1732(page), dT = await desborde(page);
    comprobar(tarjetas && !internosT.length && !r1732.length && dT.ok,
      `${combo}: tarjetas de habilitación y contraste cargadas, sin textos internos${internosT.length ? ` (${internosT.slice(0, 3).join(' | ')})` : ''}, la Res. 1732 siempre como revocada${r1732.length ? ` (falla en: ${r1732.slice(0, 2).join(' | ')})` : ''} y sin desborde`);
    comprobar(informe(registro, `torre ${combo}`), `${combo}: consola sin errores`);
    await cerrar();
  }
  resultado.etapas.modos = r;
}

// ================================================================================================ sismo (13.4)
async function etapaSismo() {
  console.log('\n== sismo (13.4): motor real, gráficas, cubierta dibujada, presupuesto, clic, respaldo sin Worker y cancelar');
  const r = {};
  const resumen = (page) => page.evaluate(() => { const u = window.__torreQA.sismo.ultimo(), R = u.resultados; let s = 0; for (let i = 0; i < R.u.length; i++) s += R.u[i]; return { motor: window.__torreQA.sismo.motor(), nt: u.nt, dc: u.dc_max, deriva: u.deriva_vector_max, suma_u: s, rotulas: u.rotulas }; });
  {
    const { page, registro, cerrar, listo } = await pagina({ movimientoReducido: true });
    comprobar(listo, 'la vista carga');
    await page.evaluate(() => window.__torreQA.modo('pisos'));       // los pisos quedan armados (y ocultos en el simulador)
    await esperar(page, () => window.__torreQA.pisos().pisos >= 4, { ms: 60000 });
    const fichaBase = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
    for (const esc of ['nido_2015', 'local_hip']) {
      const t0 = Date.now();
      const res = await page.evaluate((e) => window.__torreQA.sismo.calcular({ escenario: e }), esc);
      await pausa(600);
      const info = await page.evaluate(() => {
        const Q = window.__torreQA, u = Q.sismo.ultimo();
        let err = 0;
        for (let i = 0; i < u.nt; i++) { const a = Q.sismo.cubiertaDibujada(i), b = u.cubiertaEsperada(i); err = Math.max(err, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])); }
        const g = [...document.querySelectorAll('[data-slot="torre.sismo.graficas"] svg.mr-chart')];
        Q.stats();   // un cuadro con el mapa de sombras pendiente, si lo hay; se mide el siguiente
        return { nt: u.nt, err, graficas: g.length, vacias: g.filter((s) => !s.querySelector('path')).length, motor: Q.sismo.motor(), stats: Q.stats(),
          honestidad: document.querySelector('#v-torre').innerText.includes('Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado)'), sel: Q.seleccionables() };
      });
      r[esc] = { ...info, ms: Date.now() - t0 };
      comprobar(res && !res.error && info.motor === 'trabajador' && info.graficas >= 6 && !info.vacias && info.err < 1e-4 && info.stats.llamadas <= 60 && info.stats.triangulos <= 150000 && info.honestidad && info.sel === 0,
        `${esc}: ${info.nt} pasos en el trabajador (${((Date.now() - t0) / 1000).toFixed(1)} s); ${info.graficas} gráficas; cubierta dibujada = cm + u × escala en los ${info.nt} pasos (error ${info.err.toExponential(1)} m); ${info.stats.llamadas} llamadas y ${info.stats.triangulos.toLocaleString('es-CO')} triángulos; texto de honestidad; ${info.sel} seleccionables del Stage`);
    }
    // un clic (o toque) donde hay un piso oculto de «Pisos por servicio» no cambia la ficha de siempre
    const pts = await page.evaluate(() => { const r = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [[0.3, 0.7], [0.5, 0.5], [0.6, 0.35], [0.45, 0.8]].map(([fx, fy]) => [r.left + r.width * fx, r.top + r.height * fy]); });
    for (const [x, y] of pts) { await page.mouse.click(x, y); await pausa(150); }
    comprobar(await page.evaluate((f) => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML === f, fichaBase), '4 clics sobre los pisos ocultos no cambian la ficha de siempre');
    r.con_trabajador = await resumen(page);
    comprobar(informe(registro, 'sismo con trabajador'), 'consola sin errores');
    await cerrar();
  }
  {
    // respaldo sin Worker: mismo resultado que el trabajador y «Cancelar» a la mitad en ≤ 300 ms
    const { page, registro, cerrar } = await pagina({ sinWorker: true, movimientoReducido: true });
    await page.evaluate(() => window.__torreQA.sismo.calcular({ escenario: 'local_hip' }));
    const sinW = await resumen(page);
    const con = r.con_trabajador;
    comprobar(sinW.motor === 'hilo_principal' && sinW.nt === con.nt && sinW.suma_u === con.suma_u && sinW.dc === con.dc && sinW.deriva === con.deriva,
      `sin Worker: motor «${sinW.motor}» y el mismo resultado que el trabajador (${sinW.nt} pasos, D/C ${sinW.dc?.toFixed(4)} = ${con.dc?.toFixed(4)}, Σu igual: ${sinW.suma_u === con.suma_u})`);
    const c = await page.evaluate(async () => {
      const p = window.__torreQA.sismo.calcular({ escenario: 'nido_2015' });
      let f = 0;
      for (let k = 0; k < 800 && f < 0.3; k++) { await new Promise((ok) => setTimeout(ok, 25)); f = +document.querySelector('[data-o="progreso"]')?.value || 0; }
      const t = performance.now(); document.querySelector('[data-s="cancelar"]').click(); const res = await p;
      return { f, ms: performance.now() - t, cancelado: !!res?.cancelado, estado: document.querySelector('[data-o="estado"]').textContent };
    });
    r.cancelar = c;
    comprobar(c.cancelado && c.ms <= 300, `«Cancelar» con ${(100 * c.f).toFixed(0)} % hecho en el hilo principal responde en ${c.ms.toFixed(0)} ms (≤ 300): «${c.estado}»`);
    comprobar(informe(registro, 'sismo sin Worker'), 'consola sin errores');
    await cerrar();
  }
  resultado.etapas.sismo = r;
}

// ================================================================================================ carrera (13.4)
async function etapaCarrera() {
  console.log('\n== carrera: cambiar de modo en medio de un cálculo, de una carga o de un vuelo de cámara');
  const { page, registro, cerrar } = await pagina({});
  const r = {};
  // en medio de un cálculo del simulador → modelo BIM: nada del simulador queda en sus contenedores
  await page.evaluate(() => window.__torreQA.modo('sismo'));
  await esperar(page, () => !!window.__torreQA.sismo.ultimo(), { ms: 180000 });
  await page.evaluate(() => { window.__torreQA.sismo.calcular({ escenario: 'local_hip' }); });
  await esperar(page, () => (+document.querySelector('[data-o="progreso"]')?.value || 0) > 0.05, { ms: 30000 });
  await page.evaluate(() => window.__torreQA.modo('bim'));
  await esperar(page, () => window.__torreQA.bim?.api?.()?.estado?.().cargado, { ms: 120000 });
  await pausa(4000);   // lo que le faltaba al cálculo
  const c1 = await contenedores(page);
  r.calculo_a_bim = c1;
  comprobar(c1.bim.panel && !c1.sismo.panel && !c1.sismo.panelLleno && !c1.sismo.hud && !c1.tarjetaSismo,
    `cálculo a la mitad → «Modelo BIM»: panel del BIM a la vista; panel, HUD y tarjeta del simulador ocultos y vacíos (${JSON.stringify(c1.sismo)})`);
  // en medio de la carga del recorrido → simulador → «Con la torre» (turnos): gana el último pedido
  await page.evaluate(() => { window.__torreQA.modo('recorrido'); window.__torreQA.modo('sismo'); return window.__torreQA.modo('torre'); });
  await pausa(5000);
  const c2 = await contenedores(page), m2 = await page.evaluate(() => window.__torreQA.modo());
  r.turnos = { modo: m2, ...c2 };
  comprobar(m2 === 'torre' && nadaDe(c2), `tres cambios seguidos (recorrido, simulador, «Con la torre»): queda «${m2}» sin contenedores de los otros a la vista`);
  // en medio del vuelo de cámara de «Pisos por servicio» → recorrido: la cámara es la del caminante
  await page.evaluate(() => window.__torreQA.modo('pisos'));
  await pausa(300);
  await page.evaluate(() => window.__torreQA.modo('recorrido'));
  await esperar(page, () => !!window.__torreQA.recorrido.estado(), { ms: 90000 });
  await pausa(2500);
  const cam = await page.evaluate(async () => {
    const core = await import(new URL('js/core.js', location.href).href), st = core.engine.active, e = window.__torreQA.recorrido.estado();
    return { fov: st.camera.fov, x: st.camera.position.x, z: st.camera.position.z, px: e.posicion[0], py: e.posicion[1], en_muro: e.en_muro };
  });
  r.vuelo_a_recorrido = cam;
  comprobar(Math.hypot(cam.x - cam.px, -cam.z - cam.py) < 0.6 && cam.fov > 40 && !cam.en_muro,
    `vuelo de «Pisos por servicio» → recorrido: la cámara queda en los ojos del caminante (a ${Math.hypot(cam.x - cam.px, -cam.z - cam.py).toFixed(2)} m; campo vertical ${cam.fov.toFixed(0)}°)`);
  // y de vuelta en «Con la torre» todo como al principio
  await page.evaluate(() => window.__torreQA.modo('torre'));
  await pausa(1500);
  const c3 = await contenedores(page), cam2 = await page.evaluate(async () => (await import(new URL('js/core.js', location.href).href)).engine.active.camera.fov);
  comprobar(nadaDe(c3) && Math.abs(cam2 - 36) < 0.01, `de vuelta en «Con la torre»: sin contenedores de los modos y campo de 36° (${cam2})`);
  comprobar(informe(registro, 'carrera'), 'consola sin errores');
  await cerrar();
  resultado.etapas.carrera = r;
}

// ================================================================================================ las otras 9 vistas
async function etapaVistas() {
  console.log('\n== las otras vistas del sitio: lienzo 3D, consola y desborde');
  const r = {};
  for (const [tema, tel] of COMBOS) {
    const combo = nombreCombo(tema, tel);
    const { page, registro, cerrar } = await abrir(nav, op, { url: `${srv.url}atlas.html#dinero`, tema, telefono: tel, esperados: ESPERADOS });
    const vistas = await page.evaluate(() => [...document.querySelectorAll('nav.tabs a[data-view]')].map((a) => a.dataset.view).filter((v) => v !== 'torre'));
    if (!comprobar(vistas.length === 9, `${combo}: el sitio tiene 9 vistas además de la torre (${vistas.join(', ')})`)) { await cerrar(); continue; }
    for (const v of vistas) {
      const e0 = registro.errores.length, f0 = registro.fallidas.length;
      const visto = await irAVista(page, v, { ms: 30000 });
      await pausa(op.rapido ? 1500 : 3000);
      const d = await desborde(page);
      const errores = [...registro.errores.slice(e0), ...registro.fallidas.slice(f0)];
      const finito = await page.evaluate(async () => { const st = (await import(new URL('js/core.js', location.href).href)).engine.active, sc = st?.sunLight?.shadow?.camera; return !st || [...st.camera.position.toArray(), ...st.controls.target.toArray(), ...(sc ? [sc.left, sc.right, sc.top, sc.bottom] : [])].every(Number.isFinite); });
      (r[combo] ||= {})[v] = { lienzo: visto, desborde: !d.ok, errores: errores.length, finito };
      comprobar(visto && d.ok && !errores.length && finito, `${combo} · ${v}: lienzo 3D ${visto ? 'sí' : 'no'} · desborde ${d.ok ? 'no' : `sí (${d.culpables.slice(0, 3).join(', ')})`} · errores ${errores.length ? errores.slice(0, 2).join(' | ') : 0}${finito ? '' : ' · cámara o sombra con valores no finitos'}`);
      await foto(page, `vista-${v}-${combo}`);
    }
    informe(registro, `vistas ${combo}`);
    await cerrar();
  }
  resultado.etapas.vistas = r;
}

// ================================================================================================ sitio publicado
async function etapaPublicado() {
  // por omisión, site/ bajo /trabajemosjuntos/ (GitHub Pages); con --url, el que esté servido allí (Caddy, Railway)
  const externo = typeof op.url === 'string';
  const sop = externo ? op : { ...op, raiz: 'site', raizAbs: resolve(RAIZ_REPO, 'site'), base: '/trabajemosjuntos/' };
  if (!externo && !comprobar(existsSync(join(RAIZ_REPO, 'site/atlas.html')), 'site/ está construido (python3 scripts/build_site.py)')) return;
  const s2 = await servidor(sop);
  console.log(`\n== publicado: ${s2.url}`);
  const r = { url: s2.url };
  const { page, registro, cerrar } = await abrir(nav, sop, { url: `${s2.url}atlas.html?qa=1#torre` });
  const listo = await esperar(page, () => window.__torreQA?.listo?.() && document.querySelector('#v-torre canvas.gl'), { ms: 60000 });
  const doc = await page.evaluate(() => document.compatMode);
  comprobar(listo && doc === 'CSS1Compat', `la vista de la torre carga (modo del documento ${doc})`);
  // archivos partidos juntos, como los recibe cada modo
  const d = await page.evaluate(async () => {
    const Q = window.__torreQA, [pl, inv, hab, est, bim] = await Promise.all(['torre_plantas.json', 'torre_inventario.json', 'torre_habilitacion.json', 'sismo_torre_estructura.json', 'torre_bim.json'].map((f) => Q.datos(f)));
    return { niveles: pl?.niveles?.length, unidades: inv?.unidades?.length, implementos: Object.keys(inv?.implementos || {}).length, servicios: hab?.servicios?.length, bloques: est?.bloques?.length, ifc: bim?.ifc?.length };
  });
  r.datos = d;
  comprobar(d.niveles === 7 && d.unidades > 1000 && d.implementos > 0 && d.servicios > 10 && d.bloques >= 1 && d.ifc === 2, `datos con sus partes juntas: ${JSON.stringify(d)}`);
  // el simulador en el Worker de módulo
  await alRecuadro(page);
  const res = await page.evaluate(() => window.__torreQA.sismo.calcular({ escenario: 'nido_2015' }));
  const motor = await page.evaluate(() => window.__torreQA.sismo.motor());
  r.motor = motor;
  comprobar(res && !res.error && motor === 'trabajador', `el simulador calcula en el Worker de módulo (motor «${motor}», ${res?.nt} pasos)`);
  // descarga de los IFC desde la pestaña del modelo BIM
  await page.evaluate(() => window.__torreQA.modo('bim'));
  await esperar(page, () => window.__torreQA.bim?.api?.()?.estado?.().cargado, { ms: 120000 });
  await page.evaluate(() => window.__torreQA.bim.api().pestana('ifc'));
  await pausa(500);
  const ifc = await page.evaluate(async () => Promise.all([...document.querySelectorAll('a.bim-descarga')].map(async (a) => {
    const rr = await fetch(a.href), b = await rr.arrayBuffer(), cab = new TextDecoder().decode(b.slice(0, 2000));
    return { archivo: a.getAttribute('download'), url: a.href, estado: rr.status, mb: +(b.byteLength / 1048576).toFixed(2), iso: cab.startsWith('ISO-10303-21;'), ifc4: /FILE_SCHEMA\s*\(\s*\(\s*'IFC4'\s*\)\s*\)/.test(cab), tipo: rr.headers.get('content-type') };
  })));
  r.ifc = ifc;
  comprobar(ifc.length === 2 && ifc.every((f) => f.estado === 200 && f.iso && f.ifc4 && f.mb > 1), `descarga de los IFC: ${ifc.map((f) => `${f.archivo} ${f.mb} MB (${f.estado}, ${f.tipo || 'sin tipo'}${f.iso && f.ifc4 ? ', ISO-10303-21 IFC4' : ', encabezado inválido'})`).join(' · ')}`);
  comprobar(informe(registro, `publicado ${s2.url}`), 'consola sin errores');
  await captura(page, sop, `publicado-${externo ? 'url' : 'subruta'}`);
  await cerrar(); await s2.cerrar();
  resultado.etapas[`publicado${externo ? '_url' : '_subruta'}`] = r;
}

// ================================================================================================ rendimiento en teléfono
async function etapaRendimiento() {
  console.log('\n== rendimiento: teléfono (390 × 844) con la CPU ×4 — entrar al recorrido, calcular un sismo y abrir el modelo BIM');
  const r = {};
  const { page, contexto, registro, cerrar } = await abrir(nav, op, { telefono: true, esperados: ESPERADOS });
  const cdp = await contexto.newCDPSession(page);
  await page.addInitScript(() => { window.__largas = []; try { new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__largas.push([Math.round(e.startTime), Math.round(e.duration)]))).observe({ type: 'longtask', buffered: true }); } catch { /* sin longtask */ } });
  // el freno se mide en una página vacía: la misma cuenta antes y después de pedirlo (debe tardar ≈ 4 veces más)
  await page.goto('about:blank');
  const cuenta = () => page.evaluate(() => { const t = performance.now(); let x = 0; for (let i = 0; i < 3e7; i++) x += Math.sqrt(i); return [performance.now() - t, x]; });
  const [ms1] = await cuenta();
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  const [ms4] = await cuenta();
  r.freno = +(ms4 / ms1).toFixed(2);
  comprobar(r.freno > 2.5, `la CPU de la página va frenada: la misma cuenta tarda ${r.freno} veces más (${ms1.toFixed(0)} → ${ms4.toFixed(0)} ms)`);
  const t0 = Date.now();
  await page.goto(`${srv.url}atlas.html?qa=1#torre`, { waitUntil: 'load' });
  const listo = await esperar(page, () => window.__torreQA?.listo?.() && document.querySelector('#v-torre canvas.gl'), { ms: 180000 });
  r.carga_s = (Date.now() - t0) / 1000;
  await alRecuadro(page);
  const tramo = async (nombre, fn, cond, ms = 240000) => {
    const ini = await page.evaluate(() => performance.now()), t = Date.now();
    await page.evaluate(fn);
    const ok = await esperar(page, cond, { ms });
    await cuadros(page, 3);
    const lt = await page.evaluate((ini) => { const L = window.__largas.filter(([s]) => s >= ini); return { n: L.length, max: Math.max(0, ...L.map(([, d]) => d)), total: L.reduce((a, [, d]) => a + d, 0) }; }, ini);
    const s = await stats(page);
    r[nombre] = { ok, s: (Date.now() - t) / 1000, largas: lt, llamadas: s.llamadas };
    return r[nombre];
  };
  const a = await tramo('recorrido', () => window.__torreQA.modo('recorrido'), () => !!window.__torreQA.recorrido.estado());
  await pausa(1000);
  const b = await tramo('sismo', () => window.__torreQA.modo('sismo'), () => !!window.__torreQA.sismo.ultimo());
  const calc = await page.evaluate(() => window.__torreQA.sismo.ultimo()?.duracion_ms);
  await pausa(1000);
  const c = await tramo('bim', () => window.__torreQA.modo('bim'), () => window.__torreQA.bim?.api?.()?.estado?.().cargado);
  r.sismo.calculo_trabajador_ms = calc;
  await foto(page, 'rendimiento-telefono-cpu4-bim');
  const linea = (n, x) => `${n} en ${x.s.toFixed(1)} s (${x.largas.n} tareas largas, la mayor de ${x.largas.max} ms, ${x.llamadas} llamadas)`;
  console.log(`  carga de la vista ${r.carga_s.toFixed(1)} s · ${linea('recorrido', a)} · ${linea('sismo', b)} (el cálculo en el trabajador: ${calc} ms) · ${linea('modelo BIM', c)}`);
  comprobar(listo && a.ok && b.ok && c.ok && r.carga_s < 120 && a.s < 120 && b.s < 180 && c.s < 180, 'los tres pasos terminan con la CPU ×4 (límites de humo: 2 min para cargar y entrar al recorrido, 3 min para el sismo y el BIM)');
  comprobar(informe(registro, 'rendimiento teléfono ×4'), 'consola sin errores');
  await cerrar();
  resultado.etapas.rendimiento = r;
}

// ================================================================================================ corrida
if (solo.has('datos')) etapaDatos();
const conNavegador = [...solo].some((e) => e !== 'datos');
if (conNavegador) {
  if (!op.vendor) { console.error('Falta --vendor <carpeta> con three/ y gsap/ (ver scripts/qa/LEEME.md)'); process.exit(2); }
  srv = await servidor(op); nav = await navegador(op);
  console.log(`sitio: ${srv.url}${srv.externo ? ' (externo)' : ` (${op.raiz})`}`);
  const etapas = { modos: etapaModos, sismo: etapaSismo, carrera: etapaCarrera, vistas: etapaVistas, publicado: etapaPublicado, rendimiento: etapaRendimiento };
  for (const [nombre, fn] of Object.entries(etapas)) {
    if (!solo.has(nombre)) continue;
    try { await fn(); } catch (e) { falla(`etapa ${nombre}: ${e.stack || e}`); }
  }
  await nav.close(); await srv.cerrar();
}
resultado.fallas = fallas;
const ruta = await guardarJSON(op, 'torre_qa.json', resultado);
console.log(`\n${fallas.length ? `QA de la torre con ${fallas.length} fallas` : 'QA de la torre sin fallas'} · informe: ${ruta}`);
process.exit(fallas.length ? 1 : 0);
