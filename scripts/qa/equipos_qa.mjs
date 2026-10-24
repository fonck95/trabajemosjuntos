#!/usr/bin/env node
// QA del catálogo 3D de equipos (web/js/equipos3d.js; equipo C, contrato de integración 5 y 16.5).
//
//   PLAYWRIGHT_MODULE=… node scripts/qa/equipos_qa.mjs --vendor <carpeta> [--salida <carpeta>] [--solo api,grilla,piso,telefono]
//
// Sirve la raíz del repositorio con scripts/qa/comun.mjs (three y GSAP locales con --vendor) y abre en Chromium una página de
// QA que arma este guion (no queda en web/):
//   · api: la lista cerrada contra el catálogo, cada modelo y variante en LOD0 y LOD1 (geometría no nula, no indexada, con
//     position/normal/color, triángulos dentro del 5.1, LOD1 de ≤ 4 cajas), error claro con un modelo desconocido, y la capa
//     de un piso (fixture del Anexo A y datos reales de cada nivel) en baja, media y alta: llamadas y triángulos medidos por
//     el renderizador contra el 5.2, pick, colorear, resaltar, desplazar, fantasma, entrarRecinto y dispose.
//   · grilla: todos los modelos con su nombre, medidas y triángulos (LOD0 grande y LOD1 en el recuadro), en claro y oscuro.
//   · piso: el laboratorio (piso 2), la cubierta y los exteriores con la capa real, para ver ubicación y orientación.
//   · telefono: la grilla en 390 × 844 (sin desborde horizontal).
// Sale con código 1 si algo falla. Las capturas quedan en --salida (por omisión, la carpeta temporal del sistema).
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { opciones, servidor, navegador, abrir, esperar, desborde, captura, informe, guardarJSON, RAIZ_REPO } from './comun.mjs';

const op = opciones(process.argv.slice(2), { raiz: '.' });
const solo = new Set(String(op.solo || 'api,grilla,piso,telefono').split(','));
const POR_PAGINA = 24;

// tokens de color del sitio (claro y oscuro), copiados de web/index.html para que el 3D use los mismos
function tokensCSS() {
  const html = readFileSync(join(RAIZ_REPO, 'web', 'index.html'), 'utf8');
  const a = html.indexOf(':root {'), b = html.indexOf('* { box-sizing');
  return a >= 0 && b > a ? html.slice(a, b) : ':root { --bg: #f2f2ef; --surface: #fff; --ink: #111; --muted: #5a5a56; --line: #dadad4; --accent: #e3141b; --data: #6250d6; }';
}

function paginaQA() {
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>QA de equipos 3D</title>
<style>
${tokensCSS()}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink); font: 13px/1.35 system-ui, sans-serif; }
#lienzo { position: fixed; inset: 0; width: 100vw; height: 100vh; display: block; }
#grilla { position: fixed; inset: 0; display: grid; pointer-events: none; }
.celda { position: relative; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); overflow: hidden; }
.celda b { position: absolute; left: 8px; top: 6px; right: 8px; font-size: 13px; color: var(--ink); overflow-wrap: anywhere; }
.celda small { position: absolute; left: 8px; bottom: 6px; right: 34%; color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }
.celda i { position: absolute; right: 4px; bottom: 4px; width: 30%; height: 30%; border: 1px dashed var(--line); font-style: normal; font-size: 10px; color: var(--muted); text-align: right; padding: 1px 3px; }
#estado { position: fixed; right: 8px; top: 4px; color: var(--muted); font-size: 11px; }
</style>
<script type="importmap">{ "imports": { "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js", "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/" } }</script>
</head><body>
<canvas id="lienzo"></canvas><div id="grilla"></div><div id="estado"></div>
<script type="module">
import * as E from '/web/js/equipos3d.js';
import { THREE, tokens } from '/web/js/core.js';
window.__E = E; window.__THREE = THREE;
const q = new URLSearchParams(location.search), modo = q.get('modo') || 'grilla';
const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('lienzo'), antialias: true });
renderer.setPixelRatio(1);
renderer.setSize(innerWidth, innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.info.autoReset = false;
window.__renderer = renderer;
const T = tokens();
function luces(escena) {
  const oscuro = T.bg.r + T.bg.g + T.bg.b < 0.3;
  escena.add(new THREE.HemisphereLight(0xffffff, oscuro ? 0x404448 : 0xb9b4a8, oscuro ? 1.6 : 1.9));
  const s = new THREE.DirectionalLight(0xffffff, oscuro ? 1.6 : 1.8); s.position.set(-3, 6, -4); escena.add(s);
  const s2 = new THREE.DirectionalLight(0xffffff, 0.5); s2.position.set(4, 2, 3); escena.add(s2);
}
function malla(g) {
  const M = E.materiales(), o = new THREE.Group();
  o.add(new THREE.Mesh(g, M.opaco));
  if (g.userData.vidrio) o.add(new THREE.Mesh(g.userData.vidrio, M.vidrio));
  return o;
}
function encuadre(cam, obj, az = 35, el = 24) {
  const caja = new THREE.Box3().setFromObject(obj), esf = caja.getBoundingSphere(new THREE.Sphere());
  const a = az * Math.PI / 180, e = el * Math.PI / 180;
  const dir = new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), -Math.cos(a) * Math.cos(e));
  const dist = esf.radius / Math.sin((cam.fov * Math.PI / 180) / 2) * 1.02;
  cam.position.copy(esf.center).addScaledVector(dir, dist);
  cam.near = dist / 100; cam.far = dist * 4; cam.lookAt(esf.center); cam.updateProjectionMatrix();
}
const casos = () => {
  const lista = [];
  for (const m of E.MODELOS) {
    lista.push([m, null]);
    for (const v of (window.__VARIANTES || {})[m] || []) lista.push([m, v]);
  }
  return lista;
};
const fmt = (v) => v.toFixed(2).replace('.', ',');

async function grilla() {
  const cols = innerWidth < 600 ? 2 : 6, filas = innerWidth < 600 ? 4 : 4, desde = +(q.get('desde') || 0);
  const todos = casos(), lista = todos.slice(desde, desde + cols * filas);
  const g = document.getElementById('grilla');
  g.style.gridTemplateColumns = 'repeat(' + cols + ', 1fr)'; g.style.gridTemplateRows = 'repeat(' + filas + ', 1fr)';
  const cw = innerWidth / cols, ch = innerHeight / filas, cam = new THREE.PerspectiveCamera(28, 1, 0.01, 100);
  const fondo = T.surface.clone();
  renderer.setScissorTest(true);
  renderer.setClearColor(T.bg); renderer.clear();
  lista.forEach(([m, v], k) => {
    const nom = E.nominal(m), dim = (window.__CATALOGO[m] && (v ? (window.__CATALOGO[m].variantes?.[v]?.dim_m || window.__CATALOGO[m].dim_m) : window.__CATALOGO[m].dim_m)) || nom.dim;
    const g0 = E.geometria(m, dim, 0, { variante: v }), g1 = E.geometria(m, dim, 1, { variante: v });
    const d = document.createElement('div'); d.className = 'celda'; d.dataset.modelo = m;
    d.innerHTML = '<b>' + E.NOMBRES[m] + (v ? ' (' + v + ')' : '') + '</b><small>' + dim.map(fmt).join(' × ') + ' m · ' + g0.userData.triangulos + ' triángulos</small><i>LOD1 · ' + g1.userData.triangulos + '</i>';
    g.appendChild(d);
    const cx = (k % cols) * cw, cy = Math.floor(k / cols) * ch;
    const y = innerHeight - cy - ch;
    for (const [geo, x0, y0, w, h] of [[g0, cx, y + 18, cw, ch - 40], [g1, cx + cw * 0.7, y + 4, cw * 0.3 - 4, ch * 0.3 - 4]]) {
      const esc = new THREE.Scene(); luces(esc); const o = malla(geo); esc.add(o);
      cam.aspect = w / h; encuadre(cam, o);
      renderer.setViewport(x0, y0, w, h); renderer.setScissor(x0, y0, w, h);
      renderer.setClearColor(fondo); renderer.clear(); renderer.render(esc, cam);
    }
  });
  renderer.setScissorTest(false);
  document.getElementById('estado').textContent = (desde + 1) + '–' + (desde + lista.length) + ' de ' + todos.length;
  return { total: todos.length, dibujados: lista.length };
}

// ---- capa de un nivel con los datos reales (o el fixture), dibujada sobre sus muros como contexto
async function cargar(u) { const r = await fetch(u); if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); }
function murosDe(nivel) {
  const g = new THREE.Group(), mat = new THREE.MeshStandardMaterial({ color: T.wall, roughness: 0.9, transparent: true, opacity: 0.55 });
  for (const m of nivel?.muros || []) {
    const [ax, ay] = m.a, [bx, by] = m.b, L = Math.hypot(bx - ax, by - ay), h = Math.min(m.altura || 3, 1.2);
    if (L < 0.01) continue;
    const b = new THREE.Mesh(new THREE.BoxGeometry(L, h, m.espesor || 0.15), mat);
    b.position.set((ax + bx) / 2, h / 2, -(ay + by) / 2); b.rotation.y = Math.atan2(by - ay, bx - ax);
    g.add(b);
  }
  const piso = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshStandardMaterial({ color: T.ground, roughness: 1 }));
  piso.rotation.x = -Math.PI / 2; piso.position.y = -0.01; g.add(piso);
  return g;
}
async function nivel(clave, calidad) {
  const inv = await cargar('/web/data/torre_inventario.json');
  const parte = await cargar('/web/data/torre_inventario_' + clave + '.json');
  const pl = await cargar('/web/data/torre_plantas_' + clave + '.json').catch(() => null);
  const us = E.unidadesDelPiso(inv, clave, parte);
  const capa = E.crearCapaEquipos(us, inv.catalogo, { z: 0 }, { calidad });
  return { inv, us, capa, planta: pl?.niveles?.[0] || null };
}
function medir(escena, cam) {
  renderer.info.reset(); renderer.render(escena, cam);
  return { llamadas: renderer.info.render.calls, triangulos: renderer.info.render.triangles };
}
async function piso() {
  const clave = q.get('nivel') || 'P2', calidad = q.get('calidad') || 'alta';
  const { capa, planta, us } = await nivel(clave, calidad);
  const esc = new THREE.Scene(); esc.background = T.bg; luces(esc);
  esc.add(murosDe(planta)); esc.add(capa.objeto);
  // encuadre: los recintos cuyo servicio o ambiente coinciden con «zona» (y se entra al primero), o todo el nivel
  const zona = q.get('zona'), rx = zona ? new RegExp(zona, 'i') : null;
  const ids = new Set((planta?.recintos || []).filter((r) => rx && rx.test((r.servicio_programa || '') + ' ' + (r.ambiente || ''))).map((r) => r.id));
  const sel = rx ? us.filter((u) => ids.has(u.recinto)) : us, rec = rx ? sel.find((u) => u.recinto)?.recinto : null;
  const caja = new THREE.Box3();
  for (const u of sel) caja.expandByPoint(new THREE.Vector3(u.x, u.z, -u.y));
  const c = caja.getCenter(new THREE.Vector3()), t = caja.getSize(new THREE.Vector3());
  const cam = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 0.05, 500), R = Math.max(t.x, t.z, 4) * (rx ? 0.75 : 0.62);
  cam.position.set(c.x + R * 0.35, c.y + R * 1.05, c.z + R * 0.9); cam.lookAt(c);
  if (q.get('fantasma')) capa.fantasma(true);
  if (rec) capa.entrarRecinto(rec);
  if (q.get('resaltar')) capa.resaltar(sel.slice(0, 2).map((u) => u.id));
  if (q.get('colorear')) capa.colorear(sel.filter((_, i) => i % 7 === 3).map((u) => u.id), '#d03b3b');
  await new Promise((r) => setTimeout(r, 0));
  const m = medir(esc, cam);
  document.getElementById('estado').textContent = clave + ' · ' + calidad + ' · ' + us.length + ' unidades';
  return { ...capa.stats(), medido: m };
}

// ---- pruebas de la API
async function api() {
  const out = { errores: [], avisos: [], modelos: E.MODELOS.size, casos: 0, niveles: {} };
  const err = (t) => out.errores.push(t);
  const cat = window.__CATALOGO;
  for (const k of Object.keys(cat)) if (!E.MODELOS.has(k)) err('modelo del catálogo sin modelo 3D: ' + k);
  for (const k of E.MODELOS) if (!cat[k]) err('modelo 3D sin entrada en el catálogo: ' + k);
  const tri = {};
  for (const [m, v] of casos()) for (const lod of [0, 1]) {
    out.casos++;
    const dim = v ? (cat[m]?.variantes?.[v]?.dim_m || cat[m]?.dim_m) : cat[m]?.dim_m;
    let g;
    try { g = E.geometria(m, dim, lod, { variante: v }); } catch (e) { err(m + ' LOD' + lod + ': ' + e.message); continue; }
    if (!g || !g.isBufferGeometry) { err(m + ' LOD' + lod + ': nula'); continue; }
    if (g.index) err(m + ' LOD' + lod + ': indexada');
    for (const a of ['position', 'normal', 'color']) if (!g.attributes[a]) err(m + ' LOD' + lod + ': sin ' + a);
    const t = g.userData.triangulos, lim = E.limiteTriangulos(m, lod);
    if (t > lim) err(m + (v ? ':' + v : '') + ' LOD' + lod + ': ' + t + ' triángulos (tope ' + lim + ')');
    if (lod === 1 && g.userData.piezas > 4) err(m + (v ? ':' + v : '') + ' LOD1: ' + g.userData.piezas + ' cajas');
    if (!v) tri[m + ' LOD' + lod] = t;
  }
  out.triangulos = tri;
  try { E.geometria('modelo_que_no_existe', [1, 1, 1], 0); err('un modelo desconocido no lanzó error'); }
  catch (e) { out.desconocido = e.message; if (!/modelo_que_no_existe/.test(e.message)) err('el error no nombra el modelo'); }
  try { E.crearCapaEquipos([{ id: 'U-x', modelo3d: 'cosa_rara', x: 0, y: 0, z: 0 }], {}, { z: 0 }); err('la capa aceptó un modelo desconocido'); } catch { /* bien */ }

  // fixture del Anexo A: tres unidades (camilla, carro de paro y desfibrilador sobre el carro)
  const fx = await cargar('/scripts/fixtures/torre/inventario_min.json');
  const cam = new THREE.PerspectiveCamera(60, 1, 0.05, 200);
  // orientación (0, giro antihorario en planta = rotation.y) y espalda a −y: una cama girada 90° queda a lo largo de x y
  // su cabecero (alto) al oriente; vale igual con la fila web, con el objeto normalizado y en instancias o fundida
  for (const calidad of ['baja', 'media']) for (const forma of ['fila', 'normalizada']) {
    const filas = [0, 1, 2, 3].map((k) => ['U-o' + k, 0, 1, 'R', 3 * k, 0, 0, Math.PI / 2, -1, -1, -1, 'piso', 'en_dotacion']);
    const lineas = [{ modelo3d: 'cama_hospitalaria' }];
    const us = forma === 'fila' ? filas : E.unidadesDelPiso({ unidades: filas, lineas, columnas_unidades: fx.columnas_unidades }, 1);
    const capa = E.crearCapaEquipos(us, {}, { z: 0 }, { calidad, lineas });
    const caja = new THREE.Box3().setFromObject(capa.objeto), t = caja.getSize(new THREE.Vector3());
    // cama 1,00 × 2,20: girada 90°, en three ocupa 2,20 en x (las cuatro camas: 9 + 2,20) y 1,00 en z
    if (Math.abs(t.z - 1.0) > 0.05 || Math.abs(t.x - 11.2) > 0.1) err('orientación ' + calidad + ' ' + forma + ': caja ' + t.x.toFixed(2) + ' × ' + t.z.toFixed(2));
    // el cabecero (espalda, −y local) queda en +x del mundo tras girar 90°: lo más alto de la cama está al oriente
    const rc = new THREE.Raycaster(new THREE.Vector3(1.08, 3, 0), new THREE.Vector3(0, -1, 0)), rc2 = new THREE.Raycaster(new THREE.Vector3(-1.08, 3, 0), new THREE.Vector3(0, -1, 0));
    const pE = capa.pick(rc), pO = capa.pick(rc2);
    if (!pE || !pO || !(3 - pE.distancia > 3 - pO.distancia)) err('orientación ' + calidad + ' ' + forma + ': el cabecero no queda al oriente');
    capa.dispose();
  }
  for (const calidad of ['baja', 'media', 'alta']) {
    const capa = E.crearCapaEquipos(fx.unidades, fx.catalogo, { z: 0 }, { calidad, lineas: fx.lineas, columnas: fx.columnas_unidades });
    const ids = capa.unidades().map((u) => u.id);
    const r = {};
    // pick desde arriba: el desfibrilador tapa el carro donde está apoyado
    for (const id of ids) {
      const c = capa.centro(id), rc = new THREE.Raycaster(new THREE.Vector3(c.x, c.y + 5, c.z), new THREE.Vector3(0, -1, 0));
      r[id] = capa.pick(rc)?.unidad || null;
    }
    const pegados = ids.filter((id) => r[id] === id).length;
    if (pegados < ids.length - 1) err('fixture ' + calidad + ': pick acertó ' + pegados + ' de ' + ids.length);
    const s0 = capa.stats();
    capa.resaltar([ids[0]]); const s1 = capa.stats(); if (s1.llamadas !== s0.llamadas + 1) err('resaltar no agrega su llamada (' + calidad + ')');
    capa.resaltar(null); if (capa.stats().llamadas !== s0.llamadas) err('resaltar(null) no quita la caja');
    const c0 = capa.centro(ids[0]).clone(); capa.desplazar(ids[0], 0.5, -0.25); const c1 = capa.centro(ids[0]);
    if (Math.abs(c1.x - c0.x - 0.5) > 1e-6 || Math.abs(c1.z - c0.z - 0.25) > 1e-6) err('desplazar no mueve el centro como se pide');
    await new Promise((x) => setTimeout(x, 0));
    const rc = new THREE.Raycaster(new THREE.Vector3(c1.x, c1.y + 5, c1.z), new THREE.Vector3(0, -1, 0));
    if (capa.pick(rc)?.unidad !== ids[0]) err('pick no encuentra la unidad desplazada (' + calidad + ')');
    capa.desplazar(ids[0], 0, 0);
    capa.colorear([ids[0]], '#00ff00');
    capa.colorear(null, null);
    capa.entrarRecinto(capa.unidades()[0].recinto); const s2 = capa.stats();
    capa.entrarRecinto(null); const s3 = capa.stats();
    if (s3.llamadas !== s0.llamadas) err('entrarRecinto(null) no devuelve las llamadas (' + calidad + ')');
    out['fixture_' + calidad] = { stats: s0, recinto: s2, pick: r };
    const esc = new THREE.Scene(); luces(esc); esc.add(capa.objeto); cam.position.set(0, 6, 6); cam.lookAt(0, 0, 0);
    medir(esc, cam);
    capa.dispose();
    if (capa.objeto.parent) err('dispose no saca el grupo de la escena');
  }

  // datos reales: cada nivel en las tres calidades, contra el 5.2 (la planta usa ≤ 8 llamadas en baja; ≈ 15 en media)
  const tope = { baja: { llamadas: 22, triangulos: 100000 }, media: { llamadas: 30, triangulos: 120000 }, alta: { llamadas: 30, triangulos: 160000 } };
  for (const clave of ['EXT', 'P1', 'P2', 'P3', 'P4', 'BT', 'CUB']) {
    out.niveles[clave] = {};
    for (const calidad of ['baja', 'media', 'alta']) {
      const t0 = performance.now();
      let n;
      try { n = await nivel(clave, calidad); } catch (e) { err(clave + ' ' + calidad + ': ' + e.message); continue; }
      const ms = Math.round(performance.now() - t0);
      const { capa, us } = n;
      // recinto con más unidades: entra (malla del recinto), fantasma y resaltado encendidos = el peor caso de la capa
      const cuenta = {}; for (const u of us) if (u.recinto) cuenta[u.recinto] = (cuenta[u.recinto] || 0) + 1;
      const rec = Object.entries(cuenta).sort((a, b) => b[1] - a[1])[0]?.[0];
      capa.entrarRecinto(rec); capa.fantasma(true); capa.resaltar(us.slice(0, 3).map((u) => u.id));
      capa.colorear(us.slice(0, 40).map((u) => u.id), '#d03b3b');
      const esc = new THREE.Scene(); luces(esc); esc.add(capa.objeto);
      const caja = new THREE.Box3().setFromObject(capa.objeto), c = caja.getCenter(new THREE.Vector3()), t = caja.getSize(new THREE.Vector3());
      const camN = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 1000);
      camN.position.set(c.x, c.y + Math.max(t.x, t.z) * 1.3 + 5, c.z + 0.01); camN.lookAt(c);
      const m = medir(esc, camN), s = capa.stats();
      if (m.llamadas > tope[calidad].llamadas) err(clave + ' ' + calidad + ': ' + m.llamadas + ' llamadas de equipos (tope ' + tope[calidad].llamadas + ')');
      if (m.triangulos > tope[calidad].triangulos) err(clave + ' ' + calidad + ': ' + m.triangulos + ' triángulos de equipos (tope ' + tope[calidad].triangulos + ')');
      if (s.llamadas < m.llamadas) out.avisos.push(clave + ' ' + calidad + ': stats() cuenta ' + s.llamadas + ' llamadas y el renderizador ' + m.llamadas);
      let ok = 0, prob = 0;
      for (const u of capa.unidades().filter((u) => u.dibujada && u.montaje === 'piso' && u.dim[0] > 0.45 && u.dim[1] > 0.45).slice(0, 30)) {
        const cc = capa.centro(u.id), rc = new THREE.Raycaster(new THREE.Vector3(cc.x, cc.y + 6, cc.z), new THREE.Vector3(0, -1, 0));
        prob++; if (capa.pick(rc)) ok++;
      }
      out.niveles[clave][calidad] = { unidades: us.length, ms, stats: s, medido: m, pick: ok + '/' + prob, recinto: rec };
      capa.dispose();
    }
  }
  return out;
}

const listo = (r) => { window.__resultado = r; document.body.dataset.listo = '1'; };
(async () => {
  window.__CATALOGO = (await cargar('/data/proyectos/torre_hospital/catalogo_equipos.json')).modelos;
  window.__VARIANTES = {};
  for (const [m, e] of Object.entries(window.__CATALOGO)) if (e.variantes) window.__VARIANTES[m] = Object.keys(e.variantes);
  try { listo(await ({ grilla, piso, api }[modo])()); } catch (e) { console.error(e); listo({ error: String(e && e.stack || e) }); }
})();
</script></body></html>`;
}

const RUTA = '__qa/equipos.html';
async function pagina(nav, srv, { tema = 'claro', telefono = false, consulta = '' } = {}) {
  const ab = await abrir(nav, op, { tema, telefono });
  await ab.page.route(`**/${RUTA}*`, (r) => r.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: paginaQA() }));
  await ab.page.goto(`${srv.url}${RUTA}?${consulta}`, { waitUntil: 'load' });
  const ok = await esperar(ab.page, () => document.body.dataset.listo === '1', { ms: 240000 });
  const r = ok ? await ab.page.evaluate(() => window.__resultado) : { error: 'tiempo agotado' };
  return { ...ab, r };
}

const srv = await servidor(op);
const nav = await navegador(op);
let bien = true;
const resumen = {};
try {
  if (solo.has('api')) {
    const p = await pagina(nav, srv, { consulta: 'modo=api' });
    const r = p.r;
    bien = informe(p.registro, 'equipos api') && bien;
    if (r.error) { console.log('MAL api:', r.error); bien = false; }
    else {
      console.log(`modelos ${r.modelos} · casos ${r.casos} (modelo × variante × LOD) · errores ${r.errores.length} · avisos ${r.avisos.length}`);
      console.log(`error con modelo desconocido: «${r.desconocido}»`);
      for (const e of r.errores) console.log('   MAL', e);
      for (const e of r.avisos) console.log('   aviso', e);
      for (const c of ['baja', 'media', 'alta']) console.log(`fixture ${c}: ${JSON.stringify(r['fixture_' + c].stats)} · recinto ${JSON.stringify(r['fixture_' + c].recinto)}`);
      for (const [k, v] of Object.entries(r.niveles)) console.log(`${k.padEnd(4)} ${Object.entries(v).map(([c, x]) => `${c}: ${x.unidades} u, ${x.medido.llamadas} ll, ${x.medido.triangulos} tri, ${x.stats.instancias} inst, pick ${x.pick}, ${x.ms} ms`).join(' | ')}`);
      const t = Object.entries(r.triangulos).filter(([k]) => k.endsWith('LOD0')).sort((a, b) => b[1] - a[1]);
      console.log('LOD0 más pesados:', t.slice(0, 6).map(([k, v]) => `${k.replace(' LOD0', '')} ${v}`).join(', '), '· media', Math.round(t.reduce((a, [, v]) => a + v, 0) / t.length));
      if (r.errores.length) bien = false;
      resumen.api = r;
    }
    await p.cerrar();
  }
  for (const tema of ['claro', 'oscuro']) {
    if (solo.has('grilla')) {
      let desde = 0, total = 1, k = 0;
      while (desde < total) {
        const p = await pagina(nav, srv, { tema, consulta: `modo=grilla&desde=${desde}` });
        if (p.r.error) { console.log('MAL grilla:', p.r.error); bien = false; await p.cerrar(); break; }
        total = p.r.total;
        const ruta = await captura(p.page, op, `equipos-grilla-${tema}-${++k}`);
        const ok = informe(p.registro, `grilla ${tema} ${desde + 1}-${desde + p.r.dibujados} → ${ruta}`);
        bien = ok && bien;
        desde += POR_PAGINA;
        await p.cerrar();
      }
    }
    if (solo.has('piso')) {
      for (const [nivel, extra, nombre] of [['P2', 'zona=laboratorio&resaltar=1&colorear=1', 'laboratorio'], ['P2', '', ''], ['P1', 'zona=rayos|reanimaci', 'rayosx'], ['P3', 'zona=parto', 'partos'], ['CUB', '', ''], ['EXT', '', ''], ['BT', '', '']]) {
        const p = await pagina(nav, srv, { tema, consulta: `modo=piso&nivel=${nivel}&calidad=alta&fantasma=1&${extra}` });
        if (p.r.error) { console.log('MAL piso:', p.r.error); bien = false; await p.cerrar(); continue; }
        const ruta = await captura(p.page, op, `equipos-piso-${nivel}${nombre ? '-' + nombre : ''}-${tema}`);
        bien = informe(p.registro, `piso ${nivel} ${tema}: ${p.r.medido.llamadas} llamadas, ${p.r.medido.triangulos} triángulos → ${ruta}`) && bien;
        await p.cerrar();
      }
    }
    if (solo.has('telefono')) {
      const p = await pagina(nav, srv, { tema, telefono: true, consulta: 'modo=grilla&desde=0' });
      const d = await desborde(p.page);
      const ruta = await captura(p.page, op, `equipos-telefono-${tema}`);
      if (!d.ok) { console.log('MAL desborde horizontal en teléfono:', d.scrollWidth, '>', d.innerWidth, d.culpables.join(', ')); bien = false; }
      bien = informe(p.registro, `teléfono ${tema} (scrollWidth ${d.scrollWidth} = innerWidth ${d.innerWidth}) → ${ruta}`) && bien;
      await p.cerrar();
    }
  }
  if (resumen.api) console.log('informe:', await guardarJSON(op, 'equipos_qa.json', resumen.api));
} finally {
  await nav.close();
  await srv.cerrar();
}
console.log(bien ? 'QA de equipos: bien' : 'QA de equipos: con fallas');
process.exit(bien ? 0 : 1);
