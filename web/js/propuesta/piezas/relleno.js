// Relleno sanitario municipal nuevo (vereda Kilómetro Cinco): predio en grama con cerco de malla y franja de árboles,
// celdas por fases (la de la fase 1 como un cerro de tres terrazas de 3 m con taludes reales de 3H:1V y bermas de 1,5 m con
// cuneta; las dos de abajo, cerradas y con pasto, con bajantes escalonados y chimeneas de biogás; la de arriba, la cara
// activa, con geomembrana, zanja de anclaje, el frente de descargue, el compactador pata de cabra, la volqueta y los
// operarios; una rampa de afirmado sube desde la vía interna), lagunas de lixiviados con dique, geomembrana, cerco y caseta
// de bombeo, ECA abierta con banda de clasificación y pacas, compostaje en hileras con volteadora, portería con báscula,
// talanquera y camión recolector, vías internas de afirmado con cunetas, pozos de monitoreo y alumbrado. Todo va en metros
// del modelo: los polígonos y las vías vienen de geo.json (saneamiento) y la función solo los arma. Las piezas se juntan
// por material (acopio): unas pocas mallas por grupo, más las instanciadas (árboles, gente, pacas, residuos).
import { THREE, mat } from '../../core.js';
import { losa, cinta, arboles, palmas, gente, postes, jardin, aLoLargo, centro, dentro, distLinea, unir, azar, local, V } from '../geo3d.js';
import { matT, matAgua } from '../texturas.js';

const capa = (raiz, n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
// terrazas de la celda de la fase 1: alto de cada una, ancho horizontal de su talud (3H:1V) y de la berma que la separa de
// la siguiente; BASE: la celda arranca un poco por encima de la losa del predio (así el pie del talud no titila con ella)
const TERRAZAS = 3, ALTO = 3, TALUD = 3 * ALTO, BERMA = 1.5, RETIRO = TALUD + BERMA, BASE = 0.1, CIMA = TERRAZAS * ALTO + BASE;

function cruce([a, b], [c, d]) {
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
  return [a[0] + t * r[0], a[1] + t * r[1]];
}
// polígono convexo desplazado d metros hacia adentro (cada lado se corre y se corta con el vecino), en cualquier sentido
export function adentro(poly, d) {
  const n = poly.length, area = poly.reduce((a, p, i) => { const q = poly[(i + 1) % n]; return a + p[0] * q[1] - q[0] * p[1]; }, 0), s = area > 0 ? 1 : -1;
  const lados = poly.map((p, i) => {
    const q = poly[(i + 1) % n], dx = q[0] - p[0], dy = q[1] - p[1], L = Math.hypot(dx, dy) || 1, nx = (-dy / L) * s, ny = (dx / L) * s;
    return [[p[0] + nx * d, p[1] + ny * d], [q[0] + nx * d, q[1] + ny * d]];
  });
  return lados.map((l, i) => cruce(lados[(i + n - 1) % n], l) || l[0]);
}
// puntos cada «paso» metros a lo largo de cada lado del polígono, corridos «d» metros hacia adentro; sirve para polígonos
// no convexos porque descarta los que caen fuera
function franja(poly, d, paso) {
  const n = poly.length, s = poly.reduce((a, p, i) => { const q = poly[(i + 1) % n]; return a + p[0] * q[1] - q[0] * p[1]; }, 0) > 0 ? 1 : -1, out = [];
  poly.forEach((p, i) => {
    const q = poly[(i + 1) % n], dx = q[0] - p[0], dy = q[1] - p[1], L = Math.hypot(dx, dy);
    if (L < 1) return;
    const nx = (-dy / L) * s, ny = (dx / L) * s;
    for (let t = paso / 2; t < L; t += paso) {
      const pt = [p[0] + (dx * t) / L + nx * d, p[1] + (dy * t) / L + ny * d];
      if (dentro(pt, poly) && !out.some((o) => Math.hypot(o[0] - pt[0], o[1] - pt[1]) < paso * 0.6)) out.push(pt);
    }
  });
  return out;
}
// ángulo (radianes, antihorario desde el oriente) del lado más largo y medidas del polígono en ese marco
function marcoDe(poly) {
  let mejor = 0, ang = 0;
  poly.forEach((p, i) => { const q = poly[(i + 1) % poly.length], L = Math.hypot(q[0] - p[0], q[1] - p[1]); if (L > mejor) { mejor = L; ang = Math.atan2(q[1] - p[1], q[0] - p[0]); } });
  const [cx, cy] = centro(poly), c = Math.cos(ang), s = Math.sin(ang);
  const us = poly.map(([x, y]) => (x - cx) * c + (y - cy) * s), vs = poly.map(([x, y]) => -(x - cx) * s + (y - cy) * c);
  return { cx, cy, ang, w: Math.max(...us) - Math.min(...us), d: Math.max(...vs) - Math.min(...vs) };
}
// polilínea corrida d metros a la izquierda (cunetas a los lados de una vía)
export function paralela(pts, d) {
  return pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let dx = b[0] - a[0], dy = b[1] - a[1]; const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    return [p[0] - dy * d, p[1] + dx * d];
  });
}

// ---------------------------------------------------------------- geometría
// caja con la base en y (marco local: x al frente, z a un lado) y cilindro vertical con la base en y
export const caja = (w, h, d, x = 0, y = 0, z = 0) => new THREE.BoxGeometry(w, h, d).translate(x, y + h / 2, z);
export const cil = (r, h, x = 0, y = 0, z = 0, seg = 12, r2 = r) => new THREE.CylinderGeometry(r, r2, h, seg).translate(x, y + h / 2, z);
// lleva una geometría del marco local (x al frente, y arriba, z a la derecha) al punto (x, y) del modelo con rumbo rot
export const ubicar = (g, x, y, rot = 0, h = 0) => g.rotateY(rot).translate(x, h, -y);
/**
 * Acopio de piezas por material: put(material, …geometrías) en coordenadas de three; poner(plantilla, x, y, rot, h) copia
 * una plantilla local ({ material: [geometrías] }) al modelo; volcar(padre, M) une todo en una malla por material y
 * unidas() lo devuelve unido por material (para instanciarlo).
 */
export function acopio() {
  const P = {};
  const put = (k, ...gs) => { (P[k] || (P[k] = [])).push(...gs); };
  const poner = (T, x, y, rot = 0, h = 0) => Object.entries(T).forEach(([k, gs]) => gs.forEach((g) => put(k, ubicar(g.clone(), x, y, rot, h))));
  const volcar = (padre, M, { sombra = true } = {}) => {
    Object.entries(P).forEach(([k, gs]) => {
      if (!gs.length) return;
      if (!M[k]) throw new Error(`acopio sin material: ${k}`);
      const o = new THREE.Mesh(unir(gs), M[k]); o.castShadow = sombra && !M[k].transparent; o.receiveShadow = true; padre.add(o);
    });
    Object.keys(P).forEach((k) => delete P[k]);
  };
  // la plantilla unida (una geometría por material) para instanciarla en varios sitios
  const unidas = () => { const o = {}; Object.entries(P).forEach(([k, gs]) => { if (gs.length) o[k] = unir(gs); }); Object.keys(P).forEach((k) => delete P[k]); return o; };
  return { put, poner, volcar, unidas };
}
// anillo de caras entre dos polígonos con los mismos vértices (a a la altura ha, b a la altura hb): taludes, bermas y
// diques. Cada cuadrilátero queda con la normal hacia arriba, sea cual sea el sentido del polígono
function anillo(a, ha, b, hb) {
  const pos = [], n = a.length, e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n, q = [V(a[i][0], a[i][1], ha), V(a[j][0], a[j][1], ha), V(b[j][0], b[j][1], hb), V(b[i][0], b[i][1], hb)];
    e1.subVectors(q[1], q[0]); e2.subVectors(q[2], q[0]);
    (e1.cross(e2).y >= 0 ? [0, 1, 2, 0, 2, 3] : [0, 2, 1, 0, 3, 2]).forEach((k) => pos.push(q[k].x, q[k].y, q[k].z));
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.computeVertexNormals();
  return g;
}
// cuadriláteros sueltos (rampas): lista de [a, b, c, d] en coordenadas de three; se ven de los dos lados (material)
function caras(quads) {
  const pos = [];
  quads.forEach((q) => [0, 1, 2, 0, 2, 3].forEach((k) => pos.push(q[k].x, q[k].y, q[k].z)));
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.computeVertexNormals();
  return g;
}
/**
 * Cerco de malla eslabonada de «alto» m sobre una polilínea: paños de malla, postes de concreto cada «paso» m y alambre
 * arriba. Los tramos cuyo centro cae a menos de «hueco» m de una de las «puertas» quedan abiertos (portones).
 */
export function cerco(A, pts, { alto = 2.2, paso = 3, puertas = [], hueco = 5, malla = 'malla', poste = 'poste' } = {}) {
  const libres = [];
  for (let i = 1; i < pts.length; i++) {
    const [a, b] = [pts[i - 1], pts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L < 0.5) continue;
    const n = Math.max(1, Math.round(L / paso)), ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
    for (let k = 0; k < n; k++) {
      const p0 = [a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n], p1 = [a[0] + ((b[0] - a[0]) * (k + 1)) / n, a[1] + ((b[1] - a[1]) * (k + 1)) / n];
      const m = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2], l = L / n;
      if (puertas.some((p) => Math.hypot(p[0] - m[0], p[1] - m[1]) < hueco)) { libres.push(p0, p1); continue; }
      A.put(malla, new THREE.PlaneGeometry(l, alto - 0.15).rotateY(ang).translate(m[0], 0.15 + (alto - 0.15) / 2, -m[1]));
      A.put('oscuro', new THREE.BoxGeometry(l, 0.04, 0.04).rotateY(ang).translate(m[0], alto, -m[1]));
      A.put(poste, caja(0.14, alto + 0.15, 0.14, p0[0], 0, -p0[1]));
    }
  }
  const u = pts[pts.length - 1]; A.put(poste, caja(0.14, alto + 0.15, 0.14, u[0], 0, -u[1]));
  return libres;
}

// ---------------------------------------------------------------- vehículos y máquinas (plantillas locales: x al frente)
const rueda = (x, z, r = 0.5, w = 0.4) => new THREE.CylinderGeometry(r, r, w, 14).rotateX(Math.PI / 2).translate(x, r, z);
// compactador de relleno pata de cabra: motor atrás, cabina, hoja adelante y cuatro tambores con patas
function compactador() {
  const T = { amarillo: [], oscuro: [], vidrio: [], acero: [] };
  T.amarillo.push(caja(2.8, 1.5, 2.3, -2.2, 1.0, 0), caja(3.4, 0.6, 1.2, 0.6, 0.9, 0), caja(2.0, 0.22, 2.1, -0.5, 2.85, 0), caja(0.35, 1.25, 3.9, 3.7, 0.15, 0));
  T.amarillo.push(caja(1.5, 0.3, 0.25, 2.9, 0.75, 0.95), caja(1.5, 0.3, 0.25, 2.9, 0.75, -0.95));
  T.vidrio.push(caja(1.7, 1.15, 1.8, -0.5, 1.7, 0));
  [[-1.3, -0.85], [0.3, -0.85], [-1.3, 0.85], [0.3, 0.85]].forEach(([x, z]) => T.oscuro.push(caja(0.08, 1.2, 0.08, x, 1.65, z)));
  T.oscuro.push(cil(0.07, 1.1, -3.0, 2.5, 0.6, 6), caja(2.9, 0.12, 2.4, -2.2, 2.5, 0));
  [2.1, -2.3].forEach((x) => [-1.0, 1.0].forEach((z) => {
    T.acero.push(new THREE.CylinderGeometry(0.78, 0.78, 1.0, 16).rotateX(Math.PI / 2).translate(x, 0.82, z));
    for (let k = 0; k < 12; k++) for (const dz of [-0.32, 0.02, 0.34]) T.acero.push(new THREE.BoxGeometry(0.18, 0.22, 0.18).translate(0, 0.86, 0).rotateZ((k / 12) * Math.PI * 2 + dz * 2).translate(x, 0.82, z + dz));
  }));
  return T;
}
// volqueta: chasis, cabina blanca y platón levantado vuelco radianes alrededor del eje de atrás
function volqueta(vuelco = 0.55) {
  const T = { naranja: [], oscuro: [], vidrio: [], blanco: [], caucho: [] };
  T.oscuro.push(caja(7.4, 0.35, 1.0, -0.3, 0.75, 0), caja(0.5, 1.4, 0.25, -3.4, 0.8, 0));
  T.blanco.push(caja(1.9, 1.75, 2.4, 2.95, 0.95, 0), caja(0.4, 0.4, 2.42, 3.85, 0.95, 0));
  T.vidrio.push(caja(0.06, 0.8, 2.1, 3.92, 1.8, 0), caja(1.1, 0.62, 2.44, 2.8, 1.92, 0));
  [caja(5.0, 0.15, 2.4, 0, 0, 0), caja(5.0, 1.1, 0.1, 0, 0.15, 1.15), caja(5.0, 1.1, 0.1, 0, 0.15, -1.15), caja(0.12, 1.4, 2.4, 2.45, 0.15, 0)].forEach((g) => T.naranja.push(g.translate(2.5, 0, 0).rotateZ(vuelco).translate(-3.6, 1.05, 0)));
  [3.0, -1.6, -2.8].forEach((x) => [-1.05, 1.05].forEach((z) => T.caucho.push(rueda(x, z))));
  return T;
}
// camión recolector compactador: cabina blanca, caja verde con franja blanca y tolva trasera
function recolector() {
  const T = { verde: [], blanco: [], oscuro: [], vidrio: [], caucho: [] };
  T.oscuro.push(caja(8.0, 0.35, 1.0, 0, 0.75, 0));
  T.blanco.push(caja(1.9, 1.85, 2.45, 3.05, 0.9, 0), caja(5.25, 0.3, 2.55, -0.75, 2.0, 0), caja(1.5, 2.3, 2.45, -4.05, 0.75, 0));
  T.verde.push(caja(5.2, 2.55, 2.45, -0.75, 1.1, 0), caja(1.6, 0.4, 2.5, -4.0, 3.05, 0));
  T.vidrio.push(caja(0.06, 0.8, 2.15, 4.02, 1.85, 0), caja(1.1, 0.6, 2.47, 2.9, 1.95, 0));
  [3.1, -1.4, -2.6].forEach((x) => [-1.05, 1.05].forEach((z) => T.caucho.push(rueda(x, z))));
  return T;
}
// volteadora de compost a horcajadas: dos orugas, columnas, viga, cabina y tambor (ancho de la hilera + 1 m)
function volteadora(ancho = 4.6) {
  const T = { verdeMaq: [], oscuro: [], vidrio: [], acero: [] }, z = ancho / 2;
  [-z, z].forEach((s) => { T.oscuro.push(caja(3.0, 0.7, 0.6, 0, 0, s)); T.verdeMaq.push(caja(0.6, 2.4, 0.5, 0, 0.7, s)); });
  T.verdeMaq.push(caja(1.2, 0.6, ancho + 0.8, 0, 3.0, 0), caja(1.3, 1.3, 1.2, 0.2, 3.6, z - 0.4));
  T.vidrio.push(caja(1.32, 0.7, 1.0, 0.25, 4.0, z - 0.4));
  T.acero.push(new THREE.CylinderGeometry(0.55, 0.55, ancho - 0.4, 12).rotateX(Math.PI / 2).translate(0, 0.9, 0));
  return T;
}
// caseta: muros de pañete, cubierta de zinc a un agua con alero, puerta y ventana al frente (+x)
function caseta(w, d, h = 2.8) {
  return {
    muro: [caja(w, h, d)], zinc: [new THREE.BoxGeometry(w + 0.8, 0.08, d + 0.8).rotateX(0).rotateZ(0.08).translate(0, h + 0.15, 0)],
    madera: [caja(0.06, 2.0, 0.9, w / 2 + 0.01, 0, -d / 4)], vidrio: [caja(0.05, 0.9, Math.min(1.6, d * 0.4), w / 2 + 0.01, 1.1, d / 5)],
  };
}
/** Letrero en un tablero sobre dos postes, de frente a +x local (renglones: [texto, tamaño relativo]). */
export function letrero(renglones, { w = 5, h = 1.8, alto = 1.2, fondo = '#1f5a45', tinta = '#f4f1e8', acento = '#e8c15a' } = {}) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = Math.round((1024 * h) / w);
  const x = c.getContext('2d');
  x.fillStyle = fondo; x.fillRect(0, 0, c.width, c.height);
  x.strokeStyle = 'rgba(255,255,255,0.35)'; x.lineWidth = 8; x.strokeRect(14, 14, c.width - 28, c.height - 28);
  const total = renglones.reduce((a, [, k]) => a + k, 0), paso = (c.height - 60) / total;
  let y = 30;
  x.textAlign = 'center'; x.textBaseline = 'middle';
  renglones.forEach(([t, k], i) => {
    let px = Math.round(paso * k * 0.72);
    const fuente = () => { x.font = `${i ? 600 : 'bold'} ${px}px "Public Sans", Arial, sans-serif`; };
    fuente(); x.fillStyle = i ? tinta : acento;
    while (x.measureText(t).width > c.width - 80 && px > 10) { px = Math.round(px * 0.9); fuente(); }   // que quepa a lo ancho
    x.fillText(t, c.width / 2, y + (paso * k) / 2); y += paso * k;
  });
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  const g = new THREE.Group(), pm = mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.5 });
  g.add(new THREE.Mesh(unir([caja(0.12, alto + h, 0.12, 0, 0, -w / 2 + 0.3), caja(0.12, alto + h, 0.12, 0, 0, w / 2 - 0.3), caja(0.1, h + 0.1, w + 0.1, -0.06, alto - 0.05, 0)]), pm));
  const cara = new THREE.Mesh(new THREE.PlaneGeometry(w, h).rotateY(Math.PI / 2).translate(0.005, alto + h / 2, 0), new THREE.MeshStandardMaterial({ map: t, roughness: 0.55 }));
  g.add(cara);
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}

// { predio, celdas: polígono convexo de la fase 1, futuras: [polígonos], lixiviados: [polígonos], eca, compostaje,
//   porteria: [x, y] (o polígono), entrada: [[x, y], [x, y]] (de la vía a la portería), vias: [polilíneas internas],
//   franja: polilínea de la franja de árboles, monitoreo: [[x, y]] (pozos) }
export function rellenoNuevo({ predio, celdas, futuras = [], lixiviados = [], eca, compostaje, porteria, entrada, vias = [], franja: lineaArboles = null, monitoreo = [] }) {
  const raiz = new THREE.Group();
  const piso = capa(raiz, 'piso'), cerro = capa(raiz, 'celdas'), obras = capa(raiz, 'obras'), verde = capa(raiz, 'verde');
  // las losas del piso (predio, celdas futuras, vías y patios) se adelantan solo unas unidades de profundidad, sin el
  // término de la pendiente: de lejos y en ángulo bajo ese término las adelantaba metros y tapaban las lagunas, las pilas
  // de compostaje y la báscula, que van pocos centímetros por encima. Las unidades bastan para que no titilen entre ellas
  const po = (k) => ({ polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -k });
  const M = {
    predio: matT('cesped', { color: '#d5ddb4', ...po(2) }), futura: matT('tierra', { color: '#ece3cf', ...po(4) }),
    via: matT('tierra', { color: '#d9cbad', ...po(6) }), patio: matT('concreto', { modo: 'xz', color: '#e2ded6', ...po(5) }), cuneta: matT('concreto', { color: '#bdb9b0', ...po(8) }),
    pasto: matT('cesped', { color: '#c9d79f' }), berma: matT('tierra', { color: '#e0d6bd' }), membrana: matT('membrana', { color: '#2c3135', escala: 28, roughness: 0.38 }),
    tierra: matT('tierra', { color: '#b39a75', side: THREE.DoubleSide }), zanja: matT('tierra', { color: '#7e6a52' }),
    liner: matT('membrana', { color: '#1f2326', escala: 14, roughness: 0.32 }), lixiviado: matAgua('#55603f'),
    concreto: matT('concreto'), muro: matT('estuco', { color: '#efebe2' }), zinc: matT('zinc', { color: '#cdd3d6' }), madera: matT('madera'),
    malla: matT('malla', { color: '#b7bec2' }), poste: matT('concreto', { color: '#d7d3cb' }), compost: matT('tierra', { escala: 3, relieve: 0.03 }),
    acero: mat(new THREE.Color('#6b747c'), { roughness: 0.45, metalness: 0.6 }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.4 }),
    caucho: mat(new THREE.Color('#1c1d1f'), { roughness: 0.85 }), vidrio: mat(new THREE.Color('#33434e'), { roughness: 0.08, metalness: 0.7 }),
    amarillo: mat(new THREE.Color('#f0b51c'), { roughness: 0.5 }), naranja: mat(new THREE.Color('#e2702a'), { roughness: 0.5 }), blanco: mat(new THREE.Color('#f1f0ea'), { roughness: 0.45 }),
    verde: mat(new THREE.Color('#2f7a4c'), { roughness: 0.5 }), verdeMaq: mat(new THREE.Color('#3f8a3a'), { roughness: 0.5 }), rojo: mat(new THREE.Color('#c8322b'), { roughness: 0.5 }),
    azul: mat(new THREE.Color('#2f5f9e'), { roughness: 0.5 }), placa: mat(new THREE.Color('#4a5157'), { roughness: 0.55, metalness: 0.5 }),
    basura: new THREE.MeshStandardMaterial({ roughness: 0.62 }), paca: new THREE.MeshStandardMaterial({ roughness: 0.9 }),
  };
  const r = azar(41);
  const Ap = acopio(), Ac = acopio(), Ao = acopio();
  const personas = { cerro: [], obras: [] };
  const vest = () => ({ camisa: ['#f28c28', '#e8e04a', '#f2c230'][Math.floor(r() * 3)], pantalon: '#2b3a55' });

  // --- piso: predio en grama, celdas futuras desmontadas (afirmado claro) con estacas de replanteo, vías internas de
  // afirmado con cunetas y la entrada desde la vía a Puerto Berrío
  if (predio) Ap.put('predio', losa(predio, 0.08));
  futuras.forEach((f) => {
    Ap.put('futura', losa(f, 0.12));
    f.forEach(([x, y]) => { Ao.put('madera', caja(0.06, 0.9, 0.06, x, 0, -y)); Ao.put('naranja', caja(0.08, 0.14, 0.08, x, 0.9, -y)); });
  });
  const internas = vias.filter((v) => v?.length > 1), todas = [...internas, ...(entrada?.length > 1 ? [entrada] : [])];
  internas.forEach((v) => { Ap.put('via', cinta(v, 6, 0.14)); [3.5, -3.5].forEach((d) => Ap.put('cuneta', cinta(paralela(v, d), 0.55, 0.16))); });
  if (entrada?.length > 1) Ap.put('via', cinta(entrada, 7, 0.14));

  // --- celda de la fase 1: tres terrazas de 3 m con taludes de 3H:1V y bermas de 1,5 m. Las dos de abajo, cerradas, con
  // cobertura de pasto, cunetas en las bermas, canal perimetral al pie y bajantes escalonados en el medio de cada lado; la
  // de arriba, la cara activa, con geomembrana (paños de 7 m), zanja de anclaje y el frente de trabajo en la meseta
  let cima = null, rampa = null;
  if (celdas) {
    const ring = (d) => adentro(celdas, d);
    for (let k = 0; k < TERRAZAS; k++) {
      const a = ring(k * RETIRO), b = ring(k * RETIRO + TALUD), h0 = k * ALTO + BASE, h1 = (k + 1) * ALTO + BASE, arriba = k === TERRAZAS - 1;
      Ac.put(arriba ? 'membrana' : 'pasto', anillo(a, h0, b, h1));
      if (!arriba) {
        Ac.put('berma', anillo(b, h1, ring((k + 1) * RETIRO), h1));
        Ac.put('cuneta', cinta([...ring((k + 1) * RETIRO - 1.0), ...ring((k + 1) * RETIRO - 1.0).slice(0, 2)], 0.5, h1 + 0.04));
        if (k === TERRAZAS - 2) Ac.put('zanja', cinta([...ring((k + 1) * RETIRO - 0.3), ...ring((k + 1) * RETIRO - 0.3).slice(0, 2)], 0.4, h1 + 0.03));
        // bajante escalonado en el medio de cada lado: seis gradas de concreto que siguen el talud
        a.forEach((p, i) => {
          const j = (i + 1) % a.length, ma = [(p[0] + a[j][0]) / 2, (p[1] + a[j][1]) / 2], mb = [(b[i][0] + b[j][0]) / 2, (b[i][1] + b[j][1]) / 2], rot = Math.atan2(mb[1] - ma[1], mb[0] - ma[0]);
          for (let s = 0; s < 6; s++) { const t = (s + 0.5) / 6; Ac.put('concreto', ubicar(caja(1.5, 0.55, 1.3, 0, -0.35, 0), ma[0] + (mb[0] - ma[0]) * t, ma[1] + (mb[1] - ma[1]) * t, rot, h0 + ALTO * t)); }
        });
      }
    }
    Ac.put('cuneta', cinta([...ring(-1.0), ...ring(-1.0).slice(0, 2)], 0.8, BASE + 0.04));
    cima = ring((TERRAZAS - 1) * RETIRO + TALUD);
    Ac.put('membrana', losa(cima, CIMA));
    // rampa de afirmado: sale del extremo de la meseta más cercano a la vía interna y baja derecho hasta ella
    const f = marcoDe(cima), L = local(f.cx, f.cy, f.ang), via = internas[0];
    const extremos = [[L(f.w / 2, 0), f.ang], [L(-f.w / 2, 0), f.ang + Math.PI]];
    const [[e, dir]] = via ? extremos.sort((p, q) => distLinea(p[0], via) - distLinea(q[0], via)) : extremos;
    const ux = Math.cos(dir), uy = Math.sin(dir);
    let largo = 30;
    if (via) for (let s = 30; s < 80; s++) { largo = s; if (distLinea([e[0] + ux * s, e[1] + uy * s], via) < 3.2) break; }
    // (un tramo plano de 2 m sobre la meseta y luego la pendiente, siempre por encima del talud, que es más empinado)
    const p0 = [e[0] - ux * 2, e[1] - uy * 2], p1 = [e[0] + ux * largo, e[1] + uy * largo], nx = -uy * 3, ny = ux * 3, hc = CIMA + 0.04, hb = BASE + 0.08;
    const q = (p, s, h) => V(p[0] + nx * s, p[1] + ny * s, h);
    Ac.put('tierra', caras([[q(p0, -1, hc), q(p0, 1, hc), q(e, 1, hc), q(e, -1, hc)], [q(e, -1, hc), q(e, 1, hc), q(p1, 1, hb), q(p1, -1, hb)], [q(e, 1, hc), q(p1, 1, hb), q(p1, 1, 0), q(e, 1, 0)], [q(e, -1, hc), q(p1, -1, hb), q(p1, -1, 0), q(e, -1, 0)]]));
    rampa = { e, dir };
    // frente de trabajo en el otro extremo de la meseta: cobertura diaria de tierra, residuos recién descargados, el
    // compactador, la volqueta que descarga y tres operarios con chaleco
    const sg = dir === f.ang ? -1 : 1, Lf = (u, v) => L(sg * u, v), largoM = f.w;
    const frente = [Lf(largoM * 0.5 - 0.6, -f.d / 2 + 0.6), Lf(largoM * 0.08, -f.d / 2 + 0.6), Lf(largoM * 0.08, f.d / 2 - 0.6), Lf(largoM * 0.5 - 0.6, f.d / 2 - 0.6)];
    Ac.put('tierra', losa(frente, CIMA + 0.12));
    const n = 150, bolsas = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1, 0), M.basura, n), m4 = new THREE.Matrix4(), qq = new THREE.Quaternion(), e3 = new THREE.Euler(), col = new THREE.Color();
    const tonos = ['#1d1f22', '#2a2d31', '#e8e6df', '#3a6fb0', '#2f8a4c', '#c9b28a', '#8a2f2f', '#d9d4c7', '#1d1f22', '#5a5f63'];
    for (let i = 0; i < n; i++) {
      const u = largoM * (0.18 + r() * 0.3), v = (r() - 0.5) * (f.d - 2), [x, y] = Lf(u, v), s = 0.25 + r() * 0.4;
      qq.setFromEuler(e3.set(r() * 3, r() * 3, r() * 3)); m4.compose(V(x, y, CIMA + 0.12 + s * 0.3), qq, new THREE.Vector3(s, s * 0.6, s)); bolsas.setMatrixAt(i, m4); bolsas.setColorAt(i, col.set(tonos[Math.floor(r() * tonos.length)]));
    }
    bolsas.castShadow = true; bolsas.receiveShadow = true; bolsas.computeBoundingSphere(); cerro.add(bolsas);
    const ang = f.ang + (sg < 0 ? Math.PI : 0);   // rumbo hacia el extremo del frente
    Ac.poner(compactador(), ...Lf(largoM * 0.3, -f.d * 0.12), ang + 0.25, CIMA + 0.12);
    Ac.poner(volqueta(0.6), ...Lf(largoM * 0.02, f.d * 0.16), ang + Math.PI, CIMA + 0.05);
    [[0.2, 0.32], [0.12, -0.3], [-0.05, 0.36]].forEach(([u, v]) => personas.cerro.push(Object.assign([...Lf(largoM * u, f.d * v), ang + r() * 2, vest()], { h: CIMA + 0.12 })));
    // chimeneas de biogás (tubo con anillo de grava) a media altura de los taludes cerrados, cada 22 m, y dos en la meseta
    const chim = [];
    for (let k = 0; k < TERRAZAS - 1; k++) { const anil = ring(k * RETIRO + TALUD / 2); aLoLargo([...anil, anil[0]], 22, 0, 6).forEach(([x, y]) => chim.push([x, y, k * ALTO + ALTO / 2 + BASE])); }
    [0.36, 0.16].forEach((u) => { const [x, y] = Lf(-largoM * u, -f.d * 0.3); chim.push([x, y, CIMA]); });
    chim.forEach(([x, y, h]) => { Ac.put('concreto', cil(0.55, 0.3, x, h, -y, 10)); Ac.put('blanco', cil(0.11, 2.1, x, h, -y, 8), new THREE.TorusGeometry(0.22, 0.09, 6, 10, Math.PI).translate(x - 0.22, h + 2.1, -y)); });
  }

  // --- lagunas de lixiviados: dique con talud exterior empradizado, corona de afirmado, talud interior con geomembrana
  // negra y lámina de lixiviado; cerco de malla con portón hacia el ramal y caseta de bombeo
  lixiviados.forEach((l) => {
    const corona = adentro(l, 2.4), interior = adentro(l, 3.4), fondo = adentro(l, 6);
    Ao.put('pasto', anillo(l, 0.08, corona, 1.6));
    Ao.put('berma', anillo(corona, 1.6, interior, 1.6));
    Ao.put('liner', anillo(interior, 1.6, fondo, 0.3));
    Ao.put('lixiviado', losa(adentro(l, 4.3), 1.0));
  });
  if (lixiviados.length) {
    const xs = lixiviados.flat().map((p) => p[0]), ys = lixiviados.flat().map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs) - 3, Math.max(...xs) + 16, Math.min(...ys) - 3, Math.max(...ys) + 3];
    const ramal = internas.find((v) => v.length === 2) || internas[0], puerta = ramal ? [x0, centro(lixiviados.flat())[1]] : null;
    cerco(Ao, [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], { alto: 2, puertas: puerta ? [puerta] : [], hueco: 3 });
    const [cx, cy] = [x1 - 7, (y0 + y1) / 2];
    Ao.poner(caseta(4, 3.2, 2.6), cx, cy, Math.PI);
    Ao.put('acero', ...lixiviados.map((l) => { const [lx, ly] = centro(l), d = Math.hypot(cx - lx, cy - ly); return new THREE.CylinderGeometry(0.12, 0.12, d, 8).rotateZ(Math.PI / 2).rotateY(Math.atan2(cy - ly, cx - lx)).translate((cx + lx) / 2, 1.75, -(cy + ly) / 2); }));
  }

  // --- ECA: nave abierta (columnas de acero, muro bajo y cubierta de zinc a dos aguas) sobre un patio de concreto, con
  // tolva y banda de clasificación, operarios a lado y lado, compactadora de pacas, pacas de reciclables arrumadas y el
  // recolector que descarga en la entrada
  const marcos = {};
  if (eca) {
    const f = marcos.eca = marcoDe(eca), Le = Math.min(48, f.w * 0.8), We = Math.min(30, f.d * 0.75), H = 7, pend = 0.27, L = local(f.cx, f.cy, f.ang);
    Ap.put('patio', losa(eca, 0.12));
    const T = { acero: [], muro: [], zinc: [], caucho: [], azul: [], oscuro: [] }, nC = 6;
    for (let i = 0; i <= nC; i++) {
      const u = -Le / 2 + (i * Le) / nC;
      [-1, 1].forEach((s) => T.acero.push(caja(0.35, H, 0.35, u, 0, s * We / 2)));
      T.acero.push(caja(0.18, 0.3, We, u, H - 0.3, 0));
      [-1, 1].forEach((s) => T.acero.push(new THREE.BoxGeometry(0.16, 0.25, We / 2 / Math.cos(pend)).rotateX(s * pend).translate(u, H + (We / 4) * Math.tan(pend) - 0.15, s * We / 4)));
    }
    [-1, 1].forEach((s) => {
      T.muro.push(caja(Le, 1.6, 0.22, 0, 0, s * We / 2));
      T.zinc.push(new THREE.BoxGeometry(Le + 1.6, 0.1, (We / 2 + 1) / Math.cos(pend)).rotateX(s * pend).translate(0, H + ((We / 2 - 1) / 2) * Math.tan(pend), s * (We / 2 + 1) / 2));
    });
    T.muro.push(caja(0.22, 1.6, We * 0.6, Le / 2, 0, -We * 0.2));
    // banda: estructura, tolva, cinta de caucho y compactadora de pacas al final
    T.acero.push(caja(22, 0.3, 1.4, -2, 0.75, -5), caja(2.6, 1.6, 2.6, -14, 1.0, -5));
    for (let u = -12; u <= 8; u += 2.5) [-0.6, 0.6].forEach((z) => T.acero.push(caja(0.1, 0.75, 0.1, u, 0, -5 + z)));
    T.caucho.push(caja(22, 0.06, 1.1, -2, 1.05, -5));
    T.azul.push(caja(2.4, 2.8, 2.0, 11, 0, -5), caja(0.6, 1.2, 1.6, 12.4, 2.8, -5));
    T.oscuro.push(caja(0.3, 0.3, 0.3, 11, 2.8, -4.2));
    Ao.poner(T, f.cx, f.cy, f.ang);
    // pacas (1,1 × 1,1 × 1 m) de cartón, PET, plástico, latas y papel en filas de dos o tres de alto
    const P = [], cols = ['#b08a5a', '#5aa0d8', '#e8e8e2', '#a9b0b6', '#d8cfa8', '#7fb6d9', '#c49a62'].map((c) => new THREE.Color(c));
    for (let u = -16; u <= 6; u += 1.25) for (let v = -10; v <= -3; v += 1.3) { if (r() < 0.25) continue; const pisos = 1 + Math.floor(r() * 3); for (let k = 0; k < pisos; k++) P.push([u, v, k, cols[Math.floor(r() * cols.length)]]); }
    const pacas = new THREE.InstancedMesh(new THREE.BoxGeometry(1.1, 1.0, 1.1), M.paca, P.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), tinte = new THREE.Color();
    P.forEach(([u, v, k, c], i) => { const [x, y] = L(u, v); q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), f.ang + (r() - 0.5) * 0.12); m4.compose(V(x, y, 0.12 + 0.5 + k * 1.0), q, new THREE.Vector3(1, 1, 1)); pacas.setMatrixAt(i, m4); pacas.setColorAt(i, tinte.copy(c).multiplyScalar(0.9 + r() * 0.15)); });
    pacas.castShadow = true; pacas.receiveShadow = true; pacas.computeBoundingSphere(); obras.add(pacas);
    // (la banda va a 5 m a la izquierda del eje: z = −5 en la plantilla; las pacas, al otro lado)
    for (let u = -10; u <= 4; u += 3.5) [6.1, 3.9].forEach((v) => personas.obras.push(Object.assign([...L(u + r(), v), f.ang + (v > 5 ? -Math.PI / 2 : Math.PI / 2), vest()], { h: 0.12 })));
    Ao.poner(recolector(), ...L(-Le / 2 - 6, 5), f.ang + Math.PI, 0.12);
  }

  // --- compostaje: patio de concreto, hileras de 3,6 m de base y 1,7 m de alto (las frescas más claras, las maduras más
  // oscuras), la volteadora a horcajadas sobre una de ellas y dos operarios
  if (compostaje) {
    const f = marcos.compostaje = marcoDe(compostaje), n = Math.max(3, Math.min(8, Math.floor((f.d - 6) / 5.5))), L = local(f.cx, f.cy, f.ang);
    const largo = Math.max(10, f.w - 10);
    Ap.put('patio', losa(compostaje, 0.12));
    const geo = new THREE.CapsuleGeometry(1.8, largo - 3.6, 4, 12).rotateZ(Math.PI / 2).scale(1, 1.7 / 1.8, 1);
    const hileras = new THREE.InstancedMesh(geo, M.compost, n), m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), f.ang);
    const tonos = ['#8a7448', '#7a6440', '#6f5233', '#5e4630', '#4f3b28', '#46352a', '#3f2f22', '#3a2b20'].map((c) => new THREE.Color(c));
    for (let k = 0; k < n; k++) { const v = -((n - 1) * 5.5) / 2 + k * 5.5, [x, y] = L(0, v); m4.compose(V(x, y, 0.12), q, new THREE.Vector3(1, 1, 1)); hileras.setMatrixAt(k, m4); hileras.setColorAt(k, tonos[Math.round((k / Math.max(1, n - 1)) * (tonos.length - 1))]); }
    hileras.castShadow = true; hileras.receiveShadow = true; hileras.computeBoundingSphere(); obras.add(hileras);
    const kv = -((n - 1) * 5.5) / 2 + Math.min(1, n - 1) * 5.5;
    Ao.poner(volteadora(), ...L(largo * 0.18, kv), f.ang, 0.12);
    personas.obras.push(Object.assign([...L(-largo * 0.3, kv + 2.75), f.ang + 1.2, vest()], { h: 0.12 }), Object.assign([...L(largo * 0.36, kv - 2.75), f.ang - 2, vest()], { h: 0.12 }));
  }

  // --- portería: báscula de camiones (foso de concreto, plataforma de acero y rampas), caseta con cubierta de zinc,
  // talanquera, tablero de pesaje, el recolector sobre la báscula, un vigilante y el letrero a la entrada
  if (porteria) {
    const [px, py] = Array.isArray(porteria[0]) ? centro(porteria) : porteria, ang = entrada?.length > 1 ? Math.atan2(entrada[1][1] - entrada[0][1], entrada[1][0] - entrada[0][0]) : 0;
    const g = new THREE.Group(); g.position.copy(V(px, py)); g.rotation.y = ang;
    const A = acopio(), cuna = (s) => { const sh = new THREE.Shape([new THREE.Vector2(s * 9.5, 0), new THREE.Vector2(s * 13.5, 0), new THREE.Vector2(s * 9.5, 0.38)]); return new THREE.ExtrudeGeometry(sh, { depth: 3.6, bevelEnabled: false }).translate(0, 0, -1.8); };
    A.put('concreto', caja(19.2, 0.34, 4.2), cuna(1), cuna(-1));
    A.put('placa', caja(18, 0.05, 3.6, 0, 0.34, 0));
    A.poner(caseta(5, 3.6, 2.8), 0, -7.5, Math.PI / 2);
    A.put('rojo', caja(0.3, 1.1, 0.3, -11, 0, 4.2));
    for (let k = 0; k < 7; k++) A.put(k % 2 ? 'blanco' : 'rojo', caja(0.12, 0.12, 1.0, -11, 1.0, 3.6 - k));
    A.put('oscuro', caja(0.12, 2.0, 0.12, 4, 0, 3.0), caja(0.15, 0.9, 1.6, 4, 2.0, 3.0));
    A.poner(recolector(), 0, 0, 0, 0.39);
    A.volcar(g, M);
    const L = local(px, py, ang);
    personas.obras.push([...L(-2.5, -4.3), ang - Math.PI / 2, { camisa: '#2b4a7a', pantalon: '#1f2329' }]);
    // el letrero, de frente a quien llega por la entrada (al lado derecho, antes de la talanquera)
    const cartel = letrero([['RELLENO SANITARIO', 1], ['Kilómetro Cinco · Yondó', 0.8], ['ECA · compostaje · celdas', 0.6]], { w: 5.5, h: 2 });
    const [lx, ly] = L(-25, 7); cartel.position.copy(V(lx, ly)); cartel.rotation.y = ang + Math.PI; obras.add(cartel);
    obras.add(g);
  }

  // --- cerco perimetral con el portón donde la entrada cruza el lindero
  if (predio) {
    let puerta = null;
    if (entrada?.length > 1) for (let i = 0; i < predio.length && !puerta; i++) puerta = cruceSeg(entrada[0], entrada[1], predio[i], predio[(i + 1) % predio.length]);
    const libres = cerco(Ao, [...predio, predio[0]], { puertas: puerta ? [puerta] : [], hueco: 6 });
    // portón: dos postes gruesos en el vano y dos hojas abiertas hacia adentro
    if (puerta && libres.length) {
      const ext = [libres[0], libres[libres.length - 1]];
      ext.forEach((p) => Ao.put('concreto', caja(0.35, 2.6, 0.35, p[0], 0, -p[1])));
    }
  }
  // --- pozos de monitoreo: losa de concreto, tubo de revestimiento, tapa con candado y placa
  monitoreo.forEach(([x, y]) => {
    Ao.put('concreto', caja(1.2, 0.15, 1.2, x, 0.05, -y));
    Ao.put('blanco', cil(0.09, 0.85, x, 0.2, -y, 10));
    Ao.put('amarillo', caja(0.34, 0.55, 0.34, x, 0.2, -y));
    Ao.put('oscuro', caja(0.05, 1.3, 0.05, x + 0.9, 0, -y));
    Ao.put('blanco', caja(0.04, 0.32, 0.5, x + 0.92, 1.05, -y));
  });
  // --- alumbrado a lo largo de la vía interna principal
  if (internas[0]) obras.add(postes(aLoLargo(internas[0], 35, 4.2, 10).map(([x, y]) => [x, y]), 7));

  Ap.volcar(piso, M, { sombra: false });
  Ac.volcar(cerro, M);
  Ao.volcar(obras, M);
  if (personas.cerro.length) cerro.add(gente(personas.cerro, { semilla: 5 }));
  if (personas.obras.length) obras.add(gente(personas.obras, { semilla: 6 }));

  // --- franja de aislamiento: árboles de especies mezcladas cada 8,5 m sobre la línea de geo.json (si no, a 6 m del
  // lindero hacia adentro), con palmas intercaladas; ninguno sobre las vías ni en la portería
  const libre = ([x, y]) => todas.every((v) => distLinea([x, y], v) > 7) && (!porteria || Math.hypot(x - (porteria[0]?.[0] ?? porteria[0]), y - (porteria[0]?.[1] ?? porteria[1])) > 14);
  const sitiosArboles = (lineaArboles?.length > 1 ? aLoLargo(lineaArboles, 8.5).map(([x, y]) => [x, y]) : (predio ? franja(predio, 6, 9) : [])).filter(libre);
  const deArbol = sitiosArboles.filter((_, i) => i % 7 !== 3), dePalma = sitiosArboles.filter((_, i) => i % 7 === 3);
  if (deArbol.length) verde.add(arboles(deArbol, { alto: 11, semilla: 77, especie: 'mixto' }));
  if (dePalma.length) verde.add(palmas(dePalma, { alto: 10, semilla: 78 }));
  if (porteria && entrada?.length > 1) {
    const [px, py] = Array.isArray(porteria[0]) ? centro(porteria) : porteria, ang = Math.atan2(entrada[1][1] - entrada[0][1], entrada[1][0] - entrada[0][0]), L = local(px, py, ang);
    verde.add(jardin([L(-6, -11), L(5, -11), L(5, -13.5), L(-6, -13.5)], { densidad: 0.9, semilla: 9 }));
    verde.add(palmas([L(-7, -12.5), L(6.5, -12.5), L(-25, 10.5)], { alto: 8, semilla: 79 }));
  }

  raiz.userData.partes = { piso, celdas: cerro, obras, verde };
  raiz.userData.contorno = predio || celdas;
  raiz.userData.centro = centro(predio || celdas);
  raiz.userData.celda = celdas ? centro(celdas) : null;
  raiz.userData.eca = marcos.eca ? [marcos.eca.cx, marcos.eca.cy] : null;
  raiz.userData.compostaje = marcos.compostaje ? [marcos.compostaje.cx, marcos.compostaje.cy] : null;
  raiz.userData.lixiviados = lixiviados.length ? centro(lixiviados[0]) : null;
  raiz.userData.rampa = rampa;
  return raiz;
}
// punto donde se cortan los segmentos ab y cd (null si no se cortan)
function cruceSeg(a, b, c, d) {
  const p = cruce([a, b], [c, d]); if (!p) return null;
  const en = (s, t, q) => Math.min(s[0], t[0]) - 0.01 <= q[0] && q[0] <= Math.max(s[0], t[0]) + 0.01 && Math.min(s[1], t[1]) - 0.01 <= q[1] && q[1] <= Math.max(s[1], t[1]) + 0.01;
  return en(a, b, p) && en(c, d, p) ? p : null;
}
