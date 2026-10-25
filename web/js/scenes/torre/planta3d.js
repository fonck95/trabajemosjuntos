// Geometría 3D de un nivel de la torre desde web/data/torre_plantas.json y su rejilla de colisión (equipo C; especificación
// de integración, 6.1 a 6.4 y 16.1). La usa el recorrido en primera persona y la puede reutilizar D en «Pisos por servicio».
//
// Todo se arma en coordenadas de planta (x al este, y al norte, z arriba, metros) y pasa a three como (X, Y, Z) = (x, z, −y),
// que es una rotación propia: los triángulos que giran en sentido antihorario vistos desde afuera en planta siguen
// siéndolo en three. La geometría es local al nivel (z = 0 es su piso terminado) y el grupo va a la cota del nivel
// (grupo.position.y = nivel.z); quien la reutilice puede moverlo.
//
// Llamadas de dibujo: cuatro mallas fundidas con colores por vértice (muros, puertas, escaleras y señales; pisos; cielo;
// vidrios y mallas del cerramiento), dentro del presupuesto del 5.2 (≤ 8 de la planta).
import { THREE, onTheme, tokens } from '../../core.js';

// ---------------------------------------------------------------- colores (estimación de materiales, sin texturas)
const HEX = {
  panete: '#f0eee8', ladrillo: '#b5562f', concreto: '#bcb8af', plomado: '#d5dade', parapeto: '#c8c4bb', cerramiento: '#7e847a',
  cielo: '#f6f5f1', losa: '#c7c3bb', borde_losa: '#a9a59c', puerta: '#d2c19c', cortafuego: '#9e4336', puerta_plomo: '#8d98a1',
  marco: '#8a8d91', escalon: '#cbc7be', baranda: '#5f6469', vidrio: '#9fc3d6', malla: '#3f5a46', cabina: '#9ea4aa',
  piso_bano: '#dfe9ec', piso_tecnico: '#c4c1ba', asfalto: '#6f7173', adoquin: '#b8ad9b', verde: '#86a872', tronco: '#6b4a32',
  copa: '#4d8a46', cubierta: '#c3c1ba', huella: '#d9d6cf', senal_texto: '#ffffff',
};
const C = Object.fromEntries(Object.entries(HEX).map(([k, v]) => [k, new THREE.Color(v)]));
const BLANCO = new THREE.Color(1, 1, 1);
// tono suave del color de señalización del grupo para el piso (Res. 1633, Cuadros 2 y 3, en grupos_1633)
function tonoPiso(hex, k = 0.58) { return new THREE.Color(hex || '#9aa0a6').lerp(BLANCO, k); }

// ---------------------------------------------------------------- utilidades de geometría en planta
const EPS = 1e-6;
export function enPoligono(x, y, pol) {
  let dentro = false;
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) {
    const [xi, yi] = pol[i], [xj, yj] = pol[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}
const enRect = (x, y, r, m = 0) => x >= r[0] - m && x <= r[2] + m && y >= r[1] - m && y <= r[3] + m;
export function centroide(pol) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) {
    const [x0, y0] = pol[j], [x1, y1] = pol[i], f = x0 * y1 - x1 * y0;
    a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f;
  }
  if (Math.abs(a) < EPS) return [pol[0][0], pol[0][1]];
  return [cx / (3 * a), cy / (3 * a)];
}
function caja2(pol) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pol) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}
// punto interior «visible» de un polígono (el centroide de una L puede caer afuera): el centro de la celda libre más
// alejada del borde en una rejilla gruesa
export function puntoInterior(pol) {
  const c = centroide(pol);
  const [x0, y0, x1, y1] = caja2(pol);
  let mejor = enPoligono(c[0], c[1], pol) ? [c[0], c[1], distBorde(c[0], c[1], pol)] : null;
  const paso = Math.max(0.2, Math.min(x1 - x0, y1 - y0) / 8);
  for (let x = x0 + paso / 2; x < x1; x += paso) for (let y = y0 + paso / 2; y < y1; y += paso) {
    if (!enPoligono(x, y, pol)) continue;
    const d = distBorde(x, y, pol);
    if (!mejor || d > mejor[2] + 0.3) mejor = [x, y, d];
  }
  return mejor ? [mejor[0], mejor[1]] : c;
}
function distBorde(x, y, pol) {
  let d = Infinity;
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) d = Math.min(d, distSegmento(x, y, pol[j], pol[i]));
  return d;
}
function distSegmento(px, py, [ax, ay], [bx, by]) {
  const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

// ---------------------------------------------------------------- acumulador de triángulos (planta → three)
class Acum {
  constructor() { this.p = []; this.n = []; this.c = []; this.rangos = null; }
  get vertices() { return this.p.length / 3; }
  // triángulo en planta (CCW visto desde afuera); color THREE.Color
  tri(a, b, c, col) {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
    for (const q of [a, b, c]) { this.p.push(q[0], q[2], -q[1]); this.n.push(nx, nz, -ny); this.c.push(col.r, col.g, col.b); }
  }
  quad(a, b, c, d, col) { this.tri(a, b, c, col); this.tri(a, c, d, col); }
  // caja orientada: eje de a a b en planta, ancho t (centrada), de z0 a z1; colores { izq, der, top, bot, ext }
  prisma(ax, ay, bx, by, t, z0, z1, col) {
    const L = Math.hypot(bx - ax, by - ay);
    if (L < 1e-4 || z1 - z0 < 1e-4) return;
    const ux = (bx - ax) / L, uy = (by - ay) / L, nx = -uy * (t / 2), ny = ux * (t / 2);
    const A = [ax + nx, ay + ny], B = [bx + nx, by + ny], Bd = [bx - nx, by - ny], Ad = [ax - nx, ay - ny];   // izquierda: A-B; derecha: Ad-Bd
    const c = (k) => (col.isColor ? col : col[k] || col.izq || col.der);
    const p = (q, z) => [q[0], q[1], z];
    this.quad(p(Ad, z0), p(Bd, z0), p(Bd, z1), p(Ad, z1), c('der'));       // cara derecha (mira a −n)
    this.quad(p(B, z0), p(A, z0), p(A, z1), p(B, z1), c('izq'));           // cara izquierda (mira a +n)
    this.quad(p(Bd, z0), p(B, z0), p(B, z1), p(Bd, z1), c('ext'));         // extremo b
    this.quad(p(A, z0), p(Ad, z0), p(Ad, z1), p(A, z1), c('ext'));         // extremo a
    this.quad(p(Ad, z1), p(Bd, z1), p(B, z1), p(A, z1), c('top'));         // arriba
    this.quad(p(A, z0), p(B, z0), p(Bd, z0), p(Ad, z0), c('bot'));         // abajo
  }
  caja(x0, y0, z0, x1, y1, z1, col) { const ym = (y0 + y1) / 2; this.prisma(x0, ym, x1, ym, y1 - y0, z0, z1, col); }
  // barra entre dos puntos 3D de planta, sección cuadrada g × g (barandas inclinadas)
  barra(p1, p2, g, col) {
    const d = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]], L = Math.hypot(...d);
    if (L < 1e-4) return;
    const u = d.map((v) => v / L), ref = Math.abs(u[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
    let a = [u[1] * ref[2] - u[2] * ref[1], u[2] * ref[0] - u[0] * ref[2], u[0] * ref[1] - u[1] * ref[0]];
    const la = Math.hypot(...a); a = a.map((v) => (v / la) * (g / 2));
    const b = [u[1] * a[2] - u[2] * a[1], u[2] * a[0] - u[0] * a[2], u[0] * a[1] - u[1] * a[0]];
    const esq = (p, s, t) => [p[0] + s * a[0] + t * b[0], p[1] + s * a[1] + t * b[1], p[2] + s * a[2] + t * b[2]];
    const q = [[1, 1], [-1, 1], [-1, -1], [1, -1]];
    for (let i = 0; i < 4; i++) {
      const [s0, t0] = q[i], [s1, t1] = q[(i + 1) % 4];
      this.quad(esq(p1, s0, t0), esq(p1, s1, t1), esq(p2, s1, t1), esq(p2, s0, t0), col);
    }
  }
  // polígono plano a la altura z (o z(x, y)); arriba: normal +z; si no, −z (cielo)
  poligono(pol, z, col, arriba = true) {
    let pts = pol.map(([x, y]) => new THREE.Vector2(x, y));
    if (pts.length > 2 && pts[0].equals(pts[pts.length - 1])) pts = pts.slice(0, -1);
    if (THREE.ShapeUtils.isClockWise(pts)) pts.reverse();
    const tris = THREE.ShapeUtils.triangulateShape(pts, []);
    const zf = typeof z === 'function' ? z : () => z;
    for (const [i, j, k] of tris) {
      const a = [pts[i].x, pts[i].y, zf(pts[i].x, pts[i].y)], b = [pts[j].x, pts[j].y, zf(pts[j].x, pts[j].y)], c = [pts[k].x, pts[k].y, zf(pts[k].x, pts[k].y)];
      if (arriba) this.tri(a, b, c, col); else this.tri(a, c, b, col);
    }
  }
  geometria() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.p, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.n, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.c, 3));
    g.computeBoundingSphere();
    return g;
  }
}

// ---------------------------------------------------------------- materiales compartidos (siguen el tema)
let MATS = null;
function materiales() {
  if (MATS) return MATS;
  const opaco = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85, metalness: 0.02 });
  const piso = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75, metalness: 0.02, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  // el cielo raso mira hacia abajo: sin sombras solo lo alumbra el hemisferio; un poco de emisión lo deja claro, como
  // un cielo con luminarias
  const cielo = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0, emissive: 0x6e6d69 });
  // doble cara en una sola pasada (una llamada por malla transparente)
  const vidrio = new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, opacity: 0.32, roughness: 0.1, metalness: 0, depthWrite: false, side: THREE.DoubleSide, forceSinglePass: true });
  MATS = { opaco, piso, cielo, vidrio };
  const tema = (t) => {
    if (!t) return;
    const oscuro = t.bg.r + t.bg.g + t.bg.b < 0.3;
    opaco.color.setScalar(oscuro ? 0.86 : 1); piso.color.setScalar(oscuro ? 0.84 : 1); cielo.color.setScalar(oscuro ? 0.8 : 1);
    cielo.emissive.setHex(oscuro ? 0x3a3936 : 0x6e6d69);
    vidrio.opacity = oscuro ? 0.4 : 0.32;
  };
  try { tema(tokens()); } catch { /* sin documento */ }
  onTheme(tema);
  return MATS;
}

// ---------------------------------------------------------------- lectura del nivel
// Recintos y subrecintos indexados, con el piso de cada uno (z_piso_m y rampas) y una rejilla de búsqueda de 1 m
function indice(nivel) {
  const recs = (nivel.recintos || []).map((r) => ({ r, pol: r.poligono, caja: caja2(r.poligono) }));
  const subs = [];
  for (const r of nivel.recintos || []) for (const s of r.subrecintos || []) subs.push({ r: s, padre: r, pol: s.poligono, caja: caja2(s.poligono) });
  const porId = new Map(recs.map((o) => [o.r.id, o]));
  for (const s of subs) porId.set(s.r.id, s);
  const C1 = 1, todos = recs.concat(subs);
  const [bx0, by0, bx1, by1] = caja2(nivel.contorno?.length ? nivel.contorno : todos.flatMap((o) => o.pol));
  const nx = Math.max(1, Math.ceil((bx1 - bx0) / C1)), ny = Math.max(1, Math.ceil((by1 - by0) / C1));
  const celdas = Array.from({ length: nx * ny }, () => []);
  for (const o of recs) {
    const [x0, y0, x1, y1] = o.caja;
    for (let i = Math.max(0, Math.floor((x0 - bx0) / C1)); i <= Math.min(nx - 1, Math.floor((x1 - bx0) / C1)); i++)
      for (let j = Math.max(0, Math.floor((y0 - by0) / C1)); j <= Math.min(ny - 1, Math.floor((y1 - by0) / C1)); j++) celdas[j * nx + i].push(o);
  }
  const recintoEn = (x, y) => {
    const i = Math.floor((x - bx0) / C1), j = Math.floor((y - by0) / C1);
    if (i < 0 || j < 0 || i >= nx || j >= ny) return null;
    // primero los recintos transitables (la huella de la torre en los exteriores tapa todo lo demás)
    let otro = null;
    for (const o of celdas[j * nx + i]) if (enRect(x, y, o.caja, 1e-3) && enPoligono(x, y, o.pol)) { if (o.r.transitable === false) otro = otro || o.r.id; else return o.r.id; }
    return otro;
  };
  const subrecintoEn = (x, y, rec) => {
    for (const s of subs) if ((!rec || s.padre.id === rec) && enRect(x, y, s.caja, 1e-3) && enPoligono(x, y, s.pol)) return s.r.id;
    return null;
  };
  return { recs, subs, porId, recintoEn, subrecintoEn };
}
// cota del piso de un recinto en (x, y), relativa al nivel: z_piso_m y rampa { eje, desde, hasta, z0, z1 }
export function cotaPiso(r, x, y) {
  if (!r) return 0;
  const z = +r.z_piso_m || 0, ra = r.rampa;
  if (ra && ra.hasta !== ra.desde) {
    const v = ra.eje === 'y' ? y : x, t = Math.max(0, Math.min(1, (v - ra.desde) / (ra.hasta - ra.desde)));
    return z + (+ra.z0 || 0) + t * ((+ra.z1 || 0) - (+ra.z0 || 0));
  }
  return z;
}

// ---------------------------------------------------------------- muros con vanos
// tramos de un muro: [{ s0, s1, z0, z1 }] (s a lo largo del eje, z sobre el piso del muro) descontando puertas y ventanas
function vanosDe(m, puertas, ventanas) {
  const ax = m.a[0], ay = m.a[1], L = Math.hypot(m.b[0] - ax, m.b[1] - ay);
  const ux = (m.b[0] - ax) / L, uy = (m.b[1] - ay) / L;
  const s = (p) => (p[0] - ax) * ux + (p[1] - ay) * uy;
  const v = [];
  for (const p of puertas) { const c = s(p.centro), w = +p.ancho || 0.9; v.push({ s0: c - w / 2, s1: c + w / 2, zb: 0, zt: +p.alto || 2.1, puerta: p }); }
  for (const w of ventanas) { const c = s(w.centro), a = +w.ancho || 1; v.push({ s0: c - a / 2, s1: c + a / 2, zb: +w.antepecho || 1, zt: (+w.antepecho || 1) + (+w.alto || 2), ventana: w }); }
  v.sort((a, b) => a.s0 - b.s0);
  return { L, ux, uy, vanos: v.map((o) => ({ ...o, s0: Math.max(0, o.s0), s1: Math.min(L, o.s1) })).filter((o) => o.s1 - o.s0 > 0.02) };
}
const ALTURA_MURO = (m, nivel) => {
  const h = +m.altura;
  if (Number.isFinite(h) && h > 0) return h;
  return m.tipo === 'fachada' || m.tipo === 'nucleo' ? +nivel.altura_entrepiso_m || 4.2 : +nivel.altura_libre_m || 3;
};
// colores de cada cara de un muro según su tipo y sus lados [izquierdo, derecho] mirando de a a b
function coloresMuro(m) {
  const ext = (l) => l === 'exterior';
  switch (m.tipo) {
    case 'fachada': return { izq: ext(m.lados?.[0]) ? C.ladrillo : C.panete, der: ext(m.lados?.[1]) ? C.ladrillo : C.panete, top: C.ladrillo, bot: C.panete, ext: C.ladrillo };
    case 'nucleo': return { izq: C.concreto, der: C.concreto, top: C.concreto, bot: C.concreto, ext: C.concreto };
    case 'plomado': return { izq: C.plomado, der: C.plomado, top: C.plomado, bot: C.plomado, ext: C.plomado };
    case 'parapeto': return { izq: C.parapeto, der: C.parapeto, top: C.concreto, bot: C.parapeto, ext: C.parapeto };
    case 'cerramiento': return { izq: C.concreto, der: C.concreto, top: C.concreto, bot: C.concreto, ext: C.concreto };
    default: return { izq: C.panete, der: C.panete, top: C.panete, bot: C.panete, ext: C.panete };
  }
}
// Arma un muro (sus tramos sólidos, dinteles, antepechos y vidrios) con un desplazamiento vertical zOff
function armarMuro(op, vi, m, nivel, puertas, ventanas, zOff = 0, { hojas = null, senales = null } = {}) {
  if (m.tipo === 'abierto' || !(+m.espesor > 0)) return;
  const H = ALTURA_MURO(m, nivel), t = +m.espesor, zb = zOff + (+m.z_base_m || 0);
  const { L, ux, uy, vanos } = vanosDe(m, puertas, ventanas);
  const col = coloresMuro(m), ext = t / 2 - 0.002;   // se prolonga media junta para cerrar las esquinas
  const P = (s) => [m.a[0] + ux * s, m.a[1] + uy * s];
  const pieza = (s0, s1, z0, z1, c = col) => { const [x0, y0] = P(s0), [x1, y1] = P(s1); op.prisma(x0, y0, x1, y1, t, zb + z0, zb + z1, c); };
  // cerramiento: muro bajo de 0,40 m y malla hasta su altura (en la malla transparente)
  const solido = m.tipo === 'cerramiento' ? Math.min(0.4, H) : H;
  let cur = -ext;
  for (const v of vanos) {
    if (v.s0 > cur) pieza(cur, v.s0, 0, solido);
    if (v.zb > 0) pieza(v.s0, v.s1, 0, Math.min(v.zb, solido));
    if (v.zt < solido) pieza(v.s0, v.s1, v.zt, solido);
    if (v.ventana && vi) {
      const [x0, y0] = P(v.s0), [x1, y1] = P(v.s1);
      vi.quad([x0, y0, zb + v.zb], [x1, y1, zb + v.zb], [x1, y1, zb + Math.min(v.zt, H)], [x0, y0, zb + Math.min(v.zt, H)], C.vidrio);
      // marco: travesaño inferior y superior delgados
      op.prisma(x0, y0, x1, y1, t + 0.02, zb + v.zb - 0.03, zb + v.zb, C.marco);
    }
    if (v.puerta && hojas) hojas(v.puerta, m, P, ux, uy, t, zb);
    if (v.puerta && senales) senales(v.puerta, m, ux, uy, t, zb);
    cur = Math.max(cur, v.s1);
  }
  if (L + ext > cur) pieza(cur, L + ext, 0, solido);
  if (m.tipo === 'cerramiento' && vi && H > solido) {
    let c = -ext;
    const malla = (s0, s1) => { const [x0, y0] = P(s0), [x1, y1] = P(s1); vi.quad([x0, y0, zb + solido], [x1, y1, zb + solido], [x1, y1, zb + H], [x0, y0, zb + H], C.malla); };
    for (const v of vanos) { if (v.s0 > c) malla(c, v.s0); c = Math.max(c, v.s1); }
    if (L + ext > c) malla(c, L + ext);
    // postes cada 2,5 m
    for (let s = 0; s <= L; s += 2.5) { const [x, y] = P(s); op.caja(x - 0.03, y - 0.03, zb + solido, x + 0.03, y + 0.03, zb + H, C.baranda); }
  }
}

// ---------------------------------------------------------------- escaleras
// partes de una escalera con el lado por donde se sube (dirección en planta, antihorario desde +x)
const DIR = (deg) => { const r = ((+deg || 0) * Math.PI) / 180; return [Math.round(Math.cos(r)), Math.round(Math.sin(r))]; };
// cota de la superficie de una parte en (x, y), relativa al nivel de la parte
export function cotaParte(p, x, y) {
  if (p.tipo !== 'tramo') return +p.z || 0;
  const [dx, dy] = DIR(p.sube_hacia_deg), [x0, y0, x1, y1] = p.rect;
  let t;
  if (dx > 0) t = (x - x0) / (x1 - x0); else if (dx < 0) t = (x1 - x) / (x1 - x0);
  else if (dy > 0) t = (y - y0) / (y1 - y0); else t = (y1 - y) / (y1 - y0);
  t = Math.max(0, Math.min(1, t));
  return +p.z0 + t * (+p.z1 - +p.z0);
}
function armarEscalera(op, esc, zOff) {
  for (const p of esc.partes || []) {
    const [x0, y0, x1, y1] = p.rect;
    if (p.tipo !== 'tramo') { const z = zOff + (+p.z || 0); op.caja(x0, y0, z - 0.22, x1, y1, z, { izq: C.escalon, der: C.escalon, top: C.escalon, bot: C.losa, ext: C.losa }); continue; }
    const n = Math.max(1, +p.contrahuellas || 12), [dx, dy] = DIR(p.sube_hacia_deg), z0 = zOff + +p.z0, z1 = zOff + +p.z1, h = (z1 - z0) / n;
    const largo = dx ? x1 - x0 : y1 - y0;
    for (let k = 0; k < n; k++) {
      const a = (k / n) * largo, b = ((k + 1) / n) * largo, zt = z0 + (k + 1) * h;
      let r;
      if (dx > 0) r = [x0 + a, y0, x0 + b, y1]; else if (dx < 0) r = [x1 - b, y0, x1 - a, y1];
      else if (dy > 0) r = [x0, y0 + a, x1, y0 + b]; else r = [x0, y1 - b, x1, y1 - a];
      op.caja(r[0], r[1], zt - h - 0.18, r[2], r[3], zt, { izq: C.escalon, der: C.escalon, top: C.escalon, bot: C.losa, ext: C.escalon });
    }
    // pasamanos a ambos lados, a 0,90 m sobre la línea de huellas, con dos parales
    const lados = dx ? [[y0 + 0.05], [y1 - 0.05]] : [[x0 + 0.05], [x1 - 0.05]];
    for (const [c] of lados) {
      const pIni = dx ? [dx > 0 ? x0 : x1, c] : [c, dy > 0 ? y0 : y1], pFin = dx ? [dx > 0 ? x1 : x0, c] : [c, dy > 0 ? y1 : y0];
      op.barra([pIni[0], pIni[1], z0 + 0.9], [pFin[0], pFin[1], z1 + 0.9], 0.05, C.baranda);
      for (const f of [0.08, 0.92]) {
        const px = pIni[0] + (pFin[0] - pIni[0]) * f, py = pIni[1] + (pFin[1] - pIni[1]) * f, pz = z0 + (z1 - z0) * f;
        op.caja(px - 0.02, py - 0.02, pz, px + 0.02, py + 0.02, pz + 0.9, C.baranda);
      }
    }
  }
}

// ---------------------------------------------------------------- construcción de un nivel
// colorPor: 'grupo' | 'estado' | 'contraste' | null. op.abajo: nivel inferior (para ver completa la escalera que baja);
// op.envolvente: niveles de la torre cuyas fachadas y losas se dibujan como contexto (exteriores y cubierta);
// op.estados: Map<recinto, 'cumple' | 'parcial' | 'falta' | …> para colorPor 'estado'; op.contraste: Map<recinto, Color>.
// op.omitirContexto: ids de niveles del contexto que no se dibujan en la envolvente (el recorrido dibuja el piso 1 entero
// junto a los exteriores); op.huella: false omite el piso de los recintos no transitables (la huella de la torre en los
// exteriores, cuando el piso 1 se dibuja encima).
export function construirPiso(nivel, {
  tier = 'media', colorPor = 'grupo', grupos = {}, cielo = true, envolvente = true, abajo = null, contexto = null, senales = true, hojas = true,
  estados = null, contraste = null, coloresEstado = null, omitirContexto = [], huella = true,
} = {}) {
  const mats = materiales();
  const ix = indice(nivel);
  const op = new Acum(), pi = new Acum(), ci = new Acum(), vi = new Acum();
  const tipoNivel = nivel.id === 'EXT' ? 'ext' : nivel.id === 'CUB' ? 'cub' : nivel.id === 'BT' ? 'bt' : 'piso';
  const hLibre = +nivel.altura_libre_m || 3, hEntre = +nivel.altura_entrepiso_m || 4.2;
  const escaleras = nivel.escaleras || [];
  const recEsc = new Map(escaleras.map((e) => [e.recinto, e]));
  const escAbajo = new Map((abajo?.escaleras || []).map((e) => [e.id, e]));
  const puertasPorMuro = new Map(), ventanasPorMuro = new Map();
  for (const p of nivel.puertas || []) { if (!puertasPorMuro.has(p.muro)) puertasPorMuro.set(p.muro, []); puertasPorMuro.get(p.muro).push(p); }
  for (const w of nivel.ventanas || []) { if (!ventanasPorMuro.has(w.muro)) ventanasPorMuro.set(w.muro, []); ventanasPorMuro.get(w.muro).push(w); }
  const grupoDe = (id) => ix.porId.get(id)?.padre?.grupo_1633 || ix.porId.get(id)?.r?.grupo_1633 || null;
  const colorGrupo = (g) => grupos?.[g]?.color_hex || null;

  // lado hacia el que queda un recinto respecto de un muro (+1 izquierda, −1 derecha, 0 no se sabe)
  const ladoDe = (id, cx, cy, nx, ny) => {
    if (!id) return 0;
    const o = ix.porId.get(id);
    const prueba = (s) => (o ? enPoligono(cx + s * nx * 0.35, cy + s * ny * 0.35, o.pol) : id === 'exterior' && !ix.recintoEn(cx + s * nx * 0.35, cy + s * ny * 0.35));
    if (prueba(1)) return 1;
    if (prueba(-1)) return -1;
    return 0;
  };
  // hojas de puerta abiertas a 90° (batientes), corridas (corredizas y automáticas, estas de vidrio)
  const hojasPuerta = !hojas ? null : (p, m, P, ux, uy, t, zb) => {
    if (p.espejo_de) return;   // el vano se dibuja; la hoja ya la tiene su puerta espejo
    const nx = -uy, ny = ux, cx = p.centro[0], cy = p.centro[1], w = +p.ancho || 0.9, alto = (+p.alto || 2.1) - 0.02, n = Math.max(1, +p.hojas || 1);
    const ladoHacia = ladoDe(p.hacia, cx, cy, nx, ny) || -ladoDe(p.desde, cx, cy, nx, ny) || 1;
    const lado = p.abre === 'afuera' ? -ladoHacia : ladoHacia;
    const col = p.tipo === 'cortafuego' ? C.cortafuego : m.tipo === 'plomado' ? C.puerta_plomo : C.puerta;
    if (p.abre === 'corrediza' || p.tipo === 'corrediza' || p.tipo === 'automatica') {
      const off = (t / 2 + 0.035) * ladoHacia, hw = w / n, vidrio = p.tipo === 'automatica';
      for (let k = 0; k < n; k++) {
        // abiertas: cada hoja corrida a su lado, sobre el muro
        const sgn = n === 2 ? (k ? 1 : -1) : (p.bisagra === 'derecha' ? 1 : -1);
        const c0 = sgn * (w / 2 + hw / 2 - 0.05);
        const x0 = cx + ux * (c0 - hw / 2) + nx * off, y0 = cy + uy * (c0 - hw / 2) + ny * off, x1 = cx + ux * (c0 + hw / 2) + nx * off, y1 = cy + uy * (c0 + hw / 2) + ny * off;
        if (vidrio) vi.quad([x0, y0, zb], [x1, y1, zb], [x1, y1, zb + alto], [x0, y0, zb + alto], C.vidrio);
        else op.prisma(x0, y0, x1, y1, 0.04, zb, zb + alto, col);
      }
      return;
    }
    // batiente: bisagra a la izquierda o a la derecha de quien entra hacia «hacia»; la hoja abierta queda perpendicular
    const hx = nx * ladoHacia, hy = ny * ladoHacia, izq = [-hy, hx];
    const bis = p.bisagra === 'derecha' ? -1 : 1;
    const ejes = n === 2 ? [1, -1] : [bis];
    for (const e of ejes) {
      const bx = cx + izq[0] * e * (w / 2 - 0.02), by = cy + izq[1] * e * (w / 2 - 0.02), lw = w / n - 0.03;
      op.prisma(bx + nx * lado * (t / 2), by + ny * lado * (t / 2), bx + nx * lado * (t / 2 + lw), by + ny * lado * (t / 2 + lw), 0.045, zb, zb + alto, col);
    }
  };
  // señal de color sobre la puerta (Res. 1633: colores de señalización por grupo), a cada lado: el color del recinto al
  // que se entra por ese lado
  const senalPuerta = !senales ? null : (p, m, ux, uy, t, zb) => {
    const nx = -uy, ny = ux, cx = p.centro[0], cy = p.centro[1], w = Math.min(+p.ancho || 0.9, 1.0), z = zb + (+p.alto || 2.1) + 0.1;
    for (const s of [1, -1]) {
      const otro = ladoDe(p.hacia, cx, cy, nx, ny) === -s ? p.hacia : ladoDe(p.desde, cx, cy, nx, ny) === -s ? p.desde : null;
      const g = otro && otro !== 'exterior' ? grupoDe(otro) : null;
      if (!g || g === 'circulacion') continue;
      const hex = colorGrupo(g);
      if (!hex) continue;
      const d = t / 2 + 0.012;
      op.prisma(cx - ux * w / 2 + nx * s * d, cy - uy * w / 2 + ny * s * d, cx + ux * w / 2 + nx * s * d, cy + uy * w / 2 + ny * s * d, 0.02, z, z + 0.12, new THREE.Color(hex));
    }
  };

  // ---- muros del nivel
  // en los exteriores, la fachada del piso 1 la dibuja la envolvente (con sus ventanas) o el piso 1 entero: se omiten los
  // muros de fachada de los exteriores que caen sobre el contorno de la torre
  const contornoTorre = contexto?.find?.((n) => n.id === 'P1')?.contorno;
  const sobreContorno = (m) => contornoTorre && [m.a, m.b].every(([x, y]) => contornoTorre.some((q, i) => { const r = contornoTorre[(i + 1) % contornoTorre.length]; return distSegmento(x, y, q, r) < 0.05; }));
  for (const m of nivel.muros || []) {
    if (tipoNivel === 'ext' && m.tipo === 'fachada' && sobreContorno(m)) continue;
    armarMuro(op, vi, m, nivel, puertasPorMuro.get(m.id) || [], ventanasPorMuro.get(m.id) || [], 0, { hojas: hojasPuerta, senales: senalPuerta });
  }
  // columnas (en los muros, en el contorno o en el borde de los corredores)
  for (const c of nivel.columnas || []) op.caja(c.x - (+c.b || 0.6) / 2, c.y - (+c.h || 0.6) / 2, 0, c.x + (+c.b || 0.6) / 2, c.y + (+c.h || 0.6) / 2, hEntre, C.concreto);

  // ---- pisos (una malla con colores por vértice; rangos por recinto para colorearRecintos)
  const rangosPiso = new Map();
  const colorBase = new Map();
  const colorPisoDe = (r) => {
    const nom = String(r.ambiente || r.nombre || '');
    if (tipoNivel === 'ext') {
      if (r.transitable === false) return C.huella;
      if (/retorno|bah[ií]a|v[ií]a de servicio/i.test(nom)) return C.asfalto;
      return C.adoquin;
    }
    if (tipoNivel === 'cub') return C.cubierta;
    if (tipoNivel === 'bt' && r.tipo === 'circulacion') return /v[ií]a/i.test(nom) ? C.asfalto : C.adoquin;
    if (/ascensor|montacargas/i.test(nom) && r.grupo_1633 === 'circulacion') return C.cabina;
    const hex = colorGrupo(r.grupo_1633);
    return hex ? tonoPiso(hex, r.grupo_1633 === 'circulacion' ? 0.4 : 0.5) : C.huella;
  };
  for (const { r, pol } of ix.recs) {
    if (!huella && r.transitable === false) continue;
    const esc = recEsc.get(r.id);
    const v0 = pi.vertices, col = colorPisoDe(r);
    if (esc && (abajo || esc.baja_a)) {
      // núcleo de escalera con piso abajo: solo el descanso de piso (bajo los tramos se ve la escalera que baja)
      for (const p of esc.partes || []) if (p.tipo === 'descanso_piso') { const [x0, y0, x1, y1] = p.rect; pi.poligono([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], +p.z || 0, col); }
    } else {
      pi.poligono(pol, (x, y) => cotaPiso(r, x, y), col);
    }
    rangosPiso.set(r.id, [v0, pi.vertices]);
    colorBase.set(r.id, col);
    // subrecintos (baños con tabique): piso de baldosa un poco arriba (sin pelea de profundidad)
    for (const s of r.subrecintos || []) { const w0 = pi.vertices; pi.poligono(s.poligono, cotaPiso(r, 0, 0) + 0.006, C.piso_bano); rangosPiso.set(s.id, [w0, pi.vertices]); colorBase.set(s.id, C.piso_bano); }
  }

  // ---- escaleras: las del nivel y, si hay piso abajo, las del nivel inferior completas (el hueco se ve entero) con los
  // muros de su núcleo
  for (const e of escaleras) armarEscalera(op, e, 0);
  if (abajo) {
    const dz = (+abajo.z || 0) - (+nivel.z || 0);
    const pAbajo = new Map(), vAbajo = new Map();
    for (const p of abajo.puertas || []) { if (!pAbajo.has(p.muro)) pAbajo.set(p.muro, []); pAbajo.get(p.muro).push(p); }
    for (const w of abajo.ventanas || []) { if (!vAbajo.has(w.muro)) vAbajo.set(w.muro, []); vAbajo.get(w.muro).push(w); }
    for (const e of escaleras) {
      const eb = escAbajo.get(e.id);
      if (!eb) continue;
      armarEscalera(op, eb, dz);
      for (const m of abajo.muros || []) if ((m.lados || []).includes(eb.recinto)) armarMuro(op, vi, m, abajo, pAbajo.get(m.id) || [], vAbajo.get(m.id) || [], dz);
      // piso del núcleo de abajo, si es el primer nivel de la escalera
      const rb = (abajo.recintos || []).find((r) => r.id === eb.recinto);
      if (rb && !eb.baja_a) pi.poligono(rb.poligono, dz, colorPisoDe(rb));
    }
  }
  // ojo de cada escalera: baranda baja en su borde, del piso del nivel a la cota alta de sus tramos
  for (const e of escaleras) {
    if (!e.ojo) continue;
    const [x0, y0, x1, y1] = e.ojo, zTop = Math.max(0, ...(e.partes || []).map((p) => +p.z1 || +p.z || 0));
    if (zTop <= 0.01) continue;
    op.caja(x0 + 0.02, y0, 0, x1 - 0.02, y1, 0.05, C.losa);
    for (const [ax, ay, bx, by] of [[x0, y0, x0, y1], [x1, y0, x1, y1]]) op.prisma(ax, ay, bx, by, 0.04, 0, Math.min(zTop, hEntre) + 1.0, C.baranda.clone().lerp(BLANCO, 0.25));
  }

  // ---- obstáculos del recorrido: hueco de la escalera abierta (baranda de 1,10 m salvo la llegada), árboles e islas
  const llegadas = [];
  for (const eb of abajo?.escaleras || []) for (const p of eb.partes || []) if (p.tipo === 'tramo' && Math.abs(+p.z1 - (+nivel.z - +abajo.z)) < 0.05) llegadas.push(p);
  for (const o of nivel.obstaculos_recorrido || []) {
    const pol = o.poligono, zb = +o.z_piso_m || 0, h = +o.altura_m || 1;
    if (/hueco/i.test(o.id)) {
      for (let i = 0; i < pol.length; i++) {
        const a = pol[i], b = pol[(i + 1) % pol.length];
        // tramos de borde libres donde llega un tramo de la escalera de abajo (su extremo alto)
        const libres = llegadas.map((p) => bordeAlto(p)).filter(Boolean).filter(([q, r]) => colineales(a, b, q, r));
        for (const [s0, s1] of restarIntervalos(a, b, libres)) {
          const L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / L, uy = (b[1] - a[1]) / L;
          op.prisma(a[0] + ux * s0, a[1] + uy * s0, a[0] + ux * s1, a[1] + uy * s1, 0.06, zb, zb + h, C.baranda.clone().lerp(BLANCO, 0.3));
        }
      }
      continue;
    }
    const [x0, y0, x1, y1] = caja2(pol);
    if (/mango|[aá]rbol|palma/i.test(o.id + o.nombre)) {
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, r = Math.max(0.2, (x1 - x0) / 2);
      op.caja(cx - r * 0.6, cy - r * 0.6, zb, cx + r * 0.6, cy + r * 0.6, zb + h * 0.45, C.tronco);
      const R = Math.min(5, h * 0.4);
      op.caja(cx - R, cy - R, zb + h * 0.4, cx + R, cy + R, zb + h * 0.85, C.copa);
      op.caja(cx - R * 0.6, cy - R * 0.6, zb + h * 0.85, cx + R * 0.6, cy + R * 0.6, zb + h, C.copa);
    } else if (/isla|verde|jard/i.test(o.id + o.nombre)) {
      op.caja(x0, y0, zb, x1, y1, zb + Math.max(0.15, h), { izq: C.concreto, der: C.concreto, top: C.verde, bot: C.concreto, ext: C.concreto });
      if (/palma/i.test(o.nombre)) { const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2; op.caja(cx - 0.15, cy - 0.15, zb, cx + 0.15, cy + 0.15, zb + 6, C.tronco); op.caja(cx - 1.6, cy - 1.6, zb + 5.6, cx + 1.6, cy + 1.6, zb + 6.4, C.copa); }
    }
    // el resto (filas de paneles de la terraza) los dibuja la capa de equipos; aquí solo cuentan para la colisión
  }

  // ---- cielo raso: a la altura libre en los recintos cerrados; en los núcleos de escalera, en lo alto del hueco
  const conCielo = (r) => {
    if (!cielo) return false;
    const nom = String(r.ambiente || r.nombre || '');
    if (tipoNivel === 'ext') return /galer[ií]a cubierta/i.test(nom);
    if (tipoNivel === 'cub') return /caseta/i.test(nom);
    if (tipoNivel === 'bt') return r.tipo === 'recinto' && !/enterrad|cisterna|tanque|patio|pasaje|almacenamiento central/i.test(nom);
    return r.transitable !== false;
  };
  for (const { r, pol } of ix.recs) {
    if (!conCielo(r)) continue;
    const h = recEsc.has(r.id) ? hEntre - 0.02 : /ductos/i.test(r.ambiente || '') ? hEntre - 0.02 : tipoNivel === 'ext' ? 3.2 : hLibre;
    ci.poligono(pol, cotaPiso(r, 0, 0) + h, C.cielo, false);
  }

  // ---- envolvente de la torre como contexto (exteriores, bloque técnico y cubierta): fachadas con ventanas y losas
  if (envolvente && Array.isArray(contexto) && tipoNivel !== 'piso') {
    for (const L of contexto) {
      if (L.id === nivel.id || L.id === 'EXT' || omitirContexto.includes(L.id)) continue;
      if (tipoNivel === 'bt' && L.id === 'BT') continue;
      if (tipoNivel === 'cub' && L.id === 'BT') continue;
      const dz = (+L.z || 0) - (+nivel.z || 0);
      const pM = new Map(), vM = new Map();
      for (const p of L.puertas || []) { if (!pM.has(p.muro)) pM.set(p.muro, []); pM.get(p.muro).push(p); }
      for (const w of L.ventanas || []) { if (!vM.has(w.muro)) vM.set(w.muro, []); vM.get(w.muro).push(w); }
      const tipos = L.id === 'CUB' ? ['parapeto', 'fachada', 'nucleo'] : ['fachada'];
      for (const m of L.muros || []) {
        if (!tipos.includes(m.tipo)) continue;
        if (L.id === 'CUB' && m.tipo === 'nucleo' && !(m.lados || []).some((l) => /A220/.test(String(l)))) continue;
        armarMuro(op, vi, m, L, pM.get(m.id) || [], vM.get(m.id) || [], dz);
      }
      if (L.id === 'CUB') {
        for (const r of L.recintos || []) pi.poligono(r.poligono, dz + (+r.z_piso_m || 0), C.cubierta);
        // techo de las casetas de escalera
        for (const r of L.recintos || []) if (/caseta/i.test(r.ambiente || '')) op.poligono(r.poligono, dz + (+L.altura_libre_m || 3) + 0.2, C.losa);
      } else if (L.contorno && /^P[2-4]$/.test(L.id)) {
        // losa entre pisos: borde visible y cara inferior
        const [x0, y0, x1, y1] = caja2(L.contorno);
        op.caja(x0 + 0.1, y0 + 0.1, dz - 0.3, x1 - 0.1, y1 - 0.1, dz, { izq: C.borde_losa, der: C.borde_losa, top: C.losa, bot: C.cielo, ext: C.borde_losa });
      } else if (L.id === 'P1' && tipoNivel === 'ext') {
        pi.poligono(L.contorno, 0.004, C.huella);
      }
    }
  }

  // ---- mallas
  const grupo = new THREE.Group();
  grupo.name = `planta:${nivel.id}`;
  grupo.position.y = +nivel.z || 0;
  const mk = (acc, mat, nombre) => {
    if (!acc.vertices) return null;
    const m = new THREE.Mesh(acc.geometria(), mat);
    m.name = nombre;
    m.matrixAutoUpdate = false;
    grupo.add(m);
    return m;
  };
  const mallaMuros = mk(op, mats.opaco, 'planta:muros');
  const mallaPisos = mk(pi, mats.piso, 'planta:pisos');
  const mallaCielo = mk(ci, mats.cielo, 'planta:cielo');
  const mallaVidrio = mk(vi, mats.vidrio, 'planta:vidrios');
  if (mallaVidrio) mallaVidrio.renderOrder = 1;
  grupo.updateMatrixWorld(true);
  for (const m of [mallaMuros, mallaPisos, mallaCielo, mallaVidrio]) if (m) m.updateMatrix();
  const colPiso = mallaPisos?.geometry.attributes.color;
  const col0 = colPiso ? colPiso.array.slice() : null;

  const pintarRango = (id, c) => {
    const r = rangosPiso.get(id);
    if (!r || !colPiso) return;
    const a = colPiso.array;
    for (let v = r[0]; v < r[1]; v++) { if (c) { a[3 * v] = c.r; a[3 * v + 1] = c.g; a[3 * v + 2] = c.b; } else { a[3 * v] = col0[3 * v]; a[3 * v + 1] = col0[3 * v + 1]; a[3 * v + 2] = col0[3 * v + 2]; } }
  };
  const api = {
    grupo, mallaMuros, mallaPisos, mallaCielo, mallaVidrio, nivel,
    recintoEn: ix.recintoEn,
    subrecintoEn: ix.subrecintoEn,
    recinto: (id) => ix.porId.get(id)?.r || null,
    // pinta el piso de los recintos del mapa (id → THREE.Color, o null para el tono de su grupo); sin mapa, restaura todo
    colorearRecintos(mapa) {
      if (!colPiso) return;
      if (!mapa) colPiso.array.set(col0);
      else for (const id of rangosPiso.keys()) if (mapa.has(id)) pintarRango(id, mapa.get(id) ? new THREE.Color(mapa.get(id)) : null); else pintarRango(id, null);
      colPiso.needsUpdate = true;
    },
    // nombre y punto de cada recinto (coordenadas locales del grupo, a 2,2 m sobre su piso)
    etiquetas() {
      return ix.recs.filter(({ r }) => r.transitable !== false).map(({ r, pol }) => {
        const [x, y] = puntoInterior(pol);
        return { recinto: r.id, texto: r.ambiente || r.nombre || r.id, punto: new THREE.Vector3(x, cotaPiso(r, x, y) + 2.2, -y), grupo: r.grupo_1633 };
      });
    },
    stats() {
      let llamadas = 0, triangulos = 0;
      for (const m of [mallaMuros, mallaPisos, mallaCielo, mallaVidrio]) if (m && m.visible) { llamadas++; triangulos += m.geometry.attributes.position.count / 3; }
      return { llamadas, triangulos };
    },
    cielo(on) { if (mallaCielo) mallaCielo.visible = !!on; },
    dispose() {
      for (const m of [mallaMuros, mallaPisos, mallaCielo, mallaVidrio]) if (m) { m.geometry.dispose(); m.removeFromParent(); }
      grupo.removeFromParent();
    },
  };
  // color inicial por estado o contraste (si se pidió)
  if (colorPor === 'estado' && estados) api.colorearRecintos(new Map([...estados].map(([id, e]) => [id, coloresEstado?.[e] || null])));
  else if (colorPor === 'contraste' && contraste) api.colorearRecintos(contraste);
  else if (colorPor === null) api.colorearRecintos(new Map([...rangosPiso.keys()].map((id) => [id, C.huella])));
  return api;
}
// extremo alto de un tramo (el borde por donde se llega arriba) como segmento [[x, y], [x, y]]
export function bordeAlto(p) {
  const [dx, dy] = DIR(p.sube_hacia_deg), [x0, y0, x1, y1] = p.rect;
  if (dx > 0) return [[x1, y0], [x1, y1]]; if (dx < 0) return [[x0, y0], [x0, y1]];
  if (dy > 0) return [[x0, y1], [x1, y1]]; return [[x0, y0], [x1, y0]];
}
function colineales(a, b, q, r) {
  const L = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const d = (p) => Math.abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / L;
  return d(q) < 0.08 && d(r) < 0.08;
}
// partes de [a, b] que no cubren los segmentos libres (todos colineales con a-b), como intervalos [s0, s1] desde a
function restarIntervalos(a, b, libres) {
  const L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / L, uy = (b[1] - a[1]) / L;
  const s = (p) => (p[0] - a[0]) * ux + (p[1] - a[1]) * uy;
  const quitar = libres.map(([q, r]) => [Math.min(s(q), s(r)), Math.max(s(q), s(r))]).sort((x, y) => x[0] - y[0]);
  const out = [];
  let cur = 0;
  for (const [q0, q1] of quitar) { if (q0 > cur) out.push([cur, Math.min(q0, L)]); cur = Math.max(cur, q1); }
  if (cur < L) out.push([cur, L]);
  return out.filter(([x, y]) => y - x > 0.02);
}

// ---------------------------------------------------------------- rejilla de colisión
// inflado de una rejilla (1 = bloqueada) por el radio del caminante: distancia (chaflán 3-4) a la celda bloqueada más
// cercana, y se bloquea lo que queda a menos del umbral (en unidades del chaflán, 3 por celda)
function inflar(g, nx, ny, umbral) {
  const INF = 1 << 20, dist = new Int32Array(nx * ny);
  for (let k = 0; k < g.length; k++) dist[k] = g[k] === 1 ? 0 : INF;
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const k = j * nx + i;
    if (!dist[k]) continue;
    let d = dist[k];
    if (i > 0) d = Math.min(d, dist[k - 1] + 3);
    if (j > 0) { d = Math.min(d, dist[k - nx] + 3); if (i > 0) d = Math.min(d, dist[k - nx - 1] + 4); if (i < nx - 1) d = Math.min(d, dist[k - nx + 1] + 4); }
    dist[k] = d;
  }
  for (let j = ny - 1; j >= 0; j--) for (let i = nx - 1; i >= 0; i--) {
    const k = j * nx + i;
    if (!dist[k]) continue;
    let d = dist[k];
    if (i < nx - 1) d = Math.min(d, dist[k + 1] + 3);
    if (j < ny - 1) { d = Math.min(d, dist[k + nx] + 3); if (i < nx - 1) d = Math.min(d, dist[k + nx + 1] + 4); if (i > 0) d = Math.min(d, dist[k + nx - 1] + 4); }
    dist[k] = d;
  }
  // la celda bloqueada se mide desde su centro: quien llama suma media celda al radio
  const out = new Uint8Array(g);
  for (let k = 0; k < g.length; k++) if (g[k] !== 1 && dist[k] < umbral) out[k] = 1;
  return out;
}
// Códigos de celda: 0 libre, 1 bloqueada, 2 zona de escalera (libre si alguna parte de escalera la cubre a una altura
// continua con la del caminante: eso lo decide quien camina, con las partes de todos los niveles).
// op.obstaculos: huellas de equipos grandes [{ x, y, w, d, rot }] (rectángulos girados) y polígonos extra; op.partes:
// rectángulos de las partes de escalera (de este nivel y de los vecinos) que cuentan como piso dentro de los núcleos;
// op.llegadas: bordes altos de los tramos que llegan desde abajo (en el hueco de la escalera abierta no llevan baranda).
// Un obstáculo con altura (op.obstaculos con «alto», o los de obstaculos_recorrido con altura_m) bloquea a quien camina
// por el piso, pero no es duro: «duro» es la rejilla inflada sin ellos y «alto», la altura de lo que tapa cada celda sobre
// su piso (la máxima de los obstáculos cuya huella inflada la cubre), para que quien salta pase por encima o se pare allí.
export function rejillaColision(nivel, { celda = 0.10, radio = 0.30, obstaculos = [], partes = null, llegadas = [] } = {}) {
  const ix = indice(nivel);
  const [cx0, cy0, cx1, cy1] = caja2(nivel.contorno?.length ? nivel.contorno : ix.recs.flatMap((o) => o.pol));
  const x0 = cx0 - 1, y0 = cy0 - 1, nx = Math.ceil((cx1 - cx0 + 2) / celda), ny = Math.ceil((cy1 - cy0 + 2) / celda);
  const g = new Uint8Array(nx * ny).fill(1);
  const esc = new Set((nivel.escaleras || []).map((e) => e.recinto));
  const rectsEsc = partes || (nivel.escaleras || []).flatMap((e) => (e.partes || []).map((p) => p.rect));
  const cubierta = (x, y) => rectsEsc.some((r) => enRect(x, y, r, 1e-3));
  // acceso de cada puerta de un núcleo de escalera: el vano y 0,45 m a cada lado del muro son piso, aunque el descanso
  // empiece en la cara libre de la estructura (0,17 m dentro del recinto): sin esto la franja entre el eje del muro y el
  // descanso queda bloqueada y la puerta no se puede cruzar
  const muroDe = new Map((nivel.muros || []).map((m) => [m.id, m]));
  const accesos = [];
  for (const p of nivel.puertas || []) {
    const m = muroDe.get(p.muro);
    if (!m || !p.centro || !(esc.has(p.desde) || esc.has(p.hacia))) continue;
    const L = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]) || 1;
    accesos.push({ x: p.centro[0], y: p.centro[1], ux: (m.b[0] - m.a[0]) / L, uy: (m.b[1] - m.a[1]) / L, hl: (+p.ancho || 0.9) / 2, hw: (+m.espesor || 0.2) / 2 + 0.45,
      adentro: p.desde !== 'exterior' && p.hacia !== 'exterior' });
  }
  const enAcceso = (x, y) => accesos.some((a) => { const px = x - a.x, py = y - a.y; return Math.abs(px * a.ux + py * a.uy) <= a.hl && Math.abs(-px * a.uy + py * a.ux) <= a.hw; });
  // 1) recintos transitables
  const llenar = (pol, fn) => {
    const [px0, py0, px1, py1] = caja2(pol);
    const j0 = Math.max(0, Math.floor((py0 - y0) / celda)), j1 = Math.min(ny - 1, Math.ceil((py1 - y0) / celda));
    for (let j = j0; j <= j1; j++) {
      const y = y0 + (j + 0.5) * celda, xs = [];
      for (let i = 0, k = pol.length - 1; i < pol.length; k = i++) {
        const [xa, ya] = pol[k], [xb, yb] = pol[i];
        if ((ya > y) !== (yb > y)) xs.push(xa + ((y - ya) * (xb - xa)) / (yb - ya));
      }
      xs.sort((a, b) => a - b);
      for (let q = 0; q + 1 < xs.length; q += 2) {
        const i0 = Math.max(0, Math.ceil((xs[q] - x0) / celda - 0.5)), i1 = Math.min(nx - 1, Math.floor((xs[q + 1] - x0) / celda - 0.5));
        for (let i = i0; i <= i1; i++) fn(j * nx + i, x0 + (i + 0.5) * celda, y);
      }
    }
  };
  for (const { r, pol } of ix.recs) {
    if (r.transitable === false) continue;
    if (esc.has(r.id)) llenar(pol, (k, x, y) => { g[k] = cubierta(x, y) ? 2 : enAcceso(x, y) ? 0 : 1; });
    else llenar(pol, (k) => { g[k] = 0; });
  }
  // la franja del vano que no cae en ningún recinto (el del corredor llega a la cara del muro y el núcleo empieza en su
  // eje) también es piso; las puertas al exterior no: afuera no hay rejilla
  for (const a of accesos) {
    if (!a.adentro) continue;
    const ext = Math.abs(a.ux) * a.hl + Math.abs(a.uy) * a.hw, eyt = Math.abs(a.uy) * a.hl + Math.abs(a.ux) * a.hw;
    const i0 = Math.max(0, Math.floor((a.x - ext - x0) / celda)), i1 = Math.min(nx - 1, Math.floor((a.x + ext - x0) / celda));
    const j0 = Math.max(0, Math.floor((a.y - eyt - y0) / celda)), j1 = Math.min(ny - 1, Math.floor((a.y + eyt - y0) / celda));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const k = j * nx + i, px = x0 + (i + 0.5) * celda, py = y0 + (j + 0.5) * celda;
      if (g[k] === 1 && enAcceso(px, py) && !ix.recs.some((o) => enPoligono(px, py, o.pol))) g[k] = 0;
    }
  }
  // 2) bloqueos crudos: muros (menos las puertas), columnas, ojos de escalera, obstáculos y equipos; los obstáculos con
  // altura van aparte (bajo) y dejan su altura en alto, sobre la huella inflada por el radio
  const crudo = new Uint8Array(nx * ny), bajo = new Uint8Array(nx * ny), alto = new Float32Array(nx * ny);
  const marcarOBB = (cx, cy, ux, uy, hl, hw, en = crudo, valor = 1) => {
    const ext = Math.abs(ux) * hl + Math.abs(uy) * hw, eyt = Math.abs(uy) * hl + Math.abs(ux) * hw;
    const i0 = Math.max(0, Math.floor((cx - ext - x0) / celda)), i1 = Math.min(nx - 1, Math.floor((cx + ext - x0) / celda));
    const j0 = Math.max(0, Math.floor((cy - eyt - y0) / celda)), j1 = Math.min(ny - 1, Math.floor((cy + eyt - y0) / celda));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const px = x0 + (i + 0.5) * celda - cx, py = y0 + (j + 0.5) * celda - cy;
      if (Math.abs(px * ux + py * uy) <= hl && Math.abs(-px * uy + py * ux) <= hw) { const k = j * nx + i; if (en[k] < valor) en[k] = valor; }
    }
  };
  const margen = radio + celda;
  const marcarAlto = (pol, h) => {
    const [a0, b0, a1, b1] = caja2(pol);
    marcarOBB((a0 + a1) / 2, (b0 + b1) / 2, 1, 0, (a1 - a0) / 2 + margen, (b1 - b0) / 2 + margen, alto, h);
  };
  const segmento = (ax, ay, bx, by, t) => {
    const L = Math.hypot(bx - ax, by - ay);
    if (L < 1e-4) return;
    const ux = (bx - ax) / L, uy = (by - ay) / L;
    marcarOBB((ax + bx) / 2, (ay + by) / 2, ux, uy, L / 2, Math.max(t, celda * 0.6) / 2);
  };
  const puertasPorMuro = new Map();
  for (const p of nivel.puertas || []) { if (!puertasPorMuro.has(p.muro)) puertasPorMuro.set(p.muro, []); puertasPorMuro.get(p.muro).push(p); }
  for (const m of nivel.muros || []) {
    if (m.tipo === 'abierto' || !(+m.espesor > 0)) continue;
    const { L, ux, uy, vanos } = vanosDe(m, puertasPorMuro.get(m.id) || [], []);
    const t = +m.espesor, e = t / 2;
    let cur = -e;
    for (const v of vanos) { if (v.s0 > cur) segmento(m.a[0] + ux * cur, m.a[1] + uy * cur, m.a[0] + ux * v.s0, m.a[1] + uy * v.s0, t); cur = Math.max(cur, v.s1); }
    if (L + e > cur) segmento(m.a[0] + ux * cur, m.a[1] + uy * cur, m.a[0] + ux * (L + e), m.a[1] + uy * (L + e), t);
  }
  for (const c of nivel.columnas || []) marcarOBB(c.x, c.y, 1, 0, (+c.b || 0.6) / 2, (+c.h || 0.6) / 2);
  for (const e of nivel.escaleras || []) if (e.ojo) { const [a, b, c2, d] = e.ojo; marcarOBB((a + c2) / 2, (b + d) / 2, 1, 0, (c2 - a) / 2, (d - b) / 2); }
  // obstáculos del recorrido: el hueco de la escalera abierta pasa a zona de escalera (solo se pisa el tramo que baja y
  // continúa a la altura del piso); su borde, salvo la llegada, es baranda
  for (const o of nivel.obstaculos_recorrido || []) {
    if (/hueco/i.test(o.id)) {
      llenar(o.poligono, (k, x, y) => { g[k] = cubierta(x, y) ? 2 : 1; });
      const pol = o.poligono;
      for (let i = 0; i < pol.length; i++) {
        const a = pol[i], b = pol[(i + 1) % pol.length];
        const libres = llegadas.filter(([q, r]) => colineales(a, b, q, r));
        for (const [s0, s1] of restarIntervalos(a, b, libres)) {
          const L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / L, uy = (b[1] - a[1]) / L;
          segmento(a[0] + ux * s0, a[1] + uy * s0, a[0] + ux * s1, a[1] + uy * s1, 0.06);
        }
      }
      continue;
    }
    const h = +o.altura_m;
    if (h > 0) { llenar(o.poligono, (k) => { bajo[k] = 1; }); marcarAlto(o.poligono, h); } else llenar(o.poligono, (k) => { crudo[k] = 1; });
  }
  for (const ob of obstaculos) {
    const h = +ob.alto, en = h > 0 ? bajo : crudo;
    if (ob.poligono) { llenar(ob.poligono, (k) => { en[k] = 1; }); if (h > 0) marcarAlto(ob.poligono, h); continue; }
    const c = Math.cos(ob.rot || 0), s = Math.sin(ob.rot || 0);
    marcarOBB(ob.x, ob.y, c, s, ob.w / 2, ob.d / 2, en);
    if (h > 0) marcarOBB(ob.x, ob.y, c, s, ob.w / 2 + margen, ob.d / 2 + margen, alto, h);
  }
  // 3) inflado por el radio del caminante: distancia (chaflán 3-4) a la celda bloqueada más cercana. Dos veces: con todo
  // (lo que usa quien camina por el piso) y sin los obstáculos con altura (lo duro: muros, columnas, barandas, vacíos)
  const gDuro = new Uint8Array(g);
  for (let k = 0; k < g.length; k++) { if (crudo[k]) gDuro[k] = g[k] = 1; else if (bajo[k]) g[k] = 1; }
  const umbral = ((radio + celda / 2) / celda) * 3;
  const final = inflar(g, nx, ny, umbral), duro = inflar(gDuro, nx, ny, umbral);
  const idx = (x, y) => { const i = Math.floor((x - x0) / celda), j = Math.floor((y - y0) / celda); return i < 0 || j < 0 || i >= nx || j >= ny ? -1 : j * nx + i; };
  const codigo = (x, y) => { const k = idx(x, y); return k < 0 ? 1 : final[k]; };
  const libre = (x, y) => codigo(x, y) !== 1;
  return {
    x0, y0, nx, ny, celda, radio, datos: final, crudo: g, duro, alto,
    codigo,
    libre,
    // movimiento con deslizamiento a lo largo de los muros (por ejes), en pasos de media celda
    mover([x, y], [dx, dy], puede = libre) {
      const n = Math.max(1, Math.ceil(Math.hypot(dx, dy) / (celda * 0.5)));
      const sx = dx / n, sy = dy / n;
      for (let k = 0; k < n; k++) {
        if (puede(x + sx, y + sy)) { x += sx; y += sy; continue; }
        if (sx && puede(x + sx, y)) { x += sx; continue; }
        if (sy && puede(x, y + sy)) { y += sy; continue; }
        break;
      }
      return [x, y];
    },
    // camino por la rejilla (A* con 8 vecinos) o null
    camino(a, b) {
      const ka = idx(a[0], a[1]), kb = idx(b[0], b[1]);
      if (ka < 0 || kb < 0 || final[ka] === 1 || final[kb] === 1) return null;
      const gS = new Float32Array(nx * ny).fill(Infinity), de = new Int32Array(nx * ny).fill(-1), cerrado = new Uint8Array(nx * ny);
      const bi = kb % nx, bj = (kb / nx) | 0, h = (k) => Math.hypot((k % nx) - bi, ((k / nx) | 0) - bj);
      const abierto = [ka]; gS[ka] = 0;
      const f = (k) => gS[k] + h(k);
      let it = 0;
      while (abierto.length && it++ < 400000) {
        let m = 0;
        for (let q = 1; q < abierto.length; q++) if (f(abierto[q]) < f(abierto[m])) m = q;
        const k = abierto.splice(m, 1)[0];
        if (k === kb) break;
        cerrado[k] = 1;
        const i = k % nx, j = (k / nx) | 0;
        for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
          if (!di && !dj) continue;
          const ii = i + di, jj = j + dj;
          if (ii < 0 || jj < 0 || ii >= nx || jj >= ny) continue;
          const kk = jj * nx + ii;
          if (cerrado[kk] || final[kk] === 1) continue;
          const c = gS[k] + (di && dj ? Math.SQRT2 : 1);
          if (c < gS[kk]) { if (gS[kk] === Infinity) abierto.push(kk); gS[kk] = c; de[kk] = k; }
        }
      }
      if (de[kb] < 0 && ka !== kb) return null;
      const out = [];
      for (let k = kb; k >= 0; k = de[k]) { out.push([x0 + ((k % nx) + 0.5) * celda, y0 + (((k / nx) | 0) + 0.5) * celda]); if (k === ka) break; }
      return out.reverse();
    },
    // celda libre más cercana a (x, y) dentro de un radio (búsqueda en anillos), o null
    cercana(x, y, maxR = 3, filtro = null) {
      const k0 = idx(x, y);
      if (k0 >= 0 && final[k0] !== 1 && (!filtro || filtro(x, y))) return [x, y];
      const i0 = Math.floor((x - x0) / celda), j0 = Math.floor((y - y0) / celda), R = Math.ceil(maxR / celda);
      for (let r = 1; r <= R; r++) {
        let mejor = null, dm = Infinity;
        for (let dj = -r; dj <= r; dj++) for (let di = -r; di <= r; di++) {
          if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
          const i = i0 + di, j = j0 + dj;
          if (i < 0 || j < 0 || i >= nx || j >= ny || final[j * nx + i] === 1) continue;
          const px = x0 + (i + 0.5) * celda, py = y0 + (j + 0.5) * celda;
          if (filtro && !filtro(px, py)) continue;
          const d = Math.hypot(px - x, py - y);
          if (d < dm) { dm = d; mejor = [px, py]; }
        }
        if (mejor) return mejor;
      }
      return null;
    },
  };
}
