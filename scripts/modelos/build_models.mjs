// Genera los modelos GLB del atlas y los optimiza como se haría con modelos profesionales:
// geometría agrupada por material, instancias GPU (EXT_mesh_gpu_instancing) para elementos
// repetidos, deduplicación, soldado de vértices, compresión Draco y textura PNG para el detalle
// fino (celdas solares) en vez de geometría. Salida: web/models/*.glb + manifest.json
//
// Uso: cd scripts/modelos && npm install && npm run build
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { Document, NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, instance, prune, weld, draco } from '@gltf-transform/functions';
import draco3d from 'draco3dgltf';
import { writeFileSync, mkdirSync } from 'node:fs';
import { deflateSync } from 'node:zlib';

const OUT = new URL('../../web/models/', import.meta.url);
mkdirSync(OUT, { recursive: true });

// ---------- utilidades
const lin = (hex) => { const c = new THREE.Color(hex); return [c.r, c.g, c.b]; }; // Color de three ya convierte sRGB → lineal

function png(w, h, px) {
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
class Part {
  constructor() { this.byMat = new Map(); }
  add(mat, geo, pos = [0, 0, 0], rot = [0, 0, 0], keepUV = false) {
    const g = geo.clone();
    g.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(...pos), new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot)), new THREE.Vector3(1, 1, 1)));
    if (!keepUV) g.deleteAttribute('uv');
    if (!g.index) { const idx = []; for (let i = 0; i < g.attributes.position.count; i++) idx.push(i); g.setIndex(idx); }
    if (!this.byMat.has(mat)) this.byMat.set(mat, []);
    this.byMat.get(mat).push(g);
    return this;
  }
  box(mat, w, h, d, x, y, z, rot) { return this.add(mat, new THREE.BoxGeometry(w, h, d), [x, y + h / 2, z], rot); }
  cyl(mat, r, h, x, y, z, seg = 16, rot) { return this.add(mat, new THREE.CylinderGeometry(r, r, h, seg), [x, y + h / 2, z], rot); }
}

class Builder {
  constructor(name) {
    this.doc = new Document();
    this.doc.createBuffer();
    this.scene = this.doc.createScene(name);
    this.mats = {};
    this.tris = 0;
  }
  mat(key, { color, rough = 0.8, metal = 0, emissive, tex } = {}) {
    if (this.mats[key]) return this.mats[key];
    const m = this.doc.createMaterial(key).setBaseColorFactor([...lin(color), 1]).setRoughnessFactor(rough).setMetallicFactor(metal);
    if (emissive) m.setEmissiveFactor(lin(emissive));
    if (tex) m.setBaseColorTexture(this.doc.createTexture(key).setMimeType('image/png').setImage(tex));
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
    for (const [matKey, geos] of part.byMat) mesh.addPrimitive(this.geoToPrim(mergeGeometries(geos, false), this.mats[matKey]));
    return mesh;
  }
  node(name, mesh, t = [0, 0, 0], r = [0, 0, 0], s = [1, 1, 1], parent = this.scene) {
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(...r));
    const n = this.doc.createNode(name).setTranslation(t).setRotation([q.x, q.y, q.z, q.w]).setScale(s);
    if (mesh) n.setMesh(mesh);
    parent.addChild(n);
    return n;
  }
}

// ---------- texturas
const cellsTex = png(128, 256, (x, y) => {
  // módulo de 6 × 12 celdas monocristalinas con busbars, sobre lámina posterior blanca
  const cw = 128 / 6, ch = 256 / 12, cx = x % cw, cy = y % ch;
  if (cx < 0.9 || cy < 0.9) return [150, 156, 162];
  const corner = (cx < 3 || cx > cw - 3) && (cy < 3 || cy > ch - 3);
  if (corner) return [150, 156, 162];
  if ((Math.abs(cx - cw * 0.3) < 0.5 || Math.abs(cx - cw * 0.7) < 0.5)) return [120, 128, 140];
  const n = ((x * 73856093) ^ (y * 19349663)) % 7;
  return [14 + n, 22 + n, 48 + n * 2];
});

function materials(b) {
  b.mat('concreto', { color: '#ecebe6', rough: 0.88 });
  b.mat('concreto_oscuro', { color: '#c9c8c2', rough: 0.9 });
  b.mat('vidrio', { color: '#4f6f82', rough: 0.08, metal: 0.25 });
  b.mat('aluminio', { color: '#c4c8cb', rough: 0.32, metal: 0.9 });
  b.mat('acero', { color: '#2b2d30', rough: 0.45, metal: 0.75 });
  b.mat('cubierta', { color: '#8e938f', rough: 0.85 });
  b.mat('rojo', { color: '#e3141b', rough: 0.5, emissive: '#3a0003' });
  b.mat('contenedor', { color: '#eda100', rough: 0.55, metal: 0.35 });
  b.mat('generador', { color: '#eb6834', rough: 0.5, metal: 0.4 });
  b.mat('celdas', { color: '#ffffff', rough: 0.22, metal: 0.3, tex: cellsTex });
  b.mat('blanco', { color: '#f4f4f2', rough: 0.6 });
  b.mat('lamina', { color: '#2a2f38', rough: 0.6 });
}

// ---------- módulo fotovoltaico (1,134 × 2,278 m) con marco de aluminio y celdas por textura
function pvMesh(b, name = 'modulo_fv') {
  const W = 1.134, L = 2.278, T = 0.035, f = 0.035;
  const frame = new Part()
    .box('aluminio', W, T, f, 0, 0, -L / 2 + f / 2).box('aluminio', W, T, f, 0, 0, L / 2 - f / 2)
    .box('aluminio', f, T, L, -W / 2 + f / 2, 0, 0).box('aluminio', f, T, L, W / 2 - f / 2, 0, 0);
  const cells = new Part();
  const top = new THREE.PlaneGeometry(W - 2 * f, L - 2 * f); top.rotateX(-Math.PI / 2);
  cells.add('celdas', top, [0, T * 0.92, 0], [0, 0, 0], true);
  cells.box('lamina', W - 2 * f, T * 0.8, L - 2 * f, 0, 0.002, 0);
  const mesh = b.doc.createMesh(name);
  for (const part of [frame, cells]) for (const [k, geos] of part.byMat) mesh.addPrimitive(b.geoToPrim(mergeGeometries(geos, false), b.mats[k]));
  return mesh;
}

// Arreglo de módulos inclinados 10° (latitud ~7° N) como nodos que luego se convierten en instancias GPU
function pvArray(b, mesh, parent, cols, rows, origin, tilt = 0.17, gapX = 0.02, gapZ = 0.12) {
  const W = 1.134 + gapX, L = 2.278 * Math.cos(tilt) + gapZ;
  for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
    const x = origin[0] + (c - (cols - 1) / 2) * W, z = origin[2] + (r - (rows - 1) / 2) * L;
    b.node(`fv_${c}_${r}`, mesh, [x, origin[1], z], [tilt, 0, 0], [1, 1, 1], parent);
  }
}

// ---------- contenedor de baterías (20 pies: 6,06 × 2,59 × 2,44 m)
function bessPart(detail = true) {
  const p = new Part(), L = 6.06, H = 2.59, D = 2.44;
  p.box('contenedor', L, H - 0.12, D, 0, 0.12, 0);
  p.box('acero', L, 0.12, D, 0, 0, 0);
  if (detail) {
    for (let i = 0; i < 20; i++) { const x = -L / 2 + 0.2 + i * ((L - 0.4) / 19); p.box('contenedor', 0.1, H - 0.4, 0.05, x, 0.2, D / 2 + 0.02); p.box('contenedor', 0.1, H - 0.4, 0.05, x, 0.2, -D / 2 - 0.02); }
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) for (const y of [0, H - 0.16]) p.box('acero', 0.18, 0.16, 0.18, x * (L / 2 - 0.09), y, z * (D / 2 - 0.09));
    // puertas en un extremo con barras de cierre
    p.box('contenedor', 0.04, H - 0.4, D / 2 - 0.08, L / 2 + 0.02, 0.2, -D / 4).box('contenedor', 0.04, H - 0.4, D / 2 - 0.08, L / 2 + 0.02, 0.2, D / 4);
    for (const z of [-0.85, -0.35, 0.35, 0.85]) p.cyl('aluminio', 0.025, H - 0.5, L / 2 + 0.07, 0.25, z, 8);
    // equipo de aire acondicionado y rejillas de ventilación
    p.box('blanco', 0.9, 0.9, 0.35, -1.6, 0.9, D / 2 + 0.2);
    p.cyl('acero', 0.3, 0.04, -1.6, 1.35, D / 2 + 0.38, 20, [Math.PI / 2, 0, 0]);
    for (let i = 0; i < 6; i++) p.box('acero', 0.8, 0.03, 0.06, 1.2, 0.6 + i * 0.12, D / 2 + 0.05);
    p.box('blanco', 0.6, 0.4, 0.02, 0.2, 1.6, D / 2 + 0.06);
  }
  return p;
}

// ---------- hospital (misma huella que la escena: bloque de 18 × 10 m, dos pisos)
function buildHospital(detail) {
  const b = new Builder(detail ? 'hospital_lod0' : 'hospital_lod1');
  materials(b);
  const root = b.node('E.S.E. Hospital Héctor Abad Gómez', null);
  const pv = pvMesh(b);
  const p = new Part();
  // plataforma y bloque de hospitalización
  p.box('concreto_oscuro', 46, 0.15, 30, 0, 0, 2);
  p.box('concreto', 18, 6, 10, 0, 0.15, 0);
  p.box('concreto_oscuro', 18.3, 0.25, 10.3, 0, 3.05, 0);
  p.box('cubierta', 18, 0.3, 10, 0, 6.15, 0);
  for (const [w, d, x, z] of [[18.3, 0.2, 0, 5.05], [18.3, 0.2, 0, -5.05], [0.2, 10.3, 9.05, 0], [0.2, 10.3, -9.05, 0]]) p.box('concreto', w, 0.7, d, x, 6.15, z);
  // ventanas: vidrio + marcos de aluminio en fachadas norte y sur
  const win = (cx, y, z, nz, w = 1.5, h = 1.3) => {
    p.box('vidrio', w, h, 0.06, cx, y, z + nz * 0.01);
    if (detail) {
      const f = 0.07, zz = z + nz * 0.05;
      p.box('aluminio', w + f * 2, f, 0.1, cx, y - f, zz).box('aluminio', w + f * 2, f, 0.1, cx, y + h, zz);
      p.box('aluminio', f, h, 0.1, cx - w / 2 - f / 2, y, zz).box('aluminio', f, h, 0.1, cx + w / 2 + f / 2, y, zz);
      p.box('aluminio', f * 0.6, h, 0.08, cx, y, zz);
      p.box('concreto_oscuro', w + 0.3, 0.08, 0.35, cx, y - 0.12, z + nz * 0.15);
    }
  };
  for (let i = 0; i < 8; i++) for (const y of [1.1, 4.0]) { win(-7.7 + i * 2.2, y, 5, 1); win(-7.7 + i * 2.2, y, -5, -1); }
  if (!detail) { p.box('vidrio', 17, 1.3, 0.06, 0, 1.1, 5.01).box('vidrio', 17, 1.3, 0.06, 0, 4.0, 5.01); }
  // acceso principal con marquesina y letrero
  p.box('concreto', 6, 0.3, 3, 0, 3.0, 6.5);
  for (const x of [-2.6, 2.6]) p.cyl('aluminio', 0.12, 3.0, x, 0, 7.8, 12);
  p.box('vidrio', 3.2, 2.6, 0.08, 0, 0.15, 5.05);
  p.box('blanco', 2.2, 1.6, 0.12, 0, 6.6, 5.1);
  p.box('rojo', 0.35, 1.2, 0.08, -0.55, 6.8, 5.18).box('rojo', 0.35, 1.2, 0.08, 0.55, 6.8, 5.18).box('rojo', 0.75, 0.3, 0.08, 0, 7.25, 5.18);
  // urgencias con bahía de ambulancias
  p.box('concreto', 8, 3.6, 7, 13, 0.15, 1.5).box('cubierta', 8, 0.25, 7, 13, 3.75, 1.5);
  p.box('rojo', 8.02, 0.35, 7.02, 13, 3.1, 1.5);
  p.box('concreto', 6, 0.3, 4, 13, 3.3, 7);
  if (detail) for (const x of [10.5, 15.5]) p.cyl('aluminio', 0.12, 3.3, x, 0, 8.6, 12);
  for (let i = 0; i < 3; i++) win(10.5 + i * 2.4, 1.3, 5.0, 1, 1.4, 1.1);
  // consulta externa y servicios
  p.box('concreto', 9, 3.6, 7, -13.5, 0.15, -1).box('cubierta', 9, 0.25, 7, -13.5, 3.75, -1);
  for (let i = 0; i < 3; i++) win(-16.5 + i * 3, 1.3, 2.5, 1, 1.6, 1.1);
  p.box('concreto', 6, 3, 5, 4, 0.15, -9).box('cubierta', 6, 0.2, 5, 4, 3.15, -9);
  if (detail) for (let i = 0; i < 8; i++) p.box('aluminio', 4.5, 0.05, 0.12, 4, 0.8 + i * 0.25, -11.55);
  // equipos de cubierta
  if (detail) for (const [x, z] of [[-6, -3], [-3, -3], [5, -3], [8, -3]]) {
    p.box('aluminio', 1.6, 1.0, 1.2, x, 6.45, z);
    p.cyl('acero', 0.45, 0.06, x, 7.45, z, 24);
  }
  // marquesina del parqueadero: estructura de acero
  const cpZ = 14.5;
  for (const x of [-8, -2.7, 2.7, 8]) { p.cyl('acero', 0.12, 2.6, x, 0.15, cpZ - 2, 10); p.cyl('acero', 0.12, 3.1, x, 0.15, cpZ + 2, 10); }
  p.box('acero', 18, 0.15, 0.2, 0, 2.75, cpZ - 2).box('acero', 18, 0.15, 0.2, 0, 3.25, cpZ + 2);
  // planta de respaldo y mástil de conectividad
  p.box('generador', 3.4, 2.1, 1.9, -12, 0.15, -8).box('acero', 0.3, 1.3, 0.3, -10.8, 2.25, -8);
  p.cyl('acero', 0.12, 10, 8.5, 6.45, -3.5, 10);
  if (detail) { p.add('aluminio', new THREE.SphereGeometry(0.9, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.4), [8.5, 15.5, -3.5], [-Math.PI / 2.4, 0, 0]); }
  b.node('edificio', b.partMesh('edificio', p), [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
  // baterías: contenedor de 20 pies
  b.node('BESS_400kWh', b.partMesh('contenedor_bess', bessPart(detail)), [-12, 0.15, 9], [0, 0, 0], [1.25, 1, 1], root);
  // solar: cubierta (60 kWp) + marquesina (40 kWp) con módulos de 550 Wp
  if (detail) {
    const roofPV = b.node('solar_cubierta', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
    pvArray(b, pv, roofPV, 14, 4, [0, 6.75, 0.2]);
    pvArray(b, pv, roofPV, 6, 3, [13, 4.15, 1.2]);
    const cp = b.node('solar_marquesina', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
    pvArray(b, pv, cp, 16, 2, [0, 3.35, cpZ], 0.12);
  } else {
    const low = new Part().box('celdas', 16, 0.08, 8.5, 0, 6.75, 0.2).box('celdas', 18, 0.08, 4.6, 0, 3.3, cpZ);
    b.node('solar_simplificada', b.partMesh('solar_simplificada', low), [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
  }
  return b;
}

function buildBESS() {
  const b = new Builder('contenedor_bess'); materials(b);
  b.node('Contenedor BESS 20 pies', b.partMesh('contenedor_bess', bessPart(true)));
  return b;
}
function buildPV() {
  const b = new Builder('modulo_fv'); materials(b);
  b.node('Módulo FV 550 Wp', pvMesh(b));
  return b;
}

// ---------- optimización y escritura
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'draco3d.encoder': await draco3d.createEncoderModule(),
  'draco3d.decoder': await draco3d.createDecoderModule(),
});
const manifest = [];
const jobs = [
  ['hospital_lod0', () => buildHospital(true), 'Hospital Héctor Abad Gómez (detalle completo)'],
  ['hospital_lod1', () => buildHospital(false), 'Hospital Héctor Abad Gómez (nivel de detalle bajo)'],
  ['contenedor_bess', buildBESS, 'Contenedor de baterías LFP de 20 pies'],
  ['modulo_fv', buildPV, 'Módulo fotovoltaico de 550 Wp'],
];
for (const [name, fn, title] of jobs) {
  const b = fn();
  const doc = b.doc;
  const raw = await io.writeBinary(doc);
  await doc.transform(dedup(), instance({ min: 4 }), weld(), prune(), draco({ method: 'edgebreaker', quantizePosition: 14, quantizeNormal: 10, quantizeTexcoord: 12 }));
  const glb = await io.writeBinary(doc);
  writeFileSync(new URL(`${name}.glb`, OUT), glb);
  // copia en base64 para hospedajes que no sirven .glb (el cargador la usa como respaldo)
  writeFileSync(new URL(`${name}.glb.json`, OUT), JSON.stringify({ glb: Buffer.from(glb).toString('base64') }));
  const exts = doc.getRoot().listExtensionsUsed().map((e) => e.extensionName);
  const inst = doc.getRoot().listNodes().filter((n) => n.getExtension('EXT_mesh_gpu_instancing')).length;
  manifest.push({ id: name, titulo: title, archivo: `models/${name}.glb`, bytes: glb.byteLength, bytes_sin_comprimir: raw.byteLength, triangulos_fuente: Math.round(b.tris), materiales: doc.getRoot().listMaterials().length, extensiones: exts, nodos_instanciados: inst });
  console.log(`${name}: ${(raw.byteLength / 1024).toFixed(0)} KB → ${(glb.byteLength / 1024).toFixed(0)} KB · ${Math.round(b.tris)} triángulos fuente · ${exts.join(', ')}`);
}
writeFileSync(new URL('manifest.json', OUT), JSON.stringify(manifest, null, 1));
