// Piezas 3D de la propuesta hechas con geometría propia (sin modelos externos): losas y prismas a partir de polígonos,
// cintas sobre polilíneas, tubos, árboles y palmas instanciados, naves, silos, tanques, graderías, cubiertas tensadas,
// torres de luz, barandas, enrocados, muelles y letras. Todo en metros sobre el plano del modelo: x al oriente y y al
// norte (en three, z = −y). Las piezas nacen con la base en y = 0 para que crezcan desde el piso al animarlas.
import { THREE, mat, gsap } from '../core.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

export const V = (x, y, h = 0) => new THREE.Vector3(x, h, -y);
// Une geometrías en una sola (una llamada de dibujo): sin coordenadas de textura, que no todas traen
export function unir(geos) {
  return mergeGeometries(geos.map((g) => { const n = g.index ? g.toNonIndexed() : g.clone(); n.deleteAttribute('uv'); if (!n.attributes.normal) n.computeVertexNormals(); return n; }));
}
const RX = new THREE.Matrix4().makeRotationX(-Math.PI / 2);

// Forma 2D (x, y al norte) que al girar −90° en X queda acostada, con y hacia el norte (−z)
export function forma(pts, huecos = []) {
  const s = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)));
  huecos.forEach((h) => s.holes.push(new THREE.Path(h.map(([x, y]) => new THREE.Vector2(x, y)))));
  return s;
}
// Superficie plana a la altura h
export function losa(pts, h = 0, huecos) {
  const g = new THREE.ShapeGeometry(forma(pts, huecos));
  g.applyMatrix4(RX); g.translate(0, h, 0);
  return g;
}
// Prisma vertical de alto a sobre el polígono (base en h0)
export function prisma(pts, a, h0 = 0, huecos) {
  const g = new THREE.ExtrudeGeometry(forma(pts, huecos), { depth: a, bevelEnabled: false, curveSegments: 6 });
  g.applyMatrix4(RX); g.translate(0, h0, 0);
  return g;
}
// Rectángulo centrado en (cx, cy), de ancho w (eje local x) y fondo d, girado rot radianes (antihorario desde el oriente)
export function rect(cx, cy, w, d, rot = 0) {
  const c = Math.cos(rot), s = Math.sin(rot);
  return [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map(([x, y]) => [cx + x * c - y * s, cy + x * s + y * c]);
}
// Punto local (u al «frente», v a la izquierda) de un marco con origen (ox, oy) y rumbo rot
export const local = (ox, oy, rot) => (u, v) => [ox + u * Math.cos(rot) - v * Math.sin(rot), oy + u * Math.sin(rot) + v * Math.cos(rot)];

// Cinta de ancho fijo sobre una polilínea (andenes, ciclorrutas, senderos, colectores vistos en planta)
export function cinta(pts, ancho, h = 0.05) {
  const pos = [], idx = [], w = ancho / 2;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    let dx = b[0] - a[0], dy = b[1] - a[1]; const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    const k = pos.length / 3;
    pos.push(pts[i][0] - dy * w, h, -(pts[i][1] + dx * w), pts[i][0] + dy * w, h, -(pts[i][1] - dx * w));
    if (i) idx.push(k - 2, k - 1, k, k - 1, k + 1, k);   // caras hacia arriba (normal +y): se ven desde la cámara
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx); g.computeVertexNormals();
  return g;
}
// Longitud de una polilínea y punto a una fracción t de su recorrido
export function largo(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); return L; }
export function puntoEn(pts, t) {
  const L = largo(pts) * THREE.MathUtils.clamp(t, 0, 1);
  let acc = 0;
  for (let i = 1; i < pts.length; i++) {
    const s = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (acc + s >= L) { const u = s ? (L - acc) / s : 0; return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * u, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * u, Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])]; }
    acc += s;
  }
  const n = pts.length - 1; return [pts[n][0], pts[n][1], n ? Math.atan2(pts[n][1] - pts[n - 1][1], pts[n][0] - pts[n - 1][0]) : 0];
}
// Puntos repartidos cada paso metros a lo largo de la polilínea, corridos off metros a la izquierda (negativo: derecha)
export function aLoLargo(pts, paso, off = 0, desde = 0) {
  const out = [], L = largo(pts);
  for (let s = desde; s <= L; s += paso) { const [x, y, a] = puntoEn(pts, s / L); out.push([x - Math.sin(a) * off, y + Math.cos(a) * off, a]); }
  return out;
}
// Polilínea suavizada (Catmull-Rom centrípeta) con n puntos
export function suave(pts, n = 64) {
  if (pts.length < 3) return pts;
  const c = new THREE.CatmullRomCurve3(pts.map(([x, y]) => new THREE.Vector3(x, y, 0)), false, 'centripetal');
  return c.getSpacedPoints(n).map((p) => [p.x, p.y]);
}
// Tubo sobre una polilínea a la altura h (tuberías y colectores); se dibuja de a poco con revelar()
export function tubo(pts, radio, h = 0.4, segRadio = 8) {
  const curva = new THREE.CatmullRomCurve3(pts.map(([x, y]) => V(x, y, h)), false, 'centripetal', 0.2);
  return new THREE.TubeGeometry(curva, Math.max(16, Math.round(largo(pts) / 4)), radio, segRadio, false);
}
// Contorno de polígono a ras del piso (borde de un predio o de una zona) como cinta cerrada
export function contorno(pts, ancho = 1.2, h = 0.12) { return cinta([...pts, pts[0], pts[1]], ancho, h); }

// Punto dentro de polígono (par-impar)
export function dentro([x, y], poly) {
  let d = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d;
  }
  return d;
}
// distancia de un punto a una polilínea
export function distLinea(p, linea) {
  let d = Infinity;
  for (let i = 1; i < linea.length; i++) {
    const [a, b] = [linea[i - 1], linea[i]], dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
    d = Math.min(d, Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy));
  }
  return d;
}
export function area(poly) { let a = 0; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) a += (poly[j][0] + poly[i][0]) * (poly[j][1] - poly[i][1]); return Math.abs(a / 2); }
export function centro(poly) { const n = poly.length; return [poly.reduce((a, p) => a + p[0], 0) / n, poly.reduce((a, p) => a + p[1], 0) / n]; }
// Pseudoaleatorio reproducible: la maqueta sale igual en cada carga
export function azar(semilla = 1) { let s = semilla >>> 0 || 1; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
// Puntos al azar dentro de un polígono, separados al menos sep metros
export function sembrar(poly, n, sep = 4, semilla = 7) {
  const r = azar(semilla), xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)], out = [];
  for (let k = 0; k < n * 40 && out.length < n; k++) {
    const p = [x0 + r() * (x1 - x0), y0 + r() * (y1 - y0)];
    if (dentro(p, poly) && out.every((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) >= sep)) out.push(p);
  }
  return out;
}

// ---------------------------------------------------------------- materiales con nombre (se recolorean con el tema)
// La escena crea un juego y lo deja como predeterminado de las piezas (usarMateriales)
let MAT = null;
export function usarMateriales(M) { MAT = M; }
export function materiales(T) {
  const M = {
    verde: mat(new THREE.Color('#5f9a4a'), { roughness: 0.95 }), verdeOsc: mat(new THREE.Color('#3e7a3a'), { roughness: 0.95 }),
    grama: mat(new THREE.Color('#5aa34a'), { roughness: 0.9 }), arcilla: mat(new THREE.Color('#b8693b'), { roughness: 1 }),
    tronco: mat(new THREE.Color('#6b4a2f'), { roughness: 1 }), copa: mat(new THREE.Color('#ffffff'), { roughness: 0.9, flatShading: true }),
    concreto: mat(new THREE.Color('#c9c7c0'), { roughness: 0.9 }), adoquin: mat(new THREE.Color('#b3aa9c'), { roughness: 0.95 }),
    asfalto: mat(new THREE.Color('#5d6064'), { roughness: 0.95 }), muro: mat(T.wall, { roughness: 0.85 }),
    techo: mat(new THREE.Color('#8f9aa3'), { roughness: 0.55, metalness: 0.35 }), techoRojo: mat(new THREE.Color('#b9583d'), { roughness: 0.75 }),
    metal: mat(new THREE.Color('#9aa3ab'), { roughness: 0.4, metalness: 0.65 }), oscuro: mat(new THREE.Color('#2f3439'), { roughness: 0.6, metalness: 0.3 }),
    madera: mat(new THREE.Color('#a8744a'), { roughness: 0.8 }), roca: mat(new THREE.Color('#8b8a84'), { roughness: 1, flatShading: true }),
    membrana: mat(new THREE.Color('#f4f3ef'), { roughness: 0.6, side: THREE.DoubleSide }),
    agua: mat(T.water, { roughness: 0.15, metalness: 0.1, transparent: true, opacity: 0.92 }),
    aguaClara: mat(new THREE.Color('#4fa6c9'), { roughness: 0.1, metalness: 0.05 }),
    aguaTurbia: mat(new THREE.Color('#6d6a3b'), { roughness: 0.25 }),
    luz: new THREE.MeshBasicMaterial({ color: new THREE.Color('#fff4cf') }),
    vidrio: mat(new THREE.Color('#7fa7bd'), { roughness: 0.1, metalness: 0.4 }),
    solar: mat(new THREE.Color('#1d2c4a'), { roughness: 0.25, metalness: 0.5 }),
  };
  return M;
}
// Material de color de un módulo, con brillo propio leve para que se lea de lejos
export function matModulo(color, opts = {}) { return mat(new THREE.Color(color), { roughness: 0.6, emissive: new THREE.Color(color), emissiveIntensity: 0.12, ...opts }); }
// Material translúcido para zonas (sectores, áreas de intervención)
export function matZona(color, opacidad = 0.28) {
  return new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: opacidad, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
}

// ---------------------------------------------------------------- árboles y palmas instanciados
const geoTronco = new THREE.CylinderGeometry(0.16, 0.24, 1, 6).translate(0, 0.5, 0);
const geoCopa = new THREE.IcosahedronGeometry(1, 1).translate(0, 0, 0);
const geoPalmaTronco = new THREE.CylinderGeometry(0.14, 0.2, 1, 6).translate(0, 0.5, 0);
const geoPalmaHojas = (() => {
  const hojas = [];
  for (let i = 0; i < 7; i++) {
    const h = new THREE.ConeGeometry(0.35, 3.2, 3, 1).rotateZ(-Math.PI / 2 - 0.45).translate(1.5, -0.55, 0).rotateY((i / 7) * Math.PI * 2);
    hojas.push(h.toNonIndexed());
  }
  return mergeGeometries(hojas);
})();
const VERDES = ['#4f8f3f', '#5d9e45', '#3f7f39', '#6aa84f', '#477f35', '#7aa23f'].map((c) => new THREE.Color(c));

// puntos: [[x, y], …]; alto: metros (con ±25 % de variación); devuelve un grupo con troncos y copas instanciados
export function arboles(puntos, { alto = 8, copa = 0.42, semilla = 3, tronco } = {}) {
  const g = new THREE.Group(), n = puntos.length;
  if (!n) return g;
  const r = azar(semilla), M = tronco || arboles.mats || (arboles.mats = { tronco: mat(new THREE.Color('#6b4a2f'), { roughness: 1 }), copa: mat(new THREE.Color('#ffffff'), { roughness: 0.9, flatShading: true }) });
  const t = new THREE.InstancedMesh(geoTronco, M.tronco, n), c = new THREE.InstancedMesh(geoCopa, M.copa, n);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
  puntos.forEach(([x, y], i) => {
    const h = alto * (0.75 + r() * 0.5), rc = h * copa * (0.85 + r() * 0.3);
    m4.compose(V(x, y), q, new THREE.Vector3(1, h * 0.55, 1)); t.setMatrixAt(i, m4);
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), r() * 6.28);
    m4.compose(V(x, y, h * 0.55 + rc * 0.6), q, new THREE.Vector3(rc, rc * 0.82, rc)); c.setMatrixAt(i, m4); q.identity();
    c.setColorAt(i, VERDES[Math.floor(r() * VERDES.length)]);
  });
  [t, c].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); g.add(o); });
  g.userData.instancias = [t, c];
  return g;
}
export function palmas(puntos, { alto = 9, semilla = 5 } = {}) {
  const g = new THREE.Group(), n = puntos.length;
  if (!n) return g;
  const r = azar(semilla), M = palmas.mats || (palmas.mats = { tronco: mat(new THREE.Color('#8a7356'), { roughness: 1 }), hojas: mat(new THREE.Color('#5c9a3c'), { roughness: 0.9, flatShading: true, side: THREE.DoubleSide }) });
  const t = new THREE.InstancedMesh(geoPalmaTronco, M.tronco, n), h = new THREE.InstancedMesh(geoPalmaHojas, M.hojas, n);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
  puntos.forEach(([x, y], i) => {
    const a = alto * (0.8 + r() * 0.4);
    m4.compose(V(x, y), q, new THREE.Vector3(1, a, 1)); t.setMatrixAt(i, m4);
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), r() * 6.28);
    m4.compose(V(x, y, a), q, new THREE.Vector3(1, 1, 1)); h.setMatrixAt(i, m4); q.identity();
  });
  [t, h].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); g.add(o); });
  g.userData.instancias = [t, h];
  return g;
}

// ---------------------------------------------------------------- edificaciones simples
// Nave con cubierta a dos aguas (o en arco) centrada en (cx, cy), girada rot; w = luz, d = largo, h = altura de muro
export function nave(cx, cy, w, d, h, rot = 0, { techo = 'dosaguas', muro, cubierta, alero = 0.6 } = {}) {
  const g = new THREE.Group(), mm = muro || MAT.muro, mc = cubierta || MAT.techo;
  const caja = new THREE.Mesh(new THREE.BoxGeometry(w, h, d).translate(0, h / 2, 0), mm);
  let tg;
  if (techo === 'arco') {
    // medio cilindro con el eje a lo largo de la nave (z) y la bóveda hacia arriba
    tg = new THREE.CylinderGeometry(w / 2 + alero, w / 2 + alero, d + alero * 2, 20, 1, true, -Math.PI / 2, Math.PI).rotateX(-Math.PI / 2);
    tg.scale(1, 0.45, 1); tg.translate(0, h, 0);
  } else if (techo === 'plano') {
    tg = new THREE.BoxGeometry(w + alero, 0.35, d + alero).translate(0, h + 0.17, 0);
  } else {
    const p = (w / 2 + alero) * 0.36, s = new THREE.Shape([new THREE.Vector2(-w / 2 - alero, 0), new THREE.Vector2(w / 2 + alero, 0), new THREE.Vector2(0, p)]);
    tg = new THREE.ExtrudeGeometry(s, { depth: d + alero * 2, bevelEnabled: false }).translate(0, 0, -(d + alero * 2) / 2).translate(0, h, 0);
  }
  const techoM = new THREE.Mesh(tg, mc);
  [caja, techoM].forEach((o) => { o.castShadow = true; o.receiveShadow = true; g.add(o); });
  g.position.copy(V(cx, cy)); g.rotation.y = rot;
  return g;
}
// Silo cilíndrico con techo cónico
export function silo(x, y, r, h, m) {
  const g = new THREE.Group(), mm = m || MAT.metal;
  const c = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 20).translate(0, h / 2, 0), mm);
  const t = new THREE.Mesh(new THREE.ConeGeometry(r * 1.04, r * 0.7, 20).translate(0, h + r * 0.35, 0), mm);
  const p = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.75, r * 0.9, 1.6, 16).translate(0, 0.8, 0), MAT.concreto || mm);
  [c, t, p].forEach((o) => { o.castShadow = true; o.receiveShadow = true; g.add(o); });
  g.position.copy(V(x, y));
  return g;
}
// Tanque cilíndrico bajo (reactores, clarificadores, tanques de agua) con borde
export function tanque(x, y, r, h, { m, agua, borde = 0.35 } = {}) {
  const g = new THREE.Group(), mm = m || MAT.concreto;
  const c = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 32, 1, true).translate(0, h / 2, 0), mm);
  c.material = mm.clone(); c.material.side = THREE.DoubleSide;
  const b = new THREE.Mesh(new THREE.TorusGeometry(r, borde / 2, 6, 40).rotateX(Math.PI / 2).translate(0, h, 0), mm);
  g.add(c, b);
  if (agua) { const w = new THREE.Mesh(new THREE.CircleGeometry(r * 0.98, 32).rotateX(-Math.PI / 2).translate(0, h - 0.4, 0), agua); w.receiveShadow = true; g.add(w); }
  const f = new THREE.Mesh(new THREE.CircleGeometry(r, 32).rotateX(-Math.PI / 2).translate(0, 0.05, 0), mm); g.add(f);
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  g.position.copy(V(x, y));
  return g;
}
// Cúpula (biodigestor, reactor cubierto)
export function domo(x, y, r, m) {
  const o = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.7, 1), m || MAT.membrana);
  o.castShadow = true; o.receiveShadow = true; o.position.copy(V(x, y));
  return o;
}
// Graderías escalonadas: w de frente, filas de 0,8 m de huella y 0,42 m de contrahuella; mira hacia rot
export function graderia(cx, cy, w, filas, rot = 0, m) {
  const g = new THREE.Group(), geos = [];
  for (let i = 0; i < filas; i++) geos.push(new THREE.BoxGeometry(w, 0.42 * (i + 1), 0.8).translate(0, 0.21 * (i + 1), -0.4 - i * 0.8));
  const o = new THREE.Mesh(mergeGeometries(geos), m || MAT.concreto);
  o.castShadow = true; o.receiveShadow = true; g.add(o);
  g.position.copy(V(cx, cy)); g.rotation.y = rot;
  return g;
}
// Cubierta tensada (paraboloide hiperbólico) de w × d sobre cuatro mástiles; alto h en dos esquinas y h − flecha en las otras
export function membrana(cx, cy, w, d, h, rot = 0, { flecha = 1.6, m, mastil } = {}) {
  const g = new THREE.Group(), geo = new THREE.PlaneGeometry(w, d, 18, 12), p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) { const u = p.getX(i) / (w / 2), v = p.getY(i) / (d / 2); p.setZ(i, (u * v) * flecha * 0.5 + (1 - u * u) * 0.25 * flecha); }
  geo.computeVertexNormals(); geo.rotateX(-Math.PI / 2); geo.translate(0, h, 0);
  const s = new THREE.Mesh(geo, m || MAT.membrana); s.castShadow = true; s.receiveShadow = true; g.add(s);
  const mg = new THREE.CylinderGeometry(0.12, 0.16, 1, 8).translate(0, 0.5, 0), mm = mastil || MAT.metal;
  [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => { const hh = h + a * b * flecha * 0.5 + 0.3; const o = new THREE.Mesh(mg, mm); o.scale.y = hh; o.position.set(a * w / 2, 0, b * d / 2); o.castShadow = true; g.add(o); });
  g.position.copy(V(cx, cy)); g.rotation.y = rot;
  return g;
}
// Torres de iluminación deportiva LED con cabezal emisivo
export function torresLuz(puntos, h = 18, { m, luz } = {}) {
  const g = new THREE.Group(), n = puntos.length;
  if (!n) return g;
  const pg = new THREE.CylinderGeometry(0.18, 0.3, h, 8).translate(0, h / 2, 0), cg = new THREE.BoxGeometry(2.6, 1.4, 0.4).translate(0, h + 0.5, 0);
  const lg = new THREE.PlaneGeometry(2.3, 1.1).translate(0, h + 0.5, 0.21);
  const P = new THREE.InstancedMesh(pg, m || MAT.metal, n), C = new THREE.InstancedMesh(cg, MAT.oscuro || m, n), L = new THREE.InstancedMesh(lg, luz || MAT.luz, n);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  puntos.forEach(([x, y, haciaX, haciaY], i) => {
    const ang = haciaX != null ? Math.atan2(haciaX - x, -(haciaY - y)) : 0;
    q.setFromEuler(e.set(-0.35, ang, 0, 'YXZ')); m4.compose(V(x, y), new THREE.Quaternion(), new THREE.Vector3(1, 1, 1)); P.setMatrixAt(i, m4);
    const qh = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), ang);
    m4.compose(V(x, y), qh, new THREE.Vector3(1, 1, 1)); C.setMatrixAt(i, m4); L.setMatrixAt(i, m4);
  });
  [P, C].forEach((o) => { o.castShadow = true; o.computeBoundingSphere(); g.add(o); });
  L.computeBoundingSphere(); g.add(L);
  return g;
}
// Postes de luz peatonal a lo largo de una polilínea
export function postes(puntos, h = 4.5, m) {
  const n = puntos.length, g = new THREE.Group();
  if (!n) return g;
  const pg = new THREE.CylinderGeometry(0.06, 0.08, h, 6).translate(0, h / 2, 0), lg = new THREE.SphereGeometry(0.22, 10, 8).translate(0, h, 0);
  const P = new THREE.InstancedMesh(pg, m || MAT.oscuro, n), L = new THREE.InstancedMesh(lg, MAT.luz, n), m4 = new THREE.Matrix4();
  puntos.forEach(([x, y], i) => { m4.makeTranslation(x, 0, -y); P.setMatrixAt(i, m4); L.setMatrixAt(i, m4); });
  P.computeBoundingSphere(); L.computeBoundingSphere(); g.add(P, L);
  return g;
}
// Baranda a lo largo de una polilínea a la altura h0 (pasamanos y parales cada 2 m)
export function baranda(pts, h0 = 0, { alto = 1.05, m } = {}) {
  const g = new THREE.Group(), mm = m || MAT.oscuro;
  const pas = new THREE.Mesh(cinta(pts, 0.08, h0 + alto), mm); g.add(pas);
  const ps = aLoLargo(pts, 2), pg = new THREE.BoxGeometry(0.05, alto, 0.05).translate(0, alto / 2, 0);
  const P = new THREE.InstancedMesh(pg, mm, ps.length), m4 = new THREE.Matrix4();
  ps.forEach(([x, y], i) => { m4.makeTranslation(x, h0, -y); P.setMatrixAt(i, m4); });
  P.computeBoundingSphere(); g.add(P);
  return g;
}
// Enrocado: bloques de roca instanciados en una franja (protección de orilla)
export function enrocado(poly, n = 400, { tam = 1.4, alto = 0.6, semilla = 11, m } = {}) {
  const pts = sembrar(poly, n, tam * 0.7, semilla), r = azar(semilla + 1);
  const im = new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1, 0), m || MAT.roca, pts.length), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  pts.forEach(([x, y], i) => {
    const s = tam * (0.6 + r() * 0.7); q.setFromEuler(e.set(r() * 3, r() * 3, r() * 3));
    m4.compose(V(x, y, alto * r()), q, new THREE.Vector3(s, s * 0.7, s)); im.setMatrixAt(i, m4);
  });
  im.castShadow = true; im.receiveShadow = true; im.computeBoundingSphere();
  return im;
}

// ---------------------------------------------------------------- casas en serie (vivienda nueva) instanciadas
// lotes: [{ x, y, rot, pisos }] → muros y cubiertas a dos aguas, con colores de fachada variados
const FACHADAS = ['#f3efe6', '#f6e7c8', '#e9f0f2', '#f4dcd2', '#e6efe0', '#f1e4ef'].map((c) => new THREE.Color(c));
export function casas(lotes, { frente = 6, fondo = 9, alto = 2.7, semilla = 9 } = {}) {
  const g = new THREE.Group(), n = lotes.length;
  if (!n) return g;
  const r = azar(semilla);
  const mg = new THREE.BoxGeometry(frente - 0.3, 1, fondo).translate(0, 0.5, 0);
  const s = new THREE.Shape([new THREE.Vector2(-frente / 2, 0), new THREE.Vector2(frente / 2, 0), new THREE.Vector2(0, 1.5)]);
  const tg = new THREE.ExtrudeGeometry(s, { depth: fondo + 0.6, bevelEnabled: false }).translate(0, 0, -(fondo + 0.6) / 2);
  const M = casas.mats || (casas.mats = { muro: mat(new THREE.Color('#ffffff'), { roughness: 0.9 }), techo: mat(new THREE.Color('#b65a3c'), { roughness: 0.8 }) });
  const W = new THREE.InstancedMesh(mg, M.muro, n), R = new THREE.InstancedMesh(tg, M.techo, n), m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
  lotes.forEach((l, i) => {
    const h = alto * (l.pisos || 1);
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), l.rot || 0);
    m4.compose(V(l.x, l.y), q, new THREE.Vector3(1, h, 1)); W.setMatrixAt(i, m4);
    m4.compose(V(l.x, l.y, h), q, new THREE.Vector3(1, 1, 1)); R.setMatrixAt(i, m4);
    W.setColorAt(i, FACHADAS[Math.floor(r() * FACHADAS.length)]);
  });
  [W, R].forEach((o) => { o.castShadow = true; o.receiveShadow = true; o.computeBoundingSphere(); g.add(o); });
  g.userData.instancias = [W, R];
  return g;
}

// ---------------------------------------------------------------- letras 3D
let fuente = null;
export async function letras(texto, { alto = 2.2, fondo = 0.6, colores = ['#e3141b'], acento = -1, separacion = 0.25 } = {}) {
  const [{ FontLoader }, { TextGeometry }] = await Promise.all([import('three/addons/loaders/FontLoader.js'), import('three/addons/geometries/TextGeometry.js')]);
  fuente = fuente || await new FontLoader().loadAsync('https://cdn.jsdelivr.net/npm/three@0.160.0/examples/fonts/helvetiker_bold.typeface.json');
  const g = new THREE.Group();
  let x = 0;
  [...texto].forEach((ch, i) => {
    const geo = new TextGeometry(ch, { font: fuente, size: alto, height: fondo, curveSegments: 6, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.04, bevelSegments: 2 });
    geo.computeBoundingBox();
    const bb = geo.boundingBox, w = bb.max.x - bb.min.x;
    const m = mat(new THREE.Color(colores[i % colores.length]), { roughness: 0.45, emissive: new THREE.Color(colores[i % colores.length]), emissiveIntensity: 0.25 });
    const o = new THREE.Mesh(geo, m); o.position.x = x - bb.min.x; o.castShadow = true; g.add(o);
    if (i === acento) { // tilde: la fuente no trae «Ó»
      const t = new THREE.Mesh(new THREE.BoxGeometry(w * 0.32, alto * 0.13, fondo).rotateZ(0.6), m);
      t.position.set(x + w * 0.62, alto * 1.16, fondo / 2); t.castShadow = true; g.add(t);
    }
    x += w + separacion;
  });
  g.children.forEach((o) => { o.position.x -= x / 2; });
  return g;
}

// ---------------------------------------------------------------- animaciones (GSAP; sin GSAP saltan al final)
// Crece un objeto desde el piso (escala vertical)
export function crecer(obj, { duracion = 0.9, retraso = 0, tl, alFinal, onUpdate } = {}) {
  if (!gsap) { obj.scale.y = 1; alFinal?.(); return; }
  const tw = { y: 0.001 };
  const fn = () => { obj.scale.y = tw.y; onUpdate?.(); };
  const anim = gsap.fromTo(tw, { y: 0.001 }, { y: 1, duration: duracion, delay: tl ? 0 : retraso, ease: 'back.out(1.4)', onUpdate: fn, onComplete: alFinal });
  if (tl) tl.add(anim, retraso);
  return anim;
}
// Hace aparecer las instancias de un grupo una tras otra (casas, árboles) desde el piso
export function brotar(grupo, { duracion = 1.6, tl, retraso = 0, onUpdate, alFinal } = {}) {
  const ims = grupo.userData.instancias || [];
  if (!ims.length) return null;
  ims.forEach((im) => { if (!im.userData.base) { im.userData.base = []; const m4 = new THREE.Matrix4(); for (let i = 0; i < im.count; i++) { im.getMatrixAt(i, m4); im.userData.base.push(m4.clone()); } } });
  const n = ims[0].count, p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3(), m4 = new THREE.Matrix4();
  const aplicar = (u) => {
    ims.forEach((im) => {
      for (let i = 0; i < im.count; i++) {
        const k = THREE.MathUtils.clamp(u * (1 + 0.6) - (i / Math.max(1, n - 1)) * 0.6, 0, 1), e = k < 1 ? 1 - Math.pow(1 - k, 3) : 1;
        im.userData.base[i].decompose(p, q, s);
        if (im === ims[0]) { s.y *= Math.max(0.001, e); } else { p.y *= Math.max(0.001, e); s.multiplyScalar(Math.max(0.001, e)); }
        m4.compose(p, q, s); im.setMatrixAt(i, m4);
      }
      im.instanceMatrix.needsUpdate = true;
    });
    onUpdate?.();
  };
  if (!gsap) { aplicar(1); alFinal?.(); return null; }
  const o = { u: 0 };
  aplicar(0);
  const anim = gsap.to(o, { u: 1, duration: duracion, ease: 'none', delay: tl ? 0 : retraso, onUpdate: () => aplicar(o.u), onComplete: alFinal });
  if (tl) tl.add(anim, retraso);
  return anim;
}
// Dibuja de a poco una geometría indexada o no (tubos, cintas): drawRange de 0 al total
export function revelar(mesh, { duracion = 1.4, tl, retraso = 0, onUpdate } = {}) {
  const g = mesh.geometry, total = g.index ? g.index.count : g.attributes.position.count;
  if (!gsap) { g.setDrawRange(0, Infinity); return null; }
  const o = { u: 0 };
  g.setDrawRange(0, 0);
  const anim = gsap.to(o, { u: 1, duration: duracion, ease: 'power2.inOut', delay: tl ? 0 : retraso, onUpdate: () => { g.setDrawRange(0, Math.floor((total * o.u) / 6) * 6); onUpdate?.(); }, onComplete: () => g.setDrawRange(0, Infinity) });
  if (tl) tl.add(anim, retraso);
  return anim;
}
