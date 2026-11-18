// Parque lineal del caño colector Shell: el caño canalizado se renaturaliza (cauce vivo con orillas vegetadas en lugar de
// canal muerto), con sendero peatonal y ciclorruta por la orilla occidental, que es la que está libre de casas, árboles
// nativos donde la franja es ancha, laguna de retención y bosque inundable (drenaje sostenible), puentes peatonales en
// las prolongaciones de las calles y luminarias. El corredor cambia de ancho por tramos, como lo midió el levantamiento:
// cada tramo dice cuántos metros hay libres al occidente y al oriente del eje.
//
// Acabados: agua con olas, orillas en talud (de lo húmedo a lo seco) con enrocado al pie, gaviones donde las casas quedan
// pegadas al cauce y plantas de ribera; sendero de adoquín con bordillos, ciclorruta verde con línea amarilla y
// pictogramas; bancas con caneca en bolsillos de concreto hacia el agua, luminarias con su charco de luz, bolardos en los
// cruces, paneles interpretativos; puentes de tablas en arco con baranda de acero y pasamanos de madera; laguna con borde
// de piedra, juncos y deck mirador; gente caminando, en bicicleta y sentada. El caño pasa bajo la vía a Barrancabermeja
// por un box culvert: ahí el agua, las orillas y el sendero se cortan (no se pintan encima de la vía) y el sendero cruza
// por una cebra. Todo instanciado o unido por material para pocas llamadas de dibujo.
import { THREE, mat } from '../../core.js';
import { CALLES } from '../../data.js';
import { losa, rect, arboles, palmas, matas, postes, bancas, canecas, bolardos, gente, aLoLargo, puntoEn, largo, suave, unir, sembrar, distLinea, dentro, azar, luzComun } from '../geo3d.js';
import { matT, matAgua, MatMundo } from '../texturas.js';

const valor = (f, p) => (typeof f === 'function' ? f(p) : f);
// polilínea corrida off metros a la izquierda de su sentido (negativo: derecha); off puede ser una función del punto;
// cerrado: el primer y el último punto son vecinos (anillos)
function paralela(pts, off, cerrado = false) {
  const n = pts.length;
  return pts.map((p, i) => {
    const a = cerrado ? pts[(i - 1 + n) % n] : pts[Math.max(0, i - 1)], b = cerrado ? pts[(i + 1) % n] : pts[Math.min(n - 1, i + 1)];
    const L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, o = valor(off, p);
    return [p[0] - ((b[1] - a[1]) / L) * o, p[1] + ((b[0] - a[0]) / L) * o];
  });
}
// Superficie a lo largo de una polilínea con un perfil transversal: filas [desplazamiento, alto, color?] de izquierda a
// derecha (cada valor puede ser una función del punto). Caras hacia arriba. corte(p) quita el cuadro cuyo centro cae donde
// pasa una vía (el caño va por debajo); cerrado: anillo (borde de la laguna)
function perfil(pts, filas, { corte = null, cerrado = false } = {}) {
  const R = filas.map(([o]) => paralela(pts, o, cerrado)), n = pts.length, k = filas.length, pos = [], col = [], idx = [];
  const conColor = filas.some((f) => f[2]);
  for (let i = 0; i < n; i++) for (let j = 0; j < k; j++) {
    const [x, y] = R[j][i];
    pos.push(x, valor(filas[j][1], pts[i]), -y);
    if (conColor) col.push(...(filas[j][2] || [1, 1, 1]));
  }
  const tramos = cerrado ? n : n - 1;
  for (let s = 0; s < tramos; s++) {
    const i0 = s, i1 = (s + 1) % n;
    for (let j = 1; j < k; j++) {
      if (corte) { const q = [R[j - 1][i0], R[j][i0], R[j - 1][i1], R[j][i1]]; if (corte([(q[0][0] + q[1][0] + q[2][0] + q[3][0]) / 4, (q[0][1] + q[1][1] + q[2][1] + q[3][1]) / 4])) continue; }
      const a = i0 * k + j - 1, b = i0 * k + j, c = i1 * k + j - 1, d = i1 * k + j;
      idx.push(a, b, c, b, d, c);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  if (conColor) g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx); g.computeVertexNormals();
  return g;
}
// bordillo o muro bajo a lo largo de la polilínea: cara de arriba y los dos costados (aristas vivas, no redondeadas)
function muro(pts, off, ancho, h0, h1, corte) {
  const a = (p) => valor(off, p) + ancho / 2, b = (p) => valor(off, p) - ancho / 2;
  return unir([perfil(pts, [[a, h1], [b, h1]], { corte }), perfil(pts, [[a, h0], [a, h1]], { corte }), perfil(pts, [[b, h1], [b, h0]], { corte })]);
}
// distancia con signo de p a la polilínea (+ a la izquierda) y la normal izquierda y la y del punto más cercano
function respecto(p, linea) {
  let m = [Infinity, 0, 1, p[1]];
  for (let i = 1; i < linea.length; i++) {
    const [a, b] = [linea[i - 1], linea[i]], dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2));
    const qx = a[0] + t * dx, qy = a[1] + t * dy, d = Math.hypot(p[0] - qx, p[1] - qy);
    if (d < Math.abs(m[0])) { const L = Math.sqrt(L2); m = [(Math.sign(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) || 1) * d, -dy / L, dx / L, qy]; }
  }
  return m;
}
// las vías del casco cerca del corredor (CALLES de OpenStreetMap) con su medio ancho, andenes incluidos: el caño pasa por
// debajo de las que lo cruzan (alcantarilla), y el prado del parque no se pinta encima de ninguna
const CON_ANDEN = new Set(['residential', 'tertiary', 'secondary']);
function viasCerca(e, m = 40) {
  const xs = e.map((p) => p[0]), ys = e.map((p) => p[1]), [x0, x1, y0, y1] = [Math.min(...xs) - m, Math.max(...xs) + m, Math.min(...ys) - m, Math.max(...ys) + m];
  return (CALLES?.calles || []).filter((c) => c.p?.some((q, i) => i && Math.max(q[0], c.p[i - 1][0]) > x0 && Math.min(q[0], c.p[i - 1][0]) < x1 && Math.max(q[1], c.p[i - 1][1]) > y0 && Math.min(q[1], c.p[i - 1][1]) < y1))
    .map((c) => ({ p: c.p, w: (c.ancho || 6) / 2 + (CON_ANDEN.has(c.tipo) ? 1.3 : 0), calzada: (c.ancho || 6) / 2 }));
}
// primer punto donde una vía corta una polilínea (o null)
function cruce(via, linea) {
  for (let i = 1; i < via.p.length; i++) for (let j = 1; j < linea.length; j++) {
    const [a, b, c, d] = [linea[j - 1], linea[j], via.p[i - 1], via.p[i]], r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], den = r[0] * s[1] - r[1] * s[0];
    if (!den) continue;
    const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
    if (t >= 0 && t <= 1 && u >= 0 && u <= 1) return { p: [a[0] + t * r[0], a[1] + t * r[1]], ang: Math.atan2(s[1], s[0]) };
  }
  return null;
}

// texturas de lienzo: panel interpretativo y pictograma de la ciclorruta (una vez por página)
let texPanel = null, texCicla = null;
function texturaPanel() {
  if (texPanel) return texPanel;
  const c = document.createElement('canvas'); c.width = 512; c.height = 360;
  const x = c.getContext('2d');
  x.fillStyle = '#f3eee1'; x.fillRect(0, 0, 512, 360);
  x.fillStyle = '#1f5a46'; x.fillRect(0, 0, 512, 92);
  x.fillStyle = '#ffffff'; x.font = 'bold 36px "Public Sans", Arial, sans-serif'; x.fillText('CAÑO COLECTOR SHELL', 22, 48);
  x.fillStyle = '#cfe8d8'; x.font = '22px "Public Sans", Arial, sans-serif'; x.fillText('Parque lineal · cauce vivo', 22, 79);
  // corte del cauce: orillas con árboles, agua con una garza, sendero y ciclorruta a un lado
  x.fillStyle = '#8a6d4c'; x.beginPath(); x.moveTo(20, 250); x.lineTo(150, 250); x.lineTo(205, 290); x.lineTo(300, 290); x.lineTo(355, 250); x.lineTo(492, 250); x.lineTo(492, 300); x.lineTo(20, 300); x.fill();
  x.fillStyle = '#3f8fa6'; x.beginPath(); x.moveTo(178, 270); x.lineTo(205, 290); x.lineTo(300, 290); x.lineTo(328, 270); x.fill();
  x.strokeStyle = '#d7eef4'; x.lineWidth = 3; for (let k = 0; k < 3; k++) { x.beginPath(); for (let i = 0; i <= 12; i++) x.lineTo(196 + i * 9, 276 + k * 5 + Math.sin(i * 1.4 + k) * 2); x.stroke(); }
  [[60, 196, 34], [112, 206, 26], [400, 200, 30], [452, 210, 24]].forEach(([cx, cy, rr]) => { x.fillStyle = '#5d4632'; x.fillRect(cx - 4, cy + rr * 0.4, 8, 250 - cy - rr * 0.4); x.fillStyle = '#4f8a3a'; x.beginPath(); x.arc(cx, cy, rr, 0, Math.PI * 2); x.fill(); });
  x.fillStyle = '#e8c15a'; x.fillRect(370, 244, 50, 6); x.fillStyle = '#2f9464'; x.fillRect(424, 244, 44, 6);
  x.fillStyle = '#ffffff'; x.strokeStyle = '#ffffff'; x.lineCap = 'round';
  x.beginPath(); x.ellipse(262, 238, 20, 10, -0.2, 0, Math.PI * 2); x.fill();
  x.lineWidth = 5; x.beginPath(); x.moveTo(276, 232); x.quadraticCurveTo(292, 214, 280, 196); x.stroke();
  x.beginPath(); x.arc(281, 193, 6, 0, Math.PI * 2); x.fill();
  x.strokeStyle = '#e8b13a'; x.lineWidth = 3; x.beginPath(); x.moveTo(286, 193); x.lineTo(304, 197); x.stroke();
  x.strokeStyle = '#3a3a3a'; x.lineWidth = 2; x.beginPath(); x.moveTo(258, 246); x.lineTo(256, 276); x.moveTo(266, 246); x.lineTo(268, 276); x.stroke();
  x.fillStyle = '#2a3a33'; x.font = '19px "Public Sans", Arial, sans-serif';
  x.fillText('Sendero 3 m · Ciclorruta 2,5 m · luz LED', 22, 128); x.fillText('Laguna de retención · bosque inundable', 22, 154);
  x.fillStyle = '#1f5a46'; x.font = 'bold 18px "Public Sans", Arial, sans-serif'; x.fillText('Yondó 2028–2031 · Ciudadela deportiva ecológica', 22, 338);
  texPanel = new THREE.CanvasTexture(c); texPanel.colorSpace = THREE.SRGBColorSpace; texPanel.anisotropy = 8;
  return texPanel;
}
function texturaCicla() {
  if (texCicla) return texCicla;
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d');
  x.clearRect(0, 0, 256, 256); x.strokeStyle = '#ffffff'; x.fillStyle = '#ffffff'; x.lineWidth = 11; x.lineCap = 'round'; x.lineJoin = 'round';
  [[70, 120], [186, 120]].forEach(([cx, cy]) => { x.beginPath(); x.arc(cx, cy, 40, 0, Math.PI * 2); x.stroke(); });
  x.beginPath(); x.moveTo(70, 120); x.lineTo(116, 120); x.lineTo(156, 66); x.lineTo(98, 66); x.lineTo(70, 120); x.moveTo(116, 120); x.lineTo(92, 52); x.moveTo(78, 50); x.lineTo(108, 50); x.moveTo(156, 66); x.lineTo(186, 120); x.moveTo(156, 66); x.lineTo(150, 44); x.lineTo(170, 40); x.stroke();
  x.beginPath(); x.moveTo(84, 196); x.lineTo(150, 196); x.stroke();
  x.beginPath(); x.moveTo(176, 196); x.lineTo(146, 178); x.lineTo(146, 214); x.closePath(); x.fill();
  texCicla = new THREE.CanvasTexture(c); texCicla.colorSpace = THREE.SRGBColorSpace; texCicla.anisotropy = 8;
  return texCicla;
}
// gavión (1 m por tramo, en coordenadas del mundo con MatMundo): piedras de canto apretadas tras la malla de alambre en
// rombos de 12 cm; se repite sin costura (las piedras del borde se pintan también del otro lado)
let texGav = null;
function texturaGavion() {
  if (texGav) return texGav;
  const n = 256, c = document.createElement('canvas'); c.width = c.height = n;
  const x = c.getContext('2d'), r = azar(5), tonos = ['#9d968a', '#a9a397', '#877f74', '#b4ada1', '#938b7f', '#7d766c', '#a39a8b'];
  x.fillStyle = '#3b3732'; x.fillRect(0, 0, n, n);
  for (let i = 0; i < 190; i++) {
    const cx = r() * n, cy = r() * n, rx = 9 + r() * 12, ry = 7 + r() * 9, a = r() * Math.PI, t = tonos[Math.floor(r() * tonos.length)];
    for (const dx of [-n, 0, n]) for (const dy of [-n, 0, n]) {
      x.fillStyle = t; x.beginPath(); x.ellipse(cx + dx, cy + dy, rx, ry, a, 0, Math.PI * 2); x.fill();
      x.fillStyle = 'rgba(255,255,255,0.13)'; x.beginPath(); x.ellipse(cx + dx - rx * 0.2, cy + dy - ry * 0.3, rx * 0.55, ry * 0.45, a, 0, Math.PI * 2); x.fill();
    }
  }
  x.strokeStyle = 'rgba(214,218,220,0.85)'; x.lineWidth = 2;
  for (let k = -n; k <= 2 * n; k += 32) { x.beginPath(); x.moveTo(k, 0); x.lineTo(k + n, n); x.stroke(); x.beginPath(); x.moveTo(k, 0); x.lineTo(k - n, n); x.stroke(); }
  texGav = new THREE.CanvasTexture(c); texGav.colorSpace = THREE.SRGBColorSpace; texGav.wrapS = texGav.wrapT = THREE.RepeatWrapping; texGav.anisotropy = 8;
  return texGav;
}
// garza blanca (0,9 m) mirando hacia +x: cuerpo, cuello y cabeza blancos; pico y patas amarillo oscuro
const geoGarza = (() => {
  const blanco = unir([new THREE.SphereGeometry(0.15, 8, 6).scale(1.7, 1, 0.9).translate(0, 0.62, 0), new THREE.CylinderGeometry(0.03, 0.045, 0.4, 6).rotateZ(-0.35).translate(0.2, 0.84, 0), new THREE.SphereGeometry(0.055, 8, 6).translate(0.27, 1.03, 0), new THREE.ConeGeometry(0.06, 0.24, 6).rotateZ(Math.PI / 2 + 0.5).translate(-0.3, 0.56, 0)]);
  const patas = unir([new THREE.ConeGeometry(0.018, 0.17, 5).rotateZ(-Math.PI / 2).translate(0.39, 1.02, 0), new THREE.CylinderGeometry(0.011, 0.011, 0.52, 4).translate(0.02, 0.26, 0.05), new THREE.CylinderGeometry(0.011, 0.011, 0.52, 4).rotateZ(0.25).translate(-0.05, 0.26, -0.05)]);
  return { blanco, patas };
})();
// bicicleta de 1,7 m con el frente hacia +x: marco de tubos (se tiñe por instancia) y ruedas
function tuboEntre(a, b, r) {
  const d = new THREE.Vector3().subVectors(b, a), L = d.length(), g = new THREE.CylinderGeometry(r, r, L, 6).translate(0, L / 2, 0);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize())); g.translate(a.x, a.y, a.z);
  return g;
}
const geoBici = (() => {
  const P = (x, y, z = 0) => new THREE.Vector3(x, y, z), BB = P(0, 0.3), S = P(-0.14, 0.86), H = P(0.36, 0.86), Hb = P(0.41, 0.7), RA = P(-0.52, 0.36), FA = P(0.52, 0.36);
  const marco = unir([tuboEntre(BB, S, 0.022), tuboEntre(P(-0.12, 0.8), H, 0.02), tuboEntre(BB, Hb, 0.024), tuboEntre(BB, RA, 0.016), tuboEntre(P(-0.12, 0.8), RA, 0.014), tuboEntre(Hb, FA, 0.018), tuboEntre(H, Hb, 0.022),
    tuboEntre(H, P(0.33, 0.99), 0.018), tuboEntre(P(0.33, 0.99, -0.26), P(0.33, 0.99, 0.26), 0.016), new THREE.BoxGeometry(0.26, 0.05, 0.12).translate(-0.15, 0.89, 0)]);
  const ruedas = unir([new THREE.TorusGeometry(0.33, 0.032, 5, 18).translate(-0.52, 0.36, 0), new THREE.TorusGeometry(0.33, 0.032, 5, 18).translate(0.52, 0.36, 0), new THREE.CylinderGeometry(0.06, 0.06, 0.04, 8).rotateX(Math.PI / 2).translate(0, 0.3, 0)]);
  return { marco, ruedas };
})();
const COLOR_BICI = ['#c8372d', '#2e5fa8', '#f0c419', '#1f2329', '#3a7d44', '#e07a3a', '#d9d2c4'].map((c) => new THREE.Color(c));

// eje: [[x, y], …] de sur a norte; tramos: [{ y0, y1, occidente, oriente }] (metros libres a cada lado del eje);
// humedales y bosques: polígonos [[x, y], …]; puentes: puntos [x, y] (o fracciones del recorrido, 0–1)
export function parqueLineal(eje, { tramos = [], humedales = [], bosques = [], puentes = [0.22, 0.48, 0.78] } = {}) {
  const raiz = new THREE.Group(), e = suave(eje, Math.max(24, Math.round(largo(eje) / 6))), Lt = largo(e);
  const capa = (n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
  const cauce = capa('cauce'), orillas = capa('orillas'), sendas = capa('sendas'), verde = capa('verde'), puentesG = capa('puentes'), sudsG = capa('suds'), personas = capa('gente');
  const po = (k) => ({ polygonOffset: true, polygonOffsetFactor: -k, polygonOffsetUnits: -k });
  const C = {
    // verde de agua limpia con algo de limo (el cielo que refleja ya la azula: un tono más azul se ve de piscina)
    agua: matAgua('#4f7f74', po(8)), laguna: matAgua('#477667', po(8)),
    prado: matT('cesped', { color: '#e2ebcf', ...po(5) }), talud: matT('cesped', { color: '#dfe8c8', vertexColors: true, ...po(6) }),
    roca: matT('roca', { color: '#a59f93' }), gavion: new MatMundo({ map: texturaGavion(), escala: 1, relieve: 0.04, roughness: 0.95 }),
    sendero: matT('adoquin', { color: '#f2e5ca', ...po(7) }), cicla: matT('caucho', { color: '#2f9464', ...po(7) }), bordillo: matT('concreto', { color: '#ebe7de' }),
    amarilla: mat(new THREE.Color('#f2c230'), { roughness: 0.6, ...po(9) }), blanca: mat(new THREE.Color('#f7f7f2'), { roughness: 0.7, ...po(9) }),
    madera: matT('madera'), pilote: matT('madera', { color: '#7a5a3e' }), metal: mat(new THREE.Color('#2b3035'), { roughness: 0.45, metalness: 0.6 }),
    concreto: matT('concreto'), grava: matT('tierra', { color: '#d9d2c4', ...po(7) }), oscuro: mat(new THREE.Color('#1d2124'), { roughness: 0.9 }),
    panel: new THREE.MeshStandardMaterial({ map: texturaPanel(), roughness: 0.6 }),
    cicloPicto: new THREE.MeshStandardMaterial({ map: texturaCicla(), alphaTest: 0.4, roughness: 0.75, ...po(10) }),
    bici: new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0.5 }), llanta: new THREE.MeshStandardMaterial({ color: 0x16181a, roughness: 0.8 }),
  };
  const malla = (geo, m, sombra = false) => { const o = new THREE.Mesh(geo, m); o.receiveShadow = true; o.castShadow = sombra; return o; };
  // ancho libre a cada lado según el tramo (si no hay tramos: 20 m al occidente y 6 m al oriente), suavizado ±10 m en
  // los cambios de tramo para que el sendero no dé un salto
  const T = [...tramos].sort((a, b) => a.y0 - b.y0), base = { occidente: 20, oriente: 6 };
  const enY = (y) => T.find((t) => y >= t.y0 && y <= t.y1) || T.reduce((m, t) => (Math.abs((t.y0 + t.y1) / 2 - y) < Math.abs((m.y0 + m.y1) / 2 - y) ? t : m), T[0]) || base;
  const memo = new Map();
  const ancho = (y) => { const k = Math.round(y * 4) / 4; if (!memo.has(k)) { let o = 0, r = 0; [-10, -5, 0, 5, 10].forEach((d) => { const t = enY(k + d); o += t.occidente; r += t.oriente; }); memo.set(k, [o / 5, r / 5]); } return memo.get(k); };
  const W = (p) => ancho(p[1])[0], E = (p) => ancho(p[1])[1];
  // la sección: medio cauce al occidente (aO) y al oriente (aE) con un leve serpenteo; sendero (3 m) y ciclorruta (2,5 m)
  // por la orilla occidental, a una distancia que cabe en cada tramo; talud entre el agua y el sendero (wO) y al oriente (wE)
  const aO = (p) => 2.5 + 0.3 * Math.sin(p[1] / 17), aE = (p) => Math.min(2.5 + 0.3 * Math.sin(p[1] / 13 + 1), E(p) - 0.3);
  const cSen = (p) => Math.min(W(p) - 3.6, 8.5), sIn = (p) => cSen(p) - 2.7, sOut = (p) => cSen(p) + 0.3, cIn = (p) => cSen(p) + 0.4, cOut = (p) => cSen(p) + 2.9;
  const wO = (p) => sIn(p) - aO(p), eOut = (p) => Math.max(aE(p) + 0.3, Math.min(E(p), 4.5)), wE = (p) => eOut(p) - aE(p), gaviones = (p) => E(p) < 3;
  const vias = viasCerca(e), cruzan = vias.filter((v) => cruce(v, e));
  const bajo = (lista) => (p, m = 0.3) => lista.some((v) => distLinea(p, v.p) < v.w + m);
  const bajoCruce = bajo(cruzan), bajoVia = bajo(vias);
  // arco recorrido (s) ↔ punto del eje, corrido off metros al occidente
  const en = (s, off = 0) => { const [x, y, a] = puntoEn(e, THREE.MathUtils.clamp(s / Lt, 0, 1)); const o = valor(off, [x, y]); return [x - Math.sin(a) * o, y + Math.cos(a) * o, a]; };
  const sDe = (p) => { let mejor = 0, d = Infinity, acc = 0; for (let i = 1; i < e.length; i++) { const [a, b] = [e[i - 1], e[i]], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1, t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (L * L))), dd = Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy); if (dd < d) { d = dd; mejor = acc + t * L; } acc += L; } return mejor; };
  const lejos = (s, lista, d) => lista.every((q) => Math.abs(q - s) > d);
  const r = azar(91);
  const sc = paralela(e, (p) => cSen(p) - 1.2), cc = paralela(e, (p) => cSen(p) + 1.65);

  // --- cauce: prado del corredor (no encima de las vías) y lámina de agua con olas (se corta donde la vía pasa encima)
  cauce.add(malla(perfil(e, [[W, 0.07], [(p) => -E(p), 0.07]], { corte: bajoVia }), C.prado));
  cauce.add(malla(perfil(e, [[aO, 0.12], [(p) => -aE(p), 0.12]], { corte: bajoCruce }), C.agua));

  // --- orillas: talud de lo húmedo (junto al agua, más oscuro) a lo seco, con una cresta baja; enrocado al pie y gaviones
  // donde las casas quedan pegadas al cauce
  const crest = (w) => 0.14 + 0.05 * Math.min(w, 3.4), SECO = [1, 1, 1], MEDIO = [0.9, 0.93, 0.8], HUMEDO = [0.62, 0.57, 0.45];
  const taludO = perfil(e, [[(p) => sIn(p) + 0.05, 0.12, SECO], [(p) => sIn(p) - 0.3 * wO(p), (p) => 0.12 + (crest(wO(p)) - 0.12) * 0.85, SECO], [(p) => aO(p) + 0.35 * wO(p), (p) => crest(wO(p)), MEDIO], [(p) => aO(p) + 0.1, 0.15, HUMEDO], [(p) => aO(p) - 0.15, 0.06, HUMEDO]], { corte: bajoCruce });
  const taludE = perfil(e, [[(p) => -(aE(p) - 0.15), 0.06, HUMEDO], [(p) => -(aE(p) + 0.1), 0.15, HUMEDO], [(p) => -(aE(p) + 0.45 * wE(p)), (p) => crest(wE(p)), MEDIO], [(p) => -(eOut(p) + 0.05), 0.1, SECO]], { corte: bajoCruce });
  orillas.add(malla(unir([taludO, taludE]), C.talud));
  const rocas = [], m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), eu = new THREE.Euler(), v3 = new THREE.Vector3(), s3 = new THREE.Vector3();
  const fila = (linea, paso, salta) => aLoLargo(linea, paso).forEach(([x, y, a]) => {
    if (bajoCruce([x, y]) || salta?.([x, y])) return;
    const j = (r() - 0.5) * 0.4, s = 0.24 + r() * 0.3;
    q.setFromEuler(eu.set(r() * 3, r() * 3, r() * 3)); m4.compose(v3.set(x - Math.sin(a) * j, 0.1 + r() * 0.08, -(y + Math.cos(a) * j)), q, s3.set(s * (1 + r() * 0.4), s * 0.55, s)); rocas.push(m4.clone());
  });
  fila(paralela(e, (p) => aO(p) + 0.05), 0.95); fila(paralela(e, (p) => -(aE(p) + 0.05)), 1.0, gaviones);
  fila(paralela(e, (p) => aO(p) + 0.55), 3.2, (p) => wO(p) < 2);   // piedras sueltas más arriba, donde el talud es ancho
  const gav = [];
  aLoLargo(paralela(e, (p) => -(aE(p) + 0.5)), 1.5).forEach(([x, y, a]) => {
    if (!gaviones([x, y]) || bajoCruce([x, y])) return;
    const c = (o) => [x + Math.sin(a) * o, y - Math.cos(a) * o];   // o metros más hacia el oriente
    const [x1, y1] = c(0.15);
    gav.push(new THREE.BoxGeometry(1.46, 0.55, 1.0).rotateY(a).translate(x, 0.27, -y), new THREE.BoxGeometry(1.46, 0.5, 0.7).rotateY(a).translate(x1, 0.8, -y1));
  });
  // piedras de 20 caras sin sombra propia: son más de mil y a ras del agua la sombra casi no se ve
  const geoPiedra = new THREE.IcosahedronGeometry(1, 0), imR = new THREE.InstancedMesh(geoPiedra, C.roca, rocas.length);
  rocas.forEach((m, i) => imR.setMatrixAt(i, m)); imR.receiveShadow = true; imR.computeBoundingSphere(); orillas.add(imR);
  if (gav.length) orillas.add(malla(unir(gav), C.gavion, true));
  // la alcantarilla bajo la vía: cabezales de concreto con la boca oscura a los dos lados, paralelos a la vía
  const cab = [], boca = [], parche = { asfalto: [], anden: [], raya: [] };
  cruzan.forEach((v) => {
    const { p: pc, ang } = cruce(v, e), sV = sDe(pc);
    // la vía sigue entera sobre la alcantarilla: un parche de calzada, andenes y línea amarilla (los mismos materiales del
    // mundo que la vía de la escena) tapa la cinta del caño de hoy que la escena pinta encima
    const nrm = [-Math.sin(ang), Math.cos(ang)], Lp = 18;
    parche.asfalto.push(losa(rect(pc[0], pc[1], Lp, 2 * v.calzada, ang), 0.05)); parche.raya.push(losa(rect(pc[0], pc[1], Lp, 0.16, ang), 0.056));
    if (v.w > v.calzada + 0.1) [-1, 1].forEach((sg) => parche.anden.push(losa(rect(pc[0] + nrm[0] * sg * (v.calzada + 0.65), pc[1] + nrm[1] * sg * (v.calzada + 0.65), Lp, 1.3, ang), 0.05)));
    let s0 = sV; while (s0 > 0 && bajoCruce(en(s0))) s0 -= 0.5;
    let s1 = sV; while (s1 < Lt && bajoCruce(en(s1))) s1 += 0.5;
    [s0 - 0.4, s1 + 0.4].forEach((s, k) => {
      const [x, y, a] = en(s), sale = k ? 1 : -1, bx = x + Math.cos(a) * sale * 0.22, by = y + Math.sin(a) * sale * 0.22;
      cab.push(new THREE.BoxGeometry(8, 1.1, 0.35).rotateY(ang).translate(x, 0.45, -y));
      boca.push(new THREE.BoxGeometry(3.6, 0.72, 0.04).rotateY(ang).translate(bx, 0.36, -by));
    });
  });
  if (cab.length) {
    orillas.add(malla(unir(cab), C.concreto, true), malla(unir(boca), C.oscuro));
    orillas.add(malla(unir(parche.asfalto), matT('asfalto', po(4))), malla(unir(parche.raya), new THREE.MeshBasicMaterial({ color: 0xe8c547, ...po(5) })));
    if (parche.anden.length) orillas.add(malla(unir(parche.anden), matT('concreto', { modo: 'xz', color: '#e4e0d8', ...po(4) })));
  }

  // --- laguna de retención (antes que el mobiliario: su deck pide un cruce de la ciclorruta)
  const lagunas = humedales.map((poly, k) => {
    const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length, cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
    const rx = (Math.max(...poly.map((p) => p[0])) - Math.min(...poly.map((p) => p[0]))) * 0.46, ry = (Math.max(...poly.map((p) => p[1])) - Math.min(...poly.map((p) => p[1]))) * 0.46;
    let pts = Array.from({ length: 48 }, (_, i) => { const t = (i / 48) * 2 * Math.PI, qq = 1 + 0.1 * Math.sin(3 * t + k); return [cx + rx * qq * Math.cos(t), cy + ry * qq * Math.sin(t)]; });
    // no invade la ciclorruta: lo que quede a menos de 1,8 m de su borde se corre hacia afuera, y se suaviza el borde
    pts = pts.map((p) => { const [d, nx, ny, qy] = respecto(p, e), lim = cOut([0, qy]) + 1.8; return d > -2 && d < lim ? [p[0] + nx * (lim - d), p[1] + ny * (lim - d)] : p; });
    for (let it = 0; it < 2; it++) pts = pts.map((p, i) => { const a = pts[(i + 47) % 48], b = pts[(i + 1) % 48]; return [(a[0] + 2 * p[0] + b[0]) / 4, (a[1] + 2 * p[1] + b[1]) / 4]; });
    let ar = 0; pts.forEach((p, i) => { const b = pts[(i + 1) % 48]; ar += p[0] * b[1] - b[0] * p[1]; });
    if (ar < 0) pts.reverse();   // antihorario: la izquierda del recorrido es el agua
    // el deck: en el punto del borde más cercano al sendero, entrando 2,8 m al agua
    let i0 = 0, dmin = Infinity; pts.forEach((p, i) => { const d = distLinea(p, sc); if (d < dmin) { dmin = d; i0 = i; } });
    const P0 = pts[i0], [ta, tb] = [pts[(i0 + 47) % 48], pts[(i0 + 1) % 48]], tl = Math.hypot(tb[0] - ta[0], tb[1] - ta[1]) || 1, t = [(tb[0] - ta[0]) / tl, (tb[1] - ta[1]) / tl], n = [-t[1], t[0]];
    return { pts, P0, t, n, s: sDe(P0) };
  });

  // --- sendas: sendero de adoquín y ciclorruta verde con bordillos y franja separadora; la ciclorruta sigue pintada al
  // cruzar la vía (cruce de bicicletas), el sendero cruza por una cebra
  sendas.add(malla(perfil(e, [[sOut, 0.11], [sIn, 0.11]], { corte: bajoCruce }), C.sendero));
  sendas.add(malla(perfil(e, [[cOut, 0.11], [cIn, 0.11]]), C.cicla));
  sendas.add(malla(unir([muro(e, sIn, 0.16, 0.05, 0.2, bajoCruce), muro(e, (p) => cOut(p) + 0.08, 0.16, 0.05, 0.18, bajoCruce), perfil(e, [[cIn, 0.113], [sOut, 0.113]], { corte: bajoCruce })]), C.bordillo, true));
  // línea amarilla discontinua de la ciclorruta (1,8 m cada 4 m) y cebras: sobre la vía y frente al deck de cada laguna
  sendas.add(malla(unir(aLoLargo(cc, 4).map(([x, y, a]) => new THREE.BoxGeometry(1.8, 0.012, 0.12).rotateY(a).translate(x, 0.122, -y))), C.amarilla));
  const cebra = [];
  cruzan.forEach((v) => aLoLargo(sc, 0.9).forEach(([x, y, a]) => { if (distLinea([x, y], v.p) < v.calzada) cebra.push(new THREE.BoxGeometry(0.45, 0.012, 2.8).rotateY(a).translate(x, 0.064, -y)); }));
  lagunas.forEach((L) => { const [x, y, a] = en(L.s); for (let k = 0; k < 5; k++) { const o = cIn([x, y]) + 0.25 + k * 0.5, px = x - Math.sin(a) * o, py = y + Math.cos(a) * o; cebra.push(new THREE.BoxGeometry(2.4, 0.012, 0.25).rotateY(a).translate(px, 0.125, -py)); } });
  if (cebra.length) sendas.add(malla(unir(cebra), C.blanca));
  // pictogramas de bicicleta en los dos sentidos (cada uno en su mitad del carril)
  const mob = new THREE.Group(); sendas.add(mob);
  const picto = aLoLargo(e, 46, 0, 14).map(([x, y, a], i) => { const sube = i % 2 === 0, o = cSen([x, y]) + 1.65 + (sube ? -0.62 : 0.62); return [x - Math.sin(a) * o, y + Math.cos(a) * o, sube ? a : a + Math.PI]; }).filter((p) => !bajoCruce(p));
  const imP = new THREE.InstancedMesh(new THREE.PlaneGeometry(1.15, 1.15).rotateX(-Math.PI / 2), C.cicloPicto, picto.length);
  picto.forEach(([x, y, a], i) => { m4.compose(v3.set(x, 0.124, -y), q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), a), s3.set(1, 1, 1)); imP.setMatrixAt(i, m4); });
  imP.receiveShadow = true; imP.computeBoundingSphere(); mob.add(imP);

  // --- puentes: dónde van (el de la alcantarilla se corre fuera de la vía, a la orilla del bosque)
  const fraccion = (p) => (typeof p === 'number' ? p : sDe(p) / Lt);
  const sPuentes = puentes.map(fraccion).map((f) => {
    let s = f * Lt;
    if (cruzan.some((v) => distLinea(en(s), v.p) < v.w + 7)) { let d = 0.5; while (d < 40) { if (!cruzan.some((v) => distLinea(en(s - d), v.p) < v.w + 7)) { s -= d; break; } if (!cruzan.some((v) => distLinea(en(s + d), v.p) < v.w + 7)) { s += d; break; } d += 0.5; } }
    return s;
  });

  // --- mobiliario: luminarias cada 25 m al borde del sendero, bolsillos con banca hacia el agua cada 28 m (con caneca),
  // bolardos de luz en los cruces y a la entrada de los puentes, paneles interpretativos en los accesos
  const libreS = (s, d = 6) => lejos(s, sPuentes, d) && lejos(s, lagunas.map((L) => L.s), 4) && !bajoCruce(en(s, (p) => cSen(p) - 1.2), 3);
  const sPostes = [], sBancas = [];
  for (let s = 6; s < Lt - 3; s += 25) if (lejos(s, sPuentes, 4) && !bajoCruce(en(s, (p) => sIn(p) - 0.45), 2)) sPostes.push(s);
  for (let s = 16; s < Lt - 6; s += 28) if (wO(en(s)) > 2.3 && libreS(s, 8) && lejos(s, sPostes, 3)) sBancas.push(s);
  mob.add(postes(sPostes.map((s) => en(s, (p) => sIn(p) - 0.45)), 4.2));
  const bolsillos = [], lb = [], lc = [], sentados = [];
  sBancas.forEach((s, i) => {
    const [x, y, a] = en(s, (p) => sIn(p) - 0.78), [bx, by] = en(s, (p) => sIn(p) - 0.85);
    bolsillos.push(new THREE.BoxGeometry(2.8, 0.13, 1.5).rotateY(a).translate(x, 0.105, -y));
    lb.push(Object.assign([bx, by, a], { h: 0.17 }));
    if (i % 2 === 0) { const [cx, cy] = en(s + 1.55, (p) => sIn(p) - 0.6); lc.push(Object.assign([cx, cy, a], { h: 0.17 })); }
    const k = r();
    if (k < 0.65) [-0.45, 0.45].slice(0, k < 0.3 ? 2 : 1).forEach((u) => sentados.push(Object.assign([bx + Math.cos(a) * u, by + Math.sin(a) * u, a], { h: 0.26 })));
  });
  if (bolsillos.length) mob.add(malla(unir(bolsillos), C.concreto, true));
  mob.add(bancas(lb), canecas(lc));
  const lBol = [];
  cruzan.forEach((v) => {
    const sV = sDe((cruce(v, sc) || cruce(v, e)).p);
    let s0 = sV; while (s0 > 0 && distLinea(en(s0, (p) => cSen(p) - 1.2), v.p) < v.w + 0.3) s0 -= 0.5;
    let s1 = sV; while (s1 < Lt && distLinea(en(s1, (p) => cSen(p) - 1.2), v.p) < v.w + 0.3) s1 += 0.5;
    [s0 - 0.8, s1 + 0.8].forEach((s) => [(p) => sIn(p) + 0.55, (p) => cSen(p) - 1.2, (p) => sOut(p) - 0.45].forEach((o) => lBol.push(en(s, o))));
  });
  sPuentes.forEach((s) => [-1.95, 1.95].forEach((d) => lBol.push(en(s + d, (p) => sIn(p) + 0.4))));
  mob.add(bolardos(lBol.map(([x, y]) => [x, y])));
  // paneles: al comienzo, en el puente del medio, frente a la laguna y al final; al occidente de la ciclorruta si cabe,
  // si no en el talud, siempre de cara al sendero
  const sPan = [8, sPuentes[Math.floor(sPuentes.length / 2)] - 9, ...lagunas.map((L) => L.s + 7), Lt - 8].filter((s) => s != null && s > 0 && s < Lt && libreS(s, 4) && lejos(s, sBancas, 3) && lejos(s, sPostes, 2));
  const paneles = sPan.map((s) => { const p = en(s), oeste = W(p) - cOut(p) > 1.8; const [x, y, a] = en(s, oeste ? (pp) => cOut(pp) + 0.95 : (pp) => sIn(pp) - 0.55); return [x, y, oeste ? a : a + Math.PI]; });
  if (paneles.length) {
    const geoMarco = unir([new THREE.BoxGeometry(0.08, 1.15, 0.08).translate(-0.6, 0.575, 0), new THREE.BoxGeometry(0.08, 1.15, 0.08).translate(0.6, 0.575, 0), new THREE.BoxGeometry(1.36, 0.98, 0.07).translate(0, 1.42, -0.01), new THREE.BoxGeometry(1.5, 0.06, 0.24).translate(0, 1.94, 0)]);
    const geoCara = new THREE.PlaneGeometry(1.24, 0.87).translate(0, 1.42, 0.03);
    const imM = new THREE.InstancedMesh(geoMarco, C.madera, paneles.length), imC = new THREE.InstancedMesh(geoCara, C.panel, paneles.length);
    paneles.forEach(([x, y, a], i) => { m4.compose(v3.set(x, 0.07, -y), q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), a), s3.set(1, 1, 1)); imM.setMatrixAt(i, m4); imC.setMatrixAt(i, m4); });
    [imM, imC].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); mob.add(o); });
  }

  // --- puentes peatonales: tablero de tablas en arco rebajado (3 m), largueros de acero, baranda de parales de acero con
  // pasamanos de madera y cinta LED, estribos de concreto en las crestas del talud y una luminaria en cada extremo
  const P = { madera: [], metal: [], concreto: [], led: [] }, lucesP = [], enPuente = [];
  const H = (X) => 0.14 + 0.95 * (1 - (X / 6.4) ** 2), dH = (X) => (-2 * 0.95 * X) / (6.4 * 6.4);
  sPuentes.forEach((s, ip) => {
    const [x, y, a] = en(s), M = new THREE.Matrix4().makeRotationY(a + Math.PI / 2).setPosition(x, 0, -y), add = (k, g) => P[k].push(g.applyMatrix4(M));
    for (let X = -6.32; X <= 6.33; X += 0.17) add('madera', new THREE.BoxGeometry(0.15, 0.05, 3).rotateZ(Math.atan(dH(X))).translate(X, H(X) - 0.02, 0));
    for (let k = 0; k < 12; k++) {
      const X0 = -6.2 + (12.4 * k) / 12, X1 = -6.2 + (12.4 * (k + 1)) / 12, Xm = (X0 + X1) / 2, Lg = Math.hypot(X1 - X0, H(X1) - H(X0)), ang = Math.atan2(H(X1) - H(X0), X1 - X0);
      const seg = (h, d, dy, z) => new THREE.BoxGeometry(Lg + 0.02, h, d).rotateZ(ang).translate(Xm, H(Xm) + dy, z);
      [-1.42, 1.42].forEach((z) => { add('metal', seg(0.3, 0.12, -0.2, z)); add('madera', seg(0.05, 0.11, 1.05, z * 1.04)); add('led', seg(0.015, 0.05, 1.015, z * 1.04)); [0.38, 0.7].forEach((dy) => add('metal', seg(0.025, 0.025, dy, z * 1.04))); });
    }
    for (let X = -6.1; X <= 6.15; X += 1.525) [-1.48, 1.48].forEach((z) => add('metal', new THREE.BoxGeometry(0.06, 1.05, 0.06).translate(X, H(X) + 0.52, z)));
    [-3.3, 3.3].forEach((X) => add('concreto', new THREE.BoxGeometry(0.5, H(X) - 0.2, 3.2).translate(X, (H(X) - 0.2) / 2, 0)));
    [-6.4, 6.4].forEach((X) => add('concreto', new THREE.BoxGeometry(0.9, 0.3, 3.3).translate(X, -0.04, 0)));
    const enM = (X, Z) => { const p = new THREE.Vector3(X, 0, Z).applyMatrix4(M); return [p.x, -p.z]; };
    lucesP.push(enM(-6.2, -1.95), enM(5.2, 1.95));   // la del occidente en el talud, no en medio del sendero
    // alguien cruzando y alguien asomado al agua
    [[-1.4 + ip * 0.9, 0.55], [1.2, -1.05]].slice(0, ip % 2 ? 2 : 1).forEach(([X, Z], k) => enPuente.push(Object.assign([...enM(X, Z), a + (k ? Math.PI / 2 : 0)], { h: H(X) + 0.01 })));
  });
  if (sPuentes.length) {
    puentesG.add(malla(unir(P.madera), C.madera, true), malla(unir(P.metal), C.metal, true), malla(unir(P.concreto), C.concreto, true), malla(unir(P.led), luzComun()));
    puentesG.add(postes(lucesP, 3.8));
  }

  // --- laguna de retención y humedales: lámina de agua con borde de grava y piedras, juncos, jardín de lluvia y un deck
  // mirador de madera con baranda
  const L3 = { madera: [], pilote: [], metal: [], led: [] }, enLaguna = [], ninos = [], juncos = [], lluvia = [], lagoRocas = [], garzas = [];
  lagunas.forEach((Lg, k) => {
    const { pts, P0, t, n } = Lg, cerrada = pts;
    sudsG.add(malla(losa(cerrada, 0.13), C.laguna));
    sudsG.add(malla(perfil(cerrada, [[0.35, 0.125], [-1.2, 0.125]], { cerrado: true }), C.grava));
    // el deck: 4,6 m a lo largo de la orilla y 3,2 m hacia el agua, a 0,45 m
    const cen = [P0[0] + n[0] * 1.3, P0[1] + n[1] * 1.3], ang = Math.atan2(t[1], t[0]), M = new THREE.Matrix4().makeRotationY(ang).setPosition(cen[0], 0, -cen[1]), add = (key, g) => L3[key].push(g.applyMatrix4(M));
    // marco local: x a lo largo de la orilla, −z hacia el agua (n), z hacia el sendero
    for (let z = -1.6; z <= 1.6; z += 0.16) add('madera', new THREE.BoxGeometry(4.6, 0.05, 0.14).translate(0, 0.43, z));
    [[-2.1, -1.4], [2.1, -1.4], [-2.1, 1.4], [2.1, 1.4], [0, -1.4], [0, 1.4]].forEach(([px, pz]) => add('pilote', new THREE.CylinderGeometry(0.1, 0.1, 0.9, 8).translate(px, -0.05, pz)));
    add('pilote', new THREE.BoxGeometry(4.7, 0.18, 0.12).translate(0, 0.32, -1.6)); add('pilote', new THREE.BoxGeometry(4.7, 0.18, 0.12).translate(0, 0.32, 1.6));
    const borde = [[-2.25, 1.0], [-2.25, -1.55], [2.25, -1.55], [2.25, 1.0]];
    for (let i = 1; i < borde.length; i++) {
      const [a0, b0] = [borde[i - 1], borde[i]], len = Math.hypot(b0[0] - a0[0], b0[1] - a0[1]), an = Math.atan2(-(b0[1] - a0[1]), b0[0] - a0[0]), mx = (a0[0] + b0[0]) / 2, mz = (a0[1] + b0[1]) / 2;
      add('madera', new THREE.BoxGeometry(len + 0.1, 0.05, 0.11).rotateY(an).translate(mx, 1.5, mz)); add('led', new THREE.BoxGeometry(len, 0.015, 0.05).rotateY(an).translate(mx, 1.465, mz));
      [0.82, 1.14].forEach((h) => add('metal', new THREE.BoxGeometry(len, 0.025, 0.025).rotateY(an).translate(mx, h, mz)));
      for (let u = 0; u < len - 0.1; u += 1.2) add('metal', new THREE.BoxGeometry(0.06, 1.05, 0.06).translate(a0[0] + ((b0[0] - a0[0]) * u) / len, 0.97, a0[1] + ((b0[1] - a0[1]) * u) / len));
    }
    add('metal', new THREE.BoxGeometry(0.06, 1.05, 0.06).translate(2.25, 0.97, 1.0));
    // una banca de madera mirando al agua y la familia: dos adultos y dos niños en el deck, uno más en la orilla
    add('madera', new THREE.BoxGeometry(1.8, 0.06, 0.45).translate(0, 0.9, 0.9)); [-0.75, 0.75].forEach((px) => add('metal', new THREE.BoxGeometry(0.06, 0.44, 0.4).translate(px, 0.67, 0.9)));
    const enM = (X, Z) => { const p = new THREE.Vector3(X, 0, Z).applyMatrix4(M); return [p.x, -p.z]; };
    enLaguna.push(Object.assign([...enM(-1.2, -1.0), ang], { h: 0.45 }), Object.assign([...enM(0.9, -0.9), ang + 0.6], { h: 0.45 }));
    ninos.push(Object.assign([...enM(-0.4, -1.2), ang], { h: 0.45 }), Object.assign([...enM(0.2, -1.25), ang], { h: 0.45 }));
    const orilla = paralela(cerrada, -0.6, true), io = (Math.floor(cerrada.length / 2) + cerrada.indexOf(P0)) % cerrada.length;
    enLaguna.push(orilla[(io + 3) % orilla.length]); ninos.push(orilla[(io + 4) % orilla.length], orilla[(io + 5) % orilla.length].map((v, j) => v + (j ? 0.6 : 0.4)));
    // piedras del borde (no frente al deck), juncos en grupos dentro del agua y jardín de lluvia afuera
    const junto = (p) => Math.hypot(p[0] - cen[0], p[1] - cen[1]) < 3.6;
    const anillo = [...cerrada, cerrada[0]];
    aLoLargo(paralela(anillo, -0.25), 0.7).forEach(([x, y]) => { if (junto([x, y])) return; const s = 0.22 + r() * 0.26; q.setFromEuler(eu.set(r() * 3, r() * 3, r() * 3)); m4.compose(v3.set(x + (r() - 0.5) * 0.3, 0.12, -(y + (r() - 0.5) * 0.3)), q, s3.set(s * 1.2, s * 0.6, s)); lagoRocas.push(m4.clone()); });
    [[0.7, 0.62], [1.5, 0.8]].forEach(([o, paso], fi) => aLoLargo(paralela(anillo, o), paso).forEach(([x, y], i) => { if (junto([x, y]) || Math.sin(i * 0.37 + k + fi) < -0.35) return; juncos.push([x + (r() - 0.5) * 0.45, y + (r() - 0.5) * 0.45]); }));
    const ext = paralela(cerrada, -1.6, true);
    sembrar(humedales[k], 150, 1.0, 40 + k).forEach((p) => { const [d, , , qy] = respecto(p, e); if (!dentro(p, ext) && d > cOut([0, qy]) + 0.9) lluvia.push(p); });
    // dos garzas en la orilla de la laguna, lejos del deck
    [Math.floor(cerrada.length * 0.3), Math.floor(cerrada.length * 0.72)].forEach((j, i) => { const [x, y] = paralela(cerrada, 0.5, true)[(cerrada.indexOf(P0) + j) % cerrada.length]; garzas.push([x, y, r() * 6.28]); });
  });
  if (lagunas.length) {
    sudsG.add(malla(unir(L3.madera), C.madera, true), malla(unir(L3.pilote), C.pilote, true), malla(unir(L3.metal), C.metal, true), malla(unir(L3.led), luzComun()));
    // las piedras del borde, en su propia malla: son de la laguna (suds), no de las orillas del caño
    const im = new THREE.InstancedMesh(geoPiedra, C.roca, lagoRocas.length);
    lagoRocas.forEach((m, i) => im.setMatrixAt(i, m)); im.receiveShadow = true; im.computeBoundingSphere(); sudsG.add(im);
  }

  // --- verde: árboles nativos variados (sombra, guayacanes, flamboyanes) al occidente donde la franja es ancha y en la
  // orilla oriental si hay espacio; árboles de ribera en el talud ancho; palmas alineadas tras la ciclorruta; plantas de
  // ribera (helechos, heliconias, arbustos) en las crestas del talud; bosque inundable con sotobosque; juncos y jardín de lluvia
  const sLibre = (s, d) => lejos(s, sPuentes, d) && lejos(s, sBancas, 2.2) && lejos(s, sPostes, 1.6) && lejos(s, sPan, 1.8) && lejos(s, lagunas.map((L) => L.s), 3);
  const oeste = [], palmasO = [], este = [], ribera = [];
  for (let s = 5; s < Lt; s += 10.5) { const p = en(s); if (W(p) >= 14 && !bajoVia(en(s, (pp) => cOut(pp) + 4.8), 2)) oeste.push(en(s, (pp) => Math.min(W(pp) - 1.6, cOut(pp) + 4.8))); }
  for (let s = 9; s < Lt; s += 16) { const p = en(s); if (W(p) - cOut(p) >= 2.4 && sLibre(s, 5) && !bajoVia(en(s, (pp) => cOut(pp) + 1.3), 1.5)) palmasO.push(en(s, (pp) => cOut(pp) + 1.3)); }
  for (let s = 4; s < Lt; s += 11) { const p = en(s); if (E(p) >= 5.5 && lejos(s, sPuentes, 7) && !bajoVia(en(s, (pp) => -(E(pp) - 1.5)), 2)) este.push(en(s, (pp) => -(E(pp) - 1.5))); }
  for (let s = 11; s < Lt; s += 14) { const p = en(s); if (wO(p) > 2.6 && sLibre(s, 7) && !bajoCruce(p, 4)) ribera.push(en(s, (pp) => aO(pp) + 0.55 * wO(pp))); }
  const xy = (l) => l.map(([x, y]) => [x, y]);
  verde.add(arboles(xy(oeste), { alto: 10, semilla: 61, especie: 'mixto' }), arboles(xy(este), { alto: 8.5, semilla: 62, especie: 'mixto' }));
  verde.add(arboles(xy(ribera.filter((_, i) => i % 3 !== 1)), { alto: 7.5, semilla: 66, especie: 'sombra' }), arboles(xy(ribera.filter((_, i) => i % 3 === 1)), { alto: 7, semilla: 67, especie: 'flamboyan' }));
  // plantas de ribera: en la cresta de los dos taludes (no frente a las bancas, los postes ni los puentes)
  const plantas = { helecho: [], heliconia: [], arbusto: [], cordyline: [] };
  const reparte = (p, pesos) => { let u = r(); const t = Object.keys(pesos).find((k) => (u -= pesos[k]) < 0) || 'helecho'; plantas[t].push(p); };
  for (let s = 1; s < Lt; s += 2.1) { const p = en(s); if (wO(p) < 0.9 || !sLibre(s, 7.5) || bajoCruce(p, 1)) continue; const [x, y] = en(s + (r() - 0.5) * 0.8, (pp) => aO(pp) + (0.3 + r() * 0.35) * wO(pp)); reparte([x, y], { helecho: 0.55, heliconia: 0.3, cordyline: 0.15 }); }
  for (let s = 2; s < Lt; s += 2.6) { const p = en(s); if (wE(p) < 0.8 || !lejos(s, sPuentes, 7.5) || bajoCruce(p, 1) || gaviones(p)) continue; const [x, y] = en(s + (r() - 0.5) * 0.8, (pp) => -(aE(pp) + (0.35 + r() * 0.3) * wE(pp))); reparte([x, y], { helecho: 0.6, heliconia: 0.4 }); }
  // bosque inundable: árboles apartados del cauce y de las sendas que cruzan el polígono, con sotobosque
  const libre = (p) => distLinea(p, e) > 4 && distLinea(p, sc) > 2.6 && distLinea(p, cc) > 2.4 && !bajoVia(p, 1);
  bosques.forEach((poly, i) => {
    // de cada siete puntos: uno de palma (las palmas del humedal rompen el dosel parejo), dos de especie mixta y el resto de
    // árboles de sombra altos
    const pts = sembrar(poly, 64, 4.5, 70 + i).filter(libre), cada = (...k) => pts.filter((_, j) => k.includes(j % 7));
    verde.add(arboles(cada(0, 2, 4, 6), { alto: 12, semilla: 64 + i }), arboles(cada(1, 5), { alto: 10, semilla: 74 + i, especie: 'mixto' }));
    palmasO.push(...cada(3));
    sembrar(poly, 110, 1.8, 90 + i).filter((p) => libre(p) && distLinea(p, e) > 4.5).forEach((p) => reparte(p, { helecho: 0.45, arbusto: 0.3, heliconia: 0.25 }));
  });
  lluvia.forEach((p) => reparte(p, { heliconia: 0.35, cordyline: 0.3, helecho: 0.25, arbusto: 0.1 }));
  // las palmas tras la ciclorruta y las del bosque, en una sola malla por material
  verde.add(palmas(xy(palmasO), { alto: 11, semilla: 63 }));
  verde.add(matas(juncos.filter((_, i) => i % 5), { tipo: 'helecho', alto: 1.35, semilla: 78 }), matas(juncos.filter((_, i) => !(i % 5)), { tipo: 'heliconia', alto: 1.7, semilla: 79 }));
  // garzas: las de la laguna y tres más en el agua del caño, junto a la orilla (la vida que vuelve al cauce)
  [0.18, 0.55, 0.86].forEach((f) => { const s = f * Lt; if (lejos(s, sPuentes, 10) && !bajoCruce(en(s), 4)) { const [x, y, a] = en(s, (p) => (f > 0.5 ? aO(p) - 0.6 : -(aE(p) - 0.6))); garzas.push([x, y, a + (f > 0.5 ? 0.6 : -2.4)]); } });
  if (garzas.length) {
    const g = new THREE.Group(), imB = new THREE.InstancedMesh(geoGarza.blanco, mat(new THREE.Color('#f4f3ee'), { roughness: 0.7 }), garzas.length), imP2 = new THREE.InstancedMesh(geoGarza.patas, mat(new THREE.Color('#b08a2e'), { roughness: 0.7 }), garzas.length);
    garzas.forEach(([x, y, a], i) => { m4.compose(v3.set(x, 0.12, -y), q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), a), s3.set(1, 1, 1)); imB.setMatrixAt(i, m4); imP2.setMatrixAt(i, m4); });
    [imB, imP2].forEach((o) => { o.castShadow = true; o.computeBoundingSphere(); g.add(o); });
    verde.add(g);
  }
  const ALTO = { helecho: 0.85, heliconia: 1.5, arbusto: 1.1, cordyline: 1 };
  // las matas bajas no proyectan sombra (cientos de instancias que en el mapa de sombra apenas se notan); los árboles sí
  Object.entries(plantas).forEach(([t, l], i) => { if (!l.length) return; const g = matas(l, { tipo: t, alto: ALTO[t], semilla: 80 + i }); if (t !== 'heliconia') g.traverse((o) => { o.castShadow = false; }); verde.add(g); });

  // --- gente: paseantes por el sendero, ciclistas por la ciclorruta (en su sentido), sentados en las bancas, en los
  // puentes y una familia en la laguna
  const paseo = [], ciclistas = [], bicis = [];
  for (let s = 5 + r() * 6; s < Lt - 3; s += 13 + r() * 14) { if (!lejos(s, sPuentes, 2.5)) continue; const o = (pp) => cSen(pp) - 1.2 + (r() - 0.5) * 1.6; const [x, y, a] = en(s, o); paseo.push([x, y, a + (r() < 0.5 ? 0 : Math.PI)]); if (r() < 0.3) { const [x2, y2] = en(s + 0.7, (pp) => o(pp) + 0.55); paseo.push([x2, y2, a]); } }
  for (let s = 20 + r() * 20; s < Lt - 5; s += 38 + r() * 30) {
    const sube = r() < 0.5, [x, y, a] = en(s, (pp) => cSen(pp) + 1.65 + (sube ? -0.6 : 0.6)), rot = sube ? a : a + Math.PI;
    bicis.push([x, y, rot]); ciclistas.push(Object.assign([x - Math.cos(rot) * 0.12, y - Math.sin(rot) * 0.12, rot], { h: 0.17 }));
  }
  personas.add(gente([...paseo, ...ciclistas, ...enLaguna], { semilla: 31 }));
  // los de los puentes, con su puente: crecen con él al animarse (en el grupo de la gente quedaban en el aire)
  if (enPuente.length) puentesG.add(gente(enPuente, { semilla: 37 }));
  if (sentados.length) personas.add(gente(sentados, { sentado: true, semilla: 33 }));
  if (ninos.length) personas.add(gente(ninos, { semilla: 35, escala: 0.62 }));
  if (bicis.length) {
    const imF = new THREE.InstancedMesh(geoBici.marco, C.bici, bicis.length), imW = new THREE.InstancedMesh(geoBici.ruedas, C.llanta, bicis.length);
    bicis.forEach(([x, y, a], i) => { m4.compose(v3.set(x, 0.11, -y), q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), a), s3.set(1, 1, 1)); imF.setMatrixAt(i, m4); imW.setMatrixAt(i, m4); imF.setColorAt(i, COLOR_BICI[i % COLOR_BICI.length]); });
    [imF, imW].forEach((o) => { o.castShadow = true; o.computeBoundingSphere(); personas.add(o); });
  }

  raiz.userData.partes = { cauce, orillas, sendas, verde, puentes: puentesG, suds: sudsG, gente: personas };
  raiz.userData.eje = e;
  return raiz;
}
