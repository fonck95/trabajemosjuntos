// Relleno sanitario municipal nuevo (vereda Kilómetro Cinco): predio con franja de árboles, celdas por fases (la de la
// fase 1 como un cerro de tres terrazas de 3 m que se retiran 9 m por nivel, o sea taludes de 3H:1V, con las dos de abajo
// ya cubiertas de pasto y la de arriba, la cara activa, con geomembrana; las demás, celdas futuras), lagunas de lixiviados,
// ECA y planta de compostaje, portería con báscula y la entrada desde la vía. Todo va en metros del modelo: los polígonos
// vienen de geo.json (saneamiento) y la función solo los arma.
import { THREE, mat } from '../../core.js';
import { losa, prisma, cinta, arboles, nave, centro, dentro, V } from '../geo3d.js';

const sombra = (o) => { o.traverse((k) => { if (k.isMesh) { k.castShadow = true; k.receiveShadow = true; } }); return o; };
const capa = (raiz, n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
// terrazas de la celda de la fase 1: alto de cada una y cuánto se retira la siguiente (3H:1V)
const TERRAZAS = 3, ALTO = 3, RETIRO = 9;

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

// { predio, celdas: polígono convexo de la fase 1, futuras: [polígonos], lixiviados: [polígonos], eca, compostaje,
//   porteria: [x, y] (o polígono), entrada: [[x, y], [x, y]] (de la vía a la portería) }
export function rellenoNuevo({ predio, celdas, futuras = [], lixiviados = [], eca, compostaje, porteria, entrada }) {
  const raiz = new THREE.Group();
  const piso = capa(raiz, 'piso'), cerro = capa(raiz, 'celdas'), obras = capa(raiz, 'obras'), verde = capa(raiz, 'verde');
  // las losas del piso (predio, celdas futuras y entrada) se adelantan solo unas unidades de profundidad, sin el término
  // de la pendiente: de lejos y en ángulo bajo ese término las adelantaba metros y tapaban las lagunas, las pilas de
  // compostaje y la báscula, que van pocos centímetros por encima. Las unidades bastan para que no titilen contra el piso
  const M = {
    predio: mat(new THREE.Color('#c9bfa4'), { roughness: 1, polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -2 }),
    futura: mat(new THREE.Color('#d8cfb4'), { roughness: 1, polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -3 }),
    cubierta: mat(new THREE.Color('#7f9f5a'), { roughness: 1 }), talud: mat(new THREE.Color('#a39577'), { roughness: 1 }),
    geomembrana: mat(new THREE.Color('#2b3833'), { roughness: 0.45, metalness: 0.1 }), lixiviado: mat(new THREE.Color('#55603f'), { roughness: 0.2 }),
    borde: mat(new THREE.Color('#bdb8ad'), { roughness: 0.9 }), via: mat(new THREE.Color('#a8997f'), { roughness: 1, polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -4 }),
    compost: mat(new THREE.Color('#6f5233'), { roughness: 1 }), placa: mat(new THREE.Color('#3f464c'), { roughness: 0.6, metalness: 0.3 }),
    caseta: mat(new THREE.Color('#ece8e0'), { roughness: 0.85 }),
  };
  if (predio) piso.add(new THREE.Mesh(losa(predio, 0.08), M.predio));
  futuras.forEach((f) => piso.add(new THREE.Mesh(losa(f, 0.12), M.futura)));
  // celda de la fase 1: tres terrazas de 3 m (9 m de alto) que se retiran 9 m por nivel; las de abajo, cerradas y con pasto,
  // y la de arriba, la cara activa, con geomembrana y una franja de cobertura diaria
  if (celdas) {
    for (let k = 0; k < TERRAZAS; k++) {
      const p = adentro(celdas, k * RETIRO), arriba = k === TERRAZAS - 1;
      cerro.add(sombra(new THREE.Mesh(prisma(p, ALTO, k * ALTO), arriba ? M.geomembrana : M.cubierta)));
      if (!arriba) cerro.add(new THREE.Mesh(cinta([...p, p[0], p[1]], 1.2, (k + 1) * ALTO + 0.02), M.talud));
    }
    const top = adentro(celdas, (TERRAZAS - 1) * RETIRO), [tx, ty] = centro(top), f = marcoDe(top);
    const cob = [[-f.w * 0.42, -f.d * 0.12], [-f.w * 0.05, -f.d * 0.12], [-f.w * 0.05, f.d * 0.32], [-f.w * 0.42, f.d * 0.32]].map(([u, v]) => [tx + u * Math.cos(f.ang) - v * Math.sin(f.ang), ty + u * Math.sin(f.ang) + v * Math.cos(f.ang)]);
    cerro.add(new THREE.Mesh(losa(cob, TERRAZAS * ALTO + 0.06), M.talud));
  }
  // lagunas de lixiviados con su borde de concreto
  lixiviados.forEach((l) => {
    piso.add(new THREE.Mesh(losa(l, 0.3), M.lixiviado));
    obras.add(new THREE.Mesh(cinta([...l, l[0], l[1]], 1.4, 0.55), M.borde));
  });
  // ECA: nave de clasificación alineada con su lote; compostaje: pilas en hileras a lo largo del lado mayor
  const marcos = {};
  if (eca) {
    const f = marcos.eca = marcoDe(eca);
    obras.add(nave(f.cx, f.cy, Math.min(48, f.w * 0.8), Math.min(30, f.d * 0.75), 8, f.ang, { techo: 'dosaguas' }));
  }
  if (compostaje) {
    const f = marcos.compostaje = marcoDe(compostaje), n = Math.max(3, Math.min(8, Math.floor((f.d - 6) / 5.5)));
    const largo = Math.max(10, f.w - 10), pila = new THREE.ExtrudeGeometry(new THREE.Shape([new THREE.Vector2(-1.8, 0), new THREE.Vector2(1.8, 0), new THREE.Vector2(0, 1.6)]), { depth: largo, bevelEnabled: false }).translate(0, 0, -largo / 2).rotateY(Math.PI / 2);
    for (let k = 0; k < n; k++) {
      const v = -((n - 1) * 5.5) / 2 + k * 5.5, m = new THREE.Mesh(pila, M.compost);
      m.position.copy(V(f.cx - v * Math.sin(f.ang), f.cy + v * Math.cos(f.ang))); m.rotation.y = f.ang;
      sombra(m); obras.add(m);
    }
  }
  // portería con báscula de camiones, girada con la entrada
  if (porteria) {
    const [px, py] = Array.isArray(porteria[0]) ? centro(porteria) : porteria, ang = entrada?.length > 1 ? Math.atan2(entrada[1][1] - entrada[0][1], entrada[1][0] - entrada[0][0]) : 0;
    const g = new THREE.Group(); g.position.copy(V(px, py)); g.rotation.y = ang;
    g.add(new THREE.Mesh(new THREE.BoxGeometry(6, 3.4, 4).translate(0, 1.7, 7), M.caseta), new THREE.Mesh(new THREE.BoxGeometry(18, 0.3, 3.6).translate(0, 0.15, 0), M.placa));
    obras.add(sombra(g));
  }
  // entrada nueva en afirmado, de la vía a Puerto Berrío a la portería
  if (entrada?.length > 1) piso.add(new THREE.Mesh(cinta(entrada, 7, 0.14), M.via));
  // franja de aislamiento: árboles cada 9 m a 6 m del lindero, hacia adentro (el predio no es convexo: se muestrea cada lado
  // y se descartan los puntos que caen fuera)
  if (predio) verde.add(arboles(franja(predio, 6, 9), { alto: 11, semilla: 77 }));

  raiz.userData.partes = { piso, celdas: cerro, obras, verde };
  raiz.userData.contorno = predio || celdas;
  raiz.userData.centro = centro(predio || celdas);
  raiz.userData.celda = celdas ? centro(celdas) : null;
  raiz.userData.eca = marcos.eca ? [marcos.eca.cx, marcos.eca.cy] : null;
  raiz.userData.compostaje = marcos.compostaje ? [marcos.compostaje.cx, marcos.compostaje.cy] : null;
  raiz.userData.lixiviados = lixiviados.length ? centro(lixiviados[0]) : null;
  return raiz;
}
