// Plantas industriales de la propuesta, armadas con geometría propia y orientadas sobre su lote:
//  · PTAR central del casco urbano: pretratamiento, reactores anaerobios UASB, filtros percoladores, sedimentadores,
//    lechos de secado de lodos, edificio de operación y laboratorio, cerramiento con barrera verde;
//  · módulo de ampliación de la PTAP (de 40 a ~60 L/s): floculador, sedimentador de placas y filtros rápidos;
//  · parque agroindustrial: naves por componente, silos, tanques, domos del biodigestor, pilas de compostaje, patios y
//    camiones, organizados en zona sucia, limpia y logística;
//  · granja solar centralizada: filas de módulos en estructura fija, casetas de inversores y subestación elevadora.
// Cada función recibe el centro (x, y) y el rumbo del lote (grados desde el oriente, antihorario) y devuelve un grupo con
// partes nombradas para animarlas.
import { THREE, mat } from '../../core.js';
import { nave, silo, tanque, domo, losa, cinta, arboles, unir, azar, V } from '../geo3d.js';

const sombra = (o) => { o.traverse((k) => { if (k.isMesh) { k.castShadow = true; k.receiveShadow = true; } }); return o; };
function marco(cx, cy, rumbo) {
  const g = new THREE.Group(); g.position.copy(V(cx, cy)); g.rotation.y = THREE.MathUtils.degToRad(rumbo);
  return g;
}
const capa = (raiz, n) => { const g = new THREE.Group(); g.name = n; raiz.add(g); return g; };
const aModelo = (raiz) => (u, v) => { raiz.updateMatrixWorld(true); const p = new THREE.Vector3(u, 0, -v).applyMatrix4(raiz.matrixWorld); return [p.x, -p.z]; };

// ---------------------------------------------------------------- PTAR central (UASB + filtros percoladores)
// ~ 170 × 110 m (1,9 ha): en el marco local u va a lo largo del lote y v a lo ancho; el agua entra por u negativo
export function ptar(cx, cy, rumbo = 0, { reactores = 3, filtros = 2 } = {}) {
  const raiz = marco(cx, cy, rumbo), M = {
    piso: mat(new THREE.Color('#b9b5aa'), { roughness: 0.95 }), via: mat(new THREE.Color('#6a6d70'), { roughness: 0.95 }),
    concreto: mat(new THREE.Color('#d2cec4'), { roughness: 0.85 }), reactor: mat(new THREE.Color('#9fb3bd'), { roughness: 0.5, metalness: 0.3 }),
    agua: mat(new THREE.Color('#5d8f86'), { roughness: 0.2 }), aguaClara: mat(new THREE.Color('#4aa3c8'), { roughness: 0.12 }), lodo: mat(new THREE.Color('#5b4a3a'), { roughness: 1 }),
    roca: mat(new THREE.Color('#8e8b84'), { roughness: 1 }), techo: mat(new THREE.Color('#3f464c'), { roughness: 0.5, metalness: 0.4 }), cerco: mat(new THREE.Color('#20252a'), { transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }),
  };
  const piso = capa(raiz, 'piso'), obras = capa(raiz, 'obras'), verde = capa(raiz, 'verde');
  piso.add(new THREE.Mesh(losa([[-88, -56], [88, -56], [88, 56], [-88, 56]], 0.06), M.piso));
  piso.add(new THREE.Mesh(cinta([[-88, -44], [88, -44]], 7, 0.08), M.via), new THREE.Mesh(cinta([[60, -44], [60, 50]], 6, 0.08), M.via));
  // pretratamiento: canal de rejillas y desarenador
  obras.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(26, 1.6, 6).translate(-70, 0.8, 0), M.concreto)));
  obras.add(new THREE.Mesh(new THREE.BoxGeometry(24, 0.1, 4.6).translate(-70, 1.55, 0), M.agua));
  // reactores UASB (cilindros de 16 m de diámetro y 6 m de alto) en fila
  for (let i = 0; i < reactores; i++) {
    const r = new THREE.Group(); r.add(new THREE.Mesh(new THREE.CylinderGeometry(8, 8, 6, 36).translate(0, 3, 0), M.reactor));
    r.add(new THREE.Mesh(new THREE.CylinderGeometry(8.3, 8.3, 0.4, 36).translate(0, 6.2, 0), M.techo));
    r.add(new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 3, 8).translate(0, 7.8, 0), M.techo));
    r.position.set(-36 + i * 21, 0, -10); obras.add(sombra(r));
  }
  // filtros percoladores (lecho de piedra con brazo distribuidor) y sedimentadores secundarios
  for (let i = 0; i < filtros; i++) {
    const f = tanque(0, 0, 11, 4.5, { m: M.concreto }); f.position.set(-26 + i * 28, 0, -(28));
    const lecho = new THREE.Mesh(new THREE.CylinderGeometry(10.6, 10.6, 0.3, 36).translate(0, 4.1, 0), M.roca); f.add(lecho);
    const brazo = new THREE.Mesh(new THREE.BoxGeometry(21, 0.25, 0.5).translate(0, 4.7, 0), M.techo); brazo.name = 'brazo'; f.add(brazo);
    obras.add(sombra(f));
  }
  [[34, 26], [56, 26]].forEach(([u, v]) => { const s = tanque(0, 0, 8, 3.6, { m: M.concreto, agua: M.aguaClara }); s.position.set(u, 0, -v); obras.add(sombra(s)); });
  // lechos de secado de lodos y edificio de operación con laboratorio
  for (let i = 0; i < 4; i++) { obras.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(14, 0.9, 9).translate(32 + (i % 2) * 16, 0.45, -(-6 + Math.floor(i / 2) * 11)), M.concreto))); obras.add(new THREE.Mesh(new THREE.BoxGeometry(13, 0.1, 8).translate(32 + (i % 2) * 16, 0.88, -(-6 + Math.floor(i / 2) * 11)), M.lodo)); }
  const edif = nave(0, 0, 12, 22, 4.2, 0, { techo: 'plano', muro: M.concreto, cubierta: M.techo }); edif.position.set(72, 0, -(-24)); obras.add(edif);
  // cerramiento y barrera verde perimetral
  const per = [[-88, -56], [88, -56], [88, 56], [-88, 56], [-88, -56]], cerco = [];
  for (let i = 1; i < per.length; i++) { const [a, b] = [per[i - 1], per[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]); cerco.push(new THREE.PlaneGeometry(L, 2.4).rotateY(Math.atan2(b[1] - a[1], b[0] - a[0])).translate((a[0] + b[0]) / 2, 1.2, -(a[1] + b[1]) / 2)); }
  obras.add(new THREE.Mesh(unir(cerco), M.cerco));
  const borde = [];
  for (let u = -84; u <= 84; u += 7) borde.push([u, 61], [u, -61]);
  for (let v = -54; v <= 54; v += 8) borde.push([-93, v], [93, v]);
  verde.add(arboles(borde, { alto: 10, semilla: 81 }));
  raiz.userData.partes = { piso, obras, verde };
  raiz.userData.aModelo = aModelo(raiz);
  raiz.userData.contorno = [[-95, -63], [95, -63], [95, 63], [-95, 63]].map(([u, v]) => raiz.userData.aModelo(u, v));
  raiz.userData.entrada = raiz.userData.aModelo(-86, 0); raiz.userData.salida = raiz.userData.aModelo(86, 20);
  return raiz;
}

// ---------------------------------------------------------------- ampliación de la PTAP (módulo de ~20 L/s)
export function moduloPTAP(cx, cy, rumbo = 0) {
  const raiz = marco(cx, cy, rumbo), M = { concreto: mat(new THREE.Color('#d6d2c8'), { roughness: 0.85 }), agua: mat(new THREE.Color('#4aa3c8'), { roughness: 0.12 }), techo: mat(new THREE.Color('#2f6fb3'), { roughness: 0.5, metalness: 0.3 }) };
  const obras = capa(raiz, 'obras');
  [[-14, 0, 12, 8], [2, 0, 14, 10], [18, 0, 10, 10]].forEach(([u, v, w, d], i) => {
    obras.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(w, 3.2, d).translate(u, 1.6, -v), M.concreto)));
    obras.add(new THREE.Mesh(new THREE.BoxGeometry(w - 0.8, 0.1, d - 0.8).translate(u, 3.15, -v), M.agua));
    if (i === 2) obras.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(w + 1, 0.3, d + 1).translate(u, 5.6, -v), M.techo)));
  });
  raiz.userData.partes = { obras }; raiz.userData.aModelo = aModelo(raiz);
  return raiz;
}

// ---------------------------------------------------------------- parque agroindustrial
// comps: [{ id, tipo, u, v, w, d, rot }] en el marco local del lote (u a lo largo, v a lo ancho; w y d son la huella del
// componente: la nave ocupa la mayor parte y el resto queda para silos, tanques o patio). lote: polígono local del predio
// (si no viene, un rectángulo de ancho × fondo); vias: [{ puntos, ancho }]; restricciones: polígonos sin construir.
const TIPOS = {
  matadero: { h: 7, techo: 'dosaguas', color: '#e9e4da' }, pescado: { h: 6.5, techo: 'dosaguas', color: '#e3eef2' },
  concentrados: { h: 14, techo: 'dosaguas', color: '#ece6d6', silos: 4 }, trilladora: { h: 10, techo: 'arco', color: '#efe9da', silos: 3 },
  leche: { h: 6, techo: 'plano', color: '#f1f1ee', tanques: 2 }, maquinaria: { h: 8, techo: 'arco', color: '#d9d4c8', patio: true },
  frio: { h: 8, techo: 'plano', color: '#eef2f4' }, admin: { h: 7, techo: 'plano', color: '#f3efe6' }, porteria: { h: 4.5, techo: 'plano', color: '#f3efe6' },
  bodegas: { h: 8, techo: 'dosaguas', color: '#e6e1d6' }, biodigestor: { domos: 2, pilas: 5 }, compostaje: { pilas: 6 }, ptar: { lagunas: 2 },
  corrales: { corral: true }, muelle: { muelle: true },
};
export function parqueAgro({ centro, rumbo = 0, ancho = 360, fondo = 260, comps = [], zonas = [], lote = null, vias = null, restricciones = [] }) {
  const raiz = marco(centro[0], centro[1], rumbo), r = azar(91);
  const piso = capa(raiz, 'piso'), obras = capa(raiz, 'obras'), verde = capa(raiz, 'verde'), zonasG = capa(raiz, 'zonas');
  const M = {
    piso: mat(new THREE.Color('#bdb6a6'), { roughness: 0.95 }), patio: mat(new THREE.Color('#6d7074'), { roughness: 0.95 }), techo: mat(new THREE.Color('#9aa3aa'), { roughness: 0.45, metalness: 0.5 }),
    silo: mat(new THREE.Color('#c4ccd2'), { roughness: 0.35, metalness: 0.6 }), tanque: mat(new THREE.Color('#e6eaed'), { roughness: 0.3, metalness: 0.5 }), domo: mat(new THREE.Color('#3f6e4a'), { roughness: 0.7 }),
    compost: mat(new THREE.Color('#5b4733'), { roughness: 1, flatShading: true }), laguna: mat(new THREE.Color('#5e8c80'), { roughness: 0.25 }), cerca: mat(new THREE.Color('#6b5640'), { roughness: 0.9 }),
    madera: mat(new THREE.Color('#9a6b3f'), { roughness: 0.8 }), camion: [mat(new THREE.Color('#e9e9e6'), { roughness: 0.4 }), mat(new THREE.Color('#c0392b'), { roughness: 0.4 }), mat(new THREE.Color('#2d5aa0'), { roughness: 0.4 })],
    maquina: mat(new THREE.Color('#f2b632'), { roughness: 0.5 }), verdeM: mat(new THREE.Color('#3f8a3a'), { roughness: 0.6 }),
    retiro: new THREE.MeshBasicMaterial({ color: new THREE.Color('#d9363e'), transparent: true, opacity: 0.18, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }),
  };
  const poli = lote || [[-ancho / 2, -fondo / 2], [ancho / 2, -fondo / 2], [ancho / 2, fondo / 2], [-ancho / 2, fondo / 2]];
  piso.add(new THREE.Mesh(losa(poli, 0.05), M.piso));
  (vias || [{ puntos: [[-ancho / 2, 0], [ancho / 2, 0]], ancho: 10 }, { puntos: [[-ancho / 2 + 40, -fondo / 2], [-ancho / 2 + 40, fondo / 2]], ancho: 9 }])
    .forEach((v) => piso.add(new THREE.Mesh(cinta(v.puntos, v.ancho || 8, 0.08), M.patio)));
  zonas.forEach((z) => { const m = new THREE.Mesh(losa(z.poligono, 0.12), new THREE.MeshBasicMaterial({ color: new THREE.Color(z.color), transparent: true, opacity: 0.2, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 })); m.userData.zona = z.id; zonasG.add(m); });
  restricciones.forEach((poly) => zonasG.add(new THREE.Mesh(losa(poly, 0.14), M.retiro)));
  const partes = {};
  comps.forEach((c) => {
    const t = TIPOS[c.tipo] || TIPOS.admin, g = new THREE.Group(), W = c.w || 30, D = c.d || 20;
    g.name = c.id; g.position.set(c.u, 0, -c.v); g.rotation.y = THREE.MathUtils.degToRad(c.rot || 0);
    const muro = t.color ? mat(new THREE.Color(t.color), { roughness: 0.85 }) : null;
    if (t.patio) {
      // nave en el 40 % del fondo y patio con la maquinaria en el resto
      g.add(nave(0, D * 0.27, W * 0.86, D * 0.36, t.h, 0, { techo: t.techo, muro, cubierta: M.techo }));
      g.add(new THREE.Mesh(losa([[-W / 2 + 1, -D / 2 + 1], [W / 2 - 1, -D / 2 + 1], [W / 2 - 1, D * 0.05], [-W / 2 + 1, D * 0.05]], 0.09), M.patio));
      for (let i = 0; i < 10; i++) { const m = new THREE.Mesh(new THREE.BoxGeometry(4.5, 2.6, 2.4).translate(0, 1.3, 0), i % 3 === 2 ? M.verdeM : M.maquina); m.position.set(-W / 2 + 7 + (i % 5) * (W - 14) / 4, 0, -(-D / 2 + 7 + Math.floor(i / 5) * 12)); g.add(sombra(m)); }
    } else if (t.h) {
      const extra = t.silos ? 10 : t.tanques ? 6 : 0, w = (W - extra) * 0.9, d = D * 0.84;
      g.add(nave(-extra / 2, 0, w, d, t.h, 0, { techo: t.techo, muro, cubierta: M.techo }));
      for (let i = 0; i < (t.silos || 0); i++) g.add(silo(W / 2 - 4.6, -d / 2 + 5 + (i * (d - 10)) / Math.max(1, t.silos - 1), 4, t.h + 6, M.silo));
      for (let i = 0; i < (t.tanques || 0); i++) { const tk = new THREE.Mesh(new THREE.CylinderGeometry(2, 2, 6, 20).rotateZ(Math.PI / 2).translate(0, 2.4, 0), M.tanque); tk.position.set(W / 2 - 3, 0, -(-d / 4 + i * (d / 2))); tk.rotation.y = Math.PI / 2; g.add(sombra(tk)); }
    }
    if (t.domos) { const dz = t.pilas ? D / 4 : 0; for (let i = 0; i < t.domos; i++) g.add(domo(-W / 4 + i * (W / 2), dz, Math.min(9, W / 6), M.domo)); }
    if (t.pilas) { const n = t.pilas, z0 = t.domos ? -D / 4 : 0, lp = Math.min(34, W * 0.8); for (let i = 0; i < n; i++) { const p = new THREE.Mesh(new THREE.CylinderGeometry(2, 2, lp, 10, 1, false, 0, Math.PI).rotateZ(Math.PI / 2), M.compost); p.position.set(0, 0, -(z0 - (D / 4.5) + (i * (D / 2.2)) / Math.max(1, n - 1))); g.add(sombra(p)); } }
    for (let i = 0; i < (t.lagunas || 0); i++) { const h = D / (t.lagunas * 1.25), y0 = -D / 2 + 3 + i * (h + 4); g.add(new THREE.Mesh(losa([[-W / 2 + 3, y0], [W / 2 - 3, y0], [W / 2 - 3, y0 + h], [-W / 2 + 3, y0 + h]], 0.1), M.laguna)); }
    if (t.corral) { const cerc = [], nx = Math.max(2, Math.round(W / 10)); for (let i = 0; i <= nx; i++) cerc.push(new THREE.BoxGeometry(0.15, 1.5, D * 0.92).translate(-W / 2 + (i * W) / nx, 0.75, 0)); cerc.push(new THREE.BoxGeometry(W, 1.5, 0.15).translate(0, 0.75, -D * 0.46), new THREE.BoxGeometry(W, 1.5, 0.15).translate(0, 0.75, D * 0.46)); g.add(sombra(new THREE.Mesh(unir(cerc), M.cerca))); }
    if (t.muelle) { g.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(W, 1.6, D).translate(0, 0.8, 0), M.madera))); const barc = new THREE.Mesh(new THREE.BoxGeometry(W * 0.9, 2.4, 9).translate(0, 1.2, 0), M.camion[2]); barc.position.set(0, 0, -(D / 2 + 6)); g.add(sombra(barc)); }
    sombra(g); obras.add(g); partes[c.id] = g;
  });
  // camiones en la vía interna y barrera verde en el borde del predio
  const via0 = (vias && vias[0]?.puntos) || [[-ancho / 2, 0], [ancho / 2, 0]];
  for (let i = 0; i < 8; i++) { const k = Math.min(via0.length - 2, Math.floor(r() * (via0.length - 1))), f = r(), [a, b] = [via0[k], via0[k + 1]], c = new THREE.Group(), m = M.camion[i % 3]; c.add(new THREE.Mesh(new THREE.BoxGeometry(9, 3.2, 2.5).translate(-1.2, 1.9, 0), m), new THREE.Mesh(new THREE.BoxGeometry(2.6, 2.6, 2.5).translate(4.3, 1.6, 0), M.camion[0])); c.position.set(a[0] + (b[0] - a[0]) * f, 0, -(a[1] + (b[1] - a[1]) * f)); c.rotation.y = Math.atan2(b[1] - a[1], b[0] - a[0]); obras.add(sombra(c)); }
  const [pu, pv] = [poli.reduce((a, q) => a + q[0], 0) / poli.length, poli.reduce((a, q) => a + q[1], 0) / poli.length], borde = [];
  for (let i = 0; i < poli.length; i++) {
    const [a, b] = [poli[i], poli[(i + 1) % poli.length]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.floor(L / 9));
    for (let k = 0; k < n; k++) { const x = a[0] + ((b[0] - a[0]) * k) / n, y = a[1] + ((b[1] - a[1]) * k) / n, dd = Math.hypot(x - pu, y - pv) || 1; borde.push([x - ((x - pu) / dd) * 3, y - ((y - pv) / dd) * 3]); }
  }
  verde.add(arboles(borde, { alto: 11, semilla: 93 }));
  raiz.userData.partes = { piso, obras, verde, zonas: zonasG, comps: partes };
  raiz.userData.aModelo = aModelo(raiz);
  raiz.userData.contorno = poli.map(([u, v]) => raiz.userData.aModelo(u, v));
  return raiz;
}

// ---------------------------------------------------------------- granja solar centralizada
// filas de módulos de 550 Wp (2,28 × 1,13 m) en estructura fija inclinada 10° al sur, dos módulos en vertical por mesa
export function granjaSolar(poligono, { kwp = 1500, paso = 7.5, salida = null } = {}) {
  const raiz = new THREE.Group(), xs = poligono.map((p) => p[0]), ys = poligono.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const dentro = ([x, y]) => { let d = false; for (let i = 0, j = poligono.length - 1; i < poligono.length; j = i++) { const [xi, yi] = poligono[i], [xj, yj] = poligono[j]; if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d; } return d; };
  // las filas se llenan desde el lado de la salida de la línea, dejando una franja libre para inversores y subestación
  const norte = salida ? salida[1] > (y0 + y1) / 2 : false, franja = salida ? 14 : 6, filas = [];
  if (norte) for (let y = y1 - franja - 2.3; y >= y0 + 4; y -= paso) filas.push(y);
  else for (let y = y0 + franja + 2.3; y <= y1 - 4; y += paso) filas.push(y);
  const mesas = [], n0 = Math.ceil((kwp * 1000) / 550 / 2);   // mesas de dos módulos en vertical
  for (const y of filas) {
    for (let x = x0 + 4; x <= x1 - 4 && mesas.length < n0; x += 1.16) if ([[-0.6, -2.3], [0.6, -2.3], [0.6, 2.3], [-0.6, 2.3]].every(([dx, dy]) => dentro([x + dx, y + dy]))) mesas.push([x, y]);
    if (mesas.length >= n0) break;
  }
  const panel = mat(new THREE.Color('#1c2b48'), { roughness: 0.25, metalness: 0.55 }), marcoM = mat(new THREE.Color('#9aa3aa'), { roughness: 0.5, metalness: 0.6 });
  // módulos inclinados 10° hacia el sur (la normal mira al sur, −y del modelo = +z de three)
  const geoP = new THREE.BoxGeometry(1.13, 0.04, 4.56).rotateX(0.175).translate(0, 1.6, 0), geoS = new THREE.BoxGeometry(0.08, 1.6, 0.08).translate(0, 0.8, 0);
  const P = new THREE.InstancedMesh(geoP, panel, mesas.length), S = new THREE.InstancedMesh(geoS, marcoM, mesas.length), m4 = new THREE.Matrix4();
  mesas.forEach(([x, y], i) => { m4.makeTranslation(x, 0, -y); P.setMatrixAt(i, m4); S.setMatrixAt(i, m4); });
  [P, S].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); raiz.add(o); });
  raiz.userData.instancias = [P, S];
  const kw = Math.round((mesas.length * 2 * 550) / 1000);
  // subestación elevadora a 13,2 kV junto a la salida (dentro del predio) y casetas de inversores en la franja libre
  const cx = xs.reduce((a, v) => a + v, 0) / xs.length, cy = ys.reduce((a, v) => a + v, 0) / ys.length;
  let sp = salida ? [...salida] : [cx + 40, y0 + 6];
  if (salida) for (let k = 0; k < 200 && !dentro(sp); k++) { const d = Math.hypot(cx - sp[0], cy - sp[1]) || 1; sp = [sp[0] + ((cx - sp[0]) / d) * 2, sp[1] + ((cy - sp[1]) / d) * 2]; }
  if (salida) { const d = Math.hypot(cx - sp[0], cy - sp[1]) || 1; sp = [sp[0] + ((cx - sp[0]) / d) * 6, sp[1] + ((cy - sp[1]) / d) * 6]; }
  const yF = norte ? y1 - franja / 2 : y0 + franja / 2, inv = new THREE.Group(), gris = mat(new THREE.Color('#e8e8e4')), acero = mat(new THREE.Color('#7f878e'), { metalness: 0.4, roughness: 0.5 });
  [-24, -48, -72].map((d) => [sp[0] + d, yF]).filter((q) => dentro(q)).forEach(([x, y]) => inv.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(6, 2.8, 2.6).translate(x, 1.4, -y), gris))));
  inv.add(sombra(new THREE.Mesh(new THREE.BoxGeometry(9, 4, 7).translate(sp[0], 2, -sp[1]), acero)));
  raiz.add(inv);
  raiz.userData.kwp = kw; raiz.userData.mesas = mesas.length;
  raiz.userData.subestacion = sp;
  return raiz;
}
