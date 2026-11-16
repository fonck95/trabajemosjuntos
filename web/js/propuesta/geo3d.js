// Piezas 3D de la propuesta hechas con geometría propia (sin modelos externos): losas y prismas a partir de polígonos,
// cintas sobre polilíneas, tubos, árboles y palmas instanciados, naves, silos, tanques, graderías, cubiertas tensadas,
// torres de luz, barandas, enrocados, muelles y letras. Todo en metros sobre el plano del modelo: x al oriente y y al
// norte (en three, z = −y). Las piezas nacen con la base en y = 0 para que crezcan desde el piso al animarlas.
import { THREE, mat, gsap } from '../core.js';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { matT, matAgua, tex, texPalma, texHoja } from './texturas.js';

export const V = (x, y, h = 0) => new THREE.Vector3(x, h, -y);
// Une geometrías en una sola (una llamada de dibujo): sin coordenadas de textura, que no todas traen
export function unir(geos) {
  return mergeGeometries(geos.map((g) => { const n = g.index ? g.toNonIndexed() : g.clone(); n.deleteAttribute('uv'); if (!n.attributes.normal) n.computeVertexNormals(); return n; }));
}
const RX = new THREE.Matrix4().makeRotationX(-Math.PI / 2);

// Forma 2D (x, y al norte) que al girar −90° en X queda acostada, con y hacia el norte (−z)
export function forma(pts, huecos = []) {
  const s = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)));
  huecos.forEach((h) => s.holes.push(new THREE.Path(h.map(([x, y]) => new THREE.Vector2(x, y)))));
  return s;
}
// Superficie plana a la altura h
export function losa(pts, h = 0, huecos) {
  const g = new THREE.ShapeGeometry(forma(pts, huecos));
  g.applyMatrix4(RX); g.translate(0, h, 0);
  return g;
}
// Prisma vertical de alto a sobre el polígono (base en h0)
export function prisma(pts, a, h0 = 0, huecos) {
  const g = new THREE.ExtrudeGeometry(forma(pts, huecos), { depth: a, bevelEnabled: false, curveSegments: 6 });
  g.applyMatrix4(RX); g.translate(0, h0, 0);
  return g;
}
// Rectángulo centrado en (cx, cy), de ancho w (eje local x) y fondo d, girado rot radianes (antihorario desde el oriente)
export function rect(cx, cy, w, d, rot = 0) {
  const c = Math.cos(rot), s = Math.sin(rot);
  return [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map(([x, y]) => [cx + x * c - y * s, cy + x * s + y * c]);
}
// Punto local (u al «frente», v a la izquierda) de un marco con origen (ox, oy) y rumbo rot
export const local = (ox, oy, rot) => (u, v) => [ox + u * Math.cos(rot) - v * Math.sin(rot), oy + u * Math.sin(rot) + v * Math.cos(rot)];

// Cinta de ancho fijo sobre una polilínea (andenes, ciclorrutas, senderos, colectores vistos en planta)
export function cinta(pts, ancho, h = 0.05) {
  const pos = [], idx = [], w = ancho / 2;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let dx = b[0] - a[0], dy = b[1] - a[1]; const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    const k = pos.length / 3;
    pos.push(pts[i][0] - dy * w, h, -(pts[i][1] + dx * w), pts[i][0] + dy * w, h, -(pts[i][1] - dx * w));
    if (i) idx.push(k - 2, k - 1, k, k - 1, k + 1, k);   // caras hacia arriba (normal +y): se ven desde la cámara
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
  return g;
}
// Longitud de una polilínea y punto a una fracción t de su recorrido
export function largo(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; }
export function puntoEn(pts, t) {
  const L = largo(pts) * THREE.MathUtils.clamp(t, 0, 1);
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const s = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (acc + s >= L) { const u = s ? (L - acc) / s : 0; return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * u, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * u, Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])]; }
    acc += s;
  }
  const n = pts.length - 1; return [pts[n][0], pts[n][1], n ? Math.atan2(pts[n][1] - pts[n - 1][1], pts[n][0] - pts[n - 1][0]) : 0];
}
// Puntos repartidos cada paso metros a lo largo de la polilínea, corridos off metros a la izquierda (negativo: derecha)
export function aLoLargo(pts, paso, off = 0, desde = 0) {
  const out = [], L = largo(pts);
  for (let s = desde; s <= L; s += paso) { const [x, y, a] = puntoEn(pts, s / L); out.push([x - Math.sin(a) * off, y + Math.cos(a) * off, a]); }
  return out;
}
// Polilínea suavizada (Catmull-Rom centrípeta) con n puntos
export function suave(pts, n = 64) {
  if (pts.length < 3) return pts;
  const c = new THREE.CatmullRomCurve3(pts.map(([x, y]) => new THREE.Vector3(x, y, 0)), false, 'centripetal');
  return c.getSpacedPoints(n).map((p) => [p.x, p.y]);
}
// Tubo sobre una polilínea a la altura h (tuberías y colectores); se dibuja de a poco con revelar()
export function tubo(pts, radio, h = 0.4, segRadio = 8) {
  const curva = new THREE.CatmullRomCurve3(pts.map(([x, y]) => V(x, y, h)), false, 'centripetal', 0.2);
  return new THREE.TubeGeometry(curva, Math.max(16, Math.round(largo(pts) / 4)), radio, segRadio, false);
}
// Contorno de polígono a ras del piso (borde de un predio o de una zona) como cinta cerrada
export function contorno(pts, ancho = 1.2, h = 0.12) { return cinta([...pts, pts[0], pts[1]], ancho, h); }

// Punto dentro de polígono (par-impar)
export function dentro([x, y], poly) {
  let d = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d;
  }
  return d;
}
// distancia de un punto a una polilínea
export function distLinea(p, linea) {
  let d = Infinity;
  for (let i = 1; i < linea.length; i++) {
    const [a, b] = [linea[i - 1], linea[i]], dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    d = Math.min(d, Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy));
  }
  return d;
}
export function area(poly) { let a = 0; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) a += (poly[j][0] + poly[i][0]) * (poly[j][1] - poly[i][1]); return Math.abs(a / 2); }
export function centro(poly) { const n = poly.length; return [poly.reduce((a, p) => a + p[0], 0) / n, poly.reduce((a, p) => a + p[1], 0) / n]; }
// Pseudoaleatorio reproducible: la maqueta sale igual en cada carga
export function azar(semilla = 1) { let s = semilla >>> 0 || 1; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
// Puntos al azar dentro de un polígono, separados al menos sep metros
export function sembrar(poly, n, sep = 4, semilla = 7) {
  const r = azar(semilla), xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)], out = [];
  for (let k = 0; k < n * 40 && out.length < n; k++) {
    const p = [x0 + r() * (x1 - x0), y0 + r() * (y1 - y0)];
    if (dentro(p, poly) && out.every((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) >= sep)) out.push(p);
  }
  return out;
}

// ---------------------------------------------------------------- materiales con nombre
// La escena crea un juego y lo deja como predeterminado de las piezas (usarMateriales). Los de superficie llevan textura en
// coordenadas del mundo (texturas.js): césped, concreto, adoquín, asfalto, pañete, zinc, teja, madera, lona; el color
// real de cada material (ya no el del tema: la maqueta se ve igual en los dos temas y cambia la hora del día)
let MAT = null;
export function usarMateriales(M) { MAT = M; }
export function materiales() {
  const M = {
    verde: matT('cesped', { color: '#d4e3c2' }), verdeOsc: matT('cesped', { color: '#a3b993' }),
    grama: matT('cesped'), arcilla: matT('arcilla'),
    tronco: mat(new THREE.Color('#5e4a38'), { roughness: 1 }), copa: matT('follaje', { color: '#5d8a3c' }),
    concreto: matT('concreto'), adoquin: matT('adoquin'),
    asfalto: matT('asfalto'), muro: matT('estuco', { color: '#f3efe6' }),
    techo: matT('zinc', { color: '#b3bbc0' }), techoRojo: matT('teja'),
    metal: mat(new THREE.Color('#a7afb6'), { roughness: 0.32, metalness: 0.78 }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.45 }),
    madera: matT('madera'), roca: matT('roca', { color: '#a19b8f' }),
    membrana: matT('membrana'),
    agua: matAgua('#5d7468', { transparent: true, opacity: 0.95 }),
    aguaClara: matAgua('#4f93a8'),
    aguaTurbia: matAgua('#6d6a3b', { roughness: 0.3 }),
    luz: new THREE.MeshBasicMaterial({ color: new THREE.Color('#fff1cc') }),
    vidrio: mat(new THREE.Color('#4f6676'), { roughness: 0.05, metalness: 0.7 }),
    solar: mat(new THREE.Color('#1b2944'), { roughness: 0.18, metalness: 0.65 }),
  };
  return M;
}
// Material de color de un módulo, con brillo propio leve para que se lea de lejos
export function matModulo(color, opts = {}) { return mat(new THREE.Color(color), { roughness: 0.6, emissive: new THREE.Color(color), emissiveIntensity: 0.12, ...opts }); }
// Material translúcido para zonas (sectores, áreas de intervención)
export function matZona(color, opacidad = 0.28) {
  return new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: opacidad, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
}

// ---------------------------------------------------------------- vegetación instanciada
// Copas orgánicas: varios volúmenes deformados con una función suave de la posición (sin grietas entre caras) y con normales
// suavizadas, más claros arriba que abajo (sombra propia), con textura de follaje y relieve. Palmas con hojas arqueadas
// recortadas por el alfa (las sombras también salen con la forma de los foliolos). Una llamada de dibujo por especie.
const ondula = (x, y, z, s) => 0.16 * Math.sin(3.1 * x + 1.7 + s) * Math.sin(2.7 * y + 0.3 + s * 0.5) * Math.sin(3.3 * z + 2.1 + s * 0.3) + 0.07 * Math.sin(7.3 * x + 2 * s) * Math.sin(6.1 * z + 1.1);
function bulto(det, s = 0) {
  let g = new THREE.IcosahedronGeometry(1, det); g.deleteAttribute('normal'); g.deleteAttribute('uv'); g = mergeVertices(g);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) { const x = p.getX(i), y = p.getY(i), z = p.getZ(i), k = 1 + ondula(x, y, z, s); p.setXYZ(i, x * k, y * k, z * k); }
  return g;
}
function copaGeo(lumps, det = 1) {
  const g = mergeGeometries(lumps.map(([x, y, z, r], i) => bulto(det, i * 1.3).scale(r, r, r).translate(x, y, z)));
  g.computeVertexNormals();
  const p = g.attributes.position, c = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) { const k = 0.48 + 0.6 * THREE.MathUtils.smoothstep(p.getY(i), -0.95, 1.05); c[i * 3] = c[i * 3 + 1] = c[i * 3 + 2] = k; }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  g.computeBoundingSphere();
  return g;
}
const LUMPS = [[0, 0, 0, 1], [0.62, 0.1, 0.18, 0.62], [-0.52, 0.16, -0.3, 0.6], [0.08, 0.48, -0.42, 0.56], [-0.24, -0.16, 0.54, 0.6], [0.3, 0.38, 0.46, 0.5]];
// tres niveles de detalle: seis volúmenes (proyecto), tres (contexto del pueblo) y uno (potreros y rondas, que se ven de lejos)
const geoCopa = copaGeo(LUMPS), geoCopaSimple = copaGeo(LUMPS.slice(0, 3)), geoCopaLejana = copaGeo([[0, 0, 0, 1.05]], 1);
const geoTronco = unir([
  new THREE.CylinderGeometry(0.12, 0.22, 1, 7).translate(0, 0.5, 0),
  new THREE.CylinderGeometry(0.045, 0.085, 0.42, 5).translate(0, 0.21, 0).rotateZ(0.75).translate(0.04, 0.78, 0),
  new THREE.CylinderGeometry(0.04, 0.08, 0.38, 5).translate(0, 0.19, 0).rotateZ(-0.7).rotateY(2).translate(-0.03, 0.84, 0.02),
]);
// hoja de palma: cinta arqueada en V (raquis arriba, foliolos colgando a los lados), con UV para la textura de foliolos
function fronda(L, W, elev, caida, seg = 9) {
  const pos = [], uv = [], idx = [];
  let x = 0, y = 0;
  for (let i = 0; i <= seg; i++) {
    const t = i / seg, ang = elev - caida * Math.pow(t, 1.35), w = W * Math.pow(Math.sin(Math.PI * (0.12 + 0.88 * t)), 0.55) * (1 - 0.35 * t);
    if (i) { x += Math.cos(ang) * (L / seg); y += Math.sin(ang) * (L / seg); }
    const cae = w * 0.32;
    pos.push(x, y - cae, -w / 2, x, y + 0.03, 0, x, y - cae, w / 2);
    uv.push(t, 0, t, 0.5, t, 1);
    if (i) { const k = i * 3; idx.push(k - 3, k, k - 2, k - 2, k, k + 1, k - 2, k + 1, k - 1, k - 1, k + 1, k + 2); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.setIndex(idx);
  return g;
}
function coronaPalma(n, seg) {
  const hs = [], k = n / 2;
  for (let i = 0; i < n; i++) {
    const alta = i < k, rot = (i / k) * Math.PI * 2 + (alta ? 0 : Math.PI / k) + Math.sin(i * 7.1) * 0.15;
    hs.push(fronda(alta ? 3.3 : 3.6, alta ? 1.15 : 1.25, alta ? 0.95 : 0.45, alta ? 1.25 : 1.35, seg).rotateY(rot));
  }
  const g = mergeGeometries(hs); g.computeVertexNormals(); g.computeBoundingSphere();
  return g;
}
const geoPalmaHojas = coronaPalma(12, 9), geoPalmaSimple = coronaPalma(8, 5);
const geoPalmaTronco = new THREE.CylinderGeometry(0.15, 0.22, 1, 9, 4).translate(0, 0.5, 0);
const COPAS = {
  sombra: ['#3f6b2a', '#4a7a30', '#557f2f', '#3c6a33', '#5f8a35', '#46733a', '#6b8f3a', '#4e7a2c'],
  guayacan: ['#e0619d', '#ea7fb2', '#d24f8f', '#f19ac2', '#e46aa5'],
  flamboyan: ['#e0482a', '#ee6a2e', '#d63b2b', '#f07a3a'],
  amarillo: ['#f0c419', '#e8b40f', '#f4d03a'],
};
const PALETA = Object.fromEntries(Object.entries(COPAS).map(([k, v]) => [k, v.map((c) => new THREE.Color(c))]));
// especie 'mixto': casi todo árboles de sombra, con guayacanes rosados, flamboyanes y guayacanes amarillos
const MIXTO = [['sombra', 0.8], ['guayacan', 0.09], ['flamboyan', 0.07], ['amarillo', 0.04]];
function matsArbol() {
  return arboles.mats || (arboles.mats = {
    tronco: matT('corteza', { color: '#7a6450', escala: 1.4 }),
    copa: matT('follaje', { vertexColors: true }),
  });
}

// puntos: [[x, y], …]; alto: metros (con ±25 % de variación); especie: sombra | guayacan | flamboyan | amarillo | mixto;
// simple: copa de tres volúmenes (contexto del pueblo) o 'lejano', de uno (potreros y rondas). Devuelve un grupo con troncos y
// copas instanciados
export function arboles(puntos, { alto = 8, copa = 0.42, semilla = 3, tronco, especie = 'sombra', simple = false } = {}) {
  const g = new THREE.Group(), n = puntos.length;
  if (!n) return g;
  const r = azar(semilla), M = tronco ? { tronco: tronco.tronco || matsArbol().tronco, copa: matsArbol().copa } : matsArbol();
  const t = new THREE.InstancedMesh(geoTronco, M.tronco, n), c = new THREE.InstancedMesh(simple === 'lejano' ? geoCopaLejana : simple ? geoCopaSimple : geoCopa, M.copa, n);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0);
  puntos.forEach(([x, y], i) => {
    let esp = especie;
    if (esp === 'mixto') { let u = r(); esp = MIXTO.find(([, w]) => (u -= w) < 0)?.[0] || 'sombra'; }
    const flor = esp !== 'sombra', h = alto * (0.75 + r() * 0.5) * (flor ? 0.85 : 1), rc = h * copa * (0.85 + r() * 0.3) * (flor ? 1.12 : 1);
    q.setFromAxisAngle(eje, r() * 6.28);
    m4.compose(V(x, y), q, new THREE.Vector3(1 + rc * 0.05, h * 0.55, 1 + rc * 0.05)); t.setMatrixAt(i, m4);
    m4.compose(V(x, y, h * 0.55 + rc * 0.55), q, new THREE.Vector3(rc, rc * (flor ? 0.7 : 0.8), rc)); c.setMatrixAt(i, m4);
    const pal = PALETA[esp] || PALETA.sombra;
    c.setColorAt(i, pal[Math.floor(r() * pal.length)]);
  });
  [t, c].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); g.add(o); });
  g.userData.instancias = [t, c];
  return g;
}
export function palmas(puntos, { alto = 9, semilla = 5, simple = false } = {}) {
  const g = new THREE.Group(), n = puntos.length;
  if (!n) return g;
  const r = azar(semilla), M = palmas.mats || (palmas.mats = {
    tronco: matT('corteza', { color: '#cdbb9e' }),
    hojas: new THREE.MeshStandardMaterial({ map: texPalma(), alphaTest: 0.45, side: THREE.DoubleSide, roughness: 0.75 }),
  });
  const t = new THREE.InstancedMesh(geoPalmaTronco, M.tronco, n), h = new THREE.InstancedMesh(simple ? geoPalmaSimple : geoPalmaHojas, M.hojas, n);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), col = new THREE.Color();
  puntos.forEach(([x, y], i) => {
    const a = alto * (0.8 + r() * 0.4), s = 0.85 + r() * 0.3, inc = (r() - 0.5) * 0.08;
    q.setFromEuler(e.set(inc, r() * 6.28, (r() - 0.5) * 0.08));
    m4.compose(V(x, y), q, new THREE.Vector3(1, a, 1)); t.setMatrixAt(i, m4);
    const tope = new THREE.Vector3(0, a, 0).applyQuaternion(q);
    m4.compose(V(x, y, 0).add(tope), q, new THREE.Vector3(s, s, s)); h.setMatrixAt(i, m4);
    h.setColorAt(i, col.setHSL(0.24 + r() * 0.04, 0.35 + r() * 0.15, 0.62 + r() * 0.12));
  });
  [t, h].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); g.add(o); });
  g.userData.instancias = [t, h];
  return g;
}
// Matas: hojas lanceoladas que salen de un mismo punto (cordyline roja, heliconia, helecho) y arbustos redondos
function geoMata(n, alto, abre, ancho, semilla) {
  const r = azar(semilla), hojas = [];
  for (let i = 0; i < n; i++) {
    const pos = [], uv = [], idx = [], L = alto * (0.75 + r() * 0.35), tilt = abre * (0.35 + r() * 0.65), seg = 4;
    for (let k = 0; k <= seg; k++) {
      const t = k / seg, x = Math.sin(tilt) * L * t + 0.25 * L * t * t * Math.sin(tilt), y = Math.cos(tilt) * L * t - 0.3 * L * t * t * Math.sin(tilt);
      pos.push(x, y, -ancho / 2, x, y, ancho / 2); uv.push(0, t, 1, t);
      if (k) { const j = k * 2; idx.push(j - 2, j - 1, j, j - 1, j + 1, j); }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.setIndex(idx);
    hojas.push(g.rotateX((r() - 0.5) * 0.6).rotateY(i * 2.39996 + r() * 0.3));
  }
  const g = mergeGeometries(hojas); g.computeVertexNormals();
  const p = g.attributes.position, c = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) { const k = 0.55 + 0.5 * Math.min(1, p.getY(i) / alto); c[i * 3] = c[i * 3 + 1] = c[i * 3 + 2] = k; }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3)); g.computeBoundingSphere();
  return g;
}
const MATAS = {
  cordyline: { geo: () => geoMata(13, 1.0, 0.55, 0.17, 1), colores: ['#7e1d35', '#9b2742', '#b03852', '#6a1a32', '#8c2a3e'] },
  heliconia: { geo: () => geoMata(7, 1.6, 0.5, 0.42, 2), colores: ['#4f7f2e', '#5b8c34', '#46762a'] },
  helecho: { geo: () => geoMata(16, 0.8, 1.05, 0.24, 3), colores: ['#6a9a3a', '#7aa844', '#5d8f34'] },
  arbusto: { geo: () => copaGeo(LUMPS.slice(0, 4)), colores: ['#4b7a2e', '#58863a', '#3f6e2c', '#64903f'] },
};
const geoMatas = {};
// puntos: [[x, y], …]; tipo: cordyline | heliconia | helecho | arbusto; alto: metros (± 20 %)
export function matas(puntos, { tipo = 'arbusto', alto = 1, semilla = 7 } = {}) {
  const g = new THREE.Group(), n = puntos.length, T = MATAS[tipo] || MATAS.arbusto;
  if (!n) return g;
  const M = matas.mats || (matas.mats = {
    hoja: new THREE.MeshStandardMaterial({ map: texHoja(), alphaTest: 0.5, side: THREE.DoubleSide, vertexColors: true, roughness: 0.65 }),
    bulto: matT('follaje', { vertexColors: true, escala: 1.2 }),
  });
  const geo = geoMatas[tipo] || (geoMatas[tipo] = T.geo()), r = azar(semilla), cols = T.colores.map((c) => new THREE.Color(c));
  const im = new THREE.InstancedMesh(geo, tipo === 'arbusto' ? M.bulto : M.hoja, n), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0);
  puntos.forEach(([x, y], i) => {
    const s = alto * (0.8 + r() * 0.4);
    q.setFromAxisAngle(eje, r() * 6.28);
    if (tipo === 'arbusto') m4.compose(V(x, y, s * 0.42), q, new THREE.Vector3(s * 0.6, s * 0.5, s * 0.6)); else m4.compose(V(x, y), q, new THREE.Vector3(s, s, s));
    im.setMatrixAt(i, m4); im.setColorAt(i, cols[Math.floor(r() * cols.length)]);
  });
  im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere(); g.add(im);
  g.userData.instancias = [im];
  return g;
}
// Jardinera mixta: reparte matas de varios tipos en un polígono (lo que llevan los jardines de los renders)
export function jardin(poly, { densidad = 0.6, semilla = 5, tipos = ['cordyline', 'helecho', 'arbusto', 'heliconia'] } = {}) {
  const g = new THREE.Group(), pts = sembrar(poly, Math.max(1, Math.round(area(poly) * densidad)), 0.8, semilla), r = azar(semilla + 1), por = tipos.map(() => []);
  pts.forEach((p) => por[Math.floor(r() * tipos.length)].push(p));
  tipos.forEach((t, i) => { if (por[i].length) g.add(matas(por[i], { tipo: t, alto: t === 'heliconia' ? 1.5 : t === 'arbusto' ? 1.1 : 0.95, semilla: semilla + i * 13 })); });
  g.userData.instancias = g.children.flatMap((h) => h.userData.instancias);
  return g;
}

// ---------------------------------------------------------------- edificaciones simples
// Nave con cubierta a dos aguas (o en arco) centrada en (cx, cy), girada rot; w = luz, d = largo, h = altura de muro
export function nave(cx, cy, w, d, h, rot = 0, { techo = 'dosaguas', muro, cubierta, alero = 0.6 } = {}) {
  const g = new THREE.Group(), mm = muro || MAT.muro, mc = cubierta || MAT.techo;
  const caja = new THREE.Mesh(new THREE.BoxGeometry(w, h, d).translate(0, h / 2, 0), mm);
  let tg;
  if (techo === 'arco') {
    // medio cilindro con el eje a lo largo de la nave (z) y la bóveda hacia arriba
    tg = new THREE.CylinderGeometry(w / 2 + alero, w / 2 + alero, d + alero * 2, 20, 1, true, -Math.PI / 2, Math.PI).rotateX(-Math.PI / 2);
    tg.scale(1, 0.45, 1); tg.translate(0, h, 0);
  } else if (techo === 'plano') {
    tg = new THREE.BoxGeometry(w + alero, 0.35, d + alero).translate(0, h + 0.17, 0);
  } else {
    const p = (w / 2 + alero) * 0.36, s = new THREE.Shape([new THREE.Vector2(-w / 2 - alero, 0), new THREE.Vector2(w / 2 + alero, 0), new THREE.Vector2(0, p)]);
    tg = new THREE.ExtrudeGeometry(s, { depth: d + alero * 2, bevelEnabled: false }).translate(0, 0, -(d + alero * 2) / 2).translate(0, h, 0);
  }
  const techoM = new THREE.Mesh(tg, mc);
  [caja, techoM].forEach((o) => { o.castShadow = true; o.receiveShadow = true; g.add(o); });
  g.position.copy(V(cx, cy)); g.rotation.y = rot;
  return g;
}
// Silo cilíndrico con techo cónico
export function silo(x, y, r, h, m) {
  const g = new THREE.Group(), mm = m || MAT.metal;
  const c = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 20).translate(0, h / 2, 0), mm);
  const t = new THREE.Mesh(new THREE.ConeGeometry(r * 1.04, r * 0.7, 20).translate(0, h + r * 0.35, 0), mm);
  const p = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.75, r * 0.9, 1.6, 16).translate(0, 0.8, 0), MAT.concreto || mm);
  [c, t, p].forEach((o) => { o.castShadow = true; o.receiveShadow = true; g.add(o); });
  g.position.copy(V(x, y));
  return g;
}
// Tanque cilíndrico bajo (reactores, clarificadores, tanques de agua) con borde
export function tanque(x, y, r, h, { m, agua, borde = 0.35 } = {}) {
  const g = new THREE.Group(), mm = m || MAT.concreto;
  const c = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 32, 1, true).translate(0, h / 2, 0), mm);
  c.material = mm.clone(); c.material.side = THREE.DoubleSide;
  const b = new THREE.Mesh(new THREE.TorusGeometry(r, borde / 2, 6, 40).rotateX(Math.PI / 2).translate(0, h, 0), mm);
  g.add(c, b);
  if (agua) { const w = new THREE.Mesh(new THREE.CircleGeometry(r * 0.98, 32).rotateX(-Math.PI / 2).translate(0, h - 0.4, 0), agua); w.receiveShadow = true; g.add(w); }
  const f = new THREE.Mesh(new THREE.CircleGeometry(r, 32).rotateX(-Math.PI / 2).translate(0, 0.05, 0), mm); g.add(f);
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  g.position.copy(V(x, y));
  return g;
}
// Cúpula (biodigestor, reactor cubierto)
export function domo(x, y, r, m) {
  const o = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.7, 1), m || MAT.membrana);
  o.castShadow = true; o.receiveShadow = true; o.position.copy(V(x, y));
  return o;
}
// Graderías escalonadas: w de frente, filas de 0,8 m de huella y 0,42 m de contrahuella; mira hacia rot
export function graderia(cx, cy, w, filas, rot = 0, m) {
  const g = new THREE.Group(), geos = [];
  for (let i = 0; i < filas; i++) geos.push(new THREE.BoxGeometry(w, 0.42 * (i + 1), 0.8).translate(0, 0.21 * (i + 1), -0.4 - i * 0.8));
  const o = new THREE.Mesh(mergeGeometries(geos), m || MAT.concreto);
  o.castShadow = true; o.receiveShadow = true; g.add(o);
  g.position.copy(V(cx, cy)); g.rotation.y = rot;
  return g;
}
// Cubierta tensada (paraboloide hiperbólico) de w × d sobre cuatro mástiles; alto h en dos esquinas y h − flecha en las otras
export function membrana(cx, cy, w, d, h, rot = 0, { flecha = 1.6, m, mastil } = {}) {
  const g = new THREE.Group(), geo = new THREE.PlaneGeometry(w, d, 18, 12), p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) { const u = p.getX(i) / (w / 2), v = p.getY(i) / (d / 2); p.setZ(i, (u * v) * flecha * 0.5 + (1 - u * u) * 0.25 * flecha); }
  geo.computeVertexNormals(); geo.rotateX(-Math.PI / 2); geo.translate(0, h, 0);
  const s = new THREE.Mesh(geo, m || MAT.membrana); s.castShadow = true; s.receiveShadow = true; g.add(s);
  const mg = new THREE.CylinderGeometry(0.12, 0.16, 1, 8).translate(0, 0.5, 0), mm = mastil || MAT.metal;
  [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => { const hh = h + a * b * flecha * 0.5 + 0.3; const o = new THREE.Mesh(mg, mm); o.scale.y = hh; o.position.set(a * w / 2, 0, b * d / 2); o.castShadow = true; g.add(o); });
  g.position.copy(V(cx, cy)); g.rotation.y = rot;
  return g;
}
// Torres de iluminación deportiva LED: poste cónico con base, cabezal con marco y 12 proyectores inclinados hacia el foco
export function torresLuz(puntos, h = 18, { m, luz } = {}) {
  const g = new THREE.Group(), n = puntos.length;
  if (!n) return g;
  const pg = unir([new THREE.CylinderGeometry(0.2, 0.36, h, 8).translate(0, h / 2, 0), new THREE.CylinderGeometry(0.6, 0.66, 0.5, 8).translate(0, 0.25, 0)]);
  const marco = [new THREE.BoxGeometry(0.16, 1.9, 0.16).translate(0, h + 0.75, 0)], caras = [];
  [0, 0.68, 1.36].forEach((dy) => marco.push(new THREE.BoxGeometry(3.5, 0.1, 0.1).translate(0, h + 0.12 + dy, 0.12)));
  [-1.75, 1.75].forEach((x) => marco.push(new THREE.BoxGeometry(0.1, 1.5, 0.1).translate(x, h + 0.8, 0.12)));
  for (let fila = 0; fila < 3; fila++) for (let c = 0; c < 4; c++) {
    const x = -1.2 + c * 0.8, y = h + 0.3 + fila * 0.68;
    marco.push(new THREE.BoxGeometry(0.66, 0.46, 0.26).rotateX(0.5).translate(x, y, 0.36));
    caras.push(new THREE.PlaneGeometry(0.56, 0.36).translate(0, 0, 0.135).rotateX(0.5).translate(x, y, 0.36));
  }
  const P = new THREE.InstancedMesh(pg, m || MAT.metal, n), C = new THREE.InstancedMesh(unir(marco), MAT.oscuro || m, n), L = new THREE.InstancedMesh(unir(caras), luz || MAT.luz, n);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0), uno = new THREE.Vector3(1, 1, 1);
  puntos.forEach(([x, y, haciaX, haciaY], i) => {
    const ang = haciaX != null ? Math.atan2(haciaX - x, -(haciaY - y)) : 0;
    q.setFromAxisAngle(eje, ang); m4.compose(V(x, y), q, uno);
    P.setMatrixAt(i, m4); C.setMatrixAt(i, m4); L.setMatrixAt(i, m4);
  });
  [P, C].forEach((o) => { o.castShadow = true; o.computeBoundingSphere(); g.add(o); });
  L.computeBoundingSphere(); g.add(L);
  return g;
}
// Postes de luz peatonal a lo largo de una polilínea: poste delgado y luminaria LED circular (la cara de abajo y el canto brillan)
export function postes(puntos, h = 4.5, m) {
  const n = puntos.length, g = new THREE.Group();
  if (!n) return g;
  const pg = unir([new THREE.CylinderGeometry(0.05, 0.08, h, 8).translate(0, h / 2, 0), new THREE.CylinderGeometry(0.34, 0.22, 0.13, 16).translate(0, h + 0.065, 0), new THREE.CylinderGeometry(0.13, 0.13, 0.3, 8).translate(0, 0.15, 0)]);
  const lg = unir([new THREE.CircleGeometry(0.3, 16).rotateX(Math.PI / 2).translate(0, h - 0.004, 0), new THREE.CylinderGeometry(0.315, 0.315, 0.035, 16, 1, true).translate(0, h + 0.01, 0)]);
  const P = new THREE.InstancedMesh(pg, m || MAT.oscuro, n), L = new THREE.InstancedMesh(lg, MAT.luz, n), m4 = new THREE.Matrix4();
  puntos.forEach(([x, y], i) => { m4.makeTranslation(x, 0, -y); P.setMatrixAt(i, m4); L.setMatrixAt(i, m4); });
  P.castShadow = true; P.computeBoundingSphere(); L.computeBoundingSphere(); g.add(P, L);
  return g;
}
// Baranda a lo largo de una polilínea a la altura h0 (pasamanos y parales cada 2 m)
export function baranda(pts, h0 = 0, { alto = 1.05, m } = {}) {
  const g = new THREE.Group(), mm = m || MAT.oscuro;
  const pas = new THREE.Mesh(cinta(pts, 0.08, h0 + alto), mm); g.add(pas);
  const ps = aLoLargo(pts, 2), pg = new THREE.BoxGeometry(0.05, alto, 0.05).translate(0, alto / 2, 0);
  const P = new THREE.InstancedMesh(pg, mm, ps.length), m4 = new THREE.Matrix4();
  ps.forEach(([x, y], i) => { m4.makeTranslation(x, h0, -y); P.setMatrixAt(i, m4); });
  P.computeBoundingSphere(); g.add(P);
  return g;
}
// Enrocado: bloques de roca instanciados en una franja (protección de orilla)
export function enrocado(poly, n = 400, { tam = 1.4, alto = 0.6, semilla = 11, m } = {}) {
  const pts = sembrar(poly, n, tam * 0.7, semilla), r = azar(semilla + 1);
  const im = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1, 0), m || MAT.roca, pts.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  pts.forEach(([x, y], i) => {
    const s = tam * (0.6 + r() * 0.7); q.setFromEuler(e.set(r() * 3, r() * 3, r() * 3));
    m4.compose(V(x, y, alto * r()), q, new THREE.Vector3(s, s * 0.7, s)); im.setMatrixAt(i, m4);
  });
  im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere();
  return im;
}

// ---------------------------------------------------------------- casas en serie (vivienda nueva) instanciadas
// Casa de dos pisos en lote de 6 × 12 m: muros de pañete pintado, cubierta de teja a dos aguas paralela a la calle (con
// aleros adelante y atrás, continua de casa a casa), puerta de madera con alero, ventana con reja y alféizar, balcón con
// baranda en el segundo piso, ventanas atrás, antejardín con muro bajo y caminito. Una malla instanciada por material:
// cien casas en nueve llamadas de dibujo. Coordenadas locales: x a lo largo de la calle, +z hacia la calle (la fachada)
const FACHADAS = ['#f3efe6', '#f6e3bd', '#e3eef2', '#f4d6c8', '#e2eed9', '#efe1ec', '#f7efcf', '#dfe7f1', '#f2e6d8', '#e8f0e4'].map((c) => new THREE.Color(c));
const caja = (w, h, d, x, y, z) => new THREE.BoxGeometry(w, h, d).translate(x, y + h / 2, z);
// faldón de cubierta con UV en metros (u a lo largo de la cumbrera, v por la pendiente) para la textura de teja
function faldon(x0, x1, za, ya, zb, yb, esc = 0.5) {
  const L = Math.hypot(zb - za, yb - ya), g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute([x0, ya, za, x1, ya, za, x1, yb, zb, x0, yb, zb], 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute([x0 * esc, 0, x1 * esc, 0, x1 * esc, L * esc, x0 * esc, L * esc], 2));
  g.setIndex(za > zb ? [0, 1, 2, 0, 2, 3] : [0, 2, 1, 0, 3, 2]); g.computeVertexNormals();
  return g;
}
function plantillaCasa({ frente = 6, fondo = 9.5, alto = 2.7, pisos = 2, lote = 12 }) {
  const H = alto * pisos, z0 = -lote / 2 + 0.75, zf = z0 + fondo, zc = z0 + fondo / 2, w = frente - 0.02, e = 0.65, pend = Math.tan(0.35);
  const sube = (fondo / 2) * pend, P = { muro: [], techo: [], marco: [], vidrio: [], luz: [], puerta: [], concreto: [], cesped: [], baranda: [] };
  P.muro.push(caja(w, H, fondo, 0, 0, z0 + fondo / 2));
  // culatas (los triángulos de los extremos, en las dos caras)
  const cul = new THREE.BufferGeometry(), cp = [];
  [-w / 2, w / 2].forEach((x) => cp.push(x, H, z0, x, H + sube, zc, x, H, zf, x, H, z0, x, H, zf, x, H + sube, zc));
  cul.setAttribute('position', new THREE.Float32BufferAttribute(cp, 3)); cul.computeVertexNormals(); P.muro.push(cul);
  P.techo.push(faldon(-frente / 2, frente / 2, z0 - e, H - e * pend, zc, H + sube + 0.05), faldon(-frente / 2, frente / 2, zf + e, H - e * pend, zc, H + sube + 0.05));
  // fachada a la calle: puerta, ventana con reja, alero sobre la puerta, escalón; segundo piso con balcón y ventana
  const zF = zf + 0.03, marco = (x, y, ww, hh) => { P.marco.push(caja(ww + 0.16, 0.08, 0.06, x, y + hh, zF), caja(0.08, hh, 0.06, x - ww / 2 - 0.04, y, zF), caja(0.08, hh, 0.06, x + ww / 2 + 0.04, y, zF)); };
  P.puerta.push(caja(1.0, 2.15, 0.06, -1.7, 0, zF)); marco(-1.7, 0, 1.0, 2.15);
  P.concreto.push(caja(1.7, 0.08, 0.8, -1.7, 2.32, zf + 0.4), caja(1.9, 0.15, 1.0, -1.7, 0, zf + 0.5));
  P.luz.push(caja(1.6, 1.2, 0.04, 1.15, 0.95, zF)); marco(1.15, 0.95, 1.6, 1.2); P.marco.push(caja(1.9, 0.07, 0.16, 1.15, 0.88, zf + 0.07));
  for (let k = 0; k <= 6; k++) P.baranda.push(caja(0.025, 1.2, 0.025, 1.15 - 0.8 + k * (1.6 / 6), 0.95, zf + 0.07));
  P.marco.push(caja(w + 0.06, 0.16, 0.1, 0, alto - 0.08, zf + 0.04));                       // franja del entrepiso
  if (pisos > 1) {
    P.vidrio.push(caja(1.2, 1.1, 0.04, -1.6, alto + 0.95, zF)); marco(-1.6, alto + 0.95, 1.2, 1.1); P.marco.push(caja(1.5, 0.07, 0.16, -1.6, alto + 0.88, zf + 0.07));
    P.luz.push(caja(1.0, 2.1, 0.04, 1.2, alto + 0.05, zF)); marco(1.2, alto + 0.05, 1.0, 2.1);
    P.concreto.push(caja(2.5, 0.12, 0.85, 1.2, alto - 0.02, zf + 0.42));                     // losa del balcón
    P.baranda.push(caja(2.5, 0.05, 0.05, 1.2, alto + 1.0, zf + 0.82), caja(0.05, 1.0, 0.05, -0.05, alto + 0.1, zf + 0.82), caja(0.05, 1.0, 0.05, 2.45, alto + 0.1, zf + 0.82));
    for (let k = 1; k < 10; k++) P.baranda.push(caja(0.022, 0.92, 0.022, -0.05 + k * 0.25, alto + 0.1, zf + 0.82));
  }
  // fachada de atrás: dos ventanas por piso
  for (let p = 0; p < pisos; p++) [-1.5, 1.5].forEach((x) => P.vidrio.push(caja(1.0, 1.0, 0.04, x, p * alto + 1.1, z0 - 0.03)));
  // antejardín: césped, muro bajo con la entrada frente a la puerta y caminito
  const zl = lote / 2;
  P.cesped.push(caja(frente - 0.1, 0.06, zl - zf - 0.1, 0, 0, (zf + zl) / 2));
  const [gx0, gx1] = [-2.3, -1.1];   // la entrada del muro bajo, frente a la puerta
  P.concreto.push(caja(gx0 + frente / 2, 0.55, 0.15, (-frente / 2 + gx0) / 2, 0, zl - 0.1), caja(frente / 2 - gx1, 0.55, 0.15, (frente / 2 + gx1) / 2, 0, zl - 0.1), caja(1.1, 0.07, zl - zf - 0.95, -1.7, 0, (zf + 1.0 + zl) / 2));
  P.marco.push(caja(frente + 0.02, 0.2, 0.08, 0, H - e * pend - 0.18, zf + e - 0.02), caja(frente + 0.02, 0.2, 0.08, 0, H - e * pend - 0.18, z0 - e + 0.02));   // tapacanes
  const out = {};
  for (const [k, gs] of Object.entries(P)) if (gs.length) out[k] = k === 'techo' ? mergeGeometries(gs) : unir(gs);
  return out;
}
const plantillas = new Map();
export function casas(lotes, { frente = 6, fondo = 9.5, alto = 2.7, semilla = 9, lote = 12 } = {}) {
  const g = new THREE.Group(), n = lotes.length;
  if (!n) return g;
  const r = azar(semilla);
  const M = casas.mats || (casas.mats = {
    muro: matT('estuco', { color: '#ffffff' }), techo: new THREE.MeshStandardMaterial({ map: tex('teja'), roughness: 0.78, side: THREE.DoubleSide }),
    marco: matT('estuco', { color: '#fbfaf6' }), vidrio: mat(new THREE.Color('#3e5361'), { roughness: 0.05, metalness: 0.75 }), puerta: matT('madera', { color: '#b58a64' }),
    luz: mat(new THREE.Color('#3e5361'), { roughness: 0.05, metalness: 0.75, emissive: new THREE.Color('#ffc27a'), emissiveIntensity: 0 }),
    concreto: matT('concreto', { color: '#e6e2da' }), cesped: matT('cesped'), baranda: mat(new THREE.Color('#2a2e32'), { roughness: 0.45, metalness: 0.6 }),
  });
  const pisos = Math.max(...lotes.map((l) => l.pisos || 1)), clave = `${frente}|${fondo}|${alto}|${pisos}|${lote}`;
  if (!plantillas.has(clave)) plantillas.set(clave, plantillaCasa({ frente, fondo, alto, pisos, lote }));
  const T = plantillas.get(clave), partes = Object.keys(T);
  const ims = partes.map((k) => new THREE.InstancedMesh(T[k], M[k], n)), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0), uno = new THREE.Vector3(1, 1, 1), tinte = new THREE.Color();
  lotes.forEach((l, i) => {
    q.setFromAxisAngle(eje, l.rot || 0); m4.compose(V(l.x, l.y), q, uno);
    ims.forEach((im) => im.setMatrixAt(i, m4));
    ims[partes.indexOf('muro')].setColorAt(i, FACHADAS[Math.floor(r() * FACHADAS.length)]);
    ims[partes.indexOf('techo')].setColorAt(i, tinte.setRGB(0.9 + r() * 0.1, 0.88 + r() * 0.1, 0.86 + r() * 0.1));
  });
  ims.forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); });
  const muro = ims[partes.indexOf('muro')];
  [muro, ...ims.filter((o) => o !== muro)].forEach((o) => g.add(o));
  g.userData.instancias = g.children.slice();
  g.userData.crecerY = true;   // brotar: todas las partes crecen juntas desde el piso
  g.userData.ventanas = M.luz;   // las ventanas que se encienden al atardecer (emissiveIntensity)
  return g;
}

// ---------------------------------------------------------------- mobiliario, gente y carros instanciados
// Cada función recibe una lista de [x, y, rot] (rot en radianes, antihorario desde el oriente) y devuelve un grupo con una
// malla instanciada por material: decenas de piezas en dos o tres llamadas de dibujo
function instancias(partes, lista, { escala, color } = {}) {
  const g = new THREE.Group(), n = lista.length, m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eje = new THREE.Vector3(0, 1, 0), s = new THREE.Vector3(1, 1, 1);
  if (!n) return g;
  const ims = partes.map(([geo, m]) => new THREE.InstancedMesh(geo, m, n));
  lista.forEach((it, i) => {
    const [x, y, rot = 0] = it;
    q.setFromAxisAngle(eje, rot); const k = escala ? escala(it, i) : 1; s.set(k, k, k);
    m4.compose(V(x, y, it.h || 0), q, s);
    ims.forEach((im, j) => { im.setMatrixAt(i, m4); const c = color?.(it, i, j); if (c) im.setColorAt(i, c); });
  });
  ims.forEach((im) => { im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere(); g.add(im); });
  g.userData.instancias = ims;
  return g;
}
// Banca de concreto con asiento y espaldar de madera (1,8 m)
const geoBanca = {
  base: unir([new THREE.BoxGeometry(0.42, 0.44, 0.56).translate(-0.72, 0.22, 0), new THREE.BoxGeometry(0.42, 0.44, 0.56).translate(0.72, 0.22, 0)]),
  madera: unir([new THREE.BoxGeometry(1.9, 0.07, 0.5).translate(0, 0.475, 0.02), new THREE.BoxGeometry(1.9, 0.36, 0.06).rotateX(-0.12).translate(0, 0.72, -0.24)]),
};
export function bancas(lista) { return instancias([[geoBanca.base, MAT.concreto], [geoBanca.madera, MAT.madera]], lista); }
// Bolardo de luz (0,9 m): poste negro con la franja de luz arriba
const geoBolardo = { poste: unir([new THREE.CylinderGeometry(0.075, 0.085, 0.9, 10).translate(0, 0.45, 0), new THREE.CylinderGeometry(0.09, 0.09, 0.05, 10).translate(0, 0.93, 0)]), luz: new THREE.CylinderGeometry(0.078, 0.078, 0.14, 10).translate(0, 0.78, 0) };
export function bolardos(lista) { return instancias([[geoBolardo.poste, MAT.oscuro], [geoBolardo.luz, MAT.luz]], lista.map(([x, y]) => [x, y, 0])); }
// Caneca con forro de madera y marco negro
const geoCaneca = { madera: new THREE.BoxGeometry(0.46, 0.78, 0.46).translate(0, 0.43, 0), marco: unir([new THREE.BoxGeometry(0.52, 0.06, 0.52).translate(0, 0.85, 0), new THREE.BoxGeometry(0.5, 0.05, 0.5).translate(0, 0.03, 0)]) };
export function canecas(lista) { return instancias([[geoCaneca.madera, MAT.madera], [geoCaneca.marco, MAT.oscuro]], lista); }
// Personas (1,7 m): piernas, torso con brazos y cabeza; colores de camisa, pantalón y piel por persona
const geoPersona = {
  piernas: unir([new THREE.BoxGeometry(0.13, 0.84, 0.16).translate(-0.085, 0.42, 0), new THREE.BoxGeometry(0.13, 0.84, 0.16).translate(0.085, 0.42, 0)]),
  torso: unir([new THREE.CylinderGeometry(0.2, 0.15, 0.62, 8).scale(1, 1, 0.62).translate(0, 1.15, 0), new THREE.BoxGeometry(0.08, 0.56, 0.1).rotateZ(0.07).translate(-0.255, 1.12, 0), new THREE.BoxGeometry(0.08, 0.56, 0.1).rotateZ(-0.07).translate(0.255, 1.12, 0)]),
  cabeza: unir([new THREE.SphereGeometry(0.105, 10, 8).scale(0.95, 1.12, 1).translate(0, 1.6, 0), new THREE.CylinderGeometry(0.05, 0.06, 0.1, 6).translate(0, 1.48, 0)]),
};
const ROPA = ['#f2f2ee', '#2e5fa8', '#c8372d', '#f0c419', '#3a7d44', '#1f2329', '#e07a3a', '#7a4fa0', '#58a6c8', '#d9d2c4'].map((c) => new THREE.Color(c));
const PANT = ['#2b3a55', '#1f2329', '#8a7a5c', '#4a4f55', '#2f4a6b'].map((c) => new THREE.Color(c));
const PIEL = ['#c68a5e', '#a8714a', '#e0b088', '#8d5a3b', '#d9a273', '#b9805a'].map((c) => new THREE.Color(c));
// lista: [[x, y, rot, { camisa, pantalon }?]]; sentado: personas en gradería (piernas dobladas: solo torso y cabeza)
export function gente(lista, { semilla = 3, sentado = false, escala = 1 } = {}) {
  const r = azar(semilla), mp = gente.mat || (gente.mat = new THREE.MeshStandardMaterial({ roughness: 0.85 }));
  const pick = (a) => a[Math.floor(r() * a.length)];
  // colores de cada persona en el orden de las partes: [pantalón, camisa, piel] de pie, [camisa, piel] sentada
  const cols = lista.map((it) => {
    const o = it[3] || {}, camisa = o.camisa ? new THREE.Color(o.camisa) : pick(ROPA), pant = o.pantalon ? new THREE.Color(o.pantalon) : pick(PANT), piel = pick(PIEL);
    return { c: sentado ? [camisa, piel] : [pant, camisa, piel], k: (0.92 + r() * 0.14) * escala };
  });
  const partes = sentado ? [[geoPersona.torso, mp], [geoPersona.cabeza, mp]] : [[geoPersona.piernas, mp], [geoPersona.torso, mp], [geoPersona.cabeza, mp]];
  const pos = lista.map((it) => Object.assign([it[0], it[1], it[2] || 0], { h: (it.h || 0) - (sentado ? 0.42 : 0) }));
  const g = instancias(partes, pos, { escala: (_, i) => cols[i].k, color: (_, i, j) => cols[i].c[j] });
  g.traverse((o) => { if (o.isMesh) o.receiveShadow = false; });
  return g;
}
// Carros (SUV y automóvil de 4,5 m): carrocería extruida con bisel, vidrios oscuros y ruedas
const geoCarro = (() => {
  const perfil = new THREE.Shape([[-2.25, 0.32], [2.2, 0.32], [2.3, 0.72], [2.12, 0.93], [1.2, 1.0], [-1.95, 1.04], [-2.27, 0.92]].map(([x, y]) => new THREE.Vector2(x, y)));
  const cuerpo = new THREE.ExtrudeGeometry(perfil, { depth: 1.72, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.06, bevelSegments: 2, curveSegments: 4 }).translate(0, 0, -0.86);
  const cab = new THREE.Shape([[1.15, 0.98], [0.5, 1.56], [-1.72, 1.6], [-2.02, 1.02]].map(([x, y]) => new THREE.Vector2(x, y)));
  const vidrio = new THREE.ExtrudeGeometry(cab, { depth: 1.56, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelSegments: 1 }).translate(0, 0, -0.78);
  const techo = new THREE.BoxGeometry(2.0, 0.06, 1.5).translate(-0.62, 1.6, 0);
  const ruedas = unir([[-1.42, 0.82], [1.42, 0.82], [-1.42, -0.82], [1.42, -0.82]].map(([x, z]) => new THREE.CylinderGeometry(0.36, 0.36, 0.26, 14).rotateX(Math.PI / 2).translate(x, 0.36, z)));
  return { cuerpo: unir([cuerpo, techo]), vidrio: unir([vidrio]), ruedas };
})();
const PINTURA = ['#e9ebed', '#f4f4f2', '#b9bec3', '#8c9298', '#1f2326', '#e9ebed', '#9b2b26', '#2b4a7a', '#d8dadc', '#5a5f63'].map((c) => new THREE.Color(c));
export function carros(lista, { semilla = 9 } = {}) {
  const r = azar(semilla), M = carros.mats || (carros.mats = {
    cuerpo: new THREE.MeshStandardMaterial({ roughness: 0.28, metalness: 0.55 }), vidrio: new THREE.MeshStandardMaterial({ color: 0x1c2329, roughness: 0.06, metalness: 0.8 }), ruedas: new THREE.MeshStandardMaterial({ color: 0x17191b, roughness: 0.8 }),
  });
  const cols = lista.map((it) => (it[3] ? new THREE.Color(it[3]) : PINTURA[Math.floor(r() * PINTURA.length)]));
  return instancias([[geoCarro.cuerpo, M.cuerpo], [geoCarro.vidrio, M.vidrio], [geoCarro.ruedas, M.ruedas]], lista, { color: (_, i, j) => (j === 0 ? cols[i] : null) });
}

// ---------------------------------------------------------------- letras 3D
let fuente = null;
export async function letras(texto, { alto = 2.2, fondo = 0.6, colores = ['#e3141b'], acento = -1, separacion = 0.25 } = {}) {
  const [{ FontLoader }, { TextGeometry }] = await Promise.all([import('three/addons/loaders/FontLoader.js'), import('three/addons/geometries/TextGeometry.js')]);
  fuente = fuente || await new FontLoader().loadAsync('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/fonts/helvetiker_bold.typeface.json');
  const g = new THREE.Group();
  let x = 0;
  [...texto].forEach((ch, i) => {
    const geo = new TextGeometry(ch, { font: fuente, size: alto, height: fondo, curveSegments: 6, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.04, bevelSegments: 2 });
    geo.computeBoundingBox();
    const bb = geo.boundingBox, w = bb.max.x - bb.min.x;
    const m = mat(new THREE.Color(colores[i % colores.length]), { roughness: 0.45, emissive: new THREE.Color(colores[i % colores.length]), emissiveIntensity: 0.25 });
    const o = new THREE.Mesh(geo, m); o.position.x = x - bb.min.x; o.castShadow = true; g.add(o);
    if (i === acento) { // tilde: la fuente no trae «Ó»
      const t = new THREE.Mesh(new THREE.BoxGeometry(w * 0.32, alto * 0.13, fondo).rotateZ(0.6), m);
      t.position.set(x + w * 0.62, alto * 1.16, fondo / 2); t.castShadow = true; g.add(t);
    }
    x += w + separacion;
  });
  g.children.forEach((o) => { o.position.x -= x / 2; });
  return g;
}

// ---------------------------------------------------------------- animaciones (GSAP; sin GSAP saltan al final)
// Crece un objeto desde el piso (escala vertical)
export function crecer(obj, { duracion = 0.9, retraso = 0, tl, alFinal, onUpdate } = {}) {
  if (!gsap) { obj.scale.y = 1; alFinal?.(); return; }
  const tw = { y: 0.001 };
  const fn = () => { obj.scale.y = tw.y; onUpdate?.(); };
  const anim = gsap.fromTo(tw, { y: 0.001 }, { y: 1, duration: duracion, delay: tl ? 0 : retraso, ease: 'back.out(1.4)', onUpdate: fn, onComplete: alFinal });
  if (tl) tl.add(anim, retraso);
  return anim;
}
// Hace aparecer las instancias de un grupo una tras otra (casas, árboles) desde el piso
export function brotar(grupo, { duracion = 1.6, tl, retraso = 0, onUpdate, alFinal } = {}) {
  const ims = grupo.userData.instancias || [];
  if (!ims.length) return null;
  ims.forEach((im) => { if (!im.userData.base) { im.userData.base = []; const m4 = new THREE.Matrix4(); for (let i = 0; i < im.count; i++) { im.getMatrixAt(i, m4); im.userData.base.push(m4.clone()); } } });
  const n = ims[0].count, p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3(), m4 = new THREE.Matrix4();
  const aplicar = (u) => {
    ims.forEach((im) => {
      for (let i = 0; i < im.count; i++) {
        const k = THREE.MathUtils.clamp(u * (1 + 0.6) - (i / Math.max(1, n - 1)) * 0.6, 0, 1), e = k < 1 ? 1 - Math.pow(1 - k, 3) : 1;
        im.userData.base[i].decompose(p, q, s);
        if (im === ims[0] || grupo.userData.crecerY) { s.y *= Math.max(0.001, e); } else { p.y *= Math.max(0.001, e); s.multiplyScalar(Math.max(0.001, e)); }
        m4.compose(p, q, s); im.setMatrixAt(i, m4);
      }
      im.instanceMatrix.needsUpdate = true;
    });
    onUpdate?.();
  };
  if (!gsap) { aplicar(1); alFinal?.(); return null; }
  const o = { u: 0 };
  aplicar(0);
  const anim = gsap.to(o, { u: 1, duration: duracion, ease: 'none', delay: tl ? 0 : retraso, onUpdate: () => aplicar(o.u), onComplete: alFinal });
  if (tl) tl.add(anim, retraso);
  return anim;
}
// Dibuja de a poco una geometría indexada o no (tubos, cintas): drawRange de 0 al total
export function revelar(mesh, { duracion = 1.4, tl, retraso = 0, onUpdate } = {}) {
  const g = mesh.geometry, total = g.index ? g.index.count : g.attributes.position.count;
  if (!gsap) { g.setDrawRange(0, Infinity); return null; }
  const o = { u: 0 };
  g.setDrawRange(0, 0);
  const anim = gsap.to(o, { u: 1, duration: duracion, ease: 'power2.inOut', delay: tl ? 0 : retraso, onUpdate: () => { g.setDrawRange(0, Math.floor((total * o.u) / 6) * 6); onUpdate?.(); }, onComplete: () => g.setDrawRange(0, Infinity) });
  if (tl) tl.add(anim, retraso);
  return anim;
}
