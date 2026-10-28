// Mirador Puerta del Magdalena, junto al estribo de Yondó del puente Guillermo Gaviria Correa, armado sobre el prediseño
// del levantamiento (orilla leída en la imagen de sep-2025). Zona A: franja de protección hidráulica de 283 m de orilla y
// 36 m de ancho (30 m de ronda y 6 m de pie de enrocado dentro del agua), con enrocado en el talud y vegetación de ribera,
// sin pavimento. Zona B: plaza de 0,46 ha detrás de la ronda, aguas abajo del puente, con las letras «YONDÓ» de frente a
// la plaza, jardineras con árboles, bancas, luminarias y parqueadero. Un sendero curvo en deck cruza la ronda y corre por
// el borde del agua hasta un mirador de 10 × 10 m sobre pilotes, y una pasarela articulada baja al muelle flotante de
// 30 × 5 m donde hoy atracan las lanchas.
// Marco local: u a lo largo de la orilla aguas abajo y v hacia el río, con origen en el cruce del eje del puente con la
// orilla; las piezas de geo3d reciben (u, −v).
import { THREE, mat } from '../../core.js';
import { losa, cinta, enrocado, arboles, palmas, postes, letras, aLoLargo, suave, unir, dentro, sembrar } from '../geo3d.js';

// prediseño de respaldo en el marco local (u, v); geo.json lo trae en metros del modelo y se convierte al marco
const DISENO = {
  zonaA: [[-80, -30], [-50, -28], [-25, -25], [0, -22], [25, -30], [50, -33], [75, -32.1], [100, -34.1], [125, -38], [150, -43], [175, -44], [200, -45], [200, -9], [175, -8], [150, -7], [125, -2], [100, 2], [75, 4], [50, 2.9], [25, 6], [0, 14], [-24.9, 11], [-50, 8], [-80, 6]],
  plaza: [[32, -32], [60, -33], [90, -34.1], [118, -37], [117.9, -86], [89.9, -87], [60, -88], [32, -87.1]],
  mirador: [[52, -5], [62, -5], [62, 5], [52, 5]],
  muelle: [[92, 12], [122, 11.9], [122.1, 17], [92, 17]],
  letras: [80, -38.1],
  deck: [[112, -37], [117, -30], [119, -22], [116, -14], [109, -8], [100, -4], [90, -2], [80, -1.1], [71, -0.5], [63, 0]],
  pasarela: [[102, -4], [104, 12]],
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
const distLinea = (p, linea) => {
  let d = Infinity;
  for (let i = 1; i < linea.length; i++) {
    const [a, b] = [linea[i - 1], linea[i]], dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    d = Math.min(d, Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy));
  }
  return d;
};

// { origen: [x, y] (eje del puente en la orilla), angulo: grados desde el oriente (antihorario) de la orilla aguas abajo,
//   diseno: { zonaA, plaza, mirador, muelle, letras, deck, pasarela, acceso, orilla } en metros del modelo (opcional) }
export async function miradorMagdalena({ origen, angulo, diseno = null }) {
  const raiz = new THREE.Group(), th = THREE.MathUtils.degToRad(angulo), c = Math.cos(th), s = Math.sin(th);
  raiz.position.set(origen[0], 0, -origen[1]); raiz.rotation.y = th;
  const aLocal = ([x, y]) => [(x - origen[0]) * c + (y - origen[1]) * s, (x - origen[0]) * s - (y - origen[1]) * c];
  const D = { ...DISENO };
  if (diseno) Object.entries(diseno).forEach(([k, v]) => { if (v?.length) D[k] = typeof v[0] === 'number' ? aLocal(v) : v.map(aLocal); });
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const zonaA = capa('zonaA'), plaza = capa('plaza'), deck = capa('deck'), muelle = capa('muelle'), verde = capa('verde'), letrasG = capa('letras');
  const C = {
    adoquin: mat(new THREE.Color('#cdbca5'), { roughness: 0.9 }), borde: mat(new THREE.Color('#8f8678'), { roughness: 0.9 }),
    jardin: mat(new THREE.Color('#5f9e48'), { roughness: 1 }), madera: mat(new THREE.Color('#a8703f'), { roughness: 0.75 }),
    pilote: mat(new THREE.Color('#5a4632'), { roughness: 0.9 }), metal: mat(new THREE.Color('#2b3035'), { roughness: 0.5, metalness: 0.5 }),
    roca: mat(new THREE.Color('#8d8a82'), { roughness: 1, flatShading: true }), concreto: mat(new THREE.Color('#bdb8ae'), { roughness: 0.9 }),
    zonaA: new THREE.MeshBasicMaterial({ color: new THREE.Color('#2a78d6'), transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 }),
    ribera: mat(new THREE.Color('#6f9f4f'), { roughness: 1, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }),
    lancha: mat(new THREE.Color('#f2f2ee'), { roughness: 0.5 }), toldo: mat(new THREE.Color('#2459a6'), { roughness: 0.6 }), banca: mat(new THREE.Color('#9c6b43'), { roughness: 0.8 }),
    asfalto: mat(new THREE.Color('#5a5e63'), { roughness: 0.95 }), cal: new THREE.MeshBasicMaterial({ color: 0xf2f2f2 }),
  };
  const sombra = (o) => { o.traverse((k) => { if (k.isMesh) { k.castShadow = true; k.receiveShadow = true; } }); return o; };
  const orilla = D.orilla, vOrilla = (u) => { for (let i = 1; i < orilla.length; i++) if (u <= orilla[i][0]) { const [a, b] = [orilla[i - 1], orilla[i]], t = (u - a[0]) / (b[0] - a[0] || 1); return a[1] + t * (b[1] - a[1]); } return orilla[orilla.length - 1][1]; };

  // --- zona A: franja de la ronda (tenue), talud con vegetación de ribera y enrocado del pie contra la socavación
  zonaA.add(new THREE.Mesh(losa(D.zonaA.map(L), 0.3), C.zonaA));
  const banda = (v0, v1) => [...orilla.map(([u, v]) => [u, v + v0]), ...[...orilla].reverse().map(([u, v]) => [u, v + v1])];
  zonaA.add(new THREE.Mesh(losa(banda(-29, -7).map(L), 0.12), C.ribera));
  zonaA.add(enrocado(banda(-7, 5).map(L), 2200, { tam: 1.15, alto: 0.7, semilla: 17, m: C.roca }));
  // --- zona B: plaza de esquinas redondeadas con borde, prado central, jardineras con árboles, bancas y luminarias
  const contorno = redondear(D.plaza, 9);
  plaza.add(sombra(new THREE.Mesh(losa(contorno.map(L), 0.18), C.adoquin)));
  plaza.add(new THREE.Mesh(cinta([...contorno, contorno[0], contorno[1]].map(L), 0.7, 0.24), C.borde));
  const cu = D.plaza.reduce((a, p) => a + p[0], 0) / D.plaza.length, cv = D.plaza.reduce((a, p) => a + p[1], 0) / D.plaza.length;
  const prado = Array.from({ length: 40 }, (_, i) => { const t = (i / 40) * 2 * Math.PI; return [cu + 24 * Math.cos(t), cv - 12 + 8 * Math.sin(t)]; });
  plaza.add(new THREE.Mesh(losa(prado.map(L), 0.22), C.jardin));
  const jardineras = [[cu - 30, cv + 10, 4.5], [cu - 12, cv + 4, 5.5], [cu + 14, cv + 8, 5], [cu + 32, cv + 4, 4.5], [cu - 32, cv - 14, 4], [cu + 33, cv - 16, 4]];
  const tierra = [], anillos = [], bancas = [];
  jardineras.forEach(([u, v, r]) => {
    const pts = Array.from({ length: 30 }, (_, i) => [u + r * Math.cos((i / 30) * 2 * Math.PI), v + r * Math.sin((i / 30) * 2 * Math.PI)]);
    tierra.push(losa(pts.map(L), 0.62)); anillos.push(cinta([...pts, pts[0], pts[1]].map(L), 0.45, 0.6));
    [0.5, 2.6, 4.4].forEach((a) => { const x = u + (r + 1.4) * Math.cos(a), z = v + (r + 1.4) * Math.sin(a); bancas.push(new THREE.BoxGeometry(2.2, 0.45, 0.6).rotateY(-a + Math.PI / 2).translate(x, 0.42, z)); });
  });
  plaza.add(new THREE.Mesh(unir(tierra), C.jardin), sombra(new THREE.Mesh(unir(anillos), C.concreto)), sombra(new THREE.Mesh(unir(bancas), C.banca)));
  verde.add(arboles(jardineras.map(([u, v]) => L([u, v])), { alto: 8, semilla: 51 }));
  verde.add(arboles([[cu - 16, cv - 12], [cu, cv - 13], [cu + 16, cv - 11]].map(L), { alto: 10, semilla: 53 }));
  verde.add(palmas([D.plaza[0], D.plaza[3], D.plaza[4], D.plaza[7]].map(([u, v]) => L([u + (u < cu ? 5 : -5), v + (v < cv ? 5 : -5)])), { alto: 9, semilla: 52 }));
  plaza.add(postes(aLoLargo(contorno.map(L), 15), 4.6));
  // baranda en el borde de la plaza que da a la ronda (deja libre la entrada al deck)
  const bordeRio = contorno.filter(([u, v]) => v > cv + 18 && Math.hypot(u - D.deck[0][0], v - D.deck[0][1]) > 7);
  if (bordeRio.length > 1) plaza.add(barandaEn(bordeRio.map(([u, v]) => [u, v - 0.6, 0.2]), C.metal));
  // parqueadero sobre el borde de la vía y acceso desde la vía del puente (el empalme se acuerda con la concesión)
  const sur = [...D.plaza].sort((a, b) => a[1] - b[1]).slice(0, 2).sort((a, b) => a[0] - b[0]);
  if (sur.length === 2) {
    const [a, b] = sur, u0 = a[0] + 4, u1 = Math.min(b[0] - 4, u0 + 50), v1 = Math.min(a[1], b[1]) - 1, v0 = v1 - 5.5;
    plaza.add(new THREE.Mesh(losa([[u0, v0], [u1, v0], [u1, v1], [u0, v1]].map(L), 0.1), C.asfalto));
    const rayas = []; for (let u = u0; u <= u1; u += 2.5) rayas.push(cinta([[u, v0 + 0.4], [u, v1 - 0.4]].map(L), 0.1, 0.11));
    plaza.add(new THREE.Mesh(unir(rayas), C.cal));
  }
  plaza.add(new THREE.Mesh(cinta(D.acceso.map(L), 7, 0.1), C.asfalto));
  // --- letras «YONDÓ» de colores (≈14 m), de frente a la plaza y con el río detrás
  const ly = await letras('YONDO', { alto: 3.2, fondo: 0.8, colores: ['#7cc242', '#2a9fd6', '#e8452c', '#1f6fd1', '#f5b400'], acento: 4, separacion: 0.4 });
  const [lu, lv] = D.letras;
  ly.position.set(lu, 0.7, lv); ly.rotation.y = Math.PI;   // el texto mira hacia −v (la plaza): la «Y» queda aguas abajo
  const zocalo = new THREE.Mesh(new THREE.BoxGeometry(15.5, 0.7, 2.4).translate(0, 0.35, 0), C.concreto); zocalo.position.set(lu, 0.05, lv);
  letrasG.add(sombra(zocalo), sombra(ly));

  // --- sendero curvo en deck: sale de la plaza, cruza la ronda y corre por el borde del agua hasta el mirador
  const ruta = suave(D.deck, 60), n = ruta.length, h0 = 0.8, h1 = 4.2, alto = (i) => h0 + (h1 - h0) * (i / (n - 1)) ** 0.85;
  const tablas = [], pilotes = [];
  for (let i = 1; i < n; i++) {
    const [a, b] = [ruta[i - 1], ruta[i]], h = (alto(i - 1) + alto(i)) / 2, Lg = Math.hypot(b[0] - a[0], b[1] - a[1]), ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
    tablas.push(new THREE.BoxGeometry(Lg + 0.1, 0.2, 3).rotateY(-ang).translate((a[0] + b[0]) / 2, h, (a[1] + b[1]) / 2));
    if (i % 4 === 0) [-1.35, 1.35].forEach((o) => { const x = a[0] - Math.sin(ang) * o, z = a[1] + Math.cos(ang) * o; pilotes.push(new THREE.CylinderGeometry(0.14, 0.14, h + 3, 6).translate(x, (h - 3) / 2, z)); });
  }
  deck.add(sombra(new THREE.Mesh(unir(tablas), C.madera)));
  const lado = (o) => ruta.map(([u, v], i) => { const [a, b] = [ruta[Math.max(0, i - 1)], ruta[Math.min(n - 1, i + 1)]], ang = Math.atan2(b[1] - a[1], b[0] - a[0]); return [u - Math.sin(ang) * o, v + Math.cos(ang) * o, alto(i)]; });
  deck.add(barandaEn(lado(1.45), C.metal), barandaEn(lado(-1.45), C.metal));
  // --- mirador: plataforma de 10 × 10 m sobre pilotes en el borde del agua, con pérgola de sombra
  const md = D.mirador, mu = md.reduce((a, p) => a + p[0], 0) / md.length, mv = md.reduce((a, p) => a + p[1], 0) / md.length;
  const plataforma = new THREE.Mesh(new THREE.ExtrudeGeometry(new THREE.Shape(md.map(L).map(([x, y]) => new THREE.Vector2(x, y))), { depth: 0.3, bevelEnabled: false }).rotateX(-Math.PI / 2).translate(0, h1 - 0.1, 0), C.madera);
  deck.add(sombra(plataforma));
  md.forEach(([u, v]) => pilotes.push(new THREE.CylinderGeometry(0.2, 0.2, h1 + 4, 8).translate(u + (mu - u) * 0.08, (h1 - 4) / 2, v + (mv - v) * 0.08)));
  pilotes.push(new THREE.CylinderGeometry(0.22, 0.22, h1 + 4, 8).translate(mu, (h1 - 4) / 2, mv));
  deck.add(sombra(new THREE.Mesh(unir(pilotes), C.pilote)));
  const borde = [...md, md[0]].map(([u, v]) => [u + (mu - u) * 0.04, v + (mv - v) * 0.04, h1 + 0.2]);
  deck.add(barandaEn(borde, C.metal));
  const pergola = [];
  [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(([a, b]) => pergola.push(new THREE.BoxGeometry(0.22, 2.7, 0.22).translate(mu + a * 3.2, h1 + 1.55, mv + b * 3.2)));
  for (let k = -3; k <= 3; k++) pergola.push(new THREE.BoxGeometry(7.2, 0.14, 0.32).translate(mu, h1 + 2.95, mv + k * 1.05));
  deck.add(sombra(new THREE.Mesh(unir(pergola), C.madera)));
  // --- muelle flotante con pasarela articulada, la chalupa de toldo azul y dos lanchas
  const mm = D.muelle, au = mm.reduce((a, p) => a + p[0], 0) / mm.length, av = mm.reduce((a, p) => a + p[1], 0) / mm.length;
  const largoM = Math.hypot(mm[1][0] - mm[0][0], mm[1][1] - mm[0][1]), anchoM = Math.hypot(mm[2][0] - mm[1][0], mm[2][1] - mm[1][1]), angM = Math.atan2(mm[1][1] - mm[0][1], mm[1][0] - mm[0][0]);
  const ponton = new THREE.Mesh(new THREE.BoxGeometry(largoM, 0.6, anchoM).translate(0, 0.3, 0), C.madera); ponton.position.set(au, 0, av); ponton.rotation.y = -angM; muelle.add(sombra(ponton));
  const [pa, pb] = D.pasarela, iPa = ruta.reduce((k, p, i) => (Math.hypot(p[0] - pa[0], p[1] - pa[1]) < Math.hypot(ruta[k][0] - pa[0], ruta[k][1] - pa[1]) ? i : k), 0);
  const hPa = alto(iPa), lp = Math.hypot(pb[0] - pa[0], pb[1] - pa[1]), angP = Math.atan2(pb[1] - pa[1], pb[0] - pa[0]);
  const pas = new THREE.Mesh(new THREE.BoxGeometry(lp, 0.16, 2).translate(lp / 2, 0, 0), C.madera);
  pas.position.set(pa[0], hPa, pa[1]); pas.rotation.set(0, -angP, 0); pas.rotateZ(-Math.atan2(hPa - 0.6, lp)); muelle.add(sombra(pas));
  const bote = (u, v, largo, toldo) => { const g = new THREE.Group(); g.add(new THREE.Mesh(new THREE.BoxGeometry(largo, 1, largo * 0.22).translate(0, 0.35, 0), C.lancha)); if (toldo) { g.add(new THREE.Mesh(new THREE.BoxGeometry(largo * 0.7, 0.12, largo * 0.24).translate(0, 2.3, 0), C.toldo)); [-1, 1].forEach((k) => g.add(new THREE.Mesh(new THREE.BoxGeometry(0.1, 1.9, largo * 0.2).translate(k * largo * 0.33, 1.3, 0), C.metal))); } g.position.set(u, 0, v); g.rotation.y = -angM; return sombra(g); };
  muelle.add(bote(au - 4, av + anchoM / 2 + 2.2, 14, true), bote(au + 10, av + anchoM / 2 + 1.8, 6.5, false), bote(au + 4, av + anchoM / 2 + 6, 6, false));
  // --- vegetación de ribera en la ronda (lejos del deck y del muelle) y algunas palmas
  const ribera = sembrar(banda(-27, -9), 70, 6.5, 29).filter(([u, v]) => distLinea([u, v], ruta) > 5 && !dentro([u, v], D.plaza) && Math.abs(u) > 16);
  verde.add(arboles(ribera.map(L), { alto: 9, semilla: 57 }));
  verde.add(palmas(sembrar(banda(-24, -12), 10, 14, 31).filter(([u, v]) => distLinea([u, v], ruta) > 6 && Math.abs(u) > 16).map(L), { alto: 11, semilla: 58 }));

  raiz.userData.partes = { zonaA, plaza, deck, muelle, verde, letras: letrasG };
  raiz.updateMatrixWorld(true);
  const aModelo = (u, v) => { const p = new THREE.Vector3(u, 0, v).applyMatrix4(raiz.matrixWorld); return [p.x, -p.z]; };
  raiz.userData.aModelo = aModelo;
  const us = [...D.plaza, ...ruta, ...md, ...mm].map((p) => p[0]), vs = [...D.plaza, ...ruta, ...md, ...mm].map((p) => p[1]);
  raiz.userData.contorno = [[Math.min(...us) - 6, Math.min(...vs) - 6], [Math.max(...us) + 6, Math.min(...vs) - 6], [Math.max(...us) + 6, Math.max(...vs) + 6], [Math.min(...us) - 6, Math.max(...vs) + 6]].map(([u, v]) => aModelo(u, v));
  raiz.userData.contornoA = D.zonaA.map(([u, v]) => aModelo(u, v));
  raiz.userData.zonaA = aModelo(14, vOrilla(14) - 16); raiz.userData.zonaB = aModelo(cu, cv - 21);
  raiz.userData.mirador = aModelo(mu, mv); raiz.userData.muelle = aModelo(au, av);
  return raiz;
}

// baranda que sigue la altura de cada punto [u, v, h] (pasamanos en tubo y parales cada 2 m), en el marco (u, h, v)
function barandaEn(pts, m) {
  const g = new THREE.Group(), alto = 1.05;
  const curva = new THREE.CatmullRomCurve3(pts.map(([u, v, h]) => new THREE.Vector3(u, h + alto, v)));
  g.add(new THREE.Mesh(new THREE.TubeGeometry(curva, Math.max(8, pts.length * 2), 0.045, 5), m));
  const parales = [];
  let acum = 2;
  for (let i = 1; i < pts.length; i++) {
    const [a, b] = [pts[i - 1], pts[i]], d = Math.hypot(b[0] - a[0], b[1] - a[1]);
    for (let t = 0; t < d; t += 2) { if ((acum += 2) < 2) continue; const k = t / (d || 1), u = a[0] + (b[0] - a[0]) * k, v = a[1] + (b[1] - a[1]) * k, h = a[2] + (b[2] - a[2]) * k; parales.push(new THREE.BoxGeometry(0.05, alto, 0.05).translate(u, h + alto / 2, v)); }
  }
  if (parales.length) g.add(new THREE.Mesh(unir(parales), m));
  return g;
}
