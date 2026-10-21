// Utilidades compartidas para generar modelos GLB: geometría agrupada por material, texturas
// procedurales (PNG), materiales PBR, módulo fotovoltaico, contenedor de baterías y escritura
// optimizada (dedup + instancias GPU + soldado + Draco) con copia base64 para hospedajes sin .glb.
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { Document, NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS, EXTMeshGPUInstancing } from '@gltf-transform/extensions';
import { dedup, instance, prune, weld, draco } from '@gltf-transform/functions';
import draco3d from 'draco3dgltf';
import { writeFileSync, mkdirSync } from 'node:fs';
import { deflateSync } from 'node:zlib';

export { THREE, mergeGeometries };
export const lin = (hex) => { const c = new THREE.Color(hex); return [c.r, c.g, c.b]; }; // Color de three ya convierte sRGB → lineal

export function png(w, h, px) {
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w * 4 + 1)] = 0;
    for (let x = 0; x < w; x++) { const [r, g, b, a = 255] = px(x, y); raw.set([r, g, b, a], y * (w * 4 + 1) + 1 + x * 4); }
  }
  const crcT = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcT[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0))]);
}

// Acumula geometrías por material y las fusiona en una primitiva por material (menos draw calls)
export class Part {
  constructor() { this.byMat = new Map(); }
  get empty() { return this.byMat.size === 0; }
  add(mat, geo, pos = [0, 0, 0], rot = [0, 0, 0], keepUV = false) {
    const g = geo.index ? geo.clone() : geo.clone();
    g.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...pos), new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot)), new THREE.Vector3(1, 1, 1)));
    return this.addRaw(mat, g, keepUV);
  }
  // Geometría ya transformada (o con matriz arbitraria)
  addRaw(mat, g, keepUV = false, matrix) {
    if (matrix) g = g.clone().applyMatrix4(matrix);
    if (!keepUV && g.attributes.uv) g.deleteAttribute('uv');
    if (keepUV && !g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    if (!g.attributes.normal) g.computeVertexNormals();
    for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k);
    if (!g.index) { const idx = []; for (let i = 0; i < g.attributes.position.count; i++) idx.push(i); g.setIndex(idx); }
    const key = keepUV ? `${mat}` : mat;
    if (!this.byMat.has(key)) this.byMat.set(key, []);
    this.byMat.get(key).push(g);
    return this;
  }
  box(mat, w, h, d, x, y, z, rot) { return this.add(mat, new THREE.BoxGeometry(w, h, d), [x, y + h / 2, z], rot); }
  cyl(mat, r, h, x, y, z, seg = 16, rot) { return this.add(mat, new THREE.CylinderGeometry(r, r, h, seg), [x, y + h / 2, z], rot); }
}

export class Builder {
  constructor(name) {
    this.doc = new Document();
    this.doc.createBuffer();
    this.scene = this.doc.createScene(name);
    this.mats = {};
    this.uvMats = new Set();
    this.tris = 0;
  }
  mat(key, { color, rough = 0.8, metal = 0, emissive, tex, alpha, doubleSided = false, opacity = 1 } = {}) {
    if (this.mats[key]) return this.mats[key];
    const m = this.doc.createMaterial(key).setBaseColorFactor([...lin(color), opacity]).setRoughnessFactor(rough).setMetallicFactor(metal).setDoubleSided(doubleSided);
    if (emissive) m.setEmissiveFactor(lin(emissive));
    if (tex) { m.setBaseColorTexture(this.doc.createTexture(key).setMimeType('image/png').setImage(tex)); this.uvMats.add(key); }
    if (alpha || opacity < 1) m.setAlphaMode(alpha === 'mask' ? 'MASK' : 'BLEND');
    return (this.mats[key] = m);
  }
  geoToPrim(g, mat) {
    const d = this.doc, buf = d.getRoot().listBuffers()[0];
    const p = d.createPrimitive().setMaterial(mat);
    p.setAttribute('POSITION', d.createAccessor().setType('VEC3').setArray(new Float32Array(g.attributes.position.array)).setBuffer(buf));
    p.setAttribute('NORMAL', d.createAccessor().setType('VEC3').setArray(new Float32Array(g.attributes.normal.array)).setBuffer(buf));
    if (g.attributes.uv) p.setAttribute('TEXCOORD_0', d.createAccessor().setType('VEC2').setArray(new Float32Array(g.attributes.uv.array)).setBuffer(buf));
    p.setIndices(d.createAccessor().setType('SCALAR').setArray(new Uint32Array(g.index.array)).setBuffer(buf));
    this.tris += g.index.count / 3;
    return p;
  }
  partMesh(name, part) {
    const mesh = this.doc.createMesh(name);
    for (const [matKey, geos] of part.byMat) {
      const withUV = this.uvMats.has(matKey);
      const gs = geos.map((g) => {
        if (withUV && !g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
        if (!withUV && g.attributes.uv) g.deleteAttribute('uv');
        return g;
      });
      if (!this.mats[matKey]) throw new Error(`material sin definir: ${matKey}`);
      mesh.addPrimitive(this.geoToPrim(mergeGeometries(gs, false), this.mats[matKey]));
    }
    return mesh;
  }
  node(name, mesh, t = [0, 0, 0], r = [0, 0, 0], s = [1, 1, 1], parent = this.scene) {
    const q = Array.isArray(r) && r.length === 4 ? r : (() => { const qq = new THREE.Quaternion().setFromEuler(new THREE.Euler(...r)); return [qq.x, qq.y, qq.z, qq.w]; })();
    const n = this.doc.createNode(name).setTranslation(t).setRotation(q).setScale(s);
    if (mesh) n.setMesh(mesh);
    parent.addChild(n);
    return n;
  }
}

// Instancias GPU (EXT_mesh_gpu_instancing) bajo un nodo padre concreto: a diferencia de la función
// instance() de gltf-transform, que lleva los lotes a la raíz, así se conserva la jerarquía por capas.
// trs: [{ t: [x,y,z], r: [x,y,z,w], s: [x,y,z] }]
export function instanced(b, name, mesh, trs, parent) {
  if (!trs.length) return null;
  b.instExt ??= b.doc.createExtension(EXTMeshGPUInstancing);
  const buf = b.doc.getRoot().listBuffers()[0], n = trs.length;
  const T = new Float32Array(3 * n), R = new Float32Array(4 * n), S = new Float32Array(3 * n);
  trs.forEach((x, i) => { T.set(x.t || [0, 0, 0], 3 * i); R.set(x.r || [0, 0, 0, 1], 4 * i); S.set(x.s || [1, 1, 1], 3 * i); });
  const acc = (arr, type) => b.doc.createAccessor().setType(type).setArray(arr).setBuffer(buf);
  const batch = b.instExt.createInstancedMesh().setAttribute('TRANSLATION', acc(T, 'VEC3')).setAttribute('ROTATION', acc(R, 'VEC4')).setAttribute('SCALE', acc(S, 'VEC3'));
  const node = b.doc.createNode(name).setMesh(mesh).setExtension('EXT_mesh_gpu_instancing', batch);
  (parent || b.scene).addChild(node);
  return node;
}

// ---------- texturas procedurales (escala de grises: el color del material las tiñe)
const hash = (x, y) => { let h = (x * 374761393 + y * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177; return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };
export const TEX = {
  // módulo de 6 × 12 celdas monocristalinas con busbars, sobre lámina posterior blanca
  celdas: png(128, 256, (x, y) => {
    const cw = 128 / 6, ch = 256 / 12, cx = x % cw, cy = y % ch;
    if (cx < 0.9 || cy < 0.9) return [150, 156, 162];
    const corner = (cx < 3 || cx > cw - 3) && (cy < 3 || cy > ch - 3);
    if (corner) return [150, 156, 162];
    if ((Math.abs(cx - cw * 0.3) < 0.5 || Math.abs(cx - cw * 0.7) < 0.5)) return [120, 128, 140];
    const n = ((x * 73856093) ^ (y * 19349663)) % 7;
    return [14 + n, 22 + n, 48 + n * 2];
  }),
  // 1 m de lámina: ondas cada 7,6 cm (zinc), 17,7 cm (fibrocemento), trapecios cada 25 cm (termoacústica)
  zinc: png(128, 8, (x) => { const v = 200 + 45 * Math.sin((x / 128) * 13 * 2 * Math.PI); return [v, v, v]; }),
  fibrocemento: png(128, 8, (x, y) => { const v = 205 + 35 * Math.sin((x / 128) * 5.65 * 2 * Math.PI) + (hash(x, y) - 0.5) * 14; return [v, v, v]; }),
  termoacustica: png(128, 8, (x) => { const t = ((x / 128) * 4) % 1; const v = t < 0.18 ? 255 : t < 0.26 ? 175 : t > 0.92 ? 190 : 225; return [v, v, v]; }),
  // teja de barro: canales cada 20 cm y traslapo cada 33 cm (1 m × 1 m)
  teja: png(128, 128, (x, y) => {
    const u = ((x / 128) * 5) % 1, v = ((y / 128) * 3) % 1;
    let s = 170 + 70 * Math.sin(u * Math.PI); if (v > 0.9) s *= 0.62; s += (hash(Math.floor((x / 128) * 5), Math.floor((y / 128) * 3)) - 0.5) * 40;
    return [s, s, s];
  }),
  concreto: png(64, 64, (x, y) => { const v = 225 + (hash(x, y) - 0.5) * 26 + (hash(x >> 3, y >> 3) - 0.5) * 18; return [v, v, v]; }),
  // ladrillo visto: 25 × 7,5 cm con junta de 1 cm (1 m × 1 m)
  ladrillo: png(128, 128, (x, y) => {
    const row = Math.floor((y / 128) * 12), off = row % 2 ? 0.5 : 0, u = ((x / 128) * 4 + off) % 1, v = ((y / 128) * 12) % 1;
    if (u < 0.04 || v < 0.1) return [225, 220, 212];
    const s = 175 + (hash(Math.floor((x / 128) * 4 + off), row) - 0.5) * 60; return [s, s * 0.95, s * 0.92];
  }),
  // bloque de concreto: 40 × 20 cm
  bloque: png(128, 128, (x, y) => {
    const row = Math.floor((y / 128) * 5), off = row % 2 ? 0.5 : 0, u = ((x / 128) * 2.5 + off) % 1, v = ((y / 128) * 5) % 1;
    if (u < 0.025 || v < 0.05) return [170, 170, 168];
    const s = 225 + (hash(x, y) - 0.5) * 20; return [s, s, s];
  }),
  // celosía o calado de ventilación: cuadrícula de huecos de 15 cm
  celosia: png(64, 64, (x, y) => { const u = ((x / 64) * 6) % 1, v = ((y / 64) * 6) % 1; return u > 0.18 && v > 0.18 ? [40, 40, 42] : [245, 245, 245]; }),
  // reja sobre vidrio
  reja: png(64, 64, (x) => { const u = ((x / 64) * 8) % 1; return u < 0.12 ? [210, 210, 210] : [60, 76, 88]; }),
  // cancha: líneas blancas sobre base (se tiñe)
  pasto: png(64, 64, (x, y) => { const v = 200 + (hash(x, y) - 0.5) * 50; return [v, v, v]; }),
  asfalto: png(64, 64, (x, y) => { const v = 200 + (hash(x, y) - 0.5) * 40; return [v, v, v]; }),
};

export function baseMaterials(b) {
  b.mat('concreto', { color: '#ecebe6', rough: 0.88 });
  b.mat('concreto_oscuro', { color: '#c9c8c2', rough: 0.9 });
  b.mat('vidrio', { color: '#3e5868', rough: 0.08, metal: 0.25 });
  b.mat('aluminio', { color: '#c4c8cb', rough: 0.32, metal: 0.9 });
  b.mat('acero', { color: '#2b2d30', rough: 0.45, metal: 0.75 });
  b.mat('cubierta', { color: '#8e938f', rough: 0.85 });
  b.mat('rojo', { color: '#e3141b', rough: 0.5, emissive: '#3a0003' });
  b.mat('contenedor', { color: '#eda100', rough: 0.55, metal: 0.35 });
  b.mat('generador', { color: '#eb6834', rough: 0.5, metal: 0.4 });
  b.mat('celdas', { color: '#ffffff', rough: 0.22, metal: 0.3, tex: TEX.celdas });
  b.mat('blanco', { color: '#f4f4f2', rough: 0.6 });
  b.mat('lamina', { color: '#2a2f38', rough: 0.6 });
}

// ---------- módulo fotovoltaico (1,134 × 2,278 m) con marco de aluminio y celdas por textura
export const MOD = { W: 1.134, L: 2.278, T: 0.035, kwp: 0.55 };
export function pvMesh(b, name = 'modulo_fv') {
  const { W, L, T } = MOD, f = 0.035;
  const frame = new Part()
    .box('aluminio', W, T, f, 0, 0, -L / 2 + f / 2).box('aluminio', W, T, f, 0, 0, L / 2 - f / 2)
    .box('aluminio', f, T, L, -W / 2 + f / 2, 0, 0).box('aluminio', f, T, L, W / 2 - f / 2, 0, 0);
  const cells = new Part();
  const top = new THREE.PlaneGeometry(W - 2 * f, L - 2 * f); top.rotateX(-Math.PI / 2);
  cells.add('celdas', top, [0, T * 0.92, 0], [0, 0, 0], true);
  cells.box('lamina', W - 2 * f, T * 0.8, L - 2 * f, 0, 0.002, 0);
  const mesh = b.doc.createMesh(name);
  for (const part of [frame, cells]) for (const [k, geos] of part.byMat) mesh.addPrimitive(b.geoToPrim(mergeGeometries(geos.map((g) => { if (b.uvMats.has(k)) return g; if (g.attributes.uv) g.deleteAttribute('uv'); return g; }), false), b.mats[k]));
  return mesh;
}

// Arreglo de módulos inclinados 10° (latitud ~7° N) como nodos que luego se convierten en instancias GPU
export function pvArray(b, mesh, parent, cols, rows, origin, tilt = 0.17, gapX = 0.02, gapZ = 0.12) {
  const W = MOD.W + gapX, L = MOD.L * Math.cos(tilt) + gapZ;
  for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
    const x = origin[0] + (c - (cols - 1) / 2) * W, z = origin[2] + (r - (rows - 1) / 2) * L;
    b.node(`fv_${c}_${r}`, mesh, [x, origin[1], z], [tilt, 0, 0], [1, 1, 1], parent);
  }
}

// ---------- contenedor de baterías (20 pies: 6,06 × 2,59 × 2,44 m; 10 pies: 2,99 m)
export function bessPart(detail = true, L = 6.06) {
  const p = new Part(), H = 2.59, D = 2.44;
  p.box('contenedor', L, H - 0.12, D, 0, 0.12, 0);
  p.box('acero', L, 0.12, D, 0, 0, 0);
  if (detail) {
    const n = Math.max(6, Math.round(L * 3.3));
    for (let i = 0; i < n; i++) { const x = -L / 2 + 0.2 + i * ((L - 0.4) / (n - 1)); p.box('contenedor', 0.1, H - 0.4, 0.05, x, 0.2, D / 2 + 0.02); p.box('contenedor', 0.1, H - 0.4, 0.05, x, 0.2, -D / 2 - 0.02); }
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) for (const y of [0, H - 0.16]) p.box('acero', 0.18, 0.16, 0.18, x * (L / 2 - 0.09), y, z * (D / 2 - 0.09));
    // puertas en un extremo con barras de cierre
    p.box('contenedor', 0.04, H - 0.4, D / 2 - 0.08, L / 2 + 0.02, 0.2, -D / 4).box('contenedor', 0.04, H - 0.4, D / 2 - 0.08, L / 2 + 0.02, 0.2, D / 4);
    for (const z of [-0.85, -0.35, 0.35, 0.85]) p.cyl('aluminio', 0.025, H - 0.5, L / 2 + 0.07, 0.25, z, 8);
    // equipo de aire acondicionado y rejillas de ventilación
    const ax = -L / 2 + Math.min(1.4, L * 0.25);
    p.box('blanco', 0.9, 0.9, 0.35, ax, 0.9, D / 2 + 0.2);
    p.cyl('acero', 0.3, 0.04, ax, 1.35, D / 2 + 0.38, 20, [Math.PI / 2, 0, 0]);
    for (let i = 0; i < 6; i++) p.box('acero', 0.8, 0.03, 0.06, L / 2 - 1.8, 0.6 + i * 0.12, D / 2 + 0.05);
    p.box('blanco', 0.6, 0.4, 0.02, L / 2 - 2.6, 1.6, D / 2 + 0.06);
  }
  return p;
}

// ---------- optimización y escritura
let ioPromise = null;
export function getIO() {
  ioPromise ??= (async () => new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
    'draco3d.encoder': await draco3d.createEncoderModule(),
    'draco3d.decoder': await draco3d.createDecoderModule(),
  }))();
  return ioPromise;
}

// Optimiza el documento y escribe <dir>/<name>.glb y <name>.glb.json. Devuelve métricas.
export async function writeGLB(b, dirURL, name, { compress = true, instance: autoInstance = true } = {}) {
  const io = await getIO();
  const doc = b.doc;
  mkdirSync(dirURL, { recursive: true });
  const raw = await io.writeBinary(doc);
  const steps = [dedup(), ...(autoInstance ? [instance({ min: 3 })] : []), weld(), prune()];
  if (compress) steps.push(draco({ method: 'edgebreaker', quantizePosition: 14, quantizeNormal: 10, quantizeTexcoord: 12 }));
  await doc.transform(...steps);
  const glb = await io.writeBinary(doc);
  writeFileSync(new URL(`${name}.glb`, dirURL), glb);
  writeFileSync(new URL(`${name}.glb.json`, dirURL), JSON.stringify({ glb: Buffer.from(glb).toString('base64') }));
  const exts = doc.getRoot().listExtensionsUsed().map((e) => e.extensionName);
  const inst = doc.getRoot().listNodes().filter((n) => n.getExtension('EXT_mesh_gpu_instancing')).length;
  return { bytes: glb.byteLength, bytes_sin_comprimir: raw.byteLength, triangulos_fuente: Math.round(b.tris), materiales: doc.getRoot().listMaterials().length, extensiones: exts, nodos_instanciados: inst };
}
