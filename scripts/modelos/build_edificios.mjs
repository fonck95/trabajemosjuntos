// Réplicas 3D de las dependencias públicas de Yondó a partir de data/edificios/<id>.json
// (levantamiento con satélite, Street View y fotos; formato en data/edificios/ESPECIFICACION.md).
// Cada GLB tiene dos capas: "existente" (el edificio real) y "adecuaciones" (solar, baterías,
// equipos, cubierta nueva y la conexión eléctrica del proyecto de microrred), para mostrar el antes y el después.
// Salida: web/models/edificios/<id>_lod0.glb (detalle) y <id>_lod1.glb (lejos) + manifest.json
//
// Obra nueva (opcional, no cambia las réplicas): fachadas por lado (muro cortina, panel compuesto, concreto a la vista,
// ladrillo), ventanas corridas, losas expresadas, parasoles instanciados, marquesinas, bahía de ambulancias, puentes,
// equipos de cubierta, paisajismo, letreros institucionales y pérgola solar. Formato en ESPECIFICACION.md («Obra nueva»).
//
// Sin parpadeo (z-fighting): nada queda coplanar con otra superficie visible. Los suelos se escalonan
// (NIVEL), lo que va sobre un muro sobresale ≥ 2,5 cm, los vanos tienen jambas y los muros tapados por
// otro volumen no se dibujan. Se verifica con check_coplanar.mjs.
//
// Uso: cd scripts/modelos && node build_edificios.mjs [id ...] [--sin-comprimir]
import { THREE, Part, Builder, baseMaterials, pvMesh, bessPart, warnSign, writeGLB, instanced, TEX, MOD } from './lib.mjs';
import { FontLoader } from 'three/examples/jsm/loaders/FontLoader.js';
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const dirURL = (env, rel) => (process.env[env] ? pathToFileURL(process.env[env].replace(/\/?$/, '/')) : new URL(rel, import.meta.url));
const DATA = dirURL('EDIFICIOS_DIR', '../../data/edificios/');
const OUT = dirURL('EDIFICIOS_OUT', '../../web/models/edificios/');
const CALLES_URL = new URL('../../data/geo/calles.json', import.meta.url);
const CALLES = existsSync(CALLES_URL) ? JSON.parse(readFileSync(CALLES_URL)) : null;
const font = new FontLoader().parse(JSON.parse(readFileSync(new URL('./node_modules/three/examples/fonts/helvetiker_bold.typeface.json', import.meta.url))));
const D2R = Math.PI / 180;
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const UP = V3(0, 1, 0);
const CARD = { N: [0, 1], S: [0, -1], E: [1, 0], O: [-1, 0], W: [-1, 0] };
const warn = [];

// Alturas (m) de las superficies del suelo: escalonadas 2,5 cm para que ninguna quede coplanar con otra ni con el
// terreno y las calles que dibuja la web (y ≈ 0–0,05). El predio es la capa más baja; la pintura va a media altura.
const NIVEL = { predio: 0.03, zona_verde: 0.055, parqueadero: 0.08, patio: 0.105, plaza: 0.13, anden: 0.155, cancha: 0.18 };
const ORDEN = Object.keys(NIVEL);
const PINTURA = 0.0125, PISO = 0.21; // pintura sobre su superficie; piso de corredores, pórticos y kioscos
const REV = 0.12; // profundidad de las jambas de puertas y ventanas (LOD0)
const COLOR = { potencia: '#f08a00', datos: '#6250d6' };

// ---------- marco local de un rectángulo: x a lo largo del eje largo, z perpendicular; plano: x = este, y = norte → three: X = este, Z = −norte
function frame(o) {
  const th = (o.rumbo_eje ?? 0) * D2R;
  const [cx, cy] = o.centro;
  const m = new THREE.Matrix4().compose(V3(cx, o.base ?? 0, -cy), new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2 - th), V3(1, 1, 1));
  const L = o.largo, A = o.ancho;
  // normal exterior de cada lado en planta (este, norte), vector tangente (de izquierda a derecha visto desde afuera), largo y distancia al centro
  const sides = {
    '+Z': { plan: [Math.cos(th), -Math.sin(th)], n: V3(0, 0, 1), t: V3(1, 0, 0), len: L, half: A / 2 },
    '-Z': { plan: [-Math.cos(th), Math.sin(th)], n: V3(0, 0, -1), t: V3(-1, 0, 0), len: L, half: A / 2 },
    '+X': { plan: [Math.sin(th), Math.cos(th)], n: V3(1, 0, 0), t: V3(0, 0, -1), len: A, half: L / 2 },
    '-X': { plan: [-Math.sin(th), -Math.cos(th)], n: V3(-1, 0, 0), t: V3(0, 0, 1), len: A, half: L / 2 },
  };
  return { m, inv: m.clone().invert(), L, A, th, sides };
}
function sideFor(f, card) {
  if (f.sides[card]) return card;
  const c = CARD[String(card || 'S').toUpperCase()[0]] || CARD.S;
  let best = '+Z', bd = -2;
  for (const [k, s] of Object.entries(f.sides)) { const d = s.plan[0] * c[0] + s.plan[1] * c[1]; if (d > bd) { bd = d; best = k; } }
  return best;
}
const sidesOf = (f, lados) => {
  const out = new Set();
  for (const l of lados || ['largo', 'corto']) {
    if (l === 'largo') { out.add('+Z'); out.add('-Z'); } else if (l === 'corto') { out.add('+X'); out.add('-X'); } else if (l === 'todos') Object.keys(f.sides).forEach((k) => out.add(k)); else out.add(sideFor(f, l));
  }
  return [...out];
};
// matriz que lleva coordenadas "de fachada" (x a lo largo, y arriba, z hacia afuera) a coordenadas del edificio
function sideMatrix(f, s, along, y, out = 0) {
  const S = f.sides[s];
  const p = S.n.clone().multiplyScalar(S.half + out).add(S.t.clone().multiplyScalar(along)); p.y = y;
  return f.m.clone().multiply(new THREE.Matrix4().makeBasis(S.t, UP, S.n).setPosition(p));
}
const boxG = (w, h, d, x = 0, y = 0, z = 0) => new THREE.BoxGeometry(w, h, d).translate(x, y + h / 2, z);
// caja adosada a un muro (z = 0): sin la cara trasera, que nunca se ve y quedaría coplanar con otras
const boxW = (w, h, d, x = 0, y = 0, z = 0) => { const g = boxG(w, h, d, x, y, z); g.setIndex(Array.from(g.index.array).slice(0, 30)); return g; };
// caja con UV en metros (la textura repite cada `rep` m)
function boxUV(w, h, d, x = 0, y = 0, z = 0, rep = 2) {
  const g = boxG(w, h, d, x, y, z), uv = g.attributes.uv, dims = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  for (let f = 0; f < 6; f++) for (let k = 0; k < 4; k++) { const i = f * 4 + k; uv.setXY(i, (uv.getX(i) * dims[f][0]) / rep, (uv.getY(i) * dims[f][1]) / rep); }
  return g;
}
// UV en metros → baldosa de textura de tile[0] × tile[1] m (paneles, tablas de formaleta, ladrillo); sin tile no cambia nada
function uvs(g, tile) {
  if (!tile || !g?.attributes.uv) return g;
  const uv = g.attributes.uv;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) / tile[0], uv.getY(i) / tile[1]);
  return g;
}
// caja orientada entre dos puntos (vigas, rieles, correas); "up" fija el giro de la sección w × h
function beamG(a, b, w, h, up = UP) {
  const d = b.clone().sub(a), len = d.length(); if (len < 1e-4) return null;
  const x = d.multiplyScalar(1 / len);
  let ref = up.clone(); if (Math.abs(ref.clone().normalize().dot(x)) > 0.98) ref = Math.abs(x.y) < 0.9 ? UP.clone() : V3(1, 0, 0);
  const y = ref.addScaledVector(x, -ref.dot(x)).normalize(), z = x.clone().cross(y);
  return new THREE.BoxGeometry(len, h, w).applyMatrix4(new THREE.Matrix4().makeBasis(x, y, z).setPosition(a.clone().add(b).multiplyScalar(0.5)));
}
function tubeG(a, b, r, seg = 8) {
  const d = b.clone().sub(a), len = d.length(); if (len < 1e-4) return null;
  const g = new THREE.CylinderGeometry(r, r, len, seg);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(UP, d.normalize())).translate((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2);
  return g;
}
// quita puntos repetidos y colineales de una polilínea
function simplify(pts) {
  const q = [];
  for (const p of pts) if (!q.length || q[q.length - 1].distanceTo(p) > 0.01) q.push(p.clone());
  for (let i = q.length - 2; i > 0; i--) { const a = q[i].clone().sub(q[i - 1]).normalize(), b = q[i + 1].clone().sub(q[i]).normalize(); if (a.dot(b) > 0.9995) q.splice(i, 1); }
  return q;
}
// tubo por una polilínea (ductos, bajantes, cables) con codos esféricos
function pipe(part, mat, pts, r, joints = true, seg = 8) {
  const q = simplify(pts);
  for (let i = 1; i < q.length; i++) { const g = tubeG(q[i - 1], q[i], r, seg); if (g) part.addRaw(mat, g); }
  if (joints) for (let i = 1; i < q.length - 1; i++) part.addRaw(mat, new THREE.SphereGeometry(r * 1.04, seg, Math.max(4, seg / 2 + 1)).translate(q[i].x, q[i].y, q[i].z));
  return q;
}

// ---------- polígono plano con normal orientada hacia "hint" y UV en metros (proyección en u, v)
function polyGeo(pts, hint, uDir, vDir) {
  let p = pts.map((q) => q.clone());
  const n = new THREE.Vector3().subVectors(p[1], p[0]).cross(new THREE.Vector3().subVectors(p[2], p[0])).normalize();
  if (hint && n.dot(hint) < 0) { p = p.reverse(); n.negate(); }
  const pos = [], nor = [], uv = [], idx = [];
  const u = uDir || new THREE.Vector3().subVectors(p[1], p[0]).normalize();
  const v = vDir || new THREE.Vector3().crossVectors(n, u).normalize();
  p.forEach((q) => { pos.push(q.x, q.y, q.z); nor.push(n.x, n.y, n.z); uv.push(q.dot(u), q.dot(v)); });
  for (let i = 1; i < p.length - 1; i++) idx.push(0, i, i + 1);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  return g;
}
// tira de cuadriláteros (bóveda) a partir de dos polilíneas
function stripGeo(a, b, outHint) {
  const g = new THREE.BufferGeometry(), pos = [], uv = [], idx = [];
  let acc = 0;
  for (let i = 0; i < a.length; i++) {
    if (i) acc += a[i].distanceTo(a[i - 1]);
    pos.push(a[i].x, a[i].y, a[i].z, b[i].x, b[i].y, b[i].z);
    uv.push(a[i].x, acc, b[i].x, acc);
    if (i) { const k = i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); }
  }
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  const n0 = new THREE.Vector3().fromBufferAttribute(g.attributes.normal, 0);
  if (outHint && n0.dot(outHint(a[0])) < 0) { for (let i = 0; i < idx.length; i += 3) [idx[i + 1], idx[i + 2]] = [idx[i + 2], idx[i + 1]]; g.setIndex(idx); g.computeVertexNormals(); }
  return g;
}

// ---------- texto en relieve con tildes compuestas (la fuente no trae Á, Í, Ñ…). Con `real`, las tildes van sobre la altura
// real de las mayúsculas de la fuente (CAP × size, medida en la "E"); todos los letreros la usan. Sin `real` se usa la altura
// supuesta de 0,72 × size, con la que la tilde aguda quedaba dentro de la letra
const CAP = (() => { const g = new THREE.ShapeGeometry(font.generateShapes('E', 1)); g.computeBoundingBox(); return g.boundingBox.max.y; })();
function textGeo(text, size, depth = 0.04, real = false) {
  const data = font.data, sc = size / data.resolution, cap = (real ? CAP : 0.72) * size, kt = real ? 0.75 : 0.9;
  const geos = []; let x = 0;
  const ext = (shapes, dx, dy = 0) => { const g = new THREE.ExtrudeGeometry(shapes, { depth, bevelEnabled: false, curveSegments: 3 }); g.translate(dx, dy, 0); geos.push(g); };
  for (const ch of String(text).toUpperCase()) {
    const [b, ...marks] = ch.normalize('NFD');
    const g = data.glyphs[b] || data.glyphs['?'];
    const adv = (g?.ha ?? data.resolution * 0.5) * sc;
    if (b !== ' ' && g) ext(font.generateShapes(b, size), x);
    const cx = x + adv / 2;
    for (const m of marks) {
      if (m === '́') ext([new THREE.Shape([new THREE.Vector2(cx - 0.06 * size, cap + 0.07 * size), new THREE.Vector2(cx + 0.06 * size, cap + 0.07 * size), new THREE.Vector2(cx + 0.16 * size, cap + 0.24 * size), new THREE.Vector2(cx + 0.02 * size, cap + 0.24 * size)])], 0);
      else if (m === '̃' && data.glyphs['~']) ext(font.generateShapes('~', size * kt), cx - (data.glyphs['~'].ha * sc * kt) / 2, real ? cap + 0.07 * size - 0.49 * size : cap - 0.18 * size);
      else if (m === '̈') for (const d of [-0.14, 0.06]) ext([new THREE.Shape([new THREE.Vector2(cx + d * size, cap + 0.08 * size), new THREE.Vector2(cx + (d + 0.09) * size, cap + 0.08 * size), new THREE.Vector2(cx + (d + 0.09) * size, cap + 0.17 * size), new THREE.Vector2(cx + d * size, cap + 0.17 * size)])], 0);
    }
    x += adv;
  }
  if (!geos.length) return null;
  const merged = geos.length === 1 ? geos[0] : (() => { const gs = geos.map((g) => { g.deleteAttribute('uv'); return g.index ? g.toNonIndexed() : g; }); return mergeAll(gs); })();
  merged.translate(-x / 2, 0, 0);
  return merged;
}
function mergeAll(gs) {
  const pos = [], nor = [];
  for (const g of gs) { const p = g.attributes.position.array, n = g.attributes.normal.array; for (let i = 0; i < p.length; i++) { pos.push(p[i]); nor.push(n[i]); } }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  return g;
}

// ---------- materiales. Los colores de la especificación van por vértice ("material#rrggbb"): todas las
// fachadas pintadas, zócalos, bandas y cercas comparten "pintura", y cada tipo de cubierta un solo material.
const ROOF_TEX = { zinc: TEX.zinc, fibrocemento: TEX.fibrocemento, termoacustica: TEX.termoacustica, teja_barro: TEX.teja, concreto: TEX.concreto, policarbonato: null };
const ROOF_DEF = { zinc: '#9aa1a6', fibrocemento: '#9b9d98', termoacustica: '#e9e7e1', teja_barro: '#a5512f', concreto: '#b9b6ad', policarbonato: '#d6e2e8' };
const hexOK = (c, d) => (typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c) ? c.toLowerCase() : d);
const tint = (k, c, d = '#888888') => `${k}${hexOK(c, d)}`;
const shade = (c, f) => '#' + new THREE.Color(c).multiplyScalar(f).getHexString();
function roofMat(b, t) {
  const material = ROOF_TEX[t?.material] !== undefined ? t.material : 'zinc';
  const key = `techo_${material}`;
  b.mat(key, { color: '#ffffff', rough: material === 'zinc' ? 0.5 : material === 'policarbonato' ? 0.2 : 0.85, metal: material === 'zinc' ? 0.55 : material === 'termoacustica' ? 0.2 : 0, tex: ROOF_TEX[material] || undefined, doubleSided: true, opacity: material === 'policarbonato' ? 0.75 : 1 });
  return tint(key, t?.color, ROOF_DEF[material]);
}
function wallMat(fa) {
  const material = fa?.material || 'pañete_pintado';
  const key = { ladrillo_visto: 'muro_ladrillo', bloque: 'muro_bloque', metal: 'muro_metal', vidrio: 'muro_vidrio' }[material] || 'pintura';
  return tint(key, fa?.color, material === 'ladrillo_visto' ? '#b4583c' : '#efece4');
}
const wallColor = (fa) => hexOK(fa?.color, fa?.material === 'ladrillo_visto' ? '#b4583c' : '#efece4');
function extraMaterials(b) {
  b.mat('pintura', { color: '#ffffff', rough: 0.88 });
  b.mat('pintura_satin', { color: '#ffffff', rough: 0.5, metal: 0.1 });
  b.mat('metal_pintado', { color: '#ffffff', rough: 0.45, metal: 0.5 });
  b.mat('muro_ladrillo', { color: '#ffffff', rough: 0.9, tex: TEX.ladrillo });
  b.mat('muro_bloque', { color: '#ffffff', rough: 0.9, tex: TEX.bloque });
  b.mat('muro_metal', { color: '#ffffff', rough: 0.45, metal: 0.5, tex: TEX.zinc });
  b.mat('muro_vidrio', { color: '#ffffff', rough: 0.1, metal: 0.3 });
  b.mat('persiana', { color: '#8d979d', rough: 0.45, metal: 0.6, tex: TEX.persiana });
  b.mat('celosia', { color: '#ffffff', rough: 0.9, tex: TEX.celosia });
  b.mat('reja_vidrio', { color: '#ffffff', rough: 0.3, metal: 0.3, tex: TEX.reja });
  b.mat('tronco', { color: '#6b5544', rough: 0.95 });
  b.mat('copa', { color: '#ffffff', rough: 0.95 });
  b.mat('pasto', { color: '#6f9450', rough: 1, tex: TEX.pasto });
  b.mat('asfalto', { color: '#5f6366', rough: 0.95, tex: TEX.asfalto });
  // suelos del predio en tonos medios (no blancos): se leen bien en tema claro y oscuro
  b.mat('predio', { color: '#c9ccc2', rough: 1 });
  b.mat('piso', { color: '#d3d2c9', rough: 0.95, tex: TEX.losa });
  b.mat('bandera_am', { color: '#fcd116', rough: 0.8, doubleSided: true });
  b.mat('bandera_az', { color: '#003893', rough: 0.8, doubleSided: true });
  b.mat('bandera_ro', { color: '#ce1126', rough: 0.8, doubleSided: true });
  b.mat('verde_ve', { color: '#18a957', rough: 0.4, emissive: '#0a4d27' });
  b.mat('malla', { color: '#ffffff', rough: 0.5, metal: 0.5, tex: TEX.malla, alpha: 'mask', doubleSided: true });
  b.mat('pantalla', { color: '#0e1a20', rough: 0.15, metal: 0.2, emissive: '#0b3a46' });
  // conexión del proyecto: potencia en ámbar y datos en violeta, algo emisivos para que se lean en la sombra
  b.mat('potencia', { color: COLOR.potencia, rough: 0.45, emissive: shade(COLOR.potencia, 0.42) });
  b.mat('datos', { color: COLOR.datos, rough: 0.45, emissive: shade(COLOR.datos, 0.45) });
}

// ---------- cubiertas (coordenadas locales del volumen). R = { roof, walls, wk, rk, rot, caps, trim, closed, eaves, soffit }
// caps: caballetes; trim: cielo raso del alero, tapas y canales (solo una vez: no se repiten en la cubierta nueva).
// Devuelven las caras útiles para los paneles.
const rotG = (R, g) => (R.rot ? g.applyMatrix4(R.rot) : g);
const rotV = (R, v, dir = false) => (R.rot ? (dir ? v.clone().transformDirection(R.rot) : v.clone().applyMatrix4(R.rot)) : v.clone());
function eave(R, a, b, out, wd, w0, w1, pipes) { if (R.trim) R.eaves.push({ a: rotV(R, a), b: rotV(R, b), out: rotV(R, out, true), wd, w0: rotV(R, w0), w1: rotV(R, w1), pipes }); }
// caballete en "V" invertida sobre una cumbrera a lo largo de x (centro en x0), con faldas hasta la cubierta
function ridgeCap(R, len, yR, p, x0 = 0) {
  const half = 0.16, lift = 0.03, yA = yR + lift / Math.cos(p), ez = half * Math.cos(p) + lift * Math.sin(p), ey = yR - half * Math.sin(p) + lift * Math.cos(p), yr = yR - ez * Math.tan(p) - 0.01;
  const a = x0 - len / 2, b = x0 + len / 2;
  for (const sg of [1, -1]) {
    R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(a, yA, 0), V3(b, yA, 0), V3(b, ey, sg * ez), V3(a, ey, sg * ez)], V3(0, Math.cos(p), sg * Math.sin(p)))));
    R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(a, ey, sg * ez), V3(b, ey, sg * ez), V3(b, yr, sg * ez), V3(a, yr, sg * ez)], V3(0, 0, sg))));
  }
  for (const [x, sx] of [[a, -1], [b, 1]]) R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(x, yA, 0), V3(x, ey, ez), V3(x, yr, ez), V3(x, yr, -ez), V3(x, ey, -ez)], V3(sx, 0, 0))));
}
// Dos aguas con cumbrera a lo largo de x (largo W) y luz D; si la cumbrera va por el lado corto se gira 90°.
function gable(W, D, eaveY, t, R) {
  const p = (t.pendiente ?? 15) * D2R, v = t.voladizo ?? 0.6, vx = Math.min(v, 0.5), s = D / 2, ro = s + v;
  const yR = eaveY + s * Math.tan(p), yE = eaveY - v * Math.tan(p), X = W / 2 + vx;
  const faces = [];
  for (const sg of [1, -1]) {
    const pts = [V3(-X, yR, 0), V3(X, yR, 0), V3(X, yE, sg * ro), V3(-X, yE, sg * ro)];
    const vd = V3(0, -Math.sin(p), sg * Math.cos(p));
    R.roof.addRaw(R.rk, rotG(R, polyGeo(pts, V3(0, Math.cos(p), sg * Math.sin(p)), V3(1, 0, 0), vd)), true);
    // cara útil (sobre el muro, sin alero) para el arreglo solar
    faces.push(face([V3(-W / 2, yR, 0), V3(W / 2, yR, 0), V3(W / 2, eaveY, sg * s), V3(-W / 2, eaveY, sg * s)], V3(0, Math.cos(p), sg * Math.sin(p)), V3(1, 0, 0), vd, R.rot));
    // tapa del alero (fascia)
    R.roof.addRaw(R.rk, rotG(R, boxG(2 * X, 0.18, 0.03, 0, yE - 0.18, sg * (ro + 0.06))), true);
    eave(R, V3(-X, yE, sg * ro), V3(X, yE, sg * ro), V3(0, 0, sg), v, V3(-W / 2, 0, sg * s), V3(W / 2, 0, sg * s), true);
    if (R.trim && R.closed && v > 0.08) {
      // cielo raso del alero y tapas en el plano de los hastiales
      R.walls.addRaw(R.soffit, rotG(R, polyGeo([V3(-W / 2, yE - 0.15, sg * s), V3(W / 2, yE - 0.15, sg * s), V3(W / 2, yE - 0.15, sg * (ro + 0.045)), V3(-W / 2, yE - 0.15, sg * (ro + 0.045))], V3(0, -1, 0))));
      for (const sx of [1, -1]) R.walls.addRaw(R.wk, rotG(R, polyGeo([V3(sx * W / 2, yE - 0.15, sg * s), V3(sx * W / 2, yE - 0.15, sg * (ro + 0.045)), V3(sx * W / 2, yE, sg * (ro + 0.045)), V3(sx * W / 2, eaveY, sg * s)], V3(sx, 0, 0))), true);
    }
  }
  if (R.caps) ridgeCap(R, 2 * X, yR, p);
  for (const sx of [1, -1]) {
    if (R.closed) R.walls.addRaw(R.wk, rotG(R, polyGeo([V3(sx * W / 2, eaveY, -s), V3(sx * W / 2, eaveY, s), V3(sx * W / 2, yR, 0)], V3(sx, 0, 0))), true);
    // tablas de borde inclinadas en los hastiales
    if (vx > 0.05) for (const sg of [1, -1]) { const up = V3(0, Math.cos(p), sg * Math.sin(p)); R.roof.addRaw(R.rk, rotG(R, beamG(V3(sx * (X - 0.035), yR - 0.07, 0).addScaledVector(V3(0, -Math.sin(p), sg * Math.cos(p)), -0.02), V3(sx * (X - 0.035), yE - 0.07, sg * ro).addScaledVector(V3(0, -Math.sin(p), sg * Math.cos(p)), 0.02), 0.04, 0.18, up)), true); }
  }
  return faces;
}
function hip(W, D, eaveY, t, R) {
  const p = (t.pendiente ?? 15) * D2R, v = t.voladizo ?? 0.6;
  const Wp = W + 2 * v, Dp = D + 2 * v, yE = eaveY - v * Math.tan(p);
  if (Wp < Dp) { const r90 = new THREE.Matrix4().makeRotationY(Math.PI / 2); return hip(D, W, eaveY, t, { ...R, rot: R.rot ? R.rot.clone().multiply(r90) : r90 }); }
  const faces = [], r = (Wp - Dp) / 2, yR = yE + (Dp / 2) * Math.tan(p);
  for (const sg of [1, -1]) {
    const n = V3(0, Math.cos(p), sg * Math.sin(p)), vd = V3(0, -Math.sin(p), sg * Math.cos(p));
    R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(-Wp / 2, yE, sg * Dp / 2), V3(Wp / 2, yE, sg * Dp / 2), V3(r, yR, 0), V3(-r, yR, 0)], n, V3(1, 0, 0), vd)), true);
    const rr = Math.max(0, (W - D) / 2), yr = eaveY + (D / 2) * Math.tan(p);
    faces.push(face([V3(-W / 2, eaveY, sg * D / 2), V3(W / 2, eaveY, sg * D / 2), V3(rr, yr, 0), V3(-rr, yr, 0)], n, V3(1, 0, 0), vd, R.rot));
    const nx = V3(sg * Math.sin(p), Math.cos(p), 0), vdx = V3(sg * Math.cos(p), -Math.sin(p), 0);
    R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(sg * Wp / 2, yE, -Dp / 2), V3(sg * Wp / 2, yE, Dp / 2), V3(sg * r, yR, 0)], nx, V3(0, 0, 1), vdx)), true);
    faces.push(face([V3(sg * W / 2, eaveY, -D / 2), V3(sg * W / 2, eaveY, D / 2), V3(sg * rr, yr, 0)], nx, V3(0, 0, 1), vdx, R.rot));
    eave(R, V3(-Wp / 2, yE, sg * Dp / 2), V3(Wp / 2, yE, sg * Dp / 2), V3(0, 0, sg), v, V3(-W / 2, 0, sg * D / 2), V3(W / 2, 0, sg * D / 2), true);
    eave(R, V3(sg * Wp / 2, yE, -Dp / 2), V3(sg * Wp / 2, yE, Dp / 2), V3(sg, 0, 0), v, V3(sg * W / 2, 0, -D / 2), V3(sg * W / 2, 0, D / 2), false);
  }
  for (const [w, d, x, z] of [[Wp + 0.15, 0.03, 0, Dp / 2 + 0.06], [Wp + 0.15, 0.03, 0, -Dp / 2 - 0.06], [0.03, Dp + 0.15, Wp / 2 + 0.06, 0], [0.03, Dp + 0.15, -Wp / 2 - 0.06, 0]]) R.roof.addRaw(R.rk, rotG(R, boxG(w, 0.18, d, x, yE - 0.18, z)), true);
  if (R.caps) {
    ridgeCap(R, Math.max(0.3, 2 * r), yR, p);
    for (const sx of [1, -1]) for (const sz of [1, -1]) {
      const up = V3(0, Math.cos(p), sz * Math.sin(p)).add(V3(sx * Math.sin(p), Math.cos(p), 0)).normalize();
      const a = V3(sx * Wp / 2, yE, sz * Dp / 2).addScaledVector(up, 0.045), c = V3(sx * r, yR, 0).addScaledVector(up, 0.045);
      R.roof.addRaw(R.rk, rotG(R, beamG(a, c, 0.2, 0.05, up)));
    }
  }
  if (R.trim && R.closed && v > 0.08) {
    const y = yE - 0.15, i = -0.045;
    for (const sg of [1, -1]) {
      R.walls.addRaw(R.soffit, rotG(R, polyGeo([V3(-Wp / 2 + i, y, sg * (Dp / 2 - i)), V3(Wp / 2 - i, y, sg * (Dp / 2 - i)), V3(W / 2, y, sg * D / 2), V3(-W / 2, y, sg * D / 2)], V3(0, -1, 0))));
      R.walls.addRaw(R.soffit, rotG(R, polyGeo([V3(sg * (Wp / 2 - i), y, -Dp / 2 + i), V3(sg * (Wp / 2 - i), y, Dp / 2 - i), V3(sg * W / 2, y, D / 2), V3(sg * W / 2, y, -D / 2)], V3(0, -1, 0))));
    }
  }
  return faces;
}
// Una agua: cae hacia +z en el marco (W a lo largo, D en la dirección de la pendiente)
function shed(W, D, eaveY, t, R) {
  const p = (t.pendiente ?? 10) * D2R, v = t.voladizo ?? 0.6, rise = D * Math.tan(p);
  const yHi = eaveY + rise + v * Math.tan(p), yLo = eaveY - v * Math.tan(p), X = W / 2 + v;
  const n = V3(0, Math.cos(p), Math.sin(p)), vd = V3(0, -Math.sin(p), Math.cos(p));
  R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(-X, yHi, -D / 2 - v), V3(X, yHi, -D / 2 - v), V3(X, yLo, D / 2 + v), V3(-X, yLo, D / 2 + v)], n, V3(1, 0, 0), vd)), true);
  for (const z of [D / 2 + v, -D / 2 - v]) R.roof.addRaw(R.rk, rotG(R, boxG(2 * X, 0.18, 0.03, 0, (z > 0 ? yLo : yHi) - 0.18, z + Math.sign(z) * 0.06)), true);
  if (R.closed) {
    for (const sx of [1, -1]) R.walls.addRaw(R.wk, rotG(R, polyGeo([V3(sx * W / 2, eaveY, -D / 2), V3(sx * W / 2, eaveY, D / 2), V3(sx * W / 2, eaveY + rise, -D / 2)], V3(sx, 0, 0))), true);
    R.walls.addRaw(R.wk, rotG(R, polyGeo([V3(-W / 2, eaveY, -D / 2), V3(W / 2, eaveY, -D / 2), V3(W / 2, eaveY + rise, -D / 2), V3(-W / 2, eaveY + rise, -D / 2)], V3(0, 0, -1))), true);
  }
  eave(R, V3(-X, yLo, D / 2 + v), V3(X, yLo, D / 2 + v), V3(0, 0, 1), v, V3(-W / 2, 0, D / 2), V3(W / 2, 0, D / 2), true);
  if (R.trim && R.closed && v > 0.08) {
    R.walls.addRaw(R.soffit, rotG(R, polyGeo([V3(-W / 2, yLo - 0.15, D / 2), V3(W / 2, yLo - 0.15, D / 2), V3(W / 2, yLo - 0.15, D / 2 + v + 0.045), V3(-W / 2, yLo - 0.15, D / 2 + v + 0.045)], V3(0, -1, 0))));
    for (const sx of [1, -1]) R.walls.addRaw(R.wk, rotG(R, polyGeo([V3(sx * W / 2, yLo - 0.15, D / 2), V3(sx * W / 2, yLo - 0.15, D / 2 + v + 0.045), V3(sx * W / 2, yLo, D / 2 + v + 0.045), V3(sx * W / 2, eaveY, D / 2)], V3(sx, 0, 0))), true);
  }
  return [face([V3(-W / 2, eaveY + rise, -D / 2), V3(W / 2, eaveY + rise, -D / 2), V3(W / 2, eaveY, D / 2), V3(-W / 2, eaveY, D / 2)], n, V3(1, 0, 0), vd, R.rot)];
}
// Bóveda (cubierta curva) de luz D a lo largo de x
function vault(W, D, eaveY, t, R) {
  const f = Math.max(0.3, t.flecha ?? D * 0.12), v = t.voladizo ?? 0.4, X = W / 2 + v;
  const Rr = ((D / 2) ** 2 + f ** 2) / (2 * f), yc = eaveY + f - Rr, N = 18;
  const arc = (z) => yc + Math.sqrt(Math.max(0, Rr * Rr - z * z));
  const a = [], bb = [];
  for (let i = 0; i <= N; i++) { const z = -D / 2 - 0.25 + ((D + 0.5) * i) / N; a.push(V3(-X, arc(z), z)); bb.push(V3(X, arc(z), z)); }
  R.roof.addRaw(R.rk, rotG(R, stripGeo(a, bb, (q) => V3(0, q.y - yc, q.z))), true);
  if (R.closed) for (const sx of [1, -1]) {
    const pts = [V3(sx * W / 2, eaveY, -D / 2)];
    for (let i = 0; i <= N; i++) { const z = -D / 2 + (D * i) / N; pts.push(V3(sx * W / 2, arc(z), z)); }
    pts.push(V3(sx * W / 2, eaveY, D / 2));
    R.walls.addRaw(R.wk, rotG(R, polyGeo(pts, V3(sx, 0, 0))), true);
  }
  for (const sg of [1, -1]) { const z = sg * (D / 2 + 0.25); eave(R, V3(-X, arc(z), z), V3(X, arc(z), z), V3(0, 0, sg), 0.25, V3(-W / 2, 0, sg * D / 2), V3(W / 2, 0, sg * D / 2), true); }
  // caras para paneles: cada mitad de la bóveda se describe como arco
  return [1, -1].map((sg) => ({ arc: true, sg, W, D, yc, Rr, rot: R.rot, n: (R.rot ? V3(0, 0, sg).applyMatrix4(new THREE.Matrix4().extractRotation(R.rot)) : V3(0, 0, sg)) }));
}
function flat(W, D, eaveY, t, R) {
  const pp = t.parapeto ?? 0.6;
  if (pp > 0) {
    R.roof.addRaw(R.rk, rotG(R, polyGeo([V3(-W / 2, eaveY + 0.02, -D / 2), V3(W / 2, eaveY + 0.02, -D / 2), V3(W / 2, eaveY + 0.02, D / 2), V3(-W / 2, eaveY + 0.02, D / 2)], UP, V3(1, 0, 0), V3(0, 0, 1))), true);
    // obra nueva (R.side): cada lado con su acabado y UV a escala; los antepechos ±X se acortan para no solapar las esquinas
    if (R.side) for (const [s, w, d, x, z] of [['+Z', W + 0.4, 0.2, 0, D / 2], ['-Z', W + 0.4, 0.2, 0, -D / 2], ['+X', 0.2, D - 0.2, W / 2, 0], ['-X', 0.2, D - 0.2, -W / 2, 0]]) R.walls.addRaw(R.side[s].key, rotG(R, uvs(boxUV(w, pp, d, x, eaveY, z, 1), R.side[s].tile)), true);
    else for (const [w, d, x, z] of [[W + 0.4, 0.2, 0, D / 2], [W + 0.4, 0.2, 0, -D / 2], [0.2, D, W / 2, 0], [0.2, D, -W / 2, 0]]) R.walls.addRaw(R.wk, rotG(R, boxG(w, pp, d, x, eaveY, z)), true);
    // remate (coronación) del antepecho
    if (R.trim) for (const [w, d, x, z] of [[W + 0.5, 0.3, 0, D / 2], [W + 0.5, 0.3, 0, -D / 2], [0.3, D - 0.3, W / 2, 0], [0.3, D - 0.3, -W / 2, 0]]) R.walls.addRaw(R.coping, rotG(R, boxG(w, 0.05, d, x, eaveY + pp, z)));
  } else R.roof.addRaw(R.rk, rotG(R, boxUV(W + 0.1, 0.2, D + 0.1, 0, eaveY - 0.18, 0, 1)), true); // losa con borde
  return [{ flat: true, W, D, y: eaveY + 0.02, rot: R.rot }];
}
// cara plana útil para FV: centroide, base ortonormal (u a lo largo, vd pendiente abajo, n normal) en coordenadas locales del volumen
function face(pts, n, u, vd, rot) {
  const P = rot ? pts.map((q) => q.clone().applyMatrix4(rot)) : pts;
  const r3 = rot ? new THREE.Matrix4().extractRotation(rot) : null;
  const tr = (d) => (r3 ? d.clone().applyMatrix4(r3) : d.clone());
  const c = P.reduce((a, q) => a.add(q), V3(0, 0, 0)).multiplyScalar(1 / P.length);
  return { pts: P, c, n: tr(n).normalize(), u: tr(u).normalize(), vd: tr(vd).normalize() };
}

// ---------- muros: tramos tapados por otros volúmenes, vanos y piezas
// segmento [t0, t1] de p→q dentro del rectángulo |x| ≤ hx, |z| ≤ hz (Liang–Barsky)
function clipSeg(p, q, hx, hz) {
  let t0 = 0, t1 = 1; const dx = q.x - p.x, dz = q.z - p.z;
  for (const [pp, qq] of [[-dx, p.x + hx], [dx, hx - p.x], [-dz, p.z + hz], [dz, hz - p.z]]) {
    if (Math.abs(pp) < 1e-12) { if (qq < 0) return null; continue; }
    const r = qq / pp;
    if (pp < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; }
  }
  return t1 - t0 > 1e-6 ? [t0, t1] : null;
}
// Tramos del lado s del volumen A que quedan dentro de otro volumen cerrado (no se ven) o sobre un muro de un
// volumen anterior que mira al mismo lado (serían coplanares): { a0, a1, y0, y1 } en coordenadas de la fachada.
// Con `parapeto` (fachadas de obra nueva), si el tramo corre por el borde de B y B tiene cubierta plana con antepecho,
// lo tapado sube hasta el remate del antepecho: así ventanas, enjutas y parasoles empiezan por encima de él.
function coverage(V, A, s, parapeto = false) {
  const S = A.f.sides[s], e = 0.03, out = [];
  const c = S.n.clone().multiplyScalar(S.half);
  const l = c.clone().addScaledVector(S.t, -S.len / 2).applyMatrix4(A.f.m), r = c.clone().addScaledVector(S.t, S.len / 2).applyMatrix4(A.f.m);
  const nW = S.n.clone().transformDirection(A.f.m);
  for (const B of V) {
    if (B === A || !B.f || B.open) continue;
    const y0 = Math.max(0, B.base - A.base), y1 = Math.min(A.eave, B.top - A.base);
    if (y1 - y0 < 0.05) continue;
    const lb = l.clone().applyMatrix4(B.f.inv), rb = r.clone().applyMatrix4(B.f.inv);
    const tt = clipSeg(lb, rb, B.f.L / 2 + e, B.f.A / 2 + e); if (!tt || (tt[1] - tt[0]) * S.len < 0.05) continue;
    // ¿el tramo corre sobre un borde de B?
    const m = lb.clone().lerp(rb, (tt[0] + tt[1]) / 2), dir = rb.clone().sub(lb).normalize();
    let edge = null;
    if (Math.abs(Math.abs(m.z) - B.f.A / 2) < e && Math.abs(dir.z) < 0.02) edge = m.z > 0 ? '+Z' : '-Z';
    else if (Math.abs(Math.abs(m.x) - B.f.L / 2) < e && Math.abs(dir.x) < 0.02) edge = m.x > 0 ? '+X' : '-X';
    if (edge && B.f.sides[edge].n.clone().transformDirection(B.f.m).dot(nW) > 0.9 && B.i > A.i) continue; // el muro anterior se queda
    const pp = parapeto && edge && B.v.techo?.tipo === 'plano' ? B.v.techo.parapeto ?? 0.6 : 0;
    out.push({ a0: -S.len / 2 + tt[0] * S.len, a1: -S.len / 2 + tt[1] * S.len, y0, y1: pp > 0 ? Math.min(A.eave, B.top + pp + 0.05 - A.base) : y1 });
  }
  return out;
}
const subtract = (ranges, [c0, c1]) => ranges.flatMap(([a, b]) => (c1 <= a || c0 >= b ? [[a, b]] : [[a, Math.min(b, c0)], [Math.max(a, c1), b]].filter(([x, y]) => y - x > 1e-3)));
// rectángulos visibles de un muro de largo len y alto H descontando lo tapado
function wallRects(len, H, cov) {
  const cl = (x) => Math.max(-len / 2, Math.min(len / 2, x));
  const xs = [...new Set([-len / 2, len / 2, ...cov.flatMap((c) => [cl(c.a0), cl(c.a1)])])].sort((a, b) => a - b), out = [];
  for (let i = 0; i < xs.length - 1; i++) {
    const x0 = xs[i], x1 = xs[i + 1]; if (x1 - x0 < 0.01) continue;
    let rg = [[0, H]];
    for (const c of cov) if (c.a0 <= x0 + 1e-3 && c.a1 >= x1 - 1e-3) rg = subtract(rg, [c.y0, c.y1]);
    for (const [y0, y1] of rg) {
      const prev = out.find((q) => Math.abs(q.x1 - x0) < 1e-6 && Math.abs(q.y0 - y0) < 1e-6 && Math.abs(q.y1 - y1) < 1e-6);
      if (prev) prev.x1 = x1; else out.push({ x0, x1, y0, y1 });
    }
  }
  return out;
}
// columnas en el perímetro de un volumen abierto (cada ~sep m), 3 cm adentro del borde: [x, z] locales. En corredores
// y pórticos anchos no se ponen las que quedarían pegadas a un muro (la viga se apoya en él); las pilastras sí.
function columnPts(v, f, V) {
  const sep = v.sep_columnas ?? 3.5, cs = v.columna ?? 0.25, L = f.L, A = f.A, k = cs / 2 + 0.03;
  const nL = Math.max(1, Math.round(L / sep)), nA = Math.max(1, Math.round(A / sep)), pts = new Set();
  for (let i = 0; i <= nL; i++) for (const z of [-A / 2, A / 2]) pts.add(`${(-L / 2 + (i * L) / nL).toFixed(2)},${z.toFixed(2)}`);
  for (let j = 0; j <= nA; j++) for (const x of [-L / 2, L / 2]) pts.add(`${x.toFixed(2)},${(-A / 2 + (j * A) / nA).toFixed(2)}`);
  const out = [...pts].map((q) => { const [x, z] = q.split(',').map(Number); return [x - Math.sign(x) * k, z - Math.sign(z) * k]; });
  if (!V) return out;
  const me = V.findIndex((B) => B.v === v), wide = Math.min(L, A) >= 4 * cs;
  return out.filter(([x, z]) => {
    const c = V3(x, 0, z).applyMatrix4(f.m);
    const dup = V.slice(0, Math.max(0, me)).some((B) => B.open && B.f && columnPts(B.v, B.f).some(([bx, bz]) => V3(bx, 0, bz).applyMatrix4(B.f.m).distanceTo(c) < Math.max(cs, B.v.columna ?? 0.25)));
    return !dup && !(wide && V.some((B) => { if (!B.f || B.open || B.v === v) return false; const l = c.clone().applyMatrix4(B.f.inv), m = cs / 2 + 0.12; return Math.abs(l.x) <= B.f.L / 2 + m && Math.abs(l.z) <= B.f.A / 2 + m; }));
  });
}
// ¿hay otro volumen cerrado o una columna justo delante del tramo [a0, a1] × [y0, y1] del lado s (hasta "depth" m)?
function obstructed(V, A, s, a0, a1, y0, y1, depth) {
  const S = A.f.sides[s], q = [[a0, 0.005], [a1, 0.005], [a1, depth], [a0, depth]].map(([a, o]) => S.n.clone().multiplyScalar(S.half + o).addScaledVector(S.t, a).applyMatrix4(A.f.m));
  const yy0 = A.base + y0, yy1 = A.base + y1;
  const hit = (Q) => !q.concat(Q).some((_, i, all) => {
    const P1 = q, P2 = Q, poly = i < 4 ? P1 : P2, j = i % 4, r0 = poly[j], r1 = poly[(j + 1) % 4], nx = -(r1.z - r0.z), nz = r1.x - r0.x;
    const pr = (S2) => S2.map((w) => w.x * nx + w.z * nz), a = pr(P1), b = pr(P2);
    return Math.max(...a) < Math.min(...b) + 1e-4 || Math.max(...b) < Math.min(...a) + 1e-4;
  });
  for (const B of V) {
    if (B === A || !B.f || B.top < yy0 + 0.05 || B.base > yy1 - 0.05) continue;
    if (!B.open) { if (hit([[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([x, z]) => V3((x * B.f.L) / 2, 0, (z * B.f.A) / 2).applyMatrix4(B.f.m)))) return true; continue; }
    const h = (B.v.columna ?? 0.25) / 2 + 0.05;
    for (const [x, z] of columnPts(B.v, B.f, V)) if (hit([[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([u, w]) => V3(x + u * h, 0, z + w * h).applyMatrix4(B.f.m)))) return true;
  }
  return false;
}
const opInRect = (o, r) => o.along - o.w / 2 > r.x0 + 0.04 && o.along + o.w / 2 < r.x1 - 0.04 && o.y0 >= r.y0 - 1e-3 && o.y0 + o.h < r.y1 - 0.04;
// un rectángulo de muro; en LOD0 con los vanos recortados (puertas como muescas, ventanas como huecos)
function wallRect(part, wk, m0, r, ops, detail, tile) {
  const inner = detail ? ops.filter((o) => opInRect(o, r)) : [];
  if (!inner.length) { part.addRaw(wk, uvs(polyGeo([V3(r.x0, r.y0, 0), V3(r.x1, r.y0, 0), V3(r.x1, r.y1, 0), V3(r.x0, r.y1, 0)], V3(0, 0, 1), V3(1, 0, 0), UP), tile).applyMatrix4(m0), true); return; }
  const notch = inner.filter((o) => o.y0 <= r.y0 + 1e-3).sort((a, b) => a.along - b.along), holes = inner.filter((o) => o.y0 > r.y0 + 1e-3);
  const c = [[r.x0, r.y0]];
  for (const o of notch) c.push([o.along - o.w / 2, r.y0], [o.along - o.w / 2, r.y0 + o.h], [o.along + o.w / 2, r.y0 + o.h], [o.along + o.w / 2, r.y0]);
  c.push([r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]);
  const sh = new THREE.Shape(c.map(([x, y]) => new THREE.Vector2(x, y)));
  for (const o of holes) sh.holes.push(new THREE.Path([[o.along - o.w / 2, o.y0], [o.along + o.w / 2, o.y0], [o.along + o.w / 2, o.y0 + o.h], [o.along - o.w / 2, o.y0 + o.h]].map(([x, y]) => new THREE.Vector2(x, y))));
  part.addRaw(wk, uvs(new THREE.ShapeGeometry(sh), tile).applyMatrix4(m0), true);
}
// intervalos de [x0, x1] libres de vanos que cruzan la franja [y0, y1]
function freeSpans(x0, x1, ops, y0, y1) {
  let sp = [[x0, x1]];
  for (const o of ops) if (o.y0 < y1 && o.y0 + o.h > y0) sp = subtract(sp, [o.along - o.w / 2, o.along + o.w / 2]);
  return sp.filter(([a, b]) => b - a > 0.02);
}
// Vano en LOD0: jambas, fondo oscuro, carpintería (marco, parteluces, vidrio, reja o celosía; hoja con tableros o
// cortina enrollable), alféizar y dintel. En LOD1, un panel plano 4 cm delante del muro.
function opening(part, f, s, o, wk, trimK, detail, topRoom, ext = 1, tile) {
  const th = 2 * f.sides[s].half, k = Math.min(REV, th - 0.03) / REV; // en paños delgados la carpintería se acerca al muro
  const m = sideMatrix(f, s, o.along, o.y0, 0), mi = m.clone().multiply(new THREE.Matrix4().makeScale(1, 1, k)), w = o.w, h = o.h;
  const add = (key, g, uv = false) => g && part.addRaw(key, g.applyMatrix4(mi), uv), addOut = (key, g, uv = false) => g && part.addRaw(key, g.applyMatrix4(m), uv);
  const door = o.kind === 'puerta', cel = !door && (o.tipo === 'celosia' || o.tipo === 'calado');
  const uvScale = (g, s) => { const uv = g.attributes.uv, p = g.attributes.position; for (let i = 0; i < uv.count; i++) uv.setXY(i, p.getX(i) / s, p.getY(i) / s); return g; };
  // fachadas de obra nueva: vidrio del muro cortina y marco oscuro (o.vidrio, o.marco); las réplicas usan los de siempre
  const gk = o.vidrio || 'vidrio', fk = o.marco ? tint('metal_pintado', o.marco) : 'metal_pintado#d9dcdc';
  if (!detail) {
    const key = door ? (w > 2.6 ? 'persiana' : o.vidrio ? gk : 'pintura#4a3a2e') : cel ? 'celosia' : o.tipo === 'reja' ? 'reja_vidrio' : gk;
    addOut(key, uvScale(new THREE.PlaneGeometry(w, h).translate(0, h / 2, 0.04), key === 'celosia' ? 0.9 : key === 'reja_vidrio' ? 0.5 : 1), key !== 'vidrio' && key !== 'pintura#4a3a2e');
    return;
  }
  const d = -REV, q = (pts, n) => add(wk, uvs(polyGeo(pts, n), tile), true);
  q([V3(-w / 2, 0, 0), V3(-w / 2, h, 0), V3(-w / 2, h, d), V3(-w / 2, 0, d)], V3(1, 0, 0));
  q([V3(w / 2, 0, 0), V3(w / 2, 0, d), V3(w / 2, h, d), V3(w / 2, h, 0)], V3(-1, 0, 0));
  q([V3(-w / 2, h, 0), V3(w / 2, h, 0), V3(w / 2, h, d), V3(-w / 2, h, d)], V3(0, -1, 0));
  if (!door) q([V3(-w / 2, 0, 0), V3(w / 2, 0, 0), V3(w / 2, 0, d), V3(-w / 2, 0, d)], V3(0, 1, 0));
  add('pintura#17191b', new THREE.PlaneGeometry(w, h).translate(0, h / 2, d)); // fondo: nada se ve a través del vano
  if (cel) { add('celosia', uvScale(new THREE.PlaneGeometry(w, h).translate(0, h / 2, -0.05), 0.9), true); return; }
  if (!door) {
    const vit = o.tipo === 'vitrina', fw = 0.05;
    add(gk, new THREE.PlaneGeometry(w, h).translate(0, h / 2, -0.075));
    add(fk, boxG(w, fw, 0.06, 0, 0, -0.06)); add(fk, boxG(w, fw, 0.06, 0, h - fw, -0.06));
    add(fk, boxG(fw, h - 2 * fw, 0.06, -w / 2 + fw / 2, fw, -0.06)); add(fk, boxG(fw, h - 2 * fw, 0.06, w / 2 - fw / 2, fw, -0.06));
    const nV = Math.max(1, Math.round(w / (o.tipo === 'franja' ? 1.5 : vit ? 1.1 : 0.75)));
    for (let i = 1; i < nV; i++) add(fk, boxG(0.035, h - 2 * fw, 0.04, -w / 2 + (i * w) / nV, fw, -0.06));
    const yT = vit ? (h > 2.3 ? 2.0 : 0) : h > 1.5 ? h * 0.68 : 0;
    if (yT) add(fk, boxG(w - 2 * fw, 0.035, 0.04, 0, yT, -0.06));
    if (o.tipo === 'reja') {
      const nb = Math.max(2, Math.round(w / 0.12));
      for (let i = 0; i < nb; i++) add('metal_pintado#3f4448', boxG(0.018, h, 0.018, -w / 2 + ((i + 0.5) * w) / nb, 0, -0.012));
      for (const yy of [h / 3, (2 * h) / 3]) add('metal_pintado#3f4448', boxG(w, 0.03, 0.008, 0, yy, -0.016));
    }
    if (!vit && ext !== null) addOut(trimK, boxW(w + 0.12 * ext, 0.05, 0.09, 0, -0.065, 0.045)); // alféizar
  } else {
    const fw = 0.07, lw = w - 2 * fw, lh = h - fw;
    add(fk, boxG(fw, h, 0.08, -w / 2 + fw / 2, 0, -0.06)); add(fk, boxG(fw, h, 0.08, w / 2 - fw / 2, 0, -0.06)); add(fk, boxG(lw, fw, 0.08, 0, h - fw, -0.06));
    if (w > 2.6) {
      // portón: cortina enrollable de lamas con barra inferior y manijas
      const g = new THREE.PlaneGeometry(lw, lh).translate(0, lh / 2, -0.08), uv = g.attributes.uv, p = g.attributes.position;
      for (let i = 0; i < uv.count; i++) uv.setXY(i, p.getX(i), p.getY(i));
      add('persiana', g, true);
      add('metal_pintado#2b2d30', boxG(lw, 0.07, 0.05, 0, 0, -0.075));
      for (const x of [-lw / 4, lw / 4]) add('metal_pintado#c4c8cb', boxG(0.14, 0.03, 0.03, x, 0.25, -0.045));
    } else if (o.vidrio) {
      // puerta de aluminio y vidrio (fachadas de obra nueva): hojas con marco, vidrio y manija vertical
      const n = w > 1.3 ? 2 : 1, lwi = lw / n;
      for (let i = 0; i < n; i++) {
        const cx = -lw / 2 + lwi * (i + 0.5);
        add(gk, new THREE.PlaneGeometry(lwi - 0.1, lh - 0.1).translate(cx, lh / 2, -0.08));
        add(fk, boxG(lwi - 0.01, 0.06, 0.04, cx, 0, -0.08)); add(fk, boxG(lwi - 0.01, 0.06, 0.04, cx, lh - 0.06, -0.08));
        for (const sx of [-1, 1]) add(fk, boxG(0.05, lh - 0.12, 0.04, cx + sx * (lwi / 2 - 0.03), 0.06, -0.08));
        const hx = n === 2 ? (i ? -lwi / 2 + 0.12 : lwi / 2 - 0.12) : lwi / 2 - 0.14;
        add('metal_pintado#c4c8cb', boxG(0.03, 0.7, 0.04, cx + hx, 0.75, -0.04));
      }
    } else {
      const n = w > 1.3 ? 2 : 1, lwi = lw / n;
      for (let i = 0; i < n; i++) {
        const cx = -lw / 2 + lwi * (i + 0.5);
        add('pintura#4a3a2e', boxG(lwi - 0.01, lh, 0.04, cx, 0, -0.08));
        for (const [yy, hh] of [[0.18, lh * 0.36], [lh * 0.6, lh * 0.3]]) add('pintura#4a3a2e', boxG(lwi - 0.24, hh, 0.015, cx, yy, -0.0525));
        const hx = n === 2 ? (i ? -lwi / 2 + 0.08 : lwi / 2 - 0.08) : lwi / 2 - 0.1;
        add('metal_pintado#c4c8cb', boxG(0.03, 0.15, 0.05, cx + hx, 0.95, -0.035));
      }
    }
  }
  if (topRoom > 0.14 && ext !== null) addOut(trimK, boxW(w + 0.2 * ext, 0.1, 0.02, 0, h, 0.01)); // dintel
}

// ---------- volumen: muros, vanos, zócalo, entrepisos, corredor, letrero, cubierta, canales y bajantes
function volume(b, vi, V, P, detail) {
  const v = vi.v, f = vi.f, base = vi.base, eaveH = vi.eave, abierto = vi.open;
  const fa = v.fachada || {};
  let t = v.techo || { tipo: 'plano' };
  const wk = wallMat(fa), wcol = wallColor(fa);
  const trimK = tint('pintura', shade(wcol, 0.86)), soffit = 'pintura#e2dfd6'; // cielo raso del alero: claro neutro
  const L = f.L, A = f.A, pisos = Math.max(1, v.pisos ?? 1), hf = eaveH / pisos;
  const W = P.walls, M = (g, m) => g.applyMatrix4(m);
  vi.ops = {}; vi.cov = {}; vi.pipes = {}; vi.cols = [];
  // acabado por lado (fachadas de obra nueva: muro cortina, panel compuesto, concreto a la vista…); null en las réplicas
  const SS = abierto ? null : cladSides(fa, f);
  if (SS) newMats(b);
  vi.SS = SS;
  if (abierto) {
    // pórtico, corredor o kiosco: columnas en el perímetro (cada ~3,5 m) con basa y capitel, y viga de amarre
    const cs = v.columna ?? 0.25, floor = v.piso !== false && base === 0;
    for (const [cx, cz] of columnPts(v, f, V)) {
      W.addRaw(wk, M(boxG(cs, eaveH, cs, cx, 0, cz), f.m), true);
      vi.cols.push(V3(cx, 0, cz).applyMatrix4(f.m));
      if (detail) {
        if (eaveH > 1.2) W.addRaw(trimK, M(boxG(cs + 0.1, 0.27, cs + 0.1, cx, (floor ? PISO : 0) - 0.02, cz), f.m));
        if (eaveH > 1.0) W.addRaw(trimK, M(boxG(cs + 0.08, 0.1, cs + 0.08, cx, eaveH - 0.4, cz), f.m));
      }
    }
    for (const [a, b2] of [[V3(-L / 2 + 0.03, 0, A / 2 - 0.13), V3(L / 2 - 0.03, 0, A / 2 - 0.13)], [V3(-L / 2 + 0.03, 0, -A / 2 + 0.13), V3(L / 2 - 0.03, 0, -A / 2 + 0.13)], [V3(L / 2 - 0.13, 0, -A / 2 + 0.23), V3(L / 2 - 0.13, 0, A / 2 - 0.23)], [V3(-L / 2 + 0.13, 0, -A / 2 + 0.23), V3(-L / 2 + 0.13, 0, A / 2 - 0.23)]]) {
      const wa = a.clone().applyMatrix4(f.m), wb = b2.clone().applyMatrix4(f.m);
      let spans = [[0, 1]];
      for (const B of V) if (B.f && !B.open && B !== vi && B.top > vi.base + eaveH - 0.3 && B.base < vi.base + eaveH) { const tt = clipSeg(wa.clone().applyMatrix4(B.f.inv), wb.clone().applyMatrix4(B.f.inv), B.f.L / 2 + 0.12, B.f.A / 2 + 0.12); if (tt) spans = subtract(spans, tt); }
      for (const [t0, t1] of spans) if ((t1 - t0) * a.distanceTo(b2) > 0.1) W.addRaw(wk, beamG(wa.clone().lerp(wb, t0).setY(vi.base + eaveH - 0.15), wa.clone().lerp(wb, t1).setY(vi.base + eaveH - 0.15), 0.2, 0.3), true);
    }
    if (floor) W.addRaw('piso', M(boxUV(L + 0.16, PISO, A + 0.16), f.m), true);
  }
  if (t.tipo === 'ninguno') W.addRaw(wk, M(boxG(L, 0.15, A, 0, eaveH - 0.15, 0), f.m), true);
  if (!abierto) {
    // vanos por lado: puertas de la especificación y ventanas por piso (las del primer piso no van sobre puertas)
    const ops = {}, doors = {};
    for (const s of Object.keys(f.sides)) ops[s] = [];
    for (const d of fa.puertas || []) {
      const s = sideFor(f, d.lado), S = f.sides[s], w = d.ancho ?? 1.8, h = Math.min(d.alto ?? 2.4, eaveH - 0.15), along = ((d.pos ?? 0.5) - 0.5) * S.len;
      (doors[s] ||= []).push([along - w / 2 - 0.4, along + w / 2 + 0.4]);
      ops[s].push({ kind: 'puerta', along, w, h, y0: 0 });
    }
    const vn = fa.ventanas;
    if (vn) {
      const ww = vn.ancho ?? 1.4, wh = vn.alto ?? 1.2, sill = vn.antepecho ?? 1.0, sep = Math.max(ww + 0.4, vn.separacion ?? 3), tipo = vn.tipo || 'ventana';
      for (const s of sidesOf(f, vn.lados)) {
        const S = f.sides[s], n = Math.max(0, Math.floor((S.len - 1.2 - ww) / sep) + 1);
        for (let k = 0; k < pisos; k++) {
          const y = k * hf + (tipo === 'vitrina' ? 0.25 : sill), h = tipo === 'vitrina' ? Math.min(hf - 0.6, 2.6) : Math.min(wh, hf - sill - 0.25);
          if (h < 0.3) continue;
          if (tipo === 'franja') {
            // ventana corrida: una por piso de punta a punta (menos el margen); en el primer piso se corta en las puertas.
            // Después se parte en los tramos visibles del muro
            const mg = vn.margen ?? 0.6;
            let sp = [[-S.len / 2 + mg, S.len / 2 - mg]];
            if (k === 0) for (const dd of doors[s] || []) sp = subtract(sp, dd);
            for (const [a0, a1] of sp) if (a1 - a0 > 0.8) ops[s].push({ kind: 'ventana', tipo, along: (a0 + a1) / 2, w: a1 - a0, h, y0: y });
            continue;
          }
          for (let i = 0; i < n; i++) {
            const along = (i - (n - 1) / 2) * sep;
            if (k === 0 && (doors[s] || []).some(([a0, a1]) => along + ww / 2 > a0 && along - ww / 2 < a1)) continue;
            ops[s].push({ kind: 'ventana', tipo, along, w: ww, h, y0: y });
          }
        }
      }
    }
    for (const [s, S] of Object.entries(f.sides)) {
      vi.cov[s] = coverage(V, vi, s, !!SS);
      const rects = wallRects(S.len, eaveH, vi.cov[s]), m0 = sideMatrix(f, s, 0, 0, 0);
      const sd = SS ? SS[s] : null, wkS = sd ? sd.key : wk, trimS = sd?.clad ? tint('metal_pintado', PERFIL_DEF) : sd ? tint('pintura', shade(sd.color, 0.86)) : trimK;
      // en el muro cortina solo quedan las puertas (el muro es el vidrio); las ventanas corridas se parten por tramos visibles
      let list = sd?.cortina ? ops[s].filter((o) => o.kind === 'puerta') : ops[s];
      list = list.flatMap((o) => (o.tipo !== 'franja' ? [o] : rects.filter((r) => r.y0 <= o.y0 + 1e-3 && o.y0 + o.h < r.y1 - 0.04).flatMap((r) => {
        const a0 = Math.max(o.along - o.w / 2, r.x0 + 0.35), a1 = Math.min(o.along + o.w / 2, r.x1 - 0.35);
        return a1 - a0 > 0.8 ? [{ ...o, along: (a0 + a1) / 2, w: a1 - a0 }] : [];
      })));
      if (sd?.clad) for (const o of list) Object.assign(o, { vidrio: tint('vidrio_cortina', hexOK(fa.muro_cortina?.color_vidrio, VIDRIO_DEF)), marco: hexOK(fa.ventanas?.color_marco, '#3b4043') });
      // solo quedan los vanos que caben enteros en un tramo visible y no se pisan entre sí
      const kept = [];
      for (const o of list) {
        if (!rects.some((r) => opInRect(o, r))) continue;
        if (o.kind === 'ventana' && obstructed(V, vi, s, o.along - o.w / 2 + 0.05, o.along + o.w / 2 - 0.05, o.y0, o.y0 + o.h, 0.12)) continue;
        if (kept.some((k) => Math.abs(k.along - o.along) < (k.w + o.w) / 2 + 0.08 && k.y0 < o.y0 + o.h + 0.08 && o.y0 < k.y0 + k.h + 0.08)) continue;
        kept.push(o);
      }
      vi.ops[s] = kept;
      if (sd?.cortina) { curtainSide(W, vi, s, rects, kept, sd, SS, detail); continue; }
      for (const r of rects) wallRect(W, wkS, m0, r, kept, detail, sd?.tile);
      for (const o of kept) {
        const r = rects.find((q) => opInRect(o, q)), ob = (e) => obstructed(V, vi, s, o.along - o.w / 2 - e, o.along + o.w / 2 + e, o.y0 - 0.1, o.y0 + o.h + 0.12, 0.12);
        opening(W, f, s, o, wkS, trimS, detail, r.y1 - (o.y0 + o.h), !ob(0.1) ? 1 : !ob(0) ? 0 : null, sd?.tile);
      }
      // los acabados nuevos no llevan zócalo pintado ni bandas de entrepiso (las reemplazan las losas expresadas)
      if (sd?.clad) continue;
      // zócalo (2,5 cm) y bandas de entrepiso (12 cm), interrumpidos en los vanos; envuelven las esquinas
      const zh = fa.zocalo ? fa.zocalo.altura ?? 0.8 : 0, zk = fa.zocalo ? tint('pintura', fa.zocalo.color, '#7a2b2b') : null;
      for (const r of rects) {
        const ext = (a, bb, e) => [Math.abs(a + S.len / 2) < 1e-3 ? a - e : a, Math.abs(bb - S.len / 2) < 1e-3 ? bb + e : bb];
        if (zk && r.y0 < 0.01) for (const [a, bb] of freeSpans(r.x0, r.x1, kept, 0, zh + 0.03)) { const [x0, x1] = ext(a, bb, 0.025); W.addRaw(zk, M(boxW(x1 - x0, Math.min(zh, r.y1), 0.025, (x0 + x1) / 2, 0, 0.0125), m0)); }
        for (let k = 1; k < pisos && !fa.losas_expresadas; k++) {
          const yb = k * hf - 0.1; if (yb < r.y0 || yb + 0.2 > r.y1) continue;
          for (const [a, bb] of freeSpans(r.x0, r.x1, kept, yb, yb + 0.2)) { const [x0, x1] = ext(a, bb, 0.12); W.addRaw(trimS, M(boxW(x1 - x0, 0.2, 0.12, (x0 + x1) / 2, yb, 0.06), m0)); }
        }
      }
    }
    // obra nueva: bordes de losa que sobresalen en cada piso y parasoles (instanciados)
    if (fa.losas_expresadas) slabEdges(W, vi, fa.losas_expresadas, P.puentes, P);
    if (fa.parasoles) sunShades(P, vi, fa, SS, detail);
  }
  // corredor con columnas (basa y capitel), viga, piso elevado y cubierta con tapa
  const co = fa.corredor;
  if (co) {
    const s = sideFor(f, co.lado), S = f.sides[s], d = co.profundidad ?? 2.4, sep = co.sep_columnas ?? 3.5, len = S.len, m = sideMatrix(f, s, 0, 0, 0);
    const yTop = (pisos > 1 ? hf : eaveH) - 0.05;
    W.addRaw('piso', M(boxUV(len - 0.12, PISO, d + 0.07, 0, 0, (d + 0.07) / 2 - 0.03), m), true);
    const nC = Math.max(2, Math.round(len / sep) + 1);
    for (let i = 0; i < nC; i++) {
      const x = -len / 2 + 0.2 + (i * (len - 0.4)) / (nC - 1);
      W.addRaw(wk, M(boxG(0.25, yTop - PISO, 0.25, x, PISO, d - 0.2), m), true);
      if (detail) { W.addRaw(trimK, M(boxG(0.35, 0.27, 0.35, x, PISO - 0.02, d - 0.2), m)); W.addRaw(trimK, M(boxG(0.33, 0.1, 0.33, x, yTop - 0.38, d - 0.2), m)); }
    }
    W.addRaw(wk, M(boxG(len, 0.28, 0.25, 0, yTop - 0.28, d - 0.2), m), true);
    const rk = t.tipo === 'ninguno' || t.tipo === 'plano' ? roofMat(b, { material: 'concreto' }) : roofMat(b, t);
    const drop = (d + 0.3) * Math.tan(8 * D2R);
    P.roofKeep.addRaw(rk, M(polyGeo([V3(-len / 2 - 0.2, yTop + 0.15, 0), V3(len / 2 + 0.2, yTop + 0.15, 0), V3(len / 2 + 0.2, yTop + 0.15 - drop, d + 0.3), V3(-len / 2 - 0.2, yTop + 0.15 - drop, d + 0.3)], UP, V3(1, 0, 0), V3(0, 0, 1)), m), true);
    if (detail) P.roofKeep.addRaw(rk, M(boxG(len + 0.4, 0.15, 0.03, 0, yTop + 0.15 - drop - 0.15, d + 0.315), m), true);
  }
  // letrero (en relieve, 3 cm delante del muro)
  const le = fa.letrero;
  if (le?.texto && !abierto) {
    const s = sideFor(f, le.lado), S = f.sides[s], chars = le.texto.length;
    const size = Math.max(0.18, Math.min(0.55, (S.len * 0.8) / Math.max(1, chars * 0.68)));
    const tg = textGeo(le.texto, size, 0.04, true);
    if (tg) {
      const dd = (vi.ops[s] || []).filter((o) => o.kind === 'puerta');
      const along = dd.length ? dd[0].along : 0;
      const top = (pisos > 1 ? hf : eaveH) - size - 0.12, doorTop = Math.max(0, ...dd.map((o) => o.h + 0.1));
      const y = Math.min(top, Math.max(doorTop + 0.25, (pisos > 1 ? hf : eaveH) - size - 0.35));
      W.addRaw(tint('pintura_satin', le.color, '#1b3d7a'), M(tg, sideMatrix(f, s, along, y, SS?.[s]?.cortina ? CW_D + 0.05 : 0.045)));
    }
  }
  // cubierta
  const ry = new THREE.Matrix4().makeRotationY(Math.PI / 2);
  const along = t.cumbrera !== 'corto';
  const roofParts = (R) => {
    if (t.tipo === 'dos_aguas') return along ? gable(L, A, eaveH, t, R) : gable(A, L, eaveH, t, { ...R, rot: ry });
    if (t.tipo === 'cuatro_aguas') return hip(L, A, eaveH, t, R);
    if (t.tipo === 'una_agua') {
      const s = sideFor(f, t.caida || 'S');
      const rot = { '+Z': null, '-Z': new THREE.Matrix4().makeRotationY(Math.PI), '+X': ry, '-X': new THREE.Matrix4().makeRotationY(-Math.PI / 2) }[s];
      return s === '+Z' || s === '-Z' ? shed(L, A, eaveH, t, { ...R, rot }) : shed(A, L, eaveH, t, { ...R, rot });
    }
    if (t.tipo === 'curvo') return along ? vault(L, A, eaveH, t, R) : vault(A, L, eaveH, t, { ...R, rot: ry });
    if (t.tipo === 'plano') return flat(L, A, eaveH, t, R);
    return [];
  };
  // las caras se generan en coordenadas locales; se agregan aplicando el marco del volumen
  const local = { walls: new Part(), roof: new Part() }, eaves = [];
  if (vi.lift && t.voladizo !== 0) t = { ...t, voladizo: Math.max(0.05, (t.voladizo ?? (t.tipo === 'curvo' ? 0.4 : 0.6)) - vi.lift * 1.5) };
  const R0 = { roof: local.roof, walls: local.walls, wk, rk: roofMat(b, t), caps: detail, trim: detail, closed: !abierto, eaves, soffit, coping: tint('pintura', '#dcd9d1') };
  // antepecho por lado con el acabado de cada fachada (coronación de aluminio sobre el muro cortina) y remate metálico
  if (SS) Object.assign(R0, { side: Object.fromEntries(Object.entries(SS).map(([s, sd]) => [s, crownOf(fa, sd)])), coping: tint('metal_pintado', '#c9cdd0') });
  const faces = roofParts(R0), lift = vi.lift || 0;
  const raise = (part) => { if (lift) for (const gs of part.byMat.values()) for (const g of gs) g.translate(0, lift, 0); };
  raise(local.roof);
  if (lift) {
    for (const e of eaves) { e.a.y += lift; e.b.y += lift; }
    for (const q of faces || []) { if (q.c) { q.c.y += lift; q.pts.forEach((x) => { x.y += lift; }); } if (q.flat) q.y += lift; if (q.arc) q.yc += lift; }
  }
  const replaced = !!(P.newRoof && P.replace(v));
  if (replaced) { const nr = new Part(); roofParts({ ...R0, roof: nr, walls: new Part(), rk: roofMat(b, P.newRoofSpec(t)), trim: false, eaves: [] }); raise(nr); mergeInto(P.newRoof, nr, f.m); }
  mergeInto(W, local.walls, f.m);
  mergeInto(replaced ? P.roof : P.roofKeep, local.roof, f.m);
  const roofGeos = [...local.roof.byMat.values()].flat();
  // canales en los aleros y bajantes por el muro (evitan vanos y tramos tapados)
  if (detail) for (const e of eaves) {
    const out = e.out.clone().transformDirection(f.m), a = e.a.clone().applyMatrix4(f.m), bb = e.b.clone().applyMatrix4(f.m);
    const ga = a.clone().addScaledVector(out, 0.16), gb = bb.clone().addScaledVector(out, 0.16); ga.y -= 0.1; gb.y -= 0.1;
    const gl = ga.distanceTo(gb);
    W.addRaw('metal_pintado#c3c7c8', new THREE.CylinderGeometry(0.065, 0.065, gl, 8).rotateZ(Math.PI / 2).rotateY(-Math.atan2(gb.z - ga.z, gb.x - ga.x)).translate((ga.x + gb.x) / 2, (ga.y + gb.y) / 2 + 0.01, (ga.z + gb.z) / 2));
    if (abierto || !e.pipes) continue;
    const sKey = Object.keys(f.sides).find((k) => f.sides[k].n.dot(e.out) > 0.9); if (!sKey) continue;
    const S = f.sides[sKey], w0 = e.w0.dot(S.t), w1 = e.w1.dot(S.t), lo = Math.min(w0, w1) + 0.3, hi = Math.max(w0, w1) - 0.3;
    if (hi - lo < 1) continue;
    const nMid = Math.max(0, Math.round((hi - lo) / 20) - 1), cands = [lo, hi, ...Array.from({ length: nMid }, (_, i) => lo + ((i + 1) * (hi - lo)) / (nMid + 1))];
    vi.pipes[sKey] = [];
    for (const c0 of cands) {
      let at = null;
      for (let k = 0; k < 8 && at === null; k++) {
        const c = c0 + (c0 === hi ? -1 : 1) * k * 0.4;
        if (c < lo - 1e-6 || c > hi + 1e-6) break;
        const blocked = (vi.cov[sKey] || []).some((q) => c > q.a0 - 0.15 && c < q.a1 + 0.15 && q.y0 < e.a.y) || (vi.ops[sKey] || []).some((o) => Math.abs(c - o.along) < o.w / 2 + 0.15);
        if (!blocked) at = c;
      }
      if (at === null) continue;
      vi.pipes[sKey].push(at);
      const wall = S.n.clone().multiplyScalar(S.half + 0.07).addScaledVector(S.t, at), gut = S.n.clone().multiplyScalar(S.half + e.wd + 0.16).addScaledVector(S.t, at);
      const y0 = e.a.y - 0.14;
      const pts = [V3(gut.x, y0, gut.z), V3(gut.x, y0 - 0.12, gut.z), V3(wall.x, y0 - 0.3, wall.z), V3(wall.x, 0.32, wall.z), V3(wall.x + S.n.x * 0.14, 0.14, wall.z + S.n.z * 0.14)].map((q) => q.applyMatrix4(f.m));
      pipe(W, 'metal_pintado#c3c7c8', pts, 0.045, true, 8);
    }
  }
  return { f, faces: (faces || []).map((q) => ({ ...q, m: f.m })), eave: eaveH, base, roofGeos };
}
function mergeInto(dst, src, m) { for (const [k, gs] of src.byMat) for (const g of gs) dst.addRaw(k, g.applyMatrix4(m), !!g.attributes.uv); }
function volumePoly(b, v, P, detail) {
  const fa = v.fachada || {}, wk = wallMat(fa), base = v.base ?? 0, h = Math.max(0.3, (v.altura_alero ?? 3) - base);
  const shape = new THREE.Shape(v.poligono.map(([x, y]) => new THREE.Vector2(x, y)));
  const g = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false }); g.rotateX(-Math.PI / 2); g.translate(0, base, 0);
  P.walls.addRaw(wk, g.index ? g.toNonIndexed() : g, true);
  if ((v.techo?.tipo ?? 'plano') === 'plano' && (v.techo?.parapeto ?? 0.5) > 0) {
    const pts = v.poligono, pp = v.techo?.parapeto ?? 0.5;
    for (let i = 0; i < pts.length; i++) {
      const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length], len = Math.hypot(x1 - x0, y1 - y0);
      if (len < 0.05) continue;
      const m = new THREE.Matrix4().compose(V3((x0 + x1) / 2, base + h, -(y0 + y1) / 2), new THREE.Quaternion().setFromAxisAngle(UP, Math.atan2(y1 - y0, x1 - x0)), V3(1, 1, 1));
      P.walls.addRaw(wk, boxG(len + 0.2, pp, 0.2).applyMatrix4(m), true);
      if (detail) P.walls.addRaw(tint('pintura', '#dcd9d1'), boxG(len + 0.3, 0.05, 0.3, 0, pp, 0).applyMatrix4(m));
    }
  }
  return { faces: [], eave: base + h, base, roofGeos: [] };
}

// ---------- fachadas de obra nueva: acabado por lado, muro cortina, losas expresadas y parasoles
// Solo se activan con las opciones nuevas (fachada.lados_material, materiales muro_cortina / panel_compuesto /
// concreto_visto, fachada.ladrillo, losas_expresadas, parasoles): las réplicas existentes se generan igual que antes.
const CLAD = { muro_cortina: '#2f4656', panel_compuesto: '#d3d6d8', concreto_visto: '#bdbab2', ladrillo_visto: '#b4583c' };
const VIDRIO_DEF = '#2f4656', PERFIL_DEF = '#c3c8cc';
const CW_D = 0.1; // los parales del muro cortina sobresalen 10 cm del vidrio
const hsh = (a, b) => { let h = (a * 374761393 + b * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177; return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };
const unitBox = new THREE.BoxGeometry(1, 1, 1);
// materiales de obra nueva: se crean solo cuando una especificación los usa
function newMats(b) {
  if (b.mats.vidrio_cortina) return;
  b.mat('vidrio_cortina', { color: '#ffffff', rough: 0.07, metal: 0.55 }); // oscuro y algo reflejante (más con el mapa de entorno de la web)
  b.mat('muro_panel', { color: '#ffffff', rough: 0.4, metal: 0.4, tex: TEX.panel });
  b.mat('muro_concreto', { color: '#ffffff', rough: 0.93, tex: TEX.concreto_tabla });
  b.mat('muro_ladrillo_fino', { color: '#ffffff', rough: 0.9, tex: TEX.ladrillo_fino });
  b.mat('luz', { color: '#fff8ec', rough: 0.5, emissive: '#fff1d0' });
}
// acabado de un lado: { material, key (material#color), color, tile (baldosa en m), clad (acabado nuevo), cortina, cw }
function cladOf(fa, m, c, nuevo) {
  if (!(m in CLAD) || (m === 'ladrillo_visto' && !nuevo)) return { material: m, key: wallMat({ material: m, color: c }), color: wallColor({ material: m, color: c }), clad: false };
  const color = hexOK(c, CLAD[m]), o = { material: m, color, clad: true, cortina: m === 'muro_cortina' };
  if (m === 'panel_compuesto') { const p = fa.panel || {}; o.key = tint('muro_panel', color); o.tile = [4 * (p.ancho ?? 1.5), 4 * (p.alto ?? 0.75)]; }
  else if (m === 'concreto_visto') { o.key = tint('muro_concreto', color); o.tile = [2.4, 1.2]; }
  else if (m === 'ladrillo_visto') { o.key = tint('muro_ladrillo_fino', color); o.tile = [1.02, 1.05]; }
  else {
    const cw = fa.muro_cortina || {};
    o.cw = { modulo: Math.max(0.6, cw.modulo ?? 1.5), enjuta: Math.max(0.3, cw.enjuta ?? 1.0), vidrio: hexOK(cw.color_vidrio, hexOK(c, VIDRIO_DEF)), perfil: hexOK(cw.color_perfil, PERFIL_DEF), enjutaColor: hexOK(cw.color_enjuta, '#56636c') };
    o.key = tint('vidrio_cortina', o.cw.vidrio);
  }
  return o;
}
// acabado de cada lado del volumen, o null si la fachada no usa ninguna opción nueva
function cladSides(fa, f) {
  const lm = fa.lados_material && typeof fa.lados_material === 'object' ? fa.lados_material : null, main = fa.material || 'pañete_pintado';
  if (!lm && !(main in CLAD && (main !== 'ladrillo_visto' || fa.ladrillo))) return null;
  const out = {};
  for (const s of Object.keys(f.sides)) out[s] = cladOf(fa, main, fa.color, !!(fa.ladrillo || lm));
  for (const [k, val] of Object.entries(lm || {})) {
    const o = typeof val === 'string' ? { material: val } : val || {}, m = o.material || main;
    if (!['largo', 'corto', 'todos'].includes(k) && !CARD[String(k).toUpperCase()[0]]) { warn.push(`lados_material: lado desconocido "${k}"`); continue; }
    for (const s of sidesOf(f, [k])) out[s] = cladOf(fa, m, o.color ?? (m === main ? fa.color : undefined), true);
  }
  return out;
}
// antepecho de la cubierta plana en un lado: fachada.coronacion, panel del color del perfil sobre el muro cortina, o el acabado del lado
function crownOf(fa, sd) {
  const c = fa.coronacion;
  const o = c ? cladOf(fa, c.material || 'panel_compuesto', c.color, true) : sd;
  return o.cortina ? cladOf(fa, 'panel_compuesto', o.cw.perfil, true) : o;
}
// Muro cortina de un lado: vidrio por módulos (tres tonos apenas distintos, como las unidades reales), enjutas opacas en cada
// losa, en la base y bajo la coronación, parales (10 cm) y travesaños (7 cm) de aluminio, esquineros y puertas de vidrio.
// Cada esquina la pone el lado que la tiene a su derecha; si el vecino de la izquierda no es muro cortina, va un paral de remate.
function curtainSide(W, vi, s, rects, doors, sd, SS, detail) {
  const f = vi.f, S = f.sides[s], len = S.len, eaveH = vi.eave, pisos = Math.max(1, vi.v.pisos ?? 1), hf = eaveH / pisos;
  const cw = sd.cw, m0 = sideMatrix(f, s, 0, 0, 0), pk = tint('metal_pintado', cw.perfil), ek = tint('vidrio_cortina', cw.enjutaColor);
  const dM = CW_D, wM = 0.06, dT = 0.07, e = cw.enjuta;
  const gk = [1, 1.1, 0.9].map((k) => tint('vidrio_cortina', shade(cw.vidrio, k)));
  const bands = [[-1, 0.18], [eaveH - Math.min(e / 2, 0.6), eaveH + 5]];
  for (let k = 1; k < pisos; k++) bands.push([k * hf - e / 2, k * hf + e / 2]);
  const inBand = (y0, y1) => bands.some(([a, c]) => y0 >= a - 1e-3 && y1 <= c + 1e-3);
  const n = Math.max(1, Math.round(len / cw.modulo)), pitch = len / n, grid = Array.from({ length: n - 1 }, (_, i) => -len / 2 + (i + 1) * pitch);
  const dr = doors.map((o) => ({ a: o.along - o.w / 2, b: o.along + o.w / 2, h: o.h }));
  const quad = (key, x0, x1, y0, y1) => W.addRaw(key, polyGeo([V3(x0, y0, 0), V3(x1, y0, 0), V3(x1, y1, 0), V3(x0, y1, 0)], V3(0, 0, 1)).applyMatrix4(m0));
  const bar = (w, h, d, x, y, z) => W.addRaw(pk, boxW(w, h, d, x, y, z).applyMatrix4(m0));
  const uniq = (a) => [...new Set(a.map((x) => +x.toFixed(4)))].sort((p, q) => p - q);
  const left = Object.keys(f.sides).find((k) => f.sides[k].n.dot(S.t) < -0.9), leftCurtain = !!SS[left]?.cortina, sid = Object.keys(f.sides).indexOf(s) * 997;
  for (const r of rects) {
    const xg = grid.filter((x) => x > r.x0 + 0.25 && x < r.x1 - 0.25 && !dr.some((d) => x > d.a - 0.3 && x < d.b + 0.3));
    const xs = uniq([r.x0, r.x1, ...xg, ...dr.flatMap((d) => [d.a, d.b]).filter((x) => x > r.x0 + 0.05 && x < r.x1 - 0.05)]);
    const ys = uniq([r.y0, r.y1, ...bands.flat().filter((y) => y > r.y0 + 0.02 && y < r.y1 - 0.02)]);
    for (let i = 0; i < xs.length - 1; i++) {
      const xa = xs[i], xb = xs[i + 1], door = dr.find((d) => xa >= d.a - 1e-3 && xb <= d.b + 1e-3), col = Math.round((xa + xb) / 2 / pitch);
      for (let j = 0; j < ys.length - 1; j++) {
        let ya = ys[j]; const yb = ys[j + 1];
        if (door && ya < door.h) { if (yb <= door.h + 1e-3) continue; ya = door.h; }
        quad(inBand(ys[j], yb) ? ek : gk[Math.floor(hsh(sid + col, Math.round(ya * 10)) * 2.999)], xa, xb, ya, yb);
      }
    }
    // sobre otro volumen, parales y esquineros arrancan 5 cm más arriba (no quedan en el plano de su cubierta o antepecho)
    const yb = r.y0 > 0.01 ? r.y0 + 0.05 : r.y0, H = r.y1 - yb;
    for (const x of xg) bar(wM, H, dM, x, yb, dM / 2);
    // travesaños en los bordes de las enjutas, cortados en las puertas (el cabezal de la puerta los reemplaza)
    for (const y of uniq(bands.flat().filter((y) => y > r.y0 + 0.04 && y < r.y1 - 0.04))) {
      let sp = [[r.x0, r.x1]];
      for (const d of dr) if (y < d.h + 0.15) sp = subtract(sp, [d.a - 0.1, d.b + 0.1]);
      for (const [a, c] of sp) if (c - a > 0.05) bar(c - a, 0.06, dT, (a + c) / 2, y - 0.03, dT / 2);
    }
    // extremos: esquinero, o paral de remate que entra hasta el muro del volumen vecino (3 cm más allá del tramo visible),
    // a 3 cm de las caras de su antepecho
    if (r.x1 >= len / 2 - 1e-3) bar(wM + dM, H, wM + dM, len / 2 + (dM - wM) / 2, yb, (dM - wM) / 2); // esquinero
    else bar(0.07, H, dM, r.x1 - 0.005, yb, dM / 2);
    if (r.x0 > -len / 2 + 1e-3) bar(0.07, H, dM, r.x0 + 0.005, yb, dM / 2);
    else if (!leftCurtain) bar(wM, H, dM, -len / 2 + wM / 2, yb, dM / 2);
  }
  for (const o of doors) curtainDoor(W, f, s, o, sd, detail);
}
// Puerta en el muro cortina: vestíbulo hundido 40 cm con retornos de aluminio, marco exterior, hojas corredizas
// automáticas (paños fijos laterales en vanos de más de 3,2 m) y cabezal del operador. En LOD1, un paño de vidrio.
function curtainDoor(W, f, s, o, sd, detail) {
  const m = sideMatrix(f, s, o.along, 0, 0), add = (k, g) => W.addRaw(k, g.applyMatrix4(m));
  const cw = sd.cw, pk = tint('metal_pintado', cw.perfil), w = o.w, h = o.h, R = 0.4, lg = tint('vidrio_cortina', shade(cw.vidrio, 1.3));
  if (!detail) { add(lg, new THREE.PlaneGeometry(w, h).translate(0, h / 2, -0.05)); return; }
  const q = (k, pts, n) => add(k, polyGeo(pts, n));
  q('pintura#17191b', [V3(-w / 2, 0, -R), V3(w / 2, 0, -R), V3(w / 2, h, -R), V3(-w / 2, h, -R)], V3(0, 0, 1));
  q(pk, [V3(-w / 2, 0, 0), V3(-w / 2, h, 0), V3(-w / 2, h, -R), V3(-w / 2, 0, -R)], V3(1, 0, 0));
  q(pk, [V3(w / 2, 0, 0), V3(w / 2, 0, -R), V3(w / 2, h, -R), V3(w / 2, h, 0)], V3(-1, 0, 0));
  q(pk, [V3(-w / 2, h, 0), V3(w / 2, h, 0), V3(w / 2, h, -R), V3(-w / 2, h, -R)], V3(0, -1, 0));
  const dd = CW_D + 0.04;
  for (const sx of [-1, 1]) add(pk, boxW(0.08, h + 0.12, dd, sx * (w / 2 + 0.04), 0, dd / 2));
  add(pk, boxW(w, 0.12, dd, 0, h, dd / 2));
  const np = w > 3.2 ? 4 : w > 1.5 ? 2 : 1, pw = w / np, zl = -0.22, hl = h - 0.24;
  add(pk, boxG(w, 0.24, 0.2, 0, hl, zl));
  for (let i = 0; i < np; i++) {
    const cx = -w / 2 + pw * (i + 0.5);
    add(lg, new THREE.PlaneGeometry(pw - 0.08, hl - 0.08).translate(cx, hl / 2, zl));
    add(pk, boxG(pw, 0.05, 0.05, cx, 0, zl));
    for (const sx of [-1, 1]) add(pk, boxG(0.045, hl - 0.05, 0.05, cx + sx * (pw / 2 - 0.0225), 0.05, zl));
  }
}
// Losas expresadas: borde de losa que sobresale `voladizo` en cada entrepiso (y en la cubierta con `cubierta: true`) por los
// tramos visibles de cada lado; donde otro volumen tapa el muro, el borde entra 3 cm en él. Se guardan en P.rings y se
// dibujan al final (ringsOut), cuando ya se sabe por dónde suben los ductos de la conexión. Los lados ±Z se prolongan en las
// esquinas y los ±X se recortan 12 cm (lo que el borde entra en el muro), para que dos bordes nunca se solapen.
function slabEdges(W, vi, le, cuts, P) {
  const f = vi.f, eaveH = vi.eave, pisos = Math.max(1, vi.v.pisos ?? 1), hf = eaveH / pisos;
  const v = Math.max(0.05, le.voladizo ?? 0.4), e = Math.max(0.1, le.espesor ?? 0.35), key = tint('pintura', le.color, '#eeede9');
  const ys = Array.from({ length: pisos - 1 }, (_, k) => (k + 1) * hf);
  if (le.cubierta) ys.push(eaveH);
  for (const s of sidesOf(f, le.lados || ['todos'])) {
    const S = f.sides[s], m0 = sideMatrix(f, s, 0, 0, 0), zs = s === '+Z' || s === '-Z', h = S.len / 2;
    for (const y of ys) {
      const ya = y + 0.05 - e, ym = y + 0.05 - e / 2;
      let sp = [[-h, h]];
      for (const c of vi.cov[s] || []) if (c.y0 <= ym && c.y1 >= ym) sp = subtract(sp, [c.a0 <= -h + 1e-3 ? -h - 1 : c.a0 + 0.06, c.a1 >= h - 1e-3 ? h + 1 : c.a1 - 0.06]);
      for (const [c0, c1, cy0, cy1] of cutsOn(vi, s, cuts, -0.12, v)) if (cy0 < y + 0.05 && cy1 > ya) sp = subtract(sp, [c0, c1]);
      for (let [a0, a1] of sp) {
        if (a0 <= -h + 1e-3) a0 = zs ? -h - v : -h + 0.12;
        if (a1 >= h - 1e-3) a1 = zs ? h + v : h - 0.12;
        if (a1 - a0 > 0.1) P.rings.push({ W, key, m0, vi, s, a0, a1, ya, e, v });
      }
    }
  }
}
// Dibuja los bordes de losa guardados; en la obra nueva se cortan donde pasa un tramo vertical de los ductos de la conexión
function ringsOut(P, cortar) {
  for (const rg of P.rings) {
    let sp = [[rg.a0, rg.a1]];
    const S = rg.vi.f.sides[rg.s], ya = rg.vi.base + rg.ya, yb = ya + rg.e;
    if (cortar(rg.vi)) for (const d of P.ductos) for (let i = 1; i < d.pts.length; i++) {
      const p = d.pts[i - 1], q = d.pts[i];
      if (Math.hypot(p.x - q.x, p.z - q.z) > 0.05 || Math.max(p.y, q.y) < ya || Math.min(p.y, q.y) > yb) continue;
      const l = p.clone().applyMatrix4(rg.vi.f.inv), al = l.dot(S.t), ou = l.dot(S.n) - S.half;
      if (ou > -0.17 - d.r && ou < rg.v + d.r + 0.05) sp = subtract(sp, [al - d.r - 0.06, al + d.r + 0.06]);
    }
    for (const [a0, a1] of sp) if (a1 - a0 > 0.1) rg.W.addRaw(rg.key, boxG(a1 - a0, rg.e, rg.v + 0.12, (a0 + a1) / 2, rg.ya, (rg.v - 0.12) / 2).applyMatrix4(rg.m0));
  }
}
// instancias GPU por capa: una malla unitaria por clave y su lista de transformaciones. Al armar el GLB, las claves con
// menos de 10 instancias se funden en el entorno de su capa (no suman llamadas de dibujo), salvo `siempre` (parasoles)
function inst(P, key, name, make, siempre = false) { let it = P.inst.get(key); if (!it) P.inst.set(key, (it = { name, part: make(), trs: [], siempre })); return it; }
function trsOf(m, s) { const t = V3(0, 0, 0), q = new THREE.Quaternion(), sc = V3(1, 1, 1); m.decompose(t, q, sc); return { t: t.toArray(), r: [q.x, q.y, q.z, q.w], s: s || sc.toArray() }; }
// Huella de cada puente (esquinas en planta y alturas, con su estructura): losas expresadas y parasoles le dejan paso
function bridgeCuts(spec) {
  return (spec.elementos || []).filter((e) => e.tipo === 'puente' && e.desde && e.hasta).map((e) => {
    const a = planToThree(e.desde), c = planToThree(e.hasta), d = c.clone().sub(a).normalize(), n = V3(-d.z, 0, d.x), hw = (e.ancho ?? 3) / 2 + 0.35, y0 = e.altura ?? 4.2;
    const pa = a.clone().addScaledVector(d, -0.4), pc = c.clone().addScaledVector(d, 0.4);
    return { pts: [pa.clone().addScaledVector(n, hw), pc.clone().addScaledVector(n, hw), pc.clone().addScaledVector(n, -hw), pa.clone().addScaledVector(n, -hw)], y0: y0 - (e.estructura === 'viga' ? 1.25 : 0.3), y1: y0 + (e.alto ?? 3) + 0.4 };
  });
}
// tramos [a0, a1, y0, y1] del lado s (en coordenadas de la fachada) que ocupa un puente entre o0 y o1 m del muro
function cutsOn(vi, s, cuts, o0, o1) {
  const S = vi.f.sides[s], out = [];
  for (const c of cuts || []) {
    const ls = c.pts.map((p) => p.clone().applyMatrix4(vi.f.inv)), al = ls.map((l) => l.dot(S.t)), ou = ls.map((l) => l.dot(S.n) - S.half);
    if (Math.max(...ou) < o0 || Math.min(...ou) > o1) continue;
    out.push([Math.min(...al) - 0.05, Math.max(...al) + 0.05, c.y0 - vi.base, c.y1 - vi.base]);
  }
  return out;
}
// Parasoles instanciados (una caja unitaria por color, escalada por instancia). Verticales: aletas de la base (o 1,2 m sobre
// el volumen que tapa el muro) hasta casi el remate del antepecho, con ménsulas en cada losa; en el muro cortina van sobre los
// parales. Horizontales: lamas inclinadas en la parte alta de cada piso, sostenidas por platinas verticales cada ~3 m.
function sunShades(P, vi, fa, SS, detail) {
  const f = vi.f, eaveH = vi.eave, pisos = Math.max(1, vi.v.pisos ?? 1), hf = eaveH / pisos;
  const t = vi.v.techo || {}, pp = t.tipo === 'plano' ? t.parapeto ?? 0.6 : 0;
  for (const ps of [].concat(fa.parasoles)) {
    if (!ps || typeof ps !== 'object') continue;
    const hor = ps.tipo === 'horizontal', d = Math.max(0.1, ps.profundidad ?? 0.6), sep = Math.max(0.2, ps.separacion ?? 0.9), th = ps.espesor ?? (hor ? 0.04 : 0.06);
    const col = hexOK(ps.color, '#d9d5cc'), it = inst(P, `parasol${col}`, 'parasoles', () => new Part().add(`metal_pintado${col}`, unitBox), true);
    const put = (m, sc) => it.trs.push(trsOf(m, sc));
    for (const s of sidesOf(f, ps.lados || ['todos'])) {
      const S = f.sides[s], cw = SS?.[s]?.cortina ? SS[s].cw : null, wz = cw ? CW_D : 0, z0 = wz + 0.05;
      const doorsS = (vi.ops[s] || []).filter((o) => o.kind === 'puerta');
      const M = (x, y, z, rx = 0) => sideMatrix(f, s, x, y, z).multiply(new THREE.Matrix4().makeRotationX(rx));
      const cuts = cutsOn(vi, s, P.puentes, wz, z0 + d);
      for (const r of wallRects(S.len, eaveH, vi.cov[s] || [])) {
        const yA = r.y0 + (r.y0 > 0.05 ? 1.2 : ps.desde ?? 0), yB = r.y1 + (r.y1 > eaveH - 0.01 ? Math.max(0, pp - 0.08) : 0);
        const cL = r.x0 <= -S.len / 2 + 1e-3, cR = r.x1 >= S.len / 2 - 1e-3;
        if (!hor) {
          let xs = [];
          if (cw) { const n = Math.max(1, Math.round(S.len / cw.modulo)), p = S.len / n, k = Math.max(1, Math.round(sep / p)); for (let i = k; i < n; i += k) xs.push(-S.len / 2 + i * p); }
          else { const n = Math.max(1, Math.floor((S.len - 0.6) / sep) + 1); for (let i = 0; i < n; i++) xs.push((i - (n - 1) / 2) * sep); }
          for (const x of xs.filter((x) => x > r.x0 + 0.3 && x < r.x1 - 0.3)) {
            let y0 = yA;
            for (const o of doorsS) if (Math.abs(x - o.along) < o.w / 2 + 0.25) y0 = Math.max(y0, o.h + 0.6);
            if (yB - y0 < 1) continue;
            let ys = [[y0, yB]];
            for (const [c0, c1, cy0, cy1] of cuts) if (x + th > c0 && x - th < c1) ys = subtract(ys, [cy0 - 0.1, cy1 + 0.1]);
            for (const [ya, yb] of ys) if (yb - ya > 0.5) put(M(x, (ya + yb) / 2, z0 + d / 2), [th, yb - ya, d]);
            if (detail) for (let k = 1; k <= pisos; k++) { const yy = Math.min(k * hf, yB) - 0.6; if (yy > y0 + 0.2) put(M(x, yy, (wz - 0.02 + z0 + 0.03) / 2), [0.03, 0.12, z0 + 0.05 - wz]); }
          }
          continue;
        }
        const x0 = r.x0 + (cL ? 0.15 : 0.35), x1 = r.x1 - (cR ? 0.15 : 0.35);
        if (x1 - x0 < 1) continue;
        const np = Math.max(1, Math.ceil((x1 - x0) / 3)), tilt = -(ps.inclinacion ?? 15) * D2R;
        for (let k = 0; k < pisos; k++) {
          const ys = [];
          for (let y = (k + 1) * hf - 0.5; y > k * hf + (ps.antepecho ?? 1.0); y -= sep) if (y > yA && y < Math.min(yB, eaveH) - 0.3) ys.push(y);
          if (!ys.length) continue;
          const yt = ys[0] + 0.15, yb = ys[ys.length - 1] - 0.15;
          let xr = [[x0, x1]];
          for (const [c0, c1, cy0, cy1] of cuts) if (cy0 < yt && cy1 > yb) xr = subtract(xr, [c0, c1]);
          for (const y of ys) for (const [a, c] of xr) if (c - a > 0.3) put(M((a + c) / 2, y, z0 + d / 2, tilt), [c - a, th, d]);
          for (let i = 0; i <= np; i++) if (xr.some(([a, c]) => x0 + 0.03 + (i * (x1 - x0 - 0.06)) / np > a - 1e-3 && x0 + 0.03 + (i * (x1 - x0 - 0.06)) / np < c + 1e-3)) put(M(x0 + 0.03 + (i * (x1 - x0 - 0.06)) / np, (yt + yb) / 2, (wz - 0.02 + z0 + d) / 2), [0.02, yt - yb, z0 + d + 0.02 - wz]);
        }
      }
    }
  }
}

// ---------- suelos escalonados (losas con borde) y altura del suelo en un punto
const planToThree = ([x, y], yy = 0) => V3(x, yy, -y);
function rectOrPoly(o) {
  if (o.poligono) return o.poligono;
  if (o.centro && o.largo) { const f = frame(o); return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, c]) => { const p = V3(a * f.L / 2, 0, c * f.A / 2).applyMatrix4(f.m); return [p.x, -p.z]; }); }
  return null;
}
const area = (q) => q.reduce((s, [x, y], i) => { const [x1, y1] = q[(i + 1) % q.length]; return s + x * y1 - x1 * y; }, 0) / 2;
function insetPoly(q, d) {
  if (!d) return q;
  const sg = area(q) > 0 ? 1 : -1, n = q.length, lines = [];
  for (let i = 0; i < n; i++) { const [x0, y0] = q[i], [x1, y1] = q[(i + 1) % n], l = Math.hypot(x1 - x0, y1 - y0) || 1, nx = (-(y1 - y0) / l) * sg, ny = ((x1 - x0) / l) * sg; lines.push([x0 + nx * d, y0 + ny * d, (x1 - x0) / l, (y1 - y0) / l]); }
  const out = q.map((p, i) => {
    const [ax, ay, adx, ady] = lines[(i + n - 1) % n], [bx, by, bdx, bdy] = lines[i], den = adx * bdy - ady * bdx;
    if (Math.abs(den) < 1e-6) return [bx, by];
    const tt = ((bx - ax) * bdy - (by - ay) * bdx) / den;
    return [ax + adx * tt, ay + ady * tt];
  });
  return Math.sign(area(out)) === Math.sign(area(q)) && Math.abs(area(out)) > Math.abs(area(q)) * 0.5 ? out : q;
}
function inPoly([x, y], q) { let c = false; for (let i = 0, j = q.length - 1; i < q.length; j = i++) { const [xi, yi] = q[i], [xj, yj] = q[j]; if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c; } return c; }
// Losa: tapa exacta a la altura de su nivel y bordes (sardinel) desde el suelo, retranqueados 1,2 cm por nivel
// para que dos losas con un borde común nunca dejen caras verticales coplanares.
function slab(P, mat, pts, tipo) {
  let q = []; for (const p of pts) if (!q.length || Math.hypot(p[0] - q[q.length - 1][0], p[1] - q[q.length - 1][1]) > 0.01) q.push(p);
  if (q.length > 3 && Math.hypot(q[0][0] - q[q.length - 1][0], q[0][1] - q[q.length - 1][1]) < 0.01) q.pop();
  if (q.length < 3 || Math.abs(area(q)) < 0.01) return;
  const y = NIVEL[tipo], k = ORDEN.indexOf(tipo);
  const g = new THREE.ShapeGeometry(new THREE.Shape(q.map(([x, yy]) => new THREE.Vector2(x, yy)))); g.rotateX(-Math.PI / 2); g.translate(0, y, 0);
  const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, g.attributes.position.getX(i) / 2, g.attributes.position.getZ(i) / 2);
  P.env.addRaw(mat, g, true);
  const e = insetPoly(q, k ? 0.045 + 0.012 * k : 0), sg = area(e) > 0 ? 1 : -1;
  for (let i = 0; i < e.length; i++) {
    const [x0, y0] = e[i], [x1, y1] = e[(i + 1) % e.length];
    P.env.addRaw(mat, polyGeo([V3(x0, 0, -y0), V3(x1, 0, -y1), V3(x1, y, -y1), V3(x0, y, -y0)], V3((y1 - y0) * sg, 0, (x1 - x0) * sg)), true);
  }
  P.ground.push({ q, y });
}
const groundAt = (P, x, y) => P.ground.reduce((h, s) => (s.y > h && inPoly([x, y], s.q) ? s.y : h), 0);
// pintura plana (líneas, bahías) sobre el suelo del punto
function paintQuad(P, mat, w, d, m, y) { P.equip.addRaw(mat, new THREE.PlaneGeometry(w, d).rotateX(-Math.PI / 2).translate(0, y, 0).applyMatrix4(m)); }

// ---------- elementos del entorno
function nearestWall(V, c, maxD = 1.6) {
  let best = null;
  for (const vi of V) {
    if (!vi.f || vi.open) continue;
    const l = c.clone().applyMatrix4(vi.f.inv);
    for (const [k, S] of Object.entries(vi.f.sides)) {
      const nl = S.n, dist = l.x * nl.x + l.z * nl.z - S.half, al = l.x * S.t.x + l.z * S.t.z;
      if (dist > -0.3 && dist < maxD && Math.abs(al) < S.len / 2 && (!best || dist < best.dist)) best = { vi, s: k, dist, n: S.n.clone().transformDirection(vi.f.m) };
    }
  }
  return best;
}
function element(b, e, P, detail, V) {
  const at = (o = e) => (o.centro ? planToThree(o.centro) : V3(0, 0, 0));
  switch (e.tipo) {
    case 'cerramiento': {
      const pts = e.poligono || e.linea; if (!pts || pts.length < 2) return;
      const closed = !!e.poligono && !e.abierto, h = e.altura ?? 2, mat = e.material || 'muro';
      const col = e.color || (mat === 'muro' ? '#e6e2d8' : '#3a3f44');
      const n = closed ? pts.length : pts.length - 1;
      for (let i = 0; i < n; i++) {
        const [xa, ya] = pts[i], [xb, yb] = pts[(i + 1) % pts.length];
        if (Math.hypot(xb - xa, yb - ya) < 0.05) continue;
        let spans = [[0, 1]];
        for (const vi of V) {
          if (!vi.f || vi.open) continue;
          const tt = clipSeg(V3(xa, 0, -ya).applyMatrix4(vi.f.inv), V3(xb, 0, -yb).applyMatrix4(vi.f.inv), vi.f.L / 2 + 0.3, vi.f.A / 2 + 0.3);
          if (tt) spans = subtract(spans, tt);
        }
        for (const vi of V) if (vi.f && vi.open) {
          const la = V3(xa, 0, -ya).applyMatrix4(vi.f.inv), lb = V3(xb, 0, -yb).applyMatrix4(vi.f.inv), hc = (vi.v.columna ?? 0.25) / 2 + 0.15;
          for (const [cx, cz] of columnPts(vi.v, vi.f, V)) { const tt = clipSeg(la.clone().sub(V3(cx, 0, cz)), lb.clone().sub(V3(cx, 0, cz)), hc, hc); if (tt) spans = subtract(spans, tt); }
        }
        // volúmenes poligonales: fuera los tramos a menos de 30 cm de su contorno
        const segLen = Math.hypot(xb - xa, yb - ya), nS = Math.max(2, Math.ceil(segLen / 0.05));
        for (const vi of V) if (vi.v.poligono) {
          const q = vi.v.poligono, near = (p) => inPoly(p, q) || q.some(([x0, y0], k) => { const [x1, y1] = q[(k + 1) % q.length], dx = x1 - x0, dy = y1 - y0, l2 = dx * dx + dy * dy || 1, tt = Math.max(0, Math.min(1, ((p[0] - x0) * dx + (p[1] - y0) * dy) / l2)); return Math.hypot(x0 + tt * dx - p[0], y0 + tt * dy - p[1]) < 0.3; });
          let run0 = null;
          for (let k = 0; k <= nS; k++) { const tt = k / nS, b0 = near([xa + (xb - xa) * tt, ya + (yb - ya) * tt]); if (b0 && run0 === null) run0 = Math.max(0, tt - 0.5 / nS); if ((!b0 || k === nS) && run0 !== null) { spans = subtract(spans, [run0, b0 ? 1 : Math.min(1, tt)]); run0 = null; } }
        }
        for (const [t0, t1] of spans) {
          const x0 = xa + (xb - xa) * t0, y0 = ya + (yb - ya) * t0, x1 = xa + (xb - xa) * t1, y1 = ya + (yb - ya) * t1, len = Math.hypot(x1 - x0, y1 - y0); if (len < 0.1) continue;
          const m = new THREE.Matrix4().compose(V3((x0 + x1) / 2, 0, -(y0 + y1) / 2), new THREE.Quaternion().setFromAxisAngle(UP, Math.atan2(y1 - y0, x1 - x0)), V3(1, 1, 1));
          const add = (k, g) => P.env.addRaw(k, g.applyMatrix4(m));
          if (mat === 'muro') {
            // muro con columnetas cada ~3 m y remate
            const wk = tint('pintura', col);
            add(wk, boxG(len, h, 0.15)); add(tint('pintura', shade(col, 0.9)), boxG(len + 0.07, 0.08, 0.23, 0, h, 0));
            if (detail && h > 1) { const k = Math.max(1, Math.round(len / 3)); for (let j = 0; j <= k; j++) add(wk, boxG(0.25, h, 0.25, -len / 2 + (j * len) / k, 0, 0)); }
            continue; // siguiente tramo
          }
          const mk = tint('metal_pintado', col);
          const k = Math.max(1, Math.round(len / 2.5));
          const eA = t0 === 0 ? 0.1 : 0, eB = t1 === 1 ? 0.1 : 0;
        add(tint('pintura', '#c8c5bc'), boxG(len + eA + eB, mat === 'malla' ? 0.25 : 0.4, 0.2, (eB - eA) / 2));
          if (mat === 'malla') {
            // malla eslabonada: tubos cada 2,5 m con tapa, pasamanos y paño con transparencia
            for (let j = 0; j <= k; j++) { const x = -len / 2 + (j * len) / k; add(mk, new THREE.CylinderGeometry(0.03, 0.03, h, detail ? 8 : 5).translate(x, h / 2, 0)); if (detail) add(mk, new THREE.SphereGeometry(0.04, 8, 4).translate(x, h, 0)); }
            add(mk, new THREE.CylinderGeometry(0.02, 0.02, len, detail ? 6 : 4).rotateZ(Math.PI / 2).translate(0, h - 0.05, 0));
            const g = new THREE.PlaneGeometry(len, h - 0.3).translate(0, 0.25 + (h - 0.3) / 2, 0), uv = g.attributes.uv, p = g.attributes.position;
            for (let q = 0; q < uv.count; q++) uv.setXY(q, p.getX(q) / 0.2, p.getY(q) / 0.2);
            P.env.addRaw(tint('malla', col), g.applyMatrix4(m), true);
            continue;
          }
          // reja: sobrecimiento, parales cada 2,5 m con tapa, pasamanos arriba y abajo y barrotes cada 12 cm
          for (let j = 0; j <= k; j++) { const x = -len / 2 + (j * len) / k; add(mk, boxG(0.08, h, 0.08, x, 0, 0)); if (detail) add(mk, boxG(0.11, 0.03, 0.11, x, h, 0)); }
          add(mk, boxG(len, 0.05, 0.05, 0, h - 0.12, 0)); add(mk, boxG(len, 0.04, 0.04, 0, 0.5, 0));
          if (detail) { const nb = Math.round(len / 0.12); for (let j = 0; j < nb; j++) add(mk, boxG(0.018, h - 0.5, 0.018, -len / 2 + (j + 0.5) * (len / nb), 0.4, 0)); }
          else add(mk, boxG(len, h - 0.55, 0.01, 0, 0.45, 0));
          }
      }
      return;
    }
    case 'tanque_elevado': {
      const c = at(), H = e.altura ?? 12, d = e.diametro ?? 4, th = Math.min(d * 0.9, H * 0.35), r0 = Math.max(0.5, d * 0.18);
      P.env.add('pintura#ecebe6', new THREE.CylinderGeometry(r0, Math.max(0.6, d * 0.22), H - th, 16), [c.x, (H - th) / 2, c.z]);
      P.env.add('pintura_satin#d8dcdf', new THREE.CylinderGeometry(d / 2, d / 2.6, th, 28), [c.x, H - th / 2, c.z]);
      P.env.add('pintura_satin#d8dcdf', new THREE.ConeGeometry(d / 2 + 0.05, d * 0.18, 28), [c.x, H + d * 0.09, c.z]);
      if (detail) {
        P.env.add('pintura#c9c8c2', new THREE.CylinderGeometry(d / 2.6 + 0.12, d / 2.6 + 0.12, 0.25, 28), [c.x, H - th - 0.1, c.z]);
        P.env.add('pintura#c9c8c2', new THREE.CylinderGeometry(r0 + 0.35, r0 + 0.45, 0.4, 16), [c.x, 0.2, c.z]);
      }
      return;
    }
    case 'arbol': {
      const c = at(), H = e.altura ?? 8, cp = e.copa ?? H * 0.7;
      P.trees.push({ c, H, cp }); return;
    }
    case 'cancha': {
      if (!e.centro) { const pts = rectOrPoly(e); if (pts) slab(P, tint('pintura', e.color, '#3f7f6a'), pts, 'cancha'); return; }
      const f = frame({ ...e, largo: e.largo ?? 28, ancho: e.ancho ?? 15 }), pts = rectOrPoly({ ...e, largo: f.L, ancho: f.A });
      slab(P, e.superficie === 'concreto' ? 'piso' : tint('pintura', e.color, '#3f7f6a'), pts, 'cancha');
      // demarcación (pintura a media altura entre niveles)
      const y = NIVEL.cancha + PINTURA;
      for (const [w, d, x, z] of [[f.L, 0.08, 0, f.A / 2 - 0.04], [f.L, 0.08, 0, -f.A / 2 + 0.04], [0.08, f.A - 0.16, f.L / 2 - 0.04, 0], [0.08, f.A - 0.16, -f.L / 2 + 0.04, 0], [0.08, f.A - 0.16, 0, 0]]) P.env.addRaw('pintura#f5f5f0', new THREE.PlaneGeometry(w, d).rotateX(-Math.PI / 2).translate(x, y, z).applyMatrix4(f.m));
      P.env.addRaw('pintura#f5f5f0', new THREE.RingGeometry(1.75, 1.83, 40).rotateX(-Math.PI / 2).translate(0, y, 0).applyMatrix4(f.m));
      if (e.cubierta) {
        const h = e.altura ?? 8, nc = Math.max(2, Math.round(f.L / 6) + 1), fl = f.A * 0.12, Dv = f.A + 1;
        const Rr = ((Dv / 2) ** 2 + fl ** 2) / (2 * fl), yc = h + fl - Rr;
        for (let i = 0; i < nc; i++) {
          const x = -f.L / 2 + (i * f.L) / (nc - 1);
          for (const sz of [1, -1]) P.env.addRaw('metal_pintado#2b2d30', boxG(0.3, h, 0.3, x, 0, sz * (f.A / 2 + 0.5)).applyMatrix4(f.m));
          // cercha en arco bajo la bóveda
          if (detail) { const arcPts = []; for (let k = 0; k <= 12; k++) { const z = -Dv / 2 + (Dv * k) / 12; arcPts.push(V3(x, yc + Math.sqrt(Math.max(0, Rr * Rr - z * z)) - 0.35, z).applyMatrix4(f.m)); } pipe(P.env, 'metal_pintado#2b2d30', arcPts, 0.09, false, 6); }
        }
        const rp = new Part(), wp = new Part();
        vault(f.L + 1, f.A + 1, h, { flecha: fl, voladizo: 0.5 }, { roof: rp, walls: wp, wk: 'metal_pintado#2b2d30', rk: roofMat(b, { material: e.material_cubierta || 'zinc', color: e.color_cubierta }), caps: false, trim: false, eaves: [] });
        mergeInto(P.roofKeep, rp, f.m);
      }
      return;
    }
    case 'parqueadero': case 'patio': case 'anden': case 'zona_verde': case 'plaza': {
      const pts = rectOrPoly(e); if (!pts) return;
      slab(P, { parqueadero: 'asfalto', zona_verde: 'pasto' }[e.tipo] || 'piso', pts, e.tipo);
      return;
    }
    case 'cubierta_ligera': {
      // estructura metálica: parales hasta la cubierta (más altos del lado alto), vigas de borde y correas
      const f = frame({ ...e, largo: e.largo ?? 6, ancho: e.ancho ?? 4 }), h = e.altura ?? 3, tp = Math.tan(6 * D2R);
      const yAt = (z) => h + (f.A / 2 - z) * tp;
      for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
        const z = sz * (f.A / 2 - 0.1);
        P.env.addRaw('metal_pintado#2b2d30', boxG(0.12, yAt(z) - 0.26, 0.12, sx * (f.L / 2 - 0.1), 0, z).applyMatrix4(f.m));
        if (detail) P.env.addRaw('pintura#ecebe6', boxG(0.3, 0.2, 0.3, sx * (f.L / 2 - 0.1), 0, z).applyMatrix4(f.m));
      }
      for (const sz of [1, -1]) { const z = sz * (f.A / 2 - 0.1); P.env.addRaw('metal_pintado#2b2d30', beamG(V3(-f.L / 2, yAt(z) - 0.18, z), V3(f.L / 2, yAt(z) - 0.18, z), 0.1, 0.16).applyMatrix4(f.m)); }
      // cabios en la dirección de la pendiente
      if (detail) { const nr = Math.max(2, Math.round(f.L / 1.5) + 1); for (let i = 0; i < nr; i++) { const x = -f.L / 2 + 0.1 + (i * (f.L - 0.2)) / (nr - 1), za = -f.A / 2 - 0.2, zb = f.A / 2 + 0.2; P.env.addRaw('metal_pintado#2b2d30', beamG(V3(x, yAt(za) - 0.06, za), V3(x, yAt(zb) - 0.06, zb), 0.05, 0.08).applyMatrix4(f.m)); } }
      const rp = new Part(), wp = new Part();
      shed(f.L, f.A, h, { pendiente: 6, voladizo: 0.3 }, { roof: rp, walls: wp, wk: 'metal_pintado#2b2d30', rk: roofMat(b, { material: e.material || 'zinc', color: e.color }), caps: false, trim: false, eaves: [] });
      mergeInto(P.roofKeep, rp, f.m);
      return;
    }
    case 'asta': {
      const c = at(), h = e.altura ?? 8;
      P.env.add('metal_pintado#c4c8cb', new THREE.CylinderGeometry(0.04, 0.06, h, 10), [c.x, h / 2, c.z]);
      if (detail) { P.env.add('pintura#ecebe6', new THREE.CylinderGeometry(0.25, 0.3, 0.3, 12), [c.x, 0.15, c.z]); P.env.add('metal_pintado#c4c8cb', new THREE.SphereGeometry(0.07, 10, 6), [c.x, h + 0.05, c.z]); }
      [['bandera_am', 0.5, 0], ['bandera_az', 0.25, -0.5], ['bandera_ro', 0.25, -0.75]].forEach(([m, hh, dy]) => P.env.add(m, new THREE.PlaneGeometry(1.5, hh), [c.x + 0.78, h - 0.25 + dy - hh / 2 + 0.25, c.z]));
      return;
    }
    case 'poste': {
      // poste de concreto con cruceta, aisladores y luminaria (y caja del medidor si la especificación la menciona)
      const c = at(), h = e.altura ?? 9;
      P.env.add('pintura#ecebe6', new THREE.CylinderGeometry(0.1, 0.16, h, detail ? 10 : 6), [c.x, h / 2, c.z]);
      P.env.addRaw('metal_pintado#2b2d30', boxG(1.6, 0.1, 0.1, c.x, h - 0.6, c.z));
      if (detail) {
        for (const x of [-0.7, 0, 0.7]) P.env.add('pintura_satin#d8dcdf', new THREE.CylinderGeometry(0.05, 0.07, 0.18, 8), [c.x + x, h - 0.41, c.z]);
        const a = V3(c.x, h - 1.4, c.z), bb = V3(c.x + 0.25, h - 1.0, c.z - 1.3);
        pipe(P.env, 'metal_pintado#c4c8cb', [a, V3(c.x, h - 1.1, c.z - 0.3), bb], 0.035, true, 6);
        P.env.addRaw('pintura_satin#eceeee', beamG(bb.clone().add(V3(0, -0.04, 0.1)), bb.clone().add(V3(0, -0.08, -0.5)), 0.28, 0.12));
        if (/medidor/i.test(e.nombre || '')) P.env.addRaw('pintura_satin#f2f3f3', boxG(0.32, 0.45, 0.2, c.x, 1.5, c.z + 0.26));
      }
      P.poles.push({ c, h, e });
      return;
    }
    case 'torre': case 'antena': {
      const c = at(), h = e.altura ?? 24, w0 = e.tipo === 'torre' ? Math.max(1.2, h * 0.08) : 0.4, w1 = 0.35;
      const leg = (sx, sz, y) => { const w = w0 + (w1 - w0) * (y / h); return V3(c.x + sx * w / 2, y, c.z + sz * w / 2); };
      for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) P.env.addRaw('metal_pintado#c4c8cb', tubeG(leg(sx, sz, 0), leg(sx, sz, h), 0.045, 6));
      if (e.tipo === 'torre') {
        const corners = [[1, 1], [1, -1], [-1, -1], [-1, 1]];
        for (let y = 3; y < h; y += 3) for (let k = 0; k < 4; k++) {
          const [ax, az] = corners[k], [bx, bz] = corners[(k + 1) % 4];
          P.env.addRaw('metal_pintado#c4c8cb', tubeG(leg(ax, az, y), leg(bx, bz, y), 0.025, 4));
          if (detail) { P.env.addRaw('metal_pintado#c4c8cb', tubeG(leg(ax, az, y - 3), leg(bx, bz, y), 0.018, 4)); P.env.addRaw('metal_pintado#c4c8cb', tubeG(leg(bx, bz, y - 3), leg(ax, az, y), 0.018, 4)); }
        }
      }
      return;
    }
    case 'pozo': {
      // pozo profundo con bomba sumergible ("lapicero"): losa, revestimiento de acero (8" por defecto), cabezal con brida,
      // descarga con válvula de cheque y de compuerta, manómetro, conduit eléctrico y tablero de arranque con variador
      // bajo una cubierta pequeña; "rumbo" orienta la descarga
      const c = at(), D = ((e.diametro_pulgadas ?? 8) * 0.0254) + 0.03, ry = THREE.MathUtils.degToRad(e.rumbo ?? 0);
      const m = new THREE.Matrix4().compose(V3(c.x, 0, c.z), new THREE.Quaternion().setFromAxisAngle(UP, -ry), V3(1, 1, 1));
      const add = (k, g, uv = false) => P.env.addRaw(k, g.applyMatrix4(m), uv);
      add('piso', boxUV(2.2, 0.25, 2.2, 0, 0.03, 0), true);
      add('metal_pintado#3d4a57', new THREE.CylinderGeometry(D / 2, D / 2, 0.7, detail ? 20 : 8).translate(0, 0.28 + 0.35, 0));
      add('metal_pintado#2f6db3', new THREE.CylinderGeometry(D / 2 + 0.07, D / 2 + 0.07, 0.06, detail ? 20 : 8).translate(0, 1.0, 0));
      // descarga horizontal hacia "adelante" (+z local)
      const y = 0.86, d0 = V3(0, y, 0), d1 = V3(0, y, 1.9);
      add('metal_pintado#2f6db3', tubeG(V3(0, 1.0, 0), d0, 0.07, 10));
      add('metal_pintado#2f6db3', tubeG(d0, d1, 0.07, 10));
      add('metal_pintado#2f6db3', tubeG(d1, V3(0, 0.28, 1.9), 0.07, 10));
      if (detail) {
        add('metal_pintado#20262c', boxG(0.24, 0.22, 0.3, 0, y - 0.11, 0.7));          // cheque
        add('metal_pintado#20262c', boxG(0.22, 0.26, 0.22, 0, y - 0.13, 1.2));         // compuerta
        add('metal_pintado#c4c8cb', new THREE.CylinderGeometry(0.02, 0.02, 0.5, 8).translate(0, y + 0.26 + 0.05, 1.2));
        add('pintura_satin#f2f3f3', new THREE.CylinderGeometry(0.07, 0.07, 0.04, 16).rotateX(Math.PI / 2).translate(0, y + 0.3, 0.45));
        add('metal_pintado#c4c8cb', tubeG(V3(0, y + 0.07, 0.45), V3(0, y + 0.26, 0.45), 0.012, 6));
      }
      // tablero de arranque y variador sobre soporte, con cubierta
      const tx = 1.6;
      add('metal_pintado#2b2d30', boxG(0.08, 1.9, 0.08, tx - 0.3, 0.28, -0.3)); add('metal_pintado#2b2d30', boxG(0.08, 1.9, 0.08, tx + 0.3, 0.28, -0.3));
      add('pintura_satin#e9ebec', boxG(0.7, 0.9, 0.3, tx, 1.0, -0.3));
      if (detail) { add('pintura_satin#2a2f38', boxG(0.2, 0.14, 0.02, tx - 0.15, 1.55, -0.14)); add('metal_pintado#eb6834', boxG(0.1, 0.1, 0.02, tx + 0.18, 1.6, -0.14)); }
      add('metal_pintado#c4c8cb', boxG(1.3, 0.05, 1.0, tx, 2.3, -0.3));
      add('metal_pintado#f08a00', tubeG(V3(tx - 0.25, 1.0, -0.3), V3(0.15, 0.3, -0.15), 0.025, 6));   // conduit de fuerza a la bomba
      return;
    }
    case 'planta_electrica': {
      const c = at(), l = e.largo ?? 3, hh = e.altura ?? 1.9, w = e.ancho ?? 1.5;
      P.env.addRaw('piso', boxUV(l + 0.6, 0.15, w + 0.6, c.x, 0, c.z), true);
      P.env.addRaw('metal_pintado#eb6834', boxG(l, hh, w, c.x, 0.15, c.z));
      if (detail) {
        P.env.addRaw('rejilla', boxG(0.02, hh * 0.7, w * 0.8, c.x + l / 2 + 0.02, 0.15 + hh * 0.15, c.z), true);
        P.env.addRaw('pintura_satin#2a2f38', boxG(0.4, 0.5, 0.03, c.x - l / 4, 0.15 + hh * 0.45, c.z + w / 2 + 0.02));
        P.env.add('metal_pintado#2b2d30', new THREE.CylinderGeometry(0.06, 0.06, 0.6, 8), [c.x - l / 3, 0.15 + hh + 0.3, c.z]);
      }
      return;
    }
    case 'aire_acondicionado': {
      // condensadora con ventilador, rejilla lateral y ménsulas; de espaldas al muro más cercano
      const c = at(), y = e.altura ?? 0.3, nw = nearestWall(V, c);
      const ry = nw ? Math.atan2(nw.n.x, nw.n.z) : 0;
      const back = nw ? Math.max(0, 0.22 - nw.dist) : 0;
      const m = new THREE.Matrix4().compose(V3(c.x, 0, c.z).addScaledVector(nw ? nw.n : V3(0, 0, 1), back), new THREE.Quaternion().setFromAxisAngle(UP, ry), V3(1, 1, 1));
      const add = (k, g, uv = false) => P.env.addRaw(k, g.applyMatrix4(m), uv);
      add('pintura_satin#eceeee', boxG(0.9, 0.68, 0.34, 0, y, 0));
      add('pintura#17191b', new THREE.CylinderGeometry(0.25, 0.25, 0.02, detail ? 24 : 10).rotateX(Math.PI / 2).translate(-0.12, y + 0.34, 0.18));
      if (detail) {
        add('metal_pintado#c4c8cb', new THREE.TorusGeometry(0.25, 0.012, 4, 24).translate(-0.12, y + 0.34, 0.195));
        for (const a of [0, Math.PI / 2]) add('metal_pintado#c4c8cb', new THREE.BoxGeometry(0.5, 0.012, 0.012).rotateZ(a).translate(-0.12, y + 0.34, 0.197));
        add('rejilla', boxG(0.02, 0.55, 0.28, 0.46, y + 0.06, 0), true);
        add('pintura_satin#eceeee', boxG(0.92, 0.03, 0.36, 0, y + 0.68, 0));
        const rc = new THREE.Raycaster(V3(c.x, y + 0.05, c.z), V3(0, -1, 0), 0, 1.2), hit = y > 0.5 ? rc.intersectObjects(P.roofRay || [], false)[0] : null;
        if (hit) for (const x of [-0.35, 0.35]) add('metal_pintado#2b2d30', boxG(0.06, y - hit.point.y + 0.03, 0.3, x, hit.point.y - 0.03, 0));
        else if (y > 0.5) for (const x of [-0.35, 0.35]) { add('metal_pintado#2b2d30', boxG(0.04, 0.04, 0.46, x, y - 0.04, -0.06)); add('metal_pintado#2b2d30', beamG(V3(x, y - 0.04, 0.12), V3(x, y - 0.4, -0.2), 0.04, 0.03, V3(0, 0, 1))); }
        else for (const x of [-0.35, 0.35]) add('metal_pintado#2b2d30', boxG(0.06, Math.max(0.02, y), 0.3, x, 0, 0));
        for (const [x, r] of [[0.32, 0.012], [0.38, 0.008]]) add('metal_pintado#b87333', tubeG(V3(x, y + 0.12, -0.17), V3(x, y + 0.12, -0.17 - back - 0.05), r, 6));
      }
      return;
    }
    default: warn.push(`elemento desconocido: ${e.tipo}`);
  }
}
// árbol unitario (alto 1, copa de diámetro 1; se escala por instancia): tronco con dos ramas y copa de varios
// lóbulos en tres verdes (color por vértice: tronco y copa son solo dos llamadas de dibujo)
function treeMesh(b, detail) {
  const p = new Part();
  p.add('tronco', new THREE.CylinderGeometry(0.03, 0.05, 0.56, detail ? 8 : 5), [0, 0.28, 0]);
  if (detail) for (const [x, z] of [[0.13, 0.05], [-0.1, -0.09]]) p.addRaw('tronco', tubeG(V3(0, 0.4, 0), V3(x, 0.62, z), 0.018, 5));
  const lobes = detail
    ? [[0, 0.7, 0, 0.42, '#4b7735'], [0.2, 0.66, 0.12, 0.27, '#3f6a31'], [-0.2, 0.67, 0.08, 0.26, '#567f3a'], [0.04, 0.68, -0.22, 0.26, '#3c6530'], [-0.08, 0.86, 0.1, 0.25, '#62903f'], [0.12, 0.84, -0.06, 0.24, '#5a8a3c'], [-0.18, 0.78, -0.14, 0.22, '#477234']]
    : [[0, 0.7, 0, 0.45, '#4b7735'], [0.08, 0.84, 0.05, 0.3, '#5a8a3c']];
  lobes.forEach(([x, y, z, r, c], i) => p.add(`copa${c}`, new THREE.IcosahedronGeometry(r, detail ? 1 : 0).rotateY(i * 0.73).rotateX(i * 0.41).scale(1, 0.72, 1), [x, y, z]));
  return b.partMesh('arbol', p);
}

// ---------- elementos de obra nueva (segunda pasada de build: ya se conocen los suelos y las cubiertas)
const NUEVOS = new Set(['marquesina_acceso', 'bahia_ambulancias', 'puente', 'equipo_cubierta', 'jardinera', 'banca', 'luminaria', 'letrero_institucional']);
const rayDown = new THREE.Raycaster();
// altura de la cubierta más alta bajo un punto (null si no hay cubierta)
function roofAt(P, x, z) { rayDown.set(V3(x, 300, z), V3(0, -1, 0)); rayDown.far = 600; const h = rayDown.intersectObjects(P.roofRay || [], false)[0]; return h ? h.point.y : null; }
// lado de un rectángulo más alejado de los volúmenes cerrados: el frente abierto de marquesinas y bahías
function farSide(f, V) {
  let best = '+Z', bd = -Infinity;
  for (const [k, S] of Object.entries(f.sides)) {
    const p = S.n.clone().multiplyScalar(S.half + 0.5).applyMatrix4(f.m);
    let dmin = Infinity;
    for (const vi of V) { if (!vi.f || vi.open) continue; const l = p.clone().applyMatrix4(vi.f.inv); dmin = Math.min(dmin, Math.hypot(Math.max(0, Math.abs(l.x) - vi.f.L / 2), Math.max(0, Math.abs(l.z) - vi.f.A / 2))); }
    if (dmin > bd) { bd = dmin; best = k; }
  }
  return best;
}
// recorta un polígono plano [[x, z]] a la franja xa ≤ x ≤ xb
function clipX(poly, xa, xb) {
  const cut = (pts, keep, x0) => {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i], q = pts[(i + 1) % pts.length], ip = keep(p[0]), iq = keep(q[0]);
      if (ip) out.push(p);
      if (ip !== iq) { const t = (x0 - p[0]) / (q[0] - p[0]); out.push([x0, p[1] + t * (q[1] - p[1])]); }
    }
    return out;
  };
  return cut(cut(poly, (x) => x >= xa, xa), (x) => x <= xb, xb);
}
// rotación en planta para que el eje local +z mire hacia `rumbo` (grados desde el norte)
const facing = (rumbo) => new THREE.Quaternion().setFromAxisAngle(UP, Math.PI - (rumbo ?? 180) * D2R);
function elementoNuevo(e, P, detail, V) {
  if (e.tipo !== 'puente' && !e.centro && !e.centros && !(e.tipo === 'letrero_institucional' && e.volumen)) { warn.push(`${e.tipo} sin centro`); return; }
  switch (e.tipo) {
    case 'marquesina_acceso': marquesina(e, P, V, detail, false); return;
    case 'bahia_ambulancias': bahia(e, P, V, detail); return;
    case 'puente': puente(e, P, V, detail); return;
    case 'equipo_cubierta': equipo(e, P, detail); return;
    case 'jardinera': jardinera(e, P, detail); return;
    case 'banca': bancas(e, P, detail); return;
    case 'luminaria': luminarias(e, P, detail); return;
    case 'letrero_institucional': letreroInst(e, P, V, detail);
  }
}
// Marquesina de acceso: losa delgada (borde de panel, cielo raso claro 2,5 cm abajo con luminarias empotradas) sobre columnas
// de acero esbeltas en el frente abierto, o en voladizo con tensores al muro. El frente es `frente` o el lado más lejano de los
// volúmenes. En la bahía de ambulancias (amb) es más alta, con columnas gruesas y franjas de protección.
function marquesina(e, P, V, detail, amb) {
  const f = frame({ ...e, largo: e.largo ?? (amb ? 12 : 10), ancho: e.ancho ?? (amb ? 8 : 4.5), base: 0 }), L = f.L, A = f.A;
  const g0 = groundAt(P, e.centro[0], e.centro[1]), h = e.altura ?? (amb ? 4.6 : 3.8), esp = e.espesor ?? (amb ? 0.45 : 0.3);
  const fk = tint('metal_pintado', e.color, '#eef0f0'), ck = tint('pintura', e.color_cielo, '#f3f2ee'), sk = tint('metal_pintado', e.color_columnas, '#3a3f44');
  const add = (k, g) => g && P.env.addRaw(k, g.applyMatrix4(f.m));
  add(fk, boxG(L, esp, A, 0, h, 0));
  const i0 = 0.05, yc = h - 0.025;
  add(ck, polyGeo([V3(-L / 2 + i0, yc, -A / 2 + i0), V3(L / 2 - i0, yc, -A / 2 + i0), V3(L / 2 - i0, yc, A / 2 - i0), V3(-L / 2 + i0, yc, A / 2 - i0)], V3(0, -1, 0)));
  if (detail) {
    const nx = Math.max(1, Math.round(L / 2.2)), nz = Math.max(1, Math.round(A / 2.2));
    for (let a = 0; a < nx; a++) for (let c = 0; c < nz; c++) add('luz', new THREE.CylinderGeometry(0.11, 0.11, 0.02, 12).translate(-L / 2 + (a + 0.5) * (L / nx), yc - 0.01, -A / 2 + (c + 0.5) * (A / nz)));
  }
  const fs = e.frente ? sideFor(f, e.frente) : farSide(f, V), S = f.sides[fs];
  if (e.apoyo === 'voladizo') {
    // tensores desde el borde frontal hasta el muro, 2,4 m más arriba, con placas de anclaje
    for (const x of [-S.len / 3, S.len / 3]) {
      const a = S.n.clone().multiplyScalar(S.half - 0.35).addScaledVector(S.t, x).setY(h + esp), c = S.n.clone().multiplyScalar(-S.half + 0.04).addScaledVector(S.t, x).setY(h + esp + 2.4);
      add(sk, tubeG(a, c, 0.025, 8));
      add(sk, beamG(c.clone().addScaledVector(S.n, -0.06), c.clone().addScaledVector(S.n, 0.02), 0.25, 0.3));
      if (detail) add(sk, beamG(a.clone().setY(h + esp - 0.01), a.clone().setY(h + esp + 0.12), 0.1, 0.12, S.n));
    }
    return;
  }
  const r = (e.diametro_columnas ?? (amb ? 0.32 : 0.2)) / 2, sep = e.sep_columnas ?? (amb ? 6 : 5), inset = amb ? 0.6 : 0.45, seg = detail ? 16 : 8;
  const n = Math.max(2, Math.ceil((S.len - 2 * inset) / sep) + 1);
  for (let k = 0; k < n; k++) {
    const p = S.n.clone().multiplyScalar(S.half - inset).addScaledVector(S.t, -S.len / 2 + inset + (k * (S.len - 2 * inset)) / (n - 1));
    add(sk, new THREE.CylinderGeometry(r, r, h - g0 + 0.02, seg).translate(p.x, (g0 - 0.02 + h) / 2, p.z));
    if (!detail) continue;
    add(sk, new THREE.CylinderGeometry(r + 0.07, r + 0.09, 0.04, seg).translate(p.x, g0 + 0.02, p.z)); // cubreplaca
    if (amb) for (const y of [0.15, 0.55]) add('advertencia', new THREE.CylinderGeometry(r + 0.012, r + 0.012, 0.25, seg).translate(p.x, g0 + y + 0.125, p.z));
  }
}
// Bahía de ambulancias: marquesina alta (4,6 m libres, salvo `cubierta: false`), recuadro amarillo, franja achurada contra el
// muro (descargue), rótulo en el piso que se lee llegando por el frente y bolardos contra el muro que dejan libres las puertas.
function bahia(e, P, V, detail) {
  const f = frame({ ...e, largo: e.largo ?? 12, ancho: e.ancho ?? 8, base: 0 });
  const fs = e.frente ? sideFor(f, e.frente) : farSide(f, V), S = f.sides[fs];
  if (e.cubierta !== false) marquesina({ ...e, largo: f.L, ancho: f.A, frente: fs }, P, V, detail, true);
  const g0 = groundAt(P, e.centro[0], e.centro[1]), y = g0 + PINTURA, yk = tint('pintura', e.color_demarcacion, '#f2c200');
  // marco de la bahía: x a lo largo del frente, z del muro (−) al frente (+)
  const bm = f.m.clone().multiply(new THREE.Matrix4().makeBasis(S.t, UP, S.n));
  const gq = (x0, x1, z0, z1) => P.env.addRaw(yk, polyGeo([V3(x0, y, z0), V3(x1, y, z0), V3(x1, y, z1), V3(x0, y, z1)], UP).applyMatrix4(bm));
  const hx = S.len / 2 - 0.3, hz = S.half - 0.3, lw = 0.15;
  gq(-hx, hx, hz - lw, hz); gq(-hx, hx, -hz, -hz + lw); gq(-hx, -hx + lw, -hz + lw, hz - lw); gq(hx - lw, hx, -hz + lw, hz - lw);
  const z0 = -hz + lw + 0.1, z1 = z0 + 1.2;
  for (let c = -hx - 1.2; c < hx; c += 0.6) {
    const poly = clipX([[c, z0], [c + 0.15, z0], [c + 1.35, z1], [c + 1.2, z1]], -hx + lw + 0.05, hx - lw - 0.05);
    if (poly.length >= 3) P.env.addRaw(yk, polyGeo(poly.map(([a, z]) => V3(a, y, z)), UP).applyMatrix4(bm));
  }
  gq(-hx + lw, hx - lw, z1 + 0.05, z1 + 0.17);
  const txt = e.rotulo ?? 'AMBULANCIAS';
  if (txt) {
    const size = Math.min(0.7, (2 * hx * 0.7) / Math.max(1, txt.length * 0.85)), tg = textGeo(txt, size, 0.003, true);
    if (tg) P.env.addRaw('pintura#f5f5f0', tg.applyMatrix4(bm.clone().multiply(new THREE.Matrix4().makeBasis(V3(1, 0, 0), V3(0, 0, -1), UP).setPosition(0, y, (z1 + 0.17 + hz) / 2 + size * 0.36))));
  }
  // bolardos de acero con franja reflectiva contra el muro, con un claro frente a cada puerta cercana (solo LOD0)
  if (!detail) return;
  const it = inst(P, 'bolardo', 'bolardos', () => new Part()
    .add('metal_pintado#9ea4a8', new THREE.CylinderGeometry(0.09, 0.09, 0.9, 14), [0, 0.45, 0])
    .add('metal_pintado#f4c400', new THREE.CylinderGeometry(0.105, 0.105, 0.08, 14), [0, 0.72, 0])
    .add('metal_pintado#9ea4a8', new THREE.SphereGeometry(0.09, 14, 4, 0, Math.PI * 2, 0, Math.PI / 2), [0, 0.9, 0]));
  const inv = bm.clone().invert(), gaps = [];
  for (const vi of V) for (const [s, ops] of Object.entries(vi.ops || {})) for (const o of ops) if (o.kind === 'puerta') {
    const l = wallPt(vi, s, o.along, 0, 0).applyMatrix4(inv);
    if (Math.abs(l.z + S.half) < 2.5 && Math.abs(l.x) < S.len / 2 + 1) gaps.push([l.x - o.w / 2 - 0.6, l.x + o.w / 2 + 0.6]);
  }
  for (let x = -hx; x <= hx + 1e-6; x += (2 * hx) / Math.max(1, Math.round((2 * hx) / 1.5))) {
    if (gaps.some(([a, c]) => x > a && x < c)) continue;
    it.trs.push(trsOf(bm.clone().multiply(new THREE.Matrix4().makeTranslation(x, g0 - 0.02, -S.half + 0.45))));
  }
}
// Puente cubierto y acristalado entre `desde` y `hasta` a `altura` (piso): losa, cubierta con borde, muros de vidrio con enjuta
// baja, parales cada 1,5 m y pasamanos, y estructura en cerchas laterales (por defecto) o vigas bajo la losa; columnas en `apoyos`.
// Los extremos entran 30 cm en los volúmenes que tocan; un extremo libre lleva cierre de vidrio.
function puente(e, P, V, detail) {
  if (!e.desde || !e.hasta) { warn.push('puente sin desde/hasta'); return; }
  const a = planToThree(e.desde), c = planToThree(e.hasta), y0 = e.altura ?? 4.2, w = e.ancho ?? 3, hc = e.alto ?? 3;
  const dir = c.clone().sub(a); if (dir.length() < 1) return; dir.normalize();
  const inside = (p) => V.some((vi) => { if (!vi.f || vi.open || vi.top < y0 + hc - 0.2 || vi.base > y0 + 0.1) return false; const l = p.clone().applyMatrix4(vi.f.inv); return Math.abs(l.x) < vi.f.L / 2 - 0.05 && Math.abs(l.z) < vi.f.A / 2 - 0.05; });
  const ea = inside(a.clone().addScaledVector(dir, -0.3)), ec = inside(c.clone().addScaledVector(dir, 0.3));
  const p0 = a.clone().addScaledVector(dir, ea ? -0.3 : 0), p1 = c.clone().addScaledVector(dir, ec ? 0.3 : 0), Lx = p0.distanceTo(p1), X = Lx / 2, mid = p0.clone().add(p1).multiplyScalar(0.5);
  const m = new THREE.Matrix4().compose(V3(mid.x, 0, mid.z), new THREE.Quaternion().setFromAxisAngle(UP, Math.atan2(-dir.z, dir.x)), V3(1, 1, 1));
  const sk = tint('metal_pintado', e.color, '#3a3f44'), gk = tint('vidrio_cortina', hexOK(e.color_vidrio, VIDRIO_DEF)), pk = tint('metal_pintado', e.color_perfil, PERFIL_DEF);
  const add = (k, g) => g && P.env.addRaw(k, g.applyMatrix4(m)), est = e.estructura || 'cercha';
  add('pintura#d8d7d1', boxG(Lx, 0.3, w + 0.1, 0, y0 - 0.3, 0));
  add(tint('metal_pintado', e.color_cubierta, '#e6e8e9'), boxG(Lx, 0.35, w + (est === 'viga' ? 0.3 : 0.2), 0, y0 + hc, 0)); // con cerchas, justo hasta los cordones
  for (const sz of [1, -1]) {
    const z = (sz * w) / 2, nz = V3(0, 0, sz), q = (k, ya, yb) => add(k, polyGeo([V3(-X, ya, z), V3(X, ya, z), V3(X, yb, z), V3(-X, yb, z)], nz));
    q(tint('vidrio_cortina', '#56636c'), y0, y0 + 0.9); q(gk, y0 + 0.9, y0 + hc);
    const nm = Math.max(1, Math.round(Lx / 1.5));
    for (let i = 1; i < nm; i++) add(pk, boxG(0.05, hc, 0.06, -X + (i * Lx) / nm, y0, z + sz * 0.03));
    add(pk, boxG(Lx, 0.05, 0.05, 0, y0 + 0.875, z + sz * 0.025));
  }
  for (const [free, sx] of [[!ea, -1], [!ec, 1]]) if (free) add(gk, polyGeo([V3(sx * X, y0, -w / 2), V3(sx * X, y0, w / 2), V3(sx * X, y0 + hc, w / 2), V3(sx * X, y0 + hc, -w / 2)], V3(sx, 0, 0)));
  if (est === 'viga') {
    for (const sz of [1, -1]) { const z = sz * (w / 2 - 0.35); add(sk, boxG(Lx, 0.9, 0.025, 0, y0 - 1.2, z)); add(sk, boxG(Lx, 0.03, 0.3, 0, y0 - 1.2, z)); add(sk, boxG(Lx, 0.03, 0.3, 0, y0 - 0.33, z)); }
  } else {
    // cerchas Warren a los lados: cordones, montantes y diagonales en tubo cuadrado
    const np = Math.max(2, Math.round(Lx / (hc + 0.6))), yb = y0 - 0.15, yt = y0 + hc + 0.175;
    for (const sz of [1, -1]) {
      const z = sz * (w / 2 + 0.2), px = (i) => -X + 0.1 + (i * (Lx - 0.2)) / np;
      add(sk, beamG(V3(-X, yb, z), V3(X, yb, z), 0.2, 0.2)); add(sk, beamG(V3(-X, yt, z), V3(X, yt, z), 0.2, 0.2));
      for (let i = 0; i <= np; i++) {
        add(sk, beamG(V3(px(i), yb + 0.1, z), V3(px(i), yt - 0.1, z), 0.16, 0.16, V3(0, 0, 1)));
        if (i < np) add(sk, i % 2 ? beamG(V3(px(i), yb + 0.1, z), V3(px(i + 1), yt - 0.1, z), 0.13, 0.13, V3(0, 0, 1)) : beamG(V3(px(i), yt - 0.1, z), V3(px(i + 1), yb + 0.1, z), 0.13, 0.13, V3(0, 0, 1)));
      }
    }
  }
  // columnas intermedias (sobre el eje del puente) con cabezal transversal
  const top = est === 'viga' ? y0 - 1.2 : y0 - 0.25;
  for (const pt of e.apoyos || []) {
    const x = planToThree(pt).sub(p0).dot(dir) - X, g = groundAt(P, pt[0], pt[1]);
    if (Math.abs(x) > X) continue;
    add(sk, boxG(0.4, top - 0.3 - g + 0.02, 0.4, x, g - 0.02, 0));
    add(sk, boxG(0.5, 0.3, w + 0.7, x, top - 0.3, 0));
  }
}
// Equipos de cubierta sobre su base de concreto: manejadora de aire (uma), enfriador (chiller), tanque, cuarto de máquinas del
// ascensor y pantalla de lamas que oculta los equipos (abierta arriba). Se apoyan en la cubierta más alta bajo el centro (o en `base`).
function equipo(e, P, detail) {
  const kind = e.equipo || 'uma', D = { uma: [5, 2.2, 2.1], chiller: [6, 2.3, 2.4], tanque: [2.2, 2.2, 2.6], cuarto_maquinas: [4, 3, 3], pantalla: [12, 8, 2.4] }[kind];
  if (!D) { warn.push(`equipo_cubierta desconocido: ${kind}`); return; }
  const c = planToThree(e.centro), y0 = e.base ?? roofAt(P, c.x, c.z) ?? groundAt(P, e.centro[0], e.centro[1]);
  const f = frame({ ...e, largo: e.largo ?? D[0], ancho: e.ancho ?? D[1], base: y0 }), L = f.L, A = f.A, H = e.alto ?? e.altura ?? D[2];
  const add = (k, g, uv = false) => g && P.env.addRaw(k, g.applyMatrix4(f.m), uv), wp = (pts) => pts.map((q) => q.applyMatrix4(f.m));
  const body = tint('pintura_satin', e.color, kind === 'tanque' ? '#d5d9dc' : '#e6e8e9'), steel = 'metal_pintado#4a4f54', alu = 'metal_pintado#b9bec2', pad = 'pintura#c9c8c2', seg = detail ? 20 : 10;
  if (kind === 'pantalla') {
    const col = tint('metal_pintado', e.color, '#b4b9bd'), pts = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => V3((a * L) / 2, 0, (b * A) / 2));
    for (let i = 0; i < 4; i++) {
      const p = pts[i], q = pts[(i + 1) % 4], len = p.distanceTo(q), d = q.clone().sub(p).normalize(), out = V3(d.z, 0, -d.x), mid = p.clone().add(q).multiplyScalar(0.5);
      const np = Math.max(1, Math.ceil(len / 2.5));
      for (let k = 0; k < np; k++) { const x = p.clone().addScaledVector(d, (k * len) / np); add(col, boxG(0.09, H + 0.03, 0.09, x.x, -0.03, x.z)); }
      if (detail) {
        // lamas a 45° cada ~20 cm (el borde exterior abajo) entre rieles; base (−d, arriba, afuera) para que la terna sea derecha
        const nb = Math.max(2, Math.floor((H - 0.25) / 0.2)), sm = new THREE.Matrix4().makeBasis(d.clone().negate(), UP, out);
        for (let j = 0; j < nb; j++) add(col, new THREE.BoxGeometry(len, 0.012, 0.15).rotateX(Math.PI / 4).applyMatrix4(sm.clone().setPosition(mid.clone().setY(0.15 + (j + 0.5) * ((H - 0.25) / nb)))));
        for (const yy of [0.1, H - 0.05]) add(col, beamG(p.clone().setY(yy), q.clone().setY(yy), 0.05, 0.08));
      } else for (const sg of [1, -1]) {
        const g = new THREE.PlaneGeometry(len, H - 0.1), uv = g.attributes.uv;
        for (let k = 0; k < uv.count; k++) uv.setXY(k, uv.getX(k) * len, (uv.getY(k) * (H - 0.1)) / 1.6);
        add('rejilla', g.applyMatrix4(new THREE.Matrix4().makeBasis(d.clone().multiplyScalar(-sg), UP, out.clone().multiplyScalar(sg)).setPosition(mid.clone().addScaledVector(out, sg * 0.02).setY(0.05 + (H - 0.1) / 2))), true);
      }
    }
    return;
  }
  if (kind === 'tanque') {
    const r = Math.min(L, A) / 2, s2 = detail ? 28 : 12;
    add(pad, boxG(2 * r + 0.4, 0.15, 2 * r + 0.4, 0, -0.03, 0));
    add(body, new THREE.CylinderGeometry(r, r, H, s2).translate(0, 0.12 + H / 2, 0));
    add(body, new THREE.CylinderGeometry(r * 0.3, r, 0.3, s2).translate(0, 0.12 + H + 0.15, 0));
    if (detail) {
      add(steel, new THREE.CylinderGeometry(0.28, 0.28, 0.1, 16).translate(0, 0.12 + H + 0.35, 0));
      for (const yy of [0.35, 0.68]) add(body, new THREE.CylinderGeometry(r + 0.025, r + 0.025, 0.06, s2).translate(0, 0.12 + H * yy, 0));
      for (const sx of [-0.22, 0.22]) add(alu, boxG(0.04, H + 0.3, 0.04, sx, 0.12, r + 0.18));
      for (let yy = 0.4; yy < H + 0.3; yy += 0.3) add(alu, boxG(0.44, 0.025, 0.025, 0, 0.12 + yy, r + 0.18));
      pipe(P.env, alu, wp([V3(-r * 0.6, 0.4, -r * 0.6), V3(-r - 0.3, 0.4, -r * 0.6), V3(-r - 0.3, -0.05, -r * 0.6)]), 0.05, true, 8);
    }
    return;
  }
  if (kind === 'cuarto_maquinas') {
    const cv = e.material === 'concreto_visto', wk = cv ? tint('muro_concreto', e.color, CLAD.concreto_visto) : tint('pintura', e.color, '#e9e7e1');
    add(wk, uvs(boxUV(L, H, A, 0, -0.03, 0, 1), cv ? [2.4, 1.2] : null), true);
    add('pintura#d6d4cd', boxG(L + 0.3, 0.18, A + 0.3, 0, H - 0.03, 0));
    if (detail) { add(steel, boxG(1.0, 2.12, 0.05, -L / 4, -0.02, A / 2 + 0.025)); add('rejilla', boxG(0.05, 0.6, Math.min(1.2, A - 0.6), L / 2 + 0.025, H - 1.1, 0), true); }
    return;
  }
  add(pad, boxG(L + 0.5, 0.15, A + 0.5, 0, -0.03, 0));
  add(steel, boxG(L, 0.14, A, 0, 0.12, 0));
  if (kind === 'uma') {
    add(body, boxG(L, H - 0.26, A, 0, 0.26, 0));
    for (const x of [L / 2 - 1.0, L / 2 - 2.1]) add(alu, boxG(0.8, 1.3, 0.62, x, -0.05, -A / 2 - 0.29)); // ductos que bajan a la cubierta
    if (detail) {
      const n = Math.max(2, Math.round(L / 1.1)), hb = H - 0.26;
      for (let i = 1; i < n; i++) for (const sz of [1, -1]) add(alu, boxG(0.04, hb - 0.08, 0.02, -L / 2 + (i * L) / n, 0.3, sz * (A / 2 + 0.01)));
      for (let i = 0; i < n; i++) add(steel, boxG(0.03, 0.18, 0.04, -L / 2 + ((i + 0.5) * L) / n + 0.3, 0.26 + hb * 0.5, A / 2 + 0.03));
      add('rejilla', boxG(0.03, hb * 0.6, A * 0.8, -L / 2 - 0.015, 0.26 + hb * 0.2, 0), true);
      add(body, boxG(0.45, 0.06, A * 0.86, -L / 2 - 0.2, 0.26 + hb * 0.8 + 0.02, 0));
      add('pintura#2a2e31', new THREE.CylinderGeometry(0.42, 0.42, 0.06, seg).translate(L / 2 - 0.7, H, 0));
      add(alu, new THREE.CylinderGeometry(0.47, 0.47, 0.18, seg, 1, true).translate(L / 2 - 0.7, H + 0.09, 0));
    }
    return;
  }
  // enfriador enfriado por aire: compresores abajo, serpentines con rejilla, cubierta con ventiladores y tuberías aisladas
  const hb = 1.05;
  add(body, boxG(L, hb - 0.26, A, 0, 0.26, 0));
  add('rejilla', boxG(L - 0.12, H - 0.16 - hb, A - 0.12, 0, hb, 0), true);
  add(body, boxG(L, 0.16, A, 0, H - 0.16, 0));
  if (detail) for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) add(body, boxG(0.1, H - 0.06 - hb, 0.1, sx * (L / 2 - 0.05), hb - 0.02, sz * (A / 2 - 0.05)));
  const nx = Math.max(1, Math.round(L / 1.15)), nz = A > 1.8 ? 2 : 1, rf = Math.min(L / nx, A / nz) * 0.42;
  for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
    const x = -L / 2 + ((i + 0.5) * L) / nx, z = -A / 2 + ((j + 0.5) * A) / nz;
    add(alu, new THREE.CylinderGeometry(rf, rf, 0.3, seg, 1, true).translate(x, H + 0.15, z));
    add('pintura#22262a', new THREE.CylinderGeometry(rf * 0.96, rf * 0.96, 0.02, seg).translate(x, H + 0.01, z));
    if (detail) for (const a of [0.4, 0.4 + Math.PI / 2]) add(alu, new THREE.BoxGeometry(2 * rf, 0.025, 0.025).rotateY(a).translate(x, H + 0.28, z));
  }
  if (detail) for (const z of [-0.3, 0.3]) pipe(P.env, alu, wp([V3(L / 2 - 0.3, 0.6, z), V3(L / 2 + 0.45, 0.6, z), V3(L / 2 + 0.45, -0.05, z)]), 0.09, true, 8);
}
// Jardinera elevada de concreto (o `material: "metal"`) con tierra y arbustos instanciados
function jardinera(e, P, detail) {
  const f = frame({ ...e, largo: e.largo ?? 4, ancho: e.ancho ?? 1.5, base: 0 }), L = f.L, A = f.A, H = e.alto ?? 0.45, t = e.espesor ?? 0.15;
  const g0 = groundAt(P, e.centro[0], e.centro[1]), wk = e.material === 'metal' ? tint('metal_pintado', e.color, '#4a4f54') : tint('pintura', e.color, '#d9d7d0');
  const add = (k, g) => P.env.addRaw(k, g.applyMatrix4(f.m));
  for (const sz of [1, -1]) add(wk, boxG(L, H + 0.02, t, 0, g0 - 0.02, sz * (A / 2 - t / 2)));
  for (const sx of [1, -1]) add(wk, boxG(t, H + 0.02, A - 2 * t, sx * (L / 2 - t / 2), g0 - 0.02, 0));
  const ys = g0 + H - 0.08, xi = L / 2 - t, zi = A / 2 - t;
  add('pintura#4d3d2c', polyGeo([V3(-xi, ys, -zi), V3(xi, ys, -zi), V3(xi, ys, zi), V3(-xi, ys, zi)], UP));
  if (e.plantas === false || !detail) return; // arbustos solo en LOD0
  const it = inst(P, 'arbusto', 'arbustos', () => {
    const p = new Part();
    [[0, 0.36, 0, 0.42, '#4f7a37'], [0.22, 0.3, 0.1, 0.3, '#5d8a3e'], [-0.2, 0.32, -0.08, 0.3, '#436d31']].forEach(([x, y, z, r, c], i) => p.add(`copa${c}`, new THREE.IcosahedronGeometry(r, detail ? 1 : 0).rotateY(i).scale(1, 0.8, 1), [x, y, z]));
    return p;
  });
  const sp = e.separacion_plantas ?? 0.8, nx = Math.max(1, Math.round((2 * xi) / sp)), nz = Math.max(1, Math.round((2 * zi) / sp)), id = Math.round(e.centro[0] * 13 + e.centro[1] * 7);
  for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) {
    const k = id + i * 31 + j * 17, s = 0.55 + hsh(k, 1) * 0.4;
    const pl = V3(-xi + ((i + 0.5) * 2 * xi) / nx + (hsh(k, 2) - 0.5) * 0.2, ys - 0.05, -zi + ((j + 0.5) * 2 * zi) / nz + (hsh(k, 3) - 0.5) * 0.2).applyMatrix4(f.m);
    const q = new THREE.Quaternion().setFromAxisAngle(UP, hsh(k, 4) * 6.28);
    it.trs.push({ t: pl.toArray(), r: [q.x, q.y, q.z, q.w], s: [s, s * (0.8 + hsh(k, 5) * 0.4), s] });
  }
}
// Bancas (instanciadas): dos apoyos de concreto y asiento de listones de madera; `respaldo: true` agrega espaldar.
// `rumbo`: hacia dónde mira quien se sienta. `centros` pone varias iguales.
function bancas(e, P, detail) {
  if (!detail) return; // a la distancia del LOD1 no se ven
  const L = e.largo ?? 1.8, resp = !!e.respaldo;
  const it = inst(P, `banca${L}${resp ? 'r' : ''}`, 'bancas', () => {
    const p = new Part(), wood = 'pintura#9a6b45';
    for (const x of [-L / 2 + 0.25, L / 2 - 0.25]) p.box('pintura#c9c7c0', 0.12, 0.42, 0.45, x, 0, 0);
    for (let i = 0; i < 5; i++) p.box(wood, L, 0.04, 0.085, 0, 0.42, -0.2 + i * 0.1);
    if (resp) {
      for (const x of [-L / 2 + 0.25, L / 2 - 0.25]) p.box('pintura#3a3f44', 0.05, 0.5, 0.04, x, 0.46, -0.22);
      for (let i = 0; i < 3; i++) p.box(wood, L, 0.08, 0.035, 0, 0.6 + i * 0.12, -0.25);
    }
    return p;
  });
  for (const c of e.centros || [e.centro]) { const q = facing(e.rumbo), p = planToThree(c, groundAt(P, c[0], c[1]) - 0.02); it.trs.push({ t: p.toArray(), r: [q.x, q.y, q.z, q.w] }); }
}
// Luminarias peatonales (instanciadas): poste cónico de acero con base, brazo corto y luminaria plana con difusor encendido.
// `rumbo`: hacia dónde apunta el brazo. `centros` pone varias iguales.
function luminarias(e, P, detail) {
  if (!detail) return; // a la distancia del LOD1 no se ven
  const h = e.altura ?? 4.5, col = hexOK(e.color, '#3a3f44'), mk = `metal_pintado${col}`;
  const it = inst(P, `luminaria${h}${col}`, 'luminarias', () => {
    const p = new Part();
    p.add(mk, new THREE.CylinderGeometry(0.045, 0.07, h, 10), [0, h / 2, 0]).add(mk, new THREE.CylinderGeometry(0.12, 0.13, 0.1, 10), [0, 0.05, 0]);
    p.box(mk, 0.24, 0.05, 0.05, 0.1, h - 0.06, 0).box(mk, 0.62, 0.07, 0.26, 0.5, h - 0.07, 0).box('luz', 0.56, 0.02, 0.2, 0.5, h - 0.09, 0);
    return p;
  });
  for (const c of e.centros || [e.centro]) {
    const q = new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2 - (e.rumbo ?? 0) * D2R), p = planToThree(c, groundAt(P, c[0], c[1]) - 0.02);
    it.trs.push({ t: p.toArray(), r: [q.x, q.y, q.z, q.w] });
  }
}
// Letrero institucional: letras grandes en relieve (con tildes) sobre el antepecho de un volumen, de pie sobre una canaleta,
// en su fachada (`sobre: "fachada"`, a la altura `y`) o libres (`centro`, `rumbo` hacia donde miran, `base`).
function letreroInst(e, P, V, detail) {
  if (!e.texto) return;
  const Hl = e.altura ?? 0.9, size = Hl / CAP, dep = e.profundidad ?? 0.12, key = tint('pintura_satin', e.color, '#1d4f91');
  const tg = textGeo(e.texto, size, dep, true); if (!tg) return;
  tg.computeBoundingBox();
  const tw = tg.boundingBox.max.x - tg.boundingBox.min.x;
  let m;
  if (e.volumen) {
    const vi = V.find((x) => x.v.id === e.volumen && x.f && !x.open);
    if (!vi) { warn.push(`letrero_institucional: no hay un volumen rectangular "${e.volumen}"`); return; }
    const s = sideFor(vi.f, e.lado || 'S'), S = vi.f.sides[s], along = ((e.pos ?? 0.5) - 0.5) * S.len, t = vi.v.techo || {};
    if ((e.sobre || 'parapeto') === 'parapeto') {
      const pp = t.tipo === 'plano' ? t.parapeto ?? 0.6 : 0, y = vi.eave + pp + (detail && pp > 0 ? 0.05 : 0) + (vi.lift || 0);
      P.env.addRaw('metal_pintado#3a3f44', boxG(tw + 0.3, 0.14, dep + 0.08).applyMatrix4(sideMatrix(vi.f, s, along, y, 0)));
      m = sideMatrix(vi.f, s, along, y + 0.14, -dep / 2);
    } else m = sideMatrix(vi.f, s, along, e.y ?? Math.max(0.5, vi.eave - Hl - 0.7), (vi.SS?.[s]?.cortina ? CW_D : 0) + 0.06);
  } else {
    const c = planToThree(e.centro);
    m = new THREE.Matrix4().compose(V3(c.x, e.base ?? 0, c.z), facing(e.rumbo), V3(1, 1, 1));
  }
  P.env.addRaw(key, tg.applyMatrix4(m));
}

// ---------- adecuaciones: paneles (con rieles y anclajes), marquesinas, baterías, inversores y conexión
const quatFrom = (u, n, d) => { const x = u.clone(); if (x.clone().cross(n).dot(d) < 0) x.negate(); return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, n, d)); };
// devuelve { mods: [[p, q]], u, kind, ext } (p: centro de la cara inferior del módulo)
function placeModules(ad, faceInfo) {
  const cols = Math.max(1, ad.columnas | 0), rows = Math.max(1, ad.filas | 0);
  const vert = (ad.orientacion_modulo || 'vertical') !== 'horizontal';
  const mw = vert ? MOD.W : MOD.L, ml = vert ? MOD.L : MOD.W, gu = 0.02, gv = 0.05;
  const pu = mw + gu, pv = ml + gv;
  const mods = [];
  const modRot = vert ? new THREE.Quaternion() : new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2);
  if (faceInfo.flat) {
    // racks inclinados en cubierta plana orientados al azimut (planta) indicado
    const az = (ad.azimut ?? 180) * D2R, tilt = (ad.inclinacion ?? 10) * D2R;
    const fdir = V3(Math.sin(az), 0, -Math.cos(az)), u = V3(Math.cos(az), 0, Math.sin(az));
    const n = UP.clone().multiplyScalar(Math.cos(tilt)).addScaledVector(fdir, Math.sin(tilt)).normalize();
    const d = fdir.clone().multiplyScalar(Math.cos(tilt)).addScaledVector(UP, -Math.sin(tilt)).normalize();
    const c = V3(0, faceInfo.y, 0).applyMatrix4(faceInfo.m);
    const rowPitch = ml * Math.cos(tilt) + 0.45, q = quatFrom(u, n, d).multiply(modRot);
    for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
      const p = c.clone().addScaledVector(u, (i - (cols - 1) / 2) * pu).addScaledVector(fdir, (j - (rows - 1) / 2) * rowPitch); p.y += 0.25 + (ml / 2) * Math.sin(tilt);
      mods.push([p, q]);
    }
    return { mods, u, kind: 'rack', ext: [mw, ml] };
  }
  if (faceInfo.arc) {
    const { sg, yc, Rr, D } = faceInfo, rot = faceInfo.rot, r3m = new THREE.Matrix4().extractRotation(faceInfo.m);
    let uW = V3(1, 0, 0);
    for (let j = 0; j < rows; j++) {
      const s = 0.4 + (j + 0.5) * pv; // longitud de arco desde la clave
      const ang = s / Rr; if (Math.sin(ang) * Rr > D / 2 - 0.3) continue;
      const z = sg * Rr * Math.sin(ang), y = yc + Rr * Math.cos(ang) + 0.12;
      const nL = V3(0, Math.cos(ang), sg * Math.sin(ang)), dL = V3(0, -Math.sin(ang), sg * Math.cos(ang));
      for (let i = 0; i < cols; i++) {
        const p = V3((i - (cols - 1) / 2) * pu, y, z), n = nL.clone(), d = dL.clone(), u = V3(1, 0, 0);
        if (rot) { const r3 = new THREE.Matrix4().extractRotation(rot); p.applyMatrix4(rot); n.applyMatrix4(r3); d.applyMatrix4(r3); u.applyMatrix4(r3); }
        p.applyMatrix4(faceInfo.m); n.applyMatrix4(r3m); d.applyMatrix4(r3m); u.applyMatrix4(r3m); uW = u;
        mods.push([p, quatFrom(u, n, d).multiply(modRot)]);
      }
    }
    return { mods, u: uW, kind: 'arco', ext: [mw, ml] };
  }
  const r3 = new THREE.Matrix4().extractRotation(faceInfo.m);
  const n = faceInfo.n.clone().applyMatrix4(r3), u = faceInfo.u.clone().applyMatrix4(r3), d = faceInfo.vd.clone().applyMatrix4(r3);
  const c = faceInfo.c.clone().applyMatrix4(faceInfo.m).addScaledVector(n, 0.14);
  const q = quatFrom(u, n, d).multiply(modRot);
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) mods.push([c.clone().addScaledVector(u, (i - (cols - 1) / 2) * pu).addScaledVector(d, (j - (rows - 1) / 2) * pv), q]);
  return { mods, u, kind: 'faldon', ext: [mw, ml] };
}
// rieles de aluminio bajo cada fila (a ¼ y ¾ del módulo) y anclajes hasta la cubierta (o patas en racks)
function rails(P, arr, rayMeshes, detail) {
  const rc = new THREE.Raycaster(), rows = new Map();
  for (const [p, q] of arr.mods) {
    const n = UP.clone().applyQuaternion(q), d = arr.u.clone().cross(n).normalize();
    const key = `${Math.round(p.dot(d) / 0.3)}_${Math.round(n.y * 50)}`;
    if (!rows.has(key)) rows.set(key, { n, d, ps: [] });
    rows.get(key).ps.push(p);
  }
  for (const { n, d, ps } of rows.values()) {
    const tu = ps.map((p) => p.dot(arr.u)), i0 = tu.indexOf(Math.min(...tu)), i1 = tu.indexOf(Math.max(...tu));
    const a0 = ps[i0].clone().addScaledVector(arr.u, -arr.ext[0] / 2 - 0.08), a1 = ps[i1].clone().addScaledVector(arr.u, arr.ext[0] / 2 + 0.08);
    for (const s of [-1, 1]) {
      const off = d.clone().multiplyScalar((s * arr.ext[1]) / 4).addScaledVector(n, -0.022);
      const ra = a0.clone().add(off), rb = a1.clone().add(off);
      P.rack.addRaw('metal_pintado#c4c8cb', beamG(ra, rb, 0.04, 0.04, n));
      if (!detail || !rayMeshes.length) continue;
      const len = ra.distanceTo(rb), nf = Math.max(2, Math.ceil(len / 1.4));
      for (let k = 0; k <= nf; k++) {
        const top = ra.clone().lerp(rb, k / nf).addScaledVector(n, -0.02), dir = arr.kind === 'rack' ? V3(0, -1, 0) : n.clone().negate();
        rc.set(top, dir); rc.far = 1.5;
        const hit = rc.intersectObjects(rayMeshes, false)[0];
        if (!hit || hit.distance < 0.02) continue;
        const bot = top.clone().addScaledVector(dir, hit.distance + 0.02);
        P.rack.addRaw('metal_pintado#2b2d30', beamG(top, bot, arr.kind === 'rack' ? 0.05 : 0.06, arr.kind === 'rack' ? 0.05 : 0.03, arr.u));
        if (arr.kind === 'rack') P.rack.addRaw('pintura#ecebe6', boxG(0.3, 0.11, 0.22, bot.x, bot.y - 0.01, bot.z));
      }
    }
  }
}
// Marquesina solar (o estructura en tierra si es baja): columnas con placa y dado, vigas, correas bajo cada fila
// de módulos, riostras y canal. Devuelve los módulos y los pies de columna (para la ruta de potencia).
function canopy(ad, P, detail) {
  const f = frame({ ...ad, largo: ad.largo ?? 16, ancho: ad.ancho ?? 6 }), h = ad.altura ?? 3.5, tilt = (ad.inclinacion ?? (h < 1.5 ? 10 : 5)) * D2R;
  const cols = Math.max(1, ad.columnas | 0), rows = Math.max(1, ad.filas | 0), vert = (ad.orientacion_modulo || 'horizontal') === 'vertical';
  const mw = vert ? MOD.W : MOD.L, ml = vert ? MOD.L : MOD.W, pu = mw + 0.02, pv = ml + 0.02;
  const r3 = new THREE.Matrix4().extractRotation(f.m);
  const uL = V3(1, 0, 0), nL = V3(0, Math.cos(tilt), Math.sin(tilt)), dL = V3(0, -Math.sin(tilt), Math.cos(tilt));
  const u = uL.clone().applyMatrix4(r3), n = nL.clone().applyMatrix4(r3), d = dL.clone().applyMatrix4(r3);
  const q = quatFrom(u, n, d).multiply(vert ? new THREE.Quaternion() : new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2));
  const cL = V3(0, h + 0.35, 0), mods = [];
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) mods.push([cL.clone().addScaledVector(uL, (i - (cols - 1) / 2) * pu).addScaledVector(dL, (j - (rows - 1) / 2) * pv).applyMatrix4(f.m), q]);
  // estructura en coordenadas locales
  const FL = cols * pu, FW = rows * pv, add = (k, g) => g && P.rack.addRaw(k, g.applyMatrix4(f.m));
  const purl = (s) => cL.clone().addScaledVector(dL, s).addScaledVector(nL, -0.06);
  for (let j = 0; j < rows; j++) for (const s of [-1, 1]) { const o = (j - (rows - 1) / 2) * pv + (s * ml) / 4; add('metal_pintado#2b2d30', beamG(purl(o).addScaledVector(uL, -FL / 2 - 0.15), purl(o).addScaledVector(uL, FL / 2 + 0.15), 0.06, 0.09, nL)); }
  const nc = Math.max(2, Math.round(FL / 5.5) + 1), low = h < 1.5, feet = [];
  const beamAt = (s) => cL.clone().addScaledVector(dL, s).addScaledVector(nL, -0.2);
  for (let i = 0; i < nc; i++) {
    const x = -FL / 2 + 0.4 + (i * (FL - 0.8)) / (nc - 1), sh = uL.clone().multiplyScalar(x);
    add('metal_pintado#2b2d30', beamG(beamAt(-FW / 2 - 0.1).add(sh), beamAt(FW / 2 + 0.1).add(sh), 0.12, 0.2, nL));
    const legs = low || FW > 6.5 ? [-FW / 2 + 0.5, FW / 2 - 0.5] : [0];
    for (const s of legs) {
      const top = beamAt(s).add(sh).addScaledVector(nL, -0.1), foot = V3(top.x, 0, top.z);
      add('metal_pintado#2b2d30', beamG(foot, top, 0.18, 0.18, V3(0, 0, 1)));
      if (detail) {
        add('metal_pintado#2b2d30', boxG(0.36, 0.03, 0.36, foot.x, 0.25, foot.z));
        add('pintura#ecebe6', boxG(0.5, 0.25, 0.5, foot.x, 0, foot.z));
        if (!low && legs.length === 1) for (const sd of [-1, 1]) add('metal_pintado#2b2d30', beamG(V3(foot.x, top.y - 0.9, foot.z), beamAt(sd * 1.1).add(sh).addScaledVector(nL, -0.1), 0.08, 0.08, V3(1, 0, 0)));
      }
      feet.push(foot.clone().applyMatrix4(f.m));
    }
  }
  if (detail && !low) add('metal_pintado#c3c7c8', beamG(beamAt(FW / 2 + 0.1).addScaledVector(uL, -FL / 2), beamAt(FW / 2 + 0.1).addScaledVector(uL, FL / 2), 0.14, 0.12));
  return { mods, u, kind: 'marquesina', ext: [mw, ml], feet, top: h };
}
// Pérgola solar sobre una cubierta plana: pórticos de acero apoyados en la losa (columnas cada ~6,5 m con dado, placa y
// riostras), vigas en la pendiente de los módulos, vigas de amarre, correas bajo cada fila y canal en el borde bajo; los
// equipos de la cubierta quedan debajo. La base es la cubierta del `volumen` (o la más alta bajo el centro) y `altura` es la
// del plano de los módulos sobre ella (la luz libre bajo las vigas es ~0,75 m menor).
function pergola(ad, P, V, detail) {
  const f0 = frame({ ...ad, largo: ad.largo ?? 16, ancho: ad.ancho ?? 10 }), c = V3(0, 0, 0).applyMatrix4(f0.m);
  const vol = ad.volumen ? V.find((x) => x.v.id === ad.volumen && x.f) : null;
  const base = ad.base ?? (vol ? vol.base + vol.eave + 0.02 + (vol.lift || 0) : roofAt(P, c.x, c.z) ?? 0);
  const f = frame({ ...ad, largo: f0.L, ancho: f0.A, base }), h = ad.altura ?? 3.5, tilt = (ad.inclinacion ?? 3) * D2R;
  const cols = Math.max(1, ad.columnas | 0), rows = Math.max(1, ad.filas | 0), vert = (ad.orientacion_modulo || 'horizontal') === 'vertical';
  const mw = vert ? MOD.W : MOD.L, ml = vert ? MOD.L : MOD.W, pu = mw + 0.02, pv = ml + 0.02;
  const r3 = new THREE.Matrix4().extractRotation(f.m);
  const uL = V3(1, 0, 0), nL = V3(0, Math.cos(tilt), Math.sin(tilt)), dL = V3(0, -Math.sin(tilt), Math.cos(tilt));
  const u = uL.clone().applyMatrix4(r3), n = nL.clone().applyMatrix4(r3), d = dL.clone().applyMatrix4(r3);
  const q = quatFrom(u, n, d).multiply(vert ? new THREE.Quaternion() : new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2));
  const cL = V3(0, h, 0), mods = [];
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) mods.push([cL.clone().addScaledVector(uL, (i - (cols - 1) / 2) * pu).addScaledVector(dL, (j - (rows - 1) / 2) * pv).applyMatrix4(f.m), q]);
  const FL = cols * pu, FW = rows * pv, sk = tint('metal_pintado', ad.color, '#5d6368'), add = (k, g) => g && P.rack.addRaw(k, g.applyMatrix4(f.m));
  const at = (s, off, x = 0) => cL.clone().addScaledVector(dL, s).addScaledVector(nL, off).addScaledVector(uL, x);
  for (let j = 0; j < rows; j++) for (const sg of [-1, 1]) { const o = (j - (rows - 1) / 2) * pv + (sg * ml) / 4; add(sk, beamG(at(o, -0.07, -FL / 2 - 0.1), at(o, -0.07, FL / 2 + 0.1), 0.06, 0.1, nL)); }
  const nx = Math.max(2, Math.ceil((FL - 1) / 6.5) + 1), nz = Math.max(2, Math.ceil((FW - 1.2) / 6.5) + 1), feet = [];
  const xs = Array.from({ length: nx }, (_, i) => -FL / 2 + 0.5 + (i * (FL - 1)) / (nx - 1)), ss = Array.from({ length: nz }, (_, j) => -FW / 2 + 0.6 + (j * (FW - 1.2)) / (nz - 1));
  for (const x of xs) add(sk, beamG(at(-FW / 2 - 0.1, -0.27, x), at(FW / 2 + 0.1, -0.27, x), 0.16, 0.3, nL));
  for (const s of ss) add(sk, beamG(at(s, -0.57, -FL / 2 + 0.4), at(s, -0.57, FL / 2 - 0.4), 0.14, 0.3, nL));
  for (const x of xs) for (const s of ss) {
    const top = at(s, -0.72, x), foot = V3(top.x, detail ? 0.1 : -0.02, top.z); // dentro del dado (o 2 cm en la losa)
    add(sk, beamG(foot, top, 0.22, 0.22, V3(0, 0, 1)));
    if (detail) {
      add('pintura#c9c8c2', boxG(0.5, 0.3, 0.5, foot.x, -0.02, foot.z));
      add(sk, boxG(0.4, 0.03, 0.4, foot.x, 0.28, foot.z));
      for (const sg of [-1, 1]) add(sk, beamG(V3(top.x, top.y - 1.0, top.z), at(s, -0.62, x + sg * 1.0), 0.08, 0.08, V3(0, 0, 1)));
    }
    feet.push(foot.clone().setY(0).applyMatrix4(f.m));
  }
  if (detail) add(sk, beamG(at(FW / 2 + 0.17, -0.2, -FL / 2 - 0.1), at(FW / 2 + 0.17, -0.2, FL / 2 + 0.1), 0.14, 0.16, nL));
  return { mods, u, kind: 'pergola', ext: [mw, ml], feet, top: base + h, vi: vol };
}
// Baterías: gabinetes (con puertas, rejillas, aire acondicionado y señales) o contenedor; losa y bolardos
function bessGroup(b, be, P, detail) {
  const tipo = be.tipo || (be.kwh > 200 ? 'contenedor_20' : be.kwh > 90 ? 'contenedor_10' : 'gabinete');
  const L = be.largo ?? (tipo === 'contenedor_20' ? 6.06 : tipo === 'contenedor_10' ? 2.99 : Math.max(1.4, Math.ceil((be.kwh || 30) / 60) * 1.3 + 1));
  const c0 = be.centro || [0, 0], g = groundAt(P, c0[0], c0[1]), pad = g + 0.15;
  const f = frame({ ...be, centro: c0, largo: L, ancho: be.ancho ?? (tipo === 'gabinete' ? 1.2 : 2.44) });
  const add = (k, geo, uv = false) => P.bess.addRaw(k, geo.applyMatrix4(f.m), uv);
  add('piso', boxUV(f.L + 0.6, pad, f.A + 0.6), true);
  const cab = [];
  if (tipo === 'gabinete') {
    const n = Math.max(1, Math.ceil((be.kwh || 30) / 60));
    for (let i = 0; i < n + 1; i++) {
      const x = -f.L / 2 + 0.65 + i * ((f.L - 1.3) / Math.max(1, n)), pcs = i === n, w = pcs ? 0.8 : 1.0, h = pcs ? 1.9 : 2.15, d = pcs ? 0.7 : 0.8;
      add('pintura_satin#f2f3f3', boxG(w, h - 0.08, d, x, pad + 0.08, 0));
      add('pintura_satin#e3141b', boxG(w + 0.05, 0.08, d + 0.05, x, pad + h - 0.4, 0));
      add('pintura_satin#2a2f38', boxG(0.25, 0.15, 0.04, x, pad + h * 0.65, d / 2 + 0.015));
      cab.push({ x, w, h, d });
      if (detail) {
        const z = d / 2;
        add('metal_pintado#2b2d30', boxG(w + 0.04, 0.1, d + 0.04, x, pad - 0.02, 0)); // zócalo del gabinete
        if (!pcs) add('pintura#17191b', boxG(0.012, h - 0.35, 0.024, x, pad + 0.12, z)); // junta entre las dos puertas
        for (const hx of pcs ? [w / 2 - 0.1] : [-0.07, 0.07]) add('metal_pintado#c4c8cb', boxG(0.03, 0.2, 0.04, x + hx, pad + 1.0, z + 0.02));
        add('rejilla', boxG(w - 0.2, 0.3, 0.02, x, pad + 0.2, z + 0.03), true);
        warnSign(P.bess, 0.22, f.m.clone().multiply(new THREE.Matrix4().makeTranslation(x + (pcs ? -0.2 : 0.28), pad + (pcs ? 0.85 : 1.2), z + 0.022)));
        if (pcs) { add('pintura_satin#f4f4f2', boxG(0.5, 0.6, 0.22, x, pad + 0.55, -d / 2 - 0.11)); add('rejilla', boxG(0.4, 0.25, 0.02, x, pad + 0.85, -d / 2 - 0.23), true); } // aire acondicionado de puerta
      }
    }
  } else {
    const part = bessPart(detail, tipo === 'contenedor_20' ? 6.06 : 2.99);
    for (const [k, gs] of part.byMat) for (const gg of gs) P.bess.addRaw(k, gg.clone().translate(0, pad, 0).applyMatrix4(f.m), !!gg.attributes.uv);
  }
  // bolardos amarillos con franjas negras alrededor de la losa
  if (detail) {
    const hx = f.L / 2 + 0.55, hz = f.A / 2 + 0.55, nx = Math.max(1, Math.round((2 * hx) / 1.6));
    const pts = [];
    for (let i = 0; i <= nx; i++) for (const z of [-hz, hz]) pts.push([-hx + (i * 2 * hx) / nx, z]);
    for (const [x, z] of pts) {
      add('advertencia', new THREE.CylinderGeometry(0.08, 0.08, 0.9, 10).translate(x, g + 0.45, z));
      for (const y of [0.55, 0.75]) add('pintura#17191b', new THREE.CylinderGeometry(0.095, 0.095, 0.07, 10).translate(x, g + y, z));
    }
  }
  return { f, pad, g, tipo };
}
// Inversores en el muro (con disipador, pantalla y seccionador DC) y bandeja ámbar sobre ellos
function inverters(P, inv, V, detail) {
  const vi = V.find((x) => x.v.id === inv.volumen && x.f && !x.open) || V.find((x) => x.f && !x.open); if (!vi) return null;
  const f = vi.f, s = sideFor(f, inv.lado || 'S'), n = Math.max(1, inv.n ?? 1), S = f.sides[s];
  const pos = Math.max(-S.len / 2 + 0.6 + (n * 0.85) / 2, Math.min(S.len / 2 - 0.6 - (n * 0.85) / 2, inv.pos ?? 0));
  const alongs = [];
  for (let i = 0; i < n; i++) {
    const a = (i - (n - 1) / 2) * 0.85 + pos, m = sideMatrix(f, s, a, 1.2, cwOff(vi, s)), add = (k, g) => P.equip.addRaw(k, g.applyMatrix4(m));
    alongs.push(a);
    add('pintura_satin#e9ecec', boxW(0.6, 0.78, 0.24, 0, 0, 0.12));
    add('pantalla', boxG(0.16, 0.1, 0.02, 0.1, 0.5, 0.25));
    add('pintura_satin#2b2f33', boxW(0.64, 0.08, 0.27, 0, 0.72, 0.135));
    if (detail) {
      for (const sx of [-1, 1]) for (let k = 0; k < 4; k++) add('metal_pintado#c4c8cb', boxG(0.03, 0.6, 0.02, sx * 0.315, 0.06, 0.04 + k * 0.05)); // disipadores laterales
      add('pintura_satin#e9ecec', boxW(0.18, 0.26, 0.12, -0.42, -0.12, 0.06)); // seccionador DC
      add('rojo', boxG(0.05, 0.1, 0.04, -0.42, 0.0, 0.14));
      for (const x of [-0.18, -0.06, 0.06, 0.18]) add('pintura#17191b', new THREE.CylinderGeometry(0.018, 0.018, 0.06, 6).translate(x, -0.03, 0.12));
    }
  }
  return { vi, s, alongs, a0: Math.min(...alongs) - 0.4, a1: Math.max(...alongs) + 0.4, y: 2.25 };
}
function charger(P, c, detail) {
  const g = groundAt(P, c.centro[0], c.centro[1]), y = g + PINTURA;
  const f = frame({ centro: c.centro, largo: 5, ancho: 2.5, rumbo_eje: c.rumbo_eje ?? 0 });
  const add = (k, geo) => P.equip.addRaw(k, geo.applyMatrix4(f.m));
  add('pintura#ecebe6', boxG(0.5, 0.12, 0.4, -2.7, g, 0));
  add('pintura_satin#2a2f38', boxG(0.35, 1.45, 0.25, -2.7, g + 0.12, 0));
  add('verde_ve', boxG(0.39, 0.1, 0.29, -2.7, g + 1.32, 0));
  if (detail) { add('pantalla', boxG(0.02, 0.18, 0.14, -2.515, g + 1.05, 0)); add('pintura#17191b', new THREE.TorusGeometry(0.12, 0.02, 6, 12).rotateY(Math.PI / 2).translate(-2.48, g + 0.74, 0.06)); }
  for (const [w, d, x, z] of [[5, 0.1, 0, 1.25], [5, 0.1, 0, -1.25], [0.1, 2.5, 2.5, 0], [1.2, 1.2, 0, 0]]) paintQuad(P, 'pintura#18a957', w, d, f.m.clone().multiply(new THREE.Matrix4().makeTranslation(x, 0, z)), y);
  return V3(-2.7, g, 0).applyMatrix4(f.m);
}

// ---------- conexión: arreglos → bajada por el muro → inversores → baterías → tablero/medidor → red
// Lado de un volumen que da a la calle más cercana (OpenStreetMap en data/geo/calles.json)
function streetSide(spec, vi, ref) {
  if (!CALLES) return null;
  const k = 111320, o = CALLES.origen, bx = (spec.lon - o.lon) * k * Math.cos((o.lat * Math.PI) / 180), by = (spec.lat - o.lat) * k;
  let best = null;
  for (const [s, S] of Object.entries(vi.f.sides)) {
    const nW = S.n.clone().transformDirection(vi.f.m), np = [nW.x, -nW.z];
    const la = ref ? Math.max(-S.len * 0.45, Math.min(S.len * 0.45, ref.clone().applyMatrix4(vi.f.inv).dot(S.t))) : 0;
    for (const off of [-1, 0, 1]) {
      const pw = S.n.clone().multiplyScalar(S.half).addScaledVector(S.t, Math.max(-S.len * 0.45, Math.min(S.len * 0.45, la + off * 2))).applyMatrix4(vi.f.m), p = [pw.x, -pw.z];
      const run = ref ? Math.hypot(pw.x - ref.x, pw.z - ref.z) : 0;
      for (const c of CALLES.calles) for (let j = 1; j < c.p.length; j++) {
        const a = [c.p[j - 1][0] - bx, c.p[j - 1][1] - by], bb = [c.p[j][0] - bx, c.p[j][1] - by];
        const ab = [bb[0] - a[0], bb[1] - a[1]], l2 = ab[0] ** 2 + ab[1] ** 2 || 1;
        const tt = Math.max(0, Math.min(1, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2));
        const w = [a[0] + tt * ab[0] - p[0], a[1] + tt * ab[1] - p[1]], dist = Math.hypot(...w);
        if (dist > 90 || (w[0] * np[0] + w[1] * np[1]) < 0.5 * dist) continue;
        const score = dist + 0.25 * run;
        if (!best || score < best.score) best = { s, dist, score, calle: c.nombre || c.tipo };
      }
    }
  }
  return best;
}
// posición libre en un muro (sin vanos, bajantes ni tramos tapados) cerca de "target" para un tramo [lo, hi]
function wallSlot(V, vi, s, target, lo, hi, avoid = []) {
  const S = vi.f.sides[s];
  for (let k = 0; k < 400; k++) {
    const a = target + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * 0.1;
    if (a + lo < -S.len / 2 + 0.3 || a + hi > S.len / 2 - 0.3) continue;
    const bad = (vi.ops[s] || []).some((o) => o.along + o.w / 2 > a + lo - 0.1 && o.along - o.w / 2 < a + hi + 0.1 && o.y0 < 2.4)
      || (vi.cov[s] || []).some((c) => c.a1 > a + lo - 0.1 && c.a0 < a + hi + 0.1 && c.y0 < 2.4)
      || (vi.pipes[s] || []).some((x) => x > a + lo - 0.25 && x < a + hi + 0.25)
      || avoid.some(([x0, x1]) => x1 > a + lo && x0 < a + hi)
      || obstructed(V, vi, s, a + lo, a + hi, 0.5, 2.4, 0.45);
    if (!bad) return a;
  }
  return null;
}
// en un muro cortina, lo que va sobre el muro (tablero, medidor, inversores, ductos) se monta delante de los parales
const cwOff = (vi, s) => (vi.SS?.[s]?.cortina ? CW_D + 0.02 : 0);
const wallPt = (vi, s, a, y, out = 0.15) => { const S = vi.f.sides[s]; const p = S.n.clone().multiplyScalar(S.half + out + cwOff(vi, s)).addScaledVector(S.t, a); p.y = y; return p.applyMatrix4(vi.f.m); };
const proj = (vi, s, p) => { const l = p.clone().applyMatrix4(vi.f.inv), S = vi.f.sides[s]; return l.x * S.t.x + l.z * S.t.z; };
function conexion(spec, P, V, arrays, invInfo, bessInfo, evPt, detail) {
  const R = detail ? 0.1 : 0.12, seg = detail ? 10 : 6, J = detail, POW = P.pow, DAT = P.dat, MED = 0.58, GWO = -0.58;
  const gp = (p) => groundAt(P, p.x, -p.z) + R + 0.02; // ducto enterrado: se dibuja sobre el suelo para que se lea
  const G = (p) => V3(p.x, gp(p), p.z);
  const roofs = V.flatMap((vi) => vi.ray || []), rc = new THREE.Raycaster();
  const roofY = (x, z) => { rc.set(V3(x, 80, z), V3(0, -1, 0)); rc.far = 200; const h = rc.intersectObjects(roofs, false)[0]; return h ? h.point.y : null; };
  const run = (pts) => { P.ductos.push({ pts, r: R }); return pipe(POW, 'potencia', pts, R, J, seg); };
  // esquina de un tramo en "L" entre a y b: primero a lo largo de "dir" (horizontal)
  const corner = (a, b, dir) => { const d = dir.clone().setY(0).normalize(); return a.clone().addScaledVector(d, b.clone().sub(a).setY(0).dot(d)); };
  const wallN = (vi, s) => vi.f.sides[s].n.clone().transformDirection(vi.f.m), wallT = (vi, s) => vi.f.sides[s].t.clone().transformDirection(vi.f.m);
  const flatD = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
  // ---- tablero y medidor: junto al poste de la red si hay uno a menos de 40 m de un muro; si no, en la fachada que da a la calle
  const mainVi = invInfo?.vi || V.find((x) => x.f && !x.open && x.v.techo?.tipo !== 'ninguno') || V.find((x) => x.f && !x.open);
  if (!mainVi) return null;
  const ref = invInfo ? wallPt(invInfo.vi, invInfo.s, (invInfo.a0 + invInfo.a1) / 2, 0) : V3(0, 0, 0).applyMatrix4(mainVi.f.m);
  let site = null, nota;
  for (const pl of P.poles) for (const vi of V) {
    if (!vi.f || vi.open || vi.v.techo?.tipo === 'ninguno') continue;
    for (const s of Object.keys(vi.f.sides)) {
      const S = vi.f.sides[s], l = pl.c.clone().applyMatrix4(vi.f.inv), dist = l.x * S.n.x + l.z * S.n.z - S.half, al = l.x * S.t.x + l.z * S.t.z;
      if (dist < 0.5 || dist > 40 || Math.abs(al) > S.len / 2 + dist) continue;
      if (!site || dist < site.dist) site = { vi, s, dist, target: Math.max(-S.len / 2, Math.min(S.len / 2, al)), pl };
    }
  }
  const pole = site?.pl || null;
  if (pole) nota = `Punto de conexión: poste existente de la red a ${site.dist.toFixed(0)} m del muro${pole.e.nombre ? ` (${pole.e.nombre})` : ''}; acometida subterránea desde el medidor y bajante por el poste.`;
  else {
    const st = streetSide(spec, mainVi, ref), s = st?.s || sideFor(mainVi.f, (mainVi.v.fachada?.puertas || [])[0]?.lado || 'S');
    site = { vi: mainVi, s, target: proj(mainVi, s, ref) };
    nota = `Sin poste cercano en la especificación: el punto de conexión es la acometida en la fachada de ${mainVi.v.nombre || mainVi.v.id} que da a ${st ? `la calle (${st.calle}, a ${st.dist.toFixed(0)} m)` : 'la puerta principal'}.`;
  }
  const nArr = arrays.filter((a) => a.mods.length).length;
  const avoid = (vi, s) => (invInfo && invInfo.vi === vi && invInfo.s === s ? [[invInfo.a0 - 0.6, invInfo.a1 + 0.9 + 0.3 * nArr]] : []);
  let ta = wallSlot(V, site.vi, site.s, site.target, -0.8, 0.8, avoid(site.vi, site.s));
  if (ta === null) for (const s of Object.keys(site.vi.f.sides)) { ta = wallSlot(V, site.vi, s, 0, -0.8, 0.8, avoid(site.vi, s)); if (ta !== null) { site.s = s; break; } }
  if (ta === null) ta = site.target;
  const tv = site.vi, ts = site.s, TB = (a, y, out) => wallPt(tv, ts, ta + a, y, out), mt = (a, y) => sideMatrix(tv.f, ts, ta + a, y, cwOff(tv, ts));
  // tablero general (gris con franja ámbar), medidor bidireccional y pasarela IoT (franja violeta)
  const pc = P.punto, gw = P.gw;
  pc.addRaw('pintura_satin#aeb5b9', boxW(0.7, 1.0, 0.25, 0, 0, 0.125).applyMatrix4(mt(0, 0.8)));
  pc.addRaw('potencia', boxW(0.76, 0.08, 0.27, 0, 0.82, 0.135).applyMatrix4(mt(0, 0.8)));
  pc.addRaw('pintura_satin#f2f3f3', boxW(0.3, 0.5, 0.2, 0, 0, 0.1).applyMatrix4(mt(MED, 1.2)));
  pc.addRaw('pantalla', boxG(0.18, 0.12, 0.02, 0, 0.3, 0.205).applyMatrix4(mt(MED, 1.2)));
  if (detail) {
    pc.addRaw('pintura_satin#2b2f33', boxG(0.012, 0.9, 0.02, 0, 0.05, 0.255).applyMatrix4(mt(0, 0.8)));
    pc.addRaw('metal_pintado#c4c8cb', boxG(0.04, 0.16, 0.04, 0.25, 0.42, 0.27).applyMatrix4(mt(0, 0.8)));
    warnSign(pc, 0.18, mt(-0.17, 1.45).multiply(new THREE.Matrix4().makeTranslation(0, 0, 0.265)));
    pc.addRaw('potencia', boxW(0.34, 0.04, 0.22, 0, 0.5, 0.11).applyMatrix4(mt(MED, 1.2)));
  }
  gw.addRaw('pintura_satin#f2f3f3', boxW(0.26, 0.32, 0.1, 0, 0, 0.05).applyMatrix4(mt(GWO, 1.45)));
  gw.addRaw('datos', boxW(0.3, 0.05, 0.12, 0, 0.22, 0.06).applyMatrix4(mt(GWO, 1.45)));
  gw.addRaw('datos', new THREE.CylinderGeometry(0.012, 0.012, 0.2, 6).translate(0.09, 0.42, 0.05).applyMatrix4(mt(GWO, 1.45)));
  const tablero = TB(0, 1.3, 0.125), gateway = TB(GWO, 1.61, 0.05);
  // borde de la cubierta frente a un punto del muro: { p: 30 cm afuera del borde, y: altura de la cubierta en el borde }
  const eY = tv.base + tv.eave;
  const edge = (a) => {
    let lastY = null;
    for (let o = 0.15; o < 5; o += 0.1) { const p = wallPt(tv, ts, a, 0, o), y = roofY(p.x, p.z); if (y === null || y > eY + 3) return { p: wallPt(tv, ts, a, 0, o + 0.3), y: lastY ?? eY }; lastY = y; }
    return { p: wallPt(tv, ts, a, 0, 0.6), y: eY };
  };
  // ---- datos: de la pasarela, muro arriba, bajo el alero y hasta la antena sobre el borde de la cubierta
  const ed = edge(ta + GWO), yUnder = Math.max(2.4 + tv.base, Math.min(ed.y, eY) - 0.45), antTop = V3(ed.p.x, ed.y + 1.4, ed.p.z);
  const dat = [TB(GWO, 1.77, 0.12), TB(GWO, yUnder, 0.12), V3(ed.p.x, yUnder, ed.p.z), V3(ed.p.x, ed.y + 0.3, ed.p.z)];
  P.ductos.push({ pts: dat, r: detail ? 0.05 : 0.07 }, { pts: [V3(ed.p.x, yUnder - 0.3, ed.p.z), antTop], r: 0.03 });
  pipe(DAT, 'datos', dat, detail ? 0.05 : 0.07, J, seg);
  gw.addRaw('metal_pintado#c4c8cb', tubeG(V3(ed.p.x, yUnder - 0.3, ed.p.z), antTop, 0.03, 8));
  gw.addRaw('pintura_satin#f2f3f3', new THREE.CylinderGeometry(0.06, 0.06, 0.55, 10).translate(antTop.x, antTop.y + 0.27, antTop.z));
  gw.addRaw('datos', new THREE.CylinderGeometry(0.085, 0.085, 0.06, 10).translate(antTop.x, antTop.y + 0.4, antTop.z));
  // ---- red: acometida subterránea y bajante por el poste, o acometida en la fachada con capacete y aislador
  let red;
  if (pole) {
    const base = V3(pole.c.x, 0, pole.c.z), toW = TB(MED, 0, 0.15).sub(base).setY(0).normalize(), side = base.clone().addScaledVector(toW, 0.24);
    red = V3(side.x, pole.h - 1.9, side.z);
    const m0 = TB(MED, 0.5, 0.15);
    run([TB(MED, 1.2, 0.15), m0, G(m0), G(corner(m0, side, wallN(tv, ts))), G(side), red]);
    POW.addRaw('potencia', new THREE.SphereGeometry(R * 1.6, seg, 6).translate(red.x, red.y, red.z));
  } else {
    const ed2 = edge(ta + MED), y = Math.max(2.5 + tv.base, Math.min(ed2.y, eY) - 0.6);
    red = TB(MED, y + 0.25, 0.62);
    run([TB(MED, 1.7, 0.15), TB(MED, y, 0.15), TB(MED, y + 0.25, 0.36)]);
    pc.addRaw('potencia', beamG(TB(MED, y + 0.25, 0.32), TB(MED, y + 0.25, 0.6), 0.17, 0.21)); // capacete de la acometida
    pc.addRaw('pintura_satin#d8dcdf', new THREE.CylinderGeometry(0.05, 0.07, 0.16, 8).translate(red.x, red.y + 0.18, red.z)); // aislador de retención
  }
  // ---- CA: inversores → baterías → tablero (o inversores → tablero) y tablero → cargador
  const tbIn = TB(-0.2, 0.8, 0.15);
  if (invInfo) {
    const { vi, s } = invInfo, bProj = bessInfo ? proj(vi, s, bessInfo.c) : invInfo.a1;
    const endA = Math.abs(bProj - invInfo.a0) < Math.abs(bProj - invInfo.a1) ? invInfo.a0 : invInfo.a1, otherA = endA === invInfo.a0 ? invInfo.a1 : invInfo.a0;
    run([wallPt(vi, s, otherA, invInfo.y), wallPt(vi, s, endA, invInfo.y)]); // bandeja sobre los inversores
    for (const a of invInfo.alongs) run([wallPt(vi, s, a, invInfo.y), wallPt(vi, s, a, 1.98)]);
    const down = wallPt(vi, s, endA, invInfo.y);
    if (bessInfo) {
      const e1 = bessInfo.entry(down), e2 = bessInfo.entry(tbIn);
      run([down, G(down), G(corner(down, e1, wallN(vi, s))), G(e1), V3(e1.x, bessInfo.pad + 0.5, e1.z)]);
      run([V3(e2.x, bessInfo.pad + 0.5, e2.z), G(e2), G(corner(e2, tbIn, wallT(tv, ts))), G(tbIn), tbIn]);
    } else if (vi === tv && s === ts) run([down, wallPt(vi, s, ta - 0.2, invInfo.y), TB(-0.2, 1.8, 0.15)]);
    else run([down, G(down), G(corner(down, tbIn, wallN(vi, s))), G(tbIn), tbIn]);
  }
  if (evPt) { const o = TB(0.2, 0.8, 0.15), e = evPt.clone().add(o.clone().sub(evPt).setY(0).normalize().multiplyScalar(0.32)); run([o, G(o), G(corner(o, e, wallN(tv, ts))), G(e), e.setY(evPt.y + 0.5)]); }
  // ---- CC: de cada arreglo, por la cubierta hasta el borde y bajada por el muro, por una columna o enterrada
  arrays.forEach((arr, k) => {
    if (!arr.mods.length || !invInfo) return;
    const { vi, s } = invInfo, tgt = invInfo.a1 + 0.35 + k * 0.3, T = wallPt(vi, s, tgt, invInfo.y), Tg = wallPt(vi, s, tgt, 0);
    run([wallPt(vi, s, invInfo.a1, invInfo.y), T]);
    const buried = (from) => [from, G(from), G(corner(from, Tg, wallT(vi, s))), G(Tg), T];
    if (arr.kind === 'marquesina') {
      const ft = arr.feet.reduce((a, b) => (flatD(a, T) < flatD(b, T) ? a : b)), dir = T.clone().sub(ft).setY(0).normalize(), c0 = ft.clone().addScaledVector(dir, 0.2);
      run(buried(V3(c0.x, Math.max(0.6, arr.top), c0.z)));
      return;
    }
    // inicio: el módulo más cercano (en planta) a la llegada; se sigue la cubierta en línea recta hacia ella
    const S1 = arr.mods.map(([p]) => p).reduce((a, b) => (flatD(a, T) < flatD(b, T) ? a : b)).clone();
    const path = [];
    // tramo a lo largo del faldón hasta quedar frente a la llegada (si sigue sobre la cubierta)
    let S0 = S1;
    const K = corner(S1, T, arr.u), l1 = flatD(S1, K);
    if (l1 > 0.3 && roofY(K.x, K.z) !== null) {
      for (let x = 0; x < l1; x += 0.35) { const p = S1.clone().lerp(K, x / l1), y = roofY(p.x, p.z); if (y !== null) path.push(p.setY(y + 0.16)); }
      S0 = K;
    }
    const dir = T.clone().sub(S0).setY(0), dl = dir.length(); dir.normalize();
    const at = (x) => S0.clone().addScaledVector(dir, x);
    const hitAt = (x, prev) => { const p = at(x), y = roofY(p.x, p.z); return y === null || (prev !== null && y < prev - 1.2) ? null : y; };
    let x = 0, prev = null;
    const n0 = path.length;
    for (; x < dl + 12; x += 0.35) { const y = hitAt(x, prev); if (y === null) break; prev = y; path.push(at(x).setY(y + 0.16)); }
    if (path.length === n0) return;
    let lo = x - 0.35, hi = x; for (let i = 0; i < 8; i++) { const mid = (lo + hi) / 2; if (hitAt(mid, prev) !== null) lo = mid; else hi = mid; }
    const yEdge = roofY(at(lo).x, at(lo).z) ?? prev, edgeP = at(lo).setY(yEdge + 0.16), outP = at(lo + 0.35).setY(yEdge + 0.16), yB = yEdge - 0.3;
    path.push(edgeP, outP);
    const pv = arr.vi;
    if (pv?.open && pv.cols.length) {
      // cubierta sobre columnas: bajo el alero hasta la columna más cercana y por ella al suelo
      const col = pv.cols.reduce((a, b) => (flatD(a, outP) < flatD(b, outP) ? a : b)), d2 = T.clone().sub(col).setY(0).normalize(), c = col.clone().addScaledVector(d2, (pv.v.columna ?? 0.25) / 2 + 0.1);
      const yc = Math.min(yB, pv.base + pv.eave - 0.45);
      path.push(V3(outP.x, yc, outP.z), V3(c.x, yc, c.z), ...buried(V3(c.x, yc, c.z)).slice(1));
    } else if (x < dl - 0.2 || flatD(outP, T) > 3) path.push(...buried(V3(outP.x, yB, outP.z)));
    else if (yB > T.y + 0.2) path.push(V3(outP.x, yB, outP.z), V3(T.x, yB, T.z), T);
    else path.push(V3(outP.x, T.y, outP.z), T);
    run(path);
  });
  return { tablero, gateway, red, nota, poste: !!pole };
}

// ---------- edificio completo
function build(spec, detail) {
  const b = new Builder(`${spec.id}_${detail ? 'lod0' : 'lod1'}`);
  baseMaterials(b); extraMaterials(b);
  const ad = spec.adecuaciones || {};
  const cn = ad.cubierta_nueva || (/(cambio|reemplazo|sustituci[oó]n|cambiar|reemplazar)[^.;]{0,40}cubierta|cubierta nueva|nueva cubierta/i.test((ad.obras_civiles || []).join(' ')) ? { material: 'termoacustica' } : null);
  const replaceIds = cn?.volumenes || null;
  const P = {
    walls: new Part(), roof: new Part(), roofKeep: new Part(), env: new Part(), newRoof: cn ? new Part() : null,
    equip: new Part(), bess: new Part(), solarFlat: new Part(), rack: new Part(), pow: new Part(), dat: new Part(), punto: new Part(), gw: new Part(),
    ground: [], trees: [], poles: [], inst: new Map(), puentes: bridgeCuts(spec), rings: [], ductos: [],
    replace: (v) => estadoDe(v) === 'existe' && (replaceIds ? replaceIds.includes(v.id) : ['fibrocemento', 'zinc', undefined].includes(v.techo?.material) && v.techo?.tipo !== 'plano' && v.techo?.tipo !== 'ninguno'),
    newRoofSpec: (t) => ({ ...t, material: cn?.material || 'termoacustica', color: cn?.color || (cn?.material === 'teja_barro' ? '#a5512f' : '#e9e7e1') }),
  };
  // estado de cada pieza: "existe" (se conserva), "demoler" (se ve en "Hoy" y desaparece con el proyecto) o "nuevo"
  // (obra nueva, solo con el proyecto). Cada estado acumula sus muros, cubiertas, entorno y árboles por separado
  const estadoDe = (o) => o.estado || spec.estado || 'existe';
  // (inst: instancias GPU de la capa: parasoles, luminarias, bancas, bolardos, arbustos)
  const G = { existe: { walls: P.walls, roof: P.roof, roofKeep: P.roofKeep, env: P.env, trees: P.trees, inst: P.inst } };
  for (const k of ['demoler', 'nuevo']) G[k] = { walls: new Part(), roof: new Part(), roofKeep: new Part(), env: new Part(), trees: [], inst: new Map() };
  const usar = (k) => Object.assign(P, G[k] || G.existe);
  // lo que hoy existe no tapa ni es tapado por la obra nueva, y lo que se demuele no cuenta para la obra nueva
  const compatibles = (k) => (k === 'nuevo' ? ['existe', 'nuevo'] : k === 'demoler' ? ['existe', 'demoler'] : ['existe']);
  // predio: rectángulo que envuelve todo con 2 m de margen (capa más baja del suelo)
  const xs = [], ys = [];
  const push = (pts) => pts && pts.forEach(([x, y]) => { xs.push(x); ys.push(y); });
  for (const v of spec.volumenes || []) push(rectOrPoly(v));
  for (const e of spec.elementos || []) push(rectOrPoly(e) || (e.centro ? [e.centro] : e.poligono || e.linea || (e.desde && e.hasta ? [e.desde, e.hasta] : e.centros)));
  if (xs.length) { const m = 2; slab(P, 'predio', [[Math.min(...xs) - m, Math.min(...ys) - m], [Math.max(...xs) + m, Math.min(...ys) - m], [Math.max(...xs) + m, Math.max(...ys) + m], [Math.min(...xs) - m, Math.max(...ys) + m]], 'predio'); }
  // volúmenes: marcos primero (para saber qué muros tapa cada uno)
  const V = (spec.volumenes || []).map((v, i) => {
    const base = v.base ?? 0, open = !!v.abierto, rect = !v.poligono && v.centro && v.largo && v.ancho;
    const eave = Math.max(base + (open ? 0.4 : 2.2), v.altura_alero ?? base + 3.2) - base;
    return { v, i, base, open, eave, top: base + eave, f: rect ? frame(v) : null };
  });
  // cubiertas vecinas a la misma altura cuyos aleros se solapan: se levantan 4 u 8 cm (y el alero se acorta 6 o 12 cm)
  // para que ni los faldones ni las tapas queden coplanares
  const corners = (vi, ext) => [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, c]) => V3((a * vi.f.L) / 2 + a * ext, 0, (c * vi.f.A) / 2 + c * ext).applyMatrix4(vi.f.m));
  const sepAxis = (P1, P2) => [P1, P2].some((Q) => Q.some((q, i) => { const r = Q[(i + 1) % 4], nx = -(r.z - q.z), nz = r.x - q.x; const pr = (S) => S.map((w) => w.x * nx + w.z * nz); const a = pr(P1), bb = pr(P2); return Math.max(...a) < Math.min(...bb) - 1e-3 || Math.max(...bb) < Math.min(...a) - 1e-3; }));
  V.forEach((vi, i) => {
    vi.lift = 0;
    const t = vi.v.techo; if (!vi.f || !t || t.tipo === 'ninguno') return;
    const ext = Math.max(0.3, t.voladizo ?? 0.6), used = new Set();
    for (const vj of V.slice(0, i)) {
      const tj = vj.v.techo; if (!vj.f || !tj || tj.tipo === 'ninguno') continue;
      if (Math.abs(vi.top - vj.top) > 0.3) continue; // aleros a alturas parecidas: faldones o tapas podrían coincidir
      if (!sepAxis(corners(vi, ext), corners(vj, Math.max(0.3, tj.voladizo ?? 0.6)))) used.add(vj.lift);
    }
    vi.lift = [0, 0.04, 0.08, 0.12].find((x) => !used.has(x)) ?? 0;
  });
  const vols = V.map((vi) => {
    try {
      const k = estadoDe(vi.v); usar(k);
      const Vc = V.filter((vj) => compatibles(k).includes(estadoDe(vj.v)));
      const r = vi.f ? volume(b, vi, Vc, P, detail) : volumePoly(b, vi.v, P, detail);
      vi.ray = r.roofGeos.map((g) => new THREE.Mesh(g, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide })));
      return { id: vi.v.id, vi, ...r };
    } catch (e) { warn.push(`${spec.id}/${vi.v.id}: ${e.message}`); vi.ray = []; return { id: vi.v.id, vi, faces: [] }; }
  });
  P.roofRay = V.flatMap((vi) => vi.ray || []);
  for (const e of spec.elementos || []) { if (NUEVOS.has(e.tipo)) continue; try { usar(estadoDe(e)); element(b, e, P, detail, V); } catch (err) { warn.push(`${spec.id}/elemento ${e.tipo}: ${err.message}`); } }
  // elementos de obra nueva en una segunda pasada: ya están todos los suelos (pintura de bahías) y las cubiertas (equipos)
  for (const e of spec.elementos || []) { if (!NUEVOS.has(e.tipo)) continue; try { usar(estadoDe(e)); newMats(b); elementoNuevo(e, P, detail, V); } catch (err) { warn.push(`${spec.id}/elemento ${e.tipo}: ${err.message}`); } }
  usar('existe');

  // instancias de pocas repeticiones: se funden en el entorno de su capa
  for (const g of Object.values(G)) for (const [k, it] of g.inst) {
    if (it.siempre || it.trs.length >= 10) continue;
    for (const tr of it.trs) { const m = new THREE.Matrix4().compose(V3(...tr.t), new THREE.Quaternion(...tr.r), V3(...(tr.s || [1, 1, 1]))); for (const [mk, gs] of it.part.byMat) for (const geo of gs) g.env.addRaw(mk, geo, !!geo.attributes.uv, m); }
    g.inst.delete(k);
  }
  const root = b.node(spec.nombre || spec.id, null);
  root.setExtras({ id: spec.id, lat: spec.lat, lon: spec.lon });
  const ex = b.node('existente', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root); ex.setExtras({ capa: 'existente' });
  // con losas expresadas, las mallas de muros se arman después de la conexión (los bordes de losa se cortan en sus ductos);
  // sin ellas, en el mismo orden de siempre
  const tarde = [], wallsNode = (name, mesh, part, parent) => { const nd = b.node(name, P.rings.length ? null : b.partMesh(mesh, part), [0, 0, 0], [0, 0, 0], [1, 1, 1], parent); if (P.rings.length) tarde.push(() => nd.setMesh(b.partMesh(mesh, part))); return nd; };
  wallsNode('estructura', `${spec.id}_estructura`, P.walls, ex);
  // cubiertas que el proyecto reemplaza (se ocultan con "Con el proyecto") y cubiertas que se conservan
  if (!P.roof.empty) b.node('cubierta_actual', b.partMesh(`${spec.id}_cubierta`, P.roof), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex).setExtras({ capa: 'existente', reemplazada: !!(P.newRoof && !P.newRoof.empty) });
  if (!P.roofKeep.empty) b.node('cubierta', b.partMesh(`${spec.id}_cubierta_conservada`, P.roofKeep), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex).setExtras({ capa: 'existente' });
  const env = b.node('entorno', P.env.empty ? null : b.partMesh(`${spec.id}_entorno`, P.env), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex);
  if (P.trees.length) {
    const tm = treeMesh(b, detail);
    instanced(b, 'arboles', tm, P.trees.map((t, i) => { const q = new THREE.Quaternion().setFromAxisAngle(UP, (i * 2.399) % (Math.PI * 2)); return { t: [t.c.x, 0, t.c.z], r: [q.x, q.y, q.z, q.w], s: [t.cp, t.H, t.cp] }; }), env);
  }
  const instNodes = (map, parent, pre) => [...map.values()].forEach((it, i) => instanced(b, `${pre}${it.name}`, b.partMesh(`${spec.id}_${pre}${it.name}_${i}`, it.part), it.trs, parent));
  instNodes(G.existe.inst, ex, '');

  // lo que el proyecto demuele: visible en "Hoy", oculto "Con el proyecto"
  const grupo = (k, parent, nombre, extras) => {
    const g = G[k]; if (g.walls.empty && g.roof.empty && g.roofKeep.empty && g.env.empty && !g.trees.length && !g.inst.size) return;
    const n = b.node(nombre, null, [0, 0, 0], [0, 0, 0], [1, 1, 1], parent); n.setExtras(extras);
    if (!g.walls.empty) wallsNode(`${nombre}_estructura`, `${spec.id}_${nombre}_estructura`, g.walls, n);
    for (const part of [g.roof, g.roofKeep].filter((x) => !x.empty)) b.node(`${nombre}_cubierta`, b.partMesh(`${spec.id}_${nombre}_cubierta_${part === g.roof ? 'a' : 'b'}`, part), [0, 0, 0], [0, 0, 0], [1, 1, 1], n);
    if (!g.env.empty) b.node(`${nombre}_entorno`, b.partMesh(`${spec.id}_${nombre}_entorno`, g.env), [0, 0, 0], [0, 0, 0], [1, 1, 1], n);
    if (g.trees.length) { const tm = treeMesh(b, detail); instanced(b, `${nombre}_arboles`, tm, g.trees.map((t, i) => { const q = new THREE.Quaternion().setFromAxisAngle(UP, (i * 2.399) % (Math.PI * 2)); return { t: [t.c.x, 0, t.c.z], r: [q.x, q.y, q.z, q.w], s: [t.cp, t.H, t.cp] }; }), n); }
    instNodes(g.inst, n, `${nombre}_`);
  };
  grupo('demoler', ex, 'a_demoler', { capa: 'existente', demoler: true });

  const adn = b.node('adecuaciones', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root); adn.setExtras({ capa: 'adecuaciones' });
  grupo('nuevo', adn, 'obra_nueva', { capa: 'adecuaciones', nueva: true });
  if (P.newRoof && !P.newRoof.empty) b.node('cubierta_nueva', b.partMesh(`${spec.id}_cubierta_nueva`, P.newRoof), [0, 0, 0], [0, 0, 0], [1, 1, 1], adn).setExtras({ capa: 'adecuaciones' });
  const solar = b.node('solar', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);
  const arrays = [];
  (ad.fv || []).forEach((a, k) => {
    try {
      if (a.tipo === 'marquesina') { arrays.push(canopy(a, P, detail)); return; }
      if (a.tipo === 'pergola') { newMats(b); arrays.push(pergola(a, P, V, detail)); return; }
      const vol = vols.find((v) => v.id === a.volumen) || vols[0];
      if (!vol?.faces?.length) { warn.push(`${spec.id}: el arreglo ${k} no tiene cubierta donde apoyarse`); return; }
      let fi = vol.faces[0];
      if (vol.faces.length > 1 && a.faldon && a.faldon !== 'plano') {
        const c = CARD[String(a.faldon).toUpperCase()[0]] || CARD.S, r3 = new THREE.Matrix4().extractRotation(vol.faces[0].m);
        let bd = -9;
        for (const q of vol.faces) { const n = q.n.clone().applyMatrix4(r3); const d = n.x * c[0] + -n.z * c[1]; if (d > bd) { bd = d; fi = q; } }
      }
      const arr = placeModules(a, fi); arr.vi = vol.vi;
      rails(P, arr, vol.vi.ray, detail);
      arrays.push(arr);
    } catch (e) { warn.push(`${spec.id}/fv ${k}: ${e.message}`); }
  });
  const allMods = arrays.flatMap((a) => a.mods), modules = allMods.length;
  if (detail) instanced(b, 'modulos', pvMesh(b), allMods.map(([p, q]) => ({ t: [p.x, p.y, p.z], r: [q.x, q.y, q.z, q.w] })), solar);
  else for (const [p, q] of allMods) { const g = new THREE.PlaneGeometry(MOD.W, MOD.L).rotateX(-Math.PI / 2); g.applyQuaternion(q).translate(p.x, p.y, p.z).translate(...UP.clone().applyQuaternion(q).multiplyScalar(0.035).toArray()); P.solarFlat.addRaw('celdas', g, true); }
  if (!P.rack.empty) b.node('soportes', b.partMesh(`${spec.id}_soportes`, P.rack), [0, 0, 0], [0, 0, 0], [1, 1, 1], solar);
  if (!detail && !P.solarFlat.empty) b.node('solar_simplificada', b.partMesh(`${spec.id}_solar`, P.solarFlat), [0, 0, 0], [0, 0, 0], [1, 1, 1], solar);
  let bessInfo = null;
  if (ad.bess) {
    const bi = bessGroup(b, ad.bess, P, detail);
    const c = V3(0, 0, 0).applyMatrix4(bi.f.m);
    // entrada de cables: el punto del borde de la losa más cercano a "p"
    bessInfo = { c, pad: bi.pad, entry: (p) => { const l = p.clone().applyMatrix4(new THREE.Matrix4().copy(bi.f.m).invert()); const hx = bi.f.L / 2 + 0.2, hz = bi.f.A / 2 + 0.2; const x = Math.max(-hx, Math.min(hx, l.x)), z = Math.max(-hz, Math.min(hz, l.z)); const q = Math.abs(Math.abs(x) - hx) < Math.abs(Math.abs(z) - hz) ? V3(Math.sign(x || 1) * hx, 0, z) : V3(x, 0, Math.sign(z || 1) * hz); return q.applyMatrix4(bi.f.m); } };
  }
  const invInfo = ad.inversores ? inverters(P, ad.inversores, V, detail) : null;
  const evPt = ad.cargador_ve?.centro ? charger(P, ad.cargador_ve, detail) : null;
  let cx = null;
  try { cx = conexion(spec, P, V, arrays, invInfo, bessInfo, evPt, detail); } catch (e) { warn.push(`${spec.id}/conexión: ${e.message}`); }
  ringsOut(P, (vi) => estadoDe(vi.v) === 'nuevo');
  tarde.forEach((f) => f());
  if (!P.bess.empty) b.node('almacenamiento', b.partMesh(`${spec.id}_bess`, P.bess), [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);
  if (!P.equip.empty) b.node('equipos', b.partMesh(`${spec.id}_equipos`, P.equip), [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);
  if (cx) {
    const r3 = (p) => p.toArray().map((x) => +x.toFixed(2));
    const cnode = b.node('conexion', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);
    cnode.setExtras({ capa: 'adecuaciones', nota: cx.nota, red: cx.poste ? 'poste' : 'fachada', colores: { potencia: COLOR.potencia, datos: COLOR.datos }, tablero: r3(cx.tablero), gateway: r3(cx.gateway), punto_red: r3(cx.red) });
    for (const [name, part] of [['ruta_potencia', P.pow], ['ruta_datos', P.dat], ['punto_conexion', P.punto], ['gateway', P.gw]]) if (!part.empty) b.node(name, b.partMesh(`${spec.id}_${name}`, part), [0, 0, 0], [0, 0, 0], [1, 1, 1], cnode);
    cx.out = { tablero: r3(cx.tablero), gateway: r3(cx.gateway), red: r3(cx.red), nota: cx.nota };
  }

  // tamaño (para encuadrar) a partir del predio
  const size = xs.length ? [Math.max(...xs) - Math.min(...xs) + 4, Math.max(...vols.map((v) => (v.eave ?? 3) + 3), 4), Math.max(...ys) - Math.min(...ys) + 4] : [20, 8, 20];
  return { b, modules, size, conexion: cx?.out ?? null };
}

// ---------- ejecución
const args = process.argv.slice(2), compress = !args.includes('--sin-comprimir');
const only = args.filter((a) => !a.startsWith('--'));
const files = readdirSync(DATA).filter((f) => f.endsWith('.json')).filter((f) => !only.length || only.includes(f.replace(/\.json$/, '')));
const manPath = new URL('manifest.json', OUT);
const manifest = existsSync(manPath) ? JSON.parse(readFileSync(manPath)) : [];
const gmaps = (s) => (s.pano ? `https://www.google.com/maps/@?api=1&map_action=pano&pano=${encodeURIComponent(s.pano)}${s.rumbo != null ? `&heading=${Math.round(s.rumbo)}` : ''}` : s.url || null);
for (const file of files) {
  let spec;
  try { spec = JSON.parse(readFileSync(new URL(file, DATA))); } catch (e) { console.error(`✗ ${file}: JSON inválido (${e.message})`); continue; }
  if (!spec.id || !spec.volumenes?.length) { console.error(`✗ ${file}: sin id o sin volúmenes`); continue; }
  // levantamientos que otra especificación reemplazó (por ejemplo, alas que se demuelen para una obra nueva): no se dibujan
  if (spec.reemplazado_por) { const k = manifest.findIndex((x) => x.id === spec.id); if (k >= 0) manifest.splice(k, 1); console.log(`${spec.id}: reemplazado por ${spec.reemplazado_por}, no se dibuja`); continue; }
  const before = warn.length;
  const hi = build(spec, true), m0 = await writeGLB(hi.b, OUT, `${spec.id}_lod0`, { compress, instance: false });
  const lo = build(spec, false), m1 = await writeGLB(lo.b, OUT, `${spec.id}_lod1`, { compress, instance: false });
  const kwp = +(hi.modules * MOD.kwp).toFixed(2), ad = spec.adecuaciones || {};
  if (ad.kwp_factible != null && Math.abs(ad.kwp_factible - kwp) > 1) warn.push(`${spec.id}: kwp_factible declarado ${ad.kwp_factible} ≠ módulos modelados ${hi.modules} × 0,55 = ${kwp}`);
  const entry = {
    id: spec.id, nombre: spec.nombre, nodo_microrred: spec.nodo_microrred ?? null, lat: spec.lat, lon: spec.lon,
    archivo: `models/edificios/${spec.id}_lod0.glb`, archivo_lod1: `models/edificios/${spec.id}_lod1.glb`,
    bytes: m0.bytes, bytes_lod1: m1.bytes, bytes_sin_comprimir: m0.bytes_sin_comprimir, triangulos: m0.triangulos_fuente, triangulos_lod1: m1.triangulos_fuente,
    extensiones: m0.extensiones, nodos_instanciados: m0.nodos_instanciados, tamano: hi.size.map((x) => +x.toFixed(1)),
    modulos: hi.modules, kwp_modelado: kwp, kwp_plan: ad.kwp_plan ?? null, kwp_factible: ad.kwp_factible ?? kwp,
    bess: ad.bess ? { kwh: ad.bess.kwh, kw: ad.bess.kw, tipo: ad.bess.tipo } : null,
    // puntos para etiquetar la conexión en la web (metros, marco del GLB: x este, y arriba, z sur)
    conexion: hi.conexion,
    confianza: spec.ubicacion?.confianza ?? null,
    fuentes: (spec.fuentes || []).map((s) => ({ tipo: s.tipo, fecha: s.fecha ?? null, nota: s.nota ?? null, url: gmaps(s) })).filter((s) => s.url || s.tipo === 'satelite'),
  };
  const i = manifest.findIndex((x) => x.id === spec.id); if (i >= 0) manifest[i] = entry; else manifest.push(entry);
  console.log(`${spec.id}: ${(m0.bytes / 1024).toFixed(0)} KB (lod1 ${(m1.bytes / 1024).toFixed(0)} KB) · ${m0.triangulos_fuente} triángulos (lod1 ${m1.triangulos_fuente}) · ${hi.modules} módulos = ${kwp} kWp${warn.length > before ? ' · avisos: ' + (warn.length - before) : ''}`);
}
manifest.sort((a, b) => a.id.localeCompare(b.id));
writeFileSync(manPath, JSON.stringify(manifest, null, 1));
if (warn.length) { console.warn('\nAvisos:'); warn.forEach((w) => console.warn(' · ' + w)); }
