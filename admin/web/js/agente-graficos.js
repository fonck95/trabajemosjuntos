// Los gráficos del asistente en el chat (docs/agente.md, «Gráficos en el chat»): la acción `{tipo: 'grafico', …}`
// que arma el servidor con las cifras que calculó (app/agente/grafico.py; el modelo no escribe los números) y que
// vuelve con la herramienta al repintar una conversación guardada (`grafico` de su parte). El servidor ya la validó;
// aquí se vuelve a validar con el mismo contrato (lo que no cumple no se dibuja) y se dibuja con graficos.js, el módulo
// del Tablero: barras horizontales, columnas, una barra apilada o una serie en el tiempo (la clase `serie` generaliza
// `serieMensual` a cualquier periodo: días, semanas o meses). Los colores salen solo de la paleta `SERIES`; ningún
// texto del gráfico se pinta como HTML: el título y la nota entran con textContent, y lo demás por `html` de ui.js,
// que escapa todo. agente.js lo carga con el primer gráfico (graficos.js pone sus escuchas en `document` al cargarse).
//
// Forma (todo lo demás se descarta, como en el servidor):
//   {tipo: 'grafico', clase: 'barras' | 'columnas' | 'apilada' | 'serie', titulo (≤ 120), unidad (≤ 30),
//    items: [{etiqueta (≤ 60), valor (número ≥ 0), texto? (≤ 40)}] (1–60), nota? (≤ 200)}
import { SERIES, apilada, barras, columnas } from './graficos.js';
import { html, montar, num, periodo } from './ui.js';

const CLASES = new Set(['barras', 'columnas', 'apilada', 'serie']);
const MAX_ITEMS = 60;
const TITULO_MAX = 120, UNIDAD_MAX = 30, ETIQUETA_MAX = 60, TEXTO_MAX = 40, NOTA_MAX = 200;
// Los mismos caracteres que quita `grafico._CONTROL`: controles, separadores de línea, de ancho cero y de dirección
const CONTROL = /[\u0000-\u001f\u007f-\u009f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]/g;
// Columnas: con más ítems (o etiquetas más largas de lo que cabe bajo cada columna) se leen mejor como barras
const MAX_COLUMNAS = 12;
const ANCHO_COLUMNAS = 320;     // el ancho del dibujo de `columnas` (graficos.js), en sus unidades
const ANCHO_LETRA = 6.5;        // lo que ocupa una letra de 11,5 px en esas unidades, a ojo
// Apilada: una parte por color de la paleta; las que no caben van juntas en «Otras»
const MAX_PARTES = SERIES.length;

/** Un texto limpio como lo deja el servidor: sin controles ni invisibles, con los espacios juntos y recortado a `max`
 * puntos de código. null si no es una cadena o queda vacío. */
function limpio(v, max) {
  if (typeof v !== 'string') return null;
  const s = v.replace(CONTROL, ' ').split(/\s+/).filter(Boolean).join(' ');
  return s ? Array.from(s).slice(0, max).join('') : null;
}

/** El gráfico validado (el contrato de arriba), o null si no se puede dibujar: sin clase conocida, sin título o sin
 * ningún ítem válido. Un ítem sin etiqueta o con un valor que no es un número finito ≥ 0 se descarta (como en el
 * servidor); más de 60, se cortan. */
function validar(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || !CLASES.has(a.clase)) return null;
  const titulo = limpio(a.titulo, TITULO_MAX);
  const items = [];
  for (const it of Array.isArray(a.items) ? a.items : []) {
    if (!it || typeof it !== 'object' || Array.isArray(it)) continue;
    const etiqueta = limpio(it.etiqueta, ETIQUETA_MAX);
    const valor = it.valor;
    if (etiqueta === null || typeof valor !== 'number' || !Number.isFinite(valor) || valor < 0) continue;
    const x = { etiqueta, valor };
    const t = limpio(it.texto, TEXTO_MAX);
    if (t) x.texto = t;
    items.push(x);
    if (items.length >= MAX_ITEMS) break;
  }
  if (!titulo || !items.length) return null;
  return { clase: a.clase, titulo, unidad: limpio(a.unidad, UNIDAD_MAX) || '', items, nota: limpio(a.nota, NOTA_MAX) };
}

const valorDe = (it) => it.texto ?? num(it.valor);
const globo = (t, d) => html` data-gt="${t}" data-gd="${d}"`;

/** Una serie en el tiempo (área y línea, como `serieMensual` del Tablero), con cualquier periodo: la etiqueta de cada
 * punto es su periodo («2026-11-05», «2026-S46», «2026-11» se leen como fechas; lo demás, tal cual). Debajo, hasta seis
 * etiquetas repartidas (la primera y la última siempre); cada punto tiene su globo con la cifra. */
function serie(items, unidad, color = SERIES[0]) {
  const W = 640, H = 210, m = { t: 12, r: 14, b: 26, l: 46 };
  const n = items.length;
  const max = Math.max(...items.map((d) => d.valor));
  const paso = 10 ** Math.floor(Math.log10(max || 1));
  const tope = Math.ceil(max / paso) * paso || 1;
  const x = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r);
  const y = (v) => H - m.b - (v / tope) * (H - m.t - m.b);
  const linea = items.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d.valor).toFixed(1)}`).join('');
  const area = `${linea}L${x(n - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z`;
  const marcas = [0, tope / 2, tope];
  const cuantos = Math.min(6, n);
  const rotulos = [...new Set(Array.from({ length: cuantos }, (_, k) => Math.round((k * (n - 1)) / (cuantos - 1))))];
  const ancla = (i) => (i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle');
  const ancho = (W - m.l - m.r) / (n - 1);
  const ultimo = items[n - 1];
  const sufijo = unidad ? ` ${unidad}` : '';
  const nombre = `Serie en el tiempo${unidad ? ` de ${unidad}` : ''}`;
  return html`<div class="grafico"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${nombre}">
    ${marcas.map((v) => html`<line class="rejilla-l" x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/>
      <text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${num(v)}</text>`)}
    <line class="eje" x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}"/>
    ${rotulos.map((i) => html`<text x="${x(i)}" y="${H - 6}"
      text-anchor="${ancla(i)}">${periodo(items[i].etiqueta)}</text>`)}
    <path d="${area}" fill="${color}" fill-opacity=".1"/>
    <path d="${linea}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(n - 1)}" cy="${y(ultimo.valor)}" r="4" fill="${color}" stroke="var(--surface)" stroke-width="2"/>
    ${items.map((d, i) => html`<rect class="golpe" x="${x(i) - ancho / 2}" y="${m.t}" width="${ancho}"
      height="${H - m.t - m.b}" tabindex="-1"${globo(periodo(d.etiqueta), valorDe(d) + sufijo)}/>`)}
  </svg></div>`;
}

/** ¿Caben las etiquetas debajo de las columnas sin pisarse? */
const cabenColumnas = (items) => items.length <= MAX_COLUMNAS
  && items.every((it) => Array.from(it.etiqueta).length * ANCHO_LETRA <= ANCHO_COLUMNAS / items.length);

/** Las partes de la barra apilada: una por color; si hay más, las más chicas (las últimas) van juntas en «Otras». */
function partes(items) {
  const lista = items.length > MAX_PARTES
    ? [...items.slice(0, MAX_PARTES - 1),
      { etiqueta: 'Otras', valor: items.slice(MAX_PARTES - 1).reduce((s, it) => s + it.valor, 0) }]
    : items;
  return lista.map((it, i) => ({ etiqueta: it.etiqueta, valor: it.valor, color: SERIES[i % SERIES.length] }));
}

function dibujo(g) {
  const { clase, items, unidad } = g;
  if (clase === 'serie' && items.length >= 2) return serie(items, unidad);
  if (clase === 'apilada') return apilada(partes(items), { unidad });
  if (clase === 'columnas' && cabenColumnas(items)) return columnas(items, { color: SERIES[0], unidad });
  // barras, y lo que no cabe en su forma (columnas apretadas, una serie de un solo punto)
  return barras(items, { color: SERIES[0], unidad });
}

/** El gráfico `a` (la acción del servidor o el `grafico` de una herramienta al repintar) listo para ponerlo en la
 * conversación: un `<figure class="agente-grafico">` con el título, el dibujo, la nota y, para los lectores de
 * pantalla, las cifras en texto. null si no cumple el contrato: no se dibuja nada (el chip de la herramienta ya dice
 * qué se hizo). */
export function pintarGrafico(a) {
  const g = validar(a);
  if (!g) return null;
  const fig = document.createElement('figure');
  fig.className = 'agente-grafico';
  fig.dataset.clase = g.clase;
  const cab = document.createElement('figcaption');
  const titulo = document.createElement('b');
  titulo.textContent = g.titulo;
  cab.append(titulo);
  if (g.unidad) {
    const u = document.createElement('small');
    u.textContent = g.unidad;
    cab.append(' ', u);
  }
  const cuerpo = document.createElement('div');
  cuerpo.className = 'agente-grafico-cuerpo';
  montar(cuerpo, dibujo(g));
  // Las cifras en texto: el dibujo no se lee bien con un lector de pantalla (los globos salen con el puntero o el foco)
  const cifras = document.createElement('p');
  cifras.className = 'sr';
  const sufijo = g.unidad ? ` ${g.unidad}` : '';
  cifras.textContent = g.items.map((it) => `${it.etiqueta}: ${valorDe(it)}${sufijo}`).join('; ');
  fig.append(cab, cuerpo, cifras);
  if (g.nota) {
    const nota = document.createElement('p');
    nota.className = 'agente-grafico-nota';
    nota.textContent = g.nota;
    fig.append(nota);
  }
  return fig;
}
