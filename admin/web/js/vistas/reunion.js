// Modo reunión: buscar o registrar asistentes en segundos y enriquecer su perfil en el momento.
import { api, descargar } from '../api.js';
import { $, aviso, avisoError, confirmar, datosForm, debounce, dialogo, fecha, html, icono, montar, num, titulo } from '../ui.js';
import { formularioNuevaPersona } from './comunes.js';

export async function vistaReunion(el, { params, ir }) {
  const id = Number(params[0]);
  let [r, cat] = await Promise.all([api.get(`/api/reuniones/${id}`), api.get('/api/catalogos')]);
  if (!el.isConnected) return; // mientras cargaba se pidió otra vista
  const necesidades = cat.etiquetas.filter((e) => e.grupo === 'necesidad');

  montar(el, html`
    <div class="miga"><a href="/reuniones" data-ruta>Reuniones</a> › ${fecha(r.fecha)}</div>
    <div class="cabecera">
      <div><h1>${r.titulo}</h1><div class="sub">${fecha(r.fecha)}${r.hora ? ' · ' + r.hora : ''} · ${titulo(r.lugar_nombre || r.lugar_texto || 'Sin lugar')}${r.tema ? ' · ' + r.tema : ''}</div></div>
      <div class="acciones">
        <button class="btn" id="editar">Editar</button>
        <button class="btn" id="csv">${icono('descargar')} Asistentes (CSV)</button>
        <button class="btn peligro" id="borrar">Borrar</button>
      </div>
    </div>
    <div class="registro">
      <section class="tarjeta">
        <header><h2>Registrar asistentes</h2><span class="nota">Busque por nombre, cédula o celular</span></header>
        <label class="buscador grande">${icono('buscar')}<input class="entrada" id="buscar" placeholder="Escriba para buscar en la base única…" autocomplete="off" autofocus></label>
        <div class="resultados" id="resultados"></div>
        <div id="nuevo-cta" style="margin-top:12px"><button class="btn oscuro" id="nuevo">${icono('mas')} Registrar persona nueva</button></div>
      </section>
      <section class="tarjeta">
        <header><h2>Asistentes <span id="n-asist"></span></h2><span class="nota" id="nuevos"></span></header>
        <div id="necesidades" class="chips" style="margin-bottom:10px"></div>
        <div id="asistentes"></div>
      </section>
    </div>
    ${r.descripcion || r.compromisos ? html`<section class="tarjeta" style="margin-top:16px"><h2>Notas de la reunión</h2>
      ${r.descripcion ? html`<p>${r.descripcion}</p>` : ''}${r.compromisos ? html`<h3 style="font-size:14px">Compromisos</h3><p>${r.compromisos}</p>` : ''}</section>` : ''}`);

  const ids = () => new Set(r.asistentes.map((a) => a.id));

  function pintarAsistentes() {
    $('#n-asist', el).textContent = `(${num(r.asistentes.length)})`;
    montar($('#necesidades', el), html`${r.necesidades.map((n) => html`<span class="chip azul">${n.nombre} · ${n.n}</span>`)}`);
    montar($('#asistentes', el), r.asistentes.length ? html`${r.asistentes.map((a) => html`<div class="asistente">
        <div class="anillo" style="--p:${a.completitud};width:42px;height:42px"><span style="width:32px;height:32px;font-size:11px">${a.completitud}</span></div>
        <div class="q"><a href="/personas/${a.id}" data-ruta>${a.nombre}</a>
          <div class="sec">${[a.cedula && 'CC ' + a.cedula, a.telefono, titulo(a.lugar || '')].filter(Boolean).join(' · ')}</div>
          ${a.etiquetas.length ? html`<div class="chips" style="margin-top:4px">${a.etiquetas.map((e) => html`<span class="chip">${e}</span>`)}</div>` : ''}
          ${a.nota ? html`<div class="sec" style="margin-top:4px">“${a.nota}”</div>` : ''}</div>
        <div style="display:flex;gap:4px"><button class="btn chico" data-enriquecer="${a.id}">Completar</button><button class="btn chico fantasma" data-quitar="${a.id}" aria-label="Quitar">✕</button></div>
      </div>`)}` : html`<div class="vacio"><b>Nadie registrado aún</b>Busque a cada asistente a la izquierda.</div>`);
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
      r = await api.post(`/api/reuniones/${id}/asistentes`, { persona_id: pid });
      pintarAsistentes();
      limpiarBusqueda();
      $('#buscar', el).focus();
      aviso('Asistencia registrada');
    } catch (err) { avisoError(err); } finally { agregando = false; }
  }

  async function buscarYa(texto) {
    const mio = ++turno;
    if (texto.length < 2) { consultaPintada = ''; $('#resultados', el).replaceChildren(); return; }
    const res = await api.get('/api/buscar', { q: texto });
    if (mio !== turno) return; // ya se escribió otra cosa (o se agregó a alguien)
    const ya = ids();
    montar($('#resultados', el), res.length ? html`${res.map((p) => html`<div class="resultado">
        <div class="q"><b>${p.nombre}</b><small>${[p.cedula && 'CC ' + p.cedula, p.telefono, titulo(p.lugar || '')].filter(Boolean).join(' · ') || 'Sin datos de contacto'}</small></div>
        ${ya.has(p.id) ? html`<span class="chip verde">Ya está</span>` : html`<button class="btn chico primario" data-agregar="${p.id}">Agregar</button>`}
      </div>`)}` : html`<div class="sec">No aparece en la base. Regístrela como persona nueva.</div>`);
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
  el.addEventListener('click', async (e) => {
    const ag = e.target.closest('[data-agregar]');
    if (ag) return agregar(Number(ag.dataset.agregar));
    const qt = e.target.closest('[data-quitar]');
    if (qt) {
      try { r = await api.del(`/api/reuniones/${id}/asistentes/${qt.dataset.quitar}`); pintarAsistentes(); } catch (err) { avisoError(err); }
      return;
    }
    const en = e.target.closest('[data-enriquecer]');
    if (en) return enriquecer(Number(en.dataset.enriquecer));
    if (e.target.closest('#nuevo')) {
      formularioNuevaPersona({ cat, reunionId: id, nombreInicial: $('#buscar', el).value.trim(), alCrear: async (p) => {
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

  // Completar en el momento lo que más importa de cada asistente
  async function enriquecer(pid) {
    const p = await api.get(`/api/personas/${pid}`);
    const tiene = new Set(p.etiquetas.map((x) => x.id));
    const { el: d, cerrar } = dialogo({
      titulo: `Completar: ${titulo(p.nombre)}`,
      cuerpo: html`<form class="form" id="f-enr">
        <label class="campo"><span>Cédula</span><input name="cedula" value="${p.cedula ?? ''}" inputmode="numeric"></label>
        <label class="campo"><span>Celular</span><input name="telefono" value="${p.telefono ?? ''}" inputmode="tel"></label>
        <label class="campo"><span>Ocupación</span><input name="ocupacion" value="${p.ocupacion ?? ''}"></label>
        <label class="campo"><span>Personas en el hogar</span><input name="personas_hogar" type="number" min="0" max="40" value="${p.personas_hogar ?? ''}"></label>
        <label class="campo"><span>Autorización de datos</span><select name="consentimiento">${[['pendiente', 'Pendiente'], ['si', 'Sí, autorizó'], ['no', 'No autorizó']].map(([v, t]) => html`<option value="${v}" ${p.consentimiento === v ? 'selected' : ''}>${t}</option>`)}</select></label>
        <label class="interruptor" style="align-self:end"><span>Líder comunitario</span><input type="checkbox" name="lider" ${p.lider ? 'checked' : ''}></label>
        <div class="campo ancho"><span>Necesidades</span><div class="chips">${necesidades.map((x) => html`<button type="button" class="chip" data-et="${x.id}" aria-pressed="${tiene.has(x.id)}">${x.nombre}</button>`)}</div></div>
        <label class="campo ancho"><span>Lo que dijo o pidió en la reunión</span><textarea name="nota" placeholder="Queda en su historial, ligado a esta reunión" maxlength="4000"></textarea></label>
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="guardar-enr">Guardar</button>`,
    });
    const f = $('#f-enr', d);
    f.addEventListener('click', (ev) => { const c = ev.target.closest('[data-et]'); if (c) c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') !== 'true'); });
    $('#guardar-enr', d).addEventListener('click', async (ev) => {
      const boton = ev.currentTarget;
      if (boton.disabled || !f.reportValidity()) return;
      const datos = datosForm(f);
      const nota = datos.nota; delete datos.nota;
      for (const k of Object.keys(datos)) if (String(datos[k] ?? '') === String(p[k] ?? '') || (k === 'lider' && !!datos[k] === !!p[k])) delete datos[k];
      if (datos.consentimiento === 'si' && p.consentimiento !== 'si') datos.consentimiento_fecha = r.fecha;
      // El diálogo solo muestra necesidades: las etiquetas de los demás grupos (intereses, roles) se conservan
      const mostradas = new Set(necesidades.map((x) => x.id));
      const etiquetas = [...p.etiquetas.map((x) => x.id).filter((x) => !mostradas.has(x)),
        ...[...f.querySelectorAll('[data-et][aria-pressed="true"]')].map((b) => Number(b.dataset.et))];
      if (etiquetas.length !== tiene.size || etiquetas.some((x) => !tiene.has(x))) datos.etiquetas = etiquetas;
      boton.disabled = true; // evita guardar dos veces (y duplicar la nota) con un doble clic
      try {
        await api.patch(`/api/personas/${pid}`, datos);
        if (nota) await api.post(`/api/personas/${pid}/notas`, { texto: nota, reunion_id: id });
        r = await api.get(`/api/reuniones/${id}`);
        pintarAsistentes(); cerrar(); aviso('Perfil actualizado');
      } catch (err) { avisoError(err); boton.disabled = false; }
    });
  }

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
      </form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g-ed">Guardar</button>`,
    });
    $('#g-ed', d).addEventListener('click', async (ev) => {
      const f = $('#f-ed', d);
      const boton = ev.currentTarget;
      if (boton.disabled || !f.reportValidity()) return;
      boton.disabled = true;
      try {
        await api.patch(`/api/reuniones/${id}`, datosForm(f));
        cerrar(); aviso('Reunión actualizada'); ir(`/reuniones/${id}`, { reemplazar: true });
      } catch (err) { avisoError(err); boton.disabled = false; }
    });
  }

  pintarAsistentes();
  return () => buscar.cancel();
}
