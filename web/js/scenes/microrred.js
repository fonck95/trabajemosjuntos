// Escena 3D: Red Energética Pública de Yondó. Casco urbano esquemático (no a escala) con cada
// edificio público, su generación solar, baterías, flujos de energía y la capa digital IoT/MinTIC.
// Maqueta con orilla del Magdalena, lotes, vías demarcadas, fachadas con ventanería, cubiertas con antepecho,
// estructura de los paneles y subestación con pórtico y aisladores. Casi todo usa un material con paleta por
// vértice: cada edificio es una sola llamada de dibujo y el tema claro/oscuro se cambia en los uniformes.
import { THREE, Stage, tokens, onTheme, mat, fmtCOP, fmtN, reducedMotion, PANEL } from '../core.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { loadModel, instancedFromModel } from '../assets.js';
import { simulate, STEPS } from '../sim.js';
import { MICRORRED as M } from '../data.js';

// ---------------------------------------------------------------- utilidades de modelado
const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const ONE = V(1, 1, 1), UP = V(0, 1, 0);
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _e = new THREE.Euler(), _v = new THREE.Vector3();

// Material con paleta: cada vértice lleva el índice de su color; rugosidad, metal, tinte por instancia y brillo
// propio van en un vec4 por entrada. El índice se resuelve en el vértice (válido en WebGL 1 y 2).
function paleta(keys) {
  const n = keys.length, idx = Object.fromEntries(keys.map((k, i) => [k, i]));
  const u = { uPal: { value: keys.map(() => new THREE.Color()) }, uPRM: { value: keys.map(() => new THREE.Vector4(0.85, 0, 0, 0)) } };
  const patch = (sh) => {
    Object.assign(sh.uniforms, u);
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>\nattribute float aPal;\nuniform vec3 uPal[${n}];\nuniform vec4 uPRM[${n}];\nvarying vec3 vPal;\nvarying vec3 vPRM;`)
      .replace('#include <color_vertex>', '#include <color_vertex>\nint iPal = int(aPal + 0.5);\nvPal = uPal[iPal];\nvPRM = vec3(uPRM[iPal].xy, uPRM[iPal].w);\n#ifdef USE_INSTANCING_COLOR\nvColor = mix(vec3(1.0), vColor, uPRM[iPal].z);\n#endif');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vPal;\nvarying vec3 vPRM;')
      .replace('vec4 diffuseColor = vec4( diffuse, opacity );', 'vec4 diffuseColor = vec4( diffuse * vPal, opacity );')
      .replace('#include <roughnessmap_fragment>', 'float roughnessFactor = vPRM.x;')
      .replace('#include <metalnessmap_fragment>', 'float metalnessFactor = vPRM.y;')
      .replace('vec3 totalEmissiveRadiance = emissive;', 'vec3 totalEmissiveRadiance = emissive + vPal * vPRM.z;');
  };
  return {
    idx,
    make(opts = {}) { const m = new THREE.MeshStandardMaterial({ color: 0xffffff, ...opts }); m.onBeforeCompile = patch; m.customProgramCacheKey = () => `paleta${n}`; return m; },
    set(k, color, rough = 0.85, metal = 0, tint = 0, glow = 0) { u.uPal.value[idx[k]].set(color); u.uPRM.value[idx[k]].set(rough, metal, tint, glow); },
  };
}

// deja solo posición y normal, sin índice, para poder fusionar geometrías de distinto tipo
const clean = (g) => { if (g.index) g = g.toNonIndexed(); for (const a of Object.keys(g.attributes)) if (a !== 'position' && a !== 'normal') g.deleteAttribute(a); return g; };

// Piezas que se fusionan en una sola geometría (posición, normal e índice de paleta)
class Kit {
  constructor(P) { this.P = P; this.list = []; }
  _tag(g, k) {
    const i = this.P.idx[k];
    if (i === undefined) throw new Error(`paleta sin «${k}»`);
    g.setAttribute('aPal', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count).fill(i), 1));
    this.list.push(g);
    return this;
  }
  add(k, g, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
    g = clean(g);
    if (x || y || z || rx || ry || rz) g.applyMatrix4(_m.compose(_v.set(x, y, z), _q.setFromEuler(_e.set(rx, ry, rz)), ONE));
    return this._tag(g, k);
  }
  // geometría con grupos (p. ej. tapas y costados de una extrusión): un color por grupo
  groups(g, keys) {
    g = clean(g);
    const a = new Float32Array(g.attributes.position.count);
    g.groups.forEach((gr) => a.fill(this.P.idx[keys[gr.materialIndex] ?? keys[0]], gr.start, gr.start + gr.count));
    g.setAttribute('aPal', new THREE.BufferAttribute(a, 1));
    this.list.push(g);
    return this;
  }
  box(k, w, h, d, x = 0, y = 0, z = 0, ry = 0) { return this.add(k, new THREE.BoxGeometry(w, h, d), x, y + h / 2, z, 0, ry); }
  // canto redondeado; en piezas chicas basta un chaflán (un segmento: 108 triángulos en vez de 300)
  rbox(k, w, h, d, r, x = 0, y = 0, z = 0, ry = 0) { return this.add(k, new RoundedBoxGeometry(w, h, d, r > 0.09 ? 2 : 1, r), x, y + h / 2, z, 0, ry); }
  cyl(k, rt, rb, h, x = 0, y = 0, z = 0, seg = 10) { return this.add(k, new THREE.CylinderGeometry(rt, rb, h, seg), x, y + h / 2, z); }
  // barra entre dos puntos: conductores, riostras y tuberías
  rod(k, a, b, r, seg = 6) {
    const A = V(...a), B = V(...b), g = new THREE.CylinderGeometry(r, r, A.distanceTo(B), seg);
    g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(UP, B.clone().sub(A).normalize()));
    const c = A.add(B).multiplyScalar(0.5);
    return this.add(k, g, c.x, c.y, c.z);
  }
  // pasa las piezas a otro kit con giro y desplazamiento
  into(K, x = 0, y = 0, z = 0, ry = 0) {
    _m.compose(_v.set(x, y, z), _q.setFromEuler(_e.set(0, ry, 0)), ONE);
    this.list.forEach((g) => K.list.push(g.applyMatrix4(_m)));
    this.list = [];
    return K;
  }
  geo() { const g = this.list.length ? mergeGeometries(this.list) : new THREE.BufferGeometry(); this.list = []; return g; }
  mesh(m, cast = true) { const o = new THREE.Mesh(this.geo(), m); o.castShadow = cast; o.receiveShadow = true; return o; }
}

const rrect = (w, d, r) => {
  const s = new THREE.Shape(), x = -w / 2, y = -d / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + d - r); s.quadraticCurveTo(x + w, y + d, x + w - r, y + d);
  s.lineTo(x + r, y + d); s.quadraticCurveTo(x, y + d, x, y + d - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
};
// losa de esquinas redondeadas (lotes, prados) con la cara superior a la altura h
const slab = (K, k, x0, x1, z0, z1, h, r = 0.6) => {
  const g = new THREE.ExtrudeGeometry(rrect(x1 - x0, z1 - z0, r), { depth: h, bevelEnabled: false, curveSegments: 3 });
  g.rotateX(-Math.PI / 2);
  K.add(k, g, (x0 + x1) / 2, 0, (z0 + z1) / 2);
};
// arco elíptico con espesor (bóvedas, nervios, tímpanos), extruido a lo largo de x
const archGeo = (r0, r1, k, len) => {
  const pts = [];
  for (let i = 0; i <= 24; i++) { const f = (i / 24) * Math.PI; pts.push(new THREE.Vector2(r1 * Math.cos(f), k * r1 * Math.sin(f))); }
  if (r0 > 0) for (let i = 24; i >= 0; i--) { const f = (i / 24) * Math.PI; pts.push(new THREE.Vector2(r0 * Math.cos(f), k * r0 * Math.sin(f))); }
  return new THREE.ExtrudeGeometry(new THREE.Shape(pts), { depth: len, bevelEnabled: false }).rotateY(Math.PI / 2).translate(-len / 2, 0, 0);
};

// Ventanas en banda: vidrio 6 cm afuera del muro y parteluces 10 cm afuera (sin caras coplanares)
function ventanas(K, side, plane, along, L, y, h = 1.3, step = 1.5) {
  const ns = side === 'n' || side === 's', sg = side === 's' || side === 'e' ? 1 : -1, n = Math.max(1, Math.round(L / step));
  const put = (k, len, hh, dep, a, yy, out) => (ns ? K.box(k, len, hh, dep, along + a, yy, plane + sg * out) : K.box(k, dep, hh, len, plane + sg * out, yy, along + a));
  put('glass', L, h, 0.1, 0, y, 0.01);
  for (let i = 0; i <= n; i++) put('trim', 0.07, h + 0.12, 0.14, -L / 2 + (i * L) / n, y - 0.06, 0.03);
  put('band', L + 0.2, 0.07, 0.24, 0, y - 0.13, 0.06);
}
// bandas de ventanas por piso sobre las fachadas indicadas (n, s, e, o = w)
function bands(K, w, d, x, z, floors, fh, { sill = 0.95, h = 1.4, step = 1.5, faces = 'nsew', m = 0.7 } = {}) {
  for (let f = 0; f < floors; f++) for (const s of faces) {
    const ns = s === 'n' || s === 's', sg = s === 's' || s === 'e' ? 1 : -1;
    ventanas(K, s, ns ? z + (sg * d) / 2 : x + (sg * w) / 2, ns ? x : z, (ns ? w : d) - 2 * m, f * fh + sill, h, step);
  }
}
// vanos con marco (arquitectura tradicional): vidrio 5 cm afuera y marco 8 cm afuera
function vanos(K, side, plane, along, L, n, y, ww = 0.9, hh = 1.3, k = 'wood') {
  const ns = side === 'n' || side === 's', sg = side === 's' || side === 'e' ? 1 : -1;
  const put = (kk, a, b, c, o, yy, out) => (ns ? K.box(kk, a, b, c, along + o, yy, plane + sg * out) : K.box(kk, c, b, a, plane + sg * out, yy, along + o));
  for (let i = 0; i < n; i++) {
    const o = n === 1 ? 0 : -L / 2 + (i * L) / (n - 1);
    put('glass', ww, hh, 0.08, o, y, 0.01);
    put(k, ww + 0.16, 0.08, 0.12, o, y + hh, 0.02);
    put(k, ww + 0.2, 0.08, 0.16, o, y - 0.08, 0.04);
    for (const sx of [-1, 1]) put(k, 0.08, hh, 0.12, o + sx * (ww / 2 + 0.04), y, 0.02);
  }
}
// volumen con zócalo, fajas de entrepiso y cubierta plana con antepecho y remate (o cornisa simple)
function volume(K, w, h, d, x = 0, z = 0, { parapet = 0.45, floors = 1, wall = 'wall', roof = 'roof' } = {}) {
  K.box(wall, w, h, d, x, 0, z);
  K.box('plinth', w + 0.08, 0.42, d + 0.08, x, 0, z);
  for (let f = 1; f < floors; f++) K.box('band', w + 0.06, 0.16, d + 0.06, x, (h * f) / floors - 0.08, z);
  if (!parapet) { K.box('band', w + 0.16, 0.1, d + 0.16, x, h, z); return; }
  K.box(roof, w - 0.3, 0.05, d - 0.3, x, h, z);
  for (const s of [-1, 1]) {
    K.box(wall, w + 0.06, parapet, 0.2, x, h, z + s * (d / 2 - 0.07));
    K.box(wall, 0.2, parapet, d - 0.34, x + s * (w / 2 - 0.07), h, z);
    K.box('band', w + 0.14, 0.07, 0.3, x, h + parapet, z + s * (d / 2 - 0.07));
    K.box('band', 0.3, 0.07, d - 0.3, x + s * (w / 2 - 0.07), h + parapet, z);
  }
}
// franja de color sobre el antepecho (3 cm afuera de su cara)
function fascia(K, k, w, d, x, z, y, hh) {
  for (const s of [-1, 1]) { K.box(k, w + 0.18, hh, 0.06, x, y, z + s * (d / 2 + 0.06)); K.box(k, 0.06, hh, d + 0.06, x + s * (w / 2 + 0.06), y, z); }
}
// cubierta a dos aguas: hastiales del color del muro, faldones con alero y caballete; devuelve la pendiente
function gable(K, w, d, rise, x, y, z, { eave = 0.45, ry = 0, k = 'tile', wall = 'wall' } = {}) {
  const tri = new THREE.ExtrudeGeometry(new THREE.Shape([new THREE.Vector2(-d / 2, 0), new THREE.Vector2(d / 2, 0), new THREE.Vector2(0, rise)]), { depth: w, bevelEnabled: false });
  K.add(wall, tri.rotateY(Math.PI / 2).translate(-w / 2, 0, 0), x, y, z, 0, ry);
  const a = Math.atan2(rise, d / 2), L = Math.hypot(rise, d / 2) + eave;
  for (const s of [-1, 1]) {
    const g = new THREE.BoxGeometry(w + 2 * eave, 0.12, L).rotateX(s * a);
    K.add(k, g.translate(0, rise - (Math.sin(a) * L) / 2 + Math.cos(a) * 0.07, s * ((Math.cos(a) * L) / 2 + Math.sin(a) * 0.07)), x, y, z, 0, ry);
  }
  K.add(k, new THREE.BoxGeometry(w + 2 * eave, 0.1, 0.32).translate(0, rise + 0.1, 0), x, y, z, 0, ry);
  return a;
}
// Filas de módulos solares sobre rieles y patas (delanteras cortas, traseras altas); guarda las matrices locales
function pvRows(K, list, cols, rows, x, y, z, { tilt = 0.17, rx = 0, legs = 0.28, posts = true } = {}) {
  const base = new THREE.Matrix4().compose(V(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, 0, 0)), ONE);
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(tilt, 0, 0));
  const cw = PANEL.w + 0.04, pitch = PANEL.l * Math.cos(tilt) + 0.14, W = cols * cw;
  for (let r = 0; r < rows; r++) {
    const rz = r * pitch - ((rows - 1) * pitch) / 2, row = new THREE.Matrix4().compose(V(0, legs, rz), q, ONE);
    for (let c = 0; c < cols; c++) list.push(base.clone().multiply(row).multiply(new THREE.Matrix4().makeTranslation(c * cw - (W - cw) / 2, 0, 0)));
    for (const o of [-0.55, 0.55]) {
      K.add('steel', new THREE.BoxGeometry(W, 0.05, 0.06).translate(0, -0.055, o).applyMatrix4(row).applyMatrix4(base));
      if (!posts) continue;
      const p = V(0, -0.08, o).applyQuaternion(q).add(V(0, legs, rz)), n = Math.max(2, Math.ceil(W / 2.6) + 1);
      for (let i = 0; i < n; i++) K.add('steel', new THREE.BoxGeometry(0.05, p.y, 0.05).translate(-W / 2 + 0.3 + (i * (W - 0.6)) / (n - 1), p.y / 2, p.z).applyMatrix4(base));
    }
  }
}
const hvac = (K, x, y, z) => K.rbox('white', 0.9, 0.62, 0.7, 0.06, x, y, z).add('dark', new THREE.CylinderGeometry(0.24, 0.24, 0.04, 16), x, y + 0.64, z);
const tank = (K, x, y, z) => K.cyl('tank', 0.42, 0.45, 0.85, x, y, z, 14).cyl('tank', 0.16, 0.16, 0.08, x, y + 0.85, z, 10);
// asta con la bandera de Colombia (amarillo 1/2, azul 1/4, rojo 1/4)
const flag = (K, x, z, hh) => K.cyl('steel', 0.035, 0.05, hh, x, 0.08, z, 6).box('flagY', 0.9, 0.3, 0.03, x + 0.47, hh - 0.32, z).box('flagB', 0.9, 0.15, 0.03, x + 0.47, hh - 0.47, z).box('flagR', 0.9, 0.15, 0.03, x + 0.47, hh - 0.62, z);
// aislador de porcelana con campanas
const insulator = (K, x, y, z, h = 0.6, n = 4) => { K.cyl('porcelain', 0.045, 0.055, h, x, y, z, 8); for (let i = 0; i < n; i++) K.cyl('porcelain', 0.11, 0.11, 0.035, x, y + 0.08 + (i * (h - 0.14)) / Math.max(1, n - 1), z, 10); return K; };
// tablero de acometida en el lote: de aquí sale el enlace de energía hacia la barra
const tablero = (K, x, z, ry) => K.box('band', 0.75, 0.1, 0.45, x, 0.04, z, ry).rbox('cab', 0.62, 1.0, 0.32, 0.04, x, 0.14, z, ry).box('led', 0.08, 0.08, 0.36, x, 0.95, z, ry);
// poste de acometida con cruceta, aisladores y bajante: de su punta sale la línea aérea hacia la barra
const POSTE = 7.32;
function poste(K, x, z, ry) {
  K.cyl('band', 0.08, 0.13, 7.2, x, 0, z, 8).box('steel', 1.4, 0.1, 0.1, x, 6.95, z, ry).cyl('dark', 0.03, 0.03, 6.2, x + 0.14 * Math.sin(ry), 0.9, z + 0.14 * Math.cos(ry), 5);
  for (const o of [-0.55, 0, 0.55]) insulator(K, x + o * Math.cos(ry), 7.05, z - o * Math.sin(ry), 0.26, 2);
  return K;
}
// pasarela IoT en la cubierta: de aquí sale el enlace de datos hacia el CCED
const gateway = (K, x, y, z) => K.cyl('steel', 0.025, 0.03, 0.85, x, y, z, 5).rbox('white', 0.2, 0.26, 0.12, 0.03, x, y + 0.85, z).box('led', 0.06, 0.04, 0.13, x, y + 1.0, z);

function truck(K, x, z) {
  K.rbox('red', 0.98, 1.15, 2.5, 0.08, x, 0.32, z - 0.45).rbox('red', 0.98, 1.0, 1.05, 0.1, x, 0.32, z + 1.35);
  K.box('glass', 0.9, 0.42, 0.06, x, 0.86, z + 1.86).box('steel', 0.34, 0.08, 2.7, x, 1.5, z - 0.35).box('white', 0.8, 0.09, 0.18, x, 1.32, z + 1.25);
  for (const zz of [-1.2, 0.0, 1.35]) for (const s of [-1, 1]) K.add('dark', new THREE.CylinderGeometry(0.3, 0.3, 0.18, 12), x + s * 0.43, 0.38, z + zz, 0, 0, Math.PI / 2);
}
// contenedor de baterías (respaldo si el GLB no carga): costillas corrugadas, esquineros y puertas
function container(K, len, hgt) {
  K.box('dark', len, 0.12, hgt, 0, 0, 0).box('bess', len - 0.04, hgt - 0.12, hgt - 0.04, 0, 0.12, 0);
  const n = Math.max(6, Math.round(len * 3));
  for (let i = 0; i < n; i++) for (const s of [-1, 1]) K.box('bess', 0.07, hgt - 0.42, 0.05, -len / 2 + 0.25 + (i * (len - 0.5)) / (n - 1), 0.25, s * (hgt / 2 + 0.005));
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) K.box('dark', 0.13, hgt, 0.13, (sx * (len - 0.11)) / 2, 0, (sz * (hgt - 0.11)) / 2);
  K.rbox('white', 0.8, 0.8, 0.3, 0.05, -len / 2 + 0.9, 0.8, hgt / 2 + 0.15);
}
// armarios de baterías LFP para exterior (instalaciones pequeñas)
function cabinets(K, n) {
  for (let i = 0; i < n; i++) {
    const x = (i - (n - 1) / 2) * 0.82;
    K.rbox('bess', 0.76, 1.8, 0.66, 0.05, x, 0, 0).box('dark', 0.02, 1.55, 0.03, x, 0.12, 0.34).box('dark', 0.5, 0.22, 0.04, x, 1.32, 0.33).box('led', 0.14, 0.06, 0.03, x + 0.2, 1.6, 0.345);
  }
}
function boat(K, x, z, ry) {
  const b = new Kit(K.P);
  b.rbox('white', 3.4, 0.42, 0.95, 0.16, 0, -0.47, 0).box('flagB', 3.3, 0.08, 0.97, 0, -0.22, 0).box('dark', 0.3, 0.45, 0.3, -1.85, -0.3, 0);
  for (const [px, pz] of [[-0.4, -0.38], [-0.4, 0.38], [0.9, -0.38], [0.9, 0.38]]) b.cyl('steel', 0.025, 0.025, 0.8, px, -0.05, pz, 5);
  b.box('red', 1.7, 0.05, 0.92, 0.25, 0.75, 0);
  b.into(K, x, 0, z, ry);
}

// ---------------------------------------------------------------- capa de enlaces
// Todos los tubos de una capa van en una sola malla. Sentido, rapidez, visibilidad, resalte y color de cada
// enlace viajan en uniformes; el shader dibuja trazos con cabeza brillante que avanzan en el sentido del flujo.
const LINK_VS = `attribute float aS; attribute float aK;
uniform vec4 uS[N]; uniform vec3 uC[N]; uniform float uW;
varying float vS; varying vec4 vSt; varying vec3 vC; varying float vL;
void main() {
  int k = int(aK + 0.5);
  vSt = uS[k]; vC = uC[k]; vS = aS;
  vec3 n = normalize(normalMatrix * normal);
  vL = 0.74 + 0.22 * n.z + 0.1 * n.y;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position + normal * uW * vSt.z, 1.0);
}`;
const LINK_FS = `uniform float uT; uniform float uDash; uniform float uHead;
varying float vS; varying vec4 vSt; varying vec3 vC; varying float vL;
void main() {
  if (vSt.y < 0.5) discard;
  float u = fract(vS / uDash - uT * vSt.x);
  if (vSt.x < 0.0) u = 1.0 - u;
  float c = smoothstep(uHead, 0.9, u) * (1.0 - smoothstep(0.9, 0.99, u)) * step(0.001, abs(vSt.x));
  vec3 col = mix(vC * 0.62, mix(vC, vec3(1.0), 0.5), c);
  col = mix(col, vec3(dot(col, vec3(0.3, 0.59, 0.11))) * 0.55 + 0.14, vSt.w * 0.8);
  gl_FragColor = vec4(col * vL, 1.0);
  #include <colorspace_fragment>
}`;
class Links {
  constructor({ dash, head, widen, n = 16 }) {
    this.geos = [];
    this.u = {
      uT: { value: 0 }, uDash: { value: dash }, uHead: { value: head }, uW: { value: widen },
      uS: { value: Array.from({ length: n }, () => new THREE.Vector4(0, 1, 0, 0)) },
      uC: { value: Array.from({ length: n }, () => new THREE.Color()) },
    };
    this.mat = new THREE.ShaderMaterial({ uniforms: this.u, defines: { N: n }, vertexShader: LINK_VS, fragmentShader: LINK_FS });
  }
  add(curve, r) {
    const k = this.geos.length, L = curve.getLength();
    const g = new THREE.TubeGeometry(curve, Math.max(20, Math.round(L * 2)), r, 8, false), uv = g.attributes.uv;
    g.setAttribute('aS', new THREE.BufferAttribute(Float32Array.from({ length: uv.count }, (_, i) => uv.getX(i) * L), 1));
    g.setAttribute('aK', new THREE.BufferAttribute(new Float32Array(uv.count).fill(k), 1));
    g.deleteAttribute('uv');
    this.geos.push(g);
    return k;
  }
  build(S) { this.mesh = new THREE.Mesh(mergeGeometries(this.geos), this.mat); this.geos = null; S.add(this.mesh); return this.mesh; }
  set(k, speed, color, vis) { const s = this.u.uS.value[k]; s.x = speed; s.y = vis ? 1 : 0; this.u.uC.value[k].copy(color); }
  // resalta los enlaces indicados y apaga el resto (lista vacía: todos normales)
  focus(ks) { this.u.uS.value.forEach((s, k) => { const on = ks.includes(k); s.z = on ? 1 : 0; s.w = ks.length && !on ? 1 : 0; }); }
  live() { return this.u.uS.value.some((s) => s.y > 0.5 && Math.abs(s.x) > 1e-3); }
}

export function mount(root) {
  const el = root.querySelector('.stage');
  const home = { pos: [38, 44, 58], tg: [-2, 0, -1] };
  const st = new Stage(el, { cam: home.pos, target: home.tg, maxDist: 130, env: false, declutter: ['lbl-node', 'lbl-small'] });
  st.sunLight.shadow.normalBias = 0.05; // sin acné de sombra con el sol rasante del amanecer
  const T = tokens();
  const S = st.scene;
  const P = paleta(['wall', 'roof', 'plinth', 'band', 'trim', 'steel', 'glass', 'red', 'police', 'accent', 'court', 'tile', 'wood', 'dark', 'white', 'grass', 'foliage', 'palm', 'trunk', 'lot', 'road', 'mark', 'gravel', 'ground', 'earth', 'sand', 'water', 'foam', 'pv', 'bess', 'gen', 'cab', 'porcelain', 'copper', 'flagY', 'flagB', 'flagR', 'lamp', 'led', 'tank', 'paint']);
  const pal = P.make();
  // capas planas (demarcación, espuma, líneas de cancha) con polygonOffset: no titilan contra lo que cubren
  const palMk = P.make({ polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const mix = (a, b, k) => new THREE.Color(a).lerp(new THREE.Color(b), k);
  function paint(t) {
    const c = {
      wall: [t.wall, 0.85], roof: [t.roof, 0.9], plinth: [mix(t.wall, 0x30343a, 0.42), 0.9], band: [mix(t.wall, 0xb9b7ae, 0.4), 0.8],
      trim: [0x59626a, 0.45, 0.5], steel: [0x9aa5ad, 0.45, 0.6], glass: [0x6f93aa, 0.12, 0.35], red: [t.bad, 0.6], police: [0x1f7a3a, 0.6],
      accent: [t.s[2], 0.6], court: [0xb88d5e, 0.9], tile: [0xa65a3a, 0.85], wood: [0x7a5636, 0.8], dark: [0x2b2f33, 0.6, 0.2], white: [0xf0f0ec, 0.6],
      grass: [mix(t.ground, 0x5f9a5a, 0.6), 1], foliage: [0x3f7d4e, 0.9, 0, 1], palm: [0x4d8a3c, 0.85, 0, 1], trunk: [0x6b4f3a, 0.9],
      lot: [mix(t.ground, t.wall, 0.5), 0.95], road: [mix(t.ground, t.ink, 0.14), 0.95], mark: [mix(t.wall, 0xffffff, 0.3), 0.7],
      gravel: [mix(t.roof, t.ground, 0.35), 1], ground: [t.ground, 1], earth: [mix(t.ground, 0x7a6a55, 0.45), 1], sand: [mix(t.ground, 0xd8c7a0, 0.55), 1],
      water: [t.water, 0.15, 0.1], foam: [mix(t.water, 0xffffff, 0.45), 0.4], pv: [0x1d3557, 0.3, 0.4], bess: [t.s[3], 0.55, 0.15], gen: [t.s[1], 0.55, 0.1],
      cab: [0x8c9a94, 0.6, 0.3], porcelain: [0xe9e2d4, 0.35], copper: [0xc07a3f, 0.35, 0.7], flagY: [0xf4c20d, 0.8], flagB: [0x1f4fa3, 0.8], flagR: [0xd02a2a, 0.8],
      lamp: [0xd9d9d0, 0.4, 0.2], led: [0x2fbf71, 0.4, 0, 0, 0.5], tank: [0x24384f, 0.5], paint: [0xffffff, 0.45, 0.2, 1],
    };
    for (const [k, [col, r, m = 0, tint = 0, glow = 0]] of Object.entries(c)) P.set(k, col, r, m, tint, glow);
  }
  paint(T);
  const piso = new Kit(P), est = new Kit(P), mk = new Kit(P);
  const trees = [], palms = [], cars = [], lamps = [], obst = [];

  // ---- Terreno: losa con canto de tierra, orilla curva del Magdalena (Barrancabermeja al frente), playa y espuma
  const shore = (z) => 26.6 + 1.6 * Math.sin(z * 0.09 + 0.6) + 0.8 * Math.sin(z * 0.23);
  const shore2 = (z) => 48.5 + 1.2 * Math.sin(z * 0.07 + 2) + 0.7 * Math.sin(z * 0.19 + 1);
  const ZS = Array.from({ length: 29 }, (_, i) => 35 - i * 2.5);
  const bank = (pts) => {
    const g = new THREE.ExtrudeGeometry(new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, -z))), { depth: 0.8, bevelEnabled: true, bevelThickness: 0.12, bevelSize: 0.3, bevelSegments: 2, curveSegments: 1 });
    piso.groups(g.rotateX(-Math.PI / 2).translate(0, -0.92, 0), ['ground', 'earth']);
  };
  bank([[-45, 35], ...ZS.map((z) => [shore(z), z]), [-45, -35]]);
  bank([[62, -35], ...ZS.slice().reverse().map((z) => [shore2(z), z]), [62, 35]]);
  piso.add('water', new THREE.PlaneGeometry(30, 70).rotateX(-Math.PI / 2), 37.5, -0.32, 0);
  // cinta entre x = f(z) + a (altura ya) y f(z) + b (altura yb), con b > a
  const ribbon = (K, k, f, a, b, ya, yb) => {
    const pos = [];
    for (let i = 0; i < ZS.length - 1; i++) {
      const z0 = ZS[i], z1 = ZS[i + 1], A = [f(z0) + a, ya, z0], B = [f(z0) + b, yb, z0], C = [f(z1) + a, ya, z1], D = [f(z1) + b, yb, z1];
      pos.push(...A, ...B, ...C, ...B, ...D, ...C);
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.computeVertexNormals();
    K.add(k, g);
  };
  ribbon(piso, 'sand', shore, -0.1, 1.6, -0.05, -0.45);
  ribbon(piso, 'sand', shore2, -1.6, 0.1, -0.45, -0.05);
  ribbon(mk, 'foam', shore, 1.12, 1.45, -0.31, -0.31);
  ribbon(mk, 'foam', shore2, -1.45, -1.12, -0.31, -0.31);

  // ---- Vías entre los lotes (no atraviesan edificios), con línea central discontinua y cebras
  const ROADS = [ // x0, z0, x1, z1, ancho, avenida
    [-45, -24, 23.6, -24, 2.2, 1], [-45, 18.6, 12.8, 18.6, 2.2, 1], [-35, -35, -35, 35, 2.2, 1],
    [6.8, -24, 6.8, 7.2, 1.8], [23.2, -24, 23.2, 0.8, 1.8], [-12.5, 7.2, 12.8, 7.2, 1.6], [-12.5, 7.2, -12.5, 18.6, 1.6], [-35, 2.5, -16.4, 2.5, 1.6],
  ];
  const ext = (v, w) => (Math.abs(v) >= 34.9 || v <= -44.9 ? 0 : w / 2);
  ROADS.forEach(([x0, z0, x1, z1, w]) => {
    const hz = z0 === z1, a = (hz ? x0 : z0) - ext(hz ? x0 : z0, w), b = (hz ? x1 : z1) + ext(hz ? x1 : z1, w);
    hz ? piso.box('road', b - a, 0.03, w, (a + b) / 2, 0, z0) : piso.box('road', w, 0.03, b - a, x0, 0, (a + b) / 2);
  });
  // la línea central se interrumpe en los cruces con vías perpendiculares
  const cruce = (hz, s, fijo) => ROADS.some(([x0, z0, x1, z1, w]) => (hz ? x0 === x1 && Math.abs(s - x0) < w / 2 + 0.8 && fijo > z0 - 1.3 && fijo < z1 + 1.3 : z0 === z1 && Math.abs(s - z0) < w / 2 + 0.8 && fijo > x0 - 1.3 && fijo < x1 + 1.3));
  ROADS.filter((r) => r[5]).forEach(([x0, z0, x1, z1]) => {
    const hz = z0 === z1;
    for (let s = (hz ? x0 : z0) + 1.5; s < (hz ? x1 : z1) - 1; s += 2.4) {
      if (cruce(hz, s, hz ? z0 : x0)) continue;
      hz ? mk.box('mark', 1.2, 0.012, 0.12, s, 0.03, z0) : mk.box('mark', 0.12, 0.012, 1.2, x0, 0.03, s);
    }
  });
  const zebra = (x, z, alongX, w) => { for (let i = 0; i < 6; i++) { const o = (i - 2.5) * (w / 6.4); alongX ? mk.box('mark', 0.9, 0.012, 0.2, x, 0.03, z + o) : mk.box('mark', 0.2, 0.012, 0.9, x + o, 0.03, z); } };
  zebra(8.6, -24, true, 2.2); zebra(21.3, -24, true, 2.2); zebra(-10.6, 18.6, true, 2.2); zebra(-35, 4.4, false, 2.2); zebra(-35, -21.6, false, 2.2); zebra(-32.6, -24, true, 2.2);

  // ---- Lotes de cada sede (losas de 8 cm sobre la vía de 3 cm) y parque principal
  const LOTS = [
    [-5.9, 5.8, -16.2, -3.7], [-27.4, -6.0, -22.6, -7.8], [7.9, 18.0, -18.0, -9.9], [12.6, 22.0, -9.7, 1.0], [12.4, 25.6, 0.9, 22.0],
    [-11.7, 3.4, 8.0, 17.2], [3.5, 14.8, 8.9, 17.2], [-16.6, -7.4, -0.8, 6.4], [-11.8, -1.6, -4.9, 3.8], [-27.2, -13.3, 3.4, 14.6],
    [-32.2, -19.8, -7.6, 1.6], [7.8, 12.4, -5.4, 4.6], [-0.4, 5.8, -3.8, 2.4],
  ];
  LOTS.forEach(([x0, x1, z0, z1]) => slab(piso, 'lot', x0, x1, z0, z1, 0.08));
  const LOT = 0.08;

  // ---- Edificios públicos (cada uno una malla con paleta) y sus puntos de conexión
  const fab = {
    palacio(n, K, c) {
      const [w, h, d] = n.dim, fh = h / 2, s = d / 2, ry = h + 0.05;
      volume(K, w, h, d, 0, 0, { floors: 2 });
      bands(K, w, d, 0, 0, 2, fh, { faces: 'nwe', h: 1.7, step: 1.3 });
      for (const a of [-3.2, 3.2]) for (let f = 0; f < 2; f++) ventanas(K, 's', s, a, 2.8, f * fh + 0.95, 1.7, 1.4);
      // cuerpo central con remate, escudo y acceso; pórtico de columnas hacia el parque
      K.box('wall', 3.2, h + 1.3, 0.9, 0, 0, s + 0.4).box('band', 3.5, 0.22, 1.1, 0, h + 1.3, s + 0.4);
      K.add('white', new THREE.CylinderGeometry(0.55, 0.55, 0.08, 24), 0, h + 0.45, s + 0.88, Math.PI / 2);
      K.box('glass', 1.7, 2.7, 0.1, 0, 0.18, s + 0.86);
      ventanas(K, 's', s + 0.85, 0, 1.8, fh + 0.95, 1.7, 0.9);
      for (const x of [-4.2, -2.7, 2.7, 4.2]) K.cyl('band', 0.17, 0.2, 3.4, x, 0.18, s + 1.2, 12);
      K.box('band', 9.2, 0.3, 1.6, 0, 3.55, s + 0.75).box('band', 9.6, 0.18, 1.8, 0, 0, s + 0.85);
      for (const x of [-4.4, 4.4]) flag(K, x, s + 1.6, 6.2);
      // cubierta: mástil del CCED con antenas sectoriales y parabólicas, equipos y paneles
      K.cyl('steel', 0.07, 0.13, 3.9, 3.3, ry, -1.4, 8);
      for (let i = 0; i < 3; i++) { const a = (i * Math.PI * 2) / 3; K.box('white', 0.24, 0.8, 0.09, 3.3 + Math.cos(a) * 0.2, ry + 2.85, -1.4 + Math.sin(a) * 0.2, Math.PI / 2 - a); }
      K.add('white', new THREE.CylinderGeometry(0.34, 0.2, 0.14, 16), 3.62, ry + 2.1, -1.4, 0, 0, Math.PI / 2);
      K.add('white', new THREE.CylinderGeometry(0.3, 0.17, 0.12, 16), 3.3, ry + 1.5, -1.08, Math.PI / 2);
      hvac(K, 3.2, ry, 1.7); hvac(K, 4.2, ry, 1.7); tank(K, 4.15, ry, -2.55);
      pvRows(K, c.pv, 6, 3, -1.55, ry, 0);
      return { pw: [5.2, 4.4], cced: [3.3, ry + 4.15, -1.4], rect: [-w / 2, w / 2, -s, s + 1.8] };
    },
    hospital(n, K, c) {
      const [w, h] = n.dim, d = 8.5, cz = -1.25, fz = cz + d / 2, f2 = h / 2, ux = w / 2 + 1.65;
      volume(K, w, h, d, 0, cz, { floors: 2 });
      bands(K, w, d, 0, cz, 2, f2, { faces: 'nw', sill: 0.7, h: 1.1 });
      ventanas(K, 's', fz, 0, w - 1.4, f2 + 0.7, 1.1, 1.5);
      ventanas(K, 's', fz, 1.6, 10.4, 0.7, 1.1, 1.5);
      for (let f = 0; f < 2; f++) ventanas(K, 'e', w / 2, -4.25, 1.9, f * f2 + 0.7, 1.1, 1.0);
      // franja roja institucional y aviso con la cruz sobre el antepecho
      fascia(K, 'red', w, d, 0, cz, h + 0.08, 0.28);
      K.box('white', 1.5, 1.2, 0.1, -5.5, h + 0.52, fz - 0.05).box('red', 0.32, 0.9, 0.06, -5.5, h + 0.67, fz + 0.03).box('red', 0.9, 0.32, 0.06, -5.5, h + 0.96, fz + 0.03);
      // acceso con marquesina y puertas de vidrio
      K.box('band', 4.4, 0.24, 2.5, -5.5, 2.45, fz + 1.2).box('glass', 3.0, 2.2, 0.1, -5.5, 0.08, fz + 0.01);
      for (const x of [-7.3, -3.7]) K.cyl('steel', 0.09, 0.09, 2.45, x, 0, fz + 2.2, 8);
      // urgencias con bahía de ambulancias
      volume(K, 3.3, 3.2, 6, ux, 0, { parapet: 0.3 });
      fascia(K, 'red', 3.3, 6, ux, 0, 3.23, 0.22);
      ventanas(K, 'e', w / 2 + 3.3, 0, 4.4, 0.8, 1.1, 1.4);
      K.box('band', 3.0, 0.22, 2.6, ux, 2.6, 4.25).box('glass', 2.2, 2.2, 0.1, ux, 0.08, 3.01);
      for (const x of [ux - 1.3, ux + 1.3]) K.cyl('steel', 0.08, 0.08, 2.6, x, 0, 5.3, 8);
      hvac(K, ux - 0.6, 3.25, -1.6); hvac(K, ux + 0.6, 3.25, -1.6);
      // marquesina solar del parqueadero: columnas, vigas inclinadas y carros bajo la sombra
      const px = 2.0, pz = 5.25;
      for (const x of [px - 4.6, px - 1.55, px + 1.55, px + 4.6]) {
        K.cyl('steel', 0.09, 0.1, 2.75, x, 0, pz - 1.55, 8).cyl('steel', 0.09, 0.1, 2.42, x, 0, pz + 1.55, 8);
        K.rod('steel', [x, 2.78, pz - 1.85], [x, 2.4, pz + 1.85], 0.07);
      }
      pvRows(K, c.pv, 10, 2, px, 2.42, pz, { tilt: 0.1, legs: 0.2, posts: false });
      [-3.95, -0.9, 0.9, 3.95].forEach((x, i) => c.cars.push([px + x, pz, Math.PI / 2, i]));
      pvRows(K, c.pv, 13, 3, 0, h + 0.05, cz);
      return { pw: [10.5, 6.2], gw: [ux + 1.1, 3.25, -2.4], rect: [-w / 2, w / 2 + 3.3, cz - d / 2, pz + 2.0], obst: [[-w / 2, w / 2, cz - d / 2, fz, h + 1.8], [w / 2, w / 2 + 3.3, -3, 5.6, 3.6], [px - 5, px + 5, pz - 2, pz + 2, 3.0]] };
    },
    policia(n, K, c) {
      const [w, h, d] = n.dim, s = d / 2, ry = h + 0.05, mx = w / 2 - 0.6, mz = -s + 0.6;
      volume(K, w, h, d, 0, 0, { floors: 2 });
      bands(K, w, d, 0, 0, 2, h / 2, { faces: 'nse', sill: 0.75, h: 1.1, step: 1.2 });
      ventanas(K, 'w', -w / 2, 0, d - 1.4, h / 2 + 0.75, 1.1, 1.2);
      for (const a of [-1.9, 1.9]) ventanas(K, 'w', -w / 2, a, 1.4, 0.75, 1.1, 1.4);
      fascia(K, 'police', w, d, 0, 0, h + 0.08, 0.26);
      // acceso por la carrera con marquesina, asta y mástil de comunicaciones con baliza
      K.box('glass', 0.1, 2.3, 1.4, -w / 2 - 0.01, 0.08, 0).box('band', 1.5, 0.2, 2.6, -w / 2 - 0.7, 2.5, 0);
      for (const z of [-1.1, 1.1]) K.cyl('steel', 0.06, 0.06, 2.5, -w / 2 - 1.3, 0, z, 6);
      flag(K, -w / 2 - 0.5, -s + 0.3, 6);
      K.cyl('steel', 0.06, 0.11, 6.2, mx, ry, mz, 6).cyl('red', 0.09, 0.09, 0.14, mx, ry + 6.2, mz, 8);
      for (const y of [4.4, 5.4]) K.box('white', 0.1, 0.7, 0.22, mx + 0.16, ry + y, mz);
      tank(K, -2.6, ry, -2.2);
      pvRows(K, c.pv, 5, 2, -0.4, ry, 0.5);
      return { pw: [-3.9, 3.6], gw: [-w / 2 + 0.6, ry, -s + 0.6] };
    },
    bomberos(n, K, c) {
      const [w, h, d] = n.dim, s = d / 2, ry = h + 0.05;
      volume(K, w, h, d, 0, 0, { floors: 2 });
      bands(K, w, d, 0, 0, 1, 0, { sill: 3.45, h: 0.75, step: 1.2 });
      bands(K, w, d, 0, 0, 1, 0, { faces: 'enw', sill: 1.0, h: 1.05, step: 1.3 });
      // dos portones enrollables rojos con juntas y dintel
      for (const x of [-1.35, 1.35]) {
        K.box('red', 2.2, 3.0, 0.1, x, 0.08, s + 0.02).box('trim', 2.4, 0.14, 0.16, x, 3.08, s + 0.04);
        for (let i = 1; i < 7; i++) K.box('dark', 2.2, 0.03, 0.04, x, 0.08 + i * 0.43, s + 0.08);
      }
      fascia(K, 'red', w, d, 0, 0, h + 0.08, 0.26);
      // torre de secado de mangueras con ventanas angostas
      const tx = -w / 2 + 0.6, tz = -s + 0.6;
      K.box('wall', 1.5, 7.6, 1.5, tx, 0, tz).box('band', 1.7, 0.18, 1.7, tx, 7.6, tz).box('red', 1.56, 0.3, 1.56, tx, 7.0, tz);
      for (const y of [4.9, 6.0]) K.box('glass', 0.42, 0.75, 0.1, tx, y, tz - 0.76).box('glass', 0.1, 0.75, 0.42, tx - 0.76, y, tz);
      truck(K, -1.35, s + 2.2);
      hvac(K, -1.6, ry, 2.2);
      pvRows(K, c.pv, 4, 2, 0.8, ry, 0.3);
      return { pw: [-3.7, 2.0], gw: [w / 2 - 0.5, ry, -s + 0.5], obst: [[-w / 2, w / 2, -s, s, h + 0.6], [tx - 0.8, tx + 0.8, tz - 0.8, tz + 0.8, 7.9]] };
    },
    ptap(n, K, c) {
      const [w, h, d] = n.dim, s = d / 2, ry = h + 0.05;
      volume(K, w, h, d, 0, 0, { parapet: 0.35 });
      bands(K, w, d, 0, 0, 1, 0, { faces: 'new', sill: 1.75, h: 0.9, step: 1.4 });
      ventanas(K, 's', s, -1.9, 2.8, 1.75, 0.9, 1.4);
      K.box('steel', 2.6, 2.6, 0.1, 1.6, 0.08, s + 0.02);
      for (let i = 1; i < 8; i++) K.box('dark', 2.6, 0.025, 0.04, 1.6, 0.08 + i * 0.32, s + 0.08);
      // tanques de almacenamiento: anillos, techo cónico, escalera y tubería hacia la planta
      for (const tz of [-5.6, -1.8]) {
        const tx = -6.4;
        K.cyl('band', 1.5, 1.5, 3.2, tx, 0, tz, 28).add('band', new THREE.ConeGeometry(1.6, 0.5, 28), tx, 3.45, tz);
        for (const y of [1.05, 2.15]) K.add('steel', new THREE.TorusGeometry(1.52, 0.04, 4, 36), tx, y, tz, Math.PI / 2);
        for (const zz of [-0.18, 0.18]) K.box('steel', 0.04, 3.4, 0.04, tx + 1.56, 0.08, tz + zz);
        for (let i = 0; i < 9; i++) K.box('steel', 0.04, 0.03, 0.36, tx + 1.56, 0.3 + i * 0.36, tz);
      }
      K.rod('steel', [-4.95, 0.55, -1.2], [-w / 2 + 0.02, 0.55, -1.2], 0.09, 8);
      K.rod('steel', [-5.0, 0.55, -5.0], [-3.0, 0.55, -5.0], 0.09, 8).rod('steel', [-3.0, 0.55, -5.09], [-3.0, 0.55, -s + 0.02], 0.09, 8);
      // floculador abierto con lámina de agua y baranda
      const bz = s + 1.4;
      for (const [bw, bd, bx, bzz] of [[4, 0.2, 0, bz - 0.8], [4, 0.2, 0, bz + 0.8], [0.2, 1.8, -1.9, bz], [0.2, 1.8, 1.9, bz]]) K.box('band', bw, 1.0, bd, bx, 0, bzz);
      K.box('water', 3.56, 0.02, 1.36, 0, 0.84, bz);
      for (const x of [-1.9, -0.6, 0.6, 1.9]) K.cyl('steel', 0.025, 0.025, 0.55, x, 1.0, bz + 0.8, 5);
      K.rod('steel', [-1.9, 1.55, bz + 0.8], [1.9, 1.55, bz + 0.8], 0.025, 4);
      pvRows(K, c.pv, 9, 3, 0, 0.08, 9.0, { legs: 0.95 });
      pvRows(K, c.pv, 6, 3, 0.3, ry, 0);
      hvac(K, 3.3, ry, -2.4);
      return { pw: [-4.4, -6.9], gw: [w / 2 - 0.5, ry, -s + 0.5], rect: [-8.0, w / 2, -7.2, 12.1], obst: [[-w / 2, w / 2, -s, s, h + 0.5], [-8, -4.8, -7.2, -0.2, 3.8], [-4.5, 4.5, 6, 12, 1.6]] };
    },
    colegio(n, K, c) {
      const [w, h, d] = n.dim, t = 2.6, nz = -d / 2 + t / 2, wx = -w / 2 + t / 2, gx0 = -w / 2 + t, gz0 = -d / 2 + t, ry = h + 0.05;
      volume(K, w, h, t, 0, nz, { parapet: 0.35 });
      volume(K, t, h, d - t, wx, t / 2, { parapet: 0.35 });
      ventanas(K, 'n', -d / 2, 0, w - 1.2, 0.95, 1.5, 1.3);
      ventanas(K, 's', gz0, (gx0 + w / 2) / 2, w - t - 1.0, 0.95, 1.5, 1.3);
      ventanas(K, 'w', -w / 2, 0, d - 1.2, 0.95, 1.5, 1.3);
      ventanas(K, 'e', gx0, (gz0 + d / 2) / 2, d - t - 1.0, 0.95, 1.5, 1.3);
      ventanas(K, 'e', w / 2, nz, t - 1.0, 0.95, 1.5, 1.3);
      ventanas(K, 's', d / 2, wx, t - 1.0, 0.95, 1.5, 1.3);
      // galería cubierta hacia el patio
      K.box('band', w - t, 0.14, 1.4, (gx0 + w / 2) / 2, 2.95, gz0 + 0.68).box('band', 1.4, 0.14, d - t - 1.4, gx0 + 0.68, 2.95, (gz0 + 1.4 + d / 2) / 2);
      for (let x = gx0 + 1.6; x < w / 2 - 0.2; x += 2) K.cyl('steel', 0.07, 0.07, 2.95, x, 0, gz0 + 1.25, 6);
      for (let z = gz0 + 3.25; z < d / 2 - 0.2; z += 2) K.cyl('steel', 0.07, 0.07, 2.95, gx0 + 1.25, 0, z, 6);
      // patio: cancha demarcada con aros o zona verde con árboles
      const cx0 = gx0 + 1.9, cx1 = w / 2 - 0.5, cz0 = gz0 + 1.75, cz1 = d / 2 - 0.4, cw = cx1 - cx0, cd = cz1 - cz0, ccx = (cx0 + cx1) / 2, ccz = (cz0 + cz1) / 2;
      if (cd > 1.8) {
        K.box('court', cw, 0.03, cd, ccx, LOT, ccz);
        const y = LOT + 0.03;
        for (const s of [-1, 1]) { c.mk.box('mark', cw - 0.2, 0.008, 0.06, ccx, y, ccz + s * (cd / 2 - 0.1)); c.mk.box('mark', 0.06, 0.008, cd - 0.2, ccx + s * (cw / 2 - 0.1), y, ccz); }
        c.mk.box('mark', 0.06, 0.008, cd - 0.2, ccx, y, ccz).add('mark', new THREE.RingGeometry(0.5, 0.56, 28).rotateX(-Math.PI / 2), ccx, y + 0.008, ccz);
        for (const s of [-1, 1]) K.cyl('steel', 0.04, 0.04, 2.3, ccx + s * (cw / 2 + 0.05), LOT, ccz, 6).box('white', 0.06, 0.5, 0.8, ccx + s * (cw / 2 - 0.08), 1.9, ccz);
      } else {
        K.box('grass', cw, 0.03, Math.max(0.8, cd), ccx, LOT, ccz);
        c.trees.push([ccx - cw / 4, ccz, 0.7], [ccx + cw / 4, ccz, 0.65]);
      }
      flag(K, w / 2 - 0.4, d / 2 - 0.3, 5.5);
      pvRows(K, c.pv, Math.floor((w - 0.9) / 0.99), 1, 0, ry, nz);
      pvRows(K, c.pv, 2, 1, wx, ry, (gz0 + d / 2) / 2);
      return { pw: n.id === 'ie_led' ? [4.0, -3.9] : [-3.6, -3.45], gw: [w / 2 - 0.3, ry, nz - 0.9], obst: [[-w / 2, w / 2, -d / 2, gz0, h + 0.5], [-w / 2, gx0, gz0, d / 2, h + 0.5]] };
    },
    cultura(n, K, c) {
      const [w, , d] = n.dim, s = d / 2;
      if (n.id === 'parque_edu') {
        // Parque Educativo: pabellón de vidrio y volumen de color bajo una cubierta plana en voladizo
        K.box('glass', w - 1.6, 2.9, d - 1.6, 0.3, LOT, 0).box('accent', 2.2, 3.0, d - 1.4, -w / 2 + 1.5, 0, 0);
        for (let x = -0.6; x <= 3.0; x += 0.9) for (const sg of [-1, 1]) K.box('trim', 0.06, 2.9, 0.08, x, LOT, sg * (s - 0.79));
        for (let z = -2.2; z <= 2.2; z += 1.1) K.box('trim', 0.08, 2.9, 0.06, 3.01, LOT, z);
        K.box('band', w + 1.6, 0.32, d + 1.4, 0, 3.15, 0).box('roof', w + 1.2, 0.05, d + 1.0, 0, 3.47, 0);
        for (const [x, z] of [[-3.95, -3.35], [-3.95, 3.35], [3.95, -3.35], [3.95, 3.35], [3.95, 0], [0.3, 3.35], [0.3, -3.35]]) K.cyl('steel', 0.08, 0.08, 3.07, x, LOT, z, 8);
        K.box('band', 3.2, 0.12, 1.3, 1.4, LOT, s + 0.15);
        pvRows(K, c.pv, 7, 3, 0, 3.52, 0);
        return { pw: [4.0, -2.4], gw: [4.0, 3.52, -s - 0.3], rect: [-w / 2 - 0.8, w / 2 + 0.8, -s - 0.7, s + 0.8], obst: [[-w / 2 - 0.8, w / 2 + 0.8, -s - 0.7, s + 0.7, 4.3]] };
      }
      // Casa de la Cultura: muros con vanos de madera, cubierta de teja y corredor con columnas
      const wh = 3.3;
      volume(K, w, wh, d, 0, 0, { parapet: 0 });
      const a = gable(K, w, d, 1.5, 0, wh + 0.1, 0, { eave: 0.5 });
      vanos(K, 'n', -s, 0, w - 2.2, 4, 1.1); vanos(K, 's', s, 0, w - 2.2, 4, 1.1); vanos(K, 'e', w / 2, 0, d - 2.6, 3, 1.1); vanos(K, 'w', -w / 2, 0, d - 2.6, 3, 1.1);
      K.box('wood', 1.2, 2.3, 0.1, 0, LOT, s + 0.02);
      for (let i = 0; i < 5; i++) K.cyl('wood', 0.09, 0.1, 2.55, -w / 2 + 0.6 + (i * (w - 1.2)) / 4, LOT, s + 1.45, 8);
      K.add('tile', new THREE.BoxGeometry(w + 0.6, 0.1, 1.95), 0, 2.88, s + 0.9, 0.35).box('band', w + 0.4, 0.12, 1.8, 0, 0, s + 0.9);
      const dist = 1.55, sp = V(0, wh + 0.1 + 1.5 - Math.sin(a) * dist + Math.cos(a) * 0.13, Math.cos(a) * dist + Math.sin(a) * 0.13);
      pvRows(K, c.pv, 6, 1, 0, sp.y, sp.z, { tilt: 0, rx: a, legs: 0.06, posts: false });
      return { pw: [4.0, -1.5], gw: [-w / 2 + 0.5, wh + 0.2, -s + 0.4], top: wh + 1.8 };
    },
    cuidado(n, K, c) {
      const [w, , d] = n.dim, s = d / 2, wh = 2.6;
      volume(K, w, wh, d, 0, 0, { parapet: 0 });
      const a = gable(K, w, d, 1.25, 0, wh + 0.1, 0, { eave: 0.5 });
      vanos(K, 'n', -s, 0, w - 2, 4, 0.9, 1.0, 1.1); vanos(K, 's', s, 0, w - 2, 4, 0.9, 1.0, 1.1); vanos(K, 'w', -w / 2, 0, d - 2.4, 3, 0.9, 1.0, 1.1); vanos(K, 'e', w / 2, 0, d - 2.4, 3, 0.9, 1.0, 1.1);
      // corredor con columnas, jardín con bancas y materas
      for (let i = 0; i < 5; i++) K.cyl('wood', 0.08, 0.09, 2.2, -w / 2 + 0.5 + (i * (w - 1)) / 4, LOT, s + 0.85, 8);
      K.add('tile', new THREE.BoxGeometry(w + 0.4, 0.1, 1.2), 0, 2.45, s + 0.55, 0.3).box('band', w + 0.2, 0.12, 1.1, 0, 0, s + 0.55);
      K.box('grass', 2.4, 0.03, 3.4, 5.7, LOT, 1.4);
      for (const z of [0.4, 2.4]) K.box('wood', 0.32, 0.06, 0.9, 5.0, 0.45, z).box('steel', 0.3, 0.37, 0.06, 5.0, LOT, z - 0.35).box('steel', 0.3, 0.37, 0.06, 5.0, LOT, z + 0.35);
      for (const z of [-0.1, 2.9]) K.cyl('tile', 0.28, 0.2, 0.45, 6.5, LOT, z, 10).add('foliage', new THREE.IcosahedronGeometry(0.3, 1), 6.5, 0.75, z);
      c.trees.push([6.2, 1.4, 0.6]);
      const dist = 1.35, sp = V(0, wh + 0.1 + 1.25 - Math.sin(a) * dist + Math.cos(a) * 0.13, Math.cos(a) * dist + Math.sin(a) * 0.13);
      pvRows(K, c.pv, 7, 1, 0, sp.y, sp.z, { tilt: 0, rx: a, legs: 0.06, posts: false });
      return { pw: [4.6, -0.6], gw: [-w / 2 + 0.5, wh + 0.2, -s + 0.4], top: wh + 1.5 };
    },
    coliseo(n, K, c) {
      const [w, h, d] = n.dim, wh = h * 0.6, s = d / 2, R = s + 0.25, k = 0.36, y0 = wh + 0.1;
      volume(K, w, wh, d, 0, 0, { parapet: 0 });
      for (let x = -w / 2 + 1; x < w / 2; x += 2) for (const sg of [-1, 1]) K.box('band', 0.32, wh, 0.14, x, 0, sg * (s + 0.05));
      for (const sg of [-1, 1]) K.box('dark', w - 0.5, 0.55, 0.08, 0, wh - 1.0, sg * (s + 0.02));
      // bóveda elíptica con espesor, nervios metálicos y tímpanos de vidrio con parteluces
      K.add('roof', archGeo(R - 0.16, R, k, w + 0.5), 0, y0, 0);
      for (const x of [-4.5, -1.5, 1.5, 4.5]) K.add('band', archGeo(R - 0.05, R + 0.07, k, 0.2), x, y0, 0);
      for (const sg of [-1, 1]) {
        K.add('glass', archGeo(0, R - 0.18, k, 0.06), sg * (w / 2 - 0.03), y0, 0);
        for (let z = -3; z <= 3; z += 1.5) K.box('trim', 0.07, k * Math.sqrt((R - 0.18) ** 2 - z * z), 0.07, sg * (w / 2 + 0.01), y0, z);
      }
      // acceso oriental con marquesina
      K.box('band', 1.5, 0.22, 4.2, w / 2 + 0.7, 2.6, 0).box('glass', 0.1, 2.3, 3.0, w / 2 + 0.01, LOT, 0);
      // paneles sobre la bóveda: dos filas por costado, tangentes a la curva
      const pts = [];
      let acc = 0;
      for (let i = 0; i <= 160; i++) {
        const f = Math.PI / 2 - (i / 160) * (Math.PI / 2), p = [R * Math.cos(f), k * R * Math.sin(f)];
        if (i) acc += Math.hypot(p[0] - pts[i - 1].p[0], p[1] - pts[i - 1].p[1]);
        pts.push({ f, p, acc });
      }
      for (const sd of [1.05, 3.05]) {
        const o = pts.find((q) => q.acc >= sd), nz = Math.cos(o.f) / R, ny = Math.sin(o.f) / (k * R), L = Math.hypot(nz, ny);
        for (const sg of [-1, 1]) pvRows(K, c.pv, 10, 1, 0, y0 + o.p[1] + (ny / L) * 0.1, sg * (o.p[0] + (nz / L) * 0.1), { tilt: 0, rx: sg * Math.atan2(nz, ny), legs: 0, posts: false });
      }
      return { pw: [6.4, -3.9], gw: [w / 2 - 0.2, y0 + k * R, 0.6], top: y0 + k * R + 0.3 };
    },
  };

  const panel = root.querySelector('.node-info');
  const showNode = (n) => {
    const bess = M.bess.filter((b) => b.nodo === n.id);
    panel.innerHTML = `<h4>${n.nombre}</h4>
      <dl class="kv">
        <dt>Consumo supuesto</dt><dd>${fmtN(n.kwh_mes)} kWh/mes</dd>
        <dt>Solar propuesta</dt><dd>${n.pv_kwp ? fmtN(n.pv_kwp) + ' kWp' : '—'}</dd>
        <dt>Baterías</dt><dd>${bess.length ? bess.map((b) => `${fmtN(b.kwh)} kWh / ${fmtN(b.kw)} kW`).join(', ') : '—'}</dd>
        <dt>Prioridad en falla</dt><dd><span class="pill p${n.prioridad}">P${n.prioridad}</span> ${n.isla ? 'en microrred aislable' : 'se desconecta en falla'}</dd>
      </dl>${n.nota ? `<p class="note">${n.nota}</p>` : ''}`;
  };

  // barra de la comunidad energética (subestación compacta en el parque) y CCED en la cubierta de la Alcaldía
  const HB = V(4.4, 0, -2.5);
  const nodeObj = {}, FP = {}, pvList = [], conn = [];
  const LBL = { cultura: 1.8, ie_prim: 0.8 }; // escalones para que las etiquetas vecinas no se encimen
  let ccedPos = V(3.3, 11.7, -10.4);
  M.nodos.forEach((n) => {
    const g = new THREE.Group();
    g.position.set(n.pos[0], 0, n.pos[1]);
    S.add(g);
    if (n.forma === 'virtual' || n.forma === 'alumbrado') { nodeObj[n.id] = { n, g }; return; }
    const K = new Kit(P), c = { pv: [], mk: new Kit(P), trees: [], cars: [] };
    const info = fab[n.forma](n, K, c);
    const [w, h, d] = n.dim, rect = info.rect || [-w / 2, w / 2, -d / 2, d / 2], top = info.top ?? h + 0.5;
    // tablero y poste de acometida orientados hacia la barra; pasarela IoT en la cubierta
    const ry = Math.atan2(HB.x - n.pos[0] - info.pw[0], HB.z - n.pos[1] - info.pw[1]);
    const px = info.pw[0] + Math.cos(ry) * 0.6, pz = info.pw[1] - Math.sin(ry) * 0.6;
    tablero(K, info.pw[0], info.pw[1], ry);
    poste(K, px, pz, ry);
    if (info.gw) gateway(K, ...info.gw);
    const mesh = K.mesh(pal);
    mesh.userData.baseMat = pal;
    g.add(mesh);
    c.mk.into(mk, n.pos[0], 0, n.pos[1]);
    c.pv.forEach((m) => pvList.push(new THREE.Matrix4().makeTranslation(n.pos[0], 0, n.pos[1]).multiply(m)));
    c.trees.forEach(([x, z, sc]) => trees.push([n.pos[0] + x, n.pos[1] + z, sc]));
    c.cars.forEach(([x, z, r, i]) => cars.push([n.pos[0] + x, n.pos[1] + z, r, i]));
    (info.obst || [[...rect, top]]).forEach(([x0, x1, z0, z1, t]) => obst.push([n.pos[0] + x0, n.pos[0] + x1, n.pos[1] + z0, n.pos[1] + z1, t]));
    FP[n.id] = { x0: n.pos[0] + rect[0], x1: n.pos[0] + rect[1], z0: n.pos[1] + rect[2], z1: n.pos[1] + rect[3], top };
    if (info.cced) ccedPos = V(n.pos[0] + info.cced[0], info.cced[1], n.pos[1] + info.cced[2]);
    const lab = st.label(`<b>${n.corto}</b><span class="lv"></span>`, 'lbl-node', [0, h + 2.2 + (LBL[n.id] || 0), 0], g);
    st.pickable(g, { onPick: () => { showNode(n); select(n.id, true); }, onEnter: () => hover(n.id), onLeave: () => hover(null) });
    nodeObj[n.id] = { n, g, lab };
    conn.push({ id: n.id, pw: V(n.pos[0] + px, POSTE, n.pos[1] + pz), gw: info.gw && V(n.pos[0] + info.gw[0], info.gw[1] + 1.0, n.pos[1] + info.gw[2]) });
  });

  // ---- Iglesia (referencia urbana) con campanario y parque principal con quiosco
  {
    const cx = 9.9, cz = -1.4;
    volume(est, 4.2, 4.6, 6.2, cx, cz, { parapet: 0 });
    gable(est, 6.2, 4.2, 1.7, cx, 4.7, cz, { ry: Math.PI / 2, eave: 0.35 });
    vanos(est, 'e', cx + 2.1, cz, 3.8, 4, 1.5, 0.55, 1.9, 'band'); vanos(est, 'w', cx - 2.1, cz, 3.8, 4, 1.5, 0.55, 1.9, 'band');
    const tz = 2.55;
    est.box('wall', 1.9, 8.0, 1.9, cx, 0, tz).box('band', 2.1, 0.2, 2.1, cx, 4.7, tz).box('band', 2.1, 0.2, 2.1, cx, 8.0, tz);
    for (const [ox, oz, rw] of [[0, 0.96, 0], [0, -0.96, 0], [0.96, 0, 1], [-0.96, 0, 1]]) est.box('dark', rw ? 0.04 : 0.7, 1.1, rw ? 0.7 : 0.04, cx + ox, 6.4, tz + oz);
    est.add('tile', new THREE.ConeGeometry(1.3, 2.4, 4), cx, 9.4, tz, 0, Math.PI / 4).box('white', 0.08, 0.9, 0.08, cx, 10.6, tz).box('white', 0.5, 0.08, 0.08, cx, 11.1, tz);
    est.box('wood', 1.0, 2.1, 0.1, cx, LOT, tz + 0.97).add('white', new THREE.CylinderGeometry(0.42, 0.42, 0.06, 20), cx, 3.4, tz + 0.98, Math.PI / 2).add('dark', new THREE.CylinderGeometry(0.3, 0.3, 0.06, 20), cx, 3.4, tz + 1.0, Math.PI / 2);
    est.box('band', 3.0, 0.16, 1.0, cx, 0, tz + 1.45);
    obst.push([cx - 2.1, cx + 2.1, cz - 3.1, cz + 3.1, 6.6], [cx - 1, cx + 1, tz - 1, tz + 1, 11.3]);
    // parque: prado, senderos en cruz, quiosco con columnas y bancas
    const kx = 2.7, kz = -0.7;
    slab(piso, 'grass', 0.0, 5.4, -3.4, 2.0, 0.11, 0.5);
    piso.box('lot', 5.4, 0.13, 0.7, kx, 0, kz).box('lot', 0.7, 0.13, 5.4, kx, 0, kz).cyl('lot', 1.25, 1.25, 0.13, kx, 0, kz, 24);
    est.cyl('band', 0.95, 1.0, 0.2, kx, 0.13, kz, 8);
    for (let i = 0; i < 8; i++) { const a = (i / 8) * Math.PI * 2; est.cyl('white', 0.05, 0.05, 1.7, kx + Math.cos(a) * 0.8, 0.33, kz + Math.sin(a) * 0.8, 6); }
    est.add('tile', new THREE.ConeGeometry(1.25, 0.8, 8), kx, 2.43, kz).cyl('white', 0.04, 0.04, 0.4, kx, 2.8, kz, 5);
    for (const [bx, bz, r] of [[kx - 1.75, kz, 0], [kx + 1.75, kz, 0], [kx, kz + 1.75, 1]]) est.box('wood', r ? 0.9 : 0.32, 0.06, r ? 0.32 : 0.9, bx, 0.45, bz).box('steel', r ? 0.06 : 0.3, 0.32, r ? 0.3 : 0.06, bx - (r ? 0.38 : 0), 0.13, bz - (r ? 0 : 0.38)).box('steel', r ? 0.06 : 0.3, 0.32, r ? 0.3 : 0.06, bx + (r ? 0.38 : 0), 0.13, bz + (r ? 0 : 0.38));
    trees.push([0.6, -2.8, 0.75], [0.6, 1.5, 0.8], [4.9, 1.5, 0.7], [1.6, 0.6, 0.6]);
  }

  // ---- Barra de la comunidad energética: celdas, transformador y barra colectora de cobre sobre aisladores
  est.box('band', 2.8, 0.16, 1.9, HB.x, 0, HB.z);
  est.rbox('cab', 1.5, 1.45, 0.8, 0.05, HB.x - 0.55, 0.16, HB.z - 0.35);
  for (let i = 0; i < 3; i++) est.box('dark', 0.02, 1.2, 0.03, HB.x - 1.05 + i * 0.5, 0.28, HB.z + 0.06);
  est.rbox('cab', 0.9, 1.1, 0.8, 0.05, HB.x + 0.75, 0.16, HB.z - 0.35);
  for (let i = 0; i < 4; i++) est.box('cab', 0.06, 0.8, 0.28, HB.x + 1.23, 0.28, HB.z - 0.62 + i * 0.18);
  for (const x of [-1.1, 0, 1.1]) for (const dz of [-0.22, 0, 0.22]) insulator(est, HB.x + x, x > 0.5 ? 1.26 : 1.61, HB.z - 0.35 + dz, x > 0.5 ? 0.78 : 0.42, 3);
  for (const dz of [-0.22, 0, 0.22]) est.box('copper', 2.5, 0.07, 0.07, HB.x, 2.03, HB.z - 0.35 + dz);
  // pórtico de llegada: aquí terminan las líneas aéreas de cada sede y de la subestación; bajantes a la barra
  const GZ = HB.z + 0.6;
  for (const s of [-1, 1]) est.cyl('band', 0.1, 0.14, 7.0, HB.x + s * 1.35, 0.16, GZ, 8);
  est.box('steel', 3.0, 0.14, 0.14, HB.x, 6.92, GZ);
  for (const x of [-0.9, 0, 0.9]) est.rod('dark', [HB.x + x, 6.92, GZ], [HB.x + x * 0.95, 2.07, HB.z - 0.35], 0.025, 4);
  for (let i = 0; i < 10; i++) { const a = (i / 10) * Math.PI * 2; est.cyl('steel', 0.025, 0.025, 0.9, HB.x + Math.cos(a) * 1.55, 0.16, HB.z + Math.sin(a) * 1.15, 5); }
  st.label('Barra de la comunidad energética', 'lbl-small', [HB.x, 8.5, HB.z]);
  obst.push([HB.x - 1.4, HB.x + 1.4, HB.z - 1, HB.z + 1, 2.3]);

  // ---- Subestación Yondó (EPM): patio de grava con cerramiento, transformador de potencia, pórtico de llegada
  // con cadenas de aisladores y línea de 34,5 kV sobre postes con crucetas hacia Barrancabermeja
  const sx = M.conexion.pos[0], sz = M.conexion.pos[1];
  est.box('gravel', 5.4, 0.1, 5.2, sx, 0, sz);
  for (const s of [-1, 1]) { est.box('band', 5.5, 0.16, 0.12, sx, 0, sz + s * 2.6).box('band', 0.12, 0.16, 5.3, sx + s * 2.7, 0, sz); }
  // cerramiento: postes y dos rieles; portón al oriente, junto a la caseta de control
  for (let i = 0; i <= 8; i++) for (const s of [-1, 1]) {
    est.cyl('steel', 0.035, 0.035, 2.0, sx - 2.65 + i * 0.66, 0.1, sz + s * 2.55, 5);
    if (s < 0 || i < 6 || i === 8) est.cyl('steel', 0.035, 0.035, 2.0, sx + s * 2.65, 0.1, sz - 2.55 + i * 0.64, 5);
  }
  for (const y of [1.0, 2.05]) {
    for (const s of [-1, 1]) est.box('steel', 5.3, 0.04, 0.04, sx, y, sz + s * 2.55);
    est.box('steel', 0.04, 0.04, 5.1, sx - 2.65, y, sz).box('steel', 0.04, 0.04, 3.2, sx + 2.65, y, sz - 0.95);
  }
  const tx = sx + 0.6, tz = sz - 0.6;
  est.rbox('cab', 1.7, 1.5, 1.1, 0.04, tx, 0.1, tz);
  for (let i = 0; i < 6; i++) for (const s of [-1, 1]) est.box('cab', 0.05, 1.15, 0.45, tx - 0.62 + i * 0.25, 0.25, tz + s * 0.78);
  est.add('cab', new THREE.CylinderGeometry(0.22, 0.22, 1.2, 12), tx, 2.0, tz - 0.3, 0, 0, Math.PI / 2).box('steel', 0.08, 0.3, 0.08, tx - 0.4, 1.6, tz - 0.3).box('steel', 0.08, 0.3, 0.08, tx + 0.4, 1.6, tz - 0.3);
  const hv = [-0.4, 0, 0.4].map((dz) => (insulator(est, tx - 0.55, 1.6, tz + dz, 0.85, 5), [tx - 0.55, 2.45, tz + dz]));
  for (const dz of [-0.35, 0, 0.35]) insulator(est, tx + 0.55, 1.6, tz + dz, 0.45, 3);
  const gx = sx - 2.0;
  for (const s of [-1, 1]) { est.box('steel', 0.24, 4.6, 0.24, gx, 0.1, sz + s * 1.6); est.rod('steel', [gx, 0.3, sz + s * 1.6], [gx, 3.2, sz + s * 0.9], 0.04); }
  est.box('steel', 0.2, 0.22, 3.6, gx, 4.5, sz);
  const strings = [-1, 0, 1].map((i) => { const z = sz + i * 0.9; for (let k = 0; k < 5; k++) est.cyl('porcelain', 0.12, 0.12, 0.035, gx, 4.42 - k * 0.11, z, 10); est.cyl('dark', 0.02, 0.02, 0.6, gx, 3.85, z, 4); return [gx, 3.85, z]; });
  strings.forEach((a, i) => est.rod('dark', a, hv[i], 0.02, 4));
  est.box('wall', 1.8, 2.0, 1.4, sx + 1.2, 0.1, sz + 1.5).box('band', 2.0, 0.1, 1.6, sx + 1.2, 2.1, sz + 1.5).box('glass', 0.5, 1.6, 0.06, sx + 0.6, 0.1, sz + 2.22);
  // terminal del alimentador que sale hacia la barra
  const riser = V(sx + 2.25, POSTE, sz - 1.9);
  poste(est, riser.x, riser.z, Math.atan2(HB.x - riser.x, HB.z - riser.z));
  const cat = (a, b, sag) => { const A = V(...a), B = V(...b), Mm = A.clone().lerp(B, 0.5); Mm.y -= sag * 2; est.add('dark', new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(A, Mm, B), 14, 0.025, 4)); };
  for (const px of [-37.6, -42.2]) {
    est.cyl('band', 0.09, 0.15, 7.6, px, 0, sz, 8).box('steel', 0.12, 0.12, 2.4, px, 7.1, sz);
    est.rod('steel', [px, 6.4, sz], [px, 7.1, sz - 0.9], 0.03).rod('steel', [px, 6.4, sz], [px, 7.1, sz + 0.9], 0.03);
    for (const dz of [-0.9, 0, 0.9]) insulator(est, px, 7.22, sz + dz, 0.26, 2);
  }
  for (const dz of [-0.9, 0, 0.9]) { cat([gx, 3.85, sz + dz], [-37.6, 7.48, sz + dz], 0.35); cat([-37.6, 7.48, sz + dz], [-42.2, 7.48, sz + dz], 0.3); cat([-42.2, 7.48, sz + dz], [-44.9, 7.3, sz + dz], 0.15); }
  st.label('S/E Yondó · EPM', 'lbl-node', [sx, 7.5, sz]);
  obst.push([sx - 2.7, sx + 2.7, sz - 2.6, sz + 2.6, 5.2]);

  // ---- Muelle sobre pilotes y chalupas en el río
  est.box('wood', 5.8, 0.12, 1.6, 27.3, 0.02, -24);
  for (let x = 25.2; x <= 30; x += 1.15) for (const s of [-1, 1]) est.cyl('wood', 0.08, 0.08, 0.75, x, -0.62, -24 + s * 0.7, 6);
  boat(est, 31.4, -22.2, 0.15); boat(est, 29.6, -26.1, -0.25);

  // ---- Baterías (contenedores y armarios) con losa, medidor de carga y planta de respaldo
  const PAD = 0.14;
  const BPOS = { bess_hospital: [-25.9, -15.15, Math.PI / 2], bess_ptap: [20.0, 2.6, 0], bess_centro: [0, -14.4, 0], bess_policia: [16.9, -14.0, Math.PI / 2], bess_bomberos: [13.6, -7.8, -Math.PI / 2], bess_cultura: [-10.7, -2.6, -Math.PI / 2], bess_cpsam: [-21.4, -5.6, Math.PI / 2] };
  const bessObjs = M.bess.map((b) => {
    const n = M.nodos.find((x) => x.id === b.nodo);
    const big = b.kwh >= 100, nc = Math.ceil(b.kwh / 15), len = big ? 1.6 + b.kwh / 120 : nc * 0.82, hgt = big ? 2.4 : 1.8, dep = big ? 2.4 : 0.66;
    const [x, z, r] = BPOS[b.id] || [n.pos[0] + n.dim[0] / 2 + 1.4, n.pos[1], 0];
    est.box('band', len + 0.5, PAD, dep + 0.5, x, 0, z, r);
    const c = new THREE.Group(); c.position.set(x, PAD, z); c.rotation.y = r;
    const K = new Kit(P);
    big ? container(K, len, hgt) : cabinets(K, nc);
    const body = K.mesh(pal);
    c.add(body); S.add(c);
    if (big) st.label(`Baterías ${fmtN(b.kwh)} kWh`, 'lbl-small', [0, hgt + 0.8, 0], c);
    st.pickable(c, {
      onPick: () => { panel.innerHTML = `<h4>Baterías LFP · ${n.nombre}</h4><dl class="kv"><dt>Energía</dt><dd>${fmtN(b.kwh)} kWh</dd><dt>Potencia</dt><dd>${fmtN(b.kw)} kW</dd><dt>Función</dt><dd>Autoconsumo de día, respaldo en falla, recorte de pico nocturno</dd></dl>`; select(b.nodo, false); },
      onEnter: () => hover(b.nodo), onLeave: () => hover(null),
    });
    obst.push([x - 1.5, x + 1.5, z - 1.5, z + 1.5, hgt + 0.6]);
    return { b, c, body, big, len, hgt, fw: len - 0.3 };
  });
  // medidores: canal oscuro y barra luminosa que crece con el estado de carga (dos mallas instanciadas)
  const unit = (w, h, d) => new THREE.BoxGeometry(w, h, d).translate(0, h / 2, 0);
  const troughGeo = clean(unit(1, 0.08, 0.32)); troughGeo.setAttribute('aPal', new THREE.BufferAttribute(new Float32Array(troughGeo.attributes.position.count).fill(P.idx.dark), 1));
  const trough = new THREE.InstancedMesh(troughGeo, pal, bessObjs.length);
  const socMat = mat(T.good, { emissive: T.good, emissiveIntensity: 0.5 });
  const fill = new THREE.InstancedMesh(unit(1, 0.1, 0.22), socMat, bessObjs.length);
  S.add(trough, fill);
  const hosp = M.nodos.find((x) => x.id === 'hospital');
  const gen = new THREE.Group();
  {
    const K = new Kit(P);
    K.box('steel', 3.3, 0.18, 1.5, 0, 0, 0).rbox('gen', 3.1, 1.55, 1.35, 0.1, 0, 0.18, 0);
    for (let i = 0; i < 5; i++) for (const s of [-1, 1]) K.box('dark', 0.9, 0.05, 0.04, -0.6, 0.55 + i * 0.18, s * 0.69);
    K.box('dark', 0.04, 1.0, 1.0, 1.56, 0.4, 0).cyl('steel', 0.09, 0.09, 0.9, -1.0, 1.73, 0.3, 8).cyl('steel', 0.15, 0.12, 0.06, -1.0, 2.63, 0.3, 10);
    gen.add(K.mesh(pal));
  }
  gen.position.set(hosp.pos[0] - 8.9, PAD, hosp.pos[1] - 5.3); gen.rotation.y = Math.PI / 2; S.add(gen);
  est.box('band', 3.8, PAD, 2.0, gen.position.x, 0, gen.position.z, Math.PI / 2);
  st.label(`Planta ${M.genset.kw} kW`, 'lbl-small', [0, 3, 0], gen);

  // ---- Arbolado (copas de varios lóbulos), palmas en la orilla, alumbrado y carros (todo instanciado)
  let seed = 11;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let x = -43; x <= 23; x += 4.6) trees.push([x + rnd() * 0.8, -26.6 + rnd() * 0.5, 0.8 + rnd() * 0.35]);
  for (let x = -43; x <= 12; x += 4.6) trees.push([x + rnd() * 0.8, 21.3 + rnd() * 0.5, 0.8 + rnd() * 0.35]);
  for (let z = -33; z <= 33; z += 4.8) if (Math.abs(z + 20) > 3.5 && Math.abs(z + 24) > 2 && Math.abs(z - 18.6) > 2) trees.push([-37.9 - rnd() * 0.4, z + rnd() * 0.6, 0.8 + rnd() * 0.3]);
  const scatter = (n, x0, x1, z0, z1, f) => { for (let i = 0; i < n; i++) { const x = x0 + rnd() * (x1 - x0), z = z0 + rnd() * (z1 - z0); if (!f || f(x, z)) trees.push([x, z, 0.65 + rnd() * 0.6]); } };
  scatter(16, -44, -39.6, -34, 34);
  scatter(16, -44, 23, -34, -28.4, (x) => x < shore(-31) - 1.5);
  scatter(18, -44, 22, 22.8, 34, (x, z) => x < shore(z) - 1.5 && !(x > 12 && z < 23));
  scatter(26, 40, 61, -34, 34, (x, z) => x > shore2(z) + 1.6);
  trees.push([-26.4, 15.9, 0.7], [-15.0, 15.4, 0.75], [13.4, -4.6, 0.65]);
  for (let z = -33; z <= 33; z += 3.4) {
    if ((z > 0 && z < 22.5) || Math.abs(z + 24) < 2.4) continue;
    const x = z > -25 && z < 2 ? shore(z) - 0.8 : shore(z) - 1.3;
    if (z > -25 && z < 2 && x < 24.6) continue;
    palms.push([x, z, 0.85 + rnd() * 0.3]);
  }
  palms.push([-0.1, 2.0, 0.8], [5.4, 2.0, 0.75], [7.9, 4.2, 0.8]);
  const treeGeo = (() => {
    const K = new Kit(P).cyl('trunk', 0.11, 0.17, 1.8, 0, 0, 0, 6);
    for (const [x, y, z, r] of [[0, 2.4, 0, 1.0], [0.55, 2.1, 0.25, 0.72], [-0.5, 2.15, -0.3, 0.75], [0.1, 2.9, -0.1, 0.62]]) K.add('foliage', new THREE.IcosahedronGeometry(r, 1), x, y, z);
    return K.geo();
  })();
  const palmGeo = (() => {
    const K = new Kit(P), t = new THREE.CylinderGeometry(0.1, 0.16, 4.2, 6, 6).translate(0, 2.1, 0), p = t.attributes.position;
    for (let i = 0; i < p.count; i++) p.setX(i, p.getX(i) + 0.35 * (p.getY(i) / 4.2) ** 2);
    t.computeVertexNormals(); K.add('trunk', t);
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2, f = new THREE.ConeGeometry(0.24, 2.0, 3).scale(1, 1, 0.3).translate(0, 1.0, 0);
      f.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(UP, V(Math.cos(a), -0.35 - 0.15 * (i % 2), Math.sin(a)).normalize()));
      K.add('palm', f, 0.35, 4.15, 0);
    }
    return K.geo();
  })();
  const lampGeo = (() => new Kit(P).cyl('steel', 0.1, 0.13, 0.3, 0, 0, 0, 8).cyl('steel', 0.045, 0.07, 3.4, 0, 0.3, 0, 6).rod('steel', [0, 3.55, 0], [0.85, 3.72, 0], 0.035, 5).rbox('lamp', 0.5, 0.09, 0.22, 0.04, 0.95, 3.64, 0).geo())();
  const carGeo = (() => {
    const K = new Kit(P).rbox('paint', 1.9, 0.5, 0.86, 0.14, 0, 0.16, 0).rbox('paint', 1.05, 0.42, 0.78, 0.14, -0.12, 0.6, 0).box('glass', 1.07, 0.25, 0.8, -0.12, 0.7, 0);
    for (const [x, z] of [[0.6, 0.38], [-0.6, 0.38], [0.6, -0.38], [-0.6, -0.38]]) K.add('dark', new THREE.CylinderGeometry(0.19, 0.19, 0.14, 10), x, 0.19, z, Math.PI / 2);
    return K.geo();
  })();
  // postes de alumbrado a un costado de cada vía, con el brazo hacia la calzada
  const lampRow = (fixed, from, to, step, horiz, side, skip) => { for (let v = from; v <= to; v += step) if (!skip || !skip(v)) lamps.push(horiz ? [v, fixed, side > 0 ? Math.PI / 2 : -Math.PI / 2] : [fixed, v, side > 0 ? Math.PI : 0]); };
  lampRow(-22.55, -42, 22, 7, true, 1, (v) => v > -34 && v < -25.5);
  lampRow(17.15, -42, 10, 7, true, -1);
  lampRow(-33.55, -32, 32, 7, false, 1);
  lampRow(5.55, -22, -1, 7, false, -1);
  lampRow(24.45, -22, 0, 7, false, 1);
  lampRow(6.05, -6, 8, 7, true, -1);
  lampRow(3.65, -32, -18, 7, true, 1);
  lampRow(-13.65, 10, 16, 6, false, -1);
  cars.push([10, -22.6, 0, 1], [13.2, -22.6, 0, 5], [18.4, -22.6, Math.PI, 2], [-30, 20.1, 0, 3], [-21.5, 20.1, Math.PI, 0], [2.5, 20.1, 0, 4], [23.0, 4.4, Math.PI / 2, 0]);
  const CAR = [0xf2f2ee, 0xb9bec4, 0xc0392b, 0x2c5aa0, 0x22262a, 0xf2c200];
  const instanced = (geo, m, list, f, colors) => {
    const o = new THREE.InstancedMesh(geo, m, list.length);
    list.forEach((it, i) => { o.setMatrixAt(i, f(it, i)); if (colors) o.setColorAt(i, colors(it, i)); });
    o.castShadow = o.receiveShadow = true;
    S.add(o);
    return o;
  };
  const yAt = (x, z) => (LOTS.some(([x0, x1, z0, z1]) => x > x0 + 0.2 && x < x1 - 0.2 && z > z0 + 0.2 && z < z1 - 0.2) ? LOT : 0);
  const tint = () => new THREE.Color().setRGB(0.82 + rnd() * 0.3, 0.88 + rnd() * 0.22, 0.8 + rnd() * 0.2);
  const treesM = instanced(treeGeo, pal, trees, ([x, z, s]) => _m.compose(V(x, yAt(x, z), z), _q.setFromEuler(_e.set(0, rnd() * 6.3, 0)), V(s, s * (0.9 + rnd() * 0.25), s)), tint);
  const palmsM = instanced(palmGeo, pal, palms, ([x, z, s]) => _m.compose(V(x, yAt(x, z), z), _q.setFromEuler(_e.set(0, rnd() * 6.3, 0)), V(s, s, s)), tint);
  const lampsM = instanced(lampGeo, pal, lamps, ([x, z, r]) => _m.compose(V(x, yAt(x, z), z), _q.setFromEuler(_e.set(0, r, 0)), ONE));
  const carsM = instanced(carGeo, pal, cars, ([x, z, r]) => _m.compose(V(x, yAt(x, z), z), _q.setFromEuler(_e.set(0, r, 0)), ONE), ([, , , i]) => new THREE.Color(CAR[i % CAR.length]));
  // charcos de luz bajo las luminarias, solo de noche (aditivos, sin escribir profundidad)
  const poolMat = new THREE.MeshBasicMaterial({ color: 0xffd27a, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 });
  const pools = instanced(new THREE.CircleGeometry(1.5, 20).rotateX(-Math.PI / 2), poolMat, lamps, ([x, z, r]) => _m.makeTranslation(x + Math.cos(r) * 0.95, 0.034, z - Math.sin(r) * 0.95));
  pools.castShadow = pools.receiveShadow = false;
  pools.visible = false;

  // módulos solares: provisional instanciado (marco + celdas) hasta que carga el GLB del módulo real
  const modGeo = (() => {
    const K = new Kit(P).box('pv', 0.9, 0.035, 1.85, 0, -0.022, 0);
    for (const s of [-1, 1]) K.box('steel', 0.95, 0.045, 0.03, 0, -0.022, s * 0.935).box('steel', 0.03, 0.045, 1.9, s * 0.46, -0.022, 0);
    return K.geo();
  })();
  const pvPh = instanced(modGeo, pal, pvList, (m) => m);
  pvPh.receiveShadow = false;

  // ---- Enlaces: energía (gruesos, amarillo excedente / azul compra) y datos (delgados, morados) con trazos
  // que avanzan en el sentido del flujo; cada arco se eleva lo justo para pasar sobre los edificios
  const obstH = (x, z) => obst.reduce((m, [x0, x1, z0, z1, t]) => (x > x0 - 0.4 && x < x1 + 0.4 && z > z0 - 0.4 && z < z1 + 0.4 ? Math.max(m, t) : m), 0);
  const arcOver = (A, B, base, clear = 0.9) => {
    let lift = base;
    for (let i = 2; i < 30; i++) {
      const t = i / 32, hgt = obstH(A.x + (B.x - A.x) * t, A.z + (B.z - A.z) * t);
      if (!hgt) continue;
      const y0 = (1 - t) ** 2 * A.y + t * t * B.y + 2 * t * (1 - t) * ((A.y + B.y) / 2);
      lift = Math.max(lift, (hgt + clear - y0) / (2 * t * (1 - t)));
    }
    const Mm = A.clone().lerp(B, 0.5); Mm.y += Math.min(lift, 30);
    return new THREE.QuadraticBezierCurve3(A, Mm, B);
  };
  const power = new Links({ dash: 2.6, head: 0.3, widen: 0.12 }), data = new Links({ dash: 1.1, head: 0.72, widen: 0.07 });
  // líneas aéreas de poste a pórtico: cada una llega a su aislador, ordenadas de occidente a oriente
  const feeders = [...conn.map((o) => ({ o, from: o.pw })), { grid: true, from: riser }].sort((a, b) => a.from.x - b.from.x);
  let kGrid = 0;
  feeders.forEach((f, i) => {
    const x = HB.x - 1.2 + (2.4 * i) / (feeders.length - 1), end = V(x, POSTE, GZ);
    insulator(est, x, 7.06, GZ, 0.22, 2);
    const k = power.add(arcOver(f.from, end, 0.7), f.grid ? 0.22 : 0.16);
    if (f.grid) kGrid = k; else nodeObj[f.o.id].kp = k;
  });
  conn.forEach((o) => {
    if (!o.gw) return;
    const end = ccedPos.clone().add(o.gw.clone().sub(ccedPos).setY(0).normalize().multiplyScalar(0.45));
    nodeObj[o.id].kd = data.add(arcOver(o.gw, end, 2.5, 1.2), 0.06);
  });
  power.build(S); data.build(S);
  // ---- Mallas estáticas fusionadas: piso (solo recibe sombra), estructuras y demarcación
  const pisoM = piso.mesh(pal, false), estM = est.mesh(pal), mkM = mk.mesh(palMk, false);
  S.add(pisoM, estM, mkM);
  const cced = new THREE.Mesh(new THREE.IcosahedronGeometry(0.5, 2), new THREE.MeshBasicMaterial({ color: T.data }));
  cced.position.copy(ccedPos); S.add(cced);
  const halo = new THREE.Mesh(new THREE.TorusGeometry(0.85, 0.035, 6, 40), new THREE.MeshBasicMaterial({ color: T.data }));
  halo.position.copy(ccedPos); halo.rotation.x = Math.PI / 2; S.add(halo);
  st.label('CCED · EMS + IoT (MinTIC)', 'lbl-data', [ccedPos.x, ccedPos.y + 2.6, ccedPos.z]);
  const gridMid = riser.clone().lerp(HB, 0.5);
  const brk = st.label('✕ red caída', 'lbl-alert', [gridMid.x, 7, gridMid.z]);

  // ---- Leyenda de enlaces sobre la escena y botón para volver a la vista general
  const leg = document.createElement('div');
  leg.className = 'legend';
  leg.setAttribute('role', 'note');
  leg.style.cssText = 'position:absolute;left:10px;top:10px;z-index:2;display:grid;gap:2px;max-width:calc(100% - 130px);padding:6px 9px;font-size:0.7rem;line-height:1.35;color:var(--ink);background:color-mix(in srgb,var(--surface) 90%,transparent);border:1px solid var(--line);border-radius:8px;pointer-events:none';
  const sw = (bg, h) => `<i style="width:20px;height:${h}px;border-radius:3px;margin-right:6px;vertical-align:middle;background:${bg}"></i>`;
  leg.innerHTML = `<b style="font:600 0.62rem var(--f-mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)">Enlaces<span data-x> · el brillo avanza con el flujo</span></b>
    <span data-l="e">${sw('var(--sun)', 5)}<span data-x>Energía: </span>excedente solar<span data-x> → barra</span></span>
    <span data-l="e">${sw('var(--s1)', 5)}<span data-x>Energía: </span>compra<span data-x> desde la barra</span></span>
    <span data-l="d">${sw('repeating-linear-gradient(90deg,var(--data) 0 4px,transparent 4px 7px)', 2)}Datos IoT<span data-x> → CCED (MinTIC)</span></span>
    <button type="button" class="hud-btn" style="position:static;justify-self:start;margin-top:5px;pointer-events:auto" hidden>Vista general</button>`;
  el.appendChild(leg);
  const homeBtn = leg.querySelector('button');
  // en pantallas angostas la leyenda se abrevia y baja al pie, encima de la ayuda: arriba quedan las etiquetas
  // de las sedes, que el declutter sube para no encimarse
  const hint = el.querySelector('.stage-hint');
  new ResizeObserver(() => {
    const c = el.clientWidth < 560;
    leg.querySelectorAll('[data-x]').forEach((x) => { x.hidden = c; });
    leg.style.top = c ? 'auto' : '10px';
    leg.style.bottom = c ? `${(hint?.offsetHeight || 0) + 16}px` : 'auto';
  }).observe(el);

  // ---- Resalte: al pasar el cursor o elegir una sede, sus enlaces engordan y brillan; el resto se apaga
  let sel = null, hov = null;
  const refocus = () => {
    const o = nodeObj[hov || sel];
    power.focus(o?.kp != null ? [o.kp] : []);
    data.focus(o?.kd != null ? [o.kd] : []);
    st.invalidate();
  };
  function hover(id) { hov = id; refocus(); }
  const ringMat = new THREE.MeshBasicMaterial({ color: T.accent, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
  const ring = new THREE.Mesh(new THREE.BufferGeometry(), ringMat);
  ring.visible = false; S.add(ring);
  function select(id, fly) {
    sel = id; refocus();
    Object.values(nodeObj).forEach((o) => { if (o.lab) o.lab.element.style.borderColor = o.n.id === id ? 'var(--accent)' : ''; });
    const f = id && FP[id];
    ring.visible = !!f;
    homeBtn.hidden = !id;
    if (!f) return;
    const w = f.x1 - f.x0, d = f.z1 - f.z0, sh = rrect(w + 1.3, d + 1.3, 0.8);
    sh.holes.push(rrect(w + 0.8, d + 0.8, 0.55));
    ring.geometry.dispose();
    ring.geometry = new THREE.ShapeGeometry(sh, 4).rotateX(-Math.PI / 2).translate((f.x0 + f.x1) / 2, LOT + 0.015, (f.z0 + f.z1) / 2);
    if (!fly) return;
    // vuelo de cámara: conserva el rumbo actual y encuadra la sede desde unos 50° de altura
    const tg = V((f.x0 + f.x1) / 2, f.top * 0.35, (f.z0 + f.z1) / 2), dir = st.camera.position.clone().sub(st.controls.target).setY(0).normalize();
    const dist = 12 + 1.5 * Math.max(w, d, f.top);
    st.flyTo(tg.clone().add(dir.multiplyScalar(dist * Math.cos(0.87))).add(V(0, dist * Math.sin(0.87), 0)).toArray(), tg.toArray(), 1.2);
  }
  homeBtn.addEventListener('click', () => {
    select(null);
    const k = st.fitFactor ? st.fitFactor() : 1, tg = V(...home.tg);
    st.flyTo(V(...home.pos).sub(tg).multiplyScalar(k).add(tg).toArray(), home.tg, 1.2);
  });

  // ===== Simulación y controles
  const q = (s) => root.querySelector(s);
  const ctl = { hour: q('#mr-hour'), play: q('#mr-play'), nub: q('#mr-nub'), isla: q('#mr-isla'), dr: q('#mr-dr'), dom: q('#mr-dom'), energy: q('#mr-l-energy'), digital: q('#mr-l-data') };
  let sim, hour = 12, playing = !reducedMotion;
  const out = (k, v) => { const e = root.querySelector(`[data-o="${k}"]`); if (e) e.textContent = v; };
  const rerun = () => {
    sim = simulate(M, { nubosidad: +ctl.nub.value / 100, isla: ctl.isla.checked, dr: ctl.dr.checked, domotica: ctl.dom.checked });
    const r = sim.resumen;
    out('auto', `${fmtN(r.autosuficiencia * 100, 0)} %`);
    out('auto-l', ctl.isla.checked ? 'Demanda atendida en isla' : 'Autosuficiencia del día');
    out('crit', `${fmtN(r.criticas_atendidas * 100, 0)} %`);
    out('ahorro', ctl.isla.checked ? '—' : fmtCOP(r.ahorro_cop_dia * 365));
    out('co2', ctl.isla.checked ? '—' : `${fmtN((r.co2_evitado_kg_dia * 365) / 1000, 0)} t`);
    out('diesel', `${fmtN(r.diesel_litros, 0)} L`);
    drawChart();
  };

  // mini-gráfico de 24 h (SVG) con FV, demanda y estado de la batería
  const svg = q('.mr-chart');
  function drawChart() {
    const W = 320, H = 120, pad = 22;
    const s = sim.steps;
    const maxP = Math.max(...s.map((x) => Math.max(x.pv, x.demand))) * 1.1;
    const X = (i) => pad + (i / (STEPS - 1)) * (W - pad - 6), Y = (v) => H - 16 - (v / maxP) * (H - 30);
    const line = (f) => s.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(f(x)).toFixed(1)}`).join('');
    const area = `${line((x) => x.pv)}L${X(STEPS - 1)},${Y(0)}L${X(0)},${Y(0)}Z`;
    const socLine = s.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${(H - 16 - x.soc * (H - 30)).toFixed(1)}`).join('');
    // horas: la primera y la última alineadas hacia adentro para que no se corten en los bordes
    const ticks = [0, 6, 12, 18, 24].map((h) => `<text x="${X(Math.min(STEPS - 1, h * 4))}" y="${H - 3}" text-anchor="${h ? (h === 24 ? 'end' : 'middle') : 'start'}">${h}h</text>`).join('');
    // eje de potencia en valores redondos con su unidad arriba; el borde superior es el 100 % de la batería
    const paso = [10, 20, 25, 50, 100, 200, 250, 500].find((p) => maxP / p <= 3.2) || 1000;
    const yt = Array.from({ length: Math.floor(maxP / paso) + 1 }, (_, i) => i * paso).map((v) => `<line x1="${pad}" x2="${W - 6}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${pad - 3}" y="${Y(v) + 3}" text-anchor="end">${fmtN(v, 0)}</text>`).join('')
      + `<text x="${pad - 3}" y="8" text-anchor="end">kW</text><text x="${W - 6}" y="10" text-anchor="end" class="soc-t">batería 100 %</text>`;
    svg.innerHTML = `${yt}<path d="${area}" class="pv"/><path d="${line((x) => x.served)}" class="dem"/><path d="${socLine}" class="soc"/>${ticks}<line class="now" x1="0" x2="0" y1="8" y2="${H - 16}"/>`;
    svg.dataset.x0 = pad; svg.dataset.w = W - pad - 6;
  }

  const dim = mat(0x555a60, { transparent: true, opacity: 0.45 });
  const WHITE = new THREE.Color(0xffffff), DUSK = new THREE.Color(0xffc58a), MOON = new THREE.Color(0xa9b8ff);
  const sp = reducedMotion ? 0.3 : 1;
  function applyHour() {
    const i = Math.min(STEPS - 1, Math.floor(hour * 4));
    const s = sim.steps[i];
    const isla = ctl.isla.checked;
    const hh = Math.floor(hour), mm = Math.floor((hour % 1) * 60);
    out('hora', `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`);
    out('pv', `${fmtN(s.pv, 0)} kW`); out('dem', `${fmtN(s.served, 0)} kW`);
    out('bat', `${s.batt >= 0 ? 'entrega' : 'carga'} ${fmtN(Math.abs(s.batt), 0)} kW`);
    out('soc', `${fmtN(s.soc * 100, 0)} %`);
    out('red', isla ? 'sin red' : s.grid >= 0 ? `compra ${fmtN(s.grid, 0)} kW` : `vende ${fmtN(-s.grid, 0)} kW`);
    out('gen', `${fmtN(s.gen, 0)} kW`);
    const nl = svg.querySelector('.now'); if (nl) { const x = +svg.dataset.x0 + (i / (STEPS - 1)) * +svg.dataset.w; nl.setAttribute('x1', x); nl.setAttribute('x2', x); }
    // sol, atardecer y luna alta (de noche la luz no viene rasante: sin sombras estiradas ni acné)
    const sun = Math.max(0, Math.sin((Math.PI * (hour - 6)) / 12)), night = sun < 0.08, lampOn = night && !isla;
    st.sunLight.intensity = 0.14 + 1.6 * sun;
    st.hemi.intensity = 0.32 + 0.8 * sun;
    const ang = ((hour - 6) / 12) * Math.PI;
    if (sun > 0.04) st.sunLight.position.set(Math.cos(ang) * 50, 6 + Math.sin(ang) * 50, 18); else st.sunLight.position.set(-16, 46, 24);
    st.sunLight.color.copy(night ? MOON : WHITE.clone().lerp(DUSK, Math.max(0, 0.4 - sun) * 2));
    P.set('glass', night ? 0xffd28f : 0x6f93aa, 0.12, 0.35, 0, night ? 0.55 : 0);
    P.set('lamp', lampOn ? 0xffe0a6 : 0xd9d9d0, 0.4, 0.2, 0, lampOn ? 1.1 : 0);
    pools.visible = lampOn;
    // enlaces por edificio: sentido según excedente o compra; rapidez según la potencia
    const maxKW = 260;
    s.per.forEach((p) => {
      const o = nodeObj[p.id]; if (!o || o.kp == null) return;
      const net = p.served - p.pv, k = Math.min(1, (Math.abs(net) / maxKW) * 2.2);
      power.set(o.kp, Math.abs(net) < 0.5 ? 0 : (net < 0 ? 1 : -1) * (0.45 + 1.4 * k) * sp, net < 0 ? T.sun : T.s[0], ctl.energy.checked && (p.on || !isla));
      if (o.kd != null) data.set(o.kd, 1.1 * sp, T.data, ctl.digital.checked);
      const off = isla && (!p.on || p.served < 1e-3);
      o.g.traverse((m) => { if (m.isMesh && m.userData.baseMat) m.material = off ? dim : m.userData.baseMat; });
      o.lab.element.classList.toggle('off', off);
      o.lab.element.querySelector('.lv').textContent = off ? ' sin servicio' : ` ${net < 0 ? '+' : ''}${fmtN(-net, 0)} kW`;
    });
    const gk = Math.min(1, Math.abs(s.grid) / 400);
    power.set(kGrid, isla ? 0 : (s.grid >= 0 ? 1 : -1) * (0.5 + 1.2 * gk) * sp, isla ? T.muted : s.grid >= 0 ? T.s[0] : T.sun, ctl.energy.checked);
    brk.visible = isla; brk.element.hidden = !isla;
    leg.querySelectorAll('[data-l="e"]').forEach((x) => { x.style.opacity = ctl.energy.checked ? 1 : 0.35; });
    leg.querySelector('[data-l="d"]').style.opacity = ctl.digital.checked ? 1 : 0.35;
    cced.visible = halo.visible = ctl.digital.checked;
    // medidores de carga sobre cada batería
    const kk = Math.max(0.02, s.soc);
    socMat.color.set(s.soc < 0.25 ? T.bad : s.soc < 0.5 ? T.warn : T.good); socMat.emissive.copy(socMat.color);
    bessObjs.forEach((o, j) => {
      o.c.updateMatrixWorld();
      trough.setMatrixAt(j, o.c.matrixWorld.clone().multiply(_m.compose(V(0, o.hgt, 0), _q.identity(), V(o.fw + 0.12, 1, 1))));
      fill.setMatrixAt(j, o.c.matrixWorld.clone().multiply(_m.compose(V((-o.fw * (1 - kk)) / 2, o.hgt + 0.03, 0), _q.identity(), V(o.fw * kk, 1, 1))));
    });
    trough.instanceMatrix.needsUpdate = fill.instanceMatrix.needsUpdate = true;
    P.set('gen', s.gen > 0 ? T.bad : T.s[1], 0.55, 0.1, 0, s.gen > 0 ? 0.5 : 0);
    st.updateShadows();
  }

  ctl.hour.addEventListener('input', () => { hour = +ctl.hour.value / 4; applyHour(); });
  ctl.play.addEventListener('click', () => { playing = !playing; ctl.play.textContent = playing ? 'Pausar' : 'Reproducir día'; ctl.play.setAttribute('aria-pressed', playing); });
  ctl.play.textContent = playing ? 'Pausar' : 'Reproducir día';
  [ctl.nub, ctl.isla, ctl.dr, ctl.dom].forEach((c) => c.addEventListener('input', () => { rerun(); applyHour(); }));
  [ctl.energy, ctl.digital].forEach((c) => c.addEventListener('input', applyHour));
  q('#mr-labels').addEventListener('input', (e) => { st.labels.domElement.hidden = !e.target.checked; });

  rerun(); applyHour();
  showNode(M.nodos.find((n) => n.id === 'hospital'));

  // Presupuesto, fases y mezcla de financiación
  const B = M.presupuesto;
  const directo = B.items.reduce((a, i) => a + i.cantidad * i.unitario, 0);
  const ind = B.indirectos.map((i) => ({ ...i, valor: directo * i.pct }));
  const total = directo + ind.reduce((a, i) => a + i.valor, 0);
  const anual = simulate(M, { nubosidad: 0.3 }).resumen.ahorro_cop_dia * 365;
  root.querySelector('[data-slot="microrred.budget"]').innerHTML = `<table>
    <thead><tr><th>Grupo</th><th>Componente</th><th class="n">Cantidad</th><th class="n">Unitario</th><th class="n">Subtotal</th></tr></thead>
    <tbody>${B.items.map((i) => `<tr><td>${i.grupo}</td><td>${i.componente}<br><span class="note">${i.fuente}</span></td><td class="n">${fmtN(i.cantidad)} ${i.unidad}</td><td class="n">${fmtCOP(i.unitario)}</td><td class="n">${fmtCOP(i.cantidad * i.unitario)}</td></tr>`).join('')}
    <tr><td colspan="4"><b>Costo directo</b></td><td class="n"><b>${fmtCOP(directo)}</b></td></tr>
    ${ind.map((i) => `<tr><td>Indirecto</td><td>${i.componente}</td><td class="n">${fmtN(i.pct * 100, 0)} %</td><td></td><td class="n">${fmtCOP(i.valor)}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="4">Inversión total</td><td class="n">${fmtCOP(total)}</td></tr>
    <tr><td colspan="4">Ahorro anual estimado en facturas (día típico × 365)</td><td class="n">${fmtCOP(anual)}</td></tr>
    <tr><td colspan="4">Retorno simple</td><td class="n">${fmtN(total / anual, 1)} años</td></tr></tfoot></table>
    <div class="cols two" style="margin-top:14px">
      <div><h4>Fases</h4><table><tbody>${B.fases.map((f) => `<tr><td><b>${f.fase}</b><br><span class="note">${f.alcance}</span></td><td class="n">${fmtCOP(total * f.pct)}</td></tr>`).join('')}</tbody></table></div>
      <div><h4>Mezcla de financiación propuesta</h4><table><tbody>${B.financiacion.map((f) => `<tr><td>${f.fuente}</td><td class="n">${fmtN(f.pct * 100, 0)} %</td><td class="n">${fmtCOP(total * f.pct)}</td></tr>`).join('')}</tbody></table></div>
    </div>`;
  root.querySelector('[data-slot="microrred.cols"]').innerHTML = B.cols.map((c) => `<div class="card"><p class="eyebrow">${c.tag}</p><h3>${c.titulo}</h3>${c.html}</div>`).join('');

  // cuadro a cuadro: hora del día, avance de los trazos y pulso del CCED; sin nada que mover no se redibuja
  let acc = 0;
  st.onFrame((dt) => {
    if (playing) {
      hour = (hour + dt * 0.8) % 24; acc += dt;
      if (acc > 0.1) { acc = 0; ctl.hour.value = Math.floor(hour * 4); applyHour(); }
    }
    const flowing = power.live() || data.live();
    if (flowing) { power.u.uT.value += dt; data.u.uT.value += dt; }
    const pulse = ctl.digital.checked && !reducedMotion;
    if (pulse) { const k = 1 + 0.12 * Math.sin(performance.now() / 300); cced.scale.setScalar(k); halo.rotation.z += dt * 0.8; }
    return playing || flowing || pulse;
  });

  // ---- Modelos GLB: módulo solar real instanciado y contenedor de 20 pies escalado a cada capacidad.
  // Las cajas provisionales se ocultan pero siguen sirviendo para tocar la batería (el rayo no mira la visibilidad).
  (async () => {
    try {
      const [pv, bessM] = await Promise.all(['models/modulo_fv.glb', 'models/contenedor_bess.glb'].map((u) => loadModel(u)));
      pvPh.visible = false;
      S.add(instancedFromModel(pv.gltf, pvList, PANEL.scale));
      const big = bessObjs.filter((o) => o.big);
      big.forEach((o) => { o.body.visible = false; o.c.updateMatrixWorld(); });
      if (big.length) S.add(instancedFromModel(bessM.gltf, big.map((o) => o.c.matrixWorld.clone().multiply(new THREE.Matrix4().makeScale(o.len / 6.06, o.hgt / 2.59, o.hgt / 2.44))), 1));
      st.updateShadows();
    } catch (e) { console.warn('Modelos GLB no disponibles; se mantiene la geometría propia', e); }
  })();
  [pisoM, estM, mkM, treesM, palmsM, lampsM, carsM, pools, pvPh, trough, fill, ring, power.mesh, data.mesh, gen, ...bessObjs.map((o) => o.c), ...Object.values(nodeObj).map((o) => o.g)].forEach((o) => st.freeze(o));

  onTheme((t) => {
    Object.assign(T, t);
    paint(t);
    cced.material.color.copy(t.data); halo.material.color.copy(t.data); ringMat.color.copy(t.accent);
    applyHour();
  });
  return st;
}
