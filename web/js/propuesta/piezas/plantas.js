// Plantas industriales de la propuesta, armadas con geometría propia y orientadas sobre su lote, con el acabado de la
// cancha de sóftbol y de la vivienda (texturas en coordenadas del mundo, gente, vehículos, vegetación y luces):
//  · PTAR central del casco urbano: pretratamiento con rejillas y desarenador, reactores UASB con campanas de gas,
//    escalera de gato y tubería de biogás a la antorcha, filtros percoladores con lecho de piedra y brazo distribuidor que
//    gira, sedimentadores con puente barredor, lechos de secado con cubierta de policarbonato, edificio de operación y
//    laboratorio, vías con bordillo, cerramiento de malla, luminarias, camión vactor y operarios;
//  · módulo de ampliación de la PTAP (de 40 a ~60 L/s): floculador de pantallas, sedimentador de placas a 60°, filtros
//    rápidos con galería de tubos, pasarelas con baranda amarilla, edificio de químicos y tubería a la planta de hoy;
//  · parque agroindustrial: naves de pañete o lámina sobre zócalo con caballete, lucernarios, portones enrollables,
//    ventanas en franja y muelles de carga; silos con anillos, escalera y elevador; corrales cubiertos con ganado cebú;
//    biodigestor con domos de membrana y antorcha; compostaje en hileras; PTAR industrial con aireadores; patio de
//    maquinaria amarilla; camiones; portería con talanquera y báscula; cerco, barrera verde y muelle con planchón,
//    contenedores y grúa pórtico;
//  · granja solar centralizada: mesas de módulos con textura de celdas sobre estructura de dos postes, pasillos de grava,
//    vía de acceso, cerco con cámaras y letrero, casetas de inversores, subestación elevadora y salida a 13,2 kV.
// Cada función recibe el centro (x, y) y el rumbo del lote (grados desde el oriente, antihorario) y devuelve un grupo con
// partes nombradas para animarlas. La geometría de cada parte se junta por material (kit): pocas llamadas de dibujo.
import { THREE, mat, engine, reducedMotion } from '../../core.js';
import { losa, cinta, arboles, palmas, matas, gente, carros, postes, unir, azar, V, aLoLargo, dentro, distLinea, sembrar } from '../geo3d.js';
import { matT, matAgua } from '../texturas.js';

function marco(cx, cy, rumbo) {
  const g = new THREE.Group(); g.position.copy(V(cx, cy)); g.rotation.y = THREE.MathUtils.degToRad(rumbo);
  return g;
}
const capa = (raiz, n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
const aModelo = (raiz) => (u, v) => { raiz.updateMatrixWorld(true); const p = new THREE.Vector3(u, 0, -v).applyMatrix4(raiz.matrixWorld); return [p.x, -p.z]; };

// ---------------------------------------------------------------- kit: geometrías juntadas por material
// Los materiales con color por vértice (pintura, pañete, lámina) reciben el color de cada pieza en el atributo color: con
// un solo material se pintan barandas amarillas, puertas grises y muros de colores, y todo sale en una llamada
const colores = new Map();
const C = (h) => { let c = colores.get(h); if (!c) { c = new THREE.Color(h); colores.set(h, c); } return c; };
function pintar(g, c) {
  const n = g.attributes.position.count, a = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { a[i * 3] = c.r; a[i * 3 + 1] = c.g; a[i * 3 + 2] = c.b; }
  g.setAttribute('color', new THREE.BufferAttribute(a, 3));
  return g;
}
// geometría unida con un color por pieza: [[geo, '#hex'], …]
const pintada = (lista) => unir(lista.map(([g, c]) => pintar(g.index ? g.toNonIndexed() : g, C(c))));
function kit() {
  const por = new Map(), K = {
    add(m, geo, color) { if (!por.has(m)) por.set(m, []); por.get(m).push([geo, color]); return K; },
    // vacía el kit en el padre: una malla por material (las de luz y las translúcidas no dan sombra)
    en(padre, sombra = true) {
      por.forEach((lista, m) => {
        const o = new THREE.Mesh(unir(lista.map(([g, c]) => (m.vertexColors ? pintar(g.index ? g.toNonIndexed() : g, C(c || '#ffffff')) : g))), m);
        o.castShadow = sombra && !m.transparent && !m.isMeshBasicMaterial; o.receiveShadow = !m.isMeshBasicMaterial; padre.add(o);
      });
      por.clear();
      return padre;
    },
  };
  return K;
}
// kit que transforma cada geometría antes de guardarla (piezas armadas en su propio marco)
const xf = (K, f) => ({ add(m, g, c) { K.add(m, f(g), c); return this; } });

// primitivas en el marco local de three (x, y arriba, z): base en y
const caja = (w, h, d, x = 0, y = 0, z = 0, ry = 0) => new THREE.BoxGeometry(w, h, d).rotateY(ry).translate(x, y + h / 2, z);
const cil = (r, h, x = 0, y = 0, z = 0, seg = 16, r2 = r, abierto = false) => new THREE.CylinderGeometry(r2, r, h, seg, 1, abierto).translate(x, y + h / 2, z);
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _q = new THREE.Quaternion(), EJE_Y = new THREE.Vector3(0, 1, 0), EJE_X = new THREE.Vector3(1, 0, 0);
// cilindro de radio r entre dos puntos [x, y, z] (tubos, cables, patas)
function barra(a, b, r, seg = 6) {
  _a.set(...a); _b.set(...b).sub(_a); const L = _b.length();
  return new THREE.CylinderGeometry(r, r, L, seg).translate(0, L / 2, 0).applyQuaternion(_q.setFromUnitVectors(EJE_Y, _b.normalize())).translate(_a.x, _a.y, _a.z);
}
// perfil de sección w (ancho) × h (alto) entre dos puntos [x, y, z] (brazos de máquinas, vigas, pasarelas)
function viga(a, b, w, h) {
  _b.set(b[0] - a[0], b[1] - a[1], b[2] - a[2]); const L = _b.length();
  return new THREE.BoxGeometry(L, h, w).applyQuaternion(_q.setFromUnitVectors(EJE_X, _b.normalize())).translate((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2);
}
// recorre una polilínea [[x, z], …] por tramos: f(a, b, largo, giro en y que alinea el eje x con el tramo)
function tramos(pts, f) { for (let i = 1; i < pts.length; i++) { const [a, b] = [pts[i - 1], pts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L > 0.01) f(a, b, L, Math.atan2(-(b[1] - a[1]), b[0] - a[0])); } }
const anillo = (cx, cz, r, n = 24) => Array.from({ length: n + 1 }, (_, i) => [cx + r * Math.cos((i / n) * 2 * Math.PI), cz + r * Math.sin((i / n) * 2 * Math.PI)]);
// polígono del modelo [[u, v], …] corrido d metros hacia adentro (contornos de zonas que comparten borde)
function adentro(poly, d) {
  let s = 0; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) s += (poly[j][0] - poly[i][0]) * (poly[j][1] + poly[i][1]);
  const k = s > 0 ? 1 : -1, n = poly.length;   // s > 0: antihorario (la normal izquierda mira adentro)
  return poly.map((p, i) => {
    const a = poly[(i + n - 1) % n], b = poly[(i + 1) % n], e1 = [p[0] - a[0], p[1] - a[1]], e2 = [b[0] - p[0], b[1] - p[1]], l1 = Math.hypot(...e1) || 1, l2 = Math.hypot(...e2) || 1;
    const n1 = [-e1[1] / l1 * k, e1[0] / l1 * k], n2 = [-e2[1] / l2 * k, e2[0] / l2 * k], m = [n1[0] + n2[0], n1[1] + n2[1]], lm = Math.hypot(...m) || 1, c = Math.max(0.3, (m[0] * n1[0] + m[1] * n1[1]) / lm);
    return [p[0] + (m[0] / lm) * (d / c), p[1] + (m[1] / lm) * (d / c)];
  });
}

// ---------------------------------------------------------------- materiales compartidos por las plantas
let MP = null;
function mats() {
  if (MP) return MP;
  MP = {
    muro: matT('estuco', { vertexColors: true }),
    cubierta: matT('zinc', { vertexColors: true, metalness: 0.45, roughness: 0.46 }),
    ladrillo: matT('ladrillo'), concreto: matT('concreto'),
    patio: matT('concreto', { modo: 'xz', escala: 4, macro: 0.1, color: '#e4e0d8' }),
    asfalto: matT('asfalto'), cesped: matT('cesped', { color: '#cfdcb0' }),
    grava: matT('tierra', { color: '#c9c2b2', escala: 3 }), afirmado: matT('tierra', { color: '#b8aa90' }),
    compost: matT('tierra', { color: '#6b5236', relieve: 0.03, escala: 3 }), lodo: matT('tierra', { color: '#5e4c3b', relieve: 0.02, escala: 2.5 }),
    grano: matT('tierra', { color: '#e6d18e', escala: 2 }), antracita: matT('tierra', { color: '#46423b', escala: 2 }),
    roca: matT('roca', { color: '#8f8b82' }), membrana: matT('membrana', { color: '#4a7a52' }),
    malla: matT('malla', { color: '#b4bbc0' }),
    agua: matAgua('#4f93a8'), aguaVerde: matAgua('#5e8c80'), aguaTurbia: matAgua('#6d6a3b', { roughness: 0.3 }),
    pintura: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.55, metalness: 0.2 }),
    carroceria: new THREE.MeshStandardMaterial({ roughness: 0.35, metalness: 0.45 }),
    res: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92 }),
    inox: mat(new THREE.Color('#d6dbdf'), { roughness: 0.22, metalness: 0.85 }),
    vidrio: mat(new THREE.Color('#3a5262'), { roughness: 0.06, metalness: 0.7 }),
    poli: new THREE.MeshStandardMaterial({ color: new THREE.Color('#d3e1e6'), roughness: 0.3, metalness: 0.1, transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false }),
    llama: new THREE.MeshBasicMaterial({ color: new THREE.Color('#ffb54a'), toneMapped: false }),
  };
  MP.lamina = MP.cubierta;   // muros de lámina y cubiertas: la misma lámina ondulada (una malla menos por nave)
  // los pisos ganan a las vías del territorio que pasan por debajo (que tienen su propio desplazamiento de profundidad)
  [MP.cesped, MP.patio, MP.asfalto, MP.grava, MP.afirmado].forEach((m) => Object.assign(m, { polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }));
  return MP;
}
const AMARILLO = '#f2c230', OSCURO = '#2c3135', GALV = '#9aa3a9';

// ---------------------------------------------------------------- piezas de obra
// Nave industrial: largo L en x (la cumbrera va a lo largo), luz S en z, muros de alto h, centrada en el origen; `en`
// la lleva a su sitio. Muros de pañete o de lámina (lamina) sobre zócalo de ladrillo o concreto; cubierta a dos aguas con
// caballete (o monitor de ventilación), lucernarios y extractores, en arco o plana con antepecho; ventanas en franja alta
// en los muros largos; portones enrollables y muelles de carga con andén, abrigos y marquesina en el costado `frente`
// (±1: z positivo o negativo); puerta en el testero (±1: x). abierta: solo cubierta sobre columnas (corrales).
// Devuelve los puestos de los muelles [x, z, giro] en el borde del andén, con el giro de un camión que sale de él.
function naveInd(K, M, { L, S, h, techo = 'dosaguas', muro = '#efe9dc', cubierta = '#b4bcc1', lamina = false, zocalo = 'ladrillo', frente = 1, portones = 0, muelles = 0, ventanas = true, monitor = false, extractores = 0, lucernarios = true, testero = 0, abierta = false, en = (g) => g }) {
  const k = xf(K, en), al = 0.7, mm = lamina ? M.lamina : M.muro, a = 0.21, r = (S / 2) * Math.tan(a), w = S / 2 + al, ls = w / Math.cos(a), puestos = [];
  if (abierta) {
    for (let x = -L / 2; x <= L / 2 + 0.01; x += L / Math.max(1, Math.round(L / 6))) [-1, 1].forEach((s) => k.add(M.pintura, caja(0.25, h, 0.25, x, 0, s * (S / 2 - 0.2)), GALV));
    k.add(M.pintura, caja(L, 0.35, 0.2, 0, h - 0.35, S / 2 - 0.2), GALV).add(M.pintura, caja(L, 0.35, 0.2, 0, h - 0.35, -S / 2 + 0.2), GALV);
  } else {
    k.add(mm, caja(L, h, S), muro);
    if (zocalo) k.add(zocalo === 'ladrillo' ? M.ladrillo : M.concreto, caja(L + 0.08, zocalo === 'ladrillo' ? 1.2 : 1.6, S + 0.08));
  }
  if (techo === 'arco') {
    const R = w, f = 0.42, cima = h + R * f;
    k.add(M.cubierta, new THREE.CylinderGeometry(R, R, L + 2 * al, 28, 1, true, -Math.PI / 2, Math.PI).rotateX(-Math.PI / 2).rotateY(Math.PI / 2).scale(1, f, 1).translate(0, h, 0), cubierta);
    if (!abierta) {
      const pts = []; for (let i = 0; i <= 16; i++) { const z = -S / 2 + (S * i) / 16; pts.push(new THREE.Vector2(z, f * Math.sqrt(Math.max(0, R * R - z * z)) - 0.06)); }
      const sh = new THREE.Shape([new THREE.Vector2(S / 2, 0), new THREE.Vector2(-S / 2, 0), ...pts]);
      k.add(mm, new THREE.ShapeGeometry(sh).rotateY(Math.PI / 2).translate(L / 2, h, 0), muro).add(mm, new THREE.ShapeGeometry(sh).rotateY(-Math.PI / 2).translate(-L / 2, h, 0), muro);
    }
    if (lucernarios) for (let x = -L / 2 + 3; x < L / 2 - 4; x += 8) k.add(M.poli, caja(4.4, 0.05, 1.1, x + 2.5, cima + 0.02, 0));
  } else if (techo === 'plano') {
    k.add(M.concreto, caja(L + 0.3, 0.3, S + 0.3, 0, h, 0));
    [[L + 0.3, 0.25, 0, S / 2 + 0.03], [L + 0.3, 0.25, 0, -S / 2 - 0.03], [0.25, S + 0.3, L / 2 + 0.03, 0], [0.25, S + 0.3, -L / 2 - 0.03, 0]].forEach(([lx, lz, x, z]) => k.add(mm, caja(lx, 0.8, lz, x, h + 0.3, z), muro));
  } else {
    if (!abierta) {
      const tri = new THREE.Shape([new THREE.Vector2(-S / 2, 0), new THREE.Vector2(S / 2, 0), new THREE.Vector2(0, r)]);
      k.add(mm, new THREE.ExtrudeGeometry(tri, { depth: L, bevelEnabled: false }).rotateY(Math.PI / 2).translate(-L / 2, h, 0), muro);
    }
    // las dos aguas: el borde de la cumbrera a h + r y el alero bajo el muro; 8 cm sobre la culata (sin caras que se crucen)
    [1, -1].forEach((s) => k.add(M.cubierta, new THREE.BoxGeometry(L + 2 * al, 0.14, ls).rotateX(s * a).translate(0, h + r - (w / 2) * Math.tan(a) + 0.08, (s * w) / 2), cubierta));
    if (monitor) {
      k.add(M.pintura, caja(L * 0.84, 0.9, 2.2, 0, h + r - 0.1, 0), '#3f464c').add(M.cubierta, caja(L * 0.84 + 0.8, 0.14, 3.4, 0, h + r + 0.8, 0), cubierta);
    } else k.add(M.pintura, caja(L + 2 * al, 0.16, 0.8, 0, h + r + 0.02, 0), '#8f989e');
    if (lucernarios) [1, -1].forEach((s) => { for (let x = -L / 2 + 3; x < L / 2 - 5; x += 8) k.add(M.poli, new THREE.BoxGeometry(4.4, 0.05, Math.min(2.2, ls * 0.16)).rotateX(s * a).translate(x + 2.2, h + r - w * 0.5 * Math.tan(a) + 0.2, s * w * 0.5)); });
    for (let i = 0; i < extractores; i++) {
      const x = -L / 2 + (L * (i + 0.5)) / extractores;
      k.add(M.inox, cil(0.32, 0.4, x, h + r + 0.1, 0, 10)).add(M.inox, new THREE.SphereGeometry(0.45, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.8, 1).translate(x, h + r + 0.48, 0));
    }
  }
  if (abierta) return puestos;
  // ventanas en franja alta (paños de vidrio de 4,8 m) en los dos muros largos
  if (ventanas && h >= 4.5) [1, -1].forEach((s) => { const n = Math.max(1, Math.floor((L - 4) / 6)), lw = (L - 4) / n; for (let i = 0; i < n; i++) k.add(M.vidrio, caja(lw - 1.2, 1.0, 0.08, -L / 2 + 2 + lw * (i + 0.5), h - 2, s * (S / 2 + 0.02))); });
  const lado = frente * (S / 2);
  // portones enrollables (lámina gris con su caja arriba) hacia los extremos del costado; muelles en el centro
  const dl = muelles ? muelles * 4.4 + 2 : 0;
  for (let i = 0; i < portones; i++) {
    const x = muelles ? (i % 2 ? 1 : -1) * (dl / 2 + (L - dl) / 4) : -L / 2 + (L * (i + 0.5)) / portones;
    k.add(M.pintura, caja(4.2, Math.min(4.6, h - 1.4), 0.1, x, 0, lado + frente * 0.04), '#a7afb5').add(M.pintura, caja(4.7, 0.55, 0.5, x, Math.min(4.6, h - 1.4), lado + frente * 0.22), '#5b636a');
  }
  if (testero) k.add(M.pintura, caja(0.1, 3.6, 4, testero * (L / 2 + 0.04), 0, 0), '#a7afb5');
  if (muelles) {
    const zA = lado + frente * 1.6;
    k.add(M.concreto, caja(dl, 1.2, 3.2, 0, 0, zA));
    k.add(M.concreto, new THREE.BoxGeometry(4.2, 0.3, 2.6).rotateZ(-Math.atan2(1.2, 4)).translate(dl / 2 + 2, 0.5, zA));   // rampa
    k.add(M.cubierta, caja(dl + 1.2, 0.15, 4.4, 0, Math.min(h - 0.6, 5.2), lado + frente * 2.2), cubierta);
    for (let i = 0; i < muelles; i++) {
      const x = -dl / 2 + 1 + 4.4 * (i + 0.5);
      k.add(M.pintura, caja(3.0, 3.2, 0.1, x, 1.2, lado + frente * 0.05), '#b9c0c5');
      k.add(M.pintura, caja(3.7, 0.5, 0.6, x, 4.4, lado + frente * 0.3), OSCURO).add(M.pintura, caja(0.35, 3.2, 0.6, x - 1.68, 1.2, lado + frente * 0.3), OSCURO).add(M.pintura, caja(0.35, 3.2, 0.6, x + 1.68, 1.2, lado + frente * 0.3), OSCURO);
      [-0.95, 0.95].forEach((d) => k.add(M.pintura, caja(0.25, 0.4, 0.16, x + d, 0.65, zA + frente * 1.66), '#1b1d1f'));
      puestos.push([x, zA + frente * 1.6, -frente * Math.PI / 2]);
    }
  }
  return puestos;
}
// Nave en el marco de un componente: el lado mayor manda la cumbrera (w en x, d en z); frente ±1 es el costado largo
// (z si w ≥ d, x si no). Devuelve los puestos de los muelles en el marco del componente
function naveEn(K, M, o) {
  const giro = o.d > o.w, ry = giro ? Math.PI / 2 : 0, c = Math.cos(ry), s = Math.sin(ry), x0 = o.x || 0, z0 = o.z || 0;
  const p = naveInd(K, M, { ...o, L: Math.max(o.w, o.d), S: Math.min(o.w, o.d), en: (g) => g.rotateY(ry).translate(x0, 0, z0) });
  return p.map(([x, z, a]) => [x * c + z * s + x0, -x * s + z * c + z0, a + ry]);
}
// corre un puesto [x, z, giro] d metros hacia donde mira (el centro del camión que recula hasta el andén)
const alejar = ([x, z, a, ...r], d) => [x + Math.cos(a) * d, z - Math.sin(a) * d, a, ...r];

// Silos metálicos con anillos, techo cónico, escalera de gato con jaula y, si tolva, fondo cónico sobre patas
function silos(K, M, lista, { r, h, tolva = false, color = '#d3d9dd', lado = 1 }) {
  lista.forEach(([x, z]) => {
    const hb = 3.2, y0 = tolva ? hb + r * 0.9 : 0.8, hs = h - y0;
    if (tolva) {
      for (let i = 0; i < 6; i++) { const t = (i / 6) * Math.PI * 2; K.add(M.pintura, cil(0.16, hb + r * 0.5, x + r * 0.82 * Math.cos(t), 0, z + r * 0.82 * Math.sin(t), 6), GALV); }
      K.add(M.cubierta, new THREE.ConeGeometry(r, r * 0.9, 24, 1, true).rotateX(Math.PI).translate(x, hb + r * 0.45, z), color);
    } else K.add(M.concreto, cil(r * 1.07, 0.8, x, 0, z, 24));
    K.add(M.cubierta, cil(r, hs, x, y0, z, 24), color);
    for (let y = y0 + 1.4; y < h - 0.3; y += 1.6) K.add(M.cubierta, cil(r + 0.05, 0.1, x, y, z, 24, r + 0.05, true), '#a8b0b5');
    K.add(M.cubierta, new THREE.ConeGeometry(r * 1.03, r * 0.5, 24).translate(x, h + r * 0.25, z), color).add(M.pintura, cil(0.5, 0.5, x, h + r * 0.5 - 0.1, z, 10), '#8d969c');
    const lx = x + lado * (r + 0.16);
    K.add(M.pintura, caja(0.06, hs - 0.4, 0.45, lx, y0 + 0.2, z), OSCURO);
    for (let y = y0 + 2.6; y < h - 0.3; y += 2) K.add(M.pintura, new THREE.TorusGeometry(0.38, 0.025, 3, 8, Math.PI).rotateX(Math.PI / 2).rotateY(lado > 0 ? Math.PI / 2 : -Math.PI / 2).translate(lx, y, z), OSCURO);
  });
}
// pasarela de rejilla sobre los silos (de a a b en z, a la altura y) con baranda, elevador de cangilones con cabezal y
// tubos de llenado a cada silo
function elevador(K, M, x, zs, r, h, { lado = -1 } = {}) {
  const z0 = Math.min(...zs), z1 = Math.max(...zs), y = h + r * 0.5 + 0.4, ze = (lado < 0 ? z0 - r - 1.8 : z1 + r + 1.8), he = y + 5;
  K.add(M.pintura, caja(0.9, 0.12, z1 - z0 + 2, x, y, (z0 + z1) / 2), '#6f777d');
  barandal(K, M, [[x - 0.45, z0 - 1], [x - 0.45, z1 + 1]], y + 0.12); barandal(K, M, [[x + 0.45, z0 - 1], [x + 0.45, z1 + 1]], y + 0.12);
  K.add(M.pintura, caja(1.4, he, 1.4, x, 0, ze), '#c7cdd1').add(M.pintura, caja(2.4, 1.8, 2.2, x, he, ze), '#aab2b8');
  zs.forEach((z) => K.add(M.pintura, barra([x + 0.65, he + 0.4, ze], [x + 0.65, h + r * 0.42, z], 0.16, 6), '#8d969c'));
  return { x, y: he + 0.9, z: ze };
}
// baranda de dos tubos con parales cada paso metros sobre la polilínea [[x, z], …] a la altura h0
function barandal(K, M, pts, h0, { alto = 1.1, color = AMARILLO, paso = 1.8 } = {}) {
  tramos(pts, (a, b, L, ry) => {
    const cx = (a[0] + b[0]) / 2, cz = (a[1] + b[1]) / 2;
    K.add(M.pintura, caja(L + 0.06, 0.06, 0.06, cx, h0 + alto - 0.06, cz, ry), color).add(M.pintura, caja(L, 0.04, 0.04, cx, h0 + alto * 0.5, cz, ry), color);
    const n = Math.max(1, Math.round(L / paso));
    for (let i = 0; i < n; i++) { const t = i / n; K.add(M.pintura, caja(0.05, alto, 0.05, a[0] + (b[0] - a[0]) * t, h0, a[1] + (b[1] - a[1]) * t), color); }
  });
  const u = pts[pts.length - 1]; K.add(M.pintura, caja(0.05, alto, 0.05, u[0], h0, u[1]), color);
}
// cerca de tubo galvanizado (corrales, mangas): cuatro largueros y parales cada 2,4 m
function talanquera(K, M, pts, { alto = 1.7, color = GALV } = {}) {
  tramos(pts, (a, b, L, ry) => {
    const cx = (a[0] + b[0]) / 2, cz = (a[1] + b[1]) / 2;
    [0.35, 0.8, 1.25, alto].forEach((y) => K.add(M.pintura, caja(L, 0.07, 0.07, cx, y - 0.07, cz, ry), color));
    const n = Math.max(1, Math.round(L / 2.4));
    for (let i = 0; i <= n; i++) { const t = i / n; K.add(M.pintura, caja(0.1, alto + 0.1, 0.1, a[0] + (b[0] - a[0]) * t, 0, a[1] + (b[1] - a[1]) * t), color); }
  });
}
// cerramiento de malla eslabonada con postes cada paso metros y tubo superior sobre la polilínea [[x, z], …]
function cercoMalla(K, M, pts, { alto = 2.2, paso = 3, color = '#5f686e', base = 0 } = {}) {
  tramos(pts, (a, b, L, ry) => {
    K.add(M.malla, new THREE.PlaneGeometry(L, alto).rotateY(ry).translate((a[0] + b[0]) / 2, base + alto / 2, (a[1] + b[1]) / 2));
    K.add(M.pintura, barra([a[0], base + alto, a[1]], [b[0], base + alto, b[1]], 0.03, 5), color);
    if (base) K.add(M.concreto, caja(L, base, 0.22, (a[0] + b[0]) / 2, 0, (a[1] + b[1]) / 2, ry));
    const n = Math.max(1, Math.round(L / paso));
    for (let i = 0; i < n; i++) { const t = i / n; K.add(M.pintura, cil(0.045, alto + base + 0.12, a[0] + (b[0] - a[0]) * t, 0, a[1] + (b[1] - a[1]) * t, 6), color); }
  });
  const u = pts[pts.length - 1]; K.add(M.pintura, cil(0.05, alto + base + 0.12, u[0], 0, u[1], 6), color);
}
// polilínea del modelo [[u, v], …] partida en trozos de ~3 m, sin los que caen sobre una vía (el cerco se abre en los
// cruces): devuelve listas de puntos [x, z] del marco de three
function cercoAbierto(poly, vias, { cerrado = true, paso = 3 } = {}) {
  const out = []; let act = [];
  const pts = cerrado ? [...poly, poly[0]] : poly;
  for (let i = 1; i < pts.length; i++) {
    const [a, b] = [pts[i - 1], pts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.round(L / paso));
    for (let k = 0; k < n; k++) {
      const p = [a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n], q = [a[0] + ((b[0] - a[0]) * (k + 1)) / n, a[1] + ((b[1] - a[1]) * (k + 1)) / n], m = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
      if (vias.some((v) => distLinea(m, v.puntos) < v.ancho / 2 + 1.2)) { if (act.length > 1) out.push(act); act = []; continue; }
      if (!act.length) act.push([p[0], -p[1]]);
      act.push([q[0], -q[1]]);
    }
  }
  if (act.length > 1) out.push(act);
  return out;
}
// vías del modelo [{ puntos: [[u, v], …], ancho }] en el kit de piso: asfalto, bordillos de concreto (abiertos en los
// cruces) y raya de eje discontinua en las de 7 m o más; h: altura de la carpeta
function viasEn(KP, M, vias, { h = 0.12, dentroDe = null, rayas = true } = {}) {
  vias.forEach((v) => KP.add(v.material || M.asfalto, cinta(v.puntos, v.ancho, h)));
  const cruce = (p, yo) => vias.some((o) => o !== yo && distLinea(p, o.puntos) < o.ancho / 2 + 1.2);
  vias.forEach((v) => {
    if (v.sinBordillo) return;
    tramos(v.puntos.map(([u, w]) => [u, -w]), (a, b, L, ry) => {
      const d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L], n = Math.max(1, Math.round(L / 4)), lp = L / n;
      for (let i = 0; i < n; i++) [-1, 1].forEach((s) => {
        const t = (i + 0.5) * lp, m = [a[0] + d[0] * t - d[1] * s * (v.ancho / 2 + 0.1), a[1] + d[1] * t + d[0] * s * (v.ancho / 2 + 0.1)], mm = [m[0], -m[1]];
        if (cruce(mm, v) || (dentroDe && !dentro(mm, dentroDe))) return;
        KP.add(M.concreto, caja(lp + 0.02, 0.17, 0.2, m[0], h - 0.05, m[1], ry));
      });
    });
    if (rayas && v.ancho >= 7) aLoLargo(v.puntos, 8, 0, 3).forEach(([x, y, ang]) => { if (!cruce([x, y], v)) KP.add(M.pintura, caja(3.2, 0.015, 0.15, x, h + 0.005, -y, ang), '#f1efe6'); });
  });
}

// ---------------------------------------------------------------- vehículos, maquinaria y ganado instanciados
// Cada tipo es una geometría unida con color por vértice (carrocería, chasís, llantas, vidrios) y otra con la parte
// pintada (cabina, tanque, volco o carrocería del tractor), que toma el color de cada instancia: dos llamadas por tipo
const GV = {};
function geoVehiculo(t) {
  if (GV[t]) return GV[t];
  const P = [], Q = [], neg = '#1b1d1f', vid = '#26313a', gris = '#5f666c', bl = '#eef0ef', Y = '#efb21a';
  const rueda = (x, z, r = 0.5, a = 0.34) => P.push([new THREE.CylinderGeometry(r, r, a, 12).rotateX(Math.PI / 2).translate(x, r, z), neg]);
  const ruedas = (xs, r, a, z = 1.05) => xs.forEach((x) => { rueda(x, z, r, a); rueda(x, -z, r, a); });
  // cabina con el frente en xf: perfil extruido con el parabrisas inclinado, vidrios laterales y bómper
  const cab = (xf, alto = 3.0, larga = 2.1) => {
    Q.push(new THREE.ExtrudeGeometry(new THREE.Shape([[xf - larga, 0.95], [xf, 0.95], [xf + 0.05, 1.8], [xf - 0.28, alto], [xf - larga, alto]].map(([x, y]) => new THREE.Vector2(x, y))), { depth: 2.4, bevelEnabled: false }).translate(0, 0, -1.2));
    P.push([new THREE.BoxGeometry(0.06, 1.0, 2.2).rotateZ(0.26).translate(xf - 0.08, 2.4, 0), vid], [new THREE.BoxGeometry(larga * 0.5, 0.7, 2.42).translate(xf - larga * 0.45, 2.45, 0), vid], [new THREE.BoxGeometry(0.22, 0.42, 2.46).translate(xf + 0.08, 1.05, 0), gris]);
  };
  const chasis = (x0, x1) => P.push([caja(x1 - x0, 0.3, 1.0, (x0 + x1) / 2, 0.6, 0), neg]);
  if (t === 'furgon') { cab(4.3); chasis(-4.2, 4.2); P.push([caja(6.3, 2.75, 2.5, -1.15, 1.15, 0), bl], [caja(0.4, 0.95, 1.7, 2.2, 3.0, 0), '#c9ced1']); ruedas([3.4, -2.2, -3.3], 0.5, 0.34); }
  else if (t === 'tracto') { cab(8.2, 3.3, 2.3); chasis(3.2, 8.1); P.push([caja(13.6, 2.85, 2.55, -1.3, 1.3, 0), bl], [caja(13.6, 0.3, 1.1, -1.3, 1.0, 0), neg], [caja(0.6, 0.9, 2.3, 5.65, 3.3, 0), '#d5d9dc']); ruedas([7.1, 4.9, 3.8, -5.6, -6.7, -7.8], 0.5, 0.36); }
  else if (t === 'cisterna') { cab(4.25); chasis(-4.2, 4.2); Q.push(new THREE.CylinderGeometry(1.1, 1.1, 5.8, 18).rotateZ(Math.PI / 2).translate(-1.3, 2.25, 0)); P.push([caja(5.6, 0.08, 0.6, -1.3, 3.36, 0), gris], ...[-3.5, -1.3, 0.9].map((x) => [caja(0.4, 0.45, 1.5, x, 0.85, 0), gris])); ruedas([3.4, -2.2, -3.3], 0.5, 0.34); }
  else if (t === 'volqueta') { cab(4.0); chasis(-3.9, 3.9); Q.push(caja(5.4, 0.2, 2.4, -1.1, 1.3, 0), caja(5.4, 1.3, 0.12, -1.1, 1.5, 1.14), caja(5.4, 1.3, 0.12, -1.1, 1.5, -1.14), caja(0.15, 1.7, 2.4, 1.6, 1.3, 0), caja(0.12, 1.3, 2.4, -3.75, 1.5, 0)); ruedas([3.1, -1.8, -3.0], 0.5, 0.34); }
  else if (t === 'retro') {
    P.push([caja(3.4, 1.0, 1.9, 0, 0.85, 0), Y], [caja(1.6, 0.75, 1.2, 1.0, 1.85, 0), Y], [caja(1.5, 1.75, 1.8, -0.75, 1.85, 0), Y], [caja(1.54, 0.95, 1.84, -0.75, 2.5, 0), vid]);
    rueda(-0.9, 1.05, 0.8, 0.5); rueda(-0.9, -1.05, 0.8, 0.5); rueda(1.3, 0.95, 0.55, 0.36); rueda(1.3, -0.95, 0.55, 0.36);
    P.push([viga([0.6, 1.9, 0.98], [2.5, 0.9, 0.98], 0.18, 0.22), Y], [viga([0.6, 1.9, -0.98], [2.5, 0.9, -0.98], 0.18, 0.22), Y], [caja(0.9, 0.8, 2.3, 2.85, 0.1, 0), Y]);
    P.push([viga([-1.7, 1.7, 0], [-2.9, 3.5, 0], 0.32, 0.4), Y], [viga([-2.9, 3.5, 0], [-3.8, 1.0, 0], 0.26, 0.32), Y], [caja(0.6, 0.6, 0.7, -3.85, 0.4, 0), gris]);
    P.push([viga([-1.6, 1.2, 1.1], [-1.9, 0.1, 1.25], 0.2, 0.2), neg], [viga([-1.6, 1.2, -1.1], [-1.9, 0.1, -1.25], 0.2, 0.2), neg]);
  } else if (t === 'excavadora') {
    P.push([caja(4.4, 0.85, 0.7, 0, 0, 1.05), neg], [caja(4.4, 0.85, 0.7, 0, 0, -1.05), neg], [caja(1.8, 0.4, 1.4, 0, 0.8, 0), neg]);
    P.push([caja(3.0, 1.15, 2.5, -0.5, 1.2, 0), Y], [caja(0.7, 1.05, 2.5, -2.3, 1.2, 0), gris], [caja(1.0, 1.55, 0.95, 0.55, 2.35, 0.75), Y], [caja(1.02, 0.85, 0.97, 0.55, 2.95, 0.75), vid]);
    P.push([viga([0.9, 2.1, -0.2], [3.5, 4.5, -0.2], 0.45, 0.55), Y], [viga([3.5, 4.5, -0.2], [4.9, 1.6, -0.2], 0.35, 0.42), Y], [new THREE.BoxGeometry(0.9, 0.8, 1.0).rotateZ(0.5).translate(5.0, 1.1, -0.2), gris]);
  } else if (t === 'motoniveladora') {
    P.push([viga([3.4, 1.1, 0], [-0.4, 1.7, 0], 0.55, 0.5), Y], [caja(2.6, 1.4, 2.2, -2.6, 0.9, 0), Y], [caja(1.6, 1.75, 1.9, -0.9, 1.65, 0), Y], [caja(1.62, 1.0, 1.92, -0.9, 2.3, 0), vid]);
    P.push([new THREE.BoxGeometry(0.18, 0.6, 3.6).rotateY(0.45).translate(1.0, 0.45, 0), gris], [cil(0.85, 0.1, 1.0, 0.85, 0, 16), neg]);
    ruedas([3.3], 0.62, 0.36, 0.95); ruedas([-1.9, -3.1], 0.62, 0.4, 1.05);
  } else if (t === 'tractor') {
    Q.push(caja(2.1, 0.95, 0.9, 0.75, 0.85, 0), caja(1.4, 0.9, 1.1, -0.75, 0.8, 0), caja(1.7, 0.12, 1.7, -0.75, 2.85, 0));
    P.push([caja(1.3, 1.15, 1.3, -0.75, 1.7, 0), vid], [cil(0.05, 0.9, 1.3, 1.8, 0.3, 6), neg]);
    ruedas([-0.9], 0.85, 0.5, 0.95); ruedas([1.3], 0.5, 0.3, 0.75);
  } else if (t === 'volteadora') {
    [-2.45, 2.45].forEach((z) => P.push([caja(3.0, 0.7, 0.5, 0, 0, z), neg], [caja(1.0, 2.3, 0.35, 0, 0.7, z), Y]));
    P.push([caja(1.3, 0.5, 5.4, 0, 3.0, 0), Y], [caja(1.2, 1.4, 1.2, 0, 3.5, 2.0), Y], [caja(1.22, 0.8, 1.22, 0, 3.95, 2.0), vid], [new THREE.CylinderGeometry(0.55, 0.55, 4.4, 12).rotateX(Math.PI / 2).translate(0, 0.75, 0), gris]);
  }
  GV[t] = { base: pintada(P), pintada: Q.length ? unir(Q) : null };
  return GV[t];
}
const PINTURA_V = { furgon: ['#d8dde0', '#b8302a', '#2d5aa0', '#f1f1ee'], tracto: ['#c0392b', '#f1f1ee', '#1f4f8f', '#3a3f44'], cisterna: ['#eef0ef'], volqueta: ['#e07a1f', '#c8372d'], tractor: ['#3c7d3a', '#c8372d', '#3c7d3a'] };
// lista: [[x, y, giro, tipo, color?]] en el marco del padre (V), con .h para subirlos a un andén o una plataforma
function flota(lista) {
  const g = new THREE.Group(), M = mats(), por = {}, m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), uno = new THREE.Vector3(1, 1, 1);
  lista.forEach((it) => (por[it[3]] || (por[it[3]] = [])).push(it));
  Object.entries(por).forEach(([t, its]) => {
    const G = geoVehiculo(t), pal = PINTURA_V[t] || ['#d8dde0'];
    [[G.base, M.pintura], [G.pintada, M.carroceria]].forEach(([geo, m], j) => {
      if (!geo) return;
      const im = new THREE.InstancedMesh(geo, m, its.length);
      its.forEach((it, i) => { q.setFromAxisAngle(EJE_Y, it[2]); m4.compose(V(it[0], it[1], it.h || 0), q, uno); im.setMatrixAt(i, m4); if (j) im.setColorAt(i, C(it[4] || pal[i % pal.length])); });
      im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere(); g.add(im);
    });
  });
  return g;
}
// ganado cebú (de cuerpo claro y giba) en una sola malla: el color de cada res va en la instancia; el de la geometría
// solo oscurece patas, hocico y cola
let geoRes = null;
const PELO = ['#ece8e0', '#dcd6ca', '#c9c2b5', '#b3ab9e', '#efe9de', '#8c6c50', '#5c4535', '#2c2724', '#c9a274'];
function ganado(lista, semilla = 5) {
  geoRes = geoRes || pintada([
    [new THREE.SphereGeometry(1, 10, 7).scale(0.95, 0.43, 0.33).translate(0, 1.05, 0), '#ffffff'],
    [new THREE.SphereGeometry(1, 8, 6).scale(0.26, 0.22, 0.17).translate(0.48, 1.42, 0), '#f2f2f2'],
    [new THREE.BoxGeometry(0.55, 0.3, 0.26).rotateZ(-0.7).translate(1.12, 1.12, 0), '#f0f0f0'],
    [new THREE.BoxGeometry(0.24, 0.2, 0.22).translate(1.32, 0.86, 0), '#4a4a4a'],
    [new THREE.BoxGeometry(0.16, 0.06, 0.62).translate(1.02, 1.24, 0), '#d8d8d8'],
    [new THREE.BoxGeometry(0.42, 0.34, 0.07).translate(0.92, 0.82, 0), '#e8e8e8'],
    ...[[0.62, 0.18], [0.62, -0.18], [-0.6, 0.17], [-0.6, -0.17]].map(([x, z]) => [new THREE.BoxGeometry(0.13, 0.78, 0.13).translate(x, 0.39, z), '#9a9a9a']),
    [new THREE.BoxGeometry(0.05, 0.62, 0.05).rotateZ(0.2).translate(-0.98, 0.78, 0), '#5a5a5a'],
  ]);
  const r = azar(semilla), im = new THREE.InstancedMesh(geoRes, mats().res, Math.max(1, lista.length)), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3();
  lista.forEach(([x, z, a], i) => { const k = 0.88 + r() * 0.22; q.setFromAxisAngle(EJE_Y, a); m4.compose(new THREE.Vector3(x, 0, z), q, s.set(k, k, k)); im.setMatrixAt(i, m4); im.setColorAt(i, C(PELO[Math.floor(r() * PELO.length)])); });
  im.count = lista.length; im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere();
  return im;
}
// operarios: con bata blanca (planta de alimentos), con chaleco naranja o amarillo (patio y obra), de dotación azul
const ROPA = { bata: { camisa: '#f4f4f0', pantalon: '#e6e6e2' }, chaleco: { camisa: '#f08a24', pantalon: '#2b3a55' }, amarillo: { camisa: '#e9d22e', pantalon: '#2b3a55' }, azul: { camisa: '#2e5fa8', pantalon: '#2b3a55' }, vaquero: { camisa: '#c9b38a', pantalon: '#3a4a6b' } };

// ---------------------------------------------------------------- PTAR central (UASB + filtros percoladores)
// ~ 176 × 112 m dentro de un predio de 1,9 ha: en el marco local u va a lo largo del lote y v a lo ancho; el agua entra
// por u negativo (estación de llegada), pasa por el pretratamiento, los UASB, los filtros y los sedimentadores, y sale por u
// positivo a la laguna de pulimento
export function ptar(cx, cy, rumbo = 0, { reactores = 3, filtros = 2 } = {}) {
  const raiz = marco(cx, cy, rumbo), M = mats(), r = azar(83);
  const piso = capa(raiz, 'piso'), obras = capa(raiz, 'obras'), verde = capa(raiz, 'verde');
  const KP = kit(), K = kit(), Z = (v) => -v, rect = (u0, v0, u1, v1) => [[u0, v0], [u1, v0], [u1, v1], [u0, v1]];
  // --- piso: césped entre unidades, plataformas de concreto, vías con bordillo y raya, y la grava de la antorcha
  KP.add(M.cesped, losa(rect(-88, -56, 88, 56), 0.04));
  [rect(-85, -9, -55, 11), rect(-52, -1, 17, 44), rect(23, 17, 61, 37), rect(22, -11, 58, 14), rect(71, -38, 86, -1)].forEach((p) => KP.add(M.patio, losa(p, 0.08)));
  KP.add(M.grava, losa(rect(-72, 31, -60, 41), 0.08));
  const vias = [{ puntos: [[-96, -44], [88, -44]], ancho: 7 }, { puntos: [[66, -44], [66, 48]], ancho: 6 }, { puntos: [[66, 48], [-62, 48]], ancho: 5 }];
  viasEn(KP, M, vias, { dentroDe: rect(-88, -56, 88, 56).map(([u, v]) => [u, v]) });
  KP.add(M.afirmado, losa(rect(-104, -47.5, -96, -40.5), 0.1));
  // --- pretratamiento: cámara de llegada, canal con rejillas, desarenador de dos canales y canaleta Parshall
  K.add(M.concreto, caja(3.2, 2.6, 4, -84.6, 0, Z(0))).add(M.concreto, caja(26, 1.6, 6.4, -70, 0, Z(0)));
  [-1.6, 1.6].forEach((v) => K.add(M.aguaTurbia, caja(24.6, 0.06, 2.6, -70, 1.42, Z(v))));
  K.add(M.concreto, caja(26, 0.4, 0.3, -70, 1.6, 0));
  for (let i = 0; i < 18; i++) K.add(M.pintura, new THREE.BoxGeometry(0.05, 1.3, 0.05).rotateZ(0.3).translate(-78, 1.25, Z(-2.9 + i * 0.34)), OSCURO);
  K.add(M.pintura, caja(1.2, 1.4, 6.6, -76.4, 1.6, 0), '#56606a');
  barandal(K, M, [[-83, Z(3.4)], [-57, Z(3.4)]], 0); barandal(K, M, [[-83, Z(-3.4)], [-57, Z(-3.4)]], 0);
  K.add(M.concreto, caja(3, 3, 3, -50, 0, Z(8)));
  // --- reactores UASB: concreto, losa de cubierta con campanas de gas, pasarela con baranda, escalera de gato con jaula
  const xr = Array.from({ length: reactores }, (_, i) => -36 + i * 21);
  xr.forEach((u) => {
    const z = Z(10);
    K.add(M.concreto, cil(8, 6.5, u, 0, z, 36)).add(M.concreto, cil(8.15, 0.3, u, 6.4, z, 36));
    [-3.6, 0, 3.6].forEach((d) => K.add(M.pintura, caja(5.2, 0.7, 1.3, u, 6.7, z + d), '#7d868c'));
    barandal(K, M, anillo(u, z, 7.85, 24), 6.7);
    K.add(M.pintura, caja(0.06, 6.4, 0.45, u + 8.18, 0.3, z), OSCURO);
    for (let y = 2.6; y < 6.6; y += 1.6) K.add(M.pintura, new THREE.TorusGeometry(0.38, 0.025, 3, 8, Math.PI).rotateX(Math.PI / 2).rotateY(Math.PI / 2).translate(u + 8.18, y, z), OSCURO);
    K.add(M.pintura, barra([u, 7.4, z], [u, 7.4, Z(17.5)], 0.14), AMARILLO);
    K.add(M.pintura, barra([u, 0.6, Z(0.5)], [u, 0.6, Z(2.3)], 0.2), '#4b5a63');
  });
  // tubería de afluente (de la caja de reparto a los reactores), efluente a los filtros y biogás a la antorcha
  K.add(M.pintura, barra([-50, 0.6, Z(0.5)], [xr[xr.length - 1] + 0.3, 0.6, Z(0.5)], 0.22), '#4b5a63').add(M.pintura, barra([-58, 0.6, Z(0)], [-50, 0.6, Z(0.5)], 0.22), '#4b5a63');
  K.add(M.pintura, barra([xr[0] - 4, 0.6, Z(19)], [12, 0.6, Z(19)], 0.2), '#4b5a63');
  K.add(M.pintura, barra([xr[0], 7.4, Z(17.5)], [xr[xr.length - 1], 7.4, Z(17.5)], 0.14), AMARILLO);
  [[[xr[0], 7.4, Z(17.5)], [-46, 7.4, Z(17.5)]], [[-46, 7.4, Z(17.5)], [-46, 1.0, Z(17.5)]], [[-46, 1.0, Z(17.5)], [-46, 1.0, Z(36)]], [[-46, 1.0, Z(36)], [-64.5, 1.0, Z(36)]]].forEach(([a, b]) => K.add(M.pintura, barra(a, b, 0.14), AMARILLO));
  for (let v = 20; v < 36; v += 4) K.add(M.concreto, caja(0.5, 0.8, 0.5, -46, 0, Z(v)));
  // antorcha de biogás: trampa de condensado, chimenea con cortavientos y llama
  K.add(M.pintura, cil(0.6, 1.6, -63, 0, Z(36), 12), '#9aa3a9').add(M.pintura, cil(0.25, 8.5, -66, 0, Z(36), 10), '#a6aeb3').add(M.pintura, cil(0.45, 1.3, -66, 8.5, Z(36), 12), OSCURO);
  K.add(M.llama, new THREE.ConeGeometry(0.42, 1.9, 8).translate(-66, 10.75, Z(36)));
  // --- filtros percoladores: muro de concreto, lecho de piedra irregular y brazo distribuidor (gira: girarBrazos)
  const brazos = [], geoBrazo = pintada([[caja(21, 0.22, 0.32, 0, 4.75, 0), '#5d6a72'], [caja(0.32, 0.22, 21, 0, 4.75, 0), '#5d6a72'], [cil(0.45, 1.4, 0, 4.2, 0, 12), '#7d878d'], ...[-9, -6, -3, 3, 6, 9].flatMap((d) => [[caja(0.12, 0.25, 0.12, d, 4.5, 0.2), '#3f474d'], [caja(0.12, 0.25, 0.12, 0.2, 4.5, d), '#3f474d']])]);
  const lecho = (() => { const g = new THREE.RingGeometry(0.6, 10.75, 48, 9).rotateX(-Math.PI / 2), p = g.attributes.position, ra = azar(17); for (let i = 0; i < p.count; i++) p.setY(i, (ra() - 0.5) * 0.18); g.computeVertexNormals(); return g; })();
  for (let i = 0; i < filtros; i++) {
    const u = -26 + i * 28, z = Z(31);
    K.add(M.concreto, cil(11, 4.5, u, 0, z, 40, 11, true)).add(M.concreto, new THREE.TorusGeometry(11, 0.18, 6, 48).rotateX(Math.PI / 2).translate(u, 4.5, z));
    K.add(M.roca, lecho.clone().translate(u, 4.05, z));
    K.add(M.pintura, caja(0.06, 4.2, 0.45, u - 11.15, 0.3, z), OSCURO);
    const b = new THREE.Mesh(geoBrazo, M.pintura); b.name = 'brazo'; b.position.set(u, 0, z); b.rotation.y = i * 0.6; b.receiveShadow = true; obras.add(b); brazos.push(b);
  }
  K.add(M.pintura, barra([-26 + (filtros - 1) * 28 + 11, 0.6, Z(31)], [24, 0.6, Z(31)], 0.2), '#4b5a63');
  // --- sedimentadores secundarios: tanque con agua clara, canaleta perimetral, columna central y puente barredor
  [[32, 27], [52, 27]].forEach(([u, v], i) => {
    const z = Z(v);
    K.add(M.concreto, cil(8, 3.6, u, 0, z, 36, 8, true)).add(M.concreto, new THREE.TorusGeometry(8, 0.2, 6, 40).rotateX(Math.PI / 2).translate(u, 3.6, z));
    K.add(M.agua, new THREE.CircleGeometry(7.9, 36).rotateX(-Math.PI / 2).translate(u, 3.25, z)).add(M.concreto, new THREE.TorusGeometry(7.2, 0.22, 4, 36).rotateX(Math.PI / 2).translate(u, 3.3, z));
    K.add(M.concreto, cil(0.9, 4.1, u, 0, z, 14));
    const ang = 0.8 + i * 2.1, ex = u + Math.cos(ang) * 8.2, ez = z - Math.sin(ang) * 8.2;
    K.add(M.pintura, viga([u, 4.25, z], [ex, 4.25, ez], 1.0, 0.45), AMARILLO);
    barandal(K, M, [[u + Math.sin(ang) * 0.5, z + Math.cos(ang) * 0.5], [ex + Math.sin(ang) * 0.5, ez + Math.cos(ang) * 0.5]], 4.45);
    K.add(M.pintura, caja(0.8, 0.9, 0.8, ex, 3.6, ez), '#5d6a72');
  });
  K.add(M.pintura, barra([40, 0.4, Z(27)], [44, 0.4, Z(27)], 0.18), '#4b5a63');
  // salida enterrada hacia la laguna: cámaras de inspección con tapa y estructura de descarga
  [[61, 26], [76, 22], [85, 20]].forEach(([u, v]) => K.add(M.concreto, cil(0.9, 0.25, u, 0, Z(v), 14)).add(M.pintura, cil(0.6, 0.04, u, 0.25, Z(v), 14), '#3a3f44'));
  K.add(M.concreto, caja(3, 1.4, 3, 85, 0, Z(20)));
  // --- lechos de secado de lodos: muretes, lodo y, en dos de ellos, cubierta de policarbonato sobre marcos
  [[32, -3.5], [48, -3.5], [32, 7.5], [48, 7.5]].forEach(([u, v], i) => {
    const z = Z(v);
    [[14, 0.25, 0, 4.5], [14, 0.25, 0, -4.5], [0.25, 9, 7, 0], [0.25, 9, -7, 0]].forEach(([w, d, du, dz]) => K.add(M.concreto, caja(w, 1.0, d, u + du, 0, z + dz)));
    K.add(M.lodo, losa([[u - 6.85, v - 4.35], [u + 6.85, v - 4.35], [u + 6.85, v + 4.35], [u - 6.85, v + 4.35]], 0.62));
    if (i < 2) {
      [[-6.8, -4.3], [6.8, -4.3], [-6.8, 4.3], [6.8, 4.3], [0, -4.3], [0, 4.3]].forEach(([du, dz]) => K.add(M.pintura, caja(0.12, 3.4 + dz * 0.08, 0.12, u + du, 0, z + dz), GALV));
      K.add(M.poli, new THREE.BoxGeometry(14.6, 0.05, 9.6).rotateX(-0.08).translate(u, 3.45, z));
    }
  });
  K.add(M.pintura, barra([32, 0.5, Z(19)], [32, 0.5, Z(12.5)], 0.15), '#6b4f3a').add(M.pintura, barra([52, 0.5, Z(19)], [48, 0.5, Z(12.5)], 0.15), '#6b4f3a');
  // --- edificio de operación y laboratorio: pañete con zócalo, ventanas en franja, cubierta plana, aire acondicionado
  const be = [78, -25], bz = Z(be[1]);
  K.add(M.muro, caja(12, 4.2, 22, be[0], 0, bz), '#f2efe7').add(M.ladrillo, caja(12.08, 1.0, 22.08, be[0], 0, bz));
  K.add(M.concreto, caja(12.6, 0.3, 22.6, be[0], 4.2, bz));
  [[12.6, 0.2, 0, 11.2], [12.6, 0.2, 0, -11.2], [0.2, 22.6, 6.2, 0], [0.2, 22.6, -6.2, 0]].forEach(([w, d, du, dz]) => K.add(M.muro, caja(w, 0.6, d, be[0] + du, 4.5, bz + dz), '#e4ded2'));
  for (let i = 0; i < 5; i++) [-1, 1].forEach((s) => K.add(M.vidrio, caja(0.08, 1.3, 3, be[0] + s * 6.02, 1.5, bz - 8.8 + i * 4.4)));
  K.add(M.pintura, caja(0.08, 2.3, 1.8, be[0] - 6.04, 0, bz), '#6d4a33').add(M.concreto, caja(2.4, 0.2, 3.2, be[0] - 7, 2.8, bz));
  [[-3, -6], [2.5, 4]].forEach(([du, dz]) => K.add(M.pintura, caja(1.6, 0.9, 1.0, be[0] + du, 4.5, bz + dz), '#d9dcdc'));
  // --- cerramiento de malla sobre sardinel con el portón abierto en la vía de entrada
  cercoAbierto(rect(-88, -56, 88, 56), vias).forEach((pts) => cercoMalla(K, M, pts, { base: 0.3 }));
  K.en(obras); KP.en(piso, false);
  girarBrazos(brazos);
  // --- vehículos, gente y luces
  obras.add(flota([[-62, -42.2, 0, 'cisterna', '#e88a1a'], [-30, -45.8, Math.PI, 'volqueta']]));
  obras.add(carros([[74, -5, Math.PI / 2], [77, -5, Math.PI / 2, '#f4f4f2'], [80, -5, -Math.PI / 2], [83.5, -5, Math.PI / 2]], { semilla: 31 }));
  const op = (u, v, a, ropa, h = 0) => Object.assign([u, v, a, ROPA[ropa]], { h });
  obras.add(gente([op(-73, 4.3, 0.2, 'chaleco'), op(-66, 4.0, 2.9, 'amarillo'), op(-15, 16.6, 1.4, 'chaleco', 6.7), op(-13.5, 16.8, -1.8, 'azul', 6.7), op(31, -9.5, 0.4, 'chaleco'), op(34, -9.2, 2.5, 'chaleco'),
    op(70.8, -20, -1.6, 'bata'), op(70.9, -18.8, 1.5, 'azul'), op(-61, -37.4, 2.2, 'chaleco'), op(34.9, 30, 0.8, 'azul', 4.7), op(43, 25.5, 0.3, 'amarillo')], { semilla: 17 }));
  obras.add(postes([...aLoLargo([[-86, -48.6], [86, -48.6]], 28).map(([u, v]) => [u, v]), ...aLoLargo([[70, -36], [70, 46]], 26).map(([u, v]) => [u, v])], 8));
  // --- verde: barrera de árboles afuera del cerco (la primera, que brota), palmas y jardín frente al edificio
  const borde = [];
  for (let u = -84; u <= 84; u += 7) borde.push([u, 61], [u, -61]);
  for (let v = -54; v <= 54; v += 8) borde.push([-93, v], [93, v]);
  verde.add(arboles(borde.filter(([u, v]) => !(u < -86 && Math.abs(v + 44) < 7)).map(([u, v]) => [u + (r() - 0.5) * 2, v + (r() - 0.5) * 1.5]), { alto: 10, semilla: 81, especie: 'mixto' }));
  verde.add(palmas([[86, -40], [86, -12], [72.5, -40], [86, 5], [86, 14]], { alto: 7, semilla: 23 }));
  const jp = sembrar([[69.8, -35], [71.6, -35], [71.6, -15], [69.8, -15]], 30, 0.9, 41);
  verde.add(matas(jp.filter((_, i) => i % 2), { tipo: 'cordyline', semilla: 41 }), matas(jp.filter((_, i) => !(i % 2)), { tipo: 'heliconia', alto: 1.4, semilla: 42 }));
  raiz.userData.partes = { piso, obras, verde };
  raiz.userData.aModelo = aModelo(raiz);
  raiz.userData.contorno = [[-95, -63], [95, -63], [95, 63], [-95, 63]].map(([u, v]) => raiz.userData.aModelo(u, v));
  raiz.userData.entrada = raiz.userData.aModelo(-86, 0); raiz.userData.salida = raiz.userData.aModelo(86, 20);
  return raiz;
}
// El brazo distribuidor de los filtros percoladores gira (unas 2 vueltas por minuto) mientras la planta se ve y está
// cerca: la función de cuadro se registra la primera vez que el brazo se dibuja (la pieza no conoce la escena) y devuelve
// false cuando la capa está oculta o la cámara lejos, para no pedir cuadros. La sombra no gira: el brazo no la proyecta
function girarBrazos(brazos) {
  if (reducedMotion || !brazos.length) return;
  const b0 = brazos[0], w = new THREE.Vector3();
  let listo = false;
  const visible = () => { for (let o = b0; o; o = o.parent) if (!o.visible) return false; return true; };
  b0.onBeforeRender = () => {
    const st = engine.active;
    if (listo || !st?.onFrame) return;
    listo = true;
    st.onFrame((dt) => {
      if (!b0.parent || !visible()) return false;
      b0.getWorldPosition(w);
      if (st.camera.position.distanceTo(w) > 1500) return false;
      brazos.forEach((b) => { b.rotation.y += dt * 0.22; });
      return true;
    });
  };
}

// ---------------------------------------------------------------- ampliación de la PTAP (módulo de ~20 L/s)
// En fila de occidente a oriente: floculador de pantallas, sedimentador de placas inclinadas y cuatro filtros rápidos con
// su galería de tubos y válvulas; pasarela en la corona con baranda amarilla y escalera; edificio de químicos con los
// tanques de dosificación; tubería de entrada y de agua tratada hacia la planta de hoy (al occidente, que no se cerca)
export function moduloPTAP(cx, cy, rumbo = 0) {
  const raiz = marco(cx, cy, rumbo), M = mats(), K = kit();
  const obras = capa(raiz, 'obras'), Z = (v) => -v, H = 4.2;
  K.add(M.patio, losa([[-28, -15], [31, -15], [31, 15], [-28, 15]], 0.15)).add(M.concreto, caja(59.2, 0.15, 0.3, 1.5, 0, Z(-15.1))).add(M.concreto, caja(59.2, 0.15, 0.3, 1.5, 0, Z(15.1)));
  // tanques de concreto (muros de 0,3 m) con su lámina de agua
  const tanque = (u0, u1, v0, v1, agua, nivel) => {
    const uc = (u0 + u1) / 2, vc = (v0 + v1) / 2, lu = u1 - u0, lv = v1 - v0;
    K.add(M.concreto, caja(lu, H, 0.3, uc, 0, Z(v0 + 0.15))).add(M.concreto, caja(lu, H, 0.3, uc, 0, Z(v1 - 0.15))).add(M.concreto, caja(0.3, H, lv, u0 + 0.15, 0, Z(vc))).add(M.concreto, caja(0.3, H, lv, u1 - 0.15, 0, Z(vc)));
    if (agua) K.add(agua, caja(lu - 0.6, 0.05, lv - 0.6, uc, nivel, Z(vc)));
  };
  // floculador hidráulico: siete pantallas alternas (el agua va en zigzag)
  tanque(-24, -8, -5, 5, M.agua, 3.4);
  for (let i = 1; i < 8; i++) { const u = -24 + i * 2, abajo = i % 2; K.add(M.concreto, caja(0.15, H - 0.5, 8.2, u, 0, Z(abajo ? -0.9 : 0.9))); }
  // sedimentador de placas a 60°: placas de PVC cada 0,25 m que asoman sobre el agua y canaletas de recolección
  tanque(-7, 10, -5, 5, M.agua, 3.55);
  for (let u = -6.2; u < 9.4; u += 0.25) K.add(M.pintura, new THREE.BoxGeometry(0.02, 1.1, 9.0).rotateZ(Math.PI / 6).translate(u, 3.35, 0), '#e9eef0');
  [-4.5, -1.5, 1.5, 4.5, 7.5].forEach((u) => K.add(M.concreto, caja(0.4, 0.3, 9.4, u, 3.75, 0)));
  // filtros rápidos: cuatro celdas (dos con agua sobre el lecho y dos en lavado, con la antracita a la vista) y canal central
  tanque(11, 28, -5, 5, null, 0);
  K.add(M.concreto, caja(16.4, H, 0.3, 19.5, 0, Z(-0.6))).add(M.concreto, caja(16.4, H, 0.3, 19.5, 0, Z(0.6))).add(M.concreto, caja(0.3, H, 9.4, 19.5, 0, 0));
  [[15.25, -2.8, M.agua], [23.75, -2.8, M.antracita], [15.25, 2.8, M.antracita], [23.75, 2.8, M.agua]].forEach(([u, v, m]) => K.add(m, caja(7.9, 0.05, 3.9, u, m === M.agua ? 3.5 : 2.6, Z(v))));
  K.add(M.agua, caja(15.8, 0.05, 0.9, 19.5, 3.1, 0));
  // galería de tubos al sur de los filtros: tres colectores con válvulas de volante y bajantes a cada celda
  [[0.9, 0.3, '#2f6fb3'], [1.8, 0.25, '#2f6fb3'], [2.6, 0.18, '#3d8a55']].forEach(([y, rr, col]) => K.add(M.pintura, barra([10, y, Z(-7)], [29, y, Z(-7)], rr, 10), col));
  [13, 17.5, 21.5, 26].forEach((u) => {
    K.add(M.pintura, barra([u, 0.9, Z(-7)], [u, 0.9, Z(-5.2)], 0.2, 8), '#2f6fb3').add(M.pintura, barra([u, 2.6, Z(-7)], [u, 4.6, Z(-7)], 0.14, 8), '#3d8a55').add(M.pintura, barra([u, 4.6, Z(-7)], [u, 4.6, Z(-5.3)], 0.14, 8), '#3d8a55');
    [[0.9, 0.35], [1.8, 0.3]].forEach(([y, rr]) => K.add(M.pintura, new THREE.TorusGeometry(rr, 0.04, 4, 12).translate(u + 1, y + 0.55, Z(-7.5)), '#c0392b').add(M.pintura, cil(0.05, 0.5, u + 1, y, Z(-7.5), 6), OSCURO));
  });
  for (let u = 11; u <= 28; u += 4.25) K.add(M.concreto, caja(0.4, 0.6, 0.6, u, 0, Z(-7)));
  // pasarela norte en la corona (rejilla sobre ménsulas), puentes entre unidades, barandas amarillas y escalera
  K.add(M.pintura, caja(55.4, 0.1, 1.3, 1.3, H, Z(5.65)), '#5c6268');
  for (let u = -24; u <= 28; u += 4) K.add(M.pintura, caja(0.12, 0.35, 1.3, u, H - 0.35, Z(5.65)), '#5c6268');
  [-7.5, 10.5].forEach((u) => { K.add(M.pintura, caja(1.2, 0.1, 10, u, H, 0), '#5c6268'); barandal(K, M, [[u - 0.6, Z(-5)], [u - 0.6, Z(5)]], H + 0.1); barandal(K, M, [[u + 0.6, Z(-5)], [u + 0.6, Z(5)]], H + 0.1); });
  barandal(K, M, [[-25, Z(6.3)], [29, Z(6.3)]], H + 0.1); barandal(K, M, [[-24, Z(-5)], [28, Z(-5)]], H);
  for (let i = 0; i < 14; i++) K.add(M.concreto, caja(1.1, 0.3 * (i + 1), 0.3, -26, 0, Z(5.6 - 4.2 + i * 0.3)));
  K.add(M.pintura, barra([-26.6, 1.1, Z(1.4)], [-26.6, H + 1.1, Z(5.6)], 0.03), AMARILLO);
  // edificio de químicos (pañete, lámina y portón) con los tanques de dosificación y su tubería al floculador
  naveInd(K, M, { L: 13, S: 6.5, h: 4, muro: '#f0ece2', cubierta: '#9fb3c2', frente: -1, portones: 1, ventanas: false, lucernarios: false, en: (g) => g.translate(-14, 0, Z(10.5)) });
  [[-4.5, '#eef1f0'], [-2.2, '#2f6fb3'], [0.1, '#eef1f0']].forEach(([u, col]) => K.add(M.pintura, cil(0.9, 2.4, u, 0.2, Z(10.5), 16), col));
  K.add(M.concreto, caja(7.4, 0.35, 2.8, -2.2, 0, Z(10.5)));
  [[[-2.2, 0.7, Z(9.3)], [-2.2, 0.7, Z(6.8)]], [[-2.2, 0.7, Z(6.8)], [-25.2, 0.7, Z(6.8)]], [[-25.2, 0.7, Z(6.8)], [-25.2, 0.7, Z(1)]], [[-25.2, 0.7, Z(1)], [-24, 0.7, Z(1)]]].forEach(([a, b]) => K.add(M.pintura, barra(a, b, 0.08, 6), '#e8e4d8'));
  // tubería de interconexión con la planta de hoy (agua cruda que llega y agua tratada que vuelve), sobre apoyos
  K.add(M.pintura, barra([-46, 0.7, Z(-2.5)], [-24, 0.7, Z(-2.5)], 0.32, 10), '#2f6fb3').add(M.pintura, barra([-46, 0.7, Z(-9)], [10, 0.7, Z(-9)], 0.3, 10), '#3d8a55').add(M.pintura, barra([10, 0.7, Z(-9)], [10, 0.7, Z(-7)], 0.3, 10), '#3d8a55');
  for (let u = -44; u < -26; u += 4) K.add(M.concreto, caja(0.5, 0.5, 0.6, u, 0, Z(-2.5)));
  for (let u = -44; u < 10; u += 4) K.add(M.concreto, caja(0.5, 0.5, 0.6, u, 0, Z(-9)));
  [[-47, -2.5], [-47, -9]].forEach(([u, v]) => K.add(M.concreto, caja(2.2, 1.3, 2.2, u, 0, Z(v))).add(M.pintura, caja(1.6, 0.05, 1.6, u, 1.3, Z(v)), '#3a3f44'));
  // cerramiento de malla al norte, oriente y sur (al occidente sigue la planta de hoy) con el portón al norte
  cercoMalla(K, M, [[-28, Z(15.3)], [-10, Z(15.3)]], { base: 0.3 }); cercoMalla(K, M, [[-2, Z(15.3)], [31.2, Z(15.3)], [31.2, Z(-15.3)], [-28, Z(-15.3)]], { base: 0.3 });
  K.add(M.malla, new THREE.PlaneGeometry(8, 2.1).translate(-6, 1.35, Z(15.0))).add(M.pintura, caja(8, 0.08, 0.08, -6, 2.4, Z(15.0)), '#5f686e');
  K.en(obras);
  const op = (u, v, a, ropa, h = 0.15) => Object.assign([u, v, a, ROPA[ropa]], { h });
  obras.add(gente([op(-4, 5.6, 0.2, 'azul', H + 0.1), op(17, 5.7, 2.9, 'chaleco', H + 0.1), op(10.5, 1, 1.4, 'azul', H + 0.1), op(-11.5, 5.8, -1.5, 'bata'), op(18, -10.4, 0.3, 'chaleco')], { semilla: 29 }));
  obras.add(postes([[-24, -12.5], [8, -12.5], [29, -12.5], [29, 12.5], [6, 12.5]], 6));
  raiz.userData.partes = { obras }; raiz.userData.aModelo = aModelo(raiz);
  return raiz;
}

// ---------------------------------------------------------------- parque agroindustrial
// comps: [{ id, tipo, u, v, w, d, rot }] en el marco local del lote (u a lo largo, v a lo ancho; w y d son la huella del
// componente: la nave ocupa la mayor parte y el resto queda para silos, tanques, andenes o patio). lote: polígono local del
// predio (si no viene, un rectángulo de ancho × fondo); vias: [{ puntos, ancho }] (la primera es la interna); restricciones:
// polígonos sin construir; acceso: [u, v] del ramal de la portería y del borde de la vía pública.
// En el marco de cada componente (girado 180° en el lote del levantamiento), +z mira a la vía interna y +x al occidente.
const TIPOS = {
  matadero: { h: 7.5, techo: 'dosaguas', color: '#f3f1ea' }, pescado: { h: 7, techo: 'dosaguas', color: '#eaf1f3' },
  concentrados: { h: 14, techo: 'dosaguas', color: '#e9e2cf', silos: 4 }, trilladora: { h: 9, techo: 'arco', color: '#efe9da', silos: 3 },
  leche: { h: 6, techo: 'plano', color: '#f4f5f2', tanques: 2 }, maquinaria: { h: 8, techo: 'arco', color: '#d9d4c8', patio: true },
  frio: { h: 9, techo: 'plano', color: '#f2f5f6' }, admin: { h: 7.6, techo: 'plano', color: '#f5f2ea' }, porteria: { h: 3, techo: 'plano', color: '#f3efe6' },
  bodegas: { h: 8, techo: 'dosaguas', color: '#ddd8cc' }, biodigestor: { domos: 2, pilas: 5 }, compostaje: { pilas: 6 }, ptar: { lagunas: 2 },
  corrales: { corral: true }, muelle: { muelle: true },
};
const patio = (K, M, W, D) => K.add(M.patio, losa([[-W / 2, -D / 2], [W / 2, -D / 2], [W / 2, D / 2], [-W / 2, D / 2]], 0.08));
// hilera de compostaje: medio cilindro deformado (pila de material, irregular)
function hilera(L, r, semilla) {
  const g = new THREE.CylinderGeometry(r, r, L, 16, Math.max(4, Math.round(L / 2)), false, 0, Math.PI).rotateZ(Math.PI / 2), p = g.attributes.position, ra = azar(semilla);
  for (let i = 0; i < p.count; i++) { const y = p.getY(i); if (y > 0.05) p.setY(i, y * 0.82 + (ra() - 0.5) * 0.14); }
  g.computeVertexNormals();
  return g;
}
// Constructores de cada tipo en el marco del componente (x ∈ ±W/2, z ∈ ±D/2). out.flota: camiones y máquinas [x, z, giro,
// tipo, color?]; out.gente: [x, z, giro, ropa] (.h si están en alto); out.reses: ganado [x, z, giro]
const CONSTRUIR = {
  matadero(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const p = naveEn(K, M, { w: W * 0.9, d: D * 0.74, z: -D * 0.08, h: t.h, muro: t.color, cubierta: '#aeb6bb', zocalo: 'concreto', frente: 1, muelles: 3, monitor: true, testero: 1, portones: 1 });
    p.forEach((q, i) => { out.flota.push([...alejar(q, 4.6), 'furgon', i === 1 ? '#f1f1ee' : null]); out.gente.push(Object.assign([q[0] + 1.2, q[1] - 1, 0.4, 'bata'], { h: 1.2 })); });
    // chimenea de la caldera y condensadores del frío junto al testero oriental
    K.add(M.pintura, cil(0.45, 15, -W * 0.45 + 2, 0, -D * 0.08 - D * 0.37 + 1.6, 12), '#9aa1a6').add(M.pintura, cil(0.55, 0.5, -W * 0.45 + 2, 15, -D * 0.08 - D * 0.37 + 1.6, 12), OSCURO);
    [-6, -2, 2].forEach((z) => { K.add(M.pintura, caja(1.6, 1.4, 3, -W * 0.45 - 1.8, 0, z), '#dfe3e4'); K.add(M.pintura, cil(0.6, 0.05, -W * 0.45 - 1.8, 1.4, z - 0.7, 14), OSCURO).add(M.pintura, cil(0.6, 0.05, -W * 0.45 - 1.8, 1.4, z + 0.7, 14), OSCURO); });
  },
  corrales(K, M, W, D, t, out, r) {
    patio(K, M, W, D);
    naveInd(K, M, { L: D * 0.86, S: W * 0.8, h: 4.2, abierta: true, cubierta: '#b9c0c4', lucernarios: false, en: (g) => g.rotateY(Math.PI / 2) });
    // corrales: callejón central y dos filas de corrales de 7 m con bebederos; manga de embarque al norte y manga cubierta
    // hacia el testero del matadero (al oriente)
    const L = D * 0.86, x1 = W / 2 - 1, n = Math.floor(L / 7.2), z0 = -L / 2;
    [-1, 1].forEach((s) => {
      talanquera(K, M, [[s * 1.6, z0], [s * 1.6, -z0]]); talanquera(K, M, [[s * x1, z0], [s * x1, -z0]]);
      for (let i = 0; i <= n; i++) talanquera(K, M, [[s * 1.6, z0 + (L * i) / n], [s * x1, z0 + (L * i) / n]]);
      for (let i = 0; i < n; i++) {
        const zc = z0 + (L * (i + 0.5)) / n;
        K.add(M.concreto, caja(0.7, 0.6, 2.6, s * (x1 - 0.6), 0, zc)).add(M.agua, caja(0.5, 0.04, 2.4, s * (x1 - 0.6), 0.52, zc));
        const aqui = [];
        if (r() < 0.85) for (let k = 0, m = 3 + Math.floor(r() * 3); k < 30 && aqui.length < m; k++) { const q = [s * (2.8 + r() * (x1 - 4.6)), zc + (r() - 0.5) * (L / n - 3)]; if (aqui.every((o) => Math.hypot(o[0] - q[0], o[1] - q[1]) > 1.9)) aqui.push(q); }
        aqui.forEach(([x, z]) => out.reses.push([x, z, r() * 6.28]));
      }
    });
    talanquera(K, M, [[-1.6, -z0], [-1.6, D / 2 + 2]]); talanquera(K, M, [[1.6, -z0], [1.6, D / 2 + 2]]);
    K.add(M.concreto, new THREE.BoxGeometry(3.0, 0.4, 4.6).rotateX(-Math.atan2(1.2, 4.4)).translate(0, 0.55, D / 2 - 0.4));
    const zm = D * 0.21;
    talanquera(K, M, [[-W / 2, zm - 1.4], [-W / 2 - 6.6, zm - 1.4]]); talanquera(K, M, [[-W / 2, zm + 1.4], [-W / 2 - 6.6, zm + 1.4]]);
    K.add(M.cubierta, caja(7.4, 0.12, 3.8, -W / 2 - 3.2, 3.2, zm), '#b9c0c4');
    [-W / 2 - 0.4, -W / 2 - 6.2].forEach((x) => [-1.5, 1.5].forEach((d) => K.add(M.pintura, caja(0.12, 3.2, 0.12, x, 0, zm + d), GALV)));
    out.gente.push([3.0, D / 2 - 1.5, -2.2, 'vaquero'], [-0.4, 6, 1.6, 'vaquero']);
  },
  pescado(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const p = naveEn(K, M, { x: 1.5, w: W * 0.84, d: D * 0.84, h: t.h, muro: t.color, cubierta: '#b8c0c5', lamina: true, zocalo: 'concreto', frente: -1, muelles: 3, portones: 1, extractores: 5 });
    p.forEach((q, i) => { out.flota.push([...alejar(q, 4.6), 'furgon', i ? null : '#2d5aa0']); if (i < 2) out.gente.push(Object.assign([q[0] + 1, q[1] + 0.8, 1.2, 'bata'], { h: 1.2 })); });
    // planta de hielo con condensadores y tanque elevado de agua
    const zh = -D * 0.42 - 3.6;
    K.add(M.muro, caja(6, 5, 7, 4, 0, zh), '#e6edf0').add(M.concreto, caja(6.3, 0.25, 7.3, 4, 5, zh));
    [-1.5, 1.5].forEach((d) => K.add(M.pintura, caja(1.4, 1.0, 2.4, 4 + d, 5.25, zh), '#dfe3e4'));
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => K.add(M.pintura, caja(0.18, 7, 0.18, 11 + a * 1.2, 0, -D / 2 + 1 + b * 1.2), GALV));
    K.add(M.pintura, cil(1.7, 2.8, 11, 7, -D / 2 + 1, 18), '#4f7fb0');
  },
  frio(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const p = naveEn(K, M, { x: 2, w: W * 0.82, d: D * 0.9, h: t.h, techo: 'plano', muro: t.color, lamina: true, zocalo: 'concreto', frente: -1, muelles: 4, ventanas: false });
    p.forEach((q, i) => { out.flota.push(i % 2 ? [...alejar(q, 4.6), 'furgon', '#f1f1ee'] : [...alejar(q, 8.6), 'tracto', i ? '#1f4f8f' : null]); });
    out.gente.push(Object.assign([p[1][0] + 1, p[1][1] + 0.7, 1.6, 'bata'], { h: 1.2 }), Object.assign([p[2][0] - 0.6, p[2][1] + 1, -1.4, 'azul'], { h: 1.2 }));
    // condensadores del frío en la cubierta (con sus dos ventiladores) y la casa de máquinas al sur
    for (let i = 0; i < 6; i++) { const x = 2 - 6 + (i % 3) * 6, z = -4 + Math.floor(i / 3) * 8; K.add(M.pintura, caja(4.6, 1.3, 2.2, x, t.h + 0.3, z), '#e1e5e6'); [-1.1, 1.1].forEach((d) => K.add(M.pintura, cil(0.85, 0.05, x + d, t.h + 1.6, z, 16), OSCURO)); }
    K.add(M.muro, caja(9, 5, 4, 2, 0, -D / 2 - 1.2), '#dfe5e7').add(M.concreto, caja(9.3, 0.25, 4.3, 2, 5, -D / 2 - 1.2));
  },
  concentrados(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const p = naveEn(K, M, { x: -5, w: 26, d: D * 0.85, h: t.h, muro: t.color, cubierta: '#aab3b8', lamina: true, zocalo: 'concreto', frente: -1, muelles: 2, portones: 1, monitor: true });
    p.forEach((q) => out.flota.push([...alejar(q, 8.6), 'tracto', '#c0392b']));
    out.gente.push(Object.assign([p[0][0], p[0][1] + 1.5, 0.3, 'azul'], { h: 1.2 }));
    const xs = W / 2 - 5.5, zs = [-13.2, -4.4, 4.4, 13.2], rs = 3.7, hs = 17;
    silos(K, M, zs.map((z) => [xs, z]), { r: rs, h: hs, lado: 1 });
    const e = elevador(K, M, xs, zs, rs, hs, { lado: -1 });
    // transportador cerrado del elevador al testero sur de la nave (por fuera de los silos) y su caballete
    K.add(M.pintura, viga([e.x - 0.8, e.y - 2, e.z], [7.4, 12.6, e.z + 1.3], 1.5, 1.5), '#b9c0c4').add(M.pintura, caja(0.4, 17.2, 0.4, (e.x + 7.4) / 2, 0, e.z + 0.65), GALV);
  },
  trilladora(K, M, W, D, t, out) {
    patio(K, M, W, D);
    naveEn(K, M, { x: -6, w: 24, d: D * 0.84, h: t.h, techo: 'arco', muro: t.color, cubierta: '#c3c9cc', lamina: true, zocalo: 'concreto', frente: -1, portones: 2 });
    const xs = W / 2 - 6, zs = [-12, 0, 12], rs = 3.6, hs = 16;
    silos(K, M, zs.map((z) => [xs, z]), { r: rs, h: hs, tolva: true, lado: 1 });
    elevador(K, M, xs, zs, rs, hs, { lado: -1 });
    // secadora de columna con su ciclón y quemador, y patio de secado al sol con el arroz en eras (al oriente)
    K.add(M.pintura, caja(3.2, 15, 3.2, xs, 0, 19.5), '#c7cdd1');
    for (let y = 2; y < 14; y += 1.1) K.add(M.pintura, caja(3.26, 0.35, 3.26, xs, y, 19.5), '#7b858b');
    K.add(M.pintura, new THREE.ConeGeometry(1.1, 2.4, 14).rotateX(Math.PI).translate(xs - 3, 12, 19.5), '#c7cdd1').add(M.pintura, cil(1.1, 2.2, xs - 3, 13.2, 19.5, 14), '#c7cdd1').add(M.pintura, caja(2.4, 2.2, 2.4, xs + 3, 0, 19.5), '#8d3b2b');
    K.add(M.patio, losa([[-W / 2 - 2, -22], [-W / 2 - 28, -22], [-W / 2 - 28, 2], [-W / 2 - 2, 2]].map(([x, z]) => [x, -z]), 0.08));
    for (let i = 0; i < 9; i++) K.add(M.grano, caja(24, 0.07, 1.6, -W / 2 - 15, 0.08, -20.5 + i * 2.6));
    out.gente.push([-W / 2 - 9, -8.6, 1.4, 'amarillo'], [-W / 2 - 20, -13.8, -1.2, 'azul']);
    out.areas = [[-W / 2 - 28, -22, -W / 2 - 2, 2]];
  },
  leche(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const p = naveEn(K, M, { x: -3.5, z: -1, w: 12.5, d: 12, h: t.h, techo: 'plano', muro: t.color, zocalo: 'ladrillo', frente: 1, muelles: 1, ventanas: true });
    out.flota.push([...alejar(p[0], 4.6), 'cisterna']);
    out.gente.push(Object.assign([p[0][0] + 1.2, p[0][1] - 0.5, 2.2, 'bata'], { h: 1.2 }));
    // silos de leche de acero inoxidable, tanques horizontales sobre silletas y la tubería a la sala de recibo
    [[6.5, -5], [6.5, -1]].forEach(([x, z]) => K.add(M.inox, cil(1.5, 7.5, x, 0.4, z, 20)).add(M.inox, new THREE.SphereGeometry(1.5, 16, 6, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.35, 1).translate(x, 7.9, z)).add(M.concreto, cil(1.7, 0.4, x, 0, z, 20)));
    [3.5, 6.5].forEach((z) => { K.add(M.inox, new THREE.CylinderGeometry(1.1, 1.1, 4.6, 18).rotateX(Math.PI / 2).rotateY(Math.PI / 2).translate(6, 1.9, z)); [-1.4, 1.4].forEach((d) => K.add(M.concreto, caja(0.4, 0.8, 1.8, 6 + d, 0, z))); });
    K.add(M.inox, barra([2.8, 3, -3], [6.5, 3, -3], 0.1)).add(M.inox, barra([2.8, 2.6, 5], [4.9, 2.6, 5], 0.1));
  },
  bodegas(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const p = naveEn(K, M, { z: -2, w: W * 0.9, d: D * 0.75, h: t.h, muro: t.color, cubierta: '#a9b2b8', lamina: true, zocalo: 'concreto', frente: 1, muelles: 3, portones: 1, extractores: 4 });
    p.forEach((q, i) => { if (i !== 1) out.flota.push([...alejar(q, 4.6), 'furgon']); });
    out.gente.push(Object.assign([p[1][0], p[1][1] - 1.2, 0.5, 'azul'], { h: 1.2 }), [p[1][0] + 2, p[1][1] + 2, 2.4, 'chaleco']);
  },
  admin(K, M, W, D, t, out) {
    patio(K, M, W, D);
    // edificio de dos pisos: pañete blanco, banda gris en el entrepiso, ventanas en franja con parales, quiebrasoles en la
    // fachada a la vía, marquesina de acceso, cubierta plana con antepecho y equipos
    const L = W * 0.85, S = D * 0.6, z = -1;
    K.add(M.muro, caja(L, t.h, S, 0, 0, z), t.color).add(M.concreto, caja(L + 0.4, 0.5, S + 0.4, 0, 0, z)).add(M.pintura, caja(L + 0.1, 0.3, S + 0.1, 0, 3.6, z), '#8e969c');
    [1.0, 4.6].forEach((y) => [-1, 1].forEach((s) => { K.add(M.vidrio, caja(L - 2, 1.7, 0.08, 0, y, z + s * (S / 2 + 0.02))); for (let x = -L / 2 + 1; x <= L / 2 - 1; x += 1.6) K.add(M.pintura, caja(0.08, 1.7, 0.12, x, y, z + s * (S / 2 + 0.04)), '#4a5258'); }));
    for (let x = -L / 2 + 1.2; x < L / 2 - 1; x += 1.2) K.add(M.pintura, caja(0.12, 2.6, 0.7, x, 4.3, z + S / 2 + 0.4), '#d8d0bf');
    K.add(M.concreto, caja(L + 0.4, 0.3, S + 0.4, 0, t.h, z));
    [[L + 0.4, 0.25, 0, S / 2 + 0.08], [L + 0.4, 0.25, 0, -S / 2 - 0.08], [0.25, S + 0.4, L / 2 + 0.08, 0], [0.25, S + 0.4, -L / 2 - 0.08, 0]].forEach(([lx, lz, x, dz]) => K.add(M.muro, caja(lx, 0.7, lz, x, t.h + 0.3, z + dz), '#e4ded2'));
    K.add(M.concreto, caja(9, 0.25, 4, 0, 3.4, z + S / 2 + 2)); [-4, 4].forEach((x) => K.add(M.pintura, cil(0.14, 3.4, x, 0, z + S / 2 + 3.6, 10), '#4a5258'));
    K.add(M.vidrio, caja(3.6, 2.6, 0.1, 0, 0.5, z + S / 2 + 0.05));
    [[-8, 0], [-4, 0], [6, -1]].forEach(([x, dz]) => K.add(M.pintura, caja(1.8, 1.0, 1.2, x, t.h + 0.3, z + dz), '#d9dcdc'));
    out.gente.push([1.5, z + S / 2 + 3, 1.7, 'azul'], [-1.2, z + S / 2 + 4.5, -1.4, null], [2.5, z + S / 2 + 4.8, 2.6, 'bata']);
  },
  porteria(K, M, W, D, t, out) {
    // báscula camionera: foso de concreto con plataforma de acero y rampas, caseta del operador
    K.add(M.patio, losa([[-W / 2, -D / 2], [W / 2, -D / 2], [W / 2, D / 2], [-W / 2, D / 2]], 0.08));
    K.add(M.concreto, caja(19, 0.3, 3.9, 0, 0, -1)).add(M.pintura, caja(18.2, 0.06, 3.3, 0, 0.3, -1), '#6d757b');
    [-1, 1].forEach((s) => K.add(M.concreto, new THREE.BoxGeometry(2.4, 0.2, 3.8).rotateZ(-s * Math.atan2(0.3, 2.4)).translate(s * 10.6, 0.12, -1)));
    K.add(M.muro, caja(3.2, 2.7, 2.6, 4, 0, 4), t.color).add(M.concreto, caja(3.8, 0.2, 3.2, 4, 2.7, 4)).add(M.vidrio, caja(2.4, 1.0, 0.08, 4, 1.2, 2.68)).add(M.pintura, caja(0.3, 1.4, 0.3, -3, 0, 1.6), '#3a3f44');
    out.flota.push(Object.assign([0, -1, Math.PI, 'tracto', '#3a3f44'], { h: 0.36 }));
    out.gente.push([3.6, 2.2, 1.6, 'azul']);
  },
  maquinaria(K, M, W, D, t, out, r) {
    patio(K, M, W, D);
    naveEn(K, M, { z: D * 0.27, w: W * 0.86, d: D * 0.36, h: t.h, techo: 'arco', muro: t.color, cubierta: '#b8bfc4', lamina: true, zocalo: 'concreto', frente: -1, portones: 4 });
    // patio de maquinaria al sur de la nave: dos filas de máquinas amarillas, tractores y volquetas
    const tipos = ['excavadora', 'retro', 'motoniveladora', 'tractor', 'volqueta', 'retro', 'tractor', 'excavadora', 'volqueta', 'motoniveladora', 'tractor', 'retro'];
    tipos.forEach((tp, i) => { const fila = Math.floor(i / 6), x = -W / 2 + 7 + (i % 6) * ((W - 14) / 5), z = fila ? -D / 2 + 7 : -D * 0.1; out.flota.push([x, z, fila ? Math.PI / 2 + (r() - 0.5) * 0.2 : -Math.PI / 2 + (r() - 0.5) * 0.2, tp]); });
    out.gente.push([-6, -14, 0.4, 'chaleco'], [-4.6, -13.2, 2.8, 'chaleco'], [12, -14.5, 1.2, 'amarillo']);
    // surtidor de combustible y lavadero
    K.add(M.pintura, new THREE.CylinderGeometry(1.3, 1.3, 5, 16).rotateX(Math.PI / 2).translate(W / 2 - 2.5, 1.6, -4), '#c0392b').add(M.concreto, caja(2.6, 0.3, 5.6, W / 2 - 2.5, 0, -4));
  },
  biodigestor(K, M, W, D, t, out) {
    patio(K, M, W, D);
    // digestores: tanque de concreto con domo de doble membrana, escalera; tubería de biogás (amarilla) a la casa de máquinas
    // (motogenerador) y a la antorcha
    const zd = D * 0.24, xd = [-W * 0.23, W * 0.23], rd = Math.min(9, W / 6.5), zg = zd - rd - 1.6, zc = D / 2 - 5, xa = W / 2 - 4;
    xd.forEach((x) => {
      K.add(M.concreto, cil(rd, 4.5, x, 0, zd, 36)).add(M.membrana, new THREE.SphereGeometry(rd * 0.99, 30, 12, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.62, 1).translate(x, 4.5, zd));
      K.add(M.pintura, caja(0.45, 4.3, 0.06, x + 2, 0.2, zd - rd - 0.16), OSCURO);
      K.add(M.pintura, barra([x, 3.9, zd - rd - 0.1], [x, 3.9, zg], 0.15), AMARILLO).add(M.pintura, barra([x, 3.9, zg], [x, 1.2, zg], 0.15), AMARILLO);
    });
    // colector al sur de los digestores: a la antorcha (oriente) y, entre los dos tanques, a la casa de máquinas (norte)
    K.add(M.pintura, barra([xd[0], 1.2, zg], [xa, 1.2, zg], 0.15), AMARILLO).add(M.pintura, barra([0, 1.2, zg], [0, 1.2, zc - 2.5], 0.15), AMARILLO);
    for (let x = xd[0] + 4; x < xa; x += 5) K.add(M.concreto, caja(0.4, 1.05, 0.4, x, 0, zg));
    K.add(M.muro, caja(9, 3.6, 5, 0, 0, zc), '#ece6d8').add(M.cubierta, caja(9.6, 0.15, 5.6, 0, 3.6, zc), '#9aa4aa').add(M.pintura, cil(0.25, 3, 3.2, 3.6, zc, 8), '#8d969c').add(M.pintura, caja(0.1, 2.6, 3, 4.55, 0, zc), '#a7afb5');
    K.add(M.pintura, cil(0.6, 1.6, xa - 1.6, 0, zg, 12), '#9aa3a9').add(M.pintura, cil(0.28, 9, xa, 0, zg, 10), '#a6aeb3').add(M.pintura, cil(0.5, 1.3, xa, 9, zg, 12), OSCURO).add(M.llama, new THREE.ConeGeometry(0.45, 2, 8).translate(xa, 11.3, zg));
    // compostaje en hileras sobre placa, con la volteadora en una de ellas
    const n = t.pilas || 5, L = Math.min(40, W * 0.72);
    for (let i = 0; i < n; i++) { const z = -4 - i * ((D / 2 - 7) / Math.max(1, n - 1)); K.add(M.compost, hilera(L, 1.6, 40 + i).translate(-W * 0.06, 0.08, z)); if (i === 2) out.flota.push([-W * 0.06 + 6, z, 0, 'volteadora']); }
    out.gente.push([W * 0.32, -10, 2.1, 'chaleco'], [W * 0.3, -11.2, -0.7, 'chaleco']);
  },
  compostaje(K, M, W, D, t, out) {
    patio(K, M, W, D);
    const n = t.pilas || 6, L = W * 0.8;
    for (let i = 0; i < n; i++) K.add(M.compost, hilera(L, 1.6, 60 + i).translate(0, 0.08, -D / 2 + 4 + (i * (D - 8)) / Math.max(1, n - 1)));
  },
  ptar(K, M, W, D, t, out) {
    patio(K, M, W, D);
    // tanque de igualación, dos reactores aireados con aireadores flotantes y espuma, sedimentador con puente, casa de
    // sopladores y pasarelas con baranda amarilla
    const pared = (x0, x1, z0, z1, h, agua, nivel) => {
      const xc = (x0 + x1) / 2, zc = (z0 + z1) / 2, lx = x1 - x0, lz = z1 - z0;
      K.add(M.concreto, caja(lx, h, 0.3, xc, 0, z0 + 0.15)).add(M.concreto, caja(lx, h, 0.3, xc, 0, z1 - 0.15)).add(M.concreto, caja(0.3, h, lz, x0 + 0.15, 0, zc)).add(M.concreto, caja(0.3, h, lz, x1 - 0.15, 0, zc));
      K.add(agua, caja(lx - 0.6, 0.05, lz - 0.6, xc, nivel, zc));
    };
    const zb = [-D * 0.06, -D * 0.3];
    zb.forEach((z) => {
      pared(-W * 0.4, W * 0.32, z - 5.2, z + 5.2, 3, M.aguaVerde, 2.6);
      [-W * 0.25, -W * 0.04, W * 0.17].forEach((x) => K.add(M.pintura, cil(1.5, 0.03, x, 2.66, z, 16), '#f4f6f2').add(M.pintura, cil(0.55, 0.45, x, 2.5, z, 10), '#3a4046'));
    });
    K.add(M.pintura, caja(W * 0.72, 0.1, 1.1, -W * 0.04, 3, (zb[0] + zb[1]) / 2), '#5c6268');
    barandal(K, M, [[-W * 0.4, (zb[0] + zb[1]) / 2 - 0.55], [W * 0.32, (zb[0] + zb[1]) / 2 - 0.55]], 3.1); barandal(K, M, [[-W * 0.4, (zb[0] + zb[1]) / 2 + 0.55], [W * 0.32, (zb[0] + zb[1]) / 2 + 0.55]], 3.1);
    pared(W * 0.06, W * 0.4, D * 0.12, D * 0.42, 3.2, M.aguaTurbia, 2.7);
    const xs = -W * 0.22, zs = D * 0.27;
    K.add(M.concreto, cil(6.2, 3.2, xs, 0, zs, 32, 6.2, true)).add(M.agua, new THREE.CircleGeometry(6.1, 32).rotateX(-Math.PI / 2).translate(xs, 2.9, zs)).add(M.concreto, cil(0.7, 3.6, xs, 0, zs, 12)).add(M.pintura, viga([xs, 3.75, zs], [xs + 6.3, 3.75, zs], 0.9, 0.4), AMARILLO);
    K.add(M.muro, caja(6, 3.2, 4.5, W * 0.36, 0, -D * 0.45), '#ece6d8').add(M.cubierta, caja(6.6, 0.15, 5.1, W * 0.36, 3.2, -D * 0.45), '#9aa4aa');
    K.add(M.pintura, barra([W * 0.3, 0.6, -D * 0.45 + 2.3], [W * 0.3, 0.6, zb[1] - 5.25], 0.18), '#3d8a55');
    out.gente.push(Object.assign([-W * 0.1, (zb[0] + zb[1]) / 2, 1.5, 'chaleco'], { h: 3.1 }));
  },
  muelle(K, M, W, D, t, out) {
    // muelle sobre pilotes con defensas y bitas, rieles de la grúa pórtico (con un contenedor colgado sobre el planchón),
    // rampa a la vía; planchón con contenedores (refrigerados y secos) y remolcador de empuje. El río queda en z negativo
    for (let x = -W / 2 + 2; x <= W / 2 - 2; x += 5) [-D / 2 + 1, 0, D / 2 - 1].forEach((z) => K.add(M.concreto, cil(0.35, 2.4, x, -1.2, z, 10)));
    K.add(M.concreto, caja(W, 0.6, D, 0, 1.2, 0)).add(M.concreto, new THREE.BoxGeometry(8, 0.4, 10.4).rotateX(Math.atan2(1.7, 10)).translate(1, 0.75, D / 2 + 5));
    for (let x = -W / 2 + 2; x < W / 2; x += 4) K.add(M.pintura, caja(0.5, 1.3, 0.3, x, 0.3, -D / 2 - 0.15), '#1b1d1f');
    for (let x = -W / 2 + 4; x < W / 2; x += 8) K.add(M.pintura, cil(0.18, 0.5, x, 1.8, -D / 2 + 0.5, 10), '#2a2e32');
    [D / 2 - 1.2, -D / 2 + 0.9].forEach((z) => K.add(M.pintura, caja(W - 1, 0.1, 0.2, 0, 1.8, z), '#4a5056'));
    // grúa pórtico: dos marcos en A sobre los rieles, vigas en voladizo sobre el agua, carro, cables y contenedor
    const xg = 6, zt = D / 2 - 1.2, zr = -D / 2 + 0.9, zf = -(D / 2 + 13), gc = '#e3a21a';
    [zt, zr].forEach((z) => { K.add(M.pintura, caja(7.6, 0.7, 0.9, xg, 1.8, z), gc); [-3.4, 3.4].forEach((d) => K.add(M.pintura, viga([xg + d, 2.4, z], [xg + d * 0.25, 15, z], 0.55, 0.55), gc)); });
    [-0.9, 0.9].forEach((d) => K.add(M.pintura, caja(0.6, 1.2, zt - zf + 2, xg + d, 15, (zt + zf) / 2), gc));
    K.add(M.pintura, caja(2.6, 1.0, 2.6, xg, 16.2, -12.2), '#c8861a').add(M.vidrio, caja(1.6, 1.6, 1.8, xg + 1.8, 12.2, zt - 1.2));
    [-0.8, 0.8].forEach((d) => [-0.9, 0.9].forEach((e) => K.add(M.pintura, barra([xg + d, 16.2, -12.2 + e], [xg + d * 2.5, 8.8, -12.2 + e], 0.03, 4), OSCURO)));
    K.add(M.pintura, caja(6.2, 0.3, 2.5, xg, 8.5, -12.2), gc).add(M.lamina, caja(6.06, 2.59, 2.44, xg, 5.9, -12.2), '#eef0ef');
    // planchón: casco de proas inclinadas, borda negra y contenedores de 20 pies en dos filas
    const zb = -(D / 2 + 6.2), casco = new THREE.ExtrudeGeometry(new THREE.Shape([[-18, -1], [18, -1], [19.6, 1.6], [-19.6, 1.6]].map(([x, y]) => new THREE.Vector2(x, y))), { depth: 11, bevelEnabled: false }).translate(0, 0, zb - 5.5);
    K.add(M.pintura, casco, '#6e2a20').add(M.pintura, caja(38.8, 0.06, 10.8, 0, 1.6, zb), '#7d827e');
    [-5.45, 5.45].forEach((d) => K.add(M.pintura, caja(39.2, 0.4, 0.14, 0, 1.6, zb + d), '#22262a'));
    const cols = ['#eef0ef', '#2f5f9a', '#b2382d', '#eef0ef', '#3f7a46', '#d9822b', '#eef0ef', '#2f5f9a', '#7a2e8c', '#b2382d'];
    for (let i = 0; i < 10; i++) { const x = -14 + (i % 5) * 6.5, z = zb + (i < 5 ? -1.4 : 1.4), alto = i === 2 || i === 6 ? 2 : 1; for (let k = 0; k < alto; k++) K.add(M.lamina, caja(6.06, 2.59, 2.44, x, 1.7 + k * 2.6, z), cols[(i + k * 3) % cols.length]); }
    // remolcador de empuje a popa del planchón
    const rm = new THREE.ExtrudeGeometry(new THREE.Shape([[-4.2, -0.8], [4, -0.8], [4.4, 1.3], [-4.6, 1.3]].map(([x, y]) => new THREE.Vector2(x, y))), { depth: 6, bevelEnabled: false }).translate(-24.2, 0, zb - 3);
    K.add(M.pintura, rm, '#1f3f66').add(M.muro, caja(4.2, 2.4, 4.6, -25, 1.3, zb), '#f3f1ea').add(M.muro, caja(2.8, 1.8, 3.8, -24.6, 3.7, zb), '#f3f1ea').add(M.vidrio, caja(2.9, 0.8, 3.9, -24.6, 4.5, zb)).add(M.pintura, cil(0.08, 3, -25.5, 5.5, zb, 6), OSCURO);
    // caseta del muelle, camión refrigerado y operarios
    K.add(M.muro, caja(4, 2.6, 2.6, -W / 2 + 3.5, 1.8, D / 2 - 3), '#ece6d8').add(M.cubierta, caja(4.6, 0.12, 3.2, -W / 2 + 3.5, 4.4, D / 2 - 3), '#9aa4aa');
    out.flota.push(Object.assign([-4.5, 1.5, 0, 'tracto', '#1f4f8f'], { h: 1.8 }));
    out.gente.push(Object.assign([xg + 2, -2, 1.2, 'chaleco'], { h: 1.8 }), Object.assign([xg - 3, -3.5, -0.4, 'chaleco'], { h: 1.8 }), Object.assign([-2, zb + 4.4, 1.9, 'amarillo'], { h: 1.6 }));
  },
};

export function parqueAgro({ centro, rumbo = 0, ancho = 360, fondo = 260, comps = [], zonas = [], lote = null, vias = null, restricciones = [], acceso = null }) {
  const raiz = marco(centro[0], centro[1], rumbo), r = azar(91), M = mats();
  const piso = capa(raiz, 'piso'), obras = capa(raiz, 'obras'), verde = capa(raiz, 'verde'), zonasG = capa(raiz, 'zonas');
  const poli = lote || [[-ancho / 2, -fondo / 2], [ancho / 2, -fondo / 2], [ancho / 2, fondo / 2], [-ancho / 2, fondo / 2]];
  const vs = (vias || [{ puntos: [[-ancho / 2, 0], [ancho / 2, 0]], ancho: 10 }, { puntos: [[-ancho / 2 + 40, -fondo / 2], [-ancho / 2 + 40, fondo / 2]], ancho: 9 }]).map((v) => ({ ...v, ancho: v.ancho || 8 }));
  const via0 = vs[0].puntos, vMax = Math.max(...poli.map((p) => p[1]));
  // ramal de la portería: de la vía interna al borde de la vía pública (cruza el frente del lote)
  const [ga, gb] = acceso || [Math.max(via0[0][0], via0[via0.length - 1][0]) - 6, vMax + 10];
  const vg = via0[0][1], ramal = { puntos: [[ga, vg], [ga, gb]], ancho: 8 }, todas = [...vs, ramal];
  // --- piso: césped en el predio, vías de asfalto con bordillo y raya, parqueadero del edificio administrativo
  const KP = kit();
  KP.add(M.cesped, losa(poli, 0.04));
  viasEn(KP, M, todas.map((v, i) => (i === 1 && v.ancho < 6 ? { ...v, sinBordillo: true } : v)));
  // --- zonas: contorno del color de cada una (corrido hacia adentro: los bordes compartidos no se pisan) y un tinte leve
  const geoL = [], geoF = [];
  zonas.forEach((z) => { const p = adentro(z.poligono, 0.8); geoL.push([cinta([...p, p[0], p[1]], 0.9, 0.24), z.color]); geoF.push([losa(z.poligono, 0.2), z.color]); });
  restricciones.forEach((p) => { const q = adentro(p, 0.6); geoL.push([cinta([...q, q[0], q[1]], 0.9, 0.24), '#d9363e']); geoF.push([losa(p, 0.21), '#d9363e']); });
  if (geoL.length) {
    const basica = (op, off) => new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: op, depthWrite: false, polygonOffset: true, polygonOffsetFactor: off, polygonOffsetUnits: off });
    const f = new THREE.Mesh(pintada(geoF), basica(0.08, -4)), l = new THREE.Mesh(pintada(geoL), basica(0.85, -6));
    f.userData.zona = 'zonas'; zonasG.add(f, l);
  }
  // --- componentes: cada uno en su grupo con el id de su sitio (el asistente los aísla o atenúa por nombre)
  const partes = {}, flotaL = [], genteL = [], libres = [];
  comps.forEach((c) => {
    const t = TIPOS[c.tipo] || TIPOS.admin, g = new THREE.Group(), W = c.w || 30, D = c.d || 20;
    g.name = c.id; g.position.set(c.u, 0, -c.v); g.rotation.y = THREE.MathUtils.degToRad(c.rot || 0); g.updateMatrix();
    const K = kit(), out = { flota: [], gente: [], reses: [] };
    (CONSTRUIR[c.tipo] || CONSTRUIR.admin)(K, M, W, D, t, out, r);
    K.en(g);
    if (out.reses.length) g.add(ganado(out.reses, 7));
    const p = new THREE.Vector3();
    const aLote = (it) => { p.set(it[0], 0, it[1]).applyMatrix4(g.matrix); return Object.assign([p.x, -p.z, it[2] + g.rotation.y, ...it.slice(3)], { h: it.h || 0 }); };
    out.flota.forEach((it) => flotaL.push(aLote(it)));
    out.gente.forEach((it) => { const q = aLote(it); q[3] = ROPA[it[3]] || null; genteL.push(q); });
    obras.add(g); partes[c.id] = g;
    if (c.tipo !== 'muelle') libres.push([c.u, c.v, W / 2 + 8, D / 2 + 8]);
    (out.areas || []).forEach(([a0, b0, a1, b1]) => { const q0 = aLote([a0, b0, 0]), q1 = aLote([a1, b1, 0]); libres.push([(q0[0] + q1[0]) / 2, (q0[1] + q1[1]) / 2, Math.abs(q1[0] - q0[0]) / 2 + 3, Math.abs(q1[1] - q0[1]) / 2 + 3]); });
  });
  // --- portería: talanquera de franjas en el ramal, caseta del vigilante y la reja corrediza abierta
  const KG = kit(), xg = ga, zg = -(vMax - 2);
  KG.add(M.pintura, caja(0.35, 1.1, 0.35, xg + 4.6, 0, zg), '#3a3f44');
  for (let i = 0; i < 8; i++) KG.add(M.pintura, caja(1.08, 0.1, 0.1, xg + 4.3 - (i + 0.5) * 1.08, 1.0, zg), i % 2 ? '#f4f4f0' : '#c8372d');
  KG.add(M.muro, caja(3.2, 2.6, 3.2, xg + 7.6, 0, zg + 2), '#f3efe6').add(M.concreto, caja(3.8, 0.2, 3.8, xg + 7.6, 2.6, zg + 2)).add(M.vidrio, caja(0.08, 1.0, 2.4, xg + 5.98, 1.2, zg + 2));
  KG.add(M.malla, new THREE.PlaneGeometry(8.4, 2.1).translate(xg + 9.4, 1.25, -(vMax - 0.7))).add(M.pintura, caja(8.4, 0.08, 0.08, xg + 9.4, 2.3, -(vMax - 0.7)), '#5f686e');
  genteL.push([xg + 6.4, vMax - 3.4, Math.PI, ROPA.azul]);
  // --- cerco perimetral de malla, abierto en los cruces de las vías
  cercoAbierto(poli, todas).forEach((pts) => cercoMalla(KG, M, pts, { base: 0.25 }));
  const cerco = new THREE.Group(); KG.en(cerco); obras.add(cerco);
  // --- camiones en la vía interna, parqueadero junto a la administración y luminarias a lo largo de la vía
  // (por su carril, a más de 14 m de los camiones de los andenes, que asoman a la vía)
  const andenes = flotaL.length;
  for (let i = 0, n = 0; i < 40 && n < 6; i++) {
    const k = Math.min(via0.length - 2, Math.floor(r() * (via0.length - 1))), f = 0.08 + r() * 0.84, [a, b] = [via0[k], via0[k + 1]], ida = n % 2 === 0, ang = Math.atan2(b[1] - a[1], b[0] - a[0]) + (ida ? 0 : Math.PI);
    const off = (ida ? -1 : 1) * 2.2, L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = -(b[1] - a[1]) / L, ny = (b[0] - a[0]) / L, q = [a[0] + (b[0] - a[0]) * f + nx * off, a[1] + (b[1] - a[1]) * f + ny * off];
    if (flotaL.some(([u, v], j) => Math.hypot(u - q[0], v - q[1]) < (j < andenes ? 14 : 22))) continue;
    flotaL.push([...q, ang, n % 3 ? 'furgon' : 'tracto']); n++;
  }
  const adm = comps.find((c) => c.tipo === 'admin');
  if (adm) {
    const [u0, u1, v0, v1] = [adm.u - adm.w / 2 - 2, adm.u + adm.w / 2 + 6, adm.v - adm.d / 2 - 15, adm.v - adm.d / 2 - 3];
    KP.add(M.asfalto, losa([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], 0.11));
    const cupos = [];
    for (let u = u0 + 2; u < u1 - 2; u += 2.6) { KP.add(M.pintura, caja(0.1, 0.012, 5, u, 0.115, -(v1 - 2.6)), '#f1efe6'); cupos.push(u + 1.3); }
    obras.add(carros(cupos.filter(() => r() < 0.75).map((u) => [u, v1 - 2.7, r() < 0.5 ? Math.PI / 2 : -Math.PI / 2]), { semilla: 13 }));
    libres.push([(u0 + u1) / 2, (v0 + v1) / 2, (u1 - u0) / 2 + 4, (v1 - v0) / 2 + 4, 0]);
    // jardineras a los dos lados de la marquesina de acceso (a la vía interna)
    const vj = adm.v + adm.d * 0.3 + 1.6, tiras = [-1, 1].map((sg) => [[adm.u + sg * 6, vj], [adm.u + sg * adm.w * 0.42, vj], [adm.u + sg * adm.w * 0.42, vj + 2.6], [adm.u + sg * 6, vj + 2.6]]);
    tiras.forEach((t) => KP.add(M.cesped, losa(t, 0.11)));
    const jp = tiras.flatMap((t, i) => sembrar(t, 34, 0.9, 19 + i));
    verde.userData.jardin = { matas: jp, palmas: [-1, 1].flatMap((sg) => [[adm.u + sg * 7.2, vj + 1.3], [adm.u + sg * adm.w * 0.4, vj + 1.3]]) };
  }
  KP.en(piso, false);
  obras.add(flota(flotaL));
  obras.add(gente(genteL, { semilla: 11 }));
  // luminarias al sur de la vía interna, salvo donde hay un camión en el andén (rectángulo del camión con 1 m de holgura)
  const LARGO = { tracto: 8.3, furgon: 4.4, cisterna: 4.4 }, libreDe = ([x, y]) => flotaL.every(([u, v, a, t]) => { const dx = x - u, dy = y - v, l = dx * Math.cos(a) + dy * Math.sin(a), w = -dx * Math.sin(a) + dy * Math.cos(a); return Math.abs(l) > (LARGO[t] || 3.6) + 1 || Math.abs(w) > 2.4; });
  const lv = via0.length > 1 ? aLoLargo(via0, 30, vs[0].ancho / 2 + 1.6, 6).map(([u, v]) => [u, v]).filter(libreDe) : [];
  obras.add(postes(lv, 8));
  // --- verde: barrera de árboles en el borde del predio (la primera, que brota), palmas al frente de la vía pública,
  // jardín de la administración y árboles de sombra sueltos en el césped libre
  const [pu, pv] = [poli.reduce((a, q) => a + q[0], 0) / poli.length, poli.reduce((a, q) => a + q[1], 0) / poli.length], borde = [];
  for (let i = 0; i < poli.length; i++) {
    const [a, b] = [poli[i], poli[(i + 1) % poli.length]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.floor(L / 9));
    for (let k = 0; k < n; k++) { const x = a[0] + ((b[0] - a[0]) * k) / n, y = a[1] + ((b[1] - a[1]) * k) / n, dd = Math.hypot(x - pu, y - pv) || 1; borde.push([x - ((x - pu) / dd) * 3, y - ((y - pv) / dd) * 3]); }
  }
  const cercaVia = ([x, y], m) => todas.some((v) => distLinea([x, y], v.puntos) < v.ancho / 2 + m);
  const ocupado = ([x, y], m = 0) => cercaVia([x, y], 2.5 + m) || libres.some(([u, v, hw, hd]) => Math.abs(x - u) < hw + m && Math.abs(y - v) < hd + m) || restricciones.some((p) => dentro([x, y], p));
  const caseta = ([x, y]) => Math.abs(x - (ga + 7.6)) < 4.5 && Math.abs(y - (vMax - 4)) < 4.5;
  const sueltos = [];
  for (let k = 0; k < 400 && sueltos.length < 32; k++) {
    const p = [Math.min(...poli.map((q) => q[0])) + r() * (Math.max(...poli.map((q) => q[0])) - Math.min(...poli.map((q) => q[0]))), Math.min(...poli.map((q) => q[1])) + r() * (vMax - Math.min(...poli.map((q) => q[1])))];
    if (dentro(p, adentro(poli, 10)) && !ocupado(p, 6) && sueltos.every((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) > 14)) sueltos.push(p);
  }
  verde.add(arboles([...borde.filter((p) => !cercaVia(p, 1.5) && !caseta(p)), ...sueltos], { alto: 11, semilla: 93, especie: 'mixto' }));
  const fr = [];
  for (let u = Math.min(...poli.map((q) => q[0])) + 6; u < Math.max(...poli.map((q) => q[0])) - 4; u += 13) { const p = [u, (vMax + gb) / 2]; if (!todas.some((v) => distLinea(p, v.puntos) < v.ancho / 2 + 3)) fr.push(p); }
  verde.add(palmas(fr, { alto: 9, semilla: 27 }));
  const J = verde.userData.jardin;
  if (J) { verde.add(matas(J.matas.filter((_, i) => i % 3), { tipo: 'cordyline', semilla: 19 }), matas(J.matas.filter((_, i) => !(i % 3)), { tipo: 'heliconia', alto: 1.5, semilla: 20 }), palmas(J.palmas, { alto: 7, semilla: 31 })); delete verde.userData.jardin; }
  raiz.userData.partes = { piso, obras, verde, zonas: zonasG, comps: partes };
  raiz.userData.aModelo = aModelo(raiz);
  raiz.userData.contorno = poli.map(([u, v]) => raiz.userData.aModelo(u, v));
  return raiz;
}

// ---------------------------------------------------------------- granja solar centralizada
// filas de módulos de 550 Wp (2,28 × 1,13 m) en estructura fija inclinada 10° al sur, dos módulos en vertical por mesa
// textura de una mesa (dos módulos en vertical): celdas de 6 × 12 con barras colectoras, marco de aluminio; la luminancia
// sirve también de relieve (el marco y las juntas quedan un poco más altos que las celdas)
let texPV = null;
function texturaPanel() {
  if (texPV) return texPV;
  const c = document.createElement('canvas'); c.width = 128; c.height = 512;
  const x = c.getContext('2d');
  x.fillStyle = '#c3c9ce'; x.fillRect(0, 0, 128, 512);
  for (let m = 0; m < 2; m++) {
    const y0 = m * 256;
    x.fillStyle = '#dfe4e8'; x.fillRect(4, y0 + 4, 120, 248);
    for (let i = 0; i < 6; i++) for (let j = 0; j < 12; j++) {
      const cx = 6 + i * 19.6, cy = y0 + 6 + j * 20.3, g = x.createLinearGradient(cx, cy, cx + 18, cy + 19);
      g.addColorStop(0, '#20365e'); g.addColorStop(1, '#152447');
      x.fillStyle = g; x.fillRect(cx, cy, 18.6, 19.3);
      x.fillStyle = 'rgba(196,206,220,0.5)'; for (let b = 1; b <= 3; b++) x.fillRect(cx + b * 4.65, cy, 0.8, 19.3);
    }
  }
  texPV = new THREE.CanvasTexture(c); texPV.colorSpace = THREE.SRGBColorSpace; texPV.anisotropy = 8;
  return texPV;
}
// letrero de la portería
function texturaLetrero(t1, t2) {
  const c = document.createElement('canvas'); c.width = 512; c.height = 192;
  const x = c.getContext('2d');
  x.fillStyle = '#f4f2ea'; x.fillRect(0, 0, 512, 192); x.fillStyle = '#f0a020'; x.fillRect(0, 0, 512, 22);
  x.fillStyle = '#1d2b44'; x.font = 'bold 54px "Public Sans", Arial, sans-serif'; x.textAlign = 'center'; x.fillText(t1, 256, 96);
  x.font = '600 30px "Public Sans", Arial, sans-serif'; x.fillStyle = '#4a5562'; x.fillText(t2, 256, 150);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
export function granjaSolar(poligono, { kwp = 1500, paso = 7.5, salida = null } = {}) {
  const raiz = new THREE.Group(), xs = poligono.map((p) => p[0]), ys = poligono.map((p) => p[1]), M = mats();
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const dentroP = ([x, y]) => dentro([x, y], poligono);
  // las filas se llenan desde el lado de la salida de la línea, dejando una franja libre para inversores y subestación
  const norte = salida ? salida[1] > (y0 + y1) / 2 : false, franja = salida ? 14 : 6, filas = [];
  if (norte) for (let y = y1 - franja - 2.3; y >= y0 + 4; y -= paso) filas.push(y);
  else for (let y = y0 + franja + 2.3; y <= y1 - 4; y += paso) filas.push(y);
  const mesas = [], n0 = Math.ceil((kwp * 1000) / 550 / 2);   // mesas de dos módulos en vertical
  for (const y of filas) {
    for (let x = x0 + 4; x <= x1 - 4 && mesas.length < n0; x += 1.16) if ([[-0.6, -2.3], [0.6, -2.3], [0.6, 2.3], [-0.6, 2.3]].every(([dx, dy]) => dentroP([x + dx, y + dy]))) mesas.push([x, y]);
    if (mesas.length >= n0) break;
  }
  // módulos inclinados 10° hacia el sur (la normal mira al sur, −y del modelo = +z de three) con su textura de celdas;
  // largueros continuos bajo cada fila, y postes (corto adelante, largo atrás), viga inclinada y riostra cada tercera mesa
  const tp = texturaPanel(), panel = new THREE.MeshStandardMaterial({ map: tp, bumpMap: tp, bumpScale: 0.5, roughness: 0.16, metalness: 0.35 });
  const geoP = new THREE.BoxGeometry(1.13, 0.04, 4.56).rotateX(0.175).translate(0, 1.6, 0);
  const geoR = unir([caja(1.16, 0.08, 0.06, 0, 1.25, 1.4), caja(1.16, 0.08, 0.06, 0, 1.75, -1.4)]);
  const geoS = unir([caja(0.09, 1.3, 0.09, 0, 0, 1.4), caja(0.09, 1.8, 0.09, 0, 0, -1.4), new THREE.BoxGeometry(0.07, 0.12, 4.0).rotateX(0.175).translate(0, 1.47, 0), barra([0, 0.25, 1.4], [0, 1.55, -1.2], 0.03, 4)]);
  const acero = mat(new THREE.Color('#a9b1b7'), { roughness: 0.45, metalness: 0.6 });
  const P = new THREE.InstancedMesh(geoP, panel, mesas.length), R = new THREE.InstancedMesh(geoR, acero, mesas.length), S = new THREE.InstancedMesh(geoS, acero, mesas.length), m4 = new THREE.Matrix4(), oculta = new THREE.Matrix4();
  mesas.forEach(([x, y], i) => {
    m4.makeTranslation(x, 0, -y); P.setMatrixAt(i, m4); R.setMatrixAt(i, m4);
    const sig = mesas[i + 1], ant = mesas[i - 1], extremo = !sig || sig[1] !== y || Math.abs(sig[0] - x) > 1.5 || !ant || ant[1] !== y || Math.abs(ant[0] - x) > 1.5;
    S.setMatrixAt(i, extremo || i % 3 === 0 ? m4 : oculta.makeTranslation(x, 0, -y).scale(new THREE.Vector3(1e-4, 1e-4, 1e-4)));
  });
  [P, R, S].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); raiz.add(o); });
  raiz.userData.instancias = [P, R, S];
  const kw = Math.round((mesas.length * 2 * 550) / 1000);
  // subestación elevadora a 13,2 kV junto a la salida (dentro del predio) y casetas de inversores en la franja libre
  const cx = xs.reduce((a, v) => a + v, 0) / xs.length, cy = ys.reduce((a, v) => a + v, 0) / ys.length;
  let sp = salida ? [...salida] : [cx + 40, y0 + 6];
  if (salida) for (let k = 0; k < 200 && !dentroP(sp); k++) { const d = Math.hypot(cx - sp[0], cy - sp[1]) || 1; sp = [sp[0] + ((cx - sp[0]) / d) * 2, sp[1] + ((cy - sp[1]) / d) * 2]; }
  if (salida) { const d = Math.hypot(cx - sp[0], cy - sp[1]) || 1; sp = [sp[0] + ((cx - sp[0]) / d) * 6, sp[1] + ((cy - sp[1]) / d) * 6]; }
  const yF = norte ? y1 - franja / 2 : y0 + franja / 2, s = norte ? 1 : -1, KP = kit(), K = kit();
  // --- piso: pasto cortado en el predio, pasillos de grava entre filas y vía de acceso de afirmado con su ramal a la vía
  KP.add(M.cesped, losa(poligono, 0.03));
  const porFila = new Map(); mesas.forEach(([x, y]) => { const f = porFila.get(y) || [Infinity, -Infinity]; porFila.set(y, [Math.min(f[0], x), Math.max(f[1], x)]); });
  [...porFila.entries()].forEach(([y, [a, b]]) => { const ya = y - s * (paso / 2); if (dentroP([(a + b) / 2, ya])) KP.add(M.grava, cinta([[a - 0.6, ya], [b + 0.6, ya]], 2.6, 0.05)); });
  const yv = yF - s * 4.2, xa = salida ? sp[0] - 62 : cx;
  const ext = [x0 + 5, x1 - 5].map((x) => { let q = x; for (let k = 0; k < 40 && !dentroP([q, yv]); k++) q += x < cx ? 2 : -2; return q; });
  if (salida) ext[1] = Math.min(ext[1], sp[0] - 9);
  KP.add(M.afirmado, cinta([[ext[0], yv], [ext[1], yv]], 3.6, 0.06));
  let yb = yv; for (let k = 0; k < 60 && dentroP([xa, yb]); k++) yb += s;
  KP.add(M.afirmado, cinta([[xa, yv], [xa, yb + s * 4.5]], 4, 0.065));
  KP.en(raiz, false);
  // --- casetas de inversores: placa, contenedor con rejillas, transformador con radiadores y aisladores
  [-24, -48, -72].map((d) => [sp[0] + d, yF]).filter((q) => dentroP(q) && Math.abs(q[0] - xa) > 7).forEach(([x, y]) => {
    const z = -y;
    K.add(M.concreto, caja(9.4, 0.2, 3.6, x, 0, z)).add(M.lamina, caja(6, 2.6, 2.4, x - 1.4, 0.2, z), '#eceeed');
    [-3, -1.4, 0.2].forEach((d) => K.add(M.pintura, caja(0.9, 0.9, 0.06, x + d, 1.2, z + s * 1.22), '#5d666c'));
    K.add(M.pintura, caja(1.6, 1.7, 1.4, x + 3.1, 0.2, z), '#7f878e');
    for (let k = 0; k < 5; k++) K.add(M.pintura, caja(0.06, 1.3, 0.8, x + 2.3 + k * 0.4, 0.4, z + 1.05), '#6f777e');
    [-0.5, 0, 0.5].forEach((d) => K.add(M.pintura, cil(0.07, 0.45, x + 3.1 + d, 1.9, z, 8), '#9b6b45'));
  });
  // --- subestación elevadora: placa de grava con su malla; transformador con radiadores, tanque conservador y bujes;
  // pórtico con aisladores y seccionadores, caseta de control; poste terminal de concreto con cruceta en la salida a
  // 13,2 kV (la línea sigue por el trazado de la conexión hasta la subestación de EPM)
  const sz = -sp[1], nz = -s, xt = sp[0] - 3, zt = sz - nz * 1.6;
  K.add(M.grava, caja(14, 0.15, 10, sp[0], 0, sz)).add(M.concreto, caja(4.6, 0.4, 3.4, xt, 0.15, zt));
  K.add(M.pintura, caja(3.2, 2.6, 2.2, xt, 0.55, zt), '#7b848b');
  [-1, 1].forEach((d) => { for (let k = 0; k < 6; k++) K.add(M.pintura, caja(0.06, 2.0, 0.7, xt - 1.3 + k * 0.5, 0.8, zt + d * 1.45), '#6b737a'); });
  K.add(M.pintura, new THREE.CylinderGeometry(0.4, 0.4, 2.6, 12).rotateZ(Math.PI / 2).translate(xt, 3.55, zt + 0.6), '#7b848b');
  [-0.9, 0, 0.9].forEach((d) => K.add(M.pintura, new THREE.ConeGeometry(0.16, 1.1, 8).translate(xt + d, 3.7, zt - 0.5), '#9b6b45'));
  const zp = sz + nz * 1.2, xp = [sp[0] + 0.6, sp[0] + 6.2];
  xp.forEach((x) => K.add(M.pintura, caja(0.45, 9, 0.45, x, 0.15, zp), '#a3abb1'));
  K.add(M.pintura, caja(xp[1] - xp[0] + 0.6, 0.5, 0.5, (xp[0] + xp[1]) / 2, 9, zp), '#a3abb1');
  const fases = [-1.6, 0, 1.6].map((d) => (xp[0] + xp[1]) / 2 + d);
  fases.forEach((x, i) => { K.add(M.pintura, cil(0.12, 0.9, x, 8.1, zp, 8), '#9b6b45').add(M.pintura, barra([x, 8.2, zp], [xt + (i - 1) * 0.9, 4.3, zt - 0.5], 0.03, 4), '#3a3f44').add(M.pintura, caja(0.3, 1.6, 0.3, x, 0.15, zp - nz * 1.6), '#a3abb1'); });
  K.add(M.muro, caja(3.6, 2.8, 2.8, sp[0] - 3.4, 0.15, sz + nz * 2.8), '#efece4').add(M.concreto, caja(4, 0.2, 3.2, sp[0] - 3.4, 2.95, sz + nz * 2.8));
  cercoMalla(K, M, [[sp[0] - 7.2, sz - 5.2], [sp[0] + 7.2, sz - 5.2], [sp[0] + 7.2, sz + 5.2], [sp[0] - 7.2, sz + 5.2], [sp[0] - 7.2, sz - 5.2]], { alto: 2.4 });
  if (salida) {
    const [ex, ey] = salida, ez = -ey;
    K.add(M.concreto, cil(0.24, 12, ex, 0, ez, 10, 0.15)).add(M.pintura, caja(2.6, 0.14, 0.14, ex, 11.2, ez), '#6b737a');
    [-1.1, 0, 1.1].forEach((d, i) => {
      K.add(M.pintura, cil(0.08, 0.35, ex + d, 11.34, ez, 6), '#9b6b45');
      const a = new THREE.Vector3(fases[i], 8.1, zp), b = new THREE.Vector3(ex + d, 11.6, ez), pts = [];
      for (let k = 0; k <= 10; k++) { const t = k / 10; pts.push(new THREE.Vector3().lerpVectors(a, b, t).add(new THREE.Vector3(0, -0.5 * 4 * t * (1 - t), 0))); }
      K.add(M.pintura, new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 10, 0.03, 4), '#2a2e32');
    });
  }
  // --- cerco de malla del predio (con el portón en el ramal), cámaras en postes y letrero en la portería
  const ramal = [{ puntos: [[xa, yv], [xa, yb + s * 4.5]], ancho: 4 }];
  cercoAbierto(poligono, ramal).forEach((pts) => cercoMalla(K, M, pts, { base: 0.2 }));
  poligono.filter((_, i) => i % 2 === 0).forEach(([x, y]) => { const d = Math.hypot(cx - x, cy - y) || 1, ux = (cx - x) / d, uy = (cy - y) / d, px = x + ux * 1.2, pz = -(y + uy * 1.2); K.add(M.pintura, cil(0.09, 6, px, 0, pz, 8), '#5f686e').add(M.pintura, caja(0.5, 0.28, 0.28, px + ux * 0.4, 5.7, pz - uy * 0.4), '#e8eaeb'); });
  const yl = yb + s * 2.2, letrero = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 1.6), new THREE.MeshStandardMaterial({ map: texturaLetrero('Granja Solar Municipal', 'Yondó · 1,2 MWp'), roughness: 0.6 }));
  letrero.position.set(xa + 5.2, 2.3, -yl); letrero.rotation.y = norte ? Math.PI : 0; raiz.add(letrero);
  K.add(M.pintura, caja(4.4, 1.8, 0.08, xa + 5.2, 1.4, -yl + s * 0.06), '#3a3f44');
  [-2, 2].forEach((d) => K.add(M.pintura, cil(0.07, 3.1, xa + 5.2 + d, 0, -yl + s * 0.14, 8), '#3a3f44'));
  K.en(raiz);
  raiz.add(carros([[xa - 3, yv - s * 0.2, 0, '#f4f4f2']], { semilla: 5 }));
  const op = (x, y, a, ropa) => [x, y, a, ROPA[ropa]];
  raiz.add(gente([op(sp[0] - 24 + 1, yF - s * 2.6, 1.6, 'chaleco'), op(sp[0] - 24 - 1.5, yF - s * 2.4, -1.2, 'azul'), op(xa - 1.5, yv + s * 2.2, 2.6, 'chaleco'), ...(mesas[40] ? [op(mesas[40][0], mesas[40][1] - s * 3.3, 0, 'amarillo')] : [])], { semilla: 3 }));
  raiz.userData.kwp = kw; raiz.userData.mesas = mesas.length;
  raiz.userData.subestacion = sp;
  return raiz;
}
