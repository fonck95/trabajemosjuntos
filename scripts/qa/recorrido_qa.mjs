#!/usr/bin/env node
// QA del recorrido en primera persona de la torre (equipo C; contrato de integración 6, 13.3 y 16.6).
//
//   PLAYWRIGHT_MODULE=… node scripts/qa/recorrido_qa.mjs --vendor <carpeta> [--salida <carpeta>] [--solo niveles,alcance,unidades,guion,juego,flujo,teclado,presupuesto,salida]
//
// Sirve web/ con scripts/qa/comun.mjs (three y GSAP locales con --vendor), abre index.html?qa=1#torre en Chromium sin pantalla
// (WebGL por software) y recorre la torre con el teclado y los ganchos __torreQA y __recorridoQA:
//   · niveles: entra al recorrido y captura cada nivel (exteriores, pisos 1 a 4, bloque técnico y cubierta) en claro, oscuro
//     y teléfono (390 × 844, táctil): consola sin errores, sin desborde horizontal, etiquetas dentro del recuadro, el minimapa
//     no tapa «Rendimiento» y la barra no tapa el joystick; cada botón de la barra cabe en ella sin tocar «Rendimiento» y el
//     recinto actual se lee sobre el recuadro; textos sin rutas ni claves internas; ninguna vista sale de un solo color (un
//     punto de vista pegado a un muro). Los pisos 2 a 4 y la cubierta miran desde una entrada del recorrido de la planta.
//   · alcance: recorrido en anchura sobre la rejilla de colisión de cada nivel desde sus entradas, pasos, ascensores y
//     escaleras: falla si queda un recinto transitable al que no se llega caminando (16.1).
//   · unidades: «Ir a» cada una de las unidades de la torre y un clic en el punto que dejó a la vista: debe seleccionarla (o
//     a su contenedor); las que ningún lugar deja ver por su ubicación en los datos se listan aparte.
//   · guion: camina con teclas por los 4 pisos, los exteriores, el bloque técnico y la cubierta sin quedar en un muro; cruza
//     la puerta principal (exteriores → piso 1); sube y baja una escalera caminando; sube la escalera principal abierta;
//     los costados de las escaleras y los descansos altos que dan a un piso (la escalera principal, abierta al vestíbulo)
//     lo detienen como un muro, quieto cerca del borde y sin subirlo a ellos; en todas las juntas entre descanso y tramo de
//     todas las escaleras el carril de la rejilla es continuo y el caminante pasa sin trabarse, subiendo y bajando, a lo
//     ancho del carril (bordes junto al ojo y al muro incluidos) y a ±15° del eje, y con teclas sube la escalera principal
//     desde el muro del descanso; sale del piso 4 a la terraza y vuelve; cambia de piso en el ascensor;
//     la baranda del hueco de la escalera abierta del piso 2 lo detiene como un muro y solo se entra en él bajando; la
//     entrada del botón «Laboratorio» está libre, en la puerta y se cruza; abre las fichas del carro de paro (implementos),
//     de un analizador en comodato (reactivos), de un panel solar, del manifold de gases y de un lavamanos; usa «Ir a»
//     desde el buscador; cámara (plano cercano, rumbo tras 60 cuadros, campo horizontal) y selección (clic en muro,
//     arrastre). La escalera principal y sus costados, la terraza, el hueco y la entrada del laboratorio toman sus puntos y
//     metas de la planta publicada (escaleras[].partes, pasos_entre_niveles, obstaculos_recorrido y entradas_recorrido), no
//     de cifras fijas.
//   · juego: entra caminando desde el corredor a la escalera de evacuación norte del piso 2 (por su puerta); salta (los
//     pies suben ≈ 1,2 m y vuelven al piso; bajo un dintel se detiene) y queda parado sobre una cama y sobre una fila de
//     paneles de la terraza; el modo espectador (V) sube con Espacio a través
//     de la losa al piso 3, vuela en línea recta por donde no se camina y al volver a caminar queda en una celda libre del
//     piso; pantalla completa (P): el recuadro ocupa la ventana, la ficha pasa a su lateral y Esc devuelve todo.
//   · flujo: botón «Laboratorio», ficha a la vista tras tocar un equipo (y «Ver ficha» en el teléfono), «Ir a» desde el
//     buscador y desde «Ir a otro lugar» con el recuadro a la vista y el foco, reactivos en el buscador, faltantes con su
//     capa, tarjeta de habilitación con recintos y propuestas aparte, y torre.json tarde sin pisos en la selección.
//   · teclado: solo teclado (botón → recuadro → flechas → Tab al panel → Enter abre una ficha), atajos del navegador sin
//     interceptar, escribir en el buscador no mueve, perder el foco detiene; con prefers-reduced-motion, saltos sin fundido.
//   · presupuesto: llamadas de dibujo y triángulos de cada nivel (5.2 y 16.6): baja en 390 × 844 y media en 1400 × 900.
//   · salida: al salir, fov 36° y controles como antes, y «Con la torre» se ve igual que antes de entrar (cada captura con el
//     cuadro ya quieto, no tras una espera fija, y a la misma resolución adaptativa del motor).
// Sale con código 1 si algo falla. Las capturas y el informe (recorrido_qa.json) quedan en --salida.
import { opciones, servidor, navegador, abrir, esperar, desborde, textosInternos, captura, informe, guardarJSON } from './comun.mjs';

const op = opciones(process.argv.slice(2));
const solo = new Set(String(op.solo || 'niveles,alcance,unidades,guion,juego,flujo,teclado,presupuesto,salida').split(','));
const NIVELES = ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB'];
const fallas = [], resultado = {};
const falla = (txt) => { fallas.push(txt); console.log(`  FALLA ${txt}`); };
const bien = (txt) => console.log(`  ok ${txt}`);
const comprobar = (cond, txt) => { if (cond) bien(txt); else falla(txt); return !!cond; };
const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

const srv = await servidor({ ...op, raiz: op.raiz || 'web' });
const nav = await navegador(op);
const URL0 = `${srv.url}?qa=1#torre`;

async function pagina({ tema = 'claro', telefono = false, movimientoReducido = false } = {}) {
  const p = await abrir(nav, op, { url: URL0, tema, telefono, movimientoReducido });
  await esperar(p.page, () => window.__torreQA?.listo?.(), { ms: 40000 });
  return p;
}
async function entrar(page, destino) {
  await page.evaluate((d) => window.__torreQA.modo('recorrido', d), destino ?? null);
  const ok = await esperar(page, () => !!window.__torreQA?.recorrido?.estado?.(), { ms: 60000 });
  await cuadros(page, 3);
  return ok;
}
// espera n cuadros de animación de la página
const cuadros = (page, n = 2) => page.evaluate((n) => new Promise((r) => { let k = 0; const f = () => (++k >= n ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); }), n);
const estado = (page) => page.evaluate(() => window.__torreQA.recorrido.estado());
// el recuadro a la vista: Engine.frame no dibuja ni mueve al caminante con el recuadro fuera de la pantalla (y la ficha,
// que en los modos nuevos va antes del panel, puede dejar el buscador lejos de él)
const alRecuadro = (page) => page.evaluate(() => { const e = document.querySelector('#v-torre .stage'), r = e.getBoundingClientRect(); if (r.top < 0 || r.bottom > innerHeight) e.scrollIntoView({ block: 'center' }); });
async function irA(page, d) {
  await alRecuadro(page);
  await page.evaluate((d) => window.__torreQA.recorrido.irA(d), d);
  await pausa(450);   // fundido de 250 ms
  await cuadros(page, 3);
  return estado(page);
}
// mantiene teclas oprimidas hasta que se cumpla la condición sobre el estado (o se acabe el tiempo); vigila los muros
async function caminar(page, teclas, cond, { ms = 25000, nombre = '' } = {}) {
  await alRecuadro(page);
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus({ preventScroll: true }));
  for (const t of teclas) await page.keyboard.down(t);
  const t0 = Date.now();
  let e = null, enMuro = 0, cumplio = false;
  try {
    while (Date.now() - t0 < ms) {
      await pausa(60);
      e = await estado(page);
      if (!e) break;
      if (e.en_muro) enMuro++;
      if (cond(e)) { cumplio = true; break; }
    }
  } finally { for (const t of [...teclas].reverse()) await page.keyboard.up(t); }
  if (enMuro) falla(`${nombre}: el caminante quedó ${enMuro} veces en una celda de muro`);
  return { cumplio, e };
}
// informe de la consola: errores y fallas cuentan; los avisos se muestran (resumidos) para que se puedan revisar
function informar(registro, titulo) {
  const ok = informe(registro, titulo);
  for (const t of registro.avisos.slice(0, 4)) console.log(`    aviso: ${t.slice(0, 160)}`);
  return ok;
}
const nivelTxt = (e) => (e ? `${e.nivel} ${e.posicion.map((v) => v.toFixed(2)).join(', ')} h=${e.altura} rumbo ${e.rumbo_deg.toFixed(1)}°` : 'sin estado');

// ---------------------------------------------------------------- niveles: capturas en claro, oscuro y teléfono
async function niveles() {
  console.log('niveles: capturas de cada nivel');
  for (const [tema, telefono] of [['claro', false], ['oscuro', false], ['claro', true], ['oscuro', true]]) {
    const nombre = `${tema}${telefono ? '-telefono' : ''}`;
    const { page, registro, cerrar } = await pagina({ tema, telefono });
    await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
    if (!comprobar(await entrar(page), `${nombre}: entra al recorrido`)) { await cerrar(); continue; }
    // un punto de vista representativo de cada nivel; los pisos 2 a 4 y la cubierta, desde una entrada del recorrido de la
    // planta (punto y rumbo de entradas_recorrido): un punto fijo puede quedar pegado a un muro cuando cambia el trazado
    // (el del piso 2 quedó a 0,4 m de uno y la vista salía gris entera)
    const vistas = {
      EXT: { nivel: 'EXT', posicion: [-27, -15], rumbo_deg: 28, pitch_deg: 6 }, P1: { nivel: 'P1', posicion: [-11.4, -8.8], rumbo_deg: 10 }, P2: { nivel: 'P2', entrada: 'laboratorio' },
      P3: { nivel: 'P3', entrada: 'estacion' }, P4: { nivel: 'P4', entrada: 'terapias' }, BT: { nivel: 'BT', posicion: [5.9, -22.3], rumbo_deg: 180, pitch_deg: -8 },
      CUB: { nivel: 'CUB', entrada: 'cubierta' },
    };
    for (const id of NIVELES) {
      const e = await irA(page, vistas[id]);
      await pausa(250);
      await cuadros(page, 4);
      comprobar(e?.nivel === id && !e.en_muro, `${nombre} ${id}: ${nivelTxt(e)}`);
      await captura(page, op, `recorrido-${id}-${nombre}`);
      // la vista no es de un solo color: el más frecuente (a 16 niveles por canal) cubre menos del 70 % del recuadro
      const v = variedad(png(await page.locator('#v-torre .stage').screenshot()));
      comprobar(v.dominante < 0.7 && v.sd >= 6, `${nombre} ${id}: la vista no es de un solo color (el más frecuente cubre ${(v.dominante * 100).toFixed(0)} % del recuadro; desviación de la luminancia ${v.sd.toFixed(1)})`);
      // diseño sobre el recuadro: etiquetas dentro, minimapa sin tapar «Rendimiento», barra sin tapar el joystick
      const d = await page.evaluate(() => {
        const st = document.querySelector('#v-torre .stage').getBoundingClientRect(), R = (s) => document.querySelector(s)?.getBoundingClientRect();
        const choca = (a, b) => a && b && a.width && b.width && !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
        const vis = (s) => { const e = document.querySelector(s); return e && !e.hidden && e.offsetParent !== null && getComputedStyle(e).display !== 'none'; };
        const fuera = [...document.querySelectorAll('#v-torre .stage .reco-lbl, #v-torre .stage .reco-senal')].filter((e) => e.style.display !== 'none' && e.offsetParent && getComputedStyle(e).visibility !== 'hidden').map((e) => e.getBoundingClientRect())
          .filter((r) => r.width && (r.left < st.left - 1 || r.right > st.right + 1 || r.top < st.top - 1 || r.bottom > st.bottom + 1)).length;
        return {
          fuera, etiquetas: [...document.querySelectorAll('#v-torre .stage .reco-lbl, #v-torre .stage .reco-senal')].filter((e) => e.style.display !== 'none').length,
          mapaTapa: vis('.reco-mapa') && choca(R('.reco-mapa'), R('#v-torre .hud-btn')),
          barraTapaJoy: vis('.reco-joy') && choca(R('.reco-barra'), R('.reco-joy')),
          barraTapaRend: choca(R('.reco-barra'), R('#v-torre .hud-btn')),
          ascTapaJoy: vis('.reco-asc') && vis('.reco-joy') && choca(R('.reco-asc'), R('.reco-joy')),
          // cada botón de la barra, no solo la barra (que max-width recorta): dentro de ella y sin montarse en «Rendimiento»
          barraDesborda: (() => { const b = document.querySelector('.reco-barra'); return b.scrollWidth > b.clientWidth + 1; })(),
          botonesFuera: [...document.querySelectorAll('.reco-barra button')].filter((x) => x.offsetParent && getComputedStyle(x).display !== 'none').map((x) => [x.textContent.trim(), x.getBoundingClientRect()])
            .filter(([, r]) => r.width && (r.right > R('.reco-barra').right + 0.5 || choca(r, R('#v-torre .hud-btn')))).map(([t]) => t),
          // dónde se está, sobre el recuadro: visible, dentro del recuadro y sin chocar con la barra ni con «Rendimiento»
          donde: (() => { const e = document.querySelector('.reco-donde'), r = e?.getBoundingClientRect(); return e && vis('.reco-donde') && r.width ? { texto: e.textContent, dentro: r.left >= st.left && r.right <= st.right && r.top >= st.top, choca: choca(r, R('.reco-barra')) || choca(r, R('#v-torre .hud-btn')) || (vis('.reco-mapa') && choca(r, R('.reco-mapa'))), cortado: e.scrollWidth > e.clientWidth + 1 } : null; })(),
        };
      });
      if (d.barraDesborda || d.botonesFuera.length) falla(`${nombre} ${id}: la barra se desborda o sus botones salen de ella o tocan «Rendimiento» (${d.botonesFuera.join(', ')})`);
      if (!d.donde || !d.donde.dentro || d.donde.choca) falla(`${nombre} ${id}: el recinto actual no se ve sobre el recuadro (${JSON.stringify(d.donde)})`);
      else bien(`${nombre} ${id}: sobre el recuadro dice «${d.donde.texto}»`);
      if (d.fuera) falla(`${nombre} ${id}: ${d.fuera} etiquetas fuera del recuadro`);
      if (d.mapaTapa) falla(`${nombre} ${id}: el minimapa tapa «Rendimiento»`);
      if (d.barraTapaJoy || d.barraTapaRend || d.ascTapaJoy) falla(`${nombre} ${id}: la barra o el ascensor tapan el joystick o «Rendimiento»`);
    }
    const dz = await desborde(page);
    comprobar(dz.ok, `${nombre}: sin desborde horizontal (${dz.scrollWidth} ≤ ${dz.innerWidth})${dz.ok ? '' : ` ${dz.culpables.join(', ')}`}`);
    const internos = await textosInternos(page, '#v-torre');
    comprobar(!internos.length, `${nombre}: textos sin rutas ni claves internas${internos.length ? `: ${internos.slice(0, 3).join(' | ')}` : ''}`);
    if (!informar(registro, `recorrido ${nombre}`)) falla(`${nombre}: consola con errores`);
    await cerrar();
  }
  // la barra en anchos intermedios de escritorio (con el panel al lado el recuadro queda angosto): ningún botón cortado
  for (const [ancho, alto] of [[1100, 800], [1200, 800], [760, 900]]) {
    const { page, cerrar } = await abrir(nav, op, { url: URL0, ventana: { viewport: { width: ancho, height: alto }, deviceScaleFactor: 1 } });
    await esperar(page, () => window.__torreQA?.listo?.(), { ms: 40000 });
    await entrar(page);
    const b = await page.evaluate(() => {
      const bar = document.querySelector('.reco-barra'), R = bar.getBoundingClientRect(), rend = document.querySelector('#v-torre .hud-btn')?.getBoundingClientRect();
      return { desborda: bar.scrollWidth > bar.clientWidth + 1, fuera: [...bar.querySelectorAll('button')].filter((x) => x.offsetParent && getComputedStyle(x).display !== 'none').map((x) => [x.textContent.trim() || x.getAttribute('aria-label'), x.getBoundingClientRect()]).filter(([, q]) => q.right > R.right + 0.5 || (rend && q.right > rend.left)).map(([t]) => t) };
    });
    comprobar(!b.desborda && !b.fuera.length, `${ancho} × ${alto}: la barra cabe con todos sus botones${b.fuera.length ? ` (cortados: ${b.fuera.join(', ')})` : ''}`);
    await cerrar();
  }
}

// ---------------------------------------------------------------- alcance: a cada recinto transitable se llega caminando (16.1)
// Recorrido en anchura sobre la rejilla de colisión (celdas de 0,10 m, la misma función libre(x, y) que usa el caminante)
// desde las entradas del nivel, los pasos a otros niveles, los ascensores, las escaleras y la entrada por omisión. Falla si
// queda un recinto transitable sin ninguna celda alcanzada. Las cabinas de montacargas no son destino (se cargan, no se
// caminan) y tampoco salen en «Ir a otro lugar».
async function alcance() {
  console.log('alcance: cada recinto transitable se alcanza caminando desde una entrada');
  const { page, registro, cerrar } = await pagina({ tema: 'claro', movimientoReducido: true });
  if (!comprobar(await entrar(page), 'entra al recorrido')) { await cerrar(); return; }
  const plantas = await page.evaluate(() => window.__torreQA.datos('torre_plantas.json'));
  const res = {};
  for (const n of plantas?.niveles || []) {
    await irA(page, { nivel: n.id });
    const r = await page.evaluate((n) => {
      const api = window.__recorridoQA.api;
      const enPol = (x, y, pol) => { let d = false; for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) { const [xi, yi] = pol[i], [xj, yj] = pol[j]; if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d; } return d; };
      const pts = n.contorno?.length ? n.contorno : n.recintos.flatMap((r) => r.poligono);
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
      x0 -= 1; y0 -= 1; x1 += 1; y1 += 1;
      const c = 0.1, nx = Math.ceil((x1 - x0) / c), ny = Math.ceil((y1 - y0) / c), libre = new Uint8Array(nx * ny);
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) libre[j * nx + i] = api.libre(x0 + (i + 0.5) * c, y0 + (j + 0.5) * c) ? 1 : 0;
      const clave = { P1: '1', P2: '2', P3: '3', P4: '4', CUB: 'cubierta' }[n.id];
      const sem = [api.estado().posicion, ...(n.entradas_recorrido || []).map((q) => q.punto), ...(n.pasos_entre_niveles || []).map((q) => q.punto),
        ...(n.conexiones_verticales || []).filter((q) => q.tipo !== 'montacargas').map((q) => q.puntos?.[clave]).filter(Boolean)];
      const comp = new Uint8Array(nx * ny), cola = new Int32Array(nx * ny);
      let a = 0, b = 0;
      for (const [x, y] of sem) {
        // la celda libre más cercana a la semilla (2 m)
        const i0 = Math.floor((x - x0) / c), j0 = Math.floor((y - y0) / c);
        let k0 = -1;
        for (let r = 0; r < 20 && k0 < 0; r++) for (let dj = -r; dj <= r && k0 < 0; dj++) for (let di = -r; di <= r; di++) { const i = i0 + di, j = j0 + dj; if (i >= 0 && j >= 0 && i < nx && j < ny && libre[j * nx + i]) { k0 = j * nx + i; break; } }
        if (k0 >= 0 && !comp[k0]) { comp[k0] = 1; cola[b++] = k0; }
      }
      while (a < b) {
        const k = cola[a++], i = k % nx, j = (k / nx) | 0;
        for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const ii = i + di, jj = j + dj; if (ii < 0 || jj < 0 || ii >= nx || jj >= ny) continue; const kk = jj * nx + ii; if (comp[kk] || !libre[kk]) continue; comp[kk] = 1; cola[b++] = kk; }
      }
      const fuera = new Set((n.nucleos || []).filter((q) => q.tipo === 'montacargas').flatMap((q) => q.recintos || [q.recinto]));
      const malos = [];
      let transitables = 0;
      for (const r of n.recintos) {
        if (r.transitable === false || fuera.has(r.id)) continue;
        transitables++;
        let p0 = Infinity, q0 = Infinity, p1 = -Infinity, q1 = -Infinity;
        for (const [x, y] of r.poligono) { p0 = Math.min(p0, x); q0 = Math.min(q0, y); p1 = Math.max(p1, x); q1 = Math.max(q1, y); }
        let libres = 0, alcanzadas = 0;
        for (let y = q0 + c / 2; y < q1; y += c) for (let x = p0 + c / 2; x < p1; x += c) {
          if (!enPol(x, y, r.poligono)) continue;
          const k = Math.floor((y - y0) / c) * nx + Math.floor((x - x0) / c);
          if (!libre[k]) continue;
          libres++; if (comp[k]) alcanzadas++;
        }
        if (!alcanzadas) malos.push(`${r.id} «${r.ambiente || r.nombre}» (${libres} celdas libres)`);
      }
      // «Ir a otro lugar» no ofrece montacargas
      const lista = [...document.querySelectorAll('.reco-recintos [data-recinto]')].map((e) => e.dataset.recinto).filter((id) => fuera.has(id));
      return { transitables, malos, montacargasEnLista: lista };
    }, n);
    res[n.id] = r;
    comprobar(!r.malos.length, `${n.id}: ${r.transitables} recintos transitables, ${r.malos.length} sin llegada caminando${r.malos.length ? `: ${r.malos.slice(0, 6).join('; ')}` : ''}`);
    if (r.montacargasEnLista.length) falla(`${n.id}: «Ir a otro lugar» ofrece cabinas de montacargas (${r.montacargasEnLista.join(', ')})`);
  }
  resultado.alcance = res;
  if (!informar(registro, 'recorrido alcance')) falla('alcance: consola con errores');
  await cerrar();
}

// ---------------------------------------------------------------- unidades: «Ir a» cada unidad del inventario y un clic sobre ella
// Para cada unidad de la torre: «Ir a» la deja en su nivel, fuera de los muros, con el punto de mira que eligió dentro del
// cuadro, y un clic en ese punto selecciona la unidad que se ve (la propia o, si va dentro de otra, su contenedor). Los
// faltantes del cierre de brechas encienden su capa. Sin dibujar entre una y otra (el clic usa la cámara puesta en los ojos).
async function unidades() {
  console.log('unidades: «Ir a» cada unidad y un clic sobre ella');
  const { page, registro, cerrar } = await pagina({ tema: 'claro', movimientoReducido: true });
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  if (!comprobar(await entrar(page), 'entra al recorrido')) { await cerrar(); return; }
  const ORD = ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB'];
  const lista = (await page.evaluate(() => window.__recorridoQA.unidades({}))).filter((u) => ORD.includes(u.nivel)).sort((a, b) => ORD.indexOf(a.nivel) - ORD.indexOf(b.nivel));
  const plantas = await page.evaluate(() => window.__torreQA.datos('torre_plantas.json'));
  const t0 = Date.now(), res = [];
  for (let k = 0; k < lista.length; k += 60) {
    res.push(...await page.evaluate(([L, niveles]) => {
      const Q = window.__recorridoQA, api = Q.api, cv = document.querySelector('#v-torre canvas').getBoundingClientRect(), out = [];
      // causas de datos: la hoja abierta de una puerta barre el punto donde se toca el muro, o la unidad queda dentro de un muro
      const enHoja = (nv, [x, y]) => (niveles[nv]?.puertas || []).some((p) => Math.hypot(p.centro[0] - x, p.centro[1] - y) <= (+p.ancho || 0.9) + 0.1);
      const enMuro = (nv, x, y) => (niveles[nv]?.muros || []).some((m) => {
        const ax = m.b[0] - m.a[0], ay = m.b[1] - m.a[1], L2 = ax * ax + ay * ay || 1, t = Math.max(0, Math.min(1, ((x - m.a[0]) * ax + (y - m.a[1]) * ay) / L2));
        return +m.espesor > 0 && Math.hypot(m.a[0] + t * ax - x, m.a[1] + t * ay - y) <= +m.espesor / 2 + 0.02;
      });
      for (const u of L) {
        api.irA({ unidad: u.id });
        const e = api.estado(), o = Q.objetivo();
        let c = 'ok', sel = null;
        if (!e || e.nivel !== u.nivel) c = 'otro_nivel';
        else if (e.en_muro || !e.libre) c = 'en_muro';
        else if (!o) c = 'sin_objetivo';
        else if (!o.visto) {
          // sin vista desde ningún lugar: si desde donde quedó el primer impacto es otro equipo, la unidad está tapada por la
          // ubicación de los datos (otro equipo delante o encima), no por el recorrido
          const r = Q.rayo(e.posicion, o.punto), v = Q.unidadVista(o.unidad);
          const pm = r?.muro ? [r.muro[1][0], -r.muro[1][2]] : null;
          c = r?.unidad && String(r.unidad[0]) !== String(o.unidad) && (!r.muro || r.unidad[1] < r.muro[0]) ? 'tapada_por_otro_equipo'
            : v && enMuro(e.nivel, v.x, v.y) ? 'dentro_de_un_muro'
              : pm && enHoja(e.nivel, pm) ? 'tras_la_hoja_de_una_puerta' : 'sin_vista';
          sel = r?.unidad?.[0] ?? null;
        }
        else {
          const p = Q.pantalla(o.punto);
          if (!p || !p.delante || p.x < cv.left + 2 || p.x > cv.right - 2 || p.y < cv.top + 2 || p.y > cv.bottom - 2) c = 'fuera_de_cuadro';
          else {
            // la ficha abierta por «Ir a» no cuenta: el clic debe abrir una nueva
            const f0 = Q.ficha();
            Q.seleccionarEn(p.x, p.y);
            const f = Q.ficha();
            sel = f === f0 ? null : f?.unidad ?? (f?.implemento ? `implemento de ${f.implemento[0]}` : f?.recinto ? `recinto ${f.recinto}` : null);
            if (sel == null) c = 'clic_sin_seleccion';
            else if (String(sel) !== String(o.unidad)) c = 'otra_seleccion';
          }
        }
        const falt = u.estado === 'cierre_brechas_propuesto' && document.querySelector('[data-capa="faltantes"]')?.getAttribute('aria-pressed') !== 'true';
        if (c === 'ok' && falt) c = 'faltante_sin_capa';
        out.push({ id: u.id, c, sel, ve: o?.unidad, nivel: e?.nivel, recinto: e?.recinto });
      }
      return out;
    }, [lista.slice(k, k + 60), Object.fromEntries((plantas?.niveles || []).map((n) => [n.id, { puertas: n.puertas, muros: n.muros }]))]));
  }
  const cat = {};
  for (const r of res) cat[r.c] = (cat[r.c] || 0) + 1;
  const DATOS = new Set(['tapada_por_otro_equipo', 'dentro_de_un_muro', 'tras_la_hoja_de_una_puerta']);
  const tapadas = res.filter((r) => DATOS.has(r.c)), malos = res.filter((r) => r.c !== 'ok' && !DATOS.has(r.c));
  const porId = new Map(lista.map((u) => [u.id, u]));
  const linea = (m) => `${m.c}: ${m.id} ${porId.get(m.id).nombre.slice(0, 50)} (${porId.get(m.id).modelo}, ${porId.get(m.id).montaje}) en ${m.nivel} ${m.recinto}${m.sel ? ` → ${m.sel}` : ''}`;
  for (const m of malos.slice(0, 12)) console.log(`    ${linea(m)}`);
  comprobar(!malos.length, `«Ir a» y clic en las ${lista.length} unidades de la torre: ${JSON.stringify(cat)} (${((Date.now() - t0) / 1000).toFixed(0)} s)`);
  // las tapadas por otro equipo son de la ubicación (reglas de ubicación del inventario): se listan para corregirlas allí
  if (tapadas.length) console.log(`  aviso: ${tapadas.length} unidades que no se ven desde ningún lugar por su ubicación en los datos (otro equipo delante, dentro de un muro o tras la hoja abierta de una puerta; el recuadro rojo se ve a través):`);
  for (const m of tapadas.slice(0, 12)) console.log(`    ${linea(m)}`);
  resultado.unidades = { cat, malos, tapadas };
  if (!informar(registro, 'recorrido unidades')) falla('unidades: consola con errores');
  await cerrar();
}

// ---------------------------------------------------------------- flujo: lo que hace una persona con el ratón, el dedo y el buscador
// Botón «Laboratorio» → recorrido en la puerta del laboratorio; la ficha de lo que se toca en 3D a la vista (escritorio) o a
// un toque de «Ver ficha» (teléfono); «Ir a» desde el buscador y desde «Ir a otro lugar» deja el recuadro a la vista y con el
// foco; el buscador encuentra reactivos e implementos internos; un faltante del cierre de brechas se ve al llegar; la tarjeta
// de habilitación dice dónde está cada unidad y separa las propuestas; torre.json tarde no devuelve los pisos a la selección.
const recuadroVisible = (page) => page.evaluate(() => { const r = document.querySelector('#v-torre .stage').getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), alto: innerHeight, ok: r.top >= -1 && r.bottom <= innerHeight + 1, foco: document.activeElement === document.querySelector('#v-torre .stage') }; });
async function abrirBuscador(page) {
  await page.evaluate(() => { const d = document.querySelector('.reco-inv'); if (!d.open) { d.open = true; d.dispatchEvent(new Event('toggle')); } });
  await esperar(page, () => !!document.querySelector('.reco-busca input[type=search]'), { ms: 8000 });
}
async function buscar(page, texto, valores = {}) {
  await abrirBuscador(page);
  for (const [k, v] of Object.entries(valores)) await page.selectOption(`.reco-busca [data-f="${k}"]`, v);
  const t0 = await page.evaluate(() => document.querySelector('.reco-totales')?.textContent || '');
  await page.fill('.reco-busca input[type=search]', texto);
  await esperar(page, (t0) => document.querySelector('.reco-totales')?.textContent !== t0, { ms: 4000, arg: t0 });
  await pausa(200);
  return page.evaluate(() => ({ n: +(document.querySelector('.reco-totales b')?.textContent || '0').replace(/\D/g, ''), filas: [...document.querySelectorAll('.reco-res li')].slice(0, 3).map((li) => li.textContent.replace(/\s+/g, ' ').trim()) }));
}
async function flujo() {
  console.log('flujo: botón Laboratorio, ficha a la vista, «Ir a» con el recuadro a la vista, reactivos, faltantes, habilitación y torre.json tarde');
  // ---- escritorio
  {
    const { page, registro, cerrar } = await pagina({ tema: 'claro' });
    await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
    // botón «Laboratorio» (16.2)
    await page.click('[data-modo-torre="laboratorio"]');
    await esperar(page, () => !!window.__torreQA?.recorrido?.estado?.(), { ms: 60000 });
    await pausa(600); await cuadros(page, 3);
    let e = await estado(page);
    // la puerta y el rumbo salen de la planta (entradas_recorrido del piso 2), no de cifras fijas: la entrada cambia con el trazado
    const lab = await page.evaluate(async () => {
      const pl = await window.__torreQA.datos('torre_plantas.json'), ent = pl?.niveles?.find((n) => n.id === 'P2')?.entradas_recorrido?.find((x) => x.id === 'laboratorio');
      return { modo: window.__torreQA.modo(), pulsado: document.querySelector('[data-modo-torre="laboratorio"]').getAttribute('aria-pressed'), punto: ent?.punto, mirando: ent?.mirando_deg };
    });
    comprobar(lab.modo === 'recorrido' && lab.pulsado === 'true' && e.nivel === 'P2' && lab.punto && dAng(e.rumbo_deg, lab.mirando) < 1 && Math.hypot(e.posicion[0] - lab.punto[0], e.posicion[1] - lab.punto[1]) < 0.6,
      `el botón «Laboratorio» abre el recorrido en la puerta del laboratorio mirando hacia adentro (${nivelTxt(e)}; modo ${lab.modo}, «Laboratorio» pulsado: ${lab.pulsado})`);
    // la ficha de un equipo tocado en 3D queda a la vista junto al recuadro
    const carro = await page.evaluate(() => window.__recorridoQA.unidades({ texto: 'carro de paro' }).find((u) => u.modelo === 'carro_paro')?.id);
    await irA(page, { unidad: carro });
    await page.evaluate(() => { const f = document.querySelector('[data-slot="torre.ficha.modo"]'); f.innerHTML = ''; f.hidden = true; document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }); });
    await pausa(300);
    const pt = await page.evaluate(() => { const o = window.__recorridoQA.objetivo(); return window.__recorridoQA.pantalla(o.punto); });
    await page.mouse.click(pt.x, pt.y);
    await pausa(400);
    const fi = await page.evaluate(() => { const f = document.querySelector('[data-slot="torre.ficha.modo"]'), r = f.getBoundingClientRect(); return { top: Math.round(r.top), alto: innerHeight, sel: window.__recorridoQA.ficha()?.unidad, boton: !document.querySelector('.reco-verficha').hidden }; });
    comprobar(fi.sel === carro && fi.top < fi.alto - 60 && !fi.boton, `tocar el carro de paro en 3D abre su ficha a la vista (empieza en y=${fi.top} de ${fi.alto}; sin botón «Ver ficha»)`);
    await captura(page, op, 'flujo-ficha-tras-clic-escritorio');
    // el buscador encuentra reactivos e implementos internos y «Ir a» abre la ficha del contenedor con su contenido
    for (const [texto, patron] of [['lisante', /contiene: [^·]*lisante/i], ['adrenalina', /contiene: [^·]*adrenalina/i]]) {
      const r = await buscar(page, texto);
      comprobar(r.n > 0 && patron.test(r.filas[0] || ''), `buscar «${texto}»: ${r.n} unidades; primera: «${(r.filas[0] || '').slice(0, 110)}»`);
    }
    await page.evaluate(() => scrollTo(0, document.querySelector('.reco-res').getBoundingClientRect().top + scrollY - 200));
    await page.click('.reco-res [data-ir]');
    await pausa(1500); await cuadros(page, 3);
    let v = await recuadroVisible(page);
    const impl = await page.evaluate(() => !!document.querySelector('[data-slot="torre.ficha.modo"] details.reco-impl[open]'));
    comprobar(v.ok && v.foco && impl, `«Ir a» desde el buscador (adrenalina) deja el recuadro a la vista (${v.top}..${v.bottom} de ${v.alto}) con el foco y la ficha del carro con sus implementos abiertos (${impl})`);
    // un faltante del cierre de brechas: al llegar se enciende su capa y un clic lo selecciona
    await page.fill('.reco-busca input[type=search]', '');
    const rf = await buscar(page, '', { estado: 'u:cierre_brechas_propuesto' });
    await page.evaluate(() => { const b = document.querySelector('.reco-res [data-ir]'); b.scrollIntoView({ block: 'center' }); });
    await page.click('.reco-res [data-ir]');
    await pausa(1500); await cuadros(page, 3);
    const falt = await page.evaluate(() => { const Q = window.__recorridoQA, o = Q.objetivo(), p = Q.pantalla(o.punto), f0 = Q.ficha(); Q.seleccionarEn(p.x, p.y); const f1 = Q.ficha(); return { capa: document.querySelector('[data-capa="faltantes"]').getAttribute('aria-pressed'), visto: o.visto, sel: f1 !== f0 && f1?.unidad === o.unidad, aviso: document.querySelector('.reco-aviso')?.textContent }; });
    comprobar(rf.n > 0 && falt.capa === 'true' && falt.visto && falt.sel, `«Ir a» un faltante (${rf.n} en el filtro) enciende la capa «Faltantes» (${falt.capa}) y un clic lo selecciona (${falt.sel}); aviso «${falt.aviso}»`);
    await captura(page, op, 'flujo-ir-a-faltante');
    // «Ir a otro lugar»: el recuadro a la vista y con el foco
    await page.evaluate(() => scrollTo(0, document.querySelector('.reco-recintos').getBoundingClientRect().top + scrollY - 100));
    await page.click('.reco-recintos [data-recinto] >> nth=3');
    await pausa(1500);
    v = await recuadroVisible(page);
    comprobar(v.ok && v.foco, `«Ir a otro lugar» deja el recuadro a la vista (${v.top}..${v.bottom} de ${v.alto}) y con el foco (${v.foco})`);
    // habilitación: dónde está cada unidad y las del cierre propuesto aparte y marcadas
    await page.evaluate(() => document.querySelector('[data-slot="torre.habilitacion"]').scrollIntoView({ block: 'start' }));
    await esperar(page, () => !!document.querySelector('[data-slot="torre.habilitacion"] .hab-tabla tbody tr'), { ms: 30000 });
    const hab = await page.evaluate(() => {
      const srvs = [...document.querySelectorAll('details.hab-srv')];
      let filas = 0, conRecinto = 0, propuestasMezcladas = 0, propuestas = 0;
      for (const d of srvs) {
        d.open = true; d.dispatchEvent(new Event('toggle', { bubbles: false }));
      }
      return new Promise((r) => setTimeout(() => {
        for (const d of srvs) for (const det of d.querySelectorAll('.hab-cuerpo details')) {
          const prop = /cierre propuesto/.test(det.querySelector('summary').textContent);
          for (const li of det.querySelectorAll('li')) {
            const p1 = !!li.querySelector('.pill.p1');
            if (prop) { propuestas++; if (!p1) propuestasMezcladas++; } else { filas++; if (p1) propuestasMezcladas++; if (/ · /.test(li.querySelector('small.note')?.textContent || '')) conRecinto++; }
          }
        }
        r({ filas, conRecinto, propuestas, propuestasMezcladas });
      }, 600));
    });
    comprobar(hab.filas > 0 && hab.conRecinto / hab.filas > 0.9 && !hab.propuestasMezcladas, `habilitación: ${hab.conRecinto} de ${hab.filas} filas de «Unidades que la cubren» dicen nivel y recinto; ${hab.propuestas} propuestas del cierre aparte y marcadas (mezcladas: ${hab.propuestasMezcladas})`);
    if (!informar(registro, 'recorrido flujo escritorio')) falla('flujo escritorio: consola con errores');
    await cerrar();
  }
  // ---- teléfono: «Ir a» desde el buscador y la ficha a un toque
  {
    const { page, registro, cerrar } = await pagina({ tema: 'oscuro', telefono: true });
    await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
    await page.locator('[data-modo-torre="recorrido"]').scrollIntoViewIfNeeded();
    await page.locator('[data-modo-torre="recorrido"]').tap();
    await esperar(page, () => !!window.__torreQA?.recorrido?.estado?.(), { ms: 60000 });
    await pausa(600);
    await buscar(page, 'carro de paro');
    await page.locator('.reco-res [data-ir]').first().scrollIntoViewIfNeeded();
    await page.locator('.reco-res [data-ir]').first().tap();
    await pausa(1600); await cuadros(page, 3);
    let v = await recuadroVisible(page);
    comprobar(v.ok && v.foco, `teléfono: «Ir a» desde el buscador deja el recuadro a la vista (${v.top}..${v.bottom} de ${v.alto}) y con el foco`);
    // tocar el equipo en 3D: la ficha queda abajo y el botón «Ver ficha» la trae
    await page.evaluate(() => { const f = document.querySelector('[data-slot="torre.ficha.modo"]'); f.innerHTML = ''; f.hidden = true; });
    const pt = await page.evaluate(() => { const o = window.__recorridoQA.objetivo(); return window.__recorridoQA.pantalla(o.punto); });
    await page.touchscreen.tap(pt.x, pt.y);
    await pausa(500);
    const b = await page.evaluate(() => { const x = document.querySelector('.reco-verficha'); return { visible: !x.hidden && !!x.offsetParent, texto: x.textContent, rect: x.getBoundingClientRect().toJSON(), joy: document.querySelector('.reco-joy')?.getBoundingClientRect().toJSON() }; });
    const chocaJoy = b.joy && !(b.rect.right <= b.joy.left || b.joy.right <= b.rect.left || b.rect.bottom <= b.joy.top || b.joy.bottom <= b.rect.top);
    comprobar(b.visible && !chocaJoy, `teléfono: tras tocar el equipo aparece «${b.texto}» sobre el recuadro, sin tapar el joystick`);
    await captura(page, op, 'flujo-ver-ficha-telefono');
    if (b.visible) {
      await page.tap('.reco-verficha');
      await pausa(1200);
      const f = await page.evaluate(() => { const r = document.querySelector('[data-slot="torre.ficha.modo"]').getBoundingClientRect(); return { top: Math.round(r.top), alto: innerHeight, foco: !!document.activeElement?.closest('[data-slot="torre.ficha.modo"]') }; });
      comprobar(f.top >= -1 && f.top < f.alto - 100 && f.foco, `teléfono: «Ver ficha» lleva a la ficha (empieza en y=${f.top} de ${f.alto}) y le da el foco (${f.foco})`);
    }
    const dz = await desborde(page);
    comprobar(dz.ok, `flujo teléfono: sin desborde horizontal (${dz.scrollWidth} ≤ ${dz.innerWidth})`);
    if (!informar(registro, 'recorrido flujo teléfono')) falla('flujo teléfono: consola con errores');
    await cerrar();
  }
  // ---- torre.json llega tarde (4 s) con el recorrido ya abierto: los pisos no vuelven a la selección del Stage (6.8)
  {
    const { page, registro, cerrar } = await abrir(nav, op, { url: URL0, tema: 'claro' });
    await page.route(/\/data\/torre\.json/, async (ruta) => { await pausa(4000); await ruta.continue(); });
    await page.reload();
    await esperar(page, () => !!window.__torreQA, { ms: 30000 });
    await page.evaluate(() => window.__torreQA.modo('recorrido', null));
    await esperar(page, () => window.__torreQA?.listo?.(), { ms: 40000 });
    await pausa(800);
    const n1 = await page.evaluate(() => ({ modo: window.__torreQA.modo(), sel: window.__torreQA.seleccionables() }));
    await page.evaluate(() => window.__torreQA.modo('pisos'));
    await pausa(600);
    const n2 = await page.evaluate(() => window.__torreQA.seleccionables());
    comprobar(n1.modo === 'recorrido' && n1.sel === 0 && n2 >= 4, `con torre.json tarde y el recorrido abierto, el Stage no recibe clics (${n1.sel} seleccionables) y al volver a «Pisos» los ${n2} pisos vuelven`);
    if (!informar(registro, 'recorrido torre.json tarde')) falla('torre.json tarde: consola con errores');
    await cerrar();
  }
}

// ---------------------------------------------------------------- utilidades del guion
const dAng = (a, b) => { const d = (((a - b) % 360) + 540) % 360 - 180; return Math.abs(d); };
// gira la mirada al rumbo pedido sin moverse (las flechas giran a 120 °/s; aquí se fija el rumbo para que el guion de
// caminar no dependa de la cadencia de cuadros del navegador sin GPU)
async function girarHasta(page, rumbo, pitch = 0) {
  await page.evaluate(([r, p]) => window.__recorridoQA.girar(r, p), [rumbo, pitch]);
  await cuadros(page, 2);
  return estado(page);
}
const dentroRect = ([x, y], [x0, y0, x1, y1], m = 0) => x >= x0 - m && x <= x1 + m && y >= y0 - m && y <= y1 + m;
// distancia de un punto a un rectángulo, negativa si está adentro
const distRect = ([x, y], [x0, y0, x1, y1]) => (dentroRect([x, y], [x0, y0, x1, y1]) ? -Math.min(x - x0, x1 - x, y - y0, y1 - y) : Math.hypot(Math.max(x0 - x, 0, x - x1), Math.max(y0 - y, 0, y - y1)));
// geometría de la planta publicada (torre_plantas.json): las comprobaciones de escaleras, pasos, huecos y entradas leen de
// allí sus puntos y metas, no cifras fijas (la planta cambia con el trazado y con la coordinación BIM)
// radio del caminante y celda de la rejilla de colisión (planta3d.js con el RADIO de recorrido.js): guion() los lee del
// nivel armado (__recorridoQA.nivel()), así los márgenes de los costados, del hueco y del ojo siguen a la colisión
let RADIO = 0.20, CELDA = 0.10;
const rumboHacia = ([x0, y0], [x1, y1]) => ((Math.atan2(y1 - y0, x1 - x0) * 180) / Math.PI + 360) % 360;
const enPoligono = (x, y, pol) => { let d = false; for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) { const [xi, yi] = pol[i], [xj, yj] = pol[j]; if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d; } return d; };
const distSegmento = ([x, y], [ax, ay], [bx, by]) => { const vx = bx - ax, vy = by - ay, t = Math.max(0, Math.min(1, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy || 1))); return Math.hypot(ax + t * vx - x, ay + t * vy - y); };
// distancia de un punto al borde de un polígono, negativa si está adentro
const distPoligono = (p, pol) => { const d = Math.min(...pol.map((a, i) => distSegmento(p, a, pol[(i + 1) % pol.length]))); return enPoligono(p[0], p[1], pol) ? -d : d; };
const recintoEn = (nivel, [x, y]) => (nivel?.recintos || []).find((r) => enPoligono(x, y, r.poligono)) || null;
// eje de un tramo de escalera: índice de la coordenada a lo largo (k), sentido de subida (s), bordes bajo y alto a lo
// largo y centro del carril a través
function ejeTramo(p) {
  const r = (+p.sube_hacia_deg * Math.PI) / 180, dx = Math.round(Math.cos(r)), dy = Math.round(Math.sin(r)), [x0, y0, x1, y1] = p.rect;
  const k = dx ? 0 : 1, s = dx || dy, lo = k ? y0 : x0, hi = k ? y1 : x1;
  return { k, s, bajo: s > 0 ? lo : hi, alto: s > 0 ? hi : lo, carril: k ? (x0 + x1) / 2 : (y0 + y1) / 2, rumbo: ((+p.sube_hacia_deg % 360) + 360) % 360 };
}
const enEje = (k, a, c) => (k === 0 ? [a, c] : [c, a]);
// mantiene teclas oprimidas hasta que el caminante queda quieto (menos de 3 mm en cada una de tres tandas seguidas de 3
// cuadros de la página: no depende de la cadencia de cuadros del navegador sin GPU) o se acaba el tiempo
async function caminarHastaParar(page, teclas, { ms = 10000, nombre = '' } = {}) {
  await alRecuadro(page);
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus({ preventScroll: true }));
  for (const t of teclas) await page.keyboard.down(t);
  const t0 = Date.now();
  let e = await estado(page), quieto = 0, enMuro = 0;
  try {
    while (Date.now() - t0 < ms && quieto < 3) {
      await cuadros(page, 3);
      const q = await estado(page);
      if (!q) break;
      if (q.en_muro) enMuro++;
      quieto = q.nivel === e.nivel && Math.hypot(q.posicion[0] - e.posicion[0], q.posicion[1] - e.posicion[1]) < 0.003 ? quieto + 1 : 0;
      e = q;
    }
  } finally { for (const t of [...teclas].reverse()) await page.keyboard.up(t); }
  if (enMuro) falla(`${nombre}: el caminante quedó ${enMuro} veces en una celda de muro`);
  return { detenido: quieto >= 3, e };
}
// Pasos entre descanso y tramo en todas las escaleras de la planta publicada. Por cada extremo de cada tramo, su descanso:
// el de piso o el intermedio del mismo nivel que lo toca a la misma cota, o el de piso del nivel de arriba (la llegada, que
// se prueba en ese nivel). En cada junta:
//   · carril continuo en la rejilla: el carril del tramo (celdas libres seguidas a lo ancho, a 0,6 m de la junta) tiene en el
//     descanso, del lado que no da al ojo, el mismo borde: la celda de afuera que lo cierra en el tramo también está tapada
//     en el descanso a 0,15 y 0,35 m de la junta (salvo donde el descanso da a un piso a su misma altura: el de piso de la
//     escalera principal, al vestíbulo). Una celda de más en el descanso es un escalón donde quien camina justo en la
//     dirección del eje se traba;
//   · caminando (gancho caminar de __recorridoQA: la misma función que mueve al caminante en cada cuadro, en cuadros de
//     1/30 s, sin teclas): del descanso al tramo y del tramo al descanso, desde 0,45 m antes de la junta, con 5
//     desplazamientos a lo ancho del carril (sus dos bordes, junto al ojo y junto al muro o la baranda, incluidos) y, del
//     descanso al tramo, también a 2 celdas afuera de cada borde si allí el descanso está libre (frente a la punta del ojo);
//     con el rumbo del eje y ±15°. Debe pasar la junta por 0,45 m en no más de 3 s, sin quedar nunca en una celda de muro
//     y desde el punto pedido (libre).
async function transiciones(page, NV, R) {
  const juntas = [];
  for (const [id, n] of NV) for (const esc of n.escaleras || []) for (const p of esc.partes || []) {
    if (p.tipo !== 'tramo') continue;
    const t = ejeTramo(p), kc = 1 - t.k;
    for (const fin of ['bajo', 'alto']) {
      const J = t[fin], z = fin === 'bajo' ? +p.z0 : +p.z1, dirIn = fin === 'bajo' ? t.s : -t.s;
      const toca = (q, dz = 0) => q.tipo !== 'tramo' && Math.abs(+q.z + dz - z) < 0.05 && Math.abs((dirIn > 0 ? q.rect[t.k + 2] : q.rect[t.k]) - J) < 0.02;
      let marco = id, d = (esc.partes || []).find((q) => toca(q));
      const ar = esc.sube_a && NV.get(esc.sube_a);
      if (!d && ar) { d = ((ar.escaleras || []).find((x) => x.id === esc.id)?.partes || []).find((q) => toca(q, ar.z - n.z)); if (d) marco = ar.id; }
      juntas.push({ txt: `${id} ${esc.id} ${fin === 'bajo' ? 'arranque' : 'llegada'} del tramo ${p.rect.join(',')}${marco !== id ? ` (en ${marco})` : ''}`, marco, k: t.k, kc, c0: p.rect[kc], c1: p.rect[kc + 2], J, dirIn, rectD: d?.rect || null, ojo: esc.ojo ? [esc.ojo[kc] - (RADIO + CELDA), esc.ojo[kc + 2] + (RADIO + CELDA)] : null });
    }
  }
  const malos = juntas.filter((j) => !j.rectD).map((j) => `${j.txt}: sin descanso a su cota`);
  let casos = 0, escalones = 0;
  const carriles = [];
  for (const marco of [...new Set(juntas.filter((j) => j.rectD).map((j) => j.marco))]) {
    await irA(page, { nivel: marco });
    const res = await page.evaluate(([marco, js]) => {
      const Q = window.__recorridoQA, out = [];
      const cod = (x, y) => Q.sondeo(x, y)?.codigo;
      for (const j of js) {
        if (Q.colocar({ nivel: marco, posicion: [j.rectD[0] + 0.05, j.rectD[1] + 0.05] })?.nivel !== marco) { out.push({ j, error: `no se arma ${marco}` }); continue; }
        const P = (a, c) => (j.k === 0 ? [a, c] : [c, a]);
        // carril del tramo a 0,6 m de la junta: el intervalo más largo de celdas libres a lo ancho, de a 0,01 m
        const aL = j.J + j.dirIn * 0.6, tramos = [];
        let ini = null;
        for (let c = j.c0 + 0.005; c <= j.c1; c += 0.01) { const libre = cod(...P(aL, c)) !== 1; if (libre && ini == null) ini = c; if (!libre && ini != null) { tramos.push([ini, c - 0.01]); ini = null; } }
        if (ini != null) tramos.push([ini, j.c1 - 0.005]);
        const L = tramos.sort((a, b) => b[1] - b[0] - (a[1] - a[0]))[0];
        if (!L || L[1] - L[0] < 0.2) { out.push({ j, error: 'el tramo no tiene carril libre' }); continue; }
        out.push({ j, carril: [+L[0].toFixed(2), +L[1].toFixed(2)] });
        // carril continuo: la celda que cierra cada borde del carril en el tramo, del lado que no da al ojo, también está
        // tapada en el descanso (salvo si de ese lado el descanso da a un piso a su altura)
        for (const o of [L[0] - 0.05, L[1] + 0.05]) {
          if (j.ojo && o >= j.ojo[0] && o <= j.ojo[1]) continue;
          const abierto = (a) => [0.15, 0.25, 0.35].some((dd) => cod(...P(a, o < L[0] ? j.rectD[j.kc] - dd : j.rectD[j.kc + 2] + dd)) === 0);
          const a = [0.15, 0.35].map((d) => j.J - j.dirIn * d).find((a) => cod(...P(a, o)) !== 1 && !abierto(a));
          if (a != null) out.push({ j, escalon: `en el descanso queda libre ${P(a, o).map((v) => v.toFixed(2)).join(', ')}, que en el tramo cierra el carril [${L.map((v) => v.toFixed(2)).join(', ')}]` });
        }
        const e0 = L[0] + 0.01, e1 = L[1] - 0.01, anchos = [0, 1, 2, 3, 4].map((i) => e0 + ((e1 - e0) * i) / 4);
        for (const sentido of ['al tramo', 'al descanso']) {
          const dir = sentido === 'al tramo' ? j.dirIn : -j.dirIn, a0 = j.J - dir * 0.45, eje = j.k === 0 ? (dir > 0 ? 0 : 180) : (dir > 0 ? 90 : 270);
          const lista = anchos.map((c) => ({ c, afuera: false }));
          if (sentido === 'al tramo') for (const c of [e0 - 0.2, e1 + 0.2]) if (c > j.c0 && c < j.c1 && cod(...P(a0, c)) !== 1) lista.push({ c, afuera: true });
          for (const { c, afuera } of lista) for (const dr of [-15, 0, 15]) {
            const p0 = P(a0, c), e = Q.colocar({ nivel: marco, posicion: p0, rumbo_deg: eje + dr, pitch_deg: 0 });
            const corrido = Math.hypot(e.posicion[0] - p0[0], e.posicion[1] - p0[1]);
            let paso = -1, muro = 0, f = null;
            for (let q = 0; q < 90 && corrido < 0.02; q++) { f = Q.caminar({ n: 1, dt: 1 / 30 })[0]; if (f[4]) muro++; if ((f[1 + j.k] - j.J) * dir >= 0.45) { paso = q; break; } }
            out.push({ j, caso: { sentido, c: +c.toFixed(3), afuera, dr, ok: corrido < 0.02 && paso >= 0 && !muro, corrido: +corrido.toFixed(3), muro, fin: f || [e.nivel, ...e.posicion, e.altura] } });
          }
        }
      }
      return out;
    }, [marco, juntas.filter((j) => j.marco === marco && j.rectD)]);
    for (const q of res) {
      if (q.error) malos.push(`${q.j.txt}: ${q.error}`);
      else if (q.carril) carriles.push(`${q.j.txt}: [${q.carril.join(', ')}]`);
      else if (q.escalon) { escalones++; malos.push(`${q.j.txt}: escalón de una celda (${q.escalon})`); }
      else {
        casos++;
        const c = q.caso;
        if (!c.ok) malos.push(`${q.j.txt} ${c.sentido} desde ${c.c}${c.afuera ? ' (afuera del carril)' : ''} a ${c.dr >= 0 ? '+' : ''}${c.dr}°: ${c.corrido >= 0.02 ? `el punto de arranque no está libre (corrido ${c.corrido} m)` : `${c.muro ? `${c.muro} cuadros en un muro; ` : ''}queda en ${c.fin.slice(0, 4).join(', ')}`}`);
      }
    }
  }
  R.transiciones = { juntas: juntas.length, casos, carriles, malos };
  comprobar(juntas.length >= 2 && casos >= juntas.length * 20 && !malos.length,
    `en las ${juntas.length} juntas entre descanso y tramo de las escaleras (${[...new Set(juntas.map((j) => j.txt.split(' ').slice(0, 2).join(' ')))].join(', ')}) el carril es continuo (${escalones} escalones) y en ${casos} pasos, subiendo y bajando, a lo ancho del carril y a ±15° del eje, el caminante nunca se traba${malos.length ? `; mal (${malos.length}): ${malos.slice(0, 12).join('; ')}` : ''}`);
}
// normal de la puerta (de su muro) que apunta hacia adentro del polígono pol
function normalPuerta(nivel, puerta, pol) {
  const m = (nivel.muros || []).find((q) => q.id === puerta.muro);
  if (!m) return null;
  const L = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]) || 1, n = [-(m.b[1] - m.a[1]) / L, (m.b[0] - m.a[0]) / L];
  return enPoligono(puerta.centro[0] + n[0] * 0.3, puerta.centro[1] + n[1] * 0.3, pol) ? n : [-n[0], -n[1]];
}

// ---------------------------------------------------------------- guion del 13.3 y el 16.6 (escritorio)
async function guion() {
  console.log('guion: caminar, escaleras, ascensor, hueco, fichas, buscador, cámara y selección');
  const { page, registro, cerrar } = await pagina({ tema: 'claro' });
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  comprobar(await entrar(page), 'entra al recorrido');
  const R = {};
  const NV = new Map(((await page.evaluate(() => window.__torreQA.datos('torre_plantas.json')))?.niveles || []).map((n) => [n.id, n]));
  {
    const rj = await page.evaluate(() => window.__recorridoQA.nivel());
    if (comprobar(rj && rj.radio > 0 && rj.celda > 0, `la rejilla de colisión del nivel da su radio y su celda (${rj?.radio} m y ${rj?.celda} m)`)) { RADIO = rj.radio; CELDA = rj.celda; }
  }
  let e = await estado(page);
  comprobar(e.nivel === 'EXT', `empieza en los exteriores frente a la puerta principal (${nivelTxt(e)})`);
  // las flechas giran a 120 °/s
  const g0 = e.rumbo_deg;
  await caminar(page, ['ArrowLeft'], () => false, { ms: 600, nombre: 'giro con flechas' });
  const g1 = (await estado(page)).rumbo_deg;
  comprobar(dAng(g1, g0) > 20, `la flecha izquierda gira la mirada (${g0.toFixed(1)}° → ${g1.toFixed(1)}°)`);
  await girarHasta(page, 0);
  // exteriores → piso 1 caminando por la puerta principal
  let r = await caminar(page, ['ArrowUp'], (q) => q.nivel === 'P1', { ms: 20000, nombre: 'puerta principal' });
  comprobar(r.cumplio, `cruza la puerta principal caminando: exteriores → piso 1 (${nivelTxt(r.e)})`);
  // y de vuelta
  await girarHasta(page, 180);
  r = await caminar(page, ['KeyW'], (q) => q.nivel === 'EXT', { ms: 20000, nombre: 'puerta principal de vuelta' });
  comprobar(r.cumplio, `sale por la misma puerta: piso 1 → exteriores (${nivelTxt(r.e)})`);

  // caminar por cada nivel con un guion de teclas: nunca en un muro, siempre en celda libre, y se mueve
  const PASEO = [[['KeyW'], 2200], [['ArrowLeft'], 600], [['KeyW', 'ShiftLeft'], 1500], [['KeyD'], 900], [['KeyS'], 700], [['ArrowRight'], 1300], [['KeyW'], 2000], [['KeyA'], 800], [['ArrowUp'], 1500]];
  const INICIO = { EXT: { nivel: 'EXT', entrada: 'porton_peatonal' }, P1: { nivel: 'P1', entrada: 'urgencias' }, P2: { nivel: 'P2', entrada: 'laboratorio' }, P3: { nivel: 'P3', entrada: 'estacion' }, P4: { nivel: 'P4', entrada: 'ascensores' }, BT: { nivel: 'BT', entrada: 'pasaje' }, CUB: { nivel: 'CUB', entrada: 'cubierta' } };
  R.paseo = {};
  for (const id of NIVELES) {
    let q = await irA(page, INICIO[id]);
    const p0 = q.posicion;
    let total = 0, libres = true, prev = p0;
    for (const [teclas, ms] of PASEO) {
      const t0 = Date.now();
      await caminar(page, teclas, () => Date.now() - t0 > ms, { ms: ms + 500, nombre: `paseo ${id}` });
      q = await estado(page);
      total += Math.hypot(q.posicion[0] - prev[0], q.posicion[1] - prev[1]);
      prev = q.posicion;
      if (!q.libre) libres = false;
    }
    R.paseo[id] = { recorrido_m: +total.toFixed(2), fin: q.posicion, nivel: q.nivel };
    comprobar(q.nivel === id && total > 0.8 && libres && !q.en_muro, `paseo por ${id}: ${total.toFixed(1)} m sin entrar en muros (${nivelTxt(q)})`);
  }

  // escalera norte caminando: piso 1 → piso 2 y de vuelta
  e = await irA(page, { nivel: 'P1', posicion: [4.45, 15.3], rumbo_deg: 90 });
  r = await caminar(page, ['KeyW'], (q) => q.posicion[1] > 20.9, { ms: 30000, nombre: 'escalera tramo 1' });
  const h1 = r.e.altura;
  await girarHasta(page, 0);
  r = await caminar(page, ['KeyW'], (q) => q.posicion[0] > 7.1, { ms: 15000, nombre: 'escalera descanso' });
  await girarHasta(page, 270);
  r = await caminar(page, ['KeyW'], (q) => q.nivel === 'P2' && q.posicion[1] < 15.6, { ms: 25000, nombre: 'escalera tramo 2' });
  comprobar(h1 > 1.8 && h1 < 2.4 && r.cumplio && Math.abs(r.e.altura) < 0.05, `sube caminando la escalera norte: descanso intermedio a ${h1} m y llega al piso 2 (${nivelTxt(r.e)})`);
  await girarHasta(page, 90);
  r = await caminar(page, ['KeyW'], (q) => q.nivel === 'P1' && q.posicion[1] > 20.9, { ms: 25000, nombre: 'escalera bajando tramo 2' });
  await girarHasta(page, 180);
  r = await caminar(page, ['KeyW'], (q) => q.posicion[0] < 4.6, { ms: 15000, nombre: 'escalera bajando descanso' });
  await girarHasta(page, 270);
  r = await caminar(page, ['KeyW'], (q) => q.posicion[1] < 15.9 && Math.abs(q.altura) < 0.05, { ms: 25000, nombre: 'escalera bajando tramo 1' });
  comprobar(r.cumplio && r.e.nivel === 'P1', `baja caminando al piso 1 (${nivelTxt(r.e)})`);

  // escalera principal abierta del vestíbulo: piso 1 → piso 2 caminando, con el arranque, los tramos, el descanso
  // intermedio y la llegada de escaleras[].partes del piso 1; arriba sigue hasta la entrada «escalera_principal» del piso 2
  // (la espera desde donde se baja) y debe quedar en su recinto
  {
    const P1 = NV.get('P1'), esc = (P1?.escaleras || []).find((x) => /principal/i.test(x.nombre || '') && x.sube_a);
    const tramos = (esc?.partes || []).filter((p) => p.tipo === 'tramo').sort((a, b) => a.z0 - b.z0), di = esc?.partes.find((p) => p.tipo === 'descanso_intermedio');
    const arriba = esc && NV.get(esc.sube_a), entP = arriba?.entradas_recorrido?.find((x) => x.id === 'escalera_principal');
    if (!esc || tramos.length !== 2 || !di || !entP) falla(`escalera principal: faltan en la planta sus dos tramos, el descanso intermedio o la entrada de llegada (${esc?.id})`);
    else {
      const [t1, t2] = tramos.map(ejeTramo), kC = 1 - t1.k, lado = Math.sign(t2.carril - t1.carril);
      const p0 = enEje(t1.k, t1.bajo - t1.s * 0.9, t1.carril), cDi = [(di.rect[0] + di.rect[2]) / 2, (di.rect[1] + di.rect[3]) / 2];
      e = await irA(page, { nivel: 'P1', posicion: p0, rumbo_deg: t1.rumbo, pitch_deg: -12 });
      const arranque = e.nivel === 'P1' && Math.hypot(e.posicion[0] - p0[0], e.posicion[1] - p0[1]) < 0.15;
      await captura(page, op, 'recorrido-escalera-principal-P1');
      await girarHasta(page, t1.rumbo);
      r = await caminar(page, ['KeyW'], (q) => q.posicion[t1.k] * t1.s >= cDi[t1.k] * t1.s, { ms: 30000, nombre: 'escalera principal tramo 1' });
      const hP = r.e.altura, enDescanso = r.cumplio && dentroRect(r.e.posicion, di.rect);
      await girarHasta(page, rumboHacia([0, 0], enEje(kC, lado, 0)));
      r = await caminar(page, ['KeyW'], (q) => q.posicion[kC] * lado >= t2.carril * lado, { ms: 15000, nombre: 'escalera principal descanso' });
      const cruza = r.cumplio && Math.abs(r.e.altura - hP) < 0.05;
      await girarHasta(page, t2.rumbo);
      const llega = await caminar(page, ['KeyW'], (q) => q.nivel === esc.sube_a && q.posicion[t2.k] * t2.s >= t2.alto * t2.s + 0.3, { ms: 30000, nombre: 'escalera principal tramo 2' });
      await captura(page, op, 'recorrido-escalera-principal-llegada-P2');
      const recEnt = recintoEn(arriba, entP.punto);
      r = await caminar(page, ['KeyW'], (q) => q.posicion[t2.k] * t2.s >= entP.punto[t2.k] * t2.s, { ms: 10000, nombre: 'llegada de la escalera principal' });
      R.escalera_principal = { escalera: esc.id, arranque: p0, descanso_m: hP, llegada: llega.e?.posicion, fin: r.e?.posicion, recinto: r.e?.recinto };
      comprobar(arranque && enDescanso && Math.abs(hP - +di.z) < 0.05 && cruza && llega.cumplio && Math.abs(llega.e.altura) < 0.05 && r.cumplio && r.e.nivel === esc.sube_a && r.e.recinto === recEnt?.id,
        `sube por la escalera principal abierta (${esc.id}): arranca en ${p0.map((v) => v.toFixed(2)).join(', ')} (${arranque}), descanso a ${hP} m (planta: ${di.z} m), llega al ${esc.sube_a} a ${llega.e?.altura} m y sigue a «${entP.nombre}» en ${recEnt?.id} (${nivelTxt(r.e)}, ${r.e?.recinto})`);
    }
  }

  // costados de las escaleras: los lados de cada tramo paralelos a la subida (no su arranque ni su llegada) y los de los
  // descansos más altos que el piso (escaleras[].partes de cada nivel), a 0,1, 0,5 y 0,9 de su largo, pero no a menos de su
  // radio más dos celdas de sus extremos (junto a la esquina lo detiene antes la columna o el muro de al lado, a más de esa
  // distancia del borde). Desde el piso de al lado, quien camina hacia ellos se detiene como ante un muro: camina hasta
  // quedar quieto y debe quedar a no menos de su radio menos media celda del borde (no se sube de lado al tramo) y a no más
  // de su radio más dos celdas (lo detuvo el borde, no otra cosa antes ni el tiempo), en el piso y a su altura. Se arranca
  // de la celda de piso más lejana (hasta 1,2 m) de las seguidas desde 0,45 m afuera: contra un muro, el ojo, la franja del
  // núcleo u otra parte no hay ninguna. La escalera principal, abierta al vestíbulo, tiene al menos uno
  {
    const probados = [], malos = [];
    let capturado = false;
    for (const id of NIVELES) {
      const n = NV.get(id), bordes = [];
      for (const esc of n?.escaleras || []) for (const p of esc.partes || []) {
        const [x0, y0, x1, y1] = p.rect, t = p.tipo === 'tramo' ? ejeTramo(p) : null;
        if (!t && !(+p.z > 0.3)) continue;   // descanso a la altura del piso: se entra por cualquier lado
        for (const [a, b, nn] of [[[x0, y0], [x1, y0], [0, -1]], [[x1, y0], [x1, y1], [1, 0]], [[x1, y1], [x0, y1], [0, 1]], [[x0, y1], [x0, y0], [-1, 0]]]) {
          if (t && nn[t.k]) continue;   // arranque o llegada del tramo
          const L = Math.hypot(b[0] - a[0], b[1] - a[1]), m = Math.min(L / 2, RADIO + 2 * CELDA), vistos = new Set();
          for (const f of [0.1, 0.5, 0.9]) {
            const q = Math.min(L - m, Math.max(m, f * L)) / L, pm = [a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q], k = pm.map((v) => v.toFixed(3)).join();
            if (!vistos.has(k)) { vistos.add(k); bordes.push({ esc: esc.id, p, f, nn, pm }); }
          }
        }
      }
      if (!bordes.length) continue;
      await irA(page, { nivel: id });
      for (const bd of bordes) {
        bd.arranque = await page.evaluate(([pm, nn]) => {
          let ult = null;
          for (let d = 0.45; d <= 1.2001; d += 0.05) { const x = pm[0] + nn[0] * d, y = pm[1] + nn[1] * d; if (window.__recorridoQA.sondeo(x, y)?.codigo !== 0) break; ult = [x, y]; }
          return ult;
        }, [bd.pm, bd.nn]);
      }
      for (const bd of bordes.filter((q) => q.arranque)) {
        const e0 = await irA(page, { nivel: id, posicion: bd.arranque, rumbo_deg: rumboHacia(bd.arranque, bd.pm), pitch_deg: 0 });
        r = await caminarHastaParar(page, ['KeyW'], { nombre: `costado ${bd.esc} ${bd.p.tipo}` });
        const d = distRect(r.e.posicion, bd.p.rect), txt = `${id} ${bd.esc} ${bd.p.tipo} en ${bd.pm.map((v) => v.toFixed(2)).join(', ')}`;
        probados.push(`${txt} → a ${d.toFixed(2)} m, h=${r.e.altura}${r.detenido ? '' : ', sin detenerse'}`);
        if (!r.detenido || r.e.nivel !== id || d < RADIO - CELDA / 2 || d > RADIO + 2 * CELDA + 1e-6 || Math.abs(r.e.altura - e0.altura) > 0.05 || r.e.en_muro) malos.push(`${txt}: ${nivelTxt(r.e)} a ${d.toFixed(2)} m del borde${r.detenido ? '' : ' (no se detuvo)'}`);
        if (!capturado && bd.p.tipo === 'tramo' && bd.f === 0.5) { await captura(page, op, `recorrido-escalera-costado-${id}`); capturado = true; }
      }
    }
    R.costados = { probados, malos };
    comprobar(probados.length >= 1 && !malos.length, `los costados de las escaleras que dan a un piso detienen al caminante como un muro, quieto entre ${(RADIO - CELDA / 2).toFixed(2)} y ${(RADIO + 2 * CELDA).toFixed(2)} m del borde, sin subirlo a ellas (${probados.length} puntos: ${probados.join('; ')})${malos.length ? `; mal: ${malos.join('; ')}` : ''}`);
  }

  // pasos entre descanso y tramo en todas las escaleras (escaleras[].partes de cada nivel): cada extremo de cada tramo con
  // su descanso (el de piso o el intermedio del mismo nivel, o el de piso del nivel de arriba en la llegada), en los dos
  // sentidos (del descanso al tramo y del tramo al descanso: así se sube y se baja por cada junta)
  await transiciones(page, NV, R);
  // y con teclas, lo que encontró la revisión: sube el tramo 1 de la escalera principal, cruza el descanso hasta el muro del
  // lado del tramo 2, gira al rumbo del tramo 2 corrido 2,2° hacia ese muro y camina: debe llegar al piso de arriba
  {
    const P1 = NV.get('P1'), esc = (P1?.escaleras || []).find((x) => /principal/i.test(x.nombre || '') && x.sube_a);
    const tramos = (esc?.partes || []).filter((p) => p.tipo === 'tramo').sort((a, b) => a.z0 - b.z0), di = esc?.partes.find((p) => p.tipo === 'descanso_intermedio');
    if (esc && tramos.length === 2 && di) {
      const [t1, t2] = tramos.map(ejeTramo), kC = 1 - t1.k, lado = Math.sign(t2.carril - t1.carril), cDi = [(di.rect[0] + di.rect[2]) / 2, (di.rect[1] + di.rect[3]) / 2];
      e = await irA(page, { nivel: 'P1', posicion: enEje(t1.k, t1.bajo - t1.s * 0.9, t1.carril), rumbo_deg: t1.rumbo, pitch_deg: 0 });
      r = await caminar(page, ['KeyW'], (q) => q.posicion[t1.k] * t1.s >= cDi[t1.k] * t1.s, { ms: 30000, nombre: 'principal junto al muro: tramo 1' });
      await girarHasta(page, rumboHacia([0, 0], enEje(kC, lado, 0)));
      const alMuro = await caminarHastaParar(page, ['KeyW'], { nombre: 'principal junto al muro: descanso' });
      // el rumbo del tramo 2 corrido 2,2° hacia el muro
      const rumbo = [t2.rumbo + 2.2, t2.rumbo - 2.2].find((g) => Math.sign([Math.cos((g * Math.PI) / 180), Math.sin((g * Math.PI) / 180)][kC]) === lado);
      await girarHasta(page, rumbo);
      const sube = await caminar(page, ['KeyW'], (q) => q.nivel === esc.sube_a, { ms: 20000, nombre: 'principal junto al muro: tramo 2' });
      R.principal_muro = { descanso: alMuro.e.posicion, rumbo, fin: sube.e.posicion, nivel: sube.e.nivel };
      comprobar(alMuro.detenido && Math.abs(alMuro.e.altura - +di.z) < 0.05 && sube.cumplio,
        `por la escalera principal, desde el muro del descanso (${alMuro.e.posicion.map((v) => v.toFixed(2)).join(', ')}, h=${alMuro.e.altura}) y con rumbo ${rumbo.toFixed(1)}° sube con teclas el tramo 2 hasta el ${esc.sube_a} (${nivelTxt(sube.e)})`);
    }
  }

  // piso 4 → terraza del piso 3 (en la cubierta, más abajo) por la puerta del paso entre niveles del piso 4
  // (pasos_entre_niveles), y de vuelta por el paso de la terraza que lleva a la misma puerta. Se arranca 1 m adentro de la
  // puerta, frente a ella; la cota de llegada es la de su recinto en la cubierta (z_piso_m)
  {
    const P4 = NV.get('P4'), CUB = NV.get('CUB'), paso = (P4?.pasos_entre_niveles || []).find((p) => p.otro_nivel === 'CUB');
    const pu = paso && (P4.puertas || []).find((q) => q.id === paso.puerta), recP = paso && (P4.recintos || []).find((q) => q.id === paso.recinto);
    const recT = paso && (CUB?.recintos || []).find((q) => q.id === paso.otro_recinto), vuelta = (CUB?.pasos_entre_niveles || []).find((p) => p.otro_nivel === 'P4' && p.puerta_del_otro_nivel === paso?.puerta);
    const n = pu && recP && normalPuerta(P4, pu, recP.poligono);
    if (!paso || !pu || !recT || !vuelta || !n) falla(`terraza: falta el paso del piso 4 a la cubierta con su puerta, su recinto de llegada o el paso de vuelta (${JSON.stringify(paso)})`);
    else {
      const p0 = [paso.punto[0] + n[0], paso.punto[1] + n[1]], zT = +recT.z_piso_m || 0;
      e = await irA(page, { nivel: 'P4', posicion: p0, rumbo_deg: rumboHacia(p0, paso.punto) });
      const arranque = e.nivel === 'P4' && e.recinto === paso.recinto && Math.hypot(e.posicion[0] - p0[0], e.posicion[1] - p0[1]) < 0.15;
      r = await caminar(page, ['KeyW'], (q) => q.nivel === 'CUB', { ms: 15000, nombre: 'puerta a la terraza' });
      comprobar(arranque && r.cumplio && r.e.recinto === recT.id && Math.abs(r.e.altura - zT) < 0.05 && Math.hypot(r.e.posicion[0] - vuelta.punto[0], r.e.posicion[1] - vuelta.punto[1]) < 1.5,
        `del piso 4 sale caminando por ${pu.id} («${pu.nombre}», ${pu.ancho} m) a ${recT.id} a ${zT} m (${nivelTxt(r.e)}, ${r.e.recinto})`);
      await caminar(page, ['KeyW'], () => false, { ms: 1200, nombre: 'terraza' });
      await captura(page, op, 'recorrido-terraza-CUB');
      e = await girarHasta(page, rumboHacia((await estado(page)).posicion, vuelta.punto));
      const enTerraza = e.nivel === 'CUB';
      r = await caminar(page, ['KeyW'], (q) => q.nivel === 'P4', { ms: 15000, nombre: 'vuelta de la terraza' });
      comprobar(enTerraza && r.cumplio && r.e.recinto === paso.recinto && Math.abs(r.e.altura) < 0.05 && Math.hypot(r.e.posicion[0] - paso.punto[0], r.e.posicion[1] - paso.punto[1]) < 1.5,
        `y desde la terraza vuelve caminando al piso 4 por la misma puerta, a ${paso.recinto} (${nivelTxt(r.e)}, ${r.e.recinto})`);
      R.terraza = { puerta: pu.id, arranque: p0, llegada_terraza: recT.id, z_terraza_m: zT };
    }
  }

  // exteriores → bloque técnico por el pasaje de servicio en rampa
  e = await irA(page, { nivel: 'EXT', posicion: [10.25, -18.2], rumbo_deg: 270 });
  r = await caminar(page, ['KeyW'], (q) => q.nivel === 'BT', { ms: 15000, nombre: 'pasaje al bloque técnico' });
  comprobar(r.cumplio && r.e.altura > 1.2, `de los exteriores entra caminando al pasaje del bloque técnico, en rampa (${nivelTxt(r.e)})`);
  await girarHasta(page, 180);
  r = await caminar(page, ['KeyW', 'ShiftLeft'], (q) => q.posicion[0] < -5, { ms: 25000, nombre: 'rampa del pasaje' });
  // la rampa va de ±0,00 en el patio oriente (x = 11,9) a −1,50 en el occidente (x = −19,5): 1,5 m en 31,4 m
  const hEsperada = ((r.e.posicion[0] + 19.5) / 31.4) * 1.5;
  comprobar(r.cumplio && Math.abs(r.e.altura - hEsperada) < 0.05, `baja por la rampa del pasaje: a ${r.e.posicion[0].toFixed(1)} m los pies van a ${r.e.altura} m sobre el patio (rampa: ${hEsperada.toFixed(2)} m)`);

  // cubierta → piso 4 bajando por la escalera norte
  e = await irA(page, { nivel: 'CUB', posicion: [7.25, 15.3], rumbo_deg: 90 });
  r = await caminar(page, ['KeyW'], (q) => q.nivel === 'P4' && q.posicion[1] > 20.9, { ms: 30000, nombre: 'escalera de la cubierta' });
  comprobar(r.cumplio && Math.abs(r.e.altura - 2.1) < 0.1, `baja caminando de la cubierta al descanso intermedio del piso 4 (${nivelTxt(r.e)})`);
  await girarHasta(page, 300, -10);
  await captura(page, op, 'recorrido-escalera-norte-P4');

  // ascensor: se entra caminando a la cabina y se oprime el botón del piso 3
  e = await irA(page, { nivel: 'P2', posicion: [7.4, 5.8], rumbo_deg: 180 });
  r = await caminar(page, ['KeyW'], (q) => /A113-01/.test(q.recinto || ''), { ms: 15000, nombre: 'ascensor' });
  const botones = await page.evaluate(() => [...document.querySelectorAll('.reco-asc:not([hidden]) [data-piso]')].map((b) => b.dataset.piso));
  comprobar(r.cumplio && botones.includes('P3'), `entra caminando a la cabina del ascensor y ve los botones ${botones.join(', ')}`);
  await page.click('.reco-asc [data-piso="P3"]');
  await pausa(500); await cuadros(page, 3);
  e = await estado(page);
  comprobar(e.nivel === 'P3' && Math.hypot(e.posicion[0] - 4.6, e.posicion[1] - 5.8) < 0.3, `el ascensor lleva a la misma cabina en el piso 3 (${nivelTxt(e)})`);
  // R y F (RePág y AvPág) llevan al vestíbulo de ascensores del piso de arriba o de abajo
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus());
  await page.keyboard.press('KeyR'); await pausa(600); await cuadros(page, 3);
  e = await estado(page);
  comprobar(e.nivel === 'P4', `R sube al piso 4 (${nivelTxt(e)})`);
  await page.keyboard.press('PageDown'); await pausa(600); await cuadros(page, 3);
  e = await estado(page);
  comprobar(e.nivel === 'P3', `AvPág baja al piso 3 (${nivelTxt(e)})`);

  // hueco de la escalera abierta del piso 2 (obstaculos_recorrido): su baranda detiene al caminante como un muro (a no
  // menos de su radio menos media celda del borde) por cada tramo de borde con baranda al que se llega caminando, y solo
  // se entra en él bajando por el tramo que llega del piso 1 (borde alto de sus tramos que llegan a la cota del piso 2)
  {
    const P2 = NV.get('P2'), hueco = (P2?.obstaculos_recorrido || []).find((o) => /hueco/i.test(o.id)), pol = hueco?.poligono;
    const nAb = P2 && (P2.escaleras || []).map((x) => NV.get(x.baja_a)).find(Boolean);
    const llegadas = (nAb?.escaleras || []).flatMap((x) => (x.partes || []).filter((p) => p.tipo === 'tramo' && Math.abs(+p.z1 - (P2.z - nAb.z)) < 0.05)).map((p) => {
      const t = ejeTramo(p), [x0, y0, x1, y1] = p.rect;
      return { t, seg: t.k ? [[x0, t.alto], [x1, t.alto]] : [[t.alto, y0], [t.alto, y1]] };
    });
    if (!pol || !llegadas.length) falla(`hueco del piso 2: no está en obstaculos_recorrido o no le llega ningún tramo del piso de abajo (${hueco?.id})`);
    else {
      await irA(page, { nivel: 'P2' });
      // tramos de cada borde: los que coinciden con una llegada no llevan baranda
      const bordes = [];
      for (let i = 0; i < pol.length; i++) {
        const a = pol[i], b = pol[(i + 1) % pol.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]), u = [(b[0] - a[0]) / L, (b[1] - a[1]) / L];
        // normal hacia afuera del hueco
        let nn = [-u[1], u[0]];
        if (enPoligono((a[0] + b[0]) / 2 + nn[0] * 0.05, (a[1] + b[1]) / 2 + nn[1] * 0.05, pol)) nn = [-nn[0], -nn[1]];
        const s = (p) => (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1];
        const libres = llegadas.filter(({ seg: [q, w] }) => distSegmento(q, a, b) < 0.08 && distSegmento(w, a, b) < 0.08)
          .map(({ seg: [q, w], t }) => ({ s0: Math.min(s(q), s(w)), s1: Math.max(s(q), s(w)), t })).sort((x, y) => x.s0 - y.s0);
        let c0 = 0;
        for (const l of libres) { if (l.s0 - c0 > 0.6) bordes.push({ baranda: true, a, u, nn, s0: c0, s1: l.s0 }); bordes.push({ baranda: false, a, u, nn, s0: l.s0, s1: l.s1, t: l.t }); c0 = Math.max(c0, l.s1); }
        if (L - c0 > 0.6) bordes.push({ baranda: true, a, u, nn, s0: c0, s1: L });
      }
      // punto de arranque afuera de cada tramo de borde: el más lejano (hasta 1,2 m) de las celdas libres seguidas desde 0,45 m
      for (const bd of bordes) {
        const m = (bd.s0 + bd.s1) / 2, pm = [bd.a[0] + bd.u[0] * m, bd.a[1] + bd.u[1] * m];
        bd.medio = pm;
        bd.arranque = await page.evaluate(([pm, nn]) => {
          let ult = null;
          for (let d = 0.45; d <= 1.2001; d += 0.05) { const x = pm[0] + nn[0] * d, y = pm[1] + nn[1] * d; if (!window.__recorridoQA.api.libre(x, y)) break; ult = [x, y]; }
          return ult;
        }, [pm, bd.nn]);
      }
      const probados = [], malos = [];
      for (const bd of bordes.filter((x) => x.baranda && x.arranque)) {
        e = await irA(page, { nivel: 'P2', posicion: bd.arranque, rumbo_deg: rumboHacia(bd.arranque, bd.medio) });
        r = await caminar(page, ['KeyW'], (q) => q.nivel !== 'P2' || distPoligono(q.posicion, pol) < 0, { ms: 3500, nombre: `hueco por ${bd.medio.map((v) => v.toFixed(2)).join(', ')}` });
        const d = distPoligono(r.e.posicion, pol);
        probados.push(`${bd.medio.map((v) => v.toFixed(2)).join(', ')} → se detiene a ${d.toFixed(2)} m`);
        if (r.e.nivel !== 'P2' || d < RADIO - CELDA / 2 || Math.abs(r.e.altura) > 0.05 || r.e.en_muro) malos.push(`${bd.medio.map((v) => v.toFixed(2)).join(', ')}: ${nivelTxt(r.e)} a ${d.toFixed(2)} m del borde`);
      }
      const sinAcceso = bordes.filter((x) => x.baranda && !x.arranque).length;
      comprobar(probados.length >= 1 && !malos.length, `la baranda del hueco ${hueco.id} detiene al caminante a ≥ ${(RADIO - CELDA / 2).toFixed(2)} m del borde por los ${probados.length} tramos con baranda a los que se llega (${probados.join('; ')}; ${sinAcceso} sin acceso, contra muros)${malos.length ? `; mal: ${malos.join('; ')}` : ''}`);
      // la llegada: se entra al hueco solo bajando por el tramo, que lleva al piso de abajo
      const bajadas = [];
      for (const bd of bordes.filter((x) => !x.baranda)) {
        if (!bd.arranque) { bajadas.push({ ok: false, txt: `llegada en ${bd.medio.map((v) => v.toFixed(2)).join(', ')} sin celda libre afuera` }); continue; }
        e = await irA(page, { nivel: 'P2', posicion: bd.arranque, rumbo_deg: rumboHacia(bd.arranque, bd.medio) });
        let sobreVacio = 0;
        r = await caminar(page, ['KeyW'], (q) => { if (q.nivel === 'P2' && distPoligono(q.posicion, pol) < -0.1 && q.altura >= 0) sobreVacio++; return q.nivel === nAb.id; }, { ms: 15000, nombre: 'bajando por la llegada del hueco' });
        bajadas.push({ ok: r.cumplio && !sobreVacio && r.e.altura > 0, txt: `${bd.medio.map((v) => v.toFixed(2)).join(', ')} → ${nivelTxt(r.e)}${sobreVacio ? ` (${sobreVacio} veces a la cota del piso dentro del hueco)` : ''}` });
      }
      comprobar(bajadas.length >= 1 && bajadas.every((b) => b.ok), `al hueco solo se entra bajando por la escalera: desde la llegada baja al ${nAb.id} por el tramo (${bajadas.map((b) => b.txt).join('; ')})`);
      R.hueco = { id: hueco.id, probados, sin_acceso: sinAcceso, bajadas: bajadas.map((b) => b.txt) };
    }
  }

  // fichas: carro de paro, analizador en comodato con reactivos, panel solar, manifold de gases y lavamanos
  const buscarU = (f) => page.evaluate((f) => window.__recorridoQA.unidades(f), f);
  const casos = [
    ['carro de paro', { texto: 'carro de paro' }, (u) => u.modelo === 'carro_paro' && u.items > 3, /Implementos internos/],
    ['analizador en comodato', { capa: 'laboratorio' }, (u) => /analizador/.test(u.modelo || '') && u.items > 3, /Implementos internos[\s\S]*(Reactiv|reactiv|Calibrador|Control)/],
    ['panel solar', { texto: 'paneles' }, (u) => u.modelo === 'panel_solar_fila', /Infraestructura|Equipamiento fijo|fotovolt/i],
    ['manifold de gases', {}, (u) => u.modelo === 'manifold_gases', /Clase de riesgo/],
    ['lavamanos', { texto: 'lavamanos' }, (u) => u.modelo === 'lavamanos' && u.nivel === 'P1', /Lo que pide la norma/],
  ];
  R.fichas = {};
  for (const [nombre, filtro, cond, re] of casos) {
    const u = (await buscarU(filtro)).find(cond);
    if (!u) { falla(`ficha de ${nombre}: no hay unidad en el inventario`); continue; }
    e = await irA(page, { unidad: u.id });
    await pausa(200);
    // selección real: clic en el centro de la unidad, que está a la vista frente al caminante
    const v = await page.evaluate((id) => window.__recorridoQA.unidadVista(id), u.id);
    let clic = null;
    if (v) {
      const pt = await page.evaluate((p) => window.__recorridoQA.pantalla(p), [v.x, v.y, v.z + Math.min(v.dim[2] * 0.5, 1.2)]);
      if (pt?.delante) { await page.mouse.click(pt.x, pt.y); await pausa(250); clic = await page.evaluate(() => window.__recorridoQA.ficha()); }
    }
    const txt = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.modo"]')?.textContent || '');
    R.fichas[nombre] = { unidad: u.id, nivel: e.nivel, clic, largo: txt.length };
    comprobar(re.test(txt) && e.nivel === u.nivel, `ficha de ${nombre} (${u.nombre.slice(0, 50)}, ${e.nivel}): ${txt.length} caracteres${clic ? `; el clic seleccionó ${clic.unidad || clic.implemento || clic.recinto}` : ''}`);
    if (nombre === 'carro de paro') {
      const n = await page.evaluate(() => document.querySelectorAll('[data-slot="torre.ficha.modo"] .reco-impl li').length);
      comprobar(n >= 5, `la ficha del carro de paro lista su contenido (${n} implementos)`);
      comprobar(clic && clic.unidad === u.id, 'un clic sobre el carro de paro lo selecciona');
    }
    if (nombre === 'analizador en comodato') {
      await captura(page, op, 'recorrido-ficha-analizador');
      const n = await page.evaluate(() => document.querySelectorAll('[data-slot="torre.ficha.modo"] .reco-impl li').length);
      comprobar(n >= 3, `el analizador en comodato lista sus reactivos (${n} implementos)`);
    }
  }
  // origen de cada exigencia en la ficha (revisión final): EX-PAR-014 es una paráfrasis por confirmar, no una guía secundaria
  const fx = await page.evaluate(() => window.__recorridoQA.fichaTexto({ exigencia: 'EX-PAR-014' }));
  const liPar = (fx?.items || []).find((t) => /11\.6\.4/.test(t)) || '';
  comprobar(fx && /paráfrasis/.test(liPar) && !/guía secundaria/.test(liPar) && !/texto oficial\)/.test(liPar),
    `la ficha con la exigencia EX-PAR-014 la da como paráfrasis por confirmar, no como guía secundaria (${liPar.slice(0, 140)})`);
  // el GeneXpert es por programa o compra (no presupuestado): ni «En la dotación» ni comodato
  const gx = await page.evaluate(() => window.__recorridoQA.fichaTexto({ texto: 'GeneXpert' }));
  comprobar(gx && gx.chips.some((c) => /programa o compra/.test(c)) && !gx.chips.some((c) => /^En la dotación$|en comodato \(no suma\)/.test(c)),
    `la ficha del GeneXpert dice «por programa o compra, no presupuestado» (${(gx?.chips || []).join(' · ')})`);
  // implementos a la vista en el laboratorio (cajas de reactivos y frascos, solo en el recinto actual)
  e = await irA(page, { nivel: 'P2', recinto: 'P2-A082-01' });
  const nImpl = await page.evaluate(() => window.__recorridoQA.nivel().implementos);
  comprobar(nImpl > 0, `en el área de química del laboratorio se ven ${nImpl} implementos (reactivos, frascos y gradillas)`);
  await captura(page, op, 'recorrido-laboratorio-quimica');

  // «Ir a» desde el buscador del inventario completo
  await page.evaluate(() => { const d = document.querySelector('.reco-inv'); d.open = true; d.dispatchEvent(new Event('toggle')); d.scrollIntoView({ block: 'center' }); });
  await esperar(page, () => !!document.querySelector('.reco-busca input[type=search]'), { ms: 5000 });
  const tot0 = await page.evaluate(() => document.querySelector('.reco-totales')?.textContent || '');
  await page.fill('.reco-busca input[type=search]', 'central de gases');
  await esperar(page, (t0) => document.querySelector('.reco-totales')?.textContent !== t0 && document.querySelectorAll('.reco-res [data-ir]').length > 0, { ms: 5000, arg: tot0 });
  const tot = await page.evaluate(() => document.querySelector('.reco-totales')?.textContent || '');
  const primero = await page.evaluate(() => document.querySelector('.reco-res li')?.textContent.trim().slice(0, 80));
  comprobar(/Central de gases/.test(primero), `el buscador pone primero lo que coincide en el nombre («${primero}»)`);
  await page.click('.reco-res [data-ir]');
  await pausa(700); await cuadros(page, 3);
  e = await estado(page);
  const fichaIr = await page.evaluate(() => window.__recorridoQA.ficha());
  comprobar(e.nivel === 'BT' && /A213/.test(e.recinto || '') && fichaIr?.unidad, `«Ir a» desde el buscador lleva al manifold en el bloque técnico (${nivelTxt(e)}; ${tot.trim().slice(0, 60)})`);
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  await captura(page, op, 'recorrido-ir-a-manifold');
  // filtros: nivel, capa y estado cambian los totales
  await page.selectOption('.reco-busca [data-f="nivel"]', 'P2');
  await page.fill('.reco-busca input[type=search]', '');
  await page.selectOption('.reco-busca [data-f="capa"]', 'laboratorio');
  await pausa(300);
  const nLab = await page.evaluate(() => window.__recorridoQA && document.querySelectorAll('.reco-res li').length);
  const totLab = await page.evaluate(() => document.querySelector('.reco-totales')?.textContent || '');
  comprobar(nLab > 0 && /comodato/.test(totLab), `filtro piso 2 + laboratorio: ${totLab.trim().slice(0, 120)}`);

  // cámara: plano cercano junto a un muro, rumbo estable y campo de visión
  e = await irA(page, { nivel: 'P2', posicion: [-6.0, -16.0], rumbo_deg: 270 });
  r = await caminar(page, ['KeyW'], () => false, { ms: 1800, nombre: 'hasta el muro' });
  const cam = await page.evaluate(() => window.__recorridoQA.camara());
  const muro = -16.85 + 0.06;   // cara del muro liviano del corredor del laboratorio
  const dMuro = r.e.posicion[1] - muro;
  comprobar(cam.near <= 0.06 && dMuro < 0.45, `junto a un muro (a ${dMuro.toFixed(2)} m de su cara) el plano cercano es ${cam.near.toFixed(3)} m (≤ 0,06)`);
  comprobar(cam.hfov >= 75, `campo horizontal de ${cam.hfov.toFixed(1)}° en 1400 × 900 (≥ 75°)`);
  await irA(page, { nivel: 'P3', posicion: [-4.5, -4.6], rumbo_deg: 37 });
  await cuadros(page, 60);
  e = await estado(page);
  comprobar(dAng(e.rumbo_deg, 37) <= 0.1, `rumbo leído tras 60 cuadros quieto: ${e.rumbo_deg.toFixed(3)}° (pedido 37°)`);

  // selección: clic sobre un muro no selecciona la unidad del recinto vecino; terminar un arrastre no selecciona
  e = await irA(page, { nivel: 'P2', posicion: [-1.7, -16.0], rumbo_deg: 90, pitch_deg: -5 });
  const vecinas = await page.evaluate(() => window.__recorridoQA.unidades({ recinto: 'P2-A081-01' }).filter((u) => u.montaje === 'piso' || u.montaje === 'sobre'));
  let probada = null;
  for (const u of vecinas) {
    const v = await page.evaluate((id) => window.__recorridoQA.unidadVista(id), u.id);
    if (!v) continue;
    const pt = await page.evaluate((p) => window.__recorridoQA.pantalla(p), [v.x, v.y, v.z + v.dim[2] / 2]);
    const caja = await page.evaluate(() => { const r = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; });
    if (!pt?.delante || pt.x < caja[0] + 60 || pt.x > caja[2] - 200 || pt.y < caja[1] + 60 || pt.y > caja[3] - 30) continue;
    const antes = await page.evaluate(() => window.__recorridoQA.ficha());
    await page.mouse.click(pt.x, pt.y); await pausa(250);
    const despues = await page.evaluate(() => window.__recorridoQA.ficha());
    probada = { u: u.id, antes, despues };
    break;
  }
  comprobar(probada && probada.despues?.unidad !== probada.u, `un clic sobre el muro del corredor no selecciona la unidad de hematología que está detrás${probada ? ` (${probada.u})` : ''}`);
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  await pausa(300);
  const base0 = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
  const f0 = await page.evaluate(() => JSON.stringify(window.__recorridoQA.ficha()));
  const rumbo0 = (await estado(page)).rumbo_deg;
  const cc = await page.evaluate(() => { const r = document.querySelector('#v-torre canvas.gl').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; });
  await page.mouse.move(cc[0], cc[1]); await page.mouse.down(); await page.mouse.move(cc[0] + 30, cc[1] + 4, { steps: 4 }); await page.mouse.move(cc[0] + 80, cc[1] + 8, { steps: 4 }); await page.mouse.up();
  await pausa(250); await cuadros(page, 3);
  const f1 = await page.evaluate(() => JSON.stringify(window.__recorridoQA.ficha()));
  const rumbo1 = (await estado(page)).rumbo_deg;
  comprobar(f0 === f1 && dAng(rumbo0, rumbo1) > 2, `terminar un arrastre gira la mirada (${rumbo0.toFixed(1)}° → ${rumbo1.toFixed(1)}°) y no selecciona`);
  const base1 = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.base"]').innerHTML);
  comprobar(base0 === base1, 'los clics del recorrido no cambian la ficha de «Pisos por servicio» (pisos ocultos)');

  // entrada del botón «Laboratorio» (16.2): parado en la puerta del laboratorio del piso 2, mirando hacia adentro. El punto
  // y el rumbo son los de entradas_recorrido del piso 2; además: celda libre (ni en una columna ni en un muro), a menos de
  // 1 m de una puerta de su recinto, mirando por la normal de esa puerta hacia adentro, en un recinto que da a uno del
  // laboratorio clínico, y la puerta se cruza caminando hacia afuera y de vuelta
  {
    const P2 = NV.get('P2'), ent = (P2?.entradas_recorrido || []).find((x) => x.id === 'laboratorio'), rec = ent && recintoEn(P2, ent.punto);
    const pu = rec && (P2.puertas || []).filter((p) => p.desde === rec.id || p.hacia === rec.id).map((p) => [Math.hypot(p.centro[0] - ent.punto[0], p.centro[1] - ent.punto[1]), p]).sort((a, b) => a[0] - b[0])[0];
    if (!ent || !rec || !pu) falla(`entrada del laboratorio: falta en entradas_recorrido del piso 2, su recinto o una puerta del recinto (${JSON.stringify(ent)})`);
    else {
      const [dPu, puerta] = pu, n = normalPuerta(P2, puerta, rec.poligono), otro = puerta.desde === rec.id ? puerta.hacia : puerta.desde;
      const daAlLab = (rec.acceso || []).some((id) => /laborat/i.test((P2.recintos || []).find((q) => q.id === id)?.servicio_programa || ''));
      e = await irA(page, { laboratorio: true });
      const ok0 = e.nivel === 'P2' && Math.hypot(e.posicion[0] - ent.punto[0], e.posicion[1] - ent.punto[1]) < 0.3 && dAng(e.rumbo_deg, +ent.mirando_deg) < 1 && e.libre && !e.en_muro && e.recinto === rec.id
        && dPu <= 1.0 && n && dAng(+ent.mirando_deg, rumboHacia([0, 0], n)) <= 30 && daAlLab;
      await captura(page, op, 'recorrido-entrada-laboratorio');
      // se sale por la puerta hacia el recinto del otro lado y se vuelve a la entrada
      await girarHasta(page, rumboHacia(e.posicion, puerta.centro));
      const sale = await caminar(page, ['KeyW'], (q) => q.recinto === otro && (q.posicion[0] - puerta.centro[0]) * n[0] + (q.posicion[1] - puerta.centro[1]) * n[1] < -0.5, { ms: 8000, nombre: 'salida por la puerta del laboratorio' });
      await girarHasta(page, rumboHacia(sale.e.posicion, ent.punto));
      const fondo = (p) => (p[0] - puerta.centro[0]) * n[0] + (p[1] - puerta.centro[1]) * n[1];   // cuánto adentro de la puerta
      const vuelve = await caminar(page, ['KeyW'], (q) => q.recinto === rec.id && fondo(q.posicion) >= fondo(ent.punto) - 0.05, { ms: 8000, nombre: 'vuelta a la entrada del laboratorio' });
      comprobar(ok0 && sale.cumplio && vuelve.cumplio,
        `irA({ laboratorio: true }) deja al caminante en «${ent.nombre}» (${rec.id}, a ${dPu.toFixed(2)} m de ${puerta.id}) mirando hacia adentro (${nivelTxt(e)}; libre ${e.libre}); la puerta se cruza a ${otro} (${sale.cumplio}) y de vuelta (${vuelve.cumplio})`);
      R.laboratorio = { entrada: ent.punto, recinto: rec.id, puerta: puerta.id, otro };
    }
  }

  // capas: faltantes, cumplimiento, contraste e infraestructura
  for (const c of ['faltantes', 'estado', 'contraste', 'infraestructura']) {
    const b = await page.$(`[data-capa="${c}"]`);
    if (!b || await b.isDisabled()) { console.log(`  (capa ${c} sin datos)`); continue; }
    await b.click(); await pausa(200);
  }
  await irA(page, { nivel: 'P1', entrada: 'urgencias' });
  await captura(page, op, 'recorrido-capas-P1');
  const stCapas = await page.evaluate(() => window.__recorridoQA.nivel());
  comprobar(stCapas.equipos, `con las capas encendidas el piso 1 dibuja ${stCapas.equipos?.llamadas} llamadas de equipos`);
  for (const c of ['faltantes', 'estado', 'contraste', 'infraestructura']) { const b = await page.$(`[data-capa="${c}"]`); if (b && !(await b.isDisabled())) { await b.click(); await pausa(100); } }

  const dz = await desborde(page);
  comprobar(dz.ok, `guion: sin desborde horizontal${dz.ok ? '' : ` ${dz.culpables.join(', ')}`}`);
  const internos = await textosInternos(page, '#v-torre');
  comprobar(!internos.length, `guion: textos sin rutas ni claves internas${internos.length ? `: ${internos.slice(0, 3).join(' | ')}` : ''}`);
  if (!informar(registro, 'recorrido guion')) falla('guion: consola con errores');
  resultado.guion = R;
  await cerrar();
}

// ---------------------------------------------------------------- teclado (13.3)
async function teclado() {
  console.log('teclado: solo teclado, atajos del navegador, campos del panel, foco perdido y movimiento reducido');
  let { page, registro, cerrar } = await pagina({ tema: 'oscuro' });
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  // solo teclado: el botón «Recorrer por dentro» con Enter deja el foco en el recuadro
  await page.focus('button[data-modo-torre="recorrido"]');
  await page.keyboard.press('Enter');
  await esperar(page, () => !!window.__torreQA?.recorrido?.estado?.(), { ms: 60000 });
  await pausa(300);
  const foco = await page.evaluate(() => document.activeElement?.matches?.('#v-torre .stage') && document.activeElement.getAttribute('role'));
  comprobar(foco === 'application', 'con Enter en «Recorrer por dentro» el foco queda en el recuadro (role="application")');
  let e0 = await estado(page);
  await page.keyboard.down('ArrowUp'); await pausa(1200); await page.keyboard.up('ArrowUp'); await cuadros(page, 2);
  let e1 = await estado(page);
  comprobar(Math.hypot(e1.posicion[0] - e0.posicion[0], e1.posicion[1] - e0.posicion[1]) > 0.2 || e1.nivel !== e0.nivel, `las flechas mueven al caminante (${nivelTxt(e0)} → ${nivelTxt(e1)})`);
  await page.keyboard.press('Tab');
  const enPanel = await page.evaluate(() => !!document.activeElement?.closest?.('[data-slot="torre.panel.recorrido"]'));
  comprobar(enPanel, 'Tab pasa del recuadro al panel');
  await page.keyboard.press('Enter'); await pausa(200);
  const fichaTxt = await page.evaluate(() => document.querySelector('[data-slot="torre.ficha.modo"]')?.innerText || '');
  comprobar(fichaTxt.length > 20, `Enter abre una ficha desde el panel (${fichaTxt.split('\n')[0].slice(0, 60)})`);
  // un botón de la lista del recinto con el teclado
  const hayLista = await page.evaluate(() => { const b = document.querySelector('.reco-lista-rec button[data-unidad]'); if (b) b.focus(); return !!b; });
  if (hayLista) { await page.keyboard.press('Enter'); await pausa(200); const f = await page.evaluate(() => window.__recorridoQA.ficha()); comprobar(f?.unidad, 'Enter sobre una fila de la lista del recinto abre la ficha de la unidad'); }
  // atajos del navegador sin interceptar
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus());
  const atajos = await page.evaluate(() => [['KeyR', { ctrlKey: true }], ['KeyF', { ctrlKey: true }], ['KeyD', { metaKey: true }], ['KeyW', { altKey: true }]].map(([code, m]) => {
    const ev = new KeyboardEvent('keydown', { code, key: code.slice(3).toLowerCase(), bubbles: true, cancelable: true, ...m });
    document.querySelector('#v-torre .stage').dispatchEvent(ev);
    window.dispatchEvent(new KeyboardEvent('keyup', { code, bubbles: true, ...m }));
    return ev.defaultPrevented;
  }));
  await cuadros(page, 3);
  const e2 = await estado(page);
  comprobar(!atajos.some(Boolean) && e2.nivel === e1.nivel, `Ctrl+R, Ctrl+F, Cmd+D y Alt+W no los intercepta el recorrido (defaultPrevented: ${atajos.join(', ')})`);
  // escribir en un campo del panel no mueve al caminante
  await page.evaluate(() => { const d = document.querySelector('.reco-inv'); d.open = true; d.dispatchEvent(new Event('toggle')); });
  await esperar(page, () => !!document.querySelector('.reco-busca input[type=search]'), { ms: 5000 });
  e0 = await estado(page);
  await page.focus('.reco-busca input[type=search]');
  await page.keyboard.type('wwwwssssaaddrf', { delay: 40 });
  await pausa(300);
  e1 = await estado(page);
  comprobar(e0.posicion.join() === e1.posicion.join() && e0.nivel === e1.nivel, 'escribir «wsad r f» en el buscador no mueve al caminante ni cambia de nivel');
  // perder el foco de la ventana con una tecla oprimida detiene al caminante
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus());
  await page.keyboard.down('KeyW'); await pausa(500);
  await page.evaluate(() => window.dispatchEvent(new Event('blur')));
  await cuadros(page, 2);
  e0 = await estado(page);
  await pausa(600); await cuadros(page, 3);
  e1 = await estado(page);
  await page.keyboard.up('KeyW');
  comprobar(e0.posicion.join() === e1.posicion.join(), `al perder el foco con W oprimida el caminante se detiene (${e0.posicion.join(', ')} = ${e1.posicion.join(', ')})`);
  // Esc sale del recorrido (sin puntero tomado)
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus());
  await page.keyboard.press('Escape'); await pausa(400);
  const modo = await page.evaluate(() => window.__torreQA.modo());
  comprobar(modo === 'torre', `Esc sale del recorrido y vuelve a «Con la torre» (modo ${modo})`);
  if (!informar(registro, 'recorrido teclado')) falla('teclado: consola con errores');
  await cerrar();

  // movimiento reducido: cambios de nivel sin fundido
  ({ page, registro, cerrar } = await pagina({ tema: 'claro', movimientoReducido: true }));
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  await entrar(page, { nivel: 'P2', entrada: 'ascensores' });
  await page.evaluate(() => { window.__fundidos = 0; new MutationObserver(() => { if (document.querySelector('.reco-fundido.on')) window.__fundidos++; }).observe(document.querySelector('.reco-fundido'), { attributes: true }); document.querySelector('#v-torre .stage').focus(); });
  await page.keyboard.press('KeyR'); await pausa(300); await cuadros(page, 2);
  const er = await estado(page);
  const sinF = await page.evaluate(() => ({ f: window.__fundidos, u: window.__recorridoQA.ultimoFundido() }));
  comprobar(er.nivel === 'P3' && !sinF.f && !sinF.u, `con prefers-reduced-motion el cambio de piso es instantáneo (sin fundido; ${nivelTxt(er)})`);
  if (!informar(registro, 'recorrido movimiento reducido')) falla('movimiento reducido: consola con errores');
  await cerrar();
}

// ---------------------------------------------------------------- presupuesto del 5.2 y 16.6
async function presupuesto() {
  console.log('presupuesto: llamadas y triángulos por nivel');
  const filas = {};
  for (const [nombre, telefono, maxL, maxT] of [['baja 390 × 844', true, 30, 120000], ['media 1400 × 900', false, 45, 150000]]) {
    const { page, registro, cerrar } = await pagina({ telefono });
    await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
    // se entra por la cubierta: así cada nivel del ciclo se arma al pedirlo (el tiempo de la primera entrada incluye la
    // compilación de los programas y la carga de la vista, y se informa aparte)
    await entrar(page, { nivel: 'CUB' });
    const n0 = await page.evaluate(() => window.__recorridoQA.nivel());
    console.log(`  (primera entrada, en frío: ${Math.round(n0.ms)} ms)`);
    // el peor caso: con la capa de faltantes (malla fantasma del cierre de brechas) y la infraestructura encendidas
    await page.click('[data-capa="faltantes"]');
    for (const id of NIVELES) {
      await irA(page, { nivel: id });
      const s = await page.evaluate(() => window.__torreQA.stats());
      const n = await page.evaluate(() => window.__recorridoQA.nivel());
      filas[`${id} ${nombre}`] = { llamadas: s.llamadas, triangulos: s.triangulos, calidad: n.calidad, ms: Math.round(n.ms), tiempos: Object.fromEntries(Object.entries(n.tiempos || {}).map(([k, v]) => [k, Math.round(v)])) };
      comprobar(s.llamadas <= maxL && s.triangulos <= maxT, `${id} en ${nombre} (calidad ${n.calidad}): ${s.llamadas} llamadas ≤ ${maxL} y ${s.triangulos.toLocaleString('es-CO')} triángulos ≤ ${maxT.toLocaleString('es-CO')}; armado en ${Math.round(n.ms)} ms`);
      if (!telefono) comprobar(n.ms <= 300, `${id}: el nivel se arma en ${Math.round(n.ms)} ms (≤ 300 ms en escritorio)`);
    }
    // el recinto más cargado: el laboratorio de química (implementos) y la sala de observación de urgencias
    for (const d of [{ nivel: 'P2', recinto: 'P2-A082-01' }, { nivel: 'P1', recinto: 'P1-A024-01' }]) {
      await irA(page, d);
      const s = await page.evaluate(() => window.__torreQA.stats());
      comprobar(s.llamadas <= maxL && s.triangulos <= maxT, `${d.recinto} en ${nombre}: ${s.llamadas} llamadas y ${s.triangulos.toLocaleString('es-CO')} triángulos`);
    }
    const cam = await page.evaluate(() => window.__recorridoQA.camara());
    if (telefono) comprobar(cam.hfov >= 70, `campo horizontal de ${cam.hfov.toFixed(1)}° en 390 × 844 (≥ 70°)`);
    // ningún modelo del catálogo hace que mergeGeometries devuelva null
    const nulos = await page.evaluate(async () => {
      const E = await import('./js/equipos3d.js');
      const malos = [];
      for (const m of E.MODELOS) for (const lod of [0, 1]) { const g = E.geometria(m, null, lod); if (!g || !g.attributes.position) malos.push(`${m}/${lod}`); g?.dispose(); }
      return { n: E.MODELOS.size, malos };
    });
    comprobar(!nulos.malos.length, `los ${nulos.n} modelos del catálogo dan geometría en LOD0 y LOD1 (sin null)`);
    if (!informar(registro, `recorrido presupuesto ${nombre}`)) falla(`presupuesto ${nombre}: consola con errores`);
    await cerrar();
  }
  resultado.presupuesto = filas;
}

// ---------------------------------------------------------------- salida: la vista vuelve a ser la de antes
import { inflateSync } from 'node:zlib';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
function png(buf) {
  // decodificador mínimo de PNG (8 bits, RGB o RGBA, sin entrelazado): lo que produce Chromium en las capturas
  let p = 8, ancho = 0, alto = 0, tipo = 0;
  const datos = [];
  while (p < buf.length) {
    const n = buf.readUInt32BE(p), t = buf.toString('latin1', p + 4, p + 8);
    if (t === 'IHDR') { ancho = buf.readUInt32BE(p + 8); alto = buf.readUInt32BE(p + 12); tipo = buf[p + 17]; }
    if (t === 'IDAT') datos.push(buf.subarray(p + 8, p + 8 + n));
    p += 12 + n;
  }
  const bpp = tipo === 6 ? 4 : 3, raw = inflateSync(Buffer.concat(datos)), fila = ancho * bpp, out = Buffer.alloc(alto * fila);
  for (let y = 0; y < alto; y++) {
    const f = raw[y * (fila + 1)], src = raw.subarray(y * (fila + 1) + 1, (y + 1) * (fila + 1)), o = y * fila;
    for (let x = 0; x < fila; x++) {
      const a = x >= bpp ? out[o + x - bpp] : 0, b = y ? out[o - fila + x] : 0, c = x >= bpp && y ? out[o - fila + x - bpp] : 0;
      let v = src[x];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const q = a + b - c, pa = Math.abs(q - a), pb = Math.abs(q - b), pc = Math.abs(q - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      out[o + x] = v & 255;
    }
  }
  return { ancho, alto, bpp, px: out };
}
// variedad de una captura: parte del recuadro que cubre el color más frecuente (cuantizado a 16 niveles por canal) y
// desviación estándar de la luminancia (una vista contra un muro sale de un solo gris)
function variedad(img) {
  const n = img.ancho * img.alto, cuenta = new Map();
  let s = 0, s2 = 0;
  for (let i = 0; i < n; i++) {
    const r = img.px[i * img.bpp], g = img.px[i * img.bpp + 1], b = img.px[i * img.bpp + 2], l = 0.2126 * r + 0.7152 * g + 0.0722 * b, k = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
    s += l; s2 += l * l;
    cuenta.set(k, (cuenta.get(k) || 0) + 1);
  }
  const m = s / n;
  return { dominante: Math.max(...cuenta.values()) / n, sd: Math.sqrt(Math.max(0, s2 / n - m * m)) };
}
function diferencia(a, b) {
  if (a.ancho !== b.ancho || a.alto !== b.alto) return 1;
  let dist = 0;
  const n = a.ancho * a.alto;
  for (let i = 0; i < n; i++) {
    let d = 0;
    for (let k = 0; k < 3; k++) d = Math.max(d, Math.abs(a.px[i * a.bpp + k] - b.px[i * b.bpp + k]));
    if (d > 24) dist++;
  }
  return dist / n;
}
// resolución del motor (pixel ratio de la resolución adaptativa de core.js): la lee y, con dpr, la fija. Los cuadros lentos
// del recorrido (WebGL por software, más con la máquina cargada) la bajan de 1,5 a 1,25 o 1 en el teléfono y ya no vuelve
// a subir; dibujada a otra resolución la misma vista cambia en los bordes (el 2 % de los píxeles), así que las vistas de
// antes y de después se comparan a la misma
const resolucion = (page, dpr = null) => page.evaluate(async (dpr) => {
  const { engine } = await import(new URL('js/core.js', document.baseURI).href);
  if (dpr != null && engine.dpr !== dpr && engine.active) { engine.dpr = dpr; engine.applyDpr(engine.active); engine.active.invalidate(true); }
  return engine.dpr;
}, dpr);
// espera a que el recuadro deje de cambiar (vuelos de cámara, fundidos, cargas perezosas) en vez de una espera fija, que con
// la máquina cargada se queda corta: capturas del recorte cada 3 cuadros y 150 ms hasta que tres seguidas salen iguales
// (menos del 0,1 % de píxeles distintos entre cada par), con la resolución dpr si se pide; devuelve la última y si se
// estabilizó
async function cuadroEstable(page, recorte, { ms = 30000, dpr = null } = {}) {
  const t0 = Date.now();
  let prev = null, iguales = 0, img = null, buf = null;
  while (Date.now() - t0 < ms) {
    if (dpr != null) await resolucion(page, dpr);
    await cuadros(page, 3); await pausa(150);
    img = png(buf = await page.screenshot({ clip: recorte }));
    iguales = prev && diferencia(prev, img) < 0.001 ? iguales + 1 : 0;
    if (iguales >= 2) return { img, buf, estable: true, ms: Date.now() - t0 };
    prev = img;
  }
  return { img, buf, estable: false, ms: Date.now() - t0 };
}
async function salida() {
  console.log('salida: controles, fov y la vista «Con la torre» como antes');
  for (const telefono of [false, true]) {
    const nombre = telefono ? 'teléfono' : 'escritorio';
    const { page, registro, cerrar } = await pagina({ telefono, movimientoReducido: true });
    await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
    await cuadros(page, 5);
    const recorte = await page.evaluate(() => { const r = document.querySelector('#v-torre .stage').getBoundingClientRect(); return { x: r.left, y: r.top, width: r.width, height: r.height }; });
    await cuadroEstable(page, recorte);
    // «Hoy» y «Con la torre» antes de entrar, cada uno con el cuadro ya quieto, a la resolución de entonces
    const dpr0 = await resolucion(page);
    await page.evaluate(() => window.__torreQA.modo('hoy'));
    const hoy0 = await cuadroEstable(page, recorte, { dpr: dpr0 });
    await page.evaluate(() => window.__torreQA.modo('torre'));
    const antes = await cuadroEstable(page, recorte, { dpr: dpr0 });
    await entrar(page, { nivel: 'P2', entrada: 'laboratorio' });
    await irA(page, { nivel: 'P3' });
    const c0 = await page.evaluate(() => window.__recorridoQA.antes());
    // sale la persona (botón «Salir» de la barra)
    await page.click('.reco-barra [data-acc="salir"]');
    const dpr1 = await resolucion(page);
    const despues = await cuadroEstable(page, recorte, { dpr: dpr0 });
    const c1 = await page.evaluate(() => window.__recorridoQA.controles());
    const iguales = Object.keys(c0).every((k) => (typeof c0[k] === 'number' ? Math.abs(c0[k] - c1[k]) < 1e-6 : c0[k] === c1[k]));
    comprobar(iguales && Math.abs(c1.fov - 36) < 1e-6, `${nombre}: al salir, fov = ${c1.fov}° y los controles como antes (${JSON.stringify(c1)})`);
    const ext = await page.evaluate(() => window.__torreQA.exterior());
    comprobar(ext === null, `${nombre}: el exterior vuelve a verse entero (oculto: ${ext})`);
    const d1 = diferencia(antes.img, despues.img);
    await page.evaluate(() => window.__torreQA.modo('hoy'));
    const hoy1 = await cuadroEstable(page, recorte, { dpr: dpr0 });
    const d2 = diferencia(hoy0.img, hoy1.img);
    await captura(page, op, `recorrido-salida-hoy-${telefono ? 'telefono' : 'escritorio'}`);
    // las dos vistas se distinguen entre sí: cada captura es de su modo y no la del anterior que todavía no cambiaba
    const quietos = [hoy0, antes, despues, hoy1].every((q) => q.estable), tiempos = [hoy0, antes, despues, hoy1].map((q) => (q.ms / 1000).toFixed(1)).join(', ');
    const d0 = diferencia(hoy0.img, antes.img);
    if (!(quietos && d0 > 0.02 && d1 < 0.02 && d2 < 0.02)) {
      await mkdir(op.salida, { recursive: true });
      for (const [k, q] of Object.entries({ hoy0, antes, despues, hoy1 })) await writeFile(join(op.salida, `recorrido-salida-${telefono ? 'telefono' : 'escritorio'}-${k}.png`), q.buf);
    }
    comprobar(quietos && d0 > 0.02 && d1 < 0.02 && d2 < 0.02, `${nombre}: «Con la torre» y «Hoy» se ven igual que antes de entrar (píxeles distintos: ${(d1 * 100).toFixed(2)} % y ${(d2 * 100).toFixed(2)} %; entre las dos vistas, ${(d0 * 100).toFixed(1)} %; cuadro quieto en ${tiempos} s; resolución ×${dpr0}${dpr1 !== dpr0 ? `, que el recorrido bajó a ×${dpr1} y se devolvió para comparar` : ''}${quietos ? '' : ', alguno sin quedar quieto en 30 s'})`);
    if (!informar(registro, `recorrido salida ${nombre}`)) falla(`salida ${nombre}: consola con errores`);
    await cerrar();
  }
}

// ---------------------------------------------------------------- juego: escalera de evacuación, salto, espectador y pantalla completa
// mantiene teclas hasta la condición sin vigilar los muros (el espectador los atraviesa); devuelve el último estado
async function mantener(page, teclas, cond, ms = 30000) {
  await alRecuadro(page);
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus({ preventScroll: true }));
  for (const t of teclas) await page.keyboard.down(t);
  const t0 = Date.now();
  let e = null;
  try { while (Date.now() - t0 < ms) { await pausa(80); e = await estado(page); if (cond(e)) break; } } finally { for (const t of [...teclas].reverse()) await page.keyboard.up(t); }
  await pausa(80);
  return estado(page);
}
async function juego() {
  console.log('juego: escalera de evacuación por su puerta, salto, espectador y pantalla completa');
  const { page, registro, cerrar } = await pagina({ tema: 'claro' });
  await page.evaluate(() => document.querySelector('#v-torre .stage').scrollIntoView({ block: 'center' }));
  comprobar(await entrar(page), 'entra al recorrido');
  // la puerta de la escalera norte del piso 2 está en el muro x = 3,1 (y = 15,3): desde el corredor, caminando al oriente
  let e = await irA(page, { nivel: 'P2', posicion: [2.3, 15.3], rumbo_deg: 0 });
  let r = await caminar(page, ['KeyW'], (q) => q.recinto === 'P2-A112-01', { ms: 20000, nombre: 'puerta de la escalera norte' });
  comprobar(r.cumplio, `entra a la escalera de evacuación norte por su puerta desde el corredor (${nivelTxt(r.e)}, ${r.e.recinto})`);
  // salto: la altura máxima de los pies en los cuadros que siguen a Espacio
  e = await irA(page, { nivel: 'P2', entrada: 'ascensores' });
  await page.evaluate(() => document.querySelector('#v-torre .stage').focus({ preventScroll: true }));
  const alturas = await page.evaluate(async () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', key: ' ', bubbles: true }));
    const out = [];
    for (let k = 0; k < 90; k++) { await new Promise((q) => requestAnimationFrame(q)); out.push(window.__recorridoQA.api.estado().altura); }
    window.dispatchEvent(new KeyboardEvent('keyup', { code: 'Space', key: ' ', bubbles: true }));
    return out;
  });
  const hmax = Math.max(...alturas), hfin = alturas[alturas.length - 1];
  comprobar(hmax > e.altura + 0.9 && hmax <= e.altura + 1.21 && Math.abs(hfin - e.altura) < 0.01, `salta: los pies llegan a ${hmax.toFixed(2)} m y vuelven al piso (${hfin})`);
  // bajo el dintel de una puerta (2,10 m) el salto se detiene: los pies no pasan de 2,10 − 1,72 = 0,38 m
  e = await irA(page, { nivel: 'P2', posicion: [3.1, 15.3], rumbo_deg: 0 });
  const enVano = await page.evaluate(async () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', key: ' ', bubbles: true }));
    let m = 0;
    for (let k = 0; k < 60; k++) { await new Promise((q) => requestAnimationFrame(q)); m = Math.max(m, window.__recorridoQA.api.estado().altura); }
    window.dispatchEvent(new KeyboardEvent('keyup', { code: 'Space', key: ' ', bubbles: true }));
    return m;
  });
  comprobar(enVano > 0.2 && enVano <= 0.39, `bajo el dintel de la puerta de la escalera el salto se detiene (pies hasta ${enVano.toFixed(2)} m)`);
  // salta hacia una unidad hasta quedar parado encima: una cama del piso 3 sin nada colgado encima y una fila de paneles
  // de la terraza (4,20 m bajo el nivel de la cubierta: su altura se mide desde ese piso)
  async function subirA(id) {
    e = await irA(page, { unidad: id });
    const v = await page.evaluate((u) => window.__recorridoQA.unidadVista(u), id);
    await girarHasta(page, (Math.atan2(v.y - e.posicion[1], v.x - e.posicion[0]) * 180) / Math.PI, 0);
    const piso = e.altura;
    // «Ir a» abre la ficha y el foco puede quedar en ella: Espacio solo salta con el foco en el recuadro (como las flechas)
    await page.evaluate(() => document.querySelector('#v-torre .stage').focus({ preventScroll: true }));
    for (let k = 0; k < 6; k++) {
      await page.keyboard.down('KeyW'); await page.keyboard.press('Space'); await pausa(700); await page.keyboard.up('KeyW');
      // con pocos cuadros por segundo el salto dura más que la pausa: se lee ya en el suelo (o encima)
      await esperar(page, () => !window.__recorridoQA.api.estado()?.en_el_aire, { ms: 8000 });
      e = await estado(page);
      if (e.altura > piso + 0.3 && !e.en_el_aire) break;
    }
    return { e, piso, alto: v.dim[2] };
  }
  await irA(page, { nivel: 'P3', entrada: 'estacion' });
  const cama = await page.evaluate(() => {
    // lo que cuelga sobre la cabeza (como en techosBajos del recorrido): del cielo o de la pared desde 1,80 m, sin las cortinas
    const Q = window.__recorridoQA, encima = Q.unidades({}).filter((u) => u.nivel === 'P3' && (u.montaje === 'cielo' || u.montaje === 'pared') && u.modelo !== 'riel_cortina')
      .map((u) => Q.unidadVista(u.id)).filter((v) => v && v.z >= 1.8);
    return Q.unidades({ texto: 'cama' }).filter((u) => u.nivel === 'P3' && u.montaje === 'piso')
      .find((u) => { const v = Q.unidadVista(u.id); return v && v.dim[2] < 1.15 && !encima.some((q) => Math.hypot(q.x - v.x, q.y - v.y) < 1.6); });
  });
  if (comprobar(!!cama, `hay una cama de piso en el piso 3 sin nada colgado encima (${cama?.id})`)) {
    const r1 = await subirA(cama.id);
    comprobar(r1.e.altura > r1.piso + 0.3 && !r1.e.en_el_aire && r1.e.libre && !r1.e.en_muro, `queda parado sobre la cama (pies a ${r1.e.altura} m; libre ${r1.e.libre}, en muro ${r1.e.en_muro})`);
  }
  await irA(page, { nivel: 'CUB', entrada: 'terraza' });
  const fila = await page.evaluate(() => window.__recorridoQA.unidades({ texto: 'fotovolt' }).find((u) => u.nivel === 'CUB' && u.montaje === 'piso' && (window.__recorridoQA.unidadVista(u.id)?.z ?? 0) < -4));
  if (comprobar(!!fila, `hay una fila de paneles en la terraza (${fila?.id})`)) {
    const r2 = await subirA(fila.id);
    comprobar(r2.e.nivel === 'CUB' && r2.e.altura > r2.piso + 0.3 && !r2.e.en_el_aire, `queda parado sobre la fila de paneles de la terraza (pies a ${r2.e.altura} m; piso ${r2.piso} m)`);
  }
  // dejar de volar en una escalera: sobre el tramo bajo los pies (el del piso 1, ya en el nivel del piso 2), no sobre el de
  // arriba (que llevaría al piso 3)
  e = await irA(page, { nivel: 'P1', posicion: [4.45, 15.3], rumbo_deg: 90 });
  r = await caminar(page, ['KeyW'], (q) => q.posicion[1] > 20.9, { ms: 30000, nombre: 'juego: escalera tramo 1' });
  await girarHasta(page, 0);
  r = await caminar(page, ['KeyW'], (q) => q.posicion[0] > 7.1, { ms: 15000, nombre: 'juego: escalera descanso' });
  await girarHasta(page, 270);
  r = await caminar(page, ['KeyW'], (q) => q.nivel === 'P2' && q.posicion[1] < 18.5, { ms: 25000, nombre: 'juego: escalera tramo 2' });
  const hEsc = r.e.altura;
  await page.keyboard.press('KeyV'); await cuadros(page, 3); await page.keyboard.press('KeyV'); await pausa(800);
  e = await estado(page);
  comprobar(r.cumplio && e.nivel === 'P2' && Math.abs(e.altura - hEsc) < 0.15 && !e.espectador, `al dejar de volar en la escalera queda sobre el tramo bajo los pies (${nivelTxt(e)}; antes a ${hEsc} m)`);
  // espectador: sube con Espacio a través de la losa al piso 3, vuela al occidente por donde no se camina y aterriza
  e = await irA(page, { nivel: 'P2', entrada: 'ascensores' });
  await page.keyboard.press('KeyV');
  await cuadros(page, 2);
  comprobar(await page.evaluate(() => document.querySelector('.reco-barra [data-acc="espectador"]').getAttribute('aria-pressed') === 'true'), 'V activa el modo espectador');
  e = await mantener(page, ['Space'], (q) => q.nivel === 'P3', 40000);
  comprobar(e.nivel === 'P3', `el espectador sube a través de la losa al piso 3 (${nivelTxt(e)})`);
  e = await girarHasta(page, 180, 0);
  const p0 = e.posicion;
  e = await mantener(page, ['KeyW'], (q) => p0[0] - q.posicion[0] > 6, 40000);
  const tapados = await page.evaluate(([a, b]) => { let n = 0; for (let t = 0; t <= 1; t += 0.01) if (!window.__recorridoQA.api.libre(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))) n++; return n; }, [p0, e.posicion]);
  comprobar(p0[0] - e.posicion[0] > 6 && Math.abs(e.posicion[1] - p0[1]) < 0.05 && tapados > 0 && e.nivel === 'P3', `vuela ${(p0[0] - e.posicion[0]).toFixed(1)} m en línea recta por el piso 3 a través de ${tapados} puntos donde no se camina`);
  await page.keyboard.press('KeyV');
  await pausa(1500);
  e = await estado(page);
  comprobar(e.nivel === 'P3' && e.libre && !e.en_muro && Math.abs(e.altura) < 0.05, `al volver a caminar queda de pie en una celda libre del piso 3 (${nivelTxt(e)})`);
  // pantalla completa: el botón, la ficha en el lateral y Esc (el primero puede soltar el puntero). Se entra sin ficha
  // abierta y se elige algo adentro: al salir, la tarjeta de la ficha debe verse
  if (cama) await irA(page, { unidad: cama.id });
  await page.evaluate(() => { const f = document.querySelector('[data-slot="torre.ficha.modo"]'); f.innerHTML = ''; f.hidden = true; });
  await alRecuadro(page);
  await page.click('.reco-barra [data-acc="pantalla"]');
  await esperar(page, () => document.querySelector('#v-torre .stage').classList.contains('reco-pantalla'), { ms: 10000 });
  await pausa(600);
  const fs = await page.evaluate(() => { const st = document.querySelector('#v-torre .stage'); return { w: st.clientWidth, h: st.clientHeight, vw: innerWidth, vh: innerHeight, ficha: !!st.querySelector('.reco-fs-ficha [data-slot="torre.ficha.modo"]') }; });
  comprobar(fs.w >= fs.vw - 2 && fs.h >= fs.vh - 2 && fs.ficha, `pantalla completa: el recuadro ocupa ${fs.w} × ${fs.h} de ${fs.vw} × ${fs.vh} y la ficha pasa a su lateral`);
  // la captura en pantalla completa puede no terminar en Chromium sin pantalla (espera tipografías): no decide la prueba
  const elegidaFs = await page.evaluate(() => { const Q = window.__recorridoQA, o = Q.objetivo(), q = o && Q.pantalla(o.punto); if (q) Q.seleccionarEn(q.x, q.y); return Q.ficha()?.unidad || null; });
  comprobar(!!elegidaFs, `en pantalla completa se elige la cama con un clic (${elegidaFs})`);
  await captura(page, op, 'recorrido-pantalla-completa').catch((err) => console.log(`    aviso: sin captura en pantalla completa (${String(err.message || err).split('\n')[0]})`));
  for (let k = 0; k < 2 && (await page.evaluate(() => document.querySelector('#v-torre .stage').classList.contains('reco-pantalla'))); k++) { await page.keyboard.press('Escape'); await pausa(400); }
  await pausa(200);
  const fin = await page.evaluate(() => {
    const slot = document.querySelector('[data-slot="torre.ficha"] > [data-slot="torre.ficha.modo"]');
    return { pantalla: document.querySelector('#v-torre .stage').classList.contains('reco-pantalla'), completa: !!document.fullscreenElement, ficha: !!slot && !slot.hidden && !document.querySelector('[data-slot="torre.ficha"]').hidden };
  });
  e = await estado(page);
  comprobar(!fin.pantalla && !fin.completa && fin.ficha && !!e, `Esc sale de la pantalla completa, la ficha elegida adentro vuelve a su tarjeta y se ve, y el recorrido sigue (${JSON.stringify(fin)})`);
  if (!informar(registro, 'recorrido juego')) falla('juego: consola con errores');
  await cerrar();
}

await (async () => {
  try {
    if (solo.has('niveles')) await niveles();
    if (solo.has('alcance')) await alcance();
    if (solo.has('unidades')) await unidades();
    if (solo.has('guion')) await guion();
    if (solo.has('juego')) await juego();
    if (solo.has('flujo')) await flujo();
    if (solo.has('teclado')) await teclado();
    if (solo.has('presupuesto')) await presupuesto();
    if (solo.has('salida')) await salida();
  } catch (e) { falla(`excepción: ${e.stack || e}`); }
})();
await guardarJSON(op, 'recorrido_qa.json', { fallas, resultado });
await nav.close();
await srv.cerrar();
console.log(fallas.length ? `QA del recorrido: ${fallas.length} fallas` : 'QA del recorrido: bien');
process.exit(fallas.length ? 1 : 0);
