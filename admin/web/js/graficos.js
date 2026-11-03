// Gráficos del tablero en SVG/HTML, sin librerías. Marcas finas, extremos redondeados de 4px, separación de 2px,
// rejilla tenue, un solo eje y globo de información al pasar el puntero (también con teclado vía foco).
import { esc, html, mesCorto, num, crudo } from './ui.js';

export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)'];

// ───────── Globo compartido ─────────
let globo;
function mostrar(e, el) {
  if (!globo) {
    globo = document.createElement('div');
    globo.className = 'globo';
    document.body.append(globo);
  }
  globo.replaceChildren();
  const b = document.createElement('b');
  b.textContent = el.dataset.gt || '';
  globo.append(b);
  if (el.dataset.gd) {
    for (const linea of el.dataset.gd.split('\n')) {
      globo.append(document.createElement('br'), document.createTextNode(linea));
    }
  }
  globo.style.display = 'block';
  const r = el.getBoundingClientRect();
  const x = e?.clientX ?? r.left + r.width / 2, y = e?.clientY ?? r.top;
  const gw = globo.offsetWidth, gh = globo.offsetHeight;
  globo.style.left = Math.min(innerWidth - gw - 8, Math.max(8, x + 14)) + 'px';
  globo.style.top = Math.max(8, y - gh - 12) + 'px';
}
const ocultar = () => { if (globo) globo.style.display = 'none'; };
document.addEventListener('pointermove', (e) => {
  const el = e.target.closest?.('[data-gt]');
  if (el) mostrar(e, el); else ocultar();
});
document.addEventListener('focusin', (e) => { const el = e.target.closest?.('[data-gt]'); if (el) mostrar(null, el); });
document.addEventListener('focusout', ocultar);
document.addEventListener('scroll', ocultar, true);

const g = (t, d = '') => crudo(` data-gt="${esc(t)}" data-gd="${esc(d)}"`);

// ───────── Lista de barras horizontales (ranking) ─────────
export function barras(items, { color = 'var(--s1)', total, enlace } = {}) {
  if (!items.length) return html`<div class="vacio">Sin datos todavía</div>`;
  const max = Math.max(...items.map((i) => i.valor), 1);
  return html`<div class="lista-barras">${items.map((i) => {
    const pc = total ? ` · ${Math.round((i.valor / total) * 100)} %` : '';
    const ancho = Math.max(1, (i.valor / max) * 100);
    const cuerpo = html`<span>${i.etiqueta}</span><span><span class="b" style="width:${ancho.toFixed(1)}%;background:${crudo(i.color || color)}"></span></span><span class="n">${num(i.valor)}</span>`;
    const href = enlace?.(i);
    return href
      ? html`<a class="f" href="${href}" data-ruta tabindex="0"${g(i.etiqueta, num(i.valor) + ' personas' + pc)}>${cuerpo}</a>`
      : html`<div class="f" tabindex="0"${g(i.etiqueta, num(i.valor) + pc)}>${cuerpo}</div>`;
  })}</div>`;
}

// ───────── Barra apilada (partes de un todo) con leyenda ─────────
export function apilada(partes, { unidad = 'personas' } = {}) {
  const total = partes.reduce((a, p) => a + p.valor, 0) || 1;
  const visibles = partes.filter((p) => p.valor > 0);
  return html`<div class="apilada" role="img" aria-label="${visibles.map((p) => `${p.etiqueta}: ${p.valor}`).join(', ')}">
      ${visibles.map((p) => html`<span tabindex="0" style="flex:${p.valor} 0 0;background:${crudo(p.color)}"${g(p.etiqueta, `${num(p.valor)} ${unidad} · ${Math.round((p.valor / total) * 100)} %`)}></span>`)}
    </div>
    <div class="leyenda">${partes.map((p) => html`<span><i style="background:${crudo(p.color)}"></i>${p.etiqueta} <b>${Math.round((p.valor / total) * 100)} %</b></span>`)}</div>`;
}

// ───────── Serie mensual (área + línea) con retícula y globo ─────────
export function serieMensual(datos, { alto = 200, color = 'var(--s1)', unidad = 'trámites' } = {}) {
  if (datos.length < 2) return html`<div class="vacio">Sin suficientes datos</div>`;
  const W = 640, H = alto, m = { t: 12, r: 12, b: 26, l: 40 };
  const max = Math.max(...datos.map((d) => d.n));
  const paso = Math.pow(10, Math.floor(Math.log10(max || 1)));
  const tope = Math.ceil(max / paso) * paso || 1;
  const x = (i) => m.l + (i / (datos.length - 1)) * (W - m.l - m.r);
  const y = (v) => H - m.b - (v / tope) * (H - m.t - m.b);
  const linea = datos.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d.n).toFixed(1)}`).join('');
  const area = `${linea}L${x(datos.length - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z`;
  const marcas = [0, tope / 2, tope];
  const etiquetasX = datos.map((d, i) => [d, i]).filter(([d], i) => d.mes.endsWith('-01') || i === 0);
  const ancho = (W - m.l - m.r) / (datos.length - 1);
  const ultimo = datos[datos.length - 1];
  return html`<div class="grafico"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Serie mensual de ${unidad}">
    ${marcas.map((v) => html`<line class="rejilla-l" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${num(v)}</text>`)}
    <line class="eje" x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}"/>
    ${etiquetasX.map(([d, i]) => html`<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${d.mes.slice(0, 4)}</text>`)}
    <path d="${area}" fill="${crudo(color)}" fill-opacity=".1"/>
    <path d="${linea}" fill="none" stroke="${crudo(color)}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(datos.length - 1)}" cy="${y(ultimo.n)}" r="4" fill="${crudo(color)}" stroke="var(--surface)" stroke-width="2"/>
    ${datos.map((d, i) => html`<rect class="golpe" x="${x(i) - ancho / 2}" y="${m.t}" width="${ancho}" height="${H - m.t - m.b}" tabindex="-1"${g(mesCorto(d.mes), `${num(d.n)} ${unidad}`)}/>`)}
  </svg></div>`;
}

// ───────── Pirámide de edades (mujeres a la izquierda, hombres a la derecha) ─────────
export function piramide(filas) {
  const rangos = ['60+', '41-59', '29-40', '18-28', '0-17'];
  const v = (r, s) => filas.find((f) => f.rango === r && f.sexo === s)?.n || 0;
  const max = Math.max(1, ...filas.map((f) => f.n));
  if (!filas.length) return html`<div class="vacio">Sin edades registradas</div>`;
  return html`<div class="grafico" style="display:grid;grid-template-columns:1fr 54px 1fr;gap:6px 8px;align-items:center;font-size:12.5px">
    ${rangos.map((r) => {
      const f = v(r, 'F'), mm = v(r, 'M');
      return html`<div style="display:flex;justify-content:flex-end;align-items:center;gap:6px"><span class="sec">${num(f)}</span><span tabindex="0" style="height:14px;width:${(f / max) * 100}%;min-width:2px;background:var(--s2);border-radius:4px 0 0 4px"${g(`Mujeres ${r} años`, num(f) + ' personas')}></span></div>
        <div style="text-align:center;font-weight:650">${r}</div>
        <div style="display:flex;align-items:center;gap:6px"><span tabindex="0" style="height:14px;width:${(mm / max) * 100}%;min-width:2px;background:var(--s1);border-radius:0 4px 4px 0"${g(`Hombres ${r} años`, num(mm) + ' personas')}></span><span class="sec">${num(mm)}</span></div>`;
    })}
  </div><div class="leyenda"><span><i style="background:var(--s2)"></i>Mujeres</span><span><i style="background:var(--s1)"></i>Hombres</span></div>`;
}

// ───────── Columnas (histograma corto) ─────────
export function columnas(items, { color = 'var(--s1)', alto = 150, unidad = 'personas' } = {}) {
  const W = 320, H = alto, base = H - 22, max = Math.max(1, ...items.map((i) => i.valor));
  const banda = W / items.length, ancho = Math.min(24 * 1.6, banda * 0.55);
  return html`<div class="grafico"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Histograma">
    <line class="eje" x1="0" x2="${W}" y1="${base}" y2="${base}"/>
    ${items.map((it, i) => {
      const h = Math.max(2, (it.valor / max) * (base - 18));
      const cx = banda * i + banda / 2, x0 = cx - ancho / 2, y0 = base - h, rr = Math.min(4, h / 2);
      const d = `M${x0},${base}V${y0 + rr}Q${x0},${y0} ${x0 + rr},${y0}H${x0 + ancho - rr}Q${x0 + ancho},${y0} ${x0 + ancho},${y0 + rr}V${base}Z`;
      return html`<path d="${d}" fill="${crudo(it.color || color)}" tabindex="0"${g(it.etiqueta, `${num(it.valor)} ${unidad}`)}/>
        <text class="valor" x="${cx}" y="${y0 - 5}" text-anchor="middle">${num(it.valor)}</text>
        <text x="${cx}" y="${H - 6}" text-anchor="middle">${it.etiqueta}</text>`;
    })}
  </svg></div>`;
}

// ───────── Medidor de un indicador (proporción) ─────────
export const medidor = (valor, total) => html`<div class="medidor"><i style="width:${total ? Math.min(100, (valor / total) * 100).toFixed(1) : 0}%"></i></div>`;
