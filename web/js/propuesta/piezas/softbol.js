// Cancha de Sóftbol Casabe: el estadio renovado según el plano propuesto (home al sur), en un lote de 109 × 102,9 m: el
// de 109 × 110 m del plano no cabe exacto en la manzana del estadio actual y 102,9 m alcanzan para la cerca. Medidas
// reglamentarias de sóftbol: 18,29 m entre bases, 25,87 m de home a segunda, 13,11 m de home al lanzador, círculo del
// lanzador de 2,44 m de radio, cerca de 67,06 m en las líneas de foul a 76,20 m en el jardín central. Graderías de
// 20 × 4 m con cubierta tensada, dos dugouts de 10 × 3 m, baños y vestidores de 8 × 4 m, parqueadero de 20 cupos, cancha
// múltiple, zona infantil y biosaludable, marcador, torres de luz LED, sendero perimetral con palmas y portal de acceso.
// Se arma en un marco local con el home en el origen: u a la derecha (lado de primera base), v hacia el jardín central.
import { THREE, mat } from '../../core.js';
import { losa, cinta, graderia, membrana, torresLuz, postes, arboles, palmas, aLoLargo, unir } from '../geo3d.js';

export const MEDIDAS = {
  lote: [109, 102.9], homeAlSur: 22, bases: 18.29, homeSegunda: 25.87, lanzador: 13.11, rLanzador: 2.44, rBateo: 0.76,
  cercaFoul: 67.06, cercaCentro: 76.2, dugout: [10, 3], graderia: [20, 4], banos: [8, 4], cupos: 20,
};
// radio de la cerca según el ángulo desde el eje home → jardín central (67,06 m en las líneas de foul, 76,20 m al centro)
export const cerca = (a) => MEDIDAS.cercaFoul + (MEDIDAS.cercaCentro - MEDIDAS.cercaFoul) * Math.cos(2 * a) ** 2;

function texturaMarcador() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 224;
  const x = c.getContext('2d');
  x.fillStyle = '#14181c'; x.fillRect(0, 0, 512, 224);
  x.fillStyle = '#ffd34d'; x.font = 'bold 86px Anton, Impact, sans-serif'; x.textAlign = 'center'; x.fillText('CASABE', 256, 100);
  x.fillStyle = '#e8e8e8'; x.font = '600 30px "IBM Plex Mono", monospace'; x.fillText('BALL  STRIKE  OUT', 256, 152);
  x.fillStyle = '#ff6a3d'; x.fillText('1 2 3 4 5 6 7   R H E', 256, 196);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

// { home: [x, y] en el modelo, rumbo: grados desde el norte del eje home → jardín central }
export function canchaSoftbol({ home, rumbo = 0 }) {
  const raiz = new THREE.Group(), M = MEDIDAS;
  raiz.position.set(home[0], 0, -home[1]); raiz.rotation.y = -THREE.MathUtils.degToRad(rumbo);
  const [W, D] = M.lote, v0 = -M.homeAlSur, v1 = D - M.homeAlSur, u0 = -W / 2, u1 = W / 2;
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const piso = capa('piso'), campo = capa('campo'), obras = capa('obras'), cubierta = capa('cubierta'), luces = capa('luces'), verde = capa('verde');
  const C = {
    jardin: mat(new THREE.Color('#6fae55'), { roughness: 1 }), grama: mat(new THREE.Color('#4f9a3d'), { roughness: 0.95 }), grama2: mat(new THREE.Color('#58a646'), { roughness: 0.95 }),
    arcilla: mat(new THREE.Color('#c27744'), { roughness: 1 }), cal: new THREE.MeshBasicMaterial({ color: 0xffffff }), sendero: mat(new THREE.Color('#d8d0c2'), { roughness: 0.9 }),
    asfalto: mat(new THREE.Color('#4c5055'), { roughness: 0.95 }), cancha: mat(new THREE.Color('#2f6fb3'), { roughness: 0.7 }), caucho: mat(new THREE.Color('#2f8f6a'), { roughness: 0.9 }),
    concreto: mat(new THREE.Color('#cfcac0'), { roughness: 0.9 }), muro: mat(new THREE.Color('#ece8e0'), { roughness: 0.85 }), techo: mat(new THREE.Color('#3b4147'), { roughness: 0.5, metalness: 0.4 }),
    malla: mat(new THREE.Color('#20252a'), { roughness: 0.6, transparent: true, opacity: 0.32, side: THREE.DoubleSide, depthWrite: false }),
    cerca: mat(new THREE.Color('#1f5a3a'), { roughness: 0.7 }), amarillo: mat(new THREE.Color('#f2c230'), { roughness: 0.5 }), oscuro: mat(new THREE.Color('#2a2f34'), { roughness: 0.6, metalness: 0.3 }),
    juego: [mat(new THREE.Color('#e8562f')), mat(new THREE.Color('#f2b632')), mat(new THREE.Color('#3b8fd9'))],
    carro: [mat(new THREE.Color('#d9dcdf'), { roughness: 0.35, metalness: 0.5 }), mat(new THREE.Color('#2b2f35'), { roughness: 0.35, metalness: 0.5 }), mat(new THREE.Color('#a8322d'), { roughness: 0.35, metalness: 0.5 }), mat(new THREE.Color('#2d5aa0'), { roughness: 0.35, metalness: 0.5 })],
  };
  const sombra = (o) => { o.traverse((k) => { if (k.isMesh) { k.castShadow = true; k.receiveShadow = true; } }); return o; };
  const add = (padre, geo, m) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; padre.add(o); return o; };

  // --- piso del lote: jardines, campo de juego en abanico, arcilla del cuadro y círculos
  add(piso, losa([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], 0.05), C.jardin);
  const abanico = [[0, -2]];
  for (let i = 0; i <= 48; i++) { const a = -Math.PI / 4 + (i / 48) * (Math.PI / 2), r = cerca(a); abanico.push([r * Math.sin(a), r * Math.cos(a)]); }
  add(campo, losa(abanico, 0.09), C.grama);
  // franjas de corte de la grama (alternan tono cada 6 m en el jardín)
  const franjas = [];
  for (let r = 24; r < 76; r += 12) { const arco = []; for (let i = 0; i <= 32; i++) { const a = -Math.PI / 4 + (i / 32) * (Math.PI / 2), rr = Math.min(r, cerca(a)), r2 = Math.min(r + 6, cerca(a)); arco.push([[rr * Math.sin(a), rr * Math.cos(a)], [r2 * Math.sin(a), r2 * Math.cos(a)]]); } franjas.push(losa([...arco.map((p) => p[0]), ...arco.map((p) => p[1]).reverse()], 0.1)); }
  add(campo, unir(franjas), C.grama2);
  // cuadro de arcilla: arco de 18,29 m alrededor del lanzador, que corta las líneas de foul a 17,7 m del home
  const rC = 18.29, cv = M.lanzador, vf = (cv + Math.sqrt(2 * rC * rC - cv * cv)) / 2;
  const cuadro = [[0, 0], [vf, vf]];
  for (let i = 0; i <= 32; i++) { const a0 = Math.atan2(vf - cv, vf), a = a0 + (i / 32) * (Math.PI - 2 * a0); cuadro.push([rC * Math.cos(a), cv + rC * Math.sin(a)]); }
  cuadro.push([-vf, vf]);
  add(campo, losa(cuadro, 0.12), C.arcilla);
  const circulo = (cx, cv2, r, n = 28) => Array.from({ length: n }, (_, i) => [cx + r * Math.cos((i / n) * 2 * Math.PI), cv2 + r * Math.sin((i / n) * 2 * Math.PI)]);
  add(campo, losa(circulo(0, 0, 4.2), 0.12), C.arcilla);
  // cal: líneas de foul, círculo del lanzador, cajas de bateo, bases y home
  const cal = [];
  [-1, 1].forEach((s) => cal.push(cinta([[0, 0], [s * M.cercaFoul * Math.SQRT1_2, M.cercaFoul * Math.SQRT1_2]], 0.1, 0.14)));
  cal.push(cinta([...circulo(0, cv, M.rLanzador, 40), [M.rLanzador, cv]], 0.08, 0.14));
  [-1, 1].forEach((s) => cal.push(cinta([[s * 0.45, -0.9], [s * 1.35, -0.9], [s * 1.35, 1.2], [s * 0.45, 1.2], [s * 0.45, -0.9]], 0.06, 0.14)));
  const lb = M.bases * Math.SQRT1_2;
  [[lb, lb], [0, M.homeSegunda], [-lb, lb]].forEach(([u, v]) => cal.push(new THREE.BoxGeometry(0.38, 0.08, 0.38).translate(u, 0.16, -v)));
  cal.push(losa([[-0.22, 0], [0.22, 0], [0.22, 0.22], [0, 0.43], [-0.22, 0.22]], 0.15));
  cal.push(new THREE.BoxGeometry(0.61, 0.06, 0.15).translate(0, 0.17, -cv));
  add(campo, unir(cal), C.cal);

  // --- cerca del jardín, postes de foul, malla de protección (backstop) y cerramiento del lote
  const cercaPts = abanico.slice(1);
  const muro = [];
  for (let i = 1; i < cercaPts.length; i++) {
    const [a, b] = [cercaPts[i - 1], cercaPts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    muro.push(new THREE.BoxGeometry(L + 0.05, 1.8, 0.18).rotateY(Math.atan2(b[1] - a[1], b[0] - a[0])).translate((a[0] + b[0]) / 2, 0.9, -(a[1] + b[1]) / 2));
  }
  sombra(add(obras, unir(muro), C.cerca));
  const pf = M.cercaFoul * Math.SQRT1_2;
  [-1, 1].forEach((s) => sombra(add(obras, new THREE.CylinderGeometry(0.12, 0.14, 9, 8).translate(s * pf, 4.5, -pf), C.amarillo)));
  const back = [];
  for (let i = 0; i <= 20; i++) { const a = Math.PI + (-0.75 + (i / 20) * 1.5); back.push([7.6 * Math.sin(a) * -1, 7.6 * Math.cos(a)]); }
  const red = [];
  for (let i = 1; i < back.length; i++) { const [a, b] = [back[i - 1], back[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]); red.push(new THREE.PlaneGeometry(L, 8).rotateY(Math.atan2(b[1] - a[1], b[0] - a[0])).translate((a[0] + b[0]) / 2, 4, -(a[1] + b[1]) / 2)); }
  add(obras, unir(red), C.malla);
  back.filter((_, i) => i % 4 === 0).forEach(([u, v]) => sombra(add(obras, new THREE.CylinderGeometry(0.08, 0.1, 8.3, 6).translate(u, 4.15, -v), C.oscuro)));
  // cerramiento perimetral (malla de 2,2 m) con el vano del acceso en la esquina suroccidental
  const per = [[u0 + 14, v0], [u1, v0], [u1, v1], [u0, v1], [u0, v0 + 6]];
  const cerr = [];
  for (let i = 1; i < per.length; i++) { const [a, b] = [per[i - 1], per[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]); cerr.push(new THREE.PlaneGeometry(L, 2.2).rotateY(Math.atan2(b[1] - a[1], b[0] - a[0])).translate((a[0] + b[0]) / 2, 1.1, -(a[1] + b[1]) / 2)); }
  add(obras, unir(cerr), C.malla);

  // --- dugouts (10 × 3 m) paralelos a las líneas, afuera del cuadro, con cubierta oscura
  [-1, 1].forEach((s) => {
    const d = new THREE.Group(), a = s * Math.PI / 4, cu = 15 * Math.sin(a) + s * 7 * Math.cos(Math.PI / 4), cvv = 15 * Math.cos(a) - 7 * Math.sin(Math.PI / 4);
    d.add(new THREE.Mesh(new THREE.BoxGeometry(10, 1.2, 3).translate(0, 0.6, 0), C.concreto));
    d.add(new THREE.Mesh(new THREE.BoxGeometry(10, 0.3, 0.3).translate(0, 2.6, 1.35), C.oscuro));
    d.add(new THREE.Mesh(new THREE.BoxGeometry(10.6, 0.18, 3.6).translate(0, 2.8, 0), C.techo));
    [-4.9, 4.9].forEach((x) => d.add(new THREE.Mesh(new THREE.BoxGeometry(0.15, 2.8, 3).translate(x, 1.4, 0), C.oscuro)));
    // largo paralelo a la línea de foul y el frente (con la baranda) mirando al campo
    d.position.set(cu, 0, -cvv); d.rotation.y = s > 0 ? (5 * Math.PI) / 4 : (3 * Math.PI) / 4;
    obras.add(sombra(d));
  });
  // --- graderías principales (20 × 4 m, 5 filas) detrás del home, con cubierta tensada encima
  const gr = graderia(0, -12.5, M.graderia[0], 5, Math.PI, C.concreto); obras.add(gr);
  cubierta.add(membrana(0, -14.4, 23, 7.5, 6.4, 0, { flecha: 1.4, m: new THREE.MeshStandardMaterial({ color: 0xf5f4f0, roughness: 0.55, side: THREE.DoubleSide }), mastil: C.oscuro }));
  // --- baños y vestidores (8 × 4 m) al suroriente
  const banos = new THREE.Group();
  banos.add(new THREE.Mesh(new THREE.BoxGeometry(8, 3, 4).translate(0, 1.5, 0), C.muro), new THREE.Mesh(new THREE.BoxGeometry(9, 0.25, 5).translate(0, 3.12, 0), C.techo));
  banos.position.set(u1 - 12, 0, -(v0 + 9)); obras.add(sombra(banos));
  // --- marcador «CASABE» detrás de la cerca del jardín central
  const marc = new THREE.Group();
  marc.add(new THREE.Mesh(new THREE.BoxGeometry(8.4, 3.8, 0.4).translate(0, 5.2, 0), C.oscuro));
  const pant = new THREE.Mesh(new THREE.PlaneGeometry(8, 3.5), new THREE.MeshBasicMaterial({ map: texturaMarcador() })); pant.position.set(0, 5.2, 0.21); marc.add(pant);
  [-3, 3].forEach((x) => marc.add(new THREE.Mesh(new THREE.BoxGeometry(0.3, 3.4, 0.3).translate(x, 1.7, 0), C.oscuro)));
  marc.position.set(0, 0, -Math.min(M.cercaCentro + 5, v1 - 2.2)); obras.add(sombra(marc));
  // --- parqueadero de 20 cupos (dos filas de 10) al suroccidente, con algunos carros
  const pq = [[u0 + 2, v0 + 8], [u0 + 18, v0 + 8], [u0 + 18, v0 + 34], [u0 + 2, v0 + 34]];
  add(piso, losa(pq, 0.08), C.asfalto);
  const rayas = [];
  for (let k = 0; k <= 10; k++) [u0 + 2, u0 + 13].forEach((u) => rayas.push(cinta([[u, v0 + 8.5 + k * 2.5], [u + 5, v0 + 8.5 + k * 2.5]], 0.1, 0.11)));
  add(piso, unir(rayas), C.cal);
  const carros = [];
  [0, 1, 3, 4, 6, 8, 9, 12, 14, 17].forEach((k, i) => { const fila = k < 10 ? 0 : 1, n = k % 10, u = u0 + (fila ? 15.5 : 4.5), v = v0 + 9.75 + n * 2.5; const c = new THREE.Group(); c.add(new THREE.Mesh(new THREE.BoxGeometry(4.3, 0.75, 1.8).translate(0, 0.62, 0), C.carro[i % 4]), new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.6, 1.65).translate(-0.2, 1.28, 0), C.carro[i % 4])); c.position.set(u, 0, -v); carros.push(sombra(c)); });
  carros.forEach((c) => obras.add(c));
  // --- cancha múltiple (22 × 12 m) en la esquina noroccidental, fuera de la cerca del jardín izquierdo, y zona infantil y
  // biosaludable al occidente, en territorio de foul (|u| > v) para que no quede dentro del campo
  const [cu0, cu1, cv0, cv1] = [u0 + 1, u0 + 23, v1 - 13, v1 - 1], cmu = (cu0 + cu1) / 2, cmv = (cv0 + cv1) / 2;
  const cm = [[cu0, cv0], [cu1, cv0], [cu1, cv1], [cu0, cv1]];
  add(piso, losa(cm, 0.1), C.cancha);
  const cmL = [cinta([...cm, cm[0]], 0.08, 0.12), cinta([[cmu, cv0], [cmu, cv1]], 0.08, 0.12), cinta([...Array.from({ length: 25 }, (_, i) => [cmu + 1.8 * Math.cos((i / 24) * 2 * Math.PI), cmv + 1.8 * Math.sin((i / 24) * 2 * Math.PI)])], 0.08, 0.12)];
  add(piso, unir(cmL), C.cal);
  [cu0 + 1, cu1 - 1].forEach((u) => sombra(add(obras, new THREE.CylinderGeometry(0.08, 0.08, 3.05, 6).translate(u, 1.5, -cmv), C.oscuro)));
  const zi = [[u0 + 1, v0 + 38], [u0 + 12, v0 + 38], [u0 + 12, v0 + 60], [u0 + 1, v0 + 60]];
  add(piso, losa(zi, 0.1), C.caucho);
  [[u0 + 4, v0 + 43, 0], [u0 + 9, v0 + 48, 1], [u0 + 4.5, v0 + 53, 2], [u0 + 9, v0 + 57, 0]].forEach(([u, v, k]) => sombra(add(obras, new THREE.BoxGeometry(2.4, 1.6 + k * 0.4, 1.2).translate(u, 0.8 + k * 0.2, -v), C.juego[k])));
  // --- sendero perimetral, plazoleta de acceso y portal con letrero
  const s = 3;
  add(piso, cinta([[u0 + 16, v0 + s / 2 + 0.5], [u1 - s / 2 - 0.5, v0 + s / 2 + 0.5], [u1 - s / 2 - 0.5, v1 - s / 2 - 0.5], [u0 + 18, v1 - s / 2 - 0.5]], s, 0.11), C.sendero);
  add(piso, losa([[u0, v0], [u0 + 16, v0], [u0 + 16, v0 + 8], [u0, v0 + 8]], 0.11), C.sendero);
  add(piso, losa([[-13, -21], [13, -21], [13, -3], [-13, -3]], 0.11), C.sendero);
  const portal = new THREE.Group();
  portal.add(new THREE.Mesh(new THREE.BoxGeometry(7, 3.2, 0.5).translate(5.2, 1.6, 0), C.concreto), new THREE.Mesh(new THREE.BoxGeometry(0.5, 3.4, 0.5).translate(0, 1.7, 0), C.oscuro), new THREE.Mesh(new THREE.BoxGeometry(5.6, 0.35, 1.2).translate(-2.5, 3.3, 0), C.oscuro));
  const letrero = document.createElement('canvas'); letrero.width = 512; letrero.height = 228;
  const lx = letrero.getContext('2d'); lx.fillStyle = '#d6d2c9'; lx.fillRect(0, 0, 512, 228); lx.fillStyle = '#23272b'; lx.font = 'bold 54px "Public Sans", Arial, sans-serif'; lx.textAlign = 'left';
  lx.fillText('CANCHA DE', 28, 72); lx.font = 'bold 74px "Public Sans", Arial, sans-serif'; lx.fillText('SÓFTBOL', 28, 146); lx.font = 'bold 54px "Public Sans", Arial, sans-serif'; lx.fillText('CASABE', 28, 206);
  const tl = new THREE.CanvasTexture(letrero); tl.colorSpace = THREE.SRGBColorSpace;
  const cartel = new THREE.Mesh(new THREE.PlaneGeometry(6.4, 2.85), new THREE.MeshBasicMaterial({ map: tl })); cartel.position.set(5.2, 1.65, 0.26); portal.add(cartel);
  portal.position.set(u0 + 3, 0, -(v0 + 0.3)); obras.add(sombra(portal));

  // --- torres de luz LED apuntando al cuadro, postes peatonales y verde: palmas en el borde y árboles en los jardines
  const foco = [0, 32];
  const T = [[22, 2], [-22, 2], [u1 - 3, 40], [u0 + 3, 40], [30, v1 - 4], [-30, v1 - 4]].map(([u, v]) => [u, v, foco[0], foco[1]]);
  luces.add(torresLuz(T, 19));
  luces.add(postes(aLoLargo([[u0 + 16, v0 + 2], [u1 - 2, v0 + 2], [u1 - 2, v1 - 2], [u0 + 18, v1 - 2]], 14), 4.2));
  const borde = aLoLargo([[u0 + 1, v0 + 1], [u1 - 1, v0 + 1], [u1 - 1, v1 - 1], [u0 + 1, v1 - 1], [u0 + 1, v0 + 10]], 9).map(([u, v]) => [u, v]);
  verde.add(palmas(borde.filter(([u, v]) => !(u < u0 + 17 && v < v0 + 9)), { alto: 8.5, semilla: 21 }));
  const jardines = [];
  for (let k = 0; k < 60; k++) { const a = -Math.PI / 4 + (k / 60) * (Math.PI / 2), r = cerca(a) + 4 + (k % 3) * 2.2; jardines.push([r * Math.sin(a), r * Math.cos(a)]); }
  verde.add(arboles(jardines.filter(([u, v]) => u > u0 + 2 && u < u1 - 2 && v < v1 - 2 && !(u < cu1 + 2 && v > cv0 - 2)), { alto: 7, semilla: 33 }));
  verde.add(arboles([[u1 - 6, v0 + 22], [u1 - 8, v0 + 30], [u1 - 5, v0 + 38], [u0 + 22, v0 + 14], [u0 + 26, v0 + 6], [18, -18], [-18, -18], [26, -12], [-26, -12]], { alto: 8, semilla: 41 }));

  raiz.userData.partes = { piso, campo, obras, cubierta, luces, verde };
  // puntos del contorno del lote en el modelo (para encuadrar) y los focos de la cámara
  raiz.updateMatrixWorld(true);
  const aModelo = (u, v) => { const p = new THREE.Vector3(u, 0, -v).applyMatrix4(raiz.matrixWorld); return [p.x, -p.z]; };
  raiz.userData.contorno = [[u0, v0], [u1, v0], [u1, v1], [u0, v1]].map(([u, v]) => aModelo(u, v));
  raiz.userData.aModelo = aModelo;
  return raiz;
}
