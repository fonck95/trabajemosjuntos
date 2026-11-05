// Modo reunión (7.13): buscar o registrar asistentes en segundos y completar su perfil en el momento con «Completar»
// (el mismo de Habitantes). La lista de asistentes llega con la proyección de fila del rol.
import { api, descargar, nuevaClave, puede, sesion } from '../api.js';
import { $, aviso, avisoError, confirmar, datosForm, debounce, dialogo, fecha, html, icono, montar, num, titulo } from '../ui.js';
import { administra, dialogoCompletar, formularioNuevaPersona, textoCedula, textoTelefono } from './comunes.js';

export async function vistaReunion(el, { params, ir }) {
  const id = Number(params[0]);
  let [r, cat] = await Promise.all([api.get(`/api/reuniones/${id}`), api.catalogos()]);
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const adm = administra();
  const propia = r.creado_por_uid != null && r.creado_por_uid === sesion.uid;
  const editable = adm || propia;
  const lineaFila = (p) => [textoCedula(p), textoTelefono(p), titulo(p.lugar || '')].filter(Boolean).join(' · ');

  montar(el, html`
    <div class="miga"><a href="/reuniones" data-ruta>Reuniones</a> › ${fecha(r.fecha)}</div>
    <div class="cabecera">
      <div><h1>${r.titulo}</h1><div class="sub">${fecha(r.fecha)}${r.hora ? ' · ' + r.hora : ''} · ${titulo(r.lugar_nombre || r.lugar_texto || 'Sin lugar')}${r.tema ? ' · ' + r.tema : ''}</div>
        ${r.abierta_a_equipo ? html`<div class="chips" style="margin-top:6px"><span class="chip azul">Abierta al equipo: los planilleros registran asistentes</span></div>` : ''}</div>
      <div class="acciones">
        ${editable ? html`<button class="btn" id="editar">Editar</button>` : ''}
        ${puede('exportar') ? html`<button class="btn" id="csv">${icono('descargar')} Asistentes (CSV)</button>` : ''}
        ${adm ? html`<button class="btn peligro" id="borrar">Borrar</button>` : ''}
      </div>
    </div>
    <div class="registro">
      <section class="tarjeta">
        <header><h2>Registrar asistentes</h2><span class="nota">Busque por nombre, cédula o celular</span></header>
        <label class="buscador grande">${icono('buscar')}<input class="entrada" id="buscar" type="search" placeholder="Escriba para buscar en la base única…" autocomplete="off" autofocus></label>
        <div class="resultados" id="resultados"></div>
        ${puede('personas.crear') ? html`<div id="nuevo-cta" style="margin-top:12px"><button class="btn oscuro" id="nuevo">${icono('mas')} Registrar persona nueva</button></div>` : ''}
      </section>
      <section class="tarjeta">
        <header><h2>Asistentes <span id="n-asist"></span></h2><span class="nota" id="nuevos"></span></header>
        <div id="necesidades" class="chips" style="margin-bottom:10px"></div>
        <div id="asistentes"></div>
      </section>
    </div>
    ${r.descripcion || r.compromisos ? html`<section class="tarjeta" style="margin-top:16px"><h2>Notas de la reunión</h2>
      ${r.descripcion ? html`<p>${r.descripcion}</p>` : ''}${r.compromisos ? html`<h3 style="font-size:14px">Compromisos</h3><p>${r.compromisos}</p>` : ''}</section>` : ''}`);

  const ids = () => new Set((r.asistentes || []).map((a) => a.id));

  function pintarAsistentes() {
    const asis = r.asistentes || [];
    $('#n-asist', el).textContent = `(${num(asis.length)})`;
    montar($('#necesidades', el), html`${(r.necesidades || []).map((n) => html`<span class="chip azul">${n.nombre} · ${n.n}</span>`)}`);
    montar($('#asistentes', el), asis.length ? html`${asis.map((a) => html`<div class="asistente">
        <div class="anillo" style="--p:${Number(a.completitud) || 0};width:42px;height:42px"><span style="width:32px;height:32px;font-size:11px">${Number(a.completitud) || 0}</span></div>
        <div class="q"><a href="/personas/${a.id}" data-ruta>${a.nombre}</a>
          <div class="sec">${lineaFila(a)}</div>
          ${(a.etiquetas || []).length ? html`<div class="chips" style="margin-top:4px">${a.etiquetas.map((e) => html`<span class="chip">${typeof e === 'object' ? e.nombre : e}</span>`)}</div>` : ''}
          ${a.nota ? html`<div class="sec" style="margin-top:4px">“${a.nota}”</div>` : ''}</div>
        <div class="acciones-asistente">${puede('personas.editar') && a.consentimiento !== 'no' ? html`<button class="btn chico" data-completar="${a.id}">${icono('completar')} Completar</button>` : ''}
          ${puede('personas.notas') ? html`<button class="btn chico fantasma" data-nota="${a.id}">Nota</button>` : ''}
          <button class="btn chico fantasma" data-quitar="${a.id}" aria-label="Quitar a ${a.nombre}">✕</button></div>
      </div>`)}` : html`<div class="vacio"><b>Nadie registrado aún</b>Busque a cada asistente.</div>`);
  }

  // Búsqueda: cada consulta lleva un turno; solo pinta la última y Enter solo usa resultados del texto escrito
  let turno = 0, consultaPintada = '', agregando = false;

  function limpiarBusqueda() {
    turno++;
    consultaPintada = '';
    $('#buscar', el).value = '';
    $('#resultados', el).replaceChildren();
  }

  async function agregar(pid) {
    if (agregando) return;
    agregando = true;
    try {
      r = await api.post(`/api/reuniones/${id}/asistentes`, { persona_id: pid }, { clave: nuevaClave() });
      pintarAsistentes();
      limpiarBusqueda();
      $('#buscar', el).focus();
      aviso('Asistencia registrada');
    } catch (err) { avisoError(err); } finally { agregando = false; }
  }

  async function buscarYa(texto) {
    const mio = ++turno;
    if (texto.length < 2) { consultaPintada = ''; $('#resultados', el).replaceChildren(); return; }
    let res;
    try { res = await api.get('/api/buscar', { q: texto }); } catch (e) { if (mio === turno) avisoError(e); return; }
    if (mio !== turno) return; // ya se escribió otra cosa (o se agregó a alguien)
    const lista = Array.isArray(res) ? res : res?.filas || [];
    const ya = ids();
    montar($('#resultados', el), lista.length ? html`${lista.map((p) => html`<div class="resultado">
        <div class="q"><b>${p.nombre}</b><small>${lineaFila(p) || 'Sin datos de contacto'}</small></div>
        ${ya.has(p.id) ? html`<span class="chip verde">Ya está</span>` : html`<button class="btn chico primario" data-agregar="${p.id}">Agregar</button>`}
      </div>`)}` : html`<div class="sec">No aparece en la base.${puede('personas.crear') ? ' Regístrela como persona nueva.' : ''}</div>`);
    consultaPintada = texto;
  }
  const buscar = debounce(buscarYa, 220);

  $('#buscar', el).addEventListener('input', (e) => {
    turno++; // lo que está en pantalla ya no corresponde al texto
    consultaPintada = null;
    buscar(e.target.value.trim());
  });
  $('#buscar', el).addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const texto = e.target.value.trim();
    // Si los resultados son de una búsqueda anterior, Enter busca ya lo escrito en vez de agregar a otra persona
    if (texto !== consultaPintada) { buscar.cancel(); buscarYa(texto); return; }
    // Solo el primer resultado: si ya está registrado, Enter no agrega a la persona siguiente
    const b = $('#resultados .resultado', el)?.querySelector('[data-agregar]');
    if (b) agregar(Number(b.dataset.agregar));
  });

  // Nota de la reunión en el historial de la persona
  async function nota(pid) {
    const a = (r.asistentes || []).find((x) => x.id === pid);
    const { el: d, cerrar } = dialogo({
      titulo: `Nota · ${titulo(a?.nombre || '')}`,
      cuerpo: html`<label class="campo"><span>Lo que dijo o pidió en la reunión</span><textarea name="nota" maxlength="4000" placeholder="Queda en su historial, ligado a esta reunión"></textarea>
        <small class="nota-sensibles">No anote salud, política, religión ni otros datos sensibles.</small></label>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" data-ok>Guardar</button>`,
    });
    const clave = nuevaClave();
    d.querySelector('[data-ok]').addEventListener('click', async (ev) => {
      const texto = $('[name="nota"]', d).value.trim();
      if (!texto) return;
      ev.currentTarget.disabled = true;
      try {
        await api.post(`/api/personas/${pid}/notas`, { texto, reunion_id: id }, { clave });
        r = await api.get(`/api/reuniones/${id}`);
        pintarAsistentes(); cerrar(); aviso('Nota guardada');
      } catch (err) { avisoError(err); ev.currentTarget.disabled = false; }
    });
  }

  el.addEventListener('click', async (e) => {
    const ag = e.target.closest('[data-agregar]');
    if (ag) return agregar(Number(ag.dataset.agregar));
    const qt = e.target.closest('[data-quitar]');
    if (qt) {
      try { r = await api.del(`/api/reuniones/${id}/asistentes/${qt.dataset.quitar}`); pintarAsistentes(); } catch (err) { avisoError(err); }
      return;
    }
    const co = e.target.closest('[data-completar]');
    if (co) {
      try {
        const p = await api.get(`/api/personas/${co.dataset.completar}`);
        const res = await dialogoCompletar(p, cat);
        if (res) { r = await api.get(`/api/reuniones/${id}`); pintarAsistentes(); }
      } catch (err) { avisoError(err); }
      return;
    }
    const no = e.target.closest('[data-nota]');
    if (no) return nota(Number(no.dataset.nota));
    if (e.target.closest('#nuevo')) {
      const t = $('#buscar', el).value.trim();
      const dig = t.replace(/\D/g, '');
      const prellenado = /\d/.test(t) && dig.length >= 5 ? (/^3\d{9}$/.test(dig) ? { telefono: dig } : { cedula: dig }) : { nombre: t };
      formularioNuevaPersona({ cat, reunionId: id, prellenado, alCrear: async (p) => {
        if (p.existente) return agregar(p.id);
        r = await api.get(`/api/reuniones/${id}`); pintarAsistentes(); limpiarBusqueda();
      } });
    }
    if (e.target.closest('#csv')) { try { await descargar(`/api/reuniones/${id}/asistentes.csv`); } catch (err) { aviso(err.message, 'error'); } }
    if (e.target.closest('#borrar') && await confirmar('¿Borrar la reunión? Las personas se conservan, pero se pierde el registro de asistencia.', { si: 'Borrar', peligro: true })) {
      try { await api.del(`/api/reuniones/${id}`); ir('/reuniones'); } catch (err) { avisoError(err); }
    }
    if (e.target.closest('#editar')) editar();
  });

  function editar() {
    const { el: d, cerrar } = dialogo({
      titulo: 'Editar reunión',
      cuerpo: html`<form class="form" id="f-ed">
        <label class="campo ancho"><span>Título</span><input name="titulo" value="${r.titulo}" required minlength="3" maxlength="160"></label>
        <label class="campo"><span>Fecha</span><input name="fecha" type="date" value="${r.fecha}" required></label>
        <label class="campo"><span>Hora</span><input name="hora" type="time" value="${r.hora ?? ''}"></label>
        <label class="campo ancho"><span>Tema</span><input name="tema" value="${r.tema ?? ''}" maxlength="160"></label>
        <label class="campo ancho"><span>Descripción</span><textarea name="descripcion" maxlength="4000">${r.descripcion ?? ''}</textarea></label>
        <label class="campo ancho"><span>Compromisos</span><textarea name="compromisos" maxlength="4000">${r.compromisos ?? ''}</textarea></label>
        ${adm ? html`<label class="casilla ancho"><input type="checkbox" name="abierta_a_equipo" ${r.abierta_a_equipo ? 'checked' : ''}> Permitir que planilleros registren asistentes</label>` : ''}
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g-ed">Guardar</button>`,
    });
    $('#g-ed', d).addEventListener('click', async (ev) => {
      const f = $('#f-ed', d);
      const boton = ev.currentTarget;
      if (boton.disabled || !f.reportValidity()) return;
      boton.disabled = true;
      const datos = datosForm(f);
      if (!adm) delete datos.abierta_a_equipo;
      try {
        await api.patch(`/api/reuniones/${id}`, datos);
        cerrar(); aviso('Reunión actualizada'); ir(`/reuniones/${id}`, { reemplazar: true });
      } catch (err) { avisoError(err); boton.disabled = false; }
    });
  }

  pintarAsistentes();
  return () => buscar.cancel();
}
