// Presentación de la propuesta integral Yondó 2028–2031. Capítulos (portada, siete áreas, financiación, hoja de ruta y
// lo que se pide al nivel central) y pasos dentro de cada capítulo. Cada paso cambia el panel con GSAP, mueve la cámara
// sobre el territorio real y muestra las capas 3D de ese paso. El contenido sale de data/propuesta.json (generado desde
// data/propuesta/ por scripts/build_data.py); lo 3D de cada módulo vive en js/propuesta/modulos/<id>.js.
import { gsap, reducedMotion, countUp } from '../core.js';
import { crearEscena } from './escena.js';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const pres = $('#pres'), cab = $('.panel-cab'), cuerpo = $('.panel-cuerpo'), riel = $('.riel'), puntos = $('.puntos');
const progreso = $('.progreso'), telon = $('.telon'), indice = $('.indice'), fichas = $('.fichas'), leyenda = $('.leyenda3d');
const ICONOS = {
  portada: '<path d="M4 20V9l8-5 8 5v11M9 20v-6h6v6" />',
  vivienda: '<path d="M3 11l9-7 9 7M5 10v10h14V10M10 20v-5h4v5" />',
  urbanismo: '<path d="M4 20c3-8 13-8 16 0M12 4v8M8 8l4-4 4 4M3 20h18" />',
  agroindustria: '<path d="M4 20V10l5 3V9l5 3V7l6 4v9zM3 20h18" />',
  salud: '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />',
  aguas: '<path d="M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z" />',
  saneamiento: '<path d="M4 7h16l-2 13H6zM9 7V4h6v3M9 11v5M15 11v5" />',
  tic: '<path d="M5 12a10 10 0 0 1 14 0M8 15a5.5 5.5 0 0 1 8 0M12 19h.01M2 9a14.5 14.5 0 0 1 20 0" />',
  financiacion: '<path d="M4 20h16M6 16V10M10 16V6M14 16v-4M18 16V8" />',
  ruta: '<path d="M4 6h10M4 12h16M4 18h7M17 4v4M20 10v4M14 16v4" />',
  pedidos: '<path d="M4 4h16v12H8l-4 4zM8 9h8M8 12h5" />',
};
const icono = (id) => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">${ICONOS[id] || ICONOS.portada}</svg>`;
const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
// millones de pesos de 2026 → texto corto («$77,0 mil M», «$850 M»)
export const fmtM = (v) => {
  if (v == null || Number.isNaN(+v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e6) return `$${(v / 1e6).toLocaleString('es-CO', { maximumFractionDigits: 2 })} billones`;
  if (a >= 1000) return `$${(v / 1000).toLocaleString('es-CO', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} mil M`;
  return `$${Math.round(v).toLocaleString('es-CO')} M`;
};
const colorDe = (id) => `var(--m-${id})`;
// Los costos son de perfil o prefactibilidad: se muestran como umbral tentativo, no como cifra fija.
// Dos cifras significativas (una estimación de perfil no pretende más precisión).
const cifra2 = (v) => { if (!v) return 0; const k = 10 ** (Math.floor(Math.log10(Math.abs(v))) - 1); return Math.round(v / k) * k; };
// rango aproximado en millones de 2026 («$54 – 100 mil M»); si mínimo y máximo coinciden, valor aproximado («≈ $77 mil M»)
export const fmtRango = (min, max) => {
  if (min == null || max == null || Number.isNaN(+min) || Number.isNaN(+max)) return '—';
  const a = cifra2(Math.min(min, max)), b = cifra2(Math.max(min, max));
  if (a === b) return `≈ ${fmtM(b)}`;
  const u = b >= 1e6 ? [1e6, ' billones', 2] : b >= 1000 ? [1000, ' mil M', 1] : [1, ' M', 0];
  const n = (x) => (x / u[0]).toLocaleString('es-CO', { maximumFractionDigits: u[2] });
  return `$${n(a)} – ${n(b)}${u[1]}`;
};
// rango de un objeto {min, central, max}
export const rg = (c) => (c ? fmtRango(c.min ?? c.central, c.max ?? c.central) : '—');
// valor suelto (sin rango en los datos) como aproximación
export const aprox = (v) => (v == null ? '' : `≈ ${fmtM(cifra2(v))}`);
const leer = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const guardar = (k, v) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } };

// ---------------------------------------------------------------- tema
const TEMA = 'propuesta-tema';
const temaGuardado = leer(TEMA);
if (temaGuardado) document.documentElement.dataset.theme = temaGuardado;
function cambiarTema() {
  const oscuro = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const nuevo = oscuro ? 'light' : 'dark';
  document.documentElement.dataset.theme = nuevo; guardar(TEMA, nuevo);
}

// ---------------------------------------------------------------- datos y capítulos
const datos = await fetch(new URL('../../data/propuesta.json', import.meta.url)).then((r) => { if (!r.ok) throw new Error(`data/propuesta.json (${r.status})`); return r.json(); });
const caps = [
  { id: 'portada', nombre: 'Portada', corto: 'Portada', ...datos.portada },
  ...datos.modulos.map((m, i) => ({ ...m, modulo: true })),
  { id: 'financiacion', nombre: 'Cómo se financia', corto: 'Financiación', ...datos.financiacion },
  { id: 'ruta', nombre: 'Hoja de ruta', corto: 'Ruta', ...datos.ruta },
  { id: 'pedidos', nombre: 'Lo que pedimos', corto: 'Pedidos', ...datos.pedidos },
];
caps.forEach((c) => { c.pasos = (c.pasos || []).filter(Boolean); if (!c.pasos.length) c.pasos = [{ id: 'inicio', tipo: 'texto', titulo: c.nombre }]; });
const totalPasos = caps.reduce((a, c) => a + c.pasos.length, 0);
const inversionTotal = datos.modulos.reduce((a, m) => a + (m.inversion?.central || 0), 0);
const inversionMin = datos.modulos.reduce((a, m) => a + (m.inversion?.min ?? m.inversion?.central ?? 0), 0);
const inversionMax = datos.modulos.reduce((a, m) => a + (m.inversion?.max ?? m.inversion?.central ?? 0), 0);
const rgTotal = () => fmtRango(inversionMin, inversionMax);

// riel e índice
riel.innerHTML = caps.map((c, i) => `${i === 1 || i === caps.length - 3 ? '<span class="sep" aria-hidden="true"></span>' : ''}<button type="button" data-cap="${i}" style="--mc:${colorDe(c.id)}" aria-label="${esc(c.nombre)}">${icono(c.id)}<span class="tip">${esc(c.nombre)}</span></button>`).join('');
$('.rejilla', indice).innerHTML = caps.map((c, i) => `<button type="button" class="tarjeta" data-cap="${i}" style="--mc:${colorDe(c.id)}"><span class="n">${icono(c.id)}</span><b>${esc(c.nombre)}</b><span>${esc(c.lema || c.subtitulo || '')}</span>${c.inversion ? `<em>${rg(c.inversion)}</em>` : ''}</button>`).join('');
progreso.innerHTML = caps.map((c) => `<i style="--mc:${colorDe(c.id)};--k:${c.pasos.length}"><b></b></i>`).join('');

// ---------------------------------------------------------------- escena 3D y módulos
const escena = crearEscena($('#escena'), datos);
$('.cargando')?.remove();
escena.st.start();
const ctx3d = {};      // id de capítulo → { pasos: { id: { capas, vista, animar } }, vista }
const cargas = caps.map(async (c) => {
  try {
    const mod = await import(`./modulos/${c.id}.js`);
    ctx3d[c.id] = await mod.crear(escena, datos, c);
  } catch (e) {
    if (!/Failed to fetch|Importing a module|error loading|404/i.test(String(e))) console.warn(`3D de ${c.id}`, e);
  }
});

// ---------------------------------------------------------------- panel
const madurezPasos = ['Idea', 'Perfil', 'Prefactibilidad', 'Factibilidad', 'Diseños', 'Radicado'];
// con guiones blandos para que las palabras largas partan en las celdas angostas
const madurezRotulos = { Prefactibilidad: 'Pre\u00adfacti\u00adbilidad', Factibilidad: 'Facti\u00adbilidad' };
function cifras(lista = [], cls = '') {
  if (!lista.length) return '';
  return `<div class="cifras ${cls}">${lista.map((c) => `<div class="cifra ${c.tono || ''} ${c.ancha ? 'ancha' : ''}"><b data-cuenta>${esc(c.v)}</b><span>${esc(c.l)}</span>${c.fuente ? `<small>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.fuente)}</a>` : esc(c.fuente)}</small>` : ''}</div>`).join('')}</div>`;
}
function chipsFuentes(ids = []) {
  const F = datos.financiacion?.fuentes || [];
  return `<div class="chips">${ids.map((id) => { const f = F.find((x) => x.id === id) || { nombre: id }; return `<span class="chip" style="--c:${f.color || 'var(--muted)'}" title="${esc(f.entidad || '')}">${esc(f.corto || f.nombre)}</span>`; }).join('')}</div>`;
}
function chipsTipo(lista = []) {
  if (!lista.length) return '';
  return `<div class="chips">${lista.map((t) => (t.url ? `<a class="chip tipo" href="${esc(t.url)}" target="_blank" rel="noopener" title="Proyecto tipo del DNP">${esc(t.nombre)}</a>` : `<span class="chip tipo">${esc(t.nombre)}</span>`)).join('')}</div>`;
}
// paso que desarrolla un componente: el que lo nombra o, para «mirador_proteccion», el de otro «mirador_…» (−1 si no hay)
function pasoDeComp(c, id) {
  const k = c.pasos.findIndex((x) => x.componente === id);
  if (k >= 0 || !id.includes('_')) return k;
  const pre = `${id.split('_')[0]}_`;
  return c.pasos.findIndex((x) => x.componente?.startsWith(pre));
}
function rango(c) {
  if (!c?.central) return '';
  const max = c.max || c.central, min = c.min || c.central, top = max * 1.05;
  return `<div class="rango"><div class="eje"><i style="left:${(min / top) * 100}%;width:${((max - min) / top) * 100}%"></i></div><div class="lbls"><span>${fmtM(cifra2(min))}</span><b>≈ rango estimado</b><span>${fmtM(cifra2(max))}</span></div></div>`;
}
function fuentesCitadas(lista = []) {
  if (!lista.length) return '';
  return `<details class="fuentes-cit"><summary>Fuentes (${lista.length})</summary><ol>${lista.map((f) => `<li>${f.url ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.titulo || f.url)}</a>` : esc(f.titulo)}</li>`).join('')}</ol></details>`;
}
function pilaFinanciacion(fin = [], inv = null) {
  // cada aporte se muestra con el mismo margen (mínimo–máximo) que tiene la inversión de su módulo
  const k0 = inv?.central ? (inv.min ?? inv.central) / inv.central : 1, k1 = inv?.central ? (inv.max ?? inv.central) / inv.central : 1;
  const F = datos.financiacion?.fuentes || [], tot = fin.reduce((a, f) => a + (f.monto || 0), 0) || 1;
  const col = (id) => (F.find((x) => x.id === id) || {}).color || 'var(--muted)';
  return `<div class="pila">${fin.map((f) => `<i style="--c:${col(f.fuente)};width:${(100 * (f.monto || 0)) / tot}%" title="${esc((F.find((x) => x.id === f.fuente) || {}).nombre || f.fuente)}"></i>`).join('')}</div>
    <div class="leyenda">${fin.map((f) => { const d = F.find((x) => x.id === f.fuente) || { nombre: f.fuente }; return `<div><i style="--c:${col(f.fuente)}"></i><span><b style="font:inherit;color:var(--ink)">${esc(d.corto || d.nombre)}</b>${f.mecanismo ? ` · ${esc(f.mecanismo)}` : ''}</span><b>${fmtRango((f.monto || 0) * k0, (f.monto || 0) * k1)}</b></div>`; }).join('')}</div>`;
}

const RENDER = {
  portada(c, p) {
    return {
      cab: `<p class="ceja">${esc(datos.meta?.lugar || 'Yondó, Antioquia')} · ${esc(datos.meta?.periodo || '2028–2031')}</p><h2>${titulo(p.titulo || c.titulo)}</h2><p class="lead">${p.texto || c.lema || ''}</p>`,
      cuerpo: `${cifras(p.cifras || c.cifras)}
        <h3>Los módulos · inversión aproximada ${rgTotal()}</h3>
        <div class="comps">${datos.modulos.map((m, i) => `<button type="button" class="comp" data-ir="${i + 1}" style="--mc:${colorDe(m.id)}"><b>${esc(m.nombre)}</b><span class="v">${rg(m.inversion)}</span><span class="d">${esc(m.lema || '')}</span><span class="bar"><i style="--w:${(100 * (m.inversion?.central || 0)) / Math.max(...datos.modulos.map((x) => x.inversion?.central || 0))}%"></i></span></button>`).join('')}</div>
        ${p.nota ? `<p class="nota" style="margin-top:12px">${p.nota}</p>` : ''}`,
    };
  },
  portadilla(c, p) {
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || c.lema)}</h2><p class="lead">${p.texto || c.problema || ''}</p>`,
      cuerpo: `${cifras(p.cifras || c.cifras)}
        ${c.propuesta ? `<h3>Lo que proponemos</h3><p>${c.propuesta}</p>` : ''}
        ${c.inversion ? `<h3>Inversión aproximada (rango, millones de 2026)</h3>${rango(c.inversion)}` : ''}`,
    };
  },
  componentes(c, p) {
    const comps = c.componentes || [], max = Math.max(1, ...comps.map((x) => x.costo?.central || 0));
    // solo son botones las tarjetas que llevan a un paso propio; las demás son fichas fijas
    const tarjeta = (x) => {
      const dentro = `<b>${esc(x.nombre)}</b><span class="v">${rg(x.costo)}</span><span class="d">${esc(x.resumen || '')}</span><span class="bar"><i style="--w:${(100 * (x.costo?.central || 0)) / max}%"></i></span>`;
      return pasoDeComp(c, x.id) >= 0 ? `<button type="button" class="comp" data-comp="${esc(x.id)}">${dentro}</button>` : `<div class="comp">${dentro}</div>`;
    };
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || 'Qué se construye')}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `<div class="comps">${comps.map(tarjeta).join('')}</div>
        ${c.inversion ? `<p class="nota" style="margin-top:10px">Total aproximado del módulo: <b>${rg(c.inversion)}</b> (cifras de perfil, en millones de 2026; se ajustan con los diseños).</p>` : ''}`,
    };
  },
  componente(c, p) {
    const x = (c.componentes || []).find((k) => k.id === p.componente) || {};
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || x.nombre)}</h2><p class="lead">${p.texto || x.descripcion || ''}</p>`,
      cuerpo: `${x.especificaciones?.length ? `<h3>Especificaciones</h3><dl class="kv">${x.especificaciones.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
        ${x.costo ? `<h3>Rango de costo estimado</h3>${rango(x.costo)}${x.base_costo ? `<p class="nota">${x.base_costo}</p>` : ''}` : ''}
        ${x.proyecto_tipo?.length ? `<h3>Proyecto tipo y referentes</h3>${chipsTipo(x.proyecto_tipo)}` : ''}
        ${x.fuentes?.length ? `<h3>Fuentes de financiación</h3>${chipsFuentes(x.fuentes)}` : ''}
        ${x.ubicacion ? `<h3>Dónde</h3><p>${x.ubicacion}</p>` : ''}
        ${x.plazo ? `<p class="nota">Plazo: ${esc(x.plazo)}</p>` : ''}
        ${p.cifras ? cifras(p.cifras) : ''}`,
    };
  },
  comparacion(c, p) {
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo)}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `<div class="compara"><div class="no"><b>${esc(p.antes?.titulo || 'Antes')}</b>${p.antes?.texto || ''}</div><div class="si"><b>${esc(p.despues?.titulo || 'Propuesta')}</b>${p.despues?.texto || ''}</div></div>
        ${p.grafico === 'reloj' ? relojAgua(p) : ''}${cifras(p.cifras)}${p.nota ? `<p class="nota">${p.nota}</p>` : ''}`,
    };
  },
  texto(c, p) {
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || c.nombre)}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `${p.lista?.length ? `<ul>${p.lista.map((l) => `<li>${l}</li>`).join('')}</ul>` : ''}${cifras(p.cifras)}${p.cuerpo || ''}${p.nota ? `<p class="nota">${p.nota}</p>` : ''}`,
    };
  },
  financiacion(c, p) {
    const g = c.gestion || {}, k = madurezPasos.indexOf(g.madurez);
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || 'Cómo se financia')}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `${c.financiacion?.length ? `<h3>Mezcla de fuentes propuesta</h3>${pilaFinanciacion(c.financiacion, c.inversion)}` : ''}
        ${c.proyectos_tipo?.length ? `<h3>Proyectos tipo del DNP que sirven</h3>${chipsTipo(c.proyectos_tipo)}` : ''}
        ${g.madurez ? `<h3>Madurez hoy</h3><div class="madurez">${madurezPasos.map((m, i) => `<span class="${i <= k ? 'si' : ''} ${i === k ? 'aqui' : ''}" title="${m}">${madurezRotulos[m] || m}</span>`).join('')}</div>${g.madurez_nota ? `<p class="nota">${g.madurez_nota}</p>` : ''}` : ''}
        ${g.pedido ? `<div class="pedido"><b>Lo que pedimos al nivel central</b>${g.pedido}</div>` : ''}
        ${g.a_quien?.length ? `<h3>A quién tocar</h3><ul class="limpia">${g.a_quien.map((a) => `<li>· ${a}</li>`).join('')}</ul>` : ''}
        ${g.pasos?.length ? `<h3>Siguientes pasos</h3><ol style="margin:0 0 8px;padding-left:18px">${g.pasos.map((a) => `<li>${a}</li>`).join('')}</ol>` : ''}
        ${fuentesCitadas(c.fuentes_citadas)}`,
    };
  },
  matriz(c, p) {
    const F = c.fuentes || [], mods = datos.modulos;
    const kde = (m) => (m.inversion?.central ? [(m.inversion.min ?? m.inversion.central) / m.inversion.central, (m.inversion.max ?? m.inversion.central) / m.inversion.central] : [1, 1]);
    const porFuente = F.map((f) => { let total = 0, lo = 0, hi = 0; mods.forEach((m) => { const [k0, k1] = kde(m); (m.financiacion || []).filter((x) => x.fuente === f.id).forEach((x) => { total += x.monto || 0; lo += (x.monto || 0) * k0; hi += (x.monto || 0) * k1; }); }); return { f, total, lo, hi }; }).filter((x) => x.total > 0).sort((a, b) => b.total - a.total);
    const tot = porFuente.reduce((a, x) => a + x.total, 0) || 1;
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || 'Cómo se financia todo')}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `${cifras(p.cifras)}<h3>Por fuente (millones de 2026)</h3>
        <div class="pila">${porFuente.map((x) => `<i style="--c:${x.f.color};width:${(100 * x.total) / tot}%" title="${esc(x.f.nombre)}"></i>`).join('')}</div>
        <div class="leyenda">${porFuente.map((x) => `<div><i style="--c:${x.f.color}"></i><span><b style="font:inherit;color:var(--ink)">${esc(x.f.corto || x.f.nombre)}</b> · ${esc(x.f.entidad || '')}</span><b>${fmtRango(x.lo, x.hi)}</b></div>`).join('')}</div>
        <h3>Por módulo</h3>
        <table class="tabla"><thead><tr><th>Módulo</th><th class="n">Inversión aproximada</th><th>Fuentes principales</th></tr></thead><tbody>${mods.map((m) => `<tr><td><b style="color:${colorDe(m.id)}">●</b> ${esc(m.nombre)}</td><td class="n">${rg(m.inversion)}</td><td>${(m.financiacion || []).slice().sort((a, b) => b.monto - a.monto).slice(0, 3).map((x) => esc((F.find((f) => f.id === x.fuente) || {}).corto || x.fuente)).join(', ')}</td></tr>`).join('')}<tr><td><b>Total</b></td><td class="n"><b>${rgTotal()}</b></td><td></td></tr></tbody></table>
        ${p.nota ? `<p class="nota" style="margin-top:10px">${p.nota}</p>` : ''}`,
    };
  },
  fuentes(c, p) {
    const F = c.fuentes || [];
    return {
      cab: `<p class="ceja">${esc(c.nombre)}</p><h2>${titulo(p.titulo || 'Las fuentes, una por una')}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `<div class="comps">${F.map((f) => `<div class="comp fuente" style="--mc:${f.color};cursor:default"><b>${esc(f.nombre)}</b><span class="v">${esc(f.tipo || '')}</span><span class="d">${esc(f.que_financia || '')}${f.requisito ? ` <br><i>Requisito clave:</i> ${esc(f.requisito)}` : ''}${f.url ? ` · <a href="${esc(f.url)}" target="_blank" rel="noopener">fuente</a>` : ''}</span></div>`).join('')}</div>`,
    };
  },
  ruta(c, p) {
    const F = c.fases || [], H = c.hitos || [];
    const anios = [2026, 2027, 2028, 2029, 2030, 2031], x = (f) => ((f - 2026) / 6) * 100;
    return {
      cab: `<p class="ceja">Hoja de ruta</p><h2>${titulo(p.titulo || 'De la idea a la obra')}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `<div class="gantt" style="position:relative;margin:8px 0 10px">
          <div style="display:grid;grid-template-columns:repeat(6,1fr);font:0.66rem var(--f-mono);color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:4px">${anios.map((a) => `<span>${a}</span>`).join('')}</div>
          ${F.map((f) => { const l = x(f.desde), w = Math.min(100, x(f.hasta)) - l, der = l > 50; return `<div class="fila" style="position:relative;height:34px;margin-top:6px"><span style="position:absolute;${der ? `right:${100 - (l + w)}%;text-align:right` : `left:${l}%`};top:0;font:600 0.72rem var(--f-body);color:var(--ink);white-space:nowrap">${esc(f.nombre)}</span><i class="barra-r" style="position:absolute;left:${l}%;width:${w}%;top:17px;height:12px;border-radius:6px;background:${f.color || 'var(--accent)'};opacity:0.9"></i></div>`; }).join('')}
        </div>
        ${H.length ? `<h3>Compuertas</h3><ul class="limpia">${H.map((h) => `<li>◆ <b>${esc(h.fecha)}</b> · ${esc(h.texto)}</li>`).join('')}</ul>` : ''}
        ${p.lista?.length ? `<ul>${p.lista.map((l) => `<li>${l}</li>`).join('')}</ul>` : ''}`,
    };
  },
  pedidos(c, p) {
    const E = c.entidades || [];
    return {
      cab: `<p class="ceja">Gestión</p><h2>${titulo(p.titulo || 'Lo que pedimos')}</h2>${p.texto ? `<p class="lead">${p.texto}</p>` : ''}`,
      cuerpo: `<div class="comps">${E.map((e) => `<div class="comp" style="cursor:default;--mc:${e.modulos?.[0] ? colorDe(e.modulos[0]) : 'var(--accent)'}"><b>${esc(e.entidad)}</b><span class="v">${e.monto ? aprox(e.monto) : ''}</span><span class="d">${e.pedido}</span><span class="d">${(e.modulos || []).map((id) => `<span style="color:${colorDe(id)}">●</span> ${esc((datos.modulos.find((m) => m.id === id) || {}).corto || id)}`).join(' &nbsp; ')}</span></div>`).join('')}</div>
        ${p.nota ? `<p class="nota" style="margin-top:10px">${p.nota}</p>` : ''}`,
    };
  },
};
// el cuerpo del panel se desvanece abajo mientras haya más contenido para leer
function marcarDesborde() {
  const p = $('.panel'), hojaEntera = getComputedStyle(p).overflowY === 'auto', el = hojaEntera ? p : cuerpo;
  (hojaEntera ? cuerpo : p).classList.remove('mas');
  el.classList.toggle('mas', el.scrollTop + el.clientHeight < el.scrollHeight - 6);
}
cuerpo.addEventListener('scroll', marcarDesborde, { passive: true });
$('.panel').addEventListener('scroll', marcarDesborde, { passive: true });
addEventListener('resize', marcarDesborde);
// titular partido en palabras (para animarlas)
// palabras del título (para animarlas); el número y su unidad («69 %», «24 horas») no se separan
function titulo(t) {
  return String(t || '').replace(/(\d)\s+(%|horas?\b|km\b|ha\b|L\/s|m³|MWp|kWp|MW\b|M\b|millones|billones)/g, '$1\u00a0$2')
    .split(/[ \t\n]+/).filter(Boolean).map((w) => `<span class="w">${esc(w)}</span>`).join(' ');
}
// gráfico de 24 horas: horas con agua hoy (franja) frente a la meta (todo el día)
function relojAgua(p) {
  const h0 = p.reloj?.desde ?? 4, h1 = p.reloj?.hasta ?? 13, R = 52, C = 64;
  const arco = (a, b, r) => { const p0 = (a / 24) * Math.PI * 2 - Math.PI / 2, p1 = (b / 24) * Math.PI * 2 - Math.PI / 2; return `M${C + r * Math.cos(p0)} ${C + r * Math.sin(p0)} A${r} ${r} 0 ${b - a > 12 ? 1 : 0} 1 ${C + r * Math.cos(p1)} ${C + r * Math.sin(p1)}`; };
  return `<svg class="reloj" viewBox="0 0 300 128" role="img" aria-label="Horas de servicio de agua: hoy de ${h0} a ${h1}, meta 24 horas">
    <circle cx="${C}" cy="${C}" r="${R}" fill="none" stroke="var(--line)" stroke-width="14"/>
    <path class="arco-hoy" d="${arco(h0, h1, R)}" fill="none" stroke="var(--m-aguas)" stroke-width="14" stroke-linecap="round"/>
    <text x="${C}" y="${C - 2}" text-anchor="middle" style="font:400 26px var(--f-display);fill:var(--ink)">${h1 - h0} h</text>
    <text x="${C}" y="${C + 16}" text-anchor="middle" style="font:10px var(--f-mono);fill:var(--muted)">hoy</text>
    <circle cx="${C + 150}" cy="${C}" r="${R}" fill="none" stroke="var(--m-aguas)" stroke-width="14" class="arco-meta"/>
    <text x="${C + 150}" y="${C - 2}" text-anchor="middle" style="font:400 26px var(--f-display);fill:var(--ink)">24 h</text>
    <text x="${C + 150}" y="${C + 16}" text-anchor="middle" style="font:10px var(--f-mono);fill:var(--muted)">meta 2030</text>
  </svg>`;
}

// ---------------------------------------------------------------- navegación
const estado = { ci: -1, pi: -1 };
let tlPanel = null, tlTelon = null, cola = Promise.resolve();
function hashDe(ci, pi) { return `#${caps[ci].id}${pi ? `/${pi + 1}` : ''}`; }
function desdeHash() {
  const [id, n] = location.hash.replace('#', '').split('/');
  const ci = Math.max(0, caps.findIndex((c) => c.id === id));
  return [ci, Math.min(Math.max(0, (parseInt(n, 10) || 1) - 1), caps[ci].pasos.length - 1)];
}
function ir(ci, pi, opts = {}) { cola = cola.then(() => mostrar(ci, pi, opts)).catch((e) => console.error(e)); return cola; }
function avanzar(d) {
  let { ci, pi } = estado;
  if (tlTelon?.isActive()) { tlTelon.progress(1); return; }
  pi += d;
  if (pi >= caps[ci].pasos.length) { if (ci < caps.length - 1) { ci++; pi = 0; } else pi = caps[ci].pasos.length - 1; }
  if (pi < 0) { if (ci > 0) { ci--; pi = caps[ci].pasos.length - 1; } else pi = 0; }
  ir(ci, pi, { dir: d });
}

async function mostrar(ci, pi, { dir = 1, primera = false } = {}) {
  if (ci === estado.ci && pi === estado.pi) return;
  const c = caps[ci], p = c.pasos[pi], cambia = ci !== estado.ci;
  estado.ci = ci; estado.pi = pi;
  if (location.hash !== hashDe(ci, pi)) history.replaceState(null, '', hashDe(ci, pi));
  pres.style.setProperty('--mc', colorDe(c.id));
  document.title = `${c.nombre} · Yondó 2028–2031`;
  // riel, puntos, progreso y control
  $$('button', riel).forEach((b) => b.setAttribute('aria-current', +b.dataset.cap === ci ? 'step' : 'false'));
  puntos.innerHTML = c.pasos.map((x, i) => `<button type="button" data-paso="${i}" aria-label="Paso ${i + 1}: ${esc(x.titulo || '')}" aria-current="${i === pi ? 'step' : 'false'}"></button>`).join('');
  $('.control .donde b').textContent = c.nombre;
  $('.control .sig span').textContent = ci === caps.length - 1 && pi === c.pasos.length - 1 ? 'Fin' : pi === c.pasos.length - 1 ? caps[ci + 1].corto || 'Siguiente' : 'Siguiente';
  $$('i', progreso).forEach((el, i) => el.style.setProperty('--p', i < ci ? 1 : i > ci ? 0 : (pi + 1) / c.pasos.length));
  leyenda.innerHTML = (p.leyenda || []).map((l) => `<span><i class="${l.forma || ''}" style="--c:${l.color || 'var(--mc)'}"></i><em>${esc(l.texto)}</em></span>`).join('');
  leyenda.classList.remove('abierta');
  // telón al cambiar de capítulo (no en la primera carga)
  if (cambia && !primera && gsap && !reducedMotion) telonDe(c);
  await pintarPanel(c, p, dir, cambia && !primera);
  // 3D: capas y cámara del paso (los módulos pueden tardar en cargar: se espera al suyo hasta 4 s y, si llega después,
  // se vuelve a aplicar el paso); si mientras tanto se pasó a otro paso, este ya no toca la escena
  const listo = await Promise.race([cargas[ci].then(() => true), new Promise((r) => setTimeout(() => r(false), 4000))]);
  const vigente = () => estado.ci === ci && estado.pi === pi;
  if (!vigente()) return;
  pasar3D(c, p);
  if (!listo) cargas[ci].then(() => { if (vigente()) pasar3D(c, p); });
}

function telonDe(c) {
  tlTelon?.kill();
  const banda = $('.banda', telon), n = $('.n', telon), t = $('.t', telon), l = $('.l', telon);
  telon.style.setProperty('--mc', colorDe(c.id));
  n.textContent = ''; t.innerHTML = [...(c.nombre || '')].map((ch) => `<span class="ch">${ch === ' ' ? '&nbsp;' : esc(ch)}</span>`).join(''); l.textContent = c.lema || '';
  tlTelon = gsap.timeline({ defaults: { ease: 'power3.inOut' } })
    .set(telon, { autoAlpha: 1 })
    .fromTo(banda, { scaleX: 0, transformOrigin: 'left center' }, { scaleX: 1, duration: 0.45 })
    .fromTo(n, { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.5, ease: 'power3.out' }, 0.25)
    .fromTo($$('.ch', t), { yPercent: 110, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.45, stagger: 0.025, ease: 'power3.out' }, 0.32)
    .fromTo(l, { y: 14, opacity: 0 }, { y: 0, opacity: 0.92, duration: 0.4, ease: 'power2.out' }, 0.5)
    .to([n, t, l], { x: 50, opacity: 0, duration: 0.3, ease: 'power2.in' }, 1.35)
    .to(banda, { scaleX: 0, transformOrigin: 'right center', duration: 0.45 }, 1.45)
    .set(telon, { autoAlpha: 0 });
}

async function pintarPanel(c, p, dir, conTelon) {
  const r = (RENDER[p.tipo] || RENDER.texto)(c, p);
  const salir = gsap && !reducedMotion && cab.innerHTML ? gsap.to([cab, cuerpo], { opacity: 0, y: dir > 0 ? -12 : 12, duration: 0.18, ease: 'power2.in' }) : null;
  if (salir) await salir;
  cab.innerHTML = r.cab; cuerpo.innerHTML = r.cuerpo; cuerpo.scrollTop = 0; $('.panel').scrollTop = 0;
  // la hoja toma de una vez (sin transición) la altura del texto nuevo, antes de que el paso encuadre la maqueta
  if (hojaMQ.matches) { pres.classList.add('arrastrando'); aplicarHoja(hoja, { reencuadre: false }); void panelEl.offsetHeight; pres.classList.remove('arrastrando'); }
  requestAnimationFrame(marcarDesborde);
  $('.panel').style.setProperty('--mc', colorDe(c.id));
  if (!gsap || reducedMotion) { gsap?.set([cab, cuerpo], { clearProps: 'all' }); return; }
  tlPanel?.kill();
  tlPanel = gsap.timeline({ defaults: { ease: 'power3.out' }, delay: conTelon ? 0.95 : 0 }).set([cab, cuerpo], { opacity: 1, y: 0 });
  // cada grupo se anima solo si el paso lo tiene (GSAP avisa en la consola cuando la lista está vacía)
  const desde = (el, vars, t) => { if (el.length) tlPanel.from(el, vars, t); };
  desde($$('.ceja', cab), { opacity: 0, x: -10, duration: 0.35 }, 0);
  desde($$('h2 .w', cab), { yPercent: 70, opacity: 0, duration: 0.5, stagger: 0.04 }, 0.05);
  desde($$('.lead', cab), { opacity: 0, y: 10, duration: 0.45 }, 0.2);
  desde([...cuerpo.children], { opacity: 0, y: 14, duration: 0.45, stagger: 0.06 }, 0.28);
  desde($$('.cifra', cuerpo), { opacity: 0, y: 12, scale: 0.97, duration: 0.4, stagger: 0.07 }, 0.3);
  desde($$('.comp .bar i, .pila i', cuerpo), { scaleX: 0, transformOrigin: 'left center', duration: 0.7, stagger: 0.04, ease: 'power2.out' }, 0.45);
  desde($$('.rango .eje i, .rango .eje em, .madurez span', cuerpo), { opacity: 0, scaleX: 0.3, transformOrigin: 'left center', duration: 0.5, stagger: 0.04 }, 0.45);
  desde($$('.gantt .barra-r', cuerpo), { scaleX: 0, transformOrigin: 'left center', duration: 0.6, stagger: 0.12 }, 0.4);
  tlPanel.add(() => $$('.cifra b[data-cuenta]', cuerpo).forEach((b) => countUp(b, 1.2)), 0.35);
  const arco = $('.arco-hoy', cuerpo);
  if (arco) { const L = arco.getTotalLength(); gsap.fromTo(arco, { strokeDasharray: L, strokeDashoffset: L }, { strokeDashoffset: 0, duration: 1.1, delay: 0.6, ease: 'power2.out' }); }
}

let capasVisibles = [];
function pasar3D(c, p) {
  const m = ctx3d[c.id], def = m?.pasos?.[p.id] || m?.pasos?.['*'] || {};
  const ids = [...(m?.siempre || []), ...(def.capas || []), ...(p.capas || [])];
  // la visión completa (hoja de ruta, pedidos) muestra las capas principales de todos los módulos; en los demás pasos,
  // los otros módulos dejan la maqueta como está hoy (por ejemplo, la torre del hospital vuelve a su estado actual)
  Object.entries(ctx3d).forEach(([id, x]) => {
    if (def.todos) { ids.push(...(x?.completo || [])); x?.alCompleto?.(); } else if (id !== c.id) x?.salir?.();
  });
  escena.verCapas(ids);
  // en la visión de conjunto solo quedan las etiquetas del capítulo (si no, se enciman las de las siete áreas)
  escena.soloEtiquetas?.(def.etiquetas || (def.todos ? [...(m?.siempre || []), ...(def.capas || []), ...(p.capas || [])] : null));
  capasVisibles = ids;
  def.antes?.();
  escena.st._obra = null;   // la vista del paso dice qué obra encuadra (los rótulos se apartan de ella en el celular)
  (def.vista || m?.vista)?.();
  if (gsap && !reducedMotion) def.animar?.(); else def.alFinal?.();
  // el mapa de sombras se recalcula a pedido: una vez más cuando ya terminaron de crecer las piezas del paso
  clearTimeout(tSombras); tSombras = setTimeout(() => escena.st.updateShadows(), 3600);
}
let tSombras = 0;
// al cambiar el tamaño de la pantalla (o al ocultar el panel) se vuelve a encuadrar el paso, salvo que la persona haya movido la cámara
let tReenc = 0;
function reencuadrar() {
  clearTimeout(tReenc);
  tReenc = setTimeout(() => {
    if (escena.st.userMoved || estado.ci < 0) return;
    const c = caps[estado.ci], p = c.pasos[estado.pi], m = ctx3d[c.id], def = m?.pasos?.[p.id] || m?.pasos?.['*'] || {};
    (def.vista || m?.vista)?.();
  }, 250);
}
addEventListener('resize', reencuadrar);

// ---------------------------------------------------------------- índice, fichas y herramientas
function abrirIndice(v = indice.hidden) {
  indice.hidden = !v;
  if (v && gsap && !reducedMotion) gsap.from($$('.tarjeta', indice), { opacity: 0, y: 18, duration: 0.4, stagger: 0.035, ease: 'power3.out' });
  if (v) $('.tarjeta', indice)?.focus();
}
function abrirFichas(v = fichas.hidden) {
  fichas.hidden = !v;
  if (!v || fichas.dataset.listo) return;
  fichas.dataset.listo = '1';
  fichas.innerHTML = `<div class="cab"><h2>Fichas de la propuesta 2028–2031</h2><div class="herr"><button type="button" data-accion="imprimir">Imprimir o guardar en PDF</button><button type="button" data-accion="fichas">Cerrar</button></div></div>
    <p class="nota">${esc(datos.meta?.moneda || 'Millones de pesos constantes de 2026')} · corte ${esc(datos.meta?.fecha_corte || '')} · inversión total aproximada ${rgTotal()} (rangos de perfil, no costos fijos)</p>
    ${datos.modulos.map((m, i) => `<article style="--mc:${colorDe(m.id)}"><p class="ceja">${esc(m.nombre)}</p><h3>${esc(m.lema || '')}</h3>
      <div class="cols"><div><p>${m.problema || ''}</p><p><b>Propuesta.</b> ${m.propuesta || ''}</p>
        <table class="tabla"><thead><tr><th>Componente</th><th class="n">Costo aproximado</th><th>Proyecto tipo</th></tr></thead><tbody>${(m.componentes || []).map((x) => `<tr><td>${esc(x.nombre)}</td><td class="n">${rg(x.costo)}</td><td>${(x.proyecto_tipo || []).map((t) => esc(t.nombre)).join('; ') || '—'}</td></tr>`).join('')}<tr><td><b>Total</b></td><td class="n"><b>${rg(m.inversion)}</b></td><td></td></tr></tbody></table></div>
      <div>${pilaFinanciacion(m.financiacion || [], m.inversion)}${m.gestion?.pedido ? `<div class="pedido"><b>Lo que pedimos</b>${m.gestion.pedido}</div>` : ''}${m.metas?.length ? `<h4 style="margin:12px 0 4px">Metas</h4><ul>${m.metas.map((x) => `<li>${esc(x.indicador)}: ${esc(x.base ?? '')} → <b>${esc(x.meta)}</b></li>`).join('')}</ul>` : ''}</div></div></article>`).join('')}`;
}
function pantalla() { if (document.fullscreenElement) document.exitFullscreen?.(); else document.documentElement.requestFullscreen?.().catch(() => {}); }
function alternarPanel(v) {
  const oculto = v ?? !pres.classList.contains('sin-panel');
  pres.classList.toggle('sin-panel', oculto);
  $('[data-accion="panel"]').setAttribute('aria-pressed', String(oculto));
  setTimeout(reencuadrar, 460);
}

document.addEventListener('click', (e) => {
  const a = e.target.closest('[data-accion]'), cap = e.target.closest('[data-cap]'), paso = e.target.closest('[data-paso]'), irA = e.target.closest('[data-ir]'), comp = e.target.closest('[data-comp]');
  if (a) {
    const k = a.dataset.accion;
    if (k === 'sig') avanzar(1); else if (k === 'ant') avanzar(-1);
    else if (k === 'indice') abrirIndice(); else if (k === 'fichas') abrirFichas(); else if (k === 'imprimir') print();
    else if (k === 'tema') cambiarTema(); else if (k === 'pantalla') pantalla(); else if (k === 'panel') alternarPanel();
    return;
  }
  if (cap) { abrirIndice(false); ir(+cap.dataset.cap, 0); return; }
  if (paso) { ir(estado.ci, +paso.dataset.paso); return; }
  if (irA) { ir(+irA.dataset.ir, 0); return; }
  if (comp) { const k = pasoDeComp(caps[estado.ci], comp.dataset.comp); if (k >= 0) ir(estado.ci, k); }
});
leyenda.addEventListener('click', () => leyenda.classList.toggle('abierta'));

// ---------------------------------------------------------------- hoja inferior (celular y tableta en vertical)
// Tres alturas: «mini» deja solo la ceja y el título, «medio» (la de partida) muestra el texto y deja la mitad de arriba
// para la maqueta, y «grande» es para leer. Se cambia tocando el asa (mini ↔ medio) o arrastrándola; al soltar se ajusta
// a la altura más cercana y la cámara vuelve a encuadrar en lo que queda libre encima.
const hojaMQ = matchMedia('(max-width: 1080px) and (orientation: portrait), (max-width: 1080px) and (min-height: 561px)');
const panelEl = $('.panel'), asa = $('.panel .asa');
let hoja = 'medio';
function alturaHoja(estado) {
  const ctl = $('.control').getBoundingClientRect(), bar = $('.barra').getBoundingClientRect();
  const libre = Math.max(160, ctl.top - 12 - (bar.bottom + 10));
  if (estado === 'grande') return Math.round(libre);
  if (estado === 'mini') {
    const antes = pres.classList.contains('hoja-mini');
    pres.classList.add('hoja-mini');
    const h = cab.offsetHeight + 6;
    if (!antes) pres.classList.remove('hoja-mini');
    return Math.round(Math.min(h, libre * 0.4));
  }
  // media: la altura de siempre o, si el título y la entrada del paso no caben, la que necesiten (hasta el 55 % de lo libre)
  const base = Math.min(Math.max(190, innerHeight * 0.38), 380, libre * 0.62);
  return Math.round(Math.max(base, Math.min(cab.offsetHeight + 12, libre * 0.55)));
}
function aplicarHoja(estado = hoja, { reencuadre = true } = {}) {
  if (!hojaMQ.matches) { pres.classList.remove('hoja-mini', 'panel-grande'); pres.style.removeProperty('--hoja'); return; }
  hoja = estado;
  // las clases van antes de medir: con hoja-mini puesta el título mide menos y la hoja media volvía más baja
  pres.classList.toggle('hoja-mini', estado === 'mini');
  pres.classList.toggle('panel-grande', estado === 'grande');
  pres.style.setProperty('--hoja', `${alturaHoja(estado)}px`);
  asa.setAttribute('aria-label', estado === 'mini' ? 'Mostrar el texto del paso' : 'Achicar el panel para ver la maqueta');
  asa.setAttribute('aria-expanded', String(estado !== 'mini'));
  requestAnimationFrame(marcarDesborde);
  if (reencuadre) setTimeout(reencuadrar, 360);
}
let arrastre = null;
asa.addEventListener('pointerdown', (e) => {
  if (!hojaMQ.matches) return;
  arrastre = { y0: e.clientY, h0: panelEl.getBoundingClientRect().height, movio: false, min: alturaHoja('mini'), max: alturaHoja('grande') };
  asa.setPointerCapture(e.pointerId);
});
asa.addEventListener('pointermove', (e) => {
  if (!arrastre) return;
  const dy = arrastre.y0 - e.clientY;
  if (!arrastre.movio && Math.abs(dy) < 6) return;
  arrastre.movio = true; pres.classList.add('arrastrando');
  pres.style.setProperty('--hoja', `${Math.round(Math.min(arrastre.max, Math.max(arrastre.min, arrastre.h0 + dy)))}px`);
});
function soltarHoja() {
  const a = arrastre; arrastre = null;
  if (!a) return;
  pres.classList.remove('arrastrando');
  if (!a.movio) { aplicarHoja(hoja === 'mini' ? 'medio' : hoja === 'medio' ? 'mini' : 'medio'); return; }
  const h = panelEl.getBoundingClientRect().height, d = alturaHoja('medio');
  aplicarHoja(h < (a.min + d) / 2 ? 'mini' : h < (d + a.max) / 2 ? 'medio' : 'grande');
}
asa.addEventListener('pointerup', soltarHoja);
asa.addEventListener('pointercancel', soltarHoja);
asa.addEventListener('keydown', (e) => { if (e.key === 'ArrowUp') { e.preventDefault(); aplicarHoja(hoja === 'mini' ? 'medio' : 'grande'); } else if (e.key === 'ArrowDown') { e.preventDefault(); aplicarHoja(hoja === 'grande' ? 'medio' : 'mini'); } });
// con la hoja en mini, tocar el título la abre
cab.addEventListener('click', () => { if (hoja === 'mini' && hojaMQ.matches) aplicarHoja('medio'); });
addEventListener('resize', () => aplicarHoja(hoja, { reencuadre: false }));
aplicarHoja('medio', { reencuadre: false });
addEventListener('keydown', (e) => {
  if (e.altKey || e.ctrlKey || e.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  const k = e.key;
  if (k === 'Escape') { if (!indice.hidden) abrirIndice(false); else if (!fichas.hidden) abrirFichas(false); return; }
  if (!fichas.hidden) return;
  if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(k) && !(k === 'Enter' && e.target.closest('button,a'))) { e.preventDefault(); if (!indice.hidden) abrirIndice(false); avanzar(1); }
  else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(k)) { e.preventDefault(); avanzar(-1); }
  else if (k === 'Home') ir(0, 0);
  else if (k === 'End') ir(caps.length - 1, 0);
  else if (k === 'i' || k === 'I' || k === 'o' || k === 'O') abrirIndice();
  else if (k === 'h' || k === 'H') alternarPanel();
  else if (k === 'f' || k === 'F') pantalla();
  else if (k === 'd' || k === 'D') pres.toggleAttribute('data-debug');
  else if (/^[0-9]$/.test(k) && +k < caps.length) ir(+k, 0);
});
// deslizar el panel con el dedo también avanza (el lienzo 3D queda para girar la cámara)
let toque = null;
$('.panel').addEventListener('touchstart', (e) => { toque = [e.touches[0].clientX, e.touches[0].clientY]; }, { passive: true });
$('.panel').addEventListener('touchend', (e) => {
  if (!toque) return;
  const dx = e.changedTouches[0].clientX - toque[0], dy = e.changedTouches[0].clientY - toque[1]; toque = null;
  if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) avanzar(dx < 0 ? 1 : -1);
});
addEventListener('hashchange', () => { const [ci, pi] = desdeHash(); ir(ci, pi); });

// arranque: la vista que pide la dirección (o la portada)
const [ci0, pi0] = desdeHash();
ir(ci0, pi0, { primera: true });
