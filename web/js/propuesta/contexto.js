// Contexto urbano y rural de la maqueta: las casas del pueblo a partir de las huellas abiertas y los árboles de los patios,
// las rondas de los caños y las orillas del río.
// · Casas: cada huella se mide con su rectángulo mínimo. Las rectangulares de hasta 15 m de fondo llevan cubierta a dos
//   aguas (zinc pintado u oxidado, o teja de barro) con aleros y culatas; las demás, losa con pretil y, a veces, tanque.
//   Los muros llevan una fachada con puerta, ventanas con reja y zócalo en el lado que da a la calle, y ventanas pequeñas en
//   los otros (texFachada, en UV de metros), teñida con el color de cada casa; de noche brillan los vidrios.
// · Árboles: en los patios y solares del casco (lejos de muros, calles y agua), a lo largo de los caños y en las orillas del
//   río, más algunos sueltos en los potreros. Nunca dentro de un sitio del proyecto (geo.json), de una zona de intervención
//   ni de una sede. Van en mallas instanciadas por trozos del territorio para que la cámara y la sombra descarten lo que no ven.
import { THREE } from '../core.js';
import { dentro, azar, distLinea } from './geo3d.js';
import { FACHADA } from './texturas.js';

// ---------------------------------------------------------------- rejilla espacial
export class Rejilla {
  constructor(celda) { this.c = celda; this.m = new Map(); }
  _k(i, j) { return i * 73856093 ^ j * 19349663; }
  agregar(obj, x0, y0, x1, y1) {
    const c = this.c;
    for (let i = Math.floor(x0 / c); i <= Math.floor(x1 / c); i++) for (let j = Math.floor(y0 / c); j <= Math.floor(y1 / c); j++) {
      const k = this._k(i, j); let l = this.m.get(k); if (!l) this.m.set(k, (l = [])); l.push(obj);
    }
  }
  en(x, y) { return this.m.get(this._k(Math.floor(x / this.c), Math.floor(y / this.c))) || []; }
}
function distSeg(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}
// líneas con ancho (calles, caños): ¿el punto está a menos de ancho/2 + extra de alguna?
export function rejillaLineas(lineas, celda = 40) {
  const R = new Rejilla(celda);
  lineas.forEach((l) => {
    const w = (l.ancho || 4) / 2;
    for (let i = 1; i < l.p.length; i++) {
      const [a, b] = [l.p[i - 1], l.p[i]], m = w + 8;
      R.agregar({ a, b, w }, Math.min(a[0], b[0]) - m, Math.min(a[1], b[1]) - m, Math.max(a[0], b[0]) + m, Math.max(a[1], b[1]) + m);
    }
  });
  R.cerca = (x, y, extra = 0) => R.en(x, y).some((s) => distSeg(x, y, s.a[0], s.a[1], s.b[0], s.b[1]) < s.w + extra);
  return R;
}
// Punto en polígono rápido para polígonos grandes (el río tiene 321 vértices): las aristas se reparten en franjas
// horizontales de `banda` metros y el rayo solo cruza las de la franja del punto
export function poligonoRapido(poly, banda = 60) {
  const franjas = new Map();
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [a, b] = [poly[j], poly[i]], y0 = Math.floor(Math.min(a[1], b[1]) / banda), y1 = Math.floor(Math.max(a[1], b[1]) / banda);
    for (let k = y0; k <= y1; k++) { if (!franjas.has(k)) franjas.set(k, []); franjas.get(k).push([a, b]); }
  }
  return ([x, y]) => {
    let d = false;
    for (const [[xj, yj], [xi, yi]] of franjas.get(Math.floor(y / banda)) || []) if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) d = !d;
    return d;
  };
}
// polígonos: ¿el punto está dentro o a menos de m metros?
export function rejillaPoligonos(polys, celda = 60, margen = 0) {
  const R = new Rejilla(celda);
  polys.forEach((p) => {
    const xs = p.map((q) => q[0]), ys = p.map((q) => q[1]);
    R.agregar(p, Math.min(...xs) - margen, Math.min(...ys) - margen, Math.max(...xs) + margen, Math.max(...ys) + margen);
  });
  const anillos = new Map(polys.map((p) => [p, [...p, p[0]]]));
  R.toca = (x, y, m = margen) => R.en(x, y).some((p) => dentro([x, y], p) || (m > 0 && distLinea([x, y], anillos.get(p)) < m));
  return R;
}

// ---------------------------------------------------------------- casas
const FACH = ['#f5f2ea', '#f6e6c2', '#e3eef3', '#f4dbca', '#e2eedb', '#efe1ec', '#f7f0d0', '#dce6f1', '#f2e1cd', '#d6ece7', '#f6d8a4', '#cde3ea', '#f1f1f1', '#ffffff'].map((c) => new THREE.Color(c));
const ZINC = ['#aab1b5', '#9ba3a8', '#b9bec0', '#90989c', '#a77a60', '#8f6650', '#9b4134', '#52708e', '#5a7d60', '#b6bab2'].map((c) => new THREE.Color(c));
const TEJA = ['#ffffff', '#f3e9de', '#e5d6c6', '#f8efe8'].map((c) => new THREE.Color(c));
const LOSA = ['#cbc8c1', '#bebbb4', '#d6d3cb', '#b8b6b0'].map((c) => new THREE.Color(c));
const TANQUE = ['#1f2326', '#1f2326', '#2c4f7a', '#8f9599'].map((c) => new THREE.Color(c));

// rectángulo de área mínima (calibres sobre las aristas): centro, ejes y semilados (a ≥ b)
function rectMin(pts) {
  let best = null;
  for (let i = 0; i < pts.length; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) % pts.length], L = Math.hypot(bx - ax, by - ay);
    if (L < 0.4) continue;
    const ux = (bx - ax) / L, uy = (by - ay) / L;
    let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
    for (const [x, y] of pts) { const u = x * ux + y * uy, v = -x * uy + y * ux; u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
    const A = (u1 - u0) * (v1 - v0);
    if (!best || A < best.A) best = { A, ux, uy, u0, u1, v0, v1 };
  }
  const { ux, uy, u0, u1, v0, v1, A } = best, cu = (u0 + u1) / 2, cv = (v0 + v1) / 2;
  let a = (u1 - u0) / 2, b = (v1 - v0) / 2, ex = [ux, uy], ey = [-uy, ux];
  if (b > a) { [a, b] = [b, a]; [ex, ey] = [ey, [-ex[0], -ex[1]]]; }
  return { c: [cu * ux - cv * uy, cu * uy + cv * ux], a, b, ex, ey, A };
}

// Búferes de una tanda de casas (las del pueblo o las de una zona de intervención)
function bufer() { return { muro: { p: [], u: [], c: [] }, zinc: { p: [], u: [], c: [] }, teja: { p: [], u: [], c: [] }, losa: { p: [], c: [] } }; }
const P3 = (x, y, h) => [x, h, -y];
function tri(b, a, c2, d, col, uv) {
  b.p.push(...a, ...c2, ...d);
  for (let k = 0; k < 3; k++) b.c.push(col.r, col.g, col.b);
  if (uv && b.u) b.u.push(...uv);
}
function quad(b, a, c2, d, e, col, uv) { tri(b, a, c2, d, col, uv && [uv[0], uv[1], uv[2], uv[3], uv[4], uv[5]]); tri(b, a, d, e, col, uv && [uv[0], uv[1], uv[4], uv[5], uv[6], uv[7]]); }

/**
 * Casas a partir de las huellas. calles: rejillaLineas de las calles (para saber qué muro da a la calle); zonaDe([x, y]):
 * id de la zona de intervención o null; saltar([x, y], semilados): true si la huella no va (sedes del atlas).
 * Devuelve { tandas: Map(id|null → búfer), huellas: [{ pts, cx, cy, area, h, zona, techo, tope }], tanques: [[x, y, h, r, color]] }
 */
export function casasDeHuellas(poligonos, { calles, zonaDe, saltar }) {
  const tandas = new Map(), huellas = [], tanques = [];
  const W = FACHADA.ancho, HT = FACHADA.alto;
  poligonos.forEach((flat, k) => {
    const pts = []; for (let i = 0; i < flat.length; i += 2) pts.push([flat[i], flat[i + 1]]);
    if (pts.length < 3) return;
    const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length, cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
    let sa = 0; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) sa += (pts[j][0] - pts[i][0]) * (pts[j][1] + pts[i][1]);
    const area = Math.abs(sa / 2), ccw = sa < 0;
    if (saltar?.([cx, cy])) return;
    const h = 2.9 + (area > 160 ? 2.6 : 0) + ((k * 2654435761) % 5) * 0.25;
    const zona = zonaDe([cx, cy]);
    if (!tandas.has(zona)) tandas.set(zona, bufer());
    const B = tandas.get(zona), hash = (k * 2246822519) >>> 0, r = azar(hash + 1);
    const cf = FACH[hash % FACH.length], R = rectMin(pts), relleno = area / R.A;
    const dosAguas = relleno > 0.8 && R.b * 2 <= 15 && area < 420 && hash % 100 < 80;
    const deTeja = dosAguas && hash % 100 < 30, tanP = deTeja ? 0.46 : 0.3;
    const sube = dosAguas ? R.b * tanP : 0, pretil = dosAguas ? 0 : 0.55;
    // muros: cada arista con la fachada de la calle o la lateral, centrada en su largo
    for (let i = 0; i < pts.length; i++) {
      const [ax, ay] = pts[i], [bx, by] = pts[(i + 1) % pts.length], L = Math.hypot(bx - ax, by - ay);
      if (L < 0.05) continue;
      const nx = (ccw ? by - ay : ay - by) / L, ny = (ccw ? ax - bx : bx - ax) / L;
      const calle = calles.cerca((ax + bx) / 2 + nx * 4.5, (ay + by) / 2 + ny * 4.5, 2.5);
      const vb = calle ? 0 : FACHADA.lateral, top = h + pretil;
      let u0, u1;
      if (L < 2.4) { u0 = FACHADA.liso[0]; u1 = u0 + Math.min(L, 0.9); } else { u0 = W / 2 - L / 2; u1 = W / 2 + L / 2; }
      quad(B.muro, P3(ax, ay, 0), P3(bx, by, 0), P3(bx, by, top), P3(ax, ay, top), cf,
        [u0 / W, vb / HT, u1 / W, vb / HT, u1 / W, (vb + top) / HT, u0 / W, (vb + top) / HT]);
    }
    const techo = [];
    const add = (b, a, c2, d, col, uv) => { tri(b, a, c2, d, col, uv); techo.push(a[0], a[1] + 0.12, a[2], c2[0], c2[1] + 0.12, c2[2], d[0], d[1] + 0.12, d[2]); };
    if (dosAguas) {
      const { c, a, b, ex, ey } = R, e = 0.5, eg = 0.35, hE = h - e * tanP, hR = h + sube;
      const at = (s, t, z) => P3(c[0] + s * ex[0] + t * ey[0], c[1] + s * ex[1] + t * ey[1], z);
      const buf = deTeja ? B.teja : B.zinc, col = deTeja ? TEJA[hash % TEJA.length] : ZINC[(hash >>> 3) % ZINC.length];
      const esc = deTeja ? 0.5 : 1, lv = (b + e) * Math.sqrt(1 + tanP * tanP) * esc, s0 = -(a + eg), s1 = a + eg;
      [-1, 1].forEach((lado) => {
        const p0 = at(s0, lado * (b + e), hE), p1 = at(s1, lado * (b + e), hE), p2 = at(s1, 0, hR + 0.03), p3 = at(s0, 0, hR + 0.03);
        add(buf, p0, p1, p2, col, [s0 * esc, 0, s1 * esc, 0, s1 * esc, lv]); add(buf, p0, p2, p3, col, [s0 * esc, 0, s1 * esc, lv, s0 * esc, lv]);
        // culata: triángulo de muro sobre el lado corto (textura lisa de la banda lateral)
        tri(B.muro, at(lado * a, -b, h), at(lado * a, b, h), at(lado * a, 0, hR), cf, [5 / W, (6 + h) / HT, 5.95 / W, (6 + h) / HT, 5.5 / W, (6 + hR) / HT]);
      });
    } else {
      const col = LOSA[hash % LOSA.length];
      THREE.ShapeUtils.triangulateShape(pts.map(([x, y]) => new THREE.Vector2(x, y)), []).forEach(([i, j, l]) => add(B.losa, P3(...pts[i], h + 0.04), P3(...pts[j], h + 0.04), P3(...pts[l], h + 0.04), col));
      if (!zona && hash % 100 < 45 && area > 30) {
        const rr = 0.5 + r() * 0.25, ang = r() * 6.28, d = Math.min(R.b * 0.5, 2);
        const px = cx + Math.cos(ang) * d, py = cy + Math.sin(ang) * d;
        if (dentro([px, py], pts)) tanques.push([px, py, h + 0.04, rr, TANQUE[hash % TANQUE.length]]);
      }
    }
    huellas.push({ pts, cx, cy, area, h, zona, techo: new Float32Array(techo), tope: h + Math.max(sube, pretil) });
  });
  return { tandas, huellas, tanques };
}
/** Geometrías de un búfer de casas: { muro, zinc, teja, losa } (las vacías, null). */
export function geometrias(B) {
  const out = {};
  for (const [k, b] of Object.entries(B)) {
    if (!b.p.length) { out[k] = null; continue; }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(b.p, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(b.c, 3));
    if (b.u?.length) g.setAttribute('uv', new THREE.Float32BufferAttribute(b.u, 2));
    g.computeVertexNormals(); g.computeBoundingSphere();
    out[k] = g;
  }
  return out;
}

// ---------------------------------------------------------------- árboles
/**
 * Puntos para árboles: { pueblo: [[x, y]], palmas: [[x, y]], rondas: [[x, y]], potrero: [[x, y]] }.
 * huellas: las de casasDeHuellas; calles, canos: rejillaLineas; agua: rejillaPoligonos de ciénagas; rio: { poligono, islas };
 * excluir: rejillaPoligonos de sitios y zonas; cajas: [[x, y, semiancho, semifondo]] de las sedes; canosLineas: los caños.
 */
export async function sembrarArboles({ huellas, calles, canos, canosLineas, agua, rio, excluir, cajas, semilla = 77, pausa = async () => {} }) {
  const r = azar(semilla), pueblo = [], palmasP = [], rondas = [], potrero = [];
  const H = new Rejilla(14), ocupado = new Set(), C = 45, kc = (x, y) => `${Math.floor(x / C)},${Math.floor(y / C)}`;
  let X0 = Infinity, X1 = -Infinity, Y0 = Infinity, Y1 = -Infinity;
  huellas.forEach((h) => {
    const xs = h.pts.map((p) => p[0]), ys = h.pts.map((p) => p[1]);
    const b = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    H.agregar(h, b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2); ocupado.add(kc(h.cx, h.cy));
    X0 = Math.min(X0, b[0]); X1 = Math.max(X1, b[2]); Y0 = Math.min(Y0, b[1]); Y1 = Math.max(Y1, b[3]);
  });
  const enPueblo = (x, y) => { const i = Math.floor(x / C), j = Math.floor(y / C); for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) if (ocupado.has(`${i + a},${j + b}`)) return true; return false; };
  const enRioP = rio?.poligono ? poligonoRapido(rio.poligono) : () => false, islas = (rio?.islas || []).map((i) => poligonoRapido(i, 40));
  const enRio = (x, y) => enRioP([x, y]) && !islas.some((f) => f([x, y]));
  const anillo = new Map(huellas.map((h) => [h, [...h.pts, h.pts[0]]]));
  const libre = (x, y, dCasa = 1.6) => {
    if (H.en(x, y).some((h) => dentro([x, y], h.pts) || distLinea([x, y], anillo.get(h)) < dCasa)) return false;
    if (calles.cerca(x, y, 1.4) || canos.cerca(x, y, 1.8) || agua.toca(x, y) || excluir.toca(x, y)) return false;
    if (cajas.some(([bx, by, hx, hy]) => Math.abs(x - bx) < hx + 4 && Math.abs(y - by) < hy + 4)) return false;
    return !enRio(x, y);
  };
  // patios y solares del casco: una rejilla de 7 m con desorden; uno de cada cuatro sitios libres lleva árbol
  let col = 0;
  if (huellas.length) for (let x = X0; x <= X1; x += 7) {
    for (let y = Y0; y <= Y1; y += 7) {
      const px = x + (r() - 0.5) * 6, py = y + (r() - 0.5) * 6;
      if (r() > 0.27 || !enPueblo(px, py) || !libre(px, py)) continue;
      (r() < 0.22 ? palmasP : pueblo).push([px, py]);
    }
    if (++col % 60 === 0) await pausa();   // cede el hilo cada 420 m de pueblo
  }
  await pausa();
  // rondas de los caños: árboles a los dos lados, más tupidos fuera del casco
  canosLineas.forEach((l) => {
    for (let i = 1; i < l.p.length; i++) {
      const [a, b] = [l.p[i - 1], l.p[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / (L || 1), uy = (b[1] - a[1]) / (L || 1);
      for (let s = r() * 9; s < L; s += 9) [-1, 1].forEach((lado) => {
        const off = (l.ancho || 3) / 2 + 3 + r() * 12, px = a[0] + ux * s - uy * off * lado, py = a[1] + uy * s + ux * off * lado;
        if (r() < (enPueblo(px, py) ? 0.25 : 0.7) && libre(px, py, 3)) rondas.push([px, py]);
      });
    }
  });
  await pausa();
  // orillas del río: franja de bosque de galería del lado de tierra
  const pr = rio?.poligono || [];
  for (let i = 1; i < pr.length; i++) {
    const [a, b] = [pr[i - 1], pr[i]], L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / (L || 1), uy = (b[1] - a[1]) / (L || 1);
    for (let s = r() * 14; s < L; s += 14) [-1, 1].forEach((lado) => {
      const off = 6 + r() * 30, px = a[0] + ux * s - uy * off * lado, py = a[1] + uy * s + ux * off * lado;
      if (Math.hypot(px, py) < 9000 && r() < 0.75 && libre(px, py, 3)) rondas.push([px, py]);
    });
  }
  await pausa();
  // potreros: árboles sueltos y algunos bosquecitos en 7 km a la redonda, fuera del casco
  for (let k = 0; k < 2600; k++) {
    const ang = r() * 6.283, d = 900 + Math.sqrt(r()) * 6200, px = Math.cos(ang) * d, py = Math.sin(ang) * d;
    const n = r() < 0.15 ? 6 : 1;
    for (let j = 0; j < n; j++) { const qx = px + (r() - 0.5) * 50 * (n > 1), qy = py + (r() - 0.5) * 50 * (n > 1); if (!enPueblo(qx, qy) && libre(qx, qy, 4)) potrero.push([qx, qy]); }
  }
  return { pueblo, palmas: palmasP, rondas, potrero };
}
/** Reparte puntos en trozos cuadrados de lado `lado` (para que cada malla instanciada se descarte por su cuenta). */
export function trozos(puntos, lado) {
  const m = new Map();
  puntos.forEach((p) => { const k = `${Math.floor(p[0] / lado)},${Math.floor(p[1] / lado)}`; if (!m.has(k)) m.set(k, []); m.get(k).push(p); });
  return [...m.values()];
}
