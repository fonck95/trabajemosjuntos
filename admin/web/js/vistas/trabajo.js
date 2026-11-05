// Mi trabajo (7.7): las listas del planillero (tarjetas que abren Habitantes), la persona actual y la cola del
// consultor, y los indicadores propios. El administrador y el coordinador ven las mismas tarjetas para toda la base,
// con un selector de usuario.
import { api, ErrorApi, sesion } from '../api.js';
import { marcarLlamada } from '../llamadas.js';
import { enlaceWhatsapp, esCelular, marcable, telefonosUsables } from '../modelo.js';
import { $, $$, aviso, avisoError, chipAbordaje, chipAutorizacion, debounce, html, icono, montar, num, titulo } from '../ui.js';
import { dialogoAcercamiento, mensajeNoContactable } from './acercamiento.js';
import { administra } from './comunes.js';
import { pintarIndicadores } from './usuarios.js';

const ACTUAL = 'yj_persona_actual'; // solo el id, en sessionStorage: al volver (o recargar) la persona sigue ahí
const LISTAS_C = [['por_llamar', 'Por llamar'], ['volver_a_llamar', 'Volver a llamar'], ['mis_hoy', 'Hoy']];
const leerActual = () => { try { return Number(sessionStorage.getItem(ACTUAL)) || null; } catch { return null; } };
const guardarActual = (pid) => { try { if (pid) sessionStorage.setItem(ACTUAL, String(pid)); else sessionStorage.removeItem(ACTUAL); } catch { /* nada */ } };

export async function vistaTrabajo(el, ctx) {
  if (sesion.rol === 'consultor') return trabajoConsultor(el, ctx);
  return trabajoListas(el, ctx);
}

// Etiquetas del resumen del día y la semana que pueda traer /api/trabajo
const RESUMEN = { creadas: 'Creadas', actualizadas: 'Actualizadas', acercamientos: 'Acercamientos', contactadas: 'Contactadas', visitas: 'Visitas', cedulas: 'Cédulas', puesto_mesa: 'Puestos y mesas' };
const resumenHtml = (t, r) => {
  const filas = Object.entries(r || {}).filter(([, n]) => typeof n === 'number');
  return filas.length ? html`<div class="resumen-dia"><b>${t}</b>${filas.map(([k, n]) => html`<span>${RESUMEN[k] || k.replace(/_/g, ' ')} <b>${num(n)}</b></span>`)}</div>` : '';
};

// ───────── Planillero, administrador y coordinador ─────────
async function trabajoListas(el, { q, ir }) {
  const adm = administra();
  let uid = adm && q.get('uid') ? Number(q.get('uid')) : null;
  const cat = await api.catalogos();
  if (!el.isConnected) return;
  const usuarios = (cat.usuarios || []).filter((u) => u.activo !== false);

  montar(el, html`
    <div class="cabecera">
      <div><h1>Mi trabajo</h1><div class="sub" id="sub-trabajo">${adm ? 'Toda la base' : 'Lo que falta en su zona'}</div></div>
      ${adm && usuarios.length ? html`<div class="acciones"><label class="campo selector-usuario"><span>Ver como</span><select id="uid">
        <option value="">Toda la base</option>${usuarios.map((u) => html`<option value="${u.id}" ${uid === u.id ? 'selected' : ''}>${u.nombre || u.usuario} · ${u.rol}</option>`)}</select></label></div>` : ''}
    </div>
    <div id="listas"><div class="cargando"><div class="giro"></div></div></div>
    <section class="tarjeta" id="alcance" hidden></section>
    <section class="tarjeta indicadores-trabajo"><header><h2>${adm && !uid ? 'Mis indicadores' : 'Indicadores'}</h2><span class="nota">Últimos 30 días</span></header><div id="indicadores"><div class="cargando"><div class="giro"></div></div></div></section>`);

  async function cargar() {
    const t = await api.get('/api/trabajo', uid ? { uid } : undefined);
    if (!el.isConnected) return;
    const listas = t.listas || [];
    // «Visitar: no contestan o sin número» es la lista que deja el consultor para el trabajo de campo
    montar($('#listas', el), listas.length ? html`<div class="kpis kpis-trabajo">${listas.map((l) => html`<a class="kpi ${l.clave === 'visitar' ? 'acento' : ''} ${l.n ? '' : 'en-cero'}" href="${l.enlace || '/personas'}" data-ruta>
        <div class="t">${l.titulo}</div><div class="v">${num(l.n)}</div><div class="d">${l.n ? 'Ver en Habitantes →' : 'Nada pendiente'}</div></a>`)}</div>
      ${resumenHtml('Hoy', t.hoy)}${resumenHtml('Esta semana', t.semana)}`
      : html`<div class="tarjeta vacio"><b>Nada pendiente</b>No hay listas de trabajo para su zona.</div>`);
    const al = t.alcance;
    const caja = $('#alcance', el);
    const lugares = (al?.lugares || []).map((x) => (typeof x === 'object' ? x.nombre : (cat.lugares || []).find((l) => l.id === x)?.nombre || `Lugar ${x}`));
    const areas = (al?.areas || []).map((x) => (typeof x === 'object' ? x.nombre : `Zona ${x}`));
    caja.hidden = !al;
    if (al) {
      montar(caja, html`<header><h2>Su zona de trabajo</h2></header>${lugares.length || areas.length
        ? html`<div class="chips">${areas.map((a) => html`<span class="chip azul">${icono('zona')} ${a}</span>`)}${lugares.map((l) => html`<span class="chip borde">${titulo(l)}</span>`)}</div>`
        : html`<p class="sec">Sin asignación: trabaja con toda la base.</p>`}`);
    }
    try {
      const ind = await api.get(uid ? `/api/usuarios/${uid}/indicadores` : '/api/yo/indicadores');
      if (el.isConnected) pintarIndicadores($('#indicadores', el), ind);
    } catch (e) {
      if (el.isConnected) montar($('#indicadores', el), html`<p class="sec">${e.message}</p>`);
    }
  }

  $('#uid', el)?.addEventListener('change', (e) => {
    uid = e.target.value ? Number(e.target.value) : null;
    history.replaceState({}, '', location.pathname + (uid ? `?uid=${uid}` : ''));
    montar($('#listas', el), html`<div class="cargando"><div class="giro"></div></div>`);
    cargar().catch(avisoError);
  });
  await cargar();
}

// ───────── Consultor ─────────
async function trabajoConsultor(el) {
  let lista = 'por_llamar';
  let pagina = 1, filas = [], total = 0;
  let actual = null; // ficha de la persona actual
  let info = {};

  montar(el, html`
    <div class="cabecera"><div><h1>Mi trabajo</h1><div class="sub" id="sub-trabajo">Su cola de llamadas</div></div></div>
    <section class="tarjeta persona-actual" id="actual"></section>
    <label class="buscador grande buscador-trabajo">${icono('buscar')}<input class="entrada" id="buscar" type="search" autocomplete="off" placeholder="Nombre, o número completo si le están llamando"></label>
    <div class="resultados" id="resultados"></div>
    <div class="pestanas" role="tablist" id="listas-c">${LISTAS_C.map(([k, t]) => html`<button role="tab" data-lista="${k}" aria-selected="${k === lista}">${t} <span class="n" data-n="${k}"></span></button>`)}</div>
    <div id="cola"></div>
    <section class="tarjeta indicadores-trabajo"><header><h2>Mis indicadores</h2><span class="nota">Últimos 30 días</span></header><div id="indicadores"><div class="cargando"><div class="giro"></div></div></div></section>`);

  // Explicación de la cola vacía: solo se llama a quien autorizó
  const vacia = () => html`<div class="vacio cola-vacia"><b>0 personas en la cola</b>Solo se llama a quien autorizó el contacto${info.pendientes_sin_autorizacion != null ? html`; hay <b>${num(info.pendientes_sin_autorizacion)}</b> pendientes de autorización` : ''}.</div>`;

  function botonesContacto(p, { indice = 0, numero = null, whatsapp = null, canales = null } = {}) {
    const usables = telefonosUsables(p);
    const n = numero || usables[indice]?.numero;
    if (!n) return html`<span class="sec">Sin número usable</span>`;
    const permitidos = canales || ['llamada', ...(esCelular(n) ? ['whatsapp'] : [])];
    return html`${permitidos.includes('llamada') ? html`<a class="btn" href="tel:${marcable(n)}" data-llamar="${p.id}" data-indice="${indice}" data-canal="llamada">${icono('telefono')} Llamar</a>` : ''}
      ${permitidos.includes('whatsapp') && esCelular(n) && whatsapp !== false ? html`<a class="btn" href="${enlaceWhatsapp(n)}" target="_blank" rel="noopener noreferrer" data-llamar="${p.id}" data-indice="${indice}" data-canal="whatsapp">${icono('whatsapp')} WhatsApp</a>` : ''}`;
  }

  function pintarActual() {
    const caja = $('#actual', el);
    if (!actual) {
      montar(caja, html`<div class="sin-actual"><div><b>Nadie en curso</b><p class="sec">«Siguiente» le asigna la próxima persona de la cola durante 20 minutos.</p></div>
        <button class="btn primario grande" data-siguiente>${icono('siguiente')} Siguiente</button></div>`);
      return;
    }
    const p = actual;
    const usables = telefonosUsables(p);
    const t0 = usables[0];
    montar(caja, html`<div class="etiqueta-actual">Persona actual</div>
      <h2 class="nombre-actual"><a href="/personas/${p.id}" data-ruta>${p.nombre}</a></h2>
      <div class="sec">${[titulo(p.lugar_nombre || p.lugar || ''), p.rango_edad && `${p.rango_edad} años`].filter(Boolean).join(' · ')}</div>
      <div class="chips" style="margin:8px 0">${chipAbordaje(p.abordaje)}${chipAutorizacion(p)}</div>
      ${t0 ? html`<div class="numero-actual">${t0.numero}${usables.length > 1 ? html` <small class="sec">y ${usables.length - 1} más en la ficha</small>` : ''}</div>` : ''}
      <div class="fila-botones botones-actual">${botonesContacto(p)}
        <button class="btn primario" data-registrar="${p.id}">${icono('acercamiento')} Registrar</button>
        <button class="btn" data-saltar>Saltar</button>
        <button class="btn oscuro" data-siguiente>${icono('siguiente')} Siguiente</button></div>`);
  }

  async function cargarActual(pid) {
    try {
      actual = await api.get(`/api/personas/${pid}`);
      guardarActual(pid);
    } catch (e) {
      actual = null;
      guardarActual(null);
      if (!(e instanceof ErrorApi && [403, 404, 409].includes(e.estado))) avisoError(e);
    }
    if (el.isConnected) pintarActual();
  }

  let pidiendo = false;
  async function siguiente({ saltar = false } = {}) {
    if (pidiendo) return;
    pidiendo = true;
    try {
      if (saltar && actual) await api.del(`/api/trabajo/tomar/${actual.id}`).catch(() => {});
      const lst = lista === 'mis_hoy' ? 'por_llamar' : lista;
      const r = await api.post(`/api/trabajo/siguiente?lista=${lst}`);
      if (r && typeof r === 'object' && r.id) {
        actual = r;
        guardarActual(r.id);
        pintarActual();
        $('#actual', el).scrollIntoView({ block: 'start', behavior: 'smooth' });
      } else {
        actual = null;
        guardarActual(null);
        montar($('#actual', el), vacia());
      }
    } catch (e) { avisoError(e); } finally { pidiendo = false; }
  }

  async function cargarCola({ mas = false } = {}) {
    if (!mas) { pagina = 1; filas = []; montar($('#cola', el), html`<div class="cargando"><div class="giro"></div></div>`); }
    const d = await api.get('/api/trabajo/cola', { lista, pagina });
    if (!el.isConnected) return;
    total = d.total || 0;
    filas = mas ? [...filas, ...(d.filas || [])] : d.filas || [];
    const n = $(`[data-n="${lista}"]`, el);
    if (n) n.textContent = num(total);
    const hay = filas.length < total && pagina < 10;
    montar($('#cola', el), filas.length ? html`<div class="filas-cola">${filas.map((f) => html`<div class="fila-cola tarjeta" data-id="${f.id}">
        <div class="q"><b>${f.nombre}</b><div class="sec">${[titulo(f.lugar || ''), f.rango_edad && `${f.rango_edad} años`].filter(Boolean).join(' · ')}</div>
          <div class="chips">${chipAbordaje(f.abordaje)}${f.abordaje?.ultimo_resultado ? html`<span class="chip borde">${String(f.abordaje.ultimo_resultado).replace(/_/g, ' ')}</span>` : ''}</div></div>
        <div class="fila-botones">${lista === 'mis_hoy' ? '' : botonesContacto({ id: f.id, telefonos: [] }, { indice: f.telefono_indice ?? 0, numero: f.telefono, whatsapp: f.whatsapp, canales: f.canales_permitidos })}
          <button class="btn chico primario" data-registrar="${f.id}">Registrar</button></div></div>`)}</div>
      ${hay ? html`<button class="btn" id="mas-cola">Ver más</button>` : ''}`
      : lista === 'mis_hoy' ? html`<div class="vacio"><b>Hoy todavía no registra contactos</b></div>` : vacia());
  }

  async function info0() {
    try {
      info = await api.get('/api/trabajo');
      for (const l of info.listas || []) { const n = $(`[data-n="${l.clave}"]`, el); if (n) n.textContent = num(l.n); }
    } catch { info = {}; }
  }

  // Llamar o escribir desde la cola o la persona actual: se toma a la persona (para que nadie más la llame) y se anota
  // la llamada sin registrar. El enlace tel: o de WhatsApp sigue su curso
  function alLlamar(a) {
    const pid = Number(a.dataset.llamar);
    marcarLlamada({ pid, indice: Number(a.dataset.indice) || 0, canal: a.dataset.canal });
    api.post(`/api/trabajo/tomar/${pid}`, undefined, { keepalive: true }).catch((e) => { if (e instanceof ErrorApi && e.codigo === 'tomada') aviso(`Ya la tiene ${e.detalle?.usuario || 'otro consultor'}`, 'error', 6000); });
    if (!actual || actual.id !== pid) { guardarActual(pid); cargarActual(pid); }
  }

  async function registrar(pid) {
    try {
      if (!actual || actual.id !== pid) {
        await api.post(`/api/trabajo/tomar/${pid}`);
        actual = await api.get(`/api/personas/${pid}`);
        guardarActual(pid);
        pintarActual();
      }
      const r = await dialogoAcercamiento(actual, { alDeshacer: () => cargarActual(pid) });
      if (!r) return;
      // Registrado: pasa a la siguiente persona de la cola (7.5)
      await siguiente();
      cargarCola().catch(avisoError);
      info0();
    } catch (e) {
      if (e instanceof ErrorApi && e.codigo === 'tomada') aviso(`Ya la tiene ${e.detalle?.usuario || 'otro consultor'}`, 'error', 6000);
      else if (e instanceof ErrorApi && e.codigo === 'no_contactable') aviso(mensajeNoContactable(e), 'error', 7000);
      else avisoError(e);
    }
  }

  // Buscador: por nombre (3 letras o más) o por el número completo de una llamada entrante
  let turno = 0;
  const buscar = debounce(async (texto) => {
    const mio = ++turno;
    const dig = texto.replace(/\D/g, '');
    const caja = $('#resultados', el);
    if (/\d/.test(texto) ? dig.length !== 10 : texto.length < 3) { caja.replaceChildren(); return; }
    try {
      const r = await api.get('/api/buscar', { q: /\d/.test(texto) ? dig : texto });
      if (mio !== turno || !el.isConnected) return;
      const lista0 = Array.isArray(r) ? r : r?.filas || [];
      montar(caja, lista0.length ? html`${lista0.map((x) => html`<div class="resultado"><div class="q"><b>${x.nombre}</b><small>${titulo(x.lugar || '')}${x.abordaje_estado ? ' · ' + String(x.abordaje_estado).replace(/_/g, ' ') : ''}</small></div>
        ${x.contactable === false ? html`<span class="chip">No contactable</span>` : html`<button class="btn chico primario" data-abrir="${x.id}">Abrir</button>`}</div>`)}`
        : html`<p class="sec">Nadie con ese ${/\d/.test(texto) ? 'número' : 'nombre'}.</p>`);
    } catch (e) { if (mio === turno) avisoError(e); }
  }, 350);
  $('#buscar', el).addEventListener('input', (e) => buscar(e.target.value.trim()));

  el.addEventListener('click', async (e) => {
    const ll = e.target.closest('[data-llamar]');
    if (ll) { alLlamar(ll); return; }
    if (e.target.closest('[data-siguiente]')) { siguiente(); return; }
    if (e.target.closest('[data-saltar]')) { siguiente({ saltar: true }); return; }
    const rg = e.target.closest('[data-registrar]');
    if (rg) { registrar(Number(rg.dataset.registrar)); return; }
    const ab = e.target.closest('[data-abrir]');
    if (ab) {
      const pid = Number(ab.dataset.abrir);
      try {
        await api.post(`/api/trabajo/tomar/${pid}`);
        await cargarActual(pid);
        $('#resultados', el).replaceChildren();
        $('#buscar', el).value = '';
        $('#actual', el).scrollIntoView({ block: 'start', behavior: 'smooth' });
      } catch (err) {
        if (err instanceof ErrorApi && err.codigo === 'tomada') aviso(`Ya la tiene ${err.detalle?.usuario || 'otro consultor'}`, 'error', 6000);
        else avisoError(err);
      }
      return;
    }
    const tab = e.target.closest('[data-lista]');
    if (tab) {
      lista = tab.dataset.lista;
      for (const b of $$('[data-lista]', el)) b.setAttribute('aria-selected', b === tab);
      cargarCola().catch(avisoError);
      return;
    }
    if (e.target.closest('#mas-cola')) { pagina += 1; cargarCola({ mas: true }).catch(avisoError); }
  });

  const pid = leerActual();
  if (pid) await cargarActual(pid); else pintarActual();
  await info0();
  try { await cargarCola(); } catch (e) { montar($('#cola', el), html`<div class="vacio"><b>No se pudo cargar la cola</b>${e.message}</div>`); }
  try {
    const ind = await api.get('/api/yo/indicadores');
    if (el.isConnected) pintarIndicadores($('#indicadores', el), ind, { rol: 'consultor' });
  } catch (e) { if (el.isConnected) montar($('#indicadores', el), html`<p class="sec">${e.message}</p>`); }
  return () => buscar.cancel();
}
