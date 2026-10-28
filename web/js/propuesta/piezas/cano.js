// Parque lineal del caño colector Shell: el caño canalizado se renaturaliza (cauce vivo con orillas vegetadas en lugar de
// canal muerto), con sendero peatonal y ciclorruta por la orilla occidental, que es la que está libre de casas, árboles
// nativos donde la franja es ancha, laguna de retención y bosque inundable (drenaje sostenible), puentes peatonales en
// las prolongaciones de las calles y luminarias. El corredor cambia de ancho por tramos, como lo midió el levantamiento:
// cada tramo dice cuántos metros hay libres al occidente y al oriente del eje.
import { THREE, mat } from '../../core.js';
import { cinta, losa, arboles, palmas, postes, aLoLargo, puntoEn, largo, suave, V, unir, sembrar } from '../geo3d.js';

// polilínea corrida off metros a la izquierda de su sentido (negativo: derecha); off puede ser una función del punto
function paralela(pts, off) {
  return pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)], L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, o = typeof off === 'function' ? off(p) : off;
    return [p[0] - ((b[1] - a[1]) / L) * o, p[1] + ((b[0] - a[0]) / L) * o];
  });
}
// franja entre dos paralelas de ancho variable (de izquierda a derecha: o0 > o1)
function franja(pts, o0, o1, h) {
  const A = paralela(pts, o0), B = paralela(pts, o1), pos = [], idx = [];
  A.forEach((a, i) => { pos.push(a[0], h, -a[1], B[i][0], h, -B[i][1]); if (i) { const k = i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); } });
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
  return g;
}

// eje: [[x, y], …] de sur a norte; tramos: [{ y0, y1, occidente, oriente }] (metros libres a cada lado del eje);
// humedales y bosques: polígonos [[x, y], …]; puentes: puntos [x, y] (o fracciones del recorrido, 0–1)
export function parqueLineal(eje, { tramos = [], humedales = [], bosques = [], puentes = [0.22, 0.48, 0.78] } = {}) {
  const raiz = new THREE.Group(), e = suave(eje, Math.max(24, Math.round(largo(eje) / 6)));
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const cauce = capa('cauce'), orillas = capa('orillas'), sendas = capa('sendas'), verde = capa('verde'), puentesG = capa('puentes'), sudsG = capa('suds');
  const C = {
    agua: mat(new THREE.Color('#3f9cc4'), { roughness: 0.12, metalness: 0.08, polygonOffset: true, polygonOffsetFactor: -8, polygonOffsetUnits: -8 }),
    orilla: mat(new THREE.Color('#5d9a45'), { roughness: 1, polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 }),
    ronda: new THREE.MeshBasicMaterial({ color: new THREE.Color('#14a06c'), transparent: true, opacity: 0.18, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }),
    sendero: mat(new THREE.Color('#d9c9a6'), { roughness: 0.9, polygonOffset: true, polygonOffsetFactor: -7, polygonOffsetUnits: -7 }),
    cicla: mat(new THREE.Color('#2f9b6a'), { roughness: 0.8, polygonOffset: true, polygonOffsetFactor: -7, polygonOffsetUnits: -7 }),
    madera: mat(new THREE.Color('#a8703f'), { roughness: 0.75 }), metal: mat(new THREE.Color('#2b3035'), { roughness: 0.5, metalness: 0.5 }),
    humedal: mat(new THREE.Color('#4d8c7a'), { roughness: 0.3, polygonOffset: true, polygonOffsetFactor: -8, polygonOffsetUnits: -8 }),
    junco: mat(new THREE.Color('#7da84a'), { roughness: 1, flatShading: true }),
  };
  // ancho libre a cada lado según el tramo (si no hay tramos: 20 m al occidente y 6 m al oriente)
  const tramo = ([, y]) => tramos.find((t) => y >= t.y0 && y <= t.y1) || tramos.reduce((m, t) => (Math.abs((t.y0 + t.y1) / 2 - y) < Math.abs((m.y0 + m.y1) / 2 - y) ? t : m), tramos[0] || { occidente: 20, oriente: 6, y0: -1e9, y1: 1e9 });
  const W = (p) => tramo(p).occidente, E = (p) => tramo(p).oriente;
  // corredor protegido (tenue), orillas vegetadas y cauce vivo de 5 m
  cauce.add(new THREE.Mesh(franja(e, W, (p) => -E(p), 0.06), C.ronda));
  orillas.add(new THREE.Mesh(franja(e, (p) => Math.min(W(p) - 5.5, 4.5) + 2.5, (p) => -Math.max(2.6, Math.min(E(p), 4.5)), 0.09), C.orilla));
  cauce.add(new THREE.Mesh(cinta(e, 5, 0.12), C.agua));
  // sendero (3 m) y ciclorruta (2,5 m) juntos por la orilla occidental, a una distancia que cabe en cada tramo
  const cSen = (p) => Math.min(W(p) - 3.6, 8.5), sen = paralela(e, (p) => cSen(p) - 1.2), cic = paralela(e, (p) => cSen(p) + 1.65);
  sendas.add(new THREE.Mesh(cinta(sen, 3, 0.11), C.sendero), new THREE.Mesh(cinta(cic, 2.5, 0.11), C.cicla));
  sendas.add(postes(aLoLargo(sen, 22).map(([x, y]) => [x, y]), 4.2));
  // árboles nativos donde la franja es ancha (más allá de la ciclorruta al occidente y en la orilla oriental si hay espacio)
  const oeste = aLoLargo(paralela(e, (p) => Math.min(W(p) - 1.5, cSen(p) + 5.5)), 9).filter(([x, y]) => W([x, y]) >= 14).map(([x, y]) => [x, y]);
  const este = aLoLargo(paralela(e, (p) => -(E(p) - 1.5)), 11, 0, 4).filter(([x, y]) => E([x, y]) >= 6).map(([x, y]) => [x, y]);
  const orilla = aLoLargo(paralela(e, 3.6), 13, 0, 6).map(([x, y]) => [x, y]);
  verde.add(arboles([...oeste, ...este], { alto: 10, semilla: 61 }), arboles(orilla, { alto: 7, semilla: 62 }), palmas(aLoLargo(paralela(e, (p) => Math.min(W(p) - 2, cSen(p) + 4)), 48, 0, 20).filter(([x, y]) => W([x, y]) >= 12).map(([x, y]) => [x, y]), { alto: 10, semilla: 63 }));
  bosques.forEach((poly, i) => verde.add(arboles(sembrar(poly, 60, 4.5, 70 + i), { alto: 12, semilla: 64 + i })));
  // puentes peatonales en arco sobre el cauce, con barandas
  const fraccion = (p) => { if (typeof p === 'number') return p; let mejor = 0, d = Infinity, acum = 0; for (let i = 1; i < e.length; i++) { const L = Math.hypot(e[i][0] - e[i - 1][0], e[i][1] - e[i - 1][1]); const dd = Math.hypot(e[i][0] - p[0], e[i][1] - p[1]); acum += L; if (dd < d) { d = dd; mejor = acum; } } return mejor / acum; };
  puentes.map(fraccion).forEach((f) => {
    const [x, y, a] = puntoEn(e, f), g = new THREE.Group(), n = 12, tablas = [];
    for (let i = 0; i < n; i++) {
      const u0 = -6 + (12 * i) / n, u1 = -6 + (12 * (i + 1)) / n, h0 = 1.4 * (1 - (u0 / 6) ** 2) + 0.3, h1 = 1.4 * (1 - (u1 / 6) ** 2) + 0.3;
      tablas.push(new THREE.BoxGeometry(12 / n + 0.05, 0.2, 2.6).rotateZ(Math.atan2(h1 - h0, 12 / n)).translate((u0 + u1) / 2, (h0 + h1) / 2, 0));
    }
    g.add(new THREE.Mesh(unir(tablas), C.madera));
    const lado = (z) => Array.from({ length: n + 1 }, (_, i) => { const u = -6 + (12 * i) / n; return [u, 1.4 * (1 - (u / 6) ** 2) + 0.4, z]; });
    [-1.25, 1.25].forEach((z) => { const pts = lado(z); const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map(([u, h, zz]) => new THREE.Vector3(u, h + 1, zz))), 24, 0.05, 5); g.add(new THREE.Mesh(geo, C.metal)); });
    g.position.copy(V(x, y)); g.rotation.y = a + Math.PI / 2;   // el tablero cruza el cauce de lado a lado
    g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    puentesG.add(g);
  });
  // laguna de retención y humedales (drenaje sostenible): lámina de agua con borde orgánico y juncos
  humedales.forEach((poly, k) => {
    const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length, cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
    const rx = (Math.max(...poly.map((p) => p[0])) - Math.min(...poly.map((p) => p[0]))) * 0.46, ry = (Math.max(...poly.map((p) => p[1])) - Math.min(...poly.map((p) => p[1]))) * 0.46;
    const pts = Array.from({ length: 32 }, (_, i) => { const t = (i / 32) * 2 * Math.PI, q = 1 + 0.1 * Math.sin(3 * t + k); return [cx + rx * q * Math.cos(t), cy + ry * q * Math.sin(t)]; });
    sudsG.add(new THREE.Mesh(losa(pts, 0.13), C.humedal));
    const N = 90, juncos = new THREE.InstancedMesh(new THREE.ConeGeometry(0.35, 1.6, 5).translate(0, 0.8, 0), C.junco, N), m4 = new THREE.Matrix4();
    for (let i = 0; i < N; i++) { const t = (i / N) * 2 * Math.PI, q = 0.84 + ((i * 37) % 10) / 60; m4.makeTranslation(cx + rx * q * Math.cos(t), 0.1, -(cy + ry * q * Math.sin(t))); juncos.setMatrixAt(i, m4); }
    juncos.computeBoundingSphere(); sudsG.add(juncos);
  });
  raiz.userData.partes = { cauce, orillas, sendas, verde, puentes: puentesG, suds: sudsG };
  raiz.userData.eje = e;
  return raiz;
}
