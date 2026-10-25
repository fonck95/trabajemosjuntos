// Herramientas comunes de QA del atlas en Chromium sin pantalla (equipo D; especificación de integración 2.1 y 12.1).
// Las usan scripts/qa/torre_qa.mjs (D), scripts/qa/recorrido_qa.mjs (C) y scripts/sismo/qa_worker.mjs (A).
//
// - servidor estático de web/ (o de site/), en la raíz o bajo una subruta como la de GitHub Pages, con los tipos MIME y el
//   «nosniff» de Caddy; web/index.html se sirve envuelto en <!doctype>/<head>/<body> igual que lo hace build_site.py;
// - desvío de los CDN (cdn.jsdelivr.net, unpkg.com, cdnjs.cloudflare.com, Google Fonts) a copias locales en la carpeta
//   --vendor (three@0.160.0 y gsap@3.12.5 sacados con «npm pack»: ver scripts/qa/LEEME.md); cualquier otro sitio externo
//   se corta, así la prueba no depende de la red;
// - registro de la consola (errores, avisos y excepciones), de las peticiones fallidas y de las respuestas ≥ 400, con una
//   lista de fallas esperadas (por ejemplo, los módulos que un equipo todavía no ha subido);
// - desborde horizontal (scrollWidth > innerWidth) con los elementos que lo causan;
// - capturas de pantalla, ventana de escritorio o de teléfono (390 × 844, táctil) y tema claro u oscuro.
//
// Uso como biblioteca:
//   import { opciones, servidor, abrir, desborde, captura, esperar, informe } from '../qa/comun.mjs';
//   const op = opciones();                                   // --vendor, --raiz, --base, --salida (capturas; por omisión
//                                                            // en la carpeta temporal del sistema, fuera del repositorio), --puerto,
//                                                            // --url (sitio ya servido: Caddy, un despliegue; no levanta servidor)
//   const srv = await servidor(op);                          // { url, cerrar() }
//   const nav = await navegador(op);                         // Chromium (PLAYWRIGHT_MODULE o «playwright»)
//   const { page, registro } = await abrir(nav, op, { url: srv.url + '?qa=1#torre', tema: 'oscuro', telefono: true });
//   … await desborde(page); await captura(page, op, 'torre-oscuro-tel'); informe(registro);
// Uso directo (prueba de humo de varias vistas):
//   node scripts/qa/comun.mjs --vendor <carpeta> [--raiz web|site] [--vistas dinero,torre] [--temas claro,oscuro] [--telefono]
import http from 'node:http';
import { readFile, stat, mkdir, writeFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { extname, join, normalize, resolve, sep, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { tmpdir } from 'node:os';

export const RAIZ_REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const VENTANAS = {
  escritorio: { viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 },
  telefono: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};
// WebGL por software (SwiftShader): sin GPU en el contenedor de QA
export const ARGS_CHROMIUM = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];

// ---------------------------------------------------------------- opciones de la línea de órdenes
export function opciones(argv = process.argv.slice(2), defecto = {}) {
  const op = { raiz: 'web', base: '/', puerto: 0, salida: join(tmpdir(), 'atlas_qa'), vendor: process.env.QA_VENDOR || null, ...defecto, resto: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], sig = () => argv[++i];
    if (a === '--vendor') op.vendor = sig();
    else if (a === '--raiz') op.raiz = sig();
    else if (a === '--base') op.base = sig();
    else if (a === '--puerto') op.puerto = +sig();
    else if (a === '--salida') op.salida = sig();
    else if (a === '--url') op.url = sig();
    else if (a.startsWith('--') && argv[i + 1] && !argv[i + 1].startsWith('--')) op[a.slice(2)] = sig();
    else if (a.startsWith('--')) op[a.slice(2)] = true;
    else op.resto.push(a);
  }
  if (!op.base.startsWith('/')) op.base = `/${op.base}`;
  if (!op.base.endsWith('/')) op.base += '/';
  op.raizAbs = resolve(RAIZ_REPO, op.raiz);
  if (op.vendor) op.vendor = resolve(op.vendor);
  return op;
}

// ---------------------------------------------------------------- servidor estático
const TIPOS = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.bin': 'application/octet-stream', '.wasm': 'application/wasm',
  '.ktx2': 'image/ktx2', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.csv': 'text/csv; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8', '.woff2': 'font/woff2', '.ico': 'image/x-icon',
};
// web/index.html no trae <!doctype>/<head>/<body> (se publica también como Artifact, que los agrega): se envuelve como en
// scripts/build_site.py para que el navegador no la lea en modo «quirks»
export function envolverIndex(cuerpo) {
  if (/^\s*<!doctype/i.test(cuerpo)) return cuerpo;
  const fin = cuerpo.indexOf('</style>') + '</style>'.length;
  return `<!doctype html>\n<html lang="es">\n<head>\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n${cuerpo.slice(0, fin)}\n</head>\n<body>\n${cuerpo.slice(fin)}\n</body>\n</html>\n`;
}
export async function servidor(op = opciones()) {
  // --url: el sitio ya está servido por otro lado (Caddy con el Caddyfile del repositorio, un despliegue): no se levanta nada
  if (typeof op.url === 'string') return { url: op.url.endsWith('/') ? op.url : `${op.url}/`, puerto: +new URL(op.url).port || 80, raiz: null, externo: true, cerrar: async () => {} };
  const raiz = op.raizAbs || resolve(RAIZ_REPO, op.raiz || 'web'), base = op.base || '/';
  const srv = http.createServer(async (req, res) => {
    try {
      const u = new URL(req.url, 'http://local');
      if (!u.pathname.startsWith(base)) { res.writeHead(404); res.end(); return; }
      let rel = decodeURIComponent(u.pathname.slice(base.length));
      if (rel === '' || rel.endsWith('/')) rel += 'index.html';
      const ruta = normalize(join(raiz, rel));
      if (ruta !== raiz && !ruta.startsWith(raiz + sep)) { res.writeHead(403); res.end(); return; }
      const st = await stat(ruta).catch(() => null);
      if (!st || !st.isFile()) { res.writeHead(404, { 'content-type': 'text/plain' }); res.end('no encontrado'); return; }
      let cuerpo = await readFile(ruta);
      if (rel === 'index.html') cuerpo = Buffer.from(envolverIndex(cuerpo.toString('utf8')));
      res.writeHead(200, { 'content-type': TIPOS[extname(ruta).toLowerCase()] || 'application/octet-stream', 'x-content-type-options': 'nosniff', 'cache-control': 'no-store' });
      res.end(req.method === 'HEAD' ? undefined : cuerpo);
    } catch (e) { res.writeHead(500); res.end(String(e)); }
  });
  await new Promise((ok) => srv.listen(op.puerto || 0, '127.0.0.1', ok));
  const puerto = srv.address().port;
  return { url: `http://127.0.0.1:${puerto}${base}`, puerto, raiz, cerrar: () => new Promise((ok) => srv.close(ok)) };
}

// ---------------------------------------------------------------- desvío de los CDN a la carpeta --vendor
function versionLocal(vendor, pkg) {
  try { return JSON.parse(readFileSync(join(vendor, pkg, 'package.json'), 'utf8')).version; } catch { return null; }
}
const avisadas = new Set();
function archivoVendor(vendor, url) {
  const u = new URL(url);
  let m;
  // cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js · unpkg.com/three@0.160.0/…
  if ((u.hostname === 'cdn.jsdelivr.net' && (m = u.pathname.match(/^\/npm\/((?:@[^/]+\/)?[^@/]+)@([^/]+)\/(.*)$/)))
    || (u.hostname === 'unpkg.com' && (m = u.pathname.match(/^\/((?:@[^/]+\/)?[^@/]+)@([^/]+)\/(.*)$/)))) {
    const [, pkg, ver, resto] = m, local = versionLocal(vendor, pkg);
    if (local && local !== ver && !avisadas.has(pkg)) { avisadas.add(pkg); console.warn(`[qa] ${pkg}: la página pide ${ver} y la copia local es ${local}`); }
    return join(vendor, pkg, resto);
  }
  // cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js → <vendor>/gsap/dist/gsap.min.js (o <vendor>/gsap/gsap.min.js)
  if (u.hostname === 'cdnjs.cloudflare.com' && (m = u.pathname.match(/^\/ajax\/libs\/([^/]+)\/([^/]+)\/(.*)$/))) {
    const [, pkg, ver, resto] = m, local = versionLocal(vendor, pkg);
    if (local && local !== ver && !avisadas.has(pkg)) { avisadas.add(pkg); console.warn(`[qa] ${pkg}: la página pide ${ver} y la copia local es ${local}`); }
    return [join(vendor, pkg, 'dist', resto), join(vendor, pkg, resto)].find((r) => existsSync(r)) || join(vendor, pkg, 'dist', resto);
  }
  return null;
}
export async function desviarCDN(contexto, vendor) {
  await contexto.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, async (ruta) => {
    const url = ruta.request().url(), host = new URL(url).hostname;
    if (host === 'fonts.googleapis.com') {
      // tipografías: si la carpeta trae fonts.css (con sus woff2 en fonts/), se usa; si no, hoja vacía (quedan las de respaldo)
      const css = vendor && join(vendor, 'fonts.css');
      return ruta.fulfill({ status: 200, contentType: 'text/css; charset=utf-8', body: css && existsSync(css) ? readFileSync(css) : '/* qa: sin Google Fonts */' });
    }
    if (host === 'fonts.gstatic.com') {
      const f = vendor && join(vendor, 'fonts', new URL(url).pathname.split('/').pop());
      return f && existsSync(f) ? ruta.fulfill({ status: 200, contentType: 'font/woff2', body: readFileSync(f) }) : ruta.fulfill({ status: 204, body: '' });
    }
    const f = vendor && archivoVendor(vendor, url);
    if (f && existsSync(f)) return ruta.fulfill({ status: 200, contentType: TIPOS[extname(f)] || 'application/octet-stream', body: readFileSync(f) });
    if (f) console.warn(`[qa] falta en --vendor: ${f}`);
    else if (!avisadas.has(host)) { avisadas.add(host); console.warn(`[qa] petición externa cortada: ${host}`); }
    return ruta.abort('blockedbyclient');
  });
}

// ---------------------------------------------------------------- navegador y páginas
export async function cargarPlaywright() {
  const ruta = process.env.PLAYWRIGHT_MODULE;
  if (ruta) {
    const idx = [join(ruta, 'index.mjs'), join(ruta, 'index.js')].find((r) => existsSync(r));
    return import(pathToFileURL(idx || ruta).href);
  }
  return import('playwright');
}
export async function navegador(op = {}) {
  const pw = await cargarPlaywright(), chromium = pw.chromium || pw.default?.chromium;
  return chromium.launch({ headless: true, args: ARGS_CHROMIUM, ...(op.lanzar || {}) });
}
// Abre una página con su propio contexto (tema, ventana, desvío de CDN y registro). esperados: lista de expresiones con las
// URL que pueden fallar sin que cuente como error (módulos o datos que otro equipo aún no subió)
export async function abrir(nav, op, { url, tema = 'claro', telefono = false, ventana, esperados = [], movimientoReducido = false, sinWorker = false } = {}) {
  const v = ventana || VENTANAS[telefono ? 'telefono' : 'escritorio'];
  const ctx = await nav.newContext({ ...v, colorScheme: tema === 'oscuro' ? 'dark' : 'light', reducedMotion: movimientoReducido ? 'reduce' : 'no-preference', locale: 'es-CO' });
  if (sinWorker) await ctx.addInitScript(() => { Object.defineProperty(window, 'Worker', { value: undefined, configurable: true }); });
  await desviarCDN(ctx, op.vendor);
  const page = await ctx.newPage();
  const registro = registrar(page, esperados);
  if (url) await page.goto(url, { waitUntil: 'load' });
  return { page, contexto: ctx, registro, cerrar: () => ctx.close() };
}
export function registrar(page, esperados = []) {
  const r = { errores: [], avisos: [], fallidas: [], esperadas: [] };
  const esperado = (u) => !!u && esperados.some((re) => re.test(u));
  page.on('console', (m) => {
    const t = m.type(), loc = m.location()?.url || '', txt = m.text();
    if (t !== 'error' && t !== 'warning') return;
    // «Failed to load resource» trae la URL en location: si es una falla esperada no cuenta como error
    if (/Failed to load resource/.test(txt) && esperado(loc)) { r.esperadas.push(`${txt} · ${loc}`); return; }
    (t === 'error' ? r.errores : r.avisos).push(`${txt}${loc ? ` · ${loc}` : ''}`);
  });
  page.on('pageerror', (e) => r.errores.push(`excepción: ${e.message}`));
  // ERR_ABORTED es una petición cancelada (cambio de vista o cierre de la página con una carga en curso): aviso, no falla
  page.on('requestfailed', (q) => { const u = q.url(), t = q.failure()?.errorText || ''; if (/^https?:\/\/(127\.0\.0\.1|localhost)/.test(u) && !esperado(u)) (/ERR_ABORTED/.test(t) ? r.avisos : r.fallidas).push(`${t} · ${u}`); });
  page.on('response', (s) => { const u = s.url(); if (s.status() >= 400 && /^https?:\/\/(127\.0\.0\.1|localhost)/.test(u)) (esperado(u) ? r.esperadas : r.fallidas).push(`${s.status()} · ${u}`); });
  return r;
}
// Espera una condición evaluada en la página (función sin argumentos o con arg), con tiempo límite
export async function esperar(page, fn, { ms = 20000, arg } = {}) {
  try { await page.waitForFunction(fn, arg, { timeout: ms, polling: 100 }); return true; } catch { return false; }
}
// Cambia de vista como lo haría la persona (pestaña de la cabecera) y espera a que la sección esté a la vista
export async function irAVista(page, vista, { ms = 20000 } = {}) {
  await page.evaluate((v) => { const a = document.querySelector(`nav.tabs a[data-view="${v}"]`); if (a) a.click(); else location.hash = v; }, vista);
  return esperar(page, (v) => { const s = document.getElementById(`v-${v}`); return s && !s.hidden && s.querySelector('canvas.gl'); }, { ms, arg: vista });
}

// ---------------------------------------------------------------- verificaciones
export async function desborde(page) {
  return page.evaluate(() => {
    const ancho = innerWidth, sw = document.documentElement.scrollWidth, culpables = [];
    if (sw > ancho) {
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect();
        if (r.right > ancho + 1 && r.width > 0 && getComputedStyle(el).position !== 'fixed') {
          const nombre = el.tagName.toLowerCase() + (el.id ? `#${el.id}` : '') + (el.className && typeof el.className === 'string' ? `.${el.className.trim().split(/\s+/).join('.')}` : '') + (el.dataset?.slot ? `[${el.dataset.slot}]` : '');
          culpables.push(`${nombre} (${Math.round(r.right)} px)`);
          if (culpables.length >= 8) break;
        }
      }
    }
    return { ok: sw <= ancho, scrollWidth: sw, innerWidth: ancho, culpables };
  });
}
// Texto visible de un elemento (o de la página) que cita rutas o claves internas (13.4 y 13.6)
export const RE_INTERNO = /\.json|→\s*[a-z]+_[a-z_]+|data\//;
export async function textosInternos(page, selector = 'main') {
  return page.evaluate(({ selector, re }) => {
    const rx = new RegExp(re), out = [];
    const raiz = document.querySelector(selector) || document.body;
    const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const el = n.parentElement;
      if (!el || !el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;   // oculto
      if (rx.test(n.textContent)) out.push(n.textContent.trim().slice(0, 160));
    }
    return out;
  }, { selector, re: RE_INTERNO.source });
}
export async function captura(page, op, nombre, opc = {}) {
  await mkdir(op.salida, { recursive: true });
  const ruta = join(op.salida, `${nombre}.png`);
  await page.screenshot({ path: ruta, ...opc });
  return ruta;
}
// Resumen legible del registro; devuelve true si no hubo errores ni fallas inesperadas
export function informe(registro, titulo = '') {
  const ok = !registro.errores.length && !registro.fallidas.length;
  console.log(`${ok ? 'OK ' : 'MAL'} ${titulo} · errores ${registro.errores.length} · fallas ${registro.fallidas.length} · avisos ${registro.avisos.length} · esperadas ${registro.esperadas.length}`);
  for (const e of [...registro.errores, ...registro.fallidas]) console.log(`    ${e}`);
  return ok;
}
export async function guardarJSON(op, nombre, obj) {
  await mkdir(op.salida, { recursive: true });
  const ruta = join(op.salida, nombre);
  await writeFile(ruta, JSON.stringify(obj, null, 1));
  return ruta;
}

// ---------------------------------------------------------------- prueba de humo (uso directo)
if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  const op = opciones();
  if (!op.vendor) { console.error('Falta --vendor <carpeta> con three/ y gsap/ (ver scripts/qa/LEEME.md)'); process.exit(2); }
  const vistas = String(op.vistas || 'dinero,torre').split(','), temas = String(op.temas || 'claro').split(',');
  const srv = await servidor(op), nav = await navegador(op);
  let todo = true;
  for (const tema of temas) for (const tel of op.telefono ? [false, true] : [false]) for (const v of vistas) {
    const { page, registro, cerrar } = await abrir(nav, op, { url: `${srv.url}#${v}`, tema, telefono: tel });
    const visto = await esperar(page, (x) => { const s = document.getElementById(`v-${x}`); return s && !s.hidden && s.querySelector('canvas.gl'); }, { arg: v });
    await page.waitForTimeout(+op.espera || 4000);
    const d = await desborde(page), nombre = `${v}-${tema}${tel ? '-telefono' : ''}`;
    await captura(page, op, nombre);
    todo = informe(registro, `${nombre}${visto ? '' : ' (sin lienzo 3D)'} · desborde ${d.ok ? 'no' : `sí: ${d.culpables.join(', ')}`}`) && d.ok && visto && todo;
    await cerrar();
  }
  await nav.close(); await srv.cerrar();
  console.log(todo ? 'Prueba de humo sin errores.' : 'Prueba de humo con errores.');
  process.exit(todo ? 0 : 1);
}
