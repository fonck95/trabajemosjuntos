// Cancha de Sóftbol Casabe: el estadio renovado según el plano propuesto (home al sur), en un lote de 109 × 102,9 m: el
// de 109 × 110 m del plano no cabe exacto en la manzana del estadio actual y 102,9 m alcanzan para la cerca. Medidas
// reglamentarias de sóftbol: 18,29 m entre bases, 25,87 m de home a segunda, 13,11 m de home al lanzador, círculo del
// lanzador de 2,44 m de radio, cerca de 67,06 m en las líneas de foul a 76,20 m en el jardín central. Graderías de
// 20 × 4 m con cubierta tensada, dos dugouts de 10 × 3 m, baños y vestidores de 8 × 4 m, parqueadero de 20 cupos, cancha
// múltiple, zona infantil y biosaludable, marcador, torres de luz LED, sendero perimetral con palmas y portal de acceso.
// Se arma en un marco local con el home en el origen: u a la derecha (lado de primera base), v hacia el jardín central.
//
// Acabados como en los renders de la propuesta: césped con franjas de corte, arcilla del cuadro y pista de advertencia, cerca
// del jardín acolchada con remate amarillo, mallas eslabonadas, gradería con sillas y tres módulos de cubierta tensada, portal
// con letrero y silueta del bateador, pérgolas de acero y madera con mesas y luz LED a lo largo de los senderos de adoquín,
// jardineras con cordylines, helechos y heliconias, bancas, bolardos y canecas, guayacanes rosados y palmas, parque infantil
// con velaria, cancha múltiple con malla, parqueadero con carros, cebra y reductor, jugadores en el campo y público.
import { THREE, mat } from '../../core.js';
import { losa, cinta, prisma, graderia, membrana, torresLuz, postes, arboles, palmas, matas, jardin, bancas, bolardos, canecas, gente, carros, aLoLargo, unir, azar } from '../geo3d.js';
import { matT } from '../texturas.js';

export const MEDIDAS = {
  lote: [109, 102.9], homeAlSur: 22, bases: 18.29, homeSegunda: 25.87, lanzador: 13.11, rLanzador: 2.44, rBateo: 0.76,
  cercaFoul: 67.06, cercaCentro: 76.2, dugout: [10, 3], graderia: [20, 4], banos: [8, 4], cupos: 20,
};
// radio de la cerca según el ángulo desde el eje home → jardín central (67,06 m en las líneas de foul, 76,20 m al centro)
export const cerca = (a) => MEDIDAS.cercaFoul + (MEDIDAS.cercaCentro - MEDIDAS.cercaFoul) * Math.cos(2 * a) ** 2;

// marcador LED en español, como en los renders: CASABE, bola / strike / out y las carreras por entrada
function texturaMarcador() {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 448;
  const x = c.getContext('2d');
  x.fillStyle = '#101316'; x.fillRect(0, 0, 1024, 448);
  x.strokeStyle = '#2c3238'; x.lineWidth = 6; x.strokeRect(10, 10, 1004, 428);
  x.fillStyle = '#f4f1e8'; x.font = 'bold 104px Anton, Impact, sans-serif'; x.textAlign = 'center'; x.fillText('CASABE', 512, 120);
  x.font = '600 34px "IBM Plex Mono", monospace'; x.fillStyle = '#e9e6dc';
  x.textAlign = 'left'; x.fillText('BOLA', 64, 196); x.fillText('STRIKE', 420, 196); x.fillText('OUT', 800, 196);
  x.fillStyle = '#ffcf3a'; [[180, '2'], [580, '1'], [890, '1']].forEach(([px, t]) => x.fillText(t, px, 196));
  x.fillStyle = '#9aa3aa'; x.font = '600 28px "IBM Plex Mono", monospace'; x.fillText('1 2 3 4 5 6 7   C', 470, 262);
  x.font = '600 36px "IBM Plex Mono", monospace';
  [['VISITANTE', '0 0 1 0 0 2 0', '3', 318], ['LOCAL', '1 0 0 2 1 0 0', '4', 390]].forEach(([eq, ent, tot, y]) => {
    x.fillStyle = '#e9e6dc'; x.fillText(eq, 64, y); x.fillStyle = '#ffcf3a'; x.fillText(ent, 470, y); x.fillStyle = '#ff6a3d'; x.fillText(tot, 800, y);
  });
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}
// letrero del portal: muro gris carbón con el nombre y la silueta blanca del bateador
function texturaPortal() {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 460;
  const x = c.getContext('2d');
  const g = x.createLinearGradient(0, 0, 0, 460); g.addColorStop(0, '#2a2e32'); g.addColorStop(1, '#1d2023');
  x.fillStyle = g; x.fillRect(0, 0, 1024, 460);
  x.fillStyle = 'rgba(255,255,255,0.05)'; for (let i = 0; i < 1024; i += 64) x.fillRect(i, 0, 2, 460);
  x.fillStyle = '#ece8df'; x.textAlign = 'left';
  x.font = '600 62px "Public Sans", Arial, sans-serif'; x.fillText('CANCHA DE SÓFTBOL', 70, 170);
  x.fillStyle = '#e8c15a'; x.font = 'bold 150px Anton, Impact, sans-serif'; x.fillText('CASABE', 66, 330);
  // bateador: cabeza, casco, tronco, piernas abiertas y el bate arriba
  x.strokeStyle = '#ece8df'; x.fillStyle = '#ece8df'; x.lineCap = 'round'; x.lineJoin = 'round';
  const bx = 830, by = 120;
  x.beginPath(); x.arc(bx, by, 26, 0, Math.PI * 2); x.fill();
  x.lineWidth = 30; x.beginPath(); x.moveTo(bx - 4, by + 34); x.lineTo(bx - 22, by + 150); x.stroke();
  x.lineWidth = 22; x.beginPath(); x.moveTo(bx - 22, by + 150); x.lineTo(bx - 80, by + 280); x.moveTo(bx - 22, by + 150); x.lineTo(bx + 40, by + 210); x.lineTo(bx + 36, by + 290); x.stroke();
  x.lineWidth = 16; x.beginPath(); x.moveTo(bx - 6, by + 60); x.lineTo(bx + 40, by + 70); x.lineTo(bx + 60, by + 30); x.stroke();
  x.lineWidth = 12; x.beginPath(); x.moveTo(bx + 60, by + 30); x.lineTo(bx + 30, by - 100); x.stroke();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}

// { home: [x, y] en el modelo, rumbo: grados desde el norte del eje home → jardín central }
export function canchaSoftbol({ home, rumbo = 0 }) {
  const raiz = new THREE.Group(), M = MEDIDAS;
  raiz.position.set(home[0], 0, -home[1]); raiz.rotation.y = -THREE.MathUtils.degToRad(rumbo);
  raiz.updateMatrixWorld(true);
  const [W, D] = M.lote, v0 = -M.homeAlSur, v1 = D - M.homeAlSur, u0 = -W / 2, u1 = W / 2;
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const piso = capa('piso'), campo = capa('campo'), obras = capa('obras'), cubierta = capa('cubierta'), luces = capa('luces'), verde = capa('verde'), personas = capa('gente');
  // dirección del eje home → jardín central en el mundo (para las franjas de corte del césped)
  const eje = new THREE.Vector3(0, 0, -1).applyQuaternion(raiz.quaternion);
  const C = {
    jardin: matT('cesped', { color: '#e6efdc' }),
    grama: matT('cesped', { color: '#cfe6b8', franjas: { origen: [home[0], -home[1]], dir: [eje.x, eje.z], ancho: 9, k: 0.1, k2: 0.04 } }),
    arcilla: matT('arcilla'), pista: matT('arcilla', { color: '#d9c7b4' }),
    cal: mat(new THREE.Color('#fbfbf7'), { roughness: 0.9 }), sendero: matT('adoquin'), plaza: matT('adoquin', { color: '#efe9e0' }),
    asfalto: matT('asfalto'), cancha: matT('caucho', { color: '#2f6fb8', escala: 0.9, relieve: 0 }), cancha2: matT('caucho', { color: '#5d97d6', escala: 0.9, relieve: 0 }),
    caucho: matT('caucho', { color: '#1f9e8f' }), caucho2: matT('caucho', { color: '#f2c230' }),
    concreto: matT('concreto'), muro: matT('estuco', { color: '#f1ede4' }), techo: matT('zinc', { color: '#565d63', metalness: 0.6 }),
    malla: matT('malla', { color: '#2f5d3d' }), mallaNegra: matT('malla', { color: '#25292c' }),
    cerca: mat(new THREE.Color('#1f4f37'), { roughness: 0.75 }), amarillo: mat(new THREE.Color('#f2c230'), { roughness: 0.45 }), oscuro: mat(new THREE.Color('#25292d'), { roughness: 0.45, metalness: 0.55 }),
    madera: matT('madera'), tierra: mat(new THREE.Color('#4a3a2c'), { roughness: 1 }), silla: mat(new THREE.Color('#ffffff'), { roughness: 0.5 }),
    lona: matT('membrana', { color: '#efe6d2' }), led: new THREE.MeshBasicMaterial({ color: 0xffe2a6 }),
    juego: ['#e8562f', '#2fa75a', '#f2b632', '#3b8fd9'].map((c) => mat(new THREE.Color(c), { roughness: 0.45 })),
  };
  const sombra = (o) => { o.traverse((k) => { if (k.isMesh) { k.castShadow = true; k.receiveShadow = true; } }); return o; };
  const add = (padre, geo, m) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; padre.add(o); return o; };
  const solido = (padre, geo, m) => { const o = add(padre, geo, m); o.castShadow = true; return o; };
  const caja = (w, h, d, u, y, v, rot = 0) => new THREE.BoxGeometry(w, h, d).rotateY(rot).translate(u, y + h / 2, -v);
  // punto a s metros por la línea de foul (lado +1 primera, −1 tercera) y o metros afuera de ella
  const enLinea = (lado, s, o) => [lado * (s + o) * Math.SQRT1_2, (s - o) * Math.SQRT1_2];
  const rotLinea = (lado) => (lado > 0 ? Math.PI / 4 : -Math.PI / 4);   // giro que alinea el eje local x con la línea
  const haciaLinea = (lado) => (lado > 0 ? (5 * Math.PI) / 4 : (3 * Math.PI) / 4);   // giro con el frente local (+z) hacia la línea
  const r = azar(29);

  // --- piso del lote: césped de jardines
  add(piso, losa([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], 0.05), C.jardin);
  // --- campo: abanico de césped con franjas, pista de advertencia, arcilla del cuadro y círculos
  const abanico = [[0, -2]];
  for (let i = 0; i <= 64; i++) { const a = -Math.PI / 4 + (i / 64) * (Math.PI / 2), rr = cerca(a); abanico.push([rr * Math.sin(a), rr * Math.cos(a)]); }
  add(campo, losa(abanico, 0.09), C.grama);
  const pista = [];
  for (let i = 0; i <= 64; i++) { const a = -Math.PI / 4 + (i / 64) * (Math.PI / 2), rr = cerca(a); pista.push([rr * Math.sin(a), rr * Math.cos(a)]); }
  for (let i = 64; i >= 0; i--) { const a = -Math.PI / 4 + (i / 64) * (Math.PI / 2), rr = cerca(a) - 3.6; pista.push([rr * Math.sin(a), rr * Math.cos(a)]); }
  add(campo, losa(pista, 0.11), C.pista);
  // cuadro de arcilla: arco de 18,29 m alrededor del lanzador, que corta las líneas de foul a 17,7 m del home
  const rC = 18.29, cv = M.lanzador, vf = (cv + Math.sqrt(2 * rC * rC - cv * cv)) / 2;
  const cuadro = [[0, 0], [vf, vf]];
  for (let i = 0; i <= 40; i++) { const a0 = Math.atan2(vf - cv, vf), a = a0 + (i / 40) * (Math.PI - 2 * a0); cuadro.push([rC * Math.cos(a), cv + rC * Math.sin(a)]); }
  cuadro.push([-vf, vf]);
  add(campo, losa(cuadro, 0.12), C.arcilla);
  const circulo = (cx, cv2, rr, n = 32) => Array.from({ length: n }, (_, i) => [cx + rr * Math.cos((i / n) * 2 * Math.PI), cv2 + rr * Math.sin((i / n) * 2 * Math.PI)]);
  add(campo, losa(circulo(0, 0, 4.4), 0.12), C.arcilla);
  [-1, 1].forEach((s) => add(campo, losa(circulo(s * 11.5, -3.2, 0.76, 20), 0.125), C.arcilla));   // círculos de espera
  // cal: líneas de foul, círculo del lanzador, cajas de bateo y del receptor, bases, home y la goma
  const cal = [];
  [-1, 1].forEach((s) => cal.push(cinta([[0, 0], [s * M.cercaFoul * Math.SQRT1_2, M.cercaFoul * Math.SQRT1_2]], 0.1, 0.14)));
  cal.push(cinta([...circulo(0, cv, M.rLanzador, 48), [M.rLanzador, cv]], 0.08, 0.14));
  [-1, 1].forEach((s) => cal.push(cinta([[s * 0.45, -0.9], [s * 1.35, -0.9], [s * 1.35, 1.2], [s * 0.45, 1.2], [s * 0.45, -0.9]], 0.06, 0.14)));
  cal.push(cinta([[-0.45, -0.9], [-0.45, -3], [0.45, -3], [0.45, -0.9]], 0.06, 0.14));
  [-1, 1].forEach((s) => cal.push(cinta([[s * 0.76 + 11.5 * s, -3.2], ...circulo(s * 11.5, -3.2, 0.76, 20).slice(1), [s * 0.76 + 11.5 * s, -3.2]], 0.05, 0.135)));
  const lb = M.bases * Math.SQRT1_2;
  [[lb, lb], [0, M.homeSegunda], [-lb, lb]].forEach(([u, v]) => cal.push(new THREE.BoxGeometry(0.38, 0.09, 0.38).rotateY(Math.PI / 4).translate(u, 0.17, -v)));
  cal.push(losa([[0, 0], [0.22, 0.22], [0.22, 0.43], [-0.22, 0.43], [-0.22, 0.22]], 0.15));   // punta atrás, lado plano al lanzador
  cal.push(new THREE.BoxGeometry(0.61, 0.06, 0.15).translate(0, 0.17, -cv));
  add(campo, unir(cal), C.cal);

  // --- cerca del jardín: muro acolchado verde con remate amarillo y postes de foul
  const cercaPts = abanico.slice(1), muro = [], remate = [];
  for (let i = 1; i < cercaPts.length; i++) {
    const [a, b] = [cercaPts[i - 1], cercaPts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), ang = Math.atan2(b[1] - a[1], b[0] - a[0]), cx = (a[0] + b[0]) / 2, cz = -(a[1] + b[1]) / 2;
    muro.push(new THREE.BoxGeometry(L + 0.05, 1.8, 0.22).rotateY(ang).translate(cx, 0.9, cz));
    remate.push(new THREE.BoxGeometry(L + 0.05, 0.12, 0.3).rotateY(ang).translate(cx, 1.86, cz));
  }
  solido(obras, unir(muro), C.cerca); solido(obras, unir(remate), C.amarillo);
  const pf = M.cercaFoul * Math.SQRT1_2;
  [-1, 1].forEach((s) => solido(obras, unir([new THREE.CylinderGeometry(0.12, 0.14, 9.5, 10).translate(s * pf, 4.75, -pf), new THREE.BoxGeometry(0.05, 6, 1.2).rotateY(s * Math.PI / 4).translate(s * pf + s * 0.5, 6, -pf + 0.5)]), C.amarillo));
  // --- mallas eslabonadas: backstop de 8 m detrás del home y cercas de 1,8 m frente a los dugouts hasta los postes de foul
  const malla = (pts, alto, m, { poste = 3, base = 0, riel = C.amarillo } = {}) => {
    const g = new THREE.Group(), planos = [], postesG = [], rieles = [];
    for (let i = 1; i < pts.length; i++) {
      const [a, b] = [pts[i - 1], pts[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), ang = Math.atan2(b[1] - a[1], b[0] - a[0]), cx = (a[0] + b[0]) / 2, cz = -(a[1] + b[1]) / 2;
      planos.push(new THREE.PlaneGeometry(L, alto).rotateY(ang).translate(cx, base + alto / 2, cz));
      rieles.push(new THREE.CylinderGeometry(0.035, 0.035, L, 6).rotateZ(Math.PI / 2).rotateY(ang).translate(cx, base + alto, cz));
      for (let s = 0; s < L; s += poste) postesG.push(new THREE.CylinderGeometry(0.04, 0.045, alto + base, 6).translate(a[0] + ((b[0] - a[0]) * s) / L, (alto + base) / 2, -(a[1] + ((b[1] - a[1]) * s) / L)));
    }
    const ul = pts[pts.length - 1]; postesG.push(new THREE.CylinderGeometry(0.04, 0.045, alto + base, 6).translate(ul[0], (alto + base) / 2, -ul[1]));
    add(g, unir(planos), m); solido(g, unir(postesG), C.oscuro); solido(g, unir(rieles), riel);
    return g;
  };
  const back = [];
  for (let i = 0; i <= 20; i++) { const a = Math.PI + (-0.75 + (i / 20) * 1.5); back.push([-7.6 * Math.sin(a), 7.6 * Math.cos(a)]); }
  obras.add(malla(back, 8, C.mallaNegra, { poste: 2.2, riel: C.oscuro }));
  [-1, 1].forEach((lado) => obras.add(malla([back[lado > 0 ? 20 : 0], enLinea(lado, 8, 5.4), enLinea(lado, 22, 5.4), enLinea(lado, 66.8, 0.35)], 1.8, C.malla)));
  // --- cerramiento perimetral (malla de 2,2 m sobre sardinel) con el vano del acceso en la esquina suroccidental
  const per = [[u0 + 14, v0], [u1, v0], [u1, v1], [u0, v1], [u0, v0 + 6]];
  obras.add(malla(per, 2.2, C.malla, { poste: 3, base: 0.3, riel: C.cerca }));
  const sard = [];
  for (let i = 1; i < per.length; i++) { const [a, b] = [per[i - 1], per[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]); sard.push(caja(L + 0.3, 0.3, 0.25, (a[0] + b[0]) / 2, 0, (a[1] + b[1]) / 2, Math.atan2(b[1] - a[1], b[0] - a[0]))); }
  solido(obras, unir(sard), C.concreto);

  // --- dugouts (10 × 3 m) paralelos a las líneas, afuera del cuadro: muros, banca, baranda y cubierta oscura volada
  [-1, 1].forEach((lado) => {
    const d = new THREE.Group();
    d.add(new THREE.Mesh(unir([new THREE.BoxGeometry(10, 2.5, 0.25).translate(0, 1.25, -1.4), new THREE.BoxGeometry(0.25, 2.5, 3).translate(-4.9, 1.25, 0), new THREE.BoxGeometry(0.25, 2.5, 3).translate(4.9, 1.25, 0)]), C.concreto));
    d.add(new THREE.Mesh(new THREE.BoxGeometry(10, 0.08, 3).translate(0, 0.04, 0), C.concreto));
    d.add(new THREE.Mesh(unir([new THREE.BoxGeometry(9, 0.07, 0.45).translate(0, 0.46, -1.05), new THREE.BoxGeometry(9, 0.5, 0.06).translate(0, 0.8, -1.26)]), C.madera));
    d.add(new THREE.Mesh(unir([new THREE.BoxGeometry(9.6, 0.06, 0.06).translate(0, 1.05, 1.42), ...[-4.5, -1.5, 1.5, 4.5].map((x) => new THREE.BoxGeometry(0.06, 1.05, 0.06).translate(x, 0.52, 1.42))]), C.oscuro));
    d.add(new THREE.Mesh(new THREE.BoxGeometry(10.8, 0.16, 3.9).translate(0, 2.62, 0.3), C.techo));
    const [cu, cvv] = enLinea(lado, 15, 7);
    d.position.set(cu, 0, -cvv); d.rotation.y = lado > 0 ? (5 * Math.PI) / 4 : (3 * Math.PI) / 4;
    obras.add(sombra(d));
  });
  // --- graderías principales (20 × 4 m, 5 filas) detrás del home, con sillas, barandas, muro de fondo y escaleras
  const gr = graderia(0, -12.5, M.graderia[0], 5, Math.PI, C.concreto); obras.add(gr);
  const sillas = [], publico = [], seatG = unir([new THREE.BoxGeometry(0.44, 0.08, 0.42).translate(0, 0.42, 0.05), new THREE.BoxGeometry(0.44, 0.42, 0.06).rotateX(-0.12).translate(0, 0.66, -0.17)]);
  for (let f = 0; f < 5; f++) for (let k = 0; k < 36; k++) {
    const u = -9.2 + k * 0.52 + (k >= 18 ? 0.6 : 0) - (k < 18 ? 0.6 : 0), v = -12.5 - 0.8 * f - 0.42, h = 0.42 * (f + 1);
    if (Math.abs(u) < 0.6) continue;
    sillas.push(Object.assign([u, v, Math.PI], { h }));
    if (r() < 0.5) publico.push(Object.assign([u, v + 0.05, Math.PI], { h: h + 0.06 }));
  }
  const sil = new THREE.InstancedMesh(seatG, C.silla, sillas.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI), azul = new THREE.Color('#1f5fa8'), gris = new THREE.Color('#d9dcdf');
  sillas.forEach(([u, v], i) => { m4.compose(new THREE.Vector3(u, sillas[i].h, -v), q, new THREE.Vector3(1, 1, 1)); sil.setMatrixAt(i, m4); sil.setColorAt(i, (i % 36) % 9 < 7 ? azul : gris); });
  sil.castShadow = true; sil.receiveShadow = true; sil.computeBoundingSphere(); obras.add(sil);
  solido(obras, unir([caja(21, 1.2, 0.25, 0, 2.1, -16.6), caja(0.25, 3.3, 4.2, -10.4, 0, -14.4), caja(0.25, 3.3, 4.2, 10.4, 0, -14.4)]), C.concreto);
  solido(obras, unir([caja(20, 0.05, 0.05, 0, 1.0, -12.4), ...Array.from({ length: 11 }, (_, k) => caja(0.05, 1.0, 0.05, -10 + k * 2, 0, -12.4))]), C.oscuro);
  // --- cubierta tensada: tres módulos de lona en paraboloide sobre mástiles, de 7,8 m cada uno
  const lonaM = C.lona;
  [-7.8, 0, 7.8].forEach((u, i) => cubierta.add(membrana(u, -14.6, 7.9, 7.8, 6.6 + (i === 1 ? 0.5 : 0), 0, { flecha: i % 2 ? -1.5 : 1.5, m: lonaM, mastil: C.oscuro })));
  // --- baños y vestidores (8 × 4 m) al suroriente: muros de pañete con zócalo de ladrillo, puertas y cubierta a cuatro aguas
  const banos = new THREE.Group(), hip = new THREE.ConeGeometry(6.4, 1.6, 4, 1).rotateY(Math.PI / 4).scale(1.05, 1, 0.55).translate(0, 3.8, 0);
  banos.add(new THREE.Mesh(new THREE.BoxGeometry(8, 3, 4).translate(0, 1.5, 0), C.muro), new THREE.Mesh(new THREE.BoxGeometry(8.04, 0.9, 4.04).translate(0, 0.45, 0), matT('ladrillo')), new THREE.Mesh(hip, C.techo));
  banos.add(new THREE.Mesh(unir([-2.4, 0.4, 2.4].map((x) => new THREE.BoxGeometry(1, 2.1, 0.08).translate(x, 1.05, 2.03))), C.madera));
  banos.add(new THREE.Mesh(new THREE.BoxGeometry(8.2, 0.12, 1.4).translate(0, 2.7, 2.6), C.concreto));
  banos.position.set(u1 - 12, 0, -(v0 + 9)); obras.add(sombra(banos));
  // --- marcador «CASABE» detrás de la cerca del jardín central, sobre una estructura de acero
  const marc = new THREE.Group();
  marc.add(new THREE.Mesh(new THREE.BoxGeometry(8.6, 4, 0.45).translate(0, 5.3, 0), C.oscuro));
  const pant = new THREE.Mesh(new THREE.PlaneGeometry(8.2, 3.6), new THREE.MeshBasicMaterial({ map: texturaMarcador() })); pant.position.set(0, 5.3, 0.235); marc.add(pant);
  marc.add(new THREE.Mesh(unir([-3, 3].map((x) => new THREE.BoxGeometry(0.32, 3.4, 0.32).translate(x, 1.7, 0))), C.oscuro));
  marc.position.set(0, 0, -(M.cercaCentro + 0.7)); obras.add(sombra(marc));

  // --- parqueadero de 20 cupos (dos filas de 10) al suroccidente: asfalto, bordillo, demarcación, flechas, cebra y reductor
  const pq = [[u0 + 2, v0 + 8], [u0 + 18, v0 + 8], [u0 + 18, v0 + 34], [u0 + 2, v0 + 34]];
  add(piso, losa(pq, 0.08), C.asfalto);
  solido(obras, unir([caja(16.4, 0.15, 0.2, u0 + 10, 0, v0 + 7.9), caja(16.4, 0.15, 0.2, u0 + 10, 0, v0 + 34.1), caja(0.2, 0.15, 26, u0 + 1.9, 0, v0 + 21), caja(0.2, 0.15, 26, u0 + 18.1, 0, v0 + 21)]), C.concreto);
  const rayas = [];
  for (let k = 0; k <= 10; k++) [u0 + 2, u0 + 13].forEach((u) => rayas.push(cinta([[u, v0 + 8.5 + k * 2.5], [u + 5, v0 + 8.5 + k * 2.5]], 0.1, 0.11)));
  const flecha = (u, v, s) => losa([[u - 0.25, v], [u + 0.25, v], [u + 0.25, v + s * 1.6], [u + 0.7, v + s * 1.6], [u, v + s * 2.6], [u - 0.7, v + s * 1.6], [u - 0.25, v + s * 1.6]].map(([a, b]) => [a, b]), 0.11);
  rayas.push(flecha(u0 + 10, v0 + 14, 1), flecha(u0 + 10, v0 + 27, 1));
  for (let k = 0; k < 6; k++) rayas.push(losa([[u0 + 18.4, v0 + 3 + k * 0.9], [u0 + 21.6, v0 + 3 + k * 0.9], [u0 + 21.6, v0 + 3.45 + k * 0.9], [u0 + 18.4, v0 + 3.45 + k * 0.9]], 0.125));   // cebra hacia el sendero
  add(piso, unir(rayas), C.cal);
  const reductor = [];
  for (let k = 0; k < 8; k++) reductor.push(caja(0.9, 0.08, 0.5, u0 + 3.0 + k * 0.95 + 4.2, 0.08, v0 + 9.4));
  solido(obras, unir(reductor.filter((_, k) => k % 2 === 0)), C.amarillo); solido(obras, unir(reductor.filter((_, k) => k % 2 === 1)), C.oscuro);
  const lugares = [0, 1, 3, 4, 6, 8, 9, 11, 12, 14, 15, 17, 19].map((k) => { const fila = k < 10 ? 0 : 1, n = k % 10; return [u0 + (fila ? 15.5 : 4.5), v0 + 9.75 + n * 2.5, fila ? Math.PI : 0]; });
  obras.add(carros(lugares, { semilla: 7 }));

  // --- cancha múltiple (22 × 12 m) en la esquina noroccidental: piso acrílico azul, zonas claras, aros y malla de 4 m
  const [cu0, cu1, cv0, cv1] = [u0 + 1, u0 + 23, v1 - 13, v1 - 1], cmu = (cu0 + cu1) / 2, cmv = (cv0 + cv1) / 2;
  const cm = [[cu0, cv0], [cu1, cv0], [cu1, cv1], [cu0, cv1]];
  add(piso, losa(cm, 0.1), C.cancha);
  add(piso, unir([losa([[cu0 + 1, cmv - 2.4], [cu0 + 6.8, cmv - 1.8], [cu0 + 6.8, cmv + 1.8], [cu0 + 1, cmv + 2.4]], 0.11), losa([[cu1 - 1, cmv - 2.4], [cu1 - 6.8, cmv - 1.8], [cu1 - 6.8, cmv + 1.8], [cu1 - 1, cmv + 2.4]], 0.11)]), C.cancha2);
  const cmL = [cinta([...cm.map(([u, v]) => [u + (u < cmu ? 1 : -1), v + (v < cmv ? 1 : -1)]), [cu0 + 1, cv0 + 1]], 0.08, 0.12), cinta([[cmu, cv0 + 1], [cmu, cv1 - 1]], 0.08, 0.12), cinta(circulo(cmu, cmv, 1.8, 33), 0.08, 0.12)];
  [-1, 1].forEach((s) => cmL.push(cinta(Array.from({ length: 17 }, (_, i) => { const a = -Math.PI / 2 + (i / 16) * Math.PI; return [cmu + s * (8.8 - 4.4 * Math.cos(a)), cmv + 4.4 * Math.sin(a)]; }), 0.08, 0.12)));
  add(piso, unir(cmL), C.cal);
  [-1, 1].forEach((s) => {
    const u = cmu + s * 10.4;
    solido(obras, unir([caja(0.14, 3.2, 0.14, u + s * 0.6, 0, cmv), caja(0.9, 0.1, 0.1, u + s * 0.15, 3.0, cmv)]), C.oscuro);
    solido(obras, caja(0.06, 1.05, 1.8, u - s * 0.25, 2.75, cmv), C.muro);
  });
  obras.add(malla([[cu0, cv0], [cu1, cv0], [cu1, cv1], [cu0, cv1], [cu0, cv0]], 4, C.malla, { poste: 3, riel: C.cerca }));

  // --- zona infantil al occidente (territorio de foul): piso de caucho con círculos, juego con torres, toboganes, red y velaria
  const zi = [[u0 + 1, v0 + 38], [u0 + 12, v0 + 38], [u0 + 12, v0 + 60], [u0 + 1, v0 + 60]];
  add(piso, losa(zi, 0.1), C.caucho);
  add(piso, unir([losa(circulo(u0 + 6.5, v0 + 50, 2.6, 28), 0.11), losa(circulo(u0 + 5, v0 + 43, 1.6, 24), 0.11), losa(circulo(u0 + 8.5, v0 + 56, 1.8, 24), 0.11)]), C.caucho2);
  solido(piso, unir([caja(11.4, 0.3, 0.2, u0 + 6.5, 0, v0 + 37.9), caja(11.4, 0.3, 0.2, u0 + 6.5, 0, v0 + 60.1), caja(0.2, 0.3, 22.4, u0 + 12.1, 0, v0 + 49)]), C.concreto);
  const juego = new THREE.Group(), [ju, jv] = [u0 + 6.5, v0 + 50.5];
  [[-1.6, -1.6, 0, 3.2], [1.6, 1.6, 1, 3.6]].forEach(([du, dv, k, h]) => {
    const t = new THREE.Group(); t.position.set(ju + du, 0, -(jv + dv));
    t.add(new THREE.Mesh(unir([[-0.8, -0.8], [0.8, -0.8], [-0.8, 0.8], [0.8, 0.8]].map(([x, z]) => new THREE.BoxGeometry(0.12, h, 0.12).translate(x, h / 2, z))), C.juego[2]));
    t.add(new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.12, 1.7).translate(0, 1.5, 0), C.madera));
    t.add(new THREE.Mesh(unir([new THREE.BoxGeometry(1.7, 0.6, 0.06).translate(0, 1.85, 0.82), new THREE.BoxGeometry(0.06, 0.6, 1.7).translate(-0.82, 1.85, 0)]), C.juego[k === 0 ? 3 : 2]));
    t.add(new THREE.Mesh(new THREE.ConeGeometry(1.35, 1.1, 4).rotateY(Math.PI / 4).translate(0, h + 0.5, 0), C.juego[k]));
    juego.add(t);
  });
  juego.add(new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.1, 2.2).translate(ju, 1.5, -jv), C.madera));
  const tobogan = (u, v, dir, m) => { const L = 3.2, g = new THREE.BoxGeometry(0.7, 0.08, L).translate(0, 0, L / 2).rotateX(0.45); const o = new THREE.Mesh(g, m); o.position.set(u, 1.5, -v); o.rotation.y = dir; return o; };
  juego.add(tobogan(ju - 1.6, jv - 2.45, 0, C.juego[0]), tobogan(ju + 1.6, jv + 2.45, Math.PI, C.juego[3]));
  juego.add(new THREE.Mesh(unir([new THREE.BoxGeometry(0.06, 1.6, 0.06).translate(ju + 2.6, 0.8, -(jv - 0.4)), new THREE.BoxGeometry(0.06, 1.6, 0.06).translate(ju + 2.6, 0.8, -(jv + 0.6)), ...[0.3, 0.6, 0.9, 1.2].map((y) => new THREE.BoxGeometry(0.05, 0.05, 1.0).translate(ju + 2.6, y, -(jv + 0.1)))]), C.juego[2]));
  const red = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 1.8).rotateX(-0.5).translate(ju - 2.7, 0.75, -(jv + 0.9)), C.mallaNegra); juego.add(red);
  obras.add(sombra(juego));
  // velaria (lona tensada) sobre postes negros
  cubierta.add(membrana(ju, jv, 9.6, 10.5, 4.6, 0.2, { flecha: 1.1, m: C.lona, mastil: C.oscuro }));
  // biosaludable: tres máquinas al sur de la zona infantil
  [[u0 + 3.5, v0 + 40.5], [u0 + 6.5, v0 + 40.5], [u0 + 9.5, v0 + 40.5]].forEach(([u, v], i) => solido(obras, unir([new THREE.CylinderGeometry(0.07, 0.07, 1.9, 8).translate(u, 0.95, -v), new THREE.TorusGeometry(0.45, 0.04, 6, 16).rotateY(i).translate(u, 1.3, -v), new THREE.CylinderGeometry(0.05, 0.05, 1.2, 6).rotateZ(Math.PI / 2).rotateY(i).translate(u, 0.6, -v)]), C.juego[i % 2 ? 2 : 1]));

  // --- senderos de adoquín: perimetral, plaza del acceso, plaza de la gradería y paseos junto a las cercas de foul
  const s = 3, ruta = [[u0 + 16, v0 + s / 2 + 0.5], [u1 - s / 2 - 0.5, v0 + s / 2 + 0.5], [u1 - s / 2 - 0.5, v1 - s / 2 - 0.5], [cu1 + 2, v1 - s / 2 - 0.5]];
  const paseo = (lado) => [enLinea(lado, -2, 10.5), enLinea(lado, 8, 9.2), enLinea(lado, 24, 9.2), enLinea(lado, lado > 0 ? 52 : 50, 9.2)];
  const paseos = [paseo(1), paseo(-1)];
  add(piso, unir([cinta(ruta, s, 0.11), ...paseos.map((p) => cinta(p, 3.2, 0.115)), cinta([enLinea(1, 52, 9.2), [u1 - 2, 30.4]], 3, 0.112)]), C.sendero);
  add(piso, unir([losa([[u0, v0], [u0 + 16, v0], [u0 + 16, v0 + 8], [u0, v0 + 8]], 0.11), losa([[-14, -21], [14, -21], [14, -6.5], [-14, -6.5]], 0.11)]), C.plaza);
  // jardineras de borde de concreto con plantas tropicales a lo largo de los senderos y frente a la gradería
  const jardinera = (pts, ancho = 1.8, semilla = 1) => {
    const izq = [], der = [];
    pts.forEach((p, i) => { const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)], L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, nx = -(b[1] - a[1]) / L, ny = (b[0] - a[0]) / L; izq.push([p[0] + nx * ancho / 2, p[1] + ny * ancho / 2]); der.push([p[0] - nx * ancho / 2, p[1] - ny * ancho / 2]); });
    const poly = [...izq, ...der.reverse()];
    solido(piso, prisma(poly, 0.42), C.concreto);
    add(piso, cinta(pts, ancho - 0.36, 0.425), C.tierra);
    const g = jardin(poly, { densidad: 1.5, semilla });
    return g;
  };
  const suaveL = (pts, n = 18) => { const c = new THREE.CatmullRomCurve3(pts.map(([u, v]) => new THREE.Vector3(u, v, 0)), false, 'centripetal'); return c.getPoints(n).map((p) => [p.x, p.y]); };
  [1, -1].forEach((lado, i) => {
    verde.add(jardinera(suaveL([enLinea(lado, 24, 17.3), enLinea(lado, 33, 18.1), enLinea(lado, lado > 0 ? 44 : 40, 17.1)]), 1.6, 40 + i));
    verde.add(jardinera(suaveL([enLinea(lado, 2, 12.2), enLinea(lado, 8, 11.4), enLinea(lado, 14, 11.6)]), 1.4, 50 + i));
  });
  verde.add(jardinera(suaveL([[u1 - 8, v0 + 20], [u1 - 7.4, v0 + 40], [u1 - 8.2, v0 + 62], [u1 - 7.6, v0 + 84]], 30), 1.8, 61));
  verde.add(jardinera([[-13.5, -20.4], [-13.5, -7.2]], 1.2, 62), jardinera([[13.5, -20.4], [13.5, -7.2]], 1.2, 63));

  // --- pérgolas de acero negro con techo de listones de madera, cinta LED, mesas de picnic y celosía, junto a los paseos
  const pergola = (lado) => {
    const g = new THREE.Group(), largo = 18, ancho = 4.6, alto = 2.9, est = [], list = [], mesas = [], led = [];
    for (let x = -largo / 2; x <= largo / 2 + 0.01; x += 3.6) [-ancho / 2, ancho / 2].forEach((z) => est.push(new THREE.BoxGeometry(0.14, alto, 0.14).translate(x, alto / 2, z)));
    [-ancho / 2, ancho / 2].forEach((z) => est.push(new THREE.BoxGeometry(largo + 0.6, 0.28, 0.16).translate(0, alto + 0.14, z)));
    for (let x = -largo / 2; x <= largo / 2 + 0.01; x += 1.8) est.push(new THREE.BoxGeometry(0.1, 0.22, ancho + 0.8).translate(x, alto + 0.39, 0));
    for (let z = -ancho / 2 - 0.3; z <= ancho / 2 + 0.31; z += 0.24) list.push(new THREE.BoxGeometry(largo + 0.8, 0.06, 0.12).translate(0, alto + 0.53, z));
    [-ancho / 2 + 0.2, ancho / 2 - 0.2].forEach((z) => led.push(new THREE.BoxGeometry(largo, 0.03, 0.05).translate(0, alto - 0.02, z)));
    for (let x = -largo / 2 + 2; x <= largo / 2 - 1.9; x += 3.6) {
      mesas.push(new THREE.BoxGeometry(2.0, 0.06, 0.8).translate(x, 0.76, 0), new THREE.BoxGeometry(2.0, 0.05, 0.3).translate(x, 0.45, 0.62), new THREE.BoxGeometry(2.0, 0.05, 0.3).translate(x, 0.45, -0.62));
      est.push(new THREE.BoxGeometry(0.08, 0.76, 0.6).translate(x - 0.8, 0.38, 0), new THREE.BoxGeometry(0.08, 0.76, 0.6).translate(x + 0.8, 0.38, 0));
    }
    for (let k = 0; k < 9; k++) list.push(new THREE.BoxGeometry(0.09, 2.2, 0.05).translate(-largo / 2 + 0.25 + k * 0.22, 1.1, -ancho / 2));   // celosía
    const o1 = new THREE.Mesh(unir(est), C.oscuro), o2 = new THREE.Mesh(unir(list), C.madera), o3 = new THREE.Mesh(unir(mesas), C.madera), o4 = new THREE.Mesh(unir(led), C.led);
    g.add(sombra(o1), sombra(o3), o4);
    const piso2 = new THREE.Mesh(new THREE.BoxGeometry(largo + 1, 0.12, ancho + 1).translate(0, 0.06, 0), C.concreto); piso2.receiveShadow = true; g.add(piso2);
    const [pu, pv] = enLinea(lado, 33, 13);
    g.position.set(pu, 0, -pv); g.rotation.y = rotLinea(lado);
    const techo = new THREE.Group(); techo.add(sombra(o2)); techo.position.copy(g.position); techo.rotation.copy(g.rotation);
    obras.add(g); cubierta.add(techo);
    return g;
  };
  [1, -1].forEach(pergola);

  // --- portal del acceso suroccidental: muro de letrero gris carbón, marquesina de acero y rejas
  const portal = new THREE.Group();
  const cartel = new THREE.MeshStandardMaterial({ map: texturaPortal(), emissive: 0xffffff, emissiveMap: null, roughness: 0.7 });
  cartel.emissiveMap = cartel.map; cartel.emissiveIntensity = 0.12;
  portal.add(new THREE.Mesh(new THREE.BoxGeometry(8, 3.6, 0.6).translate(5.4, 1.8, 0), C.oscuro));
  const frente = new THREE.Mesh(new THREE.PlaneGeometry(7.6, 3.4), cartel); frente.position.set(5.4, 1.8, 0.31); portal.add(frente);
  portal.add(new THREE.Mesh(unir([new THREE.BoxGeometry(0.22, 4.2, 0.22).translate(0, 2.1, 0), new THREE.BoxGeometry(0.22, 4.2, 0.22).translate(-3.2, 2.1, 0), new THREE.BoxGeometry(4.2, 0.22, 1.6).translate(-1.6, 4.2, 0.2)]), C.oscuro));
  portal.add(new THREE.Mesh(unir(Array.from({ length: 13 }, (_, k) => new THREE.BoxGeometry(0.04, 2, 0.04).translate(-0.2 - k * 0.24, 1.0, 0)).concat([new THREE.BoxGeometry(3.1, 0.06, 0.06).translate(-1.6, 1.98, 0)])), C.oscuro));
  portal.add(new THREE.Mesh(new THREE.BoxGeometry(9.5, 0.4, 1.2).translate(5.4, 0.2, 1.2), C.concreto));
  portal.position.set(u0 + 3, 0, -(v0 + 0.7)); obras.add(sombra(portal));

  // --- torres de luz LED apuntando al cuadro, postes peatonales, bolardos en los paseos; bancas y canecas
  const foco = [0, 32];
  const T = [[22, 2], [-22, 2], [u1 - 5, 40], [u0 + 3, 40], [30, v1 - 5.5], [-30, v1 - 5.5]].map(([u, v]) => [u, v, foco[0], foco[1]]);
  luces.add(torresLuz(T, 19));
  luces.add(postes(aLoLargo([[u0 + 16, v0 + 0.3], [u1 - 0.3, v0 + 0.3], [u1 - 0.3, v1 - 0.3], [cu1 + 2, v1 - 0.3]], 14), 4.2));
  luces.add(bolardos([...paseos.flatMap((p) => aLoLargo(p, 6, -1.85, 3)), ...aLoLargo(ruta, 7, -1.75, 2).filter(([u, v]) => u > u0 + 18 || v > v0 + 6)].map(([u, v]) => [u, v])));
  obras.add(bancas([...[1, -1].flatMap((lado) => [8, 16, 50].filter((x) => lado > 0 || x < 44).map((x) => [...enLinea(lado, x, 11.3), haciaLinea(lado)])),
    ...[10, 26, 50, 58, 74].map((v) => [u1 - 4.6, v, Math.PI / 2]), [-6, -6.9, Math.PI], [6, -6.9, Math.PI], [u0 + 12.6, v0 + 45, -Math.PI / 2], [u0 + 12.6, v0 + 54, -Math.PI / 2]]));
  obras.add(canecas([[u1 - 4.6, 18], [u1 - 4.6, 66], [-9, -6.8], [9, -6.8], enLinea(1, 22, 11.2), enLinea(-1, 22, 11.2), [u0 + 17, v0 + 7]]));

  // --- verde: palmas en el borde, guayacanes rosados en los paseos, árboles de sombra detrás de la cerca del jardín
  const borde = aLoLargo([[u0 + 1, v0 + 1], [u1 - 1, v0 + 1], [u1 - 1, v1 - 1], [u0 + 1, v1 - 1], [u0 + 1, v0 + 10]], 9).map(([u, v]) => [u, v]);
  verde.add(palmas(borde.filter(([u, v]) => !(u < u0 + 17 && v < v0 + 9) && !(u < cu1 + 1.5 && v > cv0 - 1.5) && !(u < u0 + 13.5 && v > v0 + 36.5 && v < v0 + 61.5)), { alto: 9.5, semilla: 21 }));
  verde.add(arboles([...[1, -1].flatMap((lado) => [20, 47].map((x) => enLinea(lado, x, 17))), [u1 - 7.5, v0 + 30], [u1 - 7.5, v0 + 56], [-17.5, -19], [17.5, -19]], { alto: 8, semilla: 44, especie: 'guayacan' }));
  const jardines = [];
  for (let k = 0; k < 56; k++) { const a = -Math.PI / 4 + (k / 56) * (Math.PI / 2), rr = cerca(a) + 4.5 + (k % 3) * 2.4; jardines.push([rr * Math.sin(a), rr * Math.cos(a)]); }
  verde.add(arboles(jardines.filter(([u, v]) => u > u0 + 2 && u < u1 - 8 && v < v1 - 4 && !(u < cu1 + 2 && v > cv0 - 2) && Math.hypot(u, v - M.cercaCentro - 0.7) > 6), { alto: 7.5, semilla: 33, especie: 'mixto' }));
  verde.add(palmas([[u0 + 1.2, v0 + 12], [u0 + 1.2, v0 + 20], [u0 + 1.2, v0 + 28], [u0 + 19.2, v0 + 12], [u0 + 19.2, v0 + 30], [u0 + 16.5, v0 + 2.5], [u0 + 16.5, v0 + 6]], { alto: 6.5, semilla: 23 }));
  verde.add(matas([[u0 + 1.4, v0 + 16], [u0 + 1.4, v0 + 24], [u0 + 19.2, v0 + 21], [u0 + 14.8, v0 + 1.6], [u0 + 12, v0 + 1.6]], { tipo: 'heliconia', alto: 1.5, semilla: 71 }));

  // --- gente: el partido (defensa, bateador, receptor, umpire, coaches y el siguiente al bate), público, familias y paseantes
  const L = { camisa: '#f4f4f0', pantalon: '#1f4f8f' }, Vt = { camisa: '#b8302a', pantalon: '#d8d8d2' }, U = { camisa: '#1d2124', pantalon: '#3a3f44' };
  const juego2 = [[0, cv + 0.3, Math.PI, L], [0, -1.6, 0, L], [0, -2.6, 0, U], [lb + 2.2, lb + 1.2, -2.4, L], [-lb - 2.2, lb + 1.2, 2.4, L], [5.5, M.homeSegunda + 2.5, Math.PI, L], [-6, M.homeSegunda + 1.5, Math.PI, L],
    [-38, 52, 2.6, L], [0, 63, Math.PI, L], [37, 52, -2.6, L], [-1.0, 0.4, -Math.PI / 2, Vt], [-11.5, -3.2, 0.6, Vt], [...enLinea(1, 26, 2.5), Math.PI / 2, Vt], [...enLinea(-1, 22, 2.5), -Math.PI / 2, L]];
  personas.add(gente(juego2.map(([u, v, rr, ropa]) => [u, v, rr, ropa]), { semilla: 3 }));
  personas.add(gente(publico, { sentado: true, semilla: 5 }));
  const paseantes = [];
  [1, -1].forEach((lado) => { [12, 21, 38].forEach((x, i) => { const [u, v] = enLinea(lado, x, 9.2 + (i % 2 ? 0.6 : -0.6)); paseantes.push([u, v, rotLinea(lado) + (i % 2 ? 0 : Math.PI)]); }); [-6.5, -3, 3, 6.5].forEach((x) => { const [u, v] = enLinea(lado, 33 + x, 13 + (x > 0 ? 0.9 : -0.9)); paseantes.push([u, v, rotLinea(lado) + (x > 0 ? Math.PI / 2 : -Math.PI / 2)]); }); });
  [[u1 - 2, 12, Math.PI / 2], [u1 - 2.4, 36, -Math.PI / 2], [u1 - 1.8, 61, Math.PI / 2], [-3, -10, 0.4], [4, -9, -0.7], [-9, -18, 1.2], [u0 + 8, v0 + 3, 0.3], [u0 + 10, v0 + 4.2, 2.8], [u0 + 7, v0 + 46, 1.0], [u0 + 4, v0 + 54, 2.2]].forEach((p) => paseantes.push(p));
  personas.add(gente(paseantes, { semilla: 9 }));
  const ninos = gente([[u0 + 5.6, v0 + 48, 0.5], [u0 + 8.4, v0 + 52, 2.1], [u0 + 6.8, v0 + 45.5, -0.4], [u0 + 4.6, v0 + 56.5, 1.4], [u0 + 9.4, v0 + 44, 2.9]], { semilla: 13, escala: 0.62 });
  personas.add(ninos);

  raiz.userData.partes = { piso, campo, obras, cubierta, luces, verde, gente: personas };
  // puntos del contorno del lote en el modelo (para encuadrar) y los focos de la cámara
  raiz.updateMatrixWorld(true);
  const aModelo = (u, v) => { const p = new THREE.Vector3(u, 0, -v).applyMatrix4(raiz.matrixWorld); return [p.x, -p.z]; };
  raiz.userData.contorno = [[u0, v0], [u1, v0], [u1, v1], [u0, v1]].map(([u, v]) => aModelo(u, v));
  raiz.userData.aModelo = aModelo;
  return raiz;
}
