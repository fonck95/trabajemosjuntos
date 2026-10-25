// Esquema 2D del despiece de un elemento (equipo F; especificación de integración 17.5): dos vistas en SVG acotadas al lado
// del 3D —la sección (con las barras cortadas como puntos y el estribo, la espiral o la malla que cae en el plano) y el
// alzado o la planta (con todas las barras proyectadas)—, las zonas del armado (confinamiento lo, 2h de las vigas, bordes de
// muros, cabeza del pilote, traslapos) y la lista de juegos con su etiqueta del despiece («16 N.º 8», «E N.º 4 c/0,10…»).
// El contorno del concreto sale del mismo corte de la geometría que la tapa del 3D (poligonosCorte de bim3d.js).
import { poligonosCorte } from './bim3d.js';
import { polilineas, familia, FAMILIAS } from './bim_refuerzo.js';

const COLOR = Object.fromEntries(FAMILIAS.map((f) => [f.id, f.color]));
const nf = (v, d = 2) => (Number.isFinite(+v) ? (+v).toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—');
const num = (s) => (s == null ? null : +String(s).replace(/\./g, '').replace(',', '.'));
const escS = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export function tipoDespiece(e) {
  if (e.clase === 'IfcColumn' || e.clase === 'IfcPile') return 'vertical';
  if (e.clase === 'IfcWall' && (e.tipo_predefinido === 'SHEAR' || e.objeto_tipo === 'RETAININGWALL')) return 'muro';
  if (e.clase === 'IfcBeam' || e.tipo_predefinido === 'FOOTING_BEAM') return 'viga';
  if (e.clase === 'IfcStair' || e.clase === 'IfcStairFlight') return 'escalera';
  return 'placa';
}

// vistas del elemento según su tipo: { titulo, corte, map(p) → [u, v], tipo: 'seccion' | 'proyeccion', filtro }
function vistas(e, caja, sols, juegos, opc) {
  const [x0, y0, z0, x1, y1, z1] = caja, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, t = tipoDespiece(e);
  const largoX = x1 - x0 >= y1 - y0;
  const zt = (z) => `${z >= 0 ? '+' : '−'}${nf(Math.abs(z), 2)}`;
  if (t === 'vertical') {
    let zc = e.clase === 'IfcPile' ? z1 - 1.0 : z0 + 0.3 * (z1 - z0), nota = '';
    if (e.clase === 'IfcColumn') {
      // la sección se corta donde solo están las barras de este piso: por encima del traslapo con las del piso de abajo
      // (en gris; con la convención del prediseño va a media altura de este piso) y por debajo del traslapo con las del
      // piso de arriba; si no hay tramo libre de 0,4 m, se rotula
      const { pmin, pmax, abajoMax, arribaMin } = alcanceBarras(z0, juegos, opc);
      const a = Math.max(z0, pmin, abajoMax), b = Math.min(z1, pmax, arribaMin);
      if (b - a >= 0.4) zc = (a + b) / 2;
      else nota = ' (en el traslapo: barras de este piso y, en gris, las del piso de abajo o de arriba)';
    }
    return [
      { titulo: `Sección horizontal a la cota ${zt(zc)} m${nota}`, corte: { tipo: 'h', c: zc }, map: (p) => [p[0], p[1]], tipo: 'seccion', ejes: ['x', 'y'] },
      { titulo: `Alzado (visto desde el sur${e.clase === 'IfcColumn' && (opc.contexto || []).length ? '; en gris, las barras de las columnas de abajo y de arriba' : ''})`, corte: { tipo: 'y', c: cy }, map: (p) => [p[0], p[2]], tipo: 'proyeccion', ejes: ['x', 'z'], recorteW: e.clase === 'IfcColumn' ? recorteColumna(z0, z1, juegos, opc) : null },
    ];
  }
  if (t === 'muro') {
    const zc = z0 + 0.4 * (z1 - z0);
    return [
      { titulo: `Sección horizontal a la cota ${zt(zc)} m`, corte: { tipo: 'h', c: zc }, map: largoX ? (p) => [p[0], p[1]] : (p) => [p[1], -p[0]], tipo: 'seccion' },
      { titulo: `Alzado del muro (visto desde el ${largoX ? 'sur' : 'occidente'})`, corte: largoX ? { tipo: 'y', c: cy } : { tipo: 'x', c: cx }, map: largoX ? (p) => [p[0], p[2]] : (p) => [p[1], p[2]], tipo: 'proyeccion' },
    ];
  }
  if (t === 'viga') {
    // la sección va a un tercio de la luz (fuera del centro exacto, donde puede caer un estribo justo en el plano)
    const c3 = largoX ? x0 + 0.37 * (x1 - x0) : y0 + 0.37 * (y1 - y0);
    return [
      { titulo: 'Sección transversal a un tercio de la luz', corte: largoX ? { tipo: 'x', c: c3 } : { tipo: 'y', c: c3 }, map: largoX ? (p) => [p[1], p[2]] : (p) => [p[0], p[2]], tipo: 'seccion' },
      { titulo: `Alzado de la viga (visto desde el ${largoX ? 'sur' : 'occidente'}; las barras corridas siguen a los otros tramos)`, corte: largoX ? { tipo: 'y', c: cy } : { tipo: 'x', c: cx }, map: largoX ? (p) => [p[0], p[2]] : (p) => [p[1], p[2]], tipo: 'proyeccion', recorteU: 0.9 },
    ];
  }
  if (t === 'escalera') {
    // el primer tramo manda: su alzado es el corte por el centro de su ancho; luego la planta de toda la escalera
    const f = opc.tramo || { u: [0, 1, 0], centro: [cx, cy] }, enY = Math.abs(f.u[1]) > 0.9;
    const filtro = (pts) => pts.every((q) => (enY ? Math.abs(q[0] - f.centro[0]) : Math.abs(q[1] - f.centro[1])) < (f.ancho || 1.3) / 2 + 0.05);
    return [
      { titulo: 'Corte por el primer tramo', corte: enY ? { tipo: 'x', c: f.centro[0] } : { tipo: 'y', c: f.centro[1] }, map: enY ? (p) => [p[1], p[2]] : (p) => [p[0], p[2]], tipo: 'proyeccion', filtro },
      { titulo: 'Planta de la escalera', corte: { tipo: 'h', c: z0 + 0.05 }, map: (p) => [p[0], p[1]], tipo: 'proyeccion' },
    ];
  }
  // placas: dados, losas de pilotes, losas, contrapiso, fosos y cisternas
  const zm = z0 + 0.5 * (z1 - z0);
  return [
    { titulo: `Planta (corte a la cota ${zt(zm)} m)`, corte: { tipo: 'h', c: zm }, map: (p) => [p[0], p[1]], tipo: 'proyeccion' },
    { titulo: 'Sección por el centro (vista desde el sur)', corte: { tipo: 'y', c: cy + 0.013 }, map: (p) => [p[0], p[2]], tipo: 'seccion' },
  ];
}

// alcance en z de las barras longitudinales de una columna y de las de contexto (columnas de abajo y de arriba)
function alcanceBarras(z0, juegos, opc) {
  let pmin = Infinity, pmax = -Infinity, abajoMax = -Infinity, arribaMin = Infinity;
  for (const j of juegos) if (familia(j.rol) === 'longitudinal') for (const pl of polilineas(j, opc.formas || [])) for (const q of pl) { pmin = Math.min(pmin, q[2]); pmax = Math.max(pmax, q[2]); }
  for (const c of opc.contexto || []) for (const j of c.juegos) {
    if (familia(j.rol) !== 'longitudinal') continue;
    for (const pl of polilineas(j, c.formas)) {
      const zs = pl.map((q) => q[2]), zmin = Math.min(...zs), zmax = Math.max(...zs);
      if (zmin < z0 - 0.05) abajoMax = Math.max(abajoMax, zmax);
      else if (zmin > z0 + 0.05) arribaMin = Math.min(arribaMin, zmin);
    }
  }
  return { pmin, pmax, abajoMax, arribaMin };
}
// ventana en altura del alzado de una columna: sus barras completas (de traslapo a traslapo) y un margen
function recorteColumna(z0, z1, juegos, opc) {
  const { pmin, pmax } = alcanceBarras(z0, juegos, opc);
  return [Math.min(z0, Number.isFinite(pmin) ? pmin : z0) - 0.35, Math.max(z1, Number.isFinite(pmax) ? pmax : z1) + 0.35];
}

// zonas del armado (intervalos en u o v de la vista de alzado) a partir del despiece y de los textos del prediseño
function zonas(e, caja, juegos, formas, vista, opc) {
  const [, , z0, , , z1] = caja, t = tipoDespiece(e), Z = [], txt = `${e.refuerzo_texto || ''} ${juegos.map((j) => j.etiqueta).join(' ')}`;
  if (t === 'vertical' && e.clase === 'IfcColumn') {
    const lo = num(txt.match(/lo = ([\d.,]+) m/)?.[1]);
    const zs = opc.zSofito ?? z1;
    if (lo) {
      Z.push({ eje: 'v', a: z0, b: z0 + lo, texto: `lo = ${nf(lo)} m (confinada)`, color: '#2471a3' });
      if (zs - lo > z0 + lo) Z.push({ eje: 'v', a: zs - lo, b: zs, texto: `lo = ${nf(lo)} m (confinada)`, color: '#2471a3' });
      if (z1 - zs > 0.05) Z.push({ eje: 'v', a: zs, b: z1, texto: 'nudo con las vigas', color: '#7d8a96' });
    }
    // traslapos: con el piso de abajo (sus barras, en gris, suben hasta aquí) y con el de arriba (las de este piso suben
    // hasta la mitad de su altura libre); si las barras de este piso arrancan en el de abajo, allí está su traslapo
    const { pmin, pmax, abajoMax, arribaMin } = alcanceBarras(z0, juegos, { ...opc, formas });
    if (pmin < z0 - 0.1) Z.push({ eje: 'v', a: pmin, b: z0, texto: 'arranque en el piso de abajo (traslapo en su mitad central)', color: '#c0392b' });
    else if (pmin > z0 + 0.1 && abajoMax > pmin) Z.push({ eje: 'v', a: pmin, b: Math.min(abajoMax, z1), texto: 'traslapo con las barras del piso de abajo', color: '#c0392b' });
    if (pmax > z1 + 0.1 && arribaMin < pmax) Z.push({ eje: 'v', a: Math.max(arribaMin, z1), b: pmax, texto: 'traslapo en la mitad central del piso de arriba', color: '#c0392b' });
  } else if (e.clase === 'IfcPile') {
    for (const j of juegos) if (j.param?.tramos) for (const tr of j.param.tramos) Z.push({ eje: 'v', a: tr.z0, b: tr.z1, texto: `espiral c/${nf(tr.paso, tr.paso < 0.1 ? 3 : 2)}`, color: '#2471a3' });
  } else if (t === 'viga') {
    const h2 = num(txt.match(/2h = ([\d.,]+) m/)?.[1]);
    const [u0, u1] = vista.rangoU;
    if (h2 && u1 - u0 > 2 * h2) { Z.push({ eje: 'u', a: u0, b: u0 + h2, texto: `2h = ${nf(h2)} m`, color: '#2471a3' }); Z.push({ eje: 'u', a: u1 - h2, b: u1, texto: `2h = ${nf(h2)} m`, color: '#2471a3' }); }
  } else if (t === 'muro') {
    for (const [rol, nom] of [['borde_i', 'borde i'], ['borde_j', 'borde j']]) {
      let a = Infinity, b = -Infinity;
      for (const j of juegos) if (j.rol === rol) for (const pl of polilineas(j, formas)) for (const q of pl) { const u = vista.map(q)[0]; a = Math.min(a, u); b = Math.max(b, u); }
      if (b > a) Z.push({ eje: 'u', a, b, texto: `elemento de ${nom}`, color: '#c0392b' });
    }
  }
  return Z;
}

// una vista en SVG: contorno del concreto, barras, cotas y zonas
const GRIS = '#9a9a95';
function svgVista(v, sols, juegos, formas, { ancho = 320, alto = 300, zonasDe, contexto = [] }) {
  const pols = poligonosCorte(sols, v.corte).map((pl) => pl.map(v.map));
  const dist = (p) => (v.corte.tipo === 'h' ? p[2] - v.corte.c : v.corte.tipo === 'x' ? p[0] - v.corte.c : p[1] - v.corte.c);
  const lineas = [], puntos = [];
  // las barras de contexto (columnas de abajo y de arriba) van primero y en gris: debajo de las del elemento
  const todos = [...contexto.flatMap((c) => c.juegos.map((j) => ({ j, formas: c.formas, gris: true }))), ...juegos.map((j) => ({ j, formas, gris: false }))];
  for (const { j, formas: fm, gris } of todos) {
    const col = gris ? GRIS : COLOR[familia(j.rol)], r = (j.db_mm || 12.7) / 2000;
    const pls = polilineas(j, fm);
    if (v.tipo === 'seccion' && j.param?.tipo === 'espiral' && v.corte.tipo === 'h') {
      // la espiral de un pilote, en una sección horizontal, es su anillo
      const P = j.param, en = P.tramos.some((t) => v.corte.c >= t.z0 && v.corte.c <= t.z1);
      if (en) lineas.push({ pts: Array.from({ length: 37 }, (_, i) => v.map([P.centro[0] + P.radio * Math.cos((i * Math.PI) / 18), P.centro[1] + P.radio * Math.sin((i * Math.PI) / 18), v.corte.c])), col, r });
      continue;
    }
    if (v.tipo === 'seccion') {
      // barras que cruzan el plano: un punto; barras que caen en el plano: la copia más cercana
      let mejor = null, dmin = Infinity;
      for (const pl of pls) {
        let cruza = false;
        for (let i = 0; i + 1 < pl.length; i++) {
          const da = dist(pl[i]), db = dist(pl[i + 1]);
          if ((da < 0) !== (db < 0) && Math.abs(da - db) > 1e-9) { const s = da / (da - db), q = pl[i].map((c, k) => c + s * (pl[i + 1][k] - c)); puntos.push({ uv: v.map(q), r, col }); cruza = true; }
        }
        if (cruza) continue;
        const m = pl.reduce((s, q) => Math.max(s, Math.abs(dist(q))), 0);
        if (m < dmin) { dmin = m; mejor = pl; }
      }
      if (mejor && dmin < 0.2) lineas.push({ pts: mejor.map(v.map), col, r });
    } else {
      for (const pl of pls) if (!v.filtro || v.filtro(pl)) lineas.push({ pts: pl.map(v.map), col, r });
    }
  }
  // recorte a lo largo: la ventana es el concreto del elemento con un margen (las barras que siguen se cortan en el borde)
  if (v.recorteU != null && pols.length) {
    const a = Math.min(...pols.flat().map((q) => q[0])) - v.recorteU, b = Math.max(...pols.flat().map((q) => q[0])) + v.recorteU;
    const dentro = [];
    for (const l of lineas) {
      let cur = [];
      for (let i = 0; i < l.pts.length; i++) {
        const p = l.pts[i], q = l.pts[i + 1];
        if (p[0] >= a && p[0] <= b) cur.push(p);
        if (!q) break;
        // cruces del tramo p-q con los bordes de la ventana
        for (const x of [a, b].filter((x) => (p[0] - x) * (q[0] - x) < 0).sort((m, k) => (q[0] > p[0] ? m - k : k - m))) {
          const t = (x - p[0]) / (q[0] - p[0]), m = [x, p[1] + t * (q[1] - p[1])];
          if (p[0] >= a && p[0] <= b) { cur.push(m); if (cur.length > 1) dentro.push({ ...l, pts: cur }); cur = []; } else cur = [m];
        }
      }
      if (cur.length > 1) dentro.push({ ...l, pts: cur });
    }
    lineas.length = 0; lineas.push(...dentro);
  }
  // recorte en altura (columnas): las barras de contexto y las que siguen se cortan en el borde de la ventana
  if (v.recorteW) {
    const [a, b] = v.recorteW, dentro = [];
    for (const l of lineas) {
      let cur = [];
      for (let i = 0; i < l.pts.length; i++) {
        const p = l.pts[i], q = l.pts[i + 1];
        if (p[1] >= a && p[1] <= b) cur.push(p);
        if (!q) break;
        for (const w of [a, b].filter((w) => (p[1] - w) * (q[1] - w) < 0).sort((m, k) => (q[1] > p[1] ? m - k : k - m))) {
          const t = (w - p[1]) / (q[1] - p[1]), m = [p[0] + t * (q[0] - p[0]), w];
          if (p[1] >= a && p[1] <= b) { cur.push(m); if (cur.length > 1) dentro.push({ ...l, pts: cur }); cur = []; } else cur = [m];
        }
      }
      if (cur.length > 1) dentro.push({ ...l, pts: cur });
    }
    lineas.length = 0; lineas.push(...dentro);
  }
  // límites de la vista: concreto y barras
  let u0 = Infinity, u1 = -Infinity, w0 = Infinity, w1 = -Infinity;
  const ext = ([u, w]) => { if (u < u0) u0 = u; if (u > u1) u1 = u; if (w < w0) w0 = w; if (w > w1) w1 = w; };
  pols.forEach((pl) => pl.forEach(ext)); lineas.forEach((l) => l.pts.forEach(ext)); puntos.forEach((p) => ext(p.uv));
  if (!(u1 > u0) || !(w1 > w0)) return { svg: '', rango: null };
  v.rangoU = [Math.min(...pols.flat().map((q) => q[0])), Math.max(...pols.flat().map((q) => q[0]))];
  const Z = zonasDe ? zonasDe(v) : [];
  const mI = 46, mD = Z.some((z) => z.eje === 'v') ? 118 : 14, mS = Z.some((z) => z.eje === 'u') ? 30 : 12, mB = 50;
  const s = Math.min((ancho - mI - mD) / (u1 - u0), (alto - mS - mB) / (w1 - w0), 900);
  const W = Math.round((u1 - u0) * s + mI + mD), Hh = Math.round((w1 - w0) * s + mS + mB);
  const X = (u) => +(mI + (u - u0) * s).toFixed(1), Y = (w) => +(mS + (w1 - w) * s).toFixed(1);
  const pts = (L) => L.map(([u, w]) => `${X(u)},${Y(w)}`).join(' ');
  let o = '';
  // concreto: relleno claro con su rayado de corte en las secciones
  for (const pl of pols) o += `<polygon points="${pts(pl)}" class="bd-conc${v.tipo === 'seccion' ? ' bd-cortado' : ''}"/>`;
  for (const l of lineas) o += `<polyline points="${pts(l.pts)}" fill="none" stroke="${l.col}" stroke-width="${Math.max(0.9, Math.min(2.6, 2 * l.r * s)).toFixed(2)}" stroke-linejoin="round" stroke-linecap="round"/>`;
  for (const p of puntos) o += `<circle cx="${X(p.uv[0])}" cy="${Y(p.uv[1])}" r="${Math.max(2, p.r * s).toFixed(2)}" fill="${p.col}" stroke="#1d1d1b" stroke-width="0.5"/>`;
  // cotas totales del concreto (abajo y a la izquierda)
  const [cu0, cu1] = v.rangoU, cw0 = Math.min(...pols.flat().map((q) => q[1])), cw1 = Math.max(...pols.flat().map((q) => q[1]));
  const yb = Hh - 30, xl = 14;
  o += `<g class="bd-cota"><line x1="${X(cu0)}" y1="${yb}" x2="${X(cu1)}" y2="${yb}"/><line x1="${X(cu0)}" y1="${yb - 4}" x2="${X(cu0)}" y2="${yb + 4}"/><line x1="${X(cu1)}" y1="${yb - 4}" x2="${X(cu1)}" y2="${yb + 4}"/><text x="${(X(cu0) + X(cu1)) / 2}" y="${yb - 4}" text-anchor="middle">${nf(cu1 - cu0)} m</text>`;
  o += `<line x1="${xl}" y1="${Y(cw0)}" x2="${xl}" y2="${Y(cw1)}"/><line x1="${xl - 4}" y1="${Y(cw0)}" x2="${xl + 4}" y2="${Y(cw0)}"/><line x1="${xl - 4}" y1="${Y(cw1)}" x2="${xl + 4}" y2="${Y(cw1)}"/><text x="${xl + 4}" y="${(Y(cw0) + Y(cw1)) / 2}" transform="rotate(-90 ${xl + 4} ${(Y(cw0) + Y(cw1)) / 2})" text-anchor="middle" dy="-6">${nf(cw1 - cw0)} m</text></g>`;
  // zonas: a la derecha (en altura) o arriba (a lo largo)
  let fila = 0;
  for (const z of Z) {
    if (z.eje === 'v') {
      const xr = Math.round((u1 - u0) * s + mI + 8 + (fila++ % 2) * 6), ya = Y(Math.min(z.b, w1)), yb2 = Y(Math.max(z.a, w0));
      o += `<g class="bd-zona" style="--c:${z.color}"><line x1="${xr}" y1="${ya}" x2="${xr}" y2="${yb2}"/><line x1="${xr - 3}" y1="${ya}" x2="${xr + 3}" y2="${ya}"/><line x1="${xr - 3}" y1="${yb2}" x2="${xr + 3}" y2="${yb2}"/>`;
      const lineasT = partir(z.texto, 18);
      lineasT.forEach((tl, i) => { o += `<text x="${xr + 6}" y="${(ya + yb2) / 2 + (i - (lineasT.length - 1) / 2) * 10 + 3}">${escS(tl)}</text>`; });
      o += '</g>';
    } else {
      const yt = 12 + (fila++ % 2) * 9, xa = X(Math.max(z.a, u0)), xb = X(Math.min(z.b, u1));
      o += `<g class="bd-zona" style="--c:${z.color}"><line x1="${xa}" y1="${yt}" x2="${xb}" y2="${yt}"/><line x1="${xa}" y1="${yt - 3}" x2="${xa}" y2="${yt + 3}"/><line x1="${xb}" y1="${yt - 3}" x2="${xb}" y2="${yt + 3}"/><text x="${(xa + xb) / 2}" y="${yt - 3}" text-anchor="middle">${escS(z.texto)}</text></g>`;
    }
  }
  // escala gráfica de 1 m (o de 0,5 m si la vista es pequeña)
  const em = s >= 140 ? 0.25 : s >= 60 ? 0.5 : 1;
  o += `<g class="bd-escala"><line x1="${W - 10 - em * s}" y1="${Hh - 6}" x2="${W - 10}" y2="${Hh - 6}"/><line x1="${W - 10 - em * s}" y1="${Hh - 9}" x2="${W - 10 - em * s}" y2="${Hh - 3}"/><line x1="${W - 10}" y1="${Hh - 9}" x2="${W - 10}" y2="${Hh - 3}"/><text x="${W - 14 - em * s}" y="${Hh - 3}" text-anchor="end">escala ${nf(em, em < 1 ? 2 : 0)} m</text></g>`;
  return { svg: `<svg class="bd-svg" viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}" role="img" aria-label="${escS(v.titulo)}">${o}</svg>`, puntos: puntos.length, lineas: lineas.length };
}
function partir(t, n) {
  const L = [], ps = String(t).split(' ');
  let a = '';
  for (const p of ps) { if ((a + ' ' + p).trim().length > n && a) { L.push(a); a = p; } else a = (a + ' ' + p).trim(); }
  if (a) L.push(a);
  return L;
}

// HTML del despiece: las dos vistas y la lista de juegos (agrupados por etiqueta) con su color
export function despiece(e, { caja, sols, juegos, formas, opc = {}, ancho = 320 }) {
  if (!juegos?.length) return '';
  const V = vistas(e, caja, sols, juegos, { ...opc, formas });
  const out = V.map((v) => {
    const t = tipoDespiece(e), conZonas = v.tipo === 'proyeccion' && t !== 'placa' && t !== 'escalera';
    const r = svgVista(v, sols, juegos, formas, { ancho, alto: v.tipo === 'seccion' && t !== 'placa' ? 250 : 320, contexto: opc.contexto || [], zonasDe: conZonas ? (vv) => zonas(e, caja, juegos, formas, vv, opc) : null });
    return { v, ...r };
  });
  // juegos agrupados por etiqueta y familia (lo que se lee en la obra)
  const grupos = new Map();
  for (const j of juegos) {
    const k = `${familia(j.rol)}|${j.etiqueta}`;
    const g = grupos.get(k) || { fam: familia(j.rol), etiqueta: j.etiqueta, tipo: j.tipo, n: 0, kg: 0, zona: j.zona, ganchos: j.ganchos };
    g.n += j.n || 1; g.kg += j.kg || 0; grupos.set(k, g);
    if (!g.zona && j.zona) g.zona = j.zona;
  }
  // kilos de este elemento y, en una viga, aparte los de las barras corridas de los otros tramos que pasan por ella
  const propios = juegos.filter((j) => !j.host || j.host === e.id);
  const kg = propios.reduce((s, j) => s + (j.kg || 0), 0), nb = propios.reduce((s, j) => s + (j.n || 1), 0);
  const kgT = juegos.reduce((s, j) => s + (j.kg || 0), 0);
  const total = propios.length < juegos.length
    ? `${nf(nb, 0)} barras y ${nf(kg, 0)} kg de acero de 420 MPa de este tramo (${nf(kgT, 0)} kg con las barras corridas de los otros tramos que pasan por él; cálculo propio con el despiece del prediseño).`
    : `${nf(nb, 0)} barras y ${nf(kg, 0)} kg de acero de 420 MPa en este elemento (cálculo propio con el despiece del prediseño).`;
  return `<div class="bd">${out.filter((o) => o.svg).map((o) => `<figure class="bd-fig"><figcaption>${escS(o.v.titulo)}</figcaption>${o.svg}</figure>`).join('')}
    <ul class="bd-juegos">${[...grupos.values()].map((g) => `<li><i style="background:${COLOR[g.fam]}"></i><span><b>${escS(g.etiqueta)}</b><small> · ${escS(g.tipo)}${g.zona ? ` · ${escS(g.zona)}` : ''}${g.ganchos ? ` · ganchos de ${escS(g.ganchos)}` : ''} · ${nf(g.n, 0)} barras, ${nf(g.kg, 0)} kg</small></span></li>`).join('')}</ul>
    <p class="note bd-total">${total}</p>${opc.notaDibujo ? `<p class="note bd-total">${escS(opc.notaDibujo)}</p>` : ''}</div>`;
}
