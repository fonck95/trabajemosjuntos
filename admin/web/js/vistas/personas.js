// Directorio de habitantes con búsqueda, filtros combinables, orden, paginación y exportación.
import { api, descargar } from '../api.js';
import { $, $$, FUENTES, aviso, chipPrecision, debounce, fecha, html, icono, montar, num, titulo } from '../ui.js';
import { formularioNuevaPersona } from './comunes.js';

const FILTROS = ['q', 'zona', 'lugar_id', 'fuente', 'lista', 'etiqueta', 'con_cedula', 'con_telefono', 'precision', 'asistio',
  'consentimiento', 'lider', 'sexo', 'completitud_max', 'ids', 'ids_total', 'reunion_id'];
// Filtros que solo llegan por enlace (sin control propio): se muestran como chip para verlos y quitarlos
const OCULTOS = {
  // La lista de un hexágono lleva como mucho 500 ids: el chip dice cuántas de cuántas se ven
  ids: (v, f) => (Number(f.ids_total) > (v || '').split(',').length
    ? `Selección del mapa: ${num((v || '').split(',').length)} de ${num(Number(f.ids_total))}` : 'Selección del mapa'),
  lider: () => 'Solo líderes',
  sexo: (v) => (v === 'F' ? 'Mujeres' : v === 'M' ? 'Hombres' : `Sexo: ${v}`),
  completitud_max: (v) => `Perfil hasta ${v} %`,
  reunion_id: (v) => `Asistentes de la reunión ${v}`,
};

export async function vistaPersonas(el, { q, ir }) {
  const f = Object.fromEntries(FILTROS.filter((k) => q.get(k)).map((k) => [k, q.get(k)]));
  let orden = q.get('orden') || 'nombre', pagina = Number(q.get('pagina') || 1);
  const cat = await api.get('/api/catalogos');
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const opciones = (lista, valor) => lista.map(([v, t]) => html`<option value="${v}" ${String(valor ?? '') === String(v) ? 'selected' : ''}>${t}</option>`);

  montar(el, html`
    <div class="cabecera">
      <div><h1>Habitantes</h1><div class="sub" id="total">Cargando…</div></div>
      <div class="acciones">
        <button class="btn" id="exportar" title="Exporta lo filtrado; omite a quien marcó «No autorizó» el tratamiento de sus datos">${icono('descargar')} Exportar a Excel</button>
        <button class="btn primario" id="nueva">${icono('mas')} Nueva persona</button>
      </div>
    </div>
    <div class="filtros">
      <label class="buscador"><span class="sr">Buscar</span>${icono('buscar')}<input class="entrada" id="q" placeholder="Nombre, cédula, teléfono, dirección o ficha" value="${f.q || ''}"></label>
      <select class="entrada" data-f="zona">${opciones([['', 'Zona'], ['urbana', 'Casco urbano'], ['rural', 'Rural'], ['sin', 'Sin zona']], f.zona)}</select>
      <select class="entrada" data-f="lugar_id">${opciones([['', 'Barrio / vereda'], ['0', 'Sin barrio o vereda'], ...cat.lugares.map((l) => [l.id, titulo(l.nombre) + (l.tipo !== 'barrio' ? ` · ${l.tipo.replace('_', ' ')}` : '')])], f.lugar_id)}</select>
      <select class="entrada" data-f="fuente">${opciones([['', 'Fuente'], ['tramites', 'Base de trámites'], ['cedulas', 'Base con cédula'], ['ambas', 'En las dos'], ['reunion', 'Registradas en reunión'], ['manual', 'Registro manual']], f.fuente)}</select>
      <select class="entrada" data-f="etiqueta">${opciones([['', 'Necesidad / etiqueta'], ...cat.etiquetas.map((e) => [e.id, e.nombre])], f.etiqueta)}</select>
      <select class="entrada" data-f="lista">${opciones([['', 'Lista'], ...cat.listas.map((l) => [l, l])], f.lista)}</select>
      <select class="entrada" data-f="con_cedula">${opciones([['', 'Cédula'], ['1', 'Con cédula'], ['0', 'Sin cédula']], f.con_cedula)}</select>
      <select class="entrada" data-f="con_telefono">${opciones([['', 'Celular'], ['1', 'Con celular'], ['0', 'Sin celular']], f.con_telefono)}</select>
      <select class="entrada" data-f="precision">${opciones([['', 'Ubicación'], ['exacta', 'Dirección exacta'], ['aproximada', 'Aproximada'], ['ubicada', 'Con ubicación'], ['sin', 'Sin ubicar']], f.precision)}</select>
      <select class="entrada" data-f="asistio">${opciones([['', 'Reuniones'], ['1', 'Asistió'], ['0', 'Sin reunión']], f.asistio)}</select>
      <select class="entrada" data-f="consentimiento">${opciones([['', 'Autorización'], ['si', 'Autorizó'], ['pendiente', 'Pendiente'], ['no', 'No autorizó']], f.consentimiento)}</select>
      <select class="entrada" id="orden">${opciones([['nombre', 'Orden: nombre'], ['-completitud', 'Menos completos'], ['completitud', 'Más completos'], ['contacto', 'Contacto reciente'], ['reciente', 'Editados recientemente']], orden)}</select>
      ${Object.entries(OCULTOS).filter(([k]) => f[k]).map(([k, t]) => html`<button class="chip rojo" data-quitar="${k}" aria-label="Quitar filtro: ${t(f[k], f)}">${t(f[k], f)} ✕</button>`)}
    </div>
    <div class="envoltura-tabla"><table class="tabla"><thead><tr>
      <th>Nombre</th><th>Cédula</th><th>Teléfono</th><th>Barrio / vereda</th><th>Ubicación</th><th>Fuentes</th><th class="num">Reuniones</th><th>Perfil</th>
    </tr></thead><tbody id="filas"></tbody></table></div>
    <div class="paginacion" id="paginacion"></div>`);

  let turno = 0;
  async function cargar() {
    // Una búsqueda que se dispara después de salir de la vista no debe tocar la URL ni el DOM de otra
    if (!el.isConnected) return;
    const mio = ++turno;
    const params = { ...f, orden, pagina, por_pagina: 50 };
    history.replaceState({}, '', '/personas?' + new URLSearchParams(Object.entries(params).filter(([k, v]) => v && !(k === 'pagina' && v === 1) && k !== 'por_pagina')));
    $('#filas', el).innerHTML = String(html`${Array.from({ length: 8 }, () => html`<tr><td colspan="8"><div class="esqueleto" style="height:18px"></div></td></tr>`)}`);
    const d = await api.get('/api/personas', params);
    if (mio !== turno || !el.isConnected) return; // llegó tarde: ya se pidió otra página u otros filtros
    const recortada = f.ids && Number(f.ids_total) > d.total;
    $('#total', el).textContent = recortada
      ? `${num(d.total)} de las ${num(Number(f.ids_total))} personas del hexágono (la selección del mapa llega hasta 500)`
      : `${num(d.total)} personas con estos filtros`;
    montar($('#filas', el), d.filas.length ? html`${d.filas.map((p) => html`<tr data-id="${p.id}">
        <td><a class="nombre" href="/personas/${p.id}" data-ruta>${p.nombre}</a>${p.lider ? html`<span class="chip rojo">Líder</span> ` : ''}${p.ultimo_contacto ? html`<span class="sec">Último contacto ${fecha(p.ultimo_contacto)}</span>` : ''}</td>
        <td>${p.cedula || html`<span class="sec">—</span>`}</td>
        <td>${p.telefono || html`<span class="sec">—</span>`}</td>
        <td>${p.lugar ? titulo(p.lugar) : html`<span class="sec">—</span>`}<div class="sec">${p.zona === 'rural' ? 'Rural' : p.zona === 'urbana' ? 'Casco urbano' : ''}</div></td>
        <td>${chipPrecision(p.precision)}</td>
        <td><div class="chips">${p.fuentes.map((x) => html`<span class="chip borde">${FUENTES[x] || x}</span>`)}</div></td>
        <td class="num">${p.reuniones || ''}</td>
        <td><span class="barra-comp"><i><b style="width:${p.completitud}%"></b></i>${p.completitud} %</span></td>
      </tr>`)}` : html`<tr><td colspan="8"><div class="vacio"><b>Nadie coincide</b>Pruebe con menos filtros.</div></td></tr>`);
    const paginas = Math.max(1, Math.ceil(d.total / d.por_pagina));
    montar($('#paginacion', el), html`<span>Página ${pagina} de ${num(paginas)}</span>
      <span style="display:flex;gap:6px"><button class="btn chico" data-p="${pagina - 1}" ${pagina <= 1 ? 'disabled' : ''}>← Anterior</button>
      <button class="btn chico" data-p="${pagina + 1}" ${pagina >= paginas ? 'disabled' : ''}>Siguiente →</button></span>`);
  }

  const buscar = debounce((e) => { f.q = e.target.value.trim() || undefined; pagina = 1; cargar(); }, 300);
  $('#q', el).addEventListener('input', buscar);
  for (const s of $$('[data-f]', el)) s.addEventListener('change', () => { f[s.dataset.f] = s.value || undefined; pagina = 1; cargar(); });
  $('#orden', el).addEventListener('change', (e) => { orden = e.target.value; pagina = 1; cargar(); });
  for (const b of $$('[data-quitar]', el)) b.addEventListener('click', () => {
    delete f[b.dataset.quitar];
    if (b.dataset.quitar === 'ids') delete f.ids_total;
    b.remove(); pagina = 1; cargar();
  });
  $('#paginacion', el).addEventListener('click', (e) => { const b = e.target.closest('[data-p]'); if (b) { pagina = Number(b.dataset.p); cargar(); el.scrollIntoView(); } });
  // El nombre es un enlace (teclado, lector de pantalla, abrir en otra pestaña); el resto de la fila también abre la ficha
  $('#filas', el).addEventListener('click', (e) => {
    if (e.target.closest('a')) return;
    const tr = e.target.closest('tr[data-id]');
    if (tr) ir(`/personas/${tr.dataset.id}`);
  });
  $('#exportar', el).addEventListener('click', async () => {
    try { await descargar('/api/exportar.xlsx', f); aviso('Exportación lista (quedó registrada en la auditoría)'); } catch (e) { aviso(e.message, 'error'); }
  });
  $('#nueva', el).addEventListener('click', () => formularioNuevaPersona({ cat, alCrear: (p) => ir(`/personas/${p.id}`) }));
  await cargar();
  return () => buscar.cancel();
}
