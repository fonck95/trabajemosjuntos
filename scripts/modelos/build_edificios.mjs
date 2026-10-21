// Réplicas 3D de las dependencias públicas de Yondó a partir de data/edificios/<id>.json
// (levantamiento con satélite, Street View y fotos; formato en data/edificios/ESPECIFICACION.md).
// Cada GLB tiene dos capas: "existente" (el edificio real) y "adecuaciones" (solar, baterías,
// equipos y cubierta nueva del proyecto de microrred), para mostrar el antes y el después.
// Salida: web/models/edificios/<id>_lod0.glb (detalle) y <id>_lod1.glb (lejos) + manifest.json
//
// Uso: cd scripts/modelos && node build_edificios.mjs [id ...] [--sin-comprimir]
import { THREE, Part, Builder, baseMaterials, pvMesh, bessPart, writeGLB, instanced, TEX, MOD } from './lib.mjs';
import { FontLoader } from 'three/examples/jsm/loaders/FontLoader.js';
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs';

import { pathToFileURL } from 'node:url';
const dirURL = (env, rel) => (process.env[env] ? pathToFileURL(process.env[env].replace(/\/?$/, '/')) : new URL(rel, import.meta.url));
const DATA = dirURL('EDIFICIOS_DIR', '../../data/edificios/');
const OUT = dirURL('EDIFICIOS_OUT', '../../web/models/edificios/');
const font = new FontLoader().parse(JSON.parse(readFileSync(new URL('./node_modules/three/examples/fonts/helvetiker_bold.typeface.json', import.meta.url))));
const D2R = Math.PI / 180;
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const UP = V3(0, 1, 0);
const CARD = { N: [0, 1], S: [0, -1], E: [1, 0], O: [-1, 0], W: [-1, 0] };
const warn = [];

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
  return { m, L, A, th, sides };
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

// ---------- texto en relieve con tildes compuestas (la fuente no trae Á, Í, Ñ…)
function textGeo(text, size, depth = 0.04) {
  const data = font.data, sc = size / data.resolution, cap = 0.72 * size;
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
      else if (m === '̃' && data.glyphs['~']) ext(font.generateShapes('~', size * 0.9), cx - (data.glyphs['~'].ha * sc * 0.9) / 2, cap - 0.18 * size);
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

// ---------- materiales dependientes del edificio
const ROOF_TEX = { zinc: TEX.zinc, fibrocemento: TEX.fibrocemento, termoacustica: TEX.termoacustica, teja_barro: TEX.teja, concreto: TEX.concreto, policarbonato: null };
const ROOF_DEF = { zinc: '#9aa1a6', fibrocemento: '#9b9d98', termoacustica: '#e9e7e1', teja_barro: '#a5512f', concreto: '#b9b6ad', policarbonato: '#d6e2e8' };
const WALL_TEX = { ladrillo_visto: TEX.ladrillo, bloque: TEX.bloque, metal: TEX.zinc };
const hexOK = (c, d) => (typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c) ? c.toLowerCase() : d);
function roofMat(b, t) {
  const material = ROOF_TEX[t?.material] !== undefined ? t.material : 'zinc';
  const color = hexOK(t?.color, ROOF_DEF[material]);
  const key = `techo_${material}_${color.slice(1)}`;
  b.mat(key, { color, rough: material === 'zinc' ? 0.5 : material === 'policarbonato' ? 0.2 : 0.85, metal: material === 'zinc' ? 0.55 : material === 'termoacustica' ? 0.2 : 0, tex: ROOF_TEX[material] || undefined, doubleSided: true, opacity: material === 'policarbonato' ? 0.75 : 1 });
  return key;
}
function wallMat(b, fa) {
  const material = fa?.material || 'pañete_pintado';
  const color = hexOK(fa?.color, material === 'ladrillo_visto' ? '#b4583c' : '#efece4');
  const key = `muro_${material === 'pañete_pintado' ? 'p' : material}_${color.slice(1)}`;
  b.mat(key, { color, rough: material === 'vidrio' ? 0.1 : material === 'metal' ? 0.45 : 0.9, metal: material === 'metal' ? 0.5 : 0, tex: WALL_TEX[material] });
  return key;
}
function colorMat(b, prefix, color, opts = {}) { const c = hexOK(color, '#888888'); const key = `${prefix}_${c.slice(1)}`; b.mat(key, { color: c, rough: 0.85, ...opts }); return key; }
function extraMaterials(b) {
  b.mat('marco', { color: '#d9dcdc', rough: 0.4, metal: 0.6 });
  b.mat('puerta', { color: '#4a3a2e', rough: 0.7 });
  b.mat('puerta_metal', { color: '#5d6a73', rough: 0.45, metal: 0.6 });
  b.mat('celosia', { color: '#ffffff', rough: 0.9, tex: TEX.celosia });
  b.mat('reja_vidrio', { color: '#ffffff', rough: 0.3, metal: 0.3, tex: TEX.reja });
  b.mat('tronco', { color: '#6b5544', rough: 0.95 });
  b.mat('copa', { color: '#4e7a37', rough: 0.95 });
  b.mat('copa2', { color: '#3f6a31', rough: 0.95 });
  b.mat('pasto', { color: '#6f9450', rough: 1, tex: TEX.pasto });
  b.mat('asfalto', { color: '#5f6366', rough: 0.95, tex: TEX.asfalto });
  b.mat('piso', { color: '#cfcbc2', rough: 0.95, tex: TEX.concreto });
  b.mat('predio', { color: '#d7d3c8', rough: 1 });
  b.mat('linea', { color: '#f5f5f0', rough: 0.8 });
  b.mat('tanque', { color: '#d8dcdf', rough: 0.6 });
  b.mat('bandera_am', { color: '#fcd116', rough: 0.8, doubleSided: true });
  b.mat('bandera_az', { color: '#003893', rough: 0.8, doubleSided: true });
  b.mat('bandera_ro', { color: '#ce1126', rough: 0.8, doubleSided: true });
  b.mat('equipo', { color: '#eceeee', rough: 0.5 });
  b.mat('ducto', { color: '#9aa0a4', rough: 0.5, metal: 0.4 });
  b.mat('verde_ve', { color: '#18a957', rough: 0.4, emissive: '#0a4d27' });
  b.mat('gabinete', { color: '#f2f3f3', rough: 0.45, metal: 0.2 });
  b.mat('gabinete_franja', { color: '#e3141b', rough: 0.5 });
  b.mat('pintura_ve', { color: '#18a957', rough: 0.8 });
}

// ---------- cubiertas (coordenadas locales del volumen; devuelven caras para los paneles)
// Dos aguas con cumbrera a lo largo de x (largo W) y luz D; si la cumbrera va por el lado corto se gira 90°.
function gable(W, D, eave, t, roof, walls, wallKey, roofKey, rot) {
  const p = (t.pendiente ?? 15) * D2R, v = t.voladizo ?? 0.6, vx = Math.min(v, 0.5), s = D / 2, ro = s + v;
  const yR = eave + s * Math.tan(p), yE = eave - v * Math.tan(p), X = W / 2 + vx;
  const R = (g) => (rot ? g.applyMatrix4(rot) : g);
  const faces = [];
  for (const sg of [1, -1]) {
    const pts = [V3(-X, yR, 0), V3(X, yR, 0), V3(X, yE, sg * ro), V3(-X, yE, sg * ro)];
    const vd = V3(0, -Math.sin(p), sg * Math.cos(p));
    roof.addRaw(roofKey, R(polyGeo(pts, V3(0, Math.cos(p), sg * Math.sin(p)), V3(1, 0, 0), vd)), true);
    // cara útil (sobre el muro, sin alero) para el arreglo solar
    faces.push(face([V3(-W / 2, yR, 0), V3(W / 2, yR, 0), V3(W / 2, eave, sg * s), V3(-W / 2, eave, sg * s)], V3(0, Math.cos(p), sg * Math.sin(p)), V3(1, 0, 0), vd, rot));
    // tapa del alero y cumbrera
    roof.addRaw(roofKey, R(boxG(2 * X, 0.18, 0.03, 0, yE - 0.18, sg * ro)), true);
  }
  roof.addRaw(roofKey, R(boxG(2 * X, 0.07, 0.34, 0, yR - 0.01, 0)), true);
  for (const sx of [1, -1]) {
    walls.addRaw(wallKey, R(polyGeo([V3(sx * W / 2, eave, -s), V3(sx * W / 2, eave, s), V3(sx * W / 2, yR, 0)], V3(sx, 0, 0))), true);
    // tablas de borde inclinadas en los hastiales
    for (const sg of [1, -1]) roof.addRaw(roofKey, R(polyGeo([V3(sx * X, yR + 0.02, 0), V3(sx * X, yE + 0.02, sg * ro), V3(sx * X, yE - 0.16, sg * ro), V3(sx * X, yR - 0.16, 0)], V3(sx, 0, 0))), true);
  }
  return faces;
}
function hip(W, D, eave, t, roof, roofKey, rot) {
  const p = (t.pendiente ?? 15) * D2R, v = t.voladizo ?? 0.6;
  const Wp = W + 2 * v, Dp = D + 2 * v, yE = eave - v * Math.tan(p);
  const R = (g) => (rot ? g.applyMatrix4(rot) : g);
  const faces = [];
  if (Wp >= Dp) {
    const r = (Wp - Dp) / 2, yR = yE + (Dp / 2) * Math.tan(p);
    for (const sg of [1, -1]) {
      const n = V3(0, Math.cos(p), sg * Math.sin(p)), vd = V3(0, -Math.sin(p), sg * Math.cos(p));
      roof.addRaw(roofKey, R(polyGeo([V3(-Wp / 2, yE, sg * Dp / 2), V3(Wp / 2, yE, sg * Dp / 2), V3(r, yR, 0), V3(-r, yR, 0)], n, V3(1, 0, 0), vd)), true);
      const rr = Math.max(0, (W - D) / 2), yr = eave + (D / 2) * Math.tan(p);
      faces.push(face([V3(-W / 2, eave, sg * D / 2), V3(W / 2, eave, sg * D / 2), V3(rr, yr, 0), V3(-rr, yr, 0)], n, V3(1, 0, 0), vd, rot));
      const nx = V3(sg * Math.sin(p), Math.cos(p), 0), vdx = V3(sg * Math.cos(p), -Math.sin(p), 0);
      roof.addRaw(roofKey, R(polyGeo([V3(sg * Wp / 2, yE, -Dp / 2), V3(sg * Wp / 2, yE, Dp / 2), V3(sg * r, yR, 0)], nx, V3(0, 0, 1), vdx)), true);
      faces.push(face([V3(sg * W / 2, eave, -D / 2), V3(sg * W / 2, eave, D / 2), V3(sg * rr, yr, 0)], nx, V3(0, 0, 1), vdx, rot));
    }
    roof.addRaw(roofKey, R(boxG(Math.max(0.3, 2 * r), 0.07, 0.3, 0, yR - 0.01, 0)), true);
  } else {
    const rot90 = new THREE.Matrix4().makeRotationY(Math.PI / 2);
    return hip(D, W, eave, t, roof, roofKey, rot ? rot.clone().multiply(rot90) : rot90);
  }
  for (const [w, d, x, z] of [[Wp, 0.03, 0, Dp / 2], [Wp, 0.03, 0, -Dp / 2], [0.03, Dp, Wp / 2, 0], [0.03, Dp, -Wp / 2, 0]]) roof.addRaw(roofKey, R(boxG(w, 0.18, d, x, yE - 0.18, z)), true);
  return faces;
}
// Una agua: cae hacia +z en el marco (W a lo largo, D en la dirección de la pendiente)
function shed(W, D, eave, t, roof, walls, wallKey, roofKey, rot) {
  const p = (t.pendiente ?? 10) * D2R, v = t.voladizo ?? 0.6, rise = D * Math.tan(p);
  const R = (g) => (rot ? g.applyMatrix4(rot) : g);
  const yHi = eave + rise + v * Math.tan(p), yLo = eave - v * Math.tan(p), X = W / 2 + v;
  const n = V3(0, Math.cos(p), Math.sin(p)), vd = V3(0, -Math.sin(p), Math.cos(p));
  roof.addRaw(roofKey, R(polyGeo([V3(-X, yHi, -D / 2 - v), V3(X, yHi, -D / 2 - v), V3(X, yLo, D / 2 + v), V3(-X, yLo, D / 2 + v)], n, V3(1, 0, 0), vd)), true);
  for (const z of [D / 2 + v, -D / 2 - v]) roof.addRaw(roofKey, R(boxG(2 * X, 0.18, 0.03, 0, (z > 0 ? yLo : yHi) - 0.18, z)), true);
  for (const sx of [1, -1]) walls.addRaw(wallKey, R(polyGeo([V3(sx * W / 2, eave, -D / 2), V3(sx * W / 2, eave, D / 2), V3(sx * W / 2, eave + rise, -D / 2)], V3(sx, 0, 0))), true);
  walls.addRaw(wallKey, R(polyGeo([V3(-W / 2, eave, -D / 2), V3(W / 2, eave, -D / 2), V3(W / 2, eave + rise, -D / 2), V3(-W / 2, eave + rise, -D / 2)], V3(0, 0, -1))), true);
  return [face([V3(-W / 2, eave + rise, -D / 2), V3(W / 2, eave + rise, -D / 2), V3(W / 2, eave, D / 2), V3(-W / 2, eave, D / 2)], n, V3(1, 0, 0), vd, rot)];
}
// Bóveda (cubierta curva) de luz D a lo largo de x
function vault(W, D, eave, t, roof, walls, wallKey, roofKey, rot) {
  const f = Math.max(0.3, t.flecha ?? D * 0.12), v = t.voladizo ?? 0.4, X = W / 2 + v;
  const Rr = ((D / 2) ** 2 + f ** 2) / (2 * f), yc = eave + f - Rr, N = 18;
  const R = (g) => (rot ? g.applyMatrix4(rot) : g);
  const arc = (z) => yc + Math.sqrt(Math.max(0, Rr * Rr - z * z));
  const a = [], bb = [];
  for (let i = 0; i <= N; i++) { const z = -D / 2 - 0.25 + ((D + 0.5) * i) / N; a.push(V3(-X, arc(z), z)); bb.push(V3(X, arc(z), z)); }
  roof.addRaw(roofKey, R(stripGeo(a, bb, (q) => V3(0, q.y - yc, q.z))), true);
  for (const sx of [1, -1]) {
    const pts = [V3(sx * W / 2, eave, -D / 2)];
    for (let i = 0; i <= N; i++) { const z = -D / 2 + (D * i) / N; pts.push(V3(sx * W / 2, arc(z), z)); }
    pts.push(V3(sx * W / 2, eave, D / 2));
    walls.addRaw(wallKey, R(polyGeo(pts, V3(sx, 0, 0))), true);
  }
  // caras para paneles: cada mitad de la bóveda se describe como arco
  return [1, -1].map((sg) => ({ arc: true, sg, W, D, yc, Rr, rot, n: (rot ? V3(0, 0, sg).applyMatrix4(new THREE.Matrix4().extractRotation(rot)) : V3(0, 0, sg)) }));
}
function flat(W, D, eave, t, roof, walls, wallKey, roofKey, rot) {
  const pp = t.parapeto ?? 0.6;
  const R = (g) => (rot ? g.applyMatrix4(rot) : g);
  roof.addRaw(roofKey, R(polyGeo([V3(-W / 2, eave + 0.02, -D / 2), V3(W / 2, eave + 0.02, -D / 2), V3(W / 2, eave + 0.02, D / 2), V3(-W / 2, eave + 0.02, D / 2)], UP, V3(1, 0, 0), V3(0, 0, 1))), true);
  if (pp > 0) for (const [w, d, x, z] of [[W + 0.3, 0.15, 0, D / 2], [W + 0.3, 0.15, 0, -D / 2], [0.15, D, W / 2, 0], [0.15, D, -W / 2, 0]]) walls.addRaw(wallKey, R(boxG(w, pp, d, x, eave, z)), true);
  return [{ flat: true, W, D, y: eave + 0.02, rot }];
}
// cara plana útil para FV: centroide, base ortonormal (u a lo largo, vd pendiente abajo, n normal) en coordenadas locales del volumen
function face(pts, n, u, vd, rot) {
  const P = rot ? pts.map((q) => q.clone().applyMatrix4(rot)) : pts;
  const r3 = rot ? new THREE.Matrix4().extractRotation(rot) : null;
  const tr = (d) => (r3 ? d.clone().applyMatrix4(r3) : d.clone());
  const c = P.reduce((a, q) => a.add(q), V3(0, 0, 0)).multiplyScalar(1 / P.length);
  return { pts: P, c, n: tr(n).normalize(), u: tr(u).normalize(), vd: tr(vd).normalize() };
}

// ---------- volumen: muros, ventanas, puertas, zócalo, entrepisos, corredor, letrero, cubierta
function volume(b, v, P, detail) {
  const abierto = !!v.abierto;
  const f = frame(v), base = v.base ?? 0, eave = Math.max(base + (abierto ? 0.4 : 2.2), v.altura_alero ?? base + 3.2) - base;
  const fa = v.fachada || {}, t = v.techo || { tipo: 'plano' };
  const wk = wallMat(b, fa);
  const L = f.L, A = f.A, pisos = Math.max(1, v.pisos ?? 1), hf = eave / pisos;
  const W = P.walls, M = (g, m) => g.applyMatrix4(m);
  if (abierto) {
    // pórtico, corredor o kiosco: columnas en el perímetro (cada ~3,5 m) y viga de amarre bajo la cubierta
    const sep = v.sep_columnas ?? 3.5, cs = v.columna ?? 0.25;
    const nL = Math.max(1, Math.round(L / sep)), nA = Math.max(1, Math.round(A / sep));
    const pts = new Set();
    for (let i = 0; i <= nL; i++) for (const z of [-A / 2, A / 2]) pts.add(`${(-L / 2 + (i * L) / nL).toFixed(2)},${z.toFixed(2)}`);
    for (let j = 0; j <= nA; j++) for (const x of [-L / 2, L / 2]) pts.add(`${x.toFixed(2)},${(-A / 2 + (j * A) / nA).toFixed(2)}`);
    for (const k of pts) { const [x, z] = k.split(',').map(Number); W.addRaw(wk, M(boxG(cs, eave, cs, x - Math.sign(x) * cs / 2, 0, z - Math.sign(z) * cs / 2), f.m)); }
    for (const [w, d, x, z] of [[L, 0.2, 0, A / 2 - 0.1], [L, 0.2, 0, -A / 2 + 0.1], [0.2, A, L / 2 - 0.1, 0], [0.2, A, -L / 2 + 0.1, 0]]) W.addRaw(wk, M(boxG(w, 0.3, d, x, eave - 0.3, z), f.m));
    if (v.piso !== false && base === 0) W.addRaw('piso', M(boxG(L, 0.12, A), f.m));
  }
  // muros con UV en metros
  if (!abierto) for (const [s, S] of Object.entries(f.sides)) {
    const c = S.n.clone().multiplyScalar(S.half), l = c.clone().addScaledVector(S.t, -S.len / 2), r = c.clone().addScaledVector(S.t, S.len / 2);
    W.addRaw(wk, M(polyGeo([l, r, r.clone().setY(eave), l.clone().setY(eave)], S.n, S.t, V3(0, 1, 0)), f.m), true);
  }
  if (t.tipo === 'ninguno') W.addRaw(wk, M(boxG(L, 0.15, A, 0, eave - 0.15, 0), f.m), true);
  // zócalo y bandas de entrepiso
  if (fa.zocalo && !abierto) { const zk = colorMat(b, 'zocalo', fa.zocalo.color); for (const s of Object.keys(f.sides)) P.walls.addRaw(zk, M(boxG(f.sides[s].len + 0.04, fa.zocalo.altura ?? 0.8, 0.03), sideMatrix(f, s, 0, 0, 0.015))); }
  const bandK = colorMat(b, 'banda', '#' + new THREE.Color(hexOK(fa.color, '#efece4')).multiplyScalar(0.86).getHexString());
  for (let k = 1; k < pisos; k++) for (const s of Object.keys(f.sides)) P.walls.addRaw(bandK, M(boxG(f.sides[s].len + 0.24, 0.2, 0.12), sideMatrix(f, s, 0, k * hf - 0.1, 0.06)));
  // puertas
  const doors = {};
  for (const d of fa.puertas || []) {
    const s = sideFor(f, d.lado), S = f.sides[s], w = d.ancho ?? 1.8, h = d.alto ?? 2.4, along = ((d.pos ?? 0.5) - 0.5) * S.len;
    (doors[s] ||= []).push([along - w / 2 - 0.4, along + w / 2 + 0.4]);
    const m = sideMatrix(f, s, along, 0, 0);
    P.walls.addRaw(w > 2.6 ? 'puerta_metal' : 'puerta', M(boxG(w, h, 0.06, 0, 0, 0.02), m));
    if (detail) for (const [ww, hh, x, y] of [[w + 0.24, 0.12, 0, h], [0.12, h, -w / 2 - 0.06, 0], [0.12, h, w / 2 + 0.06, 0]]) P.walls.addRaw('marco', M(boxG(ww, hh, 0.1, x, y, 0.04), m));
  }
  // ventanas por piso
  const vn = abierto ? null : fa.ventanas;
  if (vn) {
    const ww = vn.ancho ?? 1.4, wh = vn.alto ?? 1.2, sill = vn.antepecho ?? 1.0, sep = Math.max(ww + 0.4, vn.separacion ?? 3);
    const tipo = vn.tipo || 'ventana';
    const glass = tipo === 'celosia' || tipo === 'calado' ? 'celosia' : tipo === 'reja' ? 'reja_vidrio' : 'vidrio';
    for (const s of sidesOf(f, vn.lados)) {
      const S = f.sides[s], n = Math.max(0, Math.floor((S.len - 1.2 - ww) / sep) + 1);
      for (let k = 0; k < pisos; k++) {
        const y = k * hf + (tipo === 'vitrina' ? 0.25 : sill), h = tipo === 'vitrina' ? Math.min(hf - 0.6, 2.6) : Math.min(wh, hf - sill - 0.25);
        if (h < 0.3) continue;
        for (let i = 0; i < n; i++) {
          const along = (i - (n - 1) / 2) * sep;
          if (k === 0 && (doors[s] || []).some(([a0, a1]) => along + ww / 2 > a0 && along - ww / 2 < a1)) continue;
          const m = sideMatrix(f, s, along, y, 0);
          P.walls.addRaw(glass, M(boxG(ww, h, 0.05, 0, 0, 0.02), m), glass !== 'vidrio');
          if (detail && glass !== 'celosia') {
            for (const [a, bh, x, yy] of [[ww + 0.12, 0.06, 0, -0.06], [ww + 0.12, 0.06, 0, h], [0.06, h, -ww / 2 - 0.03, 0], [0.06, h, ww / 2 + 0.03, 0]]) P.walls.addRaw('marco', M(boxG(a, bh, 0.07, x, yy, 0.04), m));
            if (ww > 1.1) P.walls.addRaw('marco', M(boxG(0.04, h, 0.05, 0, 0, 0.05), m));
            P.walls.addRaw(bandK, M(boxG(ww + 0.25, 0.06, 0.16, 0, -0.12, 0.06), m));
          }
        }
      }
    }
  }
  // corredor con columnas
  const co = fa.corredor;
  if (co) {
    const s = sideFor(f, co.lado), S = f.sides[s], d = co.profundidad ?? 2.4, sep = co.sep_columnas ?? 3.5, len = S.len;
    const yTop = (pisos > 1 ? hf : eave) - 0.05;
    P.walls.addRaw('piso', M(boxG(len, 0.15, d, 0, 0, d / 2), sideMatrix(f, s, 0, 0, 0)));
    const nC = Math.max(2, Math.round(len / sep) + 1);
    for (let i = 0; i < nC; i++) P.walls.addRaw(wk, M(boxG(0.25, yTop - 0.15, 0.25, -len / 2 + 0.2 + (i * (len - 0.4)) / (nC - 1), 0.15, d - 0.2), sideMatrix(f, s, 0, 0, 0)));
    const rk = t.tipo === 'ninguno' || t.tipo === 'plano' ? roofMat(b, { material: 'concreto' }) : roofMat(b, t);
    const drop = (d + 0.3) * Math.tan(8 * D2R);
    P.roofKeep.addRaw(rk, M(polyGeo([V3(-len / 2 - 0.2, yTop + 0.15, 0), V3(len / 2 + 0.2, yTop + 0.15, 0), V3(len / 2 + 0.2, yTop + 0.15 - drop, d + 0.3), V3(-len / 2 - 0.2, yTop + 0.15 - drop, d + 0.3)], UP, V3(1, 0, 0), V3(0, 0, 1)), sideMatrix(f, s, 0, 0, 0)), true);
  }
  // letrero
  const le = fa.letrero;
  if (le?.texto) {
    const s = sideFor(f, le.lado), S = f.sides[s], chars = le.texto.length;
    const size = Math.max(0.18, Math.min(0.55, (S.len * 0.8) / Math.max(1, chars * 0.68)));
    const tg = textGeo(le.texto, size, 0.04);
    if (tg) {
      const along = doors[s]?.length ? (doors[s][0][0] + doors[s][0][1]) / 2 : 0;
      const top = (pisos > 1 ? hf : eave) - size - 0.12, doorTop = Math.max(0, ...(fa.puertas || []).filter((d) => sideFor(f, d.lado) === s).map((d) => d.alto ?? 2.4));
      const y = Math.min(top, Math.max(doorTop + 0.25, (pisos > 1 ? hf : eave) - size - 0.35));
      P.walls.addRaw(colorMat(b, 'letrero', le.color || '#1b3d7a', { rough: 0.5 }), M(tg, sideMatrix(f, s, along, y, 0.03)));
    }
  }
  // cubierta
  const ry = new THREE.Matrix4().makeRotationY(Math.PI / 2);
  const along = t.cumbrera !== 'corto';
  const roofParts = (roofPart, mat) => {
    const geoWalls = P.walls, rk = mat;
    if (t.tipo === 'dos_aguas') return along ? gable(L, A, eave, t, roofPart, geoWalls, wk, rk) : gable(A, L, eave, t, roofPart, geoWalls, wk, rk, ry);
    if (t.tipo === 'cuatro_aguas') return hip(L, A, eave, t, roofPart, rk);
    if (t.tipo === 'una_agua') {
      const s = sideFor(f, t.caida || 'S');
      const rot = { '+Z': null, '-Z': new THREE.Matrix4().makeRotationY(Math.PI), '+X': ry, '-X': new THREE.Matrix4().makeRotationY(-Math.PI / 2) }[s];
      return s === '+Z' || s === '-Z' ? shed(L, A, eave, t, roofPart, geoWalls, wk, rk, rot) : shed(A, L, eave, t, roofPart, geoWalls, wk, rk, rot);
    }
    if (t.tipo === 'curvo') return along ? vault(L, A, eave, t, roofPart, geoWalls, wk, rk) : vault(A, L, eave, t, roofPart, geoWalls, wk, rk, ry);
    if (t.tipo === 'plano') return flat(L, A, eave, t, roofPart, geoWalls, wk, rk);
    return [];
  };
  // las caras se generan en coordenadas locales; se agregan aplicando el marco del volumen
  const local = { walls: new Part(), roof: new Part() };
  const PW = P.walls; P.walls = local.walls;
  const faces = roofParts(local.roof, roofMat(b, t));
  const replaced = !!(P.newRoof && P.replace(v));
  if (replaced) { const nr = new Part(); P.walls = new Part(); roofParts(nr, roofMat(b, P.newRoofSpec(t))); mergeInto(P.newRoof, nr, f.m); }
  P.walls = PW;
  mergeInto(P.walls, local.walls, f.m);
  mergeInto(replaced ? P.roof : P.roofKeep, local.roof, f.m);
  return { f, faces: (faces || []).map((q) => ({ ...q, m: f.m })), eave, base };
}
function mergeInto(dst, src, m) { for (const [k, gs] of src.byMat) for (const g of gs) dst.addRaw(k, g.applyMatrix4(m), !!g.attributes.uv); }
function volumePoly(b, v, P) {
  const fa = v.fachada || {}, wk = wallMat(b, fa), base = v.base ?? 0, h = Math.max(0.3, (v.altura_alero ?? 3) - base);
  const shape = new THREE.Shape(v.poligono.map(([x, y]) => new THREE.Vector2(x, y)));
  const g = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false }); g.rotateX(-Math.PI / 2); g.translate(0, base, 0);
  P.walls.addRaw(wk, g.index ? g.toNonIndexed() : g, true);
  if ((v.techo?.tipo ?? 'plano') === 'plano' && (v.techo?.parapeto ?? 0.5) > 0) {
    const pts = v.poligono, pp = v.techo?.parapeto ?? 0.5;
    for (let i = 0; i < pts.length; i++) {
      const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length], len = Math.hypot(x1 - x0, y1 - y0);
      const m = new THREE.Matrix4().compose(V3((x0 + x1) / 2, base + h, -(y0 + y1) / 2), new THREE.Quaternion().setFromAxisAngle(UP, Math.atan2(y1 - y0, x1 - x0)), V3(1, 1, 1));
      P.walls.addRaw(wk, boxG(len + 0.15, pp, 0.15).applyMatrix4(m), true);
    }
  }
  return { faces: [], eave: base + h, base };
}

// ---------- elementos del entorno
const planToThree = ([x, y], yy = 0) => V3(x, yy, -y);
function rectOrPoly(o) {
  if (o.poligono) return o.poligono;
  if (o.centro && o.largo) { const f = frame(o); return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, c]) => { const p = V3(a * f.L / 2, 0, c * f.A / 2).applyMatrix4(f.m); return [p.x, -p.z]; }); }
  return null;
}
function flatPoly(P, mat, pts, y) {
  const shape = new THREE.Shape(pts.map(([x, yy]) => new THREE.Vector2(x, yy)));
  const g = new THREE.ShapeGeometry(shape); g.rotateX(-Math.PI / 2); g.translate(0, y, 0);
  const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, g.attributes.position.getX(i) / 2, g.attributes.position.getZ(i) / 2);
  P.addRaw(mat, g, true);
}
function element(b, e, P, detail, tree) {
  const at = (o = e) => (o.centro ? planToThree(o.centro) : V3(0, 0, 0));
  switch (e.tipo) {
    case 'cerramiento': {
      const pts = e.poligono || e.linea; if (!pts || pts.length < 2) return;
      const closed = !!e.poligono && !e.abierto, h = e.altura ?? 2, mat = e.material || 'muro';
      const wk = colorMat(b, 'cerca', e.color || (mat === 'muro' ? '#e6e2d8' : '#3a3f44'), { metal: mat === 'muro' ? 0 : 0.5 });
      const n = closed ? pts.length : pts.length - 1;
      for (let i = 0; i < n; i++) {
        const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length], len = Math.hypot(x1 - x0, y1 - y0); if (len < 0.05) continue;
        const m = new THREE.Matrix4().compose(V3((x0 + x1) / 2, 0, -(y0 + y1) / 2), new THREE.Quaternion().setFromAxisAngle(UP, Math.atan2(y1 - y0, x1 - x0)), V3(1, 1, 1));
        if (mat === 'muro') { P.env.addRaw(wk, boxG(len, h, 0.15).applyMatrix4(m)); P.env.addRaw(wk, boxG(len, 0.08, 0.22, 0, h, 0).applyMatrix4(m)); continue; }
        P.env.addRaw('piso', boxG(len, 0.4, 0.18).applyMatrix4(m));
        const k = Math.max(1, Math.round(len / 2.5));
        for (let j = 0; j <= k; j++) P.env.addRaw(wk, boxG(0.08, h, 0.08, -len / 2 + (j * len) / k, 0, 0).applyMatrix4(m));
        P.env.addRaw(wk, boxG(len, 0.05, 0.05, 0, h - 0.1, 0).applyMatrix4(m));
        if (detail) { const nb = Math.round(len / 0.14); for (let j = 0; j < nb; j++) P.env.addRaw(wk, boxG(0.02, h - 0.5, 0.02, -len / 2 + (j + 0.5) * (len / nb), 0.4, 0).applyMatrix4(m)); }
        else P.env.addRaw(wk, boxG(len, h - 0.5, 0.01, 0, 0.4, 0).applyMatrix4(m));
      }
      return;
    }
    case 'tanque_elevado': {
      const c = at(), H = e.altura ?? 12, d = e.diametro ?? 4, th = Math.min(d * 0.9, H * 0.35);
      P.env.add('concreto', new THREE.CylinderGeometry(Math.max(0.5, d * 0.18), Math.max(0.6, d * 0.22), H - th, 16), [c.x, (H - th) / 2, c.z]);
      P.env.add('tanque', new THREE.CylinderGeometry(d / 2, d / 2.6, th, 28), [c.x, H - th / 2, c.z]);
      P.env.add('tanque', new THREE.ConeGeometry(d / 2 + 0.05, d * 0.18, 28), [c.x, H + d * 0.09, c.z]);
      return;
    }
    case 'arbol': {
      const c = at(), H = e.altura ?? 8, cp = e.copa ?? H * 0.7;
      tree.push({ c, H, cp }); return;
    }
    case 'cancha': {
      if (!e.centro) { const pts = rectOrPoly(e); if (pts) flatPoly(P.env, colorMat(b, 'cancha', e.color || '#3f7f6a'), pts, 0.04); return; }
      const f = frame({ ...e, largo: e.largo ?? 28, ancho: e.ancho ?? 15 }), pts = rectOrPoly({ ...e, largo: f.L, ancho: f.A });
      flatPoly(P.env, e.superficie === 'concreto' ? 'piso' : colorMat(b, 'cancha', e.color || '#3f7f6a'), pts, 0.04);
      const lines = [[f.L, 0.08, 0, f.A / 2 - 0.04], [f.L, 0.08, 0, -f.A / 2 + 0.04], [0.08, f.A, f.L / 2 - 0.04, 0], [0.08, f.A, -f.L / 2 + 0.04, 0], [0.08, f.A, 0, 0]];
      for (const [w, d, x, z] of lines) P.env.addRaw('linea', boxG(w, 0.01, d, x, 0.05, z).applyMatrix4(f.m));
      P.env.addRaw('linea', new THREE.RingGeometry(1.75, 1.83, 40).rotateX(-Math.PI / 2).translate(0, 0.061, 0).applyMatrix4(f.m));
      if (e.cubierta) {
        const h = e.altura ?? 8, nc = Math.max(2, Math.round(f.L / 6) + 1);
        for (let i = 0; i < nc; i++) for (const sz of [1, -1]) P.env.addRaw('acero', boxG(0.3, h, 0.3, -f.L / 2 + (i * f.L) / (nc - 1), 0, sz * (f.A / 2 + 0.5)).applyMatrix4(f.m));
        const rp = new Part(), wp = new Part(), rk = roofMat(b, { material: e.material_cubierta || 'zinc', color: e.color_cubierta });
        vault(f.L + 1, f.A + 1, h, { flecha: f.A * 0.12, voladizo: 0.5 }, rp, wp, 'acero', rk);
        mergeInto(P.roofKeep, rp, f.m);
      }
      return;
    }
    case 'parqueadero': case 'patio': case 'anden': case 'zona_verde': case 'plaza': {
      const pts = rectOrPoly(e); if (!pts) return;
      flatPoly(P.env, { parqueadero: 'asfalto', zona_verde: 'pasto' }[e.tipo] || 'piso', pts, e.tipo === 'zona_verde' ? 0.02 : 0.03);
      return;
    }
    case 'cubierta_ligera': {
      const f = frame({ ...e, largo: e.largo ?? 6, ancho: e.ancho ?? 4 }), h = e.altura ?? 3;
      for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) P.env.addRaw('acero', boxG(0.12, h, 0.12, sx * (f.L / 2 - 0.1), 0, sz * (f.A / 2 - 0.1)).applyMatrix4(f.m));
      const rp = new Part(), wp = new Part();
      shed(f.L, f.A, h, { pendiente: 6, voladizo: 0.3 }, rp, wp, 'acero', roofMat(b, { material: e.material || 'zinc', color: e.color }));
      mergeInto(P.roofKeep, rp, f.m);
      return;
    }
    case 'asta': {
      const c = at(), h = e.altura ?? 8;
      P.env.add('aluminio', new THREE.CylinderGeometry(0.04, 0.06, h, 10), [c.x, h / 2, c.z]);
      [['bandera_am', 0.5, 0], ['bandera_az', 0.25, -0.5], ['bandera_ro', 0.25, -0.75]].forEach(([m, hh, dy]) => P.env.add(m, new THREE.PlaneGeometry(1.5, hh), [c.x + 0.78, h - 0.25 + dy - hh / 2 + 0.25, c.z]));
      return;
    }
    case 'poste': {
      const c = at(), h = e.altura ?? 9;
      P.env.add('concreto', new THREE.CylinderGeometry(0.1, 0.16, h, 8), [c.x, h / 2, c.z]);
      P.env.addRaw('concreto', boxG(1.6, 0.1, 0.1, c.x, h - 0.6, c.z));
      return;
    }
    case 'torre': case 'antena': {
      const c = at(), h = e.altura ?? 24, w0 = e.tipo === 'torre' ? Math.max(1.2, h * 0.08) : 0.4, w1 = 0.35;
      for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
        const a = V3(c.x + sx * w0 / 2, 0, c.z + sz * w0 / 2), b2 = V3(c.x + sx * w1 / 2, h, c.z + sz * w1 / 2);
        const len = a.distanceTo(b2), g = new THREE.CylinderGeometry(0.04, 0.05, len, 6);
        g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(UP, b2.clone().sub(a).normalize())).translate((a.x + b2.x) / 2, h / 2, (a.z + b2.z) / 2);
        P.env.addRaw('aluminio', g);
      }
      if (e.tipo === 'torre') for (let y = 3; y < h; y += 3) { const w = w0 + (w1 - w0) * (y / h); for (const [sx, sz, rx] of [[0, 1, 0], [0, -1, 0], [1, 0, 1], [-1, 0, 1]]) P.env.addRaw('aluminio', boxG(rx ? 0.04 : w, 0.04, rx ? w : 0.04, c.x + sx * w / 2, y, c.z + sz * w / 2)); }
      return;
    }
    case 'planta_electrica': { const c = at(); P.env.addRaw('generador', boxG(e.largo ?? 3, e.altura ?? 1.9, e.ancho ?? 1.5, c.x, 0.15, c.z)); P.env.addRaw('piso', boxG((e.largo ?? 3) + 0.6, 0.15, (e.ancho ?? 1.5) + 0.6, c.x, 0, c.z)); return; }
    case 'aire_acondicionado': { const c = at(), y = e.altura ?? 0.3; P.env.addRaw('equipo', boxG(0.95, 0.7, 0.4, c.x, y, c.z)); P.env.add('acero', new THREE.CylinderGeometry(0.24, 0.24, 0.03, 18), [c.x, y + 0.38, c.z + 0.21], [Math.PI / 2, 0, 0]); return; }
    default: warn.push(`elemento desconocido: ${e.tipo}`);
  }
}
function treeMesh(b) {
  const p = new Part();
  p.add('tronco', new THREE.CylinderGeometry(0.035, 0.05, 0.45, 7), [0, 0.225, 0]);
  p.add('copa', new THREE.IcosahedronGeometry(0.5, 1).scale(1, 0.62, 1), [0, 0.68, 0]);
  p.add('copa2', new THREE.IcosahedronGeometry(0.34, 0).scale(1, 0.7, 1), [0.18, 0.88, 0.1]);
  return b.partMesh('arbol', p);
}

// ---------- adecuaciones: paneles sobre cubiertas, marquesinas, baterías, inversores, cargador
function placeModules(b, ad, faceInfo, pvMeshRef, parent, P, detail) {
  const cols = Math.max(1, ad.columnas | 0), rows = Math.max(1, ad.filas | 0);
  const vert = (ad.orientacion_modulo || 'vertical') !== 'horizontal';
  const mw = vert ? MOD.W : MOD.L, ml = vert ? MOD.L : MOD.W, gu = 0.02, gv = 0.05;
  const pu = mw + gu, pv = ml + gv;
  const mats = [];
  const quatFrom = (u, n, d) => { const x = u.clone(); if (x.clone().cross(n).dot(d) < 0) x.negate(); return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, n, d)); };
  const modRot = vert ? new THREE.Quaternion() : new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2);
  if (faceInfo.flat) {
    // racks inclinados en cubierta plana orientados al azimut (planta) indicado
    const az = (ad.azimut ?? 180) * D2R, tilt = (ad.inclinacion ?? 10) * D2R;
    const fdir = V3(Math.sin(az), 0, -Math.cos(az)), u = V3(Math.cos(az), 0, Math.sin(az));
    const n = UP.clone().multiplyScalar(Math.cos(tilt)).addScaledVector(fdir, Math.sin(tilt)).normalize();
    const d = fdir.clone().multiplyScalar(Math.cos(tilt)).addScaledVector(UP, -Math.sin(tilt)).normalize();
    const c = V3(0, faceInfo.y, 0).applyMatrix4(faceInfo.m); if (faceInfo.rot) { /* centro del volumen */ }
    const rowPitch = ml * Math.cos(tilt) + 0.45;
    const q = quatFrom(u, n, d).multiply(modRot);
    for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
      const p = c.clone().addScaledVector(u, (i - (cols - 1) / 2) * pu).addScaledVector(fdir, (j - (rows - 1) / 2) * rowPitch); p.y += 0.25 + (ml / 2) * Math.sin(tilt);
      mats.push([p, q]);
    }
  } else if (faceInfo.arc) {
    const { sg, yc, Rr, D } = faceInfo, rot = faceInfo.rot;
    const half = new Part();
    for (let j = 0; j < rows; j++) {
      const s = 0.4 + (j + 0.5) * pv; // longitud de arco desde la clave
      const ang = s / Rr; if (Math.sin(ang) * Rr > D / 2 - 0.3) continue;
      const z = sg * Rr * Math.sin(ang), y = yc + Rr * Math.cos(ang) + 0.1;
      const nL = V3(0, Math.cos(ang), sg * Math.sin(ang)), dL = V3(0, -Math.sin(ang), sg * Math.cos(ang));
      for (let i = 0; i < cols; i++) {
        let p = V3((i - (cols - 1) / 2) * pu, y, z), n = nL.clone(), d = dL.clone(), u = V3(1, 0, 0);
        if (rot) { const r3 = new THREE.Matrix4().extractRotation(rot); p.applyMatrix4(rot); n.applyMatrix4(r3); d.applyMatrix4(r3); u.applyMatrix4(r3); }
        const r3m = new THREE.Matrix4().extractRotation(faceInfo.m);
        p.applyMatrix4(faceInfo.m); n.applyMatrix4(r3m); d.applyMatrix4(r3m); u.applyMatrix4(r3m);
        mats.push([p, quatFrom(u, n, d).multiply(modRot)]);
      }
    }
    void half;
  } else {
    const r3 = new THREE.Matrix4().extractRotation(faceInfo.m);
    const n = faceInfo.n.clone().applyMatrix4(r3), u = faceInfo.u.clone().applyMatrix4(r3), d = faceInfo.vd.clone().applyMatrix4(r3);
    const c = faceInfo.c.clone().applyMatrix4(faceInfo.m).addScaledVector(n, 0.13);
    const q = quatFrom(u, n, d).multiply(modRot);
    for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) mats.push([c.clone().addScaledVector(u, (i - (cols - 1) / 2) * pu).addScaledVector(d, (j - (rows - 1) / 2) * pv), q]);
  }
  addModules(b, mats, pvMeshRef, parent, P, detail);
  return mats.length;
}
function addModules(b, mats, pvMeshRef, parent, P, detail) {
  if (detail) instanced(b, 'modulos', pvMeshRef, mats.map(([p, q]) => ({ t: [p.x, p.y, p.z], r: [q.x, q.y, q.z, q.w] })), parent);
  else for (const [p, q] of mats) { const g = new THREE.PlaneGeometry(MOD.W, MOD.L).rotateX(-Math.PI / 2); g.applyQuaternion(q).translate(p.x, p.y + 0.02, p.z); P.solarFlat.addRaw('celdas', g, true); }
}
function canopy(b, ad, pvMeshRef, parent, P, detail) {
  const f = frame({ ...ad, largo: ad.largo ?? 16, ancho: ad.ancho ?? 6 }), h = ad.altura ?? 3.5, tilt = 5 * D2R;
  const nc = Math.max(2, Math.round(f.L / 5.5) + 1);
  for (let i = 0; i < nc; i++) {
    const x = -f.L / 2 + 0.3 + (i * (f.L - 0.6)) / (nc - 1);
    P.equip.addRaw('acero', boxG(0.22, h + (f.A / 2) * Math.tan(tilt), 0.22, x, 0, 0).applyMatrix4(f.m));
    P.equip.addRaw('acero', boxG(0.14, 0.24, f.A, x, h, 0).applyMatrix4(f.m));
  }
  for (const z of [-f.A / 3, 0, f.A / 3]) P.equip.addRaw('acero', boxG(f.L, 0.12, 0.1, 0, h + 0.22, z).applyMatrix4(f.m));
  const cols = Math.max(1, ad.columnas | 0), rows = Math.max(1, ad.filas | 0), vert = (ad.orientacion_modulo || 'horizontal') === 'vertical';
  const pu = (vert ? MOD.W : MOD.L) + 0.02, pv = (vert ? MOD.L : MOD.W) + 0.02;
  const r3 = new THREE.Matrix4().extractRotation(f.m);
  const u = V3(1, 0, 0).applyMatrix4(r3), n = V3(0, Math.cos(tilt), Math.sin(tilt)).applyMatrix4(r3), d = V3(0, -Math.sin(tilt), Math.cos(tilt)).applyMatrix4(r3);
  const x = u.clone(); if (x.clone().cross(n).dot(d) < 0) x.negate();
  const q = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, n, d)).multiply(vert ? new THREE.Quaternion() : new THREE.Quaternion().setFromAxisAngle(UP, Math.PI / 2));
  const c = V3(0, h + 0.4, 0).applyMatrix4(f.m), mats = [];
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) mats.push([c.clone().addScaledVector(u, (i - (cols - 1) / 2) * pu).addScaledVector(d, (j - (rows - 1) / 2) * pv), q]);
  addModules(b, mats, pvMeshRef, parent, P, detail);
  return mats.length;
}
function bessGroup(b, be, P, detail) {
  const tipo = be.tipo || (be.kwh > 200 ? 'contenedor_20' : be.kwh > 90 ? 'contenedor_10' : 'gabinete');
  const L = be.largo ?? (tipo === 'contenedor_20' ? 6.06 : tipo === 'contenedor_10' ? 2.99 : Math.max(1.4, Math.ceil((be.kwh || 30) / 60) * 1.3 + 1));
  const f = frame({ ...be, centro: be.centro || [0, 0], largo: L, ancho: be.ancho ?? (tipo === 'gabinete' ? 1.2 : 2.44) });
  P.bess.addRaw('piso', boxG(f.L + 0.6, 0.15, f.A + 0.6).applyMatrix4(f.m));
  if (tipo === 'gabinete') {
    const n = Math.max(1, Math.ceil((be.kwh || 30) / 60));
    for (let i = 0; i < n + 1; i++) {
      const x = -f.L / 2 + 0.65 + i * ((f.L - 1.3) / Math.max(1, n));
      const g = i === n ? boxG(0.8, 1.9, 0.7, x, 0.15, 0) : boxG(1.0, 2.15, 0.8, x, 0.15, 0);
      P.bess.addRaw('gabinete', g.applyMatrix4(f.m));
      if (detail) { P.bess.addRaw('gabinete_franja', boxG(i === n ? 0.82 : 1.02, 0.08, 0.82, x, 1.9, 0).applyMatrix4(f.m)); P.bess.addRaw('lamina', boxG(0.25, 0.15, 0.02, x, 1.5, 0.41).applyMatrix4(f.m)); }
    }
  } else {
    const part = bessPart(detail, tipo === 'contenedor_20' ? 6.06 : 2.99);
    for (const [k, gs] of part.byMat) for (const g of gs) P.bess.addRaw(k, g.clone().translate(0, 0.15, 0).applyMatrix4(f.m));
  }
}
function inverters(b, inv, vols, P) {
  const vol = vols.find((x) => x.id === inv.volumen) || vols[0]; if (!vol?.f) return;
  const f = vol.f, s = sideFor(f, inv.lado || 'S'), n = Math.max(1, inv.n ?? 1);
  for (let i = 0; i < n; i++) {
    const m = sideMatrix(f, s, (i - (n - 1) / 2) * 0.85 + (inv.pos ?? 0) , 1.2, 0);
    P.equip.addRaw('gabinete', boxG(0.6, 0.78, 0.24, 0, 0, 0.12).applyMatrix4(m));
    P.equip.addRaw('lamina', boxG(0.2, 0.1, 0.02, 0, 0.5, 0.25).applyMatrix4(m));
  }
  const m0 = sideMatrix(f, s, ((n - 1) / 2) * 0.85 + 0.7, 1.1, 0);
  P.equip.addRaw('aluminio', boxG(0.45, 0.6, 0.18, 0, 0, 0.09).applyMatrix4(m0)); // medidor bidireccional y tablero
  P.equip.addRaw('equipo', boxG(0.25, 0.25, 0.08, 0.5, 0.35, 0.04).applyMatrix4(m0)); // pasarela IoT de la domótica
  P.equip.addRaw('acero', boxG(0.02, 0.35, 0.02, 0.6, 0.6, 0.06).applyMatrix4(m0));
  const top = vol.eave - 0.3;
  P.equip.addRaw('ducto', boxG(0.08, top - 2.0, 0.06, 0, 2.0, 0.05).applyMatrix4(sideMatrix(f, s, 0, 0, 0)));
  P.equip.addRaw('ducto', boxG(n * 0.85 + 0.4, 0.06, 0.08, 0, 2.05, 0.06).applyMatrix4(sideMatrix(f, s, 0, 0, 0)));
}
function charger(b, c, P) {
  const f = frame({ centro: c.centro, largo: 5, ancho: 2.5, rumbo_eje: c.rumbo_eje ?? 0 });
  P.equip.addRaw('lamina', boxG(0.35, 1.45, 0.25, -2.7, 0, 0).applyMatrix4(f.m));
  P.equip.addRaw('verde_ve', boxG(0.36, 0.1, 0.26, -2.7, 1.2, 0).applyMatrix4(f.m));
  for (const [w, d, x, z] of [[5, 0.1, 0, 1.25], [5, 0.1, 0, -1.25], [0.1, 2.5, 2.5, 0]]) P.equip.addRaw('pintura_ve', boxG(w, 0.01, d, x, 0.035, z).applyMatrix4(f.m));
  P.equip.addRaw('pintura_ve', boxG(1.2, 0.01, 1.2, 0, 0.035, 0).applyMatrix4(f.m));
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
    equip: new Part(), bess: new Part(), solarFlat: new Part(),
    replace: (v) => (replaceIds ? replaceIds.includes(v.id) : ['fibrocemento', 'zinc', undefined].includes(v.techo?.material) && v.techo?.tipo !== 'plano' && v.techo?.tipo !== 'ninguno'),
    newRoofSpec: (t) => ({ ...t, material: cn?.material || 'termoacustica', color: cn?.color || (cn?.material === 'teja_barro' ? '#a5512f' : '#e9e7e1') }),
  };
  const vols = (spec.volumenes || []).map((v) => {
    try { return { id: v.id, ...(v.poligono ? volumePoly(b, v, P) : volume(b, v, P, detail)) }; } catch (e) { warn.push(`${spec.id}/${v.id}: ${e.message}`); return { id: v.id, faces: [] }; }
  });
  const trees = [];
  for (const e of spec.elementos || []) { try { element(b, e, P, detail, trees); } catch (err) { warn.push(`${spec.id}/elemento ${e.tipo}: ${err.message}`); } }
  // predio: rectángulo que envuelve todo con 2 m de margen
  const xs = [], ys = [];
  const push = (pts) => pts && pts.forEach(([x, y]) => { xs.push(x); ys.push(y); });
  for (const v of spec.volumenes || []) push(rectOrPoly(v));
  for (const e of spec.elementos || []) push(rectOrPoly(e) || (e.centro ? [e.centro] : e.poligono || e.linea));
  if (xs.length) { const m = 2; flatPoly(P.env, 'predio', [[Math.min(...xs) - m, Math.min(...ys) - m], [Math.max(...xs) + m, Math.min(...ys) - m], [Math.max(...xs) + m, Math.max(...ys) + m], [Math.min(...xs) - m, Math.max(...ys) + m]], 0.01); }

  const root = b.node(spec.nombre || spec.id, null);
  root.setExtras({ id: spec.id, lat: spec.lat, lon: spec.lon });
  const ex = b.node('existente', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root); ex.setExtras({ capa: 'existente' });
  b.node('estructura', b.partMesh(`${spec.id}_estructura`, P.walls), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex);
  // cubiertas que el proyecto reemplaza (se ocultan con "Con el proyecto") y cubiertas que se conservan
  if (!P.roof.empty) b.node('cubierta_actual', b.partMesh(`${spec.id}_cubierta`, P.roof), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex).setExtras({ capa: 'existente', reemplazada: !!(P.newRoof && !P.newRoof.empty) });
  if (!P.roofKeep.empty) b.node('cubierta', b.partMesh(`${spec.id}_cubierta_conservada`, P.roofKeep), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex).setExtras({ capa: 'existente' });
  const env = b.node('entorno', P.env.empty ? null : b.partMesh(`${spec.id}_entorno`, P.env), [0, 0, 0], [0, 0, 0], [1, 1, 1], ex);
  if (trees.length) {
    const tm = treeMesh(b);
    instanced(b, 'arboles', tm, trees.map((t, i) => { const q = new THREE.Quaternion().setFromAxisAngle(UP, (i * 2.399) % (Math.PI * 2)); return { t: [t.c.x, 0, t.c.z], r: [q.x, q.y, q.z, q.w], s: [t.cp, t.H, t.cp] }; }), env);
  }

  const adn = b.node('adecuaciones', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root); adn.setExtras({ capa: 'adecuaciones' });
  if (P.newRoof && !P.newRoof.empty) b.node('cubierta_nueva', b.partMesh(`${spec.id}_cubierta_nueva`, P.newRoof), [0, 0, 0], [0, 0, 0], [1, 1, 1], adn).setExtras({ capa: 'adecuaciones' });
  const solar = b.node('solar', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);
  const pvm = detail ? pvMesh(b) : null;
  let modules = 0;
  (ad.fv || []).forEach((a, k) => {
    try {
      const grp = b.node(`arreglo_${k}`, null, [0, 0, 0], [0, 0, 0], [1, 1, 1], solar);
      if (a.tipo === 'marquesina') { modules += canopy(b, a, pvm, grp, P, detail); return; }
      const vol = vols.find((v) => v.id === a.volumen) || vols[0];
      if (!vol?.faces?.length) { warn.push(`${spec.id}: el arreglo ${k} no tiene cubierta donde apoyarse`); return; }
      let fi = vol.faces[0];
      if (vol.faces.length > 1 && a.faldon && a.faldon !== 'plano') {
        const c = CARD[String(a.faldon).toUpperCase()[0]] || CARD.S, r3 = new THREE.Matrix4().extractRotation(vol.faces[0].m);
        let bd = -9;
        for (const q of vol.faces) { const n = q.n.clone().applyMatrix4(r3); const d = n.x * c[0] + -n.z * c[1]; if (d > bd) { bd = d; fi = q; } }
      }
      modules += placeModules(b, a, fi, pvm, grp, P, detail);
    } catch (e) { warn.push(`${spec.id}/fv ${k}: ${e.message}`); }
  });
  if (!detail && !P.solarFlat.empty) b.node('solar_simplificada', b.partMesh(`${spec.id}_solar`, P.solarFlat), [0, 0, 0], [0, 0, 0], [1, 1, 1], solar);
  if (ad.bess) bessGroup(b, ad.bess, P, detail);
  if (ad.inversores) inverters(b, ad.inversores, vols, P);
  if (ad.cargador_ve?.centro) charger(b, ad.cargador_ve, P);
  if (!P.bess.empty) b.node('almacenamiento', b.partMesh(`${spec.id}_bess`, P.bess), [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);
  if (!P.equip.empty) b.node('equipos', b.partMesh(`${spec.id}_equipos`, P.equip), [0, 0, 0], [0, 0, 0], [1, 1, 1], adn);

  // tamaño (para encuadrar) a partir del predio
  const size = xs.length ? [Math.max(...xs) - Math.min(...xs) + 4, Math.max(...vols.map((v) => (v.eave ?? 3) + 3), 4), Math.max(...ys) - Math.min(...ys) + 4] : [20, 8, 20];
  return { b, modules, size };
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
    confianza: spec.ubicacion?.confianza ?? null,
    fuentes: (spec.fuentes || []).map((s) => ({ tipo: s.tipo, fecha: s.fecha ?? null, nota: s.nota ?? null, url: gmaps(s) })).filter((s) => s.url || s.tipo === 'satelite'),
  };
  const i = manifest.findIndex((x) => x.id === spec.id); if (i >= 0) manifest[i] = entry; else manifest.push(entry);
  console.log(`${spec.id}: ${(m0.bytes / 1024).toFixed(0)} KB (lod1 ${(m1.bytes / 1024).toFixed(0)} KB) · ${m0.triangulos_fuente} triángulos · ${hi.modules} módulos = ${kwp} kWp${warn.length > before ? ' · avisos: ' + (warn.length - before) : ''}`);
}
manifest.sort((a, b) => a.id.localeCompare(b.id));
writeFileSync(manPath, JSON.stringify(manifest, null, 1));
if (warn.length) { console.warn('\nAvisos:'); warn.forEach((w) => console.warn(' · ' + w)); }
