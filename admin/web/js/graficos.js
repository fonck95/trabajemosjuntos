// Gráficos del tablero en SVG/HTML, sin librerías. Marcas finas, extremos redondeados de 4px, separación de 2px,
// rejilla tenue, un solo eje y globo de información al pasar el puntero (también con teclado vía foco).
// Todo pasa por `html`, que escapa: los colores son variables CSS o hexadecimales del código y no cambian al escaparse.
import { RANGOS_EDAD } from './modelo.js';
import { html, mesCorto, num } from './ui.js';

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

const g = (t, d = '') => html` data-gt="${t}" data-gd="${d}"`;

// ───────── Lista de barras horizontales (ranking) ─────────
export function barras(items, { color = 'var(--s1)', total, enlace, unidad = 'personas' } = {}) {
  if (!items.length) return html`<div class="vacio">Sin datos todavía</div>`;
  const max = Math.max(...items.map((i) => i.valor), 1);
  return html`<div class="lista-barras">${items.map((i) => {
    const pc = total ? ` · ${Math.round((i.valor / total) * 100)} %` : '';
    const ancho = Math.max(1, (i.valor / max) * 100);
    const cuerpo = html`<span>${i.etiqueta}</span><span><span class="b" style="width:${ancho.toFixed(1)}%;background:${i.color || color}"></span></span><span class="n">${i.texto ?? num(i.valor)}</span>`;
    const href = enlace?.(i);
    return href
      ? html`<a class="f" href="${href}" data-ruta tabindex="0"${g(i.etiqueta, (i.texto ?? num(i.valor)) + ' ' + unidad + pc)}>${cuerpo}</a>`
      : html`<div class="f" tabindex="0"${g(i.etiqueta, (i.texto ?? num(i.valor)) + pc)}>${cuerpo}</div>`;
  })}</div>`;
}

// ───────── Barra apilada (partes de un todo) con leyenda ─────────
export function apilada(partes, { unidad = 'personas', enlace } = {}) {
  const total = partes.reduce((a, p) => a + p.valor, 0) || 1;
  const visibles = partes.filter((p) => p.valor > 0);
  return html`<div class="apilada" role="img" aria-label="${visibles.map((p) => `${p.etiqueta}: ${p.valor}`).join(', ')}">
      ${visibles.map((p) => html`<span tabindex="0" style="flex:${p.valor} 0 0;background:${p.color}"${g(p.etiqueta, `${num(p.valor)} ${unidad} · ${Math.round((p.valor / total) * 100)} %`)}></span>`)}
    </div>
    <div class="leyenda">${partes.map((p) => {
      const cuerpo = html`<i style="background:${p.color}"></i>${p.etiqueta} <b>${Math.round((p.valor / total) * 100)} %</b>`;
      const href = enlace?.(p);
      return href ? html`<a href="${href}" data-ruta>${cuerpo}</a>` : html`<span>${cuerpo}</span>`;
    })}</div>`;
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
    <path d="${area}" fill="${color}" fill-opacity=".1"/>
    <path d="${linea}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(datos.length - 1)}" cy="${y(ultimo.n)}" r="4" fill="${color}" stroke="var(--surface)" stroke-width="2"/>
    ${datos.map((d, i) => html`<rect class="golpe" x="${x(i) - ancho / 2}" y="${m.t}" width="${ancho}" height="${H - m.t - m.b}" tabindex="-1"${g(mesCorto(d.mes), `${num(d.n)} ${unidad}`)}/>`)}
  </svg></div>`;
}

// ───────── Pirámide de edades (mujeres a la izquierda, hombres a la derecha, sin sexo en gris) ─────────
// `filas` = [{rango, sexo, n}] con sexo F, M o sin dato; `rangos` de menor a mayor (arriba van los mayores).
// `enlace(rango, sexo)` hace de cada barra un enlace a Habitantes con ese filtro.
export function piramide(filas, rangos = RANGOS_EDAD, { enlace } = {}) {
  if (!filas.length) return html`<div class="vacio">Sin edades registradas</div>`;
  const sinSexo = (s) => s !== 'F' && s !== 'M';
  const v = (r, s) => filas.filter((f) => f.rango === r && (s === 'sin' ? sinSexo(f.sexo) && f.sexo !== 'N' : f.sexo === s)).reduce((a, f) => a + (f.n || 0), 0);
  const orden = [...rangos].reverse();
  const max = Math.max(1, ...orden.flatMap((r) => [v(r, 'F'), v(r, 'M'), v(r, 'sin')]));
  const hayGris = orden.some((r) => v(r, 'sin') > 0);
  const barra = (r, s, n, clase0, texto) => {
    const clase = n ? clase0 : `${clase0} cero`;
    const cuerpo = html`<span class="barra-p ${clase}" style="width:${((n / max) * 100).toFixed(1)}%"></span>`;
    const href = n && enlace ? enlace(r, s) : null;
    return href ? html`<a class="celda-p ${clase}" href="${href}" data-ruta${g(texto, num(n) + ' personas')}>${cuerpo}<span class="sec">${num(n)}</span></a>`
      : html`<span class="celda-p ${clase}" tabindex="0"${g(texto, num(n) + ' personas')}>${cuerpo}<span class="sec">${num(n)}</span></span>`;
  };
  return html`<div class="grafico piramide ${hayGris ? 'con-gris' : ''}">
    ${orden.map((r) => html`${barra(r, 'F', v(r, 'F'), 'mujeres', `Mujeres ${r} años`)}<div class="rango-p">${r}</div>${barra(r, 'M', v(r, 'M'), 'hombres', `Hombres ${r} años`)}${hayGris ? barra(r, 'sin', v(r, 'sin'), 'sin-sexo', `Sin sexo registrado, ${r} años`) : ''}`)}
  </div><div class="leyenda"><span><i style="background:var(--s2)"></i>Mujeres</span><span><i style="background:var(--s1)"></i>Hombres</span>${hayGris ? html`<span><i style="background:var(--axis)"></i>Sin sexo</span>` : ''}</div>`;
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
      return html`<path d="${d}" fill="${it.color || color}" tabindex="0"${g(it.etiqueta, `${num(it.valor)} ${unidad}`)}/>
        <text class="valor" x="${cx}" y="${y0 - 5}" text-anchor="middle">${num(it.valor)}</text>
        <text x="${cx}" y="${H - 6}" text-anchor="middle">${it.etiqueta}</text>`;
    })}
  </svg></div>`;
}

// ───────── Medidor de un indicador (proporción) ─────────
export const medidor = (valor, total) => html`<div class="medidor"><i style="width:${total ? Math.min(100, (valor / total) * 100).toFixed(1) : 0}%"></i></div>`;
