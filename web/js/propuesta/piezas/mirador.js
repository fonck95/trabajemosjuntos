// Mirador Puerta del Magdalena, junto al estribo de Yondó del puente Guillermo Gaviria Correa, armado sobre el prediseño
// del levantamiento (orilla leída en la imagen de sep-2025). Zona A: franja de protección hidráulica de 283 m de orilla y
// 36 m de ancho (30 m de ronda y 6 m de pie de enrocado dentro del agua), con enrocado en el talud y vegetación de ribera,
// sin pavimento. Zona B: plaza de 0,46 ha detrás de la ronda, aguas abajo del puente, con las letras «YONDÓ» de frente a
// la plaza, jardineras con árboles, bancas, luminarias y parqueadero. Un sendero curvo en deck cruza la ronda y corre por
// el borde del agua hasta un mirador de 10 × 10 m sobre pilotes. La propuesta no lleva muelle: el embarque de lanchas no
// se formaliza aquí.
//
// Acabados: plaza de adoquín con franja perimetral y bordillo, prado, jardineras de concreto con guayacanes y plantas
// tropicales, bancas, canecas, bolardos y luminarias con su charco de luz, caseta de información con el letrero «Puerta
// del Magdalena», vendedores con carrito y sombrilla, parqueadero con carros y motos, gente. Deck de tablas sobre
// largueros y pilotes, con baranda de parales de acero, pasamanos de madera y cinta de luz; mirador con lona tensada. En
// el río, una chalupa de toldo amarillo cruza hacia Barrancabermeja con su estela (paisaje, no obra). Ronda con pasto,
// geotextil, enrocado con helechos entre las piedras y señal de ronda hídrica; frente al deck y el mirador la ribera lleva
// matas y palmas bajas en lugar de árboles, para que se lean desde la cámara del paso (que mira hacia el río).
// Marco local: u a lo largo de la orilla aguas abajo y v hacia el río, con origen en el cruce del eje del puente con la
// orilla; las piezas de geo3d reciben (u, −v).
import { THREE, mat } from '../../core.js';
import { losa, cinta, enrocado, arboles, palmas, matas, postes, bancas, bolardos, canecas, gente, carros, letras, aLoLargo, suave, unir, dentro, sembrar, distLinea, azar, luzComun } from '../geo3d.js';
import { matT } from '../texturas.js';

// prediseño de respaldo en el marco local (u, v); geo.json lo trae en metros del modelo y se convierte al marco
const DISENO = {
  zonaA: [[-80, -30], [-50, -28], [-25, -25], [0, -22], [25, -30], [50, -33], [75, -32.1], [100, -34.1], [125, -38], [150, -43], [175, -44], [200, -45], [200, -9], [175, -8], [150, -7], [125, -2], [100, 2], [75, 4], [50, 2.9], [25, 6], [0, 14], [-24.9, 11], [-50, 8], [-80, 6]],
  plaza: [[32, -32], [60, -33], [90, -34.1], [118, -37], [117.9, -86], [89.9, -87], [60, -88], [32, -87.1]],
  mirador: [[52, -5], [62, -5], [62, 5], [52, 5]],
  letras: [80, -38.1],
  deck: [[112, -37], [117, -30], [119, -22], [116, -14], [109, -8], [100, -4], [90, -2], [80, -1.1], [71, -0.5], [63, 0]],
  acceso: [[-2, -100], [20, -96], [32, -92]],
  orilla: [[-80, 0], [-50, 2], [-25, 5], [0, 8], [25, 0], [49.9, -3], [75, -2], [100, -4], [125, -8], [150, -13], [175, -14], [200, -15.1]],
};
const L = ([u, v]) => [u, -v];   // (u, v) del marco → (x, y) que esperan las piezas de geo3d

// esquinas redondeadas: cada vértice se reemplaza por un arco de radio r entre sus dos lados
function redondear(poly, r = 6, n = 6) {
  const out = [];
  poly.forEach((p, i) => {
    const a = poly[(i - 1 + poly.length) % poly.length], b = poly[(i + 1) % poly.length];
    const la = Math.hypot(a[0] - p[0], a[1] - p[1]), lb = Math.hypot(b[0] - p[0], b[1] - p[1]), k = Math.min(r, la / 2.2, lb / 2.2);
    const p0 = [p[0] + ((a[0] - p[0]) / la) * k, p[1] + ((a[1] - p[1]) / la) * k], p1 = [p[0] + ((b[0] - p[0]) / lb) * k, p[1] + ((b[1] - p[1]) / lb) * k];
    for (let j = 0; j <= n; j++) { const t = j / n; out.push([(1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p[0] + t * t * p1[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p[1] + t * t * p1[1]]); }
  });
  return out;
}
// anillo corrido off metros hacia adentro (el polígono puede venir en cualquier sentido)
function adentro(poly, off) {
  let ar = 0; poly.forEach((p, i) => { const b = poly[(i + 1) % poly.length]; ar += p[0] * b[1] - b[0] * p[1]; });
  const s = ar > 0 ? 1 : -1, n = poly.length;
  return poly.map((p, i) => { const a = poly[(i - 1 + n) % n], b = poly[(i + 1) % n], l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; return [p[0] - ((b[1] - a[1]) / l) * off * s, p[1] + ((b[0] - a[0]) / l) * off * s]; });
}
// franja entre dos anillos (o polilíneas) A y B a las alturas hA y hB, en coordenadas del marco (u, v)
function tira(A, B, hA, hB, cerrado = true) {
  const pos = [], idx = [], n = A.length;
  A.forEach((a, i) => pos.push(a[0], hA, a[1], B[i][0], hB, B[i][1]));
  for (let i = 0; i < (cerrado ? n : n - 1); i++) { const j = (i + 1) % n; idx.push(2 * i, 2 * i + 1, 2 * j, 2 * i + 1, 2 * j + 1, 2 * j); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
  return g;
}
// bordillo o muro bajo sobre un anillo: cara de arriba y los dos costados (materiales de dos caras)
function muroAnillo(poly, a0, a1, h0, h1) { const A = adentro(poly, a0), B = adentro(poly, a1); return unir([tira(A, B, h1, h1), tira(A, A, h0, h1), tira(B, B, h0, h1)]); }
// los charcos de luz de postes y bolardos van a 0,16 m: sobre la plaza (0,18) se suben
const alzarCharcos = (g, dy) => { g.traverse((o) => { if (o.name === 'charcos') o.position.y += dy; }); return g; };
// matas por tipo, un grupo por tipo (lista): brotar escalona las instancias por el conteo de la primera malla del grupo, y
// con tipos de conteos distintos en un mismo grupo los de más instancias quedaban encogidos al final. Solo las heliconias
// (1,5 m) proyectan sombra: cientos de matas bajas en el mapa de sombra casi no se notan
function matasPorTipo(porTipo, altos, semilla, h = 0) {
  return Object.entries(porTipo).filter(([, l]) => l.length).map(([t, l], i) => {
    const m = matas(l, { tipo: t, alto: altos[t], semilla: semilla + i });
    if (t !== 'heliconia') m.traverse((o) => { o.castShadow = false; });
    m.position.y = h;
    return m;
  });
}
// matas en macizos (3 a 7 alrededor de cada centro, casi todas de un mismo tipo), como se siembra una ribera, no regadas
function racimos(poly, n, sep, semilla, vale, tipos) {
  const r = azar(semilla), por = Object.fromEntries(tipos.map((t) => [t, []]));
  sembrar(poly, n, sep, semilla).forEach(([cu, cv]) => {
    const t = tipos[Math.floor(r() * tipos.length)], k = 3 + Math.floor(r() * 5);
    for (let i = 0; i < k; i++) { const a = r() * 6.28, d = Math.sqrt(r()) * 1.5, p = [cu + Math.cos(a) * d, cv + Math.sin(a) * d]; if (vale(p)) por[r() < 0.8 ? t : tipos[Math.floor(r() * tipos.length)]].push(L(p)); }
  });
  return por;
}
// estela de una lancha en marcha (marco del casco, proa en +Lc/2, popa en −Lc/2): los dos brazos de la ola de Kelvin
// (~19,5°) nacen junto a la proa y se abren hacia atrás como líneas de espuma delgadas y cortadas, y detrás de la popa la
// espuma revuelta del motor. Alfa por vértice que se desvanece hacia atrás (anchos y blancos, los brazos parecían haces de luz)
function estelaGeo(Lc, B) {
  const pos = [], col = [], idx = [];
  const tira = (pts) => {
    const base = pos.length / 3;
    pts.forEach(([x, z, w, a], i) => {
      const [x2, z2] = pts[Math.min(i + 1, pts.length - 1)], [x0, z0] = pts[Math.max(i - 1, 0)], l = Math.hypot(x2 - x0, z2 - z0) || 1, nx = -(z2 - z0) / l, nz = (x2 - x0) / l;
      pos.push(x + (nx * w) / 2, 0.03, z + (nz * w) / 2, x - (nx * w) / 2, 0.03, z - (nz * w) / 2); col.push(1, 1, 1, a, 1, 1, 1, a);
      if (i) { const k = base + i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); }
    });
  };
  const xb = Lc / 2 - Lc * 0.22, K = 36, ang = 0.34;
  // brazos: de la amura hacia atrás, con tramos de espuma y de agua lisa alternados (cada ~0,9 m)
  [-1, 1].forEach((sg) => tira(Array.from({ length: K + 1 }, (_, i) => { const t = i / K, d = t * 24; return [xb - d * Math.cos(ang), sg * (B * 0.42 + d * Math.sin(ang)), 0.16 + 0.7 * t, 0.42 * (1 - t) ** 1.4 * (i % 3 === 2 ? 0.15 : 1)]; })));
  // espuma del motor: una franja que se ensancha poco y se deshace en parches
  tira(Array.from({ length: 19 }, (_, i) => { const t = i / 18; return [-Lc / 2 - 0.3 - t * 13, 0, 0.9 + 1.1 * t, 0.4 * (1 - t) ** 1.6 * (i % 3 === 1 ? 0.45 : 1)]; }));
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col, 4)); g.setIndex(idx); g.computeVertexNormals();
  return g;
}

// baranda que sigue la altura de cada punto [u, v, h] del piso: parales de acero cada paso metros, dos pasamanos
// intermedios de acero, pasamanos de madera arriba y una cinta LED debajo de él. Va a un lote { metal, madera, led }
function barandal(pts, lote, { alto = 1.05, paso = 1.6 } = {}) {
  let acc = paso;
  for (let i = 1; i < pts.length; i++) {
    const [a, b] = [pts[i - 1], pts[i]], du = b[0] - a[0], dv = b[1] - a[1], Lh = Math.hypot(du, dv);
    if (Lh < 1e-3) continue;
    const dh = b[2] - a[2], L3 = Math.hypot(Lh, dh), yaw = Math.atan2(-dv, du), pitch = Math.atan2(dh, Lh), mu = (a[0] + b[0]) / 2, mv = (a[1] + b[1]) / 2, mh = (a[2] + b[2]) / 2;
    const seg = (h, d, dy) => new THREE.BoxGeometry(L3 + 0.04, h, d).rotateZ(pitch).rotateY(yaw).translate(mu, mh + dy, mv);
    lote.madera.push(seg(0.05, 0.12, alto)); lote.led.push(seg(0.015, 0.05, alto - 0.035)); [0.36, 0.7].forEach((dy) => lote.metal.push(seg(0.022, 0.022, dy)));
    for (let t = 0; t < Lh; t += 0.25) {
      if ((acc += 0.25) < paso && !(i === 1 && t === 0)) continue;
      acc = 0; const k = t / Lh;
      lote.metal.push(new THREE.BoxGeometry(0.06, alto, 0.06).translate(a[0] + du * k, a[2] + dh * k + alto / 2, a[1] + dv * k));
    }
  }
  const z = pts[pts.length - 1];
  lote.metal.push(new THREE.BoxGeometry(0.06, alto, 0.06).translate(z[0], z[2] + alto / 2, z[1]));
}

// --- letreros pintados en lienzo
function lienzo(w, h, pintar) { const c = document.createElement('canvas'); c.width = w; c.height = h; pintar(c.getContext('2d'), w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; }
const texLetrero = () => lienzo(1024, 220, (x, w, h) => {
  const g = x.createLinearGradient(0, 0, 0, h); g.addColorStop(0, '#1a4a72'); g.addColorStop(1, '#0f2f4c'); x.fillStyle = g; x.fillRect(0, 0, w, h);
  x.strokeStyle = '#f5c84a'; x.lineWidth = 7; x.beginPath(); for (let i = 0; i <= 64; i++) x.lineTo((i / 64) * w, 186 + Math.sin(i * 0.55) * 7); x.stroke();
  x.fillStyle = '#ffffff'; x.textAlign = 'center'; x.font = 'bold 92px Anton, Impact, "Arial Black", sans-serif'; x.fillText('PUERTA DEL MAGDALENA', w / 2, 110);
  x.fillStyle = '#f5c84a'; x.font = '600 34px "Public Sans", Arial, sans-serif'; x.fillText('Información turística · mirador del río', w / 2, 160);
});
const texRonda = () => lienzo(512, 320, (x, w, h) => {
  x.fillStyle = '#1f6b4a'; x.fillRect(0, 0, w, h); x.strokeStyle = '#ffffff'; x.lineWidth = 10; x.strokeRect(14, 14, w - 28, h - 28);
  x.fillStyle = '#ffffff'; x.textAlign = 'center'; x.font = 'bold 64px "Public Sans", Arial, sans-serif'; x.fillText('RONDA HÍDRICA', w / 2, 112);
  x.font = '30px "Public Sans", Arial, sans-serif'; x.fillText('Río Grande de la Magdalena', w / 2, 170); x.fillText('Zona de protección · 30 m', w / 2, 214);
  x.strokeStyle = '#9fd3ea'; x.lineWidth = 6; [0, 1].forEach((k) => { x.beginPath(); for (let i = 0; i <= 20; i++) x.lineTo(150 + i * 10.6, 256 + k * 16 + Math.sin(i * 0.9) * 6); x.stroke(); });
});

// --- chalupa: casco afilado (popa plana, proa que se levanta), franja de color, fondo rojo bajo el agua, piso, bancas,
// toldo azul en arco sobre parales y motor fuera de borda. Frente hacia +x; la línea de agua en y = 0. Devuelve las
// geometrías por material y los puestos de los pasajeros ([x, z])
const ROJO = [0.62, 0.2, 0.15], BLANCO = [0.95, 0.95, 0.93];
function chalupa(Lc, B, { toldo = true, franja = '#1f6fd1' } = {}) {
  const N = 16, F = new THREE.Color(franja), FR = [F.r, F.g, F.b], est = [];
  const medio = (t) => (t < 0.35 ? 0.84 + 0.16 * (t / 0.35) : t < 0.62 ? 1 : Math.pow(Math.cos(((t - 0.62) / 0.38) * (Math.PI / 2)), 0.75));
  for (let i = 0; i <= N; i++) { const t = i / N; est.push([(t - 0.5) * Lc, (medio(t) * B) / 2, t]); }
  const lazo = [...est.map(([x, w, t]) => [x, -w, t]), ...est.slice(0, -1).reverse().map(([x, w, t]) => [x, w, t])];
  const anillos = [[-0.3, 0.3, ROJO], [-0.04, 0.8, ROJO], [0, 0.84, BLANCO], [0.46, 0.98, BLANCO], [0.49, 0.99, FR], [0.74, 1, FR]];
  const pos = [], col = [], idx = [], M = lazo.length;
  anillos.forEach(([y, s, c]) => lazo.forEach(([x, z, t]) => {
    const k = (y + 0.3) / 1.04, proa = Math.max(0, (t - 0.62) / 0.38) ** 2, fondo = Math.max(0, (t - 0.7) / 0.3) ** 2;
    pos.push(x, y + 0.3 * proa * k + 0.28 * fondo * (1 - k), z * s); col.push(...c);
  }));
  for (let k = 0; k < anillos.length - 1; k++) for (let j = 0; j < M; j++) { const a = k * M + j, b = k * M + ((j + 1) % M), c = a + M, d = b + M; idx.push(a, b, c, b, d, c); }
  const casco = new THREE.BufferGeometry(); casco.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); casco.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); casco.setIndex(idx); casco.computeVertexNormals();
  const ancho = (x) => (medio(THREE.MathUtils.clamp(x / Lc + 0.5, 0, 1)) * B) / 2;
  const piso = new THREE.ShapeGeometry(new THREE.Shape(lazo.map(([x, z]) => new THREE.Vector2(x * 0.95, -z * 0.88)))).rotateX(-Math.PI / 2).translate(0, 0.18, 0);
  const madera = [], metal = [], lona = [], motor = [], puestos = [];
  const nb = Math.max(2, Math.round(Lc / 2.1)), xs = Array.from({ length: nb }, (_, i) => -Lc * 0.32 + (i * Lc * 0.6) / (nb - 1));
  xs.forEach((x) => { const w = ancho(x) * 1.9; madera.push(new THREE.BoxGeometry(0.32, 0.05, w).translate(x, 0.45, 0)); [-0.45, 0.45].forEach((z) => puestos.push([x, z * (B / 2.4)])); });
  if (toldo) {
    const x0 = -Lc * 0.36, x1 = Lc * 0.24, R = (B + 0.1) / 1.1, yTop = 2.05;
    lona.push(new THREE.CylinderGeometry(R, R, x1 - x0, 14, 1, true, Math.PI / 2 - 0.58, 1.16).rotateZ(Math.PI / 2).translate((x0 + x1) / 2, yTop - R, 0));
    [x0 + 0.1, (x0 + x1) / 2, x1 - 0.1].forEach((x) => [-1, 1].forEach((s) => metal.push(new THREE.CylinderGeometry(0.03, 0.03, yTop - 0.17 * R - 0.72, 6).translate(x, (yTop - 0.17 * R + 0.72) / 2, s * ancho(x) * 0.9))));
  }
  const xp = -Lc / 2 - 0.24;
  motor.push(new THREE.BoxGeometry(0.5, 0.6, 0.4).translate(xp - 0.05, 1.05, 0), new THREE.BoxGeometry(0.16, 1.05, 0.12).translate(xp, 0.28, 0), new THREE.BoxGeometry(0.3, 0.1, 0.3).translate(xp + 0.12, 0.76, 0), new THREE.BoxGeometry(0.42, 0.06, 0.14).translate(xp - 0.08, -0.16, 0));
  return { casco, piso, madera, metal, lona, motor, puestos, popa: -Lc / 2 + 0.7 };
}
// motos estacionadas (1,9 m, frente hacia +x): carrocería teñida por instancia y partes oscuras
const geoMoto = (() => {
  const carroceria = unir([new THREE.BoxGeometry(0.9, 0.28, 0.24).translate(0.0, 0.6, 0), new THREE.BoxGeometry(0.42, 0.22, 0.3).translate(0.2, 0.82, 0), new THREE.BoxGeometry(0.62, 0.09, 0.28).translate(-0.24, 0.86, 0), new THREE.BoxGeometry(0.5, 0.06, 0.16).rotateZ(0.25).translate(-0.62, 0.66, 0), new THREE.BoxGeometry(0.16, 0.16, 0.2).translate(0.62, 0.96, 0)]);
  const oscuro = unir([new THREE.TorusGeometry(0.29, 0.075, 6, 16).translate(-0.66, 0.31, 0), new THREE.TorusGeometry(0.29, 0.075, 6, 16).translate(0.68, 0.31, 0), new THREE.CylinderGeometry(0.03, 0.03, 0.78, 6).rotateZ(-0.35).translate(0.6, 0.66, 0), new THREE.CylinderGeometry(0.02, 0.02, 0.7, 6).rotateX(Math.PI / 2).translate(0.5, 1.02, 0), new THREE.BoxGeometry(0.5, 0.18, 0.2).translate(-0.05, 0.4, 0)]);
  return { carroceria, oscuro };
})();
// carrito de vendedor con sombrilla (frente hacia +x)
const geoCarrito = {
  caja: new THREE.BoxGeometry(1.3, 0.75, 0.8).translate(0, 0.85, 0),
  metal: unir([new THREE.CylinderGeometry(0.025, 0.025, 1.25, 6).translate(0.1, 1.85, 0), ...[-0.45, 0.45].map((z) => new THREE.CylinderGeometry(0.24, 0.24, 0.05, 12).rotateX(Math.PI / 2).translate(-0.35, 0.24, z * 1.02)), new THREE.CylinderGeometry(0.02, 0.02, 0.9, 6).rotateX(Math.PI / 2).translate(-0.85, 1.05, 0), new THREE.BoxGeometry(0.06, 0.5, 0.06).translate(0.55, 0.25, 0)]),
  sombrilla: new THREE.ConeGeometry(1.15, 0.38, 10, 1, true).translate(0.1, 2.48, 0),
};
const SOMBRILLAS = ['#d63b2b', '#f0c419', '#2e7fd1', '#2fa75a'].map((c) => new THREE.Color(c)), MOTOS = ['#c8372d', '#1f2329', '#2e5fa8', '#e9ebed', '#1f2329', '#9b2b26'].map((c) => new THREE.Color(c));

// { origen: [x, y] (eje del puente en la orilla), angulo: grados desde el oriente (antihorario) de la orilla aguas abajo,
//   diseno: { zonaA, plaza, mirador, letras, deck, acceso, orilla } en metros del modelo (opcional) }
export async function miradorMagdalena({ origen, angulo, diseno = null }) {
  const raiz = new THREE.Group(), th = THREE.MathUtils.degToRad(angulo), c = Math.cos(th), s = Math.sin(th);
  raiz.position.set(origen[0], 0, -origen[1]); raiz.rotation.y = th;
  const aLocal = ([x, y]) => [(x - origen[0]) * c + (y - origen[1]) * s, (x - origen[0]) * s - (y - origen[1]) * c];
  const D = { ...DISENO };
  if (diseno) Object.entries(diseno).forEach(([k, v]) => { if (v?.length) D[k] = typeof v[0] === 'number' ? aLocal(v) : v.map(aLocal); });
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const zonaA = capa('zonaA'), plaza = capa('plaza'), deck = capa('deck'), verde = capa('verde'), letrasG = capa('letras');
  const po = (k) => ({ polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const C = {
    adoquin: matT('adoquin', { color: '#efe5d2' }), adoquinB: matT('adoquin', { color: '#bfb19a', side: THREE.DoubleSide, ...po(1) }),
    borde: matT('concreto', { color: '#dcd7cc', side: THREE.DoubleSide }), concreto: matT('concreto'),
    prado: matT('cesped', po(1)), tierra: matT('tierra', { color: '#6f5a45', ...po(1) }),
    madera: matT('madera'), tabla: matT('madera', { color: '#d29d6c' }), pilote: matT('madera', { color: '#6a4e36' }),
    metal: mat(new THREE.Color('#2b3035'), { roughness: 0.45, metalness: 0.6 }), roca: matT('roca', { color: '#a39d92' }),
    zonaA: new THREE.MeshBasicMaterial({ color: new THREE.Color('#2a78d6'), transparent: true, opacity: 0.13, depthWrite: false, side: THREE.DoubleSide, ...po(6) }),
    ribera: matT('cesped', { color: '#cfd9ae', ...po(4) }), geotextil: matT('tierra', { color: '#7b7466', ...po(5) }),
    asfalto: matT('asfalto', po(1)), cal: new THREE.MeshBasicMaterial({ color: 0xf2f2f2, ...po(3) }), amarilla: new THREE.MeshBasicMaterial({ color: 0xf2c230, ...po(3) }),
    lona: matT('membrana', { color: '#f6f2e8' }), toldo: matT('membrana', { color: '#2f62b0' }),
    casco: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.42, side: THREE.DoubleSide }), interior: mat(new THREE.Color('#7f8c94'), { roughness: 0.8 }),
    motor: mat(new THREE.Color('#24272a'), { roughness: 0.35, metalness: 0.35 }), estela: new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, depthWrite: false, roughness: 0.9, side: THREE.DoubleSide, ...po(4) }),   // con luz: al atardecer la espuma se apaga con el agua
    muro: matT('estuco', { color: '#f4efe4' }), ladrillo: matT('ladrillo'), vidrio: mat(new THREE.Color('#3e5361'), { roughness: 0.08, metalness: 0.7 }), techo: matT('zinc', { color: '#5d646a' }),
    letrero: new THREE.MeshStandardMaterial({ map: texLetrero(), roughness: 0.55, emissive: 0xffffff, emissiveIntensity: 0.08 }),
    ronda: new THREE.MeshStandardMaterial({ map: texRonda(), roughness: 0.6 }),
    carrito: mat(new THREE.Color('#f4f1ea'), { roughness: 0.5 }), sombrilla: new THREE.MeshStandardMaterial({ roughness: 0.7, side: THREE.DoubleSide }),
    moto: new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.45 }), llanta: mat(new THREE.Color('#17191b'), { roughness: 0.8 }),
  };
  C.letrero.emissiveMap = C.letrero.map;
  const sombra = (o) => { o.traverse((k) => { if (k.isMesh) { k.castShadow = true; k.receiveShadow = true; } }); return o; };
  const malla = (geo, m, proyecta = true) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; o.castShadow = proyecta; return o; };
  const volcar = (padre, lote, mats) => Object.entries(lote).forEach(([k, gs]) => { if (gs.length) padre.add(malla(unir(gs), mats[k], k !== 'led')); });
  const orilla = D.orilla, vOrilla = (u) => { for (let i = 1; i < orilla.length; i++) if (u <= orilla[i][0]) { const [a, b] = [orilla[i - 1], orilla[i]], t = (u - a[0]) / (b[0] - a[0] || 1); return a[1] + t * (b[1] - a[1]); } return orilla[orilla.length - 1][1]; };
  const r = azar(23);
  // gente de cada parte en su grupo (el deck crece al animarse: la gente crece con él, no queda en el aire)
  const quien = { plaza: [], sentados: [], deck: [] };

  // --- zona A: franja de la ronda (tenue), talud con pasto de ribera, geotextil asomando sobre el enrocado del pie contra la
  // socavación, helechos entre las piedras y la señal de ronda hídrica
  zonaA.add(new THREE.Mesh(losa(D.zonaA.map(L), 0.3), C.zonaA));
  const banda = (v0, v1) => [...orilla.map(([u, v]) => [u, v + v0]), ...[...orilla].reverse().map(([u, v]) => [u, v + v1])];
  const bandaU = (u0, u1, v0, v1) => { const us = []; for (let u = u0; u <= u1; u += 4) us.push(u); return [...us.map((u) => [u, vOrilla(u) + v0]), ...[...us].reverse().map((u) => [u, vOrilla(u) + v1])]; };
  zonaA.add(malla(losa(banda(-29, -7).map(L), 0.12), C.ribera, false));
  zonaA.add(malla(losa(banda(-8.6, -6.2).map(L), 0.135), C.geotextil, false));
  zonaA.add(enrocado(banda(-7, 5).map(L), 2200, { tam: 1.15, alto: 0.7, semilla: 17, m: C.roca }));
  // la ruta del deck (para apartar plantas y árboles), antes de armarlo
  const md = D.mirador, mu = md.reduce((a, p) => a + p[0], 0) / md.length, mv = md.reduce((a, p) => a + p[1], 0) / md.length;
  const fin = D.deck[D.deck.length - 1], dirFin = [mu - fin[0], mv - fin[1]], lFin = Math.hypot(...dirFin) || 1;
  let tFin = 0;
  while (tFin < lFin && !dentro([fin[0] + (dirFin[0] / lFin) * tFin, fin[1] + (dirFin[1] / lFin) * tFin], md)) tFin += 0.25;
  const pDeck = tFin > 0 && tFin < lFin ? [...D.deck, [fin[0] + (dirFin[0] / lFin) * (tFin + 0.5), fin[1] + (dirFin[1] / lFin) * (tFin + 0.5)]] : D.deck;
  const ruta = suave(pDeck, 60), n = ruta.length, h0 = 0.35, h1 = 4.3, alto = (i) => h0 + (h1 - h0) * (i / (n - 1)) ** 0.85;
  const cerca = (p, d) => distLinea(p, ruta) < d || dentro(p, md);
  zonaA.add(...matasPorTipo(racimos(banda(-6.6, -1.2), 34, 5, 19, (p) => !cerca(p, 2.6), ['helecho', 'helecho', 'heliconia']), { helecho: 0.95, heliconia: 1.3 }, 21));
  // señales de ronda hídrica en los dos extremos de la plaza, de cara a ella: postes y tablero unidos, la cara instanciada
  const senales = [-34, 160].map((u) => [u, vOrilla(u) - 25]);
  zonaA.add(malla(unir(senales.flatMap(([u, v]) => [new THREE.BoxGeometry(0.1, 2.3, 0.1).translate(u - 0.7, 1.27, v + 0.02), new THREE.BoxGeometry(0.1, 2.3, 0.1).translate(u + 0.7, 1.27, v + 0.02), new THREE.BoxGeometry(1.7, 1.08, 0.05).translate(u, 1.84, v + 0.03)])), C.metal));
  const caraS = new THREE.InstancedMesh(new THREE.PlaneGeometry(1.6, 1.0).rotateY(Math.PI), C.ronda, senales.length);
  senales.forEach(([u, v], i) => caraS.setMatrixAt(i, new THREE.Matrix4().makeTranslation(u, 1.84, v)));
  caraS.computeBoundingSphere(); zonaA.add(caraS);

  // --- zona B: plaza de adoquín con franja perimetral más oscura y bordillo, prado, jardineras con árboles y plantas,
  // bancas, canecas, luminarias y bolardos
  const contorno = redondear(D.plaza, 9);
  plaza.add(malla(losa(contorno.map(L), 0.18), C.adoquin, false));
  plaza.add(malla(tira(adentro(contorno, 0.3), adentro(contorno, 1.8), 0.183, 0.183), C.adoquinB, false));
  // los bordillos de la plaza, del prado y de las jardineras van en una sola malla (mismo concreto)
  const bordes = [muroAnillo(contorno, -0.2, 0.3, 0, 0.3)];
  const cu = D.plaza.reduce((a, p) => a + p[0], 0) / D.plaza.length, cv = D.plaza.reduce((a, p) => a + p[1], 0) / D.plaza.length;
  const prado = Array.from({ length: 48 }, (_, i) => { const t = (i / 48) * 2 * Math.PI; return [cu + 24 * Math.cos(t), cv - 12 + 8 * Math.sin(t)]; });
  plaza.add(malla(losa(prado.map(L), 0.19), C.prado, false)); bordes.push(muroAnillo(prado, -0.12, 0.12, 0.15, 0.28));
  const jardineras = [[cu - 30, cv + 10, 4.5], [cu - 12, cv + 4, 5.5], [cu + 14, cv + 8, 5], [cu + 32, cv + 4, 4.5], [cu - 32, cv - 14, 4], [cu + 33, cv - 16, 4]];
  const anillos = [], tierras = [], lBancas = [], lCanecas = [], enJardineras = { heliconia: [], cordyline: [], helecho: [] };
  jardineras.forEach(([u, v, rr], j) => {
    const pts = Array.from({ length: 36 }, (_, i) => [u + rr * Math.cos((i / 36) * 2 * Math.PI), v + rr * Math.sin((i / 36) * 2 * Math.PI)]);
    anillos.push(muroAnillo(pts, -0.05, 0.3, 0.1, 0.6)); tierras.push(losa(adentro(pts, 0.3).map(L), 0.55));
    [0.5, 2.6, 4.4].forEach((a, k) => {
      const x = u + (rr + 0.95) * Math.cos(a), z = v + (rr + 0.95) * Math.sin(a), rot = Math.atan2(Math.cos(a), Math.sin(a));
      lBancas.push(Object.assign([x, -z, rot], { h: 0.18 }));
      if ((j + k) % 3 === 0) lCanecas.push(Object.assign([u + (rr + 0.7) * Math.cos(a + 0.42), -(v + (rr + 0.7) * Math.sin(a + 0.42)), rot], { h: 0.18 }));
      const sg = r() < 0.5 ? 1 : -1;   // a un lado de la banca: su eje largo va en (cos rot, sen rot) del modelo
      if (r() < 0.45) quien.sentados.push(Object.assign([x + Math.cos(rot) * 0.42 * sg, -z + Math.sin(rot) * 0.42 * sg, rot], { h: 0.18 + 0.51 - 0.42 }));
    });
    sembrar(adentro(pts, 0.55), Math.round(rr * rr * 1.6), 0.85, 30 + j).filter(([pu, pv]) => Math.hypot(pu - u, pv - v) > 0.9).forEach((p, i) => enJardineras[['heliconia', 'cordyline', 'helecho', 'cordyline'][i % 4]].push(L(p)));
  });
  verde.add(...matasPorTipo(enJardineras, { heliconia: 1.4, cordyline: 1.0, helecho: 0.9 }, 30, 0.55));   // sobre la tierra de las jardineras
  plaza.add(malla(unir([...bordes, ...anillos]), C.borde), malla(unir(tierras), C.tierra, false), bancas(lBancas), canecas(lCanecas));
  const arbJ = arboles(jardineras.map(([u, v]) => L([u, v])), { alto: 8, semilla: 51, especie: 'guayacan' }); arbJ.position.y = 0.55;
  verde.add(arbJ);
  verde.add(palmas([D.plaza[0], D.plaza[3], D.plaza[4], D.plaza[7]].map(([u, v]) => L([u + (u < cu ? 5 : -5), v + (v < cv ? 5 : -5)])), { alto: 9, semilla: 52 }));
  // luminarias 1,2 m adentro del borde y bolardos de luz frente al parqueadero y a la entrada del deck
  const luces = aLoLargo(adentro(contorno, 1.2).map(L), 15);
  plaza.add(alzarCharcos(postes(luces, 4.6), 0.04));
  // baranda en el borde de la plaza que da a la ronda (deja libre la entrada al deck)
  const bordeRio = adentro(contorno, 0.6).filter(([u, v]) => v > cv + 18 && Math.hypot(u - D.deck[0][0], v - D.deck[0][1]) > 7);
  const lPlaza = { metal: [], madera: [], led: [] };
  if (bordeRio.length > 1) barandal(bordeRio.map(([u, v]) => [u, v, 0.18]), lPlaza);
  // parqueadero sobre el borde de la vía y acceso desde la vía del puente (el empalme se acuerda con la concesión)
  const sur = [...D.plaza].sort((a, b) => a[1] - b[1]).slice(0, 2).sort((a, b) => a[0] - b[0]), lBolardos = [], asfaltos = [];
  if (sur.length === 2) {
    const [a, b] = sur, u0 = a[0] - 1, u1 = Math.min(b[0] - 4, u0 + 50), v1 = Math.min(a[1], b[1]) - 1, v0 = v1 - 5.5, cupos = Math.floor((u1 - u0) / 2.5);
    asfaltos.push(losa([[u0, v0], [u1, v0], [u1, v1], [u0, v1]].map(L), 0.1));
    const rayas = []; for (let k = 0; k <= cupos; k++) { const u = u0 + k * 2.5; rayas.push(cinta([[u, v0 + 0.4], [u, v1 - 0.4]].map(L), 0.1, 0.11)); }
    plaza.add(malla(unir(rayas), C.cal, false));
    plaza.add(malla(unir([new THREE.BoxGeometry(u1 - u0 + 0.3, 0.15, 0.18).translate((u0 + u1) / 2, 0.075, v0 - 0.09), new THREE.BoxGeometry(0.18, 0.15, v1 - v0).translate(u0 - 0.09, 0.075, (v0 + v1) / 2), new THREE.BoxGeometry(0.18, 0.15, v1 - v0).translate(u1 + 0.09, 0.075, (v0 + v1) / 2)]), C.concreto));
    const vc = (v0 + v1) / 2, cars = [], motos = [];
    for (let k = 0; k < cupos; k++) {
      const u = u0 + 1.25 + k * 2.5;
      if (k === cupos - 1) [-0.75, 0, 0.75].forEach((du, i) => motos.push([u + du, -(vc + (i - 1) * 0.6), -Math.PI / 2 + (r() - 0.5) * 0.2]));
      else if (r() < 0.7) cars.push(Object.assign([u, -(vc - 0.3), -Math.PI / 2 + (r() - 0.5) * 0.06], { h: 0.1 }));
    }
    plaza.add(carros(cars, { semilla: 27 }));
    if (motos.length) {
      const imC = new THREE.InstancedMesh(geoMoto.carroceria, C.moto, motos.length), imO = new THREE.InstancedMesh(geoMoto.oscuro, C.llanta, motos.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0);
      motos.forEach(([x, y, rr], i) => { m4.compose(new THREE.Vector3(x, 0.1, -y), q.setFromAxisAngle(Y, rr), new THREE.Vector3(1, 1, 1)); imC.setMatrixAt(i, m4); imO.setMatrixAt(i, m4); imC.setColorAt(i, MOTOS[i % MOTOS.length]); });
      [imC, imO].forEach((o) => { o.castShadow = true; o.computeBoundingSphere(); plaza.add(o); });
    }
    aLoLargo([[u0 + 0.5, v1 + 2.3], [u1 - 0.5, v1 + 2.3]].map(L), 3.1).forEach(([x, y]) => lBolardos.push([x, y]));
    quien.plaza.push([u0 + 4, -(v1 + 3.4), 0.3], [u0 + 4.7, -(v1 + 3.8), 2.4], Object.assign([u1 - 1.3, -(vc + 1.4), 1.6], { h: 0.1 }));
  }
  lBolardos.push(...[[D.deck[0][0] - 1.6, D.deck[0][1] - 3.2], [D.deck[0][0] + 1.4, D.deck[0][1] - 3.4]].map(L));
  plaza.add(alzarCharcos(bolardos(lBolardos), 0.04));
  // vía de acceso con su línea amarilla
  asfaltos.push(cinta(D.acceso.map(L), 7, 0.1));
  plaza.add(malla(unir(asfaltos), C.asfalto, false), malla(unir(aLoLargo(D.acceso, 4).map(([u, v, a]) => new THREE.BoxGeometry(1.8, 0.01, 0.12).rotateY(-a).translate(u, 0.112, v))), C.amarilla, false));
  // caseta de información turística junto a la entrada del deck, con el letrero «Puerta del Magdalena» de cara a la plaza
  {
    const g = new THREE.Group(), w = 3.8, d = 2.6, hm = 2.7;
    g.add(malla(new THREE.BoxGeometry(w, hm, d).translate(0, hm / 2, 0), C.muro), malla(new THREE.BoxGeometry(w + 0.04, 0.55, d + 0.04).translate(0, 0.275, 0), C.ladrillo));
    g.add(malla(new THREE.BoxGeometry(w + 1.4, 0.18, d + 1.6).translate(0, hm + 0.09, 0.1), C.techo));
    g.add(malla(new THREE.BoxGeometry(2.3, 1.0, 0.05).translate(-0.4, 1.45, -d / 2 - 0.01), C.vidrio, false));
    g.add(malla(new THREE.PlaneGeometry(4.36, 0.94).rotateY(Math.PI).translate(0, hm + 1.0, -0.665), C.letrero, false));
    g.position.set(D.deck[0][0] - 6.5, 0.18, D.deck[0][1] - 8.5); plaza.add(g);
    // mostrador, puerta y la estructura del letrero van con la madera y el acero de la plaza (menos llamadas de dibujo)
    const enK = (geo) => geo.translate(g.position.x, g.position.y, g.position.z);
    lPlaza.madera.push(enK(new THREE.BoxGeometry(2.6, 0.06, 0.45).translate(-0.4, 0.95, -d / 2 - 0.2)), enK(new THREE.BoxGeometry(0.05, 2.1, 0.9).translate(w / 2 + 0.02, 1.05, 0.2)));
    lPlaza.metal.push(enK(new THREE.BoxGeometry(0.1, 1.1, 0.1).translate(-1.6, hm + 0.73, -0.6)), enK(new THREE.BoxGeometry(0.1, 1.1, 0.1).translate(1.6, hm + 0.73, -0.6)), enK(new THREE.BoxGeometry(4.5, 1.05, 0.12).translate(0, hm + 1.0, -0.6)));
    quien.plaza.push([g.position.x - 0.6, -(g.position.z - 2.3), 0.2], [g.position.x + 0.5, -(g.position.z - 3.1), 2.9]);
  }
  // vendedores con carrito y sombrilla cerca de las letras, y la gente: la foto frente a las letras y los que pasean
  const [lu, lv] = D.letras, carritos = [[lu - 13, lv - 7, 0.4], [lu + 13, lv - 6, 2.7], [cu - 24, cv - 22, -0.6]];
  {
    const n3 = carritos.length, ims = [[geoCarrito.caja, C.carrito], [geoCarrito.metal, C.metal], [geoCarrito.sombrilla, C.sombrilla]].map(([gg, m]) => new THREE.InstancedMesh(gg, m, n3)), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0);
    carritos.forEach(([u, v, a], i) => { m4.compose(new THREE.Vector3(u, 0.18, v), q.setFromAxisAngle(Y, a), new THREE.Vector3(1, 1, 1)); ims.forEach((im) => im.setMatrixAt(i, m4)); ims[2].setColorAt(i, SOMBRILLAS[i % SOMBRILLAS.length]); quien.plaza.push(Object.assign([u + Math.cos(a) * 1.1, -(v - Math.sin(a) * 1.1), a], { h: 0.18 })); });
    ims.forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); plaza.add(o); });
  }
  [-2.4, -1.5, -0.6, 0.8, 2.0].forEach((du, i) => quien.plaza.push([lu + du, -(lv - 5.2 - (i % 2) * 0.5), 0]));
  quien.plaza.push([lu + 0.4, -(lv - 9.5), Math.PI]);   // el de la foto
  const libresPlaza = sembrar(adentro(D.plaza, 4), 60, 3.5, 41).filter(([u, v]) => Math.hypot((u - cu) / 25.5, (v - cv + 12) / 9.5) > 1 && jardineras.every(([ju, jv, rr]) => Math.hypot(u - ju, v - jv) > rr + 2) && Math.hypot(u - lu, v - lv) > 9 && Math.hypot(u - D.deck[0][0] + 6.5, v - D.deck[0][1] + 8.5) > 5 && carritos.every(([cx, cz]) => Math.hypot(u - cx, v - cz) > 2.6));
  libresPlaza.slice(0, 18).forEach(([u, v]) => quien.plaza.push([u, -v, r() * 6.28]));

  // --- letras «YONDÓ» de colores (≈14 m), de frente a la plaza y con el río detrás
  // (si la tipografía no se descarga, el mirador se arma igual, con el zócalo sin letras)
  const ly = await letras('YONDO', { alto: 3.2, fondo: 0.8, colores: ['#7cc242', '#2a9fd6', '#e8452c', '#1f6fd1', '#f5b400'], acento: 4, separacion: 0.4 }).catch((e) => { console.warn('letras del mirador', e); return null; });
  const zocalo = new THREE.Mesh(new THREE.BoxGeometry(15.5, 0.7, 2.4).translate(0, 0.35, 0), C.concreto); zocalo.position.set(lu, 0.05, lv);
  letrasG.add(sombra(zocalo));
  if (ly) { ly.position.set(lu, 0.7, lv); ly.rotation.y = Math.PI; letrasG.add(sombra(ly)); }   // el texto mira hacia −v (la plaza): la «Y» queda aguas abajo

  // --- sendero curvo en deck: sale de la plaza, cruza la ronda y corre por el borde del agua hasta el mirador. Tablas de
  // 15 cm sobre dos largueros y pilotes cada ~6 m; la rampa sube de 0,35 m (el bordillo de la plaza) a 4,3 m (4–5 %)
  const lDeck = { madera: [], metal: [], led: [], tabla: [], pilote: [], lona: [] };
  for (let i = 1; i < n; i++) {
    const [a, b] = [ruta[i - 1], ruta[i]], Lg = Math.hypot(b[0] - a[0], b[1] - a[1]), yaw = Math.atan2(-(b[1] - a[1]), b[0] - a[0]), ha = alto(i - 1), hb = alto(i), pitch = Math.atan2(hb - ha, Lg);
    const k = Math.max(1, Math.round(Lg / 0.17));
    for (let j = 0; j < k; j++) { const t = (j + 0.5) / k; lDeck.tabla.push(new THREE.BoxGeometry(0.15, 0.05, 3).rotateZ(pitch).rotateY(yaw).translate(a[0] + (b[0] - a[0]) * t, ha + (hb - ha) * t + 0.075, a[1] + (b[1] - a[1]) * t)); }
    [-1.3, 1.3].forEach((o) => { const x = (a[0] + b[0]) / 2 + Math.sin(yaw) * o, z = (a[1] + b[1]) / 2 + Math.cos(yaw) * o; lDeck.pilote.push(new THREE.BoxGeometry(Lg + 0.05, 0.24, 0.12).rotateZ(pitch).rotateY(yaw).translate(x, (ha + hb) / 2 - 0.07, z)); });
    if (i % 4 === 0) {
      lDeck.pilote.push(new THREE.BoxGeometry(0.14, 0.16, 3.1).rotateY(yaw).translate(a[0], ha - 0.1, a[1]));
      [-1.35, 1.35].forEach((o) => { const x = a[0] + Math.sin(yaw) * o, z = a[1] + Math.cos(yaw) * o; lDeck.pilote.push(new THREE.CylinderGeometry(0.14, 0.14, ha + 3, 8).translate(x, (ha - 3) / 2, z)); });
    }
  }
  // barandas a los dos lados, cortadas donde el deck entra a la plataforma
  const lado = (o) => ruta.map(([u, v], i) => { const [a, b] = [ruta[Math.max(0, i - 1)], ruta[Math.min(n - 1, i + 1)]], ang = Math.atan2(b[1] - a[1], b[0] - a[0]); return [u - Math.sin(ang) * o, v + Math.cos(ang) * o, alto(i) + 0.1]; });
  const tramos = (pts) => { const out = [[]]; pts.forEach((p) => { if (dentro([p[0], p[1]], md)) { if (out[out.length - 1].length) out.push([]); } else out[out.length - 1].push(p); }); return out.filter((t) => t.length > 1); };
  [1.45, -1.45].forEach((o) => tramos(lado(o)).forEach((t) => barandal(t, lDeck)));
  // --- mirador: plataforma de 10 × 10 m sobre pilotes en el borde del agua, de tablas, con baranda y lona tensada
  const e1 = [md[1][0] - md[0][0], md[1][1] - md[0][1]], e2 = [md[3][0] - md[0][0], md[3][1] - md[0][1]], l1 = Math.hypot(...e1), l2 = Math.hypot(...e2), yawM = Math.atan2(-e1[1], e1[0]);
  for (let t = 0.09; t < l2 - 0.05; t += 0.17) { const cxm = md[0][0] + e1[0] / 2 + (e2[0] / l2) * t, czm = md[0][1] + e1[1] / 2 + (e2[1] / l2) * t; lDeck.tabla.push(new THREE.BoxGeometry(l1 - 0.1, 0.05, 0.15).rotateY(yawM).translate(cxm, h1 + 0.075, czm)); }
  const plataforma = new THREE.Mesh(new THREE.ExtrudeGeometry(new THREE.Shape(md.map(L).map(([x, y]) => new THREE.Vector2(x, y))), { depth: 0.3, bevelEnabled: false }).rotateX(-Math.PI / 2).translate(0, h1 - 0.25, 0), C.pilote);
  deck.add(sombra(plataforma));
  md.forEach(([u, v]) => lDeck.pilote.push(new THREE.CylinderGeometry(0.2, 0.2, h1 + 4, 8).translate(u + (mu - u) * 0.08, (h1 - 4) / 2, v + (mv - v) * 0.08)));
  lDeck.pilote.push(new THREE.CylinderGeometry(0.22, 0.22, h1 + 4, 8).translate(mu, (h1 - 4) / 2, mv));
  // baranda de la plataforma: un lazo abierto en el lado por donde llega el deck
  const llegada = ruta[n - 1], ladoDeck = md.reduce((k, p, i) => { const q = md[(i + 1) % md.length], dm = (rr) => Math.hypot((rr[0] + rr[2]) / 2 - llegada[0], (rr[1] + rr[3]) / 2 - llegada[1]); return dm([...p, ...q]) < dm([...md[k], ...md[(k + 1) % md.length]]) ? i : k; }, 0);
  const borde = Array.from({ length: md.length }, (_, j) => md[(ladoDeck + 1 + j) % md.length]).map(([u, v]) => [u + (mu - u) * 0.04, v + (mv - v) * 0.04, h1 + 0.1]);
  barandal(borde, lDeck);
  // lona tensada en paraboloide (como membrana() de geo3d) con sus cuatro mástiles de acero hasta cada esquina, unidos al
  // acero del deck
  {
    const w = 7.4, hL = 3.3, fl = 1.1, geo = new THREE.PlaneGeometry(w, w, 14, 14), p = geo.attributes.position, alturaL = (a, b) => a * b * fl * 0.5 + (1 - a * a) * 0.25 * fl;
    for (let i = 0; i < p.count; i++) p.setZ(i, alturaL(p.getX(i) / (w / 2), p.getY(i) / (w / 2)));
    geo.computeVertexNormals(); geo.rotateX(-Math.PI / 2); geo.rotateY(yawM); geo.translate(mu, h1 + 0.1 + hL, mv); lDeck.lona.push(geo);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => { const hh = hL + alturaL(a, -b) + 0.12, c = new THREE.Vector3(a * w / 2, 0, b * w / 2).applyAxisAngle(new THREE.Vector3(0, 1, 0), yawM); lDeck.metal.push(new THREE.CylinderGeometry(0.07, 0.1, hh, 8).translate(mu + c.x, h1 + 0.1 + hh / 2, mv + c.z)); });
  }
  // dos bancas mirando al río y gente asomada a la baranda
  const haciaRio = [(e2[0] / l2) * Math.sign(e2[1] || 1), (e2[1] / l2) * Math.sign(e2[1] || 1)], rotR = Math.atan2(haciaRio[0], haciaRio[1]);
  const lbDeck = [-2.2, 2.2].map((du) => Object.assign([mu + du, -(mv - 1.2), rotR], { h: h1 + 0.1 }));
  deck.add(bancas(lbDeck));
  [[-3, 4.3], [-1.9, 4.4], [2.5, 4.2], [4.3, 2.0], [-4.2, 0.6]].forEach(([du, dv]) => quien.deck.push(Object.assign([mu + du, -(mv + dv), rotR], { h: h1 + 0.1 })));
  for (let i = 6; i < n - 6; i += 9) { const o = (r() - 0.5) * 1.6, [a, b] = [ruta[i - 1], ruta[i + 1]], ang = Math.atan2(b[1] - a[1], b[0] - a[0]); quien.deck.push(Object.assign([ruta[i][0] - Math.sin(ang) * o, -(ruta[i][1] + Math.cos(ang) * o), r() * 6.28], { h: alto(i) + 0.1 })); }

  // --- en el río, una chalupa de toldo amarillo cruza hacia Barrancabermeja con su estela, frente al mirador: paisaje del
  // Magdalena, no obra (la propuesta no lleva muelle). Va suelta en la pieza, sin grupo: no es una parte que se quite
  const rio = new THREE.Group(); raiz.add(rio);
  const pasajeros = [], piloto = [];
  {
    const Lc = 11, B = 2.3, M = new THREE.Matrix4().makeRotationY(-Math.PI / 2 - 0.15).setPosition(mu + 16, 0, mv + 44.5);
    const ch = chalupa(Lc, B, { toldo: true, franja: '#f0c419' });
    const lote = { casco: [ch.casco], interior: [ch.piso], madera: ch.madera, metal: ch.metal, toldo: ch.lona, motor: ch.motor };
    Object.values(lote).forEach((gs) => gs.forEach((g) => g.applyMatrix4(M)));
    volcar(rio, lote, C);
    rio.add(new THREE.Mesh(estelaGeo(Lc, B).applyMatrix4(M), C.estela));
    const yaw = new THREE.Euler().setFromRotationMatrix(M, 'YXZ').y;
    ch.puestos.slice(0, 6).forEach(([x, z]) => { const p = new THREE.Vector3(x, 0, z).applyMatrix4(M); pasajeros.push(Object.assign([p.x, -p.z, yaw, { camisa: '#f07a1f' }], { h: 0.475 - 0.42 })); });
    const pm = new THREE.Vector3(ch.popa, 0, 0).applyMatrix4(M); piloto.push(Object.assign([pm.x, -pm.z, yaw, { camisa: '#f07a1f' }], { h: 0.18 }));
  }
  volcar(deck, lDeck, { ...C, tabla: C.tabla, led: luzComun() });
  volcar(plaza, lPlaza, { ...C, led: luzComun() });

  // --- gente: en la plaza, sentados en las bancas, en el deck y el mirador, y en la chalupa que cruza (chaleco naranja)
  plaza.add(gente(quien.plaza.map((it) => (it.h != null ? it : Object.assign(it, { h: 0.18 }))), { semilla: 61 }), gente(quien.sentados, { sentado: true, semilla: 62 }));
  deck.add(gente(quien.deck, { semilla: 63 }));
  rio.add(gente(piloto, { semilla: 65 }), gente(pasajeros, { sentado: true, semilla: 66 }));

  // --- vegetación de ribera en la ronda: árboles nativos lejos del deck, y fuera del cono de la cámara del paso (que mira
  // hacia +v por encima de la plaza): ahí, matas y palmas bajas, para que el deck y el mirador se lean
  const us = [...ruta, ...md].map((p) => p[0]), uMin = Math.min(...us) - 12, uMax = Math.max(...us) + 10;
  const ribera = sembrar(banda(-27, -9.5), 90, 6.5, 29).filter(([u, v]) => distLinea([u, v], ruta) > 9 && !dentro([u, v], D.plaza) && Math.abs(u) > 16 && (u < uMin || u > uMax));
  // con los tres árboles del prado de la plaza en la misma malla
  verde.add(arboles([[cu - 16, cv - 12], [cu, cv - 13], [cu + 16, cv - 11], ...ribera].map(L), { alto: 9.5, semilla: 57, especie: 'mixto' }));
  verde.add(palmas(sembrar(banda(-24, -12), 14, 13, 31).filter(([u, v]) => distLinea([u, v], ruta) > 6.5 && Math.abs(u) > 16 && !dentro([u, v], md)).map(L), { alto: 9, semilla: 58 }));
  verde.add(...matasPorTipo(racimos(bandaU(uMin, uMax, -27, -8.5), 36, 4.6, 33, (p) => !cerca(p, 2.4) && !dentro(p, D.plaza), ['heliconia', 'helecho', 'cordyline', 'helecho']), { heliconia: 1.5, helecho: 0.9, cordyline: 1.0 }, 70));

  raiz.userData.partes = { zonaA, plaza, deck, verde, letras: letrasG };
  raiz.updateMatrixWorld(true);
  const aModelo = (u, v) => { const p = new THREE.Vector3(u, 0, v).applyMatrix4(raiz.matrixWorld); return [p.x, -p.z]; };
  raiz.userData.aModelo = aModelo;
  const usC = [...D.plaza, ...ruta, ...md].map((p) => p[0]), vsC = [...D.plaza, ...ruta, ...md].map((p) => p[1]);
  raiz.userData.contorno = [[Math.min(...usC) - 6, Math.min(...vsC) - 6], [Math.max(...usC) + 6, Math.min(...vsC) - 6], [Math.max(...usC) + 6, Math.max(...vsC) + 6], [Math.min(...usC) - 6, Math.max(...vsC) + 6]].map(([u, v]) => aModelo(u, v));
  raiz.userData.contornoA = D.zonaA.map(([u, v]) => aModelo(u, v));
  raiz.userData.zonaA = aModelo(14, vOrilla(14) - 16); raiz.userData.zonaB = aModelo(cu, cv - 21);
  raiz.userData.mirador = aModelo(mu, mv);
  return raiz;
}
