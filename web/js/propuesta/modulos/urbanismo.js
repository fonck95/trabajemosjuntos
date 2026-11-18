// Urbanismo: la ciudadela deportiva ecológica que une el caño colector Shell (parque lineal renaturalizado), la Cancha de
// Sóftbol Casabe renovada, la alameda por las calles que ya existen, el coliseo Benito Arias, el Parque Educativo, el
// parque principal, la cancha y canchas cubiertas junto al CIC; y, junto al puente sobre el Magdalena, el Mirador Puerta
// del Magdalena con la protección de la orilla. Las posiciones salen de data/propuesta/geo.json (urbanismo); si falta
// algo, se usan las del levantamiento.
//
// Acabados como en la cancha de sóftbol (piezas/softbol.js): materiales con textura en coordenadas del mundo, gente,
// vehículos, vegetación tropical, luminarias que se encienden al atardecer y mobiliario, todo instanciado o unido por
// material para que cada pieza cueste pocas llamadas de dibujo. El estadio de hoy (portadilla) tiene su propio modelo:
// grama gastada, cuadro de tierra, gradería vieja con techo de zinc oxidado y el muro de bloque del cerramiento.
import { THREE, mat } from '../../core.js';
import { CALLES } from '../../data.js';
import { V, cinta, losa, rect, arboles, palmas, matas, postes, bancas, bolardos, canecas, gente, carros, graderia, charcos, aLoLargo, puntoEn, crecer, brotar, revelar, dentro, unir, azar, luzComun, sembrar } from '../geo3d.js';
import { matT, tex } from '../texturas.js';
import { canchaSoftbol } from '../piezas/softbol.js';
import { miradorMagdalena } from '../piezas/mirador.js';
import { parqueLineal } from '../piezas/cano.js';
import { sitio, sitios, trazado, trazados, caja } from './comun.js';

// levantamiento (OpenStreetMap, huellas e imagen satelital de referencia): lo reemplaza geo.json
const BASE = {
  softbol: { home: [-47.7, 88.8], rumbo: 346.5 },
  alameda: [[-42.5, 55.2], [-30.7, 58.7], [18.2, 75], [63.6, 88.3], [71.7, 90.2], [86.6, 29.1], [101.1, -37.4], [151, -26.7], [182.4, -20], [168.7, 48.3], [209, 57.6], [209, 96.4]],
  mirador: { origen: [1536.4, 7915.9], angulo: 138.7 },
  ciudadela: [[-215, -45], [-120, -70], [60, -80], [285, -35], [300, 40], [225, 140], [40, 205], [-130, 190], [-215, 150]],
  explanada: [[-318, 62], [-243, 64], [-240, 116], [-318, 118]],
  hitos: { coliseo: [141, 0], parque_edu: [151, -41], parque_principal: [209, 96], cancha: [242, 3], cic: [-282, 140] },
};

// eje del caño colector Shell (OpenStreetMap) si geo.json no trae el de la fase 1
function ejeCano(y0 = -100, y1 = 410) {
  const tramos = CALLES.canos.filter((c) => c.nombre === 'Caño Colector Shell').map((c) => c.p);
  const pts = tramos.flat().filter(([, y]) => y >= y0 && y <= y1).sort((a, b) => a[1] - b[1]);
  return pts.filter((p, i) => !i || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 1);
}
// distancia de un punto a un polígono (0 si está dentro)
function distPoligono(p, poly) {
  if (dentro(p, poly)) return 0;
  let d = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [a, b] = [poly[j], poly[i]], dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    d = Math.min(d, Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy));
  }
  return d;
}
// distancia desde p, en la dirección d, hasta el borde del polígono (null si el rayo no lo corta)
function hastaBorde(p, d, poly) {
  let t = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [ax, ay] = poly[j], ex = poly[i][0] - ax, ey = poly[i][1] - ay, den = d[0] * ey - d[1] * ex;
    if (Math.abs(den) < 1e-9) continue;
    const s = ((ax - p[0]) * ey - (ay - p[1]) * ex) / den, u = ((ax - p[0]) * d[1] - (ay - p[1]) * d[0]) / den;
    if (s > 0 && u >= 0 && u <= 1) t = Math.min(t, s);
  }
  return Number.isFinite(t) ? t : null;
}

// ---------------------------------------------------------------- utilidades de geometría de esta área
const EJE_Y = new THREE.Vector3(0, 1, 0);
// tubo recto entre dos puntos [x, y, z] de three (cerchas, arcos de portería, bicicletas, barandas)
function barra(a, b, r = 0.04, seg = 5) {
  const va = new THREE.Vector3(...a), d = new THREE.Vector3(...b).sub(va), L = d.length();
  const g = new THREE.CylinderGeometry(r, r, L, seg, 1).translate(0, L / 2, 0);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(EJE_Y, d.normalize())); g.translate(va.x, va.y, va.z);
  return g;
}
// cuadrilátero (o triángulo, con d = null) entre puntos de three: paños de red y lonas
function pano(a, b, c, d = null) {
  const g = new THREE.BufferGeometry(), p = d ? [...a, ...b, ...c, ...a, ...c, ...d] : [...a, ...b, ...c];
  g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.computeVertexNormals();
  return g;
}
// una malla instanciada de `geo` en [x, y, rot, h] del marco del padre (rot: rumbo de su eje x, antihorario desde el oriente)
function instanciar(geo, m, lista, { colores, sombra = true } = {}) {
  const im = new THREE.InstancedMesh(geo, m, Math.max(1, lista.length)), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), uno = new THREE.Vector3(1, 1, 1);
  lista.forEach(([x, y, rot = 0, h = 0], i) => { q.setFromAxisAngle(EJE_Y, rot); m4.compose(V(x, y, h), q, uno); im.setMatrixAt(i, m4); if (colores) im.setColorAt(i, colores[i % colores.length]); });
  im.count = lista.length; im.castShadow = sombra; im.receiveShadow = true; im.computeBoundingSphere();
  return im;
}
// malla eslabonada sobre una polilínea [[x, y], …] del marco del padre: paños, postes cada `cada` m y pasamanos arriba.
// Devuelve las geometrías para unirlas por material con las de las otras mallas de la pieza
function malla(pts, alto, { cada = 3, base = 0, r = 0.04 } = {}) {
  const panos = [], postes = [], rieles = [];
  for (let i = 1; i < pts.length; i++) {
    const [a, b] = [pts[i - 1], pts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), ang = Math.atan2(b[1] - a[1], b[0] - a[0]), cx = (a[0] + b[0]) / 2, cz = -(a[1] + b[1]) / 2;
    panos.push(new THREE.PlaneGeometry(L, alto).rotateY(ang).translate(cx, base + alto / 2, cz));
    rieles.push(new THREE.CylinderGeometry(r * 0.8, r * 0.8, L, 6).rotateZ(Math.PI / 2).rotateY(ang).translate(cx, base + alto, cz));
    for (let s = 0; s < L - 0.01; s += cada) postes.push(new THREE.CylinderGeometry(r, r * 1.1, alto + base, 6).translate(a[0] + ((b[0] - a[0]) * s) / L, (alto + base) / 2, -(a[1] + ((b[1] - a[1]) * s) / L)));
  }
  const u = pts[pts.length - 1]; postes.push(new THREE.CylinderGeometry(r, r * 1.1, alto + base, 6).translate(u[0], (alto + base) / 2, -u[1]));
  return { panos, postes, rieles };
}
// mancha irregular (calvas de la grama, tierra pisada): polígono estrellado alrededor de (x, y)
const mancha = (r, x, y, rr, n = 12, k = 0.45) => Array.from({ length: n }, (_, i) => { const a = (i / n) * Math.PI * 2, q = rr * (1 - k / 2 + k * r()); return [x + q * Math.cos(a), y + q * Math.sin(a)]; });
const circulo = (x, y, rr, a0 = 0, a1 = Math.PI * 2, n = 32) => Array.from({ length: n + 1 }, (_, i) => { const a = a0 + ((a1 - a0) * i) / n; return [x + rr * Math.cos(a), y + rr * Math.sin(a)]; });

// bicicleta (1,7 m, a lo largo de x) y moto parqueada, en una geometría cada una
let geoBici = null, geoMoto = null;
function bici() {
  if (geoBici) return geoBici;
  const rueda = (x) => new THREE.TorusGeometry(0.34, 0.028, 5, 18).translate(x, 0.36, 0);
  const t = (a, b, r = 0.022) => barra(a, b, r, 4), cj = [0.36, 0.86, 0], sill = [-0.14, 0.9, 0], ped = [0, 0.33, 0];
  geoBici = unir([rueda(-0.52), rueda(0.52), t([-0.52, 0.36, 0], ped), t(ped, sill), t([-0.52, 0.36, 0], sill), t(sill, cj), t(ped, cj), t([0.52, 0.36, 0], cj), t(cj, [0.42, 1.0, 0]),
    new THREE.BoxGeometry(0.05, 0.03, 0.52).translate(0.42, 1.0, 0), new THREE.BoxGeometry(0.26, 0.05, 0.11).translate(-0.14, 0.93, 0)]);
  return geoBici;
}
function moto() {
  if (geoMoto) return geoMoto;
  const rueda = (x) => new THREE.TorusGeometry(0.27, 0.085, 6, 16).translate(x, 0.33, 0);
  geoMoto = {
    ruedas: unir([rueda(-0.62), rueda(0.62), barra([0.62, 0.33, 0], [0.42, 1.0, 0], 0.03, 5), new THREE.BoxGeometry(0.06, 0.04, 0.68).translate(0.42, 1.02, 0)]),
    cuerpo: unir([new THREE.BoxGeometry(0.7, 0.3, 0.3).translate(0.02, 0.62, 0), new THREE.BoxGeometry(0.42, 0.22, 0.34).translate(0.18, 0.86, 0), new THREE.BoxGeometry(0.62, 0.1, 0.28).translate(-0.3, 0.86, 0), new THREE.BoxGeometry(0.5, 0.06, 0.2).translate(-0.62, 0.62, 0)]),
  };
  return geoMoto;
}
// señal vertical de calle compartida (azul, peatón y bicicleta, como la de la norma), en un lienzo pequeño
let texSenal = null;
function texturaSenal() {
  if (texSenal) return texSenal;
  const c = document.createElement('canvas'); c.width = 128; c.height = 160;
  const x = c.getContext('2d');
  x.fillStyle = '#f4f4f0'; x.fillRect(0, 0, 128, 160); x.fillStyle = '#1f5fa8'; x.fillRect(6, 6, 116, 148);
  x.strokeStyle = x.fillStyle = '#f4f4f0'; x.lineCap = 'round'; x.lineJoin = 'round';
  x.beginPath(); x.arc(36, 28, 7, 0, 7); x.fill();
  x.lineWidth = 6; x.beginPath(); x.moveTo(36, 38); x.lineTo(34, 62); x.lineTo(26, 84); x.moveTo(34, 62); x.lineTo(44, 84); x.moveTo(24, 52); x.lineTo(36, 43); x.lineTo(48, 53); x.stroke();
  x.lineWidth = 4; [76, 106].forEach((cx) => { x.beginPath(); x.arc(cx, 74, 11, 0, 7); x.stroke(); });
  x.beginPath(); x.moveTo(76, 74); x.lineTo(88, 58); x.lineTo(106, 74); x.moveTo(84, 54); x.lineTo(94, 54); x.moveTo(76, 74); x.lineTo(92, 74); x.lineTo(100, 56); x.stroke();
  x.beginPath(); x.arc(92, 42, 6, 0, 7); x.fill();
  x.font = 'bold 19px "Public Sans", Arial, sans-serif'; x.textAlign = 'center'; x.fillText('CALLE', 64, 118); x.fillText('COMPARTIDA', 64, 140);
  texSenal = new THREE.CanvasTexture(c); texSenal.colorSpace = THREE.SRGBColorSpace; texSenal.anisotropy = 4;
  return texSenal;
}
// grafiti del muro del skatepark
function texturaGrafiti() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 128;
  const x = c.getContext('2d'), r = azar(91);
  x.fillStyle = '#c4bfb6'; x.fillRect(0, 0, 512, 128);
  ['#e8562f', '#2fa75a', '#f2c230', '#3b8fd9', '#c13b8a', '#2fb7b0'].forEach((col, i) => { x.fillStyle = col; x.globalAlpha = 0.85; x.beginPath(); x.ellipse(50 + i * 84 + r() * 16, 64 + (r() - 0.5) * 30, 46 + r() * 16, 30 + r() * 14, r() * 3, 0, 7); x.fill(); });
  x.globalAlpha = 1; x.font = 'bold 76px Anton, Impact, sans-serif'; x.textAlign = 'center'; x.lineWidth = 9; x.strokeStyle = '#1d2023';
  x.strokeText('CASABE SK8', 256, 94); x.fillStyle = '#f7f3e8'; x.fillText('CASABE SK8', 256, 94);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

// ---------------------------------------------------------------- el estadio de hoy (portadilla)
// Como está: grama gastada con calvas y caminos de tierra, cuadro de tierra irregular, cal borrada, backstop viejo de malla
// sobre tubos oxidados, gradería de concreto con techo de zinc oxidado por el lado de primera, bancas por el de tercera,
// cuatro postes de luz viejos, el muro de bloque del cerramiento con su portón y unos muchachos jugando. En el marco de la
// cancha nueva (home en el origen, u hacia primera, v hacia el jardín central): el diamante queda donde se renueva
function estadioHoy({ home, rumbo }, cerr) {
  const raiz = new THREE.Group(), r = azar(83);
  const rad = THREE.MathUtils.degToRad(rumbo), du = [Math.cos(rad), -Math.sin(rad)], dv = [Math.sin(rad), Math.cos(rad)];
  const loc = new THREE.Group(); loc.position.set(home[0], 0, -home[1]); loc.rotation.y = -rad; raiz.add(loc);
  const aLocal = ([x, y]) => { const dx = x - home[0], dy = y - home[1]; return [dx * du[0] + dy * du[1], dx * dv[0] + dy * dv[1]]; };
  const C = {
    // grama reseca, entre verde oliva y paja (sobre la textura de tierra: la del césped o el potrero, teñida, se veía igual
    // al pasto de los solares vecinos), y tierra polvorienta (no la arcilla roja de la cancha nueva)
    grama: matT('tierra', { color: '#a9bd78', escala: 9, macro: 0.3 }), calva: matT('tierra', { color: '#e2cfae', polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }),
    tierra: matT('tierra', { color: '#d9ab84', polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }), loma: matT('tierra', { color: '#c99a74' }),
    cal: mat(new THREE.Color('#e4e0d2'), { roughness: 0.95, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }),
    malla: matT('malla', { color: '#6e655b' }), oxido: mat(new THREE.Color('#7b5b45'), { roughness: 0.8, metalness: 0.35 }), madera: matT('madera', { color: '#9c8466' }),
    concreto: matT('concreto', { color: '#b3ab9e' }), zinc: matT('zinc', { color: '#a09485', side: THREE.DoubleSide }), zincOx: matT('zinc', { color: '#8a6a52', side: THREE.DoubleSide }),
    poste: matT('concreto', { color: '#a7a195' }), muro: matT('estuco', { color: '#d9d2c4' }), ladrillo: matT('ladrillo'), remate: matT('concreto', { color: '#c9c3b8' }),
    porton: mat(new THREE.Color('#4a5b50'), { roughness: 0.6, metalness: 0.45 }),
  };
  const add = (padre, geo, m, sombra = false) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; o.castShadow = sombra; padre.add(o); return o; };
  const enLinea = (lado, s, o) => [lado * (s + o) * Math.SQRT1_2, (s - o) * Math.SQRT1_2];

  // --- piso: la grama gastada en todo el cerramiento (mundo) y el muro con el portón hacia la tercera base, en el lado
  // del cerramiento que da a la alameda (el más cercano al home)
  add(raiz, losa(cerr, 0.05), C.grama);
  let iF = 0, dF = Infinity;
  cerr.forEach((p, i) => { const q = cerr[(i + 1) % cerr.length], d = Math.hypot((p[0] + q[0]) / 2 - home[0], (p[1] + q[1]) / 2 - home[1]); if (d < dF) { dF = d; iF = i; } });
  const W = { muro: [], ladrillo: [], remate: [], porton: [] };
  let puerta = null;
  cerr.forEach((p, i) => {
    const q = cerr[(i + 1) % cerr.length], L = Math.hypot(q[0] - p[0], q[1] - p[1]), ang = Math.atan2(q[1] - p[1], q[0] - p[0]), e = [(q[0] - p[0]) / L, (q[1] - p[1]) / L];
    const en = (s) => [p[0] + e[0] * s, p[1] + e[1] * s];
    let tramos = [[0, L]];
    if (i === iF) {
      const u0 = aLocal(p)[0], k = e[0] * du[0] + e[1] * du[1], tG = THREE.MathUtils.clamp(Math.abs(k) > 0.1 ? (-26 - u0) / k : L / 3, 6, L - 6);
      tramos = [[0, tG - 3], [tG + 3, L]];
      puerta = { c: en(tG), ang };
    }
    tramos.forEach(([s0, s1]) => {
      const m = en((s0 + s1) / 2), len = s1 - s0, pon = (lista, w, h, d, y) => lista.push(new THREE.BoxGeometry(w, h, d).rotateY(ang).translate(m[0], y + h / 2, -m[1]));
      pon(W.ladrillo, len, 0.6, 0.27, 0); pon(W.muro, len, 1.8, 0.2, 0.6); pon(W.remate, len + 0.08, 0.08, 0.3, 2.4);
      // pilastras de 3,5 m en 3,5 m (la de la esquina la pone el tramo que arranca en ella; junto al portón, su pilar)
      for (let s = i === iF && s0 > 0 ? s0 + 3.5 : s0; s < s1 - 0.6; s += 3.5) { const c = en(s); W.muro.push(new THREE.BoxGeometry(0.36, 2.46, 0.36).rotateY(ang).translate(c[0], 1.23, -c[1])); }
    });
  });
  if (puerta) {
    // pilares de ladrillo y dos hojas de reja con lámina abajo, cerradas
    const { c, ang } = puerta, hoja = [];
    [-3.2, 3.2].forEach((x) => W.ladrillo.push(new THREE.BoxGeometry(0.5, 2.9, 0.5).translate(x, 1.45, 0)));
    [-1, 1].forEach((s) => {
      const x0 = s * 0.03, x1 = s * 2.92, xm = (x0 + x1) / 2, w = Math.abs(x1 - x0);
      hoja.push(new THREE.BoxGeometry(w, 0.08, 0.08).translate(xm, 2.24, 0), new THREE.BoxGeometry(w, 0.08, 0.08).translate(xm, 0.1, 0), new THREE.BoxGeometry(w, 0.9, 0.03).translate(xm, 0.55, 0));
      [x0, x1].forEach((x) => hoja.push(new THREE.BoxGeometry(0.08, 2.2, 0.08).translate(x, 1.18, 0)));
      for (let k = 1; k < 19; k++) hoja.push(new THREE.BoxGeometry(0.025, 1.3, 0.025).translate(x0 + (x1 - x0) * (k / 19), 1.6, 0));
    });
    const giro = (g) => g.rotateY(ang).translate(c[0], 0, -c[1]);
    W.ladrillo.splice(-2, 2, ...W.ladrillo.slice(-2).map(giro));
    W.porton.push(...hoja.map(giro));
  }
  add(raiz, unir(W.muro), C.muro, true); add(raiz, unir(W.ladrillo), C.ladrillo, true); add(raiz, unir(W.remate), C.remate, true);
  if (W.porton.length) add(raiz, unir(W.porton), C.porton, true);

  // --- calvas: el camino del portón a la gradería y al home, frente a la gradería, las cajas de los coaches y el jardín
  const calvas = [], pg = puerta ? aLocal(puerta.c) : [-26, -22];
  for (let k = 0; k <= 10; k++) { const t = k / 10; calvas.push(mancha(r, pg[0] + (-4 - pg[0]) * t, pg[1] + 2 + (-6 - pg[1] - 2) * t, 1.5 + r() * 0.6, 9)); }
  for (let s = 6; s <= 26; s += 3.5) calvas.push(mancha(r, ...enLinea(1, s, 7.2), 1.3 + r() * 0.5, 9));
  [[13.5, 5], [-13.5, 5]].forEach(([u, v]) => calvas.push(mancha(r, u, v, 1.6, 10)));
  for (let k = 0; k < 11; k++) { const v = 30 + r() * 34, u = (r() - 0.5) * 1.3 * v; calvas.push(mancha(r, u, v, 1.4 + r() * 2.8, 12, 0.6)); }
  add(loc, unir(calvas.map((p) => losa(p, 0.07))), C.calva);
  // --- cuadro de tierra irregular (todo el cuadro, sin grama: así está), la loma y el home
  const piel = [];
  for (let i = 0; i < 60; i++) {
    const t = (i / 60) * Math.PI * 2, R = (20 - 6.2 * Math.pow((1 - Math.cos(t)) / 2, 1.4)) * (1 + 0.06 * Math.sin(3 * t + 1.3) + 0.04 * Math.sin(7 * t + 0.4) + (r() - 0.5) * 0.05);
    piel.push([R * Math.sin(t), 11 + R * Math.cos(t)]);
  }
  add(loc, losa(piel, 0.09), C.tierra);
  add(loc, new THREE.CylinderGeometry(2.4, 2.9, 0.16, 20).translate(0, 0.17, -13.11), C.loma);
  // --- cal borrada: tramos de las líneas de foul, las bases sucias, la goma y el home
  const cal = [];
  [-1, 1].forEach((lado) => [[0.7, 10], [12, 24.5], [27.5, 38], [42, 49]].forEach(([s0, s1]) => cal.push(cinta([enLinea(lado, s0, 0), enLinea(lado, s1, 0)], 0.09, 0.11))));
  const lb = 18.29 * Math.SQRT1_2;
  [[lb, lb], [0, 25.87], [-lb, lb]].forEach(([u, v]) => cal.push(new THREE.BoxGeometry(0.38, 0.08, 0.38).rotateY(Math.PI / 4).translate(u, 0.13, -v)));
  cal.push(losa([[0, 0], [0.22, 0.22], [0.22, 0.43], [-0.22, 0.43], [-0.22, 0.22]], 0.12), new THREE.BoxGeometry(0.61, 0.05, 0.15).translate(0, 0.27, -13.11));
  add(loc, unir(cal), C.cal);
  // --- backstop viejo: malla de 5 m sobre tubos oxidados en arco detrás del home, con tablones abajo
  const arco = Array.from({ length: 9 }, (_, i) => { const a = Math.PI + (-0.95 + (i / 8) * 1.9); return [7.2 * Math.sin(a), 7.2 * Math.cos(a)]; });
  const bs = malla(arco, 5, { cada: 2.4, r: 0.05 }), tablas = [];
  for (let i = 1; i < arco.length; i++) { const [a, b] = [arco[i - 1], arco[i]]; tablas.push(new THREE.BoxGeometry(Math.hypot(b[0] - a[0], b[1] - a[1]), 0.6, 0.05).rotateY(Math.atan2(b[1] - a[1], b[0] - a[0])).translate((a[0] + b[0]) / 2, 0.3, -(a[1] + b[1]) / 2)); }
  add(loc, unir(bs.panos), C.malla); add(loc, unir([...bs.postes, ...bs.rieles]), C.oxido, true); add(loc, unir(tablas), C.madera, true);
  // --- gradería vieja de concreto por el lado de primera: cinco filas, columnas de tubo y techo de zinc a un agua, con
  // láminas más oxidadas; mira hacia la línea
  const grada = new THREE.Group(), [gu, gv] = enLinea(1, 17, 10.5);
  grada.position.set(gu, 0, -gv); grada.rotation.y = (5 * Math.PI) / 4; loc.add(grada);
  grada.add(graderia(0, 0, 18, 5, 0, C.concreto));
  const cols = [], techo = [], parches = [], pend = Math.atan2(1.3, 4.9);
  [-8.6, -4.3, 0, 4.3, 8.6].forEach((x) => { cols.push(barra([x, 0, 0.5], [x, 3.75, 0.5], 0.07, 6), barra([x, 0, -4.4], [x, 5.05, -4.4], 0.07, 6), barra([x, 3.75, 0.5], [x, 5.05, -4.4], 0.05, 5)); });
  techo.push(new THREE.BoxGeometry(19.4, 0.04, 5.8).rotateX(pend).translate(0, 4.43, -1.95));
  [-6.1, -1.3, 3.9, 7.4].forEach((x, k) => parches.push(new THREE.BoxGeometry(1.1 + k * 0.3, 0.02, 5.8).rotateX(pend).translate(x, 4.47, -1.95)));
  add(grada, unir(cols), C.oxido, true); add(grada, unir(techo), C.zinc, true); add(grada, unir(parches), C.zincOx);
  // --- postes de luz viejos de concreto en las esquinas del campo, con tres reflectores apuntando al cuadro
  // (el giro deja el frente local +z mirando al foco, como en torresLuz)
  const pPost = [[-38, 6], [38, 6], [-35, 58], [35, 58]].map(([u, v]) => [u, v, Math.atan2(-u, -(30 - v))]);
  const fuste = unir([new THREE.CylinderGeometry(0.13, 0.24, 14, 8).translate(0, 7, 0), new THREE.BoxGeometry(3.2, 0.14, 0.14).translate(0, 13.5, 0)]);
  const caj = unir([-1.1, 0, 1.1].map((x) => new THREE.BoxGeometry(0.55, 0.4, 0.32).rotateX(0.4).translate(x, 13.75, 0.25)));
  const cara = unir([-1.1, 0, 1.1].map((x) => new THREE.PlaneGeometry(0.46, 0.3).rotateX(0.4).translate(x, 13.75 - 0.06, 0.25 + 0.165)));
  loc.add(instanciar(fuste, C.poste, pPost), instanciar(caj, C.oxido, pPost), instanciar(cara, luzComun(), pPost, { sombra: false }));
  // --- bancas sueltas por el lado de tercera
  loc.add(bancas([10, 16, 22].map((s) => [...enLinea(-1, s, 8.2), (3 * Math.PI) / 4])));
  // --- un partido de barrio: lanzador, bateador, receptor, defensas y unos niños detrás del backstop; público en la gradería
  const jug = [Object.assign([0, 13.4, Math.PI], { h: 0.24 }), [-1.0, 0.4, -Math.PI / 2], [0, -1.6, 0], [lb + 2, lb + 1.2, -2.4], [-lb - 2.2, lb + 0.8, 2.4], [-6.5, 21, Math.PI], [4.5, 23.5, Math.PI], [-22, 46, 2.6], [3, 52, Math.PI], [20, 44, -2.6]];
  loc.add(gente(jug, { semilla: 17 }), gente([[-2.5, -8.6, 0.2], [-1.4, -8.9, -0.3], [2.2, -8.4, 0.6], [-3.4, 3.2, 1.1]], { semilla: 19, escala: 0.66 }));
  const sentados = [];
  [[-6.5, 0], [-5.9, 0], [-1.2, 1], [3.6, 1], [4.2, 1], [-3.8, 2], [6.8, 2], [0.4, 3], [-7.5, 4]].forEach(([x, f]) => sentados.push(Object.assign([x, 0.42 + 0.8 * f, 0], { h: 0.42 * (f + 1) + 0.06 })));
  grada.add(gente(sentados, { sentado: true, semilla: 21 }));
  return raiz;
}

// ---------------------------------------------------------------- cancha de fútbol de la ciudadela
// Grama con franjas de corte, demarcación reglamentaria (áreas, punto penal, medialuna, círculo central y esquinas), arcos
// con red, banderines, mallas detrás de los arcos, bancos de suplentes con techo de acrílico, gradería pequeña con público
// y un partido. Marco local: s a lo largo del eje mayor del polígono (a → b) y t a su izquierda
function canchaFutbol(poly) {
  const g = new THREE.Group();
  const [a, b] = poly, L0 = Math.hypot(b[0] - a[0], b[1] - a[1]), ex = [(b[0] - a[0]) / L0, (b[1] - a[1]) / L0], ey = [-ex[1], ex[0]];
  const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length, cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
  const st = poly.map(([x, y]) => [(x - cx) * ex[0] + (y - cy) * ex[1], (x - cx) * ey[0] + (y - cy) * ey[1]]);
  // medidas que caben en el polígono: el campo con 4,5 m detrás de los arcos y 7,5 m a los lados para bancos y gradería
  const sF = Math.min(...st.filter((p) => p[0] > 0).map((p) => p[0])), sA = Math.min(...st.filter((p) => p[0] < 0).map((p) => -p[0]));
  const tI = Math.min(...st.filter((p) => p[1] > 0).map((p) => p[1])), tD = Math.min(...st.filter((p) => p[1] < 0).map((p) => -p[1]));
  const HL = Math.min(47, Math.min(sF, sA) - 4.5), HW = Math.min(30, Math.min(tI, tD) - 7.5);
  const f = new THREE.Group(); f.position.set(cx, 0, -cy); f.rotation.y = Math.atan2(ex[1], ex[0]); g.add(f);
  const C = {
    grama: matT('cesped', { color: '#d6eac0', franjas: { origen: [cx, -cy], dir: [ex[0], -ex[1]], ancho: 6.4, k: 0.11 }, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }),
    cal: mat(new THREE.Color('#fbfbf6'), { roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }),
    tubo: mat(new THREE.Color('#f4f4f0'), { roughness: 0.35, metalness: 0.3 }), red: matT('malla', { color: '#f2f2ee', escala: 0.22 }),
    malla: matT('malla', { color: '#2f3d36' }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.5 }),
    banderin: mat(new THREE.Color('#f07a2a'), { roughness: 0.6, side: THREE.DoubleSide }), silla: mat(new THREE.Color('#1f5fa8'), { roughness: 0.45 }),
    acrilico: new THREE.MeshStandardMaterial({ color: 0xa9c3cf, roughness: 0.1, metalness: 0.1, transparent: true, opacity: 0.42, side: THREE.DoubleSide, depthWrite: false }),
    concreto: matT('concreto'),
  };
  const grama = new THREE.Mesh(losa(poly, 0.14), C.grama); grama.receiveShadow = true; g.add(grama);
  const P3 = (s, y, t) => [s, y, -t];
  // --- demarcación (12 cm) a 0,2 m
  const ln = [], w = 0.12, h = 0.2;
  ln.push(cinta([[-HL, -HW], [HL, -HW], [HL, HW], [-HL, HW], [-HL, -HW], [HL, -HW]], w, h), cinta([[0, -HW], [0, HW]], w, h), cinta(circulo(0, 0, 9.15, 0, Math.PI * 2, 48), w, h));
  [-1, 1].forEach((sg) => {
    const x0 = sg * HL;
    ln.push(cinta([[x0, -20.16], [x0 - sg * 16.5, -20.16], [x0 - sg * 16.5, 20.16], [x0, 20.16]], w, h), cinta([[x0, -9.16], [x0 - sg * 5.5, -9.16], [x0 - sg * 5.5, 9.16], [x0, 9.16]], w, h));
    const pen = x0 - sg * 11, ab = Math.acos(5.5 / 9.15);
    ln.push(cinta(circulo(pen, 0, 9.15, sg > 0 ? Math.PI - ab : -ab, sg > 0 ? Math.PI + ab : ab, 16), w, h), losa(circulo(pen, 0, 0.2, 0, Math.PI * 2, 10).slice(0, -1), h));
    [-1, 1].forEach((st2) => ln.push(cinta(circulo(x0, st2 * HW, 1, sg > 0 ? (st2 > 0 ? Math.PI : Math.PI / 2) : (st2 > 0 ? -Math.PI / 2 : 0), sg > 0 ? (st2 > 0 ? 1.5 * Math.PI : Math.PI) : (st2 > 0 ? 0 : Math.PI / 2), 6), w, h)));
  });
  ln.push(losa(circulo(0, 0, 0.2, 0, Math.PI * 2, 10).slice(0, -1), h));
  const lineas = new THREE.Mesh(unir(ln), C.cal); lineas.receiveShadow = true; f.add(lineas);
  // --- arcos de 7,32 × 2,44 m con red, banderines de esquina
  const tubos = [], redes = [], band = [];
  [-1, 1].forEach((sg) => {
    const s0 = sg * HL, s1 = sg * (HL + 2);
    [-3.66, 3.66].forEach((t) => {
      tubos.push(barra(P3(s0, 0, t), P3(s0, 2.44, t), 0.06, 8), barra(P3(s0, 2.44, t), P3(s1, 0.04, t), 0.03, 5), barra(P3(s0, 0.04, t), P3(s1, 0.04, t), 0.03, 5));
      redes.push(pano(P3(s0, 0, t), P3(s0, 2.44, t), P3(s1, 0, t)));
    });
    tubos.push(barra(P3(s0, 2.44, -3.72), P3(s0, 2.44, 3.72), 0.06, 8), barra(P3(s1, 0.04, -3.66), P3(s1, 0.04, 3.66), 0.03, 5));
    redes.push(pano(P3(s0, 2.44, -3.66), P3(s0, 2.44, 3.66), P3(s1, 0, 3.66), P3(s1, 0, -3.66)));
    [-1, 1].forEach((st2) => { tubos.push(barra(P3(s0, 0, st2 * HW), P3(s0, 1.5, st2 * HW), 0.02, 5)); band.push(new THREE.PlaneGeometry(0.4, 0.3).translate(sg * 0.22, 1.33, 0).translate(s0, 0, -st2 * HW)); });
  });
  [[tubos, C.tubo], [redes, C.red], [band, C.banderin]].forEach(([gs, m]) => { const o = new THREE.Mesh(unir(gs), m); o.castShadow = m !== C.red; o.receiveShadow = true; f.add(o); });
  // --- mallas de 6 m detrás de los arcos y malla baja frente a la gradería
  const mF = [malla([[-(HL + 3.4), -16], [-(HL + 3.4), 16]], 6, { cada: 4 }), malla([[HL + 3.4, -16], [HL + 3.4, 16]], 6, { cada: 4 }), malla([[-HL, -(HW + 2)], [HL, -(HW + 2)]], 1.1, { cada: 3, r: 0.03 })];
  f.add(new THREE.Mesh(unir(mF.flatMap((m) => m.panos)), C.malla));
  const posMF = new THREE.Mesh(unir(mF.flatMap((m) => [...m.postes, ...m.rieles])), C.oscuro); posMF.castShadow = true; f.add(posMF);
  // --- bancos de suplentes (5 m, sillas azules, techo y espaldar de acrílico) en el lado oriental, a 8 m del medio
  const est = [], sillas = [], acr = [], tB = HW + 2.8;
  [-8, 8].forEach((s) => {
    [-2.5, 2.5].forEach((d) => est.push(barra(P3(s + d, 0, tB + 0.6), P3(s + d, 2.0, tB + 0.6), 0.04, 6), barra(P3(s + d, 2.0, tB + 0.6), P3(s + d, 2.0, tB - 0.9), 0.03, 5)));
    est.push(new THREE.BoxGeometry(5, 0.06, 0.06).translate(s, 0.42, -(tB + 0.1)));
    for (let k = 0; k < 9; k++) sillas.push(new THREE.BoxGeometry(0.46, 0.06, 0.42).translate(s - 2.1 + k * 0.525, 0.46, -tB), new THREE.BoxGeometry(0.46, 0.4, 0.05).rotateX(0.12).translate(s - 2.1 + k * 0.525, 0.7, -(tB + 0.22)));
    acr.push(new THREE.BoxGeometry(5.2, 0.02, 1.6).rotateX(-0.12).translate(s, 2.02, -(tB - 0.15)), new THREE.BoxGeometry(5.2, 1.8, 0.02).translate(s, 1.0, -(tB + 0.62)));
  });
  [[est, C.oscuro], [sillas, C.silla], [acr, C.acrilico]].forEach(([gs, m]) => { const o = new THREE.Mesh(unir(gs), m); o.castShadow = m !== C.acrilico; o.receiveShadow = true; f.add(o); });
  // --- gradería de tres filas en el lado occidental, con público
  const gr = graderia(0, -(HW + 4), 22, 3, Math.PI, C.concreto); f.add(gr);
  // el público (en el marco de la cancha: la gradería está girada 180°) y los suplentes en sus bancos, en una sola malla
  const pub = [-9.4, -7.8, -6.6, 6.6, 7.2, 8.4, 9.6].map((s) => Object.assign([s, tB + 0.05, Math.PI], { h: 0.54 }));
  for (let fl = 0; fl < 3; fl++) for (let k = 0; k < 40; k++) if ((k * 7 + fl * 3) % 5 < 2) pub.push(Object.assign([10.2 - k * 0.52, -(HW + 4) - (0.42 + 0.8 * fl), Math.PI], { h: 0.42 * (fl + 1) + 0.06 }));
  f.add(gente(pub, { sentado: true, semilla: 31 }));
  // --- el partido: amarillo contra rojo, arqueros, árbitro y un balón
  const A = { camisa: '#f2c230', pantalon: '#1f4f8f' }, B = { camisa: '#c8372d', pantalon: '#f2f2ee' }, R = { camisa: '#1d2124', pantalon: '#1d2124' };
  const jug = [[-HL + 1.2, 0.5, 0, { camisa: '#3a7d44', pantalon: '#1f2329' }], [HL - 1.2, -0.8, Math.PI, { camisa: '#7a4fa0', pantalon: '#1f2329' }],
    [-24, 10, 0.3, A], [-20, -14, 0.1, A], [-9, 3, 0.5, A], [-4, -16, 0.2, A], [6, 8, 0.6, A], [14, -5, 0.4, A],
    [-15, 4, Math.PI, B], [-6, -8, 2.8, B], [2, 2.5, 3.0, B], [10, 15, 3.3, B], [19, -9, 2.9, B], [27, 4, 3.1, B], [1, -12, 1.2, R]];
  f.add(gente(jug.map(([s, t, rr, ropa]) => [s, t, rr, ropa]), { semilla: 33 }));
  const balon = new THREE.Mesh(new THREE.SphereGeometry(0.11, 12, 8), mat(new THREE.Color('#ffffff'), { roughness: 0.5 })); balon.position.set(3.2, 0.25, -1.9); balon.castShadow = true; f.add(balon);
  return g;
}

// ---------------------------------------------------------------- canchas cubiertas y skatepark (explanada al sur del CIC)
// Dos canchas múltiples de 28 × 15 m (baloncesto y microfútbol) en piso de caucho con zona de seguridad, bajo una cubierta
// de zinc en arco rebajado sobre cerchas y columnas de acero con pedestal, canales y bajantes; malla perimetral de 3 m,
// luminarias LED colgadas de las cerchas (se encienden al atardecer), gradería con público y jugadores. Al oriente, un
// skatepark de ≈1.000 m² con bowl, cuarto de tubo, funbox, cuñas, barandas de grind y un muro con grafiti; bicicletero,
// bancas, palmas, jardín y árboles hacia el caño
function instalacionesCIC(poly) {
  const raiz = new THREE.Group(), [a, b] = [poly[0], poly[1]], ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]), cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const piso = capa('piso'), obras = capa('obras'), cubierta = capa('cubierta');
  const M = {
    losa: matT('concreto', { modo: 'xz', color: '#dcd6cb' }),
    seguridad: matT('caucho', { color: '#4f6072', escala: 0.9, relieve: 0 }), cancha: matT('caucho', { color: '#2f6fb8', escala: 0.9, relieve: 0 }), cancha2: matT('caucho', { color: '#1f9e8f', escala: 0.9, relieve: 0 }),
    cal: new THREE.MeshBasicMaterial({ color: 0xffffff }),
    columna: mat(new THREE.Color('#8e99a2'), { roughness: 0.38, metalness: 0.72 }), pedestal: matT('concreto', { color: '#cfc9be' }),
    // lámina prepintada nueva: la onda del zinc solo como relieve (su color trae manchas de óxido, que son del estadio de hoy)
    techo: matT('zinc', { map: null, alto: tex('zinc'), escalaAlto: 1, color: '#e3e8eb', side: THREE.DoubleSide }),
    skate: matT('concreto', { color: '#c9c4bb' }), bowl: matT('concreto', { color: '#d3cec5', side: THREE.DoubleSide }),
    metal: mat(new THREE.Color('#b9c0c6'), { roughness: 0.25, metalness: 0.85 }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.45 }),
    blanco: mat(new THREE.Color('#f4f4f0'), { roughness: 0.4, metalness: 0.2 }), aro: mat(new THREE.Color('#e8692f'), { roughness: 0.4, metalness: 0.5 }),
    red: matT('malla', { color: '#f2f2ee', escala: 0.22 }), malla: matT('malla', { color: '#33413a' }),
    tablero: new THREE.MeshStandardMaterial({ color: 0xeef3f5, roughness: 0.12, metalness: 0.1, transparent: true, opacity: 0.75 }),
    grafiti: new THREE.MeshStandardMaterial({ map: texturaGrafiti(), roughness: 0.9 }),
  };
  const add = (padre, geo, m, sombra = true) => { const o = new THREE.Mesh(geo, m); o.castShadow = sombra; o.receiveShadow = true; padre.add(o); return o; };
  add(piso, losa(poly, 0.07), M.losa, false);
  const g = new THREE.Group(); g.position.set(cx - 11, 0, -cy); g.rotation.y = ang; raiz.add(g);
  // --- dos canchas de 28 × 15 m sobre la zona de seguridad, con sus líneas: baloncesto (zonas) y microfútbol (áreas)
  add(g, losa([[-15.6, -15.7], [15.6, -15.7], [15.6, 15.7], [-15.6, 15.7]], 0.09), M.seguridad, false);
  const ln = [];
  [[-8, M.cancha], [8, M.cancha2]].forEach(([v, m]) => {
    const c = [[-14, v - 7.5], [14, v - 7.5], [14, v + 7.5], [-14, v + 7.5]];
    add(g, losa(c, 0.11), m, false);
    ln.push(cinta([...c, c[0], c[1]], 0.08, 0.13), cinta([[0, v - 7.5], [0, v + 7.5]], 0.08, 0.13), cinta(circulo(0, v, 1.8), 0.08, 0.13));
    [-1, 1].forEach((s) => {
      const x0 = s * 14;
      ln.push(cinta([[x0, v - 2.45], [x0 - s * 5.8, v - 2.45], [x0 - s * 5.8, v + 2.45], [x0, v + 2.45]], 0.08, 0.13));
      ln.push(cinta(circulo(x0, v, 6, s > 0 ? Math.PI / 2 : -Math.PI / 2, s > 0 ? 1.5 * Math.PI : Math.PI / 2, 20), 0.08, 0.13));
    });
  });
  add(g, unir(ln), M.cal, false);
  // --- aros de baloncesto (poste detrás de la línea final, brazo, tablero y aro con red) y arcos de microfútbol con red
  const acero = [], blancos = [], aros = [], redes = [], tableros = [];
  [-8, 8].forEach((v) => [-1, 1].forEach((s) => {
    const x0 = s * 14, xp = x0 + s * 1.3, s1 = x0 + s * 0.8;
    acero.push(barra([xp, 0, -v], [xp, 3.55, -v], 0.09, 8), barra([xp, 3.45, -v], [x0 - s * 1.15, 3.45, -v], 0.05, 6), barra([xp, 2.5, -v], [x0 - s * 0.9, 3.4, -v], 0.04, 5));
    tableros.push(new THREE.BoxGeometry(0.04, 1.05, 1.8).translate(x0 - s * 1.2, 3.42, -v));
    aros.push(new THREE.TorusGeometry(0.23, 0.02, 6, 18).rotateX(Math.PI / 2).translate(x0 - s * 1.6, 3.05, -v));
    redes.push(new THREE.CylinderGeometry(0.23, 0.15, 0.42, 10, 1, true).translate(x0 - s * 1.6, 2.84, -v));
    [-1.5, 1.5].forEach((t) => {
      blancos.push(barra([x0, 0, -(v + t)], [x0, 2, -(v + t)], 0.04, 6), barra([x0, 2, -(v + t)], [s1, 0.03, -(v + t)], 0.025, 5));
      redes.push(pano([x0, 0, -(v + t)], [x0, 2, -(v + t)], [s1, 0, -(v + t)]));
    });
    blancos.push(barra([x0, 2, -(v - 1.54)], [x0, 2, -(v + 1.54)], 0.04, 6), barra([s1, 0.03, -(v - 1.5)], [s1, 0.03, -(v + 1.5)], 0.025, 5));
    redes.push(pano([x0, 2, -(v - 1.5)], [x0, 2, -(v + 1.5)], [s1, 0, -(v + 1.5)], [s1, 0, -(v - 1.5)]));
  }));
  // --- estructura: columnas cilíndricas de acero sobre pedestal, bajantes junto a tres de ellas y malla de 3 m en los
  // costados (abierta en el medio, por donde se entra)
  const cols = [], pedes = [];
  for (let u = -22.5; u <= 22.6; u += 7.5) [-16, 16].forEach((v) => {
    cols.push(new THREE.CylinderGeometry(0.2, 0.2, 6.6, 12).translate(u, 3.7, -v)); pedes.push(new THREE.BoxGeometry(0.76, 0.4, 0.76).translate(u, 0.2, -v));
    if (Math.abs(u) > 22 || Math.abs(u) < 0.1) cols.push(barra([u + 0.38, 0.05, -v * 1.0375], [u + 0.38, 6.9, -v * 1.0375], 0.06, 6));   // hasta la canal
  });
  const mallas = [-16, 16].flatMap((v) => [malla([[-22.5, v], [-2.5, v]], 3, { cada: 2.5, r: 0.035 }), malla([[2.5, v], [22.5, v]], 3, { cada: 2.5, r: 0.035 })]);
  const mG = new THREE.Group(); obras.add(mG);
  add(mG, unir(cols), M.columna); add(mG, unir(pedes), M.pedestal); add(mG, unir(mallas.flatMap((m) => m.panos)), M.malla, false);
  add(mG, unir(mallas.flatMap((m) => [...m.postes, ...m.rieles])), M.oscuro);
  // --- cubierta: arco rebajado de zinc sobre siete cerchas de cordones curvos con diagonales, correas y canales de aguas lluvia
  const yArco = (v) => 7 + 4 * (1 - (v / 16.4) ** 2), yInf = (v) => 7 + 3.1 * (1 - (v / 16) ** 2);
  const arco = new THREE.Shape(), n = 24;
  for (let i = 0; i <= n; i++) { const v = -16.4 + (32.8 * i) / n; arco[i ? 'lineTo' : 'moveTo'](v, yArco(v)); }
  for (let i = n; i >= 0; i--) { const v = -16.4 + (32.8 * i) / n; arco.lineTo(v, yArco(v) + 0.25); }
  const techo = add(cubierta, new THREE.ExtrudeGeometry(arco, { depth: 46, bevelEnabled: false }).rotateY(Math.PI / 2).translate(-23, 0, 0), M.techo);
  techo.receiveShadow = true;
  const cer = [], led = [], caras = [];
  for (let u = -22.5; u <= 22.6; u += 7.5) {
    const sup = [], inf = [];
    for (let k = 0; k <= 16; k++) { const v = -16 + k * 2; sup.push([u, yArco(v) - 0.06, -v]); inf.push([u, yInf(v), -v]); }
    for (let k = 1; k <= 16; k++) cer.push(barra(sup[k - 1], sup[k], 0.06, 4), barra(inf[k - 1], inf[k], 0.05, 4), barra(k % 2 ? inf[k - 1] : sup[k - 1], k % 2 ? sup[k] : inf[k], 0.03, 4));
    // luminarias LED lineales colgadas de la cercha: carcasa oscura y cara de luz hacia abajo (luzComun)
    [-11, -4, 4, 11].forEach((v) => {
      const y = yInf(v) - 0.4;
      led.push(new THREE.BoxGeometry(1.2, 0.08, 0.26).translate(u, y, -v), barra([u, y + 0.04, -v], [u, yInf(v), -v], 0.01, 3));
      caras.push(new THREE.PlaneGeometry(1.1, 0.2).rotateX(Math.PI / 2).translate(u, y - 0.045, -v));
    });
  }
  [-14, -10, -6, -2, 2, 6, 10, 14].forEach((v) => cer.push(new THREE.BoxGeometry(46, 0.12, 0.08).translate(0, yArco(v) - 0.1, -v)));
  [-1, 1].forEach((s) => cer.push(new THREE.BoxGeometry(46.6, 0.25, 0.32).translate(0, 6.95, -s * 16.6)));
  add(cubierta, unir(cer), M.columna); add(cubierta, unir(led), M.oscuro, false);
  const luces = add(cubierta, unir(caras), luzComun(), false);
  luces.receiveShadow = false;
  // aros, arcos, tableros y redes con las canchas (en el piso: no crecen con la estructura)
  add(g, unir(acero), M.oscuro); add(g, unir(blancos), M.blanco); add(g, unir(aros), M.aro); add(g, unir(tableros), M.tablero, false); add(g, unir(redes), M.red, false);
  g.add(charcos([[0, -8, 12], [0, 8, 12], [36, 0, 14]], { h: 0.16 }));
  // --- gradería de tres filas al sur de las canchas, con público
  const gr = graderia(0, -18.6, 14, 3, Math.PI, M.pedestal); g.add(gr);
  // (el público va con los demás sentados, en el marco de las canchas: la gradería está girada 180°)
  const pub = [[41, -18, Math.PI], [43.4, -18, Math.PI]].map((p) => Object.assign(p, { h: 0.63 }));   // dos en el ledge del skatepark
  for (let fl = 0; fl < 3; fl++) for (let k = 0; k < 26; k++) if ((k * 5 + fl * 2) % 4 < 2) pub.push(Object.assign([6.6 - k * 0.52, -18.6 - (0.42 + 0.8 * fl), Math.PI], { h: 0.42 * (fl + 1) + 0.06 }));
  g.add(gente(pub, { sentado: true, semilla: 41 }));
  // --- skatepark (≈ 21 × 40 m) al oriente de la cubierta
  const sk = new THREE.Group(); sk.position.set(36, 0, 0); g.add(sk);
  add(sk, losa([[-10.5, -20], [10.5, -20], [10.5, 20], [-10.5, 20]], 0.12), M.skate, false);
  // bowl elevado: fondo plano, transición curva de 1,8 m hasta el coping, terraza y muro exterior
  const perfil = [[0.01, 0.13], [2.4, 0.13]];
  for (let k = 1; k <= 8; k++) { const fi = (k / 8) * (Math.PI / 2); perfil.push([2.4 + 1.8 * Math.sin(fi), 1.93 - 1.8 * Math.cos(fi)]); }
  perfil.push([5.2, 1.93], [5.25, 0.12]);
  add(sk, new THREE.LatheGeometry(perfil.map(([x, y]) => new THREE.Vector2(x, y)), 40).translate(-4, 0, -10), M.bowl);
  // cuarto de tubo de 8 m con terraza al norte, cuñas enfrentadas, funbox con baranda, ledge y muro con grafiti
  const qp = new THREE.Shape([new THREE.Vector2(0, 0.12)]);
  for (let k = 1; k <= 8; k++) { const fi = (k / 8) * 1.05; qp.lineTo(2.6 * Math.sin(fi), 2.72 - 2.6 * Math.cos(fi)); }
  qp.lineTo(3.4, 2.72 - 2.6 * Math.cos(1.05)); qp.lineTo(3.4, 0.12);
  add(sk, new THREE.ExtrudeGeometry(qp, { depth: 8, bevelEnabled: false }).rotateY(Math.PI / 2).translate(1.5, 0, -16), M.skate);
  const cuna = (w, l, h) => new THREE.ExtrudeGeometry(new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(l, 0), new THREE.Vector2(l, h)]), { depth: w, bevelEnabled: false });
  const bloques = [cuna(5, 6, 1.4).translate(-3, 0.12, -2.5).translate(-6, 0, 12), cuna(5, 6, 1.4).translate(-3, 0.12, -2.5).rotateY(Math.PI).translate(5, 0, 12),
    new THREE.BoxGeometry(3, 0.6, 4).translate(5, 0.42, -4), new THREE.BoxGeometry(5, 0.45, 0.6).translate(6, 0.345, 18), new THREE.BoxGeometry(8, 1.4, 0.25).translate(-4, 0.82, 19.2)];
  // las rampas del funbox, con el lado alto contra sus dos caras
  bloques.push(cuna(3, 2.4, 0.6).translate(-2.4, 0.12, -1.5).rotateY(-Math.PI / 2).translate(5, 0, -6), cuna(3, 2.4, 0.6).translate(-2.4, 0.12, -1.5).rotateY(Math.PI / 2).translate(5, 0, -2));
  add(sk, unir(bloques), M.skate);
  const fierros = [barra([6.2, 0.75, -2.1], [6.2, 0.75, -5.9], 0.03, 6), new THREE.TorusGeometry(4.2, 0.05, 6, 48).rotateX(Math.PI / 2).translate(-4, 1.93, -10), barra([1.5, 2.72 - 2.6 * Math.cos(1.05), -18.25], [9.5, 2.72 - 2.6 * Math.cos(1.05), -18.25], 0.05, 6)];
  [[-8.5, 1.5, -8.5, -4.5], [-4, -6.5, 2, -6.5]].forEach(([u0, v0, u1, v1]) => {
    fierros.push(barra([u0, 0.42, -v0], [u1, 0.42, -v1], 0.035, 6));
    [[u0, v0], [u1, v1], [(u0 + u1) / 2, (v0 + v1) / 2]].forEach(([u, v]) => fierros.push(barra([u, 0.12, -v], [u, 0.42, -v], 0.03, 5)));
  });
  add(sk, unir(fierros), M.metal);
  const graf = new THREE.Mesh(new THREE.PlaneGeometry(7.8, 1.3).translate(-4, 0.82, 19.33), M.grafiti); graf.receiveShadow = true; sk.add(graf);
  // --- gente: baloncesto en la cancha sur, microfútbol en la norte, patinadores y ciclistas; bicicletero y bancas al norte
  const jug = [[-11, -7, 0.4], [-9.5, -9.6, 2.1], [-12.2, -9.8, 1.0], [-8, -6.2, -2.6], [-6.4, -8.8, 2.9], [-10.4, -5.4, 1.8],
    [-10, 9, 0.2], [-5, 5.5, 0.6], [-2, 10.5, 2.4], [3, 7.5, -2.8], [6, 4.8, 3.0], [9, 10, 2.6], [12.6, 8.2, Math.PI], [-12.6, 7.8, 0], [0.5, 1.2, 1.4]];
  // patinadores (el skatepark está 36 m al oriente): en el fondo del bowl y en su terraza, sobre el funbox, en la losa y en
  // la terraza del cuarto de tubo
  [[-4, 10, 0.3, 0.13], [0.7, 10, 1.2, 1.93], [5, 4, 2.2, 0.72], [0, -2, 0.8, 0.12], [5.5, 18.8, 2.9, 1.43]].forEach(([u, v, r2, h]) => jug.push(Object.assign([u + 36, v, r2], { h })));
  g.add(gente(jug, { semilla: 43 }));
  g.add(instanciar(bici(), M.oscuro, Array.from({ length: 6 }, (_, i) => [-16 + i * 0.75, 20.2, Math.PI / 2])), new THREE.Mesh(barra([-16.4, 0.5, -20.2], [-11.8, 0.5, -20.2], 0.03, 5), M.metal));
  g.add(bancas([[-8, 19.6, 0], [-2, 19.6, 0], [8, 19.6, 0], [16, 19.6, 0]]), canecas([[-5, 19.6], [12, 19.6]]));
  // --- verde: palmas al norte y al occidente, jardín al norte y árboles de sombra hacia el caño
  const verde = new THREE.Group(); g.add(verde);
  verde.add(palmas([...Array.from({ length: 9 }, (_, i) => [-24 + i * 9, 25.5]), ...Array.from({ length: 6 }, (_, i) => [-27.2, -22 + i * 8.8])], { alto: 8.5, semilla: 49 }));   // a 4 m del alero
  // (el jardín va aparte: brotar anima instancias de mallas de igual cantidad, y las matas de un jardín no lo son); las dos
  // franjas comparten sus mallas por tipo de planta
  const pj = [...sembrar([[-24, 22.6], [-12.5, 22.6], [-12.5, 24.4], [-24, 24.4]], 26, 0.75, 51), ...sembrar([[20, 22.6], [44, 22.6], [44, 24.4], [20, 24.4]], 52, 0.75, 53)];
  [['cordyline', 0.95], ['heliconia', 1.4], ['helecho', 0.85], ['arbusto', 1.1]].forEach(([tipo, alto], k) => g.add(matas(pj.filter((_, i) => i % 4 === k), { tipo, alto, semilla: 57 + k })));
  verde.add(arboles(Array.from({ length: 6 }, (_, i) => [48.5, -21 + i * 8.4]), { alto: 8, semilla: 55, especie: 'mixto' }));
  [obras, cubierta].forEach((o) => { o.position.copy(g.position); o.rotation.copy(g.rotation); });
  raiz.userData.partes = { piso, obras, cubierta, verde };
  raiz.userData.centro = [cx, cy];
  return raiz;
}

export async function crear(esc, datos) {
  const G = datos.geo?.urbanismo || {}, color = '--m-urbanismo';
  const S = (id) => sitio(datos, 'urbanismo', id), Tz = (id) => trazado(datos, 'urbanismo', id);
  const sb = S('softbol_home'), mi = S('mirador_origen'), lt = S('letras_yondo');
  const cfgSoft = sb ? { home: [sb.x, sb.y], rumbo: sb.orientacion_grados ?? BASE.softbol.rumbo } : BASE.softbol;
  const cfgMir = {
    origen: mi ? [mi.x, mi.y] : BASE.mirador.origen, angulo: mi?.angulo_orilla ?? BASE.mirador.angulo,
    diseno: { zonaA: S('mirador_zona_a')?.poligono, plaza: S('mirador_zona_b')?.poligono, mirador: S('mirador_elevado')?.poligono, muelle: S('muelle_flotante')?.poligono, letras: lt ? [lt.x, lt.y] : null, deck: Tz('sendero_deck')?.puntos, pasarela: Tz('pasarela_muelle')?.puntos, acceso: Tz('acceso_plaza')?.puntos, orilla: Tz('orilla_2025')?.puntos },
  };
  const ala = Tz('alameda')?.puntos || BASE.alameda, conector = Tz('conector_cic')?.puntos;
  const eje = Tz('parque_lineal_f1')?.puntos || ejeCano();
  const tramos = trazados(datos, 'urbanismo', 'tramo').filter((t) => t.fase === 1 && t.y0 != null).map((t) => ({ y0: t.y0, y1: t.y1, occidente: t.occidente_m, oriente: t.oriente_m }));
  const humedales = sitios(datos, 'urbanismo', 'humedal').filter((s) => s.fase === 1).map((s) => s.poligono);
  const bosques = sitios(datos, 'urbanismo', 'bosque').map((s) => s.poligono);
  const puentes = sitios(datos, 'urbanismo', 'puente').filter((s) => s.fase === 1);
  const ciud = S('ciudadela')?.poligono || BASE.ciudadela, explanada = S('explanada_cic')?.poligono || BASE.explanada;

  // --- hoy (portadilla): el estadio y el caño canalizado, tal como están. El estadio se modela (antes era solo la línea
  // del cerramiento sobre el potrero); la línea gris queda encima del muro, como en la leyenda
  const cHoy = esc.capa('urb.hoy'), cerr = S('softbol_cerramiento')?.poligono;
  if (cerr) {
    cHoy.add(estadioHoy(cfgSoft, cerr));
    esc.linea([...cerr, cerr[0]].map(([x, y]) => [x, y, 2.62]), { color: '--muted', ancho: 2.5, padre: cHoy });
    // el rótulo, al borde norte del cerramiento (el del fondo de la vista del paso, que mira al rumbo 20°) y su punto en el
    // centro: antes iba en el centroide y tapaba el tercio norte de la cancha
    const [cx, cy] = [cerr.reduce((a, p) => a + p[0], 0) / cerr.length, cerr.reduce((a, p) => a + p[1], 0) / cerr.length];
    const dN = [Math.sin(Math.PI / 9), Math.cos(Math.PI / 9)], tN = (hastaBorde([cx, cy], dN, cerr) ?? 50) + 5;
    esc.etiqueta('<b>Estadio de sóftbol (hoy)</b><small>cerramiento de 1,2 ha</small>', { pos: [cx + dN[0] * tN, cy + dN[1] * tN, 3], padre: cHoy, color: 'var(--muted)', cls: 'lbl-p mini', ancla: [0.5, 1], punto: [cx, cy, 1] });
  }
  const ejeHoy = (Tz('cano_eje')?.puntos || ejeCano()).filter(([, y]) => y <= 430);
  if (ejeHoy.length > 1) {
    esc.linea(ejeHoy.map(([x, y]) => [x, y, 1.6]), { color: '--m-aguas', ancho: 3.5, padre: cHoy });
    const [x, y] = ejeHoy[Math.floor(ejeHoy.length * 0.4)];
    esc.etiqueta('<b>Caño Colector Shell (hoy)</b><small>canalizado, de espaldas al barrio</small>', { pos: [x - 12, y, 6], padre: cHoy, color: 'var(--m-aguas)', cls: 'lbl-p mini', ancla: [1, 0.5] });
  }

  // --- ciudadela: contorno punteado, la cancha de fútbol y rótulos (encima de lo que nombran) de lo que integra
  const cCiud = esc.capa('urb.ciudadela');
  esc.linea([...ciud, ciud[0]].map(([x, y]) => [x, y, 1.5]), { color, ancho: 3, punteada: true, guion: 10, padre: cCiud });
  const rot = (txt, sub, [x, y], h = 16) => esc.etiqueta(`<b>${txt}</b>${sub ? `<small>${sub}</small>` : ''}`, { pos: [x, y, h], padre: cCiud, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  const futbol = S('cancha_futbol')?.poligono;
  if (futbol) cCiud.add(canchaFutbol(futbol));
  rot('Coliseo Benito Arias', 'se integra', BASE.hitos.coliseo, 20);
  rot('Parque Educativo', null, BASE.hitos.parque_edu, 12);
  rot('Parque principal', null, BASE.hitos.parque_principal, 10);
  rot('Cancha de fútbol', null, futbol ? [S('cancha_futbol').x, S('cancha_futbol').y] : BASE.hitos.cancha, 6);
  rot('CIC', null, BASE.hitos.cic, 12);

  // --- Cancha de Sóftbol Casabe
  const cSoft = esc.capa('urb.softbol'), soft = canchaSoftbol(cfgSoft);
  cSoft.add(soft);
  // el rótulo, detrás de la cerca del jardín central (no sobre el diamante)
  const [hx, hy] = soft.userData.aModelo(0, 88);
  esc.etiqueta('<b>Cancha de Sóftbol Casabe</b><small>109 × 102,9 m · luz LED · graderías cubiertas</small>', { pos: [hx, hy, 12], padre: cSoft, color: `var(${color})`, ancla: [0.5, 1], punto: [...soft.userData.aModelo(0, 30), 1] });

  // --- parque lineal del caño colector (fase 1: del bosque del sur a la Calle 55)
  const cCano = esc.capa('urb.cano'), pl = parqueLineal(eje, { tramos, humedales, bosques, puentes: puentes.length ? puentes.map((s) => [s.x, s.y]) : undefined });
  cCano.add(pl);
  // el rótulo, al oriente del eje (las sendas van por la orilla occidental); los de los puentes, en su propia capa
  const em = pl.userData.eje[Math.floor(pl.userData.eje.length * 0.62)];
  esc.etiqueta('<b>Parque lineal del caño colector</b><small>cauce vivo · sendero y ciclorruta · laguna y bosque inundable</small>', { pos: [em[0] + 22, em[1], 10], padre: cCano, color: `var(${color})`, ancla: [0, 0.5], punto: [em[0], em[1], 1] });
  const cPP = esc.capa('urb.puentes');
  puentes.forEach((s) => esc.etiqueta(`<b>${s.id.toUpperCase()}</b>`, { pos: [s.x, s.y, 7], padre: cPP, color: '#a8703f', cls: 'lbl-p mini', titulo: s.nombre, ancla: [0.5, 1] }));

  // --- alameda: calle compartida a nivel por las calles existentes (Calle 50, Carrera 54, carriles del coliseo y Calle 49
  // peatonal): adoquín con la franja central en el color del área y bordillos a nivel; en las esquinas, otro adoquín con
  // borde blanco (la calle sigue a nivel) y bolardos; árboles variados donde hay espacio (no sobre las casas), palmas en
  // los remates, estancias cada 24 m (jardinera, banca y caneca), luminarias LED, la señal de calle compartida al
  // empezar cada tramo y la vida de la calle: gente a pie, en bicicleta, motos parqueadas y algún carro a paso lento.
  // Conector al CIC por el PP2
  await esc.listoHuellas;
  const huellas = esc.huellas.filter((h) => !h.zona);
  const libre = (p, d = 2.2) => huellas.every((h) => Math.abs(h.cx - p[0]) > 40 || Math.abs(h.cy - p[1]) > 40 || distPoligono(p, h.pts) > d);
  const cAla = esc.capa('urb.alameda');
  const po = (k) => ({ polygonOffset: true, polygonOffsetFactor: k, polygonOffsetUnits: k });
  const pav = matT('adoquin', { color: '#ecc9a2', ...po(-6) }), franja = matT('adoquin', po(-7)), bordillo = matT('concreto', { color: '#efebe3', modo: 'xz', ...po(-5) });
  const pisoAla = new THREE.Mesh(cinta(ala, 7.5, 0.1), pav), lineaAla = new THREE.Mesh(cinta(ala, 1.5, 0.12), franja);
  const bordes = new THREE.Mesh(unir([cinta(ala, 8.1, 0.1), ...(conector ? [cinta(conector, 5.6, 0.1)] : [])]), bordillo);
  [pisoAla, lineaAla, bordes].forEach((o) => { o.receiveShadow = true; cAla.add(o); });
  esc.tenir(franja, color);
  if (conector) { const o = new THREE.Mesh(cinta(conector, 5, 0.1), pav); o.receiveShadow = true; cAla.add(o); }
  // esquinas: donde la alameda dobla (más de 25°), un cuadro de adoquín gris con borde blanco y bolardos en sus esquinas
  const esq = [];
  for (let i = 1; i < ala.length - 1; i++) {
    const a0 = Math.atan2(ala[i][1] - ala[i - 1][1], ala[i][0] - ala[i - 1][0]), a1 = Math.atan2(ala[i + 1][1] - ala[i][1], ala[i + 1][0] - ala[i][0]);
    let giro = Math.abs(a1 - a0); if (giro > Math.PI) giro = 2 * Math.PI - giro;
    if (giro > 0.44) esq.push({ p: ala[i], a0, a1 });
  }
  const pEsq = esq.map(({ p, a0 }) => rect(p[0], p[1], 8.4, 8.4, a0));
  if (pEsq.length) {
    const blanco = mat(new THREE.Color('#f4f2ea'), { roughness: 0.85, ...po(-9) });
    const e1 = new THREE.Mesh(unir(pEsq.map((p) => losa(p, 0.13))), matT('adoquin', { color: '#c2bbb2', ...po(-8) })), e2 = new THREE.Mesh(unir(pEsq.map((p) => cinta([...p, p[0], p[1]], 0.3, 0.14))), blanco);
    [e1, e2].forEach((o) => { o.receiveShadow = true; cAla.add(o); });
  }
  const sinEsquina = (p, d = 6) => esq.every(({ p: q }) => Math.hypot(p[0] - q[0], p[1] - q[1]) > d);
  const extremos = [ala[0], ala[ala.length - 1], ...(conector ? [conector[conector.length - 1]] : [])];
  const lejosExtremos = (p) => extremos.every((q) => Math.hypot(p[0] - q[0], p[1] - q[1]) > 7);
  // árboles: a un lado especie mixta (casi todo sombra, con guayacanes y flamboyanes), al otro sombra y guayacanes rosados
  // alternados, flamboyanes en el conector y palmas en los remates. Cada 14 m y de copa contenida: con la fila cerrada de
  // antes (11 m, 8,5 m de alto) la calle no se veía y desde lejos la alameda era solo una fila de árboles
  const xy = (l) => l.map(([x, y]) => [x, y]);
  const ladoA = xy(aLoLargo(ala, 14, 4.9, 3)).filter((p) => libre(p) && sinEsquina(p, 5) && lejosExtremos(p));
  const ladoB = xy(aLoLargo(ala, 14, -4.9, 10)).filter((p) => libre(p) && sinEsquina(p, 5) && lejosExtremos(p));
  const con = conector ? xy(aLoLargo(conector, 10, 3.6, 4)).filter((p) => libre(p) && lejosExtremos(p)) : [];
  const punta = (pts) => xy([...aLoLargo(pts, 3.4, 5.4, 0).slice(0, 2), ...aLoLargo(pts, 3.4, -5.4, 0).slice(0, 2)]);
  const remates = [...punta(ala), ...punta([...ala].reverse()), ...(conector ? punta([...conector].reverse()) : [])].filter((p) => libre(p, 1.6));
  const arbAla = [
    arboles([...ladoA, ...ladoB.filter((_, i) => i % 3 !== 1)], { alto: 7.1, copa: 0.36, semilla: 71, especie: 'mixto' }),
    arboles(ladoB.filter((_, i) => i % 3 === 1), { alto: 6.5, copa: 0.36, semilla: 73, especie: 'guayacan' }), arboles(con, { alto: 6.8, copa: 0.36, semilla: 74, especie: 'flamboyan' }), palmas(remates, { alto: 8, semilla: 75 }),
  ];
  cAla.add(...arbAla);
  // estancias cada 24 m, alternando el lado: jardinera baja con cordylines, heliconias y helechos, banca y caneca
  const jard = [], plantas = { cordyline: [], heliconia: [], helecho: [] }, tipos = Object.keys(plantas), bancasL = [], canecasL = [], sentados = [], motos = [];
  aLoLargo(ala, 24, 0, 16).forEach(([x, y, a], i) => {
    const s = i % 2 ? 1 : -1, n = [-Math.sin(a), Math.cos(a)], d = [Math.cos(a), Math.sin(a)], en = (al, off) => [x + d[0] * al + n[0] * off * s, y + d[1] * al + n[1] * off * s];
    const c = en(0, 3.0);
    if (!libre(c, 2.4) || !sinEsquina(c, 8)) return;
    const pr = rect(c[0], c[1], 3.6, 1.1, a);
    jard.push(pr);
    sembrar(pr, 7, 0.42, 100 + i).forEach((p, k) => plantas[tipos[(k + i) % 3]].push(p));
    const b = en(3.1, 3.15), cn = en(-2.6, 3.1);
    if (libre(b, 1.2)) { bancasL.push([...b, s > 0 ? a : a + Math.PI]); if (i % 2 === 0) sentados.push(Object.assign([...en(3.1 + (i % 4 ? 0.4 : -0.4), 3.25), s > 0 ? a : a + Math.PI], { h: 0.54 })); }
    if (libre(cn, 1)) canecasL.push([...cn, a]);
    // motos parqueadas contra el otro borde, perpendiculares a la calle
    if (i % 3 === 1) [-0.5, 0.5].forEach((k) => { const m = en(k, -2.7); if (libre(m, 1.4)) motos.push([...m, a + Math.PI / 2]); });
  });
  if (jard.length) {
    const borde = [], tierra = [];
    jard.forEach((pr) => {
      tierra.push(losa(pr, 0.15));
      pr.forEach((p, k) => { const q = pr[(k + 1) % 4], L = Math.hypot(q[0] - p[0], q[1] - p[1]); borde.push(new THREE.BoxGeometry(L + 0.12, 0.2, 0.12).rotateY(Math.atan2(q[1] - p[1], q[0] - p[0])).translate((p[0] + q[0]) / 2, 0.1, -(p[1] + q[1]) / 2)); });
    });
    const o1 = new THREE.Mesh(unir(borde), matT('concreto', { color: '#e3ded4' })), o2 = new THREE.Mesh(unir(tierra), matT('tierra', { color: '#6a5442', ...po(-9) }));
    o1.castShadow = true; [o1, o2].forEach((o) => { o.receiveShadow = true; cAla.add(o); });
    cAla.add(matas(plantas.cordyline, { tipo: 'cordyline', alto: 0.9, semilla: 81 }), matas(plantas.heliconia, { tipo: 'heliconia', alto: 1.25, semilla: 82 }), matas(plantas.helecho, { tipo: 'helecho', alto: 0.8, semilla: 83 }));
  }
  cAla.add(bancas(bancasL), canecas(canecasL));
  // luminarias LED cada 20 m y bolardos de luz en las esquinas
  cAla.add(postes(xy(aLoLargo(ala, 20, 3.9, 10)).filter((p) => libre(p, 1)), 4.4));
  if (pEsq.length) cAla.add(bolardos(pEsq.flat().filter((p) => libre(p, 1))));
  // la calle: dos carros a paso lento por el carril derecho, ciclistas en los dos sentidos y gente a pie (lejos de los carros)
  const enAla = (t, off, contra = false) => { const [x, y, a] = puntoEn(ala, t); return [x - Math.sin(a) * off, y + Math.cos(a) * off, contra ? a + Math.PI : a]; };
  const autos = [enAla(0.24, -1.7), enAla(0.66, -1.7)].filter((p) => sinEsquina(p, 7));
  const lejosAutos = (p) => autos.every((q) => Math.hypot(p[0] - q[0], p[1] - q[1]) > 4.5);
  const ciclas = [[0.1, -1.0], [0.35, 1.0, true], [0.5, -1.0], [0.8, 1.0, true], [0.92, -1.0]].map(([t, o, c]) => enAla(t, o, c)).filter((p) => lejosAutos(p) && sinEsquina(p, 5));
  const pas = [];
  aLoLargo(ala, 13, 0, 6).forEach(([x, y, a], i) => {
    const o = [1.8, -2.0, 0.9, -1.2][i % 4], p = [x - Math.sin(a) * o, y + Math.cos(a) * o, a + Math.PI / 2 + (i % 2 ? Math.PI : 0)];
    if (!lejosAutos(p) || !sinEsquina(p, 4.5)) return;
    pas.push(p);
    if (i % 3 === 0) pas.push([p[0] + Math.cos(a) * 0.8, p[1] + Math.sin(a) * 0.8, p[2]]);   // en pareja
  });
  cAla.add(carros(autos, { semilla: 85 }), gente(pas, { semilla: 86 }));
  if (ciclas.length) {
    const mBici = mat(new THREE.Color('#ffffff'), { roughness: 0.4, metalness: 0.5 }), colores = ['#c8372d', '#2e5fa8', '#1f2329', '#3a7d44', '#e07a3a'].map((c) => new THREE.Color(c));
    cAla.add(instanciar(bici(), mBici, ciclas, { colores }));
    ciclas.forEach(([x, y, a]) => sentados.push(Object.assign([x, y, a + Math.PI / 2], { h: 0.55 })));   // los ciclistas, como sentados
  }
  cAla.add(gente(sentados, { sentado: true, semilla: 84 }));
  if (motos.length) {
    const G2 = moto(), cuerpo = mat(new THREE.Color('#ffffff'), { roughness: 0.35, metalness: 0.4 }), colores = ['#c8372d', '#1f2329', '#2e5fa8', '#e9ebed'].map((c) => new THREE.Color(c));
    cAla.add(instanciar(G2.cuerpo, cuerpo, motos, { colores }), instanciar(G2.ruedas, mat(new THREE.Color('#1c1e20'), { roughness: 0.7 }), motos));
  }
  // señal vertical de calle compartida al empezar cada tramo, a la derecha y de frente a quien entra
  const senales = [];
  const senal = (p, a, al, entra) => { const q = [p[0] + Math.cos(a) * al - Math.sin(a) * -4.4 * entra, p[1] + Math.sin(a) * al + Math.cos(a) * -4.4 * entra]; if (libre(q, 0.8)) senales.push([...q, entra > 0 ? a - Math.PI / 2 : a + Math.PI / 2]); };
  const ang = (pts, i) => Math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0]);
  senal(ala[0], ang(ala, 0), 2.5, 1);
  senal(ala[ala.length - 1], ang(ala, ala.length - 2), -2.5, -1);
  if (conector?.length > 1) senal(conector[0], ang(conector, 0), 2.5, 1);
  esq.forEach(({ p, a1 }) => senal(p, a1, 6, 1));
  if (senales.length) {
    const poste = unir([new THREE.CylinderGeometry(0.04, 0.045, 2.75, 8).translate(0, 1.375, 0), new THREE.BoxGeometry(0.64, 0.79, 0.025).translate(0, 2.3, 0.07)]);
    cAla.add(instanciar(poste, mat(new THREE.Color('#9aa1a7'), { roughness: 0.4, metalness: 0.6 }), senales), instanciar(new THREE.PlaneGeometry(0.6, 0.75).translate(0, 2.3, 0.095), new THREE.MeshStandardMaterial({ map: texturaSenal(), roughness: 0.55 }), senales, { sombra: false }));
  }
  const am = ala[Math.floor(ala.length * 0.4)];
  esc.etiqueta('<b>Alameda de la ciudadela</b><small>483 m por calles que ya existen</small>', { pos: [am[0], am[1] + 8, 14], padre: cAla, color: `var(${color})` });

  // --- canchas cubiertas y skatepark en la explanada al sur del CIC
  const cInst = esc.capa('urb.instalaciones'), inst = instalacionesCIC(explanada);
  cInst.add(inst);
  esc.etiqueta('<b>Canchas cubiertas y skatepark</b><small>explanada al sur del CIC · a un puente del estadio</small>', { pos: [...inst.userData.centro, 16], padre: cInst, color: `var(${color})`, ancla: [0, 1], punto: [...inst.userData.centro, 2] });

  // --- Mirador Puerta del Magdalena: se arma aparte porque las letras usan una fuente que se descarga, y el capítulo no la
  // espera (el paso del mirador vuelve a encuadrar y anima cuando llega)
  const cMir = esc.capa('urb.mirador');
  const tb = datos.territorio?.puente?.tablero;
  if (tb?.length > 1) esc.etiqueta('<b>Puente Guillermo Gaviria Correa</b><small>a Barrancabermeja</small>', { pos: [(tb[0][0] + tb[1][0]) / 2, (tb[0][1] + tb[1][1]) / 2, 30], padre: cMir, cls: 'lbl-p mini' });
  let mir = null;
  const listoMir = miradorMagdalena(cfgMir).then((m) => {
    mir = m; cMir.add(m);
    const U = m.userData;
    // el mirador va primero: si en el celular no caben todos, es el último que se oculta
    esc.etiqueta('<b>Mirador elevado</b><small>10 × 10 m sobre pilotes</small>', { pos: [...U.mirador, 12], padre: cMir, color: '#a8703f', cls: 'lbl-p mini' });
    esc.etiqueta('<b>Zona A · protección hidráulica</b><small>283 m de orilla: enrocado y vegetación de ribera</small>', { pos: [...U.zonaA, 8], padre: cMir, color: 'var(--m-aguas)', cls: 'lbl-p mini' });
    esc.etiqueta('<b>Zona B · plaza mirador</b><small>letras YONDÓ · jardineras · parqueadero</small>', { pos: [...U.zonaB, 12], padre: cMir, color: `var(${color})`, cls: 'lbl-p mini' });
    esc.etiqueta('<b>Muelle flotante</b><small>lanchas Barrancabermeja–Casabe</small>', { pos: [...U.muelle, 6], padre: cMir, color: '#a8703f', cls: 'lbl-p mini' });
    esc.sincronizarEtiquetas(); esc.st.updateShadows(); esc.st.invalidate();
    return m;
  }).catch((e) => { console.warn('mirador', e); return null; });
  esc.sincronizarEtiquetas();

  // --- vistas y animaciones de cada paso
  const capasTodo = ['urb.ciudadela', 'urb.softbol', 'urb.cano', 'urb.alameda', 'urb.instalaciones'];
  const piezas = capasTodo.slice(1);   // en las vistas de conjunto, solo los rótulos de las cuatro piezas
  const inv = () => esc.st.invalidate();
  const vistaCiud = () => esc.encuadrar([...ciud, ...explanada], { rumbo: 200, elev: 48, margen: 0.8 });
  // la vista de conjunto, con el estadio a la vista: un poco más cerca y los rótulos de las piezas apartados de la cancha
  // (antes los cuatro caían encima de ella y la tapaban)
  const vistaConjunto = () => esc.encuadrar([...ciud, ...explanada], { rumbo: 200, elev: 46, margen: 0.9, obra: soft.userData.contorno, apartar: true, sinCruces: true });
  const vistaSoft = () => esc.encuadrar(soft.userData.contorno, { rumbo: 200, elev: 34, margen: 0.9, alto: 10 });
  const vistaCano = () => esc.encuadrar(caja(pl.userData.eje, 24), { rumbo: 118, elev: 40, margen: 0.94 });
  const vistaAla = () => esc.encuadrar(caja([...ala, ...(conector || [])], 30), { rumbo: 196, elev: 46, margen: 0.94 });
  // la explanada con el puente PP2, que la une con el estadio (con toda la cancha, en el celular la obra quedaba diminuta)
  const pp2 = puentes.find((s) => s.id === 'pp2');
  const vistaInst = () => esc.encuadrar([...explanada, ...(pp2 ? [[pp2.x, pp2.y]] : soft.userData.contorno)], { rumbo: 208, elev: 38, margen: 0.94, alto: 10 });
  // la plaza, el deck, el mirador y el muelle, más toda la zona A (la protección de la orilla que abre el paso); en el
  // celular, sin los 280 m de orilla, que dejarían el mirador diminuto (solo el punto del rótulo de la zona A)
  const encuadrarMir = (vuelo = true) => esc.encuadrar(mir ? [...mir.userData.contorno, ...(innerWidth > 640 ? mir.userData.contornoA : [mir.userData.zonaA])] : caja([cfgMir.origen], 150), { rumbo: 221, elev: 30, margen: 0.92, alto: 12, vuelo });
  // cuando el mirador termina de cargar se vuelve a encuadrar; con una narración en pantalla (esc.guiado) o un paseo de
  // la cámara solo queda anotado: la cámara la lleva el plan
  const vistaMir = () => { encuadrarMir(); if (!mir) listoMir.then((m) => { if (m && cMir.visible) encuadrarMir(!esc.guiado && !esc.st.paseo); }); };
  const animSoft = () => {
    const P = soft.userData.partes;
    crecer(P.obras, { duracion: 1.1, retraso: 0.6, onUpdate: inv, alFinal: () => esc.st.updateShadows() });
    crecer(P.cubierta, { duracion: 1.0, retraso: 1.2, onUpdate: inv });
    crecer(P.luces, { duracion: 1.2, retraso: 1.4, onUpdate: inv });
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.6, retraso: 1 + i * 0.2, onUpdate: inv }));
  };
  const animCano = () => {
    const P = pl.userData.partes;
    P.cauce.children.forEach((m) => m.isMesh && revelar(m, { duracion: 1.8, retraso: 0.5, onUpdate: inv }));
    P.sendas.children.forEach((m) => m.isMesh && revelar(m, { duracion: 1.8, retraso: 0.9, onUpdate: inv }));
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.8, retraso: 1.2 + i * 0.15, onUpdate: inv }));
    crecer(P.puentes, { duracion: 0.9, retraso: 2, onUpdate: inv });
  };
  const animAla = () => { arbAla.forEach((g, i) => brotar(g, { duracion: 2, retraso: 0.7 + i * 0.12, onUpdate: inv })); [pisoAla, lineaAla].forEach((m) => revelar(m, { duracion: 1.6, retraso: 0.5, onUpdate: inv })); };
  const animInst = () => {
    const P = inst.userData.partes;
    crecer(P.obras, { duracion: 1, retraso: 0.6, onUpdate: inv }); crecer(P.cubierta, { duracion: 1, retraso: 1.1, onUpdate: inv, alFinal: () => esc.st.updateShadows() });
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.6, retraso: 1.2 + i * 0.2, onUpdate: inv }));
  };
  const animMir = () => {
    if (!mir) { listoMir.then((m) => { if (m && cMir.visible) animMir(); }); return; }
    const P = mir.userData.partes;
    crecer(P.zonaA, { duracion: 1, retraso: 0.8, onUpdate: inv });
    crecer(P.letras, { duracion: 1.1, retraso: 1.3, onUpdate: inv });
    crecer(P.deck, { duracion: 1.1, retraso: 1.6, onUpdate: inv });
    crecer(P.muelle, { duracion: 0.9, retraso: 1.9, onUpdate: inv });
    P.verde.children.forEach((g, i) => brotar(g, { duracion: 1.4, retraso: 1.2 + i * 0.2, onUpdate: inv }));
  };
  // el partido (simulación de la maqueta): se mueve en cada cuadro mientras está encendido y la cancha está a la vista
  const partido = soft.userData.partido;
  esc.st.onFrame((dt) => {
    let vis = true; for (let p = soft; p; p = p.parent) if (!p.visible) { vis = false; break; }
    return vis || !partido.activo() ? partido.paso(dt) : false;
  });
  const hoy = (v) => (G.zonas || []).forEach((z) => esc.verHoy(z, v));
  return {
    // las simulaciones de la maqueta que vive en este capítulo (simulacion.js): el partido en la Cancha de Sóftbol Casabe
    simulaciones: {
      partido: { pieza: cSoft, jugar: (v) => partido.jugar(v), activo: () => partido.activo() },
    },
    completo: [...capasTodo, 'urb.mirador'],
    alCompleto: () => hoy(false),
    salir: () => { hoy(true); partido.jugar(false); },   // fuera del capítulo la cancha no está a la vista: el partido se detiene
    // cuando el asistente muestra, oculta o aísla piezas (visual.js): si la cancha no está a la vista, su lote no queda
    // vacío (vuelven las casas de hoy), y al revés
    alAjustar: () => hoy(!cSoft.visible),
    pasos: {
      portadilla: { capas: ['urb.ciudadela', 'urb.hoy'], antes: () => hoy(true), vista: vistaCiud },
      componentes: { capas: capasTodo, antes: () => hoy(false), vista: vistaConjunto, animar: () => { animSoft(); animCano(); animAla(); animInst(); }, etiquetas: piezas },
      softbol: { capas: capasTodo, antes: () => hoy(false), vista: vistaSoft, animar: animSoft, etiquetas: ['urb.softbol'] },
      cano: { capas: [...capasTodo, 'urb.puentes'], antes: () => hoy(false), vista: vistaCano, animar: animCano, etiquetas: ['urb.cano', 'urb.puentes'] },
      alameda: { capas: capasTodo, antes: () => hoy(false), vista: vistaAla, animar: animAla, etiquetas: ['urb.alameda'] },
      instalaciones: { capas: capasTodo, antes: () => hoy(false), vista: vistaInst, animar: animInst, etiquetas: ['urb.instalaciones'] },
      mirador: { capas: ['urb.mirador'], vista: vistaMir, animar: animMir },
      '*': { capas: [...capasTodo], antes: () => hoy(false), vista: vistaConjunto, etiquetas: piezas },
    },
  };
}
