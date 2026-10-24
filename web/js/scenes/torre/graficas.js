// Gráficas de la vista sísmica de la torre (equipo D; especificación de integración, 8.4). SVG con la clase
// svg.mr-chart, colores de los tokens del tema (var(--s1)…, var(--ink), var(--muted)), así siguen el tema claro u
// oscuro sin redibujar. Cada gráfica se dibuja a la medida de su contenedor (1 unidad del SVG = 1 px) y se vuelve a
// dibujar si cambia el ancho, para que el texto se lea igual en el teléfono y en escritorio.
// Todo lo que se dibuja sale del cálculo (Resultados del motor, 7.6, y los mensajes del 7.5): aquí no se calcula
// física, solo escalas, ejes y rótulos. Cada función devuelve { cursor(i), dispose() }: cursor(i) marca el paso de
// tiempo i del deslizador (o el punto del lazo, o el perfil de derivas de ese paso).
// Pasar el puntero (o el dedo) sobre una gráfica muestra los valores del punto más cercano; los mismos valores están
// en la tabla de variables y en la ficha, así que la lectura no depende del puntero.
import { escH } from './textos.js';

const NS = 'http://www.w3.org/2000/svg';
// orden fijo de colores por serie (paleta del sitio, validada para daltonismo en claro y oscuro: s1, s2, s3, s7, s5, s4)
const C = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s7)', 'var(--s5)', 'var(--s4)'];
const num = (v, d = 2) => (Number.isFinite(v) ? v.toLocaleString('es-CO', { maximumFractionDigits: d, minimumFractionDigits: 0 }) : '—');
// cifras significativas, con coma decimal y sin notación exponencial para lo que se lee en la tabla
export function sig(v, n = 3) {
  if (!Number.isFinite(v)) return '—';
  if (v === 0) return '0';
  const a = Math.abs(v), d = Math.max(0, n - 1 - Math.floor(Math.log10(a)));
  return v.toLocaleString('es-CO', { maximumFractionDigits: Math.min(8, d), minimumFractionDigits: 0 });
}
const fx = (v) => (Math.round(v * 10) / 10).toString();

// ---------------------------------------------------------------- escalas y marcas de los ejes
function pasoLindo(rango, n) {
  const bruto = rango / Math.max(1, n), p = Math.pow(10, Math.floor(Math.log10(bruto))), r = bruto / p;
  return (r >= 5 ? 10 : r >= 2 ? 5 : r >= 1 ? 2 : 1) * p;
}
function marcasLin(a, b, n = 5) {
  if (!(b > a)) { b = a + 1; }
  const p = pasoLindo(b - a, n), out = [];
  for (let v = Math.ceil(a / p) * p; v <= b + p * 1e-6; v += p) out.push(Math.abs(v) < p * 1e-9 ? 0 : v);
  return out;
}
function marcasLog(a, b) {
  const out = [];
  for (let e = Math.floor(Math.log10(a)); e <= Math.ceil(Math.log10(b)); e++) for (const m of [1, 2, 5]) { const v = m * 10 ** e; if (v >= a * 0.999 && v <= b * 1.001) out.push(v); }
  return out;
}
// rótulo de un valor de eje: sin ceros de más y con coma decimal
const rotulo = (v) => { const a = Math.abs(v); return a === 0 ? '0' : a >= 1000 ? num(v, 0) : a >= 1 ? num(v, 2) : sig(v, 1); };
const rangoDe = (arrs, simetrico = false) => {
  let lo = Infinity, hi = -Infinity;
  for (const a of arrs) if (a) for (let i = 0; i < a.length; i++) { const v = a[i]; if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
  if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
  if (simetrico) { const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1; return [-m, m]; }
  if (lo === hi) { lo -= 1; hi += 1; }
  return [lo, hi];
};

// ---------------------------------------------------------------- marco común: figura, título, SVG, leyenda y lectura
// arma la figura dentro de el; dibujar(svg, W, H) devuelve el contenido y deja en el objeto «g» lo que el cursor y la
// lectura necesitan (escala x, posiciones). Se redibuja con el ancho del contenedor
function marco(el, { titulo, nota, aria, leyenda = [], alto = 0.56, minAlto = 190, maxAlto = 280 }) {
  el.replaceChildren();
  const fig = document.createElement('figure');
  fig.className = 'sg';
  fig.innerHTML = `<figcaption><b>${titulo}</b>${nota ? `<span class="note">${nota}</span>` : ''}</figcaption><div class="sg-caja"><svg class="mr-chart" role="img" aria-label="${escH(aria || titulo)}"></svg><div class="sg-lectura" hidden></div></div>`;
  if (leyenda.length) {
    const ley = document.createElement('div');
    ley.className = 'legend sg-ley';
    leyenda.forEach((l) => {
      const s = document.createElement('span'), i = document.createElement('i');
      i.className = `sg-k ${l.forma || 'ln'}`;
      i.style.setProperty('--c', l.color);
      if (l.trazo) i.style.setProperty('--d', l.trazo);
      s.append(i, document.createTextNode(l.nombre));
      ley.append(s);
    });
    fig.append(ley);
  }
  el.append(fig);
  const svg = fig.querySelector('svg'), lect = fig.querySelector('.sg-lectura'), caja = fig.querySelector('.sg-caja');
  return { fig, svg, lect, caja, alto, minAlto, maxAlto };
}
// dibuja y vuelve a dibujar con el ancho; devuelve la función de limpieza
function medir(m, dibujar) {
  let W = 0, raf = 0;
  const hacer = () => {
    raf = 0;
    const w = Math.max(260, Math.round(m.caja.clientWidth || 320));
    if (w === W) return;
    W = w;
    const H = Math.round(Math.min(m.maxAlto, Math.max(m.minAlto, w * m.alto)));
    m.svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    m.svg.setAttribute('width', W); m.svg.setAttribute('height', H);
    dibujar(W, H);
  };
  hacer();
  const ro = new ResizeObserver(() => { if (!raf) raf = requestAnimationFrame(hacer); });
  ro.observe(m.caja);
  return () => { ro.disconnect(); if (raf) cancelAnimationFrame(raf); };
}
// ejes con su rejilla; devuelve el SVG del fondo
function ejes({ W, H, M, xs, ys, X, Y, xEt, yEt, xFmt = rotulo, yFmt = rotulo }) {
  let s = '';
  for (const v of ys) { const y = fx(Y(v)); s += `<line class="grid" x1="${M.l}" x2="${W - M.r}" y1="${y}" y2="${y}"/><text x="${M.l - 4}" y="${+y + 3}" text-anchor="end">${yFmt(v)}</text>`; }
  for (const v of xs) { const x = fx(X(v)); s += `<line class="grid sg-v" x1="${x}" x2="${x}" y1="${M.t}" y2="${H - M.b}"/><text x="${x}" y="${H - M.b + 12}" text-anchor="middle">${xFmt(v)}</text>`; }
  if (xEt) s += `<text x="${W - M.r}" y="${H - 3}" text-anchor="end" class="sg-et">${xEt}</text>`;
  if (yEt) s += `<text x="${M.l - 4}" y="${M.t - 6}" text-anchor="end" class="sg-et">${yEt}</text>`;
  return s;
}
// trazo de una serie; si hay más puntos que píxeles, se toma el mínimo y el máximo de cada columna de píxeles (no se
// pierden los picos)
function trazo(xv, yv, X, Y, n = Math.min(xv.length, yv.length), paso = 1) {
  if (!n) return '';
  const W = Math.abs(X(xv[n - 1]) - X(xv[0])) || 1;
  let d = '';
  if (n <= 2 * W) {
    for (let i = 0; i < n; i += paso) { const y = yv[i]; if (!Number.isFinite(y)) continue; d += `${d ? 'L' : 'M'}${fx(X(xv[i]))},${fx(Y(y))}`; }
    return d;
  }
  let col = -1, lo = 0, hi = 0, ilo = 0, ihi = 0;
  const emitir = () => { if (col < 0) return; const [a, b] = ilo <= ihi ? [lo, hi] : [hi, lo]; d += `${d ? 'L' : 'M'}${col},${fx(Y(a))}L${col},${fx(Y(b))}`; };
  for (let i = 0; i < n; i++) {
    const y = yv[i]; if (!Number.isFinite(y)) continue;
    const c = Math.round(X(xv[i]));
    if (c !== col) { emitir(); col = c; lo = hi = y; ilo = ihi = i; } else { if (y < lo) { lo = y; ilo = i; } if (y > hi) { hi = y; ihi = i; } }
  }
  emitir();
  return d;
}
const linea = (d, color, { ancho = 2, trazo: tr = '', clase = '' } = {}) => (d ? `<path d="${d}" class="${clase}" fill="none" stroke-linejoin="round" stroke-linecap="round" style="stroke:${color};stroke-width:${ancho}px${tr ? `;stroke-dasharray:${tr}` : ''}"/>` : '');
// índice del valor más cercano en un arreglo creciente
function cercano(xv, x) {
  let a = 0, b = xv.length - 1;
  if (b < 0) return -1;
  while (b - a > 1) { const m = (a + b) >> 1; if (xv[m] < x) a = m; else b = m; }
  return Math.abs(xv[a] - x) <= Math.abs(xv[b] - x) ? a : b;
}
// lectura con cruz: al mover el puntero sobre el área de la gráfica, línea vertical en el dato más cercano y una caja
// con los valores (texto con textContent: los nombres pueden venir de los datos)
function lectura(m, g, filas /* (i) => [[nombre, valor, color]] */, cabeza /* (i) => texto */) {
  const caja = m.caja, svg = m.svg, lect = m.lect;
  let cruz = null;
  const mover = (e) => {
    if (!g.X || !g.xv) return;
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * g.W;
    if (px < g.M.l - 4 || px > g.W - g.M.r + 4) { ocultar(); return; }
    const i = cercano(g.xv, g.Xinv(px));
    if (i < 0) return;
    if (!cruz || !cruz.isConnected) { cruz = document.createElementNS(NS, 'line'); cruz.setAttribute('class', 'sg-cruz'); svg.append(cruz); }
    const x = fx(g.X(g.xv[i]));
    cruz.setAttribute('x1', x); cruz.setAttribute('x2', x); cruz.setAttribute('y1', g.M.t); cruz.setAttribute('y2', g.H - g.M.b);
    lect.replaceChildren();
    const h = document.createElement('b'); h.textContent = cabeza(i); lect.append(h);
    for (const [n, v, c] of filas(i)) {
      const f = document.createElement('span'), k = document.createElement('i'), val = document.createElement('strong');
      k.style.setProperty('--c', c); val.textContent = v; f.append(k, val, document.createTextNode(` ${n}`)); lect.append(f);
    }
    lect.hidden = false;
    const izq = (+x / g.W) * caja.clientWidth;
    lect.style.left = `${Math.min(Math.max(4, izq + 10), caja.clientWidth - lect.offsetWidth - 4)}px`;
  };
  const ocultar = () => { lect.hidden = true; cruz?.remove(); cruz = null; };
  svg.addEventListener('pointermove', mover);
  svg.addEventListener('pointerdown', mover);
  svg.addEventListener('pointerleave', ocultar);
  return () => { svg.removeEventListener('pointermove', mover); svg.removeEventListener('pointerdown', mover); svg.removeEventListener('pointerleave', ocultar); };
}
// línea del cursor de tiempo (la reubica sin redibujar)
function cursorTiempo(m, g, t) {
  let i0 = 0;
  const poner = () => {
    let l = m.svg.querySelector('.now');
    if (!l) { l = document.createElementNS(NS, 'line'); l.setAttribute('class', 'now'); m.svg.append(l); }
    if (!g.X || !t?.length) return;
    const x = fx(g.X(t[Math.min(i0, t.length - 1)]));
    l.setAttribute('x1', x); l.setAttribute('x2', x); l.setAttribute('y1', g.M.t); l.setAttribute('y2', g.H - g.M.b);
  };
  return { poner, cursor(i) { i0 = Math.max(0, i | 0); poner(); } };
}
const linX = (a, b, p, q) => { const k = (q - p) / (b - a || 1); return [(v) => p + (v - a) * k, (x) => a + (x - p) / k]; };
const logX = (a, b, p, q) => { const la = Math.log10(a), k = (q - p) / (Math.log10(b) - la || 1); return [(v) => p + (Math.log10(Math.max(v, 1e-12)) - la) * k, (x) => 10 ** (la + (x - p) / k)]; };

// ---------------------------------------------------------------- serie de tiempo genérica (y el acelerograma)
// series: [{ nombre, y, color? }], referencias: [{ valor, etiqueta }] (líneas horizontales finas, p. ej. el cortante de
// diseño), unidad del eje y. Un solo eje: las series deben tener la misma unidad
export function serieTiempo(el, { t, series = [], referencias = [], unidad = '', titulo = 'Serie de tiempo', nota = '', aria, simetrico = true, dec = 2 } = {}) {
  const cols = series.map((s, k) => s.color || C[k % C.length]);
  const m = marco(el, { titulo, nota, aria, leyenda: [...series.map((s, k) => ({ nombre: s.nombre, color: cols[k] })), ...referencias.map((r) => ({ nombre: r.etiqueta, color: 'var(--muted)', trazo: '5 3' }))] });
  const g = { M: { l: 50, r: 10, t: 16, b: 22 } };
  const tc = cursorTiempo(m, g, t);
  const [y0, y1] = rangoDe([...series.map((s) => s.y), referencias.length ? referencias.flatMap((r) => (simetrico ? [r.valor, -r.valor] : [r.valor])) : null], simetrico);
  const fin = medir(m, (W, H) => {
    const M = g.M, n = t?.length || 0, tmax = n ? t[n - 1] : 1;
    [g.X, g.Xinv] = linX(0, tmax || 1, M.l, W - M.r);
    const [Y] = linX(y0 * 1.06, y1 * 1.06, H - M.b, M.t);
    Object.assign(g, { W, H, xv: t });
    let s = ejes({ W, H, M, xs: marcasLin(0, tmax || 1, Math.max(3, Math.round(W / 90))), ys: marcasLin(y0, y1, 4), X: g.X, Y, xEt: 's', yEt: unidad });
    for (const r of referencias) for (const v of simetrico ? [r.valor, -r.valor] : [r.valor]) if (Number.isFinite(v)) s += `<line x1="${M.l}" x2="${W - M.r}" y1="${fx(Y(v))}" y2="${fx(Y(v))}" style="stroke:var(--muted);stroke-width:1px;stroke-dasharray:5 3"/>`;
    s += `<line class="sg-cero" x1="${M.l}" x2="${W - M.r}" y1="${fx(Y(0))}" y2="${fx(Y(0))}"/>`;
    series.forEach((se, k) => { s += linea(trazo(t, se.y, g.X, Y), cols[k], { ancho: series.length > 2 ? 1.5 : 2 }); });
    m.svg.innerHTML = s;
    tc.poner();
  });
  const sinLect = lectura(m, g, (i) => series.map((se, k) => [se.nombre, `${num(se.y[i], dec)} ${unidad}`, cols[k]]), (i) => `t = ${num(t[i], 2)} s`);
  return { cursor: tc.cursor, dispose() { fin(); sinLect(); el.replaceChildren(); } };
}

export function acelerograma(el, { t, ax, ay, titulo = 'Aceleración del suelo', nota } = {}) {
  return serieTiempo(el, {
    t, unidad: 'm/s²', titulo, aria: 'Acelerograma: aceleración del suelo en x y en y contra el tiempo',
    nota: nota ?? 'Las dos componentes que movieron la base, ya giradas y escaladas, cada 0,02 s (1 g = 9,81 m/s²). La línea roja es el paso del deslizador.',
    series: [{ nombre: 'x (este)', y: ax }, { nombre: 'y (norte)', y: ay }],
  });
}

// ---------------------------------------------------------------- espectros de respuesta (log-log)
export function espectros(el, { T, sa_x, sa_y, nsr10 = {}, gmpe = [], marcas = [], titulo = 'Espectro de respuesta (5 % de amortiguamiento)', nota } = {}) {
  const Tn = nsr10.T || T;
  const ley = [
    { nombre: 'Este sismo, x', color: C[0] }, { nombre: 'Este sismo, y', color: C[1] },
    ...(nsr10.con_I ? [{ nombre: 'Diseño NSR-10 de Yondó (I = 1,5)', color: 'var(--ink)' }] : []),
    ...(nsr10.sin_I ? [{ nombre: 'Diseño sin I', color: 'var(--ink)', trazo: '6 3' }] : []),
    ...(nsr10.umbral_dano ? [{ nombre: 'Umbral de daño (Ad = 0,04)', color: 'var(--muted)', trazo: '2 3' }] : []),
    ...gmpe.map((g, k) => ({ nombre: `${g.nombre}${g.peso != null && g.peso < 1 ? ` (peso ${num(g.peso * 100, 0)} %)` : ''}: mediana ± 1σ`, color: C[2 + (k % 4)], forma: 'banda' })),
  ];
  const m = marco(el, { titulo, nota: nota ?? 'Cuánto se aceleraría un oscilador de cada período con este sismo, contra el espectro de diseño de la NSR-10 para Yondó y las ecuaciones empíricas (GMPE) del tipo de sismo. Marcas: períodos de los modos de la torre.', aria: 'Espectros de respuesta del sismo contra la norma y las GMPE', leyenda: ley });
  const g = { M: { l: 50, r: 12, t: 16, b: 24 } };
  const vals = [sa_x, sa_y, nsr10.con_I, nsr10.sin_I, nsr10.umbral_dano, ...gmpe.flatMap((q) => [Array.from(q.mediana || q.mediana_g || [], (v, i) => v * Math.exp(-(q.sigma?.[i] ?? q.sigma_ln?.[i] ?? 0))), Array.from(q.mediana || q.mediana_g || [], (v, i) => v * Math.exp(q.sigma?.[i] ?? q.sigma_ln?.[i] ?? 0))])];
  let lo = Infinity, hi = 0;
  vals.forEach((a) => a && Array.from(a).forEach((v) => { if (v > 0) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (!(hi > 0)) { lo = 0.001; hi = 1; }
  const yA = 10 ** Math.floor(Math.log10(Math.max(lo, hi / 1e4))), yB = 10 ** Math.ceil(Math.log10(hi));
  const tA = Math.min(...[T?.[0], Tn?.[0]].filter((v) => v > 0), 0.02), tB = Math.max(T?.[T.length - 1] || 0, Tn?.[Tn.length - 1] || 0, 4);
  const fin = medir(m, (W, H) => {
    const M = g.M;
    [g.X, g.Xinv] = logX(tA, tB, M.l, W - M.r);
    const [Y] = logX(yA, yB, H - M.b, M.t);
    Object.assign(g, { W, H, xv: T });
    const ys = marcasLog(yA, yB).filter((v) => /^[15]/.test(String(v)) || yB / yA < 1e3);
    let s = ejes({ W, H, M, xs: marcasLog(tA, tB).filter((v) => W > 420 || /^[15]/.test(String(v))), ys, X: g.X, Y, xEt: 'período T (s)', yEt: 'Sa (g)' });
    const pos = (xv, yv) => { const xs = [], vs = []; for (let i = 0; i < Math.min(xv.length, yv.length); i++) if (xv[i] > 0 && yv[i] > 0) { xs.push(xv[i]); vs.push(yv[i]); } return [xs, vs]; };
    gmpe.forEach((q, k) => {
      const med = q.mediana || q.mediana_g || [], sg = q.sigma || q.sigma_ln || [], col = C[2 + (k % 4)];
      const [xs, md] = pos(q.T, med);
      if (!xs.length) return;
      const off = (q.T.length - xs.length);
      const sup = xs.map((x, i) => [g.X(x), Y(md[i] * Math.exp(sg[i + off] || 0))]), inf = xs.map((x, i) => [g.X(x), Y(md[i] * Math.exp(-(sg[i + off] || 0)))]);
      s += `<path d="M${[...sup, ...inf.reverse()].map(([a, b]) => `${fx(a)},${fx(b)}`).join('L')}Z" style="fill:${col};opacity:0.12;stroke:none"/>`;
      s += linea(xs.map((x, i) => `${i ? 'L' : 'M'}${fx(g.X(x))},${fx(Y(md[i]))}`).join(''), col, { ancho: 1.5, trazo: '1 3' });
      xs.forEach((x, i) => { s += `<circle cx="${fx(g.X(x))}" cy="${fx(Y(md[i]))}" r="3.5" style="fill:${col};stroke:var(--surface);stroke-width:1.5px"/>`; });
    });
    if (nsr10.umbral_dano) { const [a, b] = pos(Tn, nsr10.umbral_dano); s += linea(trazo(a, b, g.X, Y), 'var(--muted)', { ancho: 1.5, trazo: '2 3' }); }
    if (nsr10.sin_I) { const [a, b] = pos(Tn, nsr10.sin_I); s += linea(trazo(a, b, g.X, Y), 'var(--ink)', { ancho: 1.5, trazo: '6 3' }); }
    if (nsr10.con_I) { const [a, b] = pos(Tn, nsr10.con_I); s += linea(trazo(a, b, g.X, Y), 'var(--ink)', { ancho: 1.5 }); }
    if (T && sa_x) { const [a, b] = pos(T, sa_x); s += linea(trazo(a, b, g.X, Y), C[0]); }
    if (T && sa_y) { const [a, b] = pos(T, sa_y); s += linea(trazo(a, b, g.X, Y), C[1]); }
    marcas.filter((q) => q.T >= tA && q.T <= tB).forEach((q, k) => {
      const x = fx(g.X(q.T));
      s += `<line x1="${x}" x2="${x}" y1="${M.t}" y2="${H - M.b}" style="stroke:var(--ink);stroke-width:1px;opacity:0.45"/><text x="${+x + 3}" y="${M.t + 9 + (k % 3) * 11}" class="sg-et">${escH(q.etiqueta)}</text>`;
    });
    m.svg.innerHTML = s;
  });
  const interp = (xv, yv, x) => { if (!xv || !yv) return NaN; const i = cercano(xv, x); return yv[i]; };
  const sinLect = lectura(m, g, (i) => {
    const Ti = T[i], f = [['Sa x', `${sig(sa_x?.[i], 3)} g`, C[0]], ['Sa y', `${sig(sa_y?.[i], 3)} g`, C[1]]];
    if (nsr10.con_I) f.push(['NSR-10 (I = 1,5)', `${sig(interp(Tn, nsr10.con_I, Ti), 3)} g`, 'var(--ink)']);
    if (nsr10.umbral_dano) f.push(['umbral de daño', `${sig(interp(Tn, nsr10.umbral_dano, Ti), 3)} g`, 'var(--muted)']);
    return f;
  }, (i) => `T = ${sig(T[i], 3)} s`);
  return { cursor() {}, dispose() { fin(); sinLect(); el.replaceChildren(); } };
}

// espectro de Fourier (log-log) de las dos componentes; si el motor entrega el objetivo de Boore, se dibuja encima
export function fourier(el, { f, A_x, A_y, objetivo = null, titulo = 'Espectro de Fourier del acelerograma', nota } = {}) {
  const ley = [{ nombre: 'x', color: C[0] }, { nombre: 'y', color: C[1] }, ...(objetivo ? [{ nombre: 'Objetivo del método de Boore (suelo)', color: 'var(--ink)', trazo: '6 3' }] : [])];
  const m = marco(el, { titulo, nota: nota ?? 'Cómo se reparte la energía del sismo por frecuencia: los sismos grandes y lejanos tienen más contenido en frecuencias bajas.', aria: 'Espectro de Fourier del acelerograma', leyenda: ley });
  const g = { M: { l: 50, r: 12, t: 16, b: 24 } };
  let lo = Infinity, hi = 0;
  [A_x, A_y, objetivo].forEach((a) => a && Array.from(a).forEach((v) => { if (v > 0) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (!(hi > 0)) { lo = 1e-3; hi = 1; }
  const yA = 10 ** Math.floor(Math.log10(Math.max(lo, hi / 1e5))), yB = 10 ** Math.ceil(Math.log10(hi));
  const fA = Math.max(0.05, f?.find((v) => v > 0) || 0.1), fB = Math.max(f?.[f.length - 1] || 25, fA * 10);
  const fin = medir(m, (W, H) => {
    const M = g.M;
    [g.X, g.Xinv] = logX(fA, fB, M.l, W - M.r);
    const [Y] = logX(yA, yB, H - M.b, M.t);
    Object.assign(g, { W, H, xv: f });
    let s = ejes({ W, H, M, xs: marcasLog(fA, fB).filter((v) => /^[15]/.test(String(v)) || W > 520), ys: marcasLog(yA, yB).filter((v) => /^1/.test(String(v))), X: g.X, Y, xEt: 'frecuencia (Hz)', yEt: 'amplitud (m/s)' });
    const pos = (yv) => { const xs = [], vs = []; for (let i = 0; i < f.length; i++) if (f[i] > 0 && yv[i] > 0) { xs.push(f[i]); vs.push(yv[i]); } return [xs, vs]; };
    if (A_x) s += linea(trazo(...pos(A_x), g.X, Y), C[0], { ancho: 1.5 });
    if (A_y) s += linea(trazo(...pos(A_y), g.X, Y), C[1], { ancho: 1.5 });
    if (objetivo) s += linea(trazo(...pos(objetivo), g.X, Y), 'var(--ink)', { ancho: 1.5, trazo: '6 3' });
    m.svg.innerHTML = s;
  });
  const sinLect = lectura(m, g, (i) => [['x', `${sig(A_x?.[i], 3)} m/s`, C[0]], ['y', `${sig(A_y?.[i], 3)} m/s`, C[1]]], (i) => `f = ${sig(f[i], 3)} Hz`);
  return { cursor() {}, dispose() { fin(); sinLect(); el.replaceChildren(); } };
}

// ---------------------------------------------------------------- derivas por entrepiso
// x, y, vector: envolventes por entrepiso (cociente: 0,01 = 1 %); paso(i) → deriva vectorial de cada entrepiso en el
// paso i (la del deslizador); limite 1 %, umbral 0,4 % y, con mampostería adherida, 0,2 %
export function derivas(el, { pisos, x, y, vector, paso = null, limite = 0.01, umbral = 0.004, umbral_mamposteria = 0.002, mamposteria = false, titulo = 'Deriva por entrepiso', nota } = {}) {
  const N = vector?.length || 0;
  const et = pisos || Array.from({ length: N }, (_, k) => `${k + 1}`);
  const ley = [
    { nombre: 'Vectorial en las esquinas (la que se compara), máxima', color: C[0], forma: 'pt' },
    { nombre: 'Componente x, máxima', color: C[1], trazo: '5 3' }, { nombre: 'Componente y, máxima', color: C[2], trazo: '5 3' },
    ...(paso ? [{ nombre: 'En el paso del deslizador', color: 'var(--ink)', forma: 'pt' }] : []),
    { nombre: 'Límites: 1 % y 0,4 %', color: 'var(--bad)', trazo: '6 3' },
  ];
  const m = marco(el, { titulo, nota: nota ?? `1 % es el límite para el sismo de diseño; 0,4 % para el sismo pequeño y frecuente del umbral de daño${mamposteria ? ' (0,2 % con mampostería adherida)' : ''}; la deriva se mide en las esquinas, donde la torsión la hace mayor.`, aria: 'Deriva máxima de cada entrepiso contra los límites de la NSR-10', leyenda: ley, alto: 0.5, minAlto: 170, maxAlto: 260 });
  const g = { M: { l: 64, r: 14, t: 14, b: 24 } };
  let actual = null;
  const xmax = Math.max(limite * 1.1, ...Array.from(vector || []), ...Array.from(x || []), ...Array.from(y || [])) * 1.08;
  const dib = { Y: null, X: null };
  const fin = medir(m, (W, H) => {
    const M = g.M;
    const [X] = linX(0, xmax, M.l, W - M.r);
    const fila = (H - M.t - M.b) / Math.max(1, N), Y = (k) => H - M.b - fila * (k + 0.5);
    Object.assign(dib, { X, Y });
    let s = '';
    for (const v of marcasLin(0, xmax, Math.max(3, Math.round(W / 80)))) { const xx = fx(X(v)); s += `<line class="grid sg-v" x1="${xx}" x2="${xx}" y1="${M.t}" y2="${H - M.b}"/><text x="${xx}" y="${H - M.b + 12}" text-anchor="middle">${num(v * 100, 2)}</text>`; }
    s += `<text x="${W - M.r}" y="${H - 2}" text-anchor="end" class="sg-et">deriva (%)</text>`;
    for (let k = 0; k < N; k++) s += `<line class="grid" x1="${M.l}" x2="${W - M.r}" y1="${fx(Y(k))}" y2="${fx(Y(k))}"/><text x="${M.l - 6}" y="${fx(Y(k) + 3)}" text-anchor="end">${escH(et[k])}</text>`;
    const lim = [[limite, '1 %'], [umbral, '0,4 %'], ...(mamposteria ? [[umbral_mamposteria, '0,2 %']] : [])];
    lim.forEach(([v, t]) => { const xx = fx(X(v)); s += `<line x1="${xx}" x2="${xx}" y1="${M.t - 4}" y2="${H - M.b}" style="stroke:var(--bad);stroke-width:1.5px;stroke-dasharray:6 3;opacity:0.85"/><text x="${+xx - 3}" y="${M.t - 4}" text-anchor="end" class="sg-et">${t}</text>`; });
    const perfil = (a) => Array.from({ length: N }, (_, k) => `${k ? 'L' : 'M'}${fx(X(a[k] || 0))},${fx(Y(k))}`).join('');
    if (x) s += linea(perfil(x), C[1], { ancho: 1.5, trazo: '5 3' });
    if (y) s += linea(perfil(y), C[2], { ancho: 1.5, trazo: '5 3' });
    if (vector) { s += linea(perfil(vector), C[0]); for (let k = 0; k < N; k++) s += `<circle cx="${fx(X(vector[k]))}" cy="${fx(Y(k))}" r="4.5" style="fill:${C[0]};stroke:var(--surface);stroke-width:2px"/>`; }
    s += '<g class="sg-paso"></g>';
    m.svg.innerHTML = s;
    pintarPaso();
  });
  function pintarPaso() {
    const gp = m.svg.querySelector('.sg-paso');
    if (!gp || !paso || actual == null || !dib.X) return;
    const a = paso(actual);
    if (!a) { gp.innerHTML = ''; return; }
    gp.innerHTML = linea(Array.from({ length: N }, (_, k) => `${k ? 'L' : 'M'}${fx(dib.X(a[k] || 0))},${fx(dib.Y(k))}`).join(''), 'var(--ink)', { ancho: 1.5 })
      + Array.from({ length: N }, (_, k) => `<circle cx="${fx(dib.X(a[k] || 0))}" cy="${fx(dib.Y(k))}" r="4" style="fill:var(--ink);stroke:var(--surface);stroke-width:2px"/>`).join('');
  }
  // lectura por entrepiso: el puntero elige la fila más cercana
  const mover = (e) => {
    if (!dib.Y) return;
    const r = m.svg.getBoundingClientRect(), py = ((e.clientY - r.top) / r.height) * (+m.svg.getAttribute('height') || 200);
    let k = 0, best = Infinity;
    for (let q = 0; q < N; q++) { const d = Math.abs(dib.Y(q) - py); if (d < best) { best = d; k = q; } }
    m.lect.replaceChildren();
    const h = document.createElement('b'); h.textContent = `Entrepiso ${et[k]}`; m.lect.append(h);
    const filas = [['vectorial máx.', vector?.[k], C[0]], ['x máx.', x?.[k], C[1]], ['y máx.', y?.[k], C[2]]];
    if (paso && actual != null) filas.push(['en este paso', paso(actual)?.[k], 'var(--ink)']);
    for (const [n, v, c] of filas) { const f = document.createElement('span'), kk = document.createElement('i'), val = document.createElement('strong'); kk.style.setProperty('--c', c); val.textContent = `${num((v || 0) * 100, 3)} %`; f.append(kk, val, document.createTextNode(` ${n}`)); m.lect.append(f); }
    m.lect.hidden = false; m.lect.style.left = '60px';
  };
  const ocultar = () => { m.lect.hidden = true; };
  m.svg.addEventListener('pointermove', mover); m.svg.addEventListener('pointerdown', mover); m.svg.addEventListener('pointerleave', ocultar);
  return {
    cursor(i) { actual = i; pintarPaso(); },
    dispose() { fin(); m.svg.removeEventListener('pointermove', mover); m.svg.removeEventListener('pointerdown', mover); m.svg.removeEventListener('pointerleave', ocultar); el.replaceChildren(); },
  };
}

// ---------------------------------------------------------------- balance de energía (áreas apiladas)
// las cuatro energías que la estructura guarda o disipa se apilan sobre cero; el trabajo de P-Delta (negativo: energía
// que la gravedad entrega a la estructura deformada) va bajo cero; la entrada, como línea. El error es la diferencia
export function energia(el, { t, entrada, cinetica, elastica, amortiguada, histeretica, pdelta, titulo = 'Balance de energía', nota } = {}) {
  const capas = [['Cinética', cinetica, C[0]], ['Elástica', elastica, C[1]], ['Amortiguada', amortiguada, C[2]], ['Histerética (rótulas)', histeretica, C[3]]].filter(([, a]) => a);
  const n = t?.length || 0;
  let err = 0, emax = 0;
  for (let i = 0; i < n; i++) {
    const s = capas.reduce((a, [, v]) => a + (v[i] || 0), 0) + (pdelta?.[i] || 0);
    emax = Math.max(emax, Math.abs(entrada?.[i] || 0));
    err = Math.max(err, Math.abs((entrada?.[i] || 0) - s));
  }
  const errPct = emax > 0 ? (100 * err) / emax : 0;
  const m = marco(el, {
    titulo, aria: 'Balance de energía del sismo en la estructura',
    nota: nota ?? `La energía que entra con el sismo se reparte entre movimiento (cinética), deformación elástica, amortiguamiento y daño en las rótulas (histerética); el trabajo de P-Delta va bajo cero. Error del balance: ${num(errPct, 2)} % del máximo de la entrada.`,
    leyenda: [...capas.map(([nm, , c]) => ({ nombre: nm, color: c, forma: 'banda' })), ...(pdelta ? [{ nombre: 'Trabajo de P-Delta', color: C[4], forma: 'banda' }] : []), { nombre: 'Entrada', color: 'var(--ink)' }],
  });
  const g = { M: { l: 50, r: 10, t: 16, b: 22 } };
  const tc = cursorTiempo(m, g, t);
  let top = 0, bot = 0;
  for (let i = 0; i < n; i++) { const s = capas.reduce((a, [, v]) => a + Math.max(0, v[i] || 0), 0); top = Math.max(top, s, entrada?.[i] || 0); bot = Math.min(bot, pdelta?.[i] || 0); }
  if (!(top > 0)) top = 1;
  const fin = medir(m, (W, H) => {
    const M = g.M, tmax = n ? t[n - 1] : 1;
    [g.X, g.Xinv] = linX(0, tmax || 1, M.l, W - M.r);
    const [Y] = linX(bot * 1.08, top * 1.06, H - M.b, M.t);
    Object.assign(g, { W, H, xv: t });
    let s = ejes({ W, H, M, xs: marcasLin(0, tmax || 1, Math.max(3, Math.round(W / 90))), ys: marcasLin(bot, top, 4), X: g.X, Y, xEt: 's', yEt: 'kJ' });
    const paso = Math.max(1, Math.ceil(n / (W - M.l - M.r)));
    const idx = []; for (let i = 0; i < n; i += paso) idx.push(i); if (n && idx[idx.length - 1] !== n - 1) idx.push(n - 1);
    const base = new Float64Array(idx.length);
    for (const [, v, c] of capas) {
      const sup = idx.map((i, q) => base[q] + Math.max(0, v[i] || 0));
      const d = `M${idx.map((i, q) => `${fx(g.X(t[i]))},${fx(Y(sup[q]))}`).join('L')}L${idx.map((i, q) => [i, q]).reverse().map(([i, q]) => `${fx(g.X(t[i]))},${fx(Y(base[q]))}`).join('L')}Z`;
      s += `<path d="${d}" style="fill:${c};opacity:0.55;stroke:var(--surface);stroke-width:0.75px"/>`;
      sup.forEach((v2, q) => { base[q] = v2; });
    }
    if (pdelta) s += `<path d="M${idx.map((i) => `${fx(g.X(t[i]))},${fx(Y(Math.min(0, pdelta[i] || 0)))}`).join('L')}L${fx(g.X(t[idx[idx.length - 1]]))},${fx(Y(0))}L${fx(g.X(t[0]))},${fx(Y(0))}Z" style="fill:${C[4]};opacity:0.55"/>`;
    s += `<line class="sg-cero" x1="${M.l}" x2="${W - M.r}" y1="${fx(Y(0))}" y2="${fx(Y(0))}"/>`;
    if (entrada) s += linea(trazo(t, entrada, g.X, Y), 'var(--ink)', { ancho: 2 });
    m.svg.innerHTML = s;
    tc.poner();
  });
  const sinLect = lectura(m, g, (i) => [['entrada', `${num(entrada?.[i], 2)} kJ`, 'var(--ink)'], ...capas.map(([nm, v, c]) => [nm.toLowerCase(), `${num(v[i], 2)} kJ`, c]), ...(pdelta ? [['P-Delta', `${num(pdelta[i], 2)} kJ`, C[4]]] : [])], (i) => `t = ${num(t[i], 2)} s`);
  return { cursor: tc.cursor, error_pct: errPct, dispose() { fin(); sinLect(); el.replaceChildren(); } };
}

// ---------------------------------------------------------------- lazo de histéresis M–θp de las rótulas de un elemento
// lazos: [{ nombre, theta (rad), M (kN·m) }] (o theta y M sueltos); My: momento de fluencia esperado; limites: IO, LS y CP
// en rad de rotación plástica. cursor(i) marca el punto del paso i en cada lazo
export function histeresis(el, { lazos, theta, M, My = null, limites = {}, titulo = 'Lazo de histéresis M–θp', nota, sinFluencia = '' } = {}) {
  const L = (lazos || [{ nombre: 'rótula', theta, M }]).filter((q) => q.theta && q.M);
  const tieneFlujo = L.some((q) => Array.from(q.theta).some((v) => Math.abs(v) > 1e-7));
  const lim = [['IO', limites.IO, 'var(--warn)'], ['LS', limites.LS, 'var(--s2)'], ['CP', limites.CP, 'var(--bad)']].filter(([, v]) => v > 0);
  const m = marco(el, {
    titulo, aria: 'Lazo de histéresis de las rótulas del elemento seleccionado',
    nota: nota ?? (tieneFlujo ? 'Momento en el extremo contra la rotación plástica de su rótula. El área del lazo es la energía que disipa el daño. Marcas: ocupación inmediata (IO), seguridad de la vida (LS) y prevención del colapso (CP).' : (sinFluencia || 'Este elemento no fluyó: su rotación plástica fue cero en todo el sismo (no hay lazo). Toca otro elemento en el modelo para ver el suyo.')),
    leyenda: [...L.map((q, k) => ({ nombre: q.nombre, color: C[k % C.length] })), ...lim.map(([n, , c]) => ({ nombre: `θp de ${n}`, color: c, trazo: '6 3' })), ...(My ? [{ nombre: 'My esperado', color: 'var(--muted)', trazo: '2 3' }] : [])],
    alto: 0.62,
  });
  const g = { M: { l: 54, r: 12, t: 16, b: 24 } };
  let actual = null;
  const xr = Math.max(1e-4, ...L.map((q) => Math.max(...Array.from(q.theta, Math.abs))), tieneFlujo ? (limites.IO || 0) * 1.1 : 0);
  const yr = Math.max(1, ...L.map((q) => Math.max(...Array.from(q.M, Math.abs))), My ? My * 1.05 : 0);
  const fin = medir(m, (W, H) => {
    const M0 = g.M;
    [g.X] = linX(-xr * 1.08, xr * 1.08, M0.l, W - M0.r);
    const [Y] = linX(-yr * 1.08, yr * 1.08, H - M0.b, M0.t);
    Object.assign(g, { W, H, Y });
    let s = ejes({ W, H, M: M0, xs: marcasLin(-xr, xr, Math.max(3, Math.round(W / 90))), ys: marcasLin(-yr, yr, 4), X: g.X, Y, xEt: 'θp (rad)', yEt: 'M (kN·m)', xFmt: (v) => sig(v, 2) });
    s += `<line class="sg-cero" x1="${M0.l}" x2="${W - M0.r}" y1="${fx(Y(0))}" y2="${fx(Y(0))}"/><line class="sg-cero" x1="${fx(g.X(0))}" x2="${fx(g.X(0))}" y1="${M0.t}" y2="${H - M0.b}"/>`;
    for (const [n, v, c] of lim) for (const sg of [-1, 1]) { const xx = g.X(sg * v); if (xx < M0.l || xx > W - M0.r) continue; s += `<line x1="${fx(xx)}" x2="${fx(xx)}" y1="${M0.t}" y2="${H - M0.b}" style="stroke:${c};stroke-width:1.5px;stroke-dasharray:6 3"/>${sg > 0 ? `<text x="${fx(xx + 3)}" y="${M0.t + 9}" class="sg-et">${n}</text>` : ''}`; }
    if (My) for (const sg of [-1, 1]) s += `<line x1="${M0.l}" x2="${W - M0.r}" y1="${fx(Y(sg * My))}" y2="${fx(Y(sg * My))}" style="stroke:var(--muted);stroke-width:1px;stroke-dasharray:2 3"/>`;
    L.forEach((q, k) => { s += linea(Array.from(q.theta, (v, i) => `${i ? 'L' : 'M'}${fx(g.X(v))},${fx(Y(q.M[i]))}`).join(''), C[k % C.length], { ancho: 1.75 }); });
    s += '<g class="sg-paso"></g>';
    m.svg.innerHTML = s;
    pintar();
  });
  function pintar() {
    const gp = m.svg.querySelector('.sg-paso');
    if (!gp || actual == null || !g.Y) return;
    gp.innerHTML = L.map((q, k) => { const i = Math.min(actual, q.theta.length - 1); return `<circle cx="${fx(g.X(q.theta[i]))}" cy="${fx(g.Y(q.M[i]))}" r="5" style="fill:${C[k % C.length]};stroke:var(--surface);stroke-width:2px"/>`; }).join('');
  }
  return { cursor(i) { actual = i; pintar(); }, dispose() { fin(); el.replaceChildren(); } };
}
